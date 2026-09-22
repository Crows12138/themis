"""One pair of keys, two objects, and the word that says which one this is.

Two pairs of endpoints on this envelope are not one kind by virtue of
where they sit. A probability of causation and a counterfactual cell each
hold the point's bootstrap interval where the run identified a point, and
a band on the identified interval where it did not; ``ci_width_is`` says
which, and the two narrow with different things. ``themis.intervals``
declares exactly those two and names that field, and only the renderers
were reading the declaration.

What is asserted here:

- no honest answer is refused, at the strongest door that reads it, and
  the corpus exercises every branch: a pair with a point, a pair without
  one, and a block reporting no pair at all
- the roster is the one the repository declares, held against
  ``themis.intervals`` rather than against a sentence about it, so a third
  run-decided pair cannot be added there and stay unread here
- both directions of the swap are refused, on each of the four slots, and
  so is a word standing beside no interval
- the rule is reached through the public door
- the sibling the copy rule already holds is held here too, by a different
  question, and the two agree.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import intervals
from themis.verifier import VerificationError
from themis.verifier.interval_kind_rules import (
    _RULE, _WHERE_A_RUN_DECIDES,
    verify_which_object_a_run_decided_pair_is as verify)

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: How many stored answers carry one of these blocks. Named, because a
#: rule the corpus stopped exercising would go quiet without saying so.
ANSWERS_CARRYING_A_RUN_DECIDED_PAIR = 7


def _at(result, path):
    node = result
    for step in path:
        if not isinstance(node, dict):
            return None
        node = node.get(step)
    return node


def _carriers():
    return sorted(name for name, row in SHAPES.items()
                  if any(isinstance(_at(row["result"], path), dict)
                         for path in _WHERE_A_RUN_DECIDES))


# -------------------------------------------------------------- the roster


def test_the_roster_is_the_one_this_repository_declares():
    """Held against the declaration rather than against a sentence about
    it. A third run-decided pair added there and not here would be a pair
    whose word nothing reads, which is what this file exists about."""
    declared = {row.container: row.settled_by
                for row in intervals.DECLARED if row.width is None}
    assert declared == {
        "$defs.causationEstimate": "ci_width_is",
        "numeric_estimate.counterfactual_cell": "ci_width_is",
    }, declared
    assert set(_WHERE_A_RUN_DECIDES.values()) == set(declared)


def test_the_endpoints_are_the_ones_the_declaration_names():
    """And the keys the pair is written under, so a slot that renamed its
    endpoints would not leave this reading looking at nothing."""
    for row in intervals.DECLARED:
        if row.width is None:
            assert (row.lower, row.upper) == ("ci_lower", "ci_upper"), row


def test_every_slot_in_the_roster_is_somewhere_an_answer_can_carry():
    """Four paths, three of them one schema type reached three times."""
    assert len(_WHERE_A_RUN_DECIDES) == 4, _WHERE_A_RUN_DECIDES
    assert sorted(
        path[-1] for path, slot in _WHERE_A_RUN_DECIDES.items()
        if slot == "$defs.causationEstimate") == ["pn", "pns", "ps"]


# ------------------------------------------------------ the honest answers


def test_the_corpus_exercises_this_rule():
    names = _carriers()
    assert len(names) == ANSWERS_CARRYING_A_RUN_DECIDED_PAIR, names
    for name in names:
        verify(SHAPES[name]["result"])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    """The denominator: every stored answer, through the rule."""
    verify(SHAPES[shape]["result"])


def test_all_three_branches_are_exercised_by_honest_answers():
    """A rule two of whose three branches nothing reaches is a rule that
    could say anything on them."""
    seen = set()
    for name in _carriers():
        for path in _WHERE_A_RUN_DECIDES:
            block = _at(SHAPES[name]["result"], path)
            if not isinstance(block, dict):
                continue
            if block.get("ci_lower") is None and block.get("ci_upper") is None:
                seen.add("no pair")
            elif block.get("point") is not None:
                seen.add("sampling")
            else:
                seen.add("outer band")
    assert seen == {"no pair", "sampling", "outer band"}, seen


# --------------------------------------------------------- what it refuses


@pytest.mark.parametrize("path", sorted(_WHERE_A_RUN_DECIDES))
def test_a_band_called_a_bootstrap_interval_is_refused(path):
    """The forgery that matters to a reader: told the width is sampling
    noise, they wait for more rows; it is an identified set, and more rows
    will not move it."""
    envelope = {}
    node = envelope
    for step in path[:-1]:
        node = node.setdefault(step, {})
    node[path[-1]] = {"ci_lower": 0.2, "ci_upper": 0.8, "point": None,
                      "ci_width_is": "sampling"}
    with pytest.raises(VerificationError, match="this run produced") as err:
        verify(envelope)
    assert err.value.rule == _RULE
    assert "outer_band" in str(err.value)


@pytest.mark.parametrize("path", sorted(_WHERE_A_RUN_DECIDES))
def test_a_bootstrap_interval_called_a_band_is_refused(path):
    """And the other direction, which sends a reader after an assumption
    they already have."""
    envelope = {}
    node = envelope
    for step in path[:-1]:
        node = node.setdefault(step, {})
    node[path[-1]] = {"ci_lower": 0.2, "ci_upper": 0.8, "point": 0.5,
                      "ci_width_is": "outer_band"}
    with pytest.raises(VerificationError, match="this run produced"):
        verify(envelope)


def test_a_word_removed_is_refused():
    """Absent is not silence here: the renderers refuse a run-decided pair
    that says nothing, so a missing word is a reader sent back to
    guessing."""
    with pytest.raises(VerificationError, match="this run produced"):
        verify({"numeric_estimate": {"counterfactual_cell": {
            "ci_lower": 0.2, "ci_upper": 0.8, "point": 0.5,
            "ci_width_is": None}}})


def test_a_word_beside_no_interval_is_refused():
    """The third branch. A block that reported nothing to be either kind
    of, saying which kind it is."""
    with pytest.raises(VerificationError, match="no interval at all") as err:
        verify({"numeric_estimate": {"counterfactual_cell": {
            "ci_lower": None, "ci_upper": None, "point": None,
            "ci_width_is": "outer_band"}}})
    assert err.value.rule == _RULE


def test_a_block_reporting_no_interval_and_saying_nothing_is_read():
    verify({"numeric_estimate": {"counterfactual_cell": {
        "ci_lower": None, "ci_upper": None, "point": None,
        "ci_width_is": None}}})


def test_one_endpoint_alone_is_still_a_pair_to_account_for():
    """Half a pair is not no pair. Whether half of one may be reported is
    another rule's question; this one declines to let it carry the word
    for free."""
    with pytest.raises(VerificationError, match="this run produced"):
        verify({"numeric_estimate": {"counterfactual_cell": {
            "ci_lower": 0.2, "ci_upper": None, "point": None,
            "ci_width_is": "sampling"}}})


@pytest.mark.parametrize("envelope", [
    {},
    [],
    {"numeric_estimate": None},
    {"numeric_estimate": {}},
    {"numeric_estimate": {"counterfactual_cell": None}},
    {"numeric_estimate": {"probabilities_of_causation": {"pn": "a"}}},
    {"numeric_estimate": "a"},
])
def test_the_shapes_this_rule_says_nothing_about(envelope):
    verify(envelope)


# ------------------------------------------------------------- at the door


def test_the_rule_is_reached_through_the_public_door():
    """A rule nothing calls is a rule that holds nothing."""
    name = next(
        n for n in _carriers()
        if isinstance(_at(SHAPES[n]["result"],
                          ("numeric_estimate", "probabilities_of_causation",
                           "pn")), dict)
        and _at(SHAPES[n]["result"],
                ("numeric_estimate", "probabilities_of_causation", "pn",
                 "ci_width_is")) is not None)
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    forged["numeric_estimate"]["probabilities_of_causation"]["pn"][
        "ci_width_is"] = "outer_band"
    with pytest.raises(VerificationError, match="this run produced"):
        the_door_for(row["result"])(row["program"], forged)


def test_every_honest_answer_keeps_its_words_at_the_door():
    """The same denominator through the strongest door that reads it."""
    for name in _carriers():
        row = SHAPES[name]
        verify_honestly(row["program"], row["result"])
