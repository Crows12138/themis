"""Phase 5 §T / S.T.2: temporal verifier rules.

These tests pin the narrow verifier-only temporal fragment:

- T1_time_monotonicity
- T2_lag_bound
- T3_unroll_acyclic

No runtime temporal scheduler or graph-unrolling logic is involved yet.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.types import Atom, CauseQuery, ConstTerm, RelativeTimeIndex
from themis.verifier.context import VerificationContext
from themis.verifier.errors import RuleCheckFailed
from themis.verifier.rules import dispatch_rule, known_rule


def _atom(pred: str, t: int, obj: str = "me") -> Atom:
    return Atom(
        predicate=pred,
        args=(ConstTerm(name=obj),),
        time_index=RelativeTimeIndex(value=t),
    )


def _ctx(graph: nx.DiGraph, src: Atom, dst: Atom) -> VerificationContext:
    return VerificationContext(graph=graph, query=CauseQuery(from_atom=src, to_atom=dst))


def _dispatch(rule: str, ctx: VerificationContext, inputs: dict, output) -> None:
    dispatch_rule(
        rule_name=rule,
        ctx=ctx,
        inputs=inputs,
        claimed_output=output,
        step_index=0,
        step_by_id={},
        step_output_by_id={},
    )


def test_temporal_rules_are_registered():
    assert known_rule("T1_time_monotonicity")
    assert known_rule("T2_lag_bound")
    assert known_rule("T3_unroll_acyclic")


def test_t1_accepts_non_decreasing_time_order():
    x = _atom("stays_up_late", -1)
    y = _atom("feels_tired", 0)
    g = nx.DiGraph()
    g.add_edge(x, y)
    ctx = _ctx(g, x, y)
    _dispatch("T1_time_monotonicity", ctx, {"graph": g, "src": x, "dst": y}, True)


def test_t1_rejects_reverse_time_order():
    x = _atom("cause", 1)
    y = _atom("effect", 0)
    g = nx.DiGraph()
    g.add_edge(x, y)
    ctx = _ctx(g, x, y)
    with pytest.raises(RuleCheckFailed, match="T1_time_monotonicity"):
        _dispatch("T1_time_monotonicity", ctx, {"graph": g, "src": x, "dst": y}, True)


def test_t1_requires_relative_time_index():
    x = Atom(predicate="x", args=(ConstTerm(name="me"),))
    y = _atom("y", 0)
    g = nx.DiGraph()
    g.add_nodes_from([x, y])
    ctx = _ctx(g, x, y)
    with pytest.raises(RuleCheckFailed, match="relative time_index"):
        _dispatch("T1_time_monotonicity", ctx, {"graph": g, "src": x, "dst": y}, True)


def test_t2_accepts_lag_one():
    x = _atom("x", -1)
    y = _atom("y", 0)
    g = nx.DiGraph()
    g.add_edge(x, y)
    ctx = _ctx(g, x, y)
    _dispatch("T2_lag_bound", ctx, {"graph": g, "src": x, "dst": y}, True)


def test_t2_rejects_lag_two():
    x = _atom("x", -2)
    y = _atom("y", 0)
    g = nx.DiGraph()
    g.add_edge(x, y)
    ctx = _ctx(g, x, y)
    with pytest.raises(RuleCheckFailed, match="T2_lag_bound"):
        _dispatch("T2_lag_bound", ctx, {"graph": g, "src": x, "dst": y}, True)


def test_t3_accepts_acyclic_unrolled_graph():
    x0 = _atom("x", 0)
    x1 = _atom("x", 1)
    y1 = _atom("y", 1)
    g = nx.DiGraph()
    g.add_edges_from([(x0, x1), (x0, y1)])
    ctx = _ctx(g, x0, y1)
    _dispatch("T3_unroll_acyclic", ctx, {"graph": g}, True)


def test_t3_rejects_cycle_in_unrolled_graph():
    x0 = _atom("x", 0)
    x1 = _atom("x", 1)
    g = nx.DiGraph()
    g.add_edges_from([(x0, x1), (x1, x0)])
    ctx = _ctx(g, x0, x1)
    with pytest.raises(RuleCheckFailed, match="T3_unroll_acyclic"):
        _dispatch("T3_unroll_acyclic", ctx, {"graph": g}, True)
