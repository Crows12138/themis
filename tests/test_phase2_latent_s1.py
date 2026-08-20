"""Phase 2.latent S1: bidirected AST + schema surface.

S1 scope is table-land only: the bidirected statement parses into a
typed BidirectedStatement, the schema accepts and rejects the right
shapes, the statement round-trips through the serializer. Runtime
dispatch must fail loudly — not silently drop the edge — because the
m-separation / c-component machinery needed to actually use it lands
in S2+.

See PHASE_2_LATENT_CHARTER.md §7 for the slice plan.
"""
from __future__ import annotations

import json

import pytest

import themis
from themis.input.semantic_validator import (
    SemanticError,
    validate_program,
)
from themis.input.syntactic_validator import SyntacticError, validate_ast
from themis.kernel import _program_to_ast_dict
from themis.types import BidirectedStatement, Statement


# ============================================================== helpers

def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program_with_bidirected(extra_statements=()) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking", "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer", "domain": [True, False]},
            {
                "kind": "bidirected",
                "left": _atom("smoking"),
                "right": _atom("lung_cancer"),
                "annotations": {"source": "literature", "confidence": 0.8},
            },
            *extra_statements,
        ],
    }


# ==================================================== schema acceptance

def test_schema_accepts_bidirected_statement():
    program = _program_with_bidirected()
    # validate_ast returns the (possibly transformed) ast on success.
    out = validate_ast(program)
    assert isinstance(out, dict)


def test_schema_rejects_bidirected_missing_left():
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "bidirected", "right": _atom("y")},
        ],
    }
    with pytest.raises(SyntacticError):
        validate_ast(program)


def test_schema_rejects_bidirected_missing_right():
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "bidirected", "left": _atom("x")},
        ],
    }
    with pytest.raises(SyntacticError):
        validate_ast(program)


def test_schema_rejects_bidirected_with_from_to_keys():
    """bidirected uses left/right — cause's from/to must be rejected
    so the two edge kinds can't be mistaken for each other."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "bidirected", "from": _atom("x"), "to": _atom("y")},
        ],
    }
    with pytest.raises(SyntacticError):
        validate_ast(program)


# ===================================================== typed parsing

def test_validate_program_produces_typed_bidirected_statement():
    ast = _program_with_bidirected()
    # An empty check set isolates parsing from every semantic rule.
    prog = validate_program(ast, checks=frozenset())
    bidirs = [s for s in prog.statements if isinstance(s, BidirectedStatement)]
    assert len(bidirs) == 1
    b = bidirs[0]
    assert b.left.predicate == "smoking"
    assert b.right.predicate == "lung_cancer"
    assert b.annotations is not None
    assert b.annotations.source == "literature"
    assert b.annotations.confidence == 0.8


def test_parsed_bidirected_is_in_statement_union():
    """BidirectedStatement must be one of the Statement union types so
    downstream isinstance checks across the runtime stay exhaustive."""
    from typing import get_args
    assert BidirectedStatement in get_args(Statement)


# ===================================================== serializer round-trip

def test_program_to_ast_round_trips_bidirected():
    """Typed Program → dict → typed Program stays identical on
    bidirected statements (including annotations and empty forall)."""
    ast = _program_with_bidirected()
    prog = validate_program(ast, checks=frozenset())
    emitted = _program_to_ast_dict(prog)

    bidirs = [s for s in emitted["statements"] if s["kind"] == "bidirected"]
    assert len(bidirs) == 1
    b = bidirs[0]
    assert b["left"]["predicate"] == "smoking"
    assert b["right"]["predicate"] == "lung_cancer"
    assert b["annotations"] == {"source": "literature", "confidence": 0.8}
    assert "forall" not in b

    # And round-trip: emitted AST is schema-valid and re-parses.
    validate_ast(emitted)
    prog2 = validate_program(emitted, checks=frozenset())
    b2 = next(s for s in prog2.statements if isinstance(s, BidirectedStatement))
    assert b2 == next(s for s in prog.statements if isinstance(s, BidirectedStatement))


def test_serializer_round_trip_preserves_forall():
    """Bidirected with forall (slice A4-style quantifier symmetry with
    cause) must survive the serializer."""
    ast = {
        "version": "0.1",
        "domain": {
            "objects": [
                {"kind": "object", "name": "alice"},
                {"kind": "object", "name": "bob"},
            ]
        },
        "statements": [
            {
                "kind": "bidirected",
                "forall": ["X"],
                "left": {
                    "predicate": "income",
                    "args": [{"type": "var", "name": "X"}],
                },
                "right": {
                    "predicate": "health",
                    "args": [{"type": "var", "name": "X"}],
                },
            },
        ],
    }
    prog = validate_program(ast, checks=frozenset())
    emitted = _program_to_ast_dict(prog)
    b = next(s for s in emitted["statements"] if s["kind"] == "bidirected")
    assert b["forall"] == ["X"]


# ================================================ runtime guard (S1)
#
# What the gate refuses, and why, is no longer a list of kinds and no
# longer lives here — see
# tests/test_the_gate_asks_what_a_latent_can_do_not_who_reads_it.py.
# Three tests moved out with it: they pinned the gate by naming ``cause``
# as a kind that must be refused, and it was answering correctly the whole
# time. What stays here is Slice 1's own subject, which is that a
# bidirected statement parses and travels.


def test_bidirected_without_queries_now_passes_validation():
    """Post-S3.a: a program with bidirected but zero queries has no
    silent-drop risk (nothing to dispatch) — validation succeeds and
    run returns empty results. Regression pin for the narrowed gate."""
    ast = _program_with_bidirected()  # no query
    out = themis.run(ast)
    assert out["results"] == []


# ================================================ semantic checks on bidirected

def test_objects_check_fires_on_bidirected_atoms():
    """ConstTerm('ghost') in a bidirected edge should trigger the
    objects check just like it does for cause edges."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "bidirected",
                "left": {
                    "predicate": "x",
                    "args": [{"type": "const", "name": "ghost"}],
                },
                "right": _atom("y"),
            },
        ],
    }
    with pytest.raises(SemanticError) as exc:
        validate_program(ast, checks=frozenset({"objects"}))
    assert "ghost" in str(exc.value)


def test_bound_variables_check_fires_on_bidirected_edges():
    """Free VarTerm in a bidirected atom must be rejected by
    bound_variables, same as in cause / probability."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {
                "kind": "bidirected",
                "left": {
                    "predicate": "x",
                    "args": [{"type": "var", "name": "U"}],
                },
                "right": _atom("y"),
            },
        ],
    }
    with pytest.raises(SemanticError):
        validate_program(ast, checks=frozenset({"bound_variables"}))


# =================================================== regression guarantee

def test_pre_bidirected_programs_still_run():
    """Bare-DAG smoke test: a pure-cause program must still dispatch
    to structurally_solved (regression guarantee per charter §6.3)."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "cause", "from": _atom("x"), "to": _atom("y")}},
        ],
    }
    out = themis.run(ast)
    assert out["results"][0]["status"] == "structurally_solved"


def test_gate_check_listed_in_slice_1_checks():
    """Meta: the gate check must be in the default check set; otherwise
    it is trivially easy to forget to enable it and have bidirected
    programs silently succeed with a stripped graph."""
    from themis.input.semantic_validator import SLICE_1_CHECKS
    assert "bidirected_runtime_gate" in SLICE_1_CHECKS
