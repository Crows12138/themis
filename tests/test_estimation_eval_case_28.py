"""Phase 8.2.5 — eval case 28 (aspirin / heart attack with E-value)."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

import themis


_CASE_PATH = (
    Path(__file__).parent.parent
    / "docs" / "eval_set" / "cases"
    / "28_aspirin_heart_e_value_sensitivity.json"
)


def _load_case():
    with _CASE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _case_28_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "variable", "predicate": "aspirin", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_attack", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("aspirin")},
            {"kind": "cause", "from": _atom("age"), "to": _atom("heart_attack")},
            {"kind": "cause", "from": _atom("aspirin"), "to": _atom("heart_attack")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("aspirin"), "value": True},
                "target": {"atom": _atom("heart_attack"), "value": True},
                "given": [],
            }},
        ],
    }


def _case_28_data(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    age = rng.uniform(40, 80, size=n)
    aspirin = rng.random(n) < (1 / (1 + np.exp(-0.05 * (age - 60))))
    p_heart = 1 / (1 + np.exp(-(0.04 * (age - 60) - 0.5 * aspirin.astype(float) - 1.5)))
    heart = rng.random(n) < p_heart
    return pd.DataFrame({
        "age": age, "aspirin": aspirin, "heart_attack": heart,
    })


def test_case_28_recovers_protective_ate():
    df = _case_28_data(n=3000, seed=0)
    out = themis.estimate(_case_28_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert est["method"] == "backdoor_logistic"
    # ATE should be negative (aspirin reduces heart attack)
    assert est["point"] < 0


def test_case_28_attaches_e_value():
    df = _case_28_data(n=3000, seed=0)
    out = themis.estimate(_case_28_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]
    assert "sensitivity_analysis" in est

    sa = est["sensitivity_analysis"]
    assert sa["e_value"] is not None
    assert sa["risk_ratio"] is not None
    # Baseline rate should be near 0.20 by DGP construction
    assert 0.10 < sa["baseline_rate"] < 0.40

    case = _load_case()
    e_min = case["gold_numeric_estimate"]["sensitivity_expected"]["e_value_min"]
    e_max = case["gold_numeric_estimate"]["sensitivity_expected"]["e_value_max"]
    assert e_min < sa["e_value"] < e_max, (
        f"E-value {sa['e_value']} outside expected band [{e_min}, {e_max}]"
    )


def test_case_28_note_contains_interpretation():
    df = _case_28_data(n=2000, seed=0)
    out = themis.estimate(_case_28_ast(), df, ci_bootstrap=0)
    sa = out["results"][0]["numeric_estimate"]["sensitivity_analysis"]
    note = sa["note"]
    # Note should mention E-value and at least one threshold-band keyword
    assert "E-value" in note
    band_keywords = ("very weak", "modest", "moderate", "substantial", "very robust")
    assert any(k in note for k in band_keywords)


def test_case_28_verify_round_trips():
    df = _case_28_data(n=500, seed=0)
    ast = _case_28_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    themis.verify(ast, out["results"][0])
