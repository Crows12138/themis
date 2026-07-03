"""Iter 134 — multi-mediator chain CDE tests.

CDE_chain(x, x', m1*, m2*, ..., mn*) =
    E[Y | do(X=x), do(M_1=m1*), ..., do(M_n=mn*)]
  - E[Y | do(X=x'), do(M_1=m1*), ..., do(M_n=mn*)]

Plug-in g-formula: fit Y ~ X + M_1 + ... + M_n + Z, evaluate at
chain-fixed mediator values for two X levels, take sample-mean
difference. Bootstrap percentile CI.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.mediation import (
    CDEChainEstimate,
    estimate_cde_chain,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _two_mediator_chain_no_interaction(n: int = 2000, seed: int = 0):
    """X → M1 → M2 → Y with no X·M_i interactions.
    Y = 2*X + 1.5*M1 + 1.0*M2 + 0.5*Z + noise.
    Direct effect of X (with M1, M2 fixed) = 2.0."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(n) < 0.5)
    m1 = (rng.random(n) < 0.4 + 0.2 * x.astype(float))
    m2 = (rng.random(n) < 0.4 + 0.2 * m1.astype(float))
    y = (
        2.0 * x.astype(float)
        + 1.5 * m1.astype(float)
        + 1.0 * m2.astype(float)
        + 0.5 * z
        + rng.normal(size=n)
    )
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "z": z, "y": y})


def _three_mediator_chain(n: int = 1500, seed: int = 1):
    rng = np.random.default_rng(seed)
    x = (rng.random(n) < 0.5)
    m1 = (rng.random(n) < 0.5)
    m2 = (rng.random(n) < 0.5)
    m3 = (rng.random(n) < 0.5)
    y = (
        x.astype(float)
        + m1.astype(float) + m2.astype(float) + m3.astype(float)
        + rng.normal(size=n)
    )
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "m3": m3, "y": y})


def _logit_outcome_with_chain(n: int = 2000, seed: int = 2):
    rng = np.random.default_rng(seed)
    x = (rng.random(n) < 0.5)
    m1 = (rng.random(n) < 0.5)
    m2 = (rng.random(n) < 0.5)
    logits = (
        0.5 * x.astype(float)
        + 0.7 * m1.astype(float)
        + 0.4 * m2.astype(float)
    )
    p = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.random(n) < p)
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "y": y})


# ---------------------------------------------------------------------------
# Math correctness — 2-mediator chain
# ---------------------------------------------------------------------------


def test_two_mediator_chain_recovers_direct_effect_no_interaction():
    """No X·M interaction → CDE_chain(1, 0, m1*, m2*) ≈ 2.0
    regardless of m1*, m2*."""
    df = _two_mediator_chain_no_interaction(n=4000, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"),
        mediator_values=(True, True),
        adjustment=("z",),
        ci_bootstrap=0,
    )
    assert est.point == pytest.approx(2.0, abs=0.2)
    assert est.method == "cde_chain_linear"


def test_two_mediator_chain_invariant_to_mediator_values():
    df = _two_mediator_chain_no_interaction(n=3000, seed=0)
    e_tt = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        ci_bootstrap=0,
    )
    e_ff = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(False, False),
        ci_bootstrap=0,
    )
    e_tf = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, False),
        ci_bootstrap=0,
    )
    # All three should be close (no X-M interaction in DGP)
    assert abs(e_tt.point - e_ff.point) < 0.2
    assert abs(e_tt.point - e_tf.point) < 0.2


# ---------------------------------------------------------------------------
# 3-mediator chain
# ---------------------------------------------------------------------------


def test_three_mediator_chain_runs():
    df = _three_mediator_chain(n=2000, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2", "m3"),
        mediator_values=(True, False, True),
        ci_bootstrap=0,
    )
    assert est.point == pytest.approx(1.0, abs=0.2)
    assert est.mediators == ("m1", "m2", "m3")
    assert est.mediator_values == (True, False, True)


# ---------------------------------------------------------------------------
# Logit path
# ---------------------------------------------------------------------------


def test_logit_chain_returns_probability_difference():
    df = _logit_outcome_with_chain(n=2000, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        ci_bootstrap=0,
    )
    assert -1.0 <= est.point <= 1.0
    assert est.method == "cde_chain_logit"
    assert est.point > 0  # X positively affects Y in DGP


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------


