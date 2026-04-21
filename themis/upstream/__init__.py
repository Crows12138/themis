"""Upstream layer — turn out-of-Themis inputs into a Program.

Slice W1: ``program_builder`` converts an **already-parsed** extraction
dict (produced by an agent such as Claude Code, an LLM, or any other
NL front-end) into a Themis ``Program``. This module does not call an
LLM itself; it is a pure data transformation so the parser stage and
the reasoning stage remain independently testable.
"""
from .program_builder import (
    ExtractionError,
    build_program_from_extraction,
)

__all__ = [
    "ExtractionError",
    "build_program_from_extraction",
]
