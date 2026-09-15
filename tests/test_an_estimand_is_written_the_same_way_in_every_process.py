"""A counterfactual estimand is written the same way in every process.

The estimand is what a reader is shown and what the answer corpus keeps. ID*
built Line 6's product in the order the counterfactual graph's c-components
came out of a set, so the same question listed its factors differently from
one process to the next — the numbers agreed, the text did not, and a stored
answer could not be read back as the one this build writes.

The order is now read off the nodes, by the key sum variables are named by.
That key would itself move with the process if it had to fall back on which
representative make-cg elected for a merged group; it does not, because in a
consistent counterfactual graph a node's variable and the interventions fixed
above it already tell it apart from every other node, and the second test
holds that.
"""
from __future__ import annotations

import json
import os
import pathlib
import random
import subprocess
import sys

import networkx as nx

from themis.runtime import ctf_identify as ci
from themis.runtime.ctf_identify import CtfEvent
from themis.types import Atom

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEDS = ("0", "1", "2")


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


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
        hi, lo, factual = frozenset({(x, True)}), frozenset({(x, False)}), frozenset()
        for gamma in (
            (CtfEvent(y, hi, True), CtfEvent(x, factual, False)),
            (CtfEvent(y, hi, True), CtfEvent(y, lo, False)),
            (CtfEvent(y, hi, True), CtfEvent(w, factual, True)),
            (CtfEvent(y, frozenset({(x, True), (w, True)}), True), CtfEvent(x, factual, False)),
        ):
            yield graph, bidirected, gamma


_SWEEP = """
import sys
sys.path.insert(0, "tests")
from test_an_estimand_is_written_the_same_way_in_every_process import _random_problems
from themis.runtime import ctf_identify as ci
for graph, bidirected, gamma in _random_problems(664, 40, 6):
    print(repr(ci.id_star(graph, bidirected, gamma)))
    print(repr(ci.idc_star(graph, bidirected, gamma[:1], gamma[1:])))
"""

_ENVELOPE = """
import json, sys
from themis.kernel import run
program = json.loads(sys.stdin.read())
print(json.dumps(run(program)["results"][0].get("formula"), sort_keys=True))
"""


def _in_every_seed(code: str, stdin: str = "") -> dict[str, str]:
    out = {}
    for seed in SEEDS:
        done = subprocess.run(
            [sys.executable, "-c", code], cwd=ROOT, input=stdin, check=True,
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True,
            encoding="utf-8")
        out[seed] = done.stdout
    return out


def test_id_star_and_idc_star_estimands_read_the_same_in_every_process():
    texts = _in_every_seed(_SWEEP)
    assert texts["0"].count("\n") == 320
    differing = [seed for seed in SEEDS if texts[seed] != texts[SEEDS[0]]]
    assert not differing, differing


def test_a_node_is_told_apart_by_its_variable_and_what_is_fixed_above_it(monkeypatch):
    real = ci.make_cg
    graphs = []

    def recording(graph, bidirected, gamma):
        cf = real(graph, bidirected, gamma)
        if cf is not ci.INCONSISTENT:
            graphs.append(cf)
        return cf

    monkeypatch.setattr(ci, "make_cg", recording)
    for graph, bidirected, gamma in _random_problems(6640, 60, 6):
        ci.id_star(graph, bidirected, gamma)
    assert graphs
    for cf in graphs:
        keys = [(n.variable, cf.subscript[n]) for n in cf.observable()]
        assert len(keys) == len(set(keys)), keys


def test_the_worked_example_reaches_a_reader_as_one_text():
    events = [
        {"variable": {"predicate": "y", "args": []},
         "subscript": [{"atom": {"predicate": "x", "args": []}, "value": True}], "value": True},
        {"variable": {"predicate": "x", "args": []}, "subscript": [], "value": False},
        {"variable": {"predicate": "z", "args": []},
         "subscript": [{"atom": {"predicate": "d", "args": []}, "value": True}], "value": True},
        {"variable": {"predicate": "d", "args": []}, "subscript": [], "value": True},
    ]
    program = {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *({"kind": "variable", "predicate": p, "domain": [True, False]} for p in "xwyzd"),
            *({"kind": "cause", "from": {"predicate": u, "args": []},
               "to": {"predicate": v, "args": []}}
              for u, v in (("x", "w"), ("w", "y"), ("z", "y"), ("d", "z"))),
            {"kind": "bidirected", "left": {"predicate": "x", "args": []},
             "right": {"predicate": "y", "args": []}},
            {"kind": "query", "id": "q",
             "query": {"kind": "counterfactual_conjunction", "events": events}},
        ],
    }
    texts = _in_every_seed(_ENVELOPE, json.dumps(program))
    assert json.loads(texts["0"])["kind"] == "sum"
    assert len(set(texts.values())) == 1, texts
