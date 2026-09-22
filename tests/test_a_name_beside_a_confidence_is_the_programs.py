"""The names beside a confidence, against the document they came out of.

Each row of ``confidence_sources`` carries a number and two names: the slot
the number came out of, and whose statement said it. The number is held by
the arithmetic beside it -- the composite is the minimum across the rows --
and the names are held by nothing arithmetic can reach. What holds a name
is the document it was copied from, and that document is the program.

What is asserted here:

- no honest answer is refused, at the strongest door that reads it, and
  the corpus really does exercise the rule
- the label is spelled the way the producer spells it, held against the
  producer's own two spellings rather than against a sentence about them
- a row filed under a slot the program does not annotate is refused, and
  so is a row whose source is not what the program wrote at the slot it
  names
- an edge claimed twice is refused, which is the forgery the arithmetic
  cannot see: two rows carrying one number say nothing about the slot the
  reader is no longer shown
- which rows are PRESENT is not held, on purpose, and the test says so
- the rule is silent where the shape is not one this system writes
- it is reached through the public door and not only when called directly.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis.runtime.graph_projection import atom_label
from themis.runtime.numeric_estimator import format_probability_key
from themis.runtime.theta_builder import _key_of
from themis.types import (
    Annotation, Atom, ConstTerm, ProbabilityStatement, RelativeTimeIndex,
    ValuedAtom)
from themis.verifier import VerificationError
from themis.verifier.confidence_source_rules import (
    _NAMES_RULE, _atom_label_here, _slot_label_of,
    verify_the_names_beside_each_confidence as verify)

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: How many stored answers carry rows at all. Named, because a rule the
#: corpus stopped exercising would otherwise go quiet without saying so.
ANSWERS_CARRYING_SOURCES = 3


def _carriers():
    return sorted(name for name, row in SHAPES.items()
                  if row["result"].get("confidence_sources"))


def test_the_corpus_exercises_this_rule():
    names = _carriers()
    assert len(names) == ANSWERS_CARRYING_SOURCES, names
    for name in names:
        verify(SHAPES[name]["result"], SHAPES[name]["program"])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    """The denominator: every stored answer, through the rule."""
    verify(SHAPES[shape]["result"], SHAPES[shape]["program"])


def test_every_kind_of_slot_the_corpus_has_is_exercised():
    """Two of the three spellings are in the corpus. A rule whose
    parameter half was never reached would pass the denominator above on
    edges alone."""
    spelt = {row["slot_label"].split(":")[0]
             for name in _carriers()
             for row in SHAPES[name]["result"]["confidence_sources"]}
    assert spelt == {"edge", "parameter"}, spelt


# ------------------------------------------- the spelling, against the maker


def test_an_atom_is_spelled_the_way_the_producer_spells_it():
    """Held to the producer's function rather than to a sentence about it.
    Two spellings that drifted apart would make an honest observation slot
    look like a name the program does not have."""
    plain = Atom(predicate="sleep", args=(ConstTerm(name="me"),))
    at_zero = Atom(predicate="sleep", args=(ConstTerm(name="me"),),
                   time_index=RelativeTimeIndex(value=0))
    before = Atom(predicate="sleep", args=(ConstTerm(name="me"),),
                  time_index=RelativeTimeIndex(value=-1))
    after = Atom(predicate="sleep", args=(ConstTerm(name="me"),),
                 time_index=RelativeTimeIndex(value=2))
    nullary = Atom(predicate="rain", args=())
    for atom in (plain, at_zero, before, after, nullary):
        assert _atom_label_here(_atom_dict(atom)) == atom_label(atom), atom


def _atom_dict(atom: Atom) -> dict:
    """The atom as the kernel serialises it into the program document."""
    body: dict = {
        "predicate": atom.predicate,
        "args": [{"type": "const", "name": t.name} for t in atom.args],
    }
    if atom.time_index is not None:
        body["time_index"] = {"kind": "relative",
                              "value": atom.time_index.value}
    return body


@pytest.mark.parametrize("population", [None, "trial"])
def test_a_parameter_is_spelled_the_way_the_producer_spells_it(population):
    """Including the order the conditions are written in, which is the
    producer's and not the statement's: a label built in the statement's
    order would name a slot nothing else does."""
    target = ValuedAtom(
        atom=Atom(predicate="belly_fat_loss",
                  args=(ConstTerm(name="me"),)), value=True)
    running = ValuedAtom(
        atom=Atom(predicate="running", args=(ConstTerm(name="me"),)),
        value=True)
    older = ValuedAtom(
        atom=Atom(predicate="age_over_40",
                  args=(ConstTerm(name="me"),)), value=True)
    statement = ProbabilityStatement(
        target=target, given=(running, older), value=0.5,
        population=population,
        annotations=Annotation(confidence=0.6))
    written = {
        "kind": "probability",
        "target": {"atom": _atom_dict(target.atom), "value": target.value},
        "given": [{"atom": _atom_dict(va.atom), "value": va.value}
                  for va in statement.given],
        "value": 0.5,
    }
    if population is not None:
        written["population"] = population
    assert _slot_label_of(written) == (
        f"parameter:{format_probability_key(_key_of(statement))}")


# --------------------------------------------------------- what it refuses


def test_a_slot_the_program_does_not_annotate_is_refused():
    """The name is what a reader follows from a number back to the
    statement it came out of; following this one arrives nowhere."""
    name = _carriers()[0]
    forged = copy.deepcopy(SHAPES[name]["result"])
    forged["confidence_sources"][0]["slot_label"] = "edge:nowhere->nothing"
    with pytest.raises(VerificationError, match="annotates no such slot") as e:
        verify(forged, SHAPES[name]["program"])
    assert e.value.rule == _NAMES_RULE


def test_a_source_the_program_did_not_write_there_is_refused():
    """Whose word the number is. A reader weighing an answer at 0.2 is
    weighing who said 0.2."""
    name = next(n for n in _carriers()
                if SHAPES[n]["result"]["confidence_sources"][0]["source"])
    forged = copy.deepcopy(SHAPES[name]["result"])
    forged["confidence_sources"][0]["source"] = "a randomised trial"
    with pytest.raises(VerificationError, match="came from") as e:
        verify(forged, SHAPES[name]["program"])
    assert e.value.rule == _NAMES_RULE


def test_a_source_line_moved_to_another_real_slot_is_refused():
    """Not an invented name but a real one belonging to another statement:
    the label and the numbers beside it have to be one statement's."""
    envelope = {"confidence_sources": [
        {"slot_label": "edge:x->y", "source": "a review", "confidence": 0.2,
         "is_weakest": True}]}
    program = {"statements": [
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"confidence": 0.9, "source": "a review"}},
        {"kind": "cause", "from": {"predicate": "y", "args": []},
         "to": {"predicate": "z", "args": []},
         "annotations": {"confidence": 0.2, "source": "a review"}},
    ]}
    with pytest.raises(VerificationError, match="says its confidence is"):
        verify(envelope, program)


