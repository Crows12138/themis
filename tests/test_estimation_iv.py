"""Phase 7.3 S.IVN.1 — unit tests for the IV ATE estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.iv import IVEstimate, estimate_iv_ate


def _binary_iv_dgp(n=2000, seed=0, true_late=1.5):
    """Z → X → Y, U ↔ X,Y latent. Binary Z and X.

    Monotonicity holds by construction (higher Z → higher P(X=1)), so
    Wald recovers LATE.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5  # randomised instrument
    p_x_z1 = 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + u * 0.5)))
    x = rng.random(n) < p_x_z1
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _continuous_iv_dgp(n=2000, seed=0, true_ate=2.0):
    """Continuous Z, binary X, continuous Y."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.standard_normal(n)
    # Treatment assignment depends on Z + latent U (endogeneity)
    x = 0.5 * z + 0.8 * u + rng.standard_normal(n) * 0.2
    y = true_ate * x + 1.5 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


# ============================================ Wald acceptance


def test_wald_recovers_late_on_binary_iv_dgp():
    df = _binary_iv_dgp(n=3000, seed=0, true_late=1.5)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.method == "iv_wald"
    # The true LATE is the effect on compliers; Wald is consistent
    assert abs(est.point - 1.5) < 0.4, (
        f"Wald estimate {est.point} off target 1.5"
    )


def test_wald_assumptions_list_mentions_monotonicity():
    df = _binary_iv_dgp(n=500, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert any("monotonicity" in a for a in est.assumptions)
    assert any("LATE" in a for a in est.assumptions)


def test_wald_raises_when_first_stage_exactly_zero():
    """If X is constant across Z values, Wald's denominator is exactly 0."""
    rng = np.random.default_rng(0)
    n = 500
    # X is constant (all True) → E[X|Z=1] - E[X|Z=0] = 0 exactly
    df = pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "x": np.ones(n, dtype=bool),
        "y": rng.standard_normal(n),
    })
    with pytest.raises(ValueError, match="first-stage"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            ci_bootstrap=0,
        )


# ============================================ 2SLS acceptance


def test_2sls_recovers_ate_on_continuous_iv_dgp():
    df = _continuous_iv_dgp(n=3000, seed=0, true_ate=2.0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert abs(est.point - 2.0) < 0.3, (
        f"2SLS estimate {est.point} off target 2.0"
    )


def test_2sls_with_conditioning_set():
    """Include a conditioning variable W that shifts both Z's effect on X
    and Z's backdoor to Y. 2SLS with W as conditioning set should still
    recover the true ATE."""
    rng = np.random.default_rng(1)
    n = 3000
    w = rng.standard_normal(n)
    u = rng.standard_normal(n)
    z = 0.5 * w + rng.standard_normal(n)
    x = 0.5 * z + 0.3 * w + 0.8 * u + rng.standard_normal(n) * 0.2
    true_ate = 1.5
    y = true_ate * x + 0.4 * w + 1.5 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"z": z, "w": w, "x": x, "y": y})

    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert est.conditioning == ("w",)
    assert abs(est.point - 1.5) < 0.3


# ============================================ auto model selection


def test_auto_selects_wald_for_binary_binary_unconditional():
    df = _binary_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "iv_wald"


def test_auto_selects_2sls_for_continuous():
    df = _continuous_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "iv_2sls"


def test_auto_selects_2sls_when_conditioning_non_empty():
    """Even with binary Z/X, conditioning non-empty forces 2SLS."""
    df = _binary_iv_dgp(n=500, seed=0)
    df["w"] = np.random.default_rng(0).standard_normal(500)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"


# ============================================ restrictions


def test_wald_rejects_continuous_treatment():
    df = _continuous_iv_dgp(n=500, seed=0)
    with pytest.raises(ValueError, match="binary"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            model="wald", ci_bootstrap=0,
        )


def test_wald_rejects_conditioning():
    df = _binary_iv_dgp(n=500, seed=0)
    df["w"] = np.random.default_rng(0).standard_normal(500)
    with pytest.raises(NotImplementedError, match="Conditional IV"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="wald", ci_bootstrap=0,
        )


# ============================================ determinism + CI


def test_deterministic_under_fixed_seed():
    df = _binary_iv_dgp(n=500, seed=0)
    e1 = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=50, random_state=42,
    )
    e2 = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=50, random_state=42,
    )
    assert e1.point == e2.point
    assert e1.ci_lower == e2.ci_lower
    assert e1.ci_upper == e2.ci_upper


def test_bootstrap_ci_brackets_point():
    df = _binary_iv_dgp(n=800, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=100, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_ci_bootstrap_zero_skips():
    df = _binary_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.ci_lower is None
    assert est.ci_upper is None


# ============================================ shape


def test_returns_named_tuple():
    df = _binary_iv_dgp(n=100, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert isinstance(est, IVEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.instrument == "z"
    assert est.conditioning == ()
    assert len(est.data_hash) == 64
