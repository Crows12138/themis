"""Dispatch + verifier integration for the bounds numeric end.

themis.estimate turns the kernel's symbolic bounds_result into actual
numbers (same method the kernel chose), and themis.verify_bounds_result
audits them. Tamper cases confirm the audit has teeth.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import verify_bounds_result
from themis.input.syntactic_validator import validate_result
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _query():
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True}, "given": []}}


def _iv_program():
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            _query()]}


def _bow_program(extensions=None):
    prog = {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            _query()]}
    if extensions:
        prog["extensions"] = extensions
    return prog


def _identified_program():
    # X→Y, no bidirected → empty backdoor set identifies the effect.
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            _query()]}


def _fx(i, z):
    return (0, z, 1 - z, 1)[i]


def _gy(j, x):
    return (0, x, 1 - x, 1)[j]


def _iv_data(n=12000, seed=7):
    q = np.zeros(16)
    q[1 * 4 + 1] = 0.60
    q[3 * 4 + 3] = 0.20
    q[0 * 4 + 0] = 0.20
    rng = np.random.default_rng(seed)
    types = rng.choice(16, size=n, p=q)
    Z = rng.integers(0, 2, n)
    X = np.array([_fx(t // 4, z) for t, z in zip(types, Z)])
    Y = np.array([_gy(t % 4, x) for t, x in zip(types, X)])
    return pd.DataFrame(
        {"x": X.astype(bool), "y": Y.astype(bool), "z": Z.astype(bool)})


def _confounded_data(n=20000, seed=0):
    rng = np.random.default_rng(seed)
    U = rng.integers(0, 2, n)
    X = (rng.random(n) < np.where(U == 1, 0.8, 0.2)).astype(int)
    Y = (rng.random(n) < (0.2 + 0.3 * X + 0.3 * U)).astype(int)
    return pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool)})


# =============================================================== fill-in
def test_iv_graph_fills_balke_pearl_numeric():
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=50)
    b = env["results"][0]["bounds_result"]
    assert b["method"] == "balke_pearl_iv"
    assert b["estimand"] == "ace"
    assert b["instrument"] == "z"
    assert b["lower_value"] == pytest.approx(0.60, abs=0.04)
    assert b["upper_value"] == pytest.approx(1.00, abs=0.04)
    assert b["ci_lower"] <= b["lower_value"] + 1e-6
    assert len(b["numeric_data_hash"]) == 64


def test_bow_arc_fills_manski_numeric():
    env = themis.estimate(_bow_program(), _confounded_data(), ci_bootstrap=50)
    b = env["results"][0]["bounds_result"]
    assert b["method"] == "manski_natural"
    assert b["estimand"] == "arm_probability"
    assert b.get("instrument") is None
    assert 0.0 <= b["lower_value"] <= b["upper_value"] <= 1.0


def test_mtr_program_fills_manski_tamer_numeric():
    ext = {"monotonicity": {"target": "y", "treatment": "x",
                            "direction": "non_decreasing"}}
    env = themis.estimate(_bow_program(ext), _confounded_data(), ci_bootstrap=50)
    b = env["results"][0]["bounds_result"]
    assert b["method"] == "manski_tamer_monotonicity"
    assert b["estimand"] == "arm_probability"
    assert b["lower_value"] is not None


# =============================================================== schema + verify
def test_numeric_bounds_pass_schema():
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=0)
    validate_result(env["results"][0])  # raises on schema violation


def test_verify_bounds_round_trip():
    prog = _iv_program()
    env = themis.estimate(prog, _iv_data(), ci_bootstrap=0)
    verify_bounds_result(prog, env["results"][0])  # accepts honest bounds


def test_symbolic_only_bounds_verify_when_no_data():
    # themis.run (no data) → symbolic-only bounds; numeric audit is skipped.
    prog = _iv_program()
    res = themis.run(prog)["results"][0]
    assert res["bounds_result"].get("lower_value") is None
    verify_bounds_result(prog, res)  # must still accept


def test_point_identified_query_keeps_point_estimate():
    # A point-identifiable effect (empty backdoor set): the numeric_estimate
    # POINT is the primary answer. The kernel also attaches an assumption-free
    # Manski floor even when identified; the numeric end may fill that too, but
    # it is an arm-probability floor and does NOT replace the point.
    env = themis.estimate(_identified_program(), _confounded_data(), ci_bootstrap=0)
    res = env["results"][0]
    assert res.get("numeric_estimate") is not None
    b = res.get("bounds_result")
    if b is not None and b.get("lower_value") is not None:
        assert b["estimand"] == "arm_probability"


def test_iv_point_estimate_and_bounds_coexist():
    # IV graph: an IV point estimate AND assumption-free Balke-Pearl bounds.
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=0)
    res = env["results"][0]
    assert res["bounds_result"]["lower_value"] is not None
    # dispatch also produced an IV point estimate on this shape
    ne = res.get("numeric_estimate")
    assert ne is not None and "iv" in ne["method"]


# =============================================================== tamper
def _tampered(mutate):
    prog = _iv_program()
    env = themis.estimate(prog, _iv_data(), ci_bootstrap=30)
    res = copy.deepcopy(env["results"][0])
    mutate(res["bounds_result"])
    return prog, res


@pytest.mark.parametrize("mutate,label", [
    (lambda d: d.__setitem__("upper_value", d["lower_value"] - 0.1), "inverted"),
    (lambda d: d.__setitem__("estimand", "arm_probability"), "estimand_mismatch"),
    (lambda d: d.__setitem__("upper_value", 5.0), "out_of_range"),
    (lambda d: d.__setitem__("ci_lower", d["upper_value"] + 0.5), "ci_not_enclosing"),
    (lambda d: d.__setitem__("instrument", None), "missing_instrument"),
    (lambda d: d.__setitem__("numeric_data_hash", "abc"), "bad_hash"),
])
def test_verify_rejects_tampered_numeric_bounds(mutate, label):
    prog, res = _tampered(mutate)
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, res)
