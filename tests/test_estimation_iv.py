"""Phase 7.3 S.IVN.1 — unit tests for the IV ATE estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import refusals
from themis.refusals import EstimatorFailure
from themis.estimation.iv import IVEstimate, estimate_iv_ate


def _binary_iv_dgp(n=2000, seed=0, true_late=1.5):
    """Z → X → Y, U ↔ X,Y latent. Binary Z and X.

    Monotonicity holds by construction (higher Z → higher P(X=1)), so
    Wald recovers LATE.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.random(n) < 0.5  # randomised instrument
    p_x_z1 = 1 / (1 + np.exp(-(2 * z.astype(float) - 1 + u * 0.5)))
    x = rng.random(n) < p_x_z1
    y = true_late * x.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _continuous_iv_dgp(n=2000, seed=0, true_ate=2.0):
    """Continuous Z, binary X, continuous Y."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.standard_normal(n)
    # Treatment assignment depends on Z + latent U (endogeneity)
    x = 0.5 * z + 0.8 * u + rng.standard_normal(n) * 0.2
    y = true_ate * x + 1.5 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"z": z, "x": x, "y": y})


# ============================================ Wald acceptance


def test_wald_recovers_late_on_binary_iv_dgp():
    df = _binary_iv_dgp(n=3000, seed=0, true_late=1.5)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.method == "iv_wald"
    # The true LATE is the effect on compliers; Wald is consistent
    assert abs(est.point - 1.5) < 0.4, (
        f"Wald estimate {est.point} off target 1.5"
    )


def test_wald_assumptions_list_mentions_monotonicity():
    df = _binary_iv_dgp(n=500, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert any("monotonicity" in a for a in est.assumptions)
    assert any("LATE" in a for a in est.assumptions)


def test_wald_raises_when_first_stage_exactly_zero():
    """If X is constant across Z values, Wald's denominator is exactly 0."""
    rng = np.random.default_rng(0)
    n = 500
    # X is constant (all True) → E[X|Z=1] - E[X|Z=0] = 0 exactly
    df = pd.DataFrame({
        "z": rng.random(n) < 0.5,
        "x": np.ones(n, dtype=bool),
        "y": rng.standard_normal(n),
    })
    with pytest.raises(EstimatorFailure, match="first-stage") as exc:
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == refusals.NO_FIRST_STAGE
    assert exc.value.details["denominator"] == 0.0


# ============================================ 2SLS acceptance


def test_2sls_recovers_ate_on_continuous_iv_dgp():
    df = _continuous_iv_dgp(n=3000, seed=0, true_ate=2.0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert abs(est.point - 2.0) < 0.3, (
        f"2SLS estimate {est.point} off target 2.0"
    )


def test_2sls_with_conditioning_set():
    """Include a conditioning variable W that shifts both Z's effect on X
    and Z's backdoor to Y. 2SLS with W as conditioning set should still
    recover the true ATE."""
    rng = np.random.default_rng(1)
    n = 3000
    w = rng.standard_normal(n)
    u = rng.standard_normal(n)
    z = 0.5 * w + rng.standard_normal(n)
    x = 0.5 * z + 0.3 * w + 0.8 * u + rng.standard_normal(n) * 0.2
    true_ate = 1.5
    y = true_ate * x + 0.4 * w + 1.5 * u + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"z": z, "w": w, "x": x, "y": y})

    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert est.conditioning == ("w",)
    assert abs(est.point - 1.5) < 0.3


# ============================================ auto model selection


def test_auto_selects_wald_for_binary_binary_unconditional():
    df = _binary_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "iv_wald"


def test_auto_selects_2sls_for_continuous():
    df = _continuous_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0, model="auto",
    )
    assert est.method == "iv_2sls"


def test_auto_selects_2sls_when_conditioning_is_continuous():
    """Binary Z/X with a CONTINUOUS W: the strata a stratified Wald needs
    would hold about one observation each, so 2SLS is the only estimator
    available — and the fallback says so rather than passing silently."""
    df = _binary_iv_dgp(n=500, seed=0)
    df["w"] = np.random.default_rng(0).standard_normal(500)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert est.stratification_fallback is not None
    assert "continuous" in est.stratification_fallback


