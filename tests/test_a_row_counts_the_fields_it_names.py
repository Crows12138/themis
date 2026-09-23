"""A row saying a variable is undefined counts the fields it names.

A shortfall in how a variable is DEFINED reaches the reader as one
sentence out of one reading of the declaration::

    name            "framing:belly_fat_loss"
    said.predicate  "belly_fat_loss"
    said.count      "6"
    said.fields     "time_window, measurement, observability, direction,
                     baseline, state_vs_event"

Three claims and one reading behind them. The number is the length of the
list; the list is the fields a declaration has, in the order a declaration
writes them; and what the sentence says it is about is the half of its own
name after the colon.

Nothing had asked. The rule that holds a row against the reader's list is
silent for a row no ask has an item for, and a framing ask never has one —
written down, in that module, as the reason those rows go unheld. It is a
true sentence about THAT comparison and not about the row: a row says what
it is short of twice without anything else on the envelope, and the second
writing is its own name.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis import framing
from themis.verifier.errors import VerificationError
from themis.verifier.investigation_rules import (
    _SAYS_WHAT_IT_IS_SHORT_OF,
    _check_the_fields_a_row_counts_are_the_ones_it_lists as _fields,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: (answer, row index) per row that lists the fields it counts. Pinned
#: because a rule's reach is the point: silence is what this looked like
#: before, and silence is what a rule that stops reaching looks like.
LISTS_FIELDS = sorted(
    (name, i)
    for name, pair in SHAPES.items()
    for i, row in enumerate((pair["result"] or {}).get(
        "missing_information") or ())
    if isinstance((row.get("said") or {}).get("fields"), str))

#: And per row that says what it is about in words as well as in its name.
SAYS_A_PREDICATE = sorted(
    (name, i)
    for name, pair in SHAPES.items()
    for i, row in enumerate((pair["result"] or {}).get(
        "missing_information") or ())
    if isinstance((row.get("said") or {}).get("predicate"), str))


def test_the_corpus_exercises_this_rule():
    assert len(LISTS_FIELDS) == 2, LISTS_FIELDS
    assert len(SAYS_A_PREDICATE) == 2, SAYS_A_PREDICATE


def test_no_honest_answer_is_refused():
    """All of them, not only the carriers.

    A rule reading a block most answers do not carry has more quiet cases
    than loud ones, and a quiet case that raises is found last.
    """
    for _name, pair in SHAPES.items():
        verify_honestly(pair["program"], pair["result"])


@pytest.mark.parametrize("name,i", LISTS_FIELDS)
def test_a_tally_that_is_not_the_length_of_the_list_is_refused(name, i):
    forged = copy.deepcopy(SHAPES[name]["result"])
    said = forged["missing_information"][i]["said"]
    said["count"] = str(len(said["fields"].split(",")) + 1)
    with pytest.raises(VerificationError, match="fields of that variable"):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name,i", LISTS_FIELDS)
def test_a_field_no_declaration_has_is_refused(name, i):
    forged = copy.deepcopy(SHAPES[name]["result"])
    said = forged["missing_information"][i]["said"]
    said["fields"] = said["fields"].replace("baseline", "vibes")
    with pytest.raises(VerificationError, match="spelled that way"):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name,i", LISTS_FIELDS)
def test_an_order_no_declaration_writes_is_refused(name, i):
    """A list is what one reading left over, so its order is not free."""
    forged = copy.deepcopy(SHAPES[name]["result"])
    said = forged["missing_information"][i]["said"]
    listed = [word.strip() for word in said["fields"].split(",")]
    said["fields"] = ", ".join(reversed(listed))
    with pytest.raises(VerificationError, match="a declaration writes them"):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name,i", SAYS_A_PREDICATE)
def test_a_row_about_one_variable_and_named_for_another_is_refused(name, i):
    forged = copy.deepcopy(SHAPES[name]["result"])
    forged["missing_information"][i]["said"]["predicate"] = "another_variable"
    with pytest.raises(VerificationError, match="is filed under the name"):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name,i", SAYS_A_PREDICATE)
def test_saying_nothing_where_the_name_says_something_is_refused(name, i):
    """Present and empty is not absent.

    A channel that files no such field is silent here; one that files it
    and leaves it blank has said nothing in the place its own name says
    what the row is about.
    """
    forged = copy.deepcopy(SHAPES[name]["result"])
    forged["missing_information"][i]["said"]["predicate"] = ""
    with pytest.raises(VerificationError, match="is filed under the name"):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


def test_what_this_rule_does_not_answer():
    """Two silences, each of them another author's question.

    A row that lists no fields is not a row that miscounted them, and
    whether it owes the sentence at all is what the species declares one
    rule over. A tally with no list beside it is the same silence from
    the other side.
    """
    _fields("row", {"said": {"predicate": "x"}})
    _fields("row", {"said": {"count": "3"}})
    _fields("row", {})


def test_the_words_a_row_says_it_with_are_the_ones_read():
    """The two channels spell it differently and mean one thing.

    A parameter row calls what it is short of the ``key`` and a framing
    row calls it the ``predicate``. Both are the half of the name after
    the colon, which is why they are read together rather than by two
    rules that would disagree the first time one moved.
    """
    assert _SAYS_WHAT_IT_IS_SHORT_OF == ("key", "predicate")


def test_the_fields_are_the_contracts_and_in_its_order():
    """The roster is read from the contract, never kept beside it."""
    order = [field.name for field in framing.FIELDS]
    assert len(order) == len(set(order)) == 9, order
    for name, i in LISTS_FIELDS:
        listed = [word.strip() for word in
                  SHAPES[name]["result"]["missing_information"][i]
                  ["said"]["fields"].split(",")]
        assert listed == [field for field in order if field in listed], listed
