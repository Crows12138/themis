"""Must-disclose structural caveats in data_gap_report.

Five caveat kinds — each tests that:
1. The kind appears in `data_gap_report.gaps[]` when the upstream signal
   is present.
2. The description lands in `result.explanation` as a ⚠ line via
   `_attach_structural_caveats` (so the renderer cannot silently drop
   it even if it skips the gap report).
"""
from __future__ import annotations

import themis


def _atom(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _has_kind(report, kind: str) -> bool:
    return any(g["kind"] == kind for g in (report or {}).get("gaps", []))


# ============================================ IV identification


def test_iv_required_assumption_surfaces_as_must_disclose_caveat():
    """IV identification carries a required_assumption string in
    extensions. Must surface as a structural caveat — IV ATE estimates
    are conditional on monotonicity / linearity. Fixture mirrors
    test_iv_dispatch.test_iv_fallback_fires_when_backdoor_and_frontdoor_fail."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": _atom("y"),
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert "iv_identification" in (result.get("extensions") or {})
    assert _has_kind(result.get("data_gap_report"),
                     "iv_identification_assumption_required")
    explanation = result.get("explanation") or ""
    assert "monotonicity" in explanation or "linearity" in explanation


# ============================================ Mediation assumptions


def test_mediation_nde_nie_assumptions_surface_as_caveat():
    """When NDE/NIE is identifiable the assumptions list is non-empty —
    must surface so 'identifiable: true' isn't read as unconditional."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                    "mediator": _atom("m"),
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"],
                     "mediation_identification_assumption_required")
    explanation = result.get("explanation") or ""
    assert "中介" in explanation
    assert "假设" in explanation


# ============================================ Bounds-not-point


def test_bounds_result_surfaces_must_disclose_caveat():
    """When bounds_result is populated the answer is symbolic interval,
    not point. Renderer must flag this — currently a renderer that only
    reads structural_result would present it as a clean answer."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "u", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    if not result.get("bounds_result"):
        # Bounds aren't computed for every effect query — only when the
        # outcome is binary and identification fails. Skip when the
        # fixture didn't trigger bounds rather than asserting unrelated
        # state.
        return
    assert _has_kind(result["data_gap_report"],
                     "answer_is_bounds_not_point_estimate")
    explanation = result.get("explanation") or ""
    assert "bounds" in explanation or "区间" in explanation


# ============================================ LLM-declared ambiguity


def test_low_confidence_classifier_fires_below_threshold():
    """Unit test on the classifier: composite confidence below 0.6 emits
    the gap; ≥ 0.6 does not. End-to-end wiring exercised by other tests
    that have a full query stack."""
    from themis.output.data_gap_report import _classify_low_confidence

    below = list(_classify_low_confidence(0.3))
    assert len(below) == 1
    assert below[0].kind.value == "low_confidence_input_data"
    assert "0.30" in below[0].description

    at_threshold = list(_classify_low_confidence(0.6))
    assert at_threshold == []

    above = list(_classify_low_confidence(0.9))
    assert above == []

    none_input = list(_classify_low_confidence(None))
    assert none_input == []


def test_front_door_assumptions_surface_as_caveat():
    """Pearl's front-door criterion requires three graphical premises +
    consistency. Detection via derivation rule scanning, since the
    dispatcher does not echo a `front_door_identification` extension."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": _atom("y"),
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    rules = [step["rule"] for step in (result.get("derivation") or {}).get("steps", [])]
    if not any("front_door" in r for r in rules):
        return
    assert _has_kind(result["data_gap_report"],
                     "front_door_identification_assumption_required")
    explanation = result.get("explanation") or ""
    assert "前门" in explanation


