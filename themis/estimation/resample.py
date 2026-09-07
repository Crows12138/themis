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
exactly the reason the cluster case does. :class:`DeclaredMatrix` is the
same axis on a declaration that is a table rather than a number: a
misclassification correction reads a confusion matrix, and where that
matrix was counted in a validation study its entries are proportions
over a finite tally, not the channel itself. :class:`DeclaredTracking`
is the axis on a declaration that is a REGRESSION — how much of an
exposure's error tracks the outcome — and it is the one place where two
numbers from one study have to be drawn together rather than each on
its own.

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
    Threading ``(value, df)`` as a pair through the estimators is two
    records of one thing, and two records drift: the day one of them reads
    the value and not the df, its interval is the old one and nothing says
    so.

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
        absorbed_share: float = 0.0,
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

        ``absorbed_share`` is the part of the declared variance the design has
        already taken OUT of the residual, as a share of that residual —
        nonzero only where a caller declared that the error tracks a column
        the design carries. It has to be named because what the study measured
        is the TOTAL, so the total is what gets redrawn: at draw X the share
        still in the residual is ``(share + absorbed)·df/X − absorbed``, which
        is the expression above shifted, still monotone in X, and so still
        exact at its quantiles. At zero it reduces to that expression term for
        term, which is what leaves every run without such a declaration
        unmoved.
        """
        if self.validation_df is None:
            return None, None, None
        from scipy import stats

        df = self.validation_df
        tail = (1.0 - ci_level) / 2.0
        total = noise_share + absorbed_share
        refuted = float(
            stats.chi2.cdf(df * total / (1.0 + absorbed_share), df))

        def _at(x: float) -> float:
            return float(
                1.0 / np.sqrt(1.0 - (total * df / x - absorbed_share)))

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

        Here rather than at the estimators, because the branch is the same
        branch every time and a branch written once per estimator is that
        many branches on the day one is edited. It is also the branch an
        estimator forgets: reading ``.value`` and filing the known-and-fixed
        premise is exactly the drift this method exists to make impossible,
        and it happened — on the two routes that came to this class for its
        quantiles and then wrote their own premise id by hand, so their
        ledgers told a reader the study had not been priced while the
        interval beside it said it had.
        """
        settled = SETTLED_EXACTLY if self.validation_df is None else (
            SETTLED_BY_A_STUDY)
        return f"{family}_{settled}_on_{variable}"


#: The two answers to "how was this declaration settled", as they read in a
#: premise id.
#:
#: One pair for every family of declared quantity, because the question is
#: the same question — was this number taken as exact, or did a study
#: measure it and does the interval carry that study — and a reader who has
#: learnt to look for the distinction on a variance should find it worded
#: identically on a confusion matrix. The verifier restates both words
#: rather than importing them, for the reason it restates everything else.
SETTLED_EXACTLY = "known_and_fixed"
SETTLED_BY_A_STUDY = "from_a_validation_study"

#: What one validation study says about an error that tracks the outcome:
#: the four numbers a regression of ``W − X*`` on the outcome's residual
#: reports. Spelt once, because the shape is read at three doors — the
#: guard that judges what arrived, the routing property that needs only the
#: coefficient, and the schema.
TRACKING_STUDY_FIELDS = ("coefficient", "standard_error",
                         "residual_variance", "validation_df")


