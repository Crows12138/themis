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
- ``verify_bounds_results`` — independent audit of bounds_results via
  the per-method verifiers
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
from collections.abc import Callable
from dataclasses import dataclass, field

import networkx as nx
from typing import NoReturn

from . import audits, blocks, refusals
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
from .ledger import Monotonicity
from .types import (
    Annotation,
    AssocQuery,
    Atom,
    BidirectedStatement,
    FeedbackLoop,
    CausationQuery,
    CounterfactualConjunctionQuery,
    CounterfactualQuery,
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
    verify_bootstrap_records as _verify_bootstrap_records_rule,
    verify_cluster_inference as _verify_cluster_inference_rule,
    verify_berkson_error as _verify_berkson_error_rule,
    verify_survival_curve as _verify_survival_curve_rule,
    verify_outcome_error as _verify_outcome_error_rule,
    verify_fingerprints_agree as _verify_fingerprints_rule,
    verify_one_row_count as _verify_one_row_count_rule,
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
    verify_acr_decomposition,
    verify_exposure_measurement_correction_numeric,
    verify_frontdoor_empirical_numeric,
    verify_iv_overid_numeric,
    verify_treatment_box,
    verify_longitudinal_numeric,
    verify_measurement_correction_numeric,
    verify_mediation_numeric,
    verify_differential_error_numeric,
    verify_differential_outcome_error_numeric,
    verify_regression_calibration_numeric,
    verify_simex_numeric,
    verify_scm_counterfactual,
    verify_scm_counterfactual_numeric,
    verify_effect_structural,
    verify_identify,
    verify_numeric,
    verify_missing_data_recovery,
    verify_numeric_estimate,
    verify_ovb_sensitivity,
    verify_proximal_effect,
    verify_proximal_estimand,
    verify_proximal_numeric,
    verify_identification_pattern,
    verify_ambiguity_copy,
    verify_answer_names_its_question,
    verify_confidence_level,
    verify_envelope_arithmetic,
    verify_gap_names,
    verify_gap_subjects,
    verify_mechanism_target,
    verify_investigation_items,
    verify_identification_formula,
    verify_fitted_diagnostics,
    verify_frame,
    verify_post_stratification,
    verify_feedback_loop,
    verify_iv_surfaces,
    verify_llm_proposed_review,
    verify_numeric_display_agrees,
    verify_joint_identification,
    verify_longitudinal_identification,
    verify_mediation_decomposition,
    verify_selection_recovery,
    verify_transport_sources,
    verify_vector_iv_identification,
    verify_vector_iv_region,
)


@dataclass(frozen=True)
class _RouteFacts:
    """What a route audit is allowed to read.

    One shape for all of them, because a table whose entries each take
    their own arguments is a table that cannot be iterated — and iterating
    it is the whole point: the binding below can only mean something if the
    thing it binds is what actually runs.

    The envelope is in here beside the premises, and deliberately. Three of
    these claims are stated in more than one block — the IV surface and its
    source, the two mediation twins, the loop and the instrument it
    licensed — so an audit that could see only "its own" block would be
    unable to ask the question that matters about them, which is whether
    the copies agree.
    """

    result: dict
    graph: "nx.DiGraph"
    bidirected: frozenset
    query: object
    program: Program
    feedback: frozenset

    def carries(self, name: str) -> "dict | None":
        """One block of this envelope, or None where it is absent.

        Not ``block``: in this package that word already files a refusal
        and already names what an adjustment set does to a path, and a
        third sense on the same syllable is how a reader stops trusting
        any of them.
        """
        return (self.result.get("extensions") or {}).get(name)


def _audit_identification(facts: "_RouteFacts") -> None:
    """The one sentence a reader gets about where the answer came from,
    and the second block the IV strategy states it in. Both, together,
    because passing the criterion is not agreeing."""
    surface = facts.carries("identification")
    instrument = facts.carries("iv_identification")
    if surface is not None:
        verify_identification_pattern(
            surface, facts.graph, facts.bidirected, facts.query)
    if surface is not None or instrument is not None:
        verify_iv_surfaces(
            surface, instrument, facts.graph, facts.bidirected, facts.query)


def _audit_joint_identification(facts: "_RouteFacts") -> None:
    block = facts.carries("joint_identification")
    if block is not None:
        verify_joint_identification(
            block, facts.graph, facts.bidirected, facts.query)


def _audit_vector_iv_identification(facts: "_RouteFacts") -> None:
    block = facts.carries("vector_iv_identification")
    if block is not None:
        verify_vector_iv_identification(
            block, facts.graph, facts.bidirected, facts.query)


def _audit_mediation(facts: "_RouteFacts") -> None:
    """One criterion, two blocks: Pearl's conditions over a mediator SET
    reduce to his own at a singleton."""
    for name in ("mediation_decomposition", "mediation_joint_decomposition"):
        block = facts.carries(name)
        if block is not None:
            verify_mediation_decomposition(
                block, facts.graph, facts.bidirected, facts.query)


def _audit_feedback_loop(facts: "_RouteFacts") -> None:
    block = facts.carries("feedback_loop")
    if block is not None:
        verify_feedback_loop(
            block, facts.carries("iv_identification"), facts.feedback,
            facts.query)


def _audit_longitudinal_identification(facts: "_RouteFacts") -> None:
    block = facts.carries("longitudinal_identification")
    if block is not None:
        verify_longitudinal_identification(
            block, (facts.program.options or {}).get("longitudinal"),
            facts.graph, facts.bidirected)


def _audit_proximal_estimand(facts: "_RouteFacts") -> None:
    block = facts.carries("proximal_estimand")
    if block is not None:
        verify_proximal_estimand(block, facts.query)


def _audit_transport_identification(facts: "_RouteFacts") -> None:
    """Several transporting domains are several estimands of ONE target
    quantity, so whether they agree — and whether a number was therefore
    reported or withheld — is a closed form of what the block records."""
    block = facts.carries("transport_identification")
    if block is not None:
        verify_transport_sources(block)


def _audit_selection_recovery(facts: "_RouteFacts") -> None:
    block = facts.carries("selection_recovery")
    if block is not None:
        verify_selection_recovery(block, facts.graph)


def _audit_missing_data_recovery(facts: "_RouteFacts") -> None:
    block = facts.carries("missing_data_recovery")
    if block is not None:
        verify_missing_data_recovery(
            block, facts.graph,
            [s for s in facts.program.statements
             if isinstance(s, MissingnessIndicator)],
            facts.query)


def _audit_survival_curve(facts: "_RouteFacts") -> None:
    """Not a disclosure beside the answer but the answer's own working:
    the risk tables are a sufficient statistic, so the curve, its area and
    its variance are re-derived from them. The one thing they cannot
    witness — whether censoring was independent of survival — is held to
    reaching the assumption ledger instead."""
    _verify_survival_curve_rule(facts.result)


#: Every ROUTE block and what re-derives it. ``bind_audit`` refuses both
#: halves of the mistake the family exists to prevent: a block with no
#: audit, which reaches a reader on the producer's word, and an audit for
#: something this family does not contain.
_ROUTE_AUDITS = blocks.bind_audit(blocks.Family.ROUTE, {
    blocks.Block.FEEDBACK_LOOP: _audit_feedback_loop,
    blocks.Block.IDENTIFICATION: _audit_identification,
    blocks.Block.IV_IDENTIFICATION: _audit_identification,
    blocks.Block.VECTOR_IV_IDENTIFICATION: _audit_vector_iv_identification,
    blocks.Block.TRANSPORT_IDENTIFICATION: _audit_transport_identification,
    blocks.Block.JOINT_IDENTIFICATION: _audit_joint_identification,
    blocks.Block.LONGITUDINAL_IDENTIFICATION:
        _audit_longitudinal_identification,
    blocks.Block.MEDIATION_DECOMPOSITION: _audit_mediation,
    blocks.Block.MEDIATION_JOINT_DECOMPOSITION: _audit_mediation,
    blocks.Block.PROXIMAL_ESTIMAND: _audit_proximal_estimand,
    blocks.Block.SURVIVAL_CURVE: _audit_survival_curve,
    blocks.Block.SELECTION_RECOVERY: _audit_selection_recovery,
    blocks.Block.MISSING_DATA_RECOVERY: _audit_missing_data_recovery,
})


