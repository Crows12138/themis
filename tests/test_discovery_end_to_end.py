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
from tests import caveats


def _chain_lingam_dgp(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """x → m → y linear chain with exponential noise (non-Gaussian so
    LiNGAM can fully orient). Returns continuous data for tests that
    don't pass ``bool_predicates``."""
    rng = np.random.default_rng(seed)
    x = rng.exponential(1.0, n) - 1.0
    m = 2.0 * x + rng.exponential(0.3, n) - 0.3
    y = 2.0 * m + rng.exponential(0.3, n) - 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _chain_binary_dgp(n: int = 2000, seed: int = 0) -> pd.DataFrame:
    """Binarized version of ``_chain_lingam_dgp`` — for tests that
    declare ``bool_predicates`` and need the column dtypes to honestly
    match. Median-split on each column."""
    df = _chain_lingam_dgp(n=n, seed=seed)
    return (df > df.median()).astype(int)


def test_lingam_discovery_to_kernel_run_surfaces_must_disclose_caveats():
    df = _chain_lingam_dgp()
    disc = discover_graph(df, algorithm="lingam", random_state=42)
    assert ("x", "m") in disc.directed_edges
    assert ("m", "y") in disc.directed_edges

    ast = discovery_to_kernel_ast(
        disc,
        bool_predicates=(),
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

    explanation = caveats.text(result)
    # Both layers land in explanation as ⚠ lines
    assert "LINGAM" in explanation
    assert "学出" in explanation


def test_discovery_kernel_ast_carries_discovery_source_annotation():
    """Every directed / bidirected edge in the suggestion must carry
    ``annotations.source = "discovery:<algo>"`` — that's the contract
    the gap classifier relies on to flag non-evidence edges."""
    df = _chain_lingam_dgp(n=500)
    disc = discover_graph(df, algorithm="lingam", random_state=42)
    ast = discovery_to_kernel_ast(disc, bool_predicates=())

    cause_stmts = [
        s for s in ast["statements"] if s["kind"] == "cause"
    ]
    assert cause_stmts
    for s in cause_stmts:
        assert s["annotations"]["source"] == "discovery:lingam"


def test_lingam_on_gaussian_data_detects_assumption_violation():
    """LiNGAM identifiability requires non-Gaussian noise — running it
    on near-Gaussian data is the canonical 'algorithm misuse passes
    silently' bug. The detection should flag this empirically and the
    caveat channel must surface it."""
    rng = np.random.default_rng(42)
    n = 500
    a = rng.normal(0, 1, n)
    b = 0.5 * a + rng.normal(0, 1, n)
    df = pd.DataFrame({"a": a, "b": b})

    disc = discover_graph(df, algorithm="lingam", random_state=42)
    assert disc.assumption_violations  # non-empty
    assert any("高斯" in v for v in disc.assumption_violations)

    ast = discovery_to_kernel_ast(disc, bool_predicates=())
    ast["statements"].append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "cause",
            "from": {"predicate": "a",
                     "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": "b",
                   "args": [{"type": "const", "name": "me"}]},
        },
    })
    out = themis.run(ast)
    explanation = caveats.text(out["results"][0])
    assert "非高斯" in explanation
    assert "边的方向基本是任意的" in explanation


def test_lingam_on_non_gaussian_data_no_violation_flag():
    """Companion: when LiNGAM's assumption is satisfied (clearly non-
    Gaussian data), no violation should fire — caveat channel must
    not false-alarm."""
    rng = np.random.default_rng(0)
    n = 2000
    a = rng.exponential(1.0, n) - 1.0
    b = 2.0 * a + rng.exponential(0.3, n) - 0.3
    df = pd.DataFrame({"a": a, "b": b})

    disc = discover_graph(df, algorithm="lingam", random_state=42)
    assert disc.assumption_violations == ()


def test_domain_mismatch_raises_when_bool_predicates_lie():
    """Real test caught: a普通 user with continuous data who marks
    columns as bool gets a kernel_ast that's syntactically valid but
    semantically lying (kernel reasons over [True, False] domain when
    the data has 100s of unique values). discovery_to_kernel_ast must
    refuse — this is the type of silent failure the geometric caveat
    channel can't fix because the lie is in the inputs, not the
    output."""
    import pytest
    from themis.estimation.discovery import DomainMismatchError

    df = _chain_lingam_dgp(n=500)  # continuous
    disc = discover_graph(df, algorithm="lingam", random_state=42)

    with pytest.raises(DomainMismatchError, match="continuous"):
        discovery_to_kernel_ast(disc, bool_predicates=("x", "m", "y"))


def test_domain_match_passes_when_bool_predicates_honest():
    """Companion: when the data really is bool (≤2 unique values),
    declaring bool_predicates passes. Detection is empirical — based
    on actual unique-value count, not user assertion."""
    df = _chain_binary_dgp(n=500)
    disc = discover_graph(df, algorithm="pc", alpha=0.05)
    # Should not raise.
    ast = discovery_to_kernel_ast(disc, bool_predicates=("x", "m", "y"))
    bool_vars = [
        s for s in ast["statements"]
        if s["kind"] == "variable" and s.get("domain") == [True, False]
    ]
    assert len(bool_vars) == 3


def test_pc_with_small_sample_detects_assumption_violation():
    """PC at sub-200 sample sizes has weak conditional independence
    tests; warn empirically."""
    rng = np.random.default_rng(0)
    n = 100
    a = rng.standard_normal(n)
    b = 0.5 * a + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"a": a, "b": b})

    disc = discover_graph(df, algorithm="pc", alpha=0.05)
    assert any("sample size" in v for v in disc.assumption_violations)


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
    ast = discovery_to_kernel_ast(disc, bool_predicates=())
    ambs = (ast.get("extensions") or {}).get("ambiguities") or []
    if not disc.ambiguous_edges:
        return
    assert ambs
    assert all(a["kind"] == "ambiguous_orientation" for a in ambs)
