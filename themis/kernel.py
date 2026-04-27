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
    CounterfactualQuery,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    Monotonicity,
    NumericResult,
    ObservationStatement,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    QueryStatement,
    SelectionNode,
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
    verify_counterfactual,
    verify_effect_structural,
    verify_identify,
    verify_numeric,
    verify_numeric_estimate,
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

# Map: record `kind` → (target bundle kind, bundle list-field name).
# Used by ``apply_patch_and_run`` to forgivingly accept raw skeletons
# (the exact records emitted on ``investigation_requests[].items[].skeleton``)
# and auto-wrap them into the appropriate bundle envelope. The two list
# field names differ on purpose: ``skeletons`` for new probability
# statements, ``patches`` for diffs against existing variable
# declarations.
_RECORD_KIND_TO_BUNDLE = {
    "probability": (PARAMETER_BUNDLE_KIND, "skeletons"),
    "variable_patch": (FRAMING_BUNDLE_KIND, "patches"),
}


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
    d = {
        "predicate": a.predicate,
        "args": [_term_to_dict(t) for t in a.args],
    }
    if a.time_index is not None:
        d["time_index"] = {"kind": "relative", "value": a.time_index.value}
    return d


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
    if isinstance(q, CounterfactualQuery):
        d = {
            "kind": "counterfactual",
            "observed": _valued_atom_to_dict(q.observed),
            "counterfactual_intervention": _intervention_to_dict(
                q.counterfactual_intervention
            ),
            "counterfactual_target": _valued_atom_to_dict(
                q.counterfactual_target
            ),
        }
        if q.assumptions is not None and q.assumptions.monotonicity is not None:
            d["assumptions"] = {
                "monotonicity": q.assumptions.monotonicity.value,
            }
        if q.factual_target_known is not None:
            d["factual_target_known"] = q.factual_target_known
        return d
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
    if isinstance(s, SelectionNode):
        d = {
            "kind": "selection_node",
            "id": s.id,
            "affects": _atom_to_dict(s.affects),
            "source_population": s.source_population,
            "target_population": s.target_population,
        }
        ann = _annotation_to_dict(s.annotations)
        if ann is not None:
            d["annotations"] = ann
        return d
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


def estimate(program: dict | str | bytes, data, **options) -> dict:
    """Phase 7 M2 entry point — numerical estimation from data.

    ``program`` is a kernel_ast dict / JSON (same as ``run``).
    ``data`` is a pandas DataFrame whose columns match the predicates
    referenced by the program.

    Runs the identification pipeline exactly as ``run`` would, then
    — for effect queries with a resolved adjustment strategy — fits
    the relevant estimator on ``data`` and attaches a
    ``numeric_estimate`` block to the corresponding result.

    Supported in 7.1: backdoor-adjusted ATE (binary intervention +
    bool/continuous outcome). Front-door / IV / mediation estimators
    land in 7.2 / 7.3 / 7.4 and will route through this same entry.

    Options (kw-only):
        random_state (int, default 42) — deterministic seed
        ci_bootstrap (int, default 500) — bootstrap iterations; 0 skips
        model (str, default 'auto') — 'auto' | 'linear' | 'logistic'

    Returns a dict in the same shape as ``run`` with, where applicable,
    ``result['numeric_estimate']`` populated.
    """
    # Delayed import avoids pulling pandas / sklearn into ``themis.run``'s
    # import graph for callers that only need identification.
    from .estimation.dispatch import estimate_program
    return estimate_program(program, data, **options)


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

    bundles = _normalize_patches_to_bundles(patches)
    for patch in bundles:
        kind = patch["kind"]
        if kind == FRAMING_BUNDLE_KIND:
            prog = merge_variable_declaration(prog, patch)
        else:  # PARAMETER_BUNDLE_KIND — _normalize guarantees one of the two
            prog = merge_skeleton_bundle(prog, patch)

    out = _run_typed(prog)
    out["merged_program"] = _program_to_ast_dict(prog)
    return out


