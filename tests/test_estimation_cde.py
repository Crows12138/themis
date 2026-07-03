"""Iter 125 / Phase 7.5 — Controlled Direct Effect (CDE) numeric estimator.

CDE(x, x', m*) = E[Y | do(X=x), do(M=m*)] - E[Y | do(X=x'), do(M=m*)]

Plug-in g-formula on a fitted outcome model E[Y|X,M,Z]. Sklearn-based;
the statsmodels Mediation API doesn't expose do(M=m*) directly so this
estimator stands separate from estimate_mediation (which produces NDE/
NIE/TE via Imai 2010 algorithms).

VanderWeele 2015 ch.2.3.3: CDE is the policy-relevant direct effect
when the mediator is itself an intervention target — "what would the
effect of X look like if everyone's M were forced to m*?"
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.mediation import CDEEstimate, estimate_cde


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _linear_no_interaction(n: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Y = 2*X + 3*M + Z + noise. No X*M interaction → CDE(x,x',m*)
    is constant in m*; equal to NDE under linear model."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(n) < 0.5)
    m = (rng.random(n) < 0.4 + 0.2 * x.astype(float))  # M depends on X
    y = (
        2.0 * x.astype(float)
        + 3.0 * m.astype(float)
        + 1.0 * z
        + rng.normal(size=n)
    )
    return pd.DataFrame({"x": x, "m": m, "y": y, "z": z})


def _linear_with_interaction(n: int = 1000, seed: int = 1) -> pd.DataFrame:
    """Y = 2*X + 3*M + 2.5*X*M + Z + noise. CDE varies with m*: at
    m*=1 the direct contribution of X is 2 + 2.5 = 4.5; at m*=0 it's 2.

    Without explicit interaction term in the outcome model, plug-in
    g-formula picks up the AVERAGE direct effect; the interaction
    biases the estimate. We test that the estimator returns A point,
    not perfect ATE recovery."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(n) < 0.5)
    m = (rng.random(n) < 0.4 + 0.2 * x.astype(float))
    y = (
        2.0 * x.astype(float)
        + 3.0 * m.astype(float)
        + 2.5 * x.astype(float) * m.astype(float)
        + 1.0 * z
        + rng.normal(size=n)
    )
    return pd.DataFrame({"x": x, "m": m, "y": y, "z": z})


def _logit_outcome(n: int = 1000, seed: int = 2) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(n) < 0.5)
    m = (rng.random(n) < 0.4 + 0.2 * x.astype(float))
    logits = 0.5 * x.astype(float) + 1.0 * m.astype(float) + 0.3 * z
    p = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.random(n) < p)
    return pd.DataFrame({"x": x, "m": m, "y": y, "z": z})


# ---------------------------------------------------------------------------
# Linear path
# ---------------------------------------------------------------------------


def test_cde_linear_recovers_direct_effect_no_interaction():
    """No X*M interaction → CDE(1,0,m*) ≈ direct X coefficient = 2.0
    regardless of m*. Generous tolerance for finite-sample noise."""
    df = _linear_no_interaction(n=2000, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, adjustment=("z",),
        ci_bootstrap=0,
    )
    assert est.point == pytest.approx(2.0, abs=0.2)
    assert est.method == "cde_linear"


def test_cde_linear_invariant_to_mediator_value_no_interaction():
    """Without X*M interaction, CDE(1,0,m=0) should ≈ CDE(1,0,m=1)."""
    df = _linear_no_interaction(n=2000, seed=0)
    est_m1 = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    est_m0 = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=False, ci_bootstrap=0,
    )
    assert abs(est_m1.point - est_m0.point) < 0.15


