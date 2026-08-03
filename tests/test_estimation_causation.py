"""Numeric end for probabilities of causation — PN / PS / PNS from data.

D1 validation is an independent potential-outcome oracle. We sample a
rank-preserving monotone SCM: an OBSERVED confounder Z drives both X and Y, and
the two potential outcomes share a single uniform latent so Y_{x=1} ≥ Y_{x=0}
for every unit (monotonicity holds by construction). Because we generate the
potential outcomes directly, the true PN/PS/PNS are known exactly — computed in
two independent ways that must agree:

  * analytically (closed constants derived by hand from the SCM), and
  * empirically from the simulated Y_{x=1} / Y_{x=0} arrays.

The estimator sees only the observed (X, Y, Z) columns — never the potential
outcomes — and must recover the same numbers by back-door standardizing the
do-risks and applying Tian-Pearl. A NAIVE exogenous plug-in (do-risk = P(Y|X))
stays biased on the same data — the contrast that motivates the adjustment.

SCM (Z ~ Bernoulli(0.5); U ~ Uniform(0,1) shared across worlds):
    P(Y_{x=0}=1 | Z) = a(Z):  a(0)=0.2, a(1)=0.5
    P(Y_{x=1}=1 | Z) = b(Z):  b(0)=0.6, b(1)=0.8      (b ≥ a → monotone)
    P(X=1 | Z)       = p(Z):  p(0)=0.3, p(1)=0.7      (Z confounds X and Y)
    Y_{x} = 1{U < (b(Z) if x else a(Z))};  X ~ p(Z);  Y = Y_X (consistency)

True population quantities (hand-derived; see the module test for the algebra):
    P(Y_{x=1}=1) = 0.70   P(Y_{x=0}=1) = 0.35   PNS = 0.35
    PN = 0.165/0.37 ≈ 0.44595     PS = 0.185/0.355 ≈ 0.52113
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import pytest

from themis.estimation.causation import estimate_causation_probabilities
from themis.refusals import EstimatorFailure
from themis.types import Atom

X, Y, Z = Atom(predicate="x", args=()), Atom(predicate="y", args=()), Atom(predicate="z", args=())

PN_TRUE, PS_TRUE, PNS_TRUE = 0.165 / 0.37, 0.185 / 0.355, 0.35
DO_X1_TRUE, DO_X0_TRUE = 0.70, 0.35


def _confounded_graph() -> nx.DiGraph:
    g = nx.DiGraph()
    g.add_nodes_from([X, Y, Z])
    g.add_edges_from([(Z, X), (Z, Y), (X, Y)])  # back-door set for X→Y is {Z}
    return g


def _sample_monotone_scm(n: int, seed: int):
    """Return (observed_df, y1, y0) — the df has only x/y/z; y1/y0 are the
    hidden potential outcomes used to build the independent oracle."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)                              # shared latent (rank-preserving)
    a = np.where(z, 0.5, 0.2)                      # P(Y_{x=0}=1 | Z)
    b = np.where(z, 0.8, 0.6)                      # P(Y_{x=1}=1 | Z), b ≥ a
    y0 = u < a
    y1 = u < b
    px = np.where(z, 0.7, 0.3)                     # X depends on Z (confounding)
    x = rng.random(n) < px
    y = np.where(x, y1, y0)
    df = pd.DataFrame({"x": x, "y": y, "z": z})
    return df, y1, y0


def _estimate(df, **kw):
    return estimate_causation_probabilities(
        df, graph=_confounded_graph(), cause=X, effect=Y, **kw)


# --------------------------------------------------------------------------- #
# D1 — recover the true PN/PS/PNS from confounded data (monotonic point ID)
# --------------------------------------------------------------------------- #
def test_recovers_true_causation_points_under_confounding():
    df, y1, y0 = _sample_monotone_scm(300_000, seed=1)
    est = _estimate(df, monotonic=True, ci_bootstrap=0)

    assert est.method == "causation_plugin"
    assert est.interventional_risk_provenance == "backdoor_adjustment"
    assert est.adjustment == ("z",)

    # do-risks recovered by g-formula standardization on Z.
    assert abs(est.p_y_do_x1 - DO_X1_TRUE) < 0.01
    assert abs(est.p_y_do_x0 - DO_X0_TRUE) < 0.01

    # PN/PS/PNS points match the hand-derived truth ...
    assert abs(est.pn_point - PN_TRUE) < 0.02, f"PN {est.pn_point} vs {PN_TRUE}"
    assert abs(est.ps_point - PS_TRUE) < 0.02, f"PS {est.ps_point} vs {PS_TRUE}"
    assert abs(est.pns_point - PNS_TRUE) < 0.02, f"PNS {est.pns_point} vs {PNS_TRUE}"

    # ... and the INDEPENDENT potential-outcome oracle (never seen by estimator).
    pns_oracle = float(np.mean(y1 & ~y0))
    pn_oracle = float(np.mean(~y0[df["x"].to_numpy() & df["y"].to_numpy()]))
    ps_oracle = float(np.mean(y1[~df["x"].to_numpy() & ~df["y"].to_numpy()]))
    assert abs(est.pns_point - pns_oracle) < 0.02
    assert abs(est.pn_point - pn_oracle) < 0.02
    assert abs(est.ps_point - ps_oracle) < 0.02


