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

from itertools import product

import networkx as nx

from ..input.semantic_validator import validate_against_graph, validate_formula
from ..types import (
    AssocQuery,
    Atom,
    CauseQuery,
    ConfidenceSource,
    CounterfactualQuery,
    DerivationStep,
    EffectQuery,
    IdentifyQuery,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    MissingItem,
    MissingKind,
    NumericInterval,
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
    counterfactual,
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
    CounterfactualQuery: QueryKind.COUNTERFACTUAL,
}


def _atom_to_str(atom: Atom) -> str:
    args = ",".join(a.name for a in atom.args)
    base = f"{atom.predicate}({args})"
    if atom.time_index is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def _sort_supporting_paths(
    paths: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    """Sort structural-result supporting_paths deterministically.

    The cause and assoc dispatchers call different solvers
    (``directed_paths`` vs ``open_paths``) which surface paths in
    traversal-dependent order — same graph + same source/target can
    yield different orderings depending on the query kind. Sorting by
    (length, lexicographic) puts the most direct path first regardless
    of solver, so renderers see the same shape across query kinds.
    """
    return tuple(sorted(paths, key=lambda p: (len(p), p)))


def _structural_mediation_assumptions(
    strategy: str,
) -> tuple[str, ...]:
    """Assumptions a structural mediation identifiability claim rests on.

    Mirrors ``themis/estimation/mediation.py:_assumptions_for`` but at
    the identification (graph-only) layer — outcome-model assumptions
    don't apply yet (no model has been fit). The IDs reuse the renderer
    glossary so the response layer translates them via the same table
    used for backdoor / front-door numeric assumptions.
    """
    if strategy == "nde_nie":
        return (
            "pearl_2001_four_conditions_hold_on_the_graph",
            "sequential_ignorability_treatment_and_mediator",
            "no_intermediate_confounder_affected_by_treatment",
            "consistency_of_potential_outcomes",
        )
    if strategy == "cde":
        return (
            "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment",
            "consistency_of_potential_outcomes",
        )
    return ()


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
    supporting = _sort_supporting_paths(
        tuple(tuple(_atom_to_str(a) for a in p) for p in paths)
    )
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


def _dispatch_identify(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
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

    # Phase 2.latent S3.b.1: ADMG programs first try the ADMG-aware
    # backdoor (minimal_adjustment_sets with bidirected); if that
    # returns nothing, S3.a's ADMG-aware front-door is the next
    # fallback. Out-of-reach ADMG cases become needs_investigation
    # pointing at S3.b.2 (c-factor) for follow-up.
    if bidirected:
        admg_adjustment_sets = structural_solver.minimal_adjustment_sets(
            graph, x, y, given=q.given, bidirected=bidirected
        )
        if admg_adjustment_sets:
            # Adjustment set exists in ADMG — reuse the backdoor
            # derivation builder below (same formula shape).
            adjustment_sets = admg_adjustment_sets
        else:
            if not q.given:
                front = structural_solver.front_door_sets(
                    graph, x, y, bidirected=bidirected
                )
                if front:
                    return _build_identify_via_frontdoor(stmt, graph, q, front)
                # Phase 6.iv: IV fallback when ADMG backdoor + front-door
                # both fail. This is the classic IV scenario — X ↔ Y
                # bidirected (unobserved confounder), and some Z → X with
                # Z independent of Y in G[\bar{X}].
                iv = structural_solver.iv_sets(
                    graph, x, y, bidirected=bidirected
                )
                if iv:
                    return _build_identify_via_iv(
                        stmt, graph, q, iv, bidirected=bidirected
                    )
                # Tian / Shpitser ID — last resort before
                # needs_investigation. Handles c-factor-identifiable
                # ADMGs that backdoor/front-door/IV miss. Returns
                # None when the case requires Shpitser Line 7
                # symbolic substitution (not implemented in this
                # slice); scheduler then falls through to
                # needs_investigation.
                from . import c_factor
                tian = c_factor.identify_via_tian(
                    graph, bidirected, x, y, q.intervention.value,
                )
                if tian.identifiable:
                    return _build_identify_via_tian(stmt, graph, q, tian)
                if tian.hedge is not None:
                    # Shpitser Line 5 produced a hedge — definitive
                    # unidentifiability witness. Return as
                    # structurally_solved with value=False.
                    return _build_identify_unidentifiable_via_tian(
                        stmt, graph, q, tian,
                    )
            return QueryResult(
                status=ResultStatus.NEEDS_INVESTIGATION,
                query_kind=QueryKind.IDENTIFY,
                query_id=stmt.id,
                missing_information=(
                    MissingItem(
                        kind=MissingKind.STRUCTURE,
                        name="query:identify_admg",
                        priority=Priority.HIGH,
                        reason=(
                            "Phase 2.latent S3.b.1: this ADMG identify "
                            "query is reachable neither by ADMG-aware "
                            "backdoor, front-door, nor IV. Tian Lines "
                            "1-6 also did not apply; the Shpitser Line "
                            "7 case (recursive symbolic substitution) "
                            "is not implemented in this slice."
                        ),
                    ),
                ),
            )
    else:
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
            # Phase 6.iv: IV fallback. Fires when backdoor + front-door
            # both unavailable and some Z satisfies Pearl's IV criterion.
            iv = structural_solver.iv_sets(graph, x, y)
            if iv:
                return _build_identify_via_iv(stmt, graph, q, iv)

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


def _build_identify_via_tian(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    tian,
) -> QueryResult:
    """Wrap a Tian / Shpitser ID success into a full QueryResult.

    Two-step derivation:
      s1: tian_c_decomposition — c-component partitions visited by the
          recursion, frozen as the witness trail.
      s2: identify_via_tian    — consumes s1 + the constructed formula
          and concludes identifiable.

    The verifier replays the c-component decomposition independently
    and checks the formula's c-factor product structure matches the
    declared c-component partition.
    """
    x = q.intervention.atom
    y = q.target
    structural_result = StructuralResult(value=True)
    validate_formula(tian.formula)

    derivation = (
        DerivationStep(
            rule="tian_c_decomposition",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="identify_via_tian",
            inputs={
                "decomposition": StepRef(step_id="s1"),
                "formula": tian.formula,
            },
            output=structural_result,
            step_id="s2",
        ),
    )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=structural_result,
        formula=tian.formula,
        derivation=derivation,
    )


def _build_identify_unidentifiable_via_tian(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    tian,
) -> QueryResult:
    """Wrap a Shpitser-Line-5 hedge witness into structurally_solved
    with structural_result.value = False. The hedge c-component is
    recorded as an explicit witness for the verifier to replay."""
    x = q.intervention.atom
    y = q.target
    structural_result = StructuralResult(value=False)

    derivation = (
        DerivationStep(
            rule="tian_c_decomposition",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="tian_hedge_witness",
            inputs={
                "decomposition": StepRef(step_id="s1"),
            },
            output=structural_result,
            step_id="s2",
        ),
    )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
    )


