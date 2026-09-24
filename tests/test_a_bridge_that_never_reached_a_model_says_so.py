"""A call that never reached a model, said to the person who was waiting.

Somebody who has just cloned this and clicks 问 has neither the local
oauth proxy running nor an API key. That is the ordinary first click, and
what it produced was:

    把这个问题变成因果图没有成功（已重试三次）
    诊断信息：Connection error.

The first line is the STAGE sentence, and a stage sentence is true of
every way that step can fail — a model that declined, a reply that was
not JSON, a socket that was never opened. Read on its own it says this
project tried three times to build a causal graph and could not, which is
a claim about what the kernel can do and was not what happened: nothing
was asked of any model. ``themis.web.bridge_words.Bridge`` had eleven
species for what came back unusable and none for nothing coming back,
because those eleven are raised where this module reads a REPLY and the
SDK raises the rest at the one line that speaks to it.

A ``need_key`` boolean was the only thing distinguishing them, computed at
one of the three doors by asking whether ``str(exc)`` contained the
English substring "key". ``APIConnectionError`` says "Connection error.",
so it answered ``false`` for the one person it existed for, and no reader
— browser or test — ever looked, which is why it could be wrong for as
long as it liked.

So what is held here:

- the mapping is TOTAL over this SDK's exception tree, and the tree is
  walked rather than listed, so a class the SDK adds is a failure here
  and not a sentence that quietly says the wrong thing;
- the two failures a reader acts differently on do not read the same, and
  neither of them reads as the stage sentence;
- the ADDRESS is in what the reader is shown, at all three doors, because
  a proxy on this machine and an API on the internet fail identically and
  ask for different things.
"""
from __future__ import annotations

import inspect

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient

import themis
from themis import language
from themis.web import failure, llm_bridge
from themis.web.app import app
from themis.web.bridge_words import Bridge

client = TestClient(app)

#: Where a stubbed client claims it would have sent the call. Not the real
#: default: a test that used the real one could not tell a sentence
#: carrying the address from a sentence with the address written into it.
STUB_ADDRESS = "http://127.0.0.1:9/"

_REQUEST = httpx.Request("POST", STUB_ADDRESS + "v1/messages")
_RESPONSE = httpx.Response(401, request=_REQUEST)

#: The three this module answers with, and what a reader does about each.
REACHING = {
    Bridge.NOTHING_ANSWERED_AT_THAT_ADDRESS,
    Bridge.THE_CREDENTIAL_WAS_REFUSED,
    Bridge.THE_CALL_CAME_BACK_WITHOUT_AN_ANSWER,
}


def _sdk_error_classes() -> list[type]:
    """Every exception this SDK can raise, off the SDK rather than a list.

    A list written here would be a second copy of the tree, kept correct
    by whoever remembered — and the whole defect under test is a case
    that was outside somebody's enumeration.
    """
    return sorted(
        (obj for obj in vars(anthropic).values()
         if isinstance(obj, type)
         and issubclass(obj, anthropic.AnthropicError)),
        key=lambda cls: cls.__name__,
    )


def _an_instance(cls: type) -> BaseException:
    """One of ``cls``, built from what its constructor asks for."""
    params = inspect.signature(cls.__init__).parameters
    kwargs: dict = {}
    if "message" in params:
        kwargs["message"] = "the SDK's own sentence"
    if "request" in params:
        kwargs["request"] = _REQUEST
    if "response" in params:
        kwargs["response"] = _RESPONSE
    if "body" in params:
        kwargs["body"] = None
    return cls(**kwargs)


def _stub(raising: BaseException):
    """A client that fails the way the SDK fails, at a known address."""
    class _Messages:
        @staticmethod
        def create(**kwargs):
            raise raising

    class _Client:
        base_url = STUB_ADDRESS
        messages = _Messages()

    return _Client()


def _reads(exc: language.Voiced, lang: str) -> str:
    return language.assemble(exc.species.words, exc.said, exc.words, lang)


# ===================================== the mapping, over the SDK's own tree


@pytest.mark.parametrize(
    "cls", _sdk_error_classes(), ids=lambda cls: cls.__name__)
def test_every_way_this_sdk_can_fail_reaches_a_species(cls):
    """No class in the tree comes out of this module unworded."""
    voiced = llm_bridge._unreached(_an_instance(cls), STUB_ADDRESS)
    assert isinstance(voiced, llm_bridge.LLMBridgeError)
    assert voiced.species in REACHING


