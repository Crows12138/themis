"""Phase 10 follow-up: minimum sample size estimation for
``GapRequiredData.min_sample_size``.

Scope: deliberately narrow. We only fill ``min_sample_size`` when the
gap is a missing **binary-outcome distribution** under simple
backdoor-style ATE estimation. For all other cases (continuous
outcomes, mediation, IV, transport, missing assumptions) the field
stays ``None`` — power analysis there needs information the gap
report does not carry (effect-size scale, residual variance,
mediator distribution, IV strength).

The numbers we emit are honest defaults, not bespoke power
calculations: round-numbers derived from Cohen's h = 0.2 (small-to-
medium binary effect), α = 0.05 two-sided, power = 0.80, equal
two-arm allocation. The accompanying ``precision_target`` string
documents these assumptions so the user can recompute if their
clinical judgment differs.
"""
from __future__ import annotations

import math


# Standard normal quantiles. Hard-coded to avoid pulling scipy as a
# new dependency for two constants.
_Z_ALPHA_2_TWO_SIDED_05 = 1.959964   # P(|Z| > z) = 0.05
_Z_BETA_POWER_80 = 0.841621          # P(Z > z) = 0.20

DEFAULT_COHENS_H = 0.2                # small-to-medium binary effect
DEFAULT_PROPORTION_PRECISION = 0.03   # ±3 pp around assumed p


def estimate_min_n_two_arm_binary(
    *,
    cohens_h: float = DEFAULT_COHENS_H,
    z_alpha_2: float = _Z_ALPHA_2_TWO_SIDED_05,
    z_beta: float = _Z_BETA_POWER_80,
) -> tuple[int, str]:
    """Total sample size for detecting a binary-outcome treatment effect
    of size ``cohens_h`` (Cohen 1988) under two-arm equal allocation.

    Returns ``(total_n, precision_target_string)``. ``total_n`` is
    rounded UP to the nearest 50 — power-analysis precision is not
    single-person.
    """
    if cohens_h <= 0:
        raise ValueError(f"cohens_h must be positive, got {cohens_h}")
    n_per_arm = math.ceil((z_alpha_2 + z_beta) ** 2 / cohens_h ** 2)
    total = _round_up_50(2 * n_per_arm)
    note = (
        f"detect Cohen's h={cohens_h} (small-to-medium binary effect) "
        f"at α=0.05 two-sided, power=0.80; two-arm equal allocation"
    )
    return total, note


def estimate_min_n_mediation_nde_nie(
    *,
    cohens_h: float = DEFAULT_COHENS_H,
    inflation_factor: float = 2.5,
    z_alpha_2: float = _Z_ALPHA_2_TWO_SIDED_05,
    z_beta: float = _Z_BETA_POWER_80,
) -> tuple[int, str]:
    """Total sample size to detect NDE + NIE jointly under Cohen's h on
    each path, two-arm equal allocation.

    Heuristic — not a bespoke power calc: ~``inflation_factor`` × the
    simple-ATE detection n (default 2.5×, VanderWeele 2015 §4 — direct
    + indirect path power requires inflated n vs total effect alone).
    """
    if inflation_factor <= 0:
        raise ValueError(
            f"inflation_factor must be positive, got {inflation_factor}"
        )
    base, _ = estimate_min_n_two_arm_binary(
        cohens_h=cohens_h, z_alpha_2=z_alpha_2, z_beta=z_beta,
    )
    total = _round_up_50(int(base * inflation_factor))
    note = (
        f"detect NDE + NIE jointly at Cohen's h={cohens_h} on each path "
        f"(α=0.05, power=0.80); heuristic = {inflation_factor}× simple "
        f"ATE n per VanderWeele 2015 §4"
    )
    return total, note


