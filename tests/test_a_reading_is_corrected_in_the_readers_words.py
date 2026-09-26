"""A reading is corrected in the reader's own words.

The page says what a sentence was read as (#780). A reader who sees that it
is not what they meant needs a way to say so that is not "draw the graph
again" or "ask again and hope": asked again, the model reads the whole
sentence afresh and can change what the reader had already accepted. So
the reader writes one sentence, and the model is handed the question, the
program on the screen and that sentence, as one exchange, and returns the
program changed where the sentence reaches. The kernel runs it like any
other; the page shows what changed and can step back (#781).
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from themis.web import app as app_module
from themis.web import llm_bridge
from themis.web.bridge_words import Bridge

from . import web_source

client = TestClient(app_module.app)
PROMPT = (pathlib.Path(llm_bridge.__file__).resolve().parent.parent
          / "prompts" / "nl_to_kernel_ast.md")
SECTION = "When the reader corrects a reading"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*confounders):
    names = ["smoking", "lung_cancer", *confounders]
    edges = [("smoking", "lung_cancer"),
             *((c, t) for c in confounders for t in ("smoking", "lung_cancer"))]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": n, "domain": [True, False]}
              for n in names),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)}
              for a, b in edges),
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": _atom("smoking"),
                       "to": _atom("lung_cancer")}},
        ],
    }


ON_SCREEN = _program("genetic_predisposition")
REVISED = _program()


def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _Model:
    """Answers each call with the next reply, the last one for as long as it
    is asked, and keeps what it was sent."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent: list[dict] = []
        self.base_url = "http://stub.invalid"
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.sent.append(kwargs)
        return _message(self.replies.pop(0) if len(self.replies) > 1
                        else self.replies[0])


@pytest.fixture
def model(monkeypatch):
    def install(*replies):
        stub = _Model(*replies)
        monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
        return stub
    return install


# --- what the model is handed ------------------------------------------------------

def test_the_model_is_handed_the_question_the_program_and_the_correction(model):
    stub = model(json.dumps(REVISED))
    got = llm_bridge.revise_kernel_ast("吸烟会导致肺癌吗", ON_SCREEN,
                                       "别加遗传这个因素")
    assert got == REVISED
    sent = stub.sent[0]
    assert sent["system"] == PROMPT.read_text(encoding="utf-8")
    turns = sent["messages"][-3:]
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[0]["content"] == "吸烟会导致肺癌吗"
    assert json.loads(turns[1]["content"]) == ON_SCREEN
    assert turns[2]["content"] == "别加遗传这个因素"


def test_what_a_reply_after_a_program_means_is_the_prompt_s_to_say():
    """The correction goes to the model as the reader wrote it, the way the
    question does, so the account of what a turn after a program is, and
    what to do with it, has to be in the document it is sent with."""
    assert f"## {SECTION}" in PROMPT.read_text(encoding="utf-8")


def test_a_correction_the_model_declines_is_not_retried(model):
    stub = model(json.dumps({"error": "the correction contradicts itself"}))
    with pytest.raises(llm_bridge.LLMBridgeError) as caught:
        llm_bridge.revise_kernel_ast("q", ON_SCREEN, "x and not x")
    assert caught.value.species is Bridge.THE_MODEL_DECLINED_THE_QUESTION
    assert len(stub.sent) == 1


# --- the door ----------------------------------------------------------------------

def _post(**overrides):
    body = {"nl": "吸烟会导致肺癌吗", "program": ON_SCREEN,
            "correction": "别加遗传这个因素", "lang": "zh", **overrides}
    return client.post("/api/revise", json=body)


def test_the_revised_program_is_run_and_written_up(model):
    model(json.dumps(REVISED), "读回来的回答")
    r = _post()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["correction"] == "别加遗传这个因素"
    assert body["kernel_ast"] == REVISED
    assert body["envelope"]["results"]
    assert body["reply"] == "读回来的回答"


def test_a_revision_that_is_not_a_program_is_filed_under_its_own_stage(model):
    model("not json")
    body = _post().json()
    assert body["stage"] == "revise_kernel_ast"


def test_a_revision_the_kernel_refuses_is_the_kernels(model):
    broken = {"version": "0.1"}
    model(json.dumps(broken))
    body = _post().json()
    assert body["stage"] == "themis_run"
    assert body["kernel_ast"] == broken


def test_no_model_no_revision(monkeypatch):
    monkeypatch.setattr(app_module, "_OFFERS_A_MODEL", False)
    body = _post().json()
    assert body["stage"] == "no_model"


# --- the page ----------------------------------------------------------------------

def test_the_page_offers_it_where_a_sentence_was_read_and_a_model_is_behind_it():
    """A program drawn by hand or built from a scenario has no sentence to
    have been read wrongly, so the workspace that asks in a sentence is the
    one that hands the result view a way to correct it."""
    ask = web_source.read(web_source.SRC / "components" / "AskWorkspace.tsx")
    assert "onRevise={offers?.llm ? correct : undefined}" in ask
    assert "revise(payload.asked, program, said" in ask
    view = web_source.read(web_source.SRC / "components" / "ResultView.tsx")
    assert "<Correction " in view
    handing = sorted(p.name for p in web_source.SRC.rglob("*.tsx")
                     if "onRevise={" in web_source.read(p))
    assert handing == ["AskWorkspace.tsx", "ResultView.tsx"]


def test_what_changed_is_read_off_the_two_programs():
    """Not taken from the model's word, and not from the screen either: the
    graph can be edited after a correction, and those edits are not what
    the correction changed."""
    said = web_source.read(web_source.SRC / "components" / "Correction.tsx")
    assert "changeBetween(revision.before, revision.after)" in said
    ask = web_source.read(web_source.SRC / "components" / "AskWorkspace.tsx")
    assert "revision: { said, before: program, after: res.kernel_ast }" in ask
