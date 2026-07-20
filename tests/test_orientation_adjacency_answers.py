"""Interactive equivalence-class orientation — adjacency answers (the last
follow-on). An answer about a pair may now be a *direction*, an *adjacency
polarity* (``"present"`` = add / assert the edge; ``"absent"`` = drop it), or
*unknown* — the three on equal footing, latest-wins per pair. A direction feeds
the Meek closure as a constraint; an adjacency polarity feeds the producer's
CI-side / drop-edge conflict detection (surfaced, never applied — either would
edit the skeleton); unknown defers. The session's start-time ``asserted_*`` are
the base (turn-0); per-turn adjacency answers override them by the same
latest-wins projection. The verifier re-derives the *effective* asserted sets
independently and ties the embedded artifacts to them.
"""
import itertools

import numpy as np
import pytest

from themis.estimation.orientation_session import (
    OrientationSessionError,
    ingest_orientation_answers,
    next_questions,
    session_to_dict,
    start_orientation_session,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_session_rules import verify_orientation_session


# --- per-turn adjacency answers surface conflicts -----------------------------

def test_present_answer_surfaces_ci_conflict():
    # data collider A->C<-B (A,B non-adjacent). Asserting A-B present per-turn
    # would shield the collider — a CI-side undermines_collider conflict.
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")])
    assert s.status == "resolved"       # nothing undetermined, no assertion yet
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "present",
                                        "source": "domain_knowledge"}])
    assert set(s.result.asserted_adjacencies) == {("A", "B")}
    assert not s.result.asserted_absences
    q = next(q for q in next_questions(s) if q.kind == "conflict")
    assert q.reason == "undermines_collider"
    assert "C" in q.detail.get("colliders", [])
    assert s.status == "open"
    # an adjacency answer is never applied — no source-trail / rejected entry
    assert not s.source_trail and not s.rejected
    verify_orientation_session(session_to_dict(s))


def test_absent_answer_surfaces_drop_edge_conflict():
    # data collider A->C<-B; asserting the arm A-C absent per-turn undermines it.
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"edge": ["A", "C"], "adjacency": "absent",
                                        "source": "human"}])
    assert set(s.result.asserted_absences) == {("A", "C")}
    q = next(q for q in next_questions(s) if q.kind == "conflict")
    assert q.reason == "undermines_collider"
    assert not s.source_trail and not s.rejected
    verify_orientation_session(session_to_dict(s))


def test_absent_answer_on_bare_edge_is_contradicts_dependence():
    s = start_orientation_session(["X", "Y"], undirected=[("X", "Y")])
    s = ingest_orientation_answers(s, [{"edge": ["X", "Y"], "adjacency": "absent"}])
    assert set(s.result.asserted_absences) == {("X", "Y")}
    q = next(q for q in next_questions(s) if q.kind == "conflict")
    assert q.reason == "contradicts_dependence"
    verify_orientation_session(session_to_dict(s))


def test_present_answer_agreeing_with_data_is_no_conflict():
    # X-Y already adjacent (an undirected edge); asserting it present agrees.
    s = start_orientation_session(["X", "Y"], undirected=[("X", "Y")])
    s = ingest_orientation_answers(s, [{"edge": ["X", "Y"], "adjacency": "present"}])
    assert set(s.result.asserted_adjacencies) == {("X", "Y")}
    assert not any(q.kind == "conflict" for q in next_questions(s))
    verify_orientation_session(session_to_dict(s))


# --- latest-wins across answer kinds ------------------------------------------

def test_present_then_absent_latest_wins():
    # A->C<-B collider. present(A,B) -> CI conflict; then absent(A,B) flips it to
    # an absence that AGREES with the data (A,B non-adjacent) -> conflict gone.
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "present"}])
    assert any(q.kind == "conflict" for q in next_questions(s))
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "absent"}])
    assert set(s.result.asserted_adjacencies) == set()
    assert set(s.result.asserted_absences) == {("A", "B")}
    assert not any(q.kind == "conflict" for q in next_questions(s))  # absence agrees
    verify_orientation_session(session_to_dict(s))


