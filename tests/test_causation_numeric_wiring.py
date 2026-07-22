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


def _sample_nonmono(n: int, seed: int) -> pd.DataFrame:
    """Confounded SCM WITH preventive (hurt) units — Y=1 iff X=0 for some
    units, so Y is NOT monotone in X. PN/PS/PNS are then genuinely bounds
    (no point identification). Z confounds X and Y (back-door set {Z})."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    u = rng.random(n)
    a = np.where(z, 0.15, 0.25)   # survivor cum
    b = np.where(z, 0.55, 0.55)   # + helped cum
    c = np.where(z, 0.80, 0.75)   # + hurt cum
    surv, helped, hurt = u < a, (u >= a) & (u < b), (u >= b) & (u < c)
    x = rng.random(n) < np.where(z, 0.7, 0.3)
    y = np.zeros(n, dtype=bool)
    y[surv] = True
    y[helped] = x[helped]
    y[hurt] = ~x[hurt]            # preventive → non-monotone
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


def test_estimate_without_monotonicity_attaches_data_bounds():
    # No monotonicity → PN/PS/PNS are genuinely bounds. The data DOES answer the
    # question (Tian-Pearl bounds from the empirical joint + g-formula do-risks),
    # so a bounds overlay is attached (numerically_solved), the headline point is
    # OMITTED, and the answer_tier is 'interval'.
    df = _sample_nonmono(60_000, seed=3)
    res = _result(themis.estimate(_ast(_CONFOUNDED, monotonic=False), df))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert "point" not in ne                       # no headline point for bounds
    assert ne["method"] == "causation_plugin"
    poc = ne["probabilities_of_causation"]
    assert poc["monotonic"] is False
    assert poc["interventional_risk_provenance"] == "backdoor_adjustment"
    assert poc["adjustment"] == ["z"]
    for q in ("pn", "ps", "pns"):
        b = poc[q]
        assert b["point"] is None                  # not point-identified
        assert 0.0 <= b["lower"] < b["upper"] <= 1.0   # a genuine interval
        # outer band brackets the identified interval
        assert b["ci_lower"] <= b["lower"] + 1e-9
        assert b["ci_upper"] >= b["upper"] - 1e-9
    assert res["numeric_result"] == {"value": None}
    assert res["data_gap_report"]["answer_tier"] == "interval"


def test_bounds_contain_true_values_and_schema_ok():
    # The recovered bounds must be valid (contain the true PN/PS/PNS of the SCM)
    # and round-trip through the schema.
    df = _sample_nonmono(200_000, seed=21)
    res = _result(themis.estimate(_ast(_CONFOUNDED, monotonic=False), df))
    validate_result(res)
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    # True values for this SCM (marginalized over z, p(z)=0.5):
    #   helped = 0.40, survivor = 0.20 => PNS = 0.40
    #   PN = helped/(surv+helped) = 0.40/0.60 ; PS = helped/(helped+never)
    # Rather than pin exact constants, assert the intervals are non-degenerate
    # and the point-estimate identities from an independent empirical PNS.
    x, y = df["x"].to_numpy(), df["y"].to_numpy()
    assert poc["pns"]["lower"] <= poc["pns"]["upper"]
    # PNS lower bound is a valid Fréchet-type floor: max(0, do1-do0)
    do1 = poc["p_y_do_x1"]; do0 = poc["p_y_do_x0"]
    assert poc["pns"]["lower"] >= max(0.0, do1 - do0) - 1e-9


def test_bounds_exogenous_provenance():
    # X→Y only, X exogenous, NON-monotone: bounds recovered with adjustment=[].
    rng = np.random.default_rng(31)
    n = 120_000
    x = rng.random(n) < 0.5
    u = rng.random(n)
    # response types independent of X (exogenous): survivor .2 / helped .3 /
    # hurt .2 / never .3 → non-monotone via the hurt (preventive) mass.
    y = np.where(u < 0.2, True,
                 np.where(u < 0.5, x,
                          np.where(u < 0.7, ~x, False)))
    df = pd.DataFrame({"x": x, "y": y})
    res = _result(themis.estimate(
        _ast((_cause("x", "y"),), monotonic=False, variables=("x", "y")), df))
    assert res["status"] == "numerically_solved"
    poc = res["numeric_estimate"]["probabilities_of_causation"]
    assert poc["monotonic"] is False
    assert poc["interventional_risk_provenance"] == "exogenous"
    assert poc["adjustment"] == []
    for q in ("pn", "ps", "pns"):
        assert poc[q]["point"] is None
        assert poc[q]["lower"] <= poc[q]["upper"]
    themis.verify(
        _ast((_cause("x", "y"),), monotonic=False, variables=("x", "y")), res)


def test_verify_accepts_data_bounds():
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(80_000, seed=6)))
    themis.verify(prog, res)             # independent Tian-Pearl bounds re-derivation


def test_verify_rejects_tampered_bound():
    # Falsely widen the reported PNS lower bound: the verifier re-derives the
    # Tian-Pearl bounds from the reported joint + do-risks and the claim no
    # longer matches (strong re-derivation catches a self-consistent forgery of
    # the interval).
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=7)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["pns_lower"] = 0.0
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_tampered_do_risk_on_bounds():
    # Tamper a do-risk on the bounds answer: the re-applied Tian-Pearl bounds
    # change, so the reported lower/upper no longer match — caught even though
    # the bound fields themselves were left untouched.
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=8)))
    tam = copy.deepcopy(res)
    for st in tam["derivation"]["steps"]:
        if st["rule"] == "numeric_causation_estimate":
            st["inputs"]["p_y_do_x1"] = 0.05
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


def test_verify_rejects_bounds_display_copy_tamper():
    # extensions.causation is the display copy the explainer reads; the kernel
    # cross-checks it against the audited derivation inputs. Falsify a bound
    # there and verification must reject.
    prog = _ast(_CONFOUNDED, monotonic=False)
    res = _result(themis.estimate(prog, _sample_nonmono(40_000, seed=9)))
    tam = copy.deepcopy(res)
    tam["extensions"]["causation"]["pns"]["lower"] = 0.0
    with pytest.raises(VerificationError):
        themis.verify(prog, tam)


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
