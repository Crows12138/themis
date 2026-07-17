"""Phase 1 — Meek orientation propagation + constraint-consistency, and the
independent verifier. Parity-checked against causal-learn's reference Meek.
"""
import numpy as np
import pytest

from themis.estimation.orientation import (
    OrientationError,
    orientation_to_dict,
    propagate_orientations,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_rules import verify_orientation_propagation


# --- the three Meek rules in isolation ----------------------------------------

def test_r1_avoids_new_collider():
    # A->B, B-C, A not adjacent C  =>  B->C
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "B")], undirected=[("B", "C")],
    )
    assert ("B", "C") in r.oriented
    assert not r.remaining_undirected
    p = {(e["from"], e["to"]): e["rule"] for e in r.provenance}
    assert p[("B", "C")] == "R1"
    verify_orientation_propagation(orientation_to_dict(r))


def test_r2_acyclicity():
    # A->B, B->C, A-C  =>  A->C
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "B"), ("B", "C")], undirected=[("A", "C")],
    )
    assert ("A", "C") in r.oriented
    p = {(e["from"], e["to"]): e["rule"] for e in r.provenance}
    assert p[("A", "C")] == "R2"
    verify_orientation_propagation(orientation_to_dict(r))


def test_r3_kite():
    # I-J, I-K, J->L, K->L, I-L, with J,K non-adjacent  =>  I->L
    r = propagate_orientations(
        ["I", "J", "K", "L"],
        directed=[("J", "L"), ("K", "L")],
        undirected=[("I", "J"), ("I", "K"), ("I", "L")],
    )
    assert ("I", "L") in r.oriented
    p = {(e["from"], e["to"]): e["rule"] for e in r.provenance}
    assert p[("I", "L")] == "R3"
    verify_orientation_propagation(orientation_to_dict(r))


# --- constraints + provenance chains ------------------------------------------

def test_constraint_orients_and_propagates_with_root_chain():
    # skeleton A-B-C (chain), no colliders. Answer A->B; Meek then forces B->C.
    r = propagate_orientations(
        ["A", "B", "C"], undirected=[("A", "B"), ("B", "C")],
        constraints=[("A", "B")],
    )
    assert ("A", "B") in r.oriented and ("B", "C") in r.oriented
    prov = {(e["from"], e["to"]): e for e in r.provenance}
    assert prov[("A", "B")]["rule"] == "constraint"
    assert prov[("B", "C")]["rule"] == "R1"
    # the propagated edge B->C rests on the A->B answer (blast-radius chain)
    assert prov[("B", "C")]["roots"] == [["A", "B"]]
    verify_orientation_propagation(orientation_to_dict(r))


# --- conflict detection (the counterexample that motivated the design) --------

def test_constraint_contradicting_data_collider_is_flagged_not_applied():
    # data-established collider A->C<-B ; answer C->A contradicts A->C
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        constraints=[("C", "A")],
    )
    # the data orientation is left intact...
    assert ("A", "C") in r.oriented
    assert ("C", "A") not in r.oriented
    # ...and the conflict is surfaced, not buried
    assert len(r.conflicts) == 1
    assert r.conflicts[0]["reason"] == "contradicts_data_orientation"
    assert r.conflicts[0]["constraint"] == ["C", "A"]
    verify_orientation_propagation(orientation_to_dict(r))


def test_constraint_on_non_edge_is_flagged():
    r = propagate_orientations(
        ["A", "B", "C"], undirected=[("A", "B")], constraints=[("A", "C")],
    )
    assert len(r.conflicts) == 1
    assert r.conflicts[0]["reason"] == "non_adjacent_pair"
    verify_orientation_propagation(orientation_to_dict(r))


def test_ill_formed_input_raises():
    with pytest.raises(OrientationError):
        propagate_orientations(["A", "B"], directed=[("A", "B")], undirected=[("A", "B")])
    with pytest.raises(OrientationError):
        propagate_orientations(["A", "B"], directed=[("A", "B"), ("B", "A")])


# --- verifier rejects tampering -----------------------------------------------

