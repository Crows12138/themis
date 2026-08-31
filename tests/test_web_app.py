"""Smoke tests for the local web UI — endpoints + happy-path round-trips."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from themis.web.app import app
from tests import caveats


client = TestClient(app)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _trivial_cause_program():
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


def test_index_serves_html():
    r = client.get("/")
    assert r.status_code == 200
    assert b"Themis" in r.content


def test_run_endpoint_returns_envelope():
    r = client.post("/api/run", json={"program": _trivial_cause_program()})
    assert r.status_code == 200
    body = r.json()
    assert "results" in body
    assert body["results"][0]["status"] == "structurally_solved"


def test_run_endpoint_surfaces_error_as_400():
    bad = {"version": "0.1"}  # missing domain / statements
    r = client.post("/api/run", json={"program": bad})
    assert r.status_code == 400
    body = r.json()
    assert "error" in body
    # The sentence arrives keyed by language rather than finished, and the
    # exception's own text arrives beside it saying what it is. The shape is
    # gated in test_a_failure_hands_over_words_rather_than_a_sentence.py.
    assert "words" in body
    assert "diagnostic" in body


def test_verify_endpoint_round_trips():
    program = _trivial_cause_program()
    run_resp = client.post("/api/run", json={"program": program})
    result = run_resp.json()["results"][0]
    r = client.post("/api/verify", json={"program": program, "result": result})
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_verify_endpoint_returns_structured_error_when_unverifiable():
    """Counterfactual NEEDS_ASSUMPTION has no derivation; verify can't
    audit. Endpoint surfaces a 400 with structured error rather than
    a 500."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {
                "kind": "counterfactual",
                "observed": {"atom": _atom("x"), "value": False},
                "counterfactual_intervention": {
                    "atom": _atom("x"), "value": True,
                },
                "counterfactual_target": {
                    "atom": _atom("y"), "value": True,
                },
             }},
        ],
    }
    result = client.post("/api/run", json={"program": program}).json()["results"][0]
    r = client.post("/api/verify", json={"program": program, "result": result})
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert "error" in body


def test_new_gap_kinds_round_trip_through_web_api():
    """unmeasured_confounder_risk and
    unattempted_layer_due_to_dispatch_conflict must propagate through
    the web /api/run endpoint with their ⚠ caveats reaching
    result.explanation. The web layer is a thin pass-through, so kernel
    fixes should automatically reach web users — but let's pin that
    contract explicitly so a future serialization regression doesn't
    silently strip the new gap_kinds."""
    import json
    from pathlib import Path
    repo_root = Path(__file__).resolve().parents[1]

    cases = [
        ("case_001_hrt_cvd.json", "unmeasured_confounder_risk"),
        (
            "case_009_mediation_x_transport.json",
            "unattempted_layer_due_to_dispatch_conflict",
        ),
    ]
    for case_file, expected_kind in cases:
        program = json.loads(
            (repo_root / "docs" / "l3_simulation" / case_file).read_text(
                encoding="utf-8"
            )
        )
        resp = client.post("/api/run", json={"program": program})
        assert resp.status_code == 200, f"{case_file}: {resp.text[:200]}"
        result = resp.json()["results"][0]
        gap_kinds = [
            g["kind"]
            for g in result.get("data_gap_report", {}).get("gaps", [])
        ]
        assert expected_kind in gap_kinds, (
            f"{case_file}: expected {expected_kind!r} in gap_kinds; got {gap_kinds}"
        )
        explanation = caveats.text(result)
        assert "⚠" in explanation, (
            f"{case_file}: must-disclose caveat ⚠ should appear in "
            f"explanation; got: {explanation[:200]!r}"
        )


# --- the reader's language, on the two channels that answer in prose ---------
#
# Nothing else here has to carry it: every other endpoint hands back an
# artifact and the browser renders it in whichever language the reader
# picked. A reply written by a model has its language the moment it is
# written, so these two are the only requests the choice has to travel on
# — and it did not travel on any of them, so both answered every reader in
# the language the site was written in.


@pytest.mark.parametrize("asked", ["zh", "en"])
def test_the_reader_s_language_reaches_the_model(asked, monkeypatch):
    """What the endpoint hands the bridge, not what the bridge does with it.

    Every language this build answers in, rather than one: a site that had
    gone on writing its author's language would pass one of these two, and
    a check that only ever asked for the other would call that wired.

    Recorded through the module the endpoint imports FROM, because that is
    the name the call resolves at run time.
    """
    from themis.web import llm_bridge

    seen: dict = {}

    def _recorded(envelope, *, nl=None, lang=None, api_key=None, model=None):
        seen["lang"] = lang
        return "…"

    monkeypatch.setattr(llm_bridge, "render_reply", _recorded)
    r = client.post("/api/render", json={"program": _trivial_cause_program(),
                                         "nl": "does x cause y",
                                         "lang": asked})
    assert r.status_code == 200, r.text
    assert str(seen["lang"]) == asked


def test_a_request_that_says_nothing_gets_the_default():
    """The default sits at this door and nowhere below it, so a caller who
    does not say which language still gets an answer — which is what a
    default is for. The failure this closes is not the absent field; it is
    the field having nowhere to go once somebody filled it in."""
    from themis.web.app import RenderRequest
    from themis import language

    assert RenderRequest(program={}).lang == language.DEFAULT


def test_a_language_this_build_cannot_answer_in_is_refused_at_the_door():
    """Rather than falling through to the site's own. The type is the enum,
    so the boundary refuses an undeclared tag the same way it refuses a
    program that is not an object — and a reader is never told that a
    language they asked for was quietly swapped for another."""
    r = client.post("/api/render", json={"program": _trivial_cause_program(),
                                         "lang": "fr"})
    assert r.status_code == 422, r.text


def test_examples_endpoint_lists_worked_examples():
    r = client.get("/api/examples")
    assert r.status_code == 200
    items = r.json()
    assert isinstance(items, list)
    if items:
        # Each example should at minimum have a name + program.
        first = items[0]
        assert "name" in first
        assert "program" in first
