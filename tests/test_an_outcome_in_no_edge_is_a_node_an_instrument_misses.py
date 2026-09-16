"""The two ends a question names are nodes of the graph it asks, an edge or none.

Balke-Pearl bounds name the instrument they were fitted around, and the
audit holds that name to what the graph offers: an edge into the treatment,
and no open path to the outcome once the treatment's outgoing edges are
cut. The audit reads that graph off the program's cause and bidirected
statements itself, so a declared variable no statement mentions was no node
of it, and an outcome that was no node offered nothing. An outcome in no
edge is the easiest one for an instrument to keep no open path to, and the
producer's projection holds it as a node since the question names it. So
every honest row the kernel wrote for such an outcome was refused: on 400
random six-variable programs, 19 of the kernel's answers, each one a
Balke-Pearl row beside an outcome in no edge, and none of the others.
"""
from __future__ import annotations

import copy
import itertools
import random

import pytest

import themis
from tests.answer_corpus import verify_honestly
from tests.bounds_rows import row
from themis.verifier.bounds_rules import (
    _graph_instrument_candidates,
    verify_balke_pearl_iv_bounds_result,
)
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(names, edges, x, y):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in names]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [{
                "kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom(x), "value": True},
                    "target": {"atom": _atom(y), "value": True},
                    "given": []}}]}


def _in_no_edge(names=("z", "x", "y"), edges=(("z", "x"),)):
    """z -> x, and y declared with no edge."""
    return _program(names, edges, "x", "y")


def _audit(program, bounds):
    verify_balke_pearl_iv_bounds_result(
        bounds, program=program,
        query_dict=program["statements"][-1]["query"])


@pytest.mark.parametrize("names, edges, offered", [
    (("z", "x", "y"), (("z", "x"),), {"z"}),
    (("z", "w", "x", "y"), (("z", "x"), ("w", "x")), {"z", "w"}),
    (("z", "x", "y"), (("z", "x"), ("x", "y")), {"z"}),
], ids=["one", "two", "the outcome with an edge, as before"])
def test_the_graph_offers_an_instrument_for_an_outcome_in_no_edge(
        names, edges, offered):
    assert _graph_instrument_candidates(
        _in_no_edge(names, edges), treatment="x", outcome="y") == offered


def test_the_kernels_row_for_it_is_accepted():
    program = _in_no_edge()
    answer = themis.run(program)["results"][0]
    assert row(answer, "balke_pearl_iv")["instrument"] == "z"
    verify_honestly(program, answer)


@pytest.mark.parametrize("named", ["y", "x", "nobody"])
def test_a_name_the_graph_cannot_offer_is_still_refused(named):
    program = _in_no_edge()
    bounds = copy.deepcopy(
        row(themis.run(program)["results"][0], "balke_pearl_iv"))
    bounds["instrument"] = named
    with pytest.raises(VerificationError, match="does not offer"):
        _audit(program, bounds)


def test_a_candidate_sharing_a_cause_with_the_outcome_is_still_refused():
    """c -> b -> x and c -> y: no directed path from b to y, and an open one."""
    program = _program(("c", "b", "x", "y"),
                       (("c", "b"), ("b", "x"), ("c", "y")), "x", "y")
    assert _graph_instrument_candidates(
        program, treatment="x", outcome="y") == set()


def _random_programs():
    rng = random.Random(689)
    names = ["a", "b", "c", "d", "e", "f"]
    found = []
    while len(found) < 12:
        order = names[:]
        rng.shuffle(order)
        edges = [(order[i], order[j])
                 for i, j in itertools.combinations(range(6), 2)
                 if rng.random() < 0.3]
        x, y = rng.sample(names, 2)
        if any(y in edge for edge in edges):
            continue
        found.append((tuple(edges), x, y))
    return found


@pytest.mark.parametrize("edges, x, y", _random_programs())
def test_every_answer_beside_an_outcome_in_no_edge_is_accepted(edges, x, y):
    program = _program(["a", "b", "c", "d", "e", "f"], edges, x, y)
    verify_honestly(program, themis.run(program)["results"][0])
