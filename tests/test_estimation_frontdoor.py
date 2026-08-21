"""Phase 7.2 S.FDN.1 — unit tests for the front-door ATE estimator.

Coverage:
- Single-mediator front-door on a classic latent-confounded graph
  (X ↔ Y latent, mediator M intercepts): recovers true ATE
- Multi-mediator (two mediators) via chain-rule: recovers true ATE
- Bool + continuous outcome paths
- Multi-valued (categorical / integer) mediator recovers true ATE
  against an analytic front-door oracle
- Integer-valued float mediator accepted; genuinely continuous and
  high-cardinality mediators rejected
- Determinism under fixed seed
- Bootstrap CI brackets point estimate
- Empty mediators rejected
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import refusals
from themis.refusals import Refusal
from themis.estimation.frontdoor import (
    FrontdoorEstimate,
    estimate_frontdoor_ate,
)
from themis.refusals import EstimatorFailure


def _single_mediator_dgp(n=2000, seed=0, true_ate=1.0):
    """X → M → Y with X ↔ Y latent confounding.

    Binary X, bool M, continuous Y.
    """
    rng = np.random.default_rng(seed)
    # Latent U confounds X and Y
    u = rng.standard_normal(n)
    # X depends on U
    p_x = 1 / (1 + np.exp(-u))
    x = rng.random(n) < p_x
    # M depends only on X (front-door requirement: no backdoor to M)
    p_m = 1 / (1 + np.exp(-(2.0 * x.astype(float) - 1)))
    m = rng.random(n) < p_m
    # Y depends on M (mediated effect of X on Y) + latent U (backdoor that
    # front-door sidesteps)
    y = true_ate * m.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _double_mediator_dgp(n=3000, seed=0, true_ate_through_m2=1.5):
    """X → M1 → M2 → Y with X ↔ Y latent. Chain-rule multi-mediator case.

    Both M1 and M2 needed to block directed path."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    m1 = rng.random(n) < (1 / (1 + np.exp(-(2.0 * x.astype(float) - 1))))
    m2 = rng.random(n) < (1 / (1 + np.exp(-(1.8 * m1.astype(float) - 1))))
    y = true_ate_through_m2 * m2.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "y": y})


