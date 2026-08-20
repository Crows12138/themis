"""Which identification route is weaker than which is a count, not a memory.

The mediation section of ``structural_solver`` carried six prose claims of
one shape: the set of graphs route A identifies contains, or is contained
in, the set route B identifies. Every one of them is decidable by
enumeration — run both routes over every small graph and compare — and not
one of them was ever run. Two had drifted. One said the CDE membership
condition C2 was "strictly weaker" than the natural-effects M4 while the
code refused a superset; the parenthetical explaining it ("CDE tolerates
X-descendants that are not M-descendants") described a candidate that both
routes reject. Another said an intermediate confounder leaves the
controlled effect identifiable, while the module's own unit test asserted —
correctly — that it sinks both.

The drift has a cause worth naming. These are claims about a lattice, and a
lattice is a thing you compute; left in prose they were written from
textbook memory, and the textbook does not know about this module's
mediator precondition. That precondition — a directed X → … → M path must
exist — makes every descendant of M a descendant of X, so the two
membership conditions coincide here and the distinction the comment was
reaching for cannot arise.

So this module computes the lattice. It enumerates every labelled DAG on
four nodes, with every subset of bidirected edges, keeps those where the
mediator mediates, and asks both routes. What it pins:

- the containment, in both directions, single-mediator and joint;
- that the two routes forbid the same nodes, and that this is a
  CONSEQUENCE of the precondition rather than a coincidence — so a
  future relaxation shows up here rather than silently changing what the
  controlled effect accepts;
- that every condition the contract declares can actually be reported.

The last one is the gate the old code would have failed. Reporting the
failure of the smallest candidate meant reporting the failure of the empty
set, and the empty set contains no descendant of anything, so "M4" and "C2"
could never be said — two of the six conditions were unreachable while both
had a Chinese sentence in the glossary waiting for a reader, and the
sentence for M4 describes precisely the intermediate-confounder case the
reader most needs it for.
"""
from __future__ import annotations

import functools
import itertools

import networkx as nx

from themis.runtime import structural_solver as ss

X, M, Y, A = "X", "M", "Y", "A"
NODES = (X, M, Y, A)
PAIRS = tuple(frozenset(p) for p in itertools.combinations(NODES, 2))

#: Two mediators, for the joint twin of the same questions.
M1, M2 = "M1", "M2"
JOINT_NODES = (X, Y, M1, M2)
JOINT_PAIRS = tuple(frozenset(p) for p in itertools.combinations(JOINT_NODES, 2))


def _all_dags(nodes: tuple[str, ...]):
    """Every labelled DAG on ``nodes``, deduped by edge set.

    Enumerating permutations and taking the forward pairs of each reaches
    every acyclic edge set, since a DAG is exactly the graphs consistent
    with some topological order.
    """
    seen: set[frozenset] = set()
    n = len(nodes)
    for order in itertools.permutations(nodes):
        forward = [(order[i], order[j])
                   for i in range(n) for j in range(i + 1, n)]
        for r in range(len(forward) + 1):
            for combo in itertools.combinations(forward, r):
                key = frozenset(combo)
                if key in seen:
                    continue
                seen.add(key)
                g = nx.DiGraph()
                g.add_nodes_from(nodes)
                g.add_edges_from(combo)
                yield g


def _subsets(pairs: tuple[frozenset, ...], max_size: int):
    for r in range(max_size + 1):
        for combo in itertools.combinations(pairs, r):
            yield frozenset(combo)


@functools.lru_cache(maxsize=1)
def _census() -> dict:
    """One pass over the single-mediator enumeration.

    Returns the four-cell table, the labels each route actually emits, and
    how often the two routes' forbidden sets come apart.
    """
    cells: dict[tuple[bool, bool], int] = {}
    nde_labels: dict[str | None, int] = {}
    cde_labels: dict[str | None, int] = {}
    forbidden_differs = 0
    graphs = 0
    witnesses: dict[tuple[bool, bool], tuple] = {}

    for g in _all_dags(NODES):
        if not (nx.has_path(g, X, M) and nx.has_path(g, M, Y)):
            continue
        graphs += 1
        ms = frozenset({M})
        if ss._forbidden_for_nde(g, X, ms) != ss._forbidden_for_cde(g, X, ms):
            forbidden_differs += 1

        for bidir in _subsets(PAIRS, len(PAIRS)):
            res = ss.mediation_sets(g, X, Y, M, bidirected=bidir)
            assert res.mediator_valid
            cell = (res.nde_nie.identifiable, res.cde.identifiable)
            cells[cell] = cells.get(cell, 0) + 1
            witnesses.setdefault(cell, (tuple(sorted(g.edges)), bidir))
            nde_labels[res.nde_nie.failed_condition] = (
                nde_labels.get(res.nde_nie.failed_condition, 0) + 1)
            cde_labels[res.cde.failed_condition] = (
                cde_labels.get(res.cde.failed_condition, 0) + 1)

    return {
        "cells": cells,
        "nde_labels": nde_labels,
        "cde_labels": cde_labels,
        "forbidden_differs": forbidden_differs,
        "graphs": graphs,
        "witnesses": witnesses,
    }


@functools.lru_cache(maxsize=1)
def _joint_census() -> dict:
    cells: dict[tuple[bool, bool], int] = {}
    ms = frozenset({M1, M2})
    for g in _all_dags(JOINT_NODES):
        if not all(nx.has_path(g, X, m) and nx.has_path(g, m, Y) for m in ms):
            continue
        for bidir in _subsets(JOINT_PAIRS, 2):
            res = ss.mediation_sets_joint(g, X, Y, ms, bidirected=bidir)
            assert res.mediator_set_valid
            cell = (res.nde_nie.identifiable, res.cde.identifiable)
            cells[cell] = cells.get(cell, 0) + 1
    return {"cells": cells}


