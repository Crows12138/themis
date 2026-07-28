"""Combined misclassification — both channels corrected at once.

The exposure and the outcome are each measured with error and each has its own
validated confusion matrix. Correcting one channel and shipping the point leaves
the other channel's bias in the number, which is why the two single-channel
estimators used to refuse to run together. Composing them inverts the same
per-stratum (X, Y) joint on BOTH sides, ``P_true = M_x⁻¹ P_obs (M_y⁻¹)ᵀ``, under
one premise neither single-channel correction makes: the two error mechanisms are
independent given the truth, ``X ⊥ Y | (X*, Y*, Z)``.

D1 oracle discipline: a synthetic SCM simulates the latent true exposure X* and
the latent true outcome Y*, so the back-door RD on the latent pair is known. The
observed columns pass through two independent Se/Sp channels. Seeing only the
observed columns, the two-sided correction recovers the latent-true RD while the
naive number AND each single-channel correction land materially away from it —
the last pair is the point of the estimator, not a bonus.
"""
import json

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.measurement import (
    CombinedMeasurementCorrectionEstimate,
    estimate_combined_measurement_correction,
    estimate_exposure_measurement_correction,
    estimate_measurement_correction,
)
from themis.estimation.dose_response import EstimatorFailure


def _M(se, sp):
    """Column-stochastic 2x2 in states order [0, 1]: M[i][j] = P(obs=i | true=j)."""
    return [[sp, 1 - se], [1 - sp, se]]


_SE_X, _SP_X = 0.90, 0.85
_SE_Y, _SP_Y = 0.80, 0.95


def _make_data(*, n=400_000, seed=11):
    """z (confounder) → X* → Y*, with z → Y* too. The observed x and y each pass
    through their own Se/Sp channel, driven by INDEPENDENT uniforms so the
    combined estimator's premise holds. Returns (df, latent-true back-door RD)."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, size=n)
    xstar = (rng.random(n) < (0.30 + 0.30 * z)).astype(int)
    ystar = (rng.random(n) < (0.20 + 0.30 * xstar + 0.20 * z)).astype(int)

    true_rd = 0.0
    for zv in (0, 1):
        m = z == zv
        true_rd += (
            ystar[m & (xstar == 1)].mean() - ystar[m & (xstar == 0)].mean()
        ) * m.mean()

    ux, uy = rng.random(n), rng.random(n)
    x = np.where(xstar == 1, (ux < _SE_X).astype(int), (ux < 1 - _SP_X).astype(int))
    y = np.where(ystar == 1, (uy < _SE_Y).astype(int), (uy < 1 - _SP_Y).astype(int))
    return pd.DataFrame({"x": x, "y": y, "z": z}), float(true_rd)


def _estimate(df, **kw):
    return estimate_combined_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=_M(_SE_X, _SP_X), exposure_states=[0, 1],
        outcome_confusion_matrix=_M(_SE_Y, _SP_Y), outcome_states=[0, 1],
        target_value=1, ci_bootstrap=0, **kw,
    )


# --- D1 -----------------------------------------------------------------------


def test_both_sided_inversion_recovers_truth_while_each_single_channel_does_not():
    """The whole reason the combined estimator exists: correcting either channel
    alone leaves the other's bias in the number."""
    df, true_rd = _make_data()
    est = _estimate(df)
    assert isinstance(est, CombinedMeasurementCorrectionEstimate)
    assert est.point == pytest.approx(true_rd, abs=0.02)

    # Neither single-channel correction gets there, and neither does the naive.
    assert abs(est.naive_point - true_rd) > 0.05

    only_outcome = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_M(_SE_Y, _SP_Y), states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    only_exposure = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_M(_SE_X, _SP_X), states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    assert abs(only_outcome.point - true_rd) > 0.03
    assert abs(only_exposure.point - true_rd) > 0.03


