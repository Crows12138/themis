"""Regression calibration (continuous mismeasurement) — estimator + D1.

Continuous counterpart of frontier E: the structural layer only *flags*
measurement error (``measurement_error_concern``). This numeric end de-attenuates
a continuously-mismeasured EXPOSURE (classical additive error W = X* + U, known
error variance σ²_u) by the regression-calibration moment correction
β_true = (Σ_WZ − E)⁻¹ Σ_WZ b_naive, E = diag(σ²_u, 0, …).

D1 oracle discipline — two independent routes agree with the LATENT truth:

- Ground truth: a synthetic linear SCM where the true exposure X* is simulated,
  so the structural slope βx is known. The observed W = X* + U carries a known
  error variance σ²_u. The corrected estimate — which sees ONLY W — must recover
  βx; the naive OLS slope on W must be attenuated by the reliability ratio λ.
- Cross-check: the full matrix correction (Σ_WZ − E)⁻¹ Σ_WZ b (pick the exposure
  component) must equal the algebraically independent univariate reliability-ratio
  route b_naive / λ, with λ = 1 − σ²_u / Var(W|Z).
"""
import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.regression_calibration import (
    estimate_regression_calibration,
    RegressionCalibrationEstimate,
)
from themis.estimation.dose_response import EstimatorFailure


# --- synthetic linear SCM with a latent true exposure + classical error -------


