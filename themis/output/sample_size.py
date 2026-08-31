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
two-arm allocation. The accompanying :class:`Precision` states those
assumptions beside the number so the user can recompute if their
clinical judgment differs.
"""
from __future__ import annotations

import math
from enum import StrEnum, unique

from .. import language


# Standard normal quantiles. Hard-coded to avoid pulling scipy as a
# new dependency for two constants.
#
# Constants rather than parameters, which they were until the sentence
# beside the number became structured. Every function below states α and
# power to the reader, and every one of them took a z instead — so a
# caller passing a different quantile got a number computed one way and a
# sentence saying it was computed the other. Nothing ever passed one, and
# a knob that no caller turns and that would make an adjacent sentence
# false is not a feature. Changing what this module assumes is a change
# to what it SAYS, and both live here.
_Z_ALPHA_2_TWO_SIDED_05 = 1.959964   # P(|Z| > z) = 0.05
_Z_BETA_POWER_80 = 0.841621          # P(Z > z) = 0.20

DEFAULT_COHENS_H = 0.2                # small-to-medium binary effect
DEFAULT_COHENS_D = 0.5                # medium continuous effect (Cohen 1988)
DEFAULT_PROPORTION_PRECISION = 0.03   # ±3 pp around assumed p


@unique
class Precision(language.Word, vocabulary="precision_target",
                between=language.BETWEEN_STATEMENTS):
    """What a sample of the size beside it would buy, and on what.

    A minimum n means nothing on its own: an n that detects Cohen's h=0.2
    is not an n that detects h=0.5, and an n that pins a proportion to
    ±3pp is not an n that detects anything. So the number has always
    travelled with a sentence — and the sentence was written here, in one
    language, by the arithmetic that produced the number.

    The facts it states are this occasion's and travel as this occasion's;
    the statistical names in the text (Cohen's h, α, power) are not
    translated for the reason a citation is not: they are what a reader
    looks up, and a translated α is a symbol nobody can search for.
    """

    DETECT_A_BINARY_EFFECT = "detect_a_binary_effect", {
        "zh": "检出 Cohen's h={h}（二值结局的中小效应），"
              "α=0.05 双侧、power=0.80；两臂等分配",
        "en": "detect Cohen's h={h} (a small-to-medium binary effect) at "
              "α=0.05 two-sided and power 0.80, allocated equally to two "
              "arms",
    }
    DETECT_A_CONTINUOUS_EFFECT = "detect_a_continuous_effect", {
        "zh": "检出 Cohen's d={d}（连续结局的中等效应），"
              "α=0.05 双侧、power=0.80；两臂等分配",
        "en": "detect Cohen's d={d} (a medium continuous effect) at α=0.05 "
              "two-sided and power 0.80, allocated equally to two arms",
    }
    DETECT_BOTH_MEDIATION_PATHS = "detect_both_mediation_paths", {
        "zh": "同时检出 NDE 与 NIE，每条路径上按 Cohen's h={h}"
              "（α=0.05、power=0.80）；这是个经验值 = 简单 ATE 所需 n 的 "
              "{times} 倍，依据 VanderWeele 2015 §4",
        "en": "detect the NDE and the NIE together, at Cohen's h={h} on "
              "each path (α=0.05, power 0.80). A rule of thumb rather than "
              "a power calculation: {times}× the n a simple ATE needs, "
              "after VanderWeele 2015 §4",
    }
    DETECT_THE_EFFECT_IN_EVERY_STRATUM = "detect_the_effect_in_every_stratum", {
        "zh": "每一层里检出 transport 校正后的 ATE（Cohen's h={h}），"
              "共 {strata} 层；α=0.05 双侧、power=0.80",
        "en": "detect the transport-corrected ATE inside each stratum "
              "(Cohen's h={h}) across all {strata} of them, at α=0.05 "
              "two-sided and power 0.80",
    }
    PIN_THE_TARGET_DISTRIBUTION = "pin_the_target_distribution", {
        "zh": "把目标人群的 P*(Z) 估到每层 ±{precision} 以内，共 {strata} 层"
              "（按最坏情况 p={p} 算）",
        "en": "pin the target population's P*(Z) to within ±{precision} in "
              "each of {strata} strata, computed at the worst case p={p}",
    }
    PIN_ONE_PROPORTION = "pin_one_proportion", {
        "zh": "让这个边际概率的 95% 置信区间半宽 ≤{precision}"
              "（按 p={p} 的最坏方差算）",
        "en": "hold this marginal probability's 95% CI to a half-width of "
              "{precision} or less, at the worst-case variance for p={p}",
    }
    TRACE_A_DOSE_RESPONSE_CURVE = "trace_a_dose_response_curve", {
        "zh": "K={points} 个 X 采样点 × n={per_point}/点 "
              "(Cohen's d=0.5, α=0.05, power=0.80)",
        "en": "K={points} sampling points in X × n={per_point} each "
              "(Cohen's d=0.5, α=0.05, power=0.80)",
    }


def estimate_min_n_two_arm_binary(
    *, cohens_h: float = DEFAULT_COHENS_H,
) -> tuple[int, language.Statement]:
    """Total sample size for detecting a binary-outcome treatment effect
    of size ``cohens_h`` (Cohen 1988) under two-arm equal allocation.

    Returns ``(total_n, what that n buys)``. ``total_n`` is rounded UP to
    the nearest 50 — power-analysis precision is not single-person.
    """
    if cohens_h <= 0:
        raise ValueError(f"cohens_h must be positive, got {cohens_h}")
    n_per_arm = math.ceil(
        (_Z_ALPHA_2_TWO_SIDED_05 + _Z_BETA_POWER_80) ** 2 / cohens_h ** 2)
    total = _round_up_50(2 * n_per_arm)
    return total, language.state(
        Precision.DETECT_A_BINARY_EFFECT, h=cohens_h)


def estimate_min_n_two_arm_continuous(
    *, cohens_d: float = DEFAULT_COHENS_D,
) -> tuple[int, language.Statement]:
    """Total sample size for detecting a continuous-outcome treatment
    effect of standardized magnitude ``cohens_d`` (Cohen 1988) under
    two-arm equal allocation, two-sample t-test power formula:

        n_per_arm = 2 · (z_{α/2} + z_β)² / d²

    Defaults: d=0.5 (medium effect), α=0.05 two-sided, power=0.80
    → ~64 per arm → 150 total after round-up-50.

    Pairs with the binary ``estimate_min_n_two_arm_binary`` (Cohen's h)
    so missing-distribution gaps targeting continuous outcomes can also
    surface a min sample size instead of staying ``None``.
    """
    if cohens_d <= 0:
        raise ValueError(f"cohens_d must be positive, got {cohens_d}")
    n_per_arm = math.ceil(
        2 * (_Z_ALPHA_2_TWO_SIDED_05 + _Z_BETA_POWER_80) ** 2 / cohens_d ** 2)
    total = _round_up_50(2 * n_per_arm)
    return total, language.state(
        Precision.DETECT_A_CONTINUOUS_EFFECT, d=cohens_d)


def estimate_min_n_mediation_nde_nie(
    *,
    cohens_h: float = DEFAULT_COHENS_H,
    inflation_factor: float = 2.5,
) -> tuple[int, language.Statement]:
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
    base, _ = estimate_min_n_two_arm_binary(cohens_h=cohens_h)
    total = _round_up_50(int(base * inflation_factor))
    return total, language.state(
        Precision.DETECT_BOTH_MEDIATION_PATHS,
        h=cohens_h, times=inflation_factor)


def estimate_min_n_transport_source_conditional(
    *,
    n_strata: int,
    cohens_h: float = DEFAULT_COHENS_H,
) -> tuple[int, language.Statement]:
    """Source-side stratified P(Y|do(X), Z): need an ATE-detection arm
    inside each stratum, total = n_strata × simple-ATE n.

    ``n_strata`` should be the caller's count of unique combinations of
    the adjustment-set values (e.g. 2^k for k binary covariates). Caller
    is responsible for that arithmetic — this helper only multiplies.
    """
    if n_strata < 1:
        raise ValueError(f"n_strata must be >=1, got {n_strata}")
    base, _ = estimate_min_n_two_arm_binary(cohens_h=cohens_h)
    total = _round_up_50(base * n_strata)
    return total, language.state(
        Precision.DETECT_THE_EFFECT_IN_EVERY_STRATUM,
        h=cohens_h, strata=n_strata)


def estimate_min_n_transport_target_marginal(
    *,
    n_strata: int,
    precision: float = DEFAULT_PROPORTION_PRECISION,
    p_assumed: float = 0.5,
) -> tuple[int, language.Statement]:
    """Target-side P*(Z): single-proportion estimation per stratum,
    total = n_strata × single-proportion n.
    """
    if n_strata < 1:
        raise ValueError(f"n_strata must be >=1, got {n_strata}")
    base, _ = estimate_min_n_single_proportion(
        precision=precision, p_assumed=p_assumed)
    total = _round_up_50(base * n_strata)
    return total, language.state(
        Precision.PIN_THE_TARGET_DISTRIBUTION,
        precision=precision, strata=n_strata, p=p_assumed)


def estimate_min_n_single_proportion(
    *,
    precision: float = DEFAULT_PROPORTION_PRECISION,
    p_assumed: float = 0.5,
) -> tuple[int, language.Statement]:
    """Sample size to estimate a single proportion within ± ``precision``
    at 95% confidence. ``p_assumed`` defaults to 0.5 (worst case).
    """
    if not 0 < p_assumed < 1:
        raise ValueError(f"p_assumed must be in (0, 1), got {p_assumed}")
    if precision <= 0:
        raise ValueError(f"precision must be positive, got {precision}")
    variance = p_assumed * (1 - p_assumed)
    n = math.ceil(
        (_Z_ALPHA_2_TWO_SIDED_05 ** 2) * variance / precision ** 2)
    return _round_up_50(n), language.state(
        Precision.PIN_ONE_PROPORTION, precision=precision, p=p_assumed)


def estimate_n_for_target_ci_half_width(
    *,
    current_n: int,
    current_ci_half_width: float,
    target_ci_half_width: float,
) -> int:
    """Post-hoc precision budgeting: given an estimate produced from
    ``current_n`` samples with 95% CI half-width ``current_ci_half_width``,
    how large would N need to be to shrink the CI to
    ``target_ci_half_width``?

    Standard error scales as 1/√N for IID estimators, so:

        SE_new / SE_old = √(N_old / N_new)
        →  N_new = N_old · (W_old / W_new)²

    The formula is σ-free (σ cancels) and applies to any estimator
    whose CI is symmetric and width is dominated by 1/√N — i.e.
    ATE / IV / mediation point estimates from this codebase.

    Returns ``n_new``, rounded up to the nearest 50 (consistent with the
    a-priori helpers in this module).

    Aligns with VISION 2026-04-26 §"输出 (2)" requirement: "在子群 G
    做 RCT n=N 能把 CI 收缩到 ±δ" — when a current estimate's CI is
    wider than the user wants, this helper tells them how much more
    data is needed.

    It returned a sentence beside the number, and the sentence stated
    the three inputs and the number back. All four are on the envelope
    where the number lands, so the sentence belonged to whoever was
    reading — which the browser had already concluded on its own,
    building its row from the numbers and leaving the string for the
    one Python reader that printed it raw.
    """
    if current_n < 1:
        raise ValueError(f"current_n must be >=1, got {current_n}")
    if current_ci_half_width <= 0:
        raise ValueError(
            f"current_ci_half_width must be positive, got "
            f"{current_ci_half_width}"
        )
    if target_ci_half_width <= 0:
        raise ValueError(
            f"target_ci_half_width must be positive, got "
            f"{target_ci_half_width}"
        )
    ratio = current_ci_half_width / target_ci_half_width
    return _round_up_50(math.ceil(current_n * ratio ** 2))


def _round_up_50(n: int) -> int:
    """Round up to the nearest 50."""
    return ((n + 49) // 50) * 50


# ---------------------------------------------------------------------------
# Which family of formula an ask falls to.
# ---------------------------------------------------------------------------


class Measured(StrEnum):
    """Which quantity a sample would have to pin down.

    Not the variable's measurement scale, and deliberately not spelled in
    the words the envelope shows a reader for one: a five-point rating is
    discrete and still answers a mean formula, so saying "continuous" of
    it would be false about the variable while being right about the
    arithmetic. This says only which family of formula below applies.

    There is no third member for a value that is neither — a categorical
    level is not a family, it is the absence of one, and
    :func:`themis.output.data_gap_report.asked` reports it by leaving this
    unset.
    """

    PROPORTION = "proportion"   # the target value is a truth value
    MEAN = "mean"               # the target value is a number
