"""Which shape the model takes, and who settled it.

Ten estimators resolved a caller's ``model=`` into a concrete form, and every
one of them computed the same by-product on the way and threw it away: whether
the shape was CHOSEN by the system because nothing was specified, or NAMED by
the caller. The two are not distinguishable afterwards — a resolved
``"logistic"`` and a caller's ``"logistic"`` are the same string — so a
disclosure surface asking "who decided the functional form" downstream has
nothing to read, and the one that asked wrote ``"default"`` as a literal at
fourteen call sites. A constant is not an answer, and for the families whose
form is fixed by the method it was the wrong one.

Seven of those ten resolutions are also the SAME resolution — a bool outcome is
a probability and takes the logit link, anything else is a mean and takes the
line — written in seven spellings across four modules. The other three ask
different questions (a backend by sample size, a Wald family by the instrument's
support) but answer the same second question, so :func:`chosen_by` is what they
share and :func:`outcome_form` is what the seven share.

A form nothing resolved at all — the plug-in families, whose method IS its
shape — is :attr:`Provenance.INHERENT`, and those estimators say so beside the
constant they carry rather than through here: there is no resolution to hook.

**Which shapes a method can fit was decided everywhere and written nowhere.**
The estimators refuse outside their set — ``model="a_shape_nobody_declared"``
comes back as ``unknown model``, and ``iv`` even lists its five in the
refusal — but the decision lives in control flow and in a sentence, so the
one field that says what a number was actually fitted through,
``mechanism_audit.mechanisms[].form``, was any string at all. The three
fields beside it are held: ``method`` against the estimate's own account,
each named assumption against the estimate's declaration, ``target``
against the question. :data:`FITS` is that missing statement, and it is
per-method because that is the grain the paragraph above already names:
which forms an estimator can fit is that estimator's question, so a global
table would be the wrong authority answering it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import MappingProxyType

import pandas as pd

from ..ledger import Provenance


#: What a caller writes to leave the shape to the system. Spelled once because
#: it is the value the whole distinction turns on.
AUTO = "auto"

#: What a caller writes to name the non-linear arm. Spelled once for the same
#: reason :data:`AUTO` is, and needed for a second one: the families that share
#: :func:`outcome_form` do not all SPELL that arm the same way, so the word the
#: caller uses and the word the family's method string carries are two
#: different facts and only one of them is this.
LOGISTIC = "logistic"


def chosen_by(model: str) -> Provenance:
    """Who settled the form: the system, or the caller.

    The reader can act on the difference and on nothing else here — a form the
    system picked is one they can override by naming another, and a form they
    named is one they already own. Which is what
    :attr:`Provenance.DEFAULT.answerable` and
    :attr:`Provenance.CALLER_ASSERTED.answerable` say in the vocabulary this
    returns into.
    """
    return Provenance.DEFAULT if model == AUTO else Provenance.CALLER_ASSERTED


def outcome_form(
    model: str, outcome: pd.Series, *, logistic: str = "logistic",
) -> tuple[str, Provenance]:
    """The outcome model's shape, and its origin.

    ``auto`` reads the outcome column: bool is a probability and takes the
    non-linear link, anything else is a mean and takes the line. Anything the
    caller names is passed through untouched — including a name this function
    has never heard of, because which forms an estimator can fit is that
    estimator's question and refusing here would answer it for all of them.

    ``logistic`` names the non-linear arm because the mediation family spells
    it ``logit`` on its estimate, in its method string and in its tests.
    Spelling is not what this unifies.

    Which is why naming that arm resolves like ``auto`` does rather than
    passing through. The ``logistic=`` argument exists to say what THIS family
    calls the non-linear arm, and translating only the system's choice left the
    same arm coming back under two words depending on who picked it: a bool
    outcome under ``auto`` resolved to ``'logit'`` and ran, and the caller who
    named that very arm got ``'logistic'`` — a word the mediation estimator
    refuses, listing ``['logit', 'linear']`` at a caller who cannot write
    ``logit`` because the entry's option does not carry it. A translator that
    runs in one direction only is not a translator; it is a default with a
    blind spot on the other side.
    """
    if model == AUTO:
        is_bool = pd.api.types.is_bool_dtype(outcome)
        return (logistic if is_bool else "linear"), Provenance.DEFAULT
    if model == LOGISTIC:
        return logistic, Provenance.CALLER_ASSERTED
    return model, Provenance.CALLER_ASSERTED


#: What a caller leaves a NON-STRING shape lever at to say nothing about it.
#: ``AUTO`` above is the same idea for ``model=``, and a lever whose default
#: is a real value — a floor of 0.01, a ``stabilized=True`` — cannot tell a
#: caller who named that value from a caller who named nothing, so the answer
#: to "who settled this" is destroyed at the call and there is nothing
#: downstream to read. Which is how one estimate came to report the same
#: unchanged propensity floor as ``inherent``, ``default`` and
#: ``caller_asserted`` on three different runs.
UNSET = None

#: A family that settles every shape it has with the outcome model reports no
#: exceptions, and this is that. Immutable rather than a fresh ``{}``: it is a
#: dataclass default on every estimate in this layer, and a shared mutable
#: there is a bug waiting for the first estimator that edits its own.
NO_OTHER_SHAPES: Mapping[str, Provenance] = MappingProxyType({})


def pulled_by(value: object) -> Provenance:
    """Who set a shape lever this run: the caller, or nobody.

    :func:`chosen_by` one axis over. That one reads ``model=``, whose
    do-nothing value is a word the caller writes; this one reads a lever
    whose do-nothing value is the absence of one, which is what
    :data:`UNSET` is for.
    """
    return Provenance.DEFAULT if value is UNSET else Provenance.CALLER_ASSERTED


#: The two shapes :func:`outcome_form` resolves to, and the spelling the
#: mediation family gives the second — its ``logistic=`` argument, named at
#: all four of its call sites. Kept apart rather than unified: the note on
#: that parameter says spelling is not what this module unifies, and the two
#: families' estimates, method strings and tests all spell it their own way.
_OUTCOME_SHAPES = frozenset({"linear", "logistic"})
_MEDIATION_SHAPES = frozenset({"linear", "logit"})

#: What ``iv`` resolves ``model=`` to. The same five its own refusal lists.
_IV_SHAPES = frozenset({"wald", "stratified_wald", "2sls", "acr"})

#: ``simex`` builds its form out of two levers, so its set is their product.
#: Re-declared here rather than imported: ``simex`` is a family and this is
#: the shared module every family reads, and a test pins the two equal — the
#: arrangement :mod:`themis.risk_provenance` uses for the same reason.
_SIMEX_FITTERS = frozenset({"linear", "logistic"})
_SIMEX_EXTRAPOLANTS = frozenset({"linear", "quadratic", "rational"})

#: What ``dose_response`` resolves ``model=`` to — one backend per shape, and
#: the method names below spell the backend rather than the shape, so this set
#: cannot be built by :func:`_spelt_into` the way the six families are.
_DOSE_RESPONSE_SHAPES = frozenset({"linear", "forest", "drlearner"})


# --- the words a caller may write, which are not the shapes they resolve to --
#
# Everything above answers "what did this method fit". These answer "what may
# the caller ASK for", and the two were the same table for so long that the
# difference stopped being visible. They are not the same:
#
#   * ``auto`` is a word every route takes and no route fits — it is the
#     caller declining to choose, so it belongs in every set here and in none
#     of the sets above;
#   * ``iv`` reads ``model=`` as which ESTIMATOR to run, not which shape to
#     fit, so its words name Wald / 2SLS / ACR rather than a link function;
#   * a family whose method IS its shape still has a vocabulary, and it has
#     exactly one word. Saying so is what makes naming any other word a
#     refusal instead of a silence.
#
# Derived from the resolved sets rather than written beside them, so a shape
# added to a family cannot leave the word that asks for it behind.

MODEL_WORDS_OUTCOME = _OUTCOME_SHAPES | {AUTO}
MODEL_WORDS_IV = _IV_SHAPES | {AUTO}
MODEL_WORDS_DOSE_RESPONSE = _DOSE_RESPONSE_SHAPES | {AUTO}

#: For a route that fits one shape because its method IS that shape. Not an
#: empty set and not ``None``: a row that takes no choice still answers the
#: question, and the answer is that the only thing a caller may say here is
#: that they are not choosing.
MODEL_WORDS_NONE = frozenset({AUTO})

#: The one word of :data:`MODEL_WORDS_IV` that names an estimator with a ROW
#: of its own rather than a branch inside one. Over-identified IV is the
#: two-stage fit — several instruments, with the Sargan test beside it — so
#: a caller who writes it there is naming exactly what that row does, and a
#: row declaring only ``auto`` would refuse them the right word. Honoured by
#: the row's identity rather than by a parameter, which is a real way to
#: honour a request and not a loophole: what the option asks for is what
#: runs.
MODEL_WORD_TWO_STAGE = "2sls"


def _spelt_into(prefix: str, shapes: frozenset[str]
                ) -> dict[str, frozenset[str]]:
    """Rows for a family that builds its METHOD NAME out of the form.

    Six families do — ``f"backdoor_{resolved}"``, ``f"iv_{resolved}"`` and
    the rest — and pass that same ``resolved`` as the estimate's ``form``.
    Writing those rows out by hand would be a second copy of that
    construction, kept true by whoever remembered; built the same way, the
    row and the method name cannot disagree. It also covers the members
    nobody has exercised yet, which is the point: a table assembled from a
    run would refuse ``cde_logit`` for never having been seen.
    """
    return {f"{prefix}{shape}": frozenset({shape}) for shape in shapes}


#: Which shapes each method can fit.
#:
#: Keyed by method because the method is the field beside ``form`` on the
#: block, is already held to the estimate that ran, and is itself held to a
#: declared set per identification family in the verifier. So a form checked
#: against its method is checked against something that cannot be claimed
#: freely.
#:
#: The rows come from watching the build produce them — a plugin over the
#: whole suite, recording every pair that reached the audit — and NOT from
#: the answer-shape corpus, which is a sample of what somebody once ran and
#: says both fewer methods and fewer forms than exist. It says ``tmle``
#: fits ``logistic``; ``tmle`` fits ``linear`` whenever the outcome is not a
#: bool, and both were driven end to end.
FITS: dict[str, frozenset[str]] = {
    # The six that spell the form into the method name.
    **_spelt_into("backdoor_", _OUTCOME_SHAPES),
    **_spelt_into("frontdoor_", _OUTCOME_SHAPES),
    **_spelt_into("frontdoor_empirical_", _OUTCOME_SHAPES),
    **_spelt_into("joint_backdoor_", _OUTCOME_SHAPES),
    **_spelt_into("iv_", _IV_SHAPES),
    **_spelt_into("cde_", _MEDIATION_SHAPES),
    **_spelt_into("cde_chain_", _MEDIATION_SHAPES),
    # The two that resolve a form and keep one method name for both.
    "aipw": _OUTCOME_SHAPES,
    "tmle": _OUTCOME_SHAPES,
    # The mediation estimates, whose method names carry the spelling.
    "mediation_linear_imai": frozenset({"linear"}),
    "mediation_logit_imai": frozenset({"logit"}),
    "mediation_joint_linear": frozenset({"linear"}),
    "mediation_joint_logit": frozenset({"logit"}),
    # The dose-response backends, one method per backend.
    "dose_response_linear_dml": frozenset({"linear"}),
    "dose_response_causal_forest_dml": frozenset({"forest"}),
    "dose_response_linear_drlearner": frozenset({"drlearner"}),
    # The two counterfactual plug-ins, whose form says which route reached
    # the interventional risk they borrowed.
    "causation_plugin": frozenset({
        "nonparametric_c_factor_plug_in",
        "nonparametric_gformula_plug_in",
        "nonparametric_response_function_lp",
    }),
    "counterfactual_cell_plugin": frozenset({
        "nonparametric_c_factor_plug_in",
        "nonparametric_gformula_plug_in",
        "nonparametric_response_function_lp",
    }),
    # And the families whose method IS its shape.
    "ctf_conjunction_plugin": frozenset({"nonparametric_plug_in"}),
    "general_id_plugin": frozenset({"nonparametric_plug_in"}),
    "general_id_idc_plugin": frozenset({"nonparametric_plug_in"}),
    "joint_general_id_plugin": frozenset({"nonparametric_plug_in"}),
    "ipw_stabilized": frozenset({"logistic_propensity"}),
    "ipw_ht": frozenset({"logistic_propensity"}),
    "iv_2sls_overid": frozenset({"two_stage_least_squares"}),
    "iv_anderson_rubin_region": frozenset({"linear_in_the_treatment_vector"}),
    "longitudinal_gformula": frozenset({
        "sequential_regression_g_formula_simulation"}),
    "longitudinal_ipw_msm": frozenset({
        "marginal_structural_model_with_inverse_probability_weights"}),
    "missing_data_recovery_gformula": frozenset({
        "saturated_strata_recovery_plug_in"}),
    "measurement_error_correction": frozenset({
        "confusion_matrix_inversion_backdoor_standardised"}),
    "exposure_measurement_error_correction": frozenset({
        "exposure_confusion_matrix_inversion_backdoor_standardised"}),
    "combined_measurement_error_correction": frozenset({
        "combined_confusion_matrix_inversion_backdoor_standardised"}),
    "regression_calibration": frozenset({
        "regression_calibration_backdoor_linear"}),
    "differential_regression_calibration": frozenset({
        "differential_regression_calibration_backdoor_linear"}),
    "differential_outcome_correction": frozenset({
        "differential_outcome_shift_backdoor_linear"}),
    "proximal_matrix": frozenset({"nonparametric_matrix_plug_in"}),
    "proximal_miao": frozenset({"nonparametric_matrix_plug_in"}),
    "proximal_null_test": frozenset({"nonparametric_matrix_plug_in"}),
    "proximal_bridge": frozenset({"sieve_two_stage_bridge"}),
    "scm_counterfactual_linear_fit": frozenset({"linear_structural_equations"}),
    "selection_backdoor_recovery": frozenset({
        "selection_backdoor_theorem_3_5_plug_in"}),
    "transport_post_stratification": frozenset({
        "transport_reweighted_strata_plug_in"}),
    "simex": frozenset(
        f"simex_{fitter}_{extrapolant}"
        for fitter in _SIMEX_FITTERS
        for extrapolant in _SIMEX_EXTRAPOLANTS
    ),
}

#: What picks, for a method that can fit more than one shape.
#:
#: A set with two members and no account of which occasion takes which is a
#: declaration that says a method fits either — which is what the answer
#: shapes already said, wrongly, by holding one of the two. The sentence has
#: a reader: it is quoted in the refusal below, so nothing here can drift
#: into being true of no run.
FITS_TURNS_ON: dict[str, str] = {
    "aipw": "the outcome's type — a bool is a probability and takes the "
            "logit link, anything else is a mean and takes the line",
    "tmle": "the outcome's type — a bool is a probability and takes the "
            "logit link, anything else is a mean and takes the line",
    "causation_plugin":
        "which licence the interventional risk it borrowed came under — a "
        "response-function polytope, general ID's c-factor, or the "
        "g-formula",
    "counterfactual_cell_plugin":
        "which licence the interventional risk it borrowed came under — a "
        "response-function polytope, general ID's c-factor, or the "
        "g-formula",
    "simex":
        "its two levers, spelt into one word: the model fitted at each rung "
        "(``outcome_model=``) and the curve extrapolated back to λ = −1 "
        "(``extrapolant=``)",
}


def _check_every_choice_says_what_picks() -> None:
    """Both directions, at import, where the answer is cheap.

    A method fitting two shapes and saying nothing about which occasion
    takes which, and a sentence about a method that has only one shape to
    fit, are the same error from opposite sides — and a table checked in
    one direction is a table where the other side rots.
    """
    silent = sorted(m for m, s in FITS.items()
                    if len(s) > 1 and m not in FITS_TURNS_ON)
    if silent:
        raise RuntimeError(
            f"themis.estimation.form: {silent} can fit more than one shape "
            f"and FITS_TURNS_ON does not say what picks; a set with no "
            f"occasion beside it says the method fits either"
        )
    stale = sorted(m for m in FITS_TURNS_ON if len(FITS.get(m, ())) < 2)
    if stale:
        raise RuntimeError(
            f"themis.estimation.form: FITS_TURNS_ON explains {stale}, which "
            f"fit one shape or none; a sentence about a choice nobody makes "
            f"is true of no run"
        )


def _check_the_words_asked_are_the_shapes_fitted() -> None:
    """A word a caller may write with no method that fits it, and a shape a
    method fits with no word that asks for it, are one hole from two ends.

    Only ``dose_response`` needs saying: the other two word sets are built
    out of the resolved sets above, so they cannot drift from them. That
    family's method names spell the BACKEND (``dose_response_linear_dml``)
    rather than the shape, so its shapes are written twice by necessity —
    and this is the sentence that keeps the two copies one fact.
    """
    fitted: frozenset[str] = frozenset().union(*(
        shapes for method, shapes in FITS.items()
        if method.startswith("dose_response_")
    ))
    asked = MODEL_WORDS_DOSE_RESPONSE - {AUTO}
    if fitted != asked:
        raise RuntimeError(
            f"themis.estimation.form: the dose-response backends fit "
            f"{sorted(fitted)} and a caller may ask for {sorted(asked)}; a "
            f"word nobody fits is an option that cannot be honoured, and a "
            f"shape nobody can ask for is a backend with no door"
        )
    if MODEL_WORD_TWO_STAGE not in MODEL_WORDS_IV:
        raise RuntimeError(
            f"themis.estimation.form: {MODEL_WORD_TWO_STAGE!r} is declared "
            f"as the IV vocabulary's word for the row that runs it, and "
            f"that vocabulary is {sorted(MODEL_WORDS_IV)}; a word spelled "
            f"apart from the set it belongs to is a set with a second author"
        )


_check_every_choice_says_what_picks()
_check_the_words_asked_are_the_shapes_fitted()


def fits(method: str, form: str) -> str:
    """``form``, if ``method`` can fit it. Otherwise a refusal.

    The one door a form takes onto an envelope. A producer names the two
    together — the method it ran and the shape it fitted — and this is the
    only place that pairing is looked at, so a shape reaching a reader is
    one this build can say it fitted.

    A method with no row is refused rather than waved through. The set of
    methods that disclose a mechanism is finite and measured; a lookup
    that answered "no opinion" for an unknown one would be silent exactly
    where a new family arrives with nothing holding it, which is the state
    this function was written to end.
    """
    allowed = FITS.get(method)
    if allowed is None:
        raise ValueError(
            f"{method!r} disclosed a mechanism and declares no shapes it can "
            f"fit; add its row to themis.estimation.form.FITS, where a "
            f"reader's only account of what a number was fitted through is "
            f"held"
        )
    if form not in allowed:
        picks = FITS_TURNS_ON.get(method)
        because = f"; which one it fits turns on {picks}" if picks else ""
        raise ValueError(
            f"{method!r} disclosed the shape {form!r} and fits "
            f"{sorted(allowed)}{because}"
        )
    return form


def shapes_settled(assumptions: Sequence[str],
                   *pairs: tuple[str, Provenance]) -> Mapping[str, str]:
    """Who settled each shape a lever BESIDE the outcome model decided.

    An estimator names the pairs it MIGHT emit, and the declaration list it is
    about to publish decides which of them are real: a shape this run did not
    assume must not arrive with an answer about who assumed it. Reading the
    same tuple that goes on the envelope is also what keeps an origin from
    being filed under an id no reader will ever see.

    Deliberately absent is the outcome model's own shape. That one is the
    estimate's ``form_provenance``, which answers for every id restating it,
    so this map holds the EXCEPTIONS rather than everything: a family with one
    lever has one answer, and repeating it per id would be the same
    one-field-for-N-facts written out longer.
    """
    declared = set(map(str, assumptions))
    return MappingProxyType(
        {name: str(origin) for name, origin in pairs if name in declared})