def test_base_adjacency_overridden_by_absent_answer():
    # start with base asserted adjacency (A,B) the data found absent -> CI conflict;
    # a per-turn absent(A,B) answer overrides the base, and now agrees with the data.
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
                                  asserted_adjacencies=[("A", "B")])
    assert s.asserted_adjacencies == (("A", "B"),)         # base recorded
    assert set(s.result.asserted_adjacencies) == {("A", "B")}  # effective at turn 0
    assert any(q.reason == "undermines_collider" for q in next_questions(s)
               if q.kind == "conflict")
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "absent"}])
    assert s.asserted_adjacencies == (("A", "B"),)         # base unchanged
    assert set(s.result.asserted_adjacencies) == set()     # answer overrode it
    assert set(s.result.asserted_absences) == {("A", "B")}
    assert not any(q.kind == "conflict" for q in next_questions(s))
    verify_orientation_session(session_to_dict(s))


def test_adjacency_answer_retracted_by_unknown():
    # absent(X,Y) on a bare edge -> drop-edge conflict; then unknown retracts it,
    # leaving X-Y a normal (now deferred) undirected edge with no conflict.
    s = start_orientation_session(["X", "Y"], undirected=[("X", "Y")])
    s = ingest_orientation_answers(s, [{"edge": ["X", "Y"], "adjacency": "absent"}])
    assert any(q.kind == "conflict" for q in next_questions(s))
    s = ingest_orientation_answers(s, [{"edge": ["X", "Y"], "direction": None}])
    assert set(s.result.asserted_absences) == set()
    assert ("X", "Y") in s.deferred
    assert not any(q.kind == "conflict" for q in next_questions(s))
    assert s.status == "blocked"
    verify_orientation_session(session_to_dict(s))


def test_direction_supersedes_earlier_present_answer():
    # present(A,B) on an undirected edge, then a direction A->B: the direction is a
    # constraint (applied), and the pair leaves the effective adjacency set.
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "present"}])
    assert set(s.result.asserted_adjacencies) == {("A", "B")}
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"], "source": "human"}])
    assert set(s.result.asserted_adjacencies) == set()
    assert s.constraints == (("A", "B"),)
    assert ("A", "B") in s.result.oriented and ("B", "C") in s.result.oriented
    verify_orientation_session(session_to_dict(s))


def test_direction_and_adjacency_coexist_on_different_edges():
    s = start_orientation_session(["A", "B", "C", "X", "Y"],
                                  directed=[("A", "C"), ("B", "C")],
                                  undirected=[("X", "Y")])
    s = ingest_orientation_answers(s, [
        {"direction": ["X", "Y"], "source": "human"},
        {"edge": ["A", "B"], "adjacency": "present", "source": "domain_knowledge"},
    ])
    assert ("X", "Y") in s.result.oriented
    assert set(s.result.asserted_adjacencies) == {("A", "B")}
    assert any(q.reason == "undermines_collider" for q in next_questions(s)
               if q.kind == "conflict")
    verify_orientation_session(session_to_dict(s))


# --- ill-formed answers -------------------------------------------------------

def test_direction_and_adjacency_together_raises():
    s = start_orientation_session(["A", "B"], undirected=[("A", "B")])
    with pytest.raises(OrientationSessionError):
        ingest_orientation_answers(
            s, [{"direction": ["A", "B"], "adjacency": "present"}])


def test_invalid_adjacency_value_raises():
    s = start_orientation_session(["A", "B"], undirected=[("A", "B")])
    with pytest.raises(OrientationSessionError):
        ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "maybe"}])


def test_self_loop_adjacency_answer_raises():
    s = start_orientation_session(["A", "B"], undirected=[("A", "B")])
    with pytest.raises(OrientationSessionError):
        ingest_orientation_answers(s, [{"edge": ["A", "A"], "adjacency": "absent"}])


# --- verifier rejects tampering -----------------------------------------------

def _present_session_dict():
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "adjacency": "present"}])
    return session_to_dict(s)


def test_verifier_rejects_dropped_adjacency_field():
    # blank the answer's adjacency: recomputed effective loses (A,B) but the
    # embedded propagation still asserts it -> mismatch.
    d = _present_session_dict()
    for a in d["answers"]:
        if a["edge"] == ["A", "B"]:
            a["adjacency"] = None
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_flipped_adjacency_polarity():
    # flip present -> absent in the answer only; effective adjacency/absence sets
    # move but the embedded artifacts do not.
    d = _present_session_dict()
    for a in d["answers"]:
        if a["edge"] == ["A", "B"]:
            a["adjacency"] = "absent"
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_tampered_base_adjacency():
    # corrupt the top-level base: recomputed effective changes, embedded does not.
    d = _present_session_dict()
    d["asserted_adjacencies"] = [["B", "C"]]
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_answer_stating_direction_and_adjacency():
    d = _present_session_dict()
    for a in d["answers"]:
        if a["edge"] == ["A", "B"]:
            a["direction"] = ["A", "B"]   # now both a direction and an adjacency
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


