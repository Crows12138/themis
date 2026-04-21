"""Slice #37 / A5b: narrative-extraction merge tests.

Covers ``merge_variable_extractions`` (fold multiple A5 outputs) and
``merge_into_program`` (inject narrative variables into a kernel_ast
already built from a question). Pure JSON-in / JSON-out; no typed
Program objects, no LLM calls.
"""
from __future__ import annotations

import pytest

import themis
from themis.upstream import (
    ExtractionShapeError,
    MergeConflictError,
    merge_into_program,
    merge_variable_extractions,
)


# ======================================================= helpers

def _var(predicate: str, **fields) -> dict:
    return {"kind": "variable", "predicate": predicate, **fields}


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _effect_program(predicates, edges, target, intervention) -> dict:
    """Minimal kernel_ast dict for an effect query — the shape A1 emits."""
    statements: list = []
    for p in predicates:
        statements.append({"kind": "variable", "predicate": p, "domain": [True, False]})
    for src, dst in edges:
        statements.append({"kind": "cause", "from": _atom(src), "to": _atom(dst)})
    statements.append({
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "effect",
            "target": {"atom": _atom(target), "value": True},
            "intervention": {"atom": _atom(intervention), "value": True},
            "given": [],
        },
    })
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": statements,
    }


# ================================== merge_variable_extractions: basics

def test_merge_single_extraction_is_pass_through():
    ex = {"variables": [_var("running", domain=[True, False],
                              time_window="past 3 months")]}
    out = merge_variable_extractions(ex)
    assert out == ex


def test_merge_zero_extractions_returns_empty():
    assert merge_variable_extractions() == {"variables": []}


def test_merge_disjoint_predicates_preserves_order():
    a = {"variables": [_var("running", time_window="past 3 months")]}
    b = {"variables": [_var("waist_reduced", measurement="cm")]}
    out = merge_variable_extractions(a, b)
    assert [v["predicate"] for v in out["variables"]] == [
        "running", "waist_reduced",
    ]


# =========================== merge_variable_extractions: field union

def test_same_predicate_unions_disjoint_framing_fields():
    a = {"variables": [_var("running", domain=[True, False],
                              time_window="past 3 months")]}
    b = {"variables": [_var("running", threshold=">=4 sessions/week",
                              observability="self-report")]}
    out = merge_variable_extractions(a, b)
    assert len(out["variables"]) == 1
    v = out["variables"][0]
    assert v["predicate"] == "running"
    assert v["domain"] == [True, False]
    assert v["time_window"] == "past 3 months"
    assert v["threshold"] == ">=4 sessions/week"
    assert v["observability"] == "self-report"


def test_same_predicate_agreeing_field_is_kept_once():
    a = {"variables": [_var("running", time_window="past 3 months")]}
    b = {"variables": [_var("running", time_window="past 3 months")]}
    out = merge_variable_extractions(a, b)
    assert len(out["variables"]) == 1
    assert out["variables"][0]["time_window"] == "past 3 months"


# =========================== merge_variable_extractions: conflict

def test_field_conflict_raises_merge_conflict():
    a = {"variables": [_var("running", time_window="past 3 months")]}
    b = {"variables": [_var("running", time_window="daily")]}
    with pytest.raises(MergeConflictError) as exc:
        merge_variable_extractions(a, b)
    msg = str(exc.value)
    assert "running" in msg
    assert "time_window" in msg


def test_domain_conflict_raises_merge_conflict():
    a = {"variables": [_var("running", domain=[True, False])]}
    b = {"variables": [_var("running", domain=["low", "mid", "high"])]}
    with pytest.raises(MergeConflictError) as exc:
        merge_variable_extractions(a, b)
    assert "domain" in str(exc.value)


# =========================== merge_variable_extractions: shape errors

def test_missing_variables_key_raises_shape_error():
    with pytest.raises(ExtractionShapeError):
        merge_variable_extractions({})


def test_variables_not_a_list_raises_shape_error():
    with pytest.raises(ExtractionShapeError):
        merge_variable_extractions({"variables": "not-a-list"})


def test_entry_missing_kind_raises_shape_error():
    bad = {"variables": [{"predicate": "running"}]}  # no kind
    with pytest.raises(ExtractionShapeError):
        merge_variable_extractions(bad)


