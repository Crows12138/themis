"""No investigation item may leave the report claiming a clean bill.

``DataGapReport`` distinguishes "no need to ask" (the report is ``None``)
from "asked and got a clean bill of health" (``gaps == ()``). A query
that returned nothing, named exactly what it needed in
``missing_information``, and then produced ``gaps == []`` reports the
second while meaning the first.

The sharpest consequence is ``answer_tier``. It reads the
``unidentifiable_no_admissible_set`` gap to decide whether a point
estimand is in hand, so an effect query whose identification had
structurally failed — ``structural_result.value == False``, and the
reason spelled out in ``missing_information`` — still came back with
``answer_tier == "point"``.

The classifiers used to recognise their items by name — target prefixes
for identification failures, the substring ``iv`` for instruments — so a
name none of them matched fell through to nothing, and a residual pass
swept up whatever was left over. Both are gone: an item states its own
species, the report binds a renderer for every species the vocabulary
allows, and a name nobody wrote a prefix for is not a case that exists.
This file holds the invariant that motivated the sweep, now checked
against the structure that replaced it.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis import kernel


# ---------------------------------------------------------------------------
# Programs
# ---------------------------------------------------------------------------


def _c(pred: str, obj: str = "me") -> dict:
    return {"predicate": pred, "args": [{"type": "const", "name": obj}]}


def _v(pred: str) -> dict:
    return {"predicate": pred, "args": [{"type": "var", "name": "I"}]}


def _collider_program() -> dict:
    """X → W ← Y with X → Y and X ↔ Y, asked conditional on the collider W.

    The bow arc is what makes identification actually fail. This fixture
    used to omit it and justify itself with "no back-door or front-door
    adjustment exists, so the kernel raises identification:not_identifiable"
    — which is not a theorem. On a fully observed DAG every interventional
    distribution is identifiable (ID / IDC completeness); the absence of an
    adjustment set only rules out the two adjustment formulas. The kernel
    agreed with the wrong statement for as long as its IDC branch sat behind
    a latent-confounding guard, and stopped agreeing once that branch became
    reachable — so the fixture now carries the hedge its name always claimed.

    The collider stays: conditioning on it is what makes the failure a
    CONDITIONAL one, and it keeps the advisory this file's severity test is
    about.
    """
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "cause", "forall": ["I"], "from": _v("x"), "to": _v("w")},
            {"kind": "cause", "forall": ["I"], "from": _v("y"), "to": _v("w")},
            {"kind": "cause", "forall": ["I"], "from": _v("x"), "to": _v("y")},
            {"kind": "bidirected", "left": _c("x"), "right": _c("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _c("y"), "value": True},
                "intervention": {"atom": _c("x"), "value": True},
                "given": [{"atom": _c("w"), "value": True}],
            }},
        ],
    }


def _joe_program(*, drop_coefficient=False, observe=("X", "H", "Y")) -> dict:
    """Pearl Primer Model 4.1. Optionally under-specified."""
    X, H, Y = _c("X", "joe"), _c("H", "joe"), _c("Y", "joe")
    stmts = [
        {"kind": "cause", "from": X, "to": H, "coefficient": 0.5},
        {"kind": "cause", "from": X, "to": Y, "coefficient": 0.7},
        {"kind": "cause", "from": H, "to": Y, "coefficient": 0.4},
    ]
    if drop_coefficient:
        del stmts[2]["coefficient"]
    vals = {"X": 0.5, "H": 1.0, "Y": 1.5}
    atoms = {"X": X, "H": H, "Y": Y}
    for name in observe:
        stmts.append({"kind": "observation", "atom": atoms[name],
                      "value": vals[name]})
    stmts.append({"kind": "query", "id": "q1", "query": {
        "kind": "scm_counterfactual",
        "intervention": {"atom": H, "value": 2.0},
        "target": Y}})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "joe"}]},
        "statements": stmts,
    }


_PROGRAMS = {
    "identification_fails": _collider_program,
    "scm_missing_coefficient": lambda: _joe_program(drop_coefficient=True),
    "scm_under_observed": lambda: _joe_program(observe=("X", "Y")),
}


def _items(result: dict, groups: set[str]) -> list[str]:
    return [
        item["target"]
        for req in result.get("investigation_requests", []) or []
        if req["group"] in groups
        for item in req["items"]
    ]


def _report(result: dict) -> dict:
    report = result.get("data_gap_report")
    assert report is not None, "no report at all — different failure"
    return report


def _cited(result: dict) -> set[str]:
    return {
        ref["ref_id"]
        for gap in _report(result)["gaps"]
        for ref in (gap.get("provenance") or [])
        if ref["ref_kind"] == "investigation_request"
    }


# ---------------------------------------------------------------------------
# The invariant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_no_raised_item_is_absent_from_the_report(name):
    result = themis.run(_PROGRAMS[name]())["results"][0]
    raised = _items(result, {"structure", "observation"})
    assert raised, f"{name} raised no structural item — premise of this test"
    uncited = [t for t in raised if t not in _cited(result)]
    assert not uncited, f"{name}: absent from report: {uncited}"


@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_a_query_that_returned_nothing_never_reports_zero_gaps(name):
    """``gaps == ()`` is the report's way of saying it looked and found
    nothing wrong. These queries returned no answer at all."""
    result = themis.run(_PROGRAMS[name]())["results"][0]
    assert result["status"] == "needs_investigation"
    assert _report(result)["gaps"]


@pytest.mark.parametrize("name", sorted(_PROGRAMS))
def test_the_report_survives_its_own_verifier(name):
    result = themis.run(_PROGRAMS[name]())["results"][0]
    kernel.verify_data_gap_report(result)


# ---------------------------------------------------------------------------
# answer_tier — the consequence that made this a wrong signal, not a gap
# ---------------------------------------------------------------------------


def test_a_failed_identification_is_not_reported_as_a_point_estimand():
    result = themis.run(_collider_program())["results"][0]
    # Premise: identification really did fail. An ADMG refusal reports that
    # as a STRUCTURE-kind investigation item rather than a structural_result
    # of False — the two refusal shapes still differ on that field, which is
    # its own outstanding item, not this test's subject.
    assert result["status"] == "needs_investigation"
    assert "structure" in {
        m["kind"] for m in (result.get("missing_information") or [])
    }
    report = _report(result)
    kinds = [g["kind"] for g in report["gaps"]]
    assert "unidentifiable_no_admissible_set" in kinds
    assert report["answer_tier"] == "none"


def test_the_summary_leads_with_the_identification_failure():
    """Severity ordering puts it first; before the gap existed the
    summary led with a collider advisory on a query that had already
    failed to identify."""
    report = _report(themis.run(_collider_program())["results"][0])
    assert "识别路径失败" in report["summary"]


# ---------------------------------------------------------------------------
# What a structural-input gap must NOT claim
# ---------------------------------------------------------------------------


def test_an_undeclared_coefficient_is_not_called_an_identification_failure():
    """The estimand is point identified; a number was never declared.
    Labelling it ``unidentifiable_no_admissible_set`` would tell
    ``answer_tier`` the graph blocks the point, and would offer the
    boilerplate remedy of measuring a confounder or running an RCT for
    a program that needs one edge coefficient."""
    result = themis.run(_joe_program(drop_coefficient=True))["results"][0]
    gaps = _report(result)["gaps"]
    kinds = {g["kind"] for g in gaps}
    assert "missing_structural_input" in kinds
    assert "unidentifiable_no_admissible_set" not in kinds
    gap = next(g for g in gaps if g["kind"] == "missing_structural_input")
    assert "通径系数" in gap["description"]
    assert not gap.get("alternative_paths")


def test_an_unobserved_unit_variable_is_its_own_kind():
    """Abduction wants this unit's reading. A distribution over units
    does not substitute, so it is not a ``missing_distribution``."""
    result = themis.run(_joe_program(observe=("X", "Y")))["results"][0]
    gaps = _report(result)["gaps"]
    obs = [g for g in gaps if g["kind"] == "missing_unit_observation"]
    assert len(obs) == 1
    assert obs[0]["provenance"][0]["ref_id"] == "observation:H(joe)"
    assert "missing_distribution" not in {g["kind"] for g in gaps}


def test_an_item_is_reported_once_and_not_once_per_pass():
    """One item, one species, one renderer. Two passes used to compete
    for the same item — a specific classifier and a residual sweep — and
    the sweep skipped what the classifier had cited. Which order they ran
    in was load-bearing; now nothing has to be ordered."""
    result = themis.run(_collider_program())["results"][0]
    cited = [
        ref["ref_id"]
        for gap in _report(result)["gaps"]
        for ref in (gap.get("provenance") or [])
        if ref["ref_kind"] == "investigation_request"
    ]
    assert cited.count("query:effect_admg_conditional") == 1


def test_a_rejected_query_reports_the_reason_it_was_rejected_for():
    """End to end: the reason the kernel gave is the reason the user reads.

    ``identify.given`` containing a descendant of X is a fixable mistake in
    the query, and the dispatcher says so precisely. The report used to
    answer "未找到满足 IV 条件的工具变量" instead — because the target
    ``query:identify_given`` contains the letters i-v — and sent the user
    off to find an instrument for a query that needed one word deleted.
    """
    def _a(pred):
        return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "d", "domain": [True, False]},
            {"kind": "cause", "from": _a("x"), "to": _a("y")},
            {"kind": "cause", "from": _a("x"), "to": _a("d")},
            {"kind": "query", "id": "q", "query": {
                "kind": "identify",
                "target": _a("y"),
                "intervention": {"atom": _a("x"), "value": True},
                "given": [_a("d")],
            }},
        ],
    }
    result = themis.run(program)["results"][0]
    gaps = _report(result)["gaps"]
    assert "missing_iv_candidate" not in {g["kind"] for g in gaps}
    carried = [
        g for g in gaps if "后门前置条件" in g["description"]
    ]
    assert len(carried) == 1, [g["description"] for g in gaps]


def test_a_solved_query_gains_no_structural_gap():
    """Premise for the whole file: gaps come from items the kernel
    raised, not from every run."""
    result = themis.run(_joe_program())["results"][0]
    assert result["status"] == "counterfactual_solved"
    report = result.get("data_gap_report")
    kinds = {g["kind"] for g in (report or {}).get("gaps", [])}
    assert "missing_structural_input" not in kinds
    assert "missing_unit_observation" not in kinds
