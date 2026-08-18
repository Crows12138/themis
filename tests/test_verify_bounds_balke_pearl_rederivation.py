"""Strong re-derivation of the Balke-Pearl NUMERIC bounds.

Before this, ``verify_bounds_results`` only METADATA-audited the numeric
Balke-Pearl interval (direction, admissible range, width, CI containment) —
it never re-derived the value, so a self-consistent WRONG bound (an in-range,
width-consistent, CI-enclosed but falsely-tight interval) passed. The
producer now records the empirical P(X=x, Y=y | Z=z) table under
``sufficient_statistics.P_xyz``, and the verifier re-runs an independently-
transcribed response-function LP over it, rejecting a bound that isn't what
the LP yields.

The grid oracle pins the independence: the verifier's LP transcription is
compared against the producer's on random feasible tables — same answer,
separate code.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import verify_bounds_results
from themis.verifier.errors import VerificationError
from themis.verifier.bounds_rules import (
    _v_response_types,
    _verifier_response_lp,
)
from themis.response_polytope import (
    _arm_objective,
    _contrast_objective,
    _solve_response_lp,
)


def _producer_arm(P):
    """The producer's LP on the arm the fixture query asks about:
    P(y=true | do(x=true)) — level index 1 on both axes."""
    return _solve_response_lp(P, 2, 2, 2, _arm_objective(2, 2, 2, 1, 1))


def _verifier_arm(P):
    """The same objective, built from the verifier's own enumeration."""
    fxs, gys = _v_response_types(2, 2, 2)
    obj = [1.0 if g[1] == 1 else 0.0 for _f in fxs for g in gys]
    return _verifier_response_lp(P, 2, 2, 2, obj, 'bounds_balke_pearl_iv')


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _query():
    return {"kind": "query", "id": "q", "query": {
        "kind": "effect", "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True}, "given": []}}


def _iv_program():
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [
                {"kind": "variable", "predicate": "y", "domain": [True, False]},
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "z", "domain": [True, False]},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y"), "annotations": {"source": "llm_proposal"}},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x"), "annotations": {"source": "llm_proposal"}},
                {"kind": "bidirected", "left": _atom("x"), "right": _atom("y"), "annotations": {"source": "llm_proposal"}},
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
    return pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool), "z": Z.astype(bool)})


def _P_from_types(q: np.ndarray) -> np.ndarray:
    """Exact P(X=x,Y=y|Z=z) implied by a 16-type distribution (Z ~ uniform,
    independent of type). Guaranteed feasible for the response-function LP."""
    P = np.zeros((2, 2, 2))
    for z in (0, 1):
        for i in range(4):
            for j in range(4):
                x = _fx(i, z)
                y = _gy(j, x)
                P[z, x, y] += q[i * 4 + j]
    return P


@pytest.fixture(scope="module")
def bp_result():
    prog = _iv_program()
    env = themis.estimate(prog, _iv_data(), ci_bootstrap=0)
    return prog, env["results"][0]


# --- genuine round-trip ------------------------------------------------------


from tests.bounds_rows import methods, row

def test_records_p_table(bp_result):
    _, res = bp_result
    stats = row(res, "balke_pearl_iv")["sufficient_statistics"]
    P = np.asarray(stats["P_xyz"])
    assert P.shape == (2, 2, 2)


def test_genuine_bounds_round_trip(bp_result):
    prog, res = bp_result
    verify_bounds_results(prog, res)  # no raise


# --- the flagship: self-consistent wrong bound is now caught -----------------


def test_rejects_tampered_lower_value(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = row(r, "balke_pearl_iv")
    # forge a falsely-tight lower, keeping metadata (width, CI, range) valid
    b["lower_value"] = 0.30
    b["width"] = b["upper_value"] - 0.30
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, r)


def test_rejects_tampered_upper_value(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = row(r, "balke_pearl_iv")
    b["upper_value"] = min(1.0, b["upper_value"] - 0.2)
    b["width"] = b["upper_value"] - b["lower_value"]
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, r)


