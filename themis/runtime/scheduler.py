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
    DerivationStep,
    EffectQuery,
    IdentifyQuery,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
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
    StepRef,
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
from .numeric_estimator import (
    InsufficientTheta,
    ProbabilityKey,
    Theta,
    format_probability_key,
)
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
    result = StructuralResult(value=exists, supporting_paths=supporting)
    derivation: tuple[DerivationStep, ...] = ()
    if (
        q.from_atom in graph
        and q.to_atom in graph
        and q.from_atom != q.to_atom
    ):
        if exists:
            derivation = (
                DerivationStep(
                    rule="cause_via_directed_path",
                    inputs={
                        "graph": graph,
                        "src": q.from_atom,
                        "dst": q.to_atom,
                        "paths": paths,
                    },
                    output=result,
                    step_id="s1",
                ),
            )
        else:
            derivation = (
                DerivationStep(
                    rule="no_directed_path",
                    inputs={
                        "graph": graph,
                        "src": q.from_atom,
                        "dst": q.to_atom,
                    },
                    output=result,
                    step_id="s1",
                ),
            )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.CAUSE,
        query_id=stmt.id,
        structural_result=result,
        derivation=derivation,
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

    forbidden_given = frozenset(nx.descendants(graph, x)) | {x, y}
    invalid_given = tuple(atom for atom in q.given if atom in forbidden_given)
    if invalid_given:
        labels = ", ".join(_atom_to_str(atom) for atom in invalid_given)
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.IDENTIFY,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="query:identify_given",
                    priority=Priority.HIGH,
                    reason=(
                        "identify.given violates backdoor pre-conditions "
                        f"(contains X, Y, or a descendant of X): {labels}"
                    ),
                ),
            ),
        )

    adjustment_sets = structural_solver.minimal_adjustment_sets(
        graph, x, y, given=q.given
    )

    if not adjustment_sets:
        # Back-door unavailable — try the front-door criterion
        # (A6 fragment). Only fires when q.given is empty, since the
        # front-door formula shape does not currently extend to a
        # conditioning observed set.
        if not q.given:
            front = structural_solver.front_door_sets(graph, x, y)
            if front:
                return _build_identify_via_frontdoor(stmt, graph, q, front)

        # No valid adjustment at all. Report unidentifiable.
        result = StructuralResult(value=False)
        return QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.IDENTIFY,
            query_id=stmt.id,
            structural_result=result,
            derivation=(
                DerivationStep(
                    rule="unidentifiable_via_backdoor",
                    inputs={
                        "graph": graph,
                        "x": x,
                        "y": y,
                        "given": frozenset(q.given),
                    },
                    output=result,
                    step_id="s1",
                ),
            ),
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

    structural_result = StructuralResult(value=True)
    derivation = _build_identify_derivation(
        graph=graph,
        x=x,
        y=y,
        z=tuple(topo),
        given=q.given,
        target_va=target_va,
        intervention_va=intervention_va,
        observed_vas=observed_vas,
        formula=formula,
        structural_result=structural_result,
    )

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=structural_result,
        formula=formula,
        derivation=derivation,
    )


def _build_frontdoor_derivation(
    *,
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    target_va: ValuedAtom,
    intervention_va: ValuedAtom,
    formula,
    structural_result: StructuralResult,
) -> tuple[DerivationStep, ...]:
    """Derivation witness for an identification obtained via the
    front-door criterion. Mirrors ``_build_identify_derivation`` but
    cites ``front_door_criterion``, ``front_door_adjustment_formula``,
    and ``identify_via_front_door`` as the A6 rule family.
    """
    return (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="front_door_criterion",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "z": frozenset(z),
            },
            output=True,
            step_id="s2",
        ),
        DerivationStep(
            rule="front_door_adjustment_formula",
            inputs={
                "target": target_va,
                "intervention": intervention_va,
                "z": z,
            },
            output=formula,
            step_id="s3",
        ),
        DerivationStep(
            rule="identify_via_front_door",
            inputs={
                "criterion": StepRef(step_id="s2"),
                "formula": StepRef(step_id="s3"),
            },
            output=structural_result,
            step_id="s4",
        ),
    )


def _build_identify_via_frontdoor(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    front_sets: tuple[frozenset[Atom], ...],
) -> QueryResult:
    """Wrap the front-door identification path into a full QueryResult
    — chooses the smallest mediator set, builds the formula + the
    derivation, and short-circuits the normal backdoor flow."""
    chosen = min(front_sets, key=len)
    topo = [n for n in nx.topological_sort(graph) if n in chosen]

    x = q.intervention.atom
    y = q.target
    target_va = ValuedAtom(atom=y, value=None)
    intervention_va = ValuedAtom(atom=x, value=q.intervention.value)

    formula = formula_builder.front_door_formula(
        target=target_va,
        intervention=intervention_va,
        mediators=tuple(topo),
    )
    validate_formula(formula)

    structural_result = StructuralResult(value=True)
    derivation = _build_frontdoor_derivation(
        graph=graph,
        x=x, y=y, z=tuple(topo),
        target_va=target_va,
        intervention_va=intervention_va,
        formula=formula,
        structural_result=structural_result,
    )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=structural_result,
        formula=formula,
        derivation=derivation,
    )


