"""Which thing a mechanism says its shape was fitted for.

``extensions.mechanism_audit`` discloses, per fit this answer made, the
``form`` the fit took, the ``method`` that ran it, the assumptions it was
settled under, and the ``target`` — the thing that shape was fitted FOR.
Three of those four are held: ``method`` and ``assumptions`` against the
estimate's own account of the run, and each named assumption against its
ledger line. ``target`` was not. On the forty-four answer shapes every
one of thirty-one targets could be rewritten and the public door said
yes.

WHY NOTHING HELD IT, WHICH IS NOT WHAT THE OLD NOTE SAID. Every
mechanism check lives in :mod:`assumption_ledger_rules`, reached through
``verify_assumption_ledger(result)`` — a result-only audit, with no
program beside it. A target names the thing the QUESTION is about, so
the authority that settles it is the question, and in that module the
question does not exist. The nearest stand-in that does exist,
``numeric_estimate.outcome``, is the answer's own record of itself, and
it was tried: the note left behind says it refused seventeen honest
results, and concluded the FIELD was at fault for meaning two things.
Measured again from a room where the question is in scope, the field is
not at fault — twenty-six of thirty-one targets are the question's
outcome exactly, and the stand-in misses six where the question misses
five. A field that cannot be checked and a field checked against the
wrong copy read the same from inside the module that has only the wrong
copy.

WHAT THE REMAINING FIVE ARE, AND WHY THEY ARE TWO KINDS. Four are
renderings rather than references: a measurement-error route models a
SLOPE, and the slot has no way to say "the derivative of ``y`` with
respect to ``w``" except by spelling it, ``dE[y|do(w),Z]/dw``. A looser
rule is what the note above already tried, and a looser rule is not what
these want. A rendering is SPELLED, and what is spelled can be spelled
again: the question names the outcome and the variable intervened on,
the shape word beside the target names the arm the slope is taken
through, and the sentence those three make is the one the route writes.
So the four are read now, by writing the sentence a second time and
comparing — the set below names which routes spell their target, and
naming a route there no longer means nothing reads it.

The fifth was a gap of another kind and is the same move made against a
different sentence. Three questions ask about no single outcome — a
counterfactual cell, a conjunction of counterfactual events, a
probability of necessity — so there is nothing for their targets to be
EQUAL to. Those targets are renderings as well, of worlds rather than of
slopes, and every part of them is in the question: which variable was
intervened on and to what, which value the outcome is asked at, what was
observed, which events are conjoined. So the roster below spells seven
routes now and the rule has no exemption left in it.

What survives is a silence rather than an exemption, and the difference
is the whole of this module's argument. A route with no entry is read
against the outcome the question names; a question that names none
leaves nothing to read, and that is keyed on the ASKED side of the
envelope, which is what makes it a safe thing to be silent about — an
answer cannot edit the question into having no outcome. The day a route
arrives spelling a sentence nobody has written down, it is refused for
spelling one this roster does not have, which is the loud way round.

``form`` — the shape word beside the target — was the fourth, and the
note here said it was "a function of ``method`` across the corpus
(thirty-one methods, one form each)", pointing at a table of shape words
as the thing that would hold it. **The qualifier was carrying the
sentence.** ``tmle`` fits ``logistic`` when the outcome is a bool and
``linear`` when it is not, and both were driven end to end; ``aipw`` is
the same; the two counterfactual plug-ins name the route their borrowed
risk came under. The corpus holds one form for each of them because a
corpus is a sample of what somebody once ran — it names thirty-five
methods where the build produces forty-nine — so a table assembled from
it would have been assembled from the sample.

The table exists now, as :data:`themis.estimation.form.FITS`, and
:data:`FITS` below is this side's own copy of it — re-declared rather
than imported, the way :mod:`themis.risk_provenance` is, because
re-deriving an answer from the vocabulary the producer chose is not an
independent check. A test pins the two equal. What reads it is the
mechanism loop in :mod:`themis.verifier.assumption_ledger_rules`, where
``method`` and the named assumptions are already held: the authority for
a form is the method, which is on the result, so it belongs at that
result-only door rather than at this one.
"""
from __future__ import annotations

from typing import Any, Callable, Mapping

from .errors import VerificationError

_RULE = "mechanism_target_check"