def _audit_data_gap_surface(result: dict) -> None:
    """The whole of what is an audit of one result's gap surface.

    Two rules, and the reason this has a name is that for eight weeks it
    did not. The T10 pass re-implements the failure and coverage logic
    from scratch; the reconciliation pass re-derives each declared-vs-
    observed verdict from the recorded sufficient statistics and confirms
    the gaps attached to it. Both are audits of the same claim — what this
    run could not answer and why — and a caller asking for one is asking
    for both, which is why the public door runs both. The second was added
    to that door alone, so ``verify`` ran the first and a tampered
    reconciliation block reached a reader having passed the full audit.
    """
    report = result.get("data_gap_report")
    if report is not None:
        from .verifier.data_gap_rules import verify_data_gap_report as _t10
        _t10(
            report,
            derivation=result.get("derivation"),
            investigation_requests=result.get("investigation_requests", []),
            framing_notes=result.get("framing_notes", []),
        )

    from .verifier.type_reconciliation_rules import verify_type_reconciliation
    verify_type_reconciliation(result)


def _audit_refusal_claims(result: dict, facts) -> None:
    """What this run says the program blocks, re-derived from the program.

    Separate from the gap surface above because the two are audits of
    different things by different means: that one asks whether the report
    is consistent with the envelope it sits in, this one asks whether the
    program agrees with what the report says about it. A report can be
    perfectly consistent with an envelope and still describe a graph that
    identifies the estimand it says nothing identifies.
    """
    report = result.get("data_gap_report")
    if report is None:
        return
    from .verifier.refusal_rules import verify_refusal_claims
    verify_refusal_claims(report, facts)


def _audit_selection_recovery_numeric(result: dict) -> None:
    """The recovered ATE, re-run from the recorded stratum counts and the
    external weight tables. Reachable from here only if such a result ever
    carries a derivation — today it does not, and the rule is a no-op on
    everything else, which is the right way to hold a boundary that is a
    fact about the producer rather than about this audit."""
    from .verifier.selection_numeric_rules import (
        verify_selection_recovery_numeric as _rule,
    )
    _rule(result)


def _audit_missing_data_numeric(result: dict) -> None:
    """The same, for the missing-data recovery g-formula."""
    from .verifier.missing_numeric_rules import (
        verify_missing_data_numeric as _rule,
    )
    _rule(result)


#: Every envelope surface ``verify`` owes a rerun, and what performs it.
#: ``bind_rerun`` owns the denominator; the entries are the single copy
#: each surface has, so the public door and the pass inside ``verify``
#: cannot be audits of different things.
_ENVELOPE_SURFACE_AUDITS = audits.bind_rerun({
    "verify_data_gap_report": _audit_data_gap_surface,
    "verify_assumption_ledger": _verify_assumption_ledger_rule,
    "verify_cluster_inference": _verify_cluster_inference_rule,
    "verify_bootstrap_draws": _verify_bootstrap_records_rule,
    "verify_outcome_error": _verify_outcome_error_rule,
    "verify_fingerprints_agree": _verify_fingerprints_rule,
    "verify_one_row_count": _verify_one_row_count_rule,
    "verify_selection_recovery_numeric": _audit_selection_recovery_numeric,
    "verify_missing_data_numeric": _audit_missing_data_numeric,
})


def _audit_ovb_sensitivity(estimate: dict) -> None:
    """The OVB rule is handed the block; every other one is handed the
    estimate around it. Adapted here so the table below can be read as one
    kind of row."""
    verify_ovb_sensitivity(estimate["ovb_sensitivity"])


@dataclass(frozen=True)
class _EstimateAudit:
    """One re-derivation that applies because of what the ESTIMATE says.

    Each selector is a fact written on ``numeric_estimate`` — the method it
    names, or a block it carries. None of them is a fact about which branch
    of the kind dispatch the envelope reached, which is the whole reason
    they are gathered here instead of standing inside one.
    """

    rule: Callable[[dict], None]
    methods: frozenset[str] = field(default_factory=frozenset)
    method_prefixes: frozenset[str] = field(default_factory=frozenset)
    blocks: frozenset[str] = field(default_factory=frozenset)

    def applies(self, estimate: dict) -> bool:
        method = str(estimate.get("method") or "")
        return (method in self.methods
                or any(method.startswith(p) for p in self.method_prefixes)
                or any(estimate.get(b) is not None for b in self.blocks))


#: Every re-derivation the chain audit cannot reach, and what it is an
#: audit OF.
#:
#: They share one shape: a derivation terminal that licenses the structure
#: and audits metadata, beside a number whose sufficient statistics do not
#: fit derivation-input serialization — a confusion matrix, a SIMEX ladder,
#: a set of per-corner risks, a bootstrap-free closed form. So each was
#: added where its author was standing, which was inside the branch that
#: routed the shape they had in hand. Every guard they wrote is a sentence
#: about the estimate and none is a sentence about the branch, and the
#: distance between those two facts is the coverage: a mediation result is
#: ``structurally_solved`` and takes a different branch, so the E-value
#: beside it was never re-derived, and a finding this system called FRAGILE
#: could be relabelled ``very_robust`` and signed. The mediation blocks
#: themselves were found this way once already and fixed by hand-copying
#: the call onto the second branch — a third route would need a third copy,
#: and nothing would say so.
#:
#: A rule appears exactly once, and a test holds that: the table is the
#: single copy, so a call added to a branch is a failure rather than a
#: duplicate nobody can see.
_ESTIMATE_AUDITS: tuple[_EstimateAudit, ...] = (
    # The numbers riding on a mediation structural result — the Imai
    # NDE/NIE split, the two four-way splits, the controlled-direct-effect
    # curve. Their terminal is an identification, so nothing else audits
    # them.
    _EstimateAudit(
        verify_mediation_numeric,
        blocks=frozenset({"decomposition", "four_way_decomposition",
                          "four_way_ratio", "controlled_direct_effect"}),
    ),
    # A Cinelli-Hazlett OVB block: unlike the point estimate (data-refit,
    # metadata audit only), every number in it is a closed form of the
    # fit's t-value and dof.
    _EstimateAudit(_audit_ovb_sensitivity,
                   blocks=frozenset({"ovb_sensitivity"})),
    # A VanderWeele-Ding E-value block: the same, on the risk-ratio scale —
    # a closed form of the audited ATE plus one recorded conversion input.
    _EstimateAudit(verify_e_value,
                   blocks=frozenset({"sensitivity_analysis"})),
    # Over-identified 2SLS (q >= 2 instruments): the Sargan test and the
    # point, re-derived from the recorded residualised moment matrices.
    _EstimateAudit(verify_iv_overid_numeric,
                   methods=frozenset({"iv_2sls_overid"})),
    # An IV number over an ordered dose carries the margin table that says
    # which steps it averages over; re-derived from the recorded
    # per-instrument-level counts and sums.
    _EstimateAudit(verify_acr_decomposition, methods=frozenset({"iv_acr"})),
    # A front door whose mediator conditional came from the arms' own rows:
    # the point is re-derived from the two standardized arms, and on the
    # linear form from the coefficients and the mediator shift. Keyed on the
    # family rather than on its members, so a third form of the same route
    # arrives audited.
    _EstimateAudit(verify_frontdoor_empirical_numeric,
                   method_prefixes=frozenset({"frontdoor_empirical"})),
    # A joint contrast and its K-way interaction, re-derived as finite
    # differences over the recorded treatment box. Keyed on the box: both
    # joint routes emit this block, and which of them had its numbers
    # re-derived used to be which of them remembered to keep its corners.
    _EstimateAudit(verify_treatment_box,
                   blocks=frozenset({"corner_risks"})),
    # Outcome misclassification: the confusion-matrix inversion and the
    # corrected/naive point, from the recorded matrix + per-stratum
    # value-count vectors.
    _EstimateAudit(verify_measurement_correction_numeric,
                   methods=frozenset({"measurement_error_correction"})),
    # Exposure misclassification — the matrix method inverts the channel on
    # the exposure margin of the (X, Y) joint.
    _EstimateAudit(verify_exposure_measurement_correction_numeric,
                   methods=frozenset({"exposure_measurement_error_correction"})),
    # Both channels misclassified — the joint is inverted on both sides at
    # once, from the two recorded matrices and the same joint tables.
    _EstimateAudit(verify_combined_measurement_correction_numeric,
                   methods=frozenset({"combined_measurement_error_correction"})),
    # Continuous mismeasurement: the de-attenuated slope, from the recorded
    # design covariance matrix + Cov((W,Z),Y) + sigma^2_u.
    _EstimateAudit(verify_regression_calibration_numeric,
                   methods=frozenset({"regression_calibration"})),
    # The same mismeasurement on a declared nonlinear outcome model: the
    # extrapolation, from the recorded simulation ladder.
    _EstimateAudit(verify_simex_numeric, methods=frozenset({"simex"})),
    # The same with the non-differential premise withdrawn: a producer that
    # un-inflated the variance and not the covariance returns a number every
    # reliability ratio a reader checks by hand agrees with.
    _EstimateAudit(verify_differential_error_numeric,
                   methods=frozenset({"differential_regression_calibration"})),
    # The other channel, where the whole correction is one subtraction —
    # skip it and the answer is the ordinary back-door slope, which nothing
    # else in the block disagrees with.
    _EstimateAudit(verify_differential_outcome_error_numeric,
                   methods=frozenset({"differential_outcome_correction"})),
    # A dose-response curve array: the metadata audit sees only the
    # headline scalar, so the curve's construction invariants are held here.
    _EstimateAudit(verify_dose_response_curve,
                   blocks=frozenset({"dose_response_curve"})),
    # A longitudinal g-formula / IPW-MSM estimate rides on an
    # identify_via_gformula terminal: the MSM contrast is re-derived from
    # the recorded coefficients and the g-formula's identities checked.
    _EstimateAudit(verify_longitudinal_numeric,
                   blocks=frozenset({"longitudinal_ipw_msm",
                                     "longitudinal_gformula"})),
)


