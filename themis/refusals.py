"""Why a number was refused, named once.

Refusing is a first-class answer here: an estimator that cannot honestly
produce a number says so in a structured ``estimator_failure`` block
rather than shipping a biased one. ``failure_type`` is what makes that
block machine-readable — the field exists, in its own words, "so the
caller can branch on the cause without parsing free-form messages".

Branching needs the causes to be a known set, and they were not. The
species was a free-form string, the first positional argument of
:class:`EstimatorFailure`, written at each raise across eighteen
estimator modules; the result schema carried a second, hand-copied list
of fourteen values. Nothing held the two together, so sixty-four species
came into being and fifty of them never reached the schema. An envelope
carrying one of those fifty fails Themis's own schema — and every public
``verify`` entrance validates first, so those refusals could not be
audited at all.

It is the familiar shape: a semantic fact with no first-class
representation degrades into a convention, and a convention that drifts
does not raise. So the species live here, the exception that carries one
lives here beside them, and the schema's enum is checked against this
registry rather than maintained next to it.

They are an ``enum`` rather than a list of module constants, which closes
the half a registry cannot reach from inside. Gathering the constants
into an ``ALL`` set told us this file was complete; nothing told us that
``refusals.NOT_IDENTIFED`` is not a species, because a module attribute
is looked up only when its line runs — and the line that names a refusal
is, by construction, the branch no test took. Membership is structural
now: the class is the registry, ``Refusal(name)`` is the lookup, a
misspelt species is a name that does not exist rather than a line waiting
to raise, and ``@unique`` refuses two names for one reason at import,
where the enum would otherwise quietly make the second an alias.

A species also declares its :class:`Kind`, because "no number" is not one
answer but five, and which one it is decides what the reader should do
next: fix the graph, get more data, wait for us to build it, correct the
request, or simply retry. The kind rides out on the envelope, stamped
from here at the exit — a consumer that had to map sixty-nine species
onto those five itself would be keeping a second copy of this file, in
TypeScript or in a prompt, and it would drift the way the schema's enum
drifted.

**This is the estimator's refusal, not the narrative extractor's.**
:mod:`themis.upstream.narrative_merge` carries its own ``refusals`` — a
language model declining to propose an edge it was asked about — which
shares the word and nothing else.
"""
from __future__ import annotations

import string
from collections.abc import Mapping
from enum import unique

from . import language
from .types import EnvelopeName, ResultStatus, envelope_scalar

# Both enums below end up as fields of ``estimator_failure``, so both obey
# the envelope rule :class:`~themis.types.EnvelopeName` states: copies and
# pickles come back as the plain name.


@unique
class Kind(EnvelopeName):
    """What the reader should do about a refusal.

    The distinction a consumer acts on. Declared beside the species by
    whoever adds it, because only the estimator knows whether it stopped
    at the graph, at the data, or at the edge of what it implements — and
    declared there once, so no raise site and no reader has to decide it.

    Each member also declares :attr:`outcome`: where a refusal is the WHOLE
    of a result, what happened to the query. It was decided at the catch
    site until #434, and a catch site sees an exception FAMILY — the
    counterfactual solver's spans nine species over four kinds, and the one
    status those two handlers wrote fits one of the nine.
    """

    outcome: ResultStatus
    """The query's status when this refusal is all the result contains.

    Deliberately COARSER than the kind: several kinds share an outcome, and
    that is what keeps this from being a second copy of the kind on every
    refused result (the shape #345 removed). The kind says whose limitation
    it is; the status says what became of the query, and a reader who wants
    to know which of "get more data" and "fix your input" applies reads the
    kind, which is the field that answers it.

    It applies only where the refusal is the whole result. A result that
    also carries an identification answer has a status about THAT — the
    data end's refusals ride results whose status says the structural
    question was answered, or that a gap in it remains, and neither is a
    statement about the refusal.
    """

    def __new__(cls, value: str, outcome: ResultStatus) -> "Kind":
        member = str.__new__(cls, value)
        member._value_ = value
        member.outcome = outcome
        return member

    GRAPH = ("graph", ResultStatus.NEEDS_INVESTIGATION)
    """The causal structure does not permit this quantity. More of the same
    data will not help; the graph or the query has to change."""

    DATA = ("data", ResultStatus.NEEDS_INVESTIGATION)
    """The structure permits it and this sample cannot support it — an empty
    stratum, a singular design, too few rows. Different data would work."""

    UNBUILT = ("unbuilt", ResultStatus.OUTSIDE_LANGUAGE)
    """The question is well-posed and identified, and Themis has not built
    this case. An honest gap, not an error.

    The one kind whose outcome is ``outside_language``, and it is what that
    status was already telling readers: "not that the data are short — the
    form of the question has no representation here yet"."""

    REQUEST = ("request", ResultStatus.NEEDS_INVESTIGATION)
    """The request or an input the caller supplied is malformed or
    inconsistent with the data. The caller changes something and retries.

    Sharing ``needs_investigation`` with the two above is a declared cost:
    the status alone does not separate "get more data" from "fix what you
    sent". Giving this kind a status of its own would make the map
    injective, and an injective map from kind to status is a second copy of
    the kind — the reader's own field for that question is ``kind``."""

    BACKEND = ("backend", ResultStatus.NEEDS_INVESTIGATION)
    """A numeric routine did not return an answer. No verdict has been passed
    on the question, the graph, or the data — which is also why ``unknown``
    files here: it diagnoses nothing, and a kind that claimed more would be
    claiming it on ``unknown``'s behalf.

    Its outcome is the least wrong of the seven rather than a fitting one,
    and it is unexercised: no refusal of this kind reached the kernel exit
    in a full suite run. The day one does is the day to ask whether "the
    tool broke and nothing was learned" needs saying."""


@unique
class Remedy(EnvelopeName):
    """A route past ONE refusal, on the occasion it was raised.

    :class:`Kind` answers "what now" per species — five answers, declared
    once beside the species. This answers it per RAISE SITE, and the two are
    different questions because the same species is raised by estimators
    whose routes out differ: ``overlap_insufficient`` is raised at five
    sites, and the way past it is a column that has to vary at four of them
    and a randomised design at the fifth. A species sentence cannot say
    that, and the sites that knew it wrote it into prose of their own —
    English prose, at the end of a description, in a report that is
    otherwise the reader's language and behind no gate at all (#432).

    So the route is a WORD and its object, not a sentence. The member is
    what the envelope carries and is in no language; the object is a name
    the occasion already has — a column, a parameter, a method — and is in
    no language either. The sentence is assembled where the reader's
    language is known, which is the only place that can know it.

    A member takes exactly one object or none, and which is fixed by the
    member rather than by the caller: a template with a hole nobody fills
    reaches the reader with a brace in it.
    """

    template: language.Words
    """This route's sentence, by language, with at most one ``{subject}``."""

    def __new__(cls, value: str, template: language.Words) -> "Remedy":
        member = str.__new__(cls, value)
        member._value_ = value
        member.template = template
        return member

    @property
    def takes_object(self) -> bool:
        """Whether this route names something, or is complete on its own."""
        return any("{subject}" in text for text in self.template.values())

    SUPPLY_DATA_VARIATION = (
        "supply_data_variation",
        {"zh": "需要 {subject} 在数据里取到不止一个值",
         "en": "supply data in which {subject} takes more than one value"},
    )
    SUPPLY_DATA_STRATUM = (
        "supply_data_stratum",
        {"zh": "需要覆盖 {subject} 这一层的数据",
         "en": "supply data covering the stratum {subject}"},
    )
    SUPPLY_INPUT = (
        "supply_input",
        {"zh": "把 {subject} 作为参数传进来",
         "en": "pass {subject}"},
    )
    CHANGE_INPUT = (
        "change_input",
        {"zh": "改一下传给 {subject} 的值",
         "en": "change what you passed for {subject}"},
    )
    USE_METHOD = (
        "use_method",
        {"zh": "改用 {subject}", "en": "use {subject} instead"},
    )
    CHANGE_DESIGN = (
        "change_design",
        {"zh": "这批数据本身给不出这个对比，要一个能制造它的设计——随机化实验，"
               "或图里一个工具变量",
         "en": "these data cannot produce the contrast; it takes a design "
               "that creates one — a randomised experiment, or an instrument "
               "on the graph"},
    )


#: Every route by the token an envelope carries. A lookup rather than
#: ``Remedy(token)`` for the reason :data:`BY_NAME` is one for species: a
#: member carries more than its value, so calling the class is calling a
#: constructor that wants the rest of it.
REMEDY_BY_NAME: dict[str, Remedy] = {str(m): m for m in Remedy}


def _remedy(remedy) -> Remedy:
    """The route by that name, or a refusal to proceed without one."""
    member = REMEDY_BY_NAME.get(str(remedy))
    if member is None:
        raise ValueError(
            f"unregistered remedy {str(remedy)!r}; declare it in "
            f"themis.refusals.Remedy beside the others, with its sentence "
            f"in every language this build answers in"
        )
    return member


