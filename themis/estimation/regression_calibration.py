"""Regression calibration — continuous mismeasurement de-attenuation numeric end.

The confusion-matrix module (``measurement.py``) corrects a *discrete*
misclassified variable by inverting a known column-stochastic matrix. This
module is its **continuous** counterpart: a continuous exposure measured with
**classical additive error** — we observe ``W = X* + U`` instead of the true
``X*``, with ``U`` mean-zero, independent of ``(X*, Z)`` and of the outcome
given ``X*``, and a *known* error variance ``σ²_u`` (from a validation substudy,
replicate measurements, or the literature — the exact analogue of a known
confusion matrix).

Model (Carroll, Ruppert, Stefanski & Crainiceanu 2006 *Measurement Error in
Nonlinear Models* §3; Rosner, Willett & Spiegelman 1989; Fuller 1987). Linear
structural outcome model, back-door adjustment set Z:

    Y = β0 + βx · X* + βz'·Z + ε ,   E[ε | X*, Z] = 0
    W = X* + U ,                     U ⟂ (X*, Z, ε),  Var(U) = σ²_u  (known)

The naive OLS of Y on the *observed* (W, Z) is attenuated: the classical error
inflates only the W-variance, so the whole design covariance is

    Σ_WZ = Σ_{X*Z} + E ,   E = diag(σ²_u, 0, …, 0)   (error only on W)

while Cov((W, Z), Y) = Cov((X*, Z), Y) is unchanged (U ⟂ Y). Hence the true
structural coefficients are an EXACT moment correction of the naive ones — the
continuous analogue of the confusion-matrix inversion M⁻¹:

    b_naive = Σ_WZ⁻¹ Cov((W, Z), Y)                      (attenuated)
    β_true  = Σ_{X*Z}⁻¹ Cov((W, Z), Y)
            = (Σ_WZ − E)⁻¹ Σ_WZ b_naive                  (de-attenuated)

The corrected causal effect is ``βx = β_true[exposure]`` — the effect on Y per
unit of the *true* exposure X*, adjusting for Z. For a single exposure this
reduces to the classic reliability-ratio correction ``βx_true = b_naive / λ``
with the covariate-adjusted reliability ratio

    λ = Var(X*|Z) / Var(W|Z) = 1 − σ²_u / Var(W|Z)       (continuous "det(M)")

where ``Var(W|Z)`` is the residual variance of W after regressing on Z. λ plays
exactly the role det(M) = Se+Sp−1 plays for a binary outcome: the factor the
naive estimate is divided by. For the linear model this is regression
calibration (replace X* by Ê[X*|W,Z] and refit) and the moment correction
coincide, so the recovery is exact (no normality assumption needed).

Guards (honest, not silent):

- **Degenerate reliability.** σ²_u ≥ Var(W|Z) ⇒ λ ≤ 0 ⇒ Σ_{X*Z} is not positive
  definite: the claimed error variance meets or exceeds the observed conditional
  variance, so the measurement carries no usable signal about X* ⇒ refuse
  (``EstimatorFailure``), mirroring the singular-matrix guard in ``measurement``.
- **Non-positive error variance.** σ²_u ≤ 0 is not a variance ⇒ refuse.
- **Non-continuous exposure.** A near-discrete exposure (≤ ``_MIN_CONTINUOUS_
  DISTINCT`` distinct values) is a misclassification object, not classical
  additive error ⇒ refuse, pointing at the confusion-matrix method.
- **Singular design.** A collinear covariate set (Σ_WZ not invertible) ⇒ refuse.

Scope (declared tradeoffs):

- **Continuous exposure**, **classical additive** error (``W = X* + U``,
  ``U ⟂``); Berkson error, differential error, and a mismeasured *outcome* /
  *covariate* are deferred (this estimator is exposure-side).
- **Linear** structural outcome model — the moment correction is exact for a
  linear Y (or the linear-probability projection of a binary Y). A nonlinear
  outcome (logistic, Cox) would need the approximate RC "replace-and-refit" or
  SIMEX; both are deferred. SIMEX in particular is a simulation-extrapolation
  heuristic (a tuned extrapolant, not a closed form), so it does not fit the
  per-number re-derivation contract and is out of scope.
- **Known, FIXED** error variance σ²_u (a validation-study / replicate quantity),
  exactly as the confusion matrix is fixed. Propagating validation-study
  uncertainty in σ²_u itself (a second layer) is deferred; the bootstrap
  propagates the main-sample sampling variability only.
- **Numeric** back-door adjustment covariates Z; a categorical Z (dummy coding)
  is deferred.

The sufficient statistics recorded on the estimate (the design covariance matrix
Σ_WZ, the Cov((W,Z), Y) vector, σ²_u, and n) are exactly what
``themis.verify_regression_calibration_numeric`` re-derives the corrected point,
the naive point, and the reliability from — it never re-touches the raw data and
never imports this module.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices

# An exposure with fewer than this many distinct values is treated as discrete
# (a misclassification object) rather than a continuously-mismeasured one.
_MIN_CONTINUOUS_DISTINCT = 10
# λ (reliability ratio) at or below this ⇒ the corrected design is not positive
# definite ⇒ refuse.
_LAMBDA_FLOOR = 1e-9
_TOL = 1e-9


@dataclass(frozen=True)
class RegressionCalibrationEstimate:
    """Regression-calibration-corrected effect of a continuously-mismeasured
    exposure, with a bootstrap CI.

    ``point`` is the corrected per-unit slope βx of the true exposure X* on Y
    adjusting for Z. ``naive_point`` is the attenuated naive OLS slope of Y on
    the observed W adjusting for Z — the biased number the correction replaces.
    ``reliability`` is λ = 1 − σ²_u/Var(W|Z), the continuous analogue of det(M).
    ``sufficient_statistics`` carries the design covariance matrix Σ_WZ, the
    Cov((W,Z), Y) vector, σ²_u, and n — everything the numeric verifier
    re-derives the point from.
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
    error_variance: float
    reliability: float
    naive_slope: tuple[float, ...]
    corrected_slope: tuple[float, ...]
    design_vars: tuple[str, ...]
    sufficient_statistics: dict = field(default_factory=dict)
    cluster: str | None = None
    form: str = "regression_calibration_backdoor_linear"
    model_assumption: str = ""


