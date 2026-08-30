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

:class:`Draws` is the third, and it is about the draws that did not
happen. Most refits can fail on a particular resample — an empty
stratum, a singular design, a reliability the correction cannot use —
and every loop in this package answers the same way, by skipping that
replicate and taking its percentiles over what is left. That is the
right answer; the interval IS over the evaluable draws. What was
missing is that nobody was told how many that was. A percentile
interval over 962 of 1000 draws and one over 1000 of 1000 are the same
two numbers on the page, and the first is a fact about how close this
sample or this declaration sits to a boundary the estimator cannot
cross — which is exactly the kind of thing this package exists to
report rather than absorb.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field

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

    **The draw is one of three ways a route carries this, and for a while
    it looked like the only one.** A bootstrap redraws σ² per replicate;
    SIMEX reads its fitted curve at λ* = −σ²/σ̂² instead, whose exact
    distribution follows from the same χ²; and the two routes that price
    somebody else's interval read the quantiles of the widening factor
    directly, in :meth:`inflation_interval`. Each is closed-form from the
    same declaration. The species that used to say "no route here can
    carry it" is gone because it ran out of routes — which is the honest
    reading of what it had been recording.
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

    def inflation_interval(
        self, noise_share: float, *, ci_level: float,
    ) -> tuple[float | None, float | None, float | None]:
        """What this declaration's own uncertainty does to a widening factor.

        Two routes here price somebody ELSE's interval rather than reporting
        one: a declared error variance takes a share of the residual, and
        every least-squares interval on that design is wider by
        ``1/√(1−share)``. Both are the same arithmetic on a different
        channel, so the branch is written once here rather than twice there.

        ``noise_share`` is that share at the DECLARED σ̂². Since σ² = σ̂²·df/X
        with X ~ χ²_df, the factor is ``1/√(1 − share·df/X)`` — monotone
        decreasing in X, so its quantiles are exact and no quadrature is
        needed. Returns ``(lower, upper, refuted)``, all ``None`` where the
        caller declared no study and the question does not arise.

        ``refuted`` is P(share·df/X ≥ 1) = χ²_df.cdf(df·share) — the share
        of the caller's own validation study at which the declared noise
        would take the whole residual, which is the case both routes already
        refuse outright at the declared value. Where it reaches the tail an
        endpoint stands for, ``upper`` is ``None``: the widening is bounded
        below and not above, and a finite number there would be a ceiling
        the study does not supply.
        """
        if self.validation_df is None:
            return None, None, None
        from scipy import stats

        df = self.validation_df
        tail = (1.0 - ci_level) / 2.0
        refuted = float(stats.chi2.cdf(df * noise_share, df))

        def _at(x: float) -> float:
            return float(1.0 / np.sqrt(1.0 - noise_share * df / x))

        lower = _at(float(stats.chi2.ppf(1.0 - tail, df)))
        upper = None if refuted >= tail else _at(
            float(stats.chi2.ppf(tail, df)))
        return lower, upper, refuted

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


#: The fewest replicates a percentile interval may be taken over.
#:
#: Two, because ``np.quantile`` of a single value returns that value: a
#: "95% interval" from one surviving draw is a point printed twice, and it
#: reaches the reader looking like the tightest result in the report. One
#: draw is not a sampling distribution, so there is no interval to report
#: and the honest answer is that there is none.
FEWEST_DRAWS = 2

#: Where a discarded draw goes when the loop caught something that carries
#: no refusal species.
#:
#: A key rather than silence. The alternative is a block whose reasons do
#: not add up to its losses, and a reader cannot tell an unaccounted draw
#: from one the producer forgot to count — so the honest name for "this
#: failed in a way nothing here classifies" is a name.
UNNAMED = "unclassified"


