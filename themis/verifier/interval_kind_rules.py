"""Which of two objects a pair of endpoints is, where the run decides.

Most pairs of endpoints on this envelope are one thing by virtue of where
they sit: a bounds row's ``ci_lower``/``ci_upper`` is an outer band on a
set, a point estimator's is a sampling interval around a point. Two are
not. A probability of causation and a counterfactual cell each carry ONE
pair of keys holding TWO different objects -- the point's bootstrap
interval where the run identified a point, and a band on the identified
interval where it did not -- and which one came out is a fact about the
run rather than about the slot. ``ci_width_is`` is the word that says so,
and the two narrow with different things, so the word decides what a
reader is told to do next about a number they are weighing.

:mod:`themis.intervals` already declares this. Its ``_BIMODAL`` rows name
exactly these two containers, give them no fixed width, and name
``ci_width_is`` as the field that settles them. Nothing in this package
read that declaration: the renderers do, through ``pair_at``, which is how
a wrong word reaches a reader as a confident sentence about what would
make the interval narrower.

Measured before this existed: on every stored answer carrying a
probability of causation, all three of ``pn``, ``ps`` and ``pns`` could
have the word rewritten to the other one, or removed, and both public
doors said yes. The sibling was held, which is the part worth saying out
loud -- the copy rule compares a deep leaf under its bare name only where
nothing else on the envelope answers to that word, and ``ci_width_is``
answers three times here and once there. That rule is right to decline:
an ambiguity is not a disagreement, and it says so. What was missing is a
reading that does not go through the record at all.

Re-derived rather than read: a point came out or it did not, and that
settles it. This is the recovery :class:`themis.intervals.WidthNotStated`
exists to refuse, and refusing it there is right for the reason it gives
-- a producer recovering the word would be writing a second record of a
fact it already holds. A verifier recomputing it is the opposite act, and
is what every number on this envelope gets.

Silent where the pair is absent. A block with neither endpoint reported
nothing to be either kind of, and the rule that reads this word on the
derivation record is not asked there either -- it sits inside the branch
that runs once an endpoint exists. A word beside no pair is still refused,
because that one says something about an object the answer does not have.
"""
from __future__ import annotations

from collections.abc import Mapping

from .errors import VerificationError
from .rules import _WIDTH_OUTER_BAND, _WIDTH_SAMPLING

_RULE = "run_decided_interval_kind_check"

#: Where a run-decided pair sits on the envelope, and the slot each one is
#: declared at. Restated rather than imported, as every table this package
#: reads is: a check taking the producer's roster would agree with it by
#: construction, and what is being checked is the producer's claim. A test
#: holds this against :data:`themis.intervals.DECLARED`, so the roster
#: cannot go a member stale without saying so.
_WHERE_A_RUN_DECIDES: dict[tuple[str, ...], str] = {
    ("numeric_estimate", "probabilities_of_causation", "pn"):
        "$defs.causationEstimate",
    ("numeric_estimate", "probabilities_of_causation", "ps"):
        "$defs.causationEstimate",
    ("numeric_estimate", "probabilities_of_causation", "pns"):
        "$defs.causationEstimate",
    ("numeric_estimate", "counterfactual_cell"):
        "numeric_estimate.counterfactual_cell",
}

#: The keys the pair, its point and its word are written under. One
#: spelling for all four slots, which is why they are named once.
_LOWER, _UPPER, _POINT, _WORD = "ci_lower", "ci_upper", "point", "ci_width_is"


def _at(result: Mapping, path: tuple[str, ...]) -> object:
    node: object = result
    for step in path:
        if not isinstance(node, Mapping):
            return None
        node = node.get(step)
    return node


def verify_which_object_a_run_decided_pair_is(result: object) -> None:
    """Hold each run-decided pair's word to the run beside it.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` where a block says
    its interval is one kind and the run produced the other, or where a
    block with no interval at all says something about one.
    """
    if not isinstance(result, Mapping):
        return
    for path in _WHERE_A_RUN_DECIDES:
        block = _at(result, path)
        if not isinstance(block, Mapping):
            continue
        where = ".".join(path)
        said = block.get(_WORD)
        if block.get(_LOWER) is None and block.get(_UPPER) is None:
            if said is None:
                continue
            raise VerificationError(
                f"{where} reports no interval at all and says its width is "
                f"{said!r}; the word tells a reader what would make an "
                f"interval narrower, and there is no interval here for it "
                f"to be about",
                rule=_RULE,
            )
        point = block.get(_POINT)
        expected = _WIDTH_SAMPLING if point is not None else _WIDTH_OUTER_BAND
        if said != expected:
            raise VerificationError(
                f"{where} says ci_width_is={said!r} and this run produced "
                f"{expected!r} — the pair is "
                + (f"the bootstrap interval around the point {point!r}"
                   if point is not None
                   else "a band on the identified interval, since no point "
                        "came out")
                + ". The two narrow with different things, so the word "
                  "decides what a reader is told to do next",
                rule=_RULE,
            )
