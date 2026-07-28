"""Phase 7.L — g-methods for TIME-VARYING treatments: the longitudinal
(parametric) g-formula / g-computation.

Themis's other estimators (``backdoor`` / ``frontdoor`` / ``iv`` /
``mediation``) are all CROSS-SECTIONAL — a single treatment time point.
They cannot answer the canonical longitudinal question:

    What is the effect of a treatment STRATEGY (always-treat vs
    never-treat) when a TIME-VARYING CONFOUNDER is itself AFFECTED BY
    PAST TREATMENT?

That structure (L_k affected by A_{k-1}, affecting A_k and Y) is exactly
where ordinary outcome regression that adjusts for L_k is BIASED: L_k
sits ON the causal path A_{k-1} -> L_k -> Y, so conditioning on it blocks
the indirect effect (and, when an unmeasured U drives L_k and Y, opens a
collider). This is the entire reason g-methods exist
(Hernán & Robins, *Causal Inference: What If*, Part III, ch.21
"G-methods for time-varying treatments" — the parametric g-formula).

Method — parametric g-computation (Monte-Carlo g-formula), H&R ch.21:

    1.  Order the variables in time:  L_0, A_0, L_1, A_1, ..., L_K, A_K, Y.
    2.  Estimate the joint distribution of the baseline covariates L_0
        NON-parametrically by its empirical distribution (row resampling).
    3.  For each later time k>=1 fit a PARAMETRIC transition model for
        each covariate  L_k | (history of L's and A's up to A_{k-1}).
    4.  Fit the outcome model  Y | (full L and A history).
    5.  Monte-Carlo simulate forward under a fixed treatment STRATEGY
        (set every A_k to the strategy value), drawing each L_k from its
        fitted transition model, then average the fitted outcome:
            E[Y_{ā}] ≈ (1/n_sim) Σ Ê[Y | simulated history under ā].
    6.  Contrast the two strategies:
            ψ = E[Y_{ā=1}] − E[Y_{ā=0}].

Confidence interval: non-parametric percentile bootstrap — resample
SUBJECTS (rows), refit every model, re-simulate, recompute ψ. A subject
row is the unit of independence only when subjects are independent; when
they are nested (clinics, schools, families), ``cluster`` names that
column and the draw becomes a pairs cluster bootstrap over whole
clusters, exactly as in the cross-sectional estimators.

Deterministic given ``random_state`` (one seeded numpy Generator drives
baseline resampling, covariate-transition noise, and the bootstrap).

Binary treatment, continuous-or-binary covariates / outcome, K time
points. Covariate transition + outcome models are linear (continuous) /
logistic (binary) — the "correct model specification" assumption is the
price of the parametric g-formula, surfaced in ``assumptions``.

API::

    from themis.estimation.longitudinal import estimate_longitudinal_gformula
    est = estimate_longitudinal_gformula(
        data,
        treatments=("A0", "A1"),
        confounders_by_time=(("L0",), ("L1",)),
        outcome="Y",
    )
    print(est.point, est.ci_lower, est.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class LongitudinalGFormulaEstimate:
    """Result of a longitudinal parametric g-formula estimate.

    ``point`` is the strategy contrast  E[Y_{ā=treated}] − E[Y_{ā=control}].
    ``e_y_treated`` / ``e_y_control`` expose the two simulated strategy
    means so a consumer can sanity-check the contrast.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str  # always "longitudinal_gformula"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    treatments: tuple[str, ...]
    confounders_by_time: tuple[tuple[str, ...], ...]
    outcome: str
    strategy_treated: float
    strategy_control: float
    n_sim: int
    n_bootstrap: int
    e_y_treated: float
    e_y_control: float
    # The cluster column the bootstrap ACTUALLY resampled over (None =
    # i.i.d. rows). Reported back rather than echoed from the caller's
    # request, so a consumer that stamps "this interval is cluster-robust"
    # is stamping what happened, not what was asked for.
    cluster: str | None = None


