"""Unit tests for the slice A0 advisory framing check.

Framing is opt-in per predicate: a predicate with no VariableDeclaration
emits nothing; a predicate with a partial declaration emits exactly the
fields that were left unset.
"""
from __future__ import annotations

from themis.runtime.framing_check import check_framing
from themis.types import (
    Atom,
    ConstTerm,
    EffectQuery,
    Intervention,
    Program,
    QueryStatement,
    ValuedAtom,
    VariableDeclaration,
)


def _atom(pred: str, obj: str = "me") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _effect_query(target_pred: str, intervention_pred: str) -> QueryStatement:
    return QueryStatement(
        id="q",
        query=EffectQuery(
            target=ValuedAtom(atom=_atom(target_pred), value=True),
            intervention=Intervention(atom=_atom(intervention_pred), value=True),
            given=(),
        ),
    )


def _program(*statements) -> Program:
    return Program(version="0.1", objects=("me",), statements=tuple(statements))


def test_no_declarations_emits_no_notes():
    """Baseline: a program without any VariableDeclaration produces no
    framing_notes for its queries. This is what keeps every pre-A0
    fixture silent."""
    stmt = _effect_query("waist_reduced", "exercise_regular")
    program = _program(stmt)
    assert check_framing(program, stmt) == ()


def test_partial_declaration_reports_unset_fields():
    """A predicate declared with only domain emits a note listing the
    other four reportable fields."""
    stmt = _effect_query("waist_reduced", "exercise_regular")
    program = _program(
        VariableDeclaration(
            predicate="waist_reduced", domain=(True, False)
        ),
        stmt,
    )
    notes = check_framing(program, stmt)
    assert len(notes) == 1
    assert notes[0].predicate == "waist_reduced"
    assert set(notes[0].missing) == {
        "time_window", "measurement", "threshold", "observability",
    }


def test_fully_declared_predicate_emits_no_note():
    """If every reportable field is set the predicate is silent even
    though a declaration exists."""
    stmt = _effect_query("waist_reduced", "exercise_regular")
    program = _program(
        VariableDeclaration(
            predicate="waist_reduced",
            domain=(True, False),
            time_window="12w",
            measurement="waist cm",
            threshold=">=3cm",
            observability="observable",
        ),
        stmt,
    )
    assert check_framing(program, stmt) == ()


def test_undeclared_predicate_stays_silent_even_when_others_are_declared():
    """Opt-in is per predicate, not per program: declaring
    waist_reduced does not force a note for exercise_regular."""
    stmt = _effect_query("waist_reduced", "exercise_regular")
    program = _program(
        VariableDeclaration(
            predicate="waist_reduced",
            domain=(True, False),
            time_window="12w",
            measurement="waist cm",
            threshold=">=3cm",
            observability="observable",
        ),
        stmt,
    )
    # waist_reduced is fully declared → no note for it.
    # exercise_regular has no declaration → no note for it either.
    assert check_framing(program, stmt) == ()


def test_multiple_query_atoms_produce_deduplicated_per_predicate_notes():
    """If a query mentions the same predicate more than once we still
    emit one note per predicate, not one per occurrence."""
    # Target and intervention share the same predicate (unusual but
    # structurally legal for this test).
    stmt = QueryStatement(
        id="q",
        query=EffectQuery(
            target=ValuedAtom(atom=_atom("y", "me"), value=True),
            intervention=Intervention(atom=_atom("y", "me"), value=True),
            given=(ValuedAtom(atom=_atom("y", "me"), value=False),),
        ),
    )
    program = _program(
        VariableDeclaration(predicate="y", domain=(True, False)),
        stmt,
    )
    notes = check_framing(program, stmt)
    assert len(notes) == 1
    assert notes[0].predicate == "y"