def _build_identify_via_iv(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    iv_candidates: tuple[structural_solver.IVCandidate, ...],
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Wrap IV identification into a full QueryResult.

    Unlike backdoor / front-door, IV identification at the structural
    layer only establishes *existence* of an identification strategy —
    the specific formula (Wald / 2SLS / LATE) requires an additional
    assumption (monotonicity or linearity) that lives in the estimation
    layer (Phase 7). So we:

    - set structural_result.value = True (identifiable)
    - leave formula = None (no closed form without estimation-layer assumption)
    - record the chosen instrument + conditioning in extensions
    - emit a derivation step with rule ``identify_via_iv``

    See PHASE_6_IV_CHARTER.md §3.4 for the identification-vs-estimation
    boundary.
    """
    chosen = iv_candidates[0]  # already sorted by iv_sets (|W| asc)

    x = q.intervention.atom
    y = q.target

    structural_result = StructuralResult(value=True)

    # Two-step derivation matching front-door pattern:
    #   s1: iv_criterion_check — proves (Z, W) satisfies IV1/IV2/IV3
    #   s2: identify_via_iv    — consumes s1 and concludes identifiable
    #
    # bidirected not included in derivation inputs because the existing
    # serializer treats frozenset as atom_set (can't nest); the verifier
    # rule reconstructs it from ctx.bidirected.
    derivation = (
        DerivationStep(
            rule="iv_criterion_check",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "instrument": chosen.instrument,
                "conditioning": chosen.conditioning,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="identify_via_iv",
            inputs={
                "criterion": StepRef(step_id="s1"),
            },
            output=structural_result,
            step_id="s2",
        ),
    )

    extensions = {
        "iv_identification": {
            "strategy": "iv",
            "instrument": _atom_to_str(chosen.instrument),
            "conditioning": sorted(
                _atom_to_str(a) for a in chosen.conditioning
            ),
            "required_assumption": (
                "monotonicity (for LATE/Wald) OR linearity (for 2SLS/ATE)"
            ),
            "alternatives_count": len(iv_candidates),
        }
    }

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions=extensions,
    )


def _dispatch_mediation(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Phase 6.mediation — identification-layer dispatch for NDE/NIE/CDE.

    Invoked from ``_dispatch_effect`` when ``q.mediator`` is set. Runs
    Pearl's four-condition check for NDE/NIE and the backdoor-based
    C1/C2 check for CDE via ``structural_solver.mediation_sets``, then
    packages the result as a STRUCTURALLY_SOLVED QueryResult with
    ``extensions.mediation_decomposition``.

    No numeric formula is emitted at this layer — mediation estimation
    (via g-formula / Imai et al. sensitivity analysis) belongs to
    Phase 7. See PHASE_6_MEDIATION_CHARTER.md §3.3.
    """
    x = q.intervention.atom
    y = q.target.atom
    m = q.mediator
    assert m is not None  # guaranteed by caller

    mediation = structural_solver.mediation_sets(
        graph, x, y, m, bidirected=bidirected or None
    )

    # Decompose result for extensions and derivation rendering.
    nde_nie_info = {
        "identifiable": mediation.nde_nie.identifiable,
        "adjustment": sorted(
            _atom_to_str(a) for a in mediation.nde_nie.adjustment
        ),
        "failed_condition": mediation.nde_nie.failed_condition,
        # Structural identification of NDE/NIE rests on Pearl 2001's
        # cross-world conditions; surfacing them lets the renderer cite
        # what 'identifiable' is conditional on rather than presenting
        # it as an unconditional yes.
        "assumptions": list(
            _structural_mediation_assumptions("nde_nie")
            if mediation.nde_nie.identifiable else ()
        ),
    }
    cde_info = {
        "identifiable": mediation.cde.identifiable,
        "adjustment": sorted(
            _atom_to_str(a) for a in mediation.cde.adjustment
        ),
        "failed_condition": mediation.cde.failed_condition,
        "assumptions": list(
            _structural_mediation_assumptions("cde")
            if mediation.cde.identifiable else ()
        ),
    }

    if not mediation.mediator_valid:
        # Mediator structural prereq fails (no X→M or no M→Y path).
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="mediation:invalid_mediator",
                    priority=Priority.HIGH,
                    reason=(
                        "mediator does not lie on any directed path "
                        "X → ... → M → ... → Y; check the mediator "
                        "declaration or the graph edges"
                    ),
                ),
            ),
            extensions={
                "mediation_decomposition": {
                    "mediator": _atom_to_str(m),
                    "mediator_valid": False,
                    "nde_nie": nde_nie_info,
                    "cde": cde_info,
                }
            },
        )

    # Three-step derivation:
    #   s1: mediation_nde_nie_check — four-condition check for NDE/NIE
    #   s2: mediation_cde_check     — backdoor check for CDE
    #   s3: identify_via_mediation  — decomposition decision + strategy
    derivation = (
        DerivationStep(
            rule="mediation_nde_nie_check",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "mediator": m,
                "adjustment": mediation.nde_nie.adjustment,
            },
            output=mediation.nde_nie.identifiable,
            step_id="s1",
        ),
        DerivationStep(
            rule="mediation_cde_check",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "mediator": m,
                "adjustment": mediation.cde.adjustment,
            },
            output=mediation.cde.identifiable,
            step_id="s2",
        ),
        DerivationStep(
            rule="identify_via_mediation",
            inputs={
                "nde_nie": StepRef(step_id="s1"),
                "cde": StepRef(step_id="s2"),
            },
            output=StructuralResult(
                value=mediation.nde_nie.identifiable or mediation.cde.identifiable
            ),
            step_id="s3",
        ),
    )

    extensions = {
        "mediation_decomposition": {
            "mediator": _atom_to_str(m),
            "mediator_valid": True,
            "nde_nie": nde_nie_info,
            "cde": cde_info,
            "strategy": (
                "nde_nie" if mediation.nde_nie.identifiable
                else ("cde" if mediation.cde.identifiable else "none")
            ),
        }
    }

    structural_result = StructuralResult(
        value=mediation.nde_nie.identifiable or mediation.cde.identifiable
    )

    # Emit STRUCTURALLY_SOLVED regardless of which strategies succeed —
    # the identifiability of each is captured in extensions. Downstream
    # NL layer reads strategy + failed_condition to frame the answer.
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions=extensions,
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


