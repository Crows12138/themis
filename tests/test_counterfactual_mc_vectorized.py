"""Vectorized counterfactual Monte-Carlo == scalar == EXACT enumeration.

The production semantic probe evaluates the true ``P(γ)`` / ``P(γ|δ)`` of a
counterfactual conjunction two ways: an exact sum over the whole exogenous
space where that space fits under a cap, and Monte-Carlo above it. The
sampled path was rewritten from a per-draw Python loop (a flaky Windows
heap-corruption site at 50k+ draws) into a numpy-vectorized forward pass.
This pins both:

1. the vectorized MC equals an INDEPENDENT EXACT enumeration of the whole
   exogenous space (every latent × every per-(node,combo) response function)
   on small SCMs — the ground truth, no Monte-Carlo error at all;
2. the vectorized MC equals the readable scalar reference within MC error;
   and
3. the production EXACT path equals that same independent enumeration to
   floating point.

The enumerator here shares no code with either production path, so an
agreement is real evidence they preserve the twin-network semantics (shared
exogenous background across worlds; a node's per-parent-combo response
shared across worlds, independent across combos).

The third claim is what makes the exact path auditable at all. It computes
the same sum by a different route — the production one enumerates the
background into the arrays the forward walk already wanted and weights the
columns, this one recurses over assignments in the readable order — so
agreement is two implementations, not one implementation twice.
"""
from __future__ import annotations

import itertools
import random

import networkx as nx
import numpy as np

from themis.types import Atom
from themis.runtime.ctf_identify import CtfEvent
from themis.verifier.semantic_probe import (
    _DEFAULT_DOMAIN,
    _EXACT_BACKGROUND_CAP,
    _background_size,
    _conditional_true_exact,
    _counterfactual_true_exact,
    _sample_scm,
    _counterfactual_true_mc,
    _conditional_true_mc,
)
from tests.ctf_mc_oracle import (
    counterfactual_prob as _oracle_cf,
    conditional_prob as _oracle_cond,
)


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, Y, Z = A("x"), A("y"), A("z")


# =================================================== exact ground truth
def _response_cells(scm):
    """Every (node, parent-combo) whose response is an independent latent."""
    cells = []
    for node in scm.observed:
        for combo in scm.cpt[node]:
            cells.append((node, combo))
    return cells


def _eval_world(scm, latents, resp, gamma_events):
    """Deterministic value of each event's variable in its world, given a full
    exogenous assignment (latents + response function ``resp``)."""
    cache: dict = {}

    def value_in(node, world):
        ck = (node, world)
        if ck in cache:
            return cache[ck]
        wd = dict(world)
        if node in wd:                       # intervened in this world
            cache[ck] = wd[node]
            return wd[node]
        combo = tuple(
            latents[p] if isinstance(p, str) else value_in(p, world)
            for p in scm.parents[node]
        )
        cache[ck] = resp[(node, combo)]
        return cache[ck]

    return [value_in(e.variable, e.subscript) for e in gamma_events]


def _exact_probs(scm, gamma, delta=()):
    """Exact ``P(γ ∧ δ)`` and ``P(δ)`` by summing over the ENTIRE exogenous
    space: every latent assignment × every response-function assignment,
    weighted by ``∏ latent_dist × ∏ cpt``. Independent of the MC path."""
    cells = _response_cells(scm)
    cell_doms = [scm.domains.get(node, _DEFAULT_DOMAIN) for (node, _c) in cells]
    latent_names = list(scm.latents)
    lat_dom = scm.latent_domain
    events = (*gamma, *delta)

    p_both = 0.0   # P(γ ∧ δ)
    p_den = 0.0    # P(δ)
    for lat_vals in itertools.product(lat_dom, repeat=len(latent_names)):
        latents = dict(zip(latent_names, lat_vals))
        w_lat = 1.0
        for name, v in latents.items():
            w_lat *= scm.latent_dist[name][v]
        if w_lat == 0.0:
            continue
        for resp_vals in itertools.product(*cell_doms):
            resp = {cells[i]: resp_vals[i] for i in range(len(cells))}
            w = w_lat
            for (node, combo), v in resp.items():
                w *= scm.cpt[node][combo][v]
            if w == 0.0:
                continue
            got = _eval_world(scm, latents, resp, events)
            hit = {e: g == e.value for e, g in zip(events, got)}
            if all(hit[e] for e in delta):
                p_den += w
                if all(hit[e] for e in gamma):
                    p_both += w
    return p_both, p_den


# =================================================== tiny graphs
def _chain_scm(seed):
    # X -> Y, no confounding.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    scm = _sample_scm(g, frozenset(), {}, random.Random(seed))
    return g, scm


def _confounded_scm(seed):
    # X -> Y with X <-> Y (a shared latent) — cross-world queries feel it.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    bi = frozenset({frozenset({X, Y})})
    scm = _sample_scm(g, bi, {}, random.Random(seed))
    return g, scm


def _mediator_scm(seed):
    # X -> Z -> Y with X <-> Y.
    g = nx.DiGraph()
    g.add_edges_from([(X, Z), (Z, Y)])
    bi = frozenset({frozenset({X, Y})})
    scm = _sample_scm(g, bi, {}, random.Random(seed))
    return g, scm


