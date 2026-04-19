"""Regression tests for P1 fixes: probability queries must not be
gated on causal-DAG membership, and Theta must infer categorical
value domains from the statements themselves.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.runtime.theta_builder import build_theta_from_program
from themis.types import QueryKind, ResultStatus

FIXTURES = Path(__file__).resolve().parent / "fixtures"


# --------------------------------------------- P1-A: pure probability program

def test_probability_query_answered_without_any_cause_edges():
    """A program consisting only of probability statements and a
    probability query must still be able to answer numerically.

    Before the fix, ``_dispatch_probability`` rejected the query
    because neither atom appeared in the (empty) causal DAG."""
    path = FIXTURES / "probability_no_graph.json"
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))
    # The DAG is empty here — no cause statements.
    assert graph.number_of_edges() == 0

    results = {r.query_id: r for r in dispatch_all(program, graph)}
    r = results["prob_coin_true"]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED
    assert r.query_kind is QueryKind.PROBABILITY
    assert r.numeric_result.value == pytest.approx(0.7)


# --------------------------------------------- P1-B: categorical value domain

def test_theta_domains_inferred_from_statements():
    """String-valued confounders should appear in Theta.domains so the
    back-door evaluator iterates over {high, low} rather than the
    boolean default."""
    path = FIXTURES / "numeric_categorical.json"
    program = validate_program(
        validate_ast(parse_json(path.read_text(encoding="utf-8")))
    )
    theta = build_theta_from_program(program)

    stress_domains = {
        atom: values for atom, values in theta.domains.items()
        if atom.predicate == "stress"
    }
    assert stress_domains, "stress domain not inferred"
    (stress_values,) = stress_domains.values()
    assert set(stress_values) == {"high", "low"}


def test_categorical_backdoor_numeric_matches_hand_compute():
    """Back-door adjustment over a categorical confounder:

        ∑_z P(cancer=true|smokes=false, stress=z) · P(stress=z)
      = 0.4 · 0.25 + 0.1 · 0.75
      = 0.10 + 0.075
      = 0.175

    Before the fix, the sum was silently iterating over (True, False)
    instead of (high, low), yielding needs_investigation because
    P(cancer|smokes=false, stress=True) doesn't exist in Theta.
    """
    path = FIXTURES / "numeric_categorical.json"
    program = validate_program(
        validate_ast(parse_json(path.read_text(encoding="utf-8")))
    )
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    r = results["effect_cancer_categorical"]
    assert r.status is ResultStatus.NUMERICALLY_SOLVED, (
        f"unexpected needs_investigation with missing={r.missing_information}"
    )
    assert r.numeric_result.value == pytest.approx(0.175)
