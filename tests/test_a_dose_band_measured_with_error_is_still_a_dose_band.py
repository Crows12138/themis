"""A misclassified exposure with more than two levels.

The outcome side of the confusion-matrix correction took a k×k channel from
the start; the exposure side took 2×2 and refused everything else. Nothing in
the matrix method is binary — a stratum's joint is inverted column by column at
whatever width the channel has — so what actually held the exposure side to two
levels was the SHAPE OF ITS ANSWER: it returned ``r1 - r0``, and with k levels
there is no single difference to return.

So the primitive here is the standardised risk AT EACH LEVEL, and the contrast
is read off it against the caller's first declared state. A binary exposure
still reports one point, by the same arithmetic in the same order.

D1 oracle: a synthetic SCM with a LATENT three-level exposure X*, passed through
a known 3×3 channel. The corrected estimate sees only the misclassified column
and must recover the latent-true standardised risk at every level; the naive
estimate must stay visibly wrong. The truths are closed-form from the SCM's own
parameters, not read back from the estimator.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import answers
from themis.estimation.measurement import (
    estimate_combined_measurement_correction,
    estimate_exposure_measurement_correction,
)
from themis.refusals import EstimatorFailure

# --------------------------------------------------------------------------
# The SCM.  M[i][j] = P(X = i | X* = j) — columns are the TRUE state.
# --------------------------------------------------------------------------
MX = [
    [0.80, 0.15, 0.05],
    [0.15, 0.70, 0.20],
    [0.05, 0.15, 0.75],
]
#: P(Y=1 | X*=a, Z=z)
PY = {(0, 0): 0.20, (1, 0): 0.35, (2, 0): 0.55,
      (0, 1): 0.40, (1, 1): 0.55, (2, 1): 0.75}
PZ = 0.45
#: P(X*=a | Z=z)
PXS = {0: (0.55, 0.30, 0.15), 1: (0.25, 0.35, 0.40)}
LEVELS = (0, 1, 2)


def _truth() -> dict[int, float]:
    """Σ_z P(z) · P(Y=1 | X*=a, z), straight from the parameters above."""
    return {a: (1 - PZ) * PY[(a, 0)] + PZ * PY[(a, 1)] for a in LEVELS}


def _frame(n: int = 60000, seed: int = 11) -> tuple[pd.DataFrame, np.ndarray]:
    rng = np.random.default_rng(seed)
    z = (rng.random(n) < PZ).astype(int)
    xs = np.empty(n, dtype=int)
    for zv in (0, 1):
        mask = z == zv
        xs[mask] = rng.choice(3, size=int(mask.sum()), p=PXS[zv])
    y = rng.random(n) < np.array([PY[(int(a), int(zv))]
                                  for a, zv in zip(xs, z)])
    x = np.empty(n, dtype=int)
    mx = np.asarray(MX)
    for a in LEVELS:
        mask = xs == a
        x[mask] = rng.choice(3, size=int(mask.sum()), p=mx[:, a])
    frame = pd.DataFrame({"z": z.astype(bool), "x": x, "y": y})
    return frame, xs


def _binary_frame(n: int = 40000, seed: int = 3):
    """Two arms, one channel — the shape that must not move."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.45
    xs = rng.random(n) < np.where(z, 0.6, 0.3)
    y = rng.random(n) < (np.where(xs, 0.6, 0.3) + np.where(z, 0.1, 0.0))
    se, sp = 0.85, 0.90
    x = np.where(xs, rng.random(n) < se, rng.random(n) > sp)
    return pd.DataFrame({"z": z, "x": x, "y": y}), [[sp, 1 - se], [1 - sp, se]]


def _atom(name: str) -> dict:
    return {"predicate": name, "args": [{"type": "const", "name": "p"}]}


def _program(*, domain, intervention) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": list(domain),
             "measurement": "self-reported daily dose band"},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": _atom("y"), "value": True},
                       "intervention": {"atom": _atom("x"),
                                        "value": intervention},
                       "given": []}},
        ],
    }


def _spec(matrix, states) -> dict:
    return {"x": {"confusion_matrix": [[float(v) for v in row]
                                       for row in matrix],
                  "states": list(states)}}


@pytest.fixture(scope="module")
def solved():
    """One end-to-end k=3 run, reused by the readers of its envelope."""
    frame, _xs = _frame()
    program = _program(domain=LEVELS, intervention=2)
    out = themis.estimate(program, frame, ci_bootstrap=0,
                          misclassification=_spec(MX, LEVELS))
    return program, out["results"][0]


