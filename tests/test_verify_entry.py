"""Tests for ``themis.verify`` — the pure-JSON re-check entry.

Closes the audit loop started by ``themis.run``: given the original
kernel_ast and a single result from the envelope, any external agent
should be able to re-run the verifier without touching typed kernel
objects. These tests pin that contract for all five query kinds,
verify that tampered answers are caught, and check that the schema
tightening (derivation field now $refs derivation.schema.json)
actually rejects malformed payloads at the outer boundary.
"""
from __future__ import annotations

import copy
import json

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError, validate_result
from themis.verifier import VerificationError


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _cause_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }


def _identify_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "identify",
                       "target": _atom("y"),
                       "intervention": {"atom": _atom("x"), "value": True},
                       "given": []}},
        ],
    }


def _assoc_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "assoc", "left": _atom("x"), "right": _atom("y"),
                       "given": []}},
        ],
    }


def _effect_program_with_theta() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            # P(y=true | x=true) = 0.7; no confounder, backdoor set = {}
            {
                "kind": "probability",
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom("x"), "value": True}],
                "value": 0.7,
            },
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": _atom("y"), "value": True},
                       "intervention": {"atom": _atom("x"), "value": True},
                       "given": []}},
        ],
    }


def _probability_program_with_theta() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "probability",
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "value": 0.3,
            },
            {"kind": "query", "id": "q",
             "query": {"kind": "probability",
                       "target": {"atom": _atom("y"), "value": True},
                       "given": []}},
        ],
    }


def _counterfactual_program_with_theta() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "chose_cs_major", "domain": [True, False]},
            {"kind": "variable", "predicate": "higher_income", "domain": [True, False]},
            {"kind": "cause", "from": _atom("chose_cs_major"), "to": _atom("higher_income")},
            {
                "kind": "probability",
                "target": {"atom": _atom("chose_cs_major"), "value": False},
                "given": [],
                "value": 0.6,
            },
            {
                "kind": "probability",
                "target": {"atom": _atom("chose_cs_major"), "value": True},
                "given": [],
                "value": 0.4,
            },
            {
                "kind": "probability",
                "target": {"atom": _atom("higher_income"), "value": False},
                "given": [{"atom": _atom("chose_cs_major"), "value": False}],
                "value": 0.7,
            },
            {
                "kind": "probability",
                "target": {"atom": _atom("higher_income"), "value": True},
                "given": [{"atom": _atom("chose_cs_major"), "value": False}],
                "value": 0.3,
            },
            {
                "kind": "probability",
                "target": {"atom": _atom("higher_income"), "value": False},
                "given": [{"atom": _atom("chose_cs_major"), "value": True}],
                "value": 0.2,
            },
            {
                "kind": "probability",
                "target": {"atom": _atom("higher_income"), "value": True},
                "given": [{"atom": _atom("chose_cs_major"), "value": True}],
                "value": 0.8,
            },
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "counterfactual",
                 "observed": {"atom": _atom("chose_cs_major"), "value": False},
                 "counterfactual_intervention": {"atom": _atom("chose_cs_major"), "value": True},
                 "counterfactual_target": {"atom": _atom("higher_income"), "value": True},
                 "assumptions": {"monotonicity": "non_decreasing"},
             }},
        ],
    }


# =============================================== accept round-trips

@pytest.mark.parametrize("program_factory,expected_status", [
    (_cause_program,                    "structurally_solved"),
    (_identify_program,                 "structurally_solved"),
    (_assoc_program,                    "structurally_solved"),
    (_effect_program_with_theta,        "numerically_solved"),
    (_probability_program_with_theta,   "numerically_solved"),
    (_counterfactual_program_with_theta, "counterfactual_bounded"),
], ids=["cause", "identify", "assoc", "effect", "probability", "counterfactual"])
def test_verify_accepts_run_output_round_trip(program_factory, expected_status):
    """For each query kind, a result produced by ``themis.run`` must
    pass ``themis.verify`` without raising."""
    program = program_factory()
    out = themis.run(program)
    result = out["results"][0]
    assert result["status"] == expected_status
    themis.verify(program, result)


# ================================================= tamper rejection

def test_verify_rejects_flipped_structural_value():
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    # Flip the claimed cause verdict without adjusting the derivation.
    result["structural_result"]["value"] = False
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_verify_rejects_numeric_value_mismatch():
    program = _effect_program_with_theta()
    result = copy.deepcopy(themis.run(program)["results"][0])
    result["numeric_result"]["value"] = result["numeric_result"]["value"] + 0.1
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_verify_rejects_counterfactual_interval_mismatch():
    program = _counterfactual_program_with_theta()
    result = copy.deepcopy(themis.run(program)["results"][0])
    result["numeric_result"]["interval"]["low"] = (
        result["numeric_result"]["interval"]["low"] + 0.1
    )
    with pytest.raises(VerificationError):
        themis.verify(program, result)


def test_verify_rejects_derivation_with_wrong_final_rule():
    """Replace the claim's last-step rule with something the verifier
    would not accept as a terminal for identify."""
    program = _identify_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    steps = result["derivation"]["steps"]
    steps[-1] = {**steps[-1], "rule": "d_separated"}
    with pytest.raises(VerificationError):
        themis.verify(program, result)


# ============================================ missing / malformed

def test_verify_rejects_result_without_derivation():
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    del result["derivation"]
    with pytest.raises(ValueError, match="derivation"):
        themis.verify(program, result)


def test_verify_rejects_result_with_missing_query_id():
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    del result["query_id"]
    with pytest.raises(ValueError, match="query_id"):
        themis.verify(program, result)


def test_verify_rejects_result_pointing_at_nonexistent_query():
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    result["query_id"] = "no_such_query"
    with pytest.raises(ValueError, match="no_such_query"):
        themis.verify(program, result)


def test_verify_rejects_non_dict_result():
    with pytest.raises(TypeError, match="result must be a dict"):
        themis.verify(_cause_program(), "not a dict")  # type: ignore[arg-type]


# ======================================== schema tightening pins

def test_result_schema_rejects_malformed_derivation_payload():
    """The derivation field now $refs derivation.schema.json. A
    result whose derivation has the wrong version / kind must be
    rejected at the outer validator, not silently passed through."""
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    result["derivation"]["kind"] = "bogus_kind"
    with pytest.raises(SyntacticError):
        validate_result(result)


def test_result_schema_rejects_derivation_with_missing_steps_field():
    program = _cause_program()
    result = copy.deepcopy(themis.run(program)["results"][0])
    del result["derivation"]["steps"]
    with pytest.raises(SyntacticError):
        validate_result(result)


def test_result_schema_accepts_result_without_derivation_field():
    """The field is optional — results that omit it must still
    validate. Regression guard against the tightening accidentally
    becoming required."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": atom("y"), "value": True},
                       "intervention": {"atom": atom("x"), "value": True},
                       "given": []}},
        ],
    }
    result = themis.run(program)["results"][0]
    # needs_investigation, no derivation attached
    assert "derivation" not in result
    validate_result(result)
