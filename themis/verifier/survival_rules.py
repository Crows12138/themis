"""Independent audit of a restricted mean survival time.

The block records, per (stratum, arm), the risk table the estimate was
read off: one row per distinct observed time, carrying how many units
were at risk, how many had the event, and how many left without it. That
table is a sufficient statistic — the curve, the area under it and its
variance are functions of nothing else — so this module recomputes the
whole answer from the tables and compares, without the data and without
importing the estimator.

Three checks, and only the first is arithmetic:

**The curve.** ``S(t) = Π (1 − d_j/n_j)`` over the event times at or
before ``t``, the area ``∫₀^τ S`` as the sum of its strips, and
Greenwood's variance carried through that integral,
``Σ_j A_j²·d_j/(n_j(n_j−d_j))``. Each cell's three numbers are re-derived
and held to what it recorded.

**The standardisation.** The two reported arm means must be the recorded
cell means weighted by the recorded weights, the weights within an arm
must sum to one, and the point must be their difference. A cell whose
weight is right and whose curve is wrong, or the reverse, both survive a
check of only one of the two.

**The table's own consistency**, which is what makes the first check
worth anything. Everything above is a function of the risk set, so a
table whose ``at_risk`` column is wrong recomputes to a curve, an area
and a variance that agree with each other perfectly and describe nobody —
and the two ways a producer gets it wrong (counting ``>`` for ``>=``,
forgetting that a unit who leaves without the event still leaves) both
take exactly that shape. So a risk set has to be what the row before it
leaves standing, and the counts the cell records beside the table — how
many units, how many events, how many left — have to be the ones the
table implies.

The limit is worth stating rather than leaving implied: the block IS the
evidence. A producer that rewrote the table AND every scalar derived from
it would leave something nothing here could refute. What this rules out
is a wrong table and a producer bug, not a determined liar with a
consistent story; for that there is the horizon refusal and the fact that
the columns the answer stands on are fingerprinted elsewhere.

What no arithmetic reaches is whether censoring was independent of
survival within each cell — the assumption the whole route rests on, and
one the data cannot witness. So it is held to reaching the assumption
ledger, where a reader can disagree with it, on the pattern the Berkson
audit set for the same shape of claim.

**Independence pin:** this module MUST NOT import from
``themis.estimation``. Everything it needs is on the envelope.
"""
from __future__ import annotations

import math
from typing import NoReturn

from .errors import VerificationError

_RULE = "survival_curve_check"
_TOL = 1e-9

#: What the ledger owes a reader here, by the prefix the id carries. A
#: prefix rather than a spelling, because the producer says which set the
#: assumption was weakened by and the audit's business is that it was
#: stated at all — pinning the whole string would make this a check that
#: the producer's wording has not changed.
_INDEPENDENT_CENSORING = "censoring_is_independent_of_survival"


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(f"{what} must be a number; got {value!r}")
    return float(value)


