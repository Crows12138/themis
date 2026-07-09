"""Independent, vectorized counterfactual Monte-Carlo oracle for the ID* /
IDC* / estimation tests.

This is the D1 "second implementation": it reads ONLY the sampled ``_SCM``
structure (``parents`` / ``cpt`` / ``latent_dist``) and never imports the
identification code (``id_star`` / ``idc_star`` / ``ctf_conjunction``) NOR the
product's ``semantic_probe`` Monte-Carlo — so an agreement between an
identification-produced formula and this oracle is genuine cross-validation,
not a tautology.

It computes the true counterfactual probability by drawing all ``n`` replicates
AT ONCE as integer arrays and propagating each hypothetical world with a
handful of numpy ops. Semantics are the standard twin-network / response
function model, identical to the old per-file scalar oracles it replaces:

  * the exogenous background (the bidirected latents) is drawn ONCE per
    replicate and shared across every world;
  * a node's response to a given parent configuration is drawn once and shared
    across worlds, but responses to DIFFERENT configurations are independent
    (the canonical response-function SCM);
  * a conditional ``P(γ|δ)`` shares one background between numerator and
    denominator (a genuine conditional over parallel worlds).

The old scalar oracles (a Python loop, some recursive) churned millions of
small dict/tuple objects per call at 40k-240k draws and were a flaky Windows
native-fault (heap corruption / access violation) site under the deep pytest
callstack. Vectorizing removes the churn entirely. This oracle's equality to an
EXACT enumeration of the whole exogenous space is pinned by
``tests/test_counterfactual_mc_vectorized.py``.
"""
from __future__ import annotations

import itertools

import networkx as nx
import numpy as np

_DEFAULT_DOMAIN = (True, False)


def _sample_categorical(pvec: np.ndarray, n: int, rng) -> np.ndarray:
    """``n`` i.i.d. value-index draws from probability vector ``pvec``."""
    cum = np.cumsum(pvec)
    cum[-1] = 1.0
    return np.searchsorted(cum, rng.random(n), side="right").astype(np.int8)


def _world_values(scm, worlds, topo, n: int, rng):
    """``(world_values, value_to_index)`` — the length-``n`` int index array of
    every ``(world, node)``, by a vectorized forward pass over shared
    exogenous draws."""
    lat_dom = scm.latent_domain
    latents = {
        name: _sample_categorical(
            np.array([scm.latent_dist[name][v] for v in lat_dom], dtype=np.float64),
            n, rng,
        )
        for name in scm.latents
    }
    rows = np.arange(n)
    v2i: dict = {}
    radix: dict = {}
    response: dict = {}
    for node in topo:
        dom = scm.domains.get(node, _DEFAULT_DOMAIN)
        v2i[node] = {v: i for i, v in enumerate(dom)}
        par_doms = [
            lat_dom if isinstance(p, str) else scm.domains.get(p, _DEFAULT_DOMAIN)
            for p in scm.parents[node]
        ]
        sizes = [len(d) for d in par_doms]
        mult = [1] * len(sizes)
        acc = 1
        for k in range(len(sizes) - 1, -1, -1):
            mult[k] = acc
            acc *= sizes[k]
        radix[node] = mult
        table = np.empty((acc, n), dtype=np.int8)
        for ci, combo in enumerate(itertools.product(*par_doms) if par_doms else [()]):
            dist = scm.cpt[node][combo]
            table[ci] = _sample_categorical(
                np.array([dist[v] for v in dom], dtype=np.float64), n, rng
            )
        response[node] = table

    world_values: dict = {}
    for world in worlds:
        wd = dict(world)
        vals: dict = {}
        for node in topo:
            if node in wd:
                vals[node] = np.full(n, v2i[node][wd[node]], dtype=np.int8)
                continue
            combo_idx = np.zeros(n, dtype=np.int64)
            for k, p in enumerate(scm.parents[node]):
                pidx = latents[p] if isinstance(p, str) else vals[p]
                combo_idx += pidx.astype(np.int64) * radix[node][k]
            vals[node] = response[node][combo_idx, rows]
        world_values[world] = vals
    return world_values, v2i


def counterfactual_prob(scm, graph, gamma, n_draws: int, seed: int) -> float:
    """True ``P(γ)`` for a counterfactual conjunction ``gamma``."""
    topo = list(nx.topological_sort(graph))
    rng = np.random.default_rng(seed)
    wv, v2i = _world_values(scm, {e.subscript for e in gamma}, topo, n_draws, rng)
    mask = np.ones(n_draws, dtype=bool)
    for e in gamma:
        mask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    return float(np.count_nonzero(mask)) / n_draws


def conditional_prob(
    scm, graph, gamma, delta, n_draws: int, seed: int
) -> tuple[float, int]:
    """True ``P(γ|δ) = P(γ∧δ)/P(δ)`` sharing one background draw; returns
    ``(estimate, denominator_count)``."""
    topo = list(nx.topological_sort(graph))
    rng = np.random.default_rng(seed)
    worlds = {e.subscript for e in (*gamma, *delta)}
    wv, v2i = _world_values(scm, worlds, topo, n_draws, rng)
    dmask = np.ones(n_draws, dtype=bool)
    for e in delta:
        dmask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    nmask = dmask.copy()
    for e in gamma:
        nmask &= wv[e.subscript][e.variable] == v2i[e.variable][e.value]
    den = int(np.count_nonzero(dmask))
    return (float(np.count_nonzero(nmask)) / den if den else 0.0), den
