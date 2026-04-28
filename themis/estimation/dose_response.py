"""Phase 14 slice a — dose-response estimator (EconML-backed).

Wraps EconML's ``LinearDML`` to produce a dose-response curve when a
program's ``extensions.ambiguities`` carries a ``dose_response_query``
flag (the same trigger Phase 13's diagnostic uses).

Slice-a tradeoffs:
- LinearDML is partially-linear in T: the per-unit treatment effect θ
  is a constant, so the predicted curve is a straight line. That's
  named in ``assumptions`` so callers can tell when the linearity is
  the binding constraint vs. when it reflects the data.
- Sampling points come from (a) the treatment variable's declared
  numeric domain when present, otherwise (b) quantiles of the observed
  treatment column.
- EconML is loaded lazily. When missing, a typed
  ``EstimatorDependencyMissing`` surfaces — dispatch turns it into a
  structured ``estimator_dependency_missing`` block so the caller can
  pip-install and retry without a tracebacked crash.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import validate_data


# Quantiles used when no declared domain is available. Five points is
# enough for a line + visible departure from one; aligns with Phase 13's
# default ``sampling_point_count = 5``.
_DEFAULT_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)


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
) -> DoseResponseEstimate:
    """Fit LinearDML on the supplied data and predict a dose-response
    curve at ``sampling_points``.

    When ``sampling_points`` is None, falls back to quantiles of the
    treatment column. Outcome must be numeric (continuous or ordinal);
    bool outcomes go through Phase 7 binary-effect path, not here.

    Raises ``EstimatorDependencyMissing`` when EconML is not installed.
    """
    try:
        from econml.dml import LinearDML
    except ImportError as exc:
        raise EstimatorDependencyMissing(
            package="econml",
            install_hint="pip install econml  # or: pip install themis[estimator]",
        ) from exc

    required = {treatment, outcome, *adjustment}
    contract = validate_data(data, required_columns=required)
    df = contract.data

    y = df[outcome].to_numpy(dtype=float)
    t = df[treatment].to_numpy(dtype=float)
    if adjustment:
        w = df[list(adjustment)].to_numpy(dtype=float)
    else:
        # LinearDML requires W or X; pass a constant column when the
        # adjustment set is empty so the partially-linear stage has
        # something to regress against.
        w = np.zeros((len(df), 1), dtype=float)

    points = _resolve_sampling_points(t, sampling_points)
    reference = float(points[0])

    est = LinearDML(
        discrete_treatment=False,
        random_state=random_state,
    )
    est.fit(Y=y, T=t, X=None, W=w)

    curve_points: list[CurvePoint] = []
    n = len(df)
    alpha = 1.0 - ci_level
    for x in points:
        x = float(x)
        # effect(T0, T1) returns array of per-row effects; mean across
        # the population gives the average response change.
        per_row = est.effect(T0=np.full(n, reference), T1=np.full(n, x))
        point = float(np.mean(per_row))
        try:
            lo, hi = est.effect_interval(
                T0=np.full(n, reference), T1=np.full(n, x), alpha=alpha,
            )
            ci_lo = float(np.mean(lo))
            ci_hi = float(np.mean(hi))
        except Exception:
            # Some EconML versions / fit configurations don't expose CI.
            ci_lo, ci_hi = None, None
        curve_points.append(
            CurvePoint(x=x, effect=point, ci_lower=ci_lo, ci_upper=ci_hi),
        )

    assumptions = (
        "LinearDML 假设 Y = θ·T + g(W) + ε（在 T 上线性）；预测曲线必为直线。"
        "若疑似非线性请改用 CausalForestDML 或 GAM。",
        "无未观测混杂（given W）",
        f"重叠假设：所有 W 上 T 都有支持（采样点限于观测域内：{points[0]:g}–{points[-1]:g}）",
    )

    return DoseResponseEstimate(
        method="dose_response_linear_dml",
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
