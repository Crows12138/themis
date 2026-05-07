"""Phase 12 — symbolic bounds attempts when point identification fails.

Pure-function attempts that take a query (+ optional kernel context) and
return a ``BoundsResult`` if the method applies, ``None`` otherwise.

Charter §3 priority — implemented in this module:
- ``attempt_manski_natural`` (S.12.2): no assumptions; works on any
  binary-outcome effect query.
- ``attempt_balke_pearl_iv`` (S.12.3, separate function): requires a
  binary IV with valid IV1/IV2/IV3.
- ``attempt_manski_tamer_monotonicity`` (Phase 12.MT, post-saturation
  iter 119): tightens one side of the Manski natural interval when
  the user asserts monotone treatment response (Manski 1997 MTR;
  binary outcome). Triggered via ``program.extensions['monotonicity']``
  declaration — no kernel surface change.

Out of scope this phase: frontdoor partial, non-binary outcomes
(charter §6).
"""
from __future__ import annotations

from ..types import BoundsMethod, BoundsResult, EffectQuery, Monotonicity


def attempt_manski_natural(
    query: EffectQuery,
    *,
    outcome_event_is_discrete: bool,
) -> BoundsResult | None:
    """Manski (1990) natural bounds on ``P(Y_event | do(X=x))`` where
    ``Y_event`` is the concrete event ``target.atom = target.value``.

    Derivation: under SUTVA + consistency, the observed conditional
    ``P(Y=y | X=x)`` only constrains the potential outcome on the X=x
    sub-population. The other sub-population is unconstrained, so its
    contribution is bounded by [0, 1]:

        P(Y=y | do(X=x)) ∈
            [ P(Y=y | X=x) · P(X=x),
              P(Y=y | X=x) · P(X=x) + P(X≠x) ]

    The formula is independent of Y's dtype — it works for bool targets
    (engagement=true) AND discrete-numeric targets (engagement=4 on a
    Likert 1-5 scale, BP=140 on a fixed grid) — as long as
    ``P(Y=value)`` is a non-degenerate probability.

    Caller passes ``outcome_event_is_discrete=True`` when the target
    predicate is bool OR has a declared discrete numeric domain;
    ``False`` for unbounded continuous outcomes where ``P(Y=specific)``
    is point mass on a continuous distribution (degenerate).
    """
    if not outcome_event_is_discrete:
        return None
    if query.given:
        # Conditional effect queries (effect | given) are out of scope:
        # the Manski derivation is per the marginal P(X), and a
        # conditional restriction changes the bounds. Future extension.
        return None

    target_pred = query.target.atom.predicate
    target_val = _fmt_value(query.target.value)
    intervention_pred = query.intervention.atom.predicate
    intervention_val = _fmt_value(query.intervention.value)
    other_arm_val = _fmt_value(_negate(query.intervention.value))

    obs_term = (
        f"P({target_pred}={target_val} | "
        f"{intervention_pred}={intervention_val})"
        f" · P({intervention_pred}={intervention_val})"
    )
    other_arm_mass = f"P({intervention_pred}={other_arm_val})"

    lower = obs_term
    upper = f"{obs_term} + {other_arm_mass}"

    return BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression=lower,
        upper_expression=upper,
        assumptions=(),
        data_required=(
            f"P({target_pred}, {intervention_pred})  # joint observation",
        ),
        width_when_uninformative=False,  # symbolic phase — width depends on data
        notes=(
            "Manski (1990) natural bounds. No assumptions. "
            f"Width = P({intervention_pred}={other_arm_val}) — "
            "tight when the untreated arm is small, trivial [0,1] when "
            "no one was treated."
        ),
    )


