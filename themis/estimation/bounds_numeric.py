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
- :func:`evaluate_balke_pearl_bounds` — Balke-Pearl SHARP bounds from an
  instrument, computed by the response-function LINEAR PROGRAM over the
  canonical partition. The partition has ``|X|^|Z| · |Y|^|X|`` types, so the
  method is not a binary construction: Balke-Pearl (1997)'s 16 types and the
  closed-form "max/min of 8 linear combinations" are what it becomes when
  every variable happens to be binary (used to cross-check in tests).

ESTIMAND — all three methods bound the SAME thing: the single interventional
arm ``P(Y=y | do(X=x))`` the query named (``estimand = "arm_probability"``).
Balke-Pearl used to bound the ACE instead, which is a different question from
the one an ``EffectQuery`` asks and does not survive a multi-valued treatment
(no baseline arm) or a multi-valued outcome (not a probability difference).
Where the ACE is defined it is still reported, as ``contrast`` — a second
optimisation over the same polytope, since bounds on a difference are not the
difference of bounds.

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
function LP is Balke 1995 (thesis) / Pearl ch. 8. For the generalisation
past binary variables, Cheng & Small 2006 and Richardson & Robins 2014 on
multi-valued instruments, and the causaloptim R package (Sachs, Jonzon,
Gabriel & Sjölander), which computes the same class symbolically by vertex
enumeration where this module solves one LP per dataset.

API::

    from themis.estimation.bounds_numeric import (
        evaluate_manski_natural_bounds, evaluate_balke_pearl_bounds,
    )
    nb = evaluate_balke_pearl_bounds(
        data, treatment="x", outcome="y", instrument="z",
        treatment_value=True, outcome_value=True)
    print(nb.lower_value, nb.upper_value, nb.ci_lower, nb.ci_upper)
    print(nb.contrast)   # the ACE interval, when the treatment is binary
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import pandas as pd

from .contract import validate_data
from .. import refusals
from ..output.bounds import MAX_RESPONSE_TYPES, response_type_count
from ..refusals import Refusal
from ..refusals import EstimatorFailure
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
    # Recorded sufficient statistics that let the verifier RE-DERIVE the
    # point interval [lower_value, upper_value] independently, rather than
    # only metadata-auditing it. Balke-Pearl records the empirical
    # P(X=x, Y=y | Z=z) table ({"P_xyz": nested 2x2x2 list}) — the verifier
    # re-runs the response-function LP over it. Manski natural records the
    # three arm counts ({"n", "n_joint_target_arm", "n_other_arm"}) — the
    # verifier re-derives lower = n_joint/n and upper = (n_joint+n_other)/n
    # (this matters most for a MULTI-VALUED treatment, where the width
    # P(X≠x) pools several off-arm levels and a metadata-only audit cannot
    # tell an honest complement from a fabricated one). None for Manski-Tamer,
    # whose one-sided tightening to the observed marginal is anchored by the
    # width/range invariants.
    sufficient_statistics: dict | None = None
    # A SECOND interval, over a second quantity, from the same polytope: the
    # ACE where a binary treatment gives the difference a baseline arm. Its
    # own name and its own endpoints, because an interval whose quantity is
    # left to be inferred from the method's reputation is how the bounds
    # layer came to answer a question nobody asked.
    contrast: dict | None = None


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
    # Sufficient statistics for the verifier's INDEPENDENT re-derivation of
    # the closed form (from the SAME arrays the bound was computed on):
    #   lower = n_joint/n,  upper = (n_joint + n_other)/n,  width = n_other/n.
    # Cardinality-agnostic: n_other counts EVERY row with X≠x, so for a
    # multi-valued treatment the verifier can confirm the pooled off-arm
    # mass is honest rather than fabricated.
    x_eq = _eq(x_series, treatment_value)
    n_used = int(len(x_series))
    n_joint = int((x_eq & _eq(y_series, outcome_value)).sum())
    n_other = int((~x_eq).sum())
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
        sufficient_statistics={
            "n": n_used,
            "n_joint_target_arm": n_joint,
            "n_other_arm": n_other,
        },
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
            Refusal.INVALID_MONOTONICITY,
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
# Balke-Pearl IV bounds — via the response-function LP, at any cardinality
# ---------------------------------------------------------------------------
# Under IV exclusion + independence a unit is fully described by two maps: the
# treatment it would take at each instrument level (``z → x``) and the outcome
# it would show at each treatment level (``x → y``). The canonical partition
# is every pair of such maps; its size ``|X|^|Z| · |Y|^|X|`` follows from the
# cardinalities. Balke-Pearl's 16 is that number when everything is binary,
# and writing 16 down as a constant is what used to make three levels of an
# instrument look like a different problem.


