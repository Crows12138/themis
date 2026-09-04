"""Phase 10 §10.4 — independent verification of DataGapReport.

Three rules audit a generated DataGapReport for honesty:

- **T10-1 ``data_gap_provenance_check``** — every ref in every gap's
  provenance array must point at a real artifact present in the result
  envelope (derivation_step / investigation_request / framing_note /
  verifier_check).
- **T10-2 ``data_gap_completeness_check``** — every upstream failure
  signal that the schema can detect (failed derivation step / parameter
  investigation / framing note) must be covered by at least one gap.
- **T10-3 ``data_gap_kind_consistency_check``** — each gap's ``kind`` must
  be coherent with the upstream signal it cites in provenance (e.g. a
  gap labelled ``unidentifiable_no_admissible_set`` cited as
  ``derivation_step`` must reference a step that actually represents a
  structural failure, not a successful identification).

**Independence pin:** This module MUST NOT import from
``themis.output.data_gap_report`` or any generator-side module. The audit
is a re-implementation of the failure / coverage logic from scratch so
that bugs in the generator cannot mask themselves in the verifier. A
test in ``tests/test_verifier/test_data_gap_rules.py`` line-scans this
file to enforce the rule.

Reads only from the JSON envelope (dicts), not from typed dataclasses,
so the audit also catches serialization-layer bugs.
"""
from __future__ import annotations

from typing import Any, Mapping

from .errors import VerificationError
from .program_copy_rules import query_of


# ============================================ failure detection
#
# The verifier maintains its OWN list of rule names that indicate
# structural failure. It used to be pointed out that this was not
# imported from themis.output.data_gap_report, because bugs in one must
# not hide bugs in the other. There is nothing there to import any more:
# the kernel writes only steps that succeeded, so the producer's copy was
# removed and this one is the last.
#
# It stays because the two sides read different things. The producer
# reads a derivation the kernel just built; this reads one somebody else
# submitted, which may claim a failure no producer would write — and
# recognising that claim is the precondition for checking it.
_VERIFIER_FAILURE_RULE_NAMES: frozenset[str] = frozenset({
    "unidentifiable_via_backdoor",
    "unidentifiable_via_front_door",
    "unidentifiable_via_iv",
    "unidentifiable_via_mediation",
    "unidentifiable_via_transport",
})


def _step_failed(step: dict) -> bool:
    """A step represents structural failure when (a) it explicitly carries
    success=False or (b) its rule name is in the verifier's independent
    failure list."""
    if step.get("success") is False:
        return True
    return step.get("rule") in _VERIFIER_FAILURE_RULE_NAMES


def _step_id_or_rule(step: dict) -> str:
    """Stable identifier for matching provenance refs back to a step."""
    sid = step.get("step_id")
    if sid:
        return sid
    return step.get("rule", "")


# ============================================ T10-1 provenance resolution


def _verify_t10_1_provenance(
    report: dict,
    *,
    derivation_steps: list[dict],
    investigation_requests: list[dict],
    framing_notes: list[dict],
) -> None:
    """T10-1: every gap.provenance[i].ref_id must resolve to a real
    artifact in the result envelope."""
    derivation_ids = set()
    for step in derivation_steps:
        derivation_ids.add(_step_id_or_rule(step))
        # Some generators may also use the rule name; accept that too.
        rule = step.get("rule")
        if rule:
            derivation_ids.add(rule)

    investigation_ids: set[str] = set()
    for req in investigation_requests:
        target = req.get("target")
        if target:
            investigation_ids.add(target)
        for item in req.get("items", []) or []:
            it_target = item.get("target")
            if it_target:
                investigation_ids.add(it_target)

    framing_ids = {n.get("predicate") for n in framing_notes if n.get("predicate")}

    for gap_index, gap in enumerate(report.get("gaps", [])):
        for ref_index, ref in enumerate(gap.get("provenance", []) or []):
            ref_kind = ref.get("ref_kind")
            ref_id = ref.get("ref_id")
            if ref_kind == "derivation_step":
                if ref_id not in derivation_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites derivation_step={ref_id!r} which does not "
                        f"appear in the derivation chain",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "investigation_request":
                if ref_id not in investigation_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites investigation_request={ref_id!r} which does "
                        f"not appear in result.investigation_requests",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "framing_note":
                if ref_id not in framing_ids:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites framing_note={ref_id!r} which does not "
                        f"appear in result.framing_notes",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "verifier_check":
                # Free-form: accept any non-empty string. The generator
                # uses these for status-derived gaps where there is no
                # specific upstream artifact to point at.
                if not isinstance(ref_id, str) or not ref_id:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"verifier_check ref_id must be a non-empty string",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            else:
                raise VerificationError(
                    f"T10-1: gap[{gap_index}].provenance[{ref_index}] has "
                    f"unknown ref_kind={ref_kind!r}",
                    step_index=None, rule="data_gap_provenance_check",
                )


