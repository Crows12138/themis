"""A shorter conditional is sought among the entries theta holds.

When a formula asks for P(t | given) and theta lacks it, the evaluator
looks for the same conditional under part of ``given`` — the marginal-
independence lookup, and the diagnosis that says why the graph refused one.
Both used to spell every subset of ``given`` and ask theta for each. A
general-ID factor conditions on every predecessor of its target, so on a
graph of fifteen variables a question never came back; the demo's server
spent a core on one for an hour and a half.

Only an entry theta holds can be a candidate. What is pinned here is that
the search still tries the candidates the subset walk tried, in its order
— fewest atoms left out first, then as ``itertools.combinations`` reaches
them in the conditioning sorted by predicate and value — on both the
runtime and the verifier's own copy, and that theta is asked about as many
entries as it holds rather than as many subsets as there are.
"""
from __future__ import annotations

import itertools
import random

import networkx as nx
import pytest

from themis.runtime import numeric_estimator as runtime
from themis.runtime.numeric_estimator import (
    ProbabilityKey, Theta, format_probability_key)
from themis.runtime.structural_solver import m_separated
from themis.types import Atom, ConstTerm
from themis.verifier import rules as verifier


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _separated_by_the_runtime(graph, bidirected, target, extra, conditioning):
    return m_separated(graph, bidirected, target, extra, tuple(conditioning))


def _separated_by_the_verifier(graph, bidirected, target, extra, conditioning):
    return not verifier._verifier_is_m_connected(
        graph, bidirected, target, extra, frozenset(conditioning))


def _subset_walk(key, theta):
    """The search as it was written: every subset of the conditioning,
    fewest left out first, asked of theta in turn."""
    ordered = sorted(key.given, key=lambda p: (p[0].predicate, str(p[1])))
    for size in range(1, len(key.given) + 1):
        for left_out in itertools.combinations(ordered, size):
            reduced = ProbabilityKey(
                key.target_atom, key.target_value,
                frozenset(p for p in key.given if p not in left_out),
                key.population)
            if reduced in theta.entries:
                yield reduced, left_out


def _lookup_as_it_was(key, theta, graph, bidirected, separated):
    for reduced, left_out in _subset_walk(key, theta):
        if graph is not None and not all(
                separated(graph, bidirected, key.target_atom, a,
                          [b for b, _ in reduced.given])
                for a, _ in left_out):
            continue
        return theta.entries[reduced]
    return None


def _diagnosis_as_it_was(key, theta, graph, bidirected, separated):
    if graph is None:
        return None
    for reduced, left_out in _subset_walk(key, theta):
        if not reduced.given:
            continue
        if all(separated(graph, bidirected, key.target_atom, a,
                         [b for b, _ in reduced.given])
               for a, _ in left_out):
            continue
        return {
            "have": format_probability_key(reduced),
            "variable": key.target_atom.predicate,
            "extras": ",".join(a.predicate for a, _ in left_out),
            "conditioning": ",".join(
                a.predicate for a, _ in reduced.given) or "∅",
        }
    return None


SIDES = {
    "runtime": (runtime._try_marginal_independence_lookup,
                runtime._diagnose_marginal_independence_refusal,
                _separated_by_the_runtime),
    "verifier": (verifier._verifier_marginal_independence_lookup,
                 verifier._verifier_diagnose_marginal_independence_refusal,
                 _separated_by_the_verifier),
}


