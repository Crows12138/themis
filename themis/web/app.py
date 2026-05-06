"""FastAPI app — single-page UI + JSON endpoints over themis.run / verify.

The frontend lives in ``static/index.html``. Endpoints mirror the
in-process API exactly: /api/run takes a kernel_ast JSON, returns
the result envelope. /api/verify takes (program, result), returns
success/error. /api/examples lists worked examples from
docs/prompts/examples/.

No auth, no persistence, no LLM call — all of that is out of scope
for this slice. Bind to localhost; if you want to share, change
``--host 0.0.0.0`` at run time.
"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import themis


_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_REPO_ROOT = _HERE.parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "docs" / "prompts" / "examples"


app = FastAPI(title="Themis Web UI", version="0.1")


class RunRequest(BaseModel):
    program: dict


class VerifyRequest(BaseModel):
    program: dict
    result: dict


@app.get("/")
def index():
    return FileResponse(_STATIC / "index.html")


app.mount("/static", StaticFiles(directory=str(_STATIC)), name="static")


@app.post("/api/run")
def api_run(req: RunRequest):
    try:
        out = themis.run(req.program)
        return out
    except Exception as exc:
        # Surface the parse / semantic / runtime error type so the UI
        # can render it as a structured failure rather than a generic
        # 500.
        return JSONResponse(
            status_code=400,
            content={
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )


@app.post("/api/verify")
def api_verify(req: VerifyRequest):
    try:
        themis.verify(req.program, req.result)
        return {"ok": True}
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "error": type(exc).__name__,
                "message": str(exc),
            },
        )


@app.get("/api/examples")
def api_examples():
    """List worked examples from docs/prompts/examples/."""
    if not _EXAMPLES_DIR.exists():
        return []
    items = []
    for path in sorted(_EXAMPLES_DIR.glob("*.json")):
        try:
            content = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        # Examples wrap the program in a {nl_input, reasoning, kernel_ast}
        # tuple. Surface kernel_ast as `program`; pass nl_input through
        # so the UI can show the original natural-language question.
        program = content.get("kernel_ast", content)
        items.append({
            "name": path.stem,
            "nl_input": content.get("nl_input"),
            "program": program,
        })
    return items
