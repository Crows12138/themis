"""Kernel entry point: JSON in, JSON out.

``run`` is the single public entry that exercises the full pipeline:
parse → validate → instantiate → project → dispatch → serialize.
It does not call an LLM, does not touch disk, and does not emit
natural language. Any explanation or translation layer lives above
this boundary and consumes the structured dict this function
returns.

The input must conform to ``kernel_ast.schema.json``. The output's
``results`` entries conform to ``query_result.schema.json``. Both
schemas are the authoritative JSON contract for the kernel.
"""
from __future__ import annotations

import json

from .input.parser import parse_json
from .input.semantic_validator import validate_program
from .input.syntactic_validator import validate_ast
from .output.result_orchestrator import to_dict
from .runtime.graph_projection import project
from .runtime.instantiation import instantiate
from .runtime.scheduler import dispatch_all


def run(program: dict | str | bytes) -> dict:
    """Run the kernel end to end.

    ``program`` is either a parsed AST dict (e.g. from ``json.loads``
    or constructed programmatically) or a JSON string / bytes payload
    conforming to ``kernel_ast.schema.json``.

    Returns ``{"results": [<query_result_dict>, ...]}``. Each entry
    conforms to ``query_result.schema.json``.

    Raises ``SyntacticError`` / ``SemanticError`` if the input is
    malformed. No natural-language fallbacks — the caller is expected
    to surface the error as structured data too.
    """
    if isinstance(program, (str, bytes)):
        ast = parse_json(program)
    elif isinstance(program, dict):
        # json.loads + json.dumps round-trip keeps the caller's dict
        # untouched and catches non-JSON-serializable values early.
        ast = json.loads(json.dumps(program))
    else:
        raise TypeError(
            "run() accepts dict / str / bytes; "
            f"got {type(program).__name__}"
        )

    ast = validate_ast(ast)
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    results = dispatch_all(prog, graph)
    return {"results": [to_dict(r) for r in results]}