def _audit_estimate_blocks(result: dict) -> None:
    """Run every re-derivation this estimate calls for, whatever route the
    envelope took to get here."""
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    for row in _ESTIMATE_AUDITS:
        if row.applies(estimate):
            row.rule(estimate)


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
    BUNDLE_VERSION,
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
            ext[blocks.Block.LLM_PROPOSED_REVIEW] = review
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
            rd.setdefault("extensions", {})[blocks.Block.ASSUMPTION_LEDGER] = ledger
    for rd in result_dicts:
        blocks.check_registered(rd)
        refusals.stamp(rd)
    return {"results": result_dicts}


# ---------------------------------------------------------- Program -> AST

def _term_to_dict(t: Term) -> dict:
    if isinstance(t, ConstTerm):
        return {"type": "const", "name": t.name}
    if isinstance(t, VarTerm):
        return {"type": "var", "name": t.name}
    raise TypeError(f"unknown term: {type(t).__name__}")


def _atom_to_dict(a: Atom) -> dict:
    d: dict[str, object] = {
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
        # What the question is about, beyond X and Y. A mediator names the
        # path the question asks along; a target population names where the
        # answer is for. Both were read by the parser and unwritten here,
        # so the merged program handed back for auditing asked something
        # else than the program that was answered: a mediation question
        # came back a total-effect question, and a transported one came
        # back a one-population question the transported estimand then
        # disagreed with.
        if q.mediator is not None:
            d["mediator"] = _atom_to_dict(q.mediator)
        if q.mediators:
            d["mediators"] = [_atom_to_dict(a) for a in q.mediators]
        if q.target_population is not None:
            d["target_population"] = q.target_population
        # Serialize the first-class assumptions field if set.
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
        d = {
            "kind": "identify",
            "target": _atom_to_dict(q.target),
            "intervention": _intervention_to_dict(q.intervention),
            "given": [_atom_to_dict(a) for a in q.given],
        }
        if q.target_population is not None:
            d["target_population"] = q.target_population
        return d
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
        # The two experimental risks a counterfactual question may supply
        # itself: without them the re-parsed question has to be answered
        # from theta alone, which is a different question.
        if q.experimental_risk_treated is not None:
            d["experimental_risk_treated"] = q.experimental_risk_treated
        if q.experimental_risk_control is not None:
            d["experimental_risk_control"] = q.experimental_risk_control
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
        out = {
            "kind": "proximal_effect",
            "treatment": _atom_to_dict(q.treatment),
            "outcome": _atom_to_dict(q.outcome),
            "latent": _atom_to_dict(q.latent),
            "treatment_proxy": [_atom_to_dict(a) for a in q.treatment_proxy],
            "outcome_proxy": [_atom_to_dict(a) for a in q.outcome_proxy],
            "channel": _proximal_channel_to_dict(q.channel),
        }
        if q.covariates:
            out["covariates"] = [_atom_to_dict(a) for a in q.covariates]
        return out
    raise TypeError(f"unknown query: {type(q).__name__}")


def _proximal_channel_to_dict(channel) -> dict:
    """The channel, back in the shape the AST holds it.

    The round trip's half of the union: this and
    ``semantic_validator._to_proximal_channel`` are the two directions of one
    mapping, and a program that goes out of here has to come back in as the
    same query or the schema is describing something nobody writes.
    """
    from .types import BridgeChannel

    if isinstance(channel, BridgeChannel):
        out: dict = {
            "kind": "bridge_channel",
            "estimator": str(channel.estimator),
            "outcome_bridge": _bridge_to_dict(channel.outcome_bridge),
        }
        if channel.treatment_bridge is not None:
            out["treatment_bridge"] = _bridge_to_dict(channel.treatment_bridge)
        return out
    out = {
        "kind": "discrete_channel",
        "latent_cardinality": channel.latent_cardinality,
    }
    if channel.proxy_coarsening is not None:
        out["proxy_coarsening"] = {
            "treatment_proxy": [
                list(g) for g in channel.proxy_coarsening.treatment_proxy],
            "outcome_proxy": [
                list(g) for g in channel.proxy_coarsening.outcome_proxy],
        }
    return out


def _bridge_to_dict(bridge) -> dict:
    """One bridge, back in the shape the AST holds it."""
    out: dict = {
        "span_terms": _sieve_terms_to_list(bridge.span_terms),
        "moment_terms": _sieve_terms_to_list(bridge.moment_terms),
    }
    if bridge.ridge is not None:
        out["ridge"] = bridge.ridge
    return out


def _sieve_terms_to_list(terms) -> list:
    """One side of a sieve design, back in the shape the AST holds it."""
    return [
        {"factors": [
            {
                "variable": _atom_to_dict(f.variable),
                "basis": str(f.basis),
                "dimension": f.dimension,
            }
            for f in term.factors
        ]}
        for term in terms
    ]


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
    if isinstance(s, (BidirectedStatement, FeedbackLoop)):
        d = {
            "kind": ("bidirected" if isinstance(s, BidirectedStatement)
                     else "feedback"),
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
        if s.defaulted:
            d["defaulted"] = list(s.defaulted)
        if s.censoring is not None:
            d["censoring"] = {
                "event_indicator": s.censoring.event_indicator,
                **({} if s.censoring.horizon is None
                   else {"horizon": s.censoring.horizon}),
            }
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
    exact program the kernel computed on — not the pre-patch input.

    Which makes the whole point of this function a round trip: the
    document it writes must parse to the program it was written from, or
    the caller audits an answer against a question nobody asked. It is a
    second writer of a document the parser owns, and a second writer
    learns a field late or never — six of them, across three query kinds,
    had never been written here, so a mediation question came back a
    total-effect question and a transported one came back a
    one-population question. Every feature that added a field had a
    wiring test for its own field; the general question was asked by
    none of them, and is asked now by
    ``test_the_program_handed_back_is_the_one_that_was_answered``.
    """
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


def _leaving(out: dict) -> dict:
    """Every envelope this module hands out, held to this module's contract.

    The input half of that contract has always been checked here, at the
    door, by :func:`validate_ast`. The output half was stated in the same
    breath — "``results[*]`` conforms to ``query_result.schema.json``" —
    and then left to whoever remembered to call :func:`validate_result`,
    which is the verifier's entry and not this one. So the promise was
    kept by the tests that happened to ask for it, and the ones that did
    not were the denominator.

    What that cost, measured over the whole suite before this existed:
    four shapes reaching public envelopes that the schema forbids. The
    caller's ``model`` string as typed rather than as understood; a block
    with three readers that the contract had never heard of; a sentence
    inside a closed object; and — the one that made this visible — a
    field removed from the report a commit earlier, still written by the
    one road that hand-built the report's key set.

    ``extensions`` had a registry check at the two exits and top-level
    keys had nothing, which is why three of the four were top-level.
    """
    for entry in out.get("results") or ():
        validate_result(entry)
    return out


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
    return _leaving(out)


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
    return _leaving(estimate_program(program, data, **options))


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
    return _leaving(out)


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
    ``MalformedBundleError`` for a version it never meant to state.
    Hand-built bundles still work; this only widens the input grammar.

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
                "version": BUNDLE_VERSION,
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
    ``causation_probability_bounds`` step) that
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
        # Both absent is agreement, not a mismatch. The instrument route
        # point-identifies no interventional risk and reports neither, so a
        # comparison that only ever succeeds on two numbers would reject the
        # one route whose answer is that there are none.
        if a is None and b is None:
            return True
        return a is not None and b is not None and abs(float(a) - float(b)) <= tol

    def _fail() -> NoReturn:
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
        # The value, not the presence. Both sides always carry the key now —
        # ``validate_result`` above rejects a quantity that does not — so the
        # question left is the one the numeric twin of this function has
        # always asked: do the two numbers agree, with "no point on either
        # side" counting as agreement.
        if not _num_eq(a.get("point"), b.get("point")):
            _fail()
    for k in ("p_y_do_x1", "p_y_do_x0"):
        if not _num_eq(ext.get(k), env.get(k)):
            _fail()
    if bool(ext.get("monotonic")) != bool(env.get("monotonic")):
        _fail()
    for k in ("interventional_risk_provenance", "instrument"):
        if str(ext.get(k)) != str(env.get(k)):
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
    numeric_estimate, not the extension). Skips quietly when absent.

    A copy needs the thing it copies, and which envelopes carry one is a
    fact about the envelope rather than about the route that produced it.
    On the structural path this block is not a copy of a number — it IS the
    answer, and no point stands beside it to agree with. While the rule was
    called from inside the data branch, the branch said that for it; asked
    of every answer, it says so itself."""
    ext = (result.get("extensions") or {}).get("scm_counterfactual")
    if ext is None:
        return
    num_est = result.get("numeric_estimate")
    if num_est is None:
        return
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
        # Absent on BOTH sides is agreement, and the reason it has to be said
        # is that absence is now an answer: a point exists only where the route
        # produces one, and the instrument route produces no do-risks at all.
        if a is None or b is None:
            return a is None and b is None
        return abs(float(a) - float(b)) <= tol

    def _fail() -> NoReturn:
        raise VerificationError(
            "extensions.causation does not match the verified numeric "
            "derivation inputs (display copy diverges from the audited answer)",
            step_index=len(derivation) - 1, rule=derivation[-1].rule,
        )

    for q in ("pn", "ps", "pns"):
        a = ext.get(q)
        if not isinstance(a, dict):
            _fail()
        for field in ("lower", "upper", "point"):
            if not _num_eq(a.get(field), inp.get(f"{q}_{field}")):
                _fail()
    for k in ("p_y_do_x1", "p_y_do_x0"):
        if not _num_eq(ext.get(k), inp.get(k)):
            _fail()
    if bool(ext.get("monotonic")) != bool(inp.get("monotonic")):
        _fail()
    for k in ("interventional_risk_provenance", "instrument"):
        if ext.get(k) != inp.get(k):
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

    def _fail() -> NoReturn:
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
    for k in ("interventional_risk_provenance", "instrument"):
        if ext.get(k) != inp.get(k):
            _fail()
    joint = ext.get("observational_joint") or {}
    for k in ("p_x1_y1", "p_x1_y0", "p_x0_y1", "p_x0_y0"):
        if not _num_eq(joint.get(k), inp.get(k)):
            _fail()


def _premises_of(program: dict | str | bytes, result: dict):
    """Everything an answer is checked against, re-derived from the ASKED
    side: the caller's own document, the program parsed out of it, the
    query this result says it answers, and the context projected from all
    three.

    Not one field of it comes from a derivation. That is the fact the two
    halves of :func:`verify` are split on, and it is why this is a function
    rather than a stretch of that one.
    """
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
    from .runtime.structural_solver import (
        bidirected_from_ground, feedback_from_ground,
    )
    bidirected = bidirected_from_ground(ground)
    # #450: the declared reciprocal loops, read from the PROGRAM. The rule
    # that consumes them holds the derivation's claim to this, so a step
    # cannot vouch for the loop that licensed it.
    feedback = feedback_from_ground(ground)

    target_id = result.get("query_id")
    if target_id is None:
        raise ValueError(
            "auditing a result requires its query_id to locate the "
            "matching query in the program"
        )
    query_stmt = None
    for s in prog.statements:
        if isinstance(s, QueryStatement) and s.id == target_id:
            query_stmt = s
            break
    if query_stmt is None:
        raise ValueError(
            f"no query with id={target_id!r} in the program"
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

    ctx = VerificationContext(
        graph=graph,
        query=query_stmt.query,
        theta=theta,
        bidirected=bidirected,
        feedback=feedback,
        selection_nodes=selection_nodes,
        observations=scm_observations or None,
    )
    return ast, prog, query_stmt, ctx


def _hold_what_the_answer_says(result: dict, ast: dict, prog, ctx) -> None:
    """Every claim on the envelope that is not the conclusion itself.

    An answer says more than what it concluded. It names an estimand, it
    reports which route it took, it says what data is missing and what a
    reader should go and supply, it discloses the shape it fitted and
    copies back what the caller told it. None of that is re-derived from
    the reasoning chain — all of it is re-derived from the program and the
    question — and each of these audits already says so in its own words,
    "a fact about the ANSWER, not about the route".

    They were written into :func:`verify` below the precondition that
    belongs to the chain half, so the answer whose whole content is these
    claims — a gap diagnosis, which takes no route and therefore has no
    chain — was the one answer none of them was ever asked about. The
    classification existed in the prose and not in the structure.
    """
    target_id = result.get("query_id")

    # An effect result over a treatment VECTOR may carry an Anderson-Rubin
    # confidence region. Its derivation terminal
    # (numeric_anderson_rubin_region) does metadata + structural licensing
    # only — the inversion, the shape and every coordinate projection are
    # re-derived here from the recorded second moments, which are matrices and
    # do not fit the derivation-input serialization. Unconditional on status:
    # an unbounded region is attached beside a structural refusal. Not a ROUTE
    # block: it is the ANSWER, and the route block naming the variables it was
    # built from is audited by the table below.
    _ar_region = (result.get("extensions") or {}).get("anderson_rubin_region")
    if _ar_region is not None:
        verify_vector_iv_region(_ar_region)

    # The estimand a reader is shown, against the graph and the question it
    # claims to be for. Outside the query-kind dispatch for the reason the
    # route audits are: whether a formula reached a reader is a fact about
    # the envelope, not about which branch produced it. The probe that
    # answers this has existed since Phase 15 and was reachable from the
    # identify branch alone — where it reads the formula out of the
    # derivation, which an effect answer's chain does not carry. So on
    # twenty-three answers the estimand could be deleted outright.
    verify_identification_formula(result, ctx)

    # What a gap SAYS, against the problem it says it about. The three
    # audits in data_gap_rules read the report's skeleton and none of them
    # descends into a gap's contents, so every one of 462 `said` leaves
    # could be rewritten. Here for the same reason as the line above: a
    # gap report is a fact about the answer, not about the route.
    verify_gap_names(result, ctx)

    # And WHICH of those names. The rule above asks whether a gap's
    # words are words this problem is written in; a forgery swapping
    # one real variable for another passes it. The gap's own
    # provenance says which one it is about, and T10-1 already holds
    # that ref — the two had never been joined.
    verify_gap_subjects(result, ast)

    # What a disclosed mechanism was fitted FOR. Every other mechanism
    # check is reached through verify_assumption_ledger(result), which has
    # no program beside it, and the target's only authority is the
    # question — so the check could not be written there and was declared
    # uncheckable instead. Here it is one line, for the same reason as the
    # two above: what a block says is a fact about the answer.
    verify_mechanism_target(result, ctx)

    # What the reader is told to go and supply. The two rules that touch
    # investigation_requests use it as a denominator — gap provenance
    # resolves against its targets, and each item must be cited — so
    # nothing ever read an item, and the second turn takes its skeleton
    # verbatim as the patch. Takes the PROGRAM rather than the context:
    # the patch's fields are answerable only against what the program
    # declares, which is the one side an answer cannot edit.
    verify_investigation_items(result, prog)

    # Every ROUTE block, re-derived. The family is the repo's own name for
    # the blocks that say where a number came from, and the binding is what
    # makes coverage of it a fact rather than a habit: a block added without
    # an audit is an ImportError here, exactly as a block added without a
    # renderer already is in the report. Unconditional on status throughout —
    # a structural claim does not depend on a number coming back — and each
    # audit owns the presence check for the block(s) it names, so absence is
    # answered in one place per claim rather than at the call site.
    #
    # Here rather than after the chain because a route block says which
    # route was taken, which is re-derived from the graph: these audits
    # never read a step, and an answer that took no route still claims one
    # or claims none.
    _route_facts = _RouteFacts(
        result=result, graph=ctx.graph, bidirected=ctx.bidirected,
        query=ctx.query, program=prog, feedback=ctx.feedback)
    for _audit in dict.fromkeys(_ROUTE_AUDITS.values()):
        _audit(_route_facts)

    # An answered result can still carry a gap list, and a gap saying the
    # program identifies nothing sits oddly beside a chain that identified
    # something. The narrow door reruns this from the program; the full door
    # holds the program too, so not running it here would make ``verify`` the
    # weaker of the two on a claim both can reach.
    from .verifier.refusal_rules import RefusalFacts as _RefusalFacts
    _audit_refusal_claims(result, _RefusalFacts(
        graph=ctx.graph, bidirected=ctx.bidirected, query=ctx.query,
        feedback=ctx.feedback, selection_nodes=ctx.selection_nodes))

    # The two blocks that are not conclusions but copies of what the
    # caller said, held against the caller's own document. Outside the
    # table above because they are outside that family and because the
    # premise they are re-derived from is the program JSON rather than
    # the graph projected out of it — reading what was submitted is what
    # lets a serialisation that dropped an annotation be seen at all.
    verify_llm_proposed_review(
        (result.get("extensions") or {}).get("llm_proposed_review"), ast)
    verify_ambiguity_copy(
        (result.get("extensions") or {}).get("ambiguities"), ast,
        query_id=target_id)


def verify_answer_claims(program: dict | str | bytes, result: dict) -> None:
    """Audit what an answer SAYS, without asking for the chain.

    :func:`verify` is the strong door and requires a derivation, because
    re-running a conclusion means re-running the reasoning that reached
    it. But an answer says more than its conclusion, and an answer may
    have nothing BUT the rest: a data-gap diagnosis took no route, so it
    has no chain, and the report it hands a reader is its entire content.
    Behind the strong door that content was unreadable — not refused on
    the merits, refused before being read.

    So this is the same audits, at a door that asks only for the program:
    the estimand, every route block, the gap report's contents, the list a
    reader is told to fill, the mechanism's target, the refusal claims, and
    the caller's own words copied back.

    And everything held to the estimate, which is the half this door was
    first built without. An answer with no chain is not an answer with no
    number: the missing-data recovery path attaches a point, an interval
    and every block written beside them, and returns without a derivation.
    Behind this door those went unread — the level the interval covers at,
    the arithmetic the envelope worked out from its own figures, what each
    block says it is about. They are held now, by the phase that holds them
    in :func:`verify`, told there is no record for the one member of it
    that needs one.

    Raises ``VerificationError`` on any mismatch, ``ValueError`` if the
    result names no query this program has. Returns ``None`` on accept.
    It is not the weaker half of :func:`verify` — it is the half that has
    a different premise, and every answer has that premise.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    ast, prog, query_stmt, ctx = _premises_of(program, result)
    _hold_what_the_answer_says(result, ast, prog, ctx)
    _hold_what_the_estimate_calls_for(result, ast, query_stmt, record=None)


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

    Two halves, and only the second needs the chain. What the answer SAYS
    — its estimand, its route blocks, its gap report, its reader's list —
    is held by :func:`verify_answer_claims`, which is a door of its own
    because an answer may consist of nothing else. What the answer
    CONCLUDED is held below, and that is what the derivation is for.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")

    # Shape-check the result payload so we fail early on malformed
    # derivations rather than deep inside the verifier.
    validate_result(result)

    ast, prog, query_stmt, ctx = _premises_of(program, result)
    _hold_what_the_answer_says(result, ast, prog, ctx)

    derivation_json = result.get("derivation")
    if derivation_json is None:
        raise ValueError(
            "verify() requires a result with a derivation; this result "
            "has none (external agents cannot audit an answer without "
            "its reasoning chain). What it SAYS can still be audited: "
            "verify_answer_claims() takes the same two arguments and asks "
            "for no chain"
        )
    derivation = derivation_from_dict(derivation_json)

    # The names the chain half is written against. Every one of them was
    # re-derived from the program above, and the context is where they are
    # kept, so this is a reading and not a second derivation.
    target_id = result.get("query_id")
    graph, bidirected = ctx.graph, ctx.bidirected
    feedback, selection_nodes = ctx.feedback, ctx.selection_nodes

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
            kind == "effect"
            and bool(derivation)
            and derivation[-1].rule == "numeric_anderson_rubin_region"
        ):
            # The answer is a REGION over a coefficient vector. Routed on the
            # derivation's TERMINAL and not on a field, because the two fields
            # the branches below key on — numeric_estimate and numeric_result
            # — each mean "the answer is one number", and this answer is k
            # conservative intervals with no point among them. The terminal
            # audits metadata + structural licensing; the region itself was
            # re-derived from the recorded moments above.
            claimed = _decode_structural_result_json(result["structural_result"])
            verify_numeric_estimate(derivation, ctx, claimed)
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
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    f"verify(): {kind} result must carry a numeric_result"
                )
            claimed_numeric = _decode_numeric_result_json(
                result["numeric_result"]
            )
            verify_numeric(derivation, ctx, claimed_numeric)
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
            claimed_numeric = _decode_numeric_result_json(
                result["numeric_result"]
            )
            verify_counterfactual(derivation, ctx, claimed_numeric)
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
            claimed_numeric = _decode_numeric_result_json(
                result["numeric_result"]
            )
            verify_causation(derivation, ctx, claimed_numeric)
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
            # Membership was the branch condition, so index rather than
            # ``.get`` — the verifier takes the block itself, not an absence.
            num_est = result["numeric_estimate"]
            verify_scm_counterfactual_numeric(derivation, ctx, claimed, num_est)
        else:
            if "numeric_result" not in result:
                raise ValueError(
                    "verify(): scm_counterfactual result must carry a numeric_result"
                )
            claimed_numeric = _decode_numeric_result_json(
                result["numeric_result"]
            )
            verify_scm_counterfactual(derivation, ctx, claimed_numeric)
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

    # And what is held to the estimate itself, in the order that puts a
    # re-derivation ahead of anything held to it. A phase of its own,
    # because only one member of it reads the chain.
    _hold_what_the_estimate_calls_for(
        result, ast, query_stmt, record=derivation_json)


def _hold_what_the_estimate_calls_for(
    result: dict, ast: dict, query_stmt, *, record,
) -> None:
    """The claims a record speaks to first, and the order that says so.

    :func:`_hold_what_the_answer_says` holds the claims a chain has nothing
    to say about, and holds them before any route rule runs. These are the
    other kind: a number the envelope shows, the labels beside it, the
    level it is stated at, the surfaces standing next to it. Where a chain
    exists it speaks to some of them, and where both can speak the one
    re-deriving the record speaks first — which is why this phase runs
    after the route dispatch rather than beside the phase above. The order
    inside it is unchanged and is the meaning: a number is re-derived
    before anything is held to it.

    Membership is decided by what each audit is HANDED. An audit whose
    arguments name nothing that came from the derivation is asking about
    the ANSWER, and an answer may arrive with no chain at all — a data-gap
    diagnosis takes no route, and neither does a recovered ATE, which
    reaches a reader with a number, an interval, and every block written
    beside it. Ten families sat here reading only the envelope, the program
    and the question, and none of them could be put to such an answer. The
    partition was already in the prose — each of these says in its own
    words that it audits a block rather than a route — and the earlier
    sweep moved the ones it could name rather than the ones the calls
    declare.

    ``record`` is the submitted derivation JSON, or ``None`` when the
    answer carries none. Exactly one member of this phase needs it — the
    copy check, which holds the reader's number against the step it was
    re-derived from — and on a chainless answer there is no second copy to
    hold anything to, so that one is skipped and the other nine are not.
    """
    target_id = result.get("query_id")
    # Every re-derivation the estimate itself calls for. Outside the route
    # dispatch and not inside one of its branches: what each of them is an
    # audit of is a block or a method, both written on the estimate, and an
    # envelope that carries the block carries it whichever way it was
    # routed here. Ahead of the checks below for the reason they are
    # ordered among themselves — a number is re-derived before anything is
    # held to it.
    _audit_estimate_blocks(result)

    # The copy of the run's own record: what a reader is shown as the
    # number, against the step the rules above re-derived it from. After
    # them and not before, because the order is the meaning — the record
    # is audited first, and only then is the reader's copy held to an
    # audited record. Ahead of them this check would answer for a tampered
    # derivation before the rule that re-derives it ever ran, and the
    # rules would go unexercised at the public door. Read off the
    # submitted JSON rather than the decoded chain, so a serialisation
    # that lost a field is visible here.
    if record is not None:
        verify_numeric_display_agrees(result, record)
    # The other display copy, and the same sentence about it. A
    # counterfactual answer shows a reader the value under
    # ``extensions.scm_counterfactual``, and the rule that audits the number
    # audits ``numeric_estimate`` — so a tamper of the copy alone passes it.
    # It stood inside that route's branch, where the copy was treated as a
    # fact about how this answer was produced; it is a fact about what the
    # envelope shows, and it skips quietly where the block is absent.
    _verify_scm_counterfactual_extensions_match(result)
    # And the variables that answer names, against the question rather than
    # the record — they come from the query, so no step records them and
    # the check above cannot reach them. After it for the same reason it
    # runs after the rules: where both can speak, the one holding the copy
    # to an audited record speaks first, and this one answers for what that
    # record never carried.
    verify_answer_names_its_question(
        result.get("numeric_estimate"), ast, query_id=target_id)
    # And the figures the envelope worked out from its own figures. Neither
    # a copy nor an estimate: an identity, whose every input is already on
    # the envelope. Nothing records the sums somebody took after the
    # estimator finished, so the two checks above have nothing to hold them
    # against and this is where they are held.
    verify_envelope_arithmetic(result)
    # And the level every one of those intervals is stated at, which is the
    # other half of what a pair of endpoints means and the half no identity
    # reaches: a percentile bootstrap keeps no multiplier to invert it back
    # out of. A line this system draws rather than one a caller may draw, so
    # it is held to the constant, restated on the verifier's side.
    verify_confidence_level(result)
    # And the one answer whose own chain records no estimation at all. The
    # transport route ends its derivation at the identification and attaches
    # a number beside it, so the copy check above found no second copy and
    # said nothing — which at a door is indistinguishable from finding
    # nothing wrong. Re-derived here from the strata it is a sum over.
    verify_post_stratification(result)

    # And the blocks that are not the answer but the evidence a reader
    # weighs it with. The ledger reads its positivity verdict off the fitted
    # overlap, deliberately re-reading the estimate's own numbers so the
    # verdict is a disclosure rather than a claim — which only works while
    # those numbers can themselves be re-derived. Held here to the
    # arithmetic every fitted range obeys whatever model produced it.
    verify_fitted_diagnostics(result)

    # And what each block says it is ABOUT. The audits above re-derive a
    # number FROM the labels beside it — which columns, which states, which
    # value the risk is of, which level the mediators were held at — so to
    # them a label is an input, and an input cannot be wrong: change one and
    # the arithmetic re-derives a number consistent with itself in every
    # place, answering a question nobody asked. Last of the group because it
    # is the only one that needs the program: half of what a label claims is
    # a claim about the question, and the question is not on the envelope.
    verify_frame(result, ast, query_id=target_id)

    # Every surface standing beside the answer whose failure mode is
    # one-sided — under-disclosure reads exactly like nothing to disclose,
    # so a caller who called only this function would never learn of it.
    # Through the table rather than by hand, because what a hand-copied
    # list copies is a rule and what it is a copy OF is a door: a door is
    # free to grow a second rule and the copy does not grow with it.
    for _surface in dict.fromkeys(_ENVELOPE_SURFACE_AUDITS.values()):
        _surface(result)

    # The exposure channel's other structure, where the block's strong
    # claim is that the number beside it needed no correcting at all. The
    # arithmetic is re-derivable and is re-derived; what cannot be checked
    # by any arithmetic — that the error is Berkson and not classical, the
    # one fact separating a right answer from one attenuated by half — is
    # held to reaching the assumption ledger, where a reader can disagree.
    # Outside the table because it is outside the family: no public door
    # audits it alone, so this call is its only caller and there is no
    # second copy to diverge from.
    _verify_berkson_error_rule(result)

    # Independent audit of every bounds row. Each producer has a dedicated
    # verifier; the trilogy is complete for the 3 implemented BoundsMethod
    # values. Every row is audited — the rows are different methods on one
    # estimand, and auditing one of them says nothing about the others.
    for row in result.get("bounds_results") or ():
        _verify_one_bounds_row(
            row, ast=ast, query_dict=_query_to_dict(query_stmt.query),
            strict=False,
        )


def _verify_one_bounds_row(row: dict, *, ast, query_dict, strict: bool) -> None:
    """Route one bounds row to the verifier for its method.

    ``strict`` is what separates the two entrances. The pass inside
    :func:`verify` walks whatever the kernel produced, so a method with no
    verifier yet is not its business; the public entry is a request to
    audit this row, and answering it with silence would read as an accept.
    """
    # What the row TELLS a reader, asked of every method before the
    # dispatch that knows which one this is: `data_required` and `notes`
    # are the same two lists on all three, and the module below verifies
    # the interval rather than the account of it.
    from .verifier.bounds_account_rules import verify_bounds_account
    verify_bounds_account(row, program=ast, query_dict=query_dict)

    method = row.get("method")
    if method == "manski_natural":
        from .verifier.bounds_rules import verify_manski_natural_bounds_result
        verify_manski_natural_bounds_result(row, query_dict=query_dict)
    elif method == "manski_tamer_monotonicity":
        from .verifier.bounds_rules import verify_manski_tamer_bounds_result
        verify_manski_tamer_bounds_result(
            row, program=ast, query_dict=query_dict,
        )
    elif method == "balke_pearl_iv":
        from .verifier.bounds_rules import verify_balke_pearl_iv_bounds_result
        verify_balke_pearl_iv_bounds_result(
            row, program=ast, query_dict=query_dict,
        )
    elif not strict:
        return
    elif method == "frontdoor_partial":
        raise ValueError(
            "frontdoor_partial bounds verifier is not yet implemented "
            "(no producer either — aspirational BoundsMethod enum value)"
        )
    else:
        raise ValueError(
            f"verify_bounds_results(): unsupported bounds method {method!r}"
        )


def verify_bounds_results(program: dict | str | bytes, result: dict) -> None:
    """Independently audit every row of ``result.bounds_results``.

    Public entry parallel to :func:`verify_data_gap_report`. Unlike
    :func:`verify`, this function does NOT require a derivation chain
    on the result — bounds typically attach when point identification
    fails (status=needs_investigation) and no derivation chain exists,
    so the existing verify() path is dormant for exactly the results
    that carry bounds.

    The block is a SET: one row per method whose assumptions the program
    supports, all bracketing the same estimand. Every row is dispatched by
    its own ``method`` to the dedicated verifier (manski_natural /
    manski_tamer_monotonicity / balke_pearl_iv), because auditing one of
    them says nothing about the arithmetic of another.

    Raises :class:`themis.verifier.errors.VerificationError` on any
    mismatch (canonical-shape tampering, wrong assumption tags,
    missing monotonicity declaration, etc.). Returns ``None`` on
    accept. Raises ``ValueError`` for missing bounds_results, missing
    query_id, or an unsupported method on any row.

    The frontdoor_partial method has no producer yet (aspirational
    enum value); calling this function on an emitted
    frontdoor_partial row raises ``ValueError`` until that
    verifier lands.
    """
    if not isinstance(result, dict):
        raise TypeError(
            f"result must be a dict; got {type(result).__name__}"
        )
    validate_result(result)

    bounds_results = result.get("bounds_results")
    if not bounds_results:
        raise ValueError(
            "verify_bounds_results() requires result.bounds_results; this "
            "result has none. Use themis.verify() for non-bounds results."
        )

    target_id = result.get("query_id")
    if target_id is None:
        raise ValueError(
            "verify_bounds_results() requires result.query_id to locate "
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
            f"verify_bounds_results(): no query with id={target_id!r} "
            "in the program"
        )

    query_dict = _query_to_dict(query_stmt.query)
    for row in bounds_results:
        _verify_one_bounds_row(row, ast=ast, query_dict=query_dict, strict=True)


def verify_data_gap_report(result: dict) -> None:
    """Independently audit what one result says it could not answer.

    Two passes, both audits of the same claim: the T10 pass re-implements
    the failure and coverage logic of the report from scratch, and the
    2026-07-11 pre-flight diagnostic re-derives every
    ``declared_type_data_mismatch`` verdict from the recorded sufficient
    statistics and confirms the gaps attached to it.

    This is the public counterpart to :func:`verify`, which runs the same
    audit through the same object. It is deliberately result-only: gap
    reports cite the result envelope's derivation / investigation requests
    / framing notes, not the source program graph. It also accepts results
    with no derivation, which is necessary for advisory outputs such as
    Phase 13 dose-response data requirements — and is why it is a door of
    its own rather than only a pass inside ``verify``.

    Returns ``None`` on accept. Raises ``VerificationError`` or
    ``SyntacticError`` on malformed or inconsistent reports.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _ENVELOPE_SURFACE_AUDITS["verify_data_gap_report"](result)


def _refusal_facts(program: dict | str | bytes, target_id):
    """The program's own account of itself, for a result that has no chain.

    The same reconstruction ``verify`` performs, reached without it: a
    refusal carries no derivation, and requiring one is what left this
    whole class of answer with no door that had ever seen the program.
    """
    from .runtime.structural_solver import (
        bidirected_from_ground, feedback_from_ground,
    )
    from .types import SelectionNode as _SN
    from .verifier.refusal_rules import RefusalFacts

    ast = validate_ast(_to_ast(program))
    prog = validate_program(ast)
    ground = instantiate(prog)

    query_stmt = None
    for s in prog.statements:
        if isinstance(s, QueryStatement) and s.id == target_id:
            query_stmt = s
            break
    if query_stmt is None:
        raise ValueError(
            f"verify_refusal(): no query with id={target_id!r} in the program"
        )
    return RefusalFacts(
        graph=project(ground),
        bidirected=bidirected_from_ground(ground),
        query=query_stmt.query,
        feedback=feedback_from_ground(ground),
        selection_nodes=tuple(
            s for s in prog.statements if isinstance(s, _SN)),
    )


def verify_refusal(program: dict | str | bytes, result: dict) -> None:
    """Independently re-derive what one result says its program blocks.

    The counterpart to :func:`verify` for the answers that are not
    answers. ``verify`` requires a derivation and refuses without one,
    which is right for a number and wrong for a refusal: a refusal's
    content is a claim about the graph, and the graph is in the caller's
    hands. This is the door that takes it — parallel to
    :func:`verify_bounds_results`, which exists for the same reason, since
    bounds also attach exactly where point identification failed and no
    chain exists.

    A falsifier. It raises when the program contradicts a gap — when an
    adjustment set or a front-door route exists for an estimand the report
    says nothing identifies — and returns ``None`` otherwise. Returning
    ``None`` is not a certificate that the refusal is sound; proving
    non-identifiability is the producer's work, and where it did that work
    the proof is a hedge witness in a derivation that :func:`verify` reads.

    Raises ``VerificationError`` when a claim is refuted, ``ValueError``
    for a missing gap report or a query id absent from the program.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)

    if result.get("data_gap_report") is None:
        raise ValueError(
            "verify_refusal() requires result.data_gap_report; this result "
            "makes no claim about what its program could not answer"
        )
    target_id = result.get("query_id")
    if target_id is None:
        raise ValueError(
            "verify_refusal() requires result.query_id to locate the "
            "matching query in the program"
        )
    _audit_refusal_claims(result, _refusal_facts(program, target_id))


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
    _ENVELOPE_SURFACE_AUDITS["verify_assumption_ledger"](result)


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
    _ENVELOPE_SURFACE_AUDITS["verify_cluster_inference"](result)


def verify_bootstrap_draws(result: dict) -> None:
    """Independently audit how many draws each of one result's intervals rests on.

    The result-only counterpart to :func:`verify`, and it needs to be one for
    a sharper reason than its siblings. A ``bounds_results`` row carries its
    own bootstrap block, and bounds attach precisely where point
    identification failed — so :func:`verify` is dormant for exactly the
    results whose draws nobody else audits.

    Returns ``None`` on accept. Raises ``VerificationError`` when a block's
    losses do not add up to the draws that went missing, when a discard names
    a reason outside the refusal vocabulary, when an interval is reported over
    fewer draws than a quantile can be taken over, or when the share of draws
    refuting a declared monotonicity is not the share the record implies.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _ENVELOPE_SURFACE_AUDITS["verify_bootstrap_draws"](result)


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
    _ENVELOPE_SURFACE_AUDITS["verify_outcome_error"](result)


def verify_berkson_error(result: dict) -> None:
    """Independently audit one result's Berkson-error assessment.

    The result-only counterpart to :func:`verify`, and it rides on the
    result for the same reason :func:`verify_outcome_error` does — but the
    claim it audits is the stronger one. A Berkson block says the answer
    beside it is the causal slope UNCORRECTED, where the same declared
    variance under the classical structure would have de-attenuated it.
    No arithmetic separates those, so what is checked is that the premise
    reached the reader.

    Returns ``None`` on accept. Raises ``VerificationError`` when a
    reported scalar does not follow from the recorded moments, when the
    coefficient the price is scaled by is not the one the answer reports,
    or when the declared structure never reaches the assumption ledger.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _verify_berkson_error_rule(result)


def verify_survival_curve(result: dict) -> None:
    """Independently audit one result's restricted mean survival time.

    The result-only counterpart to :func:`verify`, on the pattern the two
    above set. What it re-derives is the whole answer: the per-cell risk
    tables are a sufficient statistic, so the Kaplan-Meier curve, the area
    under it and Greenwood's variance are recomputed from them without the
    data and without importing the estimator.

    Returns ``None`` on accept, and on a result carrying no such block.
    Raises ``VerificationError`` when a curve, area or variance does not
    recompute, when the standardisation is not the weighted mean it
    claims, when a risk table does not account for its own losses — the
    forgery every arithmetic check above would otherwise pass — or when
    the independent-censoring premise, which no arithmetic witnesses,
    never reaches the assumption ledger.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _verify_survival_curve_rule(result)


def verify_fingerprints_agree(result: dict) -> None:
    """Independently audit that every digest on one result is a digest
    of the same run of the same table.

    The result-only counterpart to :func:`verify`, for the same reason
    as :func:`verify_cluster_inference`: the digests ride on the result
    rather than on a derivation chain, and an answer can carry four of
    them while its status never flips to ``numerically_solved``.

    Agreement is not equality. A bound legitimately covers fewer
    columns than the estimate whose point it brackets, so its digest
    legitimately differs; what has to hold is that the digest is a
    function of the columns it covers, and that no answer stands on a
    column the run never received.

    Returns ``None`` on accept, and on a result carrying no digest at
    all. Raises ``VerificationError`` when two digests over one column
    list disagree, when one digest is reported over two different
    lists, when an answer stands on a column that never arrived, or
    when the derivation chain's digest is of no table this answer
    names."""
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _ENVELOPE_SURFACE_AUDITS["verify_fingerprints_agree"](result)


def verify_one_row_count(result: dict) -> None:
    """Independently audit that every record of one result's row count
    is the same number.

    The result-only counterpart to :func:`verify`, and the sibling of
    :func:`verify_fingerprints_agree`: the digests say which table an
    answer stands on and this says how big it was. Both ride on the
    result rather than on a derivation chain.

    The run writes the count down once, before any estimator runs, and
    the point estimate, each bounds row, the outcome-error block and
    every derivation step's inputs then carry their own copy. Unlike the
    digests, agreement here IS equality: a bound covering fewer columns
    still covers the same rows.

    Returns ``None`` on accept, and on a result recording the count once
    or not at all. Raises ``VerificationError`` when two records of it
    disagree — the precision a reader takes off one of them then belongs
    to a table the other was not computed on."""
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    validate_result(result)
    _ENVELOPE_SURFACE_AUDITS["verify_one_row_count"](result)


def verify_markov_blanket(result: dict) -> None:
    """Independently audit a Markov-blanket result (borrow-list #4).

    Parallel to :func:`verify_bounds_results`: the artifact is a standalone
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


def verify_lagged_discovery(result: dict) -> None:
    """Independently audit a lagged-discovery result.

    Parallel to :func:`verify_markov_blanket`, and for the same reason a
    learned graph needs one at all: re-running a search on the same data
    reproduces its bugs, so what can be audited is whether the returned object
    has the properties it claims. PCMCI's two stages each have one — the
    parent set is claimed to be a fixpoint (every parent dependent given the
    rest, every non-parent independent given all of them), and each MCI test
    is claimed to have conditioned on the target's parents plus the driver's
    own parents shifted back by the lag.

    Both are recomputed from the recorded correlation matrix with an
    independent reimplementation of the Fisher-Z test, with no re-run of the
    search. Returns ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` on any structural
    inconsistency, an ill-formed statistic, a recorded test that disagrees
    with the recomputation, an MCI test run on the wrong conditioning set, or
    a parent set that is not the fixpoint it claims at the stated alpha.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.lagged_discovery_rules import (
        verify_lagged_discovery as _verify_lagged,
    )

    _verify_lagged(result)


def verify_latent_lagged_discovery(result: dict) -> None:
    """Independently audit a lagged graph learned without causal sufficiency.

    The sibling above audits two claimed properties; this audits three, and
    the third is the one the module exists for. The screen is claimed to be a
    grow-shrink fixpoint — checked even though the producer does not present
    it as the answer, because the conditioning pool every verdict was reached
    inside is a function of it. Each verdict is claimed to be what a search
    over subsets of that pool returns, so the enumeration is re-run. And each
    endpoint mark is claimed to follow from one triple by one rule, so the
    marks are re-derived from the recorded adjacency and separating sets and
    held against the recorded ones.

    All of it from the recorded correlation matrix, with independent
    reimplementations of the Fisher-Z test, the pool, the enumeration and the
    rules, and with no re-run of the search. Returns ``None`` on accept;
    raises :class:`themis.verifier.errors.VerificationError` on any structural
    inconsistency, an ill-formed statistic, a screen that is not a fixpoint, a
    verdict the search does not return, a recorded number that disagrees with
    the recomputation, an edge list that is not the adjacent verdicts, or an
    endpoint mark the rules do not produce — which is the failure that
    matters, since a fabricated tail is a causal claim made out of nothing.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.latent_lagged_discovery_rules import (
        verify_latent_lagged_discovery as _verify_latent_lagged,
    )

    _verify_latent_lagged(result)


def verify_notears_fit(result: dict) -> None:
    """Independently audit a NOTEARS fit.

    Parallel to :func:`verify_markov_blanket`, and reaching a place the other
    discovery audits do not: a continuous optimiser's answer. A local optimum
    found by L-BFGS-B cannot be replayed step for step, so this does not try
    — it uses the fact that the objective and its gradient depend on the data
    only through the Gram matrix, which makes a d×d matrix a sufficient
    statistic for the whole problem. The acyclicity residual, the objective,
    the first-order residual, the edges at the declared threshold and the
    varsortability of the graph they make are all recomputed from that matrix
    and the returned weights, with a second transcription of the matrix
    exponential and no call to the producer.

    Returns ``None`` on accept; raises
    :class:`themis.verifier.errors.VerificationError` on any structural
    inconsistency, or on a recorded number that disagrees with the
    recomputation. Global optimality is not certified — the problem is not
    convex and no artifact here claims it.
    """
    if not isinstance(result, dict):
        raise TypeError(f"result must be a dict; got {type(result).__name__}")
    from .verifier.notears_rules import verify_notears_fit as _verify_notears

    _verify_notears(result)


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
    _ENVELOPE_SURFACE_AUDITS["verify_selection_recovery_numeric"](result)


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
    _ENVELOPE_SURFACE_AUDITS["verify_missing_data_numeric"](result)
