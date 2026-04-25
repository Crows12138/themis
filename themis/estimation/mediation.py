"""Phase 7.4 S.MN.1 — mediation numeric estimator (NDE / NIE / TE).

Wraps statsmodels' ``statsmodels.stats.mediation.Mediation`` (Imai,
Keele, Tingley 2010 algorithms 1 & 2) so Themis can produce numeric
natural direct / indirect / total effects when the identification
layer has cleared Pearl's four conditions (see Phase 6.mediation).

Scope (v1):
- Single mediator (bool or continuous)
- Binary treatment
- Bool or continuous outcome (logit / OLS)
- Adjustment set ``adjustment`` threaded into both outcome and
  mediator models as linear features
- CDE estimation **not** included in v1 — requires choosing a
  reference mediator value m* that isn't expressible cleanly in the
  statsmodels API. Deferred to 7.5 if a real case needs it.

Uses statsmodels as a production backend (not dev-only parity) per
the 5-rule API gate:
- deterministic given a seed
- statsmodels 15+ year track record
- version pinned in environment
- parity-testable against DoWhy's mediation estimator
- all outputs (3 point estimates + 3 CIs) fit in derivation JSON
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

    return MediationEstimate(
        nde_point=nde_p, nde_ci_lower=nde_lo, nde_ci_upper=nde_hi,
        nie_point=nie_p, nie_ci_lower=nie_lo, nie_ci_upper=nie_hi,
        te_point=te_p, te_ci_lower=te_lo, te_ci_upper=te_hi,
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
