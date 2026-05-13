"""LLM bridge — NL → kernel_ast and result → Chinese reply.

Sits OUTSIDE the kernel by design. Themis itself never calls an LLM;
this module is web-side glue that:

1. Loads ``docs/prompts/nl_to_kernel_ast.md`` as the system prompt.
2. Asks the LLM to emit one kernel_ast JSON for the user's NL.
3. Runs ``themis.run`` on the emitted JSON.
4. Loads ``docs/prompts/response_rendering.md``, feeds the structured
   result back, asks the LLM for a Chinese reply.

API key resolution: explicit ``api_key`` argument > ``ANTHROPIC_API_KEY``
env var. Model defaults to ``claude-sonnet-4-6``; override via
``THEMIS_LLM_MODEL``.

Both LLM calls are blocking — no streaming back to the browser in
this slice; add when there's a real-case driver for partial-result
display.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent
_PROMPT_NL_TO_AST = _REPO_ROOT / "themis" / "prompts" / "nl_to_kernel_ast.md"
_PROMPT_RENDER = _REPO_ROOT / "themis" / "prompts" / "response_rendering.md"

_DEFAULT_MODEL = os.environ.get("THEMIS_LLM_MODEL", "claude-sonnet-4-6")


class LLMBridgeError(RuntimeError):
    """Bridge-layer error (missing key, parse failure, API error).

    Distinct from semantic errors raised by ``themis.run`` so the UI
    can render them differently.
    """


def _load_system_prompt(path: Path) -> str:
    if not path.exists():
        raise LLMBridgeError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


def _client(api_key: str | None = None):
    """Lazy-import the Anthropic SDK so the web app starts even
    without the package installed (the LLM bridge is optional)."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise LLMBridgeError(
            "anthropic SDK not installed; pip install anthropic"
        ) from exc

    key = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        raise LLMBridgeError(
            "no API key — set ANTHROPIC_API_KEY env var or pass one in"
        )
    return Anthropic(api_key=key)


def _extract_first_json_object(text: str) -> dict:
    """The prompt asks for raw JSON, no fences. Real models occasionally
    wrap in ```json ... ``` or add a leading paragraph; tolerate that
    defensively here so a single stray markdown fence doesn't blow the
    whole loop."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    start = text.find("{")
    if start < 0:
        raise LLMBridgeError(
            f"no JSON object in LLM response: {text[:200]}"
        )
    depth = 0
    end = -1
    for i in range(start, len(text)):
        c = text[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise LLMBridgeError(
            f"unbalanced JSON braces in LLM response: {text[:200]}"
        )
    raw = text[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMBridgeError(
            f"LLM JSON parse: {exc}; payload: {raw[:200]}"
        ) from exc


def nl_to_kernel_ast(
    nl: str,
    *,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> dict:
    """Turn one NL question into a kernel_ast dict via the project's
    canonical prompt. Returns the dict the LLM emits — caller runs
    ``themis.run`` on it."""
    system = _load_system_prompt(_PROMPT_NL_TO_AST)
    client = _client(api_key)
    msg = client.messages.create(
        model=model,
        max_tokens=4000,
        system=system,
        messages=[{"role": "user", "content": nl}],
    )
    text = "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    )
    parsed = _extract_first_json_object(text)
    if "error" in parsed and "version" not in parsed:
        # The prompt allows {"error": "..."} as a refusal shape.
        raise LLMBridgeError(f"LLM refused: {parsed['error']}")
    return parsed


def render_reply(
    envelope: dict,
    *,
    nl: str | None = None,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> str:
    """Turn a ``themis.run`` envelope into a Chinese reply via the
    response_rendering prompt."""
    system = _load_system_prompt(_PROMPT_RENDER)
    client = _client(api_key)

    user_msg = ""
    if nl:
        user_msg += f"用户原问: {nl}\n\n"
    user_msg += (
        "下面是 themis.run 的完整 envelope（包含 program / "
        "merged_program / results）；按 prompt 给的格式输出中文回复。\n\n"
    )
    user_msg += json.dumps(envelope, ensure_ascii=False, indent=2)

    msg = client.messages.create(
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    ).strip()


def ask(
    nl: str,
    *,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> dict:
    """End-to-end: NL → kernel_ast → themis.run → Chinese reply.

    Returns ``{nl, kernel_ast, envelope, reply}``. Bridge-layer errors
    propagate as ``LLMBridgeError``; semantic errors from
    ``themis.run`` propagate as the original exception so the caller
    can distinguish bridge bugs from kernel rejection.
    """
    import themis

    kernel_ast = nl_to_kernel_ast(nl, api_key=api_key, model=model)
    envelope = themis.run(kernel_ast)
    reply = render_reply(envelope, nl=nl, api_key=api_key, model=model)
    return {
        "nl": nl,
        "kernel_ast": kernel_ast,
        "envelope": envelope,
        "reply": reply,
    }
