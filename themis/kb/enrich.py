"""KB edge verification enrichment pass.

Sits between ``kernel._run_typed`` and the result dict serialization.
Walks the typed program, sends every LLM-proposed edge through a KB
adapter for verification, and surfaces both per-edge verification
and missing-edge suggestions as ``extensions.kb_verification_report``.

Discipline (kernel-contract bound): NO LLM call here. The adapter is
responsible for being LLM-free; this module is a pure orchestrator
over the adapter's structural output.

The adapter is duck-typed — anything with ``lookup_edge(EdgeClaim)``
and ``suggest_edges_among(list[str])`` matching the Causenet adapter's
shape works. The kernel itself does not import the concrete adapter
class, so users can plug any edge-verification KB (Wikidata, custom
RAG, ...) by implementing the same two methods.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from ..types import CauseStatement, Program
from .adapters.causenet_mcp_adapter import EdgeClaim


def build_kb_verification_report(
    program: Program,
    adapter: Any,
) -> dict:
    """Walk program statements, verify LLM-proposed edges, find missing.

    Returns a dict ready to drop into
    ``query_result.extensions.kb_verification_report``::

        {
          "per_edge_verification": [
            { "edge": {"cause": "...", "effect": "..."},
              "verdict": "kb_verified|kb_partial|kb_unverified",
              ... structural signals ... },
            ...
          ],
          "suggested_missing_edges": [
            { "cause": "...", "effect": "...", "num_sources": N,
              "confidence_tier": "..." },
            ...
          ],
          "atoms_searched": ["...", ...]
        }

    Filtering: edges the LLM already proposed are stripped from
    ``suggested_missing_edges`` so the surface only shows genuinely
    new suggestions.

    Quiet on no-op: when the program has zero LLM-proposed edges AND
    the suggestion query returns nothing, returns an empty-but-shaped
    dict rather than None. Caller (kernel) decides whether to attach
    based on whether either list is non-empty.
    """
    proposed_pairs: set[tuple[str, str]] = set()
    atoms: set[str] = set()
    per_edge: list[dict] = []

    for stmt in program.statements:
        if not isinstance(stmt, CauseStatement):
            continue
        atoms.add(stmt.from_atom.predicate)
        atoms.add(stmt.to_atom.predicate)
        if stmt.annotations is None:
            continue
        source = (stmt.annotations.source or "").lower()
        if "llm" not in source:
            continue
        claim = EdgeClaim(
            cause=stmt.from_atom.predicate,
            effect=stmt.to_atom.predicate,
        )
        proposed_pairs.add((claim.cause, claim.effect))
        result = adapter.lookup_edge(claim)
        per_edge.append(_edge_lookup_to_dict(result))

    suggestions = adapter.suggest_edges_among(sorted(atoms)) if atoms else ()
    suggested: list[dict] = []
    for s in suggestions:
        # Filter out edges the LLM already proposed — the surface only
        # shows what's genuinely missing from the DAG.
        if (s.cause, s.effect) in proposed_pairs:
            continue
        suggested.append({
            "cause": s.cause,
            "effect": s.effect,
            "num_sources": s.num_sources,
            "confidence_tier": s.confidence_tier,
        })

    return {
        "per_edge_verification": per_edge,
        "suggested_missing_edges": suggested,
        "atoms_searched": sorted(atoms),
    }


def _edge_lookup_to_dict(result: Any) -> dict:
    """Convert an EdgeLookupResult dataclass to a JSON-shaped dict.

    Loose typing (Any) keeps the kernel free of a concrete adapter
    import — anything dataclass-shaped with the right fields works.
    """
    if is_dataclass(result):
        raw = asdict(result)
    else:
        # Best-effort: assume it's already dict-like
        raw = dict(result)
    # Flatten EdgeClaim into top-level cause/effect for readability
    edge = raw.pop("edge", None)
    if edge:
        raw["edge"] = {"cause": edge.get("cause"), "effect": edge.get("effect")}
    return raw
