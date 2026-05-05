"""Core data types shared across all layers.

These mirror the JSON Schema definitions in atom.schema.json,
kernel_ast.schema.json, and query_result.schema.json.

All dataclasses are frozen so values can be hashed and compared
structurally; the runtime treats them as immutable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


# ---------------------------------------------------------------------------
# atom.schema.json
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ConstTerm:
    name: str


@dataclass(frozen=True)
class VarTerm:
    name: str


Term = Union[ConstTerm, VarTerm]


@dataclass(frozen=True)
class RelativeTimeIndex:
    value: int


@dataclass(frozen=True)
class Atom:
    predicate: str
    args: tuple[Term, ...]
    time_index: RelativeTimeIndex | None = None


# ---------------------------------------------------------------------------
# kernel_ast.schema.json — model-side statements
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Annotation:
    confidence: float | None = None
    source: str | None = None


@dataclass(frozen=True)
class CauseStatement:
    from_atom: Atom
    to_atom: Atom
    forall: tuple[str, ...] = ()
    # Slice A2: symmetry with ObservationStatement / ProbabilityStatement
    # — carries provenance metadata (``source``) and composite
    # confidence for downstream consumers. Reasoning rules never
    # inspect this field; it's pure metadata so the LLM / auditor can
    # distinguish evidence-backed edges from llm-proposed hypotheses.
    annotations: Annotation | None = None


@dataclass(frozen=True)
class BidirectedStatement:
    """Phase 2.latent S1: a bidirected edge between two observed atoms.

    Semantically represents the presence of at least one unobserved
    common cause U of ``left`` and ``right``, without modeling U as an
    explicit predicate (semi-Markov representation). The statement is
    undirected — ``left`` and ``right`` are purely syntactic slots.

    S1 only lands the AST / schema surface; runtime dispatch refuses
    to execute a program containing bidirected statements until
    Phase 2.latent S2+ implements m-separation and c-component
    analysis. See PHASE_2_LATENT_CHARTER.md §6.3 / §7.
    """
    left: Atom
    right: Atom
    forall: tuple[str, ...] = ()
    annotations: Annotation | None = None


AtomValue = Union[bool, int, float, str]


@dataclass(frozen=True)
class SelectionNode:
    """Phase 9 §T9.1: a Bareinboim-Pearl selection node.

    Declares that ``affects`` has a different distribution between
    ``source_population`` and ``target_population`` — the canonical
    reason transport identification needs adjustment. The S node
    itself does NOT enter G(M) (the working causal graph); it only
    enters the *selection diagram* D = G(M) ∪ {S → affects}, which
    transport-aware identification rules construct on demand.

    No ``forall`` — populations and S nodes are program-global, not
    per-domain-object. The statement is dispatch-inert in S.T9.1.1
    (schema only); transport identification rules in S.T9.1.3 read it.
    """
    id: str
    affects: Atom
    source_population: str
    target_population: str
    annotations: Annotation | None = None


@dataclass(frozen=True)
class ObservationStatement:
    atom: Atom
    value: AtomValue
    annotations: Annotation | None = None


@dataclass(frozen=True)
class Intervention:
    atom: Atom
    value: AtomValue


@dataclass(frozen=True)
class ProbabilityStatement:
    # target and given atoms carry concrete literal values — the CPT
    # entry they describe is fully specified at program time.
    target: "ValuedAtom"
    given: tuple["ValuedAtom", ...]
    value: float
    forall: tuple[str, ...] = ()
    population: str | None = None  # Phase 9 §T9.1: source population label
    annotations: Annotation | None = None


# ---------------------------------------------------------------------------
# kernel_ast.schema.json — queries
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CauseQuery:
    from_atom: Atom
    to_atom: Atom


@dataclass(frozen=True)
class AssocQuery:
    left: Atom
    right: Atom
    given: tuple[Atom, ...]


@dataclass(frozen=True)
class EffectQuery:
    # target carries the concrete value whose probability under
    # intervention is being queried; given conditions the effect on a
    # specific subpopulation defined by concrete atom values.
    target: "ValuedAtom"
    intervention: Intervention
    given: tuple["ValuedAtom", ...]
    # Phase 6.mediation: when set, the query asks for a mediation
    # decomposition (NDE/NIE/CDE) through this mediator atom rather
    # than a plain total effect. Default None preserves pre-mediation
    # semantics and JSON schema compatibility.
    mediator: Atom | None = None
    # Phase 9 §T9.1: when set, asks for the effect in this target
    # population (transport identification path). None preserves
    # pre-transport semantics.
    target_population: str | None = None


@dataclass(frozen=True)
class IdentifyQuery:
    # identify is a structural question; target / given have no values
    # attached because identifiability depends on atoms, not values.
    target: Atom
    intervention: Intervention
    given: tuple[Atom, ...]
    # Phase 9 §T9.1: when set, asks whether the interventional quantity
    # is identifiable in this target population.
    target_population: str | None = None


@dataclass(frozen=True)
class ProbabilityQuery:
    target: "ValuedAtom"
    given: tuple["ValuedAtom", ...]


class Monotonicity(str, Enum):
    NON_DECREASING = "non_decreasing"
    NON_INCREASING = "non_increasing"


@dataclass(frozen=True)
class CounterfactualAssumptions:
    monotonicity: Monotonicity | None = None


@dataclass(frozen=True)
class CounterfactualQuery:
    observed: "ValuedAtom"
    counterfactual_intervention: Intervention
    counterfactual_target: "ValuedAtom"
    assumptions: CounterfactualAssumptions | None = None
    factual_target_known: AtomValue | None = None


Query = Union[
    CauseQuery,
    AssocQuery,
    EffectQuery,
    IdentifyQuery,
    ProbabilityQuery,
    CounterfactualQuery,
]


@dataclass(frozen=True)
class QueryStatement:
    id: str
    query: Query


@dataclass(frozen=True)
class VariableDeclaration:
    """Slice A0 advisory framing metadata, attached to a predicate.

    All fields except ``predicate`` are optional; unset fields become
    framing gaps on any query that references this predicate. Omitting
    the declaration entirely silences framing for that predicate.
    Nothing here gates reasoning — presence of a declaration cannot
    change status or numeric output.

    Slice #41 adds three more framing dimensions surfaced by the
    #33 stress test: ``direction`` (up / down / mixed effect polarity),
    ``baseline`` (the reference level a change is measured from), and
    ``state_vs_event`` (a habitual state or a discrete occurrence).
    These join the original four fields symmetrically — they are
    optional metadata; A0 reports them as gaps when unset on a
    declared predicate.
    """
    predicate: str
    domain: tuple[AtomValue, ...] | None = None
    time_window: str | None = None
    measurement: str | None = None
    threshold: str | None = None
    observability: str | None = None
    unit: str | None = None
    direction: str | None = None
    baseline: str | None = None
    state_vs_event: str | None = None


Statement = Union[
    CauseStatement,
    BidirectedStatement,
    ProbabilityStatement,
    ObservationStatement,
    QueryStatement,
    VariableDeclaration,
]


@dataclass(frozen=True)
class Program:
    version: str
    objects: tuple[str, ...]
    statements: tuple[Statement, ...]
    extensions: dict | None = None
    # Slice #36: per-run options. Currently supports ``strict_framing``
    # (bool) — when True, effect / probability queries whose predicates
    # have A0 framing gaps flip to needs_investigation before numeric
    # evaluation, instead of passing through. Additive; default None
    # preserves advisory-only behavior.
    options: dict | None = None


# ---------------------------------------------------------------------------
# query_result.schema.json — formula AST (see formula_ast_spec_v0_1.md)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VarRef:
    name: str


ValueExpr = Union[bool, int, float, str, VarRef]


@dataclass(frozen=True)
class ValuedAtom:
    atom: Atom
    # None means the value is bound externally by the enclosing query
    # context (see formula_ast_spec_v0_1.md §3.3).
    value: ValueExpr | None = None


@dataclass(frozen=True)
class ConstantExpr:
    value: float


@dataclass(frozen=True)
class ProbabilityRefExpr:
    target: ValuedAtom
    given: tuple[ValuedAtom, ...]


@dataclass(frozen=True)
class ProductExpr:
    terms: tuple["FormulaExpr", ...]


@dataclass(frozen=True)
class BindDecl:
    name: str


@dataclass(frozen=True)
class SumExpr:
    bind: BindDecl
    over: Atom
    body: "FormulaExpr"


FormulaExpr = Union[ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr]


# ---------------------------------------------------------------------------
# query_result.schema.json — result envelope
# ---------------------------------------------------------------------------

class ResultStatus(str, Enum):
    STRUCTURALLY_SOLVED = "structurally_solved"
    NUMERICALLY_SOLVED = "numerically_solved"
    NEEDS_INVESTIGATION = "needs_investigation"
    OUTSIDE_LANGUAGE = "outside_language"
    COUNTERFACTUAL_SOLVED = "counterfactual_solved"
    COUNTERFACTUAL_BOUNDED = "counterfactual_bounded"
    NEEDS_ASSUMPTION = "needs_assumption"


class QueryKind(str, Enum):
    CAUSE = "cause"
    ASSOC = "assoc"
    EFFECT = "effect"
    IDENTIFY = "identify"
    PROBABILITY = "probability"
    COUNTERFACTUAL = "counterfactual"


@dataclass(frozen=True)
class StructuralResult:
    value: bool | str | None
    supporting_paths: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class NumericInterval:
    low: float
    high: float


@dataclass(frozen=True)
class NumericResult:
    value: float | None
    interval: NumericInterval | None = None
    unit: str | None = None


class MissingKind(str, Enum):
    PARAMETER = "parameter"
    OBSERVATION = "observation"
    SAMPLE = "sample"
    STRUCTURE = "structure"
    ASSUMPTION = "assumption"
    # Slice #36: strict_framing blocked the numeric path because a
    # predicate the query references has framing gaps. Declarative
    # only — the actionable follow-up lives in the F1 DEFINE_VARIABLE
    # investigation channel; investigation_pusher skips this kind.
    FRAMING = "framing"


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class MissingItem:
    kind: MissingKind
    name: str
    priority: Priority
    reason: str | None = None


class InvestigationAction(str, Enum):
    COLLECT_OBSERVATION = "collect_observation"
    RUN_EXPERIMENT = "run_experiment"
    INCREASE_SAMPLE = "increase_sample"
    VALIDATE_PARAMETER = "validate_parameter"
    DEFINE_ASSUMPTION = "define_assumption"
    # Slice F1: surface framing gaps as an actionable task, not just an
    # advisory note. One item per underframed predicate, each carrying a
    # variable_patch skeleton that feeds directly into the A1 fill-back
    # loop via ``extract_definition_skeleton``.
    DEFINE_VARIABLE = "define_variable"


@dataclass(frozen=True)
class InvestigationItem:
    """One concrete entry inside an InvestigationRequest.

    A request groups items by MissingKind; this dataclass holds the
    per-item specifics that would be lost if we rendered the group as
    a single flat string.
    """
    target: str
    reason: str | None = None
    # For MissingKind.PARAMETER, a dict that the caller can drop into a
    # program's "statements" list after filling in ``value``. None for
    # other kinds (or when scheduler did not supply structured info).
    skeleton: dict | None = None


@dataclass(frozen=True)
class InvestigationRequest:
    action: InvestigationAction
    target: str                           # summary / first-item target
    priority: Priority
    note: str | None = None
    # v0.2 slice 9.x-B additions:
    group: str | None = None              # MissingKind.value — "parameter"...
    items: tuple[InvestigationItem, ...] = ()


@dataclass(frozen=True)
class StepRef:
    """Reference to a prior DerivationStep's output by step_id."""
    step_id: str


