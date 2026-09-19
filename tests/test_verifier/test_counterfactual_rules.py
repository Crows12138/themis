"""Unit tests for Phase 5 §C counterfactual verifier rule."""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.ledger import Monotonicity
from themis.types import (
    Atom,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    DerivationStep,
    Intervention,
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



def _step(output, *, risk=None, provenance=None, graph=None):
    inputs: dict = {"graph": graph}
    inputs["interventional_risk_provenance"] = (
        provenance
        if provenance is not None
        else ("not_required" if risk is None else "derived_identification")
    )
    if risk is not None:
        inputs["p_y_do_x_cf"] = risk
    return (
        DerivationStep(
            rule="counterfactual_cell_bounds",
            inputs=inputs,
            output=output,
            label="s1",
        ),
    )


def test_counterfactual_rule_accepts_the_ett_point():
    """P(Y_{x=1}=1 | X=0) = (P(y|do(x=1)) - P(x=1, y=1)) / P(x=0).

    The theta joint is P(0,0)=.42 P(0,1)=.18 P(1,0)=.08 P(1,1)=.32, so with
    P(y|do(x=1)) = 0.8 this is (0.8 - 0.32) / 0.6.
    """
    ctx = _ctx()
    claimed = NumericResult(value=0.8)

    verify_counterfactual(_step(claimed, risk=0.8, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_accepts_a_bounded_cell():
    """The PS cell with no monotonicity: other cell free over [0, 1].

    target = (K - other * P(x=0,y=1)) / P(x=0,y=0) with K = 0.48, so the
    interval is [(0.48 - 0.18) / 0.304 clipped to 1, 0.48 / 0.304 clipped].
    """
    ctx = _ctx(monotonicity=None, factual_target_known=False)
    lo = (0.48 - 1.0 * 0.18) / 0.42
    claimed = NumericResult(value=None, interval=NumericInterval(low=lo, high=1.0))

    verify_counterfactual(_step(claimed, risk=0.8, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_accepts_a_cell_monotonicity_pins():
    """Non-decreasing with X=0 factual and Y=1 factual forces Y_{x=1} = 1,
    so the step legitimately carries no interventional risk at all."""
    ctx = _ctx(factual_target_known=True)
    claimed = NumericResult(value=1.0)

    verify_counterfactual(_step(claimed, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_accepts_reverse_factorization_theta():
    ctx = _ctx_reverse()
    claimed = NumericResult(value=0.8)

    verify_counterfactual(_step(claimed, risk=0.8, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_accepts_ancestral_factorization_theta():
    """Z -> X, Z -> Y, X -> Y. Joint P(x=0)=0.52, P(x=1,y=1)=0.408 and the
    back-door risk P(y|do(x=1)) = 0.3*0.5 + 0.7*0.9 = 0.78."""
    ctx = _ctx_ancestral()
    claimed = NumericResult(value=(0.78 - 0.408) / 0.52)

    verify_counterfactual(_step(claimed, risk=0.78, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_tampered_point():
    ctx = _ctx()
    claimed = NumericResult(value=0.9)

    with pytest.raises(RuleCheckFailed, match="does not match the recomputed cell"):
        verify_counterfactual(_step(claimed, risk=0.8, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_tampered_interventional_risk():
    """Moving the risk moves the answer, so a doctored risk with the honest
    answer attached must not certify either."""
    ctx = _ctx()
    claimed = NumericResult(value=0.8)

    with pytest.raises(RuleCheckFailed, match="does not match the recomputed cell"):
        verify_counterfactual(_step(claimed, risk=0.6, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_no_longer_requires_monotonicity():
    """The old path refused outright without an explicit monotonicity."""
    ctx = _ctx(monotonicity=None)
    claimed = NumericResult(value=0.8)

    verify_counterfactual(_step(claimed, risk=0.8, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_not_required_when_the_cell_needs_a_risk():
    """"not required" would otherwise be a self-certifying claim."""
    ctx = _ctx(monotonicity=None, factual_target_known=False)
    claimed = NumericResult(value=0.5)

    with pytest.raises(RuleCheckFailed, match="neither consistency nor"):
        verify_counterfactual(_step(claimed, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_provenance_that_contradicts_the_inputs():
    ctx = _ctx()
    claimed = NumericResult(value=0.8)

    with pytest.raises(RuleCheckFailed, match="disagrees with the presence"):
        verify_counterfactual(
            _step(claimed, risk=0.8, provenance="not_required", graph=ctx.graph),
            ctx,
            claimed,
        )


def test_counterfactual_rule_rejects_an_unknown_provenance():
    ctx = _ctx()
    claimed = NumericResult(value=0.8)

    with pytest.raises(RuleCheckFailed, match="unknown interventional_risk_provenance"):
        verify_counterfactual(
            _step(claimed, risk=0.8, provenance="trust_me", graph=ctx.graph),
            ctx,
            claimed,
        )


def test_counterfactual_rule_rejects_a_risk_that_is_not_a_probability():
    ctx = _ctx()
    claimed = NumericResult(value=0.8)

    with pytest.raises(RuleCheckFailed, match="not a probability"):
        verify_counterfactual(_step(claimed, risk=1.3, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_a_risk_the_theta_joint_forbids():
    """Consistency confines P(y|do(x=1)) to [P(x=1,y=1), P(x=1,y=1)+P(x=0)]
    = [0.32, 0.92]; 0.1 is below it."""
    ctx = _ctx()
    claimed = NumericResult(value=0.0)

    with pytest.raises(RuleCheckFailed, match="contradicts the theta-recovered"):
        verify_counterfactual(_step(claimed, risk=0.1, graph=ctx.graph), ctx, claimed)


def test_counterfactual_rule_rejects_a_derivation_ending_in_the_old_rule():
    ctx = _ctx()
    claimed = NumericResult(value=0.8)
    deriv = (
        DerivationStep(
            rule="counterfactual_bounds_binary_monotone",
            inputs={"graph": ctx.graph},
            output=claimed,
            label="s1",
        ),
    )

    with pytest.raises(Exception):
        verify_counterfactual(deriv, ctx, claimed)


def test_verify_counterfactual_requires_counterfactual_query():
    ctx = VerificationContext(graph=nx.DiGraph(), query=None, theta=_theta())  # type: ignore[arg-type]
    claimed = NumericResult(value=1.0)
    with pytest.raises(VerificationError, match="CounterfactualQuery"):
        verify_counterfactual(_step(claimed, graph=ctx.graph), ctx, claimed)
