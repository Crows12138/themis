"""Unit tests for the back-door formula builder, with particular
focus on multi-variable joint adjustment via chain-rule factoring."""
from __future__ import annotations

import pytest

from themis.input.semantic_validator import validate_formula
from themis.runtime.formula_builder import (
    backdoor_formula,
    mediation_controlled_outcome_formula,
    mediation_potential_outcome_formula,
    transport_formula,
)
from themis.runtime.numeric_estimator import (
    ProbabilityKey,
    Theta,
    estimate_formula,
)
from themis.types import (
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


# ---------------------------------------------------------------------------
# Mediation builders — Phase 6.mediation numeric extension (v0.1.4 Fix 1)
# ---------------------------------------------------------------------------


def test_mediation_potential_outcome_no_w_natural_case_structure():
    """Natural potential outcome E[Y(X=x)] under mediator marginalisation
    with empty W: SumExpr(over=M, body=ProductExpr(P(Y|X,M), P(M|X)))."""
    y, x, m = a("y"), a("x"), a("m")
    f = mediation_potential_outcome_formula(
        target=va(y, value=True),
        intervention_outer=va(x, value=True),
        intervention_inner=va(x, value=True),
        mediators=(m,),
    )
    assert isinstance(f, SumExpr)
    assert f.over == m
    assert isinstance(f.body, ProductExpr)
    assert len(f.body.terms) == 2

    y_cond, m_cond = f.body.terms
    # P(Y=true | X=true, M=VarRef)
    assert y_cond.target.atom == y and y_cond.target.value is True
    assert len(y_cond.given) == 2
    assert y_cond.given[0].atom == x and y_cond.given[0].value is True
    assert y_cond.given[1].atom == m and isinstance(y_cond.given[1].value, VarRef)
    # P(M=VarRef | X=true)
    assert m_cond.target.atom == m and isinstance(m_cond.target.value, VarRef)
    assert len(m_cond.given) == 1
    assert m_cond.given[0].atom == x and m_cond.given[0].value is True


def test_mediation_potential_outcome_cross_world_uses_distinct_x_values():
    """Cross-world E[Y(X=x_outer, M(X=x_inner))]: the M conditional's X
    binding differs from the Y conditional's X binding."""
    y, x, m = a("y"), a("x"), a("m")
    f = mediation_potential_outcome_formula(
        target=va(y, value=True),
        intervention_outer=va(x, value=False),  # E[Y | X=0, ...]
        intervention_inner=va(x, value=True),   # M(X=1)
        mediators=(m,),
    )
    assert isinstance(f, SumExpr)
    y_cond, m_cond = f.body.terms

    # Y conditional uses X = False (outer)
    assert y_cond.given[0].atom == x and y_cond.given[0].value is False
    # M conditional uses X = True (inner) — the cross-world ingredient
    assert m_cond.given[0].atom == x and m_cond.given[0].value is True


def test_mediation_potential_outcome_with_single_w_wraps_in_outer_sum():
    """Single W adjustment: outermost SumExpr binds W, inner SumExpr binds
    M, innermost ProductExpr has 3 terms (P(Y|...), P(M|...), P(W))."""
    y, x, m, w = a("y"), a("x"), a("m"), a("w")
    f = mediation_potential_outcome_formula(
        target=va(y, value=True),
        intervention_outer=va(x, value=True),
        intervention_inner=va(x, value=True),
        mediators=(m,),
        adjustment_set=(w,),
    )
    assert isinstance(f, SumExpr) and f.over == w
    inner = f.body
    assert isinstance(inner, SumExpr) and inner.over == m
    product = inner.body
    assert isinstance(product, ProductExpr)
    assert len(product.terms) == 3   # P(Y|...), P(M|...), P(W)


def test_mediation_potential_outcome_is_wellformed():
    """The natural / cross-world / multi-W variants must all pass
    validate_formula."""
    y, x, m = a("y"), a("x"), a("m")
    ws = tuple(a(f"w{i}") for i in range(3))

    for outer_v, inner_v in [(True, True), (True, False), (False, True)]:
        for n_w in range(0, 4):
            f = mediation_potential_outcome_formula(
                target=va(y, value=True),
                intervention_outer=va(x, value=outer_v),
                intervention_inner=va(x, value=inner_v),
                mediators=(m,),
                adjustment_set=ws[:n_w],
            )
            validate_formula(f)


def test_mediation_controlled_outcome_no_w_returns_flat_conditional():
    """CDE with empty W: P(Y=y | X=x, M=m), no sum needed."""
    y, x, m = a("y"), a("x"), a("m")
    f = mediation_controlled_outcome_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        mediators=(va(m, value=False),),
    )
    assert isinstance(f, ProbabilityRefExpr)
    assert f.target.atom == y and f.target.value is True
    assert len(f.given) == 2
    assert f.given[0].atom == x and f.given[0].value is True
    assert f.given[1].atom == m and f.given[1].value is False


