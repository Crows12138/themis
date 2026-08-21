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
  here, under EITHER non-differential OR **differential** misclassification:

  - non-differential — one matrix everywhere (Y ⊥ (X,Z) | Y*, resp. X ⊥ (Y,Z) | X*);
  - differential — the axis a matrix varies over is named by ``differential_by``.
    The OUTCOME channel may depend on the exposure arm (a per-arm matrix M_x,
    "detection bias", the default) or on a back-door **covariate** (a per-covariate-
    stratum matrix M_z — the rate varies by e.g. site/age). The EXPOSURE channel
    may depend on the outcome (a per-outcome-level matrix M_y, "recall bias", the
    default) or on a back-door **covariate** (a per-covariate-stratum matrix M_z).
    The correction inverts the LEVEL-SPECIFIC matrix within each conditioning
    level. Differential misclassification can bias AWAY from the null (non-
    differential only attenuates toward it), so it gets a per-level inversion
    rather than a single de-attenuation factor det(M) — no ``naive/det`` shortcut.

  A **multi-level exposure** confusion matrix, a matrix jointly differential in the
  arm/outcome AND a covariate, and a differential matrix set that does not cover
  every observed conditioning level are deferred.
- **Combined** misclassification — both channels at once — is point-identified here
  too, by inverting the per-stratum (X, Y) joint on BOTH sides,
  ``P_true = M_x⁻¹ P_obs (M_y⁻¹)ᵀ``. It carries one premise the single-channel
  corrections do not: the two error mechanisms are independent given the truth,
  ``X ⊥ Y | (X*, Y*, Z)``. Two separately non-differential channels can still be
  correlated with each other, so this is strictly stronger and is listed as its own
  assumption. A DIFFERENTIAL matrix on either channel is refused rather than
  approximated — the level that selects one matrix is the quantity the other channel
  mismeasures, so the observed table stops being a two-sided product.
- **Known** confusion matrix / matrices, treated as FIXED. The bootstrap propagates
  the main-sample sampling variability only; validation-study uncertainty in M
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
from ..types import envelope_scalar
from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
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

    Under **differential** (per-exposure-arm) misclassification ``differential`` is
    True, ``confusion_matrix`` / ``det`` are the sentinel empty / NaN (there is no
    single matrix), and ``confusion_matrices`` carries one ``(arm, matrix, det)``
    entry per treatment arm — the per-arm matrices the inversion actually used and
    the verifier re-inverts from.
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
    data_columns: tuple[str, ...]
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
    differential: bool = False
    # The variable the differential matrices vary over (the exposure arm by
    # default, or a back-door covariate); None for the non-differential case.
    differential_by: str | None = None
    # Per-level matrices when ``differential`` — a tuple of
    # (level, matrix, det); empty for the non-differential single-matrix case.
    confusion_matrices: tuple = ()
    differential_levels: tuple = ()


# --- public entry -------------------------------------------------------------


