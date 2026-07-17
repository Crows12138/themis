"""Phase 4 — CI-independence-side conflict detection.

An unshielded collider a→C←b rests on two data facts: the collision at C, and the
NON-adjacency of a and b (the independence the discovery's CI test found). Phase 1
audits knowledge that contradicts the first (a wrong direction); Phase 4 audits
knowledge that contradicts the second — an asserted adjacency the data found
absent. If that non-adjacency is a data collider's premise the conflict is
``undermines_collider`` (naming the apex); otherwise ``contradicts_independence``.
The assertion is never applied (that would edit the skeleton).

The property test's oracle derives the undermined apexes straight from the
generating DAG's edges — a representation independent of the producer's CPDAG
``directed`` set — which is sound because for a non-adjacent pair every common
child is necessarily an unshielded-collider apex.
"""
import itertools

import numpy as np
import pytest

from themis.estimation.orientation import (
    OrientationError,
    orientation_to_dict,
    propagate_orientations,
)
from themis.estimation.orientation_questions import (
    compile_orientation_questions,
    question_set_to_dict,
)
from themis.estimation.orientation_session import (
    ingest_orientation_answers,
    next_questions,
    session_to_dict,
    start_orientation_session,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_question_rules import verify_orientation_questions
from themis.verifier.orientation_rules import verify_orientation_propagation
from themis.verifier.orientation_session_rules import verify_orientation_session


# --- producer -----------------------------------------------------------------

def test_asserting_a_collider_premise_undermines_it():
    # data collider A->C<-B ; A,B non-adjacent (unshielded). Asserting A-B adjacent
    # would shield C — the orientations A->C, B->C lose their data support.
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    conflicts = [c for c in r.conflicts if "assertion" in c]
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["reason"] == "undermines_collider"
    assert c["assertion"] == ["A", "B"]
    assert c["colliders"] == ["C"]
    # the assertion is NOT applied — the closure is untouched
    assert set(r.oriented) == {("A", "C"), ("B", "C")}
    assert r.asserted_adjacencies == (("A", "B"),)
    verify_orientation_propagation(orientation_to_dict(r))


def test_asserting_a_non_collider_independence_is_plain_conflict():
    # A-B undirected, D isolated from the pair; asserting A-D (data found them
    # independent) contradicts the CI finding but no collider rests on it.
    r = propagate_orientations(
        ["A", "B", "D"], undirected=[("A", "B")],
        asserted_adjacencies=[("A", "D")])
    conflicts = [c for c in r.conflicts if "assertion" in c]
    assert [c["reason"] for c in conflicts] == ["contradicts_independence"]
    assert "colliders" not in conflicts[0]
    verify_orientation_propagation(orientation_to_dict(r))


def test_asserting_an_existing_adjacency_is_no_conflict():
    for spec in ({"undirected": [("A", "B")]}, {"directed": [("A", "B")]}):
        r = propagate_orientations(["A", "B"], asserted_adjacencies=[("B", "A")], **spec)
        assert not [c for c in r.conflicts if "assertion" in c]
        verify_orientation_propagation(orientation_to_dict(r))


def test_asserting_unknown_node_is_flagged():
    r = propagate_orientations(["A", "B"], undirected=[("A", "B")],
                               asserted_adjacencies=[("A", "Z")])
    conflicts = [c for c in r.conflicts if "assertion" in c]
    assert [c["reason"] for c in conflicts] == ["unknown_node"]
    verify_orientation_propagation(orientation_to_dict(r))


def test_duplicate_assertion_counts_once():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B"), ("B", "A"), ("A", "B")])
    assert len([c for c in r.conflicts if "assertion" in c]) == 1
    assert r.asserted_adjacencies == (("A", "B"),)


def test_self_adjacency_raises():
    with pytest.raises(OrientationError):
        propagate_orientations(["A", "B"], asserted_adjacencies=[("A", "A")])


def test_direction_and_adjacency_conflicts_coexist():
    # a direction conflict (C->A contradicts the collider) AND an adjacency
    # conflict (A-B undermines it) surface together, keyed differently.
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        constraints=[("C", "A")], asserted_adjacencies=[("A", "B")])
    reasons = {(("assertion" in c), c["reason"]) for c in r.conflicts}
    assert (False, "contradicts_data_orientation") in reasons
    assert (True, "undermines_collider") in reasons
    verify_orientation_propagation(orientation_to_dict(r))


# --- question compiler --------------------------------------------------------

def test_adjacency_conflict_becomes_a_conflict_question_first():
    r = propagate_orientations(
        ["A", "B", "C", "X", "Y"], directed=[("A", "C"), ("B", "C")],
        undirected=[("X", "Y")], asserted_adjacencies=[("A", "B")])
    qs = compile_orientation_questions(r)
    verify_orientation_questions(question_set_to_dict(qs))
    kinds = [q.kind for q in qs.questions]
    assert kinds[0] == "conflict"                      # conflicts rank first
    cq = qs.questions[0]
    assert cq.reason == "undermines_collider"
    assert "A→C←B" in cq.prompt
    assert cq.detail.get("colliders") == ["C"]


# --- verifier rejects tampering -----------------------------------------------

