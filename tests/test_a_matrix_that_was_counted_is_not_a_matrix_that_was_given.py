"""A confusion matrix is a table of proportions, and somebody counted them.

Every misclassification correction here reads a matrix the caller declares
and inverts it per stratum. The interval around the answer was a bootstrap
of the ROWS with that matrix held perfectly still — which is the right
interval when the matrix is a coding rule fixed by protocol, and too narrow
by an unstated amount when it came out of a validation study of fifty
people. The premise the ledger carried said "from a validation study" in
both cases, so nothing on the page distinguished them.

What a validation study hands over is not an estimate with degrees of
freedom but a TALLY: so many subjects known to be at each true state, so
many of them recorded at each state. A column of counts over its total is a
Dirichlet, exactly as a variance over its study is a χ² — and this route,
unlike the three in #471, has a bootstrap already running, so the study is
carried by redrawing the matrix inside it.

Discipline: the point is unchanged by the declaration (it is the inversion
at the study's own matrix either way), the WIDTH is what moves, and every
claim below is either a property of the arithmetic or a forgery the
verifier has to reject.
"""
import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.measurement import (
    _any_measured,
    _declare_matrix,
    _inverses,
    estimate_combined_measurement_correction,
    estimate_exposure_measurement_correction,
    estimate_measurement_correction,
)
from themis.estimation.resample import JEFFREYS, DeclaredMatrix
from themis.output.analysis_report import build_analysis_report
from themis.assumption_glossary import is_classified
from themis import refusals
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.declaration_rules import (
    CONFUSION_MATRIX,
    VARIANCE,
    check_declaration_premises,
)
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_measurement_correction_numeric

SE, SP = 0.90, 0.85


def _M(se=SE, sp=SP):
    """Column-stochastic 2×2 in states order [False, True]."""
    return [[sp, 1 - se], [1 - sp, se]]


def _tally(n, se=SE, sp=SP):
    """The validation study that would have produced :func:`_M` — n subjects
    at each true state, counted at the rates the matrix states."""
    return [[sp * n, (1 - se) * n], [(1 - sp) * n, se * n]]


def _data(*, n=6000, seed=4):
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = rng.random(n) < (0.3 + 0.3 * z)
    ytrue = rng.random(n) < (0.2 + 0.3 * x + 0.2 * z)
    u = rng.random(n)
    y = np.where(ytrue, u < SE, u > SP)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _outcome(declaration, *, draws=300, data=None):
    return estimate_measurement_correction(
        data if data is not None else _data(),
        treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix=declaration, states=(False, True), target_value=True,
        ci_bootstrap=draws, random_state=1,
    )


def _width(est) -> float:
    return est.ci_upper - est.ci_lower


# ============================================ what the declaration changes


def test_the_point_stays_put_and_the_interval_opens_with_the_study():
    """The matrix a correction inverts is the study's own, whichever way it
    was declared, so the answer is the same number. What the study's size
    decides is how much else that number could have been.

    Measured against the fixed-matrix width rather than between the counted
    runs: once a study is declared the rng carries two streams instead of
    one, so two counted runs are not the same resample and the difference
    between neighbouring study sizes is inside Monte-Carlo noise. What is
    well outside it is the distance from "nobody may question this matrix"
    to "two hundred people were looked at" — measured 0.068 → 0.082 → 0.234
    at 20000, 200 and 20 subjects a state.
    """
    given = _outcome(_M(), draws=600)
    huge = _outcome({"validation_counts": _tally(20_000)}, draws=600)
    modest = _outcome({"validation_counts": _tally(200)}, draws=600)
    small = _outcome({"validation_counts": _tally(20)}, draws=600)

    for est in (huge, modest, small):
        assert given.point == pytest.approx(est.point, rel=1e-12)

    # A study of twenty thousand a state IS the matrix, and says so.
    assert abs(_width(huge) - _width(given)) < 0.1 * _width(given)
    assert _width(modest) > 1.1 * _width(given)
    assert _width(small) > 3 * _width(given)


def test_a_matrix_nobody_counted_leaves_the_draw_sequence_untouched():
    """The claim that makes every interval this package has already
    reported still reproducible from its record: an undeclared study
    consumes no randomness at all, so the row draws land where they did."""
    declared = _declare_matrix(_M(), 2, channel=refusals.QueryRole.OUTCOME)
    assert not declared.measured
    assert not _any_measured({0: declared})

    rng, twin = np.random.default_rng(9), np.random.default_rng(9)
    drawn = declared.draw(rng)
    assert np.allclose(np.asarray(drawn, dtype=float), _M())
    assert rng.random() == twin.random()


