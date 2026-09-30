"""A derivation is followed only where theta can close it.

When a formula asks for P(t | given) and theta lacks it, the evaluator
tries to marginalize it out of what theta holds: P(t | given) = Σ_z
P(t | given, z) · P(z | given), each outer factor looked up or derived the
same way, down to a fixed depth. The search tried every atom theta
mentions as Z, and followed each one down, before learning that none could
end anywhere. On a graph of fifteen variables whose tables a model had
filled, an estimate asked for 768 missing conditionals, each search failed,
and between them they made 244,352 calls, every one walking theta: two
minutes on a desktop, nearly seven on the demo's server.

An outer factor keeps the target and gains one condition, and is found only
when its conditions are an entry's. So the search can end only at an entry
for the same target that holds every condition of the missing key and adds
at most one per depth left, and a Z none of whose values such an entry adds
fails however far it is followed. What is pinned here is that skipping
those changes no answer — on the runtime and on the verifier's own copy,
against the search as it was — and that theta is asked about a handful of
conditionals where it was asked about thousands.
"""
from __future__ import annotations

import itertools
import random

import networkx as nx
import pytest

from themis.runtime import numeric_estimator as runtime
from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.types import Atom, ConstTerm
from themis.verifier import rules as verifier


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


# --- the search as it was ----------------------------------------------------

def _bayes_as_it_was(key, theta, depth, graph, bidirected):
    if depth > 2 or not key.given:
        return None
    for a_atom, a_value in key.given:
        if a_atom == key.target_atom:
            continue
        reduced = frozenset(p for p in key.given if p[0] != a_atom)
        found = []
        for factor in (
                ProbabilityKey(a_atom, a_value,
                               frozenset(reduced | {(key.target_atom, key.target_value)}),
                               key.population),
                ProbabilityKey(key.target_atom, key.target_value, reduced, key.population),
                ProbabilityKey(a_atom, a_value, reduced, key.population)):
            value = theta.entries.get(factor)
            if value is None:
                value = _derive_as_it_was(factor, theta, depth + 1, graph, bidirected)
            found.append(value)
            if value is None:
                break
        if None in found or found[2] == 0:
            continue
        return found[0] * found[1] / found[2]
    return None


def _derive_as_it_was(key, theta, depth=0, graph=None, bidirected=None):
    """Every atom theta mentions tried as Z, each followed down."""
    if depth > 3:
        return None
    candidates, seen = [], set()
    for entry in theta.entries:
        if entry.population != key.population:
            continue
        for ga, _ in entry.given:
            if ga != key.target_atom and ga not in seen:
                candidates.append(ga)
                seen.add(ga)
        if entry.target_atom != key.target_atom and entry.target_atom not in seen:
            candidates.append(entry.target_atom)
            seen.add(entry.target_atom)
    given_atoms = {ga for ga, _ in key.given}
    for z in candidates:
        if z == key.target_atom or z in given_atoms:
            continue
        domain = theta.domain_of(z)
        outer, inner = {}, {}
        for v in domain:
            outer_key = ProbabilityKey(key.target_atom, key.target_value,
                                       frozenset(key.given | {(z, v)}), key.population)
            value = theta.entries.get(outer_key)
            if value is None:
                value = _derive_as_it_was(outer_key, theta, depth + 1, graph, bidirected)
            if value is None:
                break
            outer[v] = value
        if len(outer) < len(domain):
            continue
        for v in domain:
            inner_key = ProbabilityKey(z, v, key.given, key.population)
            value = theta.entries.get(inner_key)
            if value is None:
                value = _derive_as_it_was(inner_key, theta, depth + 1, graph, bidirected)
            if value is None:
                value = _bayes_as_it_was(inner_key, theta, depth + 1, graph, bidirected)
            if value is None:
                value = runtime._try_marginal_independence_lookup(
                    inner_key, theta, graph=graph, bidirected=bidirected)
            if value is None:
                break
            inner[v] = value
        if len(inner) < len(domain):
            continue
        return sum(outer[v] * inner[v] for v in domain)
    return None


SIDES = {
    "runtime": runtime._try_derive_via_marginalization,
    "verifier": verifier._verifier_derive_via_marginalization,
}


# --- the cases ---------------------------------------------------------------

NAMES = "abcdef"


