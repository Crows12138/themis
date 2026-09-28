"""A sum over a variable of three values is audited at its three values.

The audit of an identified answer samples models consistent with the graph
and asks whether the estimand shown to the reader computes the true
interventional quantity in each (:mod:`themis.verifier.semantic_probe`). It
samples each variable over the values the problem gives it, builds the
conditionals the estimand asks for from the sampled model, and evaluates
the estimand on them. The store it evaluated on carried no values of its
own, so a sum ranged over true and false whatever the model was sampled
over: an estimand summing over a confounder declared at three values asked
for it at ``True``, found nothing, and the audit refused an answer it had
just been handed the right numbers for. Found on the demo, on a question
whose every variable the model had declared at three levels.
"""
from __future__ import annotations

import networkx as nx
import pytest

import themis
from themis.types import (Atom, BindDecl, ConstTerm, ProbabilityRefExpr,
                          ProductExpr, SumExpr, ValuedAtom, VarRef)
from themis.verifier.semantic_probe import probe_identify_formula

LEVELS = ["low", "mid", "high"]


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _cell(target, value, given, p):
    return {"kind": "probability", "target": {"atom": _atom(target), "value": value},
            "given": [{"atom": _atom(g), "value": v} for g, v in given], "value": p}


P_Z = {"low": 0.2, "mid": 0.5, "high": 0.3}
P_X = {"low": 0.3, "mid": 0.5, "high": 0.8}
P_Y = {(True, "low"): 0.4, (True, "mid"): 0.5, (True, "high"): 0.7,
       (False, "low"): 0.1, (False, "mid"): 0.2, (False, "high"): 0.4}


def _program():
    """x → y confounded by z, which takes three values, every number stated."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": LEVELS},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            *(_cell("z", z, [], p) for z, p in P_Z.items()),
            *(_cell("x", True, [("z", z)], p) for z, p in P_X.items()),
            *(_cell("y", True, [("x", x), ("z", z)], p) for (x, z), p in P_Y.items()),
            {"kind": "query", "id": "q", "query": {
                "kind": "effect", "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True}, "given": []}},
        ],
    }


def test_an_answer_adjusting_for_it_is_accepted():
    program = _program()
    result = themis.run(program)["results"][0]
    assert result["status"] == "numerically_solved"
    want = sum(P_Z[z] * P_Y[(True, z)] for z in LEVELS)
    assert result["numeric_result"]["value"] == pytest.approx(want, abs=1e-12)
    themis.verify(program, result)


ME = (ConstTerm("me"),)
X, Y, Z = (Atom(p, ME) for p in "xyz")


def _graph():
    return nx.DiGraph([(Z, X), (Z, Y), (X, Y)])


ADJUSTED = SumExpr(
    bind=BindDecl("z"), over=Z,
    body=ProductExpr((
        ProbabilityRefExpr(target=ValuedAtom(Y, True),
                           given=(ValuedAtom(X, True), ValuedAtom(Z, VarRef("z")))),
        ProbabilityRefExpr(target=ValuedAtom(Z, VarRef("z")), given=()),
    )))
UNADJUSTED = ProbabilityRefExpr(target=ValuedAtom(Y, True),
                                given=(ValuedAtom(X, True),))


@pytest.mark.parametrize("formula, verdict", [
    (ADJUSTED, "match"), (UNADJUSTED, "mismatch"),
], ids=["the adjustment", "no adjustment"])
def test_the_probe_samples_and_sums_over_the_same_three_values(formula, verdict):
    """Not a probe silenced: the adjustment over z's three values matches
    the sampled truth, and leaving it out is still caught."""
    got = probe_identify_formula(
        _graph(), frozenset(), x=X, x_value=True, y=Y, given=(),
        formula=formula, domains={X: (True, False), Y: (True, False),
                                  Z: tuple(LEVELS)},
        y_values=(True,))
    assert got.status == verdict, got.detail
