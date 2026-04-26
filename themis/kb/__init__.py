"""Phase 11.2 KB Adapter contract — schemas, adapter ABC, registry,
translator, cache.

Themis itself performs no IO. This package defines the contract that
client-side adapters (PrimeKG, SciGraph, SemMedDB, WebSearch wrappers)
implement, plus pure helpers for translating data_gap_report entries
into structured KBQuery and KBResult into apply_patch_and_run patches.
"""
from __future__ import annotations

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

__all__ = [
    "KBConfidenceGrade",
    "KBProvenance",
    "KBQuery",
    "KBQueryKind",
    "KBResult",
    "kb_provenance_from_dict",
    "kb_provenance_to_dict",
    "kb_query_from_dict",
    "kb_query_to_dict",
    "kb_result_from_dict",
    "kb_result_to_dict",
]
