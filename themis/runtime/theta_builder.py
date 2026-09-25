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
  completion is safe to apply unconditionally. What a reader is asked
  for is the other half of the same rule (:func:`fewest_to_ask`): all but
  one of a group that lacks every value, never all of them.
- **The axiom is held for every group**, completed or not: a group that
  names every value of its domain must sum to one, and a group that
  leaves values out must leave them room. Either failure is rejected
  with ``ConflictingThetaEntry`` rather than clamped.
- Value domains ARE inferred from probability + observation
  statements (every value seen in a ``ValuedAtom``). The declared
  domain on ``VariableDeclaration`` takes precedence when present.
  An atom no statement mentions takes its variable's declared domain,
  and ``Theta``'s boolean default only when there is no declaration.

Duplicate keys (two statements about the same key with different
values) are an error.
"""
from __future__ import annotations

from collections.abc import Iterable

from ..types import (
    Atom,
    AtomValue,
    ObservationStatement,
    ProbabilityStatement,
    Statement,
    ValuedAtom,
    VarRef,
    VariableDeclaration,
)
from .. import language
from .instantiation import instantiate
from .numeric_estimator import ProbabilityKey, Theta, format_probability_key
from .theta_words import Half, Refuses


class ConflictingThetaEntry(language.Voiced, ValueError):
    """The caller's numbers cannot all be true at once.

    A CHANNEL, carrying two of the species in
    :class:`themis.runtime.theta_words.Refuses`: two statements that
    disagree about one key, and a group whose supplied mass leaves no
    room for its complement. One is a duplicate and the other is not,
    and a caller catching this class reads which off ``species``.
    """


class NonLiteralProbabilityValue(language.Voiced, ValueError):
    """A ``ProbabilityStatement`` carries a value that is not a literal.

    The other channel, and a different question: nothing contradicts
    anything, the statement simply is not the shape its own schema
    declares.
    """


def _literal_value(va: ValuedAtom, *, half: Half) -> AtomValue:
    """Return the concrete literal carried by a probability statement's
    ``ValuedAtom``.

    ``ValuedAtom`` is shared with the formula AST, where a value may be a
    ``VarRef`` (bound by an enclosing sum) or ``None`` (bound by the
    query context). Inside a ``ProbabilityStatement`` neither is legal:
    the statement describes one CPT entry, fully specified at program
    time, and ``atom.schema.json`` §groundedAtom requires a literal.
    Theta keys and value domains are built from these values, so a
    non-literal one would silently produce a key nothing can ever match.
    This restates the statement's own contract at the point that depends
    on it, and hands back the narrowed value.
    """
    value = va.value
    if value is None or isinstance(value, VarRef):
        raise NonLiteralProbabilityValue(
            Refuses.A_VALUE_IS_NOT_A_LITERAL,
            half=half, predicate=va.atom.predicate, value=value)
    return value


def _key_of(stmt: ProbabilityStatement) -> ProbabilityKey:
    # Fix 3+4: stmt.population (Phase 9 field) is now part of the
    # canonical key. Two statements P(X=x | given) with different
    # population labels are NO LONGER treated as conflicting entries —
    # they belong to different theta partitions. Single-population
    # programs (population=None on all statements) behave identically
    # to pre-fix.
    return ProbabilityKey(
        target_atom=stmt.target.atom,
        target_value=_literal_value(stmt.target, half=Half.TARGET),
        given=frozenset(
            (va.atom, _literal_value(va, half=Half.GIVEN))
            for va in stmt.given
        ),
        population=stmt.population,
    )


def _sort_values(values: set[AtomValue]) -> tuple[AtomValue, ...]:
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
                    Refuses.TWO_STATEMENTS_DISAGREE_ABOUT_ONE_KEY,
                    key=key, first=entries[key], second=stmt.value)
            entries[key] = float(stmt.value)
            note(stmt.target.atom,
                 _literal_value(stmt.target, half=Half.TARGET))
            for va in stmt.given:
                note(va.atom, _literal_value(va, half=Half.GIVEN))
        elif isinstance(stmt, ObservationStatement):
            note(stmt.atom, stmt.value)
        elif isinstance(stmt, VariableDeclaration):
            if stmt.domain is not None:
                declared_domains[stmt.predicate] = tuple(stmt.domain)

    # Final per-atom domain: declared takes precedence when present;
    # otherwise the values observed across probability + observation
    # statements. (Theta.domain_of further falls back to (True, False)
    # for atoms with no information at all.)
    final_domains: dict[Atom, tuple[AtomValue, ...]] = {}
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

    return Theta(entries=entries, domains=final_domains,
                 declared=declared_domains)


def fewest_to_ask(
    keys: Iterable[ProbabilityKey],
    theta: Theta,
    *,
    keep: Iterable[ProbabilityKey] = (),
) -> tuple[ProbabilityKey, ...]:
    """The fewest of ``keys`` a reader must supply for every one to resolve.

    The other half of :func:`_complete_partial_distributions`. Completion
    reads one variable's values under one condition in one population as a
    group with one degree of freedom fewer than it has values: supply all
    but one and the last is one minus their sum. The callers that collect
    what an evaluation could not resolve collect it a cell at a time, so
    where a group lacks every value it has not been given they list one
    value more than anybody has to supply. A reader following the list then
    writes two numbers where one decides both — the input #771 has to catch
    when the two do not sum to one.

    So, per group: where the cells collected are every value the group
    still lacks, the last of them in the variable's order is left out, it
    being the one completion supplies. A group only part of which was
    collected keeps all of it; supplying exactly those is already the
    least, since completing any of them would take every other value.

    ``keep`` names cells a caller has more to say about than that they are
    missing — the cell whose lookup raised, with a diagnosis of its own —
    and the cell left out is then another one. Order and first occurrence
    are kept; repeats are dropped.
    """
    ordered = list(dict.fromkeys(keys))
    kept = frozenset(keep)
    supplied: dict[tuple, set] = {}
    for key in theta.entries:
        supplied.setdefault(
            (key.target_atom, key.given, key.population), set(),
        ).add(key.target_value)
    groups: dict[tuple, list[ProbabilityKey]] = {}
    for key in ordered:
        groups.setdefault(
            (key.target_atom, key.given, key.population), [],
        ).append(key)
    left_out: set[ProbabilityKey] = set()
    for group, members in groups.items():
        domain = theta.domain_of(group[0])
        lacking = [v for v in domain if v not in supplied.get(group, ())]
        if not lacking or {k.target_value for k in members} != set(lacking):
            continue
        droppable = [k for k in members if k not in kept]
        if not droppable:
            continue
        place = {value: i for i, value in enumerate(domain)}
        left_out.add(max(droppable, key=lambda k: place[k.target_value]))
    return tuple(k for k in ordered if k not in left_out)


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

    Raises ``ConflictingThetaEntry`` from :func:`_hold_the_axiom`, which
    every group passes through whether or not it is completed.
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
        total_supplied = sum(value_map.values())
        _hold_the_axiom(target_atom, given, pop, missing, total_supplied,
                        tolerance)
        if len(missing) != 1:
            # Either complete or under-specified by more than one
            # entry. The probability axiom alone determines the
            # singleton-missing case; multi-missing needs other info.
            continue
        missing_value = missing[0]
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


def _hold_the_axiom(
    target_atom: Atom,
    given: frozenset[tuple[Atom, AtomValue]],
    population: str | None,
    missing: list[AtomValue],
    total: float,
    tolerance: float,
) -> None:
    """One variable's probabilities under one condition sum to one.

    A fact about the numbers, whether or not any of them is about to be
    completed. It used to be asked only on the way to completing a group,
    which is the case where exactly one value is missing — so a pair
    supplied in full was never added up, and two pairs off by the same
    amount in opposite directions gave a joint that summed to one and an
    interval that was wrong.

    Written so that a NaN fails it: every comparison with one is false.
    """
    named = format_probability_key(ProbabilityKey(
        target_atom=target_atom, target_value="*", given=given,
        population=population))
    if not missing:
        if not abs(total - 1.0) <= tolerance:
            raise ConflictingThetaEntry(
                Refuses.A_FULL_DISTRIBUTION_DOES_NOT_SUM_TO_ONE,
                distribution=named, total=total)
        return
    if not -tolerance <= total <= 1.0 + tolerance:
        raise ConflictingThetaEntry(
            Refuses.THE_SUPPLIED_MASS_LEAVES_NO_COMPLEMENT,
            distribution=named, total=total,
            missing=", ".join(str(v) for v in missing))


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
