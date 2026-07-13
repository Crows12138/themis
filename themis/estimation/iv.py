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
    diagnostic). Homoskedastic: the heteroskedasticity-robust Hansen J is
    deferred (declared), mirroring the homoskedastic Anderson-Rubin set.
    """

    j_stat: float
    dof: int          # q − 1
    p_value: float


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
    # Residualised (FWL, on [1, W]) second moments — the verifier's inputs.
    # zz: (q, q) list-of-lists; zx, zy: length-q lists; xx/xy/yy: scalars.
    moments: dict
    cluster: str | None = None


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
    n = len(df)
    w_cols = list(conditioning)
    w = df[w_cols].to_numpy(dtype=float) if w_cols else np.empty((n, 0))
    yr = _residualise(df[outcome].to_numpy(dtype=float), w)
    xr = _residualise(df[treatment].to_numpy(dtype=float), w)
    zr = np.column_stack([
        _residualise(df[z].to_numpy(dtype=float), w) for z in instruments
    ])  # (n, q)
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
        "n": int(n),
        "n_exog": len(w_cols),
        "q": len(instruments),
    }


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

    ci_lower: float | None = None
    ci_upper: float | None = None
    if ci_bootstrap > 0:
        ci_lower, ci_upper = _bootstrap_ci_overid(
            df, treatment, outcome, instruments, conditioning,
            ci_bootstrap=ci_bootstrap, ci_level=ci_level,
            random_state=random_state, groups=groups,
        )

    assumptions = (
        "iv1_relevance_instruments_affect_treatment",
        "iv2_exclusion_instruments_affect_outcome_only_via_treatment",
        "iv3_independence_instruments_independent_of_latent_confounders",
        "linearity_of_first_and_second_stage",
        "constant_treatment_effect_else_estimand_is_weighted_average",
        "overidentifying_restrictions_testable_via_sargan_homoskedastic",
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
        moments=m,
        cluster=cluster,
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
