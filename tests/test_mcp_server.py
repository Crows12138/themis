"""Tests for the Themis MCP server (slice A1(b)).

The server is JSON-in/JSON-out — these tests drive it through the
FastMCP in-process API (no stdio transport, no LLM client) to confirm
tool dispatch and resource serving work end to end.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

import themis
from themis.mcp import build_server
from tests import caveats


REPO_ROOT = Path(__file__).resolve().parents[1]


# ============================================ fixtures


@pytest.fixture
def app():
    return build_server()


# ============================================ wiring


def test_server_constructs_with_expected_tools(app):
    tool_names = {t.name for t in asyncio.run(app.list_tools())}
    assert tool_names == {
        "themis_run",
        "themis_apply_patch_and_run",
        "themis_result",  # a part of a result the server holds
        "themis_guide",  # the prompts and schemas, a section at a time
        "themis_audit",
        "themis_verify",
        "themis_verify_data_gap_report",
        "themis_verify_bounds_results",
        "themis_verify_markov_blanket",  # borrow-list #4
        "themis_verify_lagged_discovery",  # #449
        "themis_verify_latent_lagged_discovery",  # #496
        "themis_verify_notears_fit",  # #462
        "themis_verify_selection_recovery_numeric",  # §S9.1 numeric end
        "themis_verify_missing_data_numeric",  # §S9.2 numeric end
        "themis_estimate",
        "themis_discover",
        "themis_markov_blanket",  # borrow-list #4
        "themis_discover_lagged_graph",  # #449
        "themis_discover_latent_lagged_graph",  # #496
        "themis_discover_notears",  # #462
        "themis_report",  # deterministic analyze → verify → Markdown report
        "themis_submit_verdict",  # v0.1.5 Fix 2A
        "themis_list_resources",
    }


def test_server_exposes_prompt_and_schema_resources(app):
    uris = {str(r.uri) for r in asyncio.run(app.list_resources())}
    # core prompts
    assert "themis://prompts/nl_to_kernel_ast.md" in uris
    assert "themis://prompts/response_rendering.md" in uris
    # Phase 11.1 — agent loop closure
    assert "themis://prompts/gap_to_action.md" in uris
    # Phase 11.2 — KB adapter contract
    assert "themis://prompts/kb_lookup.md" in uris
    # schemas
    assert "themis://schemas/kernel_ast.schema.json" in uris
    assert "themis://schemas/query_result.schema.json" in uris
    # Phase 11.2 — KB schemas
    assert "themis://schemas/kb_query.schema.json" in uris
    assert "themis://schemas/kb_result.schema.json" in uris


# ============================================ tool behavior


def _call_tool(app, name: str, args: dict) -> dict:
    """Drive a tool through FastMCP's call_tool API and parse the JSON result.

    FastMCP serializes tool returns as a list of content blocks; for
    dict-returning tools each block is a TextContent with JSON in `.text`.
    """
    blocks = asyncio.run(app.call_tool(name, args))
    for block in blocks:
        text = getattr(block, "text", None)
        if text:
            return json.loads(text)
    raise AssertionError(f"no text content in tool result: {blocks!r}")


def test_themis_run_tool_executes_kernel(app):
    """The simplest possible end-to-end: load a fixture, call themis_run, get a result envelope."""
    fixture = REPO_ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json"
    program = json.loads(fixture.read_text(encoding="utf-8"))

    out = _call_tool(app, "themis_run", {"program": program})

    assert "results" in out
    assert isinstance(out["results"], list)
    assert len(out["results"]) >= 1
    # An assoc query should at least carry status
    assert "status" in out["results"][0]


def test_themis_verify_tool_returns_ok_dict(app):
    """themis_verify wraps exceptions into {ok: bool, error?: str}."""
    fixture = REPO_ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json"
    program = json.loads(fixture.read_text(encoding="utf-8"))
    run_out = _call_tool(app, "themis_run", {"program": program})

    verify_out = _call_tool(
        app, "themis_verify",
        {"program": program, "result": run_out["results"][0]},
    )
    assert verify_out == {"ok": True}


def test_themis_verify_tool_returns_error_on_bad_result(app):
    fixture = REPO_ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json"
    program = json.loads(fixture.read_text(encoding="utf-8"))

    bad_result = {"status": "obviously_invalid", "query_kind": "assoc"}
    out = _call_tool(app, "themis_verify", {"program": program, "result": bad_result})
    assert out["ok"] is False
    assert "error" in out
    assert isinstance(out["error"], str) and out["error"]


def test_themis_markov_blanket_tool_round_trips(app, tmp_path):
    """themis_markov_blanket screens a target from a CSV; the emitted result
    passes themis_verify_markov_blanket, and a tampered one is rejected."""
    import numpy as np
    import pandas as pd

    rng = np.random.default_rng(0)
    n = 3000
    x1 = rng.standard_normal(n)
    t = 1.5 * x1 + 0.5 * rng.standard_normal(n)
    y = 1.3 * t + 0.5 * rng.standard_normal(n)
    noise = rng.standard_normal(n)
    csv = tmp_path / "mb.csv"
    pd.DataFrame({"T": t, "X1": x1, "Y": y, "noise": noise}).to_csv(csv, index=False)

    mb = _call_tool(
        app, "themis_markov_blanket",
        {"csv_path": str(csv), "target": "T"},
    )
    assert mb["kind"] == "markov_blanket"
    assert set(mb["blanket"]) == {"X1", "Y"}

    ok = _call_tool(app, "themis_verify_markov_blanket", {"result": mb})
    assert ok == {"ok": True}

    mb["blanket"] = sorted(mb["blanket"] + ["noise"])  # fabricate a member
    bad = _call_tool(app, "themis_verify_markov_blanket", {"result": mb})
    assert bad["ok"] is False and bad["error"]


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _dose_response_diagnostic_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "curve"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "engagement", "domain": [1, 2, 3, 4, 5]},
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "cause", "from": _atom("raise_amount"), "to": _atom("engagement")},
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("raise_amount"), "value": True},
                    "target": {"atom": _atom("engagement"), "value": 4},
                    "given": [],
                },
            },
        ],
    }


def test_themis_verify_data_gap_report_accepts_diagnostic_result(app):
    program = _dose_response_diagnostic_program()
    run_out = _call_tool(app, "themis_run", {"program": program})
    result = run_out["results"][0]
    assert "derivation" not in result
    assert result.get("data_gap_report") is not None

    out = _call_tool(app, "themis_verify_data_gap_report", {"result": result})
    assert out == {"ok": True}


def test_themis_report_tool_renders_markdown(app):
    """themis_report runs + verifies + returns one Markdown report per query."""
    fixture = REPO_ROOT / "tests" / "test_e2e" / "fixtures" / "assoc_canonical.json"
    program = json.loads(fixture.read_text(encoding="utf-8"))

    out = _call_tool(app, "themis_report", {"program": program})
    assert "reports" in out and isinstance(out["reports"], list) and out["reports"]
    assert out["reports"][0].startswith("# 因果分析报告")
    assert "statuses" in out and out["statuses"]


def test_themis_report_stamps_an_answer_that_carries_no_chain(app):
    """The stamp used to be gated on a derivation, so an answer that is an
    interval — the commonest shape without one — came back unstamped even
    though ``verify_bounds_results`` recomputes both endpoints from the
    graph. Which re-checks apply is themis.audit's question now."""
    def _atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "p"}]}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }
    out = _call_tool(app, "themis_report", {"program": program})
    report = out["reports"][0]
    assert "verify_bounds_results" in report
    assert "独立复核全部通过" in report


