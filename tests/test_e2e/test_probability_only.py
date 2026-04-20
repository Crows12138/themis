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


# ----------------------------------------------------- slice 8.2 explainer

def test_probability_success_explanation_quotes_target_and_value():
    """Slice 8.2: probability explainer must render
    P(target=val | given=val, ...) and the numeric answer."""
    from themis.output.explainer import explain
    from themis.types import QueryStatement

    path = FIXTURES / "probability_no_graph.json"
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    stmt = next(
        s for s in program.statements
        if isinstance(s, QueryStatement) and s.id == "prob_coin_true"
    )
    text = explain(results["prob_coin_true"], stmt=stmt)

    assert "coin(a)" in text
    assert "0.7" in text
    # P(...) surface: probability queries render as P(target=value[|given])
    assert text.startswith("P(")


def test_probability_missing_parameter_explanation_lists_gap():
    """When a probability query's Theta entry is absent, the explainer
    must say so and name the missing parameter."""
    from themis.output.explainer import explain
    from themis.types import (
        Atom,
        ConstTerm,
        ProbabilityQuery,
        Program,
        QueryStatement,
        ValuedAtom,
    )
    from themis.runtime.graph_projection import project as _project
    from themis.runtime.instantiation import instantiate as _inst

    # Tiny synthetic program: empty Theta, one probability query.
    coin = Atom(predicate="coin", args=(ConstTerm(name="a"),))
    program = Program(
        version="0.1",
        objects=("a",),
        statements=(
            QueryStatement(
                id="q",
                query=ProbabilityQuery(
                    target=ValuedAtom(atom=coin, value=True),
                    given=(),
                ),
            ),
        ),
    )
    graph = _project(_inst(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    r = results["q"]

    assert r.status is ResultStatus.NEEDS_INVESTIGATION
    stmt = program.statements[0]
    text = explain(r, stmt=stmt)
    assert "coin(a)" in text
    assert "无法计算" in text or "缺参数" in text
    # The structured missing-parameter name should appear verbatim.
    assert any(m.name in text for m in r.missing_information)
