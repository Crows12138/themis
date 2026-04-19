"""End-to-end tests for slice 3: identify + backdoor + formula AST.

Fixture has two scenarios:

- confounded: stress -> smokes, stress -> cancer, smokes -> cancer
  identify(cancer | do(smokes=false))
  → identifiable via adjustment set {stress}
  → formula is a SumExpr over stress(alice)

- direct: exercise -> health
  identify(health | do(exercise=true))
  → identifiable with empty adjustment
  → formula is a single ProbabilityRefExpr
"""
from __future__ import annotations

from pathlib import Path

import pytest

from causal_kernel.input.parser import parse_json
from causal_kernel.input.semantic_validator import validate_formula, validate_program
from causal_kernel.input.syntactic_validator import validate_ast, validate_result
from causal_kernel.output.explainer import explain
from causal_kernel.output.result_orchestrator import to_dict
from causal_kernel.runtime.graph_projection import project
from causal_kernel.runtime.instantiation import instantiate
from causal_kernel.runtime.scheduler import dispatch_all
from causal_kernel.types import (
    ProbabilityRefExpr,
    ProductExpr,
    QueryKind,
    ResultStatus,
    SumExpr,
    VarRef,
)

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "identify_backdoor.json"


@pytest.fixture(scope="module")
def results_by_id() -> dict:
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    return {r.query_id: r for r in dispatch_all(program, graph)}


def test_confounded_is_identifiable(results_by_id):
    r = results_by_id["identify_confounded"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.IDENTIFY
    assert r.structural_result.value is True
    assert r.formula is not None


def test_confounded_formula_is_sum_over_stress(results_by_id):
    r = results_by_id["identify_confounded"]
    formula = r.formula
    assert isinstance(formula, SumExpr)
    assert formula.over.predicate == "stress"

    body = formula.body
    assert isinstance(body, ProductExpr)
    assert len(body.terms) == 2

    conditional, z_dist = body.terms
    assert isinstance(conditional, ProbabilityRefExpr)
    assert isinstance(z_dist, ProbabilityRefExpr)

    # conditional: P(cancer | smokes=false, stress=z)
    assert conditional.target.atom.predicate == "cancer"
    assert conditional.target.value is None  # query-bound

    given_preds = {va.atom.predicate for va in conditional.given}
    assert given_preds == {"smokes", "stress"}

    # z_dist: P(stress=z)
    assert z_dist.target.atom.predicate == "stress"
    assert isinstance(z_dist.target.value, VarRef)
    assert z_dist.target.value.name == formula.bind.name
    assert z_dist.given == ()


def test_direct_is_identifiable_without_adjustment(results_by_id):
    r = results_by_id["identify_direct"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.structural_result.value is True
    # empty-adjustment formula is a flat conditional, not a sum
    assert isinstance(r.formula, ProbabilityRefExpr)
    assert r.formula.target.atom.predicate == "health"
    assert r.formula.target.value is None
    assert len(r.formula.given) == 1
    assert r.formula.given[0].atom.predicate == "exercise"
    assert r.formula.given[0].value is True


def test_identify_formulas_are_wellformed(results_by_id):
    for r in results_by_id.values():
        if r.formula is not None:
            validate_formula(r.formula)  # raises on failure


def test_identify_results_round_trip_through_schema(results_by_id):
    for qid, r in results_by_id.items():
        payload = to_dict(r)
        validate_result(payload)
        assert payload["query_kind"] == "identify", qid
        if r.formula is not None:
            assert "formula" in payload


def test_confounded_explanation_mentions_stress(results_by_id):
    text = explain(results_by_id["identify_confounded"])
    assert "stress(alice)" in text
    assert "后门" in text


def test_direct_explanation_no_adjustment_needed(results_by_id):
    text = explain(results_by_id["identify_direct"])
    assert "无需" in text or "观察分布" in text