def attempt_balke_pearl_iv(
    query: EffectQuery,
    *,
    instrument_predicate: str | None,
    outcome_is_binary: bool,
    treatment_is_binary: bool,
    instrument_is_binary: bool,
) -> BoundsResult | None:
    """Balke-Pearl (1997) bounds on the **average causal effect (ACE)**
    when X, Y, and the instrument Z are all binary and Z satisfies
    IV1 / IV2 / IV3.

    ACE = E[Y | do(X=1)] - E[Y | do(X=0)]

    The bounds are tighter than Manski natural whenever a valid IV
    exists. They use only observable joint probabilities
    ``P(Y, X | Z)`` (8 numbers for binary triples).

    The lower / upper bound formulas each take the maximum / minimum of
    8 linear combinations of those 8 probabilities (Pearl 1995 §3,
    Balke-Pearl 1997). We emit a compact symbolic reference plus the
    pointer to the canonical paper rather than spelling all 16 terms in
    one expression — the LLM consumer / future numeric layer can
    expand from the citation.

    Note: BP bounds ACE (the difference of two interventions), not the
    single quantity ``P(Y | do(X=x))`` that Themis's EffectQuery
    typically asks for. The renderer surfaces this distinction so
    the user understands what's bounded.

    Returns ``None`` if any of X / Y / Z is non-binary, no instrument
    was provided, or the query is conditional (``given`` non-empty).
    """
    if not (outcome_is_binary and treatment_is_binary and instrument_is_binary):
        return None
    if instrument_predicate is None:
        return None
    if query.given:
        return None

    target_pred = query.target.atom.predicate
    treatment_pred = query.intervention.atom.predicate
    z = instrument_predicate

    # Compact symbolic form referencing the canonical paper. The LLM /
    # numeric estimator expands by citation; rendering layer translates.
    lower = (
        f"max over 8 Balke-Pearl lower terms "
        f"(linear combos of P({target_pred}, {treatment_pred} | {z}); "
        f"see Balke-Pearl 1997 §3)"
    )
    upper = (
        f"min over 8 Balke-Pearl upper terms "
        f"(linear combos of P({target_pred}, {treatment_pred} | {z}); "
        f"same observables as lower)"
    )

    return BoundsResult(
        method=BoundsMethod.BALKE_PEARL_IV,
        lower_expression=lower,
        upper_expression=upper,
        assumptions=(
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ),
        data_required=(
            f"P({target_pred}, {treatment_pred} | {z}) "
            f"  # 8 probabilities for binary triple",
        ),
        width_when_uninformative=False,
        notes=(
            f"Balke-Pearl (1997) bounds on ACE = "
            f"E[{target_pred} | do({treatment_pred}=1)] - "
            f"E[{target_pred} | do({treatment_pred}=0)]. "
            f"Tighter than Manski natural when IV {z} is valid. "
            f"Uses only observable P({target_pred}, {treatment_pred} | {z})."
        ),
    )


