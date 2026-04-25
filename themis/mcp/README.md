# Themis MCP server (slice A1(b))

Wraps the Themis kernel as a Model Context Protocol server so any
MCP-capable LLM client (Claude Code, Claude Desktop, …) can drive
the kernel without copy-pasting prompts and inputs by hand.

## Architecture

The server exposes two surfaces:

- **Tools** — the four public JSON-in/JSON-out kernel entry points
  (`run`, `apply_patch_and_run`, `verify`, `estimate`) plus a resource
  catalog helper.
- **Resources** — the prompt files (A1, response_rendering, A5, A2,
  reply_to_framing_patch) and the JSON schemas (`kernel_ast`,
  `query_result`, `derivation`).

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
| `themis_estimate` | `themis.estimate(program, df)` | Loads CSV from `csv_path` |
| `themis_list_resources` | n/a | Returns the resource URI catalog |

## Resource catalog

| URI | Content |
|---|---|
| `themis://prompts/nl_to_kernel_ast.md` | A1 NL → kernel_ast prompt (v3) |
| `themis://prompts/response_rendering.md` | Output bridge prompt (v3) |
| `themis://prompts/narrative_to_variables.md` | A5 upstream framer |
| `themis://prompts/narrative_to_edges.md` | A2 edge proposer |
| `themis://prompts/reply_to_framing_patch.md` | F1 patch follow-up |
| `themis://schemas/kernel_ast.schema.json` | Input schema |
| `themis://schemas/query_result.schema.json` | Output schema |
| `themis://schemas/derivation.schema.json` | Embedded reasoning chain schema |

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
