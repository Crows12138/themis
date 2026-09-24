"""A shopping list says WHERE to collect, and the where is a real place.

A ``missing_information`` row short of a parameter says what to measure
and where to measure it::

    name                  "parameter:P_rct_us(y=True|x=True,z1=True)"
    said.key              "P_rct_us(y=True|x=True,z1=True)"
    observable.variables  ["x", "y", "z1"]
    observable.population "rct_us"

The what is held by :mod:`test_one_missing_parameter_written_three_ways`,
against the key on the same row. The where was held by nothing: measured
before this existed, all eighteen single-field edits of the six rows that
name a place -- the name misspelt, blanked, and replaced with a word
neither document uses -- passed both public doors. An answer could send
an analyst to a population this problem never heard of, on the one block
that IS the answer for a run that reports no number.

Two sentences hold it, and they answer different questions:

- the place is one the PROGRAM names, in either role: a selection node's
  source domain, or a question's target. The record is the program, which
  is the side an answer cannot edit.
- the key beside it names a population too, in its subscript, so the two
  are one fact written twice on one row.

Neither covers the other. A forgery that moves the place in both writings
agrees with itself, and within this rule only the program notices; a row
sent to another population this problem really does have is a real place,
and only the key notices. Which sentence speaks is exercised below by the
message each bend gets rather than described.

What this rule does NOT buy is counted too. 241 of the 252 stored answers
come from a program that names no population at all, and there the
question goes unasked rather than being answered out of the list being
judged -- a roster read off the rows would make every row agree with
itself by construction.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import _domains_the_program_declares
from themis.verifier.investigation_rules import (
    _check_the_population_this_row_sends_a_reader_to,
    populations_of,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Answers carrying the block at all.
CARRIERS = sorted(
    name for name, pair in SHAPES.items()
    if (pair["result"] or {}).get("missing_information"))

#: (answer, row index) for the rows that send a reader somewhere.
WITH_PLACE = sorted(
    (name, i)
    for name in CARRIERS
    for i, row in enumerate(SHAPES[name]["result"]["missing_information"])
    if isinstance((row.get("observable") or {}).get("population"), str)
)

#: The answers those rows are in.
ANSWERS = sorted({name for name, _ in WITH_PLACE})


def _places_of(name: str) -> frozenset[str]:
    """Every population the answer's own program names."""
    return populations_of(_premises_of(SHAPES[name]["program"],
                                       SHAPES[name]["result"])[1])


def test_the_block_and_the_part_of_it_this_rule_reaches():
    """The denominator and the honest limit, both as numbers.

    Six rows of 147 name a place. A rule that is silent on the rest is
    right to be -- a row short of a whole query names nothing to go and
    collect -- but the difference between the two counts is the only
    place that is visible, so it is written down.
    """
    assert len(CARRIERS) == 53, len(CARRIERS)
    rows = sum(len(SHAPES[n]["result"]["missing_information"])
               for n in CARRIERS)
    assert rows == 147, rows
    assert len(WITH_PLACE) == 6, len(WITH_PLACE)
    assert len(ANSWERS) == 5, ANSWERS


def test_every_place_the_corpus_names_is_one_its_program_declares():
    """The honest floor, stated as the fact it is.

    Not an assertion about the rule: an assertion about the producers.
    Every place any stored answer sends a reader to is a domain its own
    program declared, so the rule below refuses nothing honest today.
    A producer that starts naming a place from somewhere else breaks this
    line first, where the fact is, rather than arriving as a mysterious
    refusal on a run nobody can reproduce.
    """
    for name, i in WITH_PLACE:
        row = SHAPES[name]["result"]["missing_information"][i]
        assert row["observable"]["population"] in _places_of(name), (
            name, i, row["observable"]["population"], sorted(_places_of(name)))


@pytest.mark.parametrize("name", ANSWERS)
def test_an_honest_answer_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_the_program_and_the_context_say_the_same_thing():
    """One fact, and the two carriers it is read off.

    This package already had a reader for it: the gap-sentence door is
    handed a verification context and asks it for the query's target and
    each selection node's source. This rule is handed the PROGRAM, which
    is what its door takes, and so reads the same declaration off the
    statements.

    They are two projections of one document rather than two facts, and
    that is asserted where it can be seen rather than trusted: on every
    one of the 251 stored answers the two readings are the same set. A
    program shape that makes them differ fails here, in the open, instead
    of quietly giving one door a roster the other does not have.
    """
    same = 0
    for name, pair in SHAPES.items():
        _ast, program, _query, context = _premises_of(pair["program"],
                                                      pair["result"])
        assert populations_of(program) == frozenset(
            _domains_the_program_declares(pair["result"], context)), name
        same += 1
    assert same == 251, same


def test_every_forged_place_is_refused():
    """One edit at a time, counted.

    Three lies per row, and all three are the same lie told with
    different words: the place misspelt, the place blanked, and the place
    replaced with a word neither document uses. The blank is the one a
    rule written to skip missing fields lets through -- a row carrying
    the field and leaving it empty still sends a reader somewhere, and
    nowhere is not a place this problem has.
    """
    refused = 0
    for name, i in WITH_PLACE:
        pair = SHAPES[name]
        here = pair["result"]["missing_information"][i]["observable"][
            "population"]
        for bend in (here + "_forged", "", "no_document_uses_this_name"):
            forged = copy.deepcopy(pair["result"])
            forged["missing_information"][i]["observable"]["population"] = bend
            with pytest.raises(VerificationError):
                the_door_for(pair["result"])(pair["program"], forged)
            refused += 1
    assert refused == 18, refused