def attempt_manski_tamer_monotonicity(
    query: EffectQuery,
    *,
    monotonicity: Monotonicity,
    outcome_event_is_discrete: bool,
) -> BoundsResult | None:
    """Manski (1997) bounds under monotone treatment response (MTR).

    Tightens **one side** of the Manski natural interval when the user
    asserts that the potential outcome is monotone in treatment. For
    binary X, binary outcome event ``Y=y``, monotonicity direction
    ``non_decreasing`` means ``Y(1) ≥ Y(0)`` (treatment cannot decrease
    the outcome event); ``non_increasing`` means ``Y(1) ≤ Y(0)``.

    Derivation for ``non_decreasing`` and target event ``Y=y`` with
    intervention ``X=x``:

    - Among the ``X=x`` stratum, ``Y(x) = Y`` is observed; contribution
      to ``E[Y(x)]`` is exactly ``P(Y=y, X=x)``.
    - Among the ``X=¬x`` stratum, ``Y(x)`` is unobserved but constrained
      by MTR relative to the observed ``Y(¬x) = Y``.
      * For x=1 with MTR ``Y(1) ≥ Y(0)``: when ``Y(0)=1`` we observe in
        the X=0 stratum, ``Y(1)`` must be 1 — so the lower bound for
        ``E[Y(1)]`` from the unseen stratum gains the observed
        ``P(Y=1, X=0)`` contribution that Manski natural couldn't
        claim. Lower of ``P(Y=1 | do(X=1))`` becomes ``P(Y=1)``
        (the observed outcome marginal). Upper is unchanged from
        Manski natural.
      * For x=0 with MTR ``Y(1) ≥ Y(0)`` (so ``Y(0) ≤ Y(1)``):
        symmetric — upper of ``P(Y=1 | do(X=0))`` tightens to
        ``P(Y=1)``; lower unchanged.

    For ``non_increasing`` the roles flip. In all cases the interval
    is **strictly contained** in Manski natural's, sometimes
    collapsing to a point only when the data already pins it.

    Returns ``None`` if outcome is not a discrete event, intervention
    is not boolean, or the query is conditional. Conditional queries
    (``given`` non-empty) are out of scope this slice — same posture
    as Manski natural.
    """
    if not outcome_event_is_discrete:
        return None
    if query.given:
        return None
    if not isinstance(query.intervention.value, bool):
        return None

    target_pred = query.target.atom.predicate
    target_val = _fmt_value(query.target.value)
    intervention_pred = query.intervention.atom.predicate
    intervention_val = _fmt_value(query.intervention.value)
    other_arm_val = _fmt_value(_negate(query.intervention.value))

    # Same-arm contribution: P(Y=y | X=x) · P(X=x) — observed exactly.
    same_arm = (
        f"P({target_pred}={target_val} | "
        f"{intervention_pred}={intervention_val})"
        f" · P({intervention_pred}={intervention_val})"
    )
    other_arm_mass = f"P({intervention_pred}={other_arm_val})"
    other_arm_observed = (
        f"P({target_pred}={target_val} | "
        f"{intervention_pred}={other_arm_val})"
        f" · {other_arm_mass}"
    )
    target_marginal = f"P({target_pred}={target_val})"

    # Determine which side tightens. The rule:
    # MTR Y(1) >= Y(0):
    #   x=1: lower tightens to marginal,  upper = Manski natural upper
    #   x=0: lower = Manski natural,       upper tightens to marginal
    # MTR Y(1) <= Y(0):
    #   x=1: lower = Manski natural,       upper tightens to marginal
    #   x=0: lower tightens to marginal,  upper = Manski natural upper
    treating_high = bool(query.intervention.value)
    direction_increases_y = monotonicity is Monotonicity.NON_DECREASING

    # tighten_lower is True when MTR makes the lower bound informative
    # at the *observed marginal* of the target event.
    tighten_lower = treating_high == direction_increases_y

    manski_lower = same_arm
    manski_upper = f"{same_arm} + {other_arm_mass}"

    if tighten_lower:
        lower = target_marginal
        upper = manski_upper
        tightened_side = "lower"
    else:
        lower = manski_lower
        upper = target_marginal
        tightened_side = "upper"

    direction_str = (
        "non-decreasing (Y(1) ≥ Y(0))"
        if direction_increases_y
        else "non-increasing (Y(1) ≤ Y(0))"
    )

    return BoundsResult(
        method=BoundsMethod.MANSKI_TAMER_MONOTONICITY,
        lower_expression=lower,
        upper_expression=upper,
        assumptions=(f"mtr_{monotonicity.value}",),
        data_required=(
            f"P({target_pred}, {intervention_pred})  # joint observation",
        ),
        width_when_uninformative=False,
        notes=(
            f"Manski-Tamer (Manski 1997) MTR bounds with assumption "
            f"{direction_str}. The {tightened_side} bound tightens to "
            f"the observed marginal {target_marginal} relative to "
            "Manski natural; the other side is unchanged. Strictly "
            "contained in the Manski natural interval."
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _negate(v) -> object:
    """Negate a bool. Non-bool values fall through unchanged with a
    placeholder — Manski for non-binary domain is out of scope so this
    only fires on accidental misuse."""
    if isinstance(v, bool):
        return not v
    return f"NOT_{v}"


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
