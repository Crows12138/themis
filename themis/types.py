"""Core data types shared across all layers.

These mirror the JSON Schema definitions in atom.schema.json,
kernel_ast.schema.json, and query_result.schema.json.

All dataclasses are frozen so values can be hashed and compared
structurally; the runtime treats them as immutable.
"""
from __future__ import annotations

import json
import math
from collections.abc import Sequence
from dataclasses import (
    dataclass, field, fields as dc_fields, is_dataclass, replace as dc_replace,
)
from enum import StrEnum
from typing import TYPE_CHECKING, Union

import numpy as np

if TYPE_CHECKING:  # the species a shortfall names; its module imports this one
    from .gaps import Need, Route, Sentence
    # Which way a treatment may move an outcome. It carries its own words
    # now, and a vocabulary that does cannot live here: the module holding
    # that machinery imports this one. Only annotations need it, and an
    # annotation is a string.
    from .ledger import Monotonicity


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

#: What one word-shaped hole in a sentence holds as it travels: a
#: statement, or a list of them. Declared here rather than beside the door
#: that writes it because these dataclasses are what carry it and this
#: module is the one they can both see; spelled with ``dict`` rather than
#: with that door's own type because the type is the WRITER's evidence of
#: intent and what comes back off an envelope is a plain mapping.
Spoken = dict | list


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


@dataclass(frozen=True)
class FeedbackLoop:
    """#450: the caller says these two atoms cause each other.

    A DAG cannot hold that, and until this statement existed the
    declaration had nowhere to land: the LLM wrote ``reciprocal_causation``
    into ``extensions.ambiguities`` as prose, which names no atoms, so no
    handler could be written for it — the kernel picked whichever direction
    had been drawn and answered as though the other did not exist.

    Like :class:`BidirectedStatement` and :class:`SelectionNode`, this does
    not enter G(M). It adds no edge; the graph stays acyclic. What it does
    is WITHDRAW: an estimand the loop can still reach after the intervention
    is not the estimand the DAG computes, because adjusting for observed
    covariates cannot remove a feedback the treatment is part of.

    ``left`` and ``right`` are syntactic slots — the loop is unordered, both
    directions being asserted.

    Scope, and it is a condition on the answer rather than an
    implementation detail: this is an INSTANTANEOUS loop, the
    simultaneous-equations case (Haavelmo 1943). Feedback that resolves in
    time — ``A`` at t moving ``L`` at t+1 moving ``A`` at t+2 — is not a
    cycle at all once the time index is written down, and the ordinary
    ``cause`` edges express it; declaring it here instead would throw away
    the resolution that makes it identifiable.
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
class ProxyCoarsening:
    """Which observed levels of each proxy stand for ONE state of the latent U.

    Miao's formula (5) inverts a ``k×k`` measurement channel, so a proxy with
    more than ``k`` observed levels has to be recoded down to ``k`` before the
    channel exists. Grouping levels is sound — a conditional independence
    survives any function of the variable it holds for, so ``g(Z)`` still
    satisfies the model-(f) criteria — and in the population every grouping
    whose folded channel keeps full rank identifies the same effect. In a
    finite sample they do not: a different grouping is a different M and a
    different number.

    **Which is why it is declared and not inferred.** Nothing in the data
    says that levels 2 and 3 of a four-level proxy are the same state of a
    variable nobody observed; that is a claim about what the instrument
    measures, and the estimator will not make it on the caller's behalf. A
    proxy whose level count does not match ``k`` and carries no grouping is
    refused, with the missing declaration named — see
    ``GapKind.PROXY_COARSENING_UNDECLARED``.

    Groups-as-lists rather than a level-to-index map so that the arity is the
    length of the field and "every group has something in it" is a property
    of the shape. Both proxies are named even when only one needs regrouping:
    the identity grouping is cheap to write, and a declaration that states
    both axes says what the k columns of M are without anyone having to
    consult the data to find out.
    """
    treatment_proxy: tuple[tuple[AtomValue, ...], ...]
    outcome_proxy: tuple[tuple[AtomValue, ...], ...]


@dataclass(frozen=True)
class DiscreteChannel:
    """Read the proxies as a ``k×k`` measurement channel and invert it.

    Miao's formula (5). ``latent_cardinality`` is the assumed number ``k`` of
    categories of ``U`` — the strongest assumption in the method, since U is
    never seen and its cardinality must still be posited. Identification is
    then a linear solve, and what can fail is the rank condition.
    """
    latent_cardinality: int
    #: How to read a proxy with more observed levels than ``k``. Absent is
    #: the identity grouping, and therefore also the statement that each
    #: proxy is expected to present exactly ``k`` levels on its own — see
    #: :class:`ProxyCoarsening` for why this is the caller's to say.
    proxy_coarsening: "ProxyCoarsening | None" = None


class BasisFamily(EnvelopeName):
    """Which functions the bridge is assumed to be a combination of.

    A closed vocabulary because it is half of an assumption: the bridge is
    identified only if it lies in the span, so naming the family is naming
    what was assumed, and a family nobody declared is an assumption nobody
    made. More than one member on purpose — a choice with a single option
    is not a choice, and the provenance beside it would be saying the
    caller chose something they could not have chosen otherwise.

    Every member here spans the constant, and spans it with a non-zero
    coefficient on its FIRST column. That is not a coincidence to rely on
    quietly: a sieve design lays several of these side by side and takes
    one constant out of each so the whole design keeps exactly one, and a
    family that reached the constant some other way would make that
    subtraction change the span rather than deduplicate it.

    What separates the members is what each buys, because a member nobody
    has a reason to choose is a choice nobody can make:
    """

    #: Powers of the standardised proxy. Global support: every observation
    #: moves every coefficient, which is what makes a high degree both
    #: expressive and badly conditioned.
    POLYNOMIAL = "polynomial"
    #: Hat functions on sample quantiles. Local support, so a heavy tail
    #: cannot pull the fit in the middle.
    PIECEWISE_LINEAR = "piecewise_linear"
    #: Cubic B-splines on a clamped knot vector — the same local support as
    #: the hats, twice differentiable across the knots. A TRADE against
    #: them rather than an improvement on them, and both directions were
    #: measured: at equal width this span reaches a smooth target several
    #: times more closely, the hats reach a kinked one more closely, and
    #: the hats are about an order of magnitude better conditioned. So it
    #: is the family for a bridge believed smooth, and the wrong one for a
    #: bridge with a corner in it. The hats ARE the degree-one member of
    #: this family, kept under their own name because a degree field would
    #: sit on every factor and mean nothing on three of the five.
    CUBIC_SPLINE = "cubic_spline"
    #: Sines and cosines on the observed range. Declaring this ASSERTS
    #: periodicity — the span it names is the functions that come back to
    #: where they started — so it is the right family for an angle, a time
    #: of day or a season, and the wrong one for anything with two open
    #: ends, where it forces the two together.
    FOURIER = "fourier"
    #: Probabilists' Hermite polynomials, normalised. The same span as the
    #: powers at the same dimension and a far better conditioned one: they
    #: are orthogonal under the standard normal weight, so a roughly
    #: bell-shaped proxy gives a near-identity Gram matrix where raw powers
    #: give a Vandermonde. For an ILL-POSED problem that is not a tidiness
    #: argument — conditioning is the thing being fought.
    HERMITE = "hermite"


#: The narrowest sieve each family can be, and why it is not always two.
#:
#: A cubic B-spline needs four functions before it is cubic at all — with
#: fewer, the clamped knot vector has no room for the degree. The others
#: are defined at any width, and saying so here rather than in the
#: estimator is what lets the door refuse an impossible declaration before
#: a matrix is built out of it.
SIEVE_MINIMUM_DIMENSION: "dict[BasisFamily, int]" = {
    BasisFamily.POLYNOMIAL: 2,
    BasisFamily.PIECEWISE_LINEAR: 2,
    BasisFamily.CUBIC_SPLINE: 4,
    BasisFamily.FOURIER: 2,
    BasisFamily.HERMITE: 2,
}


@dataclass(frozen=True)
class SieveFactor:
    """One variable, expanded by one basis at one dimension.

    The smallest thing a sieve can be told. Separate from the term that
    holds it because a term over two variables needs a family and a
    dimension for EACH of them: a three-level stratifier and a continuous
    proxy do not want the same expansion, and one pair of numbers for the
    whole term could only say they do.
    """

    variable: Atom
    basis: BasisFamily
    dimension: int


@dataclass(frozen=True)
class SieveTerm:
    """One block of a design matrix: the tensor product of its factors.

    A term over a single variable is that variable's basis. A term over
    several is every product of one column from each, which is what lets a
    bridge differ BY a stratifier rather than merely be shifted by it —
    ``h`` interacted with age is a different function of the proxy in each
    age band, and ``h`` plus age is the same function moved up or down.
    The distinction is the caller's to make because it is an assumption
    about the bridge, and the additive one is the stronger claim.

    Dimensions multiply within a term and add across terms, which is the
    whole reason terms exist as a list: the additive arrangement is how a
    sieve stays estimable once more than one variable is in it, and a
    single tensor product over everything is the arrangement that does not.
    """

    factors: tuple[SieveFactor, ...]

    @property
    def width(self) -> int:
        """Columns this term contributes, before the shared constant is
        removed once for the whole design."""
        product = 1
        for factor in self.factors:
            product *= factor.dimension
        return product


@dataclass(frozen=True)
class BridgeFunction:
    """One bridge: the span it is assumed to lie in, and where it is tested.

    Proximal inference has two of these and they have the same shape, which
    is why this type says SPAN and MOMENTS rather than naming a proxy role.
    The outcome bridge ``h`` is a function of ``(W, C)`` whose equation is
    asked to hold at moments of ``(Z, C)``; the treatment bridge ``q`` is a
    function of ``(Z, C)`` tested at moments of ``(W, C)``. Same object,
    roles swapped — and while the field names carried the roles, a second
    bridge had no type to be written in.

    ``span_terms`` spans the functions the bridge is assumed to be one of;
    ``moment_terms`` gives the directions its defining equation is asked to
    hold along. Both are assumptions rather than settings — the sieve
    analogue of the completeness condition — which is why neither has a
    default. How WIDE each side is follows from the terms and is therefore
    not declared: two integers a caller reports beside a design they also
    declare are two chances to disagree with it, and the rule that matters
    (at least as many moments as unknowns, or the system is under-determined
    before any penalty) is then checked against a number nobody typed. That
    rule is ONE rule read over each bridge, which is what having one type
    for both of them buys.

    Either bridge's equation is a Fredholm integral equation of the first
    kind — an ILL-POSED inverse problem, in which arbitrarily small changes
    in the observed conditional law move the solution arbitrarily far. It
    has no numeric solution without regularisation, and the regularisation
    is therefore not an implementation detail: it is a term added to the
    problem that changes the answer, by an amount nothing in the data
    settles.

    ``ridge`` is the Tikhonov parameter λ, and it is the one that MAY be
    left unsaid: unlike a function class, a penalty has a defensible default
    — one scaled to the problem's own magnitude, stabilising rather than
    claiming to be optimal. Absent, the estimator picks by that rule and the
    ledger line says nobody chose it (``Provenance.DEFAULT``); present, the
    line says the caller did (``Provenance.CALLER_CHOSE``). Either way the
    answer is re-computed across a decade either side of λ and the spread is
    reported beside it, because a number that moves under the penalty more
    than it moves under sampling noise is a property of the penalty. Each
    bridge carries its own λ because each is its own ill-posed solve.
    """
    #: The span this bridge is assumed to lie in — ``b(W, C)`` for ``h``,
    #: ``g(Z, C)`` for ``q``.
    span_terms: tuple[SieveTerm, ...]
    #: The directions its equation is asked to hold along — ``a(Z, C)`` for
    #: ``h``, ``n(W, C)`` for ``q``.
    moment_terms: tuple[SieveTerm, ...]
    #: λ ≥ 0, or ``None`` for the estimator's stabilising rule.
    ridge: float | None = None

    @property
    def span_width(self) -> int:
        """Unknowns: one constant, plus what each term adds once its own copy
        of the constant is taken out."""
        return width_of(self.span_terms)

    @property
    def moment_width(self) -> int:
        """Equations available to pin them down, counted the same way."""
        return width_of(self.moment_terms)


class ProximalEstimator(EnvelopeName):
    """Which of the three answers the two bridges can give is the answer.

    Cui, Pu, Miao, Zhang & Tchetgen Tchetgen 2024 (JASA 119(546)) derives
    all three from the same pair of bridges, and they are not three spellings
    of one number: each is consistent under a DIFFERENT assumption, so
    naming one is naming what has to be true for the answer to be right.

    A closed vocabulary and not a flag, because the third member's whole
    content is a claim about the other two.
    """

    #: ``E[h(W,1,C)] − E[h(W,0,C)]``. Right if the outcome bridge's span
    #: contains the true ``h``; wrong, with nothing to catch it, if not.
    #: The only one available before there was a second bridge, and the
    #: default for that reason — it asks for strictly less than the others.
    OUTCOME_REGRESSION = "outcome_regression"
    #: ``Pn[(−1)^{1−A} q(Z,A,C) Y]``. Right if the TREATMENT bridge's span
    #: contains the true ``q``, and it does not consult ``h`` at all. Worth
    #: having beside the doubly robust one rather than folded into it:
    #: this is the estimator that visibly fails when ``q`` is wrong, and a
    #: caller comparing it against the outcome regression is reading the
    #: two assumptions against each other.
    INVERSE_PROBABILITY = "inverse_probability"
    #: The augmented combination, consistent if EITHER span is right —
    #: Theorem 3.2's union model. Not strictly better and so not the
    #: default: it needs a second design declared, and where both spans are
    #: wrong it is wrong too, which is the honest behaviour and not a
    #: safety net.
    DOUBLY_ROBUST = "doubly_robust"


@dataclass(frozen=True)
class BridgeChannel:
    """The bridges a query declared, and which of their answers it wants.

    Two bridges rather than one because an estimator that is robust in one
    direction only is not doubly robust, and one bridge cannot be robust to
    itself. Which is not the same as saying both are always needed: a caller
    who wants the outcome regression declares one, and the field for the
    other stays empty rather than being filled with a copy.

    The two bridges must not be each other's mirror — ``q`` spanning what
    ``h`` takes moments along and vice versa. Under the rule that each
    bridge have at least as many moments as unknowns, that arrangement
    forces both systems square, and two square systems built from one pair
    of designs solve to the same answer: the three estimators collapse to
    one number and the union model buys nothing. That is refused at the
    door rather than reported afterwards, because a caller who asked for
    double robustness and received a single estimate under a second name
    has not been told anything by receiving it.
    """

    #: ``h`` — spans ``(W, C)``, tested at moments of ``(Z, C)``.
    outcome_bridge: BridgeFunction
    #: ``q`` — spans ``(Z, C)``, tested at moments of ``(W, C)``. Absent
    #: exactly when the outcome regression is the estimator asked for.
    treatment_bridge: "BridgeFunction | None" = None
    #: Which answer is THE answer. Defaults to the one that needs only the
    #: outcome bridge, so a program written before there was a second one
    #: still says what it meant.
    estimator: ProximalEstimator = ProximalEstimator.OUTCOME_REGRESSION


def width_of(terms: "Sequence[SieveTerm]") -> int:
    """How many columns a list of terms builds.

    One shared constant plus each term's own width less one. Every family
    here spans the constant on its own — powers start at ``t⁰`` and hat
    functions sum to one everywhere — so terms laid side by side would
    contribute one copy of it each, and a design matrix with the constant in
    it twice is singular before any data arrives. Removing it per term and
    restoring it once is the standard reference-level arrangement, and it
    leaves the span untouched.

    Written here rather than in the estimator because the semantic validator
    has to count the same columns to refuse an under-determined system, and
    the estimator must not be imported to read a program.
    """
    return 1 + sum(term.width - 1 for term in terms)


#: How the proxies are turned into an answer. Two shapes rather than one
#: shape with optional halves: ``latent_cardinality`` used to be a required
#: field of the query itself, which made "how many states U has" and "which
#: algebra identifies the effect" the same declaration. They coincide in the
#: discrete regime — k is both the assumption and the matrix's size — and
#: they come apart in the continuous one, where U's cardinality is not
#: assumed at all. While they shared a field a continuous proxy had nowhere
#: to go but the discrete hole, and Themis answered a caller with three
#: thousand distinct floats by asking them to say which of those floats are
#: the same state of U.
ProximalChannel = Union[DiscreteChannel, BridgeChannel]


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
    unobserved. Structurally the kernel decides identifiability via
    ``runtime.proximal_identify.identify_proximal`` (Miao model (f): the proxy
    criteria W⊥(Z,X)|(U,C) and Z⊥Y|(U,X,C) plus {U,C} a sufficient confounder),
    and that decision is the SAME either way ``channel`` reads: the graph
    condition is model (f) in both regimes, and what changes is which data
    condition the graph cannot discharge — a rank condition on a finite
    channel, or the completeness of an integral operator. This is the escape
    hatch one rung past back-door / front-door / general-ID, all of which
    assume the confounders on the relevant paths are observed.

    Both proxy roles are SETS. One source of confounding rarely has one
    shadow — a study that has bone density and grip strength as negative
    controls for underlying frailty has two of them — and asking such a
    caller to pick one throws away the half that would have identified what
    the other misses. Set separation is pairwise separation for a fixed
    conditioning set, so model (f) is the same criterion read over more
    pairs, not a second criterion.

    ``covariates`` are OBSERVED and therefore not proxies of anything: they
    join the conditioning set, so every statement above is read within a
    level of C, and the effect is averaged over C at the end. They are what
    makes "stratify by age and sex, then run proximal inside the stratum"
    sayable at all.
    """
    treatment: Atom
    outcome: Atom
    latent: Atom
    #: Z — one or more treatment-inducing proxies (negative-control exposures).
    treatment_proxy: tuple[Atom, ...]
    #: W — one or more outcome-inducing proxies (negative-control outcomes).
    outcome_proxy: tuple[Atom, ...]
    #: Which algebra recovers the effect from the proxies — and therefore
    #: which parameters this query has to carry. See :data:`ProximalChannel`.
    channel: ProximalChannel
    #: C — observed variables conditioned on throughout. Empty is the
    #: unstratified question, which is what every proximal query was until
    #: there was somewhere to put these.
    covariates: tuple[Atom, ...] = ()


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


