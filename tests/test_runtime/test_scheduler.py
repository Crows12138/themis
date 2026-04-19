"""Regression tests for scheduler dispatch completeness.

The four-state contract says every in-language query must surface a
result. Slice-1 must not silently drop queries whose solver is not
yet implemented.
"""
from __future__ import annotations

from pathlib import Path

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import QueryKind, QueryStatement, ResultStatus

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = PROJECT_ROOT / "minimal_example_v0_1.json"


def test_dispatch_all_returns_one_result_per_query() -> None:
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))

    queries = [s for s in program.statements if isinstance(s, QueryStatement)]
    results = dispatch_all(program, graph)

    assert len(results) == len(queries), (
        "dispatch_all must return one result per query statement, "
        "never silently drop unsupported kinds"
    )

    ids = [r.query_id for r in results]
    assert ids == [q.id for q in queries]


def test_all_query_kinds_surface_results() -> None:
    """Every in-language query produces a result (never silently dropped)."""
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    by_id = {r.query_id: r for r in dispatch_all(program, graph)}

    # cause and identify resolve structurally.
    assert by_id["q_cause_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_cause_1"].query_kind is QueryKind.CAUSE
    assert by_id["q_identify_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_identify_1"].query_kind is QueryKind.IDENTIFY

    # effect and probability now run through the numeric dispatch paths
    # but land on needs_investigation because Theta is empty in v0.1.
    # Missing info must point at the specific conditional probability
    # the evaluator could not resolve.
    for qid, expected_kind in [
        ("q_prob_1", QueryKind.PROBABILITY),
        ("q_effect_1", QueryKind.EFFECT),
    ]:
        r = by_id[qid]
        assert r.status is ResultStatus.NEEDS_INVESTIGATION, (
            f"{qid} should be needs_investigation, got {r.status}"
        )
        assert r.query_kind is expected_kind
        assert r.missing_information, f"{qid} missing_information must be non-empty"
        assert any(
            m.name.startswith("parameter:") or m.name.startswith("numeric:")
            for m in r.missing_information
        ), [m.name for m in r.missing_information]


def test_needs_investigation_auto_populates_investigation_requests() -> None:
    """Any needs_investigation result with missing_information should
    carry matching investigation_requests pushed by the runtime."""
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    for r in dispatch_all(program, graph):
        if r.status is ResultStatus.NEEDS_INVESTIGATION and r.missing_information:
            assert r.investigation_requests, (
                f"{r.query_id}: missing_information present but no "
                f"investigation_requests attached"
            )
            assert len(r.investigation_requests) == len(r.missing_information)


def test_missing_parameter_formatter_handles_non_empty_given() -> None:
    """Regression: _missing_parameter_from_key previously projected
    (Atom, value) -> (predicate, value) before sorting and then tried
    to call .predicate on the projected string, crashing with
    AttributeError on any conditional lookup."""
    from themis.runtime.scheduler import _missing_parameter_from_key
    from themis.runtime.numeric_estimator import ProbabilityKey
    from themis.types import Atom, ConstTerm, MissingKind

    y = Atom(predicate="y", args=(ConstTerm(name="a"),))
    x1 = Atom(predicate="x1", args=(ConstTerm(name="a"),))
    x2 = Atom(predicate="x2", args=(ConstTerm(name="a"),))
    key = ProbabilityKey(
        target_atom=y,
        target_value=True,
        given=frozenset({(x1, True), (x2, False)}),
    )
    item = _missing_parameter_from_key(key, "theta lookup failed")
    assert item.kind is MissingKind.PARAMETER
    # Both atoms appear in the formatted name, sorted by predicate.
    assert "x1=True" in item.name
    assert "x2=False" in item.name
    assert item.name.startswith("parameter:P(y=True|")


def test_confidence_is_routed_through_composite_even_when_none() -> None:
    """confidence_calc.composite must be on the dispatch path. The
    spy below verifies it was called for every query; v0.1 yields
    None (no inputs), but the wiring is live."""
    from unittest.mock import patch

    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    with patch(
        "themis.runtime.scheduler.confidence_calc.composite",
        wraps=__import__(
            "themis.runtime.confidence_calc",
            fromlist=["composite"],
        ).composite,
    ) as spy:
        results = dispatch_all(program, graph)

    # One call per dispatched query.
    num_queries = sum(
        1 for s in program.statements
        if s.__class__.__name__ == "QueryStatement"
    )
    assert spy.call_count == num_queries
    # In v0.1 every result still serializes with confidence=None.
    assert all(r.confidence is None for r in results)