def _make_data(*, n=200_000, bx=0.8, bz=1.0, a=0.5, tau2=1.0, su2=1.0, seed=7):
    """Z → X*, X*/Z → Y linear SCM; observed W = X* + U with Var(U)=σ²_u.

    Returns (df_with_observed_W, bx, bz, lam) where lam = Var(X*|Z)/Var(W|Z) =
    tau2/(tau2+su2) is the population reliability ratio the naive slope is
    attenuated by. The frame carries the observed W as ``x``; X* is never seen."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    xstar = a * z + rng.normal(0, np.sqrt(tau2), n)
    y = 0.3 + bx * xstar + bz * z + rng.normal(0, 1.0, n)
    w = xstar + rng.normal(0, np.sqrt(su2), n)
    df = pd.DataFrame({"x": w, "y": y, "z": z})
    lam = tau2 / (tau2 + su2)
    return df, bx, bz, lam


# --- D1: recovery of the latent-true slope ------------------------------------


def test_corrected_recovers_true_slope_while_naive_attenuates():
    df, bx, bz, lam = _make_data(su2=1.0, tau2=1.0)  # λ ≈ 0.5
    est = estimate_regression_calibration(
        df, treatment="x", outcome="y", adjustment=("z",),
        error_variance=1.0, ci_bootstrap=0,
    )
    assert isinstance(est, RegressionCalibrationEstimate)
    # Corrected slope recovers the latent-true βx (sees only observed W).
    assert est.point == pytest.approx(bx, abs=0.02)
    # Naive OLS slope on W is attenuated by the reliability ratio λ.
    assert est.naive_point == pytest.approx(bx * lam, abs=0.02)
    assert est.reliability == pytest.approx(lam, abs=0.02)


def test_matrix_form_equals_reliability_ratio_route():
    """Cross-check: the full moment correction (pick the exposure component)
    equals the algebraically independent scalar route naive / λ."""
    df, _bx, _bz, _lam = _make_data(seed=11, su2=0.7, tau2=1.3)
    est = estimate_regression_calibration(
        df, treatment="x", outcome="y", adjustment=("z",),
        error_variance=0.7, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(est.naive_point / est.reliability, abs=1e-9)


def test_also_corrects_the_covariate_coefficient():
    """Classical error on W biases the covariate coefficient too (via the
    W–Z correlation); regression calibration de-biases the whole vector."""
    df, bx, bz, _lam = _make_data(seed=3, su2=1.0, tau2=1.0, a=0.6)
    est = estimate_regression_calibration(
        df, treatment="x", outcome="y", adjustment=("z",),
        error_variance=1.0, ci_bootstrap=0,
    )
    # corrected_slope = [βx, βz]; both recovered, naive βz is biased away.
    assert est.corrected_slope[0] == pytest.approx(bx, abs=0.02)
    assert est.corrected_slope[1] == pytest.approx(bz, abs=0.02)
    assert abs(est.naive_slope[1] - bz) > 0.05


def test_no_adjustment_marginal_reliability():
    """With no covariate the correction is the marginal reliability route."""
    df, _bx, _bz, _lam = _make_data(seed=5)
    est = estimate_regression_calibration(
        df, treatment="x", outcome="y", adjustment=(),
        error_variance=1.0, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(est.naive_point / est.reliability, abs=1e-9)


def test_bootstrap_ci_brackets_truth():
    df, bx, _bz, _lam = _make_data(seed=9, n=40_000)
    est = estimate_regression_calibration(
        df, treatment="x", outcome="y", adjustment=("z",),
        error_variance=1.0, ci_bootstrap=300, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= bx <= est.ci_upper
    assert est.ci_lower <= est.point <= est.ci_upper


# --- guards (honest refusals, not silent numbers) -----------------------------


def test_non_positive_error_variance_refuses():
    df, *_ = _make_data(n=5000)
    for bad in (0.0, -1.0, float("nan")):
        with pytest.raises(EstimatorFailure) as exc:
            estimate_regression_calibration(
                df, treatment="x", outcome="y", adjustment=("z",),
                error_variance=bad, ci_bootstrap=0,
            )
        assert exc.value.failure_type == "non_positive_error_variance"


def test_degenerate_reliability_refuses():
    """σ²_u >= Var(W|Z) ⇒ λ <= 0 ⇒ corrected design not positive definite."""
    df, *_ = _make_data(n=5000, su2=1.0, tau2=1.0)  # Var(W|Z) ≈ 2
    with pytest.raises(EstimatorFailure) as exc:
        estimate_regression_calibration(
            df, treatment="x", outcome="y", adjustment=("z",),
            error_variance=100.0, ci_bootstrap=0,
        )
    assert exc.value.failure_type == "degenerate_reliability"


def test_discrete_exposure_refuses_pointing_at_confusion_matrix():
    df, *_ = _make_data(n=5000)
    df = df.copy()
    df["x"] = (df["x"] > 0).astype(float)  # binarise the exposure
    with pytest.raises(EstimatorFailure) as exc:
        estimate_regression_calibration(
            df, treatment="x", outcome="y", adjustment=("z",),
            error_variance=0.1, ci_bootstrap=0,
        )
    assert exc.value.failure_type == "exposure_not_continuous"


# --- e2e dispatch + verify ----------------------------------------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program(*, bidirected=False):
    """W→Y + Z→W + Z→Y back-door program; noisy continuous exposure W.
    Optionally add a latent confounder W<->Y so no back-door set exists."""
    stmts = [
        {"kind": "variable", "predicate": "x",
         "measurement": "single-occasion continuous measurement (noisy)"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "variable", "predicate": "z"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
    ]
    if bidirected:
        stmts.append({"kind": "bidirected", "left": _atom("x"), "right": _atom("y")})
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True}, "given": []}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": stmts}


def _spec(su2=1.0):
    return {"x": {"error_variance": su2}}


def test_dispatch_e2e_corrects_and_flips_status():
    df, bx, _bz, _lam = _make_data(seed=11, n=50_000)
    out = themis.estimate(_program(), df, ci_bootstrap=0, measurement_error=_spec())
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "regression_calibration"
    assert ne["point"] == pytest.approx(bx, abs=0.03)
    assert ne["regression_calibration"]["naive_point"] < ne["point"]  # attenuated


def test_verify_accepts_honest_e2e():
    df, *_ = _make_data(seed=11, n=40_000)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, measurement_error=_spec())
    themis.verify(prog, out["results"][0])  # must not raise


def _e2e_result(seed=11, n=40_000):
    df, *_ = _make_data(seed=seed, n=n)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, measurement_error=_spec())
    return prog, out["results"][0]


def test_verify_rejects_forged_point():
    prog, r = _e2e_result()
    r["numeric_estimate"]["point"] = 0.5
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_forged_naive():
    prog, r = _e2e_result()
    r["numeric_estimate"]["regression_calibration"]["naive_point"] = 0.1
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_forged_reliability():
    prog, r = _e2e_result()
    r["numeric_estimate"]["regression_calibration"]["reliability"] = 0.99
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_tampered_covariance():
    prog, r = _e2e_result()
    r["numeric_estimate"]["regression_calibration"][
        "sufficient_statistics"]["cov_matrix"][0][0] = 5.0
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_degenerate_error_variance():
    prog, r = _e2e_result()
    r["numeric_estimate"]["regression_calibration"][
        "sufficient_statistics"]["error_variance"] = 100.0
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_non_symmetric_covariance():
    prog, r = _e2e_result()
    # Break symmetry on an off-diagonal without touching its mirror.
    r["numeric_estimate"]["regression_calibration"][
        "sufficient_statistics"]["cov_matrix"][0][1] += 0.5
    with pytest.raises(Exception):
        themis.verify(prog, r)


# --- honest gates -------------------------------------------------------------


def test_not_backdoor_identified_refuses():
    """A latent W<->Y confounder ⇒ no back-door set ⇒ refuse, not a naive slope."""
    df, *_ = _make_data(seed=11, n=20_000)
    out = themis.estimate(
        _program(bidirected=True), df, ci_bootstrap=0, measurement_error=_spec(),
    )
    r = out["results"][0]
    assert r.get("status") != "numerically_solved"
    fail = r.get("estimator_failure")
    if fail is not None:
        assert fail["estimator"] == "regression_calibration"
        assert fail["failure_type"] == "requires_backdoor_identification"


def test_continuous_outcome_mismeasurement_deferred():
    """A σ²_u on the OUTCOME is refused (exposure-side only), not silently ignored."""
    df, *_ = _make_data(seed=11, n=20_000)
    out = themis.estimate(
        _program(), df, ci_bootstrap=0, measurement_error={"y": {"error_variance": 1.0}},
    )
    fail = out["results"][0].get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "continuous_outcome_mismeasurement_deferred"


def test_combined_mismeasurement_deferred():
    """σ²_u for BOTH exposure and outcome ⇒ combined correction refused."""
    df, *_ = _make_data(seed=11, n=20_000)
    out = themis.estimate(
        _program(), df, ci_bootstrap=0,
        measurement_error={"x": {"error_variance": 1.0}, "y": {"error_variance": 1.0}},
    )
    fail = out["results"][0].get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "combined_mismeasurement_deferred"
