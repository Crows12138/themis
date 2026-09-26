"""A result says which question it answers, under the reader's own words.

When a model turns a sentence into a program, the program is a reading of
the sentence, and one sentence can be read more than one way. On the demo
server "吸烟会导致肺癌吗" was read once as whether smoking causes lung cancer
(a structural yes) and once as how large the effect is, with a confounder
the model added (a list of missing numbers). The page showed the sentence
and the verdict and never the reading between them, so a reader could not
tell which question had been answered without reconstructing it from the
graph and the reply (#780).

The reading is the kernel's own report line for the question, fetched from
``/api/question`` and shown under the words the reader typed.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import themis
from themis import language
from themis.output import analysis_report
from themis.web import app as app_module

from . import web_source

client = TestClient(app_module.app)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _variables(*names):
    return [{"kind": "variable", "predicate": n, "domain": [True, False]}
            for n in names]


def _program(query, *extra_edges):
    edges = [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
             for a, b in (("smoking", "lung_cancer"), *extra_edges)]
    names = sorted({n for a, b in (("smoking", "lung_cancer"), *extra_edges)
                    for n in (a, b)})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": [*_variables(*names), *edges,
                           {"kind": "query", "id": "q", "query": query}]}


#: One sentence, the two readings the demo server gave it.
WHETHER = _program({"kind": "cause", "from": _atom("smoking"),
                    "to": _atom("lung_cancer")})
HOW_LARGE = _program(
    {"kind": "effect",
     "intervention": {"atom": _atom("smoking"), "value": True},
     "target": {"atom": _atom("lung_cancer"), "value": True}, "given": []},
    ("genetic_predisposition", "smoking"),
    ("genetic_predisposition", "lung_cancer"))


def _asked(program):
    result = themis.run(program)["results"][0]
    response = client.post("/api/question",
                           json={"program": program, "result": result})
    assert response.status_code == 200, response.text
    return result, response.json()["words"]


@pytest.mark.parametrize("program", [WHETHER, HOW_LARGE],
                         ids=["whether", "how_large"])
def test_the_line_is_the_reports_own_in_every_language(program):
    result, words = _asked(program)
    assert set(words) == {str(lang) for lang in language.Lang}
    for lang in language.Lang:
        line = analysis_report.question_line(result, program, lang=lang)
        assert words[str(lang)] == line.replace("**", "")
        assert "**" not in words[str(lang)]


def test_two_readings_of_one_sentence_read_differently():
    """The case that asked for the line: a reader shown both would see
    that one asks whether and the other asks how large."""
    _, whether = _asked(WHETHER)
    _, how_large = _asked(HOW_LARGE)
    for lang in language.Lang:
        assert whether[str(lang)] != how_large[str(lang)]
        assert "smoking" in whether[str(lang)]
        assert "smoking" in how_large[str(lang)]


def test_no_model_is_needed(monkeypatch):
    monkeypatch.setattr(app_module, "_OFFERS_A_MODEL", False)
    result, words = _asked(WHETHER)
    assert all(words.values())


def test_a_line_that_cannot_be_said_is_refused_by_its_stage():
    response = client.post("/api/question", json={
        "program": WHETHER, "result": {"query_kind": "not_a_kind"}})
    assert response.status_code == 400
    body = response.json()
    assert body["stage"] == "question"
    assert set(body["words"]) == {str(lang) for lang in language.Lang}


def test_the_page_shows_it_under_the_readers_words():
    said = web_source.read(web_source.SRC / "components" / "ResultView.tsx")
    assert "questionOf(program, result)" in said
    asked = said.index("fill(SAYS.asked, lang)")
    read_as = said.index("fill(SAYS.readAs, lang)")
    assert asked < read_as
