"""Unit tests for R6 (probability_ref_lookup), R7 (formula_evaluation),
R8 (numeric_result).

Build theta, graphs, and formulas by hand. No scheduler dependency.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.types import (
    Atom,
    BindDecl,
    ConstantExpr,
    ConstTerm,
    DerivationStep,
    EffectQuery,
    Intervention,
    NumericResult,
    ProbabilityQuery,
    ProbabilityRefExpr,
    ProductExpr,
    StepRef,
    StructuralResult,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_numeric,
)
from themis.verifier.errors import RuleCheckFailed, UnknownRuleInputError


def _atom(pred: str, obj: str = "me") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _prob_query(target_pred: str, given_preds=()) -> ProbabilityQuery:
    t = _atom(target_pred)
    g = tuple(ValuedAtom(atom=_atom(p), value=True) for p in given_preds)
    return ProbabilityQuery(target=ValuedAtom(atom=t, value=True), given=g)


def _effect_query(target_pred: str, intervention_pred: str) -> EffectQuery:
    return EffectQuery(
        target=ValuedAtom(atom=_atom(target_pred), value=True),
        intervention=Intervention(atom=_atom(intervention_pred), value=True),
        given=(),
    )


def _ctx(theta: Theta, query=None):
    graph = nx.DiGraph()
    # minimal graph: EffectQuery / ProbabilityQuery don't need V for
    # verify_numeric's binding checks to pass; we pass nodes that cover
    # the query atoms so structural rules would be happy if used.
    if query is not None:
        if isinstance(query, ProbabilityQuery):
            graph.add_node(query.target.atom)
            for g in query.given:
                graph.add_node(g.atom)
        elif isinstance(query, EffectQuery):
            graph.add_node(query.target.atom)
            graph.add_node(query.intervention.atom)
            for g in query.given:
                graph.add_node(g.atom)
    return VerificationContext(graph=graph, query=query, theta=theta)


# =================================================================== R6

def test_r6_accepts_correct_lookup():
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.7})

    # Use a ProbabilityQuery so verify_numeric's binding check is a no-op
    # for formula_evaluation (we only produce R6 + R8 here).
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={
                "target": ValuedAtom(atom=coin, value=True),
                "given": (),
            },
            output=0.7,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            label="s_final",
        ),
    )
    verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.7))


def test_r6_rejects_lookup_disagreeing_with_theta():
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.7})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={
                "target": ValuedAtom(atom=coin, value=True),
                "given": (),
            },
            output=0.99,  # disagrees with theta's 0.7
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),
            label="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="probability_ref_lookup"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.99))


def test_r6_rejects_missing_key():
    coin = _atom("coin", "a")
    theta = Theta(entries={})  # no entry for this key
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={"target": ValuedAtom(atom=coin, value=True), "given": ()},
            output=0.7,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            label="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="no entry"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.7))


def test_r6_rejects_varref_value():
    """A probability derivation with a non-concrete lookup target must
    be rejected before it can masquerade as the active query."""
    coin = _atom("coin", "a")
    theta = Theta(entries={})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={
                "target": ValuedAtom(atom=coin, value=VarRef("z")),
                "given": (),
            },
            output=0.5,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.5),
            label="s_final",
        ),
    )
    with pytest.raises(VerificationError, match="probability query"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.5))


def test_r6_rejects_lookup_for_different_probability_query():
    """A pure R6 -> R8 derivation must still prove the active
    probability query, not some other conditional in the same Theta."""
    coin = _atom("coin", "a")
    other = _atom("other", "a")
    theta = Theta(entries={
        ProbabilityKey(
            target_atom=coin, target_value=True, given=frozenset()
        ): 0.1,
        ProbabilityKey(
            target_atom=other, target_value=True, given=frozenset()
        ): 0.7,
    })
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={"target": ValuedAtom(atom=other, value=True), "given": ()},
            output=0.7,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            label="s_final",
        ),
    )
    with pytest.raises(VerificationError, match="probability query"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.7))


# =================================================================== R7

def test_r7_accepts_flat_probability_ref():
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.42})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=0.42,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.42),
            label="s_final",
        ),
    )
    verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.42))


def test_r7_accepts_backdoor_sum_formula():
    """Evaluate Σ_z P(Y|X=x, Z=z) P(Z=z) for a two-value Z and compare
    to an independently hand-computed sum."""
    y = _atom("y"); x = _atom("x"); z = _atom("z")
    # P(Y=1|X=1,Z=True)=0.8; P(Y=1|X=1,Z=False)=0.2
    # P(Z=True)=0.3; P(Z=False)=0.7
    # → 0.8*0.3 + 0.2*0.7 = 0.38
    k = lambda target_v, given: ProbabilityKey(
        target_atom=y if target_v is not None and target_v in (True, False) else z,
        target_value=target_v, given=frozenset(given),
    )
    entries = {
        ProbabilityKey(target_atom=y, target_value=True,
                       given=frozenset({(x, True), (z, True)})): 0.8,
        ProbabilityKey(target_atom=y, target_value=True,
                       given=frozenset({(x, True), (z, False)})): 0.2,
        ProbabilityKey(target_atom=z, target_value=True, given=frozenset()): 0.3,
        ProbabilityKey(target_atom=z, target_value=False, given=frozenset()): 0.7,
    }
    theta = Theta(entries=entries, domains={z: (True, False)})

    bind = BindDecl(name="z_z_me")
    target_va = ValuedAtom(atom=y, value=True)
    intervention_va = ValuedAtom(atom=x, value=True)
    z_va = ValuedAtom(atom=z, value=VarRef("z_z_me"))
    cond = ProbabilityRefExpr(target=target_va, given=(intervention_va, z_va))
    prior = ProbabilityRefExpr(target=z_va, given=())
    body = ProductExpr(terms=(cond, prior))
    formula = SumExpr(bind=bind, over=z, body=body)

    query = EffectQuery(
        target=target_va,
        intervention=Intervention(atom=x, value=True),
        given=(),
    )
    ctx = _ctx(theta, query)
    ctx.graph.add_edges_from(((z, x), (z, y), (x, y)))
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": ctx.graph},
            output=True,
            label="s1",
        ),
        DerivationStep(
            rule="backdoor_criterion",
            inputs={
                "graph": ctx.graph,
                "x": x,
                "y": y,
                "z": frozenset({z}),
                "given": frozenset(),
            },
            output=True,
            label="s2",
        ),
        DerivationStep(
            rule="backdoor_adjustment_formula",
            inputs={
                "target": target_va,
                "intervention": intervention_va,
                "z": (z,),
                "given": (),
            },
            output=formula,
            label="s3",
        ),
        DerivationStep(
            rule="identify_via_backdoor",
            inputs={
                "criterion": StepRef("s2"),
                "formula": StepRef("s3"),
            },
            output=StructuralResult(value=True),
            label="s4",
        ),
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=0.38,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.38),
            label="s_final",
        ),
    )
    verify_numeric(deriv, ctx, NumericResult(value=0.38))


def test_r7_rejects_wrong_claimed_value():
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.42})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=0.99,  # wrong
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),
            label="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="formula_evaluation"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.99))


def test_r7_rejects_missing_theta_entry():
    coin = _atom("coin", "a")
    theta = Theta(entries={})  # empty
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    formula = ProbabilityRefExpr(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=0.5,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.5),
            label="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="no entry"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.5))


# =================================================================== R8

def test_r8_rejects_when_evaluation_value_disagrees():
    """R8 must reject when the claimed NumericResult.value disagrees
    with the referenced evaluation step's output."""
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.7})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={"target": ValuedAtom(atom=coin, value=True), "given": ()},
            output=0.7,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),  # doesn't match 0.7
            label="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="numeric_result"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.99))