def estimate_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    confusion_matrix=None,
    states,
    target_value,
    differential: bool = False,
    differential_by: str | None = None,
    confusion_matrices=None,
    differential_levels=None,
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
    confusion_matrix: (non-differential) k×k, ``M[i][j] = P(Y=states[i] |
        Y*=states[j])``, each column summing to 1.
    states: the k outcome states in the row/column order of the confusion
        matrix/matrices (must cover every observed outcome value).
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y*=y*)``.
    differential: when True, the outcome misclassification is **differential**
        along ``differential_by`` — supply ``confusion_matrices`` +
        ``differential_levels`` instead of ``confusion_matrix``.
    differential_by: which variable the differential matrices vary over. Defaults
        to the **exposure arm** (``treatment``) — detection bias, ``M_x``. May
        instead be a back-door **covariate** in ``adjustment`` — the
        misclassification rate varies by that covariate stratum (e.g. by site),
        ``M_z``, and the correction inverts the covariate-level-specific matrix
        within each stratum.
    confusion_matrices / differential_levels: (differential) a list of k×k
        matrices and the ``differential_by`` values they apply to, aligned 1:1;
        ``M[i][j] = P(Y=states[i] | Y*=states[j], differential_by=level)``. The
        levels must cover every observed value of ``differential_by``.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (the matrices are held fixed across resamples).

    Raises
    ------
    EstimatorFailure: differential requested but the matrix set is incomplete /
        misaligned / does not cover every ``differential_by`` level; a
        ``differential_by`` that is neither the exposure nor an adjustment
        covariate; non-binary treatment; continuous adjustment covariate;
        malformed / non-stochastic / singular confusion matrix; states not
        covering the observed outcome; target value absent; a positivity violation
        (a contributing stratum empty in an arm).
    """
    states = tuple(envelope_scalar(s) for s in states)
    k = len(states)
    if k < 2:
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"need at least 2 outcome states; got {states!r}.",
        )
    if len(set(states)) != k:
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"outcome states must be distinct; got {states!r}.",
        )
    target_value = envelope_scalar(target_value)
    if target_value not in states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            f"query target value {target_value!r} is not among the declared "
            f"outcome states {states!r}.",
        )

    # The differential axis: the variable whose value selects the confusion
    # matrix. Defaults to the exposure arm (detection bias); may instead be a
    # back-door covariate (misclassification rate varies by that stratum). The
    # inverse maps are keyed by ``_level_key`` so a bool/0-1 level matches the
    # data value the contract coerced.
    Minv_by_level: dict = {}
    differential_axis: str | None = None
    if differential:
        axis = differential_by if differential_by is not None else treatment
        if axis != treatment and axis not in adjustment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_UNKNOWN,
                f"differential_by={axis!r} is neither the exposure {treatment!r} "
                f"nor a back-door adjustment covariate {refusals.describe(list(adjustment))}; the "
                f"differential axis must be a variable the correction conditions on.",
            )
        differential_axis = axis
        level_name = "exposure arm" if axis == treatment else f"covariate {axis!r}"
        prepared = _prepare_differential(
            confusion_matrices, differential_levels, k, level_name=level_name,
        )
        Minv_by_level = {_level_key(lvl): Minv for (lvl, _M, _d, Minv) in prepared}
        if axis == treatment:
            arm_bools = {bool(lvl) for (lvl, *_rest) in prepared}
            if len(prepared) != 2 or arm_bools != {False, True}:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVELS_MISMATCH,
                    "outcome differential misclassification by the exposure arm "
                    "needs `differential_levels` = the two treatment values (one "
                    f"falsy, one truthy); got {[lvl for (lvl, *_r) in prepared]!r}. "
                    "For misclassification that varies by a COVARIATE, set "
                    "`differential_by=<covariate>`.",
                )
            by_arm_records = [
                {"arm": int(bool(lvl)),
                 "matrix": [[float(v) for v in row] for row in _M],
                 "det": _d}
                for (lvl, _M, _d, _inv) in sorted(prepared, key=lambda t: bool(t[0]))
            ]
            suff_extra: dict = {
                "differential": True,
                "confusion_matrices_by_arm": by_arm_records,
            }
            matrices_out: tuple = tuple(by_arm_records)
            differential_by_out: str | None = None
            model_assumption = (
                "被误分类的离散结局 Y 有验证研究给出的**逐暴露臂**混淆矩阵 "
                "M_x（列随机，M_x[i][j]=P(Y=state_i|Y*=state_j,X=x)）。在差异误分类"
                "（detection bias，各臂矩阵不同）下，逐层用**本臂**矩阵求逆恢复真实分布 "
                "p_true(·|x,z)=M_x⁻¹p_obs(·|x,z)，再对目标值 y* 做后门标准化 "
                "ATE=Σ_z[p_true(y*|1,z)−p_true(y*|0,z)]P(z)。各臂 det(M_x) 不同，"
                "无单一去衰减因子；差异误分类可朝远离零方向偏，故须逐臂求逆。"
            )
        else:
            by_level_records = [
                {"level": envelope_scalar(lvl),
                 "matrix": [[float(v) for v in row] for row in _M],
                 "det": _d}
                for (lvl, _M, _d, _inv) in prepared
            ]
            suff_extra = {
                "differential": True,
                "differential_by": differential_axis,
                "confusion_matrices_by_level": by_level_records,
            }
            matrices_out = tuple(by_level_records)
            differential_by_out = differential_axis
            model_assumption = (
                f"被误分类的离散结局 Y 有验证研究给出的**逐协变量 {differential_axis} 分层**"
                "混淆矩阵 M_z（列随机，M_z[i][j]=P(Y=state_i|Y*=state_j,"
                f"{differential_axis}=z)）。误分类率随该协变量而异（如随测量地点/年龄），"
                "在每个后门层内用**本层**矩阵求逆恢复真实分布 p_true(·|x,z)=M_z⁻¹"
                "p_obs(·|x,z)，再对目标值 y* 做后门标准化 "
                "ATE=Σ_z[p_true(y*|1,z)−p_true(y*|0,z)]P(z)。各层 det(M_z) 不同，"
                "无单一去衰减因子；池化单矩阵会做错，故须逐层按该协变量取值求逆。"
            )
        det = float("nan")
        confusion_matrix_out: tuple = ()
    else:
        M = _validate_matrix(confusion_matrix, k)
        det = float(np.linalg.det(M))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX,
                f"confusion matrix is non-invertible (|det| = {abs(det):.3g} < "
                f"{_DET_FLOOR:g}); the measurement carries no usable information "
                f"about the true outcome and the correction is undefined.",
            )
        Minv = np.linalg.inv(M)
        differential_axis = treatment            # both arms share the one matrix
        Minv_by_level = {_level_key(False): Minv, _level_key(True): Minv}
        confusion_matrix_out = tuple(tuple(float(v) for v in row) for row in M)
        suff_extra = {
            "confusion_matrix": [[float(v) for v in row] for row in M],
            "det": det,
        }
        matrices_out = ()
        differential_by_out = None
        model_assumption = (
            "被误分类的离散结局 Y 有验证研究给出的混淆矩阵 M（列随机，"
            "M[i][j]=P(Y=state_i|Y*=state_j)）。在非差异误分类假设下"
            "（Y⊥(X,Z)|Y*，各臂各层同一 M）逐层求逆恢复真实分布 "
            "p_true(·|x,z)=M⁻¹p_obs(·|x,z)，再对目标值 y* 做后门标准化 "
            "ATE=Σ_z[p_true(y*|1,z)−p_true(y*|0,z)]P(z)。二值结局即逐层 "
            "Rogan-Gladen，去衰减因子 det(M)=Se+Sp−1。"
        )

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

    observed_states = set(
        envelope_scalar(v) for v in pd.unique(df[outcome].dropna())
    )
    missing = observed_states - set(states)
    if missing:
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE,
            values=sorted(map(str, missing)), states=states,
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = states.index(target_value)
    point, naive, oos, suff = _formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, Minv_by_level=Minv_by_level,
        differential_axis=differential_axis, target_index=target_index,
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, Minv_by_level=Minv_by_level,
            differential_axis=differential_axis, target_index=target_index,
            groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    assumptions = _assumptions(
        adjustment, cluster, differential=differential,
        differential_axis=differential_axis, treatment=treatment,
    )
    return MeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        confusion_matrix=confusion_matrix_out,
        det=det,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            **suff_extra,
            "states": [envelope_scalar(s) for s in states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=model_assumption,
        differential=differential,
        differential_by=differential_by_out,
        confusion_matrices=matrices_out,
        differential_levels=(
            tuple(envelope_scalar(v) for v in differential_levels)
            if differential else ()
        ),
    )


# --- formula core -------------------------------------------------------------


def _formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, Minv_by_level: dict,
    differential_axis: str, target_index: int,
) -> tuple[float, float, bool, dict]:
    """Corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics.

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have support in BOTH arms (positivity). Each (arm, z) cell is inverted
    with the matrix selected by ``differential_axis``'s value in that cell:
    ``Minv_by_level[_level_key(value)]`` — the same matrix everywhere in the
    non-differential case, per-arm under detection bias, per-covariate-stratum
    when the differential axis is a covariate. ``out_of_simplex`` is True if any
    recovered p_true component lands outside [0, 1]."""
    x = _as_binary(df[treatment])
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)              # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    # One name for one fact: ``None`` IS "the axis is the exposure arm", so
    # the position of the axis column carries the branch as well.
    axis_idx = (
        None if differential_axis == treatment
        else adjustment.index(differential_axis)
    )

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
                    Refusal.INSUFFICIENT_SUPPORT,
                    f"stratum X={arm}, z={_json_key(z_key)} has no rows "
                    f"(positivity violation); P(Y|x,z) is not estimable so the "
                    f"correction cannot standardise over it.",
                )
            counts = _value_counts(yvals[mask.to_numpy()], states)
            p_obs = counts.astype(float) / n
            lvl_value = (
                bool(arm) if axis_idx is None
                else envelope_scalar(z_key[axis_idx])
            )
            Minv = Minv_by_level.get(_level_key(lvl_value))
            if Minv is None:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVEL_UNCOVERED,
                    axis=differential_axis, level=lvl_value,
                )
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
    adjustment: tuple[str, ...], states: tuple, Minv_by_level: dict,
    differential_axis: str, target_index: int, groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected effect — resample rows (or
    clusters), recompute the per-stratum correction with the matrix/matrices held
    FIXED, collect the point. Draws that induce a positivity failure are
    skipped."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            pt, _naive, _oos, _suff = _formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, Minv_by_level=Minv_by_level,
                differential_axis=differential_axis, target_index=target_index,
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


def _validate_matrix(confusion_matrix, k: int, *, label: str | None = None) -> np.ndarray:
    """``label`` names the channel when more than one matrix is in play, so a
    rejection says WHICH one is malformed instead of leaving the caller to
    guess."""
    what = f"{label} confusion matrix" if label else "confusion matrix"
    noun = f"{label} states" if label else "outcome states"
    try:
        M = np.array(confusion_matrix, dtype=float)
    except (TypeError, ValueError) as exc:
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"{what} is not a numeric array: {exc}.",
        )
    if M.shape != (k, k):
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"{what} must be {k}×{k} to match {k} {noun}; "
            f"got shape {M.shape}.",
        )
    if not np.isfinite(M).all():
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"{what} has non-finite entries.",
        )
    if (M < -_TOL).any() or (M > 1 + _TOL).any():
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"{what} entries must be probabilities in [0, 1].",
        )
    col_sums = M.sum(axis=0)
    if not np.allclose(col_sums, 1.0, atol=1e-6):
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"{what} must be column-stochastic (each column = a true "
            f"state's observed distribution, summing to 1); column sums are "
            f"{[round(float(c), 4) for c in col_sums]}.",
        )
    return M


def _level_key(v):
    """Value-based hashable key for a conditioning-variable level.

    Conditioning levels are matched to observed data values BY VALUE, so a bool
    is collapsed onto its numeric image (``False`` ≡ ``0``, ``True`` ≡ ``1``) —
    the data contract coerces a binary column to bool, and a caller who wrote the
    levels as ``[0, 1]`` must still match. This is deliberately the opposite of
    the verifier's type-strict ``_state_key``: here 0 and False are the same
    conditioning level; a caller who lists both is flagged as a duplicate."""
    if isinstance(v, bool):
        return ("n", float(v))
    if isinstance(v, (int, float)):
        return ("n", float(v))
    return ("s", str(v))


def _prepare_differential(confusion_matrices, differential_levels, k: int, *,
                          level_name: str) -> list[tuple]:
    """Validate a differential (per-level) matrix set: a list of column-stochastic,
    invertible k×k matrices aligned 1:1 with a list of conditioning-variable
    levels. Returns ``[(level_py, M, det, Minv), ...]`` in the given order.

    Raises ``EstimatorFailure`` on a missing / misaligned / malformed / singular
    set — never falls back to a single matrix."""
    if confusion_matrices is None or differential_levels is None:
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_SPEC_INCOMPLETE,
            "differential misclassification needs both `confusion_matrices` and "
            "`differential_levels` (one matrix per conditioning level); got "
            f"confusion_matrices={confusion_matrices!r}, "
            f"differential_levels={differential_levels!r}.",
        )
    mats = list(confusion_matrices)
    levels = [envelope_scalar(v) for v in differential_levels]
    if len(mats) != len(levels):
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_LEVELS_MISMATCH,
            f"got {len(mats)} confusion matrices but {len(levels)} {level_name} "
            f"levels; they must align 1:1.",
        )
    if len(mats) < 2:
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_SPEC_INCOMPLETE,
            f"differential misclassification needs at least 2 {level_name} levels; "
            f"got {levels!r}.",
        )
    if len({_level_key(v) for v in levels}) != len(levels):
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_LEVELS_MISMATCH,
            f"{level_name} levels must be distinct; got {levels!r}.",
        )
    out: list[tuple] = []
    for lvl, cm in zip(levels, mats):
        M = _validate_matrix(cm, k)
        det = float(np.linalg.det(M))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX,
                f"the confusion matrix for {level_name}={lvl!r} is non-invertible "
                f"(|det|={abs(det):.3g} < {_DET_FLOOR:g}); the correction is "
                f"undefined in that level.",
            )
        out.append((lvl, M, det, np.linalg.inv(M)))
    return out


def _require_binary(col: pd.Series, name: str) -> None:
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            Refusal.TREATMENT_NOT_BINARY,
            f"measurement-error correction needs a binary treatment {name!r}; "
            f"got values {refusals.describe(sorted(vals, key=str))} "
            f"(multi-value X is deferred).",
        )


def _require_discrete(col: pd.Series, name: str) -> None:
    k = col.nunique(dropna=True)
    if k > _MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_ADJUSTMENT,
            column=name, levels=k, cap=_MAX_LEVELS,
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
    return tuple(envelope_scalar(v) for v in key)


def _stratum_sort(rec: dict):
    return (rec["arm"], [str(v) for v in rec["z"]])


def _assumptions(
    adjustment: tuple[str, ...], cluster: str | None, *, differential: bool = False,
    differential_axis: str | None = None, treatment: str | None = None,
) -> tuple[str, ...]:
    """The premises this correction rests on, including WHICH axis it varied on.

    Same shape as :func:`_exposure_assumptions`, and it was not: this one took
    only ``differential: bool``, so the string it could write was fixed at the
    default axis. The exposure arm is only the default — the outcome channel's
    matrix may vary over a back-door covariate instead — and a boolean has
    nowhere to put which, so a run that inverted a per-stratum matrix set
    disclosed itself as a per-arm one. That is not a mis-worded string but a
    signature that cannot say what the function exists to say, which is why
    the fix is the parameter rather than a branch on top of it.
    """
    if not differential:
        mech = "non_differential_misclassification_Y_indep_XZ_given_Ytrue"
        known = "known_confusion_matrix_from_validation_study"
    elif differential_axis is None or differential_axis == treatment:
        mech = "differential_misclassification_by_exposure_arm_M_depends_on_X"
        known = "known_per_arm_confusion_matrices_from_validation_study"
    else:
        mech = f"differential_misclassification_by_covariate_{differential_axis}"
        known = "known_per_covariate_stratum_confusion_matrices_from_validation_study"
    out = [
        mech,
        known,
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

    Under **differential** exposure misclassification ``differential`` is True,
    ``confusion_matrix`` / ``det`` are the sentinel empty / NaN, and
    ``confusion_matrices`` carries the per-level matrices the inversion used. The
    differential axis is named by ``differential_by``: by the **outcome** (recall
    bias, the default — one ``(outcome_value, matrix, det)`` entry per outcome
    level, the joint's column for outcome y inverted with M_y) or by a back-door
    **covariate** (the matrix varies by e.g. site — one ``(level, matrix, det)``
    entry per covariate level, every column within a stratum inverted with that
    stratum's M_z).
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
    data_columns: tuple[str, ...]
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
    differential: bool = False
    # The variable the differential matrices vary over (the outcome by default —
    # recall bias — or a back-door covariate); None for the non-differential case.
    differential_by: str | None = None
    # Per-level matrices when ``differential`` — a tuple of (level, matrix, det);
    # empty for the non-differential case.
    confusion_matrices: tuple = ()
    differential_levels: tuple = ()


def estimate_exposure_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    confusion_matrix=None,
    states,
    target_value,
    differential: bool = False,
    differential_by: str | None = None,
    confusion_matrices=None,
    differential_levels=None,
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
    confusion_matrix: (non-differential) 2×2, ``M[i][j] = P(X=states[i] |
        X*=states[j])``, each column summing to 1.
    states: the two exposure states in the row/column order of the confusion
        matrix/matrices, in ``[control, treated]`` order (so ``states[1]`` is the
        intervened value do(X)=treated).
    target_value: the query's target outcome value y* — the effect is the
        corrected risk difference of ``P(Y=y*)`` between the recovered exposures.
    differential: when True, the exposure misclassification is **differential**
        along ``differential_by`` — supply ``confusion_matrices`` +
        ``differential_levels`` instead of ``confusion_matrix``.
    differential_by: which variable the differential matrices vary over. Defaults
        to the **outcome** (recall bias, ``M_y``). May instead be a back-door
        adjustment covariate, in which case the exposure-misclassification rate
        varies by that covariate stratum (e.g. by measurement site), and the
        matrix that inverts a stratum's joint is that stratum's own ``M_z``.
    confusion_matrices / differential_levels: (differential) a list of 2×2
        matrices and the ``differential_by`` values they apply to, aligned 1:1;
        ``M[i][j] = P(X=states[i] | X*=states[j], differential_by=level)``. By the
        outcome the levels must be exactly the observed outcome values (each
        outcome column inverted with its M_y); by a covariate they must cover
        every observed covariate value (each stratum inverted with its M_z).
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (the matrices are held fixed across resamples).

    Raises
    ------
    EstimatorFailure: differential requested but the matrix set is incomplete /
        misaligned / does not cover every observed differential level; a
        ``differential_by`` that is neither the outcome nor an adjustment
        covariate; exposure states not a binary ``[control, treated]`` pair;
        observed exposure not covered by the states; continuous / high-cardinality
        outcome; continuous adjustment covariate; malformed / non-stochastic /
        singular confusion matrix; target value absent; a positivity violation (a
        contributing stratum empty in an observed arm); a degenerate recovered
        exposure marginal (≤ 0, the conditional risk is undefined).
    """
    states = tuple(envelope_scalar(s) for s in states)
    if len(states) != 2 or len(set(states)) != 2:
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"exposure misclassification needs exactly two distinct exposure "
            f"states; got {states!r} (a multi-level exposure matrix is deferred).",
        )
    if bool(states[0]) is not False or bool(states[1]) is not True:
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"exposure states must be a binary [control, treated] pair with a "
            f"falsy control and a truthy treated (e.g. [0, 1] or [False, True]); "
            f"got {states!r}.",
        )
    target_value = envelope_scalar(target_value)

    # Non-differential: validate the single matrix now. Differential: the matrices
    # are keyed by outcome value, so they are prepared AFTER the observed outcome
    # levels are read from the data (below), to check coverage.
    if not differential:
        M = _validate_matrix(confusion_matrix, 2)
        det = float(np.linalg.det(M))
        if abs(det) < _DET_FLOOR:
            raise EstimatorFailure(
                Refusal.SINGULAR_CONFUSION_MATRIX,
                f"confusion matrix is non-invertible (|det| = {abs(det):.3g} < "
                f"{_DET_FLOOR:g}); the measurement carries no usable information "
                f"about the true exposure and the correction is undefined.",
            )
        Minv = np.linalg.inv(M)
    else:
        # No single ``M`` here at all: the per-level set is prepared below,
        # once the observed outcome levels are known.
        det = float("nan")

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    observed_x = set(
        envelope_scalar(v) for v in pd.unique(df[treatment].dropna())
    )
    if not observed_x <= set(states):
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"observed exposure values {refusals.describe(sorted(map(str, observed_x)))} are not "
            f"covered by the declared exposure states {states!r}.",
        )
    for v in adjustment:
        _require_discrete(df[v], v)

    outcome_states = tuple(sorted(
        (envelope_scalar(v) for v in pd.unique(df[outcome].dropna())), key=str
    ))
    if len(outcome_states) < 1:
        raise EstimatorFailure(Refusal.EMPTY_OUTCOME, outcome=outcome)
    if len(outcome_states) > _MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_OUTCOME,
            outcome=outcome, states=len(outcome_states), cap=_MAX_LEVELS,
        )
    if target_value not in outcome_states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            f"query target value {target_value!r} is not among the observed "
            f"outcome values {refusals.describe(list(outcome_states))}.",
        )

    # Build the inverse-matrix map. Non-differential: the same M for every column
    # and stratum. Differential: distinct matrices along ``differential_by`` — by
    # the OUTCOME (recall bias, the default; a distinct M_y per outcome level, each
    # outcome column inverted with its own matrix) or by a back-door COVARIATE (the
    # rate varies by e.g. site; a distinct M_z per covariate level, every column in
    # a stratum inverted with that stratum's matrix). Maps are keyed by
    # ``_level_key`` so a bool/0-1 level matches the value the contract coerced.
    differential_axis: str | None = None
    if differential:
        axis = differential_by if differential_by is not None else outcome
        if axis == treatment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_UNKNOWN,
                f"differential_by={axis!r} is the mismeasured exposure itself; the "
                f"exposure confusion matrix is already indexed by the true exposure "
                f"state. The exposure channel may be differential by the OUTCOME "
                f"(recall bias, the default) or by a back-door covariate; set "
                f"differential_by to one of those.",
            )
        if axis != outcome and axis not in adjustment:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_BY_UNKNOWN,
                f"differential_by={axis!r} is neither the outcome {outcome!r} nor a "
                f"back-door adjustment covariate {refusals.describe(list(adjustment))}; the "
                f"differential axis must be a variable the correction conditions on.",
            )
        differential_axis = axis
        axis_is_outcome = axis == outcome
        level_name = "outcome value" if axis_is_outcome else f"covariate {axis!r}"
        prepared = _prepare_differential(
            confusion_matrices, differential_levels, 2, level_name=level_name,
        )
        Minv_by_level = {_level_key(lvl): Minv for (lvl, _M, _d, Minv) in prepared}
        if axis_is_outcome:
            # Recall bias: map each supplied level onto the canonical observed
            # outcome value (by value — the contract may have coerced Y to bool),
            # and require the set to cover every observed outcome level exactly.
            canon = {_level_key(y): y for y in outcome_states}
            level_keys = {_level_key(lvl) for (lvl, *_r) in prepared}
            if level_keys != set(canon):
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVELS_MISMATCH,
                    "exposure differential misclassification by the outcome: "
                    "`differential_levels` must be exactly the observed outcome "
                    f"values {refusals.describe(list(outcome_states))}; got "
                    f"{[lvl for (lvl, *_r) in prepared]!r}. For misclassification "
                    f"that varies by a COVARIATE, set `differential_by=<covariate>`.",
                )
            by_outcome_records = sorted(
                ({"outcome": canon[_level_key(lvl)],
                  "matrix": [[float(v) for v in row] for row in _M],
                  "det": _d}
                 for (lvl, _M, _d, _inv) in prepared),
                key=lambda r: str(r["outcome"]),
            )
            suff_extra: dict = {
                "differential": True,
                "confusion_matrices_by_outcome": by_outcome_records,
            }
            matrices_out: tuple = tuple(by_outcome_records)
            differential_by_out: str | None = None
            model_assumption = (
                "被误分类的二值暴露 X 有验证研究给出的**逐结局**混淆矩阵 "
                "M_y（列随机，M_y[i][j]=P(X=state_i|X*=state_j,Y=y)）。在差异误分类"
                "（recall bias，各结局矩阵不同）下，逐层沿暴露轴对结局 y 的列用**本结局**"
                "矩阵 M_y⁻¹ 求逆恢复真实联合分布，再用恢复的真实暴露做后门标准化 "
                "ATE=Σ_z[P(Y=y*|X*=1,z)−P(Y=y*|X*=0,z)]P(z)。暴露侧分母 P(X*=x|z) "
                "本身也是求逆结果，故无 naive/det 捷径；差异误分类可朝远离零方向偏。"
            )
        else:
            # Covariate-differential: coverage of every observed covariate value is
            # enforced per stratum in ``_exposure_formula`` (differential_level_
            # uncovered), so an unused extra matrix is harmless.
            by_level_records = [
                {"level": envelope_scalar(lvl),
                 "matrix": [[float(v) for v in row] for row in _M],
                 "det": _d}
                for (lvl, _M, _d, _inv) in prepared
            ]
            suff_extra = {
                "differential": True,
                "differential_by": differential_axis,
                "confusion_matrices_by_level": by_level_records,
            }
            matrices_out = tuple(by_level_records)
            differential_by_out = differential_axis
            model_assumption = (
                f"被误分类的二值暴露 X 有验证研究给出的**逐协变量 {differential_axis} 分层**"
                "混淆矩阵 M_z（列随机，M_z[i][j]=P(X=state_i|X*=state_j,"
                f"{differential_axis}=z)）。暴露误分类率随该协变量而异（如随测量地点），"
                "在每个后门层内用**本层**矩阵 M_z⁻¹ 对每个结局列求逆恢复真实联合分布 "
                "p_true(X*,Y|z)=M_z⁻¹p_obs(X,Y|z)，再用恢复的真实暴露做后门标准化 "
                "ATE=Σ_z[P(Y=y*|X*=1,z)−P(Y=y*|X*=0,z)]P(z)。各层 M_z 不同，"
                "池化单矩阵会做错；暴露侧分母 P(X*=x|z) 本身也是求逆结果，故无 naive/det 捷径。"
            )
        confusion_matrix_out: tuple = ()
    else:
        Minv_by_level = {_level_key(y): Minv for y in outcome_states}
        differential_axis = outcome
        confusion_matrix_out = tuple(tuple(float(v) for v in row) for row in M)
        suff_extra = {
            "confusion_matrix": [[float(v) for v in row] for row in M],
            "det": det,
        }
        matrices_out = ()
        differential_by_out = None
        model_assumption = (
            "被误分类的二值暴露 X 有验证研究给出的混淆矩阵 M（列随机，"
            "M[i][j]=P(X=state_i|X*=state_j)）。在非差异误分类假设下"
            "（X⊥(Y,Z)|X*，各结局各层同一 M）逐层沿暴露轴对每个结局列求逆"
            "恢复真实联合分布 p_true(X*,Y|z)=M⁻¹p_obs(X,Y|z)，再用恢复的真实"
            "暴露做后门标准化 ATE=Σ_z[P(Y=y*|X*=1,z)−P(Y=y*|X*=0,z)]P(z)。"
            "暴露侧分母 P(X*=x|z) 本身也是求逆结果，故无 naive/det 捷径。"
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = outcome_states.index(target_value)
    point, naive, oos, suff = _exposure_formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=states, outcome_states=outcome_states,
        Minv_by_level=Minv_by_level, differential_axis=differential_axis,
        target_index=target_index,
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _exposure_bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=states, outcome_states=outcome_states,
            Minv_by_level=Minv_by_level, differential_axis=differential_axis,
            target_index=target_index, groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    assumptions = _exposure_assumptions(
        adjustment, cluster, differential=differential,
        differential_axis=differential_axis, outcome=outcome,
    )
    return ExposureMeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="exposure_measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=states,
        outcome_states=outcome_states,
        confusion_matrix=confusion_matrix_out,
        det=det,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            **suff_extra,
            "side": "exposure",
            "states": [envelope_scalar(s) for s in states],
            "outcome_states": [envelope_scalar(s) for s in outcome_states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=model_assumption,
        differential=differential,
        differential_by=differential_by_out,
        confusion_matrices=matrices_out,
        differential_levels=(
            tuple(envelope_scalar(v) for v in differential_levels)
            if differential else ()
        ),
    )


def _exposure_formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv_by_level: dict, differential_axis: str, target_index: int,
) -> tuple[float, float, bool, dict]:
    """Corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics (the full 2×k (X, Y) joint count tables).

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have observed support in BOTH exposure arms (positivity), and its
    recovered exposure marginal P(X*=x|z) must be strictly positive (else the
    conditional risk is undefined). Each column of a stratum's joint is inverted
    with the matrix selected by ``differential_axis``'s value:
    ``Minv_by_level[_level_key(value)]`` — the same matrix for every column in the
    non-differential case, a distinct M_y per outcome column under recall bias
    (axis = the outcome), a single per-stratum M_z applied to every column when
    the axis is a covariate (its value read from ``z_key``). ``out_of_simplex``
    is True if any recovered joint cell lands outside [0, 1]."""
    k = len(outcome_states)
    xvals = df[treatment].map(envelope_scalar)
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)              # {z_key: prob}
    marginal_counts = _marginal_counts(df, adjustment)  # {z_key: count}

    # One name for one fact: ``None`` IS "the axis is the outcome", so the
    # position of the axis column carries the branch as well.
    axis_idx = (
        None if differential_axis == outcome
        else adjustment.index(differential_axis)
    )

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
                    Refusal.INSUFFICIENT_SUPPORT,
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
            lvl_value = (
                outcome_states[yj] if axis_idx is None
                else envelope_scalar(z_key[axis_idx])
            )
            Minv = Minv_by_level.get(_level_key(lvl_value))
            if Minv is None:
                raise EstimatorFailure(
                    Refusal.DIFFERENTIAL_LEVEL_UNCOVERED,
                    axis=differential_axis, level=lvl_value,
                )
            p_true[:, yj] = Minv @ p_obs[:, yj]
        if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
            oos = True

        px1 = float(p_true[1, :].sum())
        px0 = float(p_true[0, :].sum())
        if px1 <= _TOL or px0 <= _TOL:
            raise EstimatorFailure(
                Refusal.DEGENERATE_RECOVERED_EXPOSURE,
                stratum=_json_key(z_key), p_treated=px1, p_control=px0,
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
    }
    return corrected, naive, oos, suff