def test_one_declaration_under_two_keys_is_one_draw():
    """A non-differential channel is one matrix reached under every level's
    key. Drawing it per key would make the arms differ — a differential
    channel nobody declared, and an interval widened for a variation that
    is not there."""
    declared = _declare_matrix({"validation_counts": _tally(30)}, 2,
                               channel=refusals.QueryRole.OUTCOME)
    inverses = _inverses({("n", 0.0): declared, ("n", 1.0): declared},
                         np.random.default_rng(3),
                         channel=refusals.QueryRole.OUTCOME)
    assert inverses[("n", 0.0)] is inverses[("n", 1.0)]

    # Two separate declarations of the same matrix ARE two channels, and
    # get two draws — the identity is what carries the meaning, not the
    # numbers, because a differential set declares one object per level.
    twin = _declare_matrix({"validation_counts": _tally(30)}, 2,
                           channel=refusals.QueryRole.OUTCOME)
    apart = _inverses({0: declared, 1: twin}, np.random.default_rng(3),
                      channel=refusals.QueryRole.OUTCOME)
    assert not np.allclose(apart[0], apart[1])


def test_each_column_is_its_own_multinomial():
    """A study that enrolled two hundred subjects at one true state and ten
    at the other knows the two columns that differently, and one Dirichlet
    over the whole table could not say so."""
    lopsided = [[0.9 * 200, 0.1 * 10], [0.1 * 200, 0.9 * 10]]
    declared = DeclaredMatrix(matrix=np.asarray(_M(0.9, 0.9), dtype=float),
                              counts=np.asarray(lopsided, dtype=float))
    rng = np.random.default_rng(0)
    drawn = np.stack([declared.draw(rng) for _ in range(400)])
    well_counted = drawn[:, 0, 0].std()
    barely_counted = drawn[:, 1, 1].std()
    assert barely_counted > 3 * well_counted


def test_a_cell_the_study_never_saw_is_still_possible():
    """Fifty subjects with no misrecording among them have not shown that
    the misrecording cannot happen. The bare count as a Dirichlet parameter
    would draw that cell as exactly zero for ever, which is the one
    direction of overconfidence this declaration exists to remove."""
    perfect = [[50.0, 0.0], [0.0, 50.0]]
    declared = DeclaredMatrix(matrix=np.eye(2), counts=np.asarray(perfect))
    rng = np.random.default_rng(2)
    off_diagonal = [float(declared.draw(rng)[1, 0]) for _ in range(200)]
    assert min(off_diagonal) > 0.0
    # And it stays SMALL: possible is not the same as asserted.
    assert np.mean(off_diagonal) < 0.05
    assert JEFFREYS == 0.5


class _DrawsFlat:
    """An rng whose every Dirichlet is the flat column — so the matrix it
    hands back carries no information about the truth at all."""

    def dirichlet(self, alpha):
        return np.full(len(alpha), 1.0 / len(alpha))


def test_a_redrawn_channel_that_cannot_invert_leaves_by_the_named_door():
    """The backstop, and the counterexample it exists for. A redraw that
    lands on a singular channel raises what a declared singular matrix
    raises, so the loop that catches it files the draw under the species
    that names it rather than crashing the estimate."""
    declared = _declare_matrix({"validation_counts": _tally(30)}, 2,
                               channel=refusals.QueryRole.OUTCOME)
    with pytest.raises(EstimatorFailure) as exc:
        _inverses({0: declared}, _DrawsFlat(),
                  channel=refusals.QueryRole.OUTCOME)
    assert exc.value.failure_type == Refusal.SINGULAR_CONFUSION_MATRIX.value


def test_a_channel_a_small_study_does_not_establish_says_so_in_the_width():
    """The common case the backstop is NOT for. A weak channel counted in a
    handful of subjects redraws into inversions that are near-singular
    rather than singular, and the honest answer is an interval wide enough
    to say the data does not pin the effect — discarding those draws would
    narrow it by throwing away exactly the ones carrying the news."""
    weak = _outcome({"validation_counts": _tally(6, se=0.62, sp=0.60)},
                    draws=400)
    firm = _outcome(_M(0.62, 0.60), draws=400)
    assert weak.draws.lost == 0
    assert _width(weak) > 10 * _width(firm)


# ============================================ what the ledger says