def atoms_named_by(query: Query) -> tuple[Atom, ...]:
    """Every variable a question names, read off the question itself.

    A question's variables are the atoms it holds: the treatment, the
    outcome, what it conditions on, a mediator, a second intervention, a
    proxy, the latent a proximal question is written around. This walks
    the query for them instead of listing which field of which kind holds
    one, and the difference is not tidiness. A list of those is a list of
    what its author remembered — the version this replaced named six of
    the ten kinds, and inside the kind it named most carefully it missed
    the mediator and the second treatment. Every kind it did not name got
    an empty tuple, which on the reader's surface is indistinguishable
    from a program whose variables are all fully defined: forty-nine
    answers in the suite's own corpus named an under-defined variable and
    were told nothing about it.

    Deduplicated by predicate and ordered by where the question puts it,
    so two questions naming the same variable twice say it once, and the
    order a reader is shown is the order it was asked in.
    """
    seen: dict[str, Atom] = {}
    for atom in atoms_held_by(query):
        seen.setdefault(atom.predicate, atom)
    return tuple(seen.values())


def atoms_held_by(query: Query) -> tuple[Atom, ...]:
    """Every atom a question holds, each once, in the order it holds them.

    What :func:`atoms_named_by` is read from. There a variable is a
    predicate, and ``x`` a step back and ``x`` now are one of them. On the
    ground graph a question is answered on they are two nodes, and a
    question naming both rests on the paths between them, so a reading of
    what it rests on takes the atoms themselves.
    """
    seen: dict[Atom, None] = {}
    walked: set[int] = set()

    def walk(node: object) -> None:
        if node is None or id(node) in walked:
            return
        walked.add(id(node))
        if isinstance(node, Atom):
            seen.setdefault(node)
            return
        if is_dataclass(node) and not isinstance(node, type):
            for f in dc_fields(node):
                walk(getattr(node, f.name))
            return
        if isinstance(node, (tuple, list, set, frozenset)):
            for item in node:
                walk(item)
            return
        # Anything else a question holds is a word, a number or a choice
        # from a vocabulary, and none of those is a variable.

    walk(query)
    return tuple(seen)


def atoms_the_graph_is_asked_about(query: Query) -> tuple[Atom, ...]:
    """Every atom a question needs the working graph to hold as a node.

    Every atom it holds, whichever field holds it, except where the
    question is a probability: that is a lookup in the declared
    distribution, asks the graph nothing, and may name atoms no cause
    statement mentions.

    One reading for the three places that ask it. The projection admits a
    declared atom with no edge as a node when a question names it, the
    validator refuses a program whose question names an atom that is no
    node, and each dispatcher refuses the same before it tries a route.
    Each had written its own list of which fields hold one. None listed
    the mediator block, the projection and the validator left out the
    mediator as well, and the projection left out the causation kind. The
    framing check reads the walk, so a declared mediator in no edge was a
    variable an answer told its reader to define and a node the graph did
    not have: the verifier, reading this problem's names off the graph,
    refused the honest answer. And an undeclared one got past the
    validator that refuses an undeclared treatment, to be refused further
    on as a different fault.
    """
    if isinstance(query, ProbabilityQuery):
        return ()
    return atoms_held_by(query)


def ends_the_given_holds(query: Query) -> tuple[Atom, ...]:
    """What a question conditions on that is its own treatment or outcome.

    Holding the treatment fixed beside setting it, or the outcome beside
    asking for it, is no stratum an effect could be asked of, and no graph
    identifies it or fails to. So it is refused before any route is offered
    the question, and alike for the two spellings of the estimand: the
    identify query refused it and the effect query sent it down the routes,
    to come back as an effect the graph does not identify.

    A descendant of the treatment is not among these. Whether conditioning
    on one leaves the effect identified is the identifier's to decide, and
    a check in front of it that refused every descendant refused questions
    it answers.
    """
    if isinstance(query, IdentifyQuery):
        ends = {query.intervention.atom, query.target}
        given: tuple[Atom, ...] = query.given
    elif isinstance(query, EffectQuery):
        ends = {query.intervention.atom, query.target.atom,
                *(iv.atom for iv in query.extra_interventions)}
        given = tuple(v.atom for v in query.given)
    else:
        return ()
    return tuple(dict.fromkeys(a for a in given if a in ends))


@dataclass(frozen=True)
class QueryStatement:
    id: str
    query: Query


