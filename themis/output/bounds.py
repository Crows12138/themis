"""Phase 12 — symbolic bounds attempts when point identification fails.

Pure-function attempts that take a query (+ optional kernel context) and
return a ``BoundsResult`` if the method applies, ``None`` otherwise.

Charter §3 priority — implemented in this module:
- ``attempt_manski_natural`` (S.12.2): no assumptions; works on any
  effect query whose target is a discrete event. The intervened
  treatment may be binary OR multi-valued — the natural bound is on a
  single arm ``P(Y=y | do(X=x))`` and its width is the pooled off-arm
  mass ``P(X≠x)``, so it is cardinality-agnostic in the treatment.
- ``attempt_balke_pearl_iv`` (S.12.3, separate function): sharp bounds
  from the response-function model of a valid IV (IV1/IV2/IV3), at any
  finite cardinality of X, Y and Z.
- ``attempt_manski_tamer_monotonicity`` (Phase 12.MT): tightens one
  side of the Manski natural interval when
  the user asserts monotone treatment response (Manski 1997 MTR;
  binary treatment). Triggered via ``program.extensions['monotonicity']``
  declaration — no kernel surface change.

Out of scope this phase: frontdoor partial; Manski-Tamer for a
multi-valued treatment (its monotone envelope over ordered levels is a
binary-treatment construction).
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

    It is likewise independent of the TREATMENT's cardinality: the bound
    is on the single arm ``do(X=x)``, and the unconstrained sub-population
    is everyone with ``X≠x`` — whether that is one other arm (binary X) or
    several (multi-valued X). For a binary treatment the complement is
    rendered as the single concrete other arm ``P(X=¬x)``; for a
    multi-valued treatment there is no single other arm to name, so the
    honest width is the pooled inequality ``P(X≠x)``.

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
    other_arm_mass = _complement_mass(
        intervention_pred, query.intervention.value,
    )

    obs_term = (
        f"P({target_pred}={target_val} | "
        f"{intervention_pred}={intervention_val})"
        f" · P({intervention_pred}={intervention_val})"
    )

    lower = obs_term
    upper = f"{obs_term} + {other_arm_mass}"

    return BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression=lower,
        upper_expression=upper,
        estimand="arm_probability",
        assumptions=(),
        data_required=(
            f"P({target_pred}, {intervention_pred})  # 联合观测",
        ),
        width_when_uninformative=False,  # symbolic phase — width depends on data
        notes=(
            "Manski (1990) 自然界，不加任何假设。"
            f"区间宽度 = {other_arm_mass} —— "
            "另一臂的人越少，界越紧；这个处理水平一个人都没有时，"
            "界退化成没有信息的 [0,1]。"
        ),
    )


# --------------------------------------------------------------------------
# The response-function model of an IV structure, and how big it is
# --------------------------------------------------------------------------
# Balke-Pearl's construction is one sentence, not one table: under IV
# exclusion + independence, a unit's behaviour is fully described by which
# treatment it would take at each instrument level (a map ``z → x``) and
# which outcome it would show at each treatment level (a map ``x → y``).
# The canonical partition is therefore every such pair of maps, and its SIZE
# — ``|X|^|Z| · |Y|^|X|`` — is a consequence of the cardinalities, not a
# constant. Binary everywhere gives the familiar 16.
#
# Writing that 16 down as a literal is what forced every consumer to ask "is
# it binary?" instead of "how big is it?", which is why an instrument with
# three levels used to be discarded whole.
#
# Prior art (read, not vendored — the LP here is written from the model):
# Balke & Pearl 1997 JASA for the binary case; Cheng & Small 2006 and
# Richardson & Robins 2014 for multi-valued instruments; the causaloptim R
# package (Sachs, Jonzon, Gabriel & Sjölander) computes symbolic bounds for
# this generalised class by vertex enumeration rather than a per-dataset LP.


# The LP is re-solved once per bootstrap replicate, so the model's size is
# multiplied by the replication the caller asked for. Measured on this
# machine: 4096 types ≈ 0.03 s per solve, 78125 types ≈ 0.54 s — the second
# is ~4 minutes at the default 500 replicates. A cap keeps the method from
# being promised where it cannot be delivered; above it the query falls to
# the assumption-free Manski floor, and the refusal says which cardinalities
# produced the number so the reader can see the cost of their own model.
MAX_RESPONSE_TYPES = 10_000


def response_type_count(
    *, treatment_levels: int, outcome_levels: int, instrument_levels: int,
) -> int | None:
    """Size of the canonical response-function partition, or ``None`` once it
    is known to exceed :data:`MAX_RESPONSE_TYPES`.

    Multiplied out step by step with an early exit rather than evaluated as
    ``|X|^|Z| · |Y|^|X|``: a column of floats presents thousands of distinct
    levels, and one such number raised to another is an integer Python
    declines even to render as a decimal string. The count has to be exact
    only while it is small enough to matter, and past the cap the only fact
    the caller needs is that it is past the cap.
    """
    total = 1
    for _ in range(instrument_levels):
        total *= treatment_levels
        if total > MAX_RESPONSE_TYPES:
            return None
    for _ in range(treatment_levels):
        total *= outcome_levels
        if total > MAX_RESPONSE_TYPES:
            return None
    return total


def attempt_balke_pearl_iv(
    query: EffectQuery,
    *,
    instrument_predicate: str | None,
    outcome_levels: int | None,
    treatment_levels: int | None,
    instrument_levels: int | None,
) -> BoundsResult | None:
    """Sharp bounds on the arm ``P(Y=y | do(X=x))`` the query names, from
    the response-function model of an instrument satisfying IV1/IV2/IV3.

    The identified set is ``{ the arm's value under every distribution over
    response types that reproduces the observed P(Y, X | Z) }`` — a linear
    program, and the definition of sharpness rather than an approximation of
    it. Tighter than Manski natural whenever a valid instrument exists,
    because the instrument constrains which type distributions are possible.

    **The estimand is the arm the query asked about**, at every cardinality.
    Balke-Pearl's textbook statement bounds the ACE instead, but the ACE is
    ``P(Y=1|do(X=1)) − P(Y=1|do(X=0))``: it needs a binary outcome to be a
    probability difference and a binary treatment to have a baseline arm, so
    it does not survive the generalisation. An ``EffectQuery`` names one
    intervention level and one target level, and that arm is a linear
    functional of the same type distribution — so it is what this bounds.
    The numeric end additionally reports the ACE as a named contrast where
    it is defined; see ``estimation/bounds_numeric.py``.

    Returns ``None`` when no instrument was provided, when any of the three
    cardinalities is unknown (an undeclared continuous variable has no
    response-function partition) or below two, when the model exceeds
    ``MAX_RESPONSE_TYPES``, or when the query is conditional.
    """
    if instrument_predicate is None:
        return None
    if query.given:
        return None
    if not all(isinstance(n, int) and n >= 2
               for n in (outcome_levels, treatment_levels, instrument_levels)):
        return None
    assert (outcome_levels is not None and treatment_levels is not None
            and instrument_levels is not None)  # narrowed by the check above
    n_types = response_type_count(
        treatment_levels=treatment_levels,
        outcome_levels=outcome_levels,
        instrument_levels=instrument_levels,
    )
    if n_types is None:
        return None

    target_pred = query.target.atom.predicate
    target_val = _fmt_value(query.target.value)
    treatment_pred = query.intervention.atom.predicate
    treatment_val = _fmt_value(query.intervention.value)
    z = instrument_predicate
    arm = f"P({target_pred}={target_val} | do({treatment_pred}={treatment_val}))"
    observables = f"P({target_pred}, {treatment_pred} | {z})"

    # The expression is a reference to the program, not its solution: the
    # bound is the optimum of an LP, and there is no closed form to print at
    # a general cardinality (the "max/min of 8 linear combinations" that can
    # be printed is the binary case's analytic solution).
    lower = (
        f"min of {arm} over the response-function polytope fitted to "
        f"{observables} (Balke-Pearl LP, {n_types} response types)"
    )
    upper = (
        f"max of {arm} over the response-function polytope fitted to "
        f"{observables} (same polytope, same observables as lower)"
    )

    return BoundsResult(
        method=BoundsMethod.BALKE_PEARL_IV,
        estimand="arm_probability",
        lower_expression=lower,
        upper_expression=upper,
        assumptions=(
            "iv1_relevance",
            "iv2_exclusion_instrument_affects_outcome_only_via_treatment",
            "iv3_independence_instrument_independent_of_unmeasured_confounders",
        ),
        data_required=(
            f"{observables}"
            f"  # 共 {instrument_levels * treatment_levels * outcome_levels} "
            f"个概率",
        ),
        width_when_uninformative=False,
        notes=(
            f"Balke-Pearl 锐界，作用在 {arm} 上，来自工具 {z} 的响应函数模型"
            f"（处理 {treatment_levels} 个水平 × 结局 {outcome_levels} 个水平 × "
            f"工具 {instrument_levels} 个水平 = {n_types} 种响应型）。"
            f"只要 {z} 确实是有效工具，这个界就比 Manski 自然界紧；"
            f"用到的只有可观测的 {observables}。"
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
    # MTR is binary-treatment only (guarded above), so the complement is
    # the single concrete other arm ``¬x``.
    other_arm_val = _fmt_value(not query.intervention.value)

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
        estimand="arm_probability",
        assumptions=(f"mtr_{monotonicity.value}",),
        data_required=(
            f"P({target_pred}, {intervention_pred})  # 联合观测",
        ),
        width_when_uninformative=False,
        notes=(
            f"Manski-Tamer（Manski 1997）单调处理响应界，假设为 "
            f"{direction_str}。相对 Manski 自然界，{tightened_side} 这一侧"
            f"收紧到观测边际 {target_marginal}，另一侧不变。"
            "结果严格含在 Manski 自然界区间里。"
        ),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _complement_mass(pred: str, value: object) -> str:
    """Symbolic mass of the sub-population NOT at the intervened level —
    ``P(X≠x)``, the width of the Manski natural interval.

    For a BINARY treatment the complement is the single concrete other arm,
    rendered ``P(X=¬x)`` (names the one alternative, matching the historical
    binary output). For a MULTI-VALUED treatment there is no single other
    arm to name; the honest form is the pooled inequality ``P(X≠x)`` over
    all other levels (= ``1 − P(X=x)``)."""
    if isinstance(value, bool):
        return f"P({pred}={_fmt_value(not value)})"
    return f"P({pred}≠{_fmt_value(value)})"


def _fmt_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)
