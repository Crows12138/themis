"""Strong re-derivation of the Balke-Pearl NUMERIC bounds.

Before this, ``verify_bounds_result`` only METADATA-audited the numeric
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
from themis import verify_bounds_result
from themis.verifier.errors import VerificationError
from themis.verifier.bounds_rules import _verifier_bp_bounds_from_P
from themis.estimation.bounds_numeric import _bp_ace_bounds_from_P


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


def test_records_p_table(bp_result):
    _, res = bp_result
    stats = res["bounds_result"]["sufficient_statistics"]
    P = np.asarray(stats["P_xyz"])
    assert P.shape == (2, 2, 2)


def test_genuine_bounds_round_trip(bp_result):
    prog, res = bp_result
    verify_bounds_result(prog, res)  # no raise


# --- the flagship: self-consistent wrong bound is now caught -----------------


def test_rejects_tampered_lower_value(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    # forge a falsely-tight lower, keeping metadata (width, CI, range) valid
    b["lower_value"] = 0.30
    b["width"] = b["upper_value"] - 0.30
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, r)


def test_rejects_tampered_upper_value(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    b["upper_value"] = min(1.0, b["upper_value"] - 0.2)
    b["width"] = b["upper_value"] - b["lower_value"]
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, r)


def test_rejects_tampered_p_table_inconsistent_with_bounds(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    # perturb the recorded table so LP(P') no longer yields the reported bound
    P = np.asarray(b["sufficient_statistics"]["P_xyz"])
    P[0, 0, 0] += 0.1
    P[0, 1, 1] -= 0.1  # keep the Z=0 slice summing to 1
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, r)


def test_rejects_invalid_p_table_bad_normalisation(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    P = np.asarray(b["sufficient_statistics"]["P_xyz"])
    P[0, 0, 0] += 0.3  # Z=0 slice no longer sums to 1
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, r)


def test_rejects_p_table_violating_instrumental_inequality(bp_result):
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    # A table that sums to 1 per slice but violates IV inequality
    # P(Y=0,X=0|Z=0)+P(Y=1,X=0|Z=1) > 1.
    P = np.zeros((2, 2, 2))
    P[0, 0, 0] = 1.0            # Z=0: all mass on (X=0,Y=0)
    P[1, 0, 1] = 1.0            # Z=1: all mass on (X=0,Y=1)
    b["sufficient_statistics"]["P_xyz"] = P.tolist()
    with pytest.raises(VerificationError):
        verify_bounds_result(prog, r)


# --- honest ceiling ----------------------------------------------------------


def test_self_consistent_table_and_bounds_forgery_not_caught(bp_result):
    """Replacing the recorded table with a DIFFERENT valid one AND setting the
    bounds to what the LP yields on it passes — the verifier has no DataFrame
    to re-count the true table from. The honest ceiling for a data-refit
    quantity; a lone tampered bound (above) is still caught."""
    prog, res = bp_result
    r = copy.deepcopy(res)
    b = r["bounds_result"]
    q = np.zeros(16)
    q[1 * 4 + 1] = 0.5   # compliers, Y≡X
    q[0 * 4 + 3] = 0.5   # never-takers, Y≡1
    P2 = _P_from_types(q)
    lo, hi = _bp_ace_bounds_from_P(P2)
    b["sufficient_statistics"]["P_xyz"] = P2.tolist()
    b["lower_value"] = float(lo)
    b["upper_value"] = float(hi)
    b["width"] = float(hi - lo)
    b["ci_lower"] = float(lo) - 0.05
    b["ci_upper"] = float(hi) + 0.05
    verify_bounds_result(prog, r)  # passes — documented limitation


# --- grid oracle: verifier LP == producer LP (independence pin) ---------------


def test_verifier_lp_matches_producer_on_random_tables():
    rng = np.random.default_rng(20260711)
    for _ in range(200):
        q = rng.dirichlet(np.ones(16))
        P = _P_from_types(q)
        prod_lo, prod_hi = _bp_ace_bounds_from_P(P)
        ver_lo, ver_hi = _verifier_bp_bounds_from_P(P, "bounds_balke_pearl_iv")
        assert ver_lo == pytest.approx(prod_lo, abs=1e-6)
        assert ver_hi == pytest.approx(prod_hi, abs=1e-6)


# --- no-op when nothing recorded ---------------------------------------------


def test_symbolic_only_is_noop():
    from themis.verifier.bounds_rules import _rederive_balke_pearl_numeric
    _rederive_balke_pearl_numeric({"method": "balke_pearl_iv"})  # no P_xyz → skip