def estimate_longitudinal_gformula(
    data: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
    strategy_treated: float = 1,
    strategy_control: float = 0,
    n_sim: int = 10_000,
    ci_bootstrap: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> LongitudinalGFormulaEstimate:
    """Parametric g-formula for a time-varying treatment strategy.

    Parameters
    ----------
    data: DataFrame with one row per subject; columns hold every
        treatment, every time-varying covariate, and the outcome.
    treatments: ordered tuple ``(A_0, ..., A_K)`` of binary treatment
        column names, earliest first.
    confounders_by_time: tuple of length ``K+1`` parallel to
        ``treatments``. ``confounders_by_time[k]`` lists the covariates
        measured at time k — AFTER A_{k-1} and BEFORE A_k. Index 0 holds
        the baseline covariates L_0 (before any treatment); any inner
        tuple may be empty.
    outcome: outcome column name (continuous or binary), measured after
        the last treatment.
    strategy_treated / strategy_control: the value every treatment is set
        to under the two contrasted strategies (1 vs 0 by default).
    n_sim: Monte-Carlo subjects simulated per strategy.
    ci_bootstrap: subject-resampling bootstrap reps; 0 skips the CI.
    ci_level: two-sided confidence level for the percentile CI.
    random_state: deterministic seed.
    cluster: optional column naming the level at which subjects are
        independent (clinic, school, family). The bootstrap then draws
        whole clusters with replacement instead of i.i.d. rows; the
        column itself never enters any model or the data hash.

    Returns
    -------
    LongitudinalGFormulaEstimate.

    Raises
    ------
    EstimatorFailure('overlap_insufficient') if any treatment column has
        a single observed level (maximal positivity violation — there is
        no treated/untreated contrast to learn the outcome model from).
    ValueError on a malformed spec (length mismatch, unknown column).
    """
    if len(treatments) == 0:
        raise ValueError("treatments must be non-empty")
    if len(confounders_by_time) != len(treatments):
        raise ValueError(
            "confounders_by_time must have the same length as treatments "
            f"({len(confounders_by_time)} != {len(treatments)})"
        )

    treatments = tuple(treatments)
    confounders_by_time = tuple(tuple(c) for c in confounders_by_time)

    all_confounders = tuple(c for block in confounders_by_time for c in block)
    required = {*treatments, *all_confounders, outcome}
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data
    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    # Positivity / overlap precondition, mirrored from the cross-sectional
    # backdoor estimator: a strategy contrast forces each A_k to treated /
    # control, so the outcome + transition models must have seen BOTH
    # levels of every treatment. A single-level treatment column means the
    # simulated counterfactual arm is pure extrapolation.
    for a in treatments:
        levels = df[a].dropna().unique()
        if len(levels) < 2:
            raise EstimatorFailure(
                "overlap_insufficient",
                f"treatment {a!r} has a single observed level "
                f"({levels.tolist()}) — positivity is maximally violated "
                f"and the g-formula would extrapolate the absent arm. "
                f"Supply data with variation in every treatment.",
                treatment=a,
            )

    rng = np.random.default_rng(random_state)

    e_y_treated, e_y_control = _g_formula_contrast(
        df,
        treatments=treatments,
        confounders_by_time=confounders_by_time,
        outcome=outcome,
        strategy_treated=float(strategy_treated),
        strategy_control=float(strategy_control),
        n_sim=n_sim,
        rng=rng,
    )
    point = e_y_treated - e_y_control

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df,
            treatments=treatments,
            confounders_by_time=confounders_by_time,
            outcome=outcome,
            strategy_treated=float(strategy_treated),
            strategy_control=float(strategy_control),
            n_sim=n_sim,
            ci_bootstrap=ci_bootstrap,
            ci_level=ci_level,
            rng=rng,
            groups=groups,
        )

    assumptions = (
        # Identification assumptions (H&R ch.21) — untestable from data:
        "sequential_exchangeability_no_unmeasured_time_varying_confounding",
        "positivity_each_treatment_level_observed_within_history_strata",
        "consistency_well_defined_sustained_treatment_strategy",
        # The price of the PARAMETRIC g-formula (vs nonparametric):
        "correct_specification_of_covariate_transition_and_outcome_models",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return LongitudinalGFormulaEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="longitudinal_gformula",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatments=treatments,
        confounders_by_time=confounders_by_time,
        outcome=outcome,
        strategy_treated=float(strategy_treated),
        strategy_control=float(strategy_control),
        n_sim=n_sim,
        n_bootstrap=ci_bootstrap,
        e_y_treated=float(e_y_treated),
        e_y_control=float(e_y_control),
        cluster=cluster,
    )


# ==========================================================================
# IPW-MSM — marginal structural model via inverse-probability-of-treatment
# weighting (Robins 2000; Hernán & Robins, What If, ch.12 & ch.17)
# ==========================================================================


