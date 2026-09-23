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

**The block's own scalars.** Everything above is inside a cell or built
from the cells' curves. The block also reports three numbers about the
SAMPLE — what share of it was censored, when follow-up ended, and which
column carried the event flag — and a weighting that spans the cells rather
than sitting in one. Each is a function of what the cells already record, so
each was the producer's word about its own tables. Whether the cells ARE the
sample is not assumed: they cover the run when their units add up to the
estimate's, the envelope says that for itself, and where they do not the
share has a denominator nothing here can see. The last observed time is held
either way, because a subset's maximum cannot exceed the whole's.

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
    a risk table that does not account for its own losses, two arms
    standardised over different strata, a block-level scalar that is not
    what its own cells add up to, an event column the run never read, or an
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
    estimate = result.get("numeric_estimate")
    by_arm: dict[bool, list[tuple[float, float, float]]] = {True: [], False: []}
    layers: dict[bool, dict[tuple, float]] = {True: {}, False: {}}
    events = units = censored = 0
    last_seen = 0.0
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
        if stratum in layers[arm]:
            _reject(
                f"{where} is a second cell for stratum {list(stratum)} in "
                f"the {'treated' if arm else 'control'} arm; the "
                f"standardisation weights each stratum once, so a stratum "
                f"recorded twice is one weighted twice"
            )
        layers[arm][stratum] = weight
        by_arm[arm].append((weight, rmst, variance))
        events += sum(row[2] for row in table)
        units += n
        censored += sum(row[3] for row in table)
        last_seen = max(last_seen, table[-1][0])

    _agree(events, _count(block.get("n_events"), "survival_curve.n_events"),
           "the events across every cell")
    _the_arms_standardise_over_one_set(layers)
    _the_block_against_its_cells(block, estimate, units, censored, last_seen)

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

    if isinstance(estimate, dict):
        _agree(means[True] - means[False],
               _number(estimate.get("point"), "numeric_estimate.point"),
               "the answer against the difference of the two arms' means")
        _check_the_interval(estimate, variance)
    _check_the_premise_reached_the_reader(result)


def _the_arms_standardise_over_one_set(layers: dict) -> None:
    """The strata the difference is taken over, which are one set.

    A standardised difference is ``Σ_z w(z)·[m(1,z) − m(0,z)]``: one set of
    strata, one weight apiece, and the arms differ only in which mean is
    read off inside them. That the weights within an arm sum to one is
    already held above and does not reach this — two arms carrying DIFFERENT
    strata, each arm's weights summing to one, pass it, and the difference
    they report is then between two populations rather than within one.

    A weight is a stratum's share of the sample, which is a fact about the
    stratum and not about the arm, so the two arms' weights for it are one
    number recorded twice.
    """
    treated, control = layers[True], layers[False]
    if set(treated) != set(control):
        odd = sorted(list(s) for s in set(treated) ^ set(control))
        _reject(
            f"survival_curve.cells: the arms are standardised over different "
            f"strata — {odd} appears in one arm and not in the other; a "
            f"standardised difference weights ONE set of strata, so two arms "
            f"weighted over two sets are a difference between two populations"
        )
    for stratum in sorted(treated):
        _agree(treated[stratum], control[stratum],
               f"survival_curve.cells: the weight of stratum "
               f"{list(stratum)}, which is that stratum's share of the "
               f"sample whichever arm's mean is read off inside it")


def _the_block_against_its_cells(block: dict, estimate, units: int,
                                 censored: int, last_seen: float) -> None:
    """The scalars the block reports about the sample its cells hold.

    Whether those cells ARE the sample is asked rather than assumed. The
    share is over everyone the run read; the cells are per (stratum, arm)
    and cover the run exactly when their units add up to the estimate's,
    which the envelope states for itself. Where they do not add up, the
    share's denominator is one nothing here can see, and a rule that divided
    by the cells anyway would refuse an honest run for being partial.

    The last observed time needs no such condition in one direction: it is
    the largest time anywhere in the sample, and the cells are part of the
    sample, so it is not before the largest time they record. Where they are
    the whole sample it is exactly that time.
    """
    size = estimate.get("sample_size") if isinstance(estimate, dict) else None
    whole = isinstance(size, int) and not isinstance(size, bool) \
        and size == units

    if "follow_up_ends" in block:
        ends = _number(block["follow_up_ends"],
                       "survival_curve.follow_up_ends")
        if ends < last_seen - _TOL:
            _reject(
                f"survival_curve.follow_up_ends is {ends!r} and a cell of "
                f"this block records an observation at {last_seen!r}; "
                f"follow-up ends when the last unit was last seen, so it is "
                f"not before a time the block itself carries"
            )
        if whole:
            _agree(last_seen, ends,
                   "survival_curve.follow_up_ends against the last time any "
                   "of its cells records, the cells holding every unit the "
                   "estimate was computed on")

    if "censored_share" in block and whole:
        _agree(censored / units,
               _number(block["censored_share"],
                       "survival_curve.censored_share"),
               "survival_curve.censored_share against the units its own "
               "cells record leaving without the event")

    _the_event_column_was_one_the_run_read(block, estimate)


def _the_event_column_was_one_the_run_read(block: dict, estimate) -> None:
    """The column that says whether a recorded time is an event.

    The whole curve rests on which units were censored, and the block names
    the column that decides it. Two things are asked of that name, and they
    are one question about where the fact came from. It has to be a column
    the run read — the answer lists them — because a reader sent to a column
    nobody opened cannot check the one fact the curve cannot be re-read
    without. And it has to be a column the run had not already spent: the
    time the estimate is about and the arm it compares are named on the same
    envelope, and neither of them can also be the flag saying whether a
    recorded time is an event, since one is a duration and the other is the
    contrast.

    The adjustment set is deliberately not asked about. A stratifying column
    doubling as the event flag would be a badly specified run rather than an
    inconsistent envelope, and refusing it here would be this module ruling
    on a choice it has no second record of.
    """
    name = block.get("event_indicator")
    columns = estimate.get("data_columns") if isinstance(estimate, dict) \
        else None
    if not isinstance(name, str) or not isinstance(columns, list):
        return
    if not all(isinstance(c, str) for c in columns):
        return
    if name not in columns:
        _reject(
            f"survival_curve.event_indicator names {name!r} and the run read "
            f"{sorted(columns)}; the column that decides which times are "
            f"events is the one fact the curve cannot be re-read without, "
            f"and a reader sent to a column nobody opened cannot check it"
        )
    for role in ("outcome", "treatment"):
        if name == estimate.get(role):
            _reject(
                f"survival_curve.event_indicator names {name!r} and the "
                f"estimate's {role} is the same column; the recorded time "
                f"and the arm are what the flag is read ALONGSIDE, so a "
                f"column that is both is a curve read off itself"
            )


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
