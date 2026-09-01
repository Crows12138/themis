"""A block's arithmetic was audited and its account of itself was not.

Whatever re-derives a number reads the labels beside it as the INPUTS of
the re-derivation: which columns the design had, which values the variable
takes, which value the risk is of, which level the mediators were held at.
Read as an input a label cannot be wrong. Change it and the arithmetic
re-derives a different number that agrees with itself in every place a
reader or an auditor could look — an answer to a question nobody asked.

Measured on the suite's own answers before anything here was written:
forty-eight leaves of the six correction blocks could be edited and still
pass the public door, and the ones that name rather than count could be
edited without moving a single number a reader is shown. Then ten more in
the decompositions, every one of them accepted and not one of them a
number — including the two reference levels of a joint controlled direct
effect, which a check thirty lines from one that reads its own level went
on re-deriving at 0 and 1.

Two kinds of test, and the second is the point.

The first bends one leaf, which is what the sweep gate does, and asserts the
door now refuses. That is the arithmetic of the census: forty-one of the
forty-eight.

The second bends a leaf AND every copy of it — the block, its own record,
and the index that points into it, all moved together into a story that is
internally perfect. The census cannot ask that question, because it edits
one leaf at a time. It is the question this module exists for: a block
whose account of itself is consistent with everything except the question.
"""
from __future__ import annotations

import ast
import copy
import json
import pathlib

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError
from themis.verifier.frame_rules import _CITED, verify_frame
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REPO = FIXTURES.parent.parent
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
SCHEMA = json.loads(
    (REPO / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))

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
        verify_frame(result, program,
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
    verify_frame(
        {"numeric_estimate": {"anything": {
            "weight": 0.25,
            "sufficient_statistics": {"weight": 0.25},
        }}},
        {"statements": []}, query_id="q")

    with pytest.raises(VerificationError, match="re-derived from one of them"):
        verify_frame(
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
        verify_frame(result, program, query_id="q")


# ------------------------------------- a decomposition's account of itself


@pytest.mark.parametrize("side", ["reference_control", "reference_treated"])
def test_a_joint_controlled_direct_effect_is_re_derived_where_it_says(side):
    """The sharpest of them, and it was inside one file.

    ``verify.py`` re-derives the standalone controlled-direct-effect curve
    as ``theta_x + theta_xm · level``, reading the level off the row it is
    about. Thirty lines earlier it re-derived the JOINT block's two rows as
    ``beta_x`` and ``beta_x + sum_gamma`` — the levels written into the rule
    — so a row relabelled to m*=7 went on satisfying a check about m*=0. The
    general form is the same form, and it is the one for every m*.
    """
    program, result = _pair("mediation_joint_linear")
    row = result["numeric_estimate"]["decomposition"]["cde"][side]
    assert row["mediator_level"] in (0.0, 1.0)
    row["mediator_level"] = 7.0
    with pytest.raises(VerificationError, match=r"m\*=7"):
        themis.verify(program, result)


def test_a_row_that_reports_a_controlled_effect_names_where_it_held_them():
    """The other way a level stops being checkable: not being there.

    Held by the schema, one layer before the rule, which is why the door
    refuses with the contract's words and not the re-derivation's. Pinned
    from out here anyway — the re-derivation is only as general as the row
    it reads, so ``mediator_level`` ceasing to be required would silently
    take the previous test's subject away.
    """
    program, result = _pair("mediation_joint_linear")
    del result["numeric_estimate"]["decomposition"]["cde"][
        "reference_control"]["mediator_level"]
    with pytest.raises(SyntacticError, match="mediator_level"):
        themis.verify(program, result)


@pytest.mark.parametrize("method,block,field,forged", [
    ("mediation_linear_imai", "four_way_decomposition", "scale", "risk_ratio"),
    ("mediation_linear_imai", "four_way_decomposition",
     "cde_mediator_reference", 7),
])
def test_a_split_cannot_relabel_what_it_is_a_split_of(
        method, block, field, forged):
    program, result = _pair(method)
    result["numeric_estimate"][block][field] = forged
    _door(program, result, "this system builds that split at")


def test_an_interaction_is_over_the_treatments_the_contrast_is_over():
    program, result = _pair("joint_backdoor_linear")
    result["numeric_estimate"]["interaction"]["order"] = 9
    _door(program, result, "different number of treatments")


# ------------------------------------------------------ which paper, exactly


def _declared_citation_paths(node, path=()):
    """Every place the schema says a citation may stand."""
    if not isinstance(node, dict):
        return
    for name, spec in (node.get("properties") or {}).items():
        here = path + (name,)
        if name == "reference" and spec.get("type") == "string":
            yield here
        yield from _declared_citation_paths(spec, here)


CITATION_PATHS = sorted(_declared_citation_paths(SCHEMA))


def test_every_place_a_citation_may_stand_has_one_registered():
    """Total over the schema, not over what anyone remembered.

    A container that grows a citation is covered the day the schema
    declares it. Without this the registry would go quiet exactly where a
    new attribution appeared, which is the failure mode a registry is
    supposed to remove rather than relocate.
    """
    declared = {".".join(p) for p in CITATION_PATHS}
    assert declared == set(_CITED), declared ^ set(_CITED)


def _cited_in_sources():
    """Every literal this repository writes under a ``reference`` key.

    Read out of the sources rather than out of an answer, because the point
    is the producer's copy: change a citation there and this fails, which is
    where a deliberate change gets declared. Adjacent string literals are
    folded by the parser, so what an ``ast.Constant`` holds is the whole
    text a reader would see.
    """
    for path in sorted((REPO / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and key.value == "reference"
                        and isinstance(value, ast.Constant)
                        and isinstance(value.value, str)):
                    yield path.name, value.value


def test_no_citation_is_written_that_nothing_registered():
    """The producer's side of the same pin.

    The verifier may not import the producer, so the texts are restated —
    and restating is only safe while something says the two are the same
    text. Sixteen ways to spell one attribution is what a registry is for.
    """
    known = {text for texts in _CITED.values() for text in texts}
    written = sorted(set(_cited_in_sources()))
    assert written, "no citation literal found — this gate reads nothing"
    unknown = [(where, text) for where, text in written if text not in known]
    assert not unknown, unknown


@pytest.mark.parametrize("path", sorted(_CITED))
def test_a_citation_cannot_be_replaced_with_another(path):
    """Asked at the rule, one declared path at a time, because most of them
    ride on results no snapshot happens to carry — and a citation nobody
    can reach is exactly the one worth holding."""
    result: dict = {}
    node = result
    steps = path.split(".")
    for key in steps[:-1]:
        node = node.setdefault(key, {})
    node[steps[-1]] = "Somebody Else (1999) §1"
    with pytest.raises(VerificationError, match="attributes this to"):
        verify_frame(result, {"statements": []}, query_id="q")

    node[steps[-1]] = sorted(_CITED[path])[0]
    verify_frame(result, {"statements": []}, query_id="q")