# ============================================ restrictions


def test_wald_rejects_continuous_treatment():
    df = _continuous_iv_dgp(n=500, seed=0)
    with pytest.raises(EstimatorFailure, match="binary") as exc:
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            model="wald", ci_bootstrap=0,
        )
    assert exc.value.failure_type == refusals.INVALID_INPUT


def test_wald_rejects_conditioning():
    """The MARGINAL Wald refuses a conditioning set, because ignoring W is
    a different estimand rather than an approximation of the same one."""
    df = _binary_iv_dgp(n=500, seed=0)
    df["w"] = np.random.default_rng(0).standard_normal(500)
    with pytest.raises(EstimatorFailure, match="not the same estimand") as exc:
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="wald", ci_bootstrap=0,
        )
    assert exc.value.failure_type == refusals.INVALID_INPUT


# =========================================== stratified Wald
#
# A conditional instrument names the stratified Wald, and the estimand it
# names is the RATIO OF AVERAGES — each stratum weighted by its own
# complier share. 2SLS with W entered additively answers a different
# question: it weights each stratum by how hard the instrument moves
# treatment there. The two coincide exactly when the first stage is
# equally strong everywhere, so the DGP below deliberately makes it
# unequal — otherwise every estimator here would look correct.
# ---------------------------------------------------------------------------

_P_W1 = 0.4
# w -> (P(x|z1,w), P(x|z0,w), P(y|z1,w), P(y|z0,w))
_STRATA = {
    True:  (0.9, 0.3, 0.7, 0.4),   # first stage 0.6, LATE(w=1) = 0.50
    False: (0.6, 0.2, 0.5, 0.2),   # first stage 0.4, LATE(w=0) = 0.75
}
_RATIO_OF_AVERAGES = 0.625     # (.4*.3 + .6*.3) / (.4*.6 + .6*.4)
_AVERAGE_OF_RATIOS = 0.65      # .4*.50 + .6*.75 — the plausible wrong one
_COMPLIER_SHARE = 0.48         # .4*.6 + .6*.4


def _stratified_iv_dgp(n=400_000, seed=7, p_z_given_w=(0.5, 0.1)):
    """w → z, w → y, z → x, x → y with x,y confounded.

    ``p_z_given_w`` is (P(z|w=1), P(z|w=0)); making the two unequal is
    what separates the stratified Wald from 2SLS, since 2SLS weights by
    the instrument's residual variance within the stratum.
    """
    rng = np.random.default_rng(seed)
    w = rng.random(n) < _P_W1
    pz1, pz0 = p_z_given_w
    z = rng.random(n) < np.where(w, pz1, pz0)
    p_x, p_y = np.empty(n), np.empty(n)
    for wv, (pxz1, pxz0, pyz1, pyz0) in _STRATA.items():
        m = (w == wv)
        p_x[m] = np.where(z[m], pxz1, pxz0)
        p_y[m] = np.where(z[m], pyz1, pyz0)
    return pd.DataFrame({
        "w": w, "z": z,
        "x": rng.random(n) < p_x, "y": rng.random(n) < p_y,
    })


def test_auto_selects_stratified_wald_for_binary_with_discrete_conditioning():
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_stratified_wald"
    assert est.stratification_fallback is None
    assert est.strata is not None and len(est.strata) == 2


def test_stratified_wald_targets_the_ratio_of_averages_not_the_average_of_ratios():
    """The estimand pin. Both candidates are computed from the same table;
    only one of them is a LATE, and on a DGP where the first stage is
    equally strong across strata they would be indistinguishable."""
    est = estimate_iv_ate(
        _stratified_iv_dgp(), treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert abs(est.point - _RATIO_OF_AVERAGES) < 0.01, (
        f"point {est.point} is not the complier-share-weighted LATE"
    )
    assert abs(est.point - _AVERAGE_OF_RATIOS) > 0.015, (
        f"point {est.point} is indistinguishable from the average of the "
        f"per-stratum ratios — the DGP no longer separates the estimands"
    )


def test_2sls_on_the_same_design_answers_a_different_question():
    """The premise behind the whole path: this is not a precision gap.
    2SLS is off by ~10% here and in a direction set by the design, not by
    noise — the sample is large enough that sampling error cannot explain
    it."""
    df = _stratified_iv_dgp()
    strat = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    linear = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), model="2sls", ci_bootstrap=0,
    )
    assert abs(strat.point - _RATIO_OF_AVERAGES) < 0.01
    assert abs(linear.point - _RATIO_OF_AVERAGES) > 0.04, (
        "2SLS agrees with the LATE here, so this design no longer "
        "demonstrates why the estimator choice matters"
    )


