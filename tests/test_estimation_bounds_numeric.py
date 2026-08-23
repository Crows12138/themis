"""Unit tests for the partial-identification numeric end (bounds_numeric).

The Balke-Pearl path is validated four independent ways:
  1. the published Vitamin-A worked example (Balke-Pearl 1997 Table 2 →
     −0.1946 ≤ ACE ≤ 0.0054);
  2. an INDEPENDENT re-implementation of the closed-form eqs (4)/(5) here in
     the test, compared against the module's response-function LP;
  3. a known-truth SCM whose true ACE must lie inside the bounds;
  4. at cardinalities the closed form does not cover, an independently
     enumerated response-type LP written here in the test.

(1)-(3) are all about the ACE, which is what this method used to bound. It
now bounds the ARM the query names — the ACE moved to ``contrast``, where it
is still checked against the same published numbers — because the ACE is a
probability difference between two arms and neither survives a treatment or
outcome with more than two levels, which is the whole of what (4) is for.
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from themis.estimation.bounds_numeric import (
    NumericBounds,
    evaluate_balke_pearl_bounds,
    evaluate_manski_natural_bounds,
    evaluate_manski_tamer_bounds,
)
from themis.response_polytope import _contrast_objective, _solve_response_lp
from themis.output.bounds import MAX_RESPONSE_TYPES
from themis.refusals import EstimatorFailure


def _bp_ace_bounds_from_P(P):
    """The ACE range over the binary response-function polytope — the
    quantity this module's LP used to expose directly."""
    return _solve_response_lp(P, 2, 2, 2, _contrast_objective(2, 2, 2, 1, 1, 0))


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
def _bp(df, **kw):
    kw.setdefault("treatment_value", True)
    kw.setdefault("outcome_value", True)
    kw.setdefault("ci_bootstrap", 0)
    return evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z", **kw)


def test_balke_pearl_vitamin_a_matches_published():
    """The published ACE interval, now reported as the contrast it is.

    Same two numbers, in the field that says which quantity they are about.
    lower_value / upper_value hold the arm the query asked for, which is a
    probability and cannot be −0.1946.
    """
    df = _exact_iv_frame(_VIT_A)
    nb = _bp(df)
    assert nb.method == "balke_pearl_iv"
    assert nb.estimand == "arm_probability"
    assert nb.instrument == "z"
    assert nb.contrast["kind"] == "ace"
    assert nb.contrast["lower_value"] == pytest.approx(-0.1946, abs=1e-3)
    assert nb.contrast["upper_value"] == pytest.approx(0.0054, abs=1e-3)
    assert nb.contrast["reference_value"] is False
    assert 0.0 <= nb.lower_value <= nb.upper_value <= 1.0


def test_the_arm_and_the_contrast_are_different_questions():
    """Two intervals, two quantities — the published −0.1946/0.0054 is not
    an interval the arm's endpoints could be mistaken for."""
    df = _exact_iv_frame(_VIT_A)
    nb = _bp(df)
    assert nb.lower_value >= 0.0                      # a probability
    assert nb.contrast["lower_value"] < 0.0           # a difference
    assert nb.contrast["lower_value"] != pytest.approx(nb.lower_value)


def test_the_contrast_sits_inside_the_difference_of_the_two_arm_bounds():
    """The relation that IS a theorem, in the direction it holds.

    ACE = arm(x=1) − arm(x=0), so it lies inside the interval-arithmetic
    difference of the two arms' own bounds. It is computed as its own
    optimisation rather than by that subtraction — and measurement is why
    the docstrings do not claim more: on this model the two coincide on
    every table tried, so what the second LP buys is not needing to know
    that in advance.
    """
    for frame in (_exact_iv_frame(_VIT_A), _exact_iv_frame(_p_from_q(_Q_WORKED))):
        hi_arm = _bp(frame, treatment_value=True)
        lo_arm = _bp(frame, treatment_value=False)
        naive = (hi_arm.lower_value - lo_arm.upper_value,
                 hi_arm.upper_value - lo_arm.lower_value)
        c = hi_arm.contrast
        assert naive[0] - 1e-9 <= c["lower_value"]
        assert c["upper_value"] <= naive[1] + 1e-9


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
    nb = _bp(df)
    assert nb.contrast["lower_value"] == pytest.approx(0.60, abs=1e-9)
    assert nb.contrast["upper_value"] == pytest.approx(1.00, abs=1e-9)
    # true ACE (0.60) sits on the lower boundary
    lo, hi = nb.contrast["lower_value"], nb.contrast["upper_value"]
    assert lo - 1e-9 <= _true_ace(_Q_WORKED) <= hi + 1e-9


