"""Measurement-error correction (confusion-matrix inversion) — estimator + D1.

Frontier E: the structural layer only *flags* measurement error
(``measurement_error_concern``). This numeric end de-attenuates a misclassified
discrete OUTCOME when a validated confusion matrix is supplied, via per-stratum
matrix inversion (Rogan-Gladen for the binary case).

D1 oracle discipline — two independent routes agree with the LATENT truth:

- Ground truth: a synthetic SCM where the true outcome Y* is simulated, so the
  empirical back-door RD on Y* is known. The observed Y is Y* passed through a
  known Se/Sp channel (non-differentially). The corrected estimate — which sees
  ONLY the observed Y — must recover the latent-true RD; the naive estimate must
  be attenuated by det(M) = Se+Sp−1.
- Cross-check: for a binary outcome the full matrix inversion + pick-target-
  component must equal the algebraically independent scalar Rogan-Gladen route
  (corrected_RD == naive_RD / det).
"""
import numpy as np
import pandas as pd
import pytest

from themis.estimation.measurement import (
    estimate_measurement_correction,
    MeasurementCorrectionEstimate,
)
from themis.estimation.dose_response import EstimatorFailure


# --- synthetic SCM with a latent true outcome + a known Se/Sp channel ---------


def _make_data(
    *, n=40000, effect=0.20, seed=7, se=0.90, sp=0.85, differential=False,
):
    """Z→X, Z→Y*, X→Y* linear-risk SCM; observed Y = Y* through an Se/Sp channel.

    Returns (df_with_observed_Y, empirical_true_RD, se, sp). The frame carries
    the observed (misclassified) ``y``; ``y_true`` is dropped from what the
    estimator sees (it standardises on ``y``)."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, size=n)
    # Confounding: treatment probability depends on Z.
    px = 0.30 + 0.40 * z
    x = (rng.random(n) < px).astype(int)
    # True outcome risk: base + effect*X + zeff*Z (constant RD in X across z).
    p_true = 0.25 + effect * x + 0.20 * z
    y_true = (rng.random(n) < p_true).astype(int)

    # Empirical latent-true back-door RD (the target the correction must hit).
    true_rd = 0.0
    for zval in (0, 1):
        m = z == zval
        pz = m.mean()
        r1 = y_true[m & (x == 1)].mean()
        r0 = y_true[m & (x == 0)].mean()
        true_rd += (r1 - r0) * pz

    # Observed outcome through the misclassification channel.
    u = rng.random(n)
    if differential:
        # Sensitivity differs by arm (for the differential-refusal test data).
        se_arm = np.where(x == 1, se, se - 0.15)
        keep1 = u < se_arm
    else:
        keep1 = u < se
    y_obs = np.where(
        y_true == 1,
        keep1.astype(int),                 # true positive kept w.p. Se
        (u < (1 - sp)).astype(int),        # false positive w.p. 1-Sp
    )
    df = pd.DataFrame({"x": x, "z": z, "y": y_obs})
    return df, float(true_rd), se, sp


def _binary_M(se, sp):
    """Column-stochastic 2x2 with states order [0, 1]:
    M[i][j] = P(Y=i | Y*=j)."""
    return [[sp, 1 - se], [1 - sp, se]]


# --- D1: recovery of the latent-true RD ---------------------------------------


def test_corrected_recovers_latent_true_rd_while_naive_attenuates():
    df, true_rd, se, sp = _make_data(effect=0.20)
    M = _binary_M(se, sp)
    det = se + sp - 1

    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=M, states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    assert isinstance(est, MeasurementCorrectionEstimate)
    # Corrected estimate recovers the latent-true RD (sees only observed y).
    assert est.point == pytest.approx(true_rd, abs=0.02)
    # Naive standardisation is attenuated by det(M) = Se+Sp-1.
    assert est.naive_point == pytest.approx(true_rd * det, abs=0.02)
    # det recorded correctly.
    assert est.det == pytest.approx(det, abs=1e-9)


def test_binary_matrix_inversion_equals_scalar_rogan_gladen():
    """Cross-check: the full M^-1 route (pick target component, standardise)
    equals the algebraically independent scalar route naive/det."""
    df, _true_rd, se, sp = _make_data(effect=0.15, seed=11)
    det = se + sp - 1
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    assert est.point == pytest.approx(est.naive_point / det, abs=1e-9)


def test_no_adjustment_marginal_correction():
    """With no confounder the correction is the marginal Rogan-Gladen RD."""
    df, true_rd, se, sp = _make_data(effect=0.20, seed=3)
    # Drop z from adjustment; the marginal RD is confounded but the correction
    # relation naive/det must still hold exactly.
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=(),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    det = se + sp - 1
    assert est.point == pytest.approx(est.naive_point / det, abs=1e-9)


def test_bootstrap_ci_brackets_point():
    df, _true_rd, se, sp = _make_data(effect=0.20, seed=5, n=8000)
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=200, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    # Corrected CI is wider than the (attenuated) point scale — de-attenuation
    # inflates variance by 1/det.
    assert (est.ci_upper - est.ci_lower) > 0


# --- sufficient statistics --------------------------------------------------


def test_sufficient_statistics_shape():
    df, _true_rd, se, sp = _make_data(effect=0.20, seed=9, n=6000)
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    ss = est.sufficient_statistics
    assert ss["confusion_matrix"] == [[sp, 1 - se], [1 - sp, se]]
    assert ss["states"] == [0, 1]
    assert ss["target_value"] == 1
    assert ss["target_index"] == 1
    assert ss["adjustment_vars"] == ["z"]
    # One (arm, z) stratum record per arm × z-level (2 arms × 2 levels = 4).
    assert len(ss["strata"]) == 4
    for rec in ss["strata"]:
        assert set(rec) == {"arm", "z", "counts", "n"}
        assert sum(rec["counts"]) == rec["n"]
    # Marginal counts sum to the total.
    assert sum(m["count"] for m in ss["marginal_counts"]) == ss["marginal_total"]


# --- guards -----------------------------------------------------------------


def test_singular_matrix_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    # Se + Sp = 1 → det = 0 → non-invertible (coin-flip measurement).
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.5, 0.5], [0.5, 0.5]], states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "singular_confusion_matrix"


def test_non_stochastic_matrix_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.1], [0.2, 0.8]],  # col 0 sums to 1.1
            states=[0, 1], target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "invalid_confusion_matrix"


def test_wrong_shape_matrix_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.05, 0.05], [0.1, 0.9, 0.0],
                              [0.0, 0.05, 0.95]],  # 3x3 but binary outcome
            states=[0, 1], target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "invalid_confusion_matrix"


def test_differential_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            differential=True, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "differential_misclassification"


def test_target_value_absent_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=2,
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "target_value_absent"


def test_states_incomplete_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    # Observed y has {0,1} but declared states are {0,2} — value 1 uncovered.
    # Matrix is invertible so the states-coverage check is what fires.
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.1], [0.1, 0.9]], states=[0, 2],
            target_value=0, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "states_incomplete"


def test_non_binary_treatment_refuses():
    df, _t, se, sp = _make_data(seed=2, n=2000)
    df = df.copy()
    df.loc[df.index[:100], "x"] = 2
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "treatment_not_binary"


def test_positivity_violation_refuses():
    # Build a frame (>= min sample size) where stratum z=1, x=0 is empty.
    df = pd.DataFrame({
        "x": [1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1],
        "z": [1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],   # z=1 only ever has x=1
        "y": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    })
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(0.9, 0.85), states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "insufficient_support"


# --- end-to-end dispatch + kernel.verify ------------------------------------

import copy

import themis


def _program(*, bidirected=False):
    """X→Y + Z→X + Z→Y backdoor program; noisy outcome Y. Optionally add a
    latent confounder X<->Y so no back-door set exists."""
    statements = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False],
         "measurement": "self-reported via questionnaire"},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause",
         "from": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
         "to": {"predicate": "y", "args": [{"type": "const", "name": "p"}]}},
        {"kind": "cause",
         "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
         "to": {"predicate": "x", "args": [{"type": "const", "name": "p"}]}},
        {"kind": "cause",
         "from": {"predicate": "z", "args": [{"type": "const", "name": "p"}]},
         "to": {"predicate": "y", "args": [{"type": "const", "name": "p"}]}},
    ]
    if bidirected:
        statements.append({
            "kind": "bidirected",
            "left": {"predicate": "x", "args": [{"type": "const", "name": "p"}]},
            "right": {"predicate": "y", "args": [{"type": "const", "name": "p"}]},
        })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "target": {"atom": {"predicate": "y",
                                "args": [{"type": "const", "name": "p"}]},
                       "value": True},
            "intervention": {"atom": {"predicate": "x",
                                      "args": [{"type": "const", "name": "p"}]},
                             "value": True},
            "given": [],
        },
    })
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "p"}]},
            "statements": statements}


def _bool_frame(**kw):
    df, true_rd, se, sp = _make_data(**kw)
    df = df.astype(bool)
    return df, true_rd, se, sp


def _spec(se, sp):
    return {"y": {"confusion_matrix": _binary_M(se, sp), "states": [False, True]}}


def test_dispatch_e2e_corrects_and_flips_status():
    df, true_rd, se, sp = _bool_frame(effect=0.20)
    out = themis.estimate(_program(), df, ci_bootstrap=0,
                          misclassification=_spec(se, sp))
    r = out["results"][0]
    ne = r["numeric_estimate"]
    assert r["status"] == "numerically_solved"
    assert ne["method"] == "measurement_error_correction"
    assert ne["point"] == pytest.approx(true_rd, abs=0.02)
    assert ne["measurement_correction"]["naive_point"] == pytest.approx(
        true_rd * (se + sp - 1), abs=0.02
    )


def test_verify_accepts_honest_e2e():
    df, _t, se, sp = _bool_frame(effect=0.20, seed=4)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_spec(se, sp))
    themis.verify(prog, out["results"][0])  # must not raise


def _estimate_result(seed=4, effect=0.20):
    df, _t, se, sp = _bool_frame(effect=effect, seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_spec(se, sp))
    return prog, out["results"][0]


def test_verify_rejects_forged_point():
    prog, r = _estimate_result()
    r["numeric_estimate"]["point"] = 0.05
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_forged_naive():
    prog, r = _estimate_result()
    r["numeric_estimate"]["measurement_correction"]["naive_point"] = 0.999
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_forged_matrix():
    prog, r = _estimate_result()
    # Forge a better Se/Sp while keeping the point — det + point mismatch.
    r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrix"] = [[0.99, 0.01], [0.01, 0.99]]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_dropped_stratum():
    prog, r = _estimate_result()
    ss = r["numeric_estimate"]["measurement_correction"]["sufficient_statistics"]
    ss["marginal_counts"] = ss["marginal_counts"][:1]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_tampered_stratum_count():
    prog, r = _estimate_result()
    ss = r["numeric_estimate"]["measurement_correction"]["sufficient_statistics"]
    # Break a stratum's counts so they no longer sum to n.
    ss["strata"][0]["counts"][0] += 5
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_no_misclassification_kwarg_leaves_naive_path():
    """Without the kwarg the query is the ordinary (attenuated) back-door
    estimate + the measurement_error_concern gap — unchanged behaviour."""
    df, _t, se, sp = _bool_frame(effect=0.20, seed=6)
    out = themis.estimate(_program(), df, ci_bootstrap=0)
    r = out["results"][0]
    ne = r.get("numeric_estimate") or {}
    assert ne.get("method") != "measurement_error_correction"
    kinds = [g["kind"] for g in (r.get("data_gap_report") or {}).get("gaps", [])]
    assert "measurement_error_concern" in kinds


def test_dispatch_singular_matrix_surfaces_estimator_failure():
    df, _t, se, sp = _bool_frame(effect=0.20, seed=8)
    spec = {"y": {"confusion_matrix": [[0.5, 0.5], [0.5, 0.5]], "states": [False, True]}}
    out = themis.estimate(_program(), df, ci_bootstrap=0, misclassification=spec)
    r = out["results"][0]
    assert "numeric_estimate" not in r or r["numeric_estimate"].get("method") != \
        "measurement_error_correction"
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "singular_confusion_matrix"


def test_dispatch_non_backdoor_identified_refuses():
    """A latent confounder X<->Y leaves no back-door set; the correction
    composes with back-door standardisation only, so it refuses."""
    df, _t, se, sp = _bool_frame(effect=0.20, seed=10)
    out = themis.estimate(_program(bidirected=True), df, ci_bootstrap=0,
                          misclassification=_spec(se, sp))
    r = out["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "requires_backdoor_identification"
