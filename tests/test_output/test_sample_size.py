"""Tests for themis.output.sample_size + the wire-in inside
data_gap_report._classify_missing_distribution."""
from __future__ import annotations

import math

import pytest

from themis.output.sample_size import (
    DEFAULT_COHENS_H,
    DEFAULT_PROPORTION_PRECISION,
    estimate_min_n_mediation_nde_nie,
    estimate_min_n_single_proportion,
    estimate_min_n_two_arm_binary,
    is_binary_outcome_distribution,
)


# ---------------------------------------------------------------- core math

def test_two_arm_binary_default_round_number():
    """Cohen's h=0.2, α=0.05 two-sided, power=0.80, two-arm equal:
    n_per_arm = (1.96 + 0.84)² / 0.04 ≈ 196 → total 392 → rounded 400."""
    n, note = estimate_min_n_two_arm_binary()
    assert n == 400
    assert "Cohen" in note
    assert "0.2" in note
    assert "0.05" in note
    assert "0.80" in note


def test_two_arm_binary_larger_h_smaller_n():
    """h=0.5 (medium-large effect) needs ~32 per arm = 64 total → 100
    after round-up-50."""
    n, _ = estimate_min_n_two_arm_binary(cohens_h=0.5)
    assert n == 100  # 32/arm × 2 = 64, rounded up to 100


def test_two_arm_binary_small_h_huge_n():
    """h=0.05 (very small effect) → thousands needed."""
    n, _ = estimate_min_n_two_arm_binary(cohens_h=0.05)
    assert n > 5000


def test_two_arm_binary_rejects_zero_h():
    with pytest.raises(ValueError, match="positive"):
        estimate_min_n_two_arm_binary(cohens_h=0)


def test_two_arm_binary_rejects_negative_h():
    with pytest.raises(ValueError, match="positive"):
        estimate_min_n_two_arm_binary(cohens_h=-0.1)


def test_single_proportion_default():
    """p=0.5 worst case, ±0.03 precision, 95%:
    n = 1.96² × 0.25 / 0.03² ≈ 1067 → rounded 1100."""
    n, note = estimate_min_n_single_proportion()
    assert n == 1100
    assert "p=0.5" in note
    assert "0.03" in note


def test_single_proportion_tighter_precision():
    """Halving precision should ~quadruple n."""
    n_3pp, _ = estimate_min_n_single_proportion(precision=0.03)
    n_15pp, _ = estimate_min_n_single_proportion(precision=0.015)
    assert n_15pp >= 3 * n_3pp


def test_single_proportion_rejects_invalid_p():
    with pytest.raises(ValueError, match="0, 1"):
        estimate_min_n_single_proportion(p_assumed=0)
    with pytest.raises(ValueError, match="0, 1"):
        estimate_min_n_single_proportion(p_assumed=1)


def test_single_proportion_rejects_zero_precision():
    with pytest.raises(ValueError, match="positive"):
        estimate_min_n_single_proportion(precision=0)


def test_round_to_50():
    """Power-analysis round-numbers; never single-person precision."""
    n, _ = estimate_min_n_two_arm_binary()
    assert n % 50 == 0
    n2, _ = estimate_min_n_single_proportion()
    assert n2 % 50 == 0


# ----------------------------------------------- binary-outcome heuristic

def test_is_binary_detects_lower_true():
    assert is_binary_outcome_distribution("P(y=true|x=true)")


def test_is_binary_detects_upper_true():
    assert is_binary_outcome_distribution("P(Y=True|X=True)")


def test_is_binary_detects_false():
    assert is_binary_outcome_distribution("P(y=false|x=true)")


def test_is_binary_detects_marginal_form():
    assert is_binary_outcome_distribution("P(belly_fat_loss=True)")


def test_is_binary_rejects_no_value():
    """Continuous-style display: no =true/=false on target side."""
    assert not is_binary_outcome_distribution("P(y|x)")


def test_is_binary_rejects_conditioning_side_only():
    """A bool on the conditioning side alone shouldn't trigger — we
    care about the outcome's dtype."""
    assert not is_binary_outcome_distribution("P(y_continuous|x=true)")


