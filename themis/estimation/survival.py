"""A censored outcome, answered as the quantity a censored outcome has.

The kernel could not say that a column is a follow-up time. So it read one
as an ordinary number, and the estimator averaged it. Measured on a design
whose truth is known — exponential survival, a treatment that doubles the
mean, independent exponential censoring taking 41.5% of the units — the
recorded column's arm difference is +0.333 where the survival times' is
+1.000, and ``themis.estimate`` returned ``+0.343``, ``numerically_solved``,
``backdoor_linear``, with no word in the envelope for what had happened.
Three times off, wearing a badge that says estimated.

**The mean of a censored variable is not a quantity this data has.** Waiting
longer is the only thing that shortens the unobserved tail, and no estimator
recovers it. What the data does have is the mean of ``min(T, τ)`` for a
horizon τ inside the follow-up — the RESTRICTED mean survival time (Irwin
1949; Royston & Parmar 2013). So the horizon is not a tuning parameter here
and not a default: it is the second half of the question, and a caller who
does not name one is asking for a number their data cannot carry.

That makes the estimand the same SHAPE the kernel already answers with —
a difference of means, ``E[min(T,τ)|do(x=1)] − E[min(T,τ)|do(x=0)]`` — so
no new query kind, no new reading. What changes is how the mean is taken.

**Kaplan-Meier (1958) rather than a hazard model.** A Cox hazard ratio
needs proportional hazards, which is an assumption about the whole curve
that the data is asked to carry silently; RMST needs none of it, is a
difference in TIME (a reader can be told what it means without a lesson in
hazards), and reduces to the ordinary arm difference when nothing is
censored. Cox is not built here, and the reason is not effort: a hazard
ratio and a difference in restricted means answer different questions, and
this package's estimand was already the second one.

**The covariate adjustment is the g-formula, not a regression.** Per
stratum and arm the curve is non-parametric; the strata are then averaged
with the marginal stratum weights. So the only functional-form assumption
in the whole route is the one the caller made when they chose the strata,
which is the same assumption ``backdoor_stratified`` already carries.

Independent censoring is assumed WITHIN each stratum and arm, and it is the
one assumption here that the data cannot test. It is declared, and it is
what the adjustment set is for: censoring that depends on a recorded
covariate is handled by conditioning on it, which is exactly what
stratifying does.

The sufficient statistic is the per-arm risk table — one row per distinct
observed time, carrying how many were at risk, how many had the event and
how many left. Every number below is a function of those tables alone, so
a verifier re-derives the curve, the area and the variance without the
rows.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..refusals import EstimatorFailure, Refusal, Remedy
from ..intervals import CONFIDENCE_LEVEL
from .contract import validate_data

#: Two-sided normal quantiles, for the interval. The same three levels the
#: rest of the estimation layer offers, read from one table rather than
#: from ``scipy`` — the dependency is already optional here and a normal
#: quantile at three fixed levels is a constant, not a computation.
_Z = {0.90: 1.6448536269514722,
      0.95: 1.959963984540054,
      0.99: 2.5758293035489004}


@dataclass(frozen=True)
class RiskRow:
    """One distinct observed time, and what happened at it.

    ``at_risk`` counts the units whose recorded time is at or after this
    one — the denominator of the drop. ``events`` and ``censored`` split
    the units recorded exactly here, and they are kept apart because only
    the first moves the curve while both leave the risk set.
    """

    time: float
    at_risk: int
    events: int
    censored: int


@dataclass(frozen=True)
class SurvivalArm:
    """One (stratum, arm) cell: its table, its area, and its weight."""

    arm: bool
    stratum: tuple
    weight: float
    n: int
    n_events: int
    n_censored: int
    rmst: float
    variance: float
    last_observed: float
    risk_table: tuple[RiskRow, ...]


@dataclass(frozen=True)
class SurvivalEstimate:
    """The difference in restricted mean survival time, and what it rests on."""

    point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    horizon: float
    treatment: str
    outcome: str
    event_indicator: str
    adjustment: tuple[str, ...]
    rmst_treated: float
    rmst_control: float
    variance: float
    sample_size: int
    n_events: int
    censored_share: float
    follow_up_ends: float
    arms: tuple[SurvivalArm, ...]
    assumptions: tuple[str, ...]
    data_hash: str
    data_columns: tuple[str, ...]
    exhausted_cells: tuple[tuple, ...] = ()
    """Cells whose curve reached zero — the variance term at that time is
    0/0 and is dropped. Recorded rather than absorbed: the interval there
    rests on fewer terms than the curve does, and a reader comparing two
    intervals is entitled to know which of them is missing one."""


def _risk_table(time: np.ndarray, event: np.ndarray) -> tuple[RiskRow, ...]:
    """The sufficient statistic, one row per distinct observed time.

    Every distinct time, not only the ones where the curve moves: a row
    with no events still says how many units left, and without it the
    denominators after it cannot be rebuilt from the table alone.
    """
    distinct, where, counts = np.unique(time, return_inverse=True,
                                        return_counts=True)
    events = np.bincount(where, weights=(event == 1),
                         minlength=len(distinct)).astype(int)
    # Everyone still standing when this time arrives — which is everyone
    # minus whoever left at an earlier one. From a cumulative sum rather
    # than a comparison per distinct time: with continuous follow-up every
    # time is distinct, and a pass over the sample per row would make the
    # cost of a curve quadratic in the sample it was measured on.
    at_risk = len(time) - np.concatenate(([0], np.cumsum(counts)[:-1]))
    return tuple(
        RiskRow(time=float(t), at_risk=int(n), events=int(d),
                censored=int(c - d))
        for t, n, d, c in zip(distinct, at_risk, events, counts)
    )


def _curve(table: tuple[RiskRow, ...], horizon: float
           ) -> tuple[list[tuple[float, float]], bool]:
    """``[(time, S just AFTER it), ...]`` up to the horizon, and whether the
    curve reached zero inside it.

    The pairs are what both the area and the variance are read off, so they
    are computed once. ``S`` after a row where everyone at risk had the
    event is exactly zero, and it stays there.
    """
    steps: list[tuple[float, float]] = []
    s, exhausted = 1.0, False
    for row in table:
        if row.time > horizon:
            break
        if row.events:
            if row.at_risk == row.events:
                exhausted = True
            s *= 1.0 - row.events / row.at_risk
        steps.append((row.time, s))
    return steps, exhausted


def _area(steps: list[tuple[float, float]], horizon: float,
          start: float = 0.0) -> float:
    """``∫ S(u) du`` from ``start`` to the horizon.

    ``S`` is constant on ``[t_{j-1}, t_j)`` at the value it took after the
    previous step, so each strip is that value times the strip's width. The
    last strip runs to the horizon, which is why the horizon has to sit
    inside the follow-up: past the last observation there is no value to
    carry forward, only a guess about the tail.
    """
    area, prev, s = 0.0, start, 1.0
    for time, after in steps:
        if time <= start:
            s = after
            continue
        area += s * (min(time, horizon) - prev)
        prev = min(time, horizon)
        s = after
        if time >= horizon:
            break
    if prev < horizon:
        area += s * (horizon - prev)
    return area


def _variance(table: tuple[RiskRow, ...], steps: list[tuple[float, float]],
              horizon: float) -> tuple[float, bool]:
    """Greenwood's variance carried through the integral.

    ``Var = Σ_j A_j² · d_j / (n_j(n_j − d_j))`` with ``A_j`` the area still
    to come after ``t_j`` (Klein & Moeschberger §4.5). A term where every
    unit at risk had the event is ``0/0``; it is dropped and said, rather
    than silently taken as zero — the curve is exactly zero from there on
    under the usual convention, but the uncertainty about it is not.
    """
    total, dropped = 0.0, False
    for row in table:
        if row.time > horizon or not row.events:
            continue
        if row.at_risk == row.events:
            dropped = True
            continue
        ahead = _area(steps, horizon, start=row.time)
        total += ahead * ahead * row.events / (
            row.at_risk * (row.at_risk - row.events))
    return total, dropped


def _named(keys, stratum, *, arm=None) -> str:
    """One cell, as a refusal names it to a reader.

    A cell and not a stratum where the arm is given, because the two
    refusals that use this differ in what they are about: one arm being
    absent is a fact about the STRATUM, and follow-up ending early is a
    fact about the one cell that ended early.
    """
    where = ", ".join(f"{k}={v}" for k, v in zip(keys, stratum))
    if arm is not None:
        where = f"{where}, {'treated' if arm else 'control'}" if where else (
            "treated" if arm else "control")
    return where or "(all rows)"


def _cell(frame: pd.DataFrame, outcome: str, event: str, horizon: float,
          arm: bool, stratum: tuple, weight: float
          ) -> tuple[SurvivalArm, bool]:
    """One cell, and whether its interval is short a variance term."""
    time = frame[outcome].to_numpy(float)
    seen = frame[event].to_numpy(float)
    table = _risk_table(time, seen)
    steps, exhausted = _curve(table, horizon)
    var, dropped = _variance(table, steps, horizon)
    return SurvivalArm(
        arm=arm, stratum=stratum, weight=weight, n=len(frame),
        n_events=int((seen == 1).sum()), n_censored=int((seen == 0).sum()),
        rmst=_area(steps, horizon), variance=var,
        last_observed=float(time.max()), risk_table=table,
    ), (exhausted or dropped)


def restricted_mean_survival(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    event_indicator: str,
    horizon: float | None = None,
    adjustment: tuple[str, ...] = (),
    ci_level: float = CONFIDENCE_LEVEL,
    cluster: str | None = None,
) -> SurvivalEstimate:
    """``E[min(T,τ)|do(x=1)] − E[min(T,τ)|do(x=0)]``, by Kaplan-Meier per cell.

    :param event_indicator: the column that says whether the recorded time
        is the event or the end of follow-up — 1 and 0 respectively. It is
        the whole of what the declaration adds, and without it the outcome
        column is indistinguishable from an ordinary measurement.
    :param horizon: τ. Required, and the refusal when it is absent is the
        point of this module rather than an omission: the unrestricted mean
        is not a quantity censored data carries.
    :param cluster: the run's unit of independence, where the caller named
        one. Greenwood's variance counts every unit as its own, so this
        route cannot honour it — and takes it anyway, to SAY so. An
        interval that stays silent about a named cluster column reads as
        i.i.d. inference nobody licensed, and it is the width rather than
        the point that is wrong, which is what makes silence undetectable
        by anything downstream.
    """
    if horizon is None:
        # The sentence says what is missing and the route says what to do
        # about it, and they are separate because the second belongs to the
        # occasion: the same species raised from a direct call wants a
        # keyword, and raised from a program wants a line in a declaration.
        raise EstimatorFailure(Refusal.A_CENSORED_MEAN_NEEDS_A_HORIZON,
                               outcome=outcome,
                               remedies=[(Remedy.SUPPLY_INPUT, "horizon")])
    if not isinstance(horizon, (int, float)) or isinstance(horizon, bool) \
            or not math.isfinite(horizon) or horizon <= 0:
        raise EstimatorFailure(Refusal.ARGUMENT_NOT_A_NUMBER,
                               argument="horizon", given=repr(horizon))

    contract = validate_data(
        data,
        required_columns=[treatment, outcome, event_indicator, *adjustment],
        quantity_columns=[outcome],
    )
    frame = contract.data
    seen = frame[event_indicator].to_numpy(float)
    if not np.isin(seen, (0.0, 1.0)).all():
        raise EstimatorFailure(Refusal.THE_EVENT_COLUMN_IS_NOT_AN_INDICATOR,
                               column=event_indicator,
                               got=", ".join(
                                   repr(v) for v in
                                   sorted(set(seen.tolist()))[:6]))
    if (frame[outcome].to_numpy(float) < 0).any():
        raise EstimatorFailure(Refusal.A_FOLLOW_UP_TIME_IS_NEGATIVE,
                               column=outcome)

    arms = sorted(set(frame[treatment].to_numpy().tolist()))
    if len(arms) != 2:
        raise EstimatorFailure(Refusal.TREATMENT_NOT_BINARY,
                               treatment=treatment, levels=len(arms))

    keys = list(adjustment)
    if keys:
        groups = list(frame.groupby(keys, sort=True, observed=True))
    else:
        groups = [((), frame)]

    cells: list[SurvivalArm] = []
    exhausted: list[tuple] = []
    total = len(frame)
    for stratum, block in groups:
        stratum = stratum if isinstance(stratum, tuple) else (stratum,)
        weight = len(block) / total
        # Which of the two levels is the treated arm is decided by ORDER,
        # not by truthiness. ``bool`` of the level is the obvious spelling
        # and is wrong wherever a two-level column is coded other than 0/1:
        # both arms come back True, one side of the contrast holds every
        # cell and the other holds none, and the difference of the two
        # standardised means is then a number with no second arm in it.
        for arm, level in ((False, arms[0]), (True, arms[1])):
            side = block[block[treatment] == level]
            if side.empty:
                raise EstimatorFailure(
                    Refusal.NO_WITHIN_STRATUM_CONTRAST,
                    column=treatment, strata=_named(keys, stratum))
            # The horizon has to sit inside every cell's follow-up, not
            # only inside the pooled one: a curve is carried forward from
            # its own last observation, and a cell that ends earlier would
            # contribute a flat guess about a stretch it never saw.
            if side[outcome].max() < horizon:
                raise EstimatorFailure(
                    Refusal.THE_HORIZON_IS_PAST_THE_LAST_OBSERVATION,
                    horizon=f"{horizon:g}",
                    last=f"{side[outcome].max():g}",
                    stratum=_named(keys, stratum, arm=arm),
                    remedies=[(Remedy.CHANGE_INPUT, "horizon")])
            # ``level`` is what selects the rows; ``arm`` is what the cell
            # is filed under. Two names because the first is the caller's
            # coding and the second is the contrast's own.
            cell, missing = _cell(side, outcome, event_indicator, horizon,
                                  arm, stratum, weight)
            cells.append(cell)
            if missing:
                exhausted.append((stratum, arm))

    def _standardised(which: bool) -> tuple[float, float]:
        mean = sum(c.weight * c.rmst for c in cells if c.arm is which)
        var = sum(c.weight * c.weight * c.variance
                  for c in cells if c.arm is which)
        return mean, var

    treated, var_treated = _standardised(True)
    control, var_control = _standardised(False)
    point = treated - control
    variance = var_treated + var_control
    z = _Z.get(round(ci_level, 4))
    lower = upper = None
    if z is not None and variance > 0:
        half = z * math.sqrt(variance)
        lower, upper = point - half, point + half

    return SurvivalEstimate(
        point=point, ci_lower=lower, ci_upper=upper, ci_level=ci_level,
        method="rmst_kaplan_meier", horizon=float(horizon),
        treatment=treatment, outcome=outcome,
        event_indicator=event_indicator, adjustment=tuple(adjustment),
        rmst_treated=treated, rmst_control=control, variance=variance,
        sample_size=total, n_events=int((seen == 1).sum()),
        censored_share=float((seen == 0).mean()),
        follow_up_ends=float(frame[outcome].max()),
        arms=tuple(cells), assumptions=_assumptions(adjustment, cluster),
        # The contract's digest, not one of this module's own. Two answers
        # over the same columns have to carry the same fingerprint or the
        # envelope reads as two runs of two tables — which is what
        # ``verify_fingerprints_agree`` exists to catch, and did.
        data_hash=contract.data_hash, data_columns=contract.columns,
        exhausted_cells=tuple(exhausted),
    )


def _assumptions(adjustment: tuple[str, ...],
                 cluster: str | None = None) -> tuple[str, ...]:
    """What the number rests on that the data cannot check.

    The back-door core first, because this route is back-door identified
    and nothing about a censored outcome weakens or replaces it: the same
    exchangeability, the same positivity, the same consistency the
    g-formula always needs. Positivity unconditionally, and it is measured
    rather than claimed — a cell with one arm in it leaves by
    :data:`Refusal.NO_WITHIN_STRATUM_CONTRAST` above, so an estimate that
    exists is an estimate whose cells all had both.

    Independent censoring is the one this route ADDS, and which of its two
    spellings appears says how strong it is: conditioning on a covariate
    is how censoring that depends on that covariate is handled, so the
    premise is weaker the more the caller adjusted for. Two ids rather
    than one interpolated, because an id is a token a glossary answers to
    and not a sentence.

    And the horizon, which is a premise about the ANALYST rather than
    about the world: τ read off the curves is a choice made after seeing
    the data, and what it costs is the interval's meaning rather than the
    point's.
    """
    said: tuple[str, ...] = (
        "conditional_exchangeability_given_adjustment_set",
        "positivity_overlap_of_treatment_arms",
        "consistency_of_potential_outcomes",
        "censoring_is_independent_of_survival_within_each_stratum_and_arm"
        if adjustment else
        "censoring_is_independent_of_survival_within_each_arm",
        "the_horizon_was_fixed_before_the_curves_were_seen",
    )
    if cluster is not None:
        # Greenwood counts every unit as its own, so the width here is the
        # i.i.d. one. Said rather than silently taken: it is the interval
        # and not the point that is wrong under clustering, and nothing
        # downstream can see a width that should have been wider.
        said += (f"ci_not_cluster_robust_analytic_interval_ignores_{cluster}",)
    return said


def survival_to_dict(est: SurvivalEstimate) -> dict:
    """The block as the envelope carries it."""
    return {
        "method": est.method,
        "horizon": est.horizon,
        "event_indicator": est.event_indicator,
        "rmst_treated": est.rmst_treated,
        "rmst_control": est.rmst_control,
        "variance": est.variance,
        "n_events": est.n_events,
        "censored_share": est.censored_share,
        "follow_up_ends": est.follow_up_ends,
        "exhausted_cells": [
            {"stratum": [str(v) for v in stratum], "arm": bool(arm)}
            for stratum, arm in est.exhausted_cells
        ],
        "cells": [
            {
                "arm": cell.arm,
                "stratum": [str(v) for v in cell.stratum],
                "weight": cell.weight,
                "n": cell.n,
                "n_events": cell.n_events,
                "n_censored": cell.n_censored,
                "rmst": cell.rmst,
                "variance": cell.variance,
                "last_observed": cell.last_observed,
                "risk_table": [
                    {"time": r.time, "at_risk": r.at_risk,
                     "events": r.events, "censored": r.censored}
                    for r in cell.risk_table
                ],
            }
            for cell in est.arms
        ],
    }