def test_mediation_controlled_outcome_with_single_w():
    """CDE with W=(w,): SumExpr over w wrapping P(Y|X,M,W) · P(W)."""
    y, x, m, w = a("y"), a("x"), a("m"), a("w")
    f = mediation_controlled_outcome_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        mediators=(va(m, value=False),),
        adjustment_set=(w,),
    )
    assert isinstance(f, SumExpr) and f.over == w
    product = f.body
    assert isinstance(product, ProductExpr)
    assert len(product.terms) == 2

    y_cond, w_factor = product.terms
    assert y_cond.target.atom == y
    assert len(y_cond.given) == 3   # X, M, W
    assert w_factor.target.atom == w
    assert w_factor.given == ()


def test_mediation_controlled_outcome_is_wellformed():
    """Empty / single / multi-W CDE forms all well-formed."""
    y, x, m = a("y"), a("x"), a("m")
    ws = tuple(a(f"w{i}") for i in range(3))
    for n_w in range(0, 4):
        f = mediation_controlled_outcome_formula(
            target=va(y, value=True),
            intervention=va(x, value=True),
            mediators=(va(m, value=False),),
            adjustment_set=ws[:n_w],
        )
        validate_formula(f)


# ---------------------------------------------------------------------------
# Transport builder — Fix 3+4 (charter FIX_3_4_CHARTER)
# ---------------------------------------------------------------------------


def test_transport_empty_adjustment_returns_flat_source_conditional():
    """Trivial transportability case: P*(Y|do(X)) = P(Y|X, source)."""
    y, x = a("y"), a("x")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(),
        source_population="rct_2022",
        target_population="clinic",
    )
    assert isinstance(f, ProbabilityRefExpr)
    assert f.target.atom == y and f.target.value is True
    assert len(f.given) == 1 and f.given[0].atom == x
    assert f.population == "rct_2022"


def test_transport_names_no_domain_the_problem_has_not_declared():
    """The trivial case is the case with no source domain to name — no
    selection node declares one, and the identifier says so. A default
    stood in for that missing name, so a reader was shown a factor read
    from ``source``: a domain no statement names and no theta entry is
    tagged with, which is also why its number could not be found."""
    y, x = a("y"), a("x")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(),
        source_population=None,
        target_population="clinic",
    )
    assert f.population is None

    # And there is nowhere left for a name to be invented: both are the
    # caller's to say.
    with pytest.raises(TypeError):
        transport_formula(
            target=va(y, value=True),
            intervention=va(x, value=True),
            adjustment_set=(),
        )


def test_transport_single_adjustment_tags_source_and_target():
    """Single Z: SumExpr wrapping ProductExpr(source_factor, target_factor)."""
    y, x, z = a("y"), a("x"), a("z")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(z,),
        source_population="source",
        target_population="target",
    )
    assert isinstance(f, SumExpr) and f.over == z
    product = f.body
    assert isinstance(product, ProductExpr)
    assert len(product.terms) == 2

    src, tgt = product.terms
    # Source factor: P(Y | X, Z, source)
    assert src.population == "source"
    assert src.target.atom == y
    assert len(src.given) == 2  # X + Z
    # Target factor: P*(Z, target)
    assert tgt.population == "target"
    assert tgt.target.atom == z
    assert tgt.given == ()


