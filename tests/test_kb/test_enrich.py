"""E — kernel integration of KB edge verification.

Tests that kernel.run(prog, kb_adapter=...) attaches
extensions.kb_verification_report when an adapter is supplied, and
stays byte-identical to pre-D output when no adapter is supplied.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import themis
from themis.kb.adapters.causenet_mcp_adapter import (
    CausenetMCPAdapter,
    EdgeClaim,
    EdgeLookupResult,
    SuggestedEdge,
    TitleDistEntry,
)


# ------------------------------------------------------------------
# Fixtures: a small program with one LLM-proposed cause edge.
# ------------------------------------------------------------------

def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _prog(*, llm_proposed_edge: bool) -> dict:
    cause_stmt = {
        "kind": "cause",
        "from": _atom("smoking"),
        "to": _atom("lung_cancer"),
    }
    if llm_proposed_edge:
        cause_stmt["annotations"] = {"source": "llm_proposal"}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            cause_stmt,
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {"atom": _atom("lung_cancer"), "value": True},
                    "intervention": {"atom": _atom("smoking"), "value": True},
                    "given": [],
                },
            },
        ],
    }


_PROG_LLM_PROPOSED_EDGE = _prog(llm_proposed_edge=True)
_PROG_NO_LLM_EDGES = _prog(llm_proposed_edge=False)


# ------------------------------------------------------------------
# Fake adapter — predictable structural output
# ------------------------------------------------------------------


class _FakeAdapter:
    """Mimics CausenetMCPAdapter's shape without any IO. Records calls
    so tests can verify the kernel walked the program correctly."""

    def __init__(self, lookup_results: dict[tuple[str, str], EdgeLookupResult] | None = None,
                 suggestions: tuple[SuggestedEdge, ...] = ()):
        self._lookups = lookup_results or {}
        self._suggestions = suggestions
        self.lookup_calls: list[EdgeClaim] = []
        self.suggest_calls: list[list[str]] = []

    def lookup_edge(self, edge: EdgeClaim) -> EdgeLookupResult:
        self.lookup_calls.append(edge)
        key = (edge.cause, edge.effect)
        if key in self._lookups:
            return self._lookups[key]
        return EdgeLookupResult(
            edge=edge, verdict="kb_unverified", confidence_tier="not_found",
        )

    def suggest_edges_among(self, atoms: list[str]) -> tuple[SuggestedEdge, ...]:
        self.suggest_calls.append(list(atoms))
        return self._suggestions


# ------------------------------------------------------------------
# Tests
# ------------------------------------------------------------------


def test_no_adapter_means_no_kb_field() -> None:
    """Without kb_adapter, extensions.kb_verification_report must NOT
    appear — preserves byte-identical pre-D output for non-KB users."""
    out = themis.run(_PROG_LLM_PROPOSED_EDGE)
    for r in out["results"]:
        ext = r.get("extensions", {})
        assert "kb_verification_report" not in ext


def test_adapter_attaches_kb_verification_report() -> None:
    adapter = _FakeAdapter(
        lookup_results={
            ("smoking", "lung_cancer"): EdgeLookupResult(
                edge=EdgeClaim(cause="smoking", effect="lung_cancer"),
                verdict="kb_verified",
                confidence_tier="high_confidence",
                num_sources=1690,
                unique_source_count=42,
                source_title_distribution=(
                    TitleDistEntry(title="Lung cancer", count=1000),
                    TitleDistEntry(title="Smoking", count=690),
                ),
            ),
        },
    )
    out = themis.run(_PROG_LLM_PROPOSED_EDGE, kb_adapter=adapter)
    r0 = out["results"][0]
    ext = r0.get("extensions", {})
    assert "kb_verification_report" in ext
    report = ext["kb_verification_report"]
    assert len(report["per_edge_verification"]) == 1
    pe = report["per_edge_verification"][0]
    assert pe["edge"]["cause"] == "smoking"
    assert pe["edge"]["effect"] == "lung_cancer"
    assert pe["verdict"] == "kb_verified"
    assert pe["num_sources"] == 1690


def test_adapter_called_only_for_llm_proposed_edges() -> None:
    """Edges WITHOUT annotations.source containing 'llm' must not be
    routed through lookup_edge."""
    adapter = _FakeAdapter()
    themis.run(_PROG_NO_LLM_EDGES, kb_adapter=adapter)
    assert adapter.lookup_calls == []


def test_no_llm_edges_no_attachment_when_no_suggestions() -> None:
    """If the program has zero LLM-proposed edges AND adapter returns
    no suggestions, the report should NOT be attached (avoid noise)."""
    adapter = _FakeAdapter(suggestions=())
    out = themis.run(_PROG_NO_LLM_EDGES, kb_adapter=adapter)
    for r in out["results"]:
        ext = r.get("extensions", {})
        assert "kb_verification_report" not in ext


def test_suggestions_filter_out_already_proposed_edges() -> None:
    """If adapter suggests an edge that the LLM already proposed, it
    must be filtered out of suggested_missing_edges."""
    adapter = _FakeAdapter(
        lookup_results={
            ("smoking", "lung_cancer"): EdgeLookupResult(
                edge=EdgeClaim(cause="smoking", effect="lung_cancer"),
                verdict="kb_verified", confidence_tier="high_confidence",
                num_sources=10,
            ),
        },
        suggestions=(
            SuggestedEdge(cause="smoking", effect="lung_cancer",
                          num_sources=1690, confidence_tier="high_confidence"),
            SuggestedEdge(cause="smoking", effect="cancer",
                          num_sources=234, confidence_tier="high_confidence"),
        ),
    )
    out = themis.run(_PROG_LLM_PROPOSED_EDGE, kb_adapter=adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    suggestions = report["suggested_missing_edges"]
    suggested_pairs = {(s["cause"], s["effect"]) for s in suggestions}
    # The proposed one is filtered out
    assert ("smoking", "lung_cancer") not in suggested_pairs
    # The novel one remains
    assert ("smoking", "cancer") in suggested_pairs


def test_atoms_searched_field_lists_all_atoms() -> None:
    adapter = _FakeAdapter()
    out = themis.run(_PROG_LLM_PROPOSED_EDGE, kb_adapter=adapter)
    # NO LLM-proposed edges in this output (since lookup_edge returned
    # kb_unverified by default). suggested_missing_edges is also empty.
    # That fires the "no attachment" rule — but we can still test the
    # adapter received the right atoms via its call log.
    assert sorted(adapter.suggest_calls[0]) == ["lung_cancer", "smoking"]


def test_kb_report_serializes_to_json() -> None:
    """The whole result envelope must be JSON-serializable (no
    dataclass leakage from the adapter into the output)."""
    adapter = _FakeAdapter(
        lookup_results={
            ("smoking", "lung_cancer"): EdgeLookupResult(
                edge=EdgeClaim(cause="smoking", effect="lung_cancer"),
                verdict="kb_verified", confidence_tier="high_confidence",
                num_sources=10,
                source_title_distribution=(
                    TitleDistEntry(title="Lung cancer", count=10),
                ),
            ),
        },
    )
    out = themis.run(_PROG_LLM_PROPOSED_EDGE, kb_adapter=adapter)
    json.dumps(out)  # must not raise


# ------------------------------------------------------------------
# Integration with real sibling MCP (skip if data missing)
# ------------------------------------------------------------------


def _try_load_real_adapter():
    sibling_src = (Path(__file__).resolve().parents[2]
                   / "sibling" / "themis-kb-causenet-mcp" / "src")
    if not sibling_src.exists():
        return None
    sys.path.insert(0, str(sibling_src))
    try:
        from causenet_mcp import build_server  # type: ignore[import-not-found]
    except ImportError:
        return None
    from themis.kb.adapters.causenet_mcp_adapter import make_inprocess_caller
    try:
        app = build_server()
    except FileNotFoundError:
        return None
    return CausenetMCPAdapter(make_inprocess_caller(app), use_wordnet=False)


@pytest.fixture(scope="module")
def real_adapter():
    a = _try_load_real_adapter()
    if a is None:
        pytest.skip("sibling causenet_mcp package or SQLite data not present")
    return a


def test_integration_kernel_with_real_kb(real_adapter) -> None:
    """End-to-end: kernel.run + real CauseNet sibling adapter.
    smoking → lung_cancer must come back with non-trivial KB support."""
    out = themis.run(_PROG_LLM_PROPOSED_EDGE, kb_adapter=real_adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    assert len(report["per_edge_verification"]) == 1
    pe = report["per_edge_verification"][0]
    assert pe["verdict"] in ("kb_verified", "kb_partial")
    assert pe["num_sources"] > 0
    assert pe["edge"] == {"cause": "smoking", "effect": "lung_cancer"}
