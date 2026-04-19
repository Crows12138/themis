"""Unit tests for backdoor path enumeration and adjustment set search."""
from __future__ import annotations

import networkx as nx

from causal_kernel.runtime.structural_solver import (
    backdoor_paths,
    minimal_adjustment_sets,
)
from causal_kernel.types import Atom, ConstTerm


def a(name: str) -> Atom:
    return Atom(predicate=name, args=(ConstTerm(name="x"),))


def dag(edges):
    g: nx.DiGraph = nx.DiGraph()
    for u, v in edges:
        g.add_edge(a(u), a(v))
    return g


def test_no_backdoor_when_x_has_no_parents():
    g = dag([("x", "y")])
    assert backdoor_paths(g, a("x"), a("y")) == ()


def test_backdoor_via_common_cause():
    g = dag([("z", "x"), ("z", "y"), ("x", "y")])
    paths = backdoor_paths(g, a("x"), a("y"))
    # x - z - y is the only backdoor path (ignoring the direct x->y edge)
    assert len(paths) == 1
    assert paths[0] == (a("x"), a("z"), a("y"))


def test_adjustment_set_empty_when_no_confounder():
    g = dag([("x", "y")])
    sets = minimal_adjustment_sets(g, a("x"), a("y"))
    assert sets == (frozenset(),)


def test_adjustment_set_singleton_for_single_confounder():
    g = dag([("z", "x"), ("z", "y"), ("x", "y")])
    sets = minimal_adjustment_sets(g, a("x"), a("y"))
    assert frozenset({a("z")}) in sets
    # empty set is NOT valid here
    assert frozenset() not in sets


def test_adjustment_set_excludes_descendants_of_x():
    # x -> m -> y, also z -> x, z -> y (confounder)
    # m is a descendant of x and must never be in the adjustment set
    g = dag([("z", "x"), ("z", "y"), ("x", "m"), ("m", "y")])
    sets = minimal_adjustment_sets(g, a("x"), a("y"))
    for s in sets:
        assert a("m") not in s
    # {z} should still be a valid minimal adjustment
    assert frozenset({a("z")}) in sets


def test_adjustment_set_collider_not_required():
    # x -> c <- y creates a collider between x and y, closed by default
    # with only the direct x->y edge, no backdoor exists.
    g = dag([("x", "y"), ("x", "c"), ("y", "c")])
    sets = minimal_adjustment_sets(g, a("x"), a("y"))
    # empty set suffices: no backdoor to block
    assert frozenset() in sets
