"""Phase 11.2.5 — reference KB adapter wrapping a client-supplied
search function.

This is the *minimum* viable adapter — it exists to validate that the
contract (schemas + ABC) actually composes end-to-end, not to be a
production lookup. Real adapters (PrimeKG, SemMedDB, ...) plug the
same interface but speak structured KG queries instead of free text.

Design choice: the adapter does **no parsing**. The client supplies a
``search_fn`` whose return value is already structured as a
``ParsedSearchResult`` TypedDict — failed extraction is the client's
problem. This keeps the adapter ~50 lines and the parsing logic in
client code where the LLM and prompt context can adapt.

For the reference adapter to be usable from tests / docs without a
real network, we ship a ``static_table_search`` factory that builds a
search function from a dict of canned answers.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
from collections.abc import Callable, Mapping
from typing import TypedDict

from ..contract import KBAdapter
from ..schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBResult,
    kb_query_to_dict,
)


class ParsedSearchResult(TypedDict, total=False):
    """Shape the search_fn returns when extraction succeeded.

    Required: ``value``, ``citation``, ``raw_response``.
    Optional: ``interval``, ``sample_size``, ``population_in_source``,
    ``confidence_grade``, ``notes``.
    """

    value: float
    interval: tuple[float, float]
    sample_size: int
    population_in_source: str
    citation: str
    raw_response: str
    confidence_grade: str
    notes: str


SearchFn = Callable[[KBQuery], "ParsedSearchResult | None"]


class WebSearchProxyAdapter(KBAdapter):
    """Wraps a client-supplied ``search_fn`` into the KBAdapter contract.

    Usage::

        def my_search(q: KBQuery) -> ParsedSearchResult | None:
            ...  # call WebSearch / parse / return dict (or None on failure)

        adapter = WebSearchProxyAdapter(my_search)
        registry.register(adapter)
    """

    name = "websearch_proxy"

    def __init__(self, search_fn: SearchFn) -> None:
        self._search = search_fn

    def query(self, q: KBQuery) -> KBResult:
        retrieved_at = _now_iso()
        try:
            parsed = self._search(q)
        except Exception as exc:  # adapter exceptions degrade to failure
            return _failure_result(
                q, retrieved_at, f"search_fn_raised: {exc.__class__.__name__}"
            )

        if parsed is None or "value" not in parsed:
            return _failure_result(q, retrieved_at, "no_match_or_unparseable")

        raw = str(parsed.get("raw_response", ""))
        prov = KBProvenance(
            source_kb=self.name,
            query_used=q,
            retrieved_at=retrieved_at,
            raw_response_hash=_sha256_text(raw) if raw else _sha256_query(q),
            citation=str(parsed["citation"]),
            confidence_grade=_coerce_grade(parsed.get("confidence_grade")),
            notes=parsed.get("notes"),
        )
        # Every other field off an external response is coerced before it
        # reaches the contract; the interval was only re-containered, so a
        # three-ended or non-numeric one entered a field declared as a pair.
        raw_interval = parsed.get("interval")
        interval: tuple[float, float] | None = None
        if raw_interval:
            try:
                low, high = (float(v) for v in raw_interval)
            except (TypeError, ValueError):
                return _failure_result(
                    q, retrieved_at, "interval_not_a_float_pair"
                )
            interval = (low, high)
        return KBResult(
            query=q,
            success=True,
            provenance=prov,
            value=float(parsed["value"]),
            interval=interval,
            sample_size=int(parsed["sample_size"])
            if parsed.get("sample_size") is not None
            else None,
            population_in_source=parsed.get("population_in_source"),
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256_text(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_query(q: KBQuery) -> str:
    """Fallback hash when search_fn doesn't return raw_response."""
    import json
    return _sha256_text(
        json.dumps(kb_query_to_dict(q), sort_keys=True, ensure_ascii=False)
    )


def _coerce_grade(raw: str | None) -> KBConfidenceGrade:
    if raw is None:
        return KBConfidenceGrade.UNKNOWN
    try:
        return KBConfidenceGrade(raw)
    except ValueError:
        return KBConfidenceGrade.UNKNOWN


def _failure_result(q: KBQuery, retrieved_at: str, reason: str) -> KBResult:
    """Build a failure KBResult — provenance still carries what was tried."""
    prov = KBProvenance(
        source_kb=WebSearchProxyAdapter.name,
        query_used=q,
        retrieved_at=retrieved_at,
        raw_response_hash=_sha256_query(q),
        citation="(no result)",
    )
    return KBResult(query=q, success=False, provenance=prov, failure_reason=reason)


# ---------------------------------------------------------------------------
# Static-table factory: build a search_fn from a {(kb_name, target_predicate)
# → ParsedSearchResult} dict. Convenient for tests and docs without network.
# ---------------------------------------------------------------------------


def static_table_search(
    table: Mapping[tuple[str, str], ParsedSearchResult],
) -> SearchFn:
    """Build a search_fn from a static lookup table.

    Key shape: ``(kb_name, target_predicate)`` — minimal disambiguator.
    For richer routing build your own search_fn.
    """

    def _search(q: KBQuery) -> ParsedSearchResult | None:
        target_pred = str(q.target.get("predicate", ""))
        return table.get((q.kb_name, target_pred))

    return _search