def test_naive_exogenous_plug_in_is_biased():
    # Ignoring Z (treating X as exogenous) uses do-risk = P(Y|X), which the
    # confounding biases. The adjusted estimator recovers the truth; the naive
    # contrast does not — the reason the back-door standardization is there.
    df, _y1, _y0 = _sample_monotone_scm(300_000, seed=2)
    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    naive_do_x1 = y[x].mean()
    naive_do_x0 = y[~x].mean()
    assert abs(naive_do_x1 - DO_X1_TRUE) > 0.02      # visibly biased up
    assert abs(naive_do_x0 - DO_X0_TRUE) > 0.02      # visibly biased down
    est = _estimate(df, monotonic=True, ci_bootstrap=0)
    assert abs(est.p_y_do_x1 - DO_X1_TRUE) < 0.01    # adjustment removes it
    assert abs(est.p_y_do_x0 - DO_X0_TRUE) < 0.01


def test_bootstrap_ci_brackets_the_points():
    df, _y1, _y0 = _sample_monotone_scm(40_000, seed=3)
    est = _estimate(df, monotonic=True, ci_bootstrap=200)
    for pt, lo, hi, truth in (
        (est.pn_point, est.pn_point_ci_lower, est.pn_point_ci_upper, PN_TRUE),
        (est.ps_point, est.ps_point_ci_lower, est.ps_point_ci_upper, PS_TRUE),
        (est.pns_point, est.pns_point_ci_lower, est.pns_point_ci_upper, PNS_TRUE),
    ):
        assert lo is not None and hi is not None
        assert lo <= pt <= hi
        assert lo < truth < hi