def test_one_edge_cannot_be_claimed_twice():
    """The forgery the arithmetic next door cannot see: two rows carrying
    one number leave the composite where it was, and the slot the reader
    is no longer shown leaves with them."""
    envelope = {"confidence_sources": [
        {"slot_label": "edge:x->y", "source": None, "confidence": 1.0,
         "is_weakest": True},
        {"slot_label": "edge:x->y", "source": None, "confidence": 1.0,
         "is_weakest": True}]}
    program = {"statements": [
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"confidence": 1.0}},
        {"kind": "cause", "from": {"predicate": "y", "args": []},
         "to": {"predicate": "z", "args": []},
         "annotations": {"confidence": 1.0}},
    ]}
    with pytest.raises(VerificationError, match="filed under") as e:
        verify(envelope, program)
    assert e.value.rule == _NAMES_RULE


def test_one_slot_stated_twice_in_the_program_is_not_a_repeat():
    """The other side of that check. A program may say one edge twice --
    grounded for two units, or stated at two times -- and the row is
    whichever of them the producer picked, so both have to be offerable."""
    envelope = {"confidence_sources": [
        {"slot_label": "edge:x->y", "source": "the second", "confidence": 0.8,
         "is_weakest": True}]}
    program = {"statements": [
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"confidence": 0.4, "source": "the first"}},
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"confidence": 0.8, "source": "the second"}},
    ]}
    verify(envelope, program)


