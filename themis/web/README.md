# Themis Web (local product)

A local web product over the Themis kernel — a React/Vite single-page app
backed by a FastAPI server that calls `themis.run` / `themis.verify` /
`themis.estimate` in-process. Three workspaces:

- **问一问 (Ask)** — type a Chinese causal question; the LLM bridge
  translates it to a kernel_ast, runs it, and renders an honest verdict
  (answer_tier point/interval/none, data-gap report, reply). Needs an
  Anthropic API key. Worked examples run with no key.
- **建因果图 (Build)** — draw a causal DAG (cause + latent-confounding
  edges), pick a query (effect / identify / counterfactual), and get the
  kernel's verdict: identifiable? what data is still missing?
- **数据估计 (Estimate)** — draw a DAG, upload a CSV (one column per
  variable), and get a real numeric estimate via `themis.estimate` — or
  an honest refusal (residual confounding / no overlap / too few rows).

No auth, no persistence. Localhost by default.

## Run (production build)

```
cd themis/web/frontend
pnpm install
pnpm build            # emits frontend/dist
cd ../../..
python -m themis.web  # serves the built product at http://127.0.0.1:8000
```

`python -m themis.web` serves `frontend/dist` at `/` when it exists. With
no build it serves `static/no_build.html`, which says how to make one and
shows no result — the built product is the only surface that renders a
result, which is what makes "every vocabulary in the reader's words, every
envelope field accounted for" checkable at all.

Flags: `--port 8001`, `--host 0.0.0.0` (share on LAN), `--reload` (dev).

## Develop (hot reload)

Run the backend and the Vite dev server side by side:

```
python -m themis.web                       # backend + /api on :8000
cd themis/web/frontend && pnpm dev         # Vite on :5173, proxies /api -> :8000
```

Open http://127.0.0.1:5173 — edits hot-reload. The Vite proxy forwards
`/api/*` to the backend, so there is no CORS in dev and the same relative
paths work in the production build.

## API

| Endpoint | Body | Returns |
|---|---|---|
| `POST /api/run` | `{program}` | run envelope (or 400 `{error, message}`) |
| `POST /api/clarify` | `{program, picks}` | merged run envelope — fill framing gaps and re-run (apply_patch_and_run) |
| `POST /api/estimate` | `{program, rows}` | run envelope with `numeric_estimate` |
| `POST /api/verify` | `{program, result}` | `{ok}` (result must carry a derivation) |
| `POST /api/verify_bounds_result` | `{program, result}` | `{ok}` (bounds-only audit) |
| `POST /api/ask` | `{nl, api_key?}` | `{nl, kernel_ast, envelope, reply}` |
| `GET /api/examples` | — | `[{name, nl_input, program}]` |

## API key (Ask only)

Resolution order:
1. The "API Key" button in the header — paste your key into the panel
   (stored in browser `localStorage`, sent per-request, not persisted
   server-side).
2. `ANTHROPIC_API_KEY` env var on the server.

Run JSON / Build / Estimate / examples need no key. Override the model
via `THEMIS_LLM_MODEL` (default `claude-sonnet-4-6`).

## Stack

- **Backend** `app.py` — FastAPI; thin JSON wrappers over the in-process
  kernel. `__main__.py` launches uvicorn.
- **Frontend** `frontend/` — React + Vite + TypeScript; `@xyflow/react`
  for the DAG editor, `papaparse` for CSV. Built into `frontend/dist`,
  which the backend serves. Design context in `/.impeccable.md`.

## Not yet

- No deploy config / auth / multi-user (localhost product for now).
- Estimate requires the graph's variable names to match the CSV column
  names by hand (no column-mapping UI yet).
