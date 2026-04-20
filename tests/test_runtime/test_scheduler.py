"""Regression tests for scheduler dispatch completeness.

The four-state contract says every in-language query must surface a
result. Slice-1 must not silently drop queries whose solver is not
yet implemented.
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
from themis.types import (
    Atom,
    CauseStatement,
    ConstTerm,
    IdentifyQuery,
    Intervention,
    MissingKind,
    Program,
    QueryKind,
    QueryStatement,
    ResultStatus,
)

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
    """Every in-language query produces a result (never silently dropped).

    After slice 6 the numeric dispatch paths consult a real Theta built
    from the program's probability statements. For minimal_example:

    - q_prob_1 asks P(cancer=true | tar=true), which is exactly the
      declared CPT entry → NUMERICALLY_SOLVED with value 0.2.
    - q_effect_1 needs P(cancer=true | smokes=false); Theta has no
      such entry → NEEDS_INVESTIGATION with a precise missing parameter.
    - cause / identify stay structural as before.
    """
    ast = parse_json(EXAMPLE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))

    by_id = {r.query_id: r for r in dispatch_all(program, graph)}

    assert by_id["q_cause_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_cause_1"].query_kind is QueryKind.CAUSE
    assert by_id["q_identify_1"].status is ResultStatus.STRUCTURALLY_SOLVED
    assert by_id["q_identify_1"].query_kind is QueryKind.IDENTIFY

    r_prob = by_id["q_prob_1"]
    assert r_prob.status is ResultStatus.NUMERICALLY_SOLVED
    assert r_prob.query_kind is QueryKind.PROBABILITY
    assert r_prob.numeric_result is not None
    assert r_prob.numeric_result.value == 0.2

    r_effect = by_id["q_effect_1"]
    assert r_effect.status is ResultStatus.NEEDS_INVESTIGATION
    assert r_effect.query_kind is QueryKind.EFFECT
    assert r_effect.missing_information
    assert any(
        m.name.startswith("parameter:") or m.name.startswith("numeric:")
        for m in r_effect.missing_information
    ), [m.name for m in r_effect.missing_information]


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


def test_confidence_is_routed_through_composite_for_every_query() -> None:
    """confidence_calc.composite must be on the dispatch path for
    every query. Structural queries contribute no inputs so their
    composite is None; numeric queries that match an annotated source
    inherit the slot confidence per RFC §3.3."""
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

    by_id = {r.query_id: r for r in results}

    # Structural queries always contribute nothing -> None composite.
    assert by_id["q_cause_1"].confidence is None
    assert by_id["q_identify_1"].confidence is None

    # minimal_example_v0_1.json's probability statement carries
    # annotations.confidence = 0.82 on P(cancer=true | tar=true).
    # q_prob_1 asks exactly that conditional, so slice-9 collection
    # feeds 0.82 into composite -> 0.82.
    assert by_id["q_prob_1"].confidence == pytest.approx(0.82)

    # q_effect_1 asks P(cancer=true | do(smokes=false)); the back-door
    # formula references P(cancer=true | smokes=false) which has no
    # source statement in the fixture -> no slot -> None.
    assert by_id["q_effect_1"].confidence is None


def test_identify_invalid_given_descendant_is_not_emitted_as_negative_proof() -> None:
    """Regression for V3: a `given` that violates backdoor
    preconditions (descendant of X) must not surface as a
    structurally-solved negative identify proof, because the verifier
    correctly rejects `unidentifiable_via_backdoor` on that context."""

    def atom(pred: str) -> Atom:
        return Atom(predicate=pred, args=(ConstTerm(name="me"),))

    x = atom("x")
    z = atom("z")
    y = atom("y")
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            CauseStatement(from_atom=x, to_atom=z),
            CauseStatement(from_atom=z, to_atom=y),
            QueryStatement(
                id="q_invalid_given",
                query=IdentifyQuery(
                    target=y,
                    intervention=Intervention(atom=x, value=True),
                    given=(z,),
                ),
            ),
        ),
    )
    graph = project(instantiate(program))
    result = dispatch_all(program, graph)[0]

    assert result.status is ResultStatus.NEEDS_INVESTIGATION
    assert result.query_kind is QueryKind.IDENTIFY
    assert result.derivation == ()
    assert result.structural_result is None
    assert result.missing_information
    assert result.missing_information[0].kind is MissingKind.STRUCTURE
    assert "violates backdoor pre-conditions" in result.missing_information[0].reason
