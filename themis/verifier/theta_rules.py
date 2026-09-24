"""The parameters an answer was computed from are probabilities.

Checked here rather than taken from the builder that made them. The
context an audit runs in is rebuilt from the program by the same
``build_theta`` the kernel ran, and the rules that recover a joint from it
read cells with a line-for-line copy of the producer's reader, so on this
one premise the audit had nothing of its own: for as long as the builder
added a group up only when it was completing it, two pairs supplied in
full and off by the same amount in opposite directions gave a joint that
summed to one, an interval that was wrong, and an audit that accepted it.

What is held is the axiom, group by group — one variable, one condition,
one population: every cell is in ``[0, 1]``; a group that covers its
variable's domain sums to one; a group that does not cover it sums to at
most one. A domain of a single value is a domain nobody declared — the
builder infers it from the one value a program mentioned — and says
nothing about what else the variable can be, so it is held only to the
last of the three.
"""
from __future__ import annotations

import math

from .errors import VerificationError

#: Float rounding, not leniency: the axiom is exact, and a caller whose
#: numbers were rounded before they were written down has written a
#: different distribution.
TOLERANCE = 1e-9


def verify_theta_is_a_distribution(theta) -> None:
    """Raise :class:`VerificationError` naming the first group that is not
    a (sub-)distribution. Every comparison is written so a NaN fails it."""
    groups: dict[tuple, dict] = {}
    for key, value in theta.entries.items():
        group = (key.target_atom, key.given, key.population)
        groups.setdefault(group, {})[key.target_value] = float(value)
    for (atom, given, population), cells in groups.items():
        named = _named(atom, given, population)
        for value, p in cells.items():
            if not 0.0 <= p <= 1.0:
                raise VerificationError(
                    f"theta: {named} gives {atom.predicate}={value!r} the "
                    f"value {p!r}, which is not a probability")
        total = math.fsum(cells.values())
        domain = tuple(theta.domain_of(atom))
        covers = len(domain) > 1 and set(domain) <= set(cells)
        if covers and not abs(total - 1.0) <= TOLERANCE:
            raise VerificationError(
                f"theta: every value of {named} is present and they sum "
                f"to {total!r}, not 1")
        if not covers and not total <= 1.0 + TOLERANCE:
            raise VerificationError(
                f"theta: the values of {named} that are present already "
                f"sum to {total!r}, more than 1")


def _named(atom, given, population) -> str:
    """``P(y=*|x=True)`` — spelled here rather than borrowed from the
    runtime's formatter, which is on the side being checked."""
    conditions = ",".join(
        f"{a.predicate}={v}"
        for a, v in sorted(given, key=lambda pair: (pair[0].predicate, str(pair[1]))))
    body = f"{atom.predicate}=*" + (f"|{conditions}" if conditions else "")
    return f"P({body})" if population is None else f"P_{population}({body})"
