"""Tests for themis.output.sample_size + the wire-in inside
data_gap_report._classify_missing_distribution."""
from __future__ import annotations

import math

import pytest

from themis.output.sample_size import (
    DEFAULT_COHENS_D,
    DEFAULT_COHENS_H,
    DEFAULT_PROPORTION_PRECISION,
    estimate_min_n_mediation_nde_nie,
    estimate_min_n_single_proportion,
    estimate_min_n_transport_source_conditional,
    estimate_min_n_transport_target_marginal,
    estimate_min_n_two_arm_binary,
    estimate_min_n_two_arm_continuous,
    estimate_n_for_target_ci_half_width,
    is_binary_outcome_distribution,
    is_continuous_outcome_distribution,
)
from themis.types import GapKind


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
    GapKind,
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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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


def test_gap_report_leaves_min_sample_size_unset_for_unknown_outcome():
    """Outcome shape unknown — neither =true/false nor =<number> on the
    target side → can't pick between Cohen's h and Cohen's d → leave
    min_sample_size None rather than bluff."""
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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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


# ----------------------------------------------- transport stratified

def test_transport_source_one_stratum_equals_simple_ate():
    n_simple, _ = estimate_min_n_two_arm_binary()
    n_src, _ = estimate_min_n_transport_source_conditional(n_strata=1)
    assert n_src == n_simple


def test_transport_source_scales_linearly_with_strata():
    n1, _ = estimate_min_n_transport_source_conditional(n_strata=1)
    n4, _ = estimate_min_n_transport_source_conditional(n_strata=4)
    assert n4 == 4 * n1


def test_transport_source_rejects_zero_strata():
    with pytest.raises(ValueError, match=">=1"):
        estimate_min_n_transport_source_conditional(n_strata=0)


def test_transport_target_one_stratum_equals_single_proportion():
    n_sp, _ = estimate_min_n_single_proportion()
    n_tgt, _ = estimate_min_n_transport_target_marginal(n_strata=1)
    assert n_tgt == n_sp


def test_transport_target_scales_linearly_with_strata():
    n1, _ = estimate_min_n_transport_target_marginal(n_strata=1)
    n4, _ = estimate_min_n_transport_target_marginal(n_strata=4)
    assert n4 == 4 * n1


# ----------------------------------------------- continuous outcome (Cohen's d)

def test_two_arm_continuous_default_round_number():
    """d=0.5 (medium): n_per_arm = 2·(1.96+0.84)²/0.25 ≈ 63 → 126 → 150
    after round-up-50."""
    n, note = estimate_min_n_two_arm_continuous()
    assert n == 150
    assert "Cohen" in note and "d=0.5" in note


def test_two_arm_continuous_small_d_huge_n():
    n, _ = estimate_min_n_two_arm_continuous(cohens_d=0.2)
    assert n > 700  # ~784, rounded → 800


def test_two_arm_continuous_rejects_zero_d():
    with pytest.raises(ValueError, match="positive"):
        estimate_min_n_two_arm_continuous(cohens_d=0)


def test_is_continuous_detects_numeric_target():
    assert is_continuous_outcome_distribution("P(systolic_bp=140|salt=true)")
    assert is_continuous_outcome_distribution("P(wage=50000)")
    assert is_continuous_outcome_distribution("P(score=0.85|x=true)")


def test_is_continuous_rejects_binary():
    assert not is_continuous_outcome_distribution("P(y=true|x=true)")
    assert not is_continuous_outcome_distribution("P(y=False)")


def test_is_continuous_rejects_no_value():
    """Marginal P(systolic_bp|...) with no =N on target side is shape-
    unknown — leave both detectors False so caller skips power calc."""
    assert not is_continuous_outcome_distribution("P(systolic_bp|aspirin=true)")


def test_gap_report_fills_min_sample_size_for_continuous_conditional():
    """End-to-end: P(systolic_bp=140|salt=true) → continuous conditional
    → Cohen's d → n=150."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    target = "parameter:P(systolic_bp=140|salt=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
        ),),
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
    assert gap.required_data.min_sample_size == 150
    assert "Cohen" in gap.required_data.precision_target
    assert "d=0.5" in gap.required_data.precision_target


def test_gap_report_fills_min_sample_size_for_transport_gaps():
    """E2e: transport_identification with binary adjustment set of size 1
    → 2 strata. Source gap gets 800 (=2×400), target gap gets 2200
    (=2×1100)."""
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import QueryKind, ResultStatus

    extensions = {
        "transport_identification": {
            "target_population": "tgt",
            "source_population": "src",
            "adjustment_set": [
                {"predicate": "age_group", "args": []},
            ],
            "formula_repr": "P*(recovery|do(drug)) = ...",
        },
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        derivation=(),
        investigation_requests=(),
        framing_notes=(),
        extensions=extensions,
    )
    src = next(
        g for g in report.gaps
        if g.kind.value == "transport_source_conditional_unknown"
    )
    tgt = next(
        g for g in report.gaps
        if g.kind.value == "transport_target_distribution_unknown"
    )
    assert src.required_data.min_sample_size == 800
    assert "stratum" in src.required_data.precision_target
    assert tgt.required_data.min_sample_size == 2200
    assert "P*(Z)" in tgt.required_data.precision_target


# ----------------------------------------- post-hoc precision budgeting


def test_post_hoc_halve_ci_requires_4x_n():
    """SE ∝ 1/√N → halving CI half-width needs 4× the samples.
    Pure σ-free arithmetic: N_old=400, W_old=0.10, W_new=0.05 →
    N_new = 400 · 4 = 1600."""
    n, hint = estimate_n_for_target_ci_half_width(
        current_n=400,
        current_ci_half_width=0.10,
        target_ci_half_width=0.05,
    )
    assert n == 1600
    assert "1600" in hint
    assert "4.00" in hint  # ratio² = (0.10/0.05)² = 4


def test_post_hoc_no_change_when_target_equals_current():
    """If target == current, n_new = n_old (no extra samples)."""
    n, _ = estimate_n_for_target_ci_half_width(
        current_n=300,
        current_ci_half_width=0.08,
        target_ci_half_width=0.08,
    )
    assert n == 300


def test_post_hoc_loosen_target_returns_smaller_n():
    """If user accepts a wider CI, can downsize. N_old=1000, W_old=0.04,
    W_new=0.08 → N_new = 1000 · 0.25 = 250."""
    n, _ = estimate_n_for_target_ci_half_width(
        current_n=1000,
        current_ci_half_width=0.04,
        target_ci_half_width=0.08,
    )
    assert n == 250


def test_post_hoc_round_up_to_50():
    """Edge case: 333 rounds up to 350."""
    n, _ = estimate_n_for_target_ci_half_width(
        current_n=333,
        current_ci_half_width=0.10,
        target_ci_half_width=0.10,
    )
    # ratio² = 1.0 → exact 333 → round up to 350
    assert n == 350


def test_post_hoc_rejects_invalid_inputs():
    with pytest.raises(ValueError, match="current_n"):
        estimate_n_for_target_ci_half_width(
            current_n=0,
            current_ci_half_width=0.1,
            target_ci_half_width=0.05,
        )
    with pytest.raises(ValueError, match="current_ci_half_width"):
        estimate_n_for_target_ci_half_width(
            current_n=100,
            current_ci_half_width=0.0,
            target_ci_half_width=0.05,
        )
    with pytest.raises(ValueError, match="target_ci_half_width"):
        estimate_n_for_target_ci_half_width(
            current_n=100,
            current_ci_half_width=0.1,
            target_ci_half_width=-0.05,
        )
