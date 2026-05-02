"""Phase 10 §10.3 — DataGapReport generator tests.

Per-branch unit tests + the integration test that the generator is
actually attached at dispatch time.
"""
from __future__ import annotations

import pytest

from themis.output.data_gap_report import compute_data_gap_report
from themis.types import (
    DataGap,
    DataGapReport,
    DerivationStep,
    FramingNote,
    GapBlocks,
    GapKind,
    GapRefKind,
    GapSeverity,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    Priority,
    QueryKind,
    ResultStatus,
)


# ============================================ helpers


def _param_request(items: list[tuple[str, str | None]]) -> InvestigationRequest:
    """Build a parameter-group investigation request with given (target, reason)
    items."""
    inv_items = tuple(
        InvestigationItem(target=t, reason=r) for (t, r) in items
    )
    return InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=items[0][0] if len(items) == 1 else f"parameter:{len(items)}_items",
        priority=Priority.HIGH,
        group="parameter",
        items=inv_items,
    )


def _structure_request(target: str) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.RUN_EXPERIMENT,
        target=target,
        priority=Priority.HIGH,
        group="structure",
        items=(InvestigationItem(target=target),),
    )


def _assumption_request(target: str) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.DEFINE_ASSUMPTION,
        target=target,
        priority=Priority.HIGH,
        group="assumption",
        items=(InvestigationItem(target=target),),
    )


def _failed_step(rule: str, step_id: str = "step_x") -> DerivationStep:
    return DerivationStep(
        rule=rule, inputs={}, output=False, step_id=step_id, success=False
    )


# ============================================ short-circuits


def test_returns_none_for_cause_query_with_no_framing():
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
    )
    assert report is None


def test_returns_none_for_assoc_query_with_no_framing():
    report = compute_data_gap_report(
        query_kind=QueryKind.ASSOC,
        status=ResultStatus.STRUCTURALLY_SOLVED,
    )
    assert report is None


def test_cause_query_with_framing_emits_report():
    """Even cause/assoc benefit from surfacing variable-definition
    ambiguity — that's the only signal these query kinds carry."""
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        framing_notes=(FramingNote(predicate="x", missing=("time_window",)),),
    )
    assert report is not None
    assert len(report.gaps) == 1
    assert report.gaps[0].kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION


def test_effect_query_with_no_signals_emits_empty_report():
    """Distinct from None: effect queries always get a report so callers
    can present 'no gaps' affirmatively."""
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NUMERICALLY_SOLVED,
    )
    assert report is not None
    assert report.gaps == ()
    assert report.summary == ""


# ============================================ 1. unidentifiable_no_admissible_set


