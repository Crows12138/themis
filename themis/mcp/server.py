"""FastMCP server exposing Themis kernel + prompts (slice A1(b)).

Tools (JSON in / JSON out — same contract as the kernel itself):

- ``themis_run(program)`` → wraps :func:`themis.run`
- ``themis_apply_patch_and_run(program, patches)`` → wraps :func:`themis.apply_patch_and_run`
- ``themis_verify(program, result)`` → wraps :func:`themis.verify`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_data_gap_report(result)`` → wraps :func:`themis.verify_data_gap_report`; returns ``{"ok": bool, "error": str?}``
- ``themis_estimate(program, csv_path, options=None)`` → wraps :func:`themis.estimate`; loads CSV from disk
- ``themis_list_resources()`` → returns the resource URI catalog

Resources (read by the client to drive NL↔JSON):

- ``themis://prompts/nl_to_kernel_ast.md`` — A1 input bridge
- ``themis://prompts/response_rendering.md`` — output bridge
- ``themis://prompts/narrative_to_variables.md`` — A5 upstream framer
- ``themis://prompts/narrative_to_edges.md`` — A2 edge proposer
- ``themis://prompts/reply_to_framing_patch.md`` — F1 follow-up patcher
- ``themis://prompts/gap_to_action.md`` — Phase 11.1 agent-loop decision table
- ``themis://schemas/kernel_ast.schema.json`` — input schema
- ``themis://schemas/query_result.schema.json`` — output schema
- ``themis://schemas/derivation.schema.json`` — embedded reasoning chain schema

The server does NOT call any LLM. The client (e.g. Claude Code) reads
the prompts, converts NL ↔ JSON, and calls the tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import themis


REPO_ROOT = Path(__file__).resolve().parents[2]
PROMPTS_DIR = REPO_ROOT / "docs" / "prompts"
SCHEMAS = {
    "kernel_ast.schema.json": REPO_ROOT / "kernel_ast.schema.json",
    "query_result.schema.json": REPO_ROOT / "query_result.schema.json",
    "derivation.schema.json": REPO_ROOT / "derivation.schema.json",
    # Phase 11.2 — KB adapter contract: clients implement adapters that
    # speak this query/result shape, then translate via
    # themis.kb.translator into apply_patch_and_run patches.
    "kb_query.schema.json": REPO_ROOT / "kb_query.schema.json",
    "kb_result.schema.json": REPO_ROOT / "kb_result.schema.json",
}
PROMPT_FILES = (
    "nl_to_kernel_ast.md",
    "response_rendering.md",
    "narrative_to_variables.md",
    "narrative_to_edges.md",
    "reply_to_framing_patch.md",
    # Phase 11.1 — closes the agent loop by telling the LLM what to do
    # when data_gap_report is non-empty (next-action decision table +
    # autonomous-fetch vs ask-user heuristics + loop termination rules).
    "gap_to_action.md",
    # Phase 11.2 — teaches the orchestrator to use structured KBQuery /
    # KBResult instead of free-form WebSearch strings, and to route
    # results through themis.kb.translator helpers.
    "kb_lookup.md",
)


def build_server():
    """Construct and return the configured FastMCP server.

    Kept as a function (not module-level instantiation) so tests can
    spin up an isolated instance without side effects.
    """
    from mcp.server.fastmcp import FastMCP

    app = FastMCP("themis")

    # ============================================ tools

    @app.tool()
    def themis_run(program: dict | str) -> dict:
        """Run the Themis kernel on a kernel_ast program.

        ``program``: either a ``dict`` matching ``kernel_ast.schema.json``
        or a JSON string. Returns the full ``themis.run`` envelope
        (``{"results": [...], "derivation": {...}, ...}``).
        """
        return themis.run(program)

    @app.tool()
    def themis_apply_patch_and_run(
        program: dict | str, patches: list[dict] | dict,
    ) -> dict:
        """Apply framing/parameter patches and re-run.

        Multi-turn closed loop (slice A3): the client gathers user
        replies as patch bundles, applies them to the original program,
        and gets a refreshed result envelope back.
        """
        return themis.apply_patch_and_run(program, patches)

    @app.tool()
    def themis_verify(program: dict | str, result: dict) -> dict:
        """Independently re-verify a claimed result against the program.

        Returns ``{"ok": True}`` on success or
        ``{"ok": False, "error": "<message>"}`` on failure (rather than
        raising — MCP transport-friendly).
        """
        try:
            themis.verify(program, result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_verify_data_gap_report(result: dict) -> dict:
        """Independently audit a result's data_gap_report.

        This is intentionally separate from ``themis_verify``: some
        diagnostic outputs have no query derivation to audit, but their
        T10 data-gap report is still independently checkable.
        """
        try:
            themis.verify_data_gap_report(result)
            return {"ok": True}
        except Exception as exc:  # pragma: no cover - error path is the point
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    @app.tool()
    def themis_estimate(
        program: dict | str,
        csv_path: str,
        options: dict | None = None,
    ) -> dict:
        """Run Phase 7 numeric estimation on a CSV-backed dataset.

        ``csv_path`` is loaded with pandas. ``options`` are forwarded as
        kwargs to :func:`themis.estimate` (e.g. ``{"random_state": 42}``).
        Returns the estimate envelope (point / CI / method / assumptions /
        sensitivity_analysis if binary outcome).
        """
        import pandas as pd

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        return themis.estimate(program, df, **(options or {}))

    @app.tool()
    def themis_list_resources() -> dict:
        """Catalog of available MCP resource URIs.

        Useful for clients that want to discover prompts/schemas
        without parsing the resource list themselves.
        """
        return {
            "prompts": [f"themis://prompts/{name}" for name in PROMPT_FILES],
            "schemas": [f"themis://schemas/{name}" for name in SCHEMAS],
        }

    # ============================================ resources

    def _make_text_reader(path: Path):
        def reader() -> str:
            return path.read_text(encoding="utf-8")
        return reader

    def _make_json_reader(path: Path):
        def reader() -> str:
            # Re-serialize through json to validate well-formedness.
            return json.dumps(json.loads(path.read_text(encoding="utf-8")), indent=2)
        return reader

    for name in PROMPT_FILES:
        path = PROMPTS_DIR / name
        if not path.is_file():
            continue
        app.resource(
            f"themis://prompts/{name}",
            name=name,
            mime_type="text/markdown",
        )(_make_text_reader(path))

    for name, path in SCHEMAS.items():
        if not path.is_file():
            continue
        app.resource(
            f"themis://schemas/{name}",
            name=name,
            mime_type="application/json",
        )(_make_json_reader(path))

    return app


def main() -> None:
    """CLI entry point — runs the server over stdio (default MCP transport)."""
    app = build_server()
    app.run()


if __name__ == "__main__":
    main()