def test_verifier_rejects_fabricated_orientation():
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = orientation_to_dict(r)  # nothing forced -> both edges undetermined
    d["oriented"] = [["A", "B"]]            # fabricate an unforced orientation
    d["remaining_undirected"] = [["B", "C"]]
    d["provenance"] = [{"from": "A", "to": "B", "rule": "R1", "roots": []}]
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_silently_applied_data_contradiction():
    # a producer that BURIED the conflict: applied C->A, dropped A->C, empty conflicts
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")], constraints=[("C", "A")],
    )
    d = orientation_to_dict(r)
    d["oriented"] = [["B", "C"], ["C", "A"]]      # override the data collider
    d["conflicts"] = []                            # hide the conflict
    d["provenance"] = [
        {"from": "B", "to": "C", "rule": "collider_input", "roots": []},
        {"from": "C", "to": "A", "rule": "constraint", "roots": [["C", "A"]]},
    ]
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_dropped_conflict_entry():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")], constraints=[("C", "A")],
    )
    d = orientation_to_dict(r)
    d["conflicts"] = []  # drop the (correctly non-applied) conflict record
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


# --- parity against causal-learn's reference Meek engine ----------------------

def _random_dag(p, ep, rng):
    order = rng.permutation(p); A = np.zeros((p, p))
    for a in range(p):
        for b in range(a + 1, p):
            if rng.random() < ep:
                u, v = order[a], order[b]
                A[u, v] = rng.uniform(0.5, 1.5) * rng.choice([-1, 1])
    return A


def _simulate(A, n, rng):
    import networkx as nx
    p = A.shape[0]; G = nx.DiGraph(); G.add_nodes_from(range(p))
    for u in range(p):
        for v in range(p):
            if A[u, v] != 0: G.add_edge(u, v)
    X = np.zeros((n, p))
    for v in nx.topological_sort(G):
        X[:, v] = rng.standard_normal(n)
        for u in range(p):
            if A[u, v] != 0: X[:, v] += A[u, v] * X[:, u]
    return X


def test_parity_with_causal_learn_meek():
    causallearn = pytest.importorskip("causallearn")
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.utils.PCUtils import Meek
    from causallearn.utils.PCUtils.BackgroundKnowledge import BackgroundKnowledge
    from causallearn.graph.Endpoint import Endpoint
    from copy import deepcopy
    import warnings

    def edges_of(cg):
        d = set(); u = set()
        for e in cg.G.get_graph_edges():
            a = e.get_node1().get_name(); b = e.get_node2().get_name()
            e1, e2 = e.get_endpoint1(), e.get_endpoint2()
            if e1 == Endpoint.TAIL and e2 == Endpoint.ARROW: d.add((a, b))
            elif e1 == Endpoint.ARROW and e2 == Endpoint.TAIL: d.add((b, a))
            else: u.add(frozenset((a, b)))
        return d, u

    p = 7; names = [f"X{i}" for i in range(p)]
    matches = 0; trials = 0
    for seed in range(500, 540):
        rng = np.random.default_rng(seed)
        A = _random_dag(p, 0.35, rng); X = _simulate(A, 1500, rng)
        true_dir = {(names[i], names[j]) for i in range(p) for j in range(p) if A[i, j] != 0}
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cg0 = pc(X, 0.05, "fisherz", node_names=names, show_progress=False)
        d0, u0 = edges_of(cg0)
        cand = [fs for fs in u0 if (tuple(fs) in true_dir or tuple(fs)[::-1] in true_dir)]
        if not cand:
            continue
        a, b = tuple(sorted(cand, key=lambda x: tuple(sorted(x)))[0])
        if (b, a) in true_dir:
            a, b = b, a
        trials += 1

        # our implementation
        mine = propagate_orientations(
            names, directed=d0, undirected=[tuple(x) for x in u0], constraints=[(a, b)],
        )
        # causal-learn reference: orient a->b on a copy, close under its Meek
        cg = deepcopy(cg0)
        cn = {x.get_name(): x for x in cg.G.get_nodes()}
        e_ab = cg.G.get_edge(cn[a], cn[b])
        if e_ab is not None:
            cg.G.remove_edge(e_ab)
        cg.G.add_directed_edge(cn[a], cn[b])
        bk = BackgroundKnowledge(); bk.add_required_by_node(cn[a], cn[b])
        cg = Meek.meek(cg, bk)
        dref, _ = edges_of(cg)

        assert set(mine.oriented) == dref, (
            f"seed {seed}: ours {sorted(set(mine.oriented) - dref)} "
            f"vs causal-learn {sorted(dref - set(mine.oriented))}"
        )
        verify_orientation_propagation(orientation_to_dict(mine))
        matches += 1
    assert trials >= 20, f"too few usable parity trials ({trials})"
    assert matches == trials
