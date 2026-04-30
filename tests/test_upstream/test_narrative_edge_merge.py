"""Phase 4 slice: narrative edge-merge tests.

Symmetric to ``test_narrative_merge.py``: covers
``merge_edge_extractions`` (combine multiple A2 outputs) and
``merge_edges_into_program`` (inject narrative-extracted edges into
a kernel_ast). Pure JSON-in / JSON-out; no typed Program, no LLM.
"""
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest

import themis


REPO_ROOT = Path(__file__).resolve().parents[2]
from themis.upstream import (
    ExtractionShapeError,
    MergeConflictError,
    apply_edge_refusals,
    apply_predicate_links_to_edges,
    compose_program,
    diagnose_edge_predicate_links,
    merge_edge_extractions,
    merge_edges_into_program,
    merge_narrative_ambiguities_into_program,
)


# ======================================================= helpers


def _cause(src: str, dst: str, evidence: str | None = None) -> dict:
    e = {
        "kind": "cause",
        "from": {"predicate": src},
        "to": {"predicate": dst},
        "annotations": {"source": "narrative_proposal"},
    }
    if evidence:
        e["annotations"]["evidence"] = evidence
    return e


def _bidir(a: str, b: str, evidence: str | None = None) -> dict:
    e = {
        "kind": "bidirected",
        "left": {"predicate": a},
        "right": {"predicate": b},
        "annotations": {"source": "narrative_proposal"},
    }
    if evidence:
        e["annotations"]["evidence"] = evidence
    return e


def _refusal(src: str, dst: str, reason: str) -> dict:
    return {
        "kind": "refuse_direct_edge",
        "from": src,
        "to": dst,
        "reason": reason,
    }


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _empty_program(predicates) -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": p, "domain": [True, False]}
            for p in predicates
        ],
    }


# ======================================================= merge_edge_extractions


def test_merge_zero_extractions_returns_empty():
    out = merge_edge_extractions()
    assert out == {"edges": [], "refusals": [], "narrative_ambiguities": []}


def test_merge_single_passthrough():
    a = {
        "edges": [_cause("x", "y", "evidence text")],
        "refusals": [],
        "narrative_ambiguities": [],
    }
    out = merge_edge_extractions(a)
    assert len(out["edges"]) == 1
    assert out["edges"][0]["from"]["predicate"] == "x"
    assert out["edges"][0]["annotations"]["evidence"] == "evidence text"


def test_merge_dedups_same_cause_combines_evidence():
    a = {"edges": [_cause("x", "y", "段落 A 证据")]}
    b = {"edges": [_cause("x", "y", "段落 B 证据")]}
    out = merge_edge_extractions(a, b)
    assert len(out["edges"]) == 1
    ev = out["edges"][0]["annotations"]["evidence"]
    assert isinstance(ev, list)
    assert "段落 A 证据" in ev and "段落 B 证据" in ev


def test_merge_dedups_same_evidence_string_kept_once():
    a = {"edges": [_cause("x", "y", "same")]}
    b = {"edges": [_cause("x", "y", "same")]}
    out = merge_edge_extractions(a, b)
    assert out["edges"][0]["annotations"]["evidence"] == "same"


def test_merge_bidirected_pair_is_unordered():
    a = {"edges": [_bidir("x", "y")]}
    b = {"edges": [_bidir("y", "x")]}
    out = merge_edge_extractions(a, b)
    assert len(out["edges"]) == 1


def test_merge_cause_and_bidirected_coexist_no_conflict():
    """ADMG semantics: cause(X→Y) + bidirected(X↔Y) can coexist on the same
    pair (a directed edge plus an unobserved confounder). Both edges are
    kept; not a conflict."""
    a = {"edges": [_cause("x", "y")]}
    b = {"edges": [_bidir("x", "y")]}
    out = merge_edge_extractions(a, b)
    kinds = {e["kind"] for e in out["edges"]}
    assert kinds == {"cause", "bidirected"}
    assert len(out["edges"]) == 2


def test_merge_cause_vs_refusal_conflict_raises():
    a = {"edges": [_cause("x", "y")]}
    b = {"edges": [], "refusals": [_refusal("x", "y", "looks like confounder")]}
    with pytest.raises(MergeConflictError, match="refusal vs"):
        merge_edge_extractions(a, b)


