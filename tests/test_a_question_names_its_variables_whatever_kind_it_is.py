"""Which variables a question names — and the kinds nobody ever asked.

The framing check tells a reader which variables in their question have no
operational definition: no time window, no measurement, no baseline. It is
the one thing this system says about whether the question means anything
before it starts answering it.

It read the query through six ``isinstance`` arms, each naming which fields
of that kind hold an atom, and returned nothing for anything else. Four of
the ten question kinds were not on that list — causation, counterfactual
conjunction, proximal effect, SCM counterfactual — so for those, the check
was off. **Forty-nine answers in this suite's own corpus name a variable
whose declaration is incomplete and were told nothing about it — a hundred
and forty-four variables in all.** Inside the kind the list named most
carefully it missed two fields: the MEDIATOR of a mediation query, and the
second treatment of a joint intervention — a variable the question
explicitly intervenes on.

A list of which fields hold an atom is a list of what its author remembered.
The space it should cover is "the atoms this query holds", and that is what
:func:`themis.types.atoms_named_by` reads: no class arms, no field names.
Measured before it replaced anything, and again after: on every corpus row
the roster covered, the walk drops NOTHING, and every predicate it adds
there is a mediator or a second treatment. The rest of what it reaches is
in the four kinds that had no arm at all.

The failure this shape has is the one worth naming: a partial mapping that
fails by never matching looks exactly like deliberate silence. No note and
"every variable is fully defined" are the same thing on the reader's
surface, which is why this went four kinds wide without a red test.

So the gate below is per KIND, taken from ``questions.DECLARED`` rather than
written out: every kind this build declares must have its variables checked.
A kind added tomorrow with no framing reach fails here rather than reaching
a reader as silence.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from themis import questions
from themis.kernel import validate_ast, validate_program
from themis.runtime import framing_check
from themis.types import (
    Atom,
    CausationQuery,
    ConstTerm,
    EffectQuery,
    Intervention,
    QueryStatement,
    ValuedAtom,
    atoms_named_by,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _stripped(program: dict) -> dict:
    """The same program with every declaration reduced to its predicate.

    A field somebody filled is not a gap, and which fields these corpus
    programs happen to fill is not the subject here. Stripping them makes
    every declared variable one the check has something to say about.
    """
    program = json.loads(json.dumps(program))
    for stmt in program.get("statements") or ():
        if stmt.get("kind") == "variable":
            for key in list(stmt):
                if key not in ("kind", "predicate", "domain"):
                    del stmt[key]
    return program


def _parsed(name: str):
    pair = SHAPES[name]
    program = validate_program(validate_ast(_stripped(pair["program"])))
    query_id = (pair["result"] or {}).get("query_id")
    stmt = next((s for s in program.statements
                 if isinstance(s, QueryStatement) and s.id == query_id), None)
    return program, stmt


def _rows_by_kind() -> dict[str, str]:
    """One corpus row per question kind: the one declaring the most of what
    its query names.

    Not the first row of that kind. Framing is opt-in per predicate, so a
    program that declares none of its variables is silent for a reason
    that is not the one under test — and two kinds have such a row first.
    """
    best: dict[str, tuple[int, str]] = {}
    for name in sorted(SHAPES):
        result = SHAPES[name]["result"] or {}
        kind = result.get("query_kind")
        if kind is None:
            continue
        program, stmt = _parsed(name)
        if stmt is None:
            continue
        named = {atom.predicate for atom in atoms_named_by(stmt.query)}
        declared = named & set(
            framing_check._declarations_by_predicate(program))
        if kind not in best or len(declared) > best[kind][0]:
            best[kind] = (len(declared), name)
    return {kind: name for kind, (_n, name) in best.items()}


ROWS = _rows_by_kind()


@pytest.mark.parametrize("kind", [q.kind for q in questions.DECLARED])
def test_a_question_of_any_kind_has_its_variables_checked(kind):
    """The gate the four missing kinds would have failed."""
    assert kind in ROWS, f"no corpus row asks a {kind} question"
    program, stmt = _parsed(ROWS[kind])
    named = {atom.predicate for atom in atoms_named_by(stmt.query)}
    declared = named & set(framing_check._declarations_by_predicate(program))
    assert declared, f"the {kind} row declares none of what it names"
    notes = {note.predicate
             for note in framing_check.check_framing(program, stmt)}
    assert notes == declared


def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name="u"),))


def test_the_two_the_effect_arm_did_not_name():
    """A mediation query's mediator and a joint intervention's second
    treatment. Both are variables the question is ABOUT, and neither was
    ever asked whether it has a definition."""
    query = EffectQuery(
        target=ValuedAtom(atom=_atom("y"), value=True),
        intervention=Intervention(atom=_atom("x"), value=True),
        given=(),
        extra_interventions=(Intervention(atom=_atom("b"), value=True),),
        mediator=_atom("m"),
    )
    assert [atom.predicate for atom in atoms_named_by(query)] == [
        "y", "x", "b", "m"]


def test_a_question_says_each_variable_once():
    """Two mentions of one variable are one variable."""
    query = EffectQuery(
        target=ValuedAtom(atom=_atom("y"), value=True),
        intervention=Intervention(atom=_atom("x"), value=True),
        given=(ValuedAtom(atom=_atom("x"), value=False),),
    )
    assert [atom.predicate for atom in atoms_named_by(query)] == ["y", "x"]


def test_what_a_question_holds_that_is_not_a_variable_is_not_one():
    """The counterexample. A question carries words, numbers and choices
    from a vocabulary beside its variables — a monotonicity premise, a
    risk, a population's name — and a reading that swept those up would
    ask a reader for the operational definition of ``0.4``."""
    query = CausationQuery(
        cause=_atom("drug"),
        effect=_atom("death"),
        monotonic=True,
        experimental_risk_treated=0.4,
        experimental_risk_control=0.2,
    )
    assert [atom.predicate for atom in atoms_named_by(query)] == [
        "drug", "death"]


def test_every_note_is_about_a_variable_the_question_names():
    """What makes this species' severity the species' own.

    The gap for an undefined variable used to be IMPORTANT where the query
    named it and INFORMATIONAL otherwise. The second is unreachable, and
    this is why: a note is MADE from the predicates the query names, so
    there is no note the quiet branch could be about. Asked of every row
    in the corpus rather than argued.
    """
    for name in sorted(SHAPES):
        program, stmt = _parsed(name)
        if stmt is None:
            continue
        named = {atom.predicate for atom in atoms_named_by(stmt.query)}
        notes = {note.predicate
                 for note in framing_check.check_framing(program, stmt)}
        assert notes <= named, name
