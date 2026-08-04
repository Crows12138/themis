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

A species also declares its ``kind``, because "no number" is not one
answer but five, and which one it is decides what the reader should do
next: fix the graph, get more data, wait for us to build it, correct the
request, or simply retry. The kind rides out on the envelope, stamped
from here at the exit — a consumer that had to map sixty-four species
onto those five itself would be keeping a second copy of this file, in
TypeScript or in a prompt, and it would drift the way the schema's enum
drifted.

**This is the estimator's refusal, not the narrative extractor's.**
:mod:`themis.upstream.narrative_merge` carries its own ``refusals`` — a
language model declining to propose an edge it was asked about — which
shares the word and nothing else.
"""
from __future__ import annotations


# --- what kind of refusal it is -----------------------------------------------
#
# The distinction a consumer acts on. Declared beside the species by
# whoever adds it, because only the estimator knows whether it stopped at
# the graph, at the data, or at the edge of what it implements — and
# declared there once, so no raise site and no reader has to decide it.

KIND_GRAPH = "graph"
"""The causal structure does not permit this quantity. More of the same
data will not help; the graph or the query has to change."""

KIND_DATA = "data"
"""The structure permits it and this sample cannot support it — an empty
stratum, a singular design, too few rows. Different data would work."""

KIND_UNBUILT = "unbuilt"
"""The question is well-posed and identified, and Themis has not built
this case. An honest gap, not an error."""

KIND_REQUEST = "request"
"""The request or an input the caller supplied is malformed or
inconsistent with the data. The caller changes something and retries."""

KIND_BACKEND = "backend"
"""A numeric routine did not return an answer. No verdict has been passed
on the question, the graph, or the data — which is also why ``unknown``
files here: it diagnoses nothing, and a kind that claimed more would be
claiming it on ``unknown``'s behalf."""

KINDS = (KIND_GRAPH, KIND_DATA, KIND_UNBUILT, KIND_REQUEST, KIND_BACKEND)


class Refusal(str):
    """One named reason an estimator produced no number.

    A ``str`` subclass, so a species is usable wherever its name was: in
    the envelope, in a comparison, through ``json.dumps``. What it adds
    is that the name exists in exactly one place, and that ``kind`` and
    ``says`` travel with it instead of living in whichever message
    happened to be raised.
    """

    def __new__(cls, name: str, *, kind: str, says: str) -> "Refusal":
        if kind not in KINDS:
            raise ValueError(
                f"refusal {name!r} declares kind {kind!r}, which is not one "
                f"of {list(KINDS)}"
            )
        species = super().__new__(cls, name)
        species.kind = kind    # type: ignore[misc]
        species.says = says    # type: ignore[misc]
        return species

    def __repr__(self) -> str:
        return f"Refusal({str(self)!r})"

    def __reduce__(self):
        """Copies and pickles come back as the plain name.

        The species travels into the envelope, and the envelope is data:
        whoever copies or serializes it must get back exactly the string
        that was always there. What ``kind`` and ``says`` record belongs
        to the registry, not to each place the name appears.
        """
        return (str, (str(self),))


# --- the graph does not permit it ---------------------------------------------

NOT_IDENTIFIED = Refusal(
    "not_identified",
    kind=KIND_GRAPH,
    says="the strategy effect is not identified by the g-formula — "
         "sequential exchangeability fails, so the number would be biased",
)
DO_RISK_NOT_IDENTIFIABLE = Refusal(
    "do_risk_not_identifiable",
    kind=KIND_GRAPH,
    says="P(Y=1|do(X)) is not back-door identifiable from the "
         "observational distribution on this graph",
)
INTERVENTIONAL_RISK_NOT_IDENTIFIABLE = Refusal(
    "interventional_risk_not_identifiable",
    kind=KIND_GRAPH,
    says="the interventional risk a counterfactual cell is computed from "
         "is not identified here",
)
NOT_IDENTIFIABLE_BY_GENERAL_ID = Refusal(
    "not_identifiable_by_general_id",
    kind=KIND_GRAPH,
    says="Shpitser-Pearl ID returned a hedge: the effect is not "
         "point-identified non-parametrically on this ADMG",
)
NOT_IDENTIFIABLE_BY_IDC = Refusal(
    "not_identifiable_by_idc",
    kind=KIND_GRAPH,
    says="the same, for a conditional effect, through IDC",
)
NOT_IDENTIFIABLE_COUNTERFACTUAL = Refusal(
    "not_identifiable_counterfactual",
    kind=KIND_GRAPH,
    says="ID*/IDC* found no identifying expression for the counterfactual "
         "conjunction",
)
NOT_IDENTIFIABLE_PROXIMAL = Refusal(
    "not_identifiable_proximal",
    kind=KIND_GRAPH,
    says="the proximal criteria failed: the named proxies do not identify "
         "the effect through a bridge function",
)
NOT_RECOVERABLE = Refusal(
    "not_recoverable",
    kind=KIND_GRAPH,
    says="the estimand is not recoverable under the declared selection or "
         "missingness mechanism",
)
IV_MODEL_REFUTED = Refusal(
    "iv_model_refuted",
    kind=KIND_GRAPH,
    says="the observed P(X,Y|Z) table is incompatible with ANY binary IV "
         "model — the declared instrument's own assumptions are refuted",
)