def _dispatch_assoc(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    q: AssocQuery = stmt.query  # type: ignore[assignment]
    if bidirected:
        connected = structural_solver.is_m_connected(
            graph, bidirected, q.left, q.right, q.given,
        )
        result = StructuralResult(value=connected)
        derivation: tuple[DerivationStep, ...] = ()
        if q.left in graph and q.right in graph and q.left != q.right:
            derivation = (
                DerivationStep(
                    rule=(
                        "m_connection_witness"
                        if connected else "m_separation_witness"
                    ),
                    inputs={
                        "graph": graph,
                        "x": q.left,
                        "y": q.right,
                        "z": frozenset(q.given),
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

    connected = structural_solver.is_d_connected(graph, q.left, q.right, q.given)
    paths: tuple[tuple[Atom, ...], ...] = ()
    if connected:
        paths = structural_solver.open_paths(graph, q.left, q.right, q.given)
    supporting = _sort_supporting_paths(
        tuple(tuple(_atom_to_str(a) for a in p) for p in paths)
    )
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
    d = {
        "predicate": atom.predicate,
        "args": [
            {"type": "const", "name": t.name}
            for t in atom.args
        ],
    }
    if atom.time_index is not None:
        d["time_index"] = {"kind": "relative", "value": atom.time_index.value}
    return d


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


def _counterfactual_joint_xy(
    theta: Theta,
    q: CounterfactualQuery,
    graph: nx.DiGraph,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> tuple[dict[tuple[bool, bool], float] | None, tuple[MissingItem, ...], dict]:
    """Build the factual joint table P(X, Y) for the narrow S.C.5 path.

    Current widening still stays inside the same fragment:
    - X and Y themselves remain boolean
    - first prefer graph-faithful ancestral BN factorization on the
      directed ancestral subgraph of {X, Y}
    - if that is not applicable (currently: relevant bidirected edges),
      fall back to the older local chain-rule recovery

    Missing entries still surface as ordinary PARAMETER gaps so the
    existing fill-back workflow can recover the query.
    """
    x_atom = q.observed.atom
    y_atom = q.counterfactual_target.atom
    if not set(theta.domain_of(x_atom)) or not set(theta.domain_of(x_atom)) <= {False, True}:
        raise counterfactual.CounterfactualBoundsError(
            f"counterfactual solver requires boolean domain for {x_atom.predicate}"
        )
    if not set(theta.domain_of(y_atom)) or not set(theta.domain_of(y_atom)) <= {False, True}:
        raise counterfactual.CounterfactualBoundsError(
            f"counterfactual solver requires boolean domain for {y_atom.predicate}"
        )

    factorized_joint, factorized_missing, factorized_skeletons = (
        _counterfactual_joint_xy_via_ancestral_factorization(
            graph,
            theta,
            x_atom=x_atom,
            y_atom=y_atom,
            bidirected=bidirected,
        )
    )
    if factorized_joint is not None or factorized_missing:
        return factorized_joint, factorized_missing, factorized_skeletons

    missing: list[MissingItem] = []
    skeletons: dict = {}
    joint: dict[tuple[bool, bool], float] = {}
    for x_val in (False, True):
        for y_val in (False, True):
            try:
                joint[(x_val, y_val)] = _estimate_counterfactual_joint_cell(
                    theta,
                    x_atom=x_atom,
                    x_val=x_val,
                    y_atom=y_atom,
                    y_val=y_val,
                )
            except InsufficientTheta as exc:
                item = _missing_parameter_from_key(
                    exc.missing_key,
                    exc.reason,
                )
                missing.append(item)
                if exc.missing_key is not None:
                    skeletons[item.name] = _skeleton_for_parameter(exc.missing_key)
    if missing:
        deduped_missing: list[MissingItem] = []
        seen_names: set[str] = set()
        for item in missing:
            if item.name in seen_names:
                continue
            seen_names.add(item.name)
            deduped_missing.append(item)
        return None, tuple(deduped_missing), skeletons
    return joint, (), {}


def _counterfactual_joint_xy_via_ancestral_factorization(
    graph: nx.DiGraph,
    theta: Theta,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> tuple[dict[tuple[bool, bool], float] | None, tuple[MissingItem, ...], dict]:
    """Recover P(X, Y) by enumerating the directed ancestral subgraph.

    This is the first non-local widening of the landed counterfactual
    runtime: instead of only accepting handcrafted local factorizations
    such as P(X) * P(Y|X), it uses the current DAG + CPT semantics
    directly whenever the relevant observational model is an ordinary
    ancestral BN.

    We stay conservative around ADMGs: if any bidirected edge touches
    the ancestral subgraph of {X, Y}, we do *not* pretend the directed
    factorization is valid and fall back to the older local recovery
    path.
    """
    ancestral_nodes = (
        nx.ancestors(graph, x_atom)
        | nx.ancestors(graph, y_atom)
        | {x_atom, y_atom}
    )
    if not ancestral_nodes:
        return None, (), {}
    if any(pair & ancestral_nodes for pair in bidirected):
        return None, (), {}

    subgraph = graph.subgraph(ancestral_nodes).copy()
    topo = tuple(nx.topological_sort(subgraph))
    required_keys = _required_observational_probability_keys(
        subgraph,
        topo=topo,
        theta=theta,
    )
    missing_keys = tuple(
        key for key in required_keys
        if _recover_boolean_theta_value(theta, key) is None
    )
    if missing_keys:
        missing_items = tuple(
            _missing_parameter_from_key(
                key,
                f"counterfactual bounds needs {format_probability_key(key)}",
            )
            for key in missing_keys
        )
        skeletons = {
            item.name: _skeleton_for_parameter(key)
            for item, key in zip(missing_items, missing_keys)
        }
        return None, missing_items, skeletons

    joint: dict[tuple[bool, bool], float] = {
        (False, False): 0.0,
        (False, True): 0.0,
        (True, False): 0.0,
        (True, True): 0.0,
    }
    for assignment in _ancestral_assignments(topo, theta):
        prob = 1.0
        for atom in topo:
            key = _assignment_probability_key(subgraph, atom, assignment)
            value = _recover_boolean_theta_value(theta, key)
            if value is None:
                raise AssertionError(
                    "missing key survived required-key precheck in "
                    "_counterfactual_joint_xy_via_ancestral_factorization"
                )
            prob *= value
        joint[(assignment[x_atom], assignment[y_atom])] += prob
    return joint, (), {}


def _required_observational_probability_keys(
    graph: nx.DiGraph,
    *,
    topo: tuple[Atom, ...],
    theta: Theta,
) -> tuple[ProbabilityKey, ...]:
    keys: set[ProbabilityKey] = set()
    for assignment in _ancestral_assignments(topo, theta):
        for atom in topo:
            keys.add(_assignment_probability_key(graph, atom, assignment))
    return tuple(sorted(keys, key=_probability_key_sort_key))


def _ancestral_assignments(
    topo: tuple[Atom, ...],
    theta: Theta,
):
    domains = [_counterfactual_factorization_domain(theta, atom) for atom in topo]
    for values in product(*domains):
        yield dict(zip(topo, values))


def _assignment_probability_key(
    graph: nx.DiGraph,
    atom: Atom,
    assignment: dict[Atom, object],
) -> ProbabilityKey:
    return ProbabilityKey(
        target_atom=atom,
        target_value=assignment[atom],
        given=frozenset(
            (parent, assignment[parent])
            for parent in graph.predecessors(atom)
        ),
    )


def _probability_key_sort_key(key: ProbabilityKey) -> tuple:
    given = tuple(
        sorted(
            (
                (atom.predicate, tuple(arg.name for arg in atom.args), repr(value))
                for atom, value in key.given
            )
        )
    )
    return (
        key.target_atom.predicate,
        tuple(arg.name for arg in key.target_atom.args),
        repr(key.target_value),
        given,
    )


def _counterfactual_factorization_domain(
    theta: Theta,
    atom: Atom,
) -> tuple:
    domain = tuple(theta.domain_of(atom))
    if domain and set(domain) <= {False, True}:
        return (False, True)
    return domain


def _estimate_counterfactual_joint_cell(
    theta: Theta,
    *,
    x_atom: Atom,
    x_val: bool,
    y_atom: Atom,
    y_val: bool,
) -> float:
    """Estimate one P(X=x, Y=y) cell for the narrow counterfactual path.

    Local fallback only. Prefer the graph-faithful ancestral recovery
    above; if that path is not applicable, current widening still stays
    inside the same fragment:
    - prefer the original chain-rule factorization P(X) * P(Y|X)
    - if that is unavailable, fall back to P(Y) * P(X|Y)

    If both fail, surface the missing key from the canonical
    X-first attempt so the existing parameter fill-back workflow
    stays deterministic.
    """
    x_key = ProbabilityKey(
        target_atom=x_atom,
        target_value=x_val,
        given=frozenset(),
    )
    y_given_x_key = ProbabilityKey(
        target_atom=y_atom,
        target_value=y_val,
        given=frozenset({(x_atom, x_val)}),
    )
    p_x = _recover_boolean_theta_value(theta, x_key)
    p_y_given_x = _recover_boolean_theta_value(theta, y_given_x_key)
    if p_x is not None and p_y_given_x is not None:
        return p_x * p_y_given_x

    y_key = ProbabilityKey(
        target_atom=y_atom,
        target_value=y_val,
        given=frozenset(),
    )
    x_given_y_key = ProbabilityKey(
        target_atom=x_atom,
        target_value=x_val,
        given=frozenset({(y_atom, y_val)}),
    )
    p_y = _recover_boolean_theta_value(theta, y_key)
    p_x_given_y = _recover_boolean_theta_value(theta, x_given_y_key)
    if p_y is not None and p_x_given_y is not None:
        return p_y * p_x_given_y

    missing_key = x_key if p_x is None else y_given_x_key
    raise InsufficientTheta(
        missing_key,
        f"counterfactual bounds needs {format_probability_key(missing_key)}",
    )


def _recover_boolean_theta_value(
    theta: Theta,
    key: ProbabilityKey,
) -> float | None:
    """Return theta[key] or, for boolean domains, 1 - theta[complement].

    This keeps counterfactual joint recovery inside current fragment
    semantics: the program still supplies CPT-style parameters, but the
    runtime no longer requires both boolean cells to be listed
    redundantly.
    """
    value = theta.get(key)
    if value is not None:
        return float(value)
    domain = set(theta.domain_of(key.target_atom))
    if not domain or not domain <= {False, True} or not isinstance(key.target_value, bool):
        return None
    complement_key = ProbabilityKey(
        target_atom=key.target_atom,
        target_value=not key.target_value,
        given=key.given,
    )
    complement = theta.get(complement_key)
    if complement is None:
        return None
    return 1.0 - float(complement)


def _dispatch_counterfactual(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    q: CounterfactualQuery = stmt.query  # type: ignore[assignment]

    if q.assumptions is None or q.assumptions.monotonicity is None:
        assumption_gap = MissingItem(
            kind=MissingKind.ASSUMPTION,
            name="assumptions.monotonicity",
            priority=Priority.HIGH,
            reason="首版反事实 bounds 只支持显式 monotonicity 假设",
        )
        return QueryResult(
            status=ResultStatus.NEEDS_ASSUMPTION,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=(assumption_gap,),
            investigation_requests=(
                InvestigationRequest(
                    action=InvestigationAction.DEFINE_ASSUMPTION,
                    target=assumption_gap.name,
                    priority=assumption_gap.priority,
                    note=assumption_gap.reason,
                    group=MissingKind.ASSUMPTION.value,
                    items=(
                        InvestigationItem(
                            target=assumption_gap.name,
                            reason=assumption_gap.reason,
                        ),
                    ),
                ),
            ),
        )

    try:
        joint_xy, missing, skeletons = _counterfactual_joint_xy(
            theta, q, graph, bidirected=bidirected
        )
    except counterfactual.CounterfactualBoundsError as exc:
        return QueryResult(
            status=ResultStatus.OUTSIDE_LANGUAGE,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            extensions={"counterfactual_error": str(exc)},
        )
    if missing:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=missing,
            investigation_requests=investigation_pusher.push(
                missing, skeletons=skeletons
            ),
        )

    try:
        twin = counterfactual.project_twin_network(graph, bidirected, q)
        interval = counterfactual.balke_pearl_bounds_binary_monotone(
            twin, q, joint_xy
        )
    except counterfactual.CounterfactualBoundsError as exc:
        return QueryResult(
            status=ResultStatus.OUTSIDE_LANGUAGE,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            extensions={"counterfactual_error": str(exc)},
        )

    bounded_result = NumericResult(
        value=None,
        interval=NumericInterval(low=interval.low, high=interval.high),
    )
    solved_result = NumericResult(value=interval.low)
    derivation_output = solved_result if interval.low == interval.high else bounded_result
    derivation = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": graph},
            output=derivation_output,
            step_id="s1",
        ),
    )

    if interval.low == interval.high:
        return QueryResult(
            status=ResultStatus.COUNTERFACTUAL_SOLVED,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            numeric_result=solved_result,
            derivation=derivation,
        )
    return QueryResult(
        status=ResultStatus.COUNTERFACTUAL_BOUNDED,
        query_kind=QueryKind.COUNTERFACTUAL,
        query_id=stmt.id,
        numeric_result=bounded_result,
        derivation=derivation,
    )


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


def _dispatch_transport(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    selection_nodes: "tuple[Statement, ...]",
) -> QueryResult:
    """Phase 9 §T9.1.3: Bareinboim-Pearl single-source transport identification.

    Returns a structural-only QueryResult (no numeric estimation in
    §T9.1 — that's §T9.2). Identifiable case → ``structurally_solved``
    with structural_result.value=True and a `transport_identification`
    extension. Unidentifiable → ``needs_investigation`` with a
    structure-group missing item naming the failure reason.
    """
    from . import transport as _transport

    diagram, s_atoms = _transport.build_selection_diagram(selection_nodes, graph)
    result = _transport.identify_via_transport(
        diagram, s_atoms,
        treatment=q.intervention.atom,
        outcome=q.target.atom,
    )

    transport_block = {
        "kind": "transport_identification",
        "source_population": (
            selection_nodes[0].source_population if selection_nodes else None
        ),
        "target_population": q.target_population,
        "s_nodes": [
            {"id": sn.id,
             "affects": {
                 "predicate": sn.affects.predicate,
                 "args": [{"type": "const", "name": t.name} for t in sn.affects.args],
             }}
            for sn in selection_nodes
        ],
        "adjustment_set": [
            {"predicate": a.predicate,
             "args": [{"type": "const", "name": t.name} for t in a.args]}
            for a in result.adjustment_set
        ],
        "formula_repr": result.formula_repr,
    }

    if not result.identifiable:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"transport:{q.target_population}",
                    priority=Priority.HIGH,
                    reason=result.failure_reason or "transport not identifiable",
                ),
            ),
            extensions={"transport_identification": transport_block},
        )

    src_pop = selection_nodes[0].source_population if selection_nodes else ""
    derivation_steps = (
        DerivationStep(
            rule="s_admissibility_check",
            inputs={
                "treatment": q.intervention.atom,
                "outcome": q.target.atom,
                "selection_nodes_ids": ",".join(sn.id for sn in selection_nodes),
                "adjustment_set": result.adjustment_set,
            },
            output=True,
            step_id="s_t9_1",
        ),
        DerivationStep(
            rule="transport_formula",
            inputs={
                "treatment": q.intervention.atom,
                "outcome": q.target.atom,
                "adjustment_set": result.adjustment_set,
                "source_population": src_pop,
                "target_population": q.target_population,
            },
            output=result.formula_repr,
            step_id="s_t9_2",
        ),
        DerivationStep(
            rule="identify_via_transport",
            inputs={
                "criterion": StepRef(step_id="s_t9_1"),
                "formula": StepRef(step_id="s_t9_2"),
            },
            output=StructuralResult(value=True),
            step_id="s_t9_final",
        ),
    )

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=StructuralResult(value=True),
        derivation=derivation_steps,
        extensions={"transport_identification": transport_block},
    )