def test_the_two_a_reader_can_act_on_are_named_rather_than_residue():
    """Totality alone is satisfied by answering the residue every time.

    Which would be the defect again one layer in: every failure worded,
    every failure worded the SAME. So the two that tell a reader what to
    do are pinned to their classes.
    """
    for cls in (anthropic.APIConnectionError, anthropic.APITimeoutError):
        voiced = llm_bridge._unreached(_an_instance(cls), STUB_ADDRESS)
        assert voiced.species is Bridge.NOTHING_ANSWERED_AT_THAT_ADDRESS, cls
    for cls in (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
        voiced = llm_bridge._unreached(_an_instance(cls), STUB_ADDRESS)
        assert voiced.species is Bridge.THE_CREDENTIAL_WAS_REFUSED, cls


def test_nothing_answering_and_a_credential_refused_do_not_read_the_same():
    """The counterexample the old arrangement could not produce.

    One says start the thing at that address; the other says the thing at
    that address is running and will not take what you gave it. A reader
    handed the same sentence for both has been told neither.
    """
    nothing = llm_bridge._unreached(
        _an_instance(anthropic.APIConnectionError), STUB_ADDRESS)
    refused = llm_bridge._unreached(
        _an_instance(anthropic.AuthenticationError), STUB_ADDRESS)
    for lang in ("zh", "en"):
        assert _reads(nothing, lang) != _reads(refused, lang)


def test_the_sdks_own_text_survives_beside_the_sentence():
    """What the SDK said is kept, in the species that has nothing else.

    The residue is honest only if it carries the one fact it has.
    """
    voiced = llm_bridge._unreached(
        _an_instance(anthropic.BadRequestError), STUB_ADDRESS)
    assert voiced.species is Bridge.THE_CALL_CAME_BACK_WITHOUT_AN_ANSWER
    for lang in ("zh", "en"):
        assert "the SDK's own sentence" in _reads(voiced, lang)


def test_the_address_is_in_the_sentence_and_moves_with_it():
    """A proxy on this machine and an API on the internet fail alike.

    Held both ways round: the address appears, AND a different address
    produces a different sentence — otherwise this passes on a sentence
    that has the default written into it.
    """
    here = llm_bridge._unreached(
        _an_instance(anthropic.APIConnectionError), STUB_ADDRESS)
    elsewhere = llm_bridge._unreached(
        _an_instance(anthropic.APIConnectionError), "https://api.example/")
    for lang in ("zh", "en"):
        assert STUB_ADDRESS in _reads(here, lang)
        assert "api.example" in _reads(elsewhere, lang)
        assert _reads(here, lang) != _reads(elsewhere, lang)


def test_a_call_that_did_reach_a_model_is_untouched(monkeypatch):
    """The wrapper words failures and nothing else."""
    sentinel = object()

    class _Client:
        base_url = STUB_ADDRESS
        messages = type("M", (), {"create": staticmethod(
            lambda **kw: sentinel)})()

    assert llm_bridge._ask_model(_Client(), model="m") is sentinel


# ===================================== the three doors a reader can be at


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program_missing_its_numbers():
    """X→Y confounded by Z, identifiable and blocked on distributions —
    so ``/api/assume`` has probability skeletons to ask a model about."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("y"), "value": True},
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }


#: Every door that talks to a model, and the stage each attributes to.
DOORS = [
    ("/api/ask", {"nl": "x 导致 y 吗"}, "nl_to_kernel_ast"),
    ("/api/assume", {"program": _program_missing_its_numbers()},
     "propose_theta_priors"),
    ("/api/render", {"program": _program_missing_its_numbers(),
                     "result": themis.run(
                         _program_missing_its_numbers())["results"][0],
                     "nl": "x 导致 y 吗"}, "render_reply"),
]


@pytest.mark.parametrize("path, body, stage", DOORS,
                         ids=[d[0] for d in DOORS])
def test_a_door_with_nothing_at_the_other_end_says_that(
        monkeypatch, path, body, stage):
    """All three, because the field that tried to say this was at one."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: _stub(
            _an_instance(anthropic.APIConnectionError)))

    r = client.post(path, json=body)
    assert r.status_code == 400, r.text
    got = r.json()
    assert got["stage"] == stage
    assert got["words"] == dict(Bridge.NOTHING_ANSWERED_AT_THAT_ADDRESS.words)
    assert got["slots"]["address"] == STUB_ADDRESS


@pytest.mark.parametrize("path, body, stage", DOORS,
                         ids=[d[0] for d in DOORS])
def test_a_door_is_not_left_holding_only_the_stage_sentence(
        monkeypatch, path, body, stage):
    """The defect itself, pinned at each door.

    The stage sentence is what the reader got, and it is true of every
    way that step fails — which is why it distinguished nothing. Read out
    of ``failure.STAGE`` rather than quoted here, so it stays the same
    claim if the wording changes.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: _stub(
            _an_instance(anthropic.APIConnectionError)))

    got = client.post(path, json=body).json()
    assert got["words"] != dict(failure.STAGE[stage])


def test_a_refused_credential_reads_as_one_at_the_door(monkeypatch):
    """And is a different sentence from the one above, through the door.

    The two are distinguished inside ``_unreached``; this is that
    distinction still standing where somebody reads it.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: _stub(
            _an_instance(anthropic.AuthenticationError)))

    got = client.post("/api/ask", json={"nl": "x 导致 y 吗"}).json()
    assert got["words"] == dict(Bridge.THE_CREDENTIAL_WAS_REFUSED.words)
    assert got["words"] != dict(
        Bridge.NOTHING_ANSWERED_AT_THAT_ADDRESS.words)


def test_the_reader_is_told_this_in_their_own_language(monkeypatch):
    """One failure, two renderings, the same facts in both.

    The SDK's sentence is English and stays English — a network stack's
    wording is not this project's to translate — but which failure it was
    is this project's, and that is the half a reader acts on.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(
        llm_bridge, "_client",
        lambda api_key=None: _stub(
            _an_instance(anthropic.APIConnectionError)))

    got = client.post("/api/ask", json={"nl": "x 导致 y 吗"}).json()
    said = {lang: language.fill(got["words"], lang, **got["slots"])
            for lang in ("zh", "en")}
    assert said["zh"] != said["en"]
    assert all(STUB_ADDRESS in text for text in said.values())