def _build_effect_frontdoor_structural_prefix(
    *,
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    target_va: ValuedAtom,
    intervention_va: ValuedAtom,
    formula,
) -> tuple[DerivationStep, ...]:
    """Front-door counterpart of ``_build_effect_structural_prefix`` —
    same four rules as the identify derivation, used as the prefix for
    a numeric effect derivation that evaluates the front-door formula.
    """
    return _build_frontdoor_derivation(
        graph=graph,
        x=x, y=y, z=z,
        target_va=target_va,
        intervention_va=intervention_va,
        formula=formula,
        structural_result=StructuralResult(value=True),
    )


def _build_identify_derivation(
    *,
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    given: tuple[Atom, ...],
    target_va: ValuedAtom,
    intervention_va: ValuedAtom,
    observed_vas: tuple[ValuedAtom, ...],
    formula,
    structural_result: StructuralResult,
) -> tuple[DerivationStep, ...]:
    """Produce the derivation that witnesses a successful backdoor
    identification. The verifier re-runs each cited rule independently.
    """
    given_set = frozenset(given)
    return (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "z": frozenset(z),
                "given": given_set,
            },
            output=True,
            step_id="s2",
        ),
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={
                "target": target_va,
                "intervention": intervention_va,
                "z": z,
                "given": observed_vas,
            },
            output=formula,
            step_id="s3",
        ),
        DerivationStep(
            rule="identify_via_backdoor",
            inputs={
                "criterion": StepRef(step_id="s2"),
                "formula": StepRef(step_id="s3"),
            },
            output=structural_result,
            step_id="s4",
        ),
    )


def _dispatch_assoc(stmt: QueryStatement, graph: nx.DiGraph) -> QueryResult:
    q: AssocQuery = stmt.query  # type: ignore[assignment]
    connected = structural_solver.is_d_connected(graph, q.left, q.right, q.given)
    paths: tuple[tuple[Atom, ...], ...] = ()
    if connected:
        paths = structural_solver.open_paths(graph, q.left, q.right, q.given)
    supporting = tuple(tuple(_atom_to_str(a) for a in p) for p in paths)
    result = StructuralResult(value=connected, supporting_paths=supporting)
    derivation: tuple[DerivationStep, ...] = ()
    if q.left in graph and q.right in graph and q.left != q.right:
        if connected:
            derivation = (
                DerivationStep(
                    rule="d_connected_via_open_path",
                    inputs={
                        "graph": graph,
                        "x": q.left,
                        "y": q.right,
                        "conditioning": frozenset(q.given),
                        "paths": paths,
                    },
                    output=result,
                    step_id="s1",
                ),
            )
        else:
            derivation = (
                DerivationStep(
                    rule="d_separated",
                    inputs={
                        "graph": graph,
                        "x": q.left,
                        "y": q.right,
                        "conditioning": frozenset(q.given),
                    },
                    output=result,
                    step_id="s1",
                ),
            )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.ASSOC,
        query_id=stmt.id,
        structural_result=result,
        derivation=derivation,
    )


def _missing_parameter_from_key(key: ProbabilityKey | None, reason: str) -> MissingItem:
    """Build a MissingItem that points at the exact conditional
    probability the evaluator could not resolve."""
    if key is None:
        name = "numeric:unresolved_query_bound"
    else:
        name = f"parameter:{format_probability_key(key)}"
    return MissingItem(
        kind=MissingKind.PARAMETER,
        name=name,
        priority=Priority.HIGH,
        reason=reason,
    )


def _atom_to_json(atom: Atom) -> dict:
    """Render an Atom as the same JSON shape the kernel_ast schema uses
    for ``atom`` — so a skeleton is paste-ready."""
    return {
        "predicate": atom.predicate,
        "args": [
            {"type": "const", "name": t.name}
            for t in atom.args
        ],
    }


def _skeleton_for_parameter(key: ProbabilityKey) -> dict:
    """Build a paste-ready probabilityStatement dict for a missing
    CPT entry. Caller fills ``value`` and optional annotations."""
    # Sort given by predicate name so the skeleton is deterministic
    # regardless of frozenset iteration order.
    given_sorted = sorted(
        key.given, key=lambda pair: (pair[0].predicate, str(pair[1]))
    )
    return {
        "kind": "probability",
        "target": {
            "atom": _atom_to_json(key.target_atom),
            "value": key.target_value,
        },
        "given": [
            {"atom": _atom_to_json(a), "value": v}
            for a, v in given_sorted
        ],
        "value": None,
        "annotations": {"source": "TODO"},
    }


