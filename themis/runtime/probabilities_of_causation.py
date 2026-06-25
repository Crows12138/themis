"""Probabilities of causation: PN, PS, PNS (Tian & Pearl 2000).

The three binary probabilities of causation answer the counterfactual-attribution
questions Themis previously could not:

- PN  (probability of necessity)   = P(Y_{x'}=0 | X=1, Y=1)
      "given X and Y both happened, would Y have NOT happened without X?"
- PS  (probability of sufficiency)  = P(Y_{x}=1 | X=0, Y=0)
      "given neither happened, WOULD Y have happened had X?"
- PNS (necessity AND sufficiency)   = P(Y_{x}=1, Y_{x'}=0)

This module is a pure computation over already-supplied quantities (the
observational joint of binary X, Y and the interventional risks P(Y=1|do(X))).
Every formula is Tian & Pearl (2000), "Probabilities of Causation: Bounds and
Identification" (Annals of Math & AI 28:287-313) — cited per equation. It is the
oracle; nothing here is re-derived.

- Bounds with NO assumptions, from both observational + interventional data:
  eqs (24)-(26).
- Point identification under MONOTONICITY (Y never prevented by X): eqs (40)-(42)
  (Theorem 3). Under additional EXOGENEITY these reduce to eqs (44)-(46), i.e.
  P(y_x)=P(y|x) (Theorem 4); the caller supplies the interventional risks, so the
  exogenous case is just the special case P(y|do(x)) = P(y|x).
"""
from __future__ import annotations

from dataclasses import dataclass


def _clamp(v: float) -> float:
    return 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


@dataclass(frozen=True)
class CausationProbabilities:
    """PN/PS/PNS Tian-Pearl bounds; point values present only under monotonicity.

    ``*_point`` is ``None`` when the quantity is not point-identified (no
    monotonicity assumed) or its conditioning event has zero probability.
    """

    pns_lower: float
    pns_upper: float
    pn_lower: float
    pn_upper: float
    ps_lower: float
    ps_upper: float
    pns_point: float | None
    pn_point: float | None
    ps_point: float | None
    monotonic: bool


def probabilities_of_causation(
    *,
    p_x1_y1: float,   # P(X=1, Y=1)
    p_x1_y0: float,   # P(X=1, Y=0)
    p_x0_y1: float,   # P(X=0, Y=1)
    p_x0_y0: float,   # P(X=0, Y=0)
    p_y_do_x1: float,  # P(Y=1 | do(X=1))   = P(y_x)
    p_y_do_x0: float,  # P(Y=1 | do(X=0))   = P(y_{x'})
    monotonic: bool = False,
) -> CausationProbabilities:
    """Compute PN/PS/PNS bounds (and points under monotonicity) for binary X, Y.

    The four observational cells must form a distribution (sum ≈ 1). The two
    interventional risks are P(Y=1 | do(X=x)); supply P(y|x) for the exogenous
    (no-confounding) case. ``monotonic=True`` asserts Y is monotonic in X
    (X never prevents Y), which point-identifies all three (Tian-Pearl Thm 3).
    """
    pyx = p_y_do_x1          # P(y_x)
    pyx_ = p_y_do_x0         # P(y_{x'})
    py_prime_x_ = 1.0 - pyx_  # P(y'_{x'})
    py = p_x1_y1 + p_x0_y1   # P(Y=1)
    pxy = p_x1_y1            # P(x, y)
    px_y_ = p_x0_y0          # P(x', y')

    # --- PNS bounds, Tian-Pearl (24) ---
    pns_lower = _clamp(max(0.0, pyx - pyx_, py - pyx_, pyx - py))
    pns_upper = _clamp(min(
        pyx, py_prime_x_, p_x1_y1 + p_x0_y0,
        pyx - pyx_ + p_x1_y0 + p_x0_y1,
    ))

    # --- PN bounds, Tian-Pearl (25) --- (require P(x,y) > 0)
    if pxy > 0.0:
        pn_lower = _clamp(max(0.0, (py - pyx_) / pxy))
        pn_upper = _clamp(min(1.0, (py_prime_x_ - px_y_) / pxy))
    else:
        # Conditioning event {X=1, Y=1} has zero mass — PN is undefined; report
        # the trivial [0, 1] (no information) rather than divide by zero.
        pn_lower, pn_upper = 0.0, 1.0

    # --- PS bounds, Tian-Pearl (26) --- (require P(x',y') > 0)
    if px_y_ > 0.0:
        ps_lower = _clamp(max(0.0, (pyx - py) / px_y_))
        ps_upper = _clamp(min(1.0, (pyx - pxy) / px_y_))
    else:
        ps_lower, ps_upper = 0.0, 1.0

    # --- Point identification under monotonicity, Tian-Pearl (40)-(42) ---
    pns_point = pn_point = ps_point = None
    if monotonic:
        pns_point = _clamp(pyx - pyx_)                                  # (40)
        pn_point = _clamp((py - pyx_) / pxy) if pxy > 0.0 else None     # (41)
        ps_point = _clamp((pyx - py) / px_y_) if px_y_ > 0.0 else None  # (42)

    return CausationProbabilities(
        pns_lower=pns_lower, pns_upper=pns_upper,
        pn_lower=pn_lower, pn_upper=pn_upper,
        ps_lower=ps_lower, ps_upper=ps_upper,
        pns_point=pns_point, pn_point=pn_point, ps_point=ps_point,
        monotonic=monotonic,
    )
