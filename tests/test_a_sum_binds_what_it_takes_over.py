"""A sum in the ID recursion binds what it takes over, in one operation.

``value=None`` on an occurrence means "bound by whoever holds this
formula" — the query, or an enclosing construct not yet applied. A sum
that takes the atom over becomes that holder, so the occurrence has to
point at the sum's own name. Building the sum and pointing the
occurrences at it are one operation, and this module is the reason they
cannot be written as two: half of it shipping alone produces a formula
that is malformed where nothing looks. The evaluator meets the hole much
later, inside ``P(m | x=True)``, and reports ``InsufficientTheta`` — a
message about missing data, for a formula whose binder is sitting
directly above the hole in the tree.

The denominator is every ``SumExpr(...)`` construction in
``themis/runtime/c_factor.py``, read off the source rather than off a
run, so a branch no case reaches is checked exactly like one every case
reaches.

Two shapes appear there and only one is a binder. A call passing
``bind=formula.bind`` is a structure-preserving rebuild — a walk putting
a tree back together around a changed body, carrying the binder that was
already there. A call passing ``bind=BindDecl(...)`` names a NEW
variable, and that is the one this rule is about.

Which occurrences a sum takes over is the caller's decision and not a
property of the atom: Tian's conditioning ratio puts the query's own
target in the numerator as a query-bound hole and in the denominator
under its own ``Σ_y``, the normalising constant. Measured on the ID
corpus, 21 shipped estimands do exactly that. So no rule of the form
"this atom is the query's Y, therefore it is free" can be right, and the
primitive takes the set from its caller.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis.runtime.c_factor import (
    _bind_and_sum,
    _canonical_bind_name,
)
from themis.types import (
    Atom,
    BindDecl,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
MODULE = REPO_ROOT / "themis" / "runtime" / "c_factor.py"

#: The one function allowed to name a new sum variable.
PRIMITIVE = "_bind_and_sum"


def _new_binders(source: str) -> list[tuple[str, int]]:
    """(enclosing function, line) for every construction of a NEW binder.

    A ``SumExpr(...)`` whose ``bind`` argument is a ``BindDecl(...)`` call
    introduces a variable; one that forwards an existing ``bind`` does
    not. Nothing else about the call matters here.
    """
    tree = ast.parse(source)
    found: list[tuple[str, int]] = []

    def walk(node: ast.AST, enclosing: str) -> None:
        for child in ast.iter_child_nodes(node):
            here = enclosing
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                here = child.name
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Name)
                and child.func.id == "SumExpr"
            ):
                for keyword in child.keywords:
                    if (
                        keyword.arg == "bind"
                        and isinstance(keyword.value, ast.Call)
                        and isinstance(keyword.value.func, ast.Name)
                        and keyword.value.func.id == "BindDecl"
                    ):
                        found.append((here, child.lineno))
            walk(child, here)

    walk(tree, "<module>")
    return found


def test_every_new_sum_variable_is_named_by_the_one_primitive():
    """The rule, over the recursion's own source."""
    elsewhere = [
        (where, line)
        for where, line in _new_binders(MODULE.read_text(encoding="utf-8"))
        if where != PRIMITIVE
    ]
    assert not elsewhere, (
        "a sum variable is named outside "
        f"{PRIMITIVE}: {elsewhere}. Wrapping without binding leaves the "
        "occurrences under it carrying value=None, which the evaluator "
        "reports as missing data rather than as a malformed formula."
    )


def test_the_rule_refuses_a_binder_built_anywhere_else():
    """And it says no to the thing it exists to say no to."""
    source = "\n".join([
        "def _some_new_step(body, atom):",
        "    return SumExpr(",
        "        bind=BindDecl(name='t_m'),",
        "        over=atom,",
        "        body=body,",
        "    )",
    ])
    assert _new_binders(source) == [("_some_new_step", 2)]


def test_a_rebuild_is_not_a_binder():
    """A walk carrying an existing bind through is not naming anything."""
    source = "\n".join([
        "def _walk(formula, fn):",
        "    return SumExpr(",
        "        bind=formula.bind,",
        "        over=formula.over,",
        "        body=_walk(formula.body, fn),",
        "    )",
    ])
    assert _new_binders(source) == []


def _hole(atom: Atom) -> ProbabilityRefExpr:
    return ProbabilityRefExpr(target=ValuedAtom(atom=atom, value=None), given=())


def test_taking_an_atom_over_points_its_occurrences_at_the_sum():
    m = Atom(predicate="m", args=())
    out = _bind_and_sum(_hole(m), frozenset({m}), (m,))
    assert isinstance(out, SumExpr)
    assert out.over == m
    assert out.bind.name == _canonical_bind_name(m)
    assert out.body.target.value == VarRef(name=out.bind.name)


def test_an_occurrence_bound_nearer_is_left_where_it_is():
    """A VarRef is already someone's; a do-value is nobody's to take."""
    m = Atom(predicate="m", args=())
    x = Atom(predicate="x", args=())
    inner = VarRef(name="t_m_inner")
    body = ProductExpr(terms=(
        ProbabilityRefExpr(target=ValuedAtom(atom=m, value=inner), given=()),
        ProbabilityRefExpr(target=ValuedAtom(atom=x, value=True), given=()),
    ))
    out = _bind_and_sum(body, frozenset({m, x}), (m, x))
    kept = {t.target.atom.predicate: t.target.value for t in _innermost(out).terms}
    assert kept["m"] == inner
    assert kept["x"] is True


def _innermost(node):
    while isinstance(node, SumExpr):
        node = node.body
    return node


@pytest.mark.parametrize("over", [frozenset(), None])
def test_taking_nothing_over_builds_no_sum(over):
    """An empty set is not a degenerate sum, it is no sum."""
    m = Atom(predicate="m", args=())
    body = _hole(m)
    assert _bind_and_sum(body, frozenset(over or ()), (m,)) is body