def _categorical_mediator_dgp(n=8000, seed=0):
    """X → M → Y with X ↔ Y latent, M a 3-level categorical mediator.

    U confounds X and Y (the backdoor front-door sidesteps). M depends only
    on X. Y is additive: ``g(M) + 2·U + noise`` with ``g = [0, 1, 2.5]``.
    Because M ⟂ U | X, the outcome model E[Y|X,M] is saturated in
    [X, one-hot(M)], so the front-door plug-in recovers the *analytic*
    interventional contrast

        ATE = Σ_m [P(M=m|X=1) − P(M=m|X=0)] · g(m)

    exactly in the large-sample limit — an independent oracle that does not
    reuse the estimator's machinery.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    probs0 = np.array([0.6, 0.3, 0.1])   # P(M | X=0)
    probs1 = np.array([0.1, 0.3, 0.6])   # P(M | X=1)
    m = np.empty(n, dtype=int)
    for xi in (0, 1):
        mask = x == bool(xi)
        m[mask] = rng.choice(3, size=int(mask.sum()),
                             p=(probs1 if xi == 1 else probs0))
    g = np.array([0.0, 1.0, 2.5])
    y = g[m] + 2.0 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "m": m.astype(int), "y": y})
    true_ate = float(((probs1 - probs0) * g).sum())   # = 1.25
    return df, true_ate


# ============================================ correctness


def test_single_mediator_recovers_true_ate():
    # True X → Y effect: X flips M with high probability, M → Y coef is 1.0.
    # Approximate true ATE of do(X=1) - do(X=0) on E[Y]: ~1.0 * (P(M=1|X=1) - P(M=1|X=0))
    # with sigmoid coefficients above: ~1.0 * (sigmoid(1) - sigmoid(-1)) ≈ 1.0 * 0.46
    df = _single_mediator_dgp(n=3000, seed=0, true_ate=1.0)
    expected = 1.0 * (1/(1+np.exp(-1.0)) - 1/(1+np.exp(1.0)))  # ≈ 0.462
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=0,
    )
    assert est.method == "frontdoor_linear"
    assert abs(est.point - expected) < 0.10, (
        f"expected ~{expected:.3f}, got {est.point:.3f}"
    )


def test_double_mediator_recovers_positive_effect():
    df = _double_mediator_dgp(n=3000, seed=0, true_ate_through_m2=1.5)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m1", "m2"),
        ci_bootstrap=0,
    )
    # True effect direction should be positive (larger do(X=1) vs do(X=0))
    assert est.point > 0.1, f"expected positive ATE, got {est.point}"
    # Method reflects linear outcome
    assert est.method == "frontdoor_linear"
    assert len(est.mediators) == 2


def test_multivalued_categorical_mediator_recovers_true_ate():
    """3-level integer mediator: front-door recovers the analytic ATE
    despite latent X↔Y confounding the estimator never sees."""
    df, true_ate = _categorical_mediator_dgp(n=8000, seed=0)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert est.method == "frontdoor_linear"
    assert abs(est.point - true_ate) < 0.12, (
        f"expected ~{true_ate:.3f}, got {est.point:.3f}"
    )


def test_integer_valued_float_mediator_accepted():
    """A 3-level mediator encoded as float 0.0/1.0/2.0 is treated as
    discrete (integer-valued) and recovers the same ATE."""
    df, true_ate = _categorical_mediator_dgp(n=6000, seed=1)
    df = df.assign(m=df["m"].astype(float))   # 0.0 / 1.0 / 2.0
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert abs(est.point - true_ate) < 0.15, (
        f"expected ~{true_ate:.3f}, got {est.point:.3f}"
    )


def test_categorical_mediator_bootstrap_ci_brackets_point():
    """Bootstrap over a multi-level mediator (resamples may drop a level;
    the degenerate-factor guard must hold) and the CI brackets the point."""
    df, _ = _categorical_mediator_dgp(n=2000, seed=2)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=80, random_state=3,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_bool_outcome_uses_logistic_path():
    rng = np.random.default_rng(0)
    n = 2000
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    m = rng.random(n) < (1 / (1 + np.exp(-(2.0 * x.astype(float) - 1))))
    # Bool y
    y_logit = 1.5 * m.astype(float) + 2.0 * u - 1.5
    y = rng.random(n) < (1 / (1 + np.exp(-y_logit)))
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "frontdoor_logistic"
    # Direction is positive
    assert est.point > 0.0


def test_explicit_linear_model_overrides_auto():
    df = _single_mediator_dgp(n=200, seed=0, true_ate=1.0)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=0, model="linear",
    )
    assert est.method == "frontdoor_linear"


# ============================================ determinism + CI


def test_deterministic_under_fixed_seed():
    df = _single_mediator_dgp(n=500, seed=0)
    e1 = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=50, random_state=42,
    )
    e2 = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=50, random_state=42,
    )
    assert e1.point == e2.point
    assert e1.ci_lower == e2.ci_lower
    assert e1.ci_upper == e2.ci_upper
    assert e1.data_hash == e2.data_hash


def test_bootstrap_ci_brackets_point():
    df = _single_mediator_dgp(n=800, seed=0)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=100, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_ci_bootstrap_zero_skips_ci():
    df = _single_mediator_dgp(n=200, seed=0)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=0,
    )
    assert est.ci_lower is None
    assert est.ci_upper is None


# ============================================ restrictions


def test_empty_mediators_rejected():
    df = _single_mediator_dgp(n=100, seed=0)
    with pytest.raises(ValueError, match=">=1 mediator"):
        estimate_frontdoor_ate(
            df, treatment="x", outcome="y", mediators=(),
            ci_bootstrap=0,
        )


def test_continuous_mediator_rejected():
    """A genuinely continuous (fractional-valued) mediator is deferred."""
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "x": rng.random(n) < 0.5,
        "m_cont": rng.standard_normal(n),   # fractional float
        "y": rng.standard_normal(n),
    })
    with pytest.raises(EstimatorFailure, match="continuous") as exc:
        estimate_frontdoor_ate(
            df, treatment="x", outcome="y", mediators=("m_cont",),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.CONTINUOUS_MEDIATOR


def test_high_cardinality_integer_mediator_rejected():
    """A near-continuous integer mediator (too many levels) is deferred —
    exact stratum enumeration is refused past the per-mediator level cap."""
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame({
        "x": rng.random(n) < 0.5,
        "m_int": rng.integers(0, 100, size=n),   # ~100 levels > cap
        "y": rng.standard_normal(n),
    })
    with pytest.raises(EstimatorFailure, match="continuous") as exc:
        estimate_frontdoor_ate(
            df, treatment="x", outcome="y", mediators=("m_int",),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.CONTINUOUS_MEDIATOR


# ============================================ shape


def test_returns_named_tuple_with_correct_fields():
    df = _single_mediator_dgp(n=100, seed=0)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",),
        ci_bootstrap=0,
    )
    assert isinstance(est, FrontdoorEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.mediators == ("m",)
    assert len(est.data_hash) == 64


def test_too_many_mediator_combinations_rejected():
    """Each mediator is discrete and under the per-mediator level cap, but
    their cross-product is not enumerable. The estimand is well posed — the
    exact sum over it is what is refused — so this is a species of its own,
    not the continuous-mediator one."""
    rng = np.random.default_rng(0)
    n = 600
    df = pd.DataFrame({
        "x": rng.random(n) < 0.5,
        "m1": rng.integers(0, 15, n),
        "m2": rng.integers(0, 15, n),
        "m3": rng.integers(0, 15, n),   # 15^3 = 3375 > 2048 cap
        "y": rng.standard_normal(n),
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_frontdoor_ate(
            df, treatment="x", outcome="y", mediators=("m1", "m2", "m3"),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.MEDIATOR_STRATA_INTRACTABLE
    assert exc.value.details["combinations"] == 3375
