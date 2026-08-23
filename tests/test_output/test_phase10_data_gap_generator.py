"""Phase 10 §10.3 — DataGapReport generator tests.

Per-branch unit tests + the integration test that the generator is
actually attached at dispatch time.
"""
from __future__ import annotations

import pytest

from themis import gaps
from themis.output.data_gap_report import compute_data_gap_report
from themis.types import (
    AnswerTier,
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


#: What the kernel says when theta simply has no entry, and what it says
#: when theta HAS a marginal the graph forbids substituting. Two species
#: because the repairs are opposite, which is the distinction these tests
#: are about.
_LACKS = gaps.Need.THETA_ENTRY_MISSING
_MISMATCH = gaps.Need.GRAPH_CONTRADICTS_SUPPLIED_MARGINAL


def _mismatch(key: str, *, have: str, variable: str, extras: str,
              conditioning: str) -> dict:
    return dict(need=_MISMATCH, key=key, have=have, variable=variable,
                extras=extras, conditioning=conditioning)


def _param_request(
    items: "list[tuple[str, dict | None]]",
    *,
    gap: GapKind = GapKind.MISSING_DISTRIBUTION,
) -> InvestigationRequest:
    """Build a parameter-group investigation request from (target, need)
    pairs, where the second is the species and this occasion's facts as
    :func:`themis.gaps.item` takes them, or ``None`` for an item with
    nothing to say. ``gap`` applies only to the second case; where a
    species is given it declares its own, which is the point."""
    inv_items = tuple(
        gaps.item(target=t, **o) if o else InvestigationItem(target=t, gap=gap)
        for (t, o) in items
    )
    return InvestigationRequest(
        action=InvestigationAction.VALIDATE_PARAMETER,
        target=items[0][0] if len(items) == 1 else f"parameter:{len(items)}_items",
        priority=Priority.HIGH,
        group="parameter",
        items=inv_items,
    )


def _structure_request(
    target: str, *, gap: GapKind = GapKind.MISSING_STRUCTURAL_INPUT,
) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.RUN_EXPERIMENT,
        target=target,
        priority=Priority.HIGH,
        group="structure",
        items=(InvestigationItem(target=target, gap=gap),),
    )


def _assumption_request(
    target: str, occasion: "dict | None" = None
) -> InvestigationRequest:
    return InvestigationRequest(
        action=InvestigationAction.DEFINE_ASSUMPTION,
        target=target,
        priority=Priority.HIGH,
        group="assumption",
        items=(
            gaps.item(target=target, **occasion) if occasion
            else InvestigationItem(
                target=target, gap=GapKind.MISSING_ASSUMPTION)
        ,),
    )


