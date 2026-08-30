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

The linear program itself is :mod:`themis.response_polytope`, not this
module. It consumes ``P(X, Y | Z)`` and ``P(Z)`` as arrays and is indifferent
to where they came from; what belongs here is the reduction from a DataFrame
to those two arrays, and the bootstrap around it. The parameter end reduces
``theta`` to the same two arrays and solves the same program.

ESTIMAND — all three methods bound the SAME thing: the single interventional
arm ``P(Y=y | do(X=x))`` the query named (``estimand = "arm_probability"``).
Balke-Pearl used to bound the ACE instead, which is a different question from
the one an ``EffectQuery`` asks and does not survive a multi-valued treatment
(no baseline arm) or a multi-valued outcome (not a probability difference).

An arm is a narrower question than the one an ``effect`` query puts, though:
that query asks for a CONTRAST, and a row bracketing an arm has not answered
it. So where the contrast is defined it travels beside the arm, in
``contrast``, with its own name and its own endpoints. How it is obtained is
not the same on the two methods that report one, and the difference is not a
detail: Balke-Pearl runs a SECOND optimisation over the same polytope,
because a response-type model constrains the two arms together and bounds on
a difference are then not the difference of bounds; Manski natural assumes
nothing, so the two arms' unobserved masses are disjoint sub-populations
under no joint constraint and the difference of the intervals IS the interval
of the difference. Manski-Tamer reports none — see
:func:`evaluate_manski_tamer_bounds`.

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

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .contract import validate_data
from ..types import envelope_scalar
from .. import refusals
from ..output.bounds import MAX_RESPONSE_TYPES, response_type_count
from ..refusals import Refusal
from ..refusals import EstimatorFailure
from ..response_polytope import (
    _arm_objective,
    _contrast_objective,
    _solve_response_lp,
)
from .resample import Draws, cluster_labels, resample_indices


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
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    # Arm-probability methods record the arm + event they bound; the ACE
    # method leaves these None and records the instrument instead.
    treatment_value: object = None
    outcome_value: object = None
    instrument: str | None = None
    assumptions: tuple[str, ...] = ()
    cluster: str | None = None
    #: The replicates the outer band was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    # Recorded sufficient statistics that let the verifier RE-DERIVE the
    # point interval [lower_value, upper_value] independently, rather than
    # only metadata-auditing it. Balke-Pearl records the empirical
    # P(X=x, Y=y | Z=z) table ({"P_xyz": nested 2x2x2 list}) — the verifier
    # re-runs the response-function LP over it. Manski natural records the
    # three arm counts ({"n", "n_joint_target_arm", "n_other_arm"}) — the
    # verifier re-derives lower = n_joint/n and upper = (n_joint+n_other)/n
    # (this matters most for a MULTI-VALUED treatment, where the width
    # P(X≠x) pools several off-arm levels and a metadata-only audit cannot
    # tell an honest complement from a fabricated one), and its
    # ``n_joint_other_arm`` is what makes the contrast re-derivable from the
    # same counts; Manski-Tamer records the whole ``(X, Y)`` table instead,
    # because its bound is about where the target event sits in the outcome's
    # ORDER and no fixed set of scalars carries that.
    sufficient_statistics: dict | None = None
    # A SECOND interval, over a second quantity: the ACE, where a single other
    # arm gives the difference a baseline. Its own name and its own endpoints,
    # because an interval whose quantity is left to be inferred from the
    # method's reputation is how the bounds layer came to answer a question
    # nobody asked — and, the other way round, the arm alone is a narrower
    # question than the contrast an ``effect`` query puts.
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
    #   lower = n_joint/n,  upper = (n_joint + n_other)/n,  width = n_other/n,
    # and the contrast from these plus n_joint_other. Cardinality-agnostic:
    # n_other counts EVERY row with X≠x, so for a multi-valued treatment the
    # verifier can confirm the pooled off-arm mass is honest rather than
    # fabricated.
    x_eq = _eq(x_series, treatment_value)
    y_eq = _eq(y_series, outcome_value)
    n_used = int(len(x_series))
    n_joint = int((x_eq & y_eq).sum())
    n_other = int((~x_eq).sum())
    # The off-arm's joint count. Recorded unconditionally — it is a fact
    # about the data, where having a baseline arm to contrast against is a
    # fact about the treatment's cardinality — and it is what lets the
    # verifier re-derive the contrast below from counts alone.
    n_joint_other = int(((~x_eq) & y_eq).sum())
    contrast = _natural_ace_contrast(
        x_series, x_eq, n=n_used, n_joint=n_joint, n_other=n_other,
        n_joint_other=n_joint_other,
    )
    ci_lower, ci_upper, draws = _bootstrap_outer_band(
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
        data_columns=contract.columns,
        treatment=treatment,
        outcome=outcome,
        treatment_value=envelope_scalar(treatment_value),
        outcome_value=envelope_scalar(outcome_value),
        instrument=None,
        assumptions=(),
        cluster=cluster,
        draws=draws,
        sufficient_statistics={
            "n": n_used,
            "n_joint_target_arm": n_joint,
            "n_other_arm": n_other,
            "n_joint_other_arm": n_joint_other,
        },
        contrast=contrast,
    )


