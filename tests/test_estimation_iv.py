"""Phase 7.3 S.IVN.1 — unit tests for the IV ATE estimator."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

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
    with pytest.raises(ValueError, match="first-stage"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            ci_bootstrap=0,
        )


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
    with pytest.raises(ValueError, match="binary"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            model="wald", ci_bootstrap=0,
        )


def test_wald_rejects_conditioning():
    """The MARGINAL Wald refuses a conditioning set, because ignoring W is
    a different estimand rather than an approximation of the same one."""
    df = _binary_iv_dgp(n=500, seed=0)
    df["w"] = np.random.default_rng(0).standard_normal(500)
    with pytest.raises(NotImplementedError, match="not the same estimand"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="wald", ci_bootstrap=0,
        )


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
    with pytest.raises(ValueError, match="no measurable contrast"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="stratified_wald", ci_bootstrap=0,
        )


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
    with pytest.raises(ValueError, match="moves no compliers"):
        estimate_iv_ate(
            df, treatment="x", outcome="y", instrument="z",
            conditioning=("w",), model="stratified_wald", ci_bootstrap=0,
        )


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


def test_no_anderson_rubin_set_on_the_stratified_path():
    """The AR set inverts a test for the LINEAR IV coefficient — its own
    recorded point is the 2SLS one. Attaching it here would put two
    estimands in one result."""
    est = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), ci_bootstrap=0,
    )
    assert est.anderson_rubin is None
    linear = estimate_iv_ate(
        _stratified_iv_dgp(n=20_000), treatment="x", outcome="y",
        instrument="z", conditioning=("w",), model="2sls", ci_bootstrap=0,
    )
    assert linear.anderson_rubin is not None, (
        "premise broken: AR is supposed to still be available on the "
        "linear path, so its absence above is a deliberate choice"
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
