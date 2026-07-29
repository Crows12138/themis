"""Phase 7.3 S.IVN.2-4 — IV dispatch + verifier + schema integration."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _iv_ast():
    """Z → X → Y with X ↔ Y latent. IV dispatch fires after backdoor +
    front-door both fail (front-door fails because Z → X → Y is the
    single directed path but Z itself has no backdoor-blocking
    mediator)."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
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


def _iv_data(n=3000, seed=0, true_late=1.5):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    p_x = 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u)))
    x = rng.random(n) < p_x
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


# ============================================ dispatch


def test_dispatch_picks_iv_when_backdoor_and_frontdoor_fail():
    df = _iv_data(n=3000, seed=0, true_late=1.5)
    out = themis.estimate(_iv_ast(), df, ci_bootstrap=0)
    result = out["results"][0]

    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "iv_wald"
    assert est["instrument"] == "z"
    assert est["conditioning"] == []
    assert abs(est["point"] - 1.5) < 0.4


def test_dispatch_iv_verify_round_trips():
    df = _iv_data(n=500, seed=0)
    ast = _iv_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    themis.verify(ast, out["results"][0])


def test_dispatch_iv_bootstrap_ci():
    df = _iv_data(n=800, seed=0)
    out = themis.estimate(
        _iv_ast(), df, ci_bootstrap=100, random_state=1,
    )
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_lower"] <= est["point"] <= est["ci_upper"]


def test_dispatch_iv_prefers_backdoor_when_both_available():
    """If backdoor works, IV must not fire (dispatch priority)."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            # Observable confounder Z; backdoor via {z} works
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
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    y = 1.0 * z + 2.0 * x.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"z": z, "x": x, "y": y})
    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_linear"


def test_a_conditional_query_gets_no_unconditional_iv_answer():
    """A Wald ratio has no conditional form, so it cannot answer P(Y|do(X), C).

    The identification layer refuses this combination explicitly. The
    estimation layer's guard was written separately and did not: it shipped
    a stratified Wald whose strata are the INSTRUMENT's conditioning set,
    not the query's ``given``. The proof that the number answered neither
    question is that conditioning on c=True and on c=False produced the
    same value to the last bit — so this test asks both, and neither may
    come back as an IV estimate.
    """
    def _ast(c_value):
        return {
            "version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "z", "domain": [True, False]},
                {"kind": "variable", "predicate": "c", "domain": [True, False]},
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "bidirected",
                 "left": _atom("x"), "right": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [{"atom": _atom("c"), "value": c_value}],
                }},
            ],
        }

    rng = np.random.default_rng(0)
    n = 3000
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    c = rng.random(n) < 0.5
    x = rng.random(n) < 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u)))
    y = 1.5 * x.astype(float) + 0.8 * c.astype(float) + 2.0 * u
    df = pd.DataFrame({"z": z, "c": c, "x": x, "y": y})

    for c_value in (True, False):
        result = themis.estimate(_ast(c_value), df, ci_bootstrap=0)["results"][0]
        method = (result.get("numeric_estimate") or {}).get("method", "")
        assert not method.startswith("iv_"), (
            f"given c={c_value} was answered by {method!r}"
        )


def test_dispatch_iv_skips_when_wald_denominator_zero():
    """Pathological data (Z has no effect on X) should make dispatch
    silently skip the IV path rather than crash."""
    ast = _iv_ast()
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "x": np.ones(n, dtype=bool),  # constant X → Wald denom is 0
        "y": rng.standard_normal(n),
    })
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Estimator raised, dispatch caught, no numeric_estimate attached
    assert "numeric_estimate" not in result
