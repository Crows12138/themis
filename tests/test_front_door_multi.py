"""Phase 6.front-door-multi: multi-mediator front-door end-to-end.

Covers the case where Pearl's front-door adjustment needs TWO or more
mediators — a single mediator cannot block every X→Y directed path.
The classic setup:

    X → M1 → Y
    X → M2 → Y
    X ↔ Y  (latent confounder blocks backdoor)

Neither {M1} nor {M2} alone satisfies FD1 (both directed paths must
be blocked), but {M1, M2} does.

Tests:
- ``formula_builder.front_door_formula`` accepts multi-mediator input
  and produces the chain-rule-factored nested sum
- The verifier rule ``front_door_adjustment_formula`` accepts
  multi-mediator formulas
- End-to-end: themis.run on a parallel-paths ADMG identifies via
  {M1, M2} front-door and themis.verify round-trips
"""
from __future__ import annotations

import pytest

import themis
from themis.runtime import formula_builder
from themis.types import (
    Atom,
    ConstTerm,
    ProductExpr,
    ProbabilityRefExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


# ============================================ formula shape


def test_two_mediators_produce_nested_double_sum():
    z1, z2 = _atom("z1"), _atom("z2")
    target = ValuedAtom(atom=_atom("y"), value=True)
    intervention = ValuedAtom(atom=_atom("x"), value=True)

    formula = formula_builder.front_door_formula(
        target=target, intervention=intervention, mediators=(z1, z2),
    )

    # Outer Sum over z1
    assert isinstance(formula, SumExpr)
    assert formula.over == z1

    # Next Sum over z2
    inner = formula.body
    assert isinstance(inner, SumExpr)
    assert inner.over == z2

    # Inside: Product of chain factors P(Z1|X), P(Z2|Z1,X), plus x' sum
    product = inner.body
    assert isinstance(product, ProductExpr)
    # Three terms: P(Z1|X), P(Z2|Z1,X), and the inner x' sum
    assert len(product.terms) == 3

    p_z1_given_x = product.terms[0]
    p_z2_given_z1_x = product.terms[1]
    assert isinstance(p_z1_given_x, ProbabilityRefExpr)
    assert isinstance(p_z2_given_z1_x, ProbabilityRefExpr)

    # P(Z1 | X): one condition, the intervention
    assert len(p_z1_given_x.given) == 1
    # P(Z2 | Z1, X): two conditions — the intervention and Z1
    assert len(p_z2_given_z1_x.given) == 2

    # Last term: x' sum
    x_prime_sum = product.terms[2]
    assert isinstance(x_prime_sum, SumExpr)
    assert x_prime_sum.over.predicate == "x"


def test_three_mediators_chain_rule_factors_three_conditionals():
    z1, z2, z3 = _atom("z1"), _atom("z2"), _atom("z3")
    target = ValuedAtom(atom=_atom("y"), value=True)
    intervention = ValuedAtom(atom=_atom("x"), value=True)

    formula = formula_builder.front_door_formula(
        target=target, intervention=intervention, mediators=(z1, z2, z3),
    )

    # Three nested outer sums
    outer = formula
    for expected_over in (z1, z2, z3):
        assert isinstance(outer, SumExpr)
        assert outer.over == expected_over
        outer = outer.body

    product = outer
    assert isinstance(product, ProductExpr)
    # Three chain factors + the inner x' sum
    assert len(product.terms) == 4
    # P(Z1|X) has 1 condition, P(Z2|Z1,X) has 2, P(Z3|Z1,Z2,X) has 3
    for i in range(3):
        factor = product.terms[i]
        assert isinstance(factor, ProbabilityRefExpr)
        assert len(factor.given) == i + 1


# ============================================ end-to-end themis.run + verify


def _parallel_paths_ast():
    """X → M1 → Y, X → M2 → Y, X ↔ Y (latent). Front-door needs {M1, M2}."""
    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m1", "domain": [True, False]},
            {"kind": "variable", "predicate": "m2", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("m1")},
            {"kind": "cause", "from": atom("m1"), "to": atom("y")},
            {"kind": "cause", "from": atom("x"), "to": atom("m2")},
            {"kind": "cause", "from": atom("m2"), "to": atom("y")},
            {"kind": "bidirected",
             "left": atom("x"), "right": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "identify",
                "intervention": {"atom": atom("x"), "value": True},
                "target": atom("y"),
                "given": [],
            }},
        ],
    }


def test_scheduler_picks_multi_mediator_front_door():
    ast = _parallel_paths_ast()
    out = themis.run(ast)
    result = out["results"][0]

    # Should identify via front-door with two mediators
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is True

    rules = [step["rule"] for step in result["derivation"]["steps"]]
    assert "front_door_criterion" in rules
    assert "front_door_adjustment_formula" in rules
    assert "identify_via_front_door" in rules


def test_themis_verify_accepts_multi_mediator_result():
    """Round-trip: run → verify must succeed on the multi-mediator case."""
    ast = _parallel_paths_ast()
    out = themis.run(ast)
    result = out["results"][0]
    themis.verify(ast, result)  # must not raise
