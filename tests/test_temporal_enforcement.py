"""Phase 5 §T runtime enforcement.

The verifier's T1 / T2 / T3 primitives existed but were never invoked
during ``themis.run`` — meaning a kernel program could declare 'X@t=1
causes Y@t=0' (cause runs backwards in time) and the kernel silently
accepted it. This module pins down the runtime-side enforcement:

- ``temporal_monotonicity`` semantic check rejects backward-time
  causes at parse time.
- T2's lag bound was relaxed from <= 1 (first-order Markov scaffolding)
  to any non-negative lag — multi-day / multi-week causation is real
  and shouldn't be artificially capped.
"""
from __future__ import annotations

import pytest

import themis
from themis.input.semantic_validator import SemanticError


def _atom(p, t=None):
    a = {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    if t is not None:
        a["time_index"] = {"kind": "relative", "value": t}
    return a


def _program(stmts):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def _query(p_from, p_to, t_from=None, t_to=None):
    return {
        "kind": "query", "id": "q",
        "query": {
            "kind": "cause",
            "from": _atom(p_from, t_from),
            "to": _atom(p_to, t_to),
        },
    }


# ============================================ T1 enforcement


def test_backward_time_cause_rejected_at_parse_time():
    """Cause where source.t > dest.t is semantically incoherent —
    yesterday's effect cannot precede today's cause. Phase 5 §T / T1."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("x", t=1),
         "to": _atom("y", t=0)},
        _query("x", "y", t_from=1, t_to=0),
    ])
    with pytest.raises(SemanticError, match="time monotonicity"):
        themis.run(ast)


def test_forward_time_cause_accepted():
    """Cause respecting time order works normally."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("x", t=-1),
         "to": _atom("y", t=0)},
        _query("x", "y", t_from=-1, t_to=0),
    ])
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


def test_simultaneous_cause_accepted():
    """Same time slice is the equality boundary — accepted (no
    instantaneous-cause prohibition in this slice)."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("x", t=0),
         "to": _atom("y", t=0)},
        _query("x", "y", t_from=0, t_to=0),
    ])
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


def test_partially_atemporal_cause_accepted():
    """If only one endpoint carries a time_index, no constraint —
    atemporal ↔ temporal ordering is not specified by the schema and
    the runtime treats the atemporal endpoint as living on a virtual
    'no time' slice. Backward compat with pre-§T programs."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("x"),  # no time_index
         "to": _atom("y", t=0)},
        _query("x", "y", t_to=0),
    ])
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


# ============================================ T2 relaxation


def test_multi_day_lag_accepted():
    """Real-case multi-step lag — '1 week of sugar → cavity'. Phase 5
    charter's first-order Markov bound (|lag| ≤ 1) was conservative
    scaffolding; this test pins the relaxation."""
    ast = _program([
        {"kind": "variable", "predicate": "sugar_intake", "domain": [True, False]},
        {"kind": "variable", "predicate": "cavity", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("sugar_intake", t=-7),
         "to": _atom("cavity", t=0)},
        _query("sugar_intake", "cavity", t_from=-7, t_to=0),
    ])
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


def test_chain_with_mixed_lags_accepted():
    """Heterogeneous lag chain: stress (t-3) → poor sleep (t-2) →
    fatigue (t-1) → mistake (t=0). Each cause respects T1; the chain
    runs through dispatch normally."""
    ast = _program([
        {"kind": "variable", "predicate": "stress", "domain": [True, False]},
        {"kind": "variable", "predicate": "poor_sleep", "domain": [True, False]},
        {"kind": "variable", "predicate": "fatigue", "domain": [True, False]},
        {"kind": "variable", "predicate": "mistake", "domain": [True, False]},
        {"kind": "cause",
         "from": _atom("stress", t=-3),
         "to": _atom("poor_sleep", t=-2)},
        {"kind": "cause",
         "from": _atom("poor_sleep", t=-2),
         "to": _atom("fatigue", t=-1)},
        {"kind": "cause",
         "from": _atom("fatigue", t=-1),
         "to": _atom("mistake", t=0)},
        _query("stress", "mistake", t_from=-3, t_to=0),
    ])
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"
    assert out["results"][0]["structural_result"]["value"] is True
