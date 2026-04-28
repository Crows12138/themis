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

from .errors import VerificationError


# ============================================ failure detection
#
# The verifier maintains its OWN list of rule names that indicate
# structural failure. Intentionally NOT imported from
# themis.output.data_gap_report — the whole point of an independent
# verifier is that bugs in one cannot hide bugs in the other.
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
    2. Parameter-group investigation_request items → at least one gap
       with provenance investigation_request:<item.target>.
    3. Framing notes → at least one gap with provenance
       framing_note:<predicate>.
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

    # 2. Parameter-group investigation items must be cited.
    for req in investigation_requests:
        if req.get("group") != "parameter":
            continue
        for item in req.get("items", []) or []:
            target = item.get("target")
            if not target:
                continue
            if target not in cited_investigation:
                raise VerificationError(
                    f"T10-2: parameter investigation_request "
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
    "ambiguous_variable_definition": frozenset({"framing_note"}),
    # Phase 13: dose-response data spec — provenance is a verifier_check
    # ref pointing at program.extensions.ambiguities.dose_response_query
    # (no derivation step exists for this kind; the gap is triggered by
    # a program-level ambiguity, not a failed derivation rule).
    "dose_response_data_required": frozenset({"verifier_check"}),
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
        # failed step, otherwise the gap is fabricated.
        if kind in (
            "unidentifiable_no_admissible_set",
            "missing_iv_candidate",
        ):
            for ref in provenance:
                if ref.get("ref_kind") != "derivation_step":
                    continue
                rid = ref.get("ref_id")
                # If the gap claims missing_iv_candidate / unidentifiable,
                # at least one cited step must be a failure. We allow
                # multiple refs in case the generator also cites context.
                if rid in failed_step_ids:
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
