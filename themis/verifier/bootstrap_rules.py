"""What an interval is a quantile of, held to what its block says it is.

A percentile bootstrap asks for B replicates and gets fewer whenever a refit
fails on one. Skipping such a draw is correct — the interval IS over the
evaluable draws — and it is invisible: an interval over 962 draws and one
over 1000 are the same two numbers on the page. The block exists so the
reader can tell them apart, which makes the block's own honesty the thing
worth auditing, because a wrong count reads exactly like a right one.

Three claims, and each fails silently on its own:

- **The losses add up.** ``requested - used`` draws did not survive, and
  ``discarded`` says what took them. A block whose reasons total less than
  its losses has draws nobody accounted for, and the gap looks the same as
  no gap. This is the one that catches a loop counting a drop it forgot to
  file, or filing one it did not drop.
- **The reasons are species.** Every key is a registered refusal, or the
  one name reserved for a draw lost to something carrying no species. A
  free-text key is a reason with no vocabulary behind it, and the surfaces
  that key on a species — the share of draws refuting a declared
  monotonicity, above all — read it as absence.
- **An interval rests on more than one draw.** ``numpy.quantile`` of a
  single value returns that value, so a "95% interval" taken over one
  surviving draw is a point printed twice with a confidence level beside
  it. Where an interval is reported, at least two draws answered.

What it deliberately does NOT audit: whether the interval is numerically
right. Re-deriving a percentile bootstrap needs the raw data and a rerun of
the estimator, which is the data-refit ceiling every numeric verifier here
stops at. What is checkable is the record, and the record is where this
failure hid.

The ``kind`` / ``cluster_column`` half of the block is audited by
:mod:`themis.verifier.cluster_inference_rules`, against the run's own
resolved column — a two-source agreement this module cannot make, since
everything here is internal to one block.

**Independence pin:** this module MUST NOT import from
``themis.estimation`` or ``themis.output``. It imports the refusal
vocabulary, which is the envelope's and neither producer's nor consumer's,
and restates every other constant it checks.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NoReturn

from ..refusals import Refusal
from .errors import VerificationError

_RULE = "bootstrap_draws_check"

#: The floor an interval rests on. Restated rather than imported, for the
#: reason in the header: a floor read from the producer's own constant
#: agrees with the producer by construction.
FEWEST_DRAWS = 2

#: The one key that is not a species — where a loop caught something that
#: carried none. Restated for the same reason.
UNNAMED = "unclassified"


def _reject(where: str, message: str) -> NoReturn:
    raise VerificationError(f"{where}: {message}", rule=_RULE)


def check_bootstrap_record(
    record: object, *, where: str, has_interval: bool,
) -> None:
    """Hold one ``bootstrap`` block to its own arithmetic.

    ``where`` names the block's place on the envelope, so a rejection says
    which of several a result can carry. ``has_interval`` is whether the
    thing this block belongs to reported one — the floor applies only
    there, because a loop can legitimately end with one usable draw and
    report no interval at all.

    No-op when there is no block. Raises :class:`VerificationError` on a
    malformed count, on losses that do not add up, on a discard reason
    outside the closed vocabulary, or on an interval resting on fewer
    draws than a quantile can be taken over.
    """
    if record is None:
        return
    if not isinstance(record, Mapping):
        _reject(where, f"bootstrap must be an object; got {type(record).__name__}")

    requested = _count(record, "requested", where)
    used = _count(record, "used", where)
    if requested < 1:
        _reject(where, f"bootstrap.requested is {requested}; a block that "
                       "exists says a bootstrap ran, and a run of no "
                       "replicates is said by having no block")
    if used > requested:
        _reject(where, f"bootstrap.used is {used} of {requested} requested — "
                       "more draws were usable than were drawn")

    discarded = record.get("discarded")
    if discarded is None:
        discarded = {}
    elif not isinstance(discarded, Mapping):
        _reject(where, "bootstrap.discarded must be an object mapping a "
                       "refusal species to how many draws it ate; got "
                       f"{type(discarded).__name__}")

    _check_species(discarded, where)
    _check_the_losses_add_up(requested, used, discarded, where)

    if has_interval and used < FEWEST_DRAWS:
        _reject(where, f"an interval is reported over {used} usable "
                       f"draw{'' if used == 1 else 's'}. A quantile of a "
                       "single value is that value, so the two endpoints "
                       "are one number printed twice with a confidence "
                       "level beside it")


def _count(record: Mapping, key: str, where: str) -> int:
    value = record.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        _reject(where, f"bootstrap.{key} must be an integer; got {value!r}")
    if value < 0:
        _reject(where, f"bootstrap.{key} is {value}")
    return value


def _check_species(discarded: Mapping, where: str) -> None:
    """Every reason is a name this build knows."""
    known = {str(member) for member in Refusal} | {UNNAMED}
    stray = sorted(str(k) for k in discarded if str(k) not in known)
    if stray:
        _reject(where, f"bootstrap.discarded names {stray!r}, which "
                       "no registered refusal species matches. A reason "
                       "outside the vocabulary reaches no reader: the "
                       "surfaces that act on one — the share of draws "
                       f"refuting a declared monotonicity is "
                       f"{Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE!s} — "
                       "look it up by species and find nothing")
    for key, count in discarded.items():
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            _reject(where, f"bootstrap.discarded[{str(key)!r}] is {count!r}; "
                           "a reason that ate no draws is said by not "
                           "being there")


#: Where a ``bootstrap`` block can sit, and what carries the interval it
#: describes. One entry per LOOP, not per estimator: the margin table and
#: the ratio split each run their own resampling beside the estimate's,
#: keep their own counts, and would be audited against the wrong interval
#: if they shared its entry.
#:
#: A tuple rather than a walk over every ``bootstrap`` key anywhere,
#: because the floor needs to know which interval belongs to which block,
#: and a walk that guessed would grow a rule nobody declared.
_SITES = (
    ("numeric_estimate", "numeric_estimate"),
    ("numeric_estimate.acr_decomposition", "acr_decomposition"),
    ("numeric_estimate.four_way_ratio", "four_way_ratio"),
)


def verify_bootstrap_records(result: object) -> None:
    """Audit every ``bootstrap`` block one result carries.

    Every one, because they are separate loops over separate quantities:
    auditing the estimate's says nothing about the margin table's, and the
    margin table is where a dead first stage eats draws the estimate's own
    loop never notices.

    Returns ``None`` on accept; raises :class:`VerificationError` on the
    first block that does not add up.
    """
    if not isinstance(result, Mapping):
        return
    estimate = result.get("numeric_estimate")
    if isinstance(estimate, Mapping):
        for path, key in _SITES:
            block = estimate if key == "numeric_estimate" else estimate.get(key)
            if not isinstance(block, Mapping):
                continue
            check_bootstrap_record(
                block.get("bootstrap"), where=path,
                has_interval=_carries_an_interval(block, key),
            )
    for row in result.get("bounds_results") or ():
        if isinstance(row, Mapping):
            check_bootstrap_record(
                row.get("bootstrap"),
                where=f"bounds_results[{row.get('method')!r}]",
                has_interval=row.get("ci_lower") is not None
                or row.get("ci_upper") is not None,
            )
    if isinstance(estimate, Mapping):
        _check_the_refuted_share(estimate)


def _check_the_refuted_share(estimate: Mapping) -> None:
    """The cell's refuted share, re-derived from the record it comes from.

    The one discarded count with a reader-facing meaning, and the one that
    travels DERIVED — the cell is copied into ``extensions`` where no
    estimate sits beside it, so the share has to be a field. A field
    derived from another field is a second author unless somebody holds
    the two equal, and this is where.

    Re-derived rather than read: the arithmetic is restated here from what
    the share means, so a producer that changed its denominator to
    ``requested`` — turning a refutation rate into a diluted one, on the
    same two numbers — is caught rather than agreed with.
    """
    cell = estimate.get("counterfactual_cell")
    if not isinstance(cell, Mapping):
        return
    said = cell.get("monotonicity_refuted_share")
    record = estimate.get("bootstrap")
    discarded = (record.get("discarded") or {}) if isinstance(record, Mapping) else {}
    lost = discarded.get(str(Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE)) or 0
    answered = (record.get("used") or 0 if isinstance(record, Mapping) else 0) + lost
    owed = (lost / answered) if lost and answered else None

    where = "numeric_estimate.counterfactual_cell"
    if owed is None:
        if said is not None:
            _reject(where, f"monotonicity_refuted_share is {said!r}, and no "
                           "draw was discarded as infeasible under the "
                           "declared monotonicity. A share standing where "
                           "nothing was refuted tells a reader their data "
                           "argues against an assumption it never touched")
        return
    if said is None:
        _reject(where, f"{lost} of {answered} answering draws were infeasible "
                       "under the declared monotonicity and "
                       "monotonicity_refuted_share is null. That share is "
                       "the nearest thing to a test of an assumption "
                       "usually called untestable, and a null reads as "
                       "nothing to report")
    if not isinstance(said, (int, float)) or abs(float(said) - owed) > 1e-12:
        _reject(where, f"monotonicity_refuted_share is {said!r}; {lost} of "
                       f"{answered} answering draws were infeasible, which "
                       f"is {owed!r}. The denominator is the draws that "
                       "ANSWERED and not the draws requested — a draw lost "
                       "to a thin stratum was not a vote against "
                       "monotonicity, and counting it as one reports a "
                       "refutation rate lower than the data's")


def _carries_an_interval(block: Mapping, key: str) -> bool:
    """Whether the thing this block describes reported an interval.

    Asked per site because the endpoints live in a different place on each
    — the estimate's own pair, a per-margin pair, a per-component band —
    and the floor is about an interval that was REPORTED, not about a loop
    that happened to end with one draw and said nothing.
    """
    if key == "acr_decomposition":
        return any(
            isinstance(m, Mapping) and m.get("ci_upper") is not None
            for m in block.get("margins") or ()
        )
    if key == "four_way_ratio":
        return any(
            isinstance(v, Mapping) and v.get("ci_upper") is not None
            for v in block.values()
        )
    return block.get("ci_lower") is not None or block.get("ci_upper") is not None


def _check_the_losses_add_up(
    requested: int, used: int, discarded: Mapping, where: str,
) -> None:
    lost = requested - used
    filed = sum(int(v) for v in discarded.values())
    if filed == lost:
        return
    _reject(
        where,
        f"{lost} of {requested} draws did not survive and "
        f"bootstrap.discarded accounts for {filed}. The counts are the "
        "whole content of this block: unaccounted losses look exactly like "
        "no losses, and reasons totalling more than the losses mean one "
        "draw was filed twice — either way the reader is being told a "
        "number that is not the one the interval rests on"
    )