def _hedge_step(step_id: str = "step_x") -> DerivationStep:
    """The way the kernel says "not identifiable": a step that SUCCEEDED,
    naming the c-component hedge that proves it. There is no failed step
    to build here — no producer writes one, and the report stopped
    reading for one."""
    return DerivationStep(
        rule="tian_hedge_witness", inputs={}, output=False, step_id=step_id
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


def test_a_hedge_witness_emits_blocking_gap():
    derivation = (_hedge_step("step_3"),)
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


def test_a_step_claiming_it_failed_raises_nothing_here():
    """The report used to scan for a step carrying ``success=False`` and
    raise the blocking gap from it. Nothing writes such a step: the kernel
    says "not identifiable" with a hedge witness or an investigation item,
    and over a full suite the scan only ever fired on steps its own tests
    had built. It is gone, and this states the consequence rather than
    leaving it to be discovered.

    A ``success=False`` step is still meaningful one layer out — a
    derivation submitted from outside may claim a failure, and
    ``themis/verifier/data_gap_rules.py`` reads the claim so the verifier
    can check it. That is the reader; this is not."""
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
    assert not any(
        g.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET for g in report.gaps
    )


def test_unidentifiable_offers_three_alternative_paths():
    derivation = (_hedge_step(),)
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


def _assumption_gaps(report) -> list:
    return [g for g in report.gaps if g.kind == GapKind.MISSING_ASSUMPTION]


def test_an_assumption_request_emits_a_gap_citing_the_item():
    requests = (_assumption_request("assumptions.monotonicity"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    gaps = _assumption_gaps(report)
    assert len(gaps) == 1
    assert gaps[0].severity == GapSeverity.IMPORTANT
    assert "monotonicity" in gaps[0].description
    assert gaps[0].provenance[0].ref_kind == GapRefKind.INVESTIGATION_REQUEST
    assert gaps[0].provenance[0].ref_id == "assumptions.monotonicity"


@pytest.mark.parametrize(
    "status",
    [
        ResultStatus.NEEDS_INVESTIGATION,
        ResultStatus.NEEDS_ASSUMPTION,
        ResultStatus.STRUCTURALLY_SOLVED,
    ],
)
def test_the_assumption_gap_does_not_depend_on_the_status(status):
    """The channel is the trigger. Keying on ResultStatus.NEEDS_ASSUMPTION
    made the classifier silent the day that status lost its producer,
    and the kernel does not produce it today — which is why this reads
    the same for all three."""
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=status,
        investigation_requests=(_assumption_request("effect:iv_mono"),),
    )
    assert len(_assumption_gaps(report)) == 1


def test_a_status_alone_names_no_premise_and_emits_no_gap():
    """A status says an assumption is wanted; it cannot say which one.
    The gap that used to be emitted here read '具体假设未在
    missing_information 标注' — a gap whose content is that the content
    is missing."""
    report = compute_data_gap_report(
        query_kind=QueryKind.COUNTERFACTUAL,
        status=ResultStatus.NEEDS_ASSUMPTION,
    )
    assert report is None or not _assumption_gaps(report)


def test_the_gap_says_what_the_item_asked_for_over_its_machine_name():
    """The remedy is in the species. A description built from the target
    alone hands the reader an identifier to go look up.

    What the item carries is the species and this occasion's facts, and
    the sentence is assembled here, where the reader's language is known
    — so the assertion is on the assembled sentence and would have to
    change if the item stopped carrying enough to assemble it."""
    requests = (
        _assumption_request(
            "effect:iv_first_stage_degenerate",
            dict(need=gaps.Need.IV_FIRST_STAGE_DEGENERATE,
                 instrument="z(me)"),
        ),
    )
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    found = _assumption_gaps(report)
    assert len(found) == 1
    assert "工具 z(me) 推不动处理" in found[0].description


# ============================================ 5. missing_iv_candidate


# The classifier that lived here read for a failed IV derivation step and
# attached IV-flavoured alternatives to it. Nothing writes a failed step,
# so it raised nothing, and ``MISSING_IV_CANDIDATE`` is now a declared
# empty slot — ``data_gap_report.GAP_KINDS_WITH_NO_PRODUCER`` says so and
# ``tests/test_no_step_the_kernel_wrote_says_it_failed.py`` holds that
# declaration to a census of the tree. What remains below is the other
# half: the channel by which a NAME could once become this gap.


def test_a_name_can_no_longer_produce_an_instrument_gap_at_all():
    """``given`` contains the letters i-v.

    An identify query rejected because its ``given`` violates the
    back-door pre-conditions was reported as "no valid instrumental
    variable found" — and the same substring test, used to EXCLUDE in the
    classifier that would have carried the real reason, suppressed that
    too. One coincidence both fabricated a gap and hid one.

    The fix at the time was a stricter reading of the name. What closes
    it is that no reading happens: ``MISSING_IV_CANDIDATE`` is not a
    species a missing item may declare, so no name — however spelled —
    reaches that gap through this channel.
    """
    requests = (_structure_request("query:identify_given"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.MISSING_IV_CANDIDATE not in kinds


def test_a_malformed_given_is_a_program_defect_not_a_failed_identification():
    """``query:identify_unreachable`` is the ID algorithm reporting no
    witness; ``query:identify_given`` is the user conditioning on a
    descendant of X. Telling ``answer_tier`` that the graph blocks the
    estimand is exactly what it must not be told about a fixable query.

    The two used to be told apart by a prefix that was one word too
    short. They are told apart by the branch that raised them now."""
    requests = (_structure_request("query:identify_given"),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET not in kinds
    assert GapKind.MISSING_STRUCTURAL_INPUT in kinds


def test_the_species_decides_the_gap_and_the_name_does_not():
    """Same name, same group, same channel — two different gaps, because
    the branches that raised them said different things. No naming
    convention can express that, which is why the report stopped reading
    names."""
    name = "query:identify_given"
    blocked = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=(_structure_request(
            name, gap=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        ),),
    )
    defect = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=(_structure_request(
            name, gap=GapKind.MISSING_STRUCTURAL_INPUT,
        ),),
    )
    assert blocked.answer_tier is AnswerTier.NONE
    assert defect.answer_tier is AnswerTier.POINT


def test_an_item_cannot_declare_a_species_no_renderer_is_bound_for():
    """The table covers the declared vocabulary exactly, so an item that
    reaches the report reaches the user. That is the guarantee the
    residual pass used to provide by sweeping for uncited items, now held
    at import instead of at the end of every run."""
    from themis.output import data_gap_report as mod
    from themis.types import MISSING_ITEM_GAPS

    assert set(mod._ITEM_SPECIES) == set(MISSING_ITEM_GAPS)
    with pytest.raises(ValueError, match="no renderer"):
        mod._bind_item_species({})
    with pytest.raises(ValueError, match="which no missing item may"):
        mod._bind_item_species(
            dict(mod._ITEM_SPECIES) | {GapKind.WEAK_IV_INSTRUMENT: None}
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


def test_actionable_steps_are_short_imperatives_not_description_repeats():
    """Real-test caught: actionable_next_steps used to be
    `f'补 {short_label} → {gap.if_provided}'`, which inlined the same
    if_provided text the renderer surfaces inside the gap bullet itself
    — so the user saw 'why this matters' twice, once per gap and once
    per actionable step. Now the action is short imperative only; the
    why stays in the gap object."""
    from types import SimpleNamespace

    notes = (
        FramingNote(predicate="stays_up_late", missing=("time_window",)),
    )
    stmt = SimpleNamespace(query=SimpleNamespace(
        from_atom=SimpleNamespace(predicate="stays_up_late"),
        to_atom=SimpleNamespace(predicate="prefrontal_function"),
    ))
    report = compute_data_gap_report(
        query_kind=QueryKind.CAUSE,
        status=ResultStatus.STRUCTURALLY_SOLVED,
        framing_notes=notes,
        stmt=stmt,
    )
    # The gap's if_provided text must NOT leak into actionable_next_steps.
    why_text = "下游结果（点估计 / bounds）的语义"
    assert any(why_text in g.if_provided for g in report.gaps), \
        "if_provided still on the gap (sanity check)"
    assert not any(why_text in step for step in report.actionable_next_steps), \
        "actionable_next_steps should not repeat gap.if_provided"
    # Step text mentions the predicate (so the user knows which one).
    assert any("stays_up_late" in step
               for step in report.actionable_next_steps)


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

    # Target-side line: "P*(age, sex, bmi) 在 user 上". It used to read
    # "P*(...) on user" — the one label in this table that said its
    # preposition in English while its sibling below said it in Chinese.
    # Neither reader was being written for; both now are.
    target_line = next(s for s in fix_steps if "P*(" in s)
    assert "P*(age, sex, bmi)" in target_line
    assert "在 user 上" in target_line
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
    derivation = (_hedge_step(),)
    report = compute_data_gap_report(
        query_kind=QueryKind.IDENTIFY,
        status=ResultStatus.NEEDS_INVESTIGATION,
        derivation=derivation,
    )
    assert any(s.startswith("或：") for s in report.actionable_next_steps)


# ================================================== graph-CPT mismatch


def test_dsep_refusal_reason_routes_to_graph_theta_mismatch_not_missing_distribution():
    """A lookup that failed because theta contradicts the
    declared graph wants the opposite repair from one that failed because
    theta is short of an entry, so it is its own species. The report used
    to tell them apart by searching the reason text for a phrase; the
    d-sep guard now says which it raised (``InsufficientTheta.gap``) and
    the reason text is only prose."""
    requests = (_param_request([(
        "parameter:P(m2=true|m1=true,x=true)",
        _mismatch("P(m2=true|m1=true,x=true)", have="P(m2=true|x=true)", variable="m2",
                  extras="m1", conditioning="x"),
    )]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH in kinds
    assert GapKind.MISSING_DISTRIBUTION not in kinds


def test_graph_theta_mismatch_severity_is_important_not_blocking():
    """The mismatch is a model-input inconsistency, not a data shortage —
    blocking would force users to "supply more data" they already
    supplied. Important is correct."""
    requests = (_param_request([(
        "parameter:P(y=true|x=true,z=true)",
        _mismatch("P(y=true|x=true,z=true)", have="P(y=true|x=true)", variable="y",
                  extras="z", conditioning="x"),
    )]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = next(
        g for g in report.gaps
        if g.kind == GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH
    )
    assert g.severity == GapSeverity.IMPORTANT


def test_graph_theta_mismatch_alternative_paths_name_structural_repairs():
    """The user's actionable fix is
    structural — drop the offending edge OR supply the demanded
    conditional. "Fetch more data" is NOT one of these. Pin: at least
    two of the alternative_paths describe structural fixes."""
    requests = (_param_request([(
        "parameter:P(m2=true|m1=true,x=true)",
        _mismatch("P(m2=true|m1=true,x=true)", have="P(m2=true|x=true)", variable="m2",
                  extras="m1", conditioning="x"),
    )]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = next(
        g for g in report.gaps
        if g.kind == GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH
    )
    paths = " | ".join(g.alternative_paths)
    # Either repair side must surface explicitly.
    assert "条件量" in paths or "补充" in paths
    assert "删除" in paths or "改图" in paths


def test_regular_missing_distribution_still_fires_when_no_dsep_refusal():
    """Sanity: items with empty / non-refusal reasons still route to
    MISSING_DISTRIBUTION — the route the d-sep branch does not touch."""
    requests = (_param_request([
        ("parameter:P(y=true|x=true)", None),
        ("parameter:P(z=true|x=true)",
         dict(need=_LACKS, key="P(z=True|x=True)")),
    ]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    kinds = [g.kind for g in report.gaps]
    assert GapKind.MISSING_DISTRIBUTION in kinds
    assert GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH not in kinds


def test_graph_theta_mismatch_provenance_is_investigation_request():
    """T10-3 needs provenance to match the registered ref_kind set."""
    requests = (_param_request([(
        "parameter:P(y=true|x=true,m=true)",
        _mismatch("P(y=true|x=true,m=true)", have="P(y=true|x=true)", variable="y",
                  extras="m", conditioning="x"),
    )]),)
    report = compute_data_gap_report(
        query_kind=QueryKind.EFFECT,
        status=ResultStatus.NEEDS_INVESTIGATION,
        investigation_requests=requests,
    )
    g = next(
        g for g in report.gaps
        if g.kind == GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH
    )
    assert len(g.provenance) >= 1
    assert g.provenance[0].ref_kind == GapRefKind.INVESTIGATION_REQUEST


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
