"""LLM bridge — NL → kernel_ast and result → Chinese reply.

Sits OUTSIDE the kernel by design. Themis itself never calls an LLM;
this module is web-side glue that:

1. Loads ``docs/prompts/nl_to_kernel_ast.md`` as the system prompt.
2. Asks the LLM to emit one kernel_ast JSON for the user's NL.
3. Runs ``themis.run`` on the emitted JSON.
4. Loads ``docs/prompts/response_rendering.md``, feeds the structured
   result back, asks the LLM for a Chinese reply.

Routing: by default the SDK is pointed at the local
``oauth-fingerprint-proxy`` (``http://127.0.0.1:7777``, override via
``OAUTH_PROXY_URL``). The proxy reads the live OAuth token from
``~/.claude/.credentials.json`` and rewrites the request so it carries the
Claude Code fingerprint — that's what routes the call to Claude Max
included quota instead of "extra usage" billing. If the caller supplies
an actual API key (``sk-ant-api...`` via the ``api_key`` argument or
``ANTHROPIC_API_KEY`` env var) we bypass the proxy and talk to
``api.anthropic.com`` directly with normal pay-as-you-go billing.

The proxy must be running. Start it from
``项目/oauth-fingerprint-proxy/`` with ``python proxy.py``.

Model defaults to ``claude-sonnet-4-6``; override via ``THEMIS_LLM_MODEL``.

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
_EXAMPLES_DIR = _REPO_ROOT / "themis" / "prompts" / "examples"
# The worked NL→kernel_ast pairs the prompt references. The prompt only
# shows placeholder fragments (<atom> = predicate+args, variable = bare
# <name>); without these concrete pairs as actual few-shot, the model has
# just one concrete predicate shape (the atom's) and leaks `args` onto
# variable declarations. Loading them is the fix the prompt already promises.
_FEWSHOT_NAMES = ("exercise_waist", "sleep_cognition", "veggies_blood_pressure")

_DEFAULT_MODEL = os.environ.get("THEMIS_LLM_MODEL", "claude-sonnet-4-6")
_DEFAULT_PROXY_URL = "http://127.0.0.1:7777"


class LLMBridgeError(RuntimeError):
    """Bridge-layer error (missing key, parse failure, API error).

    Distinct from semantic errors raised by ``themis.run`` so the UI
    can render them differently.
    """


def _load_system_prompt(path: Path) -> str:
    if not path.exists():
        raise LLMBridgeError(f"prompt file missing: {path}")
    return path.read_text(encoding="utf-8")


_fewshot_cache: "list[dict] | None" = None


def _fewshot_messages() -> list[dict]:
    """The worked NL→kernel_ast pairs the prompt references, as real
    few-shot turns (user = nl_input, assistant = the kernel_ast JSON).
    These show concrete variable declarations (bare predicate, no args)
    beside atoms (predicate + args), anchoring the distinction the
    placeholder-only prompt can't."""
    global _fewshot_cache
    if _fewshot_cache is None:
        msgs: list[dict] = []
        for name in _FEWSHOT_NAMES:
            try:
                d = json.loads((_EXAMPLES_DIR / f"{name}.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            nl, ka = d.get("nl_input"), d.get("kernel_ast")
            if nl and ka:
                msgs.append({"role": "user", "content": nl})
                msgs.append({"role": "assistant", "content": json.dumps(ka, ensure_ascii=False)})
        _fewshot_cache = msgs
    return _fewshot_cache


def _client(api_key: str | None = None):
    """Build the Anthropic client.

    Direct path: when ``api_key`` (argument or ``ANTHROPIC_API_KEY``) is a
    real API key (``sk-ant-api...``), call ``api.anthropic.com`` directly.

    Proxy path (default): point at the local oauth-fingerprint-proxy and
    let it supply the real OAuth token + Claude Code fingerprint. The SDK
    requires a non-empty ``api_key`` even when ``base_url`` redirects, so
    pass a placeholder.
    """
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise LLMBridgeError(
            "anthropic SDK not installed; pip install anthropic"
        ) from exc

    explicit = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if isinstance(explicit, str) and explicit.startswith("sk-ant-api"):
        return Anthropic(api_key=explicit)

    proxy_url = os.environ.get("OAUTH_PROXY_URL", _DEFAULT_PROXY_URL)
    return Anthropic(base_url=proxy_url, api_key=explicit or "proxy")


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
        messages=[*_fewshot_messages(), {"role": "user", "content": nl}],
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
        max_tokens=8000,
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
