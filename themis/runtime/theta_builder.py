"""Compile ground ``ProbabilityStatement`` entries into a ``Theta``
parameter store consumable by ``numeric_estimator``.

v0.1 semantics:

- Each ground probability statement produces exactly one entry in
  Theta: ``(target.atom, target.value, frozenset(given)) -> value``.
- ``given`` values are packaged as a frozenset of ``(atom, value)``
  pairs, matching ``ProbabilityKey.given``.
- No automatic complement is materialized (e.g. writing
  ``P(y=True|x=True) = 0.2`` does NOT synthesize
  ``P(y=False|x=True) = 0.8``). Users supply the entries they need.
  A future slice may add principled complement materialization for
  declared-boolean atoms.
- Atom value domains are left at the Theta default (booleans) unless
  a future schema extension adds domain declarations.

Duplicate keys are an error (two probability statements about the
same (target_value, given) tuple is ambiguous under model semantics).
"""
from __future__ import annotations

from ..types import ProbabilityStatement, Statement
from .instantiation import instantiate
from .numeric_estimator import ProbabilityKey, Theta


class ConflictingThetaEntry(ValueError):
    """Raised when two probability statements produce the same
    ``ProbabilityKey`` with different values."""


def _key_of(stmt: ProbabilityStatement) -> ProbabilityKey:
    return ProbabilityKey(
        target_atom=stmt.target.atom,
        target_value=stmt.target.value,
        given=frozenset((va.atom, va.value) for va in stmt.given),
    )


def build_theta(ground_statements: tuple[Statement, ...]) -> Theta:
    """Build a Theta from a fully-ground statement tuple.

    Pre-condition: caller has already run ``instantiate(program)``
    so no statement carries a non-empty ``forall``.
    """
    entries: dict[ProbabilityKey, float] = {}
    for stmt in ground_statements:
        if not isinstance(stmt, ProbabilityStatement):
            continue
        key = _key_of(stmt)
        if key in entries and entries[key] != stmt.value:
            raise ConflictingThetaEntry(
                f"two probability statements specify the same key "
                f"{key!r} with different values "
                f"({entries[key]} vs {stmt.value})"
            )
        entries[key] = float(stmt.value)
    return Theta(entries=entries)


def build_theta_from_program(program) -> Theta:
    """Convenience: instantiate then build."""
    return build_theta(instantiate(program))
