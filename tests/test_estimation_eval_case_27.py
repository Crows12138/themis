"""Phase 7.3 S.IVN.5 — eval case 27 end-to-end.

Mendelian randomization scenario: gene_variant as IV for high_cholesterol
→ heart_disease, with latent lifestyle confounder.
"""
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
    / "27_gene_cholesterol_heart_iv_numeric.json"
)


def _load_case():
    with _CASE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _case_27_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "gene_variant", "domain": [True, False]},
            {"kind": "variable", "predicate": "high_cholesterol", "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_disease", "domain": [True, False]},
            {"kind": "cause", "from": _atom("gene_variant"),
             "to": _atom("high_cholesterol")},
            {"kind": "cause", "from": _atom("high_cholesterol"),
             "to": _atom("heart_disease")},
            {"kind": "bidirected",
             "left": _atom("high_cholesterol"), "right": _atom("heart_disease")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("high_cholesterol"), "value": True},
                "target": {"atom": _atom("heart_disease"), "value": True},
                "given": [],
            }},
        ],
    }


def _case_27_data(n=5000, seed=0):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    gene = rng.random(n) < 0.5
    chol = rng.random(n) < (
        1 / (1 + np.exp(-(1.5 * gene.astype(float) - 0.5 + 0.5 * u)))
    )
    heart = rng.random(n) < (
        1 / (1 + np.exp(-(1.0 * chol.astype(float) + 1.5 * u - 1)))
    )
    return pd.DataFrame({
        "gene_variant": gene,
        "high_cholesterol": chol,
        "heart_disease": heart,
    })


def test_case_27_recovers_true_late():
    df = _case_27_data(n=5000, seed=0)
    out = themis.estimate(
        _case_27_ast(), df, ci_bootstrap=0, random_state=42,
    )
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "iv_wald"
    assert est["instrument"] == "gene_variant"

    case = _load_case()
    true_late = case["gold_numeric_estimate"]["true_late"]
    tol = case["gold_numeric_estimate"]["tolerance"]
    assert abs(est["point"] - true_late) < tol


def test_case_27_naive_biased():
    df = _case_27_data(n=5000, seed=0)
    naive = (
        df.loc[df["high_cholesterol"], "heart_disease"].mean()
        - df.loc[~df["high_cholesterol"], "heart_disease"].mean()
    )
    # Naive is confounded by lifestyle — should be larger than true LATE 0.18
    assert naive > 0.30


def test_case_27_verify_round_trip():
    df = _case_27_data(n=500, seed=0)
    ast = _case_27_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    themis.verify(ast, out["results"][0])