# --- property test: independent latest-wins projection oracle -----------------

def _unshielded_colliders(directed, skel, nodes):
    cols = set()
    for z in nodes:
        parents = [x for x in nodes if (x, z) in directed]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.add((frozenset((x, y)), z))
    return cols


def test_random_adjacency_answers_match_independent_projection():
    """Random CPDAGs driven by random answer sequences that mix directions,
    unknowns, and adjacency polarities (present / absent) on ANY pair — plus a
    random start-time base. The verifier accepts every intermediate session, and
    the producer's effective asserted sets equal an INDEPENDENT latest-wins
    projection recomputed here directly from the base and the answer history."""
    rng = np.random.default_rng(20260720)
    ran = 0
    for _ in range(400):
        n = int(rng.integers(3, 6))
        dag = {(i, j) for i in range(n) for j in range(i + 1, n) if rng.random() < 0.5}
        if not dag:
            continue
        nodes = [f"N{i}" for i in range(n)]
        skel = {frozenset((f"N{a}", f"N{b}")) for (a, b) in dag}
        dag_s = {(f"N{a}", f"N{b}") for (a, b) in dag}
        arms = set()
        for (pair, z) in _unshielded_colliders(dag_s, skel, nodes):
            for x in pair:
                arms.add((x, z))
        undirected = [tuple(sorted(tuple(p))) for p in skel
                      if not ({(tuple(p)[0], tuple(p)[1]), (tuple(p)[1], tuple(p)[0])} & arms)]

        all_pairs = [tuple(sorted((f"N{i}", f"N{j}")))
                     for i in range(n) for j in range(i + 1, n)]
        # random start-time base drawn from ALL pairs (some adjacent, some not)
        base_adj = [p for p in all_pairs if rng.random() < 0.15]
        base_abs = [p for p in all_pairs if rng.random() < 0.15 and p not in base_adj]
        s = start_orientation_session(nodes, directed=list(arms), undirected=undirected,
                                      asserted_adjacencies=base_adj,
                                      asserted_absences=base_abs)
        verify_orientation_session(session_to_dict(s))

        # ordered history of (pair, direction|None, adjacency|None), for the oracle
        history = []
        for _round in range(3):
            k = int(rng.integers(1, len(all_pairs) + 1))
            idx = rng.choice(len(all_pairs), size=k, replace=False)
            batch = []
            for j in idx:
                a, b = all_pairs[j]
                roll = rng.random()
                if roll < 0.30 and frozenset((a, b)) in skel:
                    batch.append({"direction": [a, b], "source": "human"})
                    history.append(((a, b), (a, b), None))
                elif roll < 0.45 and frozenset((a, b)) in skel:
                    batch.append({"direction": [b, a], "source": "llm_proposal"})
                    history.append(((a, b), (b, a), None))
                elif roll < 0.65:
                    batch.append({"edge": [a, b], "adjacency": "present"})
                    history.append(((a, b), None, "present"))
                elif roll < 0.85:
                    batch.append({"edge": [a, b], "adjacency": "absent"})
                    history.append(((a, b), None, "absent"))
                else:
                    batch.append({"edge": [a, b], "direction": None})
                    history.append(((a, b), None, None))
            s = ingest_orientation_answers(s, batch)
            verify_orientation_session(session_to_dict(s))

            # INDEPENDENT latest-wins projection from base + history
            latest = {}
            for (e, d, adj) in history:
                latest[e] = (d, adj)
            answered = set(latest)
            adj_answers = {e for e, (d, adj) in latest.items() if adj == "present"}
            abs_answers = {e for e, (d, adj) in latest.items() if adj == "absent"}
            base_adj_set = {tuple(sorted(p)) for p in base_adj}
            base_abs_set = {tuple(sorted(p)) for p in base_abs}
            eff_adj = {p for p in base_adj_set if p not in answered} | adj_answers
            eff_abs = {p for p in base_abs_set if p not in answered} | abs_answers
            assert set(s.result.asserted_adjacencies) == eff_adj
            assert set(s.result.asserted_absences) == eff_abs

            # deferred = latest-unknown pairs still among the remaining edges
            remaining = set(s.result.remaining_undirected)
            unknown_latest = {e for e, (d, adj) in latest.items()
                              if d is None and adj is None}
            assert set(s.deferred) == {e for e in unknown_latest if e in remaining}
        ran += 1
    assert ran >= 40, f"too few usable trials ({ran})"