def _case(seed):
    """A target conditioned on five atoms, a graph over them, and a theta
    holding some of the target's shorter conditionals among entries that
    are not candidates: another value, another population, another target,
    a conditioning with an atom the key does not have."""
    rng = random.Random(seed)
    names = rng.sample("abcdefgh", 6)
    target, given_atoms = _A(names[0]), [_A(n) for n in names[1:]]
    given = frozenset((a, rng.choice((True, False))) for a in given_atoms)
    nodes = [target, *given_atoms]
    rng.shuffle(nodes)
    graph = nx.DiGraph()
    graph.add_nodes_from(nodes)
    graph.add_edges_from((u, v) for i, u in enumerate(nodes)
                         for v in nodes[i + 1:] if rng.random() < 0.35)
    bidirected = frozenset(frozenset(pair)
                           for pair in itertools.combinations(nodes, 2)
                           if rng.random() < 0.1)
    entries = {}
    for _ in range(rng.randint(0, 9)):
        kept = frozenset(p for p in given if rng.random() < 0.5)
        if kept == given:
            continue
        entries[ProbabilityKey(target, True, kept)] = round(rng.random(), 3)
    entries[ProbabilityKey(target, False, frozenset())] = 0.5
    entries[ProbabilityKey(target, True, frozenset(), "elsewhere")] = 0.25
    entries[ProbabilityKey(given_atoms[0], True, frozenset())] = 0.75
    entries[ProbabilityKey(target, True, frozenset({(_A("zz"), True)}))] = 0.125
    return ProbabilityKey(target, True, given), Theta(entries=entries), graph, bidirected


@pytest.mark.parametrize("side", sorted(SIDES))
@pytest.mark.parametrize("seed", range(60))
def test_the_candidates_are_the_subset_walks_in_its_order(side, seed):
    lookup, diagnosis, separated = SIDES[side]
    key, theta, graph, bidirected = _case(seed)
    for g, b in ((graph, bidirected), (None, None)):
        assert lookup(key, theta, graph=g, bidirected=b) == _lookup_as_it_was(
            key, theta, g, b, separated)
        assert diagnosis(key, theta, graph=g, bidirected=b) == _diagnosis_as_it_was(
            key, theta, g, b, separated)


def test_the_cases_reach_every_answer():
    """The sixty cases above are worth something only if they include a
    lookup that finds an entry, one that finds none, and a refusal."""
    found = refused = empty = 0
    for seed in range(60):
        key, theta, graph, bidirected = _case(seed)
        value = runtime._try_marginal_independence_lookup(
            key, theta, graph=graph, bidirected=bidirected)
        found += value is not None
        empty += value is None
        refused += runtime._diagnose_marginal_independence_refusal(
            key, theta, graph=graph, bidirected=bidirected) is not None
    assert found and empty and refused


class _Counted(dict):
    """Entries that fail a test once theta has been asked, by name, about
    many more conditionals than it holds."""

    BUDGET = 100

    def __init__(self, *args):
        super().__init__(*args)
        self.asked = 0

    def _ask(self):
        self.asked += 1
        if self.asked > self.BUDGET:
            raise AssertionError(
                f"theta holds {len(self)} entries and was asked about "
                f"{self.asked} conditionals")

    def get(self, key, default=None):
        self._ask()
        return super().get(key, default)

    def __contains__(self, key):
        self._ask()
        return super().__contains__(key)


@pytest.mark.parametrize("side", sorted(SIDES))
def test_a_long_conditioning_costs_what_theta_holds(side):
    """Forty atoms in the conditioning are 2^40 subsets. The target's
    parents are the chain's two ends, so its conditional given both is
    licensed by the graph and its conditional given one end is not."""
    lookup, diagnosis, _ = SIDES[side]
    target = _A("y")
    chain = [_A(f"v{i:02d}") for i in range(40)]
    graph = nx.DiGraph()
    graph.add_edges_from(zip(chain, chain[1:]))
    graph.add_edges_from(((chain[0], target), (chain[-1], target)))
    one_end = ProbabilityKey(target, True, frozenset({(chain[-1], True)}))
    both_ends = ProbabilityKey(
        target, True, frozenset({(chain[0], True), (chain[-1], True)}))
    theta = Theta(entries=_Counted({one_end: 0.3, both_ends: 0.6}))
    key = ProbabilityKey(target, True, frozenset((a, True) for a in chain))
    assert lookup(key, theta, graph=None, bidirected=None) == 0.6
    assert lookup(key, theta, graph=graph, bidirected=frozenset()) == 0.6
    refusal = diagnosis(key, theta, graph=graph, bidirected=frozenset())
    assert refusal["have"] == format_probability_key(one_end)
    assert refusal["extras"] == ",".join(a.predicate for a in chain[:-1])