def _dispatch_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[Statement, ...]" = (),
) -> QueryResult:
    q: EffectQuery = stmt.query  # type: ignore[assignment]
    x = q.intervention.atom
    y_atom = q.target.atom
    observed_atoms = tuple(g.atom for g in q.given)

    missing_atoms = [
        a for a in (x, y_atom, *observed_atoms) if a not in graph
    ]
    if q.mediator is not None and q.mediator not in graph:
        missing_atoms.append(q.mediator)
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

    # Phase 9 §T9.1.3: when the query declares a target_population,
    # short-circuit into transport identification (Bareinboim 2014).
    # Returns structural identification only — no numeric estimation
    # in §T9.1 (deferred to §T9.2).
    if getattr(q, "target_population", None) is not None:
        return _dispatch_transport(stmt, graph, q, selection_nodes)

    # Phase 6.mediation: when the query declares a mediator, short-
    # circuit into mediation identification (NDE/NIE/CDE decomposition)
    # instead of computing the plain total-effect formula. Identification-
    # only at this layer; numeric decomposition lands in Phase 7.
    if q.mediator is not None:
        return _dispatch_mediation(stmt, graph, q, bidirected=bidirected)

    # Phase 2.latent S3.b.1: ADMG-aware backdoor first, front-door
    # second, c-factor pending S3.b.2.
    if bidirected:
        admg_adjustment_sets = structural_solver.minimal_adjustment_sets(
            graph, x, y_atom, given=observed_atoms, bidirected=bidirected
        )
        if admg_adjustment_sets:
            adjustment_sets = admg_adjustment_sets
            # Fall through to the shared backdoor-formula tail below.
        else:
            if not observed_atoms:
                front = structural_solver.front_door_sets(
                    graph, x, y_atom, bidirected=bidirected
                )
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
                missing_information=(
                    MissingItem(
                        kind=MissingKind.STRUCTURE,
                        name="query:effect_admg",
                        priority=Priority.HIGH,
                        reason=(
                            "Phase 2.latent S3.b.1: this ADMG effect "
                            "query is reachable neither by ADMG-aware "
                            "backdoor nor front-door. Tian c-factor "
                            "lands in S3.b.2; see "
                            "PHASE_2_LATENT_CHARTER.md §7."
                        ),
                    ),
                ),
            )
    else:
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
    actionable projection of the same gap.

    F9 scope (eval v1 / G1 finding): structural-only queries — cause,
    assoc, identify — are answered at the graph level and do not need
    numeric operationalization to produce a correct answer. Attach
    framing_notes as before (the advisory channel is still useful —
    response_rendering.md can mention them as soft context), but do
    NOT emit a DEFINE_VARIABLE investigation_request. The actionable
    channel is reserved for effect / probability queries whose
    dispatch paths actually block on framing.
    """
    from dataclasses import replace

    from . import framing_check

    notes = framing_check.check_framing(program, stmt)
    if not notes:
        return result

    # F9: structural query kinds — framing gaps do not block the answer,
    # so keep the advisory notes but skip the actionable investigation.
    # Counterfactual queries in S.C.1 also stay advisory-only: the
    # blocking issue is lack of solver support, not missing variable
    # metadata, so DEFINE_VARIABLE would be misleading here.
    if (
        isinstance(stmt.query, (CauseQuery, AssocQuery, IdentifyQuery, CounterfactualQuery))
        or result.status is ResultStatus.OUTSIDE_LANGUAGE
    ):
        return replace(result, framing_notes=notes)

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


def _slot_contributors(sources):
    """All source statements with a non-None annotations.confidence."""
    return [
        s for s in sources
        if s.annotations is not None and s.annotations.confidence is not None
    ]


def _slot_min_source(sources):
    """Return (source_statement, confidence) for the slot's weakest
    contributing source, or None if nothing contributes. Ties broken
    by input order — deterministic, matches _slot_confidence's implicit
    ordering."""
    contribs = _slot_contributors(sources)
    if not contribs:
        return None
    # min by confidence, stable on ties (first seen wins)
    best = contribs[0]
    best_c = best.annotations.confidence
    for s in contribs[1:]:
        c = s.annotations.confidence
        if c < best_c:
            best, best_c = s, c
    return best, best_c


def _gather_input_sources(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    theta: Theta | None = None,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
) -> tuple[ConfidenceSource, ...]:
    """Collect one ConfidenceSource per slot that contributed per
    RFC §3. Each record carries the slot label, the source
    annotation string, the confidence value, and a placeholder
    is_weakest=False that ``_attach_confidence`` stamps to True on
    the sources matching the composite min.

    - Effect / probability queries enumerate distinct ProbabilityKeys
      from the formula (dedupe) and observation slots from q.given.
    - Structural queries (cause / assoc / identify / counterfactual)
      enumerate load-bearing CauseStatement annotations.confidence
      values via supporting_paths or, when paths aren't echoed, the
      query-relevant DAG path walk. Without this collection a
      counterfactual whose load-bearing edge is marked low-confidence
      would surface as confidence=None and bypass the
      LOW_CONFIDENCE_INPUT_DATA gap.
    - Intervention atoms never contribute (do-cut).
    - Missing theta / indices on a numeric path return () for the
      probability/observation slots, but the structural-edge path
      still runs (it does not depend on theta).
    """
    collected: list[ConfidenceSource] = []
    seen_keys: set = set()

    # §3.3 structural-edge slots — runs for every query kind so
    # cause-edge confidences propagate even when no numeric formula
    # was built.
    collected.extend(
        _gather_structural_edge_sources(program, stmt, result),
    )

    if result.query_kind not in (QueryKind.EFFECT, QueryKind.PROBABILITY):
        return tuple(collected)
    if result.formula is None:
        return tuple(collected)
    if theta is None or prob_index is None or obs_index is None:
        return tuple(collected)

    seen_keys: set = set()

    # §3.1 probability slots
    for key in numeric_estimator.enumerate_keys(result.formula, theta):
        if key in seen_keys:
            continue
        seen_keys.add(key)
        picked = _slot_min_source(prob_index.get(key, ()))
        if picked is None:
            continue
        stmt_src, conf = picked
        source_str = (
            stmt_src.annotations.source
            if stmt_src.annotations is not None else None
        )
        collected.append(ConfidenceSource(
            slot_label=f"parameter:{format_probability_key(key)}",
            source=source_str,
            confidence=conf,
            is_weakest=False,
        ))

    # §3.2 observation slots
    q = stmt.query
    given = getattr(q, "given", ())
    for va in given:
        atom = getattr(va, "atom", None)
        value = getattr(va, "value", None)
        if atom is None or value is None:
            continue
        picked = _slot_min_source(obs_index.get((atom, value), ()))
        if picked is None:
            continue
        stmt_src, conf = picked
        source_str = (
            stmt_src.annotations.source
            if stmt_src.annotations is not None else None
        )
        atom_label = _atom_to_str(atom)
        collected.append(ConfidenceSource(
            slot_label=f"observation:{atom_label}={value}",
            source=source_str,
            confidence=conf,
            is_weakest=False,
        ))

    return tuple(collected)


def _gather_structural_edge_sources(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
) -> tuple[ConfidenceSource, ...]:
    """RFC §3.3 — collect annotations.confidence from CauseStatements
    on the structurally load-bearing path(s) of the query.

    Two complementary signals (matching the data-gap classifier):
    - ``supporting_paths`` from the structural result, when the
      dispatcher exposes them (cause / assoc).
    - For every other query kind, walk simple directed paths between
      query-relevant predicates in the program-derived DAG.

    Returns one ConfidenceSource per (frm, to) edge whose
    CauseStatement carries a non-None confidence.
    """
    from ..types import CauseStatement
    cause_conf: dict[tuple[str, str], tuple[str | None, float]] = {}
    for s in program.statements:
        if not isinstance(s, CauseStatement):
            continue
        ann = s.annotations
        if ann is None or ann.confidence is None:
            continue
        cause_conf[(s.from_atom.predicate, s.to_atom.predicate)] = (
            ann.source,
            ann.confidence,
        )
    if not cause_conf:
        return ()

    flagged: set[tuple[str, str]] = set()
    structural_result = getattr(result, "structural_result", None)
    paths = getattr(structural_result, "supporting_paths", ()) or ()
    for path in paths:
        for i in range(len(path) - 1):
            a = path[i].split("(", 1)[0]
            b = path[i + 1].split("(", 1)[0]
            if (a, b) in cause_conf:
                flagged.add((a, b))

    # DAG walk for non-cause/assoc query kinds. Reuse the data-gap
    # classifier's machinery so the two surfaces stay in lock-step.
    from ..output.data_gap_report import (
        _build_dag_with_proposals,
        _enumerate_simple_directed_paths,
        _query_relevant_predicates_for_path_walk,
    )
    _proposal_edges, adjacency = _build_dag_with_proposals(program)
    extensions = result.extensions or {}
    relevant = _query_relevant_predicates_for_path_walk(stmt, extensions)
    if relevant and adjacency:
        for src in relevant:
            for dst in relevant:
                if src == dst:
                    continue
                for path in _enumerate_simple_directed_paths(
                    adjacency, src, dst,
                ):
                    for i in range(len(path) - 1):
                        edge = (path[i], path[i + 1])
                        if edge in cause_conf:
                            flagged.add(edge)

    if not flagged:
        return ()
    return tuple(
        ConfidenceSource(
            slot_label=f"edge:{frm}->{to}",
            source=cause_conf[(frm, to)][0],
            confidence=cause_conf[(frm, to)][1],
            is_weakest=False,
        )
        for frm, to in sorted(flagged)
    )


def _gather_input_confidences(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    theta: Theta | None = None,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
) -> tuple[float, ...]:
    """Back-compat shim for the old float-only contract. Delegates to
    ``_gather_input_sources`` and strips the source metadata."""
    return tuple(
        s.confidence for s in _gather_input_sources(
            program, stmt, result,
            theta=theta, prob_index=prob_index, obs_index=obs_index,
        )
    )


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
    ``_gather_input_sources``.

    Slice #34 additionally populates ``confidence_sources`` — one
    entry per contributing slot with the source annotation, the
    confidence value, and an ``is_weakest`` flag for sources whose
    confidence equals the composite min. Consumers get a direct
    "why is it this low" audit trail without re-computing it.
    """
    from dataclasses import replace

    sources = _gather_input_sources(
        program, stmt, result,
        theta=theta, prob_index=prob_index, obs_index=obs_index,
    )
    computed = confidence_calc.composite(*(s.confidence for s in sources))
    if computed is None and result.confidence is None and not sources:
        return result  # avoid pointless dataclass churn

    if computed is not None:
        sources = tuple(
            ConfidenceSource(
                slot_label=s.slot_label,
                source=s.source,
                confidence=s.confidence,
                is_weakest=(s.confidence == computed),
            )
            for s in sources
        )

    return replace(result, confidence=computed, confidence_sources=sources)