#: Which shapes each method can fit — this side's own copy.
#:
#: Written out flat, and deliberately: the producer builds six of these
#: families by spelling the form into the method name, and a verifier that
#: shared that construction would agree with the producer by running the
#: producer's code. Flat, the two are two statements, and
#: ``test_a_mechanism_says_what_it_was_fitted_for`` pins them equal.
FITS: dict[str, frozenset[str]] = {
    "aipw": frozenset({"linear", "logistic"}),
    "backdoor_linear": frozenset({"linear"}),
    "backdoor_logistic": frozenset({"logistic"}),
    "causation_plugin": frozenset({
        "nonparametric_c_factor_plug_in",
        "nonparametric_gformula_plug_in",
        "nonparametric_response_function_lp"}),
    "cde_linear": frozenset({"linear"}),
    "cde_logit": frozenset({"logit"}),
    "cde_chain_linear": frozenset({"linear"}),
    "cde_chain_logit": frozenset({"logit"}),
    "combined_measurement_error_correction": frozenset({
        "combined_confusion_matrix_inversion_backdoor_standardised"}),
    "counterfactual_cell_plugin": frozenset({
        "nonparametric_c_factor_plug_in",
        "nonparametric_gformula_plug_in",
        "nonparametric_response_function_lp"}),
    "ctf_conjunction_plugin": frozenset({"nonparametric_plug_in"}),
    "differential_outcome_correction": frozenset({
        "differential_outcome_shift_backdoor_linear"}),
    "differential_regression_calibration": frozenset({
        "differential_regression_calibration_backdoor_linear"}),
    "dose_response_causal_forest_dml": frozenset({"forest"}),
    "dose_response_linear_dml": frozenset({"linear"}),
    "dose_response_linear_drlearner": frozenset({"drlearner"}),
    "exposure_measurement_error_correction": frozenset({
        "exposure_confusion_matrix_inversion_backdoor_standardised"}),
    "frontdoor_empirical_linear": frozenset({"linear"}),
    "frontdoor_empirical_logistic": frozenset({"logistic"}),
    "frontdoor_linear": frozenset({"linear"}),
    "frontdoor_logistic": frozenset({"logistic"}),
    "general_id_idc_plugin": frozenset({"nonparametric_plug_in"}),
    "general_id_plugin": frozenset({"nonparametric_plug_in"}),
    "ipw_ht": frozenset({"logistic_propensity"}),
    "ipw_stabilized": frozenset({"logistic_propensity"}),
    "iv_2sls": frozenset({"2sls"}),
    "iv_2sls_overid": frozenset({"two_stage_least_squares"}),
    "iv_acr": frozenset({"acr"}),
    "iv_anderson_rubin_region": frozenset({"linear_in_the_treatment_vector"}),
    "iv_stratified_wald": frozenset({"stratified_wald"}),
    "iv_wald": frozenset({"wald"}),
    "joint_backdoor_linear": frozenset({"linear"}),
    "joint_backdoor_logistic": frozenset({"logistic"}),
    "joint_general_id_plugin": frozenset({"nonparametric_plug_in"}),
    "longitudinal_gformula": frozenset({
        "sequential_regression_g_formula_simulation"}),
    "longitudinal_ipw_msm": frozenset({
        "marginal_structural_model_with_inverse_probability_weights"}),
    "measurement_error_correction": frozenset({
        "confusion_matrix_inversion_backdoor_standardised"}),
    "mediation_joint_linear": frozenset({"linear"}),
    "mediation_joint_logit": frozenset({"logit"}),
    "mediation_linear_imai": frozenset({"linear"}),
    "mediation_logit_imai": frozenset({"logit"}),
    "missing_data_recovery_gformula": frozenset({
        "saturated_strata_recovery_plug_in"}),
    "proximal_bridge": frozenset({"sieve_two_stage_bridge"}),
    "proximal_matrix": frozenset({"nonparametric_matrix_plug_in"}),
    "proximal_miao": frozenset({"nonparametric_matrix_plug_in"}),
    "proximal_null_test": frozenset({"nonparametric_matrix_plug_in"}),
    "regression_calibration": frozenset({
        "regression_calibration_backdoor_linear"}),
    "scm_counterfactual_linear_fit": frozenset({"linear_structural_equations"}),
    "selection_backdoor_recovery": frozenset({
        "selection_backdoor_theorem_3_5_plug_in"}),
    "simex": frozenset({
        "simex_linear_linear", "simex_linear_quadratic",
        "simex_linear_rational", "simex_logistic_linear",
        "simex_logistic_quadratic", "simex_logistic_rational"}),
    "tmle": frozenset({"linear", "logistic"}),
    "transport_post_stratification": frozenset({
        "transport_reweighted_strata_plug_in"}),
}


