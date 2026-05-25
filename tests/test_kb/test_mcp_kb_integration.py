"""G — verify the Themis MCP server, when auto-loaded with the sibling
CauseNet adapter, attaches kb_verification_report to themis_run results
through the MCP tool surface.

This is the bridge between the Phase D-F work (which tested in-process
themis.run directly) and the actual MCP transport surface that LLM
agents use. Skips if sibling causenet_mcp + SQLite data not present.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from themis.mcp import build_server
from themis.mcp.server import _try_load_kb_adapter


@pytest.fixture(scope="module")
def kb_app():
    """MCP app with auto-loaded KB adapter; skip if KB unavailable."""
    if _try_load_kb_adapter() is None:
        pytest.skip("sibling causenet_mcp not available")
    return build_server(auto_load_kb=True)


def _call_tool(app, name: str, args: dict) -> dict:
    blocks = asyncio.run(app.call_tool(name, args))
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no text content in tool result for {name!r}")


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _effect_query_program(cause: str, effect: str) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": cause,  "domain": [True, False]},
            {"kind": "variable", "predicate": effect, "domain": [True, False]},
            {
                "kind": "cause", "from": _atom(cause), "to": _atom(effect),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {"atom": _atom(effect), "value": True},
                    "intervention": {"atom": _atom(cause), "value": True},
                    "given": [],
                },
            },
        ],
    }


def test_mcp_themis_run_attaches_kb_report_when_kb_loaded(kb_app):
    """themis_run via MCP should attach kb_verification_report when
    the server was built with auto_load_kb=True and KB was found."""
    prog = _effect_query_program("smoking", "lung_cancer")
    out = _call_tool(kb_app, "themis_run", {"program": prog})
    ext = out["results"][0].get("extensions", {})
    assert "kb_verification_report" in ext, (
        f"expected kb_verification_report in extensions, got: {list(ext)}"
    )
    pe = ext["kb_verification_report"]["per_edge_verification"]
    assert len(pe) == 1
    assert pe[0]["verdict"] in ("kb_verified", "kb_partial")
    assert pe[0]["num_sources"] > 0


def test_mcp_no_kb_when_auto_load_disabled():
    """Confirm the opt-out path: auto_load_kb=False → no
    kb_verification_report on results."""
    app = build_server(auto_load_kb=False)
    prog = _effect_query_program("smoking", "lung_cancer")
    out = _call_tool(app, "themis_run", {"program": prog})
    ext = out["results"][0].get("extensions", {})
    assert "kb_verification_report" not in ext
