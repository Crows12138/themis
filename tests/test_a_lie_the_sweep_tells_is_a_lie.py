"""A lie the sweep tells has to be a lie.

The remainder gate calls a leaf held only when every KIND of lie about it
is refused, and two of the principles that makes sound are written down
where it bends: a lie has to be one the contract permits, or the gate
measures the validator; and a bend has to be a different value, or the
gate reports a correct tolerance as a hole. This file holds the third,
which was missing: a bend whose envelope is still TRUE tests nothing, and
reading its acceptance as a hole reports a correct RULE as a hole.

The bend that broke it was the literal ``"x"``, the sweep's "some other
name" for a string. Half this corpus's variables are named ``x``, and a
rule may accept two spellings of one variable on purpose --
``_atom_spellings`` documents doing exactly that, because the two
producers of the SCM display copy key on different things. So the bend
handed that rule the truth it already told, the rule accepted it, and the
leaf naming which variable a counterfactual intervened on was declared
unwitnessed on 41 rows while ``verify_scm_counterfactual_display`` had
been holding it all along.

What this file holds:

- the name the sweep lies with is one neither the program nor the answer
  uses, on every stored row, so it cannot be a spelling of anything the
  answer is about
- the rule that was reported as a hole refuses that name, and accepts the
  bare predicate -- the two halves of saying the rule was right and the
  instrument was wrong
- the name is derived rather than guessed: where the first candidate is
  taken, the next is tried

WHAT THIS FILE DOES NOT CLAIM. Nothing here says the sweep's other bends
are lies. A count bent to zero, a probability bent to 0.9 and a boolean
flipped are all different values, and whether any of them leaves a TRUE
envelope is a question per leaf that this does not ask.
"""
from __future__ import annotations

import pytest

from . import test_every_answer_shape_is_asked_the_same_question as gate


def _strings(document) -> set:
    return {value for _, value in gate._leaves(document)
            if isinstance(value, str)}


@pytest.mark.parametrize("name", sorted(gate.SHAPES))
def test_the_name_the_sweep_lies_with_is_one_nothing_uses(name: str) -> None:
    """A stranger to both documents, row by row.

    Both, because either alone leaves the other free to have the name: the
    answer spells variables the program declares, and a rule reads the two
    against each other.
    """
    pair = gate.SHAPES[name]
    stranger = gate._a_name_neither_document_uses(pair["program"],
                                                  pair["result"])
    assert stranger not in _strings(pair["program"])
    assert stranger not in _strings(pair["result"])


def test_the_name_is_derived_rather_than_guessed() -> None:
    """Where the first candidate is taken, another is found."""
    taken = {"statements": ["x", "xz", "xzz"]}
    assert gate._a_name_neither_document_uses(taken, {}) == "xzzz"
    assert gate._a_name_neither_document_uses({}, {}) == "x"


def _a_counterfactual_row() -> tuple:
    """A stored answer whose intervened variable is spelled with an x."""
    for name, pair in sorted(gate.SHAPES.items()):
        block = ((pair["result"].get("extensions") or {})
                 .get("scm_counterfactual") or {})
        variable = (block.get("intervention") or {}).get("variable")
        if isinstance(variable, str) and variable.startswith("x("):
            return name, pair
    pytest.skip("no stored counterfactual names its variable with an x")


def test_the_rule_reported_as_a_hole_refuses_a_stranger() -> None:
    """The rule was right: a name nothing has is not its variable."""
    _, pair = _a_counterfactual_row()
    program, result = pair["program"], pair["result"]
    path = ("extensions", "scm_counterfactual", "intervention", "variable")
    stranger = gate._a_name_neither_document_uses(program, result)
    bad = gate._tamper(result, path, stranger)
    doors = gate._reading_doors(program, result)
    assert any(gate._refuses(door, program, bad) for door in doors)


def test_the_bare_predicate_is_not_a_lie_about_that_variable() -> None:
    """And the instrument was wrong: the bend it used said the same thing.

    Kept beside the test above rather than deleted with the bend, because
    "the rule accepts this" is the whole of why the leaf was declared, and
    a reader of the declared remainder's history has no other way to see
    it.
    """
    _, pair = _a_counterfactual_row()
    program, result = pair["program"], pair["result"]
    path = ("extensions", "scm_counterfactual", "intervention", "variable")
    bare = gate._at(result, path).split("(")[0]
    same = gate._tamper(result, path, bare)
    doors = gate._reading_doors(program, result)
    assert not any(gate._refuses(door, program, same) for door in doors)
