"""A formula says which value it is about, and the question said it first.

``P(y=1|do(x=1))`` and ``P(y=1|do(x=0))`` are two different quantities on
one graph. The roster check holds the variables a step names; the scope
check holds the names a formula binds. Between them every predicate, every
argument and every bound index is held. The literal each term is TAKEN AT
was held by neither, because a graph has no opinion about a value and a
scope has none either.

What holds it is the question, which named the variable asked about and
each variable conditioned on before any of this ran. A formula may write
the literal the question named, or leave it OPEN -- open is a different
claim rather than a weaker one, and an identification formula for a whole
distribution writes ``None`` where an effect question writes ``True``.

THE INTERVENED VARIABLE IS NOT HELD HERE, and that is measured rather than
forgotten. The first version of this check held it and six stored answers
said no: an effect is a difference between two arms, a question names one
of them, and the formula for the other arm honestly takes x at the other
value. That is written down at the bottom of this file as a test rather
than as a regret.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import (
    Atom, ConstTerm, Intervention, ProbabilityRefExpr, ProductExpr,
    ValuedAtom, VarRef,
)
from themis.verifier.rules import (
    _literals_a_formula_takes_against_the_question,
    _what_the_question_takes_a_variable_at,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name="me"),))


class _Question:
    def __init__(self, target=None, intervention=None, given=()):
        self.target = target
        self.intervention = intervention
        self.given = given


# ------------------------------------------------------- what is read

def test_the_question_names_its_target_and_its_conditions():
    x, y, z = _atom("x"), _atom("y"), _atom("z")
    question = _Question(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=x, value=True),
        given=(ValuedAtom(atom=z, value=False),))
    assert _what_the_question_takes_a_variable_at(question) == {y: True,
                                                               z: False}


def test_the_intervened_variable_is_left_out_on_purpose():
    """An effect is a difference between two arms and the question names
    one of them, so the other arm's formula honestly takes x elsewhere.
    Reading the intervention here refused six stored answers."""
    x = _atom("x")
    question = _Question(intervention=Intervention(atom=x, value=True))
    assert _what_the_question_takes_a_variable_at(question) == {}


def test_a_question_with_none_of_the_three_contributes_nothing():
    """A transport or a discovery question passes through with an empty
    answer, and the walk then makes no claim at all -- silence rather than
    a raise, because a shape this does not describe is not a defect."""
    assert _what_the_question_takes_a_variable_at(object()) == {}


# ------------------------------------------------------- what is held

def _term(predicate: str, value):
    return ProbabilityRefExpr(
        target=ValuedAtom(atom=_atom(predicate), value=value), given=())


def _against(node, taken):
    return list(_literals_a_formula_takes_against_the_question(node, taken))


def test_a_literal_the_question_names_agrees():
    assert _against(_term("y", True), {_atom("y"): True}) == []


def test_a_literal_the_question_does_not_name_is_refused():
    found = _against(_term("y", False), {_atom("y"): True})
    assert [(a.predicate, shown, asked) for a, shown, asked in found] == \
        [("y", False, True)]


def test_an_open_literal_is_a_different_claim_and_not_a_weaker_one():
    """``None`` is what an identification formula writes where an effect
    question writes a value, and the sub-formulas of one estimand do the
    same inside a larger one."""
    assert _against(_term("y", None), {_atom("y"): True}) == []


def test_a_variable_the_question_never_names_is_not_spoken_for():
    """A mediator or a covariate is taken at a value the question never
    mentions. Measured: 17 terms in the stored answers are exactly that,
    and holding them needs a second reader nobody has yet."""
    assert _against(_term("m", True), {_atom("y"): True}) == []


def test_a_bound_index_is_not_a_literal():
    """A reference to a name a sum binds is held by the scope check
    beside this one, and it is not a value anybody took."""
    assert _against(_term("y", VarRef(name="t_y")), {_atom("y"): True}) == []


def test_the_walk_reaches_through_the_containers_a_formula_uses():
    taken = {_atom("y"): True}
    assert len(_against({"a": [_term("y", False)]}, taken)) == 1
    assert len(_against(ProductExpr(terms=(_term("y", False),)), taken)) == 1
    assert _against("y", taken) == []


# ------------------------------------------------------- the corpus


def _flip_literals(node, count) -> None:
    """Flip every boolean literal a valued atom is taken at.

    A bend within the contract: the other member of a two-valued domain,
    which is what the leaf's own declared domain offers. A literal bent to
    a string would be refused by the schema before any rule saw it.
    """
    if isinstance(node, dict):
        # A valued atom is spelled as an ``atom`` beside a ``value`` and
        # carries no kind tag of its own, in the chain and on the envelope
        # alike. Matching on the pair is what finds both.
        if "atom" in node and isinstance(node.get("value"), bool):
            node["value"] = not node["value"]
            count[0] += 1
        for value in node.values():
            _flip_literals(value, count)
    elif isinstance(node, list):
        for value in node:
            _flip_literals(value, count)


def _rows_with_a_literal(where: str) -> list:
    out = []
    for name, pair in SHAPES.items():
        count = [0]
        _flip_literals(copy.deepcopy(pair["result"].get(where) or {}), count)
        if count[0]:
            out.append(name)
    return sorted(out)


CHAIN_ROWS = _rows_with_a_literal("derivation")
ENVELOPE_ROWS = _rows_with_a_literal("formula")


def test_the_rosters_are_the_size_they_were_measured_at():
    """Two rosters: the chain's copy of a formula and the one a reader is
    shown. Both are swept, because they are two claims and one of them
    could be right while the other is not."""
    assert (len(CHAIN_ROWS), len(ENVELOPE_ROWS)) == (29, 108)


def _refused_or_untouched(name: str, where: str) -> str:
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    count = [0]
    _flip_literals(result.get(where) or {}, count)
    assert count[0], "nothing to bend"
    try:
        the_door_for(result)(pair["program"], result)
    except Exception as exc:
        return str(exc)
    return ""


@pytest.mark.parametrize("name", CHAIN_ROWS)
def test_a_flipped_literal_in_the_chain_is_refused(name):
    assert _refused_or_untouched(name, "derivation")


@pytest.mark.parametrize("name", ENVELOPE_ROWS)
def test_a_flipped_literal_on_the_envelope_is_refused(name):
    """Two copies and two claims. The probes elsewhere ask whether the
    estimand COMPUTES the right quantity in sampled models, which a
    formula can pass while naming another literal -- the models are
    sampled to make the numbers agree, not the words."""
    assert _refused_or_untouched(name, "formula")


@pytest.mark.parametrize("name", CHAIN_ROWS)
def test_the_honest_literals_still_pass(name):
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


# ------------------------------------------- the narrowing, recorded

def _rows_taking_the_intervention_elsewhere() -> list:
    """Stored answers whose chain takes the intervened variable at a value
    the question does not name.

    These refused the first version of this check, and they are honest: a
    mediation evaluation carries both arms of a contrast as separate
    inputs of one step, and only one arm can be the one the question
    named.
    """
    from themis.kernel import _premises_of
    from themis.verifier.serialization import derivation_from_dict

    out = []
    for name, pair in SHAPES.items():
        try:
            _ast, _program, statement, _ctx = _premises_of(pair["program"],
                                                           pair["result"])
        except Exception:
            continue
        intervention = getattr(statement.query, "intervention", None)
        atom = getattr(intervention, "atom", None)
        if atom is None:
            continue
        taken = {atom: getattr(intervention, "value", None)}
        chain = pair["result"].get("derivation")
        if not chain:
            continue
        for step in derivation_from_dict(chain):
            if any(_literals_a_formula_takes_against_the_question(
                    step.inputs, taken)):
                out.append(name)
                break
    return sorted(out)


def test_the_other_arm_of_a_contrast_is_not_a_forgery():
    """The narrowing, held by running the answers rather than by asserting
    about them: if this check ever reads the intervention again, every one
    of these stops verifying and this test says so."""
    rows = _rows_taking_the_intervention_elsewhere()
    assert len(rows) == 6, rows
    for name in rows:
        pair = SHAPES[name]
        verify_honestly(pair["program"], pair["result"])