def estimate_min_n_transport_source_conditional(
    *,
    n_strata: int,
    cohens_h: float = DEFAULT_COHENS_H,
    z_alpha_2: float = _Z_ALPHA_2_TWO_SIDED_05,
    z_beta: float = _Z_BETA_POWER_80,
) -> tuple[int, str]:
    """Source-side stratified P(Y|do(X), Z): need an ATE-detection arm
    inside each stratum, total = n_strata × simple-ATE n.

    ``n_strata`` should be the caller's count of unique combinations of
    the adjustment-set values (e.g. 2^k for k binary covariates). Caller
    is responsible for that arithmetic — this helper only multiplies.
    """
    if n_strata < 1:
        raise ValueError(f"n_strata must be >=1, got {n_strata}")
    base, _ = estimate_min_n_two_arm_binary(
        cohens_h=cohens_h, z_alpha_2=z_alpha_2, z_beta=z_beta,
    )
    total = _round_up_50(base * n_strata)
    note = (
        f"detect transport-adjusted ATE (Cohen's h={cohens_h}) per "
        f"stratum × {n_strata} strata; α=0.05 two-sided, power=0.80"
    )
    return total, note


def estimate_min_n_transport_target_marginal(
    *,
    n_strata: int,
    precision: float = DEFAULT_PROPORTION_PRECISION,
    p_assumed: float = 0.5,
    z_alpha_2: float = _Z_ALPHA_2_TWO_SIDED_05,
) -> tuple[int, str]:
    """Target-side P*(Z): single-proportion estimation per stratum,
    total = n_strata × single-proportion n.
    """
    if n_strata < 1:
        raise ValueError(f"n_strata must be >=1, got {n_strata}")
    base, _ = estimate_min_n_single_proportion(
        precision=precision, p_assumed=p_assumed, z_alpha_2=z_alpha_2,
    )
    total = _round_up_50(base * n_strata)
    note = (
        f"estimate target-population P*(Z) within ±{precision} per "
        f"stratum × {n_strata} strata (assumed worst-case p={p_assumed})"
    )
    return total, note


def estimate_min_n_single_proportion(
    *,
    precision: float = DEFAULT_PROPORTION_PRECISION,
    p_assumed: float = 0.5,
    z_alpha_2: float = _Z_ALPHA_2_TWO_SIDED_05,
) -> tuple[int, str]:
    """Sample size to estimate a single proportion within ± ``precision``
    at 95% confidence. ``p_assumed`` defaults to 0.5 (worst case).
    """
    if not 0 < p_assumed < 1:
        raise ValueError(f"p_assumed must be in (0, 1), got {p_assumed}")
    if precision <= 0:
        raise ValueError(f"precision must be positive, got {precision}")
    variance = p_assumed * (1 - p_assumed)
    n = math.ceil((z_alpha_2 ** 2) * variance / precision ** 2)
    note = (
        f"95% CI half-width ≤{precision} for the marginal probability "
        f"(assumed p={p_assumed}, worst-case variance)"
    )
    return _round_up_50(n), note


def _round_up_50(n: int) -> int:
    """Round up to the nearest 50."""
    return ((n + 49) // 50) * 50


# ---------------------------------------------------------------------------
# Heuristic: is the gap's distribution a binary-outcome ask?
#
# We sniff the rendered description string `P(y=true|x=true)` style.
# Bool values (=true / =false / =True / =False) signal binary outcome.
# Unknown / continuous → return False so the caller leaves min_sample_size
# unset.
# ---------------------------------------------------------------------------


_BOOL_VALUE_TOKENS = ("=true", "=false", "=True", "=False")


def is_binary_outcome_distribution(rendered: str) -> bool:
    """Heuristic — true iff the rendered ``P(...)`` string contains a
    bool value token on the target side. False on continuous or
    unknown."""
    # Target is everything before the first '|' (or the whole string for
    # marginal). Strip the leading 'P(' if present to avoid false matches
    # in conditioning-set tokens.
    inner = rendered.strip()
    if inner.startswith("P("):
        inner = inner[2:]
    target_part = inner.split("|", 1)[0]
    return any(tok in target_part for tok in _BOOL_VALUE_TOKENS)
