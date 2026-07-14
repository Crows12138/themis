"""Measurement-error correction numeric end — confusion-matrix inversion.

The structural layer only *flags* measurement error: an identification-path
variable whose ``measurement`` / ``observability`` text names a noisy modality
raises the ``measurement_error_concern`` gap ("regression dilution attenuates
your estimate; Themis does structural ID + gap diagnosis, not de-attenuation").
This module is the DATA counterpart for the cases where de-attenuation is
point-identified from a **known confusion matrix** (a validation study):

- a **misclassified discrete outcome** — ``estimate_measurement_correction``
  (Rogan-Gladen for the binary case);
- a **misclassified binary exposure** — ``estimate_exposure_measurement_correction``
  (the matrix method; Barron 1977, Greenland 1988, Marshall 1990). Because the
  channel acts on the exposure margin of the joint (X, Y) distribution rather
  than the outcome margin, this is a genuinely different correction (the
  recovered exposure marginal is itself an inversion, not an observed count), so
  it lives in its own estimator below — not a flag on the outcome one.

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

- **Outcome** and **binary-exposure** misclassification are both point-identified
  here. A **multi-level exposure** confusion matrix, and a **combined** (exposure
  AND outcome misclassified at once) correction, are deferred.
- **Non-differential** only. A differential matrix (per-arm / outcome-dependent
  M) changes the geometry — deferred.
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


# ==============================================================================
# Exposure (treatment) misclassification — the matrix method.
# ==============================================================================
#
# The channel now sits on the EXPOSURE. Let X* be the true binary exposure, X
# the observed (misclassified) one, both over the two states in ``states`` order.
# The 2×2 confusion matrix is column-stochastic with
#
#     M[i, j] = P(X = state_i | X* = state_j)          (each column sums to 1)
#
# Under **non-differential** exposure misclassification — X ⊥ (Y, Z) | X*, i.e.
# the SAME matrix applies regardless of the outcome and covariate stratum — the
# observed joint (X, Y) is a linear image of the true joint (X*, Y) *along the
# exposure axis*, one outcome column at a time:
#
#     [P(X=0, Y=y | z), P(X=1, Y=y | z)]ᵀ = M · [P(X*=0, Y=y | z), P(X*=1, Y=y | z)]ᵀ
#   ⇒ [P(X*=0, Y=y | z), P(X*=1, Y=y | z)]ᵀ = M⁻¹ · [P(X=0, Y=y | z), P(X=1, Y=y | z)]ᵀ
#
# Recovering the whole 2×k true joint per stratum, the corrected effect on the
# outcome target value y* is the back-door standardised risk difference of the
# *recovered true exposure*:
#
#     P(Y=y* | X*=x, z) = P(X*=x, Y=y* | z) / Σ_y P(X*=x, Y=y | z)
#     effect = Σ_z [ P(Y=y* | X*=1, z) − P(Y=y* | X*=0, z) ] · P(z)
#
# Unlike the outcome case, the denominator P(X*=x | z) is ITSELF an inversion
# (Σ over the recovered outcome columns), not an observed count — the reason this
# is a distinct estimator and not a flag. There is no ``naive/det`` shortcut:
# the exposure attenuation depends on the confounding structure, so the naive
# number is the genuine observed back-door RD on X, kept for contrast.


@dataclass(frozen=True)
class ExposureMeasurementCorrectionEstimate:
    """Confusion-matrix-corrected effect for a MISCLASSIFIED BINARY EXPOSURE.

    Mirrors :class:`MeasurementCorrectionEstimate` but inverts the channel on
    the *exposure* margin of the (X, Y) joint per covariate stratum (the matrix
    method; Barron 1977, Greenland 1988, Marshall 1990). ``point`` is the
    back-door standardised risk difference of the recovered true exposure
    ``Σ_z [P(Y=y*|X*=1,z) − P(Y=y*|X*=0,z)] P(z)``; ``naive_point`` is the same
    standardisation on the OBSERVED (misclassified) exposure — the biased number
    the correction replaces (no ``naive/det`` shortcut exists here). ``states``
    are the two exposure states in the row/column order of ``confusion_matrix``
    (``[control, treated]``); ``outcome_states`` are the k outcome states in the
    joint-table column order. ``det`` is det(M); ``out_of_simplex`` flags a
    recovered joint cell outside [0, 1]. ``sufficient_statistics`` carries the
    matrix, per-stratum full 2×k (X, Y) joint count tables, and the covariate
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
    outcome_states: tuple[object, ...]
    confusion_matrix: tuple[tuple[float, ...], ...]
    det: float
    out_of_simplex: bool
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "exposure_confusion_matrix_inversion_backdoor_standardised"
    model_assumption: str = ""


