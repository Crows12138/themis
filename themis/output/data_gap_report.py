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

Phase 11+ structural caveats — the kinds that QUALIFY the answer, which
a reader surface leads with rather than lists. The set is declared beside
GapKind as ``QUALIFIES_THE_ANSWER``; nothing stores a rendering of it, so
a kind that leaves the report takes every restatement with it:
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
- transport_sources_disagree — two declared source domains carry ONE
  target effect to two numbers. Theta is declared rather than estimated,
  so the difference cannot be sampling noise: at least one selection
  diagram is refuted, and no number is reported at all. The only
  falsification the kernel itself raises, and the only species with no
  alternative path — what has to change is a declaration, not the data
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

Additional data-need gap_kinds — asks rather than caveats:
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
- iv_estimand_fallback_to_linear — the instrument is valid only given a
  conditioning set, so the answer should have been a stratified Wald,
  and this sample could not be stratified; appended by
  themis/estimation/dispatch.py._attach_iv_estimand_fallback_warning.
- declared_type_data_mismatch — a column's declared type is not what the
  data holds, so the estimate is about what arrived rather than about
  the declaration; appended where the contract reads the frame.
- proxy_coarsening_undeclared — a proximal query's proxies present some
  number of levels other than the k it posits for the latent, and no
  grouping was declared; appended by
  themis/estimation/dispatch.py._record_proxy_coarsening_gap. The one
  entry here filed where NO number was produced, which is what makes it
  blocking: the others qualify an estimate, this one says why there is
  not one.
- regularisation_is_moving_the_answer — the same estimator's other
  regime, and the mirror image of the entry above. A continuous-proxy
  bridge equation has no numeric solution without a penalty, so one is
  always applied; re-solving at lighter penalties says whether the
  answer is the data's or the penalty's, and this is filed where the
  point bends further than one standard error or a lighter penalty has
  no solution at all. Appended by
  themis/estimation/dispatch.py._record_regularisation_gap.
- treatment_bridge_leaves_its_range — the third of that family, and the
  one about a function class rather than about a penalty. A proximal
  query's TREATMENT bridge is a reciprocal probability and is bounded
  below by one; the sieve solving for it is linear in its parameters
  and cannot know that, so where the declared span will not hold such a
  function the fit dips below zero and part of the inverse-probability
  average is weighted negatively. Filed off the recorded share by
  themis/estimation/dispatch.py._record_treatment_bridge_range_gap.
- answer_is_a_test_not_an_effect_size — a caveat although its route is a
  real errand, and here for the reason answer_is_bounds_not_point_estimate
  is: an answer of a weaker shape came back and the first thing the
  reader needs is not to read it as the stronger one. A discrete
  proximal query whose channel could not be inverted falls back to Miao
  §4's test of the causal null, so what is on the envelope is a p-value
  where a number was asked for — and a p-value handed to someone who
  asked how much is read as a small effect. Filed by
  themis/estimation/dispatch.py._record_only_the_null_was_tested_gap,
  which also reconciles the tier to ``none``: a test is neither a point
  nor an interval.

This list is a reading guide, not the declaration: which of the two a
kind is is stated once in ``themis.types.QUALIFIES_THE_ANSWER`` /
``ASKS_FOR_SOMETHING``, and an unclassified kind raises at import.
"""
from __future__ import annotations

import re
from typing import Iterable, NamedTuple, Protocol

from .. import blocks, gaps, language, questions, refusals
from ..gaps import (
    INSTRUMENT_CHANNEL, WHY_AN_AMBIGUITY_GIVES,
    Route, Sentence, Unnamed, occasion as _occasion, route as _route,
    route_entry as _route_entry, sentence as _sentence,
)
from . import derivation_glossary, sample_size
from .sample_size import (
    Precision,
    estimate_min_n_single_proportion,
    estimate_min_n_two_arm_binary,
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
    GapRoute,
    GapSeverity,
    InvestigationItem,
    InvestigationRequest,
    MISSING_ITEM_GAPS,
    ObservationStatement,
    QueryKind,
    RequiredDataType,
    ResultStatus,
    VariableDeclaration,
    atoms_held_by,
    cites,
    raised_by_ref,
    step_name,
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
    graph=None,
    bidirected=None,
    stmt=None,
    structural_result=None,
    bounds_results=(),
    numeric_result=None,
    confidence: float | None = None,
    dispatch=None,
) -> DataGapReport | None:
    """Synthesize a DataGapReport from the result-envelope signals.

    Returns ``None`` when the question names no quantity — so nothing but
    framing can leave it short of data — and no framing or assumption gaps
    exist. For a question that does name one the returned report may still
    have ``gaps=()`` when fully solved — callers can distinguish "no need
    to ask" (None) from "asked and got a clean bill of health" (empty
    tuple).

    No language reaches here. What this module writes is statements, and
    a statement is which sentence plus this occasion's facts — so there is
    nothing here to say in one language rather than another. A ``lang``
    threaded through thirty-five signatures used to say otherwise, and its
    one use was five holes that held another sentence: a shortfall, which
    had to be rendered on the way in because the table its sentences come
    from had no name on an envelope. No caller ever passed one.
    """
    extensions = extensions or {}

    must_disclose_gaps: list[DataGap] = []
    must_disclose_gaps.extend(
        _classify_unverified_proposal_edges(
            program, graph, structural_result, stmt, extensions,
        )
    )
    must_disclose_gaps.extend(_classify_iv_assumption(extensions))
    must_disclose_gaps.extend(_classify_feedback_loop(extensions))
    must_disclose_gaps.extend(
        _classify_mediation_assumptions(extensions))
    must_disclose_gaps.extend(
        _classify_transport_assumptions(extensions))
    must_disclose_gaps.extend(
        _classify_llm_ambiguities(extensions))
    must_disclose_gaps.extend(
        _classify_bounds_not_point(bounds_results))
    must_disclose_gaps.extend(_classify_low_confidence(confidence))
    must_disclose_gaps.extend(_classify_front_door_assumptions(
        derivation, program=program, stmt=stmt,
    ))
    must_disclose_gaps.extend(_classify_counterfactual_assumptions(
        derivation, status, query_kind,
    ))
    must_disclose_gaps.extend(
        _classify_graph_learned_from_data(program))
    must_disclose_gaps.extend(_classify_unmeasured_confounder_risk(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
    ))
    must_disclose_gaps.extend(_classify_measurement_error_concern(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
        extensions=extensions,
    ))
    must_disclose_gaps.extend(_classify_unattempted_layer_dispatch_conflict(
        dispatch=dispatch,
    ))
    must_disclose_gaps.extend(_classify_collider_conditioning_opens_backdoor(
        program=program, stmt=stmt, graph=graph, bidirected=bidirected,
    ))
    must_disclose_gaps.extend(_classify_selection_on_collider_opens_path(
        program=program, stmt=stmt, graph=graph, bidirected=bidirected,
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
    gaps.extend(_classify_investigation_items(
        investigation_requests, query_kind))
    gaps.extend(_classify_missing_mediator(
        extensions, investigation_requests))
    gaps.extend(
        _classify_transport_target_distribution(extensions, derivation))
    gaps.extend(_classify_ambiguous_variable(framing_notes, stmt))
    gaps.extend(
        _classify_dose_response_data(program, stmt, derivation))

    gaps = _rewrite_iv_aware_alternatives(gaps, bounds_results)
    gaps.sort(key=_gap_sort_key)
    answer_tier = _compute_answer_tier(
        query_kind, gaps, bounds_results, status, numeric_result, stmt,
    )
    if answer_tier is AnswerTier.NONE:
        gaps = _withdraw_interval_offers(gaps, query_kind)
    return DataGapReport(
        gaps=tuple(gaps),
        answer_tier=answer_tier,
    )


def _interval_offer(query_kind: QueryKind) -> GapRoute | None:
    """This question's interval, offered in place of the point it cannot
    have — or nothing, where it has no interval to offer.

    The method that would bracket it is this occasion's fact and the only
    thing the offer varies by.
    """
    fallback = questions.reading_of(query_kind.value).interval_fallback
    if fallback is None:
        return None
    return _route(Route.ACCEPT_THE_INTERVAL, fallback=fallback)


def _withdraw_interval_offers(
    gaps: list[DataGap], query_kind: QueryKind,
) -> list[DataGap]:
    """Take back the interval a NONE tier has just ruled out.

    The tier is the report's own word on what is still reachable; a gap
    still advising "accept bounds for an interval answer" contradicts it
    in the same breath, and the reader acts on the gap. Only the offer is
    withdrawn — :attr:`Route.BOUNDS_ALREADY_COMPUTED` means bounds exist,
    and a result carrying those does not reach NONE.

    By route, not by sentence. It used to rebuild the offer's text and
    compare, which the docstring here defended as safer than a substring
    test — and it was, but only until a second language: the withdrawal
    rendered in one and the offer in the other are two strings, and the
    gap keeps an offer the report has just contradicted.
    """
    from dataclasses import replace as _replace

    if _interval_offer(query_kind) is None:
        return gaps
    out: list[DataGap] = []
    for gap in gaps:
        kept = tuple(a for a in gap.alternative_paths
                     if a.route != Route.ACCEPT_THE_INTERVAL)
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

    Asked here before any data have arrived, so what it can answer is the
    forward-looking half: what could still be got. Once an answer exists
    the same question has the other tense — what came out — and the
    estimation layer asks it there, of the answer's own declared shape
    (``themis.answers``). Neither half is a correction of the other and
    the verifier recomputes both; what used to make them look like two
    authors of one word was the second half being decided from a list of
    gap species instead of from the shape.

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
            # A refuted declaration blocks the point the way an unidentified
            # graph does, and for the stronger reason: the estimand IS
            # identified, in two declared selection diagrams that carry it to
            # two numbers. More of the same distributions reproduces the same
            # contradiction, so there is no point to be had until one of the
            # declarations is withdrawn — which is not a data gap.
            g.kind in (GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
                       GapKind.TRANSPORT_SOURCES_DISAGREE)
            for g in gaps
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


def _rewrite_iv_aware_alternatives(
    gaps: list[DataGap],
    bounds_results,
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

    It reads ``gaps.INSTRUMENT_CHANNEL`` rather than one route, because
    which NAME the reader was sent to the instrument channel under is the
    species' business and this pass's business is the run: once an
    interval has come out of an instrument, both names mean the same next
    move. Keyed on ``find_an_instrument`` alone, this pass went quiet the
    moment a species offered the other one (#466).

    The substitution used to be made on the rendered sentence, and the
    replacement carried a note saying it was worded to avoid the three
    substrings ``scheduler._is_bounds_hint`` searches for — so that the
    scheduler would keep it as a distinct constructive alternative rather
    than collapse it into the generic bounds pointer. Both sides ask about
    the ROUTE now (:attr:`Route.answered_by`), and the wording of a
    user-facing sentence is no longer an input to either.
    """
    from dataclasses import replace

    if not any(
        getattr(getattr(b, "method", None), "value", None) == "balke_pearl_iv"
        for b in (bounds_results or ())
    ):
        return gaps
    out: list[DataGap] = []
    for g in gaps:
        if (
            g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
            and any(a.route in INSTRUMENT_CHANNEL
                    for a in g.alternative_paths)
        ):
            out.append(replace(
                g,
                alternative_paths=tuple(
                    _route(Route.TIGHTEN_THE_IV_INTERVAL)
                    if a.route in INSTRUMENT_CHANNEL else a
                    for a in g.alternative_paths
                ),
            ))
        else:
            out.append(g)
    return out


