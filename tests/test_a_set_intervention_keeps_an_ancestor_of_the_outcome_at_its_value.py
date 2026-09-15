"""A set intervention keeps an ancestor of the outcome at its value.

The ID engine's compact Line-7 shortcut answers ID(y, x∩S', Q[S'], G[S']) by
summing every intervention inside S'. That is the recursion's answer only when
none of them is still an ancestor of the outcome inside G[S']. Measured while
the semantic probe learned to ask about a corner of a treatment box (#660), on
300 random six-node graphs with two treatments: the joint engine's estimand
was refused on four identified corners, all of one graph. There do(f, b) on a,
with b→a, f↔a and f↔b, keeps b a parent of a inside S' = {f, b, a}; the
shortcut summed b anyway, and the estimand computed 0.4026 where the model's
interventional value was 0.4812. The formula was well-formed, so the retry with
the full nested Identify never ran, and the joint path had that retry switched
off because its numeric self-check could ask about one variable only.

The shortcut now declines there, and both paths retry with the full Identify,
self-checked under the whole assignment.
"""
from __future__ import annotations

import itertools
import random

import networkx as nx

from themis.runtime import c_factor
from themis.types import Atom, ConstTerm, ValuedAtom
from themis.verifier import semantic_probe as sp


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def test_every_corner_of_the_measured_box_is_identified_and_computes_its_risk():
    f, b, c, d, e, a = (_A(p) for p in "fbcdea")
    graph = nx.DiGraph([(f, c), (f, d), (f, e), (b, a), (b, c), (b, e), (c, a), (a, d)])
    bidirected = frozenset({frozenset({f, a}), frozenset({f, b}), frozenset({c, d})})
    for mask in itertools.product((True, False), repeat=2):
        corner = {f: mask[0], b: mask[1]}
        derived = c_factor.identify_via_tian_joint(graph, bidirected, corner, a)
        assert derived.identifiable, corner
        verdict = sp.probe_intervention_formula(
            graph, bidirected, intervention=corner,
            outcome=(ValuedAtom(atom=a, value=None),), given=(), formula=derived.formula)
        assert verdict.status == "match", (corner, verdict)


def _random_admg(rng, nodes, p_edge, p_arc):
    order = rng.sample(nodes, len(nodes))
    graph = nx.DiGraph()
    graph.add_nodes_from(order)
    graph.add_edges_from((u, v) for i, u in enumerate(order)
                         for v in order[i + 1:] if rng.random() < p_edge)
    bidirected = frozenset(frozenset((u, v)) for i, u in enumerate(order)
                           for v in order[i + 1:] if rng.random() < p_arc)
    return order, graph, bidirected


def test_no_corner_estimand_the_engine_emits_is_refused_on_random_graphs():
    """The graphs the four refusals were found on, asked again: wherever the
    engine identifies a corner of a two-treatment box, the probe matches."""
    rng = random.Random(660)
    nodes = [_A(p) for p in "abcdef"]
    seen = {}
    for _ in range(300):
        order, graph, bidirected = _random_admg(rng, nodes, 0.4, 0.15)
        first, second, last = sorted(rng.sample(range(len(order)), 3))
        treatments, y = (order[first], order[second]), order[last]
        for mask in itertools.product((True, False), repeat=2):
            corner = dict(zip(treatments, mask))
            derived = c_factor.identify_via_tian_joint(graph, bidirected, corner, y)
            if not derived.identifiable or derived.formula is None:
                seen["unidentified"] = seen.get("unidentified", 0) + 1
                continue
            verdict = sp.probe_intervention_formula(
                graph, bidirected, intervention=corner,
                outcome=(ValuedAtom(atom=y, value=None),), given=(),
                formula=derived.formula)
            assert not verdict.refuses, (sorted(graph.edges), bidirected, corner, y, verdict)
            seen[verdict.status] = seen.get(verdict.status, 0) + 1
    assert seen.get("match", 0) > 900 and seen.get("unidentified", 0) > 150, seen


def test_no_single_estimand_the_engine_emits_is_refused_on_random_graphs():
    """The same question of one intervention, on graphs one node larger."""
    rng = random.Random(661)
    nodes = [_A(p) for p in "abcdefg"]
    seen = {}
    for _ in range(500):
        order, graph, bidirected = _random_admg(rng, nodes, 0.4, 0.2)
        i, j = sorted(rng.sample(range(len(order)), 2))
        x, y = order[i], order[j]
        derived = c_factor.identify_via_tian(graph, bidirected, x, y, True)
        if not derived.identifiable or derived.formula is None:
            seen["unidentified"] = seen.get("unidentified", 0) + 1
            continue
        verdict = sp.probe_intervention_formula(
            graph, bidirected, intervention={x: True},
            outcome=(ValuedAtom(atom=y, value=None),), given=(),
            formula=derived.formula)
        assert not verdict.refuses, (sorted(graph.edges), bidirected, x, y, verdict)
        seen[verdict.status] = seen.get(verdict.status, 0) + 1
    assert seen.get("match", 0) > 350 and seen.get("unidentified", 0) > 50, seen