def estimate_exposure_measurement_correction(
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
) -> ExposureMeasurementCorrectionEstimate:
    """Recover the back-door effect of a misclassified binary exposure by
    inverting the confusion matrix on the exposure margin, per covariate stratum.

    Parameters
    ----------
    data: the main sample carrying the *observed* (misclassified) exposure.
    treatment / outcome: binary X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete).
    confusion_matrix: 2×2, ``M[i][j] = P(X=states[i] | X*=states[j])``, each
        column summing to 1.
    states: the two exposure states in the row/column order of
        ``confusion_matrix``, in ``[control, treated]`` order (so ``states[1]``
        is the intervened value do(X)=treated).
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y=y*)`` between the recovered exposures.
    differential: must be False; an outcome-dependent (per-Y) matrix is deferred.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (M is held fixed across resamples).

    Raises
    ------
    EstimatorFailure: differential requested; exposure states not a binary
        ``[control, treated]`` pair; observed exposure not covered by the states;
        continuous / high-cardinality outcome; continuous adjustment covariate;
        malformed / non-stochastic / singular confusion matrix; target value
        absent; a positivity violation (a contributing stratum empty in an
        observed arm); a degenerate recovered exposure marginal (≤ 0, the
        conditional risk is undefined).
    """
    if differential:
        raise EstimatorFailure(
            "differential_misclassification",
            "a differential (outcome-dependent) confusion matrix is deferred; "
            "this estimator assumes non-differential misclassification "
            "(X ⊥ (Y,Z) | X*).",
        )

    states = tuple(_py(s) for s in states)
    if len(states) != 2 or len(set(states)) != 2:
        raise EstimatorFailure(
            "exposure_not_binary",
            f"exposure misclassification needs exactly two distinct exposure "
            f"states; got {states!r} (a multi-level exposure matrix is deferred).",
        )
    if bool(states[0]) is not False or bool(states[1]) is not True:
        raise EstimatorFailure(
            "exposure_not_binary",
            f"exposure states must be a binary [control, treated] pair with a "
            f"falsy control and a truthy treated (e.g. [0, 1] or [False, True]); "
            f"got {states!r}.",
        )
    target_value = _py(target_value)

    M = _validate_matrix(confusion_matrix, 2)
    det = float(np.linalg.det(M))
    if abs(det) < _DET_FLOOR:
        raise EstimatorFailure(
            "singular_confusion_matrix",
            f"confusion matrix is non-invertible (|det| = {abs(det):.3g} < "
            f"{_DET_FLOOR:g}); the measurement carries no usable information "
            f"about the true exposure and the correction is undefined.",
        )
    Minv = np.linalg.inv(M)

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    observed_x = set(_py(v) for v in pd.unique(df[treatment].dropna()))
    if not observed_x <= set(states):
        raise EstimatorFailure(
            "exposure_not_binary",
            f"observed exposure values {sorted(map(str, observed_x))} are not "
            f"covered by the declared exposure states {states!r}.",
        )
    for v in adjustment:
        _require_discrete(df[v], v)

    outcome_states = tuple(sorted(
        (_py(v) for v in pd.unique(df[outcome].dropna())), key=str
    ))
    if len(outcome_states) < 1:
        raise EstimatorFailure(
            "empty_outcome", f"outcome {outcome!r} has no observed values.",
        )
    if len(outcome_states) > _MAX_LEVELS:
        raise EstimatorFailure(
            "continuous_outcome",
            f"outcome {outcome!r} has {len(outcome_states)} distinct values (> "
            f"{_MAX_LEVELS}); the standardised risk-difference correction needs "
            f"a discrete outcome.",
        )
    if target_value not in outcome_states:
        raise EstimatorFailure(
            "target_value_absent",
            f"query target value {target_value!r} is not among the observed "
            f"outcome values {list(outcome_states)!r}.",
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = outcome_states.index(target_value)
    point, naive, oos, suff = _exposure_formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, outcome_states=outcome_states, Minv=Minv,
        target_index=target_index,
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _exposure_bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, outcome_states=outcome_states, Minv=Minv,
            target_index=target_index, groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    assumptions = _exposure_assumptions(adjustment, cluster)
    return ExposureMeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="exposure_measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        outcome_states=outcome_states,
        confusion_matrix=tuple(tuple(float(v) for v in row) for row in M),
        det=det,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            "side": "exposure",
            "confusion_matrix": [[float(v) for v in row] for row in M],
            "states": [_py(s) for s in states],
            "outcome_states": [_py(s) for s in outcome_states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=(
            "被误分类的二值暴露 X 有验证研究给出的混淆矩阵 M（列随机，"
            "M[i][j]=P(X=state_i|X*=state_j)）。在非差异误分类假设下"
            "（X⊥(Y,Z)|X*，各结局各层同一 M）逐层沿暴露轴对每个结局列求逆"
            "恢复真实联合分布 p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z)，再用恢复的真实"
            "暴露做后门标准化 ATE=Σ_z[P(Y=y*|X*=1,z)−P(Y=y*|X*=0,z)]P(z)。"
            "暴露侧分母 P(X*=x|z) 本身也是求逆结果，故无 naive/det 捷径。"
        ),
    )


def _exposure_formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv: np.ndarray, target_index: int,
) -> tuple[float, float, bool, dict]:
    """Corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics (the full 2×k (X, Y) joint count tables).

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have observed support in BOTH exposure arms (positivity), and its
    recovered exposure marginal P(X*=x|z) must be strictly positive (else the
    conditional risk is undefined). ``out_of_simplex`` is True if any recovered
    joint cell lands outside [0, 1]."""
    k = len(outcome_states)
    xvals = df[treatment].map(_py)
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
        z_mask = _stratum_mask(df, adjustment, z_key).to_numpy()
        sub_x = xvals[z_mask].to_numpy()
        sub_y = yvals[z_mask].to_numpy()

        joint = np.zeros((2, k), dtype=float)   # rows: exposure state idx, cols: outcome
        for xi, xval in enumerate(states):
            arm_mask = sub_x == xval
            n_arm = int(arm_mask.sum())
            if n_arm == 0:
                raise EstimatorFailure(
                    "insufficient_support",
                    f"stratum X={xval!r}, z={_json_key(z_key)} has no rows "
                    f"(positivity violation); P(Y|x,z) is not estimable so the "
                    f"correction cannot standardise over it.",
                )
            sub_y_arm = sub_y[arm_mask]
            for yj, yval in enumerate(outcome_states):
                joint[xi, yj] = float(int((sub_y_arm == yval).sum()))

        Nz = joint.sum()
        p_obs = joint / Nz
        p_true = np.empty_like(p_obs)
        for yj in range(k):
            p_true[:, yj] = Minv @ p_obs[:, yj]
        if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
            oos = True

        px1 = float(p_true[1, :].sum())
        px0 = float(p_true[0, :].sum())
        if px1 <= _TOL or px0 <= _TOL:
            raise EstimatorFailure(
                "degenerate_recovered_exposure",
                f"stratum z={_json_key(z_key)} recovers a non-positive true "
                f"exposure marginal (P(X*=1|z)={px1:.3g}, P(X*=0|z)={px0:.3g}); "
                f"the conditional risk is undefined — the confusion matrix is too "
                f"weakly informative to identify the effect in this stratum.",
            )
        r1 = float(p_true[1, target_index]) / px1
        r0 = float(p_true[0, target_index]) / px0
        corrected += (r1 - r0) * p_z

        # Naive: observed-exposure back-door RD (the biased number). Row sums are
        # the observed arm sizes (both > 0 by the positivity check above).
        nr1 = float(joint[1, target_index]) / float(joint[1, :].sum())
        nr0 = float(joint[0, target_index]) / float(joint[0, :].sum())
        naive += (nr1 - nr0) * p_z

        strata_records.append({
            "z": list(_json_key(z_key)),
            "joint_counts": [[int(c) for c in row] for row in joint],
        })

    suff = {
        "strata": sorted(strata_records, key=lambda r: [str(v) for v in r["z"]]),
        "marginal_counts": [
            {"z": list(_json_key(k2)), "count": c}
            for k2, c in sorted(marginal_counts.items(), key=lambda kv: str(kv[0]))
        ],
        "marginal_total": n_total,
        "det": float(np.linalg.det(np.linalg.inv(Minv))),
    }
    return corrected, naive, oos, suff


def _exposure_bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv: np.ndarray, target_index: int, groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected effect — resample rows (or
    clusters), recompute the per-stratum correction with M held FIXED. Draws
    that induce a positivity / degenerate-recovery failure are skipped."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            pt, _naive, _oos, _suff = _exposure_formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, outcome_states=outcome_states, Minv=Minv,
                target_index=target_index,
            )
        except EstimatorFailure:
            continue
        pts.append(pt)
    if len(pts) < 2:
        return (None, None)
    arr = np.asarray(pts)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


def _exposure_assumptions(
    adjustment: tuple[str, ...], cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "non_differential_misclassification_X_indep_YZ_given_Xtrue",
        "known_confusion_matrix_from_validation_study",
        "confusion_matrix_invertible",
        "recovered_true_exposure_marginal_positive",
        "consistency_of_potential_outcomes",
        "positivity_every_contributing_stratum_has_support",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
