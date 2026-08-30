"""Slice A1: tests for the variable framing fill-back loop.

Unit tests cover extract / merge / diff in isolation; an end-to-end
test exercises the full loop on the exercise_waist_underframed
fixture and asserts two contracts simultaneously:

- ``framing_notes`` for the patched predicate strictly shrinks
  (fully vanishes when all gaps are filled).
- Query ``status`` / numeric value / confidence are *unchanged* —
  framing is advisory and must never leak into the numeric layer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    Atom,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    FramingNote,
    GapKind,
    Intervention,
    InvestigationAction,
    InvestigationItem,
    InvestigationRequest,
    Priority,
    ProbabilityQuery,
    Program,
    QueryKind,
    QueryResult,
    QueryStatement,
    ResultStatus,
    ValuedAtom,
    VariableDeclaration,
)
from themis.workflow.bundle import Refuses
from themis.workflow.variable_framing import (
    BUNDLE_KIND,
    BUNDLE_VERSION,
    MalformedBundleError,
    PATCH_KIND,
    UnknownPredicateError,
    VariablePatchConflictError,
    diff_framing_runs,
    extract_definition_skeleton,
    extract_framing_skeleton,
    merge_variable_declaration,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "test_e2e"
    / "fixtures"
    / "exercise_waist_underframed.json"
)


def _atom(pred: str, obj: str = "me") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _effect_query(target_pred: str, intervention_pred: str) -> QueryStatement:
    return QueryStatement(
        id="q",
        query=EffectQuery(
            target=ValuedAtom(atom=_atom(target_pred), value=True),
            intervention=Intervention(atom=_atom(intervention_pred), value=True),
            given=(),
        ),
    )


def _synthetic_result(framing_notes: tuple[FramingNote, ...]) -> QueryResult:
    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id="q",
        framing_notes=framing_notes,
    )


# ============================================================ extract

def test_extract_emits_one_patch_per_declared_predicate_with_gaps():
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            VariableDeclaration(predicate="y", domain=(True, False)),
            _effect_query("y", "x"),
        ),
    )
    note = FramingNote(
        predicate="y",
        missing=("time_window", "measurement", "observability"),
    )
    bundle = extract_framing_skeleton(program, [_synthetic_result((note,))])

    assert bundle["kind"] == BUNDLE_KIND
    assert bundle["version"] == BUNDLE_VERSION
    assert len(bundle["patches"]) == 1
    patch = bundle["patches"][0]
    assert patch["kind"] == PATCH_KIND
    assert patch["predicate"] == "y"
    # existing shows what is already declared (read-only context)
    assert patch["existing"] == {"domain": [True, False]}
    # fields exposes only the gap fields, all null
    assert set(patch["fields"].keys()) == {
        "time_window", "measurement", "observability",
    }
    assert all(v is None for v in patch["fields"].values())


def test_extract_dedupes_across_multiple_results_with_same_predicate():
    """Two queries both flag waist_reduced as underspecified → one
    patch, not two."""
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            VariableDeclaration(predicate="y"),
            _effect_query("y", "x"),
        ),
    )
    note = FramingNote(predicate="y", missing=("time_window",))
    bundle = extract_framing_skeleton(
        program,
        [_synthetic_result((note,)), _synthetic_result((note,))],
    )
    assert len(bundle["patches"]) == 1


def test_extract_skips_predicates_without_declaration():
    """Defensive: framing_notes shouldn't carry undeclared predicates,
    but if one somehow appears, extract silently skips it rather than
    producing a patch that merge would then reject."""
    program = Program(version="0.1", objects=("me",), statements=())
    note = FramingNote(predicate="ghost", missing=("time_window",))
    bundle = extract_framing_skeleton(program, [_synthetic_result((note,))])
    assert bundle["patches"] == []


def test_extract_emits_empty_bundle_when_no_framing_notes():
    program = Program(version="0.1", objects=(), statements=())
    bundle = extract_framing_skeleton(program, [_synthetic_result(())])
    assert bundle["patches"] == []


# ============================================================ merge

def _bundle(*patches) -> dict:
    return {
        "version": BUNDLE_VERSION,
        "kind": BUNDLE_KIND,
        "patches": list(patches),
    }


def _patch(predicate: str, **fields) -> dict:
    return {
        "kind": PATCH_KIND,
        "predicate": predicate,
        "fields": dict(fields),
    }


def test_merge_updates_existing_declaration_in_place():
    program = Program(
        version="0.1",
        objects=(),
        statements=(
            VariableDeclaration(predicate="y", domain=(True, False)),
        ),
    )
    bundle = _bundle(_patch(
        "y",
        time_window="12w",
        measurement="cm",
        threshold=">=3",
        observability="observed",
    ))
    new = merge_variable_declaration(program, bundle)

    # Exactly one VariableDeclaration, same predicate, filled.
    decls = [s for s in new.statements if isinstance(s, VariableDeclaration)]
    assert len(decls) == 1
    d = decls[0]
    assert d.predicate == "y"
    assert d.domain == (True, False)
    assert d.time_window == "12w"
    assert d.measurement == "cm"
    assert d.threshold == ">=3"
    assert d.observability == "observed"


def test_merge_preserves_already_set_fields_when_patch_does_not_override():
    program = Program(
        version="0.1",
        objects=(),
        statements=(
            VariableDeclaration(
                predicate="y", domain=(True, False), time_window="12w"
            ),
        ),
    )
    bundle = _bundle(_patch("y", measurement="cm"))
    new = merge_variable_declaration(program, bundle)
    d = [s for s in new.statements if isinstance(s, VariableDeclaration)][0]
    assert d.domain == (True, False)
    assert d.time_window == "12w"  # preserved
    assert d.measurement == "cm"


def test_merge_accepts_matching_noop_fill():
    """Writing a field to its existing value is a no-op, not a
    conflict — it keeps the patch idempotent."""
    program = Program(
        version="0.1",
        objects=(),
        statements=(
            VariableDeclaration(predicate="y", time_window="12w"),
        ),
    )
    bundle = _bundle(_patch("y", time_window="12w"))
    new = merge_variable_declaration(program, bundle)
    d = [s for s in new.statements if isinstance(s, VariableDeclaration)][0]
    assert d.time_window == "12w"


def test_merge_rejects_conflicting_field_override():
    program = Program(
        version="0.1",
        objects=(),
        statements=(
            VariableDeclaration(predicate="y", time_window="12w"),
        ),
    )
    bundle = _bundle(_patch("y", time_window="4w"))
    with pytest.raises(VariablePatchConflictError) as exc:
        merge_variable_declaration(program, bundle)
    assert exc.value.predicate == "y"
    assert exc.value.field == "time_window"
    assert exc.value.existing == "12w"
    assert exc.value.incoming == "4w"


def test_merge_rejects_patch_for_unknown_predicate():
    program = Program(version="0.1", objects=(), statements=())
    bundle = _bundle(_patch("ghost", time_window="12w"))
    with pytest.raises(UnknownPredicateError) as exc:
        merge_variable_declaration(program, bundle)
    assert exc.value.predicate == "ghost"


def test_merge_never_produces_duplicate_declaration():
    """Explicit guard: even across two patches for the same predicate
    (malformed but possible), merge must not append a second
    VariableDeclaration to statements."""
    program = Program(
        version="0.1",
        objects=(),
        statements=(
            VariableDeclaration(predicate="y"),
        ),
    )
    bundle = _bundle(
        _patch("y", time_window="12w"),
        _patch("y", measurement="cm"),
    )
    new = merge_variable_declaration(program, bundle)
    decls = [s for s in new.statements if isinstance(s, VariableDeclaration)]
    assert len(decls) == 1


def test_merge_completely_unfilled_bundle_returns_input_program():
    program = Program(
        version="0.1",
        objects=(),
        statements=(VariableDeclaration(predicate="y"),),
    )
    bundle = _bundle(_patch("y", time_window=None, measurement=None))
    new = merge_variable_declaration(program, bundle)
    # Same statements tuple (we may return the same or an equal program).
    decls = [s for s in new.statements if isinstance(s, VariableDeclaration)]
    assert decls[0].time_window is None
    assert decls[0].measurement is None


def test_merge_rejects_bundle_with_unknown_field():
    program = Program(
        version="0.1",
        objects=(),
        statements=(VariableDeclaration(predicate="y"),),
    )
    bundle = _bundle({
        "kind": PATCH_KIND,
        "predicate": "y",
        "fields": {"role": "outcome"},  # role is not a patchable field
    })
    with pytest.raises(MalformedBundleError) as raised:
        merge_variable_declaration(program, bundle)
    assert raised.value.species is Refuses.FIELD_IS_NOT_PATCHABLE
    assert raised.value.said["field"] == "role"


def test_merge_rejects_wrong_bundle_kind():
    with pytest.raises(MalformedBundleError) as raised:
        merge_variable_declaration(
            Program(version="0.1", objects=(), statements=()),
            {"version": BUNDLE_VERSION, "kind": "something_else", "patches": []},
        )
    assert raised.value.species is Refuses.KIND_IS_LIMITED_TO


# ============================================================ diff

def _with_gaps(qid: str, predicate: str, gaps: tuple[str, ...]) -> QueryResult:
    return QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        query_id=qid,
        framing_notes=(FramingNote(predicate=predicate, missing=gaps),),
    )


def test_diff_reports_resolved_when_all_gaps_close():
    before = [_with_gaps("q", "y", ("time_window", "measurement"))]
    after = [QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT, query_id="q", framing_notes=(),
    )]
    d = diff_framing_runs(before, after)
    assert any(r["predicate"] == "y" for r in d["framing"]["resolved"])


def test_diff_reports_shrunk_on_partial_fill():
    before = [_with_gaps("q", "y", ("time_window", "measurement"))]
    after = [_with_gaps("q", "y", ("measurement",))]
    d = diff_framing_runs(before, after)
    shrunk = d["framing"]["shrunk"]
    assert len(shrunk) == 1
    assert shrunk[0]["gaps_before"] == ["measurement", "time_window"]
    assert shrunk[0]["gaps_after"] == ["measurement"]


def test_diff_flags_value_drift_when_numeric_result_changes():
    """A0 invariance guard: if numeric value changes between runs
    that only differ by framing metadata, value_drift must surface
    it. In a clean A0 run this list is always empty."""
    before = [QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT,
        query_id="q",
    )]
    from themis.types import NumericResult
    after = [QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT,
        query_id="q", numeric_result=NumericResult(value=0.5),
    )]
    d = diff_framing_runs(before, after)
    assert len(d["value_drift"]) == 1
    assert d["value_drift"][0]["query_id"] == "q"


def test_diff_empty_value_drift_when_results_stable():
    from themis.types import NumericResult
    r = QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT,
        query_id="q", numeric_result=NumericResult(value=0.46),
    )
    assert diff_framing_runs([r], [r])["value_drift"] == []


# ============================================================ e2e loop

def _run_program(program: Program):
    graph = project(instantiate(program))
    return dispatch_all(program, graph)


def test_end_to_end_loop_on_exercise_waist_underframed():
    """Full closed loop:

    1. Run underframed fixture → framing_notes flag waist_reduced.
    2. extract_framing_skeleton produces a patch with four null gaps.
    3. Caller fills all four fields.
    4. merge_variable_declaration updates the single declaration.
    5. Rerun → framing_notes is empty AND numeric result unchanged.
    """
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    before_results = _run_program(program)

    bundle = extract_framing_skeleton(program, before_results)
    assert len(bundle["patches"]) == 1
    patch = bundle["patches"][0]
    assert patch["predicate"] == "waist_reduced"

    # Author fills every gap. Post-#41 that means 7 fields, not 4.
    patch["fields"] = {
        "time_window": "12w",
        "measurement": "waist circumference cm",
        "threshold": ">=3cm",
        "observability": "self-reported",
        "direction": "down",
        "baseline": "prior week",
        "state_vs_event": "state",
    }

    merged = merge_variable_declaration(program, bundle)
    after_results = _run_program(merged)

    # Only one VariableDeclaration for waist_reduced in merged — the
    # original was updated in place, not duplicated.
    decls = [
        s for s in merged.statements
        if isinstance(s, VariableDeclaration) and s.predicate == "waist_reduced"
    ]
    assert len(decls) == 1
    d = decls[0]
    assert d.time_window == "12w"
    assert d.domain == (True, False)  # preserved

    # Rerun: framing closed.
    assert all(r.framing_notes == () for r in after_results)

    # A0 advisory contract: numeric unchanged.
    d = diff_framing_runs(before_results, after_results)
    assert d["value_drift"] == []
    assert any(row["predicate"] == "waist_reduced" for row in d["framing"]["resolved"])


def test_end_to_end_partial_fill_shrinks_without_value_drift():
    """Partial fill is valid progress: gap set strictly shrinks, all
    queries stay numerically identical."""
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    before_results = _run_program(program)

    bundle = extract_framing_skeleton(program, before_results)
    patch = bundle["patches"][0]
    # Fill two of the gaps, leave the rest null. We deliberately fill
    # non-continuous fields (time_window / observability) so the partial
    # fill is a *strict* shrink. Filling a continuous ``measurement`` (e.g.
    # "waist cm") would legitimately OPEN a new threshold gap — a cutpoint
    # only becomes meaningful once the variable is numeric — which is correct
    # behavior but would violate the strict-subset premise this test pins.
    patch["fields"] = {
        "time_window": "12w",
        "observability": "self-reported",
    }

    merged = merge_variable_declaration(program, bundle)
    after_results = _run_program(merged)

    d = diff_framing_runs(before_results, after_results)
    # No resolved entry (still has gaps), one shrunk entry for waist_reduced.
    assert any(
        row["predicate"] == "waist_reduced" for row in d["framing"]["shrunk"]
    )
    assert d["value_drift"] == []


# ============================================================== F1

def _define_variable_requests(r: QueryResult):
    return tuple(
        req for req in r.investigation_requests
        if req.action is InvestigationAction.DEFINE_VARIABLE
    )


def test_scheduler_surfaces_define_variable_request_when_framing_gap_exists():
    """F1: a query that runs cleanly but references a predicate with
    unset framing metadata must carry both the advisory framing_note
    and a DEFINE_VARIABLE investigation_request so the same gap shows
    up as an actionable task, not only as a note."""
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    results = _run_program(program)

    effect_result = next(
        r for r in results if r.query_kind is QueryKind.EFFECT
    )
    assert effect_result.status is ResultStatus.NUMERICALLY_SOLVED
    assert effect_result.framing_notes  # A0 still attaches advisory note
    requests = _define_variable_requests(effect_result)
    assert len(requests) == 1
    req = requests[0]
    assert req.group == "framing"
    assert len(req.items) == 1
    item = req.items[0]
    assert item.target == "waist_reduced"
    assert item.skeleton is not None
    assert item.skeleton["kind"] == PATCH_KIND
    assert item.skeleton["predicate"] == "waist_reduced"
    assert item.skeleton["existing"] == {"domain": [True, False]}
    assert set(item.skeleton["fields"].keys()) == {
        "time_window", "measurement", "observability",
        "direction", "baseline", "state_vs_event",
    }
    assert all(v is None for v in item.skeleton["fields"].values())


def test_scheduler_emits_no_define_variable_request_when_predicate_undeclared():
    """Framing is opt-in per predicate: a query referencing an
    undeclared predicate emits neither a framing_note nor a
    DEFINE_VARIABLE request."""
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            CauseStatement(from_atom=_atom("x"), to_atom=_atom("y")),
            _effect_query("y", "x"),
        ),
    )
    results = _run_program(program)
    for r in results:
        assert r.framing_notes == ()
        assert _define_variable_requests(r) == ()


def test_scheduler_emits_no_define_variable_request_when_fully_declared():
    """Declared + all framing fields set → no advisory, no task."""
    x = _atom("x")
    y = _atom("y")
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            VariableDeclaration(
                predicate="x",
                domain=(True, False),
                time_window="12w",
                measurement="cm",
                threshold=">=3",
                observability="observed",
                direction="up",
                baseline="prior",
                state_vs_event="state",
            ),
            VariableDeclaration(
                predicate="y",
                domain=(True, False),
                time_window="12w",
                measurement="cm",
                threshold=">=3",
                observability="observed",
                direction="up",
                baseline="prior",
                state_vs_event="state",
            ),
            QueryStatement(
                id="q",
                query=ProbabilityQuery(
                    target=ValuedAtom(atom=y, value=True), given=(),
                ),
            ),
        ),
    )
    results = _run_program(program)
    for r in results:
        assert r.framing_notes == ()
        assert _define_variable_requests(r) == ()


def test_scheduler_preserves_parameter_investigation_when_adding_define_variable():
    """A probability query can be both param-missing *and*
    framing-underspecified. Both investigation channels must show up
    on the same result — DEFINE_VARIABLE augments, it does not
    replace."""
    y = _atom("y")
    program = Program(
        version="0.1",
        objects=("me",),
        statements=(
            VariableDeclaration(predicate="y", domain=(True, False)),
            QueryStatement(
                id="q",
                query=ProbabilityQuery(
                    target=ValuedAtom(atom=y, value=True), given=(),
                ),
            ),
        ),
    )
    results = _run_program(program)
    r = results[0]
    assert r.status is ResultStatus.NEEDS_INVESTIGATION
    # Two request groups: the parameter/observation one pushed from
    # missing_information, plus the framing one from F1.
    groups = {req.group for req in r.investigation_requests}
    assert "framing" in groups
    assert groups & {"parameter", "observation"}  # whichever kind it flagged


def test_extract_definition_skeleton_matches_framing_skeleton_shape():
    """F1's extract, starting from investigation_requests, produces a
    bundle identical (up to patch ordering) to A1's extract starting
    from framing_notes — same predicate set, same existing, same
    gap fields."""
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    results = _run_program(program)

    a1 = extract_framing_skeleton(program, results)
    f1 = extract_definition_skeleton(results)

    assert f1["version"] == a1["version"] == BUNDLE_VERSION
    assert f1["kind"] == a1["kind"] == BUNDLE_KIND
    # Both bundles contain the same patch set.
    a1_by_pred = {p["predicate"]: p for p in a1["patches"]}
    f1_by_pred = {p["predicate"]: p for p in f1["patches"]}
    assert set(a1_by_pred) == set(f1_by_pred)
    for predicate in a1_by_pred:
        a_patch = a1_by_pred[predicate]
        f_patch = f1_by_pred[predicate]
        assert f_patch["kind"] == a_patch["kind"] == PATCH_KIND
        assert f_patch["existing"] == a_patch["existing"]
        assert set(f_patch["fields"].keys()) == set(a_patch["fields"].keys())


def test_extract_definition_skeleton_dedupes_across_results():
    """Two QueryResults both carrying a DEFINE_VARIABLE request for the
    same predicate → one patch in the bundle, not two."""
    def _synth_define_result(predicate: str) -> QueryResult:
        skeleton = {
            "kind": PATCH_KIND,
            "predicate": predicate,
            "existing": {},
            "fields": {"time_window": None},
        }
        request = InvestigationRequest(
            action=InvestigationAction.DEFINE_VARIABLE,
            target=predicate,
            priority=Priority.MEDIUM,
            group="framing",
            items=(InvestigationItem(
                target=predicate,
                gap=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
                skeleton=skeleton,
            ),),
        )
        return QueryResult(
            status=ResultStatus.NUMERICALLY_SOLVED,
            query_kind=QueryKind.EFFECT,
            investigation_requests=(request,),
        )

    bundle = extract_definition_skeleton(
        [_synth_define_result("y"), _synth_define_result("y")],
    )
    assert len(bundle["patches"]) == 1
    assert bundle["patches"][0]["predicate"] == "y"


def test_extract_definition_skeleton_returns_detached_patch_copy():
    """Editing the extracted bundle must not mutate the source
    QueryResult's investigation skeleton in place."""
    skeleton = {
        "kind": PATCH_KIND,
        "predicate": "y",
        "existing": {"domain": [True, False]},
        "fields": {"time_window": None},
    }
    request = InvestigationRequest(
        action=InvestigationAction.DEFINE_VARIABLE,
        target="y",
        priority=Priority.MEDIUM,
        group="framing",
        items=(InvestigationItem(
            target="y",
            gap=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
            skeleton=skeleton,
        ),),
    )
    result = QueryResult(
        status=ResultStatus.NUMERICALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
        investigation_requests=(request,),
    )

    bundle = extract_definition_skeleton([result])
    bundle["patches"][0]["fields"]["time_window"] = "12w"
    bundle["patches"][0]["existing"]["domain"][0] = "changed"

    original = result.investigation_requests[0].items[0].skeleton
    assert original["fields"]["time_window"] is None
    assert original["existing"]["domain"] == [True, False]