def remedy_word(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """What one route says, hole and all.

    The pair to :func:`route`: this is the member's own sentence and takes
    no occasion, that one is the occasion's and cannot be had without it.
    A surface with a route in hand fills the hole; a surface holding the
    vocabulary itself — a glossary, or a check comparing another surface's
    copy of it — is looking at what fills it from the outside, and gets the
    template rather than a guess at what might have gone there. The
    outcome-error designs already reach a reader this way, through a table
    that carries ``{factor}``, and one shape for "a member that is a
    sentence with a hole" is worth more than two.
    """
    member = _remedy(value)
    # A language this route has no text in is answered the way
    # :func:`themis.language.gloss` answers an unlisted value — through the
    # one door that says a stand-in is one. A name the reader has to look
    # up beats silence and beats a confident sentence in the wrong
    # language; a name that cannot be told from a name the sentence is
    # ABOUT is what that door exists to stop.
    return language.say(member.template, lang, unknown=language.absent(
        "no_word_for_this_token", lang, token=str(member)))


def route(remedy, subject=None,
          lang: language.Lang | str = language.DEFAULT) -> str:
    """One route past a refusal, in the reader's language.

    Answers from the token as readily as from the member, because a token
    is what comes back off an envelope and a surface reading a result has
    nothing else. An unregistered token raises rather than rendering: unlike
    a species, whose sentence may honestly still be unwritten, a route this
    build has never heard of is a route it cannot describe, and a brace or a
    bare token in a reader's sentence is worse than the field being absent.
    """
    member = _remedy(remedy)
    if member.takes_object != (subject is not None):
        raise ValueError(
            f"{member} {'takes' if member.takes_object else 'takes no'} "
            f"subject; got {subject!r}"
        )
    slots = {} if subject is None else {"subject": language.slot(subject, lang)}
    return language.fill(member.template, lang, **slots)


@unique
class Refusal(EnvelopeName):
    """One named reason an estimator produced no number.

    A ``StrEnum``, so a species is usable wherever its name was: in the
    envelope, in a comparison, through ``json.dumps``. What it adds is
    that the name exists in exactly one place, and that ``kind`` and
    ``says`` travel with it instead of living in whichever message
    happened to be raised.
    """

    kind: Kind
    """Which of the five answers to "what now" this species gives."""

    says: str
    """What it means, for whoever adds the next species beside it. Not the
    reader's sentence: that is the occasion's, and it is the ``reason`` on
    the block."""

    def __new__(cls, value: str, kind: Kind, says: str) -> "Refusal":
        species = str.__new__(cls, value)
        species._value_ = value
        species.kind = kind
        species.says = says
        return species

    # --- the graph does not permit it -----------------------------------------
    NOT_IDENTIFIED = (
        "not_identified",
        Kind.GRAPH,
        "the strategy effect is not identified by the g-formula — "
        "sequential exchangeability fails, so the number would be biased",
    )
    DO_RISK_NOT_IDENTIFIABLE = (
        "do_risk_not_identifiable",
        Kind.GRAPH,
        "P(Y=1|do(X)) is not back-door identifiable from the "
        "observational distribution on this graph",
    )
    #: Strictly the stronger claim, and a separate name because the site
    #: above establishes only the weaker one. A door that tried back-door
    #: alone cannot say the effect is out of reach; a door that ran the
    #: whole cascade can, and a reader who is told the weaker thing goes
    #: looking for the instrument that was already tried.
    DO_RISK_NOT_IDENTIFIABLE_BY_ANY_ROUTE = (
        "do_risk_not_identifiable_by_any_route",
        Kind.GRAPH,
        "P(Y=1|do(X)) is reached by none of the routes this estimator "
        "runs — no back-door adjustment set, no general-ID estimand for "
        "the arms, and no single instrument on the graph",
    )
    INTERVENTIONAL_RISK_NOT_IDENTIFIABLE = (
        "interventional_risk_not_identifiable",
        Kind.GRAPH,
        "the interventional risk a counterfactual cell is computed from "
        "is not identified here",
    )
    NOT_IDENTIFIABLE_BY_GENERAL_ID = (
        "not_identifiable_by_general_id",
        Kind.GRAPH,
        "Shpitser-Pearl ID returned a hedge: the effect is not "
        "point-identified non-parametrically on this ADMG",
    )
    NOT_IDENTIFIABLE_BY_IDC = (
        "not_identifiable_by_idc",
        Kind.GRAPH,
        "the same, for a conditional effect, through IDC",
    )
    NOT_IDENTIFIABLE_COUNTERFACTUAL = (
        "not_identifiable_counterfactual",
        Kind.GRAPH,
        "ID*/IDC* found no identifying expression for the counterfactual "
        "conjunction",
    )
    NOT_IDENTIFIABLE_PROXIMAL = (
        "not_identifiable_proximal",
        Kind.GRAPH,
        "the proximal criteria failed: the named proxies do not identify "
        "the effect through a bridge function",
    )
    NO_IDENTIFYING_DESIGN = (
        "no_identifying_design",
        Kind.GRAPH,
        "the effect is identified by none of the designs this package names "
        "— no back-door adjustment set, no front-door set, no instrument — "
        "so nothing that composes with one of them can be reached",
    )
    NOT_RECOVERABLE = (
        "not_recoverable",
        Kind.GRAPH,
        "the estimand is not recoverable under the declared selection or "
        "missingness mechanism",
    )
    IV_MODEL_REFUTED = (
        "iv_model_refuted",
        Kind.GRAPH,
        "the observed P(X,Y|Z) table violates the instrumental inequality, "
        "which witnesses that the declared instrument's own assumptions are "
        "refuted by the data",
    )
    #: The same conclusion on weaker evidence, and the difference matters
    #: to whoever has to act on it. The polytope is empty, so no type
    #: distribution reproduces the table — but outside the binary case the
    #: instrumental inequality is not known here to be sufficient, so there
    #: is no named inequality to point at. Filing the witnessed species
    #: without a witness would offer a citation that does not exist.
    IV_MODEL_INFEASIBLE = (
        "iv_model_infeasible",
        Kind.GRAPH,
        "no distribution over response types reproduces the observed table "
        "under the instrument's assumptions, and this build has no named "
        "inequality to witness which of them the data contradicts",
    )
    #: The outcome-error twin of REQUIRES_A_POINT_ESTIMATE: that one has a
    #: design and no estimate to take the split around, this one has an
    #: estimate's question and no design. Both are about what the split is
    #: taken AROUND, which is why neither is the plain "not identified" —
    #: a reader is being told why one assessment is missing, not that the
    #: query failed.
    NO_DESIGN_TO_SPLIT_AROUND = (
        "no_design_to_split_around",
        Kind.GRAPH,
        "the residual-variance split is taken around the design that "
        "identifies the effect, and this graph offers none for it to be "
        "taken around",
    )

    # --- this data cannot support it ------------------------------------------
    # Three species on one boundary, and four sites once had the first two
    # the wrong way round — each stating the other's definition in its own
    # message. The line is two questions asked in order. Are there rows at
    # all? If there are, is the contrast missing from the whole sample, or
    # only from inside a cell the formula sums over?
    #
    # The third is not a milder second. A column that never varies cannot
    # be estimated from anywhere, and the reader's move is to go and get
    # data. A stratum holding one arm sits among strata that hold both, so
    # a regression fills it from their slope and returns a number — which
    # is why this one had to be separable: it is the case where refusing
    # and answering are BOTH defensible, and the estimator has to say which
    # it did. Two sites stated it under the names above, on either side.
    INSUFFICIENT_SUPPORT = (
        "insufficient_support",
        Kind.DATA,
        "a stratum the identifying formula sums over has no rows — a "
        "positivity violation, so the sum is not the estimand. The cell "
        "exists in the formula and not in the data",
    )
    OVERLAP_INSUFFICIENT = (
        "overlap_insufficient",
        Kind.DATA,
        "a variable, an arm or a sampling point carries no contrast to "
        "estimate from ANYWHERE in this sample: the rows are there and "
        "they do not differ. A column at a single level is this",
    )
    NO_WITHIN_STRATUM_CONTRAST = (
        "no_within_stratum_contrast",
        Kind.DATA,
        "a stratum the identifying formula sums over holds rows and only "
        "one level of the column the term compares across, so the term is "
        "a model's extrapolation rather than a comparison the data made. "
        "The sample has the contrast; this cell does not. Said of the "
        "treatment by three standardising estimators and of the instrument "
        "by the stratified Wald — one arm, whichever column defines the arms",
    )
    # Three more on the same boundary, and each was being told under one of
    # the names above. The two questions that line asks — are there rows,
    # and do they differ — both answer "yes" here, and the refusal is still
    # right: a floor of rows is not a contrast, a row that is present but
    # incomplete is not a row the formula can use, and a cut that places
    # only some of the sample has not partitioned it.
    TOO_SPARSE_TO_ESTIMATE = (
        "too_sparse_to_estimate",
        Kind.DATA,
        "a place the estimator has to produce a number in holds rows, both "
        "arms and some variation, and fewer rows than the floor this "
        "estimator sets for speaking there. Not a positivity violation — "
        "the term is defined and the estimator declines to report it at "
        "this precision",
    )
    #: Measured on the cut rather than in it. ``too_sparse_to_estimate``
    #: reports a place that turned out thin once the sample was cut there;
    #: this one is decided BEFORE any stratum exists, from how many rows a
    #: level would get on average, and so it names a column and a rate
    #: rather than a stratum and a count. The two shared a name, and the
    #: comment above the site already drew the line the name did not: a
    #: sample too thin for a cut that would work on any sample this size is
    #: not a cut this build declines to enumerate.
    STRATA_WOULD_BE_TOO_THIN = (
        "strata_would_be_too_thin",
        Kind.DATA,
        "a conditioning column cuts the sample so fine that its strata "
        "would hold too few rows to estimate in, before any stratum has "
        "been formed. The limit is the sample's, not this build's",
    )
    NO_COMPLETE_CASE_ROWS = (
        "no_complete_case_rows",
        Kind.DATA,
        "a cell holds rows and every one of them is missing a value in a "
        "column the recovery formula reads. Distinct from an empty cell: "
        "the rows are there and what is absent is a column of theirs, "
        "which is the fact a missingness graph is supposed to route around",
    )
    ROWS_OUTSIDE_THE_STRATA = (
        "rows_outside_the_strata",
        Kind.DATA,
        "the strata cut from a covariate set hold only part of the sample, "
        "so weights normalised over them describe a different population "
        "than the one asked about. The remainder are not an empty cell — "
        "they carry values the cut has nowhere to put",
    )
    NO_FIRST_STAGE = (
        "no_first_stage",
        Kind.DATA,
        "the instrument does not move the treatment in this sample, so the "
        "contrast it induces divides by zero instead of scaling into an "
        "effect — the graph's relevance arrow is not visible in the data",
    )
    #: The same arithmetic over a record that does not carry column names,
    #: and that is the reason it is a second name rather than the same one.
    #: The moment record is the producer's transcription — the verifier
    #: re-derives from it without importing the producer — and it is
    #: sufficient for the NUMBER by design and not for the sentence. A
    #: species that promised to name the instrument could not keep the
    #: promise there; this one says what the record knows.
    JOINT_FIRST_STAGE_DEGENERATE = (
        "joint_first_stage_degenerate",
        Kind.DATA,
        "the instruments taken together explain no variation in the "
        "treatment, so the moment condition they define has no slope to "
        "solve for",
    )
    #: Not "the instrument does not move the treatment" — it does not move
    #: at all, once the conditioning set is taken out of it. The estimator
    #: would still solve and would still return a number; the number just
    #: would not depend on the instrument. That is a different thing to
    #: tell somebody than a weak first stage.
    INSTRUMENT_ABSORBED_BY_CONDITIONING = (
        "instrument_absorbed_by_conditioning",
        Kind.DATA,
        "the instrument has no variation left once the conditioning set is "
        "partialled out of it, so nothing in the answer would come from the "
        "instrument at all",
    )
    NO_RESIDUAL_VARIATION = (
        "no_residual_variation",
        Kind.DATA,
        "the structural residual is exactly zero on this sample, so a "
        "statistic that divides by it is 0/0. Not a singular design — the "
        "fit is perfect, and there is nothing left for it to explain",
    )
    NO_USABLE_RESAMPLE = (
        "no_usable_resample",
        Kind.DATA,
        "every bootstrap resample was degenerate for this estimator, so the "
        "interval has no draws to be a quantile of",
    )
    SAMPLE_TOO_SMALL = (
        "sample_too_small",
        Kind.DATA,
        "the sample is below the minimum this estimator will speak on",
    )
    EMPTY_OUTCOME = (
        "empty_outcome",
        Kind.DATA,
        "the outcome column has no observed values",
    )
    OUTCOME_DOES_NOT_VARY = (
        "outcome_does_not_vary",
        Kind.DATA,
        "the outcome column is constant or nearly so, and a fit of it "
        "returns a flat curve with zero-width intervals that a reader takes "
        "for 'no effect' — the twin of overlap_insufficient on the outcome "
        "side, where the treatment not moving is already a DATA refusal",
    )
    ADJUSTMENT_ALL_MISSING = (
        "adjustment_all_missing",
        Kind.DATA,
        "an adjustment column is never observed, so its marginal — which "
        "the standardisation weights by — cannot be formed",
    )
    RANK_DEFICIENT_DESIGN = (
        "rank_deficient_design",
        Kind.DATA,
        "the OLS design for a node is rank-deficient; a minimum-norm fit "
        "would be a choice among many, not the coefficient",
    )
    RANK_CONDITION_VIOLATED = (
        "rank_condition_violated",
        Kind.DATA,
        "P(W|Z,x) is singular or ill-conditioned: the proxies are not "
        "jointly informative enough to invert",
    )
    SINGULAR_DESIGN = (
        "singular_design",
        Kind.DATA,
        "the design covariance is singular — collinear covariates",
    )
    DEGENERATE_RECOVERED_EXPOSURE = (
        "degenerate_recovered_exposure",
        Kind.DATA,
        "a stratum recovers a non-positive true exposure probability, so "
        "the corrected distribution is not a distribution",
    )
    UNIT_UNDEROBSERVED = (
        "unit_underobserved",
        Kind.DATA,
        "the unit is missing a factual value that abduction needs to pin "
        "its exogenous term",
    )
    UNDEFINED_CONDITIONING_EVENT = (
        "undefined_conditioning_event",
        Kind.DATA,
        "the conditioning conjunction has probability zero, so what is "
        "asked for is undefined rather than unknown",
    )

    # --- Themis has not built this case ---------------------------------------
    INTRACTABLE_ESTIMAND = (
        "intractable_estimand",
        Kind.UNBUILT,
        "the identified estimand has too high a treewidth to evaluate by "
        "variable elimination — beyond the plug-in's reach, not wrong",
    )
    RESPONSE_MODEL_TOO_LARGE = (
        "response_model_too_large",
        Kind.UNBUILT,
        "the response-function partition these cardinalities imply has more "
        "types than the bounds LP is run at — the sharp interval exists, "
        "this package declines to compute it here",
    )
    REQUIRES_BACKDOOR_IDENTIFICATION = (
        "requires_backdoor_identification",
        Kind.UNBUILT,
        "this correction composes with back-door standardisation, and the "
        "query is identified here by some other route — front-door or an "
        "instrument — that it has not been built onto",
    )
    REQUIRES_A_POINT_ESTIMATE = (
        "requires_a_point_estimate",
        Kind.UNBUILT,
        "this disclosure is taken around a coefficient the answering "
        "estimator produced, and the query was answered with something other "
        "than a point — there is nothing for the split to be taken around",
    )
    TOO_MANY_JOINT_TREATMENTS = (
        "too_many_joint_treatments",
        Kind.UNBUILT,
        "the joint plug-in enumerates a saturated basis over the treatment "
        "vector, and past a small number of treatments that basis is larger "
        "than any sample identifies",
    )
    # Three species stood here — a mediator with fractional values, one
    # with more levels than the sum could afford, and a set whose
    # combinations were too many. All three said the same thing in the end:
    # this front door cannot be answered by summing over mediator strata.
    # That is true and it was never the question, because the front-door
    # formula needs P(M | X) as a weight and not as a curve, and under a
    # binary treatment each arm's own rows are that weight. So the three
    # facts became one fork in the road (``frontdoor.exactly_summable``) and
    # stopped being reasons to refuse. A species no route can produce is a
    # sentence the vocabulary promises and cannot say.
    DIFFERENTIAL_COMBINED_MISCLASSIFICATION_DEFERRED = (
        "differential_combined_misclassification_deferred",
        Kind.UNBUILT,
        "differential misclassification of exposure AND outcome together "
        "is a different correction than either alone, and is not built",
    )
    TREATMENT_NOT_BINARY = (
        "treatment_not_binary",
        Kind.UNBUILT,
        "this estimator is binary-treatment only",
    )
    #: Not ``UNBUILT`` beside the one above, and the difference is the whole
    #: point: there the tool has no form for the question, here the tool has
    #: the form and the declaration did not use it. The caller adds the
    #: treatment to a sieve they already wrote and the curve is answerable,
    #: which is a retry rather than a boundary.
    BRIDGE_CANNOT_VARY_WITH_THE_TREATMENT = (
        "bridge_cannot_vary_with_the_treatment",
        Kind.REQUEST,
        "a curve asks what the bridge is at each level, and the declared "
        "sieve does not let it depend on the treatment at all",
    )
    #: ``UNBUILT`` and not ``REQUEST``: nothing the caller writes fixes it.
    #: The treatment bridge's identity carries an indicator I(A=a), so it is
    #: defined at levels the sample visits, and a continuous dose visits
    #: none of the ones a curve is drawn at.
    TREATMENT_BRIDGE_NEEDS_ROWS_AT_EACH_LEVEL = (
        "treatment_bridge_needs_rows_at_each_level",
        Kind.UNBUILT,
        "the treatment bridge is identified level by level through an "
        "indicator, and a level no row sits at has nothing to weight",
    )
    #: The exact mirror of ``bridge_cannot_vary_with_the_treatment``, one
    #: bridge over. There the span could not vary with the level and had to;
    #: here it need not and must not, because solving per level already
    #: gives every level its own coefficients. Two species and not one with
    #: a direction, because the fix is opposite and a reader acting on the
    #: wrong one makes the other true.
    TREATMENT_BRIDGE_IS_ALREADY_PER_LEVEL = (
        "treatment_bridge_is_already_per_level",
        Kind.REQUEST,
        "the treatment bridge is solved once per level, so naming the "
        "treatment in its sieve adds columns that are constant inside every "
        "arm",
    )
    #: ``DATA`` and not ``UNBUILT``: the test exists and this sample cannot
    #: carry it, which is a different sentence from "Themis has not built
    #: this" and points at a different remedy — a finer proxy or a treatment
    #: with more levels, both of which are things to go and get.
    NO_DEGREES_OF_FREEDOM_TO_TEST_THE_NULL = (
        "no_degrees_of_freedom_to_test_the_null",
        Kind.DATA,
        "the null is an over-identifying restriction, and there are as many "
        "unknowns as moments — nothing is left over to test with",
    )
    #: Distinct from ``rank_condition_violated``, which is about the per-x
    #: channel the POINT estimate inverts. This one is about the stacked
    #: channel the TEST projects on, and the two can disagree: a per-x matrix
    #: can be singular while the stack over all x has full row rank, which is
    #: the whole reason the test survives where the point estimate does not.
    STACKED_CHANNEL_IS_RANK_DEFICIENT = (
        "stacked_channel_is_rank_deficient",
        Kind.DATA,
        "the proxy channel stacked over the treatment levels does not have "
        "full row rank, so the null's restriction has no direction to be "
        "tested along",
    )
    TREATMENT_LEVELS_DIFFER = (
        "treatment_levels_differ",
        Kind.UNBUILT,
        "a joint intervention's corner puts every treatment at one shared "
        "pair of values, and these treatments do not present one — each can "
        "be binary and still be binary on a different pair, which is what "
        "leaves the corner undefined, and is not the one above",
    )
    EXPOSURE_NOT_CONTINUOUS = (
        "exposure_not_continuous",
        Kind.UNBUILT,
        "regression calibration is for a continuous exposure; a nearly "
        "discrete one wants the confusion-matrix correction instead",
    )
    OUTCOME_NOT_BINARY = (
        "outcome_not_binary",
        Kind.UNBUILT,
        "this estimator is binary-outcome only",
    )
    # instrument_not_binary lived here, and its own description said why it
    # would not last: "a multi-valued one is a larger enumeration". A larger
    # enumeration is something to enumerate, not something to decline, and
    # the response-function model now sizes itself from the cardinalities.
    # What can still stop it is the size, which is RESPONSE_MODEL_TOO_LARGE.
    OUTCOME_NOT_CONTINUOUS = (
        "outcome_not_continuous",
        Kind.UNBUILT,
        "classical additive outcome error is defined for a continuous "
        "outcome; a discrete one wants the confusion-matrix correction",
    )
    CONTINUOUS_OUTCOME = (
        "continuous_outcome",
        Kind.UNBUILT,
        "confusion-matrix correction needs a discrete outcome with few "
        "enough states to name",
    )
    CONTINUOUS_ADJUSTMENT = (
        "continuous_adjustment",
        Kind.UNBUILT,
        "this correction standardises over discrete strata, and an "
        "adjustment covariate has too many distinct values",
    )
    ADJUSTMENT_NOT_DISCRETE = (
        "adjustment_not_discrete",
        Kind.UNBUILT,
        "the same, for the missingness recovery formula",
    )
    #: One COLUMN past the per-column cap. The two caps this estimator sets
    #: are not one fact: a column with sixty levels is coarsened or dropped,
    #: and a conditioning SET whose product overruns the total is repaired
    #: by dropping one of several columns none of which is individually at
    #: fault. A sentence naming ``{column}`` cannot say the second, so the
    #: name that said both said neither.
    CONDITIONING_TOO_FINE = (
        "conditioning_too_fine",
        Kind.UNBUILT,
        "the stratified Wald aggregates over the cells of the conditioning "
        "set, and one column of it takes more levels than this build will "
        "enumerate",
    )
    TOO_MANY_STRATA = (
        "too_many_strata",
        Kind.UNBUILT,
        "the same aggregation, refused for the conditioning set as a whole: "
        "the product of its columns' levels is past the number of strata "
        "this build will enumerate, with no single column at fault",
    )
    MISMEASURED_COVARIATE_NOT_CONTINUOUS = (
        "mismeasured_covariate_not_continuous",
        Kind.UNBUILT,
        "a covariate declared mismeasured is not continuous, and only the "
        "continuous correction is built for covariates",
    )
    CAUSE_OR_EFFECT_NOT_BINARY = (
        "cause_or_effect_not_binary",
        Kind.UNBUILT,
        "probabilities of causation are defined here for binary cause and "
        "effect",
    )
    COUNTERFACTUAL_CELL_NOT_BINARY = (
        "counterfactual_cell_not_binary",
        Kind.UNBUILT,
        "the counterfactual cell estimator is boolean-only",
    )
    # ``counterfactual_cell_out_of_scope`` stood here, and it was the
    # counterfactual solver's default: a name meaning "one of ten things
    # this solver will not do", carried by the base exception so no raise
    # site had to choose. It never had a sentence in SAYS — it could not,
    # because ten facts have no one sentence — and it survived only
    # because every one of those sites was still writing its own. Each of
    # them names its own species now, and nothing is left to file this.
    COUNTERFACTUAL_CELL_CROSS_VARIABLE = (
        "counterfactual_cell_cross_variable",
        Kind.UNBUILT,
        "the cell estimator intervenes on one variable at two values; a "
        "cell across two different variables is a different quantity",
    )

    # --- the request has to change --------------------------------------------
    # ``invalid_input`` lived here, and its own description said what was
    # wrong with it: "the catch-all for a malformed request whose own
    # message says what was wrong". Twenty-five sites filed it, and because
    # the name said nothing, all twenty-five wrote their own sentence — in
    # one language, each in its own words for the same handful of faults.
    # ``invalid_confusion_matrix`` was the same shape one scale down: nine
    # sites, seven distinct faults, one name.
    #
    # The faults themselves are not twenty-five. They are the ordinary ways
    # an argument can fail its contract, and naming them is what lets one
    # sentence per fault serve every site that meets it (#405). Four of the
    # matrix's nine turned out to BE two of these, which is the measure of
    # how much of the old catch-all was really one thing.
    UNKNOWN_OPTION = (
        "unknown_option",
        Kind.REQUEST,
        "an option admitting a closed set of values was given one outside "
        "it. The set belongs to the estimator, and the refusal names it — "
        "which is what the caller cannot look up from the value they sent",
    )
    TOO_FEW_INPUTS = (
        "too_few_inputs",
        Kind.REQUEST,
        "an argument that takes several things was given fewer than the "
        "method is defined for — one mediator for a chain, one instrument "
        "for an over-identification test",
    )
    DUPLICATE_INPUT = (
        "duplicate_input",
        Kind.REQUEST,
        "an argument whose entries have to name different things names one "
        "of them twice. Not a harmless repetition: the entries index a "
        "vector of estimands, so a repeat silently changes what is asked",
    )
    INPUTS_DISAGREE = (
        "inputs_disagree",
        Kind.REQUEST,
        "two arguments that have to describe the same set describe "
        "different ones — a marginal declared over variables the "
        "adjustment set does not hold, a values list of another length "
        "than the things it values",
    )
    MALFORMED_ARGUMENT = (
        "malformed_argument",
        Kind.REQUEST,
        "an argument's structure is not the one the method reads. The "
        "refusal carries the shape it does read, because a caller who got "
        "it wrong has no way to derive that from the rejection",
    )
    #: Nothing arrived, which is not the same as something arriving and
    #: failing a test — and every test written to judge a value judges the
    #: absence of one too unless this name is between them. A reader told
    #: "the variance you declared is not positive" about a variance they
    #: never declared goes looking for the number in their own call.
    ARGUMENT_NOT_GIVEN = (
        "argument_not_given",
        Kind.REQUEST,
        "an argument the estimator needs was not named at all, so there is "
        "no value for any of its tests to have judged",
    )
    ARGUMENT_NOT_A_NUMBER = (
        "argument_not_a_number",
        Kind.REQUEST,
        "an argument that has to be a finite number is not one. A "
        "structural coefficient a residual is taken around cannot be NaN "
        "and cannot be a string",
    )
    PROBABILITIES_DO_NOT_SUM = (
        "probabilities_do_not_sum",
        Kind.REQUEST,
        "a declared distribution's probabilities do not sum to one, so it "
        "is not a distribution and the weights built from it would not be "
        "weights",
    )
    #: Not the same fault, and not the same repair: a table that sums to one
    #: with a negative cell in it and a table whose cells are each in [0, 1]
    #: but sum to 1.4 are wrong in different places. ``matrix_not_
    #: probabilities`` says this of a confusion matrix and names the
    #: correction that inverts it, which is a promise a solver handed a
    #: single number cannot keep.
    NOT_A_PROBABILITY = (
        "not_a_probability",
        Kind.REQUEST,
        "a quantity declared to be a probability lies outside [0, 1]",
    )
    ARGUMENT_MISSING_FOR_DESIGN = (
        "argument_missing_for_design",
        Kind.REQUEST,
        "the declared design rests on a premise about something the caller "
        "has not named, so the assessment would disclose a premise with a "
        "hole in it",
    )
    ARGUMENT_FOREIGN_TO_DESIGN = (
        "argument_foreign_to_design",
        Kind.REQUEST,
        "an argument was supplied that the declared design has no place "
        "for. Ignoring it would leave the caller holding a premise they "
        "believe they declared, which is worse than refusing",
    )
    MODEL_NEEDS_BINARY = (
        "model_needs_binary",
        Kind.REQUEST,
        "the model the caller named is defined for binary columns and was "
        "pointed at columns that are not. Named rather than routed around: "
        "the automatic choice would have sent this design elsewhere, and "
        "silently doing so would answer a question nobody asked",
    )
    OPTION_ANSWERS_ANOTHER_QUESTION = (
        "option_answers_another_question",
        Kind.REQUEST,
        "the option the caller named computes a different estimand from "
        "the one this query asks for — a marginal contrast where the query "
        "conditions. Not a numerical difference; a different quantity",
    )
    MATRIX_WRONG_SHAPE = (
        "matrix_wrong_shape",
        Kind.REQUEST,
        "a declared matrix is not the size the states it maps between "
        "require",
    )
    MATRIX_NOT_NUMERIC = (
        "matrix_not_numeric",
        Kind.REQUEST,
        "a declared matrix is not a numeric array at all",
    )
    MATRIX_NOT_FINITE = (
        "matrix_not_finite",
        Kind.REQUEST,
        "a declared matrix holds entries that are not finite numbers",
    )
    MATRIX_NOT_PROBABILITIES = (
        "matrix_not_probabilities",
        Kind.REQUEST,
        "a declared matrix holds entries outside [0, 1], so they are not "
        "the probabilities the correction inverts",
    )
    MATRIX_NOT_COLUMN_STOCHASTIC = (
        "matrix_not_column_stochastic",
        Kind.REQUEST,
        "a declared matrix's columns do not sum to one. Each column is one "
        "true state's distribution over observed states, so a column that "
        "does not sum to one describes a state whose observations "
        "sometimes go nowhere",
    )
    # Five that measure something the CALLER declared. A supplied confusion
    # matrix — one of them, or one per level of a differential axis — a
    # declared latent cardinality, a declared error variance and the
    # treatment vector an entry point was handed are none of them properties
    # of the sample, so DATA — "different data would work" — is a promise
    # they cannot keep; and the single-treatment case NOT_A_JOINT_INTERVENTION
    # called UNBUILT is one this package builds, by another route.
    #
    # The declaration-versus-data comparison is REQUEST's own definition, and
    # the repository already reads it that way once:
    # ``outcome_error_exceeds_residual_variance`` is the outcome-side twin of
    # DEGENERATE_RELIABILITY, and it is REQUEST.
    SINGULAR_CONFUSION_MATRIX = (
        "singular_confusion_matrix",
        Kind.REQUEST,
        "the supplied confusion matrix is non-invertible: as a measurement "
        "model it carries no information about the true value, and no "
        "quantity of data recovers what it does not distinguish",
    )
    # Its per-level twin, and a separate species because the CONSEQUENCE is
    # what a species asserts: one matrix failing to invert stops the whole
    # correction, and one LEVEL's matrix failing stops it in that level while
    # the rest of the axis is fine. A reader told the first when the second
    # is true has been told the correction is unavailable when what is
    # unavailable is one stratum of it.
    SINGULAR_CONFUSION_MATRIX_IN_STRATUM = (
        "singular_confusion_matrix_in_stratum",
        Kind.REQUEST,
        "one level's matrix in a differential misclassification model is "
        "non-invertible, so the correction is undefined in that level; no "
        "other level's matrix can stand in for it, because that they differ "
        "is exactly what a differential model claims",
    )
    DEGENERATE_RELIABILITY = (
        "degenerate_reliability",
        Kind.REQUEST,
        "one column's declared measurement-error variance meets or exceeds "
        "the variation there is to correct in it, so its reliability is not "
        "positive — the declaration contradicts the data in that column",
    )
    #: The joint fact the per-column one is necessary but not sufficient
    #: for, and the code that raises it already said so in a comment. No
    #: column is degenerate on its own here, so a reader sent to look for
    #: the offending column would find none: what is over-declared is the
    #: set of variances together, against the joint variation.
    CORRECTED_DESIGN_NOT_POSITIVE_DEFINITE = (
        "corrected_design_not_positive_definite",
        Kind.REQUEST,
        "every column's reliability is positive and the corrected design "
        "matrix still is not positive definite, so the declared variances "
        "taken together exceed the joint variation in the data",
    )
    PROXY_CARDINALITY_MISMATCH = (
        "proxy_cardinality_mismatch",
        Kind.REQUEST,
        "the proxies do not each present the number of levels the declared "
        "latent cardinality says they have; the declaration and the data "
        "disagree, and the matrix-inversion formula needs them to agree",
    )
    #: The other half of the one above, and it only became sayable once a
    #: coarsening could be declared: the caller DID say how to fold the
    #: proxy, and the folding does not fit the levels the data holds. Not
    #: the same species — the first is "you have not said", this is "what
    #: you said and what is here do not line up" — and a reader given the
    #: first when the second is true would go and write a field they have
    #: already written.
    COARSENING_DOES_NOT_PARTITION_THE_PROXY = (
        "coarsening_does_not_partition_the_proxy",
        Kind.REQUEST,
        "a declared proxy coarsening and the levels the column actually "
        "holds do not line up — every observed level has to fall in exactly "
        "one group and every group has to name levels that are there, or "
        "the folded channel is not a recoding of this column",
    )
    #: The third of the family: the grouping is a partition of the right
    #: levels and there is the wrong NUMBER of groups. Its own species
    #: because the two fields that disagree are both the caller's and
    #: neither is the data's, so a reader is being asked which of their own
    #: two statements to move.
    COARSENING_GROUP_COUNT_IS_NOT_K = (
        "coarsening_group_count_is_not_k",
        Kind.REQUEST,
        "a declared proxy coarsening makes some number of groups other than "
        "the cardinality the query posits for the latent; the groups ARE "
        "the latent's states, so their count is not free",
    )
    #: The continuous twin of ``rank_condition_violated``, and NOT that
    #: species: there the channel is singular and no lever the caller holds
    #: changes it, so the sentence ends "not proximal-recoverable on this
    #: data". Here the ill-posedness is intrinsic — a Fredholm equation of
    #: the first kind always has it — and what failed is this SIEVE at this
    #: PENALTY, both of which the caller declared and can move. A reader told
    #: the other species would abandon a question that has an answer.
    BRIDGE_ILL_POSED_AT_THIS_PENALTY = (
        "bridge_ill_posed_at_this_penalty",
        Kind.REQUEST,
        "the bridge equation is still ill-conditioned after the penalty in "
        "force: at this sieve dimension the data do not distinguish the "
        "basis functions, so what comes out is the penalty's choice among "
        "many solutions rather than the data's",
    )
    NOT_A_JOINT_INTERVENTION = (
        "not_a_joint_intervention",
        Kind.REQUEST,
        "the joint plug-in was asked for a joint effect of fewer than two "
        "treatments; the single-treatment case is built, by another route",
    )
    INVALID_MONOTONICITY = (
        "invalid_monotonicity",
        Kind.REQUEST,
        "a declared monotonicity direction is neither non-decreasing nor "
        "non-increasing",
    )
    STATES_INCOMPLETE = (
        "states_incomplete",
        Kind.REQUEST,
        "values occur in the data that the declared state list omits, so "
        "the correction would silently drop them",
    )
    #: Not "there are not two of them" — there are exactly two, and nothing
    #: in the pair says which one is the control arm. The correction reads
    #: the pair positionally into the columns of a matrix, so a pair it
    #: cannot order is a pair it would invert the wrong way round.
    ARM_ORDER_UNREADABLE = (
        "arm_order_unreadable",
        Kind.REQUEST,
        "a two-state arm pair carries nothing that says which state is the "
        "control, and the correction has to know which column of the matrix "
        "belongs to which arm",
    )
    DIFFERENTIAL_SPEC_INCOMPLETE = (
        "differential_spec_incomplete",
        Kind.REQUEST,
        "a differential-misclassification spec is missing a part it needs "
        "to say which matrix applies where",
    )
    DIFFERENTIAL_LEVELS_MISMATCH = (
        "differential_levels_mismatch",
        Kind.REQUEST,
        "the supplied matrices and the levels they are indexed by do not "
        "line up one to one",
    )
    #: Its neighbour, and not it: the matrices and the levels can line up
    #: perfectly with each other and still be indexed by levels the axis
    #: does not take. Counting is the first fault, naming the second, and
    #: the reader's next move differs — supply another matrix, or index
    #: the ones you have by the values that are actually there.
    DIFFERENTIAL_LEVELS_NOT_THE_AXIS_LEVELS = (
        "differential_levels_not_the_axis_levels",
        Kind.REQUEST,
        "the levels the differential spec is indexed by are not the levels "
        "the axis takes, so some level of the axis has no matrix of its own",
    )
    DIFFERENTIAL_BY_UNKNOWN = (
        "differential_by_unknown",
        Kind.REQUEST,
        "the axis the misclassification is said to differ by is not a "
        "variable that can carry it",
    )
    #: One clause of the same rule, and a different sentence: the axis IS a
    #: variable the correction conditions on — it is the very one this
    #: channel mismeasures, whose matrix is already indexed by its true
    #: state. "Not a variable that can carry it" would be false here.
    DIFFERENTIAL_BY_THE_MISMEASURED_VARIABLE = (
        "differential_by_the_mismeasured_variable",
        Kind.REQUEST,
        "the axis named is the variable this channel mismeasures, and its "
        "matrix is already indexed by that variable's true state",
    )
    DIFFERENTIAL_LEVEL_UNCOVERED = (
        "differential_level_uncovered",
        Kind.REQUEST,
        "a level occurring in the data has no confusion matrix supplied "
        "for it",
    )
    MISMEASURED_VARIABLE_NOT_IN_DESIGN = (
        "mismeasured_variable_not_in_design",
        Kind.REQUEST,
        "measurement error was supplied for a variable that is not in the "
        "design, so there is nothing to correct",
    )
    MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT = (
        "mismeasured_covariate_not_in_adjustment",
        Kind.REQUEST,
        "a covariate declared mismeasured is not in the adjustment set "
        "the effect was identified through",
    )
    MISSING_COLUMN = (
        "missing_column",
        Kind.REQUEST,
        "a column the query names is not in the data",
    )
    REFERENCE_MISSING_COLUMN = (
        "reference_missing_column",
        Kind.REQUEST,
        "the external unbiased reference sample is missing a column the "
        "recovery formula reweights by",
    )
    TARGET_VALUE_ABSENT = (
        "target_value_absent",
        Kind.REQUEST,
        "the target value the query asks about is not among the declared "
        "or observed states",
    )
    ATOM_NOT_IN_GRAPH = (
        "atom_not_in_graph",
        Kind.REQUEST,
        "an intervention or target atom is not a variable of the SCM",
    )
    INTERVENTION_IS_TARGET = (
        "intervention_is_target",
        Kind.REQUEST,
        "the intervention and the target are the same variable, so the "
        "counterfactual is its own assignment",
    )
    SIMEX_GRID_IS_NOT_A_LADDER = (
        "simex_grid_is_not_a_ladder",
        Kind.REQUEST,
        "the simulation grid has to start at zero and climb: the zero rung "
        "IS the uncorrected fit, and the extrapolation reads a decay",
    )
    SIMEX_GRID_IS_TOO_SHORT_FOR_THE_EXTRAPOLANT = (
        "simex_grid_is_too_short_for_the_extrapolant",
        Kind.REQUEST,
        "a family with as many parameters as rungs passes through every "
        "one of them and says nothing about where the curve goes next",
    )
    SIMEX_EXTRAPOLANT_HAS_A_POLE_AT_MINUS_ONE = (
        "simex_extrapolant_has_a_pole_at_minus_one",
        Kind.DATA,
        "the rational extrapolant fitted to this ladder is undefined at the "
        "very point the correction is read off",
    )
    BERKSON_SCATTER_EXCEEDS_RESIDUAL_VARIANCE = (
        "berkson_scatter_exceeds_residual_variance",
        Kind.REQUEST,
        "the declared scatter of the truth around the nominal exposure does "
        "not fit under the variation the data leave unexplained",
    )
    BERKSON_PRICE_HAS_NO_COEFFICIENT = (
        "berkson_price_has_no_coefficient",
        Kind.REQUEST,
        "what a Berkson error costs is scaled by the effect it rides on, so "
        "there is no price without one",
    )
    #: Four on the continuous DIFFERENTIAL correction, and the split is by
    #: what the reader does next. The first two are about the axis — one has
    #: an answer waiting (an error tracking an adjusted covariate is
    #: classical once that covariate is partialled out) and one does not.
    #: The last two are about the two declarations: whether they contradict
    #: EACH OTHER, which is settled before the data is read, and whether
    #: they contradict the SAMPLE, which is not.
    DIFFERENTIAL_AXIS_IS_AN_ADJUSTED_COVARIATE = (
        "differential_axis_is_an_adjusted_covariate",
        Kind.REQUEST,
        "an error tracking a covariate the design conditions on is classical "
        "once that covariate is partialled out, so the correction it needs is "
        "the ordinary one",
    )
    DIFFERENTIAL_AXIS_IS_NOT_THE_OUTCOME = (
        "differential_axis_is_not_the_outcome",
        Kind.UNBUILT,
        "the closed form is written for an error that tracks the outcome, and "
        "the axis named is neither that nor a covariate the design conditions "
        "on",
    )
    #: The same sentence from the other channel, and a species of its own
    #: rather than a shared one, because what the reader must WRITE differs:
    #: a mismeasured exposure's error may track the outcome, a mismeasured
    #: outcome's may track the exposure, and a species that named neither
    #: would leave both readers to work out which.
    DIFFERENTIAL_AXIS_IS_NOT_THE_EXPOSURE = (
        "differential_axis_is_not_the_exposure",
        Kind.UNBUILT,
        "the closed form is written for an outcome error that tracks the "
        "exposure, and the axis named is neither that nor a covariate the "
        "design conditions on",
    )
    DIFFERENTIAL_COEFFICIENT_EXCEEDS_THE_DECLARED_VARIANCE = (
        "differential_coefficient_exceeds_the_declared_variance",
        Kind.REQUEST,
        "the outcome-tracking part alone would contribute more variance than "
        "the whole declared error has, which leaves its classical part a "
        "negative one",
    )
    DIFFERENTIAL_CORRECTION_LEAVES_NO_TRUE_VARIANCE = (
        "differential_correction_leaves_no_true_variance",
        Kind.REQUEST,
        "the declared error and coefficient together leave the true exposure "
        "no variance to have a slope over",
    )
    BERKSON_AND_DIFFERENTIAL_ARE_INCOMPATIBLE_PREMISES = (
        "berkson_and_differential_are_incompatible_premises",
        Kind.REQUEST,
        "a Berkson error is independent of the recorded value, and an error "
        "tracking the outcome is not — the outcome depends on the truth, and "
        "the truth is the recorded value plus that error",
    )
    BERKSON_ANSWER_IS_NOT_THE_DESIGN_SLOPE = (
        "berkson_answer_is_not_the_design_slope",
        Kind.UNBUILT,
        "the identity that leaves the point uncorrected is about one "
        "functional — the ordinary slope of the outcome on the recorded "
        "exposure — and this query was answered with a different one",
    )
    SIMEX_PERTURBS_ONE_MISMEASURED_COLUMN = (
        "simex_perturbs_one_mismeasured_column",
        Kind.REQUEST,
        "simulation adds noise to the exposure; a second mismeasured column "
        "would need the two errors' covariance, which per-column variances "
        "do not carry",
    )
    #: "Absent or not positive" was two faults under one name, and the
    #: reader's next move is not the same for them: one supplies a number,
    #: the other corrects one. Absence is now counted where every other
    #: absent argument is counted.
    NON_POSITIVE_ERROR_VARIANCE = (
        "non_positive_error_variance",
        Kind.REQUEST,
        "a declared measurement-error variance is not a positive finite "
        "number, and the correction it scales is undefined",
    )
    #: Its sibling one field over. A variance may be declared with the
    #: degrees of freedom of the study that estimated it, and the interval
    #: then carries that study's uncertainty as well as the main sample's.
    #: A df of zero or less names no sampling distribution to draw from,
    #: which is a different claim from "known exactly" — and that claim is
    #: made by leaving the field out, not by writing a number that cannot
    #: be one.
    NON_POSITIVE_VALIDATION_DF = (
        "non_positive_validation_df",
        Kind.REQUEST,
        "a declared measurement-error variance carries degrees of freedom "
        "that are not a positive whole number; omit the field to say the "
        "variance is known exactly",
    )
    #: The same field one declaration over again, on the one that is a
    #: REGRESSION. δ may be declared with what the validation fit reported —
    #: its residual variance, the coefficient's standard error, and the
    #: degrees of freedom — and those are one study, so a subset of them
    #: names no distribution at all. One species for every way that
    #: declaration can be unusable rather than one per field: the caller's
    #: next move is the same in each, and it is to write the four numbers
    #: their study printed or none of them.
    TRACKING_STUDY_NOT_USABLE = (
        "tracking_study_not_usable",
        Kind.REQUEST,
        "a differential coefficient declared with the study that measured it "
        "is missing part of that study or carries a part that is not a "
        "positive number; declare the coefficient alone to say it is exact",
    )
    #: And the pair that cannot both be declared. Under the study shape the
    #: total error variance is DERIVED — σ²_0 + δ²·Var(Ỹ) — so a caller who
    #: supplies both has written one fact twice, and the day the two
    #: disagree there is no answer to which one the correction used.
    TRACKING_STUDY_AND_A_DECLARED_VARIANCE = (
        "tracking_study_and_a_declared_variance",
        Kind.REQUEST,
        "the total error variance is derived from a declared validation "
        "regression, so declaring it as well writes one fact twice",
    )
    #: The same field one declaration over. A confusion matrix may be
    #: declared as the tally the validation study actually produced, and the
    #: bootstrap then redraws it from that tally's Dirichlet. A tally that is
    #: not a rectangle of non-negative finite numbers names no multinomial
    #: to draw from — and normalising it first would hide the fault behind a
    #: complaint about a matrix the caller never wrote.
    VALIDATION_COUNTS_UNUSABLE = (
        "validation_counts_unusable",
        Kind.REQUEST,
        "a confusion matrix declared as a validation tally is not a "
        "rectangle of non-negative finite counts; declare the matrix "
        "itself to say it is known exactly",
    )
    #: Its sibling, and a separate species because the fault is a different
    #: one: the tally is well formed and one of its columns is empty. A true
    #: state no validation subject stood at was not measured at all, so that
    #: column of the matrix is not a proportion of anything.
    VALIDATION_STATE_NEVER_OBSERVED = (
        "validation_state_never_observed",
        Kind.REQUEST,
        "a validation tally has a true state no subject was observed at, so "
        "that column of the confusion matrix rests on no observation",
    )
    #: A differential matrix set declared both ways at once. Each level's
    #: matrix is one measurement of one channel, and a set that counts some
    #: levels in a study while fixing others produces an interval that is
    #: neither of the two things a reader could be told it is.
    MATRIX_SET_DECLARED_TWO_WAYS = (
        "matrix_set_declared_two_ways",
        Kind.REQUEST,
        "a differential confusion-matrix set declares some levels as a "
        "validation tally and others as exact; one channel is settled one "
        "way or the other",
    )
    OUTCOME_ERROR_EXCEEDS_RESIDUAL_VARIANCE = (
        "outcome_error_exceeds_residual_variance",
        Kind.REQUEST,
        "the declared outcome error variance exceeds the residual "
        "variance in the data — the declaration contradicts what is there",
    )
    EXTERNAL_DATA_REQUIRED = (
        "external_data_required",
        Kind.REQUEST,
        "the effect IS recoverable, with unbiased external data the call "
        "did not supply; the block names what to pass",
    )
    #: Its own definition said "either … or …", which is the confession
    #: (298) names: the interventional risk contradicting the observational
    #: joint and the declared monotonicity being refuted are two findings,
    #: and only the second was what the sentence here described. A reader
    #: told their monotonicity was refuted when the truth is that their two
    #: data sources disagree would go and drop an assumption that was never
    #: the problem.
    COUNTERFACTUAL_INPUTS_INFEASIBLE = (
        "counterfactual_inputs_infeasible",
        Kind.REQUEST,
        "the declared monotonicity is refuted by the data — no distribution "
        "satisfies both it and what was supplied. Which evidence refutes it "
        "is the occasion's, and travels as a word",
    )
    INPUTS_CONTRADICT_BY_CONSISTENCY = (
        "inputs_contradict_by_consistency",
        Kind.REQUEST,
        "an interventional risk and an observational joint that cannot both "
        "be true: consistency ties P(Y=1|do(x')) to the joint's own cells, "
        "and the supplied value falls outside the interval that leaves. No "
        "assumption is at fault here — the two sources disagree",
    )

    # --- a backend gave up ----------------------------------------------------
    CONVERGENCE_FAILURE = (
        "convergence_failure",
        Kind.BACKEND,
        "the underlying regressor raised rather than converged",
    )
    LINEAR_PROGRAM_FAILED = (
        "linear_program_failed",
        Kind.BACKEND,
        "the bounds program stopped without an optimum and without an "
        "infeasibility certificate, so whether the model is refuted is "
        "undecided — a solver not finishing is not a finding about the data",
    )
    MODEL_FIT_FAILED = (
        "model_fit_failed",
        Kind.BACKEND,
        "the same, for an outcome or mediator model on the full sample",
    )
    UNKNOWN = (
        "unknown",
        Kind.BACKEND,
        "the estimator failed in a way nothing has classified — the only "
        "species that admits the block does not know what it is saying",
    )


@unique
class Design(language.Word, vocabulary="singular_matrix"):
    """Which matrix a fit could not invert.

    ``singular_design`` was one fact — this matrix is singular on this
    sample, so the fit that needs it has no unique solution — told at seven
    sites in seven sentences, because the one thing that differed between
    them was a WORD and the occasion channel could only carry numbers. Each
    site therefore hard-coded its matrix into prose of its own, which made
    each of them another author of the species' sentence.

    A member is a NOUN PHRASE and nothing else. What its being singular
    costs is the species' sentence and is the same for all six, so a member
    that also explained the cost would be the second half of a sentence
    reaching a reader through a hole in the first — which reads, in both
    languages, as a subject that never arrives at its verb.
    """

    ROBUST_WEIGHT = ("robust_weight_matrix", {
        "zh": "有效 GMM 那一步用来加权的稳健权重矩阵 Ŝ",
        "en": "the robust weight matrix Ŝ that the efficient GMM step "
              "weights with",
    })
    INSTRUMENT_GRAM = ("instrument_gram", {
        "zh": "工具变量的 Gram 矩阵 Z'Z",
        "en": "the instruments' Gram matrix Z'Z",
    })
    SATURATED_JOINT = ("saturated_joint_design", {
        "zh": "2^K 个角点的饱和联合设计矩阵",
        "en": "the saturated joint design matrix over the 2^K corners",
    })
    OUTCOME_AND_MEDIATOR_FIT = ("outcome_and_mediator_fit", {
        "zh": "结局模型与中介模型共用的设计矩阵",
        "en": "the design matrix the outcome and mediator models share",
    })
    DESIGN_COVARIANCE = ("design_covariance", {
        "zh": "设计矩阵的协方差 Σ",
        "en": "the design covariance Σ",
    })
    NON_EXPOSURE_COVARIANCE = ("non_exposure_design_covariance", {
        "zh": "设计矩阵里非暴露那几列的协方差",
        "en": "the covariance of the design's non-exposure columns",
    })
    BRIDGE_INSTRUMENT_MOMENTS = ("bridge_instrument_moments", {
        "zh": "bridge 方程那一侧、处理侧代理的基函数二阶矩矩阵 A'A",
        "en": "the second-moment matrix A'A of the treatment proxy's basis, "
              "the side of the bridge equation the moments are taken at",
    })
    BRIDGE_OUTCOME_MOMENTS = ("bridge_outcome_moments", {
        "zh": "bridge 方程另一侧、结局侧代理的基函数二阶矩矩阵 B'B",
        "en": "the second-moment matrix B'B of the outcome proxy's basis, "
              "the side of the bridge equation the unknown lives on",
    })


@unique
class BridgeSide(language.Word, vocabulary="bridge_side"):
    """Which of a bridge's two declared designs a sentence is about.

    Not :class:`Design` next door, though both name a matrix. That one says
    which matrix would not invert — a fact about this sample — and its
    members are second-moment matrices. These two name what the CALLER
    declared, and the distinction they carry is the one the two-design
    arrangement rests on: the span is the function class the bridge is
    searched for in, the moments are the directions the equation is asked
    to hold along. A reader told "the design does not mention the
    treatment" cannot act on it without knowing which of the two, because
    the fix is written in a different field of the query.
    """

    SPAN = ("bridge_span", {
        "zh": "桥所在的那组基函数（span）",
        "en": "the basis the bridge is searched for in (its span)",
    })
    MOMENTS = ("bridge_moments", {
        "zh": "桥方程被要求成立的那组矩方向（moments）",
        "en": "the moment directions the bridge equation is asked to hold "
              "along",
    })


@unique
class Recovery(language.Word, vocabulary="recovery_mechanism"):
    """Which mechanism an estimand was asked to be recovered from.

    ``not_recoverable`` was defined as "not recoverable under the declared
    selection OR missingness mechanism", and an ``or`` in a definition is a
    name covering two facts. Here the two facts differ in exactly one word
    and in the criterion that judges it, so the cheaper repair is the one
    #405's ninth cut already used on the instrument's missing arm: lift the
    word into a slot rather than split the species.

    A member names the mechanism and the criterion together, because a
    reader who is told an estimand is unrecoverable and not told what
    decided it has no way to check the decision — and the pairing is fixed:
    which criterion applies follows from which mechanism was declared, with
    nothing for a site to choose between.
    """

    FROM_MISSINGNESS = ("from_missingness", {
        "zh": "所声明的缺失机制（判据是 Mohan-Pearl-Tian 的有序因子分解）",
        "en": "the declared missingness mechanism (judged by "
              "Mohan-Pearl-Tian's ordered factorisation)",
    })
    FROM_SELECTION = ("from_selection", {
        "zh": "所声明的选择机制（判据是 Bareinboim-Pearl 的选择后门）",
        "en": "the declared selection mechanism (judged by "
              "Bareinboim-Pearl's selection back-door criterion)",
    })


@unique
class Refutation(language.Word, vocabulary="monotonicity_refutation"):
    """What refuted a declared monotonicity.

    The finding is the same either way and so is what the reader should do
    about it, which is why this is a word and not a second species: two
    routes reach "your monotonicity is refuted" and they differ in the
    evidence, not in the conclusion or its strength. A reader who is not
    told which evidence did it cannot check the decision, and the route
    that ran is not something the reader chose.
    """

    RESPONSE_TYPE_POLYTOPE = ("response_type_polytope", {
        "zh": "把结局与处理反向的那些单位剔除之后，没有任何响应型分布能重现 "
              "P(X, Y | Z)——工具变量与这张表本身是相容的",
        "en": "no distribution over response types reproduces P(X, Y | Z) "
              "once the units whose outcome moves against the treatment are "
              "removed — the instrument and the table are compatible on "
              "their own",
    })
    CELL_FEASIBLE_SET = ("cell_feasible_set", {
        "zh": "观测联合分布与给定的 P(Y=1|do(X)) 一起，把这一格的可行集压成了"
              "空集——没有单调性时这个交集必非空",
        "en": "the observational joint and the supplied P(Y=1|do(X)) leave "
              "this cell's feasible set empty — without the monotonicity "
              "that intersection is provably non-empty",
    })


@unique
class QueryRole(language.Word, vocabulary="query_role"):
    """Which variable of the query a sentence is about.

    Two surfaces were keeping these words and neither could reach the other.
    The measurement corrections have two channels — an exposure matrix and
    an outcome matrix — and named the channel by gluing an English word into
    English prose, with the absence of a word standing for "the outcome": an
    unlabelled EXPOSURE matrix was therefore rejected in the outcome's name,
    which is what a default that means something always eventually does. The
    gap report kept the same words privately, one module away, and rendered
    them straight to a string, so they existed only for the length of one
    expression.

    One vocabulary because it is one question. Which members a given
    consumer can meet is that consumer's business — no confusion matrix
    belongs to a covariate — and a vocabulary narrowed to its narrowest
    consumer is the one that gets copied.

    Bare nouns. A member lands both as a sentence's own subject and inside a
    longer noun phrase built around it, and an article baked into the member
    can only be right in one of those two places.

    Named for the question and not for the word, because ``Role`` is taken:
    :class:`themis.estimation.strategy.Role` says what part a dispatch
    strategy plays, which is a different question with the same English name.
    Two vocabularies sharing one is not only ambiguous to read — the identity
    gate that watches envelope vocabularies resolves them by bare name, and
    would have started reporting the other one's comparisons as this one's.
    """

    EXPOSURE = ("exposure", {"zh": "暴露", "en": "exposure"})
    OUTCOME = ("outcome", {"zh": "结局", "en": "outcome"})
    ON_PATH_COVARIATE = ("on_path_covariate", {
        "zh": "路径上协变量", "en": "on-path covariate",
    })
    #: Joined when a second family of sentences needed to say which column
    #: was the one that never varied. Nine sites said "treatment" or
    #: "instrument" in English prose around a column name; the vocabulary
    #: they were spelling out by hand was this one, short by a member.
    INSTRUMENT = ("instrument", {"zh": "工具变量", "en": "instrument"})


BY_NAME: dict[str, Refusal] = {str(species): species for species in Refusal}
"""The species going by that envelope name, or nothing.

``Refusal(name)`` is the same lookup and is the one to use where an
unknown name is an error. This is for the places where it is a question:
what we read is deliberately wider than what we emit, so "is this a
species we know" has to be answerable with no.
"""

KIND_BY_NAME: dict[str, Kind] = {str(kind): kind for kind in Kind}
"""The kind going by that envelope name, or nothing.

:data:`BY_NAME` for the other closed set on the block, and for the same
reason: the report renders the kind an envelope carried, and an envelope
from another kernel may name one this build has never heard of.
"""


def stamp(result: dict) -> None:
    """Send every refusal out bearing the ``kind`` its species declares.

    A refusal is written at some thirty sites, each of which knows the
    occasion — which estimator, which stratum, what the caller should
    have supplied. None of them knows anything about the *kind* that the
    species does not already say, so none of them writes it: the
    registry stamps it here, at the exit, and a consumer reading the
    envelope branches on five values instead of on sixty-nine.

    That is why the same call also refuses an unregistered species.
    Constructing :class:`EstimatorFailure` checks at the earliest moment
    the species exists, but the hand-written sites have no constructor —
    and those were exactly the ones that invented species the schema had
    never heard of. What cannot be looked up cannot be stamped.

    Reading is deliberately not symmetric, for the reason it is not
    symmetric for blocks: ``verify()`` accepts an envelope carrying a
    species this kernel does not know, because refusing there would
    reject somebody else's honest refusal. What is closed is what we
    emit.
    """
    failure = result.get("estimator_failure")
    if not isinstance(failure, dict):
        return
    name = failure.get("failure_type")
    if name is None:
        return
    species = BY_NAME.get(str(name))
    if species is None:
        raise ValueError(
            f"result {result.get('query_id')!r} refuses with unregistered "
            f"failure_type {str(name)!r}; every reason a number is "
            f"withheld is declared in themis.refusals, so a consumer can "
            f"branch on one list instead of on whatever the estimator spelled"
        )
    failure["kind"] = species.kind
# Two kinds of collection reach a refusal's sentence and they want
# opposite treatment. A list of names — an adjustment set, a design's
# variables, an outcome's declared states — IS the answer, and cutting
# it drops the thing the reader needs. A column of data values is only
# evidence for a count, and it has no ceiling: the measured case was
# 3000 floats. So the cutoff is read off the elements, not fixed.

#: The reader's sentence for a species, in every language this build writes.
#:
#: ``says`` above is the maintainer's — what a species means to whoever adds
#: the next one beside it. This is the reader's. They stay separate because
#: they answer different people; what they are NOT is one sentence per RAISE
#: SITE. The species is the fact and the occasion is the numbers, and the
#: numbers already have a home in ``details`` that every raise site can reach.
#:
#: Measured before it was written: ``estimator_failure.reason`` had 25
#: authoring modules and two languages — 157 sentences in English, six in
#: Chinese, and which one a reader was handed depended on which estimator had
#: declined. A Chinese report read "没有给出数值 —— 这批数据支撑不住：the
#: design this strategy needs names columns the data does not have。"
#:
#: Named slots only, filled from ``details``. An f-string interpolates where
#: it is written, which makes the sentence a value rather than a template and
#: leaves nothing for a second language to be written beside — which is why
#: 149 of 171 raise sites could not have been translated at all.
SAYS: dict[str, language.Words] = {
    "adjustment_all_missing": {
        "zh": "调整集里的 {column} 从未被观测到，它的边际 P({column}) 无法恢复",
        "en": "the adjustment column {column} is never observed, so its "
              "marginal P({column}) cannot be recovered",
    },
    "adjustment_not_discrete": {
        "zh": "调整集里的 {column} 有 {levels} 个观测层级、或取值不是整数；恢复"
              "估计要在后门集上分层，所以每个调整变量都必须离散（至多 {cap} 个"
              "整数层级）。连续混杂需要一个 P(Z) 的模型，不在范围内",
        "en": "the adjustment column {column} has {levels} observed levels or "
              "non-integer values; the recovery estimator stratifies on the "
              "back-door set, so every adjustment variable must be discrete "
              "(at most {cap} integer levels). A continuous confounder needs "
              "a model for P(Z) and is out of scope",
    },
    "atom_not_in_graph": {
        "zh": "干预或目标原子不在这个 SCM 的变量集里",
        "en": "the intervention or target atom is not in the SCM's variable set",
    },
    "cause_or_effect_not_binary": {
        "zh": "这个量要求 {column} 是二值列；实际取值是 {values}",
        "en": "this quantity requires a binary column {column}; got values "
              "{values}",
    },
    "continuous_adjustment": {
        "zh": "调整协变量 {column} 有 {levels} 个不同取值（超过 {cap}）；这个"
              "饱和分层公式在离散的层上求和，连续协变量没有层可分",
        "en": "the adjustment covariate {column} has {levels} distinct values "
              "(over {cap}); this saturated stratified formula sums over "
              "discrete strata, and a continuous covariate has none",
    },
    "continuous_outcome": {
        "zh": "结局 {outcome} 有 {states} 个取值（超过 {cap}）；混淆矩阵校正"
              "要对每个结局取值命名，需要一个离散结局",
        "en": "the outcome {outcome} has {states} values (over {cap}); a "
              "confusion-matrix correction names every outcome value and so "
              "needs a discrete outcome",
    },
    # Names the levels that came out non-positive rather than a treated /
    # control pair: the correction takes an exposure of any width now, and a
    # sentence that can only name two arms could not say which of five failed.
    "degenerate_recovered_exposure": {
        "zh": "分层 z={stratum} 在暴露水平 {levels} 上恢复出的真实边际非正"
              "（{recovered}）；这些水平的条件风险因此无定义——混淆矩阵在这一层里"
              "信息太弱，识别不了效应",
        "en": "the stratum z={stratum} recovers a non-positive true exposure "
              "marginal at the levels {levels} ({recovered}), so the "
              "conditional risk is undefined there — the confusion matrix is "
              "too weakly informative to identify the effect in that stratum",
    },
    "no_usable_resample": {
        "zh": "{model} 估计量的 {resamples} 次 bootstrap 重抽样只剩 {usable} 次"
              "可用，取不出可以叫区间的分位数",
        "en": "only {usable} of {resamples} bootstrap resamples survived for "
              "the {model} estimator, which is too few to take anything worth "
              "calling an interval from",
    },
    "not_a_joint_intervention": {
        "zh": "联合干预至少需要两个处理，这次给的是 {count} 个"
              "（{treatments}）；单处理的效应走的是另一条路。",
        "en": "a joint intervention needs at least two treatments and this "
              "call named {count} ({treatments}); the single-treatment effect "
              "is answered by another route.",
    },
    "not_identifiable_by_general_id": {
        "zh": "在这张 ADMG 上，{treatment} 对 {outcome} 的效应无法被 ID 算法"
              "点识别——没有可求值的 c-factor 估计量",
        "en": "the effect of {treatment} on {outcome} is not point-identified "
              "by the ID algorithm on this ADMG — there is no c-factor "
              "estimand to evaluate",
    },
    "response_model_too_large": {
        "zh": "处理／结局／工具在这份数据上有 {nx}×{ny}×{nz} 个观测层级，响应"
              "函数划分因此有 {nx}^{nz}·{ny}^{nx} 个响应型，超过本包求解的 "
              "{cap} 个。锐界是存在的，被拒绝的是那个线性规划——它要在每个 "
              "bootstrap 重抽样上重解一次。层级这么多的列通常是连续的，而响应"
              "函数模型描述不了连续变量；把它粗化，方法就回到可及范围里",
        "en": "treatment, outcome and instrument have {nx}×{ny}×{nz} observed "
              "levels here, so the response-function partition has "
              "{nx}^{nz}·{ny}^{nx} types — above the {cap} this package "
              "solves. The sharp interval exists; what is declined is the LP, "
              "re-solved once per bootstrap replicate. A column with this many "
              "levels is usually a continuous one that no response-function "
              "model describes, and coarsening it brings the method back in "
              "reach",
    },
    "counterfactual_cell_cross_variable": {
        "zh": "反事实单格估计干预的变量与它条件其上的变量是同一个：得到 "
              "do({intervened})，而观测的是 {observed}",
        "en": "the counterfactual cell estimator intervenes on the SAME "
              "variable it conditions on; got do({intervened}) with "
              "{observed} observed",
    },
    "counterfactual_cell_not_binary": {
        "zh": "反事实单格估计只处理布尔量；{label} 上得到的是 {given}",
        "en": "the counterfactual cell estimator is boolean-only; {label} "
              "is {given}",
    },
    "counterfactual_inputs_infeasible": {
        "zh": "声明的单调性被数据推翻了：{refuted_by}。要改的是这条假设，不是"
              "数据",
        "en": "the declared monotonicity is refuted by the data: "
              "{refuted_by}. What has to change is the assumption, not the "
              "data",
    },
    "differential_level_uncovered": {
        "zh": "{axis}={level} 这一层没有提供混淆矩阵；差异性矩阵集必须覆盖"
              "差异轴上每一个观测到的层",
        "en": "no confusion matrix was supplied for {axis}={level}; the "
              "differential matrix set must cover every observed level of the "
              "differential axis",
    },
    "empty_outcome": {
        "zh": "结局列 {outcome} 没有任何观测值",
        "en": "the outcome column {outcome} has no observed values",
    },
    "intervention_is_target": {
        "zh": "干预和目标必须是两个不同的变量",
        "en": "the intervention and the target must be distinct variables",
    },
    "intractable_estimand": {
        "zh": "识别出来的估计量树宽过大，变量消元算不动（{limit}）；在这张 "
              "ADMG 上它超出了数值 plug-in 的能力",
        "en": "the identified estimand has too high a treewidth to evaluate "
              "by variable elimination ({limit}); it is beyond the numeric "
              "plug-in's reach on this ADMG",
    },
    "invalid_monotonicity": {
        "zh": "单调性只能是 'non_decreasing' 或 'non_increasing'；得到的是 "
              "{declared}",
        "en": "monotonicity must be 'non_decreasing' or 'non_increasing'; got "
              "{declared}",
    },
    "linear_program_failed": {
        "zh": "界的两个线性规划没有一致地给出不可行证书（求解器状态 "
              "{statuses}：{diagnostic}）；只有当两支都证明约束无解时，"
              "数据才算否证了这个模型，所以这一次没有对模型下任何结论。",
        "en": "the two bounds programs did not both certify infeasibility "
              "(solver statuses {statuses}: {diagnostic}); the data refutes "
              "the model only when both prove the constraints admit nothing, "
              "so nothing has been concluded about the model here.",
    },
    "mismeasured_variable_not_in_design": {
        "zh": "为 {variable} 提供了测量误差，但它不在设计变量 {design} 里"
              "（设计变量 = 暴露及其后门调整集）。一个混杂只有被调整了才谈得上"
              "被校正",
        "en": "measurement error was supplied for {variable}, which is not "
              "among the design variables {design} (the exposure and its "
              "back-door adjustment set). A confounder has to be adjusted for "
              "to be corrected",
    },
    "missing_column": {
        "zh": "数据里没有 {columns} 这些列，而查询点了它们的名字",
        "en": "the data has no column(s) {columns}, which the query names",
    },
    "no_within_stratum_contrast": {
        "zh": "{column} 只取到一个值的层：{strata}——层里有行，而两个臂之间的"
              "对比不在里面；这个估计量要在每一层内比较这两个臂，缺的那一臂"
              "只能由模型外推补上",
        "en": "strata in which {column} takes a single value: {strata} — the "
              "rows are there and the contrast between the arms is not among "
              "them; this estimator compares the two arms within each "
              "stratum, and the missing arm can only be supplied by a "
              "model's extrapolation",
    },
    "model_fit_failed": {
        "zh": "结局或中介模型在全样本上拟合失败：{detail}",
        "en": "the outcome or mediator model failed to fit on the full "
              "sample: {detail}",
    },
    "no_identifying_design": {
        "zh": "{exposure} 对 {outcome} 的效应在这张图上没有任何一条本包认识的"
              "识别路径：没有 back-door 调整集，没有 front-door 集，"
              "也没有工具变量。",
        "en": "the effect of {exposure} on {outcome} has no identifying "
              "design this package names on this graph: no back-door "
              "adjustment set, no front-door set, and no instrument.",
    },
    "not_identifiable_by_idc": {
        "zh": "在这张 ADMG 上，给定 {given} 时 {treatment} 对 {outcome} 的"
              "条件效应无法被 IDC 点识别——没有可求值的 c-factor 估计量",
        "en": "the conditional effect of {treatment} on {outcome} given "
              "{given} is not point-identified by IDC on this ADMG — there is "
              "no c-factor estimand to evaluate",
    },
    "not_identifiable_counterfactual": {
        "zh": "在这张 ADMG 上，P(γ|δ) 无法被 ID*/IDC* 算法识别——没有可求值的"
              "观测量",
        "en": "P(γ|δ) is not identifiable by the ID*/IDC* algorithm on this "
              "ADMG — there is no observational estimand to evaluate",
    },
    # The identification layer's own statement, relayed. Its token names the
    # criterion, so a ``{criterion}`` hole beside it was the machine tag
    # printed in front of the sentence that explains it — and the sentence
    # itself arrived rendered, in the one language its producer wrote.
    "not_identifiable_proximal": {
        "zh": "近端识别拒答：{detail}",
        "en": "proximal identification refused: {detail}",
    },
    "outcome_does_not_vary": {
        "zh": "结局列 {outcome} 在这份数据里几乎不变（标准差 {std}，极差 "
              "{spread}）；对它的任何拟合都会给出一条零效应曲线和零宽区间，"
              "而那是这份数据的形状，不是估计出来的答案。",
        "en": "the outcome column {outcome} barely varies in this data "
              "(std {std}, range {spread}); any fit of it returns a flat "
              "zero-effect curve with zero-width intervals, and that is the "
              "shape of this data rather than an estimated answer.",
    },
    "outcome_error_exceeds_residual_variance": {
        "zh": "声明的结局误差方差 σ²_v = {declared} 达到或超过了观测到的"
              "残差方差 Var({outcome}|D) = {residual}。这份噪声塞不进数据"
              "未能解释的那部分变异里，所以「声明的方差」「结局模型是线性的」"
              "「误差与设计独立」三条里至少有一条是假的——而最后那条正是点估计"
              "不受这个误差影响的原因。因此不出具评估",
        "en": "the declared outcome error variance σ²_v = {declared} "
              "meets or exceeds the observed residual variance "
              "Var({outcome}|D) = {residual}. The noise does not fit "
              "underneath the variation the data leave unexplained, so at "
              "least one of the declared variance, the linearity of the "
              "outcome model, and the independence of the error from the "
              "design is false — and that last one is what makes the point "
              "estimate immune to the error. No assessment is issued",
    },
    "outcome_not_binary": {
        "zh": "{outcome} 在数据里的取值是 {levels}；这个估计量只做二值结局",
        "en": "the observed values of {outcome} are {levels}; this estimator "
              "takes a binary outcome only",
    },
    "outcome_not_continuous": {
        "zh": "结局 {outcome} 只有 {distinct} 个不同取值；可加误差方差描述的是"
              "「连续」测量。离散结局属于误分类，它的误差确实会衰减效应，只是"
              "一个可加方差校正不了这种衰减",
        "en": "the outcome {outcome} has only {distinct} distinct values; an "
              "additive error variance describes a CONTINUOUS measurement. A "
              "discrete outcome is a misclassification object, and its error "
              "does attenuate the effect — but an additive variance is not "
              "what corrects that attenuation",
    },
    "proxy_cardinality_mismatch": {
        "zh": "近端公式 (5) 要求每个代理都恰好呈现 k={k} 个层级；实际 "
              "|Z|={z}、|W|={w}。要用更细的代理，就在 query 的 "
              "proxy_coarsening 里说明每个代理的哪些层级并作 k 组中的一组"
              "——哪些层级代表 U 的同一个状态，数据本身答不了",
        "en": "proximal formula (5) needs each proxy to present exactly k={k} "
              "levels; observed |Z|={z}, |W|={w}. To use a finer proxy, say "
              "on the query's proxy_coarsening which of its levels make up "
              "each of the k groups — which levels stand for the same state "
              "of U is not something the data answers",
    },
    "coarsening_does_not_partition_the_proxy": {
        "zh": "`{proxy}` 上声明的粗化与这一列实际持有的层级对不上：声明覆盖 "
              "{declared}，列里是 {observed}。每个观测到的层级要落在且只落在"
              "一个组里，每个组要指到确实存在的层级——否则折出来的通道就不是"
              "这一列的重新编码",
        "en": "the coarsening declared for `{proxy}` does not line up with "
              "the levels that column holds: the declaration covers "
              "{declared}, the column has {observed}. Every observed level "
              "has to fall in exactly one group and every group has to name "
              "levels that are there, or the folded channel is not a "
              "recoding of this column",
    },
    "coarsening_group_count_is_not_k": {
        "zh": "`{proxy}` 上声明的粗化分成了 {groups} 组，而 query 里 U 的类别"
              "数是 k={k}。这些组就是 U 的那 k 个状态，所以组数不是自由的："
              "要么改分组，要么改 latent_cardinality",
        "en": "the coarsening declared for `{proxy}` makes {groups} groups "
              "while the query posits k={k} states for U. The groups ARE "
              "those k states, so their count is not free: either regroup "
              "or change latent_cardinality",
    },
    "bridge_ill_posed_at_this_penalty": {
        "zh": "在 λ={ridge} 这个正则化强度下，bridge 方程仍然病态"
              "（条件数 {condition}）：{dimension} 维的基函数在这份数据上分辨"
              "不开，解出来的是正则化项在众多解里挑的那一个，不是数据挑的。"
              "把 dimension 调小、或者把 ridge 调大，都能让它重新可解——"
              "这两个都是你声明的",
        "en": "at λ={ridge} the bridge equation is still ill-conditioned "
              "(condition number {condition}): the data do not tell {dimension} "
              "basis functions apart, so the solution is the one the penalty "
              "picked out of many rather than the one the data did. A smaller "
              "dimension or a larger ridge makes it solvable again, and both "
              "of those are yours to declare",
    },
    "rank_condition_violated": {
        "zh": "P(W|Z,x) 奇异或病态：两个代理对未观测混杂的联合相关性不足以把"
              "测量通道求逆。在这份数据上这个效应不是近端可恢复的",
        "en": "P(W|Z,x) is singular or ill-conditioned: the proxies are not "
              "jointly relevant enough to the unobserved confounder to invert "
              "the measurement channel. The effect is not proximal-recoverable "
              "on this data",
    },
    "rank_deficient_design": {
        "zh": "节点 {node} 对父节点 {parents} 的 OLS 设计矩阵秩亏（存在共线"
              "回归元或常数列）；结构系数不唯一",
        "en": "the OLS design for node {node} on parents {parents} is "
              "rank-deficient (a collinear regressor or a constant column); "
              "the structural coefficients are not uniquely determined",
    },
    "reference_missing_column": {
        "zh": "外部无偏参照样本缺少 {columns} 这些列，而调整权重 "
              "P(z⁺)/P(z⁻|x,z⁺) 需要它们",
        "en": "the unbiased reference sample is missing the column(s) "
              "{columns} needed for the adjustment weights P(z⁺)/P(z⁻|x,z⁺)",
    },
    # Four sites wrote this, three of them word for word, and all four spelled
    # the effect ``P(y|do(x))`` — literal letters, where the reader has column
    # names. The fourth said "slope" rather than "number" because regression
    # calibration corrects a coefficient; the species says "result", which is
    # true of both, and which estimator was speaking is already on the block.
    "requires_backdoor_identification": {
        "zh": "{exposure} 对 {outcome} 的效应在这里是可识别的，但不是通过 "
              "back-door 调整；而这项校正只接在 back-door 调整之上，"
              "所以没有给出校正后的结果。",
        "en": "the effect of {exposure} on {outcome} is identified here, but "
              "not through back-door adjustment, and this correction composes "
              "with back-door adjustment only, so no corrected result is "
              "produced.",
    },
    "sample_too_small": {
        "zh": "样本量 {n} 低于估计所需的下限（{minimum}）",
        "en": "the sample size {n} is below the minimum ({minimum}) for "
              "estimation",
    },
    # Was the outcome channel's alone and said 结局 in so many words. Two
    # sites on the exposure channel said the same thing under a species that
    # meant "this correction is binary-exposure only" — a fact that stopped
    # being true when the correction was widened to k levels, and whose species
    # is gone. Naming the column serves the reader better than either did: it
    # is the name they used.
    "states_incomplete": {
        "zh": "{column} 观测到的取值 {values} 不在声明的混淆矩阵状态 {states} "
              "里；矩阵必须覆盖每一个观测到的取值",
        "en": "the observed values {values} of {column} are not among the "
              "declared confusion-matrix states {states}; the matrix must "
              "cover every observed value",
    },
    "too_many_joint_treatments": {
        "zh": "联合效应最多支持 {cap} 个处理（饱和基是 2^K − 1 列，交互项是 "
              "2^K 个角点的有限差分）；实际是 {count} 个（{treatments}）",
        "en": "the joint effect caps at {cap} treatments (the saturated basis "
              "is 2^K − 1 columns and the interaction is a 2^K-corner finite "
              "difference); got {count} ({treatments})",
    },
    "treatment_levels_differ": {
        "zh": "联合干预的角点是所有处理同时取同一对取值，而 {treatments} "
              "的取值集是 {level_sets}——不是同一对，这个角点没有定义",
        "en": "a joint intervention's corner puts every treatment at one "
              "shared pair of values, and the level sets of {treatments} are "
              "{level_sets} — not one pair, so the corner is undefined",
    },
    "treatment_not_binary": {
        "zh": "{treatment} 在数据里的取值是 {levels}；这个估计量做的是两个"
              "取值之间的对比，只接受二值处理",
        "en": "the observed values of {treatment} are {levels}; this "
              "estimator contrasts two levels and takes a binary treatment "
              "only",
    },
    "no_degrees_of_freedom_to_test_the_null": {
        "zh": "检验「X 对 Y 完全没效应」靠的是一个**过度识别**的限制：{moments} "
              "个矩条件被声称落在一个 {unknowns} 维的空间里，多出来的那几维就"
              "是检验的自由度。这里 {moments} = {treatment_levels}（{treatment} "
              "的取值数）×{proxy_levels}（处理侧代理的取值数），不比 "
              "{unknowns} 多，什么都没剩下。要么处理侧代理更细，要么处理本身"
              "取值更多——两个都是可以去拿的东西，不是方法的边界",
        "en": "testing whether `{treatment}` affects the outcome at all rests "
              "on an OVER-identifying restriction: {moments} moments are "
              "claimed to lie in a {unknowns}-dimensional space, and what is "
              "left over is the test's degrees of freedom. Here {moments} = "
              "{treatment_levels} levels of `{treatment}` × {proxy_levels} "
              "levels of the treatment-side proxy, which is no more than "
              "{unknowns}, so nothing is left over. Either proxy needs more "
              "categories, or the treatment does — both are things to go and "
              "get rather than a limit of the method",
    },
    "stacked_channel_is_rank_deficient": {
        "zh": "把各个处理水平上的 P(W|Z,x) 摞起来得到的那个矩阵秩是 {rank}，"
              "不足 {needed}。零假设说的是「{needed} 个系数就能解释全部矩条件」"
              "，而这个矩阵没有那么多独立方向，所以那句话没有可被证伪的内容。"
              "这和点估计那条秩条件不是同一条：那一条问单个 x 上的信道能不能"
              "求逆，这一条问摞起来之后还剩几个方向",
        "en": "stacking P(W|Z,x) over the treatment levels gives a matrix of "
              "rank {rank}, short of {needed}. The null says {needed} "
              "coefficients account for every moment, and this matrix has too "
              "few independent directions for that claim to have refutable "
              "content. Not the point estimate's rank condition: that one asks "
              "whether the channel at a single x inverts, this one asks how "
              "many directions survive the stack",
    },
    "treatment_bridge_is_already_per_level": {
        "zh": "处理桥 q 是按 I(A=a) 一个水平一个水平解出来的，每个水平自己一"
              "套系数——也就是说它在 {treatment} 上**已经是饱和的**。而 "
              "{design} 里有一项用到了 {treatment}：在某一个水平的那些行里 "
              "{treatment} 是常数，所以那些列在臂内彼此共线，只会把方程弄病"
              "态，换不来任何形状。把 {treatment} 从处理桥的两侧都拿掉——这和"
              "结局桥恰好相反，那一侧非写不可",
        "en": "the treatment bridge q is solved one level at a time through "
              "I(A=a), each level carrying its own coefficients — which is "
              "to say it is ALREADY saturated in {treatment}. A term of "
              "{design} names {treatment} anyway, and inside one level's "
              "rows {treatment} is constant, so those columns are collinear "
              "within every arm: they buy no shape and only make the system "
              "ill-conditioned. Take {treatment} out of both sides of the "
              "treatment bridge — the opposite of the outcome bridge, where "
              "it has to be written in",
    },
    "treatment_bridge_needs_rows_at_each_level": {
        "zh": "这条查询要的是**双稳健**（或逆概率加权）的曲线，而处理桥 q 是靠"
              "一个示性 I(A=a) 一个水平一个水平地定下来的（Cui et al. 2024 "
              "式 (8)）——{treatment} 是连续的，曲线要问的 {levels} 个水平上"
              "**一行都没有**，没有可加权的臂。结局桥那条路不受此限：它是把一"
              "座拟合好的桥在某点求值，在没有观测的水平上照样有定义。所以这里"
              "能给的是 `outcome_regression` 的曲线，双稳健要等一个 Themis 还"
              "没有的条件密度估计",
        "en": "this query asks for a **doubly robust** (or inverse-"
              "probability) curve, and the treatment bridge q is pinned down "
              "one level at a time through an indicator I(A=a) (Cui et al. "
              "2024 eq. (8)) — {treatment} is continuous and NO ROW sits at "
              "any of the {levels} levels the curve is drawn at, so there is "
              "no arm to weight. The outcome-regression route is not limited "
              "this way: evaluating a fitted bridge at a point stays defined "
              "where nothing was observed. So the curve available here is "
              "the `outcome_regression` one, and double robustness waits on "
              "a conditional density Themis does not estimate",
    },
    "bridge_cannot_vary_with_the_treatment": {
        "zh": "{treatment} 有 {levels} 个水平，所以问的是一条曲线：每个水平上"
              "一个 h(W, a, C)。而 {design} 里没有一项提到 {treatment}，这样"
              "解出来的桥在每个水平上是同一个函数，曲线只能是平的。把 "
              "{treatment} 作为一个 factor 写进那一侧的项里——和协变量一样，"
              "乘进去而不是加进去，曲线才在水平之间真的变",
        "en": "{treatment} has {levels} levels, so the question is a curve — "
              "one h(W, a, C) at each level. No term of {design} mentions "
              "{treatment}, so the bridge solved from it is the same function "
              "at every level and the curve could only come out flat. Write "
              "{treatment} into that side as a factor of its terms — "
              "multiplied in as a covariate is, not added — and the curve "
              "varies across levels",
    },
    # ``{event}`` because the second site reaches this over one binary cell
    # rather than a counterfactual conjunction: what has no mass is a fact
    # about the occasion, and a sentence that could only name δ would have
    # left that site writing its own.
    "undefined_conditioning_event": {
        "zh": "被条件的事件 {event} 概率为 0，所以这个条件概率无定义；给不出数",
        "en": "the conditioning event {event} has probability 0, so the "
              "conditional is undefined; no number can be produced",
    },
    "unit_underobserved": {
        "zh": "这个单位缺少 {variable} 的事实取值；abduction 无法恢复它的外生项",
        "en": "the unit is missing a factual value for {variable}; abduction "
              "cannot recover its exogenous term",
    },
    # --- the ways an argument fails its contract --------------------------
    # Thirty-four sites filed two catch-all species between them and wrote
    # thirty-four sentences, because a name that says "your input is
    # invalid" leaves the whole message to the site. The faults are not
    # thirty-four: they are the handful below, and each of them is met by
    # sites that have nothing else in common — an unknown option is filed
    # by five estimators, and four of the confusion matrix's own nine were
    # a count and a repetition, which every other argument can also be.
    "unknown_option": {
        "zh": "{option} 只认这几个取值：{known}；收到的是 {given}",
        "en": "{option} takes one of {known}; it was given {given}",
    },
    "too_few_inputs": {
        "zh": "{what} 至少要 {needed} 个，只收到 {given} 个",
        "en": "{what} needs at least {needed}, and {given} were given",
    },
    "duplicate_input": {
        "zh": "{what} 里同一样东西出现了两次（{given}）；它的每一项要指向不同"
              "的东西",
        "en": "{what} names the same thing twice ({given}); its entries have "
              "to be distinct",
    },
    "inputs_disagree": {
        "zh": "{one} 是 {one_is}，{other} 是 {other_is}；这两者必须一一对上",
        "en": "{one} is {one_is} and {other} is {other_is}; the two have to "
              "line up one for one",
    },
    "malformed_argument": {
        "zh": "{argument} 读的是 {shape} 这个结构，收到的是 {given}",
        "en": "{argument} is read as {shape}, and it was given {given}",
    },
    "argument_not_given": {
        "zh": "{argument} 没有给。这不是「给的值不对」——它根本没有出现，"
              "所以下面的每一条判据都没有可判的东西",
        "en": "{argument} was not given. This is not a value that failed a "
              "test — nothing arrived, so there was nothing for any of the "
              "tests below it to judge",
    },
    "argument_not_a_number": {
        "zh": "{argument} 必须是一个有限的数，收到的是 {given}",
        "en": "{argument} has to be a finite number, and it was given "
              "{given}",
    },
    "probabilities_do_not_sum": {
        "zh": "{what} 里的概率加起来是 {given}，不是 1",
        "en": "the probabilities in {what} sum to {given} rather than to 1",
    },
    "argument_missing_for_design": {
        "zh": "{design} 这个设计要有 {argument}：{premise}",
        "en": "the {design} design needs {argument}: {premise}",
    },
    "argument_foreign_to_design": {
        "zh": "{design} 这个设计没有 {argument} 的位置——它属于 {owners}："
              "{premise}",
        "en": "the {design} design has no place for {argument}; it belongs "
              "to {owners}: {premise}",
    },
    "model_needs_binary": {
        "zh": "{model} 只对二值列有定义，而 {columns} 不是二值的",
        "en": "{model} is defined for binary columns, and {columns} are not",
    },
    "option_answers_another_question": {
        "zh": "{option} 算的是另一个估计量——它把 {ignored} 边际掉了，而这个"
              "查询要在它之下作比较",
        "en": "{option} computes a different estimand: it marginalises over "
              "{ignored}, and this query compares within it",
    },
    "matrix_wrong_shape": {
        "zh": "{what} 要是 {expected} 才配得上它连接的那些状态，收到的是 "
              "{given}",
        "en": "{what} has to be {expected} to match the states it maps "
              "between; it is {given}",
    },
    "matrix_not_numeric": {
        "zh": "{what} 不是一个数值数组",
        "en": "{what} is not a numeric array",
    },
    "matrix_not_finite": {
        "zh": "{what} 里有不是有限数的元素",
        "en": "{what} holds entries that are not finite numbers",
    },
    "matrix_not_probabilities": {
        "zh": "{what} 的元素要落在 [0, 1] 里才是概率",
        "en": "{what} holds entries outside [0, 1], so they are not "
              "probabilities",
    },
    "matrix_not_column_stochastic": {
        "zh": "{what} 的每一列是一个真实状态在观测状态上的分布，各自应当加起来"
              "等于 1；实际的列和是 {sums}",
        "en": "each column of {what} is one true state's distribution over "
              "the observed states and has to sum to 1; the column sums are "
              "{sums}",
    },
    # --- the ways the data does not reach ---------------------------------
    # Twenty-nine sites, and unlike the request family above they were NOT
    # each re-describing a fault that had no name: `insufficient_support`
    # and `overlap_insufficient` say the right fact, in the right words,
    # and had no sentence here at all. What the species cannot know is
    # WHICH cell, WHICH column, and which term of the formula was the one
    # left with nothing — so every site wrote the fact again in order to
    # get the occasion in. The species keep their meaning and gain the
    # slots; only the three facts that were riding under a name meant for
    # another one become species of their own.
    #
    # `{quantity}` is the term written in column names with no values, and
    # `{cells}` is the values — together they say what the formula wanted
    # and where. Splitting them is what keeps the term from being written
    # out twice for a reader who then has to notice they are the same.
    #
    # One judgement left standing rather than folded: a bounds polytope
    # over an outcome at a single level says it here, with `{role}` set to
    # the outcome, and not under `outcome_does_not_vary`. That species'
    # sentence is about a FIT returning a flat curve with zero-width
    # intervals, which a polytope does not do; the fact they share is the
    # column, and the consequence is not the same one.
    "insufficient_support": {
        "zh": "识别公式要在 {cells} 这一格上取 {quantity}，而数据里这一格没有"
              "行；那一项没有可估的东西，模型在那里给出的数只会是外推",
        "en": "the identifying formula needs {quantity} in the cell {cells}, "
              "and the data has no rows there; the term has nothing to be "
              "estimated from, and a model's number in it would be "
              "extrapolation",
    },
    "overlap_insufficient": {
        "zh": "{column} 这一列（{role}）在整份样本里只取到 {levels}；对比要从"
              "它的取值差异里来，而这份数据里没有差异",
        "en": "the column {column} (the {role}) takes only {levels} in this "
              "whole sample; the contrast has to come from its variation, "
              "and this data has none",
    },
    "too_sparse_to_estimate": {
        "zh": "{where} 上的行数是 {given}，低于这个估计量在那里报一个数所要求的 "
              "{needed}；行是有的，只是不够",
        "en": "the number of rows at {where} is {given}, below the {needed} "
              "this estimator requires before it will report a number there; "
              "the rows are present and there are not enough of them",
    },
    "no_complete_case_rows": {
        "zh": "{cells} 这一格里没有一行是完整的——行是有的，而每一行都在恢复"
              "公式要读的列上缺值",
        "en": "no row in the cell {cells} is complete — the rows are there "
              "and every one of them is missing a value in a column the "
              "recovery formula reads",
    },
    "rows_outside_the_strata": {
        "zh": "按 {columns} 切出来的层只放下了 {rows} 行里的 {covered} 行；"
              "其余的行带着这个切法安置不了的取值，把权重在这些层上归一，"
              "描述的就是另一个人群",
        "en": "the strata cut by {columns} hold {covered} of {rows} rows; the "
              "rest carry values the cut cannot place, and weights "
              "normalised over these strata describe a different population",
    },
    # --- what the measurement corrections were told ------------------------
    # Twenty-four sites in four modules, and what they have in common is
    # not a fault: it is that the measurement-error family is the one
    # whose arguments a caller has to DECLARE rather than read off the
    # data — which states the exposure has, which matrix goes with which
    # level, how large the error variance is. A declaration can be wrong
    # in more ways than a column can, and each of those ways was told at
    # its own site because the names above them were sorted by which
    # ARGUMENT went wrong and not by what went wrong with it.
    #
    # So four names here are new, and every one of them came out of a
    # sentence that would have been false at some site: two matrices for
    # two levels the axis does not take, a pair of states that is binary
    # and unorderable, error variances that are individually fine and
    # jointly too large. Splitting is not the point — saying one thing is.
    "target_value_absent": {
        "zh": "查询问的是 {column}（{role}）取 {value} 的那一档，而这一列在"
              "这里只有 {observed} 这些取值；没有这一档，也就没有可以报的数",
        "en": "the query asks about {column} (the {role}) at {value}, and "
              "here that column takes only {observed}; with no such level "
              "there is no number to report",
    },
    "differential_levels_mismatch": {
        "zh": "差异性校正要给 {axis} 的每一层各配一个混淆矩阵，而这次给了 "
              "{matrices} 个矩阵、{levels} 个层级；两者必须一一对上，否则"
              "「哪个矩阵管哪一层」是按位置猜出来的",
        "en": "a differential correction gives every level of {axis} its own "
              "confusion matrix, and this call supplied {matrices} matrices "
              "for {levels} levels; the two have to line up one for one, or "
              "which matrix applies where is a guess made by position",
    },
    "differential_levels_not_the_axis_levels": {
        "zh": "差异性矩阵是按 {axis} 的层级索引的，而 {axis} 在这里取到的是 "
              "{expected}，这次给的层级是 {given}。这两组必须是同一组——"
              "多出来的层级没有数据，少掉的层级没有矩阵",
        "en": "the differential matrices are indexed by the levels of "
              "{axis}, which here takes {expected}, and the levels supplied "
              "are {given}. The two have to be the same set — a level too "
              "many has no data and a level too few has no matrix",
    },
    "differential_by_unknown": {
        "zh": "differential_by={axis} 既不是 {home}，也不在这次校正条件化的"
              "协变量 {adjustment} 里。差异轴必须是校正本来就在其上分层的"
              "变量，否则「这一行该用哪个矩阵」没有可查的答案",
        "en": "differential_by={axis} is neither {home} nor one of the "
              "covariates this correction conditions on ({adjustment}). The "
              "differential axis has to be a variable the correction already "
              "stratifies on, or there is nothing to look up which matrix a "
              "row belongs to",
    },
    "differential_by_the_mismeasured_variable": {
        "zh": "differential_by={axis} 正是这条通道在误测的那个变量（{role}）；"
              "它的混淆矩阵本来就是按真实{role}状态索引的，再按它分一次说不出"
              "新东西。这条通道可以按 {alternatives} 差异化",
        "en": "differential_by={axis} is the very variable this channel "
              "mismeasures (the {role}); its confusion matrix is already "
              "indexed by the true {role} state, so differing by it again "
              "says nothing new. This channel may differ by {alternatives}",
    },
    "differential_spec_incomplete": {
        "zh": "差异性误分类要 confusion_matrices= 和 differential_levels= "
              "成对给出（每一层一个矩阵），这次没给的是 {missing}；缺了任何"
              "一半，「哪个矩阵管哪一层」就无从说起",
        "en": "differential misclassification needs confusion_matrices= and "
              "differential_levels= together, one matrix per level, and "
              "{missing} was not given; without either half there is no "
              "saying which matrix applies where",
    },
    "arm_order_unreadable": {
        "zh": "{what} 给的是 {given} 这一对：两个状态是有了，而没有东西说出"
              "哪个是对照臂。这一对要写成 [对照, 处理]，对照取假值、处理取"
              "真值（比如 [0, 1] 或 [False, True]）——混淆矩阵的哪一列对哪"
              "一臂，就是这么读出来的",
        "en": "{what} was given the pair {given}: two states, and nothing in "
              "them says which is the control arm. The pair has to read as "
              "[control, treated] with a falsy control and a truthy treated "
              "(e.g. [0, 1] or [False, True]) — that is how the correction "
              "tells which column of the matrix belongs to which arm",
    },
    "simex_grid_is_not_a_ladder": {
        "zh": "模拟网格 {grid} 不是一把梯子：它必须从 0 开始并严格递增。"
              "0 那一档不是模拟——加零噪声就是原数据——它是外推的锚点，"
              "也是审计能拿来对住整把梯子的那一档",
        "en": "the simulation grid {grid} is not a ladder: it has to start "
              "at 0 and strictly climb. The zero rung is not a simulation — "
              "adding no noise leaves the data alone — it is the "
              "extrapolation's anchor, and the one rung an audit can hold "
              "the rest of the ladder to",
    },
    "simex_grid_is_too_short_for_the_extrapolant": {
        "zh": "{extrapolant} 外推式配 {rungs} 档梯子：至少要 {needed} 档。"
              "参数个数和点数一样多时，曲线穿过每一个点，"
              "对 λ=−1 那一处却什么也没说",
        "en": "the {extrapolant} extrapolant over {rungs} rungs needs at "
              "least {needed}: with as many parameters as points the curve "
              "passes through all of them and says nothing about λ = −1",
    },
    "simex_extrapolant_has_a_pole_at_minus_one": {
        "zh": "拟合出来的有理外推式的极点落在 λ={pole}，正好是要读校正值的那一点，"
              "所以那里没有值",
        "en": "the fitted rational extrapolant has its pole at λ={pole}, "
              "which is the very point the correction is read off, so there "
              "is no value there",
    },
    "berkson_scatter_exceeds_residual_variance": {
        "zh": "{exposure} 声明的是 Berkson 误差 σ²_u={declared}，配上这次答出来的效应，"
              "真值散布给残差贡献 β²σ²_u={scattered}；而观测设计下的残差方差只有 "
              "{residual}。散布装不进未被解释的那部分变异里，说明这三件事至少有一件不成立："
              "声明的方差、结局模型的线性、以及散布与名义值相互独立——而最后那条正是"
              "「这个点本来就是对的、不需要校正」所依赖的前提",
        "en": "the Berkson variance declared for {exposure} is "
              "σ²_u={declared}, and with the effect this query answered "
              "with, the scattered truth contributes β²σ²_u={scattered} to "
              "the residual — while the residual variance around the "
              "observed design is only {residual}. The scatter does not fit "
              "under the unexplained variation, so at least one of three "
              "things is false: the declared variance, the linearity of the "
              "outcome model, or the independence of the scatter from the "
              "nominal value — and that last one is the premise under which "
              "the point needed no correction at all",
    },
    "differential_axis_is_an_adjusted_covariate": {
        "zh": "differential_by={axis} 说的是 {mismeasured} 上的误差随 {axis} "
              "变，而 {axis} 正是这次调整集里的一列。把它从两边都偏出去之后，"
              "剩下的误差对这个估计量而言是经典的。这里不出数：要的是普通的"
              "那条校正，配上误差**偏掉 {axis} 之后**的残差方差",
        "en": "differential_by={axis} says the error on {mismeasured} varies "
              "with {axis}, and {axis} is one of the columns this design "
              "adjusts for. Partial it out of both sides and what is left is "
              "classical for this estimand. No number is produced here: what "
              "this needs is the ordinary correction, with the error's "
              "variance AFTER {axis} is partialled out",
    },
    "differential_axis_is_not_the_exposure": {
        "zh": "differential_by={axis} 既不是暴露 {exposure}，也不在调整集 "
              "{adjustment} 里。这条闭式写的是「结局的误差里含一份随暴露走的"
              "分量」，δ 是它的系数——非盲的结局评估者就是这种情形；随一个"
              "既不被调整、又不是暴露的变量走的误差，要的是那个变量与真值、"
              "与暴露的联合结构，而这份声明没有携带它",
        "en": "differential_by={axis} is neither the exposure {exposure} nor "
              "one of the adjustment covariates {adjustment}. The closed form "
              "is written for an OUTCOME error carrying a component that "
              "tracks the EXPOSURE, with δ as its coefficient — an unblinded "
              "outcome assessor is the ordinary case; an error tracking a "
              "variable that is neither adjusted for nor the exposure needs "
              "that variable's joint structure with the truth and the "
              "exposure, which this declaration does not carry",
    },
    "differential_axis_is_not_the_outcome": {
        "zh": "differential_by={axis} 既不是结局 {outcome}，也不在调整集 "
              "{adjustment} 里。这条闭式写的是「误差里含一份随结局走的分量」"
              "，δ 是它的系数；随一个既不被调整、又不是结局的变量走的误差，"
              "要的是那个变量与真值、与结局的联合结构，而这份声明没有携带它",
        "en": "differential_by={axis} is neither the outcome {outcome} nor "
              "one of the adjustment covariates {adjustment}. The closed form "
              "is written for an error carrying a component that tracks the "
              "OUTCOME, with δ as its coefficient; an error tracking a "
              "variable that is neither adjusted for nor the outcome needs "
              "that variable's joint structure with the truth and the "
              "outcome, which this declaration does not carry",
    },
    "differential_coefficient_exceeds_the_declared_variance": {
        "zh": "{mismeasured} 声明了误差总方差 σ²={declared} 和差异系数 "
              "δ={coefficient}；光是随 {tracks} 走的那一份就贡献 "
              "δ²·Var({tracks}|Z)={tracking} 的方差，于是经典的那一份只剩 "
              "{remainder}——那不是一个方差。这两条声明彼此矛盾，还没轮到数据"
              "说话：要么 δ 太大，要么 σ² 给的不是**总**方差（这个入口要的一直"
              "是误差的全量方差）",
        "en": "the total error variance declared for {mismeasured} is "
              "σ²={declared} and the differential coefficient is "
              "δ={coefficient}. The part that tracks {tracks} alone "
              "contributes δ²·Var({tracks}|Z)={tracking}, which leaves the "
              "classical part {remainder} — not a variance. The two "
              "declarations contradict each other before the data is "
              "consulted: either δ is too large, or the σ² given is not the "
              "TOTAL variance of the error, which is what this entry has "
              "always asked for",
    },
    "differential_correction_leaves_no_true_variance": {
        "zh": "{exposure} 上声明的 σ²_u={declared} 配 δ={coefficient}，一起把"
              "真实暴露的条件方差算成 {remainder}；观测到的那个只有 "
              "{observed}。斜率是在方差上取的，没有方差就没有斜率。这次是声明"
              "和这份样本对不上——差异误差从两处进来（抬高方差、抬高协方差），"
              "所以扣掉的比经典情形多",
        "en": "the σ²_u={declared} and δ={coefficient} declared for {exposure} "
              "put the true exposure's conditional variance at {remainder}, "
              "against an observed one of only {observed}. A slope is taken "
              "over a variance, and there is none. Here it is the "
              "declarations meeting this sample rather than each other: a "
              "differential error enters in two places — raising the variance "
              "and raising the covariance — so more is removed than in the "
              "classical case",
    },
    "berkson_and_differential_are_incompatible_premises": {
        "zh": "{exposure} 同时声明了 Berkson 结构和差异系数 δ={coefficient}。"
              "Berkson 说的是误差与**记录下来的名义值**独立，正是这条让 "
              "E[X*|W,Z]=W 成立、让不校正成为对的做法；而随结局走的误差做不到"
              "这一点——结局取决于真值，真值就是名义值加上这个误差。两条前提"
              "不能同时成立，所以这里不替你挑一条",
        "en": "{exposure} was declared with a Berkson structure and a "
              "differential coefficient δ={coefficient} at once. Berkson "
              "means the error is independent of the RECORDED nominal value, "
              "which is exactly what makes E[X*|W,Z]=W hold and leaving the "
              "point uncorrected the right thing to do. An error that tracks "
              "the outcome cannot be that: the outcome depends on the truth, "
              "and the truth is the nominal value plus this error. The two "
              "premises cannot both hold, and neither is chosen for you",
    },
    "berkson_answer_is_not_the_design_slope": {
        "zh": "把 {exposure} 的点估计留着不校正，靠的是 E[X*|W,Z]=W 这条恒等式，"
              "而它说的是一个特定的量：结局对「记录下来的暴露＋调整集」的普通"
              "最小二乘斜率，这里算出来是 {slope}。这次查询答出来的是 "
              "{answered}，是另一个泛函；这条恒等式对它成不成立要另外论证，"
              "所以不给出代价，免得让读者以为那个数也一并被判过了",
        "en": "leaving the point on {exposure} uncorrected rests on the "
              "identity E[X*|W,Z]=W, and that identity is about one "
              "quantity: the ordinary least-squares slope of the outcome on "
              "the recorded exposure and the adjustment set, which is "
              "{slope} here. This query was answered with {answered}, a "
              "different functional, and whether the identity holds for it "
              "needs its own argument. No price is issued, rather than one "
              "that would read as a verdict on that number too",
    },
    "berkson_price_has_no_coefficient": {
        "zh": "{exposure} 的 Berkson 误差要按 β²σ²_u 计入残差，所以它的代价是随效应"
              "缩放的；这次拿到的系数是 {given}，代价就没有尺度可言。效应为零时散布"
              "确实一分钱不花——但那是「没有效应可花」，不是「量过了，很小」",
        "en": "a Berkson error on {exposure} enters the residual as β²σ²_u, "
              "so what it costs is scaled by the effect it rides on, and "
              "the coefficient available here is {given} — which leaves the "
              "price with no scale. At a zero effect the scatter genuinely "
              "costs nothing, but that is «there was no effect for it to "
              "cost anything on», not «measured, and small»",
    },
    "simex_perturbs_one_mismeasured_column": {
        "zh": "除了暴露 {exposure}，还给 {others} 声明了误差方差。模拟外推是"
              "往一个变量上加噪声；同时扰动两个要用到这两个误差之间的协方差，"
              "而按列给的方差里没有这个量",
        "en": "error variances were declared for {others} as well as for the "
              "exposure {exposure}. Simulation-extrapolation adds noise to "
              "ONE variable; perturbing two at once needs the covariance "
              "between their errors, which per-column variances do not "
              "carry",
    },
    "non_positive_error_variance": {
        "zh": "{variable} 的经典测量误差方差必须是一个正的有限数，收到的是 "
              "{given}。校正的每一步都要减去它或除以它，非正的值让整条式子"
              "没有定义",
        "en": "the classical measurement-error variance declared for "
              "{variable} has to be a positive finite number, and it was "
              "given {given}. Every step of the correction subtracts it or "
              "divides by it, and a non-positive value leaves the formula "
              "undefined",
    },
    "non_positive_validation_df": {
        "zh": "声明的测量误差方差带了一个验证研究的自由度 {given}，而自由度"
              "必须是一个 ≥ 1 的整数。区间要按 σ̂²·df/χ²_df 重抽这个方差，"
              "{given} 说不出任何一个抽样分布。如果这个方差本来就是精确"
              "已知的（协议规定的剂量、四舍五入的宽度、厂商标称的公差），"
              "那就把这个字段留空——留空正是「精确已知」这句话",
        "en": "a declared measurement-error variance carries a validation "
              "study's degrees of freedom of {given}, and degrees of freedom "
              "have to be a whole number of at least 1. The interval redraws "
              "the variance as σ̂²·df/χ²_df, and {given} names no sampling "
              "distribution to redraw it from. If the variance is known "
              "exactly — a dose fixed by protocol, a rounding width, a "
              "tolerance quoted by the maker — leave the field out; leaving "
              "it out is how that is said",
    },
    "tracking_study_not_usable": {
        "zh": "δ 可以只给一个数（那是「精确已知」），也可以连同量它的那次验证"
              "回归一起给——那就要 {fields} 四个都在，后三个是正数、自由度是"
              "≥ 1 的整数。收到的是 {given}。这三个数是同一次回归的输出，只给"
              "其中一部分说不出任何一个抽样分布；把你那份研究打印出来的四个数"
              "写全，或者一个都不写",
        "en": "δ may be declared as one number, which says it is exact, or "
              "together with the validation regression that measured it — and "
              "then all four of {fields} have to be there, the last three "
              "positive and the degrees of freedom a whole number of at least "
              "1. What arrived was {given}. Those three come out of one fit, "
              "so a subset of them names no sampling distribution: write the "
              "four numbers your study printed, or none of them",
    },
    "tracking_study_and_a_declared_variance": {
        "zh": "{exposure} 上既声明了量 δ 的那次验证回归，又声明了误差总方差 "
              "{variance}。在这种声明下总方差是**推出来的**——σ²_0＋δ²·Var(Ỹ)，"
              "每一轮按当轮的 δ 和 Var(Ỹ) 重算——所以再给一个就是把同一件事写了"
              "两遍，两者不一致的那天没有办法说校正用的是哪一个。留下那次回归，"
              "把 error_variance 去掉",
        "en": "{exposure} declares both the validation regression that "
              "measured δ and a total error variance of {variance}. Under "
              "that declaration the total is DERIVED — σ²_0 + δ²·Var(Ỹ), "
              "recomputed each round from that round's δ and Var(Ỹ) — so a "
              "second one writes the same fact twice, and the day they "
              "disagree there is no answer to which the correction used. Keep "
              "the regression and drop error_variance",
    },
    "validation_counts_unusable": {
        "zh": "{what}声明成了一份验证研究的计数表，但收到的 {given} 不是一个"
              "由非负有限计数组成的矩形。区间要按每一列的 Dirichlet 重抽这个"
              "矩阵，说不出计数就说不出分布",
        "en": "{what} was declared as a validation study's count table, and "
              "{given} is not a rectangle of non-negative finite counts. The "
              "interval redraws the matrix from each column's Dirichlet, and "
              "a tally it cannot read names no distribution",
    },
    "validation_state_never_observed": {
        "zh": "{what}的验证计数表里，第 {columns} 列（按真实状态的顺序）一个"
              "受试者都没有。那一列本该是「真实状态是它的人被记成各个状态的"
              "比例」，没有人站在那个状态上，这个比例就不是任何东西的比例",
        "en": "the validation count table for {what} has no subjects at all "
              "in column(s) {columns} (in true-state order). Each column is "
              "the proportions with which subjects at that true state were "
              "recorded, and with nobody standing there it is a proportion "
              "of nothing",
    },
    "matrix_set_declared_two_ways": {
        "zh": "沿 {axis} 变化的这组混淆矩阵里，{counted} 这些层给的是验证计数、"
              "{fixed} 这些层给的是矩阵本身。一条通道要么是数出来的、区间带着"
              "那次计数的不确定性，要么是精确给定的、区间只算主样本——两者混"
              "在一起产生的区间不是其中任何一个，而页面上是同样两个数",
        "en": "in this set of confusion matrices varying along {axis}, the "
              "levels {counted} were declared as validation tallies and the "
              "levels {fixed} as matrices. A channel is either counted, and "
              "the interval carries that counting, or exact, and the "
              "interval prices the main sample — an interval mixing the two "
              "is neither, and it is the same two numbers on the page",
    },
    "degenerate_reliability": {
        "zh": "声明给 {variable} 的测量误差方差是 {error_variance}，而 "
              "{variable} 在其余设计变量之下的方差只有 {residual_variance}，"
              "可靠度 λ = {reliability} ≤ 0。这等于说这一列里没有一点真实"
              "变异——校正要除以 λ，声明和数据在这一列上是矛盾的",
        "en": "the measurement-error variance declared for {variable} is "
              "{error_variance}, and {variable}'s variance given the rest of "
              "the design is only {residual_variance}, so the reliability "
              "λ = {reliability} ≤ 0. That says the column holds no true "
              "variation at all — the correction divides by λ, and the "
              "declaration contradicts the data in that column",
    },
    "corrected_design_not_positive_definite": {
        "zh": "校正后的设计矩阵 Σ_obs − E 不是正定的。单看每一列，可靠度都还"
              "是正的；几列同时被声明有误差时，逐列判据是必要而不充分的——"
              "这组误差方差合起来超过了数据里的联合变异，校正无从定义",
        "en": "the corrected design matrix Σ_obs − E is not positive "
              "definite. Column by column every reliability is still "
              "positive; with several columns declared mismeasured the "
              "per-column test is necessary and not sufficient — these error "
              "variances taken together exceed the joint variation in the "
              "data, and the correction is undefined",
    },
    "exposure_not_continuous": {
        "zh": "回归校准建的是连续暴露上的经典可加误差，而暴露 {column} 在这"
              "份数据上只取到 {levels} 个不同值（低于 {floor}）。离散或二值"
              "的暴露不是「测量偏了一点」，是「被归错了类」，走混淆矩阵那条路",
        "en": "regression calibration is built for classical additive error "
              "on a continuous exposure, and the exposure {column} takes "
              "only {levels} distinct values here (below {floor}). A "
              "discrete or binary exposure is not measured with a small "
              "offset but classified into the wrong category, which is what "
              "the confusion-matrix correction is for",
    },
    "mismeasured_covariate_not_continuous": {
        "zh": "被声明有测量误差的协变量 {column} 只取到 {levels} 个不同值"
              "（低于 {floor}）；协变量这一侧只建了连续变量的校正，离散协"
              "变量的误分类校正暂未建",
        "en": "the covariate {column}, declared mismeasured, takes only "
              "{levels} distinct values (below {floor}); on the covariate "
              "side only the continuous correction is built, and "
              "misclassification of a discrete covariate is deferred",
    },
    # --- what identification and the backends were left with ---------------
    # The fifteen sites the measurement family left behind, and they have
    # the opposite property: nothing here is a caller's argument. Each is
    # a judgement about what this graph, this sample or this solver can
    # reach — and the reason they kept authoring is that the names above
    # them were written for the FIRST site that met them and then met a
    # second site standing somewhere else.
    #
    # A door that ran three routes and a door that ran one cannot file the
    # same "not identifiable". A refusal raised over a moment record
    # cannot name the columns the record deliberately does not carry. A
    # polytope with a named inequality to cite and one without are not
    # equally good news. Each of those is a second name, and each of them
    # is a sentence that would otherwise be false somewhere.
    "no_first_stage": {
        "zh": "{instrument} 在这份样本里推不动 {treatment}（第一阶段统计量是 "
              "{statistic}）。工具带来的对比要除以这个数才能变成效应，"
              "而它是零——图上那条相关箭头在数据里看不见",
        "en": "{instrument} does not move {treatment} in this sample (the "
              "first-stage statistic is {statistic}). The contrast the "
              "instrument induces has to be divided by that number to "
              "become an effect, and it is zero — the graph's relevance "
              "arrow is not visible in the data",
    },
    "joint_first_stage_degenerate": {
        "zh": "{n_instruments} 个工具变量合起来也解释不了处理的任何变异"
              "（联合第一阶段统计量是 {statistic}）；它们定义的矩条件里"
              "没有可解的斜率",
        "en": "the {n_instruments} instruments together explain no variation "
              "in the treatment (the joint first-stage statistic is "
              "{statistic}); the moment condition they define has no slope "
              "to solve for",
    },
    "instrument_absorbed_by_conditioning": {
        "zh": "把 {conditioning} 从 {instrument} 里投影掉之后，{instrument} "
              "就不剩变异了（残差平方和 {residual_sum_of_squares}）。"
              "两阶段最小二乘照样会给出一个数，而那个数与 {instrument} "
              "毫无关系——这跟「工具太弱」不是一回事",
        "en": "once {conditioning} is partialled out of {instrument} there "
              "is no variation left in it (residual sum of squares "
              "{residual_sum_of_squares}). Two-stage least squares would "
              "still return a number and that number would not depend on "
              "{instrument} at all — which is not the same thing as a weak "
              "instrument",
    },
    "do_risk_not_identifiable": {
        "zh": "在这张图上，P({outcome}=1|do({exposure})) 没有可用的后门调整集，"
              "所以从观测分布里点识别不出来——最常见的原因是有一个没测到的"
              "混杂同时影响 {exposure} 和 {outcome}",
        "en": "on this graph P({outcome}=1|do({exposure})) has no admissible "
              "back-door adjustment set, so it is not point-identified from "
              "the observational distribution — most often because some "
              "unmeasured confounder affects both {exposure} and {outcome}",
    },
    "do_risk_not_identifiable_by_any_route": {
        "zh": "P({outcome}=1|do({exposure})) 这个估计量跑过的三条路都到不了："
              "没有可用的后门调整集（多半是未测混杂），两个臂都没有 ID 算法"
              "给出的估计量，图上也没有单个工具变量。不是某一条路没走通，"
              "是全部",
        "en": "P({outcome}=1|do({exposure})) is out of reach on all three "
              "routes this estimator runs: no admissible back-door "
              "adjustment set (most often an unmeasured confounder), no "
              "ID-algorithm estimand for either arm, and no single "
              "instrument on the graph. Not one route failing — all of them",
    },
    # ``{estimand}`` rather than an exposure and an outcome, for the reason
    # ``insufficient_support`` takes ``{quantity}``: what is unrecoverable
    # is a term, and one of the two sites reaches this without a treatment
    # column to name — the block it refuses on carries the target and not
    # the pair. A formula is in no language, so it is a slot like any other.
    "not_recoverable": {
        "zh": "{estimand} 在{mechanism}之下恢复不出来：没有一条只由可观测量"
              "写成的分解能还原它。不产出数字，因为照现有数据直接算出来的"
              "那个数会有偏",
        "en": "{estimand} is not recoverable under {mechanism}: no "
              "factorisation written only in observable quantities restores "
              "it. No number is produced, because one computed from the data "
              "as it stands would be biased",
    },
    "no_design_to_split_around": {
        "zh": "量化结局误测要把残差方差拆开，而这个拆分是围绕识别效应的那条"
              "设计取的；P({outcome}|do({exposure})) 在这张图上既不是后门"
              "识别、也不是前门识别，还没有工具变量，于是没有设计可以围绕。"
              "结局上的经典可加误差不改变任何条件均值——缺席的是精度代价，"
              "不是点估计",
        "en": "quantifying a mismeasured outcome means splitting the "
              "residual variance, and that split is taken around the design "
              "that identifies the effect; P({outcome}|do({exposure})) is "
              "here neither back-door nor front-door identified and has no "
              "instrument, so there is no design to take it around. A "
              "classical additive error on the outcome leaves every "
              "conditional mean unchanged — what is missing is the "
              "precision cost, not the point",
    },
    "iv_model_refuted": {
        "zh": "观测到的 P(X,Y|Z) 表违反了工具变量不等式："
              "在处理的第 {level_index} 档上 Σ_y max_z P(Y=y, X=x | Z=z) = "
              "{statistic} > 1（Pearl 1995；二值情形即 Balke-Pearl 1997 "
              "式(6)）。这个不等式只用到独立性和排他性，所以违反它就是数据"
              "在说：这个工具变量本身的假设不成立",
        "en": "the observed P(X,Y|Z) table violates the instrumental "
              "inequality: at treatment level index {level_index}, "
              "Σ_y max_z P(Y=y, X=x | Z=z) = {statistic} > 1 (Pearl 1995; "
              "Balke-Pearl 1997 eq 6 in the binary case). That inequality "
              "uses only independence and exclusion, so violating it is the "
              "data saying the instrument's own assumptions do not hold",
    },
    "iv_model_infeasible": {
        "zh": "在 {nx}×{ny}×{nz} 个层级上，没有任何一个响应型上的分布能在"
              "工具独立性 + 排他性之下重现观测到的 P(X,Y|Z) 表——线性规划"
              "无可行解。工具变量不等式在这个基数下不一定充分，所以指不出"
              "是哪一条不等式；小样本时这也可能是模型边界附近的抽样噪声",
        "en": "at {nx}×{ny}×{nz} levels no distribution over response types "
              "reproduces the observed P(X,Y|Z) table under instrument "
              "independence and exclusion — the linear program is "
              "infeasible. The instrumental inequality is not known here to "
              "be sufficient at this cardinality, so no single inequality "
              "can be pointed at; on a small sample this may also be "
              "sampling noise near the model boundary",
    },
    "convergence_failure": {
        "zh": "{backend} 这个后端在拟合中抛了错，而不是收敛到一个解；"
              "这一步没有产出数",
        "en": "the {backend} backend raised during the fit rather than "
              "converging on a solution; no number came out of this step",
    },
    # --- the family that needed the slot to hold a WORD -------------------
    # One fact told at six sites in six sentences, because the only thing
    # that differed between them was which matrix — and until the occasion
    # channel could carry a word, naming it meant writing it into prose of
    # your own. What each matrix IS lives on the member (`Design`); what
    # its being singular COSTS is the same for all six and lives here.
    "singular_design": {
        "zh": "{design}在这份样本上是奇异的——它的那些列共线——于是需要它的"
              "那个拟合没有唯一解；最小范数解只是众多选择里的一个，"
              "所以不产出数字",
        "en": "{design} is singular on this sample — its columns are "
              "collinear — so the fit that needs it has no unique solution; "
              "a minimum-norm answer would be one choice among many, and no "
              "number is produced",
    },
    # The seventh site of that species was never that fact. Nothing is
    # singular here — the fit is exact, and a statistic that divides by what
    # it left over divides by zero.
    "no_residual_variation": {
        "zh": "结构残差平方和 û'û 是 {sum_of_squares}：在这份样本上结局是处理的"
              "精确线性函数，于是 Sargan 统计量 n·û'P_Z û / û'û 是 0/0，"
              "过度识别检验无从谈起",
        "en": "the structural residual sum of squares û'û is "
              "{sum_of_squares}: the outcome is an exact linear function of "
              "the treatment on this sample, so the Sargan statistic "
              "n·û'P_Z û / û'û is 0/0 and the over-identification test "
              "cannot be formed",
    },
    # The same shape one estimator over: a misclassification correction runs
    # two channels, and every sentence about a channel had to name it. The
    # word was carried as a bare English label whose ABSENCE meant "the
    # outcome", so the exposure's matrix was rejected in the outcome's name.
    "singular_confusion_matrix": {
        "zh": "{role}的混淆矩阵不可逆（|det| = {determinant}，低于阈值 "
              "{floor}）：作为测量模型它对真实的{role}没有携带可用信息，"
              "校正无从定义——它没区分开的东西，再多数据也换不回来",
        "en": "the {role} confusion matrix is not invertible (|det| = "
              "{determinant}, below the floor of {floor}): as a measurement "
              "model it carries no usable information about the true {role}, "
              "so the correction is undefined — and no quantity of data "
              "recovers what it does not distinguish",
    },
    "singular_confusion_matrix_in_stratum": {
        "zh": "{axis}={level} 这一层的{role}混淆矩阵不可逆（|det| = "
              "{determinant}，低于阈值 {floor}）：差异性校正给每一层各配一个"
              "矩阵，别的层替不了它——各层不同正是这个模型的主张——"
              "所以校正在这一层无从定义",
        "en": "the {role} confusion matrix for {axis}={level} is not "
              "invertible (|det| = {determinant}, below the floor of "
              "{floor}): a differential correction gives every level its own "
              "matrix and no other level's can stand in — that they differ "
              "is what the model claims — so the correction is undefined in "
              "that level",
    },
    # --- the five that reached the envelope through the second door ------
    # Each had exactly ONE site, and that site was a dict literal in
    # dispatch: not a species carrying several facts, just a sentence
    # written where it was thrown instead of beside the species it belongs
    # to. Nothing said so, because the gate that counts authors looks for
    # calls to the three doors and a dict literal is not one — these five
    # read as species with no sites at all.
    "differential_combined_misclassification_deferred": {
        "zh": "暴露 {exposure} 和结局 {outcome} 都给了混淆矩阵，而其中至少一个"
              "是 differential 的。联合校正把观测表分解成 M_x · P_true · M_yᵀ，"
              "这只在两个矩阵都恒定时成立；differential 的矩阵由另一条通道正在"
              "误测的那个层级选出，于是这个分解——以及建立在它上面的校正——不成立",
        "en": "a confusion matrix was supplied for both the exposure "
              "{exposure} and the outcome {outcome}, and at least one of them "
              "is differential. The combined correction factorises the "
              "observed table as M_x · P_true · M_yᵀ, which holds only while "
              "each matrix is constant; a differential matrix is selected by "
              "a level the other channel mismeasures, so the factorisation — "
              "and the correction built on it — does not apply",
    },
    "external_data_required": {
        "zh": "{exposure} 对 {outcome} 的效应在这种选择偏倚下，只有拿到外部无偏"
              "数据才恢复得出来（{needed}）。在对撞限制过的样本上算普通后门估计"
              "会有偏，所以不产出",
        "en": "the effect of {exposure} on {outcome} is recoverable from this "
              "selection bias only with external unbiased data ({needed}). "
              "The ordinary back-door estimate on the collider-restricted "
              "sample would be biased and is withheld",
    },
    "mismeasured_covariate_not_in_adjustment": {
        "zh": "给 {variable} 提供了测量误差方差，而它既不是暴露、也不在后门"
              "调整集 {adjustment} 里；一个混杂要先被调整，才谈得上被校正",
        "en": "a measurement-error variance was supplied for {variable}, "
              "which is neither the exposure nor a covariate in the back-door "
              "adjustment set {adjustment}; a confounder must be adjusted for "
              "to be corrected",
    },
    # Says nothing about WHICH g-method ran, and that is the correction: the
    # sentence it replaces named the g-formula twice, on a block whose
    # ``estimator`` field is conditional — so an ipw_msm run was told the
    # g-formula estimate would be biased. Sequential exchangeability is what
    # both of them need, and the block already carries which one ran.
    "not_identified": {
        "zh": "时变策略效应在这张图上不可识别：序贯可交换性不成立——在已测历史"
              "之下，仍有某个处理到结局之间存在一条未阻断的后门。不产出数字，"
              "因为沿这条路算出来的数会有偏",
        "en": "the time-varying strategy effect is not identified on this "
              "graph: sequential exchangeability fails — given the measured "
              "history, some treatment still has an unblocked back-door to "
              "the outcome. No number is produced, because one computed on "
              "this route would be biased",
    },
    "requires_a_point_estimate": {
        "zh": "{exposure} 对 {outcome} 的效应在这里是靠工具变量识别的，而这条"
              "设计的拆分是围绕结构残差 Var(Y − βX − γ'W)——也就是围绕 β̂ 本身"
              "——取的。这次查询没有产出点估计，也就没有 β̂ 可以围绕，因此不出"
              "评估",
        "en": "the effect of {exposure} on {outcome} is identified here "
              "through an instrument, and that design's split is taken around "
              "the structural residual Var(Y − βX − γ'W) — around β̂ itself. "
              "No point estimate was produced for this query, so there is no "
              "β̂ to take it around; no assessment is issued",
    },
    # The one species whose sentence deliberately says nothing about the
    # occasion. Ten handlers in dispatch caught an exception nobody had
    # typed and put ``str(exc)`` on the envelope as the reader's ``reason``
    # — the shape #403 took off the web edge, one layer in. The exception's
    # own text is a maintainer's, so it goes to ``details.diagnostic`` and
    # is not interpolated here: a reader told "we do not know why" and
    # handed a stack-trace fragment reads the fragment as the answer.
    #
    # It says only what its BACKEND framing does not. That the routine
    # returned nothing, and that this decides nothing about the question,
    # are the frame's two sentences (``analysis_report._kind_words``); what
    # is left for the species is why the refusal has no better name.
    "unknown": {
        "zh": "它抛出的错误在本版本里没有对应的名字，所以这里说不出更具体的"
              "原因。",
        "en": "the error it raised has no name in this build, so nothing "
              "more specific can be said here.",
    },

    # --- the sites the author count could not see -------------------------
    # Seventeen more, in two families that file a refusal by RAISING A
    # SUBCLASS: ``iv._NotStratifiable`` and the counterfactual solver's
    # ``CounterfactualBoundsError``. The counter above reads the call by
    # the name at the door, so neither family was ever in its denominator —
    # and three species reached a reader with no sentence here at all,
    # kept alive by the messages those sites were still writing.
    #
    # What the two families had in common with the fifteen before them is
    # the pattern: one name over several facts. ``conditioning_too_fine``
    # covered a sample too thin to cut, a column past a per-column cap and
    # a set past a total cap — three different repairs. ``counterfactual_
    # inputs_infeasible`` said "either the sources contradict each other or
    # the monotonicity is refuted", and only ever had the second sentence.
    "conditioning_too_fine": {
        "zh": "条件列 {column} 取 {distinct_values} 个不同的值，超过这一版每列"
              "枚举的 {cap} 档；每层大约还有 {rows_per_level} 行，所以卡住的是"
              "这一版的枚举上限，不是样本",
        "en": "the conditioning column {column} takes {distinct_values} "
              "distinct values, past the {cap} per column this build "
              "enumerates; its strata would still hold about "
              "{rows_per_level} rows each, so the limit is this build's and "
              "not the sample's",
    },
    "too_many_strata": {
        "zh": "条件集 {conditioning} 把样本切成 {strata} 层，超过这一版枚举的 "
              "{cap} 层；没有哪一列单独过界，是它们的乘积过了",
        "en": "the conditioning set {conditioning} cuts the sample into "
              "{strata} strata, past the {cap} this build enumerates; no one "
              "column is over on its own — their product is",
    },
    "strata_would_be_too_thin": {
        "zh": "条件列 {column} 在 {rows} 行上取 {distinct_values} 个不同的值，"
              "切出来每层平均只有 {rows_per_level} 行——达不到一个层里每个工具"
              "臂所需的 {minimum_per_arm} 行。这是样本的限制，不是这一版的",
        "en": "the conditioning column {column} takes {distinct_values} "
              "distinct values over {rows} rows, so its strata would hold "
              "about {rows_per_level} rows each — short of the "
              "{minimum_per_arm} per instrument arm a stratum needs. The "
              "limit is the sample's, not this build's",
    },
    # Names the value and not the column, because the solver reaches this
    # holding an arm of the intervention and not the frame it came from —
    # and the reader is looking at the query they asked.
    "interventional_risk_not_identifiable": {
        "zh": "要给出这一格，还需要 P(Y=1 | do(X={intervention}))：它在这张图上"
              "识别不出来，调用也没有给；只有观测联合分布的话，这一格就只能落"
              "在 [0, 1] 里",
        "en": "this cell needs P(Y=1 | do(X={intervention})), which is not "
              "identified on this graph and was not supplied; with the "
              "observational joint alone the cell sits anywhere in [0, 1]",
    },
    "not_a_probability": {
        "zh": "{what} 要落在 [0, 1] 里才是概率；收到的是 {given}",
        "en": "{what} has to lie in [0, 1] to be a probability; got {given}",
    },
    "inputs_contradict_by_consistency": {
        "zh": "P(Y=1|do(X={intervention}))={given} 与观测联合分布对不上：一致"
              "性把它锁在 [{lower}, {upper}] 里。两个数据来源互相矛盾，这里没有"
              "哪条假设需要改",
        "en": "P(Y=1|do(X={intervention}))={given} cannot hold with this "
              "observational joint: consistency confines it to [{lower}, "
              "{upper}]. The two sources contradict each other, and no "
              "assumption here is at fault",
    },
}


def sentence(failure_type, details=None,
             lang: language.Lang | str = language.DEFAULT) -> str | None:
    """The reader's sentence for this refusal, or ``None`` for a species
    that has not been given one yet.

    ``None`` rather than a fallback: a species still authoring its sentence
    at the raise site has one already, and inventing a second here would be
    the duplication this table exists to remove. The count of species in
    that state is a gate, so the ``None`` is visible rather than quiet.
    """
    words = SAYS.get(str(_registered(failure_type)))
    return None if words is None else language.fill(
        words, lang, **{k: language.slot(v, lang) for k, v in (details or {}).items()})


class EstimatorFailure(RuntimeError):
    """Raised when an estimator will not produce a number.

    Dispatch turns this into a structured ``estimator_failure`` block
    carrying the species, so a caller branches on the cause instead of
    parsing the message. The species must be one this module declares:
    checking here catches at run time what the annotation catches when
    the file is read, for the callers that are not read.

    ``details`` carries the numbers behind the refusal — which stratum,
    how many rows, what determinant — which belong to the occasion rather
    than to the species. They are what the species' sentence in
    :data:`SAYS` interpolates, and a raise site names its slots here and
    nowhere else.

    THERE IS NO ``message``. A site could pass one until #433, and while
    any site did, ``record`` had to relay ``str(exc)`` onto the envelope
    to avoid losing it — which is how the counterfactual solver's fourteen
    English sentences reached readers through a door the author count
    could not see. Take the sentence out of the relay and a site that
    passes one loses it silently; take it out of the constructor and the
    situation cannot arise. The count of sites that were using it was
    zero, and had been for a cut and a half.

    ``recorded`` is the same occasion's facts that its sentence does NOT
    say. Both audiences existed already, one name did not: ``details``
    names a container rather than a reader, and ``str.format`` drops a
    keyword its template has no hole for without a word, so a fact the
    species deliberately withholds (the exception's own text, which is a
    maintainer's) and a fact the sentence should have carried and does not
    looked identical — thirty-three raise sites, and the only way anyone
    knew was a script written for the occasion (#430). The module already
    draws this line one level up: :attr:`Refusal.says` is the maintainer's
    and :data:`SAYS` is the reader's, and both docstrings say so. This is
    the same line, for the occasion's facts instead of the species'.

    So ``details`` is now exactly the sentence's arguments, which lets a
    gate compare the two SETS rather than one inclusion, and ``recorded``
    is where an estimator puts what it measured and did not say. Nothing
    reads either field today — ``details`` reaches the envelope and no
    rendering surface, as one raise site's comment already observed — so
    what the split buys is not a new reader but a contract that can be
    checked: adding a fact to a refusal is now a choice between saying it
    and recording it, made where the fact is.

    The message is capped here rather than at the surface that shows it:
    a reader handed 62,000 characters is the estimator's doing, not the
    renderer's, and a cap applied where the refusal is born is a cap on
    every entrance to it. It cannot raise — a refusal that crashed on the
    length of its own explanation would turn "no number, and here is why"
    into no answer at all.
    """

    def __init__(self, failure_type: Refusal, *, recorded: dict | None = None,
                 remedies=None, **details):
        species = _registered(failure_type)
        # Before ``language.occasion`` flattens them: a word is a member here and a
        # bare token afterwards, and which set it came from is the thing
        # the flattening loses.
        self.said, self.words = language.halve(details)
        details = {k: language.occasion(v) for k, v in details.items()}
        recorded = {k: language.occasion(v) for k, v in (recorded or {}).items()}
        self.remedies = _routes(remedies)
        message = sentence(species, details)
        if message is None:
            raise ValueError(
                f"{species} has no sentence in themis.refusals.SAYS and "
                f"this raise site gave none; declare it there, beside the "
                f"species, so the reader's wording has one author"
            )
        super().__init__(language.capped(message))
        self.failure_type = species
        self.details = details
        self.recorded = recorded


def _routes(remedies) -> list[dict]:
    """The occasion's routes out, in the one shape they take on the envelope.

    A member on its own where it names nothing, a ``(member, subject)`` pair
    where it names something. Which of the two is the member's to decide, so
    the pairing is checked here rather than discovered by a reader meeting a
    ``{subject}`` that never got filled.

    Accepts its own output, because two boundaries normalise: a raise site,
    which is where a mistake should be reported, and :func:`block`, which
    the identification layer calls with no exception in hand. :func:`record`
    relays one to the other, and a normaliser that could not accept what it
    had already produced would make the relay reach around it.
    """
    out = []
    for entry in remedies or ():
        if isinstance(entry, Mapping):
            entry = (entry["remedy"], entry.get("subject"))
        member, subject = entry if isinstance(entry, tuple) else (entry, None)
        member = _remedy(member)
        if member.takes_object != (subject is not None):
            raise ValueError(
                f"{member} {'names something' if member.takes_object else 'names nothing'}"
                f"; got subject={subject!r}. Which it is belongs to the "
                f"member, not to the raise site."
            )
        row: dict = {"remedy": str(member)}
        if subject is not None:
            row["subject"] = language.occasion(subject)
        out.append(row)
    return out


def _registered(failure_type) -> Refusal:
    """The species by that name, or a refusal to proceed without one."""
    species = BY_NAME.get(str(failure_type))
    if species is None:
        raise ValueError(
            f"unregistered failure_type {str(failure_type)!r}; declare it "
            f"in themis.refusals beside the others, with the kind that "
            f"says what the reader should do about it"
        )
    return species


def block(*, estimator: str, failure_type, details=None,
          recorded=None, remedies=None) -> dict:
    """The one shape a refusal takes on the envelope.

    Two layers refuse, and until now only one of them said so in this
    shape. An estimator raises :class:`EstimatorFailure` and dispatch
    catches it; identification has no estimator and no exception to
    catch — it returns the result outright. Both are answering "why is
    there no number", so both put this block on the envelope, and the
    consumers that branch on ``failure_type`` and ``kind`` — the report,
    the browser, the schema's enum — cover both without knowing there
    were two layers.

    The species is checked here as well as at :class:`EstimatorFailure`,
    for the reason :func:`stamp` checks it a third time: a caller with no
    exception to raise has no constructor to validate it.

    THERE IS NO ``reason``. The block carried one until #411 and it was a
    sentence, which meant the language was chosen here — at the moment of
    refusing, by the process that has no reader in front of it. What the
    block carries instead is the sentence's PARTS: ``said`` for the slots
    that render the same in every language, ``words`` for the slots that
    do not, and the species, whose template every reading surface holds.
    The sentence is made where the reader's language is known.

    ``recorded`` is the occasion's other half — what was measured and not
    said. See :class:`EstimatorFailure` for why the two have separate
    names; the short version is that one bag with two audiences cannot be
    checked, because a keyword the sentence has no hole for is dropped in
    silence whether that was the intention or not.
    """
    species = _registered(failure_type)
    if str(species) not in SAYS:
        raise ValueError(
            f"{species} has no sentence in themis.refusals.SAYS; declare it "
            f"there, beside the species, so the reader's wording has one "
            f"author. Nothing downstream can supply one — the block carries "
            f"the sentence's PARTS and every surface fills that template"
        )
    raw = details or {}
    said, words = language.halve(raw)
    return _envelope(
        estimator=estimator, species=species,
        details={k: language.occasion(v) for k, v in raw.items()},
        said=said, words=words,
        recorded={k: language.occasion(v) for k, v in (recorded or {}).items()},
        remedies=_routes(remedies),
    )


def _envelope(*, estimator: str, species: Refusal, details: dict,
              said: dict, words: dict, recorded: dict,
              remedies: list) -> dict:
    """The one shape, assembled once.

    Both doors reach it with the same six things in hand and neither may
    spell the shape out again: the block is what every consumer branches
    on, and two assemblies of it are two chances for a key to appear on one
    path and not the other. An empty part is absent rather than empty, for
    the rule the schema states once — "there is nothing here" has one
    spelling.
    """
    out: dict = {"estimator": estimator, "failure_type": species}
    for key, part in (("details", details), ("said", said),
                      ("words", words), ("recorded", recorded),
                      ("remedies", remedies)):
        if part:
            out[key] = part
    return out


def said(failure: Mapping, lang: language.Lang | str = language.DEFAULT
         ) -> str:
    """A refusal off an envelope, as the sentence this reader gets.

    The reader's half of :func:`block`. Every surface that shows a refusal
    calls this — or, in the browser, the twin generated from the same
    tables — and none of them writes a word of it: the template is the
    species', the value slots arrived rendered, and the word slots are
    looked up in the sets this build declares.

    A species with no template is said by its token, and a HOLE the
    envelope carried nothing for is said by its own name — both for the
    reason :func:`themis.language.gloss` gives, and both only reachable
    from an envelope this build did not write. Every door refuses a
    speechless species where the refusal happens, and both fill the holes
    from the same ``details`` the template was authored against; what is
    left is a result read back from another build, and that reader is
    exactly the one who must not be handed a traceback instead of an
    answer.
    """
    tok = str(failure.get("failure_type") or "")
    template = SAYS.get(tok)
    if template is None:
        return language.gloss({}, tok, lang)
    return language.assemble(
        template, failure.get("said"), failure.get("words"), lang)


def outcome(failure: Mapping) -> ResultStatus:
    """What became of a query whose whole result is this refusal.

    :attr:`Kind.outcome` holds the answer, one per kind, and this is the
    lookup that spares a caller the two hops. The caller it exists for is
    identification, which returns a result rather than raising and so is
    the layer that has to name a status — and named one per CATCH SITE
    until #434, where a site catches a family: the counterfactual solver's
    spans nine species over four kinds, and both handlers wrote the status
    that fits one of the nine.

    Only where the refusal is the whole result. Where a result also carries
    an identification answer, its status is about THAT, and the data end's
    refusals all ride such results.
    """
    return _registered(failure.get("failure_type")).kind.outcome


def record(result: dict, *, estimator: str, exc: EstimatorFailure) -> None:
    """Write a caught refusal onto the envelope, in the one shape it has.

    A handler that catches :class:`EstimatorFailure` knows exactly one
    thing the exception does not carry — which estimator was running.
    Everything else is already in hand, so the block is assembled here
    rather than at each handler, where the shape had become a convention:
    several guarded ``failure_type`` with a fallback that cannot fire now
    that the constructor validates it, and all but one dropped
    ``details``.

    The occasion's facts are the part worth naming. The species says why
    a number was withheld and the kind says what to do about it; the
    occasion says which stratum was empty, how many rows it held, how wide
    the bandwidth was. Dropping them leaves a reader knowing the shape of
    the problem and nothing about its size — and the estimator had already
    paid to measure it. They travel in two fields because they have two
    audiences: ``details`` is what the sentence names, ``recorded`` is what
    it does not.

    Writing the block is not the same as answering with it. Which claim
    the handler then makes over the query — that the refusal is final, or
    that a later estimator may still answer — is the handler's to decide
    and stays at the handler.
    """
    result["estimator_failure"] = relayed(estimator=estimator, exc=exc)


def relayed(*, estimator: str, exc: EstimatorFailure) -> dict:
    """A caught refusal as the block it becomes, for a caller with no dict.

    :func:`record` writes into a result that already exists; identification
    builds its ``QueryResult`` in one expression and has nowhere to write
    yet. Both are relaying the same exception, so the relay is one function
    and the difference stays at the two call sites.

    It passes no sentence. The species has the template, and an exception
    that reached here was constructed from the same species and the same
    ``details`` — handing over ``str(exc)`` would be this layer choosing a
    language for text it did not write, and it is what let the
    counterfactual solver's fourteen English sentences reach an envelope
    without any count of authors seeing them.

    It reaches past :func:`block` to the shape they share, because the
    split into ``said`` and ``words`` was made at the raise site, on the
    values as they were passed. By the time they are on the exception they
    have been through :func:`themis.language.occasion` and a word is a bare token again —
    recomputing the split here would be reading a fact after the field
    that carried it was flattened.
    """
    return _envelope(
        estimator=estimator,
        species=exc.failure_type,
        details=exc.details,
        said=exc.said,
        words=exc.words,
        recorded=exc.recorded,
        remedies=exc.remedies,
    )
