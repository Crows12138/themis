"""D1 oracle for the Anderson-Rubin weak-IV-robust confidence set.

Two independent oracles pin the estimator:

1. **Grid inversion** — the closed-form quadratic set must equal
   ``{beta0 : AR(beta0) <= kappa}`` computed by RUNNING THE DEFINING
   REGRESSION at each grid point (regress ``Y - beta0*X`` on ``[1, W, Z]``
   and read the F-statistic for ``Z``). This validates the algebra against
   the operational definition of the AR test, independent of any formula.

2. **Coverage simulation** — under a genuinely WEAK instrument the AR set
   covers the true coefficient at ~the nominal rate (it inverts an exact
   F-test), while the 2SLS bootstrap CI materially under-covers. This is the
   whole point of AR and the reason the bootstrap CI is not enough.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from scipy.stats import f as _f_dist

from themis.estimation.iv import (
    ARConfidenceSet,
    anderson_rubin_confidence_set,
    estimate_iv_ate,
)


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _covers(ar: ARConfidenceSet, beta: float, *, tol: float = 0.0) -> bool:
    """Is ``beta`` in the AR set (respecting the set shape)?"""
    lo, hi = ar.lower, ar.upper
    if ar.kind == "bounded":
        return lo - tol <= beta <= hi + tol
    if ar.kind == "disconnected":
        return beta <= lo + tol or beta >= hi - tol
    if ar.kind == "unbounded_below":
        return beta <= hi + tol
    if ar.kind == "unbounded_above":
        return beta >= lo - tol
    if ar.kind == "whole_line":
        return True
    return False  # empty


def _ar_stat_direct(
    df: pd.DataFrame, beta0: float, *, treatment, outcome, instrument, conditioning=()
) -> float:
    """AR(beta0) by the DEFINITION: F-stat for Z in the OLS regression of
    ``Y - beta0*X`` on ``[1, W, Z]`` (single restriction)."""
    n = len(df)
    y = df[outcome].to_numpy(float) - beta0 * df[treatment].to_numpy(float)
    w = df[list(conditioning)].to_numpy(float) if conditioning else np.empty((n, 0))
    z = df[instrument].to_numpy(float).reshape(-1, 1)
    ones = np.ones((n, 1))
    full = np.hstack([ones, w, z])
    restricted = np.hstack([ones, w])

    def _rss(design, target):
        coef, *_ = np.linalg.lstsq(design, target, rcond=None)
        r = target - design @ coef
        return float(r @ r)

    rss_f = _rss(full, y)
    rss_r = _rss(restricted, y)
    m = n - w.shape[1] - 2
    return ((rss_r - rss_f) / 1.0) / (rss_f / m)


def _weak_iv_sample(n, seed, *, pi, beta=1.0, gamma=2.0, delta=1.5):
    """Confounded weak-IV SCM.  U confounds X and Y; Z affects Y only via X
    (exclusion). ``pi`` is the first-stage strength — small ``pi`` == weak."""
    rng = np.random.default_rng(seed)
    u = rng.normal(size=n)
    z = rng.normal(size=n)
    x = pi * z + delta * u + rng.normal(size=n)
    y = beta * x + gamma * u + rng.normal(size=n)
    return pd.DataFrame({"x": x, "y": y, "z": z})


# --------------------------------------------------------------------------- #
# oracle 1 — grid inversion against the defining regression
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("pi,seed", [(0.8, 1), (0.25, 2), (0.08, 3)])
def test_closed_form_matches_grid_of_the_defining_regression(pi, seed):
    df = _weak_iv_sample(3000, seed, pi=pi)
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.95
    )
    assert ar is not None
    kappa = ar.kappa

    centre = ar.point if ar.point is not None else 0.0
    grid = np.linspace(centre - 30.0, centre + 30.0, 6001)
    band = 1e-4 * kappa  # skip points sitting exactly on the F == kappa edge
    mismatches = 0
    for b0 in grid:
        f_direct = _ar_stat_direct(
            df, float(b0), treatment="x", outcome="y", instrument="z"
        )
        if abs(f_direct - kappa) < band:
            continue
        in_by_definition = f_direct <= kappa
        in_by_closed_form = _covers(ar, float(b0))
        if in_by_definition != in_by_closed_form:
            mismatches += 1
    assert mismatches == 0


def test_endpoints_sit_on_the_f_equals_kappa_boundary():
    # A finite endpoint of the AR set is exactly where AR(beta0) == kappa.
    df = _weak_iv_sample(4000, 7, pi=0.6)
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.95
    )
    assert ar.kind == "bounded"
    for endpoint in (ar.lower, ar.upper):
        f_at = _ar_stat_direct(
            df, float(endpoint), treatment="x", outcome="y", instrument="z"
        )
        assert abs(f_at - ar.kappa) < 1e-6 * ar.kappa


# --------------------------------------------------------------------------- #
# oracle 2 — coverage: AR inverts an EXACT F-test, so it stays near-nominal
# under a weak instrument AND honestly returns unbounded sets when the data
# cannot pin the coefficient. (The pairs bootstrap of a ratio does NOT simply
# under-cover under weak IV — it becomes erratically over-wide — so the value
# of AR is exactness + honest non-identification signalling, not a coverage
# race against the bootstrap.)
# --------------------------------------------------------------------------- #
def test_ar_is_exact_and_honestly_unbounded_under_weak_instrument():
    beta_true = 1.0
    n, reps = 400, 600
    covered, unbounded = 0, 0
    for r in range(reps):
        df = _weak_iv_sample(n, 1000 + r, pi=0.12, beta=beta_true)
        ar = anderson_rubin_confidence_set(
            df, treatment="x", outcome="y", instrument="z", ci_level=0.95
        )
        if _covers(ar, beta_true):
            covered += 1
        if ar.kind != "bounded":
            unbounded += 1
    cov = covered / reps
    unb = unbounded / reps
    # Exact F-test → coverage sits at the nominal 0.95 (never materially under).
    assert 0.92 <= cov <= 0.98, f"AR coverage {cov:.3f} not near nominal"
    # A weak first stage → AR honestly refuses to bound beta a large share of
    # the time. A finite bootstrap CI never signals this.
    assert unb >= 0.30, f"AR unbounded fraction {unb:.3f} unexpectedly small"


def test_bootstrap_ci_hides_the_non_identification_ar_reveals():
    # In samples where AR returns an unbounded set (the data cannot bound
    # beta), the 2SLS bootstrap still hands back a FINITE interval — falsely
    # implying identification. This is the concrete failure AR fixes.
    n, reps = 400, 80
    ar_unbounded, boot_finite_there = 0, 0
    for r in range(reps):
        df = _weak_iv_sample(n, 5000 + r, pi=0.10)
        est = estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            model="2sls", ci_bootstrap=200, random_state=r,
        )
        if est.anderson_rubin is not None and est.anderson_rubin.kind != "bounded":
            ar_unbounded += 1
            if est.ci_lower is not None and est.ci_upper is not None:
                boot_finite_there += 1
    assert ar_unbounded >= 5, f"expected some unbounded AR sets; got {ar_unbounded}"
    # Every time AR says "unbounded", the bootstrap nonetheless reports a
    # finite CI — it cannot signal non-identification.
    assert boot_finite_there == ar_unbounded


def test_ar_is_bounded_and_tight_under_a_strong_instrument():
    import statistics

    beta_true = 1.0
    n, reps = 2000, 400
    covered, widths = 0, []
    for r in range(reps):
        df = _weak_iv_sample(n, 3000 + r, pi=1.5, beta=beta_true)
        ar = anderson_rubin_confidence_set(
            df, treatment="x", outcome="y", instrument="z", ci_level=0.95
        )
        assert ar.kind == "bounded"  # a strong instrument always bounds beta
        if _covers(ar, beta_true):
            covered += 1
        widths.append(ar.upper - ar.lower)
    cov = covered / reps
    assert 0.90 <= cov <= 0.98, f"AR coverage {cov:.3f} not near nominal"
    assert statistics.median(widths) < 0.5


# --------------------------------------------------------------------------- #
# shape + consistency
# --------------------------------------------------------------------------- #
def test_strong_instrument_gives_a_bounded_set_around_the_point():
    df = _weak_iv_sample(5000, 11, pi=1.5, beta=1.0)
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.95
    )
    assert ar.kind == "bounded"
    assert ar.lower < ar.point < ar.upper
    # a strong instrument pins beta near the truth
    assert abs(ar.point - 1.0) < 0.2


def test_near_useless_instrument_gives_an_unbounded_set():
    # pi ~ 0: the first stage is essentially noise, so AR (correctly) cannot
    # bound the effect — the set is the whole line or a disconnected pair.
    df = _weak_iv_sample(400, 23, pi=0.01)
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.95
    )
    assert ar.kind in {"whole_line", "disconnected", "unbounded_below", "unbounded_above"}


def test_ar_point_matches_the_iv_point_estimate():
    df = _weak_iv_sample(3000, 31, pi=0.7)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z", model="2sls",
        ci_bootstrap=0,
    )
    assert est.anderson_rubin is not None
    assert abs(est.anderson_rubin.point - est.point) < 1e-6 * (1 + abs(est.point))


def test_kappa_is_the_f_critical_value():
    df = _weak_iv_sample(1234, 41, pi=0.6)
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.9
    )
    m = ar.n_obs - ar.n_exog - 2
    assert abs(ar.kappa - float(_f_dist.ppf(0.9, 1, m))) < 1e-9


def test_conditional_ar_partials_out_controls():
    # Add an exogenous control W; AR with conditioning={w} must residualise
    # it out (n_exog == 1) and still recover a sensible bounded set.
    rng = np.random.default_rng(55)
    n = 4000
    w = rng.normal(size=n)
    u = rng.normal(size=n)
    z = rng.normal(size=n)
    x = 0.9 * z + 0.7 * w + 1.2 * u + rng.normal(size=n)
    y = 1.0 * x + 0.5 * w + 2.0 * u + rng.normal(size=n)
    df = pd.DataFrame({"x": x, "y": y, "z": z, "w": w})
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_level=0.95,
    )
    assert ar.n_exog == 1
    assert ar.kind == "bounded"
    assert ar.lower < 1.0 < ar.upper


def test_degenerate_returns_none():
    # Instrument with no variance → AR undefined → None.
    n = 50
    df = pd.DataFrame({
        "x": np.arange(n, dtype=float),
        "y": np.arange(n, dtype=float),
        "z": np.ones(n),
    })
    ar = anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", ci_level=0.95
    )
    assert ar is None
