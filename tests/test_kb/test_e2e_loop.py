"""S.11.2.7 — full closed-loop end-to-end through transport gaps.

Drives a transport program through:
  themis.run
   → data_gap_report (transport_source_conditional_unknown)
   → gap_to_kb_query
   → WebSearchProxyAdapter (mock data)
   → kb_results_to_bundle
   → apply_patch_and_run
   → themis.verify

Subagent stress test on the Phase 11.2 contract caught a bug here:
SelectionNode was missing from kernel._statement_to_dict, so any
transport program crashed apply_patch_and_run with TypeError. This
test pins that fix and validates the whole KB-adapter loop end-to-end.
"""
from __future__ import annotations

import json

import themis
from themis.kb import (
    KBCache,
    KBQuery,
    KBQueryKind,
    KBRegistry,
    gap_to_kb_query,
    kb_results_to_bundle,
)
from themis.kb.adapters.websearch_proxy import (
    ParsedSearchResult,
    WebSearchProxyAdapter,
    static_table_search,
)


def _transport_program() -> dict:
    """Minimal transport program: aspirin → heart_attack with one
    selection node on age. Mimics the canonical S.11.2 test case."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "aspirin",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "heart_attack",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "age"},
            {
                "kind": "cause",
                "from": {"predicate": "aspirin",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "heart_attack",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "cause",
                "from": {"predicate": "age",
                         "args": [{"type": "const", "name": "me"}]},
                "to": {"predicate": "heart_attack",
                       "args": [{"type": "const", "name": "me"}]},
                "annotations": {"source": "llm_proposal"},
            },
            {
                "kind": "selection_node",
                "id": "S_age",
                "affects": {"predicate": "age",
                            "args": [{"type": "const", "name": "me"}]},
                "source_population": "rct_aspirin_2020",
                "target_population": "user",
            },
            {
                "kind": "query",
                "id": "q",
                "query": {
                    "kind": "effect",
                    "intervention": {
                        "atom": {"predicate": "aspirin",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "target": {
                        "atom": {"predicate": "heart_attack",
                                 "args": [{"type": "const", "name": "me"}]},
                        "value": True,
                    },
                    "given": [],
                    "target_population": "user",
                },
            },
        ],
    }


def test_transport_round_trip_through_apply_patch_and_run():
    """Regression: SelectionNode must serialize back to dict shape so
    apply_patch_and_run can rebuild + re-run the program."""
    program = _transport_program()
    envelope = themis.run(program)
    assert "results" in envelope
    # apply_patch_and_run must NOT crash on SelectionNode reserialization
    refreshed = themis.apply_patch_and_run(program, [])
    assert "results" in refreshed
    # Same status as the no-patch run
    assert refreshed["results"][0]["status"] == envelope["results"][0]["status"]


def test_transport_kb_loop_end_to_end():
    """Full Phase 11.2 closed loop on a transport program."""
    program = _transport_program()
    envelope = themis.run(program)
    result = envelope["results"][0]

    # The kernel returned a transport identification structure +
    # non-empty data_gap_report
    assert result.get("data_gap_report") is not None
    gaps = result["data_gap_report"]["gaps"]
    assert len(gaps) >= 1

    # Pick the first transport gap (target marginal or source conditional)
    transport_gap_dict = next(
        g for g in gaps
        if g["kind"] in (
            "transport_target_distribution_unknown",
            "transport_source_conditional_unknown",
        )
    )

    # Reconstruct a typed DataGap so gap_to_kb_query accepts it.
    # In real client code this comes from a richer types layer; here
    # we build a minimal one that exercises the translator.
    from themis.types import (
        DataGap, GapBlocks, GapKind, GapProvenanceRef, GapRefKind,
        GapRequiredData, GapSeverity, RequiredDataType,
    )
    rd = transport_gap_dict.get("required_data") or {}
    typed_gap = DataGap(
        kind=GapKind(transport_gap_dict["kind"]),
        severity=GapSeverity(transport_gap_dict["severity"]),
        description=transport_gap_dict.get("description", ""),
        blocks=GapBlocks(transport_gap_dict.get("blocks", "point_estimate")),
        provenance=tuple(
            GapProvenanceRef(GapRefKind(p["ref_kind"]), p["ref_id"])
            for p in transport_gap_dict.get("provenance", [])
        ),
        required_data=GapRequiredData(
            data_type=RequiredDataType(rd["data_type"]) if rd.get("data_type") else None,
            population=rd.get("population"),
            variables=tuple(rd.get("variables", ())),
        ) if rd else None,
    )

    # Build the KBQuery
    target_atom = {"predicate": "heart_attack",
                   "args": [{"type": "const", "name": "me"}],
                   "value": True}
    given_atoms = ({"predicate": "aspirin",
                    "args": [{"type": "const", "name": "me"}],
                    "value": True},)
    q = gap_to_kb_query(
        typed_gap,
        target=target_atom,
        given=given_atoms,
        kb_hint="websearch_proxy",
    )
    assert q is not None
    # transport_source_conditional_unknown maps to STRATIFIED_SUBGROUP;
    # transport_target_distribution_unknown maps to TARGET_POPULATION_MARGINAL.
    assert q.query_kind in (
        KBQueryKind.STRATIFIED_SUBGROUP,
        KBQueryKind.TARGET_POPULATION_MARGINAL,
    )
    assert q.kb_name == "websearch_proxy"

    # Mock adapter — returns a plausible answer
    table = {
        ("websearch_proxy", "heart_attack"): ParsedSearchResult(
            value=0.018,
            interval=(0.012, 0.026),
            sample_size=15000,
            citation="PMID:30146931",
            raw_response="Cochrane meta-analysis 2018...",
            confidence_grade="rct_meta_analysis",
        ),
    }
    adapter = WebSearchProxyAdapter(static_table_search(table))
    reg = KBRegistry()
    reg.register(adapter)

    found = reg.find(q)
    assert found is adapter
    kb_result = found.query(q)
    assert kb_result.success
    assert kb_result.value == 0.018

    # Convert to a parameter_fill_bundle
    bundle = kb_results_to_bundle([kb_result])
    assert bundle["kind"] == "parameter_fill_bundle"
    assert len(bundle["skeletons"]) == 1
    assert bundle["skeletons"][0]["annotations"]["source"] == "PMID:30146931"

    # Apply the patch — this is where the SelectionNode round-trip bug
    # used to crash before B1 fix
    refreshed = themis.apply_patch_and_run(program, [bundle])
    assert "results" in refreshed
    # The patch was accepted; new envelope is a valid result
    assert isinstance(refreshed["results"][0]["status"], str)


def test_cache_round_trip_in_e2e_loop():
    """Cache stores and retrieves a real KBResult identically."""
    q = KBQuery(
        kb_name="websearch_proxy",
        query_kind=KBQueryKind.STRATIFIED_SUBGROUP,
        target={"predicate": "y", "value": True},
    )
    table = {
        ("websearch_proxy", "y"): ParsedSearchResult(
            value=0.5, citation="PMID:1", raw_response="r",
        ),
    }
    adapter = WebSearchProxyAdapter(static_table_search(table))
    result = adapter.query(q)

    with KBCache() as cache:
        cache.put(q, result)
        got = cache.get(q)
        assert got == result