# ==========================================================================
# D1: against the latent truth
# ==========================================================================

def test_the_correction_recovers_the_latent_risk_at_every_level():
    frame, _xs = _frame()
    truth = _truth()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=list(LEVELS),
        target_value=True, ci_bootstrap=0,
    )
    for a in LEVELS:
        assert est.risks[a] == pytest.approx(truth[a], abs=0.01)


def test_the_naive_estimate_stays_wrong_where_the_corrected_one_does_not():
    """Otherwise the test above would pass on data with no misclassification
    in it, and would be measuring nothing."""
    frame, _xs = _frame()
    truth = _truth()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=list(LEVELS),
        target_value=True, ci_bootstrap=0,
    )
    top = est.dose_response_curve[-1]
    true_contrast = truth[2] - truth[0]
    assert top["point"] == pytest.approx(true_contrast, abs=0.02)
    # The channel pulls the extreme levels toward each other, so the naive
    # contrast is attenuated by roughly a third — far outside the corrected
    # estimate's tolerance.
    assert top["naive_point"] < true_contrast - 0.08


def test_the_curve_carries_every_level_but_the_reference():
    frame, _xs = _frame()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=list(LEVELS),
        target_value=True, ci_bootstrap=0,
    )
    assert [row["level"] for row in est.dose_response_curve] == [1, 2]
    for row in est.dose_response_curve:
        assert row["point"] == pytest.approx(
            est.risks[row["level"]] - est.risks[0]
        )


def test_each_level_gets_its_own_interval():
    frame, _xs = _frame(n=20000, seed=5)
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=list(LEVELS),
        target_value=True, ci_bootstrap=120, random_state=4,
    )
    seen = set()
    for row in est.dose_response_curve:
        assert row["ci_lower"] is not None and row["ci_upper"] is not None
        assert row["ci_lower"] <= row["point"] <= row["ci_upper"]
        seen.add((row["ci_lower"], row["ci_upper"]))
    # Two levels, two different intervals — one interval reused for the whole
    # curve would mean the resampling never varied with the level.
    assert len(seen) == 2


# ==========================================================================
# The binary case must not move
# ==========================================================================

def test_a_binary_exposure_answers_exactly_as_it_did():
    frame, matrix = _binary_frame()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=matrix, states=[False, True],
        target_value=True, ci_bootstrap=0,
    )
    # The value this estimator returned before the widening, to the last bit.
    assert est.point == 0.3065665768996223
    assert est.point == est.risks[1] - est.risks[0]
    assert est.naive_point == est.naive_risks[1] - est.naive_risks[0]


def test_a_binary_exposure_has_no_curve():
    """One row restating ``point`` would be a second place for the same
    number to be read, and so a second place for it to disagree."""
    frame, matrix = _binary_frame()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=matrix, states=[False, True],
        target_value=True, ci_bootstrap=0,
    )
    assert est.dose_response_curve == ()


def test_more_than_two_levels_answers_with_the_curve_and_no_point():
    """The two declared shapes are ALTERNATIVES — every surface renders the
    first that detects, so a point beside a curve would leave the curve
    carrying no answer at all. With k−1 contrasts and none of them "the"
    effect, the curve is the answer and the point is absent."""
    frame, _xs = _frame()
    est = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=list(LEVELS),
        target_value=True, ci_bootstrap=0,
    )
    assert est.point is None
    assert est.naive_point is None
    assert len(est.dose_response_curve) == 2


# ==========================================================================
# What the caller declares, and what happens when it does not
# ==========================================================================

def test_the_first_declared_state_is_the_reference():
    """Re-declaring the states in another order moves the reference, and the
    contrast follows it — the ordering IS the declaration."""
    frame, _xs = _frame()
    forward = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=MX, states=[0, 1, 2],
        target_value=True, ci_bootstrap=0,
    )
    mx = np.asarray(MX)
    order = [2, 1, 0]
    reordered = mx[np.ix_(order, order)].tolist()
    backward = estimate_exposure_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=reordered, states=[2, 1, 0],
        target_value=True, ci_bootstrap=0,
    )
    # Same two levels, opposite reference, so the contrast flips sign. Level 2
    # is the last row going forward and level 0 is the last row coming back.
    assert backward.dose_response_curve[-1]["point"] == pytest.approx(
        -forward.dose_response_curve[-1]["point"], abs=1e-9
    )
    # The middle level is in both curves and is the same risk either way —
    # only what it is subtracted from changed.
    assert backward.risks[1] == pytest.approx(forward.risks[1], abs=1e-9)


