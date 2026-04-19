"""Unit tests for d-separation primitives.

Covers collider detection, descendant-based activation, multi-path
graphs, and defensive edge cases (nodes not in graph).
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.structural_solver import (
    is_d_connected,
    open_paths,
)
from themis.types import Atom, ConstTerm


def a(name: str) -> Atom:
    """Build a ground atom with a fixed object 'x' to keep tests terse."""
    return Atom(predicate=name, args=(ConstTerm(name="x"),))


def dag(edges: list[tuple[str, str]]) -> nx.DiGraph:
    g: nx.DiGraph = nx.DiGraph()
    for u, v in edges:
        g.add_edge(a(u), a(v))
    return g


# ------------------------------------------------------------------ chain

def test_chain_open_without_conditioning():
    g = dag([("x", "m"), ("m", "y")])
    assert is_d_connected(g, a("x"), a("y"), ())


def test_chain_blocked_by_mediator():
    g = dag([("x", "m"), ("m", "y")])
    assert not is_d_connected(g, a("x"), a("y"), (a("m"),))


# ------------------------------------------------------------------ fork

def test_fork_open_without_conditioning():
    g = dag([("z", "x"), ("z", "y")])
    assert is_d_connected(g, a("x"), a("y"), ())


def test_fork_blocked_by_common_cause():
    g = dag([("z", "x"), ("z", "y")])
    assert not is_d_connected(g, a("x"), a("y"), (a("z"),))


# ------------------------------------------------------------------ collider

def test_collider_closed_without_conditioning():
    g = dag([("x", "c"), ("y", "c")])
    assert not is_d_connected(g, a("x"), a("y"), ())


def test_collider_opened_by_conditioning():
    g = dag([("x", "c"), ("y", "c")])
    assert is_d_connected(g, a("x"), a("y"), (a("c"),))


def test_collider_opened_by_descendant_of_collider():
    # x -> c <- y, and c -> d; conditioning on d should open the collider.
    g = dag([("x", "c"), ("y", "c"), ("c", "d")])
    assert is_d_connected(g, a("x"), a("y"), (a("d"),))


# ------------------------------------------------------------------ mixed

def test_multiple_paths_one_open_is_enough():
    # Two parallel structures between x and y:
    #   open chain  x -> m -> y
    #   closed chain x -> k -> y with k in conditioning
    g = dag([("x", "m"), ("m", "y"), ("x", "k"), ("k", "y")])
    assert is_d_connected(g, a("x"), a("y"), (a("k"),))
    # And the only open path should appear in open_paths().
    paths = open_paths(g, a("x"), a("y"), (a("k"),))
    assert paths == ((a("x"), a("m"), a("y")),)


# ------------------------------------------------------------------ edges

def test_missing_endpoint_returns_false():
    g = dag([("x", "y")])
    assert not is_d_connected(g, a("x"), a("nope"), ())
    assert open_paths(g, a("x"), a("nope"), ()) == ()


def test_identical_endpoints_return_false():
    g = dag([("x", "y")])
    assert not is_d_connected(g, a("x"), a("x"), ())
