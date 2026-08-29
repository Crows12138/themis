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
    Malformed,
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
    with pytest.raises(SemanticError) as raised:
        validate_program(ast)
    assert raised.value.species is Malformed.QUERY_NOT_GROUND


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
    with pytest.raises(SemanticError) as raised:
        validate_program(ast)
    assert raised.value.species is Malformed.OBSERVATION_NOT_GROUND


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
    with pytest.raises(SemanticError) as raised:
        validate_program(ast)
    assert raised.value.species is Malformed.VARIABLE_NOT_IN_FORALL
    # Which variable is undeclared is the half the reader needs and the
    # half the species cannot carry, so it is checked where it lives.
    assert raised.value.details["variables"] == ["Y"]


def _const(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def test_bidirected_only_query_atom_names_m_bias() -> None:
    """A `given` atom appearing ONLY in bidirected edges (no directed
    role) never enters V. Real-usage probe 2026-06-15: this must refuse
    as the bidirected-only / M-bias situation rather than as the
    misleading 'no cause edge introduces them', which reads as 'you
    forgot to declare it' even though the user clearly declared m. The
    two are separate species precisely so that the difference survives
    whichever language the sentence is finally written in."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "from": _const("x"), "to": _const("y")},
            {"kind": "bidirected", "left": _const("x"), "right": _const("m")},
            {"kind": "bidirected", "left": _const("m"), "right": _const("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _const("y"), "value": True},
                "intervention": {"atom": _const("x"), "value": True},
                "given": [{"atom": _const("m"), "value": True}]}},
        ],
    }
    # The query-atoms-in-V check runs over the instantiated graph in the
    # run path (validate_against_graph), so drive it via themis.run.
    import themis

    with pytest.raises(SemanticError) as raised:
        themis.run(ast)
    assert raised.value.species is Malformed.QUERY_ATOM_ONLY_BIDIRECTED


def test_truly_undeclared_query_atom_keeps_original_message() -> None:
    """Contrast to the M-bias case: an atom in NO statement at all keeps
    the original 'no cause edge introduces them' species — the bidirected
    refinement is gated on the atom actually being a bidirected endpoint."""
    import themis

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "from": _const("x"), "to": _const("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _const("y"), "value": True},
                "intervention": {"atom": _const("x"), "value": True},
                "given": [{"atom": _const("w"), "value": True}]}},
        ],
    }
    with pytest.raises(SemanticError) as raised:
        themis.run(ast)
    assert raised.value.species is Malformed.QUERY_ATOM_NOT_IN_GRAPH


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
    with pytest.raises(SemanticError) as raised:
        validate_program(ast)
    assert raised.value.species is Malformed.PREDICATE_DECLARED_TWICE
    assert raised.value.details["predicate"] == "smokes"


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
