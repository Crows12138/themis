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
    CausationQuery,
    CauseQuery,
    ConfidenceSource,
    ConstantExpr,
    CounterfactualConjunctionQuery,
    CounterfactualQuery,
    DerivationStep,
    EffectQuery,
    IdentifyQuery,
    Intervention,
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
    ProximalEffectQuery,
    Query,
    QueryKind,
    QueryResult,
    QueryStatement,
    ResultStatus,
    SCMCounterfactualQuery,
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
    CausationQuery: QueryKind.CAUSATION,
    SCMCounterfactualQuery: QueryKind.SCM_COUNTERFACTUAL,
    CounterfactualConjunctionQuery: QueryKind.COUNTERFACTUAL_CONJUNCTION,
    ProximalEffectQuery: QueryKind.PROXIMAL_EFFECT,
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

    # ───────────────────────── Phase 15B — ID/IDC is the engine.
    # The complete Shpitser-Pearl algorithm decides identifiability and
    # provides the canonical c-factor formula for EVERY point-ID query —
    # pure-DAG and ADMG alike. backdoor / front-door are no longer
    # independent solvers; they are recognized as graph-level PATTERNS
    # (the human surface — "control for W"), attached as an annotation,
    # while the formula itself is the machine-facing c-factor. IV is the
    # assumption-laden ESCALATION, fired only when the engine reports the
    # query is not nonparametrically identifiable. See
    # PHASE_15_ID_FOUNDATION_CHARTER.md.
    from . import c_factor
    if q.given:
        engine = c_factor.identify_via_idc(
            graph, bidirected, x, y, q.given, q.intervention.value,
        )
    else:
        engine = c_factor.identify_via_tian(
            graph, bidirected, x, y, q.intervention.value,
        )

    if engine.identifiable:
        return _build_identify_via_engine(stmt, graph, q, bidirected, engine)

    # Not nonparametrically point-identified — either a Shpitser Line-5 hedge
    # or a Line-7 punt. The instrumental-variable layer is the assumption-laden
    # ESCAPE from non-point-identifiability and applies in BOTH regimes: a valid
    # instrument identifies P(Y|do(X)) under an extra assumption (monotonicity →
    # LATE, linearity → Wald). Consult it before reporting a bare unidentifiable
    # verdict, so a SURROGATE instrument (whose engine returns a definitive
    # {x,y} hedge — What If Fig 16.2) is treated the same as a CAUSAL instrument
    # (whose engine punts at Line-7 — Fig 16.1). iv_sets only returns instruments
    # that satisfy the IV conditions, so the bow arc (no instrument) still falls
    # through to the hedge verdict below.
    if not q.given:
        iv = structural_solver.iv_sets(graph, x, y, bidirected=bidirected)
        if iv:
            return _build_identify_via_iv(
                stmt, graph, q, iv, bidirected=bidirected,
            )

    if engine.hedge is not None and not q.given:
        # Shpitser Line-5 hedge — a definitive, witnessed unidentifiability
        # (the hedge witness verifier covers the unconditional shape).
        return _build_identify_unidentifiable_via_tian(stmt, graph, q, engine)

    # Neither the complete nonparametric algorithm nor the IV escalation
    # reaches it — a genuine structural gap.
    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.IDENTIFY,
        query_id=stmt.id,
        missing_information=(
            MissingItem(
                kind=MissingKind.STRUCTURE,
                name="query:identify_unreachable",
                priority=Priority.HIGH,
                reason=(
                    "Not identifiable by the complete ID/IDC algorithm "
                    "(no c-factor witness), and no instrumental-variable "
                    "escalation applies."
                ),
            ),
        ),
    )


def _build_identify_via_engine(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    bidirected: "frozenset[frozenset[Atom]]",
    engine,
) -> QueryResult:
    """Wrap an ID/IDC engine success (Phase 15B). The canonical c-factor
    formula is the machine artifact; the graph-level identification
    pattern (the recognized backdoor / front-door structure + its
    adjustment / mediator set) is attached as the human-facing
    annotation under ``extensions["identification"]``."""
    from dataclasses import replace as _replace

    if hasattr(engine, "is_fraction"):  # IdcResult (conditional)
        result = _build_identify_via_idc(stmt, graph, q, engine)
    else:  # TianResult (unconditional)
        result = _build_identify_via_tian(stmt, graph, q, engine)

    annotation = _recognize_identification_pattern(graph, bidirected, q, engine)
    ext = dict(result.extensions or {})
    ext["identification"] = annotation
    return _replace(result, extensions=ext)


def _recognize_identification_pattern(
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]",
    q: IdentifyQuery,
    engine=None,
) -> dict:
    """Recognize the identification PATTERN for the graph-level annotation:
    which classic structure the graph exhibits and the set a human reads
    off it ("control for W" / "the mediator is M"). The emitted formula is
    the canonical c-factor regardless — this only labels it for the human.
    """
    x = q.intervention.atom
    y = q.target
    bi = bidirected or None
    annotation: dict
    adjustment = structural_solver.minimal_adjustment_sets(
        graph, x, y, given=q.given, bidirected=bi,
    )
    if adjustment:
        chosen = min(adjustment, key=len)
        annotation = {
            "pattern": "backdoor",
            "adjustment_set": sorted(_atom_to_str(a) for a in chosen),
        }
    elif not q.given and structural_solver.front_door_sets(
        graph, x, y, bidirected=bi
    ):
        front = structural_solver.front_door_sets(graph, x, y, bidirected=bi)
        chosen = min(front, key=len)
        annotation = {
            "pattern": "front_door",
            "mediator_set": sorted(_atom_to_str(a) for a in chosen),
        }
    else:
        annotation = {"pattern": "c_factor"}

    # Conditional estimand P(Y | do(X), Z): the conditioning is PART of
    # the question (e.g. conditioning on a collider) and the formula is
    # the IDC ratio — not a plain "adjust and done". Surface it so the
    # human-facing one-liner isn't lossy: "backdoor, control for {a}"
    # alone would silently drop the Z-conditioning.
    if q.given:
        annotation["conditioned_on"] = sorted(_atom_to_str(a) for a in q.given)
        if getattr(engine, "is_fraction", False):
            annotation["estimand"] = "conditional_idc_ratio"
    return annotation


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


