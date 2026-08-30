"""Phase 2 — compile a leverage-ranked orientation question set from an
equivalence class, and its independent verifier. The producer measures leverage
with the Phase 1 Meek propagation; the verifier re-measures with a second Meek
transcription; and the property test recomputes every number a third way — a
brute-force equivalence-class enumeration — so a rule-set bug shared by the two
propagation paths cannot hide (the discipline R4 taught).
"""
import itertools

import numpy as np
import pytest

from themis.estimation.orientation import propagate_orientations
from themis.estimation.orientation_questions import (
    asked,
    compile_orientation_questions,
    question_set_to_dict,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_question_rules import verify_orientation_questions


# --- structural unit tests ----------------------------------------------------

def test_chain_abc_leverage_and_cascade():
    # A-B-C, no colliders. Answering A->B forces B->C (R1), and answering C->B
    # forces B->A — so each edge has best-case leverage 2 (itself + the other) but
    # guaranteed 1 (the other direction cascades to nothing extra).
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    qs = compile_orientation_questions(r)
    orient = [q for q in qs.questions if q.kind == "orientation"]
    assert {q.edge for q in orient} == {("A", "B"), ("B", "C")}
    assert all(q.leverage == 2 for q in orient)
    assert all(q.guaranteed == 1 for q in orient)
    assert all(q.unlocks == () for q in orient)
    verify_orientation_questions(question_set_to_dict(qs))


def test_orientation_questions_ranked_by_descending_leverage():
    r = propagate_orientations(
        ["A", "B", "C", "D", "E"],
        undirected=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("A", "C")],
    )
    qs = compile_orientation_questions(r)
    levs = [q.leverage for q in qs.questions if q.kind == "orientation"]
    assert levs == sorted(levs, reverse=True)
    verify_orientation_questions(question_set_to_dict(qs))


def test_conflict_is_ranked_first_and_adjudicable():
    # data collider A->C<-B ; the answer C->A contradicts it -> conflict question
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")], constraints=[("C", "A")],
    )
    qs = compile_orientation_questions(r)
    cq = qs.questions[0]
    assert cq.kind == "conflict"
    assert cq.reason == "contradicts_data_orientation"
    # Adjudicable means the question offers the override as a choice rather
    # than reporting the clash. Asked of both readers, because the species
    # is what each language is written against.
    assert cq.asks["token"] == "direction_contradicts_the_data"
    assert "覆盖" in asked(cq, "zh")
    assert "override" in asked(cq, "en")
    verify_orientation_questions(question_set_to_dict(qs))


def test_one_question_per_remaining_edge():
    names = [f"N{i}" for i in range(5)]
    undirected = [("N0", "N1"), ("N1", "N2"), ("N2", "N3"), ("N3", "N4")]
    r = propagate_orientations(names, undirected=undirected)
    qs = compile_orientation_questions(r)
    orient = [q for q in qs.questions if q.kind == "orientation"]
    assert {q.edge for q in orient} == {tuple(sorted(e)) for e in undirected}
    verify_orientation_questions(question_set_to_dict(qs))


# --- verifier rejects tampering -----------------------------------------------

def test_verifier_rejects_inflated_leverage():
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = question_set_to_dict(compile_orientation_questions(r))
    for q in d["questions"]:
        if q["kind"] == "orientation":
            q["leverage"] += 5  # claim a bigger cascade than reality
            break
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


def test_verifier_rejects_wrong_guaranteed():
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = question_set_to_dict(compile_orientation_questions(r))
    for q in d["questions"]:
        if q["kind"] == "orientation":
            q["guaranteed"] = 2  # overstate what is fixed regardless of the answer
            q["unlocks"] = [["B", "C"]]
            break
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


def test_verifier_rejects_dropped_orientation_question():
    r = propagate_orientations(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")],
    )
    d = question_set_to_dict(compile_orientation_questions(r))
    d["questions"] = d["questions"][:-1]  # drop one edge's question
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


def test_verifier_rejects_fabricated_conflict_question():
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = question_set_to_dict(compile_orientation_questions(r))
    d["questions"] = [{
        "kind": "conflict", "edge": ["A", "B"], "leverage": 0, "guaranteed": 0,
        "unlocks": [], "reason": "contradicts_data_orientation", "detail": {},
        "prompt": "fabricated",
    }] + d["questions"]
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


