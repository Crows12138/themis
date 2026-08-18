"""Dispatch + verifier integration for the bounds numeric end.

themis.estimate turns the kernel's symbolic bounds_result into actual
numbers (same method the kernel chose), and themis.verify_bounds_results
audits them. Tamper cases confirm the audit has teeth.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import verify_bounds_results
from themis.input.syntactic_validator import SyntacticError, validate_result
from themis.verifier.errors import VerificationError


from tests.bounds_rows import methods, row

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


def _multivalued_query(intervention_val=2):
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": intervention_val},
        "target": {"atom": _atom("y"), "value": True}, "given": []}}


def _multivalued_bow_program(intervention_val=2):
    # x is a 3-level discrete treatment {0,1,2} with a bow-arc confounder;
    # point ID fails, so the assumption-free Manski natural floor fires on
    # the single arm do(x=intervention_val).
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [0, 1, 2]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            _multivalued_query(intervention_val)]}


def _multivalued_confounded_data(n=20000, seed=0):
    rng = np.random.default_rng(seed)
    U = rng.integers(0, 2, n)
    base = rng.integers(0, 3, n)
    X = np.where(U == 1, np.minimum(base + 1, 2), base)  # confounded dose
    Y = (rng.random(n) < np.clip(0.1 + 0.25 * X + 0.3 * U, 0, 1)).astype(int)
    return pd.DataFrame({"x": X.astype(int), "y": Y.astype(bool)})


# =============================================================== fill-in
def test_iv_graph_fills_balke_pearl_numeric():
    """The query asks for P(y=true | do(x=true)); the interval is about it.

    This test used to assert estimand == "ace" and then check the endpoints
    against 0.60 / 1.00 — the ACE interval of the worked example, under a
    query that named one arm. Both numbers moved to `contrast`, where they
    still are.
    """
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=50)
    b = row(env["results"][0], "balke_pearl_iv")
    assert b["estimand"] == "arm_probability"
    assert b["instrument"] == "z"
    assert 0.0 <= b["lower_value"] <= b["upper_value"] <= 1.0
    assert b["contrast"]["kind"] == "ace"
    assert b["contrast"]["lower_value"] == pytest.approx(0.60, abs=0.04)
    assert b["contrast"]["upper_value"] == pytest.approx(1.00, abs=0.04)
    assert b["ci_lower"] <= b["lower_value"] + 1e-6
    assert len(b["numeric_data_hash"]) == 64


def test_bow_arc_fills_manski_numeric():
    env = themis.estimate(_bow_program(), _confounded_data(), ci_bootstrap=50)
    b = row(env["results"][0], "manski_natural")
    assert b["estimand"] == "arm_probability"
    assert b.get("instrument") is None
    assert 0.0 <= b["lower_value"] <= b["upper_value"] <= 1.0


def test_multivalued_treatment_fills_manski_numeric():
    # Candidate C: a MULTI-VALUED treatment do(x=2) gets the assumption-free
    # Manski natural arm floor — before, the bool-treatment gate blocked it.
    prog = _multivalued_bow_program(2)
    df = _multivalued_confounded_data()
    env = themis.estimate(prog, df, ci_bootstrap=50)
    b = row(env["results"][0], "manski_natural")
    assert b["estimand"] == "arm_probability"
    # off-arm mass pooled over all levels != 2, matching P(x != 2) exactly.
    n = len(df)
    n_joint = int(((df.x == 2) & df.y).sum())
    n_other = int((df.x != 2).sum())
    assert b["lower_value"] == pytest.approx(n_joint / n, abs=1e-9)
    assert b["upper_value"] == pytest.approx((n_joint + n_other) / n, abs=1e-9)
    assert b["sufficient_statistics"] == {
        "n": n, "n_joint_target_arm": n_joint, "n_other_arm": n_other}
    assert "P(x≠2)" in b["upper_expression"]


def test_multivalued_bounds_verify_round_trip():
    prog = _multivalued_bow_program(2)
    env = themis.estimate(prog, _multivalued_confounded_data(), ci_bootstrap=0)
    verify_bounds_results(prog, env["results"][0])  # accepts honest


def test_multivalued_verify_rejects_fabricated_off_arm_count():
    # The strong count re-derivation catches a fabricated pooled off-arm
    # mass that a metadata-only audit (direction / range / width) would pass.
    prog = _multivalued_bow_program(2)
    env = themis.estimate(prog, _multivalued_confounded_data(), ci_bootstrap=0)
    res = copy.deepcopy(env["results"][0])
    ss = row(res, "manski_natural")["sufficient_statistics"]
    ss["n_other_arm"] = ss["n_other_arm"] - 500  # shrink pooled off-arm mass
    with pytest.raises(VerificationError, match="does not match"):
        verify_bounds_results(prog, res)


def test_multivalued_symbolic_only_verify_when_no_data():
    prog = _multivalued_bow_program(2)
    res = themis.run(prog)["results"][0]
    assert methods(res) == ["manski_natural"]
    assert row(res, "manski_natural").get("lower_value") is None
    verify_bounds_results(prog, res)  # symbolic-only still accepts


def test_mtr_program_fills_manski_tamer_numeric():
    ext = {"monotonicity": {"target": "y", "treatment": "x",
                            "direction": "non_decreasing"}}
    env = themis.estimate(_bow_program(ext), _confounded_data(), ci_bootstrap=50)
    b = row(env["results"][0], "manski_tamer_monotonicity")
    assert b["estimand"] == "arm_probability"
    assert b["lower_value"] is not None
    # The floor is evaluated too — every row is a method of its own, and
    # one row's number cannot stand for another's.
    assert row(env["results"][0], "manski_natural")["lower_value"] is not None


# =============================================================== schema + verify
def test_numeric_bounds_pass_schema():
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=0)
    validate_result(env["results"][0])  # raises on schema violation


def test_verify_bounds_round_trip():
    prog = _iv_program()
    env = themis.estimate(prog, _iv_data(), ci_bootstrap=0)
    verify_bounds_results(prog, env["results"][0])  # accepts honest bounds


def test_symbolic_only_bounds_verify_when_no_data():
    # themis.run (no data) → symbolic-only bounds; numeric audit is skipped.
    prog = _iv_program()
    res = themis.run(prog)["results"][0]
    assert row(res, "balke_pearl_iv").get("lower_value") is None
    verify_bounds_results(prog, res)  # must still accept


def test_point_identified_query_keeps_point_estimate():
    # A point-identifiable effect (empty backdoor set): the numeric_estimate
    # POINT is the primary answer. The kernel also attaches an assumption-free
    # Manski floor even when identified; the numeric end may fill that too, but
    # it is an arm-probability floor and does NOT replace the point.
    env = themis.estimate(_identified_program(), _confounded_data(), ci_bootstrap=0)
    res = env["results"][0]
    assert res.get("numeric_estimate") is not None
    for b in res.get("bounds_results") or ():
        if b.get("lower_value") is not None:
            assert b["estimand"] == "arm_probability"


def test_iv_point_estimate_and_bounds_coexist():
    # IV graph: an IV point estimate AND assumption-free Balke-Pearl bounds.
    env = themis.estimate(_iv_program(), _iv_data(), ci_bootstrap=0)
    res = env["results"][0]
    assert row(res, "balke_pearl_iv")["lower_value"] is not None
    # dispatch also produced an IV point estimate on this shape
    ne = res.get("numeric_estimate")
    assert ne is not None and "iv" in ne["method"]


# =============================================================== tamper
def _tampered(mutate):
    prog = _iv_program()
    env = themis.estimate(prog, _iv_data(), ci_bootstrap=30)
    res = copy.deepcopy(env["results"][0])
    mutate(row(res, "balke_pearl_iv"))
    return prog, res


@pytest.mark.parametrize("mutate,label", [
    (lambda d: d.__setitem__("upper_value", d["lower_value"] - 0.1), "inverted"),
    (lambda d: d.__setitem__("upper_value", 5.0), "out_of_range"),
    (lambda d: d.__setitem__("ci_lower", d["upper_value"] + 0.5), "ci_not_enclosing"),
    (lambda d: d.__setitem__("instrument", None), "missing_instrument"),
    (lambda d: d.__setitem__("numeric_data_hash", "abc"), "bad_hash"),
])
def test_verify_rejects_tampered_numeric_bounds(mutate, label):
    prog, res = _tampered(mutate)
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, res)


def test_an_estimand_this_method_does_not_bound_dies_at_the_schema():
    """The row that left this table, and where it went.

    Re-labelling the interval "ace" used to be an audit failure. The
    estimand enum now has one member, so the exit refuses it before the
    audit is reached — earlier and on every envelope, not only the ones
    somebody thought to audit. The audit's own check stays for the direct
    caller, which does not go through the exit.
    """
    prog, res = _tampered(lambda d: d.__setitem__("estimand", "ace"))
    with pytest.raises(SyntacticError, match="bounds_results"):
        verify_bounds_results(prog, res)
