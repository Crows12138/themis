"""Phase 5 §T / S.T.1: time-indexed atom surface only.

This slice is deliberately representation-only:

- ``atom.schema.json`` accepts a relative ``time_index`` and rejects
  unsupported shapes.
- ``validate_program`` parses it into typed ``Atom`` objects.
- Program / QueryResult / derivation / verification-context JSON
  round-trips preserve the field exactly.

No temporal graph semantics land here yet.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx
import pytest

from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast, validate_result
from themis.kernel import _program_to_ast_dict
from themis.output.result_orchestrator import to_dict as result_to_dict
from themis.types import (
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    DerivationStep,
    ProbabilityRefExpr,
    QueryKind,
    QueryResult,
    RelativeTimeIndex,
    ResultStatus,
    StructuralResult,
    ValuedAtom,
)
from themis.verifier import (
    VerificationContext,
    context_from_dict,
    context_to_dict,
    derivation_from_dict,
    derivation_to_dict,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DERIVATION_SCHEMA_PATH = PROJECT_ROOT / "themis" / "schemas" / "derivation.schema.json"
CONTEXT_SCHEMA_PATH = PROJECT_ROOT / "themis" / "schemas" / "verification_context.schema.json"


def _timed_atom(pred: str, t: int, obj: str = "me") -> dict:
    return {
        "predicate": pred,
        "args": [{"type": "const", "name": obj}],
        "time_index": {"kind": "relative", "value": t},
    }


def _typed_atom(pred: str, t: int, obj: str = "me") -> Atom:
    return Atom(
        predicate=pred,
        args=(ConstTerm(name=obj),),
        time_index=RelativeTimeIndex(value=t),
    )


def _validate_schema(payload: dict, path: Path) -> None:
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    schema = json.loads(path.read_text(encoding="utf-8"))
    jsonschema.validate(payload, schema)


def test_atom_schema_accepts_relative_time_index():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late", "domain": [True, False]},
            {"kind": "variable", "predicate": "feels_tired", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _timed_atom("stays_up_late", -1),
                "to": _timed_atom("feels_tired", 0),
            },
        ],
    }
    out = validate_ast(ast)
    assert isinstance(out, dict)


def test_atom_schema_rejects_non_relative_time_index_kind():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": {
                    "predicate": "x",
                    "args": [{"type": "const", "name": "me"}],
                    "time_index": {"kind": "absolute", "value": "2026-04-22"},
                },
                "to": _timed_atom("y", 0),
            },
        ],
    }
    with pytest.raises(SyntacticError):
        validate_ast(ast)


def test_validate_program_parses_typed_time_index():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _timed_atom("x", -1),
                "to": _timed_atom("y", 0),
            },
            {
                "kind": "query",
                "id": "q1",
                "query": {
                    "kind": "cause",
                    "from": _timed_atom("x", -1),
                    "to": _timed_atom("y", 0),
                },
            },
        ],
    }
    prog = validate_program(validate_ast(ast), checks=frozenset())
    cause_stmt = next(s for s in prog.statements if isinstance(s, CauseStatement))
    cause_query = next(s.query for s in prog.statements if getattr(s, "id", None) == "q1")

    assert cause_stmt.from_atom.time_index == RelativeTimeIndex(value=-1)
    assert cause_stmt.to_atom.time_index == RelativeTimeIndex(value=0)
    assert isinstance(cause_query, CauseQuery)
    assert cause_query.from_atom.time_index == RelativeTimeIndex(value=-1)
    assert cause_query.to_atom.time_index == RelativeTimeIndex(value=0)


def test_program_serializer_round_trip_preserves_time_index():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _timed_atom("x", -1),
                "to": _timed_atom("y", 0),
            },
        ],
    }
    prog = validate_program(validate_ast(ast), checks=frozenset())
    emitted = _program_to_ast_dict(prog)

    cause = next(s for s in emitted["statements"] if s["kind"] == "cause")
    assert cause["from"]["time_index"] == {"kind": "relative", "value": -1}
    assert cause["to"]["time_index"] == {"kind": "relative", "value": 0}

    prog2 = validate_program(emitted, checks=frozenset())
    assert prog2 == prog


def test_query_result_formula_json_preserves_time_index():
    x = _typed_atom("stays_up_late", -1)
    y = _typed_atom("feels_tired", 0)
    result = QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.IDENTIFY,
        query_id="q_temporal",
        structural_result=StructuralResult(value=True),
        formula=ProbabilityRefExpr(
            target=ValuedAtom(atom=y, value=True),
            given=(ValuedAtom(atom=x, value=True),),
        ),
    )
    payload = result_to_dict(result)
    validate_result(payload)
    assert payload["formula"]["target"]["atom"]["time_index"] == {
        "kind": "relative",
        "value": 0,
    }
    assert payload["formula"]["given"][0]["atom"]["time_index"] == {
        "kind": "relative",
        "value": -1,
    }


def test_derivation_round_trip_preserves_time_index():
    x = _typed_atom("x", -1)
    y = _typed_atom("y", 0)
    derivation = (
        DerivationStep(rule="debug_rule", inputs={"src": x}, output=y, step_id="s1"),
    )
    payload = derivation_to_dict(derivation)
    _validate_schema(payload, DERIVATION_SCHEMA_PATH)
    assert payload["steps"][0]["inputs"]["src"]["time_index"] == {
        "kind": "relative",
        "value": -1,
    }
    back = derivation_from_dict(payload)
    assert back == derivation


def test_verification_context_round_trip_preserves_time_index():
    x = _typed_atom("x", -1)
    y = _typed_atom("y", 0)
    g = nx.DiGraph()
    g.add_nodes_from([x, y])
    g.add_edge(x, y)
    ctx = VerificationContext(graph=g, query=CauseQuery(from_atom=x, to_atom=y))
    payload = context_to_dict(ctx)
    _validate_schema(payload, CONTEXT_SCHEMA_PATH)
    assert payload["graph"]["nodes"][0]["time_index"] in (
        {"kind": "relative", "value": -1},
        {"kind": "relative", "value": 0},
    )
    assert payload["query"]["from_atom"]["time_index"] == {
        "kind": "relative",
        "value": -1,
    }
    assert payload["query"]["to_atom"]["time_index"] == {
        "kind": "relative",
        "value": 0,
    }
    back = context_from_dict(payload)
    assert back.query == ctx.query
    assert set(back.graph.nodes()) == set(ctx.graph.nodes())
    assert set(back.graph.edges()) == set(ctx.graph.edges())
