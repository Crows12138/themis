"""make-cg (Shpitser-Pearl 2007 Fig 10, Lemmas 24-25) — counterfactual graph.

The load-bearing oracle is the worked example from Tikka's cfid R Journal
paper (arXiv:2210.14745, an independent reimplementation of the 2007
algorithm): γ = y_x ∧ x' ∧ z_d ∧ d on the graph X→W→Y ← Z ← D with X↔Y.
Its counterfactual graph has maximal c-components {X, Y_x}, {Z}, {W_x}, {D}
(cfid eq. 1). We assert the merge PARTITION and those c-components — the
invariants that do not depend on which representative atom a merged group
elects (the merge itself is non-deterministic, R-336 p.19).
"""
from __future__ import annotations

import networkx as nx

from themis.types import Atom
from themis.runtime.ctf_identify import (
    INCONSISTENT,
    CtfEvent,
    make_cg,
    sub,
    var,
    ev,
)


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, W, Y, Z, D = A("x"), A("w"), A("y"), A("z"), A("d")


def _fig1_graph():
    """cfid Fig 1(a): X→W→Y, Z→Y, D→Z, and X↔Y."""
    g = nx.DiGraph()
    g.add_edges_from([(X, W), (W, Y), (Z, Y), (D, Z)])
    bi = frozenset({frozenset({X, Y})})
    return g, bi


def _fig1_gamma():
    """γ = y_x ∧ x' ∧ z_d ∧ d (distinct values so x vs x' never alias)."""
    return (
        CtfEvent(Y, frozenset({(X, "xi")}), "yv"),   # y_x
        CtfEvent(X, frozenset(), "xp"),              # x'
        CtfEvent(Z, frozenset({(D, "dv")}), "zv"),   # z_d
        CtfEvent(D, frozenset(), "dv"),              # d
    )


# ============================================================ operators
def test_operators():
    g = _fig1_gamma()
    assert sub(g) == frozenset({X, D})
    assert var(g) == frozenset({X, Y, Z, D})
    assert ev(g) == frozenset({"yv", "xp", "zv", "dv", "xi"})


# ============================================================ the worked graph
def test_fig1_counterfactual_graph_c_components():
    g, bi = _fig1_graph()
    cf = make_cg(g, bi, _fig1_gamma())
    assert cf is not INCONSISTENT

    # V(G') — the observable (non-fixed) nodes: X, D, Z, W_x, Y_x. (The
    # intervention-fixed X node in world x is present for ancestry but is
    # not observable.)
    obs = cf.observable()
    assert len(obs) == 5

    parts = cf.c_component_partition()
    sizes = sorted(len(p) for p in parts)
    assert sizes == [1, 1, 1, 2]  # {X,Y_x} and three singletons — cfid eq.(1)

    # The size-2 component is exactly the confounded {X, Y_x} pair.
    big = next(p for p in parts if len(p) == 2)
    assert {n.variable for n in big} == {X, Y}

    # The three singletons are one W, one Z, one D.
    singles = {next(iter(p)).variable for p in parts if len(p) == 1}
    assert singles == {W, Z, D}


def test_fig1_gamma_prime_values_survive():
    g, bi = _fig1_graph()
    cf = make_cg(g, bi, _fig1_gamma())
    # γ' remaps the four events onto representatives; the observed values
    # are preserved and land on four distinct nodes.
    gp = dict(cf.gamma_prime)
    assert len(gp) == 4
    assert sorted(gp.values()) == ["dv", "xp", "yv", "zv"]
    # Each γ' node carries that value in the graph's value map.
    for node, value in cf.gamma_prime:
        assert cf.value[node] == value


def test_fig1_zx_merges_all_three_z_via_composition():
    # The Z triple (Z, Z_x, Z_d) collapses to ONE node — this is the
    # composition-axiom merge that only fires because d is observed to equal
    # the value fixed in z_d's world. So exactly one Z node survives.
    g, bi = _fig1_graph()
    cf = make_cg(g, bi, _fig1_gamma())
    z_nodes = [n for n in cf.graph.nodes() if n.variable == Z]
    assert len(z_nodes) == 1


def test_fig1_wx_does_not_merge_with_factual_w():
    # W_x cannot merge with the factual W (its parent X is fixed to xi, but
    # the factual X is observed x' ≠ xi). W_x survives as its own singleton
    # c-component and feeds Y_x; the factual W is a non-ancestor of γ' and is
    # pruned. So exactly one W node survives, and it is a parent of a Y node.
    g, bi = _fig1_graph()
    cf = make_cg(g, bi, _fig1_gamma())
    w_nodes = [n for n in cf.graph.nodes() if n.variable == W]
    assert len(w_nodes) == 1
    (wx,) = w_nodes
    children = set(cf.graph.successors(wx))
    assert any(c.variable == Y for c in children)


# ============================================================ inconsistency
def test_effectiveness_violation_is_inconsistent():
    # An event observes X = 'b' in a world that fixes X = 'a' (x_{x'}): the
    # node is fixed to 'a' but asserted 'b'. P(γ) = 0.
    g = nx.DiGraph()
    g.add_edges_from([(X, Y)])
    gamma = (CtfEvent(X, frozenset({(X, "a")}), "b"),)
    assert make_cg(g, bi_empty(), gamma) is INCONSISTENT


def test_merge_value_clash_is_inconsistent():
    # Y is a parentless source. Y_x (world intervening on X) and the factual
    # Y merge (no parents to disagree on), but γ asserts different values on
    # them → contradiction → P(γ) = 0.
    g = nx.DiGraph()
    g.add_edges_from([(X, Z)])  # Y is a separate source
    g.add_node(Y)
    gamma = (
        CtfEvent(Y, frozenset({(X, "xi")}), "a"),  # Y_x = a
        CtfEvent(Y, frozenset(), "b"),             # Y   = b
    )
    assert make_cg(g, bi_empty(), gamma) is INCONSISTENT


def test_consistent_merge_survives():
    # Same shape but with EQUAL asserted values → the merge succeeds and the
    # two Y events collapse to one node (no contradiction).
    g = nx.DiGraph()
    g.add_edges_from([(X, Z)])
    g.add_node(Y)
    gamma = (
        CtfEvent(Y, frozenset({(X, "xi")}), "a"),
        CtfEvent(Y, frozenset(), "a"),
    )
    cf = make_cg(g, bi_empty(), gamma)
    assert cf is not INCONSISTENT
    y_nodes = [n for n in cf.graph.nodes() if n.variable == Y]
    assert len(y_nodes) == 1


def bi_empty():
    return frozenset()
