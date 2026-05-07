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


# ---------------------------------------------------------------------------
# Audits for the other formula emitters: formula_builder.py
# (backdoor / front-door). These have always built well-formed formulas
# (no degenerate sums) — pinning that fact so any future refactor that
# breaks bind-binding is caught immediately.
# ---------------------------------------------------------------------------


def test_backdoor_single_z_no_degenerate_sums():
    """Σ_z P(Y|X=x, Z=z) · P(Z=z). Single binder, body must reference z."""
    from themis.runtime.formula_builder import backdoor_formula
    from themis.types import ValuedAtom

    y, x, z = _A("y"), _A("x"), _A("z")
    target = ValuedAtom(atom=y, value=None)
    intv = ValuedAtom(atom=x, value=True)
    f = backdoor_formula(target, intv, (z,))
    bad = find_degenerate_sums(f)
    assert bad == [], f"backdoor (1 Z) has degenerate sums: {bad}"


def test_backdoor_chain_rule_two_z_no_degenerate_sums():
    """Σ_z1 Σ_z2 P(Y|X, Z1, Z2) · P(Z1) · P(Z2|Z1). Chain rule
    expansion — both binders must be referenced by body."""
    from themis.runtime.formula_builder import backdoor_formula
    from themis.types import ValuedAtom

    y, x, z1, z2 = _A("y"), _A("x"), _A("z1"), _A("z2")
    target = ValuedAtom(atom=y, value=None)
    intv = ValuedAtom(atom=x, value=True)
    f = backdoor_formula(target, intv, (z1, z2))
    bad = find_degenerate_sums(f)
    assert bad == [], f"backdoor (chain-rule 2 Z) has degenerate sums: {bad}"


def test_frontdoor_single_mediator_no_degenerate_sums():
    """Σ_m P(M=m|X) · Σ_x' P(Y|X=x', M=m) · P(X=x'). Two binders,
    each must be referenced by body."""
    from themis.runtime.formula_builder import front_door_formula
    from themis.types import ValuedAtom

    y, x, m = _A("y"), _A("x"), _A("m")
    target = ValuedAtom(atom=y, value=None)
    intv = ValuedAtom(atom=x, value=True)
    f = front_door_formula(target, intv, (m,))
    bad = find_degenerate_sums(f)
    assert bad == [], f"front-door (1 mediator) has degenerate sums: {bad}"


def test_frontdoor_two_mediators_no_degenerate_sums():
    """Multi-mediator front-door (Phase 6.front-door-multi).
    Σ_m1 Σ_m2 chain rule + Σ_x' inner. Three binders."""
    from themis.runtime.formula_builder import front_door_formula
    from themis.types import ValuedAtom

    y, x, m1, m2 = _A("y"), _A("x"), _A("m1"), _A("m2")
    target = ValuedAtom(atom=y, value=None)
    intv = ValuedAtom(atom=x, value=True)
    f = front_door_formula(target, intv, (m1, m2))
    bad = find_degenerate_sums(f)
    assert bad == [], f"front-door (2 mediators) has degenerate sums: {bad}"


# ---------------------------------------------------------------------------
# Numerical evaluation pin: iter 145 fixed the Tian degenerate-sum bug;
# this section evaluates real Tian formulas against a concrete Theta to
# verify the math is RIGHT, not just the structure. Pre-iter-145 the
# formula was structurally well-formed-looking but mathematically wrong;
# only numerical eval against a known reference catches that class of bug.
# ---------------------------------------------------------------------------


def _bind_target_value(formula, target_atom, value):
    """Walk formula and replace any ValuedAtom whose atom == target_atom
    AND value is None with value=``value``. Used to bind the outermost
    query target Y to a concrete value before numerical evaluation."""
    from themis.types import (
        ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, ValuedAtom,
    )

    def _bva(va):
        if va.atom == target_atom and va.value is None:
            return ValuedAtom(atom=va.atom, value=value)
        return va

    if isinstance(formula, ConstantExpr):
        return formula
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(
            target=_bva(formula.target),
            given=tuple(_bva(g) for g in formula.given),
        )
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(
            _bind_target_value(t, target_atom, value) for t in formula.terms
        ))
    if isinstance(formula, SumExpr):
        return SumExpr(
            bind=formula.bind,
            over=formula.over,
            body=_bind_target_value(formula.body, target_atom, value),
        )
    return formula


def test_tian_pure_chain_evaluates_to_correct_ate():
    """X → M → Y, no bidirected. Tian formula is
    Σ_M P(M|X=True) · P(Y|X=True, M=m). Pre-iter-145 this evaluated
    to P(Y|X=True, M=True) (degenerate sum collapsed); post-fix it
    must marginalize M correctly to give the true ATE-style value.

    Reference: with concrete CPTs P(M|X), P(Y|X,M), the answer is
    Σ_m P(Y=True|X=True,M=m) · P(M=m|X=True). Numerical agreement
    pins that the Σ_M binder actually iterates M's domain and the
    body reads m from the bind variable."""
    from themis.runtime.c_factor import identify_via_tian
    from themis.runtime.numeric_estimator import (
        ProbabilityKey, Theta, estimate_formula,
    )

    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    r = identify_via_tian(g, frozenset(), x, y, x_value=True)
    assert r.formula is not None and r.identifiable

    # Bind Y target to True before numerical evaluation.
    formula_y_true = _bind_target_value(r.formula, y, True)

    # Concrete CPTs:
    # P(M=True | X=True) = 0.7, P(M=False | X=True) = 0.3
    # P(Y=True | X=True, M=True) = 0.8
    # P(Y=True | X=True, M=False) = 0.4
    theta = Theta(entries={
        ProbabilityKey(
            target_atom=m, target_value=True,
            given=frozenset([(x, True)]),
        ): 0.7,
        ProbabilityKey(
            target_atom=m, target_value=False,
            given=frozenset([(x, True)]),
        ): 0.3,
        ProbabilityKey(
            target_atom=y, target_value=True,
            given=frozenset([(x, True), (m, True)]),
        ): 0.8,
        ProbabilityKey(
            target_atom=y, target_value=True,
            given=frozenset([(x, True), (m, False)]),
        ): 0.4,
    })

    actual = estimate_formula(formula_y_true, theta)
    # Reference: 0.7*0.8 + 0.3*0.4 = 0.56 + 0.12 = 0.68
    expected = 0.7 * 0.8 + 0.3 * 0.4
    assert abs(actual - expected) < 1e-9, (
        f"Tian formula evaluated to {actual}, expected {expected}. "
        f"Pre-iter-145 it would have given {0.8} (P(Y|X=T,M=T) — "
        f"degenerate sum collapse to M=True term only)."
    )
