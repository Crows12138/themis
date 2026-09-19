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

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from itertools import product
from typing import NamedTuple

import networkx as nx

from .. import blocks, gaps, language, refusals, routing
from ..refusals import Refusal
from ..ledger import Monotonicity
from .iv_words import Complier, Premise
from .scheduler_words import Feasibility, Tried
from ..risk_provenance import RiskProvenance, stamp

from ..input.semantic_validator import validate_against_graph, validate_formula
from ..ledger import Monotonicity
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
    DispatchRecord,
    EffectQuery,
    FormulaExpr,
    GapKind,
    IdentifyQuery,
    Intervention,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    MissingItem,
    MissingKind,
    NumericInterval,
    NumericResult,
    Observable,
    Priority,
    ProbabilityQuery,
    Program,
    ProximalEffectQuery,
    QueryKind,
    QueryResult,
    QueryStatement,
    ResultStatus,
    SCMCounterfactualQuery,
    SelectionNode,
    StepRef,
    StructuralResult,
    ValuedAtom,
    atoms_the_graph_is_asked_about,
    ends_the_given_holds,
)
from . import (
    confidence_calc,
    counterfactual,
    formula_builder,
    investigation_pusher,
    numeric_estimator,
    postprocess,
    structural_solver,
    theta_builder,
)
from .graph_projection import atom_label
from .numeric_estimator import (
    AtomValue,
    InsufficientTheta,
    ProbabilityKey,
    Theta,
    format_probability_key,
)
from .theta_builder import (
    build_observation_source_index,
    build_probability_source_index,
)


# The envelope's spelling of a ground atom. Defined beside the graph
# whose nodes it names, because what is written with it is read back
# against them.
_atom_to_str = atom_label


def _proximal_channel_fields(channel) -> dict:
    """How a declared proximal channel says itself on the envelope.

    One author, because two layers write it: identification puts it on the
    estimand block and the verifier reads it back to decide which arithmetic
    it is re-running. ``channel_kind`` is the discriminator and the rest are
    that kind's own parameters — the flat form of the union the query holds,
    and flat only because of what a derivation step's serializer does to a
    nested dict.
    """
    from ..types import BridgeChannel

    if isinstance(channel, BridgeChannel):
        out = {
            "channel_kind": "bridge_channel",
            "estimator": str(channel.estimator),
            **_bridge_descriptor(channel.outcome_bridge, "outcome_bridge"),
        }
        if channel.treatment_bridge is not None:
            out.update(
                _bridge_descriptor(channel.treatment_bridge, "treatment_bridge"))
        return out
    return {
        "channel_kind": "discrete_channel",
        "latent_cardinality": int(channel.latent_cardinality),
    }


def _bridge_descriptor(bridge, prefix: str) -> dict:
    """One bridge, as the envelope carries it — flattened under its name.

    Prefixed keys and not a nested object for the same reason the channel
    itself is flat: this dict is both an extension block and a derivation
    step's input, and the step serializer tags a nested dict where the
    extension keeps it plain. The prefix is what a nesting level would have
    been, spelled into the key.

    The design goes out term by term and factor by factor. A single ``basis``
    used to sit at this level, from when a side was one variable's expansion
    and one family therefore described it; a design over several variables
    has one family per factor, and a descriptor naming one could not say
    which factor it was for.
    """
    return {
        f"{prefix}_span_terms": _terms_descriptor(bridge.span_terms),
        f"{prefix}_moment_terms": _terms_descriptor(bridge.moment_terms),
        # Counted from those terms rather than declared beside them, and
        # carried anyway because the verifier's under-determination check
        # is about widths and should not have to re-derive them silently.
        f"{prefix}_span_width": int(bridge.span_width),
        f"{prefix}_moment_width": int(bridge.moment_width),
        # Absent is not zero — it is "nobody named one", which is what the
        # ledger line attributes and what the reader is entitled to know
        # before arguing with the number.
        f"{prefix}_ridge": (
            None if bridge.ridge is None else float(bridge.ridge)),
    }


def _terms_descriptor(terms) -> list:
    """One side of a sieve design, as the envelope carries it.

    Plain lists and dicts of primitives: this travels both as a derivation
    step's input and as an extension block, and the two consumers agree on
    nothing except JSON.
    """
    return [
        [
            {
                "variable": factor.variable.predicate,
                "basis": str(factor.basis),
                "dimension": int(factor.dimension),
            }
            for factor in term.factors
        ]
        for term in terms
    ]


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
    if strategy == "joint_nde_nie":
        return (
            "vanderweele_vansteelandt_2014_joint_natural_effect_conditions",
            "sequential_ignorability_treatment_and_mediator_set",
            "no_confounder_of_mediatorset_outcome_affected_by_treatment_outside_the_set",
            "consistency_of_potential_outcomes",
        )
    if strategy == "joint_cde":
        return (
            "adjustment_set_blocks_mediatorset_outcome_backdoor_given_treatment",
            "controlled_direct_effect_holds_mediator_set_at_a_reference_level",
            "consistency_of_potential_outcomes",
        )
    return ()


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


def _a_given_holding_an_end(
    stmt: QueryStatement, kind: QueryKind,
) -> QueryResult | None:
    """The refusal of a question that conditions on its own treatment or
    outcome, or ``None``.

    Asked before any route by both spellings of the estimand, so an effect
    query and an identify query asking the same thing are refused the same
    way (:func:`~themis.types.ends_the_given_holds`).
    """
    held = ends_the_given_holds(stmt.query)
    if not held:
        return None
    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=kind,
        query_id=stmt.id,
        missing_information=(
            gaps.missing(
                kind=MissingKind.STRUCTURE,
                subject=f"{kind.value}_given",
                priority=Priority.HIGH,
                need=gaps.Need.GIVEN_HOLDS_THE_TREATMENT_OR_OUTCOME,
                atoms=", ".join(_atom_to_str(atom) for atom in held),
            ),
        ),
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
        atom for atom in atoms_the_graph_is_asked_about(q)
        if atom not in graph
    ]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.IDENTIFY,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(atom),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.QUERY,
                    atom=_atom_to_str(atom),
                )
                for atom in missing_atoms
            ),
        )

    refused = _a_given_holding_an_end(stmt, QueryKind.IDENTIFY)
    if refused is not None:
        return refused

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
    # One name for the engine verdict, two shapes behind it: the
    # conditional query's IDC result and the unconditional query's ID
    # result. Everything read off it below (``identifiable``, ``hedge``)
    # is what the two shapes share.
    engine: "c_factor.IdcResult | c_factor.TianResult"
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
            gaps.missing(
                kind=MissingKind.STRUCTURE,
                priority=Priority.HIGH,
                need=gaps.Need.NO_C_FACTOR_WITNESS,
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

    annotation = _recognize_identification_pattern(
        graph, bidirected,
        x=q.intervention.atom, y=q.target, given=q.given,
        is_fraction=getattr(engine, "is_fraction", False),
    )
    ext = dict(result.extensions or {})
    ext[blocks.Block.IDENTIFICATION] = annotation
    return _replace(result, extensions=ext)


def _recognize_identification_pattern(
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]",
    *,
    x: Atom,
    y: Atom,
    given: tuple[Atom, ...] = (),
    is_fraction: bool = False,
) -> dict:
    """Recognize the identification PATTERN for the graph-level annotation:
    which classic structure the graph exhibits and the set a human reads
    off it ("control for W" / "the mediator is M"). The emitted formula is
    the canonical c-factor regardless — this only labels it for the human.

    Written over atoms rather than over a query object, because both query
    shapes need it: an identify query names the pattern beside its
    formula, and an effect query — the one that returns a number — needs
    the same sentence beside the number. Taking ``IdentifyQuery`` is what
    kept it on one path.
    """
    bi = bidirected or None
    annotation: dict
    adjustment = structural_solver.minimal_adjustment_sets(
        graph, x, y, given=given, bidirected=bi,
    )
    # A front door is a property of the GRAPH, and the label says which
    # structure the reader is looking at. It used to be withheld whenever
    # the query conditioned — on the ground that P(Y|do(X), Z=z) is not the
    # plain front-door estimand, which is true and is about the ESTIMAND —
    # and the annotation fell through to ``c_factor``, the engine's name.
    # So a reader whose graph had a front door through M, and who asked a
    # conditional question about it, was shown no structure at all.
    #
    # The back-door label was never withheld that way: the search above
    # takes ``given`` and answers for it. The asymmetry was not a judgement
    # about the two structures but about the two SIGNATURES — this search
    # has no ``given`` parameter — and a label is not the identification
    # verdict, which the ID/IDC engine settles either way.
    #
    # Both facts are said instead: the pattern, and ``conditioned_on``
    # below. ``q.given`` stays out of ``covariate_set``, which is the
    # distinction the withholding was protecting — the QUESTION's
    # conditioning and an adjustment covariate read alike and mean opposite
    # things on a collider, and they remain two keys.
    front = structural_solver.generalized_front_door_sets(
        graph, x, y, bidirected=bi,
    )
    if adjustment:
        chosen = min(adjustment, key=len)
        annotation = {
            "pattern": "backdoor",
            "adjustment_set": sorted(_atom_to_str(a) for a in chosen),
        }
    elif front:
        # Sorted smallest-first by (mediators, covariates), so the first
        # is the one a human reads with the least held.
        fd = front[0]
        annotation = {
            "pattern": "front_door",
            "mediator_set": sorted(_atom_to_str(a) for a in fd.mediators),
        }
        if fd.covariates:
            annotation["covariate_set"] = sorted(
                _atom_to_str(a) for a in fd.covariates)
    else:
        annotation = {"pattern": "c_factor"}

    # Conditional estimand P(Y | do(X), Z): the conditioning is PART of
    # the question (e.g. conditioning on a collider) and the formula is
    # the IDC ratio — not a plain "adjust and done". Surface it so the
    # human-facing one-liner isn't lossy: "backdoor, control for {a}"
    # alone would silently drop the Z-conditioning.
    if given:
        annotation["conditioned_on"] = sorted(_atom_to_str(a) for a in given)
        if is_fraction:
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
        blocks.Block.IV_IDENTIFICATION: {
            "strategy": "iv",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
            "required_assumption": language.state(
                Premise.MONOTONICITY_OR_LINEARITY),
            "alternatives_count": len(iv_candidates),
        },
        # Unified graph-level annotation (the human surface), parallel to
        # the backdoor / front-door / c_factor patterns the engine emits.
        # IV is the assumption-laden escalation: the pattern names the
        # instrument and flags that point identification needs an extra
        # assumption — so a renderer keying off extensions["identification"]
        # has a complete story for IV too.
        blocks.Block.IDENTIFICATION: {
            "pattern": "instrumental_variable",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
            "required_assumption": language.state(
                Premise.MONOTONICITY_OR_LINEARITY),
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


def _a_decomposition_within_a_moved_stratum(
    stmt: QueryStatement, q: EffectQuery, moved: "frozenset[Atom]",
    channel: str,
) -> QueryResult:
    """The refusal of direct and indirect effects asked within a stratum
    the treatment moves (``stratum_moved`` on the identifier's result).

    Which people fall in such a stratum depends on the value X is set to,
    so it holds no one population whose effect could be decomposed, and
    no graph identifies a decomposition of it or fails to: no
    ``structural_result``, as for the refusal given before any route.
    """
    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        missing_information=(
            gaps.missing(
                kind=MissingKind.STRUCTURE,
                channel=channel,
                priority=Priority.HIGH,
                need=gaps.Need.DECOMPOSITION_WITHIN_A_STRATUM_THE_TREATMENT_MOVES,
                atoms=", ".join(dict.fromkeys(
                    _atom_to_str(v.atom) for v in q.given if v.atom in moved)),
            ),
        ),
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
        graph, x, y, m, given=tuple(v.atom for v in q.given),
        bidirected=bidirected or None,
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
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.MEDIATOR_OFF_THE_DIRECTED_PATHS,
                ),
            ),
            extensions={
                blocks.Block.MEDIATION_DECOMPOSITION: {
                    "mediator": _atom_to_str(m),
                    "mediator_valid": False,
                    "nde_nie": nde_nie_info,
                    "cde": cde_info,
                }
            },
        )
    if mediation.stratum_moved:
        return _a_decomposition_within_a_moved_stratum(
            stmt, q, mediation.stratum_moved, "mediation")

    # Three-step derivation:
    #   s1: mediation_nde_nie_check — four-condition check for NDE/NIE
    #   s2: mediation_cde_check     — backdoor check for CDE
    #   s3: identify_via_mediation  — decomposition decision + strategy
    derivation: tuple[DerivationStep, ...] = (
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
        blocks.Block.MEDIATION_DECOMPOSITION: {
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
        evaluation_step_id = "s4"
        numeric_block, numeric_step = _evaluate_mediation_numerically(
            target=q.target,
            x_atom=x,
            x_treated=x_treated_value,
            x_control=x_control_value,
            mediators=(m,),
            theta=theta,
            nde_nie_adj=nde_nie_adj,
            cde_adj=cde_adj,
            observed=q.given,
            step_id=evaluation_step_id,
            graph=graph,
            bidirected=bidirected,
        )
        if numeric_block is not None:
            extensions[blocks.Block.MEDIATION_DECOMPOSITION]["numeric"] = numeric_block
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
                        inputs={"evaluation": StepRef(step_id=evaluation_step_id)},
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


def _dispatch_mediation_joint(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> QueryResult:
    """Joint multi-mediator identification — VanderWeele-Vansteelandt 2014.

    Invoked from ``_dispatch_effect`` whenever ``q.mediators`` is non-empty
    (a block of one included; the set check reduces to the classical
    single-mediator one there).
    Runs the block NDE/NIE four-condition check over the mediator SET via
    ``structural_solver.mediation_sets_joint`` and packages the result
    with ``extensions.mediation_joint_decomposition``.

    Identification AND, on a boolean treatment, numeric evaluation against
    theta — the same ``_evaluate_mediation_numerically`` the single-mediator
    path uses, called with the whole block instead of one atom. No joint
    mediator distribution has to be declared: the block's law is expanded by
    the chain rule, which is an identity, and the numeric layer's
    graph-guarded reduction resolves each factor against whatever CPTs the
    user did declare. A mediator block therefore answers with a number
    exactly where a single mediator would, which is the parity this shares
    with the DATA end (``themis.estimate`` → ``estimate_mediation_joint``).

    The path-SPECIFIC split through an individual mediator remains out of
    scope (recanting-witness non-identifiability).
    """
    x = q.intervention.atom
    y = q.target.atom
    ms = frozenset(q.mediators)

    mediation = structural_solver.mediation_sets_joint(
        graph, x, y, ms, given=tuple(v.atom for v in q.given),
        bidirected=bidirected or None,
    )

    nde_nie_info = {
        "identifiable": mediation.nde_nie.identifiable,
        "adjustment": sorted(
            _atom_to_str(a) for a in mediation.nde_nie.adjustment
        ),
        "failed_condition": mediation.nde_nie.failed_condition,
        "assumptions": list(
            _structural_mediation_assumptions("joint_nde_nie")
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
            _structural_mediation_assumptions("joint_cde")
            if mediation.cde.identifiable else ()
        ),
    }
    mediators_str = sorted(_atom_to_str(a) for a in ms)

    if not mediation.mediator_set_valid:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.MEDIATOR_SET_OFF_THE_DIRECTED_PATHS,
                ),
            ),
            extensions={
                blocks.Block.MEDIATION_JOINT_DECOMPOSITION: {
                    "mediators": mediators_str,
                    "mediator_set_valid": False,
                    "nde_nie": nde_nie_info,
                    "cde": cde_info,
                }
            },
        )
    if mediation.stratum_moved:
        return _a_decomposition_within_a_moved_stratum(
            stmt, q, mediation.stratum_moved, "mediation_joint")

    any_identifiable = (
        mediation.nde_nie.identifiable or mediation.cde.identifiable
    )

    # Three-step derivation (mirrors the single-mediator mediation path,
    # which independently checks NDE/NIE and CDE):
    #   s1: mediation_nde_nie_joint_check — block four-condition check
    #   s2: mediation_cde_joint_check     — back-door check for CDE-for-a-set
    #   s3: identify_via_mediation_joint  — decomposition decision (either)
    derivation: tuple[DerivationStep, ...] = (
        DerivationStep(
            rule="mediation_nde_nie_joint_check",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "mediators": ms,
                "adjustment": mediation.nde_nie.adjustment,
            },
            output=mediation.nde_nie.identifiable,
            step_id="s1",
        ),
        DerivationStep(
            rule="mediation_cde_joint_check",
            inputs={
                "graph": graph,
                "x": x,
                "y": y,
                "mediators": ms,
                "adjustment": mediation.cde.adjustment,
            },
            output=mediation.cde.identifiable,
            step_id="s2",
        ),
        DerivationStep(
            rule="identify_via_mediation_joint",
            inputs={
                "nde_nie": StepRef(step_id="s1"),
                "cde": StepRef(step_id="s2"),
            },
            output=StructuralResult(value=any_identifiable),
            step_id="s3",
        ),
    )

    strategy = (
        "nde_nie+cde"
        if (mediation.nde_nie.identifiable and mediation.cde.identifiable)
        else "nde_nie" if mediation.nde_nie.identifiable
        else "cde" if mediation.cde.identifiable
        else "none"
    )
    extensions = {
        blocks.Block.MEDIATION_JOINT_DECOMPOSITION: {
            "mediators": mediators_str,
            "mediator_set_valid": True,
            "nde_nie": nde_nie_info,
            "cde": cde_info,
            "strategy": strategy,
        }
    }

    # Numeric evaluation against theta — the single-mediator path's gate and
    # closure, applied to the block. Boolean treatment only (a contrast has to
    # be well defined before NDE/NIE mean anything); non-boolean stays
    # STRUCTURALLY_SOLVED exactly as the single-mediator path does.
    status = ResultStatus.STRUCTURALLY_SOLVED
    numeric_result: NumericResult | None = None

    x_treated_value = q.intervention.value
    if isinstance(x_treated_value, bool) and any_identifiable:
        block = _mediator_block_order(graph, tuple(ms))
        nde_nie_adj = (
            tuple(sorted(mediation.nde_nie.adjustment, key=_atom_to_str))
            if mediation.nde_nie.identifiable else None
        )
        cde_adj = (
            tuple(sorted(mediation.cde.adjustment, key=_atom_to_str))
            if mediation.cde.identifiable else None
        )
        evaluation_step_id = "s4"
        numeric_block, numeric_step = _evaluate_mediation_numerically(
            target=q.target,
            x_atom=x,
            x_treated=x_treated_value,
            x_control=not x_treated_value,
            mediators=block,
            theta=theta,
            nde_nie_adj=nde_nie_adj,
            cde_adj=cde_adj,
            observed=q.given,
            step_id=evaluation_step_id,
            graph=graph,
            bidirected=bidirected,
        )
        if numeric_block is not None:
            extensions[blocks.Block.MEDIATION_JOINT_DECOMPOSITION]["numeric"] = numeric_block
            te = numeric_block.get("te")
            if te is not None and numeric_step is not None:
                # Same closure invariant as the single-mediator path: promote
                # to NUMERICALLY_SOLVED only when the total effect closed, so
                # a numeric_result always terminates a numeric derivation.
                # Partial cases (CDE-only, or NDE/NIE InsufficientTheta)
                # surface in extensions but keep the 3-step identification
                # derivation as the verifier trail.
                status = ResultStatus.NUMERICALLY_SOLVED
                numeric_result = NumericResult(value=te)
                derivation = derivation + (
                    numeric_step,
                    DerivationStep(
                        rule="numeric_result",
                        inputs={"evaluation": StepRef(step_id=evaluation_step_id)},
                        output=numeric_result,
                        step_id="s5",
                    ),
                )

    return QueryResult(
        status=status,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=StructuralResult(value=any_identifiable),
        numeric_result=numeric_result,
        derivation=derivation,
        extensions=extensions,
    )


# Cap on the number of CDE reference points enumerated for a mediator
# block. The reference grid is the Cartesian product of the mediators'
# theta domains, so it grows multiplicatively; past this many combinations
# the CDE branch reports ``too_many_reference_points`` instead of spending
# unbounded evaluation on a table nobody will read. NDE/NIE is unaffected
# (it marginalises the block rather than enumerating references).
_CDE_REFERENCE_POINT_CAP = 16