def test_verifier_rejects_question_on_non_remaining_edge():
    r = propagate_orientations(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = question_set_to_dict(compile_orientation_questions(r))
    d["questions"].append({
        "kind": "orientation", "edge": ["A", "C"], "leverage": 1, "guaranteed": 1,
        "unlocks": [], "reason": "", "detail": {}, "prompt": "not an edge",
    })
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


def test_verifier_rejects_misordered_ranking():
    r = propagate_orientations(
        ["A", "B", "C", "D", "E"],
        undirected=[("A", "B"), ("B", "C"), ("C", "D"), ("D", "E"), ("A", "C")],
    )
    d = question_set_to_dict(compile_orientation_questions(r))
    orient_idx = [i for i, q in enumerate(d["questions"]) if q["kind"] == "orientation"]
    if len(orient_idx) >= 2:
        i, j = orient_idx[0], orient_idx[-1]
        if d["questions"][i]["leverage"] != d["questions"][j]["leverage"]:
            d["questions"][i], d["questions"][j] = d["questions"][j], d["questions"][i]
            with pytest.raises(VerificationError):
                verify_orientation_questions(d)


# --- property test: independent brute-force enumeration oracle ----------------

def _unshielded_colliders(directed, skel, nodes):
    cols = set()
    for z in nodes:
        parents = [x for x in nodes if (x, z) in directed]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.add((frozenset((x, y)), z))
    return cols


def _acyclic(directed, nodes):
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


def _members(nodes, D, comp_edges, skel, target):
    out = []
    for bits in itertools.product((0, 1), repeat=len(comp_edges)):
        o = {e: (e if bits[i] == 0 else (e[1], e[0])) for i, e in enumerate(comp_edges)}
        full = set(D) | set(o.values())
        if _acyclic(full, nodes) and _unshielded_colliders(full, skel, nodes) == target:
            out.append(o)
    return out


def _determined_given(members, edge, direction, comp_edges):
    """Edges of the component constant across all members whose ``edge`` points
    ``direction`` — the brute-force cascade of that answer."""
    sub = [m for m in members if m[edge] == direction]
    return {e for e in comp_edges if len({m[e] for m in sub}) == 1}


def test_leverage_matches_bruteforce_enumeration_oracle():
    """Over many random small CPDAGs, recompute every question's leverage /
    guaranteed / unlocks by brute-force equivalence-class enumeration — an engine
    that shares no code with either Meek propagation path — and assert the
    compiled numbers match exactly. Also asserts a real cascade (leverage>=2)
    occurs and that the verifier accepts."""
    rng = np.random.default_rng(20260717)
    checked = max_leverage = 0
    for _ in range(400):
        n = int(rng.integers(4, 7))
        dag = {(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.5}
        if not dag:
            continue
        nodes = [f"N{i}" for i in range(n)]
        skel = {frozenset((f"N{a}", f"N{b}")) for (a, b) in dag}
        if len(skel) > 10:
            continue
        dag_s = {(f"N{a}", f"N{b}") for (a, b) in dag}
        arms = set()
        for (pair, z) in _unshielded_colliders(dag_s, skel, nodes):
            for x in pair:
                arms.add((x, z))
        undirected = [tuple(sorted(tuple(p))) for p in skel
                      if not ({(tuple(p)[0], tuple(p)[1]), (tuple(p)[1], tuple(p)[0])} & arms)]
        if not undirected:
            continue
        r = propagate_orientations(nodes, directed=list(arms), undirected=undirected)
        qs = compile_orientation_questions(r)
        verify_orientation_questions(question_set_to_dict(qs))

        D = set(r.oriented)
        U = {tuple(sorted(e)) for e in r.remaining_undirected}
        skelU = {frozenset(e) for e in D} | {frozenset(e) for e in U}
        target = _unshielded_colliders(D, skelU, nodes)
        # connected components of U
        adj = {}
        for (a, b) in U:
            adj.setdefault(a, set()).add(b); adj.setdefault(b, set()).add(a)
        comp_of = {}
        seen = set()
        comps = []
        for start in list(adj):
            if start in seen:
                continue
            stack = [start]; cn = set()
            while stack:
                x = stack.pop()
                if x in seen:
                    continue
                seen.add(x); cn.add(x); stack.extend(adj[x] - seen)
            ce = [e for e in U if e[0] in cn and e[1] in cn]
            comps.append(ce)
            for e in ce:
                comp_of[e] = ce
        members_cache = {id(ce): _members(nodes, D, ce, skelU, target) for ce in comps}

        checked += 1
        for q in qs.questions:
            if q.kind != "orientation":
                continue
            e = q.edge; a, b = e
            ce = comp_of[e]
            members = members_cache[id(ce)]
            fwd = _determined_given(members, e, (a, b), ce)
            bwd = _determined_given(members, e, (b, a), ce)
            leverage = max(len(fwd), len(bwd))
            both = fwd & bwd
            assert q.leverage == leverage, (e, q.leverage, leverage)
            assert q.guaranteed == len(both), (e, q.guaranteed, len(both))
            assert set(q.unlocks) == (both - {e}), (e, q.unlocks, both - {e})
            max_leverage = max(max_leverage, leverage)
    assert checked >= 50, f"too few usable trials ({checked})"
    assert max_leverage >= 2, "no cascade (leverage>=2) ever exercised — regime too narrow"
