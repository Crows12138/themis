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

from . import blocks
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
    CounterfactualConjunctionQuery,
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
    MissingnessIndicator,
    Program,
    ProximalEffectQuery,
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
    verify_assumption_ledger as _verify_assumption_ledger_rule,
    verify_cluster_inference as _verify_cluster_inference_rule,
    verify_outcome_error as _verify_outcome_error_rule,
    verify_causation,
    verify_causation_numeric,
    verify_counterfactual_cell_numeric,
    verify_cause,
    verify_counterfactual,
    verify_counterfactual_conjunction,
    verify_combined_measurement_correction_numeric,
    verify_ctf_conjunction_numeric,
    verify_dose_response_curve,
    verify_e_value,
    verify_exposure_measurement_correction_numeric,
    verify_iv_overid_numeric,
    verify_longitudinal_numeric,
    verify_measurement_correction_numeric,
    verify_mediation_numeric,
    verify_regression_calibration_numeric,
    verify_scm_counterfactual,
    verify_scm_counterfactual_numeric,
    verify_effect_structural,
    verify_identify,
    verify_numeric,
    verify_missing_data_recovery,
    verify_numeric_estimate,
    verify_ovb_sensitivity,
    verify_proximal_effect,
    verify_proximal_numeric,
    verify_selection_recovery,
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
            ext[blocks.LLM_PROPOSED_REVIEW] = review
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
            rd.setdefault("extensions", {})[blocks.ASSUMPTION_LEDGER] = ledger
    for rd in result_dicts:
        blocks.check_registered(rd)
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
    if isinstance(q, CounterfactualConjunctionQuery):
        def _event_to_dict(e):
            return {
                "variable": _atom_to_dict(e.variable),
                "subscript": [_valued_atom_to_dict(s) for s in e.subscript],
                "value": e.value,
            }
        out: dict = {
            "kind": "counterfactual_conjunction",
            "events": [_event_to_dict(e) for e in q.events],
        }
        if q.condition:
            out["condition"] = [_event_to_dict(e) for e in q.condition]
        return out
    if isinstance(q, ProximalEffectQuery):
        return {
            "kind": "proximal_effect",
            "treatment": _atom_to_dict(q.treatment),
            "outcome": _atom_to_dict(q.outcome),
            "latent": _atom_to_dict(q.latent),
            "treatment_proxy": _atom_to_dict(q.treatment_proxy),
            "outcome_proxy": _atom_to_dict(q.outcome_proxy),
            "latent_cardinality": q.latent_cardinality,
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
                      "direction", "baseline", "state_vs_event", "scale"):
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
    if isinstance(s, MissingnessIndicator):
        d = {
            "kind": "missingness_indicator",
            "id": s.id,
            "missing_var": _atom_to_dict(s.missing_var),
            "caused_by": [_atom_to_dict(a) for a in s.caused_by],
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


def _verify_scm_counterfactual_extensions_match(result: dict) -> None:
    """The data path's ``extensions.scm_counterfactual`` display copy carries a
    ``target_value`` (the counterfactual value a reader sees). It must equal the
    audited ``numeric_estimate.point`` — otherwise a tamper of the display copy
    alone would slip past ``verify_scm_counterfactual_numeric`` (which audits the
    numeric_estimate, not the extension). Skips quietly when absent."""
    ext = (result.get("extensions") or {}).get("scm_counterfactual")
    if ext is None:
        return
    num_est = result.get("numeric_estimate") or {}
    point = num_est.get("point")
    tv = ext.get("target_value")
    if point is None or tv is None or abs(float(tv) - float(point)) > 1e-9:
        raise VerificationError(
            "extensions.scm_counterfactual.target_value does not match the "
            "audited numeric_estimate.point (display copy diverges)",
            step_index=None, rule="numeric_scm_counterfactual_estimate",
        )


def _verify_causation_numeric_extensions_match(result: dict, derivation) -> None:
    """Numeric analogue of ``_verify_causation_extensions_match``.

    The data path's ``extensions.causation`` display copy must agree with the
    ``numeric_causation_estimate`` step's inputs (the pn/ps/pns bounds + points,
    do-risks, joint), which ``verify_causation_numeric`` already re-derived
    independently. Reads the FLAT inputs of the numeric step rather than a
    tian_pearl envelope. Skips quietly when no causation extension is present.
    """
    ext = (result.get("extensions") or {}).get("causation")
    if ext is None:
        return
    inp = derivation[-1].inputs
    if not isinstance(inp, dict):
        raise VerificationError(
            "causation numeric derivation inputs are not a dict; cannot "
            "cross-check extensions",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    tol = 1e-9

    def _num_eq(a, b) -> bool:
        return a is not None and b is not None and abs(float(a) - float(b)) <= tol

    def _fail() -> None:
        raise VerificationError(
            "extensions.causation does not match the verified numeric "
            "derivation inputs (display copy diverges from the audited answer)",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    for q in ("pn", "ps", "pns"):
        a = ext.get(q)
        if not isinstance(a, dict):
            _fail()
        if not _num_eq(a.get("lower"), inp.get(f"{q}_lower")):
            _fail()
        if not _num_eq(a.get("upper"), inp.get(f"{q}_upper")):
            _fail()
        # Points exist only under monotonicity; a bounds answer carries point=None
        # on both sides (consistent). Otherwise the display point must match.
        ap, ip = a.get("point"), inp.get(f"{q}_point")
        if (ap is not None or ip is not None) and not _num_eq(ap, ip):
            _fail()
    for k in ("p_y_do_x1", "p_y_do_x0"):
        if not _num_eq(ext.get(k), inp.get(k)):
            _fail()
    if bool(ext.get("monotonic")) != bool(inp.get("monotonic")):
        _fail()
    if ext.get("interventional_risk_provenance") != inp.get(
        "interventional_risk_provenance"
    ):
        _fail()
    ja = ext.get("observational_joint") or {}
    for k in ("p_x1_y1", "p_x1_y0", "p_x0_y1", "p_x0_y0"):
        if not _num_eq(ja.get(k), inp.get(k)):
            _fail()


def _verify_counterfactual_cell_extensions_match(result: dict, derivation) -> None:
    """The data path's ``extensions.counterfactual_cell`` display copy must
    agree with the ``numeric_counterfactual_cell_estimate`` step's inputs,
    which ``verify_counterfactual_cell_numeric`` already re-derived
    independently. Skips quietly when no such extension is present.
    """
    ext = (result.get("extensions") or {}).get("counterfactual_cell")
    if ext is None:
        return
    inp = derivation[-1].inputs
    if not isinstance(inp, dict):
        raise VerificationError(
            "counterfactual-cell numeric derivation inputs are not a dict; "
            "cannot cross-check extensions",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )
    tol = 1e-9

    def _fail() -> None:
        raise VerificationError(
            "extensions.counterfactual_cell does not match the verified "
            "numeric derivation inputs (display copy diverges from the "
            "audited answer)",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    def _num_eq(a, b) -> bool:
        if a is None or b is None:
            return a is None and b is None
        return abs(float(a) - float(b)) <= tol

    for k in ("lower", "upper", "point", "p_y_do_x_cf"):
        if not _num_eq(ext.get(k), inp.get(k)):
            _fail()
    if ext.get("interventional_risk_provenance") != inp.get(
        "interventional_risk_provenance"
    ):
        _fail()
    joint = ext.get("observational_joint") or {}
    for k in ("p_x1_y1", "p_x1_y0", "p_x0_y1", "p_x0_y0"):
        if not _num_eq(joint.get(k), inp.get(k)):
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

    # Phase 9 §S9.1: an effect result may carry a Bareinboim-Pearl
    # selection-recovery block in its extensions. It is a set of
    # d-separation facts + a closed-form recovery formula, independent of
    # the derivation chain, so re-derive it against the graph regardless
    # of the result's status.
    _sel_rec = (result.get("extensions") or {}).get("selection_recovery")
    if _sel_rec is not None:
        verify_selection_recovery(_sel_rec, graph)

    # Phase 9 §S9.2: an effect result may carry a Mohan-Pearl-Tian
    # missing-data recovery block. Re-derive it (m-graph classification +
    # ordered factorization) against the graph + declared indicators.
    _md_rec = (result.get("extensions") or {}).get("missing_data_recovery")
    if _md_rec is not None:
        _mi_stmts = [
            s for s in prog.statements if isinstance(s, MissingnessIndicator)
        ]
        verify_missing_data_recovery(
            _md_rec, graph, _mi_stmts, query_stmt.query
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
            # The mediation path attaches numeric answer blocks (Imai NDE/NIE
            # + the two four-way splits) to this structurally_solved result;
            # the structural verifier above doesn't inspect them. Re-derive
            # the ratio-scale four-way from its recorded coefficients and
            # check the construction identities of the rest.
            num_est = result.get("numeric_estimate")
            if num_est is not None:
                verify_mediation_numeric(num_est)
        elif (
            status == "numerically_solved"
            and kind == "effect"
            and "numeric_estimate" in result
            and bool(derivation)
            and derivation[-1].rule != "numeric_result"
        ):
            # Phase 7.1: data-based effect estimate. Final step is
            # numeric_backdoor_estimate (relaxed metadata audit).
            #
            # Routing keys on the derivation's TERMINAL, not merely on a
            # numeric_estimate being present: for a back-door style estimate
            # the data estimate IS the terminal, but a mediation
            # decomposition can carry two independent numeric channels — a
            # theta evaluation that terminates in numeric_result, plus a
            # DataFrame estimate of the same decomposition. Those are
            # different numbers, so tying one to the other's terminal would
            # reject an honest result. The numeric_result terminal is handled
            # in the else branch, which audits both channels on their own
            # terms.
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_numeric_estimate(derivation, ctx, claimed)
            # A backdoor_linear estimate may carry a Cinelli-Hazlett OVB
            # sensitivity block. Unlike the point estimate (data-refit,
            # metadata audit only), it is a closed form of the fit's
            # t-value + dof — so re-derive every number independently.
            ovb = (result.get("numeric_estimate") or {}).get("ovb_sensitivity")
            if ovb is not None:
                verify_ovb_sensitivity(ovb)
            # The same numeric estimate may also carry a VanderWeele-Ding
            # E-value block — also a closed form of the audited ATE plus one
            # recorded conversion input (baseline rate / outcome SD), so
            # re-derive its risk ratio and both E-values independently too.
            num_est = result.get("numeric_estimate") or {}
            if num_est.get("sensitivity_analysis") is not None:
                verify_e_value(num_est)
            # Over-identified 2SLS (q >= 2 instruments): its derivation terminal
            # (numeric_iv_overid_estimate) does metadata + structural licensing
            # only — the Sargan test and the point are re-derived here from the
            # recorded residualised moment matrices (which don't fit the
            # derivation-input serialization).
            if num_est.get("method") == "iv_2sls_overid":
                verify_iv_overid_numeric(num_est)
            # Measurement-error correction (frontier E): its derivation terminal
            # (numeric_measurement_correction_estimate) does metadata +
            # structural licensing only — the confusion-matrix inversion and the
            # corrected/naive point are re-derived here from the recorded matrix
            # + per-stratum value-count vectors (which don't fit derivation-input
            # serialization).
            if num_est.get("method") == "measurement_error_correction":
                verify_measurement_correction_numeric(num_est)
            # Exposure (treatment) misclassification — the matrix method inverts
            # the channel on the exposure margin of the (X, Y) joint; re-derived
            # here from the recorded matrix + per-stratum 2×k joint tables.
            if num_est.get("method") == "exposure_measurement_error_correction":
                verify_exposure_measurement_correction_numeric(num_est)
            # Both channels misclassified — the joint is inverted on both sides
            # at once; re-derived here from the two recorded matrices + the same
            # per-stratum 2×k joint tables.
            if num_est.get("method") == "combined_measurement_error_correction":
                verify_combined_measurement_correction_numeric(num_est)
            # Continuous mismeasurement (regression calibration): the
            # de-attenuated slope is re-derived here from the recorded design
            # covariance matrix Σ_WZ + Cov((W,Z),Y) + σ²_u (which don't fit
            # derivation-input serialization).
            if num_est.get("method") == "regression_calibration":
                verify_regression_calibration_numeric(num_est)
            # A dose-response estimate carries a curve array that the
            # metadata audit doesn't inspect (it only sees the headline
            # scalar). Audit the curve's construction invariants — the
            # answer object otherwise ships checked for JSON shape only.
            if num_est.get("dose_response_curve") is not None:
                verify_dose_response_curve(num_est)
            # Phase 7.L — a longitudinal g-formula / IPW-MSM estimate rides on
            # an identify_via_gformula structural terminal (accepted above),
            # but its strategy-contrast number is otherwise unaudited: the
            # relaxed metadata audit doesn't re-derive it. Re-derive the
            # IPW-MSM contrast from the recorded MSM coefficients + check the
            # g-formula construction identities.
            if (
                num_est.get("longitudinal_ipw_msm") is not None
                or num_est.get("longitudinal_gformula") is not None
            ):
                verify_longitudinal_numeric(num_est)
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    f"verify(): {kind} result must carry a numeric_result"
                )
            claimed = _decode_numeric_result_json(result["numeric_result"])
            verify_numeric(derivation, ctx, claimed)
            # A theta-evaluated mediation decomposition (single mediator or a
            # joint block) may ALSO carry a DataFrame estimate of the same
            # split. verify_numeric audited the theta derivation above; audit
            # the data channel the same way the structurally_solved branch
            # does, so attaching data never leaves a number unchecked.
            num_est = result.get("numeric_estimate")
            if num_est is not None:
                verify_mediation_numeric(num_est)
    elif kind == "counterfactual":
        if (
            result.get("status") == "numerically_solved"
            and "numeric_estimate" in result
        ):
            # Data path (themis.estimate): the cell was re-solved from the
            # EMPIRICAL joint + a g-formula do-risk rather than from theta. The
            # single numeric_counterfactual_cell_estimate rule re-solves the
            # consistency identity on the reported inputs and re-derives, from
            # the query alone, whether the cell needed a do-risk at all.
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_counterfactual_cell_numeric(derivation, ctx, claimed)
            # The extensions.counterfactual_cell display copy (the interval and
            # the inputs a reader sees only there) must agree with the audited
            # derivation, so a tamper of the display copy alone cannot pass.
            _verify_counterfactual_cell_extensions_match(result, derivation)
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    "verify(): counterfactual result must carry a numeric_result"
                )
            claimed = _decode_numeric_result_json(result["numeric_result"])
            verify_counterfactual(derivation, ctx, claimed)
    elif kind == "causation":
        if (
            result.get("status") == "numerically_solved"
            and "numeric_estimate" in result
        ):
            # Data path (themis.estimate): PN/PS/PNS recovered from a DataFrame
            # (empirical joint + g-formula do-risks → Tian-Pearl). The single
            # numeric_causation_estimate rule re-derives the theorem on the
            # reported inputs and re-checks the adjustment set on the graph.
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_causation_numeric(derivation, ctx, claimed)
            # The extensions.causation display copy (PS/PNS + bounds a reader
            # sees only there) must agree with the audited numeric derivation
            # inputs, so a tamper of the display copy alone cannot pass.
            _verify_causation_numeric_extensions_match(result, derivation)
        else:
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
        if (
            result.get("status") == "numerically_solved"
            and "numeric_estimate" in result
        ):
            # Data path (themis.estimate): the linear SCM's coefficients were
            # FITTED from a DataFrame (per-node OLS) rather than declared on the
            # edges, then abduction-action-prediction for the unit. The single
            # numeric_scm_counterfactual_estimate terminal is a metadata audit;
            # the point + fitted coefficients are re-derived here from the
            # recorded per-node moment matrices + observed unit (which don't fit
            # derivation-input serialization).
            claimed = _decode_structural_result_json(result["structural_result"])
            num_est = result.get("numeric_estimate")
            verify_scm_counterfactual_numeric(derivation, ctx, claimed, num_est)
            # The extensions.scm_counterfactual display copy (the counterfactual
            # value a reader sees) must agree with the audited numeric point, so
            # a tamper of the display copy alone cannot pass.
            _verify_scm_counterfactual_extensions_match(result)
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    "verify(): scm_counterfactual result must carry a numeric_result"
                )
            claimed = _decode_numeric_result_json(result["numeric_result"])
            verify_scm_counterfactual(derivation, ctx, claimed)
    elif kind == "counterfactual_conjunction":
        claimed = _decode_structural_result_json(result["structural_result"])
        if (
            result.get("status") == "numerically_solved"
            and "numeric_estimate" in result
        ):
            # Data path (themis.estimate): the ID*/IDC* estimand was
            # evaluated to a point by the non-parametric plug-in. Verify the
            # numeric derivation (ctf_conjunction_criterion re-runs the
            # engine; numeric_ctf_conjunction_estimate audits the metadata).
            verify_ctf_conjunction_numeric(derivation, ctx, claimed)
        else:
            verify_counterfactual_conjunction(derivation, ctx, claimed)
    elif kind == "proximal_effect":
        claimed = _decode_structural_result_json(result["structural_result"])
        if (
            result.get("status") == "numerically_solved"
            and "numeric_estimate" in result
        ):
            # Data path (themis.estimate): the proximal ATE was recovered by
            # Miao formula (5). Verify the numeric derivation
            # (proximal_criterion re-runs identify_proximal; the
            # numeric_proximal_estimate rule audits the metadata).
            verify_proximal_numeric(derivation, ctx, claimed)
        else:
            verify_proximal_effect(derivation, ctx, claimed)
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

    # Independent audit of the assumption ledger. Same shape as the gap-report
    # audit above and for the same reason: the ledger is a disclosure surface,
    # so its failure mode is one-sided — an assumption that never reaches it
    # is indistinguishable from an assumption nobody makes.
    _verify_assumption_ledger_rule(result)

    # Independent audit of cluster-robust inference disclosure — the third
    # one-sided surface: a dropped cluster column moves only the interval
    # WIDTH, so nothing in the point estimate reveals it. Checked here
    # because the run-level column and the estimator's own declaration both
    # ride on the result.
    _verify_cluster_inference_rule(result)

    # Independent audit of the outcome measurement-error assessment. The block
    # changes no number, so the only thing that can be wrong with it is its
    # arithmetic or its silence — and the premise it leaves unsaid
    # (non-differential error) is the one holding the point estimate up.
    _verify_outcome_error_rule(result)

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

    # 2026-07-11 pre-flight data diagnostic: independently re-derive any
    # declared_type_data_mismatch verdicts from the recorded sufficient
    # statistics and confirm the attached gaps match. No-op when the result
    # carries no reconciliation block.
    from .verifier.type_reconciliation_rules import verify_type_reconciliation

    verify_type_reconciliation(result)


def verify_assumption_ledger(result: dict) -> None:
    """Independently audit the ``extensions.assumption_ledger`` of one result.

    The result-only counterpart to :func:`verify`, parallel to
    :func:`verify_data_gap_report`: the ledger attaches to results whose status
    never flips to ``numerically_solved`` (a mediation decomposition keeps its
    structural answer primary), so it must be auditable without a derivation
    chain.

    Returns ``None`` on accept. Raises ``VerificationError`` when the ledger
    under-discloses what the envelope's channels declare.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _verify_assumption_ledger_rule(result)


def verify_cluster_inference(result: dict) -> None:
    """Independently audit one result's cluster-robustness disclosure.

    The result-only counterpart to :func:`verify`, for the same reason as
    :func:`verify_assumption_ledger`: a clustered run's numeric block can ride
    on a result whose status never flips to ``numerically_solved``, so the
    audit must not require a derivation chain.

    Returns ``None`` on accept. Raises ``VerificationError`` when an interval
    computed under a clustered run says nothing about the cluster column, or
    when a cluster-robustness claim is not supported by the envelope.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _verify_cluster_inference_rule(result)


def verify_outcome_error(result: dict) -> None:
    """Independently audit one result's outcome measurement-error assessment.

    The result-only counterpart to :func:`verify`, for the same reason as
    :func:`verify_cluster_inference`: the assessment rides on the result rather
    than on a derivation chain, and it can attach to an answer whose status
    never flips to ``numerically_solved``.

    Returns ``None`` on accept. Raises ``VerificationError`` when a reported
    scalar does not follow from the recorded moments, when the assessed design
    is not the design the estimate fitted, or when the assessment's premises —
    above all the non-differential-error premise that is the reason no
    correction was applied — never reach the estimate's declared assumptions.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _verify_outcome_error_rule(result)


def verify_markov_blanket(result: dict) -> None:
    """Independently audit a Markov-blanket result (borrow-list #4).

    Parallel to :func:`verify_bounds_result`: the artifact is a standalone
    Markov-blanket dict (from
    :func:`themis.estimation.discovery.markov_blanket_to_dict` / the
    ``themis_markov_blanket`` MCP tool), not a query_result envelope, so there
    is no derivation chain or source program to cross-reference — hence a
    dedicated public entry rather than the :func:`verify` path.

    Re-checks the completeness + minimality Markov-blanket definition directly
    on the returned set, recomputing every conditional-independence test from
    the recorded sufficient statistic — the correlation matrix (continuous,
    Fisher-Z) or the joint contingency counts (discrete, chi-square) — with an
    independent reimplementation of the test (no re-run of the grow-shrink
    search). Returns ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` on any structural
    inconsistency, an ill-formed sufficient statistic, a recorded test that
    disagrees with the recomputation, or a blanket that violates its own
    definition at the stated alpha.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.markov_blanket_rules import (
        verify_markov_blanket as _verify_mb,
    )

    _verify_mb(result)


def verify_orientation_propagation(result: dict) -> None:
    """Independently audit a Meek orientation-propagation result (Phase 1 of
    interactive equivalence-class resolution).

    Parallel to :func:`verify_markov_blanket`: the artifact is a standalone
    ``orientation_propagation`` dict (from
    :func:`themis.estimation.orientation.orientation_to_dict`), not a
    query_result envelope, so it has a dedicated public entry rather than the
    :func:`verify` path.

    Re-derives the Meek closure from the recorded input CPDAG and constraints
    with a second, standalone transcription of rules R1-R4 and the
    constraint-application / conflict-detection logic (no call to the producer,
    no causal-learn). Returns ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` when the ``oriented`` set
    disagrees with the independent closure, a data-contradicting constraint was
    silently applied instead of flagged, or a provenance entry is unjustified.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.orientation_rules import (
        verify_orientation_propagation as _verify_orient,
    )

    _verify_orient(result)


def verify_orientation_questions(result: dict) -> None:
    """Independently audit a compiled orientation question set (Phase 2 of
    interactive equivalence-class resolution).

    Parallel to :func:`verify_orientation_propagation`: the artifact is a
    standalone ``orientation_question_set`` dict (from
    :func:`themis.estimation.orientation_questions.question_set_to_dict`), not a
    query_result envelope, so it has a dedicated public entry.

    Re-enumerates the equivalence class from the recorded post-propagation CPDAG
    with a second, standalone transcription (no call to the producer), and checks
    every conflict question echoes a real conflict, every leverage number matches
    the recomputed coverage gain, and the orientation questions form a genuine
    cover of the undetermined edges. Minimality is not certified (the cover is
    greedy). Returns ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` on any mismatch.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.orientation_question_rules import (
        verify_orientation_questions as _verify_q,
    )

    _verify_q(result)


def verify_orientation_session(result: dict) -> None:
    """Independently audit an interactive orientation-resolution session (Phase 3
    of interactive equivalence-class resolution).

    The artifact is a standalone ``orientation_session`` dict (from
    :func:`themis.estimation.orientation_session.session_to_dict`). It embeds a
    Phase 1 ``orientation_propagation`` dict and a Phase 2
    ``orientation_question_set`` dict; the verifier delegates those to their own
    auditors and then certifies the session glue — that the constraints are the
    latest-wins projection of the recorded answers, the embedded artifacts are the
    session's own, ``deferred`` is exactly the still-open unknowns, the source
    trail credits every applied answer with its true entailment, and the status is
    correct — all re-derived from the answers (no producer call). Returns ``None``
    on accept; raises :class:`themis.verifier.errors.VerificationError` on any
    mismatch.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.orientation_session_rules import (
        verify_orientation_session as _verify_sess,
    )

    _verify_sess(result)


def verify_orientation_ledger_export(result: dict) -> None:
    """Independently audit an orientation-session ledger export (Phase 5 of
    interactive equivalence-class resolution — the assumption-ledger wiring).

    The artifact is a standalone ``orientation_ledger_export`` dict (from
    :func:`themis.estimation.orientation_ledger.orientation_ledger_export`). It
    embeds a Phase 3 ``orientation_session`` dict; the verifier delegates that to
    :func:`verify_orientation_session` and then independently re-derives every
    oriented edge's ledger ``source`` — propagating the ``llm_proposal`` taint
    through the Meek closure — checking the ``edges``, ``proposal_edges``,
    ``cause_statements`` sources, and ``graph_learned_from_data`` match. Returns
    ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` on any mismatch (notably an
    edge that rests on an LLM-proposed answer but is disclosed as anything else).
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.orientation_ledger_rules import (
        verify_orientation_ledger_export as _verify_led,
    )

    _verify_led(result)


def verify_selection_recovery_numeric(result: dict) -> None:
    """Independently audit a selection-backdoor recovered ATE (§S9.1 numeric).

    The artifact is a query_result whose ``numeric_estimate`` was produced by
    the selection-backdoor recovery estimator (method
    ``selection_backdoor_recovery``). This re-runs the Bareinboim-Pearl
    Theorem-3.5 formula from the recorded sufficient statistics — the
    per-stratum biased ``(n, y_sum)`` counts and the external unbiased weight
    tables P(z⁺) / P(z⁻|x,z⁺) — as a second, standalone transcription, and
    checks the reported ATE and the two arms match, and that the weight tables
    are proper distributions. It never imports the producer estimator and never
    re-touches the raw data; a result carrying no such numeric_estimate is a
    no-op. Raises :class:`themis.verifier.errors.VerificationError` on mismatch.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.selection_numeric_rules import (
        verify_selection_recovery_numeric as _verify_sel,
    )

    _verify_sel(result)


def verify_missing_data_numeric(result: dict) -> None:
    """Independently audit a recovered-from-missing-data ATE (§S9.2 numeric).

    The artifact is a query_result whose ``numeric_estimate`` was produced by
    the missing-data recovery estimator (method
    ``missing_data_recovery_gformula``). This re-runs the Mohan-Pearl-Tian
    g-formula Σ_z (E[Y|1,z]−E[Y|0,z])·P(z) from the recorded per-stratum
    sufficient statistics — the {n, y_sum} conditionals and {z, count} marginal
    tables for the recovered estimate and, when present, the naive listwise foil
    — as a second, standalone transcription, and checks the reported point, the
    marginal normalisation, and that no contributing stratum was dropped. It
    never imports the producer estimator and never re-touches the raw data; the
    numeric result carries no derivation (it is ``needs_investigation``), so this
    is the audit path — the derivation-gated ``themis.verify`` cannot reach it. A
    result carrying no such numeric_estimate is a no-op. Raises
    :class:`themis.verifier.errors.VerificationError` on mismatch.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.missing_numeric_rules import (
        verify_missing_data_numeric as _verify_md,
    )

    _verify_md(result)
