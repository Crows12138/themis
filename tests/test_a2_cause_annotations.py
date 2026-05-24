"""Slice A2: CauseStatement annotations (provenance + confidence).

Symmetric completion of the annotation channel — ObservationStatement
and ProbabilityStatement already carried ``annotations``; this slice
brings CauseStatement inline so edges can be tagged as llm_proposal
vs evidence-backed without touching reasoning rules.

Pins:
- Schema accepts cause statements with annotations
- Semantic validator threads annotations into the typed Program
- Instantiation preserves annotations across forall expansion
- Reasoning still works (annotations never influence any rule)
"""
from __future__ import annotations

import json

import pytest

import themis
from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.runtime.instantiation import instantiate
from themis.types import (
    Annotation,
    Atom,
    CauseStatement,
    ConstTerm,
    Program,
    VarTerm,
)


def _ast_with_annotated_cause(source: str = "llm_proposal",
                                confidence: float | None = None) -> dict:
    ann: dict = {"source": source}
    if confidence is not None:
        ann["confidence"] = confidence
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": ann,
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "running",
                             "args": [{"type": "const", "name": "me"}]},
                    "to": {"predicate": "belly_fat_loss",
                           "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }


# ================================================================= schema

def test_schema_accepts_cause_with_annotations():
    ast = _ast_with_annotated_cause(source="llm_proposal")
    validate_ast(ast)  # must not raise


def test_schema_accepts_cause_with_confidence_only():
    ast = _ast_with_annotated_cause(source="PubMed:12345", confidence=0.85)
    validate_ast(ast)


def test_schema_rejects_cause_annotations_with_unknown_fields():
    ast = _ast_with_annotated_cause()
    ast["statements"][2]["annotations"]["invented_field"] = "x"
    with pytest.raises(SyntacticError):
        validate_ast(ast)


# =============================================================== validator

def test_validator_threads_annotations_into_typed_cause_statement():
    ast = _ast_with_annotated_cause(source="llm_proposal", confidence=0.6)
    prog = validate_program(validate_ast(ast))
    causes = [s for s in prog.statements if isinstance(s, CauseStatement)]
    assert len(causes) == 1
    assert causes[0].annotations is not None
    assert causes[0].annotations.source == "llm_proposal"
    assert causes[0].annotations.confidence == 0.6


def test_validator_leaves_annotations_none_when_absent():
    """Back-compat: every pre-A2 program with no ``annotations`` on its
    cause statements must still land as ``annotations=None``."""
    ast = _ast_with_annotated_cause()
    del ast["statements"][2]["annotations"]
    prog = validate_program(validate_ast(ast))
    causes = [s for s in prog.statements if isinstance(s, CauseStatement)]
    assert causes[0].annotations is None


# ============================================================ instantiation

def test_instantiation_preserves_annotations_across_forall_expansion():
    """``forall`` on a cause statement unrolls per-object — each ground
    copy must carry the original annotation, not drop it."""
    x_arg = (VarTerm(name="X"),)
    running_var = Atom(predicate="running", args=x_arg)
    belly_var = Atom(predicate="belly_fat_loss", args=x_arg)
    prog = Program(
        version="0.1",
        objects=("alice", "bob"),
        statements=(
            CauseStatement(
                from_atom=running_var,
                to_atom=belly_var,
                forall=("X",),
                annotations=Annotation(source="llm_proposal"),
            ),
        ),
    )
    ground = instantiate(prog)
    assert len(ground) == 2
    for s in ground:
        assert isinstance(s, CauseStatement)
        assert s.annotations is not None
        assert s.annotations.source == "llm_proposal"
        assert s.forall == ()


# ================================================================== run()

def test_themis_run_accepts_annotated_cause_and_reasons_identically():
    """Annotations are inert to reasoning — status, structural_result,
    and derivation are identical with vs without the annotation.
    ``data_gap_report``, ``explanation``, and (Fix 3+4 v0.1.5)
    ``extensions.llm_proposed_review`` deliberately differ: the
    proposal-edge disclosure is the whole point of provenance, and
    the audit channels are the kernel-side guarantee that the
    disclosure surfaces. Covered separately in
    test_unverified_proposal_edge_* (data_gap_report) and
    test_llm_proposed_review_* (Fix 3+4 review surface).
    """
    ast_with = _ast_with_annotated_cause(source="llm_proposal")
    ast_plain = _ast_with_annotated_cause()
    del ast_plain["statements"][2]["annotations"]

    r_with = themis.run(ast_with)["results"][0]
    r_plain = themis.run(ast_plain)["results"][0]

    # Reasoning fields must match exactly — no rule reads annotations.
    # extensions is EXCLUDED here because Fix 3+4 §3.2 adds
    # llm_proposed_review when the source contains "llm" (the whole
    # point of provenance disclosure). Other extension sub-fields are
    # checked individually below to keep the rest of the contract.
    for field in ("status", "query_kind", "query_id", "structural_result",
                  "derivation", "missing_information",
                  "investigation_requests", "framing_notes",
                  "confidence", "numeric_result"):
        assert r_with.get(field) == r_plain.get(field), field
    assert r_with["query_kind"] == "cause"
    assert r_with["status"] == "structurally_solved"

    # Fix 3+4 §3.2: the annotated-llm version surfaces the review;
    # the plain version doesn't (no llm-tagged elements to disclose).
    assert "llm_proposed_review" in (r_with.get("extensions") or {})
    assert "llm_proposed_review" not in (r_plain.get("extensions") or {})


def test_instantiation_lifts_annotation_from_forall_cause_into_every_ground_copy():
    """End-to-end through themis.run with a forall cause edge carrying an
    annotation — validates that the JSON input path threads annotations
    through parse -> validate -> instantiate without loss."""
    ast = {
        "version": "0.1",
        "domain": {
            "objects": [
                {"kind": "object", "name": "alice"},
                {"kind": "object", "name": "bob"},
            ]
        },
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "running",
                         "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "var", "name": "X"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q_alice",
                "query": {
                    "kind": "cause",
                    "from": {"predicate": "running",
                             "args": [{"type": "const", "name": "alice"}]},
                    "to": {"predicate": "belly_fat_loss",
                           "args": [{"type": "const", "name": "alice"}]},
                },
            },
        ],
    }
    # Validate via typed pipeline so we can inspect typed Program
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    ground_causes = [s for s in ground if isinstance(s, CauseStatement)]
    # alice + bob = 2 ground edges
    assert len(ground_causes) == 2
    for gc in ground_causes:
        assert gc.annotations is not None
        assert gc.annotations.source == "llm_proposal"

    # End-to-end still runs cleanly.
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


