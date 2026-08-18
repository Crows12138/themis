"""Slice A0 e2e: advisory framing surfaces on an underspecified query.

The fixture reuses exercise_waist_complete's numeric content but adds
three VariableDeclarations:

- ``waist_reduced``: declared with only ``domain`` (outcome is the
  variable the user is sloppiest about — "reduced" is not a number).
- ``exercise_regular`` and ``diet_control``: fully declared.

The query is the same effect query as the complete fixture, so the
numeric verdict is unchanged (0.46, fully solved). The only new
surface is ``framing_notes``: waist_reduced should be flagged as
missing time_window / measurement / threshold / observability; the
other two predicates should be silent.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast, validate_result
from themis.output.explainer import explain
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import QueryStatement, ResultStatus

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "exercise_waist_underframed.json"
)


def _run():
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    return program, results, stmt_by_id


def test_numeric_verdict_unchanged_by_framing():
    """Framing is advisory: adding a VariableDeclaration must not move
    the numeric answer from the complete-fixture baseline (0.46)."""
    _, results, _ = _run()
    assert len(results) == 1
    r = results[0]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.numeric_result.value == pytest.approx(0.46)


def test_framing_notes_flag_underspecified_outcome():
    """waist_reduced is declared with only domain → note lists the
    remaining reportable fields (post-#41: 7 of them).
    exercise_regular / diet_control are fully declared → no notes."""
    _, results, _ = _run()
    r = results[0]
    notes = {n.predicate: set(n.missing) for n in r.framing_notes}
    assert "waist_reduced" in notes
    assert notes["waist_reduced"] == {
        "time_window", "measurement", "observability",
        "direction", "baseline", "state_vs_event",
    }
    assert "exercise_regular" not in notes
    assert "diet_control" not in notes


def test_explainer_surfaces_framing_clause():
    """The advisory should appear at the end of the explanation, after
    the numeric / confidence surface, so text-only readers see the
    framing gap."""
    _, results, stmt_by_id = _run()
    r = results[0]
    text = explain(r, stmt=stmt_by_id[r.query_id])
    # Numeric part still intact.
    assert "0.46" in text
    # Framing tail present.
    assert "问题定义" in text
    assert "waist_reduced" in text
    # The fields, in the reader's words. Pinning the identifiers here is
    # what let them reach the sentence as identifiers for as long as they
    # did — the clause named the field and never said what it was for.
    assert "时间窗" in text
    assert "测量方式" in text


def test_result_round_trips_through_schema():
    """framing_notes must serialize and schema-validate."""
    _, results, _ = _run()
    payload = to_dict(results[0])
    validate_result(payload)
    assert "framing_notes" in payload
    notes = payload["framing_notes"]
    assert len(notes) == 1
    assert notes[0]["predicate"] == "waist_reduced"
    assert set(notes[0]["missing"]) == {
        "time_window", "measurement", "observability",
        "direction", "baseline", "state_vs_event",
    }


def test_complete_fixture_remains_silent():
    """Regression guard on the flip side: the original complete
    fixture (no declarations) must still emit zero framing_notes."""
    path = FIXTURE.parent / "exercise_waist_complete.json"
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    results = dispatch_all(program, project(instantiate(program)))
    assert results[0].framing_notes == ()