@dataclass(frozen=True)
class DerivationStep:
    """One step in a QueryResult's derivation (slice V0 of the verifier).

    Each step cites a named rule. ``inputs`` is a mapping from parameter
    name to value; a value may be a concrete object (Atom, frozenset of
    Atoms, graph, FormulaExpr, ValuedAtom, ...) or a ``StepRef`` pointing
    at a prior step's output. ``output`` is the rule's result.

    The ``rule`` string must match one of the named rules that the
    verifier implements. If the verifier can't recognise the rule name
    it rejects the derivation.

    ``inputs`` uses a ``dict`` for ergonomics — the dataclass itself is
    frozen, but callers should treat the dict as read-only.

    ``success`` (Phase 10): false marks a step that ran but produced a
    structural failure (e.g. backdoor_failed, iv_invalid). The Phase 10
    DataGapReport generator scans success=false steps to emit
    unidentifiable_no_admissible_set / missing_iv_candidate gaps.
    Defaults to True so existing rule emitters need not be touched.
    """
    rule: str
    inputs: dict
    output: object
    step_id: str | None = None
    success: bool = True


@dataclass(frozen=True)
class FramingNote:
    """Slice A0 advisory: one predicate's unset framing-metadata fields.

    Emitted only for predicates that *have* a VariableDeclaration but
    leave some metadata unset. Fully-undeclared predicates produce no
    note — framing is opt-in per predicate.
    """
    predicate: str
    missing: tuple[str, ...]