def _build_identify_via_idc(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: IdentifyQuery,
    idc,
) -> QueryResult:
    """Wrap a Shpitser-Pearl IDC success into a full QueryResult.

    Two-step derivation, parallel to the Tian builder:
      s1: idc_rule2_exchange — the do-calculus Rule-2 exchange that
          moved a (possibly empty) subset of the conditioned Z into the
          do-set. The verifier replays the exchange independently.
      s2: identify_via_idc — consumes s1 + the constructed formula
          (a FractionExpr, or the bare numerator when every Z exchanged
          away) and concludes identifiable.
    """
    x = q.intervention.atom
    y = q.target
    structural_result = StructuralResult(value=True)
    validate_formula(idc.formula)

    derivation = (
        DerivationStep(
            rule="idc_rule2_exchange",
            inputs={"graph": graph, "x": x, "y": y},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="identify_via_idc",
            inputs={
                "exchange": StepRef(step_id="s1"),
                "formula": idc.formula,
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
        formula=idc.formula,
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

    instrument_label = _atom_to_str(chosen.instrument)
    conditioning_labels = sorted(_atom_to_str(a) for a in chosen.conditioning)
    extensions = {
        "iv_identification": {
            "strategy": "iv",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
            "required_assumption": (
                "monotonicity (for LATE/Wald) OR linearity (for 2SLS/ATE)"
            ),
            "alternatives_count": len(iv_candidates),
        },
        # Unified graph-level annotation (the human surface), parallel to
        # the backdoor / front-door / c_factor patterns the engine emits.
        # IV is the assumption-laden escalation: the pattern names the
        # instrument and flags that point identification needs an extra
        # assumption — so a renderer keying off extensions["identification"]
        # has a complete story for IV too.
        "identification": {
            "pattern": "instrumental_variable",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
            "required_assumption": (
                "monotonicity (for LATE/Wald) OR linearity (for 2SLS/ATE)"
            ),
        },
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
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Phase 6.mediation — identification + numeric-evaluation dispatch.

    Invoked from ``_dispatch_effect`` when ``q.mediator`` is set. Runs
    Pearl's four-condition check for NDE/NIE and the backdoor-based
    C1/C2 check for CDE via ``structural_solver.mediation_sets``, then
    packages the result with ``extensions.mediation_decomposition``.

    v0.1.4 Fix 1 extension: when the treatment is boolean and at least
    one identification strategy succeeds, the kernel additionally
    evaluates the relevant g-formulas against ``theta`` and produces:

    - For NDE/NIE: E[Y(treated)], E[Y(control)], E[Y(treated, M(control))],
      and the derived TE / NDE-at-control / NIE-at-treated.
    - For CDE: per-mediator-value CDE(m) = E[Y|do(X=treated, M=m)] −
      E[Y|do(X=control, M=m)].

    Numeric values surface in ``extensions.mediation_decomposition.numeric``.
    When TE is computed, ``numeric_result.value`` carries it and status
    upgrades to NUMERICALLY_SOLVED; otherwise stays STRUCTURALLY_SOLVED
    (still carries any partial CDE numbers in extensions).

    Falls back to structural-only when treatment is non-boolean (non-MVP)
    or when theta is incomplete (recorded as ``status: insufficient_theta``
    in the numeric block with the specific missing key).

    See PHASE_6_MEDIATION_CHARTER.md §3.3.
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

    # v0.1.4 Fix 1: numeric evaluation against theta.
    # MVP gate: boolean treatment only — sufficient for CLadder-style
    # mediation questions and for the canonical Pearl 2001 case study.
    # Non-boolean treatments stay STRUCTURALLY_SOLVED (extension point
    # for future: contrast-specifying assumptions on EffectQuery).
    status = ResultStatus.STRUCTURALLY_SOLVED
    numeric_result: NumericResult | None = None

    x_treated_value = q.intervention.value
    if isinstance(x_treated_value, bool) and (
        mediation.nde_nie.identifiable or mediation.cde.identifiable
    ):
        x_control_value = not x_treated_value
        nde_nie_adj = (
            tuple(sorted(mediation.nde_nie.adjustment, key=_atom_to_str))
            if mediation.nde_nie.identifiable else None
        )
        cde_adj = (
            tuple(sorted(mediation.cde.adjustment, key=_atom_to_str))
            if mediation.cde.identifiable else None
        )
        numeric_block, numeric_step = _evaluate_mediation_numerically(
            target=q.target,
            x_atom=x,
            x_treated=x_treated_value,
            x_control=x_control_value,
            mediator=m,
            theta=theta,
            nde_nie_adj=nde_nie_adj,
            cde_adj=cde_adj,
            observed=q.given,
            step_id="s4",
        )
        if numeric_block is not None:
            extensions["mediation_decomposition"]["numeric"] = numeric_block
            te = numeric_block.get("te")
            if te is not None and numeric_step is not None:
                # Only attach numeric steps to the derivation when the
                # total-effect closure succeeded — that's the canonical
                # "numeric_result terminates a numeric effect derivation"
                # invariant the verifier enforces. Partial cases (e.g.
                # CDE-only, or NDE/NIE InsufficientTheta) still surface
                # in extensions for the renderer but stay
                # STRUCTURALLY_SOLVED with the original 3-step
                # identification derivation as the verifier trail.
                status = ResultStatus.NUMERICALLY_SOLVED
                numeric_result = NumericResult(value=te)
                derivation = derivation + (
                    numeric_step,
                    DerivationStep(
                        rule="numeric_result",
                        inputs={"evaluation": StepRef(step_id=numeric_step.step_id)},
                        output=numeric_result,
                        step_id="s5",
                    ),
                )

    return QueryResult(
        status=status,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=structural_result,
        numeric_result=numeric_result,
        derivation=derivation,
        extensions=extensions,
    )


def _evaluate_mediation_numerically(
    *,
    target: ValuedAtom,
    x_atom: Atom,
    x_treated: bool,
    x_control: bool,
    mediator: Atom,
    theta: Theta,
    nde_nie_adj: "tuple[Atom, ...] | None",
    cde_adj: "tuple[Atom, ...] | None",
    observed: tuple[ValuedAtom, ...],
    step_id: str,
) -> "tuple[dict | None, DerivationStep | None]":
    """v0.1.4 Fix 1 helper — evaluate mediation g-formulas against theta.

    Two independent branches:

    1. NDE/NIE (when ``nde_nie_adj is not None``): build the natural
       and cross-world potential-outcome formulas via
       ``formula_builder.mediation_potential_outcome_formula``, evaluate
       three of them — E[Y(treated)], E[Y(control)], E[Y(treated,
       M(control))] — and derive TE / NDE-at-control / NIE-at-treated.
    2. CDE (when ``cde_adj is not None``): for each mediator value in
       ``theta.domain_of(mediator)`` build two controlled-outcome
       formulas via
       ``formula_builder.mediation_controlled_outcome_formula`` and
       subtract to produce CDE(m).

    Each branch's failure (InsufficientTheta on any constituent formula
    evaluation) is independent — a partial result records whichever
    branch succeeded plus an ``insufficient_theta`` note on the branch
    that failed. Returns ``(None, None)`` only if no branch was even
    attempted (both adjustments None — caller's gate should prevent
    that).
    """
    treated_va = ValuedAtom(atom=x_atom, value=x_treated)
    control_va = ValuedAtom(atom=x_atom, value=x_control)

    numeric: dict = {}

    if nde_nie_adj is not None:
        try:
            f_treated = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=treated_va,
                intervention_inner=treated_va,
                mediator=mediator,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            f_control = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=control_va,
                intervention_inner=control_va,
                mediator=mediator,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            # Two cross-world potentials — one per Pearl decomposition.
            # Both are needed because the choice of "reference treatment"
            # for NDE/NIE is ambiguous in general (interactions make the
            # two decompositions disagree), and CLadder asks both forms.
            f_cross_treated_outer = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=treated_va,
                intervention_inner=control_va,
                mediator=mediator,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            f_cross_control_outer = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=control_va,
                intervention_inner=treated_va,
                mediator=mediator,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            e_y_treated = numeric_estimator.estimate_formula(f_treated, theta)
            e_y_control = numeric_estimator.estimate_formula(f_control, theta)
            e_y_cross_treated_outer = numeric_estimator.estimate_formula(
                f_cross_treated_outer, theta
            )
            e_y_cross_control_outer = numeric_estimator.estimate_formula(
                f_cross_control_outer, theta
            )
            numeric["e_y_treated"] = e_y_treated
            numeric["e_y_control"] = e_y_control
            # Two cross-world quantities; ``e_y_cross_world`` is the
            # backwards-compat alias for the treated-outer form (the only
            # one present in pre-v0.1.4-rc internal sketches). Renderers
            # should prefer the explicit ``e_y_cross_treated_outer`` /
            # ``e_y_cross_control_outer`` keys.
            numeric["e_y_cross_world"] = e_y_cross_treated_outer
            numeric["e_y_cross_treated_outer"] = e_y_cross_treated_outer
            numeric["e_y_cross_control_outer"] = e_y_cross_control_outer
            numeric["te"] = e_y_treated - e_y_control
            # Pearl decomposition (treated reference): TE = NDE_at_control + NIE_at_treated.
            numeric["nde_at_control"] = e_y_cross_treated_outer - e_y_control
            numeric["nie_at_treated"] = e_y_treated - e_y_cross_treated_outer
            # Pearl decomposition (control reference): TE = NDE_at_treated + NIE_at_control.
            numeric["nde_at_treated"] = e_y_treated - e_y_cross_control_outer
            numeric["nie_at_control"] = e_y_cross_control_outer - e_y_control
        except InsufficientTheta as ite:
            numeric["nde_nie_status"] = {
                "status": "insufficient_theta",
                "missing_key": (
                    format_probability_key(ite.missing_key)
                    if ite.missing_key else None
                ),
                "reason": ite.reason,
            }

    if cde_adj is not None:
        mediator_domain = theta.domain_of(mediator)
        cde_per_m: dict = {}
        cde_failure = None
        for m_val in mediator_domain:
            m_va = ValuedAtom(atom=mediator, value=m_val)
            try:
                f_treated_m = formula_builder.mediation_controlled_outcome_formula(
                    target=target,
                    intervention=treated_va,
                    mediator=m_va,
                    adjustment_set=cde_adj,
                    observed=observed,
                )
                f_control_m = formula_builder.mediation_controlled_outcome_formula(
                    target=target,
                    intervention=control_va,
                    mediator=m_va,
                    adjustment_set=cde_adj,
                    observed=observed,
                )
                cde_treated = numeric_estimator.estimate_formula(f_treated_m, theta)
                cde_control = numeric_estimator.estimate_formula(f_control_m, theta)
                cde_per_m[str(m_val)] = cde_treated - cde_control
            except InsufficientTheta as ite:
                cde_failure = {
                    "status": "insufficient_theta",
                    "mediator_value": str(m_val),
                    "missing_key": (
                        format_probability_key(ite.missing_key)
                        if ite.missing_key else None
                    ),
                    "reason": ite.reason,
                }
                break
        if cde_per_m:
            numeric["cde"] = cde_per_m
        if cde_failure is not None:
            numeric["cde_status"] = cde_failure

    if not numeric:
        return None, None

    # Only include adjustments that were used. Serializer would choke
    # on None values; the absence of a key tells the verifier that
    # strategy didn't run. Mediator domain is derived by the verifier
    # from its own ctx.theta rather than being shipped in inputs (saves
    # a serialization shape and avoids drift if theta domains evolve).
    inputs: dict = {
        "target": target,
        "intervention_treated": treated_va,
        "intervention_control": control_va,
        "mediator": mediator,
        "observed": observed,
    }
    if nde_nie_adj is not None:
        inputs["nde_nie_adjustment"] = nde_nie_adj
    if cde_adj is not None:
        inputs["cde_adjustment"] = cde_adj

    step = DerivationStep(
        rule="mediation_numeric_evaluate",
        inputs=inputs,
        output=numeric,
        step_id=step_id,
    )
    return numeric, step


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


def _poc_quantity(lower: float, upper: float, point: "float | None") -> dict:
    """Serialize one probability-of-causation quantity (PN / PS / PNS).

    ``point`` is omitted when the quantity is not point-identified (no
    monotonicity) — its absence is itself information for the renderer.
    """
    d: dict = {"lower": lower, "upper": upper}
    if point is not None:
        d["point"] = point
    return d


def _derive_interventional_risks(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    x_atom: Atom,
    y_atom: Atom,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[Statement, ...]" = (),
) -> "tuple[tuple[float, float] | None, QueryResult | None]":
    """Derive P(Y=1 | do(X=1)) and P(Y=1 | do(X=0)) by running the
    existing effect identification twice.

    Reuses ``_dispatch_effect`` — so the interventional risks inherit the
    full backdoor / front-door / Tian / IV identification cascade for
    free. Returns ``((p1, p0), None)`` on success, or ``(None, gap)``
    where ``gap`` is a causation-kind ``needs_investigation`` result
    carrying the merged missing-information and a pointer to the
    experimental-risk escape hatch.
    """
    risks: list[float] = []
    merged_missing: list[MissingItem] = []
    merged_requests: list[InvestigationRequest] = []
    for x_val in (True, False):
        internal = QueryStatement(
            id=f"{stmt.id}::do_x{'1' if x_val else '0'}",
            query=EffectQuery(
                target=ValuedAtom(atom=y_atom, value=True),
                intervention=Intervention(atom=x_atom, value=x_val),
                given=(),
            ),
        )
        sub = _dispatch_effect(
            internal, graph, theta,
            bidirected=bidirected, selection_nodes=selection_nodes,
        )
        if (
            sub.status == ResultStatus.NUMERICALLY_SOLVED
            and sub.numeric_result is not None
            and sub.numeric_result.value is not None
        ):
            risks.append(float(sub.numeric_result.value))
        else:
            for item in sub.missing_information:
                if item.name not in {m.name for m in merged_missing}:
                    merged_missing.append(item)
            merged_requests.extend(sub.investigation_requests)
    if len(risks) == 2:
        return (risks[0], risks[1]), None

    # At least one interventional risk could not be obtained — the effect
    # of X on Y is not identifiable from theta (confounding / missing CPT).
    escape = MissingItem(
        kind=MissingKind.ASSUMPTION,
        name="causation:interventional_risk_unavailable",
        priority=Priority.HIGH,
        reason=(
            "P(Y=1|do(X)) could not be derived (effect not identifiable from "
            "the supplied data). Supply experimental_risk_treated / "
            "experimental_risk_control from a randomized experiment, or add "
            "the data needed to identify the effect."
        ),
    )
    gap = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.CAUSATION,
        query_id=stmt.id,
        missing_information=tuple(merged_missing) + (escape,),
        investigation_requests=tuple(merged_requests),
    )
    return None, gap


def _causation_observational_joint(
    graph: nx.DiGraph,
    theta: Theta,
    x_atom: Atom,
    y_atom: Atom,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> "tuple[dict[tuple[bool, bool], float] | None, tuple[MissingItem, ...], dict]":
    """Recover the four P(X=x, Y=y) cells from theta.

    Graph-faithful ancestral BN factorization first — this handles
    measured confounders (Z→X, Z→Y, X→Y), where the X/Y marginals
    P(X) / P(Y|X) are NOT directly in theta and must be obtained by
    summing over Z. Local P(X)·P(Y|X) chain-rule fallback second: the
    confounded-but-experimental case (drug example) supplies those
    marginals directly, and the ancestral factorization conservatively
    bails when a bidirected bow arc touches the ancestry of {X, Y}.
    """
    joint, missing, skeletons = (
        _counterfactual_joint_xy_via_ancestral_factorization(
            graph, theta, x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
        )
    )
    if joint is not None or missing:
        return joint, tuple(missing), skeletons

    missing_items: list[MissingItem] = []
    skel: dict = {}
    cells: dict[tuple[bool, bool], float] = {}
    for x_val in (True, False):
        for y_val in (True, False):
            try:
                cells[(x_val, y_val)] = _estimate_counterfactual_joint_cell(
                    theta, x_atom=x_atom, x_val=x_val,
                    y_atom=y_atom, y_val=y_val,
                )
            except InsufficientTheta as exc:
                item = _missing_parameter_from_key(exc.missing_key, exc.reason)
                if item.name not in {m.name for m in missing_items}:
                    missing_items.append(item)
                    if exc.missing_key is not None:
                        skel[item.name] = _skeleton_for_parameter(exc.missing_key)
    if missing_items:
        return None, tuple(missing_items), skel
    return cells, (), {}


def _dispatch_causation(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[Statement, ...]" = (),
) -> QueryResult:
    """Probabilities of causation — PN / PS / PNS (Tian & Pearl 2000).

    Recovers the observational joint P(X, Y) from theta, obtains the two
    interventional risks P(Y=1 | do(X=1/0)) — either user-supplied
    (randomized-experiment data, the confounded drug-example case) or
    DERIVED by running the effect identification twice — and feeds both
    into ``probabilities_of_causation`` (the Tian-Pearl core, verified
    against the published drug example). Returns the assumption-free
    bounds, plus point values when the query declares ``monotonic``.
    """
    from .probabilities_of_causation import probabilities_of_causation

    q: CausationQuery = stmt.query  # type: ignore[assignment]
    x_atom = q.cause
    y_atom = q.effect

    # 1. Both atoms must be in G(M).
    missing_atoms = [a for a in (x_atom, y_atom) if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.CAUSATION,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason="causation query atom is not in the instantiated variable set V",
                )
                for a in missing_atoms
            ),
        )

    # 2. PN/PS/PNS are defined for BINARY cause and effect only.
    for atom, role in ((x_atom, "cause"), (y_atom, "effect")):
        domain = set(theta.domain_of(atom))
        if not domain or not domain <= {False, True}:
            return QueryResult(
                status=ResultStatus.OUTSIDE_LANGUAGE,
                query_kind=QueryKind.CAUSATION,
                query_id=stmt.id,
                extensions={
                    "causation_error": (
                        f"probabilities of causation require a binary {role} "
                        f"({atom.predicate}); got domain "
                        f"{sorted(domain, key=str) or 'unknown'}"
                    )
                },
            )

    # 3. Observational joint P(X, Y) — four cells from theta.
    joint, joint_missing, joint_skeletons = _causation_observational_joint(
        graph, theta, x_atom, y_atom, bidirected=bidirected,
    )
    if joint_missing:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.CAUSATION,
            query_id=stmt.id,
            missing_information=tuple(joint_missing),
            investigation_requests=investigation_pusher.push(
                tuple(joint_missing), skeletons=joint_skeletons,
            ),
        )

    # 4. Interventional risks P(Y=1 | do(X=1/0)).
    if (
        q.experimental_risk_treated is not None
        and q.experimental_risk_control is not None
    ):
        p_y_do_x1 = float(q.experimental_risk_treated)
        p_y_do_x0 = float(q.experimental_risk_control)
        risk_provenance = "user_experimental"
    else:
        risks, gap = _derive_interventional_risks(
            stmt, graph, theta, x_atom, y_atom,
            bidirected=bidirected, selection_nodes=selection_nodes,
        )
        if gap is not None:
            return gap
        p_y_do_x1, p_y_do_x0 = risks
        risk_provenance = "derived_identification"

    # 4b. Feasibility: the interventional risks must be consistent with the
    # observational joint. By consistency P(y_x) = P(x, y) + P(y_x, x') with
    # P(y_x, x') ∈ [0, P(x')], so P(y_x) ∈ [P(x,y), P(x,y)+P(x')] (and the
    # mirror for P(y_{x'})). Infeasible user-supplied experimental risks
    # otherwise make the Tian-Pearl bounds invert (lower > upper) — an empty
    # interval that silently signals the two data sources contradict. Derived
    # risks are always feasible; the check still guards them defensively.
    p_x1 = joint[(True, True)] + joint[(True, False)]
    p_x0 = joint[(False, True)] + joint[(False, False)]
    _TOL = 1e-9
    infeasible: list[str] = []
    lo1, hi1 = joint[(True, True)], joint[(True, True)] + p_x0
    if not (lo1 - _TOL <= p_y_do_x1 <= hi1 + _TOL):
        infeasible.append(
            f"P(Y=1|do(X=1))={p_y_do_x1:.6g} must lie in "
            f"[P(X=1,Y=1), P(X=1,Y=1)+P(X=0)] = [{lo1:.6g}, {hi1:.6g}]"
        )
    lo0, hi0 = joint[(False, True)], joint[(False, True)] + p_x1
    if not (lo0 - _TOL <= p_y_do_x0 <= hi0 + _TOL):
        infeasible.append(
            f"P(Y=1|do(X=0))={p_y_do_x0:.6g} must lie in "
            f"[P(X=0,Y=1), P(X=0,Y=1)+P(X=1)] = [{lo0:.6g}, {hi0:.6g}]"
        )
    if infeasible:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.CAUSATION,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.ASSUMPTION,
                    name="causation:interventional_risks_infeasible",
                    priority=Priority.HIGH,
                    reason=(
                        "the interventional risks contradict the observational "
                        "joint (consistency constraint), so no SCM produces "
                        "both — PN/PS/PNS are undefined. "
                        + "; ".join(infeasible)
                    ),
                ),
            ),
        )

    # 5. Tian-Pearl PN / PS / PNS.
    poc = probabilities_of_causation(
        p_x1_y1=joint[(True, True)], p_x1_y0=joint[(True, False)],
        p_x0_y1=joint[(False, True)], p_x0_y0=joint[(False, False)],
        p_y_do_x1=p_y_do_x1, p_y_do_x0=p_y_do_x0,
        monotonic=q.monotonic,
    )

    # 6. Package. The derivation step's output and extensions.causation
    # carry the SAME envelope so the verifier can re-check the whole
    # PN/PS/PNS structure (not just the PN headline) from one place.
    envelope = {
        "monotonic": q.monotonic,
        "interventional_risk_provenance": risk_provenance,
        "p_y_do_x1": p_y_do_x1,
        "p_y_do_x0": p_y_do_x0,
        "observational_joint": {
            "p_x1_y1": joint[(True, True)], "p_x1_y0": joint[(True, False)],
            "p_x0_y1": joint[(False, True)], "p_x0_y0": joint[(False, False)],
        },
        "pn": _poc_quantity(poc.pn_lower, poc.pn_upper, poc.pn_point),
        "ps": _poc_quantity(poc.ps_lower, poc.ps_upper, poc.ps_point),
        "pns": _poc_quantity(poc.pns_lower, poc.pns_upper, poc.pns_point),
    }

    # Headline = PN (necessity / liability): the canonical attribution
    # quantity. Point under monotonicity, interval otherwise.
    if poc.pn_point is not None:
        numeric_result = NumericResult(value=poc.pn_point)
        status = ResultStatus.COUNTERFACTUAL_SOLVED
    else:
        numeric_result = NumericResult(
            value=None,
            interval=NumericInterval(low=poc.pn_lower, high=poc.pn_upper),
        )
        status = ResultStatus.COUNTERFACTUAL_BOUNDED

    derivation = (
        DerivationStep(
            rule="probabilities_of_causation_tian_pearl",
            inputs={
                "cause": x_atom,
                "effect": y_atom,
                "p_x1_y1": joint[(True, True)],
                "p_x1_y0": joint[(True, False)],
                "p_x0_y1": joint[(False, True)],
                "p_x0_y0": joint[(False, False)],
                "p_y_do_x1": p_y_do_x1,
                "p_y_do_x0": p_y_do_x0,
                "monotonic": q.monotonic,
                "interventional_risk_provenance": risk_provenance,
            },
            output=envelope,
            step_id="s1",
        ),
    )

    return QueryResult(
        status=status,
        query_kind=QueryKind.CAUSATION,
        query_id=stmt.id,
        numeric_result=numeric_result,
        derivation=derivation,
        extensions={"causation": envelope},
    )


