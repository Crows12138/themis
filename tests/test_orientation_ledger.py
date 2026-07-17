"""Phase 5 — wiring a resolved orientation session into the assumption ledger.

The export maps each oriented edge to the query-side provenance vocabulary, with
the ``llm_proposal`` taint propagated through the Meek closure (an edge FORCED
from an LLM-proposed answer is disclosed ``llm_proposal`` too). The verifier
delegates the embedded session to ``verify_orientation_session`` and independently
re-derives the taint classification. The integration tests prove the exported
cause statements, dropped into a program, fire ``unverified_proposal_edge_on_
query_path`` through the EXISTING data-gap machinery, unchanged.
"""
import copy

import pytest

import themis
from themis.estimation.orientation_ledger import orientation_ledger_export
from themis.estimation.orientation_session import (
    ingest_orientation_answers,
    start_orientation_session,
)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_ledger_rules import verify_orientation_ledger_export


def _sources(export):
    return {tuple(e["edge"]): e["source"] for e in export["edges"]}


# --- the taint-propagated source derivation -----------------------------------

def test_llm_proposal_taint_propagates_through_the_closure():
    # A->B answered (llm_proposal) forces B->C, C->D (R1). All three rest on the
    # LLM's guess, so all three must be disclosed llm_proposal.
    s = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")])
    s = ingest_orientation_answers(
        s, [{"direction": ["A", "B"], "source": "llm_proposal"}])
    export = orientation_ledger_export(s)
    assert _sources(export) == {("A", "B"): "llm_proposal", ("B", "C"): "llm_proposal",
                                ("C", "D"): "llm_proposal"}
    assert sorted(map(tuple, export["proposal_edges"])) == [
        ("A", "B"), ("B", "C"), ("C", "D")]
    assert export["graph_learned_from_data"] is False
    verify_orientation_ledger_export(export)
    themis.verify_orientation_ledger_export(export)   # public entry


def test_human_answer_is_trusted_no_proposal():
    s = start_orientation_session(["A", "B", "C"], undirected=[("A", "B"), ("B", "C")])
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"], "source": "human"}])
    export = orientation_ledger_export(s)
    assert all(v == "human" for v in _sources(export).values())
    assert export["proposal_edges"] == []
    verify_orientation_ledger_export(export)


def test_data_colliders_are_discovery_sourced_and_flag_learned():
    s = start_orientation_session(
        ["A", "B", "C", "X", "Y"], directed=[("A", "C"), ("B", "C")],
        undirected=[("X", "Y")])
    s = ingest_orientation_answers(
        s, [{"direction": ["X", "Y"], "source": "llm_proposal"}])
    export = orientation_ledger_export(s, data_source="discovery:pc")
    src = _sources(export)
    assert src[("A", "C")] == "discovery:pc" and src[("B", "C")] == "discovery:pc"
    assert src[("X", "Y")] == "llm_proposal"
    assert export["graph_learned_from_data"] is True
    verify_orientation_ledger_export(export)


def test_weakest_root_wins_on_a_multi_root_edge():
    # kite: a->b is R3-forced from z1->b and z2->b. One root is llm_proposal, the
    # other human — the forced edge inherits the weaker (llm_proposal).
    s = start_orientation_session(
        ["a", "b", "z1", "z2"],
        undirected=[("a", "b"), ("a", "z1"), ("a", "z2"), ("z1", "b"), ("z2", "b")])
    s = ingest_orientation_answers(s, [
        {"direction": ["z1", "b"], "source": "llm_proposal"},
        {"direction": ["z2", "b"], "source": "human"},
    ])
    export = orientation_ledger_export(s)
    src = _sources(export)
    assert src[("a", "b")] == "llm_proposal"      # weakest root wins
    assert src[("z1", "b")] == "llm_proposal" and src[("z2", "b")] == "human"
    verify_orientation_ledger_export(export)