def test_entry_missing_predicate_raises_shape_error():
    bad = {"variables": [{"kind": "variable"}]}
    with pytest.raises(ExtractionShapeError):
        merge_variable_extractions(bad)


# =================================== merge_into_program: basic merge

def test_merge_into_program_fills_empty_declaration():
    """A1 side declares 'running' as a bare bool variable; A5 side
    carries the framing metadata. Merge fills the fields in."""
    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    narrative = {"variables": [
        _var("running", domain=[True, False],
             time_window="past 3 months",
             threshold=">=4 sessions/week"),
    ]}
    out = merge_into_program(prog, narrative)
    decls = [s for s in out["statements"] if s.get("kind") == "variable"]
    by_pred = {d["predicate"]: d for d in decls}
    assert by_pred["running"]["time_window"] == "past 3 months"
    assert by_pred["running"]["threshold"] == ">=4 sessions/week"
    # untouched
    assert "time_window" not in by_pred["belly_fat_loss"]


def test_merge_into_program_adds_new_predicate_before_causes():
    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    # Narrative introduces an extra context variable that the question
    # side did not declare. It should still land as a declaration.
    narrative = {"variables": [
        _var("age_over_40", domain=[True, False],
             measurement="self-report"),
    ]}
    out = merge_into_program(prog, narrative)
    kinds = [s["kind"] for s in out["statements"]]
    # all variable declarations come before the first cause statement
    first_cause = kinds.index("cause")
    assert all(k == "variable" for k in kinds[:first_cause])
    assert "age_over_40" in {
        s["predicate"] for s in out["statements"]
        if s.get("kind") == "variable"
    }


def test_merge_into_program_does_not_mutate_input():
    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    narrative = {"variables": [_var("running", time_window="past 3 months")]}
    before = [s.get("predicate") or s.get("kind") for s in prog["statements"]]
    _ = merge_into_program(prog, narrative)
    after = [s.get("predicate") or s.get("kind") for s in prog["statements"]]
    assert before == after
    # and the original running decl still has no time_window
    run_decl = next(s for s in prog["statements"]
                    if s.get("predicate") == "running")
    assert "time_window" not in run_decl


def test_merge_into_program_field_conflict_raises():
    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    # Kernel_ast already pins running.time_window — narrative disagrees
    prog["statements"][0]["time_window"] = "daily"
    narrative = {"variables": [_var("running", time_window="past 3 months")]}
    with pytest.raises(MergeConflictError):
        merge_into_program(prog, narrative)


# =================================== merge_into_program: end-to-end

def test_merged_program_runs_through_themis():
    """e2e: narrative-heavy framing + question edges → themis.run."""
    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    narrative = {"variables": [
        _var("running", domain=[True, False],
             time_window="past 3 months",
             threshold=">=4 sessions/week",
             measurement="self-report",
             observability="self-report",
             direction="up",
             baseline="pre-habit",
             state_vs_event="state"),
    ]}
    merged = merge_into_program(prog, narrative)
    out = themis.run(merged)
    r = out["results"][0]
    # Effect query with no parameters: needs_investigation.
    assert r["status"] == "needs_investigation"
    # Framing on 'running' is now complete — framing_notes for it
    # should list at most the still-unfilled fields. 'running' was
    # fully specified above, so it either doesn't appear in
    # framing_notes or appears with missing=[].
    notes = {n["predicate"]: n for n in r.get("framing_notes", [])}
    if "running" in notes:
        assert notes["running"]["missing"] == []


def test_merge_multi_extraction_then_into_program():
    """Two narrative paragraphs merge then land in the program."""
    a = {"variables": [_var("running", domain=[True, False],
                              time_window="past 3 months")]}
    b = {"variables": [_var("running", threshold=">=4 sessions/week"),
                          _var("waist_reduced", measurement="cm")]}
    combined = merge_variable_extractions(a, b)

    prog = _effect_program(
        predicates=["running", "belly_fat_loss"],
        edges=[("running", "belly_fat_loss")],
        target="belly_fat_loss",
        intervention="running",
    )
    merged = merge_into_program(prog, combined)
    run_decl = next(s for s in merged["statements"]
                    if s.get("predicate") == "running")
    assert run_decl["time_window"] == "past 3 months"
    assert run_decl["threshold"] == ">=4 sessions/week"
    # waist_reduced was not in the question — it's added as a new decl
    assert any(s.get("predicate") == "waist_reduced"
               for s in merged["statements"])
