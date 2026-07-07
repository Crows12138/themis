"""Pipeline wiring for the general counterfactual (ID*) query kind.

``ctf_identify.id_star`` (the Shpitser-Pearl 2007 counterfactual identifier)
was previously a pure function unreachable from the kernel's public surface.
This slice threads a new ``counterfactual_conjunction`` query kind through
the whole stack — schema, semantic validation, graph projection, scheduler
dispatch, kernel round-trip, explanation, and the independent verifier — so
a client can hand the kernel a counterfactual conjunction γ as JSON and get
back an identified estimand (or a non-identifiable / P(γ)=0 verdict) that a
second, independent pass re-checks.

The verifier mirror is a Monte-Carlo *semantic* probe: it samples SCMs
consistent with the ADMG, computes the true P(γ) by counterfactual
Monte-Carlo over a shared exogenous background, and rejects a formula that
computes the wrong number. ``test_verify_rejects_tampered_formula`` proves
it has teeth.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

import themis
from themis.input.semantic_validator import SemanticError, validate_program
from themis.input.syntactic_validator import SyntacticError, validate_ast, validate_result
from themis.kernel import _program_to_ast_dict, run
from themis.verifier import VerificationError
from themis.types import (
    ConstantExpr,
    CounterfactualConjunctionQuery,
    CounterfactualEvent,
    ProbabilityRefExpr,
    QueryStatement,
    SumExpr,
)


# ------------------------------------------------------------------ builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _bidir(a, b):
    return {"kind": "bidirected", "left": {"predicate": a, "args": []},
            "right": {"predicate": b, "args": []}}


def _ev(varname, subs, value):
    return {"variable": {"predicate": varname, "args": []},
            "subscript": [{"atom": {"predicate": a, "args": []}, "value": v}
                          for (a, v) in subs],
            "value": value}


def _ast(statements, events):
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            *statements,
            {"kind": "query", "id": "q",
             "query": {"kind": "counterfactual_conjunction", "events": events}},
        ],
    }


def _simple_effect_ast():
    # X -> Y, γ = (Y_{X=1}=1). No confounding → P(Y_{X=1}=1) = P(y|x).
    return _ast([_var("x"), _var("y"), _cause("x", "y")],
                [_ev("y", [("x", True)], True)])


def _fig1_ast():
    # X->W->Y<-Z<-D, X<->Y. γ = y_x ∧ x' ∧ z_d ∧ d  (cfid worked example).
    return _ast(
        [_var("x"), _var("w"), _var("y"), _var("z"), _var("d"),
         _cause("x", "w"), _cause("w", "y"), _cause("z", "y"), _cause("d", "z"),
         _bidir("x", "y")],
        [_ev("y", [("x", True)], True),
         _ev("x", [], False),
         _ev("z", [("d", True)], True),
         _ev("d", [], True)],
    )


def _pns_ast():
    # X->Y, X<->Y, γ = y_x ∧ y'_{x'}  — the w-graph, non-identifiable.
    return _ast([_var("x"), _var("y"), _cause("x", "y"), _bidir("x", "y")],
                [_ev("y", [("x", True)], True),
                 _ev("y", [("x", False)], False)])


# ------------------------------------------------------------------ schema
def test_schema_accepts_minimal_conjunction_query():
    assert isinstance(validate_ast(_simple_effect_ast()), dict)


def test_schema_accepts_multi_world_conjunction():
    assert isinstance(validate_ast(_fig1_ast()), dict)


def test_schema_rejects_event_without_value():
    ast = _simple_effect_ast()
    del ast["statements"][-1]["query"]["events"][0]["value"]
    with pytest.raises(SyntacticError):
        validate_ast(ast)


def test_schema_rejects_empty_events():
    ast = _ast([_var("x"), _var("y"), _cause("x", "y")], [])
    with pytest.raises(SyntacticError):
        validate_ast(ast)


# ------------------------------------------------------------------ parse
def test_validate_program_parses_typed_query():
    prog = validate_program(validate_ast(_fig1_ast()), checks=frozenset())
    stmt = next(s for s in prog.statements if isinstance(s, QueryStatement))
    assert isinstance(stmt.query, CounterfactualConjunctionQuery)
    assert len(stmt.query.events) == 4
    y_x = stmt.query.events[0]
    assert isinstance(y_x, CounterfactualEvent)
    assert y_x.variable.predicate == "y"
    assert y_x.value is True
    assert y_x.subscript[0].atom.predicate == "x"
    assert y_x.subscript[0].value is True
    # the factual observation x' has an empty world
    assert stmt.query.events[1].subscript == ()


# ------------------------------------------------------------------ round-trip
def test_program_round_trip_preserves_query():
    prog = validate_program(validate_ast(_fig1_ast()), checks=frozenset())
    emitted = _program_to_ast_dict(prog)
    q = next(s for s in emitted["statements"] if s["kind"] == "query")["query"]
    assert q["kind"] == "counterfactual_conjunction"
    assert len(q["events"]) == 4
    prog2 = validate_program(validate_ast(emitted), checks=frozenset())
    assert prog2 == prog


# ------------------------------------------------------------------ run: four states
def test_run_simple_effect_identifiable():
    out = run(_simple_effect_ast())
    r = out["results"][0]
    validate_result(r)
    assert r["query_kind"] == "counterfactual_conjunction"
    assert r["status"] == "structurally_solved"
    # P(Y_{X=1}=1) with no confounding = P(y=T | x=T)
    assert r["formula"]["kind"] == "probability_ref"
    assert r["formula"]["target"]["value"] is True
    assert r["formula"]["given"][0]["value"] is True


def test_run_fig1_worked_example_identifiable():
    out = run(_fig1_ast())
    r = out["results"][0]
    validate_result(r)
    assert r["status"] == "structurally_solved"
    # the estimand is a sum over the summed-out W (Σ_w ...)
    assert r["formula"]["kind"] == "sum"


def test_run_pns_w_graph_non_identifiable():
    out = run(_pns_ast())
    r = out["results"][0]
    validate_result(r)
    assert r["status"] == "needs_investigation"
    assert r["query_kind"] == "counterfactual_conjunction"
    assert any("unidentifiable" in m["name"] for m in r["missing_information"])
    assert "formula" not in r


def test_run_effectiveness_violation_is_zero():
    # x_{x'}: X observed True in a world that fixes X False → P(γ)=0.
    ast = _ast([_var("x"), _var("y"), _cause("x", "y")],
               [_ev("x", [("x", False)], True)])
    r = run(ast)["results"][0]
    validate_result(r)
    assert r["status"] == "structurally_solved"
    assert r["formula"] == {"kind": "constant", "value": 0.0}


def test_run_atom_not_in_graph_rejected_at_validation():
    # γ references a variable with no node in G(M). Like every other query
    # kind, an out-of-graph counterfactual atom is a framing error the
    # semantic validator rejects before scheduling (the scheduler's own
    # missing-atom guard is the same defensive redundancy identify carries).
    ast = _ast([_var("x"), _var("y"), _cause("x", "y")],
               [_ev("q_absent", [("x", True)], True)])
    with pytest.raises(SemanticError):
        run(ast)


# ------------------------------------------------------------------ verify (independent mirror)
def test_verify_accepts_simple_effect():
    ast = _simple_effect_ast()
    r = run(ast)["results"][0]
    themis.verify(ast, r)  # raises on reject


def test_verify_accepts_fig1_worked_example():
    ast = _fig1_ast()
    r = run(ast)["results"][0]
    themis.verify(ast, r)  # the MC probe independently confirms the Σ_w formula


def test_verify_accepts_effectiveness_zero():
    ast = _ast([_var("x"), _var("y"), _cause("x", "y")],
               [_ev("x", [("x", False)], True)])
    r = run(ast)["results"][0]
    themis.verify(ast, r)  # P(γ)=0 is confirmed by the rule (no probe needed)


def test_verify_rejects_tampered_formula():
    """The MC semantic probe has teeth: a formula that passes every
    structural check but computes the wrong number is rejected."""
    ast = _simple_effect_ast()
    r = run(ast)["results"][0]
    tampered = copy.deepcopy(r)
    # Flip the conditioning value: P(y|x=T) → P(y|x=F). Still a well-formed,
    # still-identifiable-looking formula, but the wrong interventional number.
    tampered["formula"]["given"][0]["value"] = False
    tampered["derivation"]["steps"][-1]["inputs"]["formula"]["given"][0]["value"] = False
    with pytest.raises(VerificationError):
        themis.verify(ast, tampered)


def test_verify_rejects_tampered_structural_flag():
    """Claiming P(γ)=0 for a genuinely non-zero conjunction is rejected by
    the id_star_identification rule (engine says inconsistent=False)."""
    ast = _simple_effect_ast()
    r = run(ast)["results"][0]
    tampered = copy.deepcopy(r)
    tampered["formula"] = {"kind": "constant", "value": 0.0}
    tampered["derivation"]["steps"][-1]["inputs"]["formula"] = {
        "kind": "constant", "value": 0.0}
    with pytest.raises(VerificationError):
        themis.verify(ast, tampered)