# ============================================ T10-2 completeness


# Every investigation group must be cited, with one exemption: framing
# items reach the report as ambiguous_variable_definition gaps carrying a
# framing_note ref, so check 3 already holds them and demanding a second
# citation under a different ref kind would reject correct reports.
#
# Written as an exemption rather than an inclusion list on purpose. The
# inclusion form names the groups that are covered and lets an unnamed
# group pass in silence, which is how this rule sat green while first the
# assumption channel and then the structure and observation channels
# emitted nothing at all.
_UNCITED_GROUPS: frozenset[str] = frozenset({"framing"})


def _verify_t10_2_completeness(
    report: dict,
    *,
    derivation_steps: list[dict],
    investigation_requests: list[dict],
    framing_notes: list[dict],
) -> None:
    """T10-2: every upstream failure signal must be covered by at least
    one gap somewhere in the report.

    Coverage = some gap has a provenance ref pointing back to that
    signal. We check three signal classes (the ones the schema makes
    detectable from the JSON envelope):

    1. Failed derivation steps → at least one gap with provenance
       derivation_step:<step_id_or_rule>.
    2. Investigation_request items → at least one gap with provenance
       investigation_request:<item.target>, for every group except the
       framing exemption noted at ``_UNCITED_GROUPS``.
    3. Framing notes → at least one gap with provenance
       framing_note:<predicate>.

    Check 2 holds the whole channel because an item is the kernel saying
    what it needs, in the one place it says it. Structure items in
    particular carry no derivation step behind them — their producers
    return before any step is recorded — so an uncited one leaves the
    report claiming a clean bill of health for a query that returned
    nothing.
    """
    gaps = report.get("gaps", [])
    # Build inverted index: signal_id → set of gap indices that cite it.
    cited_derivation: set[str] = set()
    cited_investigation: set[str] = set()
    cited_framing: set[str] = set()
    for gap in gaps:
        for ref in gap.get("provenance", []) or []:
            kind = ref.get("ref_kind")
            rid = ref.get("ref_id")
            if kind == "derivation_step":
                cited_derivation.add(rid)
            elif kind == "investigation_request":
                cited_investigation.add(rid)
            elif kind == "framing_note":
                cited_framing.add(rid)

    # 1. Failed derivation steps must be cited.
    for step in derivation_steps:
        if not _step_failed(step):
            continue
        sid = _step_id_or_rule(step)
        rule = step.get("rule", "")
        # Accept either the step_id form OR the bare rule name as
        # citation — the generator may pick either.
        if sid not in cited_derivation and rule not in cited_derivation:
            raise VerificationError(
                f"T10-2: failed derivation step rule={rule!r} "
                f"step_id={sid!r} has no corresponding gap in the report",
                step_index=None, rule="data_gap_completeness_check",
            )

    # 2. Investigation items must be cited, framing aside.
    for req in investigation_requests:
        group = req.get("group")
        if group in _UNCITED_GROUPS:
            continue
        for item in req.get("items", []) or []:
            target = item.get("target")
            if not target:
                # Not "nothing to check". This loop IS the coverage
                # demand, and a falsy target let an item opt out of it by
                # naming nothing — the exemption above, reached without
                # being on the list. Measured: emptying one target was
                # accepted on five of the six answer shapes that carry a
                # citable item.
                raise VerificationError(
                    f"T10-2: {group} investigation_request carries an "
                    f"item with target={target!r}; an item with no name "
                    f"cannot be cited by a gap, and this check is what "
                    f"says it must be",
                    step_index=None, rule="data_gap_completeness_check",
                )
            if target not in cited_investigation:
                raise VerificationError(
                    f"T10-2: {group} investigation_request "
                    f"target={target!r} has no corresponding gap in the report",
                    step_index=None, rule="data_gap_completeness_check",
                )

    # 3. Framing notes must be cited.
    for note in framing_notes:
        pred = note.get("predicate")
        if not pred:
            continue
        if pred not in cited_framing:
            raise VerificationError(
                f"T10-2: framing_note predicate={pred!r} has no "
                f"corresponding gap in the report",
                step_index=None, rule="data_gap_completeness_check",
            )


