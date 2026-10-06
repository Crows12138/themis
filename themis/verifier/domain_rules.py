"""The values a variable ranges over are the program's to say.

Checked here rather than taken from the builder that made them. Every
rule that re-derives a number sums over a variable's values, and reads
them from the parameter store the audit's context is rebuilt with — by
the same ``build_theta`` the kernel ran. So on this one premise the audit
had nothing of its own, and it showed: for as long as the builder read a
yes-or-no variable met at one of its values as a variable WITH one value
(#804), a sum over it ran over a single term, the gap that should have
asked for the other value never fired, the kernel reported a number, and
the audit — summing over the same single term — agreed with it.

What is held is the reading itself, restated from the program:

- a variable that declares its values ranges over those;
- one that does not ranges over the values the program's statements meet
  it at — and a yes-or-no is both of its values, whichever were met;
- one the program says nothing about is a yes-or-no;
- and where the numbers refute that reading — a variable nothing declares,
  given a probability at every value it was met at, with mass short of
  one — nobody knows its range, and the store must say so rather than
  answer with the values met.

That is checked for every variable in the graph and every variable a
statement mentions, against what the store ANSWERS when asked, since that
answer is what the rules sum over.
"""
from __future__ import annotations

from typing import Iterable

from ..types import (
    ObservationStatement,
    ProbabilityStatement,
    VariableDeclaration,
)
from .errors import VerificationError


def verify_domains_are_the_programs(ground, atoms: Iterable, theta) -> None:
    """Raise :class:`VerificationError` at the first variable the store
    gives a range the program does not."""
    declared: dict = {}
    met: dict = {}
    groups: dict = {}
    for statement in ground:
        if isinstance(statement, VariableDeclaration):
            if statement.domain is not None:
                declared[statement.predicate] = tuple(statement.domain)
        elif isinstance(statement, ProbabilityStatement):
            met.setdefault(statement.target.atom, []).append(
                statement.target.value)
            for conditioned in statement.given:
                met.setdefault(conditioned.atom, []).append(conditioned.value)
            group = groups.setdefault(
                (statement.target.atom,
                 frozenset((va.atom, va.value) for va in statement.given),
                 statement.population), {})
            group[_keyed(statement.target.value)] = statement.value
        elif isinstance(statement, ObservationStatement):
            met.setdefault(statement.atom, []).append(statement.value)

    short = _read_short(declared, met, groups)
    answered_short = set(theta.short)
    if answered_short != short:
        raise VerificationError(
            "domain: the parameter store says the range of "
            f"{_predicates(answered_short)} is known to be short, and the "
            f"program says that of {_predicates(short)} (a variable nothing "
            "declares, given a probability at every value it was met at, "
            "with mass short of one)")

    for atom in _each_once([*met, *atoms]):
        if atom in short:
            continue
        says = _ranges_over(atom, declared, met.get(atom, ()))
        answered = tuple(theta.domain_of(atom))
        if not _the_same_values(answered, says):
            raise VerificationError(
                f"domain: the parameter store ranges {atom.predicate} over "
                f"{_listed(answered)}, and the program says "
                f"{_listed(says)} ({_why(atom, declared, met)})")


def _ranges_over(atom, declared: dict, values) -> tuple:
    if atom.predicate in declared:
        return declared[atom.predicate]
    if all(isinstance(v, bool) for v in values):
        # Naming one value of a yes-or-no is not saying the other cannot
        # happen. Also the reading of a variable nothing mentions at all.
        return (False, True)
    return tuple(values)


def _read_short(declared: dict, met: dict, groups: dict) -> set:
    """The atoms whose range the numbers say is short: nothing declares
    them, and some group gives a probability at every value they were met
    at that adds up to less than one."""
    short = set()
    for (atom, _given, _population), values in groups.items():
        if atom.predicate in declared or atom in short:
            continue
        everywhere = {_keyed(v) for v in met.get(atom, ())}
        if all(isinstance(v, bool) for v in met.get(atom, ())):
            everywhere = {_keyed(False), _keyed(True)}
        if set(values) == everywhere and sum(values.values()) < 1.0 - 1e-9:
            short.add(atom)
    return short


def _keyed(value):
    """``True`` and ``1`` told apart, which ``==`` would not do."""
    return (type(value).__name__, value)


def _the_same_values(answered: tuple, says: tuple) -> bool:
    """As sets, and with no value twice: a sum over a range that lists a
    value twice counts it twice."""
    def keyed(values):
        return [_keyed(v) for v in values]
    return (len(set(keyed(answered))) == len(answered)
            and set(keyed(answered)) == set(keyed(says)))


def _predicates(atoms) -> str:
    return "{" + ", ".join(sorted(a.predicate for a in atoms)) + "}"


def _each_once(atoms):
    seen = set()
    for atom in atoms:
        if atom not in seen:
            seen.add(atom)
            yield atom


def _listed(values) -> str:
    return "{" + ", ".join(sorted(repr(v) for v in values)) + "}"


def _why(atom, declared: dict, met: dict) -> str:
    if atom.predicate in declared:
        return "its declaration lists them"
    if atom in met:
        return "the values its statements meet it at, a yes-or-no at both"
    return "nothing mentions it, so it is a yes-or-no"
