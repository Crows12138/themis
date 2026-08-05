"""Phase 10 §10.3 — DataGapReport generator.

Pure-function synthesis of a structured "what data is still needed" report
from existing result-envelope signals (derivation steps, investigation
requests, framing notes, extensions). No I/O.

Per Phase 10 charter §4 out-of-scope: this module **MUST NOT**
- import any KB / retrieval module,
- make HTTP / file / DB calls,
- call out to LLMs.

It only reads what dispatch already produced and re-shapes it into the
DataGap / DataGapReport schema. The independence pin in T10 verifier
(S.10.4) guarantees the verifier itself does not depend on this module.

Gap_kind branches (current enum: see ``themis.types.GapKind``; cross-file
sync is pinned by ``tests/test_gap_kind_coverage_meta.py``):

Phase 10 charter §2.2 (initial 8):
1. unidentifiable_no_admissible_set       — item species, or derivation
   has unidentifiable_*
2. missing_distribution                   — item species
3. missing_population_distribution        — placeholder for §T9.2/§T9.3
4. missing_assumption                     — item species
4b. missing_unit_observation              — item species
4c. missing_structural_input              — item species
5. missing_iv_candidate                   — a failed IV derivation step
6. missing_mediator_data                  — mediation block valid + parameter
7. transport_target_distribution_unknown  — transport_identification + non-empty Z
8. ambiguous_variable_definition          — framing_notes non-empty

"Item species" means the kernel said so: every investigation item carries
``MissingItem.gap``, and ``_ITEM_SPECIES`` binds one renderer per species
the vocabulary allows. Which species an item is was decided where the
failure happened and is not inferred here — the passes that used to infer
it from the name's prefix, and from whether it contained the letters
``iv``, got it wrong in both directions at once (charter finding F).

Phase 11+ structural caveats (must-disclose channel; mirrored to
``result.explanation`` by ``scheduler._attach_structural_caveats`` —
the canonical set lives in ``scheduler._MUST_DISCLOSE_GAP_KINDS``):
- unverified_proposal_edge_on_query_path — Phase 11.x §C
- iv_identification_assumption_required — Phase 6.iv
- mediation_identification_assumption_required — Phase 6.mediation
- transport_identification_assumption_required — Phase 9 §T9.1
- llm_declared_ambiguity — A1-emitted ambiguities
- answer_is_bounds_not_point_estimate — Phase 12 bounds-first
- low_confidence_input_data — composite confidence below threshold
- front_door_identification_assumption_required — A6.front-door (program-shape
  fallback added iter 10 for needs_investigation + missing-theta case)
- counterfactual_identification_assumption_required — Phase 5 §C
- graph_learned_from_data — Phase 8.1 discovery
- collider_conditioning_opens_backdoor — iter 122 selection-bias
  signal (board #7); fires when EffectQuery.given names a collider
- dichotomized_continuous_measure — 2026-06-18 (boards #11/#1); fires
  when a path variable declares a non-empty ``threshold`` (a continuous
  measure dichotomized at a cutpoint)

Additional data-need gap_kinds (NOT must-disclose — these surface only
via ``data_gap_report``, not auto-mirrored to ``explanation``):
- transport_source_conditional_unknown — Phase 9 §T9.1 second data need
- dose_response_data_required — Phase 13

L3 simulation 2026-05-07 additions (iter 5 / iter 19):
- unmeasured_confounder_risk — DAG declares confounders but no bidirected;
  warns measured-covariate adjustment may have residual unmeasured-confounder
  bias. Cross-domain examples (HRT-CVD / Card 1995 / vitamin D-CVD).
- unattempted_layer_due_to_dispatch_conflict — query has BOTH mediator and
  target_population set; only one extension populated. Discloses silent skip.

iter 205 must-disclose addition (board #8 unblock):
- measurement_error_concern — at least one variable on the
  identification path declares a (measurement | observability) field
  whose value names a documented noisy-measurement pattern
  (self-report / questionnaire / 24h recall / single-occasion BP /
  proxy / FFQ etc.). Suppressed when extensions.ambiguities[*]
  already declared kind=='measurement_quality' (case 011 escape-hatch).
  Surfaces measurement-error bias before data collection — the same
  before-the-fact placement as unmeasured_confounder_risk. Severity
  IMPORTANT (regression-dilution / non-differential mis-classification
  are identification-impacting).

iter 206 must-disclose addition (board #7 — selection bias second
shape, complementing iter 122 collider_conditioning_opens_backdoor):
- selection_on_collider_opens_path — an ObservationStatement on node W
  encodes implicit sample restriction to W=value, AND W has both
  intervention X and target Y as directed ancestors. Conditioning on
  W (which the data-generating process does, by virtue of the sample
  being restricted) opens X→…→W←…←Y; the marginal estimate from the
  restricted sample carries selection-induced bias. Hernán-Hernández-
  Díaz-Robins 2004 *Epidemiology* 15:615 "A Structural Approach to
  Selection Bias" Figure 3-style. Distinct from iter 122's kind which
  fires on EffectQuery.given (explicit conditioning) — this fires on
  observation statements (implicit sample-restriction conditioning).

iter 207 must-disclose addition (board #1 / #11 — well-defined
intervention prerequisite; third dead-schema-theatre find of the
2026-05 mini-arc):
- ill_defined_intervention_versions — the EffectQuery's intervention
  predicate declares ``state_vs_event = "state"`` without a
  ``time_window`` on the same VariableDeclaration. Per Hernán &
  Taubman 2008 *IJO* 32(S3):S8 "Does obesity shorten life? The
  importance of well-defined interventions to answer causal questions"
  — when the exposure is a habitual / persistent attribute, multiple
  structurally-different interventions producing the same state value
  can entail DIFFERENT counterfactual outcomes (gastric-banding
  obesity loss vs lifestyle obesity loss). do(X=state) without naming
  the manipulation route silently violates the consistency assumption
  (Hernán & Robins *What If* §3.4). Suppressed when extensions has
  declared an ``ill_defined_intervention`` / ``well_defined_intervention``
  ambiguity (case 011-style escape hatch). Pre-iter-207, the variable
  schema's ``state_vs_event`` field admitted "state" / "event" as
  values but no classifier ever read the VALUE — same dead-schema
  pattern as iter 205 (measurement) + iter 206 (ObservationStatement).

iter 203 must-disclose addition:
- graph_theta_independence_mismatch — the iter 199 d-separation guard
  refused an existing-but-graph-incompatible marginal during formula
  evaluation; the user's declared graph and supplied CPTs disagree.
  Routed via the same investigation-request channel as missing_distribution
  but the classifier branches on the iter 202 d-sep refusal signature in
  item.reason and emits this dedicated kind so the structured channel
  carries the right repair action ("fix graph or supply demanded
  conditional"), not "supply more theta".

Estimator-runtime gap_kinds (attached during themis.estimate dispatch,
NOT by the classifier in this module — they require a fitted estimate
to inspect):
- weak_iv_instrument (iter 120) — first-stage F-stat below Stock-Yogo
  (2005) threshold; appended to data_gap_report by
  themis/estimation/dispatch.py._attach_weak_iv_warning_if_low_f after
  estimate_iv_ate returns.
- overidentification_rejected — the Sargan over-identification test rejected
  the q >= 2 instruments' joint validity (the data refute an exclusion
  restriction); appended by themis/estimation/dispatch.py._attach_overid_iv_warnings
  after estimate_iv_overid returns.
- propensity_overlap_violation (iter 121) — > 5% of sample has
  estimated P(X=1|Z) outside [0.05, 0.95]; appended by
  themis/estimation/dispatch.py._attach_propensity_overlap_warning
  after estimate_backdoor_ate when the adjustment set is non-empty.
- outcome_model_quasi_separation (iter 123) — > 10% of fitted
  P(Y|X,Z) falls outside [0.01, 0.99] (outcome regression saturates,
  logit blows up); appended by
  themis/estimation/dispatch.py._attach_outcome_separation_warning
  after estimate_backdoor_ate with logistic outcome.
"""
from __future__ import annotations

from typing import Callable, Iterable, NamedTuple

from .. import blocks, questions
from . import derivation_glossary
from .sample_size import (
    estimate_min_n_single_proportion,
    estimate_min_n_two_arm_binary,
    is_binary_outcome_distribution,
)
from ..types import (
    AnswerTier,
    Atom,
    BidirectedStatement,
    CausationQuery,
    CauseStatement,
    DataGap,
    DataGapReport,
    DerivationStep,
    FramingNote,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    InvestigationItem,
    InvestigationRequest,
    MISSING_ITEM_GAPS,
    ObservationStatement,
    QueryKind,
    RequiredDataType,
    ResultStatus,
    VariableDeclaration,
)

# ============================================ failure-rule registry
#
# Rule names whose presence means a structural failure happened. The
# scheduler is in the process of also marking these with success=False
# (Phase 10 §10.2 added the field with default True). Until the scheduler
# is fully converted, the generator detects failure both ways:
#   (a) explicit: step.success is False
#   (b) by name : step.rule in FAILURE_RULE_NAMES
_FAILURE_RULE_NAMES: frozenset[str] = frozenset({
    "unidentifiable_via_backdoor",
    "unidentifiable_via_front_door",
    "unidentifiable_via_iv",
    "unidentifiable_via_mediation",
    "unidentifiable_via_transport",
})

# Rule names whose ``inputs`` carry an adjustment set, under "z". Named
# rather than matched on a substring: "identify_via_backdoor" reads like
# one of these and carries only StepRefs, so a substring test finds a
# step with nothing in it and stops looking.
_ADJUSTMENT_SET_RULE_NAMES: frozenset[str] = frozenset({
    "backdoor_criterion",
    "joint_backdoor_criterion",
})


def _step_failed(step: DerivationStep) -> bool:
    return (not step.success) or step.rule in _FAILURE_RULE_NAMES


# ============================================ public entry


def compute_data_gap_report(
    *,
    query_kind: QueryKind,
    status: ResultStatus,
    derivation: tuple[DerivationStep, ...] = (),
    investigation_requests: tuple[InvestigationRequest, ...] = (),
    framing_notes: tuple[FramingNote, ...] = (),
    extensions: dict | None = None,
    program=None,
    stmt=None,
    structural_result=None,
    bounds_result=None,
    numeric_result=None,
    confidence: float | None = None,
) -> DataGapReport | None:
    """Synthesize a DataGapReport from the result-envelope signals.

    Returns ``None`` when the question names no quantity — so nothing but
    framing can leave it short of data — and no framing or assumption gaps
    exist. For a question that does name one the returned report may still
    have ``gaps=()`` when fully solved — callers can distinguish "no need
    to ask" (None) from "asked and got a clean bill of health" (empty
    tuple).
    """
    extensions = extensions or {}

    must_disclose_gaps: list[DataGap] = []
    must_disclose_gaps.extend(
        _classify_unverified_proposal_edges(
            program, structural_result, stmt, extensions,
        )
    )
    must_disclose_gaps.extend(_classify_iv_assumption(extensions))
    must_disclose_gaps.extend(_classify_mediation_assumptions(extensions))
    must_disclose_gaps.extend(_classify_transport_assumptions(extensions))
    must_disclose_gaps.extend(_classify_llm_ambiguities(extensions))
    must_disclose_gaps.extend(_classify_bounds_not_point(bounds_result))
    must_disclose_gaps.extend(_classify_low_confidence(confidence))
    must_disclose_gaps.extend(_classify_front_door_assumptions(
        derivation, program=program, stmt=stmt,
    ))
    must_disclose_gaps.extend(_classify_counterfactual_assumptions(
        derivation, status, query_kind,
    ))
    must_disclose_gaps.extend(_classify_graph_learned_from_data(program))
    must_disclose_gaps.extend(_classify_unmeasured_confounder_risk(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
    ))
    must_disclose_gaps.extend(_classify_measurement_error_concern(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions,
    ))
    must_disclose_gaps.extend(_classify_unattempted_layer_dispatch_conflict(
        stmt=stmt, extensions=extensions,
    ))
    must_disclose_gaps.extend(_classify_collider_conditioning_opens_backdoor(
        program=program, stmt=stmt,
    ))
    must_disclose_gaps.extend(_classify_selection_on_collider_opens_path(
        program=program, stmt=stmt,
    ))
    must_disclose_gaps.extend(_classify_ill_defined_intervention_versions(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions,
    ))
    must_disclose_gaps.extend(_classify_dichotomized_continuous_measure(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions,
    ))

    # A question that names no quantity cannot be short of the data for
    # one: framing is the only channel that can leave it wanting, and
    # must-disclose caveats keep the report alive so a renderer still sees
    # the structural caveats the kernel detected.
    #
    # Read from the question rather than listed here. The list also named
    # ``probability``, which does name a quantity — so a probability query
    # whose kernel had raised MISSING_DISTRIBUTION returned before the
    # species pass and reached the reader with no report, indistinguishable
    # from a clean bill of health.
    question = questions.reading_of(query_kind.value)
    if (
        not question.names_an_estimand
        and not framing_notes
        and not must_disclose_gaps
    ):
        return None

    gaps: list[DataGap] = list(must_disclose_gaps)
    gaps.extend(_classify_unidentifiable(derivation))
    # Every investigation item, as the species the kernel declared for it.
    # Total over the channel by construction, so nothing downstream has to
    # sweep for items no pass claimed.
    gaps.extend(_classify_investigation_items(investigation_requests, query_kind))
    gaps.extend(_classify_missing_population_distribution(extensions))
    gaps.extend(_classify_missing_iv(derivation))
    gaps.extend(_classify_missing_mediator(extensions, investigation_requests))
    gaps.extend(_classify_transport_target_distribution(extensions))
    gaps.extend(_classify_ambiguous_variable(framing_notes, stmt))
    gaps.extend(_classify_dose_response_data(program, stmt, derivation))

    gaps = _rewrite_iv_aware_alternatives(gaps, bounds_result)
    gaps.sort(key=_gap_sort_key)
    answer_tier = _compute_answer_tier(
        query_kind, gaps, bounds_result, status, numeric_result, stmt,
    )
    if answer_tier is AnswerTier.NONE:
        gaps = _withdraw_interval_offers(gaps, query_kind)
    summary = _make_summary(gaps, answer_tier)
    actionable = _make_actionable_steps(gaps)
    return DataGapReport(
        summary=summary,
        gaps=tuple(gaps),
        actionable_next_steps=tuple(actionable),
        answer_tier=answer_tier,
    )


def _interval_offer(query_kind: QueryKind) -> str | None:
    """The one sentence that offers this question's interval instead of a
    point, or None where it has no interval to offer.

    Built here rather than written out, so the offer and the withdrawal
    below are the same string by construction: a report that has just said
    no interval is reachable must not leave one on offer beside it, and
    matching a promise by substring is how that check would rot.
    """
    fallback = questions.reading_of(query_kind.value).interval_fallback
    return None if fallback is None else f"接受 {fallback} 给区间答案"


def _withdraw_interval_offers(
    gaps: list[DataGap], query_kind: QueryKind,
) -> list[DataGap]:
    """Take back the interval a NONE tier has just ruled out.

    The tier is the report's own word on what is still reachable; a gap
    still advising "accept bounds for an interval answer" contradicts it
    in the same breath, and the reader acts on the gap. Only the offer
    this module generated is withdrawn — a concrete "已计算 bounds" line
    means bounds exist, and a result carrying those does not reach NONE.
    """
    from dataclasses import replace as _replace

    offer = _interval_offer(query_kind)
    if offer is None:
        return gaps
    out: list[DataGap] = []
    for gap in gaps:
        kept = tuple(a for a in gap.alternative_paths if a != offer)
        out.append(
            gap if len(kept) == len(gap.alternative_paths)
            else _replace(gap, alternative_paths=kept)
        )
    return out


def _point_is_premise_blocked(stmt) -> bool:
    """Whether a premise the query did not declare, rather than absent
    data, is what stands between this query and a point.

    Probabilities of causation are Tian-Pearl intervals; monotonicity is
    what collapses them to points (Thm 3), and it is declared on the query
    rather than found in the data. Undeclared, no amount of data produces
    a point, so a tier read off the data gaps alone promises a number that
    cannot arrive.

    Sound only because the other half of the shape is settled by then. The
    interval Tian-Pearl gives needs P(Y=1|do(X)) as much as the point
    does, and the dispatcher used to return on the missing observational
    joint before it asked whether those risks were identifiable — so this
    predicate, applied to a result from that path, would have promised
    bounds an unobserved confounder rules out. The dispatcher now obtains
    both before reporting either, and an unidentifiable effect arrives
    here as the gap that outranks this.
    """
    query = getattr(stmt, "query", None)
    return isinstance(query, CausationQuery) and not query.monotonic


