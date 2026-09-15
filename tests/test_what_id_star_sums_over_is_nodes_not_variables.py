"""What ID* sums over is a set of counterfactual nodes, not of variables.

Line 6 of ID* writes ``P(γ') = Σ_{V(G')\\γ'} Π_i ID*(G, S^i_{v(G')\\S^i})``,
and every object in it is a node of the counterfactual graph: two copies of
one variable read in two worlds are two random variables. The engine had
turned three of those nodes into variables — a sum variable was named after
its variable, a sub-conjunction intervened on every other node's variable,
and the sum was attached to the branch with more than one c-component — and
each surfaced as an answer: a formula with a variable no sum binds, which the
kernel raised on, and a ``P(γ)=0`` that is not zero, given in some processes
and not others according to the order a set iterated in.

These tests hold the answers, not the mechanism's spelling: the same question
gets the same answer in every process, every answer that claims a number
computes it against models consistent with the graph, a single c-component
yields a formula the kernel and the verifier both accept, and the door still
refuses a zero the graph does not give.
"""
from __future__ import annotations

import collections
import copy
import dataclasses
import os
import pathlib
import random
import subprocess
import sys

import networkx as nx
import pytest

import themis
from themis.input.semantic_validator import validate_formula
from themis.kernel import run
from themis.runtime import ctf_identify as ci
from themis.runtime.ctf_identify import FAIL, ZERO, CtfEvent, id_star
from themis.types import Atom, ConstantExpr, SumExpr
from themis.verifier import VerificationError
from themis.verifier.semantic_probe import probe_counterfactual_formula

FORMULA_FLOOR = 180
ZERO_FLOOR = 35


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


def _graph(names, edges, bidirected):
    graph = nx.DiGraph()
    graph.add_nodes_from(A(p) for p in names)
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    return graph, frozenset(frozenset({A(u), A(v)}) for u, v in bidirected)


# c → b → d with a into both: P(d_{c=T}=T ∧ d_{c=F}=F) reads b in two worlds.
_MEDIATED = ("abcde", [("a", "b"), ("a", "d"), ("a", "e"), ("b", "d"), ("c", "b")], [("c", "e")])

# One c-component holding a node γ does not observe:
# P(c_{e=T,a=T}=T ∧ e=F).
_ONE_COMPONENT = ("abcde", [("a", "c"), ("b", "c"), ("d", "a"), ("d", "b")],
                  [("b", "c"), ("b", "e"), ("d", "e")])


def _mediated_pns():
    graph, bidirected = _graph(*_MEDIATED)
    gamma = (CtfEvent(A("d"), frozenset({(A("c"), True)}), True),
             CtfEvent(A("d"), frozenset({(A("c"), False)}), False))
    return graph, bidirected, gamma


def _one_component():
    graph, bidirected = _graph(*_ONE_COMPONENT)
    gamma = (CtfEvent(A("c"), frozenset({(A("e"), True), (A("a"), True)}), True),
             CtfEvent(A("e"), frozenset(), False))
    return graph, bidirected, gamma


def _conjunctions(x, y, w):
    hi, lo, factual = frozenset({(x, True)}), frozenset({(x, False)}), frozenset()
    return (
        (CtfEvent(y, hi, True), CtfEvent(x, factual, False)),
        (CtfEvent(y, hi, True), CtfEvent(y, lo, False)),
        (CtfEvent(y, hi, True), CtfEvent(w, factual, True)),
        (CtfEvent(y, frozenset({(x, True), (w, True)}), True), CtfEvent(x, factual, False)),
    )


def _random_problems(seed: int, graphs: int, size: int):
    rng = random.Random(seed)
    names = [A(p) for p in "abcdefg"[:size]]
    for _ in range(graphs):
        order = rng.sample(names, size)
        graph = nx.DiGraph()
        graph.add_nodes_from(order)
        graph.add_edges_from((u, v) for i, u in enumerate(order)
                             for v in order[i + 1:] if rng.random() < 0.4)
        bidirected = frozenset(frozenset((u, v)) for i, u in enumerate(order)
                               for v in order[i + 1:] if rng.random() < 0.2)
        i, j = sorted(rng.sample(range(size), 2))
        x, y = order[i], order[j]
        w = rng.choice([n for n in order if n not in (x, y)])
        for gamma in _conjunctions(x, y, w):
            yield graph, bidirected, gamma


def _no_sum_binds_a_name_twice(expr, bound=()):
    if isinstance(expr, SumExpr):
        assert expr.bind.name not in bound, (expr.bind.name, bound)
        bound = (*bound, expr.bind.name)
    for field in dataclasses.fields(expr):
        value = getattr(expr, field.name)
        for child in (value if isinstance(value, tuple) else (value,)):
            if dataclasses.is_dataclass(child) and not isinstance(child, type):
                _no_sum_binds_a_name_twice(child, bound)


def _ast(names, edges, bidirected, gamma):
    def atom(a):
        return {"predicate": a.predicate, "args": []}
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]} for p in names),
            *({"kind": "cause", "from": {"predicate": u, "args": []},
               "to": {"predicate": v, "args": []}} for u, v in edges),
            *({"kind": "bidirected", "left": {"predicate": u, "args": []},
               "right": {"predicate": v, "args": []}} for u, v in bidirected),
            {"kind": "query", "id": "q", "query": {
                "kind": "counterfactual_conjunction",
                "events": [{"variable": atom(e.variable),
                            "subscript": [{"atom": atom(a), "value": v}
                                          for a, v in sorted(e.subscript, key=lambda p: p[0].predicate)],
                            "value": e.value} for e in gamma]}},
        ],
    }


