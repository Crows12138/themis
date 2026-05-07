"""Iter 144 — generic property pin: every SumExpr.bind name MUST
appear as a VarRef somewhere in the bound atom's value within
its body. Otherwise the sum is degenerate (the bind binds nothing
the body reads), which is exactly the bug iter 141 shipped and
iter 143 retracted.

Iter 141's `_build_q_factor` shortcut produced
``Σ_x P(x=True) · P(y|x=True, m=True)``: the SumExpr bound
``t_x_me`` over atom X but the body's ProbabilityRefExpr terms
had ``ValuedAtom(atom=X, value=True)`` (literal True) instead of
``ValuedAtom(atom=X, value=VarRef('t_x_me'))``. Tests passed
because they only checked structural properties (identifiable=True,
formula non-None, repr contains x/y/m tokens).

This file plugs that gap with two layers:

1. ``find_degenerate_sums(formula)`` — pure helper, walks every
   SumExpr and returns a list of bind names whose body never
   references them via VarRef. Empty list = well-formed.

2. Self-tests for the helper itself + audits of existing
   identification paths.

Iter 144 DISCOVERY: the helper, applied to existing Tian Lines
1-6 formulas (which the test suite had long claimed work), flagged
degenerate sums in BOTH the pure-DAG chain AND the disjoint-
Y-component cases. Root cause was the same as iter 141's bug:
``_atom_to_target_va(atom)`` returned ``value=state.x_value``
literal whenever ``atom ∈ state.x``, and Line 4's multi-c-
component sub-recursion enriched ``state.x = V \\ s_i`` so
non-intervention atoms (M, Z1, Z2) got the literal do-value
substituted instead of becoming bind variables.

Iter 145 FIX: split ``_IdState.x`` (algorithmic recursion variable,
mutates) from ``_IdState.do_atoms`` (user's true intervention,
fixed across recursion). ``_atom_to_target_va`` now substitutes
literal values only for ``atom ∈ state.do_atoms``; algorithmic-x-
only atoms get VarRef bind names. The audit tests below now pass.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime import c_factor
from themis.types import (
    Atom,
    ConstTerm,
    FormulaExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


# ---------------------------------------------------------------------------
# Property checker
# ---------------------------------------------------------------------------


def _collect_varrefs_in_atom(va: ValuedAtom, names: set[str]) -> None:
    if isinstance(va.value, VarRef):
        names.add(va.value.name)


def _collect_varrefs(formula: FormulaExpr, names: set[str]) -> None:
    """Walk ``formula`` and add every ``VarRef.name`` that appears in
    any ValuedAtom's value slot to ``names``."""
    if isinstance(formula, ProbabilityRefExpr):
        _collect_varrefs_in_atom(formula.target, names)
        for g in formula.given:
            _collect_varrefs_in_atom(g, names)
    elif isinstance(formula, ProductExpr):
        for term in formula.terms:
            _collect_varrefs(term, names)
    elif isinstance(formula, SumExpr):
        _collect_varrefs(formula.body, names)
    # ConstantExpr / fall-through: no atoms to inspect


def find_degenerate_sums(formula: FormulaExpr) -> list[str]:
    """Return a list of ``SumExpr.bind.name`` values whose body does
    NOT reference the bind via any VarRef. Empty list = formula is
    well-formed wrt sum bindings.

    A degenerate sum is one where the binder declares
    ``BindDecl(name=N)`` but no descendant ValuedAtom has
    ``value=VarRef(name=N)``. Such a sum is mathematically a no-op
    (constant sum over a free variable that never appears).
    """
    bad: list[str] = []
    _walk_sums(formula, bad)
    return bad


def _walk_sums(formula: FormulaExpr, bad: list[str]) -> None:
    if isinstance(formula, SumExpr):
        body_refs: set[str] = set()
        _collect_varrefs(formula.body, body_refs)
        if formula.bind.name not in body_refs:
            bad.append(formula.bind.name)
        _walk_sums(formula.body, bad)
    elif isinstance(formula, ProductExpr):
        for term in formula.terms:
            _walk_sums(term, bad)
    # Probability / Constant: no nested sums


# ---------------------------------------------------------------------------
# Self-test: the helper itself catches the iter 141 buggy shape
# ---------------------------------------------------------------------------


def test_helper_catches_degenerate_sum_synthetic():
    """Hand-construct the iter 141 buggy shape and confirm the helper
    flags it. Without this self-test the helper itself could regress
    silently."""
    x = _A("x")
    y = _A("y")
    # Σ_{t_x_me over X} P(x=True | _) · P(y | x=True)
    # — bind 't_x_me' is declared but body references value=True (literal).
    body = ProductExpr(terms=(
        ProbabilityRefExpr(
            target=ValuedAtom(atom=x, value=True),  # literal — not VarRef
            given=(),
        ),
        ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=None),
            given=(ValuedAtom(atom=x, value=True),),  # literal — not VarRef
        ),
    ))
    from themis.types import BindDecl
    f = SumExpr(bind=BindDecl(name="t_x_me"), over=x, body=body)
    bad = find_degenerate_sums(f)
    assert "t_x_me" in bad, (
        f"Helper failed to catch degenerate sum; bad={bad}"
    )


def test_helper_passes_well_formed_sum():
    """Hand-construct a correctly-bound sum: Σ_{t_x_me over X}
    P(x=VarRef('t_x_me')). The bind is referenced by body — should
    not flag."""
    x = _A("x")
    body = ProbabilityRefExpr(
        target=ValuedAtom(atom=x, value=VarRef(name="t_x_me")),
        given=(),
    )
    from themis.types import BindDecl
    f = SumExpr(bind=BindDecl(name="t_x_me"), over=x, body=body)
    assert find_degenerate_sums(f) == []


# ---------------------------------------------------------------------------
# Real-formula audit: existing Tian Lines 1-6 paths must produce
# well-formed formulas (no degenerate sums).
# ---------------------------------------------------------------------------


def test_tian_pure_dag_chain_no_degenerate_sums():
    """X → M → Y, no bidirected. Tian Line 6 path."""
    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    r = c_factor.identify_via_tian(g, frozenset(), x, y, x_value=True)
    assert r.formula is not None
    bad = find_degenerate_sums(r.formula)
    assert bad == [], (
        f"Tian product-form formula has degenerate sums: {bad}"
    )


def test_tian_disjoint_y_component_no_degenerate_sums():
    """X → Z1, X → Z2, Z1 ↔ Z2, Z1 → Y, Z2 → Y. Tian Line 4 + 6."""
    x, z1, z2, y = _A("x"), _A("z1"), _A("z2"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, z1), (x, z2), (z1, y), (z2, y)])
    bi = frozenset({frozenset({z1, z2})})
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.formula is not None
    bad = find_degenerate_sums(r.formula)
    assert bad == [], (
        f"Tian Line 4 multi-c-component formula has degenerate sums: {bad}"
    )
