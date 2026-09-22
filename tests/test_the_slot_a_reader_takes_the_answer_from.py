"""The generic answer slot, against the block it is a second writing of.

``numeric_result`` is where a reader who does not want to know which
estimator ran finds the answer. It records nothing — the estimate is
already on the envelope — so every number in it is a number that is also
somewhere else on the same document, and the two were never held together.

What is asserted here:

- no honest answer is refused, at the strongest door that reads it, and
  the corpus exercises both shapes the slot has
- a value that is not the headline point is refused, and a range that is
  no block's range is refused
- which block a range belongs to is not asked, on purpose: that is a fact
  about the route, and the test says what asking it would have cost
- the three silences are silences about something absent, and each is
  exercised
- the rule is reached through the public door.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis.verifier import VerificationError
from themis.verifier.answer_slot_rules import (
    _RULE, verify_the_generic_slot_restates_the_answer as verify)

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: Stored answers where the slot and the estimate stand together — the
#: only shape this rule has anything to say about.
ANSWERS_IN_SCOPE = 9


def _in_scope():
    return sorted(
        name for name, row in SHAPES.items()
        if isinstance(row["result"].get("numeric_result"), dict)
        and isinstance(row["result"].get("numeric_estimate"), dict))


def test_the_corpus_exercises_this_rule():
    names = _in_scope()
    assert len(names) == ANSWERS_IN_SCOPE, names
    for name in names:
        verify(SHAPES[name]["result"])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    """The denominator: every stored answer, through the rule."""
    verify(SHAPES[shape]["result"])


def test_both_shapes_the_slot_has_are_exercised():
    """A rule whose range half nothing reached would pass the denominator
    on values alone."""
    seen = set()
    for name in _in_scope():
        slot = SHAPES[name]["result"]["numeric_result"]
        if slot.get("value") is not None:
            seen.add("value")
        if isinstance(slot.get("interval"), dict):
            seen.add("interval")
    assert seen == {"value", "interval"}, seen


# --------------------------------------------------------- what it refuses


def test_a_value_that_is_not_the_headline_point_is_refused():
    """The number a reader takes as the answer, moved away from the number
    the estimator produced."""
    with pytest.raises(VerificationError, match="written twice") as err:
        verify({"numeric_result": {"value": 0.9},
                "numeric_estimate": {"point": 0.4}})
    assert err.value.rule == _RULE


def test_a_range_no_block_reports_is_refused():
    """And the range half: a reader shown an interval this answer never
    produced."""
    with pytest.raises(VerificationError, match="never produced") as err:
        verify({"numeric_result": {"interval": {"low": 0.1, "high": 0.9}},
                "numeric_estimate": {
                    "counterfactual_cell": {"lower": 0.2, "upper": 0.8}}})
    assert err.value.rule == _RULE
    assert "counterfactual_cell" in str(err.value)


def test_half_a_range_moved_is_refused():
    """Both endpoints are the pair; moving one is a pair no block has."""
    with pytest.raises(VerificationError, match="never produced"):
        verify({"numeric_result": {"interval": {"low": 0.2, "high": 0.9}},
                "numeric_estimate": {
                    "counterfactual_cell": {"lower": 0.2, "upper": 0.8}}})


def test_a_range_belonging_to_any_block_is_accepted():
    """Which block is a fact about which route ran. Asking it would be a
    table of routes; asking whether ANY block reports the pair refuses the
    same forgeries and needs no table — the cost is that a range copied
    from the wrong block of the same answer passes, and both blocks having
    identical endpoints is the case where that is not a lie."""
    verify({"numeric_result": {"interval": {"low": 0.2, "high": 0.8}},
            "numeric_estimate": {
                "counterfactual_cell": {"lower": 0.2, "upper": 0.8},
                "probabilities_of_causation": {"lower": 0.3, "upper": 0.7}}})


def test_a_value_is_exactly_the_point_and_not_nearly():
    """One float written twice. The only distance a copy may drift is
    none, so a rounded restatement is a different number on the screen."""
    with pytest.raises(VerificationError, match="written twice"):
        verify({"numeric_result": {"value": 0.43751081656683},
                "numeric_estimate": {"point": 0.4375108165668343}})


# ------------------------------------------------------ the three silences


def test_an_answer_with_no_estimate_is_not_this_rules_business():
    """A bounded counterfactual puts its numbers under ``extensions`` and
    the slot is then the only copy on the envelope; refusing it here would
    be holding a copy against nothing."""
    verify({"numeric_result": {"interval": {"low": 0.5, "high": 1.0}}})


def test_a_value_beside_no_headline_point_is_not_compared():
    """Two stored answers are this shape. A value beside an estimate that
    reports no point is not a second writing of that point."""
    verify({"numeric_result": {"value": 1.9},
            "numeric_estimate": {"method": "scm_abduction"}})


def test_a_range_beside_no_ranged_block_is_not_compared():
    verify({"numeric_result": {"interval": {"low": 0.1, "high": 0.9}},
            "numeric_estimate": {"point": 0.5}})


@pytest.mark.parametrize("envelope", [
    {},
    [],
    {"numeric_result": None, "numeric_estimate": {}},
    {"numeric_result": {}, "numeric_estimate": {}},
    {"numeric_result": {"value": None}, "numeric_estimate": {"point": 0.4}},
    {"numeric_result": {"interval": "a"}, "numeric_estimate": {}},
    {"numeric_result": {"interval": {"low": None, "high": 0.9}},
     "numeric_estimate": {"counterfactual_cell": {"lower": 0.2,
                                                  "upper": 0.8}}},
])
def test_the_shapes_this_rule_says_nothing_about(envelope):
    verify(envelope)


# ------------------------------------------------------------- at the door


def test_the_rule_is_reached_through_the_public_door():
    """A rule nothing calls is a rule that holds nothing."""
    name = next(n for n in _in_scope()
                if SHAPES[n]["result"]["numeric_result"].get("value")
                is not None
                and SHAPES[n]["result"]["numeric_estimate"].get("point")
                is not None)
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    forged["numeric_result"]["value"] = 0.123
    with pytest.raises(VerificationError, match="written twice"):
        the_door_for(row["result"])(row["program"], forged)


def test_every_honest_answer_keeps_its_slot_at_the_door():
    """The same denominator through the strongest door that reads it."""
    for name in _in_scope():
        row = SHAPES[name]
        verify_honestly(row["program"], row["result"])