def _classify_unverified_proposal_edges(
    program,
    graph,
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

    Which edges the answer rests on is
    :func:`_statements_the_answer_rests_on`. This keeps the ones whose
    source is not evidence and names each by its predicates, which is how
    a gap cites an edge.

    What a gap tells is read off those statements themselves. One name can
    stand for several: an edge stated twice, or a program unrolled in time
    or over units grounding several edges between the same two predicates.
    Looked up again by the name, a gap told the last statement written
    under it, one the answer might not rest on, while its verifier read
    the first. So each reading among the statements behind a name is a gap
    of its own, and statements that read alike are one.
    """
    if program is None:
        return
    if not any(
        isinstance(st, (CauseStatement, BidirectedStatement))
        and _is_non_evidence_source(getattr(st.annotations, "source", None))
        for st in program.statements
    ):
        return

    # Each name with each reading once. A name is (from, to), a bidirected
    # pair ordered and its second end marked with ↔ so the renderer tells
    # it from a directed edge; a reading is what the statement's
    # annotation says.
    told: set[tuple[tuple[str, str], tuple[str, ...]]] = set()
    for st in _statements_the_answer_rests_on(
        program, graph, structural_result, stmt, extensions,
    ):
        source = getattr(st.annotations, "source", None)
        if source is None or not _is_non_evidence_source(source):
            continue
        if isinstance(st, CauseStatement):
            ends = (st.from_atom.predicate, st.to_atom.predicate)
        else:
            a, b = sorted((st.left.predicate, st.right.predicate))
            ends = (a, f"↔{b}")
        confidence = getattr(st.annotations, "confidence", None)
        if source.startswith("discovery:"):
            reading: tuple[str, ...] = (
                "discovery", source.split(":", 1)[1].upper(),
                "" if confidence is None else f"{confidence:.0%}")
        else:
            reading = ("llm_proposal",)
        told.add((ends, reading))

    for (frm, to), reading in sorted(told):
        bidirected = to.startswith("↔")
        clean_to = to[1:] if bidirected else to
        edge_render = f"{frm} ↔ {clean_to}" if bidirected else f"{frm} → {to}"
        if reading[0] == "discovery":
            said = [_sentence(Sentence.THE_EDGE_WAS_LEARNED_BY_DISCOVERY,
                              edge=edge_render, algorithm=reading[1])]
            if reading[2]:
                said.append(_sentence(
                    Sentence.THE_EDGE_SURVIVED_THIS_SHARE_OF_RESAMPLES,
                    confidence=reading[2],
                ))
        else:
            said = [_sentence(Sentence.THE_EDGE_IS_AN_LLM_PROPOSAL,
                              edge=edge_render)]
        yield DataGap(
            kind=GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
            describes=tuple(said),
            alternative_paths=(
                _route(Route.SUPPLY_A_SOURCE_FOR_THE_EDGE),
                _route(Route.ASK_CONDITIONALLY),
            ),
            provenance=cites(
                GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
                f"program:bidirected:{frm}↔{clean_to}:annotations.source"
                        if bidirected
                        else f"program:cause:{frm}->{to}:annotations.source",
            ),
        )


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


def _atoms_the_blocks_name(extensions: dict) -> Iterable[str]:
    """The atoms a route adds to those its answer rests between, as the
    envelope spells them: an IV route's instrument and what it conditions
    on, and a mediation's mediators and adjustment sets."""
    iv = (extensions or {}).get(blocks.Block.IV_IDENTIFICATION) or {}
    if iv.get("instrument"):
        yield str(iv["instrument"])
    for entry in iv.get("conditioning") or ():
        yield str(entry)
    view = _mediation_view(extensions)
    if view is not None:
        for branch in ("nde_nie", "cde"):
            for entry in (view.block.get(branch) or {}).get("adjustment") or ():
                yield str(entry)
        yield from view.mediators


def _statements_the_answer_rests_on(
    program, graph, structural_result, stmt, extensions: dict,
) -> tuple[CauseStatement | BidirectedStatement, ...]:
    """The ground cause and bidirected statements an answer rests on.

    Read on G(M), the ground graph the answer was reached on. This was
    read on the predicates, where ``x`` a step back and ``x`` now are one
    node: a program unrolled in time has cycles there, and the simple
    paths walked between predicates were not the paths the answer rests
    on — an edge on the only ground path went unreported when that path
    passed one predicate twice. The walk was bounded too, at 32 paths 12
    atoms deep, so past the bound a larger graph was an answer resting on
    fewer edges.

    A cause statement is rested on when its ground edge lies on a directed
    path between two distinct atoms the answer rests on, or a supporting
    path walks it in either direction: a directed path walks every edge
    forward, an open path through a fork ``x <- z -> y`` walks ``z -> x``
    against its arrow, and the association rests on that arm as much as on
    the other. A bidirected statement is rested on when either end is one
    of those atoms; it has no direction to lie along, so incidence is the
    test.

    Those atoms are every atom the question holds and every atom the
    blocks name. The blocks and the supporting paths spell atoms as
    strings, and are read back as nodes by the one spelling they were
    written with.
    """
    from ..runtime.graph_projection import atom_label, project
    from ..runtime.instantiation import instantiate
    from ..runtime.structural_solver import edges_between

    ground = instantiate(program)
    if graph is None:
        graph = project(ground)
    spelt = {atom_label(node): node for node in graph}

    query = getattr(stmt, "query", None) if stmt is not None else None
    between = set(atoms_held_by(query)) if query is not None else set()
    between.update(spelt[text] for text in _atoms_the_blocks_name(extensions)
                   if text in spelt)

    rested = set(edges_between(graph, between))
    for path in getattr(structural_result, "supporting_paths", ()) or ():
        nodes = [spelt.get(text) for text in path]
        for u, v in zip(nodes, nodes[1:]):
            if u is None or v is None:
                continue
            rested.update(edge for edge in ((u, v), (v, u)) if graph.has_edge(*edge))

    return tuple(
        st for st in ground
        if (isinstance(st, CauseStatement)
            and (st.from_atom, st.to_atom) in rested)
        or (isinstance(st, BidirectedStatement)
            and (st.left in between or st.right in between))
    )


def _classify_iv_assumption(
    extensions: dict,
) -> Iterable[DataGap]:
    """IV identification rests on monotonicity (LATE/Wald) or linearity
    (2SLS/ATE). Surface it as a must-disclose caveat so the renderer
    cannot present an IV estimate as an unconditional ATE.

    The premise goes into a HOLE of this gap's own sentence, which is a
    statement inside a statement. It used to be spliced in as text, and
    that is the defect this whole rule was built around one field over:
    the gap's sentence is bilingual and the thing put in its hole was
    not, so a reader asking for either language got the other one in the
    middle of it.
    """
    iv = (extensions or {}).get(blocks.Block.IV_IDENTIFICATION) or {}
    assumption = iv.get("required_assumption")
    instrument = iv.get("instrument")
    if not assumption:
        return
    if (extensions or {}).get(blocks.Block.FEEDBACK_LOOP):
        # #450 says the same thing and says more of it: not only which
        # premise the instrument rests on but that the quantity changed.
        # Rendering both would give the reader the weaker sentence first.
        return
    yield DataGap(
        kind=GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        describes=(_sentence(Sentence.IV_RESTS_ON_THIS_ASSUMPTION,
                             instrument=instrument,
                             assumption=language.Statement(assumption)),),
        provenance=cites(
            GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
            "extensions.iv_identification.required_assumption",
        ),
    )


def _classify_feedback_loop(
    extensions: dict,
) -> Iterable[DataGap]:
    """#450: what the answer beside a declared loop is an estimate OF.

    Filed here rather than in either layer because both layers reach it.
    The identification end produces the estimand with no data; the numeric
    end produces a number for it. The premise — a linear simultaneous
    system, and a coefficient rather than an equilibrium — is the same
    statement about both, and it is the half a reader cannot recover by
    looking, because a structural coefficient and an interventional
    contrast are the same number of digits.
    """
    loop = (extensions or {}).get(blocks.Block.FEEDBACK_LOOP) or {}
    left, right = loop.get("left"), loop.get("right")
    if not left or not right:
        return
    if loop.get("reduction") is None:
        # The loop reached the estimand and nothing was identified. There
        # is no number for this to be a condition on, and the gap that
        # withdrew the answer already says why — a caveat here would be a
        # reading instruction for something the reader was not given.
        return
    iv = (extensions or {}).get(blocks.Block.IV_IDENTIFICATION) or {}
    yield DataGap(
        kind=GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.IMPORTANT,
        describes=(_sentence(
            Sentence.THE_NUMBER_IS_A_SINGLE_EQUATIONS_COEFFICIENT,
            left=left, right=right,
            treatment=loop.get("treatment", ""),
            outcome=loop.get("outcome", ""),
            instrument=iv.get("instrument", ""),
        ),),
        alternative_paths=(
            # The two names this route's sentence is about are the two the
            # sentence above was just built from. Offered bare, it read
            # "if `` and `` in fact move each other one step apart" — the
            # advice with its subject removed.
            _route(Route.RESOLVE_THE_LOOP_IN_TIME,
                   treatment=loop.get("treatment", ""),
                   outcome=loop.get("outcome", "")),
            _route(Route.WITHDRAW_THE_DECLARED_LOOP),
        ),
        provenance=cites(
            GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
            "extensions.feedback_loop",
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


#: The two branches of a decomposition, as a caveat spells each and as the
#: envelope files it.
#:
#: Spelt once because the two are one fact. A caveat saying ``CDE`` is
#: saying its assumptions were read from ``…cde.assumptions`` -- the word
#: over it and the key its provenance cites pick out the same branch -- and
#: anything holding the word has to know which key it picks out.
_BRANCHES: tuple[tuple[str, str], ...] = (
    ("NDE/NIE", "nde_nie"),
    ("CDE", "cde"),
)


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
    for branch_name, branch_key in _BRANCHES:
        branch = view.block.get(branch_key) or {}
        if not branch.get("identifiable"):
            continue
        assumptions = branch.get("assumptions") or ()
        if not assumptions:
            continue
        said = (Sentence.MEDIATION_IS_IDENTIFIABLE_FOR_A_MEDIATOR_BLOCK
                if view.joint
                else Sentence.MEDIATION_IS_IDENTIFIABLE_FOR_A_MEDIATOR)
        yield DataGap(
            kind=GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
            describes=(_sentence(
                said, branch=branch_name, subject=view.subject,
                assumptions=", ".join(assumptions),
            ),),
            provenance=cites(
                GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
                f"extensions.{view.key}.{branch_key}.assumptions",
            ),
        )


def _classify_transport_assumptions(
    extensions: dict,
) -> Iterable[DataGap]:
    """Transport identification (Bareinboim-Pearl) requires
    S-admissibility plus correct selection-node specification. The
    transferred estimate is invalid outside those assumptions."""
    transport = (extensions or {}).get(blocks.Block.TRANSPORT_IDENTIFICATION) or {}
    if not transport:
        return
    tgt_pop = transport.get("target_population",
                            Unnamed.TARGET_POPULATION)
    # One line per transporting source: S-admissibility is a claim about
    # ONE selection diagram, so a reader granting it for two sources is
    # granting two things and each names its own.
    for route in transport.get("sources") or ():
        if not isinstance(route, dict) or not route.get("transportable"):
            continue
        yield DataGap(
            kind=GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
            describes=(_sentence(
                Sentence.TRANSPORT_RESTS_ON_S_ADMISSIBILITY,
                source=route.get("source_population")
                or Unnamed.SOURCE_POPULATION,
                target=tgt_pop),),
            provenance=cites(
                GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
                "extensions.transport_identification",
            ),
        )


def _classify_llm_ambiguities(
    extensions: dict,
) -> Iterable[DataGap]:
    """LLM-declared ambiguities the kernel did not resolve into a
    structural decision (reciprocal causation, mechanism vs existence,
    mediator choice). Renderer must surface the LLM's own uncertainty —
    leaving these unspoken would make the answer look confident when the
    upstream itself wasn't."""
    ambiguities = (extensions or {}).get(blocks.Block.AMBIGUITIES) or ()
    for at, amb in enumerate(ambiguities):
        if not isinstance(amb, dict):
            continue
        kind = amb.get("kind", "<unspecified>")
        rationale = next(
            (amb[field] for field in WHY_AN_AMBIGUITY_GIVES
             if amb.get(field)), "")
        # dose_response_query has its own dedicated gap_kind; skip.
        if kind == "dose_response_query":
            continue
        yield DataGap(
            kind=GapKind.LLM_DECLARED_AMBIGUITY,
            describes=(
                _sentence(
                    Sentence.THE_CALLER_FLAGGED_AN_UNCERTAINTY_AND_SAID_WHY,
                    kind=kind, rationale=rationale)
                if rationale else
                _sentence(Sentence.THE_CALLER_FLAGGED_AN_UNCERTAINTY,
                          kind=kind),
            ),
            # Where it is, not what it says it is. ``kind`` is the one
            # field this open block requires, which made it the obvious
            # thing to address an entry by and the wrong one: nothing
            # says a caller may not flag two uncertainties of a kind, and
            # when one did, two entries that differed in every other
            # field became two gaps that differed in none — each citing a
            # place with two occupants and naming neither.
            provenance=cites(
                GapKind.LLM_DECLARED_AMBIGUITY,
                f"extensions.ambiguities[#{at}]",
            ),
        )


# Threshold below which composite confidence triggers a must-disclose
# caveat. 0.6 is the conventional "substantial uncertainty" line —
# anything ≥ 0.6 gets through silently to keep the channel signal-rich
# rather than firing on every routine answer.
_LOW_CONFIDENCE_THRESHOLD: float = 0.6


def _classify_low_confidence(
    confidence: float | None,
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
        describes=(_sentence(
            Sentence.THE_COMPOSITE_CONFIDENCE_IS_BELOW_THE_THRESHOLD,
            confidence=f"{confidence:.2f}",
            threshold=_LOW_CONFIDENCE_THRESHOLD,
        ),),
        provenance=cites(GapKind.LOW_CONFIDENCE_INPUT_DATA, "confidence"),
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
    said = (_sentence(Sentence.FRONT_DOOR_RESTS_ON_FOUR_PREMISES),)
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
            describes=said,
            provenance=_step_ref(
                GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
                derivation, triggering),
        )
        return
    if _has_front_door_pattern(program, stmt):
        yield DataGap(
            kind=GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
            describes=said,
            provenance=cites(
                GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
                "program:front_door_pattern",
                ref_kind=GapRefKind.PROGRAM_SITE,
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
    distinction is lost in rendering.

    Which questions those are is the question's to declare
    (:attr:`themis.questions.Question.asks_across_worlds`) and was
    spelled here as one query kind, with a status word and a three-name
    list of derivation rules catching what that missed. They missed
    thirteen: every ``counterfactual_conjunction``, every ``causation``
    answered with points instead of bounds, and the linear-SCM
    counterfactual that came back through the estimator rather than the
    solver. Reading the answer is what made the caveat turn on what came
    out, so one ``causation`` query stated its own premises or did not
    depending on whether monotonicity had been declared -- and a
    question is not a fact about the answer to it."""
    triggering = next(
        (
            step for step in derivation
            if step.rule in _COUNTERFACTUAL_DERIVATION_RULES
        ),
        None,
    )
    if not questions.reading_of(query_kind.value).asks_across_worlds:
        return
    # Not what raised it, and named anyway: the two check names this
    # species declares are carried by answers already collected, and
    # the pair says so where it is declared.
    reached_a_counterfactual_status = status in (
        ResultStatus.COUNTERFACTUAL_SOLVED,
        ResultStatus.COUNTERFACTUAL_BOUNDED,
    )
    yield DataGap(
        kind=GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
        describes=(_sentence(
            Sentence.THE_COUNTERFACTUAL_RESTS_ON_CROSS_WORLD_PREMISES),),
        provenance=(
            _step_ref(
                GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
                derivation, triggering)
            if triggering
            # The common counterfactual case carries no derivation
            # chain — so there is no step to cite, and citing one
            # produced a dangling provenance the kernel's own T10-1
            # rejected on every derivation-less result. What raised it
            # is the question; which of the species' two names the ref
            # wears is the answer's shape, and the declaration beside
            # the pair says why that is so and what closes it.
            else raised_by_ref(
                GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
                check=("counterfactual_status"
                       if reached_a_counterfactual_status
                       else "counterfactual_query_kind"),
            )
        ),
    )


def _classify_bounds_not_point(
    bounds_results,
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
    said = [_sentence(Sentence.THE_ANSWER_IS_AN_INTERVAL_NOT_A_POINT)]
    if len(rows) > 1:
        said.append(_sentence(
            Sentence.SEVERAL_INTERVALS_BOUND_THE_SAME_QUANTITY,
            count=len(rows)))
    for b in rows:
        method = getattr(b, "method", None)
        # ``.value`` when it is an enum member, the thing itself otherwise.
        method_name = str(getattr(method, "value", method))
        assumptions = getattr(b, "assumptions", ()) or ()
        said.append(
            _sentence(Sentence.ONE_INTERVAL_AND_WHAT_IT_RESTS_ON,
                      method=method_name,
                      assumptions=", ".join(assumptions))
            if assumptions else
            _sentence(Sentence.ONE_INTERVAL_THAT_RESTS_ON_NOTHING,
                      method=method_name)
        )
        if getattr(b, "width_when_uninformative", False):
            said.append(_sentence(Sentence.AND_THAT_INTERVAL_IS_UNINFORMATIVE))
    if len(rows) > 1:
        said.append(_sentence(Sentence.CHOOSE_BY_WHICH_ASSUMPTIONS_YOU_ACCEPT))
    yield DataGap(
        kind=GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
        describes=tuple(said),
        provenance=cites(
            GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
            "bounds_results",
        ),
    )


def _classify_graph_learned_from_data(
    program,
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
    said = [_sentence(Sentence.THE_GRAPH_WAS_LEARNED_BY_AN_ALGORITHM,
                      algorithm=algo.upper())]
    if alpha is not None:
        said.append(_sentence(
            Sentence.DISCOVERY_USED_THIS_SIGNIFICANCE_THRESHOLD, alpha=alpha))
    if n is not None:
        said.append(_sentence(Sentence.DISCOVERY_RAN_ON_THIS_MANY_ROWS, n=n))
    said.append(_sentence(
        Sentence.A_LEARNED_GRAPH_INHERITS_THE_ALGORITHMS_ASSUMPTIONS))
    violations = metadata.get("assumption_violations") or ()
    if violations:
        # Statements, not text. What the run found broken is itself a
        # sentence, so it goes in the slot as one and is assembled where
        # the reader is — this used to join them with an ASCII semicolon
        # and paste the result into a Chinese sentence.
        said.append(_sentence(
            Sentence.THE_ALGORITHMS_ASSUMPTIONS_WERE_VIOLATED_ON_THIS_DATA,
            violations=[language.Statement(one) for one in violations],
        ))
    yield DataGap(
        kind=GapKind.GRAPH_LEARNED_FROM_DATA,
        describes=tuple(said),
        provenance=cites(
            GapKind.GRAPH_LEARNED_FROM_DATA,
            "program:extensions.discovery_metadata",
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
        describes=(
            _sentence(Sentence.THE_DAG_DECLARES_NO_LATENT_COMMON_CAUSE),
        ),
        # Two of these three were the only English sentences left in this
        # channel: 46 of the 48 non-Chinese alternative_paths one suite run
        # produced. A path a reader cannot act on is not an alternative.
        alternative_paths=(
            _route(Route.RUN_AN_E_VALUE),
            _route(Route.CROSS_CHECK_AN_EXPERIMENT),
            _route(Route.EMULATE_A_TARGET_TRIAL),
        ),
        provenance=cites(
            GapKind.UNMEASURED_CONFOUNDER_RISK,
            "program:confounder_pattern:no_bidirected",
        ),
    )


# Patterns that, when they appear in a variable's ``measurement`` or
# ``observability`` field, structurally signal a documented
# noisy-measurement modality. Each is matched, without regard to case,
# against the *measurement metadata* rather than free-form description
# text — the variable schema's ``measurement`` field is the contract anchor.
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
#
# What a gap quotes is the text a needle matched, as the declaration writes
# it, and not the needle. The two differ only in case, and the difference is
# a quotation of something the user never wrote: a declaration saying
# ``FFQ`` came back as ``ffq``, in the sentence and in the site the gap
# cites, and the site, looked for as written, was not there — so the answer
# was refused for a quote its producer had spelt.
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

# The fields of a declaration that say how its variable was measured, in the
# order they are read.
_HOW_IT_WAS_MEASURED: tuple[str, ...] = ("measurement", "observability")


class Measurement(language.Word, vocabulary="measurement_note",
                  between=language.BETWEEN_ITEMS):
    """What one variable's own declaration says about how it was measured.

    Each member is a statement about ONE variable, and the gap that reports
    them holds a LIST of these in a single slot — the sentence names the
    variables, and each of them is itself a small sentence.

    They used to be assembled where the list was built, and joined with a
    comma written into that code. Both halves of that were the author's
    language rather than the reader's: the Chinese report separated its
    variables with an ASCII comma, and one of the two said ``threshold:``
    in English inside a Chinese sentence. A list assembled where the reader
    is takes its punctuation from :func:`themis.language.listing` and needs
    no comma of its own.

    The quoted phrase and the cutpoint are the user's own declaration read
    back, so they arrive in whichever language it was written in.
    """

    A_FIELD_NAMES_A_KNOWN_NOISE = "a_field_names_a_known_noise", {
        "zh": "{variable}〔{role}〕({field}: 含 “{phrase}”)",
        "en": "{variable} [{role}] ({field}: contains “{phrase}”)",
    }
    A_THRESHOLD_CUT_IT_IN_TWO = "a_threshold_cut_it_in_two", {
        "zh": "{variable}（切点：“{cut}”）",
        "en": "{variable} (threshold: “{cut}”)",
    }


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
        for field_name in _HOW_IT_WAS_MEASURED:
            field_value = getattr(st, field_name, None)
            if not field_value:
                continue
            for needle in _MEASUREMENT_ERROR_PATTERNS:
                found = re.search(re.escape(needle), field_value,
                                  re.IGNORECASE)
                if found:
                    flagged.append(
                        (st.predicate, field_name, found.group(0)))
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

    def _role(pred: str) -> refusals.QueryRole:
        if pred == intervention_pred:
            return refusals.QueryRole.EXPOSURE
        if pred == target_pred:
            return refusals.QueryRole.OUTCOME
        return refusals.QueryRole.ON_PATH_COVARIATE

    noted = [
        language.state(Measurement.A_FIELD_NAMES_A_KNOWN_NOISE,
                       variable=pred, role=_role(pred), field=field,
                       phrase=quoted)
        for pred, field, quoted in flagged
    ]
    yield DataGap(
        kind=GapKind.MEASUREMENT_ERROR_CONCERN,
        describes=(_sentence(Sentence.A_VARIABLE_DECLARES_A_NOISY_MEASUREMENT,
                             variables=noted),),
        alternative_paths=(
            _route(Route.USE_EXPERIMENTAL_DATA_INSTEAD_OF_SELF_REPORT),
            _route(Route.RETEST_RELIABILITY),
            _route(Route.REPORT_ATTENUATION_RANGE),
        ),
        provenance=cites(
            GapKind.MEASUREMENT_ERROR_CONCERN,
            *(f"program:variable:{pred}:{field}:contains:{quoted}"
              for pred, field, quoted in flagged),
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
    (Phase 13/14). A caveat nonetheless, so a reader is led with the
    operationalisation rather than left to find it in a list.

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
    noted = [
        language.state(Measurement.A_THRESHOLD_CUT_IT_IN_TWO,
                       variable=pred, cut=cut)
        for pred, cut in flagged
    ]
    yield DataGap(
        kind=GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE,
        describes=(_sentence(Sentence.A_CONTINUOUS_MEASURE_WAS_CUT_IN_TWO,
                             variables=noted),),
        alternative_paths=(
            _route(Route.KEEP_THE_MEASURE_CONTINUOUS),
            _route(Route.REPORT_CUTPOINT_SENSITIVITY),
            _route(Route.STRATIFY_MORE_FINELY),
        ),
        provenance=cites(
            GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE,
            *(f"program:variable:{pred}:threshold:{cut}"
              for pred, cut in flagged),
        ),
    )


# ============================================ classifiers


def _classify_unidentifiable(
    derivation: tuple[DerivationStep, ...],
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
            describes=(_sentence(Sentence.TIAN_FOUND_A_HEDGE),),
            provenance=_step_ref(
                GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET, derivation, step),
            alternative_paths=(
                _route(Route.MEASURE_THE_CONFOUNDER_TO_BREAK_THE_HEDGE),
                _route(Route.RUN_AN_RCT_PAST_THE_HEDGE),
                _route(Route.FIND_AN_INSTRUMENT),
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
    ) -> Iterable[DataGap]: ...


#: A species is either rendered here, or declared as raised elsewhere.
_Renderer = _SpeciesRenderer | _RaisedElsewhere


def _escapes(item: InvestigationItem) -> tuple[GapRoute, ...]:
    """The ways past this item's gap that its SPECIES settles.

    Empty in two cases that look alike here and are different there: the
    species declares no route of its own (``gaps.NO_SPECIES_ESCAPE``
    holds the reason), or the item filed no species at all. The second is
    this channel's shape rather than a species the table forgot, which is
    why it is read here and not defended against in ``gaps.escapes`` — an
    unrecognised species NAME still raises, since that is a typo and not
    an absence.
    """
    return gaps.escapes(item.need) if item.need else ()


def _species_unidentifiable(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """The estimand asked for is not point identified from this graph and
    these data. Distinct from a defect in the program — this is the gap
    ``_compute_answer_tier`` reads to decide no point estimand is in
    hand, so a mediator declared off the causal path or a query atom
    absent from V must not land here.

    Ten species arrive here, and the routes come from whichever one did.
    They were three constants until #466, which made this renderer answer
    a reader whose effect would not TRANSPORT with "find an instrument" —
    an instrument in the source population transports nothing, and the
    gap it was attached to already said the failure was transport's. The
    same three reached a species whose own sentence ends "and no
    instrument route is available either"."""
    yield DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        describes=(_sentence(Sentence.THE_IDENTIFICATION_ROUTE_FAILED,
                             why=gaps.shortfall(item)),),
        alternative_paths=_escapes(item),
        provenance=_item_ref(GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET, item),
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
    offer an RCT to a program that needs one edge weight.

    The routes come from the species, and until #466 there were none at
    all on the reason this docstring used to give — "these range too
    widely for one line of advice to fit them all". That is true of the
    KIND and of no species under it, and it is the same finding as the
    trio ``_species_unidentifiable`` was shipping, arriving as silence
    rather than as wrong advice. Five of the eight still declare none,
    and now say why: for those the ask and the repair are one sentence,
    so a route would be that sentence under a second heading."""
    yield DataGap(
        kind=GapKind.MISSING_STRUCTURAL_INPUT,
        describes=(_sentence(Sentence.A_STRUCTURAL_INPUT_IS_MISSING,
                             why=gaps.shortfall(item)),),
        alternative_paths=_escapes(item) + _layer_to_drop(item),
        provenance=_item_ref(GapKind.MISSING_STRUCTURAL_INPUT, item),
    )


def _layer_to_drop(item: InvestigationItem) -> tuple:
    """The way past a joint intervention asked for beside a decomposition.

    Built here rather than declared in ``gaps.ESCAPES``, which is the split
    that table draws: its routes are the ones a species settles on its own
    and it offers them with nothing beside them, and this one says which
    layer the reader keeps and which they drop. A species that knows only
    that two were asked for knows neither, so the table's copy reached a
    reader with both names missing.

    The name it drops is the item's, put there by the one place that knows
    which other layer was declared; the name it keeps is the layer this
    build's own routing table says displaces the others, so it is read
    from there rather than decided again here.
    """
    if str(getattr(item, "need", "") or "") != str(
            gaps.Need.JOINT_WITH_MEDIATION_OR_TRANSPORT):
        return ()
    from .. import routing

    drop = dict(getattr(item, "said", None) or {}).get("drop")
    if not drop:
        return ()
    return (_route(Route.DROP_THE_OTHER_LAYER,
                   wanted=routing.route("joint_intervention").id, drop=drop),)


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
        describes=(_sentence(Sentence.THIS_UNITS_OBSERVATIONS_ARE_MISSING,
                             why=gaps.shortfall(item)),),
        provenance=_item_ref(GapKind.MISSING_UNIT_OBSERVATION, item),
    )


def _species_missing_distribution(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """A probability the evaluator looked for and theta does not hold."""
    # ``display`` is the reader's copy of the ask and goes nowhere else.
    # What shape it is, and so which sample size it wants, is read off the
    # statement the producer filed with it.
    display = _strip_parameter_prefix(item.target)
    ask = asked(item.skeleton)
    signature = _distribution_signature(ask)
    min_n, precision = _estimate_sample_size_for_distribution(ask)
    offer = _interval_offer(query_kind)
    if offer is not None:
        alt_paths = (offer,)
    else:
        # No interval channel for this question, so "accept bounds
        # instead" would be a promise nothing can keep. Said once and
        # generally: the sentence that lived here explained why an
        # observational conditional is point-estimable, and was read by
        # 222 causation gaps whose answer is an interval.
        alt_paths = (
            _route(Route.COLLECT_IT_NO_INTERVAL_FALLBACK, what=display),
        )
    yield DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        describes=(_sentence(Sentence.A_DISTRIBUTION_IS_MISSING,
                             what=display),),
        signature=signature,
        # The one species that has to say which, because for this one the
        # shape is the occasion's — see ``DATA_TYPE_TURNS_ON``. It is the
        # same fact as the signature, spelled in the reader's terms.
        required_data=GapRequiredData(
            data_type=(
                RequiredDataType.IPD
                if signature == "conditional"
                else RequiredDataType.MARGINAL
            ),
            min_sample_size=min_n,
            precision_target=precision,
        ),
        alternative_paths=alt_paths,
        provenance=_item_ref(GapKind.MISSING_DISTRIBUTION, item),
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
        describes=(_sentence(Sentence.THE_GRAPH_AND_THE_CPTS_DISAGREE,
                             what=display),),
        alternative_paths=(
            _route(Route.SUPPLY_THE_CONDITIONAL, what=display),
            _route(Route.DROP_THE_CONTRADICTING_EDGE),
        ) + tuple(o for o in (_interval_offer(query_kind),)
                  if o is not None),
        provenance=_item_ref(GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH, item),
    )


def _species_missing_assumption(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """An identification premise the kernel refuses to choose for you.

    What arrives here is not one shape: an undeclared premise
    (monotonicity), an input only an experiment can supply
    (P(Y=1|do(x)) under confounding), and declared inputs that
    contradict each other (interventional risks outside the consistency
    band, stratum weights that are not a distribution).

    "One sentence of generic advice would be wrong for most of them" was
    this renderer's reason for offering none, and it is the same true
    statement about the KIND that left ``_species_structural_input``
    silent and ``_species_unidentifiable`` wrong. Per species there is no
    such difficulty: a declaration a sample refutes has the two branches
    ``FIX_THE_*`` was written as, and a first stage that does not move is
    the one thing a stronger instrument is for. The species that still
    declines to advise is the one whose whole point is that Wald, 2SLS
    and bounds are the caller's choice among three."""
    yield DataGap(
        kind=GapKind.MISSING_ASSUMPTION,
        describes=(_sentence(Sentence.AN_IDENTIFICATION_PREMISE_IS_MISSING,
                             why=gaps.shortfall(item)),),
        alternative_paths=_escapes(item),
        provenance=_item_ref(GapKind.MISSING_ASSUMPTION, item),
    )


def _species_transport_sources_disagree(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """Two declared selection diagrams carried one quantity to two numbers.

    The only member of this vocabulary that is a falsification, so it is
    also the only one with no route: every other species names something a
    reader could go and get, and here the reader already supplied too much
    — one of the declarations has to be withdrawn, and which one is not a
    thing the kernel is in a position to decide.

    It blocks the POINT rather than the interpretation, which is the same
    thing ``_compute_answer_tier`` concludes from it: identification did
    not fail, and there is still no number, because the two the diagrams
    produce cannot both be it.
    """
    yield DataGap(
        kind=GapKind.TRANSPORT_SOURCES_DISAGREE,
        describes=(_sentence(Sentence.THE_SOURCE_DOMAINS_CONTRADICT_EACH_OTHER,
                             why=gaps.shortfall(item)),),
        provenance=_item_ref(GapKind.TRANSPORT_SOURCES_DISAGREE, item),
    )


def _loop_names(item: InvestigationItem) -> dict:
    """The four names every #450 sentence and route is written against.

    Read off the item rather than recomputed: the identification layer
    already decided which loop reaches this estimand, and deciding it a
    second time here would be a second author for the same fact.
    """
    said = dict(getattr(item, "said", None) or {})
    return {
        key: said.get(key, "")
        for key in ("left", "right", "treatment", "outcome")
    }


def _species_feedback_loop_needs_an_instrument(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """The two-equation system, with nothing to identify it yet.

    Blocking, and it names ONE thing to go and find. That is the whole
    distance travelled from what this used to be: a free-text
    ``reciprocal_causation`` note echoed back beside a number computed as
    if the second direction did not exist.

    The three routes are not ranked by preference but by what they cost.
    Resolving the loop in time is the strongest outcome and needs no
    instrument at all — it is here because a reader who has panel data
    often does not realise their loop was never instantaneous.
    """
    where = _loop_names(item)
    yield DataGap(
        kind=GapKind.MISSING_IV_CANDIDATE,
        describes=(
            _sentence(Sentence.THE_TREATMENT_IS_INSIDE_A_DECLARED_LOOP,
                      left=where["left"], right=where["right"],
                      treatment=where["treatment"],
                      outcome=where["outcome"]),
            _sentence(Sentence.ADJUSTMENT_CANNOT_REMOVE_A_FEEDBACK,
                      treatment=where["treatment"],
                      outcome=where["outcome"]),
        ),
        **_occasion(treatment=where["treatment"], outcome=where["outcome"]),
        alternative_paths=(
            _route(Route.NAME_AN_INSTRUMENT_FOR_THE_TREATMENT,
                   treatment=where["treatment"], outcome=where["outcome"]),
            _route(Route.RESOLVE_THE_LOOP_IN_TIME,
                   treatment=where["treatment"], outcome=where["outcome"]),
            _route(Route.WITHDRAW_THE_DECLARED_LOOP),
        ),
        provenance=_item_ref(GapKind.MISSING_IV_CANDIDATE, item),
    )


def _species_feedback_loop_reaches_the_estimand(
    item: InvestigationItem, query_kind: QueryKind,
) -> Iterable[DataGap]:
    """A loop on the causal path, off the shape that has a remedy.

    No instrument route is offered, and that absence is the honest part:
    the algebra an instrument rescues is about a system of TWO equations,
    and offering it here would be inventing a result. What is left to say
    is what would make the question well posed again.
    """
    where = _loop_names(item)
    yield DataGap(
        kind=GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND,
        describes=(
            _sentence(Sentence.THE_TREATMENT_IS_INSIDE_A_DECLARED_LOOP,
                      left=where["left"], right=where["right"],
                      treatment=where["treatment"],
                      outcome=where["outcome"]),
            _sentence(Sentence.A_CYCLIC_MODEL_NEED_NOT_HAVE_THIS_QUANTITY,
                      treatment=where["treatment"],
                      outcome=where["outcome"]),
        ),
        alternative_paths=(
            _route(Route.RESOLVE_THE_LOOP_IN_TIME,
                   treatment=where["treatment"], outcome=where["outcome"]),
            _route(Route.WITHDRAW_THE_DECLARED_LOOP),
        ),
        provenance=_item_ref(GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND, item),
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
    GapKind.TRANSPORT_SOURCES_DISAGREE: _species_transport_sources_disagree,
    GapKind.MISSING_IV_CANDIDATE: _species_feedback_loop_needs_an_instrument,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND:
        _species_feedback_loop_reaches_the_estimand,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: _RaisedElsewhere(
        "framing items are the action side of a gap built from "
        "framing_notes, which fire on query kinds that raise no "
        "investigation item at all — so the note, not the item, is the "
        "one source that sees every case"
    ),
})


def _item_ref(
    kind: GapKind, item: InvestigationItem,
) -> tuple[GapProvenanceRef, ...]:
    """Grounded in the ask this gap was pushed as.

    Nine species file through this channel and eight of them could have
    cited a derivation step instead, so naming the channel here is the
    occasion making its choice once rather than at each of the nine.
    :func:`themis.types.cites` holds it to what the species declares.
    """
    return cites(kind, item.target,
                 ref_kind=GapRefKind.INVESTIGATION_REQUEST)


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
}
# ``MISSING_IV_CANDIDATE`` was the second entry until #450, and it left by
# the door its own note described: the species went into MISSING_ITEM_GAPS
# and a renderer was bound for it. What made a producer possible was not
# effort but a QUESTION whose honest answer is an instrument — a treatment
# declared to be in a loop with its outcome, where no adjustment set can
# help and an instrument still can. Until such a question existed there
# was nothing for the kind to be the answer to.


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
            # Which mediators the ask is about is the ask's own statement,
            # not a substring of its rendered name: ``m in item.target``
            # matched a mediator ``bmi`` against a variable ``low_bmi``, and
            # it matched a value spelling as readily as a variable.
            ask = asked(item.skeleton)
            if ask is None:
                continue
            touched = tuple(m for m in view.mediators if m in ask.variables)
            if not touched:
                continue
            mediator = ", ".join(touched)
            min_n, precision = _estimate_sample_size_for_mediator(ask)
            yield DataGap(
                kind=GapKind.MISSING_MEDIATOR_DATA,
                describes=(_sentence(
                    Sentence
                    .THE_DECOMPOSITION_NEEDS_THE_MEDIATORS_DISTRIBUTIONS,
                    mediator=mediator, target=item.target,
                ),),
                required_data=GapRequiredData(
                    variables=touched,
                    min_sample_size=min_n,
                    precision_target=precision,
                ),
                alternative_paths=(
                    _route(Route.FALL_BACK_TO_CDE),
                    _route(Route.FALL_BACK_TO_THE_TOTAL_EFFECT),
                ),
                provenance=cites(
                    GapKind.MISSING_MEDIATOR_DATA,
                    item.target,
                    ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                ),
            )


def _classify_transport_target_distribution(
    extensions: dict, derivation: tuple[DerivationStep, ...],
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

    Both are emitted per TRANSPORTING SOURCE DOMAIN, because each domain
    adjusts for what IT was declared to differ in: two sources shifting
    different covariates need different Z, so a reader deciding which
    source to go and get is choosing between two different asks rather
    than reading one (#326)."""
    block = extensions.get(blocks.Block.TRANSPORT_IDENTIFICATION)
    if not block:
        return
    target_pop = block.get("target_population")
    # The chain carries one transport_formula step per TRANSPORTING
    # source, in source order; the block lists every source, transporting
    # or not. So the k-th such step belongs to the k-th transporting
    # source, and that correspondence is the one this pairs them by. The
    # position in the block is not it: a blocked source ahead of a
    # transporting one shifts every later index, and the name this used
    # to rebuild from the block's index then named a step that was not
    # there — or, once names are places, one belonging to another route.
    formulas = [s for s in derivation if s.rule == "transport_formula"]
    transporting = 0
    for route in block.get("sources") or ():
        if not isinstance(route, dict) or not route.get("transportable"):
            continue
        place = transporting
        transporting += 1
        # A route with nothing to stratify on asks for nothing, and the
        # trivial case is exactly that: a target population declared with
        # no selection node transports by doing nothing, so the chain took
        # another route entirely and carries no transport step. Counted
        # anyway — the place a later route's step sits depends on this one
        # having been here, not on whether it raised anything.
        if not (route.get("adjustment_set") or []):
            continue
        if place >= len(formulas):
            raise ValueError(
                f"a transporting source is about to ask for data and the "
                f"chain has no transport_formula step at place {place} to "
                f"ground the ask in (it has {len(formulas)})")
        yield from _transport_source_data_needs(
            route, derivation, formulas[place], target_pop=target_pop)


def _transport_source_data_needs(
    route: dict, derivation: tuple[DerivationStep, ...],
    step: DerivationStep, *, target_pop,
) -> Iterable[DataGap]:
    """The two asks one transporting source domain leaves open.

    Reached only for a route that has something to stratify on; the caller
    decides that, because it also has to keep counting the routes that do
    not, and one condition read in two places is one condition too many.
    """
    adjustment_set = route.get("adjustment_set", []) or []
    source_pop = route.get("source_population")
    z_names = ", ".join(_atom_label(a) for a in adjustment_set)
    treatment, outcome = _transport_treatment_outcome(route)

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
        describes=(_sentence(
            Sentence.THE_TARGET_POPULATIONS_COVARIATE_DISTRIBUTION_IS_MISSING,
            population=target_pop or Unnamed.POPULATION,
            variables=z_names,
        ),),
        required_data=GapRequiredData(
            population=target_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=target_n,
            precision_target=target_precision,
        ),
        alternative_paths=(
            _route(Route.ACCEPT_THE_SOURCE_ATE),
        ),
        provenance=_step_ref(
            GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN, derivation, step),
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
        describes=(_sentence(
            Sentence.THE_SOURCE_POPULATIONS_STRATIFIED_CONDITIONAL_IS_MISSING,
            population=source_pop or Unnamed.POPULATION,
            formula=formula_repr,
        ),),
        required_data=GapRequiredData(
            population=source_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=source_n,
            precision_target=source_precision,
        ),
        alternative_paths=(
            _route(Route.FIND_THE_RCT_IPD),
            _route(Route.FIND_A_SUBGROUP_ANALYSIS),
            _route(Route.FIND_A_MATCHED_RCT),
        ),
        provenance=_step_ref(
            GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN, derivation, step),
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


class Window(language.Word, vocabulary="time_window",
             between=language.BETWEEN_STATEMENTS):
    """When the measurements a gap asks for would have to be taken.

    One member, and a vocabulary all the same: what the field holds is a
    statement about this study rather than a value, and a field holding one
    statement is the shape that lets a second arrive without the first
    becoming prose again.
    """

    BASELINE_AND_TWO_FOLLOW_UPS = "baseline_and_two_follow_ups", {
        "zh": "建议 baseline + 4w + 12w（视实际研究问题调整）",
        "en": "baseline + 4w + 12w is a reasonable start (adjust to the "
              "actual research question)",
    }


class Sutva(language.Word, vocabulary="sutva_concern",
            between=language.BETWEEN_STATEMENTS):
    """One way this design could break the assumption that a unit's outcome
    depends only on its own assignment."""

    UNITS_MUST_NOT_COORDINATE = "units_must_not_coordinate", {
        "zh": "受试者之间不能讨论 / 协调干预（违反 SUTVA）",
        "en": "subjects must not discuss or coordinate the intervention "
              "between themselves (that violates SUTVA)",
    }
    SPILLOVER_MUST_BE_RECORDED = "spillover_must_be_recorded", {
        "zh": "若有溢出 / 同侪效应，需登记并在分析中纳入",
        "en": "where spillover or peer effects exist, record them and carry "
              "them into the analysis",
    }


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

    # If confounders_required is empty AND the
    # user's program has no extra-variable nodes beyond X / Y, the DAG is
    # bare X→Y. This is unusual for observational dose-response work
    # (Whelton 2002 / AHA 2013 / Cornelissen 2013 all flag baseline
    # outcome + demographic covariates as standard). Append a generic
    # hint so the renderer prompts the user to confirm minimality is
    # intentional. Avoids hardcoding domain-specific covariate names.
    said = [_sentence(Sentence.THE_QUESTION_ASKS_FOR_A_DOSE_RESPONSE_CURVE,
                      intervention=intervention_label, target=target_label)]
    if not confounders and _program_has_no_declared_confounders(program, stmt):
        said.append(
            _sentence(Sentence.THE_DAG_DECLARES_NO_CONFOUNDER_FOR_THE_CURVE))

    yield DataGap(
        kind=GapKind.DOSE_RESPONSE_DATA_REQUIRED,
        describes=tuple(said),
        required_data=GapRequiredData(
            sampling_point_count=K,
            min_sample_size=total,
            precision_target=language.state(
                Precision.TRACE_A_DOSE_RESPONSE_CURVE,
                points=K, per_point=n_per_point,
            ),
            confounders_required=tuple(confounders),
            time_window=language.state(Window.BASELINE_AND_TWO_FOLLOW_UPS),
            sutva_concerns=(
                language.state(Sutva.UNITS_MUST_NOT_COORDINATE),
                language.state(Sutva.SPILLOVER_MUST_BE_RECORDED),
            ),
        ),
        alternative_paths=(
            _route(Route.FALL_BACK_TO_A_BINARY_CONTRAST),
        ),
        provenance=cites(
            GapKind.DOSE_RESPONSE_DATA_REQUIRED,
            "program:extensions.ambiguities.dose_response_query",
        ),
    )


def _classify_collider_conditioning_opens_backdoor(
    *,
    program,
    stmt,
    graph=None,
    bidirected=None,
) -> Iterable[DataGap]:
    """Selection bias, the explicit-conditioning shape.

    EffectQuery's ``given`` (conditioning subgroup) contains a node W whose
    conditioning opens a path between the intervention X and the target Y.
    Per Pearl d-separation, conditioning on W (a collider on the
    X→...→W←...←Y path) OPENS that path rather than blocks it; the
    conditional effect estimate is NOT the conditional intervention effect
    on the requested subgroup — it carries collider-induced bias.

    Detection rule: :func:`conditioned_collider_opens_path` on the ground
    graph the question was answered on, with its ground bidirected edges,
    between the intervention atom and the target atom, conditioning on every
    given atom and every atom an observation restricts the sample to: the
    estimate is taken inside that sample, so those are conditioned on too,
    and one estimate has one conditioning set -- the selection caveat below
    reads the same one. An m-separation test rather than a directed-ancestor one, so
    it sees M-bias colliders whose arms are latent common causes (What If
    Fig 7.4) and colliders activated through a conditioned descendant
    (Fig 8.2), not only the direct X->W<-Y shape (Fig 8.1). W is passed over
    only when it is the intervention atom or the target atom.

    This was read on the predicates, where ``x`` a step back and ``x`` now
    are one node. Over them a collider was found where no ground path ran
    through the conditioned atom, and a conditioned ``x`` now was passed
    over as the intervention itself when it was the collider.

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

    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime.structural_solver import (
        bidirected_from_ground,
        conditioned_collider_opens_path,
    )

    if graph is None or bidirected is None:
        ground = instantiate(program)
        if graph is None:
            graph = project(ground)
        if bidirected is None:
            bidirected = bidirected_from_ground(ground)
    x, y = q.intervention.atom, q.target.atom
    intervention_pred, target_pred = x.predicate, y.predicate
    conditioning = frozenset(getattr(item, "atom", item) for item in given) | {
        st.atom for st in getattr(program, "statements", ())
        if isinstance(st, ObservationStatement)}

    for given_item in given:
        w = getattr(given_item, "atom", given_item)
        if w in (x, y):
            # Conditioning on the intervention or target itself is a
            # different problem (degenerate query), not collider opening.
            continue
        w_pred = w.predicate
        if conditioned_collider_opens_path(
            graph, bidirected, x, y, conditioning, w,
        ):
            yield DataGap(
                kind=GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR,
                describes=(_sentence(
                    Sentence.THE_CONDITIONING_NODE_IS_A_COLLIDER,
                    collider=w_pred,
                    intervention=intervention_pred, target=target_pred,
                ),),
                **_occasion(collider=w_pred),
                alternative_paths=(
                    _route(Route.ASK_THE_MARGINAL_EFFECT,
                                  target=target_pred,
                                  intervention=intervention_pred),
                    _route(Route.MAYBE_IT_IS_NOT_A_COLLIDER,
                                  collider=w_pred),
                    _route(Route.TREAT_THE_COLLIDER_AS_A_TARGET_POPULATION,
                                  collider=w_pred),
                ),
                provenance=raised_by_ref(
                    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR,
                    f"{w_pred}|{intervention_pred}->{target_pred}",
                ),
            )


def _classify_selection_on_collider_opens_path(
    *,
    program,
    stmt,
    graph=None,
    bidirected=None,
) -> Iterable[DataGap]:
    """Selection bias, the implicit-sample-restriction shape.

    Distinct from ``_classify_collider_conditioning_opens_backdoor``
    which fires on **explicit** conditioning via ``EffectQuery.given``.
    This classifier fires on **implicit sample restriction** encoded as
    an ``ObservationStatement(W, value)``: the data the user is about to
    estimate from is restricted to subjects with W=value, and restricting
    to W opens a path between intervention X and target Y. Restricting a
    sample IS conditioning on it, so the canonical X→…→W←…←Y and every
    shape the explicit-conditioning caveat sees -- arms that are latent
    common causes, W a descendant of the collider -- put selection-induced
    bias into the estimate from the restricted sample.

    Canonical case: Hernán-Hernández-Díaz-Robins 2004 *Epidemiology*
    15:615 "A Structural Approach to Selection Bias" — Figure 3-style
    HIV/AZT → AIDS-death cohort where eligibility for follow-up
    (W = "selected") is itself caused by both treatment and outcome.
    The "structural approach" framing is exactly: name the W node,
    surface that the sample restriction is conditioning on a collider.

    Detection rule: each ground observation atom W for which
    :func:`conditioned_collider_opens_path` holds on the ground graph with
    its bidirected edges, conditioning on every observed atom and every
    given atom -- the question the explicit-conditioning caveat asks, of
    the same conditioning set. It asked whether W is a directed common
    effect instead, and so said nothing of ``x <-> w <-> y`` restricted on
    ``w`` while the same ``w`` in ``given`` was a collider. Selection
    recovery still asks the directed question: its criterion is written for
    selection nodes with no latent parents, which is a limit of what it
    can recover and not of what biases the estimate.

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

    from ..runtime.graph_projection import project
    from ..runtime.instantiation import instantiate
    from ..runtime.structural_solver import (
        bidirected_from_ground,
        conditioned_collider_opens_path,
    )

    ground = instantiate(program)
    if graph is None:
        graph = project(ground)
    if bidirected is None:
        bidirected = bidirected_from_ground(ground)
    x, y = q.intervention.atom, q.target.atom
    intervention_pred, target_pred = x.predicate, y.predicate
    observed = [st for st in ground if isinstance(st, ObservationStatement)]
    conditioning = frozenset(st.atom for st in observed) | {
        getattr(item, "atom", item) for item in q.given}

    for st in observed:
        w_pred, w_value = st.atom.predicate, st.value
        if conditioned_collider_opens_path(
                graph, bidirected, x, y, conditioning, st.atom):
            yield DataGap(
                kind=GapKind.SELECTION_ON_COLLIDER_OPENS_PATH,
                describes=(_sentence(
                    Sentence.THE_SAMPLE_IS_RESTRICTED_ON_A_COLLIDER,
                    collider=w_pred, value=w_value,
                    intervention=intervention_pred, target=target_pred,
                ),),
                **_occasion(collider=w_pred, value=w_value),
                alternative_paths=(
                    _route(Route.REWEIGHT_FOR_SELECTION,
                                  collider=w_pred, value=w_value),
                    _route(Route.MAYBE_IT_IS_NOT_A_COMMON_EFFECT,
                                  collider=w_pred,
                                  intervention=intervention_pred,
                                  target=target_pred),
                    _route(Route.DECLARE_IT_A_SELECTION_NODE,
                                  collider=w_pred),
                ),
                provenance=raised_by_ref(
                    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH,
                    f"{w_pred}|{intervention_pred}->{target_pred}",
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
        said = Sentence.THE_INTERVENTION_SAYS_NEITHER_STATE_NOR_EVENT
        check = "intervention_state_inferred"
    else:
        said = Sentence.THE_INTERVENTION_IS_A_STATE_WITH_NO_TIME_WINDOW
        check = "intervention_state_without_time_window"
    yield DataGap(
        kind=GapKind.ILL_DEFINED_INTERVENTION_VERSIONS,
        describes=(_sentence(said, intervention=intervention_pred),),
        **_occasion(intervention=intervention_pred),
        alternative_paths=(
            _route(Route.DECLARE_THE_INTERVENTION_AN_EVENT,
                          intervention=intervention_pred),
            _route(Route.SPLIT_THE_INTERVENTION_IN_TWO,
                          intervention=intervention_pred),
            _route(Route.USE_EXPERIMENTAL_DATA_FOR_THE_VERSIONS),
            _route(Route.ACCEPT_THE_MIXED_ESTIMAND),
        ),
        provenance=raised_by_ref(
            GapKind.ILL_DEFINED_INTERVENTION_VERSIONS,
            intervention_pred, check=check,
        ),
    )


# ``_DISPLACED_BECAUSE`` moved to :data:`themis.gaps.DISPLACED_BECAUSE` in
# #617. It is a table of SENTENCES, and which statements a species may make
# is declared there now — leaving it here would have forced that
# declaration to list its eight members a second time.


def _classify_unattempted_layer_dispatch_conflict(
    *,
    dispatch,
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
        yield _dispatch_conflict_gap(winner, skipped, won, lost)


#: One sentence for both directions — which layer is wanted and which one
#: goes is what the two call sites differ in, not what is being said.


def _dispatch_conflict_gap(
    winner, skipped, won: str, lost: str,
) -> DataGap:
    return DataGap(
        kind=GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
        describes=(
            _sentence(Sentence.ONLY_ONE_DECLARED_LAYER_WAS_RUN,
                      won=won, lost=lost,
                      winner=winner.id, skipped=skipped.id),
            _sentence(gaps.DISPLACED_BECAUSE[winner.id, skipped.id]),
            _sentence(Sentence.THE_RESULT_REFLECTS_ONE_LAYER_ONLY,
                      winner=winner.id, skipped=skipped.id),
        ),
        **_occasion(won=won, lost=lost),
        alternative_paths=(
            _route(Route.DROP_THE_OTHER_LAYER,
                          wanted=winner.id, drop=lost),
            _route(Route.DROP_THE_OTHER_LAYER,
                          wanted=skipped.id, drop=won),
        ),
        provenance=cites(
            GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
            f"query:dispatch_conflict:{winner.id}_dispatched_"
                    f"{skipped.id}_skipped",
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


def _query_target_label(stmt) -> "str | Unnamed":
    """Best-effort label for the query's outcome variable.

    Real-test caught: cause queries (with `from`/`to`) used to fall
    through to the literal string ``<target>`` because only effect
    queries' `target.atom` shape was handled. Now also reads `to` for
    cause queries and falls back to a generic phrase instead of an
    angle-bracketed placeholder a renderer would surface verbatim.

    The phrase says the question names no outcome, and is read that way:
    a proximal effect names its own ``outcome``, and falling past it
    handed a reader the phrase where the question had the name. A
    counterfactual names its own ``counterfactual_target`` and was the
    same omission one class over -- found because the verifier's copy of
    this list learnt that spelling and the two stopped agreeing.
    """
    q = getattr(stmt, "query", None)
    if q is None:
        return Unnamed.OUTCOME
    target = getattr(q, "target", None)
    if target is not None:
        atom = getattr(target, "atom", None) or target
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # A proximal effect calls it ``outcome``; a counterfactual calls it
    # ``counterfactual_target``. CauseQuery exposes its
    # source/destination as ``from_atom`` / ``to_atom`` (avoiding Python's
    # ``from`` keyword); AssocQuery uses left/right.
    for attr in ("outcome", "counterfactual_target", "to_atom", "to",
                 "right"):
        found = getattr(q, attr, None)
        if found is not None:
            # As the branch above does: a spelling may name the atom or
            # the field that holds one, and which it is belongs to the
            # query class rather than to this list.
            atom = getattr(found, "atom", None) or found
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return Unnamed.OUTCOME


def _query_intervention_label(stmt) -> "str | Unnamed":
    """Best-effort label for the query's treatment variable. See
    ``_query_target_label`` for the cause-query motivation, and for what
    the phrase it falls back to says."""
    q = getattr(stmt, "query", None)
    if q is None:
        return Unnamed.INTERVENTION
    intv = getattr(q, "intervention", None)
    if intv is not None:
        atom = getattr(intv, "atom", None) or intv
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # A proximal effect calls it ``treatment``; a counterfactual calls it
    # ``counterfactual_intervention``. CauseQuery exposes its source as
    # ``from_atom``; AssocQuery uses ``left``. ``from`` is a Python
    # keyword so it never appears as an attribute name on typed objects,
    # but check it for dict-shaped callers anyway.
    for attr in ("treatment", "counterfactual_intervention", "from_atom",
                 "from_", "from", "left"):
        found = getattr(q, attr, None)
        if found is not None:
            # As the branch above does: a spelling may name the atom or
            # the field that holds one, and which it is belongs to the
            # query class rather than to this list.
            atom = getattr(found, "atom", None) or found
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return Unnamed.INTERVENTION


def _classify_ambiguous_variable(
    framing_notes: tuple[FramingNote, ...],
    stmt=None,
) -> Iterable[DataGap]:
    """One gap per note. ``stmt`` is no longer read.

    It used to decide a severity here: IMPORTANT for a predicate the query
    references, INFORMATIONAL for one declared in the program and left off
    the query path. The second was unreachable, and had been since the
    check was written — a framing note is MADE from the predicates the
    query names, so there is no off-query note for the quiet branch to be
    about. What kept it looking alive was that the two sides read the
    query through two different functions; they read one now, and the
    severity belongs to the species like every other.
    """
    for note in framing_notes:
        missing_str = ", ".join(note.missing)
        yield DataGap(
            kind=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
            describes=(_sentence(
                Sentence.THE_VARIABLE_HAS_NO_OPERATIONAL_DEFINITION,
                variable=note.predicate, missing=missing_str,
            ),),
            provenance=cites(
                GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
                note.predicate,
            ),
        )


# ============================================ helpers


class Ask(NamedTuple):
    """A missing probability, as the ask itself states it.

    Read off the statement filed with the gap — the same paste-ready
    ``probabilityStatement`` the reader is handed to fill in — and never
    off the rendered ``P(...)``. The rendering is the reader's copy: what
    it spells a value with is a question about language, so a branch taken
    by reading it is a kernel decision that moves when the wording does,
    and moves silently, because a substring that finds nothing looks
    exactly like a fact that is not there.

    ``measured`` is ``None`` for a target value that is neither a truth
    value nor a number — a categorical level, which no formula here
    sizes. The other two fields are still known in that case, which is
    why this is one reading and not three: what the ask is about and what
    stratum it wants do not depend on what its answer is measured on.
    """

    measured: "sample_size.Measured | None"
    given: int
    variables: frozenset[str]

    @property
    def conditional(self) -> bool:
        return self.given > 0


def asked(statement: object) -> "Ask | None":
    """What the ask states about itself, or ``None`` when it stated
    nothing — a shortfall with no probability behind it.

    ``None`` is not the same answer as an ``Ask`` whose ``measured`` is
    unset: one says nothing was stated, the other that what was stated is
    not something a formula here covers.
    """
    if not isinstance(statement, dict):
        return None
    target = statement.get("target")
    if not isinstance(target, dict):
        return None
    stated = statement.get("given")
    given: list = stated if isinstance(stated, list) else []
    value = target.get("value")
    if isinstance(value, bool):
        measured: "sample_size.Measured | None" = (
            sample_size.Measured.PROPORTION)
    elif isinstance(value, (int, float)):
        measured = sample_size.Measured.MEAN
    else:
        measured = None
    return Ask(
        measured,
        len(given),
        frozenset(
            p for p in
            (_stated_predicate(target),)
            + tuple(_stated_predicate(g) for g in given)
            if p is not None
        ),
    )


def _stated_predicate(part: object) -> str | None:
    """The predicate one half of a statement names, or ``None``."""
    if not isinstance(part, dict):
        return None
    atom = part.get("atom")
    if not isinstance(atom, dict):
        return None
    name = atom.get("predicate")
    return name if isinstance(name, str) else None


def _distribution_signature(ask: "Ask | None") -> str | None:
    """Which shape of distribution the ask is: conditional when it
    conditions on anything, marginal when it does not.

    ``None`` when the gap was filed without a statement — the signature is
    informational and the gap is the same blocking shape either way, and
    a guess here would reach an adapter as a claim about where to go
    looking. There is no ``joint``: a probability ask names one target,
    so no producer can state one. The rehydration table keeps a row for
    it, for envelopes written before that was true.
    """
    if ask is None:
        return None
    return "conditional" if ask.conditional else "marginal"


def _estimate_sample_size_for_mediator(
    ask: "Ask | None",
) -> tuple[int | None, language.Statement | None]:
    """Mediation NDE/NIE sample size: only for an ask on a proportion,
    which is the range of the constants it returns."""
    from .sample_size import Measured, estimate_min_n_mediation_nde_nie

    if ask is None or ask.measured is not Measured.PROPORTION:
        return None, None
    return estimate_min_n_mediation_nde_nie()


def _estimate_sample_size_for_transport_target(
    n_strata: int,
) -> tuple[int | None, language.Statement | None]:
    """Target-population P*(Z): single-proportion per stratum."""
    from .sample_size import estimate_min_n_transport_target_marginal

    return estimate_min_n_transport_target_marginal(n_strata=n_strata)


def _estimate_sample_size_for_transport_source(
    n_strata: int,
) -> tuple[int | None, language.Statement | None]:
    """Source-population stratified P(Y|do(X), Z)."""
    from .sample_size import estimate_min_n_transport_source_conditional

    return estimate_min_n_transport_source_conditional(n_strata=n_strata)


def _estimate_sample_size_for_distribution(
    ask: "Ask | None",
) -> tuple[int | None, language.Statement | None]:
    """Map a missing-distribution gap to (min_n, precision_target).

    Routes on the two facts the ask states — what its target value is
    measured on, and whether it conditions on anything:

    - a proportion: conditional → two-arm Cohen's h, marginal → single
      proportion
    - a mean: conditional → two-arm Cohen's d, marginal → ``None``
      (single-mean precision needs a σ nothing here holds)
    - a value that is neither, or an ask that stated no shape:
      ``(None, None)`` — better silent than wrong.
    """
    from .sample_size import Measured, estimate_min_n_two_arm_continuous

    if ask is None:
        return None, None
    if ask.measured is Measured.PROPORTION:
        if ask.conditional:
            return estimate_min_n_two_arm_binary()
        return estimate_min_n_single_proportion()
    if ask.measured is Measured.MEAN:
        if ask.conditional:
            return estimate_min_n_two_arm_continuous()
        return None, None
    return None, None


def _step_ref(
    kind: GapKind, derivation: tuple[DerivationStep, ...],
    step: DerivationStep,
) -> tuple[GapProvenanceRef, ...]:
    """Grounded in the chain — the other answer to the same question.

    A step is cited by the name the ANSWER gives it, and that name is
    where the step sits, so this has to be handed the chain as well as
    the step. Naming it any other way means writing down a second copy of
    something the answer computes, and the copy then has to keep agreeing
    with the original for as long as both exist.
    """
    for index, other in enumerate(derivation):
        if other is step:
            return cites(kind, step_name(index),
                         ref_kind=GapRefKind.DERIVATION_STEP)
    raise ValueError(
        f"a gap cites a {step.rule!r} step that is not in the chain this "
        f"report was built from; a citation names a place, and there is "
        f"no place to name")


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
        describes=tuple(
            entry for entry in (
                gaps.sentence_entry(e) for e in d.get("describes") or ()
            ) if entry is not None
        ),
        blocks=GapBlocks(d["blocks"]),
        # The one place the raw constructor is right: this is not
        # authoring a ref, it is reading one back, and a check ref has to
        # survive the round trip — which cites() refuses to build, since
        # the check's name is RAISED_BY's to supply. What the species
        # allows is still enforced one frame up, by DataGap itself.
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
        said=dict(d.get("said") or {}),
        words=dict(d.get("words") or {}),
        alternative_paths=tuple(
            r for r in (
                _route_entry(a) for a in (d.get("alternative_paths") or ())
            ) if r is not None
        ),
    )
