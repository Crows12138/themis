"""Causal reasoning kernel v0.1.

See ARCHITECTURE.md for layer definitions and dependency rules.

Public entry point::

    from themis import run
    out = run(program_json_or_dict)    # out["results"] is a list of
                                        # per-query result dicts

The kernel is JSON-in / JSON-out. Inputs conform to
``kernel_ast.schema.json``; outputs' ``results`` entries conform to
``query_result.schema.json``. No natural language passes through this
boundary.
"""

from .kernel import run

__version__ = "0.1.0"
__all__ = ["run"]