def dispatch(
    program: Program,
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta | None = None,
    *,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
    bidirected: "frozenset[frozenset[Atom]] | None" = None,
) -> QueryResult:
    """Route a query to its solver(s) and assemble a QueryResult.

    If any of ``theta`` / ``prob_index`` / ``obs_index`` / ``bidirected``
    is omitted, the missing ones are built on demand from the program.
    For batch dispatch prefer ``dispatch_all`` which builds everything
    once and reuses it.

    ``bidirected`` is the ADMG bidirected-edge set extracted from the
    ground program (Phase 2.latent S3.a). Identify / effect dispatch
    routes through the ADMG-aware front-door when this set is non-empty;
    the directed-only backdoor path is skipped for ADMG programs.
    """
    if theta is None or prob_index is None or obs_index is None or bidirected is None:
        from .instantiation import instantiate as _inst
        ground = _inst(program)
        if theta is None:
            theta = theta_builder.build_theta(ground)
        if prob_index is None:
            prob_index = build_probability_source_index(ground)
        if obs_index is None:
            obs_index = build_observation_source_index(ground)
        if bidirected is None:
            bidirected = structural_solver.bidirected_from_ground(ground)

    q = stmt.query
    if isinstance(q, CauseQuery):
        result = _dispatch_cause(stmt, graph)
    elif isinstance(q, AssocQuery):
        result = _dispatch_assoc(stmt, graph, bidirected=bidirected)
    elif isinstance(q, IdentifyQuery):
        result = _dispatch_identify(stmt, graph, bidirected=bidirected)
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
            from ..types import SelectionNode as _SN
            sel_nodes = tuple(s for s in program.statements if isinstance(s, _SN))
            result = _dispatch_effect(
                stmt, graph, theta,
                bidirected=bidirected, selection_nodes=sel_nodes,
            )
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
    elif isinstance(q, CounterfactualQuery):
        result = _dispatch_counterfactual(
            stmt, graph, theta, bidirected=bidirected
        )
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
    result = _attach_program_ambiguities(result, program=program)
    # Bounds first so the gap classifier can surface bounds-not-point as
    # a must-disclose caveat. The report is built after bounds, then
    # reconcile rewrites alt_paths inside the now-existing report.
    result = _attach_bounds_result(program, stmt, result, bidirected=bidirected)
    result = _attach_data_gap_report(result, program=program, stmt=stmt)
    result = _reconcile_alt_paths_with_bounds(result)
    return result


