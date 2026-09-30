"""A question's variables are listed before its graph is drawn.

The translation drew a question known for one answer — a correlation
explained by one hidden common cause — with that cause and nothing else.
Measured on the demo's model, nine translations of three such questions
drew three variables each, and three rewordings of the prompt and a
thinking budget left them there: the model, having recalled the textbook
answer, took it for the whole graph. A call asked only to list the domain's
variables named nine to fourteen. A common cause left out of a graph biases
the answer, and nothing after the translation can see what is missing.

So the door asks first, under ``prompts/variables_to_consider.md``, for the
exposure, the outcome, what the domain's evidence holds about the exposure's
effect one direction at a time, their common causes, the outcome's other
causes and the mediators the domain's evidence holds, and hands the translation the
question with that list beside it, as one object whose form the prompt
explains. Every program written for the question is written from that turn,
a repair included. A revision is not listed again: the program on the
reader's screen already carries what was listed. A list that cannot be drawn
up refuses the question, rather than translating without one and showing
the thin graph as if nothing had been skipped.
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

client = TestClient(app_module.app)
PROMPTS = pathlib.Path(llm_bridge.__file__).resolve().parent.parent / "prompts"
LISTING = (PROMPTS / "variables_to_consider.md").read_text(encoding="utf-8")
WRITING = (PROMPTS / "nl_to_kernel_ast.md").read_text(encoding="utf-8")
SECTION = "When the question comes with variables to consider"
QUESTION = "吃冰激凌会导致溺水吗"
LISTED = {
    "exposure": "吃冰激凌", "outcome": "溺水",
    "effect_of_exposure": {"raises": "no", "lowers": "no",
                           "evidence": "二者的相关由气温解释，没有证据表明吃冰激凌本身改变溺水风险"},
    "common_causes": [{"name": "气温", "why": "天热时吃冰激凌和游泳的人都多"}],
    "other_causes_of_outcome": [{"name": "游泳技能", "why": "不会游泳的人更容易溺水"}],
    "mediators": [],
}
ASKED = {"question": QUESTION, "variables_to_consider": LISTED}


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*variables):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *variables,
            {"kind": "cause", "from": _atom("ice_cream"), "to": _atom("drowning"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("ice_cream"),
                "to": _atom("drowning")}},
        ],
    }


def _variable(p, **extra):
    return {"kind": "variable", "predicate": p, "domain": [True, False], **extra}


GOOD = _program(_variable("ice_cream"), _variable("drowning"))
#: A declaration carrying an edge's annotations, which the schema refuses.
SLIPPED = _program(_variable("ice_cream", annotations={"source": "llm_proposal"}),
                   _variable("drowning"))


def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class _Model:
    """Answers the listing call from ``listing`` and every other call from
    ``replies``, each the next reply and the last one for as long as it is
    asked, and keeps every call in the order it was made."""

    def __init__(self, *replies, listing=(json.dumps(LISTED, ensure_ascii=False),)):
        self.replies = list(replies)
        self.listing = list(listing)
        self.calls: list[dict] = []
        self.base_url = "http://stub.invalid"
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append(kwargs)
        queue = self.listing if kwargs["system"] == LISTING else self.replies
        return _message(queue.pop(0) if len(queue) > 1 else queue[0])

    def under(self, system: str) -> list[dict]:
        return [c for c in self.calls if c["system"] == system]


@pytest.fixture
def model(monkeypatch):
    def install(*replies, **listing):
        stub = _Model(*replies, **listing)
        monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
        return stub
    return install


def _ask():
    return client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})


def _first_turn(call) -> object:
    content = call["messages"][0]["content"]
    try:
        return json.loads(content)
    except ValueError:
        return content


# --- the door ----------------------------------------------------------------

def test_the_variables_are_listed_first_from_the_question_alone(model):
    stub = model(json.dumps(GOOD), "回答")
    assert _ask().status_code == 200
    assert stub.calls[0]["system"] == LISTING
    assert stub.calls[0]["messages"] == [{"role": "user", "content": QUESTION}]
    assert len(stub.under(LISTING)) == 1


def test_the_program_is_written_from_the_question_with_the_list_beside_it(model):
    stub = model(json.dumps(GOOD), "回答")
    assert _ask().json()["kernel_ast"] == GOOD
    [written] = stub.under(WRITING)
    assert [t["role"] for t in written["messages"]] == ["user"]
    assert _first_turn(written) == ASKED


def test_a_repair_opens_with_the_turn_the_program_was_written_from(model):
    """And the list is not drawn up again for it: the repair mends the
    reading made from that list."""
    stub = model(json.dumps(SLIPPED), json.dumps(GOOD), "回答")
    assert _ask().status_code == 200
    first, repair = stub.under(WRITING)
    assert _first_turn(first) == _first_turn(repair) == ASKED
    assert json.loads(repair["messages"][1]["content"]) == SLIPPED
    assert "kernel_refused" in json.loads(repair["messages"][2]["content"])
    assert len(stub.under(LISTING)) == 1


def test_a_revision_is_not_listed_again(model):
    """The program on the reader's screen is what the revision changes, and
    it already carries what was listed."""
    stub = model(json.dumps(GOOD), "回答")
    r = client.post("/api/revise", json={
        "nl": QUESTION, "program": GOOD, "correction": "别加别的变量"})
    assert r.status_code == 200, r.text
    assert stub.under(LISTING) == []
    assert _first_turn(stub.under(WRITING)[0]) == QUESTION


def test_a_list_that_cannot_be_drawn_up_refuses_the_question(model):
    """Before a program is asked for, and at a stage of its own."""
    stub = model(json.dumps(GOOD), "回答", listing=("no json",))
    r = _ask()
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "variables_to_consider"
    assert body["words"] == dict(Bridge.THE_REPLY_CARRIES_NO_JSON.words)
    assert len(stub.under(LISTING)) == 3
    assert stub.under(WRITING) == []


def test_a_list_that_parses_on_a_later_attempt_is_the_one_used(model):
    stub = model(json.dumps(GOOD), "回答",
                 listing=("no json", json.dumps(LISTED, ensure_ascii=False)))
    assert _ask().status_code == 200
    assert len(stub.under(LISTING)) == 2
    assert _first_turn(stub.under(WRITING)[0]) == ASKED


# --- the library -------------------------------------------------------------

def test_the_library_s_ask_lists_before_it_draws(model):
    stub = model(json.dumps(GOOD), "回答")
    assert llm_bridge.ask(QUESTION)["kernel_ast"] == GOOD
    assert stub.calls[0]["system"] == LISTING
    assert _first_turn(stub.under(WRITING)[0]) == ASKED


def test_a_program_asked_for_without_a_list_is_asked_from_the_question():
    """The object form is the bridge's only when it has a list to carry."""
    assert llm_bridge._question(QUESTION, None) == QUESTION


