"""Measurement-error correction numeric end — confusion-matrix inversion.

The structural layer only *flags* measurement error: an identification-path
variable whose ``measurement`` / ``observability`` text names a noisy modality
raises the ``measurement_error_concern`` gap ("regression dilution attenuates
your estimate; Themis does structural ID + gap diagnosis, not de-attenuation").
This module is the DATA counterpart for the one case where de-attenuation is
point-identified: a **misclassified discrete outcome** whose misclassification
process is captured by a **known confusion matrix** from a validation study.

Model (Barron 1977; Greenland 1988; Kuroki & Pearl 2014; Rogan & Gladen 1978
for the binary special case). Let the true outcome be Y* and the observed
(recorded) outcome be Y, both over the same k discrete states. The confusion
matrix M is column-stochastic with

    M[i, j] = P(Y = state_i | Y* = state_j)          (each column sums to 1)

Under **non-differential** misclassification — Y ⊥ (X, Z) | Y*, i.e. the SAME
matrix applies in every treatment arm and covariate stratum — the observed
per-stratum outcome distribution is a linear image of the true one:

    p_obs(· | x, z) = M · p_true(· | x, z)   ⇒   p_true(· | x, z) = M⁻¹ p_obs(· | x, z)

The corrected effect on the query's target value y* is the back-door
standardised risk difference of the *recovered* true distribution:

    effect = Σ_z [ p_true(y* | 1, z) − p_true(y* | 0, z) ] · P(z)

with p_true(· | x, z) = M⁻¹ p_obs(· | x, z) and P(z) the empirical covariate
marginal. For a binary outcome this is exactly Rogan-Gladen applied per
stratum: p_true(1 | x, z) = (p_obs(1 | x, z) + Sp − 1) / (Se + Sp − 1), and
because det(M) = Se + Sp − 1 is constant the whole thing collapses to
``naive_effect / det(M)`` — the classic "non-differential misclassification
attenuates a risk difference by the factor Se+Sp−1" result, run in reverse.

Guards (honest, not silent):

- **Singular channel.** |det(M)| below ``_DET_FLOOR`` ⇒ the matrix is not
  invertible (the measurement carries no usable information about Y*) ⇒
  refuse (``EstimatorFailure``), mirroring the proximal rank guard — no
  fabricated point from a near-degenerate inversion.
- **Out of the simplex.** M⁻¹ p_obs is the method-of-moments estimator; it is
  unbiased but can land outside [0, 1] when the matrix is weakly informative or
  the non-differential assumption is violated. We report it as-is (clipping
  would bias it) and set the ``out_of_simplex`` diagnostic so the caller can
  surface the instability. The bootstrap CI widens accordingly.
- **Positivity.** A covariate stratum present in the marginal but empty in an
  arm has no P(y|x,z) to correct ⇒ positivity refusal rather than a made-up
  cell.

Scope (declared tradeoffs):

- **Outcome** misclassification only. Exposure/treatment misclassification is a
  different correction (it un-mixes the (X*, Y) joint and interacts with the
  adjustment set differently) — deferred.
- **Non-differential** only. A differential matrix (per-arm M) changes the
  geometry — deferred.
- **Known** confusion matrix, treated as FIXED. The bootstrap propagates the
  main-sample sampling variability only; validation-study uncertainty in M
  itself (a second bootstrap / Bayesian layer) is deferred.
- **Discrete** outcome (a confusion matrix is a discrete-misclassification
  object); continuous mismeasurement (regression calibration / SIMEX) is the
  ``measurement_error_concern`` gap's territory, not this estimator's.

The sufficient statistics recorded on the estimate (the confusion matrix, the
per-(arm, stratum) full outcome value-count vectors, and the covariate marginal
counts) are exactly what ``themis.verify_measurement_correction_numeric``
re-inverts — it never re-touches the raw data and never imports this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices

# A covariate with more distinct values than this is treated as continuous and
# refused (no empirical stratum for the saturated stratified correction).
_MAX_LEVELS = 20
# |det(M)| below this is a non-invertible measurement channel → refuse.
_DET_FLOOR = 1e-6
_TOL = 1e-9


@dataclass(frozen=True)
class MeasurementCorrectionEstimate:
    """Confusion-matrix-corrected effect on the target value, with a bootstrap CI.

    ``point`` is the corrected Σ_z [p_true(y*|1,z) − p_true(y*|0,z)] P(z).
    ``naive_point`` is the same standardisation on the *observed* (attenuated)
    distribution — the biased number the correction replaces, kept for contrast.
    ``det`` is det(M) (= Se+Sp−1 for a binary outcome); ``out_of_simplex`` flags
    a recovered probability outside [0, 1]. ``sufficient_statistics`` carries the
    confusion matrix, per-(arm, stratum) value-count vectors, and the covariate
    marginal counts — everything the numeric verifier re-inverts the point from.
    """
    point: float
    naive_point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_value: object
    states: tuple[object, ...]
    confusion_matrix: tuple[tuple[float, ...], ...]
    det: float
    out_of_simplex: bool
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "confusion_matrix_inversion_backdoor_standardised"
    model_assumption: str = ""


# --- public entry -------------------------------------------------------------


def estimate_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    confusion_matrix,
    states,
    target_value,
    differential: bool = False,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> MeasurementCorrectionEstimate:
    """Recover the back-door effect on a misclassified discrete outcome by
    inverting the confusion matrix, per covariate stratum.

    Parameters
    ----------
    data: the main sample carrying the *observed* (misclassified) outcome.
    treatment / outcome: binary X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete).
    confusion_matrix: k×k, ``M[i][j] = P(Y=states[i] | Y*=states[j])``, each
        column summing to 1.
    states: the k outcome states in the row/column order of ``confusion_matrix``
        (must cover every observed outcome value).
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y*=y*)``.
    differential: must be False; a per-arm matrix is deferred.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (M is held fixed across resamples).

    Raises
    ------
    EstimatorFailure: differential requested; non-binary treatment; continuous
        adjustment covariate; malformed / non-stochastic / singular confusion
        matrix; states not covering the observed outcome; target value absent;
        a positivity violation (a contributing stratum empty in an arm).
    """
    if differential:
        raise EstimatorFailure(
            "differential_misclassification",
            "a differential (per-arm) confusion matrix is deferred; this "
            "estimator assumes non-differential misclassification "
            "(Y ⊥ (X,Z) | Y*).",
        )

    states = tuple(_py(s) for s in states)
    k = len(states)
    if k < 2:
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            f"need at least 2 outcome states; got {states!r}.",
        )
    if len(set(states)) != k:
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            f"outcome states must be distinct; got {states!r}.",
        )
    target_value = _py(target_value)
    if target_value not in states:
        raise EstimatorFailure(
            "target_value_absent",
            f"query target value {target_value!r} is not among the declared "
            f"outcome states {states!r}.",
        )

    M = _validate_matrix(confusion_matrix, k)
    det = float(np.linalg.det(M))
    if abs(det) < _DET_FLOOR:
        raise EstimatorFailure(
            "singular_confusion_matrix",
            f"confusion matrix is non-invertible (|det| = {abs(det):.3g} < "
            f"{_DET_FLOOR:g}); the measurement carries no usable information "
            f"about the true outcome and the correction is undefined.",
        )
    Minv = np.linalg.inv(M)

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    _require_binary(df[treatment], treatment)
    for v in adjustment:
        _require_discrete(df[v], v)

    observed_states = set(_py(v) for v in pd.unique(df[outcome].dropna()))
    missing = observed_states - set(states)
    if missing:
        raise EstimatorFailure(
            "states_incomplete",
            f"observed outcome values {sorted(map(str, missing))} are not in the "
            f"declared confusion-matrix states {states!r}; the matrix must cover "
            f"every observed outcome value.",
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = states.index(target_value)
    point, naive, oos, suff = _formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, Minv=Minv, target_index=target_index,
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, Minv=Minv, target_index=target_index, groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    assumptions = _assumptions(adjustment, cluster)
    return MeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        confusion_matrix=tuple(tuple(float(v) for v in row) for row in M),
        det=det,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            "confusion_matrix": [[float(v) for v in row] for row in M],
            "states": [_py(s) for s in states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=(
            "被误分类的离散结局 Y 有验证研究给出的混淆矩阵 M（列随机，"
            "M[i][j]=P(Y=state_i|Y*=state_j)）。在非差异误分类假设下"
            "（Y⊥(X,Z)|Y*，各臂各层同一 M）逐层求逆恢复真实分布 "
            "p_true(·|x,z)=M⁻¹p_obs(·|x,z)，再对目标值 y* 做后门标准化 "
            "ATE=Σ_z[p_true(y*|1,z)−p_true(y*|0,z)]P(z)。二值结局即逐层 "
            "Rogan-Gladen，去衰减因子 det(M)=Se+Sp−1。"
        ),
    )


# --- formula core -------------------------------------------------------------


def _formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, Minv: np.ndarray,
    target_index: int,
) -> tuple[float, float, bool, dict]:
    """Corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics.

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have support in BOTH arms (positivity). ``out_of_simplex`` is True if
    any recovered p_true component lands outside [0, 1]."""
    x = _as_binary(df[treatment])
    yvals = df[outcome].map(_py)
    n_total = len(df)

    marginal = _marginal(df, adjustment)              # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    strata_records: list[dict] = []
    corrected = 0.0
    naive = 0.0
    oos = False

    for z_key, p_z in marginal.items():
        if p_z <= 0:
            continue
        z_mask = _stratum_mask(df, adjustment, z_key)
        arm_true = {}
        for arm in (1, 0):
            mask = z_mask & (x == bool(arm))
            n = int(mask.sum())
            if n == 0:
                raise EstimatorFailure(
                    "insufficient_support",
                    f"stratum X={arm}, z={_json_key(z_key)} has no rows "
                    f"(positivity violation); P(Y|x,z) is not estimable so the "
                    f"correction cannot standardise over it.",
                )
            counts = _value_counts(yvals[mask.to_numpy()], states)
            p_obs = counts.astype(float) / n
            p_true = Minv @ p_obs
            if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
                oos = True
            arm_true[arm] = float(p_true[target_index])
            strata_records.append({
                "arm": arm,
                "z": list(_json_key(z_key)),
                "counts": [int(c) for c in counts],
                "n": n,
            })
        corrected += (arm_true[1] - arm_true[0]) * p_z
        # Naive: the observed target-value risk, standardised — the biased number.
        naive += (
            _obs_target_risk(df, z_mask, x, yvals, states, target_index, 1)
            - _obs_target_risk(df, z_mask, x, yvals, states, target_index, 0)
        ) * p_z

    suff = {
        "strata": sorted(strata_records, key=_stratum_sort),
        "marginal_counts": [
            {"z": list(_json_key(k)), "count": c}
            for k, c in sorted(marginal_counts.items(), key=lambda kv: str(kv[0]))
        ],
        "marginal_total": n_total,
        "det": float(np.linalg.det(np.linalg.inv(Minv))),
    }
    return corrected, naive, oos, suff


def _obs_target_risk(df, z_mask, x, yvals, states, target_index, arm) -> float:
    mask = z_mask & (x == bool(arm))
    n = int(mask.sum())
    counts = _value_counts(yvals[mask.to_numpy()], states)
    return float(counts[target_index]) / n if n else 0.0


def _value_counts(series: pd.Series, states: tuple) -> np.ndarray:
    """Count of each state (in ``states`` order) among ``series`` values.

    Uses a plain dict (not ``Series.get``) so integer state keys are matched by
    label, not by the deprecated positional fallback."""
    counts = series.value_counts().to_dict()
    return np.array([int(counts.get(s, 0)) for s in states], dtype=float)


def _marginal(df: pd.DataFrame, vars_: tuple[str, ...]) -> dict[tuple, float]:
    n = len(df)
    if not vars_:
        return {(): 1.0}
    counts = _marginal_counts(df, vars_)
    return {k: v / n for k, v in counts.items()}


def _marginal_counts(df: pd.DataFrame, vars_: tuple[str, ...]) -> dict[tuple, int]:
    if not vars_:
        return {(): len(df)}
    out: dict[tuple, int] = {}
    sub = df[list(vars_)]
    for key, idx in sub.groupby(list(vars_), sort=True, observed=True).indices.items():
        out[_as_tuple(key, len(vars_))] = len(idx)
    return out


# --- bootstrap ----------------------------------------------------------------


def _bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, Minv: np.ndarray,
    target_index: int, groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected effect — resample rows (or
    clusters), recompute the per-stratum correction with M held FIXED, collect
    the point. Draws that induce a positivity failure are skipped."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            pt, _naive, _oos, _suff = _formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, Minv=Minv, target_index=target_index,
            )
        except EstimatorFailure:
            continue
        pts.append(pt)
    if len(pts) < 2:
        return (None, None)
    arr = np.asarray(pts)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


# --- guards / coercion --------------------------------------------------------


def _validate_matrix(confusion_matrix, k: int) -> np.ndarray:
    try:
        M = np.array(confusion_matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            f"confusion matrix is not a numeric array: {exc}.",
        )
    if M.shape != (k, k):
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            f"confusion matrix must be {k}×{k} to match {k} outcome states; "
            f"got shape {M.shape}.",
        )
    if not np.isfinite(M).all():
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            "confusion matrix has non-finite entries.",
        )
    if (M < -_TOL).any() or (M > 1 + _TOL).any():
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            "confusion-matrix entries must be probabilities in [0, 1].",
        )
    col_sums = M.sum(axis=0)
    if not np.allclose(col_sums, 1.0, atol=1e-6):
        raise EstimatorFailure(
            "invalid_confusion_matrix",
            f"confusion matrix must be column-stochastic (each column = a true "
            f"state's observed distribution, summing to 1); column sums are "
            f"{[round(float(c), 4) for c in col_sums]}.",
        )
    return M


def _require_binary(col: pd.Series, name: str) -> None:
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            "treatment_not_binary",
            f"measurement-error correction needs a binary treatment {name!r}; "
            f"got values {sorted(vals, key=str)} (multi-value X is deferred).",
        )


def _require_discrete(col: pd.Series, name: str) -> None:
    k = col.nunique(dropna=True)
    if k > _MAX_LEVELS:
        raise EstimatorFailure(
            "continuous_adjustment",
            f"adjustment covariate {name!r} has {k} distinct values (> "
            f"{_MAX_LEVELS}); the saturated stratified correction needs a "
            f"discrete covariate.",
        )


def _as_binary(col: pd.Series) -> np.ndarray:
    return col.to_numpy().astype(bool)


def _stratum_mask(df: pd.DataFrame, vars_: tuple[str, ...], key: tuple) -> pd.Series:
    if not vars_:
        return pd.Series(np.ones(len(df), dtype=bool), index=df.index)
    mask = pd.Series(np.ones(len(df), dtype=bool), index=df.index)
    for v, val in zip(vars_, key):
        mask &= (df[v].to_numpy() == val)
    return mask


def _as_tuple(key, arity: int) -> tuple:
    if arity == 1:
        return (key,)
    return tuple(key)


def _json_key(key: tuple) -> tuple:
    return tuple(_py(v) for v in key)


def _py(v):
    """Numpy scalar / bool → JSON-safe python scalar."""
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (bool, int, float, str)) or v is None:
        return v
    return str(v)


def _stratum_sort(rec: dict):
    return (rec["arm"], [str(v) for v in rec["z"]])


def _assumptions(adjustment: tuple[str, ...], cluster: str | None) -> tuple[str, ...]:
    out = [
        "non_differential_misclassification_Y_indep_XZ_given_Ytrue",
        "known_confusion_matrix_from_validation_study",
        "confusion_matrix_invertible",
        "consistency_of_potential_outcomes",
        "positivity_every_contributing_stratum_has_support",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