def _count(value: object, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _reject(f"{what} must be a count; got {value!r}")
    return value


def _agree(recomputed: float, recorded: float, what: str) -> None:
    if not math.isclose(recomputed, recorded, rel_tol=1e-7,
                        abs_tol=_TOL * max(abs(recomputed), 1.0)):
        _reject(f"{what}: recorded {recorded!r}, recomputed {recomputed!r}")


def _table(rows: object, where: str) -> list[tuple[float, int, int, int]]:
    """The recorded rows, checked for being a risk table at all."""
    if not isinstance(rows, list) or not rows:
        _reject(f"{where}.risk_table is missing")
    out: list[tuple[float, int, int, int]] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            _reject(f"{where}.risk_table[{i}] must be an object")
        time = _number(row.get("time"), f"{where}.risk_table[{i}].time")
        at_risk = _count(row.get("at_risk"), f"{where}.risk_table[{i}].at_risk")
        events = _count(row.get("events"), f"{where}.risk_table[{i}].events")
        left = _count(row.get("censored"), f"{where}.risk_table[{i}].censored")
        if time < 0:
            _reject(f"{where}.risk_table[{i}].time is {time!r}; a follow-up "
                    f"time is not negative")
        if out and time <= out[-1][0]:
            _reject(f"{where}.risk_table is not in increasing time order at "
                    f"row {i}; a table with a repeated or reordered time is "
                    f"not the one-row-per-distinct-time statistic the curve "
                    f"is read off")
        if events + left > at_risk:
            _reject(f"{where}.risk_table[{i}] loses {events + left} units "
                    f"from a risk set of {at_risk}")
        # The denominator has to be what the row before it leaves standing.
        # Checked here, in table order and before anything softer, because
        # it is the load-bearing one: a forger who drops the censored units
        # produces a table every other check below passes, and a curve that
        # is internally perfect and too optimistic everywhere. Whatever else
        # is wrong with a row, this is the first thing to say about it.
        if out:
            expected = out[-1][1] - out[-1][2] - out[-1][3]
            if at_risk != expected:
                _reject(
                    f"{where}.risk_table[{i}] says {at_risk} were at risk "
                    f"where the row before it leaves {expected}; the risk set "
                    f"is what the curve divides by, so a table that does not "
                    f"account for its own losses recomputes to a curve that "
                    f"is internally consistent and wrong"
                )
        if events + left == 0:
            _reject(f"{where}.risk_table[{i}] records a time at which "
                    f"nothing happened; the table has a row per OBSERVED "
                    f"time, and an empty one hides nothing but adds a "
                    f"denominator no unit ever stood in")
        out.append((time, at_risk, events, left))
    return out


def _curve(table, horizon: float) -> list[tuple[float, float]]:
    """``[(time, S just after it), ...]`` up to the horizon."""
    steps, s = [], 1.0
    for time, at_risk, events, _ in table:
        if time > horizon:
            break
        if events:
            s *= 1.0 - events / at_risk
        steps.append((time, s))
    return steps


def _area(steps, horizon: float, start: float = 0.0) -> float:
    """``∫ S(u) du`` from ``start`` to the horizon, strip by strip."""
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


def _variance(table, steps, horizon: float) -> float:
    """Greenwood's variance carried through the integral."""
    total = 0.0
    for time, at_risk, events, _ in table:
        if time > horizon or not events or at_risk == events:
            continue
        ahead = _area(steps, horizon, start=time)
        total += ahead * ahead * events / (at_risk * (at_risk - events))
    return total


def verify_survival_curve(result: dict) -> None:
    """Re-derive a ``survival_curve`` block from its own risk tables.

    Takes the ``query_result`` envelope: the block's arithmetic and the
    premise it owes the reader live on opposite sides of it. Returns
    ``None`` when the result carries no such block. Raises
    ``VerificationError`` on a curve, area or variance that does not
    recompute, a standardisation that is not the weighted mean it claims,
    a risk table that does not account for its own losses, or an
    independent-censoring premise that never reached the ledger.
    """
    if not isinstance(result, dict):
        return
    block = (result.get("extensions") or {}).get("survival_curve")
    if block is None:
        return
    if not isinstance(block, dict):
        _reject("extensions.survival_curve must be an object")

    horizon = _number(block.get("horizon"), "survival_curve.horizon")
    if not (horizon > 0) or not math.isfinite(horizon):
        _reject(f"a restricted mean is taken to a horizon; got {horizon!r}")

    cells = block.get("cells")
    if not isinstance(cells, list) or not cells:
        _reject("survival_curve.cells is missing; the block's whole content "
                "is the per-cell tables the answer was read off")

    exhausted = {
        (tuple(str(v) for v in (c.get("stratum") or ())), bool(c.get("arm")))
        for c in block.get("exhausted_cells") or ()
        if isinstance(c, dict)
    }
    by_arm: dict[bool, list[tuple[float, float, float]]] = {True: [], False: []}
    events = 0
    for i, cell in enumerate(cells):
        if not isinstance(cell, dict):
            _reject(f"survival_curve.cells[{i}] must be an object")
        where = f"survival_curve.cells[{i}]"
        arm = cell.get("arm")
        if not isinstance(arm, bool):
            _reject(f"{where}.arm must say which of the two arms this is")
        stratum = tuple(str(v) for v in (cell.get("stratum") or ()))
        table = _table(cell.get("risk_table"), where)

        # The counts the table implies, against the counts the cell claims.
        # Two cells could swap tables and keep every curve below valid.
        n = table[0][1]
        _agree(n, _count(cell.get("n"), f"{where}.n"),
               f"{where}: units at risk at the first observed time")
        _agree(sum(row[2] for row in table),
               _count(cell.get("n_events"), f"{where}.n_events"),
               f"{where}: events in the table")
        _agree(sum(row[3] for row in table),
               _count(cell.get("n_censored"), f"{where}.n_censored"),
               f"{where}: units whose follow-up ended without the event")
        _agree(table[-1][0],
               _number(cell.get("last_observed"), f"{where}.last_observed"),
               f"{where}: the last observed time")
        if table[-1][0] < horizon:
            _reject(
                f"{where} was followed to {table[-1][0]!r} and the mean is "
                f"reported to {horizon!r}; past the last observation a curve "
                f"is carried flat, so the area there is a guess about a "
                f"stretch nobody watched"
            )

        steps = _curve(table, horizon)
        rmst = _area(steps, horizon)
        variance = _variance(table, steps, horizon)
        _agree(rmst, _number(cell.get("rmst"), f"{where}.rmst"),
               f"{where}: the area under its Kaplan-Meier curve")
        _agree(variance, _number(cell.get("variance"), f"{where}.variance"),
               f"{where}: Greenwood's variance carried through the integral")

        # A dropped term is a narrower interval, so a cell that dropped one
        # in silence is the one forgery this arithmetic cannot see: the
        # recomputation drops the same term and agrees.
        dropped = any(at_risk == ev and ev and t <= horizon
                      for t, at_risk, ev, _ in table)
        if dropped and (stratum, arm) not in exhausted:
            _reject(
                f"{where} has a time at which every unit at risk had the "
                f"event, so its variance rests on one term fewer than its "
                f"curve does — and the block does not list it among "
                f"exhausted_cells, where a reader comparing two intervals "
                f"would look for that"
            )
        weight = _number(cell.get("weight"), f"{where}.weight")
        if not 0.0 < weight <= 1.0:
            _reject(f"{where}.weight is {weight!r}; a stratum weight is a "
                    f"share of the sample")
        # The RECOMPUTED pair, not the recorded one. They were just held
        # equal, so the two carry the same numbers today — and taking the
        # recomputation is what keeps the standardisation below downstream
        # of this module's own arithmetic rather than of the producer's.
        by_arm[arm].append((weight, rmst, variance))
        events += sum(row[2] for row in table)

    _agree(events, _count(block.get("n_events"), "survival_curve.n_events"),
           "the events across every cell")

    means: dict[bool, float] = {}
    for arm, side in by_arm.items():
        if not side:
            _reject(
                f"survival_curve records no cell for the "
                f"{'treated' if arm else 'control'} arm; a difference of two "
                f"restricted means needs both of them"
            )
        _agree(sum(w for w, _, _ in side), 1.0,
               f"the stratum weights within the "
               f"{'treated' if arm else 'control'} arm")
        means[arm] = sum(w * m for w, m, _ in side)

    _agree(means[True],
           _number(block.get("rmst_treated"), "survival_curve.rmst_treated"),
           "the treated arm's standardised restricted mean")
    _agree(means[False],
           _number(block.get("rmst_control"), "survival_curve.rmst_control"),
           "the control arm's standardised restricted mean")
    variance = sum(w * w * v for side in by_arm.values() for w, _, v in side)
    _agree(variance,
           _number(block.get("variance"), "survival_curve.variance"),
           "the variance of the difference")

    estimate = result.get("numeric_estimate")
    if isinstance(estimate, dict):
        _agree(means[True] - means[False],
               _number(estimate.get("point"), "numeric_estimate.point"),
               "the answer against the difference of the two arms' means")
        _check_the_interval(estimate, variance)
    _check_the_premise_reached_the_reader(result)


def _check_the_interval(estimate: dict, variance: float) -> None:
    """The interval's half-width, against the variance the tables imply.

    Restated rather than imported: two quantiles from one table would be
    one table checked against itself. An interval at a level this audit
    does not hold a quantile for is not an error — the producer offers
    three and a reader may ask for another — but one at a level it DOES
    hold has to be the interval that variance gives.
    """
    quantile = {0.90: 1.6448536269514722, 0.95: 1.959963984540054,
                0.99: 2.5758293035489004}.get(
        round(_number(estimate.get("ci_level"), "numeric_estimate.ci_level"), 4)
    )
    lower, upper = estimate.get("ci_lower"), estimate.get("ci_upper")
    if quantile is None or lower is None or upper is None:
        return
    _agree(2.0 * quantile * math.sqrt(variance),
           _number(upper, "numeric_estimate.ci_upper")
           - _number(lower, "numeric_estimate.ci_lower"),
           "the interval's width against the variance the tables imply")


def _check_the_premise_reached_the_reader(result: dict) -> None:
    """Independent censoring is why the curve is the survival curve.

    The one assumption this route adds that no arithmetic witnesses: the
    units still standing at each time have to be exchangeable with those
    who left, and a table where they are not produces a curve that is
    internally perfect. A premise that stops at the estimator reaches no
    reader, and this is not one they can infer from the number.
    """
    ledger = (result.get("extensions") or {}).get("assumption_ledger") or {}
    for entry in ledger.get("assumptions") or ():
        if isinstance(entry, dict) and str(
                entry.get("id")).startswith(_INDEPENDENT_CENSORING):
            return
    _reject(
        f"the assumption ledger carries no {_INDEPENDENT_CENSORING}… entry, "
        f"which is why the curve estimated from the units still standing is "
        f"the survival curve of everyone; a restricted mean shipped without "
        f"it leaves its reader nothing to disagree with"
    )
