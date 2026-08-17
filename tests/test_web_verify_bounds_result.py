"""The /api/verify_bounds_result web endpoint.

Web parallel of the MCP themis_verify_bounds_result tool.
Wraps themis.verify_bounds_result so paste-JSON UI users can audit
MTR / Manski-natural / Balke-Pearl IV bounds without going through
the derivation-required /api/verify path.
"""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

import themis
from themis.web.app import app


client = TestClient(app)


def _confounded_program():
    """Hidden u → x and u → y, plus x → y. Backdoor identification
    fails — bounds layer fires manski_natural."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "mn_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def _mtr_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "u",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "mtr_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": [],
                       "assumptions": {"monotonicity": "non_decreasing"}}},
        ],
    }


# ---------------------------------------------------------------------------
# Happy path: MN / MTR / BP-IV all accept via the new endpoint
# ---------------------------------------------------------------------------


def test_endpoint_accepts_clean_manski_natural():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result["bounds_result"]["method"] == "manski_natural"

    r = client.post(
        "/api/verify_bounds_result",
        json={"program": program, "result": result},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_endpoint_accepts_clean_mtr():
    program = _mtr_program()
    out = themis.run(program)
    result = out["results"][0]
    assert result["bounds_result"]["method"] == "manski_tamer_monotonicity"

    r = client.post(
        "/api/verify_bounds_result",
        json={"program": program, "result": result},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_endpoint_accepts_clean_balke_pearl_iv():
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "bidirected", "forall": ["I"],
             "left": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "right": {"predicate": "y",
                       "args": [{"type": "var", "name": "I"}]}},
            {"kind": "query", "id": "bp_e2e",
             "query": {"kind": "effect",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }
    out = themis.run(program)
    result = out["results"][0]
    assert result["bounds_result"]["method"] == "balke_pearl_iv"

    r = client.post(
        "/api/verify_bounds_result",
        json={"program": program, "result": result},
    )
    assert r.status_code == 200
    assert r.json() == {"ok": True}


# ---------------------------------------------------------------------------
# Error path: tampered bounds rejected with 400 + structured error
# ---------------------------------------------------------------------------


def test_endpoint_rejects_tampered_manski_natural_bounds():
    program = _confounded_program()
    out = themis.run(program)
    result = out["results"][0]
    result["bounds_result"]["lower_expression"] = "P(y=false)"  # tamper

    r = client.post(
        "/api/verify_bounds_result",
        json={"program": program, "result": result},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "VerificationError"
    assert "lower_expression mismatch" in body["message"]


def test_endpoint_rejects_result_without_bounds_result():
    program = _confounded_program()
    bare_result = {
        "status": "structurally_solved",
        "query_kind": "effect",
        "query_id": "mn_e2e",
        "structural_result": {"value": True},
    }
    r = client.post(
        "/api/verify_bounds_result",
        json={"program": program, "result": bare_result},
    )
    assert r.status_code == 400
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "ValueError"
    assert "requires result.bounds_result" in body["message"]