@dataclass(frozen=True)
class ConfidenceSource:
    """Slice #34: one slot's contribution to the composite confidence.

    The composite is ``min`` across non-None slot confidences (RFC
    §3). Each slot's contribution is the confidence of the source
    statement(s) with the minimum annotation.confidence in that slot.
    Recording this lets downstream consumers cite the weakest-link
    source explicitly instead of only seeing the aggregated number.
    """
    slot_label: str              # e.g. "parameter:P(Y=T|X=T)" or "observation:X=true"
    source: str | None           # annotations.source verbatim; None if unset
    confidence: float
    is_weakest: bool             # True iff confidence == the composite min


# ============================================ Phase 10: DataGapReport
#
# Output (2) per VISION 定位收紧 (2026-04-26): structured "what data is
# still needed to validate this causal claim" summary. The generator in
# themis/output/data_gap_report.py is a pure function over derivation +
# investigation_requests + framing_notes + extensions — no I/O.
#
# Schema mirror: query_result.schema.json#/$defs/{dataGapReport,dataGap}.


class GapKind(str, Enum):
    UNIDENTIFIABLE_NO_ADMISSIBLE_SET = "unidentifiable_no_admissible_set"
    MISSING_DISTRIBUTION = "missing_distribution"
    MISSING_POPULATION_DISTRIBUTION = "missing_population_distribution"
    MISSING_ASSUMPTION = "missing_assumption"
    MISSING_IV_CANDIDATE = "missing_iv_candidate"
    MISSING_MEDIATOR_DATA = "missing_mediator_data"
    TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN = "transport_target_distribution_unknown"
    # Bareinboim transport formula has TWO data needs: target P*(Z) AND
    # source P(Y|do(X), Z). Most meta-analyses only publish marginal
    # effects, so the source-stratified conditional is often the real
    # bottleneck — surfaced as its own gap_kind so the diagnosis names
    # it explicitly.
    TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN = "transport_source_conditional_unknown"
    AMBIGUOUS_VARIABLE_DEFINITION = "ambiguous_variable_definition"
    # Phase 13: NL questions of shape "X 让 Y 升多少 / X 和 Y 的关系图"
    # ask for a dose-response curve E[Y|do(X=x)] as a function of x.
    # Themis is a validator + diagnostician, not a regression engine —
    # it doesn't compute the curve. This gap_kind names everything the
    # user needs to fit the curve elsewhere (EconML / DoubleML / GAM):
    # X sampling points, per-point sample size, confounders to control,
    # time window, SUTVA concerns.
    DOSE_RESPONSE_DATA_REQUIRED = "dose_response_data_required"
    # The structural answer was reached only by traversing edges the
    # upstream LLM proposed (annotations.source == "llm_proposal") rather
    # than evidence-backed edges. Reasoning replays the LLM's own
    # assumption — surfaced as INFORMATIONAL so the renderer can disclose
    # this instead of presenting the answer as independently verified.
    UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH = "unverified_proposal_edge_on_query_path"
    # IV identification carries a non-default assumption (monotonicity for
    # LATE/Wald, linearity for 2SLS/ATE) — surfaced as a must-disclose
    # caveat so the renderer cannot silently report the IV estimate as
    # an unconditional ATE.
    IV_IDENTIFICATION_ASSUMPTION_REQUIRED = "iv_identification_assumption_required"
    # Mediation NDE/NIE / CDE identification each rest on cross-world
    # ignorability + sequential ignorability + no intermediate confounder
    # + consistency. "Identifiable=true" reads as unconditional unless the
    # underlying assumptions are surfaced.
    MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED = "mediation_identification_assumption_required"
    # Transport identification rests on S-admissibility + correct
    # selection-node specification. The transferred estimate isn't valid
    # outside those assumptions.
    TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED = "transport_identification_assumption_required"
    # The upstream program declared an ambiguity the kernel did not
    # resolve into a structural decision (reciprocal causation, mechanism
    # vs existence, mediator choice, etc.). Renderer must surface so the
    # user sees the LLM's own uncertainty.
    LLM_DECLARED_AMBIGUITY = "llm_declared_ambiguity"
    # Numeric answer comes from symbolic bounds (Manski / Balke-Pearl),
    # not a point estimate. Without disclosure the bounds interval reads
    # like a point with confidence intervals.
    ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE = "answer_is_bounds_not_point_estimate"
    # Composite confidence (min across slot annotations) is below the
    # caveat threshold — at least one input statement is low-confidence
    # and the answer inherits that uncertainty.
    LOW_CONFIDENCE_INPUT_DATA = "low_confidence_input_data"
    # Pearl's front-door criterion identification rests on three graphical
    # premises (M intercepts every X→Y path, no unblocked X→M backdoor,
    # all M→Y backdoors blocked by X) plus consistency. Without disclosure
    # 'identifiable via front-door' reads as unconditional.
    FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED = "front_door_identification_assumption_required"
    # Counterfactual identification (twin network / monotone bounds)
    # depends on the consistency + composition axioms and, for bounds,
    # binary + monotonicity. Renderers must surface or counterfactual
    # numbers read like ordinary point estimates.
    COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED = "counterfactual_identification_assumption_required"
    # The DAG itself (or part of it) was learned from data by a causal-
    # discovery algorithm (PC / FCI / LiNGAM) rather than declared from
    # domain knowledge. The result inherits the algorithm's assumptions —
    # faithfulness, causal sufficiency (PC), or LiNGAM's linearity /
    # non-Gaussianity. Surfaced as a top-level caveat distinct from
    # individual proposal-edge gaps.
    GRAPH_LEARNED_FROM_DATA = "graph_learned_from_data"


