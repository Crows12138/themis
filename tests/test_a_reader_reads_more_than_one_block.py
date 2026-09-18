"""A reader reads more than one block, and the chain is held to all of them.

``verify_numeric_display_agrees`` asks the one question that needs no
knowledge of any estimator: a name appearing on both sides names the same
thing. Its subject was ``result["numeric_estimate"]`` alone, which made its
reach a fact about which block an estimator happened to write its numbers
into rather than about what a reader is shown. The module already records
making that mistake one level down, when asking only the envelope's outer
keys made the reach a fact about how deep an estimator nests.

Measured: a joint mediation decomposition reports four controlled effects
under ``extensions``, recorded in the step that produced them, and not one
of them was compared with anything.

Three things had to be true for the subject to widen, and each was
measured before it was written, on the 252 stored answers:

- **A step's output is a record too.** It is where a decomposition's
  numbers live, and without it the widening catches 7 bends instead of 57.
  Read by the marker the serialisation already uses — ``items`` as a
  mapping IS a serialised mapping — because reading a typed value's
  wrapper keys as names makes its ``kind`` answer for every block that has
  one, and 21 honest bootstrap records were called a different run.
- **A block about one unit names the unit.** A counterfactual's target is
  ``Y(joe)`` where the step records ``Y``, because which unit the question
  is about does not change whether it is identified. Without this the
  widening refuses between 58 and 79 honest answers.
- **A word some block claims outright belongs to that block.** Asking
  "does this word name one thing" as a plain count over both blocks was
  wrong in the direction the first measurement did not look: two blocks
  show the same run's ``p_y_do_x0``, a count calls that an ambiguity, and
  73 leaves of ``numeric_estimate`` stop being compared — the
  probabilities of causation among them, which this module's docstring
  records as hard-won. Four readings were scored on three numbers; the one
  written costs nothing and reaches furthest.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier import display_copy_rules as display
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _rows_with(block: str):
    return sorted(
        name for name, pair in SHAPES.items()
        if isinstance(pair["result"].get(block), dict)
        and (pair["result"].get("derivation") or {}).get("steps"))


EXTENSIONS = _rows_with("extensions")


# ------------------------------------------------------------ honest first


def test_the_corpus_carries_extensions_beside_a_chain():
    """The denominator. A corpus this rule had stopped reaching would fail
    here rather than pass by asking nothing."""
    assert len(EXTENSIONS) >= 100, len(EXTENSIONS)


@pytest.mark.parametrize("name", EXTENSIONS)
def test_no_stored_answer_is_refused_by_the_widened_subject(name):
    """Every honest answer the repository produces, through its own door.
    A widening that refuses one of them is wrong however many forgeries it
    would catch."""
    pair = SHAPES[name]
    the_door_for(pair["result"])(pair["program"], pair["result"])


# ------------------------------------------------------- the widened subject


def _forge(name, path, value):
    pair = SHAPES[name]
    forged = copy.deepcopy(pair["result"])
    node = forged
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return pair["program"], forged


def test_a_number_under_extensions_is_held_to_the_step_that_recorded_it():
    """The measured case: a joint decomposition's controlled effects are
    recorded on the way OUT of the step that produced them, and the block a
    reader reads them from agreed with nothing."""
    found = None
    for name in EXTENSIONS:
        for block, body in SHAPES[name]["result"]["extensions"].items():
            numeric = body.get("numeric") if isinstance(body, dict) else None
            if not isinstance(numeric, dict):
                continue
            for leaf, value in numeric.items():
                if isinstance(value, (int, float)) and not isinstance(value,
                                                                      bool):
                    found = (name, block, leaf, value)
                    break
            if found:
                break
        if found:
            break
    assert found, "no decomposition reports a number under extensions"
    name, block, leaf, value = found
    program, forged = _forge(
        name, ("extensions", block, "numeric", leaf), value + 1.5)
    with pytest.raises(VerificationError):
        the_door_for(forged)(program, forged)


# -------------------------------------------------- a step's output records


def test_an_output_that_is_a_mapping_records_the_names_in_it():
    """``items`` as a mapping is how a serialised mapping is spelled."""
    record = display._chain_record([
        {"rule": "r", "inputs": {"a": 1},
         "output": {"kind": "mapping", "items": {"b": 2}}},
    ])
    assert record["a"] == (0, 1)
    assert record["b"] == (0, 2)


def test_an_output_that_is_a_typed_value_records_no_names():
    """And the reason it must not: a wrapper's ``kind`` would answer for
    every block that has one."""
    record = display._chain_record([
        {"rule": "r", "inputs": {"a": 1},
         "output": {"kind": "structural_result", "value": True}},
    ])
    assert "kind" not in record
    assert "value" not in record


# ------------------------------------------------ the unit a block names


def test_a_block_about_one_unit_agrees_with_a_step_that_records_the_predicate():
    assert display._agree("Y(joe)", "Y")
    assert display._agree(["a(me)", "b(me)"], ["a", "b"])
    assert display._agree([["L0(subj)"], ["L1(subj)"]], [["L0"], ["L1"]])


def test_and_a_relabelled_target_still_disagrees():
    """The reduction is what the two record in common, not a way to stop
    looking."""
    assert not display._agree("Z(joe)", "Y")
    assert not display._agree(["a(me)", "c(me)"], ["a", "b"])


def test_a_name_with_no_unit_is_unaffected():
    assert display._agree("Y", "Y")
    assert not display._agree("Y", "Z")


# ------------------------------------------- a word a block claims outright


def test_a_word_a_block_claims_outright_is_not_taken_by_a_nested_leaf():
    """The measured case: ``method`` is the numeric method that ran, and an
    estimand's nested ``method`` deeper in another block is the
    identification it rests on -- a different fact wearing the same word."""
    result = {"numeric_estimate": {"method": "proximal_null_test"},
              "extensions": {"proximal_estimand": {"method": "proximal_matrix"}}}
    claimed = display._claimed_outright(result, result["extensions"])
    assert "method" in claimed


def test_a_word_no_block_claims_outright_stays_available():
    """And the other side, which a plain count over both blocks would have
    taken away: two blocks showing the same run's quantity is not an
    ambiguity."""
    result = {
        "numeric_estimate": {"probabilities_of_causation": {"p_y_do_x0": 0.4}},
        "extensions": {"counterfactual_cell": {"p_y_do_x0": 0.4}},
    }
    claimed = display._claimed_outright(result, result["numeric_estimate"])
    assert "p_y_do_x0" not in claimed
    assert "counterfactual_cell" in claimed


def test_the_probabilities_of_causation_are_still_compared():
    """The reach this frontier must not cost, asked through the door.

    They are the leaves the module's docstring records as hard-won, they
    are named in both blocks, and a reading that counted names would have
    stopped asking about them.
    """
    name = next((n for n in EXTENSIONS
                 if "p_y_do_x0" in (SHAPES[n]["result"]
                                    .get("numeric_estimate") or {})
                 .get("probabilities_of_causation", {})), None)
    if name is None:
        pytest.skip("no probabilities of causation in the corpus")
    shown = SHAPES[name]["result"]["numeric_estimate"][
        "probabilities_of_causation"]["p_y_do_x0"]
    program, forged = _forge(
        name, ("numeric_estimate", "probabilities_of_causation", "p_y_do_x0"),
        shown + 0.25)
    with pytest.raises(VerificationError):
        the_door_for(forged)(program, forged)
