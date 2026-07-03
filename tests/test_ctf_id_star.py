"""ID* (Shpitser-Pearl 2007) — general counterfactual identification.

Validation is two-pronged (D1):

1. An INDEPENDENT counterfactual Monte-Carlo oracle. It samples an SCM
   consistent with the ADMG, then computes the true P(γ) by drawing the
   shared exogenous background ONCE per replicate and evaluating every
   hypothetical world's submodel against that same background (the
   response of a node to a given parent configuration is cached within a
   replicate, so worlds share it — the definition of a counterfactual).
   It never calls the identification code, so it cannot share a bug with
   the formula ID* produced.

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


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, W, Y, Z, D = A("x"), A("w"), A("y"), A("z"), A("d")


# ============================================================ MC oracle
def _draw(dist: dict, rng: random.Random):
    r = rng.random()
    cum = 0.0
    last = None
    for v, p in dist.items():
        last = v
        cum += p
        if r < cum:
            return v
    return last


def _counterfactual_prob(scm, gamma, n_draws: int, rng: random.Random) -> float:
    """True P(γ) by Monte-Carlo over the shared exogenous background."""
    count = 0
    for _ in range(n_draws):
        latents = {n: _draw(scm.latent_dist[n], rng) for n in scm.latents}
        world_cache: dict = {}   # (node, world) -> value
        response: dict = {}      # (node, parent-combo) -> value  (shared across worlds)

        def value_in(node, world):
            ck = (node, world)
            if ck in world_cache:
                return world_cache[ck]
            wd = dict(world)
            if node in wd:                       # intervened in this world
                world_cache[ck] = wd[node]
                return wd[node]
            combo = tuple(
                latents[p] if isinstance(p, str) else value_in(p, world)
                for p in scm.parents[node]
            )
            rk = (node, combo)
            if rk not in response:
                response[rk] = _draw(scm.cpt[node][combo], rng)
            world_cache[ck] = response[rk]
            return response[rk]

        if all(value_in(e.variable, e.subscript) == e.value for e in gamma):
            count += 1
    return count / n_draws


def _assert_matches_mc(graph, bidirected, gamma, *, n_draws=60000, tol=0.02, k=2):
    formula = id_star(graph, bidirected, gamma)
    assert formula is not FAIL and formula is not ZERO, "expected identifiable"
    for i in range(k):
        rng = random.Random(1000 + i)
        scm = _sample_scm(graph, bidirected, {}, rng)
        theta = _theta_from_scm(scm, formula, graph, bidirected)
        got = estimate_formula(formula, theta, graph=graph, bidirected=bidirected)
        mc_rng = random.Random(50 + i)
        true = _counterfactual_prob(scm, gamma, n_draws, mc_rng)
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
