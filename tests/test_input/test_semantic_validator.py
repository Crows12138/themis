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
