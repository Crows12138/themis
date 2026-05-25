"""Phase C smoke test — in-process verification of CauseNet MCP server.

Drives the FastMCP app directly (no stdio transport, no MCP client) and
confirms:
  - tool catalog is exactly the 3 expected entries
  - causenet_query_edge returns "supported" for a known edge
  - causenet_query_edge returns "not_found" for an obviously absent edge
  - causenet_neighbors returns sorted-by-num_sources results
  - kb_provenance block present on every response

Same in-process testing pattern as themis/tests/test_mcp_server.py.
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def app():
    import sys
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from causenet_mcp import build_server
    return build_server()


def _call_tool(app, name: str, args: dict) -> dict:
    """Invoke a FastMCP tool in-process and parse the JSON result.
    Matches Themis test_mcp_server._call_tool semantics."""
    blocks = asyncio.run(app.call_tool(name, args))
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no text content in tool result: {blocks!r}")


# ============================================ wiring


def test_tool_catalog(app):
    tool_names = {t.name for t in asyncio.run(app.list_tools())}
    assert tool_names == {
        "causenet_query_edge",
        "causenet_neighbors",
        "causenet_search_concept",
    }


# ============================================ query_edge


def test_query_edge_supported_returns_evidence(app):
    """smoking → lung_cancer is a canonical hit in precision tier.
    Must return supported with at least 1 evidence sentence, the KB
    provenance block, and confidence_tier=high_confidence (precision)."""
    out = _call_tool(app, "causenet_query_edge", {
        "cause": "smoking", "effect": "lung_cancer",
    })
    assert out["verdict"] == "supported"
    assert out["confidence_tier"] == "high_confidence"
    assert out["num_sources"] >= 1
    assert len(out["evidence_sample"]) >= 1
    sample = out["evidence_sample"][0]
    assert "sentence" in sample
    assert "path_pattern" in sample
    prov = out["kb_provenance"]
    assert prov["kg"] == "CauseNet"
    assert prov["tier"] == "precision-1.0"
    assert prov["kg_precision_estimate"] == 0.83


def test_query_edge_not_found_returns_zero(app):
    """An obviously-absent edge returns verdict=not_found cleanly,
    no crash. confidence_tier is 'not_found' (NOT high_confidence/extracted)."""
    out = _call_tool(app, "causenet_query_edge", {
        "cause": "purple_unicorn", "effect": "tuesday",
    })
    assert out["verdict"] == "not_found"
    assert out["confidence_tier"] == "not_found"
    assert out["num_sources"] == 0
    assert out["evidence_sample"] == []
    # Provenance is still emitted so caller knows WHICH KB said no.
    assert out["kb_provenance"]["kg"] == "CauseNet"
    # Not-found responses do NOT claim a precision estimate.
    assert "kg_precision_estimate" not in out["kb_provenance"]


def test_query_edge_normalizes_input(app):
    """User-side casing / whitespace shouldn't matter."""
    out_lower = _call_tool(app, "causenet_query_edge", {
        "cause": "smoking", "effect": "lung_cancer",
    })
    out_upper = _call_tool(app, "causenet_query_edge", {
        "cause": "  SMOKING  ", "effect": "Lung Cancer",
    })
    assert out_lower["verdict"] == out_upper["verdict"]
    assert out_lower["num_sources"] == out_upper["num_sources"]


# ============================================ neighbors


def test_neighbors_effects_of_smoking_includes_known_diseases(app):
    """`smoking` should have at least some plausible downstream
    effects in CauseNet. Each result must be labelled with
    confidence_tier (high_confidence or extracted)."""
    out = _call_tool(app, "causenet_neighbors", {
        "concept": "smoking", "direction": "effects_of", "limit": 10,
    })
    assert out["direction"] == "effects_of"
    assert len(out["results"]) >= 1
    for r in out["results"]:
        assert r["confidence_tier"] in ("high_confidence", "extracted")
    # Within high_confidence tier (precision DB), results sorted by
    # num_sources descending.
    hc = [r["num_sources"] for r in out["results"]
          if r["confidence_tier"] == "high_confidence"]
    if hc:
        assert hc == sorted(hc, reverse=True)


def test_neighbors_causes_of_cancer_returns_results(app):
    """Reverse direction: what causes cancer in CauseNet."""
    out = _call_tool(app, "causenet_neighbors", {
        "concept": "cancer", "direction": "causes_of", "limit": 5,
    })
    assert out["direction"] == "causes_of"
    assert len(out["results"]) >= 1


# ============================================ search_concept


def test_search_concept_prefix_match(app):
    """`smok` prefix should surface smoking + maybe related concepts.
    Returns ordered by appearance count."""
    out = _call_tool(app, "causenet_search_concept", {
        "prefix": "smok", "limit": 5,
    })
    matches = out["matches"]
    assert len(matches) >= 1
    # smoking should be in the top results since it appears as both
    # cause and effect in many relations
    concepts = [m["concept"] for m in matches]
    assert any("smoking" in c or "smoke" in c for c in concepts), (
        f"expected smoke-related concept; got {concepts}"
    )
