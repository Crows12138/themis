"""Phase 7.3 S.IVN.1 — instrumental-variable ATE estimators.

Two hand-rolled estimators covering the standard textbook cases:

- **Wald**: ``(E[Y|Z=1] - E[Y|Z=0]) / (E[X|Z=1] - E[X|Z=0])``.
  Under IV1/IV2/IV3 + monotonicity, recovers the Local Average
  Treatment Effect (LATE) on compliers — NOT the population ATE
  when treatment effects are heterogeneous. Requires binary Z and X.
- **2SLS**: two-stage least squares via sklearn LinearRegression.
  Under IV1/IV2/IV3 + linearity + constant treatment effect, recovers
  the ATE. Handles continuous Z / X / W.

Auto selects: binary Z + binary X → Wald; else → 2SLS. Callers can
override via ``model=...``.

Conditional IV (``conditioning`` non-empty): both stages of 2SLS /
the Wald numerator & denominator are residualised against W
(Frisch-Waugh-Lovell). For the first version we apply this only on
the 2SLS path; conditional Wald degenerates to the unconditional
form when Z and X are binary and W is a valid conditioning set.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression

from .contract import validate_data


ModelName = Literal["auto", "wald", "2sls"]


@dataclass(frozen=True)
class IVEstimate:
    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "iv_wald" | "iv_2sls"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    instrument: str
    conditioning: tuple[str, ...]
    treatment: str
    outcome: str


def estimate_iv_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    instrument: str,
    conditioning: tuple[str, ...] = (),
    model: ModelName = "auto",
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
) -> IVEstimate:
    """Instrumental-variable ATE via Wald (binary) or 2SLS (linear)."""
    required = {treatment, outcome, instrument, *conditioning}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    z_series = df[instrument]
    x_series = df[treatment]
    z_is_bool = pd.api.types.is_bool_dtype(z_series)
    x_is_bool = pd.api.types.is_bool_dtype(x_series)

    if model == "auto":
        if z_is_bool and x_is_bool and not conditioning:
            resolved = "wald"
        else:
            resolved = "2sls"
    else:
        resolved = model

    if resolved == "wald":
        if not (z_is_bool and x_is_bool):
            raise ValueError(
                "Wald estimator requires binary instrument AND binary treatment"
            )
        if conditioning:
            raise NotImplementedError(
                "Conditional IV with Wald estimator is not supported in v1; "
                "use model='2sls' when conditioning is non-empty"
            )
        point = _wald_point(df, treatment, outcome, instrument)
    elif resolved == "2sls":
        point = _two_sls_point(
            df, treatment, outcome, instrument, conditioning,
        )
    else:
        raise ValueError(f"unknown model {model!r}")

    method = f"iv_{resolved}"

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_iv(
            df, treatment, outcome, instrument, conditioning,
            model=resolved, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state,
        )

    return IVEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method=method,
        assumptions=_assumptions_for(resolved, len(conditioning)),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        instrument=instrument,
        conditioning=tuple(conditioning),
        treatment=treatment,
        outcome=outcome,
    )


# --- internals ----------------------------------------------------------------


def _wald_point(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instrument: str,
) -> float:
    z = df[instrument].to_numpy(dtype=bool)
    x = df[treatment].to_numpy(dtype=float)
    y = df[outcome].to_numpy(dtype=float)

    ey1 = y[z].mean()
    ey0 = y[~z].mean()
    ex1 = x[z].mean()
    ex0 = x[~z].mean()

    denom = ex1 - ex0
    if abs(denom) < 1e-12:
        raise ValueError(
            "Wald denominator E[X|Z=1] - E[X|Z=0] is ~0; instrument has "
            "no measurable first-stage effect on treatment"
        )
    return (ey1 - ey0) / denom


def _two_sls_point(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instrument: str,
    conditioning: tuple[str, ...],
) -> float:
    """Standard two-stage least squares:

    Stage 1: X = α + β·Z + γ'·W + ε1  (fit; take predicted X̂)
    Stage 2: Y = δ + θ·X̂ + η'·W + ε2  (fit; return θ)
    """
    w_cols = list(conditioning)
    z_arr = df[instrument].to_numpy(dtype=float).reshape(-1, 1)
    x_arr = df[treatment].to_numpy(dtype=float)
    y_arr = df[outcome].to_numpy(dtype=float)

    if w_cols:
        w_arr = df[w_cols].to_numpy(dtype=float)
        stage1_X = np.hstack([z_arr, w_arr])
        stage2_W = w_arr
    else:
        stage1_X = z_arr
        stage2_W = None

    stage1 = LinearRegression()
    stage1.fit(stage1_X, x_arr)
    x_hat = stage1.predict(stage1_X)

    if stage2_W is None:
        stage2_X = x_hat.reshape(-1, 1)
    else:
        stage2_X = np.hstack([x_hat.reshape(-1, 1), stage2_W])

    stage2 = LinearRegression()
    stage2.fit(stage2_X, y_arr)
    # The coefficient on X̂ (first column) is the IV estimate of the ATE
    return float(stage2.coef_[0])


def _bootstrap_ci_iv(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instrument: str,
    conditioning: tuple[str, ...],
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
        try:
            if model == "wald":
                estimates[i] = _wald_point(
                    sample, treatment, outcome, instrument,
                )
            else:
                estimates[i] = _two_sls_point(
                    sample, treatment, outcome, instrument, conditioning,
                )
        except ValueError:
            # Degenerate bootstrap draw (e.g. only one Z-value sampled).
            estimates[i] = np.nan
    estimates = estimates[~np.isnan(estimates)]
    if len(estimates) == 0:
        raise ValueError(
            "all bootstrap iterations failed — data is pathological "
            "for this IV estimator"
        )
    alpha = (1 - ci_level) / 2
    return (
        float(np.quantile(estimates, alpha)),
        float(np.quantile(estimates, 1 - alpha)),
    )


def _assumptions_for(model: str, n_conditioning: int) -> tuple[str, ...]:
    common = (
        "iv1_relevance_instrument_affects_treatment",
        "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
        "iv3_independence_instrument_independent_of_latent_confounders",
    )
    if model == "wald":
        return common + (
            "monotonicity_first_stage_effect_same_sign_for_all_units",
            "estimand_is_LATE_on_compliers_not_population_ATE",
        )
    if model == "2sls":
        extra = (
            "linearity_of_first_and_second_stage",
            "constant_treatment_effect_else_estimand_is_weighted_average",
        )
        if n_conditioning > 0:
            extra = extra + (
                "conditioning_set_blocks_instrument_outcome_backdoor_given_W",
            )
        return common + extra
    return common
