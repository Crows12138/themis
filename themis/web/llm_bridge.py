"""LLM bridge — NL → kernel_ast and result → a reply in the reader's language.

Sits OUTSIDE the kernel by design. Themis itself never calls an LLM;
this module is web-side glue that:

1. Asks the LLM, under ``themis/prompts/variables_to_consider.md``, for
   the variables the user's question has to consider.
2. Loads ``themis/prompts/nl_to_kernel_ast.md`` as the system prompt and
   asks the LLM to emit one kernel_ast JSON for the user's NL, with that
   list beside it.
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

Routing is declared by whoever deploys this, and read in one place,
:func:`_endpoint`:

- ``THEMIS_LLM_API_KEY`` is a key this deployment pays with. When it is
  set, every call goes to ``THEMIS_LLM_BASE_URL`` (default
  ``https://api.anthropic.com``) with it, and a key a visitor pastes is
  not read — the deployment has said who pays. Any service that speaks
  the Anthropic Messages API will do; DeepSeek's is
  ``https://api.deepseek.com/anthropic``.
- ``THEMIS_LLM_MODEL`` is the model asked for there (default
  ``claude-sonnet-4-6``), read when the call is made.
- With no key of its own a deployment is the local product. Calls go to
  the ``oauth-fingerprint-proxy`` on this machine
  (``http://127.0.0.1:7777``, override via ``OAUTH_PROXY_URL``), which
  reads the live OAuth token from ``~/.claude/.credentials.json`` and
  adds the Claude Code fingerprint; a visitor who pastes a key into the
  page's panel is sent to ``api.anthropic.com`` with it instead, because
  an Anthropic key is what that panel asks for.

It used to be guessed, twice. This module chose between the proxy and the
API by whether a key began ``sk-ant-api``, so any other provider's key
went to the proxy; and ``app.py`` wrote a placeholder key into the
process environment and handed it down with every request, so a key the
operator configured never arrived here at all.

Without a key the proxy must be running. Start it from
``项目/oauth-fingerprint-proxy/`` with ``python proxy.py``. It not running
is the ordinary case for anyone who has just cloned this, so it is a
refusal that says so — see :func:`_ask_model`.

Both LLM calls are blocking — no streaming back to the browser in
this slice; add when there's a real-case driver for partial-result
display.
"""
from __future__ import annotations

import json
import math
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import NamedTuple

from themis import language
from themis.output import bounded_view

from . import asked_for
from .bridge_words import Bridge

_REPO_ROOT = Path(__file__).parent.parent.parent
_PROMPT_CONSIDER = _REPO_ROOT / "themis" / "prompts" / "variables_to_consider.md"
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

_ANTHROPIC_MODEL = "claude-sonnet-4-6"
_ANTHROPIC_URL = "https://api.anthropic.com"
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


class Endpoint(NamedTuple):
    """Where a call goes, the key it carries, and the model asked for."""
    base_url: str
    api_key: str
    model: str


def deployment_pays() -> bool:
    """Whether this deployment declared a key of its own.

    Read by the page as well as here: a deployment that pays has no use
    for a visitor's key, so it does not ask for one.
    """
    return bool(os.environ.get("THEMIS_LLM_API_KEY"))


def _endpoint(api_key: str | None = None) -> Endpoint:
    """The one place routing is decided; the module docstring says how.

    ``api_key`` is a visitor's, from the page's panel, and counts only
    where the deployment has not said it pays. The proxy is sent a
    placeholder because the SDK will not build a client without a key,
    and the proxy supplies the real credential itself.
    """
    model = os.environ.get("THEMIS_LLM_MODEL") or _ANTHROPIC_MODEL
    own = os.environ.get("THEMIS_LLM_API_KEY")
    if own:
        return Endpoint(os.environ.get("THEMIS_LLM_BASE_URL") or _ANTHROPIC_URL,
                        own, model)
    if api_key:
        return Endpoint(_ANTHROPIC_URL, api_key, model)
    return Endpoint(os.environ.get("OAUTH_PROXY_URL", _DEFAULT_PROXY_URL),
                    "proxy", model)


