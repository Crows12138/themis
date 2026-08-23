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

from collections.abc import Mapping
from enum import unique

from . import language
from .types import EnvelopeName, envelope_scalar

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
    """

    GRAPH = "graph"
    """The causal structure does not permit this quantity. More of the same
    data will not help; the graph or the query has to change."""

    DATA = "data"
    """The structure permits it and this sample cannot support it — an empty
    stratum, a singular design, too few rows. Different data would work."""

    UNBUILT = "unbuilt"
    """The question is well-posed and identified, and Themis has not built
    this case. An honest gap, not an error."""

    REQUEST = "request"
    """The request or an input the caller supplied is malformed or
    inconsistent with the data. The caller changes something and retries."""

    BACKEND = "backend"
    """A numeric routine did not return an answer. No verdict has been passed
    on the question, the graph, or the data — which is also why ``unknown``
    files here: it diagnoses nothing, and a kind that claimed more would be
    claiming it on ``unknown``'s behalf."""


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
        "the observed P(X,Y|Z) table is incompatible with ANY IV model at "
        "this cardinality — the declared instrument's own assumptions are "
        "refuted",
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
        "one treatment arm, so the term the formula needs there is the "
        "outcome model's extrapolation rather than a comparison the data "
        "made. The sample has the contrast; this cell does not",
    )
    NO_FIRST_STAGE = (
        "no_first_stage",
        Kind.DATA,
        "the instrument does not move the treatment in this sample, so the "
        "contrast it induces divides by zero instead of scaling into an "
        "effect — the graph's relevance arrow is not visible in the data",
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
    CONTINUOUS_MEDIATOR = (
        "continuous_mediator",
        Kind.UNBUILT,
        "the front-door plug-in sums over mediator strata exactly, and this "
        "mediator is continuous or too fine to enumerate — the continuous "
        "case needs density estimation, which is deferred",
    )
    MEDIATOR_STRATA_INTRACTABLE = (
        "mediator_strata_intractable",
        Kind.UNBUILT,
        "each mediator is discrete but their combinations are too many to "
        "enumerate — the estimand is well posed, the exact sum over it is "
        "not affordable",
    )
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
    TREATMENT_LEVELS_DIFFER = (
        "treatment_levels_differ",
        Kind.UNBUILT,
        "a joint intervention's corner puts every treatment at one shared "
        "pair of values, and these treatments do not present one — each can "
        "be binary and still be binary on a different pair, which is what "
        "leaves the corner undefined, and is not the one above",
    )
    EXPOSURE_NOT_BINARY = (
        "exposure_not_binary",
        Kind.UNBUILT,
        "exposure misclassification correction is binary-exposure only",
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
    CONDITIONING_TOO_FINE = (
        "conditioning_too_fine",
        Kind.UNBUILT,
        "the stratified Wald aggregates over the cells of the conditioning "
        "set, and this set is finer than the cut it will enumerate",
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
    COUNTERFACTUAL_CELL_OUT_OF_SCOPE = (
        "counterfactual_cell_out_of_scope",
        Kind.UNBUILT,
        "the cell asked for is outside the bounds machinery's reach",
    )
    COUNTERFACTUAL_CELL_CROSS_VARIABLE = (
        "counterfactual_cell_cross_variable",
        Kind.UNBUILT,
        "the cell estimator intervenes on one variable at two values; a "
        "cell across two different variables is a different quantity",
    )

    # --- the request has to change --------------------------------------------
    INVALID_INPUT = (
        "invalid_input",
        Kind.REQUEST,
        "the estimator rejected its inputs — the catch-all for a "
        "malformed request whose own message says what was wrong",
    )
    INVALID_CONFUSION_MATRIX = (
        "invalid_confusion_matrix",
        Kind.REQUEST,
        "a supplied confusion matrix is not square, not column-stochastic, "
        "or not finite — it is not a misclassification model",
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
        "the declared measurement-error variance meets or exceeds the "
        "variation there is to correct, so the corrected design is not "
        "positive definite — the declaration contradicts the data",
    )
    PROXY_CARDINALITY_MISMATCH = (
        "proxy_cardinality_mismatch",
        Kind.REQUEST,
        "the proxies do not each present the number of levels the declared "
        "latent cardinality says they have; the declaration and the data "
        "disagree, and the matrix-inversion formula needs them to agree",
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
    DIFFERENTIAL_BY_UNKNOWN = (
        "differential_by_unknown",
        Kind.REQUEST,
        "the axis the misclassification is said to differ by is not a "
        "variable that can carry it",
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
    NON_POSITIVE_ERROR_VARIANCE = (
        "non_positive_error_variance",
        Kind.REQUEST,
        "a declared measurement-error variance is absent or not positive, "
        "and the correction it scales is undefined",
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
    COUNTERFACTUAL_INPUTS_INFEASIBLE = (
        "counterfactual_inputs_infeasible",
        Kind.REQUEST,
        "the supplied quantities admit no SCM at all — either the given "
        "interventional risk contradicts the observational joint through "
        "consistency, or the declared monotonicity is refuted by them "
        "jointly. The caller's sources disagree with each other",
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
class Design(language.Word):
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


@unique
class QueryRole(language.Word):
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


BY_NAME: dict[str, Refusal] = {str(species): species for species in Refusal}
"""The species going by that envelope name, or nothing.

``Refusal(name)`` is the same lookup and is the one to use where an
unknown name is an error. This is for the places where it is a question:
what we read is deliberately wider than what we emit, so "is this a
species we know" has to be answerable with no.
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


# A refusal's message is the reader's answer line: dispatch puts it there
# verbatim. That makes its length a property of the data, and one suite run
# measured what that costs — a message naming an outcome's observed levels
# rendered 3000 floats into a single sentence, 62,003 characters of it, 55
# times. Nothing was wrong with the sentence; the value put into it was a
# column.
#
# So the cap below is a backstop for the reader, not a fix. The fix is
# ``describe``, which is bounded by construction; a truncated message means
# a raise site is still interpolating a value raw, and a test asserts the
# backstop never fires in the suite so that site is found here rather than
# by whoever reads the answer.
_MESSAGE_CAP = 1000
# Two kinds of collection reach a refusal's sentence and they want
# opposite treatment. A list of names — an adjustment set, a design's
# variables, an outcome's declared states — IS the answer, and cutting
# it drops the thing the reader needs. A column of data values is only
# evidence for a count, and it has no ceiling: the measured case was
# 3000 floats. So the cutoff is read off the elements, not fixed.
_NAME_SAMPLE = 12
_VALUE_SAMPLE = 3


def describe(value, *, sample: int | None = None) -> str:
    """One value, as a refusal's sentence should carry it.

    Numpy scalars come back as their Python equivalents — ``np.False_`` and
    ``np.float64(0.0)`` are how a repr of a dataframe cell reads, and the
    reader did not ask about our array library. Collections say how many
    they are and show a few, because "how many levels" is the fact the
    refusal turns on and the levels themselves are the occasion's, which
    belong in ``details`` — and they say it in symbols, because this runs
    inside a sentence that HAS a language, and a count written in words
    arrives in English however that sentence was written. Four levels
    under ``treatment_not_binary`` was enough to reach a Chinese reader.

    A stratum arrives as ``{column: level}``, which :func:`_occasion` names
    on the envelope's side of this same path. This side had no branch for
    it, so a mapping fell through to the length test and rendered its KEYS:
    ``{'channel': 2}`` reached a reader as ``['channel']`` with the level
    silently gone. Three estimators wrote a cell rendering of their own
    rather than use this one, and that they had to is the same fact.

    Five copies of a numpy coercion already exist across the estimators,
    under four names, and every one of them justifies itself as JSON
    safety — a value bound for the envelope. They are not this function
    and this function does not replace them: they hand back a value, this
    hands back prose. The point is that the envelope's path had a step
    and the sentence's path had none.
    """
    scalar = getattr(value, "item", None)
    if scalar is not None and hasattr(value, "dtype") and getattr(
        value, "ndim", 1
    ) == 0:
        value = scalar()
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, Mapping):
        return ", ".join(
            f"{k}={describe(v)}" for k, v in value.items()) or "{}"
    if isinstance(value, (str, bytes)) or not hasattr(value, "__len__"):
        return repr(value)
    items = list(value)
    if sample is None:
        sample = (
            _NAME_SAMPLE
            if items and all(isinstance(v, str) for v in items)
            else _VALUE_SAMPLE
        )
    if len(items) <= sample:
        return "[" + ", ".join(describe(v) for v in items) + "]"
    shown = ", ".join(describe(v) for v in items[:sample])
    return f"[{shown}, … +{len(items) - sample}]"


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
    "degenerate_recovered_exposure": {
        "zh": "分层 z={stratum} 恢复出的真实暴露边际非正"
              "（P(X*=1|z)={p_treated}，P(X*=0|z)={p_control}）；条件风险因此"
              "无定义——混淆矩阵在这一层里信息太弱，识别不了效应",
        "en": "the stratum z={stratum} recovers a non-positive true exposure "
              "marginal (P(X*=1|z)={p_treated}, P(X*=0|z)={p_control}), so the "
              "conditional risk is undefined — the confusion matrix is too "
              "weakly informative to identify the effect in that stratum",
    },
    "no_usable_resample": {
        "zh": "{model} 估计量的 {resamples} 次 bootstrap 重抽样全部退化，"
              "区间没有可以取分位数的抽样",
        "en": "all {resamples} bootstrap resamples were degenerate for the "
              "{model} estimator, so there are no draws to take an interval "
              "from",
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
        "zh": "反事实单格估计只处理布尔量；{label}={value}",
        "en": "the counterfactual cell estimator is boolean-only; "
              "{label}={value}",
    },
    "counterfactual_inputs_infeasible": {
        "zh": "声明的单调性把结局与处理反向的那些单位剔除之后，没有任何响应型"
              "分布能重现 P(X, Y | Z)——工具变量与这张表是相容的，被推翻的是"
              "单调性假设",
        "en": "no distribution over response types reproduces P(X, Y | Z) "
              "once the declared monotonicity removes the units whose outcome "
              "moves against the treatment — the instrument is compatible "
              "with this table and the monotonicity assumption is what it "
              "refutes",
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
    "mediator_strata_intractable": {
        "zh": "前门分层的交叉积是 {combinations}，超过了 {cap} 组合的上限；"
              "中介取值组合太多，无法精确枚举",
        "en": "the front-door stratum cross-product is {combinations}, over "
              "the {cap}-combination cap; there are too many mediator level "
              "combinations to enumerate exactly",
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
    "no_first_stage": {
        "zh": "{instruments} 在这份样本里没有推动 {treatment}（第一阶段统计量 "
              "{statistic}）：工具带来的对比除以的是零，而不是被缩放成一个效应",
        "en": "{instruments} does not move {treatment} in this sample "
              "(first-stage statistic {statistic}): the contrast the "
              "instrument induces divides by zero instead of scaling into an "
              "effect",
    },
    "no_within_stratum_contrast": {
        "zh": "只有一个处理臂的层：{strata}——层里有行，两个臂之间的对比不在"
              "里面；逐层标准化要在每一层内比较两臂，缺的那一臂只能由结局"
              "模型外推补上",
        "en": "strata that hold one treatment arm: {strata} — the rows are "
              "there and the contrast between the arms is not among them; "
              "standardization compares the arms within each stratum, and "
              "the missing arm can only be supplied by the outcome model's "
              "extrapolation",
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
    "not_identifiable_proximal": {
        "zh": "近端识别在 {criterion} 这一条上拒答：{detail}",
        "en": "proximal identification refused at {criterion}: {detail}",
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
              "「连续」测量。离散结局属于误分类，它的误差确实会衰减效应——改为"
              "提供一份经验证的混淆矩阵（misclassification=），那个能校正它",
        "en": "the outcome {outcome} has only {distinct} distinct values; an "
              "additive error variance describes a CONTINUOUS measurement. A "
              "discrete outcome is a misclassification object, and its error "
              "does attenuate the effect — supply a validated confusion "
              "matrix (misclassification=) instead, which corrects it",
    },
    "proxy_cardinality_mismatch": {
        "zh": "近端公式 (5) 要求每个代理都恰好呈现 k={k} 个层级；实际 "
              "|Z|={z}、|W|={w}。把更细的代理粗化到 k 层还没有支持",
        "en": "proximal formula (5) needs each proxy to present exactly k={k} "
              "levels; observed |Z|={z}, |W|={w}. Coarsening a finer proxy to "
              "k levels is not yet supported",
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
    # sites on the exposure channel said the same thing under
    # ``exposure_not_binary``, whose fact is a different one — that this
    # correction is binary-exposure only. Naming the column serves both, and
    # serves the reader better than either: it is the name they used.
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
    "undefined_conditioning_event": {
        "zh": "条件合取 δ 的概率为 0，所以条件概率 P(γ|δ) 无定义；给不出数",
        "en": "the conditioning conjunction δ has probability 0, so the "
              "conditional P(γ|δ) is undefined; no number can be produced",
    },
    "unit_underobserved": {
        "zh": "这个单位缺少 {variable} 的事实取值；abduction 无法恢复它的外生项",
        "en": "the unit is missing a factual value for {variable}; abduction "
              "cannot recover its exogenous term",
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
              "数据才恢复得出来（{needed}）。把它作为 reference_data= 传进来才"
              "能算出恢复后的 ATE；在对撞限制过的样本上算普通后门估计会有偏，"
              "所以不产出",
        "en": "the effect of {exposure} on {outcome} is recoverable from this "
              "selection bias only with external unbiased data ({needed}). "
              "Supply it as reference_data= to compute the recovered ATE; the "
              "ordinary back-door estimate on the collider-restricted sample "
              "would be biased and is withheld",
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
}


def _occasion(value):
    """One of the occasion's numbers, as the envelope is able to hold it.

    ``details`` reaches a reader through ``estimator_failure.details``, so
    it answers to :func:`themis.types.envelope_scalar` like everything else
    on that path — and it answers here, once, rather than at each of the
    raise sites, which is the arrangement that let five of them ship a
    numpy scalar into a dict on its way to ``json.dumps``.

    Containers recurse. A stratum arrives as ``{column: level}`` and a set
    of missing columns as a list, and JSON writes both down — coercing only
    the scalars would leave a Python repr standing where the structure was,
    which is the failure this half exists to prevent, one level in.

    A value that refuses the coercion is written down rather than raised
    over. That is the one place this departs from the envelope's rule, and
    the reason is the rule :func:`_capped` already follows: a refusal that
    crashed while recording why it refused would turn "no number, and here
    is why" into no answer at all. The rule's own justification does not
    reach here either — a printed value is indistinguishable from a string
    value to whatever re-derives from it, and nothing re-derives from
    ``details``; the schema types it ``object`` and names no key.
    """
    if isinstance(value, Mapping):
        return {str(k): _occasion(v) for k, v in value.items()}
    if isinstance(value, (set, frozenset)):
        value = sorted(value, key=str)
    if isinstance(value, (list, tuple)):
        return [_occasion(v) for v in value]
    try:
        return envelope_scalar(value)
    except TypeError:
        return repr(value)


def _slot(value, lang: language.Lang | str = language.DEFAULT) -> str:
    """One of the occasion's facts, as a sentence carries it.

    A collection says how many it is and shows a few, and a float says six
    significant figures — both by way of :func:`describe`, which is where
    that judgement already lived. Everything else says itself: brackets and
    quotation marks are the SENTENCE's, and the sentence is in :data:`SAYS`
    where one author can see both languages of it at once. Reading them off
    ``!r`` at the raise site is what made them the raise site's, and it is
    why a column name arrived quoted in some refusals and bare in others.

    A WORD is the one that is not a value said back. Which matrix was
    singular, which channel was mismeasured — a member of a closed
    vocabulary, whose token is what the envelope carries and is in no
    language at all. Stringifying it would put that token into whichever
    language the sentence is in, which is the defect the table exists to
    remove; several species could not be folded at all while this channel
    could only carry numbers, because the one thing that differed between
    their sites was exactly this.
    """
    if isinstance(value, language.Word):
        return type(value).said(value, lang)
    if isinstance(value, (float, list, tuple, Mapping)):
        return describe(value)
    return str(value)


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
        words, lang, **{k: _slot(v, lang) for k, v in (details or {}).items()})


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
    :data:`SAYS` interpolates, so a raise site that gives no ``message``
    is naming its slots here and nowhere else.

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

    def __init__(self, failure_type: Refusal, message: str | None = None,
                 *, recorded: dict | None = None, **details):
        species = _registered(failure_type)
        details = {k: _occasion(v) for k, v in details.items()}
        recorded = {k: _occasion(v) for k, v in (recorded or {}).items()}
        if message is None:
            message = sentence(species, details)
            if message is None:
                raise ValueError(
                    f"{species} has no sentence in themis.refusals.SAYS and "
                    f"this raise site gave none; declare it there, beside the "
                    f"species, so the reader's wording has one author"
                )
        super().__init__(_capped(message))
        self.failure_type = species
        self.details = details
        self.recorded = recorded


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


def _capped(message) -> str:
    """The message, bounded. Never raises: a refusal that crashed on the
    length of its own explanation would turn "no number, and here is why"
    into no answer at all."""
    message = str(message)
    if len(message) <= _MESSAGE_CAP:
        return message
    return (
        message[:_MESSAGE_CAP]
        + f"… (truncated at {_MESSAGE_CAP} characters — a value was "
        f"interpolated raw; see themis.refusals.describe)"
    )


def block(*, estimator: str, failure_type, reason=None, details=None,
          recorded=None) -> dict:
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

    ``reason`` is optional for the same reason ``message`` is optional at
    the constructor, and this is the half that was missing. The sentence
    belongs to the species; a caller that composed one here would be the
    second author of a field the constructor had just been given one
    author for, and being the layer with no exception to raise is not a
    reason to write in a different language. Omit it and the species
    speaks, out of :data:`SAYS`, filled from ``details``.

    ``recorded`` is the occasion's other half — what was measured and not
    said. See :class:`EstimatorFailure` for why the two have separate
    names; the short version is that one bag with two audiences cannot be
    checked, because a keyword the sentence has no hole for is dropped in
    silence whether that was the intention or not.
    """
    species = _registered(failure_type)
    details = {k: _occasion(v) for k, v in (details or {}).items()}
    recorded = {k: _occasion(v) for k, v in (recorded or {}).items()}
    if reason is None:
        reason = sentence(species, details)
        if reason is None:
            raise ValueError(
                f"{species} has no sentence in themis.refusals.SAYS and this "
                f"caller gave no reason=; declare it there, beside the "
                f"species, so the reader's wording has one author"
            )
    out: dict = {
        "estimator": estimator,
        "failure_type": species,
        "reason": _capped(reason),
    }
    if details:
        out["details"] = details
    if recorded:
        out["recorded"] = recorded
    return out


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
    result["estimator_failure"] = block(
        estimator=estimator,
        failure_type=exc.failure_type,
        reason=str(exc),
        details=exc.details,
        recorded=exc.recorded,
    )
