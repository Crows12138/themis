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

Silent on one thing, on purpose. A composite standing alone, with no
sources beside it, is not an envelope this system writes: the composite of
nothing is None, and the one pass that writes either field writes them
together. A rule refusing that shape would be asserting something about an
answer no run produces.

The ``slot_label`` and ``source`` beside each number are NAMES -- which
slot, whose statement -- and what holds a name is the document it was
copied from rather than arithmetic over its neighbours. That document is
the program, and the second rule here reads it: every row names a slot the
program annotates, spelled the way the producer spells it, and carries
THAT statement's confidence and its source.

What the second rule does not hold is WHICH slots got a row. For an edge
that is the data-gap classifier's reading of what the answer rests on,
which the producer calls rather than restates; a rule re-deriving the
membership would hand that reading back to itself, which is a copy and not
a second opinion. So a row that is there is held to the program, and a row
that is missing is the structural question, which has its own file.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TypeGuard

from .errors import VerificationError

_RULE = "confidence_source_check"
_NAMES_RULE = "confidence_slot_names_check"


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


def _atom_label_here(atom: Mapping) -> str:
    """A ground atom as the producer spells it, written again from the AST.

    The producer's spelling lives beside the graph whose nodes it names and
    takes the dataclass; this one reads the same atom out of the program
    document. It is restated rather than imported for the reason every
    restatement in this package is, and kept to the shape exactly, because
    two spellings that drifted apart would make an honest observation slot
    look like a name the program does not have.
    """
    args = ",".join(
        str(term.get("name")) for term in (atom.get("args") or ())
        if isinstance(term, Mapping))
    base = f"{atom.get('predicate')}({args})"
    time_index = atom.get("time_index")
    if not isinstance(time_index, Mapping):
        return base
    moment = time_index.get("value")
    if not isinstance(moment, int) or isinstance(moment, bool):
        return base
    return f"{base}@t" if moment == 0 else f"{base}@t{moment:+d}"


def _predicate_and_value(valued: object) -> tuple[str, str]:
    body = valued if isinstance(valued, Mapping) else {}
    atom = body.get("atom")
    predicate = atom.get("predicate") if isinstance(atom, Mapping) else None
    return str(predicate), str(body.get("value"))


def _slot_label_of(statement: Mapping) -> str | None:
    """The one slot a statement fills, named the producer's way.

    Three spellings, because there are three kinds of slot a confidence can
    arrive through: an edge is named by its two predicates, a parameter by
    the probability it fixes with its conditions in the producer's order,
    an observation by the ground atom and the value it was seen at.
    Quantified statements are spelled from their predicates, which their
    instances share, so a program stated over all units names the same
    slots as one written out.
    """
    kind = statement.get("kind")
    if kind == "cause":
        frm, to = statement.get("from"), statement.get("to")
        if not isinstance(frm, Mapping) or not isinstance(to, Mapping):
            return None
        return f"edge:{frm.get('predicate')}->{to.get('predicate')}"
    if kind == "probability":
        predicate, value = _predicate_and_value(statement.get("target"))
        given = statement.get("given")
        conditions = sorted(
            _predicate_and_value(one) for one in (
                given if isinstance(given, Sequence)
                and not isinstance(given, (str, bytes)) else ()))
        body = f"{predicate}={value}"
        if conditions:
            body += "|" + ",".join(f"{p}={v}" for p, v in conditions)
        population = statement.get("population")
        head = "P" if population is None else f"P_{population}"
        return f"parameter:{head}({body})"
    if kind == "observation":
        atom = statement.get("atom")
        if not isinstance(atom, Mapping):
            return None
        return f"observation:{_atom_label_here(atom)}={statement.get('value')}"
    return None


def verify_the_names_beside_each_confidence(
    result: object, program: object,
) -> None:
    """Hold each confidence source's names to the statement behind it.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` where a row names a
    slot the program does not annotate, where the source beside a number is
    not the one the program wrote at that slot, or where two rows claim the
    same edge.
    """
    if not isinstance(result, Mapping) or not isinstance(program, Mapping):
        return
    listed = result.get("confidence_sources")
    if not isinstance(listed, Sequence) or isinstance(listed, (str, bytes)):
        return
    rows = [row for row in listed if isinstance(row, Mapping)]
    if not rows or len(rows) != len(listed):
        return
    statements = program.get("statements")
    if (not isinstance(statements, Sequence)
            or isinstance(statements, (str, bytes))):
        return

    slots: dict[str, list[tuple[object, object]]] = {}
    for statement in statements:
        if not isinstance(statement, Mapping):
            continue
        annotations = statement.get("annotations")
        if not isinstance(annotations, Mapping):
            continue
        if annotations.get("confidence") is None:
            continue
        label = _slot_label_of(statement)
        if label is None:
            continue
        slots.setdefault(label, []).append(
            (annotations.get("confidence"), annotations.get("source")))

    claimed: set[str] = set()
    for row in rows:
        label = row.get("slot_label")
        written = slots.get(label) if isinstance(label, str) else None
        if written is None:
            raise VerificationError(
                f"a confidence source is filed under {label!r} and the "
                f"program annotates no such slot; the ones it does annotate "
                f"are {sorted(slots)}. That name is what a reader follows "
                f"from a number back to the statement it came out of",
                rule=_NAMES_RULE,
            )
        if not any(confidence == row.get("confidence")
                   and source == row.get("source")
                   for confidence, source in written):
            raise VerificationError(
                f"the source at {label!r} says its confidence is "
                f"{row.get('confidence')!r} and that it came from "
                f"{row.get('source')!r}; the program's statements at that "
                f"slot say {written}. A source line is a copy of one of "
                f"them, and a reader weighing the answer is weighing who "
                f"said it",
                rule=_NAMES_RULE,
            )
        # One row per edge is the producer's own shape -- the edges are
        # gathered into a mapping keyed by the pair -- so a second row
        # under one name is a slot standing in for another, which the
        # arithmetic above cannot see when the two carry one number.
        if isinstance(label, str) and label.startswith("edge:"):
            if label in claimed:
                raise VerificationError(
                    f"two confidence sources are filed under {label!r}; the "
                    f"edges an answer rests on are collected one row per "
                    f"edge, so a repeat is a slot the reader is never shown "
                    f"wearing the name of one they are shown twice",
                    rule=_NAMES_RULE,
                )
            claimed.add(label)
