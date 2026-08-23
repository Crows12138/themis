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
            strata=[dict(cell) for cell in support.one_armed],
            recorded={"share": support.share},
        )
    return support


def overlap_assumption(support: Support) -> str:
    """The assumption id that is TRUE of this run.

    ``positivity_overlap_of_treatment_arms`` is a claim, and where the cells
    were counted it is a claim the count can contradict. Declaring it anyway
    is the report stating as an assumption something it has measured to be
    false — which is worse than not checking, because the reader takes the
    ledger as the list of things that were considered.
    """
    return ("positivity_violated_some_strata_hold_one_arm" if support.violated
            else "positivity_overlap_of_treatment_arms")
