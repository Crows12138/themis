"""Phase 8.2 — sensitivity analysis for numeric causal estimates.

Implements the E-value (VanderWeele & Ding 2017): a single closed-form
number summarising how strong an unmeasured confounder would need to
be — on the risk-ratio scale, simultaneously with treatment AND
outcome — to fully explain away an observed estimate.

E-value interpretation:

- E = 1 means even a tiny unmeasured confounder could explain the
  estimate — finding is fragile.
- E ≥ 2 means the confounder would need to roughly double both the
  treatment and outcome odds — a substantial bar.
- E → ∞ means the estimate is robust to unmeasured confounding.

The formula assumes the estimate is on the risk-ratio scale.
For ATE on a binary outcome (logistic backdoor / front-door /
mediation logit paths), we convert via the observed baseline rate.
For continuous outcomes the E-value is undefined here — we report
``None`` and surface a note in the result.

Reference: VanderWeele TJ, Ding P. "Sensitivity analysis in
observational research: introducing the E-value." Annals of Internal
Medicine. 2017;167(4):268-274.

API:

    from themis.estimation.sensitivity import e_value_for_risk_ratio
    e = e_value_for_risk_ratio(rr=2.5)  # → 4.44
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class EValueResult:
    """Sensitivity-analysis output for a numeric estimate.

    - ``e_value``: VanderWeele 2017 E-value on the point estimate.
    - ``e_value_ci_bound``: the same E-value applied to whichever CI
      bound is closer to the null (RR=1) — used for "robustness of the
      lower bound" claims.
    - ``risk_ratio``: the risk ratio used to compute the E-value (point
      estimate's RR; provided for transparency).
    - ``baseline_rate``: the empirical control-arm outcome rate used
      to convert ATE into RR. ``None`` for non-bool outcomes.
    - ``note``: human-readable summary of how the conversion was done
      and what the E-value implies.
    """

    e_value: float | None
    e_value_ci_bound: float | None
    risk_ratio: float | None
    baseline_rate: float | None
    note: str


def e_value_for_risk_ratio(rr: float) -> float:
    """E-value for a single risk ratio (VanderWeele & Ding 2017 formula).

    Symmetric around RR=1: ``e_value(rr) == e_value(1/rr)``. By
    convention the input is normalised to ``rr >= 1`` first.

    For RR == 1, returns 1 (no observed effect → the trivial
    confounder of strength 1 already "explains" the null).
    """
    if rr <= 0:
        raise ValueError(f"risk ratio must be positive; got {rr}")
    if rr < 1:
        rr = 1.0 / rr
    if rr == 1.0:
        return 1.0
    return rr + math.sqrt(rr * (rr - 1.0))


def e_value_from_ate_binary(
    ate: float,
    *,
    baseline_rate: float,
    ci_bound: float | None = None,
) -> EValueResult:
    """Convert an ATE on a binary outcome to a risk ratio + E-value.

    ``baseline_rate`` is P(Y=1 | X=0) on the observed sample (the
    untreated arm's outcome mean). ``ate`` is E[Y|do(X=1)] - E[Y|do(X=0)],
    so E[Y|do(X=1)] = baseline_rate + ate.

    ``ci_bound`` (optional) is the CI bound closer to the null — pass
    in ``ci_lower`` if the point estimate is positive, ``ci_upper`` if
    negative. We compute the E-value on that bound separately so users
    can claim "even the closer-to-null end of my CI implies a
    confounder of strength X to explain it away".

    Returns an EValueResult; sets fields to ``None`` and writes an
    explanatory note when the conversion is not meaningful (e.g.
    baseline 0 or 1, treated rate outside [0,1]).
    """
    if not 0 < baseline_rate < 1:
        return EValueResult(
            e_value=None,
            e_value_ci_bound=None,
            risk_ratio=None,
            baseline_rate=baseline_rate,
            note=(
                f"baseline outcome rate {baseline_rate:.3f} is at the "
                "boundary [0,1]; cannot form a risk ratio. "
                "E-value undefined for this estimate."
            ),
        )

    treated_rate = baseline_rate + ate
    if not 0 < treated_rate < 1:
        return EValueResult(
            e_value=None,
            e_value_ci_bound=None,
            risk_ratio=None,
            baseline_rate=baseline_rate,
            note=(
                f"implied treated rate {treated_rate:.3f} is outside "
                "[0,1] — the linear ATE assumption breaks down here. "
                "E-value on the risk-ratio scale is not meaningful; "
                "consider re-estimating with a logistic outcome model."
            ),
        )

    rr = treated_rate / baseline_rate
    e_point = e_value_for_risk_ratio(rr)

    e_ci = None
    if ci_bound is not None:
        ci_treated = baseline_rate + ci_bound
        if 0 < ci_treated < 1:
            rr_ci = ci_treated / baseline_rate
            e_ci = e_value_for_risk_ratio(rr_ci)

    note = _format_note(e_point, e_ci, rr, baseline_rate)
    return EValueResult(
        e_value=e_point,
        e_value_ci_bound=e_ci,
        risk_ratio=rr,
        baseline_rate=baseline_rate,
        note=note,
    )


def _format_note(
    e_point: float, e_ci: float | None, rr: float, baseline_rate: float,
) -> str:
    parts = [
        f"observed RR {rr:.3f} (baseline rate {baseline_rate:.3f})",
        f"E-value on point estimate = {e_point:.2f}",
    ]
    if e_ci is not None:
        parts.append(f"E-value on CI bound nearer the null = {e_ci:.2f}")
    if e_point < 1.5:
        parts.append("interpretation: very weak — small unmeasured confounding could explain the result")
    elif e_point < 2.5:
        parts.append("interpretation: moderate — a modestly strong confounder could explain the result")
    elif e_point < 5.0:
        parts.append("interpretation: substantial — confounder would need to be sizable to explain away")
    else:
        parts.append("interpretation: very robust — implausibly strong confounder would be needed")
    return "; ".join(parts)
