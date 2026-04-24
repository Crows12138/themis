"""Phase 5 §T / S.T.5: kernel e2e for eval Case 14 (F11 temporal).

This is intentionally a kernel-only test. The narrative/prompt layer
still belongs to S.T.6; here we pin that once the AST carries
time-indexed atoms directly, the existing end-to-end cause vertical
answers the case without flattening away the lag.
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
from themis.types import QueryKind, QueryStatement, ResultStatus

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "temporal_late_night_tired.json"
)


def _find_query(program, query_id: str) -> QueryStatement:
    for stmt in program.statements:
        if isinstance(stmt, QueryStatement) and stmt.id == query_id:
            return stmt
    raise AssertionError(f"query {query_id!r} not found")


def test_case_14_temporal_runs_end_to_end() -> None:
    program = validate_program(validate_ast(parse_json(FIXTURE.read_text("utf-8"))))
    graph = project(instantiate(program))
    stmt = _find_query(program, "q_case_14_temporal")
    result = dispatch(program, stmt, graph)

    assert result.status is ResultStatus.STRUCTURALLY_SOLVED
    assert result.query_kind is QueryKind.CAUSE
    assert result.structural_result is not None
    assert result.structural_result.value is True
    assert result.structural_result.supporting_paths == (
        ("stays_up_late(me)@t-1", "feels_tired_next_morning(me)@t"),
    )


def test_case_14_temporal_result_validates_and_explains_lag() -> None:
    program = validate_program(validate_ast(parse_json(FIXTURE.read_text("utf-8"))))
    graph = project(instantiate(program))
    stmt = _find_query(program, "q_case_14_temporal")
    result = dispatch(program, stmt, graph)

    payload = to_dict(result)
    validate_result(payload)
    assert payload["query_kind"] == "cause"
    assert payload["structural_result"]["supporting_paths"] == [
        ["stays_up_late(me)@t-1", "feels_tired_next_morning(me)@t"]
    ]

    text = explain(result)
    assert "stays_up_late(me)@t-1 -> feels_tired_next_morning(me)@t" in text
    assert "因果影响" in text