# ============================================ T10-3 kind consistency


# What gap_kinds are valid for each provenance ref_kind. A gap whose
# provenance does not contain at least one ref of an acceptable kind for
# its declared gap_kind is flagged as an inconsistency.
_KIND_ACCEPTS_REF: dict[str, frozenset[str]] = {
    "unidentifiable_no_admissible_set": frozenset(
        {"derivation_step", "investigation_request"}
    ),
    "missing_distribution": frozenset(
        {"investigation_request", "derivation_step"}
    ),
    "missing_population_distribution": frozenset(
        {"derivation_step", "investigation_request", "verifier_check"}
    ),
    "missing_assumption": frozenset(
        {"investigation_request", "verifier_check", "derivation_step"}
    ),
    # Unit-level reading an SCM counterfactual needs for abduction, and
    # the residual for any structural requirement no more specific
    # classifier claimed. Both are raised only through the
    # missing-information channel — the producers return before any
    # derivation step is recorded — so the investigation_request ref is
    # the only citation available.
    "missing_unit_observation": frozenset({"investigation_request"}),
    "missing_structural_input": frozenset({"investigation_request"}),
    "missing_iv_candidate": frozenset(
        {"derivation_step", "investigation_request"}
    ),
    "missing_mediator_data": frozenset(
        {"investigation_request", "derivation_step"}
    ),
    "transport_target_distribution_unknown": frozenset(
        {"derivation_step", "investigation_request"}
    ),
    "transport_source_conditional_unknown": frozenset(
        {"derivation_step", "investigation_request"}
    ),
    # Two declared source domains carried one target quantity to two
    # numbers. Raised in the kernel as an assumption-group item, so the
    # provenance is the request that item was pushed as — the same channel
    # every other kernel-raised species uses, and not a verifier_check:
    # this falsification is found while identifying, not while estimating.
    "transport_sources_disagree": frozenset({"investigation_request"}),
    "ambiguous_variable_definition": frozenset({"framing_note"}),
    # Phase 13: dose-response data spec — provenance is a verifier_check
    # ref pointing at program.extensions.ambiguities.dose_response_query
    # (no derivation step exists for this kind; the gap is triggered by
    # a program-level ambiguity, not a failed derivation rule).
    "dose_response_data_required": frozenset({"verifier_check"}),
    # Phase 11.x §C: provenance is a verifier_check ref pointing at the
    # specific cause-statement annotation that flagged the path edge as
    # an LLM hypothesis. Reference shape: program:cause:<from>-><to>:
    # annotations.source.
    "unverified_proposal_edge_on_query_path": frozenset({"verifier_check"}),
    # Must-disclose caveat kinds — provenance points at the result-side
    # extension or bounds_results the caveat is derived from.
    "iv_identification_assumption_required": frozenset({"verifier_check"}),
    "mediation_identification_assumption_required": frozenset(
        {"verifier_check"}
    ),
    "transport_identification_assumption_required": frozenset(
        {"verifier_check"}
    ),
    "llm_declared_ambiguity": frozenset({"verifier_check"}),
    "answer_is_bounds_not_point_estimate": frozenset({"verifier_check"}),
    "low_confidence_input_data": frozenset({"verifier_check"}),
    "front_door_identification_assumption_required": frozenset(
        # derivation_step when identify_via_front_door step is recorded;
        # verifier_check (program:front_door_pattern) when status is
        # NEEDS_INVESTIGATION and the kernel skipped recording the step.
        {"derivation_step", "verifier_check"}
    ),
    "counterfactual_identification_assumption_required": frozenset(
        # derivation_step when a counterfactual derivation step (twin
        # network / monotone bounds / consistency) is recorded; verifier_
        # check ("counterfactual_status" / "counterfactual_query_kind")
        # when the query is NEEDS_ASSUMPTION / counterfactual-kind and
        # carries no derivation chain to cite. Same status-derived
        # fallback shape as front_door_identification_assumption_required.
        {"derivation_step", "verifier_check"}
    ),
    "graph_learned_from_data": frozenset({"verifier_check"}),
    # Program-shape signal: declared confounder pattern (Z->X & Z->Y) with no
    # bidirected edges. Trigger does not require a recorded derivation step
    # (the kernel may skip identify_via_backdoor when status is
    # NEEDS_INVESTIGATION due to missing theta), so provenance is a
    # verifier_check ref pointing at the symbolic program-shape predicate.
    "unmeasured_confounder_risk": frozenset({"verifier_check"}),
    # Trigger compares query fields against result.extensions; provenance
    # is a verifier_check ref pointing at the symbolic conflict locator.
    "unattempted_layer_due_to_dispatch_conflict": frozenset({"verifier_check"}),
    # Estimator-time signal — first-stage F-stat from IV
    # estimator falls below Stock-Yogo (2005) threshold. Provenance is
    # a verifier_check ref naming the (instrument -> treatment) pair;
    # no derivation step exists because the trigger fires after the
    # numeric_estimate has been attached.
    "weak_iv_instrument": frozenset({"verifier_check"}),
    # Over-identified 2SLS — the Sargan test rejected the instruments' joint
    # validity. Estimator-time falsification signal; provenance is a
    # verifier_check ref naming the treatment, same posture as weak_iv_instrument.
    "overidentification_rejected": frozenset({"verifier_check"}),
    # A conditional binary IV design could not be stratified on this
    # sample, so the reported estimand fell back from the LATE to the
    # linear-IV coefficient. Estimator-time signal; provenance is a
    # verifier_check ref naming the (instrument | conditioning) pair,
    # same posture as weak_iv_instrument — no derivation step, because
    # the trigger fires once the estimator has already chosen.
    "iv_estimand_fallback_to_linear": frozenset({"verifier_check"}),
    # Estimator-time signal — propensity P(X=1|Z) bounded
    # away from {0,1} for too few observations under backdoor
    # adjustment. Provenance is a verifier_check ref naming the
    # (treatment, adjustment) pair; same posture as weak_iv_instrument
    # — runtime signal, no derivation step.
    "propensity_overlap_violation": frozenset({"verifier_check"}),
    # Structural signal — given (conditioning subgroup) in
    # an EffectQuery contains a node where both X and Y are ancestors
    # (collider). Provenance is a verifier_check ref naming the
    # (collider, intervention -> target) trio; classifier-driven, no
    # derivation step (fires on program shape regardless of result
    # status).
    "collider_conditioning_opens_backdoor": frozenset({"verifier_check"}),
    # Estimator-time signal — backdoor logistic fitted but
    # training-set fitted P(Y|X,Z) clusters near 0/1 (quasi-separation).
    # Provenance is a verifier_check ref naming the
    # (outcome, treatment, adjustment) trio.
    "outcome_model_quasi_separation": frozenset({"verifier_check"}),
    # Structural-input signal routed via the same
    # investigation_request channel that carries MISSING_DISTRIBUTION,
    # but the item.reason carries the d-sep refusal signature
    # ("d-separation 拒绝"). Same provenance shape as
    # missing_distribution because both originate from the formula-
    # evaluator's InsufficientTheta path; the classifier branches on
    # the reason text. Marked must-disclose IMPORTANT — graph and CPT
    # disagree, the user needs to fix one of them, not just supply more
    # theta.
    "graph_theta_independence_mismatch": frozenset(
        {"investigation_request"}
    ),
    # Program-shape signal — variable on the identification path
    # declares a (measurement | observability) field whose value names a
    # known noisy-measurement pattern (self-report / questionnaire /
    # single-occasion / proxy / 24h recall etc.). Provenance is a
    # verifier_check ref naming the (variable, field) pair; classifier-
    # driven, no derivation step exists.
    "measurement_error_concern": frozenset({"verifier_check"}),
    # Structural signal — an ObservationStatement on node W
    # (encoding implicit sample restriction to W=observed-value) where
    # both intervention X and target Y are directed ancestors of W.
    # Provenance is a verifier_check ref naming the
    # (observed_node, intervention -> target) trio; classifier-driven,
    # no derivation step. Hernán-Hernández-Díaz-Robins 2004 selection
    # bias structural pattern.
    "selection_on_collider_opens_path": frozenset({"verifier_check"}),
    # Program-shape signal — intervention atom names a
    # predicate whose VariableDeclaration declares
    # ``state_vs_event = "state"`` while no ``time_window`` is declared
    # on the same predicate. The schema admits both fields, so without
    # this classifier nothing reads state_vs_event's VALUE.
    # Provenance is a verifier_check ref naming the offending
    # (intervention_predicate, "state without time_window") pair;
    # classifier-driven, no derivation step. Authoritative source:
    # Hernán & Taubman 2008 IJO 32(S3):S8-S14 "Does obesity shorten
    # life? The importance of well-defined interventions to answer
    # causal questions"; consistency assumption framing in Hernán &
    # Robins What If §3.4.
    "ill_defined_intervention_versions": frozenset({"verifier_check"}),
    # 2026-06-18 dichotomization: a path variable's ``threshold`` field
    # encodes a continuous measure cut at a cutpoint. Provenance cites the
    # program variable + threshold value as a verifier_check (no derivation
    # step — program-shape detection like measurement_error / ill_defined).
    # Royston-Altman-Sauerbrei 2006 *Stat Med* 25:127.
    "dichotomized_continuous_measure": frozenset({"verifier_check"}),
    # 2026-07-11 pre-flight data diagnostic: CSV data contradicts a
    # variable's declared scale / domain. Provenance is a verifier_check ref
    # naming the offending predicate; the reconciliation evidence lives in
    # extensions.type_reconciliation and is independently re-derived by
    # verify_type_reconciliation (no derivation step — data-vs-declaration
    # detection on the estimate path, like the propensity-overlap and
    # quasi-separation estimator-runtime diagnostics).
    "declared_type_data_mismatch": frozenset({"verifier_check"}),
    # Estimator-time signal — a proximal query's proxies present some number
    # of levels other than the k it posits for the latent, and no coarsening
    # is declared. Provenance is a verifier_check ref naming the two proxies;
    # no derivation step exists, because the estimator refused before writing
    # one — which is the same posture as every other refusal-time diagnostic
    # here.
    "proxy_coarsening_undeclared": frozenset({"verifier_check"}),
    # #450. Raised by the identification layer, so it cites the
    # investigation request that carries the ask — the same signal
    # ``missing_iv_candidate`` cites when a loop leaves an instrument as
    # the only route.
    "feedback_loop_reaches_the_estimand": frozenset(
        {"investigation_request", "derivation_step"}
    ),
    # #451. Estimator-time, and unlike its neighbours above the estimator did
    # NOT refuse: a number was produced and the finding is about how to read
    # it. The ref is a verifier_check naming the pair, the same shape the
    # other estimator-runtime diagnostics use, because the derivation step
    # this is a fact about is written after the gap is filed.
    "regularisation_is_moving_the_answer": frozenset({"verifier_check"}),
    # The same channel for the same reason: a share counted while the
    # estimator ran, filed before the derivation step it is a fact about
    # exists to be pointed at.
    "treatment_bridge_leaves_its_range": frozenset({"verifier_check"}),
    # #457. Also estimator-time and also filed before its derivation step
    # exists — but what it is a fact about is which QUESTION got answered,
    # not how to read a number. There is a derivation step for the test, and
    # it did not fail, so pointing at one would misdescribe the finding: the
    # test succeeded and the estimate is what is absent.
    "answer_is_a_test_not_an_effect_size": frozenset({"verifier_check"}),
}