def test_transport_two_adjustments_chain_rule_target_side():
    """|Z|=2: target side decomposes via chain rule P*(Z1) · P*(Z2|Z1).
    Source side stays a single joint P(Y | X, Z1, Z2, source)."""
    y, x, z1, z2 = a("y"), a("x"), a("z1"), a("z2")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(z1, z2),
        source_population="source",
        target_population="target",
    )
    # Outer over Z1, inner over Z2
    assert isinstance(f, SumExpr) and f.over == z1
    inner = f.body
    assert isinstance(inner, SumExpr) and inner.over == z2

    product = inner.body
    assert isinstance(product, ProductExpr)
    # 1 source factor + 2 target chain-rule factors
    assert len(product.terms) == 3

    src, t1, t2 = product.terms
    assert src.population == "source"
    assert len(src.given) == 3  # X, Z1, Z2
    assert t1.population == "target" and t1.target.atom == z1 and t1.given == ()
    # P*(Z2 | Z1, target) — chain-rule conditioning
    assert t2.population == "target" and t2.target.atom == z2
    assert len(t2.given) == 1 and t2.given[0].atom == z1


def test_transport_custom_population_labels():
    """The populations are whatever the program calls them, which is why
    the builder has no labels of its own to fall back to."""
    y, x, z = a("y"), a("x"), a("z")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(z,),
        source_population="boston_rct",
        target_population="rural_india",
    )
    src, tgt = f.body.terms
    assert src.population == "boston_rct"
    assert tgt.population == "rural_india"


def test_transport_formula_is_wellformed():
    """All transport formula variants must pass validate_formula."""
    y, x = a("y"), a("x")
    zs = tuple(a(f"z{i}") for i in range(3))
    for n_z in range(0, 4):
        f = transport_formula(
            target=va(y, value=True),
            intervention=va(x, value=True),
            adjustment_set=zs[:n_z],
            source_population="source",
            target_population="target",
        )
        validate_formula(f)


def test_transport_evaluates_correctly_single_adjustment():
    """End-to-end: build transport formula + populate two-population
    theta + estimate_formula returns correct sum.

    Source: P(Y=1 | X=1, Z=0) = 0.6, P(Y=1 | X=1, Z=1) = 0.4
    Target: P*(Z=0) = 0.3, P*(Z=1) = 0.7
    Expected: 0.6 · 0.3 + 0.4 · 0.7 = 0.18 + 0.28 = 0.46
    """
    y, x, z = a("y"), a("x"), a("z")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(z,),
        source_population="source",
        target_population="target",
    )

    def key_pop(target_atom, target_value, given_pairs, pop):
        return ProbabilityKey(
            target_atom=target_atom,
            target_value=target_value,
            given=frozenset(given_pairs),
            population=pop,
        )

    theta = Theta(
        entries={
            # Source: P(Y | X, Z)
            key_pop(y, True, [(x, True), (z, False)], "source"): 0.6,
            key_pop(y, True, [(x, True), (z, True)],  "source"): 0.4,
            # Target: P*(Z)
            key_pop(z, False, [], "target"): 0.3,
            key_pop(z, True,  [], "target"): 0.7,
        },
        domains={
            y: (True, False),
            x: (True, False),
            z: (True, False),
        },
    )

    result = estimate_formula(f, theta)
    expected = 0.6 * 0.3 + 0.4 * 0.7
    assert abs(result - expected) < 1e-9, (
        f"transport eval expected {expected}, got {result}"
    )