def _compute_answer_tier(
    query_kind: QueryKind,
    gaps: list[DataGap],
    bounds_result,
    status: ResultStatus,
    numeric_result=None,
    stmt=None,
) -> AnswerTier | None:
    """The strongest answer available, orthogonal to gap severity.

    Two steps. First, is the POINT estimand blocked? — keyed on the
    authoritative "point ID failed" signals, NOT on bounds presence:
    bounds are attached to EVERY needs_investigation binary/discrete
    effect as an assumption-free floor (scheduler ``_attach_bounds_result``,
    Manski always-available), so a point-IDENTIFIED-but-missing-θ effect
    (e.g. clean backdoor) carries Manski bounds too. The real "point
    blocked" signals are:
    - the ``unidentifiable_no_admissible_set`` gap (effect point ID
      failed), or
    - a counterfactual that stopped at NEEDS_ASSUMPTION (needs an
      untestable assumption) or COUNTERFACTUAL_BOUNDED (only an interval).
    If not blocked, a point estimand is in hand — solved, or
    identifiable-but-missing-θ (a data gap, still a point).

    Second, when blocked, an interval in hand makes it INTERVAL; otherwise
    (nothing, or a trivial [0, 1]) NONE. An interval can arrive by either
    of two channels and both count: ``bounds_result``, the effect query's
    Manski / IV floor, and ``numeric_result.interval``, where a bounded
    counterfactual carries its own Tian-Pearl interval. Reading only the
    first reported "no answer available" for counterfactuals that had a
    perfectly good interval sitting in the envelope.

    The gate is the question: a tier is what the answer to it can be, so a
    question that names no quantity has none. It used to be a list of three
    kinds, which left the other seven at None here while the estimation
    layer — which reads no such list — wrote a tier for them from the
    number it had just produced. The same query then carried a tier or not
    depending on which entrance the caller used.

    Past the gate, one thing the data gaps cannot say is whether a premise
    the caller withheld has already fixed the answer's shape —
    ``_point_is_premise_blocked``.

    A tier is a claim about a question that stands. ``OUTSIDE_LANGUAGE``
    says this one does not: not that the data are short, but that the
    quantity is undefined as asked — probabilities of causation over a
    non-binary cause, a counterfactual whose bounds problem is infeasible.
    Neither the data nor a withheld premise can produce an answer, so
    neither what is in hand nor the shape an answer would take is a claim
    worth making, and the forward-looking branch below would make the
    second one.
    """
    question = questions.reading_of(query_kind.value)
    if not question.names_an_estimand:
        return None
    if status is ResultStatus.OUTSIDE_LANGUAGE:
        return AnswerTier.NONE
    identification_blocked = (
        status in (
            ResultStatus.NEEDS_ASSUMPTION,
            ResultStatus.COUNTERFACTUAL_BOUNDED,
        )
        or any(
            g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET for g in gaps
        )
    )
    premise_blocked = _point_is_premise_blocked(stmt)
    if not identification_blocked and not premise_blocked:
        return AnswerTier.POINT
    if bounds_result is not None and not getattr(
        bounds_result, "width_when_uninformative", False
    ):
        return AnswerTier.INTERVAL
    interval = getattr(numeric_result, "interval", None)
    if interval is not None and not (
        interval.low <= 0.0 and interval.high >= 1.0
    ):
        return AnswerTier.INTERVAL
    if (
        premise_blocked
        and not identification_blocked
        and numeric_result is None
        and question.interval_fallback is not None
    ):
        # Nothing computed yet, so the tier is the shape the answer will
        # take rather than what is in hand — and with the premise the only
        # thing in the way, that shape is the interval. NONE would say the
        # data cannot produce an answer, when what they cannot produce is
        # a point. Identification having failed outranks this: then the
        # bounds are out of reach too, and NONE is the honest word.
        return AnswerTier.INTERVAL
    return AnswerTier.NONE


_FIND_IV_ADVICE = "找一个满足 IV 条件的工具变量"


def _rewrite_iv_aware_alternatives(
    gaps: list[DataGap],
    bounds_result,
) -> list[DataGap]:
    """Instrument-aware repair of the static unidentifiable advice.

    When IV bounds were already computed from a declared instrument
    (``bounds_result.method == balke_pearl_iv``), the boilerplate "go
    find an instrument satisfying the IV conditions" alternative on an
    ``unidentifiable_no_admissible_set`` gap is self-contradictory — the
    interval that same gap points at LITERALLY came from that instrument.
    Replace only that one line with the honest next step: an instrument
    is already in hand; tightening the interval to a POINT estimate needs
    an extra assumption (monotonicity -> LATE / linearity -> 2SLS). The
    other alternatives (measure the confounder, run an RCT) are untouched.

    Detected purely from ``bounds_result`` — no graph walk, no extension
    stamping, so it cannot fire a spurious second gap. Real-usage probe,
    2026-06-15.
    """
    from dataclasses import replace

    method = getattr(bounds_result, "method", None)
    method_value = getattr(method, "value", method)
    if method_value != "balke_pearl_iv":
        return gaps
    out: list[DataGap] = []
    for g in gaps:
        if (
            g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
            and _FIND_IV_ADVICE in g.alternative_paths
        ):
            out.append(replace(
                g,
                alternative_paths=tuple(
                    (
                        # NB: deliberately avoids the tokens in scheduler's
                        # _BOUNDS_HINT_TOKENS ("bounds" / "Manski" /
                        # "Balke-Pearl bounds") so _reconcile_alt_paths_with
                        # _bounds keeps this as a distinct constructive
                        # alternative instead of collapsing it into the
                        # generic "已计算 bounds" pointer.
                        "工具变量已声明并已用于给出区间；要把区间收紧成点"
                        "估计，需补一个额外假设：monotonicity（→ LATE/Wald）"
                        "或 linearity（→ 2SLS/ATE）"
                    ) if a == _FIND_IV_ADVICE else a
                    for a in g.alternative_paths
                ),
            ))
        else:
            out.append(g)
    return out


def _classify_unverified_proposal_edges(
    program,
    structural_result,
    stmt,
    extensions: dict,
) -> Iterable[DataGap]:
    """The structural answer rests on edges the upstream LLM proposed
    (``annotations.source == "llm_proposal"``) rather than
    evidence-backed edges. Reasoning replays the LLM's own assumption
    instead of independently verifying it — surfaced as INFORMATIONAL so
    the renderer can disclose without overstating risk.

    Both directed (``CauseStatement``) and bidirected
    (``BidirectedStatement``, latent common cause) edges are scanned.
    Bidirected proposal edges are particularly load-bearing for IV /
    front-door identification, where the latent confounder is the
    *reason* an alternative identification strategy is needed.

    Edges are flagged via two complementary signals (either suffices):

    1. **supporting_paths** — concrete on cause / assoc results; each
       consecutive node pair on a returned path is an edge that was
       actually traversed.

    2. **DAG walk** — for every other query kind (effect / identify /
       IV / mediation / counterfactual), enumerate simple directed
       paths in the program-derived DAG between every pair of
       query-relevant predicates (intervention / target / mediator /
       given), plus instrument / adjustment-set predicates pulled from
       ``extensions`` when the dispatcher exposed them. Any
       proposal edge lying on such a path is load-bearing.

    Bidirected proposal edges are flagged when either endpoint is a
    query-relevant predicate (they are undirected, so 'on the path' is
    not the natural test — incidence on a query node is).
    """
    if program is None:
        return

    proposal_edges, adjacency = _build_dag_with_proposals(program)
    bidirected_proposals = _collect_bidirected_proposal_pairs(program)
    if not proposal_edges and not bidirected_proposals:
        return

    flagged: set[tuple[str, str]] = set()

    paths = getattr(structural_result, "supporting_paths", ()) or ()
    for path in paths:
        for i in range(len(path) - 1):
            a_pred = path[i].split("(", 1)[0]
            b_pred = path[i + 1].split("(", 1)[0]
            if (a_pred, b_pred) in proposal_edges:
                flagged.add((a_pred, b_pred))

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
                        if edge in proposal_edges:
                            flagged.add(edge)

    if bidirected_proposals and relevant:
        for left, right in bidirected_proposals:
            if left in relevant or right in relevant:
                # Render with ↔ so the renderer distinguishes from
                # directed edges. Tuple ordered for deterministic output.
                a, b = sorted((left, right))
                flagged.add((a, f"↔{b}"))

    edge_sources = _index_edge_sources(program)
    edge_confidences = _index_edge_confidence(program)
    for frm, to in sorted(flagged):
        # Look up the actual source string so the description can name
        # 'LLM hypothesis' vs 'PC algorithm output' specifically.
        bidirected = to.startswith("↔")
        clean_to = to[1:] if bidirected else to
        source_key = (
            ("bidirected", tuple(sorted((frm, clean_to))))
            if bidirected
            else ("cause", (frm, clean_to))
        )
        source_str = edge_sources.get(source_key, "")
        confidence = edge_confidences.get(source_key)
        edge_render = f"{frm} ↔ {clean_to}" if bidirected else f"{frm} → {to}"
        if source_str.startswith("discovery:"):
            algo = source_str.split(":", 1)[1]
            description = (
                f"结构性回答途径上的边 `{edge_render}` 是因果发现算法 "
                f"`{algo.upper()}` 从数据中学出的，结果以算法假设（如 PC: "
                f"忠实性 + 因果充足性；LiNGAM: 线性 + 非高斯）为前提。"
            )
            if confidence is not None:
                description += (
                    f"自助法稳定度 {confidence:.0%}（该边在此比例的数据重"
                    "采样中重现；越低越可能是采样噪声，越应复核）。"
                )
        else:
            description = (
                f"结构性回答途径上的边 `{edge_render}` 是上游 LLM 提出的"
                f"假设（annotations.source = llm_proposal），不是经证据"
                f"支持的边。当前回答相当于复述这条假设，而非独立验证。"
            )
        yield DataGap(
            kind=GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            if_provided="可换成证据支持的边或外部文献的引用",
            alternative_paths=(
                "提供支持这条边的研究 / 数据来源",
                "改为询问'若该边成立则…'的条件性问题",
            ),
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=(
                        f"program:bidirected:{frm}↔{clean_to}:annotations.source"
                        if bidirected
                        else f"program:cause:{frm}->{to}:annotations.source"
                    ),
                ),
            ),
        )


def _index_edge_sources(program) -> dict[tuple[str, tuple[str, ...]], str]:
    """Build a lookup from (kind, predicate-pair) to the verbatim
    annotations.source string. ``kind`` is ``"cause"`` or ``"bidirected"``.
    Used by the proposal-edge classifier to render description text that
    names the *kind* of non-evidence source (LLM vs discovery algorithm).
    """
    out: dict[tuple[str, tuple[str, ...]], str] = {}
    for st in program.statements:
        ann = getattr(st, "annotations", None)
        if ann is None or ann.source is None:
            continue
        if isinstance(st, CauseStatement):
            out[("cause", (st.from_atom.predicate, st.to_atom.predicate))] = ann.source
        elif isinstance(st, BidirectedStatement):
            pair = tuple(sorted((st.left.predicate, st.right.predicate)))
            out[("bidirected", pair)] = ann.source
    return out


def _index_edge_confidence(program) -> dict[tuple[str, tuple[str, ...]], float]:
    """Mirror of ``_index_edge_sources`` capturing ``annotations.confidence``
    (bootstrap edge stability, when a discovery run recorded it) so the
    proposal-edge description can report how often the edge survived
    resampling — a low fraction flags a likely artefact."""
    out: dict[tuple[str, tuple[str, ...]], float] = {}
    for st in program.statements:
        ann = getattr(st, "annotations", None)
        if ann is None or ann.confidence is None:
            continue
        if isinstance(st, CauseStatement):
            out[("cause", (st.from_atom.predicate, st.to_atom.predicate))] = ann.confidence
        elif isinstance(st, BidirectedStatement):
            pair = tuple(sorted((st.left.predicate, st.right.predicate)))
            out[("bidirected", pair)] = ann.confidence
    return out


def _collect_bidirected_proposal_pairs(
    program,
) -> set[tuple[str, str]]:
    """Bidirected (latent common cause) statements with a non-evidence
    ``annotations.source``. Returned unordered as sets of (left, right)
    predicate pairs."""
    pairs: set[tuple[str, str]] = set()
    for st in program.statements:
        if not isinstance(st, BidirectedStatement):
            continue
        ann = getattr(st, "annotations", None)
        if ann is None or not _is_non_evidence_source(ann.source):
            continue
        pairs.add((st.left.predicate, st.right.predicate))
    return pairs


def _build_dag_with_proposals(
    program,
) -> tuple[set[tuple[str, str]], dict[str, list[str]]]:
    """Pull the predicate-level DAG and the subset of non-evidence edges
    out of program.statements in a single pass.

    "Non-evidence" covers both ``annotations.source == "llm_proposal"``
    (LLM hypothesis) and ``annotations.source`` starting with
    ``"discovery:"`` (PC / FCI / LiNGAM algorithmic output). Both share
    the load-bearing-without-citation property.
    """
    proposal_edges: set[tuple[str, str]] = set()
    adjacency: dict[str, list[str]] = {}
    for st in program.statements:
        if not isinstance(st, CauseStatement):
            continue
        edge = (st.from_atom.predicate, st.to_atom.predicate)
        adjacency.setdefault(edge[0], []).append(edge[1])
        ann = getattr(st, "annotations", None)
        if ann is not None and _is_non_evidence_source(ann.source):
            proposal_edges.add(edge)
    return proposal_edges, adjacency


def _is_non_evidence_source(source: str | None) -> bool:
    """An edge source counts as non-evidence (must-disclose) when it is
    ``"llm_proposal"`` or starts with ``"discovery:"``."""
    if source is None:
        return False
    if source == "llm_proposal":
        return True
    if source.startswith("discovery:"):
        return True
    return False


def _query_relevant_predicates_for_path_walk(
    stmt, extensions: dict,
) -> frozenset[str]:
    """Predicates whose pairwise directed paths are load-bearing for the
    query. Combines query atoms (via ``_query_referenced_predicates``)
    with structural artifacts the dispatcher exposed in ``extensions``:
    instrument (IV), adjustment set / mediator adjustment, mediator.
    """
    base = set(_query_referenced_predicates(stmt))

    iv = (extensions or {}).get(blocks.IV_IDENTIFICATION) or {}
    instrument = iv.get("instrument")
    if instrument:
        base.add(str(instrument).split("(", 1)[0])
    for entry in iv.get("conditioning") or ():
        base.add(str(entry).split("(", 1)[0])

    view = _mediation_view(extensions)
    if view is not None:
        nde = view.block.get("nde_nie") or {}
        cde = view.block.get("cde") or {}
        for entry in (nde.get("adjustment") or ()):
            base.add(str(entry).split("(", 1)[0])
        for entry in (cde.get("adjustment") or ()):
            base.add(str(entry).split("(", 1)[0])
        for mediator in view.mediators:
            base.add(mediator.split("(", 1)[0])

    return frozenset(base)


def _classify_iv_assumption(extensions: dict) -> Iterable[DataGap]:
    """IV identification rests on monotonicity (LATE/Wald) or linearity
    (2SLS/ATE). The extension carries the wording verbatim; surface as a
    must-disclose caveat so the renderer cannot present an IV estimate
    as an unconditional ATE."""
    iv = (extensions or {}).get(blocks.IV_IDENTIFICATION) or {}
    assumption = iv.get("required_assumption")
    instrument = iv.get("instrument")
    if not assumption:
        return
    yield DataGap(
        kind=GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"IV 识别（工具变量 `{instrument}`）的有效性以下列假设为前提："
            f"{assumption}。读 IV 估计前应明确这条假设是否在你的场景下成立。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.iv_identification.required_assumption",
            ),
        ),
    )


class _MediationView(NamedTuple):
    """One mediation decomposition, normalized across its two shapes.

    The gap layer asks the same four things of a decomposition however it was
    asked for — is it well formed, which mediators is it about, which branches
    identified, on what assumptions. The scheduler writes the two shapes under
    DIFFERENT extension keys, with ``mediator`` / ``mediators`` and
    ``mediator_valid`` / ``mediator_set_valid``. Binding the producers below to
    this view rather than to a key is what keeps the next mediation variant
    from silently dropping out of the disclosure layer the way the block did.
    """

    key: str                      # the extension key, for provenance refs
    joint: bool
    block: dict
    valid: bool
    mediators: tuple[str, ...]
    subject: str                  # display form: `M` or `{M₁, M₂}`


