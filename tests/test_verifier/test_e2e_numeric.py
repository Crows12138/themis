"""End-to-end V1 verifier coverage: every numerically-solved effect /
probability result shipped in the repo's fixtures must produce a
derivation that the verifier accepts, and tampering with a numeric
step must produce a reject.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime import theta_builder
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    NumericResult,
    QueryKind,
    QueryStatement,
    ResultStatus,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_numeric,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "test_e2e" / "fixtures"

# Fixtures that contain at least one numerically-solved effect or
# probability query.
NUMERIC_FIXTURES = [
    FIXTURE_DIR / "numeric_backdoor.json",
    FIXTURE_DIR / "numeric_categorical.json",
    FIXTURE_DIR / "probability_no_graph.json",
]


def _run(path: Path):
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    ground = instantiate(program)
    graph = project(ground)
    theta = theta_builder.build_theta(ground)
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    return program, graph, theta, results, stmt_by_id


def _numeric_results(results):
    return [
        r for r in results
        if r.status is ResultStatus.NUMERICALLY_SOLVED
        and r.query_kind in (QueryKind.EFFECT, QueryKind.PROBABILITY)
    ]


@pytest.mark.parametrize("fixture", NUMERIC_FIXTURES, ids=lambda p: p.name)
def test_verifier_accepts_every_numerically_solved_derivation(fixture):
    _, graph, theta, results, stmt_by_id = _run(fixture)
    solved = _numeric_results(results)
    assert solved, f"{fixture.name} has no numerically-solved effect/probability"

    for r in solved:
        assert r.derivation, f"{r.query_id}: missing derivation"
        assert r.derivation[-1].rule == "numeric_result"
        ctx = VerificationContext(
            graph=graph,
            query=stmt_by_id[r.query_id].query,
            theta=theta,
        )
        verify_numeric(r.derivation, ctx, r.numeric_result)


@pytest.mark.parametrize("fixture", NUMERIC_FIXTURES, ids=lambda p: p.name)
def test_tampering_numeric_value_is_rejected(fixture):
    """Flipping the formula_evaluation output to a wrong value must
    cause R7 to reject."""
    _, graph, theta, results, stmt_by_id = _run(fixture)
    for r in _numeric_results(results):
        ctx = VerificationContext(
            graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
        )
        bad = list(r.derivation)
        for i, step in enumerate(bad):
            if step.rule == "formula_evaluation":
                bad[i] = replace(step, output=step.output + 1.0)
                break
        with pytest.raises(VerificationError):
            verify_numeric(tuple(bad), ctx, r.numeric_result)


@pytest.mark.parametrize("fixture", NUMERIC_FIXTURES, ids=lambda p: p.name)
def test_tampering_numeric_result_value_is_rejected(fixture):
    """Changing the final NumericResult.value while leaving evaluation
    intact must be rejected by R8 (the two must agree)."""
    _, graph, theta, results, stmt_by_id = _run(fixture)
    for r in _numeric_results(results):
        ctx = VerificationContext(
            graph=graph, query=stmt_by_id[r.query_id].query, theta=theta,
        )
        bad = list(r.derivation)
        for i, step in enumerate(bad):
            if step.rule == "numeric_result":
                bad[i] = replace(
                    step, output=NumericResult(value=r.numeric_result.value + 1.0)
                )
                break
        with pytest.raises(VerificationError):
            verify_numeric(
                tuple(bad), ctx,
                NumericResult(value=r.numeric_result.value + 1.0),
            )


def test_needs_investigation_has_no_derivation():
    """NUMERICALLY_SOLVED path emits derivation; NEEDS_INVESTIGATION
    (Theta incomplete) does not. V1 keeps this boundary clean; changing
    it would belong to a future slice that proves unsolvability."""
    path = FIXTURE_DIR / "numeric_backdoor_missing_parameter.json"
    _, _, _, results, _ = _run(path)
    for r in results:
        if r.status is ResultStatus.NEEDS_INVESTIGATION:
            assert r.derivation == ()
