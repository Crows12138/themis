"""What a variable declaration's framing fields are, said once.

A ``VariableDeclaration`` carries nine fields that say what the variable
MEANS — the window it refers to, how it is measured, where a cutpoint
falls, and so on. Five parts of the system ask a question about that set:
which of them a missing value is reported for, which a patch may carry,
which a default can answer, which two declarations merge by comparing,
and which the fill form offers a reader a blank for.

**Why this file exists.** Each of those questions used to answer itself by
listing all nine names again. Ten such lists existed — the dataclass, the
AST schema, two in ``runtime/framing_check``, two in
``workflow/variable_framing``, one in ``upstream/narrative_merge``, one in
``web/app``, one in the browser's ``verdict.ts``, and the schema's
``defaulted`` enum — and nothing derived any of them from any other. A
list that has to agree with another list is a derivation written as a
copy, and one of these said so outright: ``_PATCH_DISPLAY_FIELDS`` carried
"must stay in sync with ``_PATCHABLE_FIELDS`` — any shape change needs
coordinated edits in both modules". It was the only enforcement there was,
and by the time it was read it had already stopped being true.

Copying the list also copied the loop over it: two modules had grown the
same function for "what has this declaration settled, as JSON", agreeing
on every input anyone tried.

So the rows below are the fields, and the three things each row states are
the three the questions actually turn on. Every other listing in the
system is a projection of this table, and the tests say which — including
the two that cannot import Python and are held to it from outside.

``scale`` and ``defaulted`` are on the declaration and are not here.
``scale`` answers a question about the DATA (what the column holds), not
about what the variable means; ``defaulted`` names members of this table
rather than being one.
"""
from __future__ import annotations

from dataclasses import dataclass

from .types import VariableDeclaration


@dataclass(frozen=True)
class FramingField:
    """One framing field, and the three facts the questions turn on."""

    name: str

    #: Whether leaving it unset is reported as a framing gap. A field that
    #: not every variable has is not a gap when it is missing — asking a
    #: boolean outcome for its unit is asking for something that does not
    #: exist.
    reported: bool

    #: Whether "take the standard operationalisation" can answer it. The
    #: levels a variable ranges over have no standard to take: they are
    #: what the rest of the program computes over, so a default there
    #: would be a guess wearing the same word as an answer.
    defaultable: bool

    #: Whether it holds one value, so two declarations of the same
    #: predicate settle it by comparing and a view of the declaration
    #: stores it as it stands. The one that does not is a sequence, and
    #: every consumer that walks these fields has a branch for it.
    scalar: bool

    @property
    def asked(self) -> bool:
        """Whether the fill form offers a reader a blank for it.

        Derived rather than declared, because it is not a further fact:
        offering a field whose absence is not reported gives a reader a
        blank that clears nothing, and offering one a default cannot
        answer makes leaving it blank unanswerable. What the form asks is
        exactly what a reader could settle either way.
        """
        return self.reported and self.defaultable


#: The nine, in the order a declaration writes them.
FIELDS: tuple[FramingField, ...] = (
    FramingField("domain", reported=True, defaultable=False, scalar=False),
    FramingField("time_window", reported=True, defaultable=True, scalar=True),
    FramingField("measurement", reported=True, defaultable=True, scalar=True),
    FramingField("threshold", reported=True, defaultable=True, scalar=True),
    FramingField("observability", reported=True, defaultable=True, scalar=True),
    FramingField("unit", reported=False, defaultable=True, scalar=True),
    FramingField("direction", reported=True, defaultable=True, scalar=True),
    FramingField("baseline", reported=True, defaultable=True, scalar=True),
    FramingField("state_vs_event", reported=True, defaultable=True,
                 scalar=True),
)

#: The field that names members of :data:`FIELDS` instead of being one.
#: Kept beside them because every walk over the declaration's framing has
#: to decide whether it is included, and the two lists that differed by
#: exactly this were the pair nothing held equal.
NAMES_THE_DEFAULTED = "defaulted"


def names() -> tuple[str, ...]:
    return tuple(f.name for f in FIELDS)


def reported() -> tuple[str, ...]:
    """Fields whose absence is a framing gap."""
    return tuple(f.name for f in FIELDS if f.reported)


def defaultable() -> tuple[str, ...]:
    """Fields a default can answer."""
    return tuple(f.name for f in FIELDS if f.defaultable)


def scalar() -> tuple[str, ...]:
    """Fields two declarations settle by comparing values."""
    return tuple(f.name for f in FIELDS if f.scalar)


def asked() -> tuple[str, ...]:
    """Fields the fill form offers a reader a blank for."""
    return tuple(f.name for f in FIELDS if f.asked)


def settled(decl: VariableDeclaration) -> dict:
    """JSON-ish view of what this declaration has already settled.

    Settled, not set: a field answered by taking the default carries no
    value and is still not open, so the names of those come along beside
    the values. Read-only context — what a patch is shown before it is
    asked to fill the rest.
    """
    out: dict = {}
    for f in FIELDS:
        value = getattr(decl, f.name)
        if value is None:
            continue
        out[f.name] = value if f.scalar else list(value)
    if decl.defaulted:
        out[NAMES_THE_DEFAULTED] = list(decl.defaulted)
    return out