def _scm_observation_map(program: Program) -> dict:
    """Collect the unit's numeric factual values from the program's
    ObservationStatements — Pearl's evidence E=e. Non-numeric
    observations are skipped (a linear SCM is over real-valued nodes)."""
    from ..types import ObservationStatement
    obs: dict = {}
    for s in program.statements:
        if isinstance(s, ObservationStatement):
            try:
                obs[s.atom] = float(s.value)
            except (TypeError, ValueError):
                continue
    return obs


def _dispatch_scm_counterfactual(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    program: Program,
) -> QueryResult:
    """Deterministic linear-SCM counterfactual point (Pearl Primer §4.2:
    abduction–action–prediction).

    Builds the linear SCM from the path coefficients declared on the
    cause edges, takes the unit's factual values from the program's
    ObservationStatements, and computes the exact counterfactual value
    the target would have taken under the intervention. Surfaces a
    structured gap when the SCM is under-specified (an edge on the path
    lacks a coefficient) or the unit is under-observed (a relevant
    variable was not measured — abduction cannot recover its U).
    """
    from . import scm_counterfactual as scm

    q: SCMCounterfactualQuery = stmt.query  # type: ignore[assignment]
    x_atom = q.intervention.atom
    y_atom = q.target

    missing_atoms = [a for a in (x_atom, y_atom) if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.SCM_COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason="scm_counterfactual query atom is not in the variable set V",
                )
                for a in missing_atoms
            ),
        )

    # Relevant set on the MUTILATED graph: do(X) severs every edge INTO X
    # (Pearl's action step), so a variable that reached the target solely
    # through X is no longer relevant — its observation and incoming
    # coefficients must NOT be demanded. Computing ancestors on the
    # original graph over-demands exactly that severed upstream.
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(graph.in_edges(x_atom)))
    relevant = set(nx.ancestors(mutilated, y_atom)) | {y_atom}

    obs_map = _scm_observation_map(program)
    missing: list[MissingItem] = []

    # Build the structural equations from edge coefficients; flag any
    # edge on the relevant subgraph that lacks a declared coefficient. The
    # intervened variable is skipped — its equation is replaced by the
    # constant, so we never abduct its exogenous term and its incoming
    # edges/parents are irrelevant.
    equations: dict = {}
    for v in relevant:
        if v == x_atom:
            continue
        terms: list[tuple] = []
        for p in graph.predecessors(v):
            src = graph.edges[p, v].get("source")
            coef = getattr(src, "coefficient", None) if src is not None else None
            if coef is None:
                missing.append(MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"coefficient:{_atom_to_str(p)}->{_atom_to_str(v)}",
                    priority=Priority.HIGH,
                    reason=(
                        "linear-SCM counterfactual needs the path coefficient "
                        f"on edge {_atom_to_str(p)} -> {_atom_to_str(v)}"
                    ),
                ))
            else:
                terms.append((p, float(coef)))
        equations[v] = tuple(terms)

    # The unit must be fully observed over the relevant set (abduction).
    for v in relevant:
        if v not in obs_map:
            missing.append(MissingItem(
                kind=MissingKind.OBSERVATION,
                name=f"observation:{_atom_to_str(v)}",
                priority=Priority.HIGH,
                reason=(
                    "deterministic counterfactual needs this variable observed "
                    "for the unit so abduction can recover its exogenous term"
                ),
            ))

    if missing:
        # Deduplicate by name, keep order.
        seen: set[str] = set()
        deduped: list[MissingItem] = []
        for m in missing:
            if m.name not in seen:
                seen.add(m.name)
                deduped.append(m)
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.SCM_COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=tuple(deduped),
            investigation_requests=investigation_pusher.push(tuple(deduped)),
        )

    topo = tuple(n for n in nx.topological_sort(graph) if n in relevant)
    observed = {v: obs_map[v] for v in relevant}

    result = scm.linear_scm_counterfactual(
        equations=equations,
        observed=observed,
        intervention_var=x_atom,
        intervention_value=float(q.intervention.value),
        target=y_atom,
        topo_order=topo,
    )

    numeric_result = NumericResult(value=result.target_value)
    extensions = {
        "scm_counterfactual": {
            "target": _atom_to_str(y_atom),
            "target_value": result.target_value,
            "intervention": {
                "variable": _atom_to_str(x_atom),
                "value": float(q.intervention.value),
            },
            "abducted_noise": {
                _atom_to_str(a): v for a, v in result.noise.items()
            },
            "counterfactual_values": {
                _atom_to_str(a): v for a, v in result.cf_values.items()
            },
            "reference": (
                "Pearl, Glymour & Jewell (2016) Primer §4.2 "
                "abduction-action-prediction"
            ),
        }
    }
    derivation = (
        DerivationStep(
            rule="scm_abduction_action_prediction",
            inputs={
                "target": y_atom,
                "intervention_var": x_atom,
                "intervention_value": float(q.intervention.value),
            },
            output=numeric_result,
            step_id="s1",
        ),
    )
    return QueryResult(
        status=ResultStatus.COUNTERFACTUAL_SOLVED,
        query_kind=QueryKind.SCM_COUNTERFACTUAL,
        query_id=stmt.id,
        numeric_result=numeric_result,
        derivation=derivation,
        extensions=extensions,
    )


