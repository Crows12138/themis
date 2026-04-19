"""Unit tests for the back-door formula builder, with particular
focus on multi-variable joint adjustment via chain-rule factoring."""
from __future__ import annotations

from causal_kernel.input.semantic_validator import validate_formula
from causal_kernel.runtime.formula_builder import backdoor_formula
from causal_kernel.types import (
    Atom,
    ConstTerm,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


def a(name: str) -> Atom:
    return Atom(predicate=name, args=(ConstTerm(name="x"),))


def va(atom: Atom, value=None) -> ValuedAtom:
    return ValuedAtom(atom=atom, value=value)


def test_empty_adjustment_returns_flat_conditional():
    y, x = a("y"), a("x")
    f = backdoor_formula(
        target=va(y),
        intervention=va(x, value=True),
        adjustment_set=(),
    )
    assert isinstance(f, ProbabilityRefExpr)
    assert f.target.atom == y and f.target.value is None
    assert len(f.given) == 1 and f.given[0].atom == x and f.given[0].value is True


def test_single_adjustment_returns_sum_over_z():
    y, x, z = a("y"), a("x"), a("z")
    f = backdoor_formula(
        target=va(y),
        intervention=va(x, value=True),
        adjustment_set=(z,),
    )
    assert isinstance(f, SumExpr)
    assert f.over == z
    assert isinstance(f.body, ProductExpr)
    assert len(f.body.terms) == 2


def test_two_adjustments_produce_nested_sums():
    """|Z|=2 should produce two nested sums with binds in the given order."""
    y, x, z1, z2 = a("y"), a("x"), a("z1"), a("z2")
    f = backdoor_formula(
        target=va(y),
        intervention=va(x, value=True),
        adjustment_set=(z1, z2),
    )
    # Outermost binds z1, inner binds z2.
    assert isinstance(f, SumExpr)
    assert f.over == z1
    outer_bind_name = f.bind.name
    inner = f.body
    assert isinstance(inner, SumExpr)
    assert inner.over == z2
    inner_bind_name = inner.bind.name
    # Distinct bind names.
    assert outer_bind_name != inner_bind_name

    # Innermost product has 1 conditional + 2 chain-rule factors = 3 terms.
    product = inner.body
    assert isinstance(product, ProductExpr)
    assert len(product.terms) == 3


def test_two_adjustments_chain_rule_structure():
    """The chain rule factors follow the declared ordering:
    term[1] = P(Z1=z1 | observed), term[2] = P(Z2=z2 | Z1=z1, observed)."""
    y, x, z1, z2 = a("y"), a("x"), a("z1"), a("z2")
    f = backdoor_formula(
        target=va(y),
        intervention=va(x, value=True),
        adjustment_set=(z1, z2),
    )
    product = f.body.body  # type: ignore[attr-defined]
    conditional, factor_z1, factor_z2 = product.terms

    # factor_z1 = P(Z1=z1 | ):  no prior Z, no observed.
    assert factor_z1.target.atom == z1
    assert isinstance(factor_z1.target.value, VarRef)
    assert factor_z1.given == ()

    # factor_z2 = P(Z2=z2 | Z1=z1):  depends on prior Z1 only.
    assert factor_z2.target.atom == z2
    assert isinstance(factor_z2.target.value, VarRef)
    assert len(factor_z2.given) == 1
    assert factor_z2.given[0].atom == z1
    assert isinstance(factor_z2.given[0].value, VarRef)


def test_multivar_formula_is_wellformed():
    """Every produced multi-var formula must pass validate_formula
    (no free VarRefs, sum.over ground)."""
    y, x = a("y"), a("x")
    zs = tuple(a(f"z{i}") for i in range(3))
    f = backdoor_formula(
        target=va(y),
        intervention=va(x, value=True),
        adjustment_set=zs,
    )
    validate_formula(f)