def test_merge_bidirected_vs_refusal_conflict_raises():
    a = {"edges": [_bidir("x", "y")]}
    b = {"edges": [], "refusals": [_refusal("x", "y", "selection bias")]}
    with pytest.raises(MergeConflictError, match="refusal vs"):
        merge_edge_extractions(a, b)


def test_merge_concrete_citation_beats_narrative_proposal():
    a = {"edges": [{
        "kind": "cause",
        "from": {"predicate": "x"},
        "to": {"predicate": "y"},
        "annotations": {"source": "PubMed:12345", "evidence": "RCT"},
    }]}
    b = {"edges": [_cause("x", "y", "narrative")]}
    out = merge_edge_extractions(a, b)
    assert out["edges"][0]["annotations"]["source"] == "PubMed:12345"


def test_merge_refusals_dedup_by_pair():
    a = {"edges": [], "refusals": [_refusal("x", "y", "first")]}
    b = {"edges": [], "refusals": [_refusal("x", "y", "second")]}
    out = merge_edge_extractions(a, b)
    assert len(out["refusals"]) == 1
    # First wins; we don't try to combine reasons.
    assert out["refusals"][0]["reason"] == "first"


def test_merge_concatenates_narrative_ambiguities():
    a = {"edges": [], "narrative_ambiguities": [{"kind": "temporal", "description": "A"}]}
    b = {"edges": [], "narrative_ambiguities": [{"kind": "scope", "description": "B"}]}
    out = merge_edge_extractions(a, b)
    assert len(out["narrative_ambiguities"]) == 2


def test_merge_shape_validation_rejects_bad_edge():
    bad = {"edges": [{"kind": "cause", "from": {"predicate": "x"}}]}  # missing 'to'
    with pytest.raises(ExtractionShapeError):
        merge_edge_extractions(bad)


def test_merge_shape_validation_rejects_unknown_kind():
    bad = {"edges": [{"kind": "wishful", "from": {"predicate": "x"}, "to": {"predicate": "y"}}]}
    with pytest.raises(ExtractionShapeError, match="cause.*bidirected"):
        merge_edge_extractions(bad)


def test_apply_predicate_links_to_edges_rewrites_all_edge_endpoints():
    extraction = {
        "edges": [
            _cause("staying_up_late", "cognitive_slowness", "temporal evidence"),
            _bidir("staying_up_late", "latent_alertness", "shared trait"),
        ],
        "refusals": [
            _refusal("cognitive_slowness", "latent_alertness", "reverse"),
        ],
        "narrative_ambiguities": [{"kind": "alias", "description": "drift"}],
    }
    links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "staying_up_late",
                "target_predicate": "stays_up_late",
            },
            {
                "source_predicate": "cognitive_slowness",
                "target_predicate": "feels_tired_next_morning",
            },
        ],
    }

    out = apply_predicate_links_to_edges(extraction, links)

    assert out["edges"][0]["from"]["predicate"] == "stays_up_late"
    assert out["edges"][0]["to"]["predicate"] == "feels_tired_next_morning"
    assert out["edges"][1]["left"]["predicate"] == "stays_up_late"
    assert out["edges"][1]["right"]["predicate"] == "latent_alertness"
    assert out["refusals"][0]["from"] == "feels_tired_next_morning"
    assert out["refusals"][0]["to"] == "latent_alertness"
    assert out["narrative_ambiguities"] == extraction["narrative_ambiguities"]
    assert extraction["edges"][0]["from"]["predicate"] == "staying_up_late"


def test_apply_predicate_links_to_edges_dedups_collapsed_edges_with_evidence():
    extraction = {
        "edges": [
            _cause("jogging", "health_improved", "first span"),
            _cause("running", "health_improved", "second span"),
        ],
    }
    links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "jogging",
                "target_predicate": "running",
            },
        ],
    }

    out = apply_predicate_links_to_edges(extraction, links)

    assert len(out["edges"]) == 1
    edge = out["edges"][0]
    assert edge["from"]["predicate"] == "running"
    assert edge["to"]["predicate"] == "health_improved"
    assert edge["annotations"]["evidence"] == ["first span", "second span"]


