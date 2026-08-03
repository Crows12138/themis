"""Covariate-differential outcome misclassification — estimator + D1 + verifier.

Extends differential misclassification (whose axis was hardcoded to the exposure
arm) to a matrix that varies by a back-door COVARIATE stratum
(``differential_by=<covariate>``): the misclassification rate differs by e.g.
site/age. Within each stratum the correction inverts that covariate level's own
matrix; pooling a single matrix (or misreading the per-site matrices as per-arm)
is biased.

D1 oracle discipline: a synthetic SCM simulates the latent true outcome Y*, so
the empirical back-door RD on Y* is known. The observed Y passes through a
site-specific Se/Sp channel. The per-covariate-stratum correction — seeing ONLY
the observed Y — must recover the latent-true RD, while a POOLED-matrix correction
misses it.
"""
import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.measurement import (
    estimate_measurement_correction,
    MeasurementCorrectionEstimate,
)
from themis.refusals import EstimatorFailure


def _binary_M(se, sp):
    """Column-stochastic 2x2, states order [0, 1]: M[i][j] = P(Y=i | Y*=j)."""
    return np.array([[sp, 1 - se], [1 - sp, se]], dtype=float)


# Site-specific channels: site 0 accurate, site 1 noisy (a wide spread so a
# pooled matrix is clearly wrong).
_SE = {0: 0.97, 1: 0.62}
_SP = {0: 0.97, 1: 0.62}


