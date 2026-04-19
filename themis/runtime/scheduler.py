"""Four-state query dispatcher.

Takes a validated query, runs the appropriate solvers, and classifies
the outcome into one of:

- structurally_solved
- numerically_solved
- needs_investigation
- outside_language

See 理论框架_v0_1.md §12 for the formal definitions of these states.

Slice 1 only implements cause-query dispatch. Other in-language query
kinds (assoc / effect / identify / probability) surface as
``needs_investigation`` with a missing_information entry noting the
solver gap — never as a silent drop or a fabricated False answer.
"""
from __future__ import annotations

import networkx as nx

from ..input.semantic_validator import validate_formula
from ..types import (
    AssocQuery,
    Atom,
    CauseQuery,
    EffectQuery,
    IdentifyQuery,
    MissingItem,
    MissingKind,
    NumericResult,
    Priority,
    ProbabilityQuery,
    Program,
    Query,
    QueryKind,
    QueryResult,
    QueryStatement,
    ResultStatus,
    StructuralResult,
    ValuedAtom,
)
from . import (
    confidence_calc,
    formula_builder,
    investigation_pusher,
    numeric_estimator,
    structural_solver,
)
from .numeric_estimator import InsufficientTheta, ProbabilityKey, Theta


_QUERY_KIND_OF: dict[type, QueryKind] = {
    CauseQuery: QueryKind.CAUSE,
    AssocQuery: QueryKind.ASSOC,
    EffectQuery: QueryKind.EFFECT,
    IdentifyQuery: QueryKind.IDENTIFY,
    ProbabilityQuery: QueryKind.PROBABILITY,
}


def _atom_to_str(atom: Atom) -> str:
    args = ",".join(a.name for a in atom.args)
    return f"{atom.predicate}({args})"


def _query_kind(q: Query) -> QueryKind:
    kind = _QUERY_KIND_OF.get(type(q))
    if kind is None:
        raise AssertionError(f"unknown query type {type(q).__name__}")
    return kind


def _dispatch_cause(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: CauseQuery = stmt.query  # type: ignore[assignment]
    exists = structural_solver.has_directed_path(graph, q.from_atom, q.to_atom)
    paths: tuple[tuple[Atom, ...], ...] = ()
    if exists:
        paths = structural_solver.directed_paths(graph, q.from_atom, q.to_atom)
    supporting = tuple(tuple(_atom_to_str(a) for a in p) for p in paths)
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.CAUSE,
        query_id=stmt.id,
        structural_result=StructuralResult(value=exists, supporting_paths=supporting),
    )


def _dispatch_identify(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: IdentifyQuery = stmt.query  # type: ignore[assignment]
    x = q.intervention.atom
    y = q.target

    missing_atoms = [
        atom for atom in (x, y, *q.given) if atom not in graph
    ]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.IDENTIFY,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(atom)}",
                    priority=Priority.HIGH,
                    reason="query atom is not in the instantiated variable set V",
                )
                for atom in missing_atoms
            ),
        )

    adjustment_sets = structural_solver.minimal_adjustment_sets(
        graph, x, y, given=q.given
    )

    if not adjustment_sets:
        # No valid back-door adjustment exists under v0.1's simple
        # DAG model. Report an unidentifiable verdict.
        return QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.IDENTIFY,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
        )

    chosen = min(adjustment_sets, key=len)

    # Topological order within the chosen set so chain-rule factors
    # in the joint P(Z1,...,Zk|W) align with structural parenthood.
    topo = [n for n in nx.topological_sort(graph) if n in chosen]

    target_va = ValuedAtom(atom=y, value=None)
    intervention_va = ValuedAtom(atom=x, value=q.intervention.value)
    observed_vas = tuple(ValuedAtom(atom=g, value=None) for g in q.given)

    formula = formula_builder.backdoor_formula(
        target=target_va,
        intervention=intervention_va,
        adjustment_set=tuple(topo),
        observed=observed_vas,
    )

    # Defensive sanity check: every formula we emit must be well-formed.
    validate_formula(formula)

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=StructuralResult(value=True),
        formula=formula,
    )


def _dispatch_assoc(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: AssocQuery = stmt.query  # type: ignore[assignment]
    connected = structural_solver.is_d_connected(graph, q.left, q.right, q.given)
    paths: tuple[tuple[Atom, ...], ...] = ()
    if connected:
        paths = structural_solver.open_paths(graph, q.left, q.right, q.given)
    supporting = tuple(tuple(_atom_to_str(a) for a in p) for p in paths)
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.ASSOC,
        query_id=stmt.id,
        structural_result=StructuralResult(value=connected, supporting_paths=supporting),
    )


def _missing_parameter_from_key(key: ProbabilityKey | None, reason: str) -> MissingItem:
    """Build a MissingItem that points at the exact conditional
    probability the evaluator could not resolve."""
    if key is None:
        name = "numeric:unresolved_query_bound"
    else:
        # Sort by a derived key but keep the original Atom around so
        # we can still read predicate/value on the output side.
        given_pairs = sorted(
            key.given,
            key=lambda pair: (pair[0].predicate, str(pair[1])),
        )
        given_repr = ",".join(
            f"{a.predicate}={v}" for a, v in given_pairs
        )
        name = (
            f"parameter:P({key.target_atom.predicate}={key.target_value}"
            f"|{given_repr})"
        )
    return MissingItem(
        kind=MissingKind.PARAMETER,
        name=name,
        priority=Priority.HIGH,
        reason=reason,
    )


