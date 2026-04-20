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
- Value domains ARE inferred from the statements: every value seen in
  a ``ValuedAtom`` (probability target / given, observation value)
  contributes to that atom's observed domain. Atoms never seen in any
  such position fall back to ``Theta``'s boolean default.

Duplicate keys are an error (two probability statements about the
same (target_value, given) tuple is ambiguous under model semantics).
"""
from __future__ import annotations

from ..types import (
    Atom,
    AtomValue,
    ObservationStatement,
    ProbabilityStatement,
    Statement,
)
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


def _sort_values(values: set) -> tuple:
    """Return a deterministic ordering of observed values.

    Sorting is done by string repr to tolerate mixed-type sets (we do
    not police type uniformity per atom here; user pathology will
    surface through evaluation or key-lookup failure)."""
    return tuple(sorted(values, key=lambda v: (type(v).__name__, str(v))))


def build_theta(ground_statements: tuple[Statement, ...]) -> Theta:
    """Build a Theta from a fully-ground statement tuple.

    Pre-condition: caller has already run ``instantiate(program)``
    so no statement carries a non-empty ``forall``.
    """
    entries: dict[ProbabilityKey, float] = {}
    domains: dict[Atom, set[AtomValue]] = {}

    def note(atom: Atom, value: AtomValue) -> None:
        domains.setdefault(atom, set()).add(value)

    for stmt in ground_statements:
        if isinstance(stmt, ProbabilityStatement):
            key = _key_of(stmt)
            if key in entries and entries[key] != stmt.value:
                raise ConflictingThetaEntry(
                    f"two probability statements specify the same key "
                    f"{key!r} with different values "
                    f"({entries[key]} vs {stmt.value})"
                )
            entries[key] = float(stmt.value)
            note(stmt.target.atom, stmt.target.value)
            for va in stmt.given:
                note(va.atom, va.value)
        elif isinstance(stmt, ObservationStatement):
            note(stmt.atom, stmt.value)

    final_domains: dict[Atom, tuple] = {
        atom: _sort_values(values) for atom, values in domains.items()
    }
    return Theta(entries=entries, domains=final_domains)


def build_theta_from_program(program) -> Theta:
    """Convenience: instantiate then build."""
    return build_theta(instantiate(program))


# ---------------------------------------------------------------------------
# Source indices for confidence collection (RFC §3.1 / §3.2)
# ---------------------------------------------------------------------------

def build_probability_source_index(
    ground_statements: tuple[Statement, ...],
) -> dict[ProbabilityKey, tuple[ProbabilityStatement, ...]]:
    """Map each ``ProbabilityKey`` to every ground
    ``ProbabilityStatement`` that produces it.

    Used by the confidence collector to apply the RFC §3.1 slot-min
    rule without re-walking the program. A key may appear multiple
    times in the source list when ``theta_builder.build_theta``'s
    idempotency allowed multiple equivalent statements.
    """
    index: dict[ProbabilityKey, list[ProbabilityStatement]] = {}
    for stmt in ground_statements:
        if isinstance(stmt, ProbabilityStatement):
            index.setdefault(_key_of(stmt), []).append(stmt)
    return {k: tuple(v) for k, v in index.items()}


def build_observation_source_index(
    ground_statements: tuple[Statement, ...],
):
    """Map each ``(atom, value)`` pair to every ground
    ``ObservationStatement`` matching exactly.

    Used by the confidence collector to apply the RFC §3.2
    participation rule: an observation counts only when its atom
    AND value both match a ``ValuedAtom`` entry in the query's
    ``given``.
    """
    from ..types import ObservationStatement

    index: dict = {}
    for stmt in ground_statements:
        if isinstance(stmt, ObservationStatement):
            index.setdefault((stmt.atom, stmt.value), []).append(stmt)
    return {k: tuple(v) for k, v in index.items()}
