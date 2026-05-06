"""Minimal local web UI for Themis.

Run with:

    python -m themis.web

Opens a FastAPI server on http://localhost:8000 with a single-page
form for pasting kernel_ast JSON and seeing the structured result
rendered with explanation / ⚠ caveats / data_gap_report / derivation.

This is a thin wrapper around ``themis.run`` / ``themis.verify`` —
no NL → JSON bridge yet (mode b: paste-JSON dev tool). Adding an
LLM bridge is a follow-up that doesn't break this surface.
"""