def _try_numeric(
    stmt: QueryStatement,
    formula,
    theta: Theta,
    kind: QueryKind,
    *,
    structural_prefix: tuple[DerivationStep, ...] = (),
    evaluation_step_id: str = "s_eval",
) -> QueryResult:
    """Evaluate a formula with the current Theta; on InsufficientTheta
    surface a structured needs_investigation naming the missing
    parameter AND attach a paste-ready skeleton for that parameter via
    ``investigation_pusher``.

    When the evaluation succeeds, build a V1 derivation:

        structural_prefix   (caller-supplied, empty for probability)
        ++ formula_evaluation(formula, theta) -> value
        ++ numeric_result(evaluation=StepRef(eval_step)) -> NumericResult

    ``structural_prefix`` is empty for probability queries (no backdoor
    identification needed) and is the full R1..R5 chain for effect
    queries (proving the formula is what identification demands).
    """
    try:
        value = numeric_estimator.estimate_formula(formula, theta)
    except InsufficientTheta as exc:
        missing = _missing_parameter_from_key(exc.missing_key, exc.reason)
        skeletons: dict = {}
        if exc.missing_key is not None:
            skeletons[missing.name] = _skeleton_for_parameter(exc.missing_key)
        requests = investigation_pusher.push(
            (missing,), skeletons=skeletons
        )
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=kind,
            query_id=stmt.id,
            formula=formula,
            missing_information=(missing,),
            investigation_requests=requests,
        )

    numeric_result = NumericResult(value=value)
    derivation = structural_prefix + (
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=value,
            step_id=evaluation_step_id,
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef(step_id=evaluation_step_id)},
            output=numeric_result,
            step_id="s_final",
        ),
    )
    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=kind,
        query_id=stmt.id,
        formula=formula,
        numeric_result=numeric_result,
        derivation=derivation,
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
        # A6 fragment: try front-door when back-door is unavailable.
        # Only fires when observed (given) is empty — multi-mediator
        # + conditioning isn't supported in front_door_formula yet.
        if not observed_atoms:
            front = structural_solver.front_door_sets(graph, x, y_atom)
            if front:
                chosen = min(front, key=len)
                topo = [n for n in nx.topological_sort(graph) if n in chosen]
                intervention_va = ValuedAtom(
                    atom=x, value=q.intervention.value
                )
                formula = formula_builder.front_door_formula(
                    target=q.target,
                    intervention=intervention_va,
                    mediators=tuple(topo),
                )
                validate_formula(formula)
                structural_prefix = _build_effect_frontdoor_structural_prefix(
                    graph=graph,
                    x=x, y=y_atom, z=tuple(topo),
                    target_va=q.target,
                    intervention_va=intervention_va,
                    formula=formula,
                )
                return _try_numeric(
                    stmt, formula, theta, QueryKind.EFFECT,
                    structural_prefix=structural_prefix,
                )

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
                    reason="no valid back-door or front-door adjustment exists",
                ),
            ),
        )

    chosen = min(adjustment_sets, key=len)
    topo = [n for n in nx.topological_sort(graph) if n in chosen]
    # q.target and q.given already carry concrete literal values,
    # so the formula is numerically resolvable once Theta has the
    # referenced conditionals.
    intervention_va = ValuedAtom(atom=x, value=q.intervention.value)
    formula = formula_builder.backdoor_formula(
        target=q.target,
        intervention=intervention_va,
        adjustment_set=tuple(topo),
        observed=q.given,
    )
    validate_formula(formula)
    structural_prefix = _build_effect_structural_prefix(
        graph=graph,
        x=x, y=y_atom, z=tuple(topo),
        observed_atoms=observed_atoms,
        target_va=q.target,
        intervention_va=intervention_va,
        observed_vas=q.given,
        formula=formula,
    )
    return _try_numeric(
        stmt, formula, theta, QueryKind.EFFECT,
        structural_prefix=structural_prefix,
    )