def test_bootstrap_ci_brackets_point():
    df = _two_mediator_chain_no_interaction(n=1000, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        adjustment=("z",),
        ci_bootstrap=200,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper


def test_zero_bootstrap_skips_ci():
    df = _two_mediator_chain_no_interaction(n=500, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        ci_bootstrap=0,
    )
    assert est.ci_lower is None and est.ci_upper is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def test_rejects_mismatched_lengths():
    df = _two_mediator_chain_no_interaction(n=300, seed=0)
    with pytest.raises(ValueError, match="length mismatch"):
        estimate_cde_chain(
            df, treatment="x", outcome="y",
            mediators=("m1", "m2"),
            mediator_values=(True,),  # only 1 value for 2 mediators
            ci_bootstrap=0,
        )


def test_rejects_empty_mediators():
    df = _two_mediator_chain_no_interaction(n=300, seed=0)
    with pytest.raises(ValueError, match="at least one mediator"):
        estimate_cde_chain(
            df, treatment="x", outcome="y",
            mediators=(),
            mediator_values=(),
            ci_bootstrap=0,
        )


# ---------------------------------------------------------------------------
# Audit fields
# ---------------------------------------------------------------------------


def test_audit_fields_carried():
    df = _two_mediator_chain_no_interaction(n=300, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, False),
        adjustment=("z",),
        ci_bootstrap=0,
    )
    assert isinstance(est, CDEChainEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.adjustment == ("z",)
    assert est.mediators == ("m1", "m2")
    assert est.mediator_values == (True, False)
    assert isinstance(est.data_hash, str) and len(est.data_hash) == 64


def test_assumptions_name_chain_specific_conditions():
    """Chain CDE has stricter assumptions than single-M CDE — must
    include between-mediator no-confounding assumption."""
    df = _two_mediator_chain_no_interaction(n=300, seed=0)
    est = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        ci_bootstrap=0,
    )
    assumption_str = " ".join(est.assumptions)
    assert "between_successive_mediators" in assumption_str
    assert "consistency" in assumption_str


def test_n_equals_1_works_same_as_single_cde():
    """N=1 is allowed (same identification footing as estimate_cde,
    just exposed via the chain API). Estimate should be close to
    iter 125's estimate_cde for the same data."""
    from themis.estimation.mediation import estimate_cde

    # Reuse _two_mediator_chain fixture but only declare m1
    df = _two_mediator_chain_no_interaction(n=2000, seed=0)
    est_chain = estimate_cde_chain(
        df, treatment="x", outcome="y",
        mediators=("m1",), mediator_values=(True,),
        adjustment=("z", "m2"),  # treat m2 as adjustment for fair compare
        ci_bootstrap=0,
    )
    est_single = estimate_cde(
        df, treatment="x", outcome="y",
        mediator="m1", mediator_value=True,
        adjustment=("z", "m2"),
        ci_bootstrap=0,
    )
    # Should match exactly — same outcome model fit, same plug-in
    assert est_chain.point == pytest.approx(est_single.point, abs=1e-9)


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_re_exported_from_themis_estimation():
    import themis.estimation as e
    assert "estimate_cde_chain" in e.__all__
    assert "CDEChainEstimate" in e.__all__
    assert e.estimate_cde_chain is estimate_cde_chain
    assert e.CDEChainEstimate is CDEChainEstimate


# ---------------------------------------------------------------------------
# Cluster (pairs) bootstrap — parity with backdoor / mediation / cde
# ---------------------------------------------------------------------------


def _chain_cluster_dgp(seed: int, *, G: int = 45, per: int = 20):
    """Cluster-level treatment + shared family effect on Y, X → M1 → M2 → Y
    with no interactions so the chain CDE is the X coefficient (2.0). The
    within-cluster correlation makes the i.i.d. CI too narrow."""
    rng = np.random.default_rng(seed)
    clu = np.repeat(np.arange(G), per)
    x_by_cluster = rng.integers(0, 2, G)
    x = x_by_cluster[clu].astype(float)
    m1 = (rng.random(G * per) < 0.4 + 0.2 * x).astype(float)
    m2 = (rng.random(G * per) < 0.3 + 0.3 * m1).astype(float)
    u = rng.standard_normal(G) * 2.0
    y = 2.0 * x + 1.5 * m1 + 1.0 * m2 + u[clu] + rng.standard_normal(G * per) * 0.4
    return pd.DataFrame({"x": x, "m1": m1, "m2": m2, "y": y, "fam": clu})


def test_chain_cluster_none_byte_identical_to_default():
    df = _chain_cluster_dgp(0)
    kw = dict(treatment="x", outcome="y", mediators=("m1", "m2"),
              mediator_values=(True, True), ci_bootstrap=200, random_state=7)
    a = estimate_cde_chain(df, **kw)
    b = estimate_cde_chain(df, cluster=None, **kw)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper
    assert a.data_hash == b.data_hash
    assert a.cluster is None


def test_chain_cluster_column_excluded_from_hash():
    df = _chain_cluster_dgp(1)
    with_col = estimate_cde_chain(
        df, treatment="x", outcome="y", mediators=("m1", "m2"),
        mediator_values=(True, True), ci_bootstrap=50, random_state=1,
        cluster="fam")
    without = estimate_cde_chain(
        df[["x", "m1", "m2", "y"]], treatment="x", outcome="y",
        mediators=("m1", "m2"), mediator_values=(True, True),
        ci_bootstrap=50, random_state=1)
    assert with_col.data_hash == without.data_hash
    assert with_col.cluster == "fam"


def test_chain_cluster_ci_is_wider_under_clustering():
    df = _chain_cluster_dgp(2)
    kw = dict(treatment="x", outcome="y", mediators=("m1", "m2"),
              mediator_values=(True, True), ci_bootstrap=400, random_state=1)
    iid = estimate_cde_chain(df, **kw)
    clu = estimate_cde_chain(df, cluster="fam", **kw)
    assert (clu.ci_upper - clu.ci_lower) > 1.3 * (iid.ci_upper - iid.ci_lower)
    assert any("cluster_bootstrap" in a for a in clu.assumptions)
