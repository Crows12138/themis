"""What ``se_inflation`` claims, checked against what actually happens.

``assess_outcome_error`` reports one number per design — the factor by which a
declared classical outcome error σ²_v widens the interval. That number is a
claim about a sampling distribution, and the only way to check a claim about a
sampling distribution is to draw from it. Every oracle here simulates a clean
latent outcome and a noisy observed one **from the same draws**, so the two
arms differ in the error and in nothing else, and then measures the precision
loss the way the design's own inference measures it:

- BACK_DOOR — the ratio of OLS standard errors on the same design matrix. The
  claim is EQUALITY, and it is an algebraic identity rather than a limit: when
  the realised error is orthogonal to the design in-sample, the reported factor
  and the standard-error ratio agree to machine precision.
- INSTRUMENTAL_VARIABLE — the ratio of the spread of the IV point estimate
  across independently drawn samples. The claim is again EQUALITY, but only in
  the limit, so the tolerance here is a Monte-Carlo budget rather than a
  rounding allowance: it is set from the measured spread of the instrument, and
  the test also shows that it is tight enough to reject the wrong residual.
- FRONT_DOOR — the claim is an INEQUALITY. The efficient influence function
  (Guo, Benkeser & Nabi, arXiv:2312.10234, Eq. 4) puts the outcome residual in
  one term only, so σ²_v inflates a part of the variance rather than all of it
  and the scalar factor is a CEILING. Asserting equality here would assert
  something false, so the tests assert the direction and that the ceiling is
  above a cost that is itself real.

The arithmetic in this file — OLS, 2SLS, the replicate studies — is written
here rather than imported, for the reason the verifier never imports the
estimator: an oracle that shares its arithmetic with the producer cannot
contradict it. The one thing that IS imported is the front-door estimator
itself, because the front-door claim is about the interval that estimator
reports, and re-implementing it would be checking a different estimator.

**Why the front-door claim is carried by two different instruments.** The
bootstrap CI width is what a reader actually sees, but its endpoints are tail
quantiles of a few hundred resamples, so the width RATIO carries roughly 6%
Monte-Carlo error at any bootstrap size this suite can afford — comparable to
the gap being asserted on a representative design. So the tight comparison is
made against the sampling spread over fresh replicates, which estimates the
same quantity with a fraction of the noise, and the reader-visible interval is
checked separately on a design whose gap is wide enough that no bootstrap draw
can cross it.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
import pytest

from themis.estimation import assess_outcome_error, OutcomeErrorDesign
from themis.estimation.frontdoor import estimate_frontdoor_ate


# --- independent arithmetic ----------------------------------------------------


def _ols_slope_se(y: np.ndarray, X: np.ndarray) -> float:
    """The homoskedastic standard error of the first slope in ``X``.

    The factor being checked is defined as a ratio of these, so the divisor
    convention cancels and only the residual sum of squares matters.
    """
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ b
    s2 = resid @ resid / (len(y) - X.shape[1])
    return float(np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X))[1]))


def _partial_out(column: np.ndarray, exog: np.ndarray) -> np.ndarray:
    """Residual of ``column`` on ``exog``, the sample running along the last
    axis and any leading axes batching whole replicates.

    Batched because the IV oracle's precision is set by how many replicates it
    can draw, and a per-replicate Python loop would price that in seconds.
    """
    gram = np.einsum("...nk,...nl->...kl", exog, exog)
    moment = np.einsum("...nk,...n->...k", exog, column)
    coef = np.linalg.solve(gram, moment[..., None])[..., 0]
    return column - np.einsum("...nk,...k->...n", exog, coef)


def _wald_estimate(z, x, y, exog) -> np.ndarray:
    """The just-identified 2SLS point, Cov(Z,Y)/Cov(Z,X) after the exogenous
    block is partialled out of the instrument."""
    zr = _partial_out(z, exog)
    return (zr * y).sum(-1) / (zr * x).sum(-1)


def _exogenous_block(shape: tuple[int, ...], w: np.ndarray, covariate: bool):
    ones = np.ones(shape)
    return np.stack([ones, w], axis=-1) if covariate else ones[..., None]


# --- BACK_DOOR: the factor IS the standard-error ratio -------------------------


_BACKDOOR_SIGMA_V = 4.0
# The clean outcome's own residual variance, known exactly because the sample
# below is built with it. The plain-draw tolerance is derived from it rather
# than chosen, so it cannot drift into being a number that happens to pass.
_BACKDOOR_SIGNAL_VARIANCE = 1.0


def _backdoor_sample(n: int, seed: int, *, orthogonal: bool):
    """z → x → y with z → y, plus a latent clean outcome the engine never sees.

    ``orthogonal`` replaces the error draw with one that is exactly orthogonal
    to the design and to the clean residual, and scaled to exactly the declared
    variance. That is still a perfectly ordinary classical error — uncorrelated
    with everything, mean zero, the declared variance — but it removes the
    finite-sample slack between the declared σ²_v and the realised one, which
    is the only thing standing between the reported factor and the standard-
    error ratio. What is left is the algebraic identity itself.
    """
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = 0.5 * z + rng.normal(size=n)
    ystar = (
        0.3 + 0.8 * x + 1.0 * z
        + rng.normal(0, np.sqrt(_BACKDOOR_SIGNAL_VARIANCE), n)
    )
    X = np.column_stack([np.ones(n), x, z])

    if orthogonal:
        b, *_ = np.linalg.lstsq(X, ystar, rcond=None)
        basis = np.column_stack([X, ystar - X @ b])
        raw = rng.normal(size=n)
        c, *_ = np.linalg.lstsq(basis, raw, rcond=None)
        v = raw - basis @ c
        v *= np.sqrt(_BACKDOOR_SIGMA_V * (n - 1) / (v @ v))
    else:
        v = rng.normal(0, np.sqrt(_BACKDOOR_SIGMA_V), n)

    return pd.DataFrame({"x": x, "z": z, "y": ystar + v}), ystar, X


def _backdoor_factor(df: pd.DataFrame, error_variance: float) -> float:
    return assess_outcome_error(
        df, treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.BACK_DOOR,
        adjustment=("z",), error_variance=error_variance,
    ).se_inflation


def test_the_back_door_factor_is_the_ols_standard_error_ratio_exactly():
    """No tolerance worth the name: the two agree to machine precision.

    A relative band of 1e-9 is nine orders below the ~1% finite-sample slack an
    ordinary error draw carries, so it can only be met by the identity holding,
    not by a near miss.
    """
    df, ystar, X = _backdoor_sample(4_000, 7, orthogonal=True)
    reported = _backdoor_factor(df, _BACKDOOR_SIGMA_V)
    measured = _ols_slope_se(df["y"].to_numpy(), X) / _ols_slope_se(ystar, X)

    assert abs(reported / measured - 1.0) < 1e-9, (reported, measured)

    # The band above is not vacuous: it is crossed by a σ²_v that is wrong by a
    # single percent, which is far finer than anything a validation study
    # resolves. So the test is checking the identity, not the arithmetic's
    # ability to land somewhere near.
    misdeclared = _backdoor_factor(df, _BACKDOOR_SIGMA_V * 0.99)
    assert abs(misdeclared / measured - 1.0) > 1e-3, misdeclared


@pytest.mark.parametrize("seed", [0, 3, 11])
def test_the_back_door_factor_holds_under_an_ordinary_error_draw(seed):
    """The identity survives an error the sample was not built to flatter.

    An unconstrained draw reintroduces exactly what the orthogonal one removed:
    the realised error variance misses the declared σ²_v, and the error is not
    quite uncorrelated with the clean residual in-sample. Both enter the split
    at O(n^-1/2), with

        Var(residual_noisy − residual_clean) = (2σ⁴_v + 4σ²_v σ²_*) / n,

    and the factor is a square root of a ratio to σ²_*, so the relative
    discrepancy has half that standard deviation over σ²_*. The band is four of
    those, WRITTEN OUT rather than measured off the seeds — a budget derived
    from the design cannot quietly become a budget fitted to the outcome.
    """
    n = 200_000
    df, ystar, X = _backdoor_sample(n, seed, orthogonal=False)
    reported = _backdoor_factor(df, _BACKDOOR_SIGMA_V)
    measured = _ols_slope_se(df["y"].to_numpy(), X) / _ols_slope_se(ystar, X)

    spread = 0.5 * np.sqrt(
        (2 * _BACKDOOR_SIGMA_V ** 2
         + 4 * _BACKDOOR_SIGMA_V * _BACKDOOR_SIGNAL_VARIANCE) / n
    ) / _BACKDOOR_SIGNAL_VARIANCE

    assert abs(reported / measured - 1.0) < 4.0 * spread, (reported, measured)


# --- INSTRUMENTAL_VARIABLE: the factor IS the spread of the point --------------


_IV_SIGMA_V = 4.0
_IV_REPLICATES = 8_000
_IV_REPLICATE_N = 1_500
_IV_BLOCK = 500
# Four percent. The replicate study's own spread is about 1% at this many
# replicates and the reported factor's sampling error at n = 200,000 about half
# of that, so the band is roughly four combined standard deviations — and the
# realised miss is 1.3%. It also sits well inside the 7.9% by which the WRONG
# residual — the OLS projection rather than the structural one — misses, which
# is the test that keeps the band from being merely generous.
_IV_TOLERANCE = 0.04


def _iv_draw(rng, shape, *, covariate: bool):
    """A confounded exposure with a strong excluded instrument.

    The confounder u sits in the structural residual, which is exactly why the
    IV route cannot take its residual around an OLS projection: the projection
    absorbs u and reports a smaller residual than the sandwich actually carries.
    """
    z = rng.normal(size=shape)
    u = rng.normal(size=shape)
    w = rng.normal(size=shape)
    x = 1.0 * z + u + rng.normal(size=shape) + (0.6 * w if covariate else 0.0)
    ystar = (
        0.3 + 0.8 * x + 1.0 * u + rng.normal(size=shape)
        + (0.7 * w if covariate else 0.0)
    )
    return z, x, w, ystar, ystar + rng.normal(0, np.sqrt(_IV_SIGMA_V), shape)


def _iv_reported(n: int, seed: int, *, covariate: bool) -> float:
    rng = np.random.default_rng(seed)
    z, x, w, _, y = _iv_draw(rng, (n,), covariate=covariate)
    exog = _exogenous_block((n,), w, covariate)
    beta = float(_wald_estimate(z, x, y, exog))
    columns = {"z": z, "x": x, "y": y} | ({"w": w} if covariate else {})
    return assess_outcome_error(
        pd.DataFrame(columns), treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.INSTRUMENTAL_VARIABLE,
        adjustment=("w",) if covariate else (),
        instruments=("z",), treatment_coefficient=beta,
        error_variance=_IV_SIGMA_V,
    ).se_inflation


# Cached because the spread of the point and the invariance of the point are
# two readings of ONE study, and drawing it twice would cost the suite time to
# produce a second set of numbers that must agree with the first.
@lru_cache(maxsize=None)
def _iv_replicates(seed: int, covariate: bool):
    """Clean and noisy IV points over independently drawn samples, paired.

    Paired on the draw rather than run as two independent studies, because the
    two claims being checked pull in opposite directions: the ratio of spreads
    needs the shared component to cancel, and the invariance of the POINT is a
    statement about the difference, which only exists when the samples match.
    """
    rng = np.random.default_rng(seed)
    clean, noisy = [], []
    drawn = 0
    while drawn < _IV_REPLICATES:
        k = min(_IV_BLOCK, _IV_REPLICATES - drawn)
        shape = (k, _IV_REPLICATE_N)
        z, x, w, ystar, y = _iv_draw(rng, shape, covariate=covariate)
        exog = _exogenous_block(shape, w, covariate)
        clean.append(_wald_estimate(z, x, ystar, exog))
        noisy.append(_wald_estimate(z, x, y, exog))
        drawn += k
    return np.concatenate(clean), np.concatenate(noisy)


@pytest.mark.parametrize("covariate", [False, True], ids=["bare", "covariate"])
def test_the_instrumental_variable_factor_is_the_spread_of_the_iv_point(covariate):
    """The 2SLS sandwich's additive σ²_v penalty, measured.

    Both arms are exercised because they are different code: without a
    covariate the supplied β̂ IS the whole coefficient vector, with one the
    remaining coefficients are solved by OLS on the non-exposure block, and
    only the second can be singular.
    """
    clean, noisy = _iv_replicates(2_024, covariate)
    reported = _iv_reported(200_000, 101, covariate=covariate)
    measured = float(noisy.std(ddof=1) / clean.std(ddof=1))

    assert abs(reported / measured - 1.0) < _IV_TOLERANCE, (reported, measured)


@pytest.mark.parametrize("covariate", [False, True], ids=["bare", "covariate"])
def test_the_outcome_error_leaves_the_iv_point_where_it_was(covariate):
    """The premise that makes the factor the WHOLE cost.

    E[Ze] = 0 survives Y = Y* + V when E[ZV] = 0, so the difference between the
    two arms has mean exactly zero — not approximately, conditionally on the
    design. A paired study therefore measures its own standard error, and four
    of those is a real bound rather than a shrug.
    """
    clean, noisy = _iv_replicates(2_024, covariate)
    shift = noisy - clean
    standard_error = shift.std(ddof=1) / np.sqrt(len(shift))

    assert abs(shift.mean()) < 4.0 * standard_error, (shift.mean(), standard_error)


def test_the_tolerance_rejects_the_residual_the_iv_route_must_not_take():
    """The input the IV oracle has to say NO to.

    Had the structural residual been replaced by the OLS projection of Y on the
    design — the back-door arithmetic applied to an IV query — the confounder
    would have been absorbed into the fit instead of left in the residual, and
    the split would have priced a model nobody estimated. That factor misses the
    measured spread by more than the tolerance above, which is what makes the
    tolerance a Monte-Carlo budget rather than a place for a wrong formula to
    sit unnoticed.
    """
    clean, noisy = _iv_replicates(2_024, False)
    measured = float(noisy.std(ddof=1) / clean.std(ddof=1))

    rng = np.random.default_rng(101)
    z, x, _w, _ystar, y = _iv_draw(rng, (200_000,), covariate=False)
    wrong = assess_outcome_error(
        pd.DataFrame({"z": z, "x": x, "y": y}), treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.BACK_DOOR, error_variance=_IV_SIGMA_V,
    ).se_inflation

    assert abs(wrong / measured - 1.0) > _IV_TOLERANCE, (wrong, measured)


# --- FRONT_DOOR: the factor is a CEILING --------------------------------------


_FRONTDOOR_SIGMA_V = 4.0
_FRONTDOOR_REPLICATES = 2_000
_FRONTDOOR_REPLICATE_N = 1_200


def _frontdoor_sample(n: int, rng, *, sigma_v: float, quiet: bool):
    """x → m → y with an unmeasured u confounding x and y — the front-door graph.

    Two settings of the one graph. ``quiet`` shrinks the outcome's own residual
    and the confounding without shrinking what the mediator model contributes
    to the influence function, so the term σ²_v inflates shrinks relative to
    the terms it does not, and the ceiling stands further above the truth. That
    setting exists for the arm whose instrument is too noisy to resolve a
    narrow gap, and for nothing else.
    """
    effect, confounding, outcome_sd, m_given_x, m_given_not_x = (
        (2.0, 0.25, 0.2, 0.85, 0.15) if quiet else (1.5, 1.1, 1.0, 0.8, 0.25)
    )
    u = rng.normal(size=n)
    x = rng.random(n) < 1.0 / (1.0 + np.exp(-1.2 * u))
    m = rng.random(n) < np.where(x, m_given_x, m_given_not_x)
    ystar = (
        0.4 + effect * m.astype(float) + confounding * u
        + rng.normal(0, outcome_sd, n)
    )
    return pd.DataFrame(
        {"x": x, "m": m, "y": ystar + rng.normal(0, np.sqrt(sigma_v), n),
         "ystar": ystar},
    )


def _frontdoor_reported(n: int, seed: int, *, sigma_v: float, quiet: bool) -> float:
    df = _frontdoor_sample(n, np.random.default_rng(seed), sigma_v=sigma_v, quiet=quiet)
    return assess_outcome_error(
        df[["x", "m", "y"]], treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.FRONT_DOOR,
        mediators=("m",), error_variance=sigma_v,
    ).se_inflation


def _frontdoor_point(df: pd.DataFrame, outcome: str) -> float:
    return estimate_frontdoor_ate(
        df[["x", "m", outcome]], treatment="x", outcome=outcome,
        mediators=("m",), ci_bootstrap=0,
    ).point


@lru_cache(maxsize=None)
def _frontdoor_replicates(seed: int):
    rng = np.random.default_rng(seed)
    clean, noisy = [], []
    for _ in range(_FRONTDOOR_REPLICATES):
        df = _frontdoor_sample(
            _FRONTDOOR_REPLICATE_N, rng,
            sigma_v=_FRONTDOOR_SIGMA_V, quiet=False,
        )
        clean.append(_frontdoor_point(df, "ystar"))
        noisy.append(_frontdoor_point(df, "y"))
    return np.array(clean), np.array(noisy)


def test_the_front_door_factor_is_strictly_above_the_true_precision_cost():
    """The number is a ceiling, and the test asserts the ceiling.

    The reported factor is read off a large sample so that its own sampling
    error does not enter the comparison; the truth is the ratio of sampling
    spreads over fresh replicates, whose own spread at this many replicates is
    about 1.7%. The realised gap is 8.3% — some five standard deviations, so
    the direction is not a coincidence of the draw. Asserting equality here, as
    the back-door and IV routes do, would be asserting something the influence
    function says is false.
    """
    clean, noisy = _frontdoor_replicates(31)
    reported = _frontdoor_reported(
        40_000, 5, sigma_v=_FRONTDOOR_SIGMA_V, quiet=False,
    )
    measured = float(noisy.std(ddof=1) / clean.std(ddof=1))

    assert reported > measured, (reported, measured)
    # A ceiling over nothing would also satisfy the line above. The error has
    # to be costing real precision for the bound to be a bound on anything.
    assert measured > 1.2, measured
    # And a ceiling far above the truth would be useless rather than wrong.
    # Pinning the overstatement to this DGP's measured size keeps a future
    # change that loosens the bound into uselessness from passing quietly.
    assert reported < 1.35 * measured, (reported, measured)


def test_the_outcome_error_leaves_the_front_door_point_where_it_was():
    """Why the ceiling is a ceiling on the whole cost.

    V independent of the latent confounder keeps E[V | A, M, X] = 0, so the
    mediator-conditional means the front-door sum is built from do not move. If
    this failed the point would move and no precision factor, exact or bounding,
    would describe what the error cost.
    """
    clean, noisy = _frontdoor_replicates(31)
    shift = noisy - clean
    standard_error = shift.std(ddof=1) / np.sqrt(len(shift))

    assert abs(shift.mean()) < 4.0 * standard_error, (shift.mean(), standard_error)


@pytest.mark.parametrize("bootstrap_seed", [3, 4, 5])
def test_the_front_door_bound_holds_over_the_interval_the_reader_is_shown(
    bootstrap_seed,
):
    """The same inequality, against the estimator's own bootstrap interval.

    This is the width a reader actually sees, so the claim has to survive it —
    but the width's endpoints are tail quantiles of a few hundred resamples and
    the ratio of two of them carries roughly 6% Monte-Carlo error, which is the
    size of the gap on a representative design. So this arm runs on the design
    whose influence function splits most lopsidedly, where the ceiling sits
    about 80% above the truth and no bootstrap draw can reach it; the tight
    comparison is the replicate study above. Several bootstrap seeds, because a
    single one would be one draw from exactly the noise just described.
    """
    df = _frontdoor_sample(
        1_200, np.random.default_rng(5), sigma_v=1.0, quiet=True,
    )
    reported = _frontdoor_reported(1_200, 5, sigma_v=1.0, quiet=True)

    def width(outcome: str) -> float:
        estimate = estimate_frontdoor_ate(
            df[["x", "m", outcome]], treatment="x", outcome=outcome,
            mediators=("m",), ci_bootstrap=500, random_state=bootstrap_seed,
        )
        return estimate.ci_upper - estimate.ci_lower

    measured = width("y") / width("ystar")

    assert measured > 1.0, measured
    assert reported > measured, (reported, measured)


# --- the span the front-door residual is taken around --------------------------


def _three_level_mediator_sample(n: int, seed: int) -> pd.DataFrame:
    """A mediator whose effect on the outcome is not linear in its level codes.

    Binary mediators cannot show the difference — one indicator spans exactly
    what the raw column spans — so the claim that the design is built on the
    indicators is only observable where the levels carry a shape a single slope
    cannot follow.
    """
    rng = np.random.default_rng(seed)
    u = rng.normal(size=n)
    x = rng.random(n) < 1.0 / (1.0 + np.exp(-1.2 * u))
    m = np.where(
        x,
        rng.choice([0, 1, 2], size=n, p=[0.2, 0.3, 0.5]),
        rng.choice([0, 1, 2], size=n, p=[0.6, 0.25, 0.15]),
    )
    ystar = 0.4 + np.array([0.0, 2.0, 0.5])[m] + 0.9 * u + rng.normal(0, 0.5, n)
    return pd.DataFrame(
        {"x": x, "m": m.astype(float), "y": ystar + rng.normal(size=n)},
    )


def test_the_front_door_residual_is_taken_around_the_indicator_span():
    """The coarser span understates the cost, which is the wrong direction.

    Fitting the residual around the raw mediator column instead of the
    indicators the front-door outcome model actually spans leaves the level
    shape in the residual, inflates it, and reports a SMALLER precision cost
    than the design really pays. Here that understatement is over ten percent —
    invisible on a binary mediator and material on any other.
    """
    df = _three_level_mediator_sample(4_000, 5)

    expanded = assess_outcome_error(
        df, treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.FRONT_DOOR,
        mediators=("m",), error_variance=1.0,
    )
    raw_column = assess_outcome_error(
        df, treatment="x", outcome="y",
        design_kind=OutcomeErrorDesign.BACK_DOOR,
        adjustment=("m",), error_variance=1.0,
    )

    assert expanded.design_vars == ("x", "m=1.0", "m=2.0")
    assert raw_column.design_vars == ("x", "m")
    assert expanded.residual_variance < raw_column.residual_variance
    assert expanded.se_inflation > 1.05 * raw_column.se_inflation, (
        expanded.se_inflation, raw_column.se_inflation,
    )
