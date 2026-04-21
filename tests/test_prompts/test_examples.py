"""Slice A1: pin that each NL→kernel_ast prompt example is actually valid.

The examples under ``docs/prompts/examples/`` are few-shot cases an LLM
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
    / "docs"
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
    predicate must appear in the DEFINE_VARIABLE investigation items."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    ast = payload["kernel_ast"]

    declared = {
        s["predicate"] for s in ast["statements"]
        if s.get("kind") == "variable"
    }
    out = themis.run(ast)
    r = out["results"][0]
    define_reqs = [
        req for req in r.get("investigation_requests", [])
        if req["action"] == "define_variable"
    ]
    assert define_reqs, (
        f"{example_path.name}: no define_variable request — prompt "
        f"example must demonstrate the framing-gap feedback loop"
    )
    flagged = {item["target"] for item in define_reqs[0]["items"]}
    assert flagged == declared, (
        f"{example_path.name}: declared predicates {declared} do not "
        f"match flagged set {flagged}"
    )


@pytest.mark.parametrize("example_path", _load_examples())
def test_example_output_is_json_serializable(example_path):
    """The structured result must survive json.dumps — that is the
    canonical JSON contract examples must demonstrate."""
    payload = json.loads(example_path.read_text(encoding="utf-8"))
    out = themis.run(payload["kernel_ast"])
    round_tripped = json.loads(json.dumps(out, ensure_ascii=False))
    assert round_tripped == out
