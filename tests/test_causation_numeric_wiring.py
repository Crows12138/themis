"""Pipeline wiring for the PN/PS/PNS (causation) NUMERIC end.

The CausationQuery structural end (run) already answers from theta. This slice
threads the DATA end through the estimation dispatch, schema, and independent
verifier so a client can hand the kernel a causation query + a DataFrame and get
back PN/PS/PNS recovered from data (empirical joint + g-formula do-risks →
Tian-Pearl), which a second, independent pass re-derives.

The verifier mirror ``numeric_causation_estimate`` re-applies the Tian-Pearl
theorem (its OWN transcription) to the reported joint + do-risks and re-derives
the back-door adjustment set on ctx.graph — so a tampered point, do-risk, or
adjustment set is rejected, and a good result verified against a graph that
breaks the identification is rejected too.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result
from themis.verifier import VerificationError


# ------------------------------------------------------------------ builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _causation_query(monotonic=True, **kw):
    q = {"kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
         "monotonic": monotonic}
    q.update(kw)
    return q


def _ast(edges, *, monotonic=True, variables=("x", "y", "z"), theta=(), **qkw):
    # Confounded structure by default: Z→X, Z→Y, X→Y (back-door set {Z}).
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *(_var(v) for v in variables),
            *edges, *theta,
            {"kind": "query", "id": "q",
             "query": _causation_query(monotonic=monotonic, **qkw)},
        ],
    }


_CONFOUNDED = (_cause("z", "x"), _cause("z", "y"), _cause("x", "y"))


def _sample(n: int, seed: int) -> pd.DataFrame:
    """Rank-preserving monotone SCM with an observed confounder Z; true
    PN≈0.446, PS≈0.521, PNS=0.35 (see tests/test_estimation_causation.py)."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.5, 0.2)
    b = np.where(z, 0.8, 0.6)
    y0, y1 = u < a, u < b
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.where(x, y1, y0)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _result(r):
    return r["results"][0]


# ------------------------------------------------------------------ schema
def test_schema_accepts_causation_numeric_result():
    df = _sample(30_000, seed=1)
    res = _result(themis.estimate(_ast(_CONFOUNDED), df))
    validate_result(res)  # round-trips the numeric_estimate + poc block


# ------------------------------------------------------------------ estimate
def test_estimate_recovers_points_and_provenance():
    df = _sample(200_000, seed=2)
    res = _result(themis.estimate(_ast(_CONFOUNDED), df))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert ne["method"] == "causation_plugin"
    assert ne["treatment"] == "x" and ne["outcome"] == "y"
    assert abs(ne["point"] - 0.446) < 0.02                     # PN headline
    poc = ne["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "backdoor_adjustment"
    assert poc["adjustment"] == ["z"]
    assert abs(poc["ps"]["point"] - 0.521) < 0.02
    assert abs(poc["pns"]["point"] - 0.35) < 0.02
    # bounds present on every quantity
    for q in ("pn", "ps", "pns"):
        assert poc[q]["lower"] <= poc[q]["point"] <= poc[q]["upper"]


def test_estimate_without_monotonicity_attaches_no_point():
    # No monotonicity → PN/PS/PNS are only bounds; the point overlay refuses,
    # so no numeric_estimate is attached (structural answer stays primary).
    df = _sample(30_000, seed=3)
    res = _result(themis.estimate(_ast(_CONFOUNDED, monotonic=False), df))
    assert "numeric_estimate" not in res


def test_estimate_exogenous_provenance():
    # X→Y only, X exogenous: do-risk = P(Y|X), adjustment empty.
    rng = np.random.default_rng(5)
    n = 120_000
    x = rng.random(n) < 0.5
    u = rng.random(n)
    y = np.where(x, u < 0.7, u < 0.3)
    df = pd.DataFrame({"x": x, "y": y})
    res = _result(themis.estimate(
        _ast((_cause("x", "y"),), variables=("x", "y")), df))
    assert res["status"] == "numerically_solved"
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["interventional_risk_provenance"] == "exogenous"
    assert poc["adjustment"] == []


# ------------------------------------------------------------------ verify
def test_verify_accepts_numeric():
    prog = _ast(_CONFOUNDED)
    df = _sample(80_000, seed=6)
    themis.verify(prog, _result(themis.estimate(prog, df)))


def test_verify_rejects_tampered_data_hash():
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=7)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["data_hash"] = "deadbeef"
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_point():
    # Flip the reported PN point: the rule re-derives Tian-Pearl from the
    # reported joint + do-risks and the claim no longer matches.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=8)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["pn_point"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_do_risk():
    # Tamper a do-risk: the re-applied Tian-Pearl points change, so the
    # reported points no longer match — caught even though the point fields
    # themselves were left untouched.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=9)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["p_y_do_x1"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_extensions_display_copy():
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=10)))
    tam = copy.deepcopy(res)
    tam["extensions"]["causation"]["pn"]["point"] = 0.99
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_wrong_adjustment_set():
    # Claim the empty adjustment set on a genuinely confounded graph: the rule
    # re-derives the admissible sets ({z}) and rejects the empty claim.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=11)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["adjustment"] = ""      # claim exogenous / empty set
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_reruns_adjustment_from_graph():
    # A good {z}-adjusted result, verified against a program whose graph makes
    # z irrelevant (no z→y): the empty set now suffices, so the claimed {z}
    # is not an admissible MINIMAL set — the rule re-derives from ctx.graph
    # and rejects. Proves the identification check has teeth.
    prog = _ast(_CONFOUNDED)
    res = _result(themis.estimate(prog, _sample(40_000, seed=12)))
    broken = _ast((_cause("z", "x"), _cause("x", "y")))  # z no longer confounds
    with pytest.raises(VerificationError):
        themis.verify(broken, res)
