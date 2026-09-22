"""A composite is its weakest source, and the mark says which one that is.

Two numbers reach a reader together. The answer's ``confidence`` is how far
this run trusts what it was given, and ``confidence_sources`` is the list it
was taken over -- one entry per slot the answer rests on, each with the
statement behind it. What binds them is declared where the pair is:
:class:`themis.types.ConfidenceSource` says the composite is ``min`` across
the non-None slot confidences, and its ``is_weakest`` field says, in as many
words, true iff that source's confidence equals the composite min.

Both halves were the producer's word. The only rule in this package with
"confidence" in its name is about the LEVEL an interval is stated at -- a
different fact wearing the same letters, and its own docstring says so --
and nothing anywhere read the sources. Measured before this existed: on
every stored answer that carries the pair, the composite could be rewritten
to any number at all, a source's confidence to any other, and a weak link's
mark flipped off, and both public doors said yes. The number a reader is
shown as "how far to trust this" is a number, and every number that reaches
a reader is re-derived here rather than believed; this one was not.

The re-derivation is arithmetic over what the envelope already carries, so
there is no second opinion to form and nothing to import: the minimum of the
recorded confidences is the composite, and a source is a weak link exactly
when it sits at that minimum. A tie makes every source at the minimum a weak
link, which is what the flag means and what the producer writes.

EXACTLY equal, not nearly. The producer's own comparison is ``==`` against a
value it copied from one of the sources, so the composite is one of the
recorded numbers rather than a computation over them. A tolerance here would
mark a source weakest that the producer did not -- two sources a hair apart,
one flagged and one not -- and refuse an honest answer for a difference that
is real.

Silent on two things, both on purpose. A composite standing alone, with no
sources beside it, is not an envelope this system writes: the composite of
nothing is None, and the one pass that writes either field writes them
together. A rule refusing that shape would be asserting something about an
answer no run produces. And the ``slot_label`` and ``source`` beside each
number are NAMES -- which slot, whose statement -- held by nothing here,
because what holds a name is the document it was copied from rather than
arithmetic over its neighbours.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard

from .errors import VerificationError

_RULE = "confidence_source_check"


def _a_number(value: object) -> TypeGuard[float]:
    """A confidence is a number, and ``True`` is not one.

    ``bool`` is an ``int`` in this language, so a flag left where a
    confidence goes would otherwise compare as 0 or 1 and pass for a
    probability.
    """
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def verify_the_composite_is_its_weakest_source(result: object) -> None:
    """Hold the composite confidence to the sources it is taken over.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` where the number a
    reader is shown is not the weakest of the numbers beside it, or where
    the mark pointing at the weak link points somewhere else.
    """
    if not isinstance(result, Mapping):
        return
    composite = result.get("confidence")
    sources = result.get("confidence_sources")
    if not _a_number(composite):
        return
    if not isinstance(sources, Sequence) or isinstance(sources, (str, bytes)):
        return
    rows = [row for row in sources if isinstance(row, Mapping)]
    if not rows or len(rows) != len(sources):
        return
    values: list[float] = []
    for row in rows:
        value = row.get("confidence")
        if not _a_number(value):
            return
        values.append(value)

    weakest = min(values)
    if composite != weakest:
        raise VerificationError(
            f"the answer says its confidence is {composite!r} and the "
            f"weakest of the {len(values)} source(s) it is taken over is "
            f"{weakest!r}; a composite is the minimum across the slots the "
            f"answer rests on, so a reader is told this answer is trusted "
            f"further than its weakest input, or less far than any input "
            f"says",
            rule=_RULE,
        )
    for row in rows:
        marked = row.get("is_weakest")
        truly = row.get("confidence") == weakest
        if bool(marked) is truly and isinstance(marked, bool):
            continue
        raise VerificationError(
            f"the source {row.get('slot_label')!r} carries a confidence of "
            f"{row.get('confidence')!r} and is marked is_weakest="
            f"{marked!r}, while the composite these were taken over is "
            f"{weakest!r}; that mark is what a reader follows to the link "
            f"the answer is weakest at, and following it here leads to a "
            f"slot that is not one, or past the slot that is",
            rule=_RULE,
        )
