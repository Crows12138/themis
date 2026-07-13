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

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from sklearn.linear_model import LinearRegression

from .contract import validate_data
from .resample import cluster_labels, resample_indices


ModelName = Literal["auto", "wald", "2sls"]


@dataclass(frozen=True)
class ARConfidenceSet:
    """Anderson-Rubin (1949) weak-identification-robust confidence set for
    the single-instrument IV coefficient.

    The AR set inverts a test whose size is correct regardless of
    instrument strength, so — unlike the 2SLS/Wald bootstrap CI — it stays
    valid under a weak first stage. Operationally, ``beta0`` is IN the set
    iff we cannot reject that the instrument ``Z`` is uncorrelated with the
    structural residual ``Y - beta0*X`` (after partialing out the controls
    ``W``). For a single instrument that test statistic is a ratio of
    quadratics in ``beta0``, so the set is the solution of one quadratic
    inequality and can take five shapes (Dufour 1997):

      - ``bounded``          : ``[lower, upper]``                 (strong case)
      - ``disconnected``     : ``(-inf, lower] u [upper, +inf)``  (complement of
                               an open interval — a weak-instrument signature)
      - ``unbounded_below``  : ``(-inf, upper]``
      - ``unbounded_above``  : ``[lower, +inf)``
      - ``whole_line``       : ``(-inf, +inf)``          (instrument ~useless)

    ``lower`` / ``upper`` carry the finite endpoints where they exist and are
    ``None`` on the open side. The residualised second moments (plus ``n``,
    ``|W|``, ``kappa``) are retained so an independent verifier can re-solve
    the quadratic — and re-derive the point ``Szy/Szx`` — without the raw
    data. ``point`` is that just-identified IV point (``None`` if the first
    stage is exactly degenerate).
    """

    kind: str
    lower: float | None
    upper: float | None
    ci_level: float
    point: float | None
    kappa: float
    s_yy: float
    s_xy: float
    s_xx: float
    s_zy: float
    s_zx: float
    s_zz: float
    n_obs: int
    n_exog: int


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
    # iter 212: the Anderson-Rubin weak-identification-robust confidence set.
    # Always valid regardless of first-stage strength — the honest answer the
    # bootstrap CI cannot give when the instrument is weak. None when the AR
    # test is undefined on this data (residual df < 1, or instrument has ~no
    # residual variance).
    anderson_rubin: ARConfidenceSet | None = None


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

    try:
        ar_set = anderson_rubin_confidence_set(
            df, treatment=treatment, outcome=outcome, instrument=instrument,
            conditioning=conditioning, ci_level=ci_level,
        )
    except (np.linalg.LinAlgError, ValueError):
        ar_set = None

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
        anderson_rubin=ar_set,
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


# --- Anderson-Rubin weak-IV-robust confidence set -----------------------------


def _residualise(target: np.ndarray, w_design: np.ndarray) -> np.ndarray:
    """Residual of ``target`` after OLS on ``[1, W]`` (Frisch-Waugh-Lovell).

    ``w_design`` is the ``(n, |W|)`` control matrix WITHOUT an intercept
    column; the intercept is added here, so the ``|W| == 0`` case reduces to
    plain mean-centring.
    """
    n = target.shape[0]
    if w_design.shape[1]:
        design = np.hstack([np.ones((n, 1)), w_design])
    else:
        design = np.ones((n, 1))
    coef, *_ = np.linalg.lstsq(design, target, rcond=None)
    return target - design @ coef


def _ar_solve_set(a: float, b: float, c: float, *, atol: float):
    """Classify + solve ``{beta0 : a*beta0^2 + b*beta0 + c <= 0}``.

    Returns ``(kind, lower, upper)`` where the finite endpoints are ``None``
    on any open side. ``atol`` is the scale-aware threshold below which the
    leading coefficient counts as zero (the exactly-linear edge case).
    """
    if abs(a) <= atol:
        # Linear: b*beta0 + c <= 0.
        if abs(b) <= atol:
            return ("whole_line", None, None) if c <= 0 else ("empty", None, None)
        root = -c / b
        if b > 0:
            return ("unbounded_below", None, root)   # beta0 <= root
        return ("unbounded_above", root, None)        # beta0 >= root

    disc = b * b - 4.0 * a * c
    if a > 0:
        if disc <= 0:
            # Opens upward, never dips to <= 0 (the point estimate always
            # satisfies AR == 0, so for a just-identified single instrument
            # this branch is a numerical guard, not an expected outcome).
            return ("empty", None, None)
        sq = math.sqrt(disc)
        r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
        lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
        return ("bounded", lo, hi)                    # <= 0 BETWEEN the roots

    # a < 0.
    if disc <= 0:
        return ("whole_line", None, None)             # opens down, <= 0 always
    sq = math.sqrt(disc)
    r1, r2 = (-b - sq) / (2 * a), (-b + sq) / (2 * a)
    lo, hi = (r1, r2) if r1 <= r2 else (r2, r1)
    return ("disconnected", lo, hi)                   # <= 0 OUTSIDE (lo, hi)


