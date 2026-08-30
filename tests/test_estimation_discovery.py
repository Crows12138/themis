"""Phase 8.1.1 — unit tests for the discovery wrapper."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.discovery import (
    DiscoveryError,
    DiscoveryResult,
    discover_graph,
    discovery_to_kernel_ast,
)
from themis.estimation.refusal_words import Refuses


# ============================================ helpers


def _chain_dgp(n=2000, seed=0, non_gaussian=False):
    """x → m → y linear chain."""
    rng = np.random.default_rng(seed)
    if non_gaussian:
        # Exponential noise → clearly skewed → LiNGAM identifies orientation
        x = rng.exponential(1.0, n) - 1.0
        m = 2.0 * x + rng.exponential(0.3, n) - 0.3
        y = 2.0 * m + rng.exponential(0.3, n) - 0.3
    else:
        x = rng.standard_normal(n)
        m = 2.0 * x + rng.standard_normal(n) * 0.3
        y = 2.0 * m + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


# ============================================ PC


def test_pc_finds_chain_skeleton():
    """PC on a Gaussian chain may leave edges undirected (CPDAG) but
    should discover the x-m and m-y skeleton."""
    df = _chain_dgp(n=2000, seed=0)
    result = discover_graph(df, algorithm="pc", alpha=0.05)
    assert result.algorithm == "pc"

    # Combine all edge buckets — we just want to know the skeleton
    skeleton = set()
    for src, dst in result.directed_edges:
        skeleton.add(frozenset({src, dst}))
    for pair in result.ambiguous_edges:
        skeleton.add(pair)
    for pair in result.bidirected_edges:
        skeleton.add(pair)

    assert frozenset({"x", "m"}) in skeleton
    assert frozenset({"m", "y"}) in skeleton
    # PC should NOT add a spurious x-y direct edge in a true chain
    assert frozenset({"x", "y"}) not in skeleton


def test_pc_returns_metadata():
    df = _chain_dgp(n=200, seed=0)
    result = discover_graph(df, algorithm="pc", alpha=0.05)
    assert isinstance(result, DiscoveryResult)
    assert result.alpha == 0.05
    assert result.sample_size == 200
    assert result.columns == ("x", "m", "y")
    assert len(result.data_hash) == 64
    # The note names the algorithm in a slot rather than in its text, so
    # the fact is read off the fact and not off the sentence around it.
    assert result.note[0]["token"] == "found_this_many_edges"
    assert result.note[0]["said"]["algorithm"] == "PC"


# ============================================ LiNGAM


def test_lingam_directs_chain_under_non_gaussian_noise():
    """With non-Gaussian noise, LiNGAM should direct edges of the chain
    x → m → y."""
    df = _chain_dgp(n=2000, seed=0, non_gaussian=True)
    result = discover_graph(df, algorithm="lingam", random_state=42)
    assert result.algorithm == "lingam"

    directed = set(result.directed_edges)
    # Expect x→m and m→y; LiNGAM may also include x→y due to fitting noise,
    # but the two chain edges must both be present.
    assert ("x", "m") in directed
    assert ("m", "y") in directed
    # LiNGAM produces no bidirected / ambiguous edges by design
    assert result.bidirected_edges == ()
    assert result.ambiguous_edges == ()


def test_lingam_deterministic_under_fixed_seed():
    df = _chain_dgp(n=500, seed=0, non_gaussian=True)
    r1 = discover_graph(df, algorithm="lingam", random_state=42)
    r2 = discover_graph(df, algorithm="lingam", random_state=42)
    assert r1.directed_edges == r2.directed_edges
    assert r1.data_hash == r2.data_hash


# ============================================ FCI


def test_fci_runs_without_crashing_on_chain():
    """FCI is more conservative than PC; just check it returns a valid
    DiscoveryResult with the right metadata."""
    df = _chain_dgp(n=1000, seed=0)
    result = discover_graph(df, algorithm="fci", alpha=0.05)
    assert result.algorithm == "fci"
    assert isinstance(result, DiscoveryResult)
    # FCI may produce CIRCLE endpoints → ambiguous edges are common
    total_edges = (
        len(result.directed_edges)
        + len(result.bidirected_edges)
        + len(result.ambiguous_edges)
    )
    assert total_edges >= 1


# ============================================ auto


def test_auto_picks_lingam_for_non_gaussian():
    df = _chain_dgp(n=1000, seed=0, non_gaussian=True)
    result = discover_graph(df, algorithm="auto")
    assert result.algorithm == "lingam"


def test_auto_picks_pc_for_gaussian():
    df = _chain_dgp(n=1000, seed=0, non_gaussian=False)
    result = discover_graph(df, algorithm="auto")
    assert result.algorithm == "pc"


# ============================================ error paths


def test_unknown_algorithm_rejected():
    df = _chain_dgp(n=100, seed=0)
    with pytest.raises(DiscoveryError) as raised:
        discover_graph(df, algorithm="random_forest_discovery")
    assert raised.value.species is Refuses.METHOD_IS_LIMITED_TO


def test_no_usable_columns_rejected():
    df = pd.DataFrame({"name": ["a", "b", "c"] * 50})
    with pytest.raises(DiscoveryError) as raised:
        discover_graph(df)
    assert raised.value.species is Refuses.NO_USABLE_COLUMNS


# ============================================ column subset


def test_discovery_to_kernel_ast_directed_only_lingam():
    """LiNGAM produces directed edges only — kernel_ast suggestion has
    them all as cause statements with source=discovery."""
    df = _chain_dgp(n=2000, seed=0, non_gaussian=True)
    result = discover_graph(df, algorithm="lingam", random_state=42)
    suggestion = discovery_to_kernel_ast(
        result, bool_predicates=(),
    )

    assert suggestion["version"] == "0.1"
    assert suggestion["domain"] == {
        "objects": [{"kind": "object", "name": "me"}],
    }

    cause_stmts = [
        s for s in suggestion["statements"] if s["kind"] == "cause"
    ]
    var_stmts = [
        s for s in suggestion["statements"] if s["kind"] == "variable"
    ]
    bidir_stmts = [
        s for s in suggestion["statements"] if s["kind"] == "bidirected"
    ]

    assert len(var_stmts) == 3
    # LiNGAM directs the chain x→m→y → at least these two edges
    cause_pairs = {(s["from"]["predicate"], s["to"]["predicate"]) for s in cause_stmts}
    assert ("x", "m") in cause_pairs
    assert ("m", "y") in cause_pairs

    # No bidirected edges from LiNGAM
    assert bidir_stmts == []

    # All cause statements carry the discovery provenance
    for s in cause_stmts:
        assert s["annotations"]["source"] == "discovery:lingam"

    # No ambiguities (LiNGAM directs everything)
    ambs = suggestion.get("extensions", {}).get("ambiguities", [])
    assert ambs == []

    # discovery_metadata block carries provenance
    meta = suggestion["extensions"]["discovery_metadata"]
    assert meta["algorithm"] == "lingam"
    assert meta["sample_size"] == 2000
    assert len(meta["data_hash"]) == 64


def test_discovery_to_kernel_ast_pc_emits_ambiguities():
    """PC on Gaussian chain leaves edges undirected; ambiguities block
    must surface each undirected pair so the agent can disambiguate."""
    df = _chain_dgp(n=2000, seed=0)
    result = discover_graph(df, algorithm="pc", alpha=0.05)
    suggestion = discovery_to_kernel_ast(result)

    ambs = suggestion["extensions"]["ambiguities"]
    # At least one ambiguous edge is expected for a Gaussian chain
    assert len(ambs) >= 1
    for amb in ambs:
        assert amb["kind"] == "ambiguous_orientation"
        assert len(amb["endpoints"]) == 2
        assert "disambiguation_ask" in amb


def test_discovery_to_kernel_ast_with_bool_predicates():
    df = _chain_dgp(n=500, seed=0)
    df_bool = df.copy()
    df_bool["x"] = df_bool["x"] > 0
    result = discover_graph(
        df_bool, algorithm="pc", columns=("x", "m", "y"),
    )
    suggestion = discovery_to_kernel_ast(
        result, bool_predicates=("x",),
    )
    var_stmts = [
        s for s in suggestion["statements"] if s["kind"] == "variable"
    ]
    x_var = next(s for s in var_stmts if s["predicate"] == "x")
    assert x_var["domain"] == [True, False]
    # m and y left without explicit domain
    m_var = next(s for s in var_stmts if s["predicate"] == "m")
    assert "domain" not in m_var


def test_discovery_to_kernel_ast_with_query_appended():
    df = _chain_dgp(n=200, seed=0)
    result = discover_graph(df, algorithm="pc", alpha=0.05)
    query = {
        "kind": "query", "id": "q",
        "query": {
            "kind": "cause",
            "from": {"predicate": "x", "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": "y", "args": [{"type": "const", "name": "me"}]},
        },
    }
    suggestion = discovery_to_kernel_ast(result, query=query)
    query_stmts = [s for s in suggestion["statements"] if s["kind"] == "query"]
    assert len(query_stmts) == 1
    assert query_stmts[0]["id"] == "q"


def test_columns_parameter_restricts_search():
    df = _chain_dgp(n=500, seed=0)
    df["unused_col"] = np.random.default_rng(0).standard_normal(500)
    result = discover_graph(
        df, algorithm="pc", columns=("x", "m", "y"),
    )
    assert result.columns == ("x", "m", "y")
    # Confirm 'unused_col' is not in any edge bucket
    all_nodes = set()
    for src, dst in result.directed_edges:
        all_nodes.add(src); all_nodes.add(dst)
    for pair in (*result.ambiguous_edges, *result.bidirected_edges):
        all_nodes.update(pair)
    assert "unused_col" not in all_nodes
