"""Phase 8.2 — unit tests for E-value sensitivity analysis."""
from __future__ import annotations

import math

import pytest

from themis.estimation.sensitivity import (
    EValueResult,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
)


# ============================================ canonical formula


def test_e_value_at_rr_one_is_one():
    assert e_value_for_risk_ratio(1.0) == 1.0


def test_e_value_vanderweele_table_examples():
    """VanderWeele 2017 Table 2 worked examples (rounded to 2dp)."""
    # RR=2 → E ≈ 3.41
    assert abs(e_value_for_risk_ratio(2.0) - 3.4142) < 0.01
    # RR=3 → E ≈ 5.45
    assert abs(e_value_for_risk_ratio(3.0) - 5.4495) < 0.01
    # RR=1.5 → E ≈ 2.37
    assert abs(e_value_for_risk_ratio(1.5) - 2.3660) < 0.01


def test_e_value_symmetric_around_one():
    """e_value(rr) == e_value(1/rr) — protective and harmful effects
    of equal magnitude have the same E-value."""
    for rr in (1.5, 2.0, 3.0, 5.0):
        assert abs(
            e_value_for_risk_ratio(rr) - e_value_for_risk_ratio(1.0 / rr)
        ) < 1e-9


def test_e_value_monotone_increasing_above_one():
    prev = e_value_for_risk_ratio(1.01)
    for rr in (1.1, 1.5, 2.0, 5.0, 10.0):
        cur = e_value_for_risk_ratio(rr)
        assert cur > prev
        prev = cur


def test_e_value_rejects_non_positive_rr():
    with pytest.raises(ValueError, match="positive"):
        e_value_for_risk_ratio(0.0)
    with pytest.raises(ValueError, match="positive"):
        e_value_for_risk_ratio(-0.5)


# ============================================ ATE → E-value


def test_e_value_from_ate_typical_case():
    """ATE=0.1 above baseline 0.2 → treated 0.3 → RR=1.5 → E≈2.37."""
    result = e_value_from_ate_binary(ate=0.1, baseline_rate=0.2)
    assert isinstance(result, EValueResult)
    assert abs(result.risk_ratio - 1.5) < 1e-6
    assert abs(result.e_value - 2.366) < 0.01


def test_e_value_from_ate_with_ci_bound():
    result = e_value_from_ate_binary(
        ate=0.15, baseline_rate=0.20, ci_bound=0.05,
    )
    # Point: treated=0.35, RR=1.75, E ≈ 2.91
    assert abs(result.e_value - 2.9047) < 0.01
    # CI bound: treated=0.25, RR=1.25, E ≈ 1.81
    assert abs(result.e_value_ci_bound - 1.808) < 0.02


def test_e_value_handles_baseline_at_zero():
    result = e_value_from_ate_binary(ate=0.1, baseline_rate=0.0)
    assert result.e_value is None
    assert result.risk_ratio is None
    assert "boundary" in result.note


def test_e_value_handles_baseline_at_one():
    result = e_value_from_ate_binary(ate=-0.1, baseline_rate=1.0)
    assert result.e_value is None
    assert "boundary" in result.note


def test_e_value_handles_treated_rate_outside_unit():
    """ATE=0.5 with baseline 0.7 implies treated rate 1.2 — invalid."""
    result = e_value_from_ate_binary(ate=0.5, baseline_rate=0.7)
    assert result.e_value is None
    assert "outside" in result.note


# ============================================ note interpretation


def test_note_flags_weak_evidence_when_e_below_1_5():
    result = e_value_from_ate_binary(ate=0.05, baseline_rate=0.5)
    # Treated 0.55, RR ≈ 1.10, E ≈ 1.43
    assert result.e_value is not None
    assert result.e_value < 1.5
    assert "very weak" in result.note


def test_note_flags_robust_evidence_when_e_above_5():
    result = e_value_from_ate_binary(ate=0.7, baseline_rate=0.05)
    # Treated 0.75, RR=15, E ≈ 29.5 (very robust)
    assert result.e_value > 5.0
    assert "very robust" in result.note


# ============================================ shape


def test_result_is_immutable_dataclass():
    result = e_value_from_ate_binary(ate=0.1, baseline_rate=0.2)
    with pytest.raises((AttributeError, Exception)):
        result.e_value = 99.0  # frozen dataclass should reject
