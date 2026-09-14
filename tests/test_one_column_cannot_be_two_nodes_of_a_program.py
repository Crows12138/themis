"""A column of data is one node of the program.

The estimation layer is handed a frame with one column per variable and
reads a graph node off the column its predicate names. On a program
unrolled in time a variable has a node per step, so a confounder a step
back of the outcome -- y at t-1 into x at t and into y at t -- was adjusted
for as column ``y``, the outcome itself. Every ATE estimator returned a
number near zero for an effect of 0.3, recorded columns that agree with
themselves, and passed the door. A step back of the treatment was refused
for having no contrast within strata of the treatment: the same collision,
read the other way.

The frame cannot say which node a column holds. Where the program has
several nodes of a variable the frame supplies, the frame is refused at the
contract, naming the column and its nodes; and an answer that says a frame
was accepted for such a program is refused at the door.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.contract import DataContractError
from themis.estimation.refusal_words import Refuses
from themis.kernel import _premises_of
from themis.verifier import verify_a_column_is_one_node
from themis.verifier.errors import VerificationError
from tests.answer_corpus import the_door_for


def _at(p, t=None, who="u"):
    atom = {"predicate": p, "args": [{"type": "const", "name": who}]}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _program(edges, x, y, *, objects=("u",), extra=()):
    names = sorted({a["predicate"] for e in edges for a in e})
    st = [{"kind": "variable", "predicate": p, "domain": [0, 1]} for p in names]
    st += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    st += list(extra)
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": x, "value": 1},
        "target": {"atom": y, "value": 1}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": o} for o in objects]},
            "statements": st}


def _a_step_back(lagged, estimator=None):
    program = _program(
        [(_at(lagged, -1), _at("x", 0)), (_at(lagged, -1), _at("y", 0)),
         (_at("x", 0), _at("y", 0))],
        _at("x", 0), _at("y", 0))
    if estimator is not None:
        program["options"] = {"ate_estimator": estimator}
    return program


@pytest.fixture(scope="module")
def draws():
    """The confounder a step back, the treatment and the outcome now; the
    effect of the treatment on the outcome's risk is +0.3."""
    rng = np.random.default_rng(7)
    n = 4000
    lag = rng.binomial(1, 0.5, n)
    x = rng.binomial(1, 0.2 + 0.6 * lag)
    y = rng.binomial(1, 0.1 + 0.3 * x + 0.4 * lag)
    return lag, x, y


def _answer(program, frame):
    return next(r for r in themis.estimate(program, frame, ci_bootstrap=0,
                                           random_state=1)["results"]
                if r.get("query_id") == "q")


def test_a_confounder_with_a_column_of_its_own_is_estimated(draws):
    lag, x, y = draws
    program = _a_step_back("z")
    result = _answer(program, pd.DataFrame({"z": lag, "x": x, "y": y}))
    assert result["numeric_estimate"]["point"] == pytest.approx(0.3, abs=0.08)
    the_door_for(result)(program, result)


@pytest.mark.parametrize("estimator", [None, "ipw", "aipw", "tmle"])
@pytest.mark.parametrize("lagged", ["x", "y"])
def test_a_variable_with_two_nodes_is_refused_at_the_contract(draws, lagged,
                                                              estimator):
    _, x, y = draws
    with pytest.raises(DataContractError) as raised:
        _answer(_a_step_back(lagged, estimator), pd.DataFrame({"x": x, "y": y}))
    assert raised.value.species is Refuses.A_COLUMN_WOULD_HOLD_SEVERAL_NODES
    assert raised.value.details["column"] == lagged
    assert raised.value.details["nodes"] == [f"{lagged}(u)@t", f"{lagged}(u)@t-1"]


def test_a_variable_of_two_objects_is_two_nodes_too(draws):
    lag, x, y = draws
    edges = [(_at(a, who=o), _at(b, who=o)) for o in ("p", "q")
             for a, b in (("z", "x"), ("z", "y"), ("x", "y"))]
    program = _program(edges, _at("x", who="p"), _at("y", who="p"),
                       objects=("p", "q"))
    with pytest.raises(DataContractError) as raised:
        _answer(program, pd.DataFrame({"z": lag, "x": x, "y": y}))
    assert raised.value.details == {"column": "x", "nodes": ["x(p)", "x(q)"]}


def test_the_missing_data_branch_is_asked_first(draws):
    """A program declaring missingness goes to its own estimator, which
    reads columns by predicate the same way; the frame is refused before
    either branch."""
    _, x, y = draws
    program = _program(
        [(_at("y", -1), _at("x", 0)), (_at("y", -1), _at("y", 0)),
         (_at("x", 0), _at("y", 0))],
        _at("x", 0), _at("y", 0),
        extra=[{"kind": "missingness_indicator", "id": "R_y",
                "missing_var": _at("y", 0), "caused_by": [_at("y", -1)]}])
    frame = pd.DataFrame({"x": x, "y": np.where(np.arange(len(y)) % 7 == 0,
                                                np.nan, y)})
    with pytest.raises(DataContractError) as raised:
        _answer(program, frame)
    assert raised.value.species is Refuses.A_COLUMN_WOULD_HOLD_SEVERAL_NODES


def test_the_door_refuses_a_frame_accepted_for_such_a_program(draws):
    """The honest answer with a column per variable, handed over beside the
    program whose confounder is the outcome a step back."""
    lag, x, y = draws
    result = _answer(_a_step_back("z"), pd.DataFrame({"z": lag, "x": x, "y": y}))
    lagged = _a_step_back("y")
    with pytest.raises(VerificationError, match="one column cannot be all of them"):
        the_door_for(result)(lagged, result)


def test_an_answer_that_accepted_no_frame_makes_no_claim_about_one(draws):
    program = _a_step_back("y")
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == "q")
    assert "data_columns" not in (result.get("estimation_context") or {})
    _, _, _, ctx = _premises_of(program, result)
    verify_a_column_is_one_node(result, ctx.graph)
    forged = copy.deepcopy(result)
    forged["estimation_context"] = {"data_columns": ["x", "y"]}
    with pytest.raises(VerificationError, match="several nodes of that variable"):
        verify_a_column_is_one_node(forged, ctx.graph)
