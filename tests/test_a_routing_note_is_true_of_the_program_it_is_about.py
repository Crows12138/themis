"""A routing note is true of the program it is about.

A ``dose_response_query`` names the curve to draw and not the query to draw
it for. The estimation layer picks one, and where the pick was not the
obvious one it leaves a note on
``estimation_context.data_contract_warnings`` saying what happened. Four of
the six notes it can leave say the curve was not drawn at all, so on those
answers the note IS the answer to the question that was asked.

Five of the six are propositions about the PROGRAM. Nothing read them. The
shape of each note was held -- a token saying ``the_query_id_matches_nothing``
has to carry the id it is about -- and the shape is the same whichever note
the producer leaves, so the two that share a hole were interchangeable: the
run that skipped the curve because the id it was handed pointed at a
mediation could say instead that the id matched nothing, and the reader
would go hunting for a typo in a name that is spelt right, in a program
where the query it names is sitting.

What is asserted here:

- the corpus carries three of the six notes, pinned, and the roster is read
  off the vocabulary rather than restated, so a member added to it shows up
  here as an uncovered member and not as silence
- no honest answer in the corpus is refused -- all of them, not only the
  carriers, because a rule reading a field most answers do not carry is a
  rule whose quiet cases are most of its cases
- every other note, put in place of the honest one with the facts it had,
  is refused
- every name in a note, moved to another name the program carries, is
  refused
- the note written into two slots is refused when the slots disagree, in
  both directions, and the two words beside it are held as the constant
  pair they are, against the one site that writes them
- the plan is NOT re-derived, and a missing note is not an offence, because
  which query a request resolves to is a decision and a second author for a
  decision is two decisions
- and the one note that is about a column says here that its predicate is
  not checked, rather than passing as checked
"""
from __future__ import annotations

import ast
import copy
import inspect
import json
import pathlib

import pytest

from themis.estimation.warning_words import DoseResponse
from themis.language import token as spelling
from themis.verifier import VerificationError
from themis.verifier import dose_response_routing_rules as rules
from themis.verifier.dose_response_routing_rules import (
    VOCABULARY, verify_where_a_dose_response_request_went)

from .answer_corpus import verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: Every note this build can leave, read off the vocabulary. Restating them
#: would make this file a second author for the set, and the one question
#: below that a second author cannot answer is which of them the corpus
#: leaves unexercised.
EVERY_NOTE = frozenset(spelling(member) for member in DoseResponse)

#: Which of them stored answers carry, and how many answers carry one.
#: Pinned because every forgery below draws from these, and a roster taken
#: from the corpus is a roster that can empty without saying so.
ANSWERS_WITH_A_NOTE = 3
NOTES_THE_CORPUS_CARRIES = frozenset({
    "the_treatment_is_binary",
    "the_query_id_matches_nothing",
    "no_query_id_so_the_first_eligible_won",
})

#: The note that is about a column rather than about the program.
ABOUT_A_COLUMN = "the_treatment_is_binary"


def _notes(result: dict) -> list[dict]:
    context = result.get("estimation_context") or {}
    return [w for w in (context.get("data_contract_warnings") or [])
            if isinstance(w, dict) and w.get("vocabulary") == VOCABULARY]


def _carriers() -> list[str]:
    return sorted(name for name, row in SHAPES.items()
                  if _notes(row["result"]))


def _forged(name: str):
    """A deep copy of this answer, and its note inside that copy.

    Where the answer carries the note in two slots, the copy carries ONE
    object in both -- which is what the producer does, and what makes every
    forgery below the consistent one a forger would write rather than one
    that gives itself away by leaving the other slot behind.
    """
    result = copy.deepcopy(SHAPES[name]["result"])
    note = _notes(result)[0]
    fallback = result.get("estimator_fallback")
    if isinstance(fallback, dict) and fallback.get("reason") == note:
        fallback["reason"] = note
    return result, note


def test_the_corpus_exercises_this_rule():
    carriers = _carriers()
    assert len(carriers) == ANSWERS_WITH_A_NOTE, carriers
    carried = {_notes(SHAPES[n]["result"])[0]["token"] for n in carriers}
    assert carried == NOTES_THE_CORPUS_CARRIES, carried
    assert NOTES_THE_CORPUS_CARRIES < EVERY_NOTE, sorted(EVERY_NOTE)
    assert len(EVERY_NOTE) == 6, sorted(EVERY_NOTE)