def _exposure_bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Minv_by_level: dict, differential_axis: str, target_index: int,
    groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected effect — resample rows (or
    clusters), recompute the per-stratum correction with the matrix/matrices held
    FIXED. Draws that induce a positivity / degenerate-recovery failure are
    skipped."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        sub = df.iloc[idx]
        try:
            pt, _naive, _oos, _suff = _exposure_formula(
                sub, treatment=treatment, outcome=outcome, adjustment=adjustment,
                states=states, outcome_states=outcome_states,
                Minv_by_level=Minv_by_level, differential_axis=differential_axis,
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
    adjustment: tuple[str, ...], cluster: str | None, *, differential: bool = False,
    differential_axis: str | None = None, outcome: str | None = None,
) -> tuple[str, ...]:
    if not differential:
        mech = "non_differential_misclassification_X_indep_YZ_given_Xtrue"
        known = "known_confusion_matrix_from_validation_study"
    elif differential_axis == outcome:
        mech = "differential_misclassification_by_outcome_M_depends_on_Y"
        known = "known_per_outcome_confusion_matrices_from_validation_study"
    else:
        mech = f"differential_misclassification_by_covariate_{differential_axis}"
        known = "known_per_covariate_stratum_confusion_matrices_from_validation_study"
    out = [
        mech,
        known,
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


# ==============================================================================
# Combined misclassification — both channels at once.
# ==============================================================================
#
# The exposure and the outcome are BOTH measured with error, each with its own
# validated column-stochastic matrix over its own states:
#
#     M_x[a, a*] = P(X = state_a  | X* = state_a*)        (2×2)
#     M_y[b, b*] = P(Y = ystate_b | Y* = ystate_b*)       (k×k)
#
# Correcting one channel and shipping the number leaves the other channel's bias
# in place, which is why the two single-channel estimators refuse to run
# together. Composing them needs one premise neither of them makes on its own:
# the two error mechanisms are INDEPENDENT GIVEN THE TRUTH,
#
#     X ⊥ Y | (X*, Y*, Z)
#
# — the recorder who mis-transcribes the exposure does not thereby become more
# likely to mis-transcribe the outcome. Two separately non-differential channels
# can still be correlated with each other; this is strictly stronger, and it is
# what makes the observed table a two-sided linear image of the true one. Within
# a covariate stratum,
#
#     P_obs(z)[a, b] = Σ_{a*, b*} M_x[a, a*] M_y[b, b*] P_true(z)[a*, b*]
#                    = ( M_x · P_true(z) · M_yᵀ )[a, b]
#   ⇒ P_true(z)      = M_x⁻¹ · P_obs(z) · (M_y⁻¹)ᵀ
#
# so the correction is the exposure-side inversion on the left composed with the
# outcome-side inversion on the right, on the SAME 2×k joint table. The effect is
# then the exposure side's standardisation over the recovered joint:
#
#     P(Y*=y* | X*=x, z) = P_true(z)[x, y*] / Σ_b P_true(z)[x, b]
#     effect = Σ_z [ P(Y*=y* | X*=1, z) − P(Y*=y* | X*=0, z) ] · P(z)
#
# Neither channel may be DIFFERENTIAL here, and the reason is structural rather
# than budgetary: detection bias makes M_y depend on the exposure arm and recall
# bias makes M_x depend on the outcome, so the level that selects one matrix is
# the very quantity the other channel is mismeasuring. The observed table is then
# no longer M_x P_true M_yᵀ — the map stays linear in the 2k unknowns but is not
# a two-sided product, and inverting it as one would return a wrong number rather
# than a refusal.


@dataclass(frozen=True)
class CombinedMeasurementCorrectionEstimate:
    """Effect corrected for misclassification in BOTH the exposure and the outcome.

    ``point`` is the back-door standardised risk difference over the doubly
    recovered joint, ``Σ_z [P(Y*=y*|X*=1,z) − P(Y*=y*|X*=0,z)] P(z)``;
    ``naive_point`` is the same standardisation on the observed (doubly biased)
    table — the number the correction replaces. There is no single ``det``: each
    channel has its own, and ``det_joint = det(M_x)^k · det(M_y)^2`` is the
    determinant of the composed 2k×2k map, i.e. how much information the two
    channels destroy together. ``out_of_simplex`` flags a recovered joint cell
    outside [0, 1] — reported, never clipped, since it is the signal that the
    data refute the declared matrices. ``sufficient_statistics`` carries both
    matrices, the per-stratum 2×k observed joint count tables and the covariate
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
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    target_value: object
    states: tuple[object, ...]
    outcome_states: tuple[object, ...]
    exposure_confusion_matrix: tuple[tuple[float, ...], ...]
    outcome_confusion_matrix: tuple[tuple[float, ...], ...]
    det_exposure: float
    det_outcome: float
    det_joint: float
    out_of_simplex: bool
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "combined_confusion_matrix_inversion_backdoor_standardised"
    model_assumption: str = ""


def estimate_combined_measurement_correction(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    exposure_confusion_matrix,
    exposure_states,
    outcome_confusion_matrix,
    outcome_states,
    target_value,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> CombinedMeasurementCorrectionEstimate:
    """Recover the back-door effect when the binary exposure AND the discrete
    outcome are both misclassified, by inverting both channels of the per-stratum
    (X, Y) joint.

    Parameters
    ----------
    data: the main sample carrying both *observed* (misclassified) columns.
    treatment / outcome: binary X and discrete Y column names.
    adjustment: the back-door adjustment covariates Z (discrete, measured
        without error — a mismeasured covariate is a different channel).
    exposure_confusion_matrix: 2×2, ``M_x[i][j] = P(X=exposure_states[i] |
        X*=exposure_states[j])``, each column summing to 1.
    exposure_states: the two exposure states in ``[control, treated]`` order.
    outcome_confusion_matrix: k×k, ``M_y[i][j] = P(Y=outcome_states[i] |
        Y*=outcome_states[j])``, each column summing to 1.
    outcome_states: the k outcome states in the row/column order of
        ``outcome_confusion_matrix`` (must cover every observed outcome value).
    target_value: the query's target TRUE outcome value y*.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (both matrices are held fixed across resamples).

    Raises
    ------
    EstimatorFailure: exposure states not a binary ``[control, treated]`` pair;
        observed exposure not covered by them; outcome states not covering the
        observed outcome; target value absent; a high-cardinality outcome;
        continuous adjustment covariate; a malformed, non-stochastic or singular
        matrix on either channel; a positivity violation (a contributing stratum
        empty in an observed arm); a degenerate recovered true-exposure marginal.
    """
    exposure_states = tuple(envelope_scalar(s) for s in exposure_states)
    if len(exposure_states) != 2 or len(set(exposure_states)) != 2:
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"combined misclassification needs exactly two distinct exposure "
            f"states; got {exposure_states!r} (a multi-level exposure matrix is "
            f"deferred).",
        )
    if bool(exposure_states[0]) is not False or bool(exposure_states[1]) is not True:
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"exposure states must be a binary [control, treated] pair with a "
            f"falsy control and a truthy treated (e.g. [0, 1] or [False, True]); "
            f"got {exposure_states!r}.",
        )

    outcome_states = tuple(envelope_scalar(s) for s in outcome_states)
    k = len(outcome_states)
    if k < 2:
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"need at least 2 outcome states; got {outcome_states!r}.",
        )
    if len(set(outcome_states)) != k:
        raise EstimatorFailure(
            Refusal.INVALID_CONFUSION_MATRIX,
            f"outcome states must be distinct; got {outcome_states!r}.",
        )
    if k > _MAX_LEVELS:
        raise EstimatorFailure(
            Refusal.CONTINUOUS_OUTCOME,
            outcome=outcome, states=k, cap=_MAX_LEVELS,
        )
    target_value = envelope_scalar(target_value)
    if target_value not in outcome_states:
        raise EstimatorFailure(
            Refusal.TARGET_VALUE_ABSENT,
            f"query target value {target_value!r} is not among the declared "
            f"outcome states {outcome_states!r}.",
        )

    Mx = _validate_matrix(exposure_confusion_matrix, 2, label="exposure")
    det_x = float(np.linalg.det(Mx))
    if abs(det_x) < _DET_FLOOR:
        raise EstimatorFailure(
            Refusal.SINGULAR_CONFUSION_MATRIX,
            f"the EXPOSURE confusion matrix is non-invertible (|det| = "
            f"{abs(det_x):.3g} < {_DET_FLOOR:g}); the measurement carries no "
            f"usable information about the true exposure and the correction is "
            f"undefined.",
        )
    My = _validate_matrix(outcome_confusion_matrix, k, label="outcome")
    det_y = float(np.linalg.det(My))
    if abs(det_y) < _DET_FLOOR:
        raise EstimatorFailure(
            Refusal.SINGULAR_CONFUSION_MATRIX,
            f"the OUTCOME confusion matrix is non-invertible (|det| = "
            f"{abs(det_y):.3g} < {_DET_FLOOR:g}); the measurement carries no "
            f"usable information about the true outcome and the correction is "
            f"undefined.",
        )
    Mx_inv = np.linalg.inv(Mx)
    My_inv = np.linalg.inv(My)
    # The composed map on the 2k-vector of joint cells is the Kronecker product,
    # so its determinant factorises — one honest number for how much the two
    # channels destroy together, which neither det reports on its own.
    det_joint = float(det_x ** k * det_y ** 2)

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    observed_x = set(
        envelope_scalar(v) for v in pd.unique(df[treatment].dropna())
    )
    if not observed_x <= set(exposure_states):
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_BINARY,
            f"observed exposure values {refusals.describe(sorted(map(str, observed_x)))} are not "
            f"covered by the declared exposure states {exposure_states!r}.",
        )
    for v in adjustment:
        _require_discrete(df[v], v)

    observed_y = set(
        envelope_scalar(v) for v in pd.unique(df[outcome].dropna())
    )
    missing = observed_y - set(outcome_states)
    if missing:
        raise EstimatorFailure(
            Refusal.STATES_INCOMPLETE,
            values=sorted(map(str, missing)), states=outcome_states,
        )

    groups = (
        cluster_labels(df, cluster, expected_n=len(df))
        if cluster is not None else None
    )

    target_index = outcome_states.index(target_value)
    point, naive, oos, suff = _combined_formula(
        df, treatment=treatment, outcome=outcome, adjustment=adjustment,
        states=exposure_states, outcome_states=outcome_states,
        Mx_inv=Mx_inv, My_inv=My_inv, target_index=target_index,
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _combined_bootstrap(
            df, treatment=treatment, outcome=outcome, adjustment=adjustment,
            states=exposure_states, outcome_states=outcome_states,
            Mx_inv=Mx_inv, My_inv=My_inv, target_index=target_index,
            groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    model_assumption = (
        "二值暴露 X 与离散结局 Y **同时**被误分类，各有验证研究给出的列随机混淆矩阵 "
        "M_x（M_x[i][j]=P(X=state_i|X*=state_j)）与 M_y"
        "（M_y[i][j]=P(Y=state_i|Y*=state_j)）。除两条通道各自的非差异假设外，还需"
        "**两条误差机制在真值下相互独立**：X⊥Y|(X*,Y*,Z)——两条各自非差异的通道仍可能"
        "彼此相关，这是严格更强的前提，也正是它让观测联合成为真实联合的双边线性像："
        "P_obs(z)=M_x·P_true(z)·M_yᵀ，故 P_true(z)=M_x⁻¹·P_obs(z)·(M_y⁻¹)ᵀ。"
        "再用恢复的真实暴露与真实结局做后门标准化 "
        "ATE=Σ_z[P(Y*=y*|X*=1,z)−P(Y*=y*|X*=0,z)]P(z)。"
        "只校正一条通道会留下另一条的偏倚；合成映射的行列式 "
        "det=det(M_x)^k·det(M_y)² 是两条通道共同销毁的信息量。"
    )
    assumptions = _combined_assumptions(adjustment, cluster)
    return CombinedMeasurementCorrectionEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="combined_measurement_error_correction",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        target_value=target_value,
        states=exposure_states,
        outcome_states=outcome_states,
        exposure_confusion_matrix=tuple(
            tuple(float(v) for v in row) for row in Mx
        ),
        outcome_confusion_matrix=tuple(
            tuple(float(v) for v in row) for row in My
        ),
        det_exposure=det_x, det_outcome=det_y, det_joint=det_joint,
        out_of_simplex=oos,
        sufficient_statistics={
            **suff,
            "side": "combined",
            "exposure_confusion_matrix": [[float(v) for v in row] for row in Mx],
            "outcome_confusion_matrix": [[float(v) for v in row] for row in My],
            "det_exposure": det_x,
            "det_outcome": det_y,
            "det_joint": det_joint,
            "states": [envelope_scalar(s) for s in exposure_states],
            "outcome_states": [envelope_scalar(s) for s in outcome_states],
            "target_value": target_value,
            "target_index": target_index,
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=model_assumption,
    )


def _combined_formula(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Mx_inv: np.ndarray, My_inv: np.ndarray, target_index: int,
) -> tuple[float, float, bool, dict]:
    """Doubly corrected + naive standardised effect on the target value, plus the
    per-stratum sufficient statistics (the full 2×k observed (X, Y) joint tables).

    Enumeration is driven by the covariate marginal P(z); each contributing z
    must have observed support in BOTH exposure arms (positivity), and its
    recovered true-exposure marginal must be strictly positive (else the
    conditional risk is undefined). Each stratum's joint is inverted on both
    sides at once — ``M_x⁻¹ P_obs (M_y⁻¹)ᵀ`` — so neither channel's bias
    survives into the standardisation. ``out_of_simplex`` is True if any
    recovered cell lands outside [0, 1]."""
    k = len(outcome_states)
    xvals = df[treatment].map(envelope_scalar)
    yvals = df[outcome].map(envelope_scalar)
    n_total = len(df)

    marginal = _marginal(df, adjustment)                # {z_key: prob}
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

        joint = np.zeros((2, k), dtype=float)  # rows: exposure state, cols: outcome
        for xi, xval in enumerate(states):
            arm_mask = sub_x == xval
            n_arm = int(arm_mask.sum())
            if n_arm == 0:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    f"stratum X={xval!r}, z={_json_key(z_key)} has no rows "
                    f"(positivity violation); P(Y|x,z) is not estimable so the "
                    f"correction cannot standardise over it.",
                )
            sub_y_arm = sub_y[arm_mask]
            for yj, yval in enumerate(outcome_states):
                joint[xi, yj] = float(int((sub_y_arm == yval).sum()))

        p_obs = joint / joint.sum()
        p_true = Mx_inv @ p_obs @ My_inv.T
        if (p_true < -_TOL).any() or (p_true > 1 + _TOL).any():
            oos = True

        px1 = float(p_true[1, :].sum())
        px0 = float(p_true[0, :].sum())
        if px1 <= _TOL or px0 <= _TOL:
            raise EstimatorFailure(
                Refusal.DEGENERATE_RECOVERED_EXPOSURE,
                stratum=_json_key(z_key), p_treated=px1, p_control=px0,
            )
        corrected += (
            float(p_true[1, target_index]) / px1
            - float(p_true[0, target_index]) / px0
        ) * p_z

        # Naive: the back-door RD on the observed X and observed Y — both biases
        # left in. Row sums are the observed arm sizes (positive by the check).
        naive += (
            float(joint[1, target_index]) / float(joint[1, :].sum())
            - float(joint[0, target_index]) / float(joint[0, :].sum())
        ) * p_z

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
    }
    return corrected, naive, oos, suff


def _combined_bootstrap(
    df: pd.DataFrame, *, treatment: str, outcome: str,
    adjustment: tuple[str, ...], states: tuple, outcome_states: tuple,
    Mx_inv: np.ndarray, My_inv: np.ndarray, target_index: int,
    groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the doubly corrected effect — resample rows (or
    clusters), recompute with BOTH matrices held fixed. Draws that induce a
    positivity / degenerate-recovery failure are skipped."""
    rng = np.random.default_rng(random_state)
    n = len(df)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            pt, _naive, _oos, _suff = _combined_formula(
                df.iloc[idx], treatment=treatment, outcome=outcome,
                adjustment=adjustment, states=states,
                outcome_states=outcome_states,
                Mx_inv=Mx_inv, My_inv=My_inv, target_index=target_index,
            )
        except EstimatorFailure:
            continue
        pts.append(pt)
    if len(pts) < 2:
        return (None, None)
    arr = np.asarray(pts)
    alpha = (1 - ci_level) / 2
    return float(np.quantile(arr, alpha)), float(np.quantile(arr, 1 - alpha))


def _combined_assumptions(
    adjustment: tuple[str, ...], cluster: str | None,
) -> tuple[str, ...]:
    out = [
        "non_differential_misclassification_X_indep_YZ_given_Xtrue",
        "non_differential_misclassification_Y_indep_XZ_given_Ytrue",
        # The premise neither single-channel correction makes, and the one that
        # licenses the two-sided product — named so it is auditable on its own.
        "independent_error_channels_X_indep_Y_given_Xtrue_Ytrue_Z",
        "known_confusion_matrices_from_validation_studies",
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
