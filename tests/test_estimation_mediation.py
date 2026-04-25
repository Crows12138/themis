"""Phase 7.4 S.MN.1 — unit tests for the mediation numeric estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.mediation import (
    MediationEstimate,
    estimate_mediation,
)


def _linear_med_dgp(n=1000, seed=0, nde_true=0.5, nie_true=2.0):
    """Y = nde * X + nie/effect_on_M * M + noise, with M = 2 * X + noise.
    Implied NIE = (coef of X on M) * (coef of M on Y) = 2 * (nie_true/2) = nie_true."""
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    m = 2.0 * x + rng.standard_normal(n)
    # Choose coef on M so that NIE = 2 * coef_m = nie_true → coef_m = nie_true / 2
    y = nde_true * x + (nie_true / 2.0) * m + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


# ============================================ acceptance


def test_linear_mediation_recovers_nde_and_nie():
    df = _linear_med_dgp(n=2000, seed=0, nde_true=0.5, nie_true=2.0)
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=100, random_state=42,
    )
    assert est.method == "mediation_linear_imai"
    # Point estimates within 10% of truth
    assert abs(est.nde_point - 0.5) < 0.15
    assert abs(est.nie_point - 2.0) < 0.2
    # TE = NDE + NIE ≈ 2.5
    assert abs(est.te_point - 2.5) < 0.2


def test_te_equals_nde_plus_nie_up_to_sampling_noise():
    df = _linear_med_dgp(n=1000, seed=0)
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=50, random_state=42,
    )
    assert abs(est.te_point - (est.nde_point + est.nie_point)) < 0.10


def test_ci_bounds_present_and_ordered():
    df = _linear_med_dgp(n=800, seed=0)
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=50, random_state=1,
    )
    assert est.nde_ci_lower <= est.nde_point <= est.nde_ci_upper
    assert est.nie_ci_lower <= est.nie_point <= est.nie_ci_upper
    assert est.te_ci_lower <= est.te_point <= est.te_ci_upper


# ============================================ logit path


def test_logit_outcome_uses_logit_model():
    rng = np.random.default_rng(0)
    n = 2000
    x = rng.binomial(1, 0.5, n)
    m = 2.0 * x + rng.standard_normal(n)
    y_logit = 0.3 * x + 0.5 * m - 1.0
    y = rng.random(n) < (1 / (1 + np.exp(-y_logit)))
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=50, random_state=42,
    )
    assert est.method == "mediation_logit_imai"
    # NIE direction should be positive (M increases Y via positive logit)
    assert est.nie_point > 0


def test_bool_mediator_accepted():
    """Bool mediator goes through Logit first-stage."""
    rng = np.random.default_rng(0)
    n = 1000
    x = rng.binomial(1, 0.5, n)
    m = rng.random(n) < (1 / (1 + np.exp(-(2.0 * x - 1))))
    y = 0.5 * x + 1.5 * m.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=50, random_state=42,
    )
    # NIE should be positive (x→m→y is positive via positive coefs)
    assert est.nie_point > 0


# ============================================ adjustment


def test_adjustment_set_threaded_into_both_models():
    """Include a confounder that needs to be in the adjustment set."""
    rng = np.random.default_rng(0)
    n = 2000
    w = rng.standard_normal(n)
    # Treatment depends on W (observed confounder)
    x = rng.random(n) < (1 / (1 + np.exp(-w)))
    m = 2.0 * x.astype(float) + 0.5 * w + rng.standard_normal(n)
    y = 0.5 * x.astype(float) + 1.0 * m + 0.3 * w + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "w": w, "m": m, "y": y})

    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        adjustment=("w",), n_rep=50, random_state=42,
    )
    assert est.adjustment == ("w",)
    # True NIE = 2 * 1 = 2.0
    assert abs(est.nie_point - 2.0) < 0.3


# ============================================ determinism + shape


def test_deterministic_under_fixed_seed():
    df = _linear_med_dgp(n=500, seed=0)
    e1 = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=30, random_state=42,
    )
    e2 = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=30, random_state=42,
    )
    assert e1.nde_point == e2.nde_point
    assert e1.nie_point == e2.nie_point
    assert e1.te_point == e2.te_point
    assert e1.data_hash == e2.data_hash


def test_shape_and_fields():
    df = _linear_med_dgp(n=200, seed=0)
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=30, random_state=42,
    )
    assert isinstance(est, MediationEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.mediator == "m"
    assert est.n_rep == 30
    assert len(est.data_hash) == 64


# ============================================ error path


def test_unknown_model_rejected():
    df = _linear_med_dgp(n=100, seed=0)
    with pytest.raises(ValueError, match="unknown model"):
        estimate_mediation(
            df, treatment="x", outcome="y", mediator="m",
            model="random_forest", n_rep=10,
        )