def anderson_rubin_confidence_set(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    instrument: str,
    conditioning: tuple[str, ...] = (),
    ci_level: float = 0.95,
) -> ARConfidenceSet | None:
    """Single-instrument homoskedastic Anderson-Rubin confidence set.

    Residualises ``Y``, ``X``, ``Z`` on ``[1, W]`` (FWL) and inverts the test
    that ``Z`` is uncorrelated with ``Y - beta0*X``:

        ``AR(beta0) = m * N(beta0) / (T(beta0) - N(beta0))``,   ``m = n-|W|-2``
        ``N(beta0)  = (Szy - beta0*Szx)^2 / Szz``
        ``T(beta0)  = Syy - 2*beta0*Sxy + beta0^2*Sxx``

    returning ``{beta0 : AR(beta0) <= kappa}`` with the ``F(1, m)`` critical
    value ``kappa = F_{1, m; ci_level}``. Rearranged, that is the quadratic
    inequality ``A*beta0^2 + B*beta0 + C <= 0`` with ``A = g*Szx^2 - k*Sxx``,
    ``B = 2*(k*Sxy - g*Szx*Szy)``, ``C = g*Szy^2 - k*Syy`` and
    ``g = (m + kappa)/Szz`` — solved by :func:`_ar_solve_set`.

    Returns ``None`` when the test is undefined: residual df ``m < 1``, or the
    instrument has ~no residual variance (``Szz ~ 0``).
    """
    from scipy.stats import f as _f_dist

    w_cols = list(conditioning)
    n = len(data)
    n_exog = len(w_cols)
    m = n - n_exog - 2
    if m < 1:
        return None

    y = data[outcome].to_numpy(dtype=float)
    x = data[treatment].to_numpy(dtype=float)
    z = data[instrument].to_numpy(dtype=float)
    w = data[w_cols].to_numpy(dtype=float) if w_cols else np.empty((n, 0))

    yr = _residualise(y, w)
    xr = _residualise(x, w)
    zr = _residualise(z, w)

    s_yy = float(yr @ yr)
    s_xy = float(xr @ yr)
    s_xx = float(xr @ xr)
    s_zy = float(zr @ yr)
    s_zx = float(zr @ xr)
    s_zz = float(zr @ zr)

    if s_zz <= 1e-12:
        # Instrument has no residual variation — the AR test is undefined.
        return None

    kappa = float(_f_dist.ppf(ci_level, 1, m))
    g = (m + kappa) / s_zz
    a = g * s_zx * s_zx - kappa * s_xx
    b = 2.0 * (kappa * s_xy - g * s_zx * s_zy)
    c = g * s_zy * s_zy - kappa * s_yy
    a_scale = abs(g * s_zx * s_zx) + abs(kappa * s_xx) + 1.0
    kind, lower, upper = _ar_solve_set(a, b, c, atol=1e-9 * a_scale)

    point = s_zy / s_zx if abs(s_zx) > 1e-12 else None

    return ARConfidenceSet(
        kind=kind, lower=lower, upper=upper, ci_level=ci_level,
        point=point, kappa=kappa,
        s_yy=s_yy, s_xy=s_xy, s_xx=s_xx,
        s_zy=s_zy, s_zx=s_zx, s_zz=s_zz,
        n_obs=n, n_exog=n_exog,
    )


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


# --- Over-identified 2SLS + Sargan over-identification test --------------------


@dataclass(frozen=True)
class SarganTest:
    """Sargan (1958) over-identification test — homoskedastic form.

    With q > 1 instruments for a single endogenous regressor the model has
    q − 1 over-identifying restrictions. The statistic

        ``J = n · (û'P_Z û) / (û'û)``

    (û the 2SLS structural residual, P_Z the projection onto the residualised
    instrument space) is ``χ²(q − 1)`` under H0 that the instruments are
    JOINTLY valid (exclusion + exogeneity all hold). A small p-value REFUTES
    that joint validity — a data falsification of the IV model, the linear /
    continuous analogue of the Balke-Pearl instrumental inequalities. It does
    NOT move the point estimate (like the weak-instrument F, it is a
    diagnostic). This is the HOMOSKEDASTIC form; its heteroskedasticity-robust
    (efficient two-step GMM) generalisation is the companion ``HansenJTest``,
    which uses the robust weight matrix and is the more defensible falsification
    under heteroskedasticity / clustering.
    """

    j_stat: float
    dof: int          # q − 1
    p_value: float


@dataclass(frozen=True)
class HansenJTest:
    """Hansen (1982) over-identification test — the heteroskedasticity-robust
    (efficient two-step GMM) generalisation of the homoskedastic Sargan.

    Whereas Sargan weights the moments by the homoskedastic ``σ̂²·(Z'Z)``, the
    Hansen J uses the robust weight matrix ``Ŝ = (1/n) Σ û_i² z_i z_i'`` (or its
    cluster-robust sum), which is the CORRECT weighting when the structural error
    is heteroskedastic (or clustered). The statistic

        ``J = n · ḡ(β̂₂)' Ŝ⁻¹ ḡ(β̂₂)``,  ḡ(β) = (1/n)(Z'y − β·Z'x)

    evaluated at the efficient two-step GMM point ``β̂₂`` (the minimiser of the
    robustly-weighted objective) is ``χ²(q − 1)`` under the same H0 that the q
    instruments are JOINTLY valid. It coincides with Sargan under homoskedasticity
    and is the more defensible over-identification falsification otherwise. Like
    Sargan it does NOT move the headline point (which stays 2SLS); ``gmm_point``
    is the efficient GMM byproduct, reported for transparency."""

    j_stat: float
    dof: int          # q − 1
    p_value: float
    gmm_point: float  # efficient two-step GMM coefficient on the treatment


