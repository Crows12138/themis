"""Phase 7.2 S.FDN.2 + S.FDN.3 — front-door dispatch + verifier integration.

End-to-end: an ADMG with X ↔ Y latent (backdoor impossible) and a valid
single-mediator front-door should go through themis.estimate and
return a front-door numeric estimate. themis.verify must round-trip.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _frontdoor_ast():
    """X → M → Y, X ↔ Y latent. Backdoor blocked, front-door works via M."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
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


def _frontdoor_data(n=2000, seed=0, true_my_coef=1.0):
    """DGP matching the X↔Y-latent ADMG above."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    m = rng.random(n) < (1 / (1 + np.exp(-(2.0 * x.astype(float) - 1))))
    y = (
        true_my_coef * m.astype(float)
        + 2.0 * u
        + rng.standard_normal(n) * 0.3
    )
    return pd.DataFrame({"x": x, "m": m, "y": y})


# ============================================ dispatch


def test_dispatch_picks_frontdoor_when_backdoor_fails():
    df = _frontdoor_data(n=3000, seed=0, true_my_coef=1.0)
    out = themis.estimate(_frontdoor_ast(), df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "frontdoor_linear"
    assert est["mediators"] == ["m"]
    # true ATE via front-door: 1.0 * (P(M=1|X=1) - P(M=1|X=0))
    # = 1.0 * (sigmoid(1) - sigmoid(-1)) ≈ 0.462
    assert abs(est["point"] - 0.462) < 0.10, (
        f"front-door estimate {est['point']} off target ~0.462"
    )


def test_dispatch_prefers_backdoor_when_both_available():
    """If backdoor is available, the 7.1 path should fire first — the
    front-door branch is only the fallback when minimal_adjustment_sets
    returns empty."""
    # Confounded graph with observable Z: backdoor via {z} works
    ast = {
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
    rng = np.random.default_rng(0)
    n = 500
    z = rng.standard_normal(n)
    x_data = rng.random(n) < (1 / (1 + np.exp(-z)))
    y_data = 1.0 * z + 2.0 * x_data.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x_data, "z": z, "y": y_data})

    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_linear"
    assert "adjustment" in est


def test_frontdoor_estimate_verify_round_trip():
    df = _frontdoor_data(n=500, seed=0)
    ast = _frontdoor_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Must not raise
    themis.verify(ast, result)


def test_dispatch_skips_frontdoor_when_continuous_mediator():
    """v1 restriction: front-door numeric doesn't support continuous
    mediators. Dispatch should skip gracefully rather than blowing up."""
    ast = _frontdoor_ast()
    rng = np.random.default_rng(0)
    n = 200
    # Make M continuous instead of bool
    df = pd.DataFrame({
        "x": rng.random(n) < 0.5,
        "m": rng.standard_normal(n),  # continuous!
        "y": rng.standard_normal(n),
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Estimation should have been skipped
    assert "numeric_estimate" not in result


def test_dispatch_bootstrap_ci_populated():
    df = _frontdoor_data(n=500, seed=0)
    out = themis.estimate(
        _frontdoor_ast(), df, ci_bootstrap=50, random_state=1,
    )
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_upper"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]
