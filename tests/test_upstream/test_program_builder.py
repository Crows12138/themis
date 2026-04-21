"""Slice W1: extraction-dict → Program conversion tests.

Happy-path tests assert that the generated Program has the expected
statements (declarations, edges, query) and that dispatch_all runs on
it cleanly; error-path tests pin each validation error.
"""
from __future__ import annotations

import pytest

from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import dispatch_all
from themis.types import (
    AssocQuery,
    CauseQuery,
    CauseStatement,
    EffectQuery,
    InvestigationAction,
    QueryKind,
    QueryStatement,
    ResultStatus,
    VariableDeclaration,
)
from themis.upstream import (
    ExtractionError,
    build_program_from_extraction,
)


# ================================================================ effect

def _running_belly_fat_extraction() -> dict:
    """The W0 driving case: 我每天跑步，肚子上的肉会瘦下来吗."""
    return {
        "query_kind": "effect",
        "predicates": ["running", "belly_fat_loss"],
        "edges": [["running", "belly_fat_loss"]],
        "query": {
            "target": {"name": "belly_fat_loss", "value": True},
            "intervention": {"name": "running", "value": True},
            "given": [],
        },
    }


def test_build_effect_program_matches_w0_shape():
    program = build_program_from_extraction(_running_belly_fat_extraction())

    decls = [s for s in program.statements if isinstance(s, VariableDeclaration)]
    assert [d.predicate for d in decls] == ["running", "belly_fat_loss"]
    # Each declaration is bool-only, framing fields unset — this is
    # what drives A0 / F1 to flag time_window etc. as missing.
    for d in decls:
        assert d.domain == (True, False)
        assert d.time_window is None
        assert d.measurement is None
        assert d.threshold is None
        assert d.observability is None

    edges = [s for s in program.statements if isinstance(s, CauseStatement)]
    assert len(edges) == 1
    assert edges[0].from_atom.predicate == "running"
    assert edges[0].to_atom.predicate == "belly_fat_loss"

    queries = [s for s in program.statements if isinstance(s, QueryStatement)]
    assert len(queries) == 1
    assert isinstance(queries[0].query, EffectQuery)
    assert queries[0].query.target.atom.predicate == "belly_fat_loss"
    assert queries[0].query.target.value is True
    assert queries[0].query.intervention.atom.predicate == "running"
    assert queries[0].query.intervention.value is True


def test_effect_program_dispatches_and_surfaces_define_variable_request():
    """End-to-end through dispatch_all: the Program must produce the
    same DEFINE_VARIABLE investigation seen in the W0 walkthrough."""
    program = build_program_from_extraction(_running_belly_fat_extraction())
    graph = project(instantiate(program))
    results = dispatch_all(program, graph)
    assert len(results) == 1
    r = results[0]
    assert r.status is ResultStatus.NEEDS_INVESTIGATION
    assert r.query_kind is QueryKind.EFFECT

    define_requests = [
        req for req in r.investigation_requests
        if req.action is InvestigationAction.DEFINE_VARIABLE
    ]
    assert len(define_requests) == 1
    targets = {item.target for item in define_requests[0].items}
    assert targets == {"running", "belly_fat_loss"}
    # Every flagged predicate is missing exactly the seven framing
    # fields (post-#41): the four original + direction / baseline /
    # state_vs_event.
    for item in define_requests[0].items:
        fields = set(item.skeleton["fields"].keys())
        assert fields == {
            "time_window", "measurement", "threshold", "observability",
            "direction", "baseline", "state_vs_event",
        }


# ================================================================= cause

def test_build_cause_program():
    extraction = {
        "query_kind": "cause",
        "predicates": ["smoking", "lung_cancer"],
        "edges": [["smoking", "lung_cancer"]],
        "query": {"from": "smoking", "to": "lung_cancer"},
    }
    program = build_program_from_extraction(extraction)
    q = next(s for s in program.statements if isinstance(s, QueryStatement))
    assert isinstance(q.query, CauseQuery)
    assert q.query.from_atom.predicate == "smoking"
    assert q.query.to_atom.predicate == "lung_cancer"


