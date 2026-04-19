"""Composite confidence scoring.

★ v0.1 PLACEHOLDER — formal semantics deferred to v0.2 ★

Confidence in this project is a composite reliability score, NOT a
statistical confidence interval and NOT a Bayesian posterior.

The v0.1 combination rule is the **minimum** of non-None inputs:

    composite(c1, c2, ..., cn) = min(c for c in inputs if c is not None)

Rationale for the placeholder:

- Order-independent (no dependence on argument permutation).
- Monotone: adding a weaker input can only weaken the composite.
- Conservative: the composite is never stronger than the weakest link.
- Trivially computable without additional model assumptions.

What it is NOT:

- Not a probabilistic aggregation (no independence assumption is
  implied; Dempster-Shafer or noisy-or rules are v0.2 territory).
- Not a calibrated uncertainty — no meaning as a confidence interval.
- Not symmetric in the sense of rewarding multiple confirming inputs;
  two strong inputs give the same composite as one strong input.

The formula rewrite in v0.2 should be localised to this single
function. No other module should hard-code the min rule.
"""
from __future__ import annotations


def composite(*inputs: float | None) -> float | None:
    """Combine confidences of inputs into a single composite score.

    - None values are dropped.
    - If no non-None values remain, returns None.
    - Otherwise returns ``min(non_none_values)``.

    v0.1 PLACEHOLDER — do not treat as final semantics.
    """
    non_none = [c for c in inputs if c is not None]
    if not non_none:
        return None
    return min(non_none)
