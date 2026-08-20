"""S.11.2.5 — WebSearchProxyAdapter (reference adapter) tests.

End-to-end happy path: gap → translator query → adapter result →
translator skeleton → bundle. Using static_table_search avoids
network IO.
"""
from __future__ import annotations

import pytest

from themis.kb.adapters.websearch_proxy import (
    ParsedSearchResult,
    WebSearchProxyAdapter,
    static_table_search,
)
from themis.kb.contract import KBRegistry
from themis.kb.schemas import KBConfidenceGrade, KBQuery, KBQueryKind
from themis.kb.translator import (
    gap_to_kb_query,
    kb_results_to_bundle,
)
from themis.types import (
    DataGap,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    RequiredDataType,
)


def _q(predicate: str = "y") -> KBQuery:
    return KBQuery(
        kb_name=WebSearchProxyAdapter.name,
        query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
        target={"predicate": predicate, "value": True},
    )


# --------------------------------------------------------- adapter basics

def test_name_and_supports():
    a = WebSearchProxyAdapter(lambda q: None)
    assert a.name == "websearch_proxy"
    assert a.supports(_q())
    assert not a.supports(_q().__class__(
        kb_name="other", query_kind=KBQueryKind.MARGINAL_DISTRIBUTION,
        target={"predicate": "y"},
    ))


def test_search_returns_none_yields_failure():
    a = WebSearchProxyAdapter(lambda q: None)
    r = a.query(_q())
    assert r.success is False
    assert r.failure_reason == "no_match_or_unparseable"
    assert r.provenance.source_kb == "websearch_proxy"
    assert r.provenance.query_used == _q()


def test_search_missing_value_yields_failure():
    """Parsed dict without 'value' key — treat as no extraction."""
    def search(q):
        return {"citation": "x", "raw_response": "y"}  # no 'value'

    a = WebSearchProxyAdapter(search)  # type: ignore[arg-type]
    assert a.query(_q()).success is False


def test_search_raises_degrades_to_failure():
    def search(q):
        raise RuntimeError("network down")

    a = WebSearchProxyAdapter(search)
    r = a.query(_q())
    assert r.success is False
    assert "search_fn_raised" in r.failure_reason
    assert "RuntimeError" in r.failure_reason


def test_success_basic_value_only():
    parsed: ParsedSearchResult = {
        "value": 0.42,
        "citation": "PMID:111",
        "raw_response": "raw text",
    }
    a = WebSearchProxyAdapter(lambda q: parsed)
    r = a.query(_q())
    assert r.success
    assert r.value == 0.42
    assert r.provenance.citation == "PMID:111"
    assert r.provenance.raw_response_hash.startswith("sha256:")
    assert r.provenance.confidence_grade == KBConfidenceGrade.UNKNOWN


def test_success_with_interval_and_sample_size():
    parsed: ParsedSearchResult = {
        "value": 0.18,
        "interval": (0.12, 0.24),
        "sample_size": 2847,
        "population_in_source": "rct_meta_2023",
        "citation": "PMID:222",
        "raw_response": "...",
        "confidence_grade": "rct_meta_analysis",
    }
    a = WebSearchProxyAdapter(lambda q: parsed)
    r = a.query(_q())
    assert r.value == 0.18
    assert r.interval == (0.12, 0.24)
    assert r.sample_size == 2847
    assert r.population_in_source == "rct_meta_2023"
    assert r.provenance.confidence_grade == KBConfidenceGrade.RCT_META_ANALYSIS


@pytest.mark.parametrize("bad_interval", [
    (0.1, 0.2, 0.3),          # three ends for a field that holds a pair
    (0.1,),                   # one end
    (0.1, "wide"),            # a second end that is not a number
    ("lo", "hi"),             # neither end is a number
    0.15,                     # not a sequence at all
])
def test_interval_that_is_not_a_float_pair_yields_failure(bad_interval):
    """The interval is the one field a search response used to hand over
    unchecked. ``KBResult.interval`` holds a pair, so anything that is not
    one is an unparseable response, not a result with a strange interval."""
    parsed = {
        "value": 0.18,
        "interval": bad_interval,
        "citation": "PMID:333",
        "raw_response": "...",
    }
    a = WebSearchProxyAdapter(lambda q: parsed)  # type: ignore[arg-type]
    r = a.query(_q())
    assert r.success is False
    assert r.failure_reason == "interval_not_a_float_pair"
    assert r.interval is None


@pytest.mark.parametrize("empty", [None, (), []])
def test_absent_interval_is_not_a_failure(empty):
    """An omitted interval is a value without one — the pre-existing
    contract, kept: only a present-but-malformed interval refuses."""
    parsed = {
        "value": 0.18, "interval": empty,
        "citation": "PMID:334", "raw_response": "...",
    }
    a = WebSearchProxyAdapter(lambda q: parsed)  # type: ignore[arg-type]
    r = a.query(_q())
    assert r.success is True
    assert r.interval is None


