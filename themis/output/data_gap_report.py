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
1. unidentifiable_no_admissible_set       — item species, or a successful
   tian_hedge_witness step
2. missing_distribution                   — item species
3. missing_population_distribution        — no producer (declared)
4. missing_assumption                     — item species
4b. missing_unit_observation              — item species
4c. missing_structural_input              — item species
5. missing_iv_candidate                   — no producer (declared)
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
the set is declared beside GapKind as ``MIRRORED_INTO_EXPLANATION``,
and a kind that leaves the report has its line withdrawn with it):
- unverified_proposal_edge_on_query_path — Phase 11.x §C
- iv_identification_assumption_required — Phase 6.iv
- mediation_identification_assumption_required — Phase 6.mediation
- transport_identification_assumption_required — Phase 9 §T9.1
- llm_declared_ambiguity — A1-emitted ambiguities
- answer_is_bounds_not_point_estimate — Phase 12 bounds-first
- low_confidence_input_data — composite confidence below threshold
- front_door_identification_assumption_required — A6.front-door, with a
  program-shape fallback for the needs_investigation + missing-theta case
- counterfactual_identification_assumption_required — Phase 5 §C
- graph_learned_from_data — Phase 8.1 discovery
- unmeasured_confounder_risk — the DAG declares confounders but no
  bidirected edge; warns that adjusting on measured covariates may leave
  residual unmeasured-confounder bias
- unattempted_layer_due_to_dispatch_conflict — the query sets BOTH a
  mediator and a target_population and only one extension was populated;
  discloses the silent skip
- collider_conditioning_opens_backdoor — fires when EffectQuery.given
  names a collider (selection bias, explicit conditioning)
- selection_on_collider_opens_path — the second shape of the same bias,
  from implicit conditioning: an ObservationStatement on node W encodes a
  sample restriction to W=value, and W has both intervention X and target
  Y as directed ancestors. Restricting the sample conditions on W whether
  or not the query does, which opens X→…→W←…←Y, so the marginal estimate
  carries selection-induced bias. Hernán-Hernández-Díaz-Robins 2004
  *Epidemiology* 15:615 "A Structural Approach to Selection Bias",
  Figure 3-style.
- dichotomized_continuous_measure — fires when a path variable declares a
  non-empty ``threshold`` (a continuous measure cut at a point)
- measurement_error_concern — at least one variable on the identification
  path declares a (measurement | observability) field whose value names a
  documented noisy-measurement pattern (self-report / questionnaire / 24h
  recall / single-occasion BP / proxy / FFQ etc.). Suppressed when
  extensions.ambiguities[*] already declared kind=='measurement_quality'.
  Placed before data collection, like unmeasured_confounder_risk.
  Severity IMPORTANT: regression dilution and non-differential
  mis-classification are identification-impacting.
- ill_defined_intervention_versions — the EffectQuery's intervention
  predicate declares ``state_vs_event = "state"`` without a
  ``time_window`` on the same VariableDeclaration. Per Hernán & Taubman
  2008 *IJO* 32(S3):S8 "Does obesity shorten life? The importance of
  well-defined interventions to answer causal questions" — when the
  exposure is a habitual / persistent attribute, structurally different
  interventions producing the same state value can entail DIFFERENT
  counterfactual outcomes (gastric-banding obesity loss vs lifestyle
  obesity loss). do(X=state) without naming the manipulation route
  silently violates consistency (Hernán & Robins *What If* §3.4).
  Suppressed when extensions declares an ``ill_defined_intervention`` /
  ``well_defined_intervention`` ambiguity.
- graph_theta_independence_mismatch — the d-separation guard refused an
  existing-but-graph-incompatible marginal during formula evaluation, so
  the caller's declared graph and supplied CPTs disagree. It travels the
  same investigation-request channel as missing_distribution, but the
  classifier branches on the d-sep refusal signature in item.reason and
  emits this dedicated kind, because the repair is "fix the graph or
  supply the demanded conditional" and not "supply more theta".

Three of those — measurement, ObservationStatement, ``state_vs_event`` —
were fields the variable schema admitted values for while no classifier
ever read the VALUE. A schema that accepts a distinction nothing acts on
reads as coverage and is not, which is worth checking for whenever a
field is added.

Additional data-need gap_kinds (NOT must-disclose — these surface only
via ``data_gap_report``, not auto-mirrored to ``explanation``):
- transport_source_conditional_unknown — Phase 9 §T9.1 second data need
- dose_response_data_required — Phase 13

Estimator-runtime gap_kinds (attached during themis.estimate dispatch,
NOT by the classifier in this module — they require a fitted estimate
to inspect):
- weak_iv_instrument — first-stage F-stat below the Stock-Yogo (2005)
  threshold; appended to data_gap_report by
  themis/estimation/dispatch.py._attach_weak_iv_warning_if_low_f after
  estimate_iv_ate returns.
- overidentification_rejected — the Sargan over-identification test rejected
  the q >= 2 instruments' joint validity (the data refute an exclusion
  restriction); appended by themis/estimation/dispatch.py._attach_overid_iv_warnings
  after estimate_iv_overid returns.
- propensity_overlap_violation — > 5% of sample has estimated P(X=1|Z)
  outside [0.05, 0.95]; appended by
  themis/estimation/dispatch.py._attach_propensity_overlap_warning
  after estimate_backdoor_ate when the adjustment set is non-empty.
- outcome_model_quasi_separation — > 10% of fitted P(Y|X,Z) falls
  outside [0.01, 0.99] (outcome regression saturates, logit blows up);
  appended by
  themis/estimation/dispatch.py._attach_outcome_separation_warning
  after estimate_backdoor_ate with logistic outcome.

This list is a reading guide, not the declaration: which kinds are
mirrored is stated once in ``themis.types.MIRRORED_INTO_EXPLANATION`` /
``NOT_MIRRORED_INTO_EXPLANATION``, and an unclassified kind raises at
import.
"""
from __future__ import annotations

from typing import Iterable, NamedTuple, Protocol

from .. import blocks, gaps, language, questions, refusals
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

# ============================================ what a step can say
#
# Every step in a kernel derivation is a step that SUCCEEDED. Nothing in
# this module reads for a failed one, because the kernel has no way to
# write one. Unidentifiability arrives by one of two routes and neither
# is a failure record: a SUCCESSFUL ``tian_hedge_witness`` step whose
# output is ``StructuralResult(False)`` — the c-component is the proof,
# and the verifier replays it — or, when the complete algorithm exhausts
# without a witness, an investigation item declaring
# ``UNIDENTIFIABLE_NO_ADMISSIBLE_SET`` on the item channel.
#
# A third representation used to exist: a step named
# ``unidentifiable_via_*``, or one carrying ``success=False``. This module
# scanned for it, and the scan outlived the Tian wiring that replaced it,
# reading for a shape no producer could make. What kept the scan looking
# alive was its own unit tests, which built the failed step by hand — over
# a full suite the predicate answered "this failed" ten times, all ten
# inside those tests and none from a run.
#
# The wire form still carries ``success`` and the verifier still reads it,
# and that asymmetry is the point rather than a leftover: the verifier's
# input is a derivation somebody ELSE wrote, which may claim a failure the
# kernel would never produce, and checking that claim is its whole job.
# ``tests/test_no_step_the_kernel_wrote_says_it_failed.py`` holds the
# producer side to the paragraph above.

# Rule names whose ``inputs`` carry an adjustment set, under "z". Named
# rather than matched on a substring: "identify_via_backdoor" reads like
# one of these and carries only StepRefs, so a substring test finds a
# step with nothing in it and stops looking.
_ADJUSTMENT_SET_RULE_NAMES: frozenset[str] = frozenset({
    "backdoor_criterion",
    "joint_backdoor_criterion",
})


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
    bounds_results=(),
    numeric_result=None,
    confidence: float | None = None,
    dispatch=None,
    lang: language.Lang | str = language.DEFAULT,
) -> DataGapReport | None:
    """Synthesize a DataGapReport from the result-envelope signals.

    Returns ``None`` when the question names no quantity — so nothing but
    framing can leave it short of data — and no framing or assumption gaps
    exist. For a question that does name one the returned report may still
    have ``gaps=()`` when fully solved — callers can distinguish "no need
    to ask" (None) from "asked and got a clean bill of health" (empty
    tuple).

    ``lang`` is the reader's, and it reaches every producer below because
    the envelope carries no language of its own: what the report says is
    settled here, at the moment it is written, not by whoever reads it
    afterwards.
    """
    extensions = extensions or {}

    must_disclose_gaps: list[DataGap] = []
    must_disclose_gaps.extend(
        _classify_unverified_proposal_edges(
            program, structural_result, stmt, extensions, lang=lang,
        )
    )
    must_disclose_gaps.extend(_classify_iv_assumption(extensions, lang=lang))
    must_disclose_gaps.extend(
        _classify_mediation_assumptions(extensions, lang=lang))
    must_disclose_gaps.extend(
        _classify_transport_assumptions(extensions, lang=lang))
    must_disclose_gaps.extend(
        _classify_llm_ambiguities(extensions, lang=lang))
    must_disclose_gaps.extend(
        _classify_bounds_not_point(bounds_results, lang=lang))
    must_disclose_gaps.extend(_classify_low_confidence(confidence, lang=lang))
    must_disclose_gaps.extend(_classify_front_door_assumptions(
        derivation, program=program, stmt=stmt, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_counterfactual_assumptions(
        derivation, status, query_kind, lang=lang,
    ))
    must_disclose_gaps.extend(
        _classify_graph_learned_from_data(program, lang=lang))
    must_disclose_gaps.extend(_classify_unmeasured_confounder_risk(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        lang=lang,
    ))
    must_disclose_gaps.extend(_classify_measurement_error_concern(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_unattempted_layer_dispatch_conflict(
        dispatch=dispatch, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_collider_conditioning_opens_backdoor(
        program=program, stmt=stmt, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_selection_on_collider_opens_path(
        program=program, stmt=stmt, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_ill_defined_intervention_versions(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions, lang=lang,
    ))
    must_disclose_gaps.extend(_classify_dichotomized_continuous_measure(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions, lang=lang,
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
    gaps.extend(_classify_unidentifiable(derivation, lang=lang))
    # Every investigation item, as the species the kernel declared for it.
    # Total over the channel by construction, so nothing downstream has to
    # sweep for items no pass claimed.
    gaps.extend(_classify_investigation_items(
        investigation_requests, query_kind, lang=lang))
    gaps.extend(_classify_missing_mediator(
        extensions, investigation_requests, lang=lang))
    gaps.extend(
        _classify_transport_target_distribution(extensions, lang=lang))
    gaps.extend(_classify_ambiguous_variable(framing_notes, stmt, lang=lang))
    gaps.extend(
        _classify_dose_response_data(program, stmt, derivation, lang=lang))

    gaps = _rewrite_iv_aware_alternatives(gaps, bounds_results, lang=lang)
    gaps.sort(key=_gap_sort_key)
    answer_tier = _compute_answer_tier(
        query_kind, gaps, bounds_results, status, numeric_result, stmt,
    )
    if answer_tier is AnswerTier.NONE:
        gaps = _withdraw_interval_offers(gaps, query_kind, lang=lang)
    summary = _make_summary(gaps, answer_tier, lang=lang)
    actionable = _make_actionable_steps(gaps, lang=lang)
    return DataGapReport(
        summary=summary,
        gaps=tuple(gaps),
        actionable_next_steps=tuple(actionable),
        answer_tier=answer_tier,
    )


_ACCEPT_AN_INTERVAL: language.Words = {
    "zh": "接受 {fallback} 给区间答案",
    "en": "accept {fallback} and take the interval answer",
}


def _interval_offer(
    query_kind: QueryKind, *, lang: language.Lang | str,
) -> str | None:
    """The one sentence that offers this question's interval instead of a
    point, or None where it has no interval to offer.

    Built here rather than written out, so the offer and the withdrawal
    below are the same string by construction: a report that has just said
    no interval is reachable must not leave one on offer beside it, and
    matching a promise by substring is how that check would rot.
    """
    fallback = questions.reading_of(query_kind.value).interval_fallback
    if fallback is None:
        return None
    return language.fill(_ACCEPT_AN_INTERVAL, lang, fallback=fallback)


def _withdraw_interval_offers(
    gaps: list[DataGap], query_kind: QueryKind, *,
    lang: language.Lang | str,
) -> list[DataGap]:
    """Take back the interval a NONE tier has just ruled out.

    The tier is the report's own word on what is still reachable; a gap
    still advising "accept bounds for an interval answer" contradicts it
    in the same breath, and the reader acts on the gap. Only the offer
    this module generated is withdrawn — a concrete "已计算 bounds" line
    means bounds exist, and a result carrying those does not reach NONE.
    """
    from dataclasses import replace as _replace

    offer = _interval_offer(query_kind, lang=lang)
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
    bounds_results,
    status: ResultStatus,
    numeric_result=None,
    stmt=None,
) -> AnswerTier | None:
    """The strongest answer available, orthogonal to gap severity.

    Two steps. First, is the POINT estimand blocked? — keyed on the
    authoritative "point ID failed" signals, NOT on bounds presence:
    bounds are attached to EVERY needs_investigation binary/discrete
    effect as an assumption-free floor (scheduler ``_attach_bounds_results``,
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
    of two channels and both count: ``bounds_results``, the effect query's
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
    # One informative row is an interval in hand. The bounds channel
    # reports every method whose assumptions hold, and a vacuous floor
    # beside a sharp instrument interval is still an interval.
    if any(
        not getattr(b, "width_when_uninformative", False)
        for b in (bounds_results or ())
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


_FIND_IV_ADVICE: language.Words = {
    "zh": "找一个满足 IV 条件的工具变量",
    "en": "find an instrument that satisfies the IV conditions",
}
_IV_TIGHTEN_TO_A_POINT: language.Words = {
    "zh": "工具变量已声明并已用于给出区间；要把区间收紧成点估计，需补一个额外假"
          "设：monotonicity（→ LATE/Wald）或 linearity（→ 2SLS/ATE）",
    "en": "an instrument is declared and the interval already uses it; "
          "tightening that interval to a point needs one further assumption "
          "— monotonicity (→ LATE/Wald) or linearity (→ 2SLS/ATE)",
}


def _rewrite_iv_aware_alternatives(
    gaps: list[DataGap],
    bounds_results,
    *,
    lang: language.Lang | str,
) -> list[DataGap]:
    """Instrument-aware repair of the static unidentifiable advice.

    When IV bounds were already computed from a declared instrument
    (a ``balke_pearl_iv`` row among ``bounds_results``), the boilerplate "go
    find an instrument satisfying the IV conditions" alternative on an
    ``unidentifiable_no_admissible_set`` gap is self-contradictory — the
    interval that same gap points at LITERALLY came from that instrument.
    Replace only that one line with the honest next step: an instrument
    is already in hand; tightening the interval to a POINT estimate needs
    an extra assumption (monotonicity -> LATE / linearity -> 2SLS). The
    other alternatives (measure the confounder, run an RCT) are untouched.

    Detected purely from ``bounds_results`` — no graph walk, no extension
    stamping, so it cannot fire a spurious second gap. Real-usage probe,
    2026-06-15.
    """
    from dataclasses import replace

    if not any(
        getattr(getattr(b, "method", None), "value", None) == "balke_pearl_iv"
        for b in (bounds_results or ())
    ):
        return gaps
    out: list[DataGap] = []
    boilerplate = language.fill(_FIND_IV_ADVICE, lang)
    for g in gaps:
        if (
            g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
            and boilerplate in g.alternative_paths
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
                        language.fill(_IV_TIGHTEN_TO_A_POINT, lang)
                    ) if a == boilerplate else a
                    for a in g.alternative_paths
                ),
            ))
        else:
            out.append(g)
    return out