def _mediation_view(extensions: dict) -> "_MediationView | None":
    """The mediation decomposition on this result, whichever shape it took."""
    ext = extensions or {}
    for key, joint in (
        (blocks.MEDIATION_DECOMPOSITION, False),
        (blocks.MEDIATION_JOINT_DECOMPOSITION, True),
    ):
        block = ext.get(key)
        if not isinstance(block, dict):
            continue
        if joint:
            mediators = tuple(str(m) for m in (block.get("mediators") or ()))
            subject = (
                "{" + ", ".join(mediators) + "}" if mediators
                else "<unknown mediator set>"
            )
            valid = bool(block.get("mediator_set_valid"))
        else:
            one = block.get("mediator")
            mediators = (str(one),) if one else ()
            subject = str(one) if one else "<unknown mediator>"
            valid = bool(block.get("mediator_valid"))
        return _MediationView(
            key=key, joint=joint, block=block, valid=valid,
            mediators=mediators, subject=subject,
        )
    return None


def _classify_mediation_assumptions(
    extensions: dict,
) -> Iterable[DataGap]:
    """NDE/NIE / CDE identification each carry a non-empty `assumptions`
    list when identifiable. Surface a single caveat per identifiable
    branch so the renderer cannot read 'identifiable: true' as
    unconditional.

    A mediator BLOCK rests on different premises than a single mediator
    (VanderWeele-Vansteelandt joint conditions; the block CDE holds the whole
    set at a reference level), and it carries them in its own ``assumptions``
    list — so the substance comes from the block and only the subject differs.
    The block's naming also has to say what it does NOT claim: the set is
    decomposed as a whole, never split into per-path shares.
    """
    view = _mediation_view(extensions)
    if view is None or not view.valid:
        return
    for branch_name, branch_key in (("NDE/NIE", "nde_nie"), ("CDE", "cde")):
        branch = view.block.get(branch_key) or {}
        if not branch.get("identifiable"):
            continue
        assumptions = branch.get("assumptions") or ()
        if not assumptions:
            continue
        subject_clause = (
            f"（中介组 {view.subject}，作为一整组分解，不拆到单条路径）"
            if view.joint else f"（中介 {view.subject}）"
        )
        yield DataGap(
            kind=GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=(
                f"中介分解 {branch_name} 标识为可识别，前提是以下假设成立："
                f"{', '.join(assumptions)}。{subject_clause}"
            ),
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=f"extensions.{view.key}.{branch_key}.assumptions",
                ),
            ),
        )


def _classify_transport_assumptions(
    extensions: dict,
) -> Iterable[DataGap]:
    """Transport identification (Bareinboim-Pearl) requires
    S-admissibility plus correct selection-node specification. The
    transferred estimate is invalid outside those assumptions."""
    transport = (extensions or {}).get(blocks.TRANSPORT_IDENTIFICATION) or {}
    if not transport:
        return
    src_pop = transport.get("source_population", "<源人群>")
    tgt_pop = transport.get("target_population", "<目标人群>")
    yield DataGap(
        kind=GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"将估计从 {src_pop} 转移到 {tgt_pop} 的有效性以 S-admissibility "
            f"为前提：声明的 selection_nodes 必须正确捕获两人群间分布差异。"
        ),
        blocks=GapBlocks.TRANSPORT,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.transport_identification",
            ),
        ),
    )


def _classify_llm_ambiguities(extensions: dict) -> Iterable[DataGap]:
    """LLM-declared ambiguities the kernel did not resolve into a
    structural decision (reciprocal causation, mechanism vs existence,
    mediator choice). Renderer must surface the LLM's own uncertainty —
    leaving these unspoken would make the answer look confident when the
    upstream itself wasn't."""
    ambiguities = (extensions or {}).get(blocks.AMBIGUITIES) or ()
    for amb in ambiguities:
        if not isinstance(amb, dict):
            continue
        kind = amb.get("kind", "<unspecified>")
        rationale = amb.get("rationale") or amb.get("note") or ""
        # dose_response_query has its own dedicated gap_kind; skip.
        if kind == "dose_response_query":
            continue
        suffix = f"：{rationale}" if rationale else ""
        yield DataGap(
            kind=GapKind.LLM_DECLARED_AMBIGUITY,
            severity=GapSeverity.INFORMATIONAL,
            description=(
                f"上游 LLM 标记了不确定性 `{kind}`{suffix}。"
                f"答案的解读应将其考虑在内。"
            ),
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=f"extensions.ambiguities[{kind}]",
                ),
            ),
        )


# Threshold below which composite confidence triggers a must-disclose
# caveat. 0.6 is the conventional "substantial uncertainty" line —
# anything ≥ 0.6 gets through silently to keep the channel signal-rich
# rather than firing on every routine answer.
_LOW_CONFIDENCE_THRESHOLD: float = 0.6


def _classify_low_confidence(confidence: float | None) -> Iterable[DataGap]:
    """Composite confidence (min across slot-level annotations) below the
    threshold means at least one input statement carries substantial
    uncertainty. The answer inherits that uncertainty — surface so it
    does not read as a clean point estimate."""
    if confidence is None:
        return
    if confidence >= _LOW_CONFIDENCE_THRESHOLD:
        return
    yield DataGap(
        kind=GapKind.LOW_CONFIDENCE_INPUT_DATA,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"答案的复合可信度为 {confidence:.2f}（< {_LOW_CONFIDENCE_THRESHOLD}）— "
            f"至少有一项输入语句的置信度较低，结果应视为不确定的。具体的薄弱"
            f"环节见 `confidence_sources` 中标记 is_weakest=true 的条目。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="result.confidence",
            ),
        ),
    )


_FRONT_DOOR_DERIVATION_RULES: frozenset[str] = frozenset({
    "front_door_criterion",
    "front_door_adjustment_formula",
    "identify_via_front_door",
})


def _classify_front_door_assumptions(
    derivation: tuple[DerivationStep, ...],
    *,
    program=None,
    stmt=None,
) -> Iterable[DataGap]:
    """Front-door identification rests on Pearl's three graphical premises
    plus consistency. Primary signal is a derivation step with rule in
    ``_FRONT_DOOR_DERIVATION_RULES``. Fallback signal: program-shape
    detection of a front-door pattern (X↔Y bidirected + at least one
    M with X→M and M→Y), used when status is NEEDS_INVESTIGATION due
    to missing theta and the kernel skipped recording the
    identify_via_front_door step. Same fallback pattern as
    ``_classify_unmeasured_confounder_risk``.
    """
    description = (
        "前门识别（Pearl front-door criterion）的有效性以下列假设为前提："
        "(1) 中介集 M 阻断 X→Y 的所有有向路径；"
        "(2) 不存在未阻断的 X→M 后门路径；"
        "(3) 所有 M→Y 后门路径已被 X 阻断；"
        "(4) consistency of potential outcomes。"
        "若任一假设不成立，前门估计失效。"
    )
    triggering = next(
        (
            step for step in derivation
            if step.rule in _FRONT_DOOR_DERIVATION_RULES
            and not _step_failed(step)
        ),
        None,
    )
    if triggering is not None:
        yield DataGap(
            kind=GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.DERIVATION_STEP,
                    ref_id=triggering.step_id or triggering.rule,
                ),
            ),
        )
        return
    if _has_front_door_pattern(program, stmt):
        yield DataGap(
            kind=GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id="program:front_door_pattern",
                ),
            ),
        )


def _has_front_door_pattern(program, stmt) -> bool:
    """Detect front-door identification pattern from program shape:
    bidirected edge between intervention X and target Y AND at least
    one mediator M with X→M and M→Y. Used as a fallback when the
    derivation chain is empty (NEEDS_INVESTIGATION due to missing theta)."""
    if program is None or stmt is None:
        return False
    q = getattr(stmt, "query", None)
    intervention = getattr(q, "intervention", None)
    target = getattr(q, "target", None)
    if intervention is None or target is None:
        return False
    # Some queries hold ValuedAtom / Intervention with `.atom`; others hold
    # Atom directly. Fall through with getattr to handle both.
    x_atom = getattr(intervention, "atom", intervention)
    y_atom = getattr(target, "atom", target)
    x_pred = getattr(x_atom, "predicate", None)
    y_pred = getattr(y_atom, "predicate", None)
    if x_pred is None or y_pred is None:
        return False
    has_bidirected_xy = False
    children_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, BidirectedStatement):
            pair = {st.left.predicate, st.right.predicate}
            if pair == {x_pred, y_pred}:
                has_bidirected_xy = True
        if isinstance(st, CauseStatement):
            children_of.setdefault(
                st.from_atom.predicate, set()
            ).add(st.to_atom.predicate)
    if not has_bidirected_xy:
        return False
    for mediator in children_of.get(x_pred, ()):
        if mediator in (x_pred, y_pred):
            continue
        if y_pred in children_of.get(mediator, ()):
            return True
    return False


_COUNTERFACTUAL_DERIVATION_RULES: frozenset[str] = frozenset({
    "counterfactual_cell_bounds",
    "counterfactual_twin_network",
    "counterfactual_consistency",
})


def _classify_counterfactual_assumptions(
    derivation: tuple[DerivationStep, ...],
    status: ResultStatus,
    query_kind: QueryKind,
) -> Iterable[DataGap]:
    """Counterfactual identification rests on premises no data can check,
    and the list is layered: consistency + composition always; the source
    of the interventional risk whenever the two worlds differ (a cell
    across worlds is solved from P(Y=1|do x'), so whatever licences that
    number — an adjustment set being sufficient, the graph being right
    enough for the ID algorithm to identify the arm, or a randomized
    experiment — is carried into the answer); and monotonicity only when
    it was declared, where it sharpens an interval into a point rather
    than being what makes an answer possible at all.

    The user asking a counterfactual question is itself the trigger — the
    caveat applies whether the kernel solved the cell, bounded it, or
    stopped for missing inputs. Without it a stalled counterfactual
    surfaces only as a generic 'missing assumption' gap and the L3 vs L2
    distinction is lost in rendering."""
    triggering = next(
        (
            step for step in derivation
            if step.rule in _COUNTERFACTUAL_DERIVATION_RULES
            and not _step_failed(step)
        ),
        None,
    )
    is_counterfactual_status = status in (
        ResultStatus.COUNTERFACTUAL_SOLVED,
        ResultStatus.COUNTERFACTUAL_BOUNDED,
    )
    is_counterfactual_query = query_kind == QueryKind.COUNTERFACTUAL
    if (
        triggering is None
        and not is_counterfactual_status
        and not is_counterfactual_query
    ):
        return
    yield DataGap(
        kind=GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            "反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的潜在结果）"
            "+ composition 公理为前提；跨世界的格子还要用到一臂干预风险 "
            "P(Y=1|do X)，它凭什么成立（调整集充分 / 图结构正确到 general ID "
            "能识别 / 来自随机实验）也一并被继承；"
            "单调性若声明，只是把区间收紧成点的额外前提。"
            "这些假设都无法从数据本身验证。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP,
                ref_id=triggering.step_id or triggering.rule,
            )
            if triggering
            else GapProvenanceRef(
                # The common counterfactual case is NEEDS_ASSUMPTION /
                # counterfactual-query-kind, which carries no derivation
                # chain — so there is no derivation step to cite. The
                # trigger is the query/status shape; cite it as a
                # verifier_check, which T10-1 accepts as free-form and
                # does NOT require to resolve against the derivation chain
                # (mirrors _classify_front_door_assumptions' program-shape
                # fallback). Citing a DERIVATION_STEP here produced a
                # dangling provenance that the kernel's own T10-1 auditor
                # rejected on every derivation-less counterfactual result.
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=(
                    "counterfactual_status"
                    if is_counterfactual_status
                    else "counterfactual_query_kind"
                ),
            ),
        ),
    )


def _classify_bounds_not_point(bounds_result) -> Iterable[DataGap]:
    """When ``bounds_result`` is non-null the answer is a symbolic
    interval, not a point estimate. Surfaces both the method-vs-point
    distinction and the method's specific assumptions (e.g. Balke-Pearl
    needs IV1/IV2/IV3) — without these the bounds read like a point
    with confidence intervals."""
    if bounds_result is None:
        return
    method = getattr(bounds_result, "method", None)
    # ``.value`` when it is an enum member, the thing itself otherwise.
    method_name = str(getattr(method, "value", method))
    uninformative = getattr(bounds_result, "width_when_uninformative", False)
    assumptions = getattr(bounds_result, "assumptions", ()) or ()
    pieces: list[str] = [
        f"答案是 `{method_name}` 给出的符号区间，不是点估计"
    ]
    if uninformative:
        pieces.append("（且区间为非信息性 [0,1] / [-1,1]，无实际辨别力）")
    pieces.append("。渲染时必须明示这是 bounds 而非具体数值")
    if assumptions:
        pieces.append(
            f"。区间的有效性以以下假设为前提：{', '.join(assumptions)}"
        )
    pieces.append("。")
    yield DataGap(
        kind=GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
        severity=GapSeverity.INFORMATIONAL,
        description="".join(pieces),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="bounds_result",
            ),
        ),
    )


def _classify_graph_learned_from_data(program) -> Iterable[DataGap]:
    """When ``program.extensions.discovery_metadata`` is populated, the
    DAG (or part of it) was learned from data by a causal-discovery
    algorithm. The user must know — without disclosure they assume the
    graph came from domain knowledge.

    Reads from ``program.extensions`` rather than ``result.extensions``
    because discovery is a program-shape signal, not a per-query one.
    """
    if program is None:
        return
    program_ext = getattr(program, "extensions", None) or {}
    metadata = program_ext.get("discovery_metadata") or {}
    if not metadata:
        return
    algo = metadata.get("algorithm", "<unknown>")
    alpha = metadata.get("alpha")
    n = metadata.get("sample_size")
    pieces = [
        f"DAG 是由因果发现算法 `{algo.upper()}` 从数据中学出的，不是用"
        f"领域知识手工声明的。"
    ]
    if alpha is not None:
        pieces.append(f"显著性阈值 α = {alpha}。")
    if n is not None:
        pieces.append(f"样本量 N = {n}。")
    pieces.append(
        "结果继承算法的核心假设："
        "PC 需要忠实性 (faithfulness) + 因果充足性 (causal sufficiency)；"
        "FCI 放宽因果充足性但仍需忠实性；"
        "LiNGAM 需要线性 + 非高斯噪声。"
    )
    violations = metadata.get("assumption_violations") or ()
    if violations:
        pieces.append(
            " 检测到当前数据上算法假设的具体违反："
            + "；".join(violations)
            + "。"
        )
    yield DataGap(
        kind=GapKind.GRAPH_LEARNED_FROM_DATA,
        severity=GapSeverity.INFORMATIONAL,
        description="".join(pieces),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.discovery_metadata",
            ),
        ),
    )


