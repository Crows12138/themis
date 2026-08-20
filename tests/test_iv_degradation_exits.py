"""The IV module's degradation exits, and the one route that had none.

Two different things live in ``iv.py``. A refusal raises ``EstimatorFailure``
and reaches the reader as a named species. A degradation returns ``None`` and
leaves an optional block off the envelope — which is right when the block is
genuinely undefined, and silent in a way nothing checks. This file executes
the degradation exits, and pins the first-stage guard the just-identified
2SLS route was missing while its three siblings had one.
"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from themis.estimation.dispatch import _attach_weak_iv_warning_if_low_f
from themis.estimation.iv import (
    IVStratum,
    _classify_robust_ar_segments,
    _first_stage_f_stat,
    anderson_rubin_confidence_set,
    anderson_rubin_overid_set,
    estimate_iv_ate,
    robust_anderson_rubin_overid_set,
    solve_overid_from_moments,
    stratified_anderson_rubin_set,
)
from themis.refusals import EstimatorFailure, Refusal

N = 800


def _fixed_xy(seed: int = 2):
    """x and y are built once and reused for every instrument below, so any
    difference in the answer is the instrument's doing and nothing else."""
    rng = np.random.default_rng(seed)
    w = rng.standard_normal(N)
    u = rng.standard_normal(N)
    x = 0.6 * w + u + 0.3 * rng.standard_normal(N)
    y = 2.0 * x + 1.0 * w + u + 0.3 * rng.standard_normal(N)
    return w, x, y, rng


# Each of these carries exactly as much information about x as w does: none
# of its own. Least squares does not mind — it returns the minimum-norm
# solution and the caller gets a number.
NOTHING_LEFT_AFTER_W = {
    "a copy of w": lambda w: w.copy(),
    "w rescaled and shifted": lambda w: 7.0 * w - 1.0,
    "w negated": lambda w: -w,
    "a constant column": lambda w: np.ones_like(w),
}


@pytest.mark.parametrize("shape", sorted(NOTHING_LEFT_AFTER_W))
def test_2sls_refuses_an_instrument_with_nothing_left_after_conditioning(shape):
    w, x, y, _ = _fixed_xy()
    df = pd.DataFrame({"w": w, "z": NOTHING_LEFT_AFTER_W[shape](w),
                       "x": x, "y": y})
    with pytest.raises(EstimatorFailure) as exc:
        estimate_iv_ate(df, treatment="x", outcome="y", instrument="z",
                        conditioning=("w",), ci_bootstrap=0)
    assert exc.value.failure_type == Refusal.NO_FIRST_STAGE
    assert "z" in str(exc.value)


def test_a_weak_instrument_is_not_a_degenerate_one():
    """The counterexample to the guard over-reaching. A weak instrument still
    has to produce its number and the unbounded weak-robust set that says the
    data cannot pin the effect down — that unboundedness is the honest signal
    the guard must not replace with a refusal."""
    w, x, y, rng = _fixed_xy()
    df = pd.DataFrame({"w": w, "z": w + 0.02 * rng.standard_normal(N),
                       "x": x, "y": y})
    est = estimate_iv_ate(df, treatment="x", outcome="y", instrument="z",
                          conditioning=("w",), ci_bootstrap=0)
    assert est.first_stage_f_stat is not None
    assert est.first_stage_f_stat < 10.0
    assert est.anderson_rubin is not None
    assert est.anderson_rubin.kind == "whole_line"


def test_2sls_refuses_an_instrument_orthogonal_to_the_treatment():
    """The other half of the guard. An instrument that varies but explains
    none of the treatment is a different problem for the analyst than one
    with nothing left after W, and the refusal has to say which."""
    reps = N // 4
    z = np.tile([1.0, -1.0, 1.0, -1.0], reps)
    x = np.tile([1.0, 1.0, -1.0, -1.0], reps)
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"z": z, "x": x, "y": 2.0 * x + rng.standard_normal(N)})
    assert float(np.dot(z - z.mean(), x - x.mean())) == 0.0
    with pytest.raises(EstimatorFailure) as exc:
        estimate_iv_ate(df, treatment="x", outcome="y", instrument="z",
                        ci_bootstrap=0, model="2sls")
    assert exc.value.failure_type == Refusal.NO_FIRST_STAGE
    assert "x'P_Z x" in str(exc.value)


