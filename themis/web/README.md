# Themis Web (local product)

A local web product over the Themis kernel — a React/Vite single-page app
backed by a FastAPI server that calls `themis.run` / `themis.verify` /
`themis.estimate` in-process. Three workspaces:

- **问一问 (Ask)** — type a Chinese causal question; the LLM bridge
  translates it to a kernel_ast, runs it, and renders an honest verdict
  (answer_tier point/interval/none, data-gap report, reply). Needs a
  model behind it — see "Model" below. Worked examples run with none.
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

To stop it, close the window (Ctrl-C), or from anywhere:

```
python scripts/stop_web.py       # or: python scripts/stop_web.py 8001
```

It stops whatever holds the listening socket **only if the command line says
it is this project's server** — a port number is not proof of identity, so a
foreign listener is reported and left running.

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
| `POST /api/audit` | `{program, result}` | `{audits: [{audit, zh, ok, refusal}]}` — every re-check that applies to this artifact, one row each. This is the browser's re-check surface |
| `POST /api/verify` | `{program, result}` | `{ok}` (result must carry a derivation) — subsumed by `/api/audit`; `app.py`'s `COVERED_BY` says so |
| `POST /api/verify_bounds_results` | `{program, result}` | `{ok}` (bounds-only audit) — likewise |
| `POST /api/ask` | `{nl, api_key?}` | `{nl, kernel_ast, envelope, reply}` |
| `GET /api/offers` | — | `{llm, visitor_key}` — what this deployment offers |
| `GET /api/examples` | — | `[{name, nl_input, program}]` |

## Model (Ask, AI priors, plain-language reading)

Declared on the server, read in one place (`llm_bridge._endpoint`):

| Setting | Meaning |
|---|---|
| `THEMIS_WEB_LLM` | `on` / `off` — whether this deployment offers the three surfaces that need a model at all |
| `THEMIS_LLM_API_KEY` | a key the deployment pays with; when set, visitors are not asked for one |
| `THEMIS_LLM_BASE_URL` | where that key is spent (default `https://api.anthropic.com`); any service speaking the Anthropic Messages API, e.g. `https://api.deepseek.com/anthropic` |
| `THEMIS_LLM_MODEL` | the model asked for there (default `claude-sonnet-4-6`) |

With no `THEMIS_LLM_API_KEY` the deployment is the local product: calls go
to the oauth proxy on this machine (`OAUTH_PROXY_URL`, default
`http://127.0.0.1:7777`), and the page offers a panel where a visitor can
paste an Anthropic key instead (kept in browser `localStorage`, sent per
request, never stored on the server).

Run JSON / Build / Estimate / examples need no model.

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
