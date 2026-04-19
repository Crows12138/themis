"""End-to-end test for slice 1: cause vertical.

Input:  minimal_example_v0_1.json
Target: query ``q_cause_1`` — does smokes(alice) cause cancer(alice)?
Expected: structurally_solved, value True, supporting path
          smokes(alice) -> tar(alice) -> cancer(alice).
"""
from __future__ import annotations

from pathlib import Path

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast, validate_result
from themis.output.explainer import explain
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch
from themis.types import (
    QueryKind,
    QueryStatement,
    ResultStatus,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = PROJECT_ROOT / "minimal_example_v0_1.json"


def _find_query(program, query_id: str) -> QueryStatement:
    for stmt in program.statements:
        if isinstance(stmt, QueryStatement) and stmt.id == query_id:
            return stmt
    raise AssertionError(f"query {query_id!r} not found in program")


def test_q_cause_1_end_to_end() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")

    ast = parse_json(source)
    validate_ast(ast)
    program = validate_program(ast)

    ground = instantiate(program)
    graph = project(ground)

    stmt = _find_query(program, "q_cause_1")
    result = dispatch(program, stmt, graph)

    assert result.status is ResultStatus.STRUCTURALLY_SOLVED
    assert result.query_kind is QueryKind.CAUSE
    assert result.query_id == "q_cause_1"
    assert result.structural_result is not None
    assert result.structural_result.value is True

    paths = result.structural_result.supporting_paths
    assert paths == (("smokes(alice)", "tar(alice)", "cancer(alice)"),)


def test_q_cause_1_serializes_and_validates() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    program = validate_program(validate_ast(parse_json(source)))
    graph = project(instantiate(program))
    stmt = _find_query(program, "q_cause_1")
    result = dispatch(program, stmt, graph)

    payload = to_dict(result)
    # Round-trip through the query_result JSON Schema to ensure the
    # serialized shape is conformant.
    validate_result(payload)

    assert payload["status"] == "structurally_solved"
    assert payload["query_kind"] == "cause"
    assert payload["query_id"] == "q_cause_1"
    assert payload["structural_result"]["value"] is True
    assert payload["structural_result"]["supporting_paths"] == [
        ["smokes(alice)", "tar(alice)", "cancer(alice)"]
    ]


def test_q_cause_1_explanation_mentions_path() -> None:
    source = EXAMPLE.read_text(encoding="utf-8")
    program = validate_program(validate_ast(parse_json(source)))
    graph = project(instantiate(program))
    stmt = _find_query(program, "q_cause_1")
    result = dispatch(program, stmt, graph)

    text = explain(result)
    assert "smokes(alice) -> tar(alice) -> cancer(alice)" in text
    assert "因果影响" in text
