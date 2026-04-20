"""Four-state query dispatcher.

Takes a validated query, runs the appropriate solvers, and classifies
the outcome into one of:

- structurally_solved   — cause / assoc / identify verdict reached
- numerically_solved    — effect / probability evaluated against Theta
- needs_investigation   — solvable in principle but data / solver gap
- outside_language      — query type not in v0.1 language

See 理论框架_v0_1.md §12 for the formal definitions of these states.

Dispatch routing (v0.1, after slice 6 + slice 7):

- ``cause``       -> ``_dispatch_cause``     : directed-path existence.
- ``assoc``       -> ``_dispatch_assoc``     : d-separation + open-path
                                                 enumeration under the
                                                 conditioning set.
- ``identify``    -> ``_dispatch_identify``  : back-door adjustment
                                                 search, returns a
                                                 formula AST; handles
                                                 cardinality >= 2 via
                                                 chain-rule factoring.
- ``effect``      -> ``_dispatch_effect``    : back-door identify, then
                                                 numeric evaluation via
                                                 Theta.
- ``probability`` -> ``_dispatch_probability``: direct distributional
                                                 lookup in Theta; not
                                                 gated on DAG membership.

``dispatch_all`` also runs graph-level semantic checks
(``probability_parents``, ``query_atoms_in_V``) up-front and builds
Theta once via ``theta_builder``, sharing the ground statement tuple.

Every in-language query surfaces a result; no silent drops.
"""
from __future__ import annotations

import networkx as nx

from ..input.semantic_validator import validate_against_graph, validate_formula
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
    theta_builder,
)
from .numeric_estimator import InsufficientTheta, ProbabilityKey, Theta
from .theta_builder import (
    build_observation_source_index,
    build_probability_source_index,
)


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


def _dispatch_effect(
    stmt: QueryStatement, graph: nx.DiGraph, theta: Theta
) -> QueryResult:
    q: EffectQuery = stmt.query  # type: ignore[assignment]
    x = q.intervention.atom
    y_atom = q.target.atom
    observed_atoms = tuple(g.atom for g in q.given)

    missing_atoms = [
        a for a in (x, y_atom, *observed_atoms) if a not in graph
    ]
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
        graph, x, y_atom, given=observed_atoms
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
    # q.target and q.given already carry concrete literal values,
    # so the formula is numerically resolvable once Theta has the
    # referenced conditionals.
    formula = formula_builder.backdoor_formula(
        target=q.target,
        intervention=ValuedAtom(atom=x, value=q.intervention.value),
        adjustment_set=tuple(topo),
        observed=q.given,
    )
    validate_formula(formula)
    return _try_numeric(stmt, formula, theta, QueryKind.EFFECT)


def _dispatch_probability(
    stmt: QueryStatement, graph: nx.DiGraph, theta: Theta
) -> QueryResult:
    """Probability queries are purely distributional lookups.

    Unlike cause / assoc / identify / effect, a probability query does
    NOT require its target / given atoms to appear in the causal DAG.
    A program consisting only of probability statements (no cause
    edges) should still answer ``probability(atom=value)`` — Theta is
    the authority. If the exact conditional is missing from Theta, the
    evaluator surfaces a structured missing-parameter report, and the
    caller can supply the entry without first declaring a spurious
    cause edge.
    """
    q: ProbabilityQuery = stmt.query  # type: ignore[assignment]
    formula = formula_builder._conditional(  # type: ignore[attr-defined]
        q.target,
        q.given,
    )
    return _try_numeric(stmt, formula, theta, QueryKind.PROBABILITY)


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


def _slot_confidence(sources) -> float | None:
    """RFC §3.1 / §3.2: min of non-None confidences across a slot's
    source statements; None if all sources lack annotation."""
    confs = [
        s.annotations.confidence
        for s in sources
        if s.annotations is not None and s.annotations.confidence is not None
    ]
    if not confs:
        return None
    return min(confs)


