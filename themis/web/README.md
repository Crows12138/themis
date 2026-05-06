# Themis Web UI (local)

Minimal browser UI for `themis.run` / `themis.verify`. No NL bridge,
no LLM call, no persistence — just a paste-JSON-see-result panel
that renders explanation, ⚠ caveats, data-gap report, and
derivation rules in a more readable form than raw JSON.

## Run

```
python -m themis.web
```

opens `http://127.0.0.1:8000`.

## Flags

```
python -m themis.web --port 8001                # different port
python -m themis.web --host 0.0.0.0             # share on local wifi
python -m themis.web --reload                   # dev: auto-reload code
```

For public deployment (Railway / Fly / Render etc.), point the
platform at `themis.web.app:app` — same code, no changes.

## What it does

- **Ask** — type a Chinese question, the LLM bridge calls Anthropic
  with the canonical `nl_to_kernel_ast.md` prompt, runs the emitted
  kernel_ast, then calls Anthropic again with `response_rendering.md`
  to produce a Chinese reply. Two LLM calls per question.
- **Run JSON** — paste kernel_ast directly → `themis.run` → render
  envelope. No LLM involved. Useful for debugging / tweaking
  generated AST.
- **Verify** — POST `(program, result)` → `themis.verify`. Works
  when the last result carries a derivation (cause / assoc /
  identify / structurally-solved effect / counterfactual that
  reached bounds). Other shapes return a structured error message.
- **Examples** — load worked NL→kernel_ast pairs from
  `docs/prompts/examples/`.

## API key

The Ask path needs an Anthropic API key. Resolution order:

1. The "API key" link in the header — paste your key into the modal.
   Stored in browser `localStorage`, sent per-request, **not
   persisted server-side**.
2. `ANTHROPIC_API_KEY` environment variable on the server.

If neither is set, Ask returns 400 with a clear message. Run JSON
and Verify don't need a key.

Override the model via `THEMIS_LLM_MODEL` (default
`claude-sonnet-4-6`).

## What it doesn't do

- No data upload for `themis.estimate` (DataFrame paths). Add when
  there's a real-case driver.
- No streaming for the Ask response — you wait for the full reply
  to land. Add when latency on long replies starts hurting.
- No auth / rate limiting / multi-user state. Localhost only by
  default; if you bind 0.0.0.0 or deploy publicly, add an auth
  layer first — the API key field gives users their own quota
  but doesn't restrict who can hit your server.
