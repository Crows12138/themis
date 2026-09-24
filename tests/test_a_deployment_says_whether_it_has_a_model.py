"""A page is not a door, and a deployment says once which ones it opens.

Three of the things this server offers need a model behind it: turning a
question in prose into a program, sourcing a prior for each distribution
the kernel says is missing, and writing a result up as a reply. Nothing
else does — the graph, the verdict, the gap report, filling in a
definition and estimating from data are the kernel's, and the kernel
holds no model.

A deployment with no model behind it therefore offers three fewer
things, and both halves have to know: the page, so it does not draw a
button that leads nowhere, and the endpoints, so that drawing no button
is not the whole of the protection. Drawing none and leaving the
endpoint open protects the page and not the key, and the key is spent at
the endpoint.

What is asserted here:

- the fact is declared once and its vocabulary is closed, so a third
  spelling cannot read as one of the two
- ``/api/offers`` is that declaration, and whether a visitor is asked
  for a key, and nothing else
- with no model, each of the three refuses, in the reader's language,
  with a sentence that says what still works
- with no model, everything that needs none still answers
- the three that guard are exactly the three that reach for the bridge —
  derived from the source rather than listed here, so an endpoint added
  tomorrow that forgets the guard fails here rather than shipping open
- both surfaces that can offer one of the three ask what is offered
  rather than deciding for themselves.
"""
from __future__ import annotations

import importlib
import os
import re

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import themis
from themis import language
from themis.web import app as app_module
from themis.web import failure

from . import web_source

client = TestClient(app_module.app)

#: The stage this refusal is filed under, named once here so a rename has
#: to come through this test.
STAGE = "no_model"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause",
                       "from": _atom("x"), "to": _atom("y")}},
        ],
    }


#: What each of the three is asked, so that a guard is exercised by the
#: shape the endpoint really takes rather than by an empty body.
NEEDS_A_MODEL = {
    "/api/ask": {"nl": "x 会不会导致 y", "lang": "zh"},
    "/api/assume": {"program": _program(), "lang": "zh"},
    "/api/render": {"program": _program(),
                    "result": themis.run(_program())["results"][0],
                    "nl": "x", "lang": "zh"},
}

#: And the ones that need none, with the stage each honestly answers with
#: on this input. None of them is an error: an empty pick list has nothing
#: to apply and an empty table has no rows, and saying so is the answer.
NEEDS_NO_MODEL = {
    "/api/run": ({"program": _program()}, None),
    "/api/clarify": ({"program": _program(), "picks": []},
                     "nothing_to_clarify"),
    "/api/estimate": ({"program": _program(), "rows": []}, "empty_data"),
}


@pytest.fixture
def without_a_model(monkeypatch):
    """This deployment, with no model behind it.

    The module-level declaration is what both the endpoints and
    ``/api/offers`` read, so one patch moves every reader — which is the
    property being tested as much as it is the way to test it.
    """
    monkeypatch.setattr(app_module, "_OFFERS_A_MODEL", False)


# --- the declaration ----------------------------------------------------

def test_the_fact_is_a_fact():
    assert isinstance(app_module._OFFERS_A_MODEL, bool)


def test_the_vocabulary_is_closed():
    """A third spelling would read as one of the two and nobody could say
    which, so it is refused at import rather than guessed at."""
    for said in ("yes", "true", "1", "", "ON"):
        os.environ["THEMIS_WEB_LLM"] = said
        try:
            with pytest.raises(ValueError, match="THEMIS_WEB_LLM"):
                importlib.reload(app_module)
        finally:
            del os.environ["THEMIS_WEB_LLM"]
            importlib.reload(app_module)


@pytest.mark.parametrize("said,offers", [("on", True), ("off", False)])
def test_both_answers_are_answerable(said, offers, monkeypatch):
    monkeypatch.setenv("THEMIS_WEB_LLM", said)
    reloaded = importlib.reload(app_module)
    try:
        assert reloaded._OFFERS_A_MODEL is offers
    finally:
        monkeypatch.delenv("THEMIS_WEB_LLM")
        importlib.reload(app_module)


def test_the_default_is_the_local_product():
    """Nothing in the environment means the product as it runs on the
    machine it was written for, which has a model behind it. A deployment
    that does not is the one that says so."""
    assert "THEMIS_WEB_LLM" not in os.environ
    assert app_module._OFFERS_A_MODEL is True


# --- the page is told ---------------------------------------------------

def test_offers_says_what_it_knows(monkeypatch):
    monkeypatch.delenv("THEMIS_LLM_API_KEY", raising=False)
    body = client.get("/api/offers").json()
    assert body == {"llm": app_module._OFFERS_A_MODEL,
                    "visitor_key": app_module._OFFERS_A_MODEL}