def test_is_binary_handles_no_p_prefix():
    """Robustness — if upstream forgot the leading 'P('."""
    assert is_binary_outcome_distribution("y=true|x=true")


# ----------------------------------------------- E2E wire-in to gap report

def test_gap_report_fills_min_sample_size_for_binary_conditional():
    """End-to-end: a missing P(y=true|x=true) gap should carry
    min_sample_size=400 with the Cohen-h precision target."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    target = "parameter:P(y=true|x=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(target=target),),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(req,),
        framing_notes=(),
        extensions=None,
    )
    assert report is not None
    gap = next(g for g in report.gaps if g.kind.value == "missing_distribution")
    assert gap.required_data is not None
    assert gap.required_data.min_sample_size == 400
    assert "Cohen" in gap.required_data.precision_target


def test_gap_report_fills_min_sample_size_for_binary_marginal():
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    target = "parameter:P(y=True)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(target=target),),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(req,),
        framing_notes=(),
        extensions=None,
    )
    gap = next(g for g in report.gaps if g.kind.value == "missing_distribution")
    assert gap.required_data.min_sample_size == 1100
    assert "p=0.5" in gap.required_data.precision_target


def test_gap_report_leaves_min_sample_size_unset_for_continuous():
    """No bool tokens → continuous outcome → min_sample_size stays None
    (we don't bluff power calc for continuous)."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    target = "parameter:P(systolic_bp|aspirin=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(target=target),),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(req,),
        framing_notes=(),
        extensions=None,
    )
    gap = next(g for g in report.gaps if g.kind.value == "missing_distribution")
    assert gap.required_data.min_sample_size is None
    assert gap.required_data.precision_target is None


# ----------------------------------------------- mediation NDE/NIE

def test_mediation_default_inflation():
    """Default inflation 2.5× over simple ATE n (=400) → 1000."""
    n, note = estimate_min_n_mediation_nde_nie()
    assert n == 1000
    assert "NDE" in note and "NIE" in note
    assert "VanderWeele" in note


def test_mediation_custom_inflation_factor():
    n_2, _ = estimate_min_n_mediation_nde_nie(inflation_factor=2.0)
    n_3, _ = estimate_min_n_mediation_nde_nie(inflation_factor=3.0)
    assert n_3 > n_2


def test_mediation_rejects_zero_inflation():
    with pytest.raises(ValueError, match="positive"):
        estimate_min_n_mediation_nde_nie(inflation_factor=0)


def test_mediation_rounds_to_50():
    n, _ = estimate_min_n_mediation_nde_nie()
    assert n % 50 == 0


def test_gap_report_fills_min_sample_size_for_binary_mediator():
    """End-to-end: a missing P(M=true|X=true) parameter request alongside
    a mediation_decomposition extension should attach the 1000-n
    mediation heuristic on the mediator gap."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    mediator = "low_bmi"
    target = f"parameter:P({mediator}=true|exercise=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(target=target),),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(req,),
        framing_notes=(),
        extensions={
            "mediation_decomposition": {
                "mediator": mediator,
                "mediator_valid": True,
            },
        },
    )
    assert report is not None
    gap = next(
        g for g in report.gaps if g.kind.value == "missing_mediator_data"
    )
    assert gap.required_data is not None
    assert gap.required_data.min_sample_size == 1000
    assert "NDE" in gap.required_data.precision_target


def test_gap_report_leaves_mediator_n_unset_for_continuous():
    """Continuous mediator → no min_sample_size."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    mediator = "bmi_continuous"
    target = f"parameter:P({mediator}|exercise=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(target=target),),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=(),
        investigation_requests=(req,),
        framing_notes=(),
        extensions={
            "mediation_decomposition": {
                "mediator": mediator,
                "mediator_valid": True,
            },
        },
    )
    gap = next(
        g for g in report.gaps if g.kind.value == "missing_mediator_data"
    )
    assert gap.required_data.min_sample_size is None
    assert gap.required_data.precision_target is None
