"""A linear-SCM counterfactual lists what it is missing in causal order.

When the structural equations cannot be solved, the answer is a list of what
the reader must supply: a coefficient on an edge, an observation of the unit.
The list was built by walking the relevant variables as a set, so the same
question listed its gaps in a different order from one process to the next,
and the order carried nothing a reader could use. It is walked in causal order
now, which is the same in every process and is also the order a reader works
through a model in: nothing is asked about a variable before what causes it.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

import networkx as nx

ROOT = pathlib.Path(__file__).resolve().parents[1]
SEEDS = ("0", "1", "2")

_EDGES = (("z", "x"), ("x", "m"), ("m", "y"), ("z", "y"), ("x", "m2"), ("m2", "y"))


def _atom(p):
    return {"args": [{"name": "me", "type": "const"}], "predicate": p}


def _program(observed):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": p} for p in ("z", "x", "m", "y", "m2")),
            *({"kind": "cause", "from": _atom(u), "to": _atom(v)} for u, v in _EDGES),
            *({"kind": "observation", "atom": _atom(p), "value": value}
              for p, value in observed.items()),
            {"kind": "query", "id": "q1", "query": {
                "kind": "scm_counterfactual", "intervention": {"atom": _atom("x"), "value": 5.0},
                "target": _atom("y")}},
        ],
    }


_GAPS = """
import json, sys
from themis.kernel import run
result = run(json.loads(sys.stdin.read()))["results"][0]
print(json.dumps([m["name"] for m in result["missing_information"]]))
"""


def _gaps_in_every_seed(program) -> dict[str, list[str]]:
    out = {}
    for seed in SEEDS:
        done = subprocess.run(
            [sys.executable, "-c", _GAPS], cwd=ROOT, input=json.dumps(program), check=True,
            env={**os.environ, "PYTHONHASHSEED": seed}, capture_output=True, text=True,
            encoding="utf-8")
        out[seed] = json.loads(done.stdout)
    return out


def _variable_of(gap: str) -> str:
    kind, subject = gap.split(":", 1)
    return (subject.split("->")[1] if kind == "coefficient" else subject).split("(")[0]


def _asked_in_causal_order(gaps: list[str]) -> bool:
    graph = nx.DiGraph(_EDGES)
    for i, earlier in enumerate(gaps):
        for later in gaps[i + 1:]:
            if earlier.split(":")[0] != later.split(":")[0]:
                continue
            if _variable_of(later) in nx.ancestors(graph, _variable_of(earlier)):
                return False
    return True


def test_missing_coefficients_are_listed_the_same_way_in_every_process():
    lists = _gaps_in_every_seed(_program({"z": 1.0, "x": 2.0, "m": 4.0, "y": 9.0, "m2": 4.0}))
    assert len(lists["0"]) == 5 and all(g.startswith("coefficient:") for g in lists["0"])
    assert all(lists[seed] == lists["0"] for seed in SEEDS), lists
    assert _asked_in_causal_order(lists["0"]), lists["0"]


def test_missing_observations_are_listed_the_same_way_in_every_process():
    lists = _gaps_in_every_seed(_program({"x": 2.0, "y": 9.0}))
    observations = [g for g in lists["0"] if g.startswith("observation:")]
    assert sorted(observations) == ["observation:m(me)", "observation:m2(me)", "observation:z(me)"]
    assert all(lists[seed] == lists["0"] for seed in SEEDS), lists
    assert _asked_in_causal_order(lists["0"]), lists["0"]