def _try_numeric(
    stmt: QueryStatement,
    formula,
    theta: Theta,
    kind: QueryKind,
) -> QueryResult:
    """Evaluate a formula with the current Theta; on InsufficientTheta
    surface a structured needs_investigation naming the missing parameter."""
    try:
        value = numeric_estimator.estimate_formula(formula, theta)
    except InsufficientTheta as exc:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=kind,
            query_id=stmt.id,
            formula=formula,
            missing_information=(_missing_parameter_from_key(exc.missing_key, exc.reason),),
        )
    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=kind,
        query_id=stmt.id,
        formula=formula,
        numeric_result=NumericResult(value=value),
    )


def _dispatch_effect(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: EffectQuery = stmt.query  # type: ignore[assignment]
    x, y = q.intervention.atom, q.target

    missing_atoms = [a for a in (x, y, *q.given) if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason="query atom is not in the instantiated variable set V",
                )
                for a in missing_atoms
            ),
        )

    adjustment_sets = structural_solver.minimal_adjustment_sets(
        graph, x, y, given=q.given
    )
    if not adjustment_sets:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="identification:not_identifiable",
                    priority=Priority.HIGH,
                    reason="no valid back-door adjustment exists under v0.1",
                ),
            ),
        )

    chosen = min(adjustment_sets, key=len)
    topo = [n for n in nx.topological_sort(graph) if n in chosen]
    formula = formula_builder.backdoor_formula(
        target=ValuedAtom(atom=y, value=None),
        intervention=ValuedAtom(atom=x, value=q.intervention.value),
        adjustment_set=tuple(topo),
        observed=tuple(ValuedAtom(atom=g, value=None) for g in q.given),
    )
    validate_formula(formula)
    return _try_numeric(stmt, formula, numeric_estimator.empty_theta(), QueryKind.EFFECT)


def _dispatch_probability(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: ProbabilityQuery = stmt.query  # type: ignore[assignment]

    missing_atoms = [a for a in (q.target, *q.given) if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.PROBABILITY,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason="query atom is not in the instantiated variable set V",
                )
                for a in missing_atoms
            ),
        )

    # A plain probability query is a single conditional reference.
    formula = formula_builder._conditional(  # type: ignore[attr-defined]
        ValuedAtom(atom=q.target, value=None),
        tuple(ValuedAtom(atom=g, value=None) for g in q.given),
    )
    return _try_numeric(stmt, formula, numeric_estimator.empty_theta(), QueryKind.PROBABILITY)


def _attach_investigation(result: QueryResult) -> QueryResult:
    """For needs_investigation results with missing_information but no
    investigation_requests yet, populate the requests from the missing
    items."""
    if result.status != ResultStatus.NEEDS_INVESTIGATION:
        return result
    if result.investigation_requests:
        return result
    if not result.missing_information:
        return result
    from dataclasses import replace

    return replace(
        result,
        investigation_requests=investigation_pusher.push(result.missing_information),
    )


def _gather_input_confidences(
    program: Program, stmt: QueryStatement, result: QueryResult
) -> tuple[float | None, ...]:
    """Collect confidences from the model inputs that contributed to
    this query's answer.

    v0.1 returns an empty tuple: structural queries depend on the
    causal DAG (which carries no confidence annotation in the current
    schema) and numeric queries never reach a numeric answer yet. The
    function exists as a single, named extension point — when Theta is
    populated in a later slice, collect probability / observation
    confidences here.
    """
    return ()


def _attach_confidence(
    program: Program, stmt: QueryStatement, result: QueryResult
) -> QueryResult:
    """Route every result through ``confidence_calc.composite`` so the
    field is explicitly populated (rather than silently left at the
    dataclass default). v0.1 always yields None because no inputs are
    collected; the wiring is in place so downstream consumers can
    reason about confidence uniformly and a future slice only needs
    to enrich ``_gather_input_confidences``."""
    from dataclasses import replace

    inputs = _gather_input_confidences(program, stmt, result)
    computed = confidence_calc.composite(*inputs)
    if computed is None and result.confidence is None:
        return result  # avoid pointless dataclass churn
    return replace(result, confidence=computed)


def dispatch(program: Program, stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    """Route a query to its solver(s) and assemble a QueryResult."""
    q = stmt.query
    if isinstance(q, CauseQuery):
        result = _dispatch_cause(stmt, graph)
    elif isinstance(q, AssocQuery):
        result = _dispatch_assoc(stmt, graph)
    elif isinstance(q, IdentifyQuery):
        result = _dispatch_identify(stmt, graph)
    elif isinstance(q, EffectQuery):
        result = _dispatch_effect(stmt, graph)
    elif isinstance(q, ProbabilityQuery):
        result = _dispatch_probability(stmt, graph)
    else:
        # Truly unknown type: fail loudly. The schema layer should
        # have already rejected it; reaching here is a programmer bug.
        raise AssertionError(f"unknown query type {type(q).__name__}")
    result = _attach_investigation(result)
    result = _attach_confidence(program, stmt, result)
    return result


def dispatch_all(program: Program, graph: nx.DiGraph) -> tuple[QueryResult, ...]:
    """Run every QueryStatement in the program against a single shared
    graph projection.

    Unlike a silent-drop approach, every query surfaces a result —
    unimplemented kinds return ``needs_investigation``.
    """
    return tuple(
        dispatch(program, stmt, graph)
        for stmt in program.statements
        if isinstance(stmt, QueryStatement)
    )