def test_stratified_wald_reports_the_complier_share():
    est = estimate_iv_ate(
        _stratified_iv_dgp(), treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert abs(est.treatment_shift - _COMPLIER_SHARE) < 0.01
    assert abs(est.outcome_shift / est.treatment_shift - est.point) < 1e-12


def test_stratum_weights_sum_to_one_and_expose_both_arms():
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    assert abs(sum(s.weight for s in est.strata) - 1.0) < 1e-12
    for s in est.strata:
        assert s.n_instrument_high >= 2 and s.n_instrument_low >= 2
        assert s.n_obs == s.n_instrument_high + s.n_instrument_low
    by_w = {s.values[0]: s for s in est.strata}
    assert abs(by_w[True].treatment_shift - 0.6) < 0.02
    assert abs(by_w[False].treatment_shift - 0.4) < 0.02


def test_empty_conditioning_reproduces_the_marginal_wald_exactly():
    """W = () is the one-stratum degenerate case of the same arithmetic,
    which is why there is no separate code path for it."""
    df = _binary_iv_dgp(n=3000, seed=0)
    marginal = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        model="wald", ci_bootstrap=0,
    )
    stratified = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        model="stratified_wald", ci_bootstrap=0,
    )
    assert stratified.point == marginal.point


def test_stratified_wald_falls_back_when_a_stratum_lacks_an_instrument_arm():
    """Dropping the stratum would silently average over a different
    population, so the estimator refuses to and reports the substitution
    it made instead."""
    df = _stratified_iv_dgp(n=8000, seed=3)
    df.loc[df["w"] & df["z"], "z"] = False       # empty w=1's high arm
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert est.strata is None
    assert "w=True" in est.stratification_fallback
    assert "different population" in est.stratification_fallback


def test_explicit_stratified_wald_refuses_rather_than_substituting():
    """An explicit model= is a request for a particular estimand. Quietly
    returning a different one is the failure this path exists to stop."""
    df = _stratified_iv_dgp(n=8000, seed=3)
    df.loc[df["w"] & df["z"], "z"] = False
    with pytest.raises(EstimatorFailure, match="no measurable contrast") as exc:
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="stratified_wald", ci_bootstrap=0,
        )
    # An empty instrument arm inside a stratum, not our own cut being too
    # coarse: the two arrive by the same class and say different things.
    assert exc.value.failure_type == refusals.OVERLAP_INSUFFICIENT
    assert exc.value.details["stratum"] == {"w": True}


def _strata_at_the_floor(n_strata=10):
    """Every stratum holds exactly ``_MIN_PER_ARM`` rows per instrument arm.

    The full sample clears the floor everywhere; a resample rarely does,
    which is what puts draws through the bootstrap's degenerate branch.
    """
    rng = np.random.default_rng(0)
    rows = []
    for k in range(n_strata):
        for zi in (True, False):
            for _ in range(2):
                rows.append((k, zi, bool(zi), 1.5 * zi + rng.standard_normal() * 0.1))
    return pd.DataFrame(rows, columns=["w", "z", "x", "y"])