def test_rejects_tampered_p_table_inconsistent_with_bounds(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = row(r, "balke_pearl_iv")
    # perturb the recorded table so LP(P') no longer yields the reported bound
    P = np.asarray(b["sufficient_statistics"]["P_xyz"])
    P[0, 0, 0] += 0.1
    P[0, 1, 1] -= 0.1  # keep the Z=0 slice summing to 1
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, r)


def test_rejects_invalid_p_table_bad_normalisation(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = row(r, "balke_pearl_iv")
    P = np.asarray(b["sufficient_statistics"]["P_xyz"])
    P[0, 0, 0] += 0.3  # Z=0 slice no longer sums to 1
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, r)


def test_rejects_p_table_violating_instrumental_inequality(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = row(r, "balke_pearl_iv")
    # A table that sums to 1 per slice but violates IV inequality
    # P(Y=0,X=0|Z=0)+P(Y=1,X=0|Z=1) > 1.
    P = np.zeros((2, 2, 2))
    P[0, 0, 0] = 1.0            # Z=0: all mass on (X=0,Y=0)
    P[1, 0, 1] = 1.0            # Z=1: all mass on (X=0,Y=1)
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_results(prog, r)


# --- honest ceiling ----------------------------------------------------------


def _forged_table():
    q = np.zeros(16)
    q[1 * 4 + 1] = 0.5   # compliers, Y≡X
    q[0 * 4 + 3] = 0.5   # never-takers, Y≡1
    return _P_from_types(q)


def _forge(b, P2, *, contrast: bool):
    lo, hi = _producer_arm(P2)
    b["sufficient_statistics"]["P_xyz"] = P2.tolist()
    b["lower_value"] = float(lo)
    b["upper_value"] = float(hi)
    b["width"] = float(hi - lo)
    b["ci_lower"] = float(lo) - 0.05
    b["ci_upper"] = float(hi) + 0.05
    if contrast and b.get("contrast"):
        c_lo, c_hi = _solve_response_lp(
            P2, 2, 2, 2, _contrast_objective(2, 2, 2, 1, 1, 0))
        b["contrast"]["lower_value"] = float(c_lo)
        b["contrast"]["upper_value"] = float(c_hi)


def test_a_forgery_that_stops_at_the_arm_is_caught(bp_result):
    """The second reported quantity is a second thing to keep consistent.

    A forger who swaps the table and re-solves the arm still leaves the ACE
    interval standing on the old one. Nothing was designed for this — it is
    what reporting two quantities from one polytope costs an attacker.
    """
    prog, res = bp_result
    r = copy.deepcopy(res)
    assert row(r, "balke_pearl_iv").get("contrast") is not None
    _forge(row(r, "balke_pearl_iv"), _forged_table(), contrast=False)
    with pytest.raises(VerificationError, match="contrast"):
        verify_bounds_results(prog, r)


def test_self_consistent_table_and_bounds_forgery_not_caught(bp_result):
    """Replacing the recorded table with a DIFFERENT valid one AND setting
    every reported interval to what the LP yields on it passes — the verifier
    has no DataFrame to re-count the true table from. The honest ceiling for
    a data-refit quantity; a lone tampered bound (above) is still caught."""
    prog, res = bp_result
    r = copy.deepcopy(res)
    _forge(row(r, "balke_pearl_iv"), _forged_table(), contrast=True)
    verify_bounds_results(prog, r)  # passes — documented limitation


# --- grid oracle: verifier LP == producer LP (independence pin) ---------------


def test_verifier_lp_matches_producer_on_random_tables():
    rng = np.random.default_rng(20260711)
    for _ in range(200):
        q = rng.dirichlet(np.ones(16))
        P = _P_from_types(q)
        prod_lo, prod_hi = _producer_arm(P)
        ver_lo, ver_hi = _verifier_arm(P)
        assert ver_lo == pytest.approx(prod_lo, abs=1e-6)
        assert ver_hi == pytest.approx(prod_hi, abs=1e-6)


# --- no-op when nothing recorded ---------------------------------------------


def test_symbolic_only_is_noop():
    from themis.verifier.bounds_rules import _rederive_balke_pearl_numeric
    _rederive_balke_pearl_numeric({"method": "balke_pearl_iv"})  # no P_xyz → skip