def _verify_t10_3_kind_consistency(
    report: dict,
    *,
    derivation_steps: list[dict],
) -> None:
    """T10-3: each gap.kind must be coherent with what the cited
    provenance signals can support.

    Two checks:
    (a) at least one ref in provenance must be of an acceptable kind for
        the declared gap_kind (per ``_KIND_ACCEPTS_REF``);
    (b) when an unidentifiable_no_admissible_set / missing_iv_candidate
        gap cites a derivation_step, that step must actually be a failed
        step (else the gap is a phantom).
    """
    # Quick lookup of failure status by step_id / rule name.
    failed_step_ids: set[str] = set()
    for step in derivation_steps:
        if _step_failed(step):
            failed_step_ids.add(_step_id_or_rule(step))
            rule = step.get("rule", "")
            if rule:
                failed_step_ids.add(rule)

    for gap_index, gap in enumerate(report.get("gaps", [])):
        kind = gap.get("kind")
        if kind not in _KIND_ACCEPTS_REF:
            raise VerificationError(
                f"T10-3: gap[{gap_index}] has unknown kind={kind!r}",
                step_index=None, rule="data_gap_kind_consistency_check",
            )
        accepts = _KIND_ACCEPTS_REF[kind]
        provenance = gap.get("provenance", []) or []
        ref_kinds = {ref.get("ref_kind") for ref in provenance}
        if not (ref_kinds & accepts):
            raise VerificationError(
                f"T10-3: gap[{gap_index}] kind={kind!r} requires at least "
                f"one provenance ref of {sorted(accepts)}; got {sorted(ref_kinds)}",
                step_index=None, rule="data_gap_kind_consistency_check",
            )
        # Failure-only gap kinds: the cited derivation step must be a
        # failed step, otherwise the gap is fabricated. Exception:
        # ``tian_hedge_witness`` is a SUCCESSFUL step that proves
        # unidentifiability — it's the witness, not a failure record,
        # but downstream consumers see the same blocking gap.
        if kind in (
            "unidentifiable_no_admissible_set",
            "missing_iv_candidate",
        ):
            tian_hedge_step_ids = {
                _step_id_or_rule(s)
                for s in derivation_steps
                if s.get("rule") == "tian_hedge_witness"
            }
            tian_hedge_step_ids |= {"tian_hedge_witness"}
            for ref in provenance:
                if ref.get("ref_kind") != "derivation_step":
                    continue
                rid = ref.get("ref_id")
                # If the gap claims missing_iv_candidate / unidentifiable,
                # at least one cited step must be a failure or a Tian
                # hedge witness. Multiple refs allowed.
                if rid in failed_step_ids or rid in tian_hedge_step_ids:
                    break
            else:
                # No derivation_step ref pointed at a failed step.
                # Allow if the gap also cites an investigation_request —
                # in that path the failure is documented through the
                # missing-information channel, not the derivation chain.
                cited_inv = any(
                    ref.get("ref_kind") == "investigation_request"
                    for ref in provenance
                )
                if not cited_inv:
                    raise VerificationError(
                        f"T10-3: gap[{gap_index}] kind={kind!r} cites "
                        "derivation_step refs but none point at an actual "
                        "failed step (and no investigation_request ref "
                        "documents the failure either)",
                        step_index=None,
                        rule="data_gap_kind_consistency_check",
                    )


