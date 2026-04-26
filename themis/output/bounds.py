"""Phase 12 — symbolic bounds attempts when point identification fails.

Pure-function attempts that take a query (+ optional kernel context) and
return a ``BoundsResult`` if the method applies, ``None`` otherwise.

Charter §3 priority — implemented in this module:
- ``attempt_manski_natural`` (S.12.2): no assumptions; works on any
  binary-outcome effect query.
- ``attempt_balke_pearl_iv`` (S.12.3, separate function): requires a
  binary IV with valid IV1/IV2/IV3.

Out of scope this phase: frontdoor partial, Manski-Tamer monotonicity,
non-binary outcomes (charter §6).
"""
from __future__ import annotations

from ..types import BoundsMethod, BoundsResult, EffectQuery


def attempt_manski_natural(
    query: EffectQuery,
    *,
    outcome_is_binary: bool,
) -> BoundsResult | None:
    """Manski (1990) natural bounds on ``P(target | do(intervention))``
    for a binary outcome.

    Derivation: under SUTVA + consistency, the observed conditional
    ``P(Y=y | X=x)`` only constrains the potential outcome on the X=x
    sub-population. The other sub-population is unconstrained, so its
    contribution is bounded by [0, 1]:

        P(Y=y | do(X=x)) ∈
            [ P(Y=y | X=x) · P(X=x),
              P(Y=y | X=x) · P(X=x) + P(X≠x) ]

    No assumptions required. Bounds collapse to a point iff
    ``P(X=x)=1`` (no untreated arm); become trivially [0, 1] iff
    ``P(X=x)=0``. Width is exactly ``P(X≠x)`` — readable proxy for
    "how much of the population we have no info on under this
    intervention".

    Returns ``None`` for non-binary outcomes — Manski natural bounds for
    bounded continuous outcomes use ``[Y_min, Y_max]`` instead of
    ``[0, 1]``; that variant is out of scope this phase.
    """
    if not outcome_is_binary:
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
