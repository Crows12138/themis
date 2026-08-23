"""Phase 8.1.2 — the "stronger proposer".

Extends the discovery wrapper (PC/FCI/LiNGAM) with:
- a deterministic, diagnostics-driven ``auto`` selector that also picks
  the discrete-appropriate CI test / score function,
- GES (score-based) as a fourth algorithm,
- bootstrap per-edge stability scores surfaced as
  ``annotations.confidence`` on the proposal.

The point is a *better suggestion* — the graph is still a proposal the
agent must accept/reject, but now it explains why this algorithm was
chosen and how stable each edge is under resampling.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.discovery import (
    DataDiagnostics,
    discover_graph,
    discovery_to_kernel_ast,
)
from themis import gaps as _gaps


# ============================================ helpers


def _chain(n=1500, seed=0, non_gaussian=False):
    """x → m → y linear chain (Gaussian or exponential-noise)."""
    rng = np.random.default_rng(seed)
    if non_gaussian:
        x = rng.exponential(1.0, n) - 1.0
        m = 2.0 * x + rng.exponential(0.3, n) - 0.3
        y = 2.0 * m + rng.exponential(0.3, n) - 0.3
    else:
        x = rng.standard_normal(n)
        m = 2.0 * x + rng.standard_normal(n) * 0.3
        y = 2.0 * m + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


def _discrete_chain(n=1500, seed=1):
    """a → b → c binary chain (noisy copies)."""
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 2, n)
    b = np.where(rng.random(n) < 0.9, a, 1 - a)
    c = np.where(rng.random(n) < 0.9, b, 1 - b)
    return pd.DataFrame({"a": a, "b": b, "c": c})


def _cause_query(frm="x", to="y"):
    return {
        "kind": "query", "id": "q",
        "query": {
            "kind": "cause",
            "from": {"predicate": frm, "args": [{"type": "const", "name": "me"}]},
            "to": {"predicate": to, "args": [{"type": "const", "name": "me"}]},
        },
    }


# ============================================ diagnostics


def test_diagnostics_populated_for_continuous():
    r = discover_graph(_chain(non_gaussian=False), algorithm="pc")
    d = r.data_diagnostics
    assert isinstance(d, DataDiagnostics)
    assert d.n_samples == 1500 and d.n_variables == 3
    assert d.n_continuous == 3 and d.n_discrete == 0 and d.n_bool == 0
    assert d.frac_non_gaussian == pytest.approx(0.0, abs=1e-9)


def test_diagnostics_detects_non_gaussian():
    r = discover_graph(_chain(non_gaussian=True), algorithm="lingam")
    assert r.data_diagnostics.frac_non_gaussian >= 0.5


def test_diagnostics_flags_small_sample():
    r = discover_graph(_chain(n=120, non_gaussian=False), algorithm="pc")
    assert any("样本量" in note for note in r.data_diagnostics.notes)


# ============================================ selection (auto)


def test_auto_pc_for_gaussian_records_rationale():
    r = discover_graph(_chain(non_gaussian=False), algorithm="auto")
    assert r.algorithm == "pc"
    assert r.indep_test == "fisherz"
    assert "PC" in r.selection_rationale


def test_auto_lingam_when_non_gaussian_and_large_n():
    r = discover_graph(_chain(n=1000, non_gaussian=True), algorithm="auto")
    assert r.algorithm == "lingam"
    assert "LiNGAM" in r.selection_rationale


def test_auto_falls_back_to_pc_when_non_gaussian_but_small_n():
    # Non-Gaussian but N below the LiNGAM threshold → fewest-assumption PC.
    r = discover_graph(_chain(n=300, non_gaussian=True), algorithm="auto")
    assert r.algorithm == "pc"


def test_selection_is_deterministic():
    r1 = discover_graph(_chain(n=1000, non_gaussian=True), algorithm="auto")
    r2 = discover_graph(_chain(n=1000, non_gaussian=True), algorithm="auto")
    assert r1.algorithm == r2.algorithm
    assert r1.selection_rationale == r2.selection_rationale


# ============================================ discrete-appropriate CI test / score


def test_discrete_data_auto_uses_chisq():
    r = discover_graph(_discrete_chain(), algorithm="auto")
    assert r.algorithm == "pc"
    assert r.indep_test == "chisq"
    assert r.data_diagnostics.n_continuous == 0


def test_continuous_pc_uses_fisherz():
    r = discover_graph(_chain(), algorithm="pc")
    assert r.indep_test == "fisherz"


# ============================================ GES


def test_ges_finds_chain_skeleton():
    r = discover_graph(_chain(non_gaussian=False), algorithm="ges")
    assert r.algorithm == "ges"
    assert r.score_func == "local_score_BIC"
    skeleton = set()
    for s, d in r.directed_edges:
        skeleton.add(frozenset({s, d}))
    for pair in (*r.ambiguous_edges, *r.bidirected_edges):
        skeleton.add(pair)
    assert frozenset({"x", "m"}) in skeleton
    assert frozenset({"m", "y"}) in skeleton
    assert frozenset({"x", "y"}) not in skeleton


def test_ges_on_discrete_uses_bdeu_score():
    r = discover_graph(_discrete_chain(), algorithm="ges")
    assert r.algorithm == "ges"
    assert r.score_func == "local_score_BDeu"


# ============================================ GRaSP (permutation-based, added via the registry)


def test_grasp_finds_chain_skeleton():
    r = discover_graph(_chain(non_gaussian=False), algorithm="grasp")
    assert r.algorithm == "grasp"
    assert r.score_func == "local_score_BIC_from_cov"
    skeleton = set()
    for s, d in r.directed_edges:
        skeleton.add(frozenset({s, d}))
    for pair in (*r.ambiguous_edges, *r.bidirected_edges):
        skeleton.add(pair)
    assert frozenset({"x", "m"}) in skeleton
    assert frozenset({"m", "y"}) in skeleton
    assert frozenset({"x", "y"}) not in skeleton


def test_grasp_on_discrete_uses_bdeu_score():
    r = discover_graph(_discrete_chain(), algorithm="grasp")
    assert r.algorithm == "grasp"
    assert r.score_func == "local_score_BDeu"


def test_grasp_bootstrap_confidence():
    r = discover_graph(
        _chain(non_gaussian=False, n=1200), algorithm="grasp", n_bootstrap=15,
    )
    assert r.n_bootstrap_ok > 0
    assert r.skeleton_confidence  # adjacency stability recorded
    for _a, _b, conf in r.skeleton_confidence:
        assert 0.0 <= conf <= 1.0


# ============================================ registry (the algorithm knowledge base)


def test_registry_has_all_five_algorithms():
    from themis.estimation.discovery import _ALGORITHMS
    assert set(_ALGORITHMS) == {"pc", "fci", "ges", "grasp", "lingam"}


def test_auto_only_resolves_to_auto_eligible_algorithms():
    # ges / grasp / fci are explicit opt-in (auto=None) — auto must resolve
    # to pc or lingam only, whatever the data looks like.
    for kwargs in ({}, {"non_gaussian": True}):
        r = discover_graph(_chain(n=1000, **kwargs), algorithm="auto")
        assert r.algorithm in ("pc", "lingam")
    r_disc = discover_graph(_discrete_chain(), algorithm="auto")
    assert r_disc.algorithm in ("pc", "lingam")


def test_registry_specs_are_well_formed():
    from themis.estimation.discovery import _ALGORITHMS
    for name, spec in _ALGORITHMS.items():
        assert spec.name == name
        assert callable(spec.run)
        assert spec.auto is None or callable(spec.auto)
        assert spec.violations is None or callable(spec.violations)


# ============================================ bootstrap edge stability


def test_bootstrap_off_by_default():
    r = discover_graph(_chain(n=1000, non_gaussian=True), algorithm="lingam")
    assert r.n_bootstrap == 0
    assert r.edge_confidence == ()
    assert r.skeleton_confidence == ()


def test_bootstrap_populates_confidence_in_unit_interval():
    r = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=25,
    )
    assert r.n_bootstrap == 25
    assert r.n_bootstrap_ok > 0
    assert r.edge_confidence
    for _src, _dst, conf in r.edge_confidence:
        assert 0.0 <= conf <= 1.0


def test_bootstrap_true_edges_more_stable_than_spurious():
    """The payoff: the true chain edges survive nearly every resample,
    while a spurious edge (if it appears at all) is much less stable."""
    r = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=30,
    )
    conf = {(s, d): c for s, d, c in r.edge_confidence}
    assert conf.get(("x", "m"), 0.0) >= 0.8
    assert conf.get(("m", "y"), 0.0) >= 0.8
    if ("x", "y") in conf:
        assert conf[("x", "y")] < conf[("x", "m")]


def test_bootstrap_is_reproducible_under_fixed_seed():
    a = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=20,
    )
    b = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=20,
    )
    assert a.edge_confidence == b.edge_confidence
    assert a.skeleton_confidence == b.skeleton_confidence


# ============================================ kernel_ast plumbing


def test_kernel_ast_attaches_confidence_to_edges():
    r = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=25,
    )
    ast = discovery_to_kernel_ast(r, bool_predicates=())
    causes = [s for s in ast["statements"] if s["kind"] == "cause"]
    assert causes
    for s in causes:
        assert s["annotations"]["source"] == "discovery:lingam"
        assert "confidence" in s["annotations"]
        assert 0.0 <= s["annotations"]["confidence"] <= 1.0


def test_kernel_ast_has_no_confidence_without_bootstrap():
    r = discover_graph(_chain(n=1000, non_gaussian=True), algorithm="lingam")
    ast = discovery_to_kernel_ast(r, bool_predicates=())
    causes = [s for s in ast["statements"] if s["kind"] == "cause"]
    assert causes
    for s in causes:
        assert "confidence" not in s["annotations"]


def test_kernel_ast_metadata_carries_diagnostics_and_rationale():
    r = discover_graph(_chain(non_gaussian=False), algorithm="auto", n_bootstrap=10)
    meta = discovery_to_kernel_ast(r)["extensions"]["discovery_metadata"]
    assert meta["selection_rationale"]
    assert meta["indep_test"] == "fisherz"
    assert meta["n_bootstrap"] == 10
    assert meta["diagnostics"]["n_continuous"] == 3


def test_pc_ambiguities_carry_skeleton_confidence():
    r = discover_graph(
        _chain(non_gaussian=False, n=1500), algorithm="pc", n_bootstrap=20,
    )
    if not r.ambiguous_edges:
        pytest.skip("no ambiguous edges to check")
    ast = discovery_to_kernel_ast(r)
    ambs = ast.get("extensions", {}).get("ambiguities", [])
    assert any("skeleton_confidence" in a for a in ambs)


# ============================================ end-to-end: confidence survives run + surfaces


def test_confidence_kernel_ast_is_schema_valid_and_runs():
    r = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=20,
    )
    ast = discovery_to_kernel_ast(r, bool_predicates=(), query=_cause_query())
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


def test_bootstrap_confidence_surfaces_in_gap_report():
    r = discover_graph(
        _chain(n=1000, non_gaussian=True), algorithm="lingam", n_bootstrap=25,
    )
    ast = discovery_to_kernel_ast(r, bool_predicates=(), query=_cause_query())
    result = themis.run(ast)["results"][0]
    proposal_gaps = [
        g for g in result["data_gap_report"]["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    ]
    assert proposal_gaps
    assert any("自助法稳定度" in _gaps.described(g) for g in proposal_gaps)