# --- this data cannot support it ----------------------------------------------

INSUFFICIENT_SUPPORT = Refusal(
    "insufficient_support",
    kind=KIND_DATA,
    says="a stratum the identifying formula sums over has no rows — a "
         "positivity violation, so the sum is not the estimand",
)
OVERLAP_INSUFFICIENT = Refusal(
    "overlap_insufficient",
    kind=KIND_DATA,
    says="an arm or sampling point carries no contrast to estimate from",
)
NO_FIRST_STAGE = Refusal(
    "no_first_stage",
    kind=KIND_DATA,
    says="the instrument does not move the treatment in this sample, so the "
         "contrast it induces divides by zero instead of scaling into an "
         "effect — the graph's relevance arrow is not visible in the data",
)
NO_USABLE_RESAMPLE = Refusal(
    "no_usable_resample",
    kind=KIND_DATA,
    says="every bootstrap resample was degenerate for this estimator, so the "
         "interval has no draws to be a quantile of",
)
SAMPLE_TOO_SMALL = Refusal(
    "sample_too_small",
    kind=KIND_DATA,
    says="the sample is below the minimum this estimator will speak on",
)
EMPTY_OUTCOME = Refusal(
    "empty_outcome",
    kind=KIND_DATA,
    says="the outcome column has no observed values",
)
ADJUSTMENT_ALL_MISSING = Refusal(
    "adjustment_all_missing",
    kind=KIND_DATA,
    says="an adjustment column is never observed, so its marginal — which "
         "the standardisation weights by — cannot be formed",
)
RANK_DEFICIENT_DESIGN = Refusal(
    "rank_deficient_design",
    kind=KIND_DATA,
    says="the OLS design for a node is rank-deficient; a minimum-norm fit "
         "would be a choice among many, not the coefficient",
)
RANK_CONDITION_VIOLATED = Refusal(
    "rank_condition_violated",
    kind=KIND_DATA,
    says="P(W|Z,x) is singular or ill-conditioned: the proxies are not "
         "jointly informative enough to invert",
)
SINGULAR_DESIGN = Refusal(
    "singular_design",
    kind=KIND_DATA,
    says="the design covariance is singular — collinear covariates",
)
SINGULAR_CONFUSION_MATRIX = Refusal(
    "singular_confusion_matrix",
    kind=KIND_DATA,
    says="the confusion matrix is non-invertible: the measurement carries "
         "no usable information about the true value",
)
DEGENERATE_RELIABILITY = Refusal(
    "degenerate_reliability",
    kind=KIND_DATA,
    says="the corrected design is not positive definite — the declared "
         "measurement-error variance leaves no signal to correct",
)
DEGENERATE_RECOVERED_EXPOSURE = Refusal(
    "degenerate_recovered_exposure",
    kind=KIND_DATA,
    says="a stratum recovers a non-positive true exposure probability, so "
         "the corrected distribution is not a distribution",
)
UNIT_UNDEROBSERVED = Refusal(
    "unit_underobserved",
    kind=KIND_DATA,
    says="the unit is missing a factual value that abduction needs to pin "
         "its exogenous term",
)
UNDEFINED_CONDITIONING_EVENT = Refusal(
    "undefined_conditioning_event",
    kind=KIND_DATA,
    says="the conditioning conjunction has probability zero, so what is "
         "asked for is undefined rather than unknown",
)
PROXY_CARDINALITY_MISMATCH = Refusal(
    "proxy_cardinality_mismatch",
    kind=KIND_DATA,
    says="the proxies do not each present the number of levels the "
         "matrix-inversion formula needs",
)

# --- Themis has not built this case -------------------------------------------

