"""A correction's arithmetic was audited and its framing was not.

Every measurement-error method re-derives its number from the block's own
sufficient statistics, and reads that block's labels as the INPUTS of the
re-derivation: which columns the design had, which values the variable
takes, which value the risk is of, where that value sits in the list. Read
as an input a label cannot be wrong. Change it and the arithmetic re-derives
a different number that agrees with itself in every place a reader or an
auditor could look — an answer to a question nobody asked.

Measured on the suite's own answers before anything here was written:
forty-eight leaves of these six blocks could be edited and still pass the
public door, and the ones that name rather than count could be edited
without moving a single number a reader is shown.

Two kinds of test, and the second is the point.

The first bends one leaf, which is what the sweep gate does, and asserts the
door now refuses. That is the arithmetic of the census: forty-one of the
forty-eight.

The second bends a leaf AND every copy of it — the block, its own record,
and the index that points into it, all moved together into a story that is
internally perfect. The census cannot ask that question, because it edits
one leaf at a time. It is the question this module exists for: a correction
whose account of itself is consistent with everything except the question.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.correction_frame_rules import verify_correction_frame
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The six shapes and the block each writes. Read from the fixture rather
#: than restated, so a method that renames its block fails here instead of
#: quietly testing nothing.
CORRECTIONS = {
    "combined_measurement_error_correction": "measurement_correction",
    "exposure_measurement_error_correction": "measurement_correction",
    "measurement_error_correction": "measurement_correction",
    "differential_outcome_correction": "differential_outcome_error",
    "differential_regression_calibration": "differential_error",
    "regression_calibration": "regression_calibration",
    "simex": "simex",
}


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _block(result: dict, method: str) -> dict:
    return result["numeric_estimate"][CORRECTIONS[method]]


def _door(program, result, match: str) -> None:
    """The door refuses, and this rule is one of the reasons.

    Both are asserted because they say different things. That the door
    refuses is what a caller gets. That THIS rule refuses, naming this
    forgery, is what the test is about — and for most of them a
    re-derivation reaches the same edit first and refuses for its own
    reason, which is the arrangement working rather than this rule being
    unnecessary: bend every copy at once and the re-derivation is satisfied
    while the frame is not.
    """
    with pytest.raises(VerificationError):
        themis.verify(program, result)
    with pytest.raises(VerificationError, match=match):
        verify_correction_frame(result, program,
                                query_id=result.get("query_id"))


@pytest.mark.parametrize("method", sorted(CORRECTIONS))
def test_the_answer_this_method_really_gives_is_accepted(method):
    """Honest first, per shape. A forgery refused by a rule that refuses
    everything proves nothing about the rule."""
    program, result = _pair(method)
    themis.verify(program, result)
    assert CORRECTIONS[method] in result["numeric_estimate"]


# ------------------------------------------- one leaf, the way the sweep asks


def test_a_correction_cannot_say_it_corrected_another_variable():
    program, result = _pair("regression_calibration")
    _block(result, "regression_calibration")["exposure"] = "z"
    _door(program, result, "corrected 'z'")


def test_the_audit_trail_cannot_stratify_on_a_different_set():
    program, result = _pair("regression_calibration")
    stats = _block(result, "regression_calibration")["sufficient_statistics"]
    stats["adjustment_vars"] = ["q"]
    _door(program, result, "different stratification")


def test_the_moments_cannot_be_over_a_sample_the_answer_did_not_use():
    program, result = _pair("differential_outcome_correction")
    stats = _block(result, "differential_outcome_correction")[
        "sufficient_statistics"]
    stats["n"] = stats["n"] + 7
    _door(program, result, "rows")


def test_an_index_cannot_point_past_the_list_it_indexes():
    program, result = _pair("exposure_measurement_error_correction")
    stats = _block(result, "exposure_measurement_error_correction")[
        "sufficient_statistics"]
    stats["target_index"] = 9
    _door(program, result, "not one")


def test_the_exposures_column_cannot_be_the_covariates():
    program, result = _pair("regression_calibration")
    stats = _block(result, "regression_calibration")["sufficient_statistics"]
    stats["exposure_index"] = 1
    _door(program, result, "points at")


def test_a_matrix_column_that_is_not_a_distribution_is_not_a_channel():
    program, result = _pair("measurement_error_correction")
    block = _block(result, "measurement_error_correction")
    block["confusion_matrices"][0]["matrix"][0][0] = 0.5
    _door(program, result, "column 0 sums to")


def test_the_determinant_beside_a_matrix_is_that_matrix_s():
    """The figure the invertibility premise is judged on, and the figure
    that says how far the inversion multiplies the noise. Bent alone, so the
    column check above cannot be what refuses it."""
    program, result = _pair("exposure_measurement_error_correction")
    block = _block(result, "exposure_measurement_error_correction")
    block["det"] = 0.9
    block["sufficient_statistics"]["det"] = 0.9
    _door(program, result, "determinant")


def test_two_rows_of_a_per_cell_table_cannot_be_the_same_cell():
    program, result = _pair("measurement_error_correction")
    block = _block(result, "measurement_error_correction")
    block["confusion_matrices"][1]["level"] = list(
        block["confusion_matrices"][0]["level"])
    _door(program, result, "already describes that cell")


def test_a_cell_cannot_be_a_value_the_variable_does_not_take():
    program, result = _pair("measurement_error_correction")
    block = _block(result, "measurement_error_correction")
    block["confusion_matrices"][0]["level"][0] = 7
    _door(program, result, "which the program says")


def test_the_seed_a_simulation_shows_is_the_seed_the_run_used():
    program, result = _pair("simex")
    result["numeric_estimate"]["simex"]["random_state"] = 7
    _door(program, result, "seeded")


def test_the_form_on_the_block_and_the_form_on_the_ledger_are_one_choice():
    program, result = _pair("simex")
    result["numeric_estimate"]["simex"]["form"] = "simex_linear_quadratic"
    _door(program, result, "mechanism audit")


def test_a_reader_and_an_auditor_are_shown_one_run():
    """The question that closes nineteen of the forty-eight, and knows what
    none of them mean."""
    program, result = _pair("regression_calibration")
    block = _block(result, "regression_calibration")
    assert block["reliability"] == block["sufficient_statistics"]["reliability"]
    block["reliability"] = 0.99
    _door(program, result, "re-derived from one of them")


# -------------------------------------- every copy at once, the way a forger would


def test_a_correction_over_states_the_variable_does_not_take_is_refused():
    """The block, its record and the index moved together.

    Nothing inside the answer disagrees with anything else: the arithmetic
    re-derives, the two copies match, the index points where it says. What
    it collides with is the program, which said which values that variable
    has.
    """
    program, result = _pair("exposure_measurement_error_correction")
    block = _block(result, "exposure_measurement_error_correction")
    for node in (block, block["sufficient_statistics"]):
        node["states"] = [0, 1, 7]
    _door(program, result, "states the variable does not have")


def test_a_risk_reported_for_another_outcome_value_is_refused():
    """The sharpest of them. ``verify_answer_names_its_question`` holds the
    answer's variable NAMES to the query; a question is not only its
    variables. Here the block, its record and the index all agree that the
    risk is of ``y=False`` — and the query asked about ``y=True``."""
    program, result = _pair("combined_measurement_error_correction")
    block = _block(result, "combined_measurement_error_correction")
    for node in (block, block["sufficient_statistics"]):
        node["target_value"] = False
    block["sufficient_statistics"]["target_index"] = 0
    _door(program, result, "the query asked about")


def test_a_design_that_agrees_with_itself_and_not_with_the_page():
    """Both copies of the design renamed. Every re-derivation still runs,
    and the covariate a reader is told the answer adjusted for is not the
    one it adjusted for."""
    program, result = _pair("regression_calibration")
    block = _block(result, "regression_calibration")
    for node in (block, block["sufficient_statistics"]):
        node["design_vars"] = ["w", "q"]
    _door(program, result, "adjusts for")


# ---------------------------------------- the disclosure whose absence is silent


def test_a_correction_that_left_the_simplex_cannot_say_it_did_not():
    """Under-disclosure is the dangerous direction: a risk that is not a
    probability, beside a flag saying there is nothing to disclose."""
    program, result = _pair("exposure_measurement_error_correction")
    block = _block(result, "exposure_measurement_error_correction")
    block["risks"][0] = -0.2
    _door(program, result, "withheld")


def test_a_correction_that_did_not_cannot_say_it_did():
    """And the other direction, which costs a reader a number they should
    have trusted."""
    program, result = _pair("exposure_measurement_error_correction")
    block = _block(result, "exposure_measurement_error_correction")
    assert all(0.0 <= r <= 1.0 for r in block["risks"])
    block["out_of_simplex"] = True
    _door(program, result, "disproves")


# ----------------------------------------------- coverage is a shape, not a list


def test_the_pair_question_reaches_any_block_that_records_one():
    """Asked of the envelope's shape rather than of a list of corrections.

    Today the six blocks that record sufficient statistics and are not
    corrections repeat nothing in them, so the question finds nothing there
    — which is an answer and not a skip. Asked at the rule, because a block
    growing a field to prove it would be refused by the schema first, and
    the test would then pass for a reason that has nothing to do with this.
    """
    verify_correction_frame(
        {"numeric_estimate": {"anything": {
            "weight": 0.25,
            "sufficient_statistics": {"weight": 0.25},
        }}},
        {"statements": []}, query_id="q")

    with pytest.raises(VerificationError, match="re-derived from one of them"):
        verify_correction_frame(
            {"numeric_estimate": {"anything": {
                "weight": 0.25,
                "sufficient_statistics": {"weight": 0.75},
            }}},
            {"statements": []}, query_id="q")


def test_a_state_list_of_zero_and_one_is_not_a_domain_of_false_and_true():
    """Python calls a boolean an integer, and a frame check that agreed
    would let a correction over ``[0, 1]`` pass as one over the declared
    ``[false, true]`` — the whole of what this module holds."""
    program = {"statements": [
        {"kind": "variable", "predicate": "x", "domain": [True, False]}]}
    result = {"numeric_estimate": {
        "treatment": "x",
        "measurement_correction": {"states": [0, 1]},
    }}
    with pytest.raises(VerificationError, match="does not have"):
        verify_correction_frame(result, program, query_id="q")
