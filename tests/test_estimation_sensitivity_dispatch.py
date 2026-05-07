"""Phase 8.2.2 — E-value auto-attachment to dispatched numeric estimates."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# ============================================ backdoor + bool outcome


def _confounded_bool_ast():
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


def _confounded_bool_data(n=2000, seed=0, true_ate=0.15):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    p_y = np.clip(0.2 + 0.1 * z + true_ate * x.astype(float), 0.01, 0.99)
    y = rng.random(n) < p_y
    return pd.DataFrame({"x": x, "z": z, "y": y})


def test_e_value_attached_for_backdoor_bool_outcome():
    df = _confounded_bool_data(n=2000, seed=0)
    out = themis.estimate(_confounded_bool_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_logistic"
    sa = est["sensitivity_analysis"]
    assert sa["e_value"] is not None
    assert sa["risk_ratio"] is not None
    assert sa["baseline_rate"] is not None
    assert "E-value" in sa["note"]


def test_e_value_attached_for_continuous_outcome_via_chinn():
    """Iter 124: backdoor on continuous Y now attaches a Chinn-2000-
    based E-value (SMD → RR ≈ exp(0.91·SMD), then VanderWeele-Ding
    formula). baseline_rate is None on this path because the
    conversion is fully standardisation-based."""
    rng = np.random.default_rng(0)
    n = 1000
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    y = 1.0 * z + 2.0 * x.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    out = themis.estimate(_confounded_bool_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_linear"
    sa = est.get("sensitivity_analysis")
    assert sa is not None, (
        "iter 124 wired Chinn E-value for continuous outcomes; "
        "sensitivity_analysis must be present"
    )
    assert sa["e_value"] is not None
    assert sa["baseline_rate"] is None
    assert "Chinn" in sa["note"]


# ============================================ front-door + bool outcome


def _frontdoor_bool_ast():
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


def test_e_value_attached_for_frontdoor_bool_outcome():
    rng = np.random.default_rng(0)
    n = 2000
    u = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-u)))
    m = rng.random(n) < (1 / (1 + np.exp(-(2.0 * x.astype(float) - 1))))
    p_y = np.clip(
        1 / (1 + np.exp(-(1.5 * m.astype(float) + 2.0 * u - 1))),
        0.01, 0.99,
    )
    y = rng.random(n) < p_y
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    out = themis.estimate(_frontdoor_bool_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "frontdoor_logistic"
    sa = est["sensitivity_analysis"]
    assert sa["e_value"] is not None


# ============================================ IV + bool outcome


def test_e_value_attached_for_iv_bool_outcome():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    rng = np.random.default_rng(0)
    n = 3000
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    x = rng.random(n) < (1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u))))
    p_y = np.clip(0.2 + 0.3 * x.astype(float) + 0.1 * u, 0.01, 0.99)
    y = rng.random(n) < p_y
    df = pd.DataFrame({"z": z, "x": x, "y": y})

    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "iv_wald"
    sa = est["sensitivity_analysis"]
    assert sa["e_value"] is not None


# ============================================ mediation + bool outcome


def test_e_value_uses_te_for_mediation():
    """Mediation decomposition has nde/nie/te — E-value computed on TE."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
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
    n = 1000
    x = rng.binomial(1, 0.5, n)
    m = rng.random(n) < (1 / (1 + np.exp(-(2 * x - 1))))
    p_y = np.clip(0.15 + 0.3 * m.astype(float) + 0.1 * x, 0.01, 0.99)
    y = rng.random(n) < p_y
    df = pd.DataFrame({"x": x.astype(bool), "m": m, "y": y})

    out = themis.estimate(ast, df)
    result = out["results"][0]
    est = result["numeric_estimate"]
    assert "decomposition" in est
    sa = est["sensitivity_analysis"]
    assert sa["e_value"] is not None
    # E-value should be based on TE point ≈ NDE + NIE
    te_point = est["decomposition"]["te"]["point"]
    assert abs(sa["risk_ratio"] - (sa["baseline_rate"] + te_point) / sa["baseline_rate"]) < 1e-6


# ============================================ verify still passes


def test_themis_verify_round_trips_with_e_value_attached():
    df = _confounded_bool_data(n=300, seed=0)
    ast = _confounded_bool_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    themis.verify(ast, out["results"][0])
