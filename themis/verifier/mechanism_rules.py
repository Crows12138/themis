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

WHAT THIS DOES NOT REACH. ``form`` — the shape word beside the target —
is a function of ``method`` across the corpus (thirty-one methods, one
form each), and of the twenty-seven forms nothing holds, four have a
second record on the envelope and two of those four are
``estimation_context.model_preference``, which is what a caller ASKED
for and need not be what ran. So the thing that would hold ``form`` is a
table of shape words this repository would then own, which is a
different root cause from this one and belongs to its own frontier.
"""
from __future__ import annotations

from typing import Any, Mapping

from .errors import VerificationError

_RULE = "mechanism_target_check"

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