def _make_data(*, n=300_000, effect0=0.32, effect1=0.08, seed=7):
    """z (site) confounder → x, → Y*; observed Y through a per-SITE Se/Sp channel.
    The causal RD VARIES by site (effect0 vs effect1) so a pooled matrix — which
    mis-weights the two sites' corrections — biases the standardised RD (with a
    constant RD the per-site over/under-corrections would cancel).
    Returns (df, empirical_true_RD)."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, size=n)
    px = 0.30 + 0.40 * z
    x = (rng.random(n) < px).astype(int)
    eff = np.where(z == 1, effect1, effect0)
    p_true = 0.25 + eff * x + 0.20 * z
    ystar = (rng.random(n) < p_true).astype(int)

    true_rd = 0.0
    for zv in (0, 1):
        m = z == zv
        true_rd += (ystar[m & (x == 1)].mean() - ystar[m & (x == 0)].mean()) * m.mean()

    u = rng.random(n)
    y = np.empty(n, dtype=int)
    for zv in (0, 1):
        m = z == zv
        se, sp = _SE[zv], _SP[zv]
        y[m] = np.where(ystar[m] == 1, (u[m] < se).astype(int),
                        (u[m] < (1 - sp)).astype(int))
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    return df, float(true_rd)


def _diff_spec():
    return dict(
        differential=True, differential_by="z",
        confusion_matrices=[_binary_M(_SE[0], _SP[0]).tolist(),
                            _binary_M(_SE[1], _SP[1]).tolist()],
        differential_levels=[0, 1],
    )


# --- D1 -----------------------------------------------------------------------


def test_per_covariate_correction_recovers_truth_while_pooled_is_biased():
    df, true_rd = _make_data()
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[0, 1], target_value=1, ci_bootstrap=0, **_diff_spec(),
    )
    assert isinstance(est, MeasurementCorrectionEstimate)
    # Per-covariate-stratum correction recovers the latent-true RD.
    assert est.point == pytest.approx(true_rd, abs=0.02)
    # The naive (observed) back-door RD is attenuated away from the truth.
    assert abs(est.naive_point - true_rd) > 0.03

    # A POOLED single matrix (average of the two site matrices) misses the truth
    # by more than the tolerance — the capability matters.
    Mpool = 0.5 * (_binary_M(_SE[0], _SP[0]) + _binary_M(_SE[1], _SP[1]))
    Minv = np.linalg.inv(Mpool)
    pooled = 0.0
    for zv in (0, 1):
        m = df["z"] == zv
        pz = m.mean()
        risk = {}
        for arm in (0, 1):
            mm = m & (df["x"] == arm)
            p_obs = np.array([(df["y"][mm] == 0).mean(), (df["y"][mm] == 1).mean()])
            risk[arm] = (Minv @ p_obs)[1]
        pooled += (risk[1] - risk[0]) * pz
    assert abs(pooled - true_rd) > 0.02


def test_records_differential_by_and_by_level():
    df, _ = _make_data(n=20_000)
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[0, 1], target_value=1, ci_bootstrap=0, **_diff_spec(),
    )
    assert est.differential is True
    assert est.differential_by == "z"
    ss = est.sufficient_statistics
    assert ss["differential_by"] == "z"
    assert "confusion_matrices_by_level" in ss
    levels = {r["level"] for r in ss["confusion_matrices_by_level"]}
    assert levels == {0, 1}
    assert "confusion_matrices_by_arm" not in ss


def test_arm_differential_still_default_without_differential_by():
    """Backward compat: differential without differential_by is per-arm (records
    confusion_matrices_by_arm, no differential_by)."""
    df, _ = _make_data(n=20_000)
    Ma = _binary_M(0.9, 0.9).tolist()
    Mb = _binary_M(0.75, 0.8).tolist()
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[0, 1], target_value=1, ci_bootstrap=0,
        differential=True, confusion_matrices=[Ma, Mb], differential_levels=[0, 1],
    )
    assert est.differential_by is None
    assert "confusion_matrices_by_arm" in est.sufficient_statistics
    assert "confusion_matrices_by_level" not in est.sufficient_statistics


# --- guards -------------------------------------------------------------------


def test_differential_by_unknown_refuses():
    df, _ = _make_data(n=5000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[0, 1], target_value=1, ci_bootstrap=0,
            differential=True, differential_by="not_a_var",
            confusion_matrices=[_binary_M(0.9, 0.9).tolist(),
                                _binary_M(0.7, 0.7).tolist()],
            differential_levels=[0, 1],
        )
    assert exc.value.failure_type == "differential_by_unknown"


def test_uncovered_covariate_level_refuses():
    """A covariate value with no matrix in the set is refused, not silently
    dropped."""
    df, _ = _make_data(n=20_000)
    df = df.copy()
    df.loc[df.index[:4000], "z"] = 2  # a third stratum with no matrix supplied
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[0, 1], target_value=1, ci_bootstrap=0, **_diff_spec(),
        )
    assert exc.value.failure_type == "differential_level_uncovered"


# --- e2e dispatch + verify ----------------------------------------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x"},
            {"kind": "variable", "predicate": "y", "measurement": "accuracy varies by site"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {"kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}}]}


def _e2e_spec():
    s = _diff_spec()
    s["states"] = [False, True]   # match the query's boolean target value
    return {"y": s}


def test_dispatch_e2e_covariate_differential_flips_and_recovers():
    df, true_rd = _make_data(n=80_000)
    out = themis.estimate(_program(), df, ci_bootstrap=0, misclassification=_e2e_spec())
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "measurement_error_correction"
    assert ne["measurement_correction"]["differential_by"] == "z"
    assert ne["point"] == pytest.approx(true_rd, abs=0.03)


def _e2e_result(seed=7):
    df, _ = _make_data(n=60_000, seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_e2e_spec())
    return prog, out["results"][0]


def test_verify_accepts_honest_e2e():
    prog, r = _e2e_result()
    themis.verify(prog, r)  # must not raise


def test_verify_rejects_forged_point():
    prog, r = _e2e_result()
    r["numeric_estimate"]["point"] = 0.05
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_tampered_level_matrix():
    prog, r = _e2e_result()
    r["numeric_estimate"]["measurement_correction"]["sufficient_statistics"][
        "confusion_matrices_by_level"][1]["matrix"] = [[0.99, 0.01], [0.01, 0.99]]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_differential_by_mismatch():
    prog, r = _e2e_result()
    r["numeric_estimate"]["measurement_correction"]["differential_by"] = "x"
    with pytest.raises(Exception):
        themis.verify(prog, r)