def _classify_unmeasured_confounder_risk(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
) -> Iterable[DataGap]:
    """User-provided DAG has at least one declared confounder (Z with
    Z→X and Z→Y) but no bidirected / latent-common-cause edges — the DAG
    implicitly asserts every confounder is measured. Real-world cases
    (HRT-CVD WHI 2002, vitamin D-CVD VITAL 2018, breastfeeding-IQ
    Der 2006) document large RCT-vs-observational gaps from *unmeasured*
    confounders surviving measured-covariate adjustment. Surfaced as
    INFORMATIONAL so the user is alerted *before* collecting data —
    sensitivity hooks (E-value) attach later at the numeric stage
    (Phase 8.2).

    Triggered by program-shape only (declared confounder pattern + no
    bidirected), not derivation, because the kernel does not always
    record an `identify_via_backdoor` step when status is
    NEEDS_INVESTIGATION due to missing theta.

    Suppressed when:
    - query is not effect (data needs don't apply)
    - bidirected edges declared (user already knows about latents)
    - status indicates identification failed (UNIDENTIFIABLE branches
      already surface their own gap_kind)
    - no Z with Z→X AND Z→Y in the declared edges (no confounder
      modeling — would fire on front-door / IV / mediator-only shapes
      where this advisory is unhelpful)
    """
    if program is None or stmt is None:
        return
    if query_kind != QueryKind.EFFECT:
        return
    if status not in (
        ResultStatus.STRUCTURALLY_SOLVED,
        ResultStatus.NUMERICALLY_SOLVED,
        ResultStatus.NEEDS_INVESTIGATION,
    ):
        return
    has_bidirected = any(
        isinstance(st, BidirectedStatement) for st in program.statements
    )
    if has_bidirected:
        return
    query_atom = getattr(stmt, "query", None)
    intervention = getattr(query_atom, "intervention", None)
    target = getattr(query_atom, "target", None)
    if intervention is None or target is None:
        return
    intervention_pred = intervention.atom.predicate
    target_pred = target.atom.predicate
    children_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, CauseStatement):
            children_of.setdefault(
                st.from_atom.predicate, set()
            ).add(st.to_atom.predicate)
    has_confounder = False
    for pred, children in children_of.items():
        if pred in (intervention_pred, target_pred):
            continue
        if intervention_pred in children and target_pred in children:
            has_confounder = True
            break
    if not has_confounder:
        return
    yield DataGap(
        kind=GapKind.UNMEASURED_CONFOUNDER_RISK,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            "Backdoor 识别假设你列出的 confounder 已经测全 —— DAG 里没"
            "有声明任何 bidirected / latent-common-cause 边。这是"
            " measured-covariate 调整后仍残留 unmeasured confounder 的"
            "典型场景。多个域有 well-documented RCT-vs-observational"
            "（或实验-vs-观察）反转：医学（HRT-CVD WHI 2002、"
            "vitamin D-CVD VITAL 2018）、劳动经济学（Card 1995 schooling"
            "-earnings 中的 ability bias）、教育评估（charter schools "
            "CREDO 2013 中的 parental motivation）。机制各域不同（"
            "healthy-user bias / ability bias / selection effects），"
            "但**结构教训一致**——measured 调整不够。拿到数据后跑 "
            "sensitivity analysis（E-value）量化对 unmeasured confounder"
            " 的稳健性，或在 DAG 里把怀疑的 latent 显式声明为 "
            "bidirected。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=(
            "若怀疑某 latent 共因，添加 bidirected 边；Themis 会改走 "
            "ADMG-aware（Tian / front-door / IV）识别策略并报对应的 "
            "structural gap"
        ),
        alternative_paths=(
            "数据到位后跑 E-value sensitivity analysis（Phase 8.2，对"
            " binary outcome 自动附）",
            "Triangulate with RCT / quasi-experimental data when available",
            "Hernán-Robins target trial emulation framework "
            "（per-protocol analysis with strict eligibility）",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="program:confounder_pattern:no_bidirected",
            ),
        ),
    )


# Patterns that, when they appear in a variable's ``measurement`` or
# ``observability`` field, structurally signal a documented
# noisy-measurement modality. These are exact substrings (lowercased
# match) of the *measurement metadata*, not free-form description text —
# the variable schema's ``measurement`` field is the contract anchor.
# Adding a pattern here is the single point where the classifier learns
# a new modality.
#
# Authoritative references behind each pattern:
# - "self-report" / "self report" / "self-reported" / "questionnaire" /
#   "ffq" / "24h recall" / "24-h recall" / "food-frequency":
#   non-differential outcome / exposure misclassification literature
#   (Hernán & Robins *What If* §9; Rothman/Greenland *Modern
#   Epidemiology* ch.9). FFQ vs urinary recovery biomarker for sodium
#   intake: Mente et al 2016 *Lancet* showing FFQ underestimation.
# - "single-occasion" / "single occasion" / "single visit" /
#   "single measurement" / "single reading" / "office reading":
#   regression-dilution bias documented in MacMahon et al 1990
#   *Lancet* 335:765 — single-occasion BP underestimates the BP-CHD
#   slope by ~60% from within-person variation alone, independent of
#   measurement device.
# - "proxy" / "surrogate": classical errors-in-variables (Fuller 1987
#   *Measurement Error Models*); attenuation toward null when the
#   proxy is noisier than the construct.
# - 中文 patterns mirror the English ones for upstream variable
#   declarations that came in via the Chinese A1 path.
_MEASUREMENT_ERROR_PATTERNS: tuple[str, ...] = (
    "self-report",
    "self report",
    "self-reported",
    "self reported",
    "questionnaire",
    "ffq",
    "food-frequency",
    "food frequency",
    "24h recall",
    "24-h recall",
    "24 hour recall",
    "24-hour recall",
    "dietary recall",
    "single-occasion",
    "single occasion",
    "single visit",
    "single measurement",
    "single reading",
    "office reading",
    "proxy",
    "surrogate",
    "自报告",
    "自我报告",
    "自报",
    "回忆",
    "问卷",
    "单次",
    "单次测量",
    "代理",
)


def _classify_measurement_error_concern(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
) -> Iterable[DataGap]:
    """At least one variable on the identification path declares a
    ``measurement`` or ``observability`` field whose value names a
    documented noisy-measurement pattern (self-report / questionnaire /
    single-occasion / proxy / 24h recall …). Surfaces measurement
    error as a structurally-detected concern *before* the user goes to
    collect more data — the same story that makes
    ``unmeasured_confounder_risk`` valuable, but for measurement
    rather than confounding.

    Documented data-limitation literature (board #8 was 0% before this
    kind):
    - MacMahon et al 1990 *Lancet* 335:765 — single-occasion BP
      regression dilution, ~60% attenuation of BP-CHD slope.
    - Hernán & Robins *What If* §9 — non-differential exposure /
      outcome misclassification dilutes effect estimates.
    - Mente et al 2016 *Lancet* — FFQ vs 24h urinary sodium
      gold-standard comparison.
    - Fuller 1987 *Measurement Error Models* — classical
      errors-in-variables / attenuation theorem.

    Severity IMPORTANT (not informational): regression-dilution and
    non-differential mis-classification are identification-impacting
    biases that distort the estimate's *magnitude*; users acting on
    the result without knowing this would systematically under-fit
    causal effects.

    Suppressed when:
    - query is not effect (the bias story is about effect-on-Y from X)
    - status indicates identification failed (don't pile caveats on
      already-failing branches)
    - extensions.ambiguities[*] already declares
      kind=='measurement_quality' (case 011 escape-hatch path — the
      upstream LLM already named it; firing both would be redundant)

    Trigger does not require the variable to be on a specific
    minimal-adjustment-set path; classifier deliberately includes any
    declared variable as long as it is the intervention, the target,
    or a directed predecessor of either. That includes the canonical
    case (X with self-reported measurement) AND confounder-on-the-
    backdoor-path cases (Z with 24h-recall measurement) — the
    bias story applies to both.

    What the noise COSTS, however, depends on the role, and the gap names
    the role for that reason. From the exposure it attenuates; from a
    covariate it leaves residual confounding in either direction; from a
    DISCRETE outcome it attenuates too — but from a continuous outcome
    under classical additive error it costs no bias at all, only precision,
    because conditional means are preserved. The gap still fires there:
    the noise is real and its price is worth knowing, and the numeric end
    quantifies that price rather than correcting a bias that is not there.
    """
    if program is None or stmt is None:
        return
    if query_kind != QueryKind.EFFECT:
        return
    if status not in (
        ResultStatus.STRUCTURALLY_SOLVED,
        ResultStatus.NUMERICALLY_SOLVED,
        ResultStatus.NEEDS_INVESTIGATION,
    ):
        return
    # Suppression: upstream LLM already declared a measurement_quality
    # ambiguity (case 011 path). The escape-hatch entry covers the user-
    # facing surface; firing this kind on top would double-disclose.
    if extensions:
        ambiguities = extensions.get(blocks.AMBIGUITIES) or ()
        for amb in ambiguities:
            if isinstance(amb, dict) and amb.get("kind") == "measurement_quality":
                return
    query_atom = getattr(stmt, "query", None)
    intervention = getattr(query_atom, "intervention", None)
    target = getattr(query_atom, "target", None)
    if intervention is None or target is None:
        return
    intervention_pred = intervention.atom.predicate
    target_pred = target.atom.predicate
    # Build the directed-ancestor closure of {intervention, target} so
    # confounders that funnel into either are included on the
    # identification path (board #4 of MacMahon: BP — measured single-
    # occasion — funnels into CHD via age & smoking).
    parents_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, CauseStatement):
            parents_of.setdefault(
                st.to_atom.predicate, set()
            ).add(st.from_atom.predicate)
    on_path: set[str] = {intervention_pred, target_pred}
    frontier: list[str] = [intervention_pred, target_pred]
    while frontier:
        node = frontier.pop()
        for parent in parents_of.get(node, ()):
            if parent not in on_path:
                on_path.add(parent)
                frontier.append(parent)
    flagged: list[tuple[str, str, str]] = []
    for st in program.statements:
        if not isinstance(st, VariableDeclaration):
            continue
        if st.predicate not in on_path:
            continue
        for field_name in ("measurement", "observability"):
            field_value = getattr(st, field_name, None)
            if not field_value:
                continue
            haystack = field_value.lower()
            for needle in _MEASUREMENT_ERROR_PATTERNS:
                if needle in haystack:
                    flagged.append((st.predicate, field_name, needle))
                    break
            else:
                continue
            break  # one (variable, field) per variable is enough
    if not flagged:
        return
    # Stable, deterministic listing for the description and provenance. The
    # ROLE is named alongside each variable because it is what decides the
    # consequence: the same noise attenuates from the exposure, leaves residual
    # confounding from a covariate, and — on a continuous outcome — costs only
    # precision. A list without roles reads as one undifferentiated threat.
    flagged.sort()

    def _role(pred: str) -> str:
        if pred == intervention_pred:
            return "暴露"
        if pred == target_pred:
            return "结局"
        return "路径上协变量"

    var_summary = ", ".join(
        f"{pred}〔{_role(pred)}〕({field}: 含 “{needle}”)"
        for pred, field, needle in flagged
    )
    yield DataGap(
        kind=GapKind.MEASUREMENT_ERROR_CONCERN,
        severity=GapSeverity.IMPORTANT,
        description=(
            "测量误差风险：识别路径上有变量声明了高噪声测量方式 — "
            f"{var_summary}。"
            " 经典文献：MacMahon 1990 Lancet 单次门诊 BP 测量"
            "因 within-person 变异导致 BP→CHD 斜率被 regression dilution "
            "向 0 衰减约 60%；Hernán & Robins What If §9 自报告 / "
            "问卷暴露的 non-differential mis-classification 同样使 "
            "估计值低估真效应；Fuller 1987 Measurement Error Models "
            "给出 attenuation theorem 的形式定义。结构层只做识别 + 缺口诊断；"
            "但若被误分类的**离散结局**或**二值暴露**有验证研究给出的混淆矩阵，"
            "数值层可做去衰减校正（estimate(..., misclassification={<结局或暴露变量名>: "
            "{confusion_matrix, states}})），逐后门层做矩阵求逆——"
            "结局侧 p_true=M⁻¹p_obs（二值即 Rogan-Gladen 1978），暴露侧用矩阵法"
            "沿暴露轴对 (X,Y) 联合逐结局列求逆（Barron 1977 / Greenland 1988 / "
            "Marshall 1990）。误分类可为非差异（单一矩阵），也可为**差异性**"
            "（differential=True + 每个条件层一个矩阵，differential_by 指定差异轴："
            "结局侧按暴露臂=detection bias 或按**协变量分层**（differential_by=<协变量>），"
            "暴露侧按结局层=recall bias 或按**协变量分层**（differential_by=<协变量>，"
            "误分类率随测量地点/年龄而异）；差异误分类可朝远离零方向偏，故须逐层"
            "求逆，池化单矩阵会做错）；"
            "两种都由 verify_measurement_correction_numeric / "
            "verify_exposure_measurement_correction_numeric 独立重算校正值。"
            "若被误测的是**连续暴露或连续混杂**且有已知的经典加性误差方差 σ²_u"
            "（验证研究 / 重复测量），数值层可经 estimate(..., measurement_error="
            "{<变量名>: {error_variance}}) 用 regression calibration 的矩量校正"
            " β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive 去偏（Carroll 2006；误测暴露=回归稀释"
            "向零衰减，单暴露即 βx=b_naive/λ，λ=1−σ²_u/Var(W|Z) 是连续版 det(M)；"
            "误测混杂=对噪声代理调整留下的残差混淆偏倚，可朝任意方向，由整条矩阵"
            "求逆去偏无标量捷径），由 verify_regression_calibration_numeric 独立重导。"
            "被误测的若是**连续结局**则另当别论：经典加性误差 Y=Y*+V 不改变任何条件"
            "均值，点估计无偏、无可校正；同一入口 measurement_error={<结局名>: "
            "{error_variance}} 给出的是代价——残差方差按 Var(Y|D)=Var(Y*|D)+σ²_v "
            "分解，区间比结局测准时宽 √(Var(Y|D)/Var(Y*|D)) 倍，这部分靠加样本量"
            "消不掉、只能靠把结局测准（由 verify_outcome_error 独立重导）。"
        ),
        blocks=GapBlocks.IDENTIFICATION,
        if_provided=(
            "若拿到 (a) 被误分类离散结局**或二值暴露**的**验证过混淆矩阵**"
            "（Se/Sp 或整张 confusion matrix），可经 estimate(misclassification=...) "
            "逐后门层矩阵求逆去衰减；或 (b) 连续暴露**或连续混杂**的已知经典加性误差"
            "方差 σ²_u（重复测量 test-retest / 验证子样本），可经 "
            "estimate(measurement_error={<暴露或混杂名>: {error_variance}}) 用 "
            "regression calibration 去偏（误测混杂纠正残差混淆；非线性结局的 SIMEX "
            "仍推迟）；连续结局的 σ²_v 同一入口给出的是精度代价而非校正，"
            "因为它本就不偏；或 (c) gold-standard "
            "亚样本（如 BP 用 ABPM、sodium 用 24h 尿钠）做校准"
        ),
        alternative_paths=(
            "用 RCT / 实验性分配数据（消除自报告偏差）替代观察性主样本",
            "对涉及变量做 reliability 重测，按 Carroll et al 2006 "
            "*Measurement Error in Nonlinear Models* 校准",
            "在敏感性分析中报告 attenuation factor 范围（"
            "Rosner et al 1989 regression calibration upper bound）",
        ),
        provenance=tuple(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=f"program:variable:{pred}:{field}:contains:{needle}",
            )
            for pred, field, needle in flagged
        ),
    )


def _classify_dichotomized_continuous_measure(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
) -> Iterable[DataGap]:
    """At least one variable on the identification path declares a
    non-empty ``threshold`` field. The variable schema documents
    ``threshold`` as "Cutoff that turns a continuous measurement into
    this predicate's value, e.g. >=3cm" — so its presence is the
    structural fingerprint that a continuous quantity was DICHOTOMIZED
    at a cutpoint. Surfaces the dichotomization's implications *before*
    the user collects / analyses data — the same before-the-fact
    placement as ``measurement_error_concern`` and
    ``unmeasured_confounder_risk``, but for cutpoint coarsening rather
    than measurement noise or unmeasured confounding.

    Documented data-limitation literature:
    - Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127 "Dichotomizing
      continuous predictors in multiple regression: a bad idea" — power
      loss + residual confounding + cutpoint dependence.
    - Altman et al 1994 *JNCI* 86:829 — data-driven "optimal" cutpoint
      search inflates type-I error.
    - Becher 1992 *Stat Med* 11:1747 — residual confounding from coarse
      categorisation of a continuous confounder.

    Severity INFORMATIONAL: a declared cutpoint does NOT break
    identification (unlike measurement_error's regression dilution or
    ill_defined's undefined estimand); it is a known, bounded modeling
    choice whose harms (efficiency loss / cutpoint sensitivity /
    within-category residual confounding) inform interpretation and have
    a concrete continuous alternative — Themis's own dose-response path
    (Phase 13/14). Must-disclose nonetheless (mirrored to the ⚠ line) so
    a reviewer reading only ``result.explanation`` sees the operational-
    isation caveat.

    Same path-closure as ``_classify_measurement_error_concern``: a
    variable counts when it is the intervention, the target, or a
    directed ancestor of either (a dichotomized confounder funnelling
    into X or Y is exactly the residual-confounding case Becher warns
    about).

    Suppressed when:
    - query is not effect (the bias story is about estimating X→Y)
    - status indicates identification failed (don't pile caveats on
      already-failing branches)
    - extensions.ambiguities[*] already declares a dichotomization /
      arbitrary-cutpoint ambiguity (the upstream LLM named it — escape
      hatch mirroring case 011's measurement_quality suppression)
    """
    if program is None or stmt is None:
        return
    if query_kind != QueryKind.EFFECT:
        return
    if status not in (
        ResultStatus.STRUCTURALLY_SOLVED,
        ResultStatus.NUMERICALLY_SOLVED,
        ResultStatus.NEEDS_INVESTIGATION,
    ):
        return
    if extensions:
        for amb in extensions.get(blocks.AMBIGUITIES) or ():
            if isinstance(amb, dict) and amb.get("kind") in (
                "dichotomization", "arbitrary_cutpoint",
                "continuous_dichotomized",
            ):
                return
    query_atom = getattr(stmt, "query", None)
    intervention = getattr(query_atom, "intervention", None)
    target = getattr(query_atom, "target", None)
    if intervention is None or target is None:
        return
    intervention_pred = intervention.atom.predicate
    target_pred = target.atom.predicate
    parents_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, CauseStatement):
            parents_of.setdefault(
                st.to_atom.predicate, set()
            ).add(st.from_atom.predicate)
    on_path: set[str] = {intervention_pred, target_pred}
    frontier: list[str] = [intervention_pred, target_pred]
    while frontier:
        node = frontier.pop()
        for parent in parents_of.get(node, ()):
            if parent not in on_path:
                on_path.add(parent)
                frontier.append(parent)
    flagged: list[tuple[str, str]] = []
    for st in program.statements:
        if not isinstance(st, VariableDeclaration):
            continue
        if st.predicate not in on_path:
            continue
        cut = getattr(st, "threshold", None)
        if cut:
            flagged.append((st.predicate, cut))
    if not flagged:
        return
    flagged.sort()
    var_summary = ", ".join(
        f"{pred} (threshold: “{cut}”)" for pred, cut in flagged
    )
    yield DataGap(
        kind=GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            "二分化（dichotomization）：识别路径上有连续测量被在某个 cutpoint "
            f"切成二值 — {var_summary}。把连续量在阈值处二分会（1）丢失 "
            "dose-response 信息、降低统计效率（Royston, Altman & Sauerbrei "
            "2006 *Stat Med* 25:127 “Dichotomizing continuous predictors in "
            "multiple regression: a bad idea”）；（2）结果对切点敏感，数据驱动"
            "的“最优切点”搜索还会抬高假阳性（Altman et al 1994 *JNCI* 86:829）；"
            "（3）若被二分的是 confounder，类内残余混杂使调整不充分（Becher "
            "1992 *Stat Med* 11:1747）。Themis 支持把变量保留为连续并做 "
            "dose-response 估计（Phase 13/14）。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=(
            "若能拿到未二分的连续原始测量，可改走 dose-response 估计"
            "（LinearDML / DRLearner，Themis Phase 13/14），保留剂量-反应曲线"
            "并避免任意切点"
        ),
        alternative_paths=(
            "保留连续变量，用 dose-response 估计代替二分（Themis Phase 13/14）",
            "若必须二分，报告对 cutpoint 的敏感性分析（多个切点下结论是否稳定）",
            "对被二分的 confounder，改用更细分层或样条以减少类内残余混杂"
            "（Becher 1992）",
        ),
        provenance=tuple(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=f"program:variable:{pred}:threshold:{cut}",
            )
            for pred, cut in flagged
        ),
    )


