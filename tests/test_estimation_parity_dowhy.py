"""Phase 7.1 S.N.7 — parity test: Themis backdoor ATE vs DoWhy.

Cross-checks that ``themis.estimate`` and ``DoWhy.CausalModel.estimate_effect``
produce numerically close point estimates on the same synthetic DGP.
Tolerance is loose by design — sklearn's LinearRegression / LogisticRegression
choose slightly different numerical paths than DoWhy's wrappers, but
both should converge on the true ATE within a few percent on clean
synthetic data.

DoWhy is a **dev-only dependency** (same pattern as test_iv_parity_dowhy).
Production builds exclude it per CLAUDE.md 5-rule API gate.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

try:
    from dowhy import CausalModel
    _DOWHY_AVAILABLE = True
except ImportError:
    _DOWHY_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not _DOWHY_AVAILABLE,
    reason="dowhy not installed (dev-only parity dependency)",
)

import themis


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _themis_ate(ast, df, seed=42):
    out = themis.estimate(ast, df, ci_bootstrap=0, random_state=seed)
    return out["results"][0]["numeric_estimate"]["point"]


def _dowhy_ate(df, treatment, outcome, graph_dot):
    model = CausalModel(
        data=df, treatment=treatment, outcome=outcome,
        graph=graph_dot,
    )
    ident = model.identify_effect(proceed_when_unidentifiable=True)
    estimate = model.estimate_effect(
        ident, method_name="backdoor.linear_regression",
    )
    return estimate.value


def _ast_linear_confounded():
    """age → medication → bp, age → bp. Backdoor via age."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "variable", "predicate": "medication", "domain": [True, False]},
            {"kind": "variable", "predicate": "bp", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("medication")},
            {"kind": "cause", "from": _atom("age"), "to": _atom("bp")},
            {"kind": "cause", "from": _atom("medication"), "to": _atom("bp")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("medication"), "value": True},
                "target": {"atom": _atom("bp"), "value": True},
                "given": [],
            }},
        ],
    }


def _dot_linear_confounded():
    return "digraph { age -> medication; age -> bp; medication -> bp; }"


# ============================================ parity cases


def test_parity_on_single_confounder_medium_effect():
    """True ATE = -10. Both tools should agree within 5%."""
    rng = np.random.default_rng(0)
    n = 2000
    age = rng.uniform(40, 80, n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    med = rng.random(n) < p_med
    bp = 0.8 * age + 80 - 10.0 * med.astype(float) + rng.standard_normal(n) * 5
    df = pd.DataFrame({"age": age, "medication": med, "bp": bp})

    themis_val = _themis_ate(_ast_linear_confounded(), df)
    dowhy_val = _dowhy_ate(df, "medication", "bp", _dot_linear_confounded())

    # Both should be close to -10
    assert abs(themis_val - (-10.0)) < 0.5
    assert abs(dowhy_val - (-10.0)) < 0.5
    # And close to each other
    assert abs(themis_val - dowhy_val) < 0.5


def test_parity_on_strong_effect():
    """True ATE = -20. Stronger signal, tighter tolerance."""
    rng = np.random.default_rng(1)
    n = 2000
    age = rng.uniform(40, 80, n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    med = rng.random(n) < p_med
    bp = 0.8 * age + 80 - 20.0 * med.astype(float) + rng.standard_normal(n) * 5
    df = pd.DataFrame({"age": age, "medication": med, "bp": bp})

    themis_val = _themis_ate(_ast_linear_confounded(), df)
    dowhy_val = _dowhy_ate(df, "medication", "bp", _dot_linear_confounded())

    assert abs(themis_val - (-20.0)) < 0.6
    assert abs(dowhy_val - (-20.0)) < 0.6
    assert abs(themis_val - dowhy_val) < 0.5


def test_parity_on_zero_effect():
    """True ATE = 0 — a hard case because noise dominates. Both tools
    should still converge to near-zero with reasonable sample size."""
    rng = np.random.default_rng(2)
    n = 3000
    age = rng.uniform(40, 80, n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    med = rng.random(n) < p_med
    bp = 0.8 * age + 80 + 0.0 * med.astype(float) + rng.standard_normal(n) * 5
    df = pd.DataFrame({"age": age, "medication": med, "bp": bp})

    themis_val = _themis_ate(_ast_linear_confounded(), df)
    dowhy_val = _dowhy_ate(df, "medication", "bp", _dot_linear_confounded())

    # Both should be close to 0 (within sampling noise)
    assert abs(themis_val) < 0.5
    assert abs(dowhy_val) < 0.5
    assert abs(themis_val - dowhy_val) < 0.3


def test_parity_on_positive_effect():
    """True ATE = +5.0 — check sign is correct."""
    rng = np.random.default_rng(3)
    n = 2000
    age = rng.uniform(40, 80, n)
    p_med = 1 / (1 + np.exp(-0.1 * (age - 60)))
    med = rng.random(n) < p_med
    bp = 0.8 * age + 80 + 5.0 * med.astype(float) + rng.standard_normal(n) * 5
    df = pd.DataFrame({"age": age, "medication": med, "bp": bp})

    themis_val = _themis_ate(_ast_linear_confounded(), df)
    dowhy_val = _dowhy_ate(df, "medication", "bp", _dot_linear_confounded())

    assert abs(themis_val - 5.0) < 0.5
    assert abs(dowhy_val - 5.0) < 0.5
    assert abs(themis_val - dowhy_val) < 0.5


def test_parity_on_multi_confounder_graph():
    """Two confounders: age + bmi. Both tools must find both in the
    adjustment set and produce close estimates."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "variable", "predicate": "bmi", "domain": [True, False]},
            {"kind": "variable", "predicate": "medication", "domain": [True, False]},
            {"kind": "variable", "predicate": "bp", "domain": [True, False]},
            {"kind": "cause", "from": _atom("age"), "to": _atom("medication")},
            {"kind": "cause", "from": _atom("age"), "to": _atom("bp")},
            {"kind": "cause", "from": _atom("bmi"), "to": _atom("medication")},
            {"kind": "cause", "from": _atom("bmi"), "to": _atom("bp")},
            {"kind": "cause", "from": _atom("medication"), "to": _atom("bp")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("medication"), "value": True},
                "target": {"atom": _atom("bp"), "value": True},
                "given": [],
            }},
        ],
    }
    dot = (
        "digraph { "
        "age -> medication; age -> bp; "
        "bmi -> medication; bmi -> bp; "
        "medication -> bp; "
        "}"
    )
    rng = np.random.default_rng(4)
    n = 3000
    age = rng.uniform(40, 80, n)
    bmi = rng.uniform(18, 35, n)
    logits = 0.1 * (age - 60) + 0.1 * (bmi - 25)
    med = rng.random(n) < 1 / (1 + np.exp(-logits))
    bp = (
        0.8 * age + 0.5 * bmi + 70
        - 10.0 * med.astype(float)
        + rng.standard_normal(n) * 5
    )
    df = pd.DataFrame({
        "age": age, "bmi": bmi, "medication": med, "bp": bp,
    })

    themis_val = _themis_ate(ast, df)
    dowhy_val = _dowhy_ate(df, "medication", "bp", dot)

    assert abs(themis_val - (-10.0)) < 0.6
    assert abs(dowhy_val - (-10.0)) < 0.6
    assert abs(themis_val - dowhy_val) < 0.5