def _dispatch_counterfactual_conjunction(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """General counterfactual identification (Shpitser-Pearl ID*/IDC*, R-336 /
    JMLR 9:1941-1979 2008).

    Converts the query's events into a ``ctf_identify`` conjunction γ (and an
    optional conditioning conjunction δ = ``query.condition``) and runs ID*
    (δ empty) or IDC* (δ non-empty), which decide identifiability structurally
    and reduce each interventional leaf to observational ``P(v)`` through the
    existing ID engine. Outcomes:

    - a ``FormulaExpr`` → identifiable; the estimand over observational
      ``P(v)`` is returned as ``structurally_solved`` (mirrors ``identify``).
      For the conditional case this is a ``FractionExpr`` ``P(γ',δ')/P(δ')``.
    - ``ZERO`` → the (numerator) conjunction is inconsistent (an effectiveness
      violation ``x_{x'}`` or contradictory worlds), so ``P(γ|δ)=0`` — a
      definite identified answer, returned as the constant ``0``.
    - ``FAIL`` → provably non-identifiable (a w-graph / subscript-conflict
      witness, e.g. the PNS ``P(y_x, y'_{x'})`` with a direct X→Y edge, or a
      back-door blocking every IDC* move), surfaced as ``needs_investigation``.
    - ``UNDEFINED`` (conditional only) → the conditioning event δ has
      probability 0, so ``P(γ|δ)`` is undefined; surfaced as
      ``needs_investigation`` with a distinct reason.
    """
    from .ctf_identify import CtfEvent, FAIL, UNDEFINED, ZERO, id_star, idc_star

    q: CounterfactualConjunctionQuery = stmt.query  # type: ignore[assignment]

    referenced = [
        a
        for e in (*q.events, *q.condition)
        for a in (e.variable, *(s.atom for s in e.subscript))
    ]
    missing_atoms = [a for a in referenced if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason=(
                        "counterfactual event atom is not in the "
                        "instantiated variable set V"
                    ),
                )
                for a in missing_atoms
            ),
        )

    def _to_gamma(events):
        return tuple(
            CtfEvent(
                variable=e.variable,
                subscript=frozenset((s.atom, s.value) for s in e.subscript),
                value=e.value,
            )
            for e in events
        )

    gamma = _to_gamma(q.events)
    delta = _to_gamma(q.condition)

    if delta:
        outcome = idc_star(graph, bidirected, gamma, delta)
    else:
        outcome = id_star(graph, bidirected, gamma)

    if outcome is UNDEFINED:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="query:conditioning_event_probability_zero",
                    priority=Priority.HIGH,
                    reason=(
                        "P(γ|δ) is undefined: the conditioning conjunction δ "
                        "has probability 0 in every model consistent with the "
                        "graph (an effectiveness violation or contradictory "
                        "worlds), so the conditional does not exist."
                    ),
                ),
            ),
        )

    if outcome is FAIL:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="query:counterfactual_unidentifiable",
                    priority=Priority.HIGH,
                    reason=(
                        "P(γ|δ) is not identifiable by the ID*/IDC* algorithm "
                        "— a w-graph / subscript-conflict witness (e.g. the PNS "
                        "P(y_x, y'_{x'}) with a direct X→Y edge, or a back-door "
                        "blocking every conditional move). No observational "
                        "estimand exists."
                    ),
                ),
            ),
        )

    if outcome is ZERO:
        formula: FormulaExpr = ConstantExpr(value=0.0)
    else:
        formula = outcome
        validate_formula(formula)

    structural_result = StructuralResult(value=True)
    derivation = (
        DerivationStep(
            rule="id_star_identification",
            inputs={"graph": graph, "formula": formula},
            output=structural_result,
            step_id="s1",
        ),
    )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
        query_id=stmt.id,
        structural_result=structural_result,
        formula=formula,
        derivation=derivation,
    )


