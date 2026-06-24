"""Regression for A1: the independent verifier must ACCEPT a correct M-bias
identification, and must NOT be weakened into accepting an unidentifiable one.

M-bias (X→Y, X↔Z, Z↔Y): the only back-door path X↔Z↔Y has Z as a collider,
blocked under empty conditioning, so P(Y|do(X)) = P(Y|X) is point-identified.
The runtime identified it correctly, but `verify` raised — its
`identify_via_tian` rule ran the Shpitser Line-6 c-component test on the FULL
graph, omitting the Line-2 ancestor restriction that drops the non-ancestor
collider Z. The fix restricts to An(Y) first (a sound ID step), which removes
the false reject without admitting any unidentifiable claim.
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _var(p: str) -> dict:
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _identify(target: str, intervention: str) -> dict:
    return {"kind": "query", "id": "q", "query": {
        "kind": "identify",
        "target": _atom(target),
        "intervention": {"atom": _atom(intervention), "value": True},
        "given": []}}


def _program(*statements: dict) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": list(statements),
    }


def test_mbias_identification_round_trips_through_verifier():
    """run identifies P(Y|do(X)) = P(Y|X); the independent verifier accepts
    the same derivation (it used to raise)."""
    prog = _program(
        _var("x"), _var("z"), _var("y"),
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("z")},
        {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
        _identify("y", "x"),
    )
    r = themis.run(prog)["results"][0]
    assert r["structural_result"]["value"] is True
    assert r["extensions"]["identification"]["pattern"] == "backdoor"
    assert r["extensions"]["identification"]["adjustment_set"] == []
    themis.verify(prog, r)  # must not raise


def test_mbias_collider_with_child_still_verifies():
    """Z also has a child K (X→Y, X↔Z, Z↔Y, Z→K): K is irrelevant to
    P(Y|do(X)); identification and verification are unaffected."""
    prog = _program(
        _var("x"), _var("z"), _var("y"), _var("k"),
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("k")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("z")},
        {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
        _identify("y", "x"),
    )
    r = themis.run(prog)["results"][0]
    assert r["structural_result"]["value"] is True
    themis.verify(prog, r)


def test_bow_arc_stays_unidentifiable_and_verifies():
    """Guard against weakening: the bow arc (X→Y, X↔Y) must STILL be
    unidentifiable — Y stays in the {x,y} c-component even after the
    ancestor restriction — and its hedge result must verify."""
    prog = _program(
        _var("x"), _var("y"),
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify("y", "x"),
    )
    r = themis.run(prog)["results"][0]
    assert r["structural_result"]["value"] is False
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "tian_hedge_witness" in rules
    themis.verify(prog, r)
