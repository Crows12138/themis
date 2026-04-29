"""Auditable causal reasoning and estimation system.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry points::

    from themis import run, apply_patch_and_run, estimate, verify

    # Pure symbolic kernel:
    out = run(program_json_or_dict)

    # Multi-turn closed loop:
    out2 = apply_patch_and_run(program_json, [filled_bundle, ...])

    # DataFrame-backed estimation path:
    estimated = estimate(program_json_or_dict, dataframe)

    # Independent re-check (pure JSON; no typed objects needed):
    verify(program_json, out["results"][0])

The kernel is JSON-in / JSON-out. Inputs conform to
``kernel_ast.schema.json``; outputs' ``results`` entries conform to
``query_result.schema.json`` (which $refs ``derivation.schema.json``
for the embedded reasoning chain). No natural language passes through
this boundary. The estimation entry point accepts DataFrame data as an
explicit side channel and does not change the kernel AST contract.
"""

from .kernel import (
    AdmgVerificationPending,
    apply_patch_and_run,
    estimate,
    run,
    verify,
)

__version__ = "0.14.0-dev"
__all__ = [
    "AdmgVerificationPending",
    "apply_patch_and_run",
    "estimate",
    "run",
    "verify",
]
