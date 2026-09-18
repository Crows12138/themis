"""A formula is a scope, and a scope is closed in both directions.

A sum writes a name and then spends it: ``SumExpr`` carries a ``BindDecl``
and the terms underneath refer back to it with a ``VarRef``. Neither is an
atom, and the only reader a formula had was looking for atoms -- the walk
widened in #701 reaches every variable a formula NAMES and holds it to the
graph's roster, and a graph has nothing whatever to say about the name a
sum chose for its own index.

So a formula could bind ``t_c_me`` and refer to anything it liked. 18
declared leaves sat exactly there: ten binders and eight references.

What holds them needs no data, no program and no question:

- every name used is one an enclosing sum binds, and
- every name bound is one the body under it uses.

Both directions, because one alone is half a scope. Without the first a
reference can point at nothing; without the second a binder can be renamed
freely, since nothing below it would notice.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import (
    Atom, BindDecl, ConstTerm, ProbabilityRefExpr, ProductExpr, SumExpr,
    ValuedAtom, VarRef,
)
from themis.verifier.errors import RuleCheckFailed
from themis.verifier.rules import (
    _every_name_a_formula_uses_is_one_it_binds,
    _names_a_formula_uses,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _scope(node, bound=frozenset()) -> None:
    _every_name_a_formula_uses_is_one_it_binds(node, bound, 0, "r")


# ------------------------------------------------------------- the unit

def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name="me"),))


def _sum(name: str, over: str, body):
    return SumExpr(bind=BindDecl(name=name), over=_atom(over), body=body)


def _term(predicate: str, value):
    return ProbabilityRefExpr(
        target=ValuedAtom(atom=_atom(predicate), value=value), given=())


def test_a_sum_that_spends_the_name_it_binds_is_a_scope():
    _scope(_sum("t_c", "c", ProductExpr(terms=(_term("c", VarRef(name="t_c")),))))


def test_a_reference_to_a_name_nothing_binds_is_refused():
    with pytest.raises(RuleCheckFailed, match="no sum binds it"):
        _scope(ProductExpr(terms=(_term("c", VarRef(name="t_c")),)))


def test_a_binder_no_term_spends_is_refused():
    """The direction that is easy to leave out, and the one that makes the
    binder itself holdable: without it, a name nothing refers to can be
    rewritten to anything at all and no reader would notice."""
    with pytest.raises(RuleCheckFailed, match="a binder no term spends"):
        _scope(_sum("t_c", "c", ProductExpr(terms=(_term("c", True),))))


def test_a_name_is_bound_for_what_is_under_it_and_not_beside_it():
    """Scope, not a flat set of names. A sum's binder reaches its own body
    and stops there."""
    inner = _sum("t_c", "c", ProductExpr(terms=(_term("c", VarRef(name="t_c")),)))
    beside = ProductExpr(terms=(_term("m", VarRef(name="t_c")),))
    with pytest.raises(RuleCheckFailed, match="no sum binds it"):
        _scope(ProductExpr(terms=(inner, beside)))


def test_a_sum_ranges_in_the_outer_scope():
    """``over`` is the variable being summed, not the index: it is read
    where the sum stands, not inside it."""
    body = ProductExpr(terms=(_term("c", VarRef(name="t_c")),))
    _scope(_sum("t_c", "c", body))


def test_nesting_binds_both_names():
    body = ProductExpr(terms=(_term("c", VarRef(name="t_c")),
                              _term("m", VarRef(name="t_m"))))
    _scope(_sum("t_c", "c", _sum("t_m", "m", body)))


def test_the_walk_reaches_into_every_container_a_step_uses():
    """Same container vocabulary as the atom walk, for the same reason a
    formula needed one: mappings, sequences and frozen dataclasses."""
    ref = VarRef(name="t_c")
    assert sorted(_names_a_formula_uses({"a": [ref]})) == ["t_c"]
    assert sorted(_names_a_formula_uses((ref, {"b": ref}))) == ["t_c", "t_c"]
    assert sorted(_names_a_formula_uses(_term("c", ref))) == ["t_c"]
    assert sorted(_names_a_formula_uses("t_c")) == []


# ------------------------------------------------------------ the corpus

def _rows_with_a_sum() -> list:
    def has_sum(node) -> bool:
        if isinstance(node, dict):
            return node.get("kind") == "sum" or any(
                has_sum(v) for v in node.values())
        if isinstance(node, list):
            return any(has_sum(v) for v in node)
        return False

    return sorted(name for name, pair in SHAPES.items()
                  if has_sum(pair["result"].get("derivation") or {}))


SUM_ROWS = _rows_with_a_sum()


def _rows_this_check_alone_refuses() -> list:
    """The answers where renaming a binder is refused by THIS check and
    not by something else.

    Measured rather than typed out, and measured rather than read off the
    declaration: the declaration no longer names these leaves, so a roster
    taken from it would be empty and every test under it would quietly
    stop running. Which rules re-derive a formula from a template is also
    not a fact this file should carry a copy of.
    """
    out = []
    for name in SUM_ROWS:
        pair = SHAPES[name]
        result = copy.deepcopy(pair["result"])
        count = [0]
        _bend_binders(result.get("derivation") or {}, count)
        if not count[0]:
            continue
        try:
            the_door_for(result)(pair["program"], result)
        except Exception as exc:
            if "a binder no term spends" in str(exc):
                out.append(name)
    return sorted(out)


def test_the_rosters_are_the_size_they_were_measured_at():
    """Two numbers answering different questions. Every answer with a sum
    in its chain says how far the sweep below reaches; the rows this check
    alone refuses say where it is the reason rather than one reason among
    several.

    The second number is larger than the count of rows the declaration
    used to name, and the difference is worth keeping straight: a binder
    is a DECLARED leaf only where the formula is a step's INPUT, and most
    of these answers carry the formula as a step's output instead. So
    this check reaches further than the leaves it closed, which is the
    ordinary case for a rule stated about a shape rather than about a
    field.
    """
    assert len(SUM_ROWS) == 20, len(SUM_ROWS)
    assert len(_rows_this_check_alone_refuses()) == 15


def _is_refused(name: str, result: dict) -> None:
    """Refused is the claim. WHICH door refuses is not: several of these
    answers carry a formula some other rule re-derives from a template,
    and renaming a binder breaks that template first. A gate that
    insisted on its own message would be reporting other rules' work as
    missing. Where this check is the only reader -- the rows the
    declaration still names -- the message is pinned below.
    """
    pair = SHAPES[name]
    with pytest.raises(Exception):
        the_door_for(result)(pair["program"], result)


def _bend_binders(node, count) -> None:
    if isinstance(node, dict):
        bind = node.get("bind")
        if isinstance(bind, dict) and isinstance(bind.get("name"), str):
            bind["name"] = bind["name"] + "_forged"
            count[0] += 1
        for value in node.values():
            _bend_binders(value, count)
    elif isinstance(node, list):
        for value in node:
            _bend_binders(value, count)


def _bend_references(node, count) -> None:
    if isinstance(node, dict):
        if node.get("kind") == "var_ref" and isinstance(node.get("name"), str):
            node["name"] = node["name"] + "_forged"
            count[0] += 1
        for value in node.values():
            _bend_references(value, count)
    elif isinstance(node, list):
        for value in node:
            _bend_references(value, count)


@pytest.mark.parametrize("name", SUM_ROWS)
def test_renaming_a_binder_is_refused(name):
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    count = [0]
    _bend_binders(result.get("derivation") or {}, count)
    assert count[0], "no binder to bend"
    _is_refused(name, result)


@pytest.mark.parametrize("name", SUM_ROWS)
def test_renaming_a_reference_is_refused(name):
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    count = [0]
    _bend_references(result.get("derivation") or {}, count)
    if not count[0]:
        pytest.skip("this answer's sums are spelled without a reference")
    _is_refused(name, result)


@pytest.mark.parametrize("name", SUM_ROWS)
def test_the_honest_formula_still_passes(name):
    """Said once per row, because a check that refuses every formula
    refuses the forgeries too and would look identical above."""
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])
