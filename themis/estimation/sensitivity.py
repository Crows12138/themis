"""Phase 8.2 — sensitivity analysis for numeric causal estimates.

Implements the E-value (VanderWeele & Ding 2017): a single closed-form
number summarising how strong an unmeasured confounder would need to
be — on the risk-ratio scale, simultaneously with treatment AND
outcome — to fully explain away an observed estimate.

One estimate yields TWO E-values and they answer different questions.
The one on the point estimate asks how strong a confounder would have to
be to move the estimate to the null. The one on the confidence bound
nearer the null asks how strong a one would have to be to take the
FINDING away. "Is this robust" means the second, so :func:`band_for`
reads the verdict off the bound whenever there is one — and reports
which of the two it used, because the rule that picks is the thing this
module had wrong.

The formula assumes the estimate is on the risk-ratio scale.

Two conversion paths to RR:

- **Binary outcome** (``e_value_from_ate_binary``): convert ATE via
  observed baseline rate. RR = (baseline + ATE) / baseline.
- **Continuous outcome** (``e_value_from_ate_continuous``):
  convert ATE to standardised mean difference d = ATE / SD(Y), then
  approximate RR ≈ exp(0.91 · d) per Chinn (2000) — the standard
  conversion used in VanderWeele 2017 §3.3 for continuous outcomes.
  Approximation assumes within-group SDs are similar and the outcome
  is approximately log-normal; the ``note`` field in
  ``EValueResult`` explains the assumption explicitly.

References:
- VanderWeele TJ, Ding P. "Sensitivity analysis in observational
  research: introducing the E-value." Annals of Internal Medicine.
  2017;167(4):268-274.
- Chinn S. "A simple method for converting an odds ratio to effect
  size for use in meta-analysis." Statistics in Medicine.
  2000;19(22):3127-3131. (Provides the SMD ↔ log-OR conversion
  d ≈ log(OR) / 1.81, equivalently OR ≈ exp(1.81 · d). For
  rare-outcome / risk-ratio approximation: log(RR) ≈ 0.91 · d. The
  factor 0.91 ≈ √3 / π is the same scaling used to map a logistic
  effect size to a normal-scale SMD.)

API:

    from themis.estimation.sensitivity import (
        e_value_for_risk_ratio,
        e_value_from_ate_binary,
        e_value_from_ate_continuous,
    )
    e = e_value_for_risk_ratio(rr=2.5)  # → 4.44
    er = e_value_from_ate_continuous(ate=0.5, outcome_sd=2.0)
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from .. import language as _lang


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
    - ``interpretation_band``: the reader's verdict — one of
      :data:`BANDS`, or ``None`` when no E-value came out.
    - ``band_basis``: which number that verdict was read off, one of
      :data:`BAND_BASES`. Stated rather than left to be inferred: a
      reader who has to know the rule in order to know what they are
      being told cannot notice the rule being wrong.
    - ``note``: how the conversion was done. The verdict is NOT in
      here. A band said twice is a band that can disagree with itself,
      and prose is the copy nothing can re-derive.
    """

    e_value: float | None
    e_value_ci_bound: float | None
    risk_ratio: float | None
    baseline_rate: float | None
    interpretation_band: str | None
    band_basis: str | None
    note: str


#: The cut-points a verdict is read off, as (below this, band). Open at the
#: top: at or above the last cut is :data:`_LAST_BAND`.
#:
#: The numbers are this repository's, not VanderWeele & Ding's. The paper
#: states the quantity and leaves the reading to the reader, and a reading
#: with no cut-points is not one software can perform — so they are named
#: once here rather than spelled into a branch chain beside each caller,
#: which is how the two formatters came to disagree about the wording of
#: the same four bands. What the paper does fix is which NUMBER the reading
#: is about, and that is :func:`band_for`.
_BANDS: tuple[tuple[float, str], ...] = (
    (1.5, "fragile"), (2.5, "moderate"), (5.0, "substantial"),
)
_LAST_BAND = "very_robust"

#: Every band, in the order the cut-points put them. Derived rather than
#: written out, so a fourth band cannot exist for the reader and not for the
#: schema — the envelope's enum is held equal to this.
BANDS: tuple[str, ...] = tuple(name for _cut, name in _BANDS) + (_LAST_BAND,)

#: Which of the two E-values a verdict was read off. Two members, and
#: anchored anyway: the pair is the distinction the defect erased.
BAND_BASES: tuple[str, ...] = ("ci_bound", "point")


