"""Unit tests for the recursive formula evaluator.

These tests construct Theta manually to exercise every AST node in
isolation, independent of any scheduler or fixture.
"""
from __future__ import annotations

import pytest

from themis.runtime.numeric_estimator import (
    InsufficientTheta,
    ProbabilityKey,
    Theta,
    estimate_formula,
    estimate_probability,
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


def atom(pred: str, obj: str = "a") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


# ----------------------------------------------------------------- constant

def test_constant_is_returned_as_float():
    assert estimate_formula(ConstantExpr(value=0.7), Theta()) == 0.7


# ------------------------------------------------------- probability lookup

def test_probability_ref_literal_values_hit_theta():
    y = atom("y")
    x = atom("x")
    key = ProbabilityKey(
        target_atom=y,
        target_value=True,
        given=frozenset({(x, True)}),
    )
    theta = Theta(entries={key: 0.3})
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
    )
    assert estimate_formula(expr, theta) == 0.3


def test_missing_theta_entry_raises_with_key():
    y = atom("y")
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True), given=()
    )
    with pytest.raises(InsufficientTheta) as exc:
        estimate_formula(expr, Theta())
    assert exc.value.missing_key is not None
    assert exc.value.missing_key.target_atom == y
    assert exc.value.missing_key.target_value is True


def test_query_bound_target_raises_insufficient():
    y = atom("y")
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=None), given=()
    )
    with pytest.raises(InsufficientTheta):
        estimate_formula(expr, Theta())


# ----------------------------------------------------------------- product

def test_product_multiplies_terms():
    expr = ProductExpr(terms=(
        ConstantExpr(value=0.5),
        ConstantExpr(value=0.4),
        ConstantExpr(value=2.0),
    ))
    assert estimate_formula(expr, Theta()) == pytest.approx(0.4)


# --------------------------------------------------------------------- sum

def test_sum_over_boolean_domain_marginalizes():
    """∑_z P(y=True | z) over z∈{True, False}."""
    y = atom("y")
    z = atom("z")
    theta = Theta(entries={
        ProbabilityKey(
            target_atom=y, target_value=True,
            given=frozenset({(z, True)}),
        ): 0.8,
        ProbabilityKey(
            target_atom=y, target_value=True,
            given=frozenset({(z, False)}),
        ): 0.2,
    })
    bind = BindDecl(name="z_val")
    expr = SumExpr(
        bind=bind,
        over=z,
        body=ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=z, value=VarRef(name="z_val")),),
        ),
    )
    # 0.8 + 0.2 = 1.0 (unconditional marginalization of a well-formed CPD
    # is not generally 1.0 but works here because we hand-picked entries.)
    assert estimate_formula(expr, theta) == pytest.approx(1.0)


# ----------------------------------------------------- back-door integration

def test_single_var_backdoor_formula_evaluates_end_to_end():
    """Build a tiny Theta that satisfies the back-door formula
    ∑_z P(Y=True | X=False, Z=z) * P(Z=z) and evaluate."""
    y = atom("y")
    x = atom("x")
    z = atom("z")
    theta = Theta(entries={
        # P(Y=True | X=False, Z=True)
        ProbabilityKey(y, True, frozenset({(x, False), (z, True)})): 0.9,
        ProbabilityKey(y, True, frozenset({(x, False), (z, False)})): 0.3,
        # P(Z=True), P(Z=False)
        ProbabilityKey(z, True, frozenset()): 0.4,
        ProbabilityKey(z, False, frozenset()): 0.6,
    })
    bind = BindDecl(name="z_val")
    expr = SumExpr(
        bind=bind,
        over=z,
        body=ProductExpr(terms=(
            ProbabilityRefExpr(
                target=ValuedAtom(atom=y, value=True),
                given=(
                    ValuedAtom(atom=x, value=False),
                    ValuedAtom(atom=z, value=VarRef(name="z_val")),
                ),
            ),
            ProbabilityRefExpr(
                target=ValuedAtom(atom=z, value=VarRef(name="z_val")),
                given=(),
            ),
        )),
    )
    # 0.9 * 0.4 + 0.3 * 0.6 = 0.36 + 0.18 = 0.54
    assert estimate_formula(expr, theta) == pytest.approx(0.54)
