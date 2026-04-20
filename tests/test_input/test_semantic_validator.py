"""Regression tests for semantic validator tightening.

Cover the gaps found in slice-1 review:
- patterned queries must be rejected, not silently answered False
- observations must be ground
- free VarTerms in cause / probability statements must be declared
  in forall
"""
from __future__ import annotations

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import (
    SemanticError,
    validate_program,
)
from themis.input.syntactic_validator import validate_ast


def _base_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "alice"}]},
        "statements": [
            {
                "kind": "cause",
                "forall": ["X"],
                "from": {"predicate": "smokes", "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "cancer", "args": [{"type": "var", "name": "X"}]},
            }
        ],
    }


def test_patterned_cause_query_is_rejected() -> None:
    ast = _base_program()
    ast["statements"].append(
        {
            "kind": "query",
            "id": "q_bad",
            "query": {
                "kind": "cause",
                "from": {"predicate": "smokes", "args": [{"type": "var", "name": "X"}]},
                "to": {"predicate": "cancer", "args": [{"type": "var", "name": "X"}]},
            },
        }
    )
    validate_ast(ast)
    with pytest.raises(SemanticError, match="must be ground"):
        validate_program(ast)


def test_nonground_observation_is_rejected() -> None:
    ast = _base_program()
    ast["statements"].append(
        {
            "kind": "observation",
            "atom": {"predicate": "smokes", "args": [{"type": "var", "name": "X"}]},
            "value": True,
        }
    )
    validate_ast(ast)
    with pytest.raises(SemanticError, match="observation atom must be ground"):
        validate_program(ast)


def test_undeclared_var_in_cause_is_rejected() -> None:
    ast = _base_program()
    # Introduce Y into the cause statement but do not declare it in forall.
    bad = {
        "kind": "cause",
        "forall": ["X"],
        "from": {"predicate": "smokes", "args": [{"type": "var", "name": "X"}]},
        "to": {"predicate": "cancer", "args": [{"type": "var", "name": "Y"}]},
    }
    ast["statements"].append(bad)
    validate_ast(ast)
    with pytest.raises(SemanticError, match=r"\['Y'\].*not declared in forall"):
        validate_program(ast)


def test_duplicate_variable_declaration_is_rejected() -> None:
    """Slice A0 follow-up: a predicate may have at most one
    variableDeclaration. Two declarations used to silently overwrite
    each other in framing_check, making the surfaced gaps depend on
    statement order."""
    ast = _base_program()
    ast["statements"].append(
        {"kind": "variable", "predicate": "smokes", "domain": [True, False]}
    )
    ast["statements"].append(
        {"kind": "variable", "predicate": "smokes", "time_window": "lifetime"}
    )
    validate_ast(ast)  # schema itself allows both entries
    with pytest.raises(SemanticError, match="'smokes' already declared"):
        validate_program(ast)


def test_single_variable_declaration_per_predicate_passes() -> None:
    """Sanity twin: one declaration per predicate is fine even when
    the declarations are partial (framing_check will surface the gaps
    instead of erroring)."""
    ast = _base_program()
    ast["statements"].append(
        {"kind": "variable", "predicate": "smokes", "domain": [True, False]}
    )
    ast["statements"].append(
        {"kind": "variable", "predicate": "cancer", "time_window": "lifetime"}
    )
    validate_ast(ast)
    validate_program(ast)  # must not raise
