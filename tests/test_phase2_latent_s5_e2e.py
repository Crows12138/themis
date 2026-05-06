"""Phase 2.latent S5: end-to-end Done-criterion showcase.

Pins the four cases PHASE_2_LATENT_CHARTER.md §8 names as the
fragment's done signal, each exercising ``themis.run`` and
``themis.verify`` together:

1. front-door-with-hidden-U (X → M → Y, X ↔ Y) — S3.a identifies,
   S4 verifies
2. ADMG-aware backdoor (Z → X → Y, W → Y, W ↔ Z) — S3.b.1 identifies,
   S4 verifies
3. bow-arc (X → Y, X ↔ Y) — runtime returns needs_investigation;
   this charter's narrow scope does not claim unidentifiable
4. pure-DAG regression (exercise_waist shape) — unchanged backdoor
   path still solved and verified

These duplicate some coverage from the per-slice tests intentionally:
a single file that future readers can point at as "the Phase 2.latent
fragment does what the charter says it does."
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _identify(target: str, intervention: str) -> dict:
    return {
        "kind": "query", "id": "q",
        "query": {
            "kind": "identify",
            "target": _atom(target),
            "intervention": {"atom": _atom(intervention), "value": True},
            "given": [],
        },
    }


def _program(statements: list) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ============================================ charter §8 case 1 (S3.a)

def test_case_front_door_with_hidden_u_runs_and_verifies():
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify("y", "x"),
    ])
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_front_door" in rules
    # S4: independent verifier accepts (no AdmgVerificationPending).
    assert themis.verify(ast, r) is None


# ============================================ charter §8 case 2 (S3.b.1)

def test_case_admg_aware_backdoor_runs_and_verifies():
    ast = _program([
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("w"), "right": _atom("z")},
        _identify("y", "x"),
    ])
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_backdoor" in rules
    assert themis.verify(ast, r) is None


# ============================================ charter §8 case 3 (negative)

def test_case_bow_arc_resolves_to_tian_hedge():
    """Bow-arc: X → Y + X ↔ Y. Phase 2.latent ext §S3.b.2 Tian /
    Shpitser ID Line 5 fires — X and Y are in the same c-component
    of An(Y), so P(Y | do(X)) is unidentifiable from observational
    data. Pre-S3.b.2 this returned needs_investigation pointing at
    the deferred c-factor work; post-S3.b.2 it's the definitive
    structurally_solved + value=False answer."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify("y", "x"),
    ])
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is False
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "tian_hedge_witness" in rules
    # verify round-trip: hedge witness rule must accept independently.
    assert themis.verify(ast, r) is None


# ============================================ charter §8 DAG regression

def test_case_pure_dag_regression():
    """Classic confounded DAG W → X → Y with W → Y — backdoor on {W}
    works with zero ADMG machinery engaged."""
    ast = _program([
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("w"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        _identify("y", "x"),
    ])
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    # DAG path uses identify_via_backdoor — independent verifier accepts.
    assert themis.verify(ast, r) is None
