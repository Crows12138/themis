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


def test_new_gap_kinds_round_trip_through_web_api():
    """iter 28 audit guard: the gap_kinds added in iter 5
    (unmeasured_confounder_risk) and iter 19
    (unattempted_layer_due_to_dispatch_conflict) must propagate through
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
        explanation = result.get("explanation") or ""
        assert "⚠" in explanation, (
            f"{case_file}: must-disclose caveat ⚠ should appear in "
            f"explanation; got: {explanation[:200]!r}"
        )


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
