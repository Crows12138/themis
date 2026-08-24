"""Phase 5 §C / S.C.2: twin-network projection primitive."""
from __future__ import annotations

import networkx as nx

from themis.runtime.counterfactual import (
    COUNTERFACTUAL_WORLD,
    FACTUAL_WORLD,
    TwinAtom,
    project_twin_network,
)
from themis.ledger import Monotonicity
from themis.types import (
    Atom,
    ConstTerm,
    CounterfactualAssumptions,
    CounterfactualQuery,
    Intervention,
    RelativeTimeIndex,
    ValuedAtom,
)


def _atom(pred: str, *, t: int | None = None) -> Atom:
    return Atom(
        predicate=pred,
        args=(ConstTerm(name="me"),),
        time_index=(
            None if t is None else RelativeTimeIndex(value=t)
        ),
    )


def _query(x: Atom, y: Atom) -> CounterfactualQuery:
    return CounterfactualQuery(
        observed=ValuedAtom(atom=x, value=False),
        counterfactual_intervention=Intervention(atom=x, value=True),
        counterfactual_target=ValuedAtom(atom=y, value=True),
        assumptions=CounterfactualAssumptions(
            monotonicity=Monotonicity.NON_DECREASING
        ),
    )


def test_twin_network_duplicates_each_base_node_into_two_worlds():
    x = _atom("x")
    y = _atom("y")
    g = nx.DiGraph()
    g.add_edge(x, y)

    twin = project_twin_network(g, frozenset(), _query(x, y))

    assert TwinAtom(atom=x, world=FACTUAL_WORLD) in twin.graph
    assert TwinAtom(atom=x, world=COUNTERFACTUAL_WORLD) in twin.graph
    assert TwinAtom(atom=y, world=FACTUAL_WORLD) in twin.graph
    assert TwinAtom(atom=y, world=COUNTERFACTUAL_WORLD) in twin.graph
    assert twin.graph.number_of_nodes() == 4


def test_twin_network_copies_directed_edges_into_both_worlds_except_do_cut():
    x = _atom("x")
    z = _atom("z")
    y = _atom("y")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])

    twin = project_twin_network(g, frozenset(), _query(x, y))

    assert twin.graph.has_edge(
        TwinAtom(atom=z, world=FACTUAL_WORLD),
        TwinAtom(atom=x, world=FACTUAL_WORLD),
    )
    assert not twin.graph.has_edge(
        TwinAtom(atom=z, world=COUNTERFACTUAL_WORLD),
        TwinAtom(atom=x, world=COUNTERFACTUAL_WORLD),
    )
    assert twin.graph.has_edge(
        TwinAtom(atom=x, world=COUNTERFACTUAL_WORLD),
        TwinAtom(atom=y, world=COUNTERFACTUAL_WORLD),
    )


def test_twin_network_adds_same_variable_cross_world_bidirected_coupling():
    x = _atom("x")
    y = _atom("y")
    g = nx.DiGraph()
    g.add_edge(x, y)

    twin = project_twin_network(g, frozenset(), _query(x, y))

    assert frozenset(
        {
            TwinAtom(atom=x, world=FACTUAL_WORLD),
            TwinAtom(atom=x, world=COUNTERFACTUAL_WORLD),
        }
    ) in twin.bidirected
    assert frozenset(
        {
            TwinAtom(atom=y, world=FACTUAL_WORLD),
            TwinAtom(atom=y, world=COUNTERFACTUAL_WORLD),
        }
    ) in twin.bidirected


def test_original_bidirected_pair_expands_across_worlds():
    x = _atom("x")
    y = _atom("y")
    g = nx.DiGraph()
    g.add_nodes_from([x, y])
    bidirected = frozenset({frozenset({x, y})})

    twin = project_twin_network(g, bidirected, _query(x, y))

    assert frozenset(
        {
            TwinAtom(atom=x, world=FACTUAL_WORLD),
            TwinAtom(atom=y, world=FACTUAL_WORLD),
        }
    ) in twin.bidirected
    assert frozenset(
        {
            TwinAtom(atom=x, world=FACTUAL_WORLD),
            TwinAtom(atom=y, world=COUNTERFACTUAL_WORLD),
        }
    ) in twin.bidirected
    assert frozenset(
        {
            TwinAtom(atom=x, world=COUNTERFACTUAL_WORLD),
            TwinAtom(atom=y, world=COUNTERFACTUAL_WORLD),
        }
    ) in twin.bidirected


def test_twin_network_preserves_time_index_on_world_copies():
    x_prev = _atom("x", t=-1)
    y_now = _atom("y", t=0)
    g = nx.DiGraph()
    g.add_edge(x_prev, y_now)

    twin = project_twin_network(g, frozenset(), _query(x_prev, y_now))

    assert TwinAtom(atom=x_prev, world=FACTUAL_WORLD) in twin.graph
    assert TwinAtom(atom=y_now, world=COUNTERFACTUAL_WORLD) in twin.graph
    assert twin.observed.atom.time_index == x_prev.time_index
    assert twin.counterfactual_target.atom.time_index == y_now.time_index

