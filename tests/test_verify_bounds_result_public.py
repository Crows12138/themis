"""Iter 133 — public ``themis.verify_bounds_result`` entry tests.

Parallel to ``themis.verify_data_gap_report``: bounds typically attach
when point identification fails (status=needs_investigation) and no
derivation chain exists, so ``themis.verify`` rejects them for missing
derivation. This iter adds a derivation-less entry that dispatches to
the iter 126/127/130 verifier trilogy by method.
"""
from __future__ import annotations

import pytest

import themis
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# MN bounds (Phase 12)
# ---------------------------------------------------------------------------


def _confounded_program():
    """Hidden u → x and u → y, plus x → y. Backdoor identification
    fails (no observable adjustment for u); the bounds layer fires
    Manski natural since no MTR / IV declaration exists."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "mn_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_accepts_real_manski_natural_bounds():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == "manski_natural"
    # Should NOT raise.
    themis.verify_bounds_result(program, result)


def test_rejects_tampered_manski_natural():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "P(y=false)"  # tamper
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        themis.verify_bounds_result(program, result)


# ---------------------------------------------------------------------------
# MTR bounds (iter 119)
# ---------------------------------------------------------------------------


def _mtr_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "monotonicity": {
                "target": "y", "treatment": "x",
                "direction": "non_decreasing",
            },
        },
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "mtr_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_accepts_real_mtr_bounds():
    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == \
        "manski_tamer_monotonicity"
    themis.verify_bounds_result(program, result)


def test_rejects_tampered_mtr_bounds():
    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "tampered"
    with pytest.raises(VerificationError):
        themis.verify_bounds_result(program, result)


# ---------------------------------------------------------------------------
# Balke-Pearl IV bounds (Phase 12)
# ---------------------------------------------------------------------------


def _bp_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "bidirected", "forall": ["I"],
             "left": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "bp_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_accepts_real_bp_bounds():
    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result.get("bounds_result", {}).get("method") == "balke_pearl_iv"
    themis.verify_bounds_result(program, result)


def test_rejects_tampered_bp_bounds():
    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "fake lower"
    with pytest.raises(VerificationError, match="canonical 'min of P"):
        themis.verify_bounds_result(program, result)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_rejects_result_without_bounds():
    """Caller passed a result that has no bounds_result — clear error."""
    program = _confounded_program()
    result = {
        "status": "structurally_solved",
        "query_kind": "effect",
        "query_id": "mn_e2e",
        "structural_result": {"value": True},
    }
    with pytest.raises(ValueError, match="requires result.bounds_result"):
        themis.verify_bounds_result(program, result)


def test_rejects_result_without_query_id():
    program = _confounded_program()
    result = {
        "status": "needs_investigation",
        "query_kind": "effect",
        "bounds_result": {"method": "manski_natural",
                          "lower_expression": "x",
                          "upper_expression": "y",
                          "estimand": "arm_probability"},
    }
    with pytest.raises(ValueError, match="result.query_id"):
        themis.verify_bounds_result(program, result)


def test_rejects_unsupported_method():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["method"] = "frontdoor_partial"
    with pytest.raises(ValueError, match="not yet implemented"):
        themis.verify_bounds_result(program, result)


def test_rejects_unknown_method():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["method"] = "made_up_method"
    # Schema validator rejects the bad method enum value.
    with pytest.raises(Exception):
        themis.verify_bounds_result(program, result)


def test_rejects_query_id_not_in_program():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["query_id"] = "no_such_query"
    with pytest.raises(ValueError, match="no query with id"):
        themis.verify_bounds_result(program, result)


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_re_exported_from_themis():
    assert "verify_bounds_result" in themis.__all__
    assert callable(themis.verify_bounds_result)


# ---------------------------------------------------------------------------
# MCP tool wraps the public function
# ---------------------------------------------------------------------------


def test_mcp_tool_themis_verify_bounds_result_accepts_clean_result():
    import asyncio
    from themis.mcp import build_server

    app = build_server()
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]

    tool_names = {t.name for t in asyncio.run(app.list_tools())}
    assert "themis_verify_bounds_result" in tool_names

    res = asyncio.run(
        app.call_tool("themis_verify_bounds_result",
                      {"program": program, "result": result})
    )
    # FastMCP returns a list/tuple of TextContent + dict; check the
    # structured content carries ok=True.
    payload = None
    if isinstance(res, tuple):
        # newer FastMCP API
        for item in res:
            if isinstance(item, dict) and "ok" in item:
                payload = item
                break
    if payload is None:
        # alternate shape: list of TextContent objects with structured
        import json
        for chunk in res if isinstance(res, (list, tuple)) else [res]:
            text = getattr(chunk, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "ok" in parsed:
                        payload = parsed
                        break
                except (ValueError, TypeError):
                    continue

    assert payload is not None, f"could not extract structured result from {res!r}"
    assert payload["ok"] is True


def test_mcp_tool_themis_verify_bounds_result_rejects_tampered():
    import asyncio
    from themis.mcp import build_server

    app = build_server()
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "P(y=false)"  # tamper

    res = asyncio.run(
        app.call_tool("themis_verify_bounds_result",
                      {"program": program, "result": result})
    )
    # Find the {"ok": False, "error": ...} payload.
    payload = None
    if isinstance(res, tuple):
        for item in res:
            if isinstance(item, dict) and "ok" in item:
                payload = item
                break
    if payload is None:
        import json
        for chunk in res if isinstance(res, (list, tuple)) else [res]:
            text = getattr(chunk, "text", None)
            if text:
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and "ok" in parsed:
                        payload = parsed
                        break
                except (ValueError, TypeError):
                    continue

    assert payload is not None
    assert payload["ok"] is False
    assert "error" in payload
