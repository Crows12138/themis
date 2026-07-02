"""Cinelli-Hazlett omitted-variable-bias sensitivity analysis.

The regression-scale complement to the E-value: the robustness value,
partial R², and confounder-strength benchmark bounds for a linear
treatment effect. Everything is a closed form of the fit's t-value +
residual dof, so this suite pins:

1. **Formula correctness** against the sensemakr reference (its Darfur
   example: t=4.18445, dof=783 → RV_q=0.13878, RV_{q,α}=0.07626,
   partial R²=0.02187, and the 'female' benchmark bound). These are
   external golden values, not self-generated.
2. **End-to-end attachment** to backdoor_linear estimates + schema
   validation + independent re-derivation by the verifier.
3. **Verifier independence** — a second transcription of the formulas
   rejects tampered robustness values and benchmark bounds.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from themis import kernel
from themis.estimation.sensitivity_ovb import (
    adjusted_estimate,
    bias,
    estimate_ovb_sensitivity,
    ovb_partial_r2_bound,
    partial_r2,
    robustness_value,
)
from themis.input.syntactic_validator import validate_result
from themis.verifier.verify import VerificationError, verify_ovb_sensitivity


# ======================================================= sensemakr golden values


def test_partial_r2_matches_reference():
    assert partial_r2(2, 10) == pytest.approx(2 ** 2 / (2 ** 2 + 10))
    assert partial_r2(4.18445, 783) == pytest.approx(0.02187, abs=1e-4)   # Darfur
    assert partial_r2(37.5, 983) == pytest.approx(0.59, abs=1e-2)


def test_robustness_value_q_matches_reference():
    # RV_q = robustness_value with alpha=1 (f_crit=0).
    assert robustness_value(4.18445, 783, q=1, alpha=1.0) == pytest.approx(0.13878, abs=1e-4)
    assert robustness_value(1.89, 1121) == pytest.approx(0.055, abs=1e-2)
    assert robustness_value(37.5, 983) == pytest.approx(0.68, abs=1e-2)
    assert robustness_value(17, 983) == pytest.approx(0.415, abs=1e-2)


def test_robustness_value_qa_matches_darfur():
    # RV_{q,α} at α=0.05 for the Darfur treatment effect.
    assert robustness_value(4.18445, 783, q=1, alpha=0.05) == pytest.approx(0.07626, abs=1e-4)


def test_robustness_value_null_effect_is_fragile():
    # A tiny t-value ⇒ RV near 0 (any confounder overturns it).
    assert robustness_value(0.1, 500) < 0.01


def test_robustness_value_huge_effect_is_robust():
    # A huge t-value ⇒ RV near 1.
    assert robustness_value(200, 500) > 0.9


def test_bound_formula_clean_case():
    # r2dxj_x=0.1, r2yxj_dx=0.2, kd=ky=1 → exact (1/9)/(8/9)=... r2dz_x=1/9,
    # r2yz_dx = (10/sqrt(80))^2 * (0.2/0.8) = 1.25*0.25 = 0.3125.
    r2dz_x, r2yz_dx = ovb_partial_r2_bound(0.1, 0.2, kd=1.0, ky=1.0)
    assert r2dz_x == pytest.approx(1.0 / 9.0, abs=1e-9)
    assert r2yz_dx == pytest.approx(0.3125, abs=1e-9)


def test_bound_formula_darfur_female():
    # The 'female' benchmark inputs (recovered from the sensemakr golden
    # outputs) reproduce the reported r2dz_x / r2yz_dx.
    r2dz_x, r2yz_dx = ovb_partial_r2_bound(0.009077, 0.10904, kd=1.0, ky=1.0)
    assert r2dz_x == pytest.approx(0.00916, abs=1e-4)
    assert r2yz_dx == pytest.approx(0.12464, abs=1e-3)


def test_bias_and_adjusted_estimate_closed_form():
    # bias = BF·se·√dof; adjusted = est − bias (reduce).
    se, dof, est = 0.02, 100, 0.5
    r2dz, r2yz = 0.05, 0.1
    bf = math.sqrt(r2yz * r2dz / (1 - r2dz))
    expected_bias = bf * se * math.sqrt(dof)
    assert bias(r2dz, r2yz, se=se, dof=dof) == pytest.approx(expected_bias, abs=1e-12)
    assert adjusted_estimate(est, r2dz, r2yz, se=se, dof=dof) == pytest.approx(
        est - expected_bias, abs=1e-12,
    )


# ======================================================= end-to-end estimator


def _confounded_df(rng, n=2000):
    x1 = rng.normal(0, 1, n)
    x2 = rng.normal(0, 1, n)
    d = 0.6 * x1 + 0.3 * x2 + rng.normal(0, 1, n)
    y = 1.0 * d + 2.0 * x1 + 0.5 * x2 + rng.normal(0, 1, n)   # true ATE = 1
    return pd.DataFrame({"D": d, "Y": y, "X1": x1, "X2": x2})


def test_estimator_recovers_ols_coefficient_and_strong_rv():
    df = _confounded_df(np.random.default_rng(0))
    s = estimate_ovb_sensitivity(df, treatment="D", outcome="Y",
                                 adjustment=("X1", "X2"))
    assert s.estimate == pytest.approx(1.0, abs=0.1)     # true ATE
    assert 0.0 < s.robustness_value_q < 1.0
    assert s.robustness_value_q > 0.3                    # strong effect ⇒ robust
    assert s.robustness_value_qa <= s.robustness_value_q
    assert {b.covariate for b in s.benchmarks} == {"X1", "X2"}


def test_void_benchmark_is_flagged_not_dropped():
    """A covariate so strongly tied to the outcome that the implied
    confounder R² exceeds 1 is marked valid=False with None bounds, not
    silently dropped."""
    df = _confounded_df(np.random.default_rng(0))
    s = estimate_ovb_sensitivity(df, treatment="D", outcome="Y",
                                 adjustment=("X1", "X2"))
    x1 = next(b for b in s.benchmarks if b.covariate == "X1")
    assert x1.valid is False
    assert x1.adjusted_estimate is None
    x2 = next(b for b in s.benchmarks if b.covariate == "X2")
    assert x2.valid is True
    assert x2.adjusted_estimate is not None
    # a confounder as strong as X2 shrinks the effect but keeps its sign
    assert 0 < x2.adjusted_estimate < s.estimate


def test_unknown_benchmark_covariate_raises():
    df = _confounded_df(np.random.default_rng(0))
    with pytest.raises(ValueError):
        estimate_ovb_sensitivity(df, treatment="D", outcome="Y",
                                 adjustment=("X1",), benchmark_covariates=("Z9",))


# ======================================================= public path + verifier


def _program():
    D = {"predicate": "D", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    X1 = {"predicate": "X1", "args": [{"type": "const", "name": "u"}]}
    X2 = {"predicate": "X2", "args": [{"type": "const", "name": "u"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "D"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "variable", "predicate": "X1"},
            {"kind": "variable", "predicate": "X2"},
            {"kind": "cause", "from": X1, "to": D},
            {"kind": "cause", "from": X2, "to": D},
            {"kind": "cause", "from": X1, "to": Y},
            {"kind": "cause", "from": X2, "to": Y},
            {"kind": "cause", "from": D, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": D, "value": True}, "given": []}},
        ],
    }


def _estimate_result():
    df = _confounded_df(np.random.default_rng(0))
    prog = _program()
    r = kernel.estimate(prog, df, random_state=1)["results"][0]
    return prog, r


def test_public_path_attaches_validates_and_verifies():
    prog, r = _estimate_result()
    ne = r["numeric_estimate"]
    assert ne["method"] == "backdoor_linear"
    assert "ovb_sensitivity" in ne
    validate_result(r)          # schema
    kernel.verify(prog, r)      # independent OVB re-derivation accepts


def test_not_attached_to_logistic_outcome():
    """OVB is the OLS-coefficient framework; a binary (logistic) outcome
    estimate does not carry the block."""
    rng = np.random.default_rng(1)
    n = 2000
    x = rng.normal(0, 1, n)
    d = rng.binomial(1, 1 / (1 + np.exp(-x))).astype(bool)
    y = rng.binomial(1, 1 / (1 + np.exp(-(0.5 * d + x)))).astype(bool)
    df = pd.DataFrame({"D": d, "Y": y, "X1": x})
    D = {"predicate": "D", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    X1 = {"predicate": "X1", "args": [{"type": "const", "name": "u"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "D"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "variable", "predicate": "X1"},
            {"kind": "cause", "from": X1, "to": D},
            {"kind": "cause", "from": X1, "to": Y},
            {"kind": "cause", "from": D, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": D, "value": True}, "given": []}},
        ],
    }
    r = kernel.estimate(prog, df, random_state=1)["results"][0]
    assert r["numeric_estimate"]["method"] == "backdoor_logistic"
    assert "ovb_sensitivity" not in r["numeric_estimate"]


def test_verifier_accepts_correct_block():
    _, r = _estimate_result()
    verify_ovb_sensitivity(r["numeric_estimate"]["ovb_sensitivity"])  # no raise


def test_verifier_rejects_tampered_robustness_value():
    _, r = _estimate_result()
    block = dict(r["numeric_estimate"]["ovb_sensitivity"])
    block["robustness_value_q"] = 0.999
    with pytest.raises(VerificationError):
        verify_ovb_sensitivity(block)


def test_verifier_rejects_tampered_partial_r2():
    _, r = _estimate_result()
    block = dict(r["numeric_estimate"]["ovb_sensitivity"])
    block["partial_r2"] = 0.123
    with pytest.raises(VerificationError):
        verify_ovb_sensitivity(block)


def test_verifier_rejects_tampered_benchmark_bound():
    prog, r = _estimate_result()
    r["numeric_estimate"]["ovb_sensitivity"]["benchmarks"][-1]["r2dz_x"] = 0.5
    with pytest.raises((VerificationError, Exception)):
        kernel.verify(prog, r)


def test_verifier_rejects_flipped_valid_flag():
    _, r = _estimate_result()
    block = r["numeric_estimate"]["ovb_sensitivity"]
    # X1 is void (valid=False); claiming it valid must be rejected.
    x1 = next(b for b in block["benchmarks"] if b["covariate"] == "X1")
    x1["valid"] = True
    with pytest.raises(VerificationError):
        verify_ovb_sensitivity(block)
