"""Lock the exercise_waist trial-pack cases as E2E regressions.

Mirror of what commit ad0f481 did for the v0.1.0 trial cases
(`试跑案例_v0_1.md`): once a real-world-shaped fixture has been used
to reason about the system's current behaviour, pin the exact
envelope so any later slice that silently degrades it shows up as a
test failure rather than a surprise during the next trial pass.

Three fixtures, three situations:

- exercise_waist_complete.json           — happy numeric path
- exercise_waist_missing_parameter.json  — one-CPT gap, gets skeleton
- exercise_waist_confidence_mixed.json   — mixed annotations → 0.3

Causal structure (all three):
    diet_control -> exercise_regular
    diet_control -> waist_reduced
    exercise_regular -> waist_reduced

Query: effect(waist_reduced=true | do(exercise_regular=true)).
Back-door adjustment on {diet_control}; formula
    ∑_z P(waist_reduced=true | exercise_regular=true, diet_control=z)
        · P(diet_control=z)
    = 0.7·0.4 + 0.3·0.6 = 0.46
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
from themis.types import (
    InvestigationAction,
    MissingKind,
    Priority,
    QueryKind,
    QueryStatement,
    ResultStatus,
    SumExpr,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _run(name: str):
    path = FIXTURES / name
    ast = parse_json(path.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s
        for s in program.statements
        if isinstance(s, QueryStatement)
    }
    return program, results, stmt_by_id


# ============================================================ case 1

def test_complete_case_resolves_to_0_46():
    _, results, _ = _run("exercise_waist_complete.json")
    assert len(results) == 1
    r = results[0]
    assert r.query_id == "effect_waist_reduced_if_exercise"
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.query_kind is QueryKind.EFFECT
    assert r.numeric_result.value == pytest.approx(0.46)
    assert r.missing_information == ()
    assert r.investigation_requests == ()


def test_complete_case_adjusts_on_diet_control():
    _, results, _ = _run("exercise_waist_complete.json")
    r = results[0]
    assert isinstance(r.formula, SumExpr)
    assert r.formula.over.predicate == "diet_control"


def test_complete_case_explanation_quotes_query_and_value():
    _, results, stmt_by_id = _run("exercise_waist_complete.json")
    r = results[0]
    text = explain(r, stmt=stmt_by_id[r.query_id])
    assert "waist_reduced(me)" in text
    assert "exercise_regular(me)" in text
    assert "do(" in text
    assert "0.46" in text
    assert "diet_control(me)" in text
    # Complete case has no confidence annotations → no 综合可信度 clause.
    assert "综合可信度" not in text


def test_complete_case_round_trips_through_schema():
    _, results, _ = _run("exercise_waist_complete.json")
    payload = to_dict(results[0])
    validate_result(payload)
    assert payload["status"] == "numerically_solved"
    assert payload["numeric_result"]["value"] == pytest.approx(0.46)


# ============================================================ case 2

def test_missing_parameter_case_surfaces_exact_gap():
    _, results, _ = _run("exercise_waist_missing_parameter.json")
    r = results[0]
    assert r.query_id == "effect_waist_reduced_missing_parameter"
    assert r.status is ResultStatus.NEEDS_INVESTIGATION
    assert r.numeric_result is None
    assert len(r.missing_information) == 1
    m = r.missing_information[0]
    assert m.kind is MissingKind.PARAMETER
    assert m.priority is Priority.HIGH
    # Pin the name format — slice 9.x-B depends on this shape for
    # skeleton lookup; any change requires an explicit test update.
    assert m.name == (
        "parameter:P(waist_reduced=True"
        "|diet_control=False,exercise_regular=True)"
    )


def test_missing_parameter_case_attaches_paste_ready_skeleton():
    _, results, _ = _run("exercise_waist_missing_parameter.json")
    r = results[0]
    assert len(r.investigation_requests) == 1
    req = r.investigation_requests[0]
    assert req.action is InvestigationAction.VALIDATE_PARAMETER
    assert req.group == "parameter"
    assert len(req.items) == 1
    skeleton = req.items[0].skeleton
    assert skeleton is not None
    assert skeleton["kind"] == "probability"
    assert skeleton["target"]["atom"]["predicate"] == "waist_reduced"
    assert skeleton["target"]["value"] is True
    given_preds = {g["atom"]["predicate"] for g in skeleton["given"]}
    assert given_preds == {"diet_control", "exercise_regular"}
    assert skeleton["value"] is None

    # The skeleton + filled value must validate as a legal statement.
    filled = dict(skeleton)
    filled["value"] = 0.3
    draft = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [filled],
    }
    validate_ast(draft)


def test_missing_parameter_case_explanation_answers_what_why_next():
    _, results, stmt_by_id = _run("exercise_waist_missing_parameter.json")
    r = results[0]
    text = explain(r, stmt=stmt_by_id[r.query_id])
    # 1. quantity framing + identifiability acknowledgment
    assert "P(waist_reduced(me)=True" in text
    assert "可识别" in text
    # 2. specific missing parameter named verbatim
    assert (
        "parameter:P(waist_reduced=True"
        "|diet_control=False,exercise_regular=True)"
    ) in text
    # 3. three-part envelope (what / why / next)
    assert "原因" in text
    assert "下一步" in text
    assert "提供该参数" in text
    assert "优先级 高" in text


# ============================================================ case 3

def test_confidence_mixed_case_has_value_and_weakest_link():
    _, results, _ = _run("exercise_waist_confidence_mixed.json")
    r = results[0]
    assert r.query_id == "effect_waist_reduced_confidence_mixed"
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.numeric_result.value == pytest.approx(0.46)
    # Four slots annotated (0.9, 0.3, 0.8, 0.8); min rule picks 0.3.
    assert r.confidence == pytest.approx(0.3)


def test_confidence_mixed_case_explanation_surfaces_weakest_link():
    """Slice 9.x-D: the text must include the composite value AND
    the min-rule framing, so readers understand what 0.3 means."""
    _, results, stmt_by_id = _run("exercise_waist_confidence_mixed.json")
    r = results[0]
    text = explain(r, stmt=stmt_by_id[r.query_id])
    assert "0.46" in text
    assert "diet_control(me)" in text
    # Slice 9.x-D surface
    assert "0.3" in text
    assert "综合可信度" in text
    assert "最弱证据水平" in text


def test_confidence_mixed_case_round_trips_through_schema():
    _, results, _ = _run("exercise_waist_confidence_mixed.json")
    payload = to_dict(results[0])
    validate_result(payload)
    assert payload["confidence"] == pytest.approx(0.3)
    assert payload["numeric_result"]["value"] == pytest.approx(0.46)
