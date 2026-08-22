"""Doubly-robust ATE estimation — IPW + AIPW.

Completes the "robustness triangle" of the backdoor estimand. The
existing ``estimate_backdoor_ate`` is the outcome-regression (plug-in
g-formula) corner: consistent iff the OUTCOME model E[Y|T,Z] is
correct. This module adds the other two corners:

- **IPW** (``estimate_ipw_ate``) — inverse-probability weighting on
  the propensity e(Z)=P(T=1|Z). Consistent iff the TREATMENT model is
  correct. Horvitz-Thompson (unstabilized) and Hajek (stabilized,
  default) forms.

- **AIPW** (``estimate_aipw_ate``) — the augmented / doubly-robust
  estimator. Consistent if EITHER the outcome model OR the propensity
  model is correct (Robins-Rotnitzky-Zhao 1994; Bang & Robins 2005).
  This is the flagship: a second line of defence against nuisance
  misspecification that neither single-model estimator has.

AIPW estimating equation (per unit i):

    phi_i = mu1(Z_i) - mu0(Z_i)
            + T_i (Y_i - mu1(Z_i)) / e(Z_i)
            - (1 - T_i)(Y_i - mu0(Z_i)) / (1 - e(Z_i))

    psi_AIPW = (1/n) Sum_i phi_i

where mu_t(Z) = E[Y|T=t,Z] and e(Z) = P(T=1|Z).

**Inference.** The two estimators get their CI from different, and in
each case *appropriate*, machinery:

- AIPW: the moment above is Neyman-orthogonal — its Gateaux derivative
  w.r.t. the nuisances (mu, e) vanishes at the truth (Chernozhukov et
  al. 2018; Tsiatis 2006). So when the parametric nuisances are
  root-n consistent, the estimation of (mu, e) contributes negligibly
  to first-order asymptotics and the influence-function variance is
  correct:  Var(psi) = (1/n^2) Sum_i (phi_i - psi)^2.  We report this
  ANALYTIC SE + a Wald CI as the default — that closed-form inference
  is AIPW's practical advantage over the bootstrap-only g-formula.
  Under a cluster column the variance is made cluster-robust (sum the
  influence within each cluster, then across clusters).

- IPW (Hajek): its plug-in influence function is NOT orthogonal —
  ignoring propensity-estimation uncertainty biases the analytic SE.
  So IPW's CI is a percentile bootstrap that refits the propensity on
  each resample (cluster-aware via the shared resampler), correctly
  propagating that uncertainty.

**Positivity.** Both estimators divide by e (or 1-e); a propensity near
0 or 1 makes weights explode. We clip e to ``[floor, 1-floor]`` for
numerical stability (Winsorizing the weights, which preserves the ATE
estimand — unlike trimming, which drops units and changes the target)
and DISCLOSE it: ``PropensitySummary`` records the raw (pre-clip) min /
max and how many units were clipped. A caller seeing many clipped units
is being told the overlap is thin, not having it hidden.

**Scope declared.** Parametric nuisances (logistic propensity; linear /
logistic outcome), no cross-fitting. Cross-fit DML (Chernozhukov 2018)
removes own-observation overfitting bias when nuisances are flexible ML
models; it is second-order for the fixed-dimension parametric nuisances
here, and the econml DR-learner in the dose-response path already
covers the cross-fit ML case. TMLE (an equivalent doubly-robust
substitution estimator) is a separate follow-on.

References:
- Robins JM, Rotnitzky A, Zhao LP. "Estimation of regression
  coefficients when some regressors are not always observed." JASA
  1994;89(427):846-866.
- Bang H, Robins JM. "Doubly robust estimation in missing data and
  causal inference models." Biometrics 2005;61(4):962-973.
- Hernan MA, Robins JM. *Causal Inference: What If*. 2020, ch.13
  (standardization / IP weighting) — the two estimators contrasted.
- Tsiatis AA. *Semiparametric Theory and Missing Data*. 2006 (the
  influence-function variance of the AIPW estimator).

API:

    from themis.estimation.aipw import estimate_aipw_ate, estimate_ipw_ate
    est = estimate_aipw_ate(
        data, treatment="x", outcome="y", adjustment=("z1", "z2"),
    )
    print(est.point, est.ci_lower, est.ci_upper, est.std_error)
"""
from __future__ import annotations

