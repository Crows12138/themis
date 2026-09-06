"""Phase 10 §10.4 — independent verification of DataGapReport.

Three rules audit a generated DataGapReport for honesty:

- **T10-1 ``data_gap_provenance_check``** — every ref in every gap's
  provenance array must point at something that is there. What "there"
  means is the ref's own ``ref_kind``, which is why the kind is what makes
  the question askable at all: a derivation step, an investigation
  request, a framing note, a path into this answer, a place in the
  program, or a check this build ran.
- **T10-2 ``data_gap_completeness_check``** — every upstream failure
  signal that the schema can detect (failed derivation step / parameter
  investigation / framing note) must be covered by at least one gap.
- **T10-3 ``data_gap_kind_consistency_check``** — each gap's ``kind`` must
  be coherent with the upstream signal it cites in provenance (e.g. a
  gap labelled ``unidentifiable_no_admissible_set`` cited as
  ``derivation_step`` must reference a step that actually represents a
  structural failure, not a successful identification).
- **T10-5 ``data_gap_species_check``** — each gap's ``severity`` and
  ``blocks`` must be what its species declares. The few species whose
  value is an occasion's say so in code, and this rule is silent on
  exactly those.

**Independence pin:** This module MUST NOT import from
``themis.output.data_gap_report`` or any generator-side module. The audit
is a re-implementation of the failure / coverage logic from scratch so
that bugs in the generator cannot mask themselves in the verifier. A
test in ``tests/test_verifier/test_data_gap_rules.py`` line-scans this
file to enforce the rule.

Reads only from the JSON envelope (dicts), not from typed dataclasses,
so the audit also catches serialization-layer bugs. The exception is the
contract layer's declarations in :mod:`themis.types`, which are not
anything a producer wrote — they are what the words in the envelope mean.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from ..types import (
    BLOCKS_OF,
    BLOCKS_TURN_ON,
    GapKind,
    SEVERITY_OF,
    SEVERITY_TURNS_ON,
)
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
    envelope: dict | None = None,
) -> None:
    """T10-1: every gap.provenance[i].ref_id must resolve where its kind says.

    ``envelope`` is the answer the report came on, needed by the arm that
    follows a path into it. Absent, that arm refuses rather than falls
    silent — the same choice the derivation arm already makes when it is
    handed no chain, and for the same reason: an audit that cannot look is
    not an audit that saw nothing wrong.
    """
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
            elif ref_kind == "envelope_path":
                if envelope is None:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites envelope_path={ref_id!r} and this audit was "
                        f"handed no answer to follow it on",
                        step_index=None, rule="data_gap_provenance_check",
                    )
                found, why = _at_path(envelope, ref_id)
                if not found:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"cites envelope_path={ref_id!r} which this answer "
                        f"does not carry: {why}",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "program_site":
                # The declared range, and the reason is the door rather than
                # the ref: this audit is result-only by contract, so the
                # program a site would be found in is not here to look in.
                # Naming the space is still worth doing — it is what stops a
                # program site from being spelled as a path into the answer,
                # which is how one of these came to name a block that was
                # never on the envelope.
                if not isinstance(ref_id, str) or not ref_id:
                    raise VerificationError(
                        f"T10-1: gap[{gap_index}].provenance[{ref_index}] "
                        f"program_site ref_id must be a non-empty string",
                        step_index=None, rule="data_gap_provenance_check",
                    )
            elif ref_kind == "verifier_check":
                # A check, not an artifact: what this names is something
                # this build DID, and the run is over. Which check each gap
                # species is raised by is declared nowhere yet, so all this
                # can ask is that a check was named.
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


#: One step of a gap's envelope path: a key, and optionally a pick from what
#: that key holds.
_PATH_STEP = re.compile(r"([^.\[\]]+)(?:\[([^\]]*)\])?")


def _at_path(envelope: dict, path: object) -> tuple[bool, str]:
    """Whether a gap's envelope path lands on something, and why not.

    Dotted keys from the answer's root. ``[x]`` picks from what the key
    holds: on a list, the entry whose ``kind`` is ``x`` — which is how a
    report names one member of a block that carries several — and on a
    mapping, the key ``x``.

    Spelled here rather than imported because this file may not read the
    generator, and a path is followed the same way whoever wrote it.
    """
    if not isinstance(path, str) or not path:
        return False, "the path is empty"
    node: object = envelope
    for part in path.split("."):
        step = _PATH_STEP.fullmatch(part)
        if step is None:
            return False, f"{part!r} is not a step"
        key, pick = step.group(1), step.group(2)
        if not isinstance(node, dict) or key not in node:
            return False, f"nothing named {key!r} there"
        node = node[key]
        if pick is None:
            continue
        if isinstance(node, list):
            found = next((e for e in node if isinstance(e, dict)
                          and e.get("kind") == pick), None)
            if found is None:
                return False, f"no entry of {key!r} has kind {pick!r}"
            node = found
        elif isinstance(node, dict):
            if pick not in node:
                return False, f"{key!r} has no {pick!r}"
            node = node[pick]
        else:
            return False, f"{key!r} holds nothing to pick from"
    return True, ""


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
    # Phase 13: dose-response data spec — triggered by a program-level
    # ambiguity rather than a failed derivation rule, so there is no step
    # to cite and the ref names the place in the program it was found.
    "dose_response_data_required": frozenset({"program_site"}),
    # Phase 11.x §C: the ref names the cause-statement annotation that
    # flagged the path edge as an LLM hypothesis — a place in the program,
    # shaped program:cause:<from>-><to>:annotations.source.
    "unverified_proposal_edge_on_query_path": frozenset({"program_site"}),
    # Must-disclose caveat kinds — the caveat is derived from a block of
    # the answer itself, so the ref is the path to that block. That
    # sentence used to be a comment because no member of the vocabulary
    # could say it, and a ref nothing could locate is a ref nothing could
    # check.
    "iv_identification_assumption_required": frozenset({"envelope_path"}),
    "mediation_identification_assumption_required": frozenset(
        {"envelope_path"}
    ),
    "transport_identification_assumption_required": frozenset(
        {"envelope_path"}
    ),
    "llm_declared_ambiguity": frozenset({"envelope_path"}),
    "answer_is_bounds_not_point_estimate": frozenset({"envelope_path"}),
    "low_confidence_input_data": frozenset({"envelope_path"}),
    "front_door_identification_assumption_required": frozenset(
        # derivation_step when identify_via_front_door step is recorded;
        # the program site (program:front_door_pattern) when status is
        # NEEDS_INVESTIGATION and the kernel skipped recording the step.
        {"derivation_step", "program_site"}
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
    # The signal is in the PROGRAM — the producer reads
    # ``program.extensions.discovery_metadata`` and says so in its own
    # docstring, while the ref it wrote was spelled as a path into the
    # answer, naming a block no answer carries.
    "graph_learned_from_data": frozenset({"program_site"}),
    # Program-shape signal: declared confounder pattern (Z->X & Z->Y) with no
    # bidirected edges. Trigger does not require a recorded derivation step
    # (the kernel may skip identify_via_backdoor when status is
    # NEEDS_INVESTIGATION due to missing theta), so the ref names the
    # program-shape predicate it matched.
    "unmeasured_confounder_risk": frozenset({"program_site"}),
    # Trigger compares query fields against result.extensions; the ref
    # names the conflict in the program that produced it.
    "unattempted_layer_due_to_dispatch_conflict": frozenset({"program_site"}),
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
    # single-occasion / proxy / 24h recall etc.). The ref names the
    # (variable, field) pair in the program; classifier-driven, no
    # derivation step exists.
    "measurement_error_concern": frozenset({"program_site"}),
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
    # encodes a continuous measure cut at a cutpoint. The ref names the
    # program variable + threshold value (no derivation step — program-shape
    # detection like measurement_error / ill_defined).
    # Royston-Altman-Sauerbrei 2006 *Stat Med* 25:127.
    "dichotomized_continuous_measure": frozenset({"program_site"}),
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


# ================================= T10-5 what a gap is worth, and to whom
#
# ``severity`` ranks the list a reader works down and decides which gap
# reaches the headline; ``blocks`` says which of identification, a point, an
# interval, a transport or an interpretation filling this one would buy
# back. Both are acted on, and neither was read by any rule.
#
# Neither could be. Both were typed at all 47 construction sites, and a
# value every site writes is declared nowhere — so the only thing a rule
# could have held them against was the producer's layout, and a verifier
# that restates a producer's layout agrees with it by construction.
#
# They belong to the species, and now say so. :data:`themis.types.SEVERITY_OF`
# and :data:`~themis.types.BLOCKS_OF` hold the species whose value is the
# same on every occasion; :data:`~themis.types.SEVERITY_TURNS_ON` and
# :data:`~themis.types.BLOCKS_TURN_ON` hold the few where it is the
# occasion's, each naming in a sentence what it turns on. The two rows
# partition ``GapKind`` and are checked at import, so every species either
# has a word here to be held to or states in code why it has none — and this
# rule is silent on exactly the second sort, which is the declaration's own
# statement about itself rather than a corner the reading missed.
#
# Imported rather than restated, which is the opposite of every other table
# in this module and for the same reason those are restated. A restatement
# buys independence from the PRODUCER's roster. This is not the producer's
# roster: it is the contract layer's declaration of what the name means —
# the arrangement ``status_rules`` reads ``STATUS_CLAIMS`` under — and the
# producer now fills its own gaps FROM it, so a copy here would not be a
# second reading, only a second thing to drift.

_SPECIES_RULE = "data_gap_species_check"

#: The two things a gap says about its own weight, each with the species
#: that fix it and the species that declare it the occasion's.
_A_GAP_SAYS_OF_ITSELF = (
    ("severity", SEVERITY_OF, SEVERITY_TURNS_ON),
    ("blocks", BLOCKS_OF, BLOCKS_TURN_ON),
)

#: What a reader does with each, so a refusal names what goes wrong rather
#: than which field disagrees.
_WHAT_A_READER_DOES_WITH_IT = {
    "severity": ("ranks the gaps by it and reads the top of that list as "
                 "what stands in the way of an answer"),
    "blocks": "reads it to learn what filling this gap would buy back",
}

_SPECIES_NAMED: dict[str, GapKind] = {kind.value: kind for kind in GapKind}


def _verify_t10_5_species_properties(report: dict) -> None:
    """Each gap's severity and blocks, against what its species declares."""
    for gap_index, gap in enumerate(report.get("gaps") or ()):
        if not isinstance(gap, dict):
            continue
        kind = gap.get("kind")
        species = _SPECIES_NAMED.get(kind) if isinstance(kind, str) else None
        if species is None:
            # Not a species whose declaration could be looked up. A word
            # outside the vocabulary is refused by the schema the door
            # validates against, before any rule here reads it.
            continue
        for field, fixed, _the_occasion_s in _A_GAP_SAYS_OF_ITSELF:
            declared = fixed.get(species)
            if declared is None:
                continue
            shown = gap.get(field)
            if shown == declared.value:
                continue
            does = _WHAT_A_READER_DOES_WITH_IT[field]
            if shown is None:
                raise VerificationError(
                    f"T10-5: gap[{gap_index}] kind={species.value!r} says "
                    f"nothing about its {field}, and a gap of this species "
                    f"is {declared.value!r} on every occasion; a reader "
                    f"{does}",
                    step_index=None, rule=_SPECIES_RULE,
                )
            raise VerificationError(
                f"T10-5: gap[{gap_index}] kind={species.value!r} says its "
                f"{field} is {shown!r}, and a gap of this species is "
                f"{declared.value!r} on every occasion; a reader {does}",
                step_index=None, rule=_SPECIES_RULE,
            )