def test_diagnose_edge_predicate_links_reports_unmatched_endpoints_once():
    program = _empty_program(["stays_up_late", "feels_tired_next_morning"])
    extraction = {
        "edges": [
            _cause("staying_up_late", "cognitive_slowness"),
        ],
        "refusals": [
            _refusal("staying_up_late", "cognitive_slowness", "same drift"),
        ],
    }

    diagnostic = diagnose_edge_predicate_links(program, extraction)

    assert diagnostic["kind"] == "edge_predicate_link_diagnostic"
    unmatched = {
        item["source_predicate"]: item
        for item in diagnostic["unmatched"]
    }
    assert set(unmatched) == {"cognitive_slowness", "staying_up_late"}
    assert (
        unmatched["staying_up_late"]["candidates"][0]["target_predicate"]
        == "stays_up_late"
    )
    assert len(diagnostic["unmatched"]) == 2


# ======================================================= merge_edges_into_program


def test_merge_into_program_inserts_cause_with_args():
    prog = _empty_program(["x", "y"])
    extraction = {"edges": [_cause("x", "y", "narrative says so")]}
    out = merge_edges_into_program(prog, extraction)
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # Atom args should be filled with [{type:const, name:me}] per A2 contract
    assert causes[0]["from"]["args"] == [{"type": "const", "name": "me"}]
    assert causes[0]["to"]["args"] == [{"type": "const", "name": "me"}]
    assert causes[0]["annotations"]["evidence"] == "narrative says so"


def test_merge_into_program_skips_existing_pair():
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "cause", "from": _atom("x"), "to": _atom("y"),
        "annotations": {"source": "manual"},
    })
    extraction = {"edges": [_cause("x", "y", "narrative")]}
    out = merge_edges_into_program(prog, extraction)
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # Existing wins on annotations
    assert causes[0]["annotations"]["source"] == "manual"


def test_merge_into_program_allows_cause_plus_bidirected_coexistence():
    """ADMG: program with existing cause(x→y) accepts incoming bidirected(x↔y)."""
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "cause", "from": _atom("x"), "to": _atom("y"),
    })
    extraction = {"edges": [_bidir("x", "y")]}
    out = merge_edges_into_program(prog, extraction)
    kinds = [s["kind"] for s in out["statements"] if s.get("kind") in ("cause", "bidirected")]
    assert "cause" in kinds and "bidirected" in kinds


def test_merge_into_program_inserts_bidirected_with_args():
    prog = _empty_program(["x", "y"])
    extraction = {"edges": [_bidir("x", "y", "shared latent trait")]}
    out = merge_edges_into_program(prog, extraction)
    bs = [s for s in out["statements"] if s.get("kind") == "bidirected"]
    assert len(bs) == 1
    assert bs[0]["left"]["args"] == [{"type": "const", "name": "me"}]
    assert bs[0]["right"]["args"] == [{"type": "const", "name": "me"}]


def test_merge_into_program_preserves_time_index_on_atoms():
    """A1 §2c uses ``time_index`` to encode t-1→t lag; preserve it
    when injecting cause/bidirected edges so V-set construction sees
    the same time-indexed atoms the query references."""
    prog = _empty_program(["x", "y"])
    extraction = {"edges": [{
        "kind": "cause",
        "from": {"predicate": "x", "time_index": {"kind": "relative", "value": -1}},
        "to": {"predicate": "y", "time_index": {"kind": "relative", "value": 0}},
        "annotations": {"source": "narrative_proposal"},
    }]}
    out = merge_edges_into_program(prog, extraction)
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # time_index preserved from A2 atoms; args injected as [const me]
    assert causes[0]["from"]["time_index"] == {"kind": "relative", "value": -1}
    assert causes[0]["to"]["time_index"] == {"kind": "relative", "value": 0}
    assert causes[0]["from"]["args"] == [{"type": "const", "name": "me"}]


def test_merge_into_program_does_not_mutate_input():
    prog = _empty_program(["x", "y"])
    original = dict(prog)
    original_statements = list(prog["statements"])
    extraction = {"edges": [_cause("x", "y")]}
    merge_edges_into_program(prog, extraction)
    assert prog["statements"] == original_statements


def test_end_to_end_program_runs_after_edge_merge():
    """Sanity: a program with merged narrative edges still parses + runs."""
    prog = _empty_program(["x", "y"])
    prog["statements"].append({
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "assoc",
            "left": _atom("x"),
            "right": _atom("y"),
            "given": [],
        },
    })
    extraction = {"edges": [_cause("x", "y", "narrative evidence")]}
    merged = merge_edges_into_program(prog, extraction)
    out = themis.run(merged)
    assert "results" in out
    assert out["results"][0].get("status")


