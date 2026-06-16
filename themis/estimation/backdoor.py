"""Phase 7.1 S.N.2 — backdoor-adjusted ATE estimator.

Implements the outcome-regression (plug-in g-formula) estimator for
the average treatment effect ATE = E[Y|do(X=1)] - E[Y|do(X=0)]:

    ATE_hat = (1/n) Σ_i [Ê(Y | X=1, Z=Zi) - Ê(Y | X=0, Z=Zi)]

where Ê is a fitted regression model. Uses sklearn
``LogisticRegression`` for bool outcomes and ``LinearRegression`` for
continuous. Confidence intervals via non-parametric percentile
bootstrap.

The estimator is deterministic given ``random_state`` — bootstrap
resampling uses a seeded numpy Generator.

Reference: Hernan & Robins 2020 ch.13 "Standardization" (the
outcome-regression / g-formula estimator in the non-parametric limit).

API:

    from themis.estimation.backdoor import estimate_backdoor_ate
    est = estimate_backdoor_ate(
        data, treatment="x", outcome="y", adjustment=("z1", "z2"),
    )
    print(est.point, est.ci_lower, est.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data
from .dose_response import EstimatorFailure


ModelName = Literal["auto", "linear", "logistic"]


@dataclass(frozen=True)
class BackdoorEstimate:
    """Result of a backdoor-adjusted ATE estimate."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                # "backdoor_linear" | "backdoor_logistic"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    treatment: str
    outcome: str
    # Mechanism (functional form = outcome regression model) + structured
    # identification assumptions, surfaced for the assumption-ledger
    # (parity with the dose-response estimator).
    model_assumption: str = ""
    form: str = ""
    identification_assumptions: tuple[dict, ...] = ()


def estimate_backdoor_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    model: ModelName = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> BackdoorEstimate:
    """Backdoor-adjusted ATE via outcome regression + bootstrap CI.

    Parameters
    ----------
    data: pandas DataFrame containing treatment / outcome / adjustment
        columns.
    treatment: column name of the binary treatment variable.
    outcome: column name of the outcome variable (bool or continuous).
    adjustment: tuple of adjustment set column names (may be empty).
    model: 'auto' picks logistic for bool outcome and linear otherwise;
        'linear' / 'logistic' force the choice.
    ci_bootstrap: number of bootstrap resamples; 0 skips CI.
    ci_level: two-sided confidence level (default 0.95).
    random_state: deterministic seed.

    Returns
    -------
    BackdoorEstimate with point / ci_lower / ci_upper / method / etc.
    """
    required = {treatment, outcome, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    # Positivity / overlap precondition. A backdoor ATE is a contrast
    # between the treated and control arms; if the treatment column has a
    # single observed level there is NO contrast in the data. The g-formula
    # would then predict the absent arm by extrapolating a zero-variance
    # regressor and return a falsely-precise "effect" (e.g. 0.05 ± 0.01
    # from data where X is never False). Refuse rather than fabricate —
    # this is the maximal positivity violation, the "overlap limit" the
    # public ``estimate`` contract documents EstimatorFailure for.
    observed_levels = df[treatment].dropna().unique()
    if len(observed_levels) < 2:
        raise EstimatorFailure(
            "overlap_insufficient",
            f"treatment {treatment!r} has a single observed level "
            f"({observed_levels.tolist()}) in the data — positivity is "
            f"maximally violated and there is no treatment contrast to "
            f"estimate. A backdoor ATE needs both treated and control "
            f"units; supply data with variation in {treatment!r}, or use a "
            f"design (RCT / IV) that creates the contrast.",
            treatment=treatment,
        )

    outcome_series = df[outcome]
    is_bool_outcome = pd.api.types.is_bool_dtype(outcome_series)

    if model == "auto":
        resolved = "logistic" if is_bool_outcome else "linear"
    else:
        resolved = model

    method = f"backdoor_{resolved}"

    X_full, y = _design(df, treatment, outcome, adjustment)

    point = _point_estimate(
        X_full, y, df[treatment].to_numpy(dtype=bool),
        adjustment_offset=1, model=resolved,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci(
            df, treatment, outcome, adjustment,
            model=resolved, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state,
        )

    assumptions = _assumptions_for(resolved, len(adjustment))
    # Structured for the assumption-ledger: identification assumptions
    # (invalidating) separated from the functional-form choice (the
    # outcome regression model -> mechanism_audit, distorting).
    identification_assumptions = (
        {"claim": "给定调整集无未观测混杂（条件可交换性）",
         "layer": "identification", "severity": "invalidating", "testable": False},
        {"claim": "重叠 / positivity：每个调整集层内处理组与对照组都有样本",
         "layer": "identification", "severity": "invalidating", "testable": False},
        {"claim": "一致性：干预定义明确，potential outcomes 良定义",
         "layer": "identification", "severity": "invalidating", "testable": False},
    )
    if len(adjustment) == 0:
        identification_assumptions += (
            {"claim": "无条件可交换性：处理近似边际随机化（无需调整）",
             "layer": "identification", "severity": "invalidating", "testable": False},
        )
    model_assumption = (
        "outcome 用 logistic 回归建模（假设给定调整集 logit 线性）"
        if resolved == "logistic"
        else "outcome 用 linear 回归建模（假设给定调整集线性）"
    )
    return BackdoorEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        treatment=treatment,
        outcome=outcome,
        model_assumption=model_assumption,
        form=resolved,
        identification_assumptions=identification_assumptions,
    )


# --- internals ----------------------------------------------------------------


def _design(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray]:
    """Build the design matrix [treatment | adjustment] and outcome vector."""
    t_col = df[treatment].to_numpy(dtype=float)[:, None]
    if adjustment:
        z = df[list(adjustment)].to_numpy(dtype=float)
        X = np.hstack([t_col, z])
    else:
        X = t_col
    y = df[outcome].to_numpy()
    if y.dtype == bool:
        y = y.astype(int)
    return X, y


def _fit_predict(X: np.ndarray, y: np.ndarray, model: str):
    """Fit the requested model on (X, y) and return a callable p(X) -> yhat."""
    if model == "logistic":
        # LogisticRegression on binary y returns P(y=1 | X).
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y)
        return lambda X_new: clf.predict_proba(X_new)[:, 1]
    if model == "linear":
        reg = LinearRegression()
        reg.fit(X, y)
        return lambda X_new: reg.predict(X_new)
    raise ValueError(f"unknown model {model!r}")


