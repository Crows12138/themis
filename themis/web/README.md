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

- **Run** — POST kernel_ast → `themis.run` → render envelope.
- **Verify** — POST `(program, result)` → `themis.verify`. Only
  works when the last result carries a derivation (cause / assoc /
  identify / structurally-solved effect / counterfactual that
  reached bounds). Other shapes return a structured error message.
- **Examples** — load worked NL→kernel_ast pairs from
  `docs/prompts/examples/`.

## What it doesn't do

- No NL → JSON bridge. You paste kernel_ast yourself or pick an
  example. An LLM-bridge slice (server calls Anthropic API) is a
  follow-up that doesn't break this surface.
- No data upload for `themis.estimate` (DataFrame paths). Add when
  there's a real-case driver.
- No auth / rate limiting / multi-user state. Localhost only by
  default; if you bind 0.0.0.0 or deploy publicly, add an auth
  layer first.
