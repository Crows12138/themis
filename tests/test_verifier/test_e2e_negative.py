"""V3 e2e coverage: negative structural results shipped in existing
fixtures produce accepted derivations.

The current repo has three negative assoc results in
``assoc_canonical.json`` (chain_blocked / fork_blocked /
collider_closed). There are no negative identify or negative cause
results in any fixture, so those cases are covered only by the unit
tests (``test_negative_rules.py``). This file pins what we have.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    QueryKind,
    QueryStatement,
    StructuralResult,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_assoc,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "test_e2e" / "fixtures"


def _run(path: Path):
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    return graph, results, stmt_by_id


def _assoc_negatives(results):
    return [
        r for r in results
        if r.query_kind is QueryKind.ASSOC
        and r.structural_result is not None
        and r.structural_result.value is False
    ]


def test_every_assoc_negative_has_accepted_derivation():
    path = FIXTURE_DIR / "assoc_canonical.json"
    graph, results, stmt_by_id = _run(path)
    negatives = _assoc_negatives(results)
    assert negatives, "fixture unexpectedly has no negative assoc queries"

    for r in negatives:
        assert r.derivation, f"{r.query_id}: missing derivation"
        assert r.derivation[-1].rule == "d_separated"
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        verify_assoc(r.derivation, ctx, r.structural_result)


def test_tampering_d_separated_output_is_rejected():
    """Flipping the d_separated step's output to True (claiming
    d-connected, which contradicts the proof) must be rejected."""
    path = FIXTURE_DIR / "assoc_canonical.json"
    graph, results, stmt_by_id = _run(path)
    negatives = _assoc_negatives(results)

    for r in negatives:
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        bad = list(r.derivation)
        bad[0] = replace(bad[0], output=StructuralResult(value=True))
        with pytest.raises(VerificationError):
            # The rule will complain that output.value must be False;
            # verify_assoc's final-output check would also catch it.
            verify_assoc(tuple(bad), ctx, r.structural_result)


def test_tampering_d_separated_swaps_x_and_y_is_rejected_by_binding():
    """Swapping the step's x and y against the query must be caught by
    the query binding check."""
    path = FIXTURE_DIR / "assoc_canonical.json"
    graph, results, stmt_by_id = _run(path)
    negatives = _assoc_negatives(results)

    for r in negatives:
        step = r.derivation[0]
        original_x = step.inputs["x"]
        original_y = step.inputs["y"]
        if original_x == original_y:
            continue
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        bad = list(r.derivation)
        bad[0] = replace(
            bad[0],
            inputs={**bad[0].inputs, "x": original_y, "y": original_x},
        )
        with pytest.raises(VerificationError, match="does not match"):
            verify_assoc(tuple(bad), ctx, r.structural_result)


def test_positive_assoc_now_carries_witness_derivation():
    """V4 added d_connected_via_open_path, so every positive assoc
    result now carries a one-step derivation whose output matches
    the QueryResult's structural_result."""
    path = FIXTURE_DIR / "assoc_canonical.json"
    _graph, results, _stmt_by_id = _run(path)
    positives = [
        r for r in results
        if r.query_kind is QueryKind.ASSOC
        and r.structural_result is not None
        and r.structural_result.value is True
    ]
    assert positives, "fixture has no positive assoc query to cover"
    for r in positives:
        assert r.derivation
        assert r.derivation[-1].rule == "d_connected_via_open_path"
