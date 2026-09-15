"""A counterfactual answer is held to the counterfactual it says it is about.

``numeric_estimate.estimand`` is where an answer to a counterfactual
conjunction says in words which counterfactual its number belongs to. Nothing
read it: the rule that holds an answer's statement of its question to the
question reads each kind of question by the VARIABLES it names, and a
conjunction does not name its question by variables — it names it by events —
so the shape carrying the most detailed such statement was the one shape the
rule had no reading for. It has one now, transcribed on the verifier's side
rather than taken from the estimator that renders it, and the two spellings
are held to each other here.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError, verify_answer_names_its_question


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _ev(variable, held, value):
    return {"variable": {"predicate": variable, "args": []},
            "subscript": [{"atom": {"predicate": a, "args": []}, "value": v}
                          for (a, v) in held],
            "value": value}


def _ast(statements, events, condition=None):
    query = {"kind": "counterfactual_conjunction", "events": events}
    if condition is not None:
        query["condition"] = condition
    return {"version": "0.1", "domain": {"objects": []},
            "statements": [*statements, {"kind": "query", "id": "q", "query": query}]}


def _xy_program():
    return _ast([_var("x"), _var("y"), _cause("x", "y")],
                events=[_ev("y", [("x", True)], True)],
                condition=[_ev("x", [], False)])


def _two_interventions_program():
    return _ast([_var("x"), _var("m"), _var("y"),
                 _cause("x", "m"), _cause("m", "y"), _cause("x", "y")],
                events=[_ev("y", [("m", False), ("x", True)], True)])


def _xy_data(n=20000, seed=13):
    rng = np.random.default_rng(seed)
    x = rng.random(n) < 0.4
    y = np.where(x, rng.random(n) < 0.8, rng.random(n) < 0.2)
    return pd.DataFrame({"x": x, "y": y})


def _answer(program):
    return themis.estimate(program, _xy_data(), ci_bootstrap=0)["results"][0]


def test_an_honest_counterfactual_answer_is_accepted():
    program = _xy_program()
    themis.verify(program, _answer(program))


def test_an_answer_that_renames_the_counterfactual_it_is_about_is_refused():
    program = _xy_program()
    answer = _answer(program)
    assert answer["numeric_estimate"]["estimand"] == "P(y_{x=True}=True | x=False)"
    for forged in ("P(y_{x=False}=True | x=True)", "P(y=True)", "x"):
        renamed = copy.deepcopy(answer)
        renamed["numeric_estimate"]["estimand"] = forged
        with pytest.raises(VerificationError):
            themis.verify(program, renamed)


def test_a_subscript_holding_two_interventions_is_compared_not_declined():
    """The decline that lets a treatment course through is read off both
    values. Read off the shown one alone — a comma anywhere in it — this
    answer would be skipped for spelling its own subscript honestly."""
    program = _two_interventions_program()
    honest = "P(y_{m=False,x=True}=True)"
    verify_answer_names_its_question(
        {"estimand": honest}, program, query_id="q")
    with pytest.raises(VerificationError):
        verify_answer_names_its_question(
            {"estimand": "P(y_{m=True,x=False}=True)"}, program, query_id="q")


def test_the_verifier_spells_a_counterfactual_the_way_the_estimator_does():
    """Two transcriptions of one rendering, pinned to each other.

    The verifier does not call the estimator's renderer: a copy the producer
    hands over agrees with the producer by construction. What keeps the two
    honest is this.
    """
    from themis.estimation.ctf_conjunction import _render_estimand
    from themis.runtime.ctf_identify import CtfEvent
    from themis.types import Atom
    from themis.verifier.program_copy_rules import _conjunction_said

    def atom(name):
        return Atom(predicate=name, args=())

    def typed(variable, held, value):
        return CtfEvent(variable=atom(variable),
                        subscript=frozenset((atom(a), v) for a, v in held),
                        value=value)

    cases = (
        ([("y", [("x", True)], True)], []),
        ([("y", [("x", True)], True)], [("x", [], False)]),
        ([("y", [("m", False), ("x", True)], True)], []),
        ([("y", [("x", True)], True), ("y", [("x", False)], False)], []),
        ([("y", [], True)], [("x", [], True), ("z", [("d", False)], True)]),
    )
    for events, condition in cases:
        program = _ast([], [_ev(*e) for e in events], [_ev(*c) for c in condition])
        query = program["statements"][-1]["query"]
        gamma = tuple(typed(*e) for e in events)
        delta = tuple(typed(*c) for c in condition)
        assert _conjunction_said(query) == _render_estimand(gamma, delta)
