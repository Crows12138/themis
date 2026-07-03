"""Four-way decomposition: the unification of mediation and interaction
(VanderWeele 2014; *Explanation in Causal Inference* Ch. 14).

A total effect of a binary exposure A on outcome Y through a mediator M
splits into exactly four non-overlapping pieces, answering "how much of
the effect is due to neither / only interaction / both / only mediation":

    TE = CDE + INTref + INTmed + PIE

- CDE    controlled direct effect (neither mediation nor interaction):
         the effect with M fixed to its reference level 0.
- INTref reference interaction (interaction, NO mediation): the additive
         interaction operating on the mediator already present without
         exposure.
- INTmed mediated interaction (BOTH interaction and mediation): the same
         additive interaction, but operating only because the exposure
         moves the mediator.
- PIE    pure indirect effect (mediation, NO interaction): the classic
         "through M" path absent any interaction.

This module is a pure computation over already-supplied standardized
quantities — the four conditional outcome means and the two mediator
means. Every formula is VanderWeele's empirical decomposition (14.1b);
it is the oracle, nothing here is re-derived.

The bridge relations to the natural-effect decomposition (Ch. 14.7) are
also returned so callers can cross-check against an independently
computed NDE/NIE:

    PNDE (pure natural direct effect) = CDE + INTref
    TNIE (total natural indirect effect) = INTmed + PIE
    TE = PNDE + TNIE

For a linear outcome model these reproduce VanderWeele's regression form
(14.4) exactly: with E[Y|a,m] = θ0+θ1·a+θ2·m+θ3·a·m and E[M|a]=β0+β1·a,
evaluating p_am at m∈{0,1} and q_a at a∈{0,1} gives CDE=θ1,
INTref=θ3·E[M|A=0], INTmed=θ3·β1, PIE=θ2·β1.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import exp


@dataclass(frozen=True)
class FourWayComponents:
    """The four point components of a VanderWeele 2014 decomposition,
    plus the total effect and the two natural-effect bridge aggregates.

    ``additive_interaction`` is the raw additive-interaction contrast
    (p11 − p10 − p01 + p00); INTref and INTmed are this term scaled by
    the mediator's no-exposure prevalence and its exposure-induced
    change respectively. Surfacing it lets a renderer say "there is /
    isn't interaction" independent of how the mediator distributes.
    """

    cde: float
    intref: float
    intmed: float
    pie: float
    te: float
    # Ch. 14.7 bridges to the natural-effect decomposition.
    pnde: float   # CDE + INTref      (pure natural direct effect)
    tnie: float   # INTmed + PIE      (total natural indirect effect)
    additive_interaction: float


def four_way_decomposition(
    *,
    p00: float,   # E[Y | A=0, M=0]  (standardized over covariates)
    p01: float,   # E[Y | A=0, M=1]
    p10: float,   # E[Y | A=1, M=0]
    p11: float,   # E[Y | A=1, M=1]
    q0: float,    # E[M | A=0]  (= P(M=1|A=0) for a binary mediator)
    q1: float,    # E[M | A=1]
) -> FourWayComponents:
    """Compute VanderWeele's four-way decomposition (14.1b).

    ``p_am`` are the (standardized) conditional outcome means and ``q_a``
    the (standardized) mediator means at exposure level a. The exposure
    contrast is the binary 0 → 1; the controlled direct effect fixes the
    mediator at its reference level M=0.
    """
    additive_interaction = p11 - p10 - p01 + p00   # Ch. 9 additive interaction

    cde = p10 - p00                                 # E[CDE]
    intref = additive_interaction * q0              # E[INTref]
    intmed = additive_interaction * (q1 - q0)       # E[INTmed]
    pie = (p01 - p00) * (q1 - q0)                    # E[PIE]
    te = cde + intref + intmed + pie

    return FourWayComponents(
        cde=cde, intref=intref, intmed=intmed, pie=pie, te=te,
        pnde=cde + intref, tnie=intmed + pie,
        additive_interaction=additive_interaction,
    )


# ---------------------------------------------------------------------------
# Ratio (excess-relative-risk) scale — VanderWeele 2014 eAppendix §3.4
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FourWayRatioComponents:
    """The four-way decomposition on the EXCESS RELATIVE RISK scale for a
    binary outcome with a binary mediator (VanderWeele 2014, "A unification
    of mediation and interaction: a four-way decomposition", Epidemiology
    25:749-761; eAppendix §3.4).

    For a binary outcome the natural scale is multiplicative: the total
    effect is a risk ratio and the excess relative risk (RR − 1) is what
    decomposes ADDITIVELY into four pieces. Unlike the difference scale
    (``FourWayComponents``), these components are NOT collapsible from the
    standardized cell means p_am / q_a — they are functions of the logistic
    outcome (Y ~ A + M + A·M + C) and logistic mediator (M ~ A + C) model
    coefficients, reflecting logistic non-collapsibility (the odds-ratio
    approximation VanderWeele uses).

    The four ``*_comp`` are the raw ratio-scale components; ``terr`` is
    their sum. VanderWeele defines each REPORTED excess-relative-risk piece
    as ``comp · (total_rr − 1) / terr`` so the four pieces sum EXACTLY to
    ``total_err`` — a rescaling that is a no-op for the binary/binary case
    (there ``terr ≡ total_rr − 1`` identically) but corrects the
    continuous-mediator case. Proportions use ``terr`` as the denominator.

    Fields:
      err_cde / err_intref / err_intmed / err_pie : the excess-relative-risk
        attributed to (neither) / (interaction only) / (both) / (mediation
        only); sum to ``total_err``.
      total_rr : total-effect risk ratio; total_err = total_rr − 1.
      prop_* : proportion of the total ERR due to each component (sum to 1).
      prop_mediated = (intmed+pie)/terr ; prop_interaction = (intref+intmed)/
        terr ; prop_eliminated = (intref+intmed+pie)/terr — the fraction of
        the effect removed by fixing M to its reference.
    """

    err_cde: float
    err_intref: float
    err_intmed: float
    err_pie: float
    total_err: float
    total_rr: float
    prop_cde: float
    prop_intref: float
    prop_intmed: float
    prop_pie: float
    prop_mediated: float
    prop_interaction: float
    prop_eliminated: float
    # Raw (pre-rescale) components; terr is their sum.
    cde_comp: float
    intref_comp: float
    intmed_comp: float
    pie_comp: float


def four_way_ratio_decomposition(
    *,
    t1: float,   # outcome-model coefficient on A
    t2: float,   # outcome-model coefficient on M
    t3: float,   # outcome-model coefficient on A·M
    b0: float,   # mediator-model intercept
    b1: float,   # mediator-model coefficient on A
    bcc: float = 0.0,   # mediator-model covariate contribution (bc·c)
    a1: float = 1.0,    # exposure level compared (treated)
    a0: float = 0.0,    # exposure reference (control)
    mstar: float = 0.0,  # mediator reference level for the CDE
) -> FourWayRatioComponents:
    """VanderWeele's excess-relative-risk four-way decomposition (eAppendix
    §3.4) for a binary outcome + binary mediator, in closed form from the
    logistic outcome / mediator coefficients.

    ``t1, t2, t3`` are the A, M, A·M coefficients of
    ``logit P(Y=1|A,M,C) = t0 + t1·A + t2·M + t3·A·M + t_C·C`` (the
    intercept t0 and the outcome covariate coefficients cancel on the ratio
    scale, so they are not needed). ``b0, b1`` are the intercept and A
    coefficient of ``logit P(M=1|A,C) = b0 + b1·A + b_C·C`` and ``bcc`` is
    the covariate contribution ``b_C·c`` at the chosen covariate value c
    (default 0; a data estimator supplies the sample-mean value).

    This is the ORACLE — a transcription of VanderWeele's formulas, nothing
    is re-derived. The binary/binary identity ``terr ≡ total_rr − 1`` is a
    strong internal consistency check on the transcription.
    """
    def E(x: float) -> float:
        return exp(x)

    cde_comp = (
        E(t1 * (a1 - a0) + t2 * mstar + t3 * a1 * mstar)
        * (1 + E(b0 + b1 * a0 + bcc))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        - E(t2 * mstar + t3 * a0 * mstar)
        * (1 + E(b0 + b1 * a0 + bcc))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
    )
    intref_comp = (
        E(t1 * (a1 - a0))
        * (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a1))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        - 1.0
        - E(t1 * (a1 - a0) + t2 * mstar + t3 * a1 * mstar)
        * (1 + E(b0 + b1 * a0 + bcc))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        + E(t2 * mstar + t3 * a0 * mstar)
        * (1 + E(b0 + b1 * a0 + bcc))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
    )
    intmed_comp = (
        E(t1 * (a1 - a0))
        * (1 + E(b0 + b1 * a1 + bcc + t2 + t3 * a1))
        * (1 + E(b0 + b1 * a0 + bcc))
        / (
            (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
            * (1 + E(b0 + b1 * a1 + bcc))
        )
        - (1 + E(b0 + b1 * a1 + bcc + t2 + t3 * a0))
        * (1 + E(b0 + b1 * a0 + bcc))
        / (
            (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
            * (1 + E(b0 + b1 * a1 + bcc))
        )
        - E(t1 * (a1 - a0))
        * (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a1))
        / (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        + 1.0
    )
    pie_comp = (
        (1 + E(b0 + b1 * a0 + bcc))
        * (1 + E(b0 + b1 * a1 + bcc + t2 + t3 * a0))
        / (
            (1 + E(b0 + b1 * a1 + bcc))
            * (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        )
        - 1.0
    )

    terr = cde_comp + intref_comp + intmed_comp + pie_comp
    total_rr = (
        E(t1 * a1)
        * (1 + E(b0 + b1 * a0 + bcc))
        * (1 + E(b0 + b1 * a1 + bcc + t2 + t3 * a1))
        / (
            E(t1 * a0)
            * (1 + E(b0 + b1 * a1 + bcc))
            * (1 + E(b0 + b1 * a0 + bcc + t2 + t3 * a0))
        )
    )
    total_err = total_rr - 1.0

    # Rescale so the four ERR pieces sum EXACTLY to total_err. For binary/
    # binary terr == total_err identically, so this factor is 1; keeping it
    # matches VanderWeele's definition verbatim and stays robust to drift.
    scale = (total_err / terr) if terr != 0 else float("nan")

    def _prop(c: float) -> float:
        return (c / terr) if terr != 0 else float("nan")

    return FourWayRatioComponents(
        err_cde=cde_comp * scale,
        err_intref=intref_comp * scale,
        err_intmed=intmed_comp * scale,
        err_pie=pie_comp * scale,
        total_err=total_err,
        total_rr=total_rr,
        prop_cde=_prop(cde_comp),
        prop_intref=_prop(intref_comp),
        prop_intmed=_prop(intmed_comp),
        prop_pie=_prop(pie_comp),
        prop_mediated=_prop(intmed_comp + pie_comp),
        prop_interaction=_prop(intref_comp + intmed_comp),
        prop_eliminated=_prop(intref_comp + intmed_comp + pie_comp),
        cde_comp=cde_comp,
        intref_comp=intref_comp,
        intmed_comp=intmed_comp,
        pie_comp=pie_comp,
    )