INTRACTABLE_ESTIMAND = Refusal(
    "intractable_estimand",
    kind=KIND_UNBUILT,
    says="the identified estimand has too high a treewidth to evaluate by "
         "variable elimination — beyond the plug-in's reach, not wrong",
)
REQUIRES_BACKDOOR_IDENTIFICATION = Refusal(
    "requires_backdoor_identification",
    kind=KIND_UNBUILT,
    says="this correction composes with back-door standardisation, and the "
         "query was not back-door identified here",
)
NOT_A_JOINT_INTERVENTION = Refusal(
    "not_a_joint_intervention",
    kind=KIND_UNBUILT,
    says="the joint plug-in needs at least two treatments",
)
TOO_MANY_JOINT_TREATMENTS = Refusal(
    "too_many_joint_treatments",
    kind=KIND_UNBUILT,
    says="the joint plug-in enumerates a saturated basis over the treatment "
         "vector, and past a small number of treatments that basis is larger "
         "than any sample identifies",
)
CONTINUOUS_MEDIATOR = Refusal(
    "continuous_mediator",
    kind=KIND_UNBUILT,
    says="the front-door plug-in sums over mediator strata exactly, and this "
         "mediator is continuous or too fine to enumerate — the continuous "
         "case needs density estimation, which is deferred",
)
MEDIATOR_STRATA_INTRACTABLE = Refusal(
    "mediator_strata_intractable",
    kind=KIND_UNBUILT,
    says="each mediator is discrete but their combinations are too many to "
         "enumerate — the estimand is well posed, the exact sum over it is "
         "not affordable",
)
DIFFERENTIAL_COMBINED_MISCLASSIFICATION_DEFERRED = Refusal(
    "differential_combined_misclassification_deferred",
    kind=KIND_UNBUILT,
    says="differential misclassification of exposure AND outcome together "
         "is a different correction than either alone, and is not built",
)
TREATMENT_NOT_BINARY = Refusal(
    "treatment_not_binary",
    kind=KIND_UNBUILT,
    says="this estimator is binary-treatment only",
)
EXPOSURE_NOT_BINARY = Refusal(
    "exposure_not_binary",
    kind=KIND_UNBUILT,
    says="exposure misclassification correction is binary-exposure only",
)
EXPOSURE_NOT_CONTINUOUS = Refusal(
    "exposure_not_continuous",
    kind=KIND_UNBUILT,
    says="regression calibration is for a continuous exposure; a nearly "
         "discrete one wants the confusion-matrix correction instead",
)
OUTCOME_NOT_BINARY = Refusal(
    "outcome_not_binary",
    kind=KIND_UNBUILT,
    says="this estimator is binary-outcome only",
)
INSTRUMENT_NOT_BINARY = Refusal(
    "instrument_not_binary",
    kind=KIND_UNBUILT,
    says="the Balke-Pearl bounds enumerate response types over a binary "
         "instrument; a multi-valued one is a larger enumeration",
)
OUTCOME_NOT_CONTINUOUS = Refusal(
    "outcome_not_continuous",
    kind=KIND_UNBUILT,
    says="classical additive outcome error is defined for a continuous "
         "outcome; a discrete one wants the confusion-matrix correction",
)
CONTINUOUS_OUTCOME = Refusal(
    "continuous_outcome",
    kind=KIND_UNBUILT,
    says="confusion-matrix correction needs a discrete outcome with few "
         "enough states to name",
)
CONTINUOUS_ADJUSTMENT = Refusal(
    "continuous_adjustment",
    kind=KIND_UNBUILT,
    says="this correction standardises over discrete strata, and an "
         "adjustment covariate has too many distinct values",
)
ADJUSTMENT_NOT_DISCRETE = Refusal(
    "adjustment_not_discrete",
    kind=KIND_UNBUILT,
    says="the same, for the missingness recovery formula",
)
CONDITIONING_TOO_FINE = Refusal(
    "conditioning_too_fine",
    kind=KIND_UNBUILT,
    says="the stratified Wald aggregates over the cells of the conditioning "
         "set, and this set is finer than the cut it will enumerate",
)
MISMEASURED_COVARIATE_NOT_CONTINUOUS = Refusal(
    "mismeasured_covariate_not_continuous",
    kind=KIND_UNBUILT,
    says="a covariate declared mismeasured is not continuous, and only the "
         "continuous correction is built for covariates",
)
CAUSE_OR_EFFECT_NOT_BINARY = Refusal(
    "cause_or_effect_not_binary",
    kind=KIND_UNBUILT,
    says="probabilities of causation are defined here for binary cause and "
         "effect",
)
COUNTERFACTUAL_CELL_NOT_BINARY = Refusal(
    "counterfactual_cell_not_binary",
    kind=KIND_UNBUILT,
    says="the counterfactual cell estimator is boolean-only",
)
COUNTERFACTUAL_CELL_OUT_OF_SCOPE = Refusal(
    "counterfactual_cell_out_of_scope",
    kind=KIND_UNBUILT,
    says="the cell asked for is outside the bounds machinery's reach",
)
COUNTERFACTUAL_CELL_CROSS_VARIABLE = Refusal(
    "counterfactual_cell_cross_variable",
    kind=KIND_UNBUILT,
    says="the cell estimator intervenes on one variable at two values; a "
         "cell across two different variables is a different quantity",
)