def shape_the_method_cannot_fit(method: object, form: object,
                                where: str) -> str | None:
    """A complaint if this method cannot fit this shape, else ``None``.

    Returns rather than raises because the caller is one loop over the
    places this answer discloses a shape, and it words its own refusals.

    ``where`` is the place that was read, and it is a parameter because
    there is more than one of them. A mechanism row was the only place
    this was ever asked of and the refusal said so in its own words; a
    correction writing its shape inside the estimate, and writing no
    mechanism row at all, would have been refused in the name of a block
    it does not carry.

    A method with no row is a complaint too. The methods that disclose a
    mechanism are finite and were measured; answering "no opinion" for an
    unknown one would be silent exactly where a family arrives with
    nothing holding it.
    """
    allowed = FITS.get(str(method))
    if allowed is None:
        return (
            f"{where} says the fit was {method!r}, and no method by "
            f"that name declares any shape it can fit; a reader weighing the "
            f"shape has nothing to weigh it against"
        )
    if str(form) not in allowed:
        return (
            f"{where} says {method!r} fitted the shape {form!r} and "
            f"that method fits {sorted(allowed)}; the one word telling a "
            f"reader what the number was fitted through names a shape this "
            f"build cannot fit that way"
        )
    return None


#: The non-linear arm, under both spellings a caller and a family give it.
#:
#: A caller writes ``logistic`` because that is the word the entry's option
#: carries; the mediation family reports the shape it resolved to as
#: ``logit``, in its method name, its estimate and its tests. Those are two
#: names for one arm, and this side needs to know it to read a caller's word
#: against a block's ``form`` — the producer knows it as the ``logistic=``
#: argument named at that family's four call sites.
#:
#: Declared rather than imported, the way :data:`FITS` is, and pinned by
#: driving :func:`themis.estimation.form.outcome_form` both ways in the
#: tests. Two members and not a table: a family that spells the arm a third
#: way is a family this set has never heard of, and it fails here loudly
#: instead of being read as a caller who asked for something else.
_ONE_ARM_TWO_SPELLINGS: frozenset[str] = frozenset({"logistic", "logit"})


def word_that_could_not_have_asked_for(word: object, form: object) -> str | None:
    """A complaint if the caller's ``model=`` cannot have asked for this
    form, else ``None``.

    Asked only of a block that says the caller named its form, which is the
    one case where the two are supposed to be the same decision under
    possibly different spellings. Returns rather than raises for the reason
    :func:`shape_the_method_cannot_fit` does.
    """
    said, shape = str(word), str(form)
    if said == shape:
        return None
    if said in _ONE_ARM_TWO_SPELLINGS and shape in _ONE_ARM_TWO_SPELLINGS:
        return None
    return (
        f"mechanism_audit says the caller's model= settled the shape "
        f"{shape!r} and estimation_context records that caller asking for "
        f"{said!r}; the one field naming what the number was fitted through "
        f"and the one field naming what was asked for are two records of the "
        f"same decision, and a reader shown both is shown a run that did not "
        f"happen"
    )


def outcome_the_question_names(context: Any) -> str | None:
    """The predicate this question asks about, or ``None`` where it asks
    about no single one.

    ``None`` is a fact about the question and not a failure to look: an
    identify query and an effect query both carry one target atom, and a
    counterfactual conjunction carries a sentence instead. The caller is
    silent on ``None`` for that reason and for no other.
    """
    query = getattr(context, "query", None)
    target = getattr(query, "target", None)
    if target is None:
        return None
    atom = getattr(target, "atom", target)
    predicate = getattr(atom, "predicate", None)
    return str(predicate) if isinstance(predicate, str) else None


def treatment_the_question_intervenes_on(context: Any) -> str | None:
    """The variable this question intervenes on, or ``None`` where it
    intervenes on none.

    The other half of what a slope is a slope OF. ``None`` is a fact about
    the question for the same reason its sibling's is: a question that
    intervenes on nothing has no variable to differentiate through, and
    the caller is silent there rather than guessing one.
    """
    query = getattr(context, "query", None)
    intervention = getattr(query, "intervention", None)
    if intervention is None:
        return None
    atom = getattr(intervention, "atom", intervention)
    predicate = getattr(atom, "predicate", None)
    return str(predicate) if isinstance(predicate, str) else None


