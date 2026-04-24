"""Unit tests for Phase 5 §C counterfactual verifier rule."""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.types import (
    Atom,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    DerivationStep,
    Intervention,
    Monotonicity,
    NumericInterval,
    NumericResult,
    ValuedAtom,
)
from themis.verifier import VerificationContext, VerificationError, verify_counterfactual
from themis.verifier.errors import RuleCheckFailed


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _query(
    *,
    monotonicity: Monotonicity | None = Monotonicity.NON_DECREASING,
    factual_target_known: bool | None = None,
) -> CounterfactualQuery:
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    return CounterfactualQuery(
        observed=ValuedAtom(atom=x, value=False),
        counterfactual_intervention=Intervention(atom=x, value=True),
        counterfactual_target=ValuedAtom(atom=y, value=True),
        assumptions=(
            None
            if monotonicity is None
            else CounterfactualAssumptions(monotonicity=monotonicity)
        ),
        factual_target_known=factual_target_known,
    )


def _theta() -> Theta:
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    return Theta(
        entries={
            ProbabilityKey(target_atom=x, target_value=False, given=frozenset()): 0.6,
            ProbabilityKey(target_atom=x, target_value=True, given=frozenset()): 0.4,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, False)}),
            ): 0.7,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, False)}),
            ): 0.3,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, True)}),
            ): 0.2,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, True)}),
            ): 0.8,
        },
        domains={
            x: (False, True),
            y: (False, True),
        },
    )


def _theta_reverse() -> Theta:
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    return Theta(
        entries={
            ProbabilityKey(target_atom=y, target_value=False, given=frozenset()): 0.5,
            ProbabilityKey(target_atom=y, target_value=True, given=frozenset()): 0.5,
            ProbabilityKey(
                target_atom=x,
                target_value=False,
                given=frozenset({(y, False)}),
            ): 0.84,
            ProbabilityKey(
                target_atom=x,
                target_value=True,
                given=frozenset({(y, False)}),
            ): 0.16,
            ProbabilityKey(
                target_atom=x,
                target_value=False,
                given=frozenset({(y, True)}),
            ): 0.36,
            ProbabilityKey(
                target_atom=x,
                target_value=True,
                given=frozenset({(y, True)}),
            ): 0.64,
        },
        domains={
            x: (False, True),
            y: (False, True),
        },
    )


def _theta_ancestral() -> Theta:
    z = _atom("baseline_aptitude")
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    return Theta(
        entries={
            ProbabilityKey(target_atom=z, target_value=False, given=frozenset()): 0.3,
            ProbabilityKey(target_atom=z, target_value=True, given=frozenset()): 0.7,
            ProbabilityKey(
                target_atom=x,
                target_value=False,
                given=frozenset({(z, False)}),
            ): 0.8,
            ProbabilityKey(
                target_atom=x,
                target_value=True,
                given=frozenset({(z, False)}),
            ): 0.2,
            ProbabilityKey(
                target_atom=x,
                target_value=False,
                given=frozenset({(z, True)}),
            ): 0.4,
            ProbabilityKey(
                target_atom=x,
                target_value=True,
                given=frozenset({(z, True)}),
            ): 0.6,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, False), (z, False)}),
            ): 0.8,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, False), (z, False)}),
            ): 0.2,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, True), (z, False)}),
            ): 0.5,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, True), (z, False)}),
            ): 0.5,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, False), (z, True)}),
            ): 0.4,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, False), (z, True)}),
            ): 0.6,
            ProbabilityKey(
                target_atom=y,
                target_value=False,
                given=frozenset({(x, True), (z, True)}),
            ): 0.1,
            ProbabilityKey(
                target_atom=y,
                target_value=True,
                given=frozenset({(x, True), (z, True)}),
            ): 0.9,
        },
        domains={
            z: (False, True),
            x: (False, True),
            y: (False, True),
        },
    )