def _client(api_key: str | None = None):
    """The SDK client for :func:`_endpoint`'s address and key."""
    try:
        from anthropic import Anthropic
    except ImportError as exc:
        raise LLMBridgeError(
            Bridge.THE_SDK_IS_NOT_INSTALLED, package="anthropic"
        ) from exc

    where = _endpoint(api_key)
    return Anthropic(base_url=where.base_url, api_key=where.api_key)


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

    No call here asks a model to think first, and it is said here rather
    than left to the provider. Each call's ``max_tokens`` is a budget for
    the answer, and only text blocks are read. A model that thinks unless
    told not to spends the budget on thinking nobody reads and is cut off
    before the answer: DeepSeek's did, and two of five worked examples came
    back with no JSON and two more with an empty reading.
    """
    from anthropic import AnthropicError

    try:
        return client.messages.create(thinking={"type": "disabled"}, **kwargs)
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


def variables_to_consider(
    nl: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """The variables a careful reader of the domain would have a graph of
    ``nl`` consider, listed before any graph is drawn.

    Asked of its own call because the translation, asked to do it too,
    does not. Measured on the demo's model: a question known for one
    answer — a correlation explained by one hidden common cause — was
    drawn with that cause and nothing else in nine translations of nine,
    and three rewordings of the prompt and a thinking budget left it
    there, while a call asked only to list the domain's variables named
    the rest of it. A common cause left out of a graph biases the answer,
    and nothing downstream can see what is missing.

    The same call judges the exposure's effect on the outcome, one
    direction at a time, and the translation draws the exposure's own link
    by that judgement. Judged by the translation from the question, an
    effect running against what the question suspects was left out: asked
    whether doctors cause deaths, it drew doctors with no effect on deaths
    at all.

    Retried on a reply that does not parse, as a program is.
    """
    system = _load_system_prompt(_PROMPT_CONSIDER)
    client = _client(api_key)
    model = model or _endpoint(api_key).model
    last_parse_err: LLMBridgeError | None = None
    for _ in range(max(1, max_attempts)):
        msg = _ask_model(client, model=model, max_tokens=2000, system=system,
                         messages=[{"role": "user", "content": nl}])
        text = "".join(
            b.text for b in msg.content if getattr(b, "type", None) == "text")
        try:
            return _extract_first_json_object(text)
        except LLMBridgeError as exc:
            last_parse_err = exc
    raise last_parse_err  # type: ignore[misc]  # set once the loop ran ≥1 time


def _question(nl: str, considered: dict | None) -> str:
    """The turn a program is written from: the question, and beside it the
    variables to consider where a list was drawn up — as one object, so
    that the prompt can tell the reader's words from the list by the
    turn's form (its section "When the question comes with variables to
    consider")."""
    if considered is None:
        return nl
    return json.dumps({"question": nl, "variables_to_consider": considered},
                      ensure_ascii=False)


