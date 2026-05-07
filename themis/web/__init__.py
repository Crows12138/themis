"""Minimal local web UI for Themis.

Run with:

    python -m themis.web

Opens a FastAPI server on http://localhost:8000 with a single-page
form supporting two modes:

- **Mode (b) — paste-JSON**: paste a kernel_ast → ``themis.run`` →
  see the structured result rendered with explanation / ⚠ caveats /
  data_gap_report / derivation. No LLM, no key required.
- **Mode (a) — Ask**: type a Chinese NL question → the LLM bridge
  (``llm_bridge.py``) calls Anthropic with the canonical
  ``nl_to_kernel_ast.md`` prompt, runs the emitted AST, then calls
  Anthropic again with ``response_rendering.md`` to produce a Chinese
  reply. Two LLM calls per question; requires ``ANTHROPIC_API_KEY``
  or a per-request key passed via the UI.

Endpoints (defined in ``app.py``): ``/api/run`` / ``/api/verify`` /
``/api/verify_bounds_result`` (iter 137) / ``/api/examples`` /
``/api/ask``.
"""
