"""The generic answer slot, against the block it is a restatement of.

``numeric_result`` is where a reader who does not want to know which
estimator ran finds the answer: one number, or one range. It is not a
record of anything — the estimate is already on the envelope, under the
block that produced it — so every number in the slot is the SECOND writing
of a number that is also somewhere else on the same document.

Nothing held the two together. The rule that holds an envelope's numbers
to the derivation record reads the blocks a reader reads a run's own
numbers from, which are ``numeric_estimate`` and ``extensions``; this slot
is neither, and its field names would not reach the record anyway --
``value`` against a step's ``point``, ``interval.low`` against ``lower``.
That is the right shape for that rule and the wrong question for this
slot: what this one restates is not the record but the envelope beside it.

Measured before this existed: on every stored answer where the slot and
the estimate stand together, the number in the slot could be rewritten to
anything at all and both public doors said yes.

Two questions, one per shape the slot has:

- a value beside a headline point is that point. Exactly, not nearly: the
  two are one float written twice, and the only distance a copy may drift
  is none.
- a range is the range of one of the estimate's own blocks. Which block is
  a fact about which route ran, and asking WHICH would be a table of
  routes; asking whether ANY of them carries this pair is the same
  refusal for a forged range and needs no table.

Silent in three places, each because there is nothing to compare rather
than because the leaf is uninteresting. Where the answer carries no
``numeric_estimate``, its numbers live elsewhere and are held there -- a
bounded counterfactual puts them under ``extensions``, and the slot is
then the only copy on the envelope. Where the estimate reports no headline
point, a value beside it is not a second writing of that point and this
says nothing about it. And where no block of the estimate reports a range
at all, a range in the slot has no counterpart here.
"""
from __future__ import annotations

from collections.abc import Mapping

from .errors import VerificationError

_RULE = "answer_slot_restatement_check"


def verify_the_generic_slot_restates_the_answer(result: object) -> None:
    """Hold the generic answer slot to the estimate standing beside it.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` where the number a
    reader takes as the answer is not the number the estimate reports, or
    where the range beside it is a range no block of the answer has.
    """
    if not isinstance(result, Mapping):
        return
    slot = result.get("numeric_result")
    estimate = result.get("numeric_estimate")
    if not isinstance(slot, Mapping) or not isinstance(estimate, Mapping):
        return

    value = slot.get("value")
    point = estimate.get("point")
    if value is not None and point is not None and value != point:
        raise VerificationError(
            f"numeric_result.value is {value!r} and the estimate beside it "
            f"reports {point!r}; the slot is where a reader who does not "
            f"read blocks finds the answer, so the two are one number "
            f"written twice and a reader of one is reading the other",
            rule=_RULE,
        )

    interval = slot.get("interval")
    if not isinstance(interval, Mapping):
        return
    low, high = interval.get("low"), interval.get("high")
    if low is None or high is None:
        return
    ranges = [
        (name, block.get("lower"), block.get("upper"))
        for name, block in estimate.items()
        if isinstance(block, Mapping)
        and block.get("lower") is not None and block.get("upper") is not None
    ]
    if not ranges:
        return
    if any(lower == low and upper == high for _name, lower, upper in ranges):
        return
    raise VerificationError(
        f"numeric_result.interval is ({low!r}, {high!r}) and no block of "
        f"the estimate reports that range — they report "
        + ", ".join(f"{name} ({lower!r}, {upper!r})"
                    for name, lower, upper in sorted(ranges))
        + ". The slot restates one of them, so a range that is none of "
          "them is a range this answer never produced",
        rule=_RULE,
    )