@pytest.mark.parametrize("declaration,settled", [
    (_M(), "confusion_matrix_known_and_fixed_on_y"),
    ({"validation_counts": _tally(50)},
     "confusion_matrix_from_a_validation_study_on_y"),
])
def test_the_premise_says_which_of_the_two_ways_it_was_settled(declaration,
                                                               settled):
    est = _outcome(declaration, draws=0)
    assert settled in est.assumptions
    assert is_classified(settled)


def test_the_four_ids_that_restated_a_shape_and_named_a_study_are_gone():
    """Every one of them ended "from a validation study" over an interval
    that held the matrix perfectly still, and every one of them restated a
    shape the mechanism premise beside it already names."""
    retired = [
        "known_confusion_matrix_from_validation_study",
        "known_confusion_matrices_from_validation_studies",
        "known_per_arm_confusion_matrices_from_validation_study",
        "known_per_outcome_confusion_matrices_from_validation_study",
        "known_per_covariate_stratum_confusion_matrices_from_validation_study",
    ]
    est = _outcome(_M(), draws=0)
    for old in retired:
        assert old not in est.assumptions
        assert not is_classified(old), old


def test_each_channel_of_a_combined_correction_declares_its_own():
    """Two studies, two premises: a correction handed the exposure's matrix
    and given the outcome's counts rests on one of each, and a single id
    covering both could only be right when they agree."""
    df = _data()
    est = estimate_combined_measurement_correction(
        df, treatment="x", outcome="y", adjustment=("z",),
        exposure_confusion_matrix=_M(), exposure_states=(False, True),
        outcome_confusion_matrix={"validation_counts": _tally(80)},
        outcome_states=(False, True), target_value=True, ci_bootstrap=0,
    )
    assert "confusion_matrix_known_and_fixed_on_x" in est.assumptions
    assert "confusion_matrix_from_a_validation_study_on_y" in est.assumptions


def test_the_exposure_channel_carries_it_on_the_column_it_mismeasured():
    est = estimate_exposure_measurement_correction(
        _data(), treatment="x", outcome="y", adjustment=("z",),
        confusion_matrix={"validation_counts": _tally(60)},
        states=(False, True), target_value=True, ci_bootstrap=0,
    )
    assert "confusion_matrix_from_a_validation_study_on_x" in est.assumptions


def test_the_two_families_are_the_same_rule_on_a_different_stem():
    """The variance and the matrix ask one question — was this taken as
    exact, or did a study measure it — so the branch is written once and
    the families differ only in their nouns."""
    assert VARIANCE.stem != CONFUSION_MATRIX.stem
    for family in (VARIANCE, CONFUSION_MATRIX):
        check_declaration_premises(
            family, rule="r", declared=[family.stem + "known_and_fixed_on_w"],
            measured=["w"], carried={})
        with pytest.raises(VerificationError, match="prices the main sample"):
            check_declaration_premises(
                family, rule="r",
                declared=[family.stem + "from_a_validation_study_on_w"],
                measured=["w"], carried={})


# ============================================ what the gate says no to


@pytest.mark.parametrize("counts", [
    [[10, -1], [0, 11]],
    [[10, "a"], [0, 11]],
    [[10, 1], [0]],
    [],
    [[[1]]],
])
def test_a_tally_that_is_not_a_tally_is_refused(counts):
    with pytest.raises(EstimatorFailure) as exc:
        _outcome({"validation_counts": counts}, draws=0)
    assert exc.value.failure_type == Refusal.VALIDATION_COUNTS_UNUSABLE.value


def test_a_true_state_no_subject_stood_at_is_its_own_refusal():
    """Well formed, and one column empty. That column is not a proportion
    of anything, and normalising it first would hide the fault behind a
    complaint about a matrix the caller never wrote."""
    with pytest.raises(EstimatorFailure) as exc:
        _outcome({"validation_counts": [[40, 0], [10, 0]]}, draws=0)
    assert (exc.value.failure_type
            == Refusal.VALIDATION_STATE_NEVER_OBSERVED.value)


def test_a_differential_set_settled_two_ways_is_refused():
    """One channel is counted or exact. A set that counts some levels and
    fixes the rest produces an interval carrying part of a study — neither
    of the two things the premise can say, and the same two numbers on the
    page as both."""
    with pytest.raises(EstimatorFailure) as exc:
        estimate_measurement_correction(
            _data(), treatment="x", outcome="y", adjustment=("z",),
            states=(False, True), target_value=True, differential=True,
            confusion_matrices=[_M(0.9, 0.9),
                                {"validation_counts": _tally(40)}],
            differential_levels=[False, True], ci_bootstrap=0,
        )
    assert (exc.value.failure_type
            == Refusal.MATRIX_SET_DECLARED_TWO_WAYS.value)