def _mediator_block_order(
    graph: nx.DiGraph, mediators: "tuple[Atom, ...]"
) -> "tuple[Atom, ...]":
    """Order a mediator block for the chain-rule factorisation of its
    joint law P(M1..Mk | X, W) = ∏_j P(Mj | M_{<j}, X, W).

    The product is order-invariant mathematically, but the order decides
    WHICH conditionals get demanded of theta. Topological order w.r.t.
    the declared graph makes each factor run WITH the structural parent
    relationships (so a chained M1 → M2 asks for P(M2|M1, ...), the CPT
    that graph actually names) — the same convention ``adjustment_set``
    already follows. Ties break on the atom string so the order is
    deterministic and the verifier can re-derive it independently.
    """
    ms = set(mediators)
    order: list[Atom] = []
    try:
        for node in nx.lexicographical_topological_sort(graph, key=_atom_to_str):
            if node in ms:
                order.append(node)
    except (nx.NetworkXUnfeasible, nx.NetworkXError):
        order = []
    if len(order) != len(ms):
        # Cyclic graph, or a mediator absent from it — fall back to a
        # deterministic name order rather than an arbitrary one.
        order = sorted(ms, key=_atom_to_str)
    return tuple(order)


def _mediator_reference_key(combo: tuple) -> str:
    """Canonical key for one CDE reference point of a mediator block.

    Values joined with ``|`` in block order. For a single mediator this
    is a bare ``str(value)``, so the classical per-mediator-value CDE
    table keeps exactly the keys it always had.
    """
    return "|".join(str(v) for v in combo)


def _mediator_reference_points(
    mediators: "tuple[Atom, ...]", theta: Theta
) -> "tuple[tuple, ...]":
    """The CDE reference grid: the Cartesian product of each mediator's
    theta domain, in block order."""
    from itertools import product
    return tuple(product(*(theta.domain_of(m) for m in mediators)))