# --- the request has to change ------------------------------------------------

INVALID_INPUT = Refusal(
    "invalid_input",
    kind=KIND_REQUEST,
    says="the estimator rejected its inputs — the catch-all for a "
         "malformed request whose own message says what was wrong",
)
INVALID_CONFUSION_MATRIX = Refusal(
    "invalid_confusion_matrix",
    kind=KIND_REQUEST,
    says="a supplied confusion matrix is not square, not column-stochastic, "
         "or not finite — it is not a misclassification model",
)
INVALID_MONOTONICITY = Refusal(
    "invalid_monotonicity",
    kind=KIND_REQUEST,
    says="a declared monotonicity direction is neither non-decreasing nor "
         "non-increasing",
)
STATES_INCOMPLETE = Refusal(
    "states_incomplete",
    kind=KIND_REQUEST,
    says="values occur in the data that the declared state list omits, so "
         "the correction would silently drop them",
)
DIFFERENTIAL_SPEC_INCOMPLETE = Refusal(
    "differential_spec_incomplete",
    kind=KIND_REQUEST,
    says="a differential-misclassification spec is missing a part it needs "
         "to say which matrix applies where",
)
DIFFERENTIAL_LEVELS_MISMATCH = Refusal(
    "differential_levels_mismatch",
    kind=KIND_REQUEST,
    says="the supplied matrices and the levels they are indexed by do not "
         "line up one to one",
)
DIFFERENTIAL_BY_UNKNOWN = Refusal(
    "differential_by_unknown",
    kind=KIND_REQUEST,
    says="the axis the misclassification is said to differ by is not a "
         "variable that can carry it",
)
DIFFERENTIAL_LEVEL_UNCOVERED = Refusal(
    "differential_level_uncovered",
    kind=KIND_REQUEST,
    says="a level occurring in the data has no confusion matrix supplied "
         "for it",
)
MISMEASURED_VARIABLE_NOT_IN_DESIGN = Refusal(
    "mismeasured_variable_not_in_design",
    kind=KIND_REQUEST,
    says="measurement error was supplied for a variable that is not in the "
         "design, so there is nothing to correct",
)
MISMEASURED_COVARIATE_NOT_IN_ADJUSTMENT = Refusal(
    "mismeasured_covariate_not_in_adjustment",
    kind=KIND_REQUEST,
    says="a covariate declared mismeasured is not in the adjustment set "
         "the effect was identified through",
)
MISSING_COLUMN = Refusal(
    "missing_column",
    kind=KIND_REQUEST,
    says="a column the query names is not in the data",
)
REFERENCE_MISSING_COLUMN = Refusal(
    "reference_missing_column",
    kind=KIND_REQUEST,
    says="the external unbiased reference sample is missing a column the "
         "recovery formula reweights by",
)
TARGET_VALUE_ABSENT = Refusal(
    "target_value_absent",
    kind=KIND_REQUEST,
    says="the target value the query asks about is not among the declared "
         "or observed states",
)
ATOM_NOT_IN_GRAPH = Refusal(
    "atom_not_in_graph",
    kind=KIND_REQUEST,
    says="an intervention or target atom is not a variable of the SCM",
)
INTERVENTION_IS_TARGET = Refusal(
    "intervention_is_target",
    kind=KIND_REQUEST,
    says="the intervention and the target are the same variable, so the "
         "counterfactual is its own assignment",
)
NON_POSITIVE_ERROR_VARIANCE = Refusal(
    "non_positive_error_variance",
    kind=KIND_REQUEST,
    says="a declared measurement-error variance is absent or not positive, "
         "and the correction it scales is undefined",
)
OUTCOME_ERROR_EXCEEDS_RESIDUAL_VARIANCE = Refusal(
    "outcome_error_exceeds_residual_variance",
    kind=KIND_REQUEST,
    says="the declared outcome error variance exceeds the residual "
         "variance in the data — the declaration contradicts what is there",
)
EXTERNAL_DATA_REQUIRED = Refusal(
    "external_data_required",
    kind=KIND_REQUEST,
    says="the effect IS recoverable, with unbiased external data the call "
         "did not supply; the block names what to pass",
)
COUNTERFACTUAL_INPUTS_INFEASIBLE = Refusal(
    "counterfactual_inputs_infeasible",
    kind=KIND_REQUEST,
    says="the supplied quantities admit no SCM at all — either the given "
         "interventional risk contradicts the observational joint through "
         "consistency, or the declared monotonicity is refuted by them "
         "jointly. The caller's sources disagree with each other",
)

