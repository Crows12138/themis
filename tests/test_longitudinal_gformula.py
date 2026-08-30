"""Phase 7.L — longitudinal (parametric) g-formula / g-computation.

THE POINT of g-methods (Hernán & Robins, *Causal Inference: What If*,
Part III, ch.21): when a time-varying confounder L_1 is AFFECTED BY PAST
TREATMENT A_0 and also drives the later treatment A_1 and the outcome Y,
ordinary outcome regression that ADJUSTS for L_1 is BIASED — adjusting
for L_1 blocks the indirect path A_0 → L_1 → Y. The g-formula instead
SIMULATES L_1 forward under the treatment strategy, so it keeps that
indirect effect.

Synthetic 2-time-point DGP with the classic structure
(L_1 ← A_0, A_1 ← L_1, Y ← A_0, A_1, L_1) and a KNOWN true strategy
effect computed by direct large-n SCM simulation of always-treat vs
never-treat. Structural equations::

    L_0 ~ N(0, 1)
    A_0 ~ Bernoulli(expit(0.5·L_0))
    L_1 = 1.0·A_0 + 0.5·L_0 + N(0, 1)        # confounder ← past treatment
    A_1 ~ Bernoulli(expit(0.8·L_1 − 0.4))    # later treatment ← confounder
    Y   = 2.0·A_0 + 3.0·A_1 + 1.5·L_1 + 0.5·L_0 + N(0, 1)

Closed-form truth (E[L_0]=0, E[L_1 | do(A_0=a)] = a):
    E[Y_{a0,a1}] = 2·a0 + 3·a1 + 1.5·a0 = 3.5·a0 + 3·a1
    ψ = E[Y_{1,1}] − E[Y_{0,0}] = 6.5

Naive Y ~ A_0 + A_1 + L_1 regression recovers the STRUCTURAL coefficients
(coef_A0≈2.0, coef_A1≈3.0) → strategy contrast ≈ 5.0, biased LOW by 1.5
(the A_0 → L_1 → Y indirect effect it conditioned away). The g-formula
recovers ≈ 6.5.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import LinearRegression

import themis
from themis.refusals import EstimatorFailure
from themis.estimation.longitudinal import (
    LongitudinalGFormulaEstimate,
    estimate_longitudinal_gformula,
)


TRUE_STRATEGY_EFFECT = 6.5  # analytic; cross-checked by direct SCM below


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _gen_dgp(n: int, seed: int) -> pd.DataFrame:
    """One row per subject from the time-varying-confounding DGP."""
    rng = np.random.default_rng(seed)
    L0 = rng.normal(0, 1, n)
    A0 = rng.random(n) < _expit(0.5 * L0)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.8 * L1 - 0.4)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + rng.normal(0, 1, n)
    return pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1, "Y": Y})


def _truth_by_direct_scm(a0: float, a1: float, n: int = 400_000,
                         seed: int = 7) -> float:
    """E[Y under the sustained strategy (A_0=a0, A_1=a1)] by directly
    simulating the SCM with the treatments forced — the oracle the
    g-formula must reproduce without ever seeing the equations."""
    rng = np.random.default_rng(seed)
    L0 = rng.normal(0, 1, n)
    A0 = np.full(n, a0, dtype=float)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = np.full(n, a1, dtype=float)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + rng.normal(0, 1, n)
    return float(Y.mean())


def _naive_outcome_regression_strategy_effect(df: pd.DataFrame) -> float:
    """The BIASED comparator: OLS of Y on (A_0, A_1, L_1), then contrast
    the all-treated vs all-control prediction averaged over observed L_1.
    Conditions on L_1 — the mediator of A_0 — so it drops the indirect
    A_0 → L_1 → Y effect."""
    X = df[["A0", "A1", "L1"]].astype(float).to_numpy()
    reg = LinearRegression().fit(X, df["Y"].to_numpy())
    Xt = X.copy(); Xt[:, 0] = 1.0; Xt[:, 1] = 1.0
    Xc = X.copy(); Xc[:, 0] = 0.0; Xc[:, 1] = 0.0
    return float((reg.predict(Xt) - reg.predict(Xc)).mean())


# ---------------------------------------------------------------------------
# Oracle: the analytic truth matches a direct large-n SCM simulation
# ---------------------------------------------------------------------------


def test_true_strategy_effect_matches_direct_scm_simulation():
    psi = _truth_by_direct_scm(1, 1) - _truth_by_direct_scm(0, 0)
    assert psi == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.05)


# ---------------------------------------------------------------------------
# THE conformance test: naive is biased, g-formula recovers the truth
# ---------------------------------------------------------------------------


def test_naive_biased_gformula_recovers_truth():
    """The whole reason g-methods exist, in one assertion block."""
    df = _gen_dgp(n=12_000, seed=1)

    naive = _naive_outcome_regression_strategy_effect(df)
    est = estimate_longitudinal_gformula(
        df,
        treatments=("A0", "A1"),
        confounders_by_time=(("L0",), ("L1",)),
        outcome="Y",
        n_sim=40_000,
        ci_bootstrap=0,
        random_state=42,
    )

    # (a) naive outcome regression that conditions on L_1 is BIASED:
    #     it sits ~1.5 below the truth (the A_0 → L_1 → Y indirect effect).
    assert abs(naive - TRUE_STRATEGY_EFFECT) > 1.0
    assert naive == pytest.approx(5.0, abs=0.3)

    # (b) the g-formula RECOVERS the true strategy effect within
    #     sampling error.
    assert est.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.3)

    # (c) and it is decisively closer to the truth than the naive
    #     estimator — the bias is removed, not merely reduced.
    assert abs(est.point - TRUE_STRATEGY_EFFECT) < abs(naive - TRUE_STRATEGY_EFFECT)


def test_strategy_means_contrast_consistency():
    """point == e_y_treated − e_y_control (the two simulated worlds)."""
    df = _gen_dgp(n=4_000, seed=2)
    est = estimate_longitudinal_gformula(
        df, treatments=("A0", "A1"),
        confounders_by_time=(("L0",), ("L1",)), outcome="Y",
        n_sim=10_000, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(est.e_y_treated - est.e_y_control, abs=1e-9)


# ---------------------------------------------------------------------------
# Determinism + result shape
# ---------------------------------------------------------------------------


def test_deterministic_given_random_state():
    df = _gen_dgp(n=3_000, seed=3)
    kw = dict(treatments=("A0", "A1"),
              confounders_by_time=(("L0",), ("L1",)), outcome="Y",
              n_sim=5_000, ci_bootstrap=20, random_state=123)
    a = estimate_longitudinal_gformula(df, **kw)
    b = estimate_longitudinal_gformula(df, **kw)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower
    assert a.ci_upper == b.ci_upper


def test_different_seed_changes_simulation():
    df = _gen_dgp(n=3_000, seed=3)
    kw = dict(treatments=("A0", "A1"),
              confounders_by_time=(("L0",), ("L1",)), outcome="Y",
              n_sim=5_000, ci_bootstrap=0)
    a = estimate_longitudinal_gformula(df, random_state=1, **kw)
    b = estimate_longitudinal_gformula(df, random_state=2, **kw)
    # MC noise differs, but both near truth.
    assert a.point != b.point
    assert a.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.4)
    assert b.point == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.4)


def test_frozen_dataclass_and_assumptions():
    df = _gen_dgp(n=2_000, seed=4)
    est = estimate_longitudinal_gformula(
        df, treatments=("A0", "A1"),
        confounders_by_time=(("L0",), ("L1",)), outcome="Y",
        n_sim=4_000, ci_bootstrap=0,
    )
    assert isinstance(est, LongitudinalGFormulaEstimate)
    with pytest.raises(Exception):
        est.point = 0.0  # frozen
    assert est.method == "longitudinal_gformula"
    # The four canonical g-formula assumptions (H&R ch.21).
    joined = " ".join(est.assumptions)
    assert "sequential_exchangeability" in joined
    assert "positivity" in joined
    assert "consistency" in joined
    assert "correct_specification" in joined


def test_bootstrap_ci_brackets_point_and_truth():
    df = _gen_dgp(n=4_000, seed=5)
    est = estimate_longitudinal_gformula(
        df, treatments=("A0", "A1"),
        confounders_by_time=(("L0",), ("L1",)), outcome="Y",
        n_sim=4_000, ci_bootstrap=60, ci_level=0.95, random_state=9,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper
    assert est.ci_lower <= TRUE_STRATEGY_EFFECT <= est.ci_upper
    # The g-formula's loop cannot drop a draw — the simulation always
    # returns two means — so a clean run is 60 of 60, and the record says
    # so rather than restating the request under a name that would read
    # the same on an estimator that CAN drop.
    assert est.draws is not None
    assert (est.draws.requested, est.draws.used) == (60, 60)
    assert est.draws.discarded == {}


# ---------------------------------------------------------------------------
# Refusals
# ---------------------------------------------------------------------------


def test_single_level_treatment_refuses():
    """Positivity maximally violated — no contrast to learn. Mirrors the
    cross-sectional backdoor estimator's overlap guard."""
    df = _gen_dgp(n=1_000, seed=6)
    df["A1"] = True  # collapse one treatment to a single level
    with pytest.raises(EstimatorFailure) as exc:
        estimate_longitudinal_gformula(
            df, treatments=("A0", "A1"),
            confounders_by_time=(("L0",), ("L1",)), outcome="Y",
            n_sim=1_000, ci_bootstrap=0,
        )
    assert exc.value.failure_type == "overlap_insufficient"