def _point_estimate(
    X_full: np.ndarray,
    y: np.ndarray,
    treatment_vec: np.ndarray,  # unused; kept for future CATE support
    *,
    adjustment_offset: int,
    model: str,
) -> float:
    """g-formula ATE: average over observed Z of Ê(Y|X=1,Z) - Ê(Y|X=0,Z)."""
    predict = _fit_predict(X_full, y, model)

    # Build counterfactual X matrices (force column 0 to 1 / 0)
    X_treated = X_full.copy()
    X_treated[:, 0] = 1.0
    X_control = X_full.copy()
    X_control[:, 0] = 0.0

    y_hat_1 = predict(X_treated)
    y_hat_0 = predict(X_control)
    return float(np.mean(y_hat_1 - y_hat_0))


def _bootstrap_ci(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    *,
    model: str,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
) -> tuple[float, float]:
    """Non-parametric percentile bootstrap CI on the ATE."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = df.iloc[idx]
        X_b, y_b = _design(sample, treatment, outcome, adjustment)
        estimates[i] = _point_estimate(
            X_b, y_b, sample[treatment].to_numpy(dtype=bool),
            adjustment_offset=1, model=model,
        )

    alpha = (1 - ci_level) / 2
    lo = float(np.quantile(estimates, alpha))
    hi = float(np.quantile(estimates, 1 - alpha))
    return lo, hi


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    """Canonical assumption list for this estimator + model choice."""
    common = (
        "conditional_exchangeability_given_adjustment_set",
        "positivity_overlap_of_treatment_arms",
        "consistency_of_potential_outcomes",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logistic":
        common = common + ("logit_outcome_regression",)
    if n_adj == 0:
        common = common + (
            "unconditional_exchangeability_treatment_is_marginally_randomized",
        )
    return common
