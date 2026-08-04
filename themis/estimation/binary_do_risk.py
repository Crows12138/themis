"""Binary observational joint + interventional risk, recovered from a DataFrame.

The two attribution rungs — probabilities of causation (PN/PS/PNS, see
:mod:`themis.estimation.causation`) and the single binary counterfactual cell
(see :mod:`themis.estimation.counterfactual_cell`) — answer different
theorems, but both need exactly the same two things out of the data before
their theorem can run:

- the four observational cells ``P(X=x, Y=y)`` — empirical frequencies;
- the interventional risk ``P(Y=1 | do(X=x))`` for one or both arms. For
  binary Y, ``E[Y | do(X=x)] = P(Y=1 | do(X=x))`` exactly, so each arm is the
  back-door standardized (g-formula) mean ``Σ_z P̂(Y=1 | X=x, Z=z) · P̂(Z=z)``
  over a minimal back-door adjustment set Z. Z=∅ (exogeneity / randomization)
  reduces it to ``P̂(Y=1 | X=x)``.

Neither of those is the theorem under test in either module, so the
transcription lives here once and both estimators reuse it. What each module
owns is its own theorem: Tian-Pearl's PN/PS/PNS in one, the linear
consistency identity of :func:`themis.runtime.counterfactual.counterfactual_cell_interval`
in the other.

Reference: Hernán & Robins 2020 ch.13 for the g-formula (standardization)
plug-in in the non-parametric limit.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..runtime import structural_solver
from ..types import Atom
from .. import refusals
from ..refusals import EstimatorFailure


def minimal_backdoor_adjustment(
    graph, cause: Atom, effect: Atom, bidirected,
) -> tuple[str, ...]:
    """The minimal back-door adjustment set for the do-risks, as column names.

    Raises ``EstimatorFailure`` when no admissible set exists (an unmeasured
    confounder — the do-risks are not identified from the observational frame,
    and the caller must supply experimental risks)."""
    sets = structural_solver.minimal_adjustment_sets(
        graph, cause, effect, bidirected=bidirected or None,
    )
    if not sets:
        raise EstimatorFailure(
            refusals.DO_RISK_NOT_IDENTIFIABLE,
            "P(Y=1|do(X)) is not back-door identifiable from the observational "
            "data (no admissible adjustment set — likely an unmeasured "
            "confounder). Supply experimental_risk_treated / "
            "experimental_risk_control from a randomized experiment.",
        )
    # Prefer the smallest set (fewest strata → most support per cell).
    best = min(sets, key=len)
    return tuple(sorted(a.predicate for a in best))


def as_binary_column(col: pd.Series, name: str) -> np.ndarray:
    """Coerce a column to a boolean numpy array, refusing non-binary data."""
    vals = set(pd.unique(col.dropna()))
    if not vals <= {0, 1, True, False, 0.0, 1.0}:
        raise EstimatorFailure(
            refusals.CAUSE_OR_EFFECT_NOT_BINARY,
            f"this quantity requires a binary column {name!r}; got "
            f"values {refusals.describe(sorted(vals, key=str))}",
        )
    return col.to_numpy().astype(bool)


def observational_joint_xy(
    x: np.ndarray, y: np.ndarray,
) -> dict[tuple[bool, bool], float]:
    """Empirical P(X=x, Y=y) — the four cells as sample frequencies."""
    n = len(x)
    return {
        (xv, yv): float(np.count_nonzero((x == xv) & (y == yv))) / n
        for xv in (True, False)
        for yv in (True, False)
    }


def backdoor_do_risk(
    x: np.ndarray, y: np.ndarray, frame: pd.DataFrame,
    adjustment: tuple[str, ...], *, arm: bool,
) -> float:
    """P(Y=1 | do(X=arm)) by back-door standardization (discrete g-formula).

    ``Σ_z P̂(Y=1 | X=arm, Z=z) · P̂(Z=z)`` over the empirical distribution of
    the adjustment set Z. Z=∅ reduces to P̂(Y=1 | X=arm). A stratum present in
    the marginal Z but empty under this treatment arm is a positivity
    violation — raises rather than fabricating a mean."""
    if not adjustment:
        mask = x == arm
        if not mask.any():
            raise EstimatorFailure(
                refusals.INSUFFICIENT_SUPPORT,
                f"no rows with X={arm}; cannot estimate P(Y=1|do(X={arm})).",
            )
        return float(y[mask].mean())

    z = frame[list(adjustment)]
    n = len(frame)
    total = 0.0
    # Standardize over every stratum that occurs in the full sample.
    for _key, idx in z.groupby(list(adjustment), sort=False, observed=True).indices.items():
        p_z = len(idx) / n
        arm_rows = idx[x[idx] == arm]
        if arm_rows.size == 0:
            raise EstimatorFailure(
                refusals.INSUFFICIENT_SUPPORT,
                f"stratum has no X={arm} rows (positivity violation); "
                f"P(Y=1|do(X={arm})) is not estimable by standardization.",
            )
        p_y_given = float(y[arm_rows].mean())
        total += p_y_given * p_z
    return total
