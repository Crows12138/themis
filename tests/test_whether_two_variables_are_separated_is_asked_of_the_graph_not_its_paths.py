"""Whether two variables are separated is asked of the graph, not its paths.

m-separation — is every path between two variables blocked, given a set
held fixed? — was answered on both sides by listing every simple path and
checking each. The number of paths grows exponentially with the graph. The
question is asked where a formula reads a table theta does not hold as one it
does (``P(z₂ | z₁)`` as ``P(z₂)``, where the graph says the two are
independent), and a sum over a confounder table asks it once per row. On the
nineteen-variable graph a translator drew for "did I do badly on the exam
because I slept badly?", with the joint read through seven confounders
(#808), the answer took 78 seconds on the demo server, and the verifier as
long again: 97% and 99% of each was spent listing paths.

Both sides now search the graph instead: states of (variable, whether the
edge it was reached by points into it), each visited once, under the same
two rules — a variable passed through blocks when held, unless both edges
beside it point into it, when it blocks unless it or a descendant is held.
An open walk shortens to an open path, so the answer is the same; this pins
that it is, against the listing written from the definition, on random
graphs with bidirected edges, for the two questions each side asks: any open
path, and an open path leaving its start along an edge pointing into it (a
back door).
"""
from __future__ import annotations

import itertools
import random

import networkx as nx
import pytest

from themis.runtime import structural_solver
from themis.types import Atom
from themis.verifier import rules as verifier_rules


def _open_path_exists(graph, bidirected, start, end, held, *, back_door):
    """The definition, path by path."""
    if start == end:
        return False
    edges = [(t, h, False, True) for t, h in graph.edges()]
    edges += [(a, b, True, True) for a, b in (tuple(p) for p in bidirected)]
    nodes = set(graph.nodes()).union(*bidirected)
    if start not in nodes or end not in nodes:
        return False

    def at(edge, node):
        """Whether ``edge`` has its arrowhead at ``node``."""
        tail, head, into_tail, into_head = edge
        return into_head if node == head else into_tail

    def walk(node, path, came_by):
        for edge in edges:
            tail, head = edge[0], edge[1]
            if node not in (tail, head):
                continue
            onward = head if node == tail else tail
            if onward in path:
                continue
            if came_by is None:
                if back_door and not at(edge, node):
                    continue
            else:
                collider = at(came_by, node) and at(edge, node)
                if collider:
                    if not ({node} | (nx.descendants(graph, node)
                                      if node in graph else set())) & held:
                        continue
                elif node in held:
                    continue
            if onward == end:
                return True
            if walk(onward, path | {onward}, edge):
                return True
        return False

    return walk(start, {start}, None)


def _a(name):
    return Atom(predicate=name, args=())


def _random_admg(rng, n):
    names = [_a(f"v{i}") for i in range(n)]
    graph = nx.DiGraph()
    graph.add_nodes_from(names[: n - 1])  # the last may sit on a bow alone
    for i, j in itertools.combinations(range(n), 2):
        if rng.random() < 0.35:
            graph.add_edge(names[i], names[j])
    bidirected = frozenset(
        frozenset((names[i], names[j]))
        for i, j in itertools.combinations(range(n), 2)
        if rng.random() < 0.2)
    return names, graph, bidirected


_SIDES = {
    "runtime": (
        lambda g, b, s, e, h: structural_solver.is_m_connected(g, b, s, e, tuple(h)),
        lambda g, b, s, e, h: structural_solver._is_admg_backdoor_connected(
            g, b, s, e, frozenset(h)),
    ),
    "verifier": (
        lambda g, b, s, e, h: verifier_rules._verifier_is_m_connected(
            g, b, s, e, frozenset(h)),
        lambda g, b, s, e, h: verifier_rules._verifier_is_admg_backdoor_connected(
            g, b, s, e, frozenset(h)),
    ),
}


@pytest.mark.parametrize("side", sorted(_SIDES))
@pytest.mark.parametrize("seed", range(8))
def test_the_search_agrees_with_the_paths_one_by_one(side, seed):
    connected, back_door = _SIDES[side]
    rng = random.Random(seed)
    asked = 0
    both_answers = set()
    for _ in range(30):
        names, graph, bidirected = _random_admg(rng, rng.randint(3, 7))
        for start, end in itertools.permutations(names, 2):
            # Held sets that sometimes include an end: the paths answer
            # those too, and so must the search.
            held = {v for v in names if rng.random() < 0.3}
            for ask, is_back_door in ((connected, False), (back_door, True)):
                expected = _open_path_exists(graph, bidirected, start, end,
                                             held, back_door=is_back_door)
                got = ask(graph, bidirected, start, end, held)
                asked += 1
                both_answers.add(expected)
                assert got == expected, (side, is_back_door, sorted(
                    graph.edges()), sorted(map(tuple, bidirected)), start, end,
                    held)
    assert asked > 1000 and both_answers == {True, False}, (asked, both_answers)


@pytest.mark.parametrize("side", sorted(_SIDES))
def test_no_path_is_listed(side, monkeypatch):
    """The listing is what cost the time, so it is what is pinned out."""
    def refuse(*args, **kwargs):
        raise AssertionError("a simple path was listed")
    monkeypatch.setattr(nx, "all_simple_edge_paths", refuse)
    monkeypatch.setattr(nx, "all_simple_paths", refuse)
    names, graph, bidirected = _random_admg(random.Random(0), 7)
    connected, back_door = _SIDES[side]
    for start, end in itertools.permutations(names, 2):
        connected(graph, bidirected, start, end, set(names[3:5]))
        back_door(graph, bidirected, start, end, set(names[3:5]))