def test_r8_rejects_reference_to_non_evaluation_step():
    """R8.evaluation must point at an R6 or R7 step. Pointing at, say,
    a constant-carrying step is not acceptable."""
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.7})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    # Smuggle in a fake "graph_is_dag" step whose output is a bool;
    # R8 should refuse to treat it as an evaluation source.
    graph = nx.DiGraph()
    graph.add_node(coin)
    deriv = (
        DerivationStep(
            rule="graph_is_dag",
            inputs={"graph": graph},
            output=True,
            label="s_bogus",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_bogus")},
            output=NumericResult(value=1.0),
            label="s_final",
        ),
    )
    ctx = VerificationContext(graph=graph, query=query, theta=theta)
    # v0.1.4 Fix 1 broadened the allowed evaluation-source list to also
    # accept mediation_numeric_evaluate; loosen the regex to just match
    # the leading rule name rather than the exact "X or Y" phrasing.
    with pytest.raises(RuleCheckFailed, match="formula_evaluation"):
        verify_numeric(deriv, ctx, NumericResult(value=1.0))


def test_verify_numeric_rejects_when_last_step_is_not_numeric_result():
    """Even with all intermediate steps correct, a numeric derivation
    whose last step is not ``numeric_result`` must be rejected."""
    coin = _atom("coin", "a")
    key = ProbabilityKey(
        target_atom=coin, target_value=True, given=frozenset()
    )
    theta = Theta(entries={key: 0.7})
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={"target": ValuedAtom(atom=coin, value=True), "given": ()},
            output=0.7,
            label="s_eval",
        ),
    )
    with pytest.raises(VerificationError, match="numeric_result"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.7))


def test_verify_numeric_requires_theta():
    coin = _atom("coin", "a")
    query = ProbabilityQuery(
        target=ValuedAtom(atom=coin, value=True), given=(),
    )
    graph = nx.DiGraph(); graph.add_node(coin)
    ctx = VerificationContext(graph=graph, query=query, theta=None)
    deriv = (
        DerivationStep(
            rule="probability_ref_lookup",
            inputs={"target": ValuedAtom(atom=coin, value=True), "given": ()},
            output=0.7,
            label="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            label="s_final",
        ),
    )
    with pytest.raises(VerificationError, match="theta"):
        verify_numeric(deriv, ctx, NumericResult(value=0.7))
