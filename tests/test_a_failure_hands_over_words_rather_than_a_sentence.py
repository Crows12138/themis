"""The web edge decides who a text is for, instead of sending it all one way.

Fifteen handlers each answered ``{"error": type(exc).__name__, "message":
str(exc)}``. ``str(exc)`` is what the raise site wrote, and this package's
raise sites write for more than one reader — so a person asking a causal
question could be handed an argument contract, a JSON parser's complaint,
or an invariant, in whatever language its author happened to use.

That is why "not addressed to a reader" had no name here: the boundary
that would have needed one was not being drawn. These gates keep it drawn.
What they do not check is whether a stage's sentence is a GOOD one, or
whether the endpoint picked the right stage — the first is a reader's
judgement and the second is the endpoint's.
"""
from __future__ import annotations

import ast
import pathlib

import pytest

from themis import language, refusals
from themis.web import failure

ROOT = pathlib.Path(__file__).resolve().parent.parent
APP = ROOT / "themis/web/app.py"


def test_every_stage_has_a_sentence_in_every_language():
    for stage, words in failure.STAGE.items():
        assert set(words) == set(language.written()), stage


def test_no_endpoint_words_a_failure_itself():
    """The structural half: a handler that builds its own 400 body is a
    second author, and the language it picks is whichever one that author
    was writing in that day. Read off the source, because the branch that
    fails is the branch a smoke test does not take."""
    tree = ast.parse(APP.read_text(encoding="utf-8"))
    built: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != "JSONResponse":
            continue
        if any(k.arg == "status_code" and getattr(k.value, "value", None) != 200
               for k in node.keywords):
            built.append(node.lineno)
    assert built == [], (
        f"themis/web/app.py builds a failure body at lines {built}; answer "
        f"through themis.web.failure.refused so the sentence has one author"
    )


def test_an_unknown_stage_is_refused_rather_than_rendered_empty():
    """The counterexample. A lookup with a fallback would hand a reader an
    empty sentence, which reads exactly like a failure with nothing to say
    about itself."""
    with pytest.raises(KeyError, match="no sentence for stage"):
        failure.payload("a_stage_nobody_declared", ValueError("x"))


def test_a_refusal_that_owns_its_sentence_keeps_it():
    """An estimator that declines already has its wording in every language,
    beside the species. Wording it again here would be a second author for
    one fact — which is what themis.refusals.SAYS exists to prevent."""
    exc = refusals.EstimatorFailure(
        refusals.Refusal.SAMPLE_TOO_SMALL, n=40, minimum=100)
    body = failure.payload("estimate", exc)
    assert body["words"] == dict(refusals.SAYS["sample_too_small"])
    assert body["slots"] == {"n": 40, "minimum": 100}
    assert body["words"] != dict(failure.STAGE["estimate"])


def test_a_refusal_with_no_sentence_yet_falls_to_the_stage():
    """Not to silence, and not to ``str(exc)`` as the sentence: a species
    still authoring its own wording has one, but it is in one language."""
    assert "overlap_insufficient" not in refusals.SAYS
    exc = refusals.EstimatorFailure(
        refusals.Refusal.OVERLAP_INSUFFICIENT, "a stratum held one arm")
    body = failure.payload("estimate", exc)
    assert body["words"] == dict(failure.STAGE["estimate"])
    assert body["diagnostic"] == "a stratum held one arm"


def test_the_exception_text_travels_as_a_diagnostic_not_as_the_sentence():
    body = failure.payload("run", ValueError("edges[3] must be a mapping"))
    assert body["diagnostic"] == "edges[3] must be a mapping"
    assert body["error"] == "ValueError"
    assert "message" not in body, (
        "`message` was the field that made str(exc) the reader's sentence"
    )


def test_a_failure_with_no_exception_carries_no_diagnostic():
    """Nothing went wrong inside — there is only the sentence, and ``stage``
    is the whole of what happened."""
    body = failure.payload("nothing_to_clarify")
    assert "diagnostic" not in body
    assert "error" not in body
    assert body["stage"] == "nothing_to_clarify"


def test_a_live_endpoint_answers_in_the_new_shape():
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from themis.web.app import app

    r = TestClient(app).post("/api/run", json={"program": {"version": "0.1"}})
    assert r.status_code == 400
    body = r.json()
    assert body["stage"] == "run"
    assert set(body["words"]) == set(language.written())
    assert body["diagnostic"]
    assert "message" not in body