def test_an_observation_slot_is_read_although_the_corpus_has_none():
    """The third spelling, which no stored answer exercises. A spelling
    only the producer can reach is one that drifts unwatched."""
    atom = {"predicate": "slept", "args": [{"type": "const", "name": "me"}]}
    program = {"statements": [
        {"kind": "observation", "atom": atom, "value": True,
         "annotations": {"confidence": 0.7, "source": "a diary"}}]}
    verify({"confidence_sources": [
        {"slot_label": "observation:slept(me)=True", "source": "a diary",
         "confidence": 0.7, "is_weakest": True}]}, program)
    with pytest.raises(VerificationError, match="annotates no such slot"):
        verify({"confidence_sources": [
            {"slot_label": "observation:slept(me)=False", "source": "a diary",
             "confidence": 0.7, "is_weakest": True}]}, program)


# ------------------------------------------------------ what it does not do


def test_a_row_the_answer_never_wrote_is_not_this_rules_business():
    """Stated as a test because it is a decision, not an omission. Which
    slots get a row is the data-gap classifier's reading of what the
    answer rests on; re-deriving it here would hand that reading back to
    itself, which is a copy and not a second opinion."""
    program = {"statements": [
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"confidence": 0.2, "source": "a review"}},
        {"kind": "cause", "from": {"predicate": "y", "args": []},
         "to": {"predicate": "z", "args": []},
         "annotations": {"confidence": 0.9, "source": "a review"}},
    ]}
    verify({"confidence_sources": [
        {"slot_label": "edge:y->z", "source": "a review", "confidence": 0.9,
         "is_weakest": True}]}, program)


@pytest.mark.parametrize("envelope,program", [
    ({}, {"statements": []}),
    ({"confidence_sources": []}, {"statements": []}),
    ({"confidence_sources": "a"}, {"statements": []}),
    ({"confidence_sources": [None]}, {"statements": []}),
    ({"confidence_sources": [{"slot_label": "edge:x->y"}]}, {}),
    ({"confidence_sources": [{"slot_label": "edge:x->y"}]},
     {"statements": "a"}),
    ([], {"statements": []}),
    ({"confidence_sources": [{"slot_label": "edge:x->y"}]}, []),
])
def test_the_shapes_this_rule_says_nothing_about(envelope, program):
    """A document it cannot read is not a document it can refuse."""
    verify(envelope, program)


def test_a_statement_with_no_confidence_annotates_no_slot():
    """A source annotation without a confidence contributes nothing, so
    the slot it names is not one a row may be filed under."""
    program = {"statements": [
        {"kind": "cause", "from": {"predicate": "x", "args": []},
         "to": {"predicate": "y", "args": []},
         "annotations": {"source": "a review"}}]}
    with pytest.raises(VerificationError, match="annotates no such slot"):
        verify({"confidence_sources": [
            {"slot_label": "edge:x->y", "source": "a review",
             "confidence": 0.2, "is_weakest": True}]}, program)


# ------------------------------------------------------------- at the door


def test_the_rule_is_reached_through_the_public_door():
    """A rule nothing calls is a rule that holds nothing, and the sweep
    that measures coverage goes through the doors."""
    name = _carriers()[0]
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    forged["confidence_sources"][0]["slot_label"] = "edge:nowhere->nothing"
    with pytest.raises(VerificationError, match="annotates no such slot"):
        the_door_for(row["result"])(row["program"], forged)


def test_every_honest_answer_keeps_its_names_at_the_door():
    """The same denominator through the strongest door that reads it, so a
    rule that refuses an honest answer fails here rather than in the
    remainder sweep."""
    for name in _carriers():
        row = SHAPES[name]
        verify_honestly(row["program"], row["result"])
