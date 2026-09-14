"""A conditional estimate is about the stratum its question names.

An effect question can be conditioned on a stratum -- its ``given`` -- and a
conditional plug-in writes that stratum back on the estimate as
``given: [[predicate, value], ...]``. ``frame_rules._ASKED_VALUES`` holds each
value a numeric block shows back against the value the question named, and
held the target's and the intervention's but not the stratum's: on the two
corpus answers carrying it, both halves of every pair could be rewritten and
the door took them. A contrast taken within another stratum re-derives to
itself from its own records all the same.

What is held is a stratum that is written. An answer whose route writes none
is not refused for writing none: the back-door route answers a conditional
question without the field, and holding its absence would refuse that.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier.errors import VerificationError
from themis.verifier.frame_rules import _ASKED_VALUES

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES
    if "given" in (SHAPES[n]["result"].get("numeric_estimate") or {}))


def _question(name):
    result = SHAPES[name]["result"]
    return next(s["query"] for s in SHAPES[name]["program"]["statements"]
                if s.get("kind") == "query" and s.get("id") == result.get("query_id"))


def test_the_corpus_writes_a_stratum_on_two_answers_and_each_is_the_question_s():
    assert len(CARRIERS) == 2, CARRIERS
    for name in CARRIERS:
        written = SHAPES[name]["result"]["numeric_estimate"]["given"]
        assert written == _ASKED_VALUES["effect"]["given"](_question(name))
        program, result = SHAPES[name]["program"], copy.deepcopy(SHAPES[name]["result"])
        the_door_for(result)(program, result)


def _lies(written):
    (predicate, value), = written
    return {
        "another value": [[predicate, not value]],
        "another variable": [["x" if predicate != "x" else "y", value]],
        "a second condition": [[predicate, value], ["y", value]],
        "no condition written": [],
        "the value as a number": [[predicate, int(value)]],
    }


@pytest.mark.parametrize("lie", sorted(_lies([["c", True]])))
@pytest.mark.parametrize("name", CARRIERS)
def test_a_stratum_the_question_did_not_name_is_refused(name, lie):
    program, result = SHAPES[name]["program"], copy.deepcopy(SHAPES[name]["result"])
    estimate = result["numeric_estimate"]
    estimate["given"] = _lies(estimate["given"])[lie]
    with pytest.raises(VerificationError, match="given"):
        the_door_for(result)(program, result)
