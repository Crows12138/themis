"""FastAPI app — single-page UI + JSON endpoints over themis.run / verify.

The frontend is the React product in ``frontend/`` (built into
``frontend/dist``); ``static/`` holds the one page that says how to build
it. Endpoints mirror the
in-process API exactly: /api/run takes a kernel_ast JSON, returns
the result envelope. /api/verify takes (program, result), returns
success/error. /api/examples lists worked examples from
themis/prompts/examples/.

No auth, no persistence, no LLM call — all of that is out of scope
for this slice. Bind to localhost; if you want to share, change
``--host 0.0.0.0`` at run time.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import themis

# Route the LLM calls (Ask / render) through the local oauth-fingerprint
# proxy by default, so the web product needs NO API key (the proxy rebuilds
# the OAuth fingerprint and does the real auth — same as Themis_Demo). The
# anthropic SDK reads ANTHROPIC_BASE_URL from env; api_key="x" is just a
# placeholder. setdefault respects anything the operator already set, so a
# real ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL in the environment wins.
os.environ.setdefault(
    "ANTHROPIC_BASE_URL",
    os.environ.get("THEMIS_WEB_PROXY", "http://127.0.0.1:7777"),
)
os.environ.setdefault("ANTHROPIC_API_KEY", "x")


_HERE = Path(__file__).parent
_STATIC = _HERE / "static"
_NO_BUILD = _STATIC / "no_build.html"
_FRONTEND_DIST = _HERE / "frontend" / "dist"
_REPO_ROOT = _HERE.parent.parent
_EXAMPLES_DIR = _REPO_ROOT / "themis" / "prompts" / "examples"


app = FastAPI(title="Themis Web UI", version="0.1")


class RunRequest(BaseModel):
    program: dict


class VerifyRequest(BaseModel):
    program: dict
    result: dict


class AskRequest(BaseModel):
    nl: str
    api_key: str | None = None


class EstimateRequest(BaseModel):
    program: dict
    rows: list[dict]


class ClarifyRequest(BaseModel):
    program: dict
    picks: list[dict]  # [{"predicate": str, "fields": {...7 framing fields...}}]


class AssumeRequest(BaseModel):
    program: dict
    api_key: str | None = None


class RenderRequest(BaseModel):
    program: dict
    nl: str | None = None
    api_key: str | None = None


# The 7 operationalization fields that, filled, clear an
# ambiguous_variable_definition gap (ported from Themis_Demo).
_FILL_FIELDS = ("time_window", "measurement", "threshold", "observability",
                "direction", "baseline", "state_vs_event")
_FILL_DEFAULTS = {
    "time_window": "未指定（默认：研究随访期）",
    "measurement": "未指定（默认：标准测量）",
    "threshold": "未指定（默认：任意可测变化）",
    "observability": "observable",
    "direction": "up",
    "baseline": "未指定（默认：当前状态）",
    "state_vs_event": "state",
}


def _complete_framing_fields(d: dict) -> dict:
    """Ensure all 7 fields have non-empty values (fill blanks with sane
    defaults) so the patch deterministically clears the gap."""
    out = dict(_FILL_DEFAULTS)
    for k in _FILL_FIELDS:
        v = (d or {}).get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def _var_domain(program: dict, predicate: str):
    for s in program.get("statements", []):
        if s.get("kind") == "variable" and s.get("predicate") == predicate:
            return s.get("domain")
    return None


@app.get("/")
def index():
    # One surface shows a reader a result: the built React product.
    # Everything the kernel holds a surface to — each closed vocabulary said
    # in the reader's own words, each envelope field accounted for — is
    # checked against frontend/src, and can be checked there only because
    # that is the only place a result is ever rendered. So what goes out
    # when there is no build carries no result at all; it says how to build
    # one. A second, older page rendering results its own way would not be a
    # fallback — it is a different product on the same URL, and the reader
    # cannot tell which one they were handed.
    #
    # index.html must always revalidate: it references content-hashed asset
    # filenames (index-<hash>.js), so a browser that caches a stale index.html
    # would keep loading an old bundle after a rebuild. The hashed /assets/*
    # files never change for a given name and may be cached freely.
    dist_index = _FRONTEND_DIST / "index.html"
    target = dist_index if dist_index.exists() else _NO_BUILD
    return FileResponse(target, headers={"Cache-Control": "no-cache"})


# Built product assets (Vite emits /assets/*). Mounted only when a build
# exists so the dev-without-build path keeps working.
if (_FRONTEND_DIST / "assets").exists():
    app.mount("/assets", StaticFiles(directory=str(_FRONTEND_DIST / "assets")), name="assets")

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


@app.post("/api/verify_bounds_results")
def api_verify_bounds_results(req: VerifyRequest):
    """Web parallel of the MCP ``themis_verify_bounds_results`` tool.

    Wraps :func:`themis.verify_bounds_results` so paste-JSON / Ask
    flows can audit MTR / Manski-natural / Balke-Pearl IV bounds
    without going through the derivation-required ``/api/verify``
    path. Bounds typically attach when status=needs_investigation
    (no derivation chain), so /api/verify rejects them — this
    endpoint is the bounds-only counterpart.
    """
    try:
        themis.verify_bounds_results(req.program, req.result)
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


@app.post("/api/audit")
def api_audit(req: VerifyRequest):
    """Every independent re-check that applies to this artifact, run.

    Which ones apply is a question about the artifact, answered in
    themis.audits — not here, and above all not in the browser: the two
    endpoints above are each one audit of thirteen, and a caller choosing
    between them by hand is a caller who has to know which audits are not
    about their result at all.
    """
    try:
        return {"audits": themis.audit(req.program, req.result)}
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": type(exc).__name__, "message": str(exc)},
        )


# An endpoint the product does not call itself, and the one that reaches it.
# Both are MCP-parity shapes (themis_verify / themis_verify_bounds_results are
# their own tools), so they stay; what a reader can reach is /api/audit, which
# runs whichever of them applies to what they are looking at.
COVERED_BY = {
    "/api/verify": "/api/audit",
    "/api/verify_bounds_results": "/api/audit",
}


@app.post("/api/ask")
def api_ask(req: AskRequest):
    """End-to-end NL → kernel_ast → run → reply via the LLM bridge.

    Returns ``{nl, kernel_ast, envelope, reply}`` on success. On any
    failure (missing API key, LLM refusal, kernel semantic rejection,
    network error) returns 400 with ``{stage, error, message}`` so the
    UI can pinpoint where in the pipeline things broke.
    """
    import themis
    from .llm_bridge import LLMBridgeError, nl_to_kernel_ast, render_reply

    key = req.api_key or "x"
    # Retry nl→ast→run up to 3 times for transient LLM / network failures
    # (mirrors Themis_Demo). The systematic `args`-on-variable slip is fixed
    # at the root by the bridge's few-shot examples — no sanitizing here.
    kernel_ast = envelope = None
    last: Exception | None = None
    last_ast: dict | None = None
    last_stage = "nl_to_kernel_ast"
    for _ in range(3):
        last_stage = "nl_to_kernel_ast"
        try:
            a = nl_to_kernel_ast(req.nl, api_key=key)
            last_ast = a
            last_stage = "themis_run"  # NL→AST done; a failure now is the kernel's
            envelope = themis.run(a)
            kernel_ast = a
            break
        except Exception as exc:  # noqa: BLE001 — retry on any bridge/kernel error
            last = exc
    if kernel_ast is None:
        # Attribute the failure to where it actually happened, by position —
        # NOT by exception type. A transport error during the LLM call (proxy
        # down) is an nl_to_kernel_ast failure even though it is not an
        # LLMBridgeError; the old `is_bridge` heuristic mislabeled it themis_run.
        return JSONResponse(status_code=400, content={
            "stage": last_stage,
            "error": type(last).__name__,
            "message": f"生成/校验因果图失败(已重试 3 次):{type(last).__name__}: {str(last)[:200]}",
            "need_key": "key" in str(last).lower(),
            # The kernel-rejected AST (None if NL→AST itself failed) so the UI
            # can show the broken graph — mirrors the render_reply error body.
            "kernel_ast": last_ast,
        })

    try:
        reply = render_reply(envelope, nl=req.nl, api_key=req.api_key or "x")
    except LLMBridgeError as exc:
        return JSONResponse(status_code=400, content={
            "stage": "render_reply",
            "error": "LLMBridgeError",
            "message": str(exc),
            "kernel_ast": kernel_ast,
            "envelope": envelope,
        })
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "stage": "render_reply",
            "error": type(exc).__name__,
            "message": str(exc),
            "kernel_ast": kernel_ast,
            "envelope": envelope,
        })

    return {
        "nl": req.nl,
        "kernel_ast": kernel_ast,
        "envelope": envelope,
        "reply": reply,
    }


@app.post("/api/estimate")
def api_estimate(req: EstimateRequest):
    """DataFrame-backed numeric estimation: build a DataFrame from the
    uploaded rows and run ``themis.estimate`` against the program.

    Returns the run-shaped envelope (with ``numeric_estimate`` populated
    on effect-query results) or a 400 with a structured error so the UI
    can show why estimation refused (contract failure / overlap / etc.).
    """
    import pandas as pd

    if not req.rows:
        return JSONResponse(status_code=400, content={
            "error": "EmptyData", "message": "上传的数据没有任何行。",
        })
    try:
        df = pd.DataFrame(req.rows)
        # CSV cells arrive as strings / dynamic-typed numbers. Coerce
        # bool-ish object columns to real bool so the estimator contract
        # (which rejects free-form strings) accepts them.
        _bool_map = {"true": True, "1": True, "yes": True, "t": True,
                     "false": False, "0": False, "no": False, "f": False}
        for col in df.columns:
            if df[col].dtype == object:
                low = df[col].astype(str).str.strip().str.lower()
                if low.isin(_bool_map).all():
                    df[col] = low.map(_bool_map)
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__, "message": f"无法解析数据：{exc}",
        })

    try:
        out = themis.estimate(req.program, df)
        return out
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__,
            "message": str(exc),
        })


@app.post("/api/clarify")
def api_clarify(req: ClarifyRequest):
    """Fill framing gaps and re-run. Builds a deterministic
    framing_skeleton_bundle from the user's picks (the 7 operationalization
    fields per variable, blanks defaulted) and calls
    ``themis.apply_patch_and_run`` — the multi-turn 补缺口 loop. No LLM.

    Returns the run-shaped envelope of the merged program (so the UI can
    show the new verdict + whatever gaps remain), plus ``merged_program``.
    """
    patches = []
    for p in req.picks or []:
        pred = p.get("predicate")
        if not pred:
            continue
        fields = _complete_framing_fields(p.get("fields") or {})
        dom = _var_domain(req.program, pred)
        fields["domain"] = dom if dom is not None else [True, False]
        patches.append({"kind": "variable_patch", "predicate": pred, "fields": fields})
    if not patches:
        return JSONResponse(status_code=400, content={
            "error": "NoPatches", "message": "没有可应用的澄清。",
        })
    bundle = {"version": "0.1", "kind": "framing_skeleton_bundle", "patches": patches}
    try:
        out = themis.apply_patch_and_run(req.program, [bundle])
        return out
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__, "message": str(exc),
        })


def _probability_skeletons(result: dict) -> list[dict]:
    """Pull the ``kind == "probability"`` skeletons (value == null) the kernel
    listed in ``investigation_requests`` — the exact distributions it needs
    filled to compute a number."""
    out = []
    for req in result.get("investigation_requests") or []:
        for item in req.get("items") or []:
            sk = item.get("skeleton")
            if isinstance(sk, dict) and sk.get("kind") == "probability":
                out.append(sk)
    return out


@app.post("/api/assume")
def api_assume(req: AssumeRequest):
    """数据不足时的诚实兜底:让 LLM 给缺的概率分布填一组 common-knowledge
    先验(``provenance: llm_prior``),重跑得到点估计。

    每个先验都被内核收进 ``extensions.llm_proposed_review``,所以答案会
    明说"这些数字是 AI 估的,请审核"——这是 opt-in 的估算,不是内核替
    用户脑补。返回 run-shaped envelope(带点估计 + 披露面板)。
    """
    from .llm_bridge import LLMBridgeError, propose_theta_priors

    # 1. Run once to discover exactly which probabilities are missing.
    try:
        env0 = themis.run(req.program)
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__, "message": str(exc),
        })
    result0 = (env0.get("results") or [{}])[0]
    skeletons = _probability_skeletons(result0)
    if not skeletons:
        return JSONResponse(status_code=400, content={
            "error": "NothingToAssume",
            "message": "这个查询没有缺失的概率分布可供 AI 估算"
                       "(可能已能算、或缺的是结构/定义而非数值)。",
        })

    # 2. LLM sources a prior for each (disclosure is the kernel's job).
    try:
        filled = propose_theta_priors(
            req.program, skeletons, api_key=req.api_key or "x")
    except LLMBridgeError as exc:
        return JSONResponse(status_code=400, content={
            "stage": "propose_theta_priors",
            "error": "LLMBridgeError", "message": str(exc),
        })
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "stage": "propose_theta_priors",
            "error": type(exc).__name__, "message": str(exc),
        })

    # 3. Fill + re-run through the kernel's multi-turn patch loop.
    bundle = {"version": "0.1", "kind": "parameter_fill_bundle",
              "skeletons": filled}
    try:
        out = themis.apply_patch_and_run(req.program, [bundle])
        return out
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__, "message": str(exc),
        })


@app.post("/api/render")
def api_render(req: RenderRequest):
    """On-demand LLM 大白话 reading of a result. The structured verdict is
    instant; this is the optional translation layer (needs an API key)."""
    try:
        from .llm_bridge import render_reply
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": "LLMBridgeUnavailable", "message": f"无法加载 LLM 桥接：{exc}",
        })
    try:
        envelope = themis.run(req.program)
        reply = render_reply(envelope, nl=req.nl, api_key=req.api_key or "x")
        return {"reply": reply}
    except Exception as exc:
        return JSONResponse(status_code=400, content={
            "error": type(exc).__name__, "message": str(exc),
        })


@app.get("/api/examples")
def api_examples():
    """List worked examples from themis/prompts/examples/."""
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