def _predicate_of(node: object) -> str | None:
    """The variable name inside whatever shape a question hands over.

    A question carries its parts as atoms, as valued atoms and as
    interventions, and every one of them is a name with something wrapped
    around it. Reading the name is one move, so it is written once.
    """
    atom = getattr(node, "atom", node)
    predicate = getattr(atom, "predicate", None)
    return str(predicate) if isinstance(predicate, str) else None


def _an_event_as_spelt(event: object) -> str:
    """One counterfactual event, spelled the way a conjunction spells it.

    ``y_{x=True}=True``: the variable, the world it is read in, the value
    it takes there. The world is the subscript, sorted by variable so that
    two events differing only in the order they were written spell the
    same sentence.

    The parts arrive here as the QUESTION carries them, which is not the
    shape the producer's renderer takes: a question's subscript is valued
    atoms and the estimate's is pairs. Restating a rendering means
    restating what it says, not the shape its author had in hand.
    """
    subscript = getattr(event, "subscript", ()) or ()
    named = sorted(
        ((_predicate_of(one), getattr(one, "value", None))
         for one in subscript),
        key=lambda pair: str(pair[0]))
    inside = ("_{" + ",".join(f"{name}={value}" for name, value in named)
              + "}") if named else ""
    return f"{_predicate_of(getattr(event, 'variable', None))}{inside}=" \
           f"{getattr(event, 'value', None)}"


def _the_necessity_this_question_spells(context: Any,
                                        form: object) -> str | None:
    """``PN(y|x)`` — the probability that this cause was necessary for
    this effect, which a causation question asks as a pair of variables and
    names no single outcome of."""
    query = getattr(context, "query", None)
    cause = _predicate_of(getattr(query, "cause", None))
    effect = _predicate_of(getattr(query, "effect", None))
    if cause is None or effect is None:
        return None
    return f"PN({effect}|{cause})"


def _the_cell_this_question_spells(context: Any,
                                   form: object) -> str | None:
    """``P(y_{x=0}=0|x=1)`` — one cell of the counterfactual joint: the
    value the outcome is asked at in the world where the cause was set,
    given what was observed in this one. Values spelled as the integers a
    two-valued variable takes, which is how the route writes them."""
    query = getattr(context, "query", None)
    intervention = getattr(query, "counterfactual_intervention", None)
    target = getattr(query, "counterfactual_target", None)
    observed = getattr(query, "observed", None)
    if intervention is None or target is None or observed is None:
        return None
    cause = _predicate_of(intervention)
    effect = _predicate_of(target)
    if cause is None or effect is None:
        return None
    return (f"P({effect}_{{{cause}={int(intervention.value)}}}"
            f"={int(target.value)}|{cause}={int(observed.value)})")


def _the_conjunction_this_question_spells(context: Any,
                                          form: object) -> str | None:
    """``P(y_{x=True}=True | x=False)`` — a conjunction of counterfactual
    events, and a condition of them where there is one."""
    query = getattr(context, "query", None)
    events = getattr(query, "events", None)
    condition = getattr(query, "condition", None)
    if not events:
        return None
    said = f" ∧ ".join(_an_event_as_spelt(one) for one in events)
    if condition:
        given = f" ∧ ".join(_an_event_as_spelt(one) for one in condition)
        return f"P({said} | {given})"
    return f"P({said})"


def _the_slope_this_question_spells(context: Any,
                                    form: object) -> str | None:
    """``dE[y|do(w),Z]/dw`` — the derivative a measurement-error route
    models, which the problem has no name for."""
    outcome = outcome_the_question_names(context)
    treatment = treatment_the_question_intervenes_on(context)
    if outcome is None or treatment is None:
        return None
    return _the_slope_as_spelt(
        _the_link_a_slope_is_taken_through(form), outcome, treatment)


def _the_slope_as_spelt(link: str, outcome: str, treatment: str) -> str:
    """How a slope route spells the thing it was fitted for.

    A function rather than a template with holes in it, and the difference
    is what this repository means by a template. A string that gets FILLED
    is a sentence, and a sentence a reader gets belongs to the language
    layer, which is why nothing in this package fills one by hand. This is
    not one: it is a machine rendering that has to come out character for
    character the way the producer writes it, and a translated derivative
    would be the one thing it cannot be.

    Written out here rather than imported from the producer, for the reason
    every table in this package is restated: a verifier that renders with
    the producer's own function agrees with it by construction. Both parts
    come from the QUESTION — the outcome it names and the variable it
    intervenes on — and never from the estimate's own record of them,
    which is the copy this module's opening note was refused seventeen
    honest results for reading.
    """
    return f"d{link}E[{outcome}|do({treatment}),Z]/d{treatment}"


