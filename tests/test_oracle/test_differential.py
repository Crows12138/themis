"""Differential tests: runtime vs pgmpy oracle on all existing fixtures.

This slice-4 harness is the first true external check on the runtime
implementations from slices 1-3. Every cause / assoc / identify query
in every fixture is run through both sides and must agree.

Queries whose kind the oracle does not speak to (effect, probability,
or runtime results without a structural verdict) are reported as
``not_applicable`` and skipped.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from causal_kernel.input.parser import parse_json
from causal_kernel.input.semantic_validator import validate_program
from causal_kernel.input.syntactic_validator import validate_ast
from causal_kernel.oracle.differential import compare
from causal_kernel.oracle.pgmpy_adapter import build_network
from causal_kernel.runtime.graph_projection import project
from causal_kernel.runtime.instantiation import instantiate
from causal_kernel.runtime.scheduler import dispatch_all
from causal_kernel.types import QueryStatement

PROJECT_ROOT = Path(__file__).resolve().parents[2]

FIXTURES = [
    PROJECT_ROOT / "minimal_example_v0_1.json",
    PROJECT_ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json",
    PROJECT_ROOT / "tests" / "test_e2e" / "fixtures" / "identify_backdoor.json",
]


def _load(path: Path):
    ast = parse_json(path.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    oracle_network = build_network(program)
    results_by_id = {r.query_id: r for r in dispatch_all(program, graph)}
    return program, oracle_network, results_by_id


def _iter_reports(path: Path):
    program, network, results = _load(path)
    for stmt in program.statements:
        if not isinstance(stmt, QueryStatement):
            continue
        result = results[stmt.id]
        yield compare(stmt, result, network)


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_no_runtime_oracle_disagreement(fixture):
    """Every comparable query must agree between runtime and oracle."""
    disagreements = [
        r for r in _iter_reports(fixture) if r.status == "disagree"
    ]
    assert not disagreements, "; ".join(
        f"{r.query_id}: {r.reason}" for r in disagreements
    )


@pytest.mark.parametrize("fixture", FIXTURES, ids=lambda p: p.name)
def test_at_least_one_comparable_query(fixture):
    """Sanity: the fixture must contain at least one query the oracle
    can compare. A fixture of only ``not_applicable`` reports would
    give a false sense of coverage."""
    comparable = [
        r for r in _iter_reports(fixture) if r.status != "not_applicable"
    ]
    assert comparable, (
        f"{fixture.name} produced no comparable differential reports; "
        f"oracle has no coverage of this fixture"
    )


def test_assoc_canonical_all_six_agree():
    """Spot-check: every assoc query in the canonical fixture (6 total)
    is individually comparable and in agreement."""
    reports = list(_iter_reports(FIXTURES[1]))
    agree = [r for r in reports if r.status == "agree"]
    assert len(agree) == 6, (
        f"expected 6 agreeing reports on assoc_canonical, got {len(agree)}"
    )


def test_identify_backdoor_both_agree():
    """Spot-check: both identify queries in the backdoor fixture agree,
    AND the runtime's chosen adjustment set is valid per pgmpy."""
    reports = list(_iter_reports(FIXTURES[2]))
    assert all(r.status == "agree" for r in reports), [
        (r.query_id, r.reason) for r in reports if r.status != "agree"
    ]