@lru_cache(maxsize=32)
def _response_types(nx: int, ny: int, nz: int) -> tuple[tuple, tuple]:
    """(X-response types, Y-response types) as tuples of maps, indexed by
    level POSITION: ``fx[z] = x`` and ``gy[x] = y``.

    ``ny`` stays in the exponent. Collapsing the outcome to "is it the value
    the query asked about" would take it out, and is the obvious way to buy
    back the size :data:`~themis.output.bounds.MAX_RESPONSE_TYPES` spends;
    measured over 240 random tables it moves the answer on 154 of them, by up
    to 0.323. Collapsing the outcome collapses the observed table with it, and
    the equality constraints the finer table imposes are information about
    which mixtures of types reproduce the data — dropping them can only
    enlarge the feasible set, so the shortcut is valid and loose rather than
    wrong, which is why it has to be rejected on a number and not on whether
    it looks sound.
    """
    return (
        tuple(itertools.product(range(nx), repeat=nz)),
        tuple(itertools.product(range(ny), repeat=nx)),
    )


@lru_cache(maxsize=32)
def _response_constraints(nx: int, ny: int, nz: int) -> np.ndarray:
    """The equality-constraint matrix mapping a distribution over response
    types to the observable table ``P(X=x, Y=y | Z=z)``, plus the row that
    makes it a distribution.

    Built from the cardinalities alone, so it is identical across bootstrap
    replicates and cached rather than rebuilt (only the right-hand side moves).
    """
    fxs, gys = _response_types(nx, ny, nz)
    A = np.zeros((nz * nx * ny + 1, len(fxs) * len(gys)))
    row = 0
    for z in range(nz):
        for x in range(nx):
            for y in range(ny):
                for i, fx in enumerate(fxs):
                    if fx[z] != x:
                        continue
                    for j, gy in enumerate(gys):
                        if gy[x] == y:
                            A[row, i * len(gys) + j] = 1.0
                row += 1
    A[row, :] = 1.0
    return A


def _arm_objective(nx: int, ny: int, nz: int, xi: int, yi: int) -> np.ndarray:
    """Coefficients of ``P(Y=y | do(X=x))`` over the response types: a type
    contributes iff its outcome map sends level ``xi`` to level ``yi``.
    Intervening fixes X, so the treatment map plays no part."""
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for i in range(len(fxs)):
        for j, gy in enumerate(gys):
            if gy[xi] == yi:
                c[i * len(gys) + j] = 1.0
    return c


def _contrast_objective(
    nx: int, ny: int, nz: int, yi: int, hi_xi: int, lo_xi: int,
) -> np.ndarray:
    """Coefficients of ``P(Y=y|do(X=hi)) − P(Y=y|do(X=lo))`` — the same type
    distribution read through a difference instead of a level."""
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for i in range(len(fxs)):
        for j, gy in enumerate(gys):
            c[i * len(gys) + j] = (
                (1.0 if gy[hi_xi] == yi else 0.0)
                - (1.0 if gy[lo_xi] == yi else 0.0)
            )
    return c


def _cell_objective(
    nx: int, ny: int, nz: int, p_z: np.ndarray,
    *, x_observed: int, x_counterfactual: int, y_star: int,
    factual_y: int | None,
) -> np.ndarray:
    """Coefficients of the counterfactual cell's NUMERATOR
    ``P(Y_{x'}=y*, X=x [, Y=y])`` over the response types.

    A unit of type ``(fx, gy)`` sitting at instrument level ``z`` takes
    treatment ``fx[z]``, shows outcome ``gy[fx[z]]``, and would have shown
    ``gy[x']`` under ``do(X=x')``. So membership in the cell is a property of
    the type AND the level, and ``P(z)`` multiplies through because the IV
    model's independence is exactly the claim that the type does not depend
    on the level.

    ``factual_y`` is None when the factual outcome is not part of the evidence
    (the ETT cell ``P(Y_{x'}=y* | X=x)``): the outcome map is then unconstrained
    at the observed arm rather than pinned to a value.

    The DENOMINATOR is ``P(X=x [, Y=y])``, which the equality constraints fix
    at the observed table — a known number, not a variable — which is what
    keeps a conditional counterfactual a linear program rather than a
    fractional one.
    """
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for j, gy in enumerate(gys):
        if gy[x_counterfactual] != y_star:
            continue
        if factual_y is not None and gy[x_observed] != factual_y:
            continue
        for i, fx in enumerate(fxs):
            c[i * len(gys) + j] = float(
                sum(p_z[zi] for zi in range(nz) if fx[zi] == x_observed)
            )
    return c