def test_balke_pearl_contains_true_ace_on_random_scms():
    rng = np.random.default_rng(2)
    for k in range(40):
        q = rng.dirichlet(np.ones(16))
        df = _sample_iv(q, 8000, seed=100 + k)
        try:
            nb = _bp(df)
        except EstimatorFailure:
            continue  # sampling pushed the table just outside the IV model
        lo, hi = nb.contrast["lower_value"], nb.contrast["upper_value"]
        assert lo - 0.04 <= _true_ace(q) <= hi + 0.04


def test_balke_pearl_contains_the_true_arm_on_random_scms():
    """The estimand that is actually reported, held to the same standard."""
    rng = np.random.default_rng(3)
    for k in range(40):
        q = rng.dirichlet(np.ones(16))
        true_arm = float(sum(
            q[i * 4 + j] for i in range(4) for j in range(4) if _gy(j, 1) == 1))
        df = _sample_iv(q, 8000, seed=200 + k)
        try:
            nb = _bp(df)
        except EstimatorFailure:
            continue
        assert nb.lower_value - 0.04 <= true_arm <= nb.upper_value + 0.04


def test_balke_pearl_tighter_than_manski_natural_on_the_same_arm():
    """The comparison that means something.

    The two methods used to bound different quantities, so 'tighter' was a
    comparison between an ACE interval and an arm interval — not a
    comparison at all. Both bound the arm now, and the instrument's
    contribution is the difference between the two widths.
    """
    df = _exact_iv_frame(_p_from_q(_Q_WORKED))
    bp = _bp(df)
    mn = evaluate_manski_natural_bounds(
        df, treatment="x", outcome="y",
        treatment_value=True, outcome_value=True, ci_bootstrap=0)
    assert bp.estimand == mn.estimand == "arm_probability"
    assert bp.lower_value >= mn.lower_value - 1e-9
    assert bp.upper_value <= mn.upper_value + 1e-9
    assert bp.width < mn.width


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
    # The witness, not a phrase: which treatment level the inequality is
    # violated at and by how much. A refusal that cites Pearl 1995 has to
    # carry the number that citation is about.
    assert ei.value.details["level_index"] == 0
    assert ei.value.details["statistic"] > 1.0
    assert ei.value.recorded["levels"] == [2, 2, 2]


# ------------------------------------------------- past the binary case
#
# The three tests this block replaces asserted that a three-level x, y or z
# makes this estimator refuse. Two of the three cardinalities were never
# anything to the method; the third (the treatment) only changes how many
# response types there are.


def _reference_lp(P, nx, ny, nz, xi, yi):
    """The response-function LP, enumerated from scratch here, for the
    cardinalities the published closed form does not cover."""
    from scipy.optimize import linprog

    fxs = list(itertools.product(range(nx), repeat=nz))
    gys = list(itertools.product(range(ny), repeat=nx))
    nt = len(fxs) * len(gys)
    rows, b = [], []
    for z in range(nz):
        for x in range(nx):
            for y in range(ny):
                row = np.zeros(nt)
                for i, f in enumerate(fxs):
                    if f[z] != x:
                        continue
                    for j, g in enumerate(gys):
                        if g[x] == y:
                            row[i * len(gys) + j] = 1.0
                rows.append(row)
                b.append(float(P[z, x, y]))
    rows.append(np.ones(nt))
    b.append(1.0)
    c = np.array([1.0 if g[xi] == yi else 0.0 for _f in fxs for g in gys])
    A, bv = np.asarray(rows), np.asarray(b)
    lo = linprog(c, A_eq=A, b_eq=bv, bounds=[(0.0, None)] * nt, method="highs")
    hi = linprog(-c, A_eq=A, b_eq=bv, bounds=[(0.0, None)] * nt, method="highs")
    assert lo.success and hi.success
    return float(lo.fun), float(-hi.fun)


def _multi_iv_frame(nx, ny, nz, n=30000, seed=11):
    """Latent-confounded IV data at arbitrary cardinality."""
    rng = np.random.default_rng(seed)
    U = rng.integers(0, 2, n)
    Z = rng.integers(0, nz, n)
    X = np.clip(np.rint(
        Z * (nx - 1) / max(nz - 1, 1) + 0.8 * U + rng.normal(0, 0.5, n)),
        0, nx - 1).astype(int)
    Y = np.clip(np.rint(
        0.9 * X + 1.1 * U + rng.normal(0, 0.6, n)), 0, ny - 1).astype(int)
    frame = pd.DataFrame({"x": X, "y": Y, "z": Z})
    for col, k in (("x", nx), ("y", ny), ("z", nz)):
        if k == 2:
            frame[col] = frame[col].astype(bool)
    return frame


