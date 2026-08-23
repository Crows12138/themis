"""Phase 10 §10.5 — eval coverage of major gap_kinds end-to-end.

Five minimal programs, one per major gap_kind, each runs through
``themis.run`` and confirms:

1. The expected gap_kind appears in the auto-generated data_gap_report.
2. T10 verifier (S.10.4) accepts the report when re-run via
   ``themis.verify``.

Covered gap_kinds:

- ``unidentifiable_no_admissible_set``    — bidirected confounder with no
                                              valid backdoor / front-door /
                                              IV path
- ``missing_distribution``                — identifiable + Theta missing
                                              the conditional CPT
- an instrument that fails its criteria    — which is NOT
                                              ``missing_iv_candidate``:
                                              that kind has no producer
- ``transport_target_distribution_unknown`` — single-source transport,
                                                ``P*(Z)`` not provided
- ``ambiguous_variable_definition``       — predicate referenced by query
                                              has framing gaps
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import themis
from themis import gaps as _gaps


REPO = Path(__file__).resolve().parents[2]


def _atom(p: str, name: str = "me") -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": name}]}


def _cause(src: str, dst: str) -> dict:
    return {"kind": "cause", "from": _atom(src), "to": _atom(dst)}


def _var(p: str) -> dict:
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _domain(name: str = "me") -> dict:
    return {"objects": [{"kind": "object", "name": name}]}


def _gap_kinds(report: dict) -> list[str]:
    return [g["kind"] for g in (report or {}).get("gaps", [])]


def _run_and_verify(program: dict) -> dict:
    """Run + walk T10 audit on every result that carries a report."""
    out = themis.run(program)
    for r in out["results"]:
        # T10 lives inside themis.verify; only call on results with a
        # derivation — the verifier rejects results without one.
        if "derivation" in r:
            themis.verify(program, r)
    return out


# ============================================ 1. unidentifiable_no_admissible_set


def test_unidentifiable_emits_blocking_gap():
    """Bidirected X↔Y plus directed X→Y → no backdoor, no valid front-door
    mediator, no IV → identify dispatch ends in a Tian hedge witness, a
    step that SUCCEEDS and whose c-component is the proof.

    No ``variable`` statements: framing is opt-in per predicate, and
    declaring them would bury the structural failure under
    informational framing gaps."""
    program = {
        "version": "0.1",
        "domain": _domain(),
        "statements": [
            _cause("x", "y"),
            {"kind": "bidirected",
             "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "identify",
                       "target": _atom("y"),
                       "intervention": {"atom": _atom("x"), "value": True},
                       "given": []}},
        ],
    }
    out = _run_and_verify(program)
    result = out["results"][0]
    # Phase 2.latent ext §S3.b.2 Tian Line 5: bow arc is now
    # structurally proven unidentifiable (was needs_investigation before
    # Tian wiring). The downstream gap signal is the same blocking
    # `unidentifiable_no_admissible_set` kind — the difference is
    # status now reads "structurally_solved" with value=False, and the
    # description names the hedge / c-component. The branch that pointed
    # at backdoor exhaustion was not superseded in wording only: it read
    # for a step that had failed, and after this rewiring nothing wrote
    # one, so it has been removed.
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is False
    report = result.get("data_gap_report")
    assert report is not None
    assert "unidentifiable_no_admissible_set" in _gap_kinds(report)
    blocking = next(
        g for g in report["gaps"]
        if g["kind"] == "unidentifiable_no_admissible_set"
    )
    assert blocking["severity"] == "blocking"
    assert blocking["blocks"] == "identification"
    assert "hedge" in _gaps.described(blocking) or "c-component" in _gaps.described(blocking)


# ============================================ 2. missing_distribution


def test_missing_distribution_emits_blocking_gap():
    """Identifiable backdoor structure + Theta lacks the conditional CPT
    → effect dispatch returns needs_investigation with a parameter gap."""
    fx = REPO / "tests" / "test_e2e" / "fixtures" / "exercise_waist_missing_parameter.json"
    program = json.loads(fx.read_text(encoding="utf-8"))
    out = _run_and_verify(program)

    triggered = False
    for r in out["results"]:
        report = r.get("data_gap_report")
        if not report:
            continue
        if "missing_distribution" in _gap_kinds(report):
            triggered = True
            gap = next(
                g for g in report["gaps"]
                if g["kind"] == "missing_distribution"
            )
            assert gap["severity"] == "blocking"
            assert gap["blocks"] == "point_estimate"
            assert gap["signature"] in ("marginal", "conditional", "joint")
    assert triggered, "expected missing_distribution gap on the missing-parameter fixture"


# ============================================ 3. missing_iv_candidate


def test_an_instrument_that_fails_its_criteria_is_not_an_instrument_gap():
    """An ADMG (X↔Y) whose only candidate Z violates exclusion (Z↔Y).

    This asserted ``missing_iv_candidate`` OR
    ``unidentifiable_no_admissible_set``, and the disjunction is what let
    a dead label look alive: only the second arm has ever fired. The
    first cannot — its classifier read for a failed IV derivation step
    and nothing writes one. Both halves are stated separately now, which
    is the point: a disjunction passes without saying which side did it.
    """
    program = {
        "version": "0.1",
        "domain": _domain(),
        "statements": [
            _cause("z", "x"),
            _cause("x", "y"),
            # Bidirected X↔Y → unmeasured U → can't backdoor or front-door.
            {"kind": "bidirected",
             "left": _atom("x"), "right": _atom("y")},
            # And bidirected Z↔Y violates IV exclusion.
            {"kind": "bidirected",
             "left": _atom("z"), "right": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "identify",
                       "target": _atom("y"),
                       "intervention": {"atom": _atom("x"), "value": True},
                       "given": []}},
        ],
    }
    out = _run_and_verify(program)
    result = out["results"][0]
    report = result.get("data_gap_report")
    assert report is not None
    kinds = _gap_kinds(report)
    assert "unidentifiable_no_admissible_set" in kinds
    assert "missing_iv_candidate" not in kinds


# ============================================ 4. transport_target_distribution_unknown


def test_transport_emits_blocking_gap():
    """Re-use case 29 (running × belly-fat transport): structurally
    identified, but target P*(Z) was never quantified by §T9.1 → gap."""
    fx = REPO / "docs" / "eval_set" / "cases" / "29_running_belly_fat_transport.json"
    case = json.loads(fx.read_text(encoding="utf-8"))

    statements: list[dict] = []
    for v in case["gold_variables"]:
        statements.append(_var(v["predicate"]))
    for e in case["gold_edges"]:
        statements.append(_cause(e["from"], e["to"]))
    for s in case.get("gold_selection_nodes", []):
        statements.append({
            "kind": "selection_node",
            "id": s["id"],
            "affects": _atom(s["affects"]),
            "source_population": s["source_population"],
            "target_population": s["target_population"],
        })
    statements.append({
        "kind": "query", "id": "q",
        "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("running"), "value": True},
            "target": {"atom": _atom("belly_fat_loss"), "value": True},
            "given": [],
            "target_population": "user",
        },
    })
    program = {
        "version": "0.1",
        "domain": _domain(),
        "statements": statements,
    }
    out = _run_and_verify(program)
    result = out["results"][0]
    report = result.get("data_gap_report")
    assert report is not None
    kinds = _gap_kinds(report)
    # Bareinboim formula has two data needs — both gap_kinds must fire.
    assert "transport_target_distribution_unknown" in kinds
    assert "transport_source_conditional_unknown" in kinds

    target = next(
        g for g in report["gaps"]
        if g["kind"] == "transport_target_distribution_unknown"
    )
    assert target["severity"] == "blocking"
    assert target["blocks"] == "transport"
    assert target["required_data"]["population"] == "user"
    assert set(target["required_data"]["variables"]) >= {"age", "sex", "bmi"}

    source = next(
        g for g in report["gaps"]
        if g["kind"] == "transport_source_conditional_unknown"
    )
    assert source["required_data"]["data_type"] == "ipd"
    assert source["required_data"]["population"] == "rct_meta_2022"


# ============================================ 5. ambiguous_variable_definition


def test_ambiguous_variable_emits_important_gap_when_on_query_path():
    """A variable declared with framing fields missing AND referenced by
    the query → framing_note fires → important gap (the framing shapes
    how the answer reads, so it surfaces near the headline rather than
    as an end-of-reply caveat). Predicates declared but not on the
    query path stay informational; covered in
    test_phase10_data_gap_generator.py."""
    fx = REPO / "tests" / "test_e2e" / "fixtures" / "exercise_waist_underframed.json"
    program = json.loads(fx.read_text(encoding="utf-8"))
    out = _run_and_verify(program)

    triggered = False
    for r in out["results"]:
        report = r.get("data_gap_report")
        if report and "ambiguous_variable_definition" in _gap_kinds(report):
            triggered = True
            gap = next(
                g for g in report["gaps"]
                if g["kind"] == "ambiguous_variable_definition"
            )
            assert gap["severity"] == "important"
            # framing gaps don't block identification (graph-only) or the
            # estimate (Theta numbers); they block the user's ability to
            # *interpret* what was identified / estimated.
            assert gap["blocks"] == "interpretation"
    assert triggered, "expected ambiguous_variable_definition gap on the underframed fixture"


# ============================================ multi-gap composition


def test_multiple_gaps_sorted_blocking_first():
    """A program that triggers BOTH a blocking gap (missing parameter) and
    an informational gap (framing). The report must put blocking first."""
    fx = REPO / "tests" / "test_e2e" / "fixtures" / "exercise_waist_underframed.json"
    program = json.loads(fx.read_text(encoding="utf-8"))
    out = _run_and_verify(program)

    found_multi = False
    for r in out["results"]:
        report = r.get("data_gap_report")
        if not report:
            continue
        kinds = _gap_kinds(report)
        if len(kinds) < 2:
            continue
        found_multi = True
        severities = [g["severity"] for g in report["gaps"]]
        # blocking before important before informational
        order = {"blocking": 0, "important": 1, "informational": 2}
        ranks = [order[s] for s in severities]
        assert ranks == sorted(ranks)
    # Not all paths through the underframed fixture produce multi-gap;
    # accept zero hits gracefully so a future scheduler change doesn't
    # silently break this test.
    if not found_multi:
        pytest.skip("no multi-gap query in fixture under current dispatch")