def _enumerate_simple_directed_paths(
    adjacency: dict[str, list[str]],
    src: str,
    dst: str,
    *,
    max_paths: int = 32,
    max_depth: int = 12,
) -> list[tuple[str, ...]]:
    """Bounded DFS for simple directed paths src→dst. Bounds protect
    against pathological dense DAGs; real causal models are sparse so
    32×12 is comfortably above what any real query traverses.
    """
    paths: list[tuple[str, ...]] = []

    def _dfs(node: str, trail: list[str], visited: set[str]) -> None:
        if len(paths) >= max_paths:
            return
        if len(trail) > max_depth:
            return
        if node == dst:
            paths.append(tuple(trail))
            return
        for nxt in adjacency.get(node, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            trail.append(nxt)
            _dfs(nxt, trail, visited)
            trail.pop()
            visited.remove(nxt)

    if src not in adjacency:
        return paths
    _dfs(src, [src], {src})
    return paths


# ============================================ classifiers


def _classify_unidentifiable(
    derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    for step in derivation:
        # Tian Shpitser Line 5: a successful tian_hedge_witness step
        # IS the unidentifiability witness — same downstream meaning
        # as a failed unidentifiable_via_backdoor, just discovered via
        # the c-component decomposition rather than backdoor exhaustion.
        if step.rule == "tian_hedge_witness" and not _step_failed(step):
            yield DataGap(
                kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
                severity=GapSeverity.BLOCKING,
                description=(
                    "识别失败：Tian 算法在 An(Y) 子图上找到 c-component "
                    "hedge —— X 与 Y 处于同一 c-component，说明它们之间存在"
                    "未被任何观测变量遮断的潜在共同原因 / 双向耦合，"
                    "P(Y | do(X)) 在该 ADMG 下不可从观测分布识别"
                ),
                blocks=GapBlocks.IDENTIFICATION,
                provenance=(_step_ref(step),),
                if_provided="可给出识别公式 + 后续点估计",
                alternative_paths=(
                    "测量并加入 unmeasured confounder Z，打破 hedge",
                    "在 X 上做 RCT (如可行)，旁路 hedge",
                    "找一个满足 IV 条件的工具变量",
                ),
            )
            continue
        if not _step_failed(step):
            continue
        # IV-specific failure routes through _classify_missing_iv to attach
        # IV-flavored copy and avoid double-counting.
        if "iv" in step.rule:
            continue
        # Transport-specific failure routes through transport classifier.
        if "transport" in step.rule:
            continue
        yield DataGap(
            kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
            severity=GapSeverity.BLOCKING,
            # The step said in words, not its id: the reader is being told
            # why there is no answer, and a snake_case rule name makes the
            # reason unreadable at exactly the moment it matters.
            #
            # Instrumented over a full suite run this branch is reached 0
            # times. It was written for ``unidentifiable_via_backdoor``,
            # which the Tian wiring superseded and which no producer emits
            # any more, so every unidentifiable case now leaves through the
            # hedge branch above. 0 means nobody comes, not that nothing
            # leaks — the sentence is here so that if the branch does come
            # back, it comes back readable.
            description=(
                f"识别失败：这一步（{derivation_glossary.describe(step.rule)}）"
                f"报告无可调整集 / 公式不存在"
            ),
            blocks=GapBlocks.IDENTIFICATION,
            provenance=(_step_ref(step),),
            if_provided="可给出识别公式 + 后续点估计",
            alternative_paths=(
                "测量并加入 unmeasured confounder Z，重新识别",
                "在 X 上做 RCT (如可行)，旁路 backdoor",
                "找一个满足 IV 条件的工具变量",
            ),
        )


# ---------------------------------------------------------------------------
# The item channel — one renderer per species a kernel refusal can declare
# ---------------------------------------------------------------------------
#
# Every investigation item arrives carrying ``MissingItem.gap``: what kind of
# shortfall the kernel hit, said by the kernel that hit it. The renderers
# below turn each species into user-facing copy and nothing more. There is no
# pass that decides WHICH species an item is — that decision was made where
# the failure happened and is not re-derivable from the name, which is what
# the prefix list and the ``iv`` substring test tried to do and got wrong in
# both directions at once (charter finding F).
#
# The residual pass this replaces existed to make an unrecognised name loud
# rather than silent. Its guarantee now holds by construction and is stronger:
# the vocabulary is closed (``MISSING_ITEM_GAPS``), every member is bound
# below, and ``_bind_item_species`` refuses to import if one is not — so an
# item that reaches the report is an item that reaches the user.


class _RaisedElsewhere(NamedTuple):
    """A species whose gap is built from a different source.

    Declared rather than omitted, for the same reason a strategy declares
    the substitution it takes (charter slice 2): a table entry that says
    "not here, and here is why" is checkable, and a missing entry is
    indistinguishable from an oversight.
    """

    reason: str


# A species is either rendered here, or declared as raised elsewhere.
_Renderer = (
    Callable[[InvestigationItem, QueryKind], Iterable[DataGap]]
    | _RaisedElsewhere
)


def _species_unidentifiable(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """The estimand asked for is not point identified from this graph and
    these data. Distinct from a defect in the program — this is the gap
    ``_compute_answer_tier`` reads to decide no point estimand is in
    hand, so a mediator declared off the causal path or a query atom
    absent from V must not land here."""
    yield DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        severity=GapSeverity.BLOCKING,
        description=f"识别路径失败：{item.reason or item.target}",
        blocks=GapBlocks.IDENTIFICATION,
        if_provided="可给出识别公式 + 后续点估计",
        alternative_paths=(
            "测量并加入 unmeasured confounder Z，重新识别",
            "在 X 上做 RCT (如可行)，旁路 backdoor",
            "找一个满足 IV 条件的工具变量",
        ),
        provenance=(_item_ref(item),),
    )


def _species_structural_input(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """A structural requirement the kernel raised that is not an
    identification verdict — an undeclared path coefficient, a mediator
    off every directed path, a query atom absent from V, a conditioning
    event of probability zero.

    Deliberately does NOT assert that identification failed: a missing
    coefficient leaves a point-identified estimand whose number was
    simply never declared, and telling ``answer_tier`` otherwise would
    offer an RCT to a program that needs one edge weight. The gap claims
    nothing beyond the kernel's own reason, because these range too
    widely for one line of advice to fit them all."""
    yield DataGap(
        kind=GapKind.MISSING_STRUCTURAL_INPUT,
        severity=GapSeverity.BLOCKING,
        description=f"缺结构输入：{item.reason or item.target}",
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided="该查询可继续走到点估计",
        provenance=(_item_ref(item),),
    )


def _species_unit_observation(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """A unit-level value the query needs and the program did not
    observe. Not a ``missing_distribution``: abduction in a
    deterministic SCM counterfactual recovers this unit's exogenous term
    from its own measured values, so what is wanted is a reading for
    this unit and no amount of population data substitutes."""
    yield DataGap(
        kind=GapKind.MISSING_UNIT_OBSERVATION,
        severity=GapSeverity.BLOCKING,
        description=f"缺该单位的观测值：{item.reason or item.target}",
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided="该查询可继续走到点估计",
        provenance=(_item_ref(item),),
    )


def _species_missing_distribution(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """A probability the evaluator looked for and theta does not hold."""
    display = _strip_parameter_prefix(item.target)
    signature = _distribution_signature(display)
    min_n, precision = _estimate_sample_size_for_distribution(
        display, signature,
    )
    offer = _interval_offer(query_kind)
    if offer is not None:
        # A magic token that scheduler._reconcile_alt_paths_with_bounds
        # rewrites to whichever procedure produced the actual
        # bounds_result, and strips when the attempt returned nothing.
        alt_paths = (offer,)
    else:
        # No interval channel for this question, so "accept bounds
        # instead" would be a promise nothing can keep. Said once and
        # generally: the sentence that lived here explained why an
        # observational conditional is point-estimable, and was read by
        # 222 causation gaps whose answer is an interval.
        alt_paths = (
            f"直接收集 {display} 的数据 —— 该问法没有区间退路，"
            f"拿不到点估计就没有数",
        )
    yield DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description=f"缺概率分布 {display}",
        blocks=GapBlocks.POINT_ESTIMATE,
        signature=signature,
        required_data=GapRequiredData(
            data_type=(
                RequiredDataType.IPD
                if signature == "conditional"
                else RequiredDataType.MARGINAL
            ),
            min_sample_size=min_n,
            precision_target=precision,
        ),
        if_provided="可给点估计",
        alternative_paths=alt_paths,
        provenance=(_item_ref(item),),
    )


def _species_theta_graph_mismatch(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """Theta DOES hold a marginal, and the declared graph forbids
    substituting it for the demanded conditional.

    The repair is the opposite of the previous species': fix the graph,
    or supply the conditional — "supply more theta" is advice for a
    different problem, and a consumer reading only ``gap.kind`` would
    give it."""
    display = _strip_parameter_prefix(item.target)
    yield DataGap(
        kind=GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH,
        severity=GapSeverity.IMPORTANT,
        description=(
            f"声明的图与提供的 CPT 不一致：缺 {display}，"
            f"但 theta 中存在的边缘量被 d-separation 拒绝"
            f"（图蕴含的独立性不成立）"
        ),
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided="可给点估计（在解决图与 CPT 矛盾后）",
        alternative_paths=(
            f"补充所缺的条件量 {display}（接受图）",
            "或：删除引发独立性矛盾的边（改图，承认现有 CPT 已是真分布）",
        ) + tuple(o for o in (_interval_offer(query_kind),) if o is not None),
        provenance=(_item_ref(item),),
    )


def _species_missing_assumption(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """An identification premise the kernel refuses to choose for you.

    What arrives here is not one shape: an undeclared premise
    (monotonicity), an input only an experiment can supply
    (P(Y=1|do(x)) under confounding), and declared inputs that
    contradict each other (interventional risks outside the consistency
    band, stratum weights that are not a distribution). One sentence of
    generic advice would be wrong for most of them, so the gap states
    what the kernel stated and adds nothing the kernel did not derive."""
    yield DataGap(
        kind=GapKind.MISSING_ASSUMPTION,
        severity=GapSeverity.IMPORTANT,
        description=f"识别前提待补充或修正：{item.reason or item.target}",
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided="该识别路径可继续走到点估计",
        provenance=(_item_ref(item),),
    )


def _bind_item_species(
    table: dict[GapKind, _Renderer],
) -> dict[GapKind, _Renderer]:
    """The table covers the declared vocabulary exactly.

    Both directions are defects. An unbound species is an item that
    reaches the report and produces nothing, which is the silence the
    residual pass was installed to cover. A bound species outside the
    vocabulary is a renderer no item can ever reach — dead copy that
    reads like coverage.
    """
    missing = sorted(g.value for g in MISSING_ITEM_GAPS if g not in table)
    if missing:
        raise ValueError(
            f"no renderer for missing-item species {missing}; an item "
            f"declaring one would reach the report and produce no gap"
        )
    extra = sorted(g.value for g in table if g not in MISSING_ITEM_GAPS)
    if extra:
        raise ValueError(
            f"renderer bound for {extra}, which no missing item may "
            f"declare (themis.types.MISSING_ITEM_GAPS)"
        )
    return table


_ITEM_SPECIES: dict[GapKind, _Renderer] = _bind_item_species({
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: _species_unidentifiable,
    GapKind.MISSING_STRUCTURAL_INPUT: _species_structural_input,
    GapKind.MISSING_UNIT_OBSERVATION: _species_unit_observation,
    GapKind.MISSING_DISTRIBUTION: _species_missing_distribution,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH: _species_theta_graph_mismatch,
    GapKind.MISSING_ASSUMPTION: _species_missing_assumption,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: _RaisedElsewhere(
        "framing items are the action side of a gap built from "
        "framing_notes, which fire on query kinds that raise no "
        "investigation item at all — so the note, not the item, is the "
        "one source that sees every case"
    ),
})


def _item_ref(item: InvestigationItem) -> GapProvenanceRef:
    return GapProvenanceRef(
        ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id=item.target,
    )


def _strip_parameter_prefix(target: str) -> str:
    """User-facing copy drops the channel prefix the pusher put on the
    name; provenance keeps the prefixed form so T10-1 can match it."""
    prefix = "parameter:"
    return target[len(prefix):] if target.startswith(prefix) else target


def _classify_investigation_items(
    requests: tuple[InvestigationRequest, ...],
    query_kind: QueryKind,
) -> Iterable[DataGap]:
    """Every investigation item, rendered as the species it declares."""
    for req in requests:
        for item in req.items:
            render = _ITEM_SPECIES[item.gap]
            if isinstance(render, _RaisedElsewhere):
                continue
            yield from render(item, query_kind)


def _classify_missing_population_distribution(
    extensions: dict,
) -> Iterable[DataGap]:
    """Placeholder. The signal that triggers this — a multi-source
    transport block (§T9.2 / §T9.3) — does not yet exist in the kernel.
    Kept as a stable enum slot so future phases plug in without schema
    revisions. Returns empty in current scope."""
    return ()


def _classify_missing_iv(
    derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    """IV failures that left a derivation step behind.

    There used to be a second signal here: a structure-group item whose
    name looked like an instrument. It read the look-alike off a
    substring and answered "no valid instrument found" to a query that
    had named a descendant of X in its ``given`` (charter finding F).
    It is gone rather than narrowed — ``MISSING_IV_CANDIDATE`` is not in
    ``MISSING_ITEM_GAPS``, so no item can declare it, and no name can
    resemble it. A producer that wants to raise one adds the species to
    the vocabulary and binds a renderer for it.
    """
    for step in derivation:
        if not _step_failed(step):
            continue
        if "iv" not in step.rule:
            continue
        yield DataGap(
            kind=GapKind.MISSING_IV_CANDIDATE,
            severity=GapSeverity.IMPORTANT,
            description=f"IV 路径失败：rule `{step.rule}` 未通过",
            blocks=GapBlocks.IDENTIFICATION,
            if_provided="可走 IV 路径给出 LATE / 2SLS-ATE",
            alternative_paths=(
                "改用 backdoor 路径（如有可调整集）",
                "改用 front-door 路径（如有有效中介）",
            ),
            provenance=(_step_ref(step),),
        )


def _classify_missing_mediator(
    extensions: dict,
    requests: tuple[InvestigationRequest, ...],
) -> Iterable[DataGap]:
    view = _mediation_view(extensions)
    if view is None or not view.valid:
        return
    # Surface only when there's a parameter request whose target hits one of
    # the mediators — otherwise mediation is fully solved. A block's request
    # typically names several at once, so each item yields ONE gap listing the
    # mediators it actually touches, not one gap per mediator.
    for req in requests:
        if req.group != "parameter":
            continue
        for item in req.items:
            touched = tuple(m for m in view.mediators if m in item.target)
            if not touched:
                continue
            mediator = ", ".join(touched)
            min_n, precision = _estimate_sample_size_for_mediator(item.target)
            yield DataGap(
                kind=GapKind.MISSING_MEDIATOR_DATA,
                severity=GapSeverity.BLOCKING,
                description=(
                    f"中介分解需要 {mediator} 相关分布：{item.target}"
                ),
                blocks=GapBlocks.POINT_ESTIMATE,
                required_data=GapRequiredData(
                    data_type=RequiredDataType.IPD,
                    variables=touched,
                    min_sample_size=min_n,
                    precision_target=precision,
                ),
                if_provided="可给 NDE / NIE / TE 数值分解",
                alternative_paths=(
                    "回退到 CDE（控制中介，给条件直接效应）",
                    "退回 total effect，不分解",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )


def _classify_transport_target_distribution(
    extensions: dict,
) -> Iterable[DataGap]:
    """Bareinboim transport formula:

        P*(y|do(x)) = Σ_z P(y|do(x), z) · P*(z)

    Two distinct data needs that ``§T9.1`` structural identification
    leaves open — both must be filled before §T9.2 can produce a
    transport-adjusted point estimate:

    1. Target-side ``P*(z)`` — population-level marginal on Z (this gap)
    2. Source-side ``P(y|do(x), z)`` — RCT subgroup / IPD stratification
       (the second gap, often the real bottleneck since most
       meta-analyses only publish marginal effects)

    Both are emitted whenever a transport_identification block exists
    with a non-empty adjustment set."""
    block = extensions.get(blocks.TRANSPORT_IDENTIFICATION)
    if not block:
        return
    adjustment_set = block.get("adjustment_set", []) or []
    if not adjustment_set:
        return
    target_pop = block.get("target_population")
    source_pop = block.get("source_population")
    z_names = ", ".join(_atom_label(a) for a in adjustment_set)
    treatment, outcome = _transport_treatment_outcome(block)

    # Heuristic strata count: assume each adjustment-set predicate is
    # binary. Phase 12 is binary-only; revise when non-binary lands.
    n_strata = 2 ** len(adjustment_set)
    target_n, target_precision = _estimate_sample_size_for_transport_target(
        n_strata,
    )
    source_n, source_precision = _estimate_sample_size_for_transport_source(
        n_strata,
    )

    # 1. Target-side P*(Z) — population marginal.
    yield DataGap(
        kind=GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
        severity=GapSeverity.BLOCKING,
        description=(
            f"转移公式已识别，但目标人群 {target_pop or '<未命名>'} "
            f"在 {{{z_names}}} 上的分布 P*(Z) 未提供"
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.MARGINAL,
            population=target_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=target_n,
            precision_target=target_precision,
        ),
        if_provided="可给目标人群的 transport-adjusted ATE 点估计",
        alternative_paths=(
            "接受源人群 ATE 作为粗略估计（外推有效性弱）",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="s_t9_2"
            ),
        ),
    )

    # 2. Source-side P(Y|do(X), Z) — stratified conditional.
    # Often the real bottleneck since meta-analyses publish marginal
    # effects (one number) rather than per-subgroup tables.
    if treatment and outcome:
        formula_repr = (
            f"P({outcome} | do({treatment}), {z_names})"
        )
    else:
        formula_repr = "P(Y | do(X), Z)"
    yield DataGap(
        kind=GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN,
        severity=GapSeverity.BLOCKING,
        description=(
            f"转移公式还需要源人群 {source_pop or '<未命名>'} 的"
            f"分层条件分布 {formula_repr}（meta-analysis 通常只汇总"
            "成一个数，不给分层）"
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population=source_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=source_n,
            precision_target=source_precision,
        ),
        if_provided="可给目标人群的 transport-adjusted ATE 点估计",
        alternative_paths=(
            "找原始 RCT IPD（联系作者 / 看附件 supplementary table）",
            "找 meta-analysis 的 subgroup analysis（按 age / sex / BMI 分层）",
            "退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="s_t9_2"
            ),
        ),
    )


def _transport_treatment_outcome(block: dict) -> tuple[str | None, str | None]:
    """Pull treatment / outcome predicate names out of a transport
    block's formula_repr like ``P*(Y | do(X)) = ...``. Returns (X, Y)
    or (None, None) if parsing fails (defensive — block schema may
    drift)."""
    formula = block.get("formula_repr", "")
    # Cheap regex-free parse: look for "P*(<outcome> | do(<treatment>)".
    try:
        head = formula.split("=", 1)[0]
        out_part = head.split("(", 1)[1]
        outcome = out_part.split("|", 1)[0].strip()
        do_part = out_part.split("do(", 1)[1]
        treatment = do_part.split(")", 1)[0].strip()
        return treatment or None, outcome or None
    except (IndexError, ValueError):
        return None, None


_DEFAULT_DOSE_RESPONSE_K = 5


def _classify_dose_response_data(
    program, stmt, derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    """Phase 13: when the user asks for a dose-response curve (NL flagged
    via program.extensions.ambiguities[kind=dose_response_query]),
    Themis itself doesn't compute curves — but emits a fully-specified
    'what data you need to fit it elsewhere' gap.

    Trigger: program-level ambiguity entry with kind=dose_response_query.
    Renderer + LLM-prompt layer pair this with 'use EconML / DoubleML
    / GAM' guidance.
    """
    if program is None or stmt is None:
        return
    ext = getattr(program, "extensions", None) or {}
    ambs = ext.get("ambiguities") or []
    triggered = any(
        isinstance(a, dict) and a.get("kind") == "dose_response_query"
        for a in ambs
    )
    if not triggered:
        return

    from ..output.sample_size import estimate_min_n_two_arm_continuous

    # Per-arm n at default Cohen's d=0.5 → estimate_min_n_two_arm_continuous
    # returns total (~150). Per-arm = total / 2 ≈ 75; rounded → 100 for
    # K-point scaling readability.
    total_two_arm, _ = estimate_min_n_two_arm_continuous()
    n_per_point = max(50, total_two_arm // 2)
    K = _DEFAULT_DOSE_RESPONSE_K
    total = K * n_per_point

    confounders = _extract_dose_response_confounders(derivation)

    # Best-effort target / intervention names for the description
    target_label = _query_target_label(stmt)
    intervention_label = _query_intervention_label(stmt)

    # iter 13 (case 005 finding): if confounders_required is empty AND the
    # user's program has no extra-variable nodes beyond X / Y, the DAG is
    # bare X→Y. This is unusual for observational dose-response work
    # (Whelton 2002 / AHA 2013 / Cornelissen 2013 all flag baseline
    # outcome + demographic covariates as standard). Append a generic
    # hint so the renderer prompts the user to confirm minimality is
    # intentional. Avoids hardcoding domain-specific covariate names.
    extra_hint = ""
    if not confounders and _program_has_no_declared_confounders(program, stmt):
        extra_hint = (
            "（注：你的 DAG 仅声明了 intervention + target 两个节点，没有"
            "任何 confounder。观察性剂量响应分析典型需要在 DAG 里至少声明"
            " baseline outcome 与关键 demographic covariates；若你确实"
            "想保持 minimal DAG（如随机化 RCT 设计），可以忽略此提示。）"
        )

    yield DataGap(
        kind=GapKind.DOSE_RESPONSE_DATA_REQUIRED,
        severity=GapSeverity.BLOCKING,
        description=(
            f"用户问的是 {intervention_label} 与 {target_label} 之间的"
            f"剂量响应关系（曲线 / 关系图）。Themis 不算曲线（请用 EconML "
            f"/ DoubleML / GAM）—— 但下面是你做这件事所需的数据规格。"
            f"{extra_hint}"
        ),
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            sampling_point_count=K,
            min_sample_size=total,
            precision_target=(
                f"K={K} 个 X 采样点 × n={n_per_point}/点 "
                f"(Cohen's d=0.5, α=0.05, power=0.80)"
            ),
            confounders_required=tuple(confounders),
            time_window="建议 baseline + 4w + 12w（视实际研究问题调整）",
            sutva_concerns=(
                "受试者之间不能讨论 / 协调干预（违反 SUTVA）",
                "若有溢出 / 同侪效应，需登记并在分析中纳入",
            ),
        ),
        if_provided=(
            "数据齐了之后，去 EconML / DoubleML / GAM 拟合曲线 —— "
            "Themis 不在 estimator 这一步参与"
        ),
        alternative_paths=(
            "退一步只看二元对比 (X=high vs X=low)：Themis 能给区间答案",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="program:extensions.ambiguities.dose_response_query",
            ),
        ),
    )


def _classify_collider_conditioning_opens_backdoor(
    *,
    program,
    stmt,
) -> Iterable[DataGap]:
    """Iter 122 — selection-bias board (#7) signal.

    EffectQuery's ``given`` (conditioning subgroup) contains a node W
    where both the intervention X and the target Y appear as ancestors
    in the program-derived directed graph. Per Pearl d-separation,
    conditioning on W (a collider on the X→...→W←...←Y path) OPENS
    that path rather than blocks it; the conditional effect estimate
    is NOT the conditional intervention effect on the requested
    subgroup — it carries collider-induced bias.

    Detection rule (predicate-level, robust to forall instantiation):
    for each W in given.atoms, walk parents-of from W via cause edges
    and collect the transitive closure (W's ancestor set). If both X
    and Y are in W's ancestors, fire IMPORTANT severity gap.

    Severity: IMPORTANT — not informational. The estimate is no
    longer the requested causal contrast, just a confounded
    conditional. Renderer must surface clearly so the user does NOT
    interpret the result as the conditional ATE.
    """
    from ..types import EffectQuery

    if program is None or stmt is None:
        return
    q = getattr(stmt, "query", None)
    if not isinstance(q, EffectQuery):
        return
    given = getattr(q, "given", ())
    if not given:
        return

    intervention_pred = q.intervention.atom.predicate
    target_pred = q.target.atom.predicate

    # Build the predicate-level ADMG (directed cause edges + bidirected
    # latent-confounding edges; forall quantification doesn't change the
    # predicate edge structure) and detect a conditioned collider via
    # m-separation — NOT a directed-ancestor test. This catches M-bias
    # colliders whose arms are latent common causes (bidirected, X<->W<->Y —
    # What If Fig 7.4) and colliders activated through a conditioned descendant
    # (Fig 8.2), not only the direct X->W<-Y shape (Fig 8.1).
    import networkx as nx

    from ..runtime.structural_solver import conditioned_collider_opens_path
    from ..types import BidirectedStatement

    g = nx.DiGraph()
    bi_pairs: set = set()
    for st in program.statements:
        if isinstance(st, CauseStatement):
            g.add_edge(st.from_atom.predicate, st.to_atom.predicate)
        elif isinstance(st, BidirectedStatement):
            la, ra = st.left.predicate, st.right.predicate
            g.add_node(la)
            g.add_node(ra)
            bi_pairs.add(frozenset({la, ra}))
    bidirected = frozenset(bi_pairs)
    given_preds = frozenset(
        p for p in (
            getattr(getattr(gi, "atom", gi), "predicate", None) for gi in given
        )
        if p is not None
    )

    for given_item in given:
        atom = getattr(given_item, "atom", given_item)
        w_pred = getattr(atom, "predicate", None)
        if w_pred is None:
            continue
        if w_pred in (intervention_pred, target_pred):
            # Conditioning on the intervention or target itself is a
            # different problem (degenerate query), not collider opening.
            continue
        if conditioned_collider_opens_path(
            g, bidirected, intervention_pred, target_pred, given_preds, w_pred,
        ):
            yield DataGap(
                kind=GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR,
                severity=GapSeverity.IMPORTANT,
                description=(
                    f"`given` 中的条件节点 `{w_pred}` 是 collider —— 在 "
                    f"`{intervention_pred}` 与 `{target_pred}` 之间存在一条"
                    f"以 `{w_pred}` 为对撞点的路径（两条臂可经潜在/双向边，"
                    f"即 M-bias）。Pearl d-separation：在 collider（或其后代）"
                    f"上做条件会**打开**这条非因果路径而不是阻断它，给最终"
                    f"估计引入 collider-induced bias / selection bias。当前"
                    f"返回的不是 \"在 `{w_pred}` 子群上的因果效应\"，"
                    f"而是被打开的非因果路径污染过的混合量。"
                ),
                blocks=GapBlocks.IDENTIFICATION,
                if_provided=(
                    f"从 `given` 移除 `{w_pred}` —— 如果你真的想问 "
                    f"\"在 `{w_pred}` 子群上的效应\"，需要单独的 "
                    f"transport / stratified analysis（先分层再估计），"
                    f"不能直接做条件查询"
                ),
                alternative_paths=(
                    f"不做这个条件，问 marginal 效应 P({target_pred} | "
                    f"do({intervention_pred}))",
                    f"如果 `{w_pred}` 不是真 collider（即只有 X 或只有 Y "
                    f"是祖先），更新 DAG 把缺失的因果方向加进去 — "
                    f"当前结构性结论会变",
                    f"用 transport identification 路径处理 \"target "
                    f"population restricted by {w_pred}\" 而不是用 "
                    f"`given` 字段",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.VERIFIER_CHECK,
                        ref_id=(
                            f"collider:{w_pred}|"
                            f"{intervention_pred}->{target_pred}"
                        ),
                    ),
                ),
            )


def _classify_selection_on_collider_opens_path(
    *,
    program,
    stmt,
) -> Iterable[DataGap]:
    """Iter 206 — selection-bias board (#7) second shape.

    Distinct from ``_classify_collider_conditioning_opens_backdoor``
    which fires on **explicit** conditioning via ``EffectQuery.given``.
    This classifier fires on **implicit sample restriction** encoded as
    an ``ObservationStatement(W, value)``: the data the user is about to
    estimate from is restricted to subjects with W=value, and the
    declared DAG has both intervention X and target Y as directed
    ancestors of W. Per Pearl d-separation conditioning on W (which the
    sample restriction *implicitly does*) opens X→…→W←…←Y; the marginal
    estimate from the restricted sample carries selection-induced bias.

    Canonical case: Hernán-Hernández-Díaz-Robins 2004 *Epidemiology*
    15:615 "A Structural Approach to Selection Bias" — Figure 3-style
    HIV/AZT → AIDS-death cohort where eligibility for follow-up
    (W = "selected") is itself caused by both treatment and outcome.
    The "structural approach" framing is exactly: name the W node,
    surface that the sample restriction is conditioning on a collider.

    Detection rule (predicate-level):
    - For each ObservationStatement in the program, let W = its atom's
      predicate.
    - Build the parents-of map from CauseStatement edges.
    - Walk the directed-ancestor closure of W.
    - If both intervention X and target Y are in W's ancestor closure,
      fire IMPORTANT severity gap.
    - Skip the cause-self / target-self degenerate cases (W ∈ {X, Y}).

    Severity: IMPORTANT — selection on a collider biases the marginal
    estimate identifiably; this is identification damage, not just a
    caveat.

    No external library does this routing (DoWhy/EconML accept the
    user-supplied dataset and confounder set; they don't inspect for
    implicit sample-restriction colliders). Themis is uniquely
    positioned because it owns both the program-level DAG and the
    ObservationStatement structure.
    """
    from ..types import EffectQuery

    if program is None or stmt is None:
        return
    q = getattr(stmt, "query", None)
    if not isinstance(q, EffectQuery):
        return

    intervention_pred = q.intervention.atom.predicate
    target_pred = q.target.atom.predicate

    # Gather ObservationStatement-restricted predicates.
    observed_preds: list[tuple[str, object]] = []
    for st in program.statements:
        if isinstance(st, ObservationStatement):
            w_pred = st.atom.predicate
            if w_pred in (intervention_pred, target_pred):
                # Observing the intervention itself or the target
                # itself isn't selection-on-collider — it's just a
                # different (degenerate) query.
                continue
            observed_preds.append((w_pred, st.value))

    if not observed_preds:
        return

    # Build parents-of map for ancestor walk.
    parents_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, CauseStatement):
            parents_of.setdefault(
                st.to_atom.predicate, set()
            ).add(st.from_atom.predicate)

    def _ancestors_excluding(node: str, blocked: str) -> set[str]:
        """Directed-ancestor closure of ``node`` with paths through
        ``blocked`` removed (``blocked`` itself is treated as non-
        traversable). Used to verify there is a directed path from
        an ancestor candidate to ``node`` that does NOT go through
        the other candidate — Hernán 2004 §3 'common effect' requires
        the two ancestor sources to be structurally separate, not just
        a chain X→Y→W where Y trivially makes X an ancestor."""
        seen: set[str] = set()
        stack = [
            p for p in parents_of.get(node, set()) if p != blocked
        ]
        while stack:
            curr = stack.pop()
            if curr in seen or curr == blocked:
                continue
            seen.add(curr)
            stack.extend(
                p for p in parents_of.get(curr, set()) if p != blocked
            )
        return seen

    for w_pred, w_value in observed_preds:
        # Hernán 2004 §3: W is a 'common effect' of X and Y iff there is
        # a directed path X→…→W not going through Y *and* a directed path
        # Y→…→W not going through X. Pure X→Y→W chain gives X as
        # ancestor only via Y, which is overcontrol bias on a mediator,
        # not selection bias on a collider — different identification
        # problem with different repair (don't fire this kind).
        ancs_via_not_target = _ancestors_excluding(w_pred, target_pred)
        ancs_via_not_intervention = _ancestors_excluding(
            w_pred, intervention_pred
        )
        if (
            intervention_pred in ancs_via_not_target
            and target_pred in ancs_via_not_intervention
        ):
            yield DataGap(
                kind=GapKind.SELECTION_ON_COLLIDER_OPENS_PATH,
                severity=GapSeverity.IMPORTANT,
                description=(
                    f"样本被结构性限制为 `{w_pred}={w_value}` 的受试者"
                    f"（program 里有 ObservationStatement 编码了这个限制）"
                    f"，但声明的 DAG 里 `{intervention_pred}` 和 "
                    f"`{target_pred}` 都是 `{w_pred}` 的祖先 —— `{w_pred}` "
                    f"是 collider。Pearl d-separation：用『仅 "
                    f"{w_pred}={w_value} 的子样本』估计 P({target_pred} | "
                    f"do({intervention_pred})) 等于在 collider 上做条件，"
                    f"会**打开** `{intervention_pred}→...→{w_pred}←..."
                    f"←{target_pred}` 这条非因果路径，给估计引入 selection-"
                    f"induced bias。Hernán-Hernández-Díaz-Robins 2004 "
                    f"*Epidemiology* 15:615 \"A Structural Approach to "
                    f"Selection Bias\" 的标准结构。"
                ),
                blocks=GapBlocks.IDENTIFICATION,
                if_provided=(
                    f"补充未被 `{w_pred}` 限制的对照样本（覆盖 "
                    f"{w_pred}=¬{w_value} 的受试者），把全样本作为分析"
                    f"对象 —— 而不是只用 `{w_pred}={w_value}` 子样本"
                ),
                alternative_paths=(
                    f"用 inverse-probability-of-selection weighting "
                    f"(Hernán et al 2004 §5)：对每个保留样本按 "
                    f"1/P({w_pred}={w_value} | X, Y) 加权重抽以"
                    f"近似全样本",
                    f"如果 `{w_pred}` 实际并非由 `{intervention_pred}` 和 "
                    f"`{target_pred}` 共同决定，更新 DAG 删除其中一条"
                    f"祖先边 —— 当前结构性结论会随之改变",
                    f"用 `selection_node` (Phase 9 §T9.1) 把 `{w_pred}` "
                    f"声明为 transport 选择节点而不是观察节点，并通过 "
                    f"transport identification 路径处理跨人群泛化",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.VERIFIER_CHECK,
                        ref_id=(
                            f"selection_observation:{w_pred}|"
                            f"{intervention_pred}->{target_pred}"
                        ),
                    ),
                ),
            )


def _classify_ill_defined_intervention_versions(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
) -> Iterable[DataGap]:
    """Iter 207 — well-defined-intervention prerequisite (boards #1 / #11).

    Trigger: EffectQuery's intervention atom names a declared predicate
    on which ``time_window`` is absent AND ``state_vs_event`` is either
    explicit ``"state"`` (the contradiction shape: persistent attribute
    with no duration) OR also absent (the silence shape: NL-derived
    program where neither field was set — the most common shape for
    LLM-emitted kernel_ast since both fields are optional). Both shapes
    map to the same Hernán & Taubman 2008 ill-defined-intervention
    methodological concern; only the description and provenance ref_id
    distinguish them so a renderer can soften wording if desired.

    Default-on prophylactic rationale: when an LLM emits a kernel_ast
    naturally, it rarely declares ``state_vs_event``. Requiring the
    explicit ``"state"`` value before firing put the burden of "spot
    the methodology trap" back on the LLM — the very thing Themis is
    supposed to catch. So absent ``state_vs_event`` is treated as
    "plausibly state-like, please confirm". The opt-out is cheap and
    explicit: declare ``state_vs_event="event"`` (or add
    ``time_window``) on the intervention predicate's
    VariableDeclaration. See 2026-05 Q3 retest analysis.

    Authoritative source: Hernán MA, Taubman SL 2008 *Int J Obesity*
    32(Suppl 3):S8-S14 "Does obesity shorten life? The importance of
    well-defined interventions to answer causal questions" — argues
    that when the exposure is a habitual / persistent attribute (BMI,
    obesity, smoking-status-as-attribute), multiple structurally-
    different interventions can produce the same state value (e.g.
    weight loss via gastric banding vs lifestyle vs smoking cessation
    vs metabolic disease) and entail DIFFERENT counterfactual
    mortality outcomes — the same observed state value does NOT pin
    a unique counterfactual, so do(X=state) is not well defined. The
    consistency assumption (Hernán & Robins *What If* §3.4) is
    silently violated.

    Distinct from ``ambiguous_variable_definition``: that kind fires
    on each individual missing framing field (threshold / observability
    / direction / baseline) — generic "you didn't say". This kind
    fires on the *structural* well-defined-intervention concern with a
    named-paper anchor and methodology-specific repair options.

    Suppressed when:
    - query is not effect (consistency-violation story is about the
      do(.) operator)
    - status indicates identification failed (don't pile caveats on
      already-failing branches)
    - extensions.ambiguities[*] declares
      kind in {"ill_defined_intervention", "well_defined_intervention"}
      — escape-hatch path mirroring case 011's measurement_quality
      suppression
    - the intervention predicate has no VariableDeclaration at all
      (no schema admittance → nothing to flag the inferred state on)
    - state_vs_event is the literal string "event" (explicit acute
      exposure declaration; the LLM has signaled this is well-defined)
    - time_window is set (duration closes the version-ambiguity gap)

    Severity IMPORTANT — consistency violation biases the estimand
    DEFINITION (different interventions → different estimands), not
    the estimate of a single estimand. Different from
    measurement_error_concern (which biases the estimate of a
    well-defined estimand).
    """
    if program is None or stmt is None:
        return
    if query_kind != QueryKind.EFFECT:
        return
    if status not in (
        ResultStatus.STRUCTURALLY_SOLVED,
        ResultStatus.NUMERICALLY_SOLVED,
        ResultStatus.NEEDS_INVESTIGATION,
    ):
        return
    # Suppression: upstream LLM has already named this concern.
    if extensions:
        ambiguities = extensions.get(blocks.AMBIGUITIES) or ()
        for amb in ambiguities:
            if not isinstance(amb, dict):
                continue
            kind = amb.get("kind")
            if kind in (
                "ill_defined_intervention",
                "well_defined_intervention",
            ):
                return
    query_atom = getattr(stmt, "query", None)
    intervention = getattr(query_atom, "intervention", None)
    if intervention is None:
        return
    intervention_pred = intervention.atom.predicate
    decl: VariableDeclaration | None = None
    for st in program.statements:
        if (
            isinstance(st, VariableDeclaration)
            and st.predicate == intervention_pred
        ):
            decl = st
            break
    if decl is None:
        return
    state_value = getattr(decl, "state_vs_event", None)
    time_window = getattr(decl, "time_window", None)
    # time_window declared → version-ambiguity closed by duration.
    if time_window:
        return
    # state_vs_event explicitly "event" → LLM signaled well-defined
    # acute exposure (one-shot dose / discrete trigger). Trust the
    # opt-out and skip.
    if state_value == "event":
        return
    # Remaining: state_value == "state" (explicit contradiction) or
    # state_value is None (silence on both fields → inferred state-
    # like). Both fire the same GapKind; description and provenance
    # ref_id differ so a renderer can adjust tone.
    inferred = state_value is None
    if inferred:
        description = (
            f"`{intervention_pred}` 出现在 do(.) 位置，但没声明它是"
            f"**离散事件**还是**持续状态**（`state_vs_event`），也没给 "
            f"`time_window` —— 所以这里**还无法判断**这个干预定义得够不"
            f"够清楚（缺信息 ≠ 定义不清）。先确认一句：`{intervention_pred}`"
            f" 是一个**明确的动作 / 事件**（如一次性给药、参加某项目），"
            f"还是一个**属性 / 持续状态**（如肥胖、长期保持某行为）？"
            f"若是前者，干预本就定义清楚，声明 `state_vs_event=\"event\"` "
            f"即可消除本提示。若是后者，则会落入 Hernán & Taubman 2008 "
            f"*IJO* 32(S3):S8-S14 \"Does obesity shorten life?\"（该文以"
            f"肥胖为例）的 ill-defined intervention 情形：同一状态值可由多"
            f"种操纵方式达到、各自反事实不同，do({intervention_pred}=该状态)"
            f" 没有唯一定义，consistency 假设（Hernán & Robins *What If* "
            f"§3.4）会被违反 —— 这时请加 `time_window`，或在 "
            f"extensions.ambiguities opt-in `ill_defined_intervention`。"
        )
        ref_id = f"intervention_state_inferred:{intervention_pred}"
    else:
        description = (
            f"intervention 是状态不是事件、且没有指定时间窗：变量 "
            f"`{intervention_pred}` 声明了 `state_vs_event=\"state\"`"
            f"（持久性属性，不是离散事件），但同一变量没有声明 "
            f"`time_window`。这是 Hernán & Taubman 2008 *IJO* "
            f"32(S3):S8-S14 \"Does obesity shorten life? The importance"
            f" of well-defined interventions to answer causal "
            f"questions\" 的经典 ill-defined intervention 结构 —— 同一"
            f"个 `{intervention_pred}` 状态值可以由多种结构上不同的"
            f"操纵方式达到，而这些不同的操纵会带来**不同**的反事实"
            f"结果，因此 do("
            f"{intervention_pred}=state) 没有唯一定义；consistency "
            f"assumption（Hernán & Robins *What If* §3.4）被沉默地违反，"
            f"返回的 \"effect\" 实际上是多个估计量的混合。Themis 仅"
            f"surface 此问题，无法替你选具体的干预定义。"
        )
        ref_id = f"intervention_state_without_time_window:{intervention_pred}"
    yield DataGap(
        kind=GapKind.ILL_DEFINED_INTERVENTION_VERSIONS,
        severity=GapSeverity.IMPORTANT,
        description=description,
        blocks=GapBlocks.IDENTIFICATION,
        if_provided=(
            f"在 `{intervention_pred}` 的 VariableDeclaration 上加 "
            f"`time_window`（说明 \"持续多长时间 / 在哪个时点被视为该"
            f"状态\"），并在 program.extensions.ambiguities 里加 "
            f"`ill_defined_intervention` 条目，说明你打算把哪一种具体的"
            f" manipulation（如生活方式 / 用药 / 手术 / RCT 随机化）"
            f"作为 do(.) 的 well-defined intervention 等价物"
        ),
        alternative_paths=(
            f"把 `{intervention_pred}` 重新声明为一个具体的事件类变量"
            f"（state_vs_event=\"event\"）—— 一个有明确操纵动作的一次性"
            f"事件，这样 do(.) 有明确目标",
            f"把 `{intervention_pred}` 拆成两个变量：一个事件类的"
            f"intervention（具体的操纵动作）+ 一个由它导致的中间状态，"
            f"用 mediation 路径处理",
            f"用 RCT / 实验性数据替代观察性主样本 —— 实验里 do(.) 的"
            f"\"compared with what\" 由随机化协议明确定义",
            f"在 extensions.ambiguities 里以 `ill_defined_intervention` "
            f"kind 显式声明本题接受多 intervention 的混合估计量 —— "
            f"Themis 会停发本警告并在渲染时把 caveat 显式化",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=ref_id,
            ),
        ),
    )


def _classify_unattempted_layer_dispatch_conflict(
    *,
    stmt,
    extensions: dict,
) -> Iterable[DataGap]:
    """L3 case 009 finding: when a query specifies multiple identification
    layers (e.g. both ``mediator`` and ``target_population``), the kernel
    only dispatches one and silently skips the other. Without this
    disclosure the user may read the ``structurally_solved`` result and
    assume both layers were handled. Cole & Stuart 2010 + VanderWeele
    2016 §6.2 establish that mediation × transport are sequential
    operations, not a single dispatch.

    Trigger pairs (when both fields set on the query but only one
    extension populated; ``mediator`` and ``mediators`` count alike —
    a mediator BLOCK is skipped just as silently as a single one):
    - mediator(s) + target_population, transport_identification populated
      but the mediation decomposition missing/invalid → mediation skipped
    - mediator(s) + target_population, mediation decomposition populated
      but transport_identification missing → transport skipped

    Severity: IMPORTANT — the dispatched layer is structurally valid
    (not a bug to block), but silent skip violates VISION's
    honest-about-what-wasn't-done principle.
    """
    if stmt is None:
        return
    q = getattr(stmt, "query", None)
    has_mediator = (
        getattr(q, "mediator", None) is not None
        or bool(getattr(q, "mediators", None))
    )
    has_target_pop = getattr(q, "target_population", None) is not None
    if not (has_mediator and has_target_pop):
        return
    ext = extensions or {}
    transport_done = bool(ext.get(blocks.TRANSPORT_IDENTIFICATION))
    view = _mediation_view(ext)
    mediation_done = bool(view is not None and view.valid)
    if transport_done and not mediation_done:
        attempted, skipped = "transport", "mediation"
    elif mediation_done and not transport_done:
        attempted, skipped = "mediation", "transport"
    else:
        return
    mediator_field = (
        "`mediators`" if getattr(q, "mediators", None) else "`mediator`"
    )
    yield DataGap(
        kind=GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
        severity=GapSeverity.IMPORTANT,
        description=(
            f"Query 同时设了 {mediator_field} 和 `target_population` 字段；"
            f"当前 dispatch 只跑了 **{attempted}**，**{skipped}** 被静默"
            f"跳过。"
            f"Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
            f"transport 是 sequential operations（先在 source population"
            f"做 mediation, 再 transport 各 component 到 target），"
            f"不能在一个 query 里同时 dispatch。当前 result 只反映 "
            f"{attempted} 层；{skipped} 分析需要单独 query。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=(
            f"拆成两个 query：先在 source population 跑 {skipped} 分析，"
            f"再用结果做 {attempted}（或反过来按 Cole-Stuart 顺序）"
        ),
        alternative_paths=(
            f"如果只想要 {attempted} 结果，从 query 删除"
            f" {'`target_population`' if attempted == 'mediation' else mediator_field}"
            f" 字段使 dispatch 唯一",
            f"如果只想要 {skipped} 结果，从 query 删除"
            f" {'`target_population`' if skipped == 'mediation' else mediator_field}"
            f" 字段使 dispatch 唯一",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=f"query:dispatch_conflict:{attempted}_dispatched_{skipped}_skipped",
            ),
        ),
    )


def _program_has_no_declared_confounders(program, stmt) -> bool:
    """Returns True when the program declares only the intervention and
    target predicates (no third node that could be a confounder /
    mediator / instrument). Used by the dose-response advisory to detect
    when the DAG is bare X→Y so the renderer can prompt the user to
    confirm minimality is intentional. Conservative: requires both
    intervention and target to be identifiable from stmt — if either is
    None, returns False (don't fire the hint)."""
    if program is None or stmt is None:
        return False
    q = getattr(stmt, "query", None)
    intervention = getattr(q, "intervention", None)
    target = getattr(q, "target", None)
    if intervention is None or target is None:
        return False
    x_atom = getattr(intervention, "atom", intervention)
    y_atom = getattr(target, "atom", target)
    x_pred = getattr(x_atom, "predicate", None)
    y_pred = getattr(y_atom, "predicate", None)
    if x_pred is None or y_pred is None:
        return False
    declared_predicates = {
        st.predicate for st in program.statements
        if isinstance(st, VariableDeclaration)
    }
    extras = declared_predicates - {x_pred, y_pred}
    return len(extras) == 0


def _extract_dose_response_confounders(
    derivation: tuple[DerivationStep, ...],
) -> list[str]:
    """The adjustment set a back-door step already committed to.

    A step's ``inputs`` is a plain dict whose key set is decided by its
    ``rule``, and nothing states that mapping — so a reader has to know
    it rather than infer it. The verifier knows: ``_rule_backdoor_criterion``
    takes the set from ``inputs["z"]`` and rejects the step unless every
    member is an ``Atom``. This is the only reader of a step's inputs
    outside the verifier, so it names the same key and relies on the same
    guarantee instead of describing a shape of its own.

    Sorted, because the emitters pass a ``frozenset``: without it,
    iteration order would decide what the reader is shown.

    Empty when no back-door step is present (an unidentifiable graph, or
    one identified some other way) — the renderer says 'no confounders
    captured' rather than pretending.
    """
    for step in derivation:
        if step.rule not in _ADJUSTMENT_SET_RULE_NAMES or _step_failed(step):
            continue
        z = step.inputs.get("z")
        if not isinstance(z, (frozenset, set, tuple)):
            continue
        return sorted({a.predicate for a in z if isinstance(a, Atom)})
    return []


def _query_target_label(stmt) -> str:
    """Best-effort label for the query's outcome variable.

    Real-test caught: cause queries (with `from`/`to`) used to fall
    through to the literal string ``<target>`` because only effect
    queries' `target.atom` shape was handled. Now also reads `to` for
    cause queries and falls back to a generic phrase instead of an
    angle-bracketed placeholder a renderer would surface verbatim.
    """
    q = getattr(stmt, "query", None)
    if q is None:
        return "目标变量"
    target = getattr(q, "target", None)
    if target is not None:
        atom = getattr(target, "atom", None) or target
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # CauseQuery exposes its source/destination as ``from_atom`` /
    # ``to_atom`` (avoiding Python's ``from`` keyword); AssocQuery uses
    # left/right.
    for attr in ("to_atom", "to", "right"):
        atom = getattr(q, attr, None)
        if atom is not None:
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return "目标变量"


def _query_intervention_label(stmt) -> str:
    """Best-effort label for the query's treatment variable. See
    ``_query_target_label`` for the cause-query motivation."""
    q = getattr(stmt, "query", None)
    if q is None:
        return "干预变量"
    intv = getattr(q, "intervention", None)
    if intv is not None:
        atom = getattr(intv, "atom", None) or intv
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # CauseQuery exposes its source as ``from_atom``; AssocQuery uses
    # ``left``. ``from`` is a Python keyword so it never appears as an
    # attribute name on typed objects, but check it for dict-shaped
    # callers anyway.
    for attr in ("from_atom", "from_", "from", "left"):
        atom = getattr(q, attr, None)
        if atom is not None:
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return "干预变量"


def _classify_ambiguous_variable(
    framing_notes: tuple[FramingNote, ...],
    stmt=None,
) -> Iterable[DataGap]:
    on_query_path = _query_referenced_predicates(stmt)
    for note in framing_notes:
        # Predicates the query directly references take IMPORTANT
        # severity — their framing shapes how the answer is read,
        # so the gap belongs near the headline rather than at the end
        # as a quiet caveat. Predicates declared in the program but
        # not on the query path stay INFORMATIONAL.
        severity = (
            GapSeverity.IMPORTANT
            if note.predicate in on_query_path
            else GapSeverity.INFORMATIONAL
        )
        missing_str = ", ".join(note.missing)
        yield DataGap(
            kind=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
            severity=severity,
            description=(
                f"变量 `{note.predicate}` 缺操作化定义：{missing_str}"
            ),
            blocks=GapBlocks.INTERPRETATION,
            if_provided=(
                "变量框架化后，下游结果（点估计 / bounds）的语义才确定 —— "
                "用户能判断 'P(Y|X)' 到底说的是哪段时间窗 / 哪种测量"
            ),
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.FRAMING_NOTE, ref_id=note.predicate
                ),
            ),
        )