@dataclass(frozen=True)
class DeclaredTracking:
    """How much of an exposure's error tracks the outcome, and how well known.

    ``coefficient`` is δ — the slope a validation substudy holding
    (Y, X*, W, Z) reports when it regresses ``W − X*`` on the outcome's
    residual. Declared alone it is taken as exact, which is what a coding
    rule or a protocol-fixed shading means and what every caller wrote
    before the other three fields existed.

    **The other three are one study, so they arrive together or not at
    all.** ``residual_variance`` is σ̂²_0, what that regression left under
    the tracking; ``standard_error`` is se(δ̂); ``validation_df`` is the
    regression's degrees of freedom, one number for both because both come
    out of the same fit.

    **Why σ̂²_0 and not the total σ²_u**, which is what the classical
    declaration carries and what this route asked for. The two numbers a
    study reports have to be drawn from their JOINT distribution, and a
    regression's slope is independent of its residual variance under
    normality while it is NOT independent of the total ``Var(W − X*)``:
    σ̂²_u = σ̂²_0 + δ̂²·Var(Ỹ) is a function of δ̂ itself, so drawing the pair
    (δ̂, σ̂²_u) as though independent understates the interval by an amount
    that vanishes only at δ = 0. Declaring the remainder is what makes the
    draw exact, and it is also what the study actually printed — the total
    is the number a caller had to assemble by hand.

    **The draw**, under the same normal-replicate premise
    :class:`DeclaredVariance` already carries:

        σ²_0* = σ̂²_0 · df / X,                     X ~ χ²_df
        δ*    = δ̂ + se·√(σ²_0*/σ̂²_0)·Z,            Z ~ N(0, 1)

    which is δ̂ + se·t_df marginally, and jointly is the pair's own
    distribution rather than two margins pretending to be one. σ²_u is then
    composed per round as σ²_0* + δ*²·Var(Ỹ) — derived where it used to be
    declared, because under this declaration it is the derived one.

    Declaring no study consumes no randomness, so a run that declares none
    reproduces byte for byte what it produced before this class existed.
    """

    coefficient: float
    residual_variance: float | None = None
    standard_error: float | None = None
    validation_df: int | None = None

    def __post_init__(self) -> None:
        # At construction rather than at the estimator's door, for the reason
        # :class:`DeclaredVariance` validates there: this is the one place a
        # declaration becomes an object, so it is the one place that sees
        # every shape a caller can arrive in.
        df = self.validation_df
        if (df is None and self.residual_variance is None
                and self.standard_error is None):
            return
        whole = (df is not None and not isinstance(df, bool)
                 and isinstance(df, (int, float))
                 and float(df).is_integer() and df >= 1)
        positive = all(
            v is not None and not isinstance(v, bool)
            and isinstance(v, (int, float)) and np.isfinite(v) and v > 0
            for v in (self.residual_variance, self.standard_error)
        )
        if not (whole and positive):
            from ..refusals import EstimatorFailure, Refusal
            raise EstimatorFailure(
                Refusal.TRACKING_STUDY_NOT_USABLE,
                fields=list(TRACKING_STUDY_FIELDS),
                given={"coefficient": self.coefficient,
                       "standard_error": self.standard_error,
                       "residual_variance": self.residual_variance,
                       "validation_df": self.validation_df},
            )
        assert df is not None  # narrowed by ``whole``
        object.__setattr__(self, "validation_df", int(df))

    @property
    def studied(self) -> bool:
        """Whether a validation regression was declared behind δ.

        One reading of the three fields rather than three tests spread
        over the route: they arrive together, so "is there a study" is one
        question and a caller of this class must not have to know which of
        the three to ask it of.
        """
        return self.validation_df is not None

    @staticmethod
    def declared_value(given: object) -> object:
        """δ out of whichever shape a caller declared it in.

        The routing property and the guard that judges usability both need
        the coefficient and neither needs the study, and answering it here
        is what keeps a guard from refusing the SHAPE it did not recognise
        under wording about the coefficient.
        """
        if isinstance(given, DeclaredTracking):
            return given.coefficient
        if isinstance(given, Mapping):
            return given.get("coefficient")
        return given

    @classmethod
    def read(cls, given: object) -> "DeclaredTracking":
        """One of these from whatever a caller declared."""
        if isinstance(given, DeclaredTracking):
            return given
        if isinstance(given, Mapping):
            return cls(
                coefficient=float(given["coefficient"]),
                residual_variance=given.get("residual_variance"),
                standard_error=given.get("standard_error"),
                validation_df=given.get("validation_df"),
            )
        return cls(coefficient=float(given))  # type: ignore[arg-type]

    def draw(self, rng: np.random.Generator) -> tuple[float, float | None]:
        """One draw of (δ, σ²_0) from the study that measured them.

        Returns ``(δ, None)`` and consumes no randomness where no study was
        declared: there is no distribution to draw from, and σ²_0 is then
        the derived quantity rather than the declared one.

        The variance is drawn first and the slope rides on it, which is the
        joint law and not an ordering convention — se(δ̂) is σ̂_0 divided by
        the study's own spread in Ỹ, so a round that drew a larger σ²_0
        drew a study whose slope was that much less well pinned.
        """
        if not self.studied:
            return self.coefficient, None
        assert self.residual_variance is not None  # narrowed by ``studied``
        assert self.standard_error is not None
        assert self.validation_df is not None
        remainder = (self.residual_variance * self.validation_df
                     / rng.chisquare(self.validation_df))
        scale = np.sqrt(remainder / self.residual_variance)
        return (float(self.coefficient
                      + self.standard_error * scale * rng.standard_normal()),
                float(remainder))

    def premise(self, variable: str) -> str:
        """The ledger id this declaration carries, for one variable.

        The same branch :meth:`DeclaredVariance.premise` makes, made here
        rather than restated at the estimator, and for the reason given
        there: an estimator that writes the id itself takes the decision
        somewhere the declaration cannot reach.
        """
        settled = SETTLED_BY_A_STUDY if self.studied else SETTLED_EXACTLY
        return f"differential_coefficient_{settled}_on_{variable}"


