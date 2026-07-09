"""ID* (Shpitser-Pearl 2007) — general counterfactual identification.

Validation is two-pronged (D1):

1. An INDEPENDENT counterfactual Monte-Carlo oracle (``tests.ctf_mc_oracle``,
   a vectorized second implementation that never imports the identification
   code, so it cannot share a bug with the formula ID* produced). It computes
   the true P(γ) by drawing the shared exogenous background once per replicate
   and evaluating every hypothetical world's submodel against that same
   background — the response of a node to a given parent configuration is
   shared across worlds, the definition of a counterfactual.

2. The published worked example (cfid, arXiv:2210.14745, eq. after Fig 5):
   P(y_x ∧ x' ∧ z_d ∧ d) = Σ_w P_{w,z}(y,x') P_x(w) P_d(z) P(d). The ID*
   formula must equal the MC truth on several random SCMs, and the FAIL
   cases (the PNS w-graph, and the same graph with an extra X→Y edge) must
   be reported non-identifiable.
"""
from __future__ import annotations

import random

import networkx as nx

from themis.types import Atom, SumExpr, ProductExpr
from themis.runtime.ctf_identify import (
    CtfEvent,
    FAIL,
    ZERO,
    id_star,
)
from themis.verifier.semantic_probe import _sample_scm, _theta_from_scm
from themis.runtime.numeric_estimator import estimate_formula
from tests.ctf_mc_oracle import counterfactual_prob


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, W, Y, Z, D = A("x"), A("w"), A("y"), A("z"), A("d")


# The counterfactual MC oracle lives in tests.ctf_mc_oracle (a vectorized,
# identification-independent second implementation, pinned to exact enumeration
# by tests/test_counterfactual_mc_vectorized.py).
def _assert_matches_mc(graph, bidirected, gamma, *, n_draws=60000, tol=0.02, k=2):
    formula = id_star(graph, bidirected, gamma)
    assert formula is not FAIL and formula is not ZERO, "expected identifiable"
    for i in range(k):
        rng = random.Random(1000 + i)
        scm = _sample_scm(graph, bidirected, {}, rng)
        theta = _theta_from_scm(scm, formula, graph, bidirected)
        got = estimate_formula(formula, theta, graph=graph, bidirected=bidirected)
        true = counterfactual_prob(scm, graph, gamma, n_draws, 50 + i)
        assert abs(got - true) < tol, (
            f"SCM #{i}: formula={got:.4f} vs counterfactual MC={true:.4f}")
    return formula


# ============================================================ graphs
def _fig1_graph():
    g = nx.DiGraph()
    g.add_edges_from([(X, W), (W, Y), (Z, Y), (D, Z)])
    return g, frozenset({frozenset({X, Y})})


def _fig1_gamma():
    # y_x ∧ x' ∧ z_d ∧ d  (binary: x=True/x'=False, all events on value True
    # except x' which is False).
    return (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
        CtfEvent(Z, frozenset({(D, True)}), True),
        CtfEvent(D, frozenset(), True),
    )


# ============================================================ identifiable
def test_simple_effect_counterfactual():
    # P(Y_{X=1}=1) on X→Y with no confounding = P(y|do x) = P(y|x).
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    _assert_matches_mc(g, frozenset(), gamma, n_draws=40000)


def test_fig1_worked_example_matches_mc():
    g, bi = _fig1_graph()
    _assert_matches_mc(g, bi, _fig1_gamma())


def test_fig1_formula_is_sum_over_product_of_four():
    g, bi = _fig1_graph()
    formula = id_star(g, bi, _fig1_gamma())
    # Σ_w ( P_{w,z}(y,x') · P_x(w) · P_d(z) · P(d) )
    assert isinstance(formula, SumExpr)
    assert isinstance(formula.body, ProductExpr)
    assert len(formula.body.terms) == 4


def test_compound_subscript_variable_matches_mc():
    # y_{x,z} ∧ x' — Y carries TWO interventions (x=T, z=T) in one subscript,
    # while X is factually observed x'=F. This is what IDC* produces after it
    # moves z,d into y_x's subscript, and it exposed a Line-6 bug: the {W_{x,z}}
    # c-component's added intervention on X (from the factual x'=F) collided
    # with W's own world value x=T, so P(W) was taken under the wrong X. The
    # formula must reduce to Σ_w P_{z,w}(x',y)·P_x(w) — with W under x=T — and
    # match the counterfactual MC truth. Regression guard for _subconjunction.
    g, bi = _fig1_graph()
    gamma = (
        CtfEvent(Y, frozenset({(X, True), (Z, True)}), True),  # y_{x,z}
        CtfEvent(X, frozenset(), False),                       # x'
    )
    _assert_matches_mc(g, bi, gamma, n_draws=60000, tol=0.02)


# ============================================================ non-identifiable
def test_pns_w_graph_fails():
    # PNS = P(y_x ∧ y'_{x'}) with X a direct parent of Y and X↔Y — the
    # w-graph, the canonical non-identifiable counterfactual (R-336 Lemma 27).
    g = nx.DiGraph()
    g.add_edge(X, Y)
    bi = frozenset({frozenset({X, Y})})
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),    # y_x
        CtfEvent(Y, frozenset({(X, False)}), False),  # y'_{x'}
    )
    assert id_star(g, bi, gamma) is FAIL


def test_fig1_with_direct_xy_edge_fails():
    # cfid's FAIL variant: add X→Y to Fig 1. The {X,Y} component now carries
    # x in a subscript and x' observed at once → line-8 conflict.
    g = nx.DiGraph()
    g.add_edges_from([(X, W), (W, Y), (Z, Y), (D, Z), (X, Y)])
    bi = frozenset({frozenset({X, Y})})
    assert id_star(g, bi, _fig1_gamma()) is FAIL


# ============================================================ zero / tautology
def test_effectiveness_violation_is_zero():
    # x_{x'}: X observed True in a world that fixes X False. P(γ)=0.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (CtfEvent(X, frozenset({(X, False)}), True),)
    assert id_star(g, frozenset(), gamma) is ZERO


def test_tautology_event_dropped():
    # x_{x} (X observed the value it was forced to) drops out; what remains
    # is the plain effect, still identifiable.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (
        CtfEvent(X, frozenset({(X, True)}), True),   # tautology, dropped
        CtfEvent(Y, frozenset({(X, True)}), True),   # P(Y_{X=1}=1)
    )
    formula = id_star(g, frozenset(), gamma)
    assert formula is not FAIL and formula is not ZERO
