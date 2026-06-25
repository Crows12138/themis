"""Deterministic counterfactual point computation on a linear SCM.

Pearl, Glymour & Jewell, *Causal Inference in Statistics: A Primer*
(2016), §4.2 — "The Three Steps in Computing Counterfactuals":

    (i)   Abduction:  use the evidence E=e (a fully-observed unit) to
                      recover the exogenous variables U.
    (ii)  Action:     modify the model by do(X=x) — replace X's structural
                      equation with the constant.
    (iii) Prediction: use the modified model + the recovered U to compute
                      the target's counterfactual value.

For a linear SCM (each endogenous V = Σ_p α_{p→V}·p + U_V) this is exact
and fully analytic — the regime where the structural *mechanisms*, not
just the DAG, are known, so a single unit's counterfactual is a point,
not a Balke-Pearl bound. Verified against the Primer's worked Model 4.1
(Joe: U=(0.5, 0.75, 0.75); do(H=2) ⇒ Y=1.90).

This module is a pure computation over already-supplied structural
equations + observed unit values; it is the oracle, nothing is
re-derived.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..types import Atom


@dataclass(frozen=True)
class LinearSCMCounterfactual:
    """Result of an abduction–action–prediction computation.

    - ``target_value`` is the counterfactual value of the queried target.
    - ``noise`` maps each relevant variable to its abducted U_V (step i).
    - ``cf_values`` maps each relevant variable to its value in the
      modified (post-intervention) model (step iii) — the target's entry
      equals ``target_value``.
    """

    target_value: float
    noise: dict[Atom, float]
    cf_values: dict[Atom, float]


def linear_scm_counterfactual(
    *,
    equations: dict[Atom, tuple[tuple[Atom, float], ...]],
    observed: dict[Atom, float],
    intervention_var: Atom,
    intervention_value: float,
    target: Atom,
    topo_order: tuple[Atom, ...],
) -> LinearSCMCounterfactual:
    """Compute a deterministic linear-SCM counterfactual point.

    ``equations`` maps each relevant variable V to the tuple of
    ``(parent, coefficient)`` pairs in its structural equation
    ``V = Σ coefficient·parent + U_V``. ``observed`` gives the factual
    value of every relevant variable (the unit). ``topo_order`` is a
    topological order of the relevant variables (parents before
    children). The caller guarantees the relevant set is parent-closed
    and fully observed; this function is pure arithmetic.
    """
    # (i) Abduction — recover the exogenous term of every relevant V.
    noise: dict[Atom, float] = {}
    for v, terms in equations.items():
        noise[v] = observed[v] - sum(coef * observed[p] for p, coef in terms)

    # (ii) Action + (iii) Prediction — propagate forward, the intervened
    # variable pinned to its constant, every other V rebuilt from its
    # recovered U and its parents' counterfactual values.
    cf: dict[Atom, float] = {}
    for v in topo_order:
        if v == intervention_var:
            cf[v] = float(intervention_value)
        else:
            cf[v] = noise[v] + sum(coef * cf[p] for p, coef in equations[v])

    return LinearSCMCounterfactual(
        target_value=cf[target], noise=noise, cf_values=cf,
    )