# ======================================================= compose_program (end-to-end glue)


def test_compose_program_with_both_extractions():
    """A1 question-side program + A5 variable extraction + A2 edge extraction → kernel_ast."""
    base = _empty_program(["x"])  # A1 only knows x from the question
    base["statements"].append({
        "kind": "query",
        "id": "q",
        "query": {
            "kind": "assoc",
            "left": _atom("x"),
            "right": _atom("y"),
            "given": [],
        },
    })
    var_extraction = {
        "variables": [
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
        ],
    }
    edge_extraction = {"edges": [_cause("x", "y", "narrative says X then Y")]}

    out = compose_program(base, var_extraction, edge_extraction)
    # y was added from A5
    preds = {s["predicate"] for s in out["statements"] if s.get("kind") == "variable"}
    assert preds == {"x", "y"}
    # cause edge was added from A2
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert len(causes) == 1
    # full program runs through themis
    result = themis.run(out)
    assert result["results"][0].get("status")


def test_compose_program_applies_confirmed_predicate_links_to_variables_and_edges():
    base = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "stays_up_late", "domain": [True, False]},
            {"kind": "variable", "predicate": "feels_tired_next_morning", "domain": [True, False]},
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("stays_up_late"),
                    "to": _atom("feels_tired_next_morning"),
                },
            },
        ],
    }
    variables = {
        "variables": [
            {
                "kind": "variable",
                "predicate": "staying_up_late",
                "domain": [True, False],
                "observability": "self-report",
            },
        ],
    }
    edges = {
        "edges": [_cause("staying_up_late", "cognitive_slowness")],
    }
    links = {
        "kind": "predicate_link_bundle",
        "links": [
            {
                "source_predicate": "staying_up_late",
                "target_predicate": "stays_up_late",
            },
            {
                "source_predicate": "cognitive_slowness",
                "target_predicate": "feels_tired_next_morning",
            },
        ],
    }

    out = compose_program(base, variables, edges, predicate_links=links)

    decls = {
        s["predicate"]: s
        for s in out["statements"]
        if s.get("kind") == "variable"
    }
    assert set(decls) == {"feels_tired_next_morning", "stays_up_late"}
    assert decls["stays_up_late"]["observability"] == "self-report"
    causes = [s for s in out["statements"] if s.get("kind") == "cause"]
    assert causes[0]["from"]["predicate"] == "stays_up_late"
    assert causes[0]["to"]["predicate"] == "feels_tired_next_morning"

    result = themis.run(out)["results"][0]
    assert result["structural_result"]["value"] is True


def test_compose_program_skips_none_extractions():
    base = _empty_program(["x", "y"])
    out = compose_program(base, None, None)
    # No-op when both extractions are None
    assert len(out["statements"]) == len(base["statements"])


def test_apply_edge_refusals_removes_exact_question_side_direct_edge():
    base = _empty_program(["eating_ice_cream", "drowning"])
    base["statements"].append({
        "kind": "cause",
        "from": _atom("eating_ice_cream"),
        "to": _atom("drowning"),
        "annotations": {"source": "llm_proposal"},
    })
    edge_extraction = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "prompts"
            / "examples"
            / "narrative_edges_ice_cream_drowning.json"
        ).read_text(encoding="utf-8")
    )

    out = apply_edge_refusals(base, edge_extraction)

    assert any(s.get("kind") == "cause" for s in base["statements"])
    assert [
        s for s in out["statements"]
        if s.get("kind") == "cause"
    ] == []
    ambiguities = out["extensions"]["ambiguities"]
    assert ambiguities[0]["kind"] == "confounder_refusal"
    assert ambiguities[0]["alternatives"] == ["eating_ice_cream -> drowning"]


