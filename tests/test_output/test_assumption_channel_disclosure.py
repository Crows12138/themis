"""The assumption channel has to reach the data-gap report.

``MissingKind.ASSUMPTION`` items are the kernel's way of saying "this
identification needs something the data cannot decide". They travel as
``investigation_requests`` under ``group == "assumption"``. The gap
report is the surface where a consumer reads what is missing and what
to do about it, so an item that never becomes a gap is only reachable
by a reader who walks the raw missing-information channel themselves.

These tests go through ``themis.run`` rather than constructing a
``QueryResult`` by hand. A hand-built result can carry a status the
kernel never produces, which is exactly how the classifier came to be
keyed on ``ResultStatus.NEEDS_ASSUMPTION`` — a proxy that lost its last
producer — and stayed green while emitting nothing.
"""
from __future__ import annotations

import pytest

import themis
from themis import kernel


# ---------------------------------------------------------------------------
# Programs whose assumption items differ in kind: an undeclared premise,
# a degenerate instrument, and inputs that contradict each other.
# ---------------------------------------------------------------------------


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _gr(p: str, value) -> dict:
    return {"atom": _atom(p), "value": value}


def _prob(target_pred, target_v, given_pairs, value) -> dict:
    return {
        "kind": "probability",
        "target": _gr(target_pred, target_v),
        "given": [_gr(p, v) for p, v in given_pairs],
        "value": value,
    }


def _iv_program(*, monotonicity: str | None, p_x_given_z1: float = 0.8) -> dict:
    """Z → X → Y with a latent X ↔ Y. Backdoor and front-door both fail;
    the instrument reaches the effect but not without an estimator
    choice."""
    stmts = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _prob("y", True, [("z", True)], 0.7),
        _prob("y", True, [("z", False)], 0.3),
        _prob("x", True, [("z", True)], p_x_given_z1),
        _prob("x", True, [("z", False)], 0.2),
    ]
    query: dict = {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": _gr("y", True),
        "given": [],
    }
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    stmts.append({"kind": "query", "id": "q", "query": query})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


_CX = {"predicate": "drug", "args": [{"type": "const", "name": "p"}]}
_CY = {"predicate": "death", "args": [{"type": "const", "name": "p"}]}


def _causation_program(query: dict, *, p_x1=0.5, py_x1=0.2, py_x0=0.1) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": _CX, "to": _CY},
            {"kind": "bidirected", "left": _CX, "right": _CY},
            {"kind": "probability", "target": {"atom": _CX, "value": True},
             "given": [], "value": p_x1},
            {"kind": "probability", "target": {"atom": _CY, "value": True},
             "given": [{"atom": _CX, "value": True}], "value": py_x1},
            {"kind": "probability", "target": {"atom": _CY, "value": True},
             "given": [{"atom": _CX, "value": False}], "value": py_x0},
            {"kind": "query", "id": "q1", "query": query},
        ],
    }


def _assumption_targets(result: dict) -> list[str]:
    return [
        item["target"]
        for req in result.get("investigation_requests", []) or []
        if req["group"] == "assumption"
        for item in req["items"]
    ]


def _cited_targets(result: dict) -> set[str]:
    report = result.get("data_gap_report")
    if report is None:
        return set()
    return {
        ref["ref_id"]
        for gap in report["gaps"]
        for ref in (gap.get("provenance") or [])
        if ref["ref_kind"] == "investigation_request"
    }


def _assumption_gaps(result: dict) -> list[dict]:
    report = result.get("data_gap_report")
    if report is None:
        return []
    return [g for g in report["gaps"] if g["kind"] == "missing_assumption"]


# ---------------------------------------------------------------------------
# The invariant, and then the three shapes it has to hold for
# ---------------------------------------------------------------------------


_PROGRAMS = {
    "undeclared_monotonicity": lambda: _iv_program(monotonicity=None),
    "degenerate_first_stage": lambda: _iv_program(
        monotonicity="non_decreasing", p_x_given_z1=0.2,
    ),
    "risks_unavailable": lambda: _causation_program(
        {"kind": "causation", "cause": _CX, "effect": _CY, "monotonic": True},
    ),
    "risks_infeasible": lambda: _causation_program(
        {"kind": "causation", "cause": _CX, "effect": _CY,
         "experimental_risk_treated": 1.0, "experimental_risk_control": 0.0},
        p_x1=0.5, py_x1=0.5, py_x0=0.5,
    ),
}


@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_every_assumption_item_is_cited_by_a_gap(name):
    """The invariant, stated once over programs whose assumption items
    are of different kinds. An item the report does not cite is a remedy
    the kernel worked out and then dropped on the floor."""
    program = _PROGRAMS[name]()
    result = themis.run(program)["results"][0]
    raised = _assumption_targets(result)
    assert raised, f"{name} raised no assumption item — premise of this test"
    uncited = [t for t in raised if t not in _cited_targets(result)]
    assert not uncited, f"{name}: assumption items missing from report: {uncited}"


@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_the_report_survives_its_own_verifier(name):
    """T10-2 now demands the citation, so a generator that stopped
    emitting the gap would fail the audit rather than pass it quietly.

    Audited through the result-only entry point: these results stop
    before a derivation exists, which is the ordinary shape for a query
    that raised an assumption item at all."""
    result = themis.run(_PROGRAMS[name]())["results"][0]
    assert result.get("derivation") is None
    kernel.verify_data_gap_report(result)


def test_an_undeclared_premise_reaches_the_report_naming_the_instrument():
    result = themis.run(_iv_program(monotonicity=None))["results"][0]
    gaps = _assumption_gaps(result)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap["severity"] == "important"
    assert gap["blocks"] == "point_estimate"
    # The remedy is in the item's reason, not in its machine name.
    assert "monotonicity" in gap["description"]
    assert "z(me)" in gap["description"]
    assert gap["provenance"][0]["ref_id"] == "effect:iv_monotonicity_undeclared"


def test_contradictory_inputs_arrive_as_themselves_not_as_generic_advice():
    """Three of the shapes on this channel are not a missing assumption
    at all — the declared inputs contradict each other. A gap that
    answered them with "accept bounds instead of a point estimate" would
    be advising the reader past an error rather than at it."""
    result = themis.run(_PROGRAMS["risks_infeasible"]())["results"][0]
    gaps = _assumption_gaps(result)
    assert len(gaps) == 1
    gap = gaps[0]
    assert "consistency" in gap["description"]
    assert not gap.get("alternative_paths")


def test_a_degenerate_instrument_says_the_instrument_is_the_problem():
    result = themis.run(_PROGRAMS["degenerate_first_stage"]())["results"][0]
    gaps = _assumption_gaps(result)
    assert len(gaps) == 1
    assert "instrument" in gaps[0]["description"]
    assert (
        gaps[0]["provenance"][0]["ref_id"] == "effect:iv_first_stage_degenerate"
    )


def test_the_actionable_step_names_the_premise_not_the_repair():
    """The same channel carries premises to declare, experiments to run
    and declarations to fix, so the one-line step cannot name a repair
    that holds for all three."""
    result = themis.run(_iv_program(monotonicity=None))["results"][0]
    steps = result["data_gap_report"]["actionable_next_steps"]
    assert any("识别前提" in s for s in steps)