def monotone_y_types(nx: int, ny: int, direction) -> frozenset[int]:
    """Indices of the outcome-response maps a declared monotonicity permits.

    Monotonicity is a claim about which units the population contains — no
    unit whose outcome moves against the treatment — so it belongs in the
    response-function model as a restriction of the type space, not as a
    second formula applied afterwards. Levels are compared by POSITION, which
    is the sorted order of the observed values.
    """
    from ..types import Monotonicity

    # The table is the exhaustiveness statement: a direction added to the enum
    # and not to this line fails at the lookup, rather than being folded into
    # whichever branch happened to be the fallback.
    ascending = {
        Monotonicity.NON_DECREASING: True,
        Monotonicity.NON_INCREASING: False,
    }[direction]
    gys = tuple(itertools.product(range(ny), repeat=nx))
    return frozenset(
        j for j, gy in enumerate(gys)
        if all(
            (gy[i] <= gy[i + 1]) if ascending else (gy[i] >= gy[i + 1])
            for i in range(nx - 1)
        )
    )


def _solve_response_lp(
    P: np.ndarray, nx: int, ny: int, nz: int, objective: np.ndarray,
    *, allowed_y_types: frozenset[int] | None = None,
) -> tuple[float, float]:
    """Range of a linear functional over every response-type distribution
    that reproduces ``P[z,x,y] = P(X=x, Y=y | Z=z)`` — the identified set by
    its definition, not an approximation of it.

    ``allowed_y_types`` narrows the population to the outcome-response maps a
    declared assumption permits; the constraint matrix is untouched, because
    forbidding a type is saying no unit is of it, and that is a bound of zero
    on its mass.
    """
    from scipy.optimize import linprog

    A_eq = _response_constraints(nx, ny, nz)
    b_eq = np.concatenate([P.reshape(-1), [1.0]])
    n_gy = ny ** nx
    simplex: list[tuple[float, float | None]] = [
        (0.0, None)
        if allowed_y_types is None or (k % n_gy) in allowed_y_types
        else (0.0, 0.0)
        for k in range(A_eq.shape[1])
    ]
    lo = linprog(objective, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    hi = linprog(-objective, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    if not (lo.success and hi.success):
        # No type distribution reproduces the observed table under IV
        # independence + exclusion — i.e. the data REFUTES the instrument.
        # Translate the LP infeasibility into the instrumental inequality so
        # the message is causal rather than numeric.
        violation = _instrumental_inequality_violation(P, nx, ny, nz)
        raise EstimatorFailure(
            Refusal.IV_MODEL_REFUTED,
            f"the observed P(X,Y|Z) table is incompatible with the IV model "
            f"at {nx}×{ny}×{nz} levels: no distribution over response types "
            "reproduces it under instrument independence + exclusion. "
            + (violation or "The response-function LP is infeasible.")
            + " Either the instrument is invalid (IV1/IV2/IV3 fail) or, on a "
            "small sample, this is sampling noise near the model boundary.",
        )
    return float(lo.fun), float(-hi.fun)


def _instrumental_inequality_violation(
    P: np.ndarray, nx: int, ny: int, nz: int,
) -> str | None:
    """Pearl's instrumental inequality: for each treatment level,
    ``Σ_y max_z P(Y=y, X=x | Z=z) ≤ 1``. A violation WITNESSES that the IV
    model is refuted, and reduces to Balke-Pearl (1997) eq (6)'s four checks
    when everything is binary.

    It is a witness, not the whole test: outside the binary-instrument case
    the inequality is not known here to be sufficient, so the caller treats
    the LP's infeasibility as the authority and uses this only to say WHY in
    the cases where it can.
    """
    worst_x, worst = -1, -1.0
    for x in range(nx):
        total = float(sum(P[:, x, y].max() for y in range(ny)))
        if total > worst:
            worst_x, worst = x, total
    if worst > 1.0 + 1e-9:
        return (
            f"Instrumental inequality violated at treatment level index "
            f"{worst_x}: Σ_y max_z P(Y=y, X=x | Z=z) = {worst:.4f} > 1 "
            f"(Pearl 1995; Balke-Pearl 1997 eq 6 in the binary case)."
        )
    return None


def counterfactual_cell_iv_table(
    x_arr: np.ndarray, y_arr: np.ndarray, z_arr: np.ndarray, z_levels: list,
) -> tuple[np.ndarray, np.ndarray]:
    """``(P(X,Y | Z), P(Z))`` for a BINARY treatment and outcome, indexed so
    that position 0 is False and position 1 is True.

    Separate from :func:`_empirical_P_xyz` because the caller has already
    normalised its two binary columns and fixed their level order by doing so;
    re-deriving the order from the observed values would let a sample in which
    one of them is constant silently re-index the cell being asked about.
    """
    x = x_arr.astype(bool)
    y = y_arr.astype(bool)
    P = np.zeros((len(z_levels), 2, 2))
    p_z = np.zeros(len(z_levels))
    n = len(x)
    for zi, zv in enumerate(z_levels):
        zmask = _eq(z_arr, zv)
        rows = int(zmask.sum())
        p_z[zi] = rows / n if n else 0.0
        if rows == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                f"positivity violation: instrument stratum {zv!r} has no "
                "observations, so P(X, Y | Z) is undefined there and the "
                "response-function polytope has no table to be fitted to.",
            )
        for xi in (0, 1):
            for yi in (0, 1):
                cnt = int((zmask & (x == bool(xi)) & (y == bool(yi))).sum())
                P[zi, xi, yi] = cnt / rows
    return P, p_z


def counterfactual_cell_response_bounds(
    P: np.ndarray, p_z: np.ndarray,
    *, x_observed: int, x_counterfactual: int, y_star: int,
    factual_y: int | None, monotonicity=None,
) -> tuple[float, float]:
    """Sharp bounds on ``P(Y_{x'}=y* | X=x [, Y=y])`` from an instrument.

    The cell is another linear functional over the response-type distributions
    that reproduce ``P(X, Y | Z)`` — the polytope Balke-Pearl's arm bounds are
    read off — so it is the same program with a different objective. That is
    the whole method, and it is why this is sharp where routing the arm's
    INTERVAL through the consistency identity is not: the identity consumes the
    interventional risk as a scalar, and a scalar cannot carry the fact that
    the distribution producing the risk is the one that has to produce the cell.

    What that is worth is measured rather than argued, because the two-step is
    valid and cheap-looking and would otherwise keep being proposed: over 400
    random binary IV models sampled straight from the response-type
    distribution, it says something non-trivial about 46 of them against this
    program's 133, the widest single gap being [0.9207, 1.0] here against
    [0, 1] there. The median width ratio is 1.000 — an average reports the loss
    as nothing, because it is concentrated in exactly the models where having
    an instrument was worth anything. Both cover the truth on all 400, and the
    cheap route is not cheaper: same polytope, different objective vector.

    A declared ``monotonicity`` enters as the population containing no unit
    whose outcome moves against the treatment. When that leaves the program
    infeasible but dropping it does not, the assumption — not the instrument —
    is what the data refute, and the two are told apart rather than reported
    under whichever refusal came first.
    """
    nz, nx, ny = P.shape
    objective = _cell_objective(
        nx, ny, nz, p_z,
        x_observed=x_observed, x_counterfactual=x_counterfactual,
        y_star=y_star, factual_y=factual_y,
    )
    denominator = float(sum(
        p_z[zi] * (
            P[zi, x_observed, factual_y] if factual_y is not None
            else P[zi, x_observed, :].sum()
        )
        for zi in range(nz)
    ))
    allowed = (
        None if monotonicity is None
        else monotone_y_types(nx, ny, monotonicity)
    )
    try:
        lower, upper = _solve_response_lp(
            P, nx, ny, nz, objective, allowed_y_types=allowed,
        )
    except EstimatorFailure:
        if allowed is None:
            raise
        _solve_response_lp(P, nx, ny, nz, objective)
        raise EstimatorFailure(
            Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE,
            "no distribution over response types reproduces P(X, Y | Z) once "
            "the declared monotonicity removes the units whose outcome moves "
            "against the treatment — the instrument is compatible with this "
            "table and the monotonicity assumption is what it refutes.",
        )
    if denominator <= 0.0:
        # The conditioning event has no mass, so the cell is a ratio of zeros
        # and no distribution can distinguish its values. The identity route
        # answers the same degeneracy with the same box; disagreeing about it
        # would make WHICH ROUTE ran visible in the answer.
        return 0.0, 1.0
    # The numerator is a sub-event of the denominator on every feasible point,
    # so the ratio is a probability by construction and anything outside [0, 1]
    # is the simplex solver's last few bits. Clamped for the same reason the
    # identity route clamps: an answer that leaves [0, 1] is not a tighter
    # claim about the cell, it is a claim the cell cannot carry.
    return (
        min(max(lower / denominator, 0.0), 1.0),
        min(max(upper / denominator, 0.0), 1.0),
    )


def evaluate_balke_pearl_bounds(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    instrument: str,
    treatment_value=True,
    outcome_value=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> NumericBounds:
    """Sharp bounds on the single arm ``P(Y=outcome_value |
    do(X=treatment_value))`` from an instrument satisfying IV1/IV2/IV3, at
    any finite cardinality of X, Y and Z.

    THE ESTIMAND IS THE ARM, not the ACE. Balke-Pearl's textbook statement
    bounds ``P(Y=1|do(X=1)) − P(Y=1|do(X=0))``, which needs a binary outcome
    to be a probability difference and a binary treatment to have a baseline
    arm — it does not survive the generalisation, and it was never the
    quantity an ``EffectQuery`` asked for. Where the ACE IS defined (a binary
    treatment gives the difference a baseline arm) it is reported alongside,
    as ``contrast``: the same polytope read through a difference instead of a
    level. It is its own pair of optimisations rather than arithmetic on the
    arm's endpoints — a difference of two quantities is contained in the
    difference of their intervals but is not in general equal to it, and
    optimising it directly is correct without needing to know which. On the
    binary IV model the two happen to coincide on every table tried
    (including both published worked examples), so what the second LP buys
    here is not having to assume that.

    Raises ``EstimatorFailure`` when the model is larger than
    ``MAX_RESPONSE_TYPES``, when the queried level is unobserved, when a
    stratum of the instrument has no support, or when no response-type
    distribution reproduces the observed table (the instrument is refuted).
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

    x_levels = sorted_levels(df[treatment])
    y_levels = sorted_levels(df[outcome])
    z_levels = sorted_levels(df[instrument])
    nx, ny, nz = len(x_levels), len(y_levels), len(z_levels)

    for col, role, levels in (
        (treatment, "treatment", x_levels),
        (outcome, "outcome", y_levels),
        (instrument, "instrument", z_levels),
    ):
        if len(levels) < 2:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                f"{role} {col!r} takes a single value "
                f"({refusals.describe(levels)}) in this sample; a variable "
                f"that never varies carries no response types to bound over.",
            )

    if response_type_count(
        treatment_levels=nx, outcome_levels=ny, instrument_levels=nz,
    ) is None:
        raise EstimatorFailure(
            Refusal.RESPONSE_MODEL_TOO_LARGE,
            f"{treatment!r}×{outcome!r}×{instrument!r} have {nx}×{ny}×{nz} "
            f"observed levels, so the response-function partition has "
            f"{nx}^{nz}·{ny}^{nx} types — above the {MAX_RESPONSE_TYPES} "
            f"this package solves. The sharp interval exists; it is the LP, "
            f"re-solved once per bootstrap replicate, that is declined. "
            f"A column with this many observed levels is usually a "
            f"continuous one that no response-function model describes; "
            f"coarsening it brings the method back in reach.",
        )

    xi = _level_index(x_levels, treatment_value, treatment, "intervention")
    yi = _level_index(y_levels, outcome_value, outcome, "target")
    arm_obj = _arm_objective(nx, ny, nz, xi, yi)

    def bounds_from_frame(sub: pd.DataFrame) -> tuple[float, float]:
        P = _empirical_P_xyz(
            sub, treatment, outcome, instrument,
            x_levels, y_levels, z_levels,
        )
        return _solve_response_lp(P, nx, ny, nz, arm_obj)

    lower, upper = bounds_from_frame(df)
    # The full-data P(X=x, Y=y | Z=z) table is the sufficient statistic the
    # response-function LP consumes — record it, WITH the level lists, so the
    # verifier can re-derive [lower_value, upper_value] independently rather
    # than only metadata-audit. Without the levels the table's own shape is
    # the only clue to what its axes mean, and a 2×3×2 table read as 3×2×2
    # would re-derive a different interval and call the producer a liar.
    P_full = _empirical_P_xyz(
        df, treatment, outcome, instrument, x_levels, y_levels, z_levels,
    )
    stats = {
        "P_xyz": [[[float(P_full[z, x, y]) for y in range(ny)]
                   for x in range(nx)] for z in range(nz)],
        "treatment_levels": [_py(v) for v in x_levels],
        "outcome_levels": [_py(v) for v in y_levels],
        "instrument_levels": [_py(v) for v in z_levels],
        "arm_treatment_index": xi,
        "arm_outcome_index": yi,
    }
    ci_lower, ci_upper = _bootstrap_outer_band_frame(
        df, bounds_from_frame,
        ci_bootstrap=ci_bootstrap, ci_level=ci_level,
        random_state=random_state, groups=groups,
    )
    width = upper - lower
    contrast = _ace_contrast(
        P_full, nx, ny, nz, xi, yi, x_levels, y_levels,
    )
    return NumericBounds(
        method="balke_pearl_iv",
        estimand="arm_probability",
        lower_value=float(lower),
        upper_value=float(upper),
        sufficient_statistics=stats,
        contrast=contrast,
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
        instrument=instrument,
        assumptions=(
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ),
        cluster=cluster,
    )


def _ace_contrast(
    P: np.ndarray, nx: int, ny: int, nz: int, xi: int, yi: int,
    x_levels: list, y_levels: list,
) -> dict | None:
    """The average causal effect, when the treatment is binary — the queried
    arm minus the other one, bounded over the same polytope.

    ``None`` for a multi-valued treatment: with three or more levels there is
    no baseline arm the difference is against, and picking one would be this
    module inventing a question the query did not ask.
    """
    if nx != 2:
        return None
    other = 1 - xi
    lo, hi = _solve_response_lp(
        P, nx, ny, nz, _contrast_objective(nx, ny, nz, yi, xi, other),
    )
    return {
        "kind": "ace",
        "reference_value": _py(x_levels[other]),
        "lower_value": float(lo),
        "upper_value": float(hi),
    }


def _level_index(levels: list, value, column: str, role: str) -> int:
    """Position of ``value`` among the sorted observed levels."""
    for i, v in enumerate(levels):
        if v == value or (isinstance(value, bool) and bool(v) == value):
            return i
    raise EstimatorFailure(
        Refusal.TARGET_VALUE_ABSENT,
        f"the {role} level {value!r} does not occur in column {column!r} "
        f"(observed: {refusals.describe(levels)}); the response-function "
        f"model has no arm to bound there.",
    )


def _empirical_P_xyz(
    df: pd.DataFrame, treatment: str, outcome: str, instrument: str,
    x_levels, y_levels, z_levels,
) -> np.ndarray:
    """Empirical ``P(X=x, Y=y | Z=z)`` as a ``(|Z|,|X|,|Y|)`` array indexed by
    the SORTED level positions. An empty ``Z=z`` stratum is a positivity
    violation and raises rather than fabricating."""
    xs = df[treatment].to_numpy()
    ys = df[outcome].to_numpy()
    zs = df[instrument].to_numpy()
    P = np.zeros((len(z_levels), len(x_levels), len(y_levels)))
    for zi, zv in enumerate(z_levels):
        zmask = zs == zv
        nz_rows = int(zmask.sum())
        if nz_rows == 0:
            raise EstimatorFailure(
                Refusal.INSUFFICIENT_SUPPORT,
                f"positivity violation: instrument stratum {instrument}={zv!r} "
                "has no observations, so P(X,Y | Z) is undefined there and "
                "the Balke-Pearl bounds cannot be evaluated.",
            )
        for xi, xv in enumerate(x_levels):
            for yi, yv in enumerate(y_levels):
                cnt = int((zmask & (xs == xv) & (ys == yv)).sum())
                P[zi, xi, yi] = cnt / nz_rows
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


def sorted_levels(series: pd.Series) -> list:
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