_EDGE_FROM_DISCOVERY: language.Words = {
    "zh": "结构性回答途径上的边 `{edge}` 是因果发现算法 `{algorithm}` 从数据中学"
          "出的，结果以算法假设（如 PC: 忠实性 + 因果充足性；LiNGAM: 线性 + 非高"
          "斯）为前提。",
    "en": "the edge `{edge}` on the route to the structural answer was "
          "learned from the data by the causal-discovery algorithm "
          "`{algorithm}`, so the result rests on that algorithm's assumptions "
          "(PC: faithfulness and causal sufficiency; LiNGAM: linearity and "
          "non-Gaussian noise).",
}
_EDGE_BOOTSTRAP_STABILITY: language.Words = {
    "zh": "自助法稳定度 {confidence}（该边在此比例的数据重采样中重现；越低越可能"
          "是采样噪声，越应复核）。",
    "en": "bootstrap stability {confidence} (the share of resamples the edge "
          "reappears in; the lower it is the more likely it is sampling "
          "noise, and the more it wants checking).",
}
_EDGE_FROM_LLM: language.Words = {
    "zh": "结构性回答途径上的边 `{edge}` 是上游 LLM 提出的假设"
          "（annotations.source = llm_proposal），不是经证据支持的边。当前回答相"
          "当于复述这条假设，而非独立验证。",
    "en": "the edge `{edge}` on the route to the structural answer is a "
          "hypothesis the upstream LLM proposed (annotations.source = "
          "llm_proposal), not an edge evidence supports. The answer as it "
          "stands restates that hypothesis rather than verifying it.",
}
_EDGE_IF_PROVIDED: language.Words = {
    "zh": "可换成证据支持的边或外部文献的引用",
    "en": "replace it with an edge evidence supports, or with a citation to "
          "the literature",
}
_EDGE_GIVE_A_SOURCE: language.Words = {
    "zh": "提供支持这条边的研究 / 数据来源",
    "en": "give the study or the data this edge rests on",
}
_EDGE_ASK_CONDITIONALLY: language.Words = {
    "zh": "改为询问'若该边成立则…'的条件性问题",
    "en": "ask the conditional question instead — 'if this edge holds, then "
          "…'",
}