@dataclass(frozen=True)
class LongitudinalIPWMSMEstimate:
    """Result of a longitudinal IPW marginal-structural-model estimate.

    An INDEPENDENT route to the same estimand the g-formula targets — the
    time-varying treatment strategy contrast E[Y_{ā=treated}] −
    E[Y_{ā=control}] — computed by re-weighting the observed population by
    the inverse probability of the treatment actually received, then
    fitting a marginal structural (mean) model on the pseudo-population.
    Where the g-formula MODELS the covariate transitions + outcome, the
    MSM models the TREATMENT process instead, so the two are misspecified
    in different ways: agreement between them is strong evidence the
    estimate is right (Hernán & Robins ch.21).

    ``msm_coefficients`` are the per-time treatment coefficients β_k of the
    marginal structural mean model E[Y_{ā}] = β0 + Σ_k β_k·a_k; the contrast
    is (treated−control)·Σ_k β_k. ``weight_mean`` / ``weight_max`` disclose
    the weight distribution — a mean far from 1 (stabilized) or a huge max
    signals a near-positivity violation the point estimate can't fix.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str  # always "longitudinal_ipw_msm"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    treatments: tuple[str, ...]
    confounders_by_time: tuple[tuple[str, ...], ...]
    outcome: str
    strategy_treated: float
    strategy_control: float
    stabilized: bool
    e_y_treated: float
    e_y_control: float
    msm_coefficients: tuple[float, ...]   # (β0, β_{A0}, ..., β_{AK})
    weight_mean: float
    weight_max: float
    n_bootstrap: int
    cluster: str | None = None  # see LongitudinalGFormulaEstimate.cluster


def estimate_longitudinal_ipw_msm(
    data: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
    strategy_treated: float = 1,
    strategy_control: float = 0,
    stabilized: bool = True,
    ci_bootstrap: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> LongitudinalIPWMSMEstimate:
    """IPW marginal structural model for a time-varying treatment strategy.

    Same spec as :func:`estimate_longitudinal_gformula` (subject-per-row
    frame, time-ordered ``treatments`` and ``confounders_by_time``). At each
    time k a logistic treatment model P(A_k=1 | history through L_k, A_{<k})
    supplies the DENOMINATOR of the IP weight; the (stabilized) NUMERATOR is
    P(A_k=1 | past treatments only). Each subject's weight is the product
    over time of numerator/denominator (or 1/denominator when
    ``stabilized=False``). A weighted least-squares marginal structural
    mean model ``E[Y_{ā}] = β0 + Σ_k β_k·a_k`` is then fit on the
    pseudo-population; the strategy contrast is
    ``(strategy_treated − strategy_control)·Σ_k β_k``.

    The MSM is a MAIN-EFFECTS mean model (no treatment×treatment
    interaction term) — correctly specified when per-time effects are
    additive; that assumption is surfaced in ``assumptions``. CI is a
    subject (row) percentile bootstrap: refit every propensity model,
    recompute weights, refit the MSM — or a pairs cluster bootstrap over
    whole clusters when ``cluster`` names the level of independence.

    Raises ``EstimatorFailure('overlap_insufficient')`` if any treatment
    column has a single observed level; ``ValueError`` on a malformed spec.
    """
    if len(treatments) == 0:
        raise ValueError("treatments must be non-empty")
    if len(confounders_by_time) != len(treatments):
        raise ValueError(
            "confounders_by_time must have the same length as treatments "
            f"({len(confounders_by_time)} != {len(treatments)})"
        )

    treatments = tuple(treatments)
    confounders_by_time = tuple(tuple(c) for c in confounders_by_time)
    all_confounders = tuple(c for block in confounders_by_time for c in block)
    required = {*treatments, *all_confounders, outcome}
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data
    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    for a in treatments:
        levels = df[a].dropna().unique()
        if len(levels) < 2:
            raise EstimatorFailure(
                "overlap_insufficient",
                f"treatment {a!r} has a single observed level "
                f"({levels.tolist()}) — positivity is maximally violated and "
                f"the IP weight for the absent arm is undefined. Supply data "
                f"with variation in every treatment.",
                treatment=a,
            )

    point, e1, e0, betas, w_mean, w_max = _ipw_msm_contrast(
        df,
        treatments=treatments,
        confounders_by_time=confounders_by_time,
        outcome=outcome,
        strategy_treated=float(strategy_treated),
        strategy_control=float(strategy_control),
        stabilized=stabilized,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = resample_indices(n, rng, groups=groups)
            sample = df.iloc[idx].reset_index(drop=True)
            try:
                pt, *_ = _ipw_msm_contrast(
                    sample,
                    treatments=treatments,
                    confounders_by_time=confounders_by_time,
                    outcome=outcome,
                    strategy_treated=float(strategy_treated),
                    strategy_control=float(strategy_control),
                    stabilized=stabilized,
                )
            except (ValueError, np.linalg.LinAlgError):
                pt = np.nan
            draws[i] = pt
        draws = draws[np.isfinite(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    assumptions = (
        "sequential_exchangeability_no_unmeasured_time_varying_confounding",
        "positivity_each_treatment_level_observed_within_history_strata",
        "consistency_well_defined_sustained_treatment_strategy",
        # The price of IPW-MSM (vs the g-formula's outcome/transition models):
        "correct_specification_of_treatment_propensity_models",
        "marginal_structural_model_additive_no_treatment_time_interaction",
    )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return LongitudinalIPWMSMEstimate(
        point=float(point),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method="longitudinal_ipw_msm",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatments=treatments,
        confounders_by_time=confounders_by_time,
        outcome=outcome,
        strategy_treated=float(strategy_treated),
        strategy_control=float(strategy_control),
        stabilized=stabilized,
        e_y_treated=float(e1),
        e_y_control=float(e0),
        msm_coefficients=tuple(float(b) for b in betas),
        weight_mean=float(w_mean),
        weight_max=float(w_max),
        n_bootstrap=ci_bootstrap,
        cluster=cluster,
    )


# --- internals ----------------------------------------------------------------


def _is_binary(series: pd.Series) -> bool:
    """A column is treated as binary iff it's bool dtype (the data
    contract coerces every bool-like column to bool) — everything else
    is modelled as continuous."""
    return pd.api.types.is_bool_dtype(series)


def _to_float_matrix(df: pd.DataFrame, cols: list[str]) -> np.ndarray:
    """Design matrix as float64 (bool -> 0.0/1.0). Empty cols -> (n, 0)."""
    if not cols:
        return np.empty((len(df), 0), dtype=float)
    return df[cols].to_numpy(dtype=float)


class _ColumnModel:
    """A fitted conditional model  target | features, with a draw() that
    samples the target given a simulated-history frame.

    - binary target  -> logistic; draw() ~ Bernoulli(P(target=1|features))
    - continuous      -> linear;   draw() ~ N(mean, residual_sd)
    - no features (baseline-marginal degenerate case) -> empirical resample
    """

    def __init__(self, df: pd.DataFrame, target: str, features: list[str]):
        self.target = target
        self.features = list(features)
        self.binary = _is_binary(df[target])
        self._empirical = df[target].to_numpy()  # for the no-feature fallback

        y = df[target].to_numpy(dtype=float)
        X = _to_float_matrix(df, self.features)

        if not self.features:
            self.model = None  # sample from empirical marginal
            self.resid_sd = 0.0
            return

        if self.binary:
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X, y.astype(int))
            self.model = clf
            self.resid_sd = 0.0
        else:
            reg = LinearRegression()
            reg.fit(X, y)
            self.model = reg
            resid = y - reg.predict(X)
            # ddof = #params (intercept + slopes) for an unbiased-ish sigma
            dof = max(len(y) - (X.shape[1] + 1), 1)
            self.resid_sd = float(np.sqrt(np.sum(resid**2) / dof))

    def draw(self, sim: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
        """Sample the target column for every simulated subject."""
        n = len(sim)
        if self.model is None:
            return rng.choice(self._empirical, size=n, replace=True)
        X = _to_float_matrix(sim, self.features)
        if self.binary:
            p = self.model.predict_proba(X)[:, 1]
            return (rng.random(n) < p).astype(float)
        mean = self.model.predict(X)
        if self.resid_sd > 0:
            return mean + rng.normal(0.0, self.resid_sd, size=n)
        return mean

    def predict_mean(self, sim: pd.DataFrame) -> float:
        """E[target | simulated history], averaged over subjects — used
        for the OUTCOME node (no noise needed, we only want the mean)."""
        if self.model is None:
            return float(np.mean(self._empirical))
        X = _to_float_matrix(sim, self.features)
        if self.binary:
            return float(self.model.predict_proba(X)[:, 1].mean())
        return float(self.model.predict(X).mean())


def _fit_models(
    df: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
) -> tuple[list[tuple[int, str, _ColumnModel]], _ColumnModel, list[str]]:
    """Fit every covariate-transition model (k>=1) plus the outcome model.

    Returns
    -------
    transition_models : list of (time_index, covariate_name, model) for
        covariates at times k>=1, in temporal order.
    outcome_model : the Y | full-history model.
    baseline_cols : the L_0 columns (sampled empirically, not modelled).
    """
    history: list[str] = []
    transition_models: list[tuple[int, str, _ColumnModel]] = []

    K = len(treatments) - 1
    baseline_cols = list(confounders_by_time[0])

    for k in range(K + 1):
        if k >= 1:
            for cov in confounders_by_time[k]:
                model = _ColumnModel(df, cov, list(history))
                transition_models.append((k, cov, model))
                history.append(cov)
        else:
            # Baseline covariates: sampled empirically as a joint block,
            # but they ARE part of the history feeding later models.
            history.extend(baseline_cols)
        history.append(treatments[k])

    outcome_model = _ColumnModel(df, outcome, list(history))
    return transition_models, outcome_model, baseline_cols


def _g_formula_contrast(
    df: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
    strategy_treated: float,
    strategy_control: float,
    n_sim: int,
    rng: np.random.Generator,
) -> tuple[float, float]:
    """Fit models once, then simulate forward under each strategy."""
    transition_models, outcome_model, baseline_cols = _fit_models(
        df,
        treatments=treatments,
        confounders_by_time=confounders_by_time,
        outcome=outcome,
    )
    e_treated = _simulate_strategy(
        df, treatments, transition_models, outcome_model, baseline_cols,
        strategy_value=strategy_treated, n_sim=n_sim, rng=rng,
    )
    e_control = _simulate_strategy(
        df, treatments, transition_models, outcome_model, baseline_cols,
        strategy_value=strategy_control, n_sim=n_sim, rng=rng,
    )
    return e_treated, e_control


def _simulate_strategy(
    df: pd.DataFrame,
    treatments: tuple[str, ...],
    transition_models: list[tuple[int, str, _ColumnModel]],
    outcome_model: _ColumnModel,
    baseline_cols: list[str],
    *,
    strategy_value: float,
    n_sim: int,
    rng: np.random.Generator,
) -> float:
    """Monte-Carlo forward simulation under a single fixed strategy
    (every treatment set to ``strategy_value``)."""
    n = len(df)
    sim = pd.DataFrame(index=range(n_sim))

    # 1. Baseline covariates L_0 ~ empirical joint distribution.
    if baseline_cols:
        idx = rng.integers(0, n, size=n_sim)
        base = df[baseline_cols].to_numpy()[idx]
        for j, col in enumerate(baseline_cols):
            sim[col] = base[:, j]

    # 2. Walk forward in time: draw each L_k from its transition model,
    #    then SET A_k to the strategy value.
    by_time: dict[int, list[tuple[str, _ColumnModel]]] = {}
    for k, cov, model in transition_models:
        by_time.setdefault(k, []).append((cov, model))

    K = len(treatments) - 1
    for k in range(K + 1):
        for cov, model in by_time.get(k, []):
            sim[cov] = model.draw(sim, rng)
        sim[treatments[k]] = strategy_value

    # 3. Average the fitted outcome over the simulated population.
    return outcome_model.predict_mean(sim)


def _bootstrap_ci(
    df: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
    strategy_treated: float,
    strategy_control: float,
    n_sim: int,
    ci_bootstrap: int,
    ci_level: float,
    rng: np.random.Generator,
    groups: np.ndarray | None = None,
) -> tuple[float, float]:
    """Non-parametric percentile bootstrap over SUBJECTS (rows): refit
    every model on each resample, re-simulate, recompute the contrast.

    ``groups`` switches the draw to whole clusters; ``None`` reproduces
    the i.i.d. row draw exactly (same rng consumption)."""
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sample = df.iloc[idx].reset_index(drop=True)
        e1, e0 = _g_formula_contrast(
            sample,
            treatments=treatments,
            confounders_by_time=confounders_by_time,
            outcome=outcome,
            strategy_treated=strategy_treated,
            strategy_control=strategy_control,
            n_sim=n_sim,
            rng=rng,
        )
        estimates[i] = e1 - e0

    alpha = (1 - ci_level) / 2
    lo = float(np.quantile(estimates, alpha))
    hi = float(np.quantile(estimates, 1 - alpha))
    return lo, hi


# --- IPW-MSM internals --------------------------------------------------------

_PROP_EPS = 1e-6  # clip propensities off {0,1} so the IP weight stays finite


def _propensity_p1(df: pd.DataFrame, target: str, features: list[str]) -> np.ndarray:
    """P(target=1 | features) for every row. Empty features → the marginal
    proportion (an intercept-only model). Probabilities are clipped to
    ``[eps, 1-eps]`` so a reciprocal in the IP weight can't blow up."""
    n = len(df)
    a = df[target].to_numpy(dtype=float)
    if not features:
        p = np.full(n, float(a.mean()))
    else:
        X = _to_float_matrix(df, features)
        y = a.astype(int)
        if len(np.unique(y)) < 2:
            # Degenerate arm in this (bootstrap) frame — fall back to the
            # marginal so the weight stays defined rather than raising.
            p = np.full(n, float(a.mean()))
        else:
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X, y)
            p = clf.predict_proba(X)[:, 1]
    return np.clip(p, _PROP_EPS, 1.0 - _PROP_EPS)