# ============================================ public entry


def verify_data_gap_report(
    report: dict,
    *,
    derivation: dict | None = None,
    investigation_requests: list[dict] | None = None,
    framing_notes: list[dict] | None = None,
) -> None:
    """Run T10-1 / T10-2 / T10-3 against ``report``.

    Inputs are dicts (as serialized in the result envelope) so the audit
    catches serialization bugs in addition to generator bugs.

    Returns ``None`` on accept; raises ``VerificationError`` on reject
    (with rule field set to the offending T10 rule name).

    A ``None`` or empty report short-circuits to accept — the generator
    decided no gaps applied to this query, and T10-2 cannot demand
    coverage for signals that were never reported.
    """
    if report is None:
        return
    if not isinstance(report, dict):
        raise VerificationError(
            f"data_gap_report must be a dict; got {type(report).__name__}",
            step_index=None, rule="data_gap_report",
        )
    derivation_steps: list[dict] = []
    if derivation is not None:
        steps = derivation.get("steps", []) or []
        derivation_steps = list(steps)
    investigation_requests = list(investigation_requests or [])
    framing_notes = list(framing_notes or [])

    _verify_t10_1_provenance(
        report,
        derivation_steps=derivation_steps,
        investigation_requests=investigation_requests,
        framing_notes=framing_notes,
    )
    _verify_t10_2_completeness(
        report,
        derivation_steps=derivation_steps,
        investigation_requests=investigation_requests,
        framing_notes=framing_notes,
    )
    _verify_t10_3_kind_consistency(
        report,
        derivation_steps=derivation_steps,
    )


