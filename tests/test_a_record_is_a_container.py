"""A record is a container, and a formula is a record.

``_every_atom_a_step_names_is_one_the_graph_has`` is the first thing
``dispatch_rule`` does, on every step of every derivation, and its own
prose says why: a step reasoning about a graph cannot name a variable
that graph does not have, whatever it then does with it. It reaches the
atoms ``atoms_within`` can see, and that walk knew three containers -- a
mapping, a sequence, and one field called ``atom``.

A formula is none of the three. ``SumExpr``, ``ProductExpr``,
``ProbabilityRefExpr`` and ``FractionExpr`` are frozen dataclasses, so
every atom a step was handed inside a formula was invisible to the only
rule written to hold it: 399 of them across the stored answers, on nine
step rules, and 94 declared leaves that are one of their predicates or
argument names. Nothing was wrong with what that rule asks. The walk
could not see far enough to ask it.

Two halves are held here, because "a dataclass is a container too" is a
replacement rather than an addition: a ``ValuedAtom`` IS a dataclass
whose field is called ``atom``, so the general branch has to reach
everything the special case reached before the special case can go. It
does, and it reaches what the special case could not.

``Atom`` still returns before the general branch. Its arguments are
terms -- a name in a position, not a variable -- and yielding one would
say a unit is something the graph must have a node for.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import (
    Atom,
    BindDecl,
    ConstantExpr,
    ConstTerm,
    FractionExpr,
    Intervention,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarTerm,
)
from themis.verifier.rules import atoms_within

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: What the rule this walk feeds says when it refuses. Matched rather
#: than accepting any exception, because a test that takes any refusal
#: passes on a row the door was already refusing for another reason.
COMPLAINT = "has no such variable"


def _atom(predicate: str, *args: str) -> Atom:
    return Atom(predicate=predicate,
                args=tuple(ConstTerm(name=a) for a in args))


# -------------------------------------------- the containers it knew of


def test_a_bare_atom_is_itself():
    a = _atom("x", "me")
    assert list(atoms_within(a)) == [a]


def test_a_mapping_is_walked():
    a, b = _atom("x", "me"), _atom("y", "me")
    assert set(atoms_within({"treatment": a, "outcome": b})) == {a, b}


def test_a_sequence_is_walked():
    a, b = _atom("x", "me"), _atom("y", "me")
    assert set(atoms_within([a, (b,), frozenset({b})])) == {a, b}


def test_a_string_is_not_a_sequence_to_walk():
    assert list(atoms_within("predicate")) == []
    assert list(atoms_within(b"predicate")) == []


# -------------------------------- what the special case reached, still


def test_a_valued_atom_still_yields_its_atom():
    """The case the ``atom`` field existed for. It is a dataclass field
    like any other now, which is the whole reason the special case can go
    rather than sit beside the branch that subsumes it."""
    a = _atom("x", "me")
    assert list(atoms_within(ValuedAtom(atom=a, value=True))) == [a]


def test_an_intervention_still_yields_its_atom():
    a = _atom("x", "me")
    assert list(atoms_within(Intervention(atom=a, value=True))) == [a]


# --------------------------------------- what it could not reach at all


def test_an_atom_inside_a_probability_reference_is_reached():
    """The node every identification formula is built out of."""
    target, given = _atom("y", "me"), _atom("x", "me")
    ref = ProbabilityRefExpr(
        target=ValuedAtom(atom=target, value=True),
        given=(ValuedAtom(atom=given, value=True),))
    assert set(atoms_within(ref)) == {target, given}


def test_the_atom_a_sum_is_taken_over_is_reached():
    """``SumExpr.over`` is an atom in a field of its own: not a mapping
    entry, not a sequence member, and not called ``atom``."""
    over, inner = _atom("c", "me"), _atom("y", "me")
    node = SumExpr(bind=BindDecl(name="t_c_me"), over=over,
                   body=ProbabilityRefExpr(
                       target=ValuedAtom(atom=inner, value=True), given=()))
    assert set(atoms_within(node)) == {over, inner}


def test_both_sides_of_a_fraction_are_reached():
    """A conditional identification is a ratio of two formulas. A walk
    that stopped at the first would hold the numerator and leave the
    denominator free -- half a formula audited, and no way to tell from
    outside which half."""
    top, bottom = _atom("y", "me"), _atom("z", "me")
    node = FractionExpr(
        numerator=ProductExpr(terms=(ProbabilityRefExpr(
            target=ValuedAtom(atom=top, value=True), given=()),)),
        denominator=ProbabilityRefExpr(
            target=ValuedAtom(atom=bottom, value=True), given=()))
    assert set(atoms_within(node)) == {top, bottom}


def test_a_dataclass_holding_no_atom_yields_nothing():
    assert list(atoms_within(ConstantExpr(value=1.0))) == []
    assert list(atoms_within(BindDecl(name="t_c_me"))) == []


def test_a_dataclass_is_not_its_own_class():
    """``is_dataclass`` says yes to the CLASS as well as to an instance
    of it, and ``fields()`` of a class reads the defaults off the class
    object. A walk that did not say which of the two it meant would
    wander into whatever a field's default happens to be."""
    assert dataclasses.is_dataclass(ConstantExpr)
    assert list(atoms_within(ConstantExpr)) == []


def test_an_atoms_arguments_are_not_atoms():
    """The early return this walk keeps, stated as the claim it makes."""
    a = _atom("x", "me")
    assert list(atoms_within(a)) == [a]
    assert all(isinstance(t, (ConstTerm, VarTerm)) for t in a.args)


