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
from themis.refusals import EstimatorFailure


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


def test_differential_without_matrices_refuses():
    """differential=True but only a single confusion_matrix (no per-arm set) is
    an incomplete spec — refuse rather than silently apply one matrix to both
    arms."""
    df, _t, se, sp = _make_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            differential=True, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "differential_spec_incomplete"


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


# ============================================================================
# Exposure (treatment) misclassification — the matrix method.
# ============================================================================
#
# The channel now sits on the EXPOSURE. A latent true X* -> Y SCM with a
# confounder Z; X* is misclassified into the observed X non-differentially. The
# corrected estimate (which sees only the observed X) must recover the latent-
# true RD on X*, while the naive back-door RD on the observed X is attenuated.

from themis.estimation.measurement import (
    estimate_exposure_measurement_correction,
    ExposureMeasurementCorrectionEstimate,
)
from themis.verifier import verify_exposure_measurement_correction_numeric


def _make_exposure_data(
    *, n=80000, effect=0.20, seed=7, se=0.90, sp=0.85, differential=False,
):
    """Z->X*, Z->Y, X*->Y; observed X = X* through an Se/Sp channel.

    Returns (df_with_observed_X, empirical_true_RD, se, sp). ``se`` = P(X=1|X*=1),
    ``sp`` = P(X=0|X*=0). With ``differential`` the sensitivity depends on the
    outcome (for the differential-refusal data)."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, size=n)
    pxs = 0.30 + 0.40 * z
    xstar = (rng.random(n) < pxs).astype(int)
    py = 0.25 + effect * xstar + 0.20 * z
    y = (rng.random(n) < py).astype(int)

    true_rd = 0.0
    for zv in (0, 1):
        m = z == zv
        pz = m.mean()
        true_rd += (y[m & (xstar == 1)].mean() - y[m & (xstar == 0)].mean()) * pz

    u = rng.random(n)
    if differential:
        se_arm = np.where(y == 1, se, se - 0.15)   # depends on Y -> differential
        keep1 = u < se_arm
    else:
        keep1 = u < se
    x = np.where(xstar == 1, keep1.astype(int), (u < (1 - sp)).astype(int))
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    return df, float(true_rd), se, sp


# --- D1: recovery of the latent-true RD (exposure side) ----------------------


def test_exposure_corrected_recovers_latent_true_rd_while_naive_attenuates():
    df, true_rd, se, sp = _make_exposure_data(effect=0.20)
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    assert isinstance(est, ExposureMeasurementCorrectionEstimate)
    # Corrected estimate recovers the latent-true RD (sees only observed x).
    assert est.point == pytest.approx(true_rd, abs=0.02)
    # Naive back-door RD on the observed exposure is attenuated toward the null.
    assert abs(est.naive_point) < abs(est.point) - 0.01
    assert est.det == pytest.approx(se + sp - 1, abs=1e-9)
    assert est.method == "exposure_measurement_error_correction"


def test_exposure_has_no_naive_over_det_shortcut():
    """Unlike the OUTCOME case, exposure attenuation is not point = naive/det;
    the correction is a genuine matrix inversion of the (X, Y) joint."""
    df, _true_rd, se, sp = _make_exposure_data(effect=0.20, seed=3)
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=0,
    )
    det = se + sp - 1
    # The outcome-side shortcut naive/det would give a different number here.
    assert abs(est.point - est.naive_point / det) > 0.005


def test_exposure_sufficient_statistics_shape():
    df, _true_rd, se, sp = _make_exposure_data(effect=0.20, seed=9, n=6000)
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[False, True], target_value=True,
        ci_bootstrap=0,
    )
    ss = est.sufficient_statistics
    assert ss["side"] == "exposure"
    assert ss["states"] == [False, True]
    assert list(ss["outcome_states"]) == list(est.outcome_states)
    assert ss["target_value"] is True
    assert ss["adjustment_vars"] == ["z"]
    # One record per z-level (2 levels), each a full 2xk joint table.
    assert len(ss["strata"]) == 2
    k = len(est.outcome_states)
    for rec in ss["strata"]:
        assert set(rec) == {"z", "joint_counts"}
        jc = rec["joint_counts"]
        assert len(jc) == 2 and all(len(row) == k for row in jc)
    assert sum(m["count"] for m in ss["marginal_counts"]) == ss["marginal_total"]


def test_exposure_bootstrap_ci_brackets_point():
    df, _true_rd, se, sp = _make_exposure_data(effect=0.20, seed=5, n=8000)
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
        ci_bootstrap=200, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


# --- guards (exposure side) --------------------------------------------------


def test_exposure_singular_matrix_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.5, 0.5], [0.5, 0.5]], states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "singular_confusion_matrix"


def test_exposure_non_stochastic_matrix_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.1], [0.2, 0.8]],  # col 0 sums to 1.1
            states=[0, 1], target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "invalid_confusion_matrix"


def test_exposure_differential_without_matrices_refuses():
    """differential=True but only a single confusion_matrix (no per-outcome set)
    is an incomplete spec — refuse."""
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            differential=True, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "differential_spec_incomplete"


def test_exposure_multi_level_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    df = df.copy()
    df.loc[df.index[:100], "x"] = 2   # a third exposure level
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "exposure_not_binary"


def test_exposure_non_binary_states_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.05, 0.05], [0.05, 0.9, 0.05],
                              [0.05, 0.05, 0.9]],
            states=[0, 1, 2], target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "exposure_not_binary"


def test_exposure_continuous_outcome_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    df = df.copy()
    rng = np.random.default_rng(0)
    df["y"] = rng.random(len(df))   # continuous outcome
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=1,
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "continuous_outcome"


def test_exposure_target_value_absent_refuses():
    df, _t, se, sp = _make_exposure_data(seed=2, n=2000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(se, sp), states=[0, 1], target_value=9,
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "target_value_absent"


def test_exposure_positivity_violation_refuses():
    # z=1 only ever has x=1 (observed) — the naive contrast is undefined there.
    df = pd.DataFrame({
        "x": [1, 1, 0, 0, 1, 1, 0, 0, 1, 1, 1, 1],
        "z": [1, 1, 0, 0, 0, 0, 0, 0, 1, 1, 1, 1],
        "y": [1, 0, 1, 0, 1, 0, 1, 0, 1, 0, 1, 0],
    })
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(0.9, 0.85), states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "insufficient_support"


def test_exposure_degenerate_recovered_marginal_refuses():
    """A weakly-informative matrix + a stratum skewed toward observed X=0 makes
    the recovered P(X*=1|z) non-positive — the conditional risk is undefined."""
    # sp=0.6 weak: recovered P(X*=1) = (sp*P(X=1) - (1-sp)*P(X=0)) / det < 0 when
    # observed X is mostly 0. 30 ones / 70 zeros, single z-stratum.
    x = [1] * 30 + [0] * 70
    df = pd.DataFrame({
        "x": x,
        "z": [0] * 100,
        "y": ([1, 0] * 15) + ([1, 0] * 35),
    })
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=_binary_M(0.9, 0.6), states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "degenerate_recovered_exposure"


# --- end-to-end dispatch + kernel.verify (exposure side) ---------------------


def _exposure_spec(se, sp):
    return {"x": {"confusion_matrix": _binary_M(se, sp), "states": [False, True]}}


def _bool_exposure_frame(**kw):
    df, true_rd, se, sp = _make_exposure_data(**kw)
    return df.astype(bool), true_rd, se, sp


def test_exposure_dispatch_e2e_corrects_and_flips_status():
    df, true_rd, se, sp = _bool_exposure_frame(effect=0.20)
    out = themis.estimate(_program(), df, ci_bootstrap=0,
                          misclassification=_exposure_spec(se, sp))
    r = out["results"][0]
    ne = r["numeric_estimate"]
    assert r["status"] == "numerically_solved"
    assert ne["method"] == "exposure_measurement_error_correction"
    assert ne["measurement_correction"]["side"] == "exposure"
    assert ne["point"] == pytest.approx(true_rd, abs=0.02)
    assert abs(ne["measurement_correction"]["naive_point"]) < abs(ne["point"]) - 0.01


def _exposure_estimate_result(seed=4, effect=0.20):
    df, _t, se, sp = _bool_exposure_frame(effect=effect, seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0,
                          misclassification=_exposure_spec(se, sp))
    return prog, out["results"][0]


def test_exposure_verify_accepts_honest_e2e():
    prog, r = _exposure_estimate_result()
    themis.verify(prog, r)  # must not raise


def test_exposure_verify_rejects_forged_point():
    prog, r = _exposure_estimate_result()
    r["numeric_estimate"]["point"] = 0.05
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verify_rejects_forged_naive():
    prog, r = _exposure_estimate_result()
    r["numeric_estimate"]["measurement_correction"]["naive_point"] = 0.999
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verify_rejects_forged_matrix():
    prog, r = _exposure_estimate_result()
    r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrix"] = [[0.99, 0.01], [0.01, 0.99]]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verify_rejects_tampered_joint_count():
    prog, r = _exposure_estimate_result()
    ss = r["numeric_estimate"]["measurement_correction"]["sufficient_statistics"]
    ss["strata"][0]["joint_counts"][1][1] += 500   # change the recovered point
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verify_rejects_dropped_stratum():
    prog, r = _exposure_estimate_result()
    ss = r["numeric_estimate"]["measurement_correction"]["sufficient_statistics"]
    ss["marginal_counts"] = ss["marginal_counts"][:1]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verify_rejects_wrong_side_tag():
    prog, r = _exposure_estimate_result()
    r["numeric_estimate"]["measurement_correction"]["side"] = "outcome"
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_exposure_verifier_noop_on_other_methods():
    # A no-op on anything that isn't an exposure correction.
    verify_exposure_measurement_correction_numeric(
        {"method": "backdoor_linear", "point": 0.3})
    verify_exposure_measurement_correction_numeric(
        {"method": "measurement_error_correction", "point": 0.2})


def test_exposure_dispatch_singular_matrix_surfaces_estimator_failure():
    df, _t, se, sp = _bool_exposure_frame(effect=0.20, seed=8)
    spec = {"x": {"confusion_matrix": [[0.5, 0.5], [0.5, 0.5]],
                  "states": [False, True]}}
    out = themis.estimate(_program(), df, ci_bootstrap=0, misclassification=spec)
    r = out["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "singular_confusion_matrix"


def test_exposure_dispatch_non_backdoor_identified_refuses():
    df, _t, se, sp = _bool_exposure_frame(effect=0.20, seed=10)
    out = themis.estimate(_program(bidirected=True), df, ci_bootstrap=0,
                          misclassification=_exposure_spec(se, sp))
    r = out["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["failure_type"] == "requires_backdoor_identification"


def test_combined_exposure_and_outcome_spec_routes_to_the_combined_correction():
    """A confusion matrix for BOTH X and Y routes to the combined correction,
    which inverts the joint on both sides. What must never happen — correcting
    one channel and shipping a point that still carries the other's bias — is
    what this used to be a refusal about; the routing is the guard now, and the
    two-sided estimator is exercised in test_combined_misclassification.py."""
    df, _t, se, sp = _bool_exposure_frame(effect=0.20, seed=6)
    spec = {
        "x": {"confusion_matrix": _binary_M(se, sp), "states": [False, True]},
        "y": {"confusion_matrix": _binary_M(se, sp), "states": [False, True]},
    }
    out = themis.estimate(_program(), df, ci_bootstrap=0, misclassification=spec)
    r = out["results"][0]
    assert r.get("estimator_failure") is None
    ne = r["numeric_estimate"]
    assert ne["method"] == "combined_measurement_error_correction"
    assert ne["measurement_correction"]["side"] == "combined"


def test_outcome_side_still_works_alongside_exposure():
    """Backward compat: a y-keyed spec still routes to the OUTCOME correction."""
    df, true_rd, se, sp = _bool_frame(effect=0.20, seed=4)
    out = themis.estimate(_program(), df, ci_bootstrap=0,
                          misclassification=_spec(se, sp))
    r = out["results"][0]
    assert r["numeric_estimate"]["method"] == "measurement_error_correction"
    assert r["numeric_estimate"]["measurement_correction"].get("side") in (None, "outcome")


# ============================================================================
# Differential misclassification — per-level matrix inversion.
# ============================================================================
#
# OUTCOME side (detection bias): the outcome channel depends on the exposure arm
# — a distinct M_x per arm. EXPOSURE side (recall bias): the exposure channel
# depends on the outcome — a distinct M_y per outcome level. Differential
# misclassification can bias AWAY from the null, so a single (pooled) matrix
# gives a WRONG corrected number; only the per-level inversion recovers truth.

import math

# arm/outcome-specific (Se, Sp) used by the generators below.
_D_OUT = ((0.70, 0.95), (0.90, 0.85))   # (arm0, arm1) for outcome detection bias
_D_EXP = ((0.75, 0.95), (0.95, 0.80))   # (Y=0, Y=1) for exposure recall bias


def _diff_outcome_data(*, n=60000, effect=0.20, seed=7):
    """Outcome misclassification DIFFERENTIAL by exposure arm (detection bias).
    Returns (bool df carrying observed y, empirical latent-true RD)."""
    (se0, sp0), (se1, sp1) = _D_OUT
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.30 + 0.40 * z).astype(int)
    yt = (rng.random(n) < 0.25 + effect * x + 0.20 * z).astype(int)
    true_rd = sum((yt[(z == v) & (x == 1)].mean() - yt[(z == v) & (x == 0)].mean())
                  * (z == v).mean() for v in (0, 1))
    se_a = np.where(x == 1, se1, se0)
    sp_a = np.where(x == 1, sp1, sp0)
    u = rng.random(n)
    yo = np.where(yt == 1, (u < se_a).astype(int), (u < 1 - sp_a).astype(int))
    return pd.DataFrame({"x": x, "z": z, "y": yo}).astype(bool), float(true_rd)


def _diff_exposure_data(*, n=60000, effect=0.20, seed=11):
    """Exposure misclassification DIFFERENTIAL by outcome (recall bias).
    Returns (bool df carrying observed x, empirical latent-true RD)."""
    (se0, sp0), (se1, sp1) = _D_EXP
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    xs = (rng.random(n) < 0.30 + 0.40 * z).astype(int)
    y = (rng.random(n) < 0.25 + effect * xs + 0.20 * z).astype(int)
    true_rd = sum((y[(z == v) & (xs == 1)].mean() - y[(z == v) & (xs == 0)].mean())
                  * (z == v).mean() for v in (0, 1))
    se_y = np.where(y == 1, se1, se0)
    sp_y = np.where(y == 1, sp1, sp0)
    u = rng.random(n)
    xo = np.where(xs == 1, (u < se_y).astype(int), (u < 1 - sp_y).astype(int))
    return pd.DataFrame({"x": xo, "z": z, "y": y}).astype(bool), float(true_rd)


def _out_matrices():
    return [_binary_M(*_D_OUT[0]), _binary_M(*_D_OUT[1])]


def _exp_matrices():
    return [_binary_M(*_D_EXP[0]), _binary_M(*_D_EXP[1])]


def _diff_outcome_spec():
    return {"y": {"differential": True, "confusion_matrices": _out_matrices(),
                  "differential_levels": [False, True], "states": [False, True]}}


def _diff_exposure_spec():
    return {"x": {"differential": True, "confusion_matrices": _exp_matrices(),
                  "differential_levels": [False, True], "states": [False, True]}}


# --- D1: recovery (outcome / detection bias) ---------------------------------


def test_diff_outcome_recovers_true_rd():
    df, true_rd = _diff_outcome_data()
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, differential=True,
        confusion_matrices=_out_matrices(), differential_levels=[0, 1],
        ci_bootstrap=0,
    )
    assert est.differential is True
    assert math.isnan(est.det)                       # no single det under differential
    assert est.confusion_matrix == ()                # no single matrix
    assert est.point == pytest.approx(true_rd, abs=0.02)
    # Differential misclassification biases AWAY from the null here.
    assert abs(est.naive_point - true_rd) > 0.05
    ss = est.sufficient_statistics
    assert ss["differential"] is True
    arms = {r["arm"] for r in ss["confusion_matrices_by_arm"]}
    assert arms == {0, 1}
    assert "confusion_matrix" not in ss


def test_diff_outcome_single_matrix_correction_is_wrong():
    """The gap this closes: a single (arm-1) matrix applied to genuinely
    differential data gives a materially wrong corrected point; the per-arm
    inversion recovers truth."""
    df, true_rd = _diff_outcome_data(seed=3)
    (se1, sp1) = _D_OUT[1]
    wrong = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_binary_M(se1, sp1), states=[False, True],
        target_value=True, ci_bootstrap=0,
    )
    right = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, differential=True,
        confusion_matrices=_out_matrices(), differential_levels=[0, 1],
        ci_bootstrap=0,
    )
    assert abs(wrong.point - true_rd) > 0.03
    assert abs(right.point - true_rd) < 0.02


def test_diff_outcome_e2e_and_verify_accepts():
    df, true_rd = _diff_outcome_data(seed=5)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_diff_outcome_spec())
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["point"] == pytest.approx(true_rd, abs=0.02)
    mc = ne["measurement_correction"]
    assert mc["differential"] is True
    assert "confusion_matrix" not in mc and "det" not in mc
    assert {e["arm"] for e in mc["confusion_matrices"]} == {0, 1}
    themis.verify(prog, r)   # must not raise


def _diff_outcome_result(seed=5):
    df, _t = _diff_outcome_data(seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_diff_outcome_spec())
    return prog, out["results"][0]


def test_diff_outcome_verify_rejects_forged_point():
    prog, r = _diff_outcome_result()
    r["numeric_estimate"]["point"] = 0.05
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_diff_outcome_verify_rejects_tampered_arm_matrix():
    prog, r = _diff_outcome_result()
    recs = r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrices_by_arm"]
    recs[0]["matrix"] = [[0.99, 0.01], [0.01, 0.99]]   # det now disagrees
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_diff_outcome_verify_rejects_flipped_differential_flag():
    prog, r = _diff_outcome_result()
    r["numeric_estimate"]["measurement_correction"]["differential"] = False
    with pytest.raises(Exception):
        themis.verify(prog, r)


# --- guards (outcome differential) -------------------------------------------


def test_diff_outcome_levels_not_covering_both_arms_refuses():
    df, _t = _diff_outcome_data(seed=2, n=4000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, differential=True,
            confusion_matrices=_out_matrices(), differential_levels=[1, 2],
            ci_bootstrap=0,   # both truthy -> only arm 1
        )
    assert ei.value.failure_type == "differential_levels_mismatch"


def test_diff_outcome_misaligned_lengths_refuse():
    df, _t = _diff_outcome_data(seed=2, n=4000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, differential=True,
            confusion_matrices=_out_matrices(), differential_levels=[0, 1, 2],
            ci_bootstrap=0,
        )
    assert ei.value.failure_type == "differential_levels_mismatch"


def test_diff_outcome_singular_arm_matrix_refuses():
    df, _t = _diff_outcome_data(seed=2, n=4000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, differential=True,
            confusion_matrices=[_binary_M(0.70, 0.95), [[0.5, 0.5], [0.5, 0.5]]],
            differential_levels=[0, 1], ci_bootstrap=0,
        )
    assert ei.value.failure_type == "singular_confusion_matrix"


# --- D1 + e2e (exposure / recall bias) ---------------------------------------


def test_diff_exposure_recovers_true_rd():
    df, true_rd = _diff_exposure_data()
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, differential=True,
        confusion_matrices=_exp_matrices(), differential_levels=[0, 1],
        ci_bootstrap=0,
    )
    assert est.differential is True
    assert math.isnan(est.det)
    assert est.point == pytest.approx(true_rd, abs=0.02)
    assert abs(est.naive_point - true_rd) > 0.05
    ss = est.sufficient_statistics
    assert ss["side"] == "exposure" and ss["differential"] is True
    assert "confusion_matrix" not in ss
    assert len(ss["confusion_matrices_by_outcome"]) == 2


def test_diff_exposure_e2e_and_verify_accepts():
    df, true_rd = _diff_exposure_data(seed=13)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_diff_exposure_spec())
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["point"] == pytest.approx(true_rd, abs=0.02)
    mc = ne["measurement_correction"]
    assert mc["side"] == "exposure" and mc["differential"] is True
    assert "confusion_matrix" not in mc
    themis.verify(prog, r)


def _diff_exposure_result(seed=13):
    df, _t = _diff_exposure_data(seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_diff_exposure_spec())
    return prog, out["results"][0]


def test_diff_exposure_verify_rejects_forged_point():
    prog, r = _diff_exposure_result()
    r["numeric_estimate"]["point"] = 0.02
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_diff_exposure_verify_rejects_tampered_outcome_matrix():
    prog, r = _diff_exposure_result()
    recs = r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrices_by_outcome"]
    recs[0]["matrix"] = [[0.99, 0.01], [0.01, 0.99]]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_diff_exposure_levels_not_covering_outcomes_refuses():
    df, _t = _diff_exposure_data(seed=2, n=6000)
    with pytest.raises(EstimatorFailure) as ei:
        estimate_exposure_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, differential=True,
            confusion_matrices=_exp_matrices(), differential_levels=[0, 5],
            ci_bootstrap=0,   # 5 is not an observed outcome
        )
    assert ei.value.failure_type == "differential_levels_mismatch"
