"""#484 — a confusion matrix that varies by the arm AND by a covariate.

Two differential shapes were built, on the two days they were each needed:
a matrix per exposure arm (detection bias) and a matrix per covariate
stratum (accuracy that differs by site). Between them sat a refusal —
``differential_by_unknown`` — for the case that names both, which is the
ordinary one: detection bias that also differs by site.

Nothing about identification was missing. The correction inverts within
each (arm, z) cell either way, and every such cell already had a matrix of
its own; what was missing was a way to SAY which cell a matrix belongs to.
So the axis became a list of columns, the two built cases became its
one-column instances, and the refusal that stood between them had nothing
left to refuse.

The premise this rests on is the WEAKEST of the three, which is why it is
one ledger row and not two: "the rate varies by arm and by stratum"
assumes less than either single-column claim, each of which additionally
says the rate does NOT vary in the other coordinate.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.measurement import (
    estimate_exposure_measurement_correction,
    estimate_measurement_correction,
)
from themis.refusals import EstimatorFailure

#: (sensitivity, specificity) per (home, z) cell — all four different, so a
#: correction that collapsed the axis to either coordinate alone would use
#: the wrong matrix in half the cells.
CELLS = {
    (0, 0): (0.95, 0.92),
    (1, 0): (0.72, 0.98),
    (0, 1): (0.88, 0.80),
    (1, 1): (0.60, 0.90),
}
LEVELS = [[False, False], [True, False], [False, True], [True, True]]


def _M(se: float, sp: float) -> list[list[float]]:
    return [[sp, 1 - se], [1 - sp, se]]


def _matrices() -> list[list[list[float]]]:
    return [_M(*CELLS[(int(a), int(b))]) for a, b in LEVELS]


def _outcome_frame(n=120000, effect=0.20, seed=5):
    """Detection bias that also varies by site: the outcome's error rate is
    read off the (arm, z) cell the row is in."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = (rng.random(n) < 0.30 + 0.40 * z).astype(int)
    yt = (rng.random(n) < 0.25 + effect * x + 0.20 * z).astype(int)
    true_rd = sum(
        (yt[(z == v) & (x == 1)].mean() - yt[(z == v) & (x == 0)].mean())
        * (z == v).mean() for v in (0, 1))
    se = np.array([CELLS[(int(a), int(b))][0] for a, b in zip(x, z)])
    sp = np.array([CELLS[(int(a), int(b))][1] for a, b in zip(x, z)])
    u = rng.random(n)
    yo = np.where(yt == 1, (u < se).astype(int), (u < 1 - sp).astype(int))
    return pd.DataFrame({"x": x, "z": z, "y": yo}).astype(bool), float(true_rd)


