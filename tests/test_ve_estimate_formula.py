"""Variable-elimination formula evaluation (runtime.numeric_estimator).

``ve_estimate_formula`` is the crash-free replacement for the recursive
``estimate_formula`` on the large nested-ID / general-ID estimands: the
recursive walk binds a fresh subs dict per value of every enclosing Σ
(2^#sums leaf evals + 2^#sums churn), which past |V|≈14 is both exponential
and a flaky native-fault site. VE computes the IDENTICAL value in ~2^treewidth
on a complete theta. ``referenced_keys`` is the linear-per-factor twin of
``enumerate_keys`` (which materialises the 2^#sums key list). These pin both.
"""
from __future__ import annotations

import random

import networkx as nx
import pytest

from themis.runtime import c_factor
from themis.runtime.numeric_estimator import (
    Theta,
    ProbabilityKey,
    enumerate_keys,
    estimate_formula,
    referenced_keys,
    ve_estimate_formula,
)
from themis.types import (
    Atom, BindDecl, ConstTerm, FractionExpr, ProbabilityRefExpr,
    ProductExpr, SumExpr, ValuedAtom, VarRef,
)


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _napkin_chain(n_mediators: int):
    """Pearl's napkin (W→Z→X→Y, W↔X, W↔Y) extended with an X→…→Y mediator
    chain — the family that forces the full nested-ID Line-7 path. |V| =
    4 + n_mediators; for n≥1 the estimand is a deeply nested pure sum-product,
    for n=0 it is the classic napkin ratio (a fraction)."""
    w, z, x, y = _A("w"), _A("z"), _A("x"), _A("y")
    meds = [_A(f"m{i}") for i in range(n_mediators)]
    chain = [w, z, x] + meds + [y]
    g = nx.DiGraph(list(zip(chain, chain[1:])))
    bi = frozenset({frozenset({w, x}), frozenset({w, y})})
    return g, bi, x, y


def _raw_nested_formula(g, bi, x, y):
    """The full Line-7 estimand, cap + numeric self-check bypassed so the
    test can reach the larger sizes directly."""
    saved_cap = c_factor._FULL_LINE7_MAX_NODES
    saved_chk = c_factor._full_line7_numerically_sound
    c_factor._FULL_LINE7_MAX_NODES = 100
    c_factor._full_line7_numerically_sound = lambda *a, **k: True
    try:
        return c_factor.identify_via_tian(g, bi, x, y, x_value=True).formula
    finally:
        c_factor._FULL_LINE7_MAX_NODES = saved_cap
        c_factor._full_line7_numerically_sound = saved_chk


def _bind_y(formula, y, yv):
    """Substitute the query-bound outcome value into the estimand (the value=
    None outcome slots), mirroring what the probe / plug-in do before eval."""
    def fix(va):
        if va.value is None and va.atom == y:
            return ValuedAtom(atom=va.atom, value=yv)
        return va
    if isinstance(formula, ProbabilityRefExpr):
        return ProbabilityRefExpr(target=fix(formula.target),
                                  given=tuple(fix(g) for g in formula.given))
    if isinstance(formula, ProductExpr):
        return ProductExpr(terms=tuple(_bind_y(t, y, yv) for t in formula.terms))
    if isinstance(formula, SumExpr):
        return SumExpr(bind=formula.bind, over=formula.over,
                       body=_bind_y(formula.body, y, yv))
    if isinstance(formula, FractionExpr):
        return FractionExpr(numerator=_bind_y(formula.numerator, y, yv),
                            denominator=_bind_y(formula.denominator, y, yv))
    return formula


def _random_complete_theta(formula, seed):
    """Fill a Theta with a random value for every key the formula references.
    ve == recursive holds for ANY complete theta (both do the same arithmetic),
    so a random fill exercises the equivalence without needing an SCM."""
    theta = Theta()
    rng = random.Random(seed)
    for key in referenced_keys(formula, {}):
        theta.entries[key] = rng.random()
    return theta


@pytest.mark.parametrize("n_med", [0, 1, 2, 3, 4, 6])
def test_ve_equals_recursive_on_complete_theta(n_med):
    """The whole point: on a complete theta ``ve_estimate_formula`` returns the
    SAME number as the recursive ``estimate_formula`` — for the deeply-nested
    pure sum-product (n≥1) AND the napkin ratio / fraction (n=0)."""
    g, bi, x, y = _napkin_chain(n_med)
    formula = _raw_nested_formula(g, bi, x, y)
    assert formula is not None
    for yv in (True, False):
        bound = _bind_y(formula, y, yv)
        for seed in range(3):
            theta = _random_complete_theta(bound, seed)
            rec = estimate_formula(bound, theta)
            ve = ve_estimate_formula(bound, theta)
            assert abs(rec - ve) < 1e-12, (n_med, yv, seed, rec, ve)


@pytest.mark.parametrize("n_med", [0, 2, 4, 6])
def test_referenced_keys_matches_enumerate_keys_distinct(n_med):
    """``referenced_keys`` (linear per-factor) yields EXACTLY the distinct key
    set ``enumerate_keys`` (2^#sums expansion) produces — a pure speedup, not a
    different key set. Pinning this lets the theta builders swap one for the
    other."""
    g, bi, x, y = _napkin_chain(n_med)
    formula = _bind_y(_raw_nested_formula(g, bi, x, y), y, True)
    assert set(referenced_keys(formula, {})) == set(enumerate_keys(formula, Theta()))


def test_ve_degenerate_sum_multiplies_by_domain_size():
    """A Σ over a variable that appears in NO factor of its body is a
    degenerate sum = ×|domain|. VE must reproduce that (not drop it), matching
    the recursive evaluator's ``total += body`` over each value."""
    x, y = _A("x"), _A("y")
    # Σ_t P(y) — body ignores the bound t; over a binary domain this is 2·P(y).
    inner = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=True), given=())
    formula = SumExpr(bind=BindDecl(name="t"), over=x, body=inner)
    theta = Theta()
    theta.entries[ProbabilityKey(target_atom=y, target_value=True,
                                 given=frozenset())] = 0.3
    assert abs(ve_estimate_formula(formula, theta) - 0.6) < 1e-12
    assert abs(estimate_formula(formula, theta)
               - ve_estimate_formula(formula, theta)) < 1e-12


def test_ve_fraction_positivity_violation_raises():
    """A zero denominator is a positivity violation in VE just as in
    ``estimate_formula`` — the fraction rule must not silently return inf/0."""
    y = _A("y")
    num = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=True), given=())
    den = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=False), given=())
    formula = FractionExpr(numerator=num, denominator=den)
    theta = Theta()
    theta.entries[ProbabilityKey(target_atom=y, target_value=True,
                                 given=frozenset())] = 0.5
    theta.entries[ProbabilityKey(target_atom=y, target_value=False,
                                 given=frozenset())] = 0.0
    with pytest.raises(ValueError):
        ve_estimate_formula(formula, theta)
