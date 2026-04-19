"""Instantiate ``forall`` declarations over the finite object domain D.

For each statement with non-empty ``forall``, produce one ground copy
per tuple of objects drawn from D. Statements without forall pass
through unchanged.

This step is the bridge from the relational level to the propositional
working model V.
"""
from __future__ import annotations

from itertools import product
from typing import Iterable

from ..types import (
    Atom,
    CauseStatement,
    ConstTerm,
    ObservationStatement,
    ProbabilityStatement,
    Program,
    QueryStatement,
    Statement,
    Term,
    VarTerm,
)


def _subst_term(term: Term, subst: dict[str, str]) -> Term:
    if isinstance(term, VarTerm) and term.name in subst:
        return ConstTerm(name=subst[term.name])
    return term


def _subst_atom(atom: Atom, subst: dict[str, str]) -> Atom:
    return Atom(
        predicate=atom.predicate,
        args=tuple(_subst_term(t, subst) for t in atom.args),
    )


def _subst_atoms(atoms: Iterable[Atom], subst: dict[str, str]) -> tuple[Atom, ...]:
    return tuple(_subst_atom(a, subst) for a in atoms)


def _instantiate_one(stmt, subst: dict[str, str]):
    if isinstance(stmt, CauseStatement):
        return CauseStatement(
            from_atom=_subst_atom(stmt.from_atom, subst),
            to_atom=_subst_atom(stmt.to_atom, subst),
            forall=(),
        )
    if isinstance(stmt, ProbabilityStatement):
        return ProbabilityStatement(
            target=_subst_atom(stmt.target, subst),
            given=_subst_atoms(stmt.given, subst),
            value=stmt.value,
            forall=(),
            annotations=stmt.annotations,
        )
    return stmt


def instantiate(program: Program) -> tuple[Statement, ...]:
    """Return the fully ground statement list for a program.

    No statement in the output has a non-empty ``forall``.
    The order is: all ground copies of statement i appear before any
    ground copies of statement i+1.
    """
    domain = program.objects
    result: list[Statement] = []
    for stmt in program.statements:
        forall = getattr(stmt, "forall", ())
        if not forall:
            result.append(stmt)
            continue
        for assignment in product(domain, repeat=len(forall)):
            subst = dict(zip(forall, assignment))
            result.append(_instantiate_one(stmt, subst))
    return tuple(result)


def instance_variables(program: Program) -> tuple[Atom, ...]:
    """Return the ground atom set V produced by instantiating all
    cause statements.

    Used to validate that query atoms fall inside V.
    """
    ground = instantiate(program)
    seen: dict[Atom, None] = {}
    for stmt in ground:
        if isinstance(stmt, CauseStatement):
            seen.setdefault(stmt.from_atom)
            seen.setdefault(stmt.to_atom)
    return tuple(seen.keys())
