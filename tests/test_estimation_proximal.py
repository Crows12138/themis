"""Numeric end for proximal causal inference — Miao's discrete formula (5)
evaluated to an ATE from data that contains only the proxies, never U.

D1 validation is two-pronged:

1. A latent-U SCM oracle. We sample Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y,
   with a LINEAR (unclipped) outcome mechanism so the true ATE has a closed form
   — it is exactly the treatment coefficient (0.35 below), independent of the
   confounding. The estimator sees only the (X,Y,Z,W) columns (U is hidden, as in
   a real dataset) and must recover 0.35 by inverting the Z×W measurement channel.
   A naive back-door adjustment on the proxy Z stays biased on the same data —
   the contrast that motivates proximal inference.
2. Refusal paths: a broken proxy graph, an irrelevant-proxy rank failure, a proxy
   cardinality mismatch, and a positivity hole each raise rather than fabricate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.refusals import EstimatorFailure
from themis.estimation.proximal import estimate_proximal_ate
from themis.runtime.proximal_identify import identify_proximal, ProximalEstimand
from themis.types import Atom, DiscreteChannel

NO_BIDIR = frozenset()


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, Y, U, Z, W = A("x"), A("y"), A("u"), A("z"), A("w")

# Miao model (f): U confounds X,Y; Z is a treatment-inducing proxy (Z→X); W is an
# outcome-inducing proxy (W→Y). U is a named but unobserved node of this graph.
import networkx as nx


def _fig_f_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from([X, Y, U, Z, W])
    g.add_edges_from([(U, X), (U, Y), (U, Z), (U, W), (Z, X), (W, Y), (X, Y)])
    return g


# ---- latent-U SCM (model f), linear outcome so true ATE = 0.35 exactly ------
# P(Y=1|u,x,w) = 0.15 + 0.35 x + 0.25 u + 0.15 w  (all args in {0,1}); the range
# is [0.15, 0.90] so there is no clipping, hence E[Y|do 1] − E[Y|do 0] = 0.35
# for every u, w, and the ATE is 0.35 regardless of the U/W distributions.
_ATE_TRUE = 0.35


def _sample_scm(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5                              # P(U=1)=0.5
    z = rng.random(n) < np.where(u, 0.80, 0.20)          # Z relevant to U
    w = rng.random(n) < np.where(u, 0.85, 0.25)          # W relevant to U
    px1 = np.where(u, np.where(z, 0.80, 0.55), np.where(z, 0.50, 0.20))
    x = rng.random(n) < px1                              # X depends on U and Z
    py1 = 0.15 + 0.35 * x + 0.25 * u + 0.15 * w          # linear, in [0.15,0.90]
    y = rng.random(n) < py1                              # Y depends on U, X, W
    return pd.DataFrame({"x": x, "y": y, "z": z, "w": w})  # note: no 'u' column


def _estimate(df, **kw):
    return estimate_proximal_ate(
        df, graph=_fig_f_graph(), treatment=X, outcome=Y, latent=U,
        treatment_proxy=(Z,), outcome_proxy=(W,),
        channel=DiscreteChannel(latent_cardinality=2), **kw)


# --------------------------------------------------------------------------- #
# D1 prong 1 — recover the true ATE from proxy-only data
# --------------------------------------------------------------------------- #
def test_recovers_true_ate_from_latent_confounded_data():
    df = _sample_scm(200_000, seed=1)
    est = _estimate(df, ci_bootstrap=0)
    assert est.method == "proximal_matrix"
    assert est.declared_channel.latent_cardinality == 2
    assert abs(est.point - _ATE_TRUE) < 0.03, (
        f"proximal recovered {est.point:.4f}, truth {_ATE_TRUE}")


def test_naive_proxy_adjustment_stays_biased():
    # Adjusting for the proxy Z as if it were the confounder (back-door on Z)
    # does NOT remove the U-confounding: its ATE is materially off 0.35, whereas
    # proximal recovers it. This is the whole reason proximal inference exists.
    df = _sample_scm(200_000, seed=2)
    naive = 0.0
    for zval, sub in df.groupby("z"):
        p1 = sub[sub["x"]]["y"].mean()
        p0 = sub[~sub["x"]]["y"].mean()
        naive += (p1 - p0) * (len(sub) / len(df))
    prox = _estimate(df, ci_bootstrap=0).point
    assert abs(prox - _ATE_TRUE) < 0.03
    assert abs(naive - _ATE_TRUE) > 0.03  # the naive adjustment is visibly biased


def test_bootstrap_ci_brackets_point():
    df = _sample_scm(40_000, seed=3)
    est = _estimate(df, ci_bootstrap=200)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    assert est.ci_lower < _ATE_TRUE < est.ci_upper


# --------------------------------------------------------------------------- #
# D1 prong 2 — refusals never fabricate a number
# --------------------------------------------------------------------------- #
def test_refuses_when_not_identifiable():
    # Z → Y breaks Z ⊥ Y | (U,X): identification refuses, estimator raises.
    g = _fig_f_graph()
    g.add_edge(Z, Y)
    df = _sample_scm(2_000, seed=4)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_proximal_ate(
            df, graph=g, treatment=X, outcome=Y, latent=U,
            treatment_proxy=(Z,), outcome_proxy=(W,),
            channel=DiscreteChannel(latent_cardinality=2),
            ci_bootstrap=0)
    assert ei.value.failure_type == "not_identifiable_proximal"


def test_refuses_on_exactly_singular_measurement_channel():
    # A degenerate channel: within every (Z, X) cell W is an exact 50/50, so
    # P(W|Z,x) has identical columns — M is singular and cannot be inverted.
    # (This is the refusable case. STATISTICAL weak-relevance — proxies only
    # loosely tied to U — is not refused; it correctly surfaces as a very wide
    # bootstrap CI, which the next test exercises.)
    import itertools
    rows = []
    for x, z, w in itertools.product([False, True], repeat=3):
        for _ in range(8):
            rows.append({"x": x, "y": bool(x and w), "z": z, "w": w})
    df = pd.DataFrame(rows)
    with pytest.raises(EstimatorFailure) as ei:
        _estimate(df, ci_bootstrap=0)
    assert ei.value.failure_type == "rank_condition_violated"


def test_weak_proxies_give_wide_ci_not_refusal():
    # Proxies only weakly relevant to U (near-independent): M is near-singular in
    # finite samples, so the point is unreliable — but the honest signal is a wide
    # CI, not a hard refusal. We assert the estimate runs and its CI is wide.
    rng = np.random.default_rng(7)
    n = 20_000
    u = rng.random(n) < 0.5
    z = rng.random(n) < np.where(u, 0.55, 0.45)   # barely tied to U
    w = rng.random(n) < np.where(u, 0.55, 0.45)
    x = rng.random(n) < np.where(u, 0.7, 0.3)
    y = rng.random(n) < (0.15 + 0.35 * x + 0.25 * u + 0.15 * w)
    df = pd.DataFrame({"x": x, "y": y, "z": z, "w": w})
    est = _estimate(df, ci_bootstrap=200)
    assert est.ci_lower is not None
    assert (est.ci_upper - est.ci_lower) > 0.2     # honest: wide, not refused


def test_refuses_on_proxy_cardinality_mismatch():
    df = _sample_scm(5_000, seed=6)
    df = df.copy()
    df["z"] = np.arange(len(df)) % 3           # Z now has 3 levels, k=2
    with pytest.raises(EstimatorFailure) as ei:
        _estimate(df, ci_bootstrap=0)
    assert ei.value.failure_type == "proxy_cardinality_mismatch"


def test_refuses_on_positivity_hole():
    # A crafted dataset where (Z=True, X=True) never co-occur: formula (5) has no
    # P(W|Z=1,X=1) column to estimate.
    rows = []
    for i in range(60):
        z = i % 2 == 0
        x = False if z else (i % 2 == 1)       # Z=True ⇒ X=False always
        rows.append({"x": bool(x), "y": bool(i % 3 == 0),
                     "z": bool(z), "w": bool(i % 2 == 1)})
    df = pd.DataFrame(rows)
    with pytest.raises(EstimatorFailure) as ei:
        _estimate(df, ci_bootstrap=0)
    assert ei.value.failure_type in ("insufficient_support", "treatment_not_binary")


def test_identify_returns_estimand_smoke():
    # sanity: the estimator's identification gate is the committed pure function
    est = identify_proximal(
        _fig_f_graph(), NO_BIDIR, treatment=X, outcome=Y, latent=U,
        treatment_proxy=(Z,), outcome_proxy=(W,),
        channel=DiscreteChannel(latent_cardinality=2))
    assert isinstance(est, ProximalEstimand)
