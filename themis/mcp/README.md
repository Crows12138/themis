# Themis MCP server (slice A1(b))

Wraps the Themis kernel as a Model Context Protocol server so any
MCP-capable LLM client (Claude Code, Claude Desktop, …) can drive
the kernel without copy-pasting prompts and inputs by hand.

## Architecture

The server exposes two surfaces (current count: 12 tools + 12 resources;
test_mcp_server.py + iter 59 sync pin lock both):

- **Tools** — the public JSON-in/JSON-out kernel entry points:
  `themis_run`, `themis_apply_patch_and_run`, `themis_verify`,
  `themis_verify_data_gap_report` (Phase 10),
  `themis_verify_bounds_result` (iter 133),
  `themis_verify_markov_blanket` (borrow-list #4), `themis_estimate`
  (Phase 7+14), `themis_discover` (Phase 8.1),
  `themis_markov_blanket` (borrow-list #4),
  `themis_submit_verdict` (v0.1.5 Fix 2A) — plus
  `themis_list_resources` catalog helper.
- **Resources** — the prompt files (`nl_to_kernel_ast.md`,
  `response_rendering.md`, `narrative_to_variables.md`,
  `narrative_to_edges.md`, `reply_to_framing_patch.md`,
  `gap_to_action.md`, `kb_lookup.md`) and the JSON schemas
  (`kernel_ast`, `query_result`, `derivation`, `kb_query`,
  `kb_result`).

The server itself does **not** call any LLM — that would violate the
kernel's "no LLM inside `themis/*`" rule. The MCP **client** reads the
prompts as resources, drives NL ↔ JSON translation, and calls the tools.

## Run it

```bash
python -m themis.mcp.server
```

This launches over stdio (the default MCP transport). The Python
`mcp` package must be installed (`pip install mcp`).

## Wire to Claude Code

Add to `~/.claude/mcp.json` (or `.mcp.json` in the repo root):

```json
{
  "mcpServers": {
    "themis": {
      "command": "python",
      "args": ["-m", "themis.mcp.server"],
      "cwd": "/absolute/path/to/因果性ai"
    }
  }
}
```

After restart, `themis` will appear in `/mcp` and tools will be
prefixed `mcp__themis__`.

## Tool catalog

| Tool | Wraps | Notes |
|---|---|---|
| `themis_run` | `themis.run(program)` | Single-turn full pipeline |
| `themis_apply_patch_and_run` | `themis.apply_patch_and_run(program, patches)` | Multi-turn closed loop (slice A3) |
| `themis_verify` | `themis.verify(program, result)` | Returns `{ok, error?}` instead of raising |
| `themis_verify_data_gap_report` | `themis.verify_data_gap_report(result)` | Phase 10 — independent audit of gap report |
| `themis_verify_bounds_result` | `themis.verify_bounds_result(program, result)` | Iter 133 — bounds-result audit (MN/MTR/BP-IV) for derivation-less results |
| `themis_verify_markov_blanket` | `themis.verify_markov_blanket(result)` | Borrow-list #4 — re-checks the Markov-blanket definition from the recorded correlation matrix |
| `themis_estimate` | `themis.estimate(program, df)` | Loads CSV from `csv_path` (Phase 7+14) |
| `themis_discover` | `themis.estimation.discovery.discover_*` | Phase 8.1 — PC / GES skeletons from CSV |
| `themis_markov_blanket` | `themis.estimation.discovery.markov_blanket` | Borrow-list #4 — local Markov-blanket screen of a target (continuous Fisher-Z / discrete chi-square) |
| `themis_report` | `themis.build_analysis_report` (+ run/estimate/verify) | Deterministic analyze → verify → Markdown report per query (no LLM / API key) |
| `themis_submit_verdict` | n/a (agent-side commitment) | v0.1.5 Fix 2A — schema-validated `yes`/`no`/`needs_more_info` commitment channel so binary verdicts survive token-level decoding artifacts |
| `themis_list_resources` | n/a | Returns the resource URI catalog |

## Resource catalog

| URI | Content |
|---|---|
| `themis://prompts/nl_to_kernel_ast.md` | A1 NL → kernel_ast prompt |
| `themis://prompts/response_rendering.md` | Output bridge prompt |
| `themis://prompts/narrative_to_variables.md` | A5 upstream framer |
| `themis://prompts/narrative_to_edges.md` | A2 edge proposer |
| `themis://prompts/reply_to_framing_patch.md` | F1 patch follow-up |
| `themis://prompts/gap_to_action.md` | Phase 11.1 agent-loop decision table |
| `themis://prompts/kb_lookup.md` | Phase 11.2 structured KB query/result |
| `themis://schemas/kernel_ast.schema.json` | Input schema |
| `themis://schemas/query_result.schema.json` | Output schema |
| `themis://schemas/derivation.schema.json` | Embedded reasoning chain schema |
| `themis://schemas/kb_query.schema.json` | Phase 11.2 KB adapter input |
| `themis://schemas/kb_result.schema.json` | Phase 11.2 KB adapter output |

## Typical client flow

1. Read `themis://prompts/nl_to_kernel_ast.md`
2. Convert user's NL question → `kernel_ast` JSON (LLM, client-side)
3. Call `themis_run({program: <ast>})` → result envelope
4. If result has data → optionally call `themis_estimate` with a CSV
5. Read `themis://prompts/response_rendering.md`
6. Render result → Chinese reply (LLM, client-side)
7. (multi-turn) If result carries `investigation_requests`, gather user
   reply → patch bundle → call `themis_apply_patch_and_run`

## Tests

`tests/test_mcp_server.py` drives the server in-process (no stdio,
no LLM) to confirm tools and resources work. Run with:

```bash
pytest tests/test_mcp_server.py -v
```
