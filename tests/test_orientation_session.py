"""Phase 3 — the interactive orientation-resolution loop and its verifier. A
session is event-sourced (input CPDAG + ordered answers); the verifier delegates
the embedded Phase 1 / Phase 2 artifacts to their own auditors and independently
re-derives the session glue (constraints, deferred, source trail, status) from
the answers. The property test drives random answer sequences and asserts the
verifier accepts and the invariants hold.
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


# --- the loop -----------------------------------------------------------------

def test_one_answer_cascades_to_resolved():
    # undirected chain A-B-C-D; answering A->B forces B->C then C->D (R1 twice),
    # resolving the whole chain in one step.
    s0 = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")],
    )
    assert s0.status == "open"
    verify_orientation_session(session_to_dict(s0))

    s1 = ingest_orientation_answers(s0, [{"direction": ["A", "B"], "source": "human"}])
    assert set(s1.result.oriented) == {("A", "B"), ("B", "C"), ("C", "D")}
    assert s1.status == "resolved"
    assert not s1.deferred
    # the single answer entailed the two propagated edges (its blast radius)
    entry = next(e for e in s1.source_trail if e["direction"] == ["A", "B"])
    assert sorted(map(tuple, entry["entails"])) == [("B", "C"), ("C", "D")]
    verify_orientation_session(session_to_dict(s1))


def test_unknown_escape_blocks_rather_than_guesses():
    # two independent single-edge components; declining both leaves nothing to ask
    s = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("C", "D")],
    )
    s = ingest_orientation_answers(s, [
        {"edge": ["A", "B"], "direction": None, "source": "llm_proposal"},
        {"edge": ["C", "D"], "direction": None, "source": "llm_proposal"},
    ])
    assert set(s.deferred) == {("A", "B"), ("C", "D")}
    assert s.status == "blocked"
    assert next_questions(s) == ()   # deferred edges are not re-asked
    verify_orientation_session(session_to_dict(s))


def test_conflict_answer_is_rejected_not_applied():
    # data collider A->C<-B ; answering C->A contradicts it
    s = start_orientation_session(
        ["A", "B", "C"], directed=[("A", "C"), ("B", "C")],
    )
    s = ingest_orientation_answers(s, [{"direction": ["C", "A"], "source": "llm_proposal"}])
    assert ("A", "C") in s.result.oriented and ("C", "A") not in s.result.oriented
    assert [r["direction"] for r in s.rejected] == [["C", "A"]]
    assert not s.source_trail                       # nothing was applied
    assert s.status == "open"                        # the conflict is pending
    assert any(q.kind == "conflict" for q in next_questions(s))
    verify_orientation_session(session_to_dict(s))


def test_cyclic_answers_surface_as_conflict_in_the_loop():
    # triangle; answering A->B, B->C, then C->A closes a cycle — the loop rejects
    # the cycle-closing answer and surfaces it rather than building a cyclic graph
    s = start_orientation_session(
        ["A", "B", "C"], undirected=[("A", "B"), ("B", "C"), ("A", "C")],
    )
    s = ingest_orientation_answers(s, [
        {"direction": ["A", "B"], "source": "human"},
        {"direction": ["B", "C"], "source": "human"},
        {"direction": ["C", "A"], "source": "human"},
    ])
    assert [r["direction"] for r in s.rejected] == [["C", "A"]]
    assert any(r["reason"] == "creates_cycle" for r in s.rejected)
    assert ("A", "C") in s.result.oriented and ("C", "A") not in s.result.oriented
    assert any(q.reason == "creates_cycle" for q in next_questions(s) if q.kind == "conflict")
    verify_orientation_session(session_to_dict(s))


def test_revision_unknown_then_direction_latest_wins():
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"edge": ["A", "B"], "direction": None}])
    assert ("A", "B") in s.deferred
    # human comes back and orients it
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"], "source": "human"}])
    assert not s.deferred
    assert ("A", "B") in s.result.oriented and ("B", "C") in s.result.oriented
    assert s.constraints == (("A", "B"),)            # only the latest, directional
    assert s.status == "resolved"
    verify_orientation_session(session_to_dict(s))


def test_revision_overrides_earlier_direction():
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"]}])
    s = ingest_orientation_answers(s, [{"direction": ["B", "A"]}])  # changed mind
    assert s.constraints == (("B", "A"),)
    assert ("B", "A") in s.result.oriented
    verify_orientation_session(session_to_dict(s))


def test_ill_formed_answer_raises():
    s = start_orientation_session(["A", "B"], undirected=[("A", "B")])
    with pytest.raises(OrientationSessionError):
        ingest_orientation_answers(s, [{"direction": ["A", "Z"]}])  # unknown node
    with pytest.raises(OrientationSessionError):
        ingest_orientation_answers(s, [{"edge": ["A", "B"], "direction": ["A", "C"]}])


# --- verifier rejects tampering -----------------------------------------------

def _resolved_session_dict():
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"], "source": "human"}])
    return session_to_dict(s)


def test_verifier_rejects_stale_constraint():
    d = _resolved_session_dict()
    d["constraints"] = d["constraints"] + [["B", "C"]]  # a constraint not in answers
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_wrong_deferred():
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    d = session_to_dict(s)
    d["deferred"] = [["A", "B"]]  # claim deferred without an unknown answer
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_forged_source_trail_entailment():
    d = _resolved_session_dict()
    for e in d["source_trail"]:
        if e["direction"] == ["A", "B"]:
            e["entails"] = []  # hide B->C, the edge this answer actually forced
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_crediting_a_rejected_answer():
    # session where C->A was rejected; forge a trail entry crediting it
    s = start_orientation_session(["A", "B", "C"], directed=[("A", "C"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"direction": ["C", "A"], "source": "llm_proposal"}])
    d = session_to_dict(s)
    d["source_trail"] = [{"edge": ["A", "C"], "direction": ["C", "A"],
                          "source": "llm_proposal", "note": "", "entails": []}]
    d["rejected"] = []
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_wrong_status():
    d = _resolved_session_dict()
    d["status"] = "blocked"
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


def test_verifier_rejects_tampered_embedded_propagation():
    d = _resolved_session_dict()
    # corrupt the embedded Phase 1 closure — delegated verifier must catch it
    d["propagation"]["oriented"] = [["A", "B"]]
    with pytest.raises(VerificationError):
        verify_orientation_session(d)


# --- property test ------------------------------------------------------------

def _unshielded_colliders(directed, skel, nodes):
    cols = set()
    for z in nodes:
        parents = [x for x in nodes if (x, z) in directed]
        for x, y in itertools.combinations(parents, 2):
            if frozenset((x, y)) not in skel:
                cols.add((frozenset((x, y)), z))
    return cols


def test_random_answer_sequences_verify_and_hold_invariants():
    """Random small CPDAGs driven by random answer sequences (mix of directions
    and unknowns, with revisions): the verifier accepts every intermediate
    session, and the session invariants hold — constraints are latest-wins,
    deferred are exactly the still-open unknowns, resolved iff nothing remains."""
    rng = np.random.default_rng(20260717)
    ran = 0
    for _ in range(300):
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
        if not undirected:
            continue
        s = start_orientation_session(nodes, directed=list(arms), undirected=undirected)
        verify_orientation_session(session_to_dict(s))

        # a few rounds of random answers over the currently-remaining edges
        for _round in range(3):
            rem = list(s.result.remaining_undirected)
            if not rem:
                break
            k = int(rng.integers(1, len(rem) + 1))
            idx = rng.choice(len(rem), size=k, replace=False)
            batch = []
            for j in idx:
                a, b = rem[j]
                roll = rng.random()
                if roll < 0.4:
                    batch.append({"direction": [a, b], "source": "human"})
                elif roll < 0.8:
                    batch.append({"direction": [b, a], "source": "llm_proposal"})
                else:
                    batch.append({"edge": [a, b], "direction": None, "source": "human"})
            s = ingest_orientation_answers(s, batch)
            verify_orientation_session(session_to_dict(s))

            # invariants
            remaining = set(s.result.remaining_undirected)
            unknown_latest = {e for e in {a.edge for a in s.answers}
                              if [x for x in s.answers if x.edge == e][-1].direction is None}
            assert set(s.deferred) == {e for e in unknown_latest if e in remaining}
            if s.status == "resolved":
                assert not remaining and not any(q.kind == "conflict"
                                                 for q in s.question_set.questions)
        ran += 1
    assert ran >= 40, f"too few usable trials ({ran})"