# ------------------------------------------------------ and on the corpus


def _formula_sites(node, path=()):
    """Every place a stored step writes an atom's name inside a formula.

    Read off the SERIALISED form, because that is the document a forgery
    is planted in. Yields the path to a ``predicate`` and the path to
    each argument's ``name``, which are the two halves of an atom.
    """
    if isinstance(node, dict):
        if isinstance(node.get("predicate"), str):
            yield path + ("predicate",)
            for i, arg in enumerate(node.get("args") or ()):
                if isinstance(arg, dict) and isinstance(arg.get("name"), str):
                    yield path + ("args", i, "name")
        for key, value in node.items():
            yield from _formula_sites(value, path + (key,))
    elif isinstance(node, list):
        for i, value in enumerate(node):
            yield from _formula_sites(value, path + (i,))


def _steps_with_a_formula(result):
    for i, step in enumerate(
            ((result.get("derivation") or {}).get("steps") or ())):
        inputs = step.get("inputs")
        if not isinstance(inputs, dict):
            continue
        for key, value in inputs.items():
            if key.endswith("formula") and isinstance(value, dict):
                yield i, key


def _at(node, path):
    for step in path:
        node = node[step]
    return node


def _put(node, path, value):
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value


def _first_site(result, want):
    """The path to the first half-of-an-atom of the asked kind, in the
    first formula any step of this answer was handed."""
    for index, key in _steps_with_a_formula(result):
        base = ("derivation", "steps", index, "inputs", key)
        for site in _formula_sites(_at(result, base)):
            if site[-1] == want:
                return base + site
    return None


#: Every stored answer that hands a step a formula, and the two halves of
#: an atom its formulas actually write. Derived rather than listed, so a
#: producer that starts writing one is asked the same question without
#: anybody remembering to add it here.
FORMULA_ROWS = sorted(
    name for name, pair in SHAPES.items()
    if any(True for _ in _steps_with_a_formula(pair["result"])))
PREDICATE_ROWS = sorted(
    name for name in FORMULA_ROWS
    if _first_site(SHAPES[name]["result"], "predicate"))
ARGUMENT_ROWS = sorted(
    name for name in FORMULA_ROWS
    if _first_site(SHAPES[name]["result"], "name"))


def test_the_corpus_asks_these_questions_of_something():
    """A roster that came out empty would make every test below pass
    while asking nothing. Pinned, so a corpus losing its formulas says so
    here rather than by going quiet."""
    assert (len(FORMULA_ROWS), len(PREDICATE_ROWS), len(ARGUMENT_ROWS)) == \
        (31, 23, 20)


@pytest.mark.parametrize("name", FORMULA_ROWS)
def test_an_answer_whose_step_carries_a_formula_is_accepted(name):
    """First, because a forgery refused by an answer the doors already
    refuse proves nothing."""
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


@pytest.mark.parametrize("name", PREDICATE_ROWS)
def test_a_renamed_variable_inside_a_formula_is_refused(name):
    """A predicate no node of the graph carries, written where a step
    says which variables it reasoned over.

    Refused, by whichever rule gets there first. WHICH one is a different
    question, asked below; this one is what a caller gets.
    """
    pair = SHAPES[name]
    site = _first_site(pair["result"], "predicate")
    bad = copy.deepcopy(pair["result"])
    _put(bad, site, _at(pair["result"], site) + "_forged")
    with pytest.raises(Exception):
        the_door_for(pair["result"])(pair["program"], bad)


@pytest.mark.parametrize("name", ARGUMENT_ROWS)
def test_a_re_argued_variable_inside_a_formula_is_refused(name):
    """An atom's other half. ``x(u)`` and ``x(nobody)`` are two
    variables, which is what the rule this walk feeds already says in its
    own prose -- it simply never saw these."""
    pair = SHAPES[name]
    site = _first_site(pair["result"], "name")
    bad = copy.deepcopy(pair["result"])
    _put(bad, site, _at(pair["result"], site) + "_forged")
    with pytest.raises(Exception):
        the_door_for(pair["result"])(pair["program"], bad)


def _who_speaks(kind: str) -> dict:
    """How many rows each of the two answers speaks for."""
    tally = {"this walk": 0, "a witness comparison": 0}
    for name in (PREDICATE_ROWS if kind == "predicate" else ARGUMENT_ROWS):
        pair = SHAPES[name]
        site = _first_site(pair["result"], kind)
        bad = copy.deepcopy(pair["result"])
        _put(bad, site, _at(pair["result"], site) + "_forged")
        try:
            the_door_for(pair["result"])(pair["program"], bad)
        except Exception as exc:                                # noqa: BLE001
            where = ("this walk" if COMPLAINT in str(exc)
                     else "a witness comparison")
            tally[where] += 1
    return tally


@pytest.mark.parametrize("kind", ["predicate", "name"])
def test_which_rule_speaks_for_a_forged_variable(kind):
    """The split, and why there is one.

    A formula an earlier rule can compare against a WITNESS is caught
    there: an effect identified through the back or the front door has a
    prior step holding the formula that identification produced, and a
    renamed variable stops matching it. Those rows were never free.

    The rest have no witness to compare against -- Tian, IDC, ID* and a
    transport formula are identifications with no back-door twin -- and
    they are the rows this walk reaches. Pinned per half of an atom,
    because a narrowing that only lost one half would otherwise leave the
    other half's tests still passing.
    """
    assert _who_speaks(kind) == {
        "predicate": {"this walk": 14, "a witness comparison": 9},
        "name": {"this walk": 11, "a witness comparison": 9},
    }[kind]
