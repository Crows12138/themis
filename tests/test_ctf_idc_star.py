"""IDC* (Shpitser-Pearl 2008, JMLR 9:1941-1979 Fig. 12) — conditional
counterfactual identification ``P(γ | δ)``.

Validation is D1 two-pronged, mirroring ``test_ctf_id_star``:

1. An INDEPENDENT conditional Monte-Carlo oracle (``tests.ctf_mc_oracle``, a
   second implementation, NOT the product's ``semantic_probe``): it draws the
   shared exogenous background once per replicate, evaluates every world's
   submodel against it, and counts P(γ∧δ)/P(δ) with numerator and denominator
   sharing the same background — the definition of a conditional over parallel
   worlds.

2. The published worked example (JMLR §Fig 12 text): the query
   ``P(y_x | x', z_d, d)`` on ``X→W→Y ← Z ← D`` with ``X↔Y`` is identifiable
   as ``P'/P'(x')`` with ``P' = Σ_w P_{z,w}(y,x') P_x(w)``. The IDC* formula
   must equal the MC truth; the w-graph conditional and confounded ETT must
   be reported non-identifiable; conditioning on a zero-probability event
   must return UNDEFINED.
"""
from __future__ import annotations

import random

import networkx as nx

from themis.types import (
    Atom,
    ConstantExpr,
    FractionExpr,
    ProbabilityRefExpr,
    SumExpr,
)
from themis.runtime.ctf_identify import (
    CtfEvent,
    FAIL,
    UNDEFINED,
    ZERO,
    id_star,
    idc_star,
)
from themis.verifier.semantic_probe import _sample_scm, _theta_from_scm
from themis.runtime.numeric_estimator import estimate_formula
from tests.ctf_mc_oracle import conditional_prob


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, W, Y, Z, D = A("x"), A("w"), A("y"), A("z"), A("d")


# The conditional MC oracle lives in tests.ctf_mc_oracle (a vectorized,
# identification-independent second implementation, pinned to exact enumeration
# by tests/test_counterfactual_mc_vectorized.py).
def _assert_matches_mc(graph, bidirected, gamma, delta,
                       *, n_draws=120000, tol=0.03, k=2):
    formula = idc_star(graph, bidirected, gamma, delta)
    assert formula not in (FAIL, ZERO, UNDEFINED), "expected identifiable"
    for i in range(k):
        rng = random.Random(2000 + i)
        scm = _sample_scm(graph, bidirected, {}, rng)
        theta = _theta_from_scm(scm, formula, graph, bidirected)
        got = estimate_formula(formula, theta, graph=graph, bidirected=bidirected)
        true, den = conditional_prob(scm, graph, gamma, delta, n_draws, 60 + i)
        assert den > 1500, f"SCM #{i}: conditioning event too rare ({den})"
        assert abs(got - true) < tol, (
            f"SCM #{i}: formula={got:.4f} vs conditional MC={true:.4f}")
    return formula


# ============================================================ graphs
def _fig1_graph():
    g = nx.DiGraph()
    g.add_edges_from([(X, W), (W, Y), (Z, Y), (D, Z)])
    return g, frozenset({frozenset({X, Y})})


# ============================================================ the worked example
def test_worked_example_matches_mc():
    # P(y_x | x', z_d, d) — the JMLR Fig 12 worked example. IDC* moves z,d
    # into y_x's subscript (no back-door) and returns P(y_{x,z},x')/P(x').
    g, bi = _fig1_graph()
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (
        CtfEvent(X, frozenset(), False),           # x'
        CtfEvent(Z, frozenset({(D, True)}), True),  # z_d
        CtfEvent(D, frozenset(), True),            # d
    )
    formula = _assert_matches_mc(g, bi, gamma, delta)
    assert isinstance(formula, FractionExpr)
    assert isinstance(formula.numerator, SumExpr)  # Σ_w over the summed W


# ============================================================ move / reduction
def test_empty_condition_is_unconditional():
    # δ = ∅ degenerates to ID*.
    g, bi = _fig1_graph()
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    assert idc_star(g, bi, gamma, ()) == id_star(g, bi, gamma)


def test_no_confound_conditioning_drops_out():
    # X→Y, no confounding: Y_x ⊥ X, so P(y_x | x') = P(y_x) = P(y|x). The
    # line-4 move fires (no back-door from x' to y_x) and the evidence drops.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (CtfEvent(X, frozenset(), False),)
    formula = idc_star(g, frozenset(), gamma, delta)
    assert isinstance(formula, ProbabilityRefExpr)
    assert formula.target.value is True
    assert formula.given[0].atom == X and formula.given[0].value is True  # P(y|x=T)


# ============================================================ non-identifiable
def test_w_graph_conditional_fails():
    # P(y_x | y'_{x'}) — the w-graph as a conditional. Non-identifiable.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    bi = frozenset({frozenset({X, Y})})
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (CtfEvent(Y, frozenset({(X, False)}), False),)
    assert idc_star(g, bi, gamma, delta) is FAIL


def test_confounded_ett_fails():
    # P(y_x | x') with X→Y AND X↔Y: the effect of treatment on the treated.
    # y_x and x' share the latent — a back-door blocks the line-4 move, and the
    # {X,Y} cross-world joint is non-identifiable.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    bi = frozenset({frozenset({X, Y})})
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (CtfEvent(X, frozenset(), False),)
    assert idc_star(g, bi, gamma, delta) is FAIL


# ============================================================ undefined / zero
def test_conditioning_on_zero_probability_is_undefined():
    # δ contains x_{x'} (X forced False, observed True) → P(δ)=0 → UNDEFINED.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (CtfEvent(X, frozenset({(X, False)}), True),)
    assert idc_star(g, frozenset(), gamma, delta) is UNDEFINED


def test_inconsistent_joint_is_zero():
    # γ and δ assert contradictory values on the same factual node → the joint
    # γ∧δ is inconsistent (P=0), while δ alone is fine → zero-valued result.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    gamma = (CtfEvent(Y, frozenset(), True),)         # y  (factual Y=T)
    delta = (CtfEvent(Y, frozenset(), False),)        # y' (factual Y=F) — clash
    out = idc_star(g, frozenset(), gamma, delta)
    assert out is ZERO or out == ConstantExpr(value=0.0)