def _evaluate_mediation_numerically(
    *,
    target: ValuedAtom,
    x_atom: Atom,
    x_treated: bool,
    x_control: bool,
    mediators: "tuple[Atom, ...]",
    theta: Theta,
    nde_nie_adj: "tuple[Atom, ...] | None",
    cde_adj: "tuple[Atom, ...] | None",
    observed: tuple[ValuedAtom, ...],
    step_id: str,
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> "tuple[dict | None, DerivationStep | None]":
    """v0.1.4 Fix 1 helper — evaluate mediation g-formulas against theta.

    ``mediators`` is the mediator BLOCK, in chain-rule order (see
    ``_mediator_block_order``). A single-element block is the classical
    Pearl 2001 single-mediator case and evaluates the identical formulas;
    a longer block is the VanderWeele-Vansteelandt 2014 joint natural
    effect through the whole set, which is why this helper serves both
    the single-mediator and the joint dispatch.

    Two independent branches:

    1. NDE/NIE (when ``nde_nie_adj is not None``): build the natural
       and cross-world potential-outcome formulas via
       ``formula_builder.mediation_potential_outcome_formula``, evaluate
       three of them — E[Y(treated)], E[Y(control)], E[Y(treated,
       M(control))] — and derive TE / NDE-at-control / NIE-at-treated.
       The block's joint law is expanded by the chain rule inside the
       formula builder, so no joint mediator distribution has to be
       declared: per-mediator CPTs suffice whenever the graph licenses
       the reduction.
    2. CDE (when ``cde_adj is not None``): for each reference point in
       the Cartesian product of the mediators' theta domains build two
       controlled-outcome formulas via
       ``formula_builder.mediation_controlled_outcome_formula`` and
       subtract to produce CDE(m*), the effect holding the whole block
       fixed. Reference points are keyed by the mediator values joined
       with ``|`` in block order (a bare ``str(value)`` for k=1).

    Each branch's failure (InsufficientTheta on any constituent formula
    evaluation) is independent — a partial result records whichever
    branch succeeded plus an ``insufficient_theta`` note on the branch
    that failed. Returns ``(None, None)`` only if no branch was even
    attempted (both adjustments None — caller's gate should prevent
    that).

    ``graph`` / ``bidirected`` are threaded into every evaluation so the
    numeric layer's marginal-independence fallback runs under its
    d-separation guard. Without them the fallback trusts a declared
    marginal P(Mj | X, W) in place of the demanded P(Mj | M_<j, X, W) —
    correct when the graph makes the mediators conditionally independent,
    a WRONG number when it does not (a chained block M1 → M2 is exactly
    such a graph, and is a case the block identification supports). With
    them, an unlicensed substitution surfaces as insufficient_theta
    instead of a plausible answer.
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
                mediators=mediators,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            f_control = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=control_va,
                intervention_inner=control_va,
                mediators=mediators,
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
                mediators=mediators,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            f_cross_control_outer = formula_builder.mediation_potential_outcome_formula(
                target=target,
                intervention_outer=control_va,
                intervention_inner=treated_va,
                mediators=mediators,
                adjustment_set=nde_nie_adj,
                observed=observed,
            )
            e_y_treated = numeric_estimator.estimate_formula(
                f_treated, theta, graph=graph, bidirected=bidirected
            )
            e_y_control = numeric_estimator.estimate_formula(
                f_control, theta, graph=graph, bidirected=bidirected
            )
            e_y_cross_treated_outer = numeric_estimator.estimate_formula(
                f_cross_treated_outer, theta, graph=graph, bidirected=bidirected
            )
            e_y_cross_control_outer = numeric_estimator.estimate_formula(
                f_cross_control_outer, theta, graph=graph, bidirected=bidirected
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
            # A status block carries the keys of the shape it is in — the
            # grid-cap shape has no missing key at all, so this one says which
            # key is missing by naming it and says there is none by leaving it
            # out. Writing null here would be a third spelling of the second.
            numeric["nde_nie_status"] = {
                "status": "insufficient_theta",
                **_theta_shortfall(ite),
            }
            if ite.missing_key:
                numeric["nde_nie_status"]["missing_key"] = (
                    format_probability_key(ite.missing_key))

    if cde_adj is not None:
        reference_points = _mediator_reference_points(mediators, theta)
        cde_per_m: dict = {}
        cde_failure = None
        if len(reference_points) > _CDE_REFERENCE_POINT_CAP:
            cde_failure = {
                "status": "too_many_reference_points",
                "reference_point_count": len(reference_points),
                "cap": _CDE_REFERENCE_POINT_CAP,
            }
            reference_points = ()
        for combo in reference_points:
            m_vas = tuple(
                ValuedAtom(atom=m_atom, value=m_val)
                for m_atom, m_val in zip(mediators, combo)
            )
            m_key = _mediator_reference_key(combo)
            try:
                f_treated_m = formula_builder.mediation_controlled_outcome_formula(
                    target=target,
                    intervention=treated_va,
                    mediators=m_vas,
                    adjustment_set=cde_adj,
                    observed=observed,
                )
                f_control_m = formula_builder.mediation_controlled_outcome_formula(
                    target=target,
                    intervention=control_va,
                    mediators=m_vas,
                    adjustment_set=cde_adj,
                    observed=observed,
                )
                cde_treated = numeric_estimator.estimate_formula(
                    f_treated_m, theta, graph=graph, bidirected=bidirected
                )
                cde_control = numeric_estimator.estimate_formula(
                    f_control_m, theta, graph=graph, bidirected=bidirected
                )
                cde_per_m[m_key] = cde_treated - cde_control
            except InsufficientTheta as ite:
                cde_failure = {
                    "status": "insufficient_theta",
                    "mediator_value": m_key,
                    **_theta_shortfall(ite),
                }
                if ite.missing_key:
                    cde_failure["missing_key"] = format_probability_key(
                        ite.missing_key)
                break
        if cde_per_m:
            numeric["cde"] = cde_per_m
        if cde_failure is not None:
            numeric["cde_status"] = cde_failure

    if not numeric:
        return None, None

    # Only include adjustments that were used. Serializer would choke
    # on None values; the absence of a key tells the verifier that
    # strategy didn't run. Mediator domains are derived by the verifier
    # from its own ctx.theta rather than being shipped in inputs (saves
    # a serialization shape and avoids drift if theta domains evolve).
    #
    # ``mediators`` ships the ORDERED block (atom_tuple round-trips order)
    # because the chain-rule factorisation is written against it. The
    # verifier re-derives the order from the graph and checks the block
    # against the query's own mediator set, so a producer that silently
    # dropped or reordered a mediator cannot pass off the resulting
    # (different, wrong) natural effect as the declared one.
    inputs: dict = {
        "target": target,
        "intervention_treated": treated_va,
        "intervention_control": control_va,
        "mediators": mediators,
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
    derivation = ()
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


def _missing_parameter_from_key(
    key: ProbabilityKey | None,
    /,
    *,
    need: gaps.Need,
    **details,
) -> MissingItem:
    """Build a MissingItem that points at the exact conditional
    probability the evaluator could not resolve.

    ``need`` has no default. A lookup that failed because theta is short
    of an entry and one that failed because theta contradicts the
    declared graph want opposite repairs — supply the conditional versus
    fix the graph — and only the caller holding the failure knows which
    it has. A default would let the second silently arrive dressed as
    the first, which is how the report came to read the difference off
    a substring of the reason text. The gap follows from the species, so
    the two can no longer be passed apart and disagree.

    The key also says what measuring would settle the item — these
    variables, in this population — so the item carries that rather than
    only the rendered ``P(...)``. It is what lets a later pass holding a
    DataFrame decide whether the sample it was handed answers this ask,
    instead of taking the rendered name back apart.

    The skeleton is the same handover for the pass that has to state the
    ask rather than match it: the statement that would settle it, ready
    to paste back. It is attached here, at the one place a parameter ask
    is built, because coverage is then a property of the constructor
    rather than of every caller downstream remembering to carry a map.
    """
    if key is None:
        return gaps.missing(
            kind=MissingKind.PARAMETER,
            priority=Priority.HIGH,
            need=need,
            **details,
        )
    return gaps.missing(
        kind=MissingKind.PARAMETER,
        subject=format_probability_key(key),
        priority=Priority.HIGH,
        need=need,
        observable=Observable(
            variables=tuple(sorted(
                {key.target_atom.predicate}
                | {atom.predicate for atom, _ in key.given}
            )),
            population=key.population,
        ),
        skeleton=_skeleton_for_parameter(key),
        **details,
    )


def _missing_parameter_from_theta(exc: InsufficientTheta) -> MissingItem:
    """The same, for the failure the evaluator raises.

    One line, and it is here rather than inlined at each of the four
    ``except`` clauses because what it does is exactly the handover the
    exception exists for: the species and the occasion, unopened.
    """
    return _missing_parameter_from_key(
        exc.missing_key, need=exc.need, **exc.details)


def _theta_shortfall(exc: InsufficientTheta) -> dict:
    """The same handover, for the block that is not a missing item.

    The mediation arms report a shortfall as a status block rather than
    an ask, and the block used to carry the exception's sentence. It
    carries the same three fields the ask does — the species and the two
    halves of the occasion — because the surface assembling them is the
    same surface, and one exception saying two different things to two
    readers is what this replaced.
    """
    return gaps.fields(exc.need, **exc.details)


def _atom_to_json(atom: Atom) -> dict:
    """Render an Atom as the same JSON shape the kernel_ast schema uses
    for ``atom`` — so a skeleton is paste-ready."""
    d: dict[str, object] = {
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
    CPT entry. The reader fills ``value`` and optional annotations.

    Called from :func:`_missing_parameter_from_key` and nowhere else, so
    that an ask and the statement that would settle it are one object
    from the moment either exists. They were two — a tuple of items and a
    map keyed by each item's rendered name — and the pusher put them back
    together by looking the name up, which is the identity the name was
    split apart to stop being.
    """
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


@dataclass(frozen=True)
class ObservationalJoint:
    """The recovered cells, or the gap that stands in their place.

    ``cells`` is None exactly when ``missing`` is non-empty: a producer
    either fills the four cells and reports nothing missing, or reports
    what it lacked and fills nothing. Callers guard on ``cells``, which is
    the thing they go on to read — guarding on ``missing`` instead tests
    the same fact one indirection away and leaves the cells they then
    index unaccounted for.

    The two ways of breaking it are refused here rather than left to the
    producers to remember, because each turns an incomplete recovery into
    a report that does not admit to being one. No cells and nothing named
    reaches the reader as a needs_investigation that asks for more data
    without saying which — told to go and measure, handed no name. Cells
    beside a non-empty ``missing`` is the mirror: the door computes an
    answer over the cells and drops the shortfall on the floor, because
    on that branch nobody reads ``missing`` again. Refusing both at
    construction keeps the failure at the producer, which is the last
    place where what is missing still has a name.
    """

    cells: dict[tuple[bool, bool], float] | None
    missing: tuple[MissingItem, ...]
    ancestral: AncestralJoint | None

    def __post_init__(self) -> None:
        if (self.cells is None) != bool(self.missing):
            raise ValueError(
                "ObservationalJoint carries either four cells and nothing "
                "missing, or no cells and the names of what it lacked; got "
                f"cells={'absent' if self.cells is None else 'present'} "
                f"beside {len(self.missing)} missing item(s)"
            )


def _refused(stmt, query_kind: QueryKind, failure: dict) -> QueryResult:
    """A result whose whole content is one refusal.

    Identification returns a result rather than raising, so it is the layer
    that has to name a status — and each site named one of its own until
    #434. A site names the exception it catches, and a catch site catches a
    FAMILY: ``CounterfactualBoundsError`` spans nine species over four
    kinds, and the ``outside_language`` both handlers wrote is true of one
    of the nine. The kind knows, and says so once
    (:attr:`refusals.Kind.outcome`); this is the one call that reads it.
    """
    return QueryResult(
        status=refusals.outcome(failure),
        query_kind=query_kind,
        query_id=stmt.id,
        estimator_failure=failure,
    )


def _observational_joint_xy(
    theta: Theta,
    graph: nx.DiGraph,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> ObservationalJoint:
    """The four ``P(X=x, Y=y)`` cells from theta, for every door that wants them.

    One recovery, because the counterfactual cell and the three probabilities
    of causation want the same four numbers off the same theta and the same
    graph. Two recoveries of one quantity are two places to widen every time
    either of them is widened, and only one of them gets widened.

    Ancestral factorization first: it is the graph's own account of the
    distribution, and it reaches the measured-confounder shape (Z→X, Z→Y,
    X→Y) where ``P(X)`` and ``P(Y|X)`` are not in theta at all and have to be
    summed out of it. The local chain rule second, for the
    confounded-but-experimental case that supplies those two marginals
    directly and nothing upstream of them.

    Which route reports a shortfall is NOT the order they run in. The graph's
    own account being incomplete is the model being incomplete, so its
    missing factors are the gap. When a bidirected edge has widened the
    conditioning set, the wider route is the one that would give the MOST,
    and what it lacks is not what the reader must supply to reach an answer —
    it is what would make the answer sharper. The gap names the least that
    reaches an answer; the enrichment is named beside it by the caller that
    knows what it would have bought.

    Missing entries surface as ordinary PARAMETER gaps so the existing
    fill-back workflow can recover the query.
    """
    for atom in (x_atom, y_atom):
        domain = set(theta.domain_of(atom))
        if not domain or not domain <= {False, True}:
            raise counterfactual.CounterfactualBoundsError(
                Refusal.COUNTERFACTUAL_CELL_NOT_BINARY,
                label=atom.predicate, given=sorted(domain, key=str),
            )

    recovery = _ancestral_joint(
        graph, theta, x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
    )
    if recovery.joint is not None:
        marginal = recovery.joint.marginal((x_atom, y_atom))
        return ObservationalJoint(
            {
                (x_val, y_val): marginal.get((x_val, y_val), 0.0)
                for x_val in (False, True)
                for y_val in (False, True)
            },
            (), recovery.joint,
        )
    if recovery.missing and recovery.licensed:
        return ObservationalJoint(None, recovery.missing, None)

    missing: list[MissingItem] = []
    cells: dict[tuple[bool, bool], float] = {}
    for x_val in (False, True):
        for y_val in (False, True):
            try:
                cells[(x_val, y_val)] = _estimate_counterfactual_joint_cell(
                    theta,
                    x_atom=x_atom,
                    x_val=x_val,
                    y_atom=y_atom,
                    y_val=y_val,
                )
            except InsufficientTheta as exc:
                item = _missing_parameter_from_theta(exc)
                if item.name in {m.name for m in missing}:
                    continue
                missing.append(item)
    if missing:
        return ObservationalJoint(None, tuple(missing), None)
    return ObservationalJoint(cells, (), None)


class AncestralJoint(NamedTuple):
    """The observational joint over the directed ancestral subgraph of {X, Y}.

    Kept whole rather than reduced where it is recovered. The cell wants
    ``P(X, Y)``; the instrument route wants ``P(X, Y | Z)``; a recovery that
    decides in advance which of the two is wanted is a recovery the other
    caller has to write for itself.
    """

    topo: tuple[Atom, ...]
    joint: dict[tuple, float]
    licensed_to_drop_non_parents: bool

    def marginal(self, atoms: tuple[Atom, ...]) -> dict[tuple, float]:
        """Sum the joint down to ``atoms``, keyed in the order given."""
        positions = tuple(self.topo.index(atom) for atom in atoms)
        out: dict[tuple, float] = {}
        for row, prob in self.joint.items():
            key = tuple(row[i] for i in positions)
            out[key] = out.get(key, 0.0) + prob
        return out


class _AncestralRecovery(NamedTuple):
    joint: AncestralJoint | None
    missing: tuple[MissingItem, ...]
    licensed: bool


def _ancestral_joint(
    graph: nx.DiGraph,
    theta: Theta,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
) -> _AncestralRecovery:
    """Recover the joint over the ancestral subgraph of {X, Y} from theta.

    Instead of accepting only handcrafted local factorizations such as
    ``P(X)·P(Y|X)``, this uses the DAG + CPT semantics directly, at whatever
    conditioning set the graph licenses — see
    :func:`_factorization_conditioning` for why a bidirected edge widens that
    set rather than ending the route.
    """
    ancestral_nodes = (
        nx.ancestors(graph, x_atom)
        | nx.ancestors(graph, y_atom)
        | {x_atom, y_atom}
    )
    licensed = not any(pair & ancestral_nodes for pair in bidirected)
    if not ancestral_nodes:
        return _AncestralRecovery(None, (), licensed)

    subgraph = graph.subgraph(ancestral_nodes).copy()
    topo = tuple(nx.topological_sort(subgraph))
    conditioning = _factorization_conditioning(
        subgraph, topo, licensed_to_drop_non_parents=licensed,
    )
    required_keys = _required_observational_probability_keys(
        topo=topo, theta=theta, conditioning=conditioning,
    )
    missing_keys = tuple(
        key for key in required_keys
        if _recover_boolean_theta_value(theta, key) is None
    )
    if missing_keys:
        missing_items = tuple(
            _missing_parameter_from_key(
                key,
                need=gaps.Need.COUNTERFACTUAL_BOUND_NEEDS_ENTRY,
                key=format_probability_key(key),
            )
            for key in missing_keys
        )
        return _AncestralRecovery(None, missing_items, licensed)

    joint: dict[tuple, float] = {}
    for assignment in _ancestral_assignments(topo, theta):
        prob = 1.0
        for atom in topo:
            key = _assignment_probability_key(
                atom, assignment, conditioning[atom],
            )
            value = _recover_boolean_theta_value(theta, key)
            if value is None:
                raise AssertionError(
                    "missing key survived required-key precheck in "
                    "_ancestral_joint"
                )
            prob *= value
        row = tuple(assignment[atom] for atom in topo)
        joint[row] = joint.get(row, 0.0) + prob
    return _AncestralRecovery(
        AncestralJoint(topo, joint, licensed), (), licensed,
    )


def _factorization_conditioning(
    graph: nx.DiGraph,
    topo: tuple[Atom, ...],
    *,
    licensed_to_drop_non_parents: bool,
) -> dict[Atom, tuple[Atom, ...]]:
    """What each atom's chain-rule factor conditions on.

    The chain rule in topological order — ``P(V₁…Vₙ) = ∏ P(Vᵢ | V₁…Vᵢ₋₁)`` —
    holds for every joint distribution whatever the graph says. It is
    arithmetic, not a causal assumption, and no edge can make it false. What
    the GRAPH contributes is a LICENCE TO DROP the non-parents out of each
    prefix: where every common cause is measured, a variable is independent
    of its non-descendants given its parents.

    A bidirected edge withdraws that licence. A withdrawn licence to drop
    terms leaves the factorization standing with more terms in it, which is
    not the same thing as having no factorization — and reading it as the
    latter is what left the parameter end unable to recover ``P(X, Y | Z)``
    on exactly the graphs where an instrument is the only thing that can
    answer, since exclusion is what keeps ``Z`` out of ``Y``'s parents.
    """
    if licensed_to_drop_non_parents:
        return {atom: tuple(graph.predecessors(atom)) for atom in topo}
    return {atom: topo[:i] for i, atom in enumerate(topo)}


def _required_observational_probability_keys(
    *,
    topo: tuple[Atom, ...],
    theta: Theta,
    conditioning: dict[Atom, tuple[Atom, ...]],
) -> tuple[ProbabilityKey, ...]:
    keys: set[ProbabilityKey] = set()
    for assignment in _ancestral_assignments(topo, theta):
        for atom in topo:
            keys.add(
                _assignment_probability_key(atom, assignment, conditioning[atom])
            )
    return tuple(sorted(keys, key=_probability_key_sort_key))


def _ancestral_assignments(
    topo: tuple[Atom, ...],
    theta: Theta,
) -> "Iterator[dict[Atom, AtomValue]]":
    domains = [_counterfactual_factorization_domain(theta, atom) for atom in topo]
    for values in product(*domains):
        yield dict(zip(topo, values))


def _assignment_probability_key(
    atom: Atom,
    assignment: "Mapping[Atom, AtomValue]",
    conditioning: tuple[Atom, ...],
) -> ProbabilityKey:
    return ProbabilityKey(
        target_atom=atom,
        target_value=assignment[atom],
        given=frozenset(
            (given_atom, assignment[given_atom]) for given_atom in conditioning
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
) -> "tuple[AtomValue, ...]":
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
        need=gaps.Need.COUNTERFACTUAL_BOUND_NEEDS_ENTRY,
        key=format_probability_key(missing_key),
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
    selection_nodes: "tuple[SelectionNode, ...]" = (),
) -> QueryResult:
    """One binary counterfactual cell P(Y_{x'}=y* | X=x [, Y=y]).

    Recovers the observational joint P(X, Y) from theta, obtains the ONE
    interventional risk P(Y=1 | do(x')) the cell depends on — user-supplied
    experimental value, or derived by running the effect identification —
    and hands both to ``counterfactual.counterfactual_cell_interval``, whose
    single linear consistency identity covers every cell. Monotonicity, when
    declared, is an extra constraint that can collapse the interval to a
    point; it is not required to answer.

    There is a SECOND solver, and it is not a weaker version of that one.
    Where the graph carries a bow arc there is no interventional risk to be
    had at all, and an instrument bounds the cell directly over the
    response-type distributions reproducing P(X, Y | Z) — a program that
    consumes no risk. "No risk is obtainable" is therefore a statement about
    one route rather than about the question, which is why it is asked only
    after the identity route has said it cannot, and never before: where a
    back door reaches the arm, the identity rests on assumptions the caller
    already granted and the instrument's three are additional. The data end
    orders the same pair the same way.
    """
    q: CounterfactualQuery = stmt.query  # type: ignore[assignment]

    try:
        recovered = _observational_joint_xy(
            theta, graph,
            x_atom=q.observed.atom,
            y_atom=q.counterfactual_target.atom,
            bidirected=bidirected,
        )
    except counterfactual.CounterfactualBoundsError as exc:
        return _refused(stmt, QueryKind.COUNTERFACTUAL, refusals.relayed(
            estimator="counterfactual_identification", exc=exc))
    joint_xy, ancestral = recovered.cells, recovered.ancestral
    if joint_xy is None:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=recovered.missing,
            investigation_requests=investigation_pusher.push(
                recovered.missing
            ),
        )

    # The interventional risk for the counterfactual arm. Fetched only for the
    # arm actually asked about — the other one is information this answer does
    # not depend on, and requiring it would manufacture a gap. Fetched even
    # when monotonicity would pin the cell outright, because with the risk in
    # hand the solver can also detect that the two sources contradict.
    x_obs_value = q.observed.value
    x_cf_value = q.counterfactual_intervention.value
    risk: float | None = None
    risk_provenance = RiskProvenance.NOT_REQUIRED
    arm_missing: tuple[MissingItem, ...] = ()
    if isinstance(x_cf_value, bool) and x_cf_value != x_obs_value:
        supplied = (
            q.experimental_risk_treated if x_cf_value
            else q.experimental_risk_control
        )
        if supplied is not None:
            risk = float(supplied)
            risk_provenance = RiskProvenance.USER_EXPERIMENTAL
        else:
            risk, arm_missing = _derive_interventional_risk_arm(
                stmt, graph, theta,
                q.observed.atom, q.counterfactual_target.atom, x_cf_value,
                bidirected=bidirected, selection_nodes=selection_nodes,
            )
            if risk is not None:
                risk_provenance = RiskProvenance.DERIVED_IDENTIFICATION

    instrument_table: "InstrumentTable | None" = None
    instrument_atom: "Atom | None" = None
    try:
        twin = counterfactual.project_twin_network(graph, bidirected, q)
        interval = counterfactual.counterfactual_cell_interval(
            twin, q, joint_xy, p_y_do_x_cf=risk,
        )
    except counterfactual.InterventionalRiskRequired as need:
        # Neither consistency nor monotonicity determines this cell, and
        # P(Y=1|do(x')) could not be obtained. Before reporting that, ask the
        # instrument: the identity route needs the risk as a scalar, and the
        # response-function polytope needs no risk at all, so "no risk is
        # obtainable" is a statement about one route rather than about the
        # question.
        from ..response_polytope import counterfactual_cell_response_bounds

        route = _instrument_route_from_theta(
            graph, theta, ancestral,
            x_atom=q.observed.atom, y_atom=q.counterfactual_target.atom,
            bidirected=bidirected,
        )
        values, note = _over_the_response_polytope(
            route,
            lambda p_xyz, p_z: {"cell": counterfactual_cell_response_bounds(
                p_xyz, p_z,
                x_observed=int(bool(q.observed.value)),
                x_counterfactual=int(
                    bool(q.counterfactual_intervention.value)),
                y_star=int(bool(q.counterfactual_target.value)),
                factual_y=(
                    None if q.factual_target_known is None
                    else int(bool(q.factual_target_known))
                ),
                monotonicity=(
                    q.assumptions.monotonicity
                    if q.assumptions is not None else None
                ),
            )},
        )
        if values is None:
            # Report the gap that names the remedy rather than the vacuous
            # [0, 1] that would look like an answer.
            escape = gaps.missing(
                kind=MissingKind.ASSUMPTION,
                priority=Priority.HIGH,
                need=gaps.Need.INTERVENTIONAL_RISK_UNAVAILABLE_FOR_CELL,
                arm=need.needed_x_value,
                # A statement goes on the word half and the empty
                # case on the value half, and `halve` reads which
                # off the value: "there is nothing to add" is the
                # same in every language and a note is not.
                note=note or "",
            )
            merged = tuple(arm_missing) + (escape,)
            return QueryResult(
                status=ResultStatus.NEEDS_INVESTIGATION,
                query_kind=QueryKind.COUNTERFACTUAL,
                query_id=stmt.id,
                missing_information=merged,
                # Over the merge, as the causation door does over its own.
                # This carried the requests the sub-dispatch had pushed —
                # from the arm's items alone — so the escape reached the
                # reader as an ask with no entry to act on, on the door
                # whose whole point is to answer where its sibling does.
                investigation_requests=investigation_pusher.push(merged),
            )
        low, high = values["cell"]
        interval = NumericInterval(low=low, high=high)
        instrument_table = route.table
        instrument_atom = route.instrument
        risk_provenance = RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE
    except counterfactual.CounterfactualBoundsError as exc:
        # Its infeasible sibling was caught two lines above this one until
        # #434 and re-encoded as a gap whose ``reason`` was ``str(exc)`` —
        # the species, the occasion and the route out discarded, and a
        # sentence rendered in one language put back on the envelope that
        # #411 had just taken it off. One family, one door.
        return _refused(stmt, QueryKind.COUNTERFACTUAL, refusals.relayed(
            estimator="counterfactual_identification", exc=exc))

    bounded_result = NumericResult(
        value=None,
        interval=NumericInterval(low=interval.low, high=interval.high),
    )
    solved_result = NumericResult(value=interval.low)
    derivation_output = solved_result if interval.low == interval.high else bounded_result
    step_inputs: dict = {
        "graph": graph,
        "interventional_risk_provenance": stamp(
            "counterfactual_cell_bounds", risk_provenance),
    }
    if risk is not None:
        step_inputs["p_y_do_x_cf"] = risk
    if instrument_table is not None and instrument_atom is not None:
        # What the verifier re-solves. The levels travel WITH the table
        # because the table's own shape says nothing about which stratum is
        # which, and a permuted reading re-derives a different interval and
        # calls an honest producer a liar.
        step_inputs["instrument"] = instrument_atom.predicate
        step_inputs["instrument_levels"] = instrument_table.z_levels
        step_inputs["p_xyz"] = instrument_table.p_xyz
        step_inputs["p_z"] = instrument_table.p_z
    derivation = (
        DerivationStep(
            rule="counterfactual_cell_bounds",
            inputs=step_inputs,
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


class InstrumentRoute(NamedTuple):
    """The instrument and the table it conditions, or why there is neither.

    Everything both attribution doors need BEFORE the polytope begins to
    differ between them. What each door does with the table is a different
    objective on it — a cell names one arm and a factual outcome, the three
    probabilities of causation name both arms at once — and that is the whole
    of the difference. Finding the instrument, building its table, and the
    preconditions that make the program solvable are properties of the graph
    and of theta, so they happen here once.

    ``note`` says why there is no table, in the reader's terms, and it is
    present whenever the graph offered an instrument at all: an attempt that
    declines silently is indistinguishable, at every surface, from a graph
    that never had an instrument in it.
    """

    instrument: "Atom | None" = None
    table: "InstrumentTable | None" = None
    note: "language.Statement | None" = None


def _instrument_route_from_theta(
    graph: nx.DiGraph,
    theta: Theta,
    ancestral: "AncestralJoint | None",
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]",
) -> InstrumentRoute:
    """The instrument this graph offers for X→Y, and its table off theta."""
    if ancestral is None:
        return InstrumentRoute()
    z_atom = _instrument_for_theta_cell(
        graph, theta, x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
    )
    if z_atom is None or z_atom not in ancestral.topo:
        return InstrumentRoute()

    table = _instrument_table_from_theta(
        ancestral, x_atom=x_atom, y_atom=y_atom, z_atom=z_atom,
    )
    if table is None:
        return InstrumentRoute(note=language.state(
            Tried.THETA_GIVES_A_LEVEL_NO_MASS,
            instrument=z_atom.predicate))
    return InstrumentRoute(z_atom, table, None)


def _over_the_response_polytope(
    route: InstrumentRoute, solve,
) -> "tuple[dict[str, tuple[float, float]] | None, language.Statement | None]":
    """Run one door's objectives over ``route``'s table.

    ``solve(P, p_z)`` returns that door's named quantities as ``(lower,
    upper)`` pairs — one for a counterfactual cell, three for the
    probabilities of causation. Everything else is here rather than in either
    door, because none of it is about which functional was asked for.

    The consistency identity and Tian-Pearl's closed form both consume the
    interventional risk as a SCALAR, and where the graph carries a bow arc
    there is no scalar to be had. This program is not a fallback for either:
    it asks a different question of the same theta — which values are
    consistent with SOME distribution over response types reproducing
    ``P(X, Y | Z)`` — and needs no interventional risk at all. Reached only
    after the risk-consuming route has said it cannot, which is the order the
    data end uses for the same pair: where a back door reaches the arms, that
    route rests on assumptions the caller has already granted and the
    instrument's three are additional.

    An ``EstimatorFailure`` becomes a note rather than propagating: on these
    doors the instrument was not asked for, it was FOUND, so a finding that
    the found instrument is refuted by theta is a reason the door cannot
    answer, not an error in what the caller wrote.

    An answer that excludes nothing is declined for the same kind of reason.
    Returning it would replace a gap report naming a remedy with something
    shaped like an answer — the trade both doors already refuse when they
    choose the gap over a vacuous [0, 1]. The data end reports the same set
    rather than suppressing it, and that is not a divergence about the
    method: the LP is the same and returns the same numbers. It is a
    difference in what each door has to offer instead, and here a gap naming
    what to go and get beats a set that rules nothing out.
    """
    import numpy as np

    from ..response_polytope import polytope_preconditions

    if route.table is None or route.instrument is None:
        return None, route.note
    name = route.instrument.predicate
    try:
        polytope_preconditions(name, list(route.table.z_levels))
        values = solve(
            np.array(route.table.p_xyz, dtype=float),
            np.array(route.table.p_z, dtype=float),
        )
    except refusals.EstimatorFailure as exc:
        # The refusal goes in a HOLE rather than through ``str(exc)``. A
        # ``Voiced`` already holds the two halves a statement is made of,
        # so restating it here is that split read back rather than a
        # second implementation of it — and ``str(exc)`` renders in the
        # default language, which is how a refusal ended up quoted inside
        # a sentence the reader chose the language of.
        return None, language.state(
            Tried.THE_PROGRAM_DID_NOT_SOLVE,
            instrument=name,
            refusal=language.restate(
                {"token": str(exc.failure_type),
                 "said": exc.said, "words": exc.words},
                refusals.REFUSED))
    if all(low <= 1e-9 and high >= 1.0 - 1e-9 for low, high in values.values()):
        return None, language.state(
            Tried.THE_POLYTOPE_RULES_NOTHING_OUT, instrument=name)
    return values, None


def _instrument_for_theta_cell(
    graph: nx.DiGraph,
    theta: Theta,
    *,
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]",
) -> Atom | None:
    """The one instrument this graph offers for X→Y, or nothing.

    Whether a node is an instrument is
    :func:`structural_solver.unconditional_instruments`, the answer every
    door reads. Whether it has a finite domain to enumerate is a separate
    question with a different authority at each door -- a declared domain
    where the answer is a symbolic expression, the recovered theta where it
    is a table -- so this door asks theta.

    Nothing on a tie, for the reason the effect door refuses one: a graph
    carrying two valid instruments makes the answer depend on which was
    picked, and picking is not something the caller asked for.
    """
    atoms = [
        node for node in structural_solver.unconditional_instruments(
            graph, x_atom, y_atom, bidirected=bidirected)
        if len(set(theta.domain_of(node))) >= 2
    ]
    return atoms[0] if len(atoms) == 1 else None


def _sorted_levels(values) -> list:
    """Level ORDER for the instrument, matching the data end's own rule.

    Position is what the polytope indexes and what the verifier re-reads, so
    the two ends have to agree about which stratum is which or an honest
    answer re-derives as a different one.
    """
    try:
        return sorted(values)
    except TypeError:
        return sorted(values, key=str)


class InstrumentTable(NamedTuple):
    """``P(X, Y | Z)`` and ``P(Z)`` off theta, as the polytope consumes them.

    Plain Python rather than arrays, because this is also what the envelope
    carries and what the verifier re-solves; the levels travel WITH the table
    for the same reason they do on the data end — the table's shape says
    nothing about which stratum is which.
    """

    z_levels: tuple
    p_xyz: tuple
    p_z: tuple


def _instrument_table_from_theta(
    ancestral: AncestralJoint,
    *,
    x_atom: Atom,
    y_atom: Atom,
    z_atom: Atom,
) -> InstrumentTable | None:
    """Reduce the recovered ancestral joint to the instrument's table.

    ``None`` when a stratum of Z carries no mass: ``P(X, Y | Z=z)`` is
    undefined there and the polytope has no table to be fitted to, which is
    the same refusal the data end raises for an unobserved stratum.
    """
    joint = ancestral.marginal((z_atom, x_atom, y_atom))
    z_levels = _sorted_levels({row[0] for row in joint})
    p_z = [
        sum(p for (z_val, _, _), p in joint.items() if z_val == z)
        for z in z_levels
    ]
    if any(mass <= 0.0 for mass in p_z):
        return None
    return InstrumentTable(
        tuple(z_levels),
        tuple(
            tuple(
                tuple(joint.get((z, x_val, y_val), 0.0) / p_z[i]
                      for y_val in (False, True))
                for x_val in (False, True)
            )
            for i, z in enumerate(z_levels)
        ),
        tuple(p_z),
    )


def _poc_quantity(lower: float, upper: float, point: "float | None") -> dict:
    """Serialize one probability-of-causation quantity (PN / PS / PNS).

    ``point`` is null when the quantity is not point-identified (no
    monotonicity), and it is always THERE. This used to omit the key, while
    the data route wrote null into the same field of the same block for the
    same reason: one path, two spellings for one fact, and no reader that
    could tell them apart. Absence would be the weaker of the two anyway —
    it cannot be told from a producer that forgot.
    """
    return {"lower": lower, "upper": upper, "point": point}


def _derive_interventional_risk_arm(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    x_atom: Atom,
    y_atom: Atom,
    x_val: bool,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[SelectionNode, ...]" = (),
) -> "tuple[float | None, tuple[MissingItem, ...]]":
    """Derive ONE interventional risk P(Y=1 | do(X=x_val)) via the existing
    effect identification.

    Split out from ``_derive_interventional_risks`` because a counterfactual
    cell needs only the arm it is actually asking about: fetching the other
    one would manufacture a gap for information the answer does not depend
    on. Returns ``(risk, ())`` on success, ``(None, missing)`` otherwise —
    the items, and not also the requests the sub-dispatch pushed from them,
    because everything the caller needs from a request now rides on the item
    it was pushed from and the caller pushes once, at the end, over the
    merge.
    """
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
        return float(sub.numeric_result.value), ()
    return None, sub.missing_information


def _derive_interventional_risks(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    x_atom: Atom,
    y_atom: Atom,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[SelectionNode, ...]" = (),
) -> "tuple[tuple[float, float] | None, tuple[MissingItem, ...]]":
    """Derive P(Y=1 | do(X=1)) and P(Y=1 | do(X=0)) by running the
    existing effect identification twice.

    Reuses ``_dispatch_effect`` — so the interventional risks inherit the
    full backdoor / front-door / Tian / IV identification cascade for
    free. Returns ``((p1, p0), ())`` on success, or ``(None, missing)`` —
    the same shape as the single-arm helper, so the caller can merge this
    shortfall with the one theta reported instead of returning at
    whichever came first.
    """
    risks: list[float] = []
    merged_missing: list[MissingItem] = []
    for x_val in (True, False):
        risk, arm_missing = _derive_interventional_risk_arm(
            stmt, graph, theta, x_atom, y_atom, x_val,
            bidirected=bidirected, selection_nodes=selection_nodes,
        )
        if risk is not None:
            risks.append(risk)
        else:
            for item in arm_missing:
                if item.name not in {m.name for m in merged_missing}:
                    merged_missing.append(item)
    if len(risks) == 2:
        return (risks[0], risks[1]), ()

    # At least one risk could not be obtained, for one of two reasons that
    # want opposite advice: the graph does not identify the effect (no
    # theta ever will), or it does and theta is short of the distributions
    # it needs. The escape hatch — supply the risks from an experiment —
    # is worth offering either way, but saying "not identifiable" in the
    # second case sends a reader to change a graph that is already fine.
    unidentifiable = any(
        m.gap == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
        for m in merged_missing
    )
    escape = gaps.missing(
        kind=MissingKind.ASSUMPTION,
        priority=Priority.HIGH,
        need=(gaps.Need.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE if unidentifiable
              else gaps.Need.INTERVENTIONAL_RISK_NEEDS_DISTRIBUTIONS),
        # Empty, and filled in later by the caller that asked the
        # instrument — see CAUSATION_RISK_ESCAPE below. Passed here so
        # that the slot is a value the site declares rather than a hole
        # the reader is shown the name of. The caller fills it on the
        # WORD half, which overrides this one for the same hole: the
        # empty case is a value (there is nothing to add, in every
        # language) and the filled case is a sentence.
        note="",
    )
    return None, tuple(merged_missing) + (escape,)




CAUSATION_RISK_ESCAPE = gaps.filed(
    gaps.Need.INTERVENTIONAL_RISK_NOT_IDENTIFIABLE)
"""The gap that stands when no interventional risk is obtainable.

Named because two places need to agree about it: the one that raises it, and
the one that appends what the instrument route found when it was asked
instead. A reader deciding what to go and get needs both sentences, and they
belong on one item rather than two.

Read off the species rather than spelled here, because the site that
raises it no longer spells one either: this is the name that row comes
back with, and a second constant for it is a second thing to keep in
agreement. The other species that site's conditional can pick is filed
under the same name, so either of them names it.
"""


def _causation_gap(
    stmt: QueryStatement,
    *,
    joint_missing: "tuple[MissingItem, ...]",
    risk_missing: "tuple[MissingItem, ...]",
) -> QueryResult:
    """One needs_investigation result for both of the causation inputs.

    Deduplicated by name and pushed once rather than concatenated: the two
    shortfalls overlap (the ancestral factorization and the back-door
    adjustment ask theta for many of the same conditionals), and two
    request tuples would give the reader the same group twice.

    The statements the reader pastes back ride on the items themselves, so
    merging the two sides merges them too. This used to take a third
    argument — the requests the effect dispatch had already pushed — and
    scavenge their skeletons back out by target name, because the items on
    this side had been separated from theirs.
    """
    merged: list[MissingItem] = []
    seen: set[str] = set()
    for item in tuple(joint_missing) + tuple(risk_missing):
        if item.name in seen:
            continue
        seen.add(item.name)
        merged.append(item)

    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.CAUSATION,
        query_id=stmt.id,
        missing_information=tuple(merged),
        investigation_requests=investigation_pusher.push(tuple(merged)),
    )


