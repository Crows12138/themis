"""FastMCP server exposing Themis kernel + prompts (slice A1(b)).

Tools (JSON in / JSON out — same contract as the kernel itself):

- ``themis_run(program)`` → wraps :func:`themis.run`
- ``themis_apply_patch_and_run(program, patches)`` → wraps :func:`themis.apply_patch_and_run`
- ``themis_verify(program, result)`` → wraps :func:`themis.verify`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_data_gap_report(result)`` → wraps :func:`themis.verify_data_gap_report`; returns ``{"ok": bool, "error": str?}``
- ``themis_verify_bounds_result(program, result)`` → iter 133, wraps :func:`themis.verify_bounds_result`; returns ``{"ok": bool, "error": str?}``
- ``themis_estimate(program, csv_path, options=None)`` → wraps :func:`themis.estimate`; loads CSV from disk
- ``themis_discover(csv_path, ...)`` → wraps :mod:`themis.estimation.discovery` (Phase 8.1); skeleton from CSV
- ``themis_submit_verdict(verdict, question, ...)`` → Fix 2A (v0.1.5):
  schema-validated yes/no/needs_more_info commitment channel. Removes
  token-level reliability risk when downstream consumers (benchmark
  scoring, agent pipelines, audit logs) need a binary verdict.
- ``themis_list_resources()`` → returns the resource URI catalog

Resources (read by the client to drive NL↔JSON):

- ``themis://prompts/nl_to_kernel_ast.md`` — A1 input bridge
- ``themis://prompts/response_rendering.md`` — output bridge
- ``themis://prompts/narrative_to_variables.md`` — A5 upstream framer
- ``themis://prompts/narrative_to_edges.md`` — A2 edge proposer
- ``themis://prompts/reply_to_framing_patch.md`` — F1 follow-up patcher
- ``themis://prompts/gap_to_action.md`` — Phase 11.1 agent-loop decision table
- ``themis://prompts/kb_lookup.md`` — Phase 11.2 structured KB query/result
- ``themis://schemas/kernel_ast.schema.json`` — input schema
- ``themis://schemas/query_result.schema.json`` — output schema
- ``themis://schemas/derivation.schema.json`` — embedded reasoning chain schema
- ``themis://schemas/kb_query.schema.json`` — Phase 11.2 KB adapter input
- ``themis://schemas/kb_result.schema.json`` — Phase 11.2 KB adapter output

The server does NOT call any LLM. The client (e.g. Claude Code) reads
the prompts, converts NL ↔ JSON, and calls the tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import themis


REPO_ROOT = Path(__file__).resolve().parents[2]
# Schemas + prompts now live inside the package so they ship with the
# wheel. PACKAGE_ROOT resolves to .../themis/ in both git-clone and
# pip-installed modes. REPO_ROOT is still used for CSV path resolution
# (themis_estimate's csv_path argument is interpreted relative to where
# the MCP server was launched, which is the project root).
PACKAGE_ROOT = Path(__file__).resolve().parent.parent
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
SCHEMAS_DIR = PACKAGE_ROOT / "schemas"
SCHEMAS = {
    "kernel_ast.schema.json": SCHEMAS_DIR / "kernel_ast.schema.json",
    "query_result.schema.json": SCHEMAS_DIR / "query_result.schema.json",
    "derivation.schema.json": SCHEMAS_DIR / "derivation.schema.json",
    # Phase 11.2 — KB adapter contract: clients implement adapters that
    # speak this query/result shape, then translate via
    # themis.kb.translator into apply_patch_and_run patches.
    "kb_query.schema.json": SCHEMAS_DIR / "kb_query.schema.json",
    "kb_result.schema.json": SCHEMAS_DIR / "kb_result.schema.json",
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


def _try_load_kb_adapter():
    """Try to load the sibling CauseNet adapter for edge verification.

    Returns the adapter or None if unavailable. Looked up (first match wins):

    1. Sibling repo at ``../sibling/themis-kb-causenet-mcp/src`` relative
       to this package — the in-tree dev layout.
    2. Installed ``causenet_mcp`` package already on ``sys.path``.

    Gracefully returns None on any import or data error so the kernel
    runs unmodified when KB is unavailable (e.g. bare clone without
    sibling, or sibling SQLite DBs not yet built).
    """
    import sys

    sibling_src = REPO_ROOT / "sibling" / "themis-kb-causenet-mcp" / "src"
    if sibling_src.is_dir() and str(sibling_src) not in sys.path:
        sys.path.insert(0, str(sibling_src))

    try:
        from causenet_mcp import build_server as build_causenet_server  # type: ignore[import-not-found]
    except ImportError:
        return None

    try:
        causenet_app = build_causenet_server()
    except FileNotFoundError:
        # SQLite DBs not built yet — sibling exists but data missing
        return None

    from themis.kb.adapters.causenet_mcp_adapter import (
        CausenetMCPAdapter,
        make_inprocess_caller,
    )
    return CausenetMCPAdapter(
        make_inprocess_caller(causenet_app),
        use_wordnet=False,  # deterministic; nltk wordnet optional, not pulled in
    )


def build_server(*, kb_adapter: Any = None, auto_load_kb: bool = True):
    """Construct and return the configured FastMCP server.

    Kept as a function (not module-level instantiation) so tests can
    spin up an isolated instance without side effects.

    ``kb_adapter`` — optional edge-verification adapter (e.g.
    ``CausenetMCPAdapter``). When provided OR auto-loaded, every
    ``themis_run`` / ``themis_apply_patch_and_run`` attaches an
    ``extensions.kb_verification_report`` to its result envelope.

    ``auto_load_kb`` — when True (default) and no ``kb_adapter`` was
    explicitly passed, ``_try_load_kb_adapter()`` is called once at
    server construction. Set False in tests that don't want the
    multi-GB SQLite load.
    """
    from mcp.server.fastmcp import FastMCP

    app = FastMCP("themis")

    if kb_adapter is None and auto_load_kb:
        kb_adapter = _try_load_kb_adapter()

    # ============================================ tools

    @app.tool()
    def themis_run(program: dict | str) -> dict:
        """Run the Themis kernel on a kernel_ast program.

        ``program``: either a ``dict`` matching ``kernel_ast.schema.json``
        or a JSON string. Returns the full ``themis.run`` envelope
        (``{"results": [...], "derivation": {...}, ...}``).

        When this server was constructed with a KB edge-verification
        adapter (auto-loaded from the sibling CauseNet package by
        default), every LLM-proposed edge is verified against the KB
        and the result is attached as
        ``results[*].extensions.kb_verification_report``.
        """
        return themis.run(program, kb_adapter=kb_adapter)

    @app.tool()
    def themis_apply_patch_and_run(
        program: dict | str, patches: list[dict] | dict,
    ) -> dict:
        """Apply framing/parameter patches and re-run.

        Multi-turn closed loop (slice A3): the client gathers user
        replies as patch bundles, applies them to the original program,
        and gets a refreshed result envelope back. Same KB verification
        attachment as ``themis_run``.
        """
        return themis.apply_patch_and_run(program, patches, kb_adapter=kb_adapter)

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
    def themis_verify_bounds_result(
        program: dict | str, result: dict,
    ) -> dict:
        """Iter 133 — independently audit a result's bounds_result.

        Parallel to ``themis_verify_data_gap_report``: bounds typically
        attach when point identification fails (status=needs_investigation)
        and no derivation chain exists, so ``themis_verify`` rejects them
        for missing derivation. This tool dispatches by
        bounds_result.method to the iter 126/127/130 verifier trilogy
        (manski_natural / manski_tamer_monotonicity / balke_pearl_iv).
        """
        try:
            themis.verify_bounds_result(program, result)
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
    def themis_discover(
        csv_path: str,
        bool_predicates: list[str] | None = None,
        algorithm: str = "auto",
        alpha: float = 0.05,
        random_state: int = 42,
        query: dict | None = None,
    ) -> dict:
        """Run causal discovery (PC / FCI / LiNGAM) on a CSV-backed
        dataset and return a kernel_ast suggestion the agent can review,
        edit, then feed to ``themis_run``.

        Each emitted ``cause`` / ``bidirected`` edge carries
        ``annotations.source = "discovery:<algo>"`` so downstream the
        gap report flags them as algorithmic (not domain knowledge),
        and the orchestrator can ask the user to review the suggested
        graph before committing to identification.

        ``algorithm``: ``"pc"`` / ``"fci"`` / ``"lingam"`` / ``"auto"``
        (auto picks LiNGAM for clearly non-Gaussian data, else PC).
        ``bool_predicates``: column names to declare as bool domain
        (others must be filled in by the agent before themis_run will
        accept the suggestion).
        ``query``: optional pre-built query statement to embed.
        """
        import pandas as pd

        from themis.estimation.discovery import (
            discover_graph,
            discovery_to_kernel_ast,
        )

        path = Path(csv_path)
        if not path.is_absolute():
            path = (REPO_ROOT / csv_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"csv_path does not resolve to a file: {path}")
        df = pd.read_csv(path)
        result = discover_graph(
            df, algorithm=algorithm, alpha=alpha,
            random_state=random_state,
        )
        return discovery_to_kernel_ast(
            result,
            bool_predicates=tuple(bool_predicates or ()),
            query=query,
        )

    @app.tool()
    def themis_submit_verdict(
        verdict: str,
        question: str,
        justification: str | None = None,
        kernel_query_id: str | None = None,
    ) -> dict:
        """v0.1.5 Fix 2A — commit a binary verdict through a typed channel.

        Use AFTER ``themis_run`` when the user's question expects a
        binary answer (e.g. "does X cause Y?", "is the effect positive?",
        "if X hadn't happened, would Y differ?"). The verdict travels in
        a schema-validated tool argument, not in free text, so a
        token-level decoding artifact at the end of your reply cannot
        corrupt the answer downstream consumers (benchmark scoring,
        agent pipelines, audit logs) actually read.

        ``verdict`` must be one of ``"yes"`` / ``"no"`` /
        ``"needs_more_info"``. Any other value is rejected — there is
        no "almost yes" or "probably no" channel; if the kernel didn't
        give you enough to commit, return ``needs_more_info`` and use
        the free-text reply to explain what's missing.

        ``question``: the original NL question, copied verbatim (or
        first ~200 chars) so a downstream auditor can match the verdict
        to the asked thing without re-reading the full transcript.

        ``justification``: optional NL explanation, primarily for the
        audit trail. The user-facing explanation belongs in your reply,
        not here.

        ``kernel_query_id``: optional ``query_id`` from a prior
        ``themis_run`` result whose evidence backs this verdict. Lets
        downstream consumers cross-reference the typed answer to the
        structural / numeric evidence.

        For open-ended / numeric / "what is the effect" questions, do
        NOT call this tool — there is no binary verdict to commit.
        Reply in natural language directly.

        Returns an acknowledgment echoing the committed verdict. The
        MCP transcript itself is the persistent record.
        """
        allowed = ("yes", "no", "needs_more_info")
        if verdict not in allowed:
            raise ValueError(
                f"verdict must be one of {list(allowed)}, got {verdict!r}"
            )
        return {
            "ok": True,
            "verdict": verdict,
            "question_excerpt": (question or "")[:200],
            "justification": justification,
            "kernel_query_id": kernel_query_id,
        }

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
