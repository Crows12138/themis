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