def _classify_unverified_proposal_edges(
    program,
    structural_result,
    stmt,
    extensions: dict,
    *,
    lang: language.Lang | str,
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
            description = language.fill(_EDGE_FROM_DISCOVERY, lang,
                                        edge=edge_render,
                                        algorithm=algo.upper())
            if confidence is not None:
                description += language.fill(
                    _EDGE_BOOTSTRAP_STABILITY, lang,
                    confidence=f"{confidence:.0%}",
                )
        else:
            description = language.fill(_EDGE_FROM_LLM, lang,
                                        edge=edge_render)
        yield DataGap(
            kind=GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            if_provided=language.fill(_EDGE_IF_PROVIDED, lang),
            alternative_paths=(
                language.fill(_EDGE_GIVE_A_SOURCE, lang),
                language.fill(_EDGE_ASK_CONDITIONALLY, lang),
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

    iv = (extensions or {}).get(blocks.Block.IV_IDENTIFICATION) or {}
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


_IV_ASSUMPTION_REQUIRED: language.Words = {
    "zh": "IV 识别（工具变量 `{instrument}`）的有效性以下列假设为前提："
          "{assumption}。读 IV 估计前应明确这条假设是否在你的场景下成立。",
    "en": "IV identification (through the instrument `{instrument}`) is valid "
          "only under this assumption: {assumption}. Settle whether it holds "
          "in your setting before reading the IV estimate.",
}


def _classify_iv_assumption(
    extensions: dict, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """IV identification rests on monotonicity (LATE/Wald) or linearity
    (2SLS/ATE). The extension carries the wording verbatim; surface as a
    must-disclose caveat so the renderer cannot present an IV estimate
    as an unconditional ATE."""
    iv = (extensions or {}).get(blocks.Block.IV_IDENTIFICATION) or {}
    assumption = iv.get("required_assumption")
    instrument = iv.get("instrument")
    if not assumption:
        return
    yield DataGap(
        kind=GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=language.fill(_IV_ASSUMPTION_REQUIRED, lang,
                                  instrument=instrument,
                                  assumption=assumption),
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
        (blocks.Block.MEDIATION_DECOMPOSITION, False),
        (blocks.Block.MEDIATION_JOINT_DECOMPOSITION, True),
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


_MEDIATOR_BLOCK_CLAUSE: language.Words = {
    "zh": "（中介组 {subject}，作为一整组分解，不拆到单条路径）",
    "en": "(the mediator block {subject}, decomposed as one whole and not "
          "split into single paths)",
}
_MEDIATOR_CLAUSE: language.Words = {
    "zh": "（中介 {subject}）", "en": "(mediator {subject})",
}
_MEDIATION_IDENTIFIABLE: language.Words = {
    "zh": "中介分解 {branch} 标识为可识别，前提是以下假设成立：{assumptions}。"
          "{subject}",
    "en": "the {branch} mediation decomposition is marked identifiable, on "
          "the premise that these assumptions hold: {assumptions}. {subject}",
}


def _classify_mediation_assumptions(
    extensions: dict, *, lang: language.Lang | str,
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
            language.fill(_MEDIATOR_BLOCK_CLAUSE, lang, subject=view.subject)
            if view.joint
            else language.fill(_MEDIATOR_CLAUSE, lang, subject=view.subject)
        )
        yield DataGap(
            kind=GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=language.fill(
                _MEDIATION_IDENTIFIABLE, lang, branch=branch_name,
                assumptions=", ".join(assumptions), subject=subject_clause,
            ),
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=f"extensions.{view.key}.{branch_key}.assumptions",
                ),
            ),
        )


_SOURCE_POPULATION_UNNAMED: language.Words = {
    "zh": "<源人群>", "en": "<source population>",
}
_TARGET_POPULATION_UNNAMED: language.Words = {
    "zh": "<目标人群>", "en": "<target population>",
}
_TRANSPORT_S_ADMISSIBILITY: language.Words = {
    "zh": "将估计从 {source} 转移到 {target} 的有效性以 S-admissibility 为前提："
          "声明的 selection_nodes 必须正确捕获两人群间分布差异。",
    "en": "carrying the estimate from {source} to {target} is valid only "
          "under S-admissibility: the selection_nodes declared have to "
          "capture the distributional differences between the two "
          "populations correctly.",
}


def _classify_transport_assumptions(
    extensions: dict, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Transport identification (Bareinboim-Pearl) requires
    S-admissibility plus correct selection-node specification. The
    transferred estimate is invalid outside those assumptions."""
    transport = (extensions or {}).get(blocks.Block.TRANSPORT_IDENTIFICATION) or {}
    if not transport:
        return
    src_pop = transport.get(
        "source_population", language.fill(_SOURCE_POPULATION_UNNAMED, lang))
    tgt_pop = transport.get(
        "target_population", language.fill(_TARGET_POPULATION_UNNAMED, lang))
    yield DataGap(
        kind=GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=language.fill(_TRANSPORT_S_ADMISSIBILITY, lang,
                                  source=src_pop, target=tgt_pop),
        blocks=GapBlocks.TRANSPORT,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.transport_identification",
            ),
        ),
    )


_AMBIGUITY_RATIONALE: language.Words = {
    "zh": "：{rationale}", "en": ": {rationale}",
}
_LLM_AMBIGUITY: language.Words = {
    "zh": "上游 LLM 标记了不确定性 `{kind}`{rationale}。答案的解读应将其考虑在"
          "内。",
    "en": "the upstream LLM flagged an uncertainty, `{kind}`{rationale}. Read "
          "the answer with that in view.",
}


def _classify_llm_ambiguities(
    extensions: dict, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """LLM-declared ambiguities the kernel did not resolve into a
    structural decision (reciprocal causation, mechanism vs existence,
    mediator choice). Renderer must surface the LLM's own uncertainty —
    leaving these unspoken would make the answer look confident when the
    upstream itself wasn't."""
    ambiguities = (extensions or {}).get(blocks.Block.AMBIGUITIES) or ()
    for amb in ambiguities:
        if not isinstance(amb, dict):
            continue
        kind = amb.get("kind", "<unspecified>")
        rationale = amb.get("rationale") or amb.get("note") or ""
        # dose_response_query has its own dedicated gap_kind; skip.
        if kind == "dose_response_query":
            continue
        suffix = (language.fill(_AMBIGUITY_RATIONALE, lang,
                                rationale=rationale) if rationale else "")
        yield DataGap(
            kind=GapKind.LLM_DECLARED_AMBIGUITY,
            severity=GapSeverity.INFORMATIONAL,
            description=language.fill(_LLM_AMBIGUITY, lang,
                                      kind=kind, rationale=suffix),
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


_LOW_CONFIDENCE: language.Words = {
    "zh": "答案的复合可信度为 {confidence}（< {threshold}）— 至少有一项输入语句的"
          "置信度较低，结果应视为不确定的。具体的薄弱环节见 `confidence_sources` "
          "中标记 is_weakest=true 的条目。",
    "en": "the answer's composite confidence is {confidence} (< {threshold}) "
          "— at least one input statement carries substantial uncertainty, "
          "and the result should be read as uncertain. The weak links "
          "themselves are the entries marked is_weakest=true in "
          "`confidence_sources`.",
}


def _classify_low_confidence(
    confidence: float | None, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
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
        description=language.fill(
            _LOW_CONFIDENCE, lang, confidence=f"{confidence:.2f}",
            threshold=_LOW_CONFIDENCE_THRESHOLD,
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


_FRONT_DOOR_PREMISES: language.Words = {
    "zh": "前门识别（Pearl front-door criterion）的有效性以下列假设为前提：(1) 中"
          "介集 M 阻断 X→Y 的所有有向路径；(2) 不存在未阻断的 X→M 后门路径；(3) "
          "所有 M→Y 后门路径已被 X 阻断；(4) consistency of potential outcomes。"
          "若任一假设不成立，前门估计失效。",
    "en": "front-door identification (Pearl's front-door criterion) is valid "
          "only under these assumptions: (1) the mediator set M intercepts "
          "every directed path from X to Y; (2) there is no unblocked "
          "back-door path from X to M; (3) every back-door path from M to Y "
          "is blocked by X; (4) consistency of potential outcomes. If any one "
          "of them fails, the front-door estimate fails with it.",
}


def _classify_front_door_assumptions(
    derivation: tuple[DerivationStep, ...],
    *,
    program=None,
    stmt=None,
    lang: language.Lang | str,
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
    description = language.fill(_FRONT_DOOR_PREMISES, lang)
    triggering = next(
        (
            step for step in derivation
            if step.rule in _FRONT_DOOR_DERIVATION_RULES
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


_COUNTERFACTUAL_PREMISES: language.Words = {
    "zh": "反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的潜在结果）"
          "+ composition 公理为前提，这两条无法从数据本身验证；跨世界的格子还要靠"
          "某一条路线把两个世界连起来，那条路线自己的前提也一并被继承——具体是哪"
          "条、可不可检验，看答案上的 interventional_risk_provenance 与假设台账逐"
          "条列出的那几行；单调性若声明，是收紧这一格的额外前提，不是回答的前提。",
    "en": "counterfactual reasoning is valid only under consistency (an "
          "observed value = the potential outcome under do(the value it "
          "actually took)) and the composition axiom, neither of which the "
          "data can check; a cross-world cell needs some route to join the "
          "two worlds besides, and that route's own premises are inherited "
          "with it — which route, and whether it can be tested, is on the "
          "answer's interventional_risk_provenance and in the rows the "
          "assumption ledger lists one by one. Monotonicity, where it is "
          "declared, is a further premise that tightens this cell rather "
          "than a premise of the answer.",
}


def _classify_counterfactual_assumptions(
    derivation: tuple[DerivationStep, ...],
    status: ResultStatus,
    query_kind: QueryKind,
    *,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Counterfactual identification rests on premises no data can check,
    and the list is layered: consistency + composition always; and, whenever
    the two worlds differ, whatever licensed the route that crossed them.

    That second layer names no routes. It used to list three — an adjustment
    set, the ID algorithm, a randomized experiment — which was the whole set
    for as long as a cell could only be solved from a point-identified
    P(Y=1|do x'); a cell bounded over an instrument's response polytope
    borrows no such number and appears in none of them. The route's own
    licence is a required field on the answer and says which one ran, so
    this caveat says WHERE to read it instead of keeping a copy that goes
    stale the next time the cascade grows a branch. It also stops claiming
    the whole layer is unfalsifiable: an instrument's first stage is visible
    in the data, and a declared monotonicity can be refuted by the very
    program that consumed it.

    The user asking a counterfactual question is itself the trigger — the
    caveat applies whether the kernel solved the cell, bounded it, or
    stopped for missing inputs. Without it a stalled counterfactual
    surfaces only as a generic 'missing assumption' gap and the L3 vs L2
    distinction is lost in rendering."""
    triggering = next(
        (
            step for step in derivation
            if step.rule in _COUNTERFACTUAL_DERIVATION_RULES
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
        description=language.fill(_COUNTERFACTUAL_PREMISES, lang),
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


#: What separates two items of a list inside one sentence. Full-width in
#: Chinese, and a semicolon plus a space in English — it is punctuation of
#: the sentence it lands in, so it belongs to that sentence's language.
_BOUNDS_NOT_A_POINT: language.Words = {
    "zh": "答案是符号区间，不是点估计。渲染时必须明示这是 bounds 而非具体数值。",
    "en": "the answer is a symbolic interval, not a point estimate. Whatever "
          "renders it has to say so rather than let it read as a number.",
}
_BOUNDS_RESTS_ON: language.Words = {
    "zh": "假设 {assumptions}", "en": "assuming {assumptions}",
}
_BOUNDS_RESTS_ON_NOTHING: language.Words = {
    "zh": "无假设", "en": "no assumptions",
}
_BOUNDS_ROW: language.Words = {
    "zh": "`{method}`（{rests_on}）", "en": "`{method}` ({rests_on})",
}
_BOUNDS_UNINFORMATIVE: language.Words = {
    "zh": "，且区间为非信息性 [0,1] / [-1,1]，无实际辨别力",
    "en": ", and the interval is the uninformative [0,1] / [-1,1], which "
          "tells nothing apart",
}
_BOUNDS_ONE_ROW: language.Words = {
    "zh": "区间来自 {row}。", "en": "the interval comes from {row}.",
}
_BOUNDS_MANY_ROWS: language.Words = {
    "zh": "共 {count} 条，界定的是同一个量，各自靠不同的假设：{rows}。读者按自己"
          "接受哪组假设来选，**不要取交**：两条都成立时交集确实含真值，但它不是"
          "二者合取下的锐界（那要数值端在响应型多面体上另解一次），而一个不带标"
          "签的区间会把各自靠什么抹掉。",
    "en": "{count} of them, bounding the same quantity and each resting on "
          "different assumptions: {rows}. Choose by which set of assumptions "
          "you accept, and **do not intersect them**: where both hold the "
          "intersection does contain the true value, but it is not the sharp "
          "bound under their conjunction (that would take the numeric side "
          "solving once more over the response-type polytope), and an "
          "interval with no label on it erases what each one stood on.",
}


def _classify_bounds_not_point(
    bounds_results, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """The answer is a symbolic interval rather than a point estimate —
    and it is a set of them, one per method whose assumptions this program
    supports. Surfaces the method-vs-point distinction and, per row, what
    that row rests on; without the assumptions the bounds read like a
    point with confidence intervals.

    One gap naming every row, not one gap per row. They are readings of a
    single answer — the same estimand under different premises — and a gap
    apiece would present them as several separate shortfalls.
    """
    rows = tuple(bounds_results or ())
    if not rows:
        return
    per_row: list[str] = []
    for b in rows:
        method = getattr(b, "method", None)
        # ``.value`` when it is an enum member, the thing itself otherwise.
        method_name = str(getattr(method, "value", method))
        assumptions = getattr(b, "assumptions", ()) or ()
        rests_on = (
            language.fill(_BOUNDS_RESTS_ON, lang,
                          assumptions=", ".join(assumptions))
            if assumptions else language.fill(_BOUNDS_RESTS_ON_NOTHING, lang)
        )
        piece = language.fill(_BOUNDS_ROW, lang,
                              method=method_name, rests_on=rests_on)
        if getattr(b, "width_when_uninformative", False):
            piece += language.fill(_BOUNDS_UNINFORMATIVE, lang)
        per_row.append(piece)
    pieces: list[str] = [language.fill(_BOUNDS_NOT_A_POINT, lang)]
    if len(per_row) == 1:
        pieces.append(language.fill(_BOUNDS_ONE_ROW, lang, row=per_row[0]))
    else:
        pieces.append(language.fill(
            _BOUNDS_MANY_ROWS, lang, count=len(per_row),
            rows=language.fill(language.BETWEEN_STATEMENTS, lang).join(per_row),
        ))
    yield DataGap(
        kind=GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
        severity=GapSeverity.INFORMATIONAL,
        description="".join(pieces),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="bounds_results",
            ),
        ),
    )


_GRAPH_WAS_LEARNED: language.Words = {
    "zh": "DAG 是由因果发现算法 `{algorithm}` 从数据中学出的，不是用领域知识手工"
          "声明的。",
    "en": "the DAG was learned from the data by the causal-discovery "
          "algorithm `{algorithm}` rather than declared by hand from domain "
          "knowledge.",
}
_DISCOVERY_ALPHA: language.Words = {
    "zh": "显著性阈值 α = {alpha}。",
    "en": "significance threshold α = {alpha}.",
}
_DISCOVERY_SAMPLE_SIZE: language.Words = {
    "zh": "样本量 N = {n}。", "en": "sample size N = {n}.",
}
_DISCOVERY_INHERITS_ASSUMPTIONS: language.Words = {
    "zh": "结果继承算法的核心假设：PC 需要忠实性 (faithfulness) + 因果充足性 "
          "(causal sufficiency)；FCI 放宽因果充足性但仍需忠实性；LiNGAM 需要线性 "
          "+ 非高斯噪声。",
    "en": "the result inherits the algorithm's core assumptions: PC needs "
          "faithfulness and causal sufficiency; FCI relaxes causal "
          "sufficiency but still needs faithfulness; LiNGAM needs linearity "
          "and non-Gaussian noise.",
}
_DISCOVERY_VIOLATIONS: language.Words = {
    "zh": " 检测到当前数据上算法假设的具体违反：{violations}。",
    "en": " specific violations of the algorithm's assumptions were detected "
          "on this data: {violations}.",
}


def _classify_graph_learned_from_data(
    program, *, lang: language.Lang | str,
) -> Iterable[DataGap]:
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
    pieces = [language.fill(_GRAPH_WAS_LEARNED, lang, algorithm=algo.upper())]
    if alpha is not None:
        pieces.append(language.fill(_DISCOVERY_ALPHA, lang, alpha=alpha))
    if n is not None:
        pieces.append(language.fill(_DISCOVERY_SAMPLE_SIZE, lang, n=n))
    pieces.append(language.fill(_DISCOVERY_INHERITS_ASSUMPTIONS, lang))
    violations = metadata.get("assumption_violations") or ()
    if violations:
        pieces.append(language.fill(
            _DISCOVERY_VIOLATIONS, lang,
            violations=language.fill(language.BETWEEN_STATEMENTS, lang).join(violations),
        ))
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


_UNMEASURED_CONFOUNDER_RISK: language.Words = {
    "zh": "Backdoor 识别假设你列出的 confounder 已经测全 —— DAG 里没有声明任何 "
          "bidirected / latent-common-cause 边。这是 measured-covariate 调整后仍"
          "残留 unmeasured confounder 的典型场景。多个域有 well-documented "
          "RCT-vs-observational（或实验-vs-观察）反转：医学（HRT-CVD WHI 2002、"
          "vitamin D-CVD VITAL 2018）、劳动经济学（Card 1995 schooling-earnings "
          "中的 ability bias）、教育评估（charter schools CREDO 2013 中的 "
          "parental motivation）。机制各域不同（healthy-user bias / ability bias "
          "/ selection effects），但**结构教训一致**——measured 调整不够。拿到数"
          "据后跑 sensitivity analysis（E-value）量化对 unmeasured confounder 的"
          "稳健性，或在 DAG 里把怀疑的 latent 显式声明为 bidirected。",
    "en": "back-door identification assumes the confounders you listed are "
          "all of them — the DAG declares no bidirected / "
          "latent-common-cause edge at all. This is the standard setting for "
          "an unmeasured confounder surviving adjustment on the measured "
          "covariates. Several fields have well-documented "
          "RCT-vs-observational (or experiment-vs-observation) reversals: "
          "medicine (HRT-CVD, WHI 2002; vitamin D-CVD, VITAL 2018), labour "
          "economics (ability bias in Card 1995's schooling-earnings "
          "estimates), education evaluation (parental motivation in CREDO "
          "2013's charter schools). The mechanism differs by field "
          "(healthy-user bias / ability bias / selection effects), but **the "
          "structural lesson is the same** — adjusting on the measured ones "
          "is not enough. Once the data is in hand, run a sensitivity "
          "analysis (E-value) to quantify how robust this is to an "
          "unmeasured confounder, or declare the latent you suspect as a "
          "bidirected edge in the DAG.",
}
_ADD_A_BIDIRECTED_EDGE: language.Words = {
    "zh": "若怀疑某 latent 共因，添加 bidirected 边；Themis 会改走 ADMG-aware"
          "（Tian / front-door / IV）识别策略并报对应的 structural gap",
    "en": "if you suspect a latent common cause, add a bidirected edge; "
          "Themis will switch to an ADMG-aware identification strategy (Tian "
          "/ front-door / IV) and report the structural gap that goes with "
          "it",
}
_STEP_E_VALUE: language.Words = {
    "zh": "数据到位后跑 E-value 敏感性分析（Phase 8.2，对二值结局自动附）",
    "en": "run an E-value sensitivity analysis once the data is in hand "
          "(Phase 8.2, attached automatically for a binary outcome)",
}
_STEP_CROSS_CHECK_EXPERIMENT: language.Words = {
    "zh": "有随机对照 / 准实验数据时，拿它和这个观察性估计相互印证",
    "en": "where randomized or quasi-experimental data exists, check it "
          "against this observational estimate",
}
_STEP_TARGET_TRIAL: language.Words = {
    "zh": "按 Hernán-Robins 的目标试验模拟（target trial emulation）重新设计：明"
          "确入组条件，做 per-protocol 分析",
    "en": "redesign it as a Hernán-Robins target trial emulation: state the "
          "eligibility criteria, and do a per-protocol analysis",
}


def _classify_unmeasured_confounder_risk(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    lang: language.Lang | str,
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
        description=language.fill(_UNMEASURED_CONFOUNDER_RISK, lang),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=language.fill(_ADD_A_BIDIRECTED_EDGE, lang),
        # Two of these three were the only English sentences left in this
        # channel: 46 of the 48 non-Chinese alternative_paths one suite run
        # produced. A path a reader cannot act on is not an alternative.
        alternative_paths=(
            language.fill(_STEP_E_VALUE, lang),
            language.fill(_STEP_CROSS_CHECK_EXPERIMENT, lang),
            language.fill(_STEP_TARGET_TRIAL, lang),
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
#
# Both languages sit in one pool on purpose. A needle is matched against
# the user's declaration, so what settles its language is the program's
# and not the reader's — splitting the pool by reader would stop it
# recognizing a declaration written in the other one.
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


#: One flagged variable, its role, and the phrase that flagged it. The
#: phrase is the user's own declaration quoted back, so it arrives in
#: whichever language they wrote it in.
_NOISY_MEASURE_SUMMARY: language.Words = {
    "zh": "{variable}〔{role}〕({field}: 含 “{phrase}”)",
    "en": "{variable} [{role}] ({field}: contains “{phrase}”)",
}
_MEASUREMENT_ERROR_RISK: language.Words = {
    "zh": "测量误差风险：识别路径上有变量声明了高噪声测量方式 — {variables}。 经"
          "典文献：MacMahon 1990 Lancet 单次门诊 BP 测量因 within-person 变异导"
          "致 BP→CHD 斜率被 regression dilution 向 0 衰减约 60%；Hernán & "
          "Robins What If §9 自报告 / 问卷暴露的 non-differential "
          "mis-classification 同样使 估计值低估真效应；Fuller 1987 Measurement "
          "Error Models 给出 attenuation theorem 的形式定义。结构层只做识别 + 缺"
          "口诊断；但若被误分类的**离散结局**或**二值暴露**有验证研究给出的混淆"
          "矩阵，数值层可做去衰减校正（estimate(..., "
          "misclassification={{<结局或暴露变量名>: {{confusion_matrix, "
          "states}}}})），逐后门层做矩阵求逆——结局侧 p_true=M⁻¹p_obs（二值即 "
          "Rogan-Gladen 1978），暴露侧用矩阵法沿暴露轴对 (X,Y) 联合逐结局列求逆"
          "（Barron 1977 / Greenland 1988 / Marshall 1990）。误分类可为非差异（单"
          "一矩阵），也可为**差异性**（differential=True + 每个条件层一个矩阵，"
          "differential_by 指定差异轴：结局侧按暴露臂=detection bias 或按**协变量"
          "分层**（differential_by=<协变量>），暴露侧按结局层=recall bias 或按**"
          "协变量分层**（differential_by=<协变量>，误分类率随测量地点/年龄而异）；"
          "差异误分类可朝远离零方向偏，故须逐层求逆，池化单矩阵会做错）；两种都由 "
          "verify_measurement_correction_numeric / "
          "verify_exposure_measurement_correction_numeric 独立重算校正值。若被误测"
          "的是**连续暴露或连续混杂**且有已知的经典加性误差方差 σ²_u（验证研究 / "
          "重复测量），数值层可经 estimate(..., "
          "measurement_error={{<变量名>: {{error_variance}}}}) 用 regression "
          "calibration 的矩量校正 β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive 去偏（Carroll "
          "2006；误测暴露=回归稀释向零衰减，单暴露即 βx=b_naive/λ，"
          "λ=1−σ²_u/Var(W|Z) 是连续版 det(M)；误测混杂=对噪声代理调整留下的残差混"
          "淆偏倚，可朝任意方向，由整条矩阵求逆去偏无标量捷径），由 "
          "verify_regression_calibration_numeric 独立重导。被误测的若是**连续结局"
          "**则另当别论：经典加性误差 Y=Y*+V 不改变任何条件均值，点估计无偏、无可"
          "校正；同一入口 measurement_error={{<结局名>: {{error_variance}}}} 给出"
          "的是代价——残差方差按 Var(Y|D)=Var(Y*|D)+σ²_v 分解，区间比结局测准时宽 "
          "√(Var(Y|D)/Var(Y*|D)) 倍，这部分靠加样本量消不掉、只能靠把结局测准（由 "
          "verify_outcome_error 独立重导）。",
    "en": "measurement-error risk: a variable on the identification route "
          "declares a noisy way of measuring it — {variables}. The classical "
          "references: MacMahon 1990 Lancet, where a single clinic BP reading "
          "attenuates the BP→CHD slope toward 0 by about 60% through "
          "within-person variation (regression dilution); Hernán & Robins "
          "*What If* §9, where non-differential misclassification of a "
          "self-reported or questionnaire exposure likewise pulls the "
          "estimate below the true effect; Fuller 1987 *Measurement Error "
          "Models* for the formal attenuation theorem. The structural layer "
          "only identifies and diagnoses gaps — but where a misclassified "
          "**discrete outcome** or **binary exposure** has a confusion matrix "
          "from a validation study, the numeric layer can undo the "
          "attenuation (estimate(..., misclassification={{<outcome or "
          "exposure name>: {{confusion_matrix, states}}}})), inverting the "
          "matrix within each back-door stratum — on the outcome side "
          "p_true=M⁻¹p_obs (Rogan-Gladen 1978 in the binary case), on the "
          "exposure side by the matrix method, inverting the joint (X,Y) "
          "along the exposure axis one outcome column at a time (Barron 1977 "
          "/ Greenland 1988 / Marshall 1990). Misclassification may be "
          "non-differential (one matrix) or **differential** "
          "(differential=True plus one matrix per stratum, with "
          "differential_by naming the axis: on the outcome side by exposure "
          "arm = detection bias, or **by covariate stratum** "
          "(differential_by=<covariate>); on the exposure side by outcome "
          "level = recall bias, or **by covariate stratum** "
          "(differential_by=<covariate>, where the rates vary with site or "
          "age). Differential misclassification can bias away from the null, "
          "which is why each stratum has to be inverted on its own and "
          "pooling into one matrix gets it wrong.) Either way, "
          "verify_measurement_correction_numeric / "
          "verify_exposure_measurement_correction_numeric recompute the "
          "correction independently. Where what is mismeasured is a "
          "**continuous exposure or continuous confounder** with a known "
          "classical additive error variance σ²_u (validation study, repeat "
          "measurements), the numeric layer can debias through "
          "estimate(..., measurement_error={{<variable>: "
          "{{error_variance}}}}) with regression calibration's method of "
          "moments, β_true=(Σ_obs−E)⁻¹Σ_obs·b_naive (Carroll 2006; a "
          "mismeasured exposure attenuates toward zero, and with a single "
          "exposure that is βx=b_naive/λ, where λ=1−σ²_u/Var(W|Z) is the "
          "continuous counterpart of det(M); a mismeasured confounder leaves "
          "residual confounding after adjusting on the noisy proxy, which can "
          "go either way and has no scalar shortcut — the whole matrix "
          "inversion is what debiases it), and "
          "verify_regression_calibration_numeric re-derives it. A mismeasured "
          "**continuous outcome** is a different case: classical additive "
          "error Y=Y*+V moves no conditional mean, so the point estimate is "
          "unbiased and there is nothing to correct; what the same entry "
          "point measurement_error={{<outcome>: {{error_variance}}}} gives is "
          "the cost — the residual variance splits as "
          "Var(Y|D)=Var(Y*|D)+σ²_v, and the interval is "
          "√(Var(Y|D)/Var(Y*|D)) times wider than it would be with the "
          "outcome measured correctly. That part cannot be bought back with "
          "sample size; only measuring the outcome better removes it "
          "(verify_outcome_error re-derives this).",
}
_MEASUREMENT_ERROR_IF_PROVIDED: language.Words = {
    "zh": "若拿到 (a) 被误分类离散结局**或二值暴露**的**验证过混淆矩阵**（Se/Sp "
          "或整张 confusion matrix），可经 estimate(misclassification=...) 逐后门"
          "层矩阵求逆去衰减；或 (b) 连续暴露**或连续混杂**的已知经典加性误差方差 "
          "σ²_u（重复测量 test-retest / 验证子样本），可经 "
          "estimate(measurement_error={{<暴露或混杂名>: {{error_variance}}}}) 用 "
          "regression calibration 去偏（误测混杂纠正残差混淆；非线性结局的 SIMEX "
          "仍推迟）；连续结局的 σ²_v 同一入口给出的是精度代价而非校正，因为它本就"
          "不偏；或 (c) gold-standard 亚样本（如 BP 用 ABPM、sodium 用 24h 尿钠）"
          "做校准",
    "en": "given (a) a **validated confusion matrix** for the misclassified "
          "discrete outcome **or binary exposure** (Se/Sp, or the whole "
          "matrix), the attenuation can be undone through "
          "estimate(misclassification=...), inverting within each back-door "
          "stratum; or (b) a known classical additive error variance σ²_u for "
          "a continuous exposure **or continuous confounder** (test-retest "
          "repeats, a validation subsample), which debiases through "
          "estimate(measurement_error={{<exposure or confounder>: "
          "{{error_variance}}}}) with regression calibration (a mismeasured "
          "confounder has its residual confounding corrected; SIMEX for "
          "non-linear outcomes is still deferred) — for a continuous outcome "
          "the same entry point gives the precision cost rather than a "
          "correction, because there is no bias to correct; or (c) a "
          "gold-standard subsample to calibrate against (ABPM for blood "
          "pressure, 24-hour urinary sodium for salt)",
}
_STEP_USE_EXPERIMENTAL_DATA: language.Words = {
    "zh": "用 RCT / 实验性分配数据（消除自报告偏差）替代观察性主样本",
    "en": "replace the observational main sample with randomized or "
          "experimentally assigned data, which removes the self-report bias",
}
_STEP_RELIABILITY_RETEST: language.Words = {
    "zh": "对涉及变量做 reliability 重测，按 Carroll et al 2006 *Measurement "
          "Error in Nonlinear Models* 校准",
    "en": "run a reliability retest on the variables involved and calibrate "
          "as in Carroll et al 2006 *Measurement Error in Nonlinear Models*",
}
_STEP_REPORT_ATTENUATION_RANGE: language.Words = {
    "zh": "在敏感性分析中报告 attenuation factor 范围（Rosner et al 1989 "
          "regression calibration upper bound）",
    "en": "report a range for the attenuation factor in the sensitivity "
          "analysis (the regression-calibration upper bound of Rosner et al "
          "1989)",
}


def _classify_measurement_error_concern(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
    lang: language.Lang | str,
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
        ambiguities = extensions.get(blocks.Block.AMBIGUITIES) or ()
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
            role = refusals.QueryRole.EXPOSURE
        elif pred == target_pred:
            role = refusals.QueryRole.OUTCOME
        else:
            role = refusals.QueryRole.ON_PATH_COVARIATE
        return refusals.QueryRole.said(role, lang)

    var_summary = ", ".join(
        language.fill(_NOISY_MEASURE_SUMMARY, lang, variable=pred,
                      role=_role(pred), field=field, phrase=needle)
        for pred, field, needle in flagged
    )
    yield DataGap(
        kind=GapKind.MEASUREMENT_ERROR_CONCERN,
        severity=GapSeverity.IMPORTANT,
        description=language.fill(_MEASUREMENT_ERROR_RISK, lang,
                                  variables=var_summary),
        blocks=GapBlocks.IDENTIFICATION,
        if_provided=language.fill(_MEASUREMENT_ERROR_IF_PROVIDED, lang),
        alternative_paths=(
            language.fill(_STEP_USE_EXPERIMENTAL_DATA, lang),
            language.fill(_STEP_RELIABILITY_RETEST, lang),
            language.fill(_STEP_REPORT_ATTENUATION_RANGE, lang),
        ),
        provenance=tuple(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=f"program:variable:{pred}:{field}:contains:{needle}",
            )
            for pred, field, needle in flagged
        ),
    )


_DICHOTOMIZED: language.Words = {
    "zh": "二分化（dichotomization）：识别路径上有连续测量被在某个 cutpoint 切成"
          "二值 — {variables}。把连续量在阈值处二分会（1）丢失 dose-response 信"
          "息、降低统计效率（Royston, Altman & Sauerbrei 2006 *Stat Med* "
          "25:127 “Dichotomizing continuous predictors in multiple "
          "regression: a bad idea”）；（2）结果对切点敏感，数据驱动的“最优切"
          "点”搜索还会抬高假阳性（Altman et al 1994 *JNCI* 86:829）；（3）若被"
          "二分的是 confounder，类内残余混杂使调整不充分（Becher 1992 *Stat "
          "Med* 11:1747）。Themis 支持把变量保留为连续并做 dose-response 估计"
          "（Phase 13/14）。",
    "en": "dichotomization: a continuous measurement on the identification "
          "route was cut into two at some cutpoint — {variables}. Splitting a "
          "continuous quantity at a threshold (1) throws away the "
          "dose-response information and costs statistical efficiency "
          "(Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127 “Dichotomizing "
          "continuous predictors in multiple regression: a bad idea”); (2) "
          "makes the result sensitive to the cutpoint, and a data-driven "
          "search for the “optimal” one inflates false positives on top of "
          "that (Altman et al 1994 *JNCI* 86:829); (3) leaves "
          "within-category residual confounding, so the adjustment is "
          "incomplete, when what was dichotomized is a confounder (Becher "
          "1992 *Stat Med* 11:1747). Themis can keep the variable continuous "
          "and estimate the dose-response instead (Phase 13/14).",
}
_DICHOTOMIZED_IF_PROVIDED: language.Words = {
    "zh": "若能拿到未二分的连续原始测量，可改走 dose-response 估计（LinearDML / "
          "DRLearner，Themis Phase 13/14），保留剂量-反应曲线并避免任意切点",
    "en": "given the original continuous measurement before it was cut, the "
          "dose-response route is available instead (LinearDML / DRLearner, "
          "Themis Phase 13/14), which keeps the dose-response curve and needs "
          "no arbitrary cutpoint",
}
_STEP_KEEP_CONTINUOUS: language.Words = {
    "zh": "保留连续变量，用 dose-response 估计代替二分（Themis Phase 13/14）",
    "en": "keep the variable continuous and estimate the dose-response "
          "instead of dichotomizing (Themis Phase 13/14)",
}
_STEP_CUTPOINT_SENSITIVITY: language.Words = {
    "zh": "若必须二分，报告对 cutpoint 的敏感性分析（多个切点下结论是否稳定）",
    "en": "if it has to be dichotomized, report a sensitivity analysis over "
          "the cutpoint (does the conclusion hold at several of them)",
}
_STEP_FINER_STRATA: language.Words = {
    "zh": "对被二分的 confounder，改用更细分层或样条以减少类内残余混杂（Becher "
          "1992）",
    "en": "for a dichotomized confounder, use finer strata or a spline to cut "
          "the within-category residual confounding (Becher 1992)",
}


def _classify_dichotomized_continuous_measure(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
    lang: language.Lang | str,
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
        for amb in extensions.get(blocks.Block.AMBIGUITIES) or ():
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
        description=language.fill(_DICHOTOMIZED, lang,
                                  variables=var_summary),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=language.fill(_DICHOTOMIZED_IF_PROVIDED, lang),
        alternative_paths=(
            language.fill(_STEP_KEEP_CONTINUOUS, lang),
            language.fill(_STEP_CUTPOINT_SENSITIVITY, lang),
            language.fill(_STEP_FINER_STRATA, lang),
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


_TIAN_FOUND_A_HEDGE: language.Words = {
    "zh": "识别失败：Tian 算法在 An(Y) 子图上找到 c-component hedge —— X 与 Y "
          "处于同一 c-component，说明它们之间存在未被任何观测变量遮断的潜在共同"
          "原因 / 双向耦合，P(Y | do(X)) 在该 ADMG 下不可从观测分布识别",
    "en": "identification failed: Tian's algorithm found a c-component hedge "
          "on the An(Y) subgraph — X and Y sit in the same c-component, which "
          "says there is a latent common cause (or bidirected coupling) "
          "between them that no observed variable screens off, so P(Y | "
          "do(X)) is not identifiable from the observational distribution on "
          "this ADMG",
}
_MEASURE_THE_CONFOUNDER_BREAK_HEDGE: language.Words = {
    "zh": "测量并加入 unmeasured confounder Z，打破 hedge",
    "en": "measure the unmeasured confounder Z, add it, and break the hedge",
}
_RCT_BYPASS_HEDGE: language.Words = {
    "zh": "在 X 上做 RCT (如可行)，旁路 hedge",
    "en": "randomize X if that is feasible, and bypass the hedge",
}


def _classify_unidentifiable(
    derivation: tuple[DerivationStep, ...],
    *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    for step in derivation:
        # Tian Shpitser Line 5. The step SUCCEEDED and that is what makes
        # it the witness: the c-component decomposition it names is the
        # proof of unidentifiability, replayable by the verifier, where
        # the failed step this classifier used to also read for was only
        # an assertion that something had gone wrong.
        if step.rule != "tian_hedge_witness":
            continue
        yield DataGap(
            kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
            severity=GapSeverity.BLOCKING,
            description=language.fill(_TIAN_FOUND_A_HEDGE, lang),
            blocks=GapBlocks.IDENTIFICATION,
            provenance=(_step_ref(step),),
            if_provided=language.fill(_THEN_FORMULA_AND_POINT, lang),
            alternative_paths=(
                language.fill(_MEASURE_THE_CONFOUNDER_BREAK_HEDGE, lang),
                language.fill(_RCT_BYPASS_HEDGE, lang),
                language.fill(_FIND_IV_ADVICE, lang),
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


class _SpeciesRenderer(Protocol):
    """What a species' renderer is called with.

    A protocol rather than a ``Callable[...]``, because the reader's
    language arrives by keyword and a ``Callable`` cannot say so — it can
    only describe positions.
    """

    def __call__(
        self, item: InvestigationItem, query_kind: QueryKind,
        *, lang: language.Lang | str,
    ) -> Iterable[DataGap]: ...


#: A species is either rendered here, or declared as raised elsewhere.
_Renderer = _SpeciesRenderer | _RaisedElsewhere


_SPECIES_UNIDENTIFIED: language.Words = {
    "zh": "识别路径失败：{why}",
    "en": "the identification route failed: {why}",
}
_THEN_FORMULA_AND_POINT: language.Words = {
    "zh": "可给出识别公式 + 后续点估计",
    "en": "an identification formula, and a point estimate after it",
}
_MEASURE_THE_CONFOUNDER_REIDENTIFY: language.Words = {
    "zh": "测量并加入 unmeasured confounder Z，重新识别",
    "en": "measure the unmeasured confounder Z, add it, and identify again",
}
_RCT_BYPASS_BACKDOOR: language.Words = {
    "zh": "在 X 上做 RCT (如可行)，旁路 backdoor",
    "en": "randomize X if that is feasible, and bypass the back-door",
}


def _species_unidentifiable(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """The estimand asked for is not point identified from this graph and
    these data. Distinct from a defect in the program — this is the gap
    ``_compute_answer_tier`` reads to decide no point estimand is in
    hand, so a mediator declared off the causal path or a query atom
    absent from V must not land here."""
    yield DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        severity=GapSeverity.BLOCKING,
        description=language.fill(_SPECIES_UNIDENTIFIED, lang,
                                  why=gaps.said(item, lang) or item.target),
        blocks=GapBlocks.IDENTIFICATION,
        if_provided=language.fill(_THEN_FORMULA_AND_POINT, lang),
        alternative_paths=(
            language.fill(_MEASURE_THE_CONFOUNDER_REIDENTIFY, lang),
            language.fill(_RCT_BYPASS_BACKDOOR, lang),
            language.fill(_FIND_IV_ADVICE, lang),
        ),
        provenance=(_item_ref(item),),
    )


_SPECIES_STRUCTURAL_INPUT: language.Words = {
    "zh": "缺结构输入：{why}", "en": "a structural input is missing: {why}",
}
_THEN_CONTINUE_TO_POINT: language.Words = {
    "zh": "该查询可继续走到点估计",
    "en": "this query can carry on to a point estimate",
}


def _species_structural_input(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
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
        description=language.fill(_SPECIES_STRUCTURAL_INPUT, lang,
                                  why=gaps.said(item, lang) or item.target),
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided=language.fill(_THEN_CONTINUE_TO_POINT, lang),
        provenance=(_item_ref(item),),
    )


_SPECIES_UNIT_OBSERVATION: language.Words = {
    "zh": "缺该单位的观测值：{why}",
    "en": "this unit's observed values are missing: {why}",
}


def _species_unit_observation(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """A unit-level value the query needs and the program did not
    observe. Not a ``missing_distribution``: abduction in a
    deterministic SCM counterfactual recovers this unit's exogenous term
    from its own measured values, so what is wanted is a reading for
    this unit and no amount of population data substitutes."""
    yield DataGap(
        kind=GapKind.MISSING_UNIT_OBSERVATION,
        severity=GapSeverity.BLOCKING,
        description=language.fill(_SPECIES_UNIT_OBSERVATION, lang,
                                  why=gaps.said(item, lang) or item.target),
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided=language.fill(_THEN_CONTINUE_TO_POINT, lang),
        provenance=(_item_ref(item),),
    )


_SPECIES_MISSING_DISTRIBUTION: language.Words = {
    "zh": "缺概率分布 {what}", "en": "the distribution {what} is missing",
}
_COLLECT_NO_INTERVAL_FALLBACK: language.Words = {
    "zh": "直接收集 {what} 的数据 —— 该问法没有区间退路，拿不到点估计就没有数",
    "en": "collect data for {what} directly — this question has no interval "
          "to fall back on, so without the point estimate there is no number "
          "at all",
}
_THEN_A_POINT: language.Words = {"zh": "可给点估计", "en": "a point estimate"}


def _species_missing_distribution(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
) -> Iterable[DataGap]:
    """A probability the evaluator looked for and theta does not hold."""
    display = _strip_parameter_prefix(item.target)
    signature = _distribution_signature(display)
    min_n, precision = _estimate_sample_size_for_distribution(
        display, signature,
    )
    offer = _interval_offer(query_kind, lang=lang)
    if offer is not None:
        # A magic token that scheduler._reconcile_alt_paths_with_bounds
        # rewrites to whichever procedure produced the actual
        # bounds_results, and strips when the attempt returned nothing.
        alt_paths = (offer,)
    else:
        # No interval channel for this question, so "accept bounds
        # instead" would be a promise nothing can keep. Said once and
        # generally: the sentence that lived here explained why an
        # observational conditional is point-estimable, and was read by
        # 222 causation gaps whose answer is an interval.
        alt_paths = (
            language.fill(_COLLECT_NO_INTERVAL_FALLBACK, lang, what=display),
        )
    yield DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description=language.fill(_SPECIES_MISSING_DISTRIBUTION, lang,
                                  what=display),
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
        if_provided=language.fill(_THEN_A_POINT, lang),
        alternative_paths=alt_paths,
        provenance=(_item_ref(item),),
    )


_SPECIES_THETA_GRAPH_MISMATCH: language.Words = {
    "zh": "声明的图与提供的 CPT 不一致：缺 {what}，但 theta 中存在的边缘量被 "
          "d-separation 拒绝（图蕴含的独立性不成立）",
    "en": "the declared graph and the CPTs supplied disagree: {what} is "
          "missing, and a marginal that theta does carry is refused by "
          "d-separation (an independence the graph implies does not hold)",
}
_THEN_A_POINT_ONCE_RESOLVED: language.Words = {
    "zh": "可给点估计（在解决图与 CPT 矛盾后）",
    "en": "a point estimate, once the graph and the CPTs stop contradicting "
          "each other",
}
_SUPPLY_THE_CONDITIONAL: language.Words = {
    "zh": "补充所缺的条件量 {what}（接受图）",
    "en": "supply the conditional {what} that is missing (and keep the graph)",
}
_OR_DROP_THE_EDGE: language.Words = {
    "zh": "或：删除引发独立性矛盾的边（改图，承认现有 CPT 已是真分布）",
    "en": "or: drop the edge that causes the contradiction (change the graph, "
          "and take the CPTs as the true distribution)",
}


def _species_theta_graph_mismatch(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
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
        description=language.fill(_SPECIES_THETA_GRAPH_MISMATCH, lang,
                                  what=display),
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided=language.fill(_THEN_A_POINT_ONCE_RESOLVED, lang),
        alternative_paths=(
            language.fill(_SUPPLY_THE_CONDITIONAL, lang, what=display),
            language.fill(_OR_DROP_THE_EDGE, lang),
        ) + tuple(o for o in (_interval_offer(query_kind, lang=lang),)
                  if o is not None),
        provenance=(_item_ref(item),),
    )


_SPECIES_MISSING_ASSUMPTION: language.Words = {
    "zh": "识别前提待补充或修正：{why}",
    "en": "an identification premise has to be supplied or corrected: {why}",
}
_THEN_ROUTE_CONTINUES: language.Words = {
    "zh": "该识别路径可继续走到点估计",
    "en": "this identification route can carry on to a point estimate",
}


def _species_missing_assumption(
    item: InvestigationItem, query_kind: QueryKind,
    *, lang: language.Lang | str,
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
        description=language.fill(_SPECIES_MISSING_ASSUMPTION, lang,
                                  why=gaps.said(item, lang) or item.target),
        blocks=GapBlocks.POINT_ESTIMATE,
        if_provided=language.fill(_THEN_ROUTE_CONTINUES, lang),
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
    *,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Every investigation item, rendered as the species it declares."""
    for req in requests:
        for item in req.items:
            render = _ITEM_SPECIES[item.gap]
            if isinstance(render, _RaisedElsewhere):
                continue
            yield from render(item, query_kind, lang=lang)


# Kinds nothing in this tree can construct, and why each slot is open.
# Declared rather than deleted from the enum, because the schema, the KB
# translator, the browser's table and the verifier's registry all carry
# them already: a slot that says why it is empty is checkable, and a
# silent empty slot is indistinguishable from a producer somebody forgot
# to wire.
#
# ``tests/test_no_step_the_kernel_wrote_says_it_failed.py`` holds this
# table to a census of the tree. Note which direction that census proves.
# Zero construction sites IS a proof that nothing constructs the kind. One
# or more sites is NOT a proof that anything reaches one — the IV entry
# below had a classifier of its own for as long as it was unreachable,
# which is how it came to be here: the classifier read for a failed
# derivation step, and the kernel stopped writing those.
GAP_KINDS_WITH_NO_PRODUCER: dict[GapKind, str] = {
    GapKind.MISSING_POPULATION_DISTRIBUTION: (
        "multi-source transport (§T9.2 / §T9.3) does not exist in the "
        "kernel, so no block can carry the signal that raises it"
    ),
    GapKind.MISSING_IV_CANDIDATE: (
        "the only signal that raised it was a failed IV derivation step, "
        "which no producer writes; and it is not in MISSING_ITEM_GAPS, so "
        "no investigation item may declare it either. A producer that "
        "wants one adds the species to that vocabulary and binds a "
        "renderer for it"
    ),
}


_MEDIATOR_DATA_NEEDED: language.Words = {
    "zh": "中介分解需要 {mediator} 相关分布：{target}",
    "en": "the mediation decomposition needs {mediator}'s distributions: "
          "{target}",
}
_MEDIATOR_THEN_A_DECOMPOSITION: language.Words = {
    "zh": "可给 NDE / NIE / TE 数值分解",
    "en": "a numeric NDE / NIE / TE decomposition",
}
_MEDIATOR_FALL_BACK_TO_CDE: language.Words = {
    "zh": "回退到 CDE（控制中介，给条件直接效应）",
    "en": "fall back to the CDE (hold the mediator fixed, and take the "
          "controlled direct effect)",
}
_MEDIATOR_FALL_BACK_TO_TOTAL: language.Words = {
    "zh": "退回 total effect，不分解",
    "en": "fall back to the total effect, undecomposed",
}


def _classify_missing_mediator(
    extensions: dict,
    requests: tuple[InvestigationRequest, ...],
    *,
    lang: language.Lang | str,
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
                description=language.fill(
                    _MEDIATOR_DATA_NEEDED, lang,
                    mediator=mediator, target=item.target,
                ),
                blocks=GapBlocks.POINT_ESTIMATE,
                required_data=GapRequiredData(
                    data_type=RequiredDataType.IPD,
                    variables=touched,
                    min_sample_size=min_n,
                    precision_target=precision,
                ),
                if_provided=language.fill(
                    _MEDIATOR_THEN_A_DECOMPOSITION, lang),
                alternative_paths=(
                    language.fill(_MEDIATOR_FALL_BACK_TO_CDE, lang),
                    language.fill(_MEDIATOR_FALL_BACK_TO_TOTAL, lang),
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )


#: What a population is called where the block did not name it. One word
#: for both sides: which population it stands for is said by the sentence
#: it sits in, not by the placeholder.
_POPULATION_UNNAMED: language.Words = {"zh": "<未命名>", "en": "<unnamed>"}
_TRANSPORT_TARGET_MARGINAL: language.Words = {
    "zh": "转移公式已识别，但目标人群 {population} 在 {{{variables}}} 上的分布 "
          "P*(Z) 未提供",
    "en": "the transport formula is identified, but the distribution P*(Z) "
          "of the target population {population} over {{{variables}}} was "
          "not supplied",
}
_TRANSPORT_SOURCE_CONDITIONAL: language.Words = {
    "zh": "转移公式还需要源人群 {population} 的分层条件分布 {formula}"
          "（meta-analysis 通常只汇总成一个数，不给分层）",
    "en": "the transport formula also needs the stratified conditional "
          "{formula} on the source population {population} (a meta-analysis "
          "usually pools to one number and publishes no strata)",
}
_TRANSPORT_THEN_A_POINT: language.Words = {
    "zh": "可给目标人群的 transport-adjusted ATE 点估计",
    "en": "a transport-adjusted ATE point estimate for the target population",
}
_TRANSPORT_ACCEPT_SOURCE_ATE: language.Words = {
    "zh": "接受源人群 ATE 作为粗略估计（外推有效性弱）",
    "en": "take the source population's ATE as a rough estimate (the "
          "extrapolation rests on little)",
}
_TRANSPORT_FIND_IPD: language.Words = {
    "zh": "找原始 RCT IPD（联系作者 / 看附件 supplementary table）",
    "en": "find the original RCT's individual participant data (write to the "
          "authors, or check the supplementary tables)",
}
_TRANSPORT_FIND_SUBGROUPS: language.Words = {
    "zh": "找 meta-analysis 的 subgroup analysis（按 age / sex / BMI 分层）",
    "en": "find the meta-analysis's subgroup analysis (stratified by age / "
          "sex / BMI)",
}
_TRANSPORT_FIND_A_MATCHED_RCT: language.Words = {
    "zh": "退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价",
    "en": "failing that: find the one small RCT closest to your subgroup, and "
          "pay for it in sample size",
}


def _classify_transport_target_distribution(
    extensions: dict, *, lang: language.Lang | str,
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
    block = extensions.get(blocks.Block.TRANSPORT_IDENTIFICATION)
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
        description=language.fill(
            _TRANSPORT_TARGET_MARGINAL, lang,
            population=(target_pop
                        or language.fill(_POPULATION_UNNAMED, lang)),
            variables=z_names,
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.MARGINAL,
            population=target_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=target_n,
            precision_target=target_precision,
        ),
        if_provided=language.fill(_TRANSPORT_THEN_A_POINT, lang),
        alternative_paths=(
            language.fill(_TRANSPORT_ACCEPT_SOURCE_ATE, lang),
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
        description=language.fill(
            _TRANSPORT_SOURCE_CONDITIONAL, lang,
            population=(source_pop
                        or language.fill(_POPULATION_UNNAMED, lang)),
            formula=formula_repr,
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population=source_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=source_n,
            precision_target=source_precision,
        ),
        if_provided=language.fill(_TRANSPORT_THEN_A_POINT, lang),
        alternative_paths=(
            language.fill(_TRANSPORT_FIND_IPD, lang),
            language.fill(_TRANSPORT_FIND_SUBGROUPS, lang),
            language.fill(_TRANSPORT_FIND_A_MATCHED_RCT, lang),
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


_DOSE_RESPONSE_SPEC: language.Words = {
    "zh": "用户问的是 {intervention} 与 {target} 之间的剂量响应关系（曲线 / 关系"
          "图）。Themis 不算曲线（请用 EconML / DoubleML / GAM）—— 但下面是你做"
          "这件事所需的数据规格。{hint}",
    "en": "the question asks for the dose-response relationship between "
          "{intervention} and {target} (a curve, a plot). Themis does not fit "
          "curves — use EconML / DoubleML / GAM — but here is the data "
          "specification doing so would take.{hint}",
}
_DOSE_RESPONSE_NO_CONFOUNDER_HINT: language.Words = {
    "zh": "（注：你的 DAG 仅声明了 intervention + target 两个节点，没有任何 "
          "confounder。观察性剂量响应分析典型需要在 DAG 里至少声明 baseline "
          "outcome 与关键 demographic covariates；若你确实想保持 minimal DAG"
          "（如随机化 RCT 设计），可以忽略此提示。）",
    "en": "(Note: your DAG declares only the intervention and the target, "
          "with no confounder at all. An observational dose-response analysis "
          "usually needs at least the baseline outcome and the key "
          "demographic covariates declared in the DAG; if you do mean to keep "
          "the DAG minimal — a randomized design, say — you can ignore "
          "this.)",
}
_DOSE_PRECISION: language.Words = {
    "zh": "K={points} 个 X 采样点 × n={per_point}/点 (Cohen's d=0.5, α=0.05, "
          "power=0.80)",
    "en": "K={points} sampling points in X × n={per_point} each (Cohen's "
          "d=0.5, α=0.05, power=0.80)",
}
_DOSE_TIME_WINDOW: language.Words = {
    "zh": "建议 baseline + 4w + 12w（视实际研究问题调整）",
    "en": "baseline + 4w + 12w is a reasonable start (adjust to the actual "
          "research question)",
}
_DOSE_SUTVA_NO_COORDINATION: language.Words = {
    "zh": "受试者之间不能讨论 / 协调干预（违反 SUTVA）",
    "en": "subjects must not discuss or coordinate the intervention between "
          "themselves (that violates SUTVA)",
}
_DOSE_SUTVA_SPILLOVER: language.Words = {
    "zh": "若有溢出 / 同侪效应，需登记并在分析中纳入",
    "en": "where spillover or peer effects exist, record them and carry them "
          "into the analysis",
}
_DOSE_IF_PROVIDED: language.Words = {
    "zh": "数据齐了之后，去 EconML / DoubleML / GAM 拟合曲线 —— Themis 不在 "
          "estimator 这一步参与",
    "en": "once the data is complete, fit the curve in EconML / DoubleML / "
          "GAM — Themis takes no part in that step",
}
_DOSE_FALL_BACK_TO_BINARY: language.Words = {
    "zh": "退一步只看二元对比 (X=high vs X=low)：Themis 能给区间答案",
    "en": "step back to the binary contrast (X=high vs X=low), which Themis "
          "can answer with an interval",
}


def _classify_dose_response_data(
    program, stmt, derivation: tuple[DerivationStep, ...],
    *, lang: language.Lang | str,
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
    target_label = _query_target_label(stmt, lang=lang)
    intervention_label = _query_intervention_label(stmt, lang=lang)

    # If confounders_required is empty AND the
    # user's program has no extra-variable nodes beyond X / Y, the DAG is
    # bare X→Y. This is unusual for observational dose-response work
    # (Whelton 2002 / AHA 2013 / Cornelissen 2013 all flag baseline
    # outcome + demographic covariates as standard). Append a generic
    # hint so the renderer prompts the user to confirm minimality is
    # intentional. Avoids hardcoding domain-specific covariate names.
    extra_hint = ""
    if not confounders and _program_has_no_declared_confounders(program, stmt):
        extra_hint = language.fill(_DOSE_RESPONSE_NO_CONFOUNDER_HINT, lang)

    yield DataGap(
        kind=GapKind.DOSE_RESPONSE_DATA_REQUIRED,
        severity=GapSeverity.BLOCKING,
        description=language.fill(
            _DOSE_RESPONSE_SPEC, lang,
            intervention=intervention_label, target=target_label,
            hint=extra_hint,
        ),
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            sampling_point_count=K,
            min_sample_size=total,
            precision_target=language.fill(
                _DOSE_PRECISION, lang, points=K, per_point=n_per_point,
            ),
            confounders_required=tuple(confounders),
            time_window=language.fill(_DOSE_TIME_WINDOW, lang),
            sutva_concerns=(
                language.fill(_DOSE_SUTVA_NO_COORDINATION, lang),
                language.fill(_DOSE_SUTVA_SPILLOVER, lang),
            ),
        ),
        if_provided=language.fill(_DOSE_IF_PROVIDED, lang),
        alternative_paths=(
            language.fill(_DOSE_FALL_BACK_TO_BINARY, lang),
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="program:extensions.ambiguities.dose_response_query",
            ),
        ),
    )


_COLLIDER_IN_GIVEN: language.Words = {
    "zh": "`given` 中的条件节点 `{collider}` 是 collider —— 在 "
          "`{intervention}` 与 `{target}` 之间存在一条以 `{collider}` 为对撞点的"
          "路径（两条臂可经潜在/双向边，即 M-bias）。Pearl d-separation：在 "
          "collider（或其后代）上做条件会**打开**这条非因果路径而不是阻断它，给"
          "最终估计引入 collider-induced bias / selection bias。当前返回的不是 "
          "\"在 `{collider}` 子群上的因果效应\"，而是被打开的非因果路径污染过"
          "的混合量。",
    "en": "the conditioning node `{collider}` in `given` is a collider — "
          "between `{intervention}` and `{target}` there is a path that "
          "collides at `{collider}` (either arm may run through a latent or "
          "bidirected edge, which is M-bias). Pearl's d-separation: "
          "conditioning on a collider (or on its descendant) **opens** that "
          "non-causal path rather than blocking it, and puts "
          "collider-induced bias / selection bias into the estimate. What "
          "comes back is not \"the causal effect within the `{collider}` "
          "subgroup\" but a mixture contaminated by the path that was "
          "opened.",
}
_COLLIDER_DROP_FROM_GIVEN: language.Words = {
    "zh": "从 `given` 移除 `{collider}` —— 如果你真的想问 \"在 `{collider}` 子"
          "群上的效应\"，需要单独的 transport / stratified analysis（先分层再估"
          "计），不能直接做条件查询",
    "en": "drop `{collider}` from `given` — if the effect **within the "
          "`{collider}` subgroup** is really the question, it needs a "
          "transport or a stratified analysis of its own (stratify first, "
          "estimate second) rather than a conditional query",
}
_COLLIDER_ASK_MARGINAL: language.Words = {
    "zh": "不做这个条件，问 marginal 效应 P({target} | do({intervention}))",
    "en": "drop the condition and ask for the marginal effect P({target} | "
          "do({intervention}))",
}
_COLLIDER_MAYBE_NOT_ONE: language.Words = {
    "zh": "如果 `{collider}` 不是真 collider（即只有 X 或只有 Y 是祖先），更新 "
          "DAG 把缺失的因果方向加进去 — 当前结构性结论会变",
    "en": "if `{collider}` is not really a collider (only X or only Y is an "
          "ancestor), update the DAG with the causal direction that is "
          "missing — the structural conclusion will change",
}
_COLLIDER_USE_TRANSPORT: language.Words = {
    "zh": "用 transport identification 路径处理 \"target population "
          "restricted by {collider}\" 而不是用 `given` 字段",
    "en": "handle \"target population restricted by {collider}\" through "
          "the transport identification route rather than through the "
          "`given` field",
}


def _classify_collider_conditioning_opens_backdoor(
    *,
    program,
    stmt,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Selection bias, the explicit-conditioning shape.

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
                description=language.fill(
                    _COLLIDER_IN_GIVEN, lang, collider=w_pred,
                    intervention=intervention_pred, target=target_pred,
                ),
                blocks=GapBlocks.IDENTIFICATION,
                if_provided=language.fill(
                    _COLLIDER_DROP_FROM_GIVEN, lang, collider=w_pred,
                ),
                alternative_paths=(
                    language.fill(_COLLIDER_ASK_MARGINAL, lang,
                                  target=target_pred,
                                  intervention=intervention_pred),
                    language.fill(_COLLIDER_MAYBE_NOT_ONE, lang,
                                  collider=w_pred),
                    language.fill(_COLLIDER_USE_TRANSPORT, lang,
                                  collider=w_pred),
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


_SELECTED_ON_COLLIDER: language.Words = {
    "zh": "样本被结构性限制为 `{collider}={value}` 的受试者（program 里有 "
          "ObservationStatement 编码了这个限制），但声明的 DAG 里 "
          "`{intervention}` 和 `{target}` 都是 `{collider}` 的祖先 —— "
          "`{collider}` 是 collider。Pearl d-separation：用『仅 "
          "{collider}={value} 的子样本』估计 P({target} | do({intervention})) "
          "等于在 collider 上做条件，会**打开** "
          "`{intervention}→...→{collider}←...←{target}` 这条非因果路径，给估计引"
          "入 selection-induced bias。Hernán-Hernández-Díaz-Robins 2004 "
          "*Epidemiology* 15:615 \"A Structural Approach to Selection "
          "Bias\" 的标准结构。",
    "en": "the sample is structurally restricted to subjects with "
          "`{collider}={value}` (an ObservationStatement in the program "
          "encodes that restriction), and in the declared DAG both "
          "`{intervention}` and `{target}` are ancestors of `{collider}` — so "
          "`{collider}` is a collider. Pearl's d-separation: estimating "
          "P({target} | do({intervention})) from the {collider}={value} "
          "subsample alone is conditioning on a collider, and it **opens** "
          "the non-causal path "
          "`{intervention}→...→{collider}←...←{target}`, putting "
          "selection-induced bias into the estimate. This is the standard "
          "structure of Hernán-Hernández-Díaz-Robins 2004 *Epidemiology* "
          "15:615 \"A Structural Approach to Selection Bias\".",
}
_SELECTED_ADD_CONTROLS: language.Words = {
    "zh": "补充未被 `{collider}` 限制的对照样本（覆盖 {collider}=¬{value} 的受试"
          "者），把全样本作为分析对象 —— 而不是只用 `{collider}={value}` 子样本",
    "en": "add the controls that `{collider}` excluded (subjects with "
          "{collider}=¬{value}) and analyse the whole sample rather than the "
          "`{collider}={value}` subsample alone",
}
_SELECTED_REWEIGHT: language.Words = {
    "zh": "用 inverse-probability-of-selection weighting (Hernán et al 2004 "
          "§5)：对每个保留样本按 1/P({collider}={value} | X, Y) 加权重抽以近似全"
          "样本",
    "en": "use inverse-probability-of-selection weighting (Hernán et al 2004 "
          "§5): weight each retained subject by 1/P({collider}={value} | X, "
          "Y) to approximate the whole sample",
}
_SELECTED_MAYBE_NOT_COMMON: language.Words = {
    "zh": "如果 `{collider}` 实际并非由 `{intervention}` 和 `{target}` 共同决"
          "定，更新 DAG 删除其中一条祖先边 —— 当前结构性结论会随之改变",
    "en": "if `{collider}` is not in fact determined by both `{intervention}` "
          "and `{target}`, update the DAG and remove one of those ancestor "
          "edges — the structural conclusion moves with it",
}
_SELECTED_AS_SELECTION_NODE: language.Words = {
    "zh": "用 `selection_node` (Phase 9 §T9.1) 把 `{collider}` 声明为 transport "
          "选择节点而不是观察节点，并通过 transport identification 路径处理跨人群"
          "泛化",
    "en": "declare `{collider}` a transport selection node rather than an "
          "observation node with `selection_node` (Phase 9 §T9.1), and "
          "generalize across populations through the transport identification "
          "route",
}


def _classify_selection_on_collider_opens_path(
    *,
    program,
    stmt,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Selection bias, the implicit-sample-restriction shape.

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
                description=language.fill(
                    _SELECTED_ON_COLLIDER, lang,
                    collider=w_pred, value=w_value,
                    intervention=intervention_pred, target=target_pred,
                ),
                blocks=GapBlocks.IDENTIFICATION,
                if_provided=language.fill(
                    _SELECTED_ADD_CONTROLS, lang,
                    collider=w_pred, value=w_value,
                ),
                alternative_paths=(
                    language.fill(_SELECTED_REWEIGHT, lang,
                                  collider=w_pred, value=w_value),
                    language.fill(_SELECTED_MAYBE_NOT_COMMON, lang,
                                  collider=w_pred,
                                  intervention=intervention_pred,
                                  target=target_pred),
                    language.fill(_SELECTED_AS_SELECTION_NODE, lang,
                                  collider=w_pred),
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


_INTERVENTION_UNDECLARED: language.Words = {
    "zh": "`{intervention}` 出现在 do(.) 位置，但没声明它是**离散事件**还是**持"
          "续状态**（`state_vs_event`），也没给 `time_window` —— 所以这里**还无"
          "法判断**这个干预定义得够不够清楚（缺信息 ≠ 定义不清）。先确认一句："
          "`{intervention}` 是一个**明确的动作 / 事件**（如一次性给药、参加某项"
          "目），还是一个**属性 / 持续状态**（如肥胖、长期保持某行为）？若是前"
          "者，干预本就定义清楚，声明 `state_vs_event=\"event\"` 即可消除本提"
          "示。若是后者，则会落入 Hernán & Taubman 2008 *IJO* 32(S3):S8-S14 "
          "\"Does obesity shorten life?\"（该文以肥胖为例）的 ill-defined "
          "intervention 情形：同一状态值可由多种操纵方式达到、各自反事实不同，"
          "do({intervention}=该状态) 没有唯一定义，consistency 假设（Hernán & "
          "Robins *What If* §3.4）会被违反 —— 这时请加 `time_window`，或在 "
          "extensions.ambiguities opt-in `ill_defined_intervention`。",
    "en": "`{intervention}` appears in a do(.) position, but nothing says "
          "whether it is a **discrete event** or a **sustained state** "
          "(`state_vs_event`), and no `time_window` was given — so **this "
          "cannot yet be judged** one way or the other (missing information "
          "is not the same as an ill-defined intervention). One question "
          "settles it: is `{intervention}` a **definite action or event** (a "
          "single dose, enrolling in a programme), or an **attribute or "
          "sustained state** (obesity, keeping up a behaviour)? If the "
          "former, the intervention is already well defined and declaring "
          "`state_vs_event=\"event\"` clears this notice. If the latter, it "
          "falls into the ill-defined-intervention case of Hernán & Taubman "
          "2008 *IJO* 32(S3):S8-S14 \"Does obesity shorten life?\" (which "
          "uses obesity as its example): one state value is reachable by "
          "several manipulations, each with its own counterfactual, so "
          "do({intervention}=that state) has no single definition and the "
          "consistency assumption (Hernán & Robins *What If* §3.4) is "
          "violated — add a `time_window`, or opt in to "
          "`ill_defined_intervention` under extensions.ambiguities.",
}
_INTERVENTION_STATE_WITHOUT_WINDOW: language.Words = {
    "zh": "intervention 是状态不是事件、且没有指定时间窗：变量 "
          "`{intervention}` 声明了 `state_vs_event=\"state\"`（持久性属性，不"
          "是离散事件），但同一变量没有声明 `time_window`。这是 Hernán & "
          "Taubman 2008 *IJO* 32(S3):S8-S14 \"Does obesity shorten life? The "
          "importance of well-defined interventions to answer causal "
          "questions\" 的经典 ill-defined intervention 结构 —— 同一个 "
          "`{intervention}` 状态值可以由多种结构上不同的操纵方式达到，而这些不同"
          "的操纵会带来**不同**的反事实结果，因此 do({intervention}=state) 没有"
          "唯一定义；consistency assumption（Hernán & Robins *What If* §3.4）被"
          "沉默地违反，返回的 \"effect\" 实际上是多个估计量的混合。Themis 仅"
          "surface 此问题，无法替你选具体的干预定义。",
    "en": "the intervention is a state rather than an event and no time "
          "window was given: the variable `{intervention}` declares "
          "`state_vs_event=\"state\"` (a lasting attribute, not a discrete "
          "event) and declares no `time_window`. This is the classic "
          "ill-defined-intervention structure of Hernán & Taubman 2008 *IJO* "
          "32(S3):S8-S14 \"Does obesity shorten life? The importance of "
          "well-defined interventions to answer causal questions\" — one "
          "`{intervention}` state value is reachable by structurally "
          "different manipulations, those manipulations carry **different** "
          "counterfactuals, and so do({intervention}=state) has no single "
          "definition; the consistency assumption (Hernán & Robins *What If* "
          "§3.4) is violated silently, and the \"effect\" that comes back "
          "is a mixture of several estimands. Themis only surfaces this; it "
          "cannot pick the intervention's definition for you.",
}
_ILL_DEFINED_IF_PROVIDED: language.Words = {
    "zh": "在 `{intervention}` 的 VariableDeclaration 上加 `time_window`（说明 "
          "\"持续多长时间 / 在哪个时点被视为该状态\"），并在 "
          "program.extensions.ambiguities 里加 `ill_defined_intervention` 条"
          "目，说明你打算把哪一种具体的 manipulation（如生活方式 / 用药 / 手术 "
          "/ RCT 随机化）作为 do(.) 的 well-defined intervention 等价物",
    "en": "add a `time_window` to `{intervention}`'s VariableDeclaration "
          "(saying \"for how long / at which point it counts as being in "
          "that state\"), and add an `ill_defined_intervention` entry under "
          "program.extensions.ambiguities naming which concrete manipulation "
          "(lifestyle / medication / surgery / RCT randomization) you mean to "
          "stand in for do(.) as the well-defined intervention",
}
_ILL_DEFINED_MAKE_IT_AN_EVENT: language.Words = {
    "zh": "把 `{intervention}` 重新声明为一个具体的事件类变量"
          "（state_vs_event=\"event\"）—— 一个有明确操纵动作的一次性事件，这样 "
          "do(.) 有明确目标",
    "en": "redeclare `{intervention}` as a concrete event variable "
          "(state_vs_event=\"event\") — a one-off event with a definite "
          "manipulation behind it, so do(.) has something definite to act on",
}
_ILL_DEFINED_SPLIT_IN_TWO: language.Words = {
    "zh": "把 `{intervention}` 拆成两个变量：一个事件类的intervention（具体的操"
          "纵动作）+ 一个由它导致的中间状态，用 mediation 路径处理",
    "en": "split `{intervention}` into two variables: an event-shaped "
          "intervention (the concrete manipulation) and the intermediate "
          "state it causes, and handle it through the mediation route",
}
_ILL_DEFINED_USE_EXPERIMENTAL_DATA: language.Words = {
    "zh": "用 RCT / 实验性数据替代观察性主样本 —— 实验里 do(.) 的\"compared "
          "with what\" 由随机化协议明确定义",
    "en": "replace the observational main sample with RCT or experimental "
          "data — in an experiment the randomization protocol defines what "
          "do(.) is \"compared with what\"",
}
_ILL_DEFINED_OPT_IN: language.Words = {
    "zh": "在 extensions.ambiguities 里以 `ill_defined_intervention` kind 显式"
          "声明本题接受多 intervention 的混合估计量 —— Themis 会停发本警告并在渲"
          "染时把 caveat 显式化",
    "en": "declare under extensions.ambiguities, with the kind "
          "`ill_defined_intervention`, that this question accepts an estimand "
          "mixed over several interventions — Themis stops issuing this "
          "warning and makes the caveat explicit when it renders",
}


def _classify_ill_defined_intervention_versions(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
    extensions: dict | None,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """The well-defined-intervention prerequisite.

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
        ambiguities = extensions.get(blocks.Block.AMBIGUITIES) or ()
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
        description = language.fill(
            _INTERVENTION_UNDECLARED, lang, intervention=intervention_pred,
        )
        ref_id = f"intervention_state_inferred:{intervention_pred}"
    else:
        description = language.fill(
            _INTERVENTION_STATE_WITHOUT_WINDOW, lang,
            intervention=intervention_pred,
        )
        ref_id = f"intervention_state_without_time_window:{intervention_pred}"
    yield DataGap(
        kind=GapKind.ILL_DEFINED_INTERVENTION_VERSIONS,
        severity=GapSeverity.IMPORTANT,
        description=description,
        blocks=GapBlocks.IDENTIFICATION,
        if_provided=language.fill(
            _ILL_DEFINED_IF_PROVIDED, lang, intervention=intervention_pred,
        ),
        alternative_paths=(
            language.fill(_ILL_DEFINED_MAKE_IT_AN_EVENT, lang,
                          intervention=intervention_pred),
            language.fill(_ILL_DEFINED_SPLIT_IN_TWO, lang,
                          intervention=intervention_pred),
            language.fill(_ILL_DEFINED_USE_EXPERIMENTAL_DATA, lang),
            language.fill(_ILL_DEFINED_OPT_IN, lang),
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=ref_id,
            ),
        ),
    )


# Why each displaced layer cannot be done in the same dispatch, in the
# reader's language. The pairs themselves are declared in
# :mod:`themis.routing`; this table only translates them, and a gate holds
# the two to exactly the same key set, so a pair added to the route table
# without a sentence here fails rather than reaching a reader as a blank.
_DISPLACEMENT_REASON: dict[tuple[str, str], language.Words] = {
    ("longitudinal", "joint_intervention"): {
        "zh": "纵向 g-formula 沿时间序对**一条**处理轨迹做序贯标准化；对处理集合"
              "的联合干预（含处理×处理交互）不是它算出来的那个量。",
        "en": "the longitudinal g-formula standardizes sequentially along "
              "time over **one** treatment trajectory; a joint intervention "
              "on a set of treatments (with treatment-by-treatment "
              "interaction) is not the quantity it computes.",
    },
    ("longitudinal", "transport"): {
        "zh": "纵向 g-formula 在主样本自己的总体里标准化；把结果搬到目标总体是"
              "另一次识别（选择图 + s-可容许集），它不顺带做。",
        "en": "the longitudinal g-formula standardizes within the main "
              "sample's own population; carrying the result to a target "
              "population is a second identification (selection diagram + "
              "s-admissible set), and it does not come along for free.",
    },
    ("longitudinal", "mediation_joint"): {
        "zh": "时变处理的直接/间接效应分解要的是时变中介的序贯可忽略性，与总效应"
              "的 g-formula 不是同一组条件；这条路线只给总效应。",
        "en": "decomposing a time-varying treatment into direct and indirect "
              "effects needs sequential ignorability for the time-varying "
              "mediator, which is not the set of conditions the total-effect "
              "g-formula rests on; this route gives the total effect only.",
    },
    ("longitudinal", "mediation_single"): {
        "zh": "时变处理的直接/间接效应分解要的是时变中介的序贯可忽略性，与总效应"
              "的 g-formula 不是同一组条件；这条路线只给总效应。",
        "en": "decomposing a time-varying treatment into direct and indirect "
              "effects needs sequential ignorability for the time-varying "
              "mediator, which is not the set of conditions the total-effect "
              "g-formula rests on; this route gives the total effect only.",
    },
    ("joint_intervention", "transport"): {
        "zh": "联合对比是在主样本自己的总体里算的；联合干预路径的 v1 作用域明确"
              "不与 `target_population` 组合。",
        "en": "the joint contrast is computed within the main sample's own "
              "population; the v1 scope of the joint-intervention route "
              "explicitly does not compose with `target_population`.",
    },
    ("joint_intervention", "mediation_joint"): {
        "zh": "联合干预给的是处理集合的总对比（含处理×处理交互），不做直接/间接"
              "分解；该路径的 v1 作用域明确不与中介声明组合。",
        "en": "a joint intervention gives the total contrast over a set of "
              "treatments (with treatment-by-treatment interaction) and does "
              "no direct/indirect decomposition; the v1 scope of that route "
              "explicitly does not compose with a mediator declaration.",
    },
    ("joint_intervention", "mediation_single"): {
        "zh": "联合干预给的是处理集合的总对比（含处理×处理交互），不做直接/间接"
              "分解；该路径的 v1 作用域明确不与中介声明组合。",
        "en": "a joint intervention gives the total contrast over a set of "
              "treatments (with treatment-by-treatment interaction) and does "
              "no direct/indirect decomposition; the v1 scope of that route "
              "explicitly does not compose with a mediator declaration.",
    },
    ("transport", "mediation_joint"): {
        "zh": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport 是 sequential operations（先在 source population 做 "
              "mediation, 再 transport 各 component 到 target），不能在一个 "
              "query 里同时 dispatch。",
        "en": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport are sequential operations (mediation first in the "
              "source population, then each component transported to the "
              "target); they cannot be dispatched together in one query.",
    },
    ("transport", "mediation_single"): {
        "zh": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport 是 sequential operations（先在 source population 做 "
              "mediation, 再 transport 各 component 到 target），不能在一个 "
              "query 里同时 dispatch。",
        "en": "Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
              "transport are sequential operations (mediation first in the "
              "source population, then each component transported to the "
              "target); they cannot be dispatched together in one query.",
    },
    ("mediation_joint", "mediation_single"): {
        "zh": "`mediators` 把这些中介当作**一个块**做联合 NDE/NIE；穿过其中单个"
              "中介的路径特定拆分不含在块的分解里 —— 它需要块本身不需要的额外"
              "条件，本仓明确列为作用域之外。",
        "en": "`mediators` decomposes these into a joint NDE/NIE as **one "
              "block**; the path-specific split through a single mediator "
              "inside it is not part of the block's decomposition — it needs "
              "conditions the block itself does not, and this repository "
              "puts it explicitly out of scope.",
    },
}


def _classify_unattempted_layer_dispatch_conflict(
    *,
    dispatch,
    lang: language.Lang | str,
) -> Iterable[DataGap]:
    """Disclose every layer the dispatcher took this query away from.

    L3 case 009 found the first instance: a query naming both a mediator
    and a target population is claimed by two rows, the cascade returns at
    the higher one, and the reader gets a ``structurally_solved`` result
    with no sign that the other layer was never attempted.

    This used to be reconstructed here — read back which of
    ``transport_identification`` / the mediation view came out populated,
    and infer from the empty one which layer had been skipped. That is an
    inference from residue: it can see only the pair it was written for,
    and it is wrong the first time a layer fills its extension and then
    fails. The dispatcher knows the answer outright, so it now says so
    (:class:`~themis.types.DispatchRecord`) and this reads the record.

    Severity: IMPORTANT — the dispatched layer is structurally valid (not
    a bug to block), but a silent skip violates VISION's
    honest-about-what-wasn't-done principle.
    """
    if dispatch is None or not dispatch.displaced:
        return
    from .. import routing

    winner = routing.route(dispatch.answered_by)
    for skipped_id in dispatch.displaced:
        skipped = routing.route(skipped_id)
        won = f"`{winner.triggered_by}`"
        lost = f"`{skipped.triggered_by}`"
        yield _dispatch_conflict_gap(winner, skipped, won, lost, lang=lang)


_DISPATCH_CONFLICT: language.Words = {
    "zh": "Query 同时声明了 {won} 和 {lost}；当前 dispatch 只跑了 "
          "**{winner}**，**{skipped}** 被静默跳过。{reason}当前 result 只反映 "
          "{winner} 这一层；{skipped} 分析需要单独 query。",
    "en": "the query declares both {won} and {lost}; this dispatch ran "
          "**{winner}** only, and **{skipped}** was skipped in silence. "
          "{reason}The result reflects the {winner} layer alone; a {skipped} "
          "analysis takes a query of its own.",
}
_DISPATCH_SPLIT_THE_QUERY: language.Words = {
    "zh": "拆成两个 query，各自只声明一层：一个带 {won}，一个带 {lost}",
    "en": "split it into two queries, each declaring one layer: one with "
          "{won}, one with {lost}",
}
#: One sentence for both directions — which layer is wanted and which one
#: goes is what the two call sites differ in, not what is being said.
_DISPATCH_DROP_THE_OTHER: language.Words = {
    "zh": "如果只想要 {wanted} 结果，删除 {drop} 使 dispatch 唯一",
    "en": "if the {wanted} result is the one you want, drop {drop} so the "
          "dispatch is unambiguous",
}


def _dispatch_conflict_gap(
    winner, skipped, won: str, lost: str, *, lang: language.Lang | str,
) -> DataGap:
    return DataGap(
        kind=GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
        severity=GapSeverity.IMPORTANT,
        description=language.fill(
            _DISPATCH_CONFLICT, lang,
            won=won, lost=lost, winner=winner.id, skipped=skipped.id,
            reason=language.fill(
                _DISPLACEMENT_REASON[winner.id, skipped.id], lang),
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=language.fill(
            _DISPATCH_SPLIT_THE_QUERY, lang, won=won, lost=lost,
        ),
        alternative_paths=(
            language.fill(_DISPATCH_DROP_THE_OTHER, lang,
                          wanted=winner.id, drop=lost),
            language.fill(_DISPATCH_DROP_THE_OTHER, lang,
                          wanted=skipped.id, drop=won),
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=(
                    f"query:dispatch_conflict:{winner.id}_dispatched_"
                    f"{skipped.id}_skipped"
                ),
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
        if step.rule not in _ADJUSTMENT_SET_RULE_NAMES:
            continue
        z = step.inputs.get("z")
        if not isinstance(z, (frozenset, set, tuple)):
            continue
        return sorted({a.predicate for a in z if isinstance(a, Atom)})
    return []


_TARGET_LABEL: language.Words = {"zh": "目标变量",
                                 "en": "the outcome variable"}
_INTERVENTION_LABEL: language.Words = {"zh": "干预变量",
                                       "en": "the intervention variable"}


def _query_target_label(stmt, *, lang: language.Lang | str) -> str:
    """Best-effort label for the query's outcome variable.

    Real-test caught: cause queries (with `from`/`to`) used to fall
    through to the literal string ``<target>`` because only effect
    queries' `target.atom` shape was handled. Now also reads `to` for
    cause queries and falls back to a generic phrase instead of an
    angle-bracketed placeholder a renderer would surface verbatim.
    """
    q = getattr(stmt, "query", None)
    if q is None:
        return language.fill(_TARGET_LABEL, lang)
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
    return language.fill(_TARGET_LABEL, lang)


def _query_intervention_label(stmt, *, lang: language.Lang | str) -> str:
    """Best-effort label for the query's treatment variable. See
    ``_query_target_label`` for the cause-query motivation."""
    q = getattr(stmt, "query", None)
    if q is None:
        return language.fill(_INTERVENTION_LABEL, lang)
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
    return language.fill(_INTERVENTION_LABEL, lang)


_AMBIGUOUS_VARIABLE: language.Words = {
    "zh": "变量 `{variable}` 缺操作化定义：{missing}",
    "en": "the variable `{variable}` has no operational definition: "
          "{missing}",
}
_AMBIGUOUS_IF_PROVIDED: language.Words = {
    "zh": "变量框架化后，下游结果（点估计 / bounds）的语义才确定 —— 用户能判断 "
          "'P(Y|X)' 到底说的是哪段时间窗 / 哪种测量",
    "en": "once the variable is framed, what the downstream result (a point, "
          "an interval) means is settled — the reader can tell which time "
          "window and which measurement 'P(Y|X)' is about",
}


def _classify_ambiguous_variable(
    framing_notes: tuple[FramingNote, ...],
    stmt=None,
    *,
    lang: language.Lang | str,
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
            description=language.fill(
                _AMBIGUOUS_VARIABLE, lang,
                variable=note.predicate, missing=missing_str,
            ),
            blocks=GapBlocks.INTERPRETATION,
            if_provided=language.fill(_AMBIGUOUS_IF_PROVIDED, lang),
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
    lang: language.Lang | str = language.DEFAULT,
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
    return (_make_summary(hydrated, tier, lang=lang),
            _make_actionable_steps(hydrated, lang=lang))


_SUMMARY_WITH_BLOCKING: language.Words = {
    "zh": "{head}（共 {blocking} 个 blocking 缺口）",
    "en": "{head} ({blocking} blocking gaps in all)",
}
_SUMMARY_INTERVAL_AVAILABLE: language.Words = {
    "zh": "可得区间估计（点识别被阻断，但有信息性 bounds）：{base}",
    "en": "an interval is available (point identification is blocked, but "
          "the bounds are informative): {base}",
}
_SUMMARY_NEITHER: language.Words = {
    "zh": "图+数据无法给出点或区间估计（需补假设或更强数据）：{base}",
    "en": "the graph and the data give neither a point nor an interval "
          "(this needs a further assumption, or stronger data): {base}",
}


def _make_summary(
    gaps: list[DataGap], answer_tier: AnswerTier | None = None, *,
    lang: language.Lang | str,
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
        base = language.fill(_SUMMARY_WITH_BLOCKING, lang,
                             head=head.description, blocking=blocking_count)
    # Lead the one-line summary with answer availability so a prose
    # renderer is not misled into showing a blocking gap as "no answer"
    # when an interval is in hand. POINT / None leave the summary as the
    # most-blocking-gap description (no inversion to correct).
    if answer_tier == AnswerTier.INTERVAL:
        return language.fill(_SUMMARY_INTERVAL_AVAILABLE, lang, base=base)
    if answer_tier == AnswerTier.NONE:
        return language.fill(_SUMMARY_NEITHER, lang, base=base)
    return base


_STEP_SUPPLY: language.Words = {"zh": "补 {what}", "en": "supply {what}"}
_STEP_OR: language.Words = {"zh": "或：{alternative}",
                            "en": "or: {alternative}"}


def _make_actionable_steps(
    gaps: list[DataGap], *, lang: language.Lang | str,
) -> list[str]:
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
            steps.append(language.fill(
                _STEP_SUPPLY, lang, what=_short_label_for(gap, lang=lang)))
        if gap.alternative_paths:
            steps.append(language.fill(
                _STEP_OR, lang, alternative=gap.alternative_paths[0]))
    return steps


#: The noun phrases ``actionable_next_steps`` is built from. Two shapes per
#: gap kind, because a label naming the variables it wants is worth more
#: than a generic one and the required_data does not always carry them.
_LABEL_TARGET_MARGINAL: language.Words = {
    "zh": "P*({variables}) 在 {population} 上",
    "en": "P*({variables}) on {population}",
}
_LABEL_TARGET_POP_Z: language.Words = {
    "zh": "目标人群上的 P*(Z)",
    "en": "P*(Z) on the target population",
}
_LABEL_TARGET_POPULATION: language.Words = {
    "zh": "目标人群", "en": "the target population",
}
_LABEL_SOURCE_POPULATION: language.Words = {
    "zh": "源人群", "en": "the source population",
}
_LABEL_STRATIFIED_ON: language.Words = {
    "zh": "P(Y|do(X), {variables}) 在 {population} 上的分层条件分布",
    "en": "the stratified conditional P(Y|do(X), {variables}) on "
          "{population}",
}
_LABEL_SOURCE_STRATIFIED: language.Words = {
    "zh": "源人群上的分层条件分布 P(Y|do(X), Z)",
    "en": "the stratified conditional P(Y|do(X), Z) on the source population",
}
_LABEL_THETA_GRAPH_MISMATCH: language.Words = {
    "zh": "图与 CPT 的不一致（修图或补条件量）",
    "en": "the graph and the CPTs disagree (fix the graph, or supply the "
          "conditional)",
}
_LABEL_TARGET_DISTRIBUTION: language.Words = {
    "zh": "目标人群分布", "en": "the target population's distribution",
}
_LABEL_UNIT_OBSERVATION: language.Words = {
    "zh": "该单位的观测值", "en": "this unit's observed values",
}
_LABEL_STRUCTURAL_INPUT: language.Words = {
    "zh": "结构输入", "en": "a structural input",
}
_LABEL_IDENTIFICATION_PREMISE: language.Words = {
    "zh": "识别前提", "en": "an identification premise",
}
_LABEL_VALID_INSTRUMENT: language.Words = {
    "zh": "有效的工具变量", "en": "a valid instrument",
}
_LABEL_ONE_MEDIATORS_DISTRIBUTIONS: language.Words = {
    "zh": "中介 {mediator} 的相关分布",
    "en": "the distributions belonging to mediator {mediator}",
}
_LABEL_MEDIATOR_DISTRIBUTIONS: language.Words = {
    "zh": "中介相关分布", "en": "the mediator's distributions",
}
_LABEL_ADJUSTMENT_OR_ROUTE: language.Words = {
    "zh": "可识别的调整集 / 替代识别路径",
    "en": "an identifiable adjustment set, or another route to "
          "identification",
}
_LABEL_ONE_OPERATIONAL_DEFINITION: language.Words = {
    "zh": "`{variable}` 的操作化定义",
    "en": "an operational definition for `{variable}`",
}
_LABEL_OPERATIONAL_DEFINITION: language.Words = {
    "zh": "变量的操作化定义",
    "en": "an operational definition for the variable",
}


def _short_label_for(gap: DataGap, *, lang: language.Lang | str) -> str:
    """A noun-phrase label for the actionable_next_steps line. The full
    ``description`` is a complete sentence — concatenating it into "补 X
    → Y" produces a wall of text. Each gap_kind gets a concise label
    that names *what is missing* in 1-3 nouns."""
    rd = gap.required_data
    if gap.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN:
        if rd and rd.variables:
            return language.fill(
                _LABEL_TARGET_MARGINAL, lang,
                variables=", ".join(rd.variables),
                population=(rd.population
                            or language.fill(_LABEL_TARGET_POPULATION, lang)),
            )
        return language.fill(_LABEL_TARGET_POP_Z, lang)
    if gap.kind == GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN:
        if rd and rd.variables:
            return language.fill(
                _LABEL_STRATIFIED_ON, lang,
                variables=", ".join(rd.variables),
                population=(rd.population
                            or language.fill(_LABEL_SOURCE_POPULATION, lang)),
            )
        return language.fill(_LABEL_SOURCE_STRATIFIED, lang)
    if gap.kind == GapKind.MISSING_DISTRIBUTION:
        # The distribution's own name, taken from the provenance the
        # species wrote. It used to be recovered by stripping a Chinese
        # prefix off ``description`` — but the description is a sentence,
        # and a sentence in the reader's language keeps the name
        # somewhere else. The same read the ambiguous-variable branch
        # below already does.
        for prov in gap.provenance or ():
            if (prov.ref_kind == GapRefKind.INVESTIGATION_REQUEST
                    and prov.ref_id):
                return _strip_parameter_prefix(prov.ref_id)
        return gap.description
    if gap.kind == GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH:
        # actionable_next_steps wants a noun-phrase, not the
        # full sentence. The repair is structural, so name the choice
        # rather than the symptom.
        return language.fill(_LABEL_THETA_GRAPH_MISMATCH, lang)
    if gap.kind == GapKind.MISSING_POPULATION_DISTRIBUTION:
        return language.fill(_LABEL_TARGET_DISTRIBUTION, lang)
    if gap.kind == GapKind.MISSING_UNIT_OBSERVATION:
        return language.fill(_LABEL_UNIT_OBSERVATION, lang)
    if gap.kind == GapKind.MISSING_STRUCTURAL_INPUT:
        return language.fill(_LABEL_STRUCTURAL_INPUT, lang)
    if gap.kind == GapKind.MISSING_ASSUMPTION:
        # Not always an assumption to declare — the same channel carries
        # experimental inputs and contradictory declarations, so the
        # label names the premise, not the repair.
        return language.fill(_LABEL_IDENTIFICATION_PREMISE, lang)
    if gap.kind == GapKind.MISSING_IV_CANDIDATE:
        return language.fill(_LABEL_VALID_INSTRUMENT, lang)
    if gap.kind == GapKind.MISSING_MEDIATOR_DATA:
        if rd and rd.variables:
            return language.fill(_LABEL_ONE_MEDIATORS_DISTRIBUTIONS, lang,
                                 mediator=rd.variables[0])
        return language.fill(_LABEL_MEDIATOR_DISTRIBUTIONS, lang)
    if gap.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET:
        return language.fill(_LABEL_ADJUSTMENT_OR_ROUTE, lang)
    if gap.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION:
        # Provenance carries the predicate name (a FRAMING_NOTE ref).
        for prov in gap.provenance or ():
            if prov.ref_kind == GapRefKind.FRAMING_NOTE and prov.ref_id:
                return language.fill(_LABEL_ONE_OPERATIONAL_DEFINITION, lang,
                                     variable=prov.ref_id)
        return language.fill(_LABEL_OPERATIONAL_DEFINITION, lang)
    return gap.description
