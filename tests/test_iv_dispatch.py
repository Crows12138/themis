"""Phase 6.iv S.IV.2: scheduler integration — IV fallback in dispatch.

End-to-end tests that `themis.run` correctly falls back to IV
identification when backdoor + front-door both fail.
"""
from __future__ import annotations

import themis


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _identify_query(x, y):
    return {
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "identify",
            "intervention": {"atom": _atom(x), "value": True},
            "target": _atom(y),
            "given": [],
        },
    }


def _program(statements):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ==================================================== classic IV via ADMG


def test_iv_fallback_fires_when_backdoor_and_frontdoor_fail():
    """Classic IV scenario: Z → X → Y, with X ↔ Y latent confounder.

    Backdoor fails (no observed confounder).
    Front-door fails (no observed mediator — X → Y direct edge prevents
    any mediator from blocking the X→Y path).
    IV succeeds with Z.
    """
    ast = _program([
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify_query("x", "y"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    # Extensions should carry IV metadata
    assert "iv_identification" in result["extensions"]
    iv_meta = result["extensions"]["iv_identification"]
    assert iv_meta["strategy"] == "iv"
    assert iv_meta["instrument"] == "z(me)"
    assert iv_meta["conditioning"] == []
    assert "monotonicity" in iv_meta["required_assumption"]

    # Derivation should contain the identify_via_iv rule
    rules = [step["rule"] for step in result["derivation"]["steps"]]
    assert "identify_via_iv" in rules


def test_iv_fallback_non_admg_case():
    """IV works even without bidirected — if backdoor set is empty AND
    front-door is unavailable, IV can still identify.

    Construct: X → Y direct (blocks any front-door), Z → X (potential IV).
    No backdoor paths exist (no confounders). Backdoor actually trivially
    succeeds with empty set, so this won't route to IV.

    Therefore for non-ADMG IV fallback test we need a graph where
    backdoor genuinely fails. Since without bidirected all edges are
    directed, backdoor only fails if there's an unblockable path. Hard
    to construct cleanly without latent variables, so this test is
    mostly to confirm the non-ADMG code path exists — we skip it
    unless a natural example arises.
    """
    # Intentionally empty — non-ADMG IV fallback requires unusual
    # graph structures. The ADMG case (test above) is the natural
    # IV use case.
    pass


def test_backdoor_still_preferred_over_iv():
    """Sanity: when a backdoor set exists, IV must NOT fire. IV is
    a strict fallback, not a parallel strategy.
    """
    ast = _program([
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        # W is a back-door confounder (W → X, W → Y)
        {"kind": "cause", "from": _atom("w"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        # Z is also present with Z → X (could be IV but shouldn't fire)
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        _identify_query("x", "y"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    # Backdoor should fire, NOT IV
    assert "iv_identification" not in (result.get("extensions") or {})
    rules = [step["rule"] for step in result["derivation"]["steps"]]
    assert "identify_via_iv" not in rules


def test_frontdoor_still_preferred_over_iv():
    """Sanity: when front-door succeeds but backdoor fails, front-door
    fires, not IV."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        # X → M → Y, with X ↔ Y latent confounder (blocks backdoor)
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify_query("x", "y"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True
    # Phase 15B: the ID engine identifies it; IV (the escalation layer)
    # must NOT fire, and the structure is recognized as front-door.
    assert "iv_identification" not in (result.get("extensions") or {})
    rules = [step["rule"] for step in result["derivation"]["steps"]]
    assert "identify_via_iv" not in rules
    assert result["extensions"]["identification"]["pattern"] == "front_door"


def test_unidentifiable_when_all_three_fail_admg():
    """When backdoor, front-door, AND IV all fail on an ADMG case,
    Tian's hedge witness fires (Phase 2.latent ext §S3.b.2) — the bow
    arc is the canonical hedge graph, X and Y in the same c-component
    of An(Y). Result is structurally_solved with value=False, not
    needs_investigation. Pre-Tian this returned needs_investigation
    pointing at S3.b.2."""
    ast = _program([
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        # Just X ↔ Y bidirected with X → Y direct. No Z exists.
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify_query("x", "y"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is False
    rules = [s["rule"] for s in result["derivation"]["steps"]]
    assert "tian_hedge_witness" in rules


def test_iv_conditional_case_fires():
    """Conditional IV: Z → X → Y with X ↔ Y latent, plus W → Z and W → Y
    making Z not a basic IV. But given W, Z becomes valid.

    Note: Themis' IV dispatch tries conditional IV internally via
    iv_sets' max_conditioning_size default. The extension records the
    conditioning.
    """
    ast = _program([
        {"kind": "variable", "predicate": "w", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
        {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _identify_query("x", "y"),
    ])

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    iv_meta = result["extensions"]["iv_identification"]
    assert iv_meta["instrument"] == "z(me)"
    # W should be in conditioning
    assert "w(me)" in iv_meta["conditioning"]