# ============================================ what the record carries


def _program():
    """X→Y with Z→X, Z→Y; the outcome is the mismeasured column."""
    args = [{"type": "const", "name": "p"}]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False],
             "measurement": "self-reported via questionnaire"},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": {"predicate": "x", "args": args},
             "to": {"predicate": "y", "args": args}},
            {"kind": "cause", "from": {"predicate": "z", "args": args},
             "to": {"predicate": "x", "args": args}},
            {"kind": "cause", "from": {"predicate": "z", "args": args},
             "to": {"predicate": "y", "args": args}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": {"predicate": "y", "args": args},
                           "value": True},
                "intervention": {"atom": {"predicate": "x", "args": args},
                                 "value": True},
                "given": []}},
        ],
    }


def _result(declaration, *, draws=0):
    out = themis.estimate(
        _program(), _data(), ci_bootstrap=draws,
        misclassification={"y": {"confusion_matrix": declaration,
                                 "states": [False, True]}},
    )
    result = out["results"][0]
    assert "estimator_failure" not in result, result.get("estimator_failure")
    return result


def test_the_block_carries_the_tally_beside_the_matrix_it_normalises_to():
    counted = _result({"validation_counts": _tally(90)})
    mc = counted["numeric_estimate"]["measurement_correction"]
    tally = np.asarray(mc["validation_counts"], dtype=float)
    assert np.allclose(tally / tally.sum(axis=0),
                       np.asarray(mc["confusion_matrix"], dtype=float))

    given = _result(_M())
    block = given["numeric_estimate"]["measurement_correction"]
    assert "validation_counts" not in block


def test_the_audit_re_derives_the_matrix_from_the_tally():
    counted = _result({"validation_counts": _tally(90)})
    verify_measurement_correction_numeric(counted["numeric_estimate"])


FORGERIES = {
    "a tally that does not normalise to the matrix":
        lambda ne: ne["measurement_correction"]["sufficient_statistics"]
        .__setitem__("validation_counts", _tally(90, se=0.5, sp=0.5)),
    "a tally with a state nobody stood at":
        lambda ne: ne["measurement_correction"]["sufficient_statistics"]
        .__setitem__("validation_counts", [[90.0, 0.0], [10.0, 0.0]]),
    "a study denied after the fact":
        lambda ne: ne["measurement_correction"]["sufficient_statistics"]
        .pop("validation_counts"),
    "a premise saying the matrix was fixed":
        lambda ne: ne.__setitem__("assumptions", [
            "confusion_matrix_known_and_fixed_on_y"
            if a == "confusion_matrix_from_a_validation_study_on_y" else a
            for a in ne["assumptions"]]),
    "both premises at once":
        lambda ne: ne.__setitem__(
            "assumptions",
            list(ne["assumptions"]) + ["confusion_matrix_known_and_fixed_on_y"]),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_tampered_declaration_is_rejected(name):
    honest = _result({"validation_counts": _tally(90)})["numeric_estimate"]
    verify_measurement_correction_numeric(honest)
    forged = copy.deepcopy(honest)
    FORGERIES[name](forged)
    with pytest.raises(VerificationError):
        verify_measurement_correction_numeric(forged)


def test_a_premise_naming_a_study_over_a_matrix_nobody_counted_is_rejected():
    """The mirror of the loud case and the quieter one: an interval that
    held the matrix still, under a premise saying it could not have."""
    given = _result(_M())["numeric_estimate"]
    verify_measurement_correction_numeric(given)
    forged = copy.deepcopy(given)
    forged["assumptions"] = [
        "confusion_matrix_from_a_validation_study_on_y"
        if a == "confusion_matrix_known_and_fixed_on_y" else a
        for a in forged["assumptions"]
    ]
    with pytest.raises(VerificationError, match="prices the main sample"):
        verify_measurement_correction_numeric(forged)


# ============================================ the reader is told


def test_the_report_says_the_matrix_was_counted_and_how_far():
    counted = build_analysis_report(_result({"validation_counts": _tally(90)}))
    assert "每个真实状态站着 90 个人" in counted

    given = build_analysis_report(_result(_M()))
    assert "每个真实状态站着" not in given
    # The size, not the table: what a reader does with this is judge whether
    # the widening they can see is the study they were told about, and four
    # cells of a 2×2 answer that no better than their two totals.
    assert "76.5" not in counted
