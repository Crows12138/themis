"""Phase 1 — Meek orientation propagation (R1-R4) + constraint-consistency, and
the independent verifier. The authoritative check is a brute-force
equivalence-class oracle; causal-learn's reference Meek (R1-R3 only) is a
secondary cross-check on the bare, no-constraint completion.
"""
import itertools

import numpy as np
import pytest

from themis.estimation.orientation import (
    OrientationError,
    orientation_to_dict,
    propagate_orientations,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_rules import verify_orientation_propagation


# --- the Meek rules in isolation ----------------------------------------------

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


def test_r4_completes_under_constraint():
    # Regression for the R1-R3 completeness gap under background knowledge.
    # Skeleton A-B, A-C, B-C, B-D, C-D, C-E, D-E ; no colliders. The single
    # answer A->B forces C->D by R4 (R1-R3 alone leave it undirected), which then
    # unlocks C->E (R2) and D->E (R1). Without R4 the whole chain is missed.
    r = propagate_orientations(
        ["A", "B", "C", "D", "E"],
        undirected=[("A", "B"), ("A", "C"), ("B", "C"), ("B", "D"),
                    ("C", "D"), ("C", "E"), ("D", "E")],
        constraints=[("A", "B")],
    )
    oriented = set(r.oriented)
    assert {("C", "D"), ("C", "E"), ("D", "E"), ("B", "D")} <= oriented
    prov = {(e["from"], e["to"]): e for e in r.provenance}
    assert prov[("C", "D")]["rule"] == "R4"          # the edge R1-R3 could not reach
    assert prov[("C", "D")]["roots"] == [["A", "B"]]  # rests on the one answer
    assert set(r.remaining_undirected) == {("A", "C"), ("B", "C")}
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


def test_constraint_closing_a_cycle_is_flagged_not_applied():
    # triangle A-B, B-C, A-C undirected; answers A->B, B->C, then C->A would close
    # the cycle A->B->C->A — the third is flagged creates_cycle, not applied, and
    # Meek's R2 then orients A->C (acyclicity) from the two that WERE applied.
    r = propagate_orientations(
        ["A", "B", "C"],
        undirected=[("A", "B"), ("B", "C"), ("A", "C")],
        constraints=[("A", "B"), ("B", "C"), ("C", "A")],
    )
    assert {("A", "B"), ("B", "C"), ("A", "C")} == set(r.oriented)
    assert ("C", "A") not in r.oriented
    assert len(r.conflicts) == 1
    assert r.conflicts[0]["reason"] == "creates_cycle"
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


def test_verifier_rejects_dropped_r4_orientation():
    # drop a genuinely-forced R4 edge (and its provenance): the verifier's
    # independent R1-R4 closure must still force it and flag the omission.
    r = propagate_orientations(
        ["A", "B", "C", "D", "E"],
        undirected=[("A", "B"), ("A", "C"), ("B", "C"), ("B", "D"),
                    ("C", "D"), ("C", "E"), ("D", "E")],
        constraints=[("A", "B")],
    )
    d = orientation_to_dict(r)
    d["oriented"] = [e for e in d["oriented"] if e != ["C", "D"]]
    d["provenance"] = [p for p in d["provenance"]
                       if [p["from"], p["to"]] != ["C", "D"]]
    d["remaining_undirected"] = d["remaining_undirected"] + [["C", "D"]]
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


# --- brute-force equivalence-class oracle (the authoritative check) -----------

def _unshielded_colliders(directed, skel, nodes):
    cols = set()
    for z in nodes:
        parents = [x for x in nodes if (x, z) in directed]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.add((frozenset((x, y)), z))
    return cols


def _is_acyclic(directed, nodes):
    ch = {}
    for (u, v) in directed:
        ch.setdefault(u, []).append(v)
    color = {}

    def dfs(u):
        color[u] = 0
        for w in ch.get(u, ()):
            c = color.get(w)
            if c == 0:
                return False
            if c is None and not dfs(w):
                return False
        color[u] = 1
        return True

    return all(color.get(u) is not None or dfs(u) for u in nodes)


def _ground_truth_forced(nodes, skel, colliders, constraints):
    """An edge is forced iff every DAG with this skeleton, exactly these
    unshielded colliders, acyclic, and respecting the constraints agrees on it."""
    edges = [tuple(sorted(tuple(pr))) for pr in skel]
    members = []
    for bits in itertools.product((0, 1), repeat=len(edges)):
        O = {(u, v) if bits[i] == 0 else (v, u) for i, (u, v) in enumerate(edges)}
        if not _is_acyclic(O, nodes):
            continue
        if _unshielded_colliders(O, skel, nodes) != colliders:
            continue
        if not all((a, b) in O for (a, b) in constraints):
            continue
        members.append(O)
    forced = set()
    for (u, v) in edges:
        dirs = {((u, v) if (u, v) in O else (v, u)) for O in members}
        if len(dirs) == 1:
            forced.add(next(iter(dirs)))
    return forced, len(members)


def test_ground_truth_oracle_sound_and_complete():
    """Over many random small CPDAGs + a consistent constraint, the propagation
    equals the brute-force forced set exactly — sound (no unforced orientation)
    AND complete (no forced orientation missed, which is what R4 guarantees)."""
    rng = np.random.default_rng(20260717)
    checked = r4_fired = 0
    for _ in range(600):
        n = int(rng.integers(4, 7))
        dag = {(i, j) for i in range(n) for j in range(i + 1, n)
               if rng.random() < 0.5}
        if not dag:
            continue
        nodes = list(range(n))
        skel = {frozenset(e) for e in dag}
        if len(skel) > 10:
            continue
        colliders = _unshielded_colliders(dag, skel, nodes)
        arms = set()
        for (pair, z) in colliders:
            for x in pair:
                arms.add((x, z))
        undirected = [tuple(sorted(tuple(pr))) for pr in skel
                      if not ({(tuple(pr)[0], tuple(pr)[1]),
                               (tuple(pr)[1], tuple(pr)[0])} & arms)]
        if not undirected:
            continue
        k = int(rng.integers(1, 4))
        idx = rng.choice(len(undirected), size=min(k, len(undirected)), replace=False)
        constraints = []
        for j in idx:
            u, v = undirected[j]
            constraints.append((u, v) if (u, v) in dag else (v, u))

        smap = {i: f"N{i}" for i in nodes}
        res = propagate_orientations(
            [smap[i] for i in nodes],
            directed=[(smap[a], smap[b]) for (a, b) in arms],
            undirected=[(smap[u], smap[v]) for (u, v) in undirected],
            constraints=[(smap[a], smap[b]) for (a, b) in constraints],
        )
        if res.conflicts:
            continue
        forced, nmembers = _ground_truth_forced(nodes, skel, colliders, constraints)
        if nmembers == 0:
            continue
        checked += 1
        mine = {(int(a[1:]), int(b[1:])) for (a, b) in res.oriented}
        assert mine == forced, (
            f"n={n} dag={sorted(dag)} constraints={constraints}: "
            f"unsound(extra)={sorted(mine - forced)} incomplete(missed)={sorted(forced - mine)}"
        )
        verify_orientation_propagation(orientation_to_dict(res))
        if any(p["rule"] == "R4" for p in res.provenance):
            r4_fired += 1
    assert checked >= 100, f"too few usable oracle trials ({checked})"
    assert r4_fired >= 1, "R4 never exercised — oracle regime too narrow to guard it"


# --- parity against causal-learn's reference Meek (bare completion only) -------

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


def test_parity_with_causal_learn_bare_cpdag():
    """Cross-library check of the R1-R3 core: feed the raw unshielded colliders
    of a PC-discovered CPDAG (no constraint, so R4 stays dormant) and confirm
    our closure reproduces causal-learn's completed CPDAG edge-for-edge.
    causal-learn implements only R1-R3, so it is a valid oracle only here — not
    for the constrained case, which the brute-force oracle above covers."""
    causallearn = pytest.importorskip("causallearn")
    from causallearn.search.ConstraintBased.PC import pc
    from causallearn.graph.Endpoint import Endpoint
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
    trials = 0
    for seed in range(500, 540):
        rng = np.random.default_rng(seed)
        A = _random_dag(p, 0.35, rng); X = _simulate(A, 1500, rng)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            cg0 = pc(X, 0.05, "fisherz", node_names=names, show_progress=False)
        d0, u0 = edges_of(cg0)
        skel = {frozenset(e) for e in d0} | u0
        nodes = names
        # recover the unshielded colliders of the CPDAG from its directed edges
        adj = {}
        for pr in skel:
            a, b = tuple(pr); adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
        arms = set()
        for z in nodes:
            parents = [x for x in nodes if (x, z) in d0]
            for x, y in itertools.combinations(parents, 2):
                if frozenset((x, y)) not in skel:
                    arms.add((x, z)); arms.add((y, z))
        undirected = [tuple(pr) for pr in skel
                      if not ({(tuple(pr)[0], tuple(pr)[1]),
                               (tuple(pr)[1], tuple(pr)[0])} & arms)]
        # our R1-R4 closure from raw colliders, NO constraint (R4 dormant)
        mine = propagate_orientations(nodes, directed=list(arms), undirected=undirected)
        assert set(mine.oriented) == d0, (
            f"seed {seed}: ours-only {sorted(set(mine.oriented) - d0)} "
            f"causal-learn-only {sorted(d0 - set(mine.oriented))}"
        )
        verify_orientation_propagation(orientation_to_dict(mine))
        trials += 1
    assert trials >= 20, f"too few usable parity trials ({trials})"
