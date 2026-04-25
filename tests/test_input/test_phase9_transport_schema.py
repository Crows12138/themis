"""Phase 9 §T9.1 schema additions: shape tests.

Covers the new schema fields for transport identification:
- ``selection_node`` statement type
- ``population`` on probability statements (back-compat: optional)
- ``target_population`` on effect / identify queries (back-compat: optional)

Pure schema-level validation — no runtime semantics yet (those land
in S.T9.1.2 and S.T9.1.3).
"""
from __future__ import annotations

import pytest

from themis.input.syntactic_validator import SyntacticError, validate_ast


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _base_program(extra_statements: list) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "age", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            *extra_statements,
        ],
    }


# ============================================ selection_node


def test_selection_node_statement_validates():
    prog = _base_program([
        {
            "kind": "selection_node",
            "id": "S_age",
            "affects": _atom("age"),
            "source_population": "rct_2022",
            "target_population": "user",
            "annotations": {"source": "narrative_proposal", "evidence": "源 42 岁均值"},
        },
    ])
    validate_ast(prog)  # no raise


def test_selection_node_minimum_required_fields():
    prog = _base_program([
        {
            "kind": "selection_node",
            "id": "S_age",
            "affects": _atom("age"),
            "source_population": "rct_2022",
            "target_population": "user",
        },
    ])
    validate_ast(prog)


def test_selection_node_missing_affects_rejected():
    prog = _base_program([
        {
            "kind": "selection_node",
            "id": "S_age",
            "source_population": "rct_2022",
            "target_population": "user",
        },
    ])
    with pytest.raises(SyntacticError):
        validate_ast(prog)


def test_selection_node_invalid_population_name_rejected():
    prog = _base_program([
        {
            "kind": "selection_node",
            "id": "S_age",
            "affects": _atom("age"),
            "source_population": "1bad-name",  # starts with digit, has hyphen
            "target_population": "user",
        },
    ])
    with pytest.raises(SyntacticError):
        validate_ast(prog)


def test_selection_node_extra_property_rejected():
    prog = _base_program([
        {
            "kind": "selection_node",
            "id": "S_age",
            "affects": _atom("age"),
            "source_population": "rct_2022",
            "target_population": "user",
            "wishful_extra_field": "something",
        },
    ])
    with pytest.raises(SyntacticError):
        validate_ast(prog)


# ============================================ population on probability


def test_probability_statement_with_population_validates():
    prog = _base_program([
        {
            "kind": "probability",
            "target": {"atom": _atom("y"), "value": True},
            "given": [{"atom": _atom("x"), "value": True}],
            "value": 0.55,
            "population": "rct_2022",
            "annotations": {"source": "PMC9540641"},
        },
    ])
    validate_ast(prog)


def test_probability_statement_without_population_still_validates():
    """Back-compat: probability without population field is treated as universal."""
    prog = _base_program([
        {
            "kind": "probability",
            "target": {"atom": _atom("y"), "value": True},
            "given": [{"atom": _atom("x"), "value": True}],
            "value": 0.55,
        },
    ])
    validate_ast(prog)


# ============================================ target_population on queries


def test_effect_query_with_target_population_validates():
    prog = _base_program([
        {
            "kind": "query", "id": "q",
            "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "target_population": "user",
            },
        },
    ])
    validate_ast(prog)


def test_identify_query_with_target_population_validates():
    prog = _base_program([
        {
            "kind": "query", "id": "q",
            "query": {
                "kind": "identify",
                "target": _atom("y"),
                "intervention": {"atom": _atom("x"), "value": True},
                "given": [],
                "target_population": "user",
            },
        },
    ])
    validate_ast(prog)


def test_effect_query_without_target_population_still_validates():
    """Back-compat: existing effect queries unchanged."""
    prog = _base_program([
        {
            "kind": "query", "id": "q",
            "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            },
        },
    ])
    validate_ast(prog)