def _attach_program_ambiguities(
    result: QueryResult,
    *,
    program: Program | None = None,
) -> QueryResult:
    """Echo program-level ``extensions.ambiguities`` into the result so
    LLM-declared uncertainty is visible to renderers even for kinds the
    kernel has no dedicated handler for.

    Real-test caught: when the LLM flagged ``reciprocal_causation`` /
    ``mechanism_vs_existence`` / ``mediator_choice``, the kernel
    silently swallowed them — only ``dose_response_query`` triggered a
    Phase 13 gap, so the audit trail lost the rest. Renderers couldn't
    tell whether the LLM omitted those concerns or the kernel just
    didn't surface them.

    Per-query targeting: an ambiguity dict carrying ``query_id`` only
    attaches to that result; ones without ``query_id`` attach to every
    effect-shaped result (program-wide concerns)."""
    from dataclasses import replace as _replace

    if program is None:
        return result
    ext = getattr(program, "extensions", None) or {}
    ambs = ext.get("ambiguities") or []
    if not ambs:
        return result
    qid = result.query_id
    relevant: list[dict] = []
    for a in ambs:
        if not isinstance(a, dict):
            continue
        target_qid = a.get("query_id")
        if target_qid is None or target_qid == qid:
            relevant.append(a)
    if not relevant:
        return result
    new_ext = dict(result.extensions or {})
    new_ext["ambiguities"] = relevant
    return _replace(result, extensions=new_ext)


