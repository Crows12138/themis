"""Themis-side adapter for the sibling CauseNet MCP server.

This adapter does **two things**:

1. ``lookup_edge(edge)`` — verify a single LLM-proposed edge against
   CauseNet. Returns structural signals (Wikipedia source title
   distribution, path-pattern distribution, source-type distribution)
   so the upstream LLM consumer can spot homonym / sense-mismatch
   issues by reading the structure. The adapter assigns a STRUCTURAL
   verdict (``kb_verified`` / ``kb_partial`` / ``kb_unverified``) but
   does NOT do semantic LLM judging — kernel-contract bound.

2. ``suggest_edges_among(atoms)`` — for a given atom set, ask CauseNet
   for all edges where BOTH endpoints are in the set. Used to surface
   "the LLM may have missed these KB-known edges" suggestions to the
   review surface. The LLM stays the DAG's final author.

Discipline: NO LLM call inside this adapter. Concept-string translation
goes through ``themis.kb.concept_translator`` (L1+L2+L3, deterministic).
Aggregate-distribution computation is delegated to the sibling MCP server.

Transport: the adapter consumes a ``ToolCallable`` that takes a tool
name and dict args and returns a parsed JSON dict. Inject:
- in-process FastMCP (testing, same-host trusted deployments) via
  ``make_inprocess_caller(app)``, OR
- stdio MCP client (cross-process / cross-host production) via your
  own wrapper. Adapter is transport-agnostic.

NOTE: this adapter is intentionally NOT a subclass of
``themis.kb.contract.KBAdapter``. That contract is for
probability-filling (KBQuery → KBResult.value: float) and has a
different shape entirely. Edge-verification is a parallel API surface;
forcing it into KBAdapter would distort both.
"""
from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field

from ..concept_translator import translate_concept


# A tool caller is name + args → parsed-JSON dict. Inject one to swap
# transports (in-process FastMCP vs stdio MCP client vs HTTP, etc.).
ToolCallable = Callable[[str, dict], dict]


# Cap variant cross-product attempts. Without a cap, full WordNet on
# both endpoints can explode to 100+ combinations. 16 is enough to
# cover L1×L1, L2×L1, L1×L2, L2×L2 for typical inputs.
_MAX_VARIANT_COMBINATIONS = 16


# Structural homonym threshold: if the most-common source_title accounts
# for less than this fraction of total sources, the title distribution
# is considered "split" and the verdict downgrades from kb_verified to
# kb_partial. 0.5 default — the dominant sense must own at least half.
# Tunable per adapter instance for stricter or looser semantics.
_DEFAULT_TITLE_HOMOGENEITY_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Data shapes (frozen dataclasses for hashability / structural equality)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EdgeClaim:
    """An LLM-proposed edge to verify. Direction is implicit (cause →
    effect). Concept strings are raw — the adapter normalizes them via
    ``concept_translator``."""

    cause: str
    effect: str


@dataclass(frozen=True)
class TitleDistEntry:
    title: str
    count: int


@dataclass(frozen=True)
class PatternDistEntry:
    pattern: str
    count: int


@dataclass(frozen=True)
class TypeDistEntry:
    source_type: str
    count: int


@dataclass(frozen=True)
class EdgeLookupResult:
    """Outcome of one ``lookup_edge`` call.

    ``verdict`` semantics (STRUCTURAL — no LLM):
        - ``kb_verified``   — edge in KB, top title's share >= threshold
        - ``kb_partial``    — edge in KB, but title distribution split
                              (homonym risk OR genuinely contested)
        - ``kb_unverified`` — edge not found in any variant combination

    Critical caveat: ``kb_verified`` does NOT mean "this edge is causally
    true". It means "CauseNet has this edge with a dominant title cluster
    suggesting consistent sense". The upstream consumer (LLM or user)
    must read the evidence and decide what to trust.
    """

    edge: EdgeClaim
    verdict: str
    confidence_tier: str = "not_found"
    num_sources: int = 0
    unique_source_count: int = 0
    source_title_distribution: tuple[TitleDistEntry, ...] = ()
    path_pattern_distribution: tuple[PatternDistEntry, ...] = ()
    source_type_distribution: tuple[TypeDistEntry, ...] = ()
    matched_variants: dict | None = None
    queried_variants: tuple[dict, ...] = ()
    kb_provenance: dict | None = None