def test_apply_edge_refusals_keeps_multiple_same_kind_audit_records():
    base = _empty_program(["x1", "y1", "x2", "y2"])
    base["statements"].extend([
        {"kind": "cause", "from": _atom("x1"), "to": _atom("y1")},
        {"kind": "cause", "from": _atom("x2"), "to": _atom("y2")},
    ])
    edge_extraction = {
        "edges": [],
        "refusals": [
            {
                "kind": "refuse_direct_edge",
                "from": "x1",
                "to": "y1",
                "pattern": "confounder",
                "reason": "first confounder",
            },
            {
                "kind": "refuse_direct_edge",
                "from": "x2",
                "to": "y2",
                "pattern": "confounder",
                "reason": "second confounder",
            },
        ],
    }

    out = apply_edge_refusals(base, edge_extraction)

    assert [s for s in out["statements"] if s.get("kind") == "cause"] == []
    ambiguities = out["extensions"]["ambiguities"]
    assert [item["kind"] for item in ambiguities] == [
        "confounder_refusal",
        "confounder_refusal",
    ]
    assert [item["alternatives"] for item in ambiguities] == [
        ["x1 -> y1"],
        ["x2 -> y2"],
    ]


def test_merge_narrative_ambiguities_into_program_preserves_prompt_decision():
    base = _empty_program(["drinks_coffee", "alertness"])
    edge_extraction = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "prompts"
            / "examples"
            / "narrative_edges_coffee_alertness.json"
        ).read_text(encoding="utf-8")
    )

    out = merge_narrative_ambiguities_into_program(base, edge_extraction)

    ambiguity_kinds = [
        item["kind"]
        for item in out["extensions"]["ambiguities"]
    ]
    assert ambiguity_kinds == ["admg_unobserved_common_cause"]
    assert "extensions" not in base


def test_compose_program_applies_narrative_refusal_before_kernel_run():
    base = _empty_program(["eating_ice_cream", "drowning"])
    base["statements"].extend([
        {
            "kind": "cause",
            "from": _atom("eating_ice_cream"),
            "to": _atom("drowning"),
            "annotations": {"source": "llm_proposal"},
        },
        {
            "kind": "query",
            "id": "q",
            "query": {
                "kind": "cause",
                "from": _atom("eating_ice_cream"),
                "to": _atom("drowning"),
            },
        },
    ])
    edge_extraction = json.loads(
        (
            REPO_ROOT
            / "docs"
            / "prompts"
            / "examples"
            / "narrative_edges_ice_cream_drowning.json"
        ).read_text(encoding="utf-8")
    )

    program = compose_program(base, edge_extraction=edge_extraction)
    assert [
        s for s in program["statements"]
        if s.get("kind") == "cause"
    ] == []

    result = themis.run(program)["results"][0]
    assert result["status"] == "structurally_solved"
    assert result["structural_result"]["value"] is False
    ambiguity_kinds = [
        item["kind"]
        for item in program["extensions"]["ambiguities"]
    ]
    assert ambiguity_kinds == ["confounder_refusal", "confounder_refusal"]
    assert any(
        item.get("alternatives") == ["eating_ice_cream -> drowning"]
        for item in program["extensions"]["ambiguities"]
    )
    themis.verify(program, result)


def test_compose_program_does_not_mutate_base():
    base = _empty_program(["x", "y"])
    base_copy = deepcopy(base)
    edge_extraction = {"edges": [_cause("x", "y")]}
    compose_program(base, None, edge_extraction)
    assert base == base_copy


def test_compose_program_with_real_narrative_run_fixture():
    """End-to-end: feed an actual A2 fixture from narrative_to_edges_run/
    plus a hand-curated question-side base, see it run cleanly."""
    fixture_path = (
        REPO_ROOT / "docs" / "eval_set" / "narrative_to_edges_run"
        / "14_late_night_tired_temporal.json"
    )
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    edge_extraction = fixture["narrative_to_edges_output"]

    # A1-side question: "熬夜会让我第二天累吗?" → simplest assoc query.
    # The narrative declares both predicates; A2 supplies the edge.
    var_extraction = {
        "variables": [
            {"kind": "variable", "predicate": "stays_up_late", "domain": [True, False]},
            {"kind": "variable", "predicate": "feels_tired_next_morning", "domain": [True, False]},
        ],
    }
    base = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "query", "id": "q", "query": {
                "kind": "assoc",
                "left": _atom("stays_up_late"),
                "right": _atom("feels_tired_next_morning"),
                "given": [],
            }},
        ],
    }

    program = compose_program(base, var_extraction, edge_extraction)

    # Variables and edge were folded in
    kinds = [s.get("kind") for s in program["statements"]]
    assert "variable" in kinds
    assert "cause" in kinds
    # And it actually runs through the kernel
    result = themis.run(program)
    assert result["results"][0]["status"] in (
        "structurally_solved", "needs_investigation", "numerically_solved",
    )
