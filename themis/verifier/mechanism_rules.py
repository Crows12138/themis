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
respect to ``w``" except by spelling it, ``dE[y|do(w),Z]/dw``. Those are
named below and the reason they are not caught by a looser rule is that
a looser rule is what the note above already tried. The fifth is not a
gap at all: a counterfactual conjunction asks about no single outcome,
so there is nothing for a target to be equal to. That silence is keyed
on the ASKED side of the envelope, which is what makes it safe to be
silent about — an answer cannot edit the question into having no
outcome.

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

from typing import Any, Mapping

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


def shape_the_method_cannot_fit(method: object, form: object) -> str | None:
    """A complaint if this method cannot fit this shape, else ``None``.

    Returns rather than raises because the caller is one loop over a block
    whose other two fields it already checks, and it words its own
    refusals.

    A method with no row is a complaint too. The methods that disclose a
    mechanism are finite and were measured; answering "no opinion" for an
    unknown one would be silent exactly where a family arrives with
    nothing holding it.
    """
    allowed = FITS.get(str(method))
    if allowed is None:
        return (
            f"mechanism_audit says the fit was {method!r}, and no method by "
            f"that name declares any shape it can fit; a reader weighing the "
            f"shape has nothing to weigh it against"
        )
    if str(form) not in allowed:
        return (
            f"mechanism_audit says {method!r} fitted the shape {form!r} and "
            f"that method fits {sorted(allowed)}; the one word telling a "
            f"reader what the number was fitted through names a shape this "
            f"build cannot fit that way"
        )
    return None

#: The routes whose mechanism target is a rendering rather than a
#: reference. Keyed on ``method`` because that is the field naming the
#: route that a verifier can see, and it is not free to claim: the
#: estimate beside the block records the method too, and the two are
#: already held to each other, so reaching this exemption dishonestly
#: costs a second lie about which estimator ran.
#:
#: A route added here is a route whose target no rule reads. The list is
#: pinned by name in the tests so that arriving at five is a red suite
#: rather than a quiet fifth.
_RENDERS_ITS_TARGET: frozenset[str] = frozenset({
    "differential_outcome_correction",
    "differential_regression_calibration",
    "regression_calibration",
    "simex",
})


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
        if outcome is None or target == outcome:
            continue
        if mechanism.get("method") in _RENDERS_ITS_TARGET:
            continue
        raise VerificationError(
            f"mechanism_audit says the shape behind this number was "
            f"fitted for {target!r} and the question asks about "
            f"{outcome!r}; a reader weighing whether the shape is a fair "
            f"one is weighing it against the wrong variable",
            step_index=None,
            rule=_RULE,
        )