def test_no_honest_answer_is_refused():
    """All of them, and not only the carriers.

    A rule reading a field most answers do not carry has more quiet cases
    than loud ones, and a quiet case that raises is the failure that would
    be found last.
    """
    for name, row in SHAPES.items():
        verify_where_a_dose_response_request_went(row["result"],
                                                  row["program"])


@pytest.mark.parametrize("name", _carriers())
def test_no_honest_carrier_is_refused_at_the_door(name):
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


@pytest.mark.parametrize("name", _carriers())
def test_every_other_note_in_its_place_is_refused(name):
    """The forgery this exists for.

    The facts stay as they were, which is what makes this the forgery a
    producer could make by accident and a forger on purpose: the note that
    arrives is well formed, carries what its own template asks for where
    the template asks for the same thing, and says something else happened.
    """
    honest = _notes(SHAPES[name]["result"])[0]["token"]
    for other in sorted(EVERY_NOTE - {honest}):
        result, note = _forged(name)
        note["token"] = other
        with pytest.raises(VerificationError) as caught:
            verify_where_a_dose_response_request_went(
                result, SHAPES[name]["program"])
        assert other in str(caught.value), (other, str(caught.value))


@pytest.mark.parametrize("name", _carriers())
def test_a_note_that_renames_a_query_is_refused(name):
    """Each name in the note, moved to another name this program carries.

    Names from the program rather than strangers: a stranger is refused by
    anything that looks the name up at all, and what was unheld was a name
    that resolves.
    """
    said = _notes(SHAPES[name]["result"])[0].get("said") or {}
    assert said, name
    program = SHAPES[name]["program"]
    theirs = sorted({s["id"] for s in program["statements"]
                     if s.get("kind") == "query"})
    assert theirs, program
    for key, was in said.items():
        for other in theirs + ["engagement"]:
            if other == was:
                continue
            result, note = _forged(name)
            note["said"][key] = other
            with pytest.raises(VerificationError):
                verify_where_a_dose_response_request_went(result, program)


def test_the_two_slots_carry_one_statement():
    """The identity the producer states, in both directions.

    Three lines write the note and the fallback's reason, so an answer
    carrying one carries the other and they are the same object. Read from
    either side: a reader who reads the fallback and a reader who reads the
    context are entitled to read one thing.
    """
    name = next(n for n in _carriers()
                if _notes(SHAPES[n]["result"])[0]["token"] == ABOUT_A_COLUMN)
    program = SHAPES[name]["program"]

    result, _note = _forged(name)
    result.pop("estimator_fallback")
    with pytest.raises(VerificationError, match="both slots"):
        verify_where_a_dose_response_request_went(result, program)

    result, note = _forged(name)
    # Unpicked from the note on purpose: this is the forgery that edits ONE
    # slot, and the copy above keeps them one object.
    result["estimator_fallback"]["reason"] = copy.deepcopy(note)
    result["estimator_fallback"]["reason"]["said"]["treatment"] = "engagement"
    with pytest.raises(VerificationError, match="both slots"):
        verify_where_a_dose_response_request_went(result, program)

    result, note = _forged(name)
    result["estimation_context"]["data_contract_warnings"].remove(note)
    with pytest.raises(VerificationError, match="carries no statement"):
        verify_where_a_dose_response_request_went(result, program)


def test_the_fallback_names_the_one_reason_this_build_falls_back_for():
    """Not that the reason is one of the notes, but which note it is.

    The block is written at one site, for one thing that went wrong: the
    column a curve was asked over takes two values. A reason that is some
    OTHER note tells a reader the curve was dropped for something that
    does not explain a substitution, and asking only whether the two slots
    hold the same object accepts it -- measured, on a note the program
    bore out, before this was written.

    Affordable because the premise is already asserted: the test standing
    at the producer holds the sites that write this block to being one.
    """
    name = next(n for n in _carriers()
                if _notes(SHAPES[n]["result"])[0]["token"] == ABOUT_A_COLUMN)
    result, note = _forged(name)
    other = copy.deepcopy(note)
    other["token"] = "no_effect_query_to_attach_to"
    other["said"] = {}
    result["estimation_context"]["data_contract_warnings"].append(other)
    result["estimator_fallback"]["reason"] = other
    with pytest.raises(VerificationError) as caught:
        verify_where_a_dose_response_request_went(result,
                                                  SHAPES[name]["program"])
    said = str(caught.value)
    assert "for one reason" in said, said
    assert ABOUT_A_COLUMN in said, said