def test_one_declared_state_refuses():
    frame, _xs = _frame()
    with pytest.raises(EstimatorFailure) as caught:
        estimate_exposure_measurement_correction(
            frame, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[1.0]], states=[0],
            target_value=True, ci_bootstrap=0,
        )
    assert caught.value.failure_type == "too_few_inputs"


def test_a_repeated_state_refuses():
    frame, _xs = _frame()
    with pytest.raises(EstimatorFailure) as caught:
        estimate_exposure_measurement_correction(
            frame, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=MX, states=[0, 1, 1],
            target_value=True, ci_bootstrap=0,
        )
    assert caught.value.failure_type == "duplicate_input"


def test_a_matrix_narrower_than_the_declared_states_refuses():
    frame, _xs = _frame()
    with pytest.raises(EstimatorFailure) as caught:
        estimate_exposure_measurement_correction(
            frame, treatment="x", outcome="y", adjustment=("z",),
            confusion_matrix=[[0.9, 0.1], [0.1, 0.9]], states=list(LEVELS),
            target_value=True, ci_bootstrap=0,
        )
    assert caught.value.failure_type == "matrix_wrong_shape"
    assert caught.value.details["expected"] == "3×3"


# ==========================================================================
# Both channels at once
# ==========================================================================

def test_the_combined_correction_also_takes_a_wide_exposure():
    frame, _xs = _frame()
    rng = np.random.default_rng(21)
    se_y, sp_y = 0.88, 0.92
    true_y = frame["y"].to_numpy()
    frame = frame.copy()
    frame["y"] = np.where(true_y,
                          rng.random(len(frame)) < se_y,
                          rng.random(len(frame)) > sp_y)
    truth = _truth()
    est = estimate_combined_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=MX, exposure_states=list(LEVELS),
        outcome_confusion_matrix=[[sp_y, 1 - se_y], [1 - sp_y, se_y]],
        outcome_states=[False, True],
        target_value=True, ci_bootstrap=0,
    )
    for a in LEVELS:
        assert est.risks[a] == pytest.approx(truth[a], abs=0.015)
    assert est.dose_response_curve[-1]["naive_point"] < (
        truth[2] - truth[0]) - 0.08


def test_the_joint_determinant_takes_each_channels_width_from_the_other():
    """det(A ⊗ B) = det(A)^k · det(B)^kx. The second exponent used to be a
    literal 2, which is right only while the exposure is binary — and wrong
    silently, since it is a plausible number either way."""
    frame, _xs = _frame()
    rng = np.random.default_rng(21)
    se_y, sp_y = 0.88, 0.92
    frame = frame.copy()
    frame["y"] = np.where(frame["y"].to_numpy(),
                          rng.random(len(frame)) < se_y,
                          rng.random(len(frame)) > sp_y)
    my = [[sp_y, 1 - se_y], [1 - sp_y, se_y]]
    est = estimate_combined_measurement_correction(
        frame, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=MX, exposure_states=list(LEVELS),
        outcome_confusion_matrix=my, outcome_states=[False, True],
        target_value=True, ci_bootstrap=0,
    )
    det_x = float(np.linalg.det(np.asarray(MX)))
    det_y = float(np.linalg.det(np.asarray(my)))
    assert est.det_joint == pytest.approx(det_x ** 2 * det_y ** 3)


# ==========================================================================
# End to end, and the shape of the answer
# ==========================================================================

def test_the_run_solves_and_answers_with_the_curve(solved):
    _program_, result = solved
    assert result["status"] == "numerically_solved"
    estimate = result["numeric_estimate"]
    assert estimate["method"] == "exposure_measurement_error_correction"
    assert [row["x"] for row in estimate["dose_response_curve"]] == [1, 2]
    assert estimate["reference_point"] == 0
    assert estimate["dose_response_curve"][-1]["effect"] == pytest.approx(
        _truth()[2] - _truth()[0], abs=0.02
    )


def test_the_method_declares_the_shape_it_produced(solved):
    _program_, result = solved
    estimate = result["numeric_estimate"]
    declared = answers.SHAPES_OF[estimate["method"]]
    assert answers.DOSE_RESPONSE_CURVE in declared
    assert answers.DOSE_RESPONSE_CURVE.detect(estimate)
    # And the curve is what the surfaces will render, rather than being
    # shadowed by a point declared ahead of it.
    assert answers.shape_of(estimate) is answers.DOSE_RESPONSE_CURVE


