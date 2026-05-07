"""Iter 124 — E-value sensitivity for continuous-outcome ATE.

Chinn (2000) SMD→RR approximation: standardised mean difference
d = ATE / SD(Y), then risk ratio ≈ exp(0.91·d). Apply VanderWeele-Ding
(2017) E-value formula on the resulting RR.

Existing binary-outcome path (iter Phase 8.2) is preserved verbatim.
This iter adds a continuous-outcome path so sensitivity attaches to
e.g. backdoor_linear estimates of continuous outcomes too — which
were silently skipped before.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from themis.estimation.sensitivity import (
    CHINN_SMD_TO_LOG_RR,
    EValueResult,
    e_value_for_risk_ratio,
    e_value_from_ate_binary,
    e_value_from_ate_continuous,
)


# ---------------------------------------------------------------------------
# Continuous-outcome unit tests
# ---------------------------------------------------------------------------


def test_continuous_returns_finite_e_value_for_typical_input():
    r = e_value_from_ate_continuous(ate=0.5, outcome_sd=2.0)
    assert r.e_value is not None
    assert r.risk_ratio is not None
    assert r.baseline_rate is None  # standardisation-based, no baseline


def test_continuous_smd_zero_yields_e_value_one():
    """ATE = 0 → SMD = 0 → RR = 1 → E-value = 1 (the trivial null
    confounder explains the null finding)."""
    r = e_value_from_ate_continuous(ate=0.0, outcome_sd=1.5)
    assert r.e_value == pytest.approx(1.0)
    assert r.risk_ratio == pytest.approx(1.0)


def test_continuous_e_value_grows_with_effect_size():
    """Larger ATE/SD ratio → larger SMD → larger RR → larger E-value."""
    small = e_value_from_ate_continuous(ate=0.1, outcome_sd=1.0)
    big = e_value_from_ate_continuous(ate=2.0, outcome_sd=1.0)
    assert small.e_value < big.e_value


def test_continuous_chinn_factor_matches_published_formula():
    """Hand-check: ATE = 1.0, SD = 1.0 → SMD = 1.0 → RR = exp(0.91).
    Then E = RR + sqrt(RR(RR-1))."""
    r = e_value_from_ate_continuous(ate=1.0, outcome_sd=1.0)
    expected_rr = math.exp(CHINN_SMD_TO_LOG_RR * 1.0)
    expected_e = expected_rr + math.sqrt(expected_rr * (expected_rr - 1))
    assert r.risk_ratio == pytest.approx(expected_rr, rel=1e-9)
    assert r.e_value == pytest.approx(expected_e, rel=1e-9)


def test_continuous_negative_ate_symmetric_to_positive():
    """Symmetric: SMD = +1 vs -1 give the same E-value (the formula
    normalises RR to ≥1 before applying e_value_for_risk_ratio)."""
    pos = e_value_from_ate_continuous(ate=0.5, outcome_sd=1.0)
    neg = e_value_from_ate_continuous(ate=-0.5, outcome_sd=1.0)
    assert pos.e_value == pytest.approx(neg.e_value, rel=1e-9)


def test_continuous_ci_bound_yields_smaller_e_value():
    """CI bound closer to null → smaller |SMD| → RR closer to 1 →
    smaller E-value than point estimate's."""
    r = e_value_from_ate_continuous(
        ate=1.0, outcome_sd=1.0, ci_bound=0.3,
    )
    assert r.e_value > r.e_value_ci_bound


def test_continuous_zero_sd_returns_none():
    r = e_value_from_ate_continuous(ate=0.5, outcome_sd=0.0)
    assert r.e_value is None
    assert "non-positive" in r.note or "non-finite" in r.note


def test_continuous_negative_sd_returns_none():
    r = e_value_from_ate_continuous(ate=0.5, outcome_sd=-1.0)
    assert r.e_value is None


