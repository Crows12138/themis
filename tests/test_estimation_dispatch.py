"""Phase 7.1 S.N.3 — end-to-end themis.estimate integration tests.

Validates that:
- effect query + data → numeric_estimate attached, status flips to
  numerically_solved
- adjustment set is recovered from the graph (not the data)
- point estimate is in the expected range for a known DGP
- mediation queries pass through untouched (7.4 territory)
- unidentifiable queries skip the estimator cleanly
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    # Z confounds X and Y
    x = rng.random(n) < (1 / (1 + np.exp(-0.8 * z)))
    y = 1.0 * z + true_ate * x.astype(float) + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "z": z, "y": y})


def _confounded_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


# ============================================ happy path


def test_effect_query_with_data_returns_numeric_estimate():
    df = _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "backdoor_linear"
    assert est["adjustment"] == ["z"]
    assert abs(est["point"] - 2.0) < 0.25
    assert est["treatment"] == "x"
    assert est["outcome"] == "y"
    assert est["sample_size"] == 1000


def test_backdoor_estimate_attaches_assumption_ledger():
    """Binary/linear backdoor estimate surfaces the same assumption ledger
    as dose-response: identification assumptions (invalidating) + the
    outcome-model functional form (distorting), severity-sorted. (The
    user's point: binary has an applicable version too — it was just not
    wired before.)"""
    df = _linear_confounded_dgp(n=1000, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=0)
    ext = out["results"][0]["extensions"]
    # mechanism_audit: the outcome regression form
    assert ext["mechanism_audit"]["mechanisms"][0]["form"] == "linear"
    # assumption_ledger: identification + functional_form, severity-sorted
    entries = ext["assumption_ledger"]["assumptions"]
    layers = [e["layer"] for e in entries]
    assert "identification" in layers
    assert "functional_form" in layers
    idx_id = min(i for i, e in enumerate(entries) if e["layer"] == "identification")
    idx_form = next(i for i, e in enumerate(entries) if e["layer"] == "functional_form")
    assert entries[idx_id]["severity"] == "invalidating"
    assert entries[idx_form]["severity"] == "distorting"
    assert idx_id < idx_form


def test_bootstrap_ci_populated_when_enabled():
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_upper"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]


def test_precision_budget_attached_when_ci_present():
    """Iter 152: backdoor numeric_estimate carries a precision_budget
    field with N-to-halve-CI hint. SE ∝ 1/√N → halving needs 4× N."""
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    est = out["results"][0]["numeric_estimate"]
    assert "precision_budget" in est
    pb = est["precision_budget"]
    assert "current_ci_half_width" in pb
    assert "n_to_halve_ci" in pb
    assert "hint" in pb
    # Halving needs ≈4× N; current N=500 → expect n_to_halve in ~[1900, 2050]
    # (round-up-50 grain). Loose bracket — exact integer depends on bootstrap.
    assert 1900 <= pb["n_to_halve_ci"] <= 2050, (
        f"n_to_halve_ci={pb['n_to_halve_ci']} out of expected ~4×N range"
    )


def test_precision_budget_carries_relative_width_for_mechanical_surfacing():
    """Iter 160: precision_budget.relative_width = half_width / |point|
    lets the renderer's '>30% of point' heuristic be mechanical instead
    of LLM judgment. true_ate=2.0 with N=500 → expect relative_width
    well below 0.3 (CI tight relative to point of magnitude 2)."""
    df = _linear_confounded_dgp(n=500, seed=0, true_ate=2.0)
    out = themis.estimate(_confounded_ast(), df, ci_bootstrap=100, random_state=1)
    pb = out["results"][0]["numeric_estimate"]["precision_budget"]
    assert "relative_width" in pb, (
        "relative_width missing — iter 160 mechanical-surface field "
        "not wired"
    )
    # Sanity: with N=500 and a 2.0 ATE, bootstrap CI should be much
    # tighter than 30% of point. Loose bracket, just confirm finiteness
    # and order-of-magnitude correctness.
    assert 0 < pb["relative_width"] < 1.0


def test_empty_adjustment_when_no_confounder():
    """X → Y with no backdoor: ATE identifiable with empty adjustment."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(200) < 0.5,
        "y": rng.random(200) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["adjustment"] == []


# ============================================ mediation passthrough


def test_mediation_query_now_runs_imai_estimator():
    """Phase 7.4: mediation queries get a numeric NDE/NIE/TE block via
    the Imai-via-statsmodels estimator. Status stays structurally_solved
    because the identification is the primary answer; numeric is detail."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "mediator": _atom("m"),
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(100) < 0.5,
        "m": rng.random(100) < 0.5,
        "y": rng.random(100) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Status stays structurally_solved — identification is primary answer
    assert result["status"] == "structurally_solved"
    # Mediation identification preserved
    assert "mediation_decomposition" in result["extensions"]
    # Numeric attached with a decomposition sub-block
    assert "numeric_estimate" in result
    est = result["numeric_estimate"]
    assert est["method"] in ("mediation_linear_imai", "mediation_logit_imai")
    assert "decomposition" in est
    for branch in ("nde", "nie", "te"):
        assert "point" in est["decomposition"][branch]
        assert "ci_lower" in est["decomposition"][branch]


# ============================================ unidentifiable passthrough


def test_unidentifiable_query_skips_numeric():
    """X ↔ Y latent confounder, no IV. Backdoor fails, front-door
    unavailable. 7.1 must not attempt numerical estimation — result
    stays as-is from identification layer."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected",
             "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": rng.random(100) < 0.5,
        "y": rng.random(100) < 0.5,
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Identification says needs_investigation — no numeric estimate
    assert "numeric_estimate" not in result


# ============================================ determinism


def test_themis_estimate_is_deterministic():
    df = _linear_confounded_dgp(n=300, seed=0)
    o1 = themis.estimate(_confounded_ast(), df, ci_bootstrap=50, random_state=42)
    o2 = themis.estimate(_confounded_ast(), df, ci_bootstrap=50, random_state=42)
    e1 = o1["results"][0]["numeric_estimate"]
    e2 = o2["results"][0]["numeric_estimate"]
    assert e1["point"] == e2["point"]
    assert e1["ci_lower"] == e2["ci_lower"]
    assert e1["ci_upper"] == e2["ci_upper"]
    assert e1["data_hash"] == e2["data_hash"]


# ============================================ identify query untouched


def test_identify_query_returns_unchanged():
    """identify query results should NOT get a numeric_estimate — they
    answer the structural question and have no data semantics."""
    ast = _confounded_ast()
    # Flip the query kind to identify
    ast["statements"][-1] = {
        "kind": "query", "id": "q", "query": {
            "kind": "identify",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": _atom("y"),
            "given": [],
        },
    }
    df = _linear_confounded_dgp(n=100, seed=0)
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert "numeric_estimate" not in result
