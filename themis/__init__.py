"""Causal reasoning kernel v0.1.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry points::

    from themis import run, apply_patch_and_run, verify

    # Turn 1:
    out = run(program_json_or_dict)

    # Turn 2 (multi-turn closed loop, slice A3):
    out2 = apply_patch_and_run(program_json, [filled_bundle, ...])

    # Independent re-check (pure JSON; no typed objects needed):
    verify(program_json, out["results"][0])

The kernel is JSON-in / JSON-out. Inputs conform to
``kernel_ast.schema.json``; outputs' ``results`` entries conform to
``query_result.schema.json`` (which $refs ``derivation.schema.json``
for the embedded reasoning chain). No natural language passes through
this boundary.
"""

from .kernel import AdmgVerificationPending, apply_patch_and_run, run, verify

__version__ = "0.1.0"
__all__ = [
    "AdmgVerificationPending",
    "apply_patch_and_run",
    "run",
    "verify",
]
