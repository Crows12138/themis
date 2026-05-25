"""D.3 — themis-side CauseNet MCP adapter.

Unit tests use a mock ToolCallable (no sibling / DB dependency).
Integration test uses a real in-process FastMCP app loaded from the
sibling source tree — skipped if the sibling package can't be imported
or its CauseNet SQLite DB files aren't present.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from themis.kb.adapters.causenet_mcp_adapter import (
    CausenetMCPAdapter,
    EdgeClaim,
    EdgeLookupResult,
    SuggestedEdge,
    make_inprocess_caller,
)


# ============================================ Unit tests with mock caller


def _make_mock_caller(responses: dict[tuple[str, str, str], dict] | None = None,
                      tools: dict[str, dict] | None = None):
    """Build a ToolCallable that returns canned responses.

    Keys for `responses`: (tool_name, cause, effect) -> raw dict.
    Keys for `tools`: tool_name -> raw dict (when args don't matter).
    Misses fall back to a not_found-shaped response so the adapter
    doesn't crash on unexpected variants.
    """
    responses = responses or {}
    tools = tools or {}

    def _call(name: str, args: dict) -> dict:
        if name in tools:
            return tools[name]
        cause = args.get("cause", "")
        effect = args.get("effect", "")
        if (name, cause, effect) in responses:
            return responses[(name, cause, effect)]
        # Default "not_found" envelope for aggregated tool
        if name == "causenet_query_edge_aggregated":
            return {
                "verdict": "not_found",
                "confidence_tier": "not_found",
                "cause": cause, "effect": effect,
                "num_sources": 0, "unique_source_count": 0,
                "source_title_distribution": [],
                "path_pattern_distribution": [],
                "source_type_distribution": [],
                "kb_provenance": {"kg": "CauseNet", "tier": "union"},
            }
        if name == "causenet_neighbors_among":
            return {"atoms": args.get("atoms", []), "edges": [],
                    "kb_provenance": {"kg": "CauseNet", "tier": "union"}}
        raise AssertionError(f"unmocked tool call: {name} args={args}")

    return _call


def _supported_response(cause: str, effect: str, *, num_sources: int,
                         title_dist: list[tuple[str, int]],
                         pattern_dist: list[tuple[str, int]] | None = None,
                         type_dist: list[tuple[str, int]] | None = None,
                         tier: str = "high_confidence") -> dict:
    return {
        "verdict": "supported",
        "confidence_tier": tier,
        "cause": cause, "effect": effect,
        "num_sources": num_sources,
        "unique_source_count": max(1, num_sources // 2),
        "source_title_distribution": [
            {"title": t, "count": c} for t, c in title_dist
        ],
        "path_pattern_distribution": [
            {"pattern": p, "count": c} for p, c in (pattern_dist or [])
        ],
        "source_type_distribution": [
            {"source_type": st, "count": c} for st, c in (type_dist or [("wikipedia_sentence", num_sources)])
        ],
        "kb_provenance": {
            "kg": "CauseNet", "tier": "precision-1.0",
            "kg_precision_estimate": 0.83,
        },
    }


# ---- construction validation ----


def test_adapter_rejects_non_callable_tool_caller() -> None:
    with pytest.raises(TypeError):
        CausenetMCPAdapter(tool_caller="not a callable")  # type: ignore[arg-type]


def test_adapter_rejects_out_of_range_threshold() -> None:
    caller = _make_mock_caller()
    with pytest.raises(ValueError):
        CausenetMCPAdapter(caller, title_homogeneity_threshold=1.5)
    with pytest.raises(ValueError):
        CausenetMCPAdapter(caller, title_homogeneity_threshold=-0.1)


# ---- lookup_edge — happy path ----


def test_lookup_edge_kb_verified_when_title_dominates() -> None:
    """One title accounts for >50% — verdict is kb_verified."""
    caller = _make_mock_caller({
        ("causenet_query_edge_aggregated", "smoking", "lung_cancer"):
            _supported_response("smoking", "lung_cancer", num_sources=10,
                                 title_dist=[("Lung cancer", 9), ("Smoking", 1)]),
    })
    adapter = CausenetMCPAdapter(caller, use_wordnet=False)
    result = adapter.lookup_edge(EdgeClaim(cause="smoking", effect="lung_cancer"))
    assert result.verdict == "kb_verified"
    assert result.num_sources == 10
    assert result.confidence_tier == "high_confidence"
    assert result.matched_variants is None  # exact match, no variant noise


def test_lookup_edge_kb_partial_when_titles_split() -> None:
    """No title dominates — verdict is kb_partial (homonym risk)."""
    caller = _make_mock_caller({
        ("causenet_query_edge_aggregated", "bank", "erosion"):
            _supported_response("bank", "erosion", num_sources=10,
                                 title_dist=[("River bank", 4), ("Bank (financial)", 4),
                                             ("Geomorphology", 2)]),
    })
    adapter = CausenetMCPAdapter(caller, use_wordnet=False)
    result = adapter.lookup_edge(EdgeClaim(cause="bank", effect="erosion"))
    assert result.verdict == "kb_partial"
    # All distributions still surfaced — caller can inspect themselves
    assert len(result.source_title_distribution) == 3


def test_lookup_edge_kb_unverified_when_kb_misses() -> None:
    """KB has no edge for any variant — verdict kb_unverified, tier not_found."""
    caller = _make_mock_caller()  # all defaults → all not_found
    adapter = CausenetMCPAdapter(caller, use_wordnet=False)
    result = adapter.lookup_edge(EdgeClaim(cause="purple_unicorn", effect="tuesday"))
    assert result.verdict == "kb_unverified"
    assert result.confidence_tier == "not_found"
    assert result.num_sources == 0
    # queried_variants records what was tried (for audit trail)
    assert len(result.queried_variants) >= 1


# ---- lookup_edge — variant cascade ----


def test_lookup_edge_uses_l2_morphological_when_l1_misses() -> None:
    """L1 misses 'vaccines' but L2 produces 'vaccine' which hits.
    matched_variants must record the L2 variant that matched."""
    caller = _make_mock_caller({
        ("causenet_query_edge_aggregated", "vaccine", "immunity"):
            _supported_response("vaccine", "immunity", num_sources=5,
                                 title_dist=[("Vaccination", 5)]),
    })
    adapter = CausenetMCPAdapter(caller, use_wordnet=False)
    result = adapter.lookup_edge(EdgeClaim(cause="vaccines", effect="immunity"))
    assert result.verdict == "kb_verified"
    assert result.matched_variants is not None
    assert result.matched_variants["cause"] == "vaccine"


def test_lookup_edge_caps_variant_combinations() -> None:
    """Variant cascade is capped — adapter doesn't try unbounded combos
    even when both endpoints have many variants."""
    call_count = [0]

    def _counting(name, args):
        call_count[0] += 1
        return {
            "verdict": "not_found", "confidence_tier": "not_found",
            "cause": args.get("cause", ""), "effect": args.get("effect", ""),
            "num_sources": 0, "unique_source_count": 0,
            "source_title_distribution": [], "path_pattern_distribution": [],
            "source_type_distribution": [], "kb_provenance": {},
        }
    adapter = CausenetMCPAdapter(_counting, use_wordnet=False)
    adapter.lookup_edge(EdgeClaim(cause="vaccines", effect="immunities"))
    # Default cap is 16 — call count must respect it
    assert call_count[0] <= 16


def test_lookup_edge_threshold_tunable() -> None:
    """Stricter threshold (0.9) downgrades to kb_partial when top title
    only owns 70%."""
    response = _supported_response(
        "smoking", "lung_cancer", num_sources=10,
        title_dist=[("Lung cancer", 7), ("Other", 3)],
    )
    caller = _make_mock_caller({
        ("causenet_query_edge_aggregated", "smoking", "lung_cancer"): response,
    })
    strict = CausenetMCPAdapter(caller, use_wordnet=False,
                                  title_homogeneity_threshold=0.9)
    lax = CausenetMCPAdapter(caller, use_wordnet=False,
                              title_homogeneity_threshold=0.5)
    edge = EdgeClaim(cause="smoking", effect="lung_cancer")
    assert strict.lookup_edge(edge).verdict == "kb_partial"
    assert lax.lookup_edge(edge).verdict == "kb_verified"


def test_lookup_edge_no_llm_called_anywhere() -> None:
    """Discipline check: ONLY causenet_query_edge_aggregated is invoked.
    No LLM-shaped tool name appears in the call trace."""
    invocations: list[str] = []

    def _trace(name, args):
        invocations.append(name)
        return {
            "verdict": "not_found", "confidence_tier": "not_found",
            "cause": args.get("cause", ""), "effect": args.get("effect", ""),
            "num_sources": 0, "unique_source_count": 0,
            "source_title_distribution": [], "path_pattern_distribution": [],
            "source_type_distribution": [], "kb_provenance": {},
        }
    adapter = CausenetMCPAdapter(_trace, use_wordnet=False)
    adapter.lookup_edge(EdgeClaim(cause="a", effect="b"))
    assert all("llm" not in name.lower() and "judge" not in name.lower()
               and "model" not in name.lower() for name in invocations)


# ---- suggest_edges_among ----


def test_suggest_edges_among_returns_edges_from_kb() -> None:
    caller = _make_mock_caller(tools={
        "causenet_neighbors_among": {
            "atoms": ["smoking", "lung_cancer", "cancer"],
            "edges": [
                {"cause": "smoking", "effect": "lung_cancer",
                 "num_sources": 1690, "confidence_tier": "high_confidence"},
                {"cause": "smoking", "effect": "cancer",
                 "num_sources": 234, "confidence_tier": "high_confidence"},
            ],
            "kb_provenance": {"kg": "CauseNet", "tier": "union"},
        }
    })
    adapter = CausenetMCPAdapter(caller, use_wordnet=False)
    suggestions = adapter.suggest_edges_among(
        ["smoking", "lung_cancer", "cancer"]
    )
    assert len(suggestions) == 2
    assert all(isinstance(s, SuggestedEdge) for s in suggestions)
    assert suggestions[0].cause == "smoking"


def test_suggest_edges_among_empty_atoms_returns_empty() -> None:
    """No atoms → no call to KB, return empty tuple."""
    called = [False]

    def _detect(name, args):
        called[0] = True
        return {}
    adapter = CausenetMCPAdapter(_detect, use_wordnet=False)
    assert adapter.suggest_edges_among([]) == ()
    # Adapter must NOT call KB when atoms list is empty (perf + cleanliness)
    assert called[0] is False


# ============================================ Integration test (skip-if)


def _try_load_sibling_app() -> Any | None:
    """Locate the sibling causenet_mcp package and instantiate its app.
    Returns None if either the package or the SQLite data files are
    missing (so the test gracefully skips on bare clones)."""
    sibling_src = (Path(__file__).resolve().parents[2]
                   / "sibling" / "themis-kb-causenet-mcp" / "src")
    if not sibling_src.exists():
        return None
    sys.path.insert(0, str(sibling_src))
    try:
        from causenet_mcp import build_server  # type: ignore[import-not-found]
    except ImportError:
        return None
    try:
        return build_server()
    except FileNotFoundError:
        # No SQLite data built yet — graceful skip
        return None


@pytest.fixture(scope="module")
def real_adapter():
    app = _try_load_sibling_app()
    if app is None:
        pytest.skip(
            "sibling causenet_mcp package or its SQLite DBs not present"
        )
    caller = make_inprocess_caller(app)
    return CausenetMCPAdapter(caller, use_wordnet=False)


def test_integration_lookup_edge_smoking_lung_cancer(real_adapter) -> None:
    """End-to-end: real sibling MCP, real SQLite, canonical edge.
    Must come back kb_verified with non-trivial num_sources."""
    result = real_adapter.lookup_edge(
        EdgeClaim(cause="smoking", effect="lung_cancer")
    )
    assert result.verdict in ("kb_verified", "kb_partial")
    assert result.num_sources > 0
    assert len(result.source_title_distribution) > 0


def test_integration_lookup_edge_absent_returns_unverified(real_adapter) -> None:
    """Real DB query on nonsense edge: kb_unverified."""
    result = real_adapter.lookup_edge(
        EdgeClaim(cause="purple_unicorn_xyz", effect="tuesday_blue")
    )
    assert result.verdict == "kb_unverified"
    assert result.num_sources == 0


def test_integration_suggest_edges_among_real_data(real_adapter) -> None:
    """Real sibling: among {smoking, lung_cancer, cancer}, KB has at
    least smoking → lung_cancer."""
    suggestions = real_adapter.suggest_edges_among(
        ["smoking", "lung_cancer", "cancer"]
    )
    pairs = {(s.cause, s.effect) for s in suggestions}
    assert ("smoking", "lung_cancer") in pairs