def test_report_reads_the_one_program_key_both_its_entry_points_write():
    """Pins the envelope key ``themis_report``'s fall-back chain rests on.

    The tool has to recover the AST the kernel actually ran on, and it
    does so by key: ``env.get("program")``. The chain once also tried
    ``merged_program`` — which is ``apply_patch_and_run``'s key, and
    which neither of this tool's two entry points writes — so that
    branch could never fire, while the comment beside it described a
    route into the tool that did not exist.

    A wrong key here fails silently rather than loudly: the lookup just
    falls through to the caller's raw argument, which may still be an
    unparsed JSON string, and the report is then assembled with
    ``program=None`` — losing the framing and provenance sections with
    no error anywhere. That makes the key a thing to test rather than a
    thing to remember: move ``run``'s or ``estimate``'s echo and this
    goes red, so the fall-back gets told instead of quietly rotting.
    """
    import pandas as pd

    def _atom(p):
        return {"predicate": p, "args": []}

    program = {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in ("x", "y", "z")
        ] + [
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }
    rows = [
        (x, y, z)
        for z in (True, False) for x in (True, False) for y in (True, False)
    ] * 25
    data = pd.DataFrame(rows, columns=["x", "y", "z"])

    # The two entry points themis_report actually calls.
    assert "program" in themis.run(program)
    assert "program" in themis.estimate(program, data)
    # And the third one, which it does not — named here so that the key
    # the fall-back chain must NOT reach for stays visibly someone else's.
    patched = themis.apply_patch_and_run(program, [])
    assert "merged_program" in patched and "program" not in patched


def test_themis_list_resources_tool_returns_uri_catalog(app):
    out = _call_tool(app, "themis_list_resources", {})
    assert "prompts" in out and "schemas" in out
    assert any("nl_to_kernel_ast.md" in u for u in out["prompts"])
    assert any("kernel_ast.schema.json" in u for u in out["schemas"])


# ============================================ resource serving