def _case(seed):
    """Tables of a small graph, some whole and some in part, with entries
    that are no candidate beside them (another population, another value),
    and conditionals to derive that theta lacks."""
    rng = random.Random(seed)
    atoms = [_A(n) for n in rng.sample(NAMES, len(NAMES))]
    graph = nx.DiGraph()
    graph.add_nodes_from(atoms)
    entries = {}
    for i, atom in enumerate(atoms):
        parents = [p for p in atoms[:i] if rng.random() < 0.5]
        graph.add_edges_from((p, atom) for p in parents)
        whole = rng.random() < 0.7
        for values in itertools.product((True, False), repeat=len(parents)):
            if not whole and rng.random() < 0.4:
                continue
            given = frozenset(zip(parents, values))
            p = round(rng.uniform(0.05, 0.95), 3)
            entries[ProbabilityKey(atom, True, given)] = p
            if rng.random() < 0.5:
                entries[ProbabilityKey(atom, False, given)] = round(1 - p, 3)
    for _ in range(rng.randint(0, 4)):
        target = rng.choice(atoms)
        given = frozenset((a, rng.choice((True, False)))
                          for a in rng.sample([a for a in atoms if a != target],
                                              rng.randint(0, 3)))
        entries.setdefault(ProbabilityKey(target, True, given, "elsewhere"),
                           round(rng.random(), 3))
    bidirected = frozenset(frozenset(pair) for pair in itertools.combinations(atoms, 2)
                           if rng.random() < 0.1)
    missing = []
    while len(missing) < 4:
        target = rng.choice(atoms)
        given = frozenset((a, rng.choice((True, False)))
                          for a in rng.sample([a for a in atoms if a != target],
                                              rng.randint(0, 3)))
        key = ProbabilityKey(target, rng.choice((True, False)), given)
        if key not in entries:
            missing.append(key)
    return Theta(entries=entries), graph, bidirected, missing


@pytest.mark.parametrize("side", sorted(SIDES))
@pytest.mark.parametrize("seed", range(40))
def test_skipping_what_cannot_close_changes_no_answer(side, seed):
    derive = SIDES[side]
    theta, graph, bidirected, missing = _case(seed)
    for key in missing:
        for g, b in ((graph, bidirected), (None, None)):
            assert derive(key, theta, graph=g, bidirected=b) == _derive_as_it_was(
                key, theta, 0, g, b), key


def _deep_case(parents: int):
    """An outcome whose parents are all roots, its table whole and each
    parent's prevalence given: P(y) is marginalized one parent per depth,
    and closes only if there are no more parents than depths."""
    y = _A("y")
    roots = [_A(f"r{i}") for i in range(parents)]
    graph = nx.DiGraph([(r, y) for r in roots])
    entries = {}
    for values in itertools.product((True, False), repeat=parents):
        entries[ProbabilityKey(y, True, frozenset(zip(roots, values)))] = round(
            0.1 + 0.8 * sum(values) / parents, 3)
    for i, r in enumerate(roots):
        entries[ProbabilityKey(r, True, frozenset())] = 0.2 + 0.1 * i
        entries[ProbabilityKey(r, False, frozenset())] = round(0.8 - 0.1 * i, 3)
    return Theta(entries=entries), graph, ProbabilityKey(y, True, frozenset())


@pytest.mark.parametrize("side", sorted(SIDES))
@pytest.mark.parametrize("parents", [3, 4, 5])
def test_a_derivation_that_takes_every_depth_still_closes(side, parents):
    """Four parents take all four depths; five are one too many, before
    and now."""
    theta, graph, key = _deep_case(parents)
    got = SIDES[side](key, theta, graph=graph, bidirected=frozenset())
    assert got == _derive_as_it_was(key, theta, 0, graph, frozenset())
    assert (got is not None) == (parents <= 4)


def test_the_cases_reach_every_answer():
    """The cases above are worth something only if some conditionals are
    derived, some are not, and some were searched for at length before."""
    derived = underived = 0
    for seed in range(40):
        theta, graph, bidirected, missing = _case(seed)
        for key in missing:
            value = runtime._try_derive_via_marginalization(
                key, theta, graph=graph, bidirected=bidirected)
            derived += value is not None
            underived += value is None
    assert derived and underived


class _Counted(dict):
    """Entries that count how many conditionals theta is asked about by name."""

    def __init__(self, *args):
        super().__init__(*args)
        self.asked = 0

    def get(self, key, default=None):
        self.asked += 1
        return super().get(key, default)

    def __contains__(self, key):
        self.asked += 1
        return super().__contains__(key)


def _a_wide_table():
    """An outcome with eight parents, its table whole, and each parent's
    prevalence: P(y | x) is five conditions short of any entry."""
    y = _A("y")
    parents = [_A(f"p{i}") for i in range(8)]
    entries = {}
    for values in itertools.product((True, False), repeat=len(parents)):
        entries[ProbabilityKey(y, True, frozenset(zip(parents, values)))] = (
            0.1 + 0.8 * sum(values) / len(parents))
    for p in parents:
        entries[ProbabilityKey(p, True, frozenset())] = 0.5
    return ProbabilityKey(y, True, frozenset({(parents[0], True)})), entries


@pytest.mark.parametrize("side", sorted(SIDES))
def test_a_wide_table_costs_a_handful_of_questions(side):
    key, entries = _a_wide_table()
    before = Theta(entries=_Counted(entries))
    assert _derive_as_it_was(key, before) is None
    now = Theta(entries=_Counted(entries))
    assert SIDES[side](key, now) is None
    assert before.entries.asked > 1000
    assert now.entries.asked <= 10