# --- public entry -------------------------------------------------------------


def estimate_regression_calibration(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    error_variance: float,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> RegressionCalibrationEstimate:
    """De-attenuate the linear back-door effect of a continuously-mismeasured
    exposure by the regression-calibration moment correction.

    Parameters
    ----------
    data: the main sample carrying the *observed* (error-prone) exposure W.
    treatment / outcome: continuous exposure W and (linear) outcome Y columns.
    adjustment: the back-door adjustment covariates Z (numeric).
    error_variance: the KNOWN classical additive measurement-error variance σ²_u
        (from a validation study / replicates), held fixed across bootstraps.
    ci_bootstrap / ci_level / random_state / cluster: percentile-bootstrap
        controls (σ²_u is held fixed across resamples).

    Raises
    ------
    EstimatorFailure: non-positive / non-finite error variance; a near-discrete
        exposure; a collinear (singular) design; or a degenerate reliability
        (σ²_u ≥ Var(W|Z), so the corrected design is not positive definite).
    """
    if (
        not isinstance(error_variance, (int, float))
        or isinstance(error_variance, bool)
        or not np.isfinite(error_variance)
        or error_variance <= 0
    ):
        raise EstimatorFailure(
            "non_positive_error_variance",
            f"the classical measurement-error variance σ²_u must be a positive "
            f"finite number; got {error_variance!r}.",
        )

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
    )
    df = contract.data

    n_distinct = int(df[treatment].dropna().nunique())
    if n_distinct < _MIN_CONTINUOUS_DISTINCT:
        raise EstimatorFailure(
            "exposure_not_continuous",
            f"exposure {treatment!r} has only {n_distinct} distinct values; "
            f"regression calibration is for a CONTINUOUS exposure with classical "
            f"additive error. A discrete / binary exposure is a misclassification "
            f"object — use the confusion-matrix method (misclassification=) "
            f"instead.",
        )

    design_vars = (treatment, *adjustment)
    D = np.column_stack([df[v].to_numpy(dtype=float) for v in design_vars])
    y = df[outcome].to_numpy(dtype=float)
    n = len(df)

    groups = (
        cluster_labels(df, cluster, expected_n=n)
        if cluster is not None else None
    )

    point, naive, beta, b, lam, Sigma, cov_Dy = _formula(
        D, y, float(error_variance),
    )

    ci_lower = ci_upper = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap(
            D, y, float(error_variance), groups=groups,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level, random_state=random_state,
        )

    model_assumption = (
        "被经典加性误差污染的连续暴露 W=X*+U（U 均值 0、与 (X*,Z) 及给定 X* 的 Y "
        "独立），误差方差 σ²_u 由验证研究/重复测量已知且固定。经典误差只抬高设计"
        "协方差中 W 的方差：Σ_WZ=Σ_{X*Z}+E，E=diag(σ²_u,0,…)，而 Cov((W,Z),Y) 不"
        "变。故真实结构系数是朴素系数的精确矩量校正 β_true=(Σ_WZ−E)⁻¹Σ_WZ·b_naive"
        "（=(Σ_WZ−E)⁻¹Cov((W,Z),Y)），暴露分量 βx 即对 Z 调整后每单位真实暴露对 Y "
        "的因果斜率。单暴露即可靠比校正 βx_true=b_naive/λ，λ=1−σ²_u/Var(W|Z) 是连续"
        "版 det(M)。线性结局下 regression calibration 与矩量校正一致，恢复精确。"
    )
    assumptions = _assumptions(adjustment, cluster)
    return RegressionCalibrationEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="regression_calibration",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        error_variance=float(error_variance),
        reliability=lam,
        naive_slope=tuple(float(v) for v in b),
        corrected_slope=tuple(float(v) for v in beta),
        design_vars=design_vars,
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "var_y": float(np.var(y, ddof=1)),
            "error_variance": float(error_variance),
            "n": int(n),
            "exposure_index": 0,
            "reliability": lam,
            "naive_slope": [float(v) for v in b],
            "corrected_slope": [float(v) for v in beta],
            "adjustment_vars": list(adjustment),
        },
        cluster=cluster,
        model_assumption=model_assumption,
    )


