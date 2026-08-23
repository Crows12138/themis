"""Tests for the outcome_model_quasi_separation gap_kind.

When the backdoor logistic outcome model E[Y|X,Z] saturates (logits
blow up because the outcome is near-deterministic in some
(treatment, confounder) stratum), the plug-in g-formula plug-in
extrapolates with a near-singular gradient. Point estimate computes
fine; CI is misleadingly tight.

Distinct from propensity_overlap_violation: that inspects
the treatment-assignment model P(X|Z); this inspects the outcome
model P(Y|X,Z). Both can fire on the same data — they're independent
diagnostics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from themis.estimation.dispatch import (
    OUTCOME_SATURATION_FRACTION,
    OUTCOME_SATURATION_LOWER,
    OUTCOME_SATURATION_UPPER,
    _attach_outcome_separation_warning,
)
from themis.estimation.contract import validate_data


def _separating_outcome_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Outcome is near-deterministic given (X, Z): logistic outcome
    logits saturate, fitted P(Y|X,Z) clusters near 0/1."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(size=n) < 0.5)
    # Outcome with very strong linear dependence on x and z → logits
    # huge → fitted probabilities pile at 0 or 1.
    logits = 6.0 * z + 4.0 * x.astype(float)
    p = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.random(size=n) < p)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _well_behaved_outcome_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Outcome model is mild — fitted probabilities live near 0.5."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = (rng.random(size=n) < 0.5)
    logits = 0.3 * z + 0.2 * x.astype(float)
    p = 1.0 / (1.0 + np.exp(-logits))
    y = (rng.random(size=n) < p)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _contract_for(df: pd.DataFrame):
    return validate_data(df, required_columns={"x", "y", "z"})


# ---------------------------------------------------------------------------
# Positive trigger
# ---------------------------------------------------------------------------


def test_separating_data_attaches_gap():
    df = _separating_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    report = result.get("data_gap_report")
    assert report is not None
    kinds = [g["kind"] for g in report["gaps"]]
    assert "outcome_model_quasi_separation" in kinds


def test_separation_gap_has_informational_severity():
    df = _separating_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    gap = result["data_gap_report"]["gaps"][0]
    assert gap["severity"] == "informational"
    assert gap["blocks"] == "interpretation"


def test_separation_gap_describes_min_max_and_threshold():
    df = _separating_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    desc = result["data_gap_report"]["gaps"][0]["description"]
    assert "[0.01, 0.99]" in desc
    assert "min=" in desc
    assert "max=" in desc
    assert "quasi-separation" in desc.lower()


def test_separation_gap_provenance_names_outcome_treatment_z():
    df = _separating_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    prov = result["data_gap_report"]["gaps"][0]["provenance"]
    assert len(prov) == 1
    assert prov[0]["ref_kind"] == "verifier_check"
    rid = prov[0]["ref_id"]
    assert "y" in rid
    assert "x" in rid
    assert "z" in rid


def test_separation_mirrors_warning_to_explanation():
    df = _separating_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    explanation = result.get("explanation", "")
    assert "⚠" in explanation
    assert "quasi-separation" in explanation.lower()


# ---------------------------------------------------------------------------
# Skip paths — no gap
# ---------------------------------------------------------------------------


def test_well_behaved_data_skips_gap():
    df = _well_behaved_outcome_data()
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    report = result.get("data_gap_report")
    if report is not None:
        kinds = [g["kind"] for g in report["gaps"]]
        assert "outcome_model_quasi_separation" not in kinds


def test_continuous_outcome_skips_gap():
    """Only logistic outcome can saturate this way; continuous outcome
    surfaces other pathology (heteroskedasticity etc.) — out of scope."""
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "x": (rng.random(size=n) < 0.5),
        "y": rng.normal(size=n),  # continuous
        "z": rng.normal(size=n),
    })
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    assert "data_gap_report" not in result


def test_continuous_treatment_skips_gap():
    """Diagnostic v1 only handles binary treatment column."""
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "x": rng.normal(size=n),  # continuous
        "y": (rng.normal(size=n) > 0),
        "z": rng.normal(size=n),
    })
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    assert "data_gap_report" not in result


def test_single_outcome_value_skips_gap():
    """All-True or all-False outcome — model can't be fit, skip silently."""
    rng = np.random.default_rng(0)
    n = 100
    df = pd.DataFrame({
        "x": (rng.random(size=n) < 0.5),
        "y": [True] * n,  # everyone has the outcome
        "z": rng.normal(size=n),
    })
    contract = _contract_for(df)
    result: dict = {}
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    assert "data_gap_report" not in result


def test_separation_appends_to_existing_data_gap_report():
    df = _separating_outcome_data()
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
        }
    }
    _attach_outcome_separation_warning(
        result, contract, treatment="x", outcome="y", adjustment=("z",),
    )
    kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    assert kinds == [
        "iv_identification_assumption_required",
        "outcome_model_quasi_separation",
    ]


# ---------------------------------------------------------------------------
# Threshold sanity
# ---------------------------------------------------------------------------


def test_threshold_constants_are_sensible():
    assert 0 < OUTCOME_SATURATION_LOWER < OUTCOME_SATURATION_UPPER < 1
    assert 0 < OUTCOME_SATURATION_FRACTION < 1


def test_full_estimate_pipeline_attaches_gap():
    """End-to-end: themis.estimate on saturating data surfaces the
    gap on the result envelope."""
    import themis

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "sep_test",
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

    out = themis.estimate(program, _separating_outcome_data())
    result = out["results"][0]
    report = result.get("data_gap_report") or {}
    kinds = [g["kind"] for g in report.get("gaps", [])]
    assert "outcome_model_quasi_separation" in kinds, (
        f"expected outcome_model_quasi_separation in gaps, got {kinds}"
    )