@dataclass(frozen=True)
class OverIDARConfidenceSet:
    """Anderson-Rubin weak-identification-robust confidence set for the
    OVER-IDENTIFIED IV coefficient (q ≥ 2 instruments, single endogenous
    treatment) — the multi-instrument counterpart of ``ARConfidenceSet``.

    The over-identified path detects a weak JOINT first stage (the joint F) but
    its only interval is the bootstrap CI, which — exactly as in the just-
    identified case — is invalid when the instruments are jointly weak. The AR
    set inverts a test whose size is correct regardless of instrument strength:
    ``beta0`` is IN the set iff we cannot reject that the q instruments are
    jointly uncorrelated with the structural residual ``Y − beta0·X`` (after
    partialing out ``W``). For a single endogenous regressor that statistic is
    still a RATIO OF QUADRATICS in ``beta0`` — the q-dimensional projection only
    changes the coefficients, not the algebra — so the set is again the solution
    of one quadratic inequality and takes the same five Dufour (1997) shapes:

        ``AR(beta0) = [N(beta0)/q] / [(T(beta0)−N(beta0))/m] ~ F(q, m)``
        ``N(beta0)  = (ỹ − beta0·x̃)' P_Z (ỹ − beta0·x̃)``   (q-dim projection)
        ``T(beta0)  = (ỹ − beta0·x̃)'(ỹ − beta0·x̃)``,   ``m = n − |W| − q − 1``

    Inverted, ``{beta0 : AR ≤ F(q,m)}`` is ``A·beta0² + B·beta0 + C ≤ 0`` with
    ``kappa = q·F(q, m)`` (the multi-instrument generalisation of the single-
    instrument ``F(1, m)``). Unlike the just-identified set, the 2SLS ``point``
    need NOT lie in this set — when the over-identifying restrictions are
    violated ``N(point) = û'P_Z û`` (the Sargan numerator) is strictly positive,
    so the point can fall outside its own AR set. The residualised second-moment
    MATRICES live in the estimate's ``moments`` dict, so an independent verifier
    re-derives ``A/B/C`` and re-solves without the raw data.

    ``dof_num = q``; ``dof_denom = m``. ``point`` is the 2SLS coefficient
    (``= x'P_Z y / x'P_Z x``); ``None`` if the first stage is exactly degenerate.
    """

    kind: str
    lower: float | None
    upper: float | None
    ci_level: float
    point: float | None
    kappa: float
    dof_num: int
    dof_denom: int


@dataclass(frozen=True)
class RobustARConfidenceSet:
    """Heteroskedasticity-robust Anderson-Rubin confidence set (Stock-Wright 2000
    S-statistic / Kleibergen 2005 robust AR) for the over-identified IV
    coefficient -- valid under weak identification AND heteroskedasticity (or
    clustering) at once.

    The homoskedastic AR set (``OverIDARConfidenceSet``) weights the moments by
    the homoskedastic residual variance; under heteroskedasticity that weighting
    is wrong (the same defect Sargan has vs the robust Hansen J), so its coverage
    is off. The robust AR inverts the identification-robust statistic

        ``AR_r(beta0) = n * gbar(beta0)' Shat(beta0)^-1 gbar(beta0) ~ chi^2(q)``
        ``gbar(beta0) = (1/n) Z'(y - beta0*x)``
        ``Shat(beta0) = (1/n) sum_i (y_i - beta0*x_i)^2 z_i z_i'``   (HC0)
                      = (1/n) sum_c (sum_{i in c} (..) z_i)(..)'      (cluster CR0)

    (all residualised on ``[1, W]``). Because ``Shat(beta0)`` depends on beta0,
    ``AR_r`` is NOT a ratio of quadratics -- but the boundary ``{AR_r = crit}`` is
    exactly the real roots of the degree-``<=2q`` polynomial
    ``P(beta0) = N(beta0) - crit*D(beta0)`` (``D = det Shat``,
    ``N = n*gbar'adj(Shat)gbar``), so the set is found by EXACT polynomial
    root-finding, not a grid. ``Shat(beta0)`` is a sum of PSD rank-1 terms for
    every beta0, so ``AR_r`` is finite everywhere and BOTH tails share the same
    finite asymptote ``asymptote = (1/n) zx' S2^-1 zx``, which sets the tail
    membership (``asymptote <= crit`` -> the set is unbounded -- the honest
    weak-identification signal). ``crit = chi^2(q; ci_level)``.

    ``segments`` is the set as a tuple of ``(lower, upper)`` intervals (``None`` on
    an open side); ``crossings`` the sorted finite boundary points; ``kind`` a
    summary label (``bounded`` / ``disconnected`` = two rays / ``whole_line`` /
    ``empty`` / ``union`` = >2 segments / one-sided rays). The robust second-moment
    matrices ``S0/S1/S2`` (``Shat(beta0) = S0 - beta0*S1 + beta0^2*S2``) are retained
    in the estimate's ``moments`` so an independent verifier can re-evaluate
    ``AR_r`` at any beta0 and re-solve without the raw data.
    """

    kind: str
    segments: tuple
    crossings: tuple
    asymptote: float
    crit: float
    ci_level: float
    dof: int                  # q
    point: float | None
    cluster_robust: bool


@dataclass(frozen=True)
class OverIDIVEstimate:
    """Over-identified two-stage least squares (q ≥ 2 instruments, single
    endogenous treatment) + the Sargan over-identification test.

    ``point`` is the 2SLS coefficient on the treatment; ``sargan`` is the
    joint-validity falsification test. ``first_stage_f_stat`` is the JOINT F
    for all instruments (the multi-instrument weak-IV signal). The
    residualised second-moment matrices are retained so an independent
    verifier can re-derive both the point and the Sargan statistic without the
    raw data.
    """

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str                       # "iv_2sls_overid"
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    instruments: tuple[str, ...]
    conditioning: tuple[str, ...]
    treatment: str
    outcome: str
    n_instruments: int
    first_stage_f_stat: float | None
    sargan: SarganTest | None
    hansen: HansenJTest | None
    # Residualised (FWL, on [1, W]) second moments — the verifier's inputs.
    # zz: (q, q) list-of-lists; zx, zy: length-q lists; xx/xy/yy: scalars; and
    # (when Hansen J was computed) s_robust: (q, q) robust weight matrix Ŝ.
    moments: dict
    cluster: str | None = None
    # iter 240: the multi-instrument Anderson-Rubin weak-identification-robust
    # confidence set. Valid whatever the JOINT first-stage strength — the honest
    # interval the bootstrap CI cannot give when the instruments are jointly
    # weak. None when the AR test is undefined (residual df < 1, or Z'Z singular).
    anderson_rubin: OverIDARConfidenceSet | None = None
    # iter 246: the heteroskedasticity-robust (Stock-Wright S / Kleibergen) AR
    # set — valid under weak identification AND heteroskedasticity/clustering at
    # once. None when the robust inversion is degenerate (leaves the rest of the
    # estimate standing, like the homoskedastic AR set).
    robust_anderson_rubin: "RobustARConfidenceSet | None" = None