@pytest.mark.parametrize("nx,ny,nz,xv,yv", [
    (3, 2, 2, 2, True),      # multi-valued TREATMENT
    (2, 3, 2, True, 2),      # multi-valued OUTCOME
    (2, 2, 3, True, True),   # multi-valued INSTRUMENT
    (3, 3, 3, 2, 2),         # all three
])
def test_the_arm_bound_matches_an_independently_enumerated_lp(nx, ny, nz, xv, yv):
    from themis.estimation.bounds_numeric import _empirical_P_xyz, sorted_levels

    df = _multi_iv_frame(nx, ny, nz)
    nb = evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z",
        treatment_value=xv, outcome_value=yv, ci_bootstrap=0)
    assert nb.estimand == "arm_probability"
    xl = sorted_levels(df["x"])
    yl = sorted_levels(df["y"])
    zl = sorted_levels(df["z"])
    P = _empirical_P_xyz(df, "x", "y", "z", xl, yl, zl)
    lo, hi = _reference_lp(P, nx, ny, nz, xl.index(xv), yl.index(yv))
    assert nb.lower_value == pytest.approx(lo, abs=1e-9)
    assert nb.upper_value == pytest.approx(hi, abs=1e-9)


def test_a_multi_valued_treatment_reports_no_ace():
    """There is no baseline arm to be against, so there is no ACE — and
    inventing one would be this estimator answering a question the query
    did not ask."""
    df = _multi_iv_frame(3, 2, 2)
    nb = evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z",
        treatment_value=2, outcome_value=True, ci_bootstrap=0)
    assert nb.contrast is None


#: A table with three instrument levels that no response-type distribution
#: reproduces, and that violates no instrumental inequality. Counts per
#: ``z``, in the cell order ``(x=0,y=0), (x=0,y=1), (x=1,y=0), (x=1,y=1)``.
_EMPTY_BUT_UNWITNESSED = {0: (0, 0, 1, 3), 1: (0, 1, 0, 3), 2: (1, 0, 0, 3)}


def _table_frame(counts: dict, repeat: int = 100) -> pd.DataFrame:
    """An exact sample from a P(x,y|z) table given as integer cell counts."""
    rows = []
    for z, cells in counts.items():
        for (x, y), k in zip([(0, 0), (0, 1), (1, 0), (1, 1)], cells):
            rows += [{"z": z, "x": bool(x), "y": bool(y)}] * (k * repeat)
    return pd.DataFrame(rows)


def test_an_empty_polytope_with_no_violated_inequality_says_so():
    """The refusal that cannot cite Pearl 1995, and why one is needed.

    Pearl's instrumental inequality is necessary at every cardinality and
    SUFFICIENT only for a binary instrument (Balke-Pearl 1997 eq 6). Past
    that, a table can satisfy it and still lie outside the model, and the
    refusal that names it would be offering a citation that does not exist.

    ``_EMPTY_BUT_UNWITNESSED`` is such a table, and it can be checked by
    hand. Under every ``z``, three quarters of the units are (X=1, Y=1); the
    remaining quarter is (X=1, Y=0) at z=0, (X=0, Y=1) at z=1, and
    (X=0, Y=0) at z=2. The inequality sums to 1/2 at x=0 and to exactly 1 at
    x=1, so nothing is violated. The contradiction is elsewhere:

    * P(X=1 | z=0) = 1, so every unit has X(z=0) = 1 and its Y at z=0 is
      Y(1). The z=0 column therefore reads the whole population's Y(1)
      response: a quarter of it has Y(1) = 0.
    * At z=1 nobody has (X=1, Y=0), so every unit with Y(1) = 0 has
      X(z=1) = 0 — and P(X=0 | z=1) is exactly a quarter, so those two
      groups are the same quarter. Their Y at z=1 is Y(0), and the column
      puts all of it on Y=1. That quarter has Y(0) = 1.
    * At z=2 the same argument makes the units with X(z=2) = 0 that same
      quarter — and the column puts all of THEIR Y on 0. That quarter has
      Y(0) = 0.

    One quarter of the population, two answers. No distribution over
    response types reproduces the table, and no named inequality says so.
    """
    with pytest.raises(EstimatorFailure) as ei:
        evaluate_balke_pearl_bounds(
            _table_frame(_EMPTY_BUT_UNWITNESSED),
            treatment="x", outcome="y", instrument="z",
            treatment_value=True, outcome_value=True, ci_bootstrap=0)
    assert ei.value.failure_type == "iv_model_infeasible"
    assert ei.value.details == {"nx": 2, "ny": 2, "nz": 3}


def test_the_same_table_violates_no_instrumental_inequality():
    """The premise of the test above, measured rather than asserted.

    Without it, a build whose inequality check had silently stopped finding
    witnesses would pass that test while refusing every refuted table under
    the wrong name.
    """
    from themis.response_polytope import _instrumental_inequality_violation

    P = np.array([_EMPTY_BUT_UNWITNESSED[z] for z in (0, 1, 2)],
                 dtype=float).reshape(3, 2, 2) / 4
    assert _instrumental_inequality_violation(P, 2, 2, 3) is None
    assert [sum(P[:, x, y].max() for y in (0, 1)) for x in (0, 1)] == [0.5, 1.0]


