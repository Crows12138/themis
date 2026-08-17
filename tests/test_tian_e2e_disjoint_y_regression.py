"""The Tian end-to-end architectural gap, closed.

Filed first as an xfail-strict tracker for the gap wall.md iter 150
documents: semantic_validator rejected ADMG c-factor CPTs.
Closed across 4 iters of architectural progress:

- validator loosen — admissible_given = parents ∪
  directed_ancestors ∪ bidirected_siblings (covers Tian's c-factor
  topo predecessor set)
- detection helper can_derive_via_marginalization
- runtime numeric_estimator auto-marginalization (recursive,
  depth ≤ 3) — kernel now produces status='numerically_solved' for
  disjoint-Y
- mirror to the verifier's _evaluate_formula (preserves V0-V5
  independence — pure theta + canonical math, no shared state)

Test now passes as a regression pin. If any of the 4 layers regresses,
this test fails immediately.

Disjoint-Y c-component case (X→Z1, X→Z2, Z1↔Z2, Z1→Y, Z2→Y) is the
canonical scenario where Tian is the scheduler's actual identification
path (backdoor / front-door / IV all fail). Hand-computed reference
0.596 = 0.6·0.5·0.9 + 0.6·0.5·0.7 + 0.4·0.3·0.5 + 0.4·0.7·0.2.

wall.md iter 165-173 documents the full architectural arc.
"""
from __future__ import annotations

import pytest

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _prob(target: str, target_value, given: list, value: float) -> dict:
    return {
        "kind": "probability",
        "target": {"atom": _atom(target), "value": target_value},
        "given": [{"atom": _atom(g[0]), "value": g[1]} for g in given],
        "value": value,
    }


def test_tian_disjoint_y_e2e_returns_correct_numeric():
    """The e2e gap, closed across 4 architectural layers.
    Reference DGP matches test_tian_disjoint_y_evaluates_to_correct_ate
    in test_formula_sum_bind_referenced.py. Hand-computed reference
    is 0.596. themis.run + themis.verify roundtrip both succeed."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z1", "domain": [True, False]},
            {"kind": "variable", "predicate": "z2", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("z1")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("z2")},
            {"kind": "cause", "from": _atom("z1"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z2"), "to": _atom("y")},
            {
                "kind": "bidirected",
                "left": _atom("z1"), "right": _atom("z2"),
            },
            _prob("z1", True, [("x", True)], 0.6),
            _prob("z1", False, [("x", True)], 0.4),
            _prob("z2", True, [("x", True), ("z1", True)], 0.5),
            _prob("z2", False, [("x", True), ("z1", True)], 0.5),
            _prob("z2", True, [("x", True), ("z1", False)], 0.3),
            _prob("z2", False, [("x", True), ("z1", False)], 0.7),
            _prob("y", True,
                  [("x", True), ("z1", True), ("z2", True)], 0.9),
            _prob("y", True,
                  [("x", True), ("z1", True), ("z2", False)], 0.7),
            _prob("y", True,
                  [("x", True), ("z1", False), ("z2", True)], 0.5),
            _prob("y", True,
                  [("x", True), ("z1", False), ("z2", False)], 0.2),
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {"atom": _atom("y"), "value": True},
                    "intervention": {"atom": _atom("x"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    expected = (
        0.6 * 0.5 * 0.9
        + 0.6 * 0.5 * 0.7
        + 0.4 * 0.3 * 0.5
        + 0.4 * 0.7 * 0.2
    )
    assert r["status"] == "numerically_solved"
    assert abs(r["numeric_result"]["value"] - expected) < 1e-9
    themis.verify(ast, r)
