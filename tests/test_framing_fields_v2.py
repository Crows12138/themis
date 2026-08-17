"""Slice #41: pin that direction / baseline / state_vs_event framing
fields are first-class alongside the original four.

The three fields were surfaced by a framing stress test as
ambiguity dimensions every fresh agent ran into but the original
``time_window / measurement / threshold / observability`` set
couldn't capture. They join the A0 / F1 channel symmetrically.
"""
from __future__ import annotations

import copy
import json

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.runtime.framing_check import _REPORTABLE_FIELDS, check_framing
from themis.types import (
    Atom,
    ConstTerm,
    EffectQuery,
    Intervention,
    Program,
    QueryStatement,
    ValuedAtom,
    VariableDeclaration,
)


def _atom(pred: str) -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name="me"),))


def _effect_query(target_pred: str, intervention_pred: str) -> QueryStatement:
    return QueryStatement(
        id="q",
        query=EffectQuery(
            target=ValuedAtom(atom=_atom(target_pred), value=True),
            intervention=Intervention(atom=_atom(intervention_pred), value=True),
            given=(),
        ),
    )


# ============================================== registry / constants

def test_reportable_fields_include_slice_41_additions():
    assert "direction" in _REPORTABLE_FIELDS
    assert "baseline" in _REPORTABLE_FIELDS
    assert "state_vs_event" in _REPORTABLE_FIELDS


# ============================================== VariableDeclaration

def test_variable_declaration_accepts_new_fields_via_typed_constructor():
    decl = VariableDeclaration(
        predicate="y",
        domain=(True, False),
        direction="up",
        baseline="pre-intervention",
        state_vs_event="state",
    )
    assert decl.direction == "up"
    assert decl.baseline == "pre-intervention"
    assert decl.state_vs_event == "state"


def test_new_fields_default_to_none_when_unset():
    decl = VariableDeclaration(predicate="y")
    assert decl.direction is None
    assert decl.baseline is None
    assert decl.state_vs_event is None


# ============================================== framing_check behavior

def test_declared_but_partial_predicate_reports_new_fields_as_gaps():
    """A predicate that sets only the original four framing fields
    now leaves three #41 gaps that A0 flags."""
    stmt = _effect_query("y", "x")
    program = Program(
        version="0.1", objects=("me",),
        statements=(
            VariableDeclaration(
                predicate="y",
                domain=(True, False),
                time_window="12w",
                measurement="cm",
                threshold=">=3",
                observability="observed",
            ),
            stmt,
        ),
    )
    notes = check_framing(program, stmt)
    assert len(notes) == 1
    assert set(notes[0].missing) == {"direction", "baseline", "state_vs_event"}


def test_fully_framed_predicate_with_seven_fields_is_silent():
    stmt = _effect_query("y", "x")
    program = Program(
        version="0.1", objects=("me",),
        statements=(
            VariableDeclaration(
                predicate="y",
                domain=(True, False),
                time_window="12w",
                measurement="cm",
                threshold=">=3",
                observability="observed",
                direction="up",
                baseline="pre-intervention",
                state_vs_event="state",
            ),
            stmt,
        ),
    )
    assert check_framing(program, stmt) == ()


# ============================================== JSON input contract

def test_kernel_ast_schema_accepts_new_fields():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "variable", "predicate": "y",
                "domain": [True, False],
                "direction": "up",
                "baseline": "pre-intervention",
                "state_vs_event": "state",
            },
        ],
    }
    validate_ast(ast)  # must not raise


def test_kernel_ast_schema_rejects_non_string_new_fields():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y",
             "domain": [True, False],
             "direction": {"not": "a string"}},
        ],
    }
    with pytest.raises(SyntacticError):
        validate_ast(ast)


# ============================================== round-trip through themis

def test_new_fields_round_trip_through_themis_run():
    """Declare all seven framing fields; framing_notes should stay
    empty, and the merged path through themis.run works end to end."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x",
             "domain": [True, False],
             "time_window": "12w", "measurement": "cm",
             "threshold": ">=3", "observability": "observed",
             "direction": "up", "baseline": "pre", "state_vs_event": "state"},
            {"kind": "variable", "predicate": "y",
             "domain": [True, False],
             "time_window": "12w", "measurement": "cm",
             "threshold": ">=3", "observability": "observed",
             "direction": "down", "baseline": "pre", "state_vs_event": "state"},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": atom("x"), "to": atom("y")}},
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r.get("framing_notes", []) == []


def test_patch_bundle_carries_new_fields_and_merges_cleanly():
    """A variable_patch can fill direction / baseline / state_vs_event
    the same way it fills the original four fields."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("y"), "to": atom("y")} if False else None,
            {"kind": "query", "id": "q",
             "query": {"kind": "probability",
                       "target": {"atom": atom("y"), "value": True},
                       "given": []}},
        ],
    }
    # Strip the placeholder None
    ast["statements"] = [s for s in ast["statements"] if s is not None]

    out1 = themis.run(ast)
    r1 = out1["results"][0]
    # Framing channel flags all seven reportable fields on y.
    assert any(
        f == "direction" for note in r1.get("framing_notes", [])
        for f in note["missing"]
    )

    bundle = {
        "version": "0.1", "kind": "framing_skeleton_bundle",
        "patches": [{
            "kind": "variable_patch", "predicate": "y",
            "existing": {"domain": [True, False]},
            "fields": {
                "time_window": "12w", "measurement": "cm",
                "threshold": ">=3", "observability": "observed",
                "direction": "up", "baseline": "pre",
                "state_vs_event": "state",
            },
        }],
    }
    out2 = themis.apply_patch_and_run(ast, [bundle])
    r2 = out2["results"][0]
    # After filling all seven fields, framing channel is silent.
    assert r2.get("framing_notes", []) == []


# ============================================== merged_program echo

def test_merged_program_echoes_new_fields():
    """Program -> AST dict serializer must emit the three new fields
    so the verify round-trip sees what the kernel ran on."""
    def atom(p): return {"predicate": p, "args": [{"type": "const", "name": "me"}]}
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "query", "id": "q",
             "query": {"kind": "probability",
                       "target": {"atom": atom("y"), "value": True},
                       "given": []}},
        ],
    }
    bundle = {
        "version": "0.1", "kind": "framing_skeleton_bundle",
        "patches": [{
            "kind": "variable_patch", "predicate": "y",
            "existing": {"domain": [True, False]},
            "fields": {
                "direction": "up",
                "baseline": "pre",
                "state_vs_event": "state",
            },
        }],
    }
    out = themis.apply_patch_and_run(ast, [bundle])
    merged_vars = [
        s for s in out["merged_program"]["statements"]
        if s["kind"] == "variable"
    ]
    assert len(merged_vars) == 1
    v = merged_vars[0]
    assert v["direction"] == "up"
    assert v["baseline"] == "pre"
    assert v["state_vs_event"] == "state"
