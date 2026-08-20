"""Phase 9 §S9.2 numeric end — recover the back-door ATE from data that
itself has missing values (Mohan, Pearl & Tian 2013).

The identification layer (``runtime/missing_data.py`` + the scheduler's
``missing_data_recovery`` block) decides WHETHER the interventional
estimand

    P(Y | do(X)) = Σ_z P(Y | X, Z=z) · P(Z=z)

is recoverable from a data set corrupted by a response process, and
returns the recovery FORMULA. This module is the numeric counterpart: it
takes a DataFrame that still contains the missing values (NaN in the
partially-observed columns) and applies that formula to produce an actual
number.

The interventional distribution is a PRODUCT of two manifest factors and
— this is the whole point of the multi-factor combination — each factor
is estimated from its OWN complete cases, not from one listwise-deleted
subset shared by both:

- the adjusted conditional E[Y | X, Z] from rows where {Y, X, Z} are all
  observed (the factor's relevant missingness indicators are 0);
- the covariate marginal P(Z) from rows where {Z} is observed — a LARGER
  set when Y (or X) is what's missing.

Naive listwise deletion estimates BOTH factors from the fully-complete
subset, so under MAR where missingness depends on Z the estimated P(Z) is
distorted (complete cases over-represent the low-missingness strata) and,
whenever the effect is modified by Z, the ATE is biased. Using each
factor's own complete cases removes exactly that bias — the estimator
recovers the truth while the naive listwise number does not. The naive
number is reported alongside as a diagnostic.

Scope (v1, declared):
- DISCRETE back-door adjustment: the covariate marginal P(Z) and the
  stratum conditionals E[Y|X,Z] are estimated by stratification, so every
  adjustment variable must be low-cardinality (≤ 32 observed levels,
  integer-valued). A continuous confounder needs a model for P(Z) / the
  conditional and is out of scope (declared, not silently handled).
- The recovery FORMULA's validity (MAR / the ordered factorization holds)
  is an identification assumption decided structurally by the missing-data
  layer; this estimator APPLIES the formula and does not re-derive
  recoverability from the m-graph. If you call it on genuinely MNAR data
  the number is not meaningful — check ``missing_data_recovery.estimand``
  first (the kernel data path does this for you).
- Binary treatment (0/1). Outcome may be binary or continuous (a mean is
  taken within stratum, so E[Y|X,Z] is well-defined either way).

API::

    from themis.estimation.missing_recovery import estimate_recovered_ate
    est = estimate_recovered_ate(
        df_with_nan, treatment="x", outcome="y", adjustment=("z",),
    )
    est.point                # recovered ATE
    est.naive_listwise_ate   # the biased complete-case comparison
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import _hash_frame
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .resample import cluster_labels, resample_indices

_MIN_SAMPLE_SIZE = 10
_MAX_STRATA_LEVELS = 32


@dataclass(frozen=True)
class RecoveredATEEstimate:
    """Back-door ATE recovered from missing data + bootstrap CI.

    ``point`` is the multi-factor recovered ATE E[Y|do(1)] − E[Y|do(0)];
    ``naive_listwise_ate`` is the biased estimate that deletes any row with
    a missing value and estimates both factors from that one subset (None
    when the fully-complete subset has an empty treatment×stratum cell).
    The gap between them is the recovery correction.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                      # "missing_data_recovery_gformula"
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    naive_listwise_ate: float | None
    n_total: int
    n_complete_case: int             # rows with NO missing model value
    n_conditional_rows: int          # rows usable for E[Y|X,Z]
    n_marginal_rows: int             # rows usable for P(Z)
    n_strata: int
    missing_columns: tuple[str, ...]
    assumptions: tuple[str, ...]
    n_bootstrap: int                 # valid (non-degenerate) resamples
    data_hash: str
    # Per-stratum sufficient statistics the point was summed from — the
    # record an independent verifier re-derives Σ_z (E[Y|1,z]−E[Y|0,z])·P(z)
    # from without re-touching the data. Two parallel factor tables, one for
    # the recovered estimate and (when it exists) one for the naive listwise
    # foil; each carries conditional_strata {z,arm,n,y_sum} and
    # marginal_counts {z,count} + marginal_total.
    sufficient_statistics: dict = None  # type: ignore[assignment]
    cluster: str | None = None