def test_a_binary_run_declares_the_same_pair_and_produces_only_a_point():
    """The declaration is about what the METHOD can produce; which shape came
    out is this run's own fact."""
    frame, matrix = _binary_frame()
    program = _program(domain=[True, False], intervention=True)
    out = themis.estimate(program, frame, ci_bootstrap=0,
                          misclassification=_spec(matrix, [False, True]))
    estimate = out["results"][0]["numeric_estimate"]
    assert answers.POINT.detect(estimate)
    assert not answers.DOSE_RESPONSE_CURVE.detect(estimate)


def test_the_reader_gets_the_curve_in_both_languages(solved):
    _program_, result = solved
    from themis.output.analysis_report import build_analysis_report

    for lang in ("zh", "en"):
        report = build_analysis_report(result, lang=lang)
        assert isinstance(report, str) and report.strip()
        assert "this build has no word" not in report
        # Every non-reference level reaches the page — a curve summarised
        # down to one of its rows would be the shape problem all over again.
        for row in result["numeric_estimate"]["dose_response_curve"]:
            assert _fmt_in(report, row["effect"])


def _fmt_in(report: str, value: float) -> bool:
    return f"{round(value, 4)}" in report or f"{value:.4f}" in report


def test_the_reader_is_told_what_the_correction_moved(solved):
    """The size of the move is why this section exists: without it a reader
    cannot tell a correction that changed everything from one that changed
    nothing. A polytomous exposure has no single move, so it is said per
    level — the line that used to carry it reads ``naive → corrected`` and
    goes silent when there is no single point."""
    _program_, result = solved
    from themis.output.analysis_report import build_analysis_report

    block = result["numeric_estimate"]["measurement_correction"]
    naive_top = block["naive_risks"][-1] - block["naive_risks"][0]
    for lang in ("zh", "en"):
        report = build_analysis_report(result, lang=lang)
        assert _fmt_in(report, naive_top), lang


# ==========================================================================
# The verifier
# ==========================================================================

def test_the_verifier_accepts_the_honest_run(solved):
    program, result = solved
    themis.verify(program, result)


@pytest.mark.parametrize("label,tamper", [
    ("a point where no single contrast is the effect",
     lambda e: e.__setitem__("point", 0.9)),
    ("a curve effect",
     lambda e: e["dose_response_curve"][0].__setitem__("effect", 0.9)),
    ("a dropped level", lambda e: e["dose_response_curve"].pop()),
    ("a curve row moved onto the reference",
     lambda e: e["dose_response_curve"][0].__setitem__("x", 0)),
    ("a per-level risk",
     lambda e: e["measurement_correction"]["risks"].__setitem__(1, 0.9)),
    ("the reference level",
     lambda e: e["measurement_correction"]["sufficient_statistics"]
     .__setitem__("reference_value", 2)),
    ("a joint count",
     lambda e: e["measurement_correction"]["sufficient_statistics"]["strata"]
     [0]["joint_counts"][1].__setitem__(0, 999999)),
    ("the displayed confusion matrix",
     lambda e: e["measurement_correction"]["confusion_matrix"][0]
     .__setitem__(0, 0.5)),
    ("the reference the curve names",
     lambda e: e.__setitem__("reference_point", 1)),
])
def test_the_verifier_rejects(solved, label, tamper):
    program, result = solved
    forged = copy.deepcopy(result)
    tamper(forged["numeric_estimate"])
    with pytest.raises(Exception):
        themis.verify(program, forged)


def test_the_displayed_matrix_must_be_the_one_that_was_inverted(solved):
    """The only copy the verifier re-inverts is the one in the sufficient
    statistics, so without this check the block's matrix is decorative: an
    envelope could show a reader one channel while the number came from
    another, and every numeric check would still pass."""
    program, result = solved
    forged = copy.deepcopy(result)
    block = forged["numeric_estimate"]["measurement_correction"]
    # Column-stochastic and invertible — so nothing but the comparison with
    # the inverted copy can catch it.
    block["confusion_matrix"] = [[0.7, 0.2, 0.1],
                                 [0.2, 0.6, 0.2],
                                 [0.1, 0.2, 0.7]]
    with pytest.raises(Exception):
        themis.verify(program, forged)
