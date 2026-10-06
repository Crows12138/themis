"""The reading a model writes is written for the reader on the page.

#817. The plain-language reading at the foot of a result is written by a
model from ``prompts/response_rendering.md``. That prompt was written for
one reader: somebody who holds the program and will patch it. It said so
— identifiers keep their original form, name each one once beside its
translation "so the user can refer back to it when patching" — and three
real readings showed what that does for a reader who holds nothing:
``llm_proposal``, ``severity: blocking``, ``precision_target:
pin_one_proportion``, ``time_window`` and ``individual_vs_population``
set in monospace beside their Chinese glosses, as addresses into a
document they will never open.

The reader is an input, as their language already was. The prompt says
what an address is and what each kind of reader can do with one; the web
bridge, whose reader is on the page, says so with the language. And the
page shows the reading as the Markdown it is written in — its headline,
lists and fenced formula were printed as text — without letting a model
put a link or an image on the page.

Measured on the same two questions with the changed prompt: no address
in either reading, every variable by its name.
"""
from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from themis.web import llm_bridge

from tests import web_source

REPO = pathlib.Path(__file__).resolve().parent.parent
PROMPT = REPO / "themis" / "prompts" / "response_rendering.md"
SRC = web_source.SRC


def _one_paragraph(text: str) -> str:
    return " ".join(text.split())


# ------------------------------------------------------------- the prompt

def test_the_reader_is_an_input_with_two_parts():
    prompt = _one_paragraph(PROMPT.read_text(encoding="utf-8"))
    assert "**The reader is an input, not a property of this file.**" in prompt
    assert ("the language they read, and whether they hold the program"
            ) in prompt


def test_an_address_is_said_to_each_reader_in_the_form_they_can_use():
    prompt = _one_paragraph(PROMPT.read_text(encoding="utf-8"))
    assert ("a predicate, a field name, a token out of a closed set, a method "
            "or assumption id — is an address") in prompt
    # One reader keeps the old treatment; the other gets none of it.
    assert "name each address once beside its translation" in prompt
    assert "the reply carries no address at all" in prompt
    assert ("a variable is called what its declaration's `name` calls it in "
            "their language") in prompt
    # A channel that says nothing is the channel this prompt was written
    # for, so nothing changes under it.
    assert ("Where the user message does not say, the reader holds the "
            "program.") in prompt
    assert "refer back to it when patching" in prompt


def test_the_reply_is_prose_with_markdown_where_there_is_structure():
    prompt = _one_paragraph(PROMPT.read_text(encoding="utf-8"))
    assert ("prose, with Markdown where what is said has structure (a "
            "heading, a list, a fence around a formula), and no JSON") in prompt
    assert "plain text, no JSON" not in prompt


# ------------------------------------------------------------- the bridge

class _Recording:
    def __init__(self, reply: str):
        self.sent: list[dict] = []
        self.base_url = "http://stub.invalid"

        def create(**kwargs):
            self.sent.append(kwargs)
            return SimpleNamespace(
                content=[SimpleNamespace(type="text", text=reply)])

        self.messages = SimpleNamespace(create=create)


@pytest.mark.parametrize("lang, endonym", [("zh", "中文"), ("en", "English")])
def test_the_web_bridge_says_its_reader_holds_nothing(monkeypatch, lang, endonym):
    client = _Recording("a reading")
    monkeypatch.setattr(llm_bridge, "_client", lambda api_key=None: client)
    llm_bridge.render_reply({"program": {}, "results": []}, nl="x", lang=lang)
    [call] = client.sent
    [turn] = call["messages"]
    said = turn["content"]
    assert f"Write the reply in {endonym}." in said
    assert ("They do not hold the program: they never see it or this JSON, "
            "and the page shows each variable by its declared `name`.") in said
    # Said before the envelope, with the language: it is about the reader,
    # not about the result.
    assert said.index("They do not hold the program") < said.index(
        "Below is the themis.run envelope")


# --------------------------------------------------------------- the page

def test_the_reading_is_shown_as_the_markdown_it_is_written_in():
    view = web_source.without_comments(
        web_source.read(SRC / "components" / "ResultView.tsx"))
    assert "import Markdown from 'react-markdown'" in view
    assert ("<Markdown disallowedElements={NOT_FROM_A_MODEL} unwrapDisallowed>"
            "{named(reply)}</Markdown>") in view
    assert "const NOT_FROM_A_MODEL = ['a', 'img']" in view
    # Not printed as text any more.
    assert "white-space: pre-wrap" not in [
        line for line in web_source.read(SRC / "styles.css").splitlines()
        if line.startswith(".reply__body {")][0]


def test_the_renderer_is_the_one_in_the_lockfile():
    """What the page is built with is a declared dependency, not something
    found on one machine."""
    package = (SRC.parent / "package.json").read_text(encoding="utf-8")
    assert '"react-markdown": "^10.' in package
    lock = (SRC.parent / "pnpm-lock.yaml").read_text(encoding="utf-8")
    assert "react-markdown@10." in lock