def _natural_ace_contrast(
    xs: np.ndarray, x_eq: np.ndarray, *,
    n: int, n_joint: int, n_other: int, n_joint_other: int,
) -> dict | None:
    """The average causal effect — the quantity an ``effect`` query asks for —
    when there is a single other arm to contrast the queried one against.

    Sharp, and obtained by subtracting one interval from the other rather than
    by a second optimisation. The natural bounds assume nothing, so the two
    arms' unobserved masses are the ``X≠x`` units' ``Y(x)`` and the ``X=x``
    units' ``Y(x')`` — disjoint sub-populations with no constraint tying them
    together, so every pair of points in the two intervals is jointly
    attainable and the difference of the intervals IS the interval of the
    difference. That is exactly the step Balke-Pearl may not take, and why it
    runs :func:`_ace_contrast` over its polytope instead. Neither the
    treatment's nor the outcome's cardinality enters the argument: ``Y=y`` is
    an event and the slack on each arm is free over the whole off-arm mass.

    One consequence is worth stating out loud, because it is the finding
    rather than a caveat: the width is ``P(X≠x) + P(X≠x') = 1`` exactly, on
    every dataset. Half of the ACE's logically possible ``[-1, 1]`` is
    excluded and no quantity of data narrows it further — a fact about the
    assumptions, not about the sample.

    ``None`` when the off-arm is not one level. With three or more there is no
    baseline arm the difference is against and picking one would be this
    module inventing a question the query did not ask; with none, the queried
    arm is the only one anybody was observed in and there is nothing to be
    against. Both are the condition Balke-Pearl states as ``nx != 2``, asked
    of the arms rather than of the level count so that a treatment declared
    with three levels but observed at two is answered on what the data hold.
    """
    off_arm_levels = pd.unique(xs[~x_eq])
    if len(off_arm_levels) != 1:
        return None
    n_arm = n - n_other
    return {
        "kind": "ace",
        "reference_value": envelope_scalar(off_arm_levels[0]),
        "lower_value": float((n_joint - n_joint_other - n_arm) / n),
        "upper_value": float((n_joint - n_joint_other + n_other) / n),
    }


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


def mtr_pushes_outcome_up(monotonicity: str, treatment_value) -> bool:
    """Whether intervening at this arm moves ``Y`` UP for the units observed
    in the other one.

    Half of what decides which side of the interval MTR tightens. The other
    half is where the target EVENT sits in the outcome's order, and the two
    are separate questions about separate variables — which is why they are
    two functions and not one flag. Before, only this half existed, and the
    answer it gave was used as if it were both.
    """
    return bool(treatment_value) == (monotonicity == "non_decreasing")


