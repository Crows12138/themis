"""Phase 10 §10.4 — T10 verifier rule tests.

Three rules:
- T10-1 ``data_gap_provenance_check``
- T10-2 ``data_gap_completeness_check``
- T10-3 ``data_gap_kind_consistency_check``

Plus the byte-code independence pin: themis.verifier.data_gap_rules MUST
NOT import from themis.output.data_gap_report.
"""
from __future__ import annotations

import pytest

from themis.verifier.data_gap_rules import verify_data_gap_report
from themis.verifier.errors import VerificationError


def _gap(**overrides) -> dict:
    base = {
        "kind": "missing_distribution",
        "severity": "blocking",
        "description": "缺一个分布",
        "blocks": "point_estimate",
        "provenance": [
            {"ref_kind": "investigation_request", "ref_id": "P(y|x)"}
        ],
    }
    base.update(overrides)
    return base


def _report(gaps: list[dict], **overrides) -> dict:
    base = {"summary": "x", "gaps": gaps}
    base.update(overrides)
    return base


def _failed_step(rule: str, step_id: str = "step_1") -> dict:
    return {
        "rule": rule,
        "step_id": step_id,
        "inputs": {},
        "output": False,
        "success": False,
    }


def _ok_step(rule: str, step_id: str = "step_0") -> dict:
    return {
        "rule": rule,
        "step_id": step_id,
        "inputs": {},
        "output": True,
    }


def _param_request(items: list[str]) -> dict:
    return {
        "action": "validate_parameter",
        "target": items[0] if len(items) == 1 else f"parameter:{len(items)}_items",
        "priority": "high",
        "group": "parameter",
        "items": [{"target": t} for t in items],
    }


def _assumption_request(items: list[str]) -> dict:
    return {
        "action": "define_assumption",
        "target": items[0] if len(items) == 1 else f"assumption:{len(items)}_items",
        "priority": "high",
        "group": "assumption",
        "items": [{"target": t, "reason": "premise not declared"} for t in items],
    }


# ============================================ short-circuit


def test_none_report_short_circuits_to_accept():
    verify_data_gap_report(None)  # no exception


def test_empty_gaps_short_circuits_to_accept():
    """No gaps to validate, no signals to demand coverage for."""
    verify_data_gap_report(_report(gaps=[]))


def test_non_dict_report_rejected():
    with pytest.raises(VerificationError):
        verify_data_gap_report(["not", "a", "dict"])  # type: ignore[arg-type]


# ============================================ T10-1 provenance


def test_t10_1_accepts_resolved_derivation_step_ref():
    derivation = {"steps": [_failed_step("unidentifiable_via_backdoor", "s_3")]}
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {"ref_kind": "derivation_step", "ref_id": "s_3"}
                ],
            )
        ]
    )
    verify_data_gap_report(report, derivation=derivation)


