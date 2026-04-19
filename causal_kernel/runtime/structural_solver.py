"""Pure-structural reasoning on G(M).

Answers questions that depend only on graph topology:

- cause(A, B):  is there a directed path A -> ... -> B ?
- assoc(A, B | C):  is there a path between A and B that is open
  relative to conditioning set C (d-separation) ?
- backdoor paths from X to Y, and valid adjustment sets.

Completeness targets for v0.1 are stated in 理论框架_v0_1.md §14.

Slice 1 only implements directed-path queries (cause). d-separation,
back-door, and adjustment sets land in later slices.
"""
from __future__ import annotations

import networkx as nx

from ..types import Atom


def has_directed_path(graph: nx.DiGraph, src: Atom, dst: Atom) -> bool:
    """Return True iff a directed path src -> ... -> dst exists."""
    if src not in graph or dst not in graph:
        return False
    if src == dst:
        # A node has a trivial path to itself, but for cause() this
        # should not be reported as causal influence.
        return False
    return nx.has_path(graph, src, dst)


def directed_paths(
    graph: nx.DiGraph, src: Atom, dst: Atom
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate directed simple paths from src to dst.

    Used by the explanation layer to cite supporting_paths.
    """
    if src not in graph or dst not in graph or src == dst:
        return ()
    return tuple(tuple(p) for p in nx.all_simple_paths(graph, src, dst))


def _is_collider(graph: nx.DiGraph, u: Atom, v: Atom, w: Atom) -> bool:
    """True iff v is a collider on the path segment u - v - w, i.e.
    both directed edges u -> v and w -> v exist in the DAG."""
    return graph.has_edge(u, v) and graph.has_edge(w, v)


def _node_blocks_path(
    graph: nx.DiGraph,
    u: Atom,
    v: Atom,
    w: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """Decide whether intermediate node v blocks the path segment u - v - w.

    - Non-collider (chain / fork): blocked iff v is in conditioning.
    - Collider: blocked iff neither v nor any descendant of v is in
      conditioning (i.e. blocked when collider is NOT activated).
    """
    if _is_collider(graph, u, v, w):
        activated = {v} | nx.descendants(graph, v)
        return activated.isdisjoint(conditioning)
    return v in conditioning


def _path_is_open(
    graph: nx.DiGraph,
    path: tuple[Atom, ...],
    conditioning: frozenset[Atom],
) -> bool:
    """A simple undirected path is open iff no intermediate node blocks it."""
    for i in range(1, len(path) - 1):
        if _node_blocks_path(
            graph, path[i - 1], path[i], path[i + 1], conditioning
        ):
            return False
    return True


def _iter_undirected_simple_paths(
    graph: nx.DiGraph, src: Atom, dst: Atom
):
    """Iterate simple paths between src and dst ignoring edge direction."""
    return nx.all_simple_paths(graph.to_undirected(as_view=True), src, dst)


def is_d_connected(
    graph: nx.DiGraph,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> bool:
    """Return True iff at least one path between left and right is
    open given the conditioning set (d-separation criterion)."""
    if left not in graph or right not in graph or left == right:
        return False
    c_set = frozenset(conditioning)
    for path in _iter_undirected_simple_paths(graph, left, right):
        if _path_is_open(graph, tuple(path), c_set):
            return True
    return False


def open_paths(
    graph: nx.DiGraph,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate paths that are open under the conditioning set.

    Only the open paths are returned. Closed paths are intentionally
    omitted from the result structure for v0.1; if explanatory value
    requires listing them, extend ``StructuralResult`` separately.
    """
    if left not in graph or right not in graph or left == right:
        return ()
    c_set = frozenset(conditioning)
    return tuple(
        tuple(p)
        for p in _iter_undirected_simple_paths(graph, left, right)
        if _path_is_open(graph, tuple(p), c_set)
    )


def backdoor_paths(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate all back-door paths from X to Y.

    A back-door path is an undirected simple path between X and Y
    whose first edge points INTO X (i.e. there exists a directed
    edge ``path[1] -> X`` in the DAG). These are the paths that
    can carry confounding association.
    """
    if x not in graph or y not in graph or x == y:
        return ()
    result: list[tuple[Atom, ...]] = []
    for raw in _iter_undirected_simple_paths(graph, x, y):
        path = tuple(raw)
        if len(path) >= 2 and graph.has_edge(path[1], x):
            result.append(path)
    return tuple(result)


def minimal_adjustment_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    given: tuple[Atom, ...] = (),
) -> tuple[frozenset[Atom], ...]:
    """Find all subset-minimal **additional** back-door adjustment sets,
    disjoint from ``given``.

    A tuple element ``Z`` returned from this function satisfies:

    - ``Z`` is disjoint from ``given``,
    - no atom in ``Z ∪ given`` is a descendant of X,
    - ``Z ∪ given`` blocks every back-door path from X to Y, and
    - no proper subset ``Z' ⊊ Z`` also satisfies the above.

    The formula consumer treats ``given`` as already-conditioned context
    from the query; only ``Z`` is summed out.

    Returns ``()`` when X or Y lies outside the graph, or when
    ``given`` itself violates the back-door criterion (e.g. contains
    a descendant of X, or contains X or Y).

    Returns ``(frozenset(),)`` when ``given`` alone already blocks
    all back-door paths.
    """
    from itertools import combinations

    if x not in graph or y not in graph or x == y:
        return ()

    given_set = frozenset(given)
    descendants_x = nx.descendants(graph, x)

    # given must itself obey the back-door criterion's pre-conditions.
    if given_set & (descendants_x | {x, y}):
        return ()

    bdoors = backdoor_paths(graph, x, y)
    forbidden = descendants_x | {x, y} | given_set
    candidates: list[Atom] = [n for n in graph.nodes if n not in forbidden]

    def blocks_all(z: frozenset[Atom]) -> bool:
        combined = z | given_set
        for path in bdoors:
            if _path_is_open(graph, path, combined):
                return False
        return True

    minimal: list[frozenset[Atom]] = []
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            z = frozenset(combo)
            if any(existing < z for existing in minimal):
                continue
            if blocks_all(z):
                minimal.append(z)
    return tuple(minimal)
