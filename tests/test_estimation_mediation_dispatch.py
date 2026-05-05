"""Phase 7.4 S.MN.2 — mediation dispatch integration end-to-end.

When the identification layer (6.mediation) returns strategy=nde_nie,
themis.estimate should attach an Imai-via-statsmodels NDE/NIE/TE
decomposition to result["numeric_estimate"].
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _clean_mediation_ast():
    return {
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


def _clean_med_data(n=2000, seed=0, nde_true=0.5, nie_true=2.0):
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    m = 2.0 * x + rng.standard_normal(n)
    y = nde_true * x + (nie_true / 2.0) * m + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


# ============================================ end-to-end


def test_clean_mediation_attaches_numeric_decomposition():
    df = _clean_med_data(n=2000, seed=0, nde_true=0.5, nie_true=2.0)
    out = themis.estimate(_clean_mediation_ast(), df, random_state=42)
    result = out["results"][0]

    # Identification stays primary
    assert result["status"] == "structurally_solved"
    decomp = result["extensions"]["mediation_decomposition"]
    assert decomp["strategy"] == "nde_nie"

    # Numeric attached
    est = result["numeric_estimate"]
    assert est["method"] == "mediation_linear_imai"
    assert est["mediator"] == "m"
    nde = est["decomposition"]["nde"]
    nie = est["decomposition"]["nie"]
    te = est["decomposition"]["te"]
    assert abs(nde["point"] - 0.5) < 0.2
    assert abs(nie["point"] - 2.0) < 0.3
    assert abs(te["point"] - 2.5) < 0.3

    # Real test caught: 'X 占多少比例' is the user's actual mediation
    # question. ``proportion_mediated = NIE / TE = 2.0 / 2.5 = 0.8``
    # surfaces in the decomposition block alongside the absolute
    # effects, with its own bootstrap CI from Imai 2010.
    pm = est["decomposition"]["proportion_mediated"]
    assert abs(pm["point"] - 0.8) < 0.15
    assert pm["ci_lower"] <= pm["point"] <= pm["ci_upper"]


def test_intermediate_confounder_skips_numeric():
    """Recanting witness — strategy=none means no numeric estimate."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("w")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
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
    n = 200
    df = pd.DataFrame({
        "x": rng.binomial(1, 0.5, n).astype(bool),
        "w": rng.binomial(1, 0.5, n).astype(bool),
        "m": rng.binomial(1, 0.5, n).astype(bool),
        "y": rng.binomial(1, 0.5, n).astype(bool),
    })
    out = themis.estimate(ast, df)
    result = out["results"][0]
    # Identification says strategy=none; numeric should NOT fire
    assert result["extensions"]["mediation_decomposition"]["strategy"] == "none"
    assert "numeric_estimate" not in result


def test_mediation_with_observed_my_confounder_uses_adjustment():
    """Observed M-Y confounder requires adjustment; the numeric path
    must thread the identification's adjustment set into the Imai fit."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "u", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("u"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("y")},
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
    n = 1000
    u = rng.standard_normal(n)
    x = rng.binomial(1, 0.5, n)
    m = 2.0 * x + 1.0 * u + rng.standard_normal(n)
    y = 1.0 * m + 0.5 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"u": u, "x": x, "m": m, "y": y})

    out = themis.estimate(ast, df, random_state=42)
    result = out["results"][0]
    decomp = result["extensions"]["mediation_decomposition"]
    assert decomp["strategy"] == "nde_nie"
    assert decomp["nde_nie"]["adjustment"] == ["u(me)"]

    est = result["numeric_estimate"]
    assert "u" in est["adjustment"]
    nie = est["decomposition"]["nie"]
    # NIE = 2 (x→m) * 1 (m→y) = 2.0
    assert abs(nie["point"] - 2.0) < 0.4


def test_mediation_estimate_verify_round_trips():
    df = _clean_med_data(n=500, seed=0)
    ast = _clean_mediation_ast()
    out = themis.estimate(ast, df, random_state=42)
    # Status stays structurally_solved → routes to verify_effect_structural,
    # which audits the identify_via_mediation derivation. Must pass.
    themis.verify(ast, out["results"][0])