from dataclasses import dataclass
from statistics import NormalDist
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import DataContract, validate_data
from .declared import ordered_entry
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices
from .support import (
    Support, overlap_assumption, require_within_stratum_contrast,
)


OutcomeModel = Literal["auto", "linear", "logistic"]

# Default propensity clip. e in [floor, 1-floor]; 0.01 is the common
# Winsorizing threshold (weights capped at 100). Exposed as a kwarg.
DEFAULT_PROPENSITY_FLOOR = 0.01


@dataclass(frozen=True)
class PropensitySummary:
    """Overlap / positivity disclosure for a weighted estimate.

    - ``raw_min`` / ``raw_max``: the propensity range BEFORE clipping —
      the honest picture of overlap. A raw_min near 0 (or raw_max near
      1) means some units are almost never (almost always) treated.
    - ``n_trimmed``: how many of the n propensities were clipped to the
      ``[floor, 1-floor]`` band. Large ⇒ thin overlap; the weights were
      capped to keep the variance finite.
    - ``floor``: the clip threshold used.
    - ``model``: ``"logistic"`` (fitted on the adjustment set) or
      ``"marginal"`` (empty adjustment ⇒ e = P(T=1), a constant).
    """

    raw_min: float
    raw_max: float
    n_trimmed: int
    floor: float
    model: str


@dataclass(frozen=True)
class IPWEstimate:
    """Result of an inverse-probability-weighted ATE estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                # "ipw_stabilized" | "ipw_ht"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    propensity: PropensitySummary
    stabilized: bool
    form: str = ""
    cluster: str | None = None


@dataclass(frozen=True)
class AIPWEstimate:
    """Result of an augmented-IPW (doubly-robust) ATE estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                # "aipw"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    propensity: PropensitySummary
    std_error: float | None    # influence-function SE (analytic CI path)
    ci_method: str             # "influence_function" | "bootstrap"
    doubly_robust: bool = True
    form: str = ""             # outcome-model form: "linear" | "logistic"
    cluster: str | None = None


# --- public estimators --------------------------------------------------------