def test_an_identity_channel_reduces_to_the_single_channel_correction():
    """A channel measured without error is the identity matrix, and the combined
    correction must then agree with the single-channel one — the composition is
    the two inversions, not a third estimator."""
    df, _ = _make_data(n=60_000)
    identity = [[1.0, 0.0], [0.0, 1.0]]

    both = estimate_combined_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=identity, exposure_states=[0, 1],
        outcome_confusion_matrix=_M(_SE_Y, _SP_Y), outcome_states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    outcome_only = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_M(_SE_Y, _SP_Y), states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    assert both.point == pytest.approx(outcome_only.point, abs=1e-9)

    both_x = estimate_combined_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=_M(_SE_X, _SP_X), exposure_states=[0, 1],
        outcome_confusion_matrix=identity, outcome_states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    exposure_only = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=_M(_SE_X, _SP_X), states=[0, 1],
        target_value=1, ci_bootstrap=0,
    )
    assert both_x.point == pytest.approx(exposure_only.point, abs=1e-9)


def test_the_composed_determinant_factorises():
    df, _ = _make_data(n=20_000)
    est = _estimate(df)
    assert est.det_exposure == pytest.approx(_SE_X + _SP_X - 1)
    assert est.det_outcome == pytest.approx(_SE_Y + _SP_Y - 1)
    # k = 2 outcome states.
    assert est.det_joint == pytest.approx(est.det_exposure ** 2 * est.det_outcome ** 2)


def test_the_extra_premise_is_named_on_its_own():
    """The two-sided product needs the error channels to be independent given the
    truth, which neither single-channel correction assumes. A reader auditing the
    assumption list has to be able to see it without inferring it."""
    df, _ = _make_data(n=20_000)
    est = _estimate(df)
    assert (
        "independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z"
        in est.assumptions
    )
    assert "X⊥Y|(X*,Y*,Z)" in est.model_assumption


def test_the_bootstrap_holds_both_matrices_fixed():
    df, true_rd = _make_data(n=40_000)
    est = estimate_combined_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=_M(_SE_X, _SP_X), exposure_states=[0, 1],
        outcome_confusion_matrix=_M(_SE_Y, _SP_Y), outcome_states=[0, 1],
        target_value=1, ci_bootstrap=60, random_state=3,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper
    assert est.ci_lower <= true_rd <= est.ci_upper


# --- guards -------------------------------------------------------------------


