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
    """Annotations are metadata — a program with vs without an annotation
    on the same edge must produce identical reasoning output (only the
    typed Program differs, not the result)."""
    ast_with = _ast_with_annotated_cause(source="llm_proposal")
    ast_plain = _ast_with_annotated_cause()
    del ast_plain["statements"][2]["annotations"]

    out_with = themis.run(ast_with)
    out_plain = themis.run(ast_plain)

    # The reasoning result (value, explanation, everything the kernel
    # produces) must be identical — annotations never influence any rule.
    # Compare results[] only; the program echo naturally differs because
    # one program carries the annotation and the other doesn't.
    assert out_with["results"] == out_plain["results"]
    # Sanity: the reasoning actually produced a structurally_solved answer.
    r = out_with["results"][0]
    assert r["query_kind"] == "cause"
    assert r["status"] == "structurally_solved"


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
