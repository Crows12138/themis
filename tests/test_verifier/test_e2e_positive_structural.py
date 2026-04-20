"""V4 e2e: positive structural witnesses.

- Every positive assoc result from ``assoc_canonical.json`` produces a
  ``d_connected_via_open_path`` witness the verifier accepts.
- The derivation round-trips through JSON (V2) and still verifies.
- Tampering with the witness path is rejected.

There is currently no shipped fixture with a positive cause query, so
``cause_via_directed_path`` is exercised only via the unit tests in
``test_positive_rules.py``.
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
from themis.types import QueryKind, QueryStatement
from themis.verifier import (
    VerificationContext,
    VerificationError,
    derivation_from_dict,
    derivation_to_dict,
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


def _positive_assoc(results):
    return [
        r for r in results
        if r.query_kind is QueryKind.ASSOC
        and r.structural_result is not None
        and r.structural_result.value is True
    ]


def test_positive_assoc_fixtures_verify():
    graph, results, stmt_by_id = _run(FIXTURE_DIR / "assoc_canonical.json")
    positives = _positive_assoc(results)
    assert positives, "fixture has no positive assoc queries"

    for r in positives:
        assert r.derivation, f"{r.query_id}: missing derivation"
        assert r.derivation[-1].rule == "d_connected_via_open_path"
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        verify_assoc(r.derivation, ctx, r.structural_result)


def test_positive_assoc_derivation_round_trips():
    graph, results, stmt_by_id = _run(FIXTURE_DIR / "assoc_canonical.json")
    for r in _positive_assoc(results):
        payload = derivation_to_dict(r.derivation)
        back = derivation_from_dict(payload)
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        verify_assoc(back, ctx, r.structural_result)


def test_tampering_positive_assoc_paths_is_rejected():
    """Swapping the witness paths for something truncated must be
    rejected by the rule (supporting_paths mismatch or missing edge)."""
    graph, results, stmt_by_id = _run(FIXTURE_DIR / "assoc_canonical.json")
    for r in _positive_assoc(results):
        ctx = VerificationContext(graph=graph, query=stmt_by_id[r.query_id].query)
        bad = list(r.derivation)
        step = bad[0]
        original_paths = step.inputs["paths"]
        # Truncate each path to [x, y] — direct edge, which likely isn't
        # in the graph (positive assoc fixtures usually have longer paths).
        x = step.inputs["x"]
        y = step.inputs["y"]
        trimmed_paths = tuple((x, y) for _ in original_paths)
        bad[0] = replace(step, inputs={**step.inputs, "paths": trimmed_paths})
        with pytest.raises(VerificationError):
            verify_assoc(tuple(bad), ctx, r.structural_result)