def _residualise_iv_columns(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, int]:
    """Residualise Y, X, and each instrument on ``[1, W]`` (FWL). Returns the
    ``(n,)`` residual arrays ``(zr (n, q), xr, yr)`` and ``|W|``. The residualised
    columns feed both the second-moment matrices (2SLS point + Sargan) and the
    per-observation robust weight matrix Ŝ (Hansen J)."""
    n = len(df)
    w_cols = list(conditioning)
    w = df[w_cols].to_numpy(dtype=float) if w_cols else np.empty((n, 0))
    yr = _residualise(df[outcome].to_numpy(dtype=float), w)
    xr = _residualise(df[treatment].to_numpy(dtype=float), w)
    zr = np.column_stack([
        _residualise(df[z].to_numpy(dtype=float), w) for z in instruments
    ])  # (n, q)
    return zr, xr, yr, len(w_cols)


def _moments_from_arrays(
    zr: np.ndarray, xr: np.ndarray, yr: np.ndarray, n_exog: int,
) -> dict:
    """Second-moment matrices from residualised columns — the 2SLS point and
    Sargan statistic are closed forms of these."""
    zz = zr.T @ zr
    zx = zr.T @ xr
    zy = zr.T @ yr
    return {
        "zz": zz.tolist(),
        "zx": zx.tolist(),
        "zy": zy.tolist(),
        "xx": float(xr @ xr),
        "xy": float(xr @ yr),
        "yy": float(yr @ yr),
        "n": int(len(xr)),
        "n_exog": int(n_exog),
        "q": int(zr.shape[1]),
    }


def _overid_moments(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...],
) -> dict:
    """Residualise Y, X, and each instrument on ``[1, W]`` (FWL) and return
    the second-moment matrices the 2SLS point and Sargan statistic are closed
    forms of."""
    zr, xr, yr, n_exog = _residualise_iv_columns(
        df, treatment, outcome, instruments, conditioning,
    )
    return _moments_from_arrays(zr, xr, yr, n_exog)


def _robust_weight_matrix(
    zr: np.ndarray,
    xr: np.ndarray,
    yr: np.ndarray,
    beta: float,
    groups: np.ndarray | None = None,
) -> np.ndarray:
    """The robust GMM weight-variance estimator Ŝ, an estimate of
    ``Avar(√n · (1/n) Z'û)`` at the step-1 (2SLS) residuals ``û = ỹ − β·x̃``.

    - ``groups is None`` → heteroskedasticity-robust HC0:
      ``Ŝ = (1/n) Σ_i û_i² z_i z_i'`` (a sum of rank-1 PSD terms).
    - ``groups`` given → cluster-robust CR0:
      ``Ŝ = (1/n) Σ_c (Σ_{i∈c} û_i z_i)(Σ_{i∈c} û_i z_i)'`` — the correct object
      when the design is clustered; under a declared cluster a heteroskedasticity-
      only Ŝ would wrongly assume within-cluster independence.

    No small-sample HC1/CR1 multiplier (declared). Raises ``ValueError`` if the
    cluster labels are misaligned with the residualised rows (caller degrades to
    no-Hansen)."""
    n = len(xr)
    u = yr - beta * xr
    g = zr * u[:, None]                       # (n, q): per-obs moment z_i · û_i
    if groups is None:
        s = g.T @ g / n
    else:
        groups = np.asarray(groups)
        if len(groups) != n:
            raise ValueError("cluster labels misaligned with residualised rows")
        gsum = np.array([g[groups == c].sum(axis=0) for c in np.unique(groups)])
        s = gsum.T @ gsum / n
    return s


def solve_hansen_from_s(m: dict) -> dict:
    """Efficient two-step GMM point + Hansen (1982) J as closed forms of the
    robust weight matrix Ŝ (``s_robust``) and the residualised cross-moments
    Z'x / Z'y. The PRODUCER-side transcription; the verifier re-derives with its
    OWN independent one (never importing this), so a bug here is caught.

        β̂₂ = (Z'x)' Ŝ⁻¹ (Z'y) / (Z'x)' Ŝ⁻¹ (Z'x)          (efficient GMM point)
        ḡ  = (1/n)(Z'y − β̂₂·Z'x)                            (moment vector at β̂₂)
        J  = n · ḡ' Ŝ⁻¹ ḡ  ~  χ²(q − 1)                      (Hansen J)

    Reduces to the homoskedastic Sargan when Ŝ = σ̂²·(Z'Z)/n. Raises
    ``np.linalg.LinAlgError`` when Ŝ is singular, ``ValueError`` when the
    efficient first stage is degenerate."""
    q = int(m["q"]); n = int(m["n"])
    zx = np.asarray(m["zx"], dtype=float).reshape(q)
    zy = np.asarray(m["zy"], dtype=float).reshape(q)
    s = np.asarray(m["s_robust"], dtype=float).reshape(q, q)
    s_inv = np.linalg.inv(s)
    denom = float(zx @ s_inv @ zx)
    if not math.isfinite(denom) or abs(denom) < 1e-12:
        raise ValueError("efficient-GMM first stage degenerate: x'Ŝ⁻¹x ~ 0")
    beta2 = float(zx @ s_inv @ zy) / denom
    g = (zy - beta2 * zx) / n
    j = float(n * (g @ s_inv @ g))
    return {"gmm_point": beta2, "j_stat": j, "dof": q - 1}