def _ctx(
    *,
    monotonicity: Monotonicity | None = Monotonicity.NON_DECREASING,
    factual_target_known: bool | None = None,
) -> VerificationContext:
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    graph = nx.DiGraph()
    graph.add_edge(x, y)
    return VerificationContext(
        graph=graph,
        query=_query(
            monotonicity=monotonicity,
            factual_target_known=factual_target_known,
        ),
        theta=_theta(),
    )


def _ctx_reverse() -> VerificationContext:
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    graph = nx.DiGraph()
    graph.add_edge(x, y)
    return VerificationContext(
        graph=graph,
        query=_query(monotonicity=Monotonicity.NON_DECREASING),
        theta=_theta_reverse(),
    )


def _ctx_ancestral() -> VerificationContext:
    z = _atom("baseline_aptitude")
    x = _atom("chose_cs_major")
    y = _atom("higher_income")
    graph = nx.DiGraph()
    graph.add_edge(z, x)
    graph.add_edge(z, y)
    graph.add_edge(x, y)
    return VerificationContext(
        graph=graph,
        query=_query(monotonicity=Monotonicity.NON_DECREASING),
        theta=_theta_ancestral(),
    )


def test_counterfactual_rule_accepts_bounded_result():
    ctx = _ctx()
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(
                value=None,
                interval=NumericInterval(low=0.3, high=1.0),
            ),
            step_id="s1",
        ),
    )

    verify_counterfactual(
        deriv,
        ctx,
        NumericResult(value=None, interval=NumericInterval(low=0.3, high=1.0)),
    )


def test_counterfactual_rule_accepts_solved_point_result():
    ctx = _ctx(factual_target_known=True)
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(value=1.0),
            step_id="s1",
        ),
    )

    verify_counterfactual(deriv, ctx, NumericResult(value=1.0))


def test_counterfactual_rule_accepts_reverse_factorization_theta():
    ctx = _ctx_reverse()
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(
                value=None,
                interval=NumericInterval(low=0.3, high=1.0),
            ),
            step_id="s1",
        ),
    )

    verify_counterfactual(
        deriv,
        ctx,
        NumericResult(value=None, interval=NumericInterval(low=0.3, high=1.0)),
    )


def test_counterfactual_rule_accepts_ancestral_factorization_theta():
    ctx = _ctx_ancestral()
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(
                value=None,
                interval=NumericInterval(low=0.4153846153846154, high=1.0),
            ),
            step_id="s1",
        ),
    )

    verify_counterfactual(
        deriv,
        ctx,
        NumericResult(
            value=None,
            interval=NumericInterval(low=0.4153846153846154, high=1.0),
        ),
    )


def test_counterfactual_rule_rejects_tampered_interval():
    ctx = _ctx()
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(
                value=None,
                interval=NumericInterval(low=0.4, high=1.0),
            ),
            step_id="s1",
        ),
    )

    with pytest.raises(RuleCheckFailed, match="recomputed narrow monotone bounds"):
        verify_counterfactual(
            deriv,
            ctx,
            NumericResult(value=None, interval=NumericInterval(low=0.4, high=1.0)),
        )


def test_counterfactual_rule_requires_monotonicity_in_context():
    ctx = _ctx(monotonicity=None)
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(
                value=None,
                interval=NumericInterval(low=0.3, high=1.0),
            ),
            step_id="s1",
        ),
    )

    with pytest.raises(RuleCheckFailed, match="explicit monotonicity assumption"):
        verify_counterfactual(
            deriv,
            ctx,
            NumericResult(value=None, interval=NumericInterval(low=0.3, high=1.0)),
        )


def test_verify_counterfactual_requires_counterfactual_query():
    ctx = VerificationContext(graph=nx.DiGraph(), query=None, theta=_theta())  # type: ignore[arg-type]
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=NumericResult(value=1.0),
            step_id="s1",
        ),
    )
    with pytest.raises(VerificationError, match="CounterfactualQuery"):
        verify_counterfactual(deriv, ctx, NumericResult(value=1.0))