def test_t10_1_rejects_unknown_derivation_step_ref():
    derivation = {"steps": [_failed_step("unidentifiable_via_backdoor", "s_3")]}
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {"ref_kind": "derivation_step", "ref_id": "step_phantom"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-1"):
        verify_data_gap_report(report, derivation=derivation)


def test_t10_1_accepts_resolved_investigation_request_ref():
    requests = [_param_request(["P(y|x)"])]
    report = _report(
        [
            _gap(
                kind="missing_distribution",
                provenance=[
                    {"ref_kind": "investigation_request", "ref_id": "P(y|x)"}
                ],
            )
        ]
    )
    verify_data_gap_report(report, investigation_requests=requests)


def test_t10_1_rejects_unknown_investigation_request_ref():
    requests = [_param_request(["P(y|x)"])]
    report = _report(
        [
            _gap(
                provenance=[
                    {
                        "ref_kind": "investigation_request",
                        "ref_id": "P(z|w)",
                    }
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-1"):
        verify_data_gap_report(report, investigation_requests=requests)


def test_t10_1_accepts_resolved_framing_note_ref():
    framing_notes = [
        {"predicate": "exercise", "missing": ["time_window"]}
    ]
    report = _report(
        [
            _gap(
                kind="ambiguous_variable_definition",
                provenance=[
                    {"ref_kind": "framing_note", "ref_id": "exercise"}
                ],
            )
        ]
    )
    verify_data_gap_report(report, framing_notes=framing_notes)


def test_t10_1_rejects_unknown_framing_note_ref():
    framing_notes = [{"predicate": "exercise", "missing": ["time_window"]}]
    report = _report(
        [
            _gap(
                kind="ambiguous_variable_definition",
                provenance=[
                    {"ref_kind": "framing_note", "ref_id": "stranger_var"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-1"):
        verify_data_gap_report(report, framing_notes=framing_notes)


def test_t10_1_accepts_verifier_check_ref_with_any_string():
    """verifier_check refs are free-form by design — they cite status or
    rule names that don't have a canonical id elsewhere."""
    report = _report(
        [
            _gap(
                kind="missing_assumption",
                severity="important",
                provenance=[
                    {
                        "ref_kind": "verifier_check",
                        "ref_id": "status:needs_assumption",
                    }
                ],
            )
        ]
    )
    verify_data_gap_report(report)


def test_t10_1_rejects_unknown_ref_kind():
    report = _report(
        [
            _gap(
                provenance=[
                    {"ref_kind": "kind_we_made_up", "ref_id": "x"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-1"):
        verify_data_gap_report(report)


# ============================================ T10-2 completeness


def test_t10_2_rejects_uncited_failed_derivation_step():
    """A failed step with no covering gap is exactly the bug we want to
    catch — generator missed it."""
    derivation = {"steps": [_failed_step("unidentifiable_via_backdoor", "s_3")]}
    report = _report(gaps=[])  # empty: no coverage at all
    # The empty-report short-circuit doesn't apply because we had a real
    # signal; however current implementation skips empty reports. Use a
    # gap that doesn't cite the failed step.
    report = _report(
        [
            _gap(
                kind="ambiguous_variable_definition",
                severity="informational",
                provenance=[
                    {"ref_kind": "framing_note", "ref_id": "x"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-2"):
        verify_data_gap_report(
            report,
            derivation=derivation,
            framing_notes=[{"predicate": "x", "missing": []}],
        )


def test_t10_2_accepts_failed_step_cited_by_step_id():
    derivation = {"steps": [_failed_step("unidentifiable_via_backdoor", "s_3")]}
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {"ref_kind": "derivation_step", "ref_id": "s_3"}
                ],
            )
        ]
    )
    verify_data_gap_report(report, derivation=derivation)


def test_t10_2_accepts_failed_step_cited_by_rule_name():
    """Generator may cite the rule name instead of step_id."""
    derivation = {"steps": [_failed_step("unidentifiable_via_backdoor", "s_3")]}
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {
                        "ref_kind": "derivation_step",
                        "ref_id": "unidentifiable_via_backdoor",
                    }
                ],
            )
        ]
    )
    verify_data_gap_report(report, derivation=derivation)


def test_t10_2_rejects_uncited_parameter_investigation_item():
    requests = [_param_request(["P(y|x)", "P(z)"])]
    report = _report(
        [
            _gap(
                kind="missing_distribution",
                provenance=[
                    {"ref_kind": "investigation_request", "ref_id": "P(y|x)"}
                ],
            )
        ]
    )
    # Missing coverage of P(z).
    with pytest.raises(VerificationError, match="T10-2"):
        verify_data_gap_report(report, investigation_requests=requests)


def test_t10_2_rejects_uncited_assumption_investigation_item():
    """The generator that stopped emitting assumption gaps stayed green
    for as long as it did because this rule enumerated the covered
    groups by hand and assumption was not on the list. An assumption
    item is the only place its premise is named — no derivation step
    records it and no framing note carries it — so dropping it drops the
    remedy out of the envelope."""
    requests = [_assumption_request(["effect:iv_monotonicity_undeclared"])]
    unrelated = _gap(
        kind="unmeasured_confounder_risk",
        severity="informational",
        provenance=[{"ref_kind": "verifier_check", "ref_id": "program:shape"}],
    )
    with pytest.raises(VerificationError, match="T10-2"):
        verify_data_gap_report(
            _report([unrelated]), investigation_requests=requests,
        )


def test_t10_2_accepts_a_cited_assumption_investigation_item():
    requests = [_assumption_request(["effect:iv_monotonicity_undeclared"])]
    report = _report(
        [
            _gap(
                kind="missing_assumption",
                severity="important",
                provenance=[
                    {
                        "ref_kind": "investigation_request",
                        "ref_id": "effect:iv_monotonicity_undeclared",
                    }
                ],
            )
        ]
    )
    verify_data_gap_report(report, investigation_requests=requests)


def test_t10_2_leaves_structure_group_items_to_their_derivation_step():
    """Scope, pinned so it reads as a decision rather than an oversight.
    Structure items generally restate a derivation failure the report
    already cites through the step, so requiring a second citation of
    the same fact would reject correct reports. Extending the rule to
    this group is a separate piece of work with its own audit."""
    requests = [
        {
            "action": "run_experiment",
            "target": "identification:not_identifiable",
            "priority": "high",
            "group": "structure",
            "items": [{"target": "identification:not_identifiable"}],
        }
    ]
    unrelated = _gap(
        kind="unmeasured_confounder_risk",
        severity="informational",
        provenance=[{"ref_kind": "verifier_check", "ref_id": "program:shape"}],
    )
    verify_data_gap_report(
        _report([unrelated]), investigation_requests=requests,
    )


def test_t10_2_rejects_uncited_framing_note():
    framing_notes = [
        {"predicate": "exercise", "missing": ["time_window"]},
        {"predicate": "diet", "missing": ["measurement"]},
    ]
    report = _report(
        [
            _gap(
                kind="ambiguous_variable_definition",
                provenance=[
                    {"ref_kind": "framing_note", "ref_id": "exercise"}
                ],
            )
        ]
    )
    # Missing diet coverage.
    with pytest.raises(VerificationError, match="T10-2"):
        verify_data_gap_report(report, framing_notes=framing_notes)


def test_t10_2_ignores_successful_steps():
    derivation = {
        "steps": [
            _ok_step("graph_is_dag", "s_0"),
            _ok_step("backdoor_criterion", "s_1"),
        ]
    }
    # Empty report is fine when no failures exist.
    verify_data_gap_report(_report(gaps=[]), derivation=derivation)


# ============================================ T10-3 kind consistency


def test_t10_3_rejects_unidentifiable_gap_with_only_framing_provenance():
    """Unidentifiable claim must cite a derivation_step or
    investigation_request — framing alone doesn't justify it."""
    framing_notes = [{"predicate": "x", "missing": ["time_window"]}]
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {"ref_kind": "framing_note", "ref_id": "x"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-3"):
        verify_data_gap_report(report, framing_notes=framing_notes)


def test_t10_3_rejects_ambiguous_var_gap_without_framing_ref():
    """ambiguous_variable_definition can ONLY come from framing notes."""
    report = _report(
        [
            _gap(
                kind="ambiguous_variable_definition",
                provenance=[
                    {"ref_kind": "investigation_request", "ref_id": "P(y|x)"}
                ],
            )
        ]
    )
    requests = [_param_request(["P(y|x)"])]
    with pytest.raises(VerificationError, match="T10-3"):
        verify_data_gap_report(report, investigation_requests=requests)


def test_t10_3_rejects_unidentifiable_gap_citing_successful_step():
    """If the gap claims unidentifiable but cites a step that ran
    successfully, the gap is fabricated."""
    derivation = {
        "steps": [
            _ok_step("backdoor_criterion", "s_1"),
        ]
    }
    report = _report(
        [
            _gap(
                kind="unidentifiable_no_admissible_set",
                provenance=[
                    {"ref_kind": "derivation_step", "ref_id": "s_1"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-3"):
        verify_data_gap_report(report, derivation=derivation)


def test_t10_3_rejects_unknown_gap_kind():
    # Use a verifier_check ref so T10-1 (provenance resolution) passes
    # — we want T10-3 to be the rule that fires.
    report = _report(
        [
            _gap(
                kind="invented_kind",
                provenance=[
                    {"ref_kind": "verifier_check", "ref_id": "anything"}
                ],
            )
        ]
    )
    with pytest.raises(VerificationError, match="T10-3"):
        verify_data_gap_report(report)


def test_t10_3_accepts_iv_gap_via_investigation_request_path():
    """missing_iv_candidate need not cite a failed derivation step if the
    failure was reported through the investigation channel instead."""
    requests = [
        {
            "action": "run_experiment",
            "target": "iv_candidate",
            "priority": "high",
            "group": "structure",
            "items": [{"target": "iv_candidate"}],
        }
    ]
    report = _report(
        [
            _gap(
                kind="missing_iv_candidate",
                severity="important",
                provenance=[
                    {
                        "ref_kind": "investigation_request",
                        "ref_id": "iv_candidate",
                    }
                ],
            )
        ]
    )
    verify_data_gap_report(report, investigation_requests=requests)


# ============================================ end-to-end on real run


def test_t10_passes_on_real_dispatch_output():
    """Smoke test: run a real fixture through the full pipeline and
    confirm the auto-generated data_gap_report passes T10 audit."""
    import json
    from pathlib import Path
    from themis import run

    repo = Path(__file__).resolve().parents[2]
    fx = (
        repo
        / "tests"
        / "test_e2e"
        / "fixtures"
        / "exercise_waist_missing_parameter.json"
    )
    prog = json.loads(fx.read_text(encoding="utf-8"))
    out = run(prog)

    triggered = False
    for q in out["results"]:
        report = q.get("data_gap_report")
        if report is None:
            continue
        triggered = True
        verify_data_gap_report(
            report,
            derivation=q.get("derivation"),
            investigation_requests=q.get("investigation_requests", []),
            framing_notes=q.get("framing_notes", []),
        )
    assert triggered, (
        "expected at least one query in this fixture to attach a data_gap_report"
    )


# ============================================ independence pin


def test_data_gap_rules_does_not_import_generator():
    """Charter §2.4 hard pin: themis.verifier.data_gap_rules must NOT
    import themis.output.data_gap_report. The generator and verifier
    are separate code paths so a bug in one cannot mask itself in the
    other."""
    import themis.verifier.data_gap_rules as t10_mod

    forbidden_starts = (
        "from themis.output.data_gap_report",
        "from ..output.data_gap_report",
        "import themis.output.data_gap_report",
    )
    with open(t10_mod.__file__, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for forbidden in forbidden_starts:
                if stripped.startswith(forbidden):
                    raise AssertionError(
                        f"line {lineno}: data_gap_rules.py contains "
                        f"forbidden import {stripped!r} — T10 audit must "
                        "be independent of the generator implementation"
                    )


def test_data_gap_rules_has_independent_failure_registry():
    """The verifier must maintain its own list of failure-bearing rule
    names (not import the generator's). This catches the regression where
    a refactor accidentally re-points the verifier at the generator's
    constant."""
    import themis.verifier.data_gap_rules as t10_mod

    assert hasattr(t10_mod, "_VERIFIER_FAILURE_RULE_NAMES")
    assert isinstance(t10_mod._VERIFIER_FAILURE_RULE_NAMES, frozenset)
    # The set must be NON-empty so coverage of T10-2 has something to
    # detect.
    assert len(t10_mod._VERIFIER_FAILURE_RULE_NAMES) > 0