# --- the prompts -------------------------------------------------------------

def test_the_prompt_says_what_a_turn_of_that_form_is():
    """The turn is sent as data, and what it means is the prompt's to say:
    every key the bridge writes into it is named in the section that
    explains it."""
    body = WRITING.split(f"## {SECTION}", 1)[1].split("\n## ", 1)[0]
    for key in json.loads(llm_bridge._question(QUESTION, LISTED)):
        assert f"`{key}`" in body, key


def test_the_listing_prompt_asks_for_an_object():
    """What the bridge reads out of the listing is one JSON object, and the
    prompt asks for one with the roles the section above names."""
    for key in LISTED:
        assert f"`{key}`" in LISTING, key


def test_the_list_s_judgement_of_the_effect_is_read_where_the_list_is():
    """The listing judges the exposure's effect one direction at a time, on
    the evidence about the effect rather than the association the question
    reports; the translation, judging it from the question, left out effects
    that run against what the question suspects. So X's own link is drawn
    by the listing's judgement, and the section that explains the list
    names the key the judgement arrives under, and each of its answers."""
    body = WRITING.split(f"## {SECTION}", 1)[1].split("\n## ", 1)[0]
    assert "`effect_of_exposure`" in body
    for key in LISTED["effect_of_exposure"]:
        assert f"`{key}`" in LISTING, key
    for answer in ("yes", "no", "unsettled"):
        assert f"`{answer}`" in LISTING and f"`{answer}`" in body, answer
