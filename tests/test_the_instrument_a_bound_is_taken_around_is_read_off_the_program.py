"""The instrument a bound is taken around is read off the program.

Both bounds layers used to look in ``extensions.iv_identification`` first
and fall back to the structural detector. That field names the instrument
as an atom -- ``z(me)`` -- and both consumers need a predicate: the
symbolic row counts the instrument's declared levels by predicate, and the
numeric end reads the frame's column. No answer reaches either layer with
the block on it today (every route that writes it has solved the query;
bounds are only taken where none did), so the read was dead, and wrong in
the one way it could come alive.

Each layer is handed a result carrying such a block here, and has to take
its instrument from the program regardless.
"""
from __future__ import annotations

import dataclasses

import numpy as np
import pandas as pd

import themis
from themis.estimation.contract import validate_data
from themis.estimation.dispatch import _attach_numeric_bounds
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.postprocess import Inputs
from themis.runtime.scheduler import _attach_bounds_results, dispatch_all
from themis.types import QueryStatement, ResultStatus
from tests.bounds_rows import row

#: What the IV routes write, with the instrument as those routes spell it.
_AN_IV_BLOCK = {"strategy": "iv", "instrument": "z(me)", "conditioning": []}


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program():
    """z -> x -> y with x and y confounded: the effect is not identified,
    and z is the one instrument the graph offers."""
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": p, "domain": [True, False]}
                for p in ("x", "y", "z")
            ] + [
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}},
            ]}


def _frame(n=6000, seed=3):
    """Compliers, always-takers and never-takers over a randomised z."""
    rng = np.random.default_rng(seed)
    kind = rng.choice(3, size=n, p=(0.6, 0.2, 0.2))
    z = rng.integers(0, 2, n).astype(bool)
    x = np.where(kind == 0, z, kind == 1)
    y = rng.random(n) < np.where(x, 0.7, 0.3)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def test_the_symbolic_row_takes_the_instrument_from_the_program():
    prog = validate_program(validate_ast(_program()))
    graph = project(instantiate(prog))
    result = next(r for r in dispatch_all(prog, graph) if r.query_id == "q")
    assert result.status == ResultStatus.NEEDS_INVESTIGATION
    stmt = next(s for s in prog.statements
                if isinstance(s, QueryStatement) and s.id == "q")
    carrying = dataclasses.replace(
        result, bounds_results=(),
        extensions={**(result.extensions or {}),
                    "iv_identification": dict(_AN_IV_BLOCK)})
    bounded = _attach_bounds_results(carrying, Inputs(
        program=prog, stmt=stmt, graph=graph, theta=None, prob_index=None,
        obs_index=None, bidirected=frozenset()))
    sharp = [b for b in bounded.bounds_results if b.method == "balke_pearl_iv"]
    assert [b.instrument for b in sharp] == ["z"]


def test_the_numeric_row_reads_the_instrument_column_the_program_names():
    program = _program()
    output = themis.run(program)
    result = next(r for r in output["results"] if r.get("query_id") == "q")
    assert row(result, "balke_pearl_iv")["instrument"] == "z"
    result.setdefault("extensions", {})["iv_identification"] = dict(_AN_IV_BLOCK)
    contract = validate_data(_frame(), required_columns={"x", "y", "z"})
    _attach_numeric_bounds(program, output, contract, random_state=0,
                           ci_bootstrap=0)
    sharp = row(result, "balke_pearl_iv")
    assert sharp["instrument"] == "z"
    assert sharp["lower_value"] is not None
