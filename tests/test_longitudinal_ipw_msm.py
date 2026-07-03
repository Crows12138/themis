"""Phase 7.L — longitudinal IPW marginal structural model (IPW-MSM).

An INDEPENDENT route to the same estimand as the parametric g-formula
(test_longitudinal_gformula.py): the time-varying treatment strategy
contrast E[Y_{always-treat}] − E[Y_{never-treat}]. The g-formula models
the covariate transitions + outcome; the IPW-MSM models the TREATMENT
process (per-time propensities → IP weights) and fits a marginal
structural mean model on the pseudo-population. Because the two are
misspecified in DIFFERENT ways, agreement between them is strong evidence
the estimate is right (Hernán & Robins, What If, ch.21) — that
cross-validation is the centerpiece of this file.

Same canonical 2-time-point DGP with time-varying confounding affected by
past treatment; analytic truth ψ = 6.5 (see the g-formula test for the
derivation). The naive Y ~ A0+A1+L1 regression is biased LOW to ≈5.0.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

import themis
from themis.estimation.dose_response import EstimatorFailure
from themis.estimation.longitudinal import (
    LongitudinalIPWMSMEstimate,
    estimate_longitudinal_gformula,
    estimate_longitudinal_ipw_msm,
)


TRUE_STRATEGY_EFFECT = 6.5

_REPO_ROOT = Path(__file__).resolve().parents[1]
_RESULT_SCHEMA_PATH = _REPO_ROOT / "themis" / "schemas" / "query_result.schema.json"
_DERIVATION_SCHEMA_PATH = _REPO_ROOT / "themis" / "schemas" / "derivation.schema.json"


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _gen_dgp(n: int, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    L0 = rng.normal(0, 1, n)
    A0 = rng.random(n) < _expit(0.5 * L0)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.8 * L1 - 0.4)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + rng.normal(0, 1, n)
    return pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1, "Y": Y})


def _naive_strategy_effect(df: pd.DataFrame) -> float:
    X = df[["A0", "A1", "L1"]].astype(float).to_numpy()
    reg = LinearRegression().fit(X, df["Y"].to_numpy(dtype=float))
    return float(reg.coef_[0] + reg.coef_[1])


_SPEC = dict(treatments=("A0", "A1"),
             confounders_by_time=(("L0",), ("L1",)),
             outcome="Y")


# ============================================ recovers truth, beats naive


def test_ipw_msm_recovers_true_strategy_effect():
    df = _gen_dgp(n=8000, seed=0)
    est = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0)
    assert est.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.4)
    # and materially above the L1-adjusted naive regression (biased low ~5.0)
    assert est.point - _naive_strategy_effect(df) > 0.8


def test_e_y_contrast_consistency():
    df = _gen_dgp(n=6000, seed=1)
    est = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0)
    assert est.e_y_treated - est.e_y_control == pytest.approx(est.point, abs=1e-9)
    # msm_coefficients = (β0, β_A0, β_A1); contrast = β_A0 + β_A1.
    assert len(est.msm_coefficients) == 3
    assert sum(est.msm_coefficients[1:]) == pytest.approx(est.point, abs=1e-9)


# ============================================ THE cross-validation


def test_ipw_msm_agrees_with_gformula():
    """The centerpiece: two estimators of the same estimand, misspecified
    in different ways, must land close on the same data."""
    df = _gen_dgp(n=9000, seed=2)
    msm = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0)
    gf = estimate_longitudinal_gformula(df, **_SPEC, ci_bootstrap=0)
    assert abs(msm.point - gf.point) < 0.4
    # both recover the truth
    assert msm.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.4)
    assert gf.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.4)


# ============================================ weights


def test_stabilized_weights_center_near_one():
    df = _gen_dgp(n=8000, seed=3)
    est = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0, stabilized=True)
    assert est.stabilized is True
    assert est.weight_mean == pytest.approx(1.0, abs=0.1)


def test_unstabilized_has_heavier_tail_but_same_estimand():
    df = _gen_dgp(n=8000, seed=3)
    stab = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0, stabilized=True)
    unstab = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0, stabilized=False)
    # Same target estimand → close point estimates ...
    assert abs(stab.point - unstab.point) < 0.4
    # ... but the unstabilized weights have a much heavier tail.
    assert unstab.weight_max > stab.weight_max
    assert unstab.stabilized is False


# ============================================ determinism / dataclass


def test_deterministic_given_random_state():
    df = _gen_dgp(n=4000, seed=4)
    kw = dict(**_SPEC, ci_bootstrap=80, random_state=11)
    a = estimate_longitudinal_ipw_msm(df, **kw)
    b = estimate_longitudinal_ipw_msm(df, **kw)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper


def test_bootstrap_ci_brackets_point():
    df = _gen_dgp(n=6000, seed=5)
    est = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=200, random_state=1)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_frozen_dataclass_and_assumptions():
    df = _gen_dgp(n=4000, seed=6)
    est = estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0)
    assert isinstance(est, LongitudinalIPWMSMEstimate)
    with pytest.raises(Exception):
        est.point = 0.0  # frozen
    assert est.method == "longitudinal_ipw_msm"
    assert any("propensity" in a for a in est.assumptions)
    assert any("marginal_structural_model" in a for a in est.assumptions)


# ============================================ guards


def test_single_level_treatment_refuses():
    df = _gen_dgp(n=2000, seed=7)
    df["A1"] = True  # collapse one treatment to a single level
    with pytest.raises(EstimatorFailure) as e:
        estimate_longitudinal_ipw_msm(df, **_SPEC, ci_bootstrap=0)
    assert e.value.failure_type == "overlap_insufficient"


def test_spec_length_mismatch_raises():
    df = _gen_dgp(n=2000, seed=7)
    with pytest.raises(ValueError):
        estimate_longitudinal_ipw_msm(
            df, treatments=("A0", "A1"),
            confounders_by_time=(("L0",),),  # too short
            outcome="Y", ci_bootstrap=0)


# ============================================ kernel dispatch (e2e)


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "subj"}]}


def _program(estimator: str):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "subj"}]},
        "options": {
            "longitudinal": {
                "estimator": estimator,
                "treatments": ["A0", "A1"],
                "confounders_by_time": [["L0"], ["L1"]],
                "outcome": "Y",
                "strategy_treated": 1,
                "strategy_control": 0,
                "ci_bootstrap": 0,
            }
        },
        "statements": [
            {"kind": "variable", "predicate": "L0"},
            {"kind": "variable", "predicate": "A0", "domain": [True, False]},
            {"kind": "variable", "predicate": "L1"},
            {"kind": "variable", "predicate": "A1", "domain": [True, False]},
            {"kind": "variable", "predicate": "Y"},
            {"kind": "cause", "from": _atom("A0"), "to": _atom("L1")},
            {"kind": "cause", "from": _atom("L1"), "to": _atom("A1")},
            {"kind": "cause", "from": _atom("L1"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("A0"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("A1"), "to": _atom("Y")},
            {"kind": "cause", "from": _atom("L0"), "to": _atom("A0")},
            {"kind": "cause", "from": _atom("L0"), "to": _atom("Y")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "target": {"atom": _atom("Y"), "value": True},
                 "intervention": {"atom": _atom("A1"), "value": True},
                 "given": [],
             }},
        ],
    }


def _load_validator():
    from jsonschema import Draft202012Validator
    from referencing import Registry, Resource
    result_schema = json.loads(_RESULT_SCHEMA_PATH.read_text(encoding="utf-8"))
    derivation_schema = json.loads(_DERIVATION_SCHEMA_PATH.read_text(encoding="utf-8"))
    atom_schema = json.loads(
        (_REPO_ROOT / "themis" / "schemas" / "atom.schema.json").read_text(encoding="utf-8"))
    registry = Registry().with_resources([
        ("derivation.schema.json", Resource.from_contents(derivation_schema)),
        ("atom.schema.json", Resource.from_contents(atom_schema)),
    ])
    return Draft202012Validator(result_schema, registry=registry)


def test_dispatch_ipw_msm_attaches_block_and_validates_schema():
    df = _gen_dgp(n=6000, seed=8)
    out = themis.estimate(_program("ipw_msm"), df, ci_bootstrap=0)
    target = next(
        r for r in out["results"]
        if (r.get("numeric_estimate") or {}).get("method") == "longitudinal_ipw_msm"
    )
    ne = target["numeric_estimate"]
    assert ne["point"] == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.5)
    block = ne["longitudinal_ipw_msm"]
    assert block["treatments"] == ["A0", "A1"]
    assert block["stabilized"] is True
    assert len(block["msm_coefficients"]) == 3
    assert block["weight_mean"] == pytest.approx(1.0, abs=0.15)
    assert block["e_y_treated"] > block["e_y_control"]
    _load_validator().validate(target)


def test_dispatch_default_estimator_is_gformula():
    """Omitting the estimator field keeps the g-formula (byte-compatible
    with the pre-existing longitudinal path)."""
    prog = _program("gformula")
    del prog["options"]["longitudinal"]["estimator"]
    df = _gen_dgp(n=5000, seed=9)
    out = themis.estimate(prog, df, ci_bootstrap=0)
    methods = {(r.get("numeric_estimate") or {}).get("method")
               for r in out["results"]}
    assert "longitudinal_gformula" in methods
    assert "longitudinal_ipw_msm" not in methods


def test_dispatch_unknown_estimator_rejected_by_schema():
    """The kernel_ast schema pins the estimator enum, so a bad value fails
    fast at syntactic validation rather than reaching the estimator."""
    from themis.input.syntactic_validator import SyntacticError
    prog = _program("bogus")
    df = _gen_dgp(n=3000, seed=10)
    with pytest.raises(SyntacticError) as e:
        themis.estimate(prog, df, ci_bootstrap=0)
    assert "gformula" in str(e.value) and "ipw_msm" in str(e.value)


def test_dispatch_guard_rejects_unknown_estimator_directly():
    """Defense-in-depth: the dispatch-level guard (reached only when a
    caller bypasses schema validation) surfaces an estimator_failure for an
    unknown estimator rather than crashing."""
    from themis.estimation.dispatch import _maybe_estimate_longitudinal
    from themis.estimation.contract import validate_data
    df = _gen_dgp(n=3000, seed=10)
    contract = validate_data(
        df, required_columns={"A0", "A1", "L0", "L1", "Y"})
    spec = {"estimator": "bogus", "treatments": ["A0", "A1"],
            "confounders_by_time": [["L0"], ["L1"]], "outcome": "Y"}
    program = {"options": {"longitudinal": spec}}
    output = {"results": [{"query_kind": "effect"}]}
    _maybe_estimate_longitudinal(program, output, contract,
                                 random_state=1, ci_bootstrap=0)
    fail = output["results"][0]["estimator_failure"]
    assert "gformula" in fail["reason"] and "ipw_msm" in fail["reason"]
