"""Omitted-variable-bias sensitivity analysis (Cinelli & Hazlett 2020).

The regression-scale complement to the E-value (``sensitivity.py``,
risk-ratio scale). For a linear-regression treatment effect it answers
"how strong would an unobserved confounder have to be — measured as the
fraction of residual variance it explains in the treatment AND the
outcome — to overturn this estimate?", and benchmarks that strength
against the observed covariates ("a confounder as strong as X").

Everything here is a closed form of the fitted regression's summary
statistics — the treatment coefficient's t-value and the residual
degrees of freedom — so it needs no extra data pass and is exactly
re-derivable by the verifier (unlike the data-refit point estimators,
which only get a metadata audit).

Core quantities (Cinelli & Hazlett 2020; the sensemakr package):

- **partial R²** of the treatment with the outcome,
  R²_{Y~D|X} = t² / (t² + dof) — the share of residual outcome variance
  the treatment explains. Also the bias an omitted variable that
  explained the same share of BOTH treatment and outcome would cause.
- **Robustness value** RV_q: the confounding strength (as a partial R²
  that the confounder shares with BOTH treatment and outcome) needed to
  reduce the estimate by 100·q%. RV near 1 ⇒ robust; near 0 ⇒ fragile.
  RV_{q,α} additionally requires the result to become statistically
  insignificant at level α.
- **Bias / adjusted estimate** for a hypothetical confounder of a given
  (R²_{D~Z|X}, R²_{Y~Z|D,X}): bias = BF·se·√dof with the bias factor
  BF = √(R²_{Y~Z|D,X}·R²_{D~Z|X} / (1 − R²_{D~Z|X})).
- **Benchmark bounds**: given an observed covariate's partial R²s, the
  strength (and resulting bias) of a confounder "kd times as associated
  with the treatment and ky times with the outcome" — the interpretable
  handle that turns abstract R² into "as strong as covariate X".

Reference:
- Cinelli C, Hazlett C. "Making sense of sensitivity: extending omitted
  variable bias." J R Stat Soc B. 2020;82(1):39-67.
- sensemakr (R / Python) — the reference implementation whose formulas
  these reproduce (verified against its Darfur example: t=4.18445,
  dof=783 → RV_q=0.13878, RV_{q,α}=0.07626, partial R²=0.02187).

API:

    from themis.estimation.sensitivity_ovb import estimate_ovb_sensitivity
    s = estimate_ovb_sensitivity(
        data, treatment="d", outcome="y", adjustment=("x1", "x2"),
    )
    print(s.robustness_value_q, s.partial_r2, s.benchmarks)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from scipy.stats import t as _t_dist


# --- pure formulas (closed forms; verifier re-derives these) -----------------


def partial_r2(t_statistic: float, dof: int) -> float:
    """Partial R² of the coefficient: t² / (t² + dof)."""
    t2 = t_statistic * t_statistic
    return t2 / (t2 + dof)


def partial_f2(t_statistic: float, dof: int) -> float:
    """Partial (Cohen's) f²: t² / dof."""
    return t_statistic * t_statistic / dof


def robustness_value(
    t_statistic: float, dof: int, *, q: float = 1.0, alpha: float = 1.0,
) -> float:
    """Robustness value (Cinelli & Hazlett 2020), scalar.

    ``alpha=1`` (default) gives RV_q — the confounding strength (equal
    partial R² with treatment and outcome) that reduces the estimate by
    100·q%. ``alpha<1`` gives RV_{q,α}, additionally requiring the result
    to lose significance at level α. Three-case clamping matches
    sensemakr exactly.
    """
    fq = q * abs(t_statistic / math.sqrt(dof))
    # critical f at level alpha; alpha=1 → t.ppf(0.5)=0 → f_crit=0 → RV_q.
    f_crit = abs(_t_dist.ppf(alpha / 2.0, dof - 1)) / math.sqrt(dof - 1)
    fqa = fq - f_crit

    if fqa < 0:
        return 0.0
    # "constraint not binding": the confounder needed to kill significance
    # is weaker than the one needed for the q-reduction.
    if f_crit > 0 and fq > 1.0 / f_crit:
        return (fq * fq - f_crit * f_crit) / (1.0 + fq * fq)
    # "constraint binding" (the usual case)
    return 0.5 * (math.sqrt(fqa ** 4 + 4.0 * fqa ** 2) - fqa ** 2)


def bias_factor(r2dz_x: float, r2yz_dx: float) -> float:
    """BF = √( R²_{Y~Z|D,X} · R²_{D~Z|X} / (1 − R²_{D~Z|X}) )."""
    return math.sqrt(r2yz_dx * r2dz_x / (1.0 - r2dz_x))


def bias(r2dz_x: float, r2yz_dx: float, *, se: float, dof: int) -> float:
    """Absolute bias an omitted confounder of strength
    (R²_{D~Z|X}, R²_{Y~Z|D,X}) would induce: BF · se · √dof."""
    return bias_factor(r2dz_x, r2yz_dx) * se * math.sqrt(dof)


def adjusted_estimate(
    estimate: float, r2dz_x: float, r2yz_dx: float,
    *, se: float, dof: int, reduce: bool = True,
) -> float:
    """Bias-adjusted estimate. ``reduce=True`` moves the estimate toward
    zero by the bias (the confounder explains AWAY part of the effect);
    ``reduce=False`` moves it away."""
    b = bias(r2dz_x, r2yz_dx, se=se, dof=dof)
    sign = math.copysign(1.0, estimate)
    return sign * (abs(estimate) - b) if reduce else sign * (abs(estimate) + b)


def adjusted_se(r2dz_x: float, r2yz_dx: float, *, se: float, dof: int) -> float:
    """SE of the treatment coefficient after adjusting for the confounder."""
    return math.sqrt((1.0 - r2yz_dx) / (1.0 - r2dz_x)) * se * math.sqrt(dof / (dof - 1))


def ovb_partial_r2_bound(
    r2dxj_x: float, r2yxj_dx: float, *, kd: float = 1.0, ky: float = 1.0,
) -> tuple[float, float]:
    """Bound the confounder strength implied by a benchmark covariate.

    Given an observed covariate's partial R² with the treatment
    (``r2dxj_x``) and with the outcome (``r2yxj_dx``), return the
    (R²_{D~Z|X}, R²_{Y~Z|D,X}) of a hypothetical confounder ``kd`` times
    as associated with the treatment and ``ky`` times with the outcome
    (Cinelli & Hazlett 2020 §4.4).
    """
    r2dz_x = kd * (r2dxj_x / (1.0 - r2dxj_x))
    r2zxj_xd = kd * (r2dxj_x ** 2) / ((1.0 - kd * r2dxj_x) * (1.0 - r2dxj_x))
    r2yz_dx = (
        ((math.sqrt(ky) + math.sqrt(r2zxj_xd)) / math.sqrt(1.0 - r2zxj_xd)) ** 2
        * (r2yxj_dx / (1.0 - r2yxj_dx))
    )
    return r2dz_x, r2yz_dx


# --- result envelope ---------------------------------------------------------


@dataclass(frozen=True)
class OVBBenchmark:
    """Confounder strength + bias implied by one observed covariate."""

    covariate: str
    kd: float
    ky: float
    # The benchmark covariate's own partial R²s (the bound INPUTS — kept
    # so the verifier can re-derive r2dz_x / r2yz_dx / the adjusted
    # estimate from first principles).
    r2dxj_x: float         # partial R² of treatment with the covariate
    r2yxj_dx: float        # partial R² of outcome with the covariate
    r2dz_x: float | None   # implied R²_{D~Z|X} (None when math undefined)
    r2yz_dx: float | None  # implied R²_{Y~Z|D,X} (None when math undefined)
    adjusted_estimate: float | None
    adjusted_se: float | None
    adjusted_t: float | None
    valid: bool            # False when the implied confounder R² escapes [0,1]


@dataclass(frozen=True)
class OVBSensitivity:
    """Omitted-variable-bias sensitivity for a linear treatment effect."""

    treatment: str
    outcome: str
    estimate: float        # the OLS treatment coefficient
    se: float
    t_statistic: float
    dof: int
    q: float
    alpha: float
    partial_r2: float              # R²_{Y~D|X}
    robustness_value_q: float      # RV_q
    robustness_value_qa: float     # RV_{q,α}
    benchmarks: tuple[OVBBenchmark, ...]


def estimate_ovb_sensitivity(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: Sequence[str] = (),
    q: float = 1.0,
    alpha: float = 0.05,
    benchmark_covariates: Sequence[str] | None = None,
    kd: float = 1.0,
    ky: float = 1.0,
    reduce: bool = True,
) -> OVBSensitivity:
    """Cinelli-Hazlett OVB sensitivity for a linear-regression ATE.

    Fits the outcome regression Y ~ D + X (OLS) for the treatment
    coefficient's t-value + residual dof, then the robustness value,
    partial R², and — for each benchmark covariate — the confounder
    strength / bias implied by a covariate ``kd`` / ``ky`` times as
    strong. ``benchmark_covariates=None`` benchmarks against every
    covariate in the adjustment set.
    """
    adjustment = tuple(adjustment)
    cols = [treatment, *adjustment]
    X = _design_with_intercept(data[cols].to_numpy(dtype=float))
    y = data[outcome].to_numpy(dtype=float)
    # column 0 is the intercept; treatment is column 1, covariates 2..
    beta, se_vec, t_vec, dof = _ols_fit(X, y)
    coef = float(beta[1])
    se = float(se_vec[1])
    t_stat = float(t_vec[1])

    r2yd_x = partial_r2(t_stat, dof)
    rv_q = robustness_value(t_stat, dof, q=q, alpha=1.0)
    rv_qa = robustness_value(t_stat, dof, q=q, alpha=alpha)

    names = list(benchmark_covariates) if benchmark_covariates is not None \
        else list(adjustment)
    benchmarks: list[OVBBenchmark] = []
    for cov in names:
        if cov not in adjustment:
            raise ValueError(
                f"benchmark covariate {cov!r} is not in the adjustment set "
                f"{adjustment}"
            )
        j = 2 + adjustment.index(cov)     # its column in the outcome design
        r2yxj_dx = partial_r2(float(t_vec[j]), dof)
        r2dxj_x = _treatment_partial_r2(data, treatment, adjustment, cov)
        bm = _benchmark(
            cov, r2dxj_x, r2yxj_dx, kd=kd, ky=ky,
            estimate=coef, se=se, dof=dof, reduce=reduce,
        )
        benchmarks.append(bm)

    return OVBSensitivity(
        treatment=treatment,
        outcome=outcome,
        estimate=coef,
        se=se,
        t_statistic=t_stat,
        dof=dof,
        q=q,
        alpha=alpha,
        partial_r2=r2yd_x,
        robustness_value_q=rv_q,
        robustness_value_qa=rv_qa,
        benchmarks=tuple(benchmarks),
    )


def _design_with_intercept(cols: np.ndarray) -> np.ndarray:
    """Prepend an intercept column to a 2-D design matrix."""
    return np.column_stack([np.ones(cols.shape[0]), cols])


def _ols_fit(
    X: np.ndarray, y: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Ordinary least squares by the closed form — return
    (coefficients, standard errors, t-values, residual dof).

    Self-contained numpy (β = (XᵀX)⁻¹Xᵀy, homoskedastic SE from the
    residual variance) so the sensitivity path needs no statsmodels /
    extra native machinery — the same t-values and dof, computed with
    fewer moving parts. Raises ``numpy.linalg.LinAlgError`` on a singular
    design (caught upstream — sensitivity is supplementary)."""
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    resid = y - X @ beta
    dof = n - k
    sigma2 = float(resid @ resid) / dof
    se = np.sqrt(sigma2 * np.diag(XtX_inv))
    tvalues = beta / se
    return beta, se, tvalues, dof


def _treatment_partial_r2(
    data: pd.DataFrame, treatment: str, adjustment: tuple[str, ...], cov: str,
) -> float:
    """Partial R² of the treatment with covariate ``cov`` given the other
    covariates — from the auxiliary regression D ~ X."""
    others = [c for c in adjustment if c != cov]
    design_cols = [cov, *others]
    Xt = _design_with_intercept(data[design_cols].to_numpy(dtype=float))
    d = data[treatment].to_numpy(dtype=float)
    _, _, t_vec, dof_t = _ols_fit(Xt, d)
    # cov is column 1 (after the intercept)
    return partial_r2(float(t_vec[1]), dof_t)


def _benchmark(
    covariate: str, r2dxj_x: float, r2yxj_dx: float,
    *, kd: float, ky: float, estimate: float, se: float, dof: int, reduce: bool,
) -> OVBBenchmark:
    # The bound math is defined only when the covariate's partial R²s and
    # the kd-scaled treatment share stay below 1; a covariate too strong to
    # serve as a benchmark makes a denominator non-positive. Guard rather
    # than raise — a void benchmark reports None bounds + valid=False.
    try:
        bound: tuple[float, float] | None = ovb_partial_r2_bound(
            r2dxj_x, r2yxj_dx, kd=kd, ky=ky,
        )
    except (ValueError, ZeroDivisionError):
        bound = None
    valid = False
    adj_est: float | None = None
    adj_se: float | None = None
    adj_t: float | None = None
    if bound is not None:
        r2dz_x, r2yz_dx = bound
        valid = (
            math.isfinite(r2dz_x) and math.isfinite(r2yz_dx)
            and 0.0 <= r2dz_x < 1.0 and 0.0 <= r2yz_dx <= 1.0
        )
        if valid:
            adj_est = adjusted_estimate(
                estimate, r2dz_x, r2yz_dx, se=se, dof=dof, reduce=reduce,
            )
            adj_se = adjusted_se(r2dz_x, r2yz_dx, se=se, dof=dof)
            adj_t = adj_est / adj_se if adj_se > 0 else None
    return OVBBenchmark(
        covariate=covariate, kd=kd, ky=ky,
        r2dxj_x=r2dxj_x, r2yxj_dx=r2yxj_dx,
        r2dz_x=None if bound is None else bound[0],
        r2yz_dx=None if bound is None else bound[1],
        adjusted_estimate=adj_est, adjusted_se=adj_se, adjusted_t=adj_t,
        valid=valid,
    )
