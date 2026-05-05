"""Path B end-to-end: causal discovery → kernel_ast → themis.run.

Pins that the must-disclose caveat plumbing actually fires when
discovery feeds into the kernel:
- top-level ``graph_learned_from_data`` gap
- per-edge ``unverified_proposal_edge_on_query_path`` with discovery
  algorithm name in description
"""
from __future__ import annotations

import numpy as np
import pandas as pd

import themis
from themis.estimation.discovery import discover_graph, discovery_to_kernel_ast


def _chain_lingam_dgp(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """x → m → y linear chain with exponential noise (non-Gaussian so
    LiNGAM can fully orient)."""
    rng = np.random.default_rng(seed)
    x = rng.exponential(1.0, n) - 1.0
    m = 2.0 * x + rng.exponential(0.3, n) - 0.3
    y = 2.0 * m + rng.exponential(0.3, n) - 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


def test_lingam_discovery_to_kernel_run_surfaces_must_disclose_caveats():
    df = _chain_lingam_dgp()
    disc = discover_graph(df, algorithm="lingam", random_state=42)
    assert ("x", "m") in disc.directed_edges
    assert ("m", "y") in disc.directed_edges

    ast = discovery_to_kernel_ast(
        disc,
        bool_predicates=("x", "m", "y"),
        query={
            "kind": "query", "id": "q",
            "query": {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
            },
        },
    )

    out = themis.run(ast)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True

    gap_kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    # Top-level "the whole graph is learned" caveat
    assert "graph_learned_from_data" in gap_kinds
    # Per-edge "this edge is from a discovery algorithm" caveats
    proposal_gaps = [
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    ]
    assert len(proposal_gaps) >= 1

    explanation = result.get("explanation") or ""
    # Both layers land in explanation as ⚠ lines
    assert "LINGAM" in explanation
    assert "学出" in explanation


def test_discovery_kernel_ast_carries_discovery_source_annotation():
    """Every directed / bidirected edge in the suggestion must carry
    ``annotations.source = "discovery:<algo>"`` — that's the contract
    the gap classifier relies on to flag non-evidence edges."""
    df = _chain_lingam_dgp(n=500)
    disc = discover_graph(df, algorithm="lingam", random_state=42)
    ast = discovery_to_kernel_ast(disc, bool_predicates=("x", "m", "y"))

    cause_stmts = [
        s for s in ast["statements"] if s["kind"] == "cause"
    ]
    assert cause_stmts
    for s in cause_stmts:
        assert s["annotations"]["source"] == "discovery:lingam"


def test_pc_discovery_with_ambiguous_orientation_emits_ambiguity():
    """PC on a Gaussian chain leaves edges undirected (CPDAG). The
    kernel_ast suggestion must mark them as ambiguous so the renderer
    can ask the user to disambiguate."""
    rng = np.random.default_rng(0)
    n = 1500
    x = rng.standard_normal(n)
    m = 2.0 * x + rng.standard_normal(n) * 0.3
    y = 2.0 * m + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    disc = discover_graph(df, algorithm="pc", alpha=0.05)
    ast = discovery_to_kernel_ast(disc, bool_predicates=("x", "m", "y"))
    ambs = (ast.get("extensions") or {}).get("ambiguities") or []
    if not disc.ambiguous_edges:
        return
    assert ambs
    assert all(a["kind"] == "ambiguous_orientation" for a in ambs)
