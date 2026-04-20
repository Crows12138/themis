"""Composite confidence scoring (v0.2 formal rule).

Confidence is a per-input reliability scalar in [0, 1]. It is NOT
a statistical confidence interval, NOT a Bayesian posterior, and
NOT calibrated against any frequentist guarantee. See
``confidence_rfc_v0_2.md`` for the rule's motivation and the
candidates that were evaluated.

**Rule (v0.2)**: minimum of non-None inputs; None if every input
is missing:

    composite(c1, c2, ..., cn) = min(c for c in inputs if c is not None)

Properties (RFC §4 / §7):

- S1 Order-independent: ``composite(a, b) == composite(b, a)``.
- S2 Monotone: adding a weaker input cannot raise the composite.
- S3 Identity: ``composite(c) == c`` for non-None c.
- S4 Empty → None.
- S5 No independence assumption required.
- S6 Interpretable: "the weakest link decides".
- S7 Simple to compute.
- S8 Pipeline-friendly: min of mins is still a min.
- S9 Backward compatible with v0.1.0 (placeholder was min too).

Explicitly NOT:

- Not a probabilistic aggregation. Dempster-Shafer and noisy-OR
  were rejected per RFC §6 (noisy-OR violates monotonicity; DS is
  over-engineered for a scalar confidence channel).
- Not rewarding accumulated evidence: two weak inputs still
  compose to the weaker one. Evidence accumulation needs an
  independent-evidence declaration (v0.3+), opt-in only.

Inputs are collected by ``scheduler._gather_input_confidences`` per
RFC §3.3: probability slots (one per distinct ``ProbabilityKey``
referenced by the formula, slot_conf = min over source statements)
plus observation slots (matched to entries in ``q.given`` by atom
AND value; intervention atoms excluded).
"""
from __future__ import annotations


def composite(*inputs: float | None) -> float | None:
    """Combine confidences into a single composite score per the
    v0.2 min rule.

    - None values are dropped before reduction.
    - If no non-None values remain, returns None.
    - Otherwise returns ``min(non_none_values)``.
    """
    non_none = [c for c in inputs if c is not None]
    if not non_none:
        return None
    return min(non_none)