def nl_to_kernel_ast(
    nl: str,
    *,
    considered: dict | None = None,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """Turn one NL question into a kernel_ast dict via the project's
    canonical prompt, with ``considered`` — what
    :func:`variables_to_consider` listed — beside it where there is one.
    Returns the dict the LLM emits — caller runs ``themis.run`` on it.
    """
    return _program_from([{"role": "user", "content": _question(nl, considered)}],
                         api_key=api_key, model=model, max_attempts=max_attempts)


def revise_kernel_ast(
    nl: str,
    program: dict,
    correction: str,
    *,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """A reading of ``nl`` corrected in the reader's own words.

    A program written from a sentence is one reading of it, and the page
    shows the reader which one. When it is not what they meant they say so
    in a sentence rather than by editing a graph, and the model is handed
    the question, the program it wrote and that sentence, as the turns of
    one exchange. Asked again from the question alone it would read the
    whole sentence afresh and could change what the reader had accepted;
    handed the program, it has something to change only part of.

    The reader's sentence is sent as it was written, the way the question
    is: what a reply after a program means, and what to do with it, is the
    prompt's to say, in its section "When a program is followed by another
    turn".

    ``program`` is the one on the reader's screen, which may already carry
    their own edits to the graph, not necessarily the one first written.
    """
    return _program_from([
        {"role": "user", "content": nl},
        {"role": "assistant",
         "content": json.dumps(program, ensure_ascii=False)},
        {"role": "user", "content": correction},
    ], api_key=api_key, model=model, max_attempts=max_attempts)


def repair_kernel_ast(
    nl: str,
    program: dict,
    refusal: BaseException,
    *,
    considered: dict | None = None,
    api_key: str | None = None,
    model: str | None = None,
    max_attempts: int = 3,
) -> dict:
    """The program ``nl`` was read as, with what the kernel refused mended.

    The exchange opens with the turn the program was written from, the
    list beside the question included, so that the model mends the reading
    it made rather than one of a shorter question.

    A program the kernel refuses was a reading with a slip in its form — a
    key a declaration does not take, a statement of no kind the language
    has. Asked again from the question alone, the model writes a new
    reading, which may slip again elsewhere and need not be the reading it
    had; handed the program and the refusal, it has one thing to mend.

    The refusal is the kernel's turn in the same exchange a reader's
    correction takes, and it is sent as data under ``kernel_refused`` so
    that the prompt can tell the two speakers apart by the turn's form — see
    its section "When a program is followed by another turn". Its words are
    the kernel's own, said in the language the prompt is written in: the
    reader of this turn is the model, not the person who asked.
    """
    said = (language.assemble(refusal.species.words, refusal.said,
                              refusal.words, lang=language.Lang.EN)
            if isinstance(refusal, language.Voiced) else str(refusal))
    return _program_from([
        {"role": "user", "content": _question(nl, considered)},
        {"role": "assistant",
         "content": json.dumps(program, ensure_ascii=False)},
        {"role": "user",
         "content": json.dumps({"kernel_refused": said},
                               ensure_ascii=False)},
    ], api_key=api_key, model=model, max_attempts=max_attempts)


def _program_from(
    turns: list[dict],
    *,
    api_key: str | None,
    model: str | None,
    max_attempts: int,
) -> dict:
    """The program a model writes at the end of ``turns``.

    Retries only on a *parse* failure. Emitting malformed JSON is an
    occasional model slip — most common on the complex query shapes
    (counterfactual) whose verbose Chinese ambiguity strings occasionally
    carry an unescaped character — and a fresh sample almost always parses.
    A ``{"error": ...}`` refusal is a deliberate decision, never retried.
    """
    system = _load_system_prompt(_PROMPT_NL_TO_AST)
    client = _client(api_key)
    model = model or _endpoint(api_key).model
    fewshot = _fewshot_messages()
    last_parse_err: LLMBridgeError | None = None
    for _ in range(max(1, max_attempts)):
        msg = _ask_model(
            client,
            model=model,
            max_tokens=4000,
            system=system,
            messages=[*fewshot, *turns],
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
    model: str | None = None,
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
    model = model or _endpoint(api_key).model

    user_msg = ""
    if nl:
        user_msg += f"The user asked: {nl}\n\n"
    user_msg += (
        f"Write the reply in {language.endonym(lang)}.\n\n"
        "Below is the themis.run envelope (program / merged_program / "
        "results), with any part too large to send folded into a marker. "
        "Render it as the prompt describes.\n\n"
    )
    # The reader of this call is a model, and the envelope is the
    # verifier's record: its size is the question's. What a model is sent
    # of it is decided in one place for every channel that sends one.
    user_msg += json.dumps(bounded_view.view(envelope), ensure_ascii=False,
                           separators=(",", ":"))

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


#: What one prior costs a reply, and how many one call carries. On
#: deepseek-v4-pro (2026-09-27) 52 priors and their reasons came back in 1826
#: output tokens, about 35 each; 60 leaves room for a longer reason or a
#: wordier language. A call's budget is sized to the priors it carries: a
#: fixed 2000 ran out at about 55, which a graph with five common causes of
#: its outcome already needs. A call is kept to 50 because the reply is
#: written at about 57 tokens a second — 70 priors in one call took 44
#: seconds — and the parts run side by side.
_PRIOR_TOKENS_EACH = 60
_PRIOR_TOKENS_AROUND = 500
_PRIORS_PER_CALL = 50
#: A reader waits for the slowest round rather than for the sum, and a list
#: that would take more calls than this is refused before any is made
#: rather than left to run out the request: two rounds, about a minute.
_PRIOR_CALLS_AT_ONCE = 4
_PRIOR_CALLS_AT_MOST = 8


def _prior_calls(requests: list) -> list[list[int]]:
    """The indices of ``requests``, as the calls they are asked for in.

    A request is a skeleton or a :class:`themis.web.asked_for.Table`. Skeletons are gathered by
    the distribution they belong to — one variable under one condition,
    whose values must sum to one — in the order the kernel listed them; a
    table is a distribution of its own. Whole distributions are packed into
    as few calls of at most ``_PRIORS_PER_CALL`` numbers as the list needs,
    filled about evenly, since the calls run side by side and the reader
    waits for the largest. So the numbers that must agree with each other
    are always written by one reply; one distribution larger than a call
    goes alone rather than be split.
    """
    distributions: dict[tuple, list[int]] = {}
    for i, request in enumerate(requests):
        if isinstance(request, asked_for.Table):
            key: tuple = ("table", i)
        else:
            target = asked_for.atom_label((request.get("target") or {}).get("atom", {}))
            key = (target, tuple(sorted(
                (asked_for.atom_label(g.get("atom", {})), repr(g.get("value")))
                for g in request.get("given") or [])))
        distributions.setdefault(key, []).append(i)
    total = sum(asked_for.numbers(r) for r in requests)
    parts = -(-total // _PRIORS_PER_CALL)
    size = -(-total // parts) if parts else 0
    calls: list[list[int]] = []
    loads: list[int] = []
    for rows in distributions.values():
        load = sum(asked_for.numbers(requests[i]) for i in rows)
        if calls and loads[-1] + load <= size:
            calls[-1].extend(rows)
            loads[-1] += load
        else:
            calls.append(list(rows))
            loads.append(load)
    return calls


def _number(i: int, entry: object, label: str) -> float:
    """The number a reply gave one parameter, or the refusal that says it
    gave none."""
    if not isinstance(entry, dict):
        raise LLMBridgeError(
            Bridge.A_PROBABILITY_GOT_NO_PRIOR, index=i, probability=label)
    raw = entry.get("value")
    try:
        if not isinstance(raw, (bool, int, float, str)):
            # Absent or structured: the same failure as a non-numeric
            # string, and the handler below says so once for both.
            raise TypeError(type(raw).__name__)
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise LLMBridgeError(
            Bridge.A_PRIOR_IS_NOT_A_NUMBER, index=i, value=raw) from exc


def _reason(i: int, entry: dict, label: str) -> str:
    # Refused rather than filled in. ``annotations.source`` is required
    # non-empty on an ``llm_prior`` — the checker's own note says an
    # empty one would let a fabricated number through undisclosed — and
    # a constant written here satisfies that check while disclosing
    # nothing, which is the check defeated rather than met. It is also
    # the one text in this module a reader would meet that no reader's
    # language could be chosen for: the reason beside every other prior
    # is the model's, and this one would have been ours.
    reason = str(entry.get("reason") or "").strip()
    if not reason:
        raise LLMBridgeError(
            Bridge.A_PRIOR_CAME_WITH_NO_REASON, index=i, probability=label)
    return reason


def _cell_from(i: int, skeleton: dict, reply: dict | None) -> dict:
    """The skeleton filled: its value, who supplied it, and why. What the
    kernel wrote — the key, and the kind of conditional it asked for — is
    kept as written, because the statement that settles an ask is the one
    the kernel keyed it to."""
    label = asked_for.cell_label(skeleton)
    value = _number(i, reply, label)
    if not (0.0 <= value <= 1.0):
        raise LLMBridgeError(
            Bridge.A_PRIOR_IS_NOT_A_PROBABILITY, index=i, value=value)
    assert reply is not None  # _number refuses a missing entry
    return asked_for.cell_record(skeleton, value, llm_prior=True,
                                 source=_reason(i, reply, label))


def _model_from(i: int, table: asked_for.Table, reply: dict | None) -> dict:
    """The ``probability_model`` a reply to a table states, every
    parameter with its own reason."""
    if reply is None:
        raise LLMBridgeError(Bridge.A_PROBABILITY_GOT_NO_PRIOR,
                             index=i, probability=asked_for.table_label(table))
    entry = reply.get("baseline")
    label = asked_for.baseline_label(table)
    baseline = _number(i, entry, label)
    if not (0.0 < baseline < 1.0):
        raise LLMBridgeError(Bridge.A_BASELINE_IS_AT_AN_END,
                             index=i, probability=label, value=baseline)
    assert isinstance(entry, dict)  # _number refuses anything else
    given = {r.get("ratio"): r for r in reply.get("odds_ratios") or ()
             if isinstance(r, dict)}
    ratios: list[float] = []
    sources: dict[object, str] = {}
    for j in range(len(table.ratios)):
        label_j = asked_for.ratio_label(table, j)
        value = _number(i, given.get(j), label_j)
        if not (value > 0.0 and math.isfinite(value)):
            raise LLMBridgeError(Bridge.AN_ODDS_RATIO_IS_NOT_POSITIVE,
                                 index=i, probability=label_j, value=value)
        ratios.append(value)
        sources[j] = _reason(i, given[j], label_j)
    sources["baseline"] = _reason(i, entry, label)
    return asked_for.model_record(table, baseline, ratios, llm_prior=True,
                                  sources=sources)


def propose_theta_priors(
    program: dict,
    skeletons: list[dict],
    *,
    lang: language.Lang | str = language.DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> list[dict]:
    """Ask the LLM for a common-knowledge prior for each missing probability.

    ``skeletons`` are the ``kind == "probability"`` records the kernel
    emitted in ``investigation_requests`` (value == null). Returns the
    records to drop into a ``parameter_fill_bundle``, in the order of the
    skeletons: each skeleton with ``value`` filled, ``llm_prior`` set and
    ``annotations.source`` carrying the model's one-line reason, and
    everything else as the kernel wrote it — or, where the skeletons are
    cells of a distribution asked for
    as a table (:func:`themis.web.asked_for.tables`), one ``probability_model`` in their place,
    where the first of them was, every parameter with its own reason.

    The disclosure is the kernel's job: every ``llm_prior`` surfaces in
    ``extensions.llm_proposed_review`` so the answer says which numbers are
    assumed, and a table's form is a line of the assumption ledger. This
    bridge only sources the numbers; it never hides them.

    Which is why the reason is asked for in the reader's language, the way
    the reply is: it is not a note this bridge keeps, it is the ground the
    person is shown beside a number they are being asked to review.

    A long list is asked for in parts (:func:`_prior_calls`), each call
    sent the whole graph and its own requests under their indices in the
    whole list, and the parts are asked side by side.
    """
    if not skeletons:
        return []
    requests = asked_for.requests(program, skeletons)
    calls = _prior_calls(requests)
    if len(calls) > _PRIOR_CALLS_AT_MOST:
        raise LLMBridgeError(
            Bridge.TOO_MANY_PRIORS_TO_ASK_FOR,
            needed=sum(asked_for.numbers(r) for r in requests),
            most=_PRIORS_PER_CALL * _PRIOR_CALLS_AT_MOST)
    system = _load_system_prompt(_PROMPT_PROPOSE_PRIORS)
    client = _client(api_key)
    model = model or _endpoint(api_key).model
    frame = (
        f"Write every reason in {language.endonym(lang)}.\n\n"
        "The causal graph (kernel program):\n"
        + json.dumps(program, ensure_ascii=False, indent=2)
        + "\n\nThe numbers that need a prior. Fill in every index, and "
        "every ratio of a table; leave none out:\n"
    )

    def ask(rows: list[int]) -> dict[int, dict]:
        enumerated = [asked_for.shown(i, requests[i]) for i in rows]
        user_msg = frame + json.dumps(enumerated, ensure_ascii=False, indent=2)
        msg = _ask_model(
            client,
            model=model,
            max_tokens=_PRIOR_TOKENS_AROUND + _PRIOR_TOKENS_EACH * sum(
                asked_for.numbers(requests[i]) for i in rows),
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
        # A reply is read for the rows it was asked for and no others, so
        # an index it strays onto cannot stand in for another call's.
        asked = set(rows)
        return {p["index"]: p for p in priors
                if isinstance(p, dict) and p.get("index") in asked}

    if len(calls) == 1:
        replies = [ask(calls[0])]
    else:
        with ThreadPoolExecutor(
                max_workers=min(_PRIOR_CALLS_AT_ONCE, len(calls))) as pool:
            replies = list(pool.map(ask, calls))
    by_index: dict[int, dict] = {}
    for reply in replies:
        by_index.update(reply)

    return [_model_from(i, r, by_index.get(i)) if isinstance(r, asked_for.Table)
            else _cell_from(i, r, by_index.get(i))
            for i, r in enumerate(requests)]


def ask(
    nl: str,
    *,
    lang: language.Lang | str = language.DEFAULT,
    api_key: str | None = None,
    model: str | None = None,
) -> dict:
    """End-to-end: NL → the variables to consider → kernel_ast →
    themis.run → a reply in ``lang``.

    Returns ``{nl, kernel_ast, envelope, reply}``. Bridge-layer errors
    propagate as ``LLMBridgeError``; semantic errors from
    ``themis.run`` propagate as the original exception so the caller
    can distinguish bridge bugs from kernel rejection.

    Only the reply takes a language. The kernel_ast does not — a program
    is the same program whoever reads it, and the envelope carries no
    language for the same reason.
    """
    import themis

    considered = variables_to_consider(nl, api_key=api_key, model=model)
    kernel_ast = nl_to_kernel_ast(nl, considered=considered, api_key=api_key,
                                  model=model)
    envelope = themis.run(kernel_ast)
    reply = render_reply(envelope, nl=nl, lang=lang, api_key=api_key,
                         model=model)
    return {
        "nl": nl,
        "kernel_ast": kernel_ast,
        "envelope": envelope,
        "reply": reply,
    }