def test_a_singular_channel_refuses_and_names_which_one():
    df, _ = _make_data(n=5_000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_combined_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            exposure_confusion_matrix=[[0.5, 0.5], [0.5, 0.5]],
            exposure_states=[0, 1],
            outcome_confusion_matrix=_M(_SE_Y, _SP_Y), outcome_states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert exc.value.failure_type == "singular_confusion_matrix"
    assert "EXPOSURE" in str(exc.value)

    with pytest.raises(EstimatorFailure) as exc2:
        estimate_combined_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            exposure_confusion_matrix=_M(_SE_X, _SP_X), exposure_states=[0, 1],
            outcome_confusion_matrix=[[0.5, 0.5], [0.5, 0.5]],
            outcome_states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert exc2.value.failure_type == "singular_confusion_matrix"
    assert "OUTCOME" in str(exc2.value)


def test_a_malformed_matrix_says_which_channel_it_is():
    """With two matrices in play a rejection that just says 'confusion matrix'
    leaves the caller to guess which one to fix."""
    df, _ = _make_data(n=5_000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_combined_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            exposure_confusion_matrix=[[0.9, 0.2], [0.1, 0.9]],  # column sums != 1
            exposure_states=[0, 1],
            outcome_confusion_matrix=_M(_SE_Y, _SP_Y), outcome_states=[0, 1],
            target_value=1, ci_bootstrap=0,
        )
    assert "exposure confusion matrix" in str(exc.value)


def test_a_stratum_with_an_empty_arm_refuses():
    df, _ = _make_data(n=20_000)
    df = df.copy()
    df.loc[(df["z"] == 1), "x"] = 1        # stratum z=1 has no control arm
    with pytest.raises(EstimatorFailure) as exc:
        _estimate(df)
    assert exc.value.failure_type == "insufficient_support"


def test_an_uncovered_outcome_value_refuses():
    df, _ = _make_data(n=20_000)
    df = df.copy()
    df.loc[df.index[:2000], "y"] = 2       # a third outcome level with no column
    with pytest.raises(EstimatorFailure) as exc:
        _estimate(df)
    assert exc.value.failure_type == "states_incomplete"


# --- e2e dispatch + verify ----------------------------------------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "measurement": "self-reported exposure"},
            {"kind": "variable", "predicate": "y",
             "measurement": "chart-abstracted outcome"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _e2e_spec():
    return {
        "x": {"confusion_matrix": _M(_SE_X, _SP_X), "states": [False, True]},
        "y": {"confusion_matrix": _M(_SE_Y, _SP_Y), "states": [False, True]},
    }


def _e2e_result(n=80_000, seed=11):
    df, true_rd = _make_data(n=n, seed=seed)
    prog = _program()
    out = themis.estimate(prog, df, ci_bootstrap=0, misclassification=_e2e_spec())
    return prog, out["results"][0], true_rd


def test_dispatch_e2e_corrects_both_channels_instead_of_refusing():
    prog, r, true_rd = _e2e_result()
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "combined_measurement_error_correction"
    mc = ne["measurement_correction"]
    assert mc["side"] == "combined"
    assert mc["differential"] is False
    assert "confusion_matrix" not in mc      # neither matrix is "the" matrix
    assert mc["confusion_matrix_exposure"] and mc["confusion_matrix_outcome"]
    assert ne["point"] == pytest.approx(true_rd, abs=0.03)


def test_a_differential_channel_is_refused_not_approximated():
    """The two-sided factorisation holds only for channel-constant matrices; a
    differential matrix is selected by the level the other channel mismeasures."""
    df, _ = _make_data(n=20_000)
    spec = _e2e_spec()
    spec["y"] = {
        "differential": True,
        "confusion_matrices": [_M(0.9, 0.9), _M(0.7, 0.7)],
        "differential_levels": [0, 1],
        "states": [False, True],
    }
    out = themis.estimate(_program(), df, ci_bootstrap=0, misclassification=spec)
    r = out["results"][0]
    assert r["status"] != "numerically_solved"
    failure = r["estimator_failure"]
    assert failure["failure_type"] == "differential_combined_misclassification_deferred"
    assert failure["estimator"] == "combined_measurement_error_correction"


def test_verify_accepts_honest_e2e():
    prog, r, _ = _e2e_result(n=60_000)
    themis.verify(prog, r)  # must not raise


def _tampered(mutate, n=60_000):
    prog, r, _ = _e2e_result(n=n)
    r = json.loads(json.dumps(r))
    mutate(r)
    return prog, r


@pytest.mark.parametrize("mutate,label", [
    (lambda r: r["numeric_estimate"].__setitem__("point", 0.02), "point"),
    (lambda r: r["numeric_estimate"]["measurement_correction"].__setitem__(
        "naive_point", 0.31), "naive_point"),
    (lambda r: r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"].__setitem__(
        "exposure_confusion_matrix", [[0.99, 0.01], [0.01, 0.99]]), "M_x"),
    (lambda r: r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"].__setitem__(
        "outcome_confusion_matrix", [[0.99, 0.01], [0.01, 0.99]]), "M_y"),
    (lambda r: r["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["strata"].pop(), "dropped stratum"),
])
def test_verify_rejects_tampering(mutate, label):
    prog, r = _tampered(mutate)
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_a_joint_determinant_from_another_pair_of_matrices():
    """The check that exists only on this path: det_joint must factorise as
    det(M_x)^k · det(M_y)^2. Both matrices and the point stay honest here, so
    every other check passes."""
    def mutate(r):
        mc = r["numeric_estimate"]["measurement_correction"]
        mc["det_joint"] = 0.9
        mc["sufficient_statistics"]["det_joint"] = 0.9
    prog, r = _tampered(mutate)
    with pytest.raises(Exception) as exc:
        themis.verify(prog, r)
    assert "det_joint" in str(exc.value)


def test_verify_rejects_a_claim_of_differential_misclassification():
    """A combined block that claims differential misclassification is claiming a
    factorisation the estimator never licensed."""
    def mutate(r):
        r["numeric_estimate"]["measurement_correction"]["differential"] = True
    prog, r = _tampered(mutate)
    with pytest.raises(Exception):
        themis.verify(prog, r)