def xy_counts(
    xs: np.ndarray, ys: np.ndarray, x_levels: Sequence, y_levels: Sequence,
) -> np.ndarray:
    """The joint ``(X, Y)`` contingency table over the given level lists.

    The whole sufficient statistic for MTR, in the level ORDER the bound is
    about — which is why it is a table and not four scalars. Recorded on the
    envelope for the same reason Balke-Pearl records ``P_xyz``: it lets the
    verifier re-derive the interval instead of auditing metadata, and it puts
    the order this producer used somewhere a second reader can disagree with.

    A value in neither list has no place in the order, and the order is what
    the bound is computed from, so it ends the run rather than being dropped
    into a level it does not belong to.
    """
    out = np.zeros((len(x_levels), len(y_levels)), dtype=int)
    for i, xv in enumerate(x_levels):
        x_eq = _eq(xs, xv)
        for j, yv in enumerate(y_levels):
            out[i, j] = int((x_eq & _eq(ys, yv)).sum())
    if int(out.sum()) != len(xs):
        raise ValueError(
            f"themis: {len(xs) - int(out.sum())} of {len(xs)} rows hold a "
            f"(treatment, outcome) pair outside the declared levels "
            f"{list(x_levels)!r} × {list(y_levels)!r}; MTR reads the order off "
            f"the declaration, so a value it does not name has no place in it"
        )
    return out


def mtr_bounds_from_counts(
    n_xy: np.ndarray, *, xi: int, yi: int, up: bool,
) -> tuple[float, float]:
    """The sharp MTR bound on ``P(Y(x)=y)``, at any cardinality of Y, from
    the joint counts alone.

    Units observed AT the arm contribute ``1{Y=y}`` exactly, because ``Y(x)``
    is what was observed. Units observed at the OTHER arm have ``Y(x)``
    unobserved and confined by MTR to one side of what they showed:
    ``{v ≥ Y}`` when intervening here pushes the outcome up, ``{v ≤ Y}`` when
    it pushes down. So such a unit

    - CAN show ``y`` exactly when ``y`` is on that side of its observation,
      which is the upper bound's free mass;
    - MUST show ``y`` only when ``y`` is the sole value on that side — which
      happens exactly when it showed ``y`` AND ``y`` is the extreme in that
      direction, and is the lower bound's forced mass.

    The old form of this tightened one side to the observed marginal
    ``P(Y=y)`` and read WHICH side off the intervention's polarity alone. That
    is this formula at ``y = y_max`` and nowhere else: MTR constrains ``Y``,
    the bound is on the EVENT ``Y=y``, and ``1{Y=y}`` is monotone in ``Y``
    only at the top of the order — reversed at the bottom, and monotone in
    neither direction in between. Asked for ``P(Y=False | do(X=True))`` on a
    confounded binary outcome the old form returned ``[0.5626, 0.6622]`` where
    the truth was ``0.5017``: an interval that did not contain the answer.
    """
    n = int(n_xy.sum())
    if n == 0:
        return 0.0, 1.0
    same = int(n_xy[xi, yi])
    other = np.delete(n_xy, xi, axis=0)
    if up:
        reachable = int(other[:, : yi + 1].sum())
        extreme = yi == n_xy.shape[1] - 1
    else:
        reachable = int(other[:, yi:].sum())
        extreme = yi == 0
    forced = int(other[:, yi].sum()) if extreme else 0
    return (same + forced) / n, (same + reachable) / n


