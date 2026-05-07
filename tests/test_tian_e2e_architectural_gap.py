"""Iter 165 — future-work tracker for the Tian e2e architectural gap
documented in wall.md iter 150.

The disjoint-Y c-component case is the canonical scenario where Tian
is the scheduler's actual identification path (backdoor / front-door
/ IV all fail because Z1 ↔ Z2 latent confounder makes Z1, Z2
unobserved-confounded but jointly-conditional).

Tian product form gives:
    Σ_{z1, z2} P(Y|X=T, z1, z2) · P(Z1=z1|X=T) · P(Z2=z2|X=T, Z1=z1)

Iter 145 + 147 fixed the formula (verified at unit level by
test_formula_sum_bind_referenced.py); iter 148 pinned numerical
correctness via direct identify_via_tian + estimate_formula.

But routing through `themis.run` with theta hits the
semantic_validator's "given ⊆ parents(target)" rule. P(Z2|X=T, Z1)
has Z1 as a non-structural-parent (bidirected sibling). The kernel
rejects the fixture before identification runs.

This test pins the gap as xfail-strict. When a future iter
implements one of the three options (see wall.md iter 150):

1. Loosen semantic validator for ADMG topo predecessors of target
   atoms in the same c-component
2. Reformulate Tian to use joint CPT primitives
3. Accept the gap permanently

…the marker flips: option 1/2 → xpass (remove marker, test passes);
option 3 → keep xfail and update reason to point at the explicit
"won't fix" decision.

Closing iter 150's loose end with the iter 144→145 xfail-strict
pattern: file the gap as a strict-xfail with the fix path, so future
work has a concrete starting line.
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


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Iter 168 fixed half: semantic_validator now accepts the "
        "needed CPTs (parents ∪ directed-ancestors ∪ bidirected-"
        "siblings of target). But scheduler now routes the disjoint-"
        "Y query through backdoor (empty adjustment, since X has no "
        "parents), which needs P(Y|X) — not supplied. The user's "
        "P(Y|X, Z1, Z2) family is Tian-evaluable but not backdoor-"
        "evaluable. Two follow-on options: (a) scheduler falls "
        "through to Tian when the structurally-preferred path's "
        "CPTs are absent but a downstream path's CPTs are present; "
        "(b) numeric_estimator marginalizes Σ_{z1,z2} P(Y|X,z1,z2) "
        "·P(z1,z2|X) automatically when P(Y|X) is the demand. "
        "Either flips this xfail. wall.md iter 168 trace."
    ),
)
def test_tian_disjoint_y_e2e_blocked_by_semantic_validator():
    """Reference DGP matches test_tian_disjoint_y_evaluates_to_correct_ate
    in test_formula_sum_bind_referenced.py. Hand-computed reference
    is 0.596. The unit-level test proves Tian formula evaluates
    correctly; this test pins that the e2e path through themis.run
    is currently blocked by validator rejection of P(Z2|X, Z1)."""
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