def estimate_ipw_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    stabilized: bool = True,
    propensity_floor: float = DEFAULT_PROPENSITY_FLOOR,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> IPWEstimate:
    """Inverse-probability-weighted ATE + cluster-aware bootstrap CI.

    ``stabilized`` picks the Hajek estimator (default; weights
    normalized within each arm — lower variance) over the raw
    Horvitz-Thompson form. Consistent iff the propensity model is
    correct; use ``estimate_aipw_ate`` for the doubly-robust guarantee.

    CI is a percentile bootstrap that refits the propensity on each
    resample, so it propagates the propensity-estimation uncertainty
    that IPW's (non-orthogonal) plug-in influence function omits.
    ``cluster`` switches the resample to whole clusters (pairs cluster
    bootstrap); ``None`` reproduces the i.i.d. draw byte-for-byte.
    """
    ctx = _prepare(data, treatment, outcome, adjustment, cluster)
    df, contract, groups = ctx.df, ctx.contract, ctx.groups

    e, prop = _propensity_scores(df, treatment, adjustment, floor=propensity_floor)
    t = df[treatment].to_numpy(dtype=float)
    y = _outcome_vector(df, outcome)
    point = _ipw_point(t, y, e, stabilized=stabilized)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _ipw_bootstrap_ci(
            df, treatment, outcome, adjustment,
            stabilized=stabilized, floor=propensity_floor,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    method = "ipw_stabilized" if stabilized else "ipw_ht"
    assumptions = _assumptions_ipw(stabilized, len(adjustment), prop,
                                   cluster, ctx.support)
    # The design took each adjustment column as ONE term, so a column
    # with more than two levels was read as a number: level three sits
    # twice as far from level one as level two does. Nothing in the
    # program claimed that, and `scale` has no member that could deny
    # it, so the fit says what it assumed.
    assumptions += ordered_entry(ctx.df, adjustment)
    return IPWEstimate(
        point=float(point),
        ci_lower=_maybe_float(ci_lower),
        ci_upper=_maybe_float(ci_upper),
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        propensity=prop,
        stabilized=stabilized,
        form="logistic_propensity",
        cluster=cluster,
    )


def estimate_aipw_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    outcome_model: OutcomeModel = "auto",
    propensity_floor: float = DEFAULT_PROPENSITY_FLOOR,
    ci_method: Literal["influence_function", "bootstrap"] = "influence_function",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> AIPWEstimate:
    """Augmented-IPW (doubly-robust) ATE.

    Consistent if EITHER the outcome regression E[Y|T,Z] OR the
    propensity P(T=1|Z) is correctly specified.

    ``ci_method``:
    - ``"influence_function"`` (default) — analytic Wald CI from the
      orthogonal-moment influence function; cluster-robust when
      ``cluster`` is set. Assumes both nuisances are root-n consistent;
      when you suspect a misspecified nuisance, prefer the bootstrap.
    - ``"bootstrap"`` — percentile bootstrap refitting both nuisances
      per resample (cluster-aware). More expensive; no orthogonality
      assumption on the variance.

    ``outcome_model`` follows the backdoor estimator: ``"auto"`` picks
    logistic for a bool outcome and linear otherwise.
    """
    ctx = _prepare(data, treatment, outcome, adjustment, cluster)
    df, contract, groups = ctx.df, ctx.contract, ctx.groups

    resolved = _resolve_outcome_model(df, outcome, outcome_model)
    e, prop = _propensity_scores(df, treatment, adjustment, floor=propensity_floor)
    t = df[treatment].to_numpy(dtype=float)
    mu1, mu0, y = _outcome_mu(df, treatment, outcome, adjustment, model=resolved)

    phi = _aipw_pseudo_outcome(t, y, e, mu1, mu0)
    point = float(np.mean(phi))

    std_error: float | None = None
    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_method == "influence_function":
        std_error = _influence_function_se(phi, point, groups)
        if std_error is not None and ci_bootstrap != 0:
            z = NormalDist().inv_cdf(1 - (1 - ci_level) / 2)
            ci_lower = point - z * std_error
            ci_upper = point + z * std_error
    else:  # bootstrap
        if ci_bootstrap > 0:
            ci_lower, ci_upper = _aipw_bootstrap_ci(
                df, treatment, outcome, adjustment,
                model=resolved, floor=propensity_floor,
                ci_bootstrap=ci_bootstrap, ci_level=ci_level,
                random_state=random_state, groups=groups,
            )

    assumptions = _assumptions_aipw(resolved, len(adjustment), prop,
                                    cluster, ci_method, ctx.support)
    # The design took each adjustment column as ONE term, so a column
    # with more than two levels was read as a number: level three sits
    # twice as far from level one as level two does. Nothing in the
    # program claimed that, and `scale` has no member that could deny
    # it, so the fit says what it assumed.
    assumptions += ordered_entry(ctx.df, adjustment)
    return AIPWEstimate(
        point=point,
        ci_lower=_maybe_float(ci_lower),
        ci_upper=_maybe_float(ci_upper),
        ci_level=ci_level,
        method="aipw",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        propensity=prop,
        std_error=_maybe_float(std_error),
        ci_method=ci_method,
        doubly_robust=True,
        form=resolved,
        cluster=cluster,
    )


# --- shared preparation -------------------------------------------------------


@dataclass(frozen=True)
class _PreparedData:
    df: pd.DataFrame
    contract: DataContract
    groups: np.ndarray | None
    support: Support


def _prepare(
    data: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    cluster: str | None,
) -> _PreparedData:
    """Validate + overlap-check, shared by IPW, AIPW and TMLE.

    Mirrors the backdoor estimator's positivity precondition at both scopes.
    A single observed treatment level is the maximal violation — no contrast
    anywhere, every inverse-propensity weight undefined for the absent arm.
    A stratum holding one arm is the same violation inside one cell, and the
    marginal test cannot see it: Winsorizing does not either, because the
    floor is applied to a FITTED propensity and a fitted model hands a cell
    whose empirical rate is 0.000 a comfortable 0.091.
    """
    required = {treatment, outcome, *adjustment}
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    observed_levels = df[treatment].dropna().unique()
    if len(observed_levels) < 2:
        raise EstimatorFailure(
            Refusal.OVERLAP_INSUFFICIENT,
            f"treatment {treatment!r} has a single observed level "
            f"({observed_levels.tolist()}) in the data — positivity is "
            f"maximally violated and there is no treatment contrast to "
            f"estimate. IPW / AIPW need both treated and control units; "
            f"supply data with variation in {treatment!r}.",
            treatment=treatment,
        )
    support = require_within_stratum_contrast(df, treatment, adjustment)
    return _PreparedData(df=df, contract=contract, groups=groups,
                         support=support)


def _resolve_outcome_model(
    df: pd.DataFrame, outcome: str, outcome_model: OutcomeModel,
) -> str:
    if outcome_model == "auto":
        is_bool = pd.api.types.is_bool_dtype(df[outcome])
        return "logistic" if is_bool else "linear"
    return outcome_model


# --- nuisance models ----------------------------------------------------------


def _propensity_scores(
    df: pd.DataFrame,
    treatment: str,
    adjustment: tuple[str, ...],
    *,
    floor: float,
) -> tuple[np.ndarray, PropensitySummary]:
    """Fit e(Z)=P(T=1|Z), then Winsorize to [floor, 1-floor].

    Empty adjustment ⇒ the propensity is the constant marginal P(T=1).
    Returns the clipped scores + a disclosure of the raw range and the
    number of clipped units.
    """
    if not 0.0 < floor < 0.5:
        raise ValueError(f"propensity_floor must be in (0, 0.5); got {floor}")

    t = df[treatment].to_numpy(dtype=float)
    if adjustment:
        Z = df[list(adjustment)].to_numpy(dtype=float)
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(Z, t.astype(int))
        e = clf.predict_proba(Z)[:, 1]
        model = "logistic"
    else:
        e = np.full(len(t), float(t.mean()))
        model = "marginal"

    raw_min = float(e.min())
    raw_max = float(e.max())
    clipped = np.clip(e, floor, 1.0 - floor)
    n_trimmed = int(np.count_nonzero(clipped != e))
    summary = PropensitySummary(
        raw_min=raw_min, raw_max=raw_max, n_trimmed=n_trimmed,
        floor=floor, model=model,
    )
    return clipped, summary


def _outcome_vector(df: pd.DataFrame, outcome: str) -> np.ndarray:
    y = df[outcome].to_numpy()
    if y.dtype == bool:
        y = y.astype(int)
    return y.astype(float)


def _outcome_mu(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    model: str,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Fit E[Y|T,Z] and return (mu1_i, mu0_i, y) — per-unit predictions
    at T=1 and T=0 plus the observed outcome vector."""
    t = df[treatment].to_numpy(dtype=float)[:, None]
    if adjustment:
        Z = df[list(adjustment)].to_numpy(dtype=float)
        X = np.hstack([t, Z])
    else:
        X = t
    y = _outcome_vector(df, outcome)

    if model == "logistic":
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y.astype(int))
        predict = lambda M: clf.predict_proba(M)[:, 1]
    elif model == "linear":
        reg = LinearRegression()
        reg.fit(X, y)
        predict = lambda M: reg.predict(M)
    else:
        raise ValueError(f"unknown outcome model {model!r}")

    X1 = X.copy(); X1[:, 0] = 1.0
    X0 = X.copy(); X0[:, 0] = 0.0
    return predict(X1), predict(X0), y


# --- estimating equations -----------------------------------------------------


def _ipw_point(
    t: np.ndarray, y: np.ndarray, e: np.ndarray, *, stabilized: bool,
) -> float:
    """IPW ATE. Hajek (stabilized) normalizes weights within each arm;
    Horvitz-Thompson divides by n."""
    w1 = t / e
    w0 = (1.0 - t) / (1.0 - e)
    if stabilized:
        m1 = float(np.sum(w1 * y) / np.sum(w1))
        m0 = float(np.sum(w0 * y) / np.sum(w0))
    else:
        n = len(y)
        m1 = float(np.sum(w1 * y) / n)
        m0 = float(np.sum(w0 * y) / n)
    return m1 - m0


def _aipw_pseudo_outcome(
    t: np.ndarray,
    y: np.ndarray,
    e: np.ndarray,
    mu1: np.ndarray,
    mu0: np.ndarray,
) -> np.ndarray:
    """Per-unit AIPW pseudo-outcome phi_i (its mean is the point
    estimate; its centered version is the influence function)."""
    return (
        mu1 - mu0
        + t * (y - mu1) / e
        - (1.0 - t) * (y - mu0) / (1.0 - e)
    )


def _influence_function_se(
    phi: np.ndarray, point: float, groups: np.ndarray | None,
) -> float | None:
    """SE(psi) from the AIPW influence function.

    i.i.d.:      Var(psi) = (1/n^2) Sum_i (phi_i - psi)^2
    clustered:   Var(psi) = (1/n^2) Sum_c ( Sum_{i in c} (phi_i - psi) )^2

    (the cluster-robust sandwich: sum the influence within each cluster
    before squaring, so within-cluster dependence is respected).
    """
    n = len(phi)
    if n == 0:
        return None
    centered = phi - point
    if groups is None:
        var = float(np.sum(centered ** 2) / (n * n))
    else:
        groups = np.asarray(groups)
        codes = pd.factorize(groups, sort=False)[0]
        total = 0.0
        for g in range(codes.max() + 1 if len(codes) else 0):
            s = float(np.sum(centered[codes == g]))
            total += s * s
        var = total / (n * n)
    if var < 0:
        return None
    return float(np.sqrt(var))


# --- bootstrap CIs ------------------------------------------------------------


def _ipw_bootstrap_ci(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    stabilized: bool,
    floor: float,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None,
) -> tuple[float, float]:
    """Percentile bootstrap for IPW, refitting the propensity each draw."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        e_b, _ = _propensity_scores(sample, treatment, adjustment, floor=floor)
        t_b = sample[treatment].to_numpy(dtype=float)
        y_b = _outcome_vector(sample, outcome)
        estimates[i] = _ipw_point(t_b, y_b, e_b, stabilized=stabilized)
    return _percentiles(estimates, ci_level)


def _aipw_bootstrap_ci(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    model: str,
    floor: float,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
    groups: np.ndarray | None,
) -> tuple[float, float]:
    """Percentile bootstrap for AIPW, refitting BOTH nuisances each draw."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx]
        e_b, _ = _propensity_scores(sample, treatment, adjustment, floor=floor)
        t_b = sample[treatment].to_numpy(dtype=float)
        mu1_b, mu0_b, y_b = _outcome_mu(
            sample, treatment, outcome, adjustment, model=model,
        )
        phi_b = _aipw_pseudo_outcome(t_b, y_b, e_b, mu1_b, mu0_b)
        estimates[i] = float(np.mean(phi_b))
    return _percentiles(estimates, ci_level)


def _percentiles(estimates: np.ndarray, ci_level: float) -> tuple[float, float]:
    alpha = (1 - ci_level) / 2
    lo = float(np.quantile(estimates, alpha))
    hi = float(np.quantile(estimates, 1 - alpha))
    return lo, hi


# --- assumption ledgers -------------------------------------------------------


def _assumptions_ipw(
    stabilized: bool, n_adj: int, prop: PropensitySummary, cluster: str | None,
    support: Support,
) -> tuple[str, ...]:
    common: tuple[str, ...] = (
        "conditional_exchangeability_given_adjustment_set",
        overlap_assumption(support),
        "consistency_of_potential_outcomes",
        "correct_propensity_model_single_robust",
    )
    common += (
        "hajek_stabilized_weights" if stabilized else "horvitz_thompson_weights",
    )
    if n_adj == 0:
        common += ("unconditional_exchangeability_treatment_is_marginally_randomized",)
    if prop.n_trimmed:
        common += (f"propensity_clipped_to_floor_{prop.floor}_on_{prop.n_trimmed}",)
    if cluster is not None:
        common += (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return common


def _assumptions_aipw(
    outcome_model: str,
    n_adj: int,
    prop: PropensitySummary,
    cluster: str | None,
    ci_method: str,
    support: Support,
) -> tuple[str, ...]:
    common: tuple[str, ...] = (
        "conditional_exchangeability_given_adjustment_set",
        overlap_assumption(support),
        "consistency_of_potential_outcomes",
        "doubly_robust_outcome_OR_propensity_model_correct",
    )
    common += (
        "logit_outcome_regression" if outcome_model == "logistic"
        else "linear_outcome_regression",
    )
    if n_adj == 0:
        common += ("unconditional_exchangeability_treatment_is_marginally_randomized",)
    if prop.n_trimmed:
        common += (f"propensity_clipped_to_floor_{prop.floor}_on_{prop.n_trimmed}",)
    if ci_method == "influence_function":
        common += ("ci_via_analytic_influence_function",)
        if cluster is not None:
            common += (f"cluster_robust_influence_variance_on_{cluster}",)
    else:
        common += ("ci_via_percentile_bootstrap",)
        if cluster is not None:
            common += (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
    return common


def _maybe_float(x: float | None) -> float | None:
    return float(x) if x is not None else None