def _to_float_frame(data: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """A working frame of the model columns coerced to float, NaN preserved.

    Bool / int / bool-with-NaN (object) columns all become 0.0 / 1.0 / NaN
    so stratum keys and treatment comparisons are dtype-stable.
    """
    out = pd.DataFrame(index=data.index)
    for c in cols:
        out[c] = pd.to_numeric(data[c], errors="coerce").astype("float64")
    return out.reset_index(drop=True)


def _check_discrete(frame: pd.DataFrame, col: str, treatment: str) -> None:
    obs = frame[col].dropna().to_numpy()
    if obs.size == 0:
        raise EstimatorFailure(
            Refusal.ADJUSTMENT_ALL_MISSING,
            f"adjustment column {col!r} is never observed — its marginal "
            f"P({col}) cannot be recovered.",
            treatment=treatment,
        )
    levels = np.unique(obs)
    if levels.size > _MAX_STRATA_LEVELS or np.any(levels != np.round(levels)):
        raise EstimatorFailure(
            Refusal.ADJUSTMENT_NOT_DISCRETE,
            f"adjustment column {col!r} has {levels.size} observed levels / "
            f"non-integer values; the recovery estimator stratifies on the "
            f"back-door set, so each adjustment variable must be discrete "
            f"(≤ {_MAX_STRATA_LEVELS} integer levels). A continuous confounder "
            f"needs a model for P(Z) and is out of scope.",
            treatment=treatment,
        )


def _gformula_ate(
    cond_rows: pd.DataFrame,
    marg_rows: pd.DataFrame,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    stats: dict | None = None,
) -> float:
    """E[Y|do(1)] − E[Y|do(0)] = Σ_z (E[Y|1,z] − E[Y|0,z])·P(z).

    ``cond_rows`` supplies the stratum conditionals E[Y|X,z]; ``marg_rows``
    supplies the covariate marginal P(z). Passing the SAME frame for both
    gives the naive listwise g-formula; passing each factor's own
    complete-case frame gives the recovered estimate. Raises
    ``EstimatorFailure`` when a needed treatment×stratum cell is empty.

    When ``stats`` is a dict it is filled with the per-stratum sufficient
    statistics the sum was built from — ``conditional_strata`` (one
    ``{z, arm, n, y_sum}`` per contributing (arm, z) cell, so
    E[Y|arm,z] = y_sum/n), ``marginal_counts`` (``{z, count}`` per z) and
    ``marginal_total`` (so P(z) = count/total) — the record a verifier
    re-derives the point from. Left None in the bootstrap hot loop so it
    stays allocation-free there.
    """
    collect = stats is not None
    cond_strata: list[dict] = []
    marg_counts: list[dict] = []
    zt = list(adjustment)
    tx = cond_rows[treatment].to_numpy()
    yv = cond_rows[outcome].to_numpy()

    if not zt:
        ate = 0.0
        total = int(yv.size)
        for x, sign in ((1.0, 1.0), (0.0, -1.0)):
            cell = yv[tx == x]
            if cell.size == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    f"no complete-case rows with {treatment}={int(x)}.",
                    treatment=treatment,
                )
            ate += sign * float(cell.mean())
            if collect:
                cond_strata.append({
                    "z": [], "arm": int(x),
                    "n": int(cell.size), "y_sum": float(cell.sum()),
                })
        if collect:
            stats["conditional_strata"] = cond_strata
            stats["marginal_counts"] = [{"z": [], "count": int(len(marg_rows))}]
            stats["marginal_total"] = int(len(marg_rows))
        return ate

    grp = marg_rows.groupby(zt, sort=True).size()
    total = int(grp.sum())
    z_cols = [cond_rows[c].to_numpy() for c in zt]
    ate = 0.0
    for z_key, cnt in grp.items():
        z_vals = z_key if isinstance(z_key, tuple) else (z_key,)
        pz = cnt / total
        in_stratum = np.logical_and.reduce(
            [z_cols[i] == z_vals[i] for i in range(len(zt))]
        )
        if collect:
            marg_counts.append(
                {"z": [float(v) for v in z_vals], "count": int(cnt)}
            )
        eff = 0.0
        for x, sign in ((1.0, 1.0), (0.0, -1.0)):
            cell = yv[in_stratum & (tx == x)]
            if cell.size == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    f"no complete-case rows in stratum "
                    f"{dict(zip(zt, z_vals))} with {treatment}={int(x)}; the "
                    f"recovered conditional E[Y|X,Z] is undefined there.",
                    treatment=treatment,
                )
            eff += sign * float(cell.mean())
            if collect:
                cond_strata.append({
                    "z": [float(v) for v in z_vals], "arm": int(x),
                    "n": int(cell.size), "y_sum": float(cell.sum()),
                })
        ate += eff * pz
    if collect:
        stats["conditional_strata"] = cond_strata
        stats["marginal_counts"] = marg_counts
        stats["marginal_total"] = total
    return ate


def _recovered_ate(
    frame: pd.DataFrame, treatment: str, outcome: str,
    adjustment: tuple[str, ...], stats: dict | None = None,
) -> float:
    """Multi-factor recovery: each factor from its OWN complete cases."""
    cond_rows = frame.dropna(subset=[outcome, treatment, *adjustment])
    marg_rows = (
        frame.dropna(subset=list(adjustment)) if adjustment else cond_rows
    )
    return _gformula_ate(
        cond_rows, marg_rows, treatment, outcome, adjustment, stats=stats
    )


def _naive_listwise_ate(
    frame: pd.DataFrame, treatment: str, outcome: str,
    adjustment: tuple[str, ...], stats: dict | None = None,
) -> float | None:
    """Listwise deletion: BOTH factors from the fully-complete subset."""
    cc = frame.dropna(subset=[outcome, treatment, *adjustment])
    try:
        return _gformula_ate(cc, cc, treatment, outcome, adjustment, stats=stats)
    except EstimatorFailure:
        return None


