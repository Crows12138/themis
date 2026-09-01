"""Which cells of the adjustment set the contrast can be estimated in.

The back-door formula sums ``P(Y | X=arm, Z=z)`` over z, and that term is a
comparison the data made only in the cells that hold both arms. In a cell
holding one arm an outcome regression still returns a number: it fills the
absent arm from the slope it learned where both were present. That can be
the right thing to do — it is what regression adjustment is FOR — but it is
not something the data said, and an estimator that does it silently has
spoken for the data.

Three places state the per-stratum condition and none of them measured it:

- the estimator guards (``backdoor.py``, ``aipw.py``) ask whether the
  treatment column varies AT ALL. That is the same condition summed over z,
  so it is true as soon as ANY cell holds both arms — structurally blind to
  the cell that holds one;
- the assumption row ``positivity_overlap_of_treatment_arms`` reads "both
  treatment arms have units in every stratum of the adjustment set";
- ``GapKind.PROPENSITY_OVERLAP_VIOLATION``'s own comment reads "every
  confounder stratum has both treated and untreated units" and then triggers
  on a FITTED propensity leaving [0.05, 0.95]. A fitted model smooths across
  cells: on the measured case it handed a cell whose empirical treated rate
  is 0.000 a comfortable 0.091, and the gap did not fire on a frame with a
  quarter of the sample in a stratum that was never treated.

One table answers all three, so the guard that refuses, the row that declares
the assumption and the gap that discloses the extrapolation cannot disagree
about the same frame.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..refusals import EstimatorFailure, Refusal

#: A column with more distinct values than this is treated as continuous, and
#: a continuous covariate has no strata to count.
#:
#: The judgement is not new here — ``measurement`` and ``selection`` refuse a
#: covariate above it as ``continuous_adjustment``, and each held its own copy
#: of the number. This is the home, so a fourth reading of "does this column
#: have strata" cannot come out differently from the other three.
MAX_LEVELS = 20

#: Where to read a curve when the column has too many levels to enumerate.
#:
#: Five points is enough for a line plus a visible departure from one. The
#: tuple is here rather than beside either caller because two estimands now
#: ask the same question of a column — a dose-response curve asks it of the
#: treatment it varies, a controlled direct effect of the mediator it holds
#: fixed — and a reader comparing two curves from one run is entitled to
#: have them read at the same places.
CURVE_QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

#: Rows a cell needs before its arms say anything.
#:
#: Not a sample-size rule and not tuned: two is what "both arms are present"
#: costs, so a cell of one row is silent about assignment rather than evidence
#: against it. Applied to the AVERAGE cell, it is what separates a
#: stratification from an index — a cut with more cells than the sample can
#: fill twice over is a regressor that happens to have few distinct values.
_MIN_ROWS_PER_CELL = 2


@dataclass(frozen=True)
class Support:
    """What the adjustment set's cells hold, for one treatment.

    ``enumerable`` is the first question and not a detail: a continuous
    covariate gives every row its own cell, so every cell holds one arm and a
    per-cell rule would refuse every run that regression adjustment exists to
    serve. When it is false nothing below it means anything, and the fitted
    propensity is the only witness there is.
    """

    enumerable: bool
    """Whether this adjustment set cuts the sample into cells at all.

    Two things have to hold and neither implies the other. Every column has
    to have few enough levels to enumerate — the judgement ``MAX_LEVELS``
    already makes — and the cells have to be able to HOLD both arms, which
    a cell of one row cannot, however the treatment was assigned. Cardinality
    alone cannot tell twelve floats in twelve rows from three channels in
    four thousand: both are under the cap, and only one is a stratification.
    """
    cells: int
    """Cells that OCCUR in the sample. A cell the formula weights by zero
    contributes nothing, so the ones that never occur are not counted here —
    the species for those is ``insufficient_support`` and it is a different
    fact."""
    supported: int
    one_armed: tuple[dict, ...]
    """Worst first: the reader meets the largest unsupported cell first,
    because how much of the sample sits in it is what tells them whether the
    answer is mostly measured or mostly modelled."""
    share: float
    """Of the sample, the fraction sitting in ``one_armed``. This is the
    extrapolated mass — the part of the answer the outcome model supplied."""

    @property
    def violated(self) -> bool:
        """Some cell the formula sums over holds a single arm."""
        return self.enumerable and bool(self.one_armed)

    @property
    def exhausted(self) -> bool:
        """NO cell holds both arms, so nothing in the answer is a comparison
        the data made. Not a worse version of ``violated``: there is no slope
        learned anywhere to extrapolate FROM, and the number is the model."""
        return self.enumerable and self.cells > 0 and self.supported == 0


#: Nothing to say: no adjustment set, no strata, or no contrast to look for.
_UNKNOWN = Support(enumerable=False, cells=0, supported=0, one_armed=(),
                   share=0.0)


def arm_support(
    df: pd.DataFrame, treatment: str, adjustment: tuple[str, ...],
) -> Support:
    """Count the cells of ``adjustment`` that hold every observed arm."""
    if not adjustment:
        return _UNKNOWN
    if any(df[col].nunique(dropna=True) > MAX_LEVELS for col in adjustment):
        return _UNKNOWN

    arms = set(pd.unique(df[treatment].dropna()))
    if len(arms) < 2:
        # The sample itself carries no contrast. That is the marginal guard's
        # fact and a different species; reporting it as "every cell is
        # one-armed" would be true and would name the wrong thing.
        return _UNKNOWN

    values = df[treatment].to_numpy()
    n = len(df)
    supported = 0
    unsupported: list[tuple[int, dict]] = []
    grouped = df.groupby(list(adjustment), sort=False, observed=True)
    for key, idx in grouped.indices.items():
        cell = dict(zip(adjustment, key if isinstance(key, tuple) else (key,)))
        if set(pd.unique(values[idx])) >= arms:
            supported += 1
        else:
            unsupported.append((len(idx), cell))

    cells = supported + len(unsupported)
    if cells * _MIN_ROWS_PER_CELL > n:
        # More cells than the sample can fill. This is a continuous covariate
        # wearing a low cardinality — twelve distinct floats in twelve rows
        # sit under MAX_LEVELS and are not strata — and reading it as one
        # would find every cell single-armed and refuse a frame where the
        # only thing wrong is that the adjustment is a regressor.
        return _UNKNOWN

    unsupported.sort(key=lambda pair: -pair[0])
    rows = sum(size for size, _cell in unsupported)
    return Support(
        enumerable=True,
        cells=cells,
        supported=supported,
        one_armed=tuple(cell for _size, cell in unsupported),
        share=rows / n if n else 0.0,
    )


def require_within_stratum_contrast(
    df: pd.DataFrame, treatment: str, adjustment: tuple[str, ...],
) -> Support:
    """The support table, and a refusal when no cell can supply a contrast.

    The stop is at zero, not at a threshold. Where SOME cells hold both arms
    the estimate is part measurement and part extrapolation, and the honest
    answer is the number with the unsupported cells declared — which is what
    the caller does with what this returns. Where NO cell holds both arms
    there is no measured part: every term the formula needs was produced by
    the outcome model, and calling that an estimate with a caveat would put a
    confidence interval on a model's opinion. It is refused instead.
    """
    support = arm_support(df, treatment, adjustment)
    if support.exhausted:
        raise EstimatorFailure(
            Refusal.NO_WITHIN_STRATUM_CONTRAST,
            column=treatment,
            strata=[dict(cell) for cell in support.one_armed],
            recorded={"share": support.share},
        )
    return support


def levels_over_support(
    values: np.ndarray, requested: tuple[float, ...] | None = None,
) -> tuple[tuple[float, ...], bool]:
    """The levels to report a curve at, and whether the data holds them all.

    Two answers, because the column decides which one it is. A column with
    few enough distinct values to enumerate (:data:`MAX_LEVELS`, the same
    judgement four other readings of "does this column have strata" make)
    is reported AT those values: they are what the sample holds, so nothing
    is extrapolated and a reader recognises every one of them. A column
    with more is read at :data:`CURVE_QUANTILES` of its own observed
    spread — inside the support by construction, which is the property
    that matters, since a model asked outside it answers anyway.

    The second element says which of the two happened. A caller that must
    declare what it did — every level was observed, or the curve was read
    at quantiles of a continuum — cannot recover that from the levels
    alone, and inferring it from their count would make the boundary a
    second, private copy of ``MAX_LEVELS``.

    ``requested`` overrides both when the caller has a domain the program
    declared. Fewer than two points is not an override: a curve needs two
    places to be a curve, and one point silently becomes the whole answer.
    """
    v = np.asarray(values, dtype=float)
    if requested is not None and len(requested) >= 2:
        return tuple(sorted(float(p) for p in requested)), True
    distinct = sorted(set(float(x) for x in np.unique(v)))
    if len(distinct) <= MAX_LEVELS:
        return tuple(distinct), True
    # Deduplicate: on a small sample adjacent quantiles can collapse onto
    # one value, and a curve reported twice at the same level says nothing
    # the once did not.
    unique = sorted(set(round(float(q), 6) for q in np.quantile(v, CURVE_QUANTILES)))
    if len(unique) < 2:
        unique = sorted({float(v.min()), float(v.max())})
    return tuple(unique), False


#: The premise the count is about, whichever way the count comes out.
#:
#: This was a function of the :class:`Support`, returning a second id on a
#: frame whose cells contradicted the claim — the ledger asserting as an
#: assumption something the run had measured to be false is worse than not
#: checking, and forking the id was the only way to avoid it while a line had
#: nowhere to record a verdict. It has one now, so the premise is one premise
#: and what happened to it is ``checked`` on the line: the counts reach the
#: envelope as ``numeric_estimate.stratum_support`` and both the producer and
#: the verifier read the verdict off them. Two ids for one premise also meant
#: the passing frame and the frame nobody counted said the same thing.
OVERLAP_ASSUMPTION = "positivity_overlap_of_treatment_arms"
