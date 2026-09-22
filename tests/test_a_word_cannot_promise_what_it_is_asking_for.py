"""The word an answer leads with, against the errand standing beside it.

Two closed vocabularies meet on an envelope and neither is about the
other. ``Shown`` says how far a run got and each status word promises one
of its rungs; ``MissingKind`` says what the run needed and did not have.
Exactly one kind names a rung, and where it does the two sentences
contradict: an answer cannot have reached a structural result and be
sending the reader out to go and find one.

The reading that holds a status against what the envelope shows is
deliberately coarse -- ``ASK`` says only that there is an errand, because
a promise may be read off a total reading and "an errand of this shape"
is not one. So two stored answers settled nothing structurally, asked for
structure, and could still lead with the word that says the structural
question was answered.

What is asserted here:

- the join covers ``MissingKind`` exactly and does not overlap, so a
  seventh kind must be classified rather than join nothing quietly
- the leaf: both stored answers, relabelled, refused at the strongest
  door that reads them
- the rule names no status word -- it is read off ``STATUS_CLAIMS``, so
  the words it can fire on are derived and are exactly the ones that
  promise the rung some errand asks for
- the direction is one way: thirteen stored answers are structurally
  solved and still ask for the DATA, which is not this contradiction
- five silences, each about something absent
- no honest answer is refused.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis.types import STATUS_CLAIMS, MissingKind, ResultStatus, Shown
from themis.verifier.errors import VerificationError
from themis.verifier.status_rules import (
    _ASKS_FOR_NO_RUNG, _RULE_ERRAND, _THE_RUNG_AN_ERRAND_ASKS_FOR,
    verify_no_status_promises_a_rung_an_errand_asks_for as verify)

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: The two answers that settle nothing structurally and ask for structure.
THE_ANSWERS_THIS_IS_ABOUT = [
    "needs_investigation:effect:none#6d8fe1",
    "needs_investigation:effect:none#a9f370",
]

#: And the ones that are structurally solved and still owe the reader an
#: errand — the shape this must not touch.
SOLVED_AND_STILL_ASKING = 13


def _errand(kind):
    return {"kind": str(kind), "need": "whatever_it_was"}


# ------------------------------------------------------------- the join


def test_the_join_covers_every_kind_of_errand():
    """A seventh kind added to ``MissingKind`` and to neither roster would
    be an errand whose relation to the rungs nothing states."""
    classified = set(_THE_RUNG_AN_ERRAND_ASKS_FOR) | _ASKS_FOR_NO_RUNG
    assert classified == {str(k) for k in MissingKind}
    assert not (set(_THE_RUNG_AN_ERRAND_ASKS_FOR) & _ASKS_FOR_NO_RUNG)


def test_exactly_one_kind_of_errand_names_a_rung():
    """Which is why this is a join of one pair and not a table. The other
    five ask for an input or for a premise, and no rung is either."""
    assert _THE_RUNG_AN_ERRAND_ASKS_FOR == {
        str(MissingKind.STRUCTURE): Shown.STRUCTURE}


def test_the_words_this_can_fire_on_are_derived_and_not_named():
    """The rule reads ``STATUS_CLAIMS`` rather than naming a word, so a
    status added later that promises a structural result is covered
    without being mentioned here or there."""
    promising = {
        str(status) for status, claim in STATUS_CLAIMS.items()
        if any(Shown.STRUCTURE in wanted for wanted in claim.carries)}
    assert promising == {"structurally_solved"}


# --------------------------------------------------------- what it refuses


@pytest.mark.parametrize("name", THE_ANSWERS_THIS_IS_ABOUT)
def test_an_answer_asking_for_structure_may_not_say_it_has_one(name):
    """The leaf. Both of these carry a structural verdict of ``false`` and
    an errand of kind ``structure``: the question is open, and the word
    that says it was settled was refused by nothing."""
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    forged["status"] = "structurally_solved"
    with pytest.raises(VerificationError, match="go and get it") as err:
        the_door_for(row["result"])(row["program"], forged)
    assert err.value.rule == _RULE_ERRAND
    assert "structural result" in str(err.value)


def test_the_bare_envelope_is_refused_too():
    with pytest.raises(VerificationError, match="go and get it"):
        verify({"status": "structurally_solved",
                "missing_information": [_errand(MissingKind.STRUCTURE)]})


def test_one_errand_among_several_is_enough():
    """Read per item rather than over the list: an answer asking for three
    things, one of them the rung it claims, is making the claim."""
    with pytest.raises(VerificationError, match="go and get it"):
        verify({"status": "structurally_solved", "missing_information": [
            _errand(MissingKind.PARAMETER), _errand(MissingKind.SAMPLE),
            _errand(MissingKind.STRUCTURE)]})


# ---------------------------------------------------------- what it allows


def test_solved_and_asking_for_data_is_not_this_contradiction():
    """The direction matters. An estimand can be identified and its data
    not be there, and thirteen stored answers are exactly that."""
    asking = [
        name for name, row in SHAPES.items()
        if row["result"].get("status") == "structurally_solved"
        and (row["result"].get("missing_information")
             or row["result"].get("investigation_requests"))]
    assert len(asking) == SOLVED_AND_STILL_ASKING, sorted(asking)
    for name in asking:
        verify(SHAPES[name]["result"])


@pytest.mark.parametrize("kind", sorted(_ASKS_FOR_NO_RUNG))
def test_an_errand_that_names_no_rung_says_nothing_here(kind):
    verify({"status": "structurally_solved",
            "missing_information": [{"kind": kind, "need": "x"}]})


def test_a_word_that_promises_no_rung_the_errands_name_is_untouched():
    """``needs_investigation`` promises an errand, and no kind of errand
    asks for an errand — so the contradiction has one direction and this
    word is not on that side of it."""
    verify({"status": "needs_investigation",
            "missing_information": [_errand(MissingKind.STRUCTURE)]})


@pytest.mark.parametrize("envelope", [
    {},
    {"status": None},
    {"status": "a_word_no_build_carries",
     "missing_information": [_errand(MissingKind.STRUCTURE)]},
    {"status": "structurally_solved"},
    {"status": "structurally_solved", "missing_information": None},
    {"status": "structurally_solved", "missing_information": []},
    {"status": "structurally_solved", "missing_information": ["structure"]},
    {"status": "structurally_solved", "missing_information": [{}]},
    {"status": "structurally_solved", "missing_information": [{"kind": 3}]},
])
def test_the_shapes_this_rule_says_nothing_about(envelope):
    verify(envelope)


# ------------------------------------------------------------- at the door


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    row = SHAPES[shape]
    verify(row["result"])
    verify_honestly(row["program"], row["result"])
