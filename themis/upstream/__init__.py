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

Everything this package raises carries a SPECIES and this occasion's
facts rather than a finished sentence, because the reader is whoever
produced the extraction and a raise site does not know who that is.
``str(exc)`` is still what a traceback shows; ``.species``, ``.said`` and
``.words`` are what a surface assembles the sentence from once it knows
the language to say it in.

- ``extraction_words`` — ``ExtractionRefusal`` (the base every refusal
  here inherits, carrying species + facts), ``Refuses`` (which refusal it
  is) and ``Shape`` (what a field was supposed to be — a word that goes
  in a hole, not a sentence of its own)

Public surface (re-exports from sub-modules):

- ``program_builder`` — ``build_program_from_extraction``
  (extraction dict → ``Program``); raises ``ExtractionError`` when
  the input shape is rejected
- ``narrative_merge`` — variable / edge / ambiguity merge helpers:
  ``merge_into_program`` / ``merge_variable_extractions`` /
  ``merge_edges_into_program`` / ``merge_edge_extractions`` /
  ``merge_narrative_ambiguities_into_program`` / ``compose_program``
  (single-call entry); plus refusal pass-through
  (``apply_edge_refusals``) and the predicate-link drift detection
  + apply pair (``diagnose_predicate_links`` /
  ``diagnose_edge_predicate_links`` / ``apply_predicate_links`` /
  ``apply_predicate_links_to_edges``); raises
  ``ExtractionShapeError`` / ``MergeConflictError`` /
  ``PredicateLinkError`` for malformed input or conflicts
"""
from .extraction_words import ExtractionRefusal, Refuses, Shape
from .program_builder import (
    ExtractionError,
    build_program_from_extraction,
)
from .narrative_merge import (
    ExtractionShapeError,
    MergeConflictError,
    PredicateLinkError,
    apply_edge_refusals,
    apply_predicate_links,
    apply_predicate_links_to_edges,
    compose_program,
    diagnose_edge_predicate_links,
    diagnose_predicate_links,
    merge_edge_extractions,
    merge_edges_into_program,
    merge_into_program,
    merge_narrative_ambiguities_into_program,
    merge_variable_extractions,
)

__all__ = [
    "ExtractionError",
    "ExtractionRefusal",
    "ExtractionShapeError",
    "MergeConflictError",
    "PredicateLinkError",
    "Refuses",
    "Shape",
    "apply_edge_refusals",
    "apply_predicate_links",
    "apply_predicate_links_to_edges",
    "build_program_from_extraction",
    "compose_program",
    "diagnose_edge_predicate_links",
    "diagnose_predicate_links",
    "merge_edge_extractions",
    "merge_edges_into_program",
    "merge_into_program",
    "merge_narrative_ambiguities_into_program",
    "merge_variable_extractions",
]