@dataclass(frozen=True)
class SuggestedEdge:
    """A KB edge whose BOTH endpoints are in the LLM-proposed atom set
    but which the LLM did not itself propose. The adapter surfaces these
    as "did you miss these?" — the LLM/user decides whether to add."""

    cause: str
    effect: str
    num_sources: int
    confidence_tier: str
    kb_provenance: dict | None = None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class CausenetMCPAdapter:
    """Themis-side adapter — see module docstring."""

    def __init__(
        self,
        tool_caller: ToolCallable,
        *,
        use_wordnet: bool = True,
        title_homogeneity_threshold: float = _DEFAULT_TITLE_HOMOGENEITY_THRESHOLD,
    ) -> None:
        if not callable(tool_caller):
            raise TypeError("tool_caller must be callable(name, args) -> dict")
        if not 0.0 <= title_homogeneity_threshold <= 1.0:
            raise ValueError(
                f"title_homogeneity_threshold must be in [0, 1], "
                f"got {title_homogeneity_threshold}"
            )
        self._call = tool_caller
        self._use_wordnet = use_wordnet
        self._title_threshold = title_homogeneity_threshold

    def lookup_edge(self, edge: EdgeClaim) -> EdgeLookupResult:
        """Verify a single edge against CauseNet using variant cascade.

        Tries (cause_variant, effect_variant) combinations in confidence
        order — L1 normalized forms first, then L2 morphological, then
        L3 WordNet (if enabled). Stops at the first KB hit and returns
        a structurally-derived verdict.
        """
        cause_vars = translate_concept(
            edge.cause, use_wordnet=self._use_wordnet
        ).variants
        effect_vars = translate_concept(
            edge.effect, use_wordnet=self._use_wordnet
        ).variants

        tried: list[dict] = []
        for cv in cause_vars:
            if len(tried) >= _MAX_VARIANT_COMBINATIONS:
                break
            for ev in effect_vars:
                if len(tried) >= _MAX_VARIANT_COMBINATIONS:
                    break
                tried.append({"cause": cv, "effect": ev})
                raw = self._call(
                    "causenet_query_edge_aggregated",
                    {"cause": cv, "effect": ev},
                )
                if raw.get("verdict") == "supported":
                    return self._build_supported_result(
                        edge=edge,
                        raw=raw,
                        matched={"cause": cv, "effect": ev},
                        tried=tried,
                    )

        # No KB hit across all attempted variants
        return EdgeLookupResult(
            edge=edge,
            verdict="kb_unverified",
            confidence_tier="not_found",
            queried_variants=tuple(tried),
        )

    def suggest_edges_among(self, atoms: list[str]) -> tuple[SuggestedEdge, ...]:
        """For a set of LLM-proposed atoms, return all KB-known edges
        between any pair of them.

        Caller is responsible for filtering out edges the LLM already
        proposed (this adapter doesn't see the LLM's edge list — only
        the atom set). Returned tuple preserves KB tier ordering
        (high_confidence first, then extracted).
        """
        if not atoms:
            return ()
        raw = self._call("causenet_neighbors_among", {"atoms": list(atoms)})
        prov = raw.get("kb_provenance")
        return tuple(
            SuggestedEdge(
                cause=e["cause"],
                effect=e["effect"],
                num_sources=e["num_sources"],
                confidence_tier=e["confidence_tier"],
                kb_provenance=prov,
            )
            for e in raw.get("edges", [])
        )

    # ---- internal helpers ----

    def _build_supported_result(
        self,
        edge: EdgeClaim,
        raw: dict,
        matched: dict,
        tried: list[dict],
    ) -> EdgeLookupResult:
        title_dist = tuple(
            TitleDistEntry(title=e["title"], count=e["count"])
            for e in raw.get("source_title_distribution", [])
        )
        pattern_dist = tuple(
            PatternDistEntry(pattern=e["pattern"], count=e["count"])
            for e in raw.get("path_pattern_distribution", [])
        )
        type_dist = tuple(
            TypeDistEntry(source_type=e["source_type"], count=e["count"])
            for e in raw.get("source_type_distribution", [])
        )
        verdict = self._structural_verdict(title_dist)
        # Only surface matched_variants when it differs from the original
        # (saves noise in the common case where input matched directly).
        matched_field: dict | None = None
        if matched["cause"] != edge.cause or matched["effect"] != edge.effect:
            matched_field = matched
        return EdgeLookupResult(
            edge=edge,
            verdict=verdict,
            confidence_tier=raw.get("confidence_tier", "not_found"),
            num_sources=raw.get("num_sources", 0),
            unique_source_count=raw.get("unique_source_count", 0),
            source_title_distribution=title_dist,
            path_pattern_distribution=pattern_dist,
            source_type_distribution=type_dist,
            matched_variants=matched_field,
            queried_variants=tuple(tried),
            kb_provenance=raw.get("kb_provenance"),
        )

    def _structural_verdict(
        self, title_dist: tuple[TitleDistEntry, ...]
    ) -> str:
        """Decide verdict from title distribution alone — no LLM.

        Rule: top title's share of total sources >= threshold →
        ``kb_verified`` (dominant sense is clear).
        Otherwise → ``kb_partial`` (distribution split; caller should
        read the distribution to disambiguate).
        """
        if not title_dist:
            # No distribution but KB said supported — defensive default:
            # mark partial so caller knows the structural signal is missing.
            return "kb_partial"
        total = sum(e.count for e in title_dist)
        if total == 0:
            return "kb_partial"
        top_share = title_dist[0].count / total
        if top_share >= self._title_threshold:
            return "kb_verified"
        return "kb_partial"


# ---------------------------------------------------------------------------
# Helpers for wiring transports
# ---------------------------------------------------------------------------


def make_inprocess_caller(app) -> ToolCallable:
    """Build a ToolCallable that invokes the FastMCP app in-process.

    Useful for unit tests and trusted same-host deployments where the
    extra subprocess of stdio MCP is unwanted. ``app`` is whatever
    ``causenet_mcp.build_server()`` returned.
    """

    def _call(name: str, args: dict) -> dict:
        blocks = asyncio.run(app.call_tool(name, args))
        for block in blocks:
            text = getattr(block, "text", None)
            if text:
                return json.loads(text)
        raise AssertionError(
            f"no text content in MCP tool result for {name!r}: {blocks!r}"
        )

    return _call
