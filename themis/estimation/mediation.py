"""Phase 7.4 + 7.5 — mediation numeric estimators.

S.MN.1 (Phase 7.4): NDE / NIE / TE via statsmodels' Mediation class
(Imai, Keele, Tingley 2010 algorithms 1 & 2). See ``estimate_mediation``.

S.CDE (Phase 7.5, iter 125): Controlled Direct Effect at a fixed
mediator value m* via plug-in g-formula on a fitted outcome model
``Y ~ X + M + Z``. See ``estimate_cde``. Implementation is sklearn-
based (not statsmodels) because choosing a reference m* and computing
``E[Y|do(X=x), do(M=m*)]`` requires a custom plug-in that the
statsmodels Mediation API doesn't expose. Bootstrap CI matches the
backdoor estimator's percentile pattern.

Scope (current):
- Single mediator (bool or continuous)
- Binary treatment
- Bool or continuous outcome (logit / OLS)
- Adjustment set ``adjustment`` threaded into both outcome and
  mediator models as linear features
- CDE: requires the user to pass ``mediator_value=m*`` (no implicit
  reference choice — Themis does not invent which level is the
  "control" for the mediator)

Uses statsmodels as a production backend (not dev-only parity) per
the 5-rule API gate:
- deterministic given a seed
- statsmodels 15+ year track record
- version pinned in environment
- parity-testable against DoWhy's mediation estimator
- all outputs (3 point estimates + 3 CIs) fit in derivation JSON

CDE path uses sklearn linear / logistic regression for the outcome
model, same backend as ``themis/estimation/backdoor.py``.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

import statsmodels.api as sm
from statsmodels.stats.mediation import Mediation

from .contract import validate_data


@dataclass(frozen=True)
class MediationEstimate:
    """Numeric mediation decomposition.

    - ``nde`` / ``nie`` / ``te`` are point + CI for the natural direct,
      natural indirect, and total effects.
    - ``method`` distinguishes the outcome-model family.
    """

    nde_point: float
    nde_ci_lower: float
    nde_ci_upper: float
    nie_point: float
    nie_ci_lower: float
    nie_ci_upper: float
    te_point: float
    te_ci_lower: float
    te_ci_upper: float
    # Proportion of total effect mediated through M = NIE / TE.
    # The user's "X 占多少比例" question — surfaced explicitly so the
    # renderer doesn't have to compute it from {nie, te} (and lose the
    # CI by doing the division naively).
    proportion_mediated_point: float
    proportion_mediated_ci_lower: float
    proportion_mediated_ci_upper: float
    ci_level: float
    method: str                   # "mediation_linear_imai" | "mediation_logit_imai"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    n_rep: int


def estimate_mediation(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    adjustment: tuple[str, ...] = (),
    model: str = "auto",
    n_rep: int = 200,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> MediationEstimate:
    """Compute NDE / NIE / TE via the Imai et al. 2010 algorithm as
    implemented in statsmodels. See module docstring for scope.
    """
    required = {treatment, outcome, mediator, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    outcome_series = df[outcome]
    is_bool_outcome = pd.api.types.is_bool_dtype(outcome_series)
    resolved = (
        ("logit" if is_bool_outcome else "linear")
        if model == "auto" else model
    )

    # Coerce to float for statsmodels formula API
    fit_df = df.copy()
    bool_cols = [c for c in fit_df.columns if fit_df[c].dtype == bool]
    for c in bool_cols:
        fit_df[c] = fit_df[c].astype(float)

    adj_term = " + ".join(adjustment) if adjustment else ""
    sep = " + " if adj_term else ""

    # Outcome model: Y ~ X + M [+ adjustment]
    outcome_formula = f"{outcome} ~ {treatment} + {mediator}{sep}{adj_term}"
    if resolved == "logit":
        outcome_model = sm.Logit.from_formula(outcome_formula, data=fit_df)
        method = "mediation_logit_imai"
    elif resolved == "linear":
        outcome_model = sm.OLS.from_formula(outcome_formula, data=fit_df)
        method = "mediation_linear_imai"
    else:
        raise ValueError(f"unknown model {model!r}")

    # Mediator model: M ~ X [+ adjustment]
    # statsmodels.stats.mediation has a known incompatibility where
    # BinaryModel.get_distribution rejects the 'scale' kwarg that
    # Mediation.fit passes. Workaround: always use OLS on the mediator;
    # for bool mediators this is a linear-probability first stage, which
    # is a widely-accepted approximation in the Imai framework when the
    # treatment effect on the mediator is not near the [0,1] boundary.
    mediator_formula = f"{mediator} ~ {treatment}{sep}{adj_term}"
    mediator_model = sm.OLS.from_formula(mediator_formula, data=fit_df)

    # statsmodels uses numpy's default RNG; seed it for reproducibility
    rng = np.random.default_rng(random_state)
    # Monkey-patching global np.random isn't ideal, but statsmodels'
    # Mediation.fit() draws from np.random internally. Use np.random.seed
    # for compatibility with the legacy RandomState path statsmodels uses.
    np.random.seed(random_state)

    med_result = Mediation(
        outcome_model, mediator_model, treatment, mediator,
    ).fit(n_rep=n_rep)

    summary = med_result.summary()

    def _row(name: str) -> tuple[float, float, float]:
        row = summary.loc[name]
        return (
            float(row["Estimate"]),
            float(row["Lower CI bound"]),
            float(row["Upper CI bound"]),
        )

    # ACME (average) = NIE; ADE (average) = NDE
    nie_p, nie_lo, nie_hi = _row("ACME (average)")
    nde_p, nde_lo, nde_hi = _row("ADE (average)")
    te_p, te_lo, te_hi = _row("Total effect")
    # Imai's bootstrap also computes a CI for the NIE/TE ratio — use it
    # rather than re-doing point/point (which would lose the CI). The
    # row is "Prop. mediated (average)".
    pm_p, pm_lo, pm_hi = _row("Prop. mediated (average)")

    return MediationEstimate(
        nde_point=nde_p, nde_ci_lower=nde_lo, nde_ci_upper=nde_hi,
        nie_point=nie_p, nie_ci_lower=nie_lo, nie_ci_upper=nie_hi,
        te_point=te_p, te_ci_lower=te_lo, te_ci_upper=te_hi,
        proportion_mediated_point=pm_p,
        proportion_mediated_ci_lower=pm_lo,
        proportion_mediated_ci_upper=pm_hi,
        ci_level=ci_level,
        method=method,
        assumptions=_assumptions_for(resolved, len(adjustment)),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        n_rep=n_rep,
    )


@dataclass(frozen=True)
class CDEEstimate:
    """Phase 7.5 (iter 125) — Controlled Direct Effect at fixed M=m*.

    CDE(x, x', m*) = E[Y | do(X=x), do(M=m*)] - E[Y | do(X=x'), do(M=m*)]

    Differences from NDE/NIE:
    - CDE fixes M at a chosen level m* (the "control" for the
      mediator); NDE/NIE take expectations over M's natural distribution.
    - CDE only requires the X→Y identification given M (one-step
      no-unmeasured-confounders), not Pearl's full sequential
      ignorability — a strictly weaker assumption set.
    - Per VanderWeele 2015 ch.2.3.3, CDE is the policy-relevant
      direct effect when M is itself an intervention target (e.g.
      "what would the effect of X on Y look like if we forced
      everyone's M to m*?").
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                   # "cde_linear" | "cde_logit"
    mediator_value: object        # the m* the CDE was computed at
    treatment_low: object         # the x' (control treatment level)
    treatment_high: object        # the x (treated level)
    sample_size: int
    data_hash: str
    adjustment: tuple[str, ...]
    mediator: str
    treatment: str
    outcome: str
    assumptions: tuple[str, ...]


def estimate_cde(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    mediator: str,
    mediator_value: object,
    adjustment: tuple[str, ...] = (),
    treatment_low: object = False,
    treatment_high: object = True,
    model: str = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> CDEEstimate:
    """Plug-in g-formula CDE at fixed ``M = mediator_value``.

    Steps:
    1. Fit ``E[Y | X, M, Z]`` with sklearn (linear if Y continuous,
       logistic if Y bool).
    2. For each row i, predict at ``(X=high, M=m*, Z=Z_i)`` and
       ``(X=low, M=m*, Z=Z_i)``; the CDE is the sample-mean difference.
    3. Percentile bootstrap CI (same pattern as backdoor.py).

    Returns ``CDEEstimate``. Does NOT require statsmodels — purely
    sklearn — because the statsmodels Mediation API doesn't expose
    do(M=m*) plug-in directly.
    """
    from sklearn.linear_model import LinearRegression, LogisticRegression

    required = {treatment, outcome, mediator, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    is_bool_outcome = pd.api.types.is_bool_dtype(df[outcome])
    if model == "auto":
        resolved = "logit" if is_bool_outcome else "linear"
    else:
        resolved = model

    feature_cols = [treatment, mediator, *adjustment]

    def _fit_predict_diff(sample: pd.DataFrame) -> float:
        X_full = sample[feature_cols].to_numpy(dtype=float)
        y = sample[outcome].to_numpy()
        if resolved == "logit":
            y_int = y.astype(int)
            if len(np.unique(y_int)) < 2:
                raise ValueError("only one outcome value in this draw")
            clf = LogisticRegression(max_iter=1000, solver="lbfgs")
            clf.fit(X_full, y_int)
            X_high = X_full.copy()
            X_low = X_full.copy()
            # Replace the treatment column (index 0) and mediator (index 1)
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            p_high = clf.predict_proba(X_high)[:, 1]
            p_low = clf.predict_proba(X_low)[:, 1]
            return float(np.mean(p_high - p_low))
        elif resolved == "linear":
            reg = LinearRegression()
            reg.fit(X_full, y.astype(float))
            X_high = X_full.copy()
            X_low = X_full.copy()
            X_high[:, 0] = float(treatment_high)
            X_low[:, 0] = float(treatment_low)
            X_high[:, 1] = float(mediator_value)
            X_low[:, 1] = float(mediator_value)
            return float(np.mean(reg.predict(X_high) - reg.predict(X_low)))
        else:
            raise ValueError(f"unknown model {model!r}")

    point = _fit_predict_diff(df)

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        rng = np.random.default_rng(random_state)
        n = len(df)
        draws = np.empty(ci_bootstrap)
        for i in range(ci_bootstrap):
            idx = rng.integers(0, n, size=n)
            try:
                draws[i] = _fit_predict_diff(df.iloc[idx])
            except (ValueError, np.linalg.LinAlgError):
                draws[i] = np.nan
        draws = draws[~np.isnan(draws)]
        if len(draws) > 0:
            alpha = (1 - ci_level) / 2
            ci_lower = float(np.quantile(draws, alpha))
            ci_upper = float(np.quantile(draws, 1 - alpha))

    method = f"cde_{resolved}"
    assumptions = (
        "no_unmeasured_confounder_x_y_given_m_and_adjustment",
        "no_unmeasured_confounder_m_y_given_x_and_adjustment",
        "consistency_of_potential_outcomes",
    )
    if adjustment:
        assumptions = assumptions + (
            "adjustment_set_blocks_xy_and_my_backdoors",
        )

    return CDEEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method=method,
        mediator_value=mediator_value,
        treatment_low=treatment_low,
        treatment_high=treatment_high,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        adjustment=tuple(adjustment),
        mediator=mediator,
        treatment=treatment,
        outcome=outcome,
        assumptions=assumptions,
    )


def _assumptions_for(model: str, n_adj: int) -> tuple[str, ...]:
    common = (
        "sequential_ignorability_treatment_and_mediator",
        "no_intermediate_confounder_affected_by_treatment",
        "pearl_2001_four_conditions_hold_on_the_graph",
    )
    if model == "linear":
        common = common + ("linear_outcome_regression",)
    elif model == "logit":
        common = common + ("logit_outcome_regression",)
    if n_adj > 0:
        common = common + (
            "adjustment_set_blocks_mediator_outcome_backdoor_given_treatment",
        )
    return common