def test_the_marginal_wald_refuses_a_one_armed_instrument():
    """``abs(nan) < 1e-12`` is False, so an instrument with one empty arm went
    through the denominator guard written for exactly this case."""
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "z": np.zeros(N, dtype=bool),
        "x": rng.random(N) < 0.5,
        "y": rng.random(N) < 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_iv_ate(df, treatment="x", outcome="y", instrument="z",
                        ci_bootstrap=0)
    assert exc.value.failure_type == Refusal.OVERLAP_INSUFFICIENT


def test_the_weak_iv_gap_does_not_point_at_a_set_the_envelope_lacks():
    """When the weak-robust set is None it could not be formed from this
    sample. Sending the reader to read it off the result is an instruction
    with nothing behind it — the same shape as telling a renderer to quote a
    caveat the estimate has already withdrawn."""
    est = SimpleNamespace(
        first_stage_f_stat=0.4, anderson_rubin=None,
        stratified_anderson_rubin=None,
        instrument="z", treatment="x",
    )
    result: dict = {}
    _attach_weak_iv_warning_if_low_f(result, est)
    gap = result["data_gap_report"]["gaps"][0]
    assert gap["kind"] == "weak_iv_instrument"
    paths = " | ".join(gap["alternative_paths"])
    assert "这份样本不足以构造出来" in paths
    assert "report the Anderson-Rubin confidence set" not in paths


# ------------------------------------------------- the degradation exits


def _stratum(**over) -> IVStratum:
    base = dict(
        values=(True,), weight=1.0, n_obs=100,
        n_instrument_high=50, n_instrument_low=50,
        outcome_shift=1.0, treatment_shift=0.5,
        shift_var_yy=0.01, shift_var_xy=0.001, shift_var_xx=0.01,
    )
    base.update(over)
    return IVStratum(**base)


def test_the_stratified_set_declines_an_empty_table():
    assert stratified_anderson_rubin_set((), n_obs=100) is None


def test_the_stratified_set_declines_when_no_residual_df_is_left():
    """dof = n_obs - 2s: one stratum costs two parameters, so a table with as
    many strata as pairs of rows has no df left to invert a test against."""
    assert stratified_anderson_rubin_set((_stratum(),), n_obs=2) is None


def test_the_stratified_set_declines_a_table_with_no_sampling_variation():
    """Zero recorded variance everywhere is not a tight set — there is no
    test to invert, and returning one would dress a point as a set."""
    flat = _stratum(shift_var_yy=0.0, shift_var_xy=0.0, shift_var_xx=0.0)
    assert stratified_anderson_rubin_set((flat,), n_obs=100) is None


def test_the_stratified_set_does_answer_when_the_table_supports_it():
    """Without this, the three tests above pass against a function that
    returns None unconditionally."""
    got = stratified_anderson_rubin_set((_stratum(),), n_obs=100)
    assert got is not None
    assert got.n_strata == 1


def test_the_linear_set_declines_when_residual_df_is_below_one():
    df = pd.DataFrame({"w": [0.0, 1.0, 2.0], "z": [1.0, 0.0, 1.0],
                       "x": [0.5, 1.5, 2.5], "y": [1.0, 2.0, 4.0]})
    assert anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z", conditioning=("w",),
    ) is None


def _moments(q: int = 2, n: int = 400, *, zz, zx, zy) -> dict:
    return {
        "zz": np.asarray(zz, dtype=float).tolist(),
        "zx": np.asarray(zx, dtype=float).tolist(),
        "zy": np.asarray(zy, dtype=float).tolist(),
        "xx": 100.0, "xy": 80.0, "yy": 120.0,
        "n": n, "n_exog": 0, "q": q,
    }


def test_the_overid_set_declines_when_residual_df_is_below_one():
    m = _moments(n=3, zz=np.eye(2), zx=[1.0, 1.0], zy=[1.0, 1.0])
    assert anderson_rubin_overid_set(m) is None


def test_the_overid_set_declines_collinear_instruments():
    """Z'Z singular: the two instruments are one instrument written twice,
    so the projection the set inverts does not exist."""
    m = _moments(zz=[[1.0, 1.0], [1.0, 1.0]], zx=[1.0, 1.0], zy=[1.0, 1.0])
    assert anderson_rubin_overid_set(m) is None


def _robust_moments(**over) -> dict:
    m = _moments(zz=np.eye(2) * 100.0, zx=[10.0, 5.0], zy=[8.0, 4.0])
    m["s0"] = (np.eye(2) * 4.0).tolist()
    m["s1"] = (np.eye(2) * 1.0).tolist()
    m["s2"] = (np.eye(2) * 0.5).tolist()
    m.update(over)
    return m