def _the_link_a_slope_is_taken_through(form: object) -> str:
    """The arm a slope is taken through, read off the shape word beside it.

    A form names the route, the arm and, where there is one, the
    extrapolant, so the arm is a WORD of it and not a substring of it. The
    three routes with a single shape each take the line; the sixfold one
    says which arm it fitted. :data:`FITS` is what makes reading it total
    — every shape a method may declare is enumerated there, and a shape
    outside it is refused before this is asked.
    """
    return "logit " if "logistic" in str(form).split("_") else ""


#: The routes whose mechanism target is a rendering rather than a
#: reference. Keyed on ``method`` because that is the field naming the
#: route that a verifier can see, and it is not free to claim: the
#: estimate beside the block records the method too, and the two are
#: already held to each other, so reaching this reading dishonestly
#: costs a second lie about which estimator ran.
#:
#: A route here is a route whose target is read by being spelled again,
#: from the question rather than from the answer's record of it, and the
#: value beside each name is what that route spells. The roster is pinned
#: by name in the tests so that an eighth is a red suite rather than a
#: quiet eighth — a route that spells a sentence nobody wrote down is
#: refused for spelling one this roster does not have.
#:
#: Four spell a SLOPE, which is a thing the problem has no name for. Three
#: spell a world: a cell of the counterfactual joint, a conjunction of
#: counterfactual events, a probability of necessity. They are one kind of
#: thing here for one reason — nothing in the question is called what
#: they say, and everything they say is in the question.
_RENDERS_ITS_TARGET: "Mapping[str, Callable[[Any, object], str | None]]" = {
    "differential_outcome_correction": _the_slope_this_question_spells,
    "differential_regression_calibration": _the_slope_this_question_spells,
    "regression_calibration": _the_slope_this_question_spells,
    "simex": _the_slope_this_question_spells,
    "causation_plugin": _the_necessity_this_question_spells,
    "counterfactual_cell_plugin": _the_cell_this_question_spells,
    "ctf_conjunction_plugin": _the_conjunction_this_question_spells,
}

def verify_mechanism_target(result: Mapping, context: Any) -> None:
    """Hold each disclosed mechanism to the question it was fitted for.

    Returns ``None`` on accept. Raises
    :class:`~themis.verifier.errors.VerificationError` when a mechanism
    says the shape behind a number was fitted for something other than
    what the reader asked about.
    """
    audit = (result.get("extensions") or {}).get("mechanism_audit") or {}
    mechanisms = audit.get("mechanisms") or ()
    outcome = outcome_the_question_names(context)
    treatment = treatment_the_question_intervenes_on(context)
    for i, mechanism in enumerate(mechanisms):
        if not isinstance(mechanism, Mapping):
            continue
        target = mechanism.get("target")
        # Asked of every mechanism before any exemption reaches it. An
        # exemption is a way of not asking, and a blank is the one value
        # that every way of not asking lets through.
        if not isinstance(target, str) or not target.strip():
            raise VerificationError(
                f"mechanism_audit.mechanisms[{i}] discloses the shape a "
                f"number was fitted through and says it was fitted for "
                f"{target!r}; a shape is a shape OF something, and the "
                f"sentence a reader gets has a hole where that goes",
                step_index=None,
                rule=_RULE,
            )
        spells = _RENDERS_ITS_TARGET.get(str(mechanism.get("method")))
        if spells is not None:
            # Spelled, so spelled again. Silent where the question does
            # not carry the parts of its own sentence, which is the same
            # silence the rule below keeps and for the same reason.
            spelt = spells(context, mechanism.get("form"))
            if spelt is None or target == spelt:
                continue
            raise VerificationError(
                f"mechanism_audit says the shape behind this number was "
                f"fitted for {target!r}; this route spells what it was "
                f"fitted for rather than naming it, and what the question "
                f"spells is {spelt!r}; a reader weighing whether the shape "
                f"is a fair one is weighing it against a sentence nobody "
                f"asked",
                step_index=None,
                rule=_RULE,
            )
        if outcome is None or target == outcome:
            continue
        raise VerificationError(
            f"mechanism_audit says the shape behind this number was "
            f"fitted for {target!r} and the question asks about "
            f"{outcome!r}; a reader weighing whether the shape is a fair "
            f"one is weighing it against the wrong variable",
            step_index=None,
            rule=_RULE,
        )
