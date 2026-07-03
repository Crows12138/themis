"""Unit tests for the partial-identification numeric end (bounds_numeric).

The Balke-Pearl path is validated three independent ways:
  1. the published Vitamin-A worked example (Balke-Pearl 1997 Table 2 →
     −0.1946 ≤ ACE ≤ 0.0054);
  2. an INDEPENDENT re-implementation of the closed-form eqs (4)/(5) here in
     the test, compared against the module's response-function LP;
  3. a known-truth SCM whose true ACE must lie inside the bounds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.bounds_numeric import (
    NumericBounds,
    _bp_ace_bounds_from_P,
    evaluate_balke_pearl_ace_bounds,
    evaluate_manski_natural_bounds,
    evaluate_manski_tamer_bounds,
)
from themis.estimation.dose_response import EstimatorFailure


# --------------------------------------------------------------------------
# helpers: build binary-IV data from a response-type distribution q (len 16)
# --------------------------------------------------------------------------
def _fx(i, z):
    return (0, z, 1 - z, 1)[i]


def _gy(j, x):
    return (0, x, 1 - x, 1)[j]


def _sample_iv(q, n, seed):
    rng = np.random.default_rng(seed)
    types = rng.choice(16, size=n, p=q)
    Z = rng.integers(0, 2, n)
    X = np.array([_fx(t // 4, z) for t, z in zip(types, Z)])
    Y = np.array([_gy(t % 4, x) for t, x in zip(types, X)])
    return pd.DataFrame(
        {"x": X.astype(bool), "y": Y.astype(bool), "z": Z.astype(bool)}
    )


def _true_ace(q):
    return float(sum(q[i * 4 + j] * (_gy(j, 1) - _gy(j, 0))
                     for i in range(4) for j in range(4)))


def _exact_iv_frame(P_yxz, per_stratum=100_000):
    """Exact DataFrame reproducing P_yxz[y][x][z] = P(Y=y, X=x | Z=z)."""
    frames = []
    for z in (0, 1):
        for x in (0, 1):
            for y in (0, 1):
                k = int(round(P_yxz[y][x][z] * per_stratum))
                if k:
                    frames.append(pd.DataFrame({
                        "z": [bool(z)] * k, "x": [bool(x)] * k,
                        "y": [bool(y)] * k}))
    return pd.concat(frames, ignore_index=True)


def _closed_form_bounds(p):
    """INDEPENDENT re-implementation of Balke-Pearl 1997 eqs (4)/(5).
    p[y][x][z] = P(Y=y, X=x | Z=z)."""
    def P(y, x, z):
        return p[y][x][z]
    L = [
        P(0, 0, 0) + P(1, 1, 1) - 1,
        P(0, 0, 1) + P(1, 1, 1) - 1,
        P(1, 1, 0) + P(0, 0, 1) - 1,
        P(0, 0, 0) + P(1, 1, 0) - 1,
        2 * P(0, 0, 0) + P(1, 1, 0) + P(1, 0, 1) + P(1, 1, 1) - 2,
        P(0, 0, 0) + 2 * P(1, 1, 0) + P(0, 0, 1) + P(0, 1, 1) - 2,
        P(1, 0, 0) + P(1, 1, 0) + 2 * P(0, 0, 1) + P(1, 1, 1) - 2,
        P(0, 0, 0) + P(0, 1, 0) + P(0, 0, 1) + 2 * P(1, 1, 1) - 2,
    ]
    U = [
        1 - P(1, 0, 0) - P(0, 1, 1),
        1 - P(0, 1, 0) - P(1, 0, 1),
        1 - P(0, 1, 0) - P(1, 0, 0),
        1 - P(0, 1, 1) - P(1, 0, 1),
        2 - 2 * P(0, 1, 0) - P(1, 0, 0) - P(1, 0, 1) - P(1, 1, 1),
        2 - P(0, 1, 0) - 2 * P(1, 0, 0) - P(0, 0, 1) - P(0, 1, 1),
        2 - P(1, 0, 0) - P(1, 1, 0) - 2 * P(0, 1, 1) - P(1, 0, 1),
        2 - P(0, 0, 0) - P(0, 1, 0) - P(0, 1, 1) - 2 * P(1, 0, 1),
    ]
    return max(L), min(U)


def _p_from_q(q):
    p = [[[0.0] * 2 for _ in range(2)] for _ in range(2)]
    for i in range(4):
        for j in range(4):
            for z in (0, 1):
                x = _fx(i, z)
                y = _gy(j, x)
                p[y][x][z] += q[i * 4 + j]
    return p


def _P_array(p):
    P = np.zeros((2, 2, 2))
    for y in (0, 1):
        for x in (0, 1):
            for z in (0, 1):
                P[z, x, y] = p[y][x][z]
    return P


# Vitamin A Table 2 (Balke-Pearl 1997): p[y][x][z]
_VIT_A = [[[0.0064, 0.0028], [0.0000, 0.0010]],
          [[0.9936, 0.1972], [0.0000, 0.7990]]]

# Worked example: 60% compliers Y=X, 20% always-takers (1,1), 20% never (0,0)
_Q_WORKED = np.zeros(16)
_Q_WORKED[1 * 4 + 1] = 0.60
_Q_WORKED[3 * 4 + 3] = 0.20
_Q_WORKED[0 * 4 + 0] = 0.20


# =========================================================== Balke-Pearl
def test_balke_pearl_vitamin_a_matches_published():
    df = _exact_iv_frame(_VIT_A)
    nb = evaluate_balke_pearl_ace_bounds(
        df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0)
    assert nb.method == "balke_pearl_iv"
    assert nb.estimand == "ace"
    assert nb.lower_value == pytest.approx(-0.1946, abs=1e-3)
    assert nb.upper_value == pytest.approx(0.0054, abs=1e-3)
    assert nb.instrument == "z"


def test_lp_equals_closed_form_on_iv_compatible_tables():
    rng = np.random.default_rng(1)
    for _ in range(300):
        q = rng.dirichlet(np.ones(16))
        p = _p_from_q(q)
        Lc, Uc = _closed_form_bounds(p)
        Ll, Ul = _bp_ace_bounds_from_P(_P_array(p))
        assert Ll == pytest.approx(Lc, abs=1e-9)
        assert Ul == pytest.approx(Uc, abs=1e-9)


def test_balke_pearl_worked_example_exact():
    df = _exact_iv_frame(_p_from_q(_Q_WORKED))
    nb = evaluate_balke_pearl_ace_bounds(
        df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0)
    assert nb.lower_value == pytest.approx(0.60, abs=1e-9)
    assert nb.upper_value == pytest.approx(1.00, abs=1e-9)
    # true ACE (0.60) sits on the lower boundary
    assert nb.lower_value - 1e-9 <= _true_ace(_Q_WORKED) <= nb.upper_value + 1e-9


def test_balke_pearl_contains_true_ace_on_random_scms():
    rng = np.random.default_rng(2)
    for k in range(40):
        q = rng.dirichlet(np.ones(16))
        df = _sample_iv(q, 8000, seed=100 + k)
        try:
            nb = evaluate_balke_pearl_ace_bounds(
                df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0)
        except EstimatorFailure:
            continue  # sampling pushed the table just outside the IV model
        assert nb.lower_value - 0.04 <= _true_ace(q) <= nb.upper_value + 0.04


def test_balke_pearl_tighter_than_manski_natural_on_ace():
    # BP ACE interval width ≤ the no-IV Manski natural ACE width.
    df = _exact_iv_frame(_p_from_q(_Q_WORKED))
    bp = evaluate_balke_pearl_ace_bounds(
        df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0)
    # Manski natural ACE width is always exactly 1; BP here is 0.40.
    assert bp.width < 1.0


def test_balke_pearl_rejects_iv_refuting_table():
    # A table violating an instrumental inequality → honest refusal.
    p_bad = [[[0.9, 0.0], [0.05, 0.5]], [[0.0, 0.9], [0.05, 0.0]]]
    for z in (0, 1):
        s = sum(p_bad[y][x][z] for y in (0, 1) for x in (0, 1))
        for y in (0, 1):
            for x in (0, 1):
                p_bad[y][x][z] /= s
    with pytest.raises(EstimatorFailure) as ei:
        _bp_ace_bounds_from_P(_P_array(p_bad))
    assert ei.value.failure_type == "iv_model_refuted"
    assert "Instrumental inequality" in str(ei.value)


@pytest.mark.parametrize("col", ["x", "y", "z"])
def test_balke_pearl_rejects_nonbinary(col):
    df = _sample_iv(_Q_WORKED, 3000, seed=5)
    rng = np.random.default_rng(9)
    df[col] = rng.integers(0, 3, size=len(df))  # 3 levels
    with pytest.raises(EstimatorFailure):
        evaluate_balke_pearl_ace_bounds(
            df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0)


def test_empirical_P_empty_stratum_raises():
    # Directly exercise the positivity guard (as a bootstrap draw would hit).
    from themis.estimation.bounds_numeric import _empirical_P_xyz
    df = _sample_iv(_Q_WORKED, 2000, seed=6)
    only_true = df[df["z"]]  # z=False stratum now empty
    with pytest.raises(EstimatorFailure) as ei:
        _empirical_P_xyz(only_true, "x", "y", "z",
                         [False, True], [False, True], [False, True])
    assert ei.value.failure_type == "insufficient_support"


# =========================================================== Manski natural
def _confounded_frame(n=60000, seed=0):
    rng = np.random.default_rng(seed)
    U = rng.integers(0, 2, n)
    pX = np.where(U == 1, 0.8, 0.2)
    X = (rng.random(n) < pX).astype(int)
    pY = 0.2 + 0.3 * X + 0.3 * U
    Y = (rng.random(n) < pY).astype(int)
    df = pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool)})
    true_do1 = 0.5 + 0.3 * U.mean()  # E_U[0.2+0.3+0.3U]
    return df, true_do1


def test_manski_natural_contains_truth_and_width_is_p_other_arm():
    df, true_do1 = _confounded_frame(seed=0)
    nb = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y",
        treatment_value=True, outcome_value=True, ci_bootstrap=0)
    assert nb.estimand == "arm_probability"
    assert nb.lower_value - 1e-9 <= true_do1 <= nb.upper_value + 1e-9
    assert 0.0 <= nb.lower_value and nb.upper_value <= 1.0
    p_x0 = float(1 - df["x"].mean())
    assert nb.width == pytest.approx(p_x0, abs=1e-9)


def test_manski_natural_no_assumptions():
    df, _ = _confounded_frame(seed=1)
    nb = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=0)
    assert nb.assumptions == ()


# =========================================================== Manski-Tamer MTR
def test_manski_tamer_tightens_one_side_and_contains_truth():
    df, true_do1 = _confounded_frame(seed=0)  # Y increases in X → MTR holds
    nat = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=0)
    mt = evaluate_manski_tamer_bounds(
        df, treatment="x", outcome="y", monotonicity="non_decreasing",
        treatment_value=True, outcome_value=True, ci_bootstrap=0)
    # do(X=1) + non_decreasing → lower tightens UP to marginal, upper unchanged.
    assert mt.lower_value >= nat.lower_value - 1e-9
    assert mt.upper_value == pytest.approx(nat.upper_value, abs=1e-9)
    assert mt.width < nat.width
    assert mt.lower_value - 1e-9 <= true_do1 <= mt.upper_value + 1e-9
    assert mt.assumptions == ("mtr_non_decreasing",)


def test_manski_tamer_direction_flip_tightens_upper():
    df, _ = _confounded_frame(seed=2)
    # do(X=1) + non_increasing → the UPPER side tightens instead.
    nat = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=0)
    mt = evaluate_manski_tamer_bounds(
        df, treatment="x", outcome="y", monotonicity="non_increasing",
        treatment_value=True, outcome_value=True, ci_bootstrap=0)
    assert mt.upper_value <= nat.upper_value + 1e-9
    assert mt.lower_value == pytest.approx(nat.lower_value, abs=1e-9)


def test_manski_tamer_invalid_direction_raises():
    df, _ = _confounded_frame(seed=3)
    with pytest.raises(EstimatorFailure):
        evaluate_manski_tamer_bounds(
            df, treatment="x", outcome="y", monotonicity="sideways",
            ci_bootstrap=0)


# =========================================================== CI / determinism
def test_ci_outer_band_encloses_interval():
    df = _sample_iv(_Q_WORKED, 8000, seed=7)
    nb = evaluate_balke_pearl_ace_bounds(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=100, random_state=42)
    assert nb.ci_lower is not None and nb.ci_upper is not None
    assert nb.ci_lower <= nb.lower_value + 1e-6
    assert nb.ci_upper >= nb.upper_value - 1e-6
    assert nb.ci_level == 0.95


def test_deterministic_same_seed():
    df, _ = _confounded_frame(seed=4)
    a = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=80, random_state=11)
    b = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=80, random_state=11)
    assert (a.lower_value, a.upper_value, a.ci_lower, a.ci_upper) == \
           (b.lower_value, b.upper_value, b.ci_lower, b.ci_upper)


def test_cluster_bootstrap_runs():
    df, _ = _confounded_frame(n=4000, seed=5)
    df["fam"] = np.repeat(np.arange(2000), 2)  # 2000 clusters of 2
    nb = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=60,
        random_state=1, cluster="fam")
    assert nb.cluster == "fam"
    assert nb.ci_lower is not None


def test_returns_numeric_bounds_dataclass():
    df, _ = _confounded_frame(seed=6)
    nb = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y", ci_bootstrap=0)
    assert isinstance(nb, NumericBounds)
    assert nb.data_hash and len(nb.data_hash) == 64
    assert nb.sample_size == len(df)