def test_a_multi_valued_outcome_still_reports_the_ace():
    """The ACE needs a binary TREATMENT (for the baseline arm), not a
    binary outcome: with three outcome levels the contrast is still the
    difference of two probabilities of the same event."""
    df = _multi_iv_frame(2, 3, 2)
    nb = evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z",
        treatment_value=True, outcome_value=2, ci_bootstrap=0)
    assert nb.contrast is not None
    assert -1.0 <= nb.contrast["lower_value"] <= nb.contrast["upper_value"] <= 1.0


def test_the_instrument_is_worth_something_at_every_cardinality():
    """What the binary gate was costing: at each of these shapes the query
    used to fall to the no-instrument Manski floor."""
    for nx, ny, nz, xv, yv in [(3, 2, 2, 2, True), (2, 3, 2, True, 2),
                               (2, 2, 3, True, True)]:
        df = _multi_iv_frame(nx, ny, nz)
        bp = evaluate_balke_pearl_bounds(
            df, treatment="x", outcome="y", instrument="z",
            treatment_value=xv, outcome_value=yv, ci_bootstrap=0)
        mn = evaluate_manski_natural_bounds(
            df, treatment="x", outcome="y",
            treatment_value=xv, outcome_value=yv, ci_bootstrap=0)
        assert bp.width < mn.width, (nx, ny, nz)


def test_records_the_levels_its_table_is_indexed_by():
    df = _multi_iv_frame(3, 2, 2)
    nb = evaluate_balke_pearl_bounds(
        df, treatment="x", outcome="y", instrument="z",
        treatment_value=2, outcome_value=True, ci_bootstrap=0)
    stats = nb.sufficient_statistics
    assert stats["treatment_levels"] == [0, 1, 2]
    assert stats["instrument_levels"] == [False, True]
    assert stats["arm_treatment_index"] == 2
    assert np.asarray(stats["P_xyz"]).shape == (2, 3, 2)


def test_refuses_a_model_larger_than_the_lp_is_run_at():
    df = _multi_iv_frame(5, 5, 2, n=40000)
    with pytest.raises(EstimatorFailure) as ei:
        evaluate_balke_pearl_bounds(
            df, treatment="x", outcome="y", instrument="z",
            treatment_value=2, outcome_value=2, ci_bootstrap=0)
    assert ei.value.failure_type == "response_model_too_large"
    # The refusal names the arithmetic, not just the verdict.
    assert "5^2" in str(ei.value) and str(MAX_RESPONSE_TYPES) in str(ei.value)


def test_refuses_a_continuous_column_without_trying_to_count_its_types():
    """The shape a continuous outcome actually arrives in: thousands of
    observed levels, whose |Y|^|X| the size law must decline to evaluate
    rather than overflow on."""
    rng = np.random.default_rng(31)
    n = 4000
    df = pd.DataFrame({
        "z": rng.integers(0, 2, n).astype(bool),
        "x": rng.integers(0, 2, n).astype(bool),
        "y": rng.normal(size=n),
    })
    with pytest.raises(EstimatorFailure) as ei:
        evaluate_balke_pearl_bounds(
            df, treatment="x", outcome="y", instrument="z",
            treatment_value=True, outcome_value=float(df.y.iloc[0]),
            ci_bootstrap=0)
    assert ei.value.failure_type == "response_model_too_large"


def test_refuses_an_arm_the_data_never_shows():
    df = _multi_iv_frame(3, 2, 2)
    with pytest.raises(EstimatorFailure) as ei:
        evaluate_balke_pearl_bounds(
            df, treatment="x", outcome="y", instrument="z",
            treatment_value=7, outcome_value=True, ci_bootstrap=0)
    assert ei.value.failure_type == "target_value_absent"


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
        outcome_levels=[False, True],
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
        outcome_levels=[False, True],
        treatment_value=True, outcome_value=True, ci_bootstrap=0)
    assert mt.upper_value <= nat.upper_value + 1e-9
    assert mt.lower_value == pytest.approx(nat.lower_value, abs=1e-9)


def test_manski_tamer_invalid_direction_raises():
    df, _ = _confounded_frame(seed=3)
    with pytest.raises(EstimatorFailure):
        evaluate_manski_tamer_bounds(
            df, treatment="x", outcome="y", monotonicity="sideways",
            outcome_levels=[False, True], ci_bootstrap=0)


# =========================================================== CI / determinism
def test_ci_outer_band_encloses_interval():
    df = _sample_iv(_Q_WORKED, 8000, seed=7)
    nb = _bp(df, ci_bootstrap=100, random_state=42)
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