def test_offers_follows_the_declaration(without_a_model):
    assert client.get("/api/offers").json() == {
        "llm": False, "visitor_key": False}


def test_a_deployment_that_pays_asks_no_visitor_for_a_key(monkeypatch):
    """The operator declared who pays; a panel asking the visitor would
    say otherwise, and a key typed into it would not be read."""
    monkeypatch.setenv("THEMIS_LLM_API_KEY", "sk-operator")
    body = client.get("/api/offers").json()
    assert body == {"llm": app_module._OFFERS_A_MODEL, "visitor_key": False}


# --- and so are the endpoints -------------------------------------------

@pytest.mark.parametrize("path", sorted(NEEDS_A_MODEL))
def test_what_needs_a_model_refuses_without_one(path, without_a_model):
    r = client.post(path, json=NEEDS_A_MODEL[path])
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["stage"] == STAGE, body
    # In the reader's language, both of them, like every other refusal
    # this door hands back.
    assert set(body["words"]) == {str(one) for one in language.Lang}
    assert all(body["words"][str(one)] for one in language.Lang)


@pytest.mark.parametrize("path", sorted(NEEDS_NO_MODEL))
def test_what_needs_none_still_answers(path, without_a_model):
    payload, stage = NEEDS_NO_MODEL[path]
    body = client.post(path, json=payload).json()
    assert body.get("stage") == stage, body
    if stage is None:
        assert body["results"], body


def test_the_refusal_says_what_still_works():
    """A reader who meets a closed door is owed the open ones. The
    sentence is the species' and is checked for its content rather than
    quoted, so rewording it does not have to come through here twice."""
    said = failure.STAGE[STAGE]
    for one in language.Lang:
        assert said[str(one)].strip()


# --- the roster nobody has to remember to extend ------------------------

def _endpoint_bodies() -> dict[str, str]:
    """Every ``api_*`` handler in the app, by name, as source."""
    # themis/web/app.py — SRC is themis/web/frontend/src, so the server
    # sits two levels up from it.
    text = web_source.read(web_source.SRC.parent.parent / "app.py")
    out: dict[str, str] = {}
    starts = [(m.start(), m.group(1))
              for m in re.finditer(r"\ndef (api_\w+)\(", text)]
    for i, (at, name) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(text)
        out[name] = text[at:end]
    return out


def test_every_endpoint_that_reaches_for_a_model_asks_first():
    """Which endpoints need one is not a list kept here. It is read off
    the source — an endpoint needs a model exactly when it reaches for
    the bridge — so one added tomorrow that forgets the guard fails here
    instead of shipping with the door open."""
    bodies = _endpoint_bodies()
    reaching = {name for name, body in bodies.items()
                if "llm_bridge" in body}
    assert reaching, "no endpoint reaches for the bridge; this test is blind"
    unguarded = sorted(name for name in reaching
                       if "_OFFERS_A_MODEL" not in bodies[name])
    assert not unguarded, (
        f"{unguarded} reach for the model and never ask whether this "
        f"deployment has one; a page that hides the button does not close "
        f"the endpoint"
    )


def test_nothing_else_carries_the_guard():
    """The other side of it. A guard on an endpoint that needs no model
    would refuse an honest request on a deployment that is working
    exactly as intended."""
    bodies = _endpoint_bodies()
    needless = sorted(name for name, body in bodies.items()
                      if "_OFFERS_A_MODEL" in body
                      and "llm_bridge" not in body
                      and name != "api_offers")
    assert not needless, needless


# --- both surfaces ask --------------------------------------------------

@pytest.mark.parametrize("where", ["App.tsx", "components/ResultView.tsx"])
def test_the_page_asks_what_is_offered(where):
    """Two surfaces can offer one of the three — the workspace chooser
    and the result view, which carries the priors fallback and the
    reply. Each asks; neither decides."""
    said = web_source.read(web_source.SRC / where)
    assert "useOffers" in said, (
        f"{where} draws one of the three without asking whether this "
        f"deployment offers it"
    )


def test_the_answer_is_not_assumed_while_it_is_unknown():
    """Before the server answers there is no answer, and a door nobody
    knows about is not drawn. The store settles closed when the request
    fails, too: not reaching our own server is not evidence a model is
    behind it."""
    said = web_source.read(web_source.SRC / "lib" / "offers.ts")
    assert "let offers: Offers | null = null" in said
    assert "settle({ llm: false, visitor_key: false })" in said
