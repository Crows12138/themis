"""One run, one confidence level, and it is the one this system draws.

A pair of endpoints and the level they were computed at are one statement.
``[0.326, 0.426]`` says something different at 50% than at 95%, and the
whole of the difference is how much of a reader's belief those two numbers
are entitled to. The envelope wrote the level in seven slots, left some
twenty more pairs of endpoints to inherit it — a mediation answer shows
four intervals under one level — and nothing asked what it was.

Not for want of asking ABOUT it. Eight places asked whether it was a number
in (0, 1): a type check in the shape of a claim. Six answer shapes did
refuse a forged level, and all six for the same accidental reason — their
level enters an arithmetic the envelope can redo, since the Anderson-Rubin
inversions take an F or chi-square quantile at it and SIMEX takes a normal
one, so moving it breaks an identity that was being checked for its own
sake. On the other thirty-eight nothing recomputes with it and it could be
moved anywhere at all, including to a different value in one block than in
the block beside it, which is the forgery that makes one interval look
tighter than the ones it is printed next to.

**No stronger hold exists, and that is a fact about the object.** Where an
interval comes from a percentile bootstrap the level chose two quantiles of
a distribution nobody kept, and nothing on the envelope inverts to it.
Where it comes from a normal approximation the multiplier would give it
back — and the two answer shapes that record a standard error report no
interval beside it. A caller cannot ask for another level either:
``themis.estimate`` takes every other run-level inference input and has no
slot for this one. So it is a line this system draws, and the recipe for
those is already settled next door in ``fitted_diagnostic_rules``: restate
the constant, and let a test pin the two copies equal.

**The question is put wherever the word appears**, rather than at the slots
that carry it today, because which blocks name a level is a fact about the
producer's layout and the next one should arrive here by being written. A
step's inputs prefix the sub-computation they belong to (``ar_ci_level``),
and a prefix is not a different fact.

**And the other half of one sentence: an interval names its level.** That
was being said too — thirteen times, once inside each route's own rule,
each time as ``0 < ci_level < 1``, which is a type in the shape of a claim
and is also how thirteen authors each managed not to ask the question above.

It is asked here of the RUN, not of the block. Written first as "a pair of
endpoints has a level at or above it in the envelope", it refused twelve
honest answers: a causation route records its bootstrap interval inside a
derivation step, and ``derivation`` is a SIBLING of ``numeric_estimate``,
so nothing on that branch names a level and the answer's own level is not
above it. Which is this same disease one layer up — whether an interval was
covered would have been a fact about which branch its producer wrote it on.
A level is a fact about the run: one run makes its confidence statements at
one level, and ``estimation_context`` is where the run's inference inputs
are recorded once, before any estimator consumes them. So the question is
whether the run said, and every block that names a level is answered by the
half above.

**Independence pin:** this module MUST NOT import from
``themis.estimation`` or ``themis.intervals``. A verifier reading the
producer's own constant would agree with it by construction and hold
nothing; two copies and one test pinning them equal is what makes moving
this line something somebody declares rather than something that happens.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "confidence_level_check"

#: RESTATED, not imported — see the independence pin above.
_LEVEL = 0.95

#: How a block spells it. Read off the end of the key rather than listed,
#: so that a block naming its level under a new prefix is asked without
#: anybody remembering to add it.
_SUFFIX = "ci_level"


#: What a pair of endpoints that IS a confidence statement is spelled.
#: An identified set spells its own ``lower``/``upper`` or
#: ``lower_value``/``upper_value`` and has no level to name — at any sample
#: size it is the set the premises leave — so these two names are what keep
#: the question off the pairs it must not be put to. A bounds row carries
#: both kinds and is asked about exactly one of them.
_ENDPOINTS = ("ci_lower", "ci_upper")

#: Where a run records the inputs it was given, and so where it records
#: this one.
_CONTEXT = "estimation_context"


def _num(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _walk(node, path=()):
    """Every level named on this envelope, and every interval on it.

    One walk for both halves, because they are one sentence and a second
    walk would be a second place for a block to be missed from.
    """
    if isinstance(node, dict):
        if all(_num(node.get(key)) for key in _ENDPOINTS):
            yield "interval", ".".join(map(str, path)) or "the answer", node
        for key, value in node.items():
            if isinstance(key, str) and key.endswith(_SUFFIX):
                yield "level", ".".join(map(str, path + (key,))), value
            else:
                yield from _walk(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk(value, path + (f"[{index}]",))


def _the_level(where: str, value) -> None:
    if not _num(value):
        raise VerificationError(
            f"{where} is {value!r}; a confidence level is the number an "
            f"interval's coverage is stated at, and this is not a number",
            rule=_RULE,
        )
    if float(value) != _LEVEL:
        raise VerificationError(
            f"{where} is {value!r} and every confidence statement this "
            f"system makes is made at {_LEVEL}; a run cannot be asked for "
            f"another level, so an interval reported at this one was either "
            f"computed at {_LEVEL} and is being described as narrower "
            f"evidence than it is, or sits beside neighbours that are not "
            f"comparable with it",
            rule=_RULE,
        )


def verify_confidence_level(result: dict) -> None:
    """The run names its level, and every level named is that one.

    Returns ``None`` on accept; raises ``VerificationError`` naming the slot
    and what a reader would have been told.
    """
    if not isinstance(result, dict):
        return
    context = result.get(_CONTEXT)
    said = context.get(_SUFFIX) if isinstance(context, dict) else None
    intervals = []
    for kind, where, value in _walk(result):
        if kind == "level":
            _the_level(where, value)
        else:
            intervals.append((where, value))
    if intervals and said is None:
        where, node = intervals[0]
        raise VerificationError(
            f"{where} reports [{node['ci_lower']}, {node['ci_upper']}] and "
            f"{_CONTEXT} does not say what level this run states its "
            f"confidence at; two numbers with a comma between them are not a "
            f"confidence statement until somebody says how often a pair made "
            f"this way covers, and the level is a fact about the run rather "
            f"than about the branch an interval happens to sit on",
            rule=_RULE,
        )
