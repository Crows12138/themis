"""The value do() acts with is a fact of the action, not of what it changed.

A linear-SCM counterfactual is re-run by the verifier whole: abduction over
the variables the target reads once do(X) has cut X's in-edges, the action,
the prediction. Both producers show a reader that same set, and put the
value X was set to beside it. The verifier's world read that value back as
X's entry in the set -- which X has only when the target reads it. Where it
does not, the counterfactual is the unit's own observed value and the
arithmetic agreed, and the audit stopped on a KeyError: every one of 231
random counterfactuals whose target X does not reach, on the declared path,
and the same on the data-fitted one.
"""
from __future__ import annotations

import copy
import itertools
import random

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis import kernel
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(names, edges, observed, x, y, *, value=1.5, coefficients=True):
    statements = [{"kind": "variable", "predicate": n} for n in names]
    for a, b in edges:
        edge = {"kind": "cause", "from": _atom(a), "to": _atom(b)}
        if coefficients:
            edge["coefficient"] = 2.0
        statements.append(edge)
    statements += [{"kind": "observation", "atom": _atom(n), "value": v}
                   for n, v in observed.items()]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [{
                "kind": "query", "id": "q", "query": {
                    "kind": "scm_counterfactual",
                    "intervention": {"atom": _atom(x), "value": value},
                    "target": _atom(y)}}]}


UNIT = {"x": 1.0, "y": 3.0, "z": 0.5}
SHAPES = {
    "the target reads x": [("z", "y"), ("x", "y")],
    "x is downstream of the target": [("z", "y"), ("y", "x")],
    "x is beside the target": [("z", "y"), ("z", "x")],
}


def _declared(shape):
    return _program(("x", "y", "z"), SHAPES[shape], UNIT, "x", "y")


def _answer(program):
    return themis.run(program)["results"][0]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_kernels_counterfactual_is_accepted(shape):
    program = _declared(shape)
    answer = _answer(program)
    assert answer["status"] == "counterfactual_solved"
    if shape != "the target reads x":
        assert answer["numeric_result"]["value"] == UNIT["y"]
    kernel.verify(program, answer)


def _step_inputs(answer):
    return answer["derivation"]["steps"][-1]["inputs"]


def _block(answer):
    return answer["extensions"]["scm_counterfactual"]


TAMPERS = {
    "the step's intervention value":
        lambda a: _step_inputs(a).__setitem__("intervention_value", 4.0),
    "the block's intervention value":
        lambda a: _block(a)["intervention"].__setitem__("value", 4.0),
    "an entry for x the target does not read":
        lambda a: _block(a)["counterfactual_values"].__setitem__("x(me)", 1.5),
    "the block's answer":
        lambda a: _block(a).__setitem__("target_value", 4.0),
}


@pytest.mark.parametrize("tamper", sorted(TAMPERS))
@pytest.mark.parametrize("shape", ["x is downstream of the target",
                                   "x is beside the target"])
def test_what_the_answer_says_about_the_action_is_still_held(shape, tamper):
    program = _declared(shape)
    answer = copy.deepcopy(_answer(program))
    TAMPERS[tamper](answer)
    with pytest.raises(VerificationError):
        kernel.verify(program, answer)


def test_the_data_fitted_counterfactual_is_accepted_and_held():
    rng = np.random.default_rng(690)
    n = 50_000
    z = rng.standard_normal(n)
    y = 0.7 * z + rng.standard_normal(n)
    x = 1.3 * y + rng.standard_normal(n)
    program = _program(("x", "y", "z"), SHAPES["x is downstream of the target"],
                       UNIT, "x", "y", coefficients=False)
    answer = themis.estimate(program, pd.DataFrame({"z": z, "y": y, "x": x}),
                             ci_bootstrap=0, random_state=1)["results"][0]
    assert answer["status"] == "numerically_solved"
    assert answer["numeric_estimate"]["point"] == pytest.approx(UNIT["y"])
    kernel.verify(program, copy.deepcopy(answer))
    _block(answer)["intervention"]["value"] = 4.0
    with pytest.raises(VerificationError):
        kernel.verify(program, answer)


def _random_counterfactuals():
    rng = random.Random(690)
    names = ["a", "b", "c", "d", "e"]
    found = []
    while len(found) < 12:
        order = names[:]
        rng.shuffle(order)
        edges = [(order[i], order[j])
                 for i, j in itertools.combinations(range(5), 2)
                 if rng.random() < 0.4]
        x, y = rng.sample(names, 2)
        graph = nx.DiGraph(edges)
        graph.add_nodes_from(names)
        if x in nx.ancestors(graph, y):
            continue
        observed = {n: round(rng.uniform(-3, 3), 2) for n in names}
        found.append((tuple(edges), tuple(observed.items()), x, y))
    return found


@pytest.mark.parametrize("edges, observed, x, y", _random_counterfactuals())
def test_every_counterfactual_whose_target_x_does_not_reach_is_accepted(
        edges, observed, x, y):
    program = _program(["a", "b", "c", "d", "e"], edges, dict(observed), x, y)
    kernel.verify(program, _answer(program))