def _attach_data_gap_report(
    result: QueryResult,
    *,
    program: Program | None = None,
    stmt: QueryStatement | None = None,
) -> QueryResult:
    """Phase 10 §10.3 + Phase 13: synthesize the structured data-gap
    report from signals already on the QueryResult, plus (Phase 13)
    program-level extensions.ambiguities for dose-response detection."""
    from dataclasses import replace as _replace

    from ..output.data_gap_report import compute_data_gap_report

    report = compute_data_gap_report(
        query_kind=result.query_kind,
        status=result.status,
        derivation=result.derivation,
        investigation_requests=result.investigation_requests,
        framing_notes=result.framing_notes,
        program=program,
        stmt=stmt,
        extensions=result.extensions,
        structural_result=result.structural_result,
        bounds_result=result.bounds_result,
        confidence=result.confidence,
    )
    if report is None and result.data_gap_report is None:
        return result
    result = _replace(result, data_gap_report=report)
    return _attach_structural_caveats(result)


# Whitelist of gap_kinds whose `description` must surface in
# ``result.explanation`` regardless of severity. These are structural
# caveats — the renderer cannot interpret the answer correctly without
# them (e.g. "this is bounds, not a point estimate", "identification
# rests on monotonicity"). The set is intentionally narrow; ordinary
# data needs (missing distributions, IV candidates) live in the gap
# report only.
_MUST_DISCLOSE_GAP_KINDS: frozenset[str] = frozenset({
    "unverified_proposal_edge_on_query_path",
    "iv_identification_assumption_required",
    "mediation_identification_assumption_required",
    "transport_identification_assumption_required",
    "llm_declared_ambiguity",
    "answer_is_bounds_not_point_estimate",
    "low_confidence_input_data",
    "front_door_identification_assumption_required",
    "counterfactual_identification_assumption_required",
    "graph_learned_from_data",
    "unmeasured_confounder_risk",
    "unattempted_layer_due_to_dispatch_conflict",
    "collider_conditioning_opens_backdoor",
})


def _attach_structural_caveats(result: QueryResult) -> QueryResult:
    """Geometric guarantee: structural caveats the renderer must surface
    are copied into ``result.explanation`` as ⚠-prefixed lines. The
    renderer prompt makes ``explanation`` a must-quote field — with this
    attachment, the disclosure path is structural, not LLM-discretionary.

    The set of caveat kinds is the ``_MUST_DISCLOSE_GAP_KINDS``
    whitelist. Adding a new caveat kind is a two-line change: add the
    kind value here and emit it from a classifier with a description
    that reads as a complete ⚠ line.
    """
    from dataclasses import replace as _replace

    report = result.data_gap_report
    if report is None or not report.gaps:
        return result
    lines = [
        f"⚠ {gap.description}"
        for gap in report.gaps
        if gap.kind.value in _MUST_DISCLOSE_GAP_KINDS
    ]
    if not lines:
        return result
    existing = result.explanation or ""
    appended = "\n".join(lines)
    new_explanation = (
        f"{existing}\n{appended}".strip() if existing else appended
    )
    return _replace(result, explanation=new_explanation)


def _attach_bounds_result(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    bidirected: "frozenset[frozenset[Atom]] | None" = None,
) -> QueryResult:
    """Phase 12 §S.12.4: when point identification failed on an effect
    query, try symbolic bounds (Manski natural always; Balke-Pearl IV
    when a binary IV candidate exists either via
    extensions.iv_identification or via lightweight graph detection).
    Pure function — no I/O.

    Prefers the tighter method (BP when applicable, else Manski).

    IV detection (Phase 12 §S.12.6 patch): the kernel's IV identification
    pass does NOT run on ADMG-unidentifiable effect queries, so
    extensions.iv_identification is empty in the most common bounds-
    triggering scenario. We do a lightweight structural check directly:
    Z is an IV candidate iff there's a cause edge Z→X and no cause edge
    Z→Y, and Z's variable declaration is bool.
    """
    from dataclasses import replace as _replace

    from ..output.bounds import (
        attempt_balke_pearl_iv,
        attempt_manski_natural,
        attempt_manski_tamer_monotonicity,
    )
    from ..types import (
        EffectQuery,
        Monotonicity,
        ResultStatus,
        VariableDeclaration,
    )

    if result.bounds_result is not None:
        return result
    if result.status != ResultStatus.NEEDS_INVESTIGATION:
        return result
    if not isinstance(stmt.query, EffectQuery):
        return result
    query = stmt.query

    target_is_bool = isinstance(query.target.value, bool)
    intervention_is_bool = isinstance(query.intervention.value, bool)
    if not intervention_is_bool:
        return result

    target_event_is_discrete = _target_event_is_discrete(program, query)
    if not target_event_is_discrete:
        return result

    bounds = None
    # 1. Try kernel-emitted IV identification first (richest).
    #    BP-IV's 8-term formula assumes Y ∈ {0,1} so it gates on bool
    #    outcome — discrete-numeric targets fall through to Manski.
    iv_ext = (result.extensions or {}).get("iv_identification")
    instrument_pred: str | None = None
    if isinstance(iv_ext, dict):
        instrument_pred = iv_ext.get("instrument")
    # 2. Fallback: lightweight structural detection
    if instrument_pred is None:
        instrument_pred = _detect_iv_candidate_structural(
            program, query,
        )
    if instrument_pred and target_is_bool:
        bounds = attempt_balke_pearl_iv(
            query,
            instrument_predicate=instrument_pred,
            outcome_is_binary=True,
            treatment_is_binary=True,
            instrument_is_binary=True,
        )

    # 3. Manski-Tamer (MTR) — tighter than Manski natural when the user
    #    asserts monotone treatment response. Triggered via
    #    program.extensions['monotonicity'] dict matching this query's
    #    target+treatment pair. Falls back to Manski natural if no MTR
    #    declaration applies.
    if bounds is None:
        mtr_direction = _detect_monotonicity_for_query(program, query)
        if mtr_direction is not None:
            bounds = attempt_manski_tamer_monotonicity(
                query,
                monotonicity=mtr_direction,
                outcome_event_is_discrete=True,
            )

    # 4. Always-available fallback (works for bool OR discrete-numeric)
    if bounds is None:
        bounds = attempt_manski_natural(
            query, outcome_event_is_discrete=True,
        )

    if bounds is None:
        return result
    return _replace(result, bounds_result=bounds)