def test_length_mismatch_raises():
    df = _gen_dgp(n=500, seed=6)
    with pytest.raises(ValueError):
        estimate_longitudinal_gformula(
            df, treatments=("A0", "A1"),
            confounders_by_time=(("L0",),),  # too short
            outcome="Y", ci_bootstrap=0,
        )


def test_three_timepoints_runs():
    """K time points, not just 2 — the API is general over the horizon."""
    rng = np.random.default_rng(11)
    n = 3_000
    L0 = rng.normal(0, 1, n)
    A0 = rng.random(n) < _expit(0.3 * L0)
    L1 = 0.8 * A0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.5 * L1)
    L2 = 0.8 * A1 + rng.normal(0, 1, n)
    A2 = rng.random(n) < _expit(0.5 * L2)
    Y = A0 + A1 + A2 + 1.0 * L2 + rng.normal(0, 1, n)
    df = pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1,
                       "L2": L2, "A2": A2, "Y": Y})
    est = estimate_longitudinal_gformula(
        df, treatments=("A0", "A1", "A2"),
        confounders_by_time=(("L0",), ("L1",), ("L2",)), outcome="Y",
        n_sim=8_000, ci_bootstrap=0,
    )
    assert est.point > 0  # always-treat clearly beats never-treat here
    assert len(est.treatments) == 3