def band_for(e_point: float, e_ci: float | None) -> tuple[str, str]:
    """Which band this estimate lands in, and which number put it there.

    The CI bound governs whenever there is one. The two E-values are not a
    quantity and a more cautious version of it: the point's asks what would
    move the ESTIMATE to the null, the bound's asks what would take the
    FINDING away, and "is this robust" is the second question. Keyed to the
    point, an estimate whose interval already reaches the null reads as
    very robust — the reading exactly inverted, and loudest precisely where
    the evidence is weakest.

    The point is the fallback and not a second rule: when no interval was
    computed, or when it straddles the null so far that no bound lies on
    the estimate's side, the point is the only number there is.
    """
    basis = "point" if e_ci is None else "ci_bound"
    value = e_point if e_ci is None else e_ci
    for cut, name in _BANDS:
        if value < cut:
            return name, basis
    return _LAST_BAND, basis


#: What this module has to say to a reader, in each language it is written
#: in. The verdict is not among them — it left as a field.
_SAID: dict[str, _lang.Words] = {
    "baseline_on_boundary": {
        "zh": "基线结局发生率 {rate} 正落在 [0,1] 的边界上，构不成风险比；"
              "这个估计的 E 值无定义",
        "en": "the baseline outcome rate {rate} sits on the boundary of "
              "[0,1], and that is not a risk ratio; this estimate has no "
              "E-value",
    },
    "treated_rate_out_of_range": {
        "zh": "推出来的处理组发生率 {rate} 落在 [0,1] 之外——线性 ATE 假设"
              "在这里已经不成立；风险比尺度上的 E 值没有意义，建议改用 "
              "logistic 结局模型重估",
        "en": "the implied treated rate {rate} falls outside [0,1] — the "
              "linear-ATE assumption has already failed here; an E-value on "
              "the risk-ratio scale means nothing, and a logistic outcome "
              "model is what would give one",
    },
    "ate_not_finite": {
        "zh": "ATE={ate} 不是有限数；E 值无定义，连续结局这条路线需要一个"
              "有限的点估计",
        "en": "ATE={ate} is not a finite number; there is no E-value, and "
              "this route needs a finite point estimate",
    },
    "outcome_sd_not_usable": {
        "zh": "结局标准差 {sd} 非正或非有限；Chinn 2000 的 SMD→RR 换算需要"
              "一个有意义的结局尺度，E 值无定义",
        "en": "the outcome standard deviation {sd} is not positive and "
              "finite; the Chinn 2000 SMD→RR conversion needs a meaningful "
              "outcome scale, so there is no E-value",
    },
    "binary_conversion": {
        "zh": "观测到的 RR {rr}（基线发生率 {baseline}）",
        "en": "the observed RR is {rr} (baseline rate {baseline})",
    },
    "continuous_conversion": {
        "zh": "连续结局（SD={sd}）：标准化均值差 SMD d = {d}；"
              "RR ≈ exp(0.91·d) = {rr}（Chinn 2000 换算）",
        "en": "continuous outcome (SD={sd}): SMD d = {d}; "
              "RR ≈ exp(0.91·d) = {rr} (Chinn 2000 conversion)",
    },
    "point_evalue": {
        "zh": "点估计上的 E 值 = {e}",
        "en": "E-value on the point estimate = {e}",
    },
    "ci_bound_evalue": {
        "zh": "靠近零假设那一侧置信区间端点的 E 值 = {e}",
        "en": "E-value on the confidence bound nearer the null = {e}",
    },
    "chinn_caveat": {
        "zh": "近似说明：Chinn 的 0.91 因子假设组内标准差大致相等、结局大致"
              "服从对数正态。这是流行病学文献里的现成经验法则，不是一个紧的界",
        "en": "on the approximation: Chinn's 0.91 factor assumes roughly "
              "equal within-group SDs and a roughly log-normal outcome. It "
              "is the epidemiological literature's rule of thumb, not a "
              "tight bound",
    },
}


def _note(*parts: str, lang: _lang.Lang | str = _lang.DEFAULT) -> str:
    """Several loosely joined statements, in this language's punctuation."""
    return _lang.fill(_lang.BETWEEN_STATEMENTS, lang).join(parts)


def _undefined(baseline_rate: float | None, note: str) -> EValueResult:
    """No E-value came out, and the note says which of the four reasons.

    One constructor for the four, because "there is no number" is one fact.
    Four literals is four places to forget a field, and the band and its
    basis are exactly the two a fifth reason would have forgotten.
    """
    return EValueResult(
        e_value=None, e_value_ci_bound=None, risk_ratio=None,
        baseline_rate=baseline_rate, interpretation_band=None,
        band_basis=None, note=note)


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
        return _undefined(baseline_rate, _lang.fill(
            _SAID["baseline_on_boundary"], _lang.DEFAULT,
            rate=f"{baseline_rate:.3f}"))

    treated_rate = baseline_rate + ate
    if not 0 < treated_rate < 1:
        return _undefined(baseline_rate, _lang.fill(
            _SAID["treated_rate_out_of_range"], _lang.DEFAULT,
            rate=f"{treated_rate:.3f}"))

    rr = treated_rate / baseline_rate
    e_point = e_value_for_risk_ratio(rr)

    e_ci = None
    if ci_bound is not None:
        ci_treated = baseline_rate + ci_bound
        if 0 < ci_treated < 1:
            rr_ci = ci_treated / baseline_rate
            e_ci = e_value_for_risk_ratio(rr_ci)

    band, basis = band_for(e_point, e_ci)
    return EValueResult(
        e_value=e_point,
        e_value_ci_bound=e_ci,
        risk_ratio=rr,
        baseline_rate=baseline_rate,
        interpretation_band=band,
        band_basis=basis,
        note=_format_note(e_point, e_ci, rr, baseline_rate),
    )


