"""How far an answer trusts its inputs, against the inputs it trusted.

Two fields reach a reader together: ``confidence``, which is how far this
run trusts what it was given, and ``confidence_sources``, the slots it was
taken over. What binds them is declared where the pair is declared --
``ConfidenceSource`` says the composite is ``min`` across the non-None slot
confidences, and its ``is_weakest`` field says true iff that source sits at
that minimum -- and the verifier read neither. The one rule with the word
in its name is about the LEVEL an interval is stated at, which is a
different fact wearing the same letters.

What is asserted here:

- no honest answer is refused, at the strongest door that reads it, and
  the corpus really does exercise the rule -- a claim nothing satisfies is
  a claim that could be anything
- each half refuses the forgery it exists for: a composite that is not the
  minimum, and a mark that points at a slot which is not the weakest or
  away from one that is
- a tie marks every source at the minimum, which is what the flag means
  and what the producer writes
- the rule is silent where the shape is not one this system writes: a
  composite standing alone, sources that are not a list of mappings, a
  confidence that is not a number
- it is reached through the public door and not only when called directly
- the sentences name the numbers a reader would have been looking at.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis.verifier import VerificationError
from themis.verifier.confidence_source_rules import (
    _RULE, verify_the_composite_is_its_weakest_source as verify)

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: How many stored answers carry the pair. Named, because a rule the corpus
#: stopped exercising would otherwise go quiet without saying so.
ANSWERS_CARRYING_A_COMPOSITE = 3


def _carriers():
    return sorted(
        name for name, row in SHAPES.items()
        if row["result"].get("confidence") is not None
        and row["result"].get("confidence_sources"))


def test_the_corpus_exercises_this_rule():
    names = _carriers()
    assert len(names) == ANSWERS_CARRYING_A_COMPOSITE, names
    for name in names:
        verify(SHAPES[name]["result"])


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    """The denominator: every stored answer, through the rule."""
    verify(SHAPES[shape]["result"])


def test_a_composite_below_its_weakest_source_is_refused():
    """The number a reader takes as how far to trust the answer, moved
    down: the answer is shown as shakier than anything it rests on."""
    envelope = {"confidence": 0.1, "confidence_sources": [
        {"slot_label": "edge:x->y", "confidence": 0.6, "is_weakest": True}]}
    with pytest.raises(VerificationError, match="weakest of the") as err:
        verify(envelope)
    assert err.value.rule == _RULE


def test_a_composite_above_its_weakest_source_is_refused():
    """And moved up, which is the forgery that matters: a reader is told
    the answer is trusted further than its weakest input."""
    envelope = {"confidence": 0.9, "confidence_sources": [
        {"slot_label": "a", "confidence": 0.9, "is_weakest": True},
        {"slot_label": "b", "confidence": 0.2, "is_weakest": True}]}
    with pytest.raises(VerificationError, match="trusted further") as err:
        verify(envelope)
    assert err.value.rule == _RULE


def test_a_mark_on_a_source_that_is_not_the_weakest_is_refused():
    envelope = {"confidence": 0.2, "confidence_sources": [
        {"slot_label": "a", "confidence": 0.7, "is_weakest": True},
        {"slot_label": "b", "confidence": 0.2, "is_weakest": True}]}
    with pytest.raises(VerificationError, match="is_weakest=True") as err:
        verify(envelope)
    assert err.value.rule == _RULE
    assert "'a'" in str(err.value)


def test_a_weak_link_left_unmarked_is_refused():
    """The other direction, and the one a reader loses by: the mark is
    what they follow to the link the answer is weakest at."""
    envelope = {"confidence": 0.2, "confidence_sources": [
        {"slot_label": "a", "confidence": 0.7, "is_weakest": False},
        {"slot_label": "b", "confidence": 0.2, "is_weakest": False}]}
    with pytest.raises(VerificationError, match="is_weakest=False") as err:
        verify(envelope)
    assert err.value.rule == _RULE


def test_a_tie_marks_every_source_at_the_minimum():
    """What the flag means, and what the producer writes: two slots at the
    same lowest number are both the weak link."""
    verify({"confidence": 1.0, "confidence_sources": [
        {"slot_label": "a", "confidence": 1.0, "is_weakest": True},
        {"slot_label": "b", "confidence": 1.0, "is_weakest": True}]})
    with pytest.raises(VerificationError):
        verify({"confidence": 1.0, "confidence_sources": [
            {"slot_label": "a", "confidence": 1.0, "is_weakest": True},
            {"slot_label": "b", "confidence": 1.0, "is_weakest": False}]})


def test_the_mark_is_a_flag_and_a_word_is_not_one():
    """``"true"`` is not ``True``, and a reader's eye would not tell them
    apart. The schema refuses it too; a rule that compared truthiness
    would agree with the forgery."""
    with pytest.raises(VerificationError):
        verify({"confidence": 0.5, "confidence_sources": [
            {"slot_label": "a", "confidence": 0.5, "is_weakest": "true"}]})


def test_a_flag_where_a_confidence_goes_is_not_a_confidence():
    """A ``bool`` is an ``int`` in this language, so a flag left in a
    confidence slot would compare as 0 or 1 and pass for a probability."""
    verify({"confidence": 0.5, "confidence_sources": [
        {"slot_label": "a", "confidence": True, "is_weakest": True}]})


@pytest.mark.parametrize("envelope", [
    {"confidence": 0.5},
    {"confidence": 0.5, "confidence_sources": []},
    {"confidence": None, "confidence_sources": [
        {"slot_label": "a", "confidence": 0.5, "is_weakest": True}]},
    {"confidence": 0.5, "confidence_sources": {"a": 0.5}},
    {"confidence": 0.5, "confidence_sources": "a"},
    {"confidence": 0.5, "confidence_sources": [None]},
    {"confidence": 0.5, "confidence_sources": [{"slot_label": "a"}]},
    {},
    [],
])
def test_the_shapes_this_rule_says_nothing_about(envelope):
    """A composite standing alone is not an envelope this system writes --
    the composite of nothing is None, and one pass writes both fields
    together -- so refusing it would be a claim about an answer no run
    produces. The rest are not the shape at all."""
    verify(envelope)


def _a_carrier_that_does_not_print_its_confidence() -> str:
    """A carrier whose report does not also QUOTE the composite.

    An answer whose confidence fell below the threshold says so in a gap,
    and that sentence carries the number already formatted -- so on such
    an answer a moved composite is refused by the rule holding the
    printing to the record, one check before this one. Both refusals are
    right and they are about different things: that one asks whether the
    sentence a reader is handed matches the record, this one asks whether
    the record is the weakest of the sources it was composed from. Taking
    the first carrier alphabetically let the earlier rule answer for this
    one, which is a test that stops witnessing what it is named after.
    """
    for name in _carriers():
        report = json.dumps(SHAPES[name]["result"].get("data_gap_report")
                            or {}, ensure_ascii=False)
        if "the_composite_confidence_is_below_the_threshold" not in report:
            return name
    raise AssertionError("every carrier now quotes its own composite")


def test_the_rule_is_reached_through_the_public_door():
    """A rule nothing calls is a rule that holds nothing, and the sweep
    that measures coverage goes through the doors."""
    name = _a_carrier_that_does_not_print_its_confidence()
    honest = SHAPES[name]["result"]
    forged = copy.deepcopy(honest)
    forged["confidence"] = 0.123
    with pytest.raises(VerificationError, match="weakest of the"):
        the_door_for(honest)(SHAPES[name]["program"], forged)


def test_a_quoted_composite_is_answered_for_by_the_printing_rule():
    """And the carrier left out is left out for a reason that holds.

    Stated rather than assumed: on an answer that quotes its composite,
    moving the composite IS refused -- by the other rule, naming the
    printing. Neither of the two is silent here; they simply speak in the
    order they are asked.
    """
    quoted = [name for name in _carriers()
              if "the_composite_confidence_is_below_the_threshold"
              in json.dumps(SHAPES[name]["result"].get("data_gap_report")
                            or {}, ensure_ascii=False)]
    assert quoted, "no carrier quotes its composite any more"
    for name in quoted:
        honest = SHAPES[name]["result"]
        forged = copy.deepcopy(honest)
        forged["confidence"] = 0.123
        with pytest.raises(VerificationError, match="prints"):
            the_door_for(honest)(SHAPES[name]["program"], forged)


def test_every_honest_answer_keeps_its_composite_at_the_door():
    """The same denominator through the strongest door that reads it, so a
    rule that refuses an honest answer fails here rather than in the
    remainder sweep."""
    for name in _carriers():
        row = SHAPES[name]
        verify_honestly(row["program"], row["result"])
