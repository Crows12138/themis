"""Phase 16 slice 1 — the sum-to-one canceller (formula_simplify).

Two kinds of test:

1. Structural — the rule fires exactly when ``Σ_v P(v|C)·R`` has ``v``
   confined to the single distribution factor, and does NOT fire when
   another factor conditions on ``v`` (the value would change).
2. Numeric value-preservation — for a NORMALIZED Theta, the simplified
   formula computes the same number as the original. This is the safety
   net that licenses wiring the canceller into construction later: a
   simplification that changes the number is a correctness bug.
"""
from __future__ import annotations

import random

from themis.runtime.formula_simplify import simplify_formula
from themis.runtime.numeric_estimator import (
    ProbabilityKey,
    Theta,
    _evaluate,
)
from themis.types import (
    Atom,
    BindDecl,
    ConstantExpr,
    ConstTerm,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


def _atom(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


V, X, Y, W = _atom("v"), _atom("x"), _atom("y"), _atom("w")
A, B, C, D, E, F = (_atom(p) for p in ("a", "b", "c", "d", "e", "f"))


def _p(target_atom, target_val, given_pairs):
    return ProbabilityRefExpr(
        target=ValuedAtom(atom=target_atom, value=target_val),
        given=tuple(ValuedAtom(atom=a, value=val) for a, val in given_pairs),
    )


def _sum(name, over_atom, body):
    return SumExpr(bind=BindDecl(name=name), over=over_atom, body=body)


# ============================================ structural


def test_sum_of_bare_distribution_is_one():
    # Σ_v P(v | x=True) = 1
    expr = _sum("v", V, _p(V, VarRef("v"), [(X, True)]))
    assert simplify_formula(expr) == ConstantExpr(value=1.0)


def test_sum_to_one_drops_factor_and_sum():
    # Σ_v P(v|x=True) · P(y=True|x=True)  →  P(y=True|x=True)
    keep = _p(Y, True, [(X, True)])
    expr = _sum("v", V, ProductExpr(terms=(_p(V, VarRef("v"), [(X, True)]), keep)))
    assert simplify_formula(expr) == keep


def test_no_collapse_when_other_factor_conditions_on_summed_var():
    # Σ_v P(v|x=True) · P(y=True|v) — y depends on v, must NOT collapse.
    body = ProductExpr(terms=(
        _p(V, VarRef("v"), [(X, True)]),
        _p(Y, True, [(V, VarRef("v"))]),
    ))
    expr = _sum("v", V, body)
    assert simplify_formula(expr) == expr  # unchanged


def test_nested_sums_collapse_independently():
    # Σ_w Σ_v P(v|x=True) · P(w|x=True) · P(y=True|x=True)
    #   inner Σ_v drops P(v|..), outer Σ_w drops P(w|..) → P(y=True|x=True)
    keep = _p(Y, True, [(X, True)])
    inner = ProductExpr(terms=(
        _p(V, VarRef("v"), [(X, True)]),
        _p(W, VarRef("w"), [(X, True)]),
        keep,
    ))
    expr = _sum("w", W, _sum("v", V, inner))
    assert simplify_formula(expr) == keep


def test_idempotent():
    keep = _p(Y, True, [(X, True)])
    expr = _sum("v", V, ProductExpr(terms=(_p(V, VarRef("v"), [(X, True)]), keep)))
    once = simplify_formula(expr)
    assert simplify_formula(once) == once


# ============================================ numeric value-preservation


def _frac(num, den):
    from themis.types import FractionExpr
    return FractionExpr(numerator=num, denominator=den)


# ============================================ slice 2: extract


def test_extract_pulls_independent_factor_out_of_sum():
    # Σ_v [ P(z|w) · P(y|v) · P(v|x) ]  →  P(z|w) · Σ_v[ P(y|v) · P(v|x) ]
    # (inner does NOT collapse: P(y|v) conditions on the summed v.)
    pz = _p(_atom("z"), True, [(W, True)])
    pyv = _p(Y, True, [(V, VarRef("v"))])
    pvx = _p(V, VarRef("v"), [(X, True)])
    expr = _sum("v", V, ProductExpr(terms=(pz, pyv, pvx)))
    out = simplify_formula(expr)
    assert out == ProductExpr(terms=(
        pz, _sum("v", V, ProductExpr(terms=(pyv, pvx))),
    ))


def test_extract_then_collapse_compose():
    # Σ_v [ P(z|w) · P(v|x) ]  →  extract P(z|w) is unnecessary: sum-to-one
    # already collapses since v ∉ free(P(z|w)). Result = P(z|w).
    pz = _p(_atom("z"), True, [(W, True)])
    expr = _sum("v", V, ProductExpr(terms=(pz, _p(V, VarRef("v"), [(X, True)]))))
    assert simplify_formula(expr) == pz


# ============================================ slice 2: fraction cancellation


def test_fraction_cancels_shared_factor_to_numerator():
    # [P(a|b)·P(c|d)] / [P(c|d)]  →  P(a|b)
    pab = _p(A, True, [(B, True)])
    pcd = _p(C, True, [(D, True)])
    expr = _frac(ProductExpr(terms=(pab, pcd)), pcd)
    assert simplify_formula(expr) == pab


def test_fraction_cancels_one_factor_keeps_remainder():
    # [P(a|b)·P(c|d)] / [P(c|d)·P(e|f)]  →  P(a|b) / P(e|f)
    pab = _p(A, True, [(B, True)])
    pcd = _p(C, True, [(D, True)])
    pef = _p(E, True, [(F, True)])
    expr = _frac(ProductExpr(terms=(pab, pcd)), ProductExpr(terms=(pcd, pef)))
    assert simplify_formula(expr) == _frac(pab, pef)


def test_fraction_no_shared_factor_is_unchanged():
    pab = _p(A, True, [(B, True)])
    pcd = _p(C, True, [(D, True)])
    expr = _frac(pab, pcd)
    assert simplify_formula(expr) == expr


def test_fraction_inner_sum_collapses_then_cancels():
    # [P(a|b) · Σ_v P(v|x)] / [P(a|b)]  →  (Σ→1) [P(a|b)·1]/[P(a|b)] → 1
    pab = _p(A, True, [(B, True)])
    expr = _frac(
        ProductExpr(terms=(pab, _sum("v", V, _p(V, VarRef("v"), [(X, True)])))),
        pab,
    )
    assert simplify_formula(expr) == ConstantExpr(value=1.0)


def _normalized_boolean_theta(needed_targets, seed) -> Theta:
    """A Theta where every P(target=True|given) is a random p in (0,1) and
    P(target=False|given)=1-p, so each conditional sums to 1. ``needed``
    is a set of (target_atom, given_frozenset) pairs the formula references
    (target value abstracted away — both polarities are filled)."""
    rng = random.Random(seed)
    entries = {}
    for target_atom, given in needed_targets:
        p_true = rng.uniform(0.1, 0.9)
        entries[ProbabilityKey(target_atom, True, given)] = p_true
        entries[ProbabilityKey(target_atom, False, given)] = 1.0 - p_true
    return Theta(entries=entries)


def test_value_preserved_simple_sum_to_one():
    keep = _p(Y, True, [(X, True)])
    expr = _sum("v", V, ProductExpr(terms=(_p(V, VarRef("v"), [(X, True)]), keep)))
    simplified = simplify_formula(expr)

    gx = frozenset({(X, True)})
    for seed in range(20):
        theta = _normalized_boolean_theta(
            {(V, gx), (Y, gx)}, seed,
        )
        a = _evaluate(expr, theta, {})
        b = _evaluate(simplified, theta, {})
        assert abs(a - b) < 1e-12, f"seed {seed}: {a} != {b}"


def test_value_preserved_nested_double_sum():
    keep = _p(Y, True, [(X, True)])
    inner = ProductExpr(terms=(
        _p(V, VarRef("v"), [(X, True)]),
        _p(W, VarRef("w"), [(X, True)]),
        keep,
    ))
    expr = _sum("w", W, _sum("v", V, inner))
    simplified = simplify_formula(expr)
    assert simplified == keep

    gx = frozenset({(X, True)})
    for seed in range(20):
        theta = _normalized_boolean_theta({(V, gx), (W, gx), (Y, gx)}, seed)
        a = _evaluate(expr, theta, {})
        b = _evaluate(simplified, theta, {})
        assert abs(a - b) < 1e-12, f"seed {seed}: {a} != {b}"


def test_value_preserved_when_no_collapse():
    # The non-collapsing case must ALSO be value-identical (it's unchanged),
    # and crucially the simplifier must not have silently dropped the sum.
    body = ProductExpr(terms=(
        _p(V, VarRef("v"), [(X, True)]),
        _p(Y, True, [(V, VarRef("v"))]),
    ))
    expr = _sum("v", V, body)
    simplified = simplify_formula(expr)
    assert simplified == expr

    gx = frozenset({(X, True)})
    for seed in range(10):
        theta = _normalized_boolean_theta({(V, gx)}, seed)
        # P(y|v) for both v polarities
        rng = random.Random(seed + 100)
        for vval in (True, False):
            gv = frozenset({(V, vval)})
            pt = rng.uniform(0.1, 0.9)
            theta.entries[ProbabilityKey(Y, True, gv)] = pt
            theta.entries[ProbabilityKey(Y, False, gv)] = 1.0 - pt
        a = _evaluate(expr, theta, {})
        b = _evaluate(simplified, theta, {})
        assert abs(a - b) < 1e-12


def test_value_preserved_extract():
    Z = _atom("z")
    pz = _p(Z, True, [(W, True)])
    pyv = _p(Y, True, [(V, VarRef("v"))])
    pvx = _p(V, VarRef("v"), [(X, True)])
    expr = _sum("v", V, ProductExpr(terms=(pz, pyv, pvx)))
    simplified = simplify_formula(expr)
    assert simplified != expr  # extract restructured it

    for seed in range(20):
        theta = _normalized_boolean_theta(
            {
                (Z, frozenset({(W, True)})),
                (Y, frozenset({(V, True)})),
                (Y, frozenset({(V, False)})),
                (V, frozenset({(X, True)})),
            },
            seed,
        )
        a = _evaluate(expr, theta, {})
        b = _evaluate(simplified, theta, {})
        assert abs(a - b) < 1e-12, f"seed {seed}: {a} != {b}"


def test_value_preserved_fraction_cancellation():
    pab = _p(A, True, [(B, True)])
    pcd = _p(C, True, [(D, True)])
    pef = _p(E, True, [(F, True)])
    expr = _frac(ProductExpr(terms=(pab, pcd)), ProductExpr(terms=(pcd, pef)))
    simplified = simplify_formula(expr)
    assert simplified == _frac(pab, pef)

    for seed in range(20):
        theta = _normalized_boolean_theta(
            {
                (A, frozenset({(B, True)})),
                (C, frozenset({(D, True)})),
                (E, frozenset({(F, True)})),
            },
            seed,
        )
        a = _evaluate(expr, theta, {})
        b = _evaluate(simplified, theta, {})
        assert abs(a - b) < 1e-12, f"seed {seed}: {a} != {b}"