def test_a_resample_that_loses_a_stratum_arm_is_dropped_not_fatal(monkeypatch):
    """The bootstrap's catch is the refusal channel, not a blanket guard.

    It catches `EstimatorFailure` alone, which is only right if that is
    what a degenerate draw actually raises. Asserting it here rather than
    measuring it once: the branch had no construction that reached it, so
    a tally over the suite would have come back empty for want of traffic
    rather than for want of a leak.
    """
    import themis.estimation.iv as ivmod

    arrivals = []
    original = ivmod._stratified_wald_table

    def recording(*args, **kwargs):
        try:
            return original(*args, **kwargs)
        except BaseException as exc:
            arrivals.append(type(exc))
            raise

    monkeypatch.setattr(ivmod, "_stratified_wald_table", recording)

    rng = np.random.default_rng(4)
    n = 60
    w = np.array([True] * 54 + [False] * 6)
    z = np.array([True] * 27 + [False] * 27 + [True] * 3 + [False] * 3)
    x = z ^ (rng.random(n) < 0.15)
    y = 1.5 * x.astype(float) + rng.standard_normal(n)
    df = pd.DataFrame({"w": w, "z": z, "x": x, "y": y})

    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), model="stratified_wald",
        ci_bootstrap=200, random_state=1,
    )
    assert est.ci_lower < est.point < est.ci_upper
    assert arrivals, "no draw reached the degenerate branch — the construction is stale"
    assert all(issubclass(t, EstimatorFailure) for t in arrivals), set(arrivals)


def test_when_every_resample_is_degenerate_the_interval_is_refused():
    with pytest.raises(EstimatorFailure, match="degenerate") as exc:
        estimate_iv_ate(
            _strata_at_the_floor(), treatment="x", outcome="y",
            instrument="z", conditioning=("w",), model="stratified_wald",
            ci_bootstrap=200, random_state=1,
        )
    # Not the point estimate's problem: the full sample identifies it, and
    # the refusal is about the interval having no draws to be built from.
    assert exc.value.failure_type == refusals.NO_USABLE_RESAMPLE
    assert exc.value.details == {"model": "stratified_wald", "resamples": 200}


def test_too_many_strata_falls_back_naming_the_cap():
    df = _stratified_iv_dgp(n=5000, seed=1)
    rng = np.random.default_rng(0)
    df["k"] = rng.integers(0, 40, len(df))       # 40 levels, past the cap
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w", "k"), ci_bootstrap=0,
    )
    assert est.method == "iv_2sls"
    assert "distinct values" in est.stratification_fallback


def test_integer_coded_categories_still_stratify():
    """Cardinality, not dtype, decides whether W can be cut. The data
    contract widens integer columns to float, so a dtype-based gate would
    quietly drop the most common way of coding categories."""
    df = _stratified_iv_dgp(n=40_000, seed=5)
    df["w"] = df["w"].astype(int)                 # 0/1 as integers
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.method == "iv_stratified_wald", est.stratification_fallback
    assert len(est.strata) == 2
    assert abs(est.point - _RATIO_OF_AVERAGES) < 0.02


def test_degenerate_aggregate_first_stage_is_an_error_not_a_fallback():
    """No first stage is a real degeneracy: 2SLS cannot rescue it either,
    so falling back would only relabel the failure."""
    df = _stratified_iv_dgp(n=5000, seed=2)
    df["x"] = True                                # X constant → dX = 0
    with pytest.raises(EstimatorFailure, match="moves no compliers") as exc:
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="stratified_wald", ci_bootstrap=0,
        )
    assert exc.value.failure_type == refusals.NO_FIRST_STAGE


def test_stratified_wald_carries_its_own_assumptions():
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    assert any("LATE" in a for a in est.assumptions)
    assert any("positivity" in a for a in est.assumptions)
    assert any("complier_share" in a for a in est.assumptions)
    assert not any("linearity" in a for a in est.assumptions), (
        "the stratified Wald is non-parametric within strata; claiming "
        "linearity would overstate what it rests on"
    )


def test_the_linear_ar_set_never_rides_on_the_stratified_path():
    """The set in ``anderson_rubin_confidence_set`` residualises on
    [1, W] and inverts a test for the LINEAR IV coefficient, so its own
    recorded point is the 2SLS one. The stratified path gets a set built
    on its own moment instead — exactly one of the two is ever
    populated."""
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    assert est.anderson_rubin is None
    assert est.stratified_anderson_rubin is not None

    linear = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), model="2sls", ci_bootstrap=0,
    )
    assert linear.anderson_rubin is not None, (
        "premise broken: AR is supposed to still be available on the "
        "linear path, so its absence above is a deliberate choice"
    )
    assert linear.stratified_anderson_rubin is None


