"""The words an answer uses to describe what it achieved.

Three of them sit above everything else a reader sees: which question this
answers, what became of it, and what answer is still available. They were
held by nothing, and the reason is the same for all three — every rule
that could catch a lie about them is SELECTED by them. ``verify`` routes
on ``query_kind`` and on ``status``; every rule that touches the gap report
reads the gaps and none reads the word those gaps add up to. A field that
chooses the audit is a premise of the audit until somebody holds it.

They stayed invisible twice over. The census could tell an enum leaf only
one lie — a word outside its vocabulary — and validation refuses that
before a rule reads it, so all three scored as held without anything ever
asking which member they were.

WHAT IS HELD HERE AND WHAT IS NOT.

``query_kind`` is held to the program, which is the strongest record there
is: an answer may not edit the question it was asked. Every other kind is
refused, on every row.

``answer_tier`` is held only where the word is true whichever pass wrote
it. It has two authors — computed once at identification time from the
question, the status, the gap species and the interval in hand, then
written again by the estimation layer reconciling it to the number just
produced — and recomputing the first author's function refuses six honest
answers in this corpus, because on those the second author had the last
word. So what is held is: a question that names no quantity has no tier; a
question that names one has a tier; a point is not promised where the
envelope says the point is out of reach; and "no answer available" is not
said over an interval that is sitting there. The rest waits for the
frontier where the two authors become one, and the remainder is measured
below rather than described.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis import questions
from themis.verifier.data_gap_rules import (
    _HAS_INTERVAL_FALLBACK, _NAMES_AN_ESTIMAND, _an_interval_is_in_hand,
    _the_point_is_blocked, verify_answer_tier,
)
from themis.verifier.errors import VerificationError
from themis.verifier.program_copy_rules import verify_answer_names_its_kind

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
CONTRACT = json.loads(
    (pathlib.Path(__file__).parent.parent / "themis" / "schemas"
     / "query_result.schema.json").read_text(encoding="utf-8"))

KINDS = tuple(CONTRACT["properties"]["query_kind"]["enum"])
TIERS = ("point", "interval", "none")

WITH_TIER = sorted(
    n for n in SHAPES
    if isinstance(SHAPES[n]["result"].get("data_gap_report"), dict)
    and SHAPES[n]["result"]["data_gap_report"].get("answer_tier") is not None)


def _pair(name):
    pair = SHAPES[name]
    return pair["program"], copy.deepcopy(pair["result"])


# --------------------------------------------- the rosters, against theirs


def test_which_questions_name_a_quantity_is_the_readings_answer():
    """Both restated rosters against ``themis.questions``.

    Restated rather than imported for the reason every table in the
    verifier package is: a rule that reads the producer's own roster
    agrees with it by construction and has nothing to say when the roster
    changes. What makes that safe is this comparison — a new query kind
    arrives as a red suite rather than as a tier nothing reads.
    """
    assert _NAMES_AN_ESTIMAND == {
        k for k in KINDS if questions.reading_of(k).names_an_estimand}
    assert _HAS_INTERVAL_FALLBACK == {
        k for k in KINDS
        if questions.reading_of(k).interval_fallback is not None}
    assert _HAS_INTERVAL_FALLBACK < _NAMES_AN_ESTIMAND


# ------------------------------------------------ nothing honest is refused


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_no_honest_answer_is_refused(name):
    """First, because a rule that refuses an honest answer is worse than
    the hole it closes — and these two read fields every answer carries."""
    verify_honestly(*_pair(name))


# ------------------------------------------------------------- query_kind


def test_an_answer_may_not_say_it_answers_another_question():
    """Every other kind, on every row, at the door that reads that row."""
    refused = 0
    for name in sorted(SHAPES):
        program, result = _pair(name)
        shown = result.get("query_kind")
        assert isinstance(shown, str), name
        door = the_door_for(SHAPES[name]["result"])
        for other in KINDS:
            if other == shown:
                continue
            program, result = _pair(name)
            result["query_kind"] = other
            with pytest.raises(Exception):
                door(program, result)
            refused += 1
    assert refused == 2187


def test_the_kind_is_refused_by_this_rule_and_not_only_by_the_routing():
    """What the caller gets is a refusal; what this test says is which
    rule gave it.

    Routing on a changed kind refuses much of the time by accident — the
    branch it lands in asks for a block this answer does not carry. That
    is a refusal for the wrong reason, and it disappears the moment two
    kinds happen to want the same blocks.
    """
    asked = 0
    for name in sorted(SHAPES):
        program, result = _pair(name)
        shown = result["query_kind"]
        for other in KINDS:
            if other == shown:
                continue
            program, result = _pair(name)
            result["query_kind"] = other
            with pytest.raises(VerificationError, match="the question asked"):
                verify_answer_names_its_kind(result, program)
            asked += 1
    assert asked == 2187


# ------------------------------------------------------------ answer_tier


def test_a_question_that_names_no_quantity_is_given_no_tier():
    """And one that names a quantity is not left without one."""
    without = [n for n in SHAPES
               if not questions.reading_of(
                   SHAPES[n]["result"]["query_kind"]).names_an_estimand
               and isinstance(SHAPES[n]["result"].get("data_gap_report"), dict)]
    assert without, "no row asks a question that names no quantity"
    for name in without:
        program, result = _pair(name)
        result["data_gap_report"]["answer_tier"] = "point"
        with pytest.raises(VerificationError, match="promise about nothing"):
            verify_answer_tier(result, program)

    for name in WITH_TIER[:20]:
        program, result = _pair(name)
        result["data_gap_report"]["answer_tier"] = None
        with pytest.raises(VerificationError, match="nobody said"):
            verify_answer_tier(result, program)


def test_a_point_is_not_promised_where_the_point_is_out_of_reach():
    blocked = [n for n in WITH_TIER
               if _the_point_is_blocked(SHAPES[n]["result"],
                                        SHAPES[n]["program"])]
    assert blocked, "no row carries a blocking signal"
    for name in blocked:
        program, result = _pair(name)
        result["data_gap_report"]["answer_tier"] = "point"
        with pytest.raises(VerificationError, match="out of reach"):
            verify_answer_tier(result, program)


def test_no_answer_available_is_not_said_over_an_interval():
    holding = [n for n in WITH_TIER
               if _an_interval_is_in_hand(SHAPES[n]["result"])]
    assert holding, "no row carries an interval"
    for name in holding:
        program, result = _pair(name)
        result["data_gap_report"]["answer_tier"] = "none"
        with pytest.raises(VerificationError, match="give up"):
            verify_answer_tier(result, program)


def test_what_the_tier_rule_does_not_reach_is_exactly_its_two_questions():
    """The remainder, computed rather than described.

    Every surviving bend is one neither invariant is about: it does not
    promise a point where the envelope says the point is blocked, and it
    does not say "none" over an interval. That is the shape of what is
    left, and it is left because the word has two authors — not because
    nobody looked.
    """
    survived, refused = [], 0
    for name in WITH_TIER:
        was = SHAPES[name]["result"]["data_gap_report"]["answer_tier"]
        door = the_door_for(SHAPES[name]["result"])
        for other in TIERS:
            if other == was:
                continue
            program, result = _pair(name)
            result["data_gap_report"]["answer_tier"] = other
            try:
                door(program, result)
            except Exception:
                refused += 1
            else:
                survived.append((name, was, other))
    assert refused == 120
    assert len(survived) == 350
    for name, _was, other in survived:
        result, program = SHAPES[name]["result"], SHAPES[name]["program"]
        assert not (other == "point" and _the_point_is_blocked(result, program))
        assert not (other == "none" and _an_interval_is_in_hand(result))