# ===================================================== the containment


def test_no_graph_identifies_the_natural_effects_without_the_controlled_one():
    """The cell that would break the ordering is empty.

    Argued as well as counted: with the same W, M1 gives C1's X arm
    because G\\bar{XM} has a subset of G\\bar{X}'s edges, and M3 gives
    C1's M arm because X has no outgoing edge in G\\bar{XM} and so cannot
    be a non-collider on any M–Y path there — dropping it from the
    conditioning set can only close paths. Both routes draw from one pool
    and forbid the same nodes, so the W that satisfied the four conditions
    is available to the two.
    """
    census = _census()
    assert census["cells"].get((True, False), 0) == 0, (
        "a graph identifies the natural effects but not the controlled "
        f"effect: {census['witnesses'].get((True, False))}"
    )


def test_the_controlled_effect_is_identified_in_strictly_more_graphs():
    """And the containment is strict, so "weaker" is a claim with content."""
    census = _census()
    assert census["cells"].get((False, True), 0) > 0
    assert census["cells"].get((True, True), 0) > 0


def test_the_joint_routes_stand_in_the_same_order():
    """The mediator-SET twin of both, on {X, Y, M1, M2}."""
    cells = _joint_census()["cells"]
    assert cells.get((True, False), 0) == 0
    assert cells.get((False, True), 0) > 0


# ============================================ what the two routes forbid


def test_the_two_routes_forbid_the_same_nodes_because_of_the_precondition():
    """C2 admits no candidate M4 refuses, and vice versa.

    Not because the controlled effect is indifferent to a mediator's
    descendants — it is not, and ``_forbidden_for_cde`` names them — but
    because the mediator precondition puts every descendant of M inside
    the descendants of X. The comparison is between the forbidden SETS,
    not between the labels the two checkers return: a membership
    condition is tested after the separations it shares a function with,
    so which of the two a given W is refused by depends on those, and
    only the sets are the routes' own statement of what they will not
    take. Pinned as a consequence: if the precondition is ever relaxed
    the sets come apart here, which is the moment to decide what the
    controlled route should then accept.
    """
    census = _census()
    assert census["graphs"] > 0
    assert census["forbidden_differs"] == 0


def test_a_mediator_descendant_outside_x_is_what_the_precondition_forbids():
    """The counterexample to the equality is a graph the precondition bars.

    Without ``X → … → M`` the union in ``_forbidden_for_cde`` does real
    work — which is why it is written out rather than simplified to the
    M4 set.
    """
    g = nx.DiGraph()
    g.add_edges_from([(M, "D"), (X, Y), (M, Y)])  # M does not descend from X
    ms = frozenset({M})
    assert "D" not in ss._forbidden_for_nde(g, X, ms)
    assert "D" in ss._forbidden_for_cde(g, X, ms)
    # and the precondition refuses the graph, which is why no answer ever
    # depends on the difference.
    assert not ss.mediation_sets(g, X, Y, M).mediator_valid


# ==================================== every declared condition is reachable


def test_every_condition_the_contract_declares_can_be_reported():
    """A label nothing can emit is a sentence no reader will ever see.

    Both vocabularies reach a reader — the schema enumerates them, the
    glossary gives each a sentence, and the browser prints it. Before the
    search learned to report the candidate that got furthest, "M4" and
    "C2" were unreachable: the reported label was the failure of the
    smallest candidate, and the empty set violates no membership
    condition.

    Asked of the single-mediator route only, because reachability is a
    property of the shared searcher rather than of either checker, and
    the joint routes go through the same one with the same orders.
    """
    census = _census()
    for label in ss._NDE_NIE_ORDER:
        assert census["nde_labels"].get(label, 0) > 0, (
            f"no graph in the enumeration reports {label}")
    for label in ss._CDE_ORDER:
        assert census["cde_labels"].get(label, 0) > 0, (
            f"no graph in the enumeration reports {label}")


def test_the_intermediate_confounder_names_the_restriction():
    """The case the M4 sentence was written for.

    X → L → M, L → Y: L is the only thing that would block the M–Y
    backdoor and both routes refuse it for descending from X. Telling the
    reader "there is still an open backdoor" is true and useless; telling
    them "the set you need is a descendant of the treatment" is what they
    can argue with.
    """
    g = nx.DiGraph()
    g.add_edges_from([(X, "L"), ("L", M), ("L", Y), (X, M), (M, Y)])

    result = ss.mediation_sets(g, X, Y, M)
    assert result.mediator_valid
    assert not result.nde_nie.identifiable
    assert result.nde_nie.failed_condition == "M4"
    assert not result.cde.identifiable
    assert result.cde.failed_condition == "C2"


def test_an_obstruction_no_candidate_can_reach_past_is_still_named():
    """And the furthest-candidate rule does not turn every failure into a
    membership complaint: with a latent X ↔ Y no adjustment set blocks the
    X–Y backdoor at all, so the label stays at the separation that fails.
    """
    g = nx.DiGraph()
    g.add_edges_from([(X, M), (M, Y)])
    bidir = frozenset({frozenset({X, Y})})

    result = ss.mediation_sets(g, X, Y, M, bidirected=bidir)
    assert result.nde_nie.failed_condition == "M1"
    assert result.cde.failed_condition == "C1"