def test_the_robust_set_declines_collinear_instruments():
    m = _robust_moments(zz=[[1.0, 1.0], [1.0, 1.0]])
    assert robust_anderson_rubin_overid_set(m) is None


def test_the_robust_set_declines_a_first_stage_of_exactly_zero():
    m = _robust_moments(zx=[0.0, 0.0])
    assert robust_anderson_rubin_overid_set(m) is None


def test_the_robust_set_does_answer_on_moments_that_support_it():
    """Same reason as the stratified twin: pin that the two Nones above are
    the guards firing, not the function declining everything."""
    assert robust_anderson_rubin_overid_set(_robust_moments()) is not None


def test_the_f_statistic_declines_a_first_stage_that_fits_exactly():
    """A treatment that is an exact linear function of the instrument leaves
    no residual sum of squares to divide by."""
    z = np.arange(50, dtype=float)
    df = pd.DataFrame({"z": z, "x": 2.0 * z + 3.0, "y": z * 0.5})
    assert _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    ) is None


def test_the_f_statistic_declines_a_sample_with_no_residual_df():
    df = pd.DataFrame({"z": [0.0, 1.0, 2.0], "w": [1.0, 0.0, 1.0],
                       "x": [0.5, 1.5, 2.0]})
    assert _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=("w",),
    ) is None


# Two exits the estimator now stands in front of: reachable through the
# public function, unreachable through estimate_iv_ate, because the
# first-stage guard refuses the same samples earlier and with a species
# attached. They stay as guards on the direct callers, and these tests say
# which door is still open.


def test_the_f_statistic_declines_a_motionless_instrument():
    z = np.full(50, 3.0)
    df = pd.DataFrame({"z": z, "x": np.arange(50, dtype=float)})
    assert _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    ) is None


def test_the_linear_set_declines_a_motionless_instrument():
    n = 50
    df = pd.DataFrame({
        "z": np.full(n, 3.0),
        "x": np.arange(n, dtype=float),
        "y": np.arange(n, dtype=float) * 0.5,
    })
    assert anderson_rubin_confidence_set(
        df, treatment="x", outcome="y", instrument="z",
    ) is None


def test_the_estimator_refuses_before_either_of_them_is_asked():
    """The premise of the two tests above — otherwise they read as coverage
    of a path a caller can still fall down."""
    n = 50
    df = pd.DataFrame({
        "z": np.full(n, 3.0),
        "x": np.arange(n, dtype=float),
        "y": np.arange(n, dtype=float) * 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_iv_ate(df, treatment="x", outcome="y", instrument="z",
                        ci_bootstrap=0)
    assert exc.value.failure_type == Refusal.NO_FIRST_STAGE


def test_the_robust_set_declines_when_the_weight_matrices_are_singular():
    """S(β0) = S0 − β0·S1 + β0²·S2 singular for every β0: neither the tail
    asymptote nor the statistic at the point can be formed, and both of those
    are separate exits."""
    zero = np.zeros((2, 2)).tolist()
    m = _robust_moments(s0=zero, s1=zero, s2=zero)
    assert robust_anderson_rubin_overid_set(m) is None


def test_the_joint_f_is_dropped_when_the_first_stage_fits_exactly():
    """SSR_full = xx − x'P_Z x. Instruments that explain all of the treatment
    leave nothing to divide by, so the joint F — and with it the over-
    identified route's weak-instrument disclosure — is simply absent."""
    m = _moments(zz=(np.eye(2) * 4.0), zx=[4.0, 0.0], zy=[3.0, 1.0])
    m["xx"] = 4.0          # xx == x'P_Z x = 16/4 = 4  ->  SSR_full = 0
    m["xy"] = 3.0
    m["yy"] = 12.0
    solved = solve_overid_from_moments(m)
    assert solved["joint_f"] is None
    assert solved["beta"] == pytest.approx(0.75)


# The robust set's own shape vocabulary. Six labels, and a real run only
# ever produced two of them.

SHAPES = [
    ([], "empty"),
    ([(None, None)], "whole_line"),
    ([(None, 1.0)], "unbounded_below"),
    ([(1.0, None)], "unbounded_above"),
    ([(-1.0, 1.0)], "bounded"),
    ([(None, -1.0), (1.0, None)], "disconnected"),
    ([(-3.0, -1.0), (1.0, 3.0)], "union"),
]


@pytest.mark.parametrize("segments,label", SHAPES)
def test_the_robust_set_names_every_shape_it_can_take(segments, label):
    assert _classify_robust_ar_segments(segments) == label