def test_multiple_trusted_roots_collapse_to_one_marker():
    s = start_orientation_session(
        ["a", "b", "z1", "z2"],
        undirected=[("a", "b"), ("a", "z1"), ("a", "z2"), ("z1", "b"), ("z2", "b")])
    s = ingest_orientation_answers(s, [
        {"direction": ["z1", "b"], "source": "human"},
        {"direction": ["z2", "b"], "source": "temporal_order"},
    ])
    export = orientation_ledger_export(s)
    assert _sources(export)[("a", "b")] == "orientation_multiple"
    assert export["proposal_edges"] == []          # trusted → no gap
    verify_orientation_ledger_export(export)


def test_data_source_must_be_a_discovery_marker():
    s = start_orientation_session(["A", "B"], undirected=[("A", "B")])
    s = ingest_orientation_answers(s, [{"direction": ["A", "B"], "source": "human"}])
    with pytest.raises(ValueError):
        orientation_ledger_export(s, data_source="made_up")


# --- verifier rejects tampering -----------------------------------------------

def _tainted_export():
    s = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")])
    s = ingest_orientation_answers(
        s, [{"direction": ["A", "B"], "source": "llm_proposal"}])
    return orientation_ledger_export(s)


def test_verifier_rejects_under_disclosed_proposal_edge():
    d = _tainted_export()
    for e in d["edges"]:
        if tuple(e["edge"]) == ("B", "C"):
            e["source"] = "human"          # hide that it rests on the LLM's guess
    for st in d["cause_statements"]:
        if (st["from"]["predicate"], st["to"]["predicate"]) == ("B", "C"):
            st["annotations"]["source"] = "human"
    d["proposal_edges"] = [["A", "B"], ["C", "D"]]
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


def test_verifier_rejects_forged_proposal_edge_list():
    d = _tainted_export()
    d["proposal_edges"] = [["A", "B"]]     # drop two that are genuinely tainted
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


def test_verifier_rejects_cause_statement_source_mismatch():
    d = _tainted_export()
    d["cause_statements"][0]["annotations"]["source"] = "PubMed:12345"
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


def test_verifier_rejects_wrong_graph_learned_flag():
    d = _tainted_export()
    d["graph_learned_from_data"] = True    # there are no data colliders here
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


def test_verifier_rejects_bad_data_source():
    d = _tainted_export()
    d["data_source"] = "evidence"
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


def test_verifier_rejects_tampered_embedded_session():
    d = _tainted_export()
    d["session"]["propagation"]["oriented"] = [["A", "B"]]  # delegated verifier catches
    with pytest.raises(VerificationError):
        verify_orientation_ledger_export(d)


# --- end-to-end wiring through the real gap machinery -------------------------

def _program(export, nodes, x, y):
    sub = [{"type": "const", "name": "me"}]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": (
            [{"kind": "variable", "predicate": n, "domain": [True, False]}
             for n in nodes]
            + export["cause_statements"]
            + [{
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": {"predicate": x, "args": sub}, "value": True},
                    "target": {"atom": {"predicate": y, "args": sub}, "value": True},
                    "given": [],
                },
            }]
        ),
    }


def test_exported_proposal_edges_fire_the_existing_gap_and_ledger():
    s = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")])
    s = ingest_orientation_answers(
        s, [{"direction": ["A", "B"], "source": "llm_proposal"}])
    export = orientation_ledger_export(s, subjects=("me",))
    out = themis.run(_program(export, ["A", "B", "C", "D"], "A", "D"))
    result = out["results"][0]
    kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    assert "unverified_proposal_edge_on_query_path" in kinds
    ledger = (result.get("extensions") or {}).get("assumption_ledger")
    assert ledger is not None
    edge_claims = [a for a in ledger["assumptions"] if a["layer"] == "structural_edge"]
    assert edge_claims, "the taint-propagated proposal edges must reach the ledger"


def test_human_resolved_graph_fires_no_proposal_gap():
    s = start_orientation_session(
        ["A", "B", "C", "D"], undirected=[("A", "B"), ("B", "C"), ("C", "D")])
    s = ingest_orientation_answers(
        s, [{"direction": ["A", "B"], "source": "human"}])
    export = orientation_ledger_export(s, subjects=("me",))
    out = themis.run(_program(export, ["A", "B", "C", "D"], "A", "D"))
    result = out["results"][0]
    kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    assert "unverified_proposal_edge_on_query_path" not in kinds
