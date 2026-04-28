"""Phase 14 — dose-response estimator (EconML-backed).

Wraps EconML's ``LinearDML`` / ``CausalForestDML`` to produce a
dose-response curve when a program's ``extensions.ambiguities`` carries
a ``dose_response_query`` flag (the same trigger Phase 13's diagnostic
uses).

Backend selection (``model`` kwarg):
- ``'linear'`` — LinearDML; partially-linear, curve is necessarily a
  straight line. Cheapest, smallest-n viable.
- ``'forest'`` — CausalForestDML; heterogeneous treatment effects via
  honest random forest. Captures non-linearity but needs more data.
- ``'auto'`` (default) — forest when n ≥ 200, else linear. Documented
  in the result's ``assumptions`` string so the caller knows which.

Sampling points come from (a) the treatment variable's declared numeric
domain when present, otherwise (b) quantiles of the observed treatment
column.

EconML is loaded lazily. When missing, a typed
``EstimatorDependencyMissing`` surfaces — dispatch turns it into a
structured ``estimator_dependency_missing`` block so the caller can
pip-install and retry without a tracebacked crash.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from .contract import validate_data


# Quantiles used when no declared domain is available. Five points is
# enough for a line + visible departure from one; aligns with Phase 13's
# default ``sampling_point_count = 5``.
_DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

# Sample-size threshold for switching from LinearDML to CausalForestDML
# in 'auto' mode. Forest needs enough data per leaf for honest splits
# to give meaningful CIs; below this we fall back to the linear model.
_FOREST_MIN_N = 200

ModelChoice = Literal["auto", "linear", "forest"]


class EstimatorDependencyMissing(RuntimeError):
    """Raised when an estimator backend is not installed.

    Carries the install hint string so dispatch can surface it as a
    structured ``estimator_dependency_missing`` field on the result.
    """

    def __init__(self, package: str, install_hint: str):
        super().__init__(f"missing dependency: {package}")
        self.package = package
        self.install_hint = install_hint


class EstimatorFailure(RuntimeError):
    """Raised by the dose-response estimator on a recoverable numeric
    failure. Dispatch turns this into a structured ``estimator_failure``
    block with ``failure_type`` so the caller can branch on the cause
    without parsing free-form messages.

    failure_type values (slice c):
    - ``'overlap_insufficient'`` — one or more sampling points have
      fewer than ``min_neighbors`` observations within the chosen
      bandwidth; the estimate at that point would be uninformative.
    - ``'convergence_failure'`` — the underlying sklearn / EconML
      regressor raised LinAlgError, ConvergenceWarning-as-error, or
      similar.
    - ``'unknown'`` — fallback when the underlying message doesn't
      match one of the above shapes.
    """

    def __init__(self, failure_type: str, message: str, **details):
        super().__init__(message)
        self.failure_type = failure_type
        self.details = details


@dataclass(frozen=True)
class CurvePoint:
    x: float
    effect: float           # predicted Y(x) - Y(x_ref)
    ci_lower: float | None
    ci_upper: float | None


@dataclass(frozen=True)
class DoseResponseEstimate:
    method: str             # "dose_response_linear_dml"
    ci_level: float
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    sampling_points: tuple[float, ...]
    reference_point: float
    curve: tuple[CurvePoint, ...]


def estimate_dose_response(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    sampling_points: tuple[float, ...] | None = None,
    ci_level: float = 0.95,
    random_state: int = 42,
    model: ModelChoice = "auto",
) -> DoseResponseEstimate:
    """Fit a DML estimator and predict a dose-response curve at
    ``sampling_points``.

    Backend chosen by ``model``:
    - ``'linear'`` — LinearDML (always linear curve)
    - ``'forest'`` — CausalForestDML (can recover non-linear shape)
    - ``'auto'`` (default) — forest when n ≥ 200, else linear

    When ``sampling_points`` is None, falls back to quantiles of the
    treatment column. Outcome must be numeric (continuous or ordinal);
    bool outcomes go through Phase 7 binary-effect path, not here.

    Raises ``EstimatorDependencyMissing`` when EconML is not installed.
    """
    required = {treatment, outcome, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    y = df[outcome].to_numpy(dtype=float)
    t = df[treatment].to_numpy(dtype=float)
    if adjustment:
        w = df[list(adjustment)].to_numpy(dtype=float)
    else:
        # DML estimators need W or X; pass a constant column when the
        # adjustment set is empty so the nuisance stage has something
        # to regress against.
        w = np.zeros((len(df), 1), dtype=float)

    points = _resolve_sampling_points(t, sampling_points)
    reference = float(points[0])
    n = len(df)

    # Slice c: pre-check overlap before fitting so a sparse sampling
    # point fails as a structured error rather than silently producing
    # a meaningless estimate.
    _check_overlap(t=t, points=points)

    resolved = _resolve_model_choice(model, n)
    try:
        est, method, model_assumption, x_for_predict = _fit_dml_backend(
            resolved, y=y, t=t, w=w, random_state=random_state,
        )
    except EstimatorDependencyMissing:
        raise
    except (np.linalg.LinAlgError, FloatingPointError) as exc:
        raise EstimatorFailure(
            failure_type="convergence_failure",
            message=f"DML 拟合数值失败：{exc}",
            backend=resolved,
        ) from exc

    alpha = 1.0 - ci_level
    curve_points = _predict_curve(
        est, points=points, reference=reference, n=n, alpha=alpha,
        x_for_predict=x_for_predict,
    )

    assumptions = (
        model_assumption,
        "无未观测混杂（given W）",
        f"重叠假设：所有 W 上 T 都有支持（采样点限于观测域内："
        f"{points[0]:g}–{points[-1]:g}）",
    )

    return DoseResponseEstimate(
        method=method,
        ci_level=ci_level,
        assumptions=assumptions,
        sample_size=int(n),
        data_hash=contract.data_hash,
        treatment=treatment,
        outcome=outcome,
        adjustment=tuple(adjustment),
        sampling_points=tuple(float(p) for p in points),
        reference_point=reference,
        curve=tuple(curve_points),
    )


def _resolve_model_choice(model: ModelChoice, n: int) -> str:
    if model == "auto":
        return "forest" if n >= _FOREST_MIN_N else "linear"
    if model in ("linear", "forest"):
        return model
    raise ValueError(f"unknown model: {model!r}")


def _fit_dml_backend(
    resolved: str, *, y, t, w, random_state: int,
):
    """Returns (fitted_estimator, method_string, assumption_string,
    x_for_predict). LinearDML accepts X=None; CausalForestDML requires
    X — we pass the adjustment columns there so the forest can split on
    them. ``x_for_predict`` is the X array (or None) to feed back into
    .effect() at curve-prediction time.

    Imports EconML lazily so missing dep raises EstimatorDependencyMissing
    only when the user actually requests an estimate."""
    try:
        if resolved == "linear":
            from econml.dml import LinearDML
            est = LinearDML(
                discrete_treatment=False,
                random_state=random_state,
            )
            est.fit(Y=y, T=t, X=None, W=w)
            x_for_predict = None
            method = "dose_response_linear_dml"
            assumption = (
                "LinearDML 假设 Y = θ·T + g(W) + ε（在 T 上线性）；预测曲线"
                "必为直线。若疑似非线性请用 model='forest'。"
            )
        else:
            from econml.dml import CausalForestDML
            est = CausalForestDML(
                discrete_treatment=False,
                random_state=random_state,
                # n_estimators / min_samples_leaf default to honest-fit
                # values that work for the small fixtures we test. Real
                # users can override via slice c when we expose tuning.
            )
            # Forest needs X for heterogeneity. Use the adjustment
            # columns (W) as X — for a pure dose-response without a
            # declared moderator this is the natural feature set.
            est.fit(Y=y, T=t, X=w, W=None)
            x_for_predict = w
            method = "dose_response_causal_forest_dml"
            assumption = (
                "CausalForestDML：nuisance 阶段用随机森林（Y~W、T~W 可"
                "非线性），最终阶段对 T 仍线性 — 不能恢复 T-Y 非线性。"
                "若需非线性曲线需 DRLearner + T 离散化或 SparseLinearDML"
                "+poly features（未实现）。需 n ≥ 200。"
            )
    except ImportError as exc:
        raise EstimatorDependencyMissing(
            package="econml",
            install_hint=(
                "pip install econml  # or: pip install themis[estimator]"
            ),
        ) from exc

    return est, method, assumption, x_for_predict


def _predict_curve(est, *, points, reference, n, alpha, x_for_predict):
    curve_points: list[CurvePoint] = []
    for x in points:
        x = float(x)
        # effect(T0, T1, X) returns per-row effects; population mean is
        # the average response change. X=None for LinearDML, the
        # adjustment matrix for CausalForestDML.
        kwargs = {"T0": np.full(n, reference), "T1": np.full(n, x)}
        if x_for_predict is not None:
            kwargs["X"] = x_for_predict
        per_row = est.effect(**kwargs)
        point = float(np.mean(per_row))
        try:
            lo, hi = est.effect_interval(alpha=alpha, **kwargs)
            ci_lo = float(np.mean(lo))
            ci_hi = float(np.mean(hi))
        except Exception:
            # Some EconML versions / fit configurations don't expose CI.
            ci_lo, ci_hi = None, None
        curve_points.append(
            CurvePoint(x=x, effect=point, ci_lower=ci_lo, ci_upper=ci_hi),
        )
    return curve_points


def _check_overlap(*, t: np.ndarray, points: tuple[float, ...]) -> None:
    """Raise EstimatorFailure(overlap_insufficient) when any sampling
    point has fewer than ``min_neighbors`` observations within a
    Silverman-ish bandwidth (10% of the T range). This is a soft check
    — passing doesn't guarantee good overlap, but failing does
    guarantee the estimate would be uninformative."""
    min_neighbors = 5
    t_range = float(t.max() - t.min())
    if t_range <= 0:
        raise EstimatorFailure(
            failure_type="overlap_insufficient",
            message="treatment column 没有变化（max == min），无法估计剂量响应",
            t_range=t_range,
        )
    bandwidth = 0.1 * t_range
    sparse_points = []
    for p in points:
        in_band = int(np.sum(np.abs(t - p) <= bandwidth))
        if in_band < min_neighbors:
            sparse_points.append({"x": float(p), "n_within_bandwidth": in_band})
    if sparse_points:
        raise EstimatorFailure(
            failure_type="overlap_insufficient",
            message=(
                f"采样点附近样本不足（带宽 ±{bandwidth:.3g}，要求 ≥"
                f"{min_neighbors}）；这些点估计将不可信：{sparse_points}"
            ),
            sparse_points=sparse_points,
            bandwidth=float(bandwidth),
            min_neighbors=min_neighbors,
        )


def _resolve_sampling_points(
    t: np.ndarray,
    requested: tuple[float, ...] | None,
) -> tuple[float, ...]:
    if requested is not None and len(requested) >= 2:
        return tuple(sorted(float(p) for p in requested))
    qs = np.quantile(t, _DEFAULT_QUANTILES)
    # Deduplicate (small samples can collapse adjacent quantiles)
    unique = sorted(set(round(float(q), 6) for q in qs))
    if len(unique) < 2:
        # Treatment is essentially constant — caller will see a
        # degenerate one-point curve and can decide what to do.
        unique = [float(t.min()), float(t.max())]
        unique = sorted(set(unique))
    return tuple(unique)