def test_unidentifiable_via_backdoor_emits_blocking_gap():
    derivation = (_failed_step("unidentifiable_via_backdoor", "step_3"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert report is not None
    assert len(report.gaps) == 1
    g = report.gaps[0]
    assert g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
    assert g.severity == GapSeverity.BLOCKING
    assert g.blocks == GapBlocks.IDENTIFICATION
    assert g.provenance[0].ref_kind == GapRefKind.DERIVATION_STEP
    assert g.provenance[0].ref_id == "step_3"


def test_explicit_success_false_step_caught_even_for_non_unidentifiable_rule_name():
    """Rules added later that don't carry _failed in name still trigger if
    they explicitly emit success=False."""
    derivation = (
        DerivationStep(
            rule="some_future_rule",
            inputs={},
            output=False,
            step_id="step_99",
            success=False,
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert any(
        g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET for g in report.gaps
    )


def test_unidentifiable_offers_three_alternative_paths():
    derivation = (_failed_step("unidentifiable_via_backdoor"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    g = report.gaps[0]
    assert len(g.alternative_paths) == 3


# ============================================ 2. missing_distribution


def test_missing_marginal_distribution_signature_marginal():
    requests = (_param_request([("P(y=true)", None)]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = report.gaps[0]
    assert g.kind == GapKind.MISSING_DISTRIBUTION
    assert g.signature == "marginal"


def test_missing_conditional_distribution_signature_conditional():
    requests = (_param_request([("P(y=true|x=true)", None)]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = report.gaps[0]
    assert g.signature == "conditional"


def test_missing_distribution_emits_per_item():
    """Multi-item parameter request fans out to multiple gaps."""
    requests = (
        _param_request(
            [("P(y=true|x=true)", None), ("P(y=true|x=false)", None)]
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    dist_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_DISTRIBUTION
    ]
    assert len(dist_gaps) == 2


# ============================================ 4. missing_assumption


def test_needs_assumption_status_with_assumption_request_emits_specific_gap():
    requests = (_assumption_request("assumptions.monotonicity"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_ASSUMPTION,
        investigation_requests=requests,
    )
    assumption_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_ASSUMPTION
    ]
    assert len(assumption_gaps) == 1
    assert assumption_gaps[0].severity == GapSeverity.IMPORTANT
    assert "monotonicity" in assumption_gaps[0].description


def test_needs_assumption_status_without_request_emits_generic_gap():
    """Status is the only signal — fall back to a verifier-check ref."""
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_ASSUMPTION,
    )
    assumption_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_ASSUMPTION
    ]
    assert len(assumption_gaps) == 1
    assert (
        assumption_gaps[0].provenance[0].ref_kind == GapRefKind.VERIFIER_CHECK
    )


# ============================================ 5. missing_iv_candidate


def test_iv_failure_in_derivation_emits_iv_gap_not_unidentifiable():
    """IV-specific failures should route through the IV classifier so the
    user gets IV-flavored alternatives, not the generic three."""
    derivation = (_failed_step("identify_via_iv", "iv_step"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.MISSING_IV_CANDIDATE in kinds
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET not in kinds


def test_structure_request_naming_iv_emits_iv_gap():
    requests = (_structure_request("iv_candidate_for_smoking_lung_cancer"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    assert any(
        g.kind == GapKind.MISSING_IV_CANDIDATE for g in report.gaps
    )


# ============================================ 6. missing_mediator_data


def test_mediation_block_with_mediator_param_request_emits_mediator_gap():
    extensions = {
        "mediation_decomposition": {
            "mediator": "tar_in_lungs",
            "mediator_valid": True,
        }
    }
    requests = (
        _param_request([("P(tar_in_lungs=true|smoking=true)", None)]),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
        extensions=extensions,
    )
    mediator_gaps = [
        g for g in report.gaps if g.kind == GapKind.MISSING_MEDIATOR_DATA
    ]
    assert len(mediator_gaps) == 1
    assert mediator_gaps[0].required_data.variables == ("tar_in_lungs",)


def test_mediation_block_without_invalid_mediator_emits_no_mediator_gap():
    extensions = {
        "mediation_decomposition": {
            "mediator": "tar_in_lungs",
            "mediator_valid": False,
        }
    }
    requests = (
        _param_request([("P(tar_in_lungs=true|smoking=true)", None)]),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
        extensions=extensions,
    )
    assert not any(
        g.kind == GapKind.MISSING_MEDIATOR_DATA for g in report.gaps
    )


# ============================================ 7. transport_target_distribution_unknown


def test_transport_block_with_nonempty_z_emits_both_transport_gaps():
    """Bareinboim formula has TWO data needs: target P*(Z) AND source
    P(Y|do(X), Z). Both must be reported — meta-analyses publishing only
    marginal effects make the source-stratified conditional often the
    real bottleneck."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "source_population": "meta_2022",
            "target_population": "user_28f",
            "adjustment_set": [
                {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
                {"predicate": "bmi", "args": [{"type": "const", "name": "me"}]},
            ],
            "formula_repr": (
                "P*(belly_fat_loss | do(running)) = "
                "Σ_{age, bmi} P(belly_fat_loss | do(running), age, bmi) "
                "· P*(age, bmi)"
            ),
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        extensions=extensions,
    )
    target_gaps = [
        g for g in report.gaps
        if g.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN
    ]
    source_gaps = [
        g for g in report.gaps
        if g.kind == GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN
    ]
    assert len(target_gaps) == 1
    assert len(source_gaps) == 1

    target = target_gaps[0]
    assert target.required_data.population == "user_28f"
    assert target.required_data.data_type.value == "marginal"
    assert set(target.required_data.variables) == {"age", "bmi"}

    source = source_gaps[0]
    assert source.required_data.population == "meta_2022"
    assert source.required_data.data_type.value == "ipd"
    assert set(source.required_data.variables) == {"age", "bmi"}
    # description should reference the predicate names from formula_repr
    assert "running" in source.description
    assert "belly_fat_loss" in source.description


def test_transport_block_with_empty_z_emits_no_transport_gap():
    """Z empty → P*(Z) trivially known (degenerate). No gap."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "source_population": "meta_2022",
            "target_population": "user_28f",
            "adjustment_set": [],
            "formula_repr": "P*(y|do(x)) = P(y|do(x))",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        extensions=extensions,
    )
    assert not any(
        g.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN
        for g in report.gaps
    )


# ============================================ 8. ambiguous_variable_definition


def test_framing_note_emits_informational_gap():
    notes = (
        FramingNote(predicate="exercise", missing=("time_window", "measurement")),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        framing_notes=notes,
    )
    framing_gaps = [
        g for g in report.gaps
        if g.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION
    ]
    assert len(framing_gaps) == 1
    g = framing_gaps[0]
    assert g.severity == GapSeverity.INFORMATIONAL
    assert "time_window" in g.description and "measurement" in g.description


def test_framing_note_on_query_path_upgrades_to_important():
    """Real-test caught: when the underframed predicate is referenced
    by the query atom (intervention / target / from / to / left / right
    / mediator / given), its framing gap is load-bearing for how the
    answer reads — bumped from `informational` to `important` so the
    renderer surfaces it near the headline rather than as a quiet
    end-of-reply caveat."""
    import themis

    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late"},
            {"kind": "variable", "predicate": "prefrontal_function"},
            {"kind": "cause",
             "from": {"predicate": "stays_up_late",
                      "args": [{"type": "const", "name": "me"}]},
             "to": {"predicate": "prefrontal_function",
                    "args": [{"type": "const", "name": "me"}]},
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
               "kind": "cause",
               "from": {"predicate": "stays_up_late",
                        "args": [{"type": "const", "name": "me"}]},
               "to": {"predicate": "prefrontal_function",
                      "args": [{"type": "const", "name": "me"}]}}}
        ],
    }
    out = themis.run(program)
    gaps = out["results"][0]["data_gap_report"]["gaps"]
    framing = [g for g in gaps
               if g["kind"] == "ambiguous_variable_definition"]
    # Both predicates are on the query path, so both are important.
    assert len(framing) == 2
    assert all(g["severity"] == "important" for g in framing)


def test_framing_note_off_query_path_stays_informational():
    """Companion to the upgrade rule: a framing note for a predicate
    the query does not reference keeps informational severity. Built
    directly against ``compute_data_gap_report`` via a duck-typed stmt
    so the test isolates the severity decision from kernel framing-note
    generation (which only emits notes for query-relevant predicates)."""
    from types import SimpleNamespace

    notes = (
        FramingNote(predicate="on_query_path", missing=("time_window",)),
        FramingNote(predicate="off_query_path", missing=("time_window",)),
    )
    stmt = SimpleNamespace(query=SimpleNamespace(
        from_atom=SimpleNamespace(predicate="on_query_path"),
        to_atom=SimpleNamespace(predicate="other_target"),
    ))
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        framing_notes=notes,
        stmt=stmt,
    )
    by_pred = {
        g.description.split("`")[1]: g.severity
        for g in report.gaps
        if g.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION
    }
    assert by_pred["on_query_path"] == GapSeverity.IMPORTANT
    assert by_pred["off_query_path"] == GapSeverity.INFORMATIONAL


# ============================================ multi-gap composition


def test_multiple_gap_kinds_sorted_blocking_first():
    """Severity sort: blocking before important before informational."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "target_population": "user",
            "adjustment_set": [
                {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
            ],
            "formula_repr": "...",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_ASSUMPTION,
        framing_notes=(FramingNote(predicate="x", missing=("time_window",)),),
        extensions=extensions,
    )
    severities = [g.severity for g in report.gaps]
    # Blocking comes before important comes before informational.
    severity_order = {
        GapSeverity.BLOCKING: 0,
        GapSeverity.IMPORTANT: 1,
        GapSeverity.INFORMATIONAL: 2,
    }
    indices = [severity_order[s] for s in severities]
    assert indices == sorted(indices)


def test_summary_mentions_blocking_count_when_multiple_blocking():
    requests = (
        _param_request(
            [("P(y=true|x=true)", None), ("P(y=true|x=false)", None)]
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    assert "blocking" in report.summary or "缺口" in report.summary


def test_actionable_steps_skip_informational_gaps():
    """Informational gaps don't add to actionable steps."""
    notes = (FramingNote(predicate="x", missing=("time_window",)),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        framing_notes=notes,
    )
    # Only an informational gap → no actionable steps.
    assert report.actionable_next_steps == ()


def test_actionable_steps_use_short_label_for_transport():
    """The actionable_next_steps lines for transport must be concise
    labels — verbatim render of the full description sentence bloats
    the user-facing reply. Two gaps fire (target + source); both must
    use short labels."""
    extensions = {
        "transport_identification": {
            "kind": "transport_identification",
            "source_population": "rct_meta",
            "target_population": "user",
            "adjustment_set": [
                {"predicate": "age", "args": [{"type": "const", "name": "me"}]},
                {"predicate": "sex", "args": [{"type": "const", "name": "me"}]},
                {"predicate": "bmi", "args": [{"type": "const", "name": "me"}]},
            ],
            "formula_repr": "P*(y | do(x)) = ...",
        }
    }
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        extensions=extensions,
    )
    fix_steps = [
        s for s in report.actionable_next_steps if s.startswith("补 ")
    ]
    # Two transport gaps → two "补 ..." lines.
    assert len(fix_steps) == 2

    # Target-side line: "P*(age, sex, bmi) on user".
    target_line = next(s for s in fix_steps if "P*(" in s)
    assert "P*(age, sex, bmi)" in target_line
    assert "on user" in target_line
    # Source-side line: "P(Y|do(X), age, sex, bmi) 在 rct_meta 上的分层..."
    source_line = next(s for s in fix_steps if "P(Y|do(X)" in s)
    assert "rct_meta" in source_line

    # Verbose phrase from full description must not bleed into either.
    for line in fix_steps:
        assert "未提供" not in line
        assert "已识别" not in line


def test_actionable_steps_use_short_label_for_missing_distribution():
    requests = (_param_request([("P(y=true|x=true)", None)]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    fix_step = next(
        s for s in report.actionable_next_steps if s.startswith("补 ")
    )
    # Just the P(...) part, no "缺概率分布 " prefix.
    assert "P(y=true|x=true)" in fix_step
    assert "缺概率分布" not in fix_step


def test_actionable_steps_include_alternative_path():
    derivation = (_failed_step("unidentifiable_via_backdoor"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert any(s.startswith("或：") for s in report.actionable_next_steps)


# ============================================ generator import isolation


def test_generator_module_does_not_import_kb_or_io():
    """The charter §4 forbids any I/O or KB lookups inside this module.
    A coarse byte-code level check that none of the obvious culprits
    appear in the imports."""
    import themis.output.data_gap_report as gen_mod

    # Module's imports are limited to typing + types
    forbidden_substrings = (
        "requests",
        "urllib",
        "httpx",
        "aiohttp",
        "sqlite",
        "kb",
        "retrieval",
        "websearch",
    )
    src = open(gen_mod.__file__, encoding="utf-8").read().lower()
    for needle in forbidden_substrings:
        assert f"import {needle}" not in src and f"from {needle}" not in src, (
            f"data_gap_report.py contains forbidden import substring {needle!r}"
        )