# --- a backend gave up --------------------------------------------------------

CONVERGENCE_FAILURE = Refusal(
    "convergence_failure",
    kind=KIND_BACKEND,
    says="the underlying regressor raised rather than converged",
)
MODEL_FIT_FAILED = Refusal(
    "model_fit_failed",
    kind=KIND_BACKEND,
    says="the same, for an outcome or mediator model on the full sample",
)
UNKNOWN = Refusal(
    "unknown",
    kind=KIND_BACKEND,
    says="the estimator failed in a way nothing has classified — the only "
         "species that admits the block does not know what it is saying",
)


ALL: frozenset[Refusal] = frozenset(
    value for value in tuple(globals().values()) if isinstance(value, Refusal)
)
"""Every species of refusal an estimator may emit.

Collected from this module rather than listed again below it: a species
declared above and forgotten here would be exactly the drift this module
exists to end.
"""

BY_NAME: dict[str, Refusal] = {str(species): species for species in ALL}

BY_KIND: dict[str, tuple[Refusal, ...]] = {
    kind: tuple(sorted(s for s in ALL if s.kind == kind)) for kind in KINDS
}


def stamp(result: dict) -> None:
    """Send every refusal out bearing the ``kind`` its species declares.

    A refusal is written at some thirty sites, each of which knows the
    occasion — which estimator, which stratum, what the caller should
    have supplied. None of them knows anything about the *kind* that the
    species does not already say, so none of them writes it: the
    registry stamps it here, at the exit, and a consumer reading the
    envelope branches on five values instead of on sixty-four.

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
    belong in ``details``.

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
    return f"{len(items)} values (e.g. {shown}, ...)"


class EstimatorFailure(RuntimeError):
    """Raised when an estimator will not produce a number.

    Dispatch turns this into a structured ``estimator_failure`` block
    carrying the species, so a caller branches on the cause instead of
    parsing the message. The species must be one this module declares:
    checking here catches a misspelling at the moment the refusal is
    born, which is earlier and more precise than catching it at the exit.

    ``details`` is free-form and goes into the block as-is — the numbers
    behind the refusal (which stratum, how many rows, what determinant),
    which belong to the occasion rather than to the species.

    The message is capped here rather than at the surface that shows it:
    a reader handed 62,000 characters is the estimator's doing, not the
    renderer's, and a cap applied where the refusal is born is a cap on
    every entrance to it. It cannot raise — a refusal that crashed on the
    length of its own explanation would turn "no number, and here is why"
    into no answer at all.
    """

    def __init__(self, failure_type: str, message: str, **details):
        species = BY_NAME.get(str(failure_type))
        if species is None:
            raise ValueError(
                f"unregistered failure_type {str(failure_type)!r}; declare it "
                f"in themis.refusals beside the others, with the kind that "
                f"says what the reader should do about it"
            )
        message = str(message)
        if len(message) > _MESSAGE_CAP:
            message = (
                message[:_MESSAGE_CAP]
                + f"… (truncated at {_MESSAGE_CAP} characters — a value was "
                f"interpolated raw; see themis.refusals.describe)"
            )
        super().__init__(message)
        self.failure_type = species
        self.details = details


def record(result: dict, *, estimator: str, exc: EstimatorFailure) -> None:
    """Write a caught refusal onto the envelope, in the one shape it has.

    A handler that catches :class:`EstimatorFailure` knows exactly one
    thing the exception does not carry — which estimator was running.
    Everything else is already in hand, so the block is assembled here
    rather than at each handler, where the shape had become a convention:
    several guarded ``failure_type`` with a fallback that cannot fire now
    that the constructor validates it, and all but one dropped
    ``details``.

    ``details`` is the part worth naming. The species says why a number
    was withheld and the kind says what to do about it; the details say
    which stratum was empty, how many rows it held, how wide the
    bandwidth was. Dropping them leaves a reader knowing the shape of the
    problem and nothing about its size — and the estimator had already
    paid to measure it.

    Writing the block is not the same as answering with it. Which claim
    the handler then makes over the query — that the refusal is final, or
    that a later estimator may still answer — is the handler's to decide
    and stays at the handler.
    """
    block = {
        "estimator": estimator,
        "failure_type": exc.failure_type,
        "reason": str(exc),
    }
    if exc.details:
        block["details"] = exc.details
    result["estimator_failure"] = block
