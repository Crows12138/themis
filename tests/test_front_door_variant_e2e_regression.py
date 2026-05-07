"""Iter 181 — front-door variant e2e regression pin.

Iter 165-173 closed the disjoint-Y c-component case via the
validator loosen + auto-marginalization arc. Iter 181 verified
that the SAME infrastructure also opens up the front-door variant
(X → M → Y with X ↔ Y latent confounder) — the canonical Tian
Line 7 trigger pattern.

Pre-iter-168 the kernel rejected the natural fixture: ``P(Y|X, M)``
needs X in given, but X isn't a structural parent of Y. iter 168
loosened the rule to accept ``parents ∪ directed_ancestors ∪
bidirected_siblings``; X is BOTH an ancestor of Y (via X→M→Y) AND
a bidirected sibling (X↔Y). So X is admissible.

The existing front-door identification fragment (Pearl's textbook
form) handles this graph and evaluates the CPTs the user supplied.
Output: 0.6 (matches hand-computed reference).

This test was NOT writable pre-iter-168 — fixture would fail
validation. Iter 181 pins the now-working capability so a future
validator regression doesn't silently re-block it.
"""
from __future__ import annotations

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


def test_front_door_variant_e2e_returns_pearl_formula_value():
    """X → M → Y, X ↔ Y latent. Pearl front-door:
        Σ_m P(M=m|X=T) · Σ_{x'} P(Y|X=x', M=m) · P(X=x')

    Concrete CPTs:
        P(X=T)=0.5, P(M=T|X=T)=0.7, P(M=T|X=F)=0.2
        P(Y=T|X=T,M=T)=0.9, P(Y=T|X=T,M=F)=0.4
        P(Y=T|X=F,M=T)=0.6, P(Y=T|X=F,M=F)=0.1

    Inner per m:
        m=T: 0.9·0.5 + 0.6·0.5 = 0.75
        m=F: 0.4·0.5 + 0.1·0.5 = 0.25
    Outer:
        0.7·0.75 + 0.3·0.25 = 0.6
    """
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {
                "kind": "bidirected",
                "left": _atom("x"), "right": _atom("y"),
            },
            _prob("x", True, [], 0.5),
            _prob("x", False, [], 0.5),
            _prob("m", True, [("x", True)], 0.7),
            _prob("m", False, [("x", True)], 0.3),
            _prob("m", True, [("x", False)], 0.2),
            _prob("m", False, [("x", False)], 0.8),
            # P(Y|X, M) — X is admissible because it's both an
            # ancestor (X→M→Y) AND a bidirected sibling (X↔Y) of Y.
            # iter 168 loosen made this fixture validatable.
            _prob("y", True, [("x", True), ("m", True)], 0.9),
            _prob("y", True, [("x", True), ("m", False)], 0.4),
            _prob("y", True, [("x", False), ("m", True)], 0.6),
            _prob("y", True, [("x", False), ("m", False)], 0.1),
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
    assert r["status"] == "numerically_solved"
    expected = 0.7 * (0.9 * 0.5 + 0.6 * 0.5) + 0.3 * (0.4 * 0.5 + 0.1 * 0.5)
    actual = r["numeric_result"]["value"]
    assert abs(actual - expected) < 1e-9, (
        f"Front-door variant e2e: got {actual}, expected {expected}"
    )
    # Iter 182: verifier now accepts front_door_adjustment_formula
    # as a valid identification-formula witness (was backdoor-only).
    derivation_rules = [
        s["rule"] for s in r["derivation"]["steps"]
    ]
    assert "front_door_adjustment_formula" in derivation_rules
    assert "identify_via_front_door" in derivation_rules
    # Independent verifier replay must accept.
    themis.verify(ast, r)


def test_parallel_multi_mediator_front_door_variant_e2e():
    """Iter 193: parallel multi-mediator (X→M1→Y, X→M2→Y, X↔Y latent).
    Front-door demands P(M2|M1, X) for chain-rule expansion of joint
    P(M1, M2|X). User supplies marginal P(M2|X) (parallel-paths
    semantics implied). iter 193 marginal-independence fallback uses
    P(M2|X) for the demanded P(M2|M1, X), unlocking the case."""
    import itertools
    prob_stmts = [
        _prob("x", True, [], 0.5),
        _prob("x", False, [], 0.5),
        _prob("m1", True, [("x", True)], 0.7),
        _prob("m1", False, [("x", True)], 0.3),
        _prob("m1", True, [("x", False)], 0.2),
        _prob("m1", False, [("x", False)], 0.8),
        _prob("m2", True, [("x", True)], 0.6),
        _prob("m2", False, [("x", True)], 0.4),
        _prob("m2", True, [("x", False)], 0.3),
        _prob("m2", False, [("x", False)], 0.7),
    ]
    for x_v, m1_v, m2_v in itertools.product([True, False], repeat=3):
        prob_stmts.append(
            _prob(
                "y", True,
                [("x", x_v), ("m1", m1_v), ("m2", m2_v)], 0.5,
            )
        )
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m1", "domain": [True, False]},
            {"kind": "variable", "predicate": "m2", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m1")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m2")},
            {"kind": "cause", "from": _atom("m1"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("m2"), "to": _atom("y")},
            {
                "kind": "bidirected",
                "left": _atom("x"), "right": _atom("y"),
            },
            *prob_stmts,
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
    assert r["status"] == "numerically_solved"
    assert abs(r["numeric_result"]["value"] - 0.5) < 1e-9
    themis.verify(ast, r)


def test_chain_mediator_front_door_variant_e2e_via_bayes_inversion():
    """Iter 188: chain X→M1→M2→Y with X↔Y latent. Front-door demands
    P(Y|X, M2); user supplies the chain CPTs P(M2|X, M1) + P(M1|X)
    + P(Y|X, M1, M2). iter 187/188 Bayes inversion derives the
    inner factor P(M1|X, M2) from supplied chain, enabling the
    full marginalization.

    Uniform 0.5 fixture → expected 0.5 (all sums collapse). Pinning
    that the derivation completes + verifier accepts."""
    import itertools

    prob_stmts = [
        _prob("x", True, [], 0.5),
        _prob("x", False, [], 0.5),
        _prob("m1", True, [("x", True)], 0.7),
        _prob("m1", False, [("x", True)], 0.3),
        _prob("m1", True, [("x", False)], 0.2),
        _prob("m1", False, [("x", False)], 0.8),
    ]
    for x_v, m1_v in itertools.product([True, False], repeat=2):
        prob_stmts.append(
            _prob("m2", True, [("x", x_v), ("m1", m1_v)], 0.5)
        )
        prob_stmts.append(
            _prob("m2", False, [("x", x_v), ("m1", m1_v)], 0.5)
        )
    for x_v, m1_v, m2_v in itertools.product([True, False], repeat=3):
        prob_stmts.append(
            _prob(
                "y", True,
                [("x", x_v), ("m1", m1_v), ("m2", m2_v)], 0.5,
            )
        )

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m1", "domain": [True, False]},
            {"kind": "variable", "predicate": "m2", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m1")},
            {"kind": "cause", "from": _atom("m1"), "to": _atom("m2")},
            {"kind": "cause", "from": _atom("m2"), "to": _atom("y")},
            {
                "kind": "bidirected",
                "left": _atom("x"), "right": _atom("y"),
            },
            *prob_stmts,
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
    assert r["status"] == "numerically_solved"
    assert abs(r["numeric_result"]["value"] - 0.5) < 1e-9
    themis.verify(ast, r)
