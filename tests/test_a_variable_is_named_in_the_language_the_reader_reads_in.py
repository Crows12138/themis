"""A variable is named in the language the reader reads in, or the program
goes back to be mended.

#821. The page says a variable by the name its declaration gives in the
reader's language, and a declaration without one is shown as its
identifier. Of twelve real questions asked of the live site in Chinese,
two came back with every name keyed by ``en``: the prompt asked for the
key of "the language their question is written in", and a model left to
infer the key read the prompt's own skeleton, which is in English, and
keyed by that.

The reader's language is a fact the door holds and had not told the
model, and nothing held the program to it — the kernel cannot, since it
does not know who is reading. So the question is sent with ``language``
beside it, the prompt says every name is keyed by that, and the door asks
each program for a name in it before running it; one short of a name goes
back to the model with the refusal and the program, as a loop or a stray
key does, and the model mends the declaration.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from themis import language
from themis.web import app as app_module
from themis.web import llm_bridge
from themis.web.bridge_words import Bridge
from themis.web.llm_bridge import UnreadableProgram, names_for_the_reader

client = TestClient(app_module.app)
QUESTION = "吸烟会导致肺癌吗"
PROMPT = llm_bridge._REPO_ROOT / "themis" / "prompts" / "nl_to_kernel_ast.md"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _variable(p, name=None):
    out = {"kind": "variable", "predicate": p, "domain": [True, False]}
    if name is not None:
        out["name"] = name
    return out


def _program(*variables):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *variables,
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")},
            {"kind": "query", "id": "q", "query": {
                "kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")}},
        ],
    }


NAMED = _program(_variable("smoking", {"zh": "吸烟"}),
                 _variable("lung_cancer", {"zh": "肺癌"}))
#: The shape measured on the live site: every name keyed by ``en`` for a
#: question asked in Chinese.
IN_ENGLISH = _program(_variable("smoking", {"en": "smoking"}),
                      _variable("lung_cancer", {"en": "lung cancer"}))
#: One declaration with no name at all, one with an empty one.
UNNAMED = _program(_variable("smoking"),
                   _variable("lung_cancer", {"zh": "  "}))


# --- the check ----------------------------------------------------------------------

def test_a_program_named_in_the_readers_language_passes():
    names_for_the_reader(NAMED, "zh")
    names_for_the_reader(NAMED, language.Lang.ZH)


@pytest.mark.parametrize("program, short", [
    (IN_ENGLISH, ["smoking", "lung_cancer"]),
    (UNNAMED, ["smoking", "lung_cancer"]),
    (_program(_variable("smoking", {"zh": "吸烟", "en": "smoking"}),
              _variable("lung_cancer", {"en": "lung cancer"})), ["lung_cancer"]),
])
def test_a_program_short_of_a_name_is_refused_naming_the_variables(program, short):
    with pytest.raises(UnreadableProgram) as caught:
        names_for_the_reader(program, "zh")
    refused = caught.value
    assert refused.species is Bridge.A_VARIABLE_HAS_NO_NAME_IN_THE_READERS_LANGUAGE
    assert refused.details["variables"] == short
    assert refused.details["language"] == "zh"
    assert "zh" in str(refused)


def test_the_same_program_reads_in_the_language_it_is_named_in():
    names_for_the_reader(IN_ENGLISH, "en")
    with pytest.raises(UnreadableProgram):
        names_for_the_reader(NAMED, "en")


def test_what_is_not_a_declaration_in_form_is_left_to_the_kernel():
    """A statement with no predicate, or no kind, is the kernel's to refuse;
    this check says nothing about it."""
    odd = _program(_variable("smoking", {"zh": "吸烟"}),
                   _variable("lung_cancer", {"zh": "肺癌"}))
    odd["statements"].insert(0, {"kind": "variable", "domain": [True, False]})
    odd["statements"].insert(0, {"predicate": "ghost"})
    names_for_the_reader(odd, "zh")


# --- the turn -----------------------------------------------------------------------

def test_the_question_is_sent_with_the_readers_language_beside_it():
    turn = json.loads(llm_bridge._question(QUESTION, None, "zh"))
    assert turn == {"question": QUESTION, "language": "zh"}
    turn = json.loads(llm_bridge._question(QUESTION, {"exposure": "吸烟"}, language.Lang.EN))
    assert turn == {"question": QUESTION, "language": "en",
                    "variables_to_consider": {"exposure": "吸烟"}}
    assert llm_bridge._question(QUESTION, None) == QUESTION


def test_the_prompt_keys_a_name_by_the_language_the_question_arrives_with():
    text = PROMPT.read_text(encoding="utf-8")
    assert "the `language` the question arrives with" in text
    assert "`language` is the tag of the\nlanguage they read in" in text
    assert "which is the skeleton's\n  only because its question is in English" in text


# --- the door -----------------------------------------------------------------------

LISTING = llm_bridge._PROMPT_CONSIDER.read_text(encoding="utf-8")
LISTED = {"exposure": "吸烟", "outcome": "肺癌", "common_causes": [],
          "other_causes_of_outcome": [], "mediators": []}


def _message(text):
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


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


@pytest.fixture
def model(monkeypatch):
    def install(*replies):
        stub = _Model(*replies)
        monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: stub)
        return stub
    return install


def _refused_turn(sent):
    last = sent["messages"][-1]["content"]
    try:
        turn = json.loads(last)
    except ValueError:
        return None
    return turn.get("kernel_refused") if isinstance(turn, dict) else None


def test_a_program_named_in_english_for_a_chinese_reader_goes_back_and_the_mended_one_answers(model):
    stub = model(json.dumps(IN_ENGLISH), json.dumps(NAMED), "读回来的回答")
    r = client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})
    assert r.status_code == 200, r.text
    assert r.json()["kernel_ast"] == NAMED
    assert json.loads(stub.sent[0]["messages"][0]["content"])["language"] == "zh"
    assert _refused_turn(stub.sent[0]) is None
    handed = _refused_turn(stub.sent[1])
    assert handed is not None and "`zh`" in handed and "smoking" in handed
    assert json.loads(stub.sent[1]["messages"][-2]["content"]) == IN_ENGLISH
    assert json.loads(stub.sent[1]["messages"][0]["content"])["language"] == "zh"


def test_the_same_program_answers_a_reader_of_its_language(model):
    stub = model(json.dumps(IN_ENGLISH), "the reply")
    r = client.post("/api/ask", json={"nl": QUESTION, "lang": "en"})
    assert r.status_code == 200, r.text
    assert len(stub.sent) == 2  # the program, then the reply
    assert json.loads(stub.sent[0]["messages"][0]["content"])["language"] == "en"


def test_a_program_the_model_will_not_name_reaches_the_reader_in_their_words(model):
    model(json.dumps(IN_ENGLISH))
    r = client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})
    assert r.status_code == 400, r.text
    body = r.json()
    assert body["error"] == "UnreadableProgram"
    assert body["words"] == dict(Bridge.A_VARIABLE_HAS_NO_NAME_IN_THE_READERS_LANGUAGE.words)
    assert body["slots"] == {"variables": ["smoking", "lung_cancer"], "language": "zh"}
    assert body["kernel_ast"] == IN_ENGLISH


def test_a_revision_is_held_to_it_too(model):
    stub = model(json.dumps(IN_ENGLISH), json.dumps(NAMED), "读回来的回答")
    r = client.post("/api/revise", json={
        "nl": QUESTION, "program": NAMED, "correction": "别加别的变量", "lang": "zh"})
    assert r.status_code == 200, r.text
    assert r.json()["kernel_ast"] == NAMED
    assert "`zh`" in _refused_turn(stub.sent[1])


def test_the_door_s_refusal_is_handed_back_beside_the_kernel_s():
    assert UnreadableProgram in app_module._THE_PROGRAM_AS_WRITTEN
    assert issubclass(UnreadableProgram, llm_bridge.LLMBridgeError)
