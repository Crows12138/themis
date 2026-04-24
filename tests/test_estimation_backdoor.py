"""Phase 7.1 S.N.2 — unit tests for the backdoor ATE estimator.

Coverage:
- Correct sign and magnitude on a ground-truth DGP (Y linearly depends on X + Z)
- Logistic model path for bool outcome
- Linear model path for continuous outcome
- Auto model selection
- Empty adjustment set (marginal randomization case)
- Determinism under fixed random_state
- Bootstrap CI brackets the point estimate
- Independence from row order of the DataFrame
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.backdoor import (
    BackdoorEstimate,
    estimate_backdoor_ate,
)


def _linear_dgp(n=500, seed=0, true_ate=2.0, confounding=True):
    """Y = 1.0 * Z + true_ate * X + noise. When confounding=True, Z biases
    P(X=1); otherwise X is marginally random."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    if confounding:
        # Higher z makes treatment more likely — classic confounding
        logits = 0.8 * z
        x = rng.random(n) < (1 / (1 + np.exp(-logits)))
    else:
        x = rng.random(n) < 0.5
    y = 1.0 * z + true_ate * x.astype(float) + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"x": x, "z": z, "y": y})


def _bool_dgp(n=800, seed=0, confounding=True):
    """Bool outcome. True effect of X on P(Y=1) ~ 0.3."""
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    if confounding:
        x = rng.random(n) < (1 / (1 + np.exp(-0.8 * z)))
    else:
        x = rng.random(n) < 0.5
    logits = 0.5 * z + 1.5 * x.astype(float) - 1.0
    y = rng.random(n) < (1 / (1 + np.exp(-logits)))
    return pd.DataFrame({"x": x, "z": z, "y": y})


# ============================================ correctness


def test_linear_ate_recovers_true_effect_within_tolerance():
    df = _linear_dgp(n=1000, seed=0, true_ate=2.0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,  # skip CI for speed
    )
    assert abs(est.point - 2.0) < 0.2, (
        f"expected ATE ~2.0, got {est.point}"
    )
    assert est.method == "backdoor_linear"
    # Adjustment identity matters for the claim
    assert est.adjustment == ("z",)


def test_logistic_path_for_bool_outcome():
    df = _bool_dgp(n=2000, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    assert est.method == "backdoor_logistic"
    # Expected ATE on P(Y=1): positive, roughly in the 0.2-0.4 range
    assert 0.1 < est.point < 0.5


def test_auto_model_selection_linear_outcome():
    df = _linear_dgp(n=200, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "backdoor_linear"


def test_auto_model_selection_bool_outcome():
    df = _bool_dgp(n=200, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "backdoor_logistic"


def test_explicit_model_overrides_auto():
    df = _bool_dgp(n=200, seed=0)
    # Force linear even on bool outcome
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0, model="linear",
    )
    assert est.method == "backdoor_linear"


def test_unknown_model_raises():
    df = _linear_dgp(n=100, seed=0)
    with pytest.raises(ValueError, match="unknown model"):
        estimate_backdoor_ate(
            df, treatment="x", outcome="y", adjustment=("z",),
            ci_bootstrap=0, model="random_forest",  # type: ignore[arg-type]
        )


# ============================================ empty adjustment


def test_empty_adjustment_marginal_randomization():
    """When X is marginally random (no confounding), ATE estimate is
    unbiased even with empty adjustment set."""
    df = _linear_dgp(n=2000, seed=0, true_ate=1.5, confounding=False)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=(),
        ci_bootstrap=0,
    )
    assert abs(est.point - 1.5) < 0.25
    # Assumption list flags the stronger claim
    assert any(
        "marginally_randomized" in a for a in est.assumptions
    )


def test_empty_adjustment_on_confounded_data_biased_as_expected():
    """When data IS confounded but we omit the adjustment, the estimate
    is biased — this is the classic confounding failure."""
    df = _linear_dgp(n=2000, seed=0, true_ate=2.0, confounding=True)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=(),
        ci_bootstrap=0,
    )
    # Biased estimate is further from 2.0 than the adjusted estimate
    est_adjusted = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    assert abs(est.point - 2.0) > abs(est_adjusted.point - 2.0)


# ============================================ determinism + CI


def test_deterministic_under_fixed_seed():
    df = _linear_dgp(n=300, seed=0)
    e1 = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=100, random_state=42,
    )
    e2 = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=100, random_state=42,
    )
    assert e1.point == e2.point
    assert e1.ci_lower == e2.ci_lower
    assert e1.ci_upper == e2.ci_upper
    assert e1.data_hash == e2.data_hash


def test_different_seeds_produce_different_cis():
    df = _linear_dgp(n=300, seed=0)
    e1 = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=100, random_state=42,
    )
    e2 = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=100, random_state=7,
    )
    # Point is deterministic (doesn't depend on seed for fit)
    assert e1.point == e2.point
    # CIs differ due to different bootstrap resamples
    assert (e1.ci_lower, e1.ci_upper) != (e2.ci_lower, e2.ci_upper)


def test_bootstrap_ci_brackets_point():
    df = _linear_dgp(n=500, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=200, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    assert est.ci_level == 0.95


def test_ci_bootstrap_zero_skips_ci():
    df = _linear_dgp(n=100, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    assert est.ci_lower is None
    assert est.ci_upper is None


# ============================================ shape checks


def test_returns_named_tuple_with_correct_fields():
    df = _linear_dgp(n=100, seed=0)
    est = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    assert isinstance(est, BackdoorEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.adjustment == ("z",)
    assert est.sample_size == 100
    assert len(est.data_hash) == 64  # SHA-256 hex


def test_row_order_does_not_change_point_estimate():
    df = _linear_dgp(n=300, seed=0)
    shuffled = df.sample(frac=1.0, random_state=99).reset_index(drop=True)
    e1 = estimate_backdoor_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    e2 = estimate_backdoor_ate(
        shuffled, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=0,
    )
    # sklearn LinearRegression is order-invariant for the same row set
    assert abs(e1.point - e2.point) < 1e-9