# ============================================ public entry


def verify_data_gap_report(
    report: dict,
    *,
    derivation: dict | None = None,
    investigation_requests: list[dict] | None = None,
    framing_notes: list[dict] | None = None,
    envelope: dict | None = None,
) -> None:
    """Run T10-1 / T10-2 / T10-3 / T10-5 against ``report``.

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
        envelope=envelope,
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
    _verify_t10_5_species_properties(report)


# ==================================== T10-4: the tier the report announces
#
# ``answer_tier`` is the report's headline: point, interval, or none — the
# strongest answer this question can still get. Every rule above reads the
# gaps; none of them reads the word those gaps add up to, and a word no
# rule reads is an unfalsifiable claim in the place a reader looks first.
#
# It is not a sixth thing the run knows. It is a conclusion drawn from five
# things already on the envelope — the question, the status, the gap
# species, whether an interval is in hand, and which shape the answer came
# out in — plus one on the program. So it is recomputed here rather than
# compared to anything, which is the only form of holding a judgement that
# a judgement cannot satisfy by rewriting its own evidence.
#
# The last of the five is what made recomputing possible at all. The tier
# is one question in two tenses — what came out, and failing that what
# could still be got — and until the answer's shape was readable here the
# second tense was all this could ask, which is wrong on every answer that
# came out in some shape other than a number.

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

#: The status that says the question itself does not stand.
_OUTSIDE_LANGUAGE = "outside_language"

_TIER_POINT, _TIER_INTERVAL, _TIER_NONE = "point", "interval", "none"

#: Weakest last. A reader holding several is holding the strongest of them.
_STRONGEST_FIRST = (_TIER_POINT, _TIER_INTERVAL, _TIER_NONE)

#: What a reader is holding once the estimate carries this block. The keys
#: are where each declared answer shape lives on ``numeric_estimate`` and
#: the values are what that shape hands over — the two facts
#: :mod:`themis.answers` declares per shape, restated here for the reason
#: every table in this package is, and pinned to it by a test.
#:
#: Two blocks are not read by presence and are not in here. ``point`` is
#: read for presence rather than truth, because a null effect is an answer
#: and ``0.0`` is one. ``probabilities_of_causation`` is on the envelope
#: whichever way the run went, and what monotonicity buys sits INSIDE each
#: quantity, so the tier turns on the point rather than on the block.
_TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES = {
    "dose_response_curve": _TIER_POINT,
    "decomposition": _TIER_POINT,
    "controlled_direct_effect": _TIER_POINT,
    "joint_effect": _TIER_POINT,
    "counterfactual_cell": _TIER_INTERVAL,
    # A test says whether the treatment does anything and no more, so a
    # reader asking how much is holding nothing.
    "no_effect_test": _TIER_NONE,
}
_A_SINGLE_NUMBER = "point"
_THE_THREE_PROBABILITIES = "probabilities_of_causation"


def _the_tier_the_answer_came_out_as(result: Mapping) -> str | None:
    """What the estimate on this envelope actually hands a reader, or
    ``None`` where no answer this build can name has come out.

    ``None`` is not "no answer". Not every road to a number ends in a
    ``numeric_estimate`` — the structural and plug-in roads write their
    number elsewhere — so this says only that the shape vocabulary has
    nothing to say here, and the question the caller falls back on is the
    forward-looking one: what could still be got.
    """
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, Mapping):
        return None
    carried = {tier for key, tier in _TIER_OF_A_BLOCK_THE_ESTIMATE_CARRIES.items()
               if estimate.get(key)}
    if estimate.get(_A_SINGLE_NUMBER) is not None:
        carried.add(_TIER_POINT)
    three = estimate.get(_THE_THREE_PROBABILITIES)
    if isinstance(three, Mapping) and three:
        sharp = (three.get("pn") or {}).get("point") is not None \
            if isinstance(three.get("pn"), Mapping) else False
        carried.add(_TIER_POINT if sharp else _TIER_INTERVAL)
    for tier in _STRONGEST_FIRST:
        if tier in carried:
            return tier
    return None


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


#: The answers the estimate's own fields had no room for: the ANSWER-family
#: blocks ``themis.blocks`` declares with no carrier. Restated rather than
#: imported, for the reason every table in this package is, and pinned to
#: the declaration by a test.
#:
#: A block whose carrier IS ``numeric_estimate`` is a display copy of
#: something the shape table already reads, so it is not here — the field
#: and the copy would count as two answers where there is one.
_AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR = frozenset({
    "anderson_rubin_region", "causation", "scm_counterfactual",
})


def _an_answer_the_point_is_not(result: Mapping) -> bool:
    """Whether an answer outside the estimate's fields is sitting here, and
    is not one that says of itself that it brackets nothing.

    Only ever asked where the point is out of reach, and there an answer
    that exists anyway is what the reader still has. What it is not is a
    point, because the point is what the envelope has just said is
    unavailable — so what such an answer supports is the interval.

    The one thing that can make it less than that is the answer saying so.
    A confidence region over a coefficient vector is written whether or not
    it closed, and an open region excludes nothing; it says which it is,
    and that word is read rather than assumed.

    This channel is why the tier is readable for a whole road at all. The
    region is a set over k coefficients, so ``numeric_estimate`` — one
    estimand, one number, one interval — has no room for it and no answer
    shape describes it, and a rule reading only the estimate's fields sees
    a blocked point beside nothing and says "no answer available" over the
    interval each coefficient projects onto.
    """
    extensions = result.get("extensions")
    if not isinstance(extensions, Mapping):
        return False
    for key in _AN_ANSWER_THE_ESTIMATE_HAD_NO_ROOM_FOR:
        block = extensions.get(key)
        if not isinstance(block, Mapping):
            continue
        region = block.get("region")
        if isinstance(region, Mapping) and region.get("bounded") is False:
            continue
        return True
    return False


def _an_interval_is_in_hand(result: Mapping) -> bool:
    """Whether the envelope carries an interval worth calling one.

    Three channels and each is read for the answer's own word about
    itself: the bounds rows an effect question gets, where a row that
    calls its own width uninformative is not one; the interval a bounded
    counterfactual carries on its numeric result, where one spanning the
    whole of [0, 1] excludes nothing and is not one either; and an answer
    the estimate's fields had no room for, which says whether it closed.
    """
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping) and not row.get(
                "width_when_uninformative", False):
            return True
    numeric = result.get("numeric_result")
    interval = numeric.get("interval") if isinstance(numeric, Mapping) \
        else None
    if isinstance(interval, Mapping):
        low, high = interval.get("low"), interval.get("high")
        if (isinstance(low, (int, float)) and isinstance(high, (int, float))
                and not (low <= 0.0 and high >= 1.0)):
            return True
    return _an_answer_the_point_is_not(result)


def _identification_blocks_the_point(result: Mapping) -> bool:
    """Whether the run itself says the POINT is out of reach.

    Two signals and neither is bounds presence: an assumption-free floor
    is attached to every needs_investigation effect, including ones whose
    point is identified and merely missing a parameter.

    Kept apart from the premise below because the two do not answer the
    same question about an interval. Where identification failed, the
    bounds are out of reach too and NONE is the honest word; where only a
    premise is missing, the interval is exactly what is left.
    """
    report = result.get("data_gap_report")
    gaps = report.get("gaps") or () if isinstance(report, Mapping) else ()
    return (
        result.get("status") in _POINT_IS_BLOCKED_AT
        or any(isinstance(gap, Mapping)
               and gap.get("kind") in _POINT_IS_BLOCKED_BY
               for gap in gaps)
    )


def _the_point_is_blocked(result: Mapping, program: Any) -> bool:
    """Whether anything at all says the POINT is out of reach — what the
    run found, or what the question never declared."""
    return _identification_blocks_the_point(
        result) or _a_premise_the_caller_withheld_blocks_the_point(
            program, result.get("query_id"))


def _the_tier_this_envelope_supports(result: Mapping, program: Any) -> str:
    """The strongest answer this envelope actually offers a reader.

    One question asked in two tenses, and which tense applies is decided
    by the envelope rather than chosen here. Where an answer has come out,
    the tier is what it came out as. Where none has, it is what could
    still be got — and that is the only branch the gap species and the
    withheld premise are consulted for, because before there is an answer
    they are all there is to read.

    A number that came out where identification failed is the one place
    the two tenses meet: it is an estimate under an assumption nobody
    granted, so it does not make the estimand's point available and the
    envelope falls back to the interval it does have.
    """
    if result.get("status") == _OUTSIDE_LANGUAGE:
        # Not that the data are short: the quantity is undefined as asked,
        # so neither what is in hand nor what could be got is a claim worth
        # making, and the forward-looking branch would make the second.
        return _TIER_NONE
    identification_blocked = _identification_blocks_the_point(result)
    premise_blocked = _a_premise_the_caller_withheld_blocks_the_point(
        program, result.get("query_id"))
    came_out = _the_tier_the_answer_came_out_as(result)
    if came_out is not None:
        if came_out != _TIER_POINT:
            return came_out
        if not identification_blocked:
            return _TIER_POINT
    elif not identification_blocked and not premise_blocked:
        return _TIER_POINT
    if _an_interval_is_in_hand(result):
        return _TIER_INTERVAL
    if (came_out is None and premise_blocked and not identification_blocked
            and result.get("numeric_result") is None
            and result.get("query_kind") in _HAS_INTERVAL_FALLBACK):
        # Nothing computed, and with the premise the only thing in the way
        # the shape an answer would take is the interval. NONE here would
        # say the data cannot produce an answer, when what they cannot
        # produce is a point.
        return _TIER_INTERVAL
    return _TIER_NONE


def verify_answer_tier(result: Mapping, program: Any) -> None:
    """The report's headline word, held to what the envelope carries.

    Recomputed rather than compared to anything, which is the only form of
    holding a judgement that a judgement cannot satisfy by rewriting its
    own evidence.

    This used to hold two one-sided claims instead — no point past a
    blocking signal, no "none" over an interval — because recomputing the
    identification pass's function refused six honest answers, all of them
    ones the estimation layer had corrected afterwards. The six were not
    six exceptions. They were the interval-in-hand question answered from
    two hard-written channels while three answer shapes carry their
    interval elsewhere, and the estimation layer patching the result per
    site. What made the recomputation possible is that the envelope says
    which shape the answer came out in, so the two tenses of the question
    — what came out, what could still be got — are both readable here.

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

    supported = _the_tier_this_envelope_supports(result, program)
    if shown == supported:
        return

    # The two bends a reader is hurt most by, said in their own words.
    if shown == _TIER_POINT:
        raise VerificationError(
            "the report promises a reader a point estimate is still "
            "available, and this envelope carries the signal that the "
            "point is out of reach — an unidentified estimand, sources "
            "that disagree, a premise the question never declared, or an "
            "answer that came out in some other shape. More data cannot "
            "produce what is promised",
            step_index=None, rule="answer_tier_check",
        )
    if shown == _TIER_NONE:
        raise VerificationError(
            "the report tells a reader no answer is available and this "
            "envelope carries one; a reader deciding whether to collect "
            "more data is told to give up on an answer they already have",
            step_index=None, rule="answer_tier_check",
        )
    raise VerificationError(
        f"the report tells a reader the best answer available is "
        f"{shown!r}, and what this envelope carries is {supported!r}",
        step_index=None, rule="answer_tier_check",
    )
