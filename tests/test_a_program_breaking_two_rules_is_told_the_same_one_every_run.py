"""A program breaking two rules is told the same one on every run.

The input checks ran in the order of a set of strings, and a set of strings
iterates in an order each process draws from its own hash seed. Where one
program broke two rules, which refusal it got was a matter of the run. Nothing
showed this until #807 added a rule that shares programs with an older one: a
loop declared between ``x`` a step back and ``y`` now also writes ``x`` with a
time index it carries nowhere else. The test that pins the loop's refusal
passed in one full run and failed in the next, and the web door, which hands a
refusal back to the model to mend the program, would have handed back
different ones for the same program.

The checks now run in the order their table declares; the set says only which
of them run. Each child process below draws its own seed, so the order a set
would have given differs among them.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

from themis.input import semantic_validator as sv

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_SEEDS = range(6)


def _atom(predicate, *, time=None):
    out = {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}
    if time is not None:
        out["time_index"] = {"kind": "relative", "value": time}
    return out


#: Z -> X -> Y with a loop declared between X a step back and Y: the loop
#: spans two time steps, and X is written with a time index only there.
_TWO_RULES = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "scale": "continuous"},
        {"kind": "variable", "predicate": "y", "scale": "continuous"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "feedback", "left": _atom("x", time=-1), "right": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": []}},
    ],
}

_CHILD = r"""
import json, sys
from themis.input import semantic_validator as sv
from themis.input.syntactic_validator import validate_ast

program = json.loads(sys.stdin.read())
as_a_set = list(sv.SLICE_1_CHECKS)
try:
    sv.validate_program(validate_ast(program))
    told = None
except sv.SemanticError as refusal:
    told = refusal.species.name

ran = []
def recorder(name):
    return lambda *args, **kwargs: ran.append(name)
for table in (sv._CHECK_FUNCS, sv._GRAPH_CHECK_FUNCS):
    for name in table:
        table[name] = recorder(name)
sv.validate_program(program, checks=frozenset(sv._CHECK_FUNCS))
sv.validate_against_graph((), None, checks=frozenset(sv._GRAPH_CHECK_FUNCS))

print(json.dumps({
    "set_puts_time_first": as_a_set.index("time_index_everywhere_or_nowhere")
                           < as_a_set.index("feedback_loops"),
    "told": told,
    "ran": ran,
}))
"""


def _run_under(seed: int) -> dict:
    env = {**os.environ, "PYTHONHASHSEED": str(seed),
           "PYTHONPATH": str(_ROOT)}
    done = subprocess.run(
        [sys.executable, "-c", _CHILD], input=json.dumps(_TWO_RULES),
        capture_output=True, text=True, encoding="utf-8", env=env,
        cwd=_ROOT, check=True)
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_refusal_and_the_order_do_not_depend_on_the_hash_seed():
    runs = [_run_under(seed) for seed in _SEEDS]
    # The seeds reach both orders a set would have run the two rules in,
    # so agreement below is not the luck of one draw.
    assert {run["set_puts_time_first"] for run in runs} == {True, False}
    assert {run["told"] for run in runs} == {"LOOP_ACROSS_TIME_STEPS"}
    declared = [*sv._CHECK_FUNCS, *sv._GRAPH_CHECK_FUNCS]
    assert all(run["ran"] == declared for run in runs), runs


def test_the_loop_s_refusal_is_the_one_that_comes_first():
    """Of the two, the loop's hands back the stronger model: three ordinary
    edges across time steps, identifiable without an instrument."""
    order = list(sv._CHECK_FUNCS)
    assert order.index("feedback_loops") < order.index(
        "time_index_everywhere_or_nowhere")
