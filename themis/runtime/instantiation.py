"""Instantiate ``forall`` declarations over the finite object domain D.

For each statement with non-empty ``forall``, produce one ground copy
per tuple of objects drawn from D. Statements without forall pass
through unchanged.

This step is the bridge from the relational level to the propositional
working model V.
"""
from __future__ import annotations

import dataclasses
from itertools import product
from typing import Iterable

from ..types import (
    Atom,
    BidirectedStatement,
    FeedbackLoop,
    CauseStatement,
    ConstTerm,
    ObservationStatement,
    ProbabilityModel,
    ProbabilityStatement,
    Program,
    QueryStatement,
    Statement,
    Term,
    ValuedAtom,
    VariableDeclaration,
    VarTerm,
)
from .probability_models import expand


def _subst_term(term: Term, subst: dict[str, str]) -> Term:
    if isinstance(term, VarTerm) and term.name in subst:
        return ConstTerm(name=subst[term.name])
    return term


def _subst_atom(atom: Atom, subst: dict[str, str]) -> Atom:
    return Atom(
        predicate=atom.predicate,
        args=tuple(_subst_term(t, subst) for t in atom.args),
        time_index=atom.time_index,
    )


def _subst_valued(va: ValuedAtom, subst: dict[str, str]) -> ValuedAtom:
    """Instantiate only the atom part; preserve the concrete value."""
    return ValuedAtom(atom=_subst_atom(va.atom, subst), value=va.value)


def _subst_valued_tuple(
    items: Iterable[ValuedAtom], subst: dict[str, str]
) -> tuple[ValuedAtom, ...]:
    return tuple(_subst_valued(v, subst) for v in items)


def _instantiate_one(stmt, subst: dict[str, str]):
    if isinstance(stmt, CauseStatement):
        return CauseStatement(
            from_atom=_subst_atom(stmt.from_atom, subst),
            to_atom=_subst_atom(stmt.to_atom, subst),
            forall=(),
            annotations=stmt.annotations,
            coefficient=stmt.coefficient,
        )
    if isinstance(stmt, (BidirectedStatement, FeedbackLoop)):
        return type(stmt)(
            left=_subst_atom(stmt.left, subst),
            right=_subst_atom(stmt.right, subst),
            forall=(),
            annotations=stmt.annotations,
        )
    if isinstance(stmt, ProbabilityStatement):
        # Population and provenance are part of what the entry IS — its key
        # and which rule validates it — so a ground copy that dropped them
        # was a universal structural entry where a population's prior had
        # been written.
        return ProbabilityStatement(
            target=_subst_valued(stmt.target, subst),
            given=_subst_valued_tuple(stmt.given, subst),
            value=stmt.value,
            forall=(),
            population=stmt.population,
            provenance=stmt.provenance,
            annotations=stmt.annotations,
        )
    if isinstance(stmt, ProbabilityModel):
        return ProbabilityModel(
            form=stmt.form,
            target=_subst_valued(stmt.target, subst),
            given=_subst_valued_tuple(stmt.given, subst),
            baseline=stmt.baseline,
            odds_ratios=tuple(dataclasses.replace(r, atom=_subst_atom(r.atom, subst))
                              for r in stmt.odds_ratios),
            forall=(),
            population=stmt.population,
            provenance=stmt.provenance,
        )
    return stmt


def instantiate(program: Program) -> tuple[Statement, ...]:
    """Return the fully ground statement list for a program.

    No statement in the output has a non-empty ``forall``, and none is a
    :class:`ProbabilityModel`: a model is ground like any statement and then
    stands in the list as the cells it expands into, so every reader of
    ground statements reads ordinary probability entries.
    The order is: all ground copies of statement i appear before any
    ground copies of statement i+1.
    """
    domain = program.objects
    declared = {s.predicate: tuple(s.domain) for s in program.statements
                if isinstance(s, VariableDeclaration) and s.domain}
    result: list[Statement] = []
    for stmt in program.statements:
        forall = getattr(stmt, "forall", ())
        copies = [stmt] if not forall else [
            _instantiate_one(stmt, dict(zip(forall, assignment)))
            for assignment in product(domain, repeat=len(forall))]
        for copy in copies:
            if isinstance(copy, ProbabilityModel):
                result.extend(expand(copy, declared))
            else:
                result.append(copy)
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
