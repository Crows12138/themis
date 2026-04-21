"""Kernel entry point: JSON in, JSON out.

``run`` is the single public entry that exercises the full pipeline:
parse → validate → instantiate → project → dispatch → serialize.
``apply_patch_and_run`` (slice A3) threads user-supplied fill-in
bundles through the same pipeline so multi-turn follow-up rounds
stay on the JSON boundary. ``verify`` closes the auditing loop:
given the input program JSON and any one result JSON, it
independently re-runs the verifier without the caller holding
any typed kernel objects.

The kernel does not call an LLM, does not touch disk, and does not
emit natural language. Any explanation or translation layer lives
above this boundary and consumes the structured dict these functions
return.

Contracts:

- Input conforms to ``kernel_ast.schema.json``.
- Output's ``results`` entries conform to ``query_result.schema.json``
  (which now $refs ``derivation.schema.json`` for the derivation field).
- Patch bundles (A3) conform to the shapes emitted by
  ``themis.workflow.parameter_fill.extract_skeleton_bundle`` and
  ``themis.workflow.variable_framing.extract_framing_skeleton``.
"""
from __future__ import annotations

import json

from .input.parser import parse_json
from .input.semantic_validator import validate_program
from .input.syntactic_validator import validate_ast, validate_result
from .output.result_orchestrator import to_dict
from .runtime.graph_projection import project
from .runtime.instantiation import instantiate
from .runtime.scheduler import dispatch_all
from .runtime.theta_builder import build_theta
from .types import (
    Annotation,
    AssocQuery,
    Atom,
    BidirectedStatement,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    NumericResult,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    QueryStatement,
    StructuralResult,
    Term,
    ValuedAtom,
    VarTerm,
    VariableDeclaration,
)
from .verifier import (
    VerificationContext,
    VerificationError,
    derivation_from_dict,
    verify_assoc,
    verify_cause,
    verify_identify,
    verify_numeric,
)


class AdmgVerificationPending(ValueError):
    """Phase 2.latent S3.a verifier compatibility patch.

    Raised by ``themis.verify`` when asked to audit a result whose
    source program contains ``BidirectedStatement`` edges. The runtime
    can already dispatch such programs (S3.a ADMG-aware front-door;
    S3.b Tian c-factor), but the independent verifier's ADMG rule
    family (`m_separation_witness` / `identify_via_c_factor` /
    `unidentifiable_via_c_forest`) lands in S4.

    This exception is deliberately a distinct class — callers must be
    able to tell "ADMG result cannot be verified yet" apart from both a
    silent accept (dangerous) and a generic VerificationError (wrong
    contract). Once S4 ships the verifier rules, this path is removed
    and bidirected programs flow through the standard verify_identify
    / verify_numeric entries.
    """

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


# ---------------------------------------------------------- Program -> AST

def _term_to_dict(t: Term) -> dict:
    if isinstance(t, ConstTerm):
        return {"type": "const", "name": t.name}
    if isinstance(t, VarTerm):
        return {"type": "var", "name": t.name}
    raise TypeError(f"unknown term: {type(t).__name__}")


def _atom_to_dict(a: Atom) -> dict:
    return {
        "predicate": a.predicate,
        "args": [_term_to_dict(t) for t in a.args],
    }


def _valued_atom_to_dict(va: ValuedAtom) -> dict:
    return {"atom": _atom_to_dict(va.atom), "value": va.value}


def _intervention_to_dict(iv: Intervention) -> dict:
    return {"atom": _atom_to_dict(iv.atom), "value": iv.value}


def _annotation_to_dict(ann: Annotation | None) -> dict | None:
    if ann is None:
        return None
    d: dict = {}
    if ann.confidence is not None:
        d["confidence"] = ann.confidence
    if ann.source is not None:
        d["source"] = ann.source
    return d


