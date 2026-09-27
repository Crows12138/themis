"""Slice A1: pin that each NL→kernel_ast prompt example is actually valid.

The examples under ``themis/prompts/examples/`` are few-shot cases an LLM
consumes to learn how to produce canonical kernel_ast output. If the
``kernel_ast`` field in any example drifts from a schema-valid shape
or stops matching its own stated NL intent, the prompt becomes
self-inconsistent — this test catches that.

Each example must:

1. Carry a non-empty ``nl_input`` and a ``kernel_ast`` object
2. Round-trip through ``themis.run`` without raising
3. Produce exactly one query result
4. Carry a ``define_variable`` investigation request whose items
   cover every declared variable (i.e. the prompt's deliberate
   "leave framing blank" convention really does flag the user for
   follow-up)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis

EXAMPLES_DIR = (
    Path(__file__).resolve().parents[2]
    / "themis"
    / "prompts"
    / "examples"
)


def _load_examples():
    """Load question-side examples only.

    A1 examples carry a ``kernel_ast`` field (full program ready for
    themis.run). Sibling prompt families (A5 narrative,
    slice #40 reply) live in the same folder but expose other
    shapes and are validated separately in their own test modules.
    Filter by filename prefix.
    """
    skip_prefixes = ("narrative_", "reply_")
    files = [
        p for p in sorted(EXAMPLES_DIR.glob("*.json"))
        if not any(p.stem.startswith(pfx) for pfx in skip_prefixes)
    ]
    assert files, f"no question examples found under {EXAMPLES_DIR}"
    return [pytest.param(path, id=path.stem) for path in files]


@pytest.mark.parametrize("example_path", _load_examples())
def test_example_kernel_ast_runs_through_themis(example_path):
    payload = json.loads(example_path.read_text(encoding="utf-8"))

    assert "nl_input" in payload and payload["nl_input"], (
        f"{example_path.name}: missing or empty nl_input"
    )
    assert "kernel_ast" in payload, (
        f"{example_path.name}: missing kernel_ast"
    )

    out = themis.run(payload["kernel_ast"])
    assert "results" in out
    assert len(out["results"]) == 1, (
        f"{example_path.name}: expected 1 query result, got {len(out['results'])}"
    )


@pytest.mark.parametrize("example_path", _load_examples())
def test_example_flags_every_declared_predicate_for_framing(example_path):
    """The prompt convention is 'leave framing fields unset so the user
    fills them next turn'. If that convention is honored, every declared
    predicate must be surfaced back to the caller — either through the
    DEFINE_VARIABLE workflow channel or, for purely structural queries,
    through framing_notes."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    ast = payload["kernel_ast"]

    declared = {
        s["predicate"] for s in ast["statements"]
        if s.get("kind") == "variable"
    }
    # What the brainstorm adds around the question — common causes, the
    # steps of the mechanism, other causes of the outcome — is llm_proposal
    # structure, not a variable the user named: the kernel surfaces its data
    # need through the data-gap channel (missing adjustment data /
    # unmeasured_confounder_risk), NOT the framing channel, which covers the
    # variables the question itself is about.
    added = {
        p["name"] for p in payload.get("reasoning", {}).get("predicates", [])
        if p.get("role") in ("confounder", "mediator", "other_cause")
    }
    expected = declared - added
    out = themis.run(ast)
    r = out["results"][0]
    define_reqs = [
        req for req in r.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    if define_reqs:
        flagged = {item["target"] for item in define_reqs[0]["items"]}
    else:
        flagged = {note["predicate"] for note in r.get("framing_notes", [])}
    assert flagged, (
        f"{example_path.name}: prompt example did not surface framing gaps "
        f"through either define_variable or framing_notes"
    )
    assert flagged == expected, (
        f"{example_path.name}: framing-flagged set {flagged} should match "
        f"the declared variables minus those the brainstorm added {expected} "
        f"(those surface via the data-gap channel, not framing)"
    )


@pytest.mark.parametrize("example_path", _load_examples())
def test_example_output_is_json_serializable(example_path):
    """The structured result must survive json.dumps — that is the
    canonical JSON contract examples must demonstrate."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    out = themis.run(payload["kernel_ast"])
    round_tripped = json.loads(json.dumps(out, ensure_ascii=False))
    assert round_tripped == out


def test_temporal_example_lifts_lag_into_time_index_instead_of_ambiguity():
    """Phase 5 §T / S.T.6: a clean t-1 -> t question should be encoded
    directly with time_index, not downgraded to a temporal ambiguity.

    Asked as an effect (#783): whether staying up late changes the next
    morning is a question about the world, and the night's other
    circumstances are drawn at the same step as staying up."""
    path = EXAMPLES_DIR / "late_night_tired_temporal.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ast = payload["kernel_ast"]
    before, now = {"kind": "relative", "value": -1}, {"kind": "relative", "value": 0}

    query = next(
        s for s in ast["statements"]
        if s.get("kind") == "query"
    )["query"]
    assert query["kind"] == "effect"
    assert query["intervention"]["atom"]["time_index"] == before
    assert query["target"]["atom"]["time_index"] == now

    # Every edge ends where the question does or at the night before it,
    # and none runs backwards in time.
    for edge in (s for s in ast["statements"] if s.get("kind") == "cause"):
        assert edge["from"]["time_index"] == before
        assert edge["to"]["time_index"] in (before, now)

    ambiguities = ast.get("extensions", {}).get("ambiguities", [])
    assert all(item.get("kind") != "temporal" for item in ambiguities)

    r = themis.run(ast)["results"][0]
    assert r["query_kind"] == "effect"
    assert r["status"] == "needs_investigation"
    assert r["missing_information"]


def test_counterfactual_example_lifts_case17_into_counterfactual_query():
    """Phase 5 §C / S.C.6: a clean '如果当初...' example should emit a
    real counterfactual query, not an effect proxy or ambiguity."""
    path = EXAMPLES_DIR / "career_choice_counterfactual.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    ast = payload["kernel_ast"]

    query_stmt = next(
        s for s in ast["statements"]
        if s.get("kind") == "query"
    )
    assert query_stmt["query"]["kind"] == "counterfactual"
    assert "assumptions" not in query_stmt["query"]

    ambiguities = ast.get("extensions", {}).get("ambiguities", [])
    assert all(item.get("kind") != "counterfactual_query" for item in ambiguities)

    out = themis.run(ast)
    r = out["results"][0]
    # The example declares no monotonicity, which no longer blocks anything:
    # what it is short of is the distribution.
    assert r["status"] == "needs_investigation"
    assert r["missing_information"]
    assert all(
        item["kind"] == "parameter" for item in r["missing_information"]
    )
