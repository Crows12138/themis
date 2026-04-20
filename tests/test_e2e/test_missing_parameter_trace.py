"""End-to-end regression for 试跑案例 2: parameter-gap edge path.

Fixture: stress -> smokes, stress -> cancer, smokes -> cancer
with probability statements that deliberately OMIT one CPT entry:

    declared:
        P(cancer=true | smokes=false, stress=true)   = 0.3
        P(stress=true)                               = 0.4
        P(stress=false)                              = 0.6
    MISSING:
        P(cancer=true | smokes=false, stress=false)

Query: effect(cancer=true | do(smokes=false))

The back-door identification still succeeds ({stress} blocks the
back-door path), so a formula is produced. Numeric evaluation then
iterates stress over {True, False} and fails on the False branch
because that conditional is not in Theta.

This case is what motivates v0.2 Slice 9 (confidence / data entry /
investigation advancement). Pinning the full needs_investigation
envelope here means any future slice that changes how missing
parameters surface must update this test explicitly, rather than
silently degrading the diagnostic quality.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast, validate_result
from themis.output.result_orchestrator import to_dict
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    InvestigationAction,
    MissingKind,
    Priority,
    QueryKind,
    ResultStatus,
    SumExpr,
)

FIXTURE = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "numeric_backdoor_missing_parameter.json"
)


@pytest.fixture(scope="module")
def result():
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    graph = project(instantiate(program))
    results = {r.query_id: r for r in dispatch_all(program, graph)}
    return results["effect_cancer_missing_theta"]


# -------------------------------------------------- four-state verdict

def test_status_is_needs_investigation(result):
    assert result.status is ResultStatus.NEEDS_INVESTIGATION
    assert result.query_kind is QueryKind.EFFECT


def test_numeric_result_is_absent(result):
    """Numeric dispatch aborted mid-evaluation; there is no value."""
    assert result.numeric_result is None


def test_formula_is_still_emitted(result):
    """Structural identification succeeded before numeric failed, so
    the caller still sees the back-door formula they are trying to
    fill Theta for."""
    assert result.formula is not None
    # Single confounder {stress} -> outer SumExpr over stress(alice).
    assert isinstance(result.formula, SumExpr)
    assert result.formula.over.predicate == "stress"


# ------------------------------------------------- missing-parameter trace

def test_missing_information_points_at_exact_conditional(result):
    """The missing item must name the specific CPT entry the user
    needs to supply — not a generic 'parameter missing' message."""
    assert len(result.missing_information) == 1
    m = result.missing_information[0]
    assert m.kind is MissingKind.PARAMETER
    assert m.priority is Priority.HIGH

    # Name format: parameter:P(<target>=<val>|<given1>=<val1>,...)
    # Given atoms are sorted by (type, str(value)) so the order is
    # stable: smokes=False before stress=False.
    assert m.name == "parameter:P(cancer=True|smokes=False,stress=False)"


def test_missing_information_reason_explains_theta_lookup_failure(result):
    """The reason text should explicitly mention Theta / missing
    entry, so the user can trace the failure back to the
    InsufficientTheta channel without reading source."""
    m = result.missing_information[0]
    assert m.reason is not None
    assert "Theta" in m.reason


# ------------------------------------------------- investigation request

def test_investigation_request_is_attached(result):
    """needs_investigation results must carry at least one
    investigation request (pushed from missing_information)."""
    assert len(result.investigation_requests) == 1


def test_investigation_request_is_validate_parameter(result):
    """MissingKind.PARAMETER maps to InvestigationAction.VALIDATE_PARAMETER
    per investigation_pusher. The target string is the missing item
    name so the caller can directly refer back."""
    req = result.investigation_requests[0]
    assert req.action is InvestigationAction.VALIDATE_PARAMETER
    assert req.priority is Priority.HIGH
    assert req.target == "parameter:P(cancer=True|smokes=False,stress=False)"


# ----------------------------------------------------------- schema round-trip

def test_result_round_trips_through_query_result_schema(result):
    payload = to_dict(result)
    validate_result(payload)
    assert payload["status"] == "needs_investigation"
    assert payload["query_kind"] == "effect"
    # Formula is still present even in the missing-parameter case.
    assert "formula" in payload
    # Missing info and investigation are both serialized.
    assert len(payload["missing_information"]) == 1
    assert len(payload["investigation_requests"]) == 1


# ------------------------------------------------------ slice 8.2 explainer

def test_missing_parameter_explanation_names_the_gap(result):
    """The effect explainer must:
    1. acknowledge that the query is identifiable (formula exists),
    2. name the adjustment set that identifies it, and
    3. list the exact missing parameter by its structured name.

    Before slice 8.2 the explainer raised NotImplementedError on
    effect results, so this path had no user-facing surface at all."""
    from pathlib import Path
    from themis.input.parser import parse_json
    from themis.input.semantic_validator import validate_program
    from themis.input.syntactic_validator import validate_ast
    from themis.output.explainer import explain
    from themis.types import QueryStatement

    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    program = validate_program(ast)
    stmt = next(
        s for s in program.statements
        if isinstance(s, QueryStatement)
        and s.id == "effect_cancer_missing_theta"
    )
    text = explain(result, stmt=stmt)

    # (1) identifiable acknowledgment + (2) adjustment set
    assert "可识别" in text
    assert "stress(alice)" in text
    # (3) exact missing parameter is surfaced, not abbreviated
    assert "parameter:P(cancer=True|smokes=False,stress=False)" in text
