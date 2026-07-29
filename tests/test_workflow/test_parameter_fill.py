"""Tests for the parameter fill-back workflow (slice 9.x-C).

End-to-end smoke:
    extract -> user fills a value -> merge -> rerun -> diff marks
    the query as resolved.

Plus targeted tests on the pieces:
- dedupe across queries when the same skeleton surfaces twice
- unfilled skeleton raises a specific error carrying indices
- malformed bundle raises early with a clear message
- diff categorises every status transition
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from themis.input.parser import parse_json
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    QueryResult,
    QueryKind,
    ResultStatus,
    StructuralResult,
)
from themis.workflow.parameter_fill import (
    BUNDLE_KIND,
    BUNDLE_VERSION,
    MalformedBundleError,
    UnfilledSkeletonError,
    diff_runs,
    extract_skeleton_bundle,
    merge_skeleton_bundle,
)

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "test_e2e"
    / "fixtures"
    / "numeric_backdoor_missing_parameter.json"
)


def _load_program():
    ast = parse_json(FIXTURE.read_text(encoding="utf-8"))
    validate_ast(ast)
    return validate_program(ast)


def _run(program):
    graph = project(instantiate(program))
    return dispatch_all(program, graph)


# ------------------------------------------------------------ extract

def test_extract_skeleton_bundle_shape():
    results = _run(_load_program())
    bundle = extract_skeleton_bundle(results)
    assert bundle["version"] == BUNDLE_VERSION
    assert bundle["kind"] == BUNDLE_KIND
    assert len(bundle["skeletons"]) == 1
    s = bundle["skeletons"][0]
    assert s["kind"] == "probability"
    assert s["target"]["atom"]["predicate"] == "cancer"
    assert s["target"]["value"] is True
    assert s["value"] is None
    # Given ordering is deterministic (alphabetical by predicate).
    preds = [g["atom"]["predicate"] for g in s["given"]]
    assert preds == ["smokes", "stress"]


def test_extract_skeleton_bundle_empty_when_no_gaps():
    """If every query is solved (or structural), the bundle has
    no skeletons. Synthetic results are used here because no
    fixture currently has all-solved numeric queries only."""
    results = (
        QueryResult(
            status=ResultStatus.STRUCTURALLY_SOLVED,
            query_kind=QueryKind.CAUSE,
            query_id="q_ok",
            structural_result=StructuralResult(value=True),
        ),
    )
    bundle = extract_skeleton_bundle(results)
    assert bundle["skeletons"] == []


def test_extract_skeleton_bundle_dedupes_across_queries():
    """If two queries in one run reference the same missing
    parameter, only one bundle entry emerges."""
    program = _load_program()
    # Append a second effect query asking the same underlying P(Y|X).
    # Simplest way: reuse the same query under a different id.
    from themis.types import (
        EffectQuery,
        Intervention,
        QueryStatement,
        ValuedAtom,
        Atom,
        ConstTerm,
    )

    cancer_va = ValuedAtom(
        atom=Atom(predicate="cancer", args=(ConstTerm(name="alice"),)),
        value=True,
    )
    second = QueryStatement(
        id="effect_cancer_missing_theta_copy",
        query=EffectQuery(
            target=cancer_va,
            intervention=Intervention(
                atom=Atom(predicate="smokes", args=(ConstTerm(name="alice"),)),
                value=False,
            ),
            given=(),
        ),
    )
    enriched = program.statements + (second,)
    from themis.types import Program
    program2 = Program(
        version=program.version,
        objects=program.objects,
        statements=enriched,
    )
    results = _run(program2)
    # Both queries should surface the same missing parameter.
    missing_ids = {r.query_id for r in results if r.missing_information}
    assert len(missing_ids) == 2

    bundle = extract_skeleton_bundle(results)
    # Still only one skeleton after dedupe.
    assert len(bundle["skeletons"]) == 1


# ------------------------------------------------------------- merge

def test_merge_raises_on_unfilled_skeleton():
    program = _load_program()
    bundle = extract_skeleton_bundle(_run(program))
    # Don't fill.
    with pytest.raises(UnfilledSkeletonError) as exc:
        merge_skeleton_bundle(program, bundle)
    assert exc.value.unfilled == [0]


def test_merge_rejects_malformed_bundle():
    with pytest.raises(MalformedBundleError):
        merge_skeleton_bundle(_load_program(), {"no": "kind"})
    with pytest.raises(MalformedBundleError):
        merge_skeleton_bundle(
            _load_program(),
            {"kind": BUNDLE_KIND, "version": "0.2", "skeletons": []},
        )
    with pytest.raises(MalformedBundleError):
        merge_skeleton_bundle(
            _load_program(),
            {"kind": BUNDLE_KIND, "version": BUNDLE_VERSION, "skeletons": "not a list"},
        )


def test_merge_appends_filled_statements():
    program = _load_program()
    bundle = extract_skeleton_bundle(_run(program))
    # Fill the single skeleton with a value.
    bundle_filled = copy.deepcopy(bundle)
    bundle_filled["skeletons"][0]["value"] = 0.2
    new_program = merge_skeleton_bundle(program, bundle_filled)
    # Original statements preserved; one new ProbabilityStatement added.
    assert len(new_program.statements) == len(program.statements) + 1
    from themis.types import ProbabilityStatement
    appended = new_program.statements[-1]
    assert isinstance(appended, ProbabilityStatement)
    assert appended.target.atom.predicate == "cancer"
    assert appended.target.value is True
    assert appended.value == 0.2


# --------------------------------------------------- diff categorisation

def _mk_result(qid, status, value=None, missing_count=0):
    from themis.types import (
        GapKind, NumericResult, MissingItem, MissingKind, Priority,
    )
    return QueryResult(
        status=status,
        query_kind=QueryKind.EFFECT,
        query_id=qid,
        numeric_result=NumericResult(value=value) if value is not None else None,
        missing_information=tuple(
            MissingItem(
                kind=MissingKind.PARAMETER,
                name=f"p{i}",
                priority=Priority.HIGH,
                gap=GapKind.MISSING_DISTRIBUTION,
            )
            for i in range(missing_count)
        ),
    )


def test_diff_marks_resolved_transition():
    before = (_mk_result("q", ResultStatus.NEEDS_INVESTIGATION, missing_count=1),)
    after = (_mk_result("q", ResultStatus.NUMERICALLY_SOLVED, value=0.18),)
    d = diff_runs(before, after)
    assert len(d["resolved"]) == 1
    row = d["resolved"][0]
    assert row["query_id"] == "q"
    assert row["status"] == "numerically_solved"
    assert row["value"] == 0.18
    assert d["still_missing"] == []


def test_diff_marks_still_missing():
    before = (_mk_result("q", ResultStatus.NEEDS_INVESTIGATION, missing_count=2),)
    after = (_mk_result("q", ResultStatus.NEEDS_INVESTIGATION, missing_count=1),)
    d = diff_runs(before, after)
    assert len(d["still_missing"]) == 1
    # Still reports the updated missing_count for progress visibility.
    assert d["still_missing"][0]["missing_count"] == 1


def test_diff_marks_unchanged_when_status_same():
    before = (_mk_result("q", ResultStatus.NUMERICALLY_SOLVED, value=0.18),)
    after = (_mk_result("q", ResultStatus.NUMERICALLY_SOLVED, value=0.18),)
    d = diff_runs(before, after)
    assert len(d["unchanged"]) == 1


# ---------------------------------------------- slice 9.x-C end-to-end loop

def test_full_fill_loop_resolves_case_2():
    """Case 2's single parameter gap, walked through the full loop.

    After filling in the missing CPT value, the effect query that
    previously returned NEEDS_INVESTIGATION now returns
    NUMERICALLY_SOLVED. The diff makes that transition explicit."""
    program = _load_program()
    results_before = _run(program)

    # 1. extract
    bundle = extract_skeleton_bundle(results_before)
    assert len(bundle["skeletons"]) == 1

    # 2. simulate the user filling in a value
    bundle_filled = json.loads(json.dumps(bundle))  # round-trip JSON
    bundle_filled["skeletons"][0]["value"] = 0.5

    # 3. merge
    program_after = merge_skeleton_bundle(program, bundle_filled)

    # 4. re-run
    results_after = _run(program_after)

    # 5. diff: the effect query transitioned from needs_investigation
    # to numerically_solved.
    d = diff_runs(results_before, results_after)
    resolved_ids = {row["query_id"] for row in d["resolved"]}
    assert "effect_cancer_missing_theta" in resolved_ids
    assert d["still_missing"] == []

    # Hand-check the numeric: 0.3 · 0.4 + 0.5 · 0.6 = 0.12 + 0.30 = 0.42
    resolved = next(
        row for row in d["resolved"]
        if row["query_id"] == "effect_cancer_missing_theta"
    )
    assert resolved["value"] == pytest.approx(0.42)