def estimate_recovered_ate(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> RecoveredATEEstimate:
    """Recover the back-door ATE from data with missing values.

    Applies the Mohan-Pearl-Tian ordered-factorization recovery: the
    adjusted conditional E[Y|X,Z] is estimated from rows where {Y,X,Z} are
    observed and the covariate marginal P(Z) from rows where {Z} is
    observed, then combined by the g-formula. Because each factor uses its
    own complete cases, the estimate is unbiased under MAR where naive
    listwise deletion is not (that naive number is reported for contrast).

    Unlike the other estimators this does NOT route the model columns
    through the standard data contract — that contract forbids NaN, and NaN
    in the partially-observed columns is the whole subject here. ``cluster``
    switches the bootstrap to a pairs cluster bootstrap (parity with the
    rest of the estimation layer).

    Assumes the estimand is recoverable (MAR / the ordered factorization is
    valid) — an identification fact the missing-data layer decides; this
    estimator applies the formula. Requires binary treatment and discrete
    adjustment. Raises ``EstimatorFailure`` on a support / shape violation.
    """
    adjustment = tuple(adjustment)
    model_cols = [treatment, outcome, *adjustment]

    missing = [c for c in model_cols if c not in data.columns]
    if missing:
        raise EstimatorFailure(
            Refusal.MISSING_COLUMN,
            f"data is missing required columns: {missing}.",
            treatment=treatment,
        )
    n_total = len(data)
    if n_total < _MIN_SAMPLE_SIZE:
        raise EstimatorFailure(
            Refusal.SAMPLE_TOO_SMALL,
            f"sample size {n_total} is below the minimum "
            f"({_MIN_SAMPLE_SIZE}) for estimation.",
            treatment=treatment,
        )

    groups = (
        cluster_labels(data, cluster, expected_n=n_total)
        if cluster is not None else None
    )

    frame = _to_float_frame(data, model_cols)

    t_obs = frame[treatment].dropna().to_numpy()
    if not set(np.unique(t_obs)) <= {0.0, 1.0}:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            f"treatment {treatment!r} must be binary 0/1 over its observed "
            f"values; got levels {refusals.describe(sorted(set(np.unique(t_obs))))}.",
            treatment=treatment,
        )
    for z in adjustment:
        _check_discrete(frame, z, treatment)

    rec_stats: dict = {}
    point = _recovered_ate(frame, treatment, outcome, adjustment, stats=rec_stats)
    naive_stats: dict = {}
    naive = _naive_listwise_ate(
        frame, treatment, outcome, adjustment, stats=naive_stats
    )
    if naive is None:
        naive_stats = None  # type: ignore[assignment]

    missing_columns = tuple(c for c in model_cols if frame[c].isna().any())
    n_conditional = int(len(frame.dropna(subset=[outcome, treatment, *adjustment])))
    n_marginal = int(
        len(frame.dropna(subset=list(adjustment))) if adjustment else n_conditional
    )
    n_complete = int(len(frame.dropna(subset=model_cols)))
    if adjustment:
        n_strata = int(
            frame.dropna(subset=list(adjustment))
            .groupby(list(adjustment), sort=True).ngroups
        )
    else:
        n_strata = 1

    # Bootstrap (rows or whole clusters); skip degenerate resamples.
    rng = np.random.default_rng(random_state)
    draws: list[float] = []
    if ci_bootstrap > 0:
        for _ in range(ci_bootstrap):
            idx = resample_indices(n_total, rng, groups=groups)
            bframe = frame.iloc[idx].reset_index(drop=True)
            try:
                draws.append(_recovered_ate(bframe, treatment, outcome, adjustment))
            except EstimatorFailure:
                continue

    alpha = (1 - ci_level) / 2
    if draws:
        arr = np.asarray(draws, dtype=float)
        arr = arr[np.isfinite(arr)]
        ci_lower = float(np.quantile(arr, alpha)) if arr.size else None
        ci_upper = float(np.quantile(arr, 1 - alpha)) if arr.size else None
        n_boot = int(arr.size)
    else:
        ci_lower = ci_upper = None
        n_boot = 0

    assumptions: tuple[str, ...] = (
        "estimand_recoverable_ordered_factorization_valid",
        "adjustment_set_is_valid_backdoor_set",
        "discrete_adjustment_strata",
        "conditional_from_own_complete_cases_marginal_from_its_own",
    )
    if cluster is not None:
        assumptions = assumptions + (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)

    return RecoveredATEEstimate(
        point=point,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        method="missing_data_recovery_gformula",
        treatment=treatment,
        outcome=outcome,
        adjustment=adjustment,
        naive_listwise_ate=naive,
        n_total=n_total,
        n_complete_case=n_complete,
        n_conditional_rows=n_conditional,
        n_marginal_rows=n_marginal,
        n_strata=n_strata,
        missing_columns=missing_columns,
        assumptions=assumptions,
        n_bootstrap=n_boot,
        data_hash=_hash_frame(frame),
        sufficient_statistics={
            "adjustment_vars": list(adjustment),
            "recovered": rec_stats,
            "naive": naive_stats,
        },
        cluster=cluster,
    )
