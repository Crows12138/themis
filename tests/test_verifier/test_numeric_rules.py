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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            step_id="s_final",
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),
            step_id="s_final",
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            step_id="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="no entry"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.7))


def test_r6_rejects_varref_value():
    """A VarRef in target.value means the lookup isn't concrete. The
    rule must refuse instead of silently producing something."""
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.5),
            step_id="s_final",
        ),
    )
    with pytest.raises(RuleCheckFailed, match="non-concrete"):
        verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.5))


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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.42),
            step_id="s_final",
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

    bind = BindDecl(name="z_z")
    target_va = ValuedAtom(atom=y, value=True)
    intervention_va = ValuedAtom(atom=x, value=True)
    z_va = ValuedAtom(atom=z, value=VarRef("z_z"))
    cond = ProbabilityRefExpr(target=target_va, given=(intervention_va, z_va))
    prior = ProbabilityRefExpr(target=z_va, given=())
    body = ProductExpr(terms=(cond, prior))
    formula = SumExpr(bind=bind, over=z, body=body)

    query = EffectQuery(
        target=target_va,
        intervention=Intervention(atom=x, value=True),
        given=(),
    )
    deriv = (
        # No structural prefix here — we're not testing R3/R4 binding,
        # just R7's ability to evaluate the sum correctly against theta.
        DerivationStep(
            rule="formula_evaluation",
            inputs={"formula": formula},
            output=0.38,
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.38),
            step_id="s_final",
        ),
    )
    # Skip effect binding (no R3/R4 present) by using a ProbabilityQuery
    # wrapper shape — but the formula is effect-shaped. To keep the test
    # focused, use effect query and rely on the fact that our binding
    # asserter only fires when R3/R4/R7 are present with known shapes.
    verify_numeric(deriv, _ctx(theta, query), NumericResult(value=0.38))


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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),
            step_id="s_final",
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.5),
            step_id="s_final",
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.99),  # doesn't match 0.7
            step_id="s_final",
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
            step_id="s_bogus",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_bogus")},
            output=NumericResult(value=1.0),
            step_id="s_final",
        ),
    )
    ctx = VerificationContext(graph=graph, query=query, theta=theta)
    with pytest.raises(RuleCheckFailed, match="formula_evaluation or probability_ref_lookup"):
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
            step_id="s_eval",
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
            step_id="s_eval",
        ),
        DerivationStep(
            rule="numeric_result",
            inputs={"evaluation": StepRef("s_eval")},
            output=NumericResult(value=0.7),
            step_id="s_final",
        ),
    )
    with pytest.raises(VerificationError, match="theta"):
        verify_numeric(deriv, ctx, NumericResult(value=0.7))