def _query_referenced_predicates(stmt) -> frozenset[str]:
    """Predicates the query atom references — across all query kinds.

    Returns an empty set when ``stmt`` is None or has no recoverable
    query atoms. Effect queries name intervention / target / given /
    mediator; cause queries name from_atom / to_atom; assoc queries
    name left / right.
    """
    if stmt is None:
        return frozenset()
    q = getattr(stmt, "query", None)
    if q is None:
        return frozenset()
    found: set[str] = set()

    def _add_atom(obj) -> None:
        if obj is None:
            return
        atom = getattr(obj, "atom", None) or obj
        pred = getattr(atom, "predicate", None)
        if pred:
            found.add(pred)

    # Effect / counterfactual shape: intervention.atom, target.atom, mediator,
    # given is a list of atoms (or atom wrappers).
    _add_atom(getattr(q, "intervention", None))
    _add_atom(getattr(q, "target", None))
    _add_atom(getattr(q, "mediator", None))
    # Joint multi-mediator set: each M_j is a referenced column too.
    for _m in (getattr(q, "mediators", None) or ()):
        _add_atom(_m)
    given = getattr(q, "given", None)
    if given:
        for entry in given:
            _add_atom(entry)
    # Cause query: from_atom / to_atom (plus dict-shaped fallbacks).
    for attr in ("from_atom", "from_", "from", "to_atom", "to"):
        _add_atom(getattr(q, attr, None))
    # Assoc query: left / right.
    for attr in ("left", "right"):
        _add_atom(getattr(q, attr, None))
    # Counterfactual query: observed (GroundedValue), intervention
    # (Intervention wrapper), counterfactual_target (GroundedValue).
    _add_atom(getattr(q, "observed", None))
    _add_atom(getattr(q, "counterfactual_intervention", None))
    _add_atom(getattr(q, "counterfactual_target", None))
    return frozenset(found)