def test_resource_serves_prompt_text(app):
    resources = asyncio.run(app.list_resources())
    target = next(
        (r for r in resources if str(r.uri) == "themis://prompts/nl_to_kernel_ast.md"),
        None,
    )
    assert target is not None

    content = asyncio.run(app.read_resource(target.uri))
    # FastMCP's read_resource returns an iterable of content blocks; each
    # has a `.content` field carrying the text.
    blocks = list(content)
    assert blocks, "expected at least one content block"
    text = blocks[0].content if hasattr(blocks[0], "content") else str(blocks[0])
    assert "kernel_ast" in text.lower() or "nl" in text.lower()


def test_resource_serves_valid_schema_json(app):
    resources = asyncio.run(app.list_resources())
    target = next(
        (r for r in resources if str(r.uri) == "themis://schemas/kernel_ast.schema.json"),
        None,
    )
    assert target is not None

    content = asyncio.run(app.read_resource(target.uri))
    blocks = list(content)
    text = blocks[0].content if hasattr(blocks[0], "content") else str(blocks[0])
    parsed = json.loads(text)  # must be valid JSON
    # kernel_ast schema declares a top-level $id or "title" or "$schema"
    assert any(k in parsed for k in ("$id", "$schema", "title", "type"))


# ================================================= gap_kinds round-trip


@pytest.mark.parametrize("case_file,expected_kind", [
    ("case_001_hrt_cvd.json", "unmeasured_confounder_risk"),
    (
        "case_009_mediation_x_transport.json",
        "unattempted_layer_due_to_dispatch_conflict",
    ),
])
def test_new_gap_kinds_round_trip_through_mcp(
    app, case_file: str, expected_kind: str,
):
    """Every gap_kind must propagate through the MCP themis_run tool
    with its ⚠ caveat reaching result.explanation. Same pattern as the
    web /api/run regression test; MCP is also a thin pass-through, but
    serialization quirks (FastMCP JSON content blocks) deserve their
    own pin."""
    program = json.loads(
        (REPO_ROOT / "docs" / "l3_simulation" / case_file).read_text(
            encoding="utf-8"
        )
    )
    out = _call_tool(app, "themis_run", {"program": program})
    result = out["results"][0]
    gap_kinds = [
        g["kind"] for g in result.get("data_gap_report", {}).get("gaps", [])
    ]
    assert expected_kind in gap_kinds, (
        f"{case_file}: expected {expected_kind!r} in gap_kinds; got {gap_kinds}"
    )
    explanation = caveats.text(result)
    assert "⚠" in explanation, (
        f"{case_file}: must-disclose ⚠ caveat should be in explanation"
    )

    # And the data-gap report itself round-trips through verify
    verify_out = _call_tool(
        app, "themis_verify_data_gap_report", {"result": result}
    )
    assert verify_out.get("ok") is True, (
        f"{case_file}: themis_verify_data_gap_report should accept; got {verify_out}"
    )


# ============================================ v0.1.5 Fix 2A — submit_verdict


def test_submit_verdict_accepts_yes(app):
    """Happy path: the agent commits 'yes' through the typed channel."""
    out = _call_tool(app, "themis_submit_verdict", {
        "verdict": "yes",
        "question": "Does running cause weight loss in adults?",
        "justification": "Backdoor-adjusted ATE = 0.18 (95% CI 0.12-0.24)",
        "kernel_query_id": "q1",
    })
    assert out["ok"] is True
    assert out["verdict"] == "yes"
    assert "running cause weight loss" in out["question_excerpt"]
    assert out["kernel_query_id"] == "q1"


def test_submit_verdict_accepts_no(app):
    out = _call_tool(app, "themis_submit_verdict", {
        "verdict": "no",
        "question": "Does medication negatively affect heart through BP?",
    })
    assert out["verdict"] == "no"


def test_submit_verdict_accepts_needs_more_info(app):
    """The third allowed value — for when the kernel returned
    needs_investigation or bounds-only and the agent can't commit."""
    out = _call_tool(app, "themis_submit_verdict", {
        "verdict": "needs_more_info",
        "question": "Does X cause Y?",
        "justification": "Kernel returned needs_investigation: missing P(Y|X,W)",
    })
    assert out["verdict"] == "needs_more_info"


def test_submit_verdict_rejects_freeform_verdict(app):
    """The schema's whole point: anything outside the three allowed
    values must fail loudly. FastMCP surfaces the ValueError as a
    ToolError exception across the protocol boundary (matching how
    JSON-schema enum violations surface to MCP clients) rather than a
    success response — verifying the failure mode, not silent accept."""
    from mcp.server.fastmcp.exceptions import ToolError

    with pytest.raises(ToolError, match="verdict must be one of"):
        asyncio.run(app.call_tool("themis_submit_verdict", {
            "verdict": "probably_yes",
            "question": "Q",
        }))


def test_submit_verdict_excerpt_truncates_long_questions(app):
    """Audit-trail field has a 200-char cap so the response stays
    bounded regardless of input verbosity."""
    long_q = "X" * 1000
    out = _call_tool(app, "themis_submit_verdict", {
        "verdict": "yes",
        "question": long_q,
    })
    assert len(out["question_excerpt"]) == 200