def _hansen_robust_j(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...],
    *,
    m: dict,
    beta: float,
    groups: np.ndarray | None,
) -> tuple["HansenJTest | None", list | None]:
    """Compute the efficient two-step GMM Hansen J from the robust weight matrix
    at the 2SLS residuals. Returns ``(HansenJTest, s_robust_list)`` or
    ``(None, None)`` when Ŝ is singular / degenerate — Hansen is an ADD-ON
    diagnostic, so a degenerate robust weight leaves the 2SLS + Sargan estimate
    standing rather than failing it."""
    from scipy.stats import chi2 as _chi2

    zr, xr, yr, _ = _residualise_iv_columns(
        df, treatment, outcome, instruments, conditioning,
    )
    try:
        s = _robust_weight_matrix(zr, xr, yr, beta, groups)
        solved = solve_hansen_from_s({**m, "s_robust": s.tolist()})
    except (np.linalg.LinAlgError, ValueError):
        return None, None
    dof = int(solved["dof"])
    p = float(_chi2.sf(solved["j_stat"], dof)) if dof >= 1 else float("nan")
    hansen = HansenJTest(
        j_stat=float(solved["j_stat"]), dof=dof, p_value=p,
        gmm_point=float(solved["gmm_point"]),
    )
    return hansen, s.tolist()


def solve_overid_from_moments(m: dict) -> dict:
    """2SLS point + Sargan J + joint first-stage F, as closed forms of the
    residualised moments. The PRODUCER-side transcription (used by the
    estimator and its bootstrap); the verifier re-derives the same quantities
    with its OWN independent transcription of these formulas (never importing
    this one), so a bug here is caught rather than mirrored.

    Raises ``np.linalg.LinAlgError`` when Z'Z is singular (collinear
    instruments) and ``ValueError`` when the first stage is degenerate
    (x'P_Z x ≈ 0) or the residual variance is non-positive.
    """
    zz = np.asarray(m["zz"], dtype=float).reshape(m["q"], m["q"])
    zx = np.asarray(m["zx"], dtype=float).reshape(m["q"])
    zy = np.asarray(m["zy"], dtype=float).reshape(m["q"])
    xx, xy, yy = float(m["xx"]), float(m["xy"]), float(m["yy"])
    n, n_exog, q = int(m["n"]), int(m["n_exog"]), int(m["q"])

    zz_inv = np.linalg.inv(zz)
    x_pz_x = float(zx @ zz_inv @ zx)          # x'P_Z x
    x_pz_y = float(zx @ zz_inv @ zy)          # x'P_Z y
    if not math.isfinite(x_pz_x) or abs(x_pz_x) < 1e-12:
        raise ValueError("first stage degenerate: x'P_Z x ~ 0")
    beta = x_pz_y / x_pz_x

    # Sargan: û = ỹ − β·x̃ ; J = n · (û'P_Z û)/(û'û).
    a = zy - beta * zx                        # Z'û
    u_pz_u = float(a @ zz_inv @ a)            # û'P_Z û
    u_u = yy - 2.0 * beta * xy + beta * beta * xx   # û'û
    if not math.isfinite(u_u) or u_u <= 0:
        raise ValueError("non-positive structural residual sum of squares")
    j_stat = n * u_pz_u / u_u
    dof = q - 1

    # Joint first-stage F for all q instruments: SSR restricted = x̃'x̃ = xx,
    # SSR full = xx − x'P_Z x. F = ((SSR_R − SSR_F)/q)/(SSR_F/(n − q − n_exog − 1)).
    ssr_full = xx - x_pz_x
    df_resid = n - q - n_exog - 1
    if ssr_full > 1e-12 and df_resid >= 1:
        joint_f = (x_pz_x / q) / (ssr_full / df_resid)
    else:
        joint_f = None

    return {
        "beta": beta,
        "j_stat": j_stat,
        "dof": dof,
        "u_u": u_u,
        "joint_f": joint_f,
    }


def anderson_rubin_overid_set(
    m: dict, ci_level: float = 0.95,
) -> "OverIDARConfidenceSet | None":
    """Multi-instrument (q ≥ 2, single endogenous) homoskedastic Anderson-Rubin
    confidence set, as a pure closed form of the residualised second moments in
    ``m`` (the same ``moments`` dict the 2SLS point + Sargan J ride on).

    The q-dimensional projection quadratic forms
    ``P_yy = (Z'y)'(Z'Z)⁻¹(Z'y)``, ``P_xy = (Z'x)'(Z'Z)⁻¹(Z'y)``,
    ``P_xx = (Z'x)'(Z'Z)⁻¹(Z'x)`` give ``N(beta0) = P_yy − 2β0·P_xy + β0²·P_xx``
    and ``T(beta0) = yy − 2β0·xy + β0²·xx``. Inverting ``AR(beta0) ≤ F(q, m)``
    (``m = n − |W| − q − 1``) with ``kappa = q·F(q, m; ci_level)``,
    ``G = m + kappa`` yields ``A·β0² + B·β0 + C ≤ 0``:

        ``A = G·P_xx − kappa·xx``
        ``B = 2·(kappa·xy − G·P_xy)``
        ``C = G·P_yy − kappa·yy``

    solved (into the five Dufour shapes) by :func:`_ar_solve_set`. For ``q = 1``
    this reduces to :func:`anderson_rubin_confidence_set` exactly. Returns
    ``None`` when the test is undefined: residual df ``m < 1``, or ``Z'Z``
    singular (collinear instruments)."""
    from scipy.stats import f as _f_dist

    q = int(m["q"]); n = int(m["n"]); n_exog = int(m["n_exog"])
    m_denom = n - n_exog - q - 1
    if m_denom < 1:
        return None

    zz = np.asarray(m["zz"], dtype=float).reshape(q, q)
    zx = np.asarray(m["zx"], dtype=float).reshape(q)
    zy = np.asarray(m["zy"], dtype=float).reshape(q)
    xx, xy, yy = float(m["xx"]), float(m["xy"]), float(m["yy"])

    try:
        zz_inv = np.linalg.inv(zz)
    except np.linalg.LinAlgError:
        return None

    p_yy = float(zy @ zz_inv @ zy)
    p_xy = float(zx @ zz_inv @ zy)
    p_xx = float(zx @ zz_inv @ zx)

    kappa = float(q) * float(_f_dist.ppf(ci_level, q, m_denom))
    g = m_denom + kappa
    a = g * p_xx - kappa * xx
    b = 2.0 * (kappa * xy - g * p_xy)
    c = g * p_yy - kappa * yy
    a_scale = abs(g * p_xx) + abs(kappa * xx) + 1.0
    kind, lower, upper = _ar_solve_set(a, b, c, atol=1e-9 * a_scale)

    point = p_xy / p_xx if abs(p_xx) > 1e-12 else None

    return OverIDARConfidenceSet(
        kind=kind, lower=lower, upper=upper, ci_level=ci_level,
        point=point, kappa=kappa, dof_num=q, dof_denom=m_denom,
    )