def _sample_nonmonotone_scm(n: int, seed: int):
    """Independent latents for the two worlds → some units are 'preventers'
    (Y_{x=1} < Y_{x=0}), so monotonicity fails. The OBSERVED marginals (each
    arm's risk, the X/Y joint) are distributionally identical to the monotone
    SCM, so the data-based bounds are the same — but the true PN/PS/PNS now sit
    STRICTLY INSIDE the bounds (the dependence between worlds, which data cannot
    see, moved them off the boundary). Returns (df, y1, y0)."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    a = np.where(z, 0.5, 0.2)
    b = np.where(z, 0.8, 0.6)
    y0 = rng.random(n) < a                          # independent draw ...
    y1 = rng.random(n) < b                          # ... from the other world
    px = np.where(z, 0.7, 0.3)
    x = rng.random(n) < px
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z}), y1, y0


def test_bounds_contain_the_truth_without_monotonicity():
    # No monotonicity assumed → points are None, only assumption-free bounds.
    # Use a NON-monotone SCM whose true PN/PS/PNS lie strictly inside the
    # bounds (a monotone SCM would sit exactly on the lower bound, making
    # containment a knife-edge fooled by sampling noise). Truth is read off the
    # simulated potential outcomes — the estimator never sees them.
    df, y1, y0 = _sample_nonmonotone_scm(300_000, seed=4)
    est = _estimate(df, monotonic=False, ci_bootstrap=0)
    assert est.pn_point is None and est.ps_point is None and est.pns_point is None

    x, yv = df["x"].to_numpy(), df["y"].to_numpy()
    pns_true = float(np.mean(y1 & ~y0))
    pn_true = float(np.mean(~y0[x & yv]))
    ps_true = float(np.mean(y1[~x & ~yv]))
    assert est.pn_lower < pn_true < est.pn_upper
    assert est.ps_lower < ps_true < est.ps_upper
    assert est.pns_lower < pns_true < est.pns_upper


# --------------------------------------------------------------------------- #
# do-risk provenance branches
# --------------------------------------------------------------------------- #
def test_exogenous_no_confounder_uses_conditional_risk():
    # X randomized (no confounder): do-risk = P(Y|X); adjustment set is empty.
    rng = np.random.default_rng(7)
    n = 200_000
    x = rng.random(n) < 0.5
    u = rng.random(n)
    y = np.where(x, u < 0.7, u < 0.3)              # monotone, ATE = 0.4
    df = pd.DataFrame({"x": x, "y": y})
    g = nx.DiGraph()
    g.add_nodes_from([X, Y])
    g.add_edge(X, Y)
    est = estimate_causation_probabilities(
        df, graph=g, cause=X, effect=Y, monotonic=True, ci_bootstrap=0)
    assert est.interventional_risk_provenance == "exogenous"
    assert est.adjustment == ()
    assert abs(est.p_y_do_x1 - 0.7) < 0.01
    assert abs(est.p_y_do_x0 - 0.3) < 0.01
    assert abs(est.pns_point - 0.4) < 0.02


def test_experimental_risks_pass_through():
    # Confounded-but-experimentally-measured (drug example): the do-risks come
    # from a randomized experiment and pass straight through; only the joint is
    # estimated from data. Cross-checked against a direct oracle call.
    from themis.runtime.probabilities_of_causation import probabilities_of_causation

    rng = np.random.default_rng(11)
    n = 50_000
    x = rng.random(n) < 0.5
    y = rng.random(n) < np.where(x, 0.6, 0.4)
    df = pd.DataFrame({"x": x, "y": y})
    g = nx.DiGraph()
    g.add_nodes_from([X, Y])
    g.add_edge(X, Y)
    est = estimate_causation_probabilities(
        df, graph=g, cause=X, effect=Y, monotonic=True,
        experimental_risk_treated=0.55, experimental_risk_control=0.30,
        ci_bootstrap=0)
    assert est.interventional_risk_provenance == "user_experimental"
    assert est.p_y_do_x1 == 0.55 and est.p_y_do_x0 == 0.30
    oracle = probabilities_of_causation(
        p_x1_y1=est.p_x1_y1, p_x1_y0=est.p_x1_y0,
        p_x0_y1=est.p_x0_y1, p_x0_y0=est.p_x0_y0,
        p_y_do_x1=0.55, p_y_do_x0=0.30, monotonic=True)
    assert est.pn_point == pytest.approx(oracle.pn_point)
    assert est.ps_point == pytest.approx(oracle.ps_point)
    assert est.pns_point == pytest.approx(oracle.pns_point)


# --------------------------------------------------------------------------- #
# refusals never fabricate a number
# --------------------------------------------------------------------------- #
def test_refuses_unmeasured_confounder_without_experiment():
    # A latent bow X ↔ Y and no measured confounder: the do-risks are not
    # back-door identifiable and no experimental risks were supplied → refuse.
    df, _y1, _y0 = _sample_monotone_scm(2_000, seed=5)
    g = nx.DiGraph()
    g.add_nodes_from([X, Y])
    g.add_edge(X, Y)
    bidir = frozenset({frozenset({X, Y})})
    with pytest.raises(EstimatorFailure):
        estimate_causation_probabilities(
            df[["x", "y"]], graph=g, bidirected=bidir, cause=X, effect=Y,
            monotonic=True, ci_bootstrap=0)


def test_refuses_non_binary_effect():
    rng = np.random.default_rng(9)
    n = 5_000
    x = rng.random(n) < 0.5
    y = rng.integers(0, 3, n)                       # ternary — not binary
    df = pd.DataFrame({"x": x, "y": y})
    g = nx.DiGraph()
    g.add_nodes_from([X, Y])
    g.add_edge(X, Y)
    with pytest.raises(EstimatorFailure):
        estimate_causation_probabilities(
            df, graph=g, cause=X, effect=Y, monotonic=True, ci_bootstrap=0)


def test_refuses_positivity_violation():
    # A stratum with no treated units (Z=1 ⇒ X=0 always) breaks standardization.
    rng = np.random.default_rng(13)
    n = 10_000
    z = rng.random(n) < 0.5
    x = np.where(z, False, rng.random(n) < 0.5)     # Z=1 → never treated
    y = rng.random(n) < 0.5
    df = pd.DataFrame({"x": x, "y": y, "z": z})
    with pytest.raises(EstimatorFailure):
        _estimate(df, monotonic=True, ci_bootstrap=0)