# --- formula core -------------------------------------------------------------


def _conditional_var_w(Sigma: np.ndarray) -> float:
    """Residual variance of W (design index 0) after regressing on Z (the rest):
    Var(W|Z) = Σ_WW − Σ_WZ Σ_ZZ⁻¹ Σ_ZW (the Schur complement). No covariates ⇒
    Var(W|Z) = Var(W)."""
    if Sigma.shape[0] == 1:
        return float(Sigma[0, 0])
    s_ww = float(Sigma[0, 0])
    s_wz = Sigma[0, 1:]
    s_zz = Sigma[1:, 1:]
    return s_ww - float(s_wz @ np.linalg.solve(s_zz, s_wz))


def _formula(D: np.ndarray, y: np.ndarray, error_variance: float):
    """Corrected + naive exposure slope from the design (W, Z) and outcome y.

    Returns (point, naive, corrected_slope, naive_slope, reliability, Σ_WZ,
    Cov((W,Z), y)). Raises on a singular design or a degenerate reliability."""
    p = D.shape[1]
    Dc = D - D.mean(axis=0)
    yc = y - y.mean()
    Sigma = (Dc.T @ Dc) / (len(y) - 1)              # Σ_WZ
    cov_Dy = (Dc.T @ yc) / (len(y) - 1)             # Cov((W,Z), y)

    try:
        b = np.linalg.solve(Sigma, cov_Dy)          # naive OLS slopes
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            "singular_design",
            "the design covariance Σ_WZ is singular (collinear covariates); the "
            "naive regression — and so the correction — is undefined.",
        )

    var_w_given_z = _conditional_var_w(Sigma)
    lam = 1.0 - error_variance / var_w_given_z      # reliability ratio (det(M) analogue)
    if lam <= _LAMBDA_FLOOR:
        raise EstimatorFailure(
            "degenerate_reliability",
            f"the measurement-error variance σ²_u = {error_variance:.6g} meets or "
            f"exceeds Var(W|Z) = {var_w_given_z:.6g} (reliability λ = {lam:.6g} ≤ 0); "
            f"the corrected design Σ_WZ − E is not positive definite and the "
            f"measurement carries no usable information about the true exposure.",
        )

    E = np.zeros((p, p))
    E[0, 0] = error_variance
    Sigma_star = Sigma - E                          # Σ_{X*Z}
    beta = np.linalg.solve(Sigma_star, cov_Dy)      # de-attenuated slopes

    return (
        float(beta[0]), float(b[0]), beta, b, float(lam), Sigma, cov_Dy,
    )


def _bootstrap(
    D: np.ndarray, y: np.ndarray, error_variance: float, *,
    groups: np.ndarray | None,
    ci_bootstrap: int, ci_level: float, random_state: int,
) -> tuple[float | None, float | None]:
    """Percentile bootstrap of the corrected exposure slope — resample rows (or
    clusters), recompute the correction with σ²_u held FIXED, collect βx. Draws
    that induce a degenerate reliability / singular design are skipped."""
    rng = np.random.default_rng(random_state)
    n = len(y)
    pts: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            point, *_ = _formula(D[idx], y[idx], error_variance)
        except EstimatorFailure:
            continue
        pts.append(point)
    if not pts:
        return None, None
    alpha = (1.0 - ci_level) / 2.0
    lo = float(np.quantile(pts, alpha))
    hi = float(np.quantile(pts, 1.0 - alpha))
    return lo, hi


def _assumptions(adjustment: tuple[str, ...], cluster: str | None) -> tuple[str, ...]:
    adj = ", ".join(adjustment) if adjustment else "∅"
    out = [
        "经典加性测量误差 W=X*+U，U 均值 0 且与 (X*,Z,ε) 独立；误差方差 σ²_u 已知且固定。",
        "线性结构结局模型 Y=β0+βx·X*+βz'·Z+ε（矩量校正对线性结局精确）。",
        f"后门可识别，调整集 Z = {{{adj}}}（数值协变量）。",
        "暴露连续；朴素后门 OLS 因回归稀释向零衰减，校正后 βx=b_naive/λ。",
    ]
    if cluster is not None:
        out.append(f"聚类 bootstrap（按 {cluster} 重采样簇）传播抽样不确定性。")
    return tuple(out)
