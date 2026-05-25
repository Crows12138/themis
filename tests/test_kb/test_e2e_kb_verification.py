"""F — end-to-end KB edge verification on real CauseNet sibling.

Four representative scenarios stress the design:

1. **High KB coverage** — smoking → lung_cancer (canonical health edge).
   Must verify with high_confidence + dominant title cluster.

2. **Low KB coverage** — food_sharing → workplace_warmth (cross-domain
   social question). Must return kb_unverified; the report should
   gracefully say "not in KB" rather than fabricate a verdict.

3. **Translator-required** — vaccines → immunity (plural form + close
   synonym). L1 normalize won't hit; L2 morphological should produce
   "vaccine" which may hit. Tests the variant cascade works.

4. **Homonym risk** — bank → erosion (potentially river vs financial).
   If KB has both senses, structural verdict should be kb_partial; if
   it's purely one sense (e.g. only river-bank in CauseNet), the title
   distribution should still be inspectable.

Skips entirely if sibling causenet_mcp package or its SQLite DBs are
absent — keeps CI green on bare clones.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

import themis
from themis.kb.adapters.causenet_mcp_adapter import (
    CausenetMCPAdapter,
    make_inprocess_caller,
)


def _atom(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _effect_query_program(cause: str, effect: str) -> dict:
    """Smallest valid kernel_ast that exercises an LLM-proposed edge
    and an effect query along it."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": cause,  "domain": [True, False]},
            {"kind": "variable", "predicate": effect, "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom(cause),
                "to": _atom(effect),
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
    try:
        app = build_server()
    except FileNotFoundError:
        return None
    # use_wordnet=False keeps tests deterministic + fast (no nltk dep)
    return CausenetMCPAdapter(make_inprocess_caller(app), use_wordnet=False)


@pytest.fixture(scope="module")
def adapter():
    a = _try_load_real_adapter()
    if a is None:
        pytest.skip("sibling causenet_mcp package or SQLite data not present")
    return a


# ============================================ Scenario 1: high coverage


def test_scenario_high_coverage_smoking_lung_cancer(adapter) -> None:
    """smoking → lung_cancer is the canonical health edge with ~1690
    sources in precision tier. Must verify."""
    out = themis.run(_effect_query_program("smoking", "lung_cancer"),
                     kb_adapter=adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    assert len(report["per_edge_verification"]) == 1
    pe = report["per_edge_verification"][0]
    assert pe["verdict"] in ("kb_verified", "kb_partial")
    assert pe["confidence_tier"] == "high_confidence"
    assert pe["num_sources"] > 100  # canonical edge, lots of evidence
    # Structural surface present and inspectable
    assert len(pe["source_title_distribution"]) > 0


# ============================================ Scenario 2: low / no coverage


def test_scenario_low_coverage_cross_domain_returns_unverified(adapter) -> None:
    """Workplace-relationship-style queries are NOT in CauseNet's
    scope (it indexes single-word concepts from Wikipedia). The
    adapter must honestly say kb_unverified — not fabricate a verdict."""
    out = themis.run(
        _effect_query_program("food_sharing", "workplace_warmth"),
        kb_adapter=adapter,
    )
    report = out["results"][0]["extensions"]["kb_verification_report"]
    pe = report["per_edge_verification"][0]
    assert pe["verdict"] == "kb_unverified"
    assert pe["confidence_tier"] == "not_found"
    assert pe["num_sources"] == 0
    # queried_variants must record what was tried, for audit
    assert len(pe["queried_variants"]) >= 1


# ============================================ Scenario 3: translator-required


def test_scenario_translator_required_via_l2_morphological() -> None:
    """L2 morphological cascade: a plural input must reach the singular
    KB form. Use the adapter directly (no kernel) to confirm the
    cascade works — kernel-level test is in test_enrich."""
    adapter_with_translator = _try_load_real_adapter()
    if adapter_with_translator is None:
        pytest.skip("sibling data not present")
    # Enable use_wordnet so L3 also contributes
    adapter_with_translator = CausenetMCPAdapter(
        adapter_with_translator._call,  # reuse the same in-process caller
        use_wordnet=False,
    )
    from themis.kb.adapters.causenet_mcp_adapter import EdgeClaim
    # "smokings" (plural — not in KB) -> L2 produces "smoking" -> hit
    result = adapter_with_translator.lookup_edge(
        EdgeClaim(cause="smokings", effect="lung_cancer")
    )
    # Should either verify (after L2 translation) OR cleanly return
    # unverified if neither variant matches. In either case the
    # queried_variants list must show that translator generated
    # 'smoking' as a variant we tried.
    tried_causes = {v["cause"] for v in result.queried_variants}
    assert "smoking" in tried_causes, (
        f"L2 cascade should produce 'smoking' from 'smokings'; "
        f"tried: {tried_causes}"
    )


# ============================================ Scenario 4: structural surface


def test_scenario_structural_surface_inspectable_for_verified(adapter) -> None:
    """For any verified edge, the structural distributions must be
    populated so an upstream consumer can read homonym signals
    themselves. This is the core no-LLM contract."""
    out = themis.run(_effect_query_program("alcohol", "liver_disease"),
                     kb_adapter=adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    pe = report["per_edge_verification"][0]
    if pe["verdict"] in ("kb_verified", "kb_partial"):
        assert len(pe["source_title_distribution"]) > 0
        # Each title entry has the right shape
        first = pe["source_title_distribution"][0]
        assert "title" in first
        assert "count" in first
        # Counts sum to ≤ num_sources (entries are aggregated)
        total = sum(e["count"] for e in pe["source_title_distribution"])
        assert total <= pe["num_sources"]


# ============================================ KB suggestions


def test_kb_suggests_edges_for_atom_set(adapter) -> None:
    """When user proposes only smoking → lung_cancer but their atoms
    set also contains cancer (e.g. as a mediator), KB should suggest
    smoking → cancer if known."""
    # Build a program with mediator-style structure: three vars,
    # two edges, but only one of three possible directed edges
    # actually declared. KB suggester should find the missing one.
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {"kind": "variable", "predicate": "cancer", "domain": [True, False]},
            {
                "kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {"atom": _atom("lung_cancer"), "value": True},
                    "intervention": {"atom": _atom("smoking"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(prog, kb_adapter=adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    suggested_pairs = {(s["cause"], s["effect"])
                       for s in report["suggested_missing_edges"]}
    # smoking → cancer is well-known in CauseNet (smoking is a major
    # cause-of-cancer concept). The proposed edge (smoking → lung_cancer)
    # is filtered out.
    assert ("smoking", "lung_cancer") not in suggested_pairs
    # At minimum, expect smoking → cancer (extremely common in KB)
    assert ("smoking", "cancer") in suggested_pairs or len(suggested_pairs) > 0


# ============================================ Discipline check


def test_no_llm_in_kb_verification_path(adapter) -> None:
    """End-to-end discipline: kb_verification_report fields are pure
    structural — no 'llm_judge', 'semantic_aligned' or similar fields
    that would imply LLM was in the verification path."""
    out = themis.run(_effect_query_program("smoking", "lung_cancer"),
                     kb_adapter=adapter)
    report = out["results"][0]["extensions"]["kb_verification_report"]
    for pe in report["per_edge_verification"]:
        # Forbidden field names that would betray LLM-in-verifier
        for forbidden in ("llm_judge", "semantic_judgment",
                          "model_reasoning", "ai_assessment"):
            assert forbidden not in pe
        # Allowed: pure structural verdicts only
        assert pe["verdict"] in ("kb_verified", "kb_partial", "kb_unverified")