def _ip_weights(
    df: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    stabilized: bool,
) -> np.ndarray:
    """Per-subject IP-of-treatment weight, the product over time of
    numerator/denominator (stabilized) or 1/denominator (unstabilized).

    Denominator at time k: P(A_k = a_k | L_0..L_k, A_0..A_{k-1}) — the full
    time-varying history before A_k. Numerator (stabilized): P(A_k = a_k |
    A_0..A_{k-1}) — past treatment only, so the marginal treatment process
    cancels and the MSM stays fully marginal (only the treatments enter).
    """
    n = len(df)
    num = np.ones(n)
    den = np.ones(n)
    history: list[str] = []
    for k in range(len(treatments)):
        # L_k is measured before A_k → part of the denominator history.
        history.extend(confounders_by_time[k])
        a_k = df[treatments[k]].to_numpy(dtype=float)
        p_den = _propensity_p1(df, treatments[k], list(history))
        den *= np.where(a_k == 1.0, p_den, 1.0 - p_den)
        if stabilized:
            past_treatments = [treatments[j] for j in range(k)]
            p_num = _propensity_p1(df, treatments[k], past_treatments)
            num *= np.where(a_k == 1.0, p_num, 1.0 - p_num)
        history.append(treatments[k])
    return (num / den) if stabilized else (1.0 / den)


