"""Pin the round-trip: ``apply_patch_and_run`` must return a
``merged_program`` dict that ``themis.verify`` can audit the results
against.

This is a correctness contract: verifying a patched result against
the **original** program would see a divergent Theta (user-supplied
parameters missing) and falsely reject. The fix — surfaced by the
slice #33 stress test — is for ``apply_patch_and_run`` to include
the exact merged program it computed on, so auditors have the
program-result pairing that actually matches.
"""
from __future__ import annotations

import copy
import json

import pytest

import themis
from themis.input.syntactic_validator import validate_ast, validate_result
from themis.verifier import VerificationError


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _underframed_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "running", "domain": [True, False]},
            {"kind": "variable", "predicate": "belly_fat_loss",
             "domain": [True, False]},
            {"kind": "cause",
             "from": _atom("running"), "to": _atom("belly_fat_loss"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": _atom("belly_fat_loss"), "value": True},
                       "intervention": {"atom": _atom("running"), "value": True},
                       "given": []}},
        ],
    }


def _parameter_bundle(value: float = 0.55) -> dict:
    return {
        "version": "0.1",
        "kind": "parameter_fill_bundle",
        "skeletons": [{
            "kind": "probability",
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [{"atom": _atom("running"), "value": True}],
            "value": value,
            "annotations": {"source": "user_report"},
        }],
    }


def _framing_bundle() -> dict:
    return {
        "version": "0.1",
        "kind": "framing_skeleton_bundle",
        "patches": [
            {"kind": "variable_patch", "predicate": "running",
             "existing": {"domain": [True, False]},
             "fields": {"time_window": "12w",
                        "measurement": "self-report",
                        "threshold": ">=3 sessions/week",
                        "observability": "self-report",
                        "direction": "up",
                        "baseline": "prior week",
                        "state_vs_event": "state"}},
            {"kind": "variable_patch", "predicate": "belly_fat_loss",
             "existing": {"domain": [True, False]},
             "fields": {"time_window": "12w",
                        "measurement": "waist cm",
                        "threshold": ">=3 cm",
                        "observability": "self-measured",
                        "direction": "down",
                        "baseline": "prior week",
                        "state_vs_event": "state"}},
        ],
    }


# ================================================== envelope shape

def test_apply_patch_envelope_carries_merged_program():
    out = themis.apply_patch_and_run(
        _underframed_program(), [_parameter_bundle()]
    )
    assert "merged_program" in out
    assert "results" in out
    assert isinstance(out["merged_program"], dict)
    assert out["merged_program"]["version"] == "0.1"
    assert "statements" in out["merged_program"]


def test_merged_program_validates_against_kernel_ast_schema():
    """The serialized program must round-trip through the outer
    input validator — i.e. re-running it through ``themis.run``
    must succeed."""
    out = themis.apply_patch_and_run(
        _underframed_program(), [_parameter_bundle(), _framing_bundle()]
    )
    validate_ast(out["merged_program"])
    # And it actually runs — full circle.
    second_run = themis.run(out["merged_program"])
    assert second_run["results"][0]["status"] == "numerically_solved"


# ================================================== verify round-trip

def test_verify_round_trip_through_apply_patch_with_parameter_bundle():
    """The stress-test bug: original program + patched result used to
    raise (theta mismatch). Now the envelope carries the merged
    program so the audit matches the computation."""
    original = _underframed_program()
    out = themis.apply_patch_and_run(original, [_parameter_bundle(0.6)])
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    # This must NOT raise.
    themis.verify(out["merged_program"], r)


def test_verify_round_trip_through_apply_patch_with_both_bundles():
    original = _underframed_program()
    out = themis.apply_patch_and_run(
        original, [_framing_bundle(), _parameter_bundle(0.42)]
    )
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.42)
    themis.verify(out["merged_program"], r)


def test_verify_against_original_program_still_fails_as_expected():
    """Regression guard: verifying a patched result against the
    original program (instead of merged_program) still fails, so
    users who bypass the envelope feel the correctness boundary
    rather than silently getting wrong audits."""
    original = _underframed_program()
    out = themis.apply_patch_and_run(original, [_parameter_bundle(0.55)])
    r = out["results"][0]
    # Against merged_program: accepts
    themis.verify(out["merged_program"], r)
    # Against original: the parameter the result depended on is
    # absent in original's theta → verifier rejects.
    with pytest.raises(VerificationError):
        themis.verify(original, r)


# ================================================== program serializer

def test_merged_program_serializer_preserves_structure():
    """Round-trip: run -> apply-zero-patches -> merged_program must
    be semantically equivalent to the input (same statement set,
    same ordering within each kind), so merged_program is an honest
    echo of what the kernel ran on."""
    original = _underframed_program()
    out = themis.apply_patch_and_run(original, [])
    merged = out["merged_program"]

    def _kinds_and_predicates(ast):
        rows = []
        for s in ast["statements"]:
            row = {"kind": s["kind"]}
            if s["kind"] == "variable":
                row["predicate"] = s["predicate"]
            elif s["kind"] == "cause":
                row["from"] = s["from"]["predicate"]
                row["to"] = s["to"]["predicate"]
            elif s["kind"] == "query":
                row["id"] = s["id"]
                row["query_kind"] = s["query"]["kind"]
            rows.append(row)
        return rows

    assert _kinds_and_predicates(merged) == _kinds_and_predicates(original)


def test_merged_program_shows_user_supplied_parameter_statement():
    """When a parameter_fill_bundle was applied, the merged program
    must include the appended probabilityStatement — this is how
    the verifier's theta picks it up."""
    out = themis.apply_patch_and_run(
        _underframed_program(), [_parameter_bundle(0.33)]
    )
    prob_stmts = [
        s for s in out["merged_program"]["statements"]
        if s["kind"] == "probability"
    ]
    assert len(prob_stmts) == 1
    assert prob_stmts[0]["value"] == pytest.approx(0.33)


def test_merged_program_shows_filled_framing_fields():
    """When a framing_skeleton_bundle was applied, the merged program's
    VariableDeclaration statements carry the filled framing fields."""
    out = themis.apply_patch_and_run(
        _underframed_program(), [_framing_bundle()]
    )
    decls = {
        s["predicate"]: s
        for s in out["merged_program"]["statements"]
        if s["kind"] == "variable"
    }
    for pred in ("running", "belly_fat_loss"):
        assert decls[pred]["time_window"] == "12w"
        assert "measurement" in decls[pred]
        assert "threshold" in decls[pred]
        assert "observability" in decls[pred]


# ================================================== output validation

def test_merged_program_output_is_json_serializable():
    out = themis.apply_patch_and_run(
        _underframed_program(), [_framing_bundle(), _parameter_bundle()]
    )
    text = json.dumps(out, ensure_ascii=False)
    reloaded = json.loads(text)
    assert reloaded == out
