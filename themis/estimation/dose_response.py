"""Phase 14 — dose-response estimator (EconML-backed).

Wraps EconML's ``LinearDML`` / ``CausalForestDML`` / ``LinearDRLearner``
to produce a dose-response curve when a program's
``extensions.ambiguities`` carries a ``dose_response_query`` flag (the
same trigger Phase 13's diagnostic uses).

Backend selection (``model`` kwarg):
- ``'linear'`` — LinearDML; partially-linear, curve is necessarily a
  straight line. Cheapest, smallest-n viable.
- ``'forest'`` — CausalForestDML; flexible nuisance models (Y~W, T~W),
  but final stage still linear in T (does not recover T-Y
  non-linearity).
- ``'drlearner'`` — LinearDRLearner with T discretized into K bins by
  the sampling-point boundaries; estimates each bin's effect against
  the reference bin doubly-robust. **Only backend that produces a
  genuinely non-linear curve.** Needs n ≥ 200 and ≥ 3 sampling points.
- ``'auto'`` (default) — drlearner when conditions met, else linear.
  Forest is opt-in only (it doesn't fix the linear-in-T limitation).

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

from .. import refusals
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from .contract import validate_data
from .declared import ordered_entry


# Quantiles used when no declared domain is available. Five points is
# enough for a line + visible departure from one; aligns with Phase 13's
# default ``sampling_point_count = 5``.
_DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

# Sample-size threshold for switching from LinearDML to CausalForestDML
# in 'auto' mode. Forest needs enough data per leaf for honest splits
# to give meaningful CIs; below this we fall back to the linear model.
_FOREST_MIN_N = 200
_MIN_RELATIVE_OUTCOME_STD = 1e-8

ModelChoice = Literal["auto", "linear", "forest", "drlearner"]


class EstimatorDependencyMissing(RuntimeError):
    """Raised when an estimator backend is not installed.

    Carries the install hint string so dispatch can surface it as a
    structured ``estimator_dependency_missing`` field on the result.
    """

    def __init__(self, package: str, install_hint: str):
        super().__init__(f"missing dependency: {package}")
        self.package = package
        self.install_hint = install_hint


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
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    sampling_points: tuple[float, ...]
    reference_point: float
    curve: tuple[CurvePoint, ...]
    # Mechanism (functional-form) surfaced explicitly so the audit layer
    # can treat it as a first-class, provenance-tagged assumption rather
    # than digging it out of ``assumptions[0]`` by positional convention.
    # ``form`` is the resolved estimator family (linear / forest /
    # drlearner); ``model_assumption`` is the human-readable shape
    # assumption. Mechanism-audit slice (C).
    model_assumption: str = ""
    form: str = ""
    # Identification assumptions structured at source (no unmeasured
    # confounding, overlap) so the assumption-ledger can rank them by
    # severity. Each entry: {claim, layer, severity, testable}.


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
    cluster: str | None = None,
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

    # Subagent real-test caught: constant-Y was silently producing
    # all-zero curves with `numerically_solved` status — a confident
    # false-negative. Pre-check outcome variance so degenerate fits
    # surface as structured failures, like degenerate T already did.
    _check_outcome_variance(y=y, outcome=outcome)

    # Slice c: pre-check overlap before fitting so a sparse sampling
    # point fails as a structured error rather than silently producing
    # a meaningless estimate.
    _check_overlap(t=t, points=points)

    resolved = _resolve_model_choice(model, n, len(points))
    alpha = 1.0 - ci_level
    try:
        if resolved == "drlearner":
            curve_points, method, model_assumption = _fit_drlearner_curve(
                y=y, t=t, w=w, points=points, alpha=alpha,
                random_state=random_state,
            )
        else:
            est, method, model_assumption, x_for_predict = _fit_dml_backend(
                resolved, y=y, t=t, w=w, random_state=random_state,
            )
            curve_points = _predict_curve(
                est, points=points, reference=reference, n=n, alpha=alpha,
                x_for_predict=x_for_predict,
            )
    except EstimatorDependencyMissing:
        raise
    except EstimatorFailure:
        raise
    except (np.linalg.LinAlgError, FloatingPointError) as exc:
        raise EstimatorFailure(
            failure_type=Refusal.CONVERGENCE_FAILURE,
            message=f"DML 拟合数值失败：{exc}",
            backend=resolved,
        ) from exc

    # Form first (it has its own mechanism_audit channel), then
    # identification. These were derived from a structured twin that
    # carried each id's sentence, layer and testability a second time —
    # the same duplication, solved locally and in the wrong direction.
    assumptions: tuple[str, ...] = (
        model_assumption,
        "no_unmeasured_confounding_given_W",
        "positivity_every_sampled_dose_has_support_on_W",
    )
    # W enters the nuisance fits BY COLUMN, so a covariate with more than
    # two levels was read as a number: level three sits twice as far from
    # level one as level two does. Nothing in the program claimed that, and
    # `scale` has no member that could deny it, so the fit says what it
    # assumed.
    assumptions += ordered_entry(df, adjustment)
    # The dose-response CI comes from EconML's DML asymptotic interval,
    # NOT a row/cluster percentile bootstrap, so a pairs cluster
    # bootstrap is not a drop-in here. ``cluster`` is accepted for API
    # uniformity with the other estimators; when set we disclose that
    # the interval is not cluster-robust (it may be anti-conservative
    # under within-cluster dependence) rather than silently ignore it.
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_not_cluster_robust_econml_dml_interval_ignores_{cluster}",
        )

    return DoseResponseEstimate(
        method=method,
        ci_level=ci_level,
        assumptions=assumptions,
        sample_size=int(n),
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment,
        outcome=outcome,
        adjustment=tuple(adjustment),
        sampling_points=tuple(float(p) for p in points),
        reference_point=reference,
        curve=tuple(curve_points),
        model_assumption=model_assumption,
        form=resolved,
    )


def _resolve_model_choice(model: ModelChoice, n: int, k: int) -> str:
    if model == "auto":
        # Slice b.2: prefer drlearner when conditions are met — it's
        # the only backend that produces a non-linear curve. Forest
        # never wins 'auto' since its final stage is still linear in T.
        if n >= _FOREST_MIN_N and k >= 3:
            return "drlearner"
        return "linear"
    if model in ("linear", "forest", "drlearner"):
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


def _fit_drlearner_curve(*, y, t, w, points, alpha, random_state):
    """Slice b.2 — bin T at sampling-point midpoints, fit
    LinearDRLearner on the categorical T, return per-bin effects vs
    the reference bin. This is the only backend that recovers
    non-linearity because the final stage is independent per bin
    rather than linear in T.

    Returns (curve_points, method, assumption)."""
    K = len(points)
    if K < 2:
        raise EstimatorFailure(
            failure_type=Refusal.OVERLAP_INSUFFICIENT,
            message=f"DRLearner 需要 ≥ 2 采样点，仅有 {K}",
            sampling_points=list(points),
        )

    edges = _bin_midpoints(points)
    t_binned = np.digitize(t, edges)  # 0..K-1

    # Each bin must have enough samples for the doubly-robust stage to
    # behave. Mirror the slice-c overlap threshold.
    bin_counts = np.bincount(t_binned, minlength=K)
    sparse = [
        {"bin": int(k), "x": float(points[k]), "n": int(c)}
        for k, c in enumerate(bin_counts) if c < 5
    ]
    if sparse:
        raise EstimatorFailure(
            failure_type=Refusal.OVERLAP_INSUFFICIENT,
            message=(
                f"DRLearner: 离散化后某些 bin 样本不足 (要求 ≥5)：{sparse}"
            ),
            sparse_bins=sparse,
            bin_counts=[int(c) for c in bin_counts],
        )

    try:
        from econml.dr import LinearDRLearner
    except ImportError as exc:
        raise EstimatorDependencyMissing(
            package="econml",
            install_hint=(
                "pip install econml  # or: pip install themis[estimator]"
            ),
        ) from exc

    est = LinearDRLearner(random_state=random_state)
    # X is required for heterogeneity; use the adjustment columns.
    est.fit(Y=y, T=t_binned, X=w, W=None)

    curve_points: list[CurvePoint] = []
    # Reference bin: effect = 0 by construction.
    curve_points.append(
        CurvePoint(x=float(points[0]), effect=0.0, ci_lower=0.0, ci_upper=0.0),
    )
    for k in range(1, K):
        per_row = est.effect(X=w, T0=0, T1=k)
        point = float(np.mean(per_row))
        try:
            lo, hi = est.effect_interval(X=w, T0=0, T1=k, alpha=alpha)
            ci_lo = float(np.mean(lo))
            ci_hi = float(np.mean(hi))
        except Exception:
            ci_lo, ci_hi = None, None
        curve_points.append(
            CurvePoint(
                x=float(points[k]),
                effect=point, ci_lower=ci_lo, ci_upper=ci_hi,
            ),
        )

    method = "dose_response_linear_drlearner"
    assumption = (
        "LinearDRLearner：T 按相邻采样点中点离散化为 K 个 bin；每 bin 用"
        "doubly-robust 估计相对参考 bin 的平均效应；曲线由 K 个独立估计"
        "组成，可恢复非线性 dose-response（每 bin 至少需 5 观测）。"
    )
    return curve_points, method, assumption


def _bin_midpoints(points: tuple[float, ...]) -> np.ndarray:
    """Bin edges for np.digitize: midpoints between adjacent sampling
    points. n points → n-1 edges → n bins indexed 0..n-1."""
    pts = sorted(float(p) for p in points)
    return np.array(
        [(pts[i] + pts[i + 1]) / 2.0 for i in range(len(pts) - 1)],
    )


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


def _check_outcome_variance(*, y: np.ndarray, outcome: str) -> None:
    """Reject constant or near-constant Y. Without this, EconML returns
    a fit that "works" with all-zero coefficients and zero-width CIs —
    the user reads it as "no effect" when reality is "fit was
    degenerate".

    A DATA refusal, which is what this measures: the check runs before
    anything is fitted, so nothing has failed to converge yet. It said
    ``convergence_failure`` — a BACKEND species, whose framing tells the
    reader that nothing was decided about the question, the graph or the
    data — while its own message said 实为数据问题. The treatment-side twin
    below has answered ``overlap_insufficient`` since the day it was
    written, which is the symmetry this restores.
    """
    y_std = float(np.std(y))
    y_range = float(y.max() - y.min())
    scale = max(float(np.max(np.abs(y))), 1.0)
    relative_std = y_std / scale
    relative_range = y_range / scale
    if (
        relative_std < _MIN_RELATIVE_OUTCOME_STD
        or relative_range < _MIN_RELATIVE_OUTCOME_STD
    ):
        raise EstimatorFailure(
            failure_type=Refusal.OUTCOME_DOES_NOT_VARY,
            outcome=outcome,
            std=y_std,
            spread=y_range,
            outcome_scale=scale,
            outcome_relative_std=relative_std,
            outcome_relative_range=relative_range,
        )


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
            failure_type=Refusal.OVERLAP_INSUFFICIENT,
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
            failure_type=Refusal.OVERLAP_INSUFFICIENT,
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