# ============================================ helpers


def _distribution_signature(target: str) -> str | None:
    """Cheap heuristic: P(...|...) is conditional, P(...) is marginal,
    P(a, b) is joint. The signature is informational; the gap is the
    same blocking shape either way."""
    if "|" in target:
        return "conditional"
    if "," in target:
        return "joint"
    return "marginal"


def _estimate_sample_size_for_mediator(
    target: str,
) -> tuple[int | None, str | None]:
    """Mediation NDE/NIE sample size: only fires when the rendered
    parameter target looks binary-outcome (same heuristic as
    ``_estimate_sample_size_for_distribution``)."""
    from .sample_size import (
        estimate_min_n_mediation_nde_nie,
        is_binary_outcome_distribution,
    )

    if not is_binary_outcome_distribution(target):
        return None, None
    return estimate_min_n_mediation_nde_nie()


def _estimate_sample_size_for_transport_target(
    n_strata: int,
) -> tuple[int | None, str | None]:
    """Target-population P*(Z): single-proportion per stratum."""
    from .sample_size import estimate_min_n_transport_target_marginal

    return estimate_min_n_transport_target_marginal(n_strata=n_strata)


def _estimate_sample_size_for_transport_source(
    n_strata: int,
) -> tuple[int | None, str | None]:
    """Source-population stratified P(Y|do(X), Z)."""
    from .sample_size import estimate_min_n_transport_source_conditional

    return estimate_min_n_transport_source_conditional(n_strata=n_strata)