@dataclass(frozen=True)
class VariableDeclaration:
    """Slice A0 advisory framing metadata, attached to a predicate.

    All fields except ``predicate`` are optional; unset framing fields
    become framing gaps on any query that references this predicate, and
    omitting the declaration entirely silences framing for that predicate.

    Every field here was advisory until ``censoring``, which is not, and
    the line between them is the thing to keep: a framing field says how
    a well-defined quantity was operationalised, and ``censoring`` says
    the recorded column is not that quantity at all. Advisory, it would
    be advice attached to an answer already wrong.

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
    # The framing fields whose question the author saw and answered with
    # "take the standard operationalisation" rather than by naming one.
    # A third state, and the one the fields above cannot hold: unset means
    # nobody has considered the question, a value means somebody named one,
    # and neither of those is what an author does when they accept the
    # default. It used to be written into the value — four of the seven
    # defaults were sentences saying "not specified", authored so that
    # ``framing_check``'s ``is None`` would read false. A value whose only
    # job is to be present is a flag with no slot, and every consumer of
    # the fact underneath it became a reader of prose: fixed to one
    # language, held in a second copy, recognised by substring. Three of
    # the seven could not be recognised at all, their defaults being real
    # choices an author might have named. Said here, the fact is the same
    # for all seven, and it belongs to the program rather than to whichever
    # surface filled the blank.
    defaulted: tuple[str, ...] = ()
    # 2026-09-01. A POSITIVE declaration that this variable is a follow-up
    # time and not a measurement. The one field here that DOES gate
    # reasoning, and it is the exception rather than a drift: the others
    # say how a well-defined quantity was operationalised, and this one
    # says the recorded column is not the quantity at all. Left advisory
    # it would be advisory about an answer already wrong — the recorded
    # column is min(event, end of follow-up), and averaging it understates
    # the effect by however much of the tail nobody watched.
    censoring: "Censoring | None" = None


@dataclass(frozen=True)
class Censoring:
    """Which column says the event was seen, and how far to ask.

    ``horizon`` is optional here and required by the estimator, and the
    asymmetry is deliberate. A program that names the indicator without a
    horizon is well-formed — it has said the true thing about the column —
    and what it is missing is the other half of the QUESTION, which the
    refusal explains in a sentence a reader can act on. A required field
    would report the same fact as a schema violation, which teaches
    nobody why a censored variable has no unrestricted mean.
    """

    event_indicator: str
    horizon: float | None = None


Statement = Union[
    CauseStatement,
    BidirectedStatement,
    FeedbackLoop,
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


class Shown(StrEnum):
    """What an answer can be showing, coarsely enough for a word to claim it.

    The vocabulary :data:`STATUS_CLAIMS` is written in. Coarse on purpose:
    WHERE a number lives is a fact about the query kind — a joint contrast,
    a dose-response curve and three probabilities of causation each keep
    theirs under a key of their own — and a status is not a claim about
    that. It is a claim about whether the run got one.
    """

    POINT = "point"
    INTERVAL = "interval"
    NUMBER = "number"
    STRUCTURE = "structure"
    CHAIN = "chain"


#: Any of the three ways a quantity can be on the envelope, which is the
#: only grain at which a word may be made to PROMISE one.
#:
#: The two halves of a claim have opposite exposures, and the difference
#: decides how fine each may be written. A denial is read against a list
#: of places a rung can live, so a list that is short misses a lie and
#: cannot invent one. A promise read against the same short list refuses
#: an answer that kept its number somewhere the list forgot — and a rule
#: that refuses an honest answer is worse than the hole it closes.
#:
#: So a promise may only be written where the reading behind it is total.
#: "Some quantity is on the envelope" is total, because the blocks that
#: carry one are declared in :class:`themis.blocks.Family`. Which SHAPE it
#: took is not: an Anderson-Rubin region projects an interval per
#: coefficient and a linear-SCM counterfactual is a bare point, and both
#: keep it under a key of their own that no shape-level reading enumerates
#: without becoming a list of the answers its author happened to see.
A_QUANTITY: frozenset[Shown] = frozenset(
    {Shown.POINT, Shown.INTERVAL, Shown.NUMBER})


@dataclass(frozen=True)
class StatusClaim:
    """What has to be true of an answer for one status to be true of it.

    ``carries`` is a tuple of requirements and each requirement is
    satisfied by ANY of its members: a numerically solved answer shows a
    number, and an Anderson-Rubin region is a number the estimate blocks
    have no room for. ``withholds`` is the other half and the sharper one
    — a word that denies a rung the envelope plainly shows is the lie a
    reader has no way to see, because they are reading the word.

    They are also held to different standards of evidence, for the reason
    :data:`A_QUANTITY` gives: a promise is only as good as the totality of
    the reading behind it, and a denial is safe when that reading is short.
    """

    carries: tuple[frozenset[Shown], ...] = ()
    withholds: frozenset[Shown] = frozenset()


#: What each word an answer leads with claims about the answer.
#:
#: ``ResultStatus`` was a bare enum: seven strings, and what each of them
#: asserts written nowhere. Everything else in this package that reaches a
#: reader carries its meaning beside it — a route, a species and a sentence
#: are declared with what they say — and the consequence of this one not
#: being is that nothing could hold it. ``verify`` ROUTES on status, so it
#: was a premise of the audit rather than something the audit asks about,
#: which is the sentence #568 wrote about ``query_kind`` and ``answer_tier``
#: with this one named and left.
#:
#: What the words mean is not read off the corpus. It is read off the
#: words: "structurally solved" says a structure was reached and a number
#: was not, "outside language" says nothing was. The corpus is where that
#: reading is CHECKED — 243 answers, no exceptions — and where a claim that
#: does not survive it gets withdrawn rather than weakened. Two are absent
#: on purpose: ``numerically_solved`` denies nothing, because a number and
#: a structure and an interval can all be true of one answer at once, and
#: ``counterfactual_solved`` denies nothing for the same reason.
STATUS_CLAIMS: dict[ResultStatus, StatusClaim] = {
    ResultStatus.OUTSIDE_LANGUAGE: StatusClaim(
        withholds=frozenset(Shown)),
    ResultStatus.NEEDS_INVESTIGATION: StatusClaim(
        withholds=frozenset({Shown.POINT, Shown.NUMBER})),
    # No dispatcher produces this one (see the comment on the member), so
    # the corpus cannot check it. Declared anyway, for the reason
    # gaps.NO_SPECIES_ESCAPE is: an entry is checkable and an absence
    # cannot be told from an oversight. It reads off the word — an answer
    # that works IF you grant a premise has not got a number yet.
    ResultStatus.NEEDS_ASSUMPTION: StatusClaim(
        withholds=frozenset({Shown.POINT})),
    # ``structural_result`` is where identification's answer goes and the
    # only place it goes: the route blocks beside it say how the estimand
    # was recognised, not what it came out as. So this promise is written
    # against a total reading and may name the rung itself.
    ResultStatus.STRUCTURALLY_SOLVED: StatusClaim(
        carries=(frozenset({Shown.STRUCTURE}),),
        withholds=frozenset({Shown.POINT})),
    # The three words that say a quantity arrived promise it at the grain
    # A_QUANTITY explains and no finer. What separates them is the question
    # rather than the answer: a counterfactual point and an estimated one
    # are the same rung on the envelope and differ in which query kind was
    # allowed to return the word. Nothing states that, so it is the next
    # frontier rather than a claim to make here on a reading that would
    # have to enumerate every key a number can sit under.
    ResultStatus.NUMERICALLY_SOLVED: StatusClaim(carries=(A_QUANTITY,)),
    ResultStatus.COUNTERFACTUAL_SOLVED: StatusClaim(carries=(A_QUANTITY,)),
    ResultStatus.COUNTERFACTUAL_BOUNDED: StatusClaim(
        carries=(A_QUANTITY,),
        withholds=frozenset({Shown.POINT})),
}


def _every_status_says_what_it_claims() -> None:
    """A word with no entry is a word nothing can hold.

    The same shape as ``gaps._bind_escapes``: half a table reads exactly
    like a whole one, so the half that is missing has to fail here rather
    than pass quietly as a status nobody thought to write down.
    """
    unclaimed = sorted(str(s) for s in ResultStatus if s not in STATUS_CLAIMS)
    if unclaimed:
        raise ValueError(
            f"{unclaimed} reach a reader as the first word an answer says "
            f"about itself, and nothing here says what that word claims; "
            f"declare it in themis.types.STATUS_CLAIMS beside the member"
        )


_every_status_says_what_it_claims()


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

    ``skeleton`` is a third projection of the same producer's key, and the
    one the reader fills in: the ask written as the statement that would
    settle it, ready to paste back into the program. It sits on the item
    for the reason ``observable`` does — what a later pass needs is the
    ask's own shape and not its rendering. It used to travel beside the
    items in a ``{name: skeleton}`` map that the pusher rejoined by the
    rendered name, which is the failure splitting ``name`` up was meant to
    end; and every call site that did not carry the map handed the reader
    an ask with nothing to paste. ``None`` for a shortfall with no key
    behind it, which is the only case where nothing can be pasted.

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
    words: dict[str, Spoken] = field(default_factory=dict)
    observable: Observable | None = None
    skeleton: dict | None = None
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
    words: dict[str, Spoken] = field(default_factory=dict)
    # A dict the caller can drop into a program's "statements" list after
    # filling in ``value``, carried through verbatim like ``gap`` from the
    # MissingItem this was pushed from. The framing channel, which has no
    # MissingItem, supplies its own via ``gaps.item``. None for a shortfall
    # with no statement behind it — an atom the graph does not declare, an
    # assumption nobody can write down for you.
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
    # #450. A declared reciprocal loop the estimand cannot escape, in a
    # shape the simultaneous-equations reduction does not cover. Its own
    # kind rather than ``unidentifiable_no_admissible_set`` because that
    # one says a search over adjustment sets came back empty, and this
    # says something stronger and earlier: the model is not a DAG, so the
    # quantity a DAG would identify need not exist here at all (Bongers
    # et al. 2021 — a cyclic SCM need not have a solution or a unique
    # interventional distribution). What closes it is a modelling decision,
    # which is why it asks rather than qualifies.
    FEEDBACK_LOOP_REACHES_THE_ESTIMAND = "feedback_loop_reaches_the_estimand"
    MISSING_IV_CANDIDATE = "missing_iv_candidate"
    MISSING_MEDIATOR_DATA = "missing_mediator_data"
    TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN = "transport_target_distribution_unknown"
    # Bareinboim transport formula has TWO data needs: target P*(Z) AND
    # source P(Y|do(X), Z). Most meta-analyses only publish marginal
    # effects, so the source-stratified conditional is often the real
    # bottleneck — surfaced as its own gap_kind so the diagnosis names
    # it explicitly.
    TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN = "transport_source_conditional_unknown"
    # Two declared source domains both transport the target effect, and
    # carry it to different numbers. A falsification rather than a data
    # shortage, in the same family as OVERIDENTIFICATION_REJECTED: the
    # target quantity is one quantity, so two values for it witness that
    # at least one declared selection diagram is wrong. More of the same
    # distributions produces the same contradiction.
    TRANSPORT_SOURCES_DISAGREE = "transport_sources_disagree"
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
    # A proximal query declares k states for the unobserved U, and a proxy
    # column presents some other number of levels. Miao's formula (5) inverts
    # a k×k measurement channel, so the two have to agree — and which
    # observed levels of a finer proxy stand for the SAME state of U is a
    # claim about the measurement that no amount of the data settles. The
    # estimator refuses rather than guessing a grouping, and this is the
    # refusal said as an errand: what is short is a DECLARATION, on the
    # query's ``proxy_coarsening``, and until that field existed there was
    # nothing to name here. Distinct from declared_type_data_mismatch, which
    # is about a column contradicting its own declaration: here the column
    # and its declaration agree, and it is the ESTIMAND's k they do not
    # match. BLOCKING — no number is produced.
    PROXY_COARSENING_UNDECLARED = "proxy_coarsening_undeclared"
    # The continuous regime's own species, and NOT a shortfall of data: the
    # bridge equation is a Fredholm equation of the first kind, so it is
    # ill-posed by nature and has no numeric solution without a penalty
    # added to it. This fires where that penalty has moved the reported
    # number further than sampling noise does, or where a lighter one has no
    # solution at all — in both cases the number a reader is looking at is
    # substantially the penalty's rather than the data's. A number IS
    # produced, so this is not blocking; it is IMPORTANT and must-disclose,
    # because the point rests on a choice nothing in the data settles and a
    # reader shown it without that is being shown a fact.
    REGULARISATION_IS_MOVING_THE_ANSWER = "regularisation_is_moving_the_answer"
    # The treatment bridge q is a RECIPROCAL PROBABILITY — Cui et al. 2024
    # define it so — and is therefore at least one everywhere. A sieve linear
    # in its parameters does not know that, so a fitted q can come out
    # negative on some rows, and where it does the inverse-probability
    # weights are not weights. Not a shortfall of data and not the penalty's
    # doing: it is the declared span failing to contain a function of the
    # required shape, which more rows do not repair. A number IS produced —
    # the doubly robust one does not divide by q alone and survives this —
    # so IMPORTANT rather than blocking, and must-disclose, because a reader
    # shown an inverse-probability estimate built on negative weights is
    # being shown an average of something that is not an average.
    TREATMENT_BRIDGE_LEAVES_ITS_RANGE = "treatment_bridge_leaves_its_range"
    # #457. The channel was too thin to invert, so what came back is a test
    # of whether the effect is zero rather than a number for it (Miao, Geng
    # & Tchetgen Tchetgen 2018 §4). Its own kind and not
    # ``answer_is_bounds_not_point_estimate``, which is the nearest sibling
    # and says something materially different: bounds still BRACKET the
    # magnitude, and a reader can act on the width of them. A test brackets
    # nothing — reject and the effect is somewhere in (−∞, 0) ∪ (0, ∞), fail
    # to reject and even that is not established. Filing the two under one
    # name would let a surface that handles bounds believe it handles this,
    # and print a width where there is no width. BLOCKING, because the
    # question the caller asked — how much — is not the question answered.
    ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE = "answer_is_a_test_not_an_effect_size"


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
    # A falsification, and the only member that is one. It sits here rather
    # than under MISSING_ASSUMPTION because what it asks for is not an
    # assumption anybody can supply: two declared selection diagrams carry
    # one quantity to two numbers, and the repair is to withdraw one of the
    # declarations, not to add to them.
    GapKind.TRANSPORT_SOURCES_DISAGREE,
    # #450. Both halves of what a declared reciprocal loop leaves. The
    # first names a thing to go and find — something that moves the
    # treatment and reaches the outcome only through it — and it is
    # MISSING_IV_CANDIDATE rather than "no admissible set" because an
    # admissible set is not what is wanted and finding one would not
    # help. The second names no such thing, and is here for the same
    # reason TRANSPORT_SOURCES_DISAGREE is: the repair is to withdraw or
    # refine a declaration, not to add data to it.
    GapKind.MISSING_IV_CANDIDATE,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND,
})


# Which of the two things this kind is, and it is exactly one.
#
# A gap either QUALIFIES the answer — read it this way, it rests on that —
# or ASKS for something the answer needed and did not have. Both reach the
# reader; what separates them is what a reader does with one. A caveat is a
# condition on the number above it and belongs beside that number; an ask
# is an errand and belongs on a list. A surface that runs them together
# hands over a shopping list where a condition was owed.
#
# This was three sets until #395, and the third was an artefact of a second
# author. ``explanation`` was a STRING on the envelope, so the caveats were
# rendered into it while the kernel ran; the estimators, finding theirs
# while running, wrote their own words there rather than have one sentence
# said twice — and that difference in who typed it had become a set. With
# the string gone the two halves have nothing left to tell them apart, and
# the split falls back onto the question it was always about.
#
# The two rows partition the enum and are checked below, so a kind added
# later cannot default into either by being forgotten.
QUALIFIES_THE_ANSWER: frozenset[GapKind] = frozenset({
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
    # A caveat and not an ask, although all three of its routes are things
    # to do: none of them is a thing to GO AND GET, and what a reader needs
    # first is the condition on the number in front of them — that a term
    # added to make an ill-posed equation solvable is doing more of the work
    # than the sample is.
    GapKind.REGULARISATION_IS_MOVING_THE_ANSWER,
    # The same shape one bridge over, and a caveat for the same reason: a
    # span that will not hold a function bounded below by one does not come
    # to hold one with more rows, so neither route is a thing to go and get,
    # and what the reader needs first is the condition on the number — that
    # the weights it averages with are not all weights.
    GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE,
    # A caveat despite carrying a real errand, and it sits here for the
    # reason ``answer_is_bounds_not_point_estimate`` does: an answer of a
    # weaker shape came back, and the first thing the reader needs is not to
    # read it as the stronger one. A p-value handed to someone who asked how
    # much is read as a small effect unless something says otherwise, and
    # that misreading happens while they are looking at the number — before
    # any errand about better proxies could reach them.
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE,
    # A falsification found in the kernel rather than by an estimator, so
    # nobody else writes it in their own words: two source domains carried
    # one target effect to two numbers, and the answer cannot be read at
    # all without knowing that a declared diagram is refuted.
    GapKind.TRANSPORT_SOURCES_DISAGREE,
    # Found while an estimator ran rather than while the graph was read.
    # That is a fact about WHEN, not about what: each of these is still a
    # condition on the number it arrived beside, and it was only ever
    # listed apart because the estimator used to write its own wording of
    # it into a string the kernel shipped.
    GapKind.WEAK_IV_INSTRUMENT,
    GapKind.OVERIDENTIFICATION_REJECTED,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR,
    GapKind.PROPENSITY_OVERLAP_VIOLATION,
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION,
    GapKind.DECLARED_TYPE_DATA_MISMATCH,
})

# Asks. The gap report exists to carry these; restating one as a caveat
# would say "you are missing X" in the place reserved for "read the answer
# this way".
ASKS_FOR_SOMETHING: frozenset[GapKind] = frozenset({
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
    # An ask for a declaration rather than for data, which is what the two
    # rows are about: a reader meeting this has an errand — say which levels
    # go together — and not a condition to read the number under, because
    # there is no number.
    GapKind.PROXY_COARSENING_UNDECLARED,
    # The same shape one layer up: the errand is to say how the two
    # variables relate — resolve the loop in time, withdraw it, or accept
    # that the model as declared has no such quantity — and there is no
    # number for it to be a condition on.
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND,
})

if QUALIFIES_THE_ANSWER | ASKS_FOR_SOMETHING != frozenset(GapKind):
    _unclassified = frozenset(GapKind) - (
        QUALIFIES_THE_ANSWER | ASKS_FOR_SOMETHING
    )
    _both = QUALIFIES_THE_ANSWER & ASKS_FOR_SOMETHING
    raise ValueError(
        "every GapKind has to say which of the two it is, because a "
        "surface leads with the caveats and lists the asks, and a kind "
        "in neither row reaches the reader as whatever it was put next "
        "to: "
        + (f"unclassified {sorted(k.value for k in _unclassified)}; "
           if _unclassified else "")
        + (f"in both rows {sorted(k.value for k in _both)}" if _both else "")
    )


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


# --- what a species is worth, and what it stands in the way of ---------------
#
# Both were written at the construction sites — 44 of them for the severity
# and 45 for the blocks — and a value written at every site is not declared
# anywhere. What that costs is not the typing: it is that the reach of any
# rule holding these fields is decided by how the producer happened to lay
# them out, so a verifier could only restate those 45 sites, and restating a
# producer's layout is agreeing with it by construction.
#
# They belong to the species. Measured before they were moved: of the 42
# kinds, 38 are written with one severity at every site and 40 with one
# ``blocks``, and each of the few that are not has a reason its producer
# states in code — so the rows below are the producers' own values, gathered,
# and the ``TURNS_ON`` rows are the ones whose value is an occasion's rather
# than a species'.
#
# The two rows partition the enum and are checked at import, the arrangement
# ``QUALIFIES_THE_ANSWER`` uses above: a kind added later cannot default into
# a severity by being forgotten, because there is nothing to default to.

#: The species whose severity is the same on every occasion.
SEVERITY_OF: dict[GapKind, GapSeverity] = {
    # Nothing downstream can proceed: the estimand is not identified, or a
    # quantity it needs was never supplied.
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: GapSeverity.BLOCKING,
    GapKind.MISSING_DISTRIBUTION: GapSeverity.BLOCKING,
    GapKind.MISSING_UNIT_OBSERVATION: GapSeverity.BLOCKING,
    GapKind.MISSING_STRUCTURAL_INPUT: GapSeverity.BLOCKING,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND: GapSeverity.BLOCKING,
    GapKind.MISSING_IV_CANDIDATE: GapSeverity.BLOCKING,
    GapKind.MISSING_MEDIATOR_DATA: GapSeverity.BLOCKING,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: GapSeverity.BLOCKING,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: GapSeverity.BLOCKING,
    GapKind.TRANSPORT_SOURCES_DISAGREE: GapSeverity.BLOCKING,
    GapKind.DOSE_RESPONSE_DATA_REQUIRED: GapSeverity.BLOCKING,
    GapKind.PROXY_COARSENING_UNDECLARED: GapSeverity.BLOCKING,
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE: GapSeverity.BLOCKING,
    # Nothing in this tree builds one — the multi-source transport that
    # would raise it does not exist — so this row is the value the species
    # would take rather than one a site was seen to write. Declared anyway,
    # because the alternative is a hole in a table whose whole point is
    # having none, and the gate below makes a producer that disagrees with
    # it change THIS line rather than write its own.
    GapKind.MISSING_POPULATION_DISTRIBUTION: GapSeverity.BLOCKING,
    # The answer can be had and is wrong to read as it stands, or a step
    # that was owed did not run.
    GapKind.MISSING_ASSUMPTION: GapSeverity.IMPORTANT,
    GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT: GapSeverity.IMPORTANT,
    GapKind.OVERIDENTIFICATION_REJECTED: GapSeverity.IMPORTANT,
    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR: GapSeverity.IMPORTANT,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH: GapSeverity.IMPORTANT,
    GapKind.MEASUREMENT_ERROR_CONCERN: GapSeverity.IMPORTANT,
    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH: GapSeverity.IMPORTANT,
    GapKind.ILL_DEFINED_INTERVENTION_VERSIONS: GapSeverity.IMPORTANT,
    GapKind.REGULARISATION_IS_MOVING_THE_ANSWER: GapSeverity.IMPORTANT,
    GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE: GapSeverity.IMPORTANT,
    # A condition on the number that a reader can carry without changing
    # what they do next.
    GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH: GapSeverity.INFORMATIONAL,
    GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapSeverity.INFORMATIONAL,
    GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapSeverity.INFORMATIONAL,
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapSeverity.INFORMATIONAL,
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapSeverity.INFORMATIONAL,
    GapKind.LLM_DECLARED_AMBIGUITY: GapSeverity.INFORMATIONAL,
    # Every occasion, because of where the occasions come from: a framing
    # note is built out of the predicates the QUERY names, so a gap of this
    # species is always about a variable whose framing shapes how the
    # answer is read. The severity was computed per note until the two
    # readings of "which predicates the query names" became one and the
    # other branch turned out to be unreachable. A second source of
    # framing notes would make it an occasion's again, and moving this row
    # back is how that would be said.
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: GapSeverity.IMPORTANT,
    GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE: GapSeverity.INFORMATIONAL,
    GapKind.LOW_CONFIDENCE_INPUT_DATA: GapSeverity.INFORMATIONAL,
    GapKind.GRAPH_LEARNED_FROM_DATA: GapSeverity.INFORMATIONAL,
    GapKind.UNMEASURED_CONFOUNDER_RISK: GapSeverity.INFORMATIONAL,
    GapKind.WEAK_IV_INSTRUMENT: GapSeverity.INFORMATIONAL,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR: GapSeverity.INFORMATIONAL,
    GapKind.PROPENSITY_OVERLAP_VIOLATION: GapSeverity.INFORMATIONAL,
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION: GapSeverity.INFORMATIONAL,
    GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE: GapSeverity.INFORMATIONAL,
}

#: And the species whose severity is the occasion's, each saying what it
#: turns on. A sentence rather than a flag: what a reader is owed is why
#: two gaps of one species are worth different amounts, and the next
#: producer of this species has to answer the same question.
SEVERITY_TURNS_ON: dict[GapKind, str] = {
    GapKind.DECLARED_TYPE_DATA_MISMATCH: (
        "whether this answer stands on the column whose data contradict "
        "its declaration. Standing on it, the number answers a different "
        "estimand than the one declared; not standing on it, the column "
        "is simply not in this estimand"
    ),
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED: (
        "which of two things the assumption does: sit under the "
        "instrument as a condition on reading the number, or change what "
        "quantity the number is OF — a single equation's coefficient "
        "rather than the effect that was asked for"
    ),
}

#: What each species stands in the way of, on the same terms.
BLOCKS_OF: dict[GapKind, GapBlocks] = {
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: GapBlocks.IDENTIFICATION,
    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR: GapBlocks.IDENTIFICATION,
    GapKind.MEASUREMENT_ERROR_CONCERN: GapBlocks.IDENTIFICATION,
    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH: GapBlocks.IDENTIFICATION,
    GapKind.ILL_DEFINED_INTERVENTION_VERSIONS: GapBlocks.IDENTIFICATION,
    GapKind.MISSING_DISTRIBUTION: GapBlocks.POINT_ESTIMATE,
    GapKind.MISSING_ASSUMPTION: GapBlocks.POINT_ESTIMATE,
    GapKind.MISSING_UNIT_OBSERVATION: GapBlocks.POINT_ESTIMATE,
    GapKind.MISSING_STRUCTURAL_INPUT: GapBlocks.POINT_ESTIMATE,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND: GapBlocks.POINT_ESTIMATE,
    GapKind.MISSING_IV_CANDIDATE: GapBlocks.POINT_ESTIMATE,
    GapKind.MISSING_MEDIATOR_DATA: GapBlocks.POINT_ESTIMATE,
    GapKind.TRANSPORT_SOURCES_DISAGREE: GapBlocks.POINT_ESTIMATE,
    GapKind.DOSE_RESPONSE_DATA_REQUIRED: GapBlocks.POINT_ESTIMATE,
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH: GapBlocks.POINT_ESTIMATE,
    GapKind.PROXY_COARSENING_UNDECLARED: GapBlocks.POINT_ESTIMATE,
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE: GapBlocks.POINT_ESTIMATE,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: GapBlocks.TRANSPORT,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: GapBlocks.TRANSPORT,
    GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED: GapBlocks.TRANSPORT,
    # The species with no producer, for the reason its severity row gives:
    # it is a transport ask, and what it stands in the way of is the
    # transport its sibling above blocks.
    GapKind.MISSING_POPULATION_DISTRIBUTION: GapBlocks.TRANSPORT,
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: GapBlocks.INTERPRETATION,
    GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH: GapBlocks.INTERPRETATION,
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED: GapBlocks.INTERPRETATION,
    GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapBlocks.INTERPRETATION,
    GapKind.LLM_DECLARED_AMBIGUITY: GapBlocks.INTERPRETATION,
    GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE: GapBlocks.INTERPRETATION,
    GapKind.LOW_CONFIDENCE_INPUT_DATA: GapBlocks.INTERPRETATION,
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapBlocks.INTERPRETATION,
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED:
        GapBlocks.INTERPRETATION,
    GapKind.GRAPH_LEARNED_FROM_DATA: GapBlocks.INTERPRETATION,
    GapKind.UNMEASURED_CONFOUNDER_RISK: GapBlocks.INTERPRETATION,
    GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT:
        GapBlocks.INTERPRETATION,
    GapKind.WEAK_IV_INSTRUMENT: GapBlocks.INTERPRETATION,
    GapKind.OVERIDENTIFICATION_REJECTED: GapBlocks.INTERPRETATION,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR: GapBlocks.INTERPRETATION,
    GapKind.PROPENSITY_OVERLAP_VIOLATION: GapBlocks.INTERPRETATION,
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION: GapBlocks.INTERPRETATION,
    GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE: GapBlocks.INTERPRETATION,
    GapKind.REGULARISATION_IS_MOVING_THE_ANSWER: GapBlocks.INTERPRETATION,
    GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE: GapBlocks.INTERPRETATION,
}

#: The one species whose ``blocks`` is an occasion's.
BLOCKS_TURN_ON: dict[GapKind, str] = {
    GapKind.DECLARED_TYPE_DATA_MISMATCH: (
        "the verdict the reconciliation reached, and whether the answer "
        "stands on that column at all — a column this estimand does not "
        "use is only ever a matter of interpretation"
    ),
}

for _name, _fixed, _varies in (("severity", SEVERITY_OF, SEVERITY_TURNS_ON),
                               ("blocks", BLOCKS_OF, BLOCKS_TURN_ON)):
    _missing = frozenset(GapKind) - (_fixed.keys() | _varies.keys())
    _twice = _fixed.keys() & _varies.keys()
    if _missing or _twice:
        raise ValueError(
            f"every GapKind has to declare its {_name}, or declare that it "
            f"is the occasion's and what it turns on — a kind in neither "
            f"row has nothing to be filled in from and reaches a reader as "
            f"whatever the site that built it happened to type: "
            + (f"undeclared {sorted(k.value for k in _missing)}; "
               if _missing else "")
            + (f"in both rows {sorted(k.value for k in _twice)}"
               if _twice else "")
        )
del _name, _fixed, _varies, _missing, _twice


class GapRefKind(StrEnum):
    """What space a gap's provenance id lives in — which is the whole job.

    A ref is only checkable if something knows where to look for what it
    names, so the member IS the instruction for resolving the id. Three of
    these named a space from the start; the two below did not exist, and
    what filled the space they should have occupied was
    ``VERIFIER_CHECK`` — measured over the corpus, 479 of 966 refs wore it
    while addressing three different things. A kind that names no space
    leaves an auditor with no question to ask, and T10-1's arm for it
    accepted any non-empty string, which is what "unresolvable" looks like
    from the outside.
    """

    DERIVATION_STEP = "derivation_step"
    INVESTIGATION_REQUEST = "investigation_request"
    FRAMING_NOTE = "framing_note"
    #: A path into THIS answer: dotted keys from the envelope's root, with
    #: ``[x]`` picking the member of a list whose ``kind`` is ``x``.
    ENVELOPE_PATH = "envelope_path"
    #: A place in the PROGRAM that was asked, or a pattern a check matched
    #: in it. Not resolvable where T10-1 stands today: its door is handed a
    #: result and no program.
    PROGRAM_SITE = "program_site"
    #: A check this build ran, named, and about a subject where it has one.
    #: Points at no artifact — the check is the signal.
    VERIFIER_CHECK = "verifier_check"


class RequiredDataType(StrEnum):
    IPD = "ipd"
    MARGINAL = "marginal"
    RCT = "rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    EXPERT_JUDGMENT = "expert_judgment"


# --- what shape of data would fill a species --------------------------------
#
# The third field to arrive here for the reason the first two did: written at
# every construction site that has one — six of them — and declared nowhere,
# so a rule holding it could only restate the sites, and restating a
# producer's layout is agreeing with it by construction. What the word costs
# a reader is not small: it is the difference between "someone has to publish
# one number" and "someone has to collect records".
#
# Only species that ASK for data appear here, so totality is a runtime fact
# rather than a partition of the enum, the arrangement ``RAISED_BY`` uses:
# :func:`required_data_type` refuses a species that declared nothing, which
# means a site cannot invent a shape by being the only place that says it.
#
# Measured before they were moved: five of the six species write one shape at
# every site, and the sixth writes both — its row below says what that turns
# on, and the audit reads that occasion off the envelope rather than trusting
# either word.

#: The species that ask for one shape of data, whichever occasion raises them.
DATA_TYPE_OF: dict["GapKind", RequiredDataType] = {
    GapKind.MISSING_MEDIATOR_DATA: RequiredDataType.IPD,
    GapKind.DOSE_RESPONSE_DATA_REQUIRED: RequiredDataType.IPD,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: RequiredDataType.IPD,
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR: RequiredDataType.IPD,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: RequiredDataType.MARGINAL,
    # Nothing in this tree builds one, the same as in its severity row, and
    # declared here for the same reason: it is a transport ask, the KB
    # translator sends it to the same target-population marginal its sibling
    # above goes to, and a producer that disagrees has to change THIS line
    # rather than type its own shape.
    GapKind.MISSING_POPULATION_DISTRIBUTION: RequiredDataType.MARGINAL,
}

#: And the species whose shape is the occasion's, saying what it turns on and
#: which shapes the occasion chooses between. A sentence rather than a flag,
#: for the reason :data:`SEVERITY_TURNS_ON` gives: the next producer of this
#: species has to answer the same question, and an auditor needs to know
#: where to look instead of at a table.
DATA_TYPE_TURNS_ON: dict[
    "GapKind", tuple[frozenset[RequiredDataType], str]
] = {
    GapKind.MISSING_DISTRIBUTION: (
        frozenset({RequiredDataType.IPD, RequiredDataType.MARGINAL}),
        "whether the distribution it is missing conditions on anything. A "
        "conditional can only come from records carrying every half of it "
        "at once; a marginal is one number, and asking for records to get "
        "it sends a reader after data nobody needs to hand over",
    ),
}

if DATA_TYPE_OF.keys() & DATA_TYPE_TURNS_ON.keys():
    raise ValueError(
        "a species asks for one shape of data or chooses between shapes, "
        "not both: "
        + str(sorted(k.value for k in
                     DATA_TYPE_OF.keys() & DATA_TYPE_TURNS_ON.keys()))
    )
for _kind, _shapes in DATA_TYPE_TURNS_ON.items():
    if len(_shapes[0]) < 2:
        raise ValueError(
            f"{_kind.value} declares that the shape of data it asks for is "
            f"the occasion's but names fewer than two — a species with one "
            f"shape belongs in DATA_TYPE_OF, where nothing has to choose"
        )
del _kind, _shapes


def required_data_type(kind: "GapKind") -> frozenset[RequiredDataType]:
    """The shapes of data this species may ask for, or nothing if it asks
    for no particular shape.

    Total in the direction that matters, the same as :func:`raised_by`: a
    species with no row gets an empty set and every caller reads that as a
    refusal rather than as permission, because defaulting to "any shape" is
    the arrangement this table was written to end.
    """
    if kind in DATA_TYPE_OF:
        return frozenset({DATA_TYPE_OF[kind]})
    declared = DATA_TYPE_TURNS_ON.get(kind)
    return declared[0] if declared else frozenset()


# --- which check raises each species that cites one -------------------------
#
# A ``VERIFIER_CHECK`` ref says two things: which check found this, and what
# it was about. Both were written as f-string literals at the seventeen
# construction sites and declared nowhere, so an audit had no second record
# to hold either half against and could only ask that the string was not
# empty. That is the arrangement ``SEVERITY_OF`` was moved out of, for the
# same reason: a value written at every site is not declared anywhere, and a
# verifier that restates the sites agrees with them by construction.
#
# Measured before they were moved: fourteen species raise a named check,
# eighteen names between them, and ten of the fourteen use one name at every
# site. The four that use two each have a reason its producer states in
# code, and those reasons are the ``TURNS_ON`` rows.
#
# Only species that CITE a check appear here. Unlike severity, which every
# gap has, being raised by a named check is a property of how a species is
# found — so totality is a runtime fact rather than a partition of the enum:
# :func:`raised_by` refuses a species that declared nothing, which means a
# site cannot invent a check name by being the only place that says it.

#: The species raised by one check, whichever occasion raises them.
RAISED_BY: dict["GapKind", str] = {
    GapKind.ANSWER_IS_A_TEST_NOT_AN_EFFECT_SIZE: "no_effect_test",
    GapKind.COLLIDER_CONDITIONING_OPENS_BACKDOOR: "collider",
    GapKind.DECLARED_TYPE_DATA_MISMATCH: "type_reconciliation",
    GapKind.IV_ESTIMAND_FALLBACK_TO_LINEAR: "iv_estimand_fallback",
    GapKind.OUTCOME_MODEL_QUASI_SEPARATION: "outcome_separation",
    GapKind.OVERIDENTIFICATION_REJECTED: "overid",
    GapKind.PROXY_COARSENING_UNDECLARED: "proxy_coarsening",
    GapKind.REGULARISATION_IS_MOVING_THE_ANSWER: "regularisation",
    GapKind.SELECTION_ON_COLLIDER_OPENS_PATH: "selection_observation",
    GapKind.TREATMENT_BRIDGE_LEAVES_ITS_RANGE: "treatment_bridge_range",
}

#: And the species two checks can raise, each saying what the choice turns
#: on. A sentence rather than a set alone: what a reader is owed is why one
#: species arrives under two names, and the next producer of it has to
#: answer the same question — which is why the sentence is what
#: :func:`raised_by_ref` hands back to a site that did not choose, the same
#: way :data:`SEVERITY_TURNS_ON` is quoted at a gap that states no severity.
RAISED_BY_TURNS_ON: dict["GapKind", tuple[frozenset[str], str]] = {
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED: (
        frozenset({"counterfactual_status", "counterfactual_query_kind"}),
        "which of two shapes triggered it when no derivation chain exists "
        "to cite: an answer that reached a counterfactual status, or a "
        "query that asked a counterfactual and got no further",
    ),
    GapKind.ILL_DEFINED_INTERVENTION_VERSIONS: (
        frozenset({"intervention_state_inferred",
                   "intervention_state_without_time_window"}),
        "whether the declaration contradicted itself or said nothing — a "
        "predicate declared a state with no window is a different finding "
        "from one silent on both fields, and a reader adjusts tone on it",
    ),
    GapKind.PROPENSITY_OVERLAP_VIOLATION: (
        frozenset({"propensity_overlap", "stratum_overlap"}),
        "which witness saw it: the fitted propensity leaving too few "
        "observations away from {0,1}, or a stratum table with an arm "
        "missing. The finding is one finding; the evidence is not",
    ),
    GapKind.WEAK_IV_INSTRUMENT: (
        frozenset({"weak_iv", "weak_iv_joint"}),
        "whether one instrument's own first stage was weak, or the "
        "instruments were only weak read together — which is what a "
        "reader needs to know before dropping any one of them",
    ),
}

#: What a check writes where it has no subject to name. Declared once
#: because both halves read it: the producer writes it, and the audit
#: skips it rather than looking for a variable by that name.
NO_SUBJECT = "<none>"

for _kind, _checks in RAISED_BY_TURNS_ON.items():
    if len(_checks[0]) < 2:
        raise ValueError(
            f"{_kind.value} declares that its check is the occasion's but "
            f"names fewer than two — a species with one check belongs in "
            f"RAISED_BY, where nothing has to choose"
        )
if RAISED_BY.keys() & RAISED_BY_TURNS_ON.keys():
    raise ValueError(
        "a species has one check or it has a choice between checks, not "
        "both: "
        + str(sorted(k.value for k in
                     RAISED_BY.keys() & RAISED_BY_TURNS_ON.keys()))
    )
del _kind, _checks


def raised_by(kind: "GapKind") -> frozenset[str]:
    """The checks this species may name, or nothing if it names none.

    Total in the direction that matters: a species with no row gets an
    empty set, and every caller treats that as a refusal rather than as
    permission. The alternative — defaulting to "any name" — is the
    arrangement this table was written to end.
    """
    if kind in RAISED_BY:
        return frozenset({RAISED_BY[kind]})
    declared = RAISED_BY_TURNS_ON.get(kind)
    return declared[0] if declared else frozenset()


@dataclass(frozen=True)
class GapProvenanceRef:
    """One signal that triggered a DataGap: what it was, and where to look.

    :class:`GapRefKind` says which space ``ref_id`` lives in, and T10-1
    resolves it there. A kind that names no space is a ref nothing can ask
    about, which is why there is no general-purpose member.

    A ``VERIFIER_CHECK`` ref is spelled ``check`` or ``check:subject``, and
    both halves are held: the check against :data:`RAISED_BY` /
    :data:`RAISED_BY_TURNS_ON` for the species citing it, the subject
    against the names that gap says it is about.
    """
    ref_kind: GapRefKind
    ref_id: str


def raised_by_ref(
    kind: "GapKind", subject: str = "", *, check: str | None = None,
) -> tuple[GapProvenanceRef, ...]:
    """The provenance of a gap a check raised, spelled from the declaration.

    The one way to build a ``VERIFIER_CHECK`` ref, so the check's name comes
    from :data:`RAISED_BY` rather than from whichever site is writing it.
    Species that could arrive under either of two checks say which via
    ``check``, and that too is held to what they declared — a site may
    choose between the names its species owns and may not add one.

    Raises for a species that declared no check, which is what makes the
    table total without partitioning the enum: there is no way to emit one
    of these refs without a row.
    """
    allowed = raised_by(kind)
    if not allowed:
        raise ValueError(
            f"{kind.value} raised a gap and cited a check, but declares "
            f"none — add it to RAISED_BY, or to RAISED_BY_TURNS_ON with "
            f"what the choice turns on"
        )
    if check is None:
        if len(allowed) > 1:
            raise ValueError(
                f"{kind.value} can arrive under any of {sorted(allowed)} "
                f"and this site did not say which — it turns on "
                + RAISED_BY_TURNS_ON[kind][1]
            )
        (check,) = allowed
    elif check not in allowed:
        raise ValueError(
            f"{kind.value} named check {check!r}, which is not one it "
            f"declares: {sorted(allowed)}"
        )
    return (GapProvenanceRef(
        ref_kind=GapRefKind.VERIFIER_CHECK,
        ref_id=f"{check}:{subject}" if subject else check,
    ),)


#: Nine species share this because they share the reason.
_A_STEP_OR_THE_ASK = (
    "whether the identification attempt recorded a step before this "
    "gap was filed — with a chain to cite the ref names the step, and "
    "with none it names the ask the gap was pushed as"
)


#: Which space a species' provenance ids live in, as its own sites type
#: it. Lived in ``verifier.data_gap_rules._KIND_ACCEPTS_REF`` until #618,
#: where the producer could not read it: every site typed the kind beside
#: the id, nothing checked the two against each other, and the only rule
#: that consulted the table asked whether a gap carried AT LEAST ONE ref
#: of an acceptable kind — so a second ref of any other kind rode along
#: unasked. Thirteen rows are absent and a fourteenth is short a
#: member, because :func:`_bind_ref_kinds` folds the checks in; see
#: it for why they cannot be written here.
_REF_KINDS_TYPED_AT_SITES: dict["GapKind", frozenset[GapRefKind]] = {
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.MISSING_DISTRIBUTION: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    # Both of these listed verifier_check with no reason beside it, alone
    # among the entries here — and neither species declares a check, so
    # what the row promised was a shape T10-1 refuses on sight. Widening a
    # row to let something through is how an entry ends up with nothing to
    # say for itself; a species that may cite a check has to name it.
    GapKind.MISSING_POPULATION_DISTRIBUTION: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.MISSING_ASSUMPTION: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    # Unit-level reading an SCM counterfactual needs for abduction, and
    # the residual for any structural requirement no more specific
    # classifier claimed. Both are raised only through the
    # missing-information channel — the producers return before any
    # derivation step is recorded — so the investigation_request ref is
    # the only citation available.
    GapKind.MISSING_UNIT_OBSERVATION: frozenset({
        GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.MISSING_STRUCTURAL_INPUT: frozenset({
        GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.MISSING_IV_CANDIDATE: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.MISSING_MEDIATOR_DATA: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
    # Two declared source domains carried one target quantity to two
    # numbers. Raised in the kernel as an assumption-group item, so the
    # provenance is the request that item was pushed as — the same channel
    # every other kernel-raised species uses, and not a verifier_check:
    # this falsification is found while identifying, not while estimating.
    GapKind.TRANSPORT_SOURCES_DISAGREE: frozenset({
        GapRefKind.INVESTIGATION_REQUEST
    }),
    GapKind.AMBIGUOUS_VARIABLE_DEFINITION: frozenset({
        GapRefKind.FRAMING_NOTE
    }),
    # Phase 13: dose-response data spec — triggered by a program-level
    # ambiguity rather than a failed derivation rule, so there is no step
    # to cite and the ref names the place in the program it was found.
    GapKind.DOSE_RESPONSE_DATA_REQUIRED: frozenset({GapRefKind.PROGRAM_SITE}),
    # Phase 11.x §C: the ref names the cause-statement annotation that
    # flagged the path edge as an LLM hypothesis — a place in the program,
    # shaped program:cause:<from>-><to>:annotations.source.
    GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH: frozenset({
        GapRefKind.PROGRAM_SITE
    }),
    # Must-disclose caveat kinds — the caveat is derived from a block of
    # the answer itself, so the ref is the path to that block. That
    # sentence used to be a comment because no member of the vocabulary
    # could say it, and a ref nothing could locate is a ref nothing could
    # check.
    GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED: frozenset({
        GapRefKind.ENVELOPE_PATH
    }),
    GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED: frozenset({
        GapRefKind.ENVELOPE_PATH
    }),
    GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED: frozenset({
        GapRefKind.ENVELOPE_PATH
    }),
    GapKind.LLM_DECLARED_AMBIGUITY: frozenset({GapRefKind.ENVELOPE_PATH}),
    GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE: frozenset({
        GapRefKind.ENVELOPE_PATH
    }),
    GapKind.LOW_CONFIDENCE_INPUT_DATA: frozenset({GapRefKind.ENVELOPE_PATH}),
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.PROGRAM_SITE
    }),
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED: frozenset({
        GapRefKind.DERIVATION_STEP
    }),
    # The signal is in the PROGRAM — the producer reads
    # ``program.extensions.discovery_metadata`` and says so in its own
    # docstring, while the ref it wrote was spelled as a path into the
    # answer, naming a block no answer carries.
    GapKind.GRAPH_LEARNED_FROM_DATA: frozenset({GapRefKind.PROGRAM_SITE}),
    # Program-shape signal: declared confounder pattern (Z->X & Z->Y) with no
    # bidirected edges. Trigger does not require a recorded derivation step
    # (the kernel may skip identify_via_backdoor when status is
    # NEEDS_INVESTIGATION due to missing theta), so the ref names the
    # program-shape predicate it matched.
    GapKind.UNMEASURED_CONFOUNDER_RISK: frozenset({GapRefKind.PROGRAM_SITE}),
    # Trigger compares query fields against result.extensions; the ref
    # names the conflict in the program that produced it.
    GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT: frozenset({
        GapRefKind.PROGRAM_SITE
    }),
    # Structural-input signal routed via the same
    # investigation_request channel that carries MISSING_DISTRIBUTION,
    # but the item.reason carries the d-sep refusal signature
    # ("d-separation 拒绝"). Same provenance shape as
    # missing_distribution because both originate from the formula-
    # evaluator's InsufficientTheta path; the classifier branches on
    # the reason text. Marked must-disclose IMPORTANT — graph and CPT
    # disagree, the user needs to fix one of them, not just supply more
    # theta.
    GapKind.GRAPH_THETA_INDEPENDENCE_MISMATCH: frozenset({
        GapRefKind.INVESTIGATION_REQUEST
    }),
    # Program-shape signal — variable on the identification path
    # declares a (measurement | observability) field whose value names a
    # known noisy-measurement pattern (self-report / questionnaire /
    # single-occasion / proxy / 24h recall etc.). The ref names the
    # (variable, field) pair in the program; classifier-driven, no
    # derivation step exists.
    GapKind.MEASUREMENT_ERROR_CONCERN: frozenset({GapRefKind.PROGRAM_SITE}),
    # 2026-06-18 dichotomization: a path variable's ``threshold`` field
    # encodes a continuous measure cut at a cutpoint. The ref names the
    # program variable + threshold value (no derivation step — program-shape
    # detection like measurement_error / ill_defined).
    # Royston-Altman-Sauerbrei 2006 *Stat Med* 25:127.
    GapKind.DICHOTOMIZED_CONTINUOUS_MEASURE: frozenset({
        GapRefKind.PROGRAM_SITE
    }),
    # #450. Raised by the identification layer, so it cites the
    # investigation request that carries the ask — the same signal
    # ``missing_iv_candidate`` cites when a loop leaves an instrument as
    # the only route.
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND: frozenset({
        GapRefKind.DERIVATION_STEP, GapRefKind.INVESTIGATION_REQUEST
    }),
}

#: And where the occasion settles it, each row saying what it turns on.
#: One question stands behind every row — had the identification attempt
#: recorded a step by the time this gap was filed — and the rows differ
#: only in where they fall back when it had not. The thirteen species
#: folded in below are the same question's third answer: never.
REF_KIND_TURNS_ON: dict["GapKind", str] = {
    GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET: _A_STEP_OR_THE_ASK,
    GapKind.MISSING_DISTRIBUTION: _A_STEP_OR_THE_ASK,
    GapKind.MISSING_POPULATION_DISTRIBUTION: _A_STEP_OR_THE_ASK,
    GapKind.MISSING_ASSUMPTION: _A_STEP_OR_THE_ASK,
    GapKind.MISSING_IV_CANDIDATE: _A_STEP_OR_THE_ASK,
    GapKind.MISSING_MEDIATOR_DATA: _A_STEP_OR_THE_ASK,
    GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN: _A_STEP_OR_THE_ASK,
    GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN: _A_STEP_OR_THE_ASK,
    GapKind.FEEDBACK_LOOP_REACHES_THE_ESTIMAND: _A_STEP_OR_THE_ASK,
    GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED: (
        "the same question, falling back elsewhere: with a recorded "
        "identify_via_front_door step the ref names it, and where the run "
        "stopped at NEEDS_INVESTIGATION before any step was written it "
        "names the program shape that matched"
    ),
    GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED: (
        "the same question again, and the third place it falls back to: "
        "with a counterfactual derivation step recorded the ref names it, "
        "and with none it names the check that classified the query — "
        "which is why this species is in RAISED_BY_TURNS_ON too, and why "
        "VERIFIER_CHECK reaches its row through the fold below rather "
        "than being written here a second time"
    ),
}


def _bind_ref_kinds(
    typed: dict["GapKind", frozenset[GapRefKind]],
) -> dict["GapKind", frozenset[GapRefKind]]:
    """Fold the checks in, then hold the result to the space it covers.

    Which species may cite a check is settled already: it is exactly the
    species :data:`RAISED_BY` and :data:`RAISED_BY_TURNS_ON` name,
    because :func:`raised_by_ref` is the only way to build one of those
    refs. A row saying so again would be a second copy of a fact that has
    an owner, free to drift from it, so the rows are folded in here and a
    table that states one anyway is refused.

    Four things are checked, and the last is the one worth naming: a
    species has a sentence in :data:`REF_KIND_TURNS_ON` if and only if
    the bound row leaves it a choice. That is the partition
    :data:`SEVERITY_OF` and :data:`SEVERITY_TURNS_ON` keep, asked of the
    result rather than of the two tables, which is stronger — neither
    table can be read on its own to answer it.
    """
    restated = sorted(kind.value for kind, members in typed.items()
                      if GapRefKind.VERIFIER_CHECK in members)
    if restated:
        raise ValueError(
            f"{restated} declare VERIFIER_CHECK, which RAISED_BY and "
            f"RAISED_BY_TURNS_ON already settle; drop the member and let "
            f"the fold place it, or the two tables will disagree"
        )
    bound: dict["GapKind", set[GapRefKind]] = {
        kind: set(members) for kind, members in typed.items()}
    for kind in GapKind:
        if raised_by(kind):
            bound.setdefault(kind, set()).add(GapRefKind.VERIFIER_CHECK)

    outside = sorted(str(kind) for kind in bound if not isinstance(kind, GapKind))
    missing = sorted(kind.value for kind in GapKind if kind not in bound)
    if outside or missing:
        raise ValueError(
            f"a species' provenance has to point somewhere: "
            f"{missing} have no row and {outside} are not species"
        )
    empty = sorted(kind.value for kind, members in bound.items()
                   if not members)
    if empty:
        raise ValueError(
            f"{empty} declare an empty row, which reads as a refusal of "
            f"every ref and would leave the species unbuildable"
        )
    unreachable = sorted(
        str(member) for member in GapRefKind
        if not any(member in members for members in bound.values()))
    if unreachable:
        raise ValueError(
            f"{unreachable} is a space no species cites, so nothing can "
            f"put a ref there; drop the member or give it a species"
        )
    choosing = {kind for kind, members in bound.items() if len(members) > 1}
    sentenced = set(REF_KIND_TURNS_ON)
    if choosing != sentenced:
        raise ValueError(
            f"a species whose ref kind the occasion settles owes a "
            f"sentence saying what it turns on: "
            f"{sorted(k.value for k in choosing - sentenced)} have a "
            f"choice and no sentence, and "
            f"{sorted(k.value for k in sentenced - choosing)} have a "
            f"sentence and no choice"
        )
    return {kind: frozenset(members) for kind, members in bound.items()}


#: Every species, and the spaces its provenance may point into.
REF_KINDS_OF: dict["GapKind", frozenset[GapRefKind]] = _bind_ref_kinds(
    _REF_KINDS_TYPED_AT_SITES)


def ref_kinds_of(kind: "GapKind") -> frozenset[GapRefKind]:
    """The spaces this species may cite, empty for one it does not name."""
    member = kind if isinstance(kind, GapKind) else GapKind(str(kind))
    return REF_KINDS_OF.get(member, frozenset())


def cites(
    kind: "GapKind", *ref_ids: str, ref_kind: GapRefKind | None = None,
) -> tuple[GapProvenanceRef, ...]:
    """A gap's provenance, with the space read off the species.

    What :func:`raised_by_ref` is for a check, this is for every other
    channel: the site brings the id, which is the half only it knows, and
    the space comes from the declaration. Species the occasion settles
    say which via ``ref_kind`` and are held to what they declared, and a
    site that does not say is told what the choice turns on.

    A check ref is refused here whichever way it arrives, including by
    the fold filling one in. Its id carries the check's NAME, and that
    name is :data:`RAISED_BY`'s to supply — a second constructor able to
    emit one is a second place the name could come from.

    Several ids give several refs, because two producers file one gap
    over every program site that triggered it. An empty call is refused:
    a gap with no provenance is one nothing can be asked about, and the
    site that built it is a better place to learn that than the audit.
    """
    if not ref_ids:
        raise ValueError(
            f"{kind.value} cited nothing, and a gap whose provenance is "
            f"empty is one no rule can follow back to a signal"
        )
    allowed = ref_kinds_of(kind)
    if not allowed:
        raise ValueError(
            f"{kind.value} cited {list(ref_ids)} and declares no space to "
            f"cite it in — give it a row in _REF_KINDS_TYPED_AT_SITES"
        )
    if ref_kind is None:
        if len(allowed) > 1:
            raise ValueError(
                f"{kind.value} may cite any of "
                f"{sorted(str(m) for m in allowed)} and this site did not "
                f"say which — it turns on " + REF_KIND_TURNS_ON[kind]
            )
        (ref_kind,) = allowed
    elif ref_kind not in allowed:
        raise ValueError(
            f"{kind.value} cited {str(ref_kind)!r}, which is not a space "
            f"it declares: {sorted(str(m) for m in allowed)}"
        )
    if ref_kind is GapRefKind.VERIFIER_CHECK:
        raise ValueError(
            f"{kind.value} cites a check, and raised_by_ref is the one "
            f"way to build that ref so the check's name comes from "
            f"RAISED_BY rather than from this site"
        )
    return tuple(GapProvenanceRef(ref_kind=ref_kind, ref_id=one)
                 for one in ref_ids)


@dataclass(frozen=True)
class GapRequiredData:
    """Optional 'what kind of data closes this gap' block. Generator fills
    what it can infer from upstream signals; absent fields stay None."""
    data_type: RequiredDataType | None = None
    population: "str | dict | None" = None
    """Which population to collect from: a NAME, or a STATEMENT saying
    which one.

    A name is what a caller supplied — a source or target domain the
    program declared — and it renders the same to every reader. Some
    producers have no name to pass on and a characterisation instead
    ("the strata carrying only one arm of the instrument"), and a slot
    that only accepts a name leaves them writing prose into it. Which is
    the same answer the three statement fields below already give, one
    field up: :class:`themis.gaps.Population` holds the sentences."""
    variables: tuple[str, ...] = ()
    min_sample_size: int | None = None
    precision_target: dict | None = None
    """What that many would buy, and on what assumptions — as a STATEMENT
    rather than as its text.

    A number without them means nothing: an n that detects Cohen's h=0.2
    is not an n that detects h=0.5. They used to be assembled into a
    sentence by the arithmetic that produced the number, which made that
    arithmetic the author of a reader's prose and fixed its language — and
    the reason recorded beside it, that the sentence goes into a Chinese
    row of the report, had stopped being true: no Python surface renders
    this field. Its one reader is the model reading the rendering prompt.
    :class:`themis.output.sample_size.Precision` holds the sentences."""
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
    time_window: dict | None = None
    """When the measurements would have to be taken, as a STATEMENT —
    :class:`themis.output.data_gap_report.Window`."""
    sutva_concerns: tuple[dict, ...] = ()
    """The ways this design could break SUTVA, as STATEMENTS —
    :class:`themis.output.data_gap_report.Sutva`. A list of them because
    a design breaks it in more than one way at once."""


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
    words: dict[str, Spoken] = field(default_factory=dict)


@dataclass(frozen=True)
class GapSentence:
    """One statement of what a gap is, and this occasion's facts for it.

    The same three fields again, a third channel over. What a gap says
    about itself was one string, written at 38 sites: 24 filled a
    bilingual template, six were Chinese f-strings in the dispatcher, and
    four assembled a paragraph out of two to five optional pieces with
    ``+=`` and ``"".join``. That assembly is rendering, and it was
    happening in the kernel, in whichever language the builder had been
    passed.

    So a description is a LIST of these rather than one: which statements
    it has is what this occasion knows — whether the discovery run
    recorded an α, how many methods bracketed the answer, whether the
    second overidentification test was computed — and the seam between two
    of them belongs to the reader's language, not to either statement.
    """
    sentence: "Sentence"
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, Spoken] = field(default_factory=dict)


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

    ``description`` stood beside them and held the paragraph a reader is
    shown. :class:`GapSentence` says what that cost; ``describes`` is the
    statements it was assembled from, and :data:`themis.gaps.DESCRIBES`
    holds their text.

    ``severity`` and ``blocks`` come from the species unless the species
    says they are the occasion's — :data:`SEVERITY_OF` and
    :data:`BLOCKS_OF`, with :data:`SEVERITY_TURNS_ON` and
    :data:`BLOCKS_TURN_ON` for the few that are. They were typed at every
    construction site, which is how a field belonging to the species came
    to have 45 authors and no declaration.

    ``required_data.data_type`` is settled here too, from
    :data:`DATA_TYPE_OF` and :data:`DATA_TYPE_TURNS_ON`, for the same
    reason and against the same objection: the field lives one object down,
    on something that does not know which species it is describing, so
    nothing but this constructor is in a position to hold it.

    ``alternative_paths`` is held the same way and refused rather than
    filled — :data:`themis.gaps.ROUTES_OF` and
    :data:`themis.gaps.NO_WAY_PAST`, read through
    :func:`themis.gaps.ways_past`. Filling is not open to it: which of a
    species' ways past this occasion offers, and which of the occasion's
    facts each names, is the renderer's to decide. What the species does
    settle is which routes are ITS ways past, and that had 38 authors.

    Passing one is still allowed where it agrees, because
    ``dataclasses.replace`` re-enters this constructor with the gap's own
    values and a gap must survive being rewritten. What is refused is a
    value that CONTRADICTS the species: the declaration is the only place
    such a value is decided, so a site holding a different one is either
    wrong or has found a species whose value is an occasion's, and the
    second belongs in the ``TURNS_ON`` table with the sentence saying so.
    """
    kind: GapKind
    describes: tuple[GapSentence, ...]
    blocks: GapBlocks = field(default=None, kw_only=True)  # type: ignore[assignment]
    severity: GapSeverity = field(default=None, kw_only=True)  # type: ignore[assignment]
    provenance: tuple[GapProvenanceRef, ...] = ()
    signature: str | None = None
    required_data: GapRequiredData | None = None
    said: dict[str, str] = field(default_factory=dict)
    words: dict[str, Spoken] = field(default_factory=dict)
    alternative_paths: tuple[GapRoute, ...] = ()

    def __post_init__(self) -> None:
        for name, fixed, varies, where in (
            ("severity", SEVERITY_OF, SEVERITY_TURNS_ON, "SEVERITY_TURNS_ON"),
            ("blocks", BLOCKS_OF, BLOCKS_TURN_ON, "BLOCKS_TURN_ON"),
        ):
            declared = fixed.get(self.kind)
            stated = getattr(self, name)
            if declared is None:
                if stated is None:
                    raise ValueError(
                        f"{self.kind.value} declares that its {name} is the "
                        f"occasion's — {varies[self.kind]} — so this gap has "
                        f"to say which"
                    )
                continue
            if stated is None:
                object.__setattr__(self, name, declared)
            elif stated != declared:
                raise ValueError(
                    f"this gap says its {name} is {stated.value!r} and "
                    f"{self.kind.value} is {declared.value!r} on every "
                    f"occasion; a species' value is not a site's to set. If "
                    f"this occasion's really differs, the species belongs in "
                    f"{where} with the sentence saying what it turns on"
                )
        self._settle_the_shape_of_data_it_asks_for()
        self._settle_the_ways_past_it_offers()
        self._settle_the_statements_it_makes()
        self._settle_the_spaces_it_cites()

    def _settle_the_ways_past_it_offers(self) -> None:
        """The routes on this gap are ways past the gap it is.

        Imported here rather than at the top because :mod:`themis.gaps`
        imports this module: the routes are an enum there, the kind is an
        enum here, and the two meet for the first time on this object.

        Refused and never filled, which is the difference between this
        field and the three above it. A species settles WHICH routes are
        its own; which of them this occasion offers, and what each names,
        is the renderer's, and a table that answered it would be the
        renderer's branches written twice.
        """
        from .gaps import NO_WAY_PAST, ways_past

        offered = {alt.route for alt in self.alternative_paths}
        if not offered:
            return
        allowed = ways_past(
            self.kind, blocking=self.severity is GapSeverity.BLOCKING)
        stray = sorted(str(route) for route in offered - allowed)
        if not stray:
            return
        if self.kind in NO_WAY_PAST:
            raise ValueError(
                f"this gap offers {stray} and {self.kind.value} declares no "
                f"way past at all — {NO_WAY_PAST[self.kind]}. If that has "
                f"stopped being true, the species moves to gaps.ROUTES_OF "
                f"with the routes it settles"
            )
        raise ValueError(
            f"this gap offers {stray}, which {self.kind.value} does not "
            f"declare as a way past it (gaps.ROUTES_OF holds "
            f"{sorted(str(route) for route in allowed)}); a way past a gap "
            f"belongs to the gap that offers it, so a route a site knows "
            f"about is one the species has to declare"
        )

    def _settle_the_statements_it_makes(self) -> None:
        """What this gap says about itself is what its species says.

        The field a reader reads FIRST, and the one nothing held. A
        description is a list of statements from a closed vocabulary of
        88, and which of them belong to a species was typed at every site
        that builds one and declared nowhere — so a gap about measurement
        error could describe itself as a weak first stage and three public
        doors said yes.

        Refused and never filled, for the reason
        :meth:`_settle_the_ways_past_it_offers` gives: a species settles
        WHICH statements are its own; which of them this occasion makes,
        and what each names, is the renderer's.

        Silent where the kind is not one this build names. Which species
        exist is the contract's question, answered at the door that
        serialises them, and a check refusing for a reason another
        authority owns reports that authority's coverage as its own.
        """
        from .gaps import SENTENCES_OF, says_of

        said = {entry.sentence for entry in self.describes}
        if not said or not isinstance(self.kind, GapKind):
            return
        allowed = says_of(self.kind)
        stray = sorted(str(entry) for entry in said - allowed)
        if not stray:
            return
        if self.kind not in SENTENCES_OF:
            raise ValueError(
                f"this gap says {stray} and nothing in this kernel builds a "
                f"{self.kind.value} at all, so it declares no statement of "
                f"its own (see data_gap_report.GAP_KINDS_WITH_NO_PRODUCER). "
                f"A species that has gained a producer gains a row in "
                f"gaps._SENTENCES_TYPED_AT_SITES with what it says"
            )
        raise ValueError(
            f"this gap says {stray}, which {self.kind.value} does not "
            f"declare as a statement about itself (gaps.SENTENCES_OF holds "
            f"{sorted(str(entry) for entry in allowed)}); what a gap tells a "
            f"reader it IS belongs to the gap it is, so a statement a site "
            f"writes is one the species has to declare"
        )


    def _settle_the_spaces_it_cites(self) -> None:
        """Where this gap's provenance points is settled by the gap it is.

        A ref is only checkable because its kind says where to look, so
        the kind a site types beside an id is a claim about the species
        as much as about the id. The declaration is
        :data:`REF_KINDS_OF`, and :func:`cites` fills it in for sites
        that do not have a choice; this refuses the rest, which is what
        makes the two agree rather than merely coincide.

        Silent where the kind is not one this build names, for the reason
        :meth:`_settle_the_statements_it_makes` gives.
        """
        if not self.provenance or not isinstance(self.kind, GapKind):
            return
        allowed = ref_kinds_of(self.kind)
        cited = {ref.ref_kind for ref in self.provenance}
        stray = sorted(str(member) for member in cited - allowed)
        if not stray:
            return
        raise ValueError(
            f"this gap cites {stray}, which {self.kind.value} does not "
            f"declare as a space its provenance points into "
            f"(REF_KINDS_OF holds "
            f"{sorted(str(m) for m in allowed)}); where a gap's evidence "
            f"lives belongs to the gap it is, so a space a site cites is "
            f"one the species has to declare"
        )

    def _settle_the_shape_of_data_it_asks_for(self) -> None:
        """``required_data.data_type`` on the same terms, one field down.

        It sits on :class:`GapRequiredData`, which does not know the species,
        so the species has to reach it from here — that distance is how the
        word came to have six authors and no declaration.
        """
        wanted = self.required_data
        if wanted is None:
            return
        allowed = required_data_type(self.kind)
        stated = wanted.data_type
        if not allowed:
            if stated is not None:
                raise ValueError(
                    f"this gap asks for {stated.value!r} data and "
                    f"{self.kind.value} declares no shape it asks for — add "
                    f"it to DATA_TYPE_OF, or to DATA_TYPE_TURNS_ON with the "
                    f"sentence saying what the choice turns on"
                )
            return
        if stated is None:
            if len(allowed) > 1:
                raise ValueError(
                    f"{self.kind.value} asks for any of "
                    f"{sorted(shape.value for shape in allowed)} and this "
                    f"gap did not say which — it turns on "
                    + DATA_TYPE_TURNS_ON[self.kind][1]
                )
            object.__setattr__(
                self, "required_data",
                dc_replace(wanted, data_type=next(iter(allowed))),
            )
            return
        if stated not in allowed:
            raise ValueError(
                f"this gap asks for {stated.value!r} data and "
                f"{self.kind.value} asks for "
                f"{sorted(shape.value for shape in allowed)}; a species' "
                f"value is not a site's to set. If this occasion's really "
                f"differs, the species belongs in DATA_TYPE_TURNS_ON with "
                f"the sentence saying what it turns on"
            )


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
    answering in.

    ``summary`` stood here on the same terms and went the same way. Its
    head WAS the first gap's ``description`` — a rendering of a rendering,
    wrapped in one of two frames chosen by ``answer_tier`` — so both of
    its inputs were on this object and it carried no fact of its own. It
    is :func:`themis.gaps.summary` now, assembled where the reader's
    language is known."""
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
    # Built by output.bounds and seen on real results: one full-suite run
    # produced all three, two of them side by side on a single result.
    MANSKI_NATURAL = "manski_natural"
    BALKE_PEARL_IV = "balke_pearl_iv"
    MANSKI_TAMER_MONOTONICITY = "manski_tamer_monotonicity"  # under outcome monotonicity
    # A stub slot — declared so a future implementation doesn't churn the
    # enum, but NEITHER reachable from runtime NOR backed by a builder.
    # Adding it is a real-case-driven follow-up: implement only when a
    # query actually surfaces a graph that would benefit from tighter
    # bounds than Manski-natural can give. Per CLAUDE.md "don't design for
    # hypothetical future requirements" — speculative implementation is
    # explicitly out of scope.
    #
    # Which is a claim about today, and the version of this note it
    # replaces outlived its own truth: it listed the monotonicity bound as
    # an unbuilt stub for as long as that bound had been built. Whether a
    # route accepts a method is the member's own business now
    # (:attr:`themis.gaps.Route.answered_by`); whether anything PRODUCES
    # one is this note's, and only a run can say.
    FRONTDOOR_PARTIAL = "frontdoor_partial"  # Tian 2002 partial front-door


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
    distributions a client would need to evaluate the expressions — each as
    a statement, because an entry says which distribution AND what about it
    (how many cells the table has), and while it was one string the second
    half was glued to the first with a ``#``.

    `notes` is what is true of this interval that no other field carries —
    the width, the size of the response-function partition, which end an
    assumption moved, or that a sharper method was declined on size. A
    SEQUENCE, because it always was: a fourth author appended its sentence
    to whatever the method had written, with a space, and a list spelled as
    a string is a list nothing can add to without knowing what is already
    in it.

    Both hold statements rather than sentences: a token, a vocabulary and
    this occasion's facts, assembled where the reader's language is known.
    Typed ``dict`` rather than ``themis.language.Statement`` because this
    module is below that one — the type is the writer's evidence of intent,
    and what comes back off an envelope is a plain mapping.

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
    data_required: tuple[dict, ...] = ()
    width_when_uninformative: bool = False
    notes: tuple[dict, ...] = ()
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
