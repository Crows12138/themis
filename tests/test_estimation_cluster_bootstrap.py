"""Cluster (block) bootstrap for confidence intervals.

The default percentile bootstrap resamples i.i.d. rows, which under
within-cluster dependence underestimates the sampling variance → CIs
too narrow (anti-conservative). A `cluster` column switches the draw to
a pairs cluster bootstrap (Cameron-Gelbach-Miller): resample whole
clusters with replacement. These tests pin the two properties that
matter: (a) cluster=None is byte-identical to the legacy i.i.d. CI, and
(b) on clustered data the cluster CI is wider and correctly covers while
the i.i.d. CI undercovers.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from themis import kernel
from themis.estimation.backdoor import estimate_backdoor_ate
from themis.estimation.mediation import estimate_mediation
from themis.estimation.resample import resample_indices
from themis.input.syntactic_validator import validate_result


def _cluster_dgp(rng, *, G=50, per=20, ate=2.0, cluster_sd=2.0):
    """Cluster-level treatment + a shared family effect on Y (continuous,
    so the true ATE is exactly `ate`)."""
    clu = np.repeat(np.arange(G), per)
    a_by_cluster = rng.integers(0, 2, G)
    A = a_by_cluster[clu].astype(float)
    u = rng.standard_normal(G) * cluster_sd
    Y = ate * A + u[clu] + rng.standard_normal(G * per) * 0.5
    return pd.DataFrame({"A": A, "Y": Y, "fam": clu})


# ============================================ back-compat / determinism


def test_cluster_none_is_byte_identical_to_iid():
    df = _cluster_dgp(np.random.default_rng(0))
    a = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                              ci_bootstrap=200, random_state=7)
    b = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                              ci_bootstrap=200, random_state=7, cluster=None)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper
    assert a.data_hash == b.data_hash  # cluster col absent from hash either way


def test_resampler_iid_path_matches_legacy_draw():
    """The i.i.d. path must consume the rng exactly like the old inline
    ``rng.integers(0, n, size=n)`` so existing results don't move."""
    n = 100
    r1 = np.random.default_rng(3)
    r2 = np.random.default_rng(3)
    assert np.array_equal(resample_indices(n, r1, groups=None),
                          r2.integers(0, n, size=n))


def test_cluster_column_excluded_from_hash():
    df = _cluster_dgp(np.random.default_rng(1))
    with_col = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                     ci_bootstrap=50, random_state=1, cluster="fam")
    without = estimate_backdoor_ate(df[["A", "Y"]], treatment="A", outcome="Y",
                                    ci_bootstrap=50, random_state=1)
    assert with_col.data_hash == without.data_hash


# ============================================ the statistical point


def test_cluster_ci_is_wider_under_clustering():
    df = _cluster_dgp(np.random.default_rng(2))
    iid = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                ci_bootstrap=400, random_state=1)
    clu = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                ci_bootstrap=400, random_state=1, cluster="fam")
    assert (clu.ci_upper - clu.ci_lower) > 1.3 * (iid.ci_upper - iid.ci_lower)
    assert any("cluster_bootstrap" in a for a in clu.assumptions)


def test_iid_undercovers_cluster_covers():
    """Across many simulated datasets the i.i.d. 95% CI covers the true
    ATE far below 95% (anti-conservative) while the cluster CI is near
    nominal."""
    true_ate = 2.0
    n_sims = 40
    iid_hits = clu_hits = 0
    for s in range(n_sims):
        rng = np.random.default_rng(1000 + s)
        df = _cluster_dgp(rng, G=40, per=20, ate=true_ate)
        iid = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                    ci_bootstrap=150, random_state=1)
        clu = estimate_backdoor_ate(df, treatment="A", outcome="Y",
                                    ci_bootstrap=150, random_state=1, cluster="fam")
        iid_hits += iid.ci_lower <= true_ate <= iid.ci_upper
        clu_hits += clu.ci_lower <= true_ate <= clu.ci_upper
    iid_cov, clu_cov = iid_hits / n_sims, clu_hits / n_sims
    assert iid_cov < 0.85, f"i.i.d. coverage {iid_cov} unexpectedly high"
    assert clu_cov > iid_cov + 0.1
    assert clu_cov >= 0.85


def test_mediation_cluster_widens_and_keeps_four_way():
    """The mediation cluster path resamples whole clusters in the SAME
    interaction-aware refit loop (not the biased closed-form product), so
    the four-way decomposition still rides along."""
    rng = np.random.default_rng(0)
    G, per = 45, 20
    clu = np.repeat(np.arange(G), per)
    a_by = rng.integers(0, 2, G)
    A = a_by[clu].astype(float)
    M = (rng.random(G * per) < np.where(A == 1, 0.7, 0.3)).astype(float)
    u = rng.standard_normal(G) * 2.0
    Y = 0.5 * A + 1.0 * M + 2.0 * A * M + u[clu] + rng.standard_normal(G * per) * 0.4
    df = pd.DataFrame({"A": A, "M": M, "Y": Y, "fam": clu})
    iid = estimate_mediation(df, treatment="A", outcome="Y", mediator="M",
                             n_rep=60, random_state=1)
    clu_e = estimate_mediation(df, treatment="A", outcome="Y", mediator="M",
                               n_rep=60, random_state=1, cluster="fam")
    assert (clu_e.te_ci_upper - clu_e.te_ci_lower) > (iid.te_ci_upper - iid.te_ci_lower)
    assert clu_e.four_way is not None
    assert clu_e.cluster == "fam"


# ============================================ public themis.estimate path


def test_themis_estimate_options_cluster_attaches_meta_and_validates():
    A = {"predicate": "A", "args": [{"type": "const", "name": "u"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "u"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "options": {"cluster": "fam"},
        "statements": [
            {"kind": "variable", "predicate": "A"},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": A, "to": Y},
            {"kind": "query", "id": "q1", "query": {
                "kind": "effect", "target": {"atom": Y, "value": True},
                "intervention": {"atom": A, "value": True}, "given": []}},
        ],
    }
    df = _cluster_dgp(np.random.default_rng(0))
    r = kernel.estimate(prog, df, random_state=1)["results"][0]
    validate_result(r)
    assert r["numeric_estimate"]["bootstrap"] == {
        "kind": "cluster", "cluster_column": "fam",
    }
    # Without the option, no bootstrap block (i.i.d., byte-identical surface).
    prog_iid = {k: v for k, v in prog.items() if k != "options"}
    r2 = kernel.estimate(prog_iid, df, random_state=1)["results"][0]
    assert "bootstrap" not in r2["numeric_estimate"]