def _causation_over_the_instrument(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    q: CausationQuery,
    joint: "dict[tuple[bool, bool], float]",
    ancestral: "AncestralJoint | None",
    *,
    risk_missing: "tuple[MissingItem, ...]",
    x_atom: Atom,
    y_atom: Atom,
    bidirected: "frozenset[frozenset[Atom]]",
) -> QueryResult:
    """PN / PS / PNS over the response-type polytope, or the gap that stands.

    Tian-Pearl's closed form consumes both interventional risks as numbers,
    and where the graph carries a bow arc there are none to be had. The three
    quantities are then three linear functionals on the same polytope the
    counterfactual door reads its cell off — PN IS one of that door's cells,
    so a door that refused here while the other answered, on one theta and
    one graph, would be the asymmetry this pair exists to not have.

    When the instrument reaches nothing, what it found is appended to the
    escape rather than dropped: "no risk is obtainable" and "the instrument
    was asked and here is what happened" are two halves of the same answer to
    "what do I go and get".
    """
    from dataclasses import replace

    from ..response_polytope import causation_response_bounds
    from ..ledger import Monotonicity

    route = _instrument_route_from_theta(
        graph, theta, ancestral, x_atom=x_atom, y_atom=y_atom,
        bidirected=bidirected,
    )
    direction = Monotonicity.NON_DECREASING if q.monotonic else None
    values, note = _over_the_response_polytope(
        route,
        lambda p_xyz, p_z: causation_response_bounds(
            p_xyz, p_z, monotonicity=direction,
        ),
    )
    if values is None:
        return _causation_gap(
            stmt,
            joint_missing=(),
            risk_missing=tuple(
                replace(item, words={**item.words, "note": note})
                if note and item.name == CAUSATION_RISK_ESCAPE else item
                for item in risk_missing
            ),
        )

    assert route.instrument is not None and route.table is not None
    licence = stamp(
        "causation_probability_bounds",
        RiskProvenance.INSTRUMENT_RESPONSE_POLYTOPE,
    )
    envelope = {
        "monotonic": q.monotonic,
        "interventional_risk_provenance": licence,
        "instrument": route.instrument.predicate,
        "p_y_do_x1": None,
        "p_y_do_x0": None,
        "observational_joint": {
            "p_x1_y1": joint[(True, True)], "p_x1_y0": joint[(True, False)],
            "p_x0_y1": joint[(False, True)], "p_x0_y0": joint[(False, False)],
        },
        # A point exactly when the identified set collapses to one, which on
        # this route is a property of the program's answer rather than of a
        # second formula: a declared monotonicity restricts the MODEL here,
        # so it narrows the bounds themselves and in practice leaves no
        # point. Same rule as the data end, so the two agree on a degenerate
        # interval instead of one of them calling it a point.
        **{
            name: _poc_quantity(
                low, high, low if abs(high - low) <= 1e-9 else None,
            )
            for name, (low, high) in values.items()
        },
    }
    return QueryResult(
        status=ResultStatus.COUNTERFACTUAL_BOUNDED,
        query_kind=QueryKind.CAUSATION,
        query_id=stmt.id,
        numeric_result=NumericResult(
            value=None,
            interval=NumericInterval(
                low=values["pn"][0], high=values["pn"][1]),
        ),
        derivation=(
            DerivationStep(
                rule="causation_probability_bounds",
                inputs={
                    "cause": x_atom,
                    "effect": y_atom,
                    "p_x1_y1": joint[(True, True)],
                    "p_x1_y0": joint[(True, False)],
                    "p_x0_y1": joint[(False, True)],
                    "p_x0_y0": joint[(False, False)],
                    "monotonic": q.monotonic,
                    "interventional_risk_provenance": licence,
                    "instrument": route.instrument.predicate,
                    "instrument_levels": route.table.z_levels,
                    "p_xyz": route.table.p_xyz,
                    "p_z": route.table.p_z,
                },
                output=envelope,
                step_id="s1",
            ),
        ),
        extensions={blocks.Block.CAUSATION: envelope},
    )


def _dispatch_causation(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    *,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[SelectionNode, ...]" = (),
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
    missing_atoms = [a for a in atoms_the_graph_is_asked_about(q)
                     if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.CAUSATION,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.CAUSATION_QUERY,
                    atom=_atom_to_str(a),
                )
                for a in missing_atoms
            ),
        )

    # 2. PN/PS/PNS are defined for BINARY cause and effect only.
    for atom, role in ((x_atom, "cause"), (y_atom, "effect")):
        domain = set(theta.domain_of(atom))
        if not domain or not domain <= {False, True}:
            return _refused(stmt, QueryKind.CAUSATION, refusals.block(
                estimator="causation_identification",
                # The same species the data end raises for the same
                # reason (estimation.binary_do_risk): one quantity,
                # one refusal, whichever layer reached it first — and
                # so the same sentence, which is the species'. The word
                # this drops is the schematic role; what it keeps is the
                # name the caller gave the column, and that is the half
                # a reader can act on.
                failure_type=Refusal.CAUSE_OR_EFFECT_NOT_BINARY,
                details={"column": atom.predicate,
                         "values": sorted(domain, key=str)},
            ))

    # 3-4. The two inputs Tian-Pearl needs: the observational joint P(X, Y),
    # which comes from theta, and the interventional risks P(Y=1|do(X)),
    # which come from identification. They are independent, so both are
    # obtained before either shortfall is reported.
    #
    # Returning at the first one that failed reported whichever came first
    # and hid the other. The joint came first, so a query whose effect is
    # not identifiable at all — no theta will ever produce P(Y|do(X)) —
    # reached the reader as a list of distributions to go and collect. The
    # same graph WITH theta reports it correctly, which is the tell: what
    # changed was not the graph but how far the code got.
    recovered = _observational_joint_xy(
        theta, graph, x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
    )
    joint, ancestral = recovered.cells, recovered.ancestral
    risk_missing: tuple[MissingItem, ...] = ()
    if (
        q.experimental_risk_treated is not None
        and q.experimental_risk_control is not None
    ):
        p_y_do_x1 = float(q.experimental_risk_treated)
        p_y_do_x0 = float(q.experimental_risk_control)
        risk_provenance = RiskProvenance.USER_EXPERIMENTAL
    else:
        risks, risk_missing = _derive_interventional_risks(
            stmt, graph, theta, x_atom, y_atom,
            bidirected=bidirected, selection_nodes=selection_nodes,
        )
        if risks is not None:
            p_y_do_x1, p_y_do_x0 = risks
        # No risks means at least the escape item, so the merge below
        # returns before anything reads the two names left unbound here.
        risk_provenance = RiskProvenance.DERIVED_IDENTIFICATION

    if risk_missing and joint is not None:
        # Tian-Pearl's closed form has nothing to consume, and this is the
        # same question the counterfactual door asks — PN is one of its
        # cells. Asking the instrument here too is not an extra feature: a
        # door that refused while the other one answered, on one theta and
        # one graph, is the asymmetry this pair was just built to not have.
        #
        # Gated on the joint being in hand, which is not an optimisation: a
        # theta short of the joint is short of the table too, so the branch
        # would only reach the same gap by a longer road — and it would get
        # there holding a joint of None.
        return _causation_over_the_instrument(
            stmt, graph, theta, q, joint, ancestral,
            risk_missing=risk_missing,
            x_atom=x_atom, y_atom=y_atom, bidirected=bidirected,
        )
    if joint is None or risk_missing:
        return _causation_gap(
            stmt,
            joint_missing=recovered.missing,
            risk_missing=risk_missing,
        )

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
    # The two arms differ only in which joint cells bound them, and those
    # are notation — one member on two occasions rather than two members.
    infeasible: list[language.Statement] = []
    lo1, hi1 = joint[(True, True)], joint[(True, True)] + p_x0
    if not (lo1 - _TOL <= p_y_do_x1 <= hi1 + _TOL):
        infeasible.append(language.state(
            Feasibility.A_RISK_SITS_OUTSIDE_ITS_BOUND,
            quantity="P(Y=1|do(X=1))", value=f"{p_y_do_x1:.6g}",
            expression="[P(X=1,Y=1), P(X=1,Y=1)+P(X=0)]",
            lower=f"{lo1:.6g}", upper=f"{hi1:.6g}"))
    lo0, hi0 = joint[(False, True)], joint[(False, True)] + p_x1
    if not (lo0 - _TOL <= p_y_do_x0 <= hi0 + _TOL):
        infeasible.append(language.state(
            Feasibility.A_RISK_SITS_OUTSIDE_ITS_BOUND,
            quantity="P(Y=1|do(X=0))", value=f"{p_y_do_x0:.6g}",
            expression="[P(X=0,Y=1), P(X=0,Y=1)+P(X=1)]",
            lower=f"{lo0:.6g}", upper=f"{hi0:.6g}"))
    if infeasible:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.CAUSATION,
            query_id=stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.ASSUMPTION,
                    priority=Priority.HIGH,
                    need=gaps.Need.INTERVENTIONAL_RISKS_CONTRADICT_THE_JOINT,
                    # A list, joined where the reader is. A Chinese
                    # semicolon between two English clauses and an
                    # ASCII space before a Chinese one are the same
                    # mistake, and this site used to make both.
                    detail=tuple(infeasible),
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
    licence = stamp("causation_probability_bounds", risk_provenance)
    envelope = {
        "monotonic": q.monotonic,
        "interventional_risk_provenance": licence,
        # Null, not missing: this route reaches PN/PS/PNS through a pair of
        # interventional risks and never through an instrument, and saying so
        # is what makes the data route's column mean something by contrast.
        "instrument": None,
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
            rule="causation_probability_bounds",
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
                "interventional_risk_provenance": licence,
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
        extensions={blocks.Block.CAUSATION: envelope},
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

    missing_atoms = [a for a in atoms_the_graph_is_asked_about(q)
                     if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.SCM_COUNTERFACTUAL,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.SCM_COUNTERFACTUAL_QUERY,
                    atom=_atom_to_str(a),
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
    # Walked in causal order, never in the set's: the gaps below are listed
    # in the order these loops meet their variables, and a set's order moves
    # with the process, so one question listed its gaps differently from
    # one run to the next.
    topo = tuple(n for n in nx.topological_sort(graph) if n in relevant)

    obs_map = _scm_observation_map(program)
    missing: list[MissingItem] = []

    # Build the structural equations from edge coefficients; flag any
    # edge on the relevant subgraph that lacks a declared coefficient. The
    # intervened variable is skipped — its equation is replaced by the
    # constant, so we never abduct its exogenous term and its incoming
    # edges/parents are irrelevant.
    equations: dict = {}
    for v in topo:
        if v == x_atom:
            continue
        terms: list[tuple] = []
        for p in graph.predecessors(v):
            src = graph.edges[p, v].get("source")
            coef = getattr(src, "coefficient", None) if src is not None else None
            if coef is None:
                missing.append(gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=f"{_atom_to_str(p)}->{_atom_to_str(v)}",
                    priority=Priority.HIGH,
                    need=gaps.Need.PATH_COEFFICIENT_UNDECLARED,
                    parent=_atom_to_str(p),
                    child=_atom_to_str(v),
                ))
            else:
                terms.append((p, float(coef)))
        equations[v] = tuple(terms)

    # The unit must be fully observed over the relevant set (abduction).
    for v in topo:
        if v not in obs_map:
            missing.append(gaps.missing(
                kind=MissingKind.OBSERVATION,
                subject=_atom_to_str(v),
                priority=Priority.HIGH,
                need=gaps.Need.UNIT_OBSERVATION_MISSING,
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
        blocks.Block.SCM_COUNTERFACTUAL: {
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

    missing_atoms = [a for a in atoms_the_graph_is_asked_about(q)
                     if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.COUNTERFACTUAL_EVENT,
                    atom=_atom_to_str(a),
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
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.CONDITIONING_EVENT_HAS_PROBABILITY_ZERO,
                ),
            ),
        )

    if outcome is FAIL:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.COUNTERFACTUAL_CONJUNCTION,
            query_id=stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.COUNTERFACTUAL_NOT_IDENTIFIABLE,
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

    missing_atoms = [a for a in atoms_the_graph_is_asked_about(q)
                     if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.PROXIMAL_EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.PROXIMAL_ROLE,
                    atom=_atom_to_str(a),
                )
                for a in missing_atoms
            ),
        )

    outcome = identify_proximal(
        graph, bidirected,
        treatment=q.treatment, outcome=q.outcome, latent=q.latent,
        treatment_proxy=q.treatment_proxy, outcome_proxy=q.outcome_proxy,
        covariates=q.covariates, channel=q.channel,
    )

    if isinstance(outcome, ProximalNotIdentified):
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.PROXIMAL_EFFECT,
            query_id=stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.PROXIMAL_NOT_IDENTIFIABLE,
                    # The statement, not a rendered sentence and not the
                    # token beside one: which criterion broke is what the
                    # statement's own token says, and a second copy of it
                    # in the frame would be the reader meeting the machine
                    # tag before the sentence that explains it.
                    detail=outcome.statement,
                ),
            ),
        )

    estimand: ProximalEstimand = outcome
    # Flat scalars and not a nested ``channel`` object, for the same reason
    # the line below joins its list: this one dict is BOTH an extension block
    # and a derivation step's input, and the step serializer tags a nested
    # dict (``{"kind": "dict", …}``) where the extension keeps it plain. One
    # object with two shapes is a schema nobody can write once.
    descriptor = {
        "method": estimand.method,
        "treatment": _atom_to_str(estimand.treatment),
        "outcome": _atom_to_str(estimand.outcome),
        "latent": _atom_to_str(estimand.latent),
        # Collections, because the roles are sets: one source of confounding
        # rarely has one shadow, and a descriptor that could hold one name
        # per role was a descriptor that had already discarded the rest.
        "treatment_proxy": [_atom_to_str(a) for a in estimand.treatment_proxy],
        "outcome_proxy": [_atom_to_str(a) for a in estimand.outcome_proxy],
        "covariates": [_atom_to_str(a) for a in estimand.covariates],
        # Tokens, and a collection of them rather than one string. This was
        # joined into a sentence because the step serializer was said not to
        # take a collection of plain strings; it has taken one since the
        # generic ``value_tuple`` fallback landed, so what was left was a
        # rendered sentence on the envelope in whichever language the
        # producer was thinking in. A token is in no language and the
        # reader's surface joins them in its own punctuation.
        "data_conditions": [str(c) for c in estimand.data_conditions],
        **_proximal_channel_fields(estimand.channel),
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
        extensions={blocks.Block.PROXIMAL_ESTIMAND: descriptor},
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

    ``graph`` + ``bidirected`` enable the d-separation
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
        if missing_keys:
            # The exception's species describes ONE key — the one whose
            # lookup raised, and whose diagnosis names the marginal theta
            # does hold. The others were collected by re-running the walk
            # and all that is known of them is that theta lacks them, so
            # they say that and not the first one's story. Copying the
            # species across used to give every collected key the
            # raiser's kind as well, which sent a plain shortfall to the
            # repair "fix your graph".
            missing_items: tuple[MissingItem, ...] = tuple(
                _missing_parameter_from_theta(exc)
                if key == exc.missing_key
                else _missing_parameter_from_key(
                    key, need=gaps.Need.THETA_ENTRY_MISSING,
                    key=format_probability_key(key))
                for key in missing_keys
            )
        else:
            # No concrete key collected (e.g. a value-less query-bound atom):
            # keep the single original gap.
            missing_items = (_missing_parameter_from_theta(exc),)
        requests = investigation_pusher.push(missing_items)
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


def _dispatch_transport(facts: "_EffectFacts") -> QueryResult:
    """Phase 9 §T9.1.3 + Fix 3+4 §T9.2 (v0.1.5): Bareinboim-Pearl
    transport identification + numeric evaluation, once per source domain.

    A selection diagram belongs to ONE source population, so a program
    declaring two of them declares two diagrams and gets two verdicts.
    The effect transports iff SOME domain's does; every domain's answer
    rides on the block, because a reader told the effect does not
    transport needs to know which sources were tried and what each would
    have needed. Single-source is the one-domain case of that, not a
    separate path (#326).

    Identifiable case:
      - Builds one transport g-formula per transporting domain,
        ``Σ_z P(Y|X,Z,source_i) · ∏ P*(Z|...,target)``, and tries each
        against the supplied multi-population ``theta``.
      - Any domain evaluating → ``numerically_solved``. Two domains
        evaluating are two estimands of the SAME target quantity, so
        they have to agree: theta is given rather than estimated, so
        drift past floating point is the supplied numbers disagreeing
        with themselves, which refutes at least one declared selection
        diagram. That is reported instead of a number.
      - No domain evaluating → stays ``structurally_solved`` with one
        investigation request per domain naming the specific missing
        population key, so the reader can choose which source to go and
        get rather than being pointed at whichever came first.

    Unidentifiable case (structural) → ``needs_investigation`` with a
    structure-group missing item, and each domain's own blocking species.

    No source domain → :func:`_carried_as_it_stands`. The formula above
    reads its source factor from a domain where the treatment was
    randomised, and with no selection node there is no such domain to read
    it from.
    """
    from . import transport as _transport

    stmt, graph, q = facts.stmt, facts.graph, facts.query
    theta, selection_nodes = facts.theta, facts.selection_nodes
    sources = _transport.build_selection_diagrams(selection_nodes, graph)
    routes = _transport.identify_across_sources(
        sources,
        treatment=q.intervention.atom,
        outcome=q.target.atom,
    )
    by_source = {sn.id: sn.source_population for sn in selection_nodes}

    route_entries = [_transport_route_dict(r) for r in routes]
    transport_block: dict[str, object] = {
        "kind": "transport_identification",
        "target_population": q.target_population,
        "s_nodes": [
            {"id": sn.id,
             "source_population": sn.source_population,
             "affects": {
                 "predicate": sn.affects.predicate,
                 "args": [{"type": "const", "name": t.name} for t in sn.affects.args],
             }}
            for sn in selection_nodes
        ],
        "sources": route_entries,
    }
    if not sources:
        return _carried_as_it_stands(facts, transport_block)

    working = tuple(r for r in routes if r.identifiable)
    if not working:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=f"{r.source_population}"
                            f"->{q.target_population}",
                    priority=Priority.HIGH,
                    need=gaps.Need.TRANSPORT_NOT_IDENTIFIABLE,
                    # The sentence names the source domain; which of the two
                    # ways it is stuck is the block's ``blocked_by``, said
                    # there in its own words rather than pasted in here.
                    detail=r.source_population or "",
                )
                for r in routes
            ),
            extensions={blocks.Block.TRANSPORT_IDENTIFICATION: transport_block},
        )

    # EffectQuery.intervention is Intervention (atom + value); transport_
    # formula wants a ValuedAtom for the source X conditional.
    intervention_va = ValuedAtom(
        atom=q.intervention.atom, value=q.intervention.value,
    )
    derivation_steps: tuple[DerivationStep, ...] = ()
    for i, route in enumerate(working):
        derivation_steps = derivation_steps + (
            DerivationStep(
                rule="s_admissibility_check",
                inputs={
                    "treatment": q.intervention.atom,
                    "outcome": q.target.atom,
                    "selection_nodes_ids": ",".join(route.s_node_ids),
                    "adjustment_set": route.adjustment_set,
                },
                output=True,
                step_id=f"s_t9_1_{i}",
            ),
            DerivationStep(
                rule="transport_formula",
                inputs={
                    "treatment": q.intervention.atom,
                    "outcome": q.target.atom,
                    "adjustment_set": route.adjustment_set,
                    "source_population": route.source_population or "",
                    "target_population": q.target_population,
                },
                output=route.formula_repr,
                step_id=f"s_t9_2_{i}",
            ),
        )

    # Every transporting domain is tried against theta. The population
    # strings on the formula and on the supplied ProbabilityStatements
    # are the contract — a mismatch surfaces as InsufficientTheta naming
    # the specific missing key WITH its population tag, which is how a
    # reader learns that the source they have data for is not the one
    # this route rests on.
    evaluated: list[tuple[int, FormulaExpr, float]] = []
    shortfalls: list[MissingItem] = []
    formulas: list[FormulaExpr] = []
    for i, route in enumerate(working):
        expr = formula_builder.transport_formula(
            target=q.target,
            intervention=intervention_va,
            adjustment_set=tuple(route.adjustment_set),
            # Named, never invented: the trivial case has no source domain
            # (no selection node declares one), and `or "source"` turned
            # that into a domain no statement names and no theta entry
            # carries — a fabricated name on the reader's line and an
            # unfindable key for the evaluator, from one fallback.
            source_population=route.source_population,
            target_population=q.target_population,
            observed=q.given,
        )
        validate_formula(expr)
        formulas.append(expr)
        try:
            evaluated.append(
                (i, expr, numeric_estimator.estimate_formula(
                    expr, theta, graph=graph, bidirected=None)),
            )
        except InsufficientTheta as ite:
            shortfalls.append(_missing_parameter_from_theta(ite))

    # The route the chain witnesses is the one the answer rests on: the
    # first that evaluated, or — when none did — the first that
    # transports, since the claim there is only that it transports and
    # any one route establishes that. Every route is on the block either
    # way, so nothing about which one is named is hidden.
    witness = evaluated[0][0] if evaluated else 0
    derivation_steps = derivation_steps + (
        DerivationStep(
            rule="identify_via_transport",
            inputs={
                "criterion": StepRef(step_id=f"s_t9_1_{witness}"),
                "formula": StepRef(step_id=f"s_t9_2_{witness}"),
            },
            output=StructuralResult(value=True),
            step_id="s_t9_final",
        ),
    )

    if not evaluated:
        requests = investigation_pusher.push(tuple(shortfalls))
        return QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=True),
            formula=formulas[witness],
            derivation=derivation_steps,
            missing_information=tuple(shortfalls),
            investigation_requests=requests,
            extensions={blocks.Block.TRANSPORT_IDENTIFICATION: transport_block},
        )

    witness_expr, value = evaluated[0][1], evaluated[0][2]
    # A route IS its source domain — ``build_selection_diagrams`` groups the
    # declared nodes by that name, so it identifies the route's entry on the
    # block. Positions would not: ``working`` skips the blocked routes and
    # the block carries every one of them.
    entry_of = {d["source_population"]: d for d in route_entries}
    for i, _expr, evaluated_value in evaluated:
        entry_of[working[i].source_population]["numeric"] = {
            "value": evaluated_value,
        }
    values = [v for _i, _e, v in evaluated]
    spread = max(values) - min(values)
    if spread > _TRANSPORT_AGREEMENT_TOL:
        # Two diagrams, two numbers for one quantity: a falsification of
        # at least one of them, not a shortage of data. Reporting either
        # number would be picking which declaration to believe.
        disagreement = gaps.missing(
            kind=MissingKind.ASSUMPTION,
            subject=f"{q.target_population}",
            priority=Priority.HIGH,
            need=gaps.Need.TRANSPORT_SOURCES_DISAGREE,
            detail=f"{spread:.6g}",
        )
        return QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=True),
            formula=witness_expr,
            derivation=derivation_steps,
            missing_information=(disagreement,),
            investigation_requests=investigation_pusher.push((disagreement,)),
            extensions={blocks.Block.TRANSPORT_IDENTIFICATION: transport_block},
        )

    # Numeric success: append (transport_formula_ast, formula_evaluation,
    # numeric_result) to the structural prefix. The transport_formula_ast
    # step carries the FormulaExpr (parallel to backdoor_adjustment_formula
    # / front_door_adjustment_formula) so verify_numeric's formula-witness
    # check has a step to match formula_evaluation against. The
    # transport_formula step with the string output stays — the repr is
    # human-readable extension metadata; the AST is the machine-verifiable
    # derivation witness.
    ast_step_id = "s_t9_ast"
    eval_step_id = "s_t9_eval"
    numeric_result_obj = NumericResult(value=value)
    route = working[witness]
    derivation_steps = derivation_steps + (
        DerivationStep(
            rule="transport_formula_ast",
            inputs={
                "target": q.target,
                "intervention": intervention_va,
                "adjustment_set": tuple(route.adjustment_set),
                "source_population": route.source_population,
                "target_population": q.target_population,
                "observed": q.given,
            },
            output=witness_expr,
            step_id=ast_step_id,
        ),
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": witness_expr},
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
    transport_block["numeric"] = {
        "value": value,
        "source_population": route.source_population,
        "target_population": q.target_population,
        "agreeing_sources": len(evaluated),
    }

    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=stmt.id,
        structural_result=StructuralResult(value=True),
        numeric_result=numeric_result_obj,
        formula=witness_expr,
        derivation=derivation_steps,
        extensions={blocks.Block.TRANSPORT_IDENTIFICATION: transport_block},
    )