def _query_to_dict(q) -> dict:
    if isinstance(q, CauseQuery):
        return {
            "kind": "cause",
            "from": _atom_to_dict(q.from_atom),
            "to": _atom_to_dict(q.to_atom),
        }
    if isinstance(q, AssocQuery):
        return {
            "kind": "assoc",
            "left": _atom_to_dict(q.left),
            "right": _atom_to_dict(q.right),
            "given": [_atom_to_dict(a) for a in q.given],
        }
    if isinstance(q, EffectQuery):
        return {
            "kind": "effect",
            "target": _valued_atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_valued_atom_to_dict(va) for va in q.given],
        }
    if isinstance(q, IdentifyQuery):
        return {
            "kind": "identify",
            "target": _atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_atom_to_dict(a) for a in q.given],
        }
    if isinstance(q, ProbabilityQuery):
        return {
            "kind": "probability",
            "target": _valued_atom_to_dict(q.target),
            "given": [_valued_atom_to_dict(va) for va in q.given],
        }
    raise TypeError(f"unknown query: {type(q).__name__}")


def _statement_to_dict(s) -> dict:
    if isinstance(s, CauseStatement):
        d: dict = {
            "kind": "cause",
            "from": _atom_to_dict(s.from_atom),
            "to": _atom_to_dict(s.to_atom),
        }
        if s.forall:
            d["forall"] = list(s.forall)
        ann = _annotation_to_dict(s.annotations)
        if ann is not None:
            d["annotations"] = ann
        return d
    if isinstance(s, BidirectedStatement):
        d: dict = {
            "kind": "bidirected",
            "left": _atom_to_dict(s.left),
            "right": _atom_to_dict(s.right),
        }
        if s.forall:
            d["forall"] = list(s.forall)
        ann = _annotation_to_dict(s.annotations)
        if ann is not None:
            d["annotations"] = ann
        return d
    if isinstance(s, VariableDeclaration):
        d = {"kind": "variable", "predicate": s.predicate}
        if s.domain is not None:
            d["domain"] = list(s.domain)
        for field in ("time_window", "measurement", "threshold",
                      "observability", "unit",
                      "direction", "baseline", "state_vs_event"):
            v = getattr(s, field)
            if v is not None:
                d[field] = v
        return d
    if isinstance(s, ObservationStatement):
        d = {
            "kind": "observation",
            "atom": _atom_to_dict(s.atom),
            "value": s.value,
        }
        ann = _annotation_to_dict(s.annotations)
        if ann is not None:
            d["annotations"] = ann
        return d
    if isinstance(s, ProbabilityStatement):
        d = {
            "kind": "probability",
            "target": _valued_atom_to_dict(s.target),
            "given": [_valued_atom_to_dict(va) for va in s.given],
            "value": s.value,
        }
        if s.forall:
            d["forall"] = list(s.forall)
        ann = _annotation_to_dict(s.annotations)
        if ann is not None:
            d["annotations"] = ann
        return d
    if isinstance(s, QueryStatement):
        return {"kind": "query", "id": s.id, "query": _query_to_dict(s.query)}
    raise TypeError(f"unknown statement: {type(s).__name__}")


def _program_to_ast_dict(prog: Program) -> dict:
    """Serialize a typed Program back to the kernel_ast.schema.json
    JSON shape. Used by ``apply_patch_and_run`` so the caller can
    independently verify the result via ``themis.verify`` against the
    exact program the kernel computed on — not the pre-patch input."""
    ast: dict = {
        "version": prog.version,
        "domain": {
            "objects": [{"kind": "object", "name": o} for o in prog.objects]
        },
        "statements": [_statement_to_dict(s) for s in prog.statements],
    }
    if prog.extensions is not None:
        ast["extensions"] = prog.extensions
    if prog.options is not None:
        ast["options"] = prog.options
    return ast


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
    program and re-runs the full pipeline, returning an envelope with
    both the computed results and the **merged program** the kernel
    actually ran on — so an external auditor can call
    ``themis.verify(out["merged_program"], out["results"][i])``
    without having to re-apply the patches themselves.

    Return shape::

        {
            "results": [<query_result_dict>, ...],
            "merged_program": <kernel_ast.schema.json dict>
        }

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

    out = _run_typed(prog)
    out["merged_program"] = _program_to_ast_dict(prog)
    return out


# ============================================================ verify

