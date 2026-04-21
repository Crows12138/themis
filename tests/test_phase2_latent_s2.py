"""Phase 2.latent S2: ADMG solver primitives.

Pure-algorithm tests for ``structural_solver.is_m_connected`` /
``m_separated`` / ``c_components``. These primitives must not depend
on scheduler, graph_projection, or any other runtime piece — the S2
slice scope is deliberately narrow (PHASE_2_LATENT_CHARTER.md §7).

Regression guarantee (charter §7 S2 threshold): with an empty
bidirected edge set the m-separation answer must agree with the
existing ``is_d_connected``.
"""
from __future__ import annotations

from itertools import combinations

import networkx as nx
import pytest

from themis.runtime.structural_solver import (
    c_components,
    is_d_connected,
    is_m_connected,
    m_separated,
)
from themis.types import Atom, ConstTerm


# =============================================================== helpers

def _a(name: str) -> Atom:
    return Atom(predicate=name, args=(ConstTerm(name="me"),))


def _dg(edges: list[tuple[str, str]], extra_nodes: list[str] = ()) -> nx.DiGraph:
    g = nx.DiGraph()
    for n in extra_nodes:
        g.add_node(_a(n))
    for u, v in edges:
        g.add_edge(_a(u), _a(v))
    return g


def _bidir(pairs: list[tuple[str, str]]) -> frozenset[frozenset[Atom]]:
    return frozenset(frozenset({_a(u), _a(v)}) for u, v in pairs)


EMPTY_BIDIR: frozenset[frozenset[Atom]] = frozenset()


# ========================================================== c_components

def test_c_components_empty_bidir_yields_singletons():
    g = _dg([("x", "y"), ("y", "z")])
    comps = c_components(g, EMPTY_BIDIR)
    assert {frozenset(c) for c in comps} == {
        frozenset({_a("x")}),
        frozenset({_a("y")}),
        frozenset({_a("z")}),
    }


def test_c_components_single_bidirected_pair():
    g = _dg([], extra_nodes=["x", "y", "z"])
    comps = c_components(g, _bidir([("x", "y")]))
    assert {frozenset(c) for c in comps} == {
        frozenset({_a("x"), _a("y")}),
        frozenset({_a("z")}),
    }


def test_c_components_transitive_merging():
    """x ↔ y ↔ z must collapse into one component via union-find."""
    g = _dg([], extra_nodes=["x", "y", "z"])
    comps = c_components(g, _bidir([("x", "y"), ("y", "z")]))
    assert {frozenset(c) for c in comps} == {
        frozenset({_a("x"), _a("y"), _a("z")}),
    }


def test_c_components_includes_bidirected_endpoint_outside_digraph():
    """A bidirected endpoint that never shows up in a directed edge must
    still appear in the partition so no node is silently dropped."""
    g = _dg([("x", "y")])  # no 'u' node in directed graph
    comps = c_components(g, _bidir([("x", "u")]))
    all_nodes = set().union(*(set(c) for c in comps))
    assert _a("u") in all_nodes


def test_c_components_covers_every_node_exactly_once():
    g = _dg([("x", "y"), ("z", "w")])
    bidir = _bidir([("x", "z")])
    comps = c_components(g, bidir)
    # disjoint + cover
    seen: set = set()
    for c in comps:
        assert not (c & seen)
        seen |= c
    assert seen == {_a("x"), _a("y"), _a("z"), _a("w")}


# =============================== is_m_connected: empty-bidirected regression

@pytest.mark.parametrize("graph_edges,left,right,given", [
    ([("x", "y"), ("y", "z")], "x", "z", ()),
    ([("x", "y"), ("y", "z")], "x", "z", ("y",)),
    ([("x", "z"), ("y", "z")], "x", "y", ()),          # collider Z
    ([("x", "z"), ("y", "z")], "x", "y", ("z",)),       # collider conditioned
    ([("z", "x"), ("z", "y")], "x", "y", ()),          # fork at Z
    ([("z", "x"), ("z", "y")], "x", "y", ("z",)),       # fork conditioned
])
def test_m_connected_matches_d_connected_when_no_bidirected(
    graph_edges, left, right, given,
):
    g = _dg(graph_edges)
    L, R = _a(left), _a(right)
    cond = tuple(_a(n) for n in given)
    assert is_m_connected(g, EMPTY_BIDIR, L, R, cond) == is_d_connected(g, L, R, cond)


# ============================================== is_m_connected: bidirected

def test_bidirected_edge_alone_connects_endpoints():
    g = _dg([], extra_nodes=["x", "y"])
    bidir = _bidir([("x", "y")])
    # A bidirected edge has no intermediate node; the path is trivially
    # open regardless of conditioning.
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is True
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("x"),)) is True


