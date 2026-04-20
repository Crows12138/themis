"""Slice 8.4: systematic fidelity invariants for the explainer.

Every query in every e2e fixture is parametrised, and a small set of
invariants is checked independently. Each invariant asserts:

    "if the structured result contains X, the explanation text must
     also mention X (or an agreed-upon phrasing of X)."

Individual slice tests pin specific scenarios with specific strings;
these tests guard against *categories* of drift. If slice 9 or later
changes a missing-item name format, an investigation action, or the
numeric formatting, this file flags every fixture that falls out of
sync — not just the one case the slice author remembered to update.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.output import explainer as _explainer
from themis.output.explainer import explain
from themis.runtime import formula_builder
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import QueryKind, QueryStatement, ResultStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"

FIXTURES = [
    PROJECT_ROOT / "minimal_example_v0_1.json",
    FIXTURE_DIR / "assoc_canonical.json",
    FIXTURE_DIR / "identify_backdoor.json",
    FIXTURE_DIR / "identify_conditional.json",
    FIXTURE_DIR / "identify_two_var.json",
    FIXTURE_DIR / "numeric_backdoor.json",
    FIXTURE_DIR / "numeric_backdoor_missing_parameter.json",
    FIXTURE_DIR / "numeric_categorical.json",
    FIXTURE_DIR / "probability_no_graph.json",
]


def _atom_label(atom) -> str:
    return f"{atom.predicate}({','.join(t.name for t in atom.args)})"


def _collect_cases():
    cases = []
    for fpath in FIXTURES:
        ast = parse_json(fpath.read_text(encoding="utf-8"))
        program = validate_program(validate_ast(ast))
        graph = project(instantiate(program))
        results = {r.query_id: r for r in dispatch_all(program, graph)}
        for stmt in program.statements:
            if not isinstance(stmt, QueryStatement):
                continue
            cases.append(
                pytest.param(stmt, results[stmt.id], id=f"{fpath.name}::{stmt.id}")
            )
    return cases


CASES = _collect_cases()


# --------------------------------------------------------------- sanity

def test_cases_were_collected():
    """Sentinel: if this drops to 0 the fidelity suite silently passes."""
    assert len(CASES) > 0


# ------------------------------------------- invariant 1: numeric presence

@pytest.mark.parametrize("stmt, result", CASES)
def test_numeric_value_is_in_explanation(stmt, result):
    if result.status is not ResultStatus.NUMERICALLY_SOLVED:
        pytest.skip("not numerically solved")
    assert result.numeric_result is not None
    text = explain(result, stmt=stmt)
    rendered = _explainer._format_number(result.numeric_result.value)
    assert rendered in text, (
        f"numeric value {rendered!r} missing from:\n{text}"
    )


# ----------------------------------- invariant 2: adjustment atoms present

@pytest.mark.parametrize("stmt, result", CASES)
def test_adjustment_atoms_all_mentioned(stmt, result):
    if result.formula is None:
        pytest.skip("no formula")
    adj = formula_builder.adjustment_atoms(result.formula)
    if not adj:
        pytest.skip("no SumExpr adjustment atoms")
    text = explain(result, stmt=stmt)
    for atom in adj:
        label = _atom_label(atom)
        assert label in text, (
            f"adjustment atom {label!r} missing from:\n{text}"
        )


# --------------------------------- invariant 3: missing-info names verbatim

@pytest.mark.parametrize("stmt, result", CASES)
def test_missing_information_names_all_mentioned(stmt, result):
    if not result.missing_information:
        pytest.skip("no missing information")
    text = explain(result, stmt=stmt)
    for m in result.missing_information:
        assert m.name in text, (
            f"missing item {m.name!r} verbatim not in:\n{text}"
        )


# --------------------------------- invariant 4: investigation-action phrase

@pytest.mark.parametrize("stmt, result", CASES)
def test_investigation_action_phrase_mentioned(stmt, result):
    if not result.investigation_requests:
        pytest.skip("no investigation requests")
    text = explain(result, stmt=stmt)
    for req in result.investigation_requests:
        phrase = _explainer._ACTION_PHRASE.get(req.action, req.action.value)
        assert phrase in text, (
            f"action phrase {phrase!r} for target {req.target!r} "
            f"missing from:\n{text}"
        )


# ------------------------- invariant 5: identify negative verdict surfaces

@pytest.mark.parametrize("stmt, result", CASES)
def test_identify_false_verdict_surfaces_in_text(stmt, result):
    if result.query_kind is not QueryKind.IDENTIFY:
        pytest.skip("not identify")
    if (
        result.structural_result is None
        or result.structural_result.value is not False
    ):
        pytest.skip("not negative identify")
    text = explain(result, stmt=stmt)
    assert "不可识别" in text


# -------------------------- invariant 6: d-separated assoc surfaces in text

@pytest.mark.parametrize("stmt, result", CASES)
def test_d_separated_assoc_surfaces_in_text(stmt, result):
    if result.query_kind is not QueryKind.ASSOC:
        pytest.skip("not assoc")
    if (
        result.structural_result is None
        or result.structural_result.value is not False
    ):
        pytest.skip("assoc connected")
    text = explain(result, stmt=stmt)
    assert "d-分离" in text


# ----------------------------- invariant 7: cause negative verdict surfaces

@pytest.mark.parametrize("stmt, result", CASES)
def test_cause_false_verdict_surfaces_in_text(stmt, result):
    if result.query_kind is not QueryKind.CAUSE:
        pytest.skip("not cause")
    if (
        result.structural_result is None
        or result.structural_result.value is not False
    ):
        pytest.skip("cause true or not structural")
    text = explain(result, stmt=stmt)
    assert "不存在" in text or "不因果影响" in text


# ---------------------- invariant 8: confidence surfaces when non-None

@pytest.mark.parametrize("stmt, result", CASES)
def test_confidence_in_explanation_when_non_none(stmt, result):
    """Slice 9.x-D invariant: if the structured result has a composite
    confidence, the rendered number must appear in the explanation so
    text-only readers aren't blind to the evidence level."""
    if result.confidence is None:
        pytest.skip("no confidence attached")
    text = explain(result, stmt=stmt)
    rendered = _explainer._format_number(result.confidence)
    assert rendered in text, (
        f"confidence {rendered!r} missing from:\n{text}"
    )


# ------------------- invariant 9: NEEDS_INVESTIGATION has complete envelope

@pytest.mark.parametrize("stmt, result", CASES)
def test_needs_investigation_three_part_envelope(stmt, result):
    """For every needs_investigation result that carries both
    missing_information and investigation_requests, the explanation
    must render all three pieces: what / why / next-step.

    If missing_information is empty (rare — e.g. atom-not-in-V caught
    structurally), this invariant is skipped."""
    if result.status is not ResultStatus.NEEDS_INVESTIGATION:
        pytest.skip("not needs_investigation")
    if not result.missing_information:
        pytest.skip("no missing_information to render")
    text = explain(result, stmt=stmt)

    # what: every missing name verbatim
    for m in result.missing_information:
        assert m.name in text

    # why: if any missing item has a reason, the word 原因 must appear
    if any(m.reason for m in result.missing_information):
        assert "原因" in text

    # next-step: if investigation requests exist, 下一步 must appear
    if result.investigation_requests:
        assert "下一步" in text