def test_build_cause_program_runs_through_dispatch():
    extraction = {
        "query_kind": "cause",
        "predicates": ["a", "b"],
        "edges": [["a", "b"]],
        "query": {"from": "a", "to": "b"},
    }
    program = build_program_from_extraction(extraction)
    results = dispatch_all(program, project(instantiate(program)))
    assert results[0].query_kind is QueryKind.CAUSE


# ================================================================= assoc

def test_build_assoc_program():
    extraction = {
        "query_kind": "assoc",
        "predicates": ["x", "y", "z"],
        "edges": [["z", "x"], ["z", "y"]],
        "query": {"left": "x", "right": "y", "given": ["z"]},
    }
    program = build_program_from_extraction(extraction)
    q = next(s for s in program.statements if isinstance(s, QueryStatement))
    assert isinstance(q.query, AssocQuery)
    assert q.query.left.predicate == "x"
    assert q.query.right.predicate == "y"
    assert [a.predicate for a in q.query.given] == ["z"]


# ================================================================= errors

def test_rejects_unknown_query_kind():
    with pytest.raises(ExtractionError, match="query_kind"):
        build_program_from_extraction({
            "query_kind": "identify",  # not in W1 scope
            "predicates": ["a", "b"],
            "edges": [],
            "query": {},
        })


def test_rejects_non_dict_input():
    with pytest.raises(ExtractionError, match="must be a dict"):
        build_program_from_extraction([])  # type: ignore[arg-type]


def test_rejects_empty_predicates():
    with pytest.raises(ExtractionError, match="predicates"):
        build_program_from_extraction({
            "query_kind": "effect",
            "predicates": [],
            "edges": [],
            "query": {},
        })


def test_rejects_duplicate_predicate():
    with pytest.raises(ExtractionError, match="duplicate"):
        build_program_from_extraction({
            "query_kind": "cause",
            "predicates": ["x", "x"],
            "edges": [],
            "query": {"from": "x", "to": "x"},
        })


def test_rejects_edge_referencing_unknown_predicate():
    with pytest.raises(ExtractionError, match="not declared"):
        build_program_from_extraction({
            "query_kind": "cause",
            "predicates": ["a"],
            "edges": [["a", "b"]],
            "query": {"from": "a", "to": "a"},
        })


def test_rejects_edge_self_loop():
    with pytest.raises(ExtractionError, match="self-loop"):
        build_program_from_extraction({
            "query_kind": "cause",
            "predicates": ["a", "b"],
            "edges": [["a", "a"]],
            "query": {"from": "a", "to": "b"},
        })


def test_rejects_query_reference_not_in_predicate_set():
    with pytest.raises(ExtractionError, match="declared predicate set"):
        build_program_from_extraction({
            "query_kind": "cause",
            "predicates": ["a", "b"],
            "edges": [],
            "query": {"from": "a", "to": "c"},  # c not declared
        })


def test_rejects_non_bool_value_in_effect_query():
    with pytest.raises(ExtractionError, match="must be a bool"):
        build_program_from_extraction({
            "query_kind": "effect",
            "predicates": ["x", "y"],
            "edges": [["x", "y"]],
            "query": {
                "target":       {"name": "y", "value": "yes"},  # not bool
                "intervention": {"name": "x", "value": True},
                "given": [],
            },
        })


def test_rejects_missing_effect_target():
    with pytest.raises(ExtractionError, match="target"):
        build_program_from_extraction({
            "query_kind": "effect",
            "predicates": ["x", "y"],
            "edges": [["x", "y"]],
            "query": {
                "intervention": {"name": "x", "value": True},
                "given": [],
            },
        })


def test_default_query_id_is_q():
    """Not supplying query_id falls back to 'q' (matches the W0
    walkthrough id)."""
    program = build_program_from_extraction(_running_belly_fat_extraction())
    queries = [s for s in program.statements if isinstance(s, QueryStatement)]
    assert queries[0].id == "q"


def test_custom_query_id_is_honored():
    extraction = _running_belly_fat_extraction()
    extraction["query_id"] = "running_effect"
    program = build_program_from_extraction(extraction)
    queries = [s for s in program.statements if isinstance(s, QueryStatement)]
    assert queries[0].id == "running_effect"
