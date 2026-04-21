"""Pin that ``to_dict(QueryResult)`` carries the derivation chain as
structured JSON when the runtime attached one.

Before this slice, the kernel's JSON output exposed the final formula
and structural / numeric verdict but hid the step-by-step reasoning
the verifier needs. For an LLM / external agent to tell a backdoor
answer apart from a front-door one — or to re-run the verifier
against the returned payload — the derivation must cross the JSON
boundary. These tests pin exactly that:

- Identify / effect / assoc results carry a non-empty ``derivation``
  field under the ``derivation.schema.json`` shape
- The derivation round-trips through
  ``themis.verifier.serialization.derivation_from_dict`` +
  ``verify_identify`` / ``verify_cause`` / ``verify_assoc``
- Results without a derivation (e.g. needs_investigation without an
  attached chain) simply omit the field
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis
from themis.verifier import (
    VerificationContext,
    derivation_from_dict,
    verify_cause,
    verify_identify,
)

FIXTURES = Path(__file__).parent / "test_e2e" / "fixtures"


def _run(ast: dict) -> list[dict]:
    return themis.run(ast)["results"]


def _minimal_cause_program() -> dict:
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": atom("x"), "to": atom("y")}},
        ],
    }


def _minimal_identify_program() -> dict:
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "identify",
                       "target": atom("y"),
                       "intervention": {"atom": atom("x"), "value": True},
                       "given": []}},
        ],
    }


# ============================================================ presence

def test_cause_result_json_carries_derivation():
    r = _run(_minimal_cause_program())[0]
    assert "derivation" in r
    assert r["derivation"]["kind"] == "derivation"
    assert r["derivation"]["version"] == "0.1"
    assert len(r["derivation"]["steps"]) >= 1


def test_identify_result_json_carries_backdoor_derivation():
    r = _run(_minimal_identify_program())[0]
    assert "derivation" in r
    steps = r["derivation"]["steps"]
    assert [s["rule"] for s in steps] == [
        "graph_is_dag",
        "backdoor_criterion",
        "backdoor_adjustment_formula",
        "identify_via_backdoor",
    ]


def test_identify_json_distinguishes_backdoor_from_front_door():
    """The original gap that motivated this slice: LLM consumers need
    to tell identification strategies apart. Back-door is the only
    path that fires in a DAG with no confounders, so the final rule
    must be backdoor — if we later wire a front-door test case, the
    same field distinguishes them."""
    r = _run(_minimal_identify_program())[0]
    final = r["derivation"]["steps"][-1]["rule"]
    assert final in ("identify_via_backdoor", "identify_via_front_door")


# ========================================================== round-trip

def test_derivation_in_json_round_trips_through_verifier():
    """Full loop: JSON out → derivation_from_dict → verify_identify
    accepts. This is the contract that lets an external agent audit
    the answer without importing Python internals."""
    from themis.input.parser import parse_json
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.runtime.graph_projection import project
    from themis.runtime.instantiation import instantiate
    from themis.runtime.scheduler import dispatch_all
    from themis.types import IdentifyQuery, StructuralResult

    ast_dict = _minimal_identify_program()

    # Run through the kernel twice so we have both the typed result
    # (for StructuralResult / VerificationContext construction) and
    # the JSON form (for derivation_from_dict).
    ast = validate_ast(json.loads(json.dumps(ast_dict)))
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    typed_results = dispatch_all(prog, graph)
    typed_r = typed_results[0]

    json_r = themis.run(ast_dict)["results"][0]
    decoded = derivation_from_dict(json_r["derivation"])

    # Build a context matching the query that was run
    q_stmt = next(
        s for s in prog.statements
        if hasattr(s, "id") and getattr(s, "id", None) == "q"
    )
    assert isinstance(q_stmt.query, IdentifyQuery)
    ctx = VerificationContext(graph=graph, query=q_stmt.query)

    # Verify the decoded derivation proves the same claim.
    verify_identify(decoded, ctx, typed_r.structural_result)


def test_cause_derivation_round_trips_through_verify_cause():
    from themis.input.parser import parse_json
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.runtime.graph_projection import project
    from themis.runtime.instantiation import instantiate
    from themis.runtime.scheduler import dispatch_all
    from themis.types import CauseQuery

    ast_dict = _minimal_cause_program()
    ast = validate_ast(json.loads(json.dumps(ast_dict)))
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    typed_r = dispatch_all(prog, graph)[0]

    json_r = themis.run(ast_dict)["results"][0]
    decoded = derivation_from_dict(json_r["derivation"])

    q_stmt = next(
        s for s in prog.statements
        if hasattr(s, "id") and getattr(s, "id", None) == "q"
    )
    assert isinstance(q_stmt.query, CauseQuery)
    ctx = VerificationContext(graph=graph, query=q_stmt.query)
    verify_cause(decoded, ctx, typed_r.structural_result)


# ============================================================= absence

def test_needs_investigation_without_derivation_omits_field():
    """Program with no edges → identify/effect queries land in
    ``needs_investigation`` with empty derivation. JSON omits the
    field entirely (following the same optional-absent convention as
    the rest of to_dict)."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    ast = {
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
    r = themis.run(ast)["results"][0]
    assert r["status"] == "needs_investigation"
    # Derivation is empty here (numeric needed Theta, none provided, no
    # structural witness was attached by scheduler) — must be absent.
    assert "derivation" not in r


# ======================================================== schema check

def test_result_json_with_derivation_validates_against_schema():
    from themis.input.syntactic_validator import validate_result
    r = _run(_minimal_identify_program())[0]
    validate_result(r)


# ========================================================= json-stable

def test_json_with_derivation_round_trips_through_json_dumps():
    r = _run(_minimal_identify_program())[0]
    text = json.dumps(r, ensure_ascii=False)
    assert json.loads(text) == r
