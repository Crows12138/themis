"""Kernel entry point: JSON in, JSON out.

Public entries (all JSON-in / JSON-out, no typed objects required):

- ``run`` — single-turn full pipeline: parse → validate → instantiate
  → project → dispatch → serialize.
- ``apply_patch_and_run`` (slice A3) — threads user-supplied fill-in
  bundles through the same pipeline so multi-turn follow-up rounds
  stay on the JSON boundary.
- ``estimate`` — DataFrame side channel (Phase 7+): pandas DataFrame
  in, point estimate / CI / sensitivity out. Reuses the kernel's
  identification result without disturbing the JSON contract.
- ``verify`` — independent re-run of the V0–V5 verifier on a
  ``(program, result)`` pair, without the caller holding any typed
  kernel objects.
- ``verify_data_gap_report`` — T10-only audit (Phase 10), valid even
  for diagnostic results that carry no derivation.
- ``verify_bounds_result`` (iter 133) — independent audit of
  bounds_result via the iter 126/127/130 verifier trilogy
  (manski_natural / manski_tamer_monotonicity / balke_pearl_iv).
  Accepts derivation-less results — bounds typically attach when
  point identification fails (status=needs_investigation) and no
  derivation chain exists, so this is the bounds analog of the
  derivation-less verify_data_gap_report path.

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
from .output.result_orchestrator import (
    build_assumption_ledger,
    build_llm_proposed_review,
    to_dict,
)
from .runtime.graph_projection import project
from .runtime.instantiation import instantiate
from .runtime.scheduler import dispatch_all
from .runtime.theta_builder import build_theta
from .types import (
    Annotation,
    AssocQuery,
    Atom,
    BidirectedStatement,
    CausationQuery,
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
    SCMCounterfactualQuery,
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
    verify_causation,
    verify_cause,
    verify_counterfactual,
    verify_scm_counterfactual,
    verify_effect_structural,
    verify_identify,
    verify_numeric,
    verify_numeric_estimate,
    verify_ovb_sensitivity,
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
    result_dicts = [to_dict(r) for r in results]
    # Fix 3+4 §3.2 (v0.1.5): aggregate LLM-proposed elements (edges +
    # probability priors) into a single review surface per result, so
    # the agent's reply is forced to lead with audit disclosure. Only
    # attaches when at least one llm-tagged element exists — keeps
    # single-population non-LLM-prior fixtures byte-identical.
    review = build_llm_proposed_review(prog)
    if review is not None:
        for rd in result_dicts:
            ext = rd.setdefault("extensions", {})
            ext["llm_proposed_review"] = review
    # Assumption ledger — unified, severity-ranked view over the
    # per-result assumption channels (load-bearing proposal edges from
    # ``data_gap_report`` + LLM theta priors on the structural-query
    # path). The estimate path re-builds a fuller ledger downstream (it
    # adds functional-form + identification entries) and overwrites this
    # one; here the pure-run path gets the same unified surface instead
    # of having its assumptions scattered. Per-result: each carries its
    # own ``data_gap_report``.
    for rd in result_dicts:
        ledger = build_assumption_ledger(rd)
        if ledger is not None:
            rd.setdefault("extensions", {})["assumption_ledger"] = ledger
    return {"results": result_dicts}


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
        d: dict = {
            "kind": "effect",
            "target": _valued_atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_valued_atom_to_dict(va) for va in q.given],
        }
        # Joint interventions: emit only when present so single-treatment
        # programs round-trip byte-identically.
        if q.extra_interventions:
            d["extra_interventions"] = [
                _intervention_to_dict(iv) for iv in q.extra_interventions
            ]
        # Iter 131: serialize first-class assumptions field if set.
        # Backwards-compat: omit when None so old fixtures stay
        # bit-identical.
        if (
            q.assumptions is not None
            and q.assumptions.monotonicity is not None
        ):
            d["assumptions"] = {
                "monotonicity": q.assumptions.monotonicity.value,
            }
        return d
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
    if isinstance(q, CausationQuery):
        d = {
            "kind": "causation",
            "cause": _atom_to_dict(q.cause),
            "effect": _atom_to_dict(q.effect),
        }
        if q.monotonic:
            d["monotonic"] = q.monotonic
        if q.experimental_risk_treated is not None:
            d["experimental_risk_treated"] = q.experimental_risk_treated
        if q.experimental_risk_control is not None:
            d["experimental_risk_control"] = q.experimental_risk_control
        return d
    if isinstance(q, SCMCounterfactualQuery):
        return {
            "kind": "scm_counterfactual",
            "intervention": _intervention_to_dict(q.intervention),
            "target": _atom_to_dict(q.target),
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
        if s.coefficient is not None:
            d["coefficient"] = s.coefficient
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
        # Fix 3+4 (v0.1.5): population (Phase 9) and provenance
        # (Gap B / Fix 3+4) MUST round-trip through
        # _program_to_ast_dict, otherwise apply_patch_and_run's
        # merged_program loses these fields and themis.verify (which
        # re-parses the merged program) builds a different theta
        # than the runtime did. Pre-fix this was silently OK because
        # nothing read either field through the round-trip; Fix 4
        # transport surfaced it as a verify failure.
        if s.population is not None:
            d["population"] = s.population
        if s.provenance != "structural":
            d["provenance"] = s.provenance
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

    Returns ``{"results": [<query_result_dict>, ...], "program":
    <kernel_ast dict>}``. ``results[*]`` conforms to
    ``query_result.schema.json``. ``program`` is the validated /
    normalized AST the kernel actually ran on — same shape as
    ``apply_patch_and_run``'s ``merged_program``. Echoing it back
    means downstream response renderers can surface
    ``program.extensions.ambiguities`` and edge provenance without
    having to retain the original input across turns.

    Raises ``SyntacticError`` / ``SemanticError`` if the input is
    malformed. No natural-language fallbacks — the caller is expected
    to surface the error as structured data too.
    """
    ast = _to_ast(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)
    out = _run_typed(prog)
    out["program"] = _program_to_ast_dict(prog)
    return out


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


