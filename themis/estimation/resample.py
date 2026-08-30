"""Shared bootstrap resampler — i.i.d. rows or whole clusters.

Every data estimator's percentile-bootstrap CI draws B resamples and
refits. By default that draw is an i.i.d. row resample
(``rng.integers(0, n, size=n)``), which assumes independent
observations. When the data has within-cluster dependence (families /
pedigrees, repeated measures, schools), i.i.d. resampling
UNDERESTIMATES the sampling variance, so the percentile CI comes out
too narrow (anti-conservative).

This module centralises the draw so every estimator routes through one
helper:

- ``groups is None`` → i.i.d. row resample, byte-identical to the
  legacy inline ``rng.integers(0, n, size=n)`` (same rng consumption).
- ``groups`` supplied → Cameron-Gelbach-Miller *pairs cluster
  bootstrap* (Cameron & Miller 2015, "A Practitioner's Guide to
  Cluster-Robust Inference", §3.3): draw G cluster ids with
  replacement from the G unique clusters, then concatenate ALL rows of
  the drawn clusters. The resampled frame keeps whole clusters intact,
  so the within-cluster correlation structure is preserved and the
  bootstrap distribution reflects the true (cluster-level) sampling
  variability.

The helper returns POSITIONAL indices into a frame of length ``n``, so
callers use them exactly like the old inline draw: ``df.iloc[idx]``.
Note the cluster draw can return a frame whose length differs from
``n`` (clusters have unequal sizes) — that is correct and expected for
the pairs cluster bootstrap.

**A resample is a statement about what varied, and the rows are not the
only thing that did.** The paragraph above is one axis of that: ignore
the clustering and the interval comes out too narrow, because a source
of variation was held still that was not still. :class:`DeclaredVariance`
is the second axis. A measurement-error correction reads a σ² the caller
declares, and where that σ² came from a validation study it is an
ESTIMATE — so an interval computed with it held fixed prices the main
sample's uncertainty and nothing else, and comes out too narrow for
exactly the reason the cluster case does.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class DeclaredVariance:
    """A variance the caller declared, and how well they know it.

    ``value`` is σ². ``validation_df`` is the degrees of freedom of that
    estimate when it came from a validation substudy or a set of replicate
    measurements, and ``None`` when the caller means the number is known
    exactly — a dose assigned by protocol, a rounding width, a device
    tolerance quoted by its maker.

    **Two fields rather than two arguments**, because they are one fact.
    Threading ``(value, df)`` as a pair through five estimators is two
    records of one thing, and two records drift: the day a sixth estimator
    reads the value and not the df, its interval is the old one and
    nothing says so.

    ``None`` is not a default standing in for a number nobody supplied.
    It is the claim that there is no sampling distribution here to draw
    from, and :meth:`draw` answers it by consuming no randomness at all —
    so a run that declares no df is byte-identical to the same run before
    this class existed, rng stream included.

    The draw is exact rather than approximate under the premise these
    estimators already carry. Classical additive error with normal
    replicates makes ``σ̂²·df/σ² ~ χ²_df``, so

        σ²* = σ̂² · df / X,   X ~ χ²_df

    is a draw from what σ² could have been given what was measured. It is
    the parametric bootstrap of the validation study, run alongside the
    non-parametric bootstrap of the main sample — and the two are drawn
    independently because the two studies are.

    What this does NOT do is re-draw a declaration that no study
    estimated. ``differential_error``'s note has said since it was written
    that resampling such a quantity would be "widening the interval by
    re-drawing something nobody drew", and that is right. The thing that
    was missing was never the draw; it was knowing that a draw had
    happened somewhere else, which is what ``validation_df`` records.
    """

    value: float
    validation_df: int | None = None

    def __post_init__(self) -> None:
        # At construction rather than at any one caller's door, because
        # every route reaches this class and a check one route makes is a
        # check the other four do not get. Construction is reached from
        # inside the handler that owns the refusal, so this raise is caught
        # and recorded rather than leaving by the exception door.
        df = self.validation_df
        if df is None:
            return
        # Whole rather than ``int``: a caller who read their declaration out
        # of a JSON file or off a frame has 49.0 and means 49, and refusing
        # that would refuse a fact about their parser under wording about
        # their study. 2.5 is refused, and so is ``True`` — which is an
        # ``int`` and names no χ² anybody could draw from.
        whole = (not isinstance(df, bool) and isinstance(df, (int, float))
                 and float(df).is_integer() and df >= 1)
        if not whole:
            from ..refusals import EstimatorFailure, Refusal
            raise EstimatorFailure(
                Refusal.NON_POSITIVE_VALIDATION_DF, given=df)
        object.__setattr__(self, "validation_df", int(df))

    @staticmethod
    def declared_value(given: object) -> object:
        """The σ² a caller declared, out of whichever shape they declared it.

        Three shapes reach the estimators — a whole measurement spec, a bare
        number from a direct Python call, and one of these already built —
        and every guard that asks "is this variance usable" has to see past
        all three to the number. Answered once here rather than at each
        guard, because a guard that knows two of the three does not refuse a
        bad declaration; it refuses the shape it did not recognise, under
        wording about the variance.
        """
        if isinstance(given, DeclaredVariance):
            return given.value
        if isinstance(given, Mapping):
            return given.get("error_variance")
        return given

    @classmethod
    def read(cls, given: object) -> "DeclaredVariance":
        """One of these from whatever a caller declared.

        A bare number stays sugar for "known exactly", which is what every
        caller wrote before this class existed and what most of them mean.
        A whole spec is read for both keys at once, which is the point of
        having one object: the number and how well it is known arrive
        together or the second is lost.

        ``object`` rather than a union of the shapes, for the same reason
        the entry points annotate their own parameter that way: whether what
        arrived is a USABLE variance is the estimator's judgement, made in
        its own words and naming its own variable, and an annotation here
        claiming the judgement was already made would be this function
        taking it over. Every caller has made it by the time it reaches
        here, which is why the coercion below cannot fail on the value.

        It can fail on the degrees of freedom, and that is deliberate: this
        is the one place a declaration becomes an object, so it is the one
        place that can refuse a declaration nobody else will look at. Every
        caller reaches it from inside the handler that owns the refusal, so
        the sentence leaves by the door the reader can read.
        """
        if isinstance(given, DeclaredVariance):
            return given
        if isinstance(given, Mapping):
            return cls(value=float(given["error_variance"]),
                       validation_df=given.get("validation_df"))
        return cls(value=float(given))  # type: ignore[arg-type]

    @classmethod
    def from_spec(cls, spec) -> object:
        """What one measurement spec declares, as an estimator takes it.

        A NORMALISER rather than a validator: what it can turn into one of
        these it does, and what it cannot it hands on untouched. The
        estimators already answer an absent variance and an unusable one
        differently, each naming the variable it is about, and a check here
        would either duplicate those sentences or take them away — which is
        why the unusable case leaves as the caller's own value, for their
        refusal to quote back.
        """
        if not isinstance(spec, Mapping):
            return None
        value = spec.get("error_variance")
        if isinstance(value, DeclaredVariance):
            return value
        if (value is None or isinstance(value, bool)
                or not isinstance(value, (int, float))):
            return value
        return cls.read(spec)

    def draw(self, rng: np.random.Generator) -> float:
        """One draw of what this variance could have been.

        Consumes no randomness when there is no distribution to draw from,
        which is what keeps every existing run reproducing exactly.
        """
        if self.validation_df is None:
            return self.value
        return self.value * self.validation_df / rng.chisquare(
            self.validation_df)

    def refuse_if_not_carried(self, route: str, variable: str) -> None:
        """Say so, where this route's interval cannot carry the draw.

        Not every interval is a bootstrap. An analytic variance
        extrapolation and a deterministic inflation factor both have
        nowhere to put a redrawn σ², and answering anyway would ship the
        interval that ignores it under a field saying it was carried — the
        same "protection the answer does not have" the semantic checker
        already refuses one layer up.

        A route that CANNOT carry it says so here rather than each writing
        the check, because the sentence is about the declaration and not
        about the route: which routes carry it is the list of callers.
        """
        if self.validation_df is None:
            return
        from ..refusals import EstimatorFailure, Refusal
        raise EstimatorFailure(
            Refusal.VALIDATION_DF_NOT_CARRIED_HERE,
            route=route, variable=variable, given=self.validation_df)

    def premise(self, family: str, variable: str) -> str:
        """The ledger id this declaration carries, for one variable.

        The two are different CLAIMS and so different ids: one says the
        number is taken as exact, the other says a study estimated it and
        its own uncertainty is priced into the interval — which rests on
        the declared degrees of freedom being right and on the replicate
        errors being normal, neither of which the first claim needs.

        Here rather than at the five estimators, because the branch is the
        same branch every time and a branch written five times is five
        branches on the day one is edited. It is also the branch a sixth
        estimator would forget: reading ``.value`` and filing the
        known-and-fixed premise is exactly the drift this method exists to
        make impossible.
        """
        settled = "known_and_fixed" if self.validation_df is None else (
            "from_a_validation_study")
        return f"{family}_{settled}_on_{variable}"


def resample_indices(
    n: int,
    rng: np.random.Generator,
    groups: np.ndarray | None = None,
) -> np.ndarray:
    """Return positional indices for one bootstrap replicate.

    Parameters
    ----------
    n: number of rows in the frame being resampled.
    rng: a seeded ``numpy.random.Generator`` (deterministic draws).
    groups: optional length-``n`` array of cluster labels, positionally
        aligned with the frame. ``None`` → i.i.d. row resample.

    Returns
    -------
    A 1-D ``int`` array of positional indices. For the i.i.d. path the
    length is exactly ``n``; for the cluster path it is the sum of the
    sizes of the G drawn clusters.
    """
    if groups is None:
        # Byte-identical to the legacy inline draw — same rng state
        # consumption, so cluster=None reproduces existing results.
        return rng.integers(0, n, size=n)

    groups = np.asarray(groups)
    if len(groups) != n:
        raise ValueError(
            f"groups length {len(groups)} does not match frame length {n}"
        )
    # Contiguous 0..G-1 codes in first-appearance order (deterministic,
    # independent of label dtype: ints, strings, categoricals all work).
    codes = pd.factorize(groups, sort=False)[0]
    n_clusters = int(codes.max()) + 1 if len(codes) else 0
    if n_clusters == 0:
        return rng.integers(0, n, size=n)

    positions = np.arange(n)
    cluster_positions = [positions[codes == g] for g in range(n_clusters)]

    drawn = rng.integers(0, n_clusters, size=n_clusters)
    return np.concatenate([cluster_positions[g] for g in drawn])


def cluster_labels(
    data: pd.DataFrame,
    cluster: str,
    *,
    expected_n: int,
) -> np.ndarray:
    """Extract the cluster-label array for a column, with validation.

    The cluster column is a *variance concern*, not a causal-model
    node — it is never coerced to bool/float, never added to the model
    design, and never part of the data hash. This helper just pulls the
    raw labels (any hashable dtype) positionally aligned with the
    estimator's rows.

    Raises ``KeyError`` if the column is absent, ``ValueError`` if its
    length disagrees with the model frame or it contains nulls (a null
    cluster id would silently form its own degenerate cluster).
    """
    if cluster not in data.columns:
        raise KeyError(
            f"cluster column {cluster!r} not found in data columns "
            f"{list(data.columns)}"
        )
    labels = data[cluster].to_numpy()
    if len(labels) != expected_n:
        raise ValueError(
            f"cluster column {cluster!r} has length {len(labels)} but the "
            f"model frame has {expected_n} rows"
        )
    if pd.isna(labels).any():
        raise ValueError(
            f"cluster column {cluster!r} contains null values; every row "
            f"must carry a cluster id for the cluster bootstrap"
        )
    return labels