class GapSeverity(str, Enum):
    BLOCKING = "blocking"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


class GapBlocks(str, Enum):
    POINT_ESTIMATE = "point_estimate"
    BOUNDS = "bounds"
    IDENTIFICATION = "identification"
    INTERPRETATION = "interpretation"
    TRANSPORT = "transport"


class GapRefKind(str, Enum):
    DERIVATION_STEP = "derivation_step"
    INVESTIGATION_REQUEST = "investigation_request"
    FRAMING_NOTE = "framing_note"
    VERIFIER_CHECK = "verifier_check"


class RequiredDataType(str, Enum):
    IPD = "ipd"
    MARGINAL = "marginal"
    RCT = "rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    EXPERT_JUDGMENT = "expert_judgment"


@dataclass(frozen=True)
class GapProvenanceRef:
    """One signal (derivation step / investigation_request / framing_note /
    verifier check) that triggered a DataGap. T10-1 verifier checks each
    ref resolves to a real artifact in the result envelope."""
    ref_kind: GapRefKind
    ref_id: str


@dataclass(frozen=True)
class GapRequiredData:
    """Optional 'what kind of data closes this gap' block. Generator fills
    what it can infer from upstream signals; absent fields stay None."""
    data_type: RequiredDataType | None = None
    population: str | None = None
    variables: tuple[str, ...] = ()
    min_sample_size: int | None = None
    precision_target: str | None = None
    # Phase 13 — fields used by DOSE_RESPONSE_DATA_REQUIRED. Other gap
    # kinds leave these as defaults; they're additive and JSON-omitted
    # when None / empty.
    sampling_point_count: int | None = None
    """How many distinct X values the user should sample to fit the curve
    (e.g. 5 raise amounts: 0/500/1000/2000/5000). Hill-Tukey rule of
    thumb: ≥4 to detect non-linearity."""
    confounders_required: tuple[str, ...] = ()
    """Predicates the user must measure and condition on (typically the
    backdoor adjustment set extracted from the program's DAG)."""
    time_window: str | None = None
    """Recommended measurement schedule, e.g. 'baseline + 4w + 12w'."""
    sutva_concerns: tuple[str, ...] = ()
    """Domain-specific SUTVA / interference risks to control for in
    study design (e.g. 'employees discussing raises with each other')."""