def _carried_as_it_stands(
    facts: "_EffectFacts", transport_block: dict,
) -> QueryResult:
    """A target population no selection node separates from the data's.

    Nothing is declared to differ, so the effect carries to that population
    as it stands, ``P*(y | do(x)) = P(y | do(x))``, and what it carries is
    still an effect: the one population's total effect of the treatment,
    identified by the rows that identify that question. The mediator
    transport displaces stays displaced, as it is where there is a boundary.

    This used to write ``P(y | x)`` for it, the transport formula's source
    factor with no source. That factor stands for the effect in a domain
    where the treatment was randomised; read in the one population there
    is, it asserts that nothing confounds the treatment. On 300 random
    five-variable graphs the verifier's own model refused 118 of those
    answers, every one where the outcome is upstream of the treatment, and
    the same questions without the population passed.

    The block stays on the answer: it is where a reader is told the
    question named a population and no difference from it was declared.
    """
    from dataclasses import replace as _replace

    q = facts.query
    one_population = _replace(facts.stmt, query=_replace(
        q, target_population=None, mediator=None, mediators=()))
    answer = _dispatch_effect(
        one_population, facts.graph, facts.theta,
        bidirected=facts.bidirected, feedback=facts.feedback,
        longitudinal_spec=facts.longitudinal_spec,
    )
    return _replace(answer, extensions={
        **(answer.extensions or {}),
        blocks.Block.TRANSPORT_IDENTIFICATION: transport_block,
    })


#: Two domains transporting the same effect are two estimands of one
#: quantity, and theta is DECLARED rather than estimated — so a gap wider
#: than floating point is the supplied numbers contradicting each other,
#: the same standard ``_IV_WEIGHT_TOL`` holds a declared distribution to.
_TRANSPORT_AGREEMENT_TOL = 1e-9


def _transport_route_dict(result) -> dict:
    """One source domain's verdict, as the envelope carries it.

    A blocked route carries the species and no estimand; a transporting
    one carries the estimand and no species. Neither carries the other's
    slot as an empty string, which would be a second spelling of absent.
    """
    route: dict[str, object] = {
        "source_population": result.source_population,
        "s_nodes": list(result.s_node_ids),
        "transportable": result.identifiable,
    }
    if result.identifiable:
        route["adjustment_set"] = [
            {"predicate": a.predicate,
             "args": [{"type": "const", "name": t.name} for t in a.args]}
            for a in result.adjustment_set
        ]
        route["formula_repr"] = result.formula_repr
    else:
        route["blocked_by"] = result.blocked_by
    return route


class _Attempt(NamedTuple):
    """What one identification strategy came back with.

    ``result`` is set when the strategy answered. Otherwise ``missing``
    says what it would have needed — and saying so is the point. The
    cascade's last resort is a refusal that enumerates the strategies it
    tried, so a strategy that returns nothing and says nothing turns a
    graph the identify path calls *identifiable via instrument Z given W*
    into an effect result claiming nothing reaches it. ``missing`` is
    empty when the strategy genuinely has nothing to add.
    """

    result: "QueryResult | None" = None
    missing: tuple[MissingItem, ...] = ()


# Stratum weights are a distribution; drift past this is the user's
# theta disagreeing with itself, not floating-point noise.
_IV_WEIGHT_TOL = 1e-9


def _iv_stratum_table(
    theta: Theta,
    *,
    y: Atom,
    y_value,
    x: Atom,
    x_treated,
    instrument: Atom,
    z_treated,
    z_control,
    conditioning: tuple[Atom, ...],
) -> "tuple[dict | None, tuple[MissingItem, ...]]":
    """The per-stratum Wald ingredients for one (instrument, W) pair.

    Returns ``(table, ())`` when theta covers every cell, else
    ``(None, missing)`` naming the exact conditional probabilities that
    are absent.

    ``conditioning`` must already be in topological order: the stratum
    weight P(W=w) is expanded by the chain rule
    ``∏_i P(W_i=w_i | W_1=w_1, ..., W_{i-1}=w_{i-1})``, the same
    convention ``formula_builder.backdoor_formula`` uses for its joint.

    An empty ``conditioning`` produces exactly one stratum, of weight
    1.0, whose conditionals carry no W term — the classical marginal
    Wald, reached through this same arithmetic rather than a parallel
    branch.

    Aggregation is the RATIO OF AVERAGES::

        LATE = Σ_w P(w)·[P(y|z⁺,w) − P(y|z⁻,w)]
             / Σ_w P(w)·[P(x⁺|z⁺,w) − P(x⁺|z⁻,w)]

    and NOT the average of the per-stratum ratios. Only the first is the
    complier average causal effect: it weights each stratum by that
    stratum's own complier share, which is precisely the denominator
    term (Abadie 2003). Weighting the stratum LATEs by P(w) instead
    answers a different question — the two coincide only when the
    instrument moves treatment equally hard everywhere.

    Lookups are direct theta entries, with no marginalization fallback —
    the same convention the marginal Wald has always used, and the same
    one the verifier re-derives under. The cost is that a stratified
    instrument needs every stratum conditional stated outright
    (including P(W=w) for each w); the benefit is that producer and
    verifier cannot drift over which derivation filled a hole.
    """
    missing: list[MissingItem] = []
    # Two species rather than one with an optional stratum: the words
    # that would join a stratum onto the marginal sentence are words, and
    # a value slot is where a value goes.
    occasion: dict
    if conditioning:
        occasion = dict(
            need=gaps.Need.IV_WALD_LATE_NEEDS_ENTRY_IN_STRATUM,
            instrument=_atom_to_str(instrument),
            # ", " and not "、": the enumeration comma is Chinese, and a
            # value slot is not where the reader's punctuation goes. It
            # is what the other two list-valued slots already use.
            given=", ".join(_atom_to_str(a) for a in conditioning),
        )
    else:
        occasion = dict(
            need=gaps.Need.IV_WALD_LATE_NEEDS_ENTRY,
            instrument=_atom_to_str(instrument),
        )

    def entry(target_atom: Atom, target_value, given_pairs) -> "float | None":
        key = ProbabilityKey(
            target_atom=target_atom,
            target_value=target_value,
            given=frozenset(given_pairs),
        )
        value = theta.entries.get(key)
        if value is None:
            missing.append(_missing_parameter_from_key(key, **occasion))
        return value

    cells: list[dict] = []
    for values in product(*(theta.domain_of(w) for w in conditioning)):
        w_pairs = tuple(zip(conditioning, values))
        factors = [
            entry(w_atom, w_value, w_pairs[:i])
            for i, (w_atom, w_value) in enumerate(w_pairs)
        ]
        cells.append(
            {
                "values": tuple(values),
                "factors": factors,
                "p_y_given_z_treated": entry(
                    y, y_value, ((instrument, z_treated), *w_pairs),
                ),
                "p_y_given_z_control": entry(
                    y, y_value, ((instrument, z_control), *w_pairs),
                ),
                "p_x_given_z_treated": entry(
                    x, x_treated, ((instrument, z_treated), *w_pairs),
                ),
                "p_x_given_z_control": entry(
                    x, x_treated, ((instrument, z_control), *w_pairs),
                ),
            }
        )
    if missing:
        return None, tuple(missing)

    strata = []
    for cell in cells:
        weight = 1.0
        for factor in cell["factors"]:
            weight *= factor
        strata.append(
            {
                "values": cell["values"],
                "weight": weight,
                "p_y_given_z_treated": cell["p_y_given_z_treated"],
                "p_y_given_z_control": cell["p_y_given_z_control"],
                "p_x_given_z_treated": cell["p_x_given_z_treated"],
                "p_x_given_z_control": cell["p_x_given_z_control"],
            }
        )
    strata_t = tuple(strata)

    total_weight = sum(c["weight"] for c in strata_t)
    if abs(total_weight - 1.0) > _IV_WEIGHT_TOL:
        return None, (
            gaps.missing(
                kind=MissingKind.ASSUMPTION,
                priority=Priority.HIGH,
                need=gaps.Need.IV_STRATUM_WEIGHTS_NOT_NORMALIZED,
                total=total_weight,
            ),
        )

    outcome_shift = sum(
        c["weight"] * (c["p_y_given_z_treated"] - c["p_y_given_z_control"])
        for c in strata_t
    )
    treatment_shift = sum(
        c["weight"] * (c["p_x_given_z_treated"] - c["p_x_given_z_control"])
        for c in strata_t
    )
    if abs(treatment_shift) < 1e-12:
        return None, (
            gaps.missing(
                kind=MissingKind.ASSUMPTION,
                priority=Priority.HIGH,
                need=gaps.Need.IV_FIRST_STAGE_DEGENERATE,
                instrument=_atom_to_str(instrument),
            ),
        )

    return (
        {
            "strata": strata_t,
            "outcome_shift": outcome_shift,
            "treatment_shift": treatment_shift,
            "late": outcome_shift / treatment_shift,
        },
        (),
    )


def _try_iv_wald_in_effect(facts: "_EffectFacts") -> _Attempt:
    """Fix 6 (v0.1.5, audit follow-up): IV-in-effect via Wald LATE —
    generalized to a CONDITIONAL (Brito-Pearl) instrument.

    ``structural_solver.iv_sets`` has always returned conditional
    candidates — a Z that is an instrument only once W is held fixed —
    and the identify path has always reported them. The numeric end took
    the first candidate and bailed the moment it carried a conditioning
    set, so exactly those graphs got no number here while the same graph
    handed to ``themis.estimate`` with a DataFrame got one out of 2SLS.
    ``_iv_stratum_table`` closes that, with W = ∅ as the one-stratum
    degenerate case of the same arithmetic, so the marginal answer is
    unchanged.

    Candidates are tried in order (subset-minimal W first) instead of
    only the first: a non-boolean instrument, or a theta short in one
    candidate's strata, says nothing about the next candidate.

    A conditional QUERY never arrives here: an unconditional LATE in its
    place would answer a different question, and that is now stated where
    both layers read it — ``iv_candidates`` is empty under conditioning,
    so the guard does not hold. It used to be the first line of this
    function, which bound this call site and no other. Still refused
    inside, because it is about the data rather than the query shape: a
    non-boolean treatment or instrument, since Wald is a two-point
    contrast and widening it is an estimator choice.
    """
    q, graph, theta = facts.query, facts.graph, facts.theta
    x, y = facts.x_atom, facts.y_atom
    x_treated = q.intervention.value
    if not isinstance(x_treated, bool):
        return _Attempt()

    iv_candidates = facts.iv_candidates
    mono = q.assumptions.monotonicity if q.assumptions is not None else None
    if mono is None:
        return _Attempt(missing=(
            gaps.missing(
                kind=MissingKind.ASSUMPTION,
                priority=Priority.HIGH,
                need=gaps.Need.IV_MONOTONICITY_UNDECLARED,
                count=len(iv_candidates),
                candidate=_iv_candidate_label(iv_candidates[0]),
                superseded_by_estimation=True,
            ),
        ))

    order = {node: i for i, node in enumerate(nx.topological_sort(graph))}
    first_missing: tuple[MissingItem, ...] = ()
    for chosen in iv_candidates:
        z = chosen.instrument
        if set(theta.domain_of(z)) != {True, False}:
            continue
        conditioning = tuple(
            sorted(chosen.conditioning, key=lambda a: order[a])
        )
        table, missing = _iv_stratum_table(
            theta,
            y=y, y_value=q.target.value,
            x=x, x_treated=x_treated,
            instrument=z, z_treated=True, z_control=False,
            conditioning=conditioning,
        )
        if table is None:
            first_missing = first_missing or missing
            continue
        return _Attempt(
            result=_build_iv_wald_effect_result(
                facts.stmt, graph, q, x, y,
                instrument=z,
                conditioning=conditioning,
                table=table,
                monotonicity=mono.value,
                alternatives_count=len(iv_candidates),
            ),
        )
    return _Attempt(missing=first_missing)


def _iv_candidate_label(candidate) -> str:
    """``z(me)`` / ``z(me) given {w(me)}`` — the instrument as a human
    reads it off the graph."""
    label = _atom_to_str(candidate.instrument)
    if not candidate.conditioning:
        return label
    inner = ", ".join(sorted(_atom_to_str(a) for a in candidate.conditioning))
    return f"{label} given {{{inner}}}"