def test_stratified_ar_set_is_centred_on_the_reported_point():
    """A weak-robust set that brackets a different estimator's estimate is
    worse than no set: both halves stay self-consistent and nothing in the
    arithmetic gives the substitution away."""
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    sar = est.stratified_anderson_rubin
    assert sar.point == est.point
    assert sar.kind == "bounded"
    assert sar.lower < est.point < sar.upper


def test_stratified_ar_set_reports_the_aggregate_moment_it_solved():
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    sar = est.stratified_anderson_rubin
    assert sar.outcome_shift == pytest.approx(est.outcome_shift)
    assert sar.treatment_shift == pytest.approx(est.treatment_shift)
    assert sar.n_strata == len(est.strata)
    # Two cell means per stratum — one per instrument arm.
    assert sar.dof == est.sample_size - 2 * len(est.strata)
    assert sar.var_yy > 0 and sar.var_xx > 0


def test_stratified_ar_kappa_is_the_f_critical_value():
    from scipy.stats import f as f_dist

    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0, ci_level=0.9,
    )
    sar = est.stratified_anderson_rubin
    assert sar.ci_level == 0.9
    assert sar.kappa == pytest.approx(float(f_dist.ppf(0.9, 1, sar.dof)))


def test_a_degenerate_first_stage_opens_the_set_to_the_whole_line():
    """When the instrument moves no compliers the honest answer is that
    the data cannot bound the effect at all. A percentile bootstrap has no
    shape that can say this — it returns a finite interval whatever
    happens."""
    rng = np.random.default_rng(3)
    n = 3000
    w = (rng.random(n) < 0.5).astype(int)
    z = (rng.random(n) < 0.5).astype(int)
    x = (rng.random(n) < 0.3).astype(int)      # independent of z
    y = rng.normal(size=n) + x
    df = pd.DataFrame({"z": z, "x": x, "y": y, "w": w})

    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    )
    assert est.stratified_anderson_rubin.kind == "whole_line"
    assert est.stratified_anderson_rubin.lower is None
    assert est.stratified_anderson_rubin.upper is None


def test_arm_robust_variance_separates_from_pooled_on_unbalanced_arms():
    """The stratum variances are arm-specific, so the set does not assume
    the two instrument arms are equally noisy.

    With BALANCED arms the pooled and arm-specific estimators of a
    difference in means coincide, so this only shows up when the arms are
    unbalanced — and then it moves in both directions: noise in the large
    arm makes the pooled set too wide, noise in the small arm makes it too
    narrow. The narrow direction is the dangerous one.
    """
    def build(noisy_arm):
        rng = np.random.default_rng(17)
        n = 20_000
        z = (rng.random(n) < 0.85).astype(int)     # unbalanced on purpose
        comply = rng.random(n) < 0.5
        x = np.where(comply, z, (rng.random(n) < 0.3).astype(int))
        y = 0.9 * x + np.where(
            z == noisy_arm,
            rng.normal(scale=3.0, size=n),
            rng.normal(scale=0.3, size=n),
        )
        return pd.DataFrame({"z": z, "x": x, "y": y})

    for noisy_arm, direction in ((1, "wider"), (0, "narrower")):
        df = build(noisy_arm)
        pooled = estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0,
        )
        robust = estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0,
            model="stratified_wald",
        )
        assert pooled.point == robust.point, "same estimand, same number"
        w_pooled = pooled.anderson_rubin.upper - pooled.anderson_rubin.lower
        w_robust = (robust.stratified_anderson_rubin.upper
                    - robust.stratified_anderson_rubin.lower)
        if direction == "wider":
            assert w_pooled > 2 * w_robust
        else:
            assert w_robust > 2 * w_pooled


