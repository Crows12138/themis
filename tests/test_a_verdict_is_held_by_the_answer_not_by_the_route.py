"""A premise is not held by the route that happened to produce it.

``structural_result.value`` is one slot carrying ten propositions, and
which one is the question's to say. That is why auditing it belonged to
the ROUTE verifiers: only a verifier that knows which proposition was
claimed can re-derive it. But a route is chosen by the answer's status
word and the last rule of its chain, and neither of those is the
question.

So the audit of a premise came to depend on how far the run got past it.
An effect query that stopped at ``identify_via_mediation`` reaches
``verify_effect_structural``, which holds the verdict by equating it with
``derivation[-1].output``; the same query with data attached runs three
more steps and reaches ``verify_numeric``, which has no reason to read a
premise it does not use. Measured on the stored answers: of 125 carrying
a verdict, thirteen could be flipped and every door still accepted them —
eight that identified and then went on counting, five that took no route
at all.

The repair is not to widen the structural door, nor to copy the check
into thirty numeric rules and leave the hole open at the next estimator.
It is that an answer commits to identification in three places, and each
of them refuses a flip the others miss: the step that concluded it,
wherever in the chain it sits; a gap of the one declared kind that says
it failed; and a point estimate, which is what identification is for.
Nothing is re-derived — what this catches is an answer contradicting
itself.

What is asserted here:

- no stored answer is refused, at the rule and at the door that reads it
- the thirteen, chosen by the SHAPE that left them unheld rather than by
  name, are refused when flipped — at both public doors, because five of
  them have no chain and so meet the narrow one
- each of the three witnesses refuses on its own, and each is exercised
  by the corpus, so a witness that quietly stopped applying fails here
- the two questions whose verdict is not about a quantity are given no
  reading, and the field that says which those are is the questions' own
- the gap kind is read from the declared vocabulary and the point from
  the same reading the status word is held against, not a second one.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import questions
from themis.gaps import GapKind
from themis.verifier import VerificationError, status_rules, verdict_rules
from themis.verifier.verdict_rules import (
    _IDENTIFICATION_FAILED, _its_gaps_say_identification_failed,
    _the_steps_that_identified, verify_structural_verdict)

from .answer_corpus import the_door_for

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

RULE = "structural_verdict_check"

#: How many stored answers carry a verdict this rule can read, and how
#: many of them each witness applies to. Exact rather than a floor: a
#: witness the corpus stopped exercising is a witness nothing tests, and
#: it should say so here rather than pass quietly.
CARRYING_A_VERDICT = 125
WITH_THE_STEP_THAT_REACHED_IT = 33
WITH_A_GAP_SAYING_IT_FAILED = 2
WITH_A_POINT_ESTIMATE = 67

#: The two shapes that left a verdict unread, and what each came to. Not
#: a list of names: a fixture row's name is a digest of what its run
#: collected, so naming them would fossilise a re-collection away, and
#: the shape is the thing this rule is about anyway.
IDENTIFIED_THEN_WENT_ON_COUNTING = 8
TOOK_NO_ROUTE_AT_ALL = 5


def _verdict(result):
    block = result.get("structural_result")
    value = block.get("value") if isinstance(block, dict) else None
    return value if isinstance(value, bool) else None


def _steps(result):
    return (result.get("derivation") or {}).get("steps") or ()


def _a_point(result) -> bool:
    estimate = result.get("numeric_estimate") or {}
    outcome = result.get("numeric_result") or {}
    return (estimate.get("point") is not None
            or outcome.get("value") is not None)


def _flipped(result):
    other = copy.deepcopy(result)
    other["structural_result"]["value"] = not other["structural_result"]["value"]
    return other


CARRY = sorted(name for name in SHAPES
               if _verdict(SHAPES[name]["result"]) is not None)

#: The chains that reached the verdict and kept going, so the output the
#: structural door reads stopped being the last one.
WENT_ON = [name for name in CARRY
           if _the_steps_that_identified(SHAPES[name]["result"])
           and not str(_steps(SHAPES[name]["result"])[-1].get("rule", ""))
           .startswith("identify_via_")]

#: And the answers with no chain to read at all, which meet the narrow
#: door rather than the strong one.
NO_ROUTE = [name for name in CARRY
            if SHAPES[name]["result"].get("derivation") is None]


def test_the_corpus_still_carries_what_this_rule_reads():
    assert len(CARRY) == CARRYING_A_VERDICT


@pytest.mark.parametrize("name", CARRY)
def test_no_stored_answer_is_refused_by_the_rule(name):
    """Side one. A rule that refuses an honest answer is worse than the
    hole it closes, and these are the answers this system builds."""
    verify_structural_verdict(SHAPES[name]["result"])


@pytest.mark.parametrize("name", CARRY)
def test_no_stored_answer_is_refused_at_its_door(name):
    """And at the public door the rule now sits behind, which is where a
    refusal would actually reach a caller."""
    pair = SHAPES[name]
    the_door_for(pair["result"])(pair["program"], pair["result"])


def test_the_two_shapes_that_went_unheld_are_still_there():
    assert len(WENT_ON) == IDENTIFIED_THEN_WENT_ON_COUNTING
    assert len(NO_ROUTE) == TOOK_NO_ROUTE_AT_ALL


@pytest.mark.parametrize("name", WENT_ON)
def test_a_chain_that_identified_and_went_on_is_still_held(name):
    """The eight. Their identifying step is still in the chain; it is
    simply no longer the last, which is the only thing the structural
    door was looking at."""
    pair = SHAPES[name]
    with pytest.raises(VerificationError):
        the_door_for(pair["result"])(pair["program"], _flipped(pair["result"]))


@pytest.mark.parametrize("name", NO_ROUTE)
def test_a_verdict_with_no_chain_behind_it_is_still_held(name):
    """The five. No route was taken, so no route verifier was chosen, and
    the verdict was the one thing on the envelope nothing asked about."""
    pair = SHAPES[name]
    with pytest.raises(VerificationError):
        the_door_for(pair["result"])(pair["program"], _flipped(pair["result"]))


# --- the three witnesses, each on its own -------------------------------

def test_the_step_that_reached_the_verdict_refuses_a_different_one():
    with pytest.raises(VerificationError, match="this chain does not reach") as caught:
        verify_structural_verdict({
            "query_kind": "effect",
            "structural_result": {"kind": "structural_result", "value": False},
            "derivation": {"steps": [
                {"rule": "identify_via_mediation",
                 "output": {"kind": "structural_result", "value": True}},
                {"rule": "mediation_numeric_evaluate", "output": {}},
                {"rule": "numeric_result", "output": {}},
            ]},
        })
    assert caught.value.rule == RULE


def test_a_gap_saying_identification_failed_refuses_a_verdict_that_it_did():
    with pytest.raises(VerificationError, match="no admissible set") as caught:
        verify_structural_verdict({
            "query_kind": "effect",
            "structural_result": {"kind": "structural_result", "value": True},
            "missing_information": [
                {"gap": _IDENTIFICATION_FAILED, "kind": "structure"}],
        })
    assert caught.value.rule == RULE


def test_a_point_estimate_refuses_a_verdict_that_it_could_not_be_got():
    with pytest.raises(VerificationError, match="identification is what") as caught:
        verify_structural_verdict({
            "query_kind": "effect",
            "structural_result": {"kind": "structural_result", "value": False},
            "numeric_estimate": {"point": 0.4},
        })
    assert caught.value.rule == RULE


def test_the_step_witness_is_not_narrowed_to_the_questions_with_a_quantity():
    """A chain disagreeing with its own conclusion is wrong whatever was
    asked, so that witness is read before the question is."""
    with pytest.raises(VerificationError, match="this chain does not reach"):
        verify_structural_verdict({
            "query_kind": "cause",
            "structural_result": {"kind": "structural_result", "value": True},
            "derivation": {"steps": [
                {"rule": "identify_via_backdoor",
                 "output": {"kind": "structural_result", "value": False}}]},
        })


# --- each witness is exercised by the corpus ----------------------------

def test_every_witness_is_exercised_by_a_stored_answer():
    with_step = [n for n in CARRY
                 if _the_steps_that_identified(SHAPES[n]["result"])]
    with_gap = [n for n in CARRY
                if _its_gaps_say_identification_failed(SHAPES[n]["result"])]
    with_point = [n for n in CARRY if _a_point(SHAPES[n]["result"])]
    assert len(with_step) == WITH_THE_STEP_THAT_REACHED_IT
    assert len(with_gap) == WITH_A_GAP_SAYING_IT_FAILED
    assert len(with_point) == WITH_A_POINT_ESTIMATE


def test_each_of_the_thirteen_is_reached_by_a_witness():
    """And between them they cover it: no member of either shape is left
    to a door that is not there."""
    for name in WENT_ON + NO_ROUTE:
        result = _flipped(SHAPES[name]["result"])
        with pytest.raises(VerificationError):
            verify_structural_verdict(result)


# --- what the rule reads, and from where --------------------------------

def test_the_gap_kind_is_the_declared_one():
    """Ten needs raise it and spell their reasons ten ways; the kind is
    what they agree on, so it is read rather than spelt."""
    assert _IDENTIFICATION_FAILED == str(
        GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET)


def test_a_point_is_read_the_way_the_status_word_is_held_against():
    """One reading of the envelope, not two. What counts as a point is a
    fact about the envelope, and a second reading of it would be a second
    answer to one question."""
    assert verdict_rules._shown is status_rules._shown


def test_the_questions_whose_verdict_is_not_about_a_quantity_are_the_declared_two():
    assert {q.kind for q in questions.DECLARED
            if not q.names_an_estimand} == {"cause", "assoc"}


@pytest.mark.parametrize("kind", ["cause", "assoc"])
def test_no_reading_is_invented_for_a_verdict_about_a_graph(kind):
    """Their verdict says a path runs or two nodes are d-connected.
    Neither a gap about admissible sets nor a point estimate is a fact
    about that, and reading one into it is what declaring the field made
    unnecessary."""
    verify_structural_verdict({
        "query_kind": kind,
        "structural_result": {"kind": "structural_result", "value": False},
        "numeric_estimate": {"point": 0.4},
        "missing_information": [
            {"gap": _IDENTIFICATION_FAILED, "kind": "structure"}],
    })


def test_a_kind_this_build_does_not_carry_is_passed_over():
    """The schema's enum is where membership is asked; answering it here
    would be a second, weaker enum check in front of the real one."""
    verify_structural_verdict({
        "query_kind": "mediation_kind",
        "structural_result": {"kind": "structural_result", "value": False},
        "numeric_estimate": {"point": 0.4},
    })


@pytest.mark.parametrize("value", [None, "true", 1, {}])
def test_a_verdict_that_is_not_a_boolean_is_passed_over(value):
    """What may sit in the slot is the contract's question."""
    verify_structural_verdict({
        "query_kind": "effect",
        "structural_result": {"kind": "structural_result", "value": value},
        "numeric_estimate": {"point": 0.4},
    })


def test_an_answer_with_no_verdict_at_all_is_passed_over():
    verify_structural_verdict({"query_kind": "effect",
                               "numeric_estimate": {"point": 0.4}})
