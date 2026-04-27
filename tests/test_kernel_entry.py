"""Tests for the top-level ``themis.run`` JSON-in/JSON-out entry.

These pin the single public surface through which external callers
(LLM agents, CLIs, future MCP servers) drive the kernel. They verify
input / output boundary behavior, not internal reasoning — deeper
reasoning semantics are already covered by the runtime / verifier
suites.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis
from themis.input.semantic_validator import SemanticError
from themis.input.syntactic_validator import SyntacticError, validate_result

FIXTURES = Path(__file__).parent / "test_e2e" / "fixtures"


def _minimal_effect_program() -> dict:
    """A self-contained JSON AST matching the W0 driving case: two bool
    predicates, one edge, one effect query. No Theta — the run must
    still produce a valid structured result."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "variable", "predicate": "running",
                "domain": [True, False],
            },
            {
                "kind": "variable", "predicate": "belly_fat_loss",
                "domain": [True, False],
            },
            {
                "kind": "cause",
                "from": {"predicate": "running",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "belly_fat_loss",
                       "args": [{"type": "const", "name": "me"}]},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "target": {
                        "atom": {"predicate": "belly_fat_loss",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "intervention": {
                        "atom": {"predicate": "running",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                },
            },
        ],
    }


def test_run_accepts_dict_and_returns_results_envelope():
    out = themis.run(_minimal_effect_program())
    assert isinstance(out, dict)
    assert set(out.keys()) == {"results", "program"}
    assert isinstance(out["results"], list)
    assert len(out["results"]) == 1


def test_run_echoes_program_with_extensions_for_response_renderer():
    """Subagent real-test caught: program-level extensions.ambiguities
    were lost between input and output, breaking response_rendering's
    'orchestrator passes the original program' assumption. Run now
    echoes the validated program so renderers always have access."""
    program = _minimal_effect_program()
    program["extensions"] = {
        "ambiguities": [{
            "kind": "reciprocal_causation",
            "description": "X ↔ Y plausible both ways",
            "committed_direction": "X→Y",
        }],
    }
    out = themis.run(program)
    echoed = out["program"]
    assert echoed["extensions"]["ambiguities"][0]["kind"] == (
        "reciprocal_causation"
    )


def test_run_accepts_json_string():
    out = themis.run(json.dumps(_minimal_effect_program()))
    assert len(out["results"]) == 1
    assert out["results"][0]["query_id"] == "q"


def test_run_accepts_json_bytes():
    out = themis.run(json.dumps(_minimal_effect_program()).encode("utf-8"))
    assert len(out["results"]) == 1


def test_run_output_conforms_to_query_result_schema():
    """Every returned result must validate against
    ``query_result.schema.json`` — this is the kernel's public output
    contract."""
    out = themis.run(_minimal_effect_program())
    for r in out["results"]:
        validate_result(r)


def test_run_surfaces_define_variable_in_json_output():
    """The real-case driver: running / belly_fat_loss underframed,
    effect query runs, and the resulting JSON must contain a
    ``define_variable`` investigation request naming both predicates'
    framing gaps."""
    out = themis.run(_minimal_effect_program())
    r = out["results"][0]
    assert r["status"] == "needs_investigation"
    assert r["query_kind"] == "effect"

    define_reqs = [
        req for req in r.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    assert len(define_reqs) == 1
    targets = {item["target"] for item in define_reqs[0]["items"]}
    assert targets == {"running", "belly_fat_loss"}
    for item in define_reqs[0]["items"]:
        fields = set(item["skeleton"]["fields"].keys())
        assert fields == {
            "time_window", "measurement", "threshold", "observability",
            "direction", "baseline", "state_vs_event",
        }


def test_run_output_is_json_serializable():
    """The returned dict must survive json.dumps cleanly — that is the
    definition of "kernel output is JSON"."""
    out = themis.run(_minimal_effect_program())
    text = json.dumps(out, ensure_ascii=False)
    reloaded = json.loads(text)
    assert reloaded == out


def test_run_rejects_non_supported_input_type():
    with pytest.raises(TypeError, match="dict / str / bytes"):
        themis.run(12345)  # type: ignore[arg-type]


def test_run_rejects_malformed_json_string():
    with pytest.raises(json.JSONDecodeError):
        themis.run("{not valid json")


def test_run_rejects_syntactically_invalid_ast():
    with pytest.raises(SyntacticError):
        themis.run({"version": "0.1", "statements": "not a list"})


def test_run_caller_dict_is_not_mutated():
    """Run should treat the caller's dict as read-only — no in-place
    mutation of nested structures."""
    program = _minimal_effect_program()
    before = json.dumps(program, sort_keys=True)
    themis.run(program)
    after = json.dumps(program, sort_keys=True)
    assert before == after


def test_run_on_fully_parameterized_fixture_produces_numeric_result():
    """Smoke test: a fixture known to resolve to ``numerically_solved``
    still does so through the top-level entry."""
    fixture = FIXTURES / "numeric_backdoor.json"
    out = themis.run(fixture.read_text(encoding="utf-8"))
    kinds = {r["query_kind"] for r in out["results"]}
    assert "effect" in kinds or "probability" in kinds
    # at least one numerically_solved expected
    statuses = {r["status"] for r in out["results"]}
    assert "numerically_solved" in statuses
