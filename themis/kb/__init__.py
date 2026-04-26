"""Phase 11.2 KB Adapter contract — schemas, adapter ABC, registry,
translator, cache.

Themis itself performs no IO. This package defines the contract that
client-side adapters (PrimeKG, SciGraph, SemMedDB, WebSearch wrappers)
implement, plus pure helpers for translating data_gap_report entries
into structured KBQuery and KBResult into apply_patch_and_run patches.
"""
from __future__ import annotations

from .cache import KBCache, cache_key
from .contract import KBAdapter, KBRegistry
from .schemas import (
    KBConfidenceGrade,
    KBProvenance,
    KBQuery,
    KBQueryKind,
    KBResult,
    kb_provenance_from_dict,
    kb_provenance_to_dict,
    kb_query_from_dict,
    kb_query_to_dict,
    kb_result_from_dict,
    kb_result_to_dict,
)
from .translator import (
    DEFAULT_KB_NAME,
    gap_to_kb_query,
    kb_result_to_skeleton,
    kb_results_to_bundle,
)

__all__ = [
    "DEFAULT_KB_NAME",
    "KBAdapter",
    "KBCache",
    "KBConfidenceGrade",
    "KBProvenance",
    "KBQuery",
    "KBQueryKind",
    "KBRegistry",
    "KBResult",
    "cache_key",
    "gap_to_kb_query",
    "kb_provenance_from_dict",
    "kb_provenance_to_dict",
    "kb_query_from_dict",
    "kb_query_to_dict",
    "kb_result_from_dict",
    "kb_result_to_dict",
    "kb_result_to_skeleton",
    "kb_results_to_bundle",
]
