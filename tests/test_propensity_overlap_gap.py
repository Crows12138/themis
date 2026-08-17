"""Tests for the propensity_overlap_violation gap_kind.

Hernan & Robins ch.3 "positivity": every confounder stratum must have
both treated and untreated units. When estimated P(X=1|Z) is bounded
away from {0,1} for too few observations, the backdoor / g-formula
estimate extrapolates the outcome regression into off-support
territory. Themis surfaces this as a `propensity_overlap_violation`
informational gap_kind.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from themis.estimation.dispatch import (
    PROPENSITY_OVERLAP_LOWER,
    PROPENSITY_OVERLAP_UPPER,
    PROPENSITY_OVERLAP_VIOLATION_FRACTION,
    _attach_propensity_overlap_warning,
)
from themis.estimation.contract import validate_data


def _good_overlap_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Z is mildly predictive of X — propensity stays well within
    [0.05, 0.95] for nearly all observations."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    # Logistic with small slope keeps p_hat near 0.5
    logits = 0.3 * z
    p = 1.0 / (1.0 + np.exp(-logits))
    x = rng.binomial(1, p).astype(bool)
    y = (x.astype(float) + 0.5 * z + rng.normal(size=n)) > 0
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _violated_overlap_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Z almost perfectly predicts X — propensities pile up near 0 / 1."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    # Steep logistic = pushed-to-the-corners propensities
    logits = 5.0 * z
    p = 1.0 / (1.0 + np.exp(-logits))
    x = rng.binomial(1, p).astype(bool)
    y = (x.astype(float) + rng.normal(size=n)) > 0
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _contract_for(df: pd.DataFrame):
    return validate_data(df, required_columns={"x", "y", "z"})


# ---------------------------------------------------------------------------
# Happy path: violation detected
# ---------------------------------------------------------------------------


def test_violation_attaches_gap():
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    report = result.get("data_gap_report")
    assert report is not None
    kinds = [g["kind"] for g in report["gaps"]]
    assert "propensity_overlap_violation" in kinds


def test_violation_gap_has_informational_severity():
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    gap = result["data_gap_report"]["gaps"][0]
    assert gap["severity"] == "informational"
    assert gap["blocks"] == "interpretation"


def test_violation_gap_describes_propensity_bounds():
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    desc = result["data_gap_report"]["gaps"][0]["description"]
    assert "[0.05, 0.95]" in desc
    assert "min=" in desc
    assert "max=" in desc


def test_violation_carries_provenance_naming_treatment_and_z():
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    prov = result["data_gap_report"]["gaps"][0]["provenance"]
    assert len(prov) == 1
    assert prov[0]["ref_kind"] == "verifier_check"
    assert "x" in prov[0]["ref_id"]
    assert "z" in prov[0]["ref_id"]


def test_violation_mirrors_warning_to_explanation():
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    explanation = result.get("explanation", "")
    assert "⚠" in explanation
    assert "P(x=1|Z)" in explanation


# ---------------------------------------------------------------------------
# Skip paths: no gap added
# ---------------------------------------------------------------------------


def test_good_overlap_skips_gap():
    df = _good_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    # Either no report or no overlap-violation kind in it.
    report = result.get("data_gap_report")
    if report is not None:
        kinds = [g["kind"] for g in report["gaps"]]
        assert "propensity_overlap_violation" not in kinds


def test_empty_adjustment_skips_gap():
    """No adjustment → nothing to overlap on. Skip silently."""
    df = _violated_overlap_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=(),
    )
    assert "data_gap_report" not in result
    assert "explanation" not in result


def test_non_bool_treatment_skips_gap():
    """Multi-arm / continuous treatment — diagnostic doesn't generalise
    cleanly in v1. Helper guards against this defensively even though
    the data contract usually normalizes 0/1 ints back to bool — when
    the column is genuinely continuous (e.g. dose level) the guard
    still has to fire."""
    rng = np.random.default_rng(0)
    n = 200
    z = rng.normal(size=n)
    df = pd.DataFrame({
        # Continuous treatment — contract preserves float64 dtype.
        "x": rng.normal(size=n),
        "y": rng.normal(size=n) > 0,
        "z": z,
    })
    contract = _contract_for(df)
    assert not pd.api.types.is_bool_dtype(contract.data["x"]), (
        "test setup broken — contract should preserve continuous x"
    )
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    assert "data_gap_report" not in result


def test_single_arm_treatment_skips_gap():
    """Treatment column has only one value — skip rather than crash."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "x": [True] * 100,  # everyone treated
        "y": rng.normal(size=100) > 0,
        "z": rng.normal(size=100),
    })
    contract = _contract_for(df)
    result: dict = {}
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    assert "data_gap_report" not in result


def test_violation_appends_to_existing_data_gap_report():
    """Gap is appended to a prior report rather than overwriting."""
    df = _violated_overlap_data()
    contract = _contract_for(df)
    pre = {
        "kind": "iv_identification_assumption_required",
        "severity": "informational",
        "blocks": "interpretation",
        "description": "stub",
        "required_data": None,
        "alternative_paths": [],
        "provenance": [],
    }
    result = {
        "data_gap_report": {
            "summary": "preexisting",
            "gaps": [pre],
            "actionable_next_steps": [],
        }
    }
    _attach_propensity_overlap_warning(
        result, contract, treatment="x", adjustment=("z",),
    )
    kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    assert kinds == [
        "iv_identification_assumption_required",
        "propensity_overlap_violation",
    ]


# ---------------------------------------------------------------------------
# Threshold sanity
# ---------------------------------------------------------------------------


def test_threshold_constants_are_sensible():
    assert 0 < PROPENSITY_OVERLAP_LOWER < PROPENSITY_OVERLAP_UPPER < 1
    assert 0 < PROPENSITY_OVERLAP_VIOLATION_FRACTION < 1


def test_full_estimate_pipeline_attaches_gap():
    """End-to-end sanity: themis.estimate on a data set with poor
    overlap surfaces the gap on the result envelope."""
    import themis

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            # variable declarations are required for themis.estimate to
            # collect required DataFrame columns (see
            # _collect_required_columns in dispatch.py).
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x", "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y", "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "overlap_test",
             "query": {
                 "kind": "effect",
                 "target": {
                     "atom": {"predicate": "y",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "intervention": {
                     "atom": {"predicate": "x",
                              "args": [{"type": "const", "name": "me"}]},
                     "value": True,
                 },
                 "given": [],
             }},
        ],
    }

    out = themis.estimate(program, _violated_overlap_data())
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    kinds = [g["kind"] for g in report.get("gaps", [])]
    assert "propensity_overlap_violation" in kinds, (
        f"expected propensity_overlap_violation in gaps, got {kinds}"
    )
