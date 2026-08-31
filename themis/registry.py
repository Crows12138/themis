"""What this package says when one of its own declarations is missing.

Several modules here keep a table that IS a declaration. ``answers``
says which shapes an estimate of each method can come out in,
``questions`` what each ``query_kind`` asks, ``intervals`` how tight each
bounds method's interval is, ``ledger`` which layers each producer may
write. Every key those tables are looked up with is produced inside this
repository — an estimator's ``method``, the schema's own enum, a
grammar's node kind — so a miss is this package being incomplete, and
the only person who can clear one is the person extending it.

**That is who the sentence is for, and it had never been written down.**
Eight sites raised it in five wordings and two conventions: three raised
a bare ``KeyError`` and listed what the table did declare, five raised a
named subclass and did not. Nothing separated the halves except whether
the author had needed a name for a test to catch — which is a fact about
the test and not about the reader, and the difference had already been
read as a difference in audience by the one rule that asks.

So the audience is a class here, :class:`Undeclared`, and what a name on
such an exception means is stated rather than inferred: it is there to be
caught, and an exception caught for its type is still an invariant.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import TypeVar

K = TypeVar("K")
V = TypeVar("V")

__all__ = ["Undeclared", "NoRowDeclared", "row_for"]


class Undeclared(Exception):
    """Whoever is extending this package, said as a base class.

    Every subclass fires because a declaration THIS repository keeps is
    incomplete: a table with no row for a key, a row that declares
    nothing, a field a producer had to fill and did not. The key, the
    row and the field all come from inside, so nobody outside can cause
    one and nobody outside can clear one.

    Which makes these the same thing as a bare ``raise KeyError(...)`` —
    an invariant, read from a traceback by the person who can act on it,
    and never handed to whoever asked the question. A subclass carries a
    name only so that something can catch it by type; nothing may read
    its text and put it in front of a reader, which is the one rule this
    base class is worth having in order to state.
    """


class NoRowDeclared(Undeclared, KeyError):
    """A table was asked for a key it has no row for.

    Carries the three facts the eight sites had been writing out by hand,
    of which only three ever wrote the third: which table, which key, and
    what the table DOES declare. The last is the half that turns a
    refusal into a place to start — a maintainer reading "no row for
    ``backdoor_adjust``" beside a list containing ``backdoor_adjustment``
    is done, and one reading it alone is not.

    **It carries them and writes no sentence.** The wordings it replaces
    each ended in advice — add it beside the estimator that emits it,
    beside the grammar, beside the procedure — which is a phrase that
    said where the row goes to somebody already looking at the table's
    own dotted name. What is left is the shape the rest of this package
    arrived at from the other direction: the site carries facts, and
    whoever renders picks the words. Nobody renders an invariant, so the
    facts are the message, and the class name is the verb.
    """


def row_for(table: Mapping[K, V], key: object, *, named: str) -> V:
    """This table's row for ``key``, or the one refusal that has no row.

    ``key`` is typed as ``object`` on purpose, and that is what the one
    remaining ``type: ignore`` here is for. Several callers reach this
    with a value the schema says is present and a type checker cannot:
    ``estimate.get("method")``, ``node.get("kind")``. A key of the wrong
    type has to miss the same way a key of the right type misses, and be
    refused the same way — so the narrowing that would satisfy the
    checker is the branch this refusal exists to prevent. Said once here
    rather than once per caller.
    """
    try:
        return table[key]  # type: ignore[index]
    except KeyError:
        raise NoRowDeclared(
            named, key, [str(k) for k in sorted(table, key=str)]) from None