def test_marginal_and_stratified_ar_agree_when_the_arms_are_balanced():
    """W = () is the one-stratum degenerate case. The two sets are not
    required to be bit-identical — one pools the residual variance, the
    other keeps it arm-specific — but with balanced arms and homoskedastic
    noise the two estimators coincide, so a large gap here would mean the
    stratified moment is not the same test."""
    rng = np.random.default_rng(5)
    n = 5000
    z = (rng.random(n) < 0.5).astype(int)
    comply = rng.random(n) < 0.5
    x = np.where(comply, z, (rng.random(n) < 0.3).astype(int))
    y = 0.9 * x + rng.normal(size=n)
    df = pd.DataFrame({"z": z, "x": x, "y": y})

    marginal = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0,
    )
    stratified = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z", ci_bootstrap=0,
        model="stratified_wald",
    )
    assert marginal.method == "iv_wald"
    assert stratified.point == marginal.point
    a = marginal.anderson_rubin
    b = stratified.stratified_anderson_rubin
    assert b.lower == pytest.approx(a.lower, rel=1e-3)
    assert b.upper == pytest.approx(a.upper, rel=1e-3)


def test_stratified_ar_covers_at_its_nominal_rate():
    """Size control that does not depend on first-stage strength is the
    whole point of inverting a test rather than resampling an estimate.
    Run at a first stage weak enough that most draws come back unbounded.
    """
    def weak(n, seed):
        rng = np.random.default_rng(seed)
        w = (rng.random(n) < 0.5).astype(int)
        z = (rng.random(n) < 0.5).astype(int)
        comply = rng.random(n) < np.where(w == 1, 0.04, 0.02)
        always = rng.random(n) < 0.2
        u = rng.normal(size=n)                      # latent confounder
        x = np.where(always, 1, np.where(comply, z, 0))
        x = np.where(u > 1.2, 1, x)                 # u drives x as well
        tau = np.where(w == 1, 0.5, 1.5)
        y = tau * x + 1.5 * u + 0.3 * w + rng.normal(scale=0.5, size=n)
        return pd.DataFrame({"z": z, "x": x, "y": y, "w": w})

    truth = estimate_iv_ate(
        weak(2_000_000, 1), treatment="x", outcome="y", instrument="z",
        conditioning=("w",), ci_bootstrap=0,
    ).point

    def contains(s, v):
        if s.kind == "bounded":
            return s.lower <= v <= s.upper
        if s.kind == "whole_line":
            return True
        if s.kind == "disconnected":
            return v <= s.lower or v >= s.upper
        if s.kind == "unbounded_below":
            return v <= s.upper
        return v >= s.lower

    shapes, hits, reps = set(), 0, 200
    for r in range(reps):
        est = estimate_iv_ate(
            weak(2000, 900_000 + r), treatment="x", outcome="y",
            instrument="z", conditioning=("w",), ci_bootstrap=0,
        )
        s = est.stratified_anderson_rubin
        shapes.add(s.kind)
        hits += contains(s, truth)

    assert hits / reps >= 0.90, f"coverage {hits / reps} at nominal 0.95"
    assert "whole_line" in shapes, (
        "premise broken: this design is supposed to be weak enough that "
        "some draws cannot bound the effect at all"
    )


def test_bootstrap_ci_brackets_the_stratified_point():
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=150,
    )
    assert est.method == "iv_stratified_wald"
    assert est.ci_lower < est.point < est.ci_upper


# ============================================ determinism + CI


def test_deterministic_under_fixed_seed():
    df = _binary_iv_dgp(n=500, seed=0)
    e1 = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=50, random_state=42,
    )
    e2 = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=50, random_state=42,
    )
    assert e1.point == e2.point
    assert e1.ci_lower == e2.ci_lower
    assert e1.ci_upper == e2.ci_upper


def test_bootstrap_ci_brackets_point():
    df = _binary_iv_dgp(n=800, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=100, random_state=1,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_ci_bootstrap_zero_skips():
    df = _binary_iv_dgp(n=200, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.ci_lower is None
    assert est.ci_upper is None


# ============================================ shape


def test_returns_named_tuple():
    df = _binary_iv_dgp(n=100, seed=0)
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert isinstance(est, IVEstimate)
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.instrument == "z"
    assert est.conditioning == ()
    assert len(est.data_hash) == 64
