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
        "causenet_query_edge_aggregated",
        "causenet_neighbors",
        "causenet_neighbors_among",
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


# ============================================ query_edge_aggregated


def test_query_edge_aggregated_supported_returns_distributions(app):
    """smoking → lung_cancer in precision tier — aggregated form must
    return source_title / path_pattern / source_type distributions."""
    out = _call_tool(app, "causenet_query_edge_aggregated", {
        "cause": "smoking", "effect": "lung_cancer",
    })
    assert out["verdict"] == "supported"
    assert out["confidence_tier"] == "high_confidence"
    assert out["num_sources"] >= 1
    assert out["unique_source_count"] >= 1
    # All three distributions must be non-empty when num_sources >= 1
    assert len(out["source_title_distribution"]) >= 1
    assert len(out["path_pattern_distribution"]) >= 1
    assert len(out["source_type_distribution"]) >= 1
    # Distribution entry shape
    title_entry = out["source_title_distribution"][0]
    assert "title" in title_entry
    assert "count" in title_entry
    assert title_entry["count"] >= 1
    pattern_entry = out["path_pattern_distribution"][0]
    assert "pattern" in pattern_entry
    assert "count" in pattern_entry
    type_entry = out["source_type_distribution"][0]
    assert "source_type" in type_entry
    assert "count" in type_entry


def test_query_edge_aggregated_titles_sorted_descending(app):
    """Title distribution must be sorted by count descending — Top-N
    semantics depend on this for callers reading just the head."""
    out = _call_tool(app, "causenet_query_edge_aggregated", {
        "cause": "smoking", "effect": "lung_cancer",
    })
    counts = [e["count"] for e in out["source_title_distribution"]]
    assert counts == sorted(counts, reverse=True)


def test_query_edge_aggregated_not_found_empty_distributions(app):
    """Absent edge: distributions are empty lists (not omitted), counts zero."""
    out = _call_tool(app, "causenet_query_edge_aggregated", {
        "cause": "purple_unicorn", "effect": "tuesday",
    })
    assert out["verdict"] == "not_found"
    assert out["num_sources"] == 0
    assert out["unique_source_count"] == 0
    assert out["source_title_distribution"] == []
    assert out["path_pattern_distribution"] == []
    assert out["source_type_distribution"] == []


def test_query_edge_aggregated_unique_count_lt_or_eq_total(app):
    """unique_source_count counts DISTINCT pages — must be ≤ num_sources
    (which counts sentence-level extractions, can have many per page)."""
    out = _call_tool(app, "causenet_query_edge_aggregated", {
        "cause": "smoking", "effect": "lung_cancer",
    })
    assert out["unique_source_count"] <= out["num_sources"]


# ============================================ neighbors_among


def test_neighbors_among_returns_edges_within_set(app):
    """Given atoms {smoking, lung_cancer, cancer}, KB should return at
    least smoking→lung_cancer and possibly other intra-set edges."""
    out = _call_tool(app, "causenet_neighbors_among", {
        "atoms": ["smoking", "lung_cancer", "cancer"],
    })
    assert "atoms" in out
    assert "edges" in out
    # smoking → lung_cancer is canonical, must be in the set
    pairs = {(e["cause"], e["effect"]) for e in out["edges"]}
    assert ("smoking", "lung_cancer") in pairs


def test_neighbors_among_endpoints_strictly_within_set(app):
    """Every returned edge's BOTH endpoints must be in the input set —
    no leakage to concepts outside the atoms list."""
    atoms = ["smoking", "lung_cancer", "cancer", "exercise"]
    out = _call_tool(app, "causenet_neighbors_among", {"atoms": atoms})
    normalized = set(out["atoms"])
    for e in out["edges"]:
        assert e["cause"] in normalized
        assert e["effect"] in normalized


def test_neighbors_among_empty_input_returns_empty(app):
    """Empty atom list → empty edges, no crash."""
    out = _call_tool(app, "causenet_neighbors_among", {"atoms": []})
    assert out["atoms"] == []
    assert out["edges"] == []


def test_neighbors_among_normalizes_atoms(app):
    """User-side casing / spacing on input must not affect lookup."""
    out_clean = _call_tool(app, "causenet_neighbors_among", {
        "atoms": ["smoking", "lung_cancer"],
    })
    out_dirty = _call_tool(app, "causenet_neighbors_among", {
        "atoms": ["  SMOKING  ", "Lung Cancer"],
    })
    assert {(e["cause"], e["effect"]) for e in out_clean["edges"]} == \
           {(e["cause"], e["effect"]) for e in out_dirty["edges"]}


def test_neighbors_among_each_edge_has_tier(app):
    """Tier label must be on every edge so caller can weight by confidence."""
    out = _call_tool(app, "causenet_neighbors_among", {
        "atoms": ["smoking", "lung_cancer", "cancer"],
    })
    for e in out["edges"]:
        assert e["confidence_tier"] in ("high_confidence", "extracted")


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
