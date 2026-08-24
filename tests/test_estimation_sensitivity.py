"""Phase 8.2 — unit tests for E-value sensitivity analysis."""
from __future__ import annotations

import math
import re

import pytest

from themis.estimation.sensitivity import (
    EValueResult,
    Undefined,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
)


def _because(result: EValueResult) -> Undefined:
    """Which of the four stopped this, as the member rather than the token."""
    return Undefined.named(result.undefined_because["token"])


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
    assert _because(result) == Undefined.BASELINE_ON_BOUNDARY


def test_e_value_handles_baseline_at_one():
    result = e_value_from_ate_binary(ate=-0.1, baseline_rate=1.0)
    assert result.e_value is None
    assert _because(result) == Undefined.BASELINE_ON_BOUNDARY


def test_e_value_handles_treated_rate_outside_unit():
    """ATE=0.5 with baseline 0.7 implies treated rate 1.2 — invalid."""
    result = e_value_from_ate_binary(ate=0.5, baseline_rate=0.7)
    assert result.e_value is None
    assert _because(result) == Undefined.TREATED_RATE_OUT_OF_RANGE
    # The rate that decided it travels beside the reason, so the sentence a
    # reader gets can name it without this module having written one.
    assert result.undefined_because["said"] == {"rate": "1.200"}


# ============================================ note interpretation


def test_the_point_bands_the_result_when_no_interval_was_given():
    """Both of these are called without a CI bound, so the point estimate is
    the only number there is — which the result says rather than leaving to
    be inferred from a field being absent."""
    fragile = e_value_from_ate_binary(ate=0.05, baseline_rate=0.5)
    # Treated 0.55, RR ≈ 1.10, E ≈ 1.43
    assert fragile.e_value is not None and fragile.e_value < 1.5
    assert (fragile.interpretation_band, fragile.band_basis) == (
        "fragile", "point")

    robust = e_value_from_ate_binary(ate=0.7, baseline_rate=0.05)
    # Treated 0.75, RR=15, E ≈ 29.5
    assert robust.e_value > 5.0
    assert (robust.interpretation_band, robust.band_basis) == (
        "very_robust", "point")


def test_a_result_that_has_a_number_says_nothing_in_words():
    """What the reading being a field became, once the rest went too.

    The reading was a fifth clause of a sentence this module wrote, worded
    one way here and another on the continuous route — so it became a field.
    The other four clauses were the four numbers beside them said again, and
    they are gone on the same ground: every one of them is on the result, so
    the sentence was the reader surface's to compose and this module's only
    by accident of who held the values first.
    """
    result = e_value_from_ate_binary(ate=0.7, baseline_rate=0.05)
    assert result.e_value is not None
    assert result.undefined_because is None
    # The two strings left are tokens, which is what a token looks like: no
    # language wrote them, so no reader is owed a translation of them.
    assert all(re.fullmatch(r"[a-z_]+", value)
               for value in vars(result).values() if isinstance(value, str))


# ============================================ shape


def test_result_is_immutable_dataclass():
    result = e_value_from_ate_binary(ate=0.1, baseline_rate=0.2)
    with pytest.raises((AttributeError, Exception)):
        result.e_value = 99.0  # frozen dataclass should reject
