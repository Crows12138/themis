"""Ratio-scale (excess relative risk) four-way decomposition estimator —
VanderWeele 2014, binary outcome + binary mediator (eAppendix §3.4).

For a binary outcome the four-way decomposition (CDE / INTref / INTmed /
PIE) lives naturally on the multiplicative scale: the total effect is a
risk ratio and the excess relative risk (RR − 1) decomposes additively.
Unlike the difference-scale decomposition in ``four_way.py`` — a pure
computation over standardized cell means p_am / q_a — the ratio-scale
components are functions of the LOGISTIC regression coefficients and do
NOT collapse to any function of the standardized risks alone (logistic
non-collapsibility; VanderWeele works in the odds-ratio approximation).
So this estimator FITS the two parametric models and evaluates
VanderWeele's closed form:

  outcome:   logit P(Y=1 | A, M, C) = t0 + t1·A + t2·M + t3·A·M + t_C·C
  mediator:  logit P(M=1 | A, C)    = b0 + b1·A + b_C·C

extracts (t1, t2, t3) and (b0, b1, b_C), evaluates
``four_way.four_way_ratio_decomposition`` at the sample-mean covariate
value c (VanderWeele's documented "input the mean covariate value as a
summary" convention — the ratio-scale closed form is conditional on c, so
a single covariate value is chosen rather than averaging the nonlinear
formula over C), and forms percentile-bootstrap CIs.

Scope (declared):
- Binary OUTCOME required. The MEDIATOR may be binary (§3.4, logistic
  mediator model) or continuous (§3.3, linear mediator model with normal
  residual variance) — the estimator detects the mediator scale and picks
  the matching closed form. A continuous outcome has no excess relative
  risk and uses the difference-scale ``four_way_decomposition``.
- The decomposition is reported at the sample-mean covariate value. Effect
  modification by C (reporting at several c) is deferred.
- Surfaced in the kernel mediation dispatch when the outcome is binary: the
  ``themis.estimate`` mediation path attaches a ``four_way_ratio`` block
  alongside the NDE/NIE decomposition.

API::

    from themis.estimation.four_way_ratio import estimate_four_way_ratio
    est = estimate_four_way_ratio(
        data, treatment="a", outcome="y", mediator="m", adjustment=("z",),
    )
    print(est.err_cde_point, est.prop_mediated_point)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import statsmodels.api as sm

from .contract import validate_data
from .dose_response import EstimatorFailure
from .four_way import (
    FourWayRatioComponents,
    four_way_ratio_decomposition,
    four_way_ratio_decomposition_continuous,
)
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class FourWayRatioEstimate:
    """Excess-relative-risk four-way decomposition + bootstrap CIs.

    Every ``*_point`` is the estimate at the fitted coefficients; every
    ``*_ci_lower`` / ``*_ci_upper`` its percentile-bootstrap interval. The
    four ``err_*`` sum to ``total_err``; the four proportions sum to 1.
    """

    err_cde_point: float
    err_cde_ci_lower: float | None
    err_cde_ci_upper: float | None
    err_intref_point: float
    err_intref_ci_lower: float | None
    err_intref_ci_upper: float | None
    err_intmed_point: float
    err_intmed_ci_lower: float | None
    err_intmed_ci_upper: float | None
    err_pie_point: float
    err_pie_ci_lower: float | None
    err_pie_ci_upper: float | None
    total_err_point: float
    total_err_ci_lower: float | None
    total_err_ci_upper: float | None
    total_rr_point: float
    total_rr_ci_lower: float | None
    total_rr_ci_upper: float | None
    prop_mediated_point: float
    prop_mediated_ci_lower: float | None
    prop_mediated_ci_upper: float | None
    prop_interaction_point: float
    prop_interaction_ci_lower: float | None
    prop_interaction_ci_upper: float | None
    prop_eliminated_point: float
    prop_eliminated_ci_lower: float | None
    prop_eliminated_ci_upper: float | None
    ci_level: float
    method: str                       # "four_way_ratio_logit"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    mediator: str
    mediator_reference: object        # the m* the CDE fixes M at
    # The fitted coefficients the oracle was evaluated at (audit trail).
    t1: float
    t2: float
    t3: float
    b0: float
    b1: float
    bcc: float
    # "binary" (§3.4, logistic mediator) or "continuous" (§3.3, linear
    # mediator with residual variance ss_m). ss_m is None for the binary case.
    mediator_scale: str = "binary"
    ss_m: float | None = None
    cluster: str | None = None


def _is_binary(series: pd.Series) -> bool:
    return set(np.unique(series.to_numpy(dtype=float))) <= {0.0, 1.0}


def _decompose_frame(
    frame: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    adjustment: tuple[str, ...],
    mediator_reference: float,
    covariate_means: dict[str, float],
    mediator_binary: bool,
) -> tuple[FourWayRatioComponents, float, float, float, float, float, float, float | None]:
    """Fit the logistic outcome model + the mediator model on ``frame`` and
    return the ratio-scale decomposition plus the (t1, t2, t3, b0, b1, bcc,
    ss_m) it used.

    The mediator model is logistic (§3.4) for a binary mediator or linear
    (§3.3) for a continuous one; ``ss_m`` is the linear model's ML residual
    variance (SSR/n, matching VanderWeele's joint normal likelihood) and is
    ``None`` for the binary case.
    """
    adj_term = " + ".join(adjustment)
    sep = " + " if adj_term else ""
    interaction = f"{treatment}:{mediator}"
    outcome_formula = (
        f"{outcome} ~ {treatment} + {mediator} + {interaction}{sep}{adj_term}"
    )
    mediator_formula = f"{mediator} ~ {treatment}{sep}{adj_term}"

    om = sm.Logit.from_formula(outcome_formula, data=frame).fit(disp=0)
    t1 = float(om.params[treatment])
    t2 = float(om.params[mediator])
    t3 = float(om.params[interaction])

    if mediator_binary:
        mm = sm.Logit.from_formula(mediator_formula, data=frame).fit(disp=0)
        b0 = float(mm.params["Intercept"])
        b1 = float(mm.params[treatment])
        bcc = float(sum(mm.params[c] * covariate_means[c] for c in adjustment))
        comps = four_way_ratio_decomposition(
            t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, bcc=bcc,
            a1=1.0, a0=0.0, mstar=float(mediator_reference),
        )
        return comps, t1, t2, t3, b0, b1, bcc, None

    mm = sm.OLS.from_formula(mediator_formula, data=frame).fit()
    b0 = float(mm.params["Intercept"])
    b1 = float(mm.params[treatment])
    bcc = float(sum(mm.params[c] * covariate_means[c] for c in adjustment))
    # ML residual variance (SSR/n) — matches VanderWeele's nlmixed joint
    # normal likelihood ll_m = -(m-mu)²/(2·ss_m) - ½·log(ss_m).
    resid = mm.resid.to_numpy()
    ss_m = float(np.mean(resid ** 2))
    comps = four_way_ratio_decomposition_continuous(
        t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, ss_m=ss_m, bcc=bcc,
        a1=1.0, a0=0.0, mstar=float(mediator_reference),
    )
    return comps, t1, t2, t3, b0, b1, bcc, ss_m


def estimate_four_way_ratio(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    adjustment: tuple[str, ...] = (),
    mediator_reference: object = False,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> FourWayRatioEstimate:
    """Excess-relative-risk four-way decomposition (VanderWeele eAppendix
    §3.4 / §3.3).

    Requires a binary OUTCOME; the mediator may be binary (§3.4, logistic
    mediator model) or continuous (§3.3, linear mediator model with normal
    residual variance) — the estimator detects which and picks the matching
    closed form. A continuous outcome has no excess relative risk and uses
    the difference-scale ``four_way_decomposition`` instead. Covariates enter
    both models (so t1/t2/t3 and b0/b1 are adjusted); the decomposition is
    reported at the sample-mean covariate value.

    ``cluster`` switches the bootstrap to a pairs cluster bootstrap (parity
    with the other estimators); ``None`` is the i.i.d. bootstrap.
    """
    required = {treatment, outcome, mediator, *adjustment}
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required,
        presence_columns=(cluster,) if cluster is not None else (),
    )
    df = contract.data

    if not _is_binary(df[outcome]):
        raise EstimatorFailure(
            "outcome_not_binary",
            f"the excess-relative-risk four-way decomposition needs a binary "
            f"outcome; {outcome!r} is not 0/1. Use the difference-scale "
            f"four_way_decomposition for a continuous outcome.",
            treatment=treatment,
        )
    # Mediator scale selects §3.4 (binary → logistic) vs §3.3 (continuous →
    # linear with residual variance).
    mediator_binary = _is_binary(df[mediator])
    check_levels = (treatment, mediator) if mediator_binary else (treatment,)
    for t in check_levels:
        if len(np.unique(df[t].to_numpy())) < 2:
            raise EstimatorFailure(
                "overlap_insufficient",
                f"{t!r} has a single observed level — no contrast to "
                f"decompose. Supply data with variation in {t!r}.",
                treatment=treatment,
            )

    # statsmodels formula API wants float columns.
    fit_df = df.copy()
    for c in [col for col in fit_df.columns if fit_df[col].dtype == bool]:
        fit_df[c] = fit_df[c].astype(float)
    # Covariate value at which the (conditional) ratio-scale decomposition
    # is reported: the sample mean (VanderWeele's summary convention).
    covariate_means = {c: float(fit_df[c].mean()) for c in adjustment}

    mref = float(mediator_reference)

    try:
        point_comps, t1, t2, t3, b0, b1, bcc, ss_m = _decompose_frame(
            fit_df, treatment=treatment, outcome=outcome, mediator=mediator,
            adjustment=adjustment, mediator_reference=mref,
            covariate_means=covariate_means, mediator_binary=mediator_binary,
        )
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise EstimatorFailure(
            "model_fit_failed",
            f"outcome/mediator model fit failed on the full sample: {exc}",
            treatment=treatment,
        )

    # Bootstrap: resample (rows or whole clusters), refit both models,
    # recompute every reported quantity.
    rng = np.random.default_rng(random_state)
    n = len(fit_df)
    keys = (
        "err_cde", "err_intref", "err_intmed", "err_pie",
        "total_err", "total_rr",
        "prop_mediated", "prop_interaction", "prop_eliminated",
    )
    draws: dict[str, list[float]] = {k: [] for k in keys}
    if ci_bootstrap > 0:
        for _ in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            bframe = fit_df.iloc[idx].reset_index(drop=True)
            try:
                c, *_ = _decompose_frame(
                    bframe, treatment=treatment, outcome=outcome,
                    mediator=mediator, adjustment=adjustment,
                    mediator_reference=mref, covariate_means=covariate_means,
                    mediator_binary=mediator_binary,
                )
            except Exception:
                continue
            draws["err_cde"].append(c.err_cde)
            draws["err_intref"].append(c.err_intref)
            draws["err_intmed"].append(c.err_intmed)
            draws["err_pie"].append(c.err_pie)
            draws["total_err"].append(c.total_err)
            draws["total_rr"].append(c.total_rr)
            draws["prop_mediated"].append(c.prop_mediated)
            draws["prop_interaction"].append(c.prop_interaction)
            draws["prop_eliminated"].append(c.prop_eliminated)

    alpha = (1 - ci_level) / 2

    def _ci(key: str) -> tuple[float | None, float | None]:
        vals = np.asarray(draws[key], dtype=float)
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            return None, None
        return (float(np.quantile(vals, alpha)),
                float(np.quantile(vals, 1 - alpha)))

    cde_lo, cde_hi = _ci("err_cde")
    intref_lo, intref_hi = _ci("err_intref")
    intmed_lo, intmed_hi = _ci("err_intmed")
    pie_lo, pie_hi = _ci("err_pie")
    terr_lo, terr_hi = _ci("total_err")
    trr_lo, trr_hi = _ci("total_rr")
    pm_lo, pm_hi = _ci("prop_mediated")
    pi_lo, pi_hi = _ci("prop_interaction")
    pe_lo, pe_hi = _ci("prop_eliminated")

    assumptions = (
        "no_unmeasured_confounder_exposure_outcome_given_adjustment",
        "no_unmeasured_confounder_mediator_outcome_given_exposure_and_adjustment",
        "no_unmeasured_confounder_exposure_mediator_given_adjustment",
        "no_effect_of_exposure_that_confounds_mediator_outcome",
        "logit_outcome_model_with_exposure_mediator_interaction",
        (
            "logit_mediator_model" if mediator_binary
            else "linear_mediator_model_with_normal_residual_variance"
        ),
        "decomposition_reported_at_sample_mean_covariate_value",
    )
    if not mediator_binary:
        # §3.3 integrates the odds-ratio-approximation risk over the normal
        # mediator, so the closed form inherits the rare-outcome (OR≈RR)
        # approximation the ratio-scale decomposition already rests on.
        assumptions = assumptions + (
            "continuous_mediator_odds_ratio_approximation_rare_outcome",
        )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return FourWayRatioEstimate(
        err_cde_point=point_comps.err_cde,
        err_cde_ci_lower=cde_lo, err_cde_ci_upper=cde_hi,
        err_intref_point=point_comps.err_intref,
        err_intref_ci_lower=intref_lo, err_intref_ci_upper=intref_hi,
        err_intmed_point=point_comps.err_intmed,
        err_intmed_ci_lower=intmed_lo, err_intmed_ci_upper=intmed_hi,
        err_pie_point=point_comps.err_pie,
        err_pie_ci_lower=pie_lo, err_pie_ci_upper=pie_hi,
        total_err_point=point_comps.total_err,
        total_err_ci_lower=terr_lo, total_err_ci_upper=terr_hi,
        total_rr_point=point_comps.total_rr,
        total_rr_ci_lower=trr_lo, total_rr_ci_upper=trr_hi,
        prop_mediated_point=point_comps.prop_mediated,
        prop_mediated_ci_lower=pm_lo, prop_mediated_ci_upper=pm_hi,
        prop_interaction_point=point_comps.prop_interaction,
        prop_interaction_ci_lower=pi_lo, prop_interaction_ci_upper=pi_hi,
        prop_eliminated_point=point_comps.prop_eliminated,
        prop_eliminated_ci_lower=pe_lo, prop_eliminated_ci_upper=pe_hi,
        ci_level=ci_level,
        method="four_way_ratio_logit",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        mediator=mediator,
        mediator_reference=mediator_reference,
        t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, bcc=bcc,
        mediator_scale="binary" if mediator_binary else "continuous",
        ss_m=ss_m,
        cluster=cluster,
    )