def _dispatch_proximal_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Proximal causal inference (Miao-Geng-Tchetgen 2018; Kuroki-Pearl 2014).

    Decides whether the average causal effect ``P(Y|do(X))`` is identifiable when
    the sufficient confounder ``U`` is unobserved, using the declared proxies
    ``Z`` (treatment-inducing) and ``W`` (outcome-inducing) via
    ``proximal_identify.identify_proximal`` (Miao model (f)). Outcomes:

    - a ``ProximalEstimand`` → identifiable; returned as ``structurally_solved``
      with the estimand roles/method attached in ``extensions`` (an estimand
      descriptor — the from-data ATE is the ``estimate()`` numeric overlay, since
      proximal identification produces a matrix operation, not a formula AST).
    - a ``ProximalNotIdentified`` → surfaced as ``needs_investigation`` with a
      structure gap naming the failed criterion + human diagnosis.
    """
    from .proximal_identify import (
        ProximalEstimand,
        ProximalNotIdentified,
        identify_proximal,
    )

    q: ProximalEffectQuery = stmt.query  # type: ignore[assignment]

    referenced = [
        q.treatment, q.outcome, q.latent, q.treatment_proxy, q.outcome_proxy,
    ]
    missing_atoms = [a for a in referenced if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.PROXIMAL_EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"atom:{_atom_to_str(a)}",
                    priority=Priority.HIGH,
                    reason=(
                        "proximal query role atom is not in the instantiated "
                        "variable set V"
                    ),
                )
                for a in missing_atoms
            ),
        )

    outcome = identify_proximal(
        graph, bidirected,
        treatment=q.treatment, outcome=q.outcome, latent=q.latent,
        treatment_proxy=q.treatment_proxy, outcome_proxy=q.outcome_proxy,
        latent_cardinality=q.latent_cardinality,
    )

    if isinstance(outcome, ProximalNotIdentified):
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.PROXIMAL_EFFECT,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="query:proximal_not_identifiable",
                    priority=Priority.HIGH,
                    reason=(
                        f"P(Y|do(X)) is not proximal-identifiable "
                        f"({outcome.failed_criterion}): {outcome.reason}"
                    ),
                ),
            ),
        )

    estimand: ProximalEstimand = outcome
    descriptor = {
        "method": estimand.method,
        "treatment": _atom_to_str(estimand.treatment),
        "outcome": _atom_to_str(estimand.outcome),
        "latent": _atom_to_str(estimand.latent),
        "treatment_proxy": _atom_to_str(estimand.treatment_proxy),
        "outcome_proxy": _atom_to_str(estimand.outcome_proxy),
        "latent_cardinality": estimand.latent_cardinality,
        # Join to a scalar string: this descriptor rides a DerivationStep's
        # inputs, whose serializer takes scalars / atoms / graphs but not a
        # collection of plain strings.
        "data_conditions": " | ".join(estimand.data_conditions),
    }
    structural_result = StructuralResult(value=True)
    derivation = (
        DerivationStep(
            rule="proximal_criterion",
            inputs={"graph": graph, "estimand": descriptor},
            output=structural_result,
            step_id="s1",
        ),
    )
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.PROXIMAL_EFFECT,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions={"proximal_estimand": descriptor},
    )


def _try_numeric(
    stmt: QueryStatement,
    formula,
    theta: Theta,
    kind: QueryKind,
    *,
    structural_prefix: tuple[DerivationStep, ...] = (),
    evaluation_step_id: str = "s_eval",
    graph=None,
    bidirected=None,
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

    Iter 199: ``graph`` + ``bidirected`` enable the d-separation
    safety guard for marginal-independence fallback in the evaluator.
    See themis.runtime.numeric_estimator.estimate_formula for details.
    """
    try:
        value = numeric_estimator.estimate_formula(
            formula, theta, graph=graph, bidirected=bidirected,
        )
    except InsufficientTheta as exc:
        # Surface ALL distinct distributions the estimand still needs, not just
        # the first gap the fail-fast evaluator hit — so the data-gap report is
        # honest about the complete data requirement (front-door needs three
        # factors, back-door two). collect_missing_keys re-runs the SAME
        # resolution path (fallbacks included) so a derivable factor is never
        # reported missing.
        missing_keys = numeric_estimator.collect_missing_keys(
            formula, theta, graph=graph, bidirected=bidirected,
        )
        skeletons: dict = {}
        if missing_keys:
            missing_items: tuple[MissingItem, ...] = tuple(
                _missing_parameter_from_key(key, exc.reason)
                for key in missing_keys
            )
            for item, key in zip(missing_items, missing_keys):
                skeletons[item.name] = _skeleton_for_parameter(key)
        else:
            # No concrete key collected (e.g. a value-less query-bound atom):
            # keep the single original gap.
            single = _missing_parameter_from_key(exc.missing_key, exc.reason)
            missing_items = (single,)
            if exc.missing_key is not None:
                skeletons[single.name] = _skeleton_for_parameter(exc.missing_key)
        requests = investigation_pusher.push(
            missing_items, skeletons=skeletons
        )
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=kind,
            query_id=stmt.id,
            formula=formula,
            missing_information=missing_items,
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
    theta: Theta,
    selection_nodes: "tuple[Statement, ...]",
) -> QueryResult:
    """Phase 9 §T9.1.3 + Fix 3+4 §T9.2 (v0.1.5): Bareinboim-Pearl
    single-source transport identification + numeric evaluation.

    Identifiable case:
      - Builds the transport g-formula
        ``Σ_z P(Y|X,Z,source) · ∏ P*(Z|...,target)`` via
        ``formula_builder.transport_formula`` and tries to evaluate
        against the supplied two-population ``theta`` (population-
        partitioned per Fix 3+4 infrastructure slice, commit 3f2ece6).
      - If theta has both populations' entries sufficiently → status
        upgrades to ``numerically_solved``, derivation appends the
        canonical ``formula_evaluation`` + ``numeric_result`` pair
        (matching the mediation Fix 1 pattern).
      - If theta is short of either source's ``P(Y|X,Z)`` or target's
        ``P*(Z)`` → stays ``structurally_solved`` with an
        investigation_request naming the specific missing population
        key. In real deployment the agent then either supplies user
        data OR proposes ``population=target_xxx`` ``provenance=
        llm_prior`` priors (Fix 3 mechanic, charter §3.2).

    Unidentifiable case (structural) → ``needs_investigation`` with a
    structure-group missing item naming the failure reason. Identical
    to pre-fix behaviour.
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

    # Fix 3+4 §T9.2 numeric branch: try to evaluate the transport
    # formula against the two-population theta. Source factor uses
    # population=src_pop (from SelectionNode.source_population);
    # target factors use population=q.target_population. Identical
    # population strings here and on the supplied ProbabilityStatements
    # are the contract — mismatch surfaces as InsufficientTheta with
    # the specific missing key including its population tag.
    # EffectQuery.intervention is Intervention (atom + value); transport_
    # formula wants a ValuedAtom for the source X conditional. Construct
    # the ValuedAtom from the intervention pair.
    intervention_va = ValuedAtom(
        atom=q.intervention.atom, value=q.intervention.value,
    )
    transport_formula_expr = formula_builder.transport_formula(
        target=q.target,
        intervention=intervention_va,
        adjustment_set=tuple(result.adjustment_set),
        source_population=src_pop or "source",
        target_population=q.target_population or "target",
        observed=q.given,
    )
    validate_formula(transport_formula_expr)

    try:
        value = numeric_estimator.estimate_formula(
            transport_formula_expr, theta,
            graph=graph, bidirected=None,
        )
    except InsufficientTheta as ite:
        # Stay structurally_solved; surface the specific missing
        # (target or source) probability key via investigation request
        # so the agent (Fix 3 path) can propose an llm_prior patch.
        missing = _missing_parameter_from_key(
            ite.missing_key, ite.reason,
        )
        skeletons: dict = {}
        if ite.missing_key is not None:
            skeletons[missing.name] = _skeleton_for_parameter(ite.missing_key)
        requests = investigation_pusher.push(
            (missing,), skeletons=skeletons,
        )
        return QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=True),
            formula=transport_formula_expr,
            derivation=derivation_steps,
            missing_information=(missing,),
            investigation_requests=requests,
            extensions={"transport_identification": transport_block},
        )

    # Numeric success: append (transport_formula_ast, formula_evaluation,
    # numeric_result) to the existing 3-step structural prefix. The
    # transport_formula_ast step carries the FormulaExpr (parallel to
    # backdoor_adjustment_formula / front_door_adjustment_formula) so
    # verify_numeric's formula-witness check has a step to match
    # formula_evaluation against. The existing s_t9_2 (transport_formula
    # with string output) stays — string repr is human-readable extension
    # metadata; the AST is the machine-verifiable derivation witness.
    ast_step_id = "s_t9_ast"
    eval_step_id = "s_t9_eval"
    numeric_result_obj = NumericResult(value=value)
    derivation_steps = derivation_steps + (
        DerivationStep(
            rule="transport_formula_ast",
            inputs={
                "target": q.target,
                "intervention": intervention_va,
                "adjustment_set": tuple(result.adjustment_set),
                "source_population": src_pop or "source",
                "target_population": q.target_population or "target",
                "observed": q.given,
            },
            output=transport_formula_expr,
            step_id=ast_step_id,
        ),
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": transport_formula_expr},
            output=value,
            step_id=eval_step_id,
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef(step_id=eval_step_id)},
            output=numeric_result_obj,
            step_id="s_t9_final_num",
        ),
    )
    transport_block_with_numeric = dict(transport_block)
    transport_block_with_numeric["numeric"] = {
        "value": value,
        "source_population": src_pop,
        "target_population": q.target_population,
    }

    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=StructuralResult(value=True),
        numeric_result=numeric_result_obj,
        formula=transport_formula_expr,
        derivation=derivation_steps,
        extensions={"transport_identification": transport_block_with_numeric},
    )


def _try_iv_wald_in_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    x: Atom,
    y: Atom,
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> "QueryResult | None":
    """Fix 6 (v0.1.5, audit follow-up): IV-in-effect via Wald LATE.

    Wald estimator (binary treatment + binary instrument, under
    monotonicity)::

        LATE = (E[Y|Z=1] - E[Y|Z=0]) / (E[X=1|Z=1] - E[X=1|Z=0])

    Returns None when:
    - no valid instrument found (caller falls through to next strategy)
    - theta lacks any of the 4 required entries (returns None too;
      caller falls through — IV-numeric is opportunistic, doesn't
      block; if instrument exists but data is short, downstream gap
      report surfaces the missing keys when caller hits final
      needs_investigation)

    Semantic caveat surfaced via ``extensions.iv_identification.late_caveat``:
    LATE is the average effect AMONG COMPLIERS (the subpopulation
    whose treatment is shifted by the instrument), NOT the population
    ATE. Don't conflate.

    Wald demands boolean treatment + boolean instrument; non-boolean
    falls through to None and the next strategy gets a try.
    """
    # Conditional guard: the Wald LATE below is the UNCONDITIONAL complier
    # effect — it looks up P(Y|Z), P(X|Z) with no `given` term, so shipping it
    # for a query that conditions on a context would silently drop `given` and
    # answer the wrong question (the same silent-drop class Phase 1 closed on
    # the Tian path). Bail so a conditional query falls through to the IDC
    # branch (correct conditional) or an honest refusal — never an unconditional
    # LATE in place of the conditional. Unconditional IV queries are unaffected.
    if q.given:
        return None
    # MVP gate: boolean treatment, boolean instrument
    x_treated = q.intervention.value
    if not isinstance(x_treated, bool):
        return None
    x_control = not x_treated

    iv_candidates = structural_solver.iv_sets(
        graph, x, y, bidirected=bidirected,
    )
    if not iv_candidates:
        return None

    chosen = iv_candidates[0]
    z = chosen.instrument
    # MVP: boolean instrument
    z_domain = theta.domain_of(z)
    if z_domain != (True, False) and set(z_domain) != {True, False}:
        return None
    z_treated, z_control = True, False

    # 4 theta lookups: P(Y=y_val|Z=z_*), P(X=x_*|Z=z_*).
    # For W (conditioning), the Wald formula generalises to
    # P(...|Z=z, W=w) summed over P(W=w). MVP: skip W (require empty
    # conditioning) — extension hook for later.
    if chosen.conditioning:
        return None

    def _lookup(target_atom: Atom, target_val, given_pairs):
        key = numeric_estimator.ProbabilityKey(
            target_atom=target_atom,
            target_value=target_val,
            given=frozenset(given_pairs),
        )
        return theta.entries.get(key)

    p_y_given_z1 = _lookup(y, q.target.value, [(z, z_treated)])
    p_y_given_z0 = _lookup(y, q.target.value, [(z, z_control)])
    p_x_given_z1 = _lookup(x, x_treated, [(z, z_treated)])
    p_x_given_z0 = _lookup(x, x_treated, [(z, z_control)])

    if None in (p_y_given_z1, p_y_given_z0, p_x_given_z1, p_x_given_z0):
        return None  # Opportunistic: let next strategy / final
        # needs_investigation surface the missing keys.

    denom = p_x_given_z1 - p_x_given_z0
    if abs(denom) < 1e-12:
        # Wald undefined when instrument doesn't shift treatment.
        return None

    late = (p_y_given_z1 - p_y_given_z0) / denom

    # Derivation: existing iv_criterion_check + identify_via_iv (from
    # identify path) + new iv_wald_numeric_evaluate bundled step.
    treated_va = ValuedAtom(atom=x, value=x_treated)
    z_treated_va = ValuedAtom(atom=z, value=z_treated)
    z_control_va = ValuedAtom(atom=z, value=z_control)

    iv_id_step = DerivationStep(
        rule="iv_criterion_check",
        inputs={
            "graph": graph,
            "x": x,
            "y": y,
            "instrument": z,
            "conditioning": chosen.conditioning,
        },
        output=True,
        step_id="s_iv_check",
    )
    iv_choose_step = DerivationStep(
        rule="identify_via_iv",
        inputs={"criterion": StepRef(step_id="s_iv_check")},
        output=StructuralResult(value=True),
        step_id="s_iv_id",
    )
    iv_numeric_step = DerivationStep(
        rule="iv_wald_numeric_evaluate",
        inputs={
            "target": q.target,
            "intervention_treated": treated_va,
            "instrument_treated": z_treated_va,
            "instrument_control": z_control_va,
            "monotonicity": q.assumptions.monotonicity.value,
        },
        output={
            "p_y_given_z_treated": p_y_given_z1,
            "p_y_given_z_control": p_y_given_z0,
            "p_x_given_z_treated": p_x_given_z1,
            "p_x_given_z_control": p_x_given_z0,
            "late": late,
        },
        step_id="s_iv_numeric",
    )
    numeric_result_obj = NumericResult(value=late)
    final_step = DerivationStep(
        rule="numeric_result",
        inputs={"evaluation": StepRef(step_id="s_iv_numeric")},
        output=numeric_result_obj,
        step_id="s_iv_final",
    )

    extensions = {
        "iv_identification": {
            "strategy": "iv",
            "instrument": _atom_to_str(z),
            "conditioning": sorted(
                _atom_to_str(a) for a in chosen.conditioning
            ),
            "required_assumption": (
                f"monotonicity ({q.assumptions.monotonicity.value}) — "
                f"Wald LATE estimator"
            ),
            "alternatives_count": len(iv_candidates),
            "late_caveat": (
                "LATE = E[Y(X=treated) − Y(X=control) | complier]; "
                "this is the average effect AMONG COMPLIERS (the "
                "subpopulation whose treatment is shifted by the "
                "instrument), NOT the population ATE. Conflating LATE "
                "with ATE is a known IV-deployment pitfall — surface "
                "this caveat to the user before stating the answer."
            ),
            "numeric": {
                "p_y_given_z_treated": p_y_given_z1,
                "p_y_given_z_control": p_y_given_z0,
                "p_x_given_z_treated": p_x_given_z1,
                "p_x_given_z_control": p_x_given_z0,
                "late": late,
            },
        }
    }

    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=StructuralResult(value=True),
        numeric_result=numeric_result_obj,
        derivation=(iv_id_step, iv_choose_step, iv_numeric_step, final_step),
        extensions=extensions,
    )


def _dispatch_joint_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    x: Atom,
    y_atom: Atom,
    extra_atoms: tuple[Atom, ...],
    observed_atoms: tuple[Atom, ...],
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Joint multi-treatment effect identification: do(A=a, B=b, ...).

    Identifies the joint interventional contrast via the generalized
    (treatment-set) back-door criterion
    (``structural_solver.minimal_adjustment_sets_joint``) and emits a
    structurally-solved result. The data-based numeric joint contrast +
    treatment×treatment interaction is attached later by the estimation
    dispatch (``themis.estimate``); identification here is data-free.

    Out-of-scope combinations are refused explicitly:
    - ``mediator`` / ``target_population`` set together with a joint
      intervention (mediation / transport decompose a single X→Y effect;
      a joint decomposition is a separate, unbuilt operation).

    Latent (bidirected) confounding is in scope: the joint adjustment
    criterion below uses m-separation for ADMGs, so an adjustment-
    identifiable latent-confounded joint effect is solved. A latent joint
    effect with no valid adjustment set (front-door / c-component for
    sets) falls through to the ``not joint_sets`` honest refusal.
    """
    treatments = (x, *extra_atoms)

    if q.mediator is not None or q.target_population is not None:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="joint:unsupported_layer_combination",
                    priority=Priority.HIGH,
                    reason=(
                        "joint multi-treatment interventions cannot be "
                        "combined with mediation / transport in v1; these "
                        "decompose a single-treatment effect and a joint "
                        "decomposition is a separate operation"
                    ),
                ),
            ),
        )

    # Duplicate treatment atoms (same predicate intervened twice) are a
    # malformed joint vector.
    if len(set(treatments)) != len(treatments):
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="joint:duplicate_treatment",
                    priority=Priority.HIGH,
                    reason="the joint treatment vector repeats an atom",
                ),
            ),
        )

    joint_sets = structural_solver.minimal_adjustment_sets_joint(
        graph, treatments, y_atom,
        given=observed_atoms, bidirected=bidirected or None,
    )

    if not joint_sets:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name="identification:joint_not_identifiable",
                    priority=Priority.HIGH,
                    reason=(
                        "no valid joint (treatment-set) back-door adjustment "
                        "set blocks all proper non-causal paths from the "
                        "treatment vector to the target"
                    ),
                ),
            ),
        )

    chosen = min(joint_sets, key=len)
    treatments_set = frozenset(treatments)
    given_set = frozenset(observed_atoms)
    structural_result = StructuralResult(value=True)

    derivation = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="joint_backdoor_criterion",
            inputs={
                "graph": graph,
                "treatments": treatments_set,
                "y": y_atom,
                "z": chosen,
                "given": given_set,
            },
            output=True,
            step_id="s2",
        ),
        DerivationStep(
            rule="identify_via_joint_backdoor",
            inputs={"criterion": StepRef(step_id="s2")},
            output=structural_result,
            step_id="s3",
        ),
    )

    annotation = {
        "pattern": "joint_backdoor",
        "treatments": sorted(_atom_to_str(t) for t in treatments),
        "adjustment_set": sorted(_atom_to_str(a) for a in chosen),
        "interaction": "difference_scale",
    }
    if observed_atoms:
        annotation["conditioned_on"] = sorted(
            _atom_to_str(a) for a in observed_atoms
        )

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions={"joint_identification": annotation},
    )


