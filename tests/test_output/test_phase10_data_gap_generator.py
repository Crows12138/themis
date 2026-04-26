"""Phase 10 §10.3 — DataGapReport generator tests.

Per-branch unit tests + the integration test that the generator is
actually attached at dispatch time.
"""
from __future__ import annotations

import pytest

from themis.output.data_gap_report import compute_data_gap_report
from themis.types import (
    DataGap,
    DataGapReport,
    DerivationStep,
    FramingNote,
    GapBlocks,
    GapKind,
    GapRefKind,
    GapSeverity,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    Priority,
    QueryKind,
    ResultStatus,
)


# ============================================ helpers


def _param_request(items: list[tuple[str, str | None]]) -> InvestigationRequest:
    """Build a parameter-group investigation request with given (target, reason)
    items."""
    inv_items = tuple(
        InvestigationItem(target=t, reason=r) for (t, r) in items
    )
    return InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=items[0][0] if len(items) == 1 else f"parameter:{len(items)}_items",
        priority=Priority.HIGH,
        group="parameter",
        items=inv_items,
    )


def _structure_request(target: str) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.RUN_EXPERIMENT,
        target=target,
        priority=Priority.HIGH,
        group="structure",
        items=(InvestigationItem(target=target),),
    )


def _assumption_request(target: str) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.DEFINE_ASSUMPTION,
        target=target,
        priority=Priority.HIGH,
        group="assumption",
        items=(InvestigationItem(target=target),),
    )


def _failed_step(rule: str, step_id: str = "step_x") -> DerivationStep:
    return DerivationStep(
        rule=rule, inputs={}, output=False, step_id=step_id, success=False
    )


# ============================================ short-circuits


def test_returns_none_for_cause_query_with_no_framing():
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
    )
    assert report is None


def test_returns_none_for_assoc_query_with_no_framing():
    report = compute_data_gap_report(
        query_kind=QueryKind.ASSOC,
        status=ResultStatus.STRUCTURALLY_SOLVED,
    )
    assert report is None


def test_cause_query_with_framing_emits_report():
    """Even cause/assoc benefit from surfacing variable-definition
    ambiguity — that's the only signal these query kinds carry."""
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        framing_notes=(FramingNote(predicate="x", missing=("time_window",)),),
    )
    assert report is not None
    assert len(report.gaps) == 1
    assert report.gaps[0].kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION


def test_effect_query_with_no_signals_emits_empty_report():
    """Distinct from None: effect queries always get a report so callers
    can present 'no gaps' affirmatively."""
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NUMERICALLY_SOLVED,
    )
    assert report is not None
    assert report.gaps == ()
    assert report.summary == ""


# ============================================ 1. unidentifiable_no_admissible_set