def _build_effect_structural_prefix(
    *,
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    observed_atoms: tuple[Atom, ...],
    target_va: ValuedAtom,
    intervention_va: ValuedAtom,
    observed_vas: tuple[ValuedAtom, ...],
    formula,
) -> tuple[DerivationStep, ...]:
    """Build R1..R5 as the structural prefix of an effect derivation.

    Parallels ``_build_identify_derivation`` but uses effect-query
    atoms (y has a concrete target value inside ValuedAtom) and the
    observed context W comes from ``q.given``.
    """
    given_set = frozenset(observed_atoms)
    return (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "z": frozenset(z),
                "given": given_set,
            },
            output=True,
            step_id="s2",
        ),
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={
                "target": target_va,
                "intervention": intervention_va,
                "z": z,
                "given": observed_vas,
            },
            output=formula,
            step_id="s3",
        ),
        DerivationStep(
            rule="identify_via_backdoor",
            inputs={
                "criterion": StepRef(step_id="s2"),
                "formula": StepRef(step_id="s3"),
            },
            output=StructuralResult(value=True),
            step_id="s4",
        ),
    )


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


def _attach_framing(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
) -> QueryResult:
    """Slice A0 + F1: attach advisory framing_notes for predicates the
    query references, and slice F1 also surfaces each gap as a
    DEFINE_VARIABLE investigation_request carrying a ready-to-fill
    variable_patch skeleton. Status / numeric value / confidence are
    unchanged — framing stays advisory, the investigation is just the
    actionable projection of the same gap."""
    from dataclasses import replace

    from . import framing_check

    notes = framing_check.check_framing(program, stmt)
    if not notes:
        return result

    items = tuple(
        InvestigationItem(
            target=note.predicate,
            reason=(
                f"variable '{note.predicate}' is declared but missing "
                f"{len(note.missing)} framing field"
                f"{'s' if len(note.missing) != 1 else ''}: "
                f"{', '.join(note.missing)}"
            ),
            skeleton=framing_check.build_define_variable_skeleton(
                program, note.predicate, note.missing,
            ),
        )
        for note in notes
    )
    target = (
        items[0].target if len(items) == 1 else f"define_variable:{len(items)}_items"
    )
    framing_request = InvestigationRequest(
        action=InvestigationAction.DEFINE_VARIABLE,
        target=target,
        priority=Priority.MEDIUM,
        note=None,
        group="framing",
        items=items,
    )
    merged_requests = result.investigation_requests + (framing_request,)
    return replace(
        result, framing_notes=notes, investigation_requests=merged_requests,
    )


def _attach_investigation(result: QueryResult) -> QueryResult:
    """For needs_investigation results with missing_information but no
    investigation_requests yet, populate the requests from the missing
    items.

    Slice #36: MissingKind.FRAMING items are declarative — the
    actionable surface for framing gaps is the F1 DEFINE_VARIABLE
    channel attached by ``_attach_framing``. Skip them here so
    investigation_pusher doesn't emit a duplicate empty-skeleton
    request."""
    if result.status != ResultStatus.NEEDS_INVESTIGATION:
        return result
    if result.investigation_requests:
        return result
    actionable = tuple(
        m for m in result.missing_information
        if m.kind is not MissingKind.FRAMING
    )
    if not actionable:
        return result
    from dataclasses import replace

    return replace(
        result,
        investigation_requests=investigation_pusher.push(actionable),
    )


def _check_strict_framing(
    program: Program,
    stmt: QueryStatement,
) -> tuple[MissingItem, ...]:
    """Slice #36: strict framing gate.

    If ``program.options.strict_framing`` is True, return one
    MissingItem per predicate the query references that still has
    A0 framing gaps. Empty tuple means the gate is either disabled
    or the query is fully framed (numeric evaluation proceeds as
    normal in either case)."""
    if not program.options or not program.options.get("strict_framing"):
        return ()
    from . import framing_check
    notes = framing_check.check_framing(program, stmt)
    if not notes:
        return ()
    return tuple(
        MissingItem(
            kind=MissingKind.FRAMING,
            name=f"framing:{note.predicate}",
            priority=Priority.HIGH,
            reason=(
                f"strict_framing: predicate '{note.predicate}' has "
                f"{len(note.missing)} unfilled framing field"
                f"{'s' if len(note.missing) != 1 else ''}: "
                f"{', '.join(note.missing)}"
            ),
        )
        for note in notes
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
        strict_items = _check_strict_framing(program, stmt)
        if strict_items:
            result = QueryResult(
                status=ResultStatus.NEEDS_INVESTIGATION,
                query_kind=QueryKind.EFFECT,
                query_id=stmt.id,
                missing_information=strict_items,
            )
        else:
            result = _dispatch_effect(stmt, graph, theta)
    elif isinstance(q, ProbabilityQuery):
        strict_items = _check_strict_framing(program, stmt)
        if strict_items:
            result = QueryResult(
                status=ResultStatus.NEEDS_INVESTIGATION,
                query_kind=QueryKind.PROBABILITY,
                query_id=stmt.id,
                missing_information=strict_items,
            )
        else:
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
    result = _attach_framing(program, stmt, result)
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