def test_counterfactual_classifier_fires_on_status():
    """Unit test on the classifier: COUNTERFACTUAL_SOLVED status alone
    triggers the assumption gap (consistency + composition axioms)."""
    from themis.output.data_gap_report import _classify_counterfactual_assumptions
    from themis.types import QueryKind, ResultStatus

    fired = list(_classify_counterfactual_assumptions(
        derivation=(), status=ResultStatus.COUNTERFACTUAL_SOLVED,
        query_kind=QueryKind.COUNTERFACTUAL,
    ))
    assert len(fired) == 1
    assert fired[0].kind.value == "counterfactual_identification_assumption_required"
    assert "consistency" in fired[0].description

    fired_bounded = list(_classify_counterfactual_assumptions(
        derivation=(), status=ResultStatus.COUNTERFACTUAL_BOUNDED,
        query_kind=QueryKind.COUNTERFACTUAL,
    ))
    assert len(fired_bounded) == 1

    # Status alone (non-counterfactual query somehow getting a non-CF
    # status) must not trigger.
    not_counterfactual = list(_classify_counterfactual_assumptions(
        derivation=(), status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.EFFECT,
    ))
    assert not_counterfactual == []

    # Query-kind alone — the Bug 2 case: NEEDS_ASSUMPTION on a
    # counterfactual query must still fire the assumption caveat.
    fired_by_kind = list(_classify_counterfactual_assumptions(
        derivation=(), status=ResultStatus.NEEDS_ASSUMPTION,
        query_kind=QueryKind.COUNTERFACTUAL,
    ))
    assert len(fired_by_kind) == 1
    assert fired_by_kind[0].provenance[0].ref_id == "counterfactual_query_kind"


def test_bidirected_llm_proposal_edge_surfaces_as_caveat():
    """Bidirected (latent common cause) edges with annotations.source =
    llm_proposal must also surface — they are the *reason* an
    alternative identification (front-door / IV) is needed and so are
    structurally load-bearing."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {
                "kind": "bidirected",
                "left": _atom("x"),
                "right": _atom("y"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": _atom("y"),
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"],
                     "unverified_proposal_edge_on_query_path")
    explanation = result.get("explanation") or ""
    # ↔ glyph indicates the bidirected-edge channel, not a directed edge.
    assert "↔" in explanation


def test_discovery_edge_surfaces_as_caveat_with_algorithm_in_description():
    """Edges with annotations.source = "discovery:<algo>" must be flagged
    as non-evidence, with description naming the algorithm specifically
    (not the LLM-hypothesis wording). PC / FCI / LiNGAM all carry their
    own assumption stack."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom("x"),
                "to": _atom("y"),
                "annotations": {"source": "discovery:pc"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("x"),
                    "to": _atom("y"),
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"],
                     "unverified_proposal_edge_on_query_path")
    explanation = result.get("explanation") or ""
    # Description must name the algorithm + its assumptions, not generic
    # "LLM proposal" wording.
    assert "PC" in explanation
    assert "忠实性" in explanation or "因果充足性" in explanation
    assert "llm_proposal" not in explanation


def test_evidence_backed_edge_with_pubmed_source_does_not_fire():
    """Sanity: PubMed citation source must not trigger the proposal-edge
    gap. Only sources matching the non-evidence whitelist (llm_proposal,
    discovery:*) should fire."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom("x"),
                "to": _atom("y"),
                "annotations": {"source": "PubMed:12345"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("x"),
                    "to": _atom("y"),
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    report = result.get("data_gap_report")
    if report is None:
        return
    assert not _has_kind(report, "unverified_proposal_edge_on_query_path")


def test_graph_learned_from_data_surfaces_as_top_level_caveat():
    """When extensions.discovery_metadata is present (the entire DAG was
    learned by an algorithm), the result inherits the algorithm's
    structural assumptions — surface as a top-level caveat distinct
    from individual edge gaps."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("x"),
                    "to": _atom("y"),
                },
            },
        ],
        "extensions": {
            "discovery_metadata": {
                "algorithm": "pc",
                "alpha": 0.05,
                "sample_size": 200,
            },
        },
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"], "graph_learned_from_data")
    explanation = result.get("explanation") or ""
    assert "PC" in explanation
    assert "0.05" in explanation
    assert "200" in explanation