def _exposure_frame(n=120000, effect=0.20, seed=8):
    """Recall bias that also varies by site — the mirror on the other
    channel, where the axis is (outcome, covariate)."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    xs = (rng.random(n) < 0.30 + 0.40 * z).astype(int)
    y = (rng.random(n) < 0.25 + effect * xs + 0.20 * z).astype(int)
    true_rd = sum(
        (y[(z == v) & (xs == 1)].mean() - y[(z == v) & (xs == 0)].mean())
        * (z == v).mean() for v in (0, 1))
    se = np.array([CELLS[(int(a), int(b))][0] for a, b in zip(y, z)])
    sp = np.array([CELLS[(int(a), int(b))][1] for a, b in zip(y, z)])
    u = rng.random(n)
    xo = np.where(xs == 1, (u < se).astype(int), (u < 1 - sp).astype(int))
    return pd.DataFrame({"x": xo, "z": z, "y": y}).astype(bool), float(true_rd)


# --- recovery, on both channels -----------------------------------------------


def test_the_outcome_channel_recovers_the_truth_from_four_cells():
    df, truth = _outcome_frame()
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True, differential_by=["x", "z"],
        confusion_matrices=_matrices(), differential_levels=LEVELS,
    )
    assert est.point == pytest.approx(truth, abs=0.02)
    assert est.differential_by == ["x", "z"]


def test_the_naive_number_here_has_the_wrong_sign():
    """What makes this correction worth doing rather than a refinement.

    Non-differential misclassification attenuates toward the null, so a
    naive number is at least the right side of zero. These rates differ by
    arm, and the naive contrast comes back NEGATIVE against a true effect
    of about +0.2 — a reader given the uncorrected number would not read a
    smaller effect, they would read the opposite one.
    """
    df, truth = _outcome_frame()
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True, differential_by=["x", "z"],
        confusion_matrices=_matrices(), differential_levels=LEVELS,
    )
    assert truth > 0.15
    assert est.naive_point < 0
    assert est.point == pytest.approx(truth, abs=0.02)


def test_the_exposure_channel_mirrors_it():
    df, truth = _exposure_frame()
    est = estimate_exposure_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True, differential_by=["y", "z"],
        confusion_matrices=_matrices(), differential_levels=LEVELS,
    )
    assert est.point == pytest.approx(truth, abs=0.02)
    assert est.differential_by == ["y", "z"]


# --- what the ledger says it assumed ------------------------------------------


def test_the_joint_axis_is_one_premise_and_names_both_columns():
    df, _ = _outcome_frame(n=20000)
    est = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True, differential_by=["x", "z"],
        confusion_matrices=_matrices(), differential_levels=LEVELS,
    )
    mechanisms = [a for a in est.assumptions
                  if a.startswith("differential_misclassification")]
    assert mechanisms == ["differential_misclassification_by_cell_{x,z}"], (
        "a joint axis disclosed itself as the two single-axis claims, each "
        "of which says the rate does NOT vary in the other coordinate"
    )


def test_the_single_column_cases_still_say_what_they_always_said():
    """The fork must not move an answer that was already right."""
    df, _ = _outcome_frame(n=20000)
    per_arm = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True,
        confusion_matrices=[_M(*CELLS[(0, 0)]), _M(*CELLS[(1, 0)])],
        differential_levels=[False, True],
    )
    assert per_arm.differential_by is None
    assert "confusion_matrices_by_arm" in per_arm.sufficient_statistics
    assert per_arm.assumptions[0] == (
        "differential_misclassification_by_exposure_arm_M_depends_on_X")

    per_stratum = estimate_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        states=[False, True], target_value=True, ci_bootstrap=0,
        differential=True, differential_by="z",
        confusion_matrices=[_M(*CELLS[(0, 0)]), _M(*CELLS[(0, 1)])],
        differential_levels=[False, True],
    )
    assert per_stratum.differential_by == "z"
    assert per_stratum.assumptions[0] == (
        "differential_misclassification_by_covariate_z")
    assert [r["level"] for r in per_stratum.sufficient_statistics[
        "confusion_matrices_by_level"]] == [False, True], (
        "a one-column axis started spelling its levels as lists"
    )


# --- the guards ----------------------------------------------------------------


def test_a_level_that_does_not_give_one_value_per_column_refuses():
    df, _ = _outcome_frame(n=20000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, ci_bootstrap=0,
            differential=True, differential_by=["x", "z"],
            confusion_matrices=_matrices(),
            # Scalars against a two-column axis: each names one coordinate
            # and leaves the other unsaid, so no cell is identified.
            differential_levels=[False, True, False, True],
        )
    assert exc.value.failure_type == "differential_levels_mismatch"


def test_a_cell_the_data_holds_and_the_set_does_not_refuses():
    df, _ = _outcome_frame(n=20000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, ci_bootstrap=0,
            differential=True, differential_by=["x", "z"],
            confusion_matrices=_matrices()[:3],
            differential_levels=LEVELS[:3],
        )
    assert exc.value.failure_type == "differential_level_uncovered"
    assert exc.value.details["level"] == [True, True]


def test_the_column_being_corrected_cannot_select_its_own_matrix():
    """Refused by its own species, and before the unknown-column check.

    The outcome's matrix is already indexed by the true outcome state, so
    an axis on the outcome is indexed by the quantity being recovered.
    "Not a column that can carry this" would be false about it and would
    send a reader hunting for a typo in a name spelled correctly.
    """
    df, _ = _outcome_frame(n=20000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, ci_bootstrap=0,
            differential=True, differential_by=["y", "z"],
            confusion_matrices=_matrices(), differential_levels=LEVELS,
        )
    assert exc.value.failure_type == "differential_by_the_mismeasured_variable"


def test_a_column_in_neither_place_is_still_unknown():
    df, _ = _outcome_frame(n=20000)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            df, treatment="x", outcome="y", adjustment=("z",),
            states=[False, True], target_value=True, ci_bootstrap=0,
            differential=True, differential_by=["x", "not_a_var"],
            confusion_matrices=_matrices(), differential_levels=LEVELS,
        )
    assert exc.value.failure_type == "differential_by_unknown"
    assert exc.value.details["axis"] == "x × not_a_var"


# --- end to end, and the forgery the audit has to catch -------------------------


def _atom(p: str) -> dict:
    return {"predicate": p, "args": []}


_PROGRAM = {
    "version": "0.1",
    "domain": {"objects": []},
    "statements": [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": []}},
    ],
}


def _e2e():
    df, truth = _outcome_frame(n=60000)
    spec = {"y": {"differential": True, "differential_by": ["x", "z"],
                  "confusion_matrices": _matrices(),
                  "differential_levels": LEVELS, "states": [False, True]}}
    out = themis.estimate(_PROGRAM, df, ci_bootstrap=0, misclassification=spec)
    return out["results"][0], truth


def test_the_round_trip_stands():
    result, truth = _e2e()
    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "measurement_error_correction"
    assert est["point"] == pytest.approx(truth, abs=0.02)
    assert est["measurement_correction"]["differential_by"] == ["x", "z"]
    themis.verify(_PROGRAM, result)


def test_a_forged_point_is_refused():
    result, _ = _e2e()
    result["numeric_estimate"]["point"] = 0.05
    with pytest.raises(Exception, match="point mismatch"):
        themis.verify(_PROGRAM, result)


def test_relabelling_which_cell_a_matrix_belongs_to_is_refused():
    """The counterexample for the cell key itself.

    Swapping two records' MATRICES is caught by their own determinants, so
    it tests nothing about the key. Swapping their LEVELS leaves every
    record internally consistent — right matrix, right det, right tally —
    and moves only the claim about which cell each one governs. The audit
    then inverts (arm=0, z=0) with the matrix that belongs to (1, 1), and
    the only thing that can notice is a re-derivation that keys on the
    whole cell.
    """
    result, _ = _e2e()
    swapped = json.loads(json.dumps(result))
    recs = swapped["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrices_by_level"]
    recs[0]["level"], recs[3]["level"] = recs[3]["level"], recs[0]["level"]
    with pytest.raises(Exception, match="point mismatch"):
        themis.verify(_PROGRAM, swapped)


def test_a_record_shaped_for_the_wrong_axis_is_refused():
    """A two-column axis carrying a scalar level keys on something no cell
    can equal. Refused as the shape fault it is, rather than surfacing as
    "no matrix for this stratum" — a true sentence about the wrong fault."""
    result, _ = _e2e()
    broken = json.loads(json.dumps(result))
    recs = broken["numeric_estimate"]["measurement_correction"][
        "sufficient_statistics"]["confusion_matrices_by_level"]
    recs[0]["level"] = False
    with pytest.raises(Exception, match="one value per column"):
        themis.verify(_PROGRAM, broken)