def _longitudinal_spec_matches(q: EffectQuery, spec: dict) -> bool:
    """Does this effect query designate the program's longitudinal
    strategy question?

    The longitudinal spec lives in ``options.longitudinal`` (it needs the
    time ordering the cross-sectional query grammar can't express), so a
    plain ``do(A_k)`` effect query is the syntactic stand-in for the
    strategy contrast. We treat the query as the longitudinal one iff its
    outcome is the spec's outcome and its (single) intervention is one of
    the spec's time-ordered treatments — with no mediator / transport /
    joint layer stacked on top (those are separate identifications).
    """
    treatments = spec.get("treatments") or []
    outcome = spec.get("outcome")
    if q.mediator is not None or getattr(q, "target_population", None) is not None:
        return False
    if q.extra_interventions:
        return False
    return (
        q.target.atom.predicate == outcome
        and q.intervention.atom.predicate in treatments
    )


# Structural identification assumptions for the g-formula / sequential
# back-door (Hernán & Robins, What If, ch.21). These are the UNTESTABLE
# identification premises — distinct from the parametric-model
# assumptions the estimator surfaces (correct transition / outcome / IP
# models). The graph confirms the DECLARED measured history is sufficient;
# it cannot confirm there is no UNMEASURED time-varying confounder.
_LONGITUDINAL_STRUCTURAL_ASSUMPTIONS = (
    "sequential_exchangeability_no_unmeasured_time_varying_confounding",
    "positivity_each_treatment_level_observed_within_history_strata",
    "consistency_well_defined_sustained_treatment_strategy",
)