def test_verifier_rejects_forged_collider_list():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    d = orientation_to_dict(r)
    for c in d["conflicts"]:
        if c.get("reason") == "undermines_collider":
            c["colliders"] = []                        # hide the collider it breaks
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_downgraded_reason():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    d = orientation_to_dict(r)
    for c in d["conflicts"]:
        if c.get("reason") == "undermines_collider":
            c["reason"] = "contradicts_independence"   # hide that a collider is at stake
            c.pop("colliders", None)
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_fabricated_adjacency_conflict():
    r = propagate_orientations(["A", "B"], undirected=[("A", "B")])
    d = orientation_to_dict(r)
    d["conflicts"] = [{"assertion": ["A", "B"], "reason": "contradicts_independence"}]
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_dropped_adjacency_conflict():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    d = orientation_to_dict(r)
    d["conflicts"] = [c for c in d["conflicts"] if "assertion" not in c]  # silence it
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_question_verifier_rejects_missing_adjacency_conflict_question():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    d = question_set_to_dict(compile_orientation_questions(r))
    d["questions"] = [q for q in d["questions"] if q["kind"] != "conflict"]
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


# --- session ------------------------------------------------------------------

def test_session_surfaces_asserted_adjacency_and_verifies():
    s = start_orientation_session(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    assert s.status == "open"
    assert any(q.kind == "conflict" and q.reason == "undermines_collider"
               for q in next_questions(s))
    # an adjacency conflict is not an orientation answer, so it makes no
    # source-trail / rejected entry
    assert not s.source_trail and not s.rejected
    verify_orientation_session(session_to_dict(s))
    # it persists across an orientation answer on an unrelated edge
    s2 = start_orientation_session(
        ["A", "B", "C", "X", "Y"], directed=[("A", "C"), ("B", "C")],
        undirected=[("X", "Y")], asserted_adjacencies=[("A", "B")])
    s2 = ingest_orientation_answers(s2, [{"direction": ["X", "Y"], "source": "human"}])
    assert any(q.reason == "undermines_collider" for q in next_questions(s2)
               if q.kind == "conflict")
    verify_orientation_session(session_to_dict(s2))


def test_session_verifier_rejects_mismatched_asserted_adjacencies():
    s = start_orientation_session(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")])
    d = session_to_dict(s)
    d["asserted_adjacencies"] = []          # session claims none, embedded says one
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


# --- property test ------------------------------------------------------------

def _dag_colliders(dag_edges, nodes):
    """Unshielded colliders of a DAG: (frozenset(parents), apex)."""
    skel = {frozenset(e) for e in dag_edges}
    cols = []
    for z in nodes:
        parents = [x for x in nodes if (x, z) in dag_edges]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.append((x, y, z))
    return cols


def test_random_assertions_match_independent_oracle():
    """Random CPDAGs, random asserted adjacencies. The undermined apexes are
    recomputed straight from the generating DAG's edges (independent of the
    producer's CPDAG ``directed`` set); the verifier must accept and the reasons
    must match the oracle."""
    rng = np.random.default_rng(20260717)
    ran = 0
    for _ in range(400):
        n = int(rng.integers(4, 7))
        dag = {(f"N{i}", f"N{j}") for i in range(n) for j in range(i + 1, n)
               if rng.random() < 0.5}
        if not dag:
            continue
        nodes = [f"N{i}" for i in range(n)]
        skel = {frozenset(e) for e in dag}
        arms = set()
        for (x, y, z) in _dag_colliders(dag, nodes):
            arms.add((x, z)); arms.add((y, z))
        undirected = [tuple(sorted(tuple(p))) for p in skel
                      if not ({(tuple(p)[0], tuple(p)[1]), (tuple(p)[1], tuple(p)[0])} & arms)]

        # pick some non-adjacent pairs to assert, plus occasionally an existing edge
        all_pairs = [tuple(sorted((nodes[i], nodes[j])))
                     for i in range(n) for j in range(i + 1, n)]
        non_adj = [p for p in all_pairs if frozenset(p) not in skel]
        if not non_adj:
            continue
        k = int(rng.integers(1, min(len(non_adj), 3) + 1))
        asserted = [non_adj[i] for i in rng.choice(len(non_adj), size=k, replace=False)]
        if list(skel) and rng.random() < 0.3:            # sometimes assert an existing edge
            e = tuple(sorted(tuple(next(iter(skel)))))
            asserted.append(e)

        r = propagate_orientations(nodes, directed=list(arms), undirected=undirected,
                                   asserted_adjacencies=asserted)
        verify_orientation_propagation(orientation_to_dict(r))
        verify_orientation_questions(question_set_to_dict(compile_orientation_questions(r)))

        got = {tuple(c["assertion"]): (c["reason"], tuple(c.get("colliders", [])))
               for c in r.conflicts if "assertion" in c}
        for (a, b) in {tuple(sorted(p)) for p in asserted}:
            if frozenset((a, b)) in skel:
                assert (a, b) not in got            # existing edge → no conflict
                continue
            # oracle: apexes are common children in the DAG (a,b non-adjacent ⇒
            # each such child is an unshielded-collider apex)
            apexes = tuple(sorted(z for z in nodes if (a, z) in dag and (b, z) in dag))
            if apexes:
                assert got[(a, b)] == ("undermines_collider", apexes)
            else:
                assert got[(a, b)] == ("contradicts_independence", ())
        ran += 1
    assert ran >= 50, f"too few usable trials ({ran})"