def test_extract_definition_skeleton_returns_empty_bundle_when_no_gaps():
    program = Program(version="0.1", objects=(), statements=())
    results = _run_program(program)
    bundle = extract_definition_skeleton(results)
    assert bundle["kind"] == BUNDLE_KIND
    assert bundle["version"] == BUNDLE_VERSION
    assert bundle["patches"] == []


def test_end_to_end_define_variable_loop_via_investigation_channel():
    """F1 closed loop, entered from investigation_requests rather than
    framing_notes. After merge, both the notes and the DEFINE_VARIABLE
    request must vanish, with no numeric drift."""
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    program = validate_program(validate_ast(ast))
    before_results = _run_program(program)

    bundle = extract_definition_skeleton(before_results)
    assert len(bundle["patches"]) == 1
    patch = bundle["patches"][0]
    assert patch["predicate"] == "waist_reduced"
    patch["fields"] = {
        "time_window": "12w",
        "measurement": "waist circumference cm",
        "threshold": ">=3cm",
        "observability": "self-reported",
        "direction": "down",
        "baseline": "prior week",
        "state_vs_event": "state",
    }

    merged = merge_variable_declaration(program, bundle)
    after_results = _run_program(merged)

    # Notes and DEFINE_VARIABLE requests both gone.
    for r in after_results:
        assert r.framing_notes == ()
        assert _define_variable_requests(r) == ()

    # Advisory contract: numeric path unchanged.
    d = diff_framing_runs(before_results, after_results)
    assert d["value_drift"] == []
    assert any(
        row["predicate"] == "waist_reduced" for row in d["framing"]["resolved"]
    )