# --- heteroskedasticity-robust Anderson-Rubin (Stock-Wright S) set ------------


def _robust_moment_matrices(
    zr: np.ndarray, xr: np.ndarray, yr: np.ndarray,
    groups: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The three q×q matrices with ``Ŝ(β0) = S0 − β0·S1 + β0²·S2`` the robust GMM
    weight at the residual ``ỹ − β0·x̃`` for EVERY β0 (not just the 2SLS point).

    HC0 (``groups is None``): ``S0 = (1/n)Σ ỹ²zz'``, ``S1 = 2(1/n)Σ x̃ỹ zz'``,
    ``S2 = (1/n)Σ x̃² zz'`` — so ``Ŝ(β0) = (1/n)Σ(ỹ−β0x̃)² zz'``. Cluster-robust
    CR0 (``groups`` given): the same expansion of the cluster-sum outer products,
    ``S0 = (1/n)Σ_c a_c a_c'``, ``S1 = (1/n)Σ_c (a_c b_c' + b_c a_c')``,
    ``S2 = (1/n)Σ_c b_c b_c'`` with ``a_c = Σ_{i∈c} ỹ_i z_i``, ``b_c = Σ_{i∈c} x̃_i z_i``.

    Raises ``ValueError`` if cluster labels are misaligned (caller degrades to no
    robust-AR set)."""
    n = len(xr)
    if groups is None:
        gy = zr * yr[:, None]
        gx = zr * xr[:, None]
        s0 = gy.T @ gy / n
        s2 = gx.T @ gx / n
        s1 = 2.0 * (gx.T @ gy) / n
    else:
        groups = np.asarray(groups)
        if len(groups) != n:
            raise ValueError("cluster labels misaligned with residualised rows")
        q = zr.shape[1]
        s0 = np.zeros((q, q)); s1 = np.zeros((q, q)); s2 = np.zeros((q, q))
        for c in np.unique(groups):
            mask = groups == c
            a = (zr[mask] * yr[mask, None]).sum(axis=0)
            b = (zr[mask] * xr[mask, None]).sum(axis=0)
            s0 += np.outer(a, a)
            s2 += np.outer(b, b)
            s1 += np.outer(a, b) + np.outer(b, a)
        s0 /= n; s1 /= n; s2 /= n
    return s0, s1, s2


def robust_ar_statistic(
    beta0: float, zx: np.ndarray, zy: np.ndarray,
    s0: np.ndarray, s1: np.ndarray, s2: np.ndarray, n: int,
) -> float:
    """``AR_r(β0) = n · ḡ(β0)' Ŝ(β0)⁻¹ ḡ(β0)`` with ``ḡ(β0) = (1/n)(Z'y − β0·Z'x)``
    and ``Ŝ(β0) = S0 − β0·S1 + β0²·S2``. Raises ``np.linalg.LinAlgError`` if
    ``Ŝ(β0)`` is singular (measure-zero; the caller skips that β0)."""
    g = (zy - beta0 * zx) / n
    s = s0 - beta0 * s1 + beta0 * beta0 * s2
    return float(n * (g @ np.linalg.solve(s, g)))


def _classify_robust_ar_segments(segments: list) -> str:
    """Summary label for the robust-AR set from its ``(lo, hi)`` segment list."""
    if not segments:
        return "empty"
    if len(segments) == 1:
        lo, hi = segments[0]
        if lo is None and hi is None:
            return "whole_line"
        if lo is None:
            return "unbounded_below"
        if hi is None:
            return "unbounded_above"
        return "bounded"
    if (len(segments) == 2 and segments[0][0] is None
            and segments[-1][1] is None):
        return "disconnected"
    return "union"


def _robust_ar_interval_probe(lo, hi):
    """A test β0 strictly inside the interval ``(lo, hi)`` (None = ±∞)."""
    if lo is None and hi is None:
        return 0.0
    if lo is None:
        return hi - 1.0
    if hi is None:
        return lo + 1.0
    return 0.5 * (lo + hi)


def _solve_robust_ar_set(
    zx, zy, s0, s1, s2, n, q, crit, point,
):
    """Invert ``{β0 : AR_r(β0) ≤ crit}`` exactly via polynomial roots.

    Returns ``(kind, segments, crossings, asymptote)`` or ``None`` on a
    degenerate / self-inconsistent inversion. The boundary is the real roots of
    ``P(β0) = N(β0) − crit·D(β0)`` (degree ``≤ 2q``); ``P`` is recovered exactly by
    a well-conditioned Chebyshev fit of ``P(β0) = det(Ŝ)·(AR_r − crit)`` at
    ``2q+1`` nodes, then ``chebroots``. Tail membership comes from the shared
    finite asymptote ``(1/n) zx' S2⁻¹ zx``. A self-consistency check (interior of
    every claimed interval ``≤ crit``, exterior ``> crit``) guards the numerics."""
    from numpy.polynomial import chebyshev as _cheb

    def arv(b):
        return robust_ar_statistic(b, zx, zy, s0, s1, s2, n)

    # Shared tail asymptote (S2 PSD; singular only if instruments carry no
    # residual x-variation at all -> no tail information -> tail in the set).
    try:
        asymptote = float((zx @ np.linalg.solve(s2, zx)) / n)
    except np.linalg.LinAlgError:
        asymptote = 0.0
    tails_in = asymptote <= crit

    # Local scale: fit a parabola through AR_r at point, point ± h.
    try:
        a0 = arv(point)
    except np.linalg.LinAlgError:
        return None
    h = 0.5 * (abs(point) + 1.0)
    ap = am = None
    for _ in range(8):
        try:
            ap, am = arv(point + h), arv(point - h)
            break
        except np.linalg.LinAlgError:
            h *= 0.5
    if ap is None:
        return None
    curv = (ap + am - 2.0 * a0) / (2.0 * h * h)          # ≈ AR_r''(point)/...
    if curv > 1e-9 and crit > a0:
        width = math.sqrt((crit - a0) / curv)
    else:
        width = 4.0 * (abs(point) + 1.0)                 # flat / weak -> wide
    span = max(width, h) * 10.0

    # Chebyshev-fit P over point ± span (exact: P is degree ≤ 2q).
    deg = 2 * q
    nodes = point + span * np.cos(np.linspace(0.0, math.pi, deg + 1))
    xs, ps = [], []
    for t in nodes:
        s = s0 - t * s1 + t * t * s2
        try:
            d = float(np.linalg.det(s))
            ar = arv(t)
        except np.linalg.LinAlgError:
            continue
        xs.append(t); ps.append(d * (ar - crit))
    if len(xs) < deg + 1:
        return None
    try:
        coeffs = _cheb.chebfit(np.asarray(xs), np.asarray(ps), deg)
        roots = _cheb.chebroots(coeffs)
    except (np.linalg.LinAlgError, ValueError):
        return None

    crossings = []
    for r in roots:
        if abs(r.imag) > 1e-6 * (1.0 + abs(r.real)):
            continue
        b = float(r.real)
        try:
            val = arv(b)
        except np.linalg.LinAlgError:
            continue
        if abs(val - crit) <= 1e-4 * (1.0 + crit):       # a genuine crossing
            crossings.append(b)
    crossings.sort()
    deduped = []
    for b in crossings:
        if not deduped or abs(b - deduped[-1]) > 1e-7 * (1.0 + abs(b)):
            deduped.append(b)
    crossings = deduped

    # Build segments by walking membership from -inf, flipping at each crossing.
    segments, member, prev = [], tails_in, None
    for c in crossings:
        if member:
            segments.append((prev, c))
        member = not member
        prev = c
    if member:
        segments.append((prev, None))

    # Self-consistency: each of the k+1 intervals must have AR_r on the claimed
    # side of crit at an interior probe (the exact polynomial should guarantee
    # this; the guard rejects a numerically unreliable inversion -> None).
    bounds = [None, *crossings, None]
    expect = tails_in
    for i in range(len(bounds) - 1):
        b = _robust_ar_interval_probe(bounds[i], bounds[i + 1])
        try:
            v = arv(b)
        except np.linalg.LinAlgError:
            return None
        if (v <= crit) != expect and abs(v - crit) > 1e-4 * (1.0 + crit):
            return None
        expect = not expect

    kind = _classify_robust_ar_segments(segments)
    return kind, tuple(segments), tuple(crossings), asymptote


def robust_anderson_rubin_overid_set(
    m: dict, ci_level: float = 0.95, cluster_robust: bool = False,
) -> "RobustARConfidenceSet | None":
    """Heteroskedasticity-robust (Stock-Wright S / Kleibergen) Anderson-Rubin
    confidence set as a closed form of the residualised moments in ``m`` — which
    must carry the robust second-moment matrices ``s0`` / ``s1`` / ``s2`` (added by
    :func:`estimate_iv_overid`) alongside ``zz`` / ``zx`` / ``zy`` / ``n`` / ``q``.

    The 2SLS point (from ``zz``) centres the polynomial root search. Returns
    ``None`` when the inversion is degenerate (first stage exactly degenerate,
    ``Ŝ`` singular, or the numeric inversion fails its self-consistency check),
    leaving the rest of the estimate standing."""
    from scipy.stats import chi2 as _chi2

    q = int(m["q"]); n = int(m["n"])
    zz = np.asarray(m["zz"], dtype=float).reshape(q, q)
    zx = np.asarray(m["zx"], dtype=float).reshape(q)
    zy = np.asarray(m["zy"], dtype=float).reshape(q)
    s0 = np.asarray(m["s0"], dtype=float).reshape(q, q)
    s1 = np.asarray(m["s1"], dtype=float).reshape(q, q)
    s2 = np.asarray(m["s2"], dtype=float).reshape(q, q)

    crit = float(_chi2.ppf(ci_level, q))
    try:
        zz_inv = np.linalg.inv(zz)
    except np.linalg.LinAlgError:
        return None
    denom = float(zx @ zz_inv @ zx)
    if not math.isfinite(denom) or abs(denom) < 1e-12:
        return None
    point = float(zx @ zz_inv @ zy) / denom

    solved = _solve_robust_ar_set(zx, zy, s0, s1, s2, n, q, crit, point)
    if solved is None:
        return None
    kind, segments, crossings, asymptote = solved
    return RobustARConfidenceSet(
        kind=kind, segments=segments, crossings=crossings, asymptote=asymptote,
        crit=crit, ci_level=ci_level, dof=q, point=point,
        cluster_robust=cluster_robust,
    )


def estimate_iv_overid(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...] = (),
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> OverIDIVEstimate:
    """Over-identified 2SLS (q ≥ 2 instruments) + Sargan over-identification
    test for a single endogenous ``treatment``.

    Stage 1 regresses ``X`` on ``[Z_1..Z_q, W]``; stage 2 the 2SLS point is the
    coefficient on the fitted X. The Sargan J tests whether the q instruments
    are JOINTLY valid — a small p-value means the data refute the over-identifying
    restrictions the graph asserts. Bootstrap percentile CI on the point (parity
    with the just-identified path). Raises ``ValueError`` on a degenerate design
    (collinear instruments / no first stage), which the caller treats as "fall
    back to the just-identified estimate".
    """
    from scipy.stats import chi2 as _chi2

    if len(instruments) < 2:
        raise ValueError(
            "estimate_iv_overid requires ≥ 2 instruments; use estimate_iv_ate "
            "for the just-identified case"
        )

    required = {treatment, outcome, *instruments, *conditioning}
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None else None
    )
    contract = validate_data(
        data, required_columns=required, presence_columns=presence,
    )
    df = contract.data

    m = _overid_moments(df, treatment, outcome, instruments, conditioning)
    try:
        solved = solve_overid_from_moments(m)
    except np.linalg.LinAlgError as exc:
        raise ValueError(f"over-identified 2SLS design is singular: {exc}")

    point = solved["beta"]
    j_stat = solved["j_stat"]
    dof = solved["dof"]
    p_value = float(_chi2.sf(j_stat, dof)) if dof >= 1 else float("nan")
    sargan = SarganTest(j_stat=float(j_stat), dof=int(dof), p_value=p_value)

    # Heteroskedasticity-robust (cluster-robust under a declared cluster) Hansen
    # J via efficient two-step GMM. An add-on diagnostic: a degenerate robust
    # weight leaves the 2SLS + Sargan estimate standing (hansen stays None). Its
    # robust weight matrix Ŝ is recorded into `m` for the verifier.
    hansen, s_robust = _hansen_robust_j(
        df, treatment, outcome, instruments, conditioning,
        m=m, beta=point, groups=groups,
    )
    if s_robust is not None:
        m["s_robust"] = s_robust

    # Multi-instrument Anderson-Rubin weak-ID-robust confidence set — a pure
    # closed form of the moments already in `m`. Valid whatever the joint first
    # stage strength (the bootstrap CI below is not). None when the AR test is
    # undefined (residual df < 1 / Z'Z singular), leaving the estimate standing.
    ar_set = anderson_rubin_overid_set(m, ci_level=ci_level)

    # Heteroskedasticity-robust (Stock-Wright S) AR set — valid under weak
    # identification AND heteroskedasticity/clustering at once. Its β0-dependent
    # robust weight needs the three matrices S0/S1/S2 (Ŝ(β0) = S0 − β0·S1 + β0²·S2),
    # recorded into `m` for the verifier. Degenerate inversion -> None (add-on).
    robust_ar_set = None
    try:
        zr_r, xr_r, yr_r, _ = _residualise_iv_columns(
            df, treatment, outcome, instruments, conditioning,
        )
        s0, s1, s2 = _robust_moment_matrices(zr_r, xr_r, yr_r, groups)
        m["s0"] = s0.tolist(); m["s1"] = s1.tolist(); m["s2"] = s2.tolist()
        robust_ar_set = robust_anderson_rubin_overid_set(
            m, ci_level=ci_level, cluster_robust=cluster is not None,
        )
    except (np.linalg.LinAlgError, ValueError):
        robust_ar_set = None

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_overid(
            df, treatment, outcome, instruments, conditioning,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    overid_test_assumption = (
        "overidentifying_restrictions_testable_via_sargan_and_robust_hansen_j"
        if hansen is not None
        else "overidentifying_restrictions_testable_via_sargan_homoskedastic"
    )
    assumptions = (
        "iv1_relevance_instruments_affect_treatment",
        "iv2_exclusion_instruments_affect_outcome_only_via_treatment",
        "iv3_independence_instruments_independent_of_latent_confounders",
        "linearity_of_first_and_second_stage",
        "constant_treatment_effect_else_estimand_is_weighted_average",
        overid_test_assumption,
    )
    if conditioning:
        assumptions = assumptions + (
            "conditioning_set_blocks_instrument_outcome_backdoor_given_W",
        )
    if cluster is not None:
        assumptions = assumptions + (
            f"ci_via_pairs_cluster_bootstrap_on_{cluster}",
        )

    return OverIDIVEstimate(
        point=float(point),
        ci_lower=float(ci_lower) if ci_lower is not None else None,
        ci_upper=float(ci_upper) if ci_upper is not None else None,
        ci_level=ci_level,
        method="iv_2sls_overid",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        instruments=tuple(instruments),
        conditioning=tuple(conditioning),
        treatment=treatment,
        outcome=outcome,
        n_instruments=len(instruments),
        first_stage_f_stat=solved["joint_f"],
        sargan=sargan,
        hansen=hansen,
        moments=m,
        cluster=cluster,
        anderson_rubin=ar_set,
        robust_anderson_rubin=robust_ar_set,
    )


def _overid_point(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...],
) -> float:
    """Just the 2SLS point (for the bootstrap loop)."""
    m = _overid_moments(df, treatment, outcome, instruments, conditioning)
    return float(solve_overid_from_moments(m)["beta"])


def _bootstrap_ci_overid(
    df: pd.DataFrame,
    treatment: str,
    outcome: str,
    instruments: tuple[str, ...],
    conditioning: tuple[str, ...],
    *,
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
        try:
            estimates[i] = _overid_point(
                df.iloc[idx], treatment, outcome, instruments, conditioning,
            )
        except (ValueError, np.linalg.LinAlgError):
            estimates[i] = np.nan
    estimates = estimates[~np.isnan(estimates)]
    if len(estimates) == 0:
        raise ValueError(
            "all bootstrap iterations failed — data is pathological for "
            "over-identified 2SLS"
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