CHINN_SMD_TO_LOG_RR = 0.91


def e_value_from_ate_continuous(
    ate: float,
    *,
    outcome_sd: float,
    ci_bound: float | None = None,
) -> EValueResult:
    """E-value for an ATE on a continuous outcome via the
    Chinn (2000) standardised-mean-difference → risk-ratio conversion.

    Steps:
    1. Standardise the effect: d = ATE / SD(Y).
    2. Approximate risk-ratio scale: RR ≈ exp(0.91 · d).
       The factor 0.91 maps a normal-scale SMD to a log-RR under the
       standard logistic-to-normal scaling (≈ √3 / π).
    3. Apply VanderWeele-Ding's E-value formula on RR.

    Returns ``EValueResult`` whose ``baseline_rate`` field is None
    (no baseline rate is meaningful here — the conversion is fully
    standardisation-based) and whose ``note`` makes the approximation
    explicit so renderers can disclose the assumption.

    Skips with all-None when:
    - outcome_sd is non-positive (cannot standardise — typically a
      degenerate outcome with zero variance)
    - ATE is non-finite

    The CI bound (if supplied) is the bound closer to the null;
    ``e_value_ci_bound`` is computed on it the same way.
    """
    import math as _math

    if not _math.isfinite(ate):
        return _undefined(None, _lang.fill(
            _SAID["ate_not_finite"], _lang.DEFAULT, ate=ate))
    if outcome_sd <= 0 or not _math.isfinite(outcome_sd):
        return _undefined(None, _lang.fill(
            _SAID["outcome_sd_not_usable"], _lang.DEFAULT, sd=outcome_sd))

    smd = ate / outcome_sd
    rr = _math.exp(CHINN_SMD_TO_LOG_RR * smd)
    e_point = e_value_for_risk_ratio(rr)

    e_ci = None
    if ci_bound is not None and _math.isfinite(ci_bound):
        smd_ci = ci_bound / outcome_sd
        rr_ci = _math.exp(CHINN_SMD_TO_LOG_RR * smd_ci)
        e_ci = e_value_for_risk_ratio(rr_ci)

    band, basis = band_for(e_point, e_ci)
    return EValueResult(
        e_value=e_point,
        e_value_ci_bound=e_ci,
        risk_ratio=rr,
        baseline_rate=None,
        interpretation_band=band,
        band_basis=basis,
        note=_format_continuous_note(
            e_point, e_ci, rr=rr, smd=smd, outcome_sd=outcome_sd),
    )


def _evalues_said(e_point: float, e_ci: float | None,
                  lang: _lang.Lang | str) -> list[str]:
    """Both E-values, each named for the question it answers.

    Written once for the two routes. The conversion above them differs and
    the two numbers below them do not, which is the half of these notes
    that was genuinely shared — and it was the half both copies stated
    differently, one route naming the point's in English and the other in
    Chinese.
    """
    said = [_lang.fill(_SAID["point_evalue"], lang, e=f"{e_point:.2f}")]
    if e_ci is not None:
        said.append(_lang.fill(_SAID["ci_bound_evalue"], lang,
                               e=f"{e_ci:.2f}"))
    return said


def _format_continuous_note(
    e_point: float,
    e_ci: float | None,
    *,
    rr: float,
    smd: float,
    outcome_sd: float,
    lang: _lang.Lang | str = _lang.DEFAULT,
) -> str:
    return _note(
        _lang.fill(_SAID["continuous_conversion"], lang,
                   sd=f"{outcome_sd:.3g}", d=f"{smd:+.3f}", rr=f"{rr:.3f}"),
        *_evalues_said(e_point, e_ci, lang),
        _lang.fill(_SAID["chinn_caveat"], lang),
        lang=lang,
    )


def _format_note(
    e_point: float, e_ci: float | None, rr: float, baseline_rate: float,
    lang: _lang.Lang | str = _lang.DEFAULT,
) -> str:
    return _note(
        _lang.fill(_SAID["binary_conversion"], lang, rr=f"{rr:.3f}",
                   baseline=f"{baseline_rate:.3f}"),
        *_evalues_said(e_point, e_ci, lang),
        lang=lang,
    )
