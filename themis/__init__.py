"""Causal reasoning kernel v0.1.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry points::

    from themis import run, apply_patch_and_run

    # Turn 1:
    out = run(program_json_or_dict)

    # Turn 2 (multi-turn closed loop, slice A3):
    out2 = apply_patch_and_run(program_json, [filled_bundle, ...])

The kernel is JSON-in / JSON-out. Inputs conform to
``kernel_ast.schema.json``; outputs' ``results`` entries conform to
``query_result.schema.json``. No natural language passes through this
boundary.
"""

from .kernel import apply_patch_and_run, run

__version__ = "0.1.0"
__all__ = ["apply_patch_and_run", "run"]
