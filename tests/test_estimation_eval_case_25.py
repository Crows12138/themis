"""Phase 7.1 S.N.6 — eval case 25 end-to-end (backdoor numeric estimate).

Validates the full stack on a realistic observational-study scenario:

- Synthetic DGP where age confounds medication → systolic_bp
- True ATE = -10 mmHg
- Naive (unadjusted) estimate is biased because of age confounding
- themis.estimate correctly identifies backdoor adjustment on {age}
  and recovers the true ATE within tolerance
- themis.verify round-trips the resulting estimate

Case file: docs/eval_set/cases/25_medication_bp_backdoor_numeric.json
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
    / "25_medication_bp_backdoor_numeric.json"
)


def _load_case() -> dict:
    with _CASE_PATH.open("r", encoding="utf-8") as f:
        return json.load(f)


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _case_25_ast() -> dict:
    """The kernel_ast an A1-driven agent would emit for case 25."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "variable", "predicate": "medication", "domain": [True, False]},
            {"kind": "variable", "predicate": "systolic_bp", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("medication")},
            {"kind": "cause", "from": _atom("age"), "to": _atom("systolic_bp")},
            {"kind": "cause", "from": _atom("medication"), "to": _atom("systolic_bp")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("medication"), "value": True},
                "target": {"atom": _atom("systolic_bp"), "value": True},
                "given": [],
            }},
        ],
    }


def _case_25_data(n=1000, seed=0) -> pd.DataFrame:
    """Synthetic data matching the DGP described in the case gold block.

    age ~ Uniform(40, 80)
    medication ~ Bernoulli(sigmoid(0.1*(age - 60)))  # older → more likely
    systolic_bp = 0.8*age + 80 + (-10)*medication + Normal(0, 5)

    True ATE = -10 mmHg. Confounding through age is strong enough that
    the naive (unadjusted) estimate is biased positive — a clean pass
    requires adjusting for age.
    """
    rng = np.random.default_rng(seed)
    age = rng.uniform(40, 80, size=n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    medication = rng.random(n) < p_med
    bp = 0.8 * age + 80 + (-10.0) * medication.astype(float) + rng.standard_normal(n) * 5
    return pd.DataFrame({
        "age": age, "medication": medication, "systolic_bp": bp,
    })


# ============================================ correctness


def test_case_25_recovers_true_ate():
    df = _case_25_data(n=2000, seed=0)
    out = themis.estimate(
        _case_25_ast(), df,
        ci_bootstrap=0, random_state=42,
    )
    result = out["results"][0]
    assert result["status"] == "numerically_solved"
    est = result["numeric_estimate"]
    assert est["method"] == "backdoor_linear"
    assert est["adjustment"] == ["age"]

    case = _load_case()
    true_ate = case["gold_numeric_estimate"]["true_ate"]
    tol = case["gold_numeric_estimate"]["tolerance"]
    assert abs(est["point"] - true_ate) < tol, (
        f"estimate {est['point']} off from true ATE {true_ate} by more than {tol}"
    )


def test_case_25_naive_estimate_biased_without_adjustment():
    """Sanity: the whole reason we need backdoor adjustment is that
    a naive mean-difference estimator is biased on this DGP. This test
    confirms the DGP itself has the confounding we designed in."""
    df = _case_25_data(n=2000, seed=0)
    naive = df.loc[df["medication"], "systolic_bp"].mean() - df.loc[
        ~df["medication"], "systolic_bp"
    ].mean()
    # True ATE is -10; naive is biased upward by age confounding
    assert naive > -5, (
        f"naive estimate {naive} should be substantially less negative "
        f"than the true -10 due to age confounding"
    )


def test_case_25_bootstrap_ci_brackets_truth():
    """With reasonable sample size + 100 bootstrap iters the 95% CI
    should cover the true ATE = -10."""
    df = _case_25_data(n=1000, seed=0)
    out = themis.estimate(
        _case_25_ast(), df, ci_bootstrap=100, random_state=1,
    )
    est = out["results"][0]["numeric_estimate"]
    assert est["ci_lower"] is not None
    assert est["ci_upper"] is not None
    assert est["ci_lower"] <= -10.0 <= est["ci_upper"], (
        f"true ATE -10 outside CI [{est['ci_lower']}, {est['ci_upper']}]"
    )


# ============================================ case file consistency


def test_case_25_file_declares_correct_gold():
    """Guard: case file's gold_extensions and gold_numeric_estimate
    don't drift from what the kernel actually produces."""
    df = _case_25_data(n=1000, seed=0)
    out = themis.estimate(_case_25_ast(), df, ci_bootstrap=0)
    est = out["results"][0]["numeric_estimate"]

    case = _load_case()
    assert est["adjustment"] == case["gold_extensions"]["adjustment_set"]
    assert est["method"] == case["gold_numeric_estimate"]["method_expected"]


# ============================================ verify round-trip


def test_case_25_themis_verify_round_trips():
    df = _case_25_data(n=500, seed=0)
    ast = _case_25_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    result = out["results"][0]
    # Must not raise
    themis.verify(ast, result)