def test_interval_of_numeric_strings_is_coerced():
    """``value`` and ``sample_size`` were always coerced; the interval was
    only re-containered. It is coerced on the same terms now."""
    parsed = {
        "value": 0.18, "interval": ("0.12", 24),
        "citation": "PMID:335", "raw_response": "...",
    }
    a = WebSearchProxyAdapter(lambda q: parsed)  # type: ignore[arg-type]
    r = a.query(_q())
    assert r.success is True
    assert r.interval == (0.12, 24.0)


def test_unrecognized_grade_coerces_to_unknown():
    parsed: ParsedSearchResult = {
        "value": 0.1,
        "citation": "x",
        "raw_response": "y",
        "confidence_grade": "non_existent_grade",  # type: ignore[typeddict-item]
    }
    a = WebSearchProxyAdapter(lambda q: parsed)
    r = a.query(_q())
    assert r.success
    assert r.provenance.confidence_grade == KBConfidenceGrade.UNKNOWN


def test_no_raw_response_hashes_query():
    """When search_fn omits raw_response, fallback to hashing the query."""
    parsed: ParsedSearchResult = {"value": 0.5, "citation": "x", "raw_response": ""}
    a = WebSearchProxyAdapter(lambda q: parsed)
    r = a.query(_q())
    assert r.provenance.raw_response_hash.startswith("sha256:")
    # Different query → different hash
    other_parsed: ParsedSearchResult = {"value": 0.5, "citation": "x", "raw_response": ""}
    a2 = WebSearchProxyAdapter(lambda q: other_parsed)
    r2 = a2.query(_q("z"))
    assert r.provenance.raw_response_hash != r2.provenance.raw_response_hash


# ----------------------------------------------------- static_table_search

def test_static_table_hit():
    table = {
        ("websearch_proxy", "y"): ParsedSearchResult(
            value=0.7, citation="PMID:1", raw_response="raw"
        ),
    }
    a = WebSearchProxyAdapter(static_table_search(table))
    r = a.query(_q("y"))
    assert r.success
    assert r.value == 0.7


def test_static_table_miss():
    table = {("websearch_proxy", "y"): ParsedSearchResult(
        value=0.7, citation="x", raw_response="r"
    )}
    a = WebSearchProxyAdapter(static_table_search(table))
    r = a.query(_q("z"))  # different predicate
    assert r.success is False


# ------------------------------------------------------- E2E with translator

def _gap() -> DataGap:
    return DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description="P(belly_fat_loss=true | running=true) is missing",
        blocks=GapBlocks.POINT_ESTIMATE,
        provenance=(GapProvenanceRef(GapRefKind.INVESTIGATION_REQUEST, "P(...)"),),
        signature="conditional",
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population="adult_us",
            variables=("running", "belly_fat_loss"),
        ),
    )


def test_e2e_loop_via_registry():
    """gap → kb query → adapter result → bundle skeleton.
    Mimics what an orchestrator does turn-by-turn."""
    target = {"predicate": "belly_fat_loss",
              "args": [{"type": "const", "name": "me"}],
              "value": True}
    given = ({"predicate": "running",
              "args": [{"type": "const", "name": "me"}],
              "value": True},)

    # Build the lookup query
    q = gap_to_kb_query(_gap(), target=target, given=given)
    assert q is not None
    assert q.kb_name == "websearch_proxy"
    assert q.query_kind == KBQueryKind.CONDITIONAL_DISTRIBUTION

    # Register the reference adapter with a static answer
    table = {
        ("websearch_proxy", "belly_fat_loss"): ParsedSearchResult(
            value=0.31,
            interval=(0.22, 0.40),
            sample_size=1500,
            population_in_source="rct_meta_2024_adult",
            citation="PMID:99999",
            raw_response="meta-analysis...",
            confidence_grade="rct_meta_analysis",
        ),
    }
    reg = KBRegistry()
    reg.register(WebSearchProxyAdapter(static_table_search(table)))

    # Route + run
    adapter = reg.find(q)
    assert adapter is not None
    result = adapter.query(q)
    assert result.success
    assert result.value == 0.31

    # Convert to bundle ready for apply_patch_and_run
    bundle = kb_results_to_bundle([result])
    assert bundle["kind"] == "parameter_fill_bundle"
    assert len(bundle["skeletons"]) == 1
    sk = bundle["skeletons"][0]
    assert sk["value"] == 0.31
    assert sk["annotations"]["source"] == "PMID:99999"
    assert sk["target"]["atom"]["predicate"] == "belly_fat_loss"
    assert sk["target"]["value"] is True
    assert len(sk["given"]) == 1
    assert sk["given"][0]["atom"]["predicate"] == "running"


def test_e2e_failure_yields_empty_bundle():
    """When KB has no answer, bundle is empty → orchestrator falls back
    to AskUser per gap_to_action.md."""
    target = {"predicate": "y", "value": True}
    q = gap_to_kb_query(_gap(), target=target)

    reg = KBRegistry()
    reg.register(WebSearchProxyAdapter(lambda q: None))  # always fails
    result = reg.find(q).query(q)
    bundle = kb_results_to_bundle([result])
    assert bundle["skeletons"] == []  # failure dropped silently
