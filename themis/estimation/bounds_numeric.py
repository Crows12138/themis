"""Numeric end for the partial-identification (bounds) layer.

When point identification fails, ``themis/output/bounds.py`` attaches a
SYMBOLIC ``BoundsResult`` — ``lower_expression`` / ``upper_expression`` as
strings over observable probabilities. That is the honest "we cannot give a
point, but here is the interval the data alone supports" answer, but until
now it produced only *symbols*: given a DataFrame the layer could not turn
``P(Y=y|X=x)·P(X=x)`` into an actual ``[L, U]``.

This module evaluates the three implemented bounds methods on data:

- :func:`evaluate_manski_natural_bounds` — Manski (1990) natural bounds on
  the single arm ``P(Y=y | do(X=x))``. No assumptions. Always available for
  a binary-eventoutcome effect query.
- :func:`evaluate_manski_tamer_bounds` — Manski (1997) monotone-treatment-
  response tightening of ONE side of the natural interval.
- :func:`evaluate_balke_pearl_ace_bounds` — Balke-Pearl (1997) SHARP bounds
  on the average causal effect ``ACE = P(Y=1|do(X=1)) − P(Y=1|do(X=0))``
  in a binary instrument model, computed by the response-function LINEAR
  PROGRAM over the 16-type canonical partition (the first-principles
  definition of the identified set — the closed-form "max/min of 8 linear
  combinations" is its analytic solution, used to cross-check in tests).

ESTIMAND, stated per method (they bound DIFFERENT quantities — faithfully
mirrored from the symbolic layer):

- Manski natural / Manski-Tamer bound a single interventional arm
  ``P(Y=y | do(X=x))`` (``estimand = "arm_probability"``).
- Balke-Pearl bounds the ACE difference (``estimand = "ace"``).

CONFIDENCE INTERVAL — a declared modelling choice. The reported
``[ci_lower, ci_upper]`` is a non-parametric percentile bootstrap OUTER band
for the identified SET: ``ci_lower`` is the lower-α/2 quantile of the
bootstrapped LOWER endpoint and ``ci_upper`` the upper-α/2 quantile of the
bootstrapped UPPER endpoint. It covers the identified interval with
probability ≥ 1−α (conservative). It is NOT the Imbens-Manski (2004)
confidence interval for the true parameter POINT — that narrower construction
targets a different object; the outer band matches the "here is the honest
interval and its sampling uncertainty" framing of the bounds layer. The
tradeoff: the outer band never under-covers the set but is wider than an
Imbens-Manski point CI when the interval is wide.

Reference: Manski 1990 (natural bounds), Manski 1997 (MTR), Balke & Pearl
1997 JASA / Pearl "Causality" 2nd ed. ch. 8 (IV bounds); the response-
function LP is Balke 1995 (thesis) / Pearl ch. 8.

API::

    from themis.estimation.bounds_numeric import (
        evaluate_manski_natural_bounds, evaluate_balke_pearl_ace_bounds,
    )
    nb = evaluate_balke_pearl_ace_bounds(
        data, treatment="x", outcome="y", instrument="z")
    print(nb.lower_value, nb.upper_value, nb.ci_lower, nb.ci_upper)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import validate_data
from .dose_response import EstimatorFailure
from .resample import cluster_labels, resample_indices


@dataclass(frozen=True)
class NumericBounds:
    """Numeric evaluation of a symbolic ``BoundsResult`` on data."""

    method: str                    # matches BoundsMethod.value
    estimand: str                  # "arm_probability" | "ace"
    lower_value: float
    upper_value: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    width: float
    width_is_trivial: bool
    sample_size: int
    data_hash: str
    treatment: str
    outcome: str
    # Arm-probability methods record the arm + event they bound; the ACE
    # method leaves these None and records the instrument instead.
    treatment_value: object = None
    outcome_value: object = None
    instrument: str | None = None
    assumptions: tuple[str, ...] = ()
    cluster: str | None = None


# The width above which an interval is flagged "uninformative" (essentially
# the whole logically-possible range). Arm probabilities live in [0, 1] and
# the ACE in [-1, 1]; an interval within ``_TRIVIAL_SLACK`` of the full
# range carries no usable information.
_TRIVIAL_SLACK = 1e-9


# ---------------------------------------------------------------------------
# Manski natural bounds — single arm P(Y=y | do(X=x))
# ---------------------------------------------------------------------------


def evaluate_manski_natural_bounds(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    treatment_value=True,
    outcome_value=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> NumericBounds:
    """Manski (1990) natural bounds on ``P(Y=outcome_value | do(X=treatment_value))``.

    ``P(Y=y|do(X=x)) ∈ [ P(Y=y,X=x),  P(Y=y,X=x) + P(X≠x) ]``

    The lower endpoint is the observed joint mass on the treated arm; the
    unobserved ``X≠x`` sub-population contributes anywhere in ``[0, P(X≠x)]``.
    Assumption-free. When nobody has ``X=x`` the interval degenerates to the
    trivial ``[0, 1]`` — honest, but flagged ``width_is_trivial``.
    """
    contract, df, groups = _prepare(
        data, treatment, outcome, cluster=cluster,
    )
    x_series = df[treatment].to_numpy()
    y_series = df[outcome].to_numpy()

    def bounds_from(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
        return _manski_natural_arm(
            xs, ys, treatment_value, outcome_value,
        )

    lower, upper = bounds_from(x_series, y_series)
    ci_lower, ci_upper = _bootstrap_outer_band(
        df, treatment, outcome, bounds_from,
        ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, groups=groups,
    )
    width = upper - lower
    return NumericBounds(
        method="manski_natural",
        estimand="arm_probability",
        lower_value=float(lower),
        upper_value=float(upper),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        width=float(width),
        width_is_trivial=bool(width >= 1.0 - _TRIVIAL_SLACK),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment,
        outcome=outcome,
        treatment_value=_py(treatment_value),
        outcome_value=_py(outcome_value),
        instrument=None,
        assumptions=(),
        cluster=cluster,
    )


def _manski_natural_arm(
    xs: np.ndarray, ys: np.ndarray, x_val, y_val,
) -> tuple[float, float]:
    n = len(xs)
    if n == 0:
        return 0.0, 1.0
    x_eq = _eq(xs, x_val)
    joint = float(((x_eq) & _eq(ys, y_val)).sum()) / n     # P(Y=y, X=x)
    p_other = float((~x_eq).sum()) / n                     # P(X≠x)
    return joint, joint + p_other


# ---------------------------------------------------------------------------
# Manski-Tamer monotone-treatment-response bounds — single arm, one side tight
# ---------------------------------------------------------------------------


def evaluate_manski_tamer_bounds(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    monotonicity: str,               # "non_decreasing" | "non_increasing"
    treatment_value=True,
    outcome_value=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> NumericBounds:
    """Manski (1997) MTR bounds: tighten ONE side of the natural interval to
    the observed outcome marginal ``P(Y=y)`` under a monotone treatment
    response assumption. Strictly contained in the natural interval.

    Which side tightens (mirrors ``output/bounds.py`` exactly):
    MTR ``Y(1) ≥ Y(0)`` (non_decreasing):
      do(X=high): lower → P(Y=y); upper unchanged.
      do(X=low):  upper → P(Y=y); lower unchanged.
    MTR ``Y(1) ≤ Y(0)`` (non_increasing): direction flipped.
    """
    if monotonicity not in ("non_decreasing", "non_increasing"):
        raise EstimatorFailure(
            "invalid_monotonicity",
            f"monotonicity must be 'non_decreasing' or 'non_increasing', "
            f"got {monotonicity!r}",
        )
    contract, df, groups = _prepare(
        data, treatment, outcome, cluster=cluster,
    )
    # Determine which side tightens from the intervention value's polarity.
    treating_high = bool(treatment_value)
    direction_increases_y = monotonicity == "non_decreasing"
    tighten_lower = treating_high == direction_increases_y

    def bounds_from(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
        nat_lo, nat_hi = _manski_natural_arm(xs, ys, treatment_value, outcome_value)
        marginal = float(_eq(ys, outcome_value).sum()) / len(ys) if len(ys) else 0.0
        if tighten_lower:
            return marginal, nat_hi
        return nat_lo, marginal

    lower, upper = bounds_from(df[treatment].to_numpy(), df[outcome].to_numpy())
    ci_lower, ci_upper = _bootstrap_outer_band(
        df, treatment, outcome, bounds_from,
        ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, groups=groups,
    )
    width = upper - lower
    return NumericBounds(
        method="manski_tamer_monotonicity",
        estimand="arm_probability",
        lower_value=float(lower),
        upper_value=float(upper),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        width=float(width),
        width_is_trivial=bool(width >= 1.0 - _TRIVIAL_SLACK),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment,
        outcome=outcome,
        treatment_value=_py(treatment_value),
        outcome_value=_py(outcome_value),
        instrument=None,
        assumptions=(f"mtr_{monotonicity}",),
        cluster=cluster,
    )


# ---------------------------------------------------------------------------
# Balke-Pearl IV bounds — ACE, via the response-function LP
# ---------------------------------------------------------------------------

# X responds to Z; Y responds to X. 4 canonical types each → 16 joint types.
#   X-type i:  0 never (X≡0)   1 complier (X≡Z)   2 defier (X≡1−Z)   3 always (X≡1)
#   Y-type j:  0 (0,0)         1 Y≡X              2 Y≡1−X            3 (1,1)
# where the tuple is (Y at x=0, Y at x=1).
def _fx(i: int, z: int) -> int:
    return (0, z, 1 - z, 1)[i]


def _gy(j: int, x: int) -> int:
    return (0, x, 1 - x, 1)[j]


# ACE contribution per Y-type = g(1) − g(0): [0, 1, −1, 0]
_ACE_COEF = np.array(
    [_gy(j, 1) - _gy(j, 0) for i in range(4) for j in range(4)], dtype=float
)


def _bp_ace_bounds_from_P(P: np.ndarray) -> tuple[float, float]:
    """Sharp ACE bounds by LP over the 16-type simplex. ``P`` is a
    (2,2,2) array ``P[z,x,y] = P(X=x, Y=y | Z=z)``."""
    from scipy.optimize import linprog

    rows: list[np.ndarray] = []
    b: list[float] = []
    for z in (0, 1):
        for x in (0, 1):
            for y in (0, 1):
                row = np.zeros(16)
                for i in range(4):
                    for j in range(4):
                        if _fx(i, z) == x and _gy(j, _fx(i, z)) == y:
                            row[i * 4 + j] = 1.0
                rows.append(row)
                b.append(float(P[z, x, y]))
    rows.append(np.ones(16))
    b.append(1.0)
    A_eq = np.asarray(rows)
    b_eq = np.asarray(b)
    simplex = [(0.0, None)] * 16
    lo = linprog(_ACE_COEF, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    hi = linprog(-_ACE_COEF, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    if not (lo.success and hi.success):
        # No type distribution reproduces the observed table under IV
        # independence + exclusion — i.e. the data REFUTES the instrument.
        # Translate the LP infeasibility into Balke-Pearl's own falsifiability
        # test (the instrumental inequalities, eq 6) so the message is causal,
        # not numeric.
        violation = _instrumental_inequality_violation(P)
        raise EstimatorFailure(
            "iv_model_refuted",
            "the observed P(X,Y|Z) table is incompatible with the binary IV "
            "model: no distribution over response types reproduces it under "
            "instrument independence + exclusion. "
            + (violation or "The response-function LP is infeasible.")
            + " Either the instrument is invalid (IV1/IV2/IV3 fail) or, on a "
            "small sample, this is sampling noise near the model boundary.",
        )
    return float(lo.fun), float(-hi.fun)


# Balke-Pearl (1997) eq (6) — the instrumental inequalities. The binary IV
# model is REFUTED (no compatible latent distribution exists) iff any of these
# is violated. p_{yx.z} = P(Y=y, X=x | Z=z) = P[z, x, y] in this module's array.
def _instrumental_inequality_violation(P: np.ndarray) -> str | None:
    checks = (
        ("P(Y=0,X=0|Z=0)+P(Y=1,X=0|Z=1)", P[0, 0, 0] + P[1, 0, 1]),
        ("P(Y=0,X=1|Z=0)+P(Y=1,X=1|Z=1)", P[0, 1, 0] + P[1, 1, 1]),
        ("P(Y=1,X=0|Z=0)+P(Y=0,X=0|Z=1)", P[0, 0, 1] + P[1, 0, 0]),
        ("P(Y=1,X=1|Z=0)+P(Y=0,X=1|Z=1)", P[0, 1, 1] + P[1, 1, 0]),
    )
    worst = max(checks, key=lambda c: c[1])
    if worst[1] > 1.0 + 1e-9:
        return (
            f"Instrumental inequality violated: {worst[0]} = {worst[1]:.4f} "
            f"> 1 (Balke-Pearl 1997 eq 6)."
        )
    return None


def evaluate_balke_pearl_ace_bounds(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    instrument: str,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> NumericBounds:
    """Balke-Pearl (1997) sharp bounds on ``ACE = P(Y=1|do(X=1)) −
    P(Y=1|do(X=0))`` for a binary instrument ``Z``, binary treatment ``X``,
    binary outcome ``Y`` satisfying IV1/IV2/IV3.

    Computed by the response-function LP over the 16 canonical types — the
    definition of the identified set. Tighter than Manski natural whenever a
    valid instrument exists.

    Raises ``EstimatorFailure`` when X / Y / Z is non-binary, or a stratum of
    the instrument has no support (an empty ``Z=z`` cell — the conditional
    ``P(X,Y|Z=z)`` is undefined and the bounds cannot be evaluated there).
    """
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data,
        required_columns={treatment, outcome, instrument},
        presence_columns=presence,
    )
    df = contract.data

    for col, role in ((treatment, "treatment"), (outcome, "outcome"),
                      (instrument, "instrument")):
        levels = _sorted_levels(df[col])
        if len(levels) != 2:
            raise EstimatorFailure(
                f"{role}_not_binary",
                f"{role} {col!r} has {len(levels)} observed levels "
                f"({levels}); the Balke-Pearl IV bounds require a binary "
                f"{role}.",
            )

    x_levels = _sorted_levels(df[treatment])
    y_levels = _sorted_levels(df[outcome])
    z_levels = _sorted_levels(df[instrument])

    def bounds_from_frame(sub: pd.DataFrame) -> tuple[float, float]:
        P = _empirical_P_xyz(
            sub, treatment, outcome, instrument,
            x_levels, y_levels, z_levels,
        )
        return _bp_ace_bounds_from_P(P)

    lower, upper = bounds_from_frame(df)
    ci_lower, ci_upper = _bootstrap_outer_band_frame(
        df, bounds_from_frame,
        ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, groups=groups,
    )
    width = upper - lower
    return NumericBounds(
        method="balke_pearl_iv",
        estimand="ace",
        lower_value=float(lower),
        upper_value=float(upper),
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        width=float(width),
        # ACE lives in [−1, 1]; trivial when the interval spans (nearly) all.
        width_is_trivial=bool(width >= 2.0 - _TRIVIAL_SLACK),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        treatment=treatment,
        outcome=outcome,
        treatment_value=None,
        outcome_value=None,
        instrument=instrument,
        assumptions=(
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ),
        cluster=cluster,
    )


def _empirical_P_xyz(
    df: pd.DataFrame, treatment: str, outcome: str, instrument: str,
    x_levels, y_levels, z_levels,
) -> np.ndarray:
    """Empirical ``P(X=x, Y=y | Z=z)`` as a (2,2,2) array indexed by the
    SORTED level positions (low=0, high=1). An empty ``Z=z`` stratum is a
    positivity violation and raises rather than fabricating."""
    xs = df[treatment].to_numpy()
    ys = df[outcome].to_numpy()
    zs = df[instrument].to_numpy()
    P = np.zeros((2, 2, 2))
    for zi, zv in enumerate(z_levels):
        zmask = zs == zv
        nz = int(zmask.sum())
        if nz == 0:
            raise EstimatorFailure(
                "insufficient_support",
                f"positivity violation: instrument stratum {instrument}={zv!r} "
                "has no observations, so P(X,Y | Z) is undefined there and "
                "the Balke-Pearl bounds cannot be evaluated.",
            )
        for xi, xv in enumerate(x_levels):
            for yi, yv in enumerate(y_levels):
                cnt = int((zmask & (xs == xv) & (ys == yv)).sum())
                P[zi, xi, yi] = cnt / nz
    return P


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _prepare(data, treatment, outcome, *, cluster):
    """Validate the (treatment, outcome) contract and return
    (contract, normalised df, cluster groups | None)."""
    presence = (cluster,) if cluster is not None else ()
    groups = (
        cluster_labels(data, cluster, expected_n=len(data))
        if cluster is not None
        else None
    )
    contract = validate_data(
        data,
        required_columns={treatment, outcome},
        presence_columns=presence,
    )
    return contract, contract.data, groups


def _eq(arr: np.ndarray, value) -> np.ndarray:
    """Elementwise equality that treats bool arrays and 0/1 encodings the
    same (contract coerces bool columns to bool; a caller may pass True or
    1 as the value)."""
    if isinstance(value, bool):
        return arr.astype(bool) == value
    return arr == value


def _sorted_levels(series: pd.Series) -> list:
    vals = pd.unique(series.dropna())
    try:
        return sorted(vals.tolist())
    except TypeError:
        return sorted(vals.tolist(), key=str)


def _py(v):
    if isinstance(v, np.generic):
        return v.item()
    return v


def _bootstrap_outer_band(
    df: pd.DataFrame, treatment: str, outcome: str,
    bounds_from,
    *, ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[float | None, float | None]:
    """Percentile-bootstrap OUTER band for an arm-probability method whose
    ``bounds_from(xs, ys)`` returns (lower, upper) from two arrays."""
    if ci_bootstrap <= 0:
        return None, None
    rng = np.random.default_rng(random_state)
    n = len(df)
    xs_all = df[treatment].to_numpy()
    ys_all = df[outcome].to_numpy()
    lowers: list[float] = []
    uppers: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        lo, hi = bounds_from(xs_all[idx], ys_all[idx])
        lowers.append(lo)
        uppers.append(hi)
    return _outer_quantiles(lowers, uppers, ci_level)


def _bootstrap_outer_band_frame(
    df: pd.DataFrame, bounds_from_frame,
    *, ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[float | None, float | None]:
    """Percentile-bootstrap OUTER band for a method that needs the whole
    frame per replicate (Balke-Pearl reads three columns). A replicate that
    hits a positivity failure (an empty instrument stratum on that draw) is
    skipped — the band is over the evaluable draws."""
    if ci_bootstrap <= 0:
        return None, None
    rng = np.random.default_rng(random_state)
    n = len(df)
    lowers: list[float] = []
    uppers: list[float] = []
    for _ in range(ci_bootstrap):
        idx = resample_indices(n, rng, groups=groups)
        try:
            lo, hi = bounds_from_frame(df.iloc[idx])
        except EstimatorFailure:
            continue
        lowers.append(lo)
        uppers.append(hi)
    if len(lowers) < 2:
        return None, None
    return _outer_quantiles(lowers, uppers, ci_level)


def _outer_quantiles(
    lowers: list[float], uppers: list[float], ci_level: float,
) -> tuple[float, float]:
    alpha = (1.0 - ci_level) / 2.0
    lo_band = float(np.quantile(np.asarray(lowers), alpha))
    hi_band = float(np.quantile(np.asarray(uppers), 1.0 - alpha))
    return lo_band, hi_band