def _decode_structural_result_json(d: dict) -> StructuralResult:
    """Decode the untagged structural_result shape emitted by
    result_orchestrator.to_dict into a StructuralResult dataclass."""
    return StructuralResult(
        value=d["value"],
        supporting_paths=tuple(
            tuple(p) for p in d.get("supporting_paths", ())
        ),
    )


def _decode_numeric_result_json(d: dict) -> NumericResult:
    """Decode the untagged numeric_result shape emitted by
    result_orchestrator.to_dict into a NumericResult dataclass."""
    from .types import NumericInterval
    interval = None
    if "interval" in d:
        interval = NumericInterval(
            low=d["interval"]["low"], high=d["interval"]["high"],
        )
    return NumericResult(
        value=d["value"], interval=interval, unit=d.get("unit"),
    )


def verify(program: dict | str | bytes, result: dict) -> None:
    """Independently re-verify one result against its source program.

    Takes the JSON contract at face value — no typed kernel objects
    leave this function's scope. The caller supplies:

    - ``program``: the original kernel_ast payload (same shape ``run``
      accepts), as a dict or JSON string / bytes.
    - ``result``: a single entry from ``run(...)["results"]``. Must
      carry a ``derivation`` field — this function rejects
      verification-by-omission.

    The query is located by matching ``result["query_id"]`` against a
    QueryStatement in the program. The verification context is
    reconstructed from the program's graph + theta + that query.
    The derivation is decoded through the verifier's canonical
    deserializer, and the appropriate ``verify_*`` function runs.

    Raises ``VerificationError`` on any mismatch (rule failure, step
    rejection, query-binding violation). Raises ``ValueError`` if the
    result references a missing or unsupported query, or lacks a
    derivation. Returns ``None`` on accept.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")

    # Shape-check the result payload so we fail early on malformed
    # derivations rather than deep inside the verifier.
    validate_result(result)

    derivation_json = result.get("derivation")
    if derivation_json is None:
        raise ValueError(
            "verify() requires a result with a derivation; this result "
            "has none (external agents cannot audit an answer without "
            "its reasoning chain)"
        )

    ast = _to_ast(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)

    # Phase 2.latent S3.a verifier compatibility patch: the verifier's
    # ADMG rule family lands in S4. Until then, refuse to audit results
    # whose source program contains bidirected edges — silent accept
    # would be worse than an explicit pending error.
    if any(isinstance(s, BidirectedStatement) for s in prog.statements):
        raise AdmgVerificationPending(
            "verify() does not yet support programs containing "
            "bidirected edges (ADMG). The runtime dispatches these via "
            "the Phase 2.latent S3.a front-door path, but the "
            "independent verifier's ADMG rule family lands in S4. See "
            "PHASE_2_LATENT_CHARTER.md §7."
        )

    graph = project(instantiate(prog))
    theta = build_theta(instantiate(prog))

    target_id = result.get("query_id")
    if target_id is None:
        raise ValueError(
            "verify() requires result.query_id to locate the matching "
            "query in the program"
        )
    query_stmt = None
    for s in prog.statements:
        if isinstance(s, QueryStatement) and s.id == target_id:
            query_stmt = s
            break
    if query_stmt is None:
        raise ValueError(
            f"verify(): no query with id={target_id!r} in the program"
        )

    derivation = derivation_from_dict(derivation_json)
    ctx = VerificationContext(graph=graph, query=query_stmt.query, theta=theta)

    kind = result.get("query_kind")
    if kind == "cause":
        claimed = _decode_structural_result_json(result["structural_result"])
        verify_cause(derivation, ctx, claimed)
    elif kind == "assoc":
        claimed = _decode_structural_result_json(result["structural_result"])
        verify_assoc(derivation, ctx, claimed)
    elif kind == "identify":
        claimed = _decode_structural_result_json(result["structural_result"])
        verify_identify(derivation, ctx, claimed)
    elif kind in ("effect", "probability"):
        if "numeric_result" not in result:
            raise ValueError(
                f"verify(): {kind} result must carry a numeric_result"
            )
        claimed = _decode_numeric_result_json(result["numeric_result"])
        verify_numeric(derivation, ctx, claimed)
    else:
        raise ValueError(
            f"verify(): unsupported query_kind {kind!r}"
        )
