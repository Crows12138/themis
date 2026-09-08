"""What an interval is a quantile of, held to what its block says it is.

A percentile bootstrap asks for B replicates and gets fewer whenever a refit
fails on one. Skipping such a draw is correct — the interval IS over the
evaluable draws — and it is invisible: an interval over 962 draws and one
over 1000 are the same two numbers on the page. The block exists so the
reader can tell them apart, which makes the block's own honesty the thing
worth auditing, because a wrong count reads exactly like a right one.

Three claims a block makes about ITSELF, and each fails silently on its own:

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

**And a fifth, which is the one the four above cannot ask.** Every claim
so far begins at a block, so a loop that left NO block is held by nobody:
the count that is not there adds up, the species that are not there are
all registered, the floor that is not there is cleared, and the interval
printed beside them rests on whatever number the reader supplies. It is
askable because the estimator's sentence and this block are one object's
two statements — the sentence is written where enough replicates survived
for an interval to be reportable at all, the block wherever a loop ran —
so an answer saying it resampled and showing nothing contradicts itself.
One direction only: a block with no sentence is the honest shape of a loop
that lost too many draws to let its estimator claim anything.

What it deliberately does NOT audit: whether the interval is numerically
right. Re-deriving a percentile bootstrap needs the raw data and a rerun of
the estimator, which is the data-refit ceiling every numeric verifier here
stops at. What is checkable is the record, and the record is where this
failure hid.

The ``kind`` / ``cluster_column`` half of the block is audited by
:mod:`themis.verifier.cluster_inference_rules`, against the run's own
resolved column.

**And ``requested`` is held against the run too, here.** It is the one
number in this block that did not come from this block: the run records
what it was asked for, the estimator's loop records what it drew, and for
a long time nothing put the two side by side — which is a description of
this module's scope offered as if it were a reason, since the three claims
above are internal to one block only because nobody had asked the fourth.
The count reaches an estimator under the name its parameter is spelled, so
a knob spelled differently is not a wire that breaks but one that was never
drawn: two mediation loops called it something else, and every mediation
interval this system reported stood on two hundred draws — under a caller
who asked for five hundred, and under one who asked for none at all, which
this system documents as the way to skip the interval. Nothing was
inconsistent inside any of those blocks. The reader was simply told a
number about a loop nobody had ordered.

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

#: Where a run records what it was asked for, and under what name.
_CONTEXT = "estimation_context"
_ASKED = "ci_bootstrap"

#: What an estimator says about an interval it MADE by resampling — the
#: sentence, as opposed to the block. RESTATED, not imported, for the reason
#: in the header; a test reads it off the producer so the two copies cannot
#: drift into describing different sentences.
_DECLARES_A_RESAMPLED_INTERVAL = "ci_via_percentile_bootstrap"

#: A block that runs a resampling loop of its OWN, and the ceiling this
#: build puts on it. Absent from here means a block draws what the run
#: asked for, which is every other one.
#:
#: RESTATED, not imported — see the independence pin. A ceiling read from
#: the producer's own constant agrees with the producer by construction,
#: and a build that quietly halved this one would be agreed with. Two
#: copies and one test pinning them equal is what makes moving it
#: something somebody declares.
CEILINGS: dict[str, int] = {"four_way_ratio": 200}

#: Why that block has one. Quoted in the refusal, so the reason has a
#: reader and cannot drift into being true of no block.
CEILING_BECAUSE: dict[str, str] = {
    "four_way_ratio":
        "it is a second double-model bootstrap beside the estimate's own, "
        "and a supplementary audit block should not silently cost a full "
        "double fit per draw the run asked for",
}


def _check_every_ceiling_says_why() -> None:
    """Both directions, at import. A ceiling with no reason is a number
    somebody will read as arbitrary and move; a reason with no ceiling is
    a sentence about a block that no longer departs."""
    silent = sorted(set(CEILINGS) - set(CEILING_BECAUSE))
    if silent:
        raise RuntimeError(
            f"{silent} take fewer draws than the run asked for and say "
            f"nothing about why; add the occasion to "
            f"themis.verifier.bootstrap_rules.CEILING_BECAUSE")
    stale = sorted(set(CEILING_BECAUSE) - set(CEILINGS))
    if stale:
        raise RuntimeError(
            f"{stale} give a reason for a ceiling they no longer have; "
            f"remove the row from "
            f"themis.verifier.bootstrap_rules.CEILING_BECAUSE")


_check_every_ceiling_says_why()


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
                has_interval=_carries_an_interval(block),
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
    _check_every_count_is_the_runs(result)
    _check_a_declared_loop_left_its_record(result)


def _counts(node: object, under: str = ""):
    """Every resample count on one result, and the block it belongs to.

    A walk rather than the tuple above, and the difference is what the
    two questions need. The floor has to know which interval a block
    describes, so it asks at sites it can name. A count needs no
    interval: it is the run's number wherever it appears, so a block
    written after this is asked by being written rather than by somebody
    remembering to list it.
    """
    if isinstance(node, Mapping):
        record = node.get("bootstrap")
        if isinstance(record, Mapping) and "requested" in record:
            yield under, f"{under or 'the result'}.bootstrap", record
        for key, value in node.items():
            if key != "bootstrap":
                yield from _counts(value, str(key))
    elif isinstance(node, (list, tuple)):
        for value in node:
            yield from _counts(value, under)


def _check_every_count_is_the_runs(result: Mapping) -> None:
    """No interval rests on a number of draws this run did not ask for.

    The one claim in the block that reaches outside it. No-op where the
    run recorded no ask — a fragment audited on its own is not a run, and
    refusing it would make this rule a statement about how the caller
    assembled their test rather than about the answer.
    """
    context = result.get(_CONTEXT)
    if not isinstance(context, Mapping):
        return
    asked = context.get(_ASKED)
    if isinstance(asked, bool) or not isinstance(asked, int):
        return
    for block, where, record in _counts(result):
        got = record.get("requested")
        ceiling = CEILINGS.get(block)
        owed = asked if ceiling is None else min(asked, ceiling)
        if got == owed:
            continue
        because = (
            f", and {block} takes at most {ceiling} of them because "
            f"{CEILING_BECAUSE[block]}" if ceiling is not None else "")
        _reject(
            where,
            f"the interval stands on {got!r} replicates and "
            f"{_CONTEXT}.{_ASKED} says this run asked for {asked!r}"
            f"{because}. A reader is told an interval was taken over "
            f"{record.get('used')!r} of {got!r} resamples, so a count the "
            f"run did not ask for is a loop nobody ordered, described to "
            f"them as the one they did"
        )


def _any_record(node: object) -> bool:
    """Whether one estimate carries a ``bootstrap`` block anywhere under it.

    Presence, which is why this is not :func:`_counts`: that walk skips a
    block with no ``requested`` because it is asking what a count is, and a
    block missing a field is still a block. The question here is whether
    the loop left anything at all, and a walk rather than a site list
    because a decomposition puts its loop under a block of its own.
    """
    if isinstance(node, Mapping):
        if isinstance(node.get("bootstrap"), Mapping):
            return True
        return any(_any_record(value) for key, value in node.items()
                   if key != "bootstrap")
    if isinstance(node, (list, tuple)):
        return any(_any_record(value) for value in node)
    return False


def _check_a_declared_loop_left_its_record(result: Mapping) -> None:
    """A loop the estimator says it ran owes the block that describes it.

    The side every other check in this package begins on the far end of,
    and the two in :mod:`themis.verifier.cluster_inference_rules` with it:
    all of them start AT a block and hold it to its own arithmetic, to the
    run's count, or to what the estimator declared. A loop that left no
    block is therefore audited by nobody — the count that is not there adds
    up, the species that are not there are all registered, the floor that
    is not there is cleared, and the interval printed beside them rests on
    whatever number the reader supplies.

    Askable because the sentence and the block are one object's two
    statements: the estimator writes the sentence when its loop drew enough
    replicates for an interval to be reportable at all, and the block
    whenever a loop ran, so the sentence cannot be true of an answer
    carrying no block. Only that direction — a block with no sentence is
    the honest shape of a loop that ran and lost too many draws to let its
    estimator claim anything.

    Asked of the estimate, because that is where the sentence is written:
    the thirty-odd families all append it to the estimate's own
    assumptions, and the routes that fill a bounds row instead never write
    it, so there is no second pairing here going unasked. A decomposition
    describes its second loop in the same flat list, so this asks for A
    block rather than one per loop — the same reach the pairing one module
    over has, and unavailable for the same reason: one list, two loops.
    """
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, Mapping):
        return
    said = [str(item) for item in (estimate.get("assumptions") or ())]
    if _DECLARES_A_RESAMPLED_INTERVAL not in said:
        return
    if _any_record(estimate):
        return
    _reject(
        "numeric_estimate",
        f"the estimator declares {_DECLARES_A_RESAMPLED_INTERVAL!r} and no "
        f"bootstrap block sits anywhere on the estimate. The sentence says "
        f"an interval was made by resampling and is written only where "
        f"enough replicates survived to report one, so the loop it "
        f"describes ran — and every claim this module makes about such a "
        f"loop is a claim about the block, which means an interval with no "
        f"block is the one shape where a reader is told how the interval "
        f"was made and nothing can be checked about it"
    )


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


def _runs_its_own_loop(value: object) -> bool:
    """Whether this sub-block records a bootstrap of its own."""
    return (isinstance(value, Mapping)
            and isinstance(value.get("bootstrap"), Mapping))


def _carries_an_interval(block: object) -> bool:
    """Whether the loop this stamp belongs to reported an interval.

    The floor is about an interval that was REPORTED, not about a loop that
    happened to end with one draw and said nothing — so the question is
    where the endpoints are, and they are wherever the block puts them.
    Descends for that reason, and stops at any sub-block carrying a stamp of
    its own: those endpoints rest on a SECOND loop and are audited under its
    record, so counting them here would make one loop's floor fire on
    another loop's interval.

    It used to be a table keyed on the block's name — the estimate's own
    pair, ACR's per-margin pairs, the four-way ratio's per-component ones,
    and the top pair as the default. A table is complete only while somebody
    remembers to extend it, and this one's default was already wrong for
    every answer whose endpoints all nest: a clustered mediation result
    carries twenty-two of them and no top-level pair at all, so a stamp
    saying one draw survived passed the floor beside all twenty-two.
    """
    if isinstance(block, Mapping):
        for name, value in block.items():
            if name in ("ci_lower", "ci_upper"):
                if value is not None:
                    return True
            elif name == "bootstrap":
                continue                       # this block's own record
            elif _runs_its_own_loop(value):
                continue                       # a second loop, audited there
            elif _carries_an_interval(value):
                return True
    elif isinstance(block, list):
        return any(_carries_an_interval(v) for v in block
                   if not _runs_its_own_loop(v))
    return False


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