# =================================================== unconditional P(γ)
def test_vectorized_equals_exact_simple_effect():
    # P(Y_{x=1} = 1)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    for seed in range(4):
        g, scm = _chain_scm(seed)
        topo = list(nx.topological_sort(g))
        exact, _ = _exact_probs(scm, gamma)
        vec = _counterfactual_true_mc(
            scm, gamma, topo, 120_000, np.random.default_rng(seed)
        )
        assert abs(vec - exact) < 0.01, f"seed {seed}: vec={vec:.4f} exact={exact:.4f}"


def test_vectorized_equals_exact_cross_world_pns():
    # P(y_x ∧ x') — two different worlds sharing the confounding latent; the
    # canonical PN/PNS building block, and the query most sensitive to the
    # shared-exogenous / independent-response semantics.
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    for seed in range(4):
        g, scm = _confounded_scm(seed)
        topo = list(nx.topological_sort(g))
        exact, _ = _exact_probs(scm, gamma)
        vec = _counterfactual_true_mc(
            scm, gamma, topo, 200_000, np.random.default_rng(100 + seed)
        )
        assert abs(vec - exact) < 0.01, f"seed {seed}: vec={vec:.4f} exact={exact:.4f}"


def test_vectorized_equals_exact_mediated():
    # A mediated cross-world query on X -> Z -> Y with X <-> Y.
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(Z, frozenset({(X, False)}), True),
    )
    for seed in range(3):
        g, scm = _mediator_scm(seed)
        topo = list(nx.topological_sort(g))
        exact, _ = _exact_probs(scm, gamma)
        vec = _counterfactual_true_mc(
            scm, gamma, topo, 200_000, np.random.default_rng(7 + seed)
        )
        assert abs(vec - exact) < 0.012, f"seed {seed}: vec={vec:.4f} exact={exact:.4f}"


# =================================================== conditional P(γ|δ)
def test_conditional_vectorized_equals_exact():
    # P(y_x ∧ x' | z) style: a γ over two worlds, conditioned on a factual δ.
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    delta = (CtfEvent(Y, frozenset(), True),)   # factual Y=1
    for seed in range(4):
        g, scm = _confounded_scm(seed)
        topo = list(nx.topological_sort(g))
        both, den = _exact_probs(scm, gamma, delta)
        exact = both / den if den else 0.0
        vec, den_ct = _conditional_true_mc(
            scm, gamma, delta, topo, 240_000, np.random.default_rng(31 + seed)
        )
        assert den_ct > 1000, f"seed {seed}: conditioning too rare ({den_ct})"
        assert abs(vec - exact) < 0.015, f"seed {seed}: vec={vec:.4f} exact={exact:.4f}"


# ============= the shared tests/ctf_mc_oracle (D1 second implementation)
# The ID*/IDC*/estimation tests cross-check their formulas against
# tests.ctf_mc_oracle, NOT the product's semantic_probe. It is a distinct
# implementation, so its own correctness is pinned against exact enumeration
# here — the same ground truth the product MC is held to.
def test_shared_oracle_equals_exact():
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    for seed in range(4):
        g, scm = _confounded_scm(seed)
        exact, _ = _exact_probs(scm, gamma)
        got = _oracle_cf(scm, g, gamma, 200_000, 500 + seed)
        assert abs(got - exact) < 0.01, f"seed {seed}: oracle={got:.4f} exact={exact:.4f}"


def test_shared_oracle_conditional_equals_exact():
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    delta = (CtfEvent(Y, frozenset(), True),)
    for seed in range(4):
        g, scm = _confounded_scm(seed)
        both, den = _exact_probs(scm, gamma, delta)
        exact = both / den if den else 0.0
        got, den_ct = _oracle_cond(scm, g, gamma, delta, 240_000, 900 + seed)
        assert den_ct > 1000, f"seed {seed}: conditioning too rare ({den_ct})"
        assert abs(got - exact) < 0.015, f"seed {seed}: oracle={got:.4f} exact={exact:.4f}"


# ================= the production EXACT path (a second implementation)
# The probe now sums the background exactly whenever it fits under the cap,
# and samples only above it. That sum is production code computing the same
# ground truth this file enumerates independently, so it is held to it — to
# floating point, because both are exact and a disagreement would be about
# the semantics rather than about sampling error.


def test_production_exact_equals_independent_enumeration():
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    for build in (_chain_scm, _confounded_scm, _mediator_scm):
        for seed in range(4):
            g, scm = build(seed)
            topo = list(nx.topological_sort(g))
            assert _background_size(scm, topo) <= _EXACT_BACKGROUND_CAP
            exact, _ = _exact_probs(scm, gamma)
            got = _counterfactual_true_exact(scm, gamma, topo)
            assert abs(got - exact) < 1e-12, (
                f"{build.__name__} seed {seed}: got={got!r} exact={exact!r}")


def test_production_exact_conditional_equals_independent_enumeration():
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(X, frozenset(), False),
    )
    delta = (CtfEvent(Y, frozenset(), True),)
    for seed in range(4):
        g, scm = _confounded_scm(seed)
        topo = list(nx.topological_sort(g))
        both, den = _exact_probs(scm, gamma, delta)
        want = both / den if den else 0.0
        got, got_den = _conditional_true_exact(scm, gamma, delta, topo)
        assert abs(got - want) < 1e-12, f"seed {seed}: {got!r} vs {want!r}"
        assert abs(got_den - den) < 1e-12, f"seed {seed}: {got_den!r} vs {den!r}"