@pytest.mark.parametrize("name", _carriers())
def test_a_missing_note_is_not_an_offence(name):
    """The scope, asserted rather than described.

    Whether a note is OWED is the routing plan, and re-deriving the plan
    here would make this a second author for a decision. An answer with its
    notes taken away is accepted, and the frontier says so in prose above.
    """
    result, _note = _forged(name)
    result["estimation_context"]["data_contract_warnings"] = []
    result.pop("estimator_fallback", None)
    verify_where_a_dose_response_request_went(result, SHAPES[name]["program"])


def test_the_word_about_a_column_is_not_claimed_to_be_checked():
    """Its subject is held and its predicate is not, and the refusal says so.

    No door here has the data, so whether the treatment column really is
    binary cannot be asked. What can be asked is whether the name it calls
    the treatment is one a query in this program intervenes on -- and the
    difference between those two is the kind of thing that goes missing
    when a rule is described by the field it reads.
    """
    name = next(n for n in _carriers()
                if _notes(SHAPES[n]["result"])[0]["token"] == ABOUT_A_COLUMN)
    result, note = _forged(name)
    note["said"]["treatment"] = "engagement"
    result["estimator_fallback"]["reason"] = note
    with pytest.raises(VerificationError) as caught:
        verify_where_a_dose_response_request_went(result,
                                                  SHAPES[name]["program"])
    said = str(caught.value)
    assert "intervenes on" in said, said
    assert "is a fact about the data and is not asked here" in said, said
    assert "not re-derived" in inspect.getdoc(rules).lower()


def test_the_pair_beside_the_reason_is_the_one_substitution():
    """The block's other two fields, and the only hold there is on them.

    They say which estimator a reader is actually being shown. ``from``
    comes out of a declared vocabulary and ``to`` comes out of nowhere, so
    there is no set for either to be checked against and no second writing
    to compare it with; what there is, is that this build performs one
    substitution.
    """
    name = next(n for n in _carriers()
                if _notes(SHAPES[n]["result"])[0]["token"] == ABOUT_A_COLUMN)
    program = SHAPES[name]["program"]
    for field, forged_value in (("from", "dose_response_curve"),
                                ("to", "query_effect"),
                                ("to", "dose_response")):
        result, _note = _forged(name)
        result["estimator_fallback"][field] = forged_value
        with pytest.raises(VerificationError, match="one substitution"):
            verify_where_a_dose_response_request_went(result, program)


def test_the_restated_pair_is_the_pair_the_producer_writes():
    """A restatement held to the thing it restates.

    Found the way the writer-side test finds that site -- by walking
    assignments rather than by matching text -- so a pair renamed at the
    producer fails here rather than quietly coming to mean something else.
    A second such site fails there first, which is what makes restating
    affordable here at all.
    """
    source = (ROOT / "themis" / "estimation" / "dispatch.py").read_text(
        encoding="utf-8")
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any("estimator_fallback" in ast.unparse(target)
                   for target in node.targets):
            continue
        block = node.value
        assert isinstance(block, ast.Dict), ast.unparse(block)
        written = {key.value: value.value
                   for key, value in zip(block.keys, block.values)
                   if isinstance(key, ast.Constant)
                   and isinstance(value, ast.Constant)}
        found.append((written.get("from"), written.get("to")))
    assert found == [rules.THE_ONE_SUBSTITUTION], found


def test_the_half_that_comes_from_nowhere_is_recorded_as_such():
    """The finding this rule could not act on, kept where it was found.

    ``from`` is an Estimand member. ``to`` is not, and no vocabulary in
    this build has it. Saying so beside the restatement is what keeps the
    restatement from reading as an endorsement of the word.
    """
    from themis.estimation.strategy import Estimand

    went_from, went_to = rules.THE_ONE_SUBSTITUTION
    spoken = {str(member) for member in Estimand}
    assert went_from in spoken, spoken
    assert went_to not in spoken, spoken
    assert "Estimand" in inspect.getsource(rules)
