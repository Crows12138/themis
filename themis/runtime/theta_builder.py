"""Compile ground ``ProbabilityStatement`` entries into a ``Theta``
parameter store consumable by ``numeric_estimator``.

v0.1 semantics:

- Each ground probability statement produces one entry in Theta:
  ``(target.atom, target.value, frozenset(given)) -> value``.
- ``given`` values are packaged as a frozenset of ``(atom, value)``
  pairs, matching ``ProbabilityKey.given``.
- **Partial-distribution completion**: when a user
  supplies K-1 of K domain values for a (target_atom, given) group
  AND the predicate's declared domain is known (from
  ``VariableDeclaration.domain``), the kernel synthesizes the missing
  K-th entry via the probability axiom ``∑ P(X=v|given) = 1``.
  Closes the CLadder dry-run finding: agents writing
  ``P(X=true)=0.43`` for a binary X without the redundant
  ``P(X=false)=0.57`` previously broke marginalization, because the
  numeric evaluator iterates the full declared domain. The rule is
  the probability axiom — no inference, no heuristic — so the
  completion is safe to apply unconditionally. Conflicting / out-of-
  range completions (sum > 1 + ε or implied complement < 0) are
  rejected with ``ConflictingThetaEntry`` rather than silently
  clamped.
- Value domains ARE inferred from probability + observation
  statements (every value seen in a ``ValuedAtom``). The declared
  domain on ``VariableDeclaration`` takes precedence when present.
  Atoms with no information fall back to ``Theta``'s boolean default.

Duplicate keys (two statements about the same key with different
values) are an error.
"""
from __future__ import annotations

from ..types import (
    Atom,
    AtomValue,
    ObservationStatement,
    ProbabilityStatement,
    Statement,
    VariableDeclaration,
)
from .instantiation import instantiate
from .numeric_estimator import ProbabilityKey, Theta


class ConflictingThetaEntry(ValueError):
    """Raised when two probability statements produce the same
    ``ProbabilityKey`` with different values."""


def _key_of(stmt: ProbabilityStatement) -> ProbabilityKey:
    # Fix 3+4: stmt.population (Phase 9 field) is now part of the
    # canonical key. Two statements P(X=x | given) with different
    # population labels are NO LONGER treated as conflicting entries —
    # they belong to different theta partitions. Single-population
    # programs (population=None on all statements) behave identically
    # to pre-fix.
    return ProbabilityKey(
        target_atom=stmt.target.atom,
        target_value=stmt.target.value,
        given=frozenset((va.atom, va.value) for va in stmt.given),
        population=stmt.population,
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
    # Predicate name → declared domain (from VariableDeclaration). Used
    # by the partial-distribution completion below so a user who
    # supplies P(X=true)=0.43 without P(X=false)=0.57 still gets a
    # complete theta — the probability axiom (probabilities over a
    # disjoint exhaustive domain sum to 1) does the rest.
    declared_domains: dict[str, tuple[AtomValue, ...]] = {}

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
        elif isinstance(stmt, VariableDeclaration):
            if stmt.domain is not None:
                declared_domains[stmt.predicate] = tuple(stmt.domain)

    # Final per-atom domain: declared takes precedence when present;
    # otherwise the values observed across probability + observation
    # statements. (Theta.domain_of further falls back to (True, False)
    # for atoms with no information at all.)
    final_domains: dict[Atom, tuple] = {}
    seen_atoms = set(domains.keys())
    for atom in seen_atoms:
        if atom.predicate in declared_domains:
            final_domains[atom] = declared_domains[atom.predicate]
        else:
            final_domains[atom] = _sort_values(domains[atom])

    # Partial-distribution completion via probability
    # axiom. When the user supplies K-1 of K declared-domain values
    # for some (target_atom, given) group, synthesize the K-th as
    # 1 - sum(others). Applied AFTER the main loop so it can see all
    # entries + final domains. No-op when the group already has all K
    # or fewer than K-1 entries. Safety: reject obviously inconsistent
    # supplied entries (sum > 1 + ε or implied complement < -ε) rather
    # than clamp silently. Closes CLadder dry-run finding 2026-05-14
    # (Q8706 marginal).
    entries = _complete_partial_distributions(entries, final_domains)

    return Theta(entries=entries, domains=final_domains)


def _complete_partial_distributions(
    entries: dict[ProbabilityKey, float],
    final_domains: dict[Atom, tuple[AtomValue, ...]],
    *,
    tolerance: float = 1e-9,
) -> dict[ProbabilityKey, float]:
    """Augment ``entries`` so each (target_atom, given) group covers the
    full declared domain of ``target_atom``.

    Group the existing entries by ``(target_atom, given)``. For each
    group:
    - If the group has all K domain values, leave it.
    - If it has exactly K-1 of K, fill in the K-th as ``1 - sum``.
    - If it has fewer than K-1 (more than one missing), leave it (the
      probability axiom alone is insufficient).

    Raises ``ConflictingThetaEntry`` when supplied entries sum to a
    value outside ``[0, 1 + tolerance]`` (so the implied complement
    would be negative or > 1). Silently clamping would mask a real
    bug in the supplied program.
    """
    # Group entries by (target_atom, frozenset given, population).
    # Fix 3+4: completion is per-population — P(X=true | given, pop=source)
    # = 0.43 implies P(X=false | given, pop=source) = 0.57 INSIDE
    # population=source, NOT across populations. Two populations'
    # K-1 entries on the same (target, given) shape are independent.
    groups: dict[
        tuple[Atom, frozenset[tuple[Atom, AtomValue]], str | None],
        dict[AtomValue, float],
    ] = {}
    for key, value in entries.items():
        group_key = (key.target_atom, key.given, key.population)
        groups.setdefault(group_key, {})[key.target_value] = value

    completed = dict(entries)
    for (target_atom, given, pop), value_map in groups.items():
        # Declared domain wins; if target_atom isn't in final_domains
        # (which only includes atoms seen somewhere), default to the
        # boolean fallback consistent with Theta.domain_of.
        domain = final_domains.get(target_atom, (True, False))
        if len(domain) <= 1:
            continue
        seen_values = set(value_map.keys())
        missing = [v for v in domain if v not in seen_values]
        if len(missing) != 1:
            # Either complete or under-specified by more than one
            # entry. The probability axiom alone determines the
            # singleton-missing case; multi-missing needs other info.
            continue
        missing_value = missing[0]
        total_supplied = sum(value_map.values())
        if total_supplied > 1.0 + tolerance or total_supplied < -tolerance:
            raise ConflictingThetaEntry(
                f"supplied probabilities for "
                f"P({target_atom.predicate}=*|...) sum to "
                f"{total_supplied} which is outside [0, 1]; "
                f"the implied complement for "
                f"P({target_atom.predicate}={missing_value}|...) "
                f"would be invalid"
            )
        complement = 1.0 - total_supplied
        # Clamp tiny float rounding into [0, 1]; reject only when the
        # input was actually broken (caught above).
        complement = max(0.0, min(1.0, complement))
        new_key = ProbabilityKey(
            target_atom=target_atom,
            target_value=missing_value,
            given=given,
            population=pop,
        )
        completed[new_key] = complement
    return completed


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