def _ipw_msm_contrast(
    df: pd.DataFrame,
    *,
    treatments: tuple[str, ...],
    confounders_by_time: tuple[tuple[str, ...], ...],
    outcome: str,
    strategy_treated: float,
    strategy_control: float,
    stabilized: bool,
) -> tuple[float, float, float, np.ndarray, float, float]:
    """Fit the propensities, weight, and fit the weighted marginal
    structural mean model. Returns
    ``(contrast, e_y_treated, e_y_control, betas, weight_mean, weight_max)``.
    """
    w = _ip_weights(
        df, treatments=treatments,
        confounders_by_time=confounders_by_time, stabilized=stabilized,
    )
    # Marginal structural mean model: E[Y_{ā}] = β0 + Σ_k β_k·a_k, fit by
    # weighted least squares (numpy normal equations via the sqrt-weight
    # trick — no statsmodels, to keep the native footprint small).
    n = len(df)
    a_cols = [df[t].to_numpy(dtype=float) for t in treatments]
    design = np.column_stack([np.ones(n), *a_cols])
    y = df[outcome].to_numpy(dtype=float)
    sw = np.sqrt(w)
    betas, *_ = np.linalg.lstsq(design * sw[:, None], y * sw, rcond=None)
    beta0 = betas[0]
    beta_treat = betas[1:]  # per-time treatment coefficients
    sum_beta = float(np.sum(beta_treat))
    e_y_treated = float(beta0 + strategy_treated * sum_beta)
    e_y_control = float(beta0 + strategy_control * sum_beta)
    contrast = (strategy_treated - strategy_control) * sum_beta
    return (float(contrast), e_y_treated, e_y_control, betas,
            float(np.mean(w)), float(np.max(w)))
