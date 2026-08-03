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
from themis import refusals


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


def test_a_continuous_mediator_is_refused_out_loud():
    """v1 restriction: front-door numeric does not support continuous
    mediators. It used to be enough that dispatch "skipped gracefully" —
    which is what a silent refusal looks like from inside the test that
    permits it. The caller got no number and no reason, and the report
    rendered the identification verdict in the answer slot."""
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
    assert "numeric_estimate" not in result

    failure = result["estimator_failure"]
    assert failure["estimator"] == "frontdoor"
    assert failure["failure_type"] == refusals.CONTINUOUS_MEDIATOR
    assert failure["kind"] == refusals.KIND_UNBUILT
    assert failure["details"]["mediator"] == "m"


def _frontdoor_categorical_ast():
    """X → M → Y, X ↔ Y latent, with M a 3-level categorical mediator."""
    ast = _frontdoor_ast()
    for st in ast["statements"]:
        if st.get("kind") == "variable" and st.get("predicate") == "m":
            st["domain"] = [0, 1, 2]
    return ast


def _frontdoor_categorical_data(n=8000, seed=0):
    """Same X↔Y-latent ADMG but M is a 3-level categorical mediator.

    True front-door ATE is analytic: Σ_m [P(M=m|X=1)−P(M=m|X=0)]·g(m) = 1.25.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    probs0 = np.array([0.6, 0.3, 0.1])
    probs1 = np.array([0.1, 0.3, 0.6])
    m = np.empty(n, dtype=int)
    for xi in (0, 1):
        mask = x == bool(xi)
        m[mask] = rng.choice(3, size=int(mask.sum()),
                             p=(probs1 if xi == 1 else probs0))
    g = np.array([0.0, 1.0, 2.5])
    y = g[m] + 2.0 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "m": m.astype(int), "y": y})
    return df, float(((probs1 - probs0) * g).sum())


def test_dispatch_frontdoor_categorical_mediator():
    """A multi-valued (3-level) mediator flows through the full
    run→estimate→verify pipeline and recovers the analytic ATE."""
    df, true_ate = _frontdoor_categorical_data(n=8000, seed=0)
    ast = _frontdoor_categorical_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "frontdoor_linear"
    assert est["mediators"] == ["m"]
    assert abs(est["point"] - true_ate) < 0.12, (
        f"categorical front-door estimate {est['point']} off ~{true_ate:.3f}"
    )
    # verifier metadata audit must round-trip on the categorical case too
    themis.verify(ast, result)


def test_dispatch_bootstrap_ci_populated():
    df = _frontdoor_data(n=500, seed=0)
    out = themis.estimate(
        _frontdoor_ast(), df, ci_bootstrap=50, random_state=1,
    )
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_upper"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]
