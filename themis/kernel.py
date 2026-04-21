"""Kernel entry point: JSON in, JSON out.

``run`` is the single public entry that exercises the full pipeline:
parse → validate → instantiate → project → dispatch → serialize.
``apply_patch_and_run`` (slice A3) threads user-supplied fill-in
bundles through the same pipeline so multi-turn follow-up rounds
stay on the JSON boundary.

The kernel does not call an LLM, does not touch disk, and does not
emit natural language. Any explanation or translation layer lives
above this boundary and consumes the structured dict these functions
return.

Contracts:

- Input conforms to ``kernel_ast.schema.json``.
- Output's ``results`` entries conform to ``query_result.schema.json``.
- Patch bundles (A3) conform to the shapes emitted by
  ``themis.workflow.parameter_fill.extract_skeleton_bundle`` and
  ``themis.workflow.variable_framing.extract_framing_skeleton``.
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
from .workflow.parameter_fill import (
    BUNDLE_KIND as PARAMETER_BUNDLE_KIND,
    merge_skeleton_bundle,
)
from .workflow.variable_framing import (
    BUNDLE_KIND as FRAMING_BUNDLE_KIND,
    merge_variable_declaration,
)


def _to_ast(program: dict | str | bytes) -> dict:
    if isinstance(program, (str, bytes)):
        return parse_json(program)
    if isinstance(program, dict):
        # json.loads + json.dumps round-trip keeps the caller's dict
        # untouched and catches non-JSON-serializable values early.
        return json.loads(json.dumps(program))
    raise TypeError(
        "program must be dict / str / bytes; "
        f"got {type(program).__name__}"
    )


def _run_typed(prog) -> dict:
    graph = project(instantiate(prog))
    results = dispatch_all(prog, graph)
    return {"results": [to_dict(r) for r in results]}


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
    ast = _to_ast(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    return _run_typed(prog)


def apply_patch_and_run(
    program: dict | str | bytes,
    patches: list[dict] | dict,
) -> dict:
    """Apply fill-in patch bundles to a program and re-run the kernel.

    Turn 1 produces ``investigation_requests`` carrying per-item
    skeletons. The agent / user assembles those into one or more
    filled patch bundles; this function merges them into the original
    program and re-runs the full pipeline, returning the same
    ``{"results": [...]}`` envelope as ``run``.

    Supported bundle kinds (dispatched by ``bundle["kind"]``):

    - ``framing_skeleton_bundle`` — fills ``VariableDeclaration``
      framing fields (``time_window``, ``measurement``, ``threshold``,
      ``observability``); handled by
      ``workflow.variable_framing.merge_variable_declaration``.
    - ``parameter_fill_bundle`` — appends filled
      ``probabilityStatement`` records; handled by
      ``workflow.parameter_fill.merge_skeleton_bundle``.

    ``patches`` may be a single bundle dict or a list of bundles; both
    bundle kinds can be mixed in the same call. Patches are applied in
    order.

    Raises ``ValueError`` for an unknown ``kind`` and propagates the
    underlying merge errors (``VariablePatchConflictError``,
    ``UnfilledSkeletonError``, ``MalformedBundleError``,
    ``UnknownPredicateError``) when a bundle is malformed or
    inconsistent with the program.
    """
    ast = _to_ast(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)

    if isinstance(patches, dict):
        patches = [patches]
    if not isinstance(patches, list):
        raise TypeError(
            "patches must be a dict or list of dicts; "
            f"got {type(patches).__name__}"
        )

    for i, patch in enumerate(patches):
        if not isinstance(patch, dict):
            raise TypeError(f"patches[{i}] must be a dict")
        kind = patch.get("kind")
        if kind == FRAMING_BUNDLE_KIND:
            prog = merge_variable_declaration(prog, patch)
        elif kind == PARAMETER_BUNDLE_KIND:
            prog = merge_skeleton_bundle(prog, patch)
        else:
            raise ValueError(
                f"patches[{i}].kind={kind!r} is not a supported patch "
                f"bundle; expected one of "
                f"{[FRAMING_BUNDLE_KIND, PARAMETER_BUNDLE_KIND]}"
            )

    return _run_typed(prog)