def _gather_input_confidences(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    theta: Theta | None = None,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
) -> tuple[float, ...]:
    """Collect confidences per RFC §3.3.

    - Structural queries (cause / assoc / identify) contribute nothing.
    - Effect / probability queries enumerate every distinct
      ProbabilityKey looked up by the formula, pick its slot_conf via
      the prob_index, then fold in observation slots from q.given per
      the obs_index.
    - Intervention atoms never contribute (do() cuts incoming edges).
    - Missing Theta / indices -> return () rather than raising; this
      keeps the slice independent of scheduler call-order invariants.
    """
    if result.query_kind not in (QueryKind.EFFECT, QueryKind.PROBABILITY):
        return ()
    if result.formula is None:
        return ()
    if theta is None or prob_index is None or obs_index is None:
        return ()

    inputs: list[float] = []

    # §3.1 probability slots: dedupe by key, slot-min across sources.
    seen_keys: set = set()
    for key in numeric_estimator.enumerate_keys(result.formula, theta):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        c = _slot_confidence(prob_index.get(key, ()))
        if c is not None:
            inputs.append(c)

    # §3.2 observation slots: only for (atom, value) pairs matching an
    # entry in q.given. Intervention atoms intentionally skipped.
    q = stmt.query
    given = getattr(q, "given", ())
    for va in given:
        atom = getattr(va, "atom", None)
        value = getattr(va, "value", None)
        if atom is None or value is None:
            continue
        c = _slot_confidence(obs_index.get((atom, value), ()))
        if c is not None:
            inputs.append(c)

    return tuple(inputs)


def _attach_confidence(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    theta: Theta | None = None,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
) -> QueryResult:
    """Route every result through ``confidence_calc.composite``.

    v0.2 composite semantics: min of non-None slot confidences,
    None if no slots contribute. Collection rules are defined in
    ``confidence_rfc_v0_2.md`` §3 and implemented by
    ``_gather_input_confidences``.
    """
    from dataclasses import replace

    inputs = _gather_input_confidences(
        program, stmt, result,
        theta=theta, prob_index=prob_index, obs_index=obs_index,
    )
    computed = confidence_calc.composite(*inputs)
    if computed is None and result.confidence is None:
        return result  # avoid pointless dataclass churn
    return replace(result, confidence=computed)


def dispatch(
    program: Program,
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta | None = None,
    *,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
) -> QueryResult:
    """Route a query to its solver(s) and assemble a QueryResult.

    If any of ``theta`` / ``prob_index`` / ``obs_index`` is omitted,
    the missing ones are built on demand from the program. For batch
    dispatch prefer ``dispatch_all`` which builds everything once and
    reuses it.
    """
    if theta is None or prob_index is None or obs_index is None:
        from .instantiation import instantiate as _inst
        ground = _inst(program)
        if theta is None:
            theta = theta_builder.build_theta(ground)
        if prob_index is None:
            prob_index = build_probability_source_index(ground)
        if obs_index is None:
            obs_index = build_observation_source_index(ground)

    q = stmt.query
    if isinstance(q, CauseQuery):
        result = _dispatch_cause(stmt, graph)
    elif isinstance(q, AssocQuery):
        result = _dispatch_assoc(stmt, graph)
    elif isinstance(q, IdentifyQuery):
        result = _dispatch_identify(stmt, graph)
    elif isinstance(q, EffectQuery):
        result = _dispatch_effect(stmt, graph, theta)
    elif isinstance(q, ProbabilityQuery):
        result = _dispatch_probability(stmt, graph, theta)
    else:
        # Truly unknown type: fail loudly. The schema layer should
        # have already rejected it; reaching here is a programmer bug.
        raise AssertionError(f"unknown query type {type(q).__name__}")
    result = _attach_investigation(result)
    result = _attach_confidence(
        program, stmt, result,
        theta=theta, prob_index=prob_index, obs_index=obs_index,
    )
    return result


def dispatch_all(program: Program, graph: nx.DiGraph) -> tuple[QueryResult, ...]:
    """Run every QueryStatement in the program against a single shared
    graph projection.

    Graph-level semantic checks run once here. Theta and the two
    source indices for confidence collection are built from the same
    ground statement tuple (one instantiation pass), then shared
    across every dispatched query.
    """
    from .instantiation import instantiate

    ground = instantiate(program)
    validate_against_graph(ground, graph)
    theta = theta_builder.build_theta(ground)
    prob_index = build_probability_source_index(ground)
    obs_index = build_observation_source_index(ground)

    return tuple(
        dispatch(
            program, stmt, graph, theta,
            prob_index=prob_index, obs_index=obs_index,
        )
        for stmt in program.statements
        if isinstance(stmt, QueryStatement)
    )