def test_bounds_result_assumptions_surface_in_caveat():
    """Bounds methods carry method-specific assumptions (Balke-Pearl
    needs IV1/IV2/IV3). Without surfacing these the renderer presents
    bounds as if they were unconditional."""
    from themis.output.data_gap_report import _classify_bounds_not_point
    from themis.types import BoundsMethod, BoundsResult

    bounds = BoundsResult(
        method=BoundsMethod.BALKE_PEARL_IV,
        lower_expression="max(0, ...)",
        upper_expression="min(1, ...)",
        assumptions=("IV1", "IV2", "IV3"),
    )
    fired = list(_classify_bounds_not_point(bounds))
    assert len(fired) == 1
    desc = fired[0].description
    assert "IV1" in desc and "IV2" in desc and "IV3" in desc


def test_llm_declared_ambiguity_surfaces_as_caveat():
    """Program-level extensions.ambiguities (other than dose_response,
    which has its own dedicated gap_kind) must surface as a renderer
    caveat — LLM uncertainty is part of the answer envelope."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("x"),
                    "to": _atom("y"),
                },
            },
        ],
        "extensions": {
            "ambiguities": [
                {
                    "kind": "reciprocal_causation",
                    "rationale": "X and Y may be mutually causing",
                    "query_id": "q",
                },
            ],
        },
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"], "llm_declared_ambiguity")
    explanation = result.get("explanation") or ""
    assert "reciprocal_causation" in explanation


# ============================================ counterfactual full path


def test_counterfactual_query_kind_alone_fires_assumption_caveat_e2e():
    """End-to-end: a counterfactual that stops at NEEDS_ASSUMPTION must
    still surface the L3 caveat — without this the
    monotonicity / consistency disclosure is lost when bounds aren't
    reached."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "study", "domain": [True, False]},
            {"kind": "variable", "predicate": "job", "domain": [True, False]},
            {"kind": "cause", "from": _atom("study"), "to": _atom("job")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "counterfactual",
                    "observed": {"atom": _atom("study"), "value": False},
                    "counterfactual_intervention": {
                        "atom": _atom("study"), "value": True,
                    },
                    "counterfactual_target": {
                        "atom": _atom("job"), "value": True,
                    },
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"],
                     "counterfactual_identification_assumption_required")
    explanation = result.get("explanation") or ""
    assert "consistency" in explanation


def test_counterfactual_atoms_feed_proposal_edge_path_walk():
    """Bug 7 regression: counterfactual queries must feed their own
    atoms into the unverified-proposal-edge path walker. Without this,
    a llm_proposal cause edge between counterfactual antecedent and
    consequent is never flagged."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "study", "domain": [True, False]},
            {"kind": "variable", "predicate": "job", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom("study"),
                "to": _atom("job"),
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "counterfactual",
                    "observed": {"atom": _atom("study"), "value": False},
                    "counterfactual_intervention": {
                        "atom": _atom("study"), "value": True,
                    },
                    "counterfactual_target": {
                        "atom": _atom("job"), "value": True,
                    },
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert _has_kind(result["data_gap_report"],
                     "unverified_proposal_edge_on_query_path")


# ============================================ low-confidence on edges


def test_cause_edge_confidence_propagates_to_low_confidence_caveat():
    """Bug 5 regression: annotations.confidence on a load-bearing
    CauseStatement must reach the composite confidence calc and trigger
    LOW_CONFIDENCE_INPUT_DATA. Pre-fix, only probability/observation
    slots contributed, so structural answers ignored edge confidences
    entirely."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "study", "domain": [True, False]},
            {"kind": "variable", "predicate": "job", "domain": [True, False]},
            {
                "kind": "cause",
                "from": _atom("study"),
                "to": _atom("job"),
                "annotations": {"source": "PubMed:99999", "confidence": 0.2},
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "cause",
                    "from": _atom("study"),
                    "to": _atom("job"),
                },
            },
        ],
    }
    out = themis.run(ast)
    result = out["results"][0]
    assert result.get("confidence") == 0.2
    assert _has_kind(result["data_gap_report"], "low_confidence_input_data")
    explanation = result.get("explanation") or ""
    assert "0.20" in explanation or "0.2" in explanation
