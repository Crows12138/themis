"""Phase 7.4 S.MN.1 — unit tests for the mediation numeric estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import refusals
from themis.refusals import Refusal
from themis.refusals import EstimatorFailure

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


def test_exposure_mediator_interaction_recovers_correct_nde_nie():
    """Regression: with an exposure-mediator interaction the natural-effect
    decomposition must carry the θ3 terms (VanderWeele 2015 §2.2), not collapse
    to the biased Baron-Kenny estimates. DGP: M = X + noise; Y = 0.5·X + 0.5·M
    + 2·X·M + noise → true NDE = θ1 + θ3·β0 = 0.5; true NIE = (θ2+θ3)·β1 = 2.5.
    Before the fix Themis returned NDE≈1.5 / NIE≈1.5 (omitting the interaction).
    """
    rng = np.random.default_rng(0)
    n = 20000
    x = rng.integers(0, 2, n).astype(float)
    m = 1.0 * x + rng.standard_normal(n) * 0.5
    y = 0.5 * x + 0.5 * m + 2.0 * x * m + rng.standard_normal(n) * 0.5
    df = pd.DataFrame({"x": x, "m": m, "y": y})
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m", n_rep=40, random_state=1,
    )
    assert abs(est.nde_point - 0.5) < 0.1, est.nde_point   # not the biased ~1.5
    assert abs(est.nie_point - 2.5) < 0.1, est.nie_point   # not the biased ~1.5
    assert abs(est.te_point - 3.0) < 0.1, est.te_point


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


def test_proportion_mediated_present_and_consistent_with_ratio():
    """Real test caught: 'X 占多少比例' is the user's actual mediation
    question. The estimator now surfaces NIE / TE as
    ``proportion_mediated`` (Imai's bootstrap on the ratio, not
    naive point/point) so the renderer doesn't have to compute it."""
    df = _linear_med_dgp(n=2000, seed=0, nde_true=0.5, nie_true=2.0)
    est = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m",
        n_rep=200, random_state=42,
    )
    # Point should be in the same ballpark as naive ratio (Imai's
    # bootstrap on the ratio uses median of ratio, not ratio of medians)
    naive_ratio = est.nie_point / est.te_point
    assert abs(est.proportion_mediated_point - naive_ratio) < 0.05
    # CI bounds well-ordered
    assert est.proportion_mediated_ci_lower <= est.proportion_mediated_point
    assert est.proportion_mediated_point <= est.proportion_mediated_ci_upper


def test_unknown_model_rejected():
    df = _linear_med_dgp(n=100, seed=0)
    with pytest.raises(EstimatorFailure, match="unknown model") as exc:
        estimate_mediation(
            df, treatment="x", outcome="y", mediator="m",
            model="random_forest", n_rep=10,
        )
    assert exc.value.failure_type == Refusal.INVALID_INPUT


def test_a_singular_point_fit_is_refused_not_swallowed():
    """A mediator that is the treatment relabelled leaves ``Y ~ X + M``
    rank-deficient, and statsmodels raises the solver's own
    ``LinAlgError`` — a ``ValueError`` subclass, which dispatch's generic
    guard used to catch and discard along with the reason.

    The bootstrap already tolerates a resample it cannot fit; the point fit
    has no such loop, so its failure is the whole estimate's failure and
    has to say so."""
    rng = np.random.default_rng(0)
    n = 300
    x = rng.random(n) < 0.5
    df = pd.DataFrame({"x": x, "m": x, "y": rng.random(n) < 0.5})
    with pytest.raises(EstimatorFailure, match="奇异") as exc:
        estimate_mediation(
            df, treatment="x", outcome="y", mediator="m", n_rep=0,
        )
    assert exc.value.failure_type == Refusal.SINGULAR_DESIGN