@dataclass(frozen=True)
class DataGap:
    """A single data / assumption / structural shortfall blocking some
    downstream output."""
    kind: GapKind
    severity: GapSeverity
    description: str
    blocks: GapBlocks
    provenance: tuple[GapProvenanceRef, ...]
    signature: str | None = None
    required_data: GapRequiredData | None = None
    if_provided: str | None = None
    alternative_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class DataGapReport:
    """Phase 10 top-level summary of what data / assumptions / structural
    changes are still needed. Gaps are sorted by severity (blocking >
    important > informational), then by derivation order."""
    summary: str
    gaps: tuple[DataGap, ...]
    actionable_next_steps: tuple[str, ...] = ()


@dataclass(frozen=True)
class QueryResult:
    status: ResultStatus
    query_kind: QueryKind
    query_id: str | None = None
    structural_result: StructuralResult | None = None
    numeric_result: NumericResult | None = None
    confidence: float | None = None
    confidence_sources: tuple[ConfidenceSource, ...] = ()
    formula: FormulaExpr | None = None
    missing_information: tuple[MissingItem, ...] = ()
    investigation_requests: tuple[InvestigationRequest, ...] = ()
    framing_notes: tuple[FramingNote, ...] = ()
    derivation: tuple[DerivationStep, ...] = ()
    explanation: str | None = None
    extensions: dict | None = None
    data_gap_report: DataGapReport | None = None
    bounds_result: "BoundsResult | None" = None  # Phase 12 — symbolic bounds


