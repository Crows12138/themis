"""Phase 4 slice: narrative edge-merge tests.

Symmetric to ``test_narrative_merge.py``: covers
``merge_edge_extractions`` (combine multiple A2 outputs) and
``merge_edges_into_program`` (inject narrative-extracted edges into
a kernel_ast). Pure JSON-in / JSON-out; no typed Program, no LLM.
"""
from __future__ import annotations

import pytest

import themis
from themis.upstream import (
    ExtractionShapeError,
    MergeConflictError,
    merge_edge_extractions,
    merge_edges_into_program,
)


# ======================================================= helpers


def _cause(src: str, dst: str, evidence: str | None = None) -> dict:
    e = {
        "kind": "cause",
        "from": {"predicate": src},
        "to": {"predicate": dst},
        "annotations": {"source": "narrative_proposal"},
    }
    if evidence:
        e["annotations"]["evidence"] = evidence
    return e


def _bidir(a: str, b: str, evidence: str | None = None) -> dict:
    e = {
        "kind": "bidirected",
        "left": {"predicate": a},
        "right": {"predicate": b},
        "annotations": {"source": "narrative_proposal"},
    }
    if evidence:
        e["annotations"]["evidence"] = evidence
    return e


def _refusal(src: str, dst: str, reason: str) -> dict:
    return {
        "kind": "refuse_direct_edge",
        "from": src,
        "to": dst,
        "reason": reason,
    }


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _empty_program(predicates) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in predicates
        ],
    }


# ======================================================= merge_edge_extractions


def test_merge_zero_extractions_returns_empty():
    out = merge_edge_extractions()
    assert out == {"edges": [], "refusals": [], "narrative_ambiguities": []}


def test_merge_single_passthrough():
    a = {
        "edges": [_cause("x", "y", "evidence text")],
        "refusals": [],
        "narrative_ambiguities": [],
    }
    out = merge_edge_extractions(a)
    assert len(out["edges"]) == 1
    assert out["edges"][0]["from"]["predicate"] == "x"
    assert out["edges"][0]["annotations"]["evidence"] == "evidence text"


def test_merge_dedups_same_cause_combines_evidence():
    a = {"edges": [_cause("x", "y", "段落 A 证据")]}
    b = {"edges": [_cause("x", "y", "段落 B 证据")]}
    out = merge_edge_extractions(a, b)
    assert len(out["edges"]) == 1
    ev = out["edges"][0]["annotations"]["evidence"]
    assert isinstance(ev, list)
    assert "段落 A 证据" in ev and "段落 B 证据" in ev


def test_merge_dedups_same_evidence_string_kept_once():
    a = {"edges": [_cause("x", "y", "same")]}
    b = {"edges": [_cause("x", "y", "same")]}
    out = merge_edge_extractions(a, b)
    assert out["edges"][0]["annotations"]["evidence"] == "same"


def test_merge_bidirected_pair_is_unordered():
    a = {"edges": [_bidir("x", "y")]}
    b = {"edges": [_bidir("y", "x")]}
    out = merge_edge_extractions(a, b)
    assert len(out["edges"]) == 1


def test_merge_cross_kind_conflict_raises():
    a = {"edges": [_cause("x", "y")]}
    b = {"edges": [_bidir("x", "y")]}
    with pytest.raises(MergeConflictError, match="kind conflict"):
        merge_edge_extractions(a, b)


def test_merge_cause_vs_refusal_conflict_raises():
    a = {"edges": [_cause("x", "y")]}
    b = {"edges": [], "refusals": [_refusal("x", "y", "looks like confounder")]}
    with pytest.raises(MergeConflictError, match="kind conflict"):
        merge_edge_extractions(a, b)


def test_merge_concrete_citation_beats_narrative_proposal():
    a = {"edges": [{
        "kind": "cause",
        "from": {"predicate": "x"},
        "to": {"predicate": "y"},
        "annotations": {"source": "PubMed:12345", "evidence": "RCT"},
    }]}
    b = {"edges": [_cause("x", "y", "narrative")]}
    out = merge_edge_extractions(a, b)
    assert out["edges"][0]["annotations"]["source"] == "PubMed:12345"


