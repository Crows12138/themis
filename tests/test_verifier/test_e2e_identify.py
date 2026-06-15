"""End-to-end verifier coverage: every identify fixture shipped in the
repo must produce a derivation that the verifier accepts, and
tampering with a real derivation must produce a reject.

This closes the V0 loop: elaborator (scheduler / formula_builder /
structural_solver) produces the derivation; verifier independently
confirms it.
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
    IdentifyQuery,
    Intervention,
    ProbabilityRefExpr,
    QueryKind,
    QueryStatement,
    StructuralResult,
)
from themis.verifier import (
    VerificationContext,
    VerificationError,
    verify_identify,
)

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "test_e2e" / "fixtures"

# Fixtures that contain at least one identify query with value=True.
IDENTIFY_FIXTURES = [
    FIXTURE_DIR / "identify_backdoor.json",
    FIXTURE_DIR / "identify_conditional.json",
    FIXTURE_DIR / "identify_two_var.json",
]


def _run_and_verify(path: Path):
    ast = parse_json(path.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    graph = project(instantiate(program))
    results = dispatch_all(program, graph)
    stmt_by_id = {
        s.id: s for s in program.statements if isinstance(s, QueryStatement)
    }
    return program, graph, results, stmt_by_id


@pytest.mark.parametrize("fixture", IDENTIFY_FIXTURES, ids=lambda p: p.name)
def test_verifier_accepts_every_positive_identify_derivation(fixture):
    """For every identify query that returned value=True, the attached
    derivation must be non-empty and pass verify_identify."""
    _, graph, results, stmt_by_id = _run_and_verify(fixture)
    identify_positive = [
        r for r in results
        if r.query_kind is QueryKind.IDENTIFY
        and r.structural_result is not None
        and r.structural_result.value is True
    ]
    assert identify_positive, f"fixture {fixture.name} has no positive identify"

    for r in identify_positive:
        assert r.derivation, f"{r.query_id}: missing derivation"
        ctx = VerificationContext(
            graph=graph, query=stmt_by_id[r.query_id].query
        )
        verify_identify(r.derivation, ctx, r.structural_result)


@pytest.mark.parametrize("fixture", IDENTIFY_FIXTURES, ids=lambda p: p.name)
def test_tampering_criterion_output_is_rejected(fixture):
    """Flipping the engine's decomposition / exchange step output to False
    must be rejected (the rule checks the step proved True). Phase 15B:
    the point-ID engine is Tian / IDC, so the load-bearing first step is
    tian_c_decomposition / idc_rule2_exchange (backdoor_criterion on the
    legacy path)."""
    _GATE_RULES = (
        "tian_c_decomposition", "idc_rule2_exchange", "backdoor_criterion",
    )
    _, graph, results, stmt_by_id = _run_and_verify(fixture)
    for r in results:
        if (
            r.query_kind is not QueryKind.IDENTIFY
            or r.structural_result is None
            or r.structural_result.value is not True
        ):
            continue
        ctx = VerificationContext(
            graph=graph, query=stmt_by_id[r.query_id].query
        )
        # Find the engine's gate step and flip its output to False.
        bad = list(r.derivation)
        tampered = False
        for i, step in enumerate(bad):
            if step.rule in _GATE_RULES:
                bad[i] = replace(step, output=False)
                tampered = True
                break
        assert tampered, f"{r.query_id}: no gate step to tamper"
        with pytest.raises(VerificationError):
            verify_identify(tuple(bad), ctx, r.structural_result)


@pytest.mark.parametrize("fixture", IDENTIFY_FIXTURES, ids=lambda p: p.name)
def test_tampering_formula_is_rejected(fixture):
    """Swapping the adjustment formula step's output for a naive
    conditional must be rejected by R4."""
    _, graph, results, stmt_by_id = _run_and_verify(fixture)
    for r in results:
        if (
            r.query_kind is not QueryKind.IDENTIFY
            or r.structural_result is None
            or r.structural_result.value is not True
        ):
            continue
        ctx = VerificationContext(
            graph=graph, query=stmt_by_id[r.query_id].query
        )
        bad = list(r.derivation)
        tampered = False
        for i, step in enumerate(bad):
            if step.rule != "backdoor_adjustment_formula":
                continue
            if not step.inputs["z"]:
                # Empty Z → formula is already just P(target | ...);
                # swapping to the same shape wouldn't tamper anything.
                break
            target = step.inputs["target"]
            intervention = step.inputs["intervention"]
            observed = step.inputs.get("given", ())
            naive = ProbabilityRefExpr(
                target=target,
                given=(intervention,) + observed,
            )
            bad[i] = replace(step, output=naive)
            tampered = True
            break
        if not tampered:
            continue
        with pytest.raises(VerificationError):
            verify_identify(tuple(bad), ctx, r.structural_result)


@pytest.mark.parametrize("fixture", IDENTIFY_FIXTURES, ids=lambda p: p.name)
def test_verifier_rejects_derivation_for_different_query_on_same_graph(fixture):
    """A derivation must prove the active identify query, not merely
    some other query on the same graph."""
    _, graph, results, stmt_by_id = _run_and_verify(fixture)
    for r in results:
        if (
            r.query_kind is not QueryKind.IDENTIFY
            or r.structural_result is None
            or r.structural_result.value is not True
        ):
            continue

        stmt = stmt_by_id[r.query_id]
        original = stmt.query
        alt_target = next(
            atom for atom in graph.nodes
            if atom != original.target and atom != original.intervention.atom
        )
        wrong_query = IdentifyQuery(
            target=alt_target,
            intervention=Intervention(
                atom=original.intervention.atom,
                value=original.intervention.value,
            ),
            given=original.given,
        )
        ctx = VerificationContext(graph=graph, query=wrong_query)

        with pytest.raises(VerificationError, match="does not match verification context query"):
            verify_identify(r.derivation, ctx, r.structural_result)


def test_positive_cause_and_assoc_now_carry_witness_derivations():
    """V4 added cause_via_directed_path / d_connected_via_open_path.
    Every positive cause and positive assoc that references graph-
    resident atoms now carries a single-step witness derivation."""
    from themis.types import QueryKind as _QK

    path = FIXTURE_DIR / "numeric_backdoor.json"
    _, _, results, _ = _run_and_verify(path)
    for r in results:
        if r.query_kind not in (_QK.CAUSE, _QK.ASSOC):
            continue
        if r.structural_result is None or r.structural_result.value is not True:
            continue
        assert r.derivation, (
            f"positive {r.query_id} ({r.query_kind.value}) should carry "
            f"a witness derivation under V4"
        )
        expected_rule = (
            "cause_via_directed_path"
            if r.query_kind is _QK.CAUSE
            else "d_connected_via_open_path"
        )
        assert r.derivation[-1].rule == expected_rule