def _build_iv_wald_effect_result(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    q: EffectQuery,
    x: Atom,
    y: Atom,
    *,
    instrument: Atom,
    conditioning: tuple[Atom, ...],
    table: dict,
    monotonicity: str,
    alternatives_count: int,
) -> QueryResult:
    """Wrap a completed stratified Wald into the effect result.

    Derivation: the existing iv_criterion_check + identify_via_iv pair
    (shared with the identify path) plus the bundled
    iv_wald_numeric_evaluate step, which records the ordered conditioning
    set alongside the stratum table — the order is what gives each
    stratum's positional ``values`` a meaning, and the verifier
    re-enumerates against it.
    """
    treated_va = ValuedAtom(atom=x, value=q.intervention.value)
    z_treated_va = ValuedAtom(atom=instrument, value=True)
    z_control_va = ValuedAtom(atom=instrument, value=False)

    iv_id_step = DerivationStep(
        rule="iv_criterion_check",
        inputs={
            "graph": graph,
            "x": x,
            "y": y,
            "instrument": instrument,
            "conditioning": frozenset(conditioning),
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
            "instrument_conditioning": conditioning,
            "monotonicity": monotonicity,
        },
        output=table,
        step_id="s_iv_numeric",
    )
    numeric_result_obj = NumericResult(value=table["late"])
    final_step = DerivationStep(
        rule="numeric_result",
        inputs={"evaluation": StepRef(step_id="s_iv_numeric")},
        output=numeric_result_obj,
        step_id="s_iv_final",
    )

    # Two statements rather than one paragraph built by ``+=``. The
    # symbols (LATE, ATE, `strata`, `treatment_shift`) stay inside the
    # words: they are the names of things the answer carries, and a
    # reader who looks for them has to find them. What leaves is the
    # join — what goes between two sentences is a fact about the
    # language, and a ``+=`` can only know one.
    late_caveat = [language.state(Complier.LATE_IS_NOT_THE_ATE)]
    if conditioning:
        inner = ", ".join(sorted(_atom_to_str(a) for a in conditioning))
        late_caveat.append(language.state(
            Complier.STRATA_WEIGHTED_BY_COMPLIER_SHARE,
            variables="{" + inner + "}"))

    extensions = {
        blocks.Block.IV_IDENTIFICATION: {
            "strategy": "iv",
            "instrument": _atom_to_str(instrument),
            "conditioning": sorted(_atom_to_str(a) for a in conditioning),
            "required_assumption": language.state(
                Premise.MONOTONICITY_AS_DECLARED,
                direction=Monotonicity.named(monotonicity)),
            "alternatives_count": alternatives_count,
            "late_caveat": late_caveat,
            "numeric": {
                "conditioning_order": [
                    _atom_to_str(a) for a in conditioning
                ],
                "strata": [
                    {
                        "values": list(cell["values"]),
                        "weight": cell["weight"],
                        "p_y_given_z_treated": cell["p_y_given_z_treated"],
                        "p_y_given_z_control": cell["p_y_given_z_control"],
                        "p_x_given_z_treated": cell["p_x_given_z_treated"],
                        "p_x_given_z_control": cell["p_x_given_z_control"],
                    }
                    for cell in table["strata"]
                ],
                "outcome_shift": table["outcome_shift"],
                "treatment_shift": table["treatment_shift"],
                "late": table["late"],
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

    if (
        q.mediator is not None
        or q.mediators
        or q.target_population is not None
    ):
        # WHICH other layer was asked for is something only here knows, and
        # both the shortfall's sentence and the way past it are about it:
        # "cannot be combined with mediation or transport" told a reader
        # who had asked for exactly one of them that it was one of two.
        # Named as the declaration that triggers it, the way the dispatch
        # conflict names a displaced layer, so one field is one name.
        other = routing.route(
            "transport" if q.target_population is not None
            else "mediation_joint" if q.mediators
            else "mediation_single")
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.JOINT_WITH_MEDIATION_OR_TRANSPORT,
                    drop=f"`{other.triggered_by}`",
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
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.DUPLICATE_TREATMENT_ATOM,
                ),
            ),
        )

    joint_sets = structural_solver.minimal_adjustment_sets_joint(
        graph, treatments, y_atom,
        given=observed_atoms, bidirected=bidirected or None,
    )

    treatments_set = frozenset(treatments)

    if not joint_sets:
        # Adjustment fails — but the joint effect may still be non-
        # parametrically point-identified by the set-valued Shpitser-Pearl
        # ID: latent confounding neutralized without any adjustment set
        # (front-door / c-component for the treatment SET). This is the
        # joint analog of the single-treatment general-ID escape layer.
        # v1 scope: unconditional only (a conditioning set on a joint query
        # has no supported general-ID estimand).
        from . import c_factor

        if not observed_atoms:
            gid_res = c_factor.identify_via_tian_joint(
                graph, bidirected or frozenset(),
                # Identifiability does not depend on WHICH corner, so any
                # one of them settles it; the query's own level names a
                # real corner rather than inventing a placeholder.
                dict.fromkeys(treatments_set, q.intervention.value), y_atom,
            )
            if gid_res.identifiable and gid_res.formula is not None:
                structural_result = StructuralResult(value=True)
                derivation: tuple[DerivationStep, ...] = (
                    DerivationStep(
                        rule="general_id_criterion",
                        inputs={"graph": graph, "x": x, "y": y_atom},
                        output=True,
                        step_id="s1",
                    ),
                    DerivationStep(
                        rule="identify_via_general_id",
                        inputs={"criterion": StepRef(step_id="s1")},
                        output=structural_result,
                        step_id="s2",
                    ),
                )
                # No ``note``: it said in English prose what ``pattern``
                # already records and what the route renderer states in the
                # reader's language on this very branch. A writer, no reader,
                # and a third copy of one fact.
                annotation = {
                    "pattern": "joint_general_id",
                    "treatments": sorted(
                        _atom_to_str(t) for t in treatments
                    ),
                }
                return QueryResult(
                    status=ResultStatus.STRUCTURALLY_SOLVED,
                    query_kind=QueryKind.EFFECT,
                    query_id=stmt.id,
                    structural_result=structural_result,
                    derivation=derivation,
                    extensions={blocks.Block.JOINT_IDENTIFICATION: annotation},
                )

        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.JOINT_EFFECT_NOT_IDENTIFIABLE,
                ),
            ),
        )

    chosen = min(joint_sets, key=len)
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
        extensions={blocks.Block.JOINT_IDENTIFICATION: annotation},
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

    # The spec names columns, and a column is one node. On a program
    # unrolled in time a variable has a node per step, and which of them a
    # name meant is written nowhere -- a map keyed on the predicate kept
    # whichever node the graph listed last.
    nodes_named: dict = {}
    for n in graph.nodes:
        nodes_named.setdefault(n.predicate, []).append(n)
    all_names = [*treatment_names, outcome_name,
                 *[c for blk in conf_blocks_names for c in blk]]
    missing_names = [nm for nm in all_names if nm not in nodes_named]
    if missing_names:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=nm,
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.LONGITUDINAL_SPEC,
                    atom=nm,
                )
                for nm in missing_names
            ),
        )

    several = [nm for nm in dict.fromkeys(all_names)
               if len(nodes_named[nm]) > 1]
    if several:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=nm,
                    priority=Priority.HIGH,
                    need=gaps.Need.NAME_HOLDS_SEVERAL_NODES,
                    part=gaps.QueryPart.LONGITUDINAL_SPEC,
                    atom=nm,
                    atoms=", ".join(sorted(
                        _atom_to_str(n) for n in nodes_named[nm])),
                )
                for nm in several
            ),
        )

    treatments = tuple(nodes_named[nm][0] for nm in treatment_names)
    y = nodes_named[outcome_name][0]
    conf_blocks = tuple(tuple(nodes_named[c][0] for c in blk)
                        for blk in conf_blocks_names)

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

    if first_failed is not None:
        k, a_k = first_failed
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            structural_result=StructuralResult(value=False),
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a_k),
                    priority=Priority.HIGH,
                    need=gaps.Need.SEQUENTIAL_EXCHANGEABILITY_FAILS,
                    treatment=_atom_to_str(a_k),
                    time=k,
                    outcome=_atom_to_str(y),
                ),
            ),
            extensions={blocks.Block.LONGITUDINAL_IDENTIFICATION: identification_ext},
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
        extensions={blocks.Block.LONGITUDINAL_IDENTIFICATION: identification_ext},
    )


class _EffectFacts(routing.StructuralFacts):
    """The identification layer's view of one effect query.

    Adds what only this layer has — theta, the selection statements, the
    longitudinal spec — to the structural facts both layers share. Those
    additions are exactly what the routes with an identification-only end
    name in their guards, so a guard belonging to this layer cannot be
    evaluated in the layer that has no implementation for it: the attribute
    is not there.
    """

    def __init__(
        self,
        *,
        stmt: QueryStatement,
        graph: nx.DiGraph,
        bidirected: "frozenset[frozenset[Atom]]",
        feedback: "frozenset[frozenset[Atom]]",
        theta: Theta,
        selection_nodes: "tuple[SelectionNode, ...]",
        longitudinal_spec: dict | None,
    ) -> None:
        super().__init__(
            q_stmt=stmt, graph=graph, bidirected=bidirected,
            feedback=feedback,
        )
        self.stmt = stmt
        self.theta = theta
        self.selection_nodes = selection_nodes
        self.longitudinal_spec = longitudinal_spec

    @cached_property
    def declares_longitudinal(self) -> bool:
        return (
            self.longitudinal_spec is not None
            and _longitudinal_spec_matches(self.query, self.longitudinal_spec)
        )

    @cached_property
    def extra_atoms(self) -> "tuple[Atom, ...]":
        return tuple(iv.atom for iv in self.query.extra_interventions)


def _identify_backdoor(facts: _EffectFacts) -> _Attempt:
    """Phase 7.1: adjustment over the smallest valid back-door set."""
    q, graph = facts.query, facts.graph
    x, y_atom = facts.x_atom, facts.y_atom
    topo = [
        n for n in nx.topological_sort(graph) if n in facts.chosen_adjustment
    ]
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
        observed_atoms=facts.given_atoms,
        target_va=q.target,
        intervention_va=intervention_va,
        observed_vas=q.given,
        formula=formula,
    )
    return _Attempt(_try_numeric(
        facts.stmt, formula, facts.theta, QueryKind.EFFECT,
        structural_prefix=structural_prefix,
        graph=graph, bidirected=facts.bidirected,
    ))


def _identify_frontdoor(facts: _EffectFacts) -> _Attempt:
    """Phase 7.2: the front-door formula through the smallest mediator set."""
    q, graph = facts.query, facts.graph
    x, y_atom = facts.x_atom, facts.y_atom
    chosen = min(facts.front_door_sets, key=len)
    topo = [n for n in nx.topological_sort(graph) if n in chosen]
    intervention_va = ValuedAtom(atom=x, value=q.intervention.value)
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
    return _Attempt(_try_numeric(
        facts.stmt, formula, facts.theta, QueryKind.EFFECT,
        structural_prefix=structural_prefix,
        graph=graph, bidirected=facts.bidirected,
    ))


def _identify_general(facts: _EffectFacts) -> _Attempt:
    """Non-parametric point identification via Shpitser-Pearl ID / IDC.

    One row, two formulas, chosen by the query's own shape rather than by
    trying one and falling back to the other: a query either conditions on
    something or it does not, and that is not a cascade. ``identify_via_tian``
    ignores the conditioning atoms, so for a conditional query its formula is
    the MARGINAL P(Y|do(X)) — shipping it would silently drop ``given``, which
    can differ sharply from the true conditional when ``given`` modifies the
    effect. IDC (Rule-2 exchange plus the ID recursion, normalized) is the
    conditional's own estimand, and the fraction is validated to 1e-9 against
    latent-SCM ground truth.

    Ranked above the IV escalation, and that ordering is load-bearing: a
    c-factor estimand is assumption-free and answers the query's own estimand,
    whereas the Wald LATE needs a declared monotonicity and reports a contrast
    among compliers. Declining here is what earns the escalation.
    """
    from . import c_factor as _c_factor

    q, graph, bidirected = facts.query, facts.graph, facts.bidirected
    x, y_atom = facts.x_atom, facts.y_atom

    if not facts.given_atoms:
        tian = _c_factor.identify_via_tian(
            graph, bidirected, x, y_atom, q.intervention.value,
        )
        if not (tian.identifiable and tian.formula is not None):
            return _Attempt()
        # Bind q.target.value into the Tian formula's outer Y ProbRefs
        # (c_factor leaves them None for the IdentifyQuery caller).
        # Without this, the evaluator raises InsufficientTheta on
        # query-bound atoms.
        bound_formula = formula_builder.bind_target_value(
            tian.formula, y_atom, q.target.value,
        )
        validate_formula(bound_formula)
        # Reuse the identify-side derivation prefix (tian_c_decomposition
        # + identify_via_tian), then add tian_formula_ast +
        # formula_evaluation + numeric_result via _try_numeric. Same shape
        # as transport (Fix 4 §T9.2).
        structural_prefix = (
            DerivationStep(
                rule="tian_c_decomposition",
                inputs={"graph": graph, "x": x, "y": y_atom},
                output=True,
                step_id="s_tian_decomp",
            ),
            DerivationStep(
                rule="identify_via_tian",
                inputs={
                    "decomposition": StepRef(step_id="s_tian_decomp"),
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
        return _Attempt(_try_numeric(
            facts.stmt, bound_formula, facts.theta, QueryKind.EFFECT,
            structural_prefix=structural_prefix,
            graph=graph, bidirected=bidirected,
        ))

    idc = _c_factor.identify_via_idc(
        graph, bidirected, x, y_atom, facts.given_atoms, q.intervention.value,
    )
    if not (idc.identifiable and idc.formula is not None):
        return _Attempt()
    value_map = {g.atom: g.value for g in q.given}
    value_map[y_atom] = q.target.value
    bound_formula = _c_factor.bind_idc_values(idc.formula, value_map)
    validate_formula(bound_formula)
    # Three-step structural prefix, parallel to the Tian branch: s1
    # idc_rule2_exchange (verifier replays the exchange), s2
    # identify_via_idc (verifier re-checks the numerator/denominator shape
    # against its own replay), s3 idc_formula_ast (verifier re-binds Y/Z
    # values). Then _try_numeric adds formula_evaluation + numeric_result.
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
    return _Attempt(_try_numeric(
        facts.stmt, bound_formula, facts.theta, QueryKind.EFFECT,
        structural_prefix=structural_prefix,
        graph=graph, bidirected=bidirected,
    ))


def _identify_longitudinal(facts: _EffectFacts) -> _Attempt:
    """Phase 7.L: sequential g-formula over the declared treatment
    trajectory.

    The route's guard is ``declares_longitudinal``, and what that guard
    tests is the spec being there — so reaching here without one is the
    route table and this table disagreeing, not a query shape.
    """
    spec = facts.longitudinal_spec
    if spec is None:
        raise AssertionError(
            "longitudinal identification reached with no longitudinal "
            "spec; the route's applies_when tests for one"
        )
    return _Attempt(_dispatch_longitudinal(
        facts.stmt, facts.graph, facts.query, spec,
        bidirected=facts.bidirected,
    ))


def _loop_labels(facts: _EffectFacts) -> dict:
    """The occasion every feedback sentence and route is written against."""
    loop = facts.loops_reaching[0]
    left, right = sorted(loop, key=_atom_to_str)
    return {
        "left": _atom_to_str(left),
        "right": _atom_to_str(right),
        "treatment": _atom_to_str(facts.x_atom),
        "outcome": _atom_to_str(facts.y_atom),
    }


def _identify_feedback_loop(facts: _EffectFacts) -> _Attempt:
    """#450: what a declared reciprocal loop leaves of this query.

    Three outcomes and they are not degrees of the same thing.

    Off the two-equation shape there is no remedy to offer, and saying so
    is the answer: the identification the DAG would have done rests on a
    premise the program has withdrawn, and a cyclic model need not define
    the quantity at all.

    On that shape, an instrument still identifies the coefficient of X in
    the Y equation. What this end produces is the ESTIMAND and the premise
    it rests on, never a number: the number comes from data through 2SLS.
    Computing one here off theta would be mixing a declared discrete CPT
    with a linear structural equation, and the answer would belong to
    neither model.

    With no instrument, the gap names the one thing that would close it —
    a variable in the caller's setting, not a distribution — which is the
    whole difference between this and the silence it replaces.
    """
    labels = _loop_labels(facts)
    if not facts.loop_is_between_treatment_and_outcome:
        return _Attempt(result=_feedback_loop_refusal(
            facts, labels,
            need=gaps.Need.FEEDBACK_LOOP_OUTSIDE_THE_SIMULTANEOUS_CASE,
        ))
    if not facts.iv_candidates_under_the_loop:
        return _Attempt(result=_feedback_loop_refusal(
            facts, labels,
            need=gaps.Need.FEEDBACK_LOOP_NEEDS_AN_INSTRUMENT,
        ))
    return _Attempt(result=_build_feedback_loop_effect_result(facts, labels))


def _feedback_loop_refusal(
    facts: _EffectFacts, labels: dict, *, need,
) -> QueryResult:
    """No answer, and the cascade stops here.

    A ``missing`` note would not do, and the difference is the whole
    feature. A note lets the cascade go on, and the very next row is
    back-door — which on this graph finds a valid adjustment set and
    answers, because the loop is not an edge it can see. That answer is
    the silence this replaces, now with a footnote attached.
    """
    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        query_id=facts.stmt.id,
        missing_information=(
            gaps.missing(
                kind=MissingKind.STRUCTURE,
                priority=Priority.HIGH,
                need=need,
                **labels,
            ),
        ),
        extensions={
            blocks.Block.FEEDBACK_LOOP: {
                **labels,
                "withdrew": ["backdoor", "frontdoor", "general_id"],
            },
        },
    )


def _build_feedback_loop_effect_result(
    facts: _EffectFacts, labels: dict,
) -> QueryResult:
    """The estimand a simultaneous system still has, and what it rests on.

    The derivation records the loop as its own step BEFORE the IV check,
    because the two facts are not interchangeable: the instrument is valid
    for a reason (the criterion) and it is NECESSARY for a different reason
    (the loop), and a trail that recorded only the first would read as an
    ordinary IV escalation from a graph where back-door merely happened to
    fail.
    """
    chosen = facts.iv_candidates_under_the_loop[0]
    x, y = facts.x_atom, facts.y_atom
    structural_result = StructuralResult(value=True)
    loop = facts.loops_reaching[0]
    left, right = sorted(loop, key=_atom_to_str)

    derivation = (
        DerivationStep(
            rule="feedback_loop_withdraws_adjustment",
            inputs={"graph": facts.graph, "x": x, "y": y,
                    "left": left, "right": right},
            output=True,
            step_id="s_loop",
        ),
        DerivationStep(
            rule="iv_criterion_check",
            inputs={
                "graph": facts.graph,
                "x": x,
                "y": y,
                "instrument": chosen.instrument,
                "conditioning": chosen.conditioning,
            },
            output=True,
            step_id="s_iv_check",
        ),
        DerivationStep(
            rule="identify_via_iv",
            inputs={"criterion": StepRef(step_id="s_iv_check")},
            output=structural_result,
            step_id="s_iv_id",
        ),
    )

    instrument_label = _atom_to_str(chosen.instrument)
    conditioning_labels = sorted(
        _atom_to_str(a) for a in chosen.conditioning)
    # No ``required_assumption`` on either identification block, and that
    # absence is the design. The premise here is not the LATE monotonicity
    # those fields were built to carry, and it is not only an assumption —
    # it also changes WHAT the number is. Both halves are one sentence, and
    # that sentence is written once, bilingually, in the gap report from
    # the loop block below. A second wording here would be the same claim
    # with two authors, and one of them would be the one nobody updates.
    extensions = {
        blocks.Block.FEEDBACK_LOOP: {
            **labels,
            "withdrew": ["backdoor", "frontdoor", "general_id"],
            "reduction": "simultaneous_equations",
        },
        blocks.Block.IV_IDENTIFICATION: {
            "strategy": "iv",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
            # This route wrote a bare TOKEN here while its three siblings
            # wrote prose, and said why: "the report renders it verbatim".
            # The field is a statement now, so the reason is gone and the
            # member stays — the premise under a loop is two claims at
            # once (linearity, and that the number is a single equation's
            # coefficient) and its words say both. What the gap report
            # states from the loop block is still the fuller sentence, and
            # `_classify_iv_assumption` still stands down where one is
            # present, which is a decision about which sentence a reader
            # gets rather than about which language it is in.
            "required_assumption": language.state(
                Premise.LINEAR_SIMULTANEOUS_SYSTEM),
            "alternatives_count": len(facts.iv_candidates_under_the_loop),
        },
        blocks.Block.IDENTIFICATION: {
            "pattern": "instrumental_variable",
            "instrument": instrument_label,
            "conditioning": conditioning_labels,
        },
    }
    return QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=facts.stmt.id,
        structural_result=structural_result,
        derivation=derivation,
        extensions=extensions,
    )


# The identification end of every route that declares one. Binding by id
# against the shared table is what makes a strategy the table promises and
# this layer never runs impossible: ``routing.bind`` refuses both halves of
# that mistake — a route with no implementation here, and an implementation
# for a route the table does not send this way.
_EFFECT_IDENTIFICATION = routing.bind(routing.End.IDENTIFICATION, {
    "feedback_loop": _identify_feedback_loop,
    "longitudinal": _identify_longitudinal,
    "joint_intervention": lambda f: _Attempt(_dispatch_joint_effect(
        f.stmt, f.graph, f.query, f.x_atom, f.y_atom, f.extra_atoms,
        f.given_atoms, bidirected=f.bidirected,
    )),
    "transport": lambda f: _Attempt(_dispatch_transport(f)),
    "mediation_joint": lambda f: _Attempt(_dispatch_mediation_joint(
        f.stmt, f.graph, f.query, f.theta, bidirected=f.bidirected,
    )),
    "mediation_single": lambda f: _Attempt(_dispatch_mediation(
        f.stmt, f.graph, f.query, f.theta, bidirected=f.bidirected,
    )),
    "backdoor": _identify_backdoor,
    "frontdoor": _identify_frontdoor,
    "general_id": _identify_general,
    "iv_wald": _try_iv_wald_in_effect,
})


def _effect_refusal(
    facts: _EffectFacts, notes: "tuple[MissingItem, ...]",
) -> QueryResult:
    """Nothing in the table claimed this query — say so in its own terms.

    The wording forks, and deliberately so: what a reader needs to be told
    differs. On an ADMG the honest report is that back-door, front-door and
    Tian / Shpitser ID were all tried and that an IV escalation may exist
    but could not be run; on a graph with no latent confounding that report
    would name machinery the situation never involved. The ladder above is
    one — only the sentence at the end forks.
    """
    if facts.given_atoms and facts.bidirected:
        # A conditional estimand hedged even where the marginal might not
        # be: name the conditional path, never the marginal in its place.
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=facts.stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=gaps.Need.CONDITIONAL_ADMG_NOT_IDENTIFIABLE,
                ),
            ),
        )
    if facts.bidirected:
        # Nonparametric point identification failed, and that stays said:
        # it is what makes any answer here an interval or an
        # assumption-laden point rather than a point ID, and the downstream
        # answer tier reads it. When the IV layer also has something to say
        # — an instrument reaches this graph, it just could not be run —
        # those items ride ALONGSIDE it rather than replacing it. The two
        # are different facts, and the IV escalation being available is not
        # identification.
        #
        # Which is why this reason names only the durable half: an
        # instrument exists here and it costs an assumption. Whether it
        # ran is this run's business, and this run's business is already
        # written down — by the items alongside when they survive, by the
        # estimator's refusal when a supplied sample killed the first
        # stage. The clause that used to summarise them in prose was a
        # second copy of the item list, and it went stale in both
        # directions: it stayed "could not be run" after the estimator
        # had run it, and it went on pointing at "the items alongside
        # this one" after a supplied DataFrame answered them and they
        # were dropped. Its guard was the second copy's, too — any route
        # leaving any note, not the fact the sentence asserts.
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=facts.stmt.id,
            missing_information=(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    priority=Priority.HIGH,
                    need=(gaps.Need.ADMG_EFFECT_REACHABLE_ONLY_BY_INSTRUMENT
                      if facts.iv_candidates
                      else gaps.Need.ADMG_EFFECT_NOT_IDENTIFIABLE),
                ),
                *notes,
            ),
        )
    return QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        query_id=facts.stmt.id,
        structural_result=StructuralResult(value=False),
        missing_information=(
            gaps.missing(
                kind=MissingKind.STRUCTURE,
                priority=Priority.HIGH,
                need=gaps.Need.NO_BACKDOOR_OR_FRONTDOOR,
            ),
        ),
    )