def _dispatch_longitudinal(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    spec: dict,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Phase 7.L structural — identify a time-varying treatment STRATEGY
    effect via the g-formula (sequential back-door criterion).

    The longitudinal spec (``options.longitudinal``) supplies the time-
    ordered treatments A_0..A_K and the covariate blocks measured before
    each (``confounders_by_time``). The strategy contrast
    ``E[Y_{ā=treated}] − E[Y_{ā=control}]`` is point-identified by the
    g-formula iff, at each time k, the measured history
    ``H_k = {L_0..L_k, A_0..A_{k-1}}`` blocks every back-door path from
    A_k to Y (Pearl-Robins sequential back-door / sequential
    exchangeability). Future covariates are deliberately excluded from
    H_k, so a causal path A_k → L_{k+1} → Y is never mistaken for a
    back-door and blocked.

    Emits STRUCTURALLY_SOLVED with an ``identify_via_gformula`` derivation
    when every time point passes (the estimation dispatch then attaches
    the g-formula / IPW-MSM number and flips to numerically_solved,
    mirroring transport). On a failing time point — an unblocked back-door
    from some A_k to Y, i.e. an unmeasured / mis-declared time-varying
    confounder — returns NEEDS_INVESTIGATION naming which treatment is
    confounded, and attaches the extension with ``identified: False`` so
    the numeric layer refuses to ship a biased number.
    """
    treatment_names = list(spec.get("treatments") or [])
    conf_blocks_names = [list(b) for b in (spec.get("confounders_by_time") or [])]
    outcome_name = spec.get("outcome")

    pred2node = {n.predicate: n for n in graph.nodes}
    all_names = [*treatment_names, outcome_name,
                 *[c for blk in conf_blocks_names for c in blk]]
    missing_names = [nm for nm in all_names if nm not in pred2node]
    if missing_names:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"longitudinal:atom_not_in_graph:{nm}",
                    priority=Priority.HIGH,
                    reason=(
                        f"longitudinal spec references {nm!r}, which is not a "
                        f"declared variable in the graph"
                    ),
                )
                for nm in missing_names
            ),
        )

    treatments = tuple(pred2node[nm] for nm in treatment_names)
    y = pred2node[outcome_name]
    conf_blocks = tuple(tuple(pred2node[c] for c in blk) for blk in conf_blocks_names)

    # Per-time sequential back-door admissibility. H_k accumulates the
    # measured covariates up to and including time k plus the past
    # treatments A_0..A_{k-1}; each A_k must have every back-door path to Y
    # blocked by H_k. `frozenset() in minimal_adjustment_sets(..., given=H_k)`
    # holds iff H_k itself satisfies the back-door criterion for (A_k, Y)
    # — that bundles the no-descendant precondition with the blocking test.
    per_time = []
    history: list[Atom] = []
    first_failed = None
    for k, a_k in enumerate(treatments):
        history.extend(conf_blocks[k])  # L_k measured BEFORE A_k
        h_k = tuple(history)
        adj = structural_solver.minimal_adjustment_sets(
            graph, a_k, y, given=h_k, bidirected=bidirected or None,
        )
        ok_k = frozenset() in adj
        per_time.append((k, a_k, ok_k))
        if not ok_k and first_failed is None:
            first_failed = (k, a_k)
        history.append(a_k)  # A_k enters the history for later times

    identified = first_failed is None

    identification_ext = {
        "estimand": "time_varying_strategy_contrast",
        "treatments": [_atom_to_str(t) for t in treatments],
        "outcome": _atom_to_str(y),
        "confounders_by_time": [
            [_atom_to_str(a) for a in blk] for blk in conf_blocks
        ],
        "identified": identified,
        "assumptions": list(_LONGITUDINAL_STRUCTURAL_ASSUMPTIONS),
    }

    if not identified:
        k, a_k = first_failed
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                MissingItem(
                    kind=MissingKind.STRUCTURE,
                    name=f"longitudinal:sequential_exchangeability_fails:{_atom_to_str(a_k)}",
                    priority=Priority.HIGH,
                    reason=(
                        f"treatment {_atom_to_str(a_k)} (time {k}) has an open "
                        f"back-door path to {_atom_to_str(y)} that the measured "
                        f"history does not block — sequential exchangeability "
                        f"fails, so the g-formula would return a biased number. "
                        f"Measure the confounder or revise the graph."
                    ),
                ),
            ),
            extensions={"longitudinal_identification": identification_ext},
        )

    structural_result = StructuralResult(value=True)
    derivation = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            step_id="s0",
        ),
        DerivationStep(
            rule="longitudinal_sequential_exchangeability_check",
            inputs={
                "graph": graph,
                "treatments": treatments,
                "confounders_by_time": conf_blocks,
                "y": y,
            },
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="identify_via_gformula",
            inputs={
                "check": StepRef(step_id="s1"),
                "y": y,
                "treatments": treatments,
            },
            output=structural_result,
            step_id="s2",
        ),
    )

    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions={"longitudinal_identification": identification_ext},
    )


def _dispatch_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[Statement, ...]" = (),
    longitudinal_spec: dict | None = None,
) -> QueryResult:
    q: EffectQuery = stmt.query  # type: ignore[assignment]
    x = q.intervention.atom
    y_atom = q.target.atom
    observed_atoms = tuple(g.atom for g in q.given)
    extra_atoms = tuple(iv.atom for iv in q.extra_interventions)

    missing_atoms = [
        a for a in (x, y_atom, *extra_atoms, *observed_atoms) if a not in graph
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

    # Phase 7.L: a time-varying treatment STRATEGY query, declared via
    # options.longitudinal (the cross-sectional query grammar can't carry
    # the time ordering). Short-circuit into g-formula / sequential
    # back-door identification before the single-treatment back-door path
    # — the latter would silently compute the biased static-adjustment
    # ATE. The estimation dispatch attaches the g-formula / IPW-MSM number.
    if longitudinal_spec is not None and _longitudinal_spec_matches(q, longitudinal_spec):
        return _dispatch_longitudinal(
            stmt, graph, q, longitudinal_spec, bidirected=bidirected,
        )

    # Joint interventions: do(A=a, B=b, ...) over a treatment SET.
    # Short-circuit into the generalized (treatment-set) back-door
    # identification before any single-treatment path. v1 scope: not
    # combined with mediator / target_population (those decompose a
    # single X→Y effect — a joint multi-treatment decomposition is a
    # separate, unbuilt operation), so refuse that combination explicitly
    # rather than silently honoring only one layer.
    if q.extra_interventions:
        return _dispatch_joint_effect(
            stmt, graph, q, x, y_atom, extra_atoms, observed_atoms,
            bidirected=bidirected,
        )

    # Phase 9 §T9.1.3: when the query declares a target_population,
    # short-circuit into transport identification (Bareinboim 2014).
    # Fix 3+4 (v0.1.5) closed §T9.2 — transport now evaluates against
    # theta when source+target entries are sufficient, producing a
    # numeric_result instead of structurally_solved-only.
    if getattr(q, "target_population", None) is not None:
        return _dispatch_transport(stmt, graph, q, theta, selection_nodes)

    # Phase 6.mediation: when the query declares a mediator, short-
    # circuit into mediation identification (NDE/NIE/CDE decomposition)
    # instead of computing the plain total-effect formula. v0.1.4 Fix 1
    # extends this path with numeric evaluation against theta — when the
    # treatment is boolean and theta is sufficient, the kernel computes
    # TE / NDE / NIE / CDE end-to-end rather than emitting structural-
    # only identification and leaving numeric assembly to callers.
    if q.mediator is not None:
        return _dispatch_mediation(
            stmt, graph, q, theta, bidirected=bidirected,
        )

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
                        graph=graph, bidirected=bidirected,
                    )
            # Fix 6 (v0.1.5, audit follow-up): IV-in-effect via Wald
            # LATE under monotonicity. Requires the query's
            # EffectQueryAssumptions.monotonicity to be set; without
            # it the kernel can't pick an estimator (Wald vs 2SLS vs
            # bounds differ semantically) and stays at the next
            # fallback. The numeric is the COMPLIER LATE, not the
            # population ATE — extension metadata flags this so the
            # render layer can disclose.
            mono = (
                q.assumptions.monotonicity
                if q.assumptions is not None else None
            )
            if mono is not None:
                iv_result = _try_iv_wald_in_effect(
                    stmt, graph, q, x, y_atom, theta,
                    bidirected=bidirected,
                )
                if iv_result is not None:
                    return iv_result

            # Fix 5 (v0.1.5, audit follow-up): Tian-in-effect — last-
            # resort identification via Shpitser-Pearl ID before giving
            # up. Identify path already does this (line 299-311); effect
            # path used to drop straight to needs_investigation with the
            # "S3.b.2 lands later" comment. Lands now.
            from . import c_factor as _c_factor
            tian = _c_factor.identify_via_tian(
                graph, bidirected, x, y_atom, q.intervention.value,
            )
            # UNCONDITIONAL do(X) only. identify_via_tian ignores the
            # conditioning atoms, so for a CONDITIONAL query (given non-empty)
            # its formula is the MARGINAL P(Y|do(X)) — shipping it would
            # silently drop `given` and label the marginal solved (it can differ
            # sharply from the true conditional when `given` modifies the
            # effect). A conditional general-ID (IDC) numeric end is deferred, so
            # refuse below rather than ship the marginal in its place.
            if tian.identifiable and not observed_atoms:
                # Bind q.target.value into the Tian formula's outer Y
                # ProbRefs (c_factor leaves them None for the
                # IdentifyQuery caller). Without this, the evaluator
                # raises InsufficientTheta on query-bound atoms.
                bound_formula = formula_builder.bind_target_value(
                    tian.formula, y_atom, q.target.value,
                )
                validate_formula(bound_formula)
                # Reuse the identify-side derivation prefix
                # (tian_c_decomposition + identify_via_tian), then
                # add tian_formula_ast + formula_evaluation +
                # numeric_result via _try_numeric. Same shape as
                # transport (Fix 4 §T9.2).
                structural_prefix = (
                    DerivationStep(
                        rule="tian_c_decomposition",
                        inputs={
                            "graph": graph,
                            "x": x,
                            "y": y_atom,
                        },
                        output=True,
                        step_id="s_tian_decomp",
                    ),
                    DerivationStep(
                        rule="identify_via_tian",
                        inputs={
                            "decomposition": StepRef(
                                step_id="s_tian_decomp",
                            ),
                            "formula": tian.formula,
                        },
                        output=StructuralResult(value=True),
                        step_id="s_tian_id",
                    ),
                    DerivationStep(
                        rule="tian_formula_ast",
                        inputs={
                            "target": q.target,
                            "intervention": ValuedAtom(
                                atom=x, value=q.intervention.value,
                            ),
                            "unbound_formula": tian.formula,
                        },
                        output=bound_formula,
                        step_id="s_tian_ast",
                    ),
                )
                return _try_numeric(
                    stmt, bound_formula, theta, QueryKind.EFFECT,
                    structural_prefix=structural_prefix,
                    graph=graph, bidirected=bidirected,
                )

            # Phase 2 (conditional general-ID, IDC): a CONDITIONAL effect query
            # P(Y | do(X), Z) that ADMG-aware backdoor-with-given could not
            # block is handled by Shpitser-Pearl IDC. The Rule-2 exchange moves
            # exchangeable Z into the do-set and normalizes the remainder as
            # ID(Y ∪ Z_rem, X') / ID(Z_rem, X'). identify_via_idc builds the
            # symbolic estimand (X bound, Y and every conditioned Z left as
            # value=None holes); bind the query's Y and Z values in BOTH target
            # and given positions, then evaluate against theta. The IDC fraction
            # is numerically validated to 1e-9 against latent-SCM ground truth
            # (test_idc_fraction_matches_latent_scm_ground_truth). Phase 1
            # (fix b742fbd) previously WITHHELD the marginal here; Phase 2 turns
            # that honest refusal into the correct conditional number.
            if observed_atoms:
                idc = _c_factor.identify_via_idc(
                    graph, bidirected, x, y_atom, observed_atoms,
                    q.intervention.value,
                )
                if idc.identifiable and idc.formula is not None:
                    value_map = {g.atom: g.value for g in q.given}
                    value_map[y_atom] = q.target.value
                    bound_formula = _c_factor.bind_idc_values(
                        idc.formula, value_map,
                    )
                    validate_formula(bound_formula)
                    # Three-step structural prefix, parallel to the Tian-in-
                    # effect path: s1 idc_rule2_exchange (verifier replays the
                    # exchange), s2 identify_via_idc (verifier re-checks the
                    # numerator/denominator shape against its own replay), s3
                    # idc_formula_ast (verifier re-binds Y/Z values). Then
                    # _try_numeric adds formula_evaluation + numeric_result.
                    structural_prefix = (
                        DerivationStep(
                            rule="idc_rule2_exchange",
                            inputs={"graph": graph, "x": x, "y": y_atom},
                            output=True,
                            step_id="s_idc_exchange",
                        ),
                        DerivationStep(
                            rule="identify_via_idc",
                            inputs={
                                "exchange": StepRef(step_id="s_idc_exchange"),
                                "formula": idc.formula,
                            },
                            output=StructuralResult(value=True),
                            step_id="s_idc_id",
                        ),
                        DerivationStep(
                            rule="idc_formula_ast",
                            inputs={
                                "target": q.target,
                                "intervention": ValuedAtom(
                                    atom=x, value=q.intervention.value,
                                ),
                                "given": q.given,
                                "unbound_formula": idc.formula,
                            },
                            output=bound_formula,
                            step_id="s_idc_ast",
                        ),
                    )
                    return _try_numeric(
                        stmt, bound_formula, theta, QueryKind.EFFECT,
                        structural_prefix=structural_prefix,
                        graph=graph, bidirected=bidirected,
                    )
                # Conditioning present but IDC did not identify the conditional
                # (a hedge on the conditional estimand even where the marginal
                # margin was Tian-identifiable): honest structural refusal
                # naming the conditional path — never the marginal in its place.
                return QueryResult(
                    status=ResultStatus.NEEDS_INVESTIGATION,
                    query_kind=QueryKind.EFFECT,
                    query_id=stmt.id,
                    missing_information=(
                        MissingItem(
                            kind=MissingKind.STRUCTURE,
                            name="query:effect_admg_conditional",
                            priority=Priority.HIGH,
                            reason=(
                                "conditional general-ID (IDC) effect: the "
                                "conditional P(Y|do(X), given) is not identifiable "
                                "in this ADMG (the Rule-2 exchange plus ID recursion "
                                "hit a hedge on the conditional estimand). No "
                                "marginal is shipped in its place."
                            ),
                        ),
                    ),
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
                            "backdoor nor front-door nor Tian / Shpitser "
                            "ID (latter checked since Fix 5 v0.1.5). "
                            "If a Line-7 case is at play see "
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
                    graph=graph, bidirected=bidirected,
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
    # When X has no directed path to Y it is not a cause of Y, so given the
    # back-door-blocking adjustment set Y ⊥ X and P(Y|X,Z) = P(Y|Z). Keeping X
    # in the conditional would be spurious AND un-supplyable (X is not a parent
    # of Y, so the validator rejects P(Y|X,...)). Drop it so the estimand — and
    # the data-gap report derived from it — names a distribution the user can
    # actually provide.
    x_is_cause = structural_solver.has_directed_path(graph, x, y_atom)
    formula = formula_builder.backdoor_formula(
        target=q.target,
        intervention=intervention_va,
        adjustment_set=tuple(topo),
        observed=q.given,
        include_intervention=x_is_cause,
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
        graph=graph, bidirected=bidirected,
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
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    *,
    bidirected=None,
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

    Iter 204: thread ``bidirected`` through to ``_try_numeric`` so the
    iter 199 d-separation guard actually fires for probability queries.
    Pre-iter-204 the bidirected argument was dropped at this call site,
    leaving the guard dormant for the entire ``probability`` query path
    — a chain DAG (S→T→C) with marginal-only theta P(C|S) and a query
    P(C|S,T) silently returned the marginal value (0.18) instead of
    refusing, because the guard short-circuits when ``bidirected is
    None`` (see numeric_estimator._try_marginal_independence_lookup).
    Found by L3 case 012 (Pearl 1995 smoking-tar-cancer chain).
    """
    q: ProbabilityQuery = stmt.query  # type: ignore[assignment]
    formula = formula_builder._conditional(  # type: ignore[attr-defined]
        q.target,
        q.given,
    )
    return _try_numeric(
        stmt, formula, theta, QueryKind.PROBABILITY,
        graph=graph, bidirected=bidirected,
    )


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
            long_spec = None
            if program.options:
                _ls = program.options.get("longitudinal")
                if isinstance(_ls, dict):
                    long_spec = _ls
            result = _dispatch_effect(
                stmt, graph, theta,
                bidirected=bidirected, selection_nodes=sel_nodes,
                longitudinal_spec=long_spec,
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
            result = _dispatch_probability(
                stmt, graph, theta, bidirected=bidirected,
            )
    elif isinstance(q, CounterfactualQuery):
        result = _dispatch_counterfactual(
            stmt, graph, theta, bidirected=bidirected
        )
    elif isinstance(q, CausationQuery):
        from ..types import SelectionNode as _SN
        sel_nodes = tuple(s for s in program.statements if isinstance(s, _SN))
        result = _dispatch_causation(
            stmt, graph, theta,
            bidirected=bidirected, selection_nodes=sel_nodes,
        )
    elif isinstance(q, SCMCounterfactualQuery):
        result = _dispatch_scm_counterfactual(stmt, graph, program)
    elif isinstance(q, CounterfactualConjunctionQuery):
        result = _dispatch_counterfactual_conjunction(
            stmt, graph, bidirected=bidirected
        )
    elif isinstance(q, ProximalEffectQuery):
        result = _dispatch_proximal_effect(
            stmt, graph, bidirected=bidirected
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
    result = _attach_selection_recovery(program, stmt, result, graph=graph)
    result = _attach_missing_data_recovery(program, stmt, result, graph=graph)
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


def _is_selection_collider(
    graph: nx.DiGraph, x: Atom, y: Atom, w: Atom,
) -> bool:
    """Hernán 2004 §3 'common effect': W is a selection collider of X and Y
    iff there is a directed path X→…→W not through Y AND a directed path
    Y→…→W not through X. A pure chain X→Y→W (X ancestor only *via* Y) is
    over-control on a mediator, not selection on a collider — excluded.

    Mirrors the predicate-level rule in
    ``data_gap_report._classify_selection_on_collider_opens_path`` but runs
    directly on the projected graph via reachability.
    """
    if w in (x, y) or x not in graph or y not in graph or w not in graph:
        return False
    g_no_y = graph.copy()
    g_no_y.remove_node(y)
    g_no_x = graph.copy()
    g_no_x.remove_node(x)
    x_reaches_w = x in g_no_y and nx.has_path(g_no_y, x, w)
    y_reaches_w = y in g_no_x and nx.has_path(g_no_x, y, w)
    return x_reaches_w and y_reaches_w


def _serialize_selection_recovery(rec, x: Atom, y: Atom) -> dict:
    """Serialize a SelectionRecoveryResult to the JSON extension block."""
    return {
        "kind": "selection_recovery",
        "query_kind": rec.query_kind,
        "treatment": x.predicate,
        "outcome": y.predicate,
        "recoverable": rec.recoverable,
        "criterion": rec.criterion,
        "selection_nodes": [a.predicate for a in rec.selection_nodes],
        "adjustment_set": [a.predicate for a in rec.adjustment_set],
        "z_plus": [a.predicate for a in rec.z_plus],
        "z_minus": [a.predicate for a in rec.z_minus],
        "recovery_formula": rec.formula_repr,
        "external_data_needed": list(rec.external_data_needed),
        "failure_reason": rec.failure_reason,
        "reference": (
            "Bareinboim & Pearl 2012 (selection backdoor criterion); "
            "Bareinboim, Tian & Pearl 2014 (recoverability)"
        ),
    }


def _attach_selection_recovery(
    program: Program | None,
    stmt: QueryStatement | None,
    result: QueryResult,
    *,
    graph: nx.DiGraph,
) -> QueryResult:
    """Phase 9 §S9.1: attach the Bareinboim-Pearl recoverability verdict.

    Fires only for an EffectQuery whose sample is restricted (via an
    ``ObservationStatement``) on a node that is a *selection collider* of
    the treatment and outcome — exactly the situation the
    ``selection_on_collider_opens_path`` gap warns about. This turns that
    one-sided warning into a constructive verdict: whether P(y|do(x)) is
    s-recoverable from the biased sample, with what formula, and what
    external data (if any) is required.
    """
    from dataclasses import replace as _replace
    from ..types import EffectQuery, ObservationStatement
    from .selection_recovery import recover_effect

    if program is None or stmt is None:
        return result
    q = getattr(stmt, "query", None)
    if not isinstance(q, EffectQuery):
        return result
    x = q.intervention.atom
    y = q.target.atom
    if x not in graph or y not in graph:
        return result

    # Selection nodes = the sample-restricting ObservationStatement atoms,
    # resolved to graph nodes by predicate (grounding may relabel args).
    pred2node = {n.predicate: n for n in graph.nodes}
    s_atoms: list[Atom] = []
    for st in program.statements:
        if not isinstance(st, ObservationStatement):
            continue
        node = pred2node.get(st.atom.predicate)
        if node is None or node in (x, y) or node in s_atoms:
            continue
        s_atoms.append(node)
    if not s_atoms:
        return result

    # Gate: only surface when at least one restriction is a genuine
    # selection collider (otherwise there is no selection-bias question).
    if not any(_is_selection_collider(graph, x, y, s) for s in s_atoms):
        return result

    rec = recover_effect(graph, x, y, tuple(s_atoms))
    block = _serialize_selection_recovery(rec, x, y)
    new_ext = dict(result.extensions or {})
    new_ext["selection_recovery"] = block
    return _replace(result, extensions=new_ext)


def _serialize_missing_data_recovery(rec) -> dict:
    """Serialize a MissingDataRecoveryResult to the JSON extension block.

    Describes the ADJUSTED CONDITIONAL P(Y | X, given, Z) — the top-level
    keys are backward-compatible with the original slice. The full-estimand
    verdict (which also needs P(Z) recoverable) lives under ``estimand``,
    attached by ``_attach_missing_data_recovery``.
    """
    return {
        "kind": "missing_data_recovery",
        "target": rec.target_repr,
        "mechanism": rec.mechanism,
        "recoverable": rec.recoverable,
        "partially_observed": [a.predicate for a in rec.partially_observed],
        "factorization": [
            {"factor": yi.predicate, "conditioned_on": [a.predicate for a in xi]}
            for yi, xi in rec.factorization
        ],
        "recovery_formula": rec.formula_repr,
        "failure_reason": rec.failure_reason,
        "reference": (
            "Mohan, Pearl & Tian 2013 (m-graphs; MCAR/MAR/MNAR; "
            "ordered-factorization recoverability)"
        ),
    }


def _serialize_covariate_recovery(rec) -> dict | None:
    """Serialize the covariate-marginal P(Z) recovery (None if Z is empty)."""
    if rec is None:
        return None
    return {
        "target": rec.target_repr,
        "recoverable": rec.recoverable,
        "factorization": [
            {"factor": yi.predicate, "conditioned_on": [a.predicate for a in xi]}
            for yi, xi in rec.factorization
        ],
        "recovery_formula": rec.formula_repr,
        "failure_reason": rec.failure_reason,
    }


def _attach_missing_data_recovery(
    program: Program | None,
    stmt: QueryStatement | None,
    result: QueryResult,
    *,
    graph: nx.DiGraph,
) -> QueryResult:
    """Phase 9 §S9.2: attach the Mohan-Pearl-Tian missing-data verdict.

    Fires for an EffectQuery when the program declares at least one
    ``MissingnessIndicator``. It classifies the mechanism (MCAR/MAR/MNAR)
    and decides whether the full back-door g-formula estimand

        P(Y | do(X), given) = Σ_z P(Y | X, given, Z=z) · P(Z=z | given)

    is recoverable — where Z is a smallest back-door adjustment set for
    (X, Y). The interventional distribution is a PRODUCT of two manifest
    factors, so it is recoverable iff BOTH the adjusted conditional
    P(Y|X,given,Z) AND the covariate marginal P(Z|given) are recoverable
    (Mohan-Pearl-Tian 2013 §4). The top-level block describes the
    conditional (backward-compatible); the ``estimand`` sub-block carries
    the combined multi-factor verdict, and ``covariate_recovery`` the P(Z)
    factor (null when Z is empty).
    """
    from dataclasses import replace as _replace
    from ..types import EffectQuery, MissingnessIndicator
    from .missing_data import analyze_missing_data_estimand

    if program is None or stmt is None:
        return result
    q = getattr(stmt, "query", None)
    if not isinstance(q, EffectQuery):
        return result
    indicators = [
        s for s in program.statements if isinstance(s, MissingnessIndicator)
    ]
    if not indicators:
        return result

    x = q.intervention.atom
    y = q.target.atom
    if x not in graph or y not in graph:
        return result

    given = tuple(g.atom for g in q.given if g.atom in graph)
    # g-formula conditioning: X ∪ given ∪ (smallest back-door Z if any).
    z: tuple[Atom, ...] = ()
    try:
        adj_sets = structural_solver.minimal_adjustment_sets(graph, x, y, given=given)
        if adj_sets:
            z = tuple(sorted(min(adj_sets, key=len), key=lambda a: a.predicate))
    except Exception:
        z = ()
    est = analyze_missing_data_estimand(graph, indicators, y, x, given=given, z=z)
    block = _serialize_missing_data_recovery(est.conditional)
    block["adjustment_set"] = [a.predicate for a in est.adjustment_set]
    block["covariate_recovery"] = _serialize_covariate_recovery(est.covariate)
    block["estimand"] = {
        "target": est.estimand_repr,
        "recoverable": est.recoverable,
        "recovery_formula": est.formula_repr,
        "requires": (
            ["conditional P(Y|X,Z)", "covariate P(Z)"]
            if est.covariate is not None else ["conditional P(Y|X)"]
        ),
        "failure_reason": est.failure_reason,
    }
    new_ext = dict(result.extensions or {})
    new_ext["missing_data_recovery"] = block
    return _replace(result, extensions=new_ext)


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
    # iter 203: graph-CPT independence mismatch — must surface as a ⚠
    # explanation line so the renderer can't silently drop the inconsist-
    # ency under a generic "missing data" framing. The iter 202 reason
    # already enriches the missing_information channel; this entry pins
    # the structural caveat into result.explanation alongside it.
    "graph_theta_independence_mismatch",
    # iter 205: measurement-error concern surfaced from variable
    # measurement / observability metadata. Must surface as a ⚠ line
    # so a reviewer reading only ``result.explanation`` sees the
    # identification-impact warning before the headline number.
    "measurement_error_concern",
    # iter 206: implicit selection on a collider — distinct shape from
    # explicit collider conditioning (which fires on EffectQuery.given).
    # Sample restriction via ObservationStatement(W, value) opens the
    # X→…→W←…←Y non-causal path. Must surface so a reviewer reading
    # only the explanation sees the selection-bias warning before the
    # headline conditional.
    "selection_on_collider_opens_path",
    # iter 207: ill-defined intervention from intervention's variable
    # declaring state_vs_event="state" without time_window. Must surface
    # so a reviewer sees the well-defined-intervention concern (Hernán
    # & Taubman 2008) before the headline number — different
    # interventions producing the same state value entail different
    # counterfactual outcomes; do(X=state) without naming the
    # manipulation route is silently violating consistency.
    "ill_defined_intervention_versions",
    # 2026-06-18: dichotomization — a path variable's ``threshold`` field
    # marks a continuous measure cut at a cutpoint. Must surface so a
    # reviewer sees the operationalisation caveat (efficiency loss /
    # cutpoint sensitivity / within-category residual confounding;
    # Royston-Altman-Sauerbrei 2006) before the headline number, with the
    # dose-response (Phase 13/14) alternative.
    "dichotomized_continuous_measure",
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

    target_event_is_discrete = _target_event_is_discrete(program, query)
    if not target_event_is_discrete:
        return result

    # The intervened arm P(X=x) must itself be a non-degenerate discrete
    # event: a bool treatment, or a multi-valued treatment whose declared
    # domain contains the intervened level. An undeclared continuous
    # treatment gives a vacuous [0,1] arm bound, so it is not bounded here.
    if not _intervention_arm_is_discrete(program, query):
        return result

    # Manski natural bounds a single arm P(Y=y | do(X=x)) and are
    # cardinality-agnostic in the treatment (the off-arm mass is P(X≠x),
    # be it one other level or several). Balke-Pearl (16-type response
    # function) and Manski-Tamer (monotone envelope over ordered levels)
    # are both binary-TREATMENT constructions, so they stay gated on a
    # bool intervention value; a multi-valued treatment falls through to
    # the assumption-free Manski natural floor.
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
    if intervention_is_bool and instrument_pred and target_is_bool:
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
    #    target+treatment pair. Binary treatment only; falls back to
    #    Manski natural if no MTR declaration applies.
    if bounds is None and intervention_is_bool:
        mtr_direction = _detect_monotonicity_for_query(program, query)
        if mtr_direction is not None:
            bounds = attempt_manski_tamer_monotonicity(
                query,
                monotonicity=mtr_direction,
                outcome_event_is_discrete=True,
            )

    # 4. Always-available fallback (any treatment cardinality; bool OR
    #    discrete-numeric outcome event).
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


def _event_is_discrete(program: Program, predicate: str, value) -> bool:
    """Check whether ``P(predicate = value)`` is a non-degenerate discrete
    event — needed before invoking Manski-style bounds whose formula
    assumes a well-defined event probability for both the target event
    ``P(Y=y)`` and the intervened arm ``P(X=x)``.

    True iff ``value`` is bool, OR ``value`` is numeric (int/float not
    bool) AND the predicate's variable declaration carries a discrete
    numeric ``domain`` of length ≥2 containing the value. A value with no
    declared discrete domain is treated as an unbounded continuous point
    (degenerate point mass) and rejected.
    """
    from ..types import VariableDeclaration

    if isinstance(value, bool):
        return True
    if not isinstance(value, (int, float)):
        return False  # string values fall here — out of scope this phase

    decl = next(
        (
            s for s in program.statements
            if isinstance(s, VariableDeclaration) and s.predicate == predicate
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
    return value in domain


def _target_event_is_discrete(program: Program, query) -> bool:
    """Whether ``P(target.atom = target.value)`` is a non-degenerate
    discrete event (see :func:`_event_is_discrete`)."""
    from ..types import EffectQuery

    if not isinstance(query, EffectQuery):
        return False
    return _event_is_discrete(
        program, query.target.atom.predicate, query.target.value,
    )


def _intervention_arm_is_discrete(program: Program, query) -> bool:
    """Whether the intervened arm ``P(X = intervention.value)`` is a
    non-degenerate discrete event — the treatment-side analogue of
    :func:`_target_event_is_discrete`. A bool treatment is always
    discrete; a multi-valued treatment must declare a discrete numeric
    domain containing the intervened level; an undeclared continuous
    treatment yields a degenerate point mass and is rejected (its Manski
    arm bound would be a vacuous [0, 1])."""
    from ..types import EffectQuery

    if not isinstance(query, EffectQuery):
        return False
    return _event_is_discrete(
        program, query.intervention.atom.predicate, query.intervention.value,
    )


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
    bidirected = structural_solver.bidirected_from_ground(ground)
    validate_against_graph(ground, graph, bidirected=bidirected)
    theta = theta_builder.build_theta(ground)
    prob_index = build_probability_source_index(ground)
    obs_index = build_observation_source_index(ground)

    return tuple(
        dispatch(
            program, stmt, graph, theta,
            prob_index=prob_index, obs_index=obs_index,
            bidirected=bidirected,
        )
        for stmt in program.statements
        if isinstance(stmt, QueryStatement)
    )