def _detect_monotonicity_for_query(program, query):
    """Iter 119 + 131 — resolve MTR declaration for an EffectQuery.

    Iter 131 added a first-class ``query.assumptions.monotonicity``
    field; iter 119's ``program.extensions['monotonicity']`` side-
    channel is kept as a backwards-compat fallback. Resolution order:

    1. **First-class field**: ``query.assumptions.monotonicity`` —
       direct, no target/treatment matching needed (the assumption
       is on this query's own intervention → target relationship).
    2. **Extensions hack** (iter 119): walk
       ``program.extensions['monotonicity']`` (dict or list of dicts)
       and match by ``(target, treatment)`` pair to query's predicates.

    Returns the matching ``Monotonicity`` enum value, else None.
    """
    from ..types import Monotonicity

    # Iter 131: prefer first-class field.
    query_assumptions = getattr(query, "assumptions", None)
    if query_assumptions is not None:
        mono = getattr(query_assumptions, "monotonicity", None)
        if mono is not None:
            return mono

    # Iter 119 fallback: walk extensions side-channel.
    extensions = program.extensions or {}
    decls = extensions.get("monotonicity")
    if decls is None:
        return None
    if isinstance(decls, dict):
        decls = [decls]
    if not isinstance(decls, list):
        return None

    target_pred = query.target.atom.predicate
    treatment_pred = query.intervention.atom.predicate

    for decl in decls:
        if not isinstance(decl, dict):
            continue
        if decl.get("target") != target_pred:
            continue
        if decl.get("treatment") != treatment_pred:
            continue
        direction = decl.get("direction")
        try:
            return Monotonicity(direction)
        except ValueError:
            continue
    return None


def _target_event_is_discrete(program: Program, query) -> bool:
    """Check whether ``P(target.atom = target.value)`` is a non-degenerate
    discrete event — needed before invoking Manski-style bounds whose
    formula assumes a well-defined event probability.

    True iff target.value is bool, OR target.value is numeric (int/float
    not bool) AND the target predicate's variable declaration carries a
    discrete numeric ``domain`` of length ≥2 containing the value.
    """
    from ..types import EffectQuery, VariableDeclaration

    if not isinstance(query, EffectQuery):
        return False
    val = query.target.value
    if isinstance(val, bool):
        return True
    if not isinstance(val, (int, float)):
        return False  # string targets fall here — out of scope this phase

    target_pred = query.target.atom.predicate
    decl = next(
        (
            s for s in program.statements
            if isinstance(s, VariableDeclaration) and s.predicate == target_pred
        ),
        None,
    )
    if decl is None or decl.domain is None:
        return False  # no domain → unbounded continuous → degenerate
    domain = list(decl.domain)
    if len(domain) < 2:
        return False
    if not all(
        isinstance(v, (int, float)) and not isinstance(v, bool)
        for v in domain
    ):
        return False
    return val in domain


_BOUNDS_HINT_TOKENS = ("Balke-Pearl bounds", "Manski", "bounds")


def _reconcile_alt_paths_with_bounds(result: QueryResult) -> QueryResult:
    """Phase 12 §S.12.4 follow-up: align ``data_gap_report``'s static
    alternative_paths text with what the bounds attempt actually produced.

    Three cases:
    - ``bounds_result`` present → rewrite static "接受 Balke-Pearl bounds"
      lines to the concrete "已计算 bounds（method=...）— 见 bounds_result";
      prepend that line on blocking gaps that didn't already mention bounds
    - bounds attempt ran but returned None (effect query +
      needs_investigation) → strip static bounds promises rather than
      lying that BP/Manski works for non-binary outcomes
    - bounds not attempted → leave alt_paths untouched
    """
    from dataclasses import replace as _replace

    from ..types import GapSeverity, QueryKind, ResultStatus

    if result.data_gap_report is None:
        return result

    bounds_attempted = (
        result.query_kind == QueryKind.EFFECT
        and result.status == ResultStatus.NEEDS_INVESTIGATION
    )
    bounds_present = result.bounds_result is not None

    if not bounds_attempted and not bounds_present:
        return result

    def _is_bounds_hint(s: str) -> bool:
        return any(tok in s for tok in _BOUNDS_HINT_TOKENS)

    concrete = None
    if bounds_present:
        method_name = result.bounds_result.method.value
        concrete = (
            f"已计算 bounds（method={method_name}）— 见 bounds_result"
        )

    new_gaps = []
    changed = False
    for gap in result.data_gap_report.gaps:
        rewritten: list[str] = []
        gap_changed = False
        had_bounds_mention = False
        for alt in gap.alternative_paths:
            if _is_bounds_hint(alt):
                had_bounds_mention = True
                if bounds_present:
                    if concrete not in rewritten:
                        rewritten.append(concrete)
                # else: bounds attempt ran and gave None → drop the
                # misleading static promise rather than re-emit it
                gap_changed = True
            else:
                rewritten.append(alt)
        if (
            bounds_present
            and gap.severity == GapSeverity.BLOCKING
            and not had_bounds_mention
            and concrete not in rewritten
        ):
            # Prepend so actionable_next_steps (which surfaces only the
            # first alt) shows the already-computed fallback ahead of
            # heavier structural suggestions like 'do an RCT'.
            rewritten.insert(0, concrete)
            gap_changed = True
        if gap_changed:
            new_gaps.append(_replace(gap, alternative_paths=tuple(rewritten)))
            changed = True
        else:
            new_gaps.append(gap)

    if not changed:
        return result

    from ..output.data_gap_report import _make_actionable_steps

    new_steps = list(_make_actionable_steps(list(new_gaps)))
    if bounds_present:
        # Subagent real-test caught: with bounds_result attached, the
        # actionable_next_steps "或：已计算 bounds — 见 bounds_result"
        # line duplicates the pointer that's already in alt_paths AND
        # the bounds_result rendering. Drop the dup — renderer reads
        # bounds_result as its own block.
        new_steps = [s for s in new_steps if "bounds_result" not in s]
    new_report = _replace(
        result.data_gap_report,
        gaps=tuple(new_gaps),
        actionable_next_steps=tuple(new_steps),
    )
    return _replace(result, data_gap_report=new_report)


def _detect_iv_candidate_structural(
    program: Program,
    query: "EffectQuery",
) -> str | None:
    """Lightweight IV candidate detection from program edge structure.

    Returns predicate name of Z iff:
      - exists cause edge Z→X (X = intervention predicate)
      - no cause edge Z→Y (Y = target predicate)
      - Z is declared as a bool variable
    Returns None if zero or multiple candidates (don't guess on tie).
    """
    from ..types import CauseStatement, VariableDeclaration

    target_pred = query.target.atom.predicate
    intervention_pred = query.intervention.atom.predicate

    # Collect predicates with edge → intervention
    edges_to_intervention: set[str] = set()
    edges_to_target: set[str] = set()
    bool_vars: set[str] = set()
    for s in program.statements:
        if isinstance(s, CauseStatement):
            from_pred = s.from_atom.predicate
            to_pred = s.to_atom.predicate
            if to_pred == intervention_pred:
                edges_to_intervention.add(from_pred)
            if to_pred == target_pred:
                edges_to_target.add(from_pred)
        elif isinstance(s, VariableDeclaration):
            if s.domain is not None and set(s.domain) == {True, False}:
                bool_vars.add(s.predicate)

    candidates = (edges_to_intervention - edges_to_target) & bool_vars
    candidates.discard(intervention_pred)
    candidates.discard(target_pred)
    if len(candidates) == 1:
        return next(iter(candidates))
    return None


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
    bidirected = structural_solver.bidirected_from_ground(ground)

    return tuple(
        dispatch(
            program, stmt, graph, theta,
            prob_index=prob_index, obs_index=obs_index,
            bidirected=bidirected,
        )
        for stmt in program.statements
        if isinstance(stmt, QueryStatement)
    )
