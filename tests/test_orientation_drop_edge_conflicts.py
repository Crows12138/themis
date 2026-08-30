"""Phase 4 follow-on — drop-edge (asserted-non-adjacency) conflict detection.

The mirror of the CI-independence-side check. An unshielded collider a→C←b rests
on the collision at C AND the non-adjacency of a and b. Phase 4 audits knowledge
that asserts an adjacency the data found ABSENT (contradicting the non-adjacency);
this audits the opposite polarity — knowledge that asserts an absence (an edge to
drop) the data found PRESENT, contradicting the dependence the CI test found. A
pair joined only by a bare undirected edge is ``contradicts_dependence``; a pair
joined by a directed collider *arm* is ``undermines_collider`` (naming the apex),
because dropping the edge would remove an arm and the collider loses its data
support. The assertion is never applied (that would edit the skeleton).

The property test's oracle recomputes the undermined apexes straight from the
generating DAG's edges and skeleton — a representation independent of the
producer's CPDAG ``directed`` set: a data edge a→b is a collider arm iff b has
another parent w with a and w non-adjacent.
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
    asked,
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

def test_dropping_a_collider_arm_undermines_it():
    # data collider A->C<-B ; the edge A-C is the directed arm A->C. Asserting it
    # absent would remove that arm — the collider at C loses its data support.
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    conflicts = [c for c in r.conflicts if "absence" in c]
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c["reason"] == "undermines_collider"
    assert c["absence"] == ["A", "C"]
    assert c["colliders"] == ["C"]
    # the assertion is NOT applied — the closure is untouched
    assert set(r.oriented) == {("A", "C"), ("B", "C")}
    assert r.asserted_absences == (("A", "C"),)
    verify_orientation_propagation(orientation_to_dict(r))


def test_dropping_a_bare_undirected_edge_is_plain_conflict():
    # X-Y undirected (a bare skeleton dependence, not a collider arm); asserting it
    # absent contradicts the CI dependence but no collider rests on it.
    r = propagate_orientations(
        ["X", "Y"], undirected=[("X", "Y")], asserted_absences=[("Y", "X")])
    conflicts = [c for c in r.conflicts if "absence" in c]
    assert [c["reason"] for c in conflicts] == ["contradicts_dependence"]
    assert "colliders" not in conflicts[0]
    assert r.asserted_absences == (("X", "Y"),)
    verify_orientation_propagation(orientation_to_dict(r))


def test_asserting_an_existing_non_adjacency_is_no_conflict():
    # A, D genuinely non-adjacent — asserting them independent agrees with the data.
    r = propagate_orientations(
        ["A", "B", "D"], undirected=[("A", "B")], asserted_absences=[("A", "D")])
    assert not [c for c in r.conflicts if "absence" in c]
    verify_orientation_propagation(orientation_to_dict(r))


def test_absence_on_unknown_node_is_flagged():
    r = propagate_orientations(["A", "B"], undirected=[("A", "B")],
                               asserted_absences=[("A", "Z")])
    conflicts = [c for c in r.conflicts if "absence" in c]
    assert [c["reason"] for c in conflicts] == ["unknown_node"]
    verify_orientation_propagation(orientation_to_dict(r))


def test_duplicate_absence_counts_once():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C"), ("C", "A"), ("A", "C")])
    assert len([c for c in r.conflicts if "absence" in c]) == 1
    assert r.asserted_absences == (("A", "C"),)


def test_self_absence_raises():
    with pytest.raises(OrientationError):
        propagate_orientations(["A", "B"], asserted_absences=[("A", "A")])


def test_adjacency_and_absence_conflicts_coexist():
    # an asserted adjacency (A-B, which data found absent) AND an asserted absence
    # (A-C, a data collider arm) surface together, keyed differently.
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_adjacencies=[("A", "B")], asserted_absences=[("A", "C")])
    keys = {(("assertion" in c), ("absence" in c), c["reason"]) for c in r.conflicts}
    assert (True, False, "undermines_collider") in keys    # A-B adjacency
    assert (False, True, "undermines_collider") in keys    # A-C absence
    verify_orientation_propagation(orientation_to_dict(r))


def test_direction_and_absence_conflicts_coexist():
    # a direction conflict (C->A contradicts the collider) AND an absence conflict
    # (drop A-C) surface together, keyed differently.
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        constraints=[("C", "A")], asserted_absences=[("A", "C")])
    reasons = {(("absence" in c), c["reason"]) for c in r.conflicts}
    assert (False, "contradicts_data_orientation") in reasons
    assert (True, "undermines_collider") in reasons
    verify_orientation_propagation(orientation_to_dict(r))


# --- question compiler --------------------------------------------------------

def test_absence_conflict_becomes_a_conflict_question_first():
    r = propagate_orientations(
        ["A", "B", "C", "X", "Y"], directed=[("A", "C"), ("B", "C")],
        undirected=[("X", "Y")], asserted_absences=[("A", "C")])
    qs = compile_orientation_questions(r)
    verify_orientation_questions(question_set_to_dict(qs))
    assert [q.kind for q in qs.questions][0] == "conflict"      # conflicts rank first
    cq = qs.questions[0]
    assert cq.reason == "undermines_collider"
    # The arm is a fact in a hole now, not a substring of a sentence: which
    # arm the conflict is about is the same in every language, and asking
    # the rendered text for it made the assertion depend on which one the
    # producer happened to write.
    assert cq.asks["token"] == "absence_undermines_a_collider"
    assert cq.asks["said"]["arm"] == "A→C"
    assert cq.detail.get("colliders") == ["C"]


def test_bare_absence_conflict_prompt_mentions_dropping():
    r = propagate_orientations(["X", "Y"], undirected=[("X", "Y")],
                               asserted_absences=[("X", "Y")])
    qs = compile_orientation_questions(r)
    verify_orientation_questions(question_set_to_dict(qs))
    cq = qs.questions[0]
    assert cq.reason == "contradicts_dependence"
    assert cq.asks["token"] == "absence_contradicts_dependence"
    assert "删掉" in asked(cq, "zh")
    assert "drop the edge" in asked(cq, "en")


# --- verifier rejects tampering -----------------------------------------------

def test_verifier_rejects_forged_absence_conflict():
    r = propagate_orientations(["A", "B"], undirected=[("A", "B")])  # no absences
    d = orientation_to_dict(r)
    d["conflicts"] = [{"absence": ["A", "B"], "reason": "contradicts_dependence"}]
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_dropped_absence_conflict():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    d = orientation_to_dict(r)
    d["conflicts"] = [c for c in d["conflicts"] if "absence" not in c]  # silence it
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_downgraded_absence_reason():
    # hide that a collider is at stake by downgrading undermines->contradicts
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    d = orientation_to_dict(r)
    for c in d["conflicts"]:
        if "absence" in c and c.get("reason") == "undermines_collider":
            c["reason"] = "contradicts_dependence"
            c.pop("colliders", None)
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_verifier_rejects_forged_absence_collider_list():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    d = orientation_to_dict(r)
    for c in d["conflicts"]:
        if "absence" in c and c.get("reason") == "undermines_collider":
            c["colliders"] = ["A"]                              # wrong apex
    with pytest.raises(VerificationError):
        verify_orientation_propagation(d)


def test_question_verifier_rejects_missing_absence_conflict_question():
    r = propagate_orientations(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    d = question_set_to_dict(compile_orientation_questions(r))
    d["questions"] = [q for q in d["questions"] if q["kind"] != "conflict"]
    with pytest.raises(VerificationError):
        verify_orientation_questions(d)


# --- session ------------------------------------------------------------------

def test_session_surfaces_absence_and_verifies():
    s = start_orientation_session(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    assert s.status == "open"
    assert any(q.kind == "conflict" and q.reason == "undermines_collider"
               for q in next_questions(s))
    # an absence conflict is not an orientation answer — no source-trail / rejected entry
    assert not s.source_trail and not s.rejected
    assert s.asserted_absences == (("A", "C"),)
    verify_orientation_session(session_to_dict(s))
    # it persists across an orientation answer on an unrelated edge
    s2 = start_orientation_session(
        ["A", "B", "C", "X", "Y"], directed=[("A", "C"), ("B", "C")],
        undirected=[("X", "Y")], asserted_absences=[("A", "C")])
    s2 = ingest_orientation_answers(s2, [{"direction": ["X", "Y"], "source": "human"}])
    assert any(q.reason == "undermines_collider" for q in next_questions(s2)
               if q.kind == "conflict")
    verify_orientation_session(session_to_dict(s2))


def test_session_verifier_rejects_mismatched_asserted_absences():
    s = start_orientation_session(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
        asserted_absences=[("A", "C")])
    d = session_to_dict(s)
    d["asserted_absences"] = []          # session claims none, embedded says one
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


# --- property test ------------------------------------------------------------

def _dag_colliders(dag_edges, nodes):
    """Unshielded colliders of a DAG: (parent, parent, apex)."""
    skel = {frozenset(e) for e in dag_edges}
    cols = []
    for z in nodes:
        parents = [x for x in nodes if (x, z) in dag_edges]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.append((x, y, z))
    return cols


def test_random_absences_match_independent_oracle():
    """Random CPDAGs, random asserted absences (a mix of existing edges — both
    collider arms and bare undirected edges — and genuinely non-adjacent pairs).
    The undermined apexes are recomputed straight from the generating DAG (a data
    edge a→b is a collider arm iff b has another parent w with a, w non-adjacent),
    independent of the producer's CPDAG ``directed`` set."""
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

        # assert some existing edges absent (arms and undirected), plus occasionally
        # a genuinely non-adjacent pair (which should NOT conflict).
        all_pairs = [tuple(sorted((nodes[i], nodes[j])))
                     for i in range(n) for j in range(i + 1, n)]
        edges = [p for p in all_pairs if frozenset(p) in skel]
        if not edges:
            continue
        k = int(rng.integers(1, min(len(edges), 3) + 1))
        asserted = [edges[i] for i in rng.choice(len(edges), size=k, replace=False)]
        non_adj = [p for p in all_pairs if frozenset(p) not in skel]
        if non_adj and rng.random() < 0.4:
            asserted.append(non_adj[int(rng.integers(len(non_adj)))])

        r = propagate_orientations(nodes, directed=list(arms), undirected=undirected,
                                   asserted_absences=asserted)
        verify_orientation_propagation(orientation_to_dict(r))
        verify_orientation_questions(question_set_to_dict(compile_orientation_questions(r)))

        got = {tuple(c["absence"]): (c["reason"], tuple(c.get("colliders", [])))
               for c in r.conflicts if "absence" in c}
        for (a, b) in {tuple(sorted(p)) for p in asserted}:
            if frozenset((a, b)) not in skel:
                assert (a, b) not in got             # non-adjacent → agrees, no conflict
                continue
            # oracle: for each direction present in the DAG, the head is an apex iff
            # it has another parent non-adjacent to the tail (an unshielded collider).
            apexes = []
            for (tail, head) in ((a, b), (b, a)):
                if (tail, head) in dag and any(
                        w != tail and (w, head) in dag
                        and frozenset((tail, w)) not in skel for w in nodes):
                    apexes.append(head)
            apexes = tuple(sorted(apexes))
            if apexes:
                assert got[(a, b)] == ("undermines_collider", apexes)
            else:
                assert got[(a, b)] == ("contradicts_dependence", ())
        ran += 1
    assert ran >= 50, f"too few usable trials ({ran})"