def evaluate_manski_tamer_bounds(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    monotonicity: str,               # "non_decreasing" | "non_increasing"
    outcome_levels: Sequence,
    treatment_value=True,
    outcome_value=True,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> NumericBounds:
    """Manski (1997) MTR bounds on ``P(Y=y | do(X=x))`` under a monotone
    treatment response. Contained in the natural interval, and sharp.

    ``outcome_levels`` is the outcome's DECLARED order, low to high, and has
    no default on purpose. MTR is a statement about that order — without it
    there is no "monotone" to assume, and the caller that knows it is the one
    holding the program. A method asked to bound an event in an order it
    cannot see is a method guessing, which is what this one did: see
    :func:`_mtr_arm` for what the guess cost.

    The CONTRAST travels beside the arm, and is sharp. The reasoning that
    said otherwise turned on MTR tying ``Y(x)`` and ``Y(x')`` together at the
    unit level, which is true and does not reach the conclusion: the two
    arms' unknowns live in DISJOINT sub-populations — the other arm's units'
    ``Y(x)`` and this arm's units' ``Y(x')`` — and each is confined only by
    its own unit's observation. Nothing couples the two, so every pair of
    points in the two intervals is jointly attainable and the difference of
    the intervals is the interval of the difference. Checked against an
    independent route: enumerating the response types ``(Y(0), Y(1))`` that
    MTR permits gives ``[0, P(X=x,Y=y) + P(X=x',Y≠y)]`` for a binary
    treatment and binary outcome, which is what subtracting the two arms
    gives, term for term.
    """
    if monotonicity not in ("non_decreasing", "non_increasing"):
        raise EstimatorFailure(
            Refusal.INVALID_MONOTONICITY, declared=monotonicity,
        )
    levels = list(outcome_levels)
    if len(levels) < 2:
        raise ValueError(
            f"themis: MTR needs an outcome with at least two declared "
            f"levels to be monotone in; got {levels!r}"
        )
    if not any(_eq(np.array([outcome_value], dtype=object), v)[0]
               for v in levels):
        raise ValueError(
            f"themis: the target event Y={outcome_value!r} is not one of the "
            f"outcome's declared levels {levels!r}, so where it sits in the "
            f"order — which is what decides the bound — is unanswerable"
        )
    contract, df, groups = _prepare(
        data, treatment, outcome, cluster=cluster,
    )
    up = mtr_pushes_outcome_up(monotonicity, treatment_value)

    x_series = df[treatment].to_numpy()
    y_series = df[outcome].to_numpy()
    x_levels, xi = _mtr_arm_levels(df[treatment], treatment_value)
    yi = next(i for i, v in enumerate(levels)
              if _eq(np.array([outcome_value], dtype=object), v)[0])

    def bounds_from(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
        return mtr_bounds_from_counts(
            xy_counts(xs, ys, x_levels, levels), xi=xi, yi=yi, up=up,
        )

    n_xy = xy_counts(x_series, y_series, x_levels, levels)
    lower, upper = mtr_bounds_from_counts(n_xy, xi=xi, yi=yi, up=up)
    contrast = _mtr_ace_contrast(n_xy, x_levels, xi=xi, yi=yi, up=up)
    # The counts ARE the closed form's input, and the level lists are the
    # order it read them in — the fact three surfaces each had to guess
    # separately, and each guessed the same wrong way. Recorded together so
    # the verifier re-derives the interval rather than auditing its shape,
    # and so a producer reading a different order is a disagreement rather
    # than a silent second answer.
    stats = {
        "n": int(n_xy.sum()),
        "n_xy": [[int(c) for c in row] for row in n_xy],
        "treatment_levels": [envelope_scalar(v) for v in x_levels],
        "outcome_levels": [envelope_scalar(v) for v in levels],
        "arm_treatment_index": int(xi),
        "arm_outcome_index": int(yi),
    }
    ci_lower, ci_upper, draws = _bootstrap_outer_band(
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
        sufficient_statistics=stats,
        ci_lower=ci_lower,
        ci_upper=ci_upper,
        ci_level=ci_level,
        width=float(width),
        width_is_trivial=bool(width >= 1.0 - _TRIVIAL_SLACK),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment,
        outcome=outcome,
        treatment_value=envelope_scalar(treatment_value),
        outcome_value=envelope_scalar(outcome_value),
        instrument=None,
        assumptions=(f"mtr_{monotonicity}",),
        cluster=cluster,
        draws=draws,
        contrast=contrast,
    )


def _mtr_arm_levels(series: pd.Series, treatment_value) -> tuple[list, int]:
    """The treatment's levels with the queried arm guaranteed among them, and
    that arm's position.

    An arm nobody was assigned to is not a reason to refuse here, which is
    what separates this from the response-function methods: MTR bounds the
    unseen arm from the OTHER arm's observations, so the answer exists and is
    merely wide. The level is therefore appended rather than looked up, and
    the resulting order carries no meaning — the closed form asks only "this
    arm or not", and the contrast asks only which single level the other one
    is.
    """
    levels = sorted_levels(series)
    for i, v in enumerate(levels):
        if _eq(np.array([v], dtype=object), treatment_value)[0]:
            return levels, i
    return levels + [treatment_value], len(levels)


def _mtr_ace_contrast(
    n_xy: np.ndarray, x_levels: Sequence, *, xi: int, yi: int, up: bool,
) -> dict | None:
    """The ACE under MTR, when a single other arm gives the difference a
    baseline — the same condition, asked the same way, as
    :func:`_natural_ace_contrast`.

    Obtained by subtracting the other arm's MTR interval from this one's, and
    sharp for the reason in :func:`evaluate_manski_tamer_bounds`. The other
    arm's interval is this same bound with ``up`` flipped: intervening there
    pushes the outcome the other way for the units observed here.

    Half of the ACE's logically possible range is excluded on every dataset —
    the assumption says the effect has a sign, and the interval carries it.
    """
    if len(x_levels) != 2:
        return None
    other = 1 - xi
    lo_a, hi_a = mtr_bounds_from_counts(n_xy, xi=xi, yi=yi, up=up)
    lo_b, hi_b = mtr_bounds_from_counts(n_xy, xi=other, yi=yi, up=not up)
    return {
        "kind": "ace",
        "reference_value": envelope_scalar(x_levels[other]),
        "lower_value": float(lo_a - hi_b),
        "upper_value": float(hi_a - lo_b),
    }


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




















def counterfactual_cell_iv_table(
    x_arr: np.ndarray, y_arr: np.ndarray, z_arr: np.ndarray, z_levels: list,
    *, instrument: str,
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
                cells=[{instrument: zv}],
                quantity=f"P(x, y | {instrument})",
            )
        for xi in (0, 1):
            for yi in (0, 1):
                cnt = int((zmask & (x == bool(xi)) & (y == bool(yi))).sum())
                P[zi, xi, yi] = cnt / rows
    return P, p_z














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
        quantity_columns=(treatment, outcome, instrument),
    )
    df = contract.data

    x_levels = sorted_levels(df[treatment])
    y_levels = sorted_levels(df[outcome])
    z_levels = sorted_levels(df[instrument])
    nx, ny, nz = len(x_levels), len(y_levels), len(z_levels)

    for col, role, levels in (
        (treatment, refusals.QueryRole.EXPOSURE, x_levels),
        (outcome, refusals.QueryRole.OUTCOME, y_levels),
        (instrument, refusals.QueryRole.INSTRUMENT, z_levels),
    ):
        if len(levels) < 2:
            raise EstimatorFailure(
                Refusal.OVERLAP_INSUFFICIENT,
                column=col, role=role, levels=list(levels),
            )

    if response_type_count(
        treatment_levels=nx, outcome_levels=ny, instrument_levels=nz,
    ) is None:
        raise EstimatorFailure(
            Refusal.RESPONSE_MODEL_TOO_LARGE,
            nx=nx, ny=ny, nz=nz, cap=MAX_RESPONSE_TYPES,
            # Which columns they were. The sentence names the roles and
            # not the names, because the other raise site of this species
            # knows only the instrument's.
            recorded={"treatment": treatment, "outcome": outcome,
                      "instrument": instrument},
        )

    xi = _level_index(
        x_levels, treatment_value, treatment, refusals.QueryRole.EXPOSURE)
    yi = _level_index(
        y_levels, outcome_value, outcome, refusals.QueryRole.OUTCOME)
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
        "treatment_levels": [envelope_scalar(v) for v in x_levels],
        "outcome_levels": [envelope_scalar(v) for v in y_levels],
        "instrument_levels": [envelope_scalar(v) for v in z_levels],
        "arm_treatment_index": xi,
        "arm_outcome_index": yi,
    }
    ci_lower, ci_upper, draws = _bootstrap_outer_band_frame(
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
        data_columns=contract.columns,
        treatment=treatment,
        outcome=outcome,
        treatment_value=envelope_scalar(treatment_value),
        outcome_value=envelope_scalar(outcome_value),
        instrument=instrument,
        assumptions=(
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ),
        cluster=cluster,
        draws=draws,
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
        "reference_value": envelope_scalar(x_levels[other]),
        "lower_value": float(lo),
        "upper_value": float(hi),
    }


