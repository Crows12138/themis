"""Phase 7.2 S.FDN.1 — front-door adjusted ATE estimator.

Implements Pearl's front-door formula (Pearl 2009 Eq. 3.29) as a
plug-in estimator:

    P(Y | do(X=x)) = ∑_z P(Z=z | X=x) · ∑_{x'} P(Y | X=x', Z=z) · P(X=x')

ATE = E[Y | do(X=1)] - E[Y | do(X=0)].

Fits two conditional models via sklearn:
- ``P(Z | X)`` — linear / logistic on each mediator
- ``P(Y | X, Z)`` — linear / logistic on the outcome

Then combines them with the empirical marginal P(X).

Generalises to multi-mediator via the topological chain-rule
factoring (matches Phase 6.front-door-multi's identification-layer
formula):

    P(Z1, ..., Zk | X) = ∏_i P(Zi | Z_{<i}, X)

API:

    from themis.estimation.frontdoor import estimate_frontdoor_ate
    est = estimate_frontdoor_ate(
        data, treatment="x", outcome="y",
        mediators=("m1", "m2"),  # topological order
    )

First version: binary treatment + bool-or-continuous outcome, bool
mediators (so the outer sum has 2^k terms). Continuous-mediator
extension is deferred until a real case asks for it.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression, LogisticRegression

from .contract import validate_data


ModelName = Literal["auto", "linear", "logistic"]


@dataclass(frozen=True)
class FrontdoorEstimate:
    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                   # "frontdoor_linear" | "frontdoor_logistic"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    mediators: tuple[str, ...]
    treatment: str
    outcome: str


def estimate_frontdoor_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    model: ModelName = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> FrontdoorEstimate:
    """Front-door-adjusted ATE via plug-in Pearl Eq 3.29 + bootstrap CI.

    See module docstring for the formula + assumptions. Mediators
    must be passed in topological order (matching the scheduler's
    ``front_door_sets`` output).
    """
    if not mediators:
        raise ValueError("estimate_frontdoor_ate requires >=1 mediator")

    required = {treatment, outcome, *mediators}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    outcome_series = df[outcome]
    is_bool_outcome = pd.api.types.is_bool_dtype(outcome_series)
    resolved = (
        ("logistic" if is_bool_outcome else "linear")
        if model == "auto" else model
    )
    method = f"frontdoor_{resolved}"

    point = _point_estimate_frontdoor(
        df, treatment, outcome, mediators, model=resolved,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_frontdoor(
            df, treatment, outcome, mediators,
            model=resolved, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state,
        )

    return FrontdoorEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method=method,
        assumptions=_assumptions_for(resolved, len(mediators)),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        mediators=tuple(mediators),
        treatment=treatment,
        outcome=outcome,
    )


# --- internals ----------------------------------------------------------------


def _point_estimate_frontdoor(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    *,
    model: str,
) -> float:
    """Evaluate Pearl Eq 3.29 on the fitted conditionals.

    For bool mediators (first-version restriction), the outer sum
    ranges over the 2^k cross-product of mediator values. We compute
    ``∑_z P(Z=z|X=x) · ∑_x' P(Y|X=x',Z=z) · P(X=x')`` for each
    do(X) arm, then return the difference.
    """
    # All mediators must be bool in the first version — check & coerce
    for m in mediators:
        if not pd.api.types.is_bool_dtype(df[m]):
            raise NotImplementedError(
                f"front-door estimator v1 only supports bool mediators; "
                f"mediator {m!r} has dtype {df[m].dtype}"
            )

    n = len(df)
    x_arr = df[treatment].to_numpy(dtype=float).reshape(-1, 1)  # n x 1
    y_arr = df[outcome].to_numpy()
    if y_arr.dtype == bool:
        y_arr = y_arr.astype(int)

    # Fit P(Y | X, Z) — single model on (x, z1, ..., zk)
    z_arr = df[list(mediators)].to_numpy(dtype=float)
    xz = np.hstack([x_arr, z_arr])
    predict_y = _fit_predict(xz, y_arr, model)

    # Fit P(Z | X) via chain rule — each Zi as logistic on (X, Z_{<i})
    # (mediators are bool → logistic is the only sensible choice)
    chain_predictors: list = []  # list of callables: (X_arr, Z_prior_arr) -> prob Zi=1
    for i, m in enumerate(mediators):
        zi_target = df[m].to_numpy().astype(int)
        # Features: X and prior mediators' values
        prior_arr = df[list(mediators[:i])].to_numpy(dtype=float) if i > 0 else None
        if prior_arr is None:
            feats = x_arr
        else:
            feats = np.hstack([x_arr, prior_arr])
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(feats, zi_target)
        chain_predictors.append(clf)

    # Empirical P(X) — treatment prevalence
    p_x1 = float(df[treatment].mean())
    p_x0 = 1.0 - p_x1

    def p_z_given_x(z_values: np.ndarray, x_value: float) -> float:
        """Joint conditional P(Z1=z1,...,Zk=zk | X=x) via chain rule."""
        acc = 1.0
        for i, m in enumerate(mediators):
            prior = z_values[:i] if i > 0 else np.array([])
            if i == 0:
                feats = np.array([[x_value]])
            else:
                feats = np.hstack([[[x_value]], prior.reshape(1, -1)])
            proba = chain_predictors[i].predict_proba(feats)[0, 1]
            zi = z_values[i]
            acc *= proba if zi == 1 else (1 - proba)
        return float(acc)

    def inner_marginalise(z_values: np.ndarray) -> float:
        """∑_x' P(Y | X=x', Z=z) · P(X=x')."""
        feats1 = np.array([[1.0, *z_values]])
        feats0 = np.array([[0.0, *z_values]])
        y_at_1 = float(predict_y(feats1)[0])
        y_at_0 = float(predict_y(feats0)[0])
        return y_at_1 * p_x1 + y_at_0 * p_x0

    # Cross-product of bool mediator values
    def do_arm(x_arm: float) -> float:
        total = 0.0
        for mask in range(2 ** len(mediators)):
            z_values = np.array(
                [(mask >> i) & 1 for i in range(len(mediators))],
                dtype=float,
            )
            weight = p_z_given_x(z_values, x_arm)
            total += weight * inner_marginalise(z_values)
        return total

    return do_arm(1.0) - do_arm(0.0)


def _fit_predict(X: np.ndarray, y: np.ndarray, model: str):
    if model == "logistic":
        clf = LogisticRegression(max_iter=1000, solver="lbfgs")
        clf.fit(X, y)
        return lambda X_new: clf.predict_proba(X_new)[:, 1]
    if model == "linear":
        reg = LinearRegression()
        reg.fit(X, y)
        return lambda X_new: reg.predict(X_new)
    raise ValueError(f"unknown model {model!r}")


def _bootstrap_ci_frontdoor(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    mediators: tuple[str, ...],
    *,
    model: str,
    ci_bootstrap: int,
    ci_level: float,
    random_state: int,
) -> tuple[float, float]:
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = rng.integers(0, n, size=n)
        sample = df.iloc[idx]
        estimates[i] = _point_estimate_frontdoor(
            sample, treatment, outcome, mediators, model=model,
        )
    alpha = (1 - ci_level) / 2
    return float(np.quantile(estimates, alpha)), float(
        np.quantile(estimates, 1 - alpha)
    )


def _assumptions_for(model: str, n_mediators: int) -> tuple[str, ...]:
    common = (
        "front_door_criterion_holds_on_graph",
        "mediator_intercepts_all_directed_paths_from_treatment_to_outcome",
        "no_unblocked_backdoor_from_treatment_to_mediator",
        "backdoor_from_mediator_to_outcome_blocked_by_treatment",
        "consistency_of_potential_outcomes",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logistic":
        common = common + ("logit_outcome_regression",)
    if n_mediators > 1:
        common = common + (
            "chain_rule_factoring_of_joint_mediator_conditional",
        )
    return common