# ==================================== T10-4: the tier the report announces
#
# ``answer_tier`` is the report's headline: point, interval, or none — the
# strongest answer this question can still get. Every rule above reads the
# gaps; none of them reads the word those gaps add up to, and a word no
# rule reads is an unfalsifiable claim in the place a reader looks first.
#
# It is not a fifth thing the run knows. It is a conclusion drawn from four
# things already on the envelope — the question, the status, the gap
# species, and whether an interval is in hand — plus one on the program.
# So it is recomputed here rather than compared to anything, which is the
# only form of holding a judgement that a judgement cannot satisfy by
# rewriting its own evidence.

#: Which questions name a quantity an answer could be a tier OF. A tier is
#: what the answer to a question can be, so a question that names no
#: quantity has none — and this is the producer's first line.
#:
#: Restated, not imported, for the reason every table in this package is:
#: a verifier that reads the producer's own roster agrees with it by
#: construction. Pinned to ``themis.questions`` by a test, so a new kind
#: arrives as a red suite rather than as a tier nothing reads.
_NAMES_AN_ESTIMAND = frozenset({
    "effect", "identify", "probability", "counterfactual", "causation",
    "scm_counterfactual", "counterfactual_conjunction", "proximal_effect",
})

#: And which of those have an interval to fall back on when a point is out
#: of reach for a reason the data cannot mend. Same roster, same pin.
_HAS_INTERVAL_FALLBACK = frozenset({"effect", "counterfactual", "causation"})