def _normalize_patches_to_bundles(patches) -> list[dict]:
    """Forgiving input handling for ``apply_patch_and_run.patches``.

    Accepts (and converts everything to a list of bundles ready to merge):

    1. ``dict`` with ``kind`` ∈ {parameter_fill_bundle, framing_skeleton_bundle}
       → one-element list (legacy path)
    2. ``dict`` with ``kind`` ∈ {probability, variable_patch}
       → wrap in a single-record bundle of the matching type
    3. ``list[dict]`` mixing bundles and raw records — bundles pass
       through; consecutive raw records of the same kind are auto-wrapped
       into one bundle each (preserving order)

    The whole point: an LLM that copies an
    ``investigation_requests[].items[].skeleton`` verbatim and calls
    ``apply_patch_and_run`` should just work — not get
    ``MalformedBundleError: bundle.version must be '0.1'``. Hand-built
    bundles still work; this only widens the input grammar.

    Mixed kinds in adjacent raw records are tolerated (they go into
    separate bundles). Unknown ``kind`` raises ``ValueError`` with the
    full set of accepted values so the LLM can correct.
    """
    if isinstance(patches, dict):
        patches = [patches]
    if not isinstance(patches, list):
        raise TypeError(
            "patches must be a dict or list of dicts; "
            f"got {type(patches).__name__}"
        )

    out: list[dict] = []
    pending: dict[str, list[dict]] = {k: [] for k in _RECORD_KIND_TO_BUNDLE}

    def _flush() -> None:
        for record_kind, recs in pending.items():
            if not recs:
                continue
            bundle_kind, list_field = _RECORD_KIND_TO_BUNDLE[record_kind]
            out.append({
                "version": "0.1",
                "kind": bundle_kind,
                list_field: list(recs),
            })
            pending[record_kind] = []

    for i, patch in enumerate(patches):
        if not isinstance(patch, dict):
            raise TypeError(f"patches[{i}] must be a dict")
        kind = patch.get("kind")
        if kind in (FRAMING_BUNDLE_KIND, PARAMETER_BUNDLE_KIND):
            _flush()
            out.append(patch)
        elif kind in _RECORD_KIND_TO_BUNDLE:
            pending[kind].append(patch)
        else:
            accepted = (
                [FRAMING_BUNDLE_KIND, PARAMETER_BUNDLE_KIND]
                + list(_RECORD_KIND_TO_BUNDLE)
            )
            raise ValueError(
                f"patches[{i}].kind={kind!r} is not a supported patch "
                f"shape; expected one of {accepted}"
            )
    _flush()
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

    ground = instantiate(prog)
    graph = project(ground)
    theta = build_theta(ground)
    # Phase 2.latent S4: thread bidirected edge set into verification
    # context so backdoor_criterion / front_door_criterion /
    # m_separation_witness rules can independently re-check ADMG
    # semantics. Empty frozenset on pure-DAG programs preserves all
    # pre-S4 verifier paths bit-identically.
    from .runtime.structural_solver import bidirected_from_ground
    bidirected = bidirected_from_ground(ground)

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

    # Phase 9 §T9.1.4: selection nodes for transport verifier.
    from .types import SelectionNode as _SN
    selection_nodes = tuple(s for s in prog.statements if isinstance(s, _SN))

    derivation = derivation_from_dict(derivation_json)
    ctx = VerificationContext(
        graph=graph,
        query=query_stmt.query,
        theta=theta,
        bidirected=bidirected,
        selection_nodes=selection_nodes,
    )

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
        status = result.get("status")
        if status == "structurally_solved" and kind == "effect":
            # Phase 6.mediation: effect queries with a mediator return
            # STRUCTURALLY_SOLVED without a numeric formula. Route to
            # the structural effect verifier.
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_effect_structural(derivation, ctx, claimed)
        elif (
            status == "numerically_solved"
            and kind == "effect"
            and "numeric_estimate" in result
        ):
            # Phase 7.1: data-based effect estimate. Final step is
            # numeric_backdoor_estimate (relaxed metadata audit).
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_numeric_estimate(derivation, ctx, claimed)
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    f"verify(): {kind} result must carry a numeric_result"
                )
            claimed = _decode_numeric_result_json(result["numeric_result"])
            verify_numeric(derivation, ctx, claimed)
    elif kind == "counterfactual":
        if "numeric_result" not in result:
            raise ValueError(
                "verify(): counterfactual result must carry a numeric_result"
            )
        claimed = _decode_numeric_result_json(result["numeric_result"])
        verify_counterfactual(derivation, ctx, claimed)
    else:
        raise ValueError(
            f"verify(): unsupported query_kind {kind!r}"
        )

    # Phase 10 §10.4: T10 audit of the data gap report (if attached).
    # Independent of the derivation walk above — re-implements failure /
    # coverage logic from scratch in themis.verifier.data_gap_rules.
    gap_report = result.get("data_gap_report")
    if gap_report is not None:
        from .verifier.data_gap_rules import verify_data_gap_report
        verify_data_gap_report(
            gap_report,
            derivation=derivation_json,
            investigation_requests=result.get("investigation_requests", []),
            framing_notes=result.get("framing_notes", []),
        )
