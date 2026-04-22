"""F9 / G1 fix: DEFINE_VARIABLE investigation is scoped to queries
whose dispatch path blocks on framing (effect, probability). For
pure-structural queries (cause, assoc, identify) framing gaps stay
in ``framing_notes`` (advisory) but do NOT produce a
DEFINE_VARIABLE investigation_request.

Rationale: the eval v1 stress test (docs/trial_reports/
eval_set_v1_*.md) showed that cause / assoc queries were asking
users for 7 framing fields on every predicate even though the
query itself was answered at the graph level and didn't need
operationalization. G1 finding in docs/trial_reports/
post_phase2_latent_stress_test.md.
"""
from __future__ import annotations

import themis


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _base_program(query_block: dict) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")},
            {"kind": "query", "id": "q", "query": query_block},
        ],
    }


def _define_variable_requests(result: dict) -> list:
    return [
        req for req in result.get("investigation_requests", [])
        if req.get("action") == "define_variable"
    ]


# ============================ structural queries: NO DEFINE_VARIABLE

def test_cause_query_does_not_emit_define_variable():
    ast = _base_program({
        "kind": "cause",
        "from": _atom("smoking"), "to": _atom("lung_cancer"),
    })
    r = themis.run(ast)["results"][0]
    assert r["status"] == "structurally_solved"
    # advisory framing_notes still emitted (informational channel)
    notes = r.get("framing_notes", [])
    assert len(notes) == 2
    assert all(len(n["missing"]) == 7 for n in notes)
    # but no DEFINE_VARIABLE investigation on a structural query
    assert _define_variable_requests(r) == []


def test_assoc_query_does_not_emit_define_variable():
    ast = _base_program({
        "kind": "assoc",
        "left": _atom("smoking"), "right": _atom("lung_cancer"),
        "given": [],
    })
    r = themis.run(ast)["results"][0]
    assert r["status"] == "structurally_solved"
    assert r.get("framing_notes", [])  # still present
    assert _define_variable_requests(r) == []


def test_identify_query_does_not_emit_define_variable():
    ast = _base_program({
        "kind": "identify",
        "target": _atom("lung_cancer"),
        "intervention": {"atom": _atom("smoking"), "value": True},
        "given": [],
    })
    r = themis.run(ast)["results"][0]
    assert r["status"] == "structurally_solved"
    assert r.get("framing_notes", [])  # still advisory
    assert _define_variable_requests(r) == []


# ============================ numeric queries: keep DEFINE_VARIABLE

def test_effect_query_still_emits_define_variable():
    ast = _base_program({
        "kind": "effect",
        "target": {"atom": _atom("lung_cancer"), "value": True},
        "intervention": {"atom": _atom("smoking"), "value": True},
        "given": [],
    })
    r = themis.run(ast)["results"][0]
    # effect query blocks on theta; framing gaps are actionable
    reqs = _define_variable_requests(r)
    assert len(reqs) == 1
    assert {it["target"] for it in reqs[0]["items"]} == {"smoking", "lung_cancer"}


def test_probability_query_still_emits_define_variable():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "probability",
                 "target": {"atom": _atom("lung_cancer"), "value": True},
                 "given": [{"atom": _atom("smoking"), "value": True}],
             }},
        ],
    }
    r = themis.run(ast)["results"][0]
    reqs = _define_variable_requests(r)
    # probability blocks on theta — framing is actionable
    assert len(reqs) == 1


# ============================ framing_notes advisory still works

def test_cause_query_framing_notes_list_unfilled_fields():
    """Advisory channel still needs to tell response_rendering which
    fields are unset so it can mention them as soft context if useful.
    This confirms we didn't accidentally drop framing_notes along with
    the investigation_request."""
    ast = _base_program({
        "kind": "cause",
        "from": _atom("smoking"), "to": _atom("lung_cancer"),
    })
    r = themis.run(ast)["results"][0]
    notes_by_pred = {n["predicate"]: set(n["missing"]) for n in r["framing_notes"]}
    expected_fields = {
        "time_window", "measurement", "threshold", "observability",
        "direction", "baseline", "state_vs_event",
    }
    assert notes_by_pred["smoking"] == expected_fields
    assert notes_by_pred["lung_cancer"] == expected_fields


# =================== mixed program: per-query scope (independence)

def test_mixed_query_program_scopes_define_variable_per_query():
    """Program with both a structural and a numeric query must produce
    DEFINE_VARIABLE only on the numeric one."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {"kind": "cause", "from": _atom("smoking"), "to": _atom("lung_cancer")},
            {"kind": "query", "id": "q_cause",
             "query": {"kind": "cause",
                       "from": _atom("smoking"), "to": _atom("lung_cancer")}},
            {"kind": "query", "id": "q_effect",
             "query": {"kind": "effect",
                       "target": {"atom": _atom("lung_cancer"), "value": True},
                       "intervention": {"atom": _atom("smoking"), "value": True},
                       "given": []}},
        ],
    }
    results = {r["query_id"]: r for r in themis.run(ast)["results"]}
    # cause: no DEFINE_VARIABLE
    assert _define_variable_requests(results["q_cause"]) == []
    # effect: still emits DEFINE_VARIABLE
    assert len(_define_variable_requests(results["q_effect"])) == 1