#: The species that say the POINT is unreachable — not "the data are
#: short", which every gap says. Bounds presence is NOT such a signal: an
#: assumption-free floor is attached to every needs_investigation effect,
#: including ones whose point is perfectly identified and merely missing a
#: parameter.
_POINT_IS_BLOCKED_BY = frozenset({
    "unidentifiable_no_admissible_set", "transport_sources_disagree",
})

#: And the two statuses that say the same thing about themselves.
_POINT_IS_BLOCKED_AT = frozenset({
    "needs_assumption", "counterfactual_bounded",
})

_TIER_POINT, _TIER_INTERVAL, _TIER_NONE = "point", "interval", "none"


def _a_premise_the_caller_withheld_blocks_the_point(
    program: Any, query_id: Any,
) -> bool:
    """Whether a premise, rather than absent data, stands in the way.

    Probabilities of causation are intervals; monotonicity is what
    collapses them to a point, and it is declared on the question rather
    than found in the data. Undeclared, no amount of data yields a point,
    so a tier read off the gaps alone would promise a number that cannot
    arrive.
    """
    query = query_of(program, query_id) if isinstance(program, dict) \
        else None
    if not isinstance(query, Mapping):
        return False
    return query.get("kind") == "causation" and not query.get("monotonic")


def _an_interval_is_in_hand(result: Mapping) -> bool:
    """Whether the envelope carries an interval worth calling one.

    Two channels and both count: the bounds rows an effect question gets,
    and the interval a bounded counterfactual carries on its own numeric
    result. A row that says its own width is uninformative is not one, and
    neither is a numeric interval spanning the whole of [0, 1] — a bound
    that excludes nothing is not an answer a reader can use.
    """
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping) and not row.get(
                "width_when_uninformative", False):
            return True
    numeric = result.get("numeric_result")
    interval = numeric.get("interval") if isinstance(numeric, Mapping) \
        else None
    if not isinstance(interval, Mapping):
        return False
    low, high = interval.get("low"), interval.get("high")
    if not isinstance(low, (int, float)) or not isinstance(high, (int, float)):
        return False
    return not (low <= 0.0 and high >= 1.0)


