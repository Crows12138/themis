"""A program the kernel refuses is handed back with the refusal.

The model writes a program from a question, and now and then writes it
with a slip in its form: a variable declaration carrying a key only an
edge takes, a field set to null that the schema wants a string for. The
kernel refuses it as written, and the door used to answer by asking the
model again from the question alone — three fresh readings, each free to
slip somewhere else, and none of them the reading that had been refused.
Measured on the demo's model, about one program in six was refused this
way, and a refused program is a question the reader got no answer to.

Two things were missing. The refusal said which statement and not what was
wrong with it — "… is not valid under any of the given schemas" — because
a statement that fits none of a ``oneOf``'s shapes fails once per shape.
And the refusal was never shown to the model. So:

- a statement's refusal is read off the shape its ``kind`` names, and says
  what is wrong there; with no single shape named it is left as it came;
- a program the kernel refuses as written goes back to the model with the
  question and the refusal, as the next turn of the same exchange, and a
  repair the kernel refuses goes back with its own refusal;
- a failure to write a program at all is still met by writing again, and a
  failure that is not about the program as written is not handed back;
- the refusal is sent in the kernel's own words, in the language the
  prompt is written in, and the prompt says what a turn of that form is.
"""
from __future__ import annotations

import json
import pathlib
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import themis
from themis import language
from themis.input.semantic_validator import SemanticError
from themis.input.syntactic_validator import SyntacticError
from themis.web import app as app_module
from themis.web import llm_bridge

client = TestClient(app_module.app)
PROMPT = (pathlib.Path(llm_bridge.__file__).resolve().parent.parent
          / "prompts" / "nl_to_kernel_ast.md")
QUESTION = "吸烟会导致肺癌吗"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _variable(p, **extra):
    return {"kind": "variable", "predicate": p, "domain": [True, False], **extra}


def _program(*variables, query=None):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *variables,
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")},
            {"kind": "query", "id": "q", "query": query or {
                "kind": "cause", "from": _atom("smoking"),
                "to": _atom("lung_cancer")}},
        ],
    }


GOOD = _program(_variable("smoking"), _variable("lung_cancer"))
#: The slip measured most often: a declaration carrying an edge's annotations.
SLIPPED = _program(_variable("smoking", annotations={"source": "llm_proposal"}),
                   _variable("lung_cancer"))
#: Well formed, and refused by a rule of the language rather than the schema.
TWICE = _program(_variable("smoking"), _variable("smoking"), _variable("lung_cancer"))


def _refusal(program) -> Exception:
    with pytest.raises((SyntacticError, SemanticError)) as caught:
        themis.run(program)
    return caught.value


# --- what a refusal says ---------------------------------------------------------------

def test_a_statement_s_refusal_says_what_is_wrong_with_it():
    said = str(_refusal(SLIPPED))
    assert "statements/0: Additional properties are not allowed ('annotations' was unexpected)" in said
    assert "is not valid under any of the given schemas" not in said


def test_a_query_inside_a_statement_is_read_off_its_own_kind():
    stray = {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer"),
             "given": []}
    said = str(_refusal(_program(_variable("smoking"), _variable("lung_cancer"),
                                 query=stray)))
    assert "statements/3/query: Additional properties are not allowed ('given' was unexpected)" in said


def test_a_statement_that_names_no_shape_is_not_guessed_at():
    nameless = _program(_variable("smoking"), _variable("lung_cancer"))
    nameless["statements"][0] = {"predicate": "smoking", "domain": [True, False]}
    said = str(_refusal(nameless))
    assert "statements/0: " in said
    assert "is not valid under any of the given schemas" in said


# --- what the model is handed ----------------------------------------------------------

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


def _refused_turn(sent) -> str | None:
    """What the kernel refused, where a call carries a turn saying so."""
    last = sent["messages"][-1]["content"]
    try:
        turn = json.loads(last)
    except ValueError:
        return None
    return turn.get("kernel_refused") if isinstance(turn, dict) else None


def test_the_model_is_handed_the_question_the_program_and_the_refusal(model):
    stub = model(json.dumps(GOOD))
    refusal = _refusal(SLIPPED)
    assert llm_bridge.repair_kernel_ast(QUESTION, SLIPPED, refusal) == GOOD
    sent = stub.sent[0]
    assert sent["system"] == PROMPT.read_text(encoding="utf-8")
    turns = sent["messages"][-3:]
    assert [t["role"] for t in turns] == ["user", "assistant", "user"]
    assert turns[0]["content"] == QUESTION
    assert json.loads(turns[1]["content"]) == SLIPPED
    assert json.loads(turns[2]["content"]) == {"kernel_refused": str(refusal)}


def test_a_refusal_that_carries_its_own_sentence_is_sent_in_the_prompt_s_language(model):
    stub = model(json.dumps(GOOD))
    refusal = _refusal(TWICE)
    assert isinstance(refusal, SemanticError)
    llm_bridge.repair_kernel_ast(QUESTION, TWICE, refusal)
    english = language.assemble(refusal.species.words, refusal.said,
                                refusal.words, lang=language.Lang.EN)
    assert _refused_turn(stub.sent[0]) == english != str(refusal)


def test_the_prompt_says_what_a_turn_of_that_form_is():
    text = PROMPT.read_text(encoding="utf-8")
    assert "## When a program is followed by another turn" in text
    assert "`kernel_refused`" in text


# --- the door --------------------------------------------------------------------------

def _ask():
    return client.post("/api/ask", json={"nl": QUESTION, "lang": "zh"})


def test_a_refused_program_is_mended_and_the_mended_one_answers(model):
    stub = model(json.dumps(SLIPPED), json.dumps(GOOD), "读回来的回答")
    r = _ask()
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["kernel_ast"] == GOOD
    assert body["reply"] == "读回来的回答"
    assert _refused_turn(stub.sent[0]) is None
    assert "'annotations' was unexpected" in _refused_turn(stub.sent[1])
    assert json.loads(stub.sent[1]["messages"][-2]["content"]) == SLIPPED


def test_a_repair_the_kernel_refuses_goes_back_with_its_own_refusal(model):
    stub = model(json.dumps(SLIPPED), json.dumps(TWICE), json.dumps(GOOD), "回答")
    assert _ask().status_code == 200
    assert json.loads(stub.sent[2]["messages"][-2]["content"]) == TWICE
    assert _refused_turn(stub.sent[2]) == language.assemble(
        _refusal(TWICE).species.words, _refusal(TWICE).said,
        _refusal(TWICE).words, lang=language.Lang.EN)


def test_a_program_never_written_is_written_again_from_the_question(model):
    """A reply with no JSON in it is the bridge's to retry, three times, and
    then the door's to ask again — from the question, since there is no
    program to hand back."""
    stub = model("no json", "no json", "no json", json.dumps(GOOD), "回答")
    assert _ask().status_code == 200
    assert stub.sent[3]["messages"][-1]["content"] == QUESTION
    assert all(_refused_turn(sent) is None for sent in stub.sent)


def test_a_failure_that_is_not_about_the_program_is_not_handed_back(model, monkeypatch):
    stub = model(json.dumps(GOOD), json.dumps(GOOD), "回答")
    run = themis.run
    calls = {"n": 0}

    def once_broken(program, *args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("the kernel fell over")
        return run(program, *args, **kwargs)

    monkeypatch.setattr(themis, "run", once_broken)
    assert _ask().status_code == 200
    assert stub.sent[1]["messages"][-1]["content"] == QUESTION