# ====================================== unverified-proposal-edge data gap


def test_unverified_proposal_edge_emits_informational_gap():
    """Real-test caught: rendering layer was the *only* place that read
    `annotations.source = "llm_proposal"` — if the downstream LLM forgot
    to walk `program.statements`, the user got an answer that looked
    independently verified but was actually a self-replay of the LLM's
    own assumption. The gap report now surfaces this as INFORMATIONAL so
    disclosure has a structured signal, not a textual hint."""
    ast = _ast_with_annotated_cause(source="llm_proposal")
    out = themis.run(ast)
    result = out["results"][0]
    report = result["data_gap_report"]
    kinds = [g["kind"] for g in report["gaps"]]
    assert "unverified_proposal_edge_on_query_path" in kinds

    proposal_gap = next(
        g for g in report["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    )
    assert proposal_gap["severity"] == "informational"
    # Description names the actual edge, not a placeholder.
    assert "running" in proposal_gap["description"]
    assert "belly_fat_loss" in proposal_gap["description"]

    # Geometric guarantee: the disclosure also lands in ``explanation``
    # so a renderer that skips data_gap_report still cannot drop it.
    assert result.get("explanation") is not None
    assert "running" in result["explanation"]
    assert "belly_fat_loss" in result["explanation"]
    assert "llm_proposal" in result["explanation"]


def test_evidence_backed_edge_does_not_emit_proposal_gap():
    """Companion: edges with a concrete citation (PubMed:..., DOI:...)
    or no annotation at all must not trigger the proposal-edge gap —
    that would muddy the signal and produce false alarms."""
    ast_cite = _ast_with_annotated_cause(source="PubMed:12345")
    ast_plain = _ast_with_annotated_cause()
    del ast_plain["statements"][2]["annotations"]

    for ast in (ast_cite, ast_plain):
        out = themis.run(ast)
        report = out["results"][0].get("data_gap_report")
        kinds = [g["kind"] for g in (report["gaps"] if report else ())]
        assert "unverified_proposal_edge_on_query_path" not in kinds


def test_unverified_proposal_edge_flags_effect_query_via_dag_walk():
    """Effect / identify queries do not expose ``supporting_paths``;
    proposal-edge detection has to walk the program-derived DAG between
    query-relevant predicates instead. Pin: an effect query whose only
    causal pathway is an llm_proposal edge produces the same gap as the
    cause-query case."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "running",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "belly_fat_loss",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert result["query_kind"] == "effect"
    report = result["data_gap_report"]
    kinds = [g["kind"] for g in report["gaps"]]
    assert "unverified_proposal_edge_on_query_path" in kinds


def test_unverified_proposal_edge_flags_mediator_chain():
    """Mediation pathway: X -> M -> Y. Both edges llm_proposal — both
    should be flagged. Mediator predicate enters the relevant set so the
    DFS picks up X→M and M→Y separately."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {"predicate": "x",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "m",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "cause",
                "from": {"predicate": "m",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "y",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "x",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "y",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                    "mediator": {"predicate": "m",
                                 "args": [{"type": "const", "name": "me"}]},
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    report = result["data_gap_report"]
    proposal_gaps = [
        g for g in report["gaps"]
        if g["kind"] == "unverified_proposal_edge_on_query_path"
    ]
    assert len(proposal_gaps) == 2
    descriptions = " ".join(g["description"] for g in proposal_gaps)
    assert "x" in descriptions and "m" in descriptions and "y" in descriptions
