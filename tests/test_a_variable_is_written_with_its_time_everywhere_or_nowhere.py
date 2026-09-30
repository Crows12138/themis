"""A variable is written with its time index everywhere, or nowhere.

``x`` and ``x`` at a time step are two nodes of the graph with no edge
between them. The demo's model, asked "does a bad night's sleep before an
exam hurt it?", wrote the edges out of the night's sleep at t-1 into the
exam at t, and the edges into the sleep, the other causes of the exam and
the question itself without a time. The sleep the question named then had
no path to the exam it named: both interventional risks came out equal,
and the probabilities of causation refused the model's own
``P(exam | sleep)`` for contradicting them. Every layer read the graph it
was handed correctly; the program had one variable written as two.

The translation prompt already asks for a time index carried through to
every place a lagged variable appears. Nothing held a program to it.

Pinned here:

- a program writing a variable both with and without a time index is
  refused, and the refusal names every such variable at once with one of
  them in both spellings, so one round of repair can mend all of them;
- the shape that raised it is refused, and written with a time nowhere, or
  everywhere, it runs with the exposure a cause of the outcome;
- two time steps of one variable, and a variable without a time beside
  another with one, are not what it refuses;
- at the door, the split program goes back to the model with the refusal,
  and the mended program answers.
"""
from __future__ import annotations

import copy
import json

import pytest

import themis
from themis import language
from themis.input.semantic_validator import Malformed, SemanticError
from themis.web import llm_bridge

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from themis.web import app as app_module  # noqa: E402
from tests.test_a_program_the_kernel_refuses_is_handed_back_with_the_refusal import (  # noqa: E402
    _Model, _refused_turn)


def _at(name, t=None):
    atom = {"predicate": name, "args": [{"type": "const", "name": "me"}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _program(edges, cause, effect):
    names = sorted({a["predicate"] for edge in edges for a in edge})
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in names]
    statements += [{"kind": "cause", "from": u, "to": v} for u, v in edges]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "causation", "cause": cause, "effect": effect}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _night_before(sleep=None, exam=None, *, asked=(None, None)):
    """The shape the demo's model wrote: the edges out of the sleep at the
    times given, and everything else — the edges into the sleep, the rest of
    the exam's causes and the question — at the times in ``asked``."""
    return _program(
        [(_at("anxiety"), _at("sleep", asked[0])),
         (_at("anxiety"), _at("exam", asked[1])),
         (_at("sleep", sleep), _at("focus", exam)),
         (_at("focus", asked[1]), _at("exam", asked[1])),
         (_at("sleep", sleep), _at("exam", exam))],
        _at("sleep", asked[0]), _at("exam", asked[1]))


def _refusal(program):
    with pytest.raises(SemanticError) as caught:
        themis.run(copy.deepcopy(program))
    return caught.value


def _english(refusal):
    return language.assemble(refusal.species.words, refusal.said,
                             refusal.words, lang=language.Lang.EN)


# --- what is refused ---------------------------------------------------------

def test_the_shape_that_raised_it_is_refused_naming_every_variable_split():
    refusal = _refusal(_night_before(-1, 0))
    assert refusal.species is Malformed.ONE_VARIABLE_WITH_AND_WITHOUT_TIME
    assert refusal.details["variables"] == ["sleep(me)", "exam(me)", "focus(me)"]
    assert (refusal.details["untimed"], refusal.details["timed"]) == (
        "sleep(me)", "sleep(me)@t-1")
    statements = _night_before(-1, 0)["statements"]
    assert "time_index" not in statements[refusal.details["untimed_at"]]["to"]
    assert statements[refusal.details["timed_at"]]["from"]["time_index"] == {
        "kind": "relative", "value": -1}


def test_a_question_asked_without_the_time_its_variables_carry_is_refused():
    program = _program([(_at("sleep", -1), _at("exam", 0))],
                       _at("sleep"), _at("exam", 0))
    assert _refusal(program).details["variables"] == ["sleep(me)"]


# --- what is not -------------------------------------------------------------

def _risk_arms_differ(program):
    """Whether the exposure reaches the outcome on the graph the answer was
    reached on: the ask for the outcome's table conditions on it."""
    result = themis.run(copy.deepcopy(program))["results"][0]
    assert result["status"] == "needs_investigation", result["status"]
    return any("sleep" in item["name"].split("|", 1)[-1]
               and item["name"].startswith("parameter:P(exam")
               for item in result.get("missing_information") or ())


@pytest.mark.parametrize("times", [
    dict(sleep=None, exam=None, asked=(None, None)),
    dict(sleep=-1, exam=0, asked=(-1, 0)),
], ids=["nowhere", "everywhere"])
def test_written_one_way_throughout_the_exposure_reaches_the_outcome(times):
    assert _risk_arms_differ(_night_before(**times))


def test_two_time_steps_of_one_variable_are_two_nodes_on_purpose():
    program = _program(
        [(_at("sleep", -1), _at("sleep", 0)), (_at("sleep", -1), _at("exam", 0)),
         (_at("sleep", 0), _at("exam", 0))],
        _at("sleep", 0), _at("exam", 0))
    assert themis.run(program)["results"][0]["status"] == "needs_investigation"


def test_a_variable_without_a_time_beside_another_with_one_is_two_variables():
    program = _program(
        [(_at("anxiety"), _at("sleep", -1)), (_at("anxiety"), _at("exam", 0)),
         (_at("sleep", -1), _at("exam", 0))],
        _at("sleep", -1), _at("exam", 0))
    assert themis.run(program)["results"][0]["status"] == "needs_investigation"


# --- at the door -------------------------------------------------------------

def test_at_the_door_the_split_program_goes_back_and_the_mended_one_answers(
        monkeypatch):
    split, mended = _night_before(-1, 0), _night_before()
    stub = _Model(json.dumps(split), json.dumps(mended), "回答")
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
    r = TestClient(app_module.app).post(
        "/api/ask", json={"nl": "考前一晚没睡好会害我考砸吗", "lang": "zh"})
    assert r.status_code == 200, r.text
    assert r.json()["kernel_ast"] == mended
    assert _refused_turn(stub.sent[1]) == _english(_refusal(split))
