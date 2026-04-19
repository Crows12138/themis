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
