"""Regression tests for P1 fixes around identify + given and the
differential coverage-gap report.

Scenarios:

- identify_conditional.json:
  identify(cancer | do(smokes=false), given=[stress])
  where stress is the confounder. The correct behaviour is that
  {stress} as given already blocks every back-door path, so the
  runtime's chosen adjustment sum-set is empty, and the formula is a
  flat P(cancer | smokes=false, stress). In particular the formula
  must NOT contain both ``stress=z`` and an additional conditioning
  on ``stress`` (the pre-fix bug).

- identify_two_var.json:
  identify(cancer | do(smoking)) with two independent confounders
  genetics and social. Minimal adjustment set has cardinality 2,
  which v0.1 formula_builder does not support. Runtime must surface
  a NEEDS_INVESTIGATION result with a formula:joint_adjustment
  missing item. The differential comparator must NOT report agree
  for this query — it must report ``not_applicable`` with a reason
  that names the coverage gap, so CI sees the gap instead of a
  false green.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from causal_kernel.input.parser import parse_json
from causal_kernel.input.semantic_validator import validate_formula, validate_program
from causal_kernel.input.syntactic_validator import validate_ast
from causal_kernel.oracle.differential import compare
from causal_kernel.oracle.pgmpy_adapter import build_network
from causal_kernel.runtime.graph_projection import project
from causal_kernel.runtime.instantiation import instantiate
from causal_kernel.runtime.scheduler import dispatch_all
from causal_kernel.types import (
    ProbabilityRefExpr,
    QueryKind,
    QueryStatement,
    ResultStatus,
    SumExpr,
)

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _load(name: str):
    path = FIXTURES_DIR / name
    ast = parse_json(path.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    network = build_network(program)
    return program, graph, results, network


# -------------------------------------------------------- conditional fix

def test_conditional_identify_picks_empty_sum_when_given_suffices():
    _, _, results, _ = _load("identify_conditional.json")
    r = results["identify_given_is_adjustment"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.query_kind is QueryKind.IDENTIFY
    assert r.structural_result.value is True
    # Because given={stress} already blocks the only back-door path,
    # the formula degenerates to a flat probability_ref.
    assert isinstance(r.formula, ProbabilityRefExpr)


def test_conditional_identify_formula_is_wellformed_and_has_no_overlap():
    _, _, results, _ = _load("identify_conditional.json")
    r = results["identify_given_is_adjustment"]
    validate_formula(r.formula)
    # The given atom stress(alice) appears once, with value=None
    # (query-bound), and never with a VarRef simultaneously.
    assert isinstance(r.formula, ProbabilityRefExpr)
    stress_entries = [
        g for g in r.formula.given if g.atom.predicate == "stress"
    ]
    assert len(stress_entries) == 1
    assert stress_entries[0].value is None


def test_conditional_identify_differential_agrees():
    program, _, results, network = _load("identify_conditional.json")
    for stmt in program.statements:
        if isinstance(stmt, QueryStatement):
            report = compare(stmt, results[stmt.id], network)
            assert report.status == "agree", (stmt.id, report.reason)


# --------------------------------------------------------- two-var identify

def test_two_var_adjustment_is_identifiable_via_nested_sums():
    """Slice 5 extension: |Z|=2 now builds a well-formed nested-sum
    formula via chain rule, no longer a coverage gap."""
    _, _, results, _ = _load("identify_two_var.json")
    r = results["identify_needs_two_adjustments"]
    assert r.status is ResultStatus.STRUCTURALLY_SOLVED
    assert r.structural_result.value is True
    assert r.formula is not None

    # Outer node is a SumExpr wrapping another SumExpr — two nested
    # binders for the two adjustment variables.
    assert isinstance(r.formula, SumExpr)
    assert isinstance(r.formula.body, SumExpr)

    outer_over = r.formula.over.predicate
    inner_over = r.formula.body.over.predicate
    assert {outer_over, inner_over} == {"genetics", "social"}

    validate_formula(r.formula)


def test_two_var_differential_now_agrees():
    """With the multi-var builder landed, the comparator should report
    agree instead of the previous slice-4 coverage-gap not_applicable."""
    program, _, results, network = _load("identify_two_var.json")
    stmt = next(
        s for s in program.statements
        if isinstance(s, QueryStatement)
        and s.id == "identify_needs_two_adjustments"
    )
    report = compare(stmt, results[stmt.id], network)
    assert report.status == "agree", report


# ------------------------------------------------------------------ unit

def test_minimal_adjustment_sets_respects_given():
    """Unit-level: feeding stress via `given` changes the chosen sum."""
    from causal_kernel.runtime.structural_solver import minimal_adjustment_sets
    from causal_kernel.types import Atom, ConstTerm
    import networkx as nx

    stress = Atom(predicate="stress", args=(ConstTerm(name="alice"),))
    smokes = Atom(predicate="smokes", args=(ConstTerm(name="alice"),))
    cancer = Atom(predicate="cancer", args=(ConstTerm(name="alice"),))

    g: nx.DiGraph = nx.DiGraph()
    g.add_edge(stress, smokes)
    g.add_edge(stress, cancer)
    g.add_edge(smokes, cancer)

    # Without given, the unique minimal set is {stress}.
    without = minimal_adjustment_sets(g, smokes, cancer)
    assert frozenset({stress}) in without

    # With given=(stress,), the empty set is now sufficient.
    with_given = minimal_adjustment_sets(g, smokes, cancer, given=(stress,))
    assert with_given == (frozenset(),)


def test_minimal_adjustment_sets_rejects_given_descendant_of_x():
    """A given containing a descendant of X violates the back-door
    precondition; function must return ()."""
    from causal_kernel.runtime.structural_solver import minimal_adjustment_sets
    from causal_kernel.types import Atom, ConstTerm
    import networkx as nx

    x = Atom(predicate="x", args=(ConstTerm(name="a"),))
    m = Atom(predicate="m", args=(ConstTerm(name="a"),))
    y = Atom(predicate="y", args=(ConstTerm(name="a"),))
    g: nx.DiGraph = nx.DiGraph()
    g.add_edge(x, m)
    g.add_edge(m, y)

    sets = minimal_adjustment_sets(g, x, y, given=(m,))
    assert sets == ()