def _verify_causation_extensions_match(result: dict, derivation) -> None:
    """Assert ``result.extensions.causation`` agrees with the derivation
    envelope (the dict output of the single
    ``probabilities_of_causation_tian_pearl`` step) that
    ``verify_causation`` already audited. PS/PNS surface to a reader only
    via extensions, so a tamper there must not pass silently.

    Skips quietly when extensions carry no causation block (nothing to
    cross-check). Raises ``VerificationError`` on any numeric divergence.
    """
    ext = (result.get("extensions") or {}).get("causation")
    if ext is None:
        return
    env = derivation[-1].output
    if not isinstance(env, dict):
        raise VerificationError(
            "causation derivation envelope is not a dict; cannot cross-check "
            "extensions",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    tol = 1e-9

    def _num_eq(a, b) -> bool:
        return a is not None and b is not None and abs(float(a) - float(b)) <= tol

    def _fail() -> None:
        raise VerificationError(
            "extensions.causation does not match the verified derivation "
            "envelope (display copy diverges from the audited answer)",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    for q in ("pn", "ps", "pns"):
        a, b = ext.get(q), env.get(q)
        if not isinstance(a, dict) or not isinstance(b, dict):
            _fail()
        if not _num_eq(a.get("lower"), b.get("lower")):
            _fail()
        if not _num_eq(a.get("upper"), b.get("upper")):
            _fail()
        if ("point" in a) != ("point" in b):
            _fail()
        if "point" in a and not _num_eq(a.get("point"), b.get("point")):
            _fail()
    for k in ("p_y_do_x1", "p_y_do_x0"):
        if not _num_eq(ext.get(k), env.get(k)):
            _fail()
    if bool(ext.get("monotonic")) != bool(env.get("monotonic")):
        _fail()
    if ext.get("interventional_risk_provenance") != env.get(
        "interventional_risk_provenance"
    ):
        _fail()
    ja = ext.get("observational_joint") or {}
    jb = env.get("observational_joint") or {}
    for k in ("p_x1_y1", "p_x1_y0", "p_x0_y1", "p_x0_y0"):
        if not _num_eq(ja.get(k), jb.get(k)):
            _fail()


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

    # Linear-SCM counterfactual: the unit's observed factual values
    # (Pearl's evidence E=e) are a verifier premise — the abduction step
    # solves U from them. Numeric observations only (a linear SCM is over
    # real-valued nodes).
    scm_observations: dict = {}
    for s in prog.statements:
        if isinstance(s, ObservationStatement):
            try:
                scm_observations[s.atom] = float(s.value)
            except (TypeError, ValueError):
                continue

    derivation = derivation_from_dict(derivation_json)
    ctx = VerificationContext(
        graph=graph,
        query=query_stmt.query,
        theta=theta,
        bidirected=bidirected,
        selection_nodes=selection_nodes,
        observations=scm_observations or None,
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
            # A backdoor_linear estimate may carry a Cinelli-Hazlett OVB
            # sensitivity block. Unlike the point estimate (data-refit,
            # metadata audit only), it is a closed form of the fit's
            # t-value + dof — so re-derive every number independently.
            ovb = (result.get("numeric_estimate") or {}).get("ovb_sensitivity")
            if ovb is not None:
                verify_ovb_sensitivity(ovb)
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
    elif kind == "causation":
        if "numeric_result" not in result:
            raise ValueError(
                "verify(): causation result must carry a numeric_result"
            )
        claimed = _decode_numeric_result_json(result["numeric_result"])
        verify_causation(derivation, ctx, claimed)
        # The consumer-facing extensions.causation copy carries PS/PNS,
        # which are answer-grade numbers a reader sees only there (the
        # headline numeric_result is just PN). Cross-check it against the
        # derivation envelope that verify_causation just independently
        # audited, so a tamper of the display copy alone cannot pass.
        _verify_causation_extensions_match(result, derivation)
    elif kind == "scm_counterfactual":
        if "numeric_result" not in result:
            raise ValueError(
                "verify(): scm_counterfactual result must carry a numeric_result"
            )
        claimed = _decode_numeric_result_json(result["numeric_result"])
        verify_scm_counterfactual(derivation, ctx, claimed)
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

    # Iter 126/127/130: independent audit of bounds_result. Each
    # producer has a dedicated verifier; verifier trilogy now complete
    # for the 3 implemented BoundsMethod values.
    bounds_result = result.get("bounds_result")
    if bounds_result is not None:
        method = bounds_result.get("method")
        if method == "manski_tamer_monotonicity":
            from .verifier.bounds_rules import (
                verify_manski_tamer_bounds_result,
            )
            verify_manski_tamer_bounds_result(
                bounds_result,
                program=ast,
                query_dict=_query_to_dict(query_stmt.query),
            )
        elif method == "manski_natural":
            from .verifier.bounds_rules import (
                verify_manski_natural_bounds_result,
            )
            verify_manski_natural_bounds_result(
                bounds_result,
                query_dict=_query_to_dict(query_stmt.query),
            )
        elif method == "balke_pearl_iv":
            from .verifier.bounds_rules import (
                verify_balke_pearl_iv_bounds_result,
            )
            verify_balke_pearl_iv_bounds_result(
                bounds_result,
                query_dict=_query_to_dict(query_stmt.query),
            )


def verify_bounds_result(program: dict | str | bytes, result: dict) -> None:
    """Iter 133 — independently audit ``result.bounds_result`` (Phase 12 +
    iter 119 producers).

    Public entry parallel to :func:`verify_data_gap_report`. Unlike
    :func:`verify`, this function does NOT require a derivation chain
    on the result — bounds typically attach when point identification
    fails (status=needs_investigation) and no derivation chain exists,
    so the existing verify() path is dormant for that case (see iter
    126/127/130 commits).

    Dispatches by ``bounds_result.method`` to the dedicated verifier
    (manski_natural / manski_tamer_monotonicity / balke_pearl_iv).
    Raises :class:`themis.verifier.errors.VerificationError` on any
    mismatch (canonical-shape tampering, wrong assumption tags,
    missing monotonicity declaration, etc.). Returns ``None`` on
    accept. Raises ``ValueError`` for missing bounds_result, missing
    query_id, or unsupported method.

    The frontdoor_partial method has no producer yet (aspirational
    enum value); calling this function on an emitted
    frontdoor_partial bounds_result raises ``ValueError`` until that
    verifier lands.
    """
    if not isinstance(result, dict):
        raise TypeError(
            f"result must be a dict; got {type(result).__name__}"
        )
    validate_result(result)

    bounds_result = result.get("bounds_result")
    if bounds_result is None:
        raise ValueError(
            "verify_bounds_result() requires result.bounds_result; this "
            "result has none. Use themis.verify() for non-bounds results."
        )

    target_id = result.get("query_id")
    if target_id is None:
        raise ValueError(
            "verify_bounds_result() requires result.query_id to locate "
            "the matching query in the program"
        )

    ast = _to_ast(program)
    ast = validate_ast(ast)
    prog = validate_program(ast)

    query_stmt = None
    for s in prog.statements:
        if isinstance(s, QueryStatement) and s.id == target_id:
            query_stmt = s
            break
    if query_stmt is None:
        raise ValueError(
            f"verify_bounds_result(): no query with id={target_id!r} "
            "in the program"
        )

    method = bounds_result.get("method")
    if method == "manski_natural":
        from .verifier.bounds_rules import (
            verify_manski_natural_bounds_result,
        )
        verify_manski_natural_bounds_result(
            bounds_result,
            query_dict=_query_to_dict(query_stmt.query),
        )
    elif method == "manski_tamer_monotonicity":
        from .verifier.bounds_rules import (
            verify_manski_tamer_bounds_result,
        )
        verify_manski_tamer_bounds_result(
            bounds_result,
            program=ast,
            query_dict=_query_to_dict(query_stmt.query),
        )
    elif method == "balke_pearl_iv":
        from .verifier.bounds_rules import (
            verify_balke_pearl_iv_bounds_result,
        )
        verify_balke_pearl_iv_bounds_result(
            bounds_result,
            query_dict=_query_to_dict(query_stmt.query),
        )
    elif method == "frontdoor_partial":
        raise ValueError(
            "frontdoor_partial bounds verifier is not yet implemented "
            "(no producer either — aspirational BoundsMethod enum value)"
        )
    else:
        raise ValueError(
            f"verify_bounds_result(): unsupported bounds method {method!r}"
        )


def verify_data_gap_report(result: dict) -> None:
    """Independently audit the ``data_gap_report`` inside one result.

    This is the public T10-only counterpart to :func:`verify`. It is
    deliberately result-only: data-gap reports cite the result envelope's
    derivation / investigation requests / framing notes, not the source
    program graph. It also accepts results with no derivation, which is
    necessary for advisory/diagnostic outputs such as Phase 13
    dose-response data requirements.

    Returns ``None`` on accept. Raises ``VerificationError`` or
    ``SyntacticError`` on malformed or inconsistent reports.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)

    from .verifier.data_gap_rules import verify_data_gap_report as _verify_t10

    _verify_t10(
        result.get("data_gap_report"),
        derivation=result.get("derivation"),
        investigation_requests=result.get("investigation_requests", []),
        framing_notes=result.get("framing_notes", []),
    )
