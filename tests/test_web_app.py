"""Smoke tests for the local web UI — endpoints + happy-path round-trips."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from themis.web.app import app


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
    assert "message" in body


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
