"""Core data types shared across all layers.

These mirror the JSON Schema definitions in atom.schema.json,
kernel_ast.schema.json, and query_result.schema.json.

All dataclasses are frozen so values can be hashed and compared
structurally; the runtime treats them as immutable.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Union

import numpy as np

if TYPE_CHECKING:  # the species a shortfall names; its module imports this one
    from .gaps import Need, Route


class EnvelopeName(StrEnum):
    """A name that leaves its registry on the envelope.

    A registry declares a closed vocabulary once and hangs facts off each
    name; the name itself then travels out as a field. Both halves have to
    hold: inside the process the member carries what the registry knows,
    and on the envelope it is the plain string it always was. Copies and
    pickles come back as that string, because the envelope is data and
    whoever serialises it must not receive the registry along with it.

    An enum resists this in three separate places, since its members are
    singletons and it means to keep them that way: pickle looks the member
    up again, and ``copy``/``deepcopy`` hand back ``self`` without
    consulting pickle at all. Leaving any one alone would make it two
    rules — the pickled envelope is data, the copied one is not.

    It lives here rather than beside the first registry that needed it
    because there is more than one, and a base rewritten per registry is a
    rule that holds until someone forgets a third of it.
    """

    def __reduce_ex__(self, protocol):
        return (str, (str(self),))

    def __copy__(self) -> str:  # type: ignore[override]
        return str(self)

    def __deepcopy__(self, memo) -> str:  # type: ignore[override]
        return str(self)

    def __repr__(self) -> str:
        # The name, not the member. An enum's default repr spells out where
        # the value is declared, which is the one thing a reader who has
        # been handed the value does not need.
        return f"{type(self).__name__}({str(self)!r})"


# The five things JSON writes down. ``None`` is tested separately because it
# is a value rather than a type; every other one admits its subclasses, which
# is what ``json`` itself accepts.
_ENVELOPE_SCALARS = (bool, int, float, str)


def envelope_scalar(value: object) -> bool | int | float | str | None:
    """A value read out of the data, as the envelope is able to hold it.

    Six modules each wrote a version of this and the six disagreed, which
    is what independent rewrites look like as against copies. What they
    disagreed about is the predicate. Each was written as "remove numpy"
    and each documented itself as "JSON-safe", and those are different
    sets: ``.item()`` lands in the built-in types, and the built-in types
    are not the JSON ones — a clock reading, a duration and a complex
    number are all built in and none of them can be written down. So a
    value could satisfy what the code did and still fail what the
    docstring promised, out in whichever stranger's frame first reached
    ``json.dumps``.

    The conversion is therefore in two halves and only the second is the
    promise. numpy names its own plain-Python equivalent and nothing else
    knows it, so that half is delegated to it. Then the result has to BE
    one of the five, and when it is not this says so here — where the
    caller that produced the value is still on the stack — rather than
    passing the problem on to be raised somewhere that cannot name it.

    Printing the value instead is the alternative that has to be refused
    rather than merely not chosen. The verifier re-derives its findings
    from the envelope alone, so a level that was printed into a string is,
    on arrival, indistinguishable from a level that was a string: a claim
    about the data that no producer made and no reader can check.

    A float is one of the five and can still be none of them. JSON has no
    word for NaN or for either infinity; ``json.dumps`` invents three and
    refuses all three under ``allow_nan=False``, and no parser is required
    to read them. So "it serialises" and "it is JSON" are different
    questions, and the promise here is the second one. Measured when this
    was written, nothing produced a non-finite value — 19.9M conversions
    and 1768 envelopes across the suite — so this refuses what could
    arrive rather than what was arriving.
    """
    plain = value.item() if isinstance(value, np.generic) else value
    if isinstance(plain, float) and not math.isfinite(plain):
        # ``bool`` is not a float and an ``int`` cannot be non-finite, so
        # this is the whole of it. The token comes from the writer rather
        # than from a table here, because the writer is what a reader on
        # the other side would be handed.
        raise TypeError(
            f"a value read out of the data reaches the envelope as one of "
            f"the five things JSON writes down (a string, a number, true, "
            f"false, null); {plain!r} is written as {json.dumps(plain)}, "
            f"which JSON has no word for — json.dumps invents it, its own "
            f"strict mode refuses it, and no reader is required to accept "
            f"it. A number the envelope cannot carry is not a number the "
            f"verifier can re-derive from."
        )
    if plain is None or isinstance(plain, _ENVELOPE_SCALARS):
        return plain
    # Both names, because they can differ and the reader supplied only one
    # of them: a numpy clock reading arrives as ``datetime64`` and reaches
    # this line as ``date``, and a message that mentions only the second
    # describes a column the reader does not have.
    arrived = type(value).__name__
    became = type(plain).__name__
    what = arrived if became == arrived else f"{arrived}, a {became} here"
    raise TypeError(
        f"a value read out of the data reaches the envelope as one of the "
        f"five things JSON writes down (a string, a number, true, false, "
        f"null); {value!r} is a {what}, which is none of them, and printing "
        f"it would put a claim about the data on the envelope that nobody "
        f"made and no reader could check."
    )


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
    # Linear-SCM path coefficient on this edge (the α in
    # child = ... + α·from_atom + ...). Optional metadata: qualitative
    # DAG reasoning (cause / identify / backdoor) never inspects it; it
    # is consumed ONLY by the linear-SCM counterfactual point computation
    # (scm_counterfactual query, Pearl Primer §4). A fully-specified
    # linear SCM is one where every edge on the path to the target
    # carries a coefficient.
    coefficient: float | None = None


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
class MissingnessIndicator:
    """Phase 9 §S9.2: a Mohan-Pearl-Tian 2013 missingness indicator R_i.

    Declares that the substantive variable ``missing_var`` (V_i) is
    *partially observed* — sometimes missing — and that its missingness
    is caused by ``caused_by`` (the parents of R_i in the m-graph). The
    manifest data the analyst holds is the proxy V*_i = V_i when R_i=0
    (recorded) else missing; complete-case analysis conditions on R_i=0.

    Like ``SelectionNode``, the R node itself does NOT enter G(M) (the
    working causal graph). It only enters the *m-graph* built on demand
    by the missing-data recoverability rules (m-graph = G(M) ∪ {parent →
    R_i} for every declared indicator). No ``forall`` — the m-graph is
    program-global; the statement is dispatch-inert (schema + read by
    the missing-data rules only).

    An empty ``caused_by`` means R_i has no declared parents — i.e. the
    missingness is unconditionally random (MCAR contribution).
    """
    id: str
    missing_var: Atom
    caused_by: tuple[Atom, ...] = ()
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
    # Provenance of this probability entry; three accepted values:
    #
    # - ``"structural"`` (default, 2026-05-14): user-stated CPT entry,
    #   DAG parent-aligned. Strict parent-subset validation applies.
    # - ``"observational"`` (Gap B, v0.1.3): empirical / joint-derived
    #   conditional that may condition on descendants or non-parents
    #   (e.g. CLadder Q6772 Berkson-style "for accepted-AND-non-
    #   talented students, P(hard-working)=0.94"). Parent-subset
    #   validation is RELAXED — identification never requests
    #   observational keys (their shape doesn't match parent-aligned
    #   formula keys), so the entry is consumed only by direct lookup
    #   in associational / probability queries.
    # - ``"llm_prior"`` (Fix 3+4, v0.1.5): LLM-proposed prior from
    #   common knowledge when the user didn't supply a number AND
    #   the kernel reported InsufficientTheta. Strict parent-subset
    #   validation applies (it IS a CPT in the model's shape — the
    #   only difference from structural is sourcing). ``annotations.source``
    #   is REQUIRED non-empty for llm_prior — a one-sentence reason
    #   that surfaces in ``extensions.llm_proposed_review`` for the
    #   end user to audit before trusting the answer. Bounded fallback
    #   mode only (not opportunistic) — see charter
    #   FIX_3_4_CHARTER_llm_mediated_transport.md §1.4.
    provenance: str = "structural"
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
    # Joint interventions: when non-empty, the query asks for the JOINT
    # effect of intervening on the primary ``intervention`` AND every
    # Intervention in ``extra_interventions`` simultaneously —
    # do(A=a, B=b, ...). The primary intervention plus the extras form
    # the joint treatment vector {A, B, ...}. Identification uses the
    # generalized (treatment-set) back-door criterion; estimation uses
    # the joint g-formula including the treatment×treatment interaction
    # (see themis/estimation/joint.py). DEFAULT empty tuple ⇒ every
    # existing single-treatment program is byte-identical: the field is
    # omitted from serialization when empty, no identification /
    # estimation / verifier path changes, and the AST round-trips
    # exactly as before. v1 scope: binary treatments, no directed edge
    # between treatments, no mediator / target_population combined with
    # joint.
    extra_interventions: tuple[Intervention, ...] = ()
    # Phase 6.mediation: when set, the query asks for a mediation
    # decomposition (NDE/NIE/CDE) through this mediator atom rather
    # than a plain total effect. Default None preserves pre-mediation
    # semantics and JSON schema compatibility.
    mediator: Atom | None = None
    # Joint multi-mediator: when this holds >= 2 atoms, the query asks for
    # the JOINT natural-effect decomposition (joint NDE/NIE) through the
    # mediator SET taken as one block (VanderWeele-Vansteelandt 2014),
    # rather than a single-mediator split. Mutually exclusive with a
    # single ``mediator``: the scheduler routes k>=2 here and a lone
    # ``mediator`` through the single-mediator path. DEFAULT empty tuple
    # keeps every single-mediator / plain-effect program byte-identical —
    # the field is omitted from serialization when empty.
    mediators: tuple[Atom, ...] = ()
    # Phase 9 §T9.1: when set, asks for the effect in this target
    # population (transport identification path). None preserves
    # pre-transport semantics.
    target_population: str | None = None
    # A first-class assumption block, parallel to
    # CounterfactualQuery.assumptions. Carries the optional monotonicity
    # the Manski-Tamer bounds path reads. The scheduler still falls back
    # to program.extensions['monotonicity'] when
    # query.assumptions.monotonicity is None, for callers written against
    # that side channel.
    assumptions: "EffectQueryAssumptions | None" = None


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


class Monotonicity(EnvelopeName):
    """Which way the treatment is assumed to be able to move the outcome.

    On the base with the other envelope vocabularies, because it travels
    the same way: it is written into ``counterfactual.assumptions`` and
    into an assumption id, and a reader gets it back as a string. Off the
    base it answered ``str(member)`` with the member's address, which is
    the one spelling nobody asked for.
    """

    NON_DECREASING = "non_decreasing"
    NON_INCREASING = "non_increasing"


@dataclass(frozen=True)
class CounterfactualAssumptions:
    monotonicity: Monotonicity | None = None


@dataclass(frozen=True)
class EffectQueryAssumptions:
    """The first-class assumption block on EffectQuery.

    Parallel to ``CounterfactualAssumptions`` on CounterfactualQuery
    — regularizes the way assumptions attach to query types.

    Currently carries:
    - ``monotonicity``: when set, EffectQuery's bounds layer (Phase 12,
      Manski-Tamer) tightens one side of the Manski natural interval to
      the observed marginal under the declared direction. The older
      ``program.extensions['monotonicity']`` side channel is still
      supported — the scheduler falls back to it when
      query.assumptions.monotonicity is None.

    Future fields would land here as identification-time assumptions
    proliferate (e.g. effect-modification declarations, no-mediator-
    confounding for CDE).
    """
    monotonicity: Monotonicity | None = None


@dataclass(frozen=True)
class CounterfactualQuery:
    """One binary counterfactual cell: P(Y_{x'} = y* | X = x [, Y = y]).

    ``observed`` is the factual treatment X = x, ``counterfactual_intervention``
    the world we ask about (do(X = x')), ``counterfactual_target`` the event
    Y = y* whose probability is wanted, and ``factual_target_known`` the
    factual outcome y when it is part of the evidence.

    Answering it needs the observational joint P(X, Y) — recovered from theta
    — AND the interventional risk P(Y=1 | do(x')), which is either DERIVED by
    running the existing effect identification, or supplied directly via
    ``experimental_risk_treated`` / ``experimental_risk_control`` when X is
    confounded but a randomized experiment measured the risk (parallel to
    ``CausationQuery``). ``assumptions.monotonicity``, when declared, is an
    extra constraint that can sharpen the interval to a point — never a
    precondition for answering.
    """
    observed: "ValuedAtom"
    counterfactual_intervention: Intervention
    counterfactual_target: "ValuedAtom"
    assumptions: CounterfactualAssumptions | None = None
    factual_target_known: AtomValue | None = None
    experimental_risk_treated: float | None = None   # P(Y=1 | do(X=1))
    experimental_risk_control: float | None = None   # P(Y=1 | do(X=0))


@dataclass(frozen=True)
class CausationQuery:
    """Probabilities of causation (Tian & Pearl 2000) — the binary
    counterfactual-attribution query Themis previously could not answer:

    - PN  (necessity)   = P(Y_{x'}=0 | X=1, Y=1) — "given both happened,
                          would Y have NOT happened without X?" (liability)
    - PS  (sufficiency) = P(Y_{x}=1 | X=0, Y=0) — "given neither happened,
                          WOULD Y have happened had X?" (prevention)
    - PNS (both)         = P(Y_{x}=1, Y_{x'}=0)

    ``cause`` (X) and ``effect`` (Y) are binary atoms. The observational
    joint P(X, Y) is recovered from theta; the two interventional risks
    P(Y=1|do(X=1/0)) are either DERIVED via the existing effect
    identification machinery, or — for the confounded-but-experimentally-
    measured case (Tian-Pearl's drug example, where do(X) is not
    identifiable from observation alone) — supplied directly via
    ``experimental_risk_treated`` / ``experimental_risk_control``.

    ``monotonic=True`` asserts Y is monotonic in X (X never prevents Y),
    which point-identifies all three (Tian-Pearl Thm 3); otherwise only
    assumption-free bounds are returned.
    """
    cause: Atom
    effect: Atom
    monotonic: bool = False
    experimental_risk_treated: float | None = None   # P(Y=1 | do(X=1))
    experimental_risk_control: float | None = None    # P(Y=1 | do(X=0))


@dataclass(frozen=True)
class SCMCounterfactualQuery:
    """Deterministic counterfactual point on a fully-specified linear SCM
    (Pearl, Glymour & Jewell *Primer* §4.2: abduction–action–prediction).

    Given a linear SCM (each edge carries a path ``coefficient``) and a
    fully-observed unit (the factual values supplied as
    ObservationStatements — Pearl's evidence E=e), computes the exact
    value the ``target`` would have taken had ``intervention`` been
    imposed on that same unit:

      (i)   Abduction:  recover each exogenous U_V = v_obs − Σ α·parent_obs
      (ii)  Action:     replace the intervened variable's equation with the constant
      (iii) Prediction: propagate the recovered U forward through the modified SCM

    Unlike ``CounterfactualQuery`` (binary, monotone, returns Balke-Pearl
    BOUNDS), this returns an exact POINT — the regime where the structural
    mechanisms, not just the DAG, are known.
    """
    intervention: Intervention
    target: Atom


@dataclass(frozen=True)
class CounterfactualEvent:
    """One event ``V_{subscript}=value`` in a general counterfactual
    conjunction (Shpitser-Pearl R-336).

    ``variable`` is the base atom ``V``; ``subscript`` is the world in
    which it is read — a tuple of ``ValuedAtom`` interventions (empty =
    the factual world); ``value`` is the value ``V`` attains there.

    Example: ``Y_{X=1}=1`` is ``CounterfactualEvent(Y, (ValuedAtom(X, True),),
    True)``; the plain observation ``x'`` is
    ``CounterfactualEvent(X, (), False)``.
    """
    variable: Atom
    subscript: tuple[ValuedAtom, ...]
    value: AtomValue


@dataclass(frozen=True)
class CounterfactualConjunctionQuery:
    """General counterfactual identification (Shpitser-Pearl ID*/IDC*, R-336 /
    JMLR 9:1941-1979 2008).

    Asks whether ``P(γ | δ)`` is identifiable for a counterfactual conjunction

        γ = y¹_{x¹} ∧ … ∧ yᵏ_{xᵏ}

    optionally conditioned on a second counterfactual conjunction ``δ``
    (the ``condition`` field). Both span multiple, possibly contradictory,
    hypothetical worlds sharing exogenous background. This is the
    counterfactual rung of the causal hierarchy — strictly more general than
    ``CounterfactualQuery`` (a single binary/monotone world pair) and
    ``CausationQuery`` (PN/PS/PNS): the events range over arbitrary variables
    in arbitrary worlds.

    With ``condition`` empty the kernel decides identifiability structurally
    via ``runtime.ctf_identify.id_star`` (the unconditional ID*); with a
    non-empty ``condition`` it runs ``idc_star`` (IDC*, the conditional
    identifier — the engine behind attribution / effect-of-treatment-on-the-
    treated). It returns the estimand as an observational ``FormulaExpr``,
    ``P(γ|δ)=0`` for an inconsistent numerator, ``UNDEFINED`` when the
    conditioning event has probability zero, or non-identifiable (a w-graph
    witness).
    """
    events: tuple[CounterfactualEvent, ...]
    condition: tuple[CounterfactualEvent, ...] = ()


@dataclass(frozen=True)
class ProximalEffectQuery:
    """Proximal causal inference (Miao-Geng-Tchetgen 2018, Biometrika 105(4);
    Kuroki-Pearl 2014 as the independent source).

    Asks for the average causal effect ``P(Y | do(X))`` when the sufficient
    confounder ``U`` is UNOBSERVED, using two observed proxies of ``U`` — a
    treatment-inducing proxy ``Z`` and an outcome-inducing proxy ``W`` (in the
    negative-control vocabulary: a negative-control exposure and a
    negative-control outcome).

    ``latent`` names the unobserved confounder — an ordinary node of the program
    graph that carries no data column; the query merely declares which node is
    unobserved. ``latent_cardinality`` is the assumed number ``k`` of categories
    of ``U`` (the strongest assumption — U is never seen, yet its cardinality
    must be posited). Structurally the kernel decides identifiability via
    ``runtime.proximal_identify.identify_proximal`` (Miao model (f): the proxy
    criteria W⊥(Z,X)|U and Z⊥Y|(U,X) plus {U} a sufficient confounder); with
    data, ``estimation.proximal.estimate_proximal_ate`` recovers the ATE by
    inverting the Z×W measurement channel (Miao formula (5)). This is the escape
    hatch one rung past back-door / front-door / general-ID, all of which assume
    the confounders on the relevant paths are observed.
    """
    treatment: Atom
    outcome: Atom
    latent: Atom
    treatment_proxy: Atom
    outcome_proxy: Atom
    latent_cardinality: int


Query = Union[
    CauseQuery,
    AssocQuery,
    EffectQuery,
    IdentifyQuery,
    ProbabilityQuery,
    CounterfactualQuery,
    CausationQuery,
    SCMCounterfactualQuery,
    CounterfactualConjunctionQuery,
    ProximalEffectQuery,
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
    Surfaced by a framing stress test: ``direction`` (up / down /
    mixed effect polarity),
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
    # 2026-07-11 pre-flight data diagnostic: a POSITIVE declaration of the
    # variable's measurement scale — "binary" | "discrete" | "continuous".
    # Complementary to ``domain`` (which enumerates the levels of a discrete
    # / binary variable): ``scale`` is the only way to positively mark a
    # variable continuous, since "no domain" is ambiguous between "meant
    # continuous" and "didn't bother to declare". When set, the estimate
    # path reconciles it against the supplied data and raises a
    # ``declared_type_data_mismatch`` gap on disagreement (e.g. declared
    # continuous but the column has 2 distinct values). Optional advisory
    # metadata like the other framing fields — unset never gates reasoning
    # and never fires a gap.
    scale: str | None = None


Statement = Union[
    CauseStatement,
    BidirectedStatement,
    ProbabilityStatement,
    ObservationStatement,
    QueryStatement,
    VariableDeclaration,
    SelectionNode,
    MissingnessIndicator,
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
    # Fix 3+4 (charter FIX_3_4_CHARTER_llm_mediated_transport.md):
    # routes the lookup to a specific population's theta partition.
    # None = default / source population — backward-compat for all
    # existing single-population formulas (backdoor / front-door /
    # mediation / probability builders never set this, so their
    # ProbRefs hit ProbabilityKey entries with population == None).
    # Non-None values are used by the transport_formula builder to
    # tag P*(z) terms as the target-population marginal vs the
    # source-population interventional conditional in the same tree.
    population: str | None = None


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


@dataclass(frozen=True)
class FractionExpr:
    """A ratio of two formulas — the only FormulaExpr node that introduces
    division. Needed by conditional identification (IDC):
    ``P(Y|do(X),Z) = P_x(Y,Z) / P_x(Z)`` where numerator and denominator
    are each an ID result. The evaluator divides; a zero denominator is a
    positivity violation and raises."""
    numerator: "FormulaExpr"
    denominator: "FormulaExpr"


FormulaExpr = Union[
    ConstantExpr, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr
]


# ---------------------------------------------------------------------------
# query_result.schema.json — result envelope
# ---------------------------------------------------------------------------

class ResultStatus(StrEnum):
    STRUCTURALLY_SOLVED = "structurally_solved"
    NUMERICALLY_SOLVED = "numerically_solved"
    NEEDS_INVESTIGATION = "needs_investigation"
    OUTSIDE_LANGUAGE = "outside_language"
    COUNTERFACTUAL_SOLVED = "counterfactual_solved"
    COUNTERFACTUAL_BOUNDED = "counterfactual_bounded"
    # "identification works IF you grant this named untestable premise."
    # No dispatcher currently produces it: its only producer was the
    # counterfactual monotonicity gate, and monotonicity turned out to be a
    # constraint that sharpens an answer rather than a precondition for
    # having one. Kept in the envelope contract — consumers still handle it
    # and a future query kind may genuinely need it — but the handling in
    # data_gap_report / explainer is unreachable today.
    NEEDS_ASSUMPTION = "needs_assumption"


class QueryKind(StrEnum):
    CAUSE = "cause"
    ASSOC = "assoc"
    EFFECT = "effect"
    IDENTIFY = "identify"
    PROBABILITY = "probability"
    COUNTERFACTUAL = "counterfactual"
    CAUSATION = "causation"
    SCM_COUNTERFACTUAL = "scm_counterfactual"
    COUNTERFACTUAL_CONJUNCTION = "counterfactual_conjunction"
    PROXIMAL_EFFECT = "proximal_effect"


QUERY_KIND_OF: dict[type, QueryKind] = {
    CauseQuery: QueryKind.CAUSE,
    AssocQuery: QueryKind.ASSOC,
    EffectQuery: QueryKind.EFFECT,
    IdentifyQuery: QueryKind.IDENTIFY,
    ProbabilityQuery: QueryKind.PROBABILITY,
    CounterfactualQuery: QueryKind.COUNTERFACTUAL,
    CausationQuery: QueryKind.CAUSATION,
    SCMCounterfactualQuery: QueryKind.SCM_COUNTERFACTUAL,
    CounterfactualConjunctionQuery: QueryKind.COUNTERFACTUAL_CONJUNCTION,
    ProximalEffectQuery: QueryKind.PROXIMAL_EFFECT,
}
"""Which kind a query of each class is.

The two closed sets it joins are both declared just above, so this is
where the join belongs. It sat in the scheduler behind a helper that
nothing in the repository called, which is why nobody had noticed that
the input layer — the one place that turned out to need it — cannot
import the runtime.
"""


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


class MissingKind(StrEnum):
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


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class Observable:
    """What a sample would have to measure for a missing quantity to be
    had from data: these variables, drawn from this population.

    ``population`` is ``None`` for the population under study — the one a
    supplied DataFrame is a sample of. A named population is a different
    one (a transport target, a second site), and a sample of the study
    population does not settle it however many of the variables it holds.
    """
    variables: tuple[str, ...]
    population: str | None = None


@dataclass(frozen=True)
class MissingItem:
    """One thing the kernel needed and did not have.

    Orthogonal facts, each stated rather than encoded: ``gap`` is what
    kind of shortfall this is, ``kind`` is which channel would repair it,
    ``name`` identifies the specific thing, and ``observable`` says what
    measuring would settle it. ``name`` used to carry all of
    them — the producer knew the species, pressed it into a string, and
    the report recovered it with prefix and substring tests over that
    string. It recovered it wrongly whenever a name happened to read like
    another species, which is not a failure mode a naming convention can
    be made immune to.

    ``observable`` is the same fact one level down, and it exists because
    a later pass has to answer a question the name cannot be asked: the
    caller supplied a sample — does it settle this? The producer holds
    the variables and the population; every consumer that had to take
    ``P(y=True|z=True)`` apart again was reconstructing what was thrown
    away here. ``None`` when no sample settles the item at all: a graph
    that admits no adjustment set, an assumption nobody declared.

    ``superseded_by_estimation`` answers the other half of that question,
    for the asks no measurement repairs. Some of them are preconditions
    the identification layer imposes before it will write an estimand —
    declare monotonicity and the Wald ratio identifies the LATE — and the
    estimation layer answers the same query from data without consulting
    the declaration at all. So once it has spoken, by a number or by a
    refusal, the precondition is no longer what stands between the caller
    and an answer: the number discloses in the assumption ledger what it
    rested on, and the refusal says what to do instead. ``False`` for an
    ask that survives estimation — an input only an experiment supplies,
    two declared quantities that contradict each other.

    ``need`` is the species and ``gap`` is its kind, which is why the two
    are never passed together: :func:`themis.gaps.missing` reads the kind
    off the species. The pair replaced ``reason``, a sentence rendered at
    the site in one language out of exactly those two things and this
    occasion's values — ``said`` holds the values, already symbols, and
    ``words`` the slots whose text is a language, so that the surface that
    knows who is reading assembles the sentence and no site writes one.
    """
    kind: MissingKind
    name: str
    priority: Priority
    gap: GapKind
    need: "Need | None" = None
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, dict] = field(default_factory=dict)
    observable: Observable | None = None
    superseded_by_estimation: bool = False

    def __post_init__(self) -> None:
        if self.gap not in MISSING_ITEM_GAPS:
            raise ValueError(
                f"MissingItem({self.name!r}) declares gap={self.gap!r}, "
                f"which is not one of the species a missing item may be: "
                f"{sorted(g.value for g in MISSING_ITEM_GAPS)}"
            )


class InvestigationAction(StrEnum):
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
    # The species of the ``MissingItem`` this item was pushed from,
    # carried through verbatim. Required: an item with nothing to say
    # about its own species is one the report has to guess about, and
    # guessing is what this field removes. The framing channel builds its
    # items without a MissingItem and declares
    # ``AMBIGUOUS_VARIABLE_DEFINITION`` — whose gap is raised from
    # ``framing_notes`` rather than here, which the report's species
    # table states outright rather than inferring from an absent value.
    gap: GapKind
    # The species and the occasion, in the two halves the reader assembles
    # from — see MissingItem, whose items these are pushed from, and whose
    # ``need``/``said``/``words`` are copied here verbatim.
    need: "Need | None" = None
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, dict] = field(default_factory=dict)
    # For MissingKind.PARAMETER, a dict that the caller can drop into a
    # program's "statements" list after filling in ``value``. None for
    # other kinds (or when scheduler did not supply structured info).
    skeleton: dict | None = None
    # Carried through verbatim like ``gap``, and for a sharper reason:
    # this is the surface that survives. A pass that answers the query
    # drops ``missing_information`` wholesale, so an ask withdrawn on the
    # strength of what estimation did can only be recognised here.
    superseded_by_estimation: bool = False


@dataclass(frozen=True)
class InvestigationRequest:
    action: InvestigationAction
    target: str                           # summary / first-item target
    priority: Priority
    # What the items in this group have in common, as the species and the
    # occasion rather than a sentence — the same three fields the items
    # carry, so that "they are asking for the same thing" is decided on
    # the facts and not on two renderings coming out equal. ``None`` when
    # they have nothing in common, which the count in ``target`` already
    # says.
    note: dict | None = None
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

    ``success`` is false on a step that ran and produced a structural
    failure. No producer in this tree writes one: the kernel's derivations
    carry only steps that succeeded, and it says "not identifiable" with a
    successful ``tian_hedge_witness`` step or an investigation item
    instead. The field is here for the other direction — a derivation
    arriving from outside, through ``verifier.serialization``, may claim a
    failure, and the verifier has to see the claim in order to check it.
    Defaults to True.
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
    """One slot's contribution to the composite confidence.

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


class GapKind(StrEnum):
    UNIDENTIFIABLE_NO_ADMISSIBLE_SET = "unidentifiable_no_admissible_set"
    MISSING_DISTRIBUTION = "missing_distribution"
    MISSING_POPULATION_DISTRIBUTION = "missing_population_distribution"
    MISSING_ASSUMPTION = "missing_assumption"
    # A unit-level value the query needs and the program did not observe.
    # Distinct from MISSING_DISTRIBUTION: abduction in a deterministic SCM
    # counterfactual recovers this unit's exogenous term from its own
    # measured values, so what is wanted is a reading for this unit, not a
    # distribution over units. No amount of population data substitutes.
    MISSING_UNIT_OBSERVATION = "missing_unit_observation"
    # Residual for a structural requirement the kernel raised that no more
    # specific classifier claimed — an undeclared path coefficient, a
    # mediator that does not lie on a directed path, a query atom absent
    # from V, a conditioning event with probability zero in every model
    # the graph admits. Deliberately does NOT assert that identification
    # failed (``unidentifiable_no_admissible_set`` is the kind that says
    # that, and ``answer_tier`` reads it): a missing coefficient leaves a
    # point-identified estimand whose number was simply never declared.
    # Its reason for existing is to make an unclassified requirement loud
    # rather than silent, so a name added upstream costs specificity
    # instead of disappearing from the report.
    MISSING_STRUCTURAL_INPUT = "missing_structural_input"
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
    # Backdoor identification succeeded, but the user-provided DAG implicitly
    # asserts every relevant confounder is measured (no bidirected /
    # latent-common-cause edges declared). Real-world cases (HRT-CVD WHI 2002,
    # vitamin D-CVD VITAL 2018, breastfeeding-IQ Der 2006) document large
    # observational-vs-RCT gaps caused by *unmeasured* confounders that
    # survived measured-covariate adjustment. Fired as an INFORMATIONAL
    # advisory at the structural-solved stage so the user is alerted *before*
    # collecting data — sensitivity-analysis hooks (E-value) attach later at
    # the numeric stage. Suppressed on programs that already declare
    # bidirected edges (the user already knows about latents) or used IV /
    # Tian identification (those strategies *exist* to handle latents).
    UNMEASURED_CONFOUNDER_RISK = "unmeasured_confounder_risk"
    # Query specified multiple identification layers (e.g. both mediator
    # and target_population), but the kernel only dispatched one of them.
    # The other was silently skipped — Themis returned a valid result for
    # the dispatched layer but did NOT compute the other. Without this
    # disclosure the user may read 'structurally_solved' and assume both
    # layers were handled. Cole & Stuart 2010 + VanderWeele 2016 §6.2:
    # mediation × transport must be sequential operations, not a single
    # dispatch. Logged as IMPORTANT severity (not blocking — the
    # dispatched layer is correct; not informational — silent skip
    # violates VISION's honest-about-what-wasn't-done principle).
    UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT = "unattempted_layer_due_to_dispatch_conflict"
    # IV estimate was produced but the first-stage F-statistic
    # falls below the Stock-Yogo (2005) threshold (default 10), meaning
    # the instrument has weak partial correlation with treatment after
    # conditioning. Bias of the IV estimate toward OLS scales with 1/F;
    # confidence intervals from standard 2SLS asymptotics are misleading.
    # Surfaced as INFORMATIONAL must-disclose so the renderer cannot
    # silently report the LATE/ATE estimate as if it were unconditionally
    # reliable. Themis is uniquely positioned to surface this because
    # it owns both the program-level identification claim AND the
    # estimation context — DoWhy/EconML report F sometimes but don't
    # auto-route it as a structured data-gap entry.
    WEAK_IV_INSTRUMENT = "weak_iv_instrument"
    # Over-identified 2SLS (q >= 2 instruments): the Sargan over-identification
    # test REJECTS the instruments' joint validity — the data refute at least
    # one exclusion restriction. A falsification, not a data-quantity gap:
    # IMPORTANT severity (the point rests on a refuted assumption), must-disclose,
    # and it will not go away with more of the same data.
    OVERIDENTIFICATION_REJECTED = "overidentification_rejected"
    # A binary-Z / binary-X design with a conditioning set names the
    # stratified Wald — the LATE on compliers — but this sample could not
    # be cut into those strata (W continuous, too many cells, or a cell
    # with only one instrument arm), so the estimate fell back to 2SLS.
    # That is not a precision detail: 2SLS with W entered additively
    # weights each stratum's effect by the instrument's residual variance
    # there, so it targets a different quantity than the LATE and the two
    # agree only when the first stage is equally strong everywhere. The
    # fallback is reported for the same reason the estimand is named at
    # all — receiving a different number than the one asked for, with
    # nothing to mark the substitution, is the failure this discloses.
    # INFORMATIONAL must-disclose; the estimate is still surfaced.
    IV_ESTIMAND_FALLBACK_TO_LINEAR = "iv_estimand_fallback_to_linear"
    # Backdoor estimate (g-formula / outcome regression / IPW / AIPW /
    # TMLE) was produced and the "positivity" / "overlap" assumption
    # (Hernan & Robins ch.3) — every confounder stratum has both treated
    # and untreated units — does not hold. Extrapolation outside the
    # support is not real causal estimation.
    #
    # TWO WITNESSES, because the condition is a count and the count is
    # not always available. Where the adjustment set is discrete the
    # strata are enumerated and the cells holding one arm are named
    # outright. Where it is continuous there are no cells, and the
    # fallback is the fitted P(X=1|Z) leaving [0.05, 0.95] for more than
    # 5% of the sample. The fallback is a proxy and was for a long time
    # the only trigger, which is how a frame with a quarter of its
    # sample in a never-treated stratum passed: a logistic fit smooths
    # across cells and gave that stratum a propensity of 0.091.
    #
    # The name is narrower than the finding — the empirical witness
    # inspects no propensity model — and renaming an enum value that
    # reaches the schema, the browser and the frozen eval artifacts is
    # its own change.
    #
    # INFORMATIONAL must-disclose — the estimate is still computed, but
    # the user must know how much of it relies on extrapolation. DoWhy /
    # EconML can compute propensities but don't structure-route this as
    # a gap.
    PROPENSITY_OVERLAP_VIOLATION = "propensity_overlap_violation"
    # EffectQuery's `given` (conditioning subgroup) contains
    # a node W where both intervention X and target Y are ancestors.
    # Per Pearl d-separation, conditioning on W (a collider on the
    # X→...→W←...←Y path) OPENS that path rather than blocks it,
    # introducing selection / collider bias. The user thought they
    # were stratifying on a sensible covariate; structurally they
    # opened a non-causal path. Surfaced as IMPORTANT (not informational
    # — this is real identification damage, not just a caveat) so the
    # renderer cannot present the conditional effect as if it were
    # the same identification target. DoWhy/EconML accept arbitrary
    # adjustment / conditioning sets without flagging colliders;
    # Themis owns the program-level graph and can detect this
    # structurally. Selection-bias board (#7) is the lowest-coverage
    # active board — this gap_kind directly bumps it.
    COLLIDER_CONDITIONING_OPENS_BACKDOOR = "collider_conditioning_opens_backdoor"
    # Backdoor logistic estimator was fitted but the training-
    # set predicted probabilities cluster too heavily near 0 or 1 — the
    # outcome model's logits saturate, signaling quasi-separation
    # (outcome near-deterministic in some confounder stratum). The
    # plug-in g-formula then extrapolates E[Y|X=x,Z=z] using a model
    # with near-singular gradient; the point estimate is computed but
    # the CI is misleadingly tight and the bias toward 0/1 is large.
    # Trigger: > 10% of fitted P(Y|X,Z) falls outside [0.01, 0.99].
    # INFORMATIONAL must-disclose — distinct from
    # propensity_overlap_violation, which inspects the
    # treatment-assignment model P(X|Z), not the outcome model.
    # Together they cover both halves of the doubly-robust intuition.
    OUTCOME_MODEL_QUASI_SEPARATION = "outcome_model_quasi_separation"
    # Graph-CPT independence mismatch surfaced by the d-separation
    # guard. The user supplied a marginal P(Y|S) for some
    # subset S ⊂ given, the evaluator considered it as a substitute for
    # the demanded conditional P(Y|given), and the guard refused because
    # the declared graph does NOT entail Y ⊥ extras | S. That fact is
    # written into the InsufficientTheta reason string, but a reason
    # string is not a route: classified as plain MISSING_DISTRIBUTION,
    # the item tells the user (and any LLM consuming the structured
    # output) "supply more theta entries". The actionable fix is
    # different: their declared
    # graph and their supplied CPTs disagree — either drop the offending
    # edge OR supply the demanded conditional. Distinct gap_kind so the
    # structured channel can route the correct repair action, not just
    # the renderer's reason string. Must-disclose IMPORTANT severity —
    # this is a real model-input inconsistency, not a data-shortage
    # caveat. No external library does this routing — it depends on
    # owning both the structural graph and the supplied CPT family.
    GRAPH_THETA_INDEPENDENCE_MISMATCH = "graph_theta_independence_mismatch"
    # Measurement-error concern surfaced from program-shape
    # alone (no LLM-declared ambiguity required). At least one variable
    # on the identification path declares a ``measurement`` or
    # ``observability`` field whose value names a textually documented
    # noisy-measurement pattern — self-report / questionnaire / FFQ /
    # 24h recall / single-occasion BP / proxy etc. Documented data
    # limitation in MacMahon 1990 *Lancet* 335:765 (regression dilution
    # bias from single-occasion BP measurement attenuating the BP-CHD
    # association ~60%); Hernán & Robins *What If* §9 (classification
    # error in self-reported smoking dilutes the smoking-CVD effect);
    # Fuller 1987 *Measurement Error Models*. Themis is uniquely
    # positioned to surface this because it owns the variable schema
    # ((measurement, observability) are first-class fields a regression
    # tool wouldn't see). Suppressed when extensions.ambiguities[*]
    # already declared kind=='measurement_quality' (user/upstream LLM
    # has already named it — case 011's escape-hatch path). Severity
    # IMPORTANT: regression-dilution / non-differential mis-classification
    # biases the estimate; this is identification-impacting, not just
    # informational caveat. Board #8 (measurement error) was 0% before
    # this kind landed. No external library structure-routes this from
    # variable-level measurement metadata.
    MEASUREMENT_ERROR_CONCERN = "measurement_error_concern"
    # The implicit half of selection bias — distinct from
    # COLLIDER_CONDITIONING_OPENS_BACKDOOR which fires on EffectQuery
    # `given` containing a collider that the user explicitly conditions
    # on. This kind fires on the structurally-different *implicit
    # selection* case: an ObservationStatement on some node W (i.e. the
    # study sample is restricted to subjects with W=value), where W has
    # both X (intervention) and Y (target) as directed ancestors. The
    # restriction conditions on a collider implicitly — the data
    # generating process the user is about to estimate from is
    # P(Y|X, W=w_observed), not P(Y|X), and that conditioning OPENS
    # a non-causal X→…→W←…←Y path per Pearl d-separation. Canonical
    # documented case: Hernán, Hernández-Díaz & Robins 2004
    # *Epidemiology* 15:615 "A Structural Approach to Selection Bias"
    # — Figure 3-style HIV/AZT → AIDS-death study where eligibility for
    # follow-up is itself a function of both treatment and outcome.
    # Severity IMPORTANT — this is identification damage (the marginal
    # effect estimate from the restricted sample is contaminated by a
    # collider-induced association), NOT just a caveat. Distinct from
    # SelectionNode (Phase 9 §T9.1, transport diagram for
    # heterogeneous source populations) — selection-on-collider is
    # bias *within* a single sample restricted by a downstream
    # collider, not transport across populations. No external library
    # surfaces this from program shape; DoWhy/EconML accept the
    # restricted dataset and adjust on user-named confounders without
    # noticing the implicit V-structure on the sample-restriction node.
    SELECTION_ON_COLLIDER_OPENS_PATH = "selection_on_collider_opens_path"
    # The well-defined-intervention prerequisite: the EffectQuery's
    # intervention atom names a predicate whose
    # VariableDeclaration declares ``state_vs_event = "state"`` (the
    # variable is a habitual / persistent attribute, not a discrete
    # event), AND no ``time_window`` is declared on the same predicate.
    # Per Hernán & Taubman 2008 *Int J Obesity* 32(S3):S8 "Does obesity
    # shorten life? The importance of well-defined interventions to
    # answer causal questions": when the exposure is an attribute-state
    # rather than a single act, multiple structurally-different
    # interventions can produce the same state value (e.g. "be obese"
    # achievable via overeating / lack of exercise / metabolic disease
    # / postpartum) yet entail DIFFERENT counterfactual outcomes.
    # do(state=value) without a manipulation route is therefore
    # under-defined; the consistency assumption (Hernán & Robins
    # *What If* §3.4) is silently violated. Distinct shape from
    # ``ambiguous_variable_definition`` (which fires on absent fields,
    # i.e. "you didn't say anything") — this fires on a CONTRADICTION
    # between two declared fields ("state but no duration"), where the
    # variable schema itself admits the inconsistency. Severity
    # IMPORTANT: violating consistency biases the estimand definition,
    # not the estimate of a well-defined estimand. Suppressed when the
    # user / upstream LLM has already declared
    # extensions.ambiguities[*].kind == "ill_defined_intervention" or
    # "well_defined_intervention" — escape-hatch for users who have
    # already named the issue at the A1 layer, mirroring case 011's
    # measurement_quality suppression. No external library structure-
    # routes this from variable-level state_vs_event metadata — Themis
    # advertises ``state_vs_event`` as a first-class field, and a field
    # whose VALUE no classifier reads is a distinction the schema
    # accepts and nothing acts on, which reads as coverage and is not.
    ILL_DEFINED_INTERVENTION_VERSIONS = "ill_defined_intervention_versions"
    # 2026-06-18 — dichotomization, the fourth field of that same kind,
    # after ``measurement``, the ObservationStatement and
    # ``state_vs_event``: a VariableDeclaration on
    # the identification path declares a non-empty ``threshold`` field —
    # the schema documents this as "Cutoff that turns a continuous
    # measurement into this predicate's value, e.g. >=3cm", i.e. a
    # continuous quantity was DICHOTOMIZED at a cutpoint. Pre-this-kind,
    # ``threshold``'s value was read by no classifier: its ABSENCE drove
    # ``ambiguous_variable_definition`` (you didn't operationalize), but
    # its PRESENCE — the structural fingerprint of dichotomization —
    # produced zero signal. Dichotomizing a continuous measure (1) discards
    # dose-response information and loses statistical efficiency
    # (Royston, Altman & Sauerbrei 2006 *Stat Med* 25:127 "Dichotomizing
    # continuous predictors in multiple regression: a bad idea"), (2) makes
    # results sensitive to an often-arbitrary cutpoint (data-driven
    # "optimal" cutpoints inflate type-I error; Altman et al 1994 *JNCI*),
    # and (3) when the dichotomized variable is a confounder, leaves
    # within-category RESIDUAL CONFOUNDING so the adjustment is incomplete
    # (Becher 1992 *Stat Med* 11:1747). Severity INFORMATIONAL — unlike
    # measurement_error (systematic regression-dilution) or ill_defined
    # (estimand undefined), a declared cutpoint is a known, bounded modeling
    # choice that does not break identification; the caveat informs
    # interpretation and points at Themis's own dose-response path (Phase
    # 13/14) as the continuous alternative. Must-disclose. Suppressed when
    # extensions.ambiguities[*].kind names the dichotomization explicitly
    # (escape hatch mirroring case 011's measurement_quality). No external
    # library structure-routes this from a variable-level threshold field —
    # Themis owns the variable schema where ``threshold`` is first-class.
    DICHOTOMIZED_CONTINUOUS_MEASURE = "dichotomized_continuous_measure"
    # 2026-07-11 pre-flight data diagnostic (borrow-list #3): the CSV /
    # DataFrame supplied to ``themis.estimate`` disagrees with the declared
    # measurement type of a model variable. Two shapes, both surfaced here:
    # (a) the variable positively declares ``scale`` (binary / discrete /
    # continuous) or an enumerated ``domain``, and the data violates it —
    # e.g. declared ``scale="continuous"`` but the column has only 2 distinct
    # values (so any "dose-response" estimand is really a binary contrast),
    # or declared ``domain=[true,false]`` but the column carries 5 distinct
    # values (so the g-formula silently treated a multi-level exposure as
    # continuous). (b) declared discrete ``domain`` whose data contains
    # values outside the enumerated set. Distinct from
    # dichotomized_continuous_measure (which is a program-shape signal read
    # from the ``threshold`` field, no data involved) and from
    # measurement_error_concern: this gap ONLY fires when actual data is
    # present and contradicts a POSITIVE declaration — it never fires on an
    # undeclared variable (absence of ``scale``/``domain`` is "didn't say",
    # not "said continuous"), so it is silent on every consistent program.
    # Severity IMPORTANT when the produced number answers a different
    # estimand than declared (blocks=point_estimate / interpretation); the
    # estimate is still computed on the coerced data, but the report must
    # lead with the contradiction so the number is not read as the declared
    # quantity. The reconciliation evidence (declared vs observed scale,
    # distinct-value count / set) is recorded in
    # ``extensions.type_reconciliation`` so the verifier can independently
    # re-derive the verdict. No external causal library reconciles declared
    # variable scale against supplied data — Themis owns the variable schema
    # (``scale`` / ``domain``) and the data contract, so it can.
    DECLARED_TYPE_DATA_MISMATCH = "declared_type_data_mismatch"


# The species a ``MissingItem`` is allowed to declare — the vocabulary in
# which the kernel states WHAT KIND of shortfall it hit, as opposed to
# ``MissingKind``, which states WHICH CHANNEL would repair it. The two
# axes are independent: a structure-channel item can be an unidentifiable
# estimand or a defect in the program, and one investigation action fits
# both.
#
# It is a strict subset of ``GapKind`` because most gap kinds are not
# shortfalls the kernel *runs into* — they are properties of the program
# it *inspects* (a learned graph, a low-confidence source, an assumption
# a successful strategy carries). Those are raised by reading the program
# or a strategy's own block, never by an item on this channel.
#
# ``themis.output.data_gap_report`` binds one renderer per member and
# refuses to import if any member is unbound, so a species a producer can
# name is a species that reaches the user by construction — replacing the
# residual fallback that used to catch names no classifier recognised.
MISSING_ITEM_GAPS: frozenset[GapKind] = frozenset({
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
    GapKind.MISSING_STRUCTURAL_INPUT,
    GapKind.MISSING_UNIT_OBSERVATION,
    GapKind.MISSING_DISTRIBUTION,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH,
    GapKind.MISSING_ASSUMPTION,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
})


# Whether this kind's ``description`` is copied verbatim into
# ``result.explanation`` as a ⚠ line.
#
# Saying it here rather than beside the copier is what makes the copy a
# *derived view*: ``explanation`` restates part of the gap report, so a
# pass that changes the gap list has not finished until the ⚠ lines have
# been derived again. That was true and unwritten, and a point estimate
# arriving withdrew ``answer_is_bounds_not_point_estimate`` from the gaps
# while its ⚠ line — "this is bounds, not a point estimate; the renderer
# must not present a specific number" — stayed on 246 envelopes that had
# just computed one.
#
# The two rows partition the enum and are checked below, so a kind added
# later cannot default into either by being forgotten.
MIRRORED_INTO_EXPLANATION: frozenset[GapKind] = frozenset({
    # Structural caveats: the answer cannot be read correctly without
    # them, whatever their severity. What they have in common is that
    # they qualify the answer rather than ask for anything.
    GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
    GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
    GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
    GapKind.LLM_DECLARED_AMBIGUITY,
    GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
    GapKind.LOW_CONFIDENCE_INPUT_DATA,
    GapKind.GRAPH_LEARNED_FROM_DATA,
    GapKind.UNMEASURED_CONFOUNDER_RISK,
    GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH,
    GapKind.MEASUREMENT_ERROR_CONCERN,
    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH,
    GapKind.ILL_DEFINED_INTERVENTION_VERSIONS,
    GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE,
})

# Asks. The gap report exists to carry these; restating one as a caveat
# would say "you are missing X" in the place reserved for "read the answer
# this way".
GAP_REPORT_ONLY_ASKS: frozenset[GapKind] = frozenset({
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
    GapKind.MISSING_DISTRIBUTION,
    GapKind.MISSING_POPULATION_DISTRIBUTION,
    GapKind.MISSING_ASSUMPTION,
    GapKind.MISSING_UNIT_OBSERVATION,
    GapKind.MISSING_STRUCTURAL_INPUT,
    GapKind.MISSING_IV_CANDIDATE,
    GapKind.MISSING_MEDIATOR_DATA,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
    GapKind.DOSE_RESPONSE_DATA_REQUIRED,
})

# Estimator-time findings. These DO qualify the answer, and they do reach
# ``explanation`` — but written by the estimator that found them, in its
# own words, at the moment it found them, so copying the gap description
# in as well would say each of them twice.
#
# A declared set and not a comment inside the union below, because it is
# the set a reader-facing surface has to cover: an agent pre-screening
# gaps needs a rule for every kind that reaches ``explanation``, mirrored
# or not. Named by hand in a test, this group lost two of its six — and
# the hand-list had been copied from what the prompt already said, so it
# held the prompt against itself.
ESTIMATOR_TIME_FINDINGS: frozenset[GapKind] = frozenset({
    GapKind.WEAK_IV_INSTRUMENT,
    GapKind.OVERIDENTIFICATION_REJECTED,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR,
    GapKind.PROPENSITY_OVERLAP_VIOLATION,
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION,
    GapKind.DECLARED_TYPE_DATA_MISMATCH,
})

# Not mirrored, for the two different reasons above, both of which mean
# the gap report is the only place the kind's own description is stated.
NOT_MIRRORED_INTO_EXPLANATION: frozenset[GapKind] = (
    GAP_REPORT_ONLY_ASKS | ESTIMATOR_TIME_FINDINGS
)

#: Everything that reaches ``result.explanation`` by either route. What a
#: surface written for an agent has to cover, since "no rule for this
#: kind" and "this kind never appears" are indistinguishable from there.
REACHES_EXPLANATION: frozenset[GapKind] = (
    MIRRORED_INTO_EXPLANATION | ESTIMATOR_TIME_FINDINGS
)

if MIRRORED_INTO_EXPLANATION | NOT_MIRRORED_INTO_EXPLANATION != frozenset(GapKind):
    _unclassified = frozenset(GapKind) - (
        MIRRORED_INTO_EXPLANATION | NOT_MIRRORED_INTO_EXPLANATION
    )
    _both = MIRRORED_INTO_EXPLANATION & NOT_MIRRORED_INTO_EXPLANATION
    raise ValueError(
        "every GapKind has to say whether its description is copied into "
        "explanation, because that copy is a derived view something has to "
        "keep in line: "
        + (f"unclassified {sorted(k.value for k in _unclassified)}; "
           if _unclassified else "")
        + (f"in both rows {sorted(k.value for k in _both)}" if _both else "")
    )


def mirrored_caveat_lines(gaps: "list[dict]") -> set[str]:
    """The ⚠ lines the given gap list implies, exactly as they are written.

    One reader derives them, another withdraws the ones a shrunken list no
    longer implies, and both have to agree down to the leading marker — so
    the marker is written once, here.
    """
    _mirrored = {k.value for k in MIRRORED_INTO_EXPLANATION}
    return {
        f"⚠ {gap.get('description')}"
        for gap in gaps
        if gap.get("kind") in _mirrored
    }


class GapSeverity(StrEnum):
    BLOCKING = "blocking"
    IMPORTANT = "important"
    INFORMATIONAL = "informational"


class GapBlocks(StrEnum):
    POINT_ESTIMATE = "point_estimate"
    BOUNDS = "bounds"
    IDENTIFICATION = "identification"
    INTERPRETATION = "interpretation"
    TRANSPORT = "transport"


class GapRefKind(StrEnum):
    DERIVATION_STEP = "derivation_step"
    INVESTIGATION_REQUEST = "investigation_request"
    FRAMING_NOTE = "framing_note"
    VERIFIER_CHECK = "verifier_check"


class RequiredDataType(StrEnum):
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
class GapRoute:
    """One way past a gap: which route, and this occasion's facts.

    The three fields a shortfall carries (:class:`MissingItem`), one
    channel over, and here for a sharper reason than symmetry. This was a
    finished sentence, so a route's IDENTITY was its rendered text — and
    three passes have to identify one: the report withdraws the interval
    offer a NONE tier just ruled out, it replaces "go find an instrument"
    where an instrument already produced the interval, and the scheduler
    collapses a static bounds promise into a pointer at the computed one.
    Each did it by rebuilding the string, or by searching for substrings
    of it, which made the WORDING of a user-facing sentence an input to
    kernel control flow: one of those replacements carried a note saying
    it was deliberately worded to avoid the three substrings the other
    pass greps for.
    """
    route: "Route"
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, dict] = field(default_factory=dict)


@dataclass(frozen=True)
class DataGap:
    """A single data / assumption / structural shortfall blocking some
    downstream output.

    ``said`` and ``words`` are what THIS occasion is about — which
    collider, which intervention, which two layers the dispatcher had to
    choose between — split the way :func:`themis.language.halve` splits
    them: a value renders the same in every language and travels rendered,
    a word's text IS the language and travels as its set and its token.

    One pair for the gap rather than one per sentence, because the facts
    belong to the OCCASION and not to any one telling of it. Two sentences
    of the same species draw on the same facts and, where they name the
    same slot, mean the same thing by it — measured across every producer
    before the pair was put here, at zero disagreements.

    ``if_provided`` stood here and held a finished sentence saying what
    having the missing thing would buy. It was a function of ``kind``: 21
    producers, 17 templates, and every species always carrying one or
    never carrying one, with no site disagreeing. So it was a table the
    kernel already had, rendered at kernel time in whichever language was
    passed — see :data:`themis.gaps.IF_PROVIDED`, and
    :data:`themis.gaps.NOTHING_FILLS` for the species where the honest
    answer is that nothing supplied changes it.
    """
    kind: GapKind
    severity: GapSeverity
    description: str
    blocks: GapBlocks
    provenance: tuple[GapProvenanceRef, ...]
    signature: str | None = None
    required_data: GapRequiredData | None = None
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, dict] = field(default_factory=dict)
    alternative_paths: tuple[GapRoute, ...] = ()


class AnswerTier(StrEnum):
    """The strongest answer the kernel can hand back for a question that
    names an estimand (``questions.Question.names_an_estimand`` — every
    kind but ``cause`` and ``assoc``), stated explicitly so consumers do
    not have to infer it from gap-severity ordering.

    This axis is ORTHOGONAL to gap severity: severity says "how blocking
    is this gap to its own goal"; answer_tier says "what can I still
    return". For an unidentifiable effect with informative IV / Manski
    bounds, the top gap is severity=blocking (point ID truly failed) yet
    answer_tier=INTERVAL — the consumer has a usable interval, not a dead
    end. Without this field that good news is buried under a blocking gap.
    """
    POINT = "point"        # point estimand identified (possibly pending θ)
    INTERVAL = "interval"  # point ID blocked, informative bounds available
    NONE = "none"          # neither — needs an assumption / stronger data


@dataclass(frozen=True)
class DataGapReport:
    """Phase 10 top-level summary of what data / assumptions / structural
    changes are still needed. Gaps are sorted by severity (blocking >
    important > informational), then by derivation order.

    ``answer_tier`` (set for every question that names an estimand; None
    for ``cause`` / ``assoc``, which ask about the graph) names the
    strongest answer available, orthogonal to the gaps' severities — see
    ``AnswerTier``.

    ``actionable_next_steps`` stood here and was a list of finished
    sentences — "supply X", "or: Y" — one per gap worth acting on. Every
    input to it is on this object already (which gaps block, which have
    somewhere else to go, and what each is short of, by
    :data:`themis.gaps.WANTED`), so it carried no fact of its own and was a
    rendering the kernel had grown: the schema described its entries as
    Chinese, and two modules with no rendering business — the dispatcher
    re-deriving it after dropping a gap, the scheduler reordering
    ``alternative_paths`` to steer what its first line showed — were
    keeping it true. Each reader assembles it now, in the language it is
    answering in."""
    summary: str
    gaps: tuple[DataGap, ...]
    answer_tier: "AnswerTier | None" = None


@dataclass(frozen=True)
class DispatchRecord:
    """Which strategy answered, and which ones it took the query from.

    Written by the dispatcher at the moment it picks a winner, because
    that is the only moment the losers are known: the cascade returns at
    the first row whose guard holds, so a row below it that would also
    have claimed the query is never evaluated and leaves no trace. The gap
    report used to recover that fact by reading which extension came back
    non-empty — an inference from residue, and wrong the first time a
    layer fills its extension and then fails.

    Deliberately not serialized. The disclosure a reader needs is the gap
    this record produces, which names both layers in prose; putting the
    route ids in the envelope beside it would be the same fact in two
    places, and the ids name implementations rather than anything a reader
    reads. See :mod:`themis.routing` for the declarations behind it.
    """
    answered_by: str
    displaced: tuple[str, ...] = ()


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
    # Phase 12 — symbolic bounds. A SET, because the methods here bound the
    # same estimand under assumption sets that do not contain one another,
    # and a slot holding one of them holds whichever ran first. See
    # ``_attach_bounds_results``.
    bounds_results: "tuple[BoundsResult, ...]" = ()
    # Why no number came out. The result schema has carried this at the
    # top level all along; this type did not, so identification — which
    # returns a result rather than raising for dispatch to catch — had
    # nowhere to put a reason and wrote prose into ``extensions``
    # instead. Assembled by :func:`themis.refusals.block`.
    estimator_failure: dict | None = None
    # Who answered and whom they displaced — see :class:`DispatchRecord`.
    dispatch: "DispatchRecord | None" = None


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


class BoundsMethod(StrEnum):
    # Implemented and reachable from runtime / output.bounds:
    MANSKI_NATURAL = "manski_natural"
    BALKE_PEARL_IV = "balke_pearl_iv"
    # Stub slots — declared so future implementations don't churn the
    # enum, but currently NEITHER reachable from runtime NOR backed
    # by a builder. Adding either is a real-case-driven follow-up:
    # implement only when a query actually surfaces a graph that
    # would benefit from tighter bounds than Manski-natural can give.
    # Per CLAUDE.md "don't design for hypothetical future requirements"
    # — speculative implementation is explicitly out of scope.
    FRONTDOOR_PARTIAL = "frontdoor_partial"  # Tian 2002 partial front-door
    MANSKI_TAMER_MONOTONICITY = "manski_tamer_monotonicity"  # under outcome monotonicity


@dataclass(frozen=True)
class BoundsResult:
    """Symbolic bounds on the queried estimand.

    `lower_expression` and `upper_expression` are what a reader is shown,
    and only that. Nothing evaluates them: the numeric end dispatches on
    ``method`` and recomputes from the data, and it always did — the
    sentence promising that a future numeric layer would evaluate them
    outlived the layer arriving.

    Which matters because they are not all the same kind of thing. Two
    methods have a closed form and print it (``max(0, P(Y=1|X=1) -
    P(X=0))``); Balke-Pearl's bound is the optimum of a linear programme
    with no closed form at a general cardinality, so that branch prints
    the programme in words. Both are honest renderings. What is not
    honest is carrying a FACT in one — the instrument the programme is
    fitted around lived only inside that sentence, so the audit that had
    to confirm it read the sentence with a regular expression, and the
    row's own rendering became something a rewording could break.

    `width_when_uninformative` flag is True when the bounds reduce to
    the trivial [-1, 1] / [0, 1] range — the answer is honest but
    useless, so the renderer warns the user.

    `assumptions` lists what the method requires (e.g. Manski has none;
    Balke-Pearl needs IV1/IV2/IV3). `data_required` lists the observable
    distributions a client would need to evaluate the expressions.

    `estimand` names WHAT the two endpoints bound. An interval is not an
    answer until the quantity it brackets is stated, and the methods here
    do not all bracket the same one — so the symbolic result carries the
    name from the moment it is built rather than acquiring it only if a
    numeric end later runs. It has no default: a method that cannot say
    which quantity it brackets has not finished being a method.
    """
    method: BoundsMethod
    lower_expression: str
    upper_expression: str
    estimand: str
    assumptions: tuple[str, ...] = ()
    data_required: tuple[str, ...] = ()
    width_when_uninformative: bool = False
    notes: str | None = None
    #: The instrument the bound is taken around, where the method uses
    #: one. A fact rather than a phrase, so the audit can check it
    #: against the graph instead of parsing the sentence that names it —
    #: and so the sentence can be reworded without breaking the audit.
    #: ``None`` for the methods that need no instrument.
    #:
    #: Not a new key on the row: the numeric end has always written this
    #: one, and the schema declared it as the numeric end's. Describing a
    #: field by who wrote it is what hid it from the writer that did not
    #: yet exist — this is that writer, and there is one field.
    instrument: str | None = None