def _level_index(
    levels: list, value, column: str, role: refusals.QueryRole,
) -> int:
    """Position of ``value`` among the sorted observed levels."""
    for i, v in enumerate(levels):
        if v == value or (isinstance(value, bool) and bool(v) == value):
            return i
    raise EstimatorFailure(
        Refusal.TARGET_VALUE_ABSENT,
        column=column, role=role, value=value, observed=levels,
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
                cells=[{instrument: zv}],
                quantity=f"P({treatment}, {outcome} | {instrument})",
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
        quantity_columns=(treatment, outcome),
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




def _bootstrap_outer_band(
    df: pd.DataFrame, treatment: str, outcome: str,
    bounds_from,
    *, ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[float | None, float | None, Draws | None]:
    """Percentile-bootstrap OUTER band for an arm-probability method whose
    ``bounds_from(xs, ys)`` returns (lower, upper) from two arrays.

    The accumulator is returned rather than taken, because this function is
    the one that knows whether a bootstrap ran at all; a ``None`` back is
    the statement that none did."""
    if ci_bootstrap <= 0:
        return None, None, None
    rng = np.random.default_rng(random_state)
    n = len(df)
    xs_all = df[treatment].to_numpy()
    ys_all = df[outcome].to_numpy()
    lowers: list[float] = []
    uppers: list[float] = []
    draws = Draws(ci_bootstrap)
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        lo, hi = bounds_from(xs_all[idx], ys_all[idx])
        lowers.append(lo)
        uppers.append(hi)
        draws.usable()
    if not draws.enough:
        return None, None, draws
    return (*_outer_quantiles(lowers, uppers, ci_level), draws)


def _bootstrap_outer_band_frame(
    df: pd.DataFrame, bounds_from_frame,
    *, ci_bootstrap: int, ci_level: float, random_state: int,
    groups: np.ndarray | None,
) -> tuple[float | None, float | None, Draws | None]:
    """Percentile-bootstrap OUTER band for a method that needs the whole
    frame per replicate (Balke-Pearl reads three columns). A replicate that
    hits a positivity failure (an empty instrument stratum on that draw) is
    dropped and filed under the refusal that dropped it — the band is over
    the evaluable draws, and the count of the others travels with it."""
    if ci_bootstrap <= 0:
        return None, None, None
    rng = np.random.default_rng(random_state)
    n = len(df)
    lowers: list[float] = []
    uppers: list[float] = []
    draws = Draws(ci_bootstrap)
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        try:
            lo, hi = bounds_from_frame(df.iloc[idx])
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        lowers.append(lo)
        uppers.append(hi)
        draws.usable()
    if not draws.enough:
        return None, None, draws
    return (*_outer_quantiles(lowers, uppers, ci_level), draws)


def _outer_quantiles(
    lowers: list[float], uppers: list[float], ci_level: float,
) -> tuple[float, float]:
    alpha = (1.0 - ci_level) / 2.0
    lo_band = float(np.quantile(np.asarray(lowers), alpha))
    hi_band = float(np.quantile(np.asarray(uppers), 1.0 - alpha))
    return lo_band, hi_band