def test_continuous_nan_ate_returns_none():
    r = e_value_from_ate_continuous(ate=float("nan"), outcome_sd=1.0)
    assert r.e_value is None
    assert "not finite" in r.note


def test_continuous_inf_sd_returns_none():
    r = e_value_from_ate_continuous(ate=0.5, outcome_sd=float("inf"))
    assert r.e_value is None


def test_continuous_note_describes_chinn_conversion():
    r = e_value_from_ate_continuous(ate=0.5, outcome_sd=2.0)
    assert "Chinn" in r.note
    assert "0.91" in r.note
    assert "SMD" in r.note


def test_continuous_note_includes_interpretation_band():
    """Note must classify the E-value into a strength band so
    response_rendering can quote it without re-deriving."""
    fragile = e_value_from_ate_continuous(ate=0.05, outcome_sd=1.0)
    assert any(
        token in fragile.note for token in ("very weak", "very fragile")
    ) or "脆弱" in fragile.note

    robust = e_value_from_ate_continuous(ate=10.0, outcome_sd=1.0)
    assert any(
        token in robust.note for token in ("very robust", "robust")
    ) or "稳健" in robust.note


# ---------------------------------------------------------------------------
# Existing binary path is unchanged
# ---------------------------------------------------------------------------


def test_binary_path_still_works_with_baseline():
    r = e_value_from_ate_binary(ate=0.1, baseline_rate=0.3)
    assert r.e_value is not None
    assert r.baseline_rate == 0.3


def test_e_value_for_risk_ratio_one_is_one():
    assert e_value_for_risk_ratio(1.0) == 1.0


# ---------------------------------------------------------------------------
# Dispatch end-to-end: backdoor_linear continuous outcome attaches
# ---------------------------------------------------------------------------


def _continuous_outcome_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y"},  # continuous
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "cont_e_value_test",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": 1,  # Themis effect query needs a value;
                                  # for continuous outcome the "value"
                                  # is essentially ignored by linear
                                  # estimation but schema requires it
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [],
             }},
        ],
    }


def _continuous_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(size=n) < 0.5)
    # Y is continuous: linear function + noise → SD ≈ 1.5-ish
    y = 0.5 * x.astype(float) + 0.3 * z + rng.normal(size=n)
    return pd.DataFrame({"z": z, "x": x, "y": y})


def test_dispatch_attaches_sensitivity_for_continuous_outcome():
    """End-to-end: themis.estimate on a continuous-outcome program
    populates numeric_estimate.sensitivity_analysis (was silently
    skipped before iter 124)."""
    import themis

    out = themis.estimate(_continuous_outcome_program(), _continuous_data())
    result = out["results"][0]
    estimate = result.get("numeric_estimate") or {}
    sens = estimate.get("sensitivity_analysis")
    assert sens is not None, (
        f"sensitivity_analysis missing on continuous-outcome estimate; "
        f"keys: {list(estimate.keys())}"
    )
    assert sens.get("e_value") is not None
    assert sens.get("baseline_rate") is None  # continuous path
    assert "Chinn" in sens.get("note", "")


def test_dispatch_continuous_does_not_break_binary_path():
    """Sanity: a simulated binary-outcome data set still gets the
    classic baseline-rate-based E-value, not the Chinn path."""
    import themis

    # Binary outcome program
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "binary_e_value",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [],
             }},
        ],
    }

    rng = np.random.default_rng(0)
    n = 500
    z = rng.normal(size=n)
    x = (rng.random(size=n) < 0.5)
    p = 1.0 / (1.0 + np.exp(-(0.3 * z + 0.6 * x.astype(float))))
    y = (rng.random(size=n) < p)
    df = pd.DataFrame({"z": z, "x": x, "y": y})

    out = themis.estimate(program, df)
    result = out["results"][0]
    sens = (result.get("numeric_estimate") or {}).get("sensitivity_analysis")
    assert sens is not None
    assert sens.get("baseline_rate") is not None  # binary path filled it
    assert "Chinn" not in sens.get("note", "")  # not continuous path