def _estimate_sample_size_for_distribution(
    display: str, signature: str | None,
) -> tuple[int | None, str | None]:
    """Map a missing-distribution gap to (min_n, precision_target).

    Routes by outcome dtype sniffed from the rendered ``P(...)`` string:

    - Binary outcome (``P(y=true|...)``):
      conditional → two-arm Cohen's h, marginal/joint → single proportion
    - Continuous outcome (``P(systolic_bp=140|...)`` or marginal numeric):
      conditional → two-arm Cohen's d, marginal → leave None (single
      mean estimation needs σ that we don't have)
    - Unknown shape: ``(None, None)`` — better silent than wrong.
    """
    from .sample_size import (
        estimate_min_n_two_arm_continuous,
        is_continuous_outcome_distribution,
    )

    if is_binary_outcome_distribution(display):
        if signature == "conditional":
            return estimate_min_n_two_arm_binary()
        return estimate_min_n_single_proportion()
    if is_continuous_outcome_distribution(display):
        if signature == "conditional":
            return estimate_min_n_two_arm_continuous()
        # marginal continuous: we don't have σ, can't run mean precision
        return None, None
    return None, None


def _step_ref(step: DerivationStep) -> GapProvenanceRef:
    return GapProvenanceRef(
        ref_kind=GapRefKind.DERIVATION_STEP,
        ref_id=step.step_id or step.rule,
    )


def _atom_label(atom_dict: dict) -> str:
    """Render a JSON atom dict back to a short string label for the
    description / required_data.variables list."""
    if isinstance(atom_dict, dict):
        return atom_dict.get("predicate", "<atom>")
    # Defensive: transport_block schemas vary slightly between code paths.
    return str(atom_dict)


_SEVERITY_ORDER: dict[GapSeverity, int] = {
    GapSeverity.BLOCKING: 0,
    GapSeverity.IMPORTANT: 1,
    GapSeverity.INFORMATIONAL: 2,
}


def _gap_sort_key(gap: DataGap) -> tuple[int, str]:
    return (_SEVERITY_ORDER[gap.severity], gap.kind.value)


def data_gap_from_dict(d: dict) -> DataGap:
    """Read one serialized gap back into a :class:`DataGap`.

    Inverse of ``result_orchestrator._data_gap_to_dict``, and the same
    posture as ``verifier.serialization.derivation_from_dict``: it
    re-hydrates, it does not validate semantics. It exists because a
    pass downstream of serialization has to re-derive what this module
    computes FROM gaps — the summary line and the actionable tail — and
    the alternative was a second copy of those rules over dicts.
    """
    rd = d.get("required_data")
    return DataGap(
        kind=GapKind(d["kind"]),
        severity=GapSeverity(d["severity"]),
        description=d["description"],
        blocks=GapBlocks(d["blocks"]),
        provenance=tuple(
            GapProvenanceRef(
                ref_kind=GapRefKind(ref["ref_kind"]), ref_id=ref["ref_id"],
            )
            for ref in d.get("provenance", []) or []
        ),
        signature=d.get("signature"),
        required_data=None if not isinstance(rd, dict) else GapRequiredData(
            data_type=(
                RequiredDataType(rd["data_type"])
                if rd.get("data_type") is not None else None
            ),
            population=rd.get("population"),
            variables=tuple(rd.get("variables", ()) or ()),
            min_sample_size=rd.get("min_sample_size"),
            precision_target=rd.get("precision_target"),
            sampling_point_count=rd.get("sampling_point_count"),
            confounders_required=tuple(rd.get("confounders_required", ()) or ()),
            time_window=rd.get("time_window"),
            sutva_concerns=tuple(rd.get("sutva_concerns", ()) or ()),
        ),
        if_provided=d.get("if_provided"),
        alternative_paths=tuple(d.get("alternative_paths", ()) or ()),
    )


def rederive_summary_and_steps(
    gaps: "list[dict]", *, answer_tier: str | None,
) -> "tuple[str, list[str]]":
    """The two surfaces a serialized report derives from its gap list.

    ``summary`` and ``actionable_next_steps`` are functions of the gaps,
    computed here when the report is first built. A later pass that
    removes gaps — because the data the caller supplied answered them —
    has to recompute both, and it holds the report as JSON.

    Both, and from the one rule. The pass that drops the θ gaps a
    supplied DataFrame answers recomputed the summary from a local copy
    of that rule and left the tail alone, so an ordinary back-door
    result with a point estimate in hand and no distribution gap left in
    the report still opened its next-steps with "补 P(y=True|w=True,
    x=True)". A surface derived from the gaps is not reconciled by
    reconciling the gaps; it is reconciled by being derived again.
    """
    hydrated = [data_gap_from_dict(g) for g in gaps]
    tier = AnswerTier(answer_tier) if answer_tier is not None else None
    return _make_summary(hydrated, tier), _make_actionable_steps(hydrated)


def _make_summary(
    gaps: list[DataGap], answer_tier: AnswerTier | None = None
) -> str:
    if not gaps:
        return ""
    head = gaps[0]
    blocking_count = sum(
        1 for g in gaps if g.severity == GapSeverity.BLOCKING
    )
    if blocking_count <= 1:
        base = head.description
    else:
        base = f"{head.description}（共 {blocking_count} 个 blocking 缺口）"
    # Lead the one-line summary with answer availability so a prose
    # renderer is not misled into showing a blocking gap as "no answer"
    # when an interval is in hand. POINT / None leave the summary as the
    # most-blocking-gap description (no inversion to correct).
    if answer_tier == AnswerTier.INTERVAL:
        return f"可得区间估计（点识别被阻断，但有信息性 bounds）：{base}"
    if answer_tier == AnswerTier.NONE:
        return f"图+数据无法给出点或区间估计（需补假设或更强数据）：{base}"
    return base


def _make_actionable_steps(gaps: list[DataGap]) -> list[str]:
    """Short imperative tail rendered after the gap section.

    Each step is an action ('补 X' / '或：换识别路径'), not a restatement
    of gap.description or gap.if_provided — those live inside the gap
    object and are already surfaced by the renderer within each gap's
    bullet. Concatenating description + if_provided here produced a
    wall of text that just repeated the gap section verbatim.
    """
    steps: list[str] = []
    for gap in gaps:
        if gap.severity == GapSeverity.INFORMATIONAL:
            continue
        if gap.if_provided:
            steps.append(f"补 {_short_label_for(gap)}")
        if gap.alternative_paths:
            steps.append(f"或：{gap.alternative_paths[0]}")
    return steps


def _short_label_for(gap: DataGap) -> str:
    """A noun-phrase label for the actionable_next_steps line. The full
    ``description`` is a complete sentence — concatenating it into "补 X
    → Y" produces a wall of text. Each gap_kind gets a concise label
    that names *what is missing* in 1-3 nouns."""
    rd = gap.required_data
    if gap.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN:
        if rd and rd.variables:
            vars_str = ", ".join(rd.variables)
            pop = rd.population or "目标人群"
            return f"P*({vars_str}) on {pop}"
        return "目标人群上的 P*(Z)"
    if gap.kind == GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN:
        if rd and rd.variables:
            vars_str = ", ".join(rd.variables)
            pop = rd.population or "源人群"
            return f"P(Y|do(X), {vars_str}) 在 {pop} 上的分层条件分布"
        return "源人群上的分层条件分布 P(Y|do(X), Z)"
    if gap.kind == GapKind.MISSING_DISTRIBUTION:
        # gap.description is already "缺概率分布 P(...)" — strip the prefix.
        prefix = "缺概率分布 "
        if gap.description.startswith(prefix):
            return gap.description[len(prefix):]
        return gap.description
    if gap.kind == GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH:
        # iter 203: actionable_next_steps wants a noun-phrase, not the
        # full sentence. The repair is structural, so name the choice
        # rather than the symptom.
        return "图与 CPT 的不一致（修图或补条件量）"
    if gap.kind == GapKind.MISSING_POPULATION_DISTRIBUTION:
        return "目标人群分布"
    if gap.kind == GapKind.MISSING_UNIT_OBSERVATION:
        return "该单位的观测值"
    if gap.kind == GapKind.MISSING_STRUCTURAL_INPUT:
        return "结构输入"
    if gap.kind == GapKind.MISSING_ASSUMPTION:
        # Not always an assumption to declare — the same channel carries
        # experimental inputs and contradictory declarations, so the
        # label names the premise, not the repair.
        return "识别前提"
    if gap.kind == GapKind.MISSING_IV_CANDIDATE:
        return "有效的工具变量"
    if gap.kind == GapKind.MISSING_MEDIATOR_DATA:
        if rd and rd.variables:
            return f"中介 {rd.variables[0]} 的相关分布"
        return "中介相关分布"
    if gap.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET:
        return "可识别的调整集 / 替代识别路径"
    if gap.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION:
        # Provenance carries the predicate name (a FRAMING_NOTE ref).
        for prov in gap.provenance or ():
            if prov.ref_kind == GapRefKind.FRAMING_NOTE and prov.ref_id:
                return f"`{prov.ref_id}` 的操作化定义"
        return "变量的操作化定义"
    return gap.description
