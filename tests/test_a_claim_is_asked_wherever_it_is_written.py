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

The same seam ran one level further out and was found the same way. A walk
over ``estimate.items()`` visits the blocks the ESTIMATE publishes, and an
answer publishes blocks under ``extensions`` too — the counterfactual cell
under both, the same coordinates and the same assumption written twice. The
copy under the estimate was asked and the copy under the extensions was
asked by nothing at all, so a forged cell had only to be forged in the half
nobody read. Which section carries a block is no more part of what it
claims than which layer is.

And the list of what a question names was written as four coordinates and
called the whole of it. A question may also grant the assumption its answer
is identified under; whether monotonicity was assumed decides whether the
cell is a point or a range, so it says which quantity the number is. Being
spelled the same in every kind of question, it is read once for all of them
rather than copied into each kind's row.

Widening the walk turned up the premise the table had been resting on: a
field appears in it under whatever the answer calls it, which holds only
while a name means one thing. ``given`` means three. The answer's own layer
writes a stratum there; a selection recovery writes the columns it
conditioned on; a formula term writes its conditioning set. The corpus said
the widening refused nothing, and it was right about the corpus -- no
collected answer happens to put ``given`` on a block -- while the suite's
own selection answers, built rather than collected, do. Which people a
number is about is the answer's claim and no block else makes it, so that
one reading is asked where it is made.

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
    _ASKED_OF_THE_ANSWER,
    _ASKED_VALUES,
    _EVERY_KIND,
    _asked_values,
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
    layers = list(_every_layer(result, estimate))
    assert layers[0] == ("numeric_estimate", estimate)
    own = [name for name, value in estimate.items() if isinstance(value, dict)]
    assert [name for name, _ in layers[1:1 + len(own)]] == own


def test_the_walk_reaches_the_blocks_the_other_section_publishes():
    """A block is not its address.

    The extensions are named with their section, so a refusal says which of
    two copies it read rather than leaving a reader to guess.
    """
    _, result = _pair("counterfactual_cell_plugin")
    estimate = result["numeric_estimate"]
    names = [name for name, _ in _every_layer(result, estimate)]
    assert "counterfactual_cell" in names
    assert "extensions.counterfactual_cell" in names
    assert names.count("extensions.counterfactual_cell") == 1


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

    The levels come out of the investigation patch too, and not as an
    accommodation: a patch's ``existing`` map is the declaration quoted
    back to the reader as what they need not supply. Leaving it behind
    would build a pair the system cannot produce — an answer telling a
    reader the program already fixed the levels it does not fix — and
    the silence this test is about would be tested through an envelope
    that is not silent.
    """
    program, result = _pair("general_id_plugin")
    program = copy.deepcopy(program)
    treatment = result["numeric_estimate"]["treatment"]
    for statement in program["statements"]:
        if statement.get("kind") == "variable" \
                and statement.get("predicate") == treatment:
            statement.pop("domain", None)
    for request in result.get("investigation_requests") or []:
        for item in request.get("items") or []:
            skeleton = item.get("skeleton") or {}
            if skeleton.get("predicate") == treatment:
                (skeleton.get("existing") or {}).pop("domain", None)
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


# ------------------------------- one cell, two sections, both of them read


#: The four coordinates a counterfactual question names, and the two places
#: an answer writes them back. Read off the corpus rather than listed, so a
#: third section arrives here instead of being missed.
CELL_FIELDS = ("observed_x", "counterfactual_x", "target_y", "factual_y")
CELL_SECTIONS = ("numeric_estimate", "extensions")


def _cell(result, section):
    return (result[section] or {})["counterfactual_cell"]


@pytest.mark.parametrize("section", CELL_SECTIONS)
@pytest.mark.parametrize("field", CELL_FIELDS)
def test_a_cell_coordinate_the_question_did_not_name_is_refused(
        section, field):
    """Which of the four cells a number is about, forged one coordinate at
    a time, in each place the answer says it.

    Nothing here moves a number. The bounds, the interval and the
    observational joint under them go on agreeing; what changes is which
    counterfactual a reader believes the number answers.
    """
    program, result = _pair("counterfactual_cell_plugin")
    block = _cell(result, section)
    assert isinstance(block[field], bool), field
    block[field] = not block[field]
    _frame_refuses(program, result, "asked about")


@pytest.mark.parametrize("section", CELL_SECTIONS)
def test_an_assumption_the_question_did_not_grant_is_refused(section):
    """A cell identified under monotonicity and a cell identified without
    it are two different quantities, and the block is where a reader is
    told which one they have."""
    program, result = _pair("counterfactual_cell_plugin")
    block = _cell(result, section)
    assert block["monotonicity"] is None
    block["monotonicity"] = "non_decreasing"
    _frame_refuses(program, result, "asked about")


@pytest.mark.parametrize("section", CELL_SECTIONS)
def test_an_assumption_the_question_did_grant_cannot_be_dropped(section):
    """And the other direction: a question that granted it and a block
    that does not say so sends a reader looking for a range where the
    answer is a point."""
    program, result = _pair(
        "numerically_solved:counterfactual:"
        "numeric_counterfactual_cell_estimate#365c81")
    block = _cell(result, section)
    assert block["monotonicity"] == "non_decreasing"
    block["monotonicity"] = None
    _frame_refuses(program, result, "asked about")


def test_the_assumption_is_read_once_and_not_per_kind():
    """The question spells an assumption the same way whatever kind it is,
    so it is written once. A kind with no row of its own still gets it,
    which is the difference between a shared reading and a copied one."""
    assert set(_EVERY_KIND) == {"monotonicity"}
    for kind, reads in _ASKED_VALUES.items():
        assert not set(_EVERY_KIND) & set(reads), kind

    program, result = _pair("counterfactual_cell_plugin")
    asked = _asked_values(program, result.get("query_id"))
    assert "monotonicity" in asked
    assert set(_ASKED_VALUES["counterfactual"]) <= set(asked)


def test_no_answer_that_publishes_a_block_out_there_is_refused_for_it():
    """The widening's own cost, measured rather than assumed.

    Every check in the loop now also looks at the blocks the extensions
    publish. Each is guarded by the shape it reads, so a block carrying
    none of those fields is not spoken to — but that is an argument, and
    the corpus is the measurement.
    """
    published = [name for name, pair in SHAPES.items()
                 if any(isinstance(block, dict) for block
                        in (pair["result"].get("extensions") or {}).values())]
    assert len(published) >= 200, len(published)
    for name in published:
        program, result = _pair(name)
        verify_frame(result, program, query_id=result.get("query_id"))


def test_a_word_the_envelope_reuses_is_not_read_off_every_block():
    """One word, three facts, and only one of them is the question's.

    Reading it off every block was measured against the corpus first and
    looked safe there, because no collected answer puts ``given`` on a
    block. An answer the suite builds does, and this is that answer's
    shape: a selection recovery naming the columns it conditioned on,
    which is not a stratum and not wrong.
    """
    assert "given" not in _ASKED_VALUES["effect"]
    assert set(_ASKED_OF_THE_ANSWER["effect"]) == {"given"}

    program, result = _pair("numerically_solved:effect:none")
    block = result["extensions"]["selection_recovery"]
    assert "given" not in block
    block["given"] = block["adjustment_set"]
    verify_frame(result, program, query_id=result.get("query_id"))

    result["numeric_estimate"]["given"] = [["nobody", True]]
    _frame_refuses(program, result, "asked about")
