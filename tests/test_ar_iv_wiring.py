"""Pipeline wiring for the Anderson-Rubin weak-IV-robust confidence set.

The AR set rides on the existing IV numeric end. This slice
threads it through the estimation dispatch, schema, and independent verifier
so a client gets the weak-robust confidence set alongside the IV point, and a
second, independent pass RE-SOLVES it from the reported residualised
sufficient statistics (kappa, the quadratic, the set shape/endpoints, and the
point Szy/Szx). A tampered AR set, point, or kappa is rejected; an IV result
carrying no AR block still verifies (the check is additive).
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import gaps
from themis.input.syntactic_validator import validate_result
from themis.verifier import VerificationError
from tests import caveats


# ------------------------------------------------------------------ builders
def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _iv_ast():
    """Z → X → Y with X ↔ Y latent: backdoor + front-door fail, IV fires."""
    return {
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


def _strong_iv_data(n=3000, seed=0, true_late=1.5):
    """A strong binary instrument → a bounded AR set (finite endpoints)."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    p_x = 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + 0.5 * u)))
    x = rng.random(n) < p_x
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _weak_iv_data(n=1500, seed=3, true_late=1.5, pi=0.15):
    """A weak binary instrument → first-stage F < 10 (Stock-Yogo)."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5
    p_x = 1 / (1 + np.exp(-(pi * (2 * z.astype(float) - 1) + 1.5 * u)))
    x = rng.random(n) < p_x
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _result(out):
    return out["results"][0]


def _numeric_iv_step(res):
    for st in res["derivation"]["steps"]:
        if st["rule"] == "numeric_iv_estimate":
            return st
    raise AssertionError("no numeric_iv_estimate step found")


# ------------------------------------------------------------------ schema
def test_schema_accepts_ar_confidence_set():
    res = _result(themis.estimate(_iv_ast(), _strong_iv_data(), ci_bootstrap=0))
    validate_result(res)  # round-trips the anderson_rubin_confidence_set block


# ------------------------------------------------------------------ estimate
def test_estimate_attaches_bounded_ar_set():
    res = _result(themis.estimate(_iv_ast(), _strong_iv_data(), ci_bootstrap=0))
    assert res["status"] == "numerically_solved"
    ne = res["numeric_estimate"]
    assert ne["method"] == "iv_wald"
    ar = ne["anderson_rubin_confidence_set"]
    assert ar["kind"] == "bounded"
    assert ar["lower"] < ar["point"] < ar["upper"]
    assert ar["ci_level"] == 0.95
    # the AR set brackets the just-identified point
    assert abs(ar["point"] - ne["point"]) < 1e-6 * (1 + abs(ne["point"]))


def test_the_weak_instrument_caveat_cites_the_ar_set():
    res = _result(themis.estimate(_iv_ast(), _weak_iv_data(), ci_bootstrap=0))
    ne = res["numeric_estimate"]
    # genuinely weak first stage
    assert ne["first_stage_f_stat"] < 10.0
    assert "anderson_rubin_confidence_set" in ne
    # the weak-IV caveat now names the concrete AR set, not generic advice
    assert "Anderson-Rubin" in caveats.text(res)
    gap = res["data_gap_report"]["gaps"]
    weak = [g for g in gap if g["kind"] == "weak_iv_instrument"]
    assert weak
    assert "use_the_ar_set" in [
        a["route"] for a in weak[0]["alternative_paths"]
    ]


def _weak_gap(res):
    return next(g for g in res["data_gap_report"]["gaps"]
                if g["kind"] == "weak_iv_instrument")


def test_the_set_is_notation_and_what_it_means_is_a_sentence():
    """An unbounded set is a FINDING, and a finding is somebody's sentence.

    `(−∞, +∞)` reads the same to every reader and "so the instrument
    constrains nothing" does not, so the renderer used to write one
    language into the hole of a bilingual sentence by appending the second
    to the first. They are two statements now: the notation fills the
    hole, and the reading stands beside it in the same list.
    """
    res = _result(themis.estimate(
        _iv_ast(), _weak_iv_data(pi=0.01, seed=23), ci_bootstrap=0))
    assert res["numeric_estimate"][
        "anderson_rubin_confidence_set"]["kind"] == "whole_line"
    said = _weak_gap(res)["describes"]
    assert [s["sentence"] for s in said] == [
        "the_first_stage_is_weak",
        "the_anderson_rubin_set_is_this",
        "the_set_constrains_nothing",
    ]
    # The notation is the same for both readers; the reading is not.
    assert said[1]["said"]["interval"] == "(−∞, +∞)"
    zh, en = (gaps.describe(said[2], "zh"), gaps.describe(said[2], "en"))
    assert zh != en and "整条实线" in zh and "whole real line" in en


def test_a_bounded_set_says_nothing_extra_and_reads_the_same_either_way():
    """The counterexample to the gate above: a set that DOES constrain says
    only what it is, and its notation is one string in both languages."""
    res = _result(themis.estimate(
        _iv_ast(), _weak_iv_data(), ci_bootstrap=0))
    said = _weak_gap(res)["describes"]
    assert "the_set_constrains_nothing" not in [s["sentence"] for s in said]
    interval = said[1]["said"]["interval"]
    assert interval.startswith("[")
    assert all(interval in gaps.describe(said[1], lang)
               for lang in ("zh", "en"))


# ------------------------------------------------------------------ verify
def test_verify_accepts_ar_result():
    ast = _iv_ast()
    themis.verify(ast, _result(themis.estimate(ast, _strong_iv_data(), ci_bootstrap=0)))


def test_verify_rejects_tampered_ar_lower():
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=1), ci_bootstrap=0))
    tam = copy.deepcopy(res)
    _numeric_iv_step(tam)["inputs"]["ar_lower"] = 999.0
    with pytest.raises(VerificationError):
        themis.verify(ast, tam)


def test_verify_rejects_tampered_ar_kind():
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=2), ci_bootstrap=0))
    tam = copy.deepcopy(res)
    _numeric_iv_step(tam)["inputs"]["ar_kind"] = "whole_line"
    with pytest.raises(VerificationError):
        themis.verify(ast, tam)


def test_verify_rejects_tampered_ar_kappa():
    # kappa is re-derived from ci_level + df, so a tampered kappa is caught.
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=4), ci_bootstrap=0))
    tam = copy.deepcopy(res)
    _numeric_iv_step(tam)["inputs"]["ar_kappa"] = 1.0
    with pytest.raises(VerificationError):
        themis.verify(ast, tam)


def test_verify_rejects_tampered_point_via_szy_szx():
    # The verifier re-derives the IV point as Szy/Szx from the reported
    # sufficient statistics; a tampered point no longer matches.
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=5), ci_bootstrap=0))
    tam = copy.deepcopy(res)
    _numeric_iv_step(tam)["inputs"]["point"] = 0.01
    with pytest.raises(VerificationError):
        themis.verify(ast, tam)


def test_verify_rejects_tampered_sufficient_statistic():
    # Changing a single sufficient stat makes the re-solved set / point
    # disagree with the reported ones.
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=6), ci_bootstrap=0))
    tam = copy.deepcopy(res)
    _numeric_iv_step(tam)["inputs"]["ar_s_zx"] *= 0.5
    with pytest.raises(VerificationError):
        themis.verify(ast, tam)


def test_iv_result_without_ar_block_still_verifies():
    # Backward compatibility: an IV numeric result carrying no AR fields
    # verifies through the metadata path (the AR re-solve is additive).
    ast = _iv_ast()
    res = _result(themis.estimate(ast, _strong_iv_data(seed=7), ci_bootstrap=0))
    stripped = copy.deepcopy(res)
    step = _numeric_iv_step(stripped)
    for k in list(step["inputs"]):
        if k.startswith("ar_"):
            del step["inputs"][k]
    stripped["numeric_estimate"].pop("anderson_rubin_confidence_set", None)
    themis.verify(ast, stripped)
