"""LLM bridge — NL → kernel_ast and result → a reply in the reader's language.

Sits OUTSIDE the kernel by design. Themis itself never calls an LLM;
this module is web-side glue that:

1. Loads ``themis/prompts/nl_to_kernel_ast.md`` as the system prompt.
2. Asks the LLM to emit one kernel_ast JSON for the user's NL.
3. Runs ``themis.run`` on the emitted JSON.
4. Loads ``themis/prompts/response_rendering.md``, feeds the structured
   result back, and asks the LLM for a reply in the language the caller
   named.

**Two languages meet in this module and they are different questions.**
What this package SAYS to a model — the paragraph wrapped around each
payload — continues the prompt document it is sent with: one document, one
language, and the frame is the next paragraph of it. What the model says
BACK reaches a person, so the reader's language is a parameter of the
request, named by its own endonym, and said once per call. Every text
here that a reader can end up holding travels as :class:`themis.language`
words rather than as a finished string.

Both calls that produce reader text take a ``lang``. Neither reads it off
the prompt, and no prompt says a language of its own — that is what lets
one document render every language, and it is why a frame written in the
document's language is not a text owed a translation.

Nothing in ``themis.web.app`` passes ``lang`` yet: the browser holds the
reader's choice locally and renders the kernel's words itself, so no
request body carries it and both LLM surfaces run at
:data:`themis.language.DEFAULT` whoever is asking. That is a wiring gap on
the endpoints rather than a fact about this module.

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
``项目/oauth-fingerprint-proxy/`` with ``python proxy.py``. It not running
is the ordinary case for anyone who has just cloned this, so it is a
refusal that says so — see :func:`_ask_model`.

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

from themis import language

from .bridge_words import Bridge

_REPO_ROOT = Path(__file__).parent.parent.parent
_PROMPT_NL_TO_AST = _REPO_ROOT / "themis" / "prompts" / "nl_to_kernel_ast.md"
_PROMPT_RENDER = _REPO_ROOT / "themis" / "prompts" / "response_rendering.md"
_PROMPT_PROPOSE_PRIORS = _REPO_ROOT / "themis" / "prompts" / "propose_theta_priors.md"
_EXAMPLES_DIR = _REPO_ROOT / "themis" / "prompts" / "examples"
# NL→kernel_ast few-shot: intentionally EMPTY. Three same-shaped worked
# pairs (one behavior + one confounder) used to live here. As concrete
# demonstrations they did two jobs at once: anchored the JSON format AND
# homogenized output SHAPE — the model collapsed almost every question to
# that confounder triangle regardless of the structural units the NL
# actually signalled. Format anchoring (variable = bare predicate; atoms
# carry `args`) now lives in the prompt's §Schema outline as an explicit
# format note, so the `args`-leak these guarded against stays covered
# without a shape template biasing every graph. The example files remain on
# disk under prompts/examples/ for human reference; they are not injected.
# Repopulate only with genuinely diverse shapes if a real driver appears.
_FEWSHOT_NAMES: tuple[str, ...] = ()

_DEFAULT_MODEL = os.environ.get("THEMIS_LLM_MODEL", "claude-sonnet-4-6")
_DEFAULT_PROXY_URL = "http://127.0.0.1:7777"


class LLMBridgeError(language.Voiced, RuntimeError):
    """The bridge did not get back what it asked a model for.

    A CHANNEL, carrying every species in
    :class:`themis.web.bridge_words.Bridge`. It stays one class because
    what a caller does about it is one thing — this step produced nothing
    usable — and which of the eleven it was is read off ``species`` by the
    surface that words it for a reader.

    Distinct from the semantic errors ``themis.run`` raises, and now
    distinct in the way that matters rather than only by type: both carry
    their own sentence, so the web edge hands both to a reader in the
    reader's language instead of one as a sentence and one as a diagnostic.
    """


def _load_system_prompt(path: Path) -> str:
    if not path.exists():
        raise LLMBridgeError(Bridge.A_PROMPT_IS_MISSING, path=path)
    return path.read_text(encoding="utf-8")


_fewshot_cache: "list[dict] | None" = None


def _fewshot_messages() -> list[dict]:
    """The worked NL→kernel_ast pairs named in ``_FEWSHOT_NAMES``, as real
    few-shot turns (user = nl_input, assistant = the kernel_ast JSON).
    Currently ``_FEWSHOT_NAMES`` is empty (see the note there), so this
    returns ``[]`` and the prompt's §Schema outline carries the format
    anchor instead. Retained so a genuinely diverse example set can be
    reinstated without re-plumbing the call site."""
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
            Bridge.THE_SDK_IS_NOT_INSTALLED, package="anthropic"
        ) from exc

    explicit = api_key or os.environ.get("ANTHROPIC_API_KEY")
    if isinstance(explicit, str) and explicit.startswith("sk-ant-api"):
        return Anthropic(api_key=explicit)

    proxy_url = os.environ.get("OAUTH_PROXY_URL", _DEFAULT_PROXY_URL)
    return Anthropic(base_url=proxy_url, api_key=explicit or "proxy")


def _unreached(exc: BaseException, address: str) -> LLMBridgeError:
    """Which of the three ways this call did not come back with an answer.

    Split by what the reader does next rather than by status code: start
    the thing at that address, fix the credential it refused, or neither
    of those. The SDK's own tree divides the first two off cleanly — a
    failure with no response at all, and the two statuses that are about
    who is asking — so the third is the residue and says only what is
    true of every member of it, with the SDK's own text beside it. A
    residue that names itself is not the same as a fallback: what made
    this worth fixing is a sentence that read like an answer.
    """
    from anthropic import (APIConnectionError, AuthenticationError,
                           PermissionDeniedError)

    if isinstance(exc, APIConnectionError):
        return LLMBridgeError(Bridge.NOTHING_ANSWERED_AT_THAT_ADDRESS,
                              address=address)
    if isinstance(exc, (AuthenticationError, PermissionDeniedError)):
        return LLMBridgeError(Bridge.THE_CREDENTIAL_WAS_REFUSED,
                              address=address, complaint=str(exc))
    return LLMBridgeError(Bridge.THE_CALL_CAME_BACK_WITHOUT_AN_ANSWER,
                          address=address, complaint=str(exc))


def _ask_model(client, **kwargs):
    """The one place this module speaks to a model.

    Every other way the bridge comes back empty is raised where this
    module reads a REPLY, and is worded there. Not getting one is raised
    by the SDK, in its own English, and nothing caught it — so the person
    waiting in the browser was handed the stage sentence and nothing else,
    which says the step did not happen and is equally true of a model that
    declined, a reply that was not JSON, and a socket that was never
    opened. The call is this module's, so its failures are this module's
    to word, and there is one line for them to be raised at.
    """
    from anthropic import AnthropicError

    try:
        return client.messages.create(**kwargs)
    except AnthropicError as exc:
        raise _unreached(exc, str(client.base_url)) from exc


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
            Bridge.THE_REPLY_CARRIES_NO_JSON, reply=text[:200])
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
            Bridge.THE_JSON_NEVER_CLOSES, reply=text[:200])
    raw = text[start:end]
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LLMBridgeError(
            Bridge.THE_JSON_DID_NOT_PARSE,
            complaint=exc, payload=raw[:200]) from exc


def nl_to_kernel_ast(
    nl: str,
    *,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
    max_attempts: int = 3,
) -> dict:
    """Turn one NL question into a kernel_ast dict via the project's
    canonical prompt. Returns the dict the LLM emits — caller runs
    ``themis.run`` on it.

    Retries only on a *parse* failure. Emitting malformed JSON is an
    occasional model slip — most common on the complex query shapes
    (counterfactual) whose verbose Chinese ambiguity strings occasionally
    carry an unescaped character — and a fresh sample almost always parses.
    A ``{"error": ...}`` refusal is a deliberate decision, never retried.
    """
    system = _load_system_prompt(_PROMPT_NL_TO_AST)
    client = _client(api_key)
    fewshot = _fewshot_messages()
    last_parse_err: LLMBridgeError | None = None
    for _ in range(max(1, max_attempts)):
        msg = _ask_model(
            client,
            model=model,
            max_tokens=4000,
            system=system,
            messages=[*fewshot, {"role": "user", "content": nl}],
        )
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text"
        )
        try:
            parsed = _extract_first_json_object(text)
        except LLMBridgeError as exc:
            last_parse_err = exc
            continue
        if "error" in parsed and "version" not in parsed:
            # The prompt allows {"error": "..."} as a refusal shape.
            raise LLMBridgeError(
                Bridge.THE_MODEL_DECLINED_THE_QUESTION,
                reason=parsed["error"])
        return parsed
    raise last_parse_err  # type: ignore[misc]  # set once the loop ran ≥1 time


def render_reply(
    envelope: dict,
    *,
    nl: str | None = None,
    lang: language.Lang | str = language.DEFAULT,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> str:
    """Turn a ``themis.run`` envelope into a reply in the reader's language.

    The reader's language is a parameter of the request, not a property of
    the prompt: one document renders every language, and this is the single
    place that says which one. It is named by its own endonym, because an
    instruction to answer in one language should not first have to be read
    in another.
    """
    system = _load_system_prompt(_PROMPT_RENDER)
    client = _client(api_key)

    user_msg = ""
    if nl:
        user_msg += f"The user asked: {nl}\n\n"
    user_msg += (
        f"Write the reply in {language.endonym(lang)}.\n\n"
        "Below is the complete themis.run envelope (program / "
        "merged_program / results). Render it as the prompt describes.\n\n"
    )
    user_msg += json.dumps(envelope, ensure_ascii=False, indent=2)

    msg = _ask_model(
        client,
        model=model,
        max_tokens=8000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    return "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    ).strip()


def _atom_label(atom: dict) -> str:
    """`{"predicate": "veg", "args": [...]}` -> `veg` (args dropped; the
    prior is per-unit, the predicate name is what the reader weighs)."""
    return str((atom or {}).get("predicate", "?"))


def _prob_key_repr(skeleton: dict) -> str:
    """Render a probability skeleton as `P(target=v | g1=v1, g2=v2)` for the
    prompt so the model reasons about a human-readable quantity, not raw JSON."""
    tgt = skeleton.get("target", {})
    head = f"{_atom_label(tgt.get('atom', {}))}={tgt.get('value')}"
    given = skeleton.get("given") or []
    if not given:
        return f"P({head})"
    conds = ", ".join(
        f"{_atom_label(g.get('atom', {}))}={g.get('value')}" for g in given
    )
    return f"P({head} | {conds})"


def propose_theta_priors(
    program: dict,
    skeletons: list[dict],
    *,
    lang: language.Lang | str = language.DEFAULT,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> list[dict]:
    """Ask the LLM for a common-knowledge prior for each missing probability.

    ``skeletons`` are the ``kind == "probability"`` records the kernel
    emitted in ``investigation_requests`` (value == null). Returns the same
    skeletons, in the same order, each with ``value`` filled, ``provenance``
    set to ``"llm_prior"``, and ``annotations.source`` carrying the model's
    one-line reason — i.e. ready to drop into a ``parameter_fill_bundle``.

    The disclosure is the kernel's job: every ``llm_prior`` value surfaces in
    ``extensions.llm_proposed_review`` so the answer says which numbers are
    assumed. This bridge only sources the numbers; it never hides them.

    Which is why the reason is asked for in the reader's language, the way
    the reply is: it is not a note this bridge keeps, it is the ground the
    person is shown beside a number they are being asked to review.
    """
    if not skeletons:
        return []
    system = _load_system_prompt(_PROMPT_PROPOSE_PRIORS)
    client = _client(api_key)

    enumerated = [
        {"index": i, "probability": _prob_key_repr(sk)}
        for i, sk in enumerate(skeletons)
    ]
    user_msg = (
        f"Write every reason in {language.endonym(lang)}.\n\n"
        "The causal graph (kernel program):\n"
        + json.dumps(program, ensure_ascii=False, indent=2)
        + "\n\nThe probabilities that need a prior. Fill in value and "
        "reason for every index; leave none out:\n"
        + json.dumps(enumerated, ensure_ascii=False, indent=2)
    )
    msg = _ask_model(
        client,
        model=model,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": user_msg}],
    )
    text = "".join(
        b.text for b in msg.content if getattr(b, "type", None) == "text"
    )
    parsed = _extract_first_json_object(text)
    priors = parsed.get("priors")
    if not isinstance(priors, list):
        raise LLMBridgeError(
            Bridge.THE_REPLY_CARRIES_NO_PRIORS, reply=text[:200])

    by_index: dict[int, dict] = {}
    for p in priors:
        if isinstance(p, dict) and isinstance(p.get("index"), int):
            by_index[p["index"]] = p

    filled: list[dict] = []
    for i, sk in enumerate(skeletons):
        p = by_index.get(i)
        if p is None:
            raise LLMBridgeError(
                Bridge.A_PROBABILITY_GOT_NO_PRIOR,
                index=i, probability=_prob_key_repr(sk))
        try:
            raw_value = p.get("value")
            if not isinstance(raw_value, (bool, int, float, str)):
                # Absent or structured: the same failure as a non-numeric
                # string, and the handler below says so once for both.
                raise TypeError(type(raw_value).__name__)
            value = float(raw_value)
        except (TypeError, ValueError) as exc:
            raise LLMBridgeError(
                Bridge.A_PRIOR_IS_NOT_A_NUMBER,
                index=i, value=p.get("value")) from exc
        if not (0.0 <= value <= 1.0):
            raise LLMBridgeError(
                Bridge.A_PRIOR_IS_NOT_A_PROBABILITY, index=i, value=value)
        # Refused rather than filled in. ``annotations.source`` is required
        # non-empty on an ``llm_prior`` — the checker's own note says an
        # empty one would let a fabricated number through undisclosed — and
        # a constant written here satisfies that check while disclosing
        # nothing, which is the check defeated rather than met. It is also
        # the one text in this module a reader would meet that no reader's
        # language could be chosen for: the reason beside every other prior
        # is the model's, and this one would have been ours.
        reason = str(p.get("reason") or "").strip()
        if not reason:
            raise LLMBridgeError(
                Bridge.A_PRIOR_CAME_WITH_NO_REASON,
                index=i, probability=_prob_key_repr(sk))
        out = dict(sk)
        out["value"] = value
        out["provenance"] = "llm_prior"
        out["annotations"] = {"source": reason}
        filled.append(out)
    return filled


def ask(
    nl: str,
    *,
    lang: language.Lang | str = language.DEFAULT,
    api_key: str | None = None,
    model: str = _DEFAULT_MODEL,
) -> dict:
    """End-to-end: NL → kernel_ast → themis.run → a reply in ``lang``.

    Returns ``{nl, kernel_ast, envelope, reply}``. Bridge-layer errors
    propagate as ``LLMBridgeError``; semantic errors from
    ``themis.run`` propagate as the original exception so the caller
    can distinguish bridge bugs from kernel rejection.

    Only the reply takes a language. The kernel_ast does not — a program
    is the same program whoever reads it, and the envelope carries no
    language for the same reason.
    """
    import themis

    kernel_ast = nl_to_kernel_ast(nl, api_key=api_key, model=model)
    envelope = themis.run(kernel_ast)
    reply = render_reply(envelope, nl=nl, lang=lang, api_key=api_key,
                         model=model)
    return {
        "nl": nl,
        "kernel_ast": kernel_ast,
        "envelope": envelope,
        "reply": reply,
    }
