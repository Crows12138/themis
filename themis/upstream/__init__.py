"""LLM-side convenience layer — **not** part of the kernel contract.

The kernel's authoritative JSON input is ``kernel_ast.schema.json``,
consumed through ``themis.run``. Agents that can produce that canonical
shape directly do not need anything from this module.

This package exists to give NL / LLM front-ends a simpler,
higher-level dict shape (an "extraction dict") that is easier to emit
reliably from a structured LLM call, and then mechanically translate
it into a canonical ``Program``. It does not call any LLM itself and
has no runtime dependency beyond ``themis.types``.

If future consumers converge on emitting canonical kernel_ast JSON
directly, this layer can be deleted without affecting the kernel.
"""
from .program_builder import (
    ExtractionError,
    build_program_from_extraction,
)
from .narrative_merge import (
    ExtractionShapeError,
    MergeConflictError,
    compose_program,
    diagnose_predicate_links,
    merge_edge_extractions,
    merge_edges_into_program,
    merge_into_program,
    merge_variable_extractions,
)

__all__ = [
    "ExtractionError",
    "ExtractionShapeError",
    "MergeConflictError",
    "build_program_from_extraction",
    "compose_program",
    "diagnose_predicate_links",
    "merge_edge_extractions",
    "merge_edges_into_program",
    "merge_into_program",
    "merge_variable_extractions",
]