# ---------------------------------------------------------------------------
# Dispatch path: themis.estimate(..., options.longitudinal) + schema
# ---------------------------------------------------------------------------


def _load_validator():
    from themis.input.syntactic_validator import validator_for

    return validator_for("query_result.schema.json")


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "subj"}]}


def _longitudinal_program():
    """Declares the variables (so the data contract validates) and one
    effect query of A1 → Y; the longitudinal spec rides in options."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "subj"}]},
        "options": {
            "longitudinal": {
                "treatments": ["A0", "A1"],
                "confounders_by_time": [["L0"], ["L1"]],
                "outcome": "Y",
                "strategy_treated": 1,
                "strategy_control": 0,
                "n_sim": 8000,
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


def test_dispatch_attaches_longitudinal_block_and_validates_schema():
    df = _gen_dgp(n=6_000, seed=8)
    out = themis.estimate(_longitudinal_program(), df, ci_bootstrap=0)

    # find the result carrying the longitudinal numeric_estimate
    target = next(
        r for r in out["results"]
        if (r.get("numeric_estimate") or {}).get("method") == "longitudinal_gformula"
    )
    ne = target["numeric_estimate"]
    assert ne["point"] == pytest.approx(TRUE_STRATEGY_EFFECT, abs=0.35)
    block = ne["longitudinal_gformula"]
    assert block["treatments"] == ["A0", "A1"]
    assert block["confounders_by_time"] == [["L0"], ["L1"]]
    assert block["e_y_treated"] > block["e_y_control"]
    assert block["n_sim"] == 8000

    _load_validator().validate(target)


def test_dispatch_does_not_overwrite_with_static_backdoor():
    """The guard: once the longitudinal block is attached, the
    cross-sectional backdoor loop must NOT replace it with the biased
    static-adjustment ATE."""
    df = _gen_dgp(n=6_000, seed=8)
    out = themis.estimate(_longitudinal_program(), df, ci_bootstrap=0)
    target = next(
        r for r in out["results"]
        if r.get("numeric_estimate", {}).get("method") == "longitudinal_gformula"
    )
    # still the longitudinal method, not backdoor_*
    assert target["numeric_estimate"]["method"] == "longitudinal_gformula"
