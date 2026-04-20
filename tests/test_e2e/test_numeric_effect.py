"""End-to-end test for slice 6: numeric effect via populated Theta.

Fixture: stress -> smokes, stress -> cancer, smokes -> cancer
with a complete set of probability statements:

    P(cancer=true | smokes=false, stress=true)  = 0.3
    P(cancer=true | smokes=false, stress=false) = 0.1
    P(stress=true)  = 0.4
    P(stress=false) = 0.6

Query: effect(cancer(alice)=true | do(smokes(alice)=false))

Expected back-door adjustment set = {stress}, formula:
    ∑_z P(cancer=true | smokes=false, stress=z) · P(stress=z)
  = 0.3 · 0.4  +  0.1 · 0.6
  = 0.12 + 0.06
  = 0.18
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast, validate_result
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.runtime.theta_builder import build_theta_from_program
from themis.types import QueryKind, ResultStatus

FIXTURE = (
    Path(__file__).resolve().parent / "fixtures" / "numeric_backdoor.json"
)


@pytest.fixture(scope="module")
def run():
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    theta = build_theta_from_program(program)
    return program, graph, results, theta


def test_theta_populated_from_probability_statements(run):
    _, _, _, theta = run
    # Four distinct entries: two for P(cancer|smokes,stress) and two
    # for P(stress).
    assert len(theta.entries) == 4


def test_effect_is_numerically_solved(run):
    _, _, results, _ = run
    r = results["effect_cancer_given_no_smoke"]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.query_kind is QueryKind.EFFECT
    assert r.numeric_result is not None


def test_effect_value_matches_hand_computed(run):
    _, _, results, _ = run
    r = results["effect_cancer_given_no_smoke"]
    assert r.numeric_result.value == pytest.approx(0.18)


def test_effect_result_round_trips_through_schema(run):
    _, _, results, _ = run
    r = results["effect_cancer_given_no_smoke"]
    payload = to_dict(r)
    validate_result(payload)
    assert payload["status"] == "numerically_solved"
    assert payload["numeric_result"]["value"] == pytest.approx(0.18)
    # Formula is still emitted even though numeric layer closed it.
    assert "formula" in payload
    assert payload["formula"]["kind"] == "sum"


# ------------------------------------------------------ slice 8.2 explainer

def test_effect_success_explanation_states_adjustment_and_value(run):
    """Slice 8.2: the effect explainer must quote the target, the
    intervention, and the numeric answer when the query succeeds,
    plus name the adjustment set that identified it."""
    from themis.output.explainer import explain
    from themis.types import QueryStatement

    program = run[0]
    results = run[2]
    stmt = next(
        s for s in program.statements
        if isinstance(s, QueryStatement) and s.id == "effect_cancer_given_no_smoke"
    )
    text = explain(results["effect_cancer_given_no_smoke"], stmt=stmt)

    # Query surface pieces.
    assert "cancer(alice)" in text
    assert "smokes(alice)" in text
    assert "do(" in text
    # Numeric answer (rendered via :.4g).
    assert "0.18" in text
    # Identification method.
    assert "stress(alice)" in text
    assert "后门" in text


def test_effect_explanation_without_stmt_falls_back_to_generic(run):
    """Back-compat: callers that don't pass stmt still get a coherent
    explanation, just without the specific target / intervention
    quotation."""
    from themis.output.explainer import explain

    _, _, results, _ = run
    text = explain(results["effect_cancer_given_no_smoke"])
    # No per-query atoms, but still mentions the numeric value and
    # adjustment set.
    assert "0.18" in text
    assert "stress(alice)" in text
