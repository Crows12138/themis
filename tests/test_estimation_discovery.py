"""Phase 8.1.1 — unit tests for the discovery wrapper."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.discovery import DiscoveryResult, discover_graph


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
    assert "PC" in result.note or "pc" in result.note.lower()


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
    with pytest.raises(ValueError, match="unknown algorithm"):
        discover_graph(df, algorithm="random_forest_discovery")


def test_no_usable_columns_rejected():
    df = pd.DataFrame({"name": ["a", "b", "c"] * 50})
    with pytest.raises(ValueError, match="no usable columns"):
        discover_graph(df)


# ============================================ column subset


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
