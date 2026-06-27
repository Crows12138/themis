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
from .resample import cluster_labels, resample_indices


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
    cluster: str | None = None
    # iter 120: first-stage F-statistic for the instrument's effect on
    # treatment after partialing out conditioning W. Stock & Yogo (2005)
    # pin F < 10 as the canonical "weak instrument" threshold for a
    # single-instrument 2SLS / Wald case. None when computation fails
    # (degenerate first stage / sample too small) — downstream weak-IV
    # detection treats None as "could not assess" rather than "strong".
    first_stage_f_stat: float | None = None


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
    cluster: str | None = None,
) -> IVEstimate:
    """Instrumental-variable ATE via Wald (binary) or 2SLS (linear).

    ``cluster`` (optional column name) switches the bootstrap CI to a
    pairs cluster bootstrap; ``None`` reproduces the i.i.d. bootstrap.
    """
    required = {treatment, outcome, instrument, *conditioning}
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

    f_stat = _first_stage_f_stat(
        df, treatment=treatment, instrument=instrument, conditioning=conditioning,
    )

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_iv(
            df, treatment, outcome, instrument, conditioning,
            model=resolved, ci_bootstrap=ci_bootstrap,
            ci_level=ci_level, random_state=random_state,
            groups=groups,
        )

    assumptions = _assumptions_for(resolved, len(conditioning))
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return IVEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method=method,
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        instrument=instrument,
        conditioning=tuple(conditioning),
        treatment=treatment,
        outcome=outcome,
        cluster=cluster,
        first_stage_f_stat=f_stat,
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


def _first_stage_f_stat(
    df: pd.DataFrame,
    *,
    treatment: str,
    instrument: str,
    conditioning: tuple[str, ...],
) -> float | None:
    """Compute the first-stage F-statistic for the instrument's effect
    on treatment, after partialing out conditioning W. Used downstream
    by the weak-IV detector.

    Single-instrument case: F = (β̂_Z / SE(β̂_Z))² from the OLS
    regression  X = α + β·Z + γ'·W + ε.

    Returns None when the regression is degenerate (n < 3 + len(W),
    instrument variance ~0, or any sklearn-side numerical failure) —
    downstream treats None as "could not assess" rather than "strong".
    """
    z_arr = df[instrument].to_numpy(dtype=float)
    x_arr = df[treatment].to_numpy(dtype=float)
    w_cols = list(conditioning)

    n = len(df)
    k_extra = 1 + len(w_cols)  # intercept + W columns
    # Need at least one residual degree of freedom on top of the
    # parameters we're fitting (intercept + Z + W).
    if n - (k_extra + 1) < 1:
        return None
    if float(np.var(z_arr)) < 1e-12:
        return None

    if w_cols:
        w_arr = df[w_cols].to_numpy(dtype=float)
        design_with_z = np.hstack([z_arr.reshape(-1, 1), w_arr])
        design_no_z = w_arr
    else:
        design_with_z = z_arr.reshape(-1, 1)
        design_no_z = np.empty((n, 0))

    try:
        # SSR with Z (full first-stage model)
        full = LinearRegression()
        full.fit(design_with_z, x_arr)
        resid_full = x_arr - full.predict(design_with_z)
        ssr_full = float(np.sum(resid_full ** 2))

        # SSR without Z (restricted: only intercept + W)
        if design_no_z.shape[1] == 0:
            mean_x = float(np.mean(x_arr))
            ssr_restricted = float(np.sum((x_arr - mean_x) ** 2))
        else:
            restricted = LinearRegression()
            restricted.fit(design_no_z, x_arr)
            resid_r = x_arr - restricted.predict(design_no_z)
            ssr_restricted = float(np.sum(resid_r ** 2))

        # Single-restriction F = ((SSR_R - SSR_F) / 1) / (SSR_F / df_resid).
        df_resid = n - (1 + 1 + len(w_cols))  # intercept + Z + W
        if df_resid < 1 or ssr_full <= 0:
            return None
        numerator = (ssr_restricted - ssr_full)
        if numerator < 0:
            # Numerical noise; treat as zero.
            numerator = 0.0
        f = numerator / (ssr_full / df_resid)
        return float(f)
    except (np.linalg.LinAlgError, ValueError):
        return None


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
    groups: np.ndarray | None = None,
) -> tuple[float, float]:
    rng = np.random.default_rng(random_state)
    n = len(df)
    estimates = np.empty(ci_bootstrap)
    for i in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
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