@dataclass
class Draws:
    """The replicates an interval was taken over, and the ones that were not.

    A percentile bootstrap asks for ``requested`` replicates and gets fewer
    whenever a refit fails on one — an empty stratum, a singular design, a
    declaration this particular resample cannot support. Skipping such a
    draw is correct: the interval is over the draws where the estimand is
    evaluable, which is what every loop in this package already said it did.
    Not saying HOW MANY was the defect, and it is a defect of a specific
    kind — the interval carries the truncation, the page does not, and the
    reader cannot get it back from the two numbers they are shown.

    **A loop rather than a counter**, because a counter can be added to a
    loop that already exists and a loop cannot be written without one. The
    thirty-five bootstrap loops here were thirty-five transcriptions of one
    algorithm, which is why the count could go missing in all of them at
    once; iterating this object is now the way that algorithm is spelled,
    and a source-reading gate holds every draw site to it. That is the part
    that survives the next estimator being written.

    It deliberately does NOT collect the values. Loops differ in what they
    accumulate — one slope, seven decomposition terms, a whole curve — and
    a container that insisted on one shape would either fit a third of them
    or become a shape of its own to learn. What is uniform across all of
    them is the question this answers: of the replicates asked for, how
    many produced a usable refit.

    A quantity that is undefined on a draw the refit HANDLED — a proportion
    whose denominator came out zero — is a different fact, about that
    quantity rather than about the resample, and is not counted here. The
    two would be indistinguishable in one number, and the reader's next
    move differs: one says the sample is near a boundary, the other says
    this particular ratio is.

    **Why a draw was dropped is kept, and it is kept as a species rather
    than as a count.** Two estimators had already discovered that the
    reason matters: a counterfactual cell reports the share of resamples on
    which the declared monotonicity turned out infeasible, and that share
    is the nearest thing this package has to a test of an assumption
    usually called untestable. It could not travel, because it was named
    after that estimator's reason rather than after the loop — so every
    other loop threw the same information away. Keyed on
    :class:`themis.refusals.Refusal` it travels: the vocabulary is closed
    and already registered, and a reader who sees which refusal ate the
    draws learns what to change, where a bare count only tells them
    something did.
    """

    requested: int
    used: int = field(default=0, init=False)
    discarded: dict[str, int] = field(default_factory=dict, init=False)

    def __iter__(self) -> Iterator[int]:
        """One pass per requested replicate.

        Yields the round index for loops that want it; most do not.
        """
        return iter(range(self.requested))

    def usable(self) -> None:
        """Record that this replicate produced a refit the interval can use.

        Called where the loop keeps its value, so the count and the kept
        value are decided at one point. Counting the failures instead would
        put the two on different branches, and a branch added later would
        only have to remember one of them.
        """
        self.used += 1

    def unusable(self, why: object = None) -> None:
        """Record that this replicate could not be used, and why.

        ``why`` is a :class:`themis.refusals.Refusal` where the loop caught
        one, and ``None`` where it caught something with no species —
        a linear-algebra error, a model that would not converge. The
        unnamed case is counted under :data:`UNNAMED` rather than dropped,
        because a reader who is told 40 draws went missing and shown
        reasons for 12 would reasonably read the other 28 as not having
        happened.
        """
        key = UNNAMED if why is None else str(why)
        self.discarded[key] = self.discarded.get(key, 0) + 1

    @property
    def lost(self) -> int:
        """How many replicates the interval does not stand on."""
        return self.requested - self.used

    @property
    def enough(self) -> bool:
        """Whether an interval may be reported at all."""
        return self.used >= FEWEST_DRAWS

    def record(self, *, cluster: str | None) -> dict:
        """What the envelope carries about this interval's resampling.

        One block because it is one question — how this interval's draws
        were made and how many of them there turned out to be. A reader
        holding the second without the first cannot tell a cluster
        bootstrap's smaller effective sample from a discarded draw.
        """
        return {
            "kind": "cluster" if cluster is not None else "iid",
            **({"cluster_column": cluster} if cluster is not None else {}),
            "requested": self.requested,
            "used": self.used,
            **({"discarded": dict(sorted(self.discarded.items()))}
               if self.discarded else {}),
        }


def share_lost_to(record: object, why: object) -> float | None:
    """Of the draws that could have decided ``why``, the share it ate.

    ``None`` where the question does not arise: no bootstrap ran, or no
    draw was lost to ``why``. A zero would be a different statement, and
    a surface that printed it would be telling every reader about an
    assumption nothing in their data touched.

    The denominator is the draws that ANSWERED — the used ones plus the
    ones ``why`` ate — and not ``requested``. A draw lost to something
    else was not a vote against ``why``; counting it as one would let a
    thin stratum quietly shrink a refutation rate, and the reason the
    block keys its losses at all is that those two are different facts.

    Read here rather than worked out at each surface, because three of
    them worked out the counterfactual cell's monotonicity share
    separately and one of them, being a browser, cannot import this. That
    one restates it; the two that can, call it.
    """
    if not isinstance(record, Mapping):
        return None
    discarded = record.get("discarded")
    if not isinstance(discarded, Mapping):
        return None
    lost = discarded.get(str(why))
    if not lost:
        return None
    answered = int(record.get("used") or 0) + int(lost)
    return int(lost) / answered if answered else None


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