def test_bidirected_endpoints_act_as_collider_mid_path():
    """x → z ↔ y: at z both edges have arrowheads — collider.
    Under empty conditioning the collider is blocked, so the only
    path is closed and m-separated holds."""
    g = _dg([("x", "z")])
    bidir = _bidir([("z", "y")])
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is False
    # conditioning on z opens the collider
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("z"),)) is True


def test_bidirected_path_with_collider_descendant_activates():
    """x ↔ z → w, y → z: path x-z-y has collider z. Conditioning on
    w (descendant of z via directed edge) activates the collider."""
    g = _dg([("z", "w"), ("y", "z")])
    bidir = _bidir([("x", "z")])
    # no conditioning: collider blocked
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is False
    # condition on descendant of z
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("w"),)) is True


def test_double_bidirected_chain_with_shared_endpoint():
    """x ↔ z ↔ y: z is a collider on this path (arrowhead from both
    bidirected edges). Empty conditioning blocks; conditioning on z opens."""
    g = _dg([], extra_nodes=["x", "y", "z"])
    bidir = _bidir([("x", "z"), ("z", "y")])
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is False
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("z"),)) is True


def test_hidden_u_on_top_of_mediator_chain():
    """Classic front-door-with-hidden-U setup:
        x → m → y  and  x ↔ y
    Conditioning on m does NOT m-separate x from y because the
    bidirected edge still provides an open path."""
    g = _dg([("x", "m"), ("m", "y")])
    bidir = _bidir([("x", "y")])
    # directed x → m → y is open; bidirected also open
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is True
    # m blocks the directed path, but bidirected x↔y is still trivially open
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("m"),)) is True


def test_bidirected_does_not_create_descendants_for_collider_activation():
    """Descendants for collider activation are via *directed* edges only.
    x → z ← y, and w ↔ z (no directed edge to w from z).
    Conditioning on w must NOT activate the collider at z because w is
    not a directed-descendant of z."""
    g = _dg([("x", "z"), ("y", "z")])
    bidir = _bidir([("w", "z")])
    # collider z is blocked under empty conditioning
    assert is_m_connected(g, bidir, _a("x"), _a("y"), ()) is False
    # w is bidirected-linked to z but not a directed descendant — must
    # not activate the collider.
    assert is_m_connected(g, bidir, _a("x"), _a("y"), (_a("w"),)) is False


# =================================================== m_separated contract

def test_m_separated_is_negation_of_is_m_connected():
    g = _dg([("x", "y")])
    bidir = _bidir([])
    for cond in [(), (_a("y"),)]:
        assert m_separated(g, bidir, _a("x"), _a("y"), cond) == (
            not is_m_connected(g, bidir, _a("x"), _a("y"), cond)
        )


def test_m_separated_same_node_returns_true():
    g = _dg([("x", "y")])
    assert m_separated(g, EMPTY_BIDIR, _a("x"), _a("x"), ()) is True


def test_m_separated_missing_node_is_separated():
    g = _dg([("x", "y")])
    # ghost node outside the graph: no path possible → separated
    assert m_separated(g, EMPTY_BIDIR, _a("x"), _a("ghost"), ()) is True


# ============================================ symmetry and determinism

def test_is_m_connected_is_symmetric_in_left_right():
    g = _dg([("x", "z"), ("y", "z")])
    bidir = _bidir([("x", "y")])
    for cond in [(), (_a("z"),)]:
        assert (
            is_m_connected(g, bidir, _a("x"), _a("y"), cond)
            == is_m_connected(g, bidir, _a("y"), _a("x"), cond)
        )


def test_c_components_deterministic_on_repeat():
    g = _dg([("x", "y"), ("z", "w")])
    bidir = _bidir([("x", "w")])
    comps1 = {frozenset(c) for c in c_components(g, bidir)}
    comps2 = {frozenset(c) for c in c_components(g, bidir)}
    assert comps1 == comps2


# ============================= regression: existing d-sep cases unchanged

def test_existing_d_connected_cases_via_m_connected_on_more_graphs():
    """Stress the empty-bidirected regression on a richer graph:
    Every (left, right, conditioning) combination must agree with
    is_d_connected."""
    g = _dg([
        ("a", "b"), ("b", "c"), ("c", "d"),
        ("a", "e"), ("e", "d"),
        ("f", "c"),  # extra parent of c to make colliders non-trivial
    ])
    nodes = [_a(n) for n in ("a", "b", "c", "d", "e", "f")]
    pairs = [(l, r) for l in nodes for r in nodes if l != r]
    for l, r in pairs:
        for size in range(3):
            others = [n for n in nodes if n not in (l, r)]
            for combo in combinations(others, size):
                cond = tuple(combo)
                assert (
                    is_m_connected(g, EMPTY_BIDIR, l, r, cond)
                    == is_d_connected(g, l, r, cond)
                ), (l, r, cond)
