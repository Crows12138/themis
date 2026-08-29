"""Testing the causal null with proxies that cannot point-identify.

Miao, Geng & Tchetgen Tchetgen 2018 (*Biometrika* 105(4)) §4. Point
identification of ``pr{y | do(x)}`` from a pair of proxies needs both of them
to have at least as many categories as the unmeasured confounder ``U``. Where
one does not — one proxy only, a proxy coarser than ``U``, a channel matrix
that will not invert — the effect is not identified and the *causal null* can
still be tested::

    H0 : X ⊥ Y | U

which says ``X`` has no effect on ``Y`` at ANY level of ``U``. Rejecting it is
evidence of causation without any statement of how much.

How it works
------------
Under model (f), for every level ``x``::

    P(y | Z, x) = P(y | U, x) P(W | U)⁻¹ P(W | Z, x)

Stack the ``x`` levels. With ``i`` levels of ``X``, ``j`` of ``Z`` and ``k`` of
``W``, write ``q`` for the ``ij``-vector of ``E(Y | Z, x)`` and ``Q`` for the
``k × ij`` matrix whose columns are ``P(W | Z, x)``. Under H0 the second term
of the paper's decomposition (9) vanishes and::

    q = Qᵀ γ           for some k-vector γ

so the null is an OVER-IDENTIFYING restriction: ``ij`` numbers are claimed to
lie in a ``k``-dimensional space. What is tested is whether they do, with
``r = ij − k`` degrees of freedom — which is why ``ij ≥ k + 1`` is required,
and why a coarse ``Z`` can be paid for with a polytomous ``X``.

Where this departs from the paper, and what it cost to find out
--------------------------------------------------------------
Theorem 2 forms ``ξ`` by weighting with ``Σ``, the covariance of ``q̂`` alone,
and asks of ``Q̂`` only that it be consistent. But ``q̂`` and ``Q̂`` are averages
over the SAME rows of the same cells, and within a cell ``Y`` and ``W`` are
dependent — both are driven by ``U``. Writing ``e`` and ``E`` for their errors,
the residual is ``M(e − Eᵀγ)`` and not ``Me``, so a weight built from ``Var(e)``
alone is the wrong one by a term of the same order.

Measured, with the printed weight, at a nominal 5%: 15.5% at n=2000, 11.9% at
n=8000, 12.7% at n=30000 — a rate that does not fall as the sample grows,
which is what tells a systematic error from a small-sample one. Carrying the
first-stage error gives 5.4%, 4.4% and 6.0% on the same draws. The apparent
extra power of the printed form is that over-rejection and not sensitivity.

So what runs here is two-step GMM on the moments ``E[Y − γᵀe_W | cell] = 0``,
whose weight is the variance of the residual the fitted ``γ`` actually leaves.
Same null, same ``γ``, same ``r`` — only the weight differs, and the weight is
the whole difference between a test that keeps its size and one that does not.

This is a departure from the theorem as printed, not a correction of the
paper: its own simulations are reported to calibrate, the Supplementary
Material was not available here, and the settings may differ. What is claimed
is only what was measured.

Everything the test reports is derived from finite per-cell statistics —
share, ``E[Y]``, ``E[Y²]``, ``P(W)``, ``E[Y·1{W=w}]`` — which is what lets the
verifier re-run the whole thing without the data.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..refusals import EstimatorFailure, Refusal
from ..types import envelope_scalar

#: Weight passes. Two is the textbook two-step GMM: an opening weight that
#: does not depend on γ, then the weight the fitted γ implies. Fixed rather
#: than iterated to a tolerance because the verifier re-runs this and a
#: stopping rule is one more thing the two implementations could differ on.
_PASSES = 2

#: A cell with fewer rows than this has no usable within-cell variance, and a
#: variance of nothing would be divided by. Two is the arithmetic minimum;
#: this is the point past which the estimate is a number rather than a shape.
_MIN_CELL_ROWS = 30

#: Past this the stacked channel is not being solved, it is being chosen —
#: the same threshold the point estimate refuses at.
_MAX_CONDITION_NUMBER = 1e10


@dataclass(frozen=True)
class NullTestResult:
    """What the test produced, and everything it was produced from."""

    statistic: float
    degrees_of_freedom: int
    p_value: float
    #: One block per (x, z) cell, in the order the moments were stacked.
    cells: tuple[dict, ...]
    #: γ, the k coefficients the null says q lies on. Reported because the
    #: reader's question after "the null survived" is "on what", and because
    #: a verifier re-solving them is re-solving the test.
    coefficients: tuple[float, ...]


def _folded(values: pd.Series, groups: tuple[tuple[int, ...], ...]) -> np.ndarray:
    """Each row's proxy level replaced by the index of its group.

    Groups arrive as positions in the sorted level list — the shape the
    discrete path already resolved a declared coarsening into — so the fold
    here is the same fold formula (5) would have applied, and a run that
    reaches the test through a coarsened proxy is testing the channel it
    declared rather than one this module chose.
    """
    levels = sorted(values.unique())
    where = {levels[i]: group for group, members in enumerate(groups)
             for i in members}
    return values.map(where).to_numpy()


def _cell_statistics(df: pd.DataFrame, *, xcol: str, ycol: str, zcol: str,
                     wcol: str, x_levels, z_levels, w_levels) -> tuple:
    """Every cell's sufficient statistics, and nothing derived from them.

    The five per cell are what the whole test is a function of, so they are
    what travels: a record of the statistic alone would be a number nothing
    could disagree with.
    """
    n = len(df)
    x = df[xcol].to_numpy()
    z = df[zcol].to_numpy()
    w = df[wcol].to_numpy()
    y = df[ycol].to_numpy(dtype=float)
    cells = []
    for x_level in x_levels:
        for z_level in z_levels:
            rows = (x == x_level) & (z == z_level)
            count = int(rows.sum())
            if count < _MIN_CELL_ROWS:
                raise EstimatorFailure(
                    Refusal.INSUFFICIENT_SUPPORT,
                    cells=[{xcol: x_level, zcol: z_level}],
                    quantity=f"E({ycol} | {zcol}, {xcol})",
                    recorded={"rows": count, "needed": _MIN_CELL_ROWS},
                )
            here = y[rows]
            hits = w[rows]
            cells.append({
                # Through ``envelope_scalar`` because these two are the only
                # fields here that came from the DATA rather than from
                # arithmetic on it, and a column of booleans hands back a
                # type the envelope has no word for.
                "x": envelope_scalar(x_level), "z": envelope_scalar(z_level),
                "share": count / n,
                "mean_y": float(here.mean()),
                "mean_yy": float((here * here).mean()),
                "p_w": tuple(float((hits == level).mean())
                             for level in w_levels),
                "mean_y_w": tuple(float(here[hits == level].sum() / count)
                                  for level in w_levels),
            })
    return tuple(cells)


def _residual_variance(cell: dict, gamma: np.ndarray) -> float:
    """``Var(Y − γᵀe_W | cell)`` from the cell's recorded moments.

    ``e_W`` is one-hot, so ``E[e_W e_Wᵀ] = diag(P(W))`` and the cross term is
    the recorded ``E[Y·1{W=w}]``. No row is touched again.
    """
    p_w = np.asarray(cell["p_w"], dtype=float)
    y_w = np.asarray(cell["mean_y_w"], dtype=float)
    second = (cell["mean_yy"] - 2.0 * float(gamma @ y_w)
              + float(gamma @ (p_w * gamma)))
    first = cell["mean_y"] - float(gamma @ p_w)
    return max(second - first * first, 0.0)


def solve_null_test(cells: tuple[dict, ...]) -> tuple:
    """``(statistic, rank, gamma)`` from the cells alone.

    Exported because the verifier re-derives the test from the same record by
    the same arithmetic — one function with two callers, which is what the
    rest of this package is held to.
    """
    share = np.array([c["share"] for c in cells])
    q = np.array([c["mean_y"] for c in cells])
    design_q = np.array([c["p_w"] for c in cells])          # ij × k
    # The opening weight is the variance of Y itself, which is Theorem 2's.
    # It needs no γ, which is the only reason it goes first.
    variance = np.array([c["mean_yy"] - c["mean_y"] ** 2 for c in cells])
    gamma = np.zeros(design_q.shape[1])
    rank = 0
    for _ in range(_PASSES):
        if not np.all(variance > 0):
            raise EstimatorFailure(
                Refusal.RANK_CONDITION_VIOLATED,
                recorded={"zero_variance_cells": int((variance <= 0).sum())},
            )
        root = np.sqrt(share / variance)
        design = design_q * root[:, None]
        rank = int(np.linalg.matrix_rank(design))
        if rank < design_q.shape[1]:
            raise EstimatorFailure(
                Refusal.STACKED_CHANNEL_IS_RANK_DEFICIENT,
                rank=rank, needed=design_q.shape[1],
            )
        condition = float(np.linalg.cond(design))
        if not np.isfinite(condition) or condition > _MAX_CONDITION_NUMBER:
            raise EstimatorFailure(
                Refusal.RANK_CONDITION_VIOLATED,
                recorded={"condition_number": condition},
            )
        gamma, *_ = np.linalg.lstsq(design, root * q, rcond=None)
        variance = np.array([_residual_variance(c, gamma) for c in cells])
    root = np.sqrt(share / variance)
    moment = root * (q - design_q @ gamma)
    return float(moment @ moment), rank, gamma


def test_causal_null(
    df: pd.DataFrame, *, xcol: str, ycol: str, zcol: str, wcol: str,
    w_groups: "tuple[tuple[int, ...], ...] | None" = None,
) -> NullTestResult:
    """Miao §4's test, on the mean scale, from this frame.

    The mean scale rather than one level of a categorical outcome, which is
    what the paper offers for an outcome that is not categorical: ``q =
    {E(Y | Z, x₁), …, E(Y | Z, xᵢ)}``. It is also the scale the rest of
    Themis's proximal path answers on, so a reader is not asked to hold two.

    The two proxies are used at OPPOSITE granularities, and that asymmetry is
    the test's whole shape. ``W`` is folded to ``w_groups`` because the null
    reads ``q = Qᵀγ`` with γ carrying one coefficient per state of ``U``, and
    ``P(W | U)`` inverts only when ``W`` has as many levels as ``U``. ``Z``
    is used RAW: every level of it is another moment, and moments are what
    the test spends. The point estimate wanted both folded to exactly k, and
    it is the fold on ``Z`` that failed — which is how a query arrives here.
    """
    from scipy import stats

    if w_groups is not None:
        df = df.assign(**{wcol: _folded(df[wcol], w_groups)})
    x_levels = sorted(df[xcol].unique())
    z_levels = sorted(df[zcol].unique())
    w_levels = sorted(df[wcol].unique())
    moments = len(x_levels) * len(z_levels)
    unknowns = len(w_levels)
    if moments < unknowns + 1:
        raise EstimatorFailure(
            Refusal.NO_DEGREES_OF_FREEDOM_TO_TEST_THE_NULL,
            treatment=xcol, moments=moments, unknowns=unknowns,
            treatment_levels=len(x_levels), proxy_levels=len(z_levels),
        )
    cells = _cell_statistics(
        df, xcol=xcol, ycol=ycol, zcol=zcol, wcol=wcol,
        x_levels=x_levels, z_levels=z_levels, w_levels=w_levels)
    statistic, rank, gamma = solve_null_test(cells)
    n = len(df)
    degrees = moments - rank
    return NullTestResult(
        statistic=n * statistic,
        degrees_of_freedom=degrees,
        p_value=float(stats.chi2.sf(n * statistic, degrees)),
        cells=cells,
        coefficients=tuple(float(v) for v in gamma),
    )