def _the_point_is_blocked(result: Mapping, program: Any) -> bool:
    """Whether anything on the envelope says the POINT is out of reach.

    Two signals and neither is bounds presence: an assumption-free floor
    is attached to every needs_investigation effect, including ones whose
    point is identified and merely missing a parameter.
    """
    report = result.get("data_gap_report")
    gaps = report.get("gaps") or () if isinstance(report, Mapping) else ()
    return (
        result.get("status") in _POINT_IS_BLOCKED_AT
        or any(isinstance(gap, Mapping)
               and gap.get("kind") in _POINT_IS_BLOCKED_BY
               for gap in gaps)
        or _a_premise_the_caller_withheld_blocks_the_point(
            program, result.get("query_id"))
    )


def verify_answer_tier(result: Mapping, program: Any) -> None:
    """The report's headline word, held to what the envelope carries.

    WHAT THIS DOES NOT DO, and why. The tier is computed once at
    identification time from the question, the status, the gap species and
    the interval in hand — and then written a second time by the
    estimation layer, which reconciles it to the number it has just
    produced. Recomputing the first author's function refuses six honest
    answers in this repository's own corpus, because on those the second
    author had the last word. A rule that refuses an honest answer is
    worse than the hole it closes, so what is held here is what is true of
    the word whichever pass wrote it, and the rest is left to the frontier
    where the two authors become one.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` otherwise.
    """
    if not isinstance(result, Mapping):
        return
    report = result.get("data_gap_report")
    if not isinstance(report, Mapping):
        return
    kind = result.get("query_kind")
    if not isinstance(kind, str):
        return
    shown = report.get("answer_tier")

    # A tier is what the answer to a question can BE, so a question that
    # names no quantity has none. The producer's own first line.
    if kind not in _NAMES_AN_ESTIMAND:
        if shown is not None:
            raise VerificationError(
                f"the report tells a reader the best answer available is "
                f"{shown!r}, and this question names no quantity for an "
                f"answer to be about; a tier here is a promise about "
                f"nothing",
                step_index=None, rule="answer_tier_check",
            )
        return
    if shown is None:
        raise VerificationError(
            f"the report tells a reader nothing about what answer is still "
            f"available, and a {kind!r} question names a quantity an "
            f"answer would be of; the absence reads as 'not applicable' "
            f"where the truth is 'nobody said'",
            step_index=None, rule="answer_tier_check",
        )

    # A point promised where the envelope itself says the point is out of
    # reach. Both authors agree about this one: neither writes POINT past
    # a blocking signal, because the signal is what blocking MEANS.
    if shown == _TIER_POINT and _the_point_is_blocked(result, program):
        raise VerificationError(
            "the report promises a reader a point estimate is still "
            "available, and this envelope carries the signal that the "
            "point is out of reach — an unidentified estimand, sources "
            "that disagree, or a premise the question never declared. "
            "More data cannot produce what is promised",
            step_index=None, rule="answer_tier_check",
        )

    # And "no answer available" said over an interval that is sitting in
    # the envelope. NONE tells a reader to stop; an interval is a reason
    # not to.
    if shown == _TIER_NONE and _an_interval_is_in_hand(result):
        raise VerificationError(
            "the report tells a reader no answer is available and an "
            "interval is on this envelope; a reader deciding whether to "
            "collect more data is told to give up on an answer they "
            "already have",
            step_index=None, rule="answer_tier_check",
        )