def test_a_place_this_problem_has_but_this_parameter_is_not_about():
    """The lie the roster cannot see, on every row that can tell it.

    Sending a reader to the OTHER declared domain is a real place, so the
    first sentence is right to say nothing. The key on the same row is
    what notices, and it notices on all six: every stored row names its
    population in the key's subscript as well.
    """
    told = 0
    for name, i in WITH_PLACE:
        pair = SHAPES[name]
        here = pair["result"]["missing_information"][i]["observable"][
            "population"]
        elsewhere = sorted(_places_of(name) - {here})
        assert elsewhere, (name, i)
        forged = copy.deepcopy(pair["result"])
        forged["missing_information"][i]["observable"]["population"] = (
            elsewhere[0])
        with pytest.raises(VerificationError,
                           match="the key says which population"):
            the_door_for(pair["result"])(pair["program"], forged)
        told += 1
    assert told == 6, told


def test_the_two_sentences_are_told_apart_in_the_message():
    """Not a count: the sentence a reader gets has to say which.

    A place this problem does not have and a place it has but this
    parameter is not about are different problems with different fixes.
    One message covering both would leave whoever reads the refusal to go
    and work out which, on the block an analyst is meant to act on.
    """
    name, i = WITH_PLACE[0]
    pair = SHAPES[name]

    forged = copy.deepcopy(pair["result"])
    forged["missing_information"][i]["observable"]["population"] = "atlantis"
    with pytest.raises(VerificationError,
                       match="a place this problem does not have"):
        the_door_for(pair["result"])(pair["program"], forged)

    here = pair["result"]["missing_information"][i]["observable"]["population"]
    forged = copy.deepcopy(pair["result"])
    forged["missing_information"][i]["observable"]["population"] = sorted(
        _places_of(name) - {here})[0]
    with pytest.raises(VerificationError,
                       match="the key says which population"):
        the_door_for(pair["result"])(pair["program"], forged)


def test_a_program_that_names_no_place_is_not_asked_for_a_roster():
    """The limit, exercised rather than described.

    240 of the 251 stored answers come from a program that declares no
    population at all -- no selection node, no transported question --
    and 47 of those carry this block. A row there could name a place and
    this rule says nothing, because the only list it could check against
    would be the rows themselves, and a list judged against itself agrees
    with itself.

    That is a real hole, and it is a hole in the PROGRAM rather than in
    the rule: a document that names no place has nothing to be sent to.
    """
    silent = [n for n, pair in SHAPES.items()
              if not populations_of(_premises_of(pair["program"],
                                                 pair["result"])[1])]
    assert len(silent) == 240, len(silent)
    assert len([n for n in silent if n in CARRIERS]) == 47

    name = "needs_investigation:counterfactual:none"
    assert name in silent, sorted(silent)[:5]
    forged = copy.deepcopy(SHAPES[name]["result"])
    forged["missing_information"][0]["observable"]["population"] = "atlantis"
    the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


def test_the_silences_this_rule_keeps():
    """Three occasions to say nothing, put to the rule directly.

    Through the door two of them cannot be staged: a row whose key loses
    its subscript is a row whose name moved too, and the gap report
    quoting that name refuses the answer before this rule is reached. So
    the rule is asked here with rows built for the question, which is the
    only way to see that it stays quiet for the reason claimed rather
    than because something else spoke first.
    """
    row = {
        "name": "parameter:P_trial(y=True|x=True)",
        "said": {"key": "P_trial(y=True|x=True)"},
        "observable": {"population": "trial", "variables": ["x", "y"]},
    }

    # A program that declares nothing: no roster, so no question.
    _check_the_population_this_row_sends_a_reader_to(
        "missing_information[0]", row, frozenset())

    # A row that names no place: nothing was claimed.
    _check_the_population_this_row_sends_a_reader_to(
        "missing_information[0]",
        {"name": "query:something", "observable": {"variables": ["x"]}},
        frozenset({"trial"}))

    # A key whose grammar says no population: the second sentence has
    # nothing to compare, and reading one out of a shape it does not
    # recognise would be inventing the disagreement.
    _check_the_population_this_row_sends_a_reader_to(
        "missing_information[0]",
        {**row, "said": {"key": "P(y=True|x=True)"},
         "name": "parameter:P(y=True|x=True)"},
        frozenset({"trial", "user"}))

    # And the one it does speak to, so the three above are silences
    # rather than a rule that never fires.
    with pytest.raises(VerificationError,
                       match="a place this problem does not have"):
        _check_the_population_this_row_sends_a_reader_to(
            "missing_information[0]", row, frozenset({"user"}))


def test_a_place_moved_in_both_writings_is_caught_by_the_program():
    """The forgery that agrees with itself.

    Moving the place in the key as well leaves the row internally
    consistent, and the second sentence has nothing left to say. Put to
    the rule directly for the same reason as above: through the door the
    gap report quoting the parameter's name reaches this answer first, so
    a refusal there would not tell us this rule works.
    """
    with pytest.raises(VerificationError,
                       match="a place this problem does not have"):
        _check_the_population_this_row_sends_a_reader_to(
            "missing_information[0]",
            {"name": "parameter:P_atlantis(y=True|x=True)",
             "said": {"key": "P_atlantis(y=True|x=True)"},
             "observable": {"population": "atlantis",
                            "variables": ["x", "y"]}},
            frozenset({"trial", "user"}))