def test_cde_linear_with_bootstrap_ci_brackets_point():
    df = _linear_no_interaction(n=1000, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, adjustment=("z",),
        ci_bootstrap=200,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper


# ---------------------------------------------------------------------------
# Logit path
# ---------------------------------------------------------------------------


def test_cde_logit_returns_probability_difference():
    """Binary outcome → CDE returns difference in P(Y=1). Should be
    in [-1, 1] and finite."""
    df = _logit_outcome(n=2000, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, adjustment=("z",),
        ci_bootstrap=0,
    )
    assert -1.0 <= est.point <= 1.0
    assert est.method == "cde_logit"


def test_cde_logit_positive_when_x_increases_y():
    """In the logit fixture X has positive logit-coefficient on Y;
    CDE should be positive."""
    df = _logit_outcome(n=2000, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    assert est.point > 0


# ---------------------------------------------------------------------------
# Auto-dispatch by outcome dtype
# ---------------------------------------------------------------------------


def test_cde_auto_picks_linear_for_continuous():
    df = _linear_no_interaction(n=500, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, model="auto", ci_bootstrap=0,
    )
    assert est.method == "cde_linear"


def test_cde_auto_picks_logit_for_bool():
    df = _logit_outcome(n=500, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, model="auto", ci_bootstrap=0,
    )
    assert est.method == "cde_logit"


# ---------------------------------------------------------------------------
# Estimate carries audit fields
# ---------------------------------------------------------------------------


def test_cde_carries_mediator_value_in_estimate():
    df = _linear_no_interaction(n=300, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=False, ci_bootstrap=0,
    )
    assert est.mediator_value == False
    assert est.treatment == "x"
    assert est.mediator == "m"
    assert est.outcome == "y"


def test_cde_assumptions_are_stricter_than_nde():
    """CDE requires fewer assumptions than NDE/NIE — only one-step
    no-unmeasured-confounders, not Pearl's full sequential
    ignorability. Assumption tuple should reflect that."""
    df = _linear_no_interaction(n=500, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    assumptions = " ".join(est.assumptions)
    # Should NOT mention sequential ignorability (the NDE/NIE-only one)
    assert "sequential_ignorability" not in assumptions
    # Should mention X-Y and M-Y backdoors
    assert "no_unmeasured_confounder_x_y" in assumptions
    assert "no_unmeasured_confounder_m_y" in assumptions


def test_cde_data_hash_matches_contract():
    df = _linear_no_interaction(n=300, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    assert isinstance(est.data_hash, str)
    assert len(est.data_hash) == 64  # SHA-256 hex


def test_cde_returns_estimate_dataclass_instance():
    df = _linear_no_interaction(n=300, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    assert isinstance(est, CDEEstimate)


def test_cde_zero_bootstrap_skips_ci():
    df = _linear_no_interaction(n=300, seed=0)
    est = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    assert est.ci_lower is None
    assert est.ci_upper is None


# ---------------------------------------------------------------------------
# Treatment-level customisation
# ---------------------------------------------------------------------------


def test_cde_custom_treatment_levels_flips_sign():
    """CDE with treatment_high=False, treatment_low=True is the
    negation of the default. Sanity check the flip."""
    df = _linear_no_interaction(n=2000, seed=0)
    default = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True, ci_bootstrap=0,
    )
    flipped = estimate_cde(
        df, treatment="x", outcome="y", mediator="m",
        mediator_value=True,
        treatment_high=False, treatment_low=True,
        ci_bootstrap=0,
    )
    assert default.point == pytest.approx(-flipped.point, abs=1e-9)


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_cde_re_exported_from_themis_estimation():
    """Iter 125: estimate_cde and CDEEstimate are part of the public
    surface of themis.estimation."""
    import themis.estimation as e
    assert "estimate_cde" in e.__all__
    assert "CDEEstimate" in e.__all__
    assert e.estimate_cde is estimate_cde
    assert e.CDEEstimate is CDEEstimate


# ---------------------------------------------------------------------------
# Cluster (pairs) bootstrap — parity with backdoor / mediation
# ---------------------------------------------------------------------------


def _cde_cluster_dgp(seed: int, *, G: int = 45, per: int = 20) -> pd.DataFrame:
    """Cluster-level treatment + a shared family effect on Y (continuous).
    Same X for every row of a cluster + a same-sign cluster shock on Y →
    within-cluster positive correlation, so the i.i.d. bootstrap
    UNDERSTATES the variance and the cluster CI must be wider. The CDE at
    fixed M is the X coefficient (2.0); M enters additively so the
    mediator value doesn't move the direct contrast."""
    rng = np.random.default_rng(seed)
    clu = np.repeat(np.arange(G), per)
    x_by_cluster = rng.integers(0, 2, G)
    x = x_by_cluster[clu].astype(float)
    m = (rng.random(G * per) < 0.4 + 0.2 * x).astype(float)
    u = rng.standard_normal(G) * 2.0  # shared family effect
    y = 2.0 * x + 3.0 * m + u[clu] + rng.standard_normal(G * per) * 0.4
    return pd.DataFrame({"x": x, "m": m, "y": y, "fam": clu})


def test_cde_cluster_none_byte_identical_to_default():
    df = _cde_cluster_dgp(0)
    a = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                     mediator_value=True, ci_bootstrap=200, random_state=7)
    b = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                     mediator_value=True, ci_bootstrap=200, random_state=7,
                     cluster=None)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper
    assert a.data_hash == b.data_hash
    assert a.cluster is None


def test_cde_cluster_column_excluded_from_hash():
    df = _cde_cluster_dgp(1)
    with_col = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                            mediator_value=True, ci_bootstrap=50,
                            random_state=1, cluster="fam")
    without = estimate_cde(df[["x", "m", "y"]], treatment="x", outcome="y",
                           mediator="m", mediator_value=True, ci_bootstrap=50,
                           random_state=1)
    assert with_col.data_hash == without.data_hash
    assert with_col.cluster == "fam"


def test_cde_cluster_ci_is_wider_under_clustering():
    df = _cde_cluster_dgp(2)
    iid = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                       mediator_value=True, ci_bootstrap=400, random_state=1)
    clu = estimate_cde(df, treatment="x", outcome="y", mediator="m",
                       mediator_value=True, ci_bootstrap=400, random_state=1,
                       cluster="fam")
    assert (clu.ci_upper - clu.ci_lower) > 1.3 * (iid.ci_upper - iid.ci_lower)
    assert any("cluster_bootstrap" in a for a in clu.assumptions)