def test_merge_refusals_dedup_by_pair():
    a = {"edges": [], "refusals": [_refusal("x", "y", "first")]}
    b = {"edges": [], "refusals": [_refusal("x", "y", "second")]}
    out = merge_edge_extractions(a, b)
    assert len(out["refusals"]) == 1
    # First wins; we don't try to combine reasons.
    assert out["refusals"][0]["reason"] == "first"


def test_merge_concatenates_narrative_ambiguities():
    a = {"edges": [], "narrative_ambiguities": [{"kind": "temporal", "description": "A"}]}
    b = {"edges": [], "narrative_ambiguities": [{"kind": "scope", "description": "B"}]}
    out = merge_edge_extractions(a, b)
    assert len(out["narrative_ambiguities"]) == 2


def test_merge_shape_validation_rejects_bad_edge():
    bad = {"edges": [{"kind": "cause", "from": {"predicate": "x"}}]}  # missing 'to'
    with pytest.raises(ExtractionShapeError):
        merge_edge_extractions(bad)


def test_merge_shape_validation_rejects_unknown_kind():
    bad = {"edges": [{"kind": "wishful", "from": {"predicate": "x"}, "to": {"predicate": "y"}}]}
    with pytest.raises(ExtractionShapeError, match="cause.*bidirected"):
        merge_edge_extractions(bad)


# ======================================================= merge_edges_into_program


def test_merge_into_program_inserts_cause_with_args():
    prog = _empty_program(["x", "y"])
    extraction = {"edges": [_cause("x", "y", "narrative says so")]}
    out = merge_edges_into_program(prog, extraction)
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # Atom args should be filled with [{type:const, name:me}] per A2 contract
    assert causes[0]["from"]["args"] == [{"type": "const", "name": "me"}]
    assert causes[0]["to"]["args"] == [{"type": "const", "name": "me"}]
    assert causes[0]["annotations"]["evidence"] == "narrative says so"


def test_merge_into_program_skips_existing_pair():
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "cause", "from": _atom("x"), "to": _atom("y"),
        "annotations": {"source": "manual"},
    })
    extraction = {"edges": [_cause("x", "y", "narrative")]}
    out = merge_edges_into_program(prog, extraction)
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # Existing wins on annotations
    assert causes[0]["annotations"]["source"] == "manual"


def test_merge_into_program_cross_kind_conflict_with_existing():
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "cause", "from": _atom("x"), "to": _atom("y"),
    })
    extraction = {"edges": [_bidir("x", "y")]}
    with pytest.raises(MergeConflictError, match="cause.*bidirected"):
        merge_edges_into_program(prog, extraction)


def test_merge_into_program_inserts_bidirected_with_args():
    prog = _empty_program(["x", "y"])
    extraction = {"edges": [_bidir("x", "y", "shared latent trait")]}
    out = merge_edges_into_program(prog, extraction)
    bs = [s for s in out["statements"] if s.get("kind") == "bidirected"]
    assert len(bs) == 1
    assert bs[0]["left"]["args"] == [{"type": "const", "name": "me"}]
    assert bs[0]["right"]["args"] == [{"type": "const", "name": "me"}]


def test_merge_into_program_does_not_mutate_input():
    prog = _empty_program(["x", "y"])
    original = dict(prog)
    original_statements = list(prog["statements"])
    extraction = {"edges": [_cause("x", "y")]}
    merge_edges_into_program(prog, extraction)
    assert prog["statements"] == original_statements


def test_end_to_end_program_runs_after_edge_merge():
    """Sanity: a program with merged narrative edges still parses + runs."""
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "assoc",
            "left": _atom("x"),
            "right": _atom("y"),
            "given": [],
        },
    })
    extraction = {"edges": [_cause("x", "y", "narrative evidence")]}
    merged = merge_edges_into_program(prog, extraction)
    out = themis.run(merged)
    assert "results" in out
    assert out["results"][0].get("status")
