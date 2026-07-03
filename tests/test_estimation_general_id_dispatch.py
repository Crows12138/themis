"""General-ID (c-factor plug-in) dispatch + verifier integration.

End-to-end: an effect query on Pearl's napkin (identified ONLY via the
general ID algorithm) routes through themis.estimate to a general-ID
plug-in numeric estimate, PREEMPTING the IV escalation (a c-factor
estimand is assumption-free; an IV point needs monotonicity/homogeneity).
themis.verify must round-trip via the general_id_criterion +
numeric_general_id_estimate derivation, and a genuine hedge with an
instrument must still fall through to IV.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _napkin_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("w"), "to": _atom("z")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("x")},
            {"kind": "bidirected", "left": _atom("w"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _sigmoid(t):
    return 1.0 / (1.0 + np.exp(-t))


def _napkin_data(n, seed=0):
    rng = np.random.default_rng(seed)
    u_wx = rng.random(n) < 0.5
    u_wy = rng.random(n) < 0.5
    W = rng.random(n) < _sigmoid(2.5 * u_wy + 1.0 * u_wx - 1.75)
    Z = rng.random(n) < _sigmoid(3.0 * W - 1.5)
    X = rng.random(n) < _sigmoid(3.0 * Z + 0.5 * u_wx - 1.75)
    Y = rng.random(n) < _sigmoid(1.2 * X + 2.5 * u_wy - 1.85)
    return pd.DataFrame({"w": W, "z": Z, "x": X, "y": Y})


_TRUE_ATE = sum(
    0.5 * (_sigmoid(1.2 + 2.5 * u - 1.85) - _sigmoid(2.5 * u - 1.85))
    for u in (0.0, 1.0)
)


# ============================================ dispatch


def test_napkin_effect_gets_general_id_plugin():
    out = themis.estimate(_napkin_ast(), _napkin_data(4000, 0), ci_bootstrap=0)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    est = r["numeric_estimate"]
    assert est["method"] == "general_id_plugin"
    assert est["treatment"] == "x" and est["outcome"] == "y"
    assert abs(est["point"] - _TRUE_ATE) < 0.05


def test_general_id_preempts_iv():
    """Before this frontier the dispatch answered the napkin with a
    conditional-IV 2SLS estimate (assumption-laden). The assumption-free
    c-factor plug-in must now win — the method is NOT an IV method and the
    derivation is the general-ID pair, not iv_criterion_check."""
    out = themis.estimate(_napkin_ast(), _napkin_data(4000, 1), ci_bootstrap=0)
    r = out["results"][0]
    est = r["numeric_estimate"]
    assert est["method"] not in ("iv_wald", "iv_2sls")
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert rules == ["general_id_criterion", "numeric_general_id_estimate"]
    assert "iv_criterion_check" not in rules


def test_general_id_verify_round_trips():
    ast = _napkin_ast()
    out = themis.estimate(ast, _napkin_data(4000, 2), ci_bootstrap=0)
    themis.verify(ast, out["results"][0])


def test_general_id_output_validates_against_schema():
    out = themis.estimate(_napkin_ast(), _napkin_data(3000, 3), ci_bootstrap=40,
                          random_state=7)
    for r in out["results"]:
        validate_result(r)


def test_genuine_hedge_with_instrument_still_uses_iv():
    """Z → X → Y with X ↔ Y latent: do(X) is a hedge (NOT c-factor
    identified), but Z is a valid instrument. General-ID must decline and
    the dispatch must fall through to the IV escalation unchanged."""
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
    n = 4000
    u = rng.standard_normal(n)
    Z = rng.random(n) < 0.5
    X = rng.random(n) < _sigmoid(2.0 * Z.astype(float) + 1.5 * u - 1.0)
    Y = rng.random(n) < _sigmoid(1.0 * X.astype(float) + 1.5 * u - 0.75)
    df = pd.DataFrame({"z": Z, "x": X, "y": Y})
    out = themis.estimate(ast, df, ci_bootstrap=0)
    est = out["results"][0].get("numeric_estimate")
    assert est is not None
    assert est["method"] in ("iv_wald", "iv_2sls")


# ============================================ verifier tamper rejection


def _solved_napkin_result():
    ast = _napkin_ast()
    out = themis.estimate(ast, _napkin_data(4000, 4), ci_bootstrap=60,
                          random_state=11)
    return ast, out["results"][0]


def test_verify_rejects_wrong_numeric_method():
    ast, r = _solved_napkin_result()
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "numeric_general_id_estimate":
            s["inputs"]["method"] = "iv_wald"
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_verify_rejects_point_outside_ci():
    ast, r = _solved_napkin_result()
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "numeric_general_id_estimate":
            s["inputs"]["point"] = s["inputs"]["ci_upper"] + 5.0
    # keep the surfaced numeric_estimate in sync so the schema still passes
    bad["numeric_estimate"]["point"] = bad["numeric_estimate"]["ci_upper"] + 5.0
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_verify_rejects_criterion_claiming_unidentifiable():
    """The general_id_criterion step re-runs the ID engine. If a tampered
    derivation claims the effect is NOT identifiable (output False) while
    the estimate stands, the independent re-run contradicts it."""
    ast, r = _solved_napkin_result()
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "general_id_criterion":
            s["output"] = False
    with pytest.raises(Exception):
        themis.verify(ast, bad)