#: The pseudo-count added to every cell of a validation tally before it
#: becomes a Dirichlet.
#:
#: Jeffreys' prior for a multinomial, and the reason is the zero cell. A
#: validation study of fifty subjects that never once recorded a case as a
#: control has not shown that the misrecording cannot happen; with the bare
#: count as the Dirichlet parameter that cell is drawn as exactly zero in
#: every replicate for ever, which is the one direction of overconfidence
#: this declaration exists to remove. One half is the standard
#: non-informative choice and the one that keeps a never-observed cell
#: possible without asserting a rate for it.
JEFFREYS = 0.5


@dataclass(frozen=True, eq=False)
class DeclaredMatrix:
    """A confusion matrix the caller declared, and the study that counted it.

    The variance one class up is a single number and this is a table of
    proportions, and that difference is the whole difference: what a
    validation study hands over here is not an estimate with degrees of
    freedom but a TALLY — so many subjects known to be at each true state,
    so many of them recorded at each state. The sampling distribution of a
    column of counts over its total is a Dirichlet, exactly as the
    distribution of a variance over its study is a χ², and each is what its
    own study actually measured.

    ``counts[i][j]`` is the number of validation subjects whose true state
    was ``states[j]`` and whose recorded state was ``states[i]``. The
    matrix is then the column-normalisation of that table and is not
    declared separately: a caller who supplies both is writing one fact
    twice, and the day the two disagree there is no answer to which one the
    correction used.

    ``counts is None`` is the claim that the matrix is exact — a coding rule
    with a known error rate, a device's published characteristics, a channel
    fixed by protocol. :meth:`draw` answers it by consuming no randomness,
    so a run that declares no study reproduces byte for byte what it
    produced before this class existed.

    **Why the draw and not a closed form.** The two routes that price
    somebody else's interval read quantiles directly, and SIMEX reads its
    curve at a computable point; here the correction is a matrix inversion
    standardised over strata, which is not monotone in anything a quantile
    could be taken of. The bootstrap is already running, and a study that
    can be redrawn inside it is carried exactly — so this is the first of
    the three ways, at the one route that has it.

    **A redrawn matrix can fail to invert, and that is a fact and not an
    accident.** A study small enough for its Dirichlet to reach a singular
    channel is a study that does not establish an invertible one; the draw
    is discarded under the species that names it, and the record of the
    discards says how often it happened — which is the reading a caller
    needs and is exactly what a fixed matrix could never report.
    """

    matrix: np.ndarray
    counts: "np.ndarray | None" = None

    @staticmethod
    def declared(given: object, *, what: str
                 ) -> tuple[object, "np.ndarray | None"]:
        """The matrix a caller declared and the tally behind it, out of
        whichever shape they declared it in.

        A bare matrix stays sugar for "known exactly", which is what every
        caller wrote before this class existed. A mapping is read for the
        tally, and the matrix comes out of it.

        Returns the pair rather than one of these, because the matrix is
        not judged yet: whether a k×k of numbers is a usable channel is the
        estimator's own guard, naming its own states and its own species,
        and one of these carries a matrix that guard has passed. So the
        shapes are unwrapped here — where the shapes are known — and the
        object is built where the judgement is made.

        ``what`` names the channel in a rejection, for the reason the
        estimator's guard takes the same argument: a correction with a
        matrix on each side rejects one of them, and a reader who is not
        told which has been told nothing.
        """
        if isinstance(given, DeclaredMatrix):
            return given.matrix, given.counts
        if not isinstance(given, Mapping):
            return given, None
        counts = np.asarray(
            DeclaredMatrix._usable_counts(given, what=what), dtype=float)
        return counts / counts.sum(axis=0), counts

    @staticmethod
    def _usable_counts(given: Mapping, what: str) -> object:
        """The tally out of a declaration, or a refusal naming what is wrong.

        Judged here rather than where the matrix is, because a tally is not
        a matrix: the faults it can have are its own (a negative count, a
        true state nobody was observed at) and the normalisation that turns
        it into a matrix would hide both — a column of zeros divides into
        NaN, which the matrix guard then rejects as "not finite", under
        wording about a matrix the caller never wrote.
        """
        from ..refusals import EstimatorFailure, Refusal, Remedy

        raw = given.get("validation_counts")
        try:
            counts = np.asarray(raw, dtype=float)
        except (TypeError, ValueError):
            counts = None
        if (counts is None or counts.ndim != 2 or counts.size == 0
                or not np.isfinite(counts).all() or (counts < 0).any()):
            raise EstimatorFailure(
                Refusal.VALIDATION_COUNTS_UNUSABLE, what=what, given=raw,
                remedies=[(Remedy.CHANGE_INPUT, "validation_counts")])
        empty = [int(j) for j in np.flatnonzero(counts.sum(axis=0) <= 0)]
        if empty:
            raise EstimatorFailure(
                Refusal.VALIDATION_STATE_NEVER_OBSERVED,
                what=what, columns=empty,
                remedies=[(Remedy.SUPPLY_INPUT, "validation_counts")])
        return counts

    @property
    def measured(self) -> bool:
        """Whether a study counted this matrix, rather than a caller fixing it."""
        return self.counts is not None

    @property
    def study_sizes(self) -> tuple[int, ...]:
        """How many validation subjects stood at each true state, in column
        order — empty where no study was declared."""
        if self.counts is None:
            return ()
        return tuple(int(round(float(c))) for c in self.counts.sum(axis=0))

    def as_lists(self) -> list | None:
        """The tally as a record carries it, or ``None`` where there is none."""
        if self.counts is None:
            return None
        return [[float(v) for v in row] for row in self.counts]

    def draw(self, rng: np.random.Generator) -> np.ndarray:
        """One draw of what this matrix could have been.

        Each column independently, because each column is its own
        multinomial: the validation subjects known to be at true state j are
        a separate sample from those at any other state, and a study that
        enrolled fifty of one and five of another knows the two columns that
        differently. Consumes no randomness where nothing was counted.
        """
        if self.counts is None:
            return self.matrix
        alpha = self.counts + JEFFREYS
        return np.column_stack([
            rng.dirichlet(alpha[:, j]) for j in range(alpha.shape[1])
        ])

    def premise(self, family: str, variable: str) -> str:
        """The ledger id this declaration carries, for one variable.

        The same branch, in the same words, as the one a declared variance
        carries — see :meth:`DeclaredVariance.premise` for why it lives on
        the declaration and not at the estimators that read it.
        """
        settled = SETTLED_EXACTLY if self.counts is None else SETTLED_BY_A_STUDY
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

    **``requested`` is the run's number, and it arrives here by the name
    it has everywhere else.** Nothing forwards it — dispatch hands each
    estimator the settings the caller gave, keyword by keyword, so a
    parameter spelled differently from the run's is not a wire that breaks
    loudly but a wire that was never drawn: the call site simply has no
    such argument, the estimator's own default wins, and the envelope goes
    on recording what the caller asked for beside an interval built on
    something else. Two loops here were spelled ``n_rep`` and every
    mediation interval this system ever reported stood on two hundred
    draws — under a caller who asked for five hundred, and under one who
    asked for none at all, which this system documents as the way to skip
    the interval. The source gate that holds every draw site to this class
    reads the argument as well as the loop, so the next estimator to name
    it something else fails there rather than shipping an interval nobody
    asked for.
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

    def declares(self, *, cluster: str | None) -> tuple[str, ...]:
        """What an interval made THIS way lets its estimator claim about it.

        The other half of :meth:`record`, and it exists because the two
        were not halves of anything: the block below is written from what
        the loop did, and the registered sentence beside it on the envelope
        was written from ``cluster is not None`` — a fact settled before any
        loop runs, at thirty-seven of the forty-four places a
        confidence-layer sentence is decided. None of the forty-four asked
        whether the loop ran, so the sentence was wrong in both directions
        at once: a run given a cluster column and asked for no interval
        declared "the interval was obtained by resampling whole clusters"
        beside an answer that has no interval, and a run that DID resample —
        without a cluster column, so nothing named it — reported an interval
        with no account of how it was made at all.

        Reading the loop rather than the arguments is what makes both
        halves one answer. ``None`` draws is no loop; :attr:`enough` is this
        package's own predicate for "an interval may be reported at all",
        so a loop that ran and lost too many replicates says nothing either
        — there is nothing on the page for a sentence to be about.

        The cluster id is a refinement and not a replacement: an interval
        from whole-cluster resampling IS a percentile bootstrap, and the
        one family that already branched on how its interval was made
        (:mod:`themis.estimation.aipw`) said both. Saying only the second
        left every unclustered bootstrap silent, which is the half nobody
        had noticed.
        """
        if not self.enough:
            return ()
        said: tuple[str, ...] = ("ci_via_percentile_bootstrap",)
        if cluster is not None:
            said += (f"ci_via_pairs_cluster_bootstrap_on_{cluster}",)
        return said

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


def declared_by(draws: "Draws | None", *, cluster: str | None
                ) -> tuple[str, ...]:
    """:meth:`Draws.declares`, with "no loop at all" in one place.

    Every estimator spells the absent loop the same way — ``Draws(n) if n >
    0 else None`` — so ``draws is None`` IS the run that asked for no
    interval. Written here rather than at each of the call sites, because
    a conditional repeated per family is how the previous version of this
    sentence came to be repeated per family and then to differ.
    """
    return () if draws is None else draws.declares(cluster=cluster)


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
