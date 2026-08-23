"""Phase 5 §C / S.C.1: counterfactual surface only.

This slice is deliberately narrow:

- ``kernel_ast.schema.json`` accepts a ``counterfactual`` query shape.
- ``validate_program`` parses it into a typed ``CounterfactualQuery``.
- Program / verification-context JSON round-trips preserve the query.
- ``themis.run`` does not crash; it returns a stable
  ``outside_language`` result for now.

No twin-network projection, monotonicity reasoning, or bounds solver
lands here yet.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast, validate_result
from themis.kernel import _program_to_ast_dict, run
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.types import (
    CounterfactualQuery,
    Monotonicity,
    QueryKind,
    QueryStatement,
    ResultStatus,
)
from themis.verifier import VerificationContext, context_from_dict, context_to_dict

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONTEXT_SCHEMA_PATH = PROJECT_ROOT / "themis" / "schemas" / "verification_context.schema.json"


def _validate_schema(payload: dict, path: Path) -> None:
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        pytest.skip("jsonschema not installed")
    from themis.input.syntactic_validator import validator_for

    validator_for(path.name).validate(payload)


def _counterfactual_ast(*, monotonicity: str | None = "non_decreasing") -> dict:
    query: dict = {
        "kind": "counterfactual",
        "observed": {
            "atom": {
                "predicate": "chose_cs_major",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": False,
        },
        "counterfactual_intervention": {
            "atom": {
                "predicate": "chose_cs_major",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": True,
        },
        "counterfactual_target": {
            "atom": {
                "predicate": "higher_income",
                "args": [{"type": "const", "name": "me"}],
            },
            "value": True,
        },
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}

    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "cause",
                "from": {
                    "predicate": "chose_cs_major",
                    "args": [{"type": "const", "name": "me"}],
                },
                "to": {
                    "predicate": "higher_income",
                    "args": [{"type": "const", "name": "me"}],
                },
            },
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_income", "domain": [True, False]},
            {"kind": "query", "id": "q_cf", "query": query},
        ],
    }


def test_counterfactual_schema_accepts_minimal_query_shape():
    out = validate_ast(_counterfactual_ast())
    assert isinstance(out, dict)


def test_counterfactual_schema_allows_omitted_assumptions():
    out = validate_ast(_counterfactual_ast(monotonicity=None))
    assert isinstance(out, dict)


def test_counterfactual_schema_rejects_invalid_monotonicity_value():
    with pytest.raises(SyntacticError):
        validate_ast(_counterfactual_ast(monotonicity="monotone-ish"))


def test_validate_program_parses_typed_counterfactual_query():
    prog = validate_program(validate_ast(_counterfactual_ast()), checks=frozenset())
    stmt = next(s for s in prog.statements if isinstance(s, QueryStatement))
    assert isinstance(stmt.query, CounterfactualQuery)
    assert stmt.query.assumptions is not None
    assert stmt.query.assumptions.monotonicity is Monotonicity.NON_DECREASING
    assert stmt.query.counterfactual_intervention.value is True
    assert stmt.query.observed.value is False


def test_validate_program_parses_missing_assumptions_as_none():
    prog = validate_program(
        validate_ast(_counterfactual_ast(monotonicity=None)),
        checks=frozenset(),
    )
    stmt = next(s for s in prog.statements if isinstance(s, QueryStatement))
    assert isinstance(stmt.query, CounterfactualQuery)
    assert stmt.query.assumptions is None


def test_program_serializer_round_trip_preserves_counterfactual_query():
    prog = validate_program(validate_ast(_counterfactual_ast()), checks=frozenset())
    emitted = _program_to_ast_dict(prog)
    query_stmt = next(s for s in emitted["statements"] if s["kind"] == "query")
    assert query_stmt["query"]["kind"] == "counterfactual"
    assert query_stmt["query"]["assumptions"] == {"monotonicity": "non_decreasing"}
    prog2 = validate_program(validate_ast(emitted), checks=frozenset())
    assert prog2 == prog


def test_verification_context_round_trip_preserves_counterfactual_query():
    prog = validate_program(validate_ast(_counterfactual_ast()), checks=frozenset())
    graph = project(instantiate(prog))
    stmt = next(s for s in prog.statements if isinstance(s, QueryStatement))
    ctx = VerificationContext(graph=graph, query=stmt.query)
    payload = context_to_dict(ctx)
    _validate_schema(payload, CONTEXT_SCHEMA_PATH)
    assert payload["query"]["kind"] == "counterfactual_query"
    assert payload["query"]["assumptions"] == {"monotonicity": "non_decreasing"}
    back = context_from_dict(payload)
    assert isinstance(back.query, CounterfactualQuery)
    assert back.query == stmt.query


def test_run_surfaces_counterfactual_as_needs_investigation_without_theta():
    out = run(_counterfactual_ast())
    assert len(out["results"]) == 1
    result = out["results"][0]
    validate_result(result)
    assert result["query_kind"] == "counterfactual"
    assert result["status"] == "needs_investigation"
    assert result["missing_information"]
    assert "derivation" not in result