def _dispatch_effect(
    stmt: QueryStatement,
    graph: nx.DiGraph,
    theta: Theta,
    bidirected: "frozenset[frozenset[Atom]]" = frozenset(),
    feedback: "frozenset[frozenset[Atom]]" = frozenset(),
    selection_nodes: "tuple[SelectionNode, ...]" = (),
    longitudinal_spec: dict | None = None,
) -> QueryResult:
    """Offer one effect query to each identification strategy in turn.

    The order lives in ``themis.routing``, shared with the estimation
    cascade, so "transport outranks mediation" and "an assumption-free
    estimand outranks an assumption-laden one" are one statement rather
    than two files that used to agree by inspection and three times did
    not.
    """
    q: EffectQuery = stmt.query  # type: ignore[assignment]

    facts = _EffectFacts(
        stmt=stmt, graph=graph, bidirected=bidirected, feedback=feedback,
        theta=theta,
        selection_nodes=selection_nodes, longitudinal_spec=longitudinal_spec,
    )

    # Not a strategy: a query naming an atom outside V has no estimand for
    # anyone to compete over, so this is a precondition on the query rather
    # than a row that could lose to another.
    missing_atoms = [a for a in atoms_the_graph_is_asked_about(q)
                     if a not in graph]
    if missing_atoms:
        return QueryResult(
            status=ResultStatus.NEEDS_INVESTIGATION,
            query_kind=QueryKind.EFFECT,
            query_id=stmt.id,
            missing_information=tuple(
                gaps.missing(
                    kind=MissingKind.STRUCTURE,
                    subject=_atom_to_str(a),
                    priority=Priority.HIGH,
                    need=gaps.Need.ATOM_NOT_IN_GRAPH,
                    part=gaps.QueryPart.QUERY,
                    atom=_atom_to_str(a),
                )
                for a in missing_atoms
            ),
        )
    refused = _a_given_holding_an_end(stmt, QueryKind.EFFECT)
    if refused is not None:
        return refused

    notes: list[MissingItem] = []
    for route, identify in _EFFECT_IDENTIFICATION:
        if not route.applies_when(facts):
            continue
        attempt = identify(facts)
        if attempt.result is not None:
            # The winner is known here and so, for the only time, are the
            # rows it took the query from: the loop is about to return, and
            # every row below is left unevaluated. Recording it here is what
            # replaces the gap report's inference from which extension came
            # back empty.
            from dataclasses import replace as _replace

            return _replace(
                _name_the_pattern(attempt.result, route, facts),
                dispatch=DispatchRecord(
                    answered_by=route.id,
                    displaced=routing.displaced_by(route, facts),
                ),
            )
        notes.extend(attempt.missing)
    return _effect_refusal(facts, tuple(notes))


#: The effect rows whose estimand is P(Y | do(X)) for a single X, and so
#: the rows the graph-level pattern describes. Every other row —
#: transport, longitudinal, joint intervention, mediation, feedback loop,
#: IV — writes its own identification block naming a structure this
#: recognizer knows nothing about, and overwriting that would be a
#: downgrade rather than an addition.
_ROWS_THE_PATTERN_DESCRIBES = frozenset({"backdoor", "frontdoor", "general_id"})


def _name_the_pattern(
    result: QueryResult, route, facts: "_EffectFacts",
) -> QueryResult:
    """Attach the graph-level identification pattern to an effect answer.

    An identify query has always carried this. An effect query — the one
    that returns a NUMBER — carried it on no row but the IV escalation,
    so a reader holding an answer was never told which structure produced
    it: the pattern was encoded implicitly, in which cascade row fired
    and hence which derivation vocabulary appeared, and a reader does not
    read cascade rows. One recognizer, both ends, attached in the single
    place where the winning row is known.
    """
    if route.id not in _ROWS_THE_PATTERN_DESCRIBES:
        return result
    ext = dict(result.extensions or {})
    if blocks.Block.IDENTIFICATION in ext:
        return result
    from dataclasses import replace as _replace

    ext[blocks.Block.IDENTIFICATION] = _recognize_identification_pattern(
        facts.graph, facts.bidirected,
        x=facts.x_atom, y=facts.y_atom, given=facts.given_atoms,
    )
    return _replace(result, extensions=ext)


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

    ``bidirected`` MUST be threaded through to ``_try_numeric``, because
    the d-separation guard short-circuits when ``bidirected is None``
    (see numeric_estimator._try_marginal_independence_lookup) and
    dropping it here leaves the guard dormant for the entire
    ``probability`` query path: a chain DAG (S→T→C) with marginal-only
    theta P(C|S) and a query P(C|S,T) then silently returns the marginal
    value (0.18) instead of refusing. L3 case 012 (Pearl 1995
    smoking-tar-cancer chain) is the regression that catches it.
    """
    q: ProbabilityQuery = stmt.query  # type: ignore[assignment]
    formula = formula_builder._conditional(
        q.target,
        q.given,
    )
    return _try_numeric(
        stmt, formula, theta, QueryKind.PROBABILITY,
        graph=graph, bidirected=bidirected,
    )


def _attach_framing(
    result: QueryResult, inputs: postprocess.Inputs,
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

    program, stmt = inputs.program, inputs.stmt
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
        gaps.item(
            target=note.predicate,
            need=gaps.Need.FRAMING_FIELDS_UNFILLED,
            # The field names stay as they are: they are what the user
            # types back into the declaration, so translating them would
            # name something that does not exist. The sentence around
            # them belongs to the species, where the other surface that
            # files this same fact now reads it from too.
            predicate=note.predicate,
            count=len(note.missing),
            fields=", ".join(note.missing),
            skeleton=framing_check.build_define_variable_skeleton(
                program, note.predicate, note.missing,
            ),
        )
        for note in notes
    )
    # The heading is the items said shortly, and one function says it for
    # every channel. Written out by hand here it carried no note over a
    # single ask, where every other channel carries that ask's species.
    # The channel is still named by its action, which is how a framing
    # request has always been spelled and what the stored answers say.
    target, note, priority = investigation_pusher.summarise(
        InvestigationAction.DEFINE_VARIABLE.value,
        [(item.target, gaps.carried(item), Priority.MEDIUM) for item in items],
    )
    framing_request = InvestigationRequest(
        action=InvestigationAction.DEFINE_VARIABLE,
        target=target,
        priority=priority,
        note=note,
        group="framing",
        items=items,
    )
    merged_requests = result.investigation_requests + (framing_request,)
    return replace(
        result, framing_notes=notes, investigation_requests=merged_requests,
    )


def _attach_investigation(
    result: QueryResult, inputs: postprocess.Inputs,
) -> QueryResult:
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
        gaps.missing(
            kind=MissingKind.FRAMING,
            subject=note.predicate,
            priority=Priority.HIGH,
            need=gaps.Need.FRAMING_FIELDS_UNFILLED,
            predicate=note.predicate,
            count=len(note.missing),
            fields=", ".join(note.missing),
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
    graph: nx.DiGraph | None = None,
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
      values on the ground edges the answer rests on, as the data-gap
      classifier reads them. Without this collection a
      counterfactual whose load-bearing edge is marked low-confidence
      would surface as confidence=None and bypass the
      LOW_CONFIDENCE_INPUT_DATA gap.
    - Intervention atoms never contribute (do-cut).
    - Missing theta / indices on a numeric path return () for the
      probability/observation slots, but the structural-edge path
      still runs (it does not depend on theta).
    """
    collected: list[ConfidenceSource] = []

    # §3.3 structural-edge slots — runs for every query kind so
    # cause-edge confidences propagate even when no numeric formula
    # was built.
    collected.extend(
        _gather_structural_edge_sources(program, stmt, result, graph),
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
    graph: nx.DiGraph | None = None,
) -> tuple[ConfidenceSource, ...]:
    """RFC §3.3 — collect annotations.confidence from CauseStatements
    on the structurally load-bearing path(s) of the query.

    Which statements those are is the data-gap classifier's reading,
    called rather than restated. This used to walk the same predicate
    paths as a copy of that one and carried each thing the copy got
    wrong: a supporting path matched in path order only, and paths walked
    over predicates where the answer rests on ground atoms.

    Returns one ConfidenceSource per (frm, to) edge the answer rests on
    whose CauseStatement carries a non-None confidence. The slot is named
    by its predicates, and several statements can stand behind that name
    -- an edge stated twice, or grounded at two times or for two units.
    Looked up again by the name, the confidence was the last such
    statement's, rested on or not. It is read off the statements the
    answer rests on instead, and a slot several of them fill reports the
    weakest, as a probability slot does (``_slot_min_source``).
    """
    from ..types import CauseStatement
    if not any(
        isinstance(s, CauseStatement)
        and s.annotations is not None and s.annotations.confidence is not None
        for s in program.statements
    ):
        return ()

    from ..output.data_gap_report import _statements_the_answer_rests_on
    weakest: dict[tuple[str, str], tuple[str | None, float]] = {}
    for s in _statements_the_answer_rests_on(
        program, graph, getattr(result, "structural_result", None),
        stmt, result.extensions or {},
    ):
        if not isinstance(s, CauseStatement):
            continue
        ann = s.annotations
        if ann is None or ann.confidence is None:
            continue
        edge = (s.from_atom.predicate, s.to_atom.predicate)
        # min by confidence, stable on ties (first seen wins)
        if edge not in weakest or ann.confidence < weakest[edge][1]:
            weakest[edge] = (ann.source, ann.confidence)
    return tuple(
        ConfidenceSource(
            slot_label=f"edge:{frm}->{to}",
            source=weakest[(frm, to)][0],
            confidence=weakest[(frm, to)][1],
            is_weakest=False,
        )
        for frm, to in sorted(weakest)
    )


def _gather_input_confidences(
    program: Program,
    stmt: QueryStatement,
    result: QueryResult,
    *,
    theta: Theta | None = None,
    prob_index: dict | None = None,
    obs_index: dict | None = None,
    graph: nx.DiGraph | None = None,
) -> tuple[float, ...]:
    """Back-compat shim for the old float-only contract. Delegates to
    ``_gather_input_sources`` and strips the source metadata."""
    return tuple(
        s.confidence for s in _gather_input_sources(
            program, stmt, result,
            theta=theta, prob_index=prob_index, obs_index=obs_index,
            graph=graph,
        )
    )


