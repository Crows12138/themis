"""Tests for themis.output.sample_size + the wire-in inside
data_gap_report._species_missing_distribution."""
from __future__ import annotations

import math

import pytest

from themis.output.data_gap_report import asked
from themis.output.sample_size import (
    DEFAULT_COHENS_D,
    DEFAULT_COHENS_H,
    DEFAULT_PROPORTION_PRECISION,
    Measured,
    estimate_min_n_mediation_nde_nie,
    estimate_min_n_single_proportion,
    estimate_min_n_transport_source_conditional,
    estimate_min_n_transport_target_marginal,
    estimate_min_n_two_arm_binary,
    estimate_min_n_two_arm_continuous,
    estimate_n_for_target_ci_half_width,
)
from themis.types import GapKind


def statement(predicate, value, given=()):
    """The paste-ready statement a parameter ask files with its gap.

    Same shape as ``scheduler._skeleton_for_parameter`` builds, written
    out here so a test states the ask's shape instead of spelling a
    ``P(...)`` and leaving the reader to work out which fact it was
    relying on.
    """
    return {
        "kind": "probability",
        "target": {"atom": {"predicate": predicate, "args": []},
                   "value": value},
        "given": [{"atom": {"predicate": p, "args": []}, "value": v}
                  for p, v in given],
        "value": None,
        "annotations": {"source": "TODO"},
    }


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


# ------------------------------------------- the shape the ask states

def test_a_truth_value_is_a_proportion():
    assert asked(statement("y", True, [("x", True)])) == (
        Measured.PROPORTION, 1, frozenset({"y", "x"}))
    assert asked(statement("y", False)) == (
        Measured.PROPORTION, 0, frozenset({"y"}))


def test_a_number_is_a_mean():
    assert asked(statement("systolic_bp", 140, [("salt", True)])) == (
        Measured.MEAN, 1, frozenset({"systolic_bp", "salt"}))
    assert asked(statement("score", 0.85)) == (
        Measured.MEAN, 0, frozenset({"score"}))


def test_a_truth_value_on_the_conditioning_side_does_not_decide_it():
    """What the target is measured on is the target's fact. A bool in
    ``given`` says what stratum is asked for, not what the answer is."""
    ask = asked(statement("systolic_bp", 140, [("x", True), ("z", False)]))
    assert ask.measured is Measured.MEAN
    assert ask.given == 2


def test_a_categorical_level_is_neither_and_says_so():
    """Nothing here sizes a category, and the ask still has a signature —
    which is why this is not the same answer as no statement at all."""
    ask = asked(statement("dose", "high", [("x", True)]))
    assert ask.measured is None
    assert ask.conditional


def test_no_statement_is_not_the_same_answer_as_an_unsizeable_one():
    assert asked(None) is None
    assert asked("P(y=true|x=true)") is None
    assert asked({"kind": "probability"}) is None


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
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
            skeleton=statement("y", True, [("x", True)]),
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
            skeleton=statement("y", True),
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


def _distribution_gap(target, skeleton):
    from themis.output.data_gap_report import compute_data_gap_report
    from themis.types import (
        InvestigationAction,
        InvestigationItem,
        InvestigationRequest,
        Priority,
        QueryKind,
        ResultStatus,
    )

    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
            skeleton=skeleton,
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
    return next(
        g for g in report.gaps if g.kind.value == "missing_distribution")


def test_gap_report_leaves_min_sample_size_unset_for_an_unsizeable_value():
    """The ask states its shape and it is neither a proportion nor a
    mean — can't pick between Cohen's h and Cohen's d → leave
    min_sample_size None rather than bluff. The signature survives: what
    stratum is asked for does not depend on what the answer is measured
    on."""
    gap = _distribution_gap(
        "parameter:P(dose=high|aspirin=true)",
        statement("dose", "high", [("aspirin", True)]),
    )
    assert gap.required_data.min_sample_size is None
    assert gap.required_data.precision_target is None
    assert gap.signature == "conditional"


def test_gap_report_states_no_signature_when_the_ask_stated_no_shape():
    """A gap filed without a statement knows nothing about its shape, and
    says nothing rather than guessing — an adapter reads the signature as
    a claim about where to go looking."""
    gap = _distribution_gap("parameter:P(systolic_bp|aspirin=true)", None)
    assert gap.required_data.min_sample_size is None
    assert gap.required_data.precision_target is None
    assert gap.signature is None


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
            skeleton=statement(mediator, True, [("exercise", True)]),
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
    target = f"parameter:P({mediator}=27.5|exercise=true)"
    req = InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=target,
        priority=Priority.HIGH,
        group="parameter",
        items=(InvestigationItem(
            target=target, gap=GapKind.MISSING_DISTRIBUTION,
            skeleton=statement(mediator, 27.5, [("exercise", True)]),
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


def test_gap_report_fills_min_sample_size_for_continuous_conditional():
    """End-to-end: a mean, conditioned on → Cohen's d → n=150."""
    gap = _distribution_gap(
        "parameter:P(systolic_bp=140|salt=true)",
        statement("systolic_bp", 140, [("salt", True)]),
    )
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
            "s_nodes": [],
            "sources": [{
                "source_population": "src",
                "s_nodes": [],
                "transportable": True,
                "adjustment_set": [
                    {"predicate": "age_group", "args": []},
                ],
                "formula_repr": "P*(recovery|do(drug)) = ...",
            }],
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
    assert "每一层" in src.required_data.precision_target
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