def test_transport_evaluation_isolates_populations():
    """A theta with same (Z=False) marginal in source AND target with
    different values must NOT cross-contaminate: source's Z marginal
    (if present) is irrelevant to transport, only target's P*(Z) is
    consumed for the outer factor; vice versa for the source-side
    conditional."""
    y, x, z = a("y"), a("x"), a("z")
    f = transport_formula(
        target=va(y, value=True),
        intervention=va(x, value=True),
        adjustment_set=(z,),
        source_population="source",
        target_population="target",
    )

    def key_pop(target_atom, target_value, given_pairs, pop):
        return ProbabilityKey(
            target_atom=target_atom,
            target_value=target_value,
            given=frozenset(given_pairs),
            population=pop,
        )

    theta = Theta(
        entries={
            # Source: P(Y | X, Z) — what we need
            key_pop(y, True, [(x, True), (z, False)], "source"): 0.6,
            key_pop(y, True, [(x, True), (z, True)],  "source"): 0.4,
            # Source: also has P(Z) marginal — but transport must NOT use
            # this for the outer; should use target's instead.
            key_pop(z, False, [], "source"): 0.9,
            key_pop(z, True,  [], "source"): 0.1,
            # Target: P*(Z) — what we need for outer
            key_pop(z, False, [], "target"): 0.3,
            key_pop(z, True,  [], "target"): 0.7,
        },
        domains={y: (True, False), x: (True, False), z: (True, False)},
    )

    result = estimate_formula(f, theta)
    # Must equal target-marginal-based sum (0.46), NOT source-marginal-based (0.58).
    expected_target_based = 0.6 * 0.3 + 0.4 * 0.7  # = 0.46
    expected_source_based = 0.6 * 0.9 + 0.4 * 0.1  # = 0.58  (wrong if leaked)
    assert abs(result - expected_target_based) < 1e-9
    assert abs(result - expected_source_based) > 0.1


def test_q1358_nie_evaluates_to_0_11():
    """Q1358 (CLadder mediation): X=medication, M=blood_pressure, Y=heart.
    NIE@X=0 = E[Y(X=0, M(X=1))] − E[Y(X=0, M(X=0))]
    Expected: 0.11 (matches CLadder ground truth).
    Validates the full builder → numeric_estimator integration.
    """
    y, x, m = a("y"), a("x"), a("m")

    # Build the cross-world potential E[Y(X=0, M(X=1))]
    f_cross = mediation_potential_outcome_formula(
        target=va(y, value=True),
        intervention_outer=va(x, value=False),
        intervention_inner=va(x, value=True),
        mediators=(m,),
    )
    # Build the natural potential E[Y(X=0)] = E[Y(X=0, M(X=0))]
    f_natural = mediation_potential_outcome_formula(
        target=va(y, value=True),
        intervention_outer=va(x, value=False),
        intervention_inner=va(x, value=False),
        mediators=(m,),
    )

    # CLadder Q1358 parameters
    def key(target_atom, target_value, given_pairs):
        return ProbabilityKey(
            target_atom=target_atom,
            target_value=target_value,
            given=frozenset(given_pairs),
        )

    theta = Theta(
        entries={
            key(y, True, [(x, False), (m, False)]): 0.71,
            key(y, True, [(x, False), (m, True)]):  0.46,
            key(y, True, [(x, True),  (m, False)]): 0.81,
            key(y, True, [(x, True),  (m, True)]):  0.33,
            key(m, True, [(x, False)]): 0.75,
            key(m, False, [(x, False)]): 0.25,
            key(m, True, [(x, True)]):  0.31,
            key(m, False, [(x, True)]):  0.69,
        },
        domains={
            y: (True, False),
            x: (True, False),
            m: (True, False),
        },
    )

    e_y0_m_at_x1 = estimate_formula(f_cross, theta)
    e_y0          = estimate_formula(f_natural, theta)
    nie_at_0 = e_y0_m_at_x1 - e_y0

    assert abs(nie_at_0 - 0.11) < 0.005, (
        f"NIE@X=0 should be 0.11 (CLadder ground truth), "
        f"got {nie_at_0:.4f} (E[Y(0, M(1))]={e_y0_m_at_x1:.4f}, "
        f"E[Y(0)]={e_y0:.4f})"
    )