def _attach_confidence(
    result: QueryResult, inputs: postprocess.Inputs,
) -> QueryResult:
    """Route every result through ``confidence_calc.composite``.

    v0.2 composite semantics: min of non-None slot confidences,
    None if no slots contribute. Collection rules are defined in
    ``confidence_rfc_v0_2.md`` §3 and implemented by
    ``_gather_input_sources``.

    ``confidence_sources`` is populated alongside it — one entry per
    contributing slot, with the source annotation, the confidence
    value, and an ``is_weakest`` flag for sources whose confidence
    equals the composite min. A consumer then has the
    "why is it this low" audit trail without re-deriving it, which is
    the difference between a number and an answer.
    """
    from dataclasses import replace

    sources = _gather_input_sources(
        inputs.program, inputs.stmt, result,
        theta=inputs.theta,
        prob_index=inputs.prob_index,
        obs_index=inputs.obs_index,
        graph=inputs.graph,
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
    feedback: "frozenset[frozenset[Atom]] | None" = None,
) -> QueryResult:
    """Route a query to its solver(s) and assemble a QueryResult.

    If any of ``theta`` / ``prob_index`` / ``obs_index`` / ``bidirected`` /
    ``feedback`` is omitted, the missing ones are built on demand from the
    program.
    For batch dispatch prefer ``dispatch_all`` which builds everything
    once and reuses it.

    ``bidirected`` is the ADMG bidirected-edge set extracted from the
    ground program (Phase 2.latent S3.a). Identify / effect dispatch
    routes through the ADMG-aware front-door when this set is non-empty;
    the directed-only backdoor path is skipped for ADMG programs.
    """
    if (theta is None or prob_index is None or obs_index is None
            or bidirected is None or feedback is None):
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
        if feedback is None:
            feedback = structural_solver.feedback_from_ground(ground)

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
            sel_nodes = tuple(s for s in program.statements if isinstance(s, SelectionNode))
            long_spec = None
            if program.options:
                _ls = program.options.get("longitudinal")
                if isinstance(_ls, dict):
                    long_spec = _ls
            result = _dispatch_effect(
                stmt, graph, theta,
                bidirected=bidirected, feedback=feedback,
                selection_nodes=sel_nodes,
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
        sel_nodes = tuple(s for s in program.statements if isinstance(s, SelectionNode))
        result = _dispatch_counterfactual(
            stmt, graph, theta,
            bidirected=bidirected, selection_nodes=sel_nodes,
        )
    elif isinstance(q, CausationQuery):
        sel_nodes = tuple(s for s in program.statements if isinstance(s, SelectionNode))
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
    return postprocess.run(result, POST_PASSES, postprocess.Inputs(
        program=program,
        stmt=stmt,
        graph=graph,
        theta=theta,
        prob_index=prob_index,
        obs_index=obs_index,
        bidirected=bidirected,
    ))


def _attach_program_ambiguities(
    result: QueryResult, inputs: postprocess.Inputs,
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

    ext = getattr(inputs.program, "extensions", None) or {}
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
    new_ext[blocks.Block.AMBIGUITIES] = relevant
    return _replace(result, extensions=new_ext)


def _attach_data_gap_report(
    result: QueryResult, inputs: postprocess.Inputs,
) -> QueryResult:
    """Phase 10 §10.3 + Phase 13: synthesize the structured data-gap
    report from signals already on the QueryResult, plus (Phase 13)
    program-level extensions.ambiguities for dose-response detection."""
    from dataclasses import replace as _replace

    from ..output.data_gap_report import compute_data_gap_report

    program, stmt = inputs.program, inputs.stmt
    report = compute_data_gap_report(
        query_kind=result.query_kind,
        status=result.status,
        derivation=result.derivation,
        investigation_requests=result.investigation_requests,
        framing_notes=result.framing_notes,
        program=program,
        graph=inputs.graph,
        bidirected=inputs.bidirected,
        stmt=stmt,
        extensions=result.extensions,
        structural_result=result.structural_result,
        bounds_results=result.bounds_results,
        numeric_result=result.numeric_result,
        confidence=result.confidence,
        dispatch=result.dispatch,
    )
    if report is None:
        return result
    return _replace(result, data_gap_report=report)


def _serialize_selection_recovery(rec, x: Atom, y: Atom) -> dict:
    """Serialize a SelectionRecoveryResult to the JSON extension block."""
    return {
        "kind": "selection_recovery",
        "query_kind": rec.query_kind,
        "treatment": x.predicate,
        "outcome": y.predicate,
        # The subpopulation the verdict is about, written only when there is
        # one: every block before it was about the whole population, and an
        # empty list would say nothing a reader could not already assume.
        **({"given": [a.predicate for a in rec.given]} if rec.given else {}),
        "recoverable": rec.recoverable,
        "criterion": rec.criterion,
        "selection_nodes": [a.predicate for a in rec.selection_nodes],
        "adjustment_set": [a.predicate for a in rec.adjustment_set],
        "z_plus": [a.predicate for a in rec.z_plus],
        "z_minus": [a.predicate for a in rec.z_minus],
        "recovery_formula": rec.formula_repr,
        "external_data_needed": list(rec.external_data_needed),
        "failure_reason": rec.failure_reason,
        # Whether a negative here is a proof or only "not by this
        # criterion". It sits beside ``search_budget`` because the two
        # answer the same reader: one gives the range the verdict was
        # checked over, the other says whether the test that produced it
        # is necessary as well as sufficient. Both used to be clauses
        # inside the sentence, and a clause cannot be branched on.
        "complete_criterion": rec.complete_criterion,
        # The range the verdict is relative to. A ``recoverable: false``
        # here means "no admissible set this large or smaller", and a
        # reader given the verdict without the quantifier is given a
        # stronger claim than the one that was checked. The verifier reads
        # it too, so its re-search re-derives THIS claim instead of one
        # that merely shares a constant with it.
        "search_budget": rec.search_budget,
        "reference": (
            "Bareinboim & Pearl 2012 (selection backdoor criterion); "
            "Bareinboim, Tian & Pearl 2014 (recoverability)"
        ),
    }


def _attach_selection_recovery(
    result: QueryResult, inputs: postprocess.Inputs,
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

    program, graph = inputs.program, inputs.graph
    q = getattr(inputs.stmt, "query", None)
    if not isinstance(q, EffectQuery):
        return result
    x = q.intervention.atom
    y = q.target.atom
    if x not in graph or y not in graph:
        return result

    # Selection nodes = the atoms the sample is restricted on, as nodes.
    # An observation is ground, so its atom is the node it names. Looked up
    # by predicate, a variable with a second node -- a step back, or
    # another person's -- kept whichever the graph listed last, and the
    # restriction landed on a node nobody observed.
    s_atoms: list[Atom] = []
    for st in program.statements:
        if not isinstance(st, ObservationStatement):
            continue
        node = st.atom
        if node not in graph or node in (x, y) or node in s_atoms:
            continue
        s_atoms.append(node)
    if not s_atoms:
        return result

    # Gate: only surface when at least one restriction is a genuine
    # selection collider (otherwise there is no selection-bias question).
    if not any(structural_solver.is_common_effect(graph, x, y, s) for s in s_atoms):
        return result

    # The stratum the question asks about goes to the analysis with it. It
    # used to stop here, and a question about one stratum was answered
    # with the population's verdict and, on data, the population's number.
    rec = recover_effect(graph, x, y, tuple(s_atoms),
                         given=tuple(g.atom for g in q.given))
    block = _serialize_selection_recovery(rec, x, y)
    new_ext = dict(result.extensions or {})
    new_ext[blocks.Block.SELECTION_RECOVERY] = block
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
        # Its twin on the selection block, for the same reason.
        "complete_criterion": rec.complete_criterion,
        # The range the verdict is relative to — the largest conditioning
        # set the factorization search looked at. Its twin sits on the
        # selection block for the same reason: "not recoverable" without
        # the quantifier is a stronger claim than the one that was made,
        # and a verifier re-deriving it has to re-derive this one.
        "search_budget": rec.search_budget,
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
    result: QueryResult, inputs: postprocess.Inputs,
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

    program, graph = inputs.program, inputs.graph
    q = getattr(inputs.stmt, "query", None)
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
            smallest = min(adj_sets, key=len)
            z = tuple(sorted(smallest, key=lambda a: a.predicate))
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
        # Which factors this estimand is a product of. Two hardcoded
        # strings used to say it, with a literal ``P(Y|X,Z)`` in them
        # rather than the targets carried one field over — a second record
        # of the same fact, and it had already drifted from the first.
        "requires": list(est.requires),
        "failure_reason": est.failure_reason,
    }
    new_ext = dict(result.extensions or {})
    new_ext[blocks.Block.MISSING_DATA_RECOVERY] = block
    return _replace(result, extensions=new_ext)


def _attach_bounds_results(
    result: QueryResult, inputs: postprocess.Inputs,
) -> QueryResult:
    """Phase 12 §S.12.4: when point identification failed on an effect
    query, bound the estimand symbolically. Pure function — no I/O.

    EVERY method whose assumptions this program supports is reported, each
    carrying its own. This used to return the first one that fired, which
    made a slot able to hold any of them hold whichever branch ran first.
    All three bound the same quantity — ``estimand='arm_probability'`` on
    all three — under assumption sets that do not contain one another:
    Manski assumes nothing, Balke-Pearl needs IV1/IV2/IV3 off the graph,
    Manski-Tamer needs a monotone treatment response the caller asserted.
    This package's one rule for ranking strategies is that an
    assumption-free estimand outranks an assumption-laden one, and that
    rule is about the estimand CHANGING (declaring monotonicity once
    replaced a population effect with a complier contrast), not about
    which interval is narrower. It therefore declines to rank these, and a
    single slot has to.

    What that cost was not the rare case, and the measurement moved the
    item. Over 96 parseable programs and 69 effect queries in this repo,
    ZERO declare monotonicity and zero declare both it and an instrument,
    so the two assumption-laden rows never actually competed — the
    registered complaint was about a state that is constructible and has
    no instances. What DID happen, on every one of the three answers that
    reached a sharper method (3 of 36 results carrying bounds), is that
    the assumption-free floor — which applies wherever they do, and which
    this pass exists to provide — sat behind ``if bounds is None`` and so
    was never computed at all. The reader was shown an interval resting
    on IV1/IV2/IV3 with no way to see what was left without them.

    Not intersected. Under both assumption sets both intervals hold, so
    their intersection does contain the truth, but it is not the SHARP set
    under the conjunction — that is one LP over the response-function
    polytope with the monotone types removed, which the numeric end can do
    and no closed form here can — and one unlabelled interval would hide
    which half rests on what.

    IV detection (Phase 12 §S.12.6 patch): a structural check, via the same
    :func:`_instrument_candidates` the counterfactual door reads. Not the
    IV block: every route that writes one has solved the query, so no
    result this pass runs on carries it, and it names the instrument as
    an atom where everything below needs the predicate.
    """
    from dataclasses import replace as _replace

    from ..output.bounds import (
        attempt_balke_pearl_iv,
        attempt_manski_natural,
        attempt_manski_tamer_monotonicity,
    )
    from ..types import (
        EffectQuery,
            ResultStatus,
        VariableDeclaration,
    )

    program, stmt = inputs.program, inputs.stmt
    if result.bounds_results:
        return result
    if result.status != ResultStatus.NEEDS_INVESTIGATION:
        return result
    if not isinstance(stmt.query, EffectQuery):
        return result
    query = stmt.query

    # Manski / Balke-Pearl bound the estimand in the population the
    # observational joint came from. A query naming a target population
    # asks about a different one, and when its transport identification
    # failed there is no assumption-free floor for it — the source joint
    # constrains the target only through the selection diagram this query
    # just established does not carry it. Bounds computed here would not
    # be loose about the right quantity; they would be tight about the
    # wrong one.
    if query.target_population is not None:
        return result

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

    # All three methods bound the same arm P(Y=y | do(X=x)). Manski natural
    # is cardinality-agnostic by construction (the off-arm mass is P(X≠x),
    # be it one other level or several); Balke-Pearl is cardinality-agnostic
    # by SIZE — its response-function partition grows with the cardinalities
    # and is offered while it stays inside MAX_RESPONSE_TYPES. Manski-Tamer's
    # monotone envelope over ordered levels IS a binary-treatment
    # construction, so that one stays gated on a bool intervention value.
    #
    # The order below is PRESENTATION, not precedence: the floor first, then
    # each sharpening, because that is the order a reader can follow. No
    # decision rides on it, which is why there is no table declaring it — a
    # precedence number here would assert a ranking these three do not have.
    # Read off the program's structure and never off an IV block, which
    # names an atom (``z(me)``) where the level count and the numeric
    # end's column both need the predicate.
    instrument_pred = _detect_iv_candidate_structural(
        program, query, inputs.graph, inputs.bidirected)

    found: list = []

    # The assumption-free floor. Available wherever the sharper methods are,
    # which is exactly why it used to be unreachable: it was written last,
    # under a guard that only held when nothing sharper had fired.
    floor = attempt_manski_natural(query, outcome_event_is_discrete=True)
    if floor is not None:
        found.append(_note_a_sharper_method_was_declined(
            program, query, floor, instrument_pred,
        ))

    # Manski-Tamer (MTR), under a monotone treatment response the caller
    # asserted via query.assumptions.monotonicity or the older
    # program.extensions['monotonicity'] side channel.
    if intervention_is_bool:
        mtr_direction = _detect_monotonicity_for_query(program, query)
        mtr_levels = _mtr_outcome_levels(program, query)
        if mtr_direction is not None and mtr_levels is not None:
            mtr = attempt_manski_tamer_monotonicity(
                query,
                monotonicity=mtr_direction,
                outcome_event_is_discrete=True,
                outcome_levels=mtr_levels,
            )
            if mtr is not None:
                found.append(mtr)

    # Balke-Pearl, under IV1/IV2/IV3 read off the graph. Returns None when
    # the response-function partition is past MAX_RESPONSE_TYPES, and the
    # floor above says so rather than reading like a query with no
    # instrument.
    if instrument_pred:
        bp = attempt_balke_pearl_iv(
            query,
            instrument_predicate=instrument_pred,
            outcome_levels=_declared_level_count(
                program, query.target.atom.predicate, query.target.value),
            treatment_levels=_declared_level_count(
                program, query.intervention.atom.predicate,
                query.intervention.value),
            instrument_levels=_declared_level_count(
                program, instrument_pred, None),
        )
        if bp is not None:
            found.append(bp)

    if not found:
        return result
    return _replace(result, bounds_results=tuple(found))


def _note_a_sharper_method_was_declined(program, query, bounds, instrument_pred):
    """Say so when the floor is being reported because the sharp method was
    too big to compute, not because there was nothing sharper.

    A cap that quietly drops the query to the assumption-free floor reads,
    at every surface, exactly like a query that never had an instrument.
    The reader is entitled to know that a tighter answer exists and what
    it would cost to reach it.
    """
    from dataclasses import replace as _replace
    from .. import language
    from ..output.bounds import (
        MAX_RESPONSE_TYPES, Note, response_type_count)
    from ..types import BoundsMethod

    if bounds.method is BoundsMethod.BALKE_PEARL_IV or not instrument_pred:
        return bounds
    levels = [
        _declared_level_count(program, query.target.atom.predicate,
                              query.target.value),
        _declared_level_count(program, query.intervention.atom.predicate,
                              query.intervention.value),
        _declared_level_count(program, instrument_pred, None),
    ]
    if not all(isinstance(n, int) and n >= 2 for n in levels):
        return bounds
    ny, nx, nz = levels
    assert ny is not None and nx is not None and nz is not None
    if response_type_count(treatment_levels=nx, outcome_levels=ny,
                           instrument_levels=nz) is not None:
        return bounds
    # Appended rather than concatenated. The field is a sequence, so a
    # fourth author adds to it without having to know what the method
    # already said or what punctuation the reader's language joins with.
    return _replace(
        bounds,
        notes=bounds.notes + (language.state(
            Note.A_SHARPER_METHOD_WAS_DECLINED_FOR_SCALE,
            instrument=instrument_pred,
            treatment_levels=nx, outcome_levels=ny, instrument_levels=nz,
            cap=MAX_RESPONSE_TYPES),),
    )


def _mtr_outcome_levels(program, query):
    """The outcome's declared levels, low to high, or ``None`` when MTR
    cannot be justified on this outcome.

    Read here — beside :func:`_detect_monotonicity_for_query`, and imported
    by the numeric dispatcher rather than written twice — because the
    symbolic and numeric layers must agree on WHICH order they are assuming,
    not merely on whether a method applies.

    MTR is a claim about an order, and the bound it produces is on the event
    ``Y=y``, whose indicator is monotone in ``Y`` only at the top of that
    order. So the levels are not a refinement of the method: without them it
    cannot say which side of the interval its own assumption tightens, and
    what it used instead was the intervention's polarity — a fact about X.

    ``None`` on three counts, each of which is the same answer: nothing here
    knows the order.

    - The outcome is declared NOMINAL. The declaration says its levels have
      no order, and "monotone in an unordered variable" is not a weaker
      assumption but an empty one.
    - No domain is declared and the target value is not a bool. A bool has
      exactly two levels and a settled order; anything else with no
      declaration could have levels this query never mentions, and a level
      the sample happens to miss would move the top one step down.
    - The target value is not among the declared levels. Where it sits in
      the order is the question, and it is not in the order.
    """
    from ..estimation.declared import Declared
    from ..types import VariableDeclaration

    predicate = query.target.atom.predicate
    for stmt in program.statements:
        if isinstance(stmt, VariableDeclaration) and stmt.predicate == predicate:
            declared = Declared(scale=stmt.scale, domain=stmt.domain)
            break
    else:
        declared = Declared(scale=None, domain=None)

    if declared.unordered:
        return None
    levels = declared.domain
    if levels is None:
        if not isinstance(query.target.value, bool):
            return None
        levels = (False, True)
    levels = tuple(levels)
    # Which order. A declared domain records the levels IN THE ORDER THEY
    # WERE WRITTEN, because for a labelled column that is the only order
    # there is and it is the program's to state. It is not the order for a
    # number or a bool: ``domain: [true, false]`` is how these programs
    # habitually list a boolean, and reading it as "false is the higher
    # level" would make MTR tighten the wrong side just as surely as not
    # reading the order at all. So the type's own order wins where the type
    # has one, and the declaration's stands where it does not — with
    # ``scale: nominal`` as the way to say there is no order to read.
    if all(isinstance(v, (bool, int, float)) for v in levels):
        levels = tuple(sorted(levels))
    if len(levels) < 2 or query.target.value not in levels:
        return None
    return levels


def _detect_monotonicity_for_query(program, query):
    """Resolve the MTR declaration for an EffectQuery.

    ``query.assumptions.monotonicity`` is the first-class field; the
    older ``program.extensions['monotonicity']`` side channel is kept as
    a fallback. Resolution order:

    1. **First-class field**: ``query.assumptions.monotonicity`` —
       direct, no target/treatment matching needed (the assumption
       is on this query's own intervention → target relationship).
    2. **Extensions side channel**: walk
       ``program.extensions['monotonicity']`` (dict or list of dicts)
       and match by ``(target, treatment)`` pair to query's predicates.

    Returns the matching ``Monotonicity`` enum value, else None.
    """
    from ..ledger import Monotonicity

    # Prefer the first-class field.
    query_assumptions = getattr(query, "assumptions", None)
    if query_assumptions is not None:
        mono = getattr(query_assumptions, "monotonicity", None)
        if mono is not None:
            return mono

    # Fallback: walk the extensions side channel.
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
            return Monotonicity.named(direction)
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


def _declared_level_count(program: Program, predicate: str, value) -> int | None:
    """How many levels the program declares this variable to have, or None
    when it declares none — which is what "continuous" looks like here.

    A bool ``value`` answers 2 on its own: a boolean predicate has two states
    whether or not anybody wrote the domain down. This is the treatment /
    outcome / instrument's CARDINALITY, which is what decides the size of a
    response-function model — as opposed to
    :func:`_event_is_discrete`, which asks whether one particular level is a
    non-degenerate event.
    """
    from ..types import VariableDeclaration

    if isinstance(value, bool):
        return 2
    decl = next(
        (
            s for s in program.statements
            if isinstance(s, VariableDeclaration) and s.predicate == predicate
        ),
        None,
    )
    if decl is None or decl.domain is None:
        return None
    levels = len(set(decl.domain))
    return levels if levels >= 2 else None


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


def _reconcile_alt_paths_with_bounds(
    result: QueryResult, inputs: postprocess.Inputs,
) -> QueryResult:
    """Phase 12 §S.12.4 follow-up: align the routes ``data_gap_report``
    offers with what the bounds attempt actually produced.

    What this pass supplies is the two things
    :func:`themis.gaps.past_the_bounds_in_hand` cannot know for itself —
    which intervals came out, and whether an attempt was even made. The
    judgement is there rather than here because the OTHER door that adds
    routes to a report is the estimation layer, which reaches its gaps
    long after any pass has run (#444).

    Whether an attempt was made is this surface's fact alone: an effect
    query left needing investigation is where the bounds attempt runs, and
    an attempt that returned nothing is the difference between withdrawing
    a promise and leaving one nobody tested. What still returns None is a
    continuous variable with no discrete event to bound — Balke-Pearl and
    Manski both work at any discrete cardinality now.
    """
    from dataclasses import replace as _replace

    from .. import gaps
    from ..types import GapSeverity, QueryKind, ResultStatus

    if result.data_gap_report is None:
        return result

    computed = [b.method for b in (result.bounds_results or ())]
    attempted = (
        result.query_kind == QueryKind.EFFECT
        and result.status == ResultStatus.NEEDS_INVESTIGATION
    )
    if not attempted and not computed:
        return result

    new_gaps = []
    changed = False
    for gap in result.data_gap_report.gaps:
        rewritten = gaps.past_the_bounds_in_hand(
            gap.alternative_paths, computed,
            delivered_nothing=attempted and not computed,
            blocking=gap.severity == GapSeverity.BLOCKING,
        )
        if rewritten is None:
            new_gaps.append(gap)
            continue
        new_gaps.append(_replace(gap, alternative_paths=rewritten))
        changed = True

    if not changed:
        return result

    # The next-steps tail used to be rebuilt here too, and then filtered:
    # with bounds attached, its "或：已计算 bounds — 见 bounds_results" line
    # offered a computed interval as a route to itself, so a substring test
    # for ``bounds_result`` dropped it. Both are gone with the tail — it is
    # assembled by each surface out of the gaps it shows, and it no longer
    # repeats an alternative path that the gap itself carries.
    new_report = _replace(result.data_gap_report, gaps=tuple(new_gaps))
    return _replace(result, data_gap_report=new_report)


# ---------------------------------------------------------------------------
# The post-processing table.
#
# Declared in the order they were written; run in the order their blocks
# require. The two differ in one place, and that place is the reason for
# the table: ``structural_caveats`` used to be a tail call inside
# ``data_gap_report`` — a pass hidden inside another pass, which is how it
# came to read the report before the pass that revises it had run.
#
# The blocks named here are the whole dependency structure. Anything a
# pass consults that is not listed is something the dispatcher left, which
# every pass sees the same way; anything listed is a claim that running
# before its writer would give a different answer.
# ---------------------------------------------------------------------------

POST_PASSES: tuple[postprocess.Pass, ...] = postprocess.order((
    postprocess.Pass(
        # Turns the refusal's missing items into actions — unless the
        # dispatcher already built requests of its own, in which case this
        # pass stands down. That guard is why it has to produce the block
        # before framing adds to it: the other way round, framing's single
        # DEFINE_VARIABLE request would look like the dispatcher's work and
        # every missing item would lose its action.
        name="investigation",
        run=_attach_investigation,
        reads=frozenset({"status", "missing_information"}),
        writes=frozenset({"investigation_requests"}),
    ),
    postprocess.Pass(
        # The composite confidence and the per-slot trail behind it. Reads
        # the formula and the structural verdict; the extension keys are
        # the dispatcher's, naming the edges the answer leans on.
        name="confidence",
        run=_attach_confidence,
        reads=frozenset({
            "query_kind", "formula", "structural_result",
            "extensions.iv_identification",
            "extensions.mediation_decomposition",
            "extensions.mediation_joint_decomposition",
        }),
        writes=frozenset({"confidence", "confidence_sources"}),
    ),
    postprocess.Pass(
        # Advisory notes on under-specified variables, plus the one
        # actionable request that repairs them — appended to whatever
        # investigation already raised.
        name="framing",
        run=_attach_framing,
        reads=frozenset({"status", "investigation_requests"}),
        writes=frozenset({"framing_notes", "investigation_requests"}),
    ),
    postprocess.Pass(
        # Echo the program's declared ambiguities onto the result so the
        # gap report can read them from one place.
        name="program_ambiguities",
        run=_attach_program_ambiguities,
        reads=frozenset({"query_id"}),
        writes=frozenset({"extensions.ambiguities"}),
    ),
    postprocess.Pass(
        # The assumption-free floor, when point identification failed.
        # Before the report, so a bounded answer is classified as bounded.
        name="bounds",
        run=_attach_bounds_results,
        reads=frozenset({"status"}),
        writes=frozenset({"bounds_results"}),
    ),
    postprocess.Pass(
        # Reads nearly everything: the report is the account of what the
        # kernel could and could not do, so every block above it is input.
        name="data_gap_report",
        run=_attach_data_gap_report,
        reads=frozenset({
            "query_kind", "status", "derivation", "investigation_requests",
            "framing_notes", "structural_result", "numeric_result",
            "confidence", "bounds_results", "dispatch",
            "extensions.ambiguities",
            "extensions.iv_identification",
            "extensions.transport_identification",
            "extensions.mediation_decomposition",
            "extensions.mediation_joint_decomposition",
        }),
        writes=frozenset({"data_gap_report"}),
    ),
    postprocess.Pass(
        # Rewrites the report's static "bounds are available" promises into
        # what the bounds attempt actually returned. A revision, not a
        # second report.
        name="reconcile_alt_paths",
        run=_reconcile_alt_paths_with_bounds,
        reads=frozenset({
            "query_kind", "status", "bounds_results", "data_gap_report",
        }),
        writes=frozenset({"data_gap_report"}),
    ),
    postprocess.Pass(
        # Two verdicts on whether the answer survives a biased sample.
        # Neither reads any block, so neither has a place it must occupy —
        # they land last because they were declared last.
        name="selection_recovery",
        run=_attach_selection_recovery,
        reads=frozenset(),
        writes=frozenset({"extensions.selection_recovery"}),
    ),
    postprocess.Pass(
        name="missing_data_recovery",
        run=_attach_missing_data_recovery,
        reads=frozenset(),
        writes=frozenset({"extensions.missing_data_recovery"}),
    ),
))


def _detect_iv_candidate_structural(
    program: Program,
    query: "EffectQuery",
    graph: nx.DiGraph,
    bidirected: "frozenset[frozenset[Atom]]",
) -> str | None:
    """The instrument a Balke-Pearl row is fitted around, by predicate.

    Returns the predicate of Z iff Z is what
    :func:`structural_solver.unconditional_instruments` offers and Z is
    declared with a finite domain of at least two levels.

    The domain requirement is about the response-function model needing a
    finite ``z → x`` map to enumerate, not about the instrument being
    binary. Requiring ``{True, False}`` here used to throw away a perfectly
    good three-level instrument and drop the query to the no-instrument
    floor — the whole of the instrument's information, discarded over a
    cardinality the method never needed.

    Returns None if zero or multiple candidates (don't guess on tie).
    """
    from ..types import VariableDeclaration

    candidates = {
        z.predicate for z in structural_solver.unconditional_instruments(
            graph, query.intervention.atom, query.target.atom,
            bidirected=bidirected,
        )
    } & {
        s.predicate for s in program.statements
        if isinstance(s, VariableDeclaration)
        and s.domain is not None and len(set(s.domain)) >= 2
    }
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
    feedback = structural_solver.feedback_from_ground(ground)
    validate_against_graph(ground, graph, bidirected=bidirected)
    theta = theta_builder.build_theta(ground)
    prob_index = build_probability_source_index(ground)
    obs_index = build_observation_source_index(ground)

    return tuple(
        dispatch(
            program, stmt, graph, theta,
            prob_index=prob_index, obs_index=obs_index,
            bidirected=bidirected, feedback=feedback,
        )
        for stmt in program.statements
        if isinstance(stmt, QueryStatement)
    )
