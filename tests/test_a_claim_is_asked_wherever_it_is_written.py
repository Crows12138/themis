"""Which layer a claim sits at is not whether it can be wrong.

An answer's outermost labels say what the whole answer is about: which
variable, which outcome, and — on the routes that report a contrast between
two levels — which two levels it ran between and which outcome level its
risks are the probability of. The names half was held to the question by
``program_copy_rules``. The values half was held nowhere, and the reason was
a loop: the walk that asks a label what it is about started one layer in,
at ``estimate.items()``, so it only ever visited BLOCKS.

A query's ``{atom: x, value: True}`` is one node with two halves, and an
answer copies both — under two names, at whichever layer its producer put
them. Which half got held was decided by which of two tables owned the
reading; which layer got asked was decided by which of two walks owned the
question. Neither decision has anything to do with the defect, and the arm
labels fell into the seam between them: twenty-one forgeries across three
routes, every one accepted, including a general-ID answer reporting the
contrast from ``False`` to ``False`` — one cell against itself — with a
difference between them.

Not merged with the names table, though the shapes match. Measured first:
asking the names of every block as well reaches three fields today, all
three already held by something else, and two rules checking one identity is
redundancy rather than independence.

The reference arm is the one label here the question does not name. An
effect query says which level was intervened TO and leaves the FROM to the
estimator, so it is held to what the program does say — the levels the
variable has — and to the arm beside it, which the question does name.
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.frame_rules import (
    _ASKED_VALUES,
    _every_layer,
    verify_frame,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The three labels an answer uses to say which contrast it reports, and the
#: shapes that carry them — read off the snapshot, so a fourth route arrives
#: here rather than being listed.
ARMS = ("treatment_high", "treatment_low", "outcome_high")
CARRIERS = sorted(
    (name, field)
    for name, pair in SHAPES.items()
    if isinstance(pair["result"].get("numeric_estimate"), dict)
    for field in ARMS
    if pair["result"]["numeric_estimate"].get(field) is not None
)


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _frame_refuses(program, result, match):
    """The door refuses, and this rule refuses for its own reason.

    Most of these edits are reached by nothing else at all — that is what
    the frontier was — but stating both keeps the test about what THIS rule
    says rather than about what happens to be first.
    """
    with pytest.raises(VerificationError):
        themis.verify(program, result)
    with pytest.raises(VerificationError, match=match):
        verify_frame(result, program, query_id=result.get("query_id"))


# ------------------------------------------------ the walk reaches the answer


def test_the_walk_visits_the_answer_and_then_every_block_on_it():
    """The answer first, so a rule handed both the estimate and the block
    sees one dict — which is what it means for the answer to be the thing a
    question is about."""
    _, result = _pair("general_id_plugin")
    estimate = result["numeric_estimate"]
    layers = list(_every_layer(estimate))
    assert layers[0] == ("numeric_estimate", estimate)
    assert [name for name, _ in layers[1:]] == [
        name for name, value in estimate.items() if isinstance(value, dict)]


def test_the_question_is_asked_through_that_walk_and_not_a_second_one():
    """A loop over ``estimate.items()`` is how the outer layer went unasked
    for as long as it did; written as a gate so it cannot come back."""
    source = inspect.getsource(verify_frame)
    tree = ast.parse(source.lstrip())
    loops = [node for node in ast.walk(tree) if isinstance(node, ast.For)]
    assert len(loops) == 1
    call = loops[0].iter
    assert isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    assert call.func.id == "_every_layer"


# --------------------------- the levels a contrast says it ran between


@pytest.mark.parametrize("shape,field", CARRIERS)
@pytest.mark.parametrize("forged", [True, False, "hi", 7])
def test_a_level_the_question_did_not_name_is_refused(shape, field, forged):
    """Every arm label, every route, three ways of being wrong — the other
    level, a level of no variable here, and a number.

    None of these moves a number. The contrast, its interval and the
    corners under it all go on agreeing with each other; what changes is
    which two levels a reader believes the difference was taken between.
    """
    program, result = _pair(shape)
    if result["numeric_estimate"][field] == forged:
        pytest.skip("that is what this answer honestly says")
    result["numeric_estimate"][field] = forged
    _frame_refuses(program, result,
                   "asked about|takes|are one level")


def test_a_contrast_from_a_cell_to_itself_is_refused():
    """The sharpest of them: both arms at one level, so the difference the
    answer reports is a difference between a cell and itself."""
    program, result = _pair("general_id_plugin")
    estimate = result["numeric_estimate"]
    estimate["treatment_low"] = estimate["treatment_high"]
    _frame_refuses(program, result, "are one level")


def test_a_reference_arm_the_variable_never_takes_is_refused():
    """The FROM arm is not in the question, so it is held to what the
    program does say about that variable."""
    program, result = _pair("general_id_plugin")
    result["numeric_estimate"]["treatment_low"] = "control"
    _frame_refuses(program, result, "takes")


def test_a_variable_with_no_declared_domain_is_not_contradicted_about_it():
    """Silence is not a claim.

    A program that declares no levels for its treatment cannot disagree
    about the reference arm — and the answer is honest, so it must pass.
    The arm beside it is still held, because that one the question named.
    """
    program, result = _pair("general_id_plugin")
    program = copy.deepcopy(program)
    treatment = result["numeric_estimate"]["treatment"]
    for statement in program["statements"]:
        if statement.get("kind") == "variable" \
                and statement.get("predicate") == treatment:
            statement.pop("domain", None)
    themis.verify(program, result)

    result["numeric_estimate"]["treatment_low"] = "control"
    verify_frame(result, program, query_id=result.get("query_id"))

    result["numeric_estimate"]["treatment_high"] = "exposed"
    _frame_refuses(program, result, "asked about")


# ------------------------------ one fact, two names, one row each


def test_the_outcome_level_is_read_from_the_question_under_both_its_names():
    """A correction block calls it ``target_value`` and the answer's own
    layer calls it ``outcome_high``. Two rows, one reading — which is what
    a table indexed by the field an answer uses looks like when a fact is
    written at two layers."""
    query = {"kind": "effect",
             "intervention": {"atom": {"predicate": "x"}, "value": True},
             "target": {"atom": {"predicate": "y"}, "value": "high"}}
    reads = _ASKED_VALUES["effect"]
    assert reads["outcome_high"](query) == "high"
    assert reads["target_value"](query) == "high"
    assert reads["treatment_high"](query) is True


def test_a_correction_block_is_still_asked_the_question_it_always_was():
    """The walk grew a layer; it did not lose one."""
    program, result = _pair("measurement_error_correction")
    block = result["numeric_estimate"]["measurement_correction"]
    assert "target_value" in block
    block["target_value"] = "neither of the two"
    _frame_refuses(program, result, "target_value")