_ORDER_PROBE = """
import networkx as nx
from themis.runtime import ctf_identify as ci
from themis.types import Atom
A = lambda p: Atom(predicate=p, args=())
graph = nx.DiGraph()
graph.add_nodes_from(A(p) for p in "abcde")
graph.add_edges_from((A(u), A(v)) for u, v in [("a", "b"), ("a", "d"), ("a", "e"), ("b", "d"), ("c", "b")])
bidirected = frozenset({frozenset({A("c"), A("e")})})
gamma = (ci.CtfEvent(A("d"), frozenset({(A("c"), True)}), True),
         ci.CtfEvent(A("d"), frozenset({(A("c"), False)}), False))
out = ci.id_star(graph, bidirected, gamma)
print("FAIL" if out is ci.FAIL else "ZERO" if out is ci.ZERO else "formula")
"""


def test_one_question_gets_one_answer_whatever_order_a_set_iterates_in():
    """PNS through a mediator read in two worlds is not identifiable. It
    used to come back non-identifiable or ``P(γ)=0`` depending on the hash
    seed of the process asking — 0.094 on the model the data was drawn from."""
    graph, bidirected, gamma = _mediated_pns()
    assert id_star(graph, bidirected, gamma) is FAIL
    root = pathlib.Path(__file__).resolve().parents[1]
    answers = {}
    for seed in ("0", "1", "6", "7"):
        done = subprocess.run(
            [sys.executable, "-c", _ORDER_PROBE], cwd=root, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True)
        answers[seed] = done.stdout.strip()
    assert set(answers.values()) == {"FAIL"}, answers


def test_no_world_is_given_two_values_of_one_variable(monkeypatch):
    real = ci.make_cg
    worlds = []

    def recording(graph, bidirected, gamma):
        worlds.extend(e.subscript for e in gamma)
        return real(graph, bidirected, gamma)

    monkeypatch.setattr(ci, "make_cg", recording)
    for graph, bidirected, gamma in (_mediated_pns(), *_random_problems(6630, 60, 6)):
        id_star(graph, bidirected, gamma)
    twice = [w for w in worlds if len({a for a, _v in w}) < len(w)]
    assert worlds and not twice, twice[:3]


def test_two_copies_of_one_variable_are_summed_as_two_values():
    graph, bidirected, gamma = _mediated_pns()
    cf = ci.make_cg(graph, bidirected, gamma)
    values = ci._summed_values(cf, gamma)
    copies = [v.name for n, v in values.items() if n.variable == A("b")]
    assert len(copies) == 2 and len(set(copies)) == 2, copies

    outer = ci._SumVar(copies[0])
    carrying = (CtfEvent(A("e"), frozenset({(A("a"), outer)}), True),)
    renamed = ci._summed_values(cf, carrying)
    assert outer.name not in {v.name for v in renamed.values() if isinstance(v, ci._SumVar)}


def test_a_single_c_component_sums_the_nodes_it_does_not_observe():
    graph, bidirected, gamma = _one_component()
    formula = id_star(graph, bidirected, gamma)
    assert formula is not FAIL and formula is not ZERO
    validate_formula(formula)
    probe = probe_counterfactual_formula(graph, bidirected, gamma=gamma, formula=formula, k=3)
    assert probe.status == "match", probe.detail

    ast = _ast(*_ONE_COMPONENT, gamma)
    result = run(ast)["results"][0]
    assert result["status"] == "structurally_solved"
    themis.verify(ast, result)


def test_the_door_still_refuses_a_zero_the_graph_does_not_give():
    graph, bidirected, gamma = _one_component()
    ast = _ast(*_ONE_COMPONENT, gamma)
    honest = run(ast)["results"][0]
    themis.verify(ast, honest)
    forged = copy.deepcopy(honest)
    forged["formula"] = {"kind": "constant", "value": 0.0}
    forged["derivation"]["steps"][-1]["inputs"]["formula"] = {"kind": "constant", "value": 0.0}
    with pytest.raises(VerificationError):
        themis.verify(ast, forged)


def test_every_answer_that_claims_a_number_computes_it():
    """Random six-node ADMGs, four conjunctions each. A formula must bind
    every variable it uses and bind no name twice along a path; a formula or
    a ``P(γ)=0`` must match the counterfactual truth on sampled models."""
    seen = collections.Counter()
    for graph, bidirected, gamma in _random_problems(663, 100, 6):
        out = id_star(graph, bidirected, gamma)
        if out is FAIL:
            seen["FAIL"] += 1
            continue
        if out is ZERO:
            formula = ConstantExpr(value=0.0)
        else:
            formula = out
            validate_formula(formula)
            _no_sum_binds_a_name_twice(formula)
        probe = probe_counterfactual_formula(graph, bidirected, gamma=gamma, formula=formula)
        assert probe.status == "match", (gamma, probe.detail)
        seen["ZERO" if out is ZERO else "formula"] += 1
    assert FORMULA_FLOOR is not None and ZERO_FLOOR is not None, dict(seen)
    assert seen["formula"] > FORMULA_FLOOR and seen["ZERO"] > ZERO_FLOOR, dict(seen)
