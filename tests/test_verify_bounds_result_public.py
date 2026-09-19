"""The public ``themis.verify_bounds_results`` entry.

Parallel to ``themis.verify_data_gap_report``: bounds typically attach
when point identification fails (status=needs_investigation) and no
derivation chain exists, so ``themis.verify`` rejects them for missing
derivation. This is the derivation-less entry, dispatching to the
per-method verifiers.
"""
from __future__ import annotations

import pytest

import themis
from themis.verifier.errors import VerificationError


# ---------------------------------------------------------------------------
# MN bounds (Phase 12)
# ---------------------------------------------------------------------------


from tests.bounds_rows import methods, row

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
    assert methods(result) == ["manski_natural"]
    # Should NOT raise.
    themis.verify_bounds_results(program, result)


def test_rejects_tampered_manski_natural():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "manski_natural")["lower_expression"] = "P(y=false)"  # tamper
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        themis.verify_bounds_results(program, result)


# ---------------------------------------------------------------------------
# MTR bounds
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
    assert "manski_tamer_monotonicity" in methods(result)
    themis.verify_bounds_results(program, result)


def test_rejects_tampered_mtr_bounds():
    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "manski_tamer_monotonicity")["lower_expression"] = "tampered"
    with pytest.raises(VerificationError):
        themis.verify_bounds_results(program, result)


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
    assert "balke_pearl_iv" in methods(result)
    themis.verify_bounds_results(program, result)


def test_rejects_tampered_bp_bounds():
    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "balke_pearl_iv")["lower_expression"] = "fake lower"
    with pytest.raises(VerificationError, match="lower_expression mismatch"):
        themis.verify_bounds_results(program, result)


def test_rejects_bp_bounds_naming_an_instrument_the_graph_does_not_offer():
    """The tamper the public door could not see before.

    Reaching this needs the graph, which this entry has and used not to
    pass on: the instrument lived inside the expression, so the audit
    read the sentence, and a sentence saying the right thing about the
    wrong variable read as correct.
    """
    program = _bp_program()
    out = themis.run(program)
    result = out["results"][0]
    bounds = row(result, "balke_pearl_iv")
    bounds["instrument"] = "y"
    with pytest.raises(VerificationError, match="does not offer"):
        themis.verify_bounds_results(program, result)


# ---------------------------------------------------------------------------
# Error paths
# ---------------------------------------------------------------------------


def test_rejects_result_without_bounds():
    """Caller passed a result that has no bounds at all — clear error."""
    program = _confounded_program()
    result = {
        "status": "structurally_solved",
        "query_kind": "effect",
        "query_id": "mn_e2e",
        "structural_result": {"value": True},
    }
    with pytest.raises(ValueError, match="requires result.bounds_results"):
        themis.verify_bounds_results(program, result)


def test_rejects_result_without_query_id():
    program = _confounded_program()
    result = {
        "status": "needs_investigation",
        "query_kind": "effect",
        "bounds_results": [{"method": "manski_natural",
                            "lower_expression": "x",
                            "upper_expression": "y",
                            "estimand": "arm_probability",
                            "tightness": "sharp"}],
    }
    with pytest.raises(ValueError, match="result.query_id"):
        themis.verify_bounds_results(program, result)


def test_rejects_unsupported_method():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "manski_natural")["method"] = "frontdoor_partial"
    with pytest.raises(ValueError, match="not yet implemented"):
        themis.verify_bounds_results(program, result)


def test_rejects_unknown_method():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "manski_natural")["method"] = "made_up_method"
    # Schema validator rejects the bad method enum value.
    with pytest.raises(Exception):
        themis.verify_bounds_results(program, result)


def test_rejects_query_id_not_in_program():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["query_id"] = "no_such_query"
    with pytest.raises(ValueError, match="no query with id"):
        themis.verify_bounds_results(program, result)


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_re_exported_from_themis():
    assert "verify_bounds_results" in themis.__all__
    assert callable(themis.verify_bounds_results)


# ---------------------------------------------------------------------------
# MCP tool wraps the public function
# ---------------------------------------------------------------------------


def test_mcp_tool_themis_verify_bounds_results_accepts_clean_result():
    import asyncio
    from themis.mcp import build_server

    app = build_server()
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]

    tool_names = {t.name for t in asyncio.run(app.list_tools())}
    assert "themis_verify_bounds_results" in tool_names

    res = asyncio.run(
        app.call_tool("themis_verify_bounds_results",
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


def test_mcp_tool_themis_verify_bounds_results_rejects_tampered():
    import asyncio
    from themis.mcp import build_server

    app = build_server()
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    row(result, "manski_natural")["lower_expression"] = "P(y=false)"  # tamper

    res = asyncio.run(
        app.call_tool("themis_verify_bounds_results",
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
