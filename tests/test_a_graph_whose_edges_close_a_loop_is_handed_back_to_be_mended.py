"""A graph whose edges close a loop is handed back to the model to mend.

#820. Of ten real questions asked of the live site, two came back with no
answer: the model had drawn both directions between the exposure and a
neighbour — watching television and time outdoors, coffee before an exam
and anxiety — and the kernel refuses a graph with a loop. That refusal
was not in the set the door hands back to the model with the program, so
each question was re-read three times from the question alone, into the
same loop each time, and the reader was told the kernel would not accept
the graph, with the cycle in English underneath.

A loop among the cause edges is a fact about the program as written, as
a declaration with a stray key is, and the language has two statements
for what the loop stood in for: a feedback declaration beside the edge
the question asks about, or edges between time slices. So the refusal
now carries its sentence, in the reader's language on the page and in
the prompt's language to the model, says what to write instead, and goes
back with the program for one thing to be mended. Where the model does
not mend it, the sentence reaches the reader naming the loop's variables
by the names the refused program declares: the failure carries that
program, since no result does.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import themis
from themis import language
from themis.runtime.graph_projection import Closed, CyclicGraphError
from themis.web import app as app_module
from themis.web import llm_bridge

from tests import web_source

client = TestClient(app_module.app)
QUESTION = "考试前喝咖啡能提高成绩吗"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _variable(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False],
            "name": {"zh": {"coffee": "考前喝咖啡", "anxiety": "焦虑",
                            "score": "成绩"}[p]}}


def _program(*edges):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _variable("coffee"), _variable("anxiety"), _variable("score"),
            *({"kind": "cause", "from": _atom(a), "to": _atom(b)} for a, b in edges),
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("coffee"), "to": _atom("score")}},
        ],
    }


LOOPED = _program(("coffee", "score"), ("anxiety", "coffee"), ("coffee", "anxiety"))
MENDED = _program(("coffee", "score"), ("anxiety", "coffee"))


def _refusal() -> CyclicGraphError:
    with pytest.raises(CyclicGraphError) as caught:
        themis.run(LOOPED)
    return caught.value


# --- what the refusal says -------------------------------------------------------------

def test_the_refusal_carries_its_sentence_and_names_the_loop():
    refused = _refusal()
    assert isinstance(refused, language.Voiced)
    assert refused.species is Closed.THE_EDGES_CLOSE_A_LOOP
    assert refused.details["count"] == 1
    assert "anxiety(me) -> coffee(me) -> anxiety(me)" in refused.details["cycles"] \
        or "coffee(me) -> anxiety(me) -> coffee(me)" in refused.details["cycles"]
    assert len(refused.cycles) == 1


@pytest.mark.parametrize("lang, offered", [("zh", "feedback"), ("en", "feedback")])
def test_it_says_what_the_language_offers_in_place_of_the_loop(lang, offered):
    refused = _refusal()
    said = language.assemble(refused.species.words, refused.said, refused.words,
                             lang=language.Lang(lang))
    assert offered in said
    assert "coffee(me)" in said


# --- the door ------------------------------------------------------------------------

def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


LISTING = llm_bridge._PROMPT_CONSIDER.read_text(encoding="utf-8")
LISTED = {"exposure": "考前喝咖啡", "outcome": "成绩", "common_causes": [],
          "other_causes_of_outcome": [], "mediators": []}


class _Model:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.sent: list[dict] = []
        self.base_url = "http://stub.invalid"
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        if kwargs["system"] == LISTING:
            return _message(json.dumps(LISTED, ensure_ascii=False))
        self.sent.append(kwargs)
        return _message(self.replies.pop(0) if len(self.replies) > 1
                        else self.replies[0])


def _refused_turn(sent):
    last = sent["messages"][-1]["content"]
    try:
        turn = json.loads(last)
    except ValueError:
        return None
    return turn.get("kernel_refused") if isinstance(turn, dict) else None


def test_a_looped_graph_goes_back_with_the_refusal_and_the_mended_one_answers(monkeypatch):
    stub = _Model(json.dumps(LOOPED), json.dumps(MENDED), "读回来的回答")
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
    r = client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})
    assert r.status_code == 200, r.text
    assert r.json()["kernel_ast"] == MENDED
    assert _refused_turn(stub.sent[0]) is None
    handed = _refused_turn(stub.sent[1])
    assert handed is not None and "feedback" in handed and "coffee(me)" in handed
    assert json.loads(stub.sent[1]["messages"][-2]["content"]) == LOOPED


def test_a_loop_the_model_will_not_mend_reaches_the_reader_in_their_words(monkeypatch):
    stub = _Model(json.dumps(LOOPED))
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
    r = client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["stage"] == "themis_run"
    assert body["words"]["zh"].startswith("图里的因果边连成了")
    assert "feedback" in body["words"]["zh"]
    # The cycle travels as identifiers; the page says them by the names the
    # refused program declares, which is why that program rides along.
    assert "coffee(me)" in body["slots"]["cycles"]
    assert body["kernel_ast"] == LOOPED


def test_the_page_says_a_refused_program_s_variables_by_its_own_names():
    """No result holds a refused program, so nothing on the page has said
    whose names are in force; the failure carries the program, and the
    sentence's slots are said by the names it declares."""
    source = web_source.read(web_source.SRC / "api.ts")
    assert "program: data.kernel_ast ?? undefined" in source
    assert "namesOf(err?.program, lang)" in source
    assert "named(v, names)" in source
