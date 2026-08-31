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
from themis import language
from tests import caveats


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

    # The share and its interval are the answer to "X 占多少比例", and
    # they are here, in the decomposition, with names. An estimator used
    # to prepend a Chinese sentence saying them again at the top of the
    # envelope so a renderer would not have to dig; that sentence is gone
    # (#395) — it restated these three fields, and it said them in a
    # language chosen before anyone knew who was reading.
    assert pm["ci_lower"] is not None and pm["ci_upper"] is not None
    assert est["decomposition"]["nie"]["point"] is not None
    assert est["decomposition"]["te"]["point"] is not None


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


def test_mediation_decomposition_carries_per_component_precision_budget():
    """Mediation numeric_estimate.decomposition has nde/nie/
    te/proportion_mediated each with their own ci_lower/ci_upper. Each
    component now carries a precision_budget sub-field."""
    df = _clean_med_data(n=2000, seed=0)
    out = themis.estimate(_clean_mediation_ast(), df, random_state=42)
    decomp = out["results"][0]["numeric_estimate"]["decomposition"]
    for comp_name in ("nde", "nie", "te", "proportion_mediated"):
        comp = decomp[comp_name]
        assert "precision_budget" in comp, (
            f"decomposition.{comp_name} missing precision_budget"
        )
        pb = comp["precision_budget"]
        assert "current_ci_half_width" in pb
        assert "n_to_halve_ci" in pb
        assert pb["n_to_halve_ci"] >= 1


# ==================================== ratio-scale four-way (VanderWeele §3.4/§3.3)
#
# When the OUTCOME is binary the mediation dispatch also attaches a
# four_way_ratio block (excess relative risk scale) alongside the NDE/NIE.
# Binary mediator → §3.4 (logistic mediator), continuous mediator → §3.3
# (linear mediator + residual variance).


def _binary_outcome_med_data(n=1200, seed=0, continuous_mediator=False):
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    if continuous_mediator:
        m = 0.2 + 0.8 * x + rng.normal(0, 1.0, n)
    else:
        m = rng.binomial(1, 1 / (1 + np.exp(-(-0.2 + 1.0 * x))))
    y = rng.binomial(1, 1 / (1 + np.exp(-(-1.0 + 0.6 * x + 0.7 * m + 0.4 * x * m))))
    return pd.DataFrame({
        "x": x.astype(float),
        "m": m if continuous_mediator else m.astype(float),
        "y": y.astype(float),
    })


def test_binary_outcome_binary_mediator_attaches_ratio_section_3_4():
    df = _binary_outcome_med_data(seed=1, continuous_mediator=False)
    out = themis.estimate(_clean_mediation_ast(), df, ci_bootstrap=30,
                          random_state=7)
    est = out["results"][0]["numeric_estimate"]
    fr = est["four_way_ratio"]
    assert fr["mediator_scale"] == "binary"
    assert "mediator_residual_variance" not in fr        # §3.4 has no ss_m
    # the four ERR pieces sum to the total excess relative risk
    s = sum(fr[k]["point"] for k in ("err_cde", "err_intref", "err_intmed", "err_pie"))
    assert abs(s - fr["total_err"]["point"]) < 1e-9
    assert fr["err_cde"]["ci_lower"] is not None


def test_binary_outcome_continuous_mediator_attaches_ratio_section_3_3():
    """A continuous mediator under a binary (logit) outcome: the
    difference-scale four-way is skipped (four_way_unavailable) and the
    §3.3 ratio block fills in."""
    ast = _clean_mediation_ast()
    ast["statements"][1] = {"kind": "variable", "predicate": "m",
                            "domain": [0.0, 1.0]}     # framing-only domain
    df = _binary_outcome_med_data(seed=2, continuous_mediator=True)
    out = themis.estimate(ast, df, ci_bootstrap=30, random_state=7)
    est = out["results"][0]["numeric_estimate"]
    fr = est["four_way_ratio"]
    assert fr["mediator_scale"] == "continuous"
    assert fr["mediator_residual_variance"] > 0
    s = sum(fr[k]["point"] for k in ("err_cde", "err_intref", "err_intmed", "err_pie"))
    assert abs(s - fr["total_err"]["point"]) < 1e-9
    # the difference-scale block is (correctly) unavailable for this shape,
    # and WHY is a statement rather than a sentence the estimator wrote.
    # The positive case is a structured block; a negative written as one
    # string is how a negative comes to be prose in one language.
    reason = est["four_way_unavailable"]["reason"]
    assert reason == {
        "vocabulary": "four_way_unavailable",
        "token": "the_mediator_is_continuous_under_a_nonlinear_outcome",
    }
    zh, en = language.spoke(reason, "zh"), language.spoke(reason, "en")
    assert zh != en and "m∈{0,1}" in zh and "m∈{0,1}" in en


def test_continuous_outcome_gets_no_ratio_block():
    """A continuous outcome has no excess relative risk — the ratio block
    must NOT be attached (only the difference-scale four-way)."""
    df = _clean_med_data(n=2000, seed=0)          # continuous y
    out = themis.estimate(_clean_mediation_ast(), df, random_state=42)
    est = out["results"][0]["numeric_estimate"]
    assert "four_way_ratio" not in est


def test_ratio_block_output_validates_against_schema():
    from themis.input.syntactic_validator import validate_result
    df = _binary_outcome_med_data(seed=3, continuous_mediator=False)
    out = themis.estimate(_clean_mediation_ast(), df, ci_bootstrap=20,
                          random_state=7)
    for r in out["results"]:
        validate_result(r)


def test_a_singular_design_reaches_the_caller_with_its_reason():
    """The mediator is the treatment relabelled, so the outcome fit is
    rank-deficient. Before the estimator had a species for it, the solver's
    ``LinAlgError`` — a ``ValueError`` subclass — was caught by dispatch's
    generic guard and the query ended with a missing number and no reason.

    The identification verdict still stands; what changes is that the
    envelope now says why no number came with it."""
    from themis import refusals
    from themis.refusals import Refusal, Kind

    rng = np.random.default_rng(0)
    n = 400
    x = rng.random(n) < 0.5
    df = pd.DataFrame({"x": x, "m": x, "y": rng.random(n) < 0.5})

    out = themis.estimate(_clean_mediation_ast(), df, random_state=42)
    result = out["results"][0]
    assert result.get("numeric_estimate") is None

    failure = result["estimator_failure"]
    assert failure["estimator"] == "mediation"
    assert failure["failure_type"] == Refusal.SINGULAR_DESIGN
    assert failure["kind"] == Kind.DATA