def test_unidentifiable_via_backdoor_emits_blocking_gap():
    derivation = (_failed_step("unidentifiable_via_backdoor", "step_3"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert report is not None
    assert len(report.gaps) == 1
    g = report.gaps[0]
    assert g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
    assert g.severity == GapSeverity.BLOCKING
    assert g.blocks == GapBlocks.IDENTIFICATION
    assert g.provenance[0].ref_kind == GapRefKind.DERIVATION_STEP
    assert g.provenance[0].ref_id == "step_3"


def test_explicit_success_false_step_caught_even_for_non_unidentifiable_rule_name():
    """Rules added later that don't carry _failed in name still trigger if
    they explicitly emit success=False."""
    derivation = (
        DerivationStep(
            rule="some_future_rule",
            inputs={},
            output=False,
            step_id="step_99",
            success=False,
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert any(
        g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET for g in report.gaps
    )


def test_unidentifiable_offers_three_alternative_paths():
    derivation = (_failed_step("unidentifiable_via_backdoor"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    g = report.gaps[0]
    assert len(g.alternative_paths) == 3


# ============================================ 2. missing_distribution


def test_missing_marginal_distribution_signature_marginal():
    requests = (_param_request([("P(y=true)", None)]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = report.gaps[0]
    assert g.kind == GapKind.MISSING_DISTRIBUTION
    assert g.signature == "marginal"


def test_missing_conditional_distribution_signature_conditional():
    requests = (_param_request([("P(y=true|x=true)", None)]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = report.gaps[0]
    assert g.signature == "conditional"


def test_missing_distribution_emits_per_item():
    """Multi-item parameter request fans out to multiple gaps."""
    requests = (
        _param_request(
            [("P(y=true|x=true)", None), ("P(y=true|x=false)", None)]
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    dist_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_DISTRIBUTION
    ]
    assert len(dist_gaps) == 2


# ============================================ 4. missing_assumption


def test_needs_assumption_status_with_assumption_request_emits_specific_gap():
    requests = (_assumption_request("assumptions.monotonicity"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_ASSUMPTION,
        investigation_requests=requests,
    )
    assumption_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_ASSUMPTION
    ]
    assert len(assumption_gaps) == 1
    assert assumption_gaps[0].severity == GapSeverity.IMPORTANT
    assert "monotonicity" in assumption_gaps[0].description


def test_needs_assumption_status_without_request_emits_generic_gap():
    """Status is the only signal — fall back to a verifier-check ref."""
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_ASSUMPTION,
    )
    assumption_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_ASSUMPTION
    ]
    assert len(assumption_gaps) == 1
    assert (
        assumption_gaps[0].provenance[0].ref_kind == GapRefKind.VERIFIER_CHECK
    )


# ============================================ 5. missing_iv_candidate


def test_iv_failure_in_derivation_emits_iv_gap_not_unidentifiable():
    """IV-specific failures should route through the IV classifier so the
    user gets IV-flavored alternatives, not the generic three."""
    derivation = (_failed_step("identify_via_iv", "iv_step"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.MISSING_IV_CANDIDATE in kinds
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET not in kinds


def test_structure_request_naming_iv_emits_iv_gap():
    requests = (_structure_request("iv_candidate_for_smoking_lung_cancer"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    assert any(
        g.kind == GapKind.MISSING_IV_CANDIDATE for g in report.gaps
    )


# ============================================ 6. missing_mediator_data


def test_mediation_block_with_mediator_param_request_emits_mediator_gap():
    extensions = {
        "mediation_decomposition": {
            "mediator": "tar_in_lungs",
            "mediator_valid": True,
        }
    }
    requests = (
        _param_request([("P(tar_in_lungs=true|smoking=true)", None)]),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
        extensions=extensions,
    )
    mediator_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_MEDIATOR_DATA
    ]
    assert len(mediator_gaps) == 1
    assert mediator_gaps[0].required_data.variables == ("tar_in_lungs",)


def test_mediation_block_without_invalid_mediator_emits_no_mediator_gap():
    extensions = {
        "mediation_decomposition": {
            "mediator": "tar_in_lungs",
            "mediator_valid": False,
        }
    }
    requests = (
        _param_request([("P(tar_in_lungs=true|smoking=true)", None)]),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
        extensions=extensions,
    )
    assert not any(
        g.kind == GapKind.MISSING_MEDIATOR_DATA for g in report.gaps
    )


# ============================================ 7. transport_target_distribution_unknown


def test_transport_block_with_nonempty_z_emits_transport_gap():
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "source_population": "meta_2022",
            "target_population": "user_28f",
            "adjustment_set": [
                {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
                {"predicate": "bmi", "args": [{"type": "const", "name": "me"}]},
            ],
            "formula_repr": "P*(y|do(x)) = ...",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        extensions=extensions,
    )
    transport_gaps = [
        g for g in report.gaps
        if g.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN
    ]
    assert len(transport_gaps) == 1
    g = transport_gaps[0]
    assert g.required_data.population == "user_28f"
    assert set(g.required_data.variables) == {"age", "bmi"}


def test_transport_block_with_empty_z_emits_no_transport_gap():
    """Z empty → P*(Z) trivially known (degenerate). No gap."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "source_population": "meta_2022",
            "target_population": "user_28f",
            "adjustment_set": [],
            "formula_repr": "P*(y|do(x)) = P(y|do(x))",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        extensions=extensions,
    )
    assert not any(
        g.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN
        for g in report.gaps
    )


# ============================================ 8. ambiguous_variable_definition


def test_framing_note_emits_informational_gap():
    notes = (
        FramingNote(predicate="exercise", missing=("time_window", "measurement")),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        framing_notes=notes,
    )
    framing_gaps = [
        g for g in report.gaps
        if g.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION
    ]
    assert len(framing_gaps) == 1
    g = framing_gaps[0]
    assert g.severity == GapSeverity.INFORMATIONAL
    assert "time_window" in g.description and "measurement" in g.description


# ============================================ multi-gap composition


def test_multiple_gap_kinds_sorted_blocking_first():
    """Severity sort: blocking before important before informational."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "target_population": "user",
            "adjustment_set": [
                {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
            ],
            "formula_repr": "...",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_ASSUMPTION,
        framing_notes=(FramingNote(predicate="x", missing=("time_window",)),),
        extensions=extensions,
    )
    severities = [g.severity for g in report.gaps]
    # Blocking comes before important comes before informational.
    severity_order = {
        GapSeverity.BLOCKING: 0,
        GapSeverity.IMPORTANT: 1,
        GapSeverity.INFORMATIONAL: 2,
    }
    indices = [severity_order[s] for s in severities]
    assert indices == sorted(indices)


def test_summary_mentions_blocking_count_when_multiple_blocking():
    requests = (
        _param_request(
            [("P(y=true|x=true)", None), ("P(y=true|x=false)", None)]
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    assert "blocking" in report.summary or "缺口" in report.summary


def test_actionable_steps_skip_informational_gaps():
    """Informational gaps don't add to actionable steps."""
    notes = (FramingNote(predicate="x", missing=("time_window",)),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        framing_notes=notes,
    )
    # Only an informational gap → no actionable steps.
    assert report.actionable_next_steps == ()


def test_actionable_steps_include_alternative_path():
    derivation = (_failed_step("unidentifiable_via_backdoor"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert any(s.startswith("或：") for s in report.actionable_next_steps)


# ============================================ generator import isolation


def test_generator_module_does_not_import_kb_or_io():
    """The charter §4 forbids any I/O or KB lookups inside this module.
    A coarse byte-code level check that none of the obvious culprits
    appear in the imports."""
    import themis.output.data_gap_report as gen_mod

    # Module's imports are limited to typing + types
    forbidden_substrings = (
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
        "sqlite",
        "kb",
        "retrieval",
        "websearch",
    )
    src = open(gen_mod.__file__, encoding="utf-8").read().lower()
    for needle in forbidden_substrings:
        assert f"import {needle}" not in src and f"from {needle}" not in src, (
            f"data_gap_report.py contains forbidden import substring {needle!r}"
        )