# ---------------------------------------------------------------------------
# Phase 12 — bounds-first output channel
#
# When point identification fails (no admissible adjustment set / missing
# distribution / refused assumption), the validator computes information-
# preserving bounds instead of staying silent. Symbolic only in this phase
# — the client (or future numeric estimator) plugs in observed
# distributions to get a numeric interval.
#
# Schema mirror: query_result.schema.json#/$defs/boundsResult.


class BoundsMethod(str, Enum):
    MANSKI_NATURAL = "manski_natural"
    BALKE_PEARL_IV = "balke_pearl_iv"
    FRONTDOOR_PARTIAL = "frontdoor_partial"
    MANSKI_TAMER_MONOTONICITY = "manski_tamer_monotonicity"


@dataclass(frozen=True)
class BoundsResult:
    """Symbolic bounds on the queried estimand.

    `lower_expression` and `upper_expression` are human-readable strings
    over observable quantities (e.g. ``"max(0, P(Y=1|X=1) - P(X=0))"``).
    Future numeric layer evaluates these against a DataFrame; for now
    they document what the bounds *would be* given observable data.

    `width_when_uninformative` flag is True when the bounds reduce to
    the trivial [-1, 1] / [0, 1] range — the answer is honest but
    useless, so the renderer warns the user.

    `assumptions` lists what the method requires (e.g. Manski has none;
    Balke-Pearl needs IV1/IV2/IV3). `data_required` lists the observable
    distributions a client would need to evaluate the expressions.
    """
    method: BoundsMethod
    lower_expression: str
    upper_expression: str
    assumptions: tuple[str, ...] = ()
    data_required: tuple[str, ...] = ()
    width_when_uninformative: bool = False
    notes: str | None = None
