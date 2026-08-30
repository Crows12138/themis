"""SIMEX — the de-attenuation that works where the moment correction does not.

:mod:`themis.estimation.regression_calibration` corrects a continuously
mismeasured exposure by an EXACT moment identity, and the identity holds
because the outcome model is linear: classical error inflates only the
mismeasured columns' variances, so ``β_true = (Σ_obs − E)⁻¹ Cov(D, Y)``.
Under a logistic outcome that algebra is simply false — the attenuation is
not a linear map of the covariance — and the module said so and deferred
the alternative:

    SIMEX in particular is a simulation-extrapolation heuristic (a tuned
    extrapolant, not a closed form), so it does not fit the per-number
    re-derivation contract and is out of scope.

**That reason treats SIMEX as one thing, and it is two.** Cook & Stefanski
(1994) is a simulation stage followed by an extrapolation stage:

1. *Simulate.* For each λ on a declared grid, add sqrt(λ)·σ_u of fresh
   noise to the already-noisy exposure B times, refit the naive estimator
   on each, and average: θ̂(λ). Total error variance is now (1+λ)σ²_u, so
   this traces out how the estimate decays as the measurement gets worse.
2. *Extrapolate.* Fit a declared function through {(λ_k, θ̂_k)} and
   evaluate it at λ = −1, which is where the total error variance would
   be zero.

Only the first stage is random, **and its output is the second stage's
sufficient statistic.** The grid travels on the envelope, and everything
downstream of it — the extrapolant's coefficients, the point at λ = −1,
the variance, the interval — is a closed-form least-squares problem that
:func:`themis.verify_simex_numeric` recomputes without simulating
anything. What cannot be re-derived is stated rather than implied: the
grid itself comes from a seeded Monte Carlo, reproducible from the seed
but not recomputable by a second author.

**The extrapolant is declared, not tuned.** Three families (Cook &
Stefanski's own): ``linear`` γ0+γ1λ, ``quadratic`` γ0+γ1λ+γ2λ², and
``rational`` γ0+γ1/(γ2+λ). The rational one is fitted by the
linearisation that makes it a LINEAR least-squares problem — from
θ·(γ2+λ) = γ0(γ2+λ)+γ1, regress θ·λ on (λ, 1, −θ) — rather than by
nonlinear least squares. Two reasons, and neither is convenience: a
closed form is re-derivable where an optimiser's exit point is not, and
where the rational model holds EXACTLY the residuals are zero, so the two
fits coincide there.

The default is ``rational``, and the literature's usual default is
``quadratic``. That is a measured disagreement rather than a preference:
over six configurations (both outcome models × σ²_u ∈ {0.25, 0.5, 1.0},
eight samples each) rational removes 91–99% of the naive bias where
quadratic removes 46–87% and linear 18–52%, and the gap widens with the
error variance — exactly where a correction is worth having. The usual
reason to prefer quadratic is that the rational fit can put its pole where
the answer is read; that is a real failure and it has a guard of its own
rather than a default chosen to avoid meeting it.

**The linear outcome is not a use case here; it is the test.** Under a
linear outcome the naive slope decays exactly as
θ(λ) = θ_naive·Var(W|Z)/(Var(W|Z)+λσ²_u) — a rational function — so SIMEX
with the rational extrapolant must reproduce the moment correction that
:mod:`regression_calibration` computes in closed form. That gives this
module a true-value oracle for the whole pipeline, simulation stage
included, which a nonlinear outcome could never provide. It is offered as
``outcome_model="linear"`` for exactly that reason.

**The interval comes from the same extrapolation the point does.**
Stefanski & Cook's (1995) variance: at each λ the simulation already
yields the mean of the naive variance estimates σ̄²(λ) and the sample
variance of the replicate estimates s²(λ), and τ(λ) = σ̄²(λ) − s²(λ)
extrapolates to λ = −1 the same way θ does. So no bootstrap wraps the
whole procedure, and the interval is re-derived from the same grid as the
point. When the extrapolated variance comes back non-positive — which the
subtraction genuinely permits — there is no interval and the envelope
says which of the two terms was larger, rather than clipping to zero and
reporting a number. That is the measured cost of the default rather than
a theoretical one: over twelve samples per configuration the linear and
quadratic families produced an interval every time and the rational one
did so ten times in twelve. It is a price worth paying for a point that
is right, and the two times it is paid the reader is told.

**σ²_u is usually somebody's measurement too, and λ = −1 is where you
read the curve only if it was exact.** The ladder simulates with the
DECLARED σ̂²_u, so the rung at λ carries total error variance σ² + λσ̂²_u
where σ² is the truth. Setting that to zero gives λ = −σ²/σ̂²_u, and λ = −1
is that point under the assumption σ̂²_u = σ². Where a validation study
estimated σ̂²_u with ``validation_df`` degrees of freedom, classical
additive error with normal replicates makes σ̂²_u·df/σ² ~ χ²_df, so the
reading point has an EXACT distribution of its own:

    λ* = −σ²/σ̂²_u = −df / X,   X ~ χ²_df

**So the validation study's uncertainty is uncertainty about where on the
extrapolant to read the answer**, and the answer's distribution is the
sampling normal N(θ̂(λ*), τ(λ*)) mixed over that. The interval is the
central 1−α region of the mixture, which reduces to the ± z√τ(−1) above
exactly as df → ∞. The literature's route to the same place is the
stacked-estimating-equation sandwich (Carroll, Ruppert, Stefanski &
Crainiceanu 2006, ch. 5), which prices the same extra parameter to first
order; this is the same identity read exactly, and it costs no
simulation — the mixing distribution is closed-form and the extrapolants
are already fitted, so the whole interval stays re-derivable by a second
author from the recorded coefficients alone.

Measured, on the linear-outcome oracle where the rational extrapolant is
exact (n=800, σ²_u=0.25, 80 samples per row, 300 replicates a rung):
holding σ̂²_u fixed the interval's width does not depend on the study at
all, and its coverage falls from 117/120 at df=400 to 79/118 at df=9.
Reading at λ* instead: 72/74, 71/74, 73/75, 72/75, 66/67 at
df = 200, 100, 49, 24, 9, with the width climbing 0.199 → 0.858.

**τ is held at λ = −1 while the reading point moves, and that is a
declared approximation.** τ(λ) is an extrapolation of a difference of two
estimated variances, and reading it away from the one point this module
vouches for turned out to be governed by where its own fitted pole
happened to land rather than by anything about the data: at df=24 that
variant withheld 41 of 80 intervals where holding τ at −1 withheld 5, and
covered 36/39 against 72/75. Holding it understates the conditional
variance below −1 and overstates it above; the measurement says the net is
conservative. What carries the study is the mean shift, and that is read
exactly.

**Where the study reaches past the ladder, it says so rather than
truncating.** λ* < −γ2 on the rational family is σ² at or above the
exposure's whole observed spread — an error variance the observed data
itself rules out. λ* = −df/X lands there exactly when X ≤ df/γ2, so the
share is χ²_df.cdf(df/γ2) in closed form: a property of the caller's study
and this data, not of the quadrature. When it reaches the tail an endpoint
stands for (α/2), there is no interval and the reason names the number;
below that, the interval conditions on the readable part exactly and the
share says how much was left out. The one thing not done is inventing a
value at a σ² the data contradicts.

A declared cluster column leaves by that same door. Every variance on the
ladder is the fitter's own, and a model-based variance is a statement
about independent rows; a caller who names a cluster has said they are
not. There is no cluster-robust form of the Stefanski-Cook subtraction
here, so the interval is withheld and says which premise it would have
needed. The point is untouched — clustering costs precision, not
identification — and withholding is what keeps that distinction visible
instead of burying it in a width.

**And what that interval does NOT cover is an assumption, not a caveat.**
It covers sampling variability and the simulation's own noise. It does
not cover the extrapolant's approximation error, because that is a bias
and no variance sees a bias. Measured: at σ²_u = 0.25 the rational
extrapolant's residual bias is under 1% of the effect and the interval
covers the truth 15 times in 16; at σ²_u = 1.0 the residual bias is about
the interval's half-width and coverage falls to 6 in 16. The assumption
ledger carries that as a declared row rather than a footnote, because a
reader comparing this interval with a bootstrap one is comparing two
different things.

Scope (declared):

- ONE continuously mismeasured EXPOSURE with known classical additive
  error variance σ²_u. Several mismeasured columns at once is the moment
  correction's shape, not this one's: SIMEX perturbs a variable, and
  perturbing two jointly needs their error covariance, which a per-column
  variance does not carry.
- The estimand is the exposure's coefficient in the outcome model — a
  conditional log-odds ratio per unit of the TRUE exposure under
  ``logistic``, a conditional slope under ``linear``. Not a risk
  difference: turning a coefficient into one needs a contrast and a
  standardisation the caller did not ask for, and it is the coefficient
  that the measurement-error literature de-attenuates.
- This is classical additive error, as everywhere in this family, and the
  other two structures keep the row off rather than bending it. A declared
  BERKSON structure does so for a stronger reason than scope: simulation
  adds noise to a column in order to see where the attenuation curve came
  FROM, and under Berkson error there was no attenuation to extrapolate
  back through. A declared DIFFERENTIAL coefficient does so because the
  ladder would be wrong at every rung: adding noise that does not track the
  outcome makes the outcome-tracking component a smaller and smaller share
  of the error as λ climbs, so the curve being extrapolated is not the
  curve the answer sits on. Its closed form is
  :mod:`themis.estimation.differential_error`, on a linear outcome.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import numpy as np
import pandas as pd

from .contract import validate_data
from .form import shapes_settled
from ..ledger import Provenance
from ..refusals import EstimatorFailure, Refusal, Remedy
from .resample import DeclaredVariance, cluster_labels

#: The λ grid Cook & Stefanski use and every implementation since has kept.
#: It starts at 0 because that point is not a simulation at all — zero noise
#: leaves the data alone — which makes it the anchor an audit can hold the
#: rest of the grid to.
DEFAULT_LAMBDAS: tuple[float, ...] = (0.0, 0.5, 1.0, 1.5, 2.0)

#: A mismeasured exposure with fewer than this many distinct values is a
#: misclassification object, not a continuously mismeasured one. The same
#: floor regression calibration uses, and the same for the same reason.
_MIN_CONTINUOUS_DISTINCT = 10

#: |γ2 − 1| below this puts λ = −1 on the rational extrapolant's pole, where
#: the extrapolated value is not a number.
_POLE = 1e-6
_IRLS_TOL = 1e-10
_IRLS_MAX = 100


@dataclass(frozen=True)
class SimexGridPoint:
    """One rung of the simulation ladder — everything the extrapolation
    needs from it, and nothing that would have to be recomputed to check."""

    lam: float
    theta: float
    """Mean of the replicate estimates at this λ."""
    replicate_variance: float
    """Sample variance ACROSS the replicates — how much the simulation
    itself moved the answer. Zero at λ = 0 by construction."""
    variance_mean: float
    """Mean of the replicates' own variance estimates. τ(λ) is this minus
    the line above, and the subtraction is why the variance extrapolation
    can come back negative."""
    replicates: int
    """One at λ = 0: adding zero noise B times is one fit run B times, and
    running it anyway would spend the work to hide that fact."""


@dataclass(frozen=True)
class SimexEstimate:
    """A simulation-extrapolation corrected coefficient.

    ``point`` is the extrapolant at λ = −1; ``naive_point`` is the λ = 0
    rung, which IS the uncorrected fit on the observed data. ``grid`` is
    the sufficient statistic for everything else here.
    """

    point: float
    naive_point: float
    ci_lower: float | None
    ci_upper: float | None
    ci_level: float
    method: str
    assumptions: tuple[str, ...]
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    treatment: str
    outcome: str
    adjustment: tuple[str, ...]
    error_variance: float
    outcome_model: str
    extrapolant: str
    grid: tuple[SimexGridPoint, ...]
    n_replicates: int
    random_state: int
    coefficients: tuple[float, ...]
    """The extrapolant's fitted parameters, in the family's own order."""
    variance_coefficients: tuple[float, ...]
    extrapolated_variance: float | None
    """τ(−1). ``None`` when the subtraction came back non-positive, which
    is also when there is no interval."""
    validation_df: int | None = None
    """The degrees of freedom of the study that measured σ̂²_u, when the
    caller declared them. Present, the interval is the mixture over
    λ* = −df/χ²_df rather than ± z√τ(−1); absent is the claim that σ̂²_u is
    exact, and the run is byte-identical to one from before this field."""
    unreadable_share: float | None = None
    """Of the σ²_u values that study makes plausible, the share at which the
    fitted curves cannot be read — most often σ² at or above the exposure's
    whole observed spread, which the data itself rules out. ``None`` where
    no study was declared and the question does not arise; ``0.0`` is the
    statement that the study and the ladder agree everywhere it reaches."""
    no_interval_because: str | None = None
    cluster: str | None = None
    outcome_model_declared: bool = False
    extrapolant_declared: bool = False
    """Whether the caller NAMED each lever, as a fact rather than as its
    interpretation.

    ``form_provenance`` and ``shape_provenance`` below are what these two
    mean for a reader; these are what happened. Keeping both is what lets an
    audit check the second against the first instead of against itself —
    a provenance derived from a record and then compared to that same
    derivation confirms nothing.
    """
    form: str = ""
    #: The outcome model and the extrapolant are both choices the method
    #: needs and cannot make — which is what separates this from regression
    #: calibration's INHERENT, where the shape IS the method. They are two
    #: levers, so they are two answers: this one covers the outcome model
    #: and ``shape_provenance`` carries the extrapolant's exception.
    form_provenance: str = Provenance.CALLER_CHOSE
    shape_provenance: Mapping[str, str] = field(
        default_factory=lambda: MappingProxyType({}))


# --- the naive fit, and its variance ------------------------------------------


def _design(w: np.ndarray, Z: np.ndarray | None) -> np.ndarray:
    """[1, exposure, covariates] — the exposure at index 1, always, so the
    coefficient this module is about is read off one place."""
    parts = [np.ones((len(w), 1)), w[:, None]]
    if Z is not None and Z.size:
        parts.append(Z)
    return np.hstack(parts)


def _fit_linear(X: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """OLS: the exposure's coefficient and its variance."""
    xtx = X.T @ X
    try:
        cov_unscaled = np.linalg.inv(xtx)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=_DESIGN_WORD,
        )
    beta = cov_unscaled @ (X.T @ y)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    if dof <= 0:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=_DESIGN_WORD,
        )
    sigma2 = float(resid @ resid) / dof
    return float(beta[1]), float(sigma2 * cov_unscaled[1, 1])


def _fit_logistic(X: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Unpenalised logistic MLE by IRLS: the exposure's coefficient and its
    variance from the observed information.

    Written here rather than taken from scikit-learn because scikit-learn's
    default is a PENALISED fit, and a shrunk coefficient is an attenuated
    coefficient — which is the very thing this module measures. A ridge on
    the naive estimate would travel through every rung of the ladder and
    come out looking like measurement error.
    """
    beta = np.zeros(X.shape[1])
    for _ in range(_IRLS_MAX):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-np.clip(eta, -35.0, 35.0)))
        w = np.clip(p * (1.0 - p), 1e-10, None)
        try:
            step = np.linalg.solve((X * w[:, None]).T @ X, X.T @ (y - p))
        except np.linalg.LinAlgError:
            raise EstimatorFailure(
                Refusal.SINGULAR_DESIGN,
                design=_DESIGN_WORD,
            )
        beta = beta + step
        if float(np.abs(step).max()) < _IRLS_TOL:
            break
    eta = X @ beta
    p = 1.0 / (1.0 + np.exp(-np.clip(eta, -35.0, 35.0)))
    w = np.clip(p * (1.0 - p), 1e-10, None)
    try:
        cov = np.linalg.inv((X * w[:, None]).T @ X)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(Refusal.SINGULAR_DESIGN, design=_DESIGN_WORD)
    return float(beta[1]), float(cov[1, 1])


_FITTERS = {"linear": _fit_linear, "logistic": _fit_logistic}


# --- the extrapolants ---------------------------------------------------------


def _fit_polynomial(lams: np.ndarray, values: np.ndarray, degree: int):
    """Least squares on [1, λ, …, λ^degree], and the value at λ = −1."""
    design = np.vstack([lams ** k for k in range(degree + 1)]).T
    gamma, *_ = np.linalg.lstsq(design, values, rcond=None)
    at = float(sum(g * (-1.0) ** k for k, g in enumerate(gamma)))
    return tuple(float(g) for g in gamma), at


def _fit_rational(lams: np.ndarray, values: np.ndarray):
    """γ0 + γ1/(γ2+λ), by the linearisation that makes it linear.

    θ·(γ2+λ) = γ0·(γ2+λ) + γ1 rearranges to θ·λ = γ0·λ + (γ0γ2+γ1) − γ2·θ,
    which is linear in (γ0, γ0γ2+γ1, γ2). Closed form, so a verifier can
    re-derive it; and where the rational model holds exactly the residuals
    are zero, so this fit and a nonlinear one agree there — which is the
    case the oracle is built on.
    """
    design = np.vstack([lams, np.ones_like(lams), -values]).T
    solved, *_ = np.linalg.lstsq(design, values * lams, rcond=None)
    g0, b, g2 = (float(v) for v in solved)
    g1 = b - g0 * g2
    if abs(g2 - 1.0) < _POLE:
        # Two ways out, and both are the caller's: another family has no
        # pole to land there, and a denser ladder moves where this one's
        # falls. Which is why they are routes rather than sentences — the
        # fault is the same wherever it is raised and the way past it is
        # not.
        raise EstimatorFailure(
            Refusal.SIMEX_EXTRAPOLANT_HAS_A_POLE_AT_MINUS_ONE,
            pole=round(-g2, 6),
            remedies=[(Remedy.SUPPLY_INPUT, "extrapolant="),
                      (Remedy.SUPPLY_INPUT, "lambdas=")],
        )
    return (g0, g1, g2), float(g0 + g1 / (g2 - 1.0))


def _extrapolate(kind: str, lams: np.ndarray, values: np.ndarray):
    """The declared family's coefficients and its value at λ = −1."""
    if kind == "linear":
        return _fit_polynomial(lams, values, 1)
    if kind == "quadratic":
        return _fit_polynomial(lams, values, 2)
    if kind == "rational":
        return _fit_rational(lams, values)
    raise ValueError(f"unknown extrapolant {kind!r}")


def _read(kind: str, coefficients: tuple[float, ...],
          lam: np.ndarray) -> np.ndarray:
    """A fitted family's value at each λ — anywhere, not only at −1.

    :func:`_extrapolate` answers at the one point standard SIMEX reads,
    which is the only point there is when σ²_u is exact. A declared
    validation study turns that point into a distribution, so the same
    curve has to be readable wherever that distribution reaches — and it is
    the same curve, read from the same coefficients, rather than a second
    fit that could disagree with the point beside it.
    """
    if kind == "rational":
        g0, g1, g2 = coefficients
        with np.errstate(divide="ignore", invalid="ignore"):
            return g0 + g1 / (g2 + lam)
    return np.polyval(np.asarray(coefficients)[::-1], lam)


#: How many points each family needs before it is fitting rather than
#: interpolating. A family with as many parameters as points passes through
#: all of them and says nothing about λ = −1.
_NEEDS = {"linear": 3, "quadratic": 4, "rational": 4}

_DESIGN_WORD = "design_matrix"

#: How many points the validation study's own distribution is read at.
#:
#: A fixed grid of equally spaced probabilities rather than a Monte Carlo,
#: because the mixture's CDF is an average of a BOUNDED function against
#: that distribution — so the quadrature converges whatever the study's
#: degrees of freedom do to its tails, and it needs no seed. The seed is the
#: point: everything downstream of the simulated ladder in this module is
#: re-derivable by a second author, and an interval drawn from a stream
#: would have moved that line.
_VALIDATION_QUADRATURE = 512

#: Bisections used to invert the mixture's CDF. Well past the point where a
#: double stops changing, and a fixed count rather than a tolerance because
#: the verifier recomputes this: an iteration budget is arithmetic both
#: sides can agree on, where a stopping rule is a place they can differ.
_BISECTIONS = 100


# --- public entry -------------------------------------------------------------


def estimate_simex(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...] = (),
    # Widely typed on purpose. Each of the three is validated below against
    # the ONE record of what it may be — the fitter table, the family table,
    # and "is this a positive finite number" — and a Literal restating those
    # sets in the signature would be a second record of each, free to go
    # stale the day a family is added. What a caller may pass is the closed
    # set the schema states and these tables hold, not a repetition of it.
    # ``object`` for the reason its siblings give: whether what arrived is
    # a usable variance is this entry point's judgement, and a narrower
    # annotation would claim it was settled before the call. It also has to
    # admit a ``DeclaredVariance``, which is one declaration rather than a
    # number and a precision travelling separately.
    error_variance: object,
    outcome_model: str | None = None,
    extrapolant: str | None = None,
    lambdas: tuple[float, ...] = DEFAULT_LAMBDAS,
    n_replicates: int = 100,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> SimexEstimate:
    """Correct a continuously mismeasured exposure's coefficient by
    simulation-extrapolation.

    Parameters
    ----------
    error_variance: the KNOWN classical additive error variance σ²_u of the
        exposure, from a validation substudy or replicates — the same
        external input regression calibration takes, held fixed throughout.
    outcome_model: ``"logistic"`` for a binary outcome, which is what this
        module exists for; ``"linear"`` is the oracle case, where the answer
        is also available in closed form. ``None`` takes the first, and is
        what makes the estimate able to say who settled the shape.
    extrapolant: which declared family is fitted through the ladder;
        ``None`` takes the measured default, and likewise records that
        nobody named it.
    lambdas: the ladder. Must start at 0 — that rung is the naive fit — and
        increase.
    n_replicates: simulations per rung above 0.

    Raises
    ------
    EstimatorFailure: a non-positive error variance, a near-discrete
        exposure, an outcome that does not match the model, a grid that does
        not start at 0 or does not increase, a grid too short for the
        declared family, or a rational extrapolant whose pole sits at −1.
    """
    declared_variance = error_variance
    error_variance = DeclaredVariance.declared_value(error_variance)
    if (
        not isinstance(error_variance, (int, float))
        or isinstance(error_variance, bool)
        or not np.isfinite(error_variance)
        or error_variance <= 0
    ):
        raise EstimatorFailure(
            Refusal.NON_POSITIVE_ERROR_VARIANCE,
            variable=treatment, given=error_variance,
        )
    # σ²_u sets the noise added at EVERY rung, so a redrawn one moves the
    # whole ladder rather than one draw on it — which is why this route
    # carries a validation study by reading the fitted curve somewhere else
    # rather than by resampling. Read here so the refusal a bad df raises
    # leaves through this entry point's own door.
    declared = DeclaredVariance.read(declared_variance)
    # Resolved once, and who resolved it kept: a defaulted shape and a named
    # one are the same string afterwards, so the distinction is destroyed
    # unless it is taken here.
    model_declared = outcome_model is not None
    family_declared = extrapolant is not None
    model_origin = (Provenance.CALLER_CHOSE if model_declared
                    else Provenance.DEFAULT)
    family_origin = (Provenance.CALLER_CHOSE if family_declared
                     else Provenance.DEFAULT)
    outcome_model = outcome_model or "logistic"
    extrapolant = extrapolant or "rational"
    if outcome_model not in _FITTERS:
        raise ValueError(f"unknown outcome model {outcome_model!r}")
    if extrapolant not in _NEEDS:
        raise ValueError(f"unknown extrapolant {extrapolant!r}")

    lams = tuple(float(v) for v in lambdas)
    if not lams or lams[0] != 0.0 or any(
        b <= a for a, b in zip(lams, lams[1:])
    ):
        raise EstimatorFailure(
            Refusal.SIMEX_GRID_IS_NOT_A_LADDER, grid=list(lams),
        )
    if len(lams) < _NEEDS[extrapolant]:
        raise EstimatorFailure(
            Refusal.SIMEX_GRID_IS_TOO_SHORT_FOR_THE_EXTRAPOLANT,
            extrapolant=extrapolant, rungs=len(lams),
            needed=_NEEDS[extrapolant],
        )

    adjustment = tuple(sorted(adjustment))
    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
        quantity_columns=(treatment, *adjustment),
    )
    df = contract.data

    n_distinct = int(df[treatment].dropna().nunique())
    if n_distinct < _MIN_CONTINUOUS_DISTINCT:
        raise EstimatorFailure(
            Refusal.EXPOSURE_NOT_CONTINUOUS,
            column=treatment, levels=n_distinct,
            floor=_MIN_CONTINUOUS_DISTINCT,
            remedies=[(Remedy.SUPPLY_INPUT, "misclassification=")],
        )

    y = df[outcome].to_numpy()
    if y.dtype == bool:
        y = y.astype(float)
    y = y.astype(float)
    levels = np.unique(y[~np.isnan(y)])
    if outcome_model == "logistic" and not (
        len(levels) == 2 and set(levels.tolist()) <= {0.0, 1.0}
    ):
        raise EstimatorFailure(
            Refusal.OUTCOME_NOT_BINARY,
            outcome=outcome, levels=levels.tolist(),
        )

    w = df[treatment].to_numpy(dtype=float)
    Z = (
        np.column_stack([df[c].to_numpy(dtype=float) for c in adjustment])
        if adjustment else None
    )
    if cluster is not None:  # validated, and recorded on the estimate
        cluster_labels(df, cluster, expected_n=len(df))

    fit = _FITTERS[outcome_model]
    sigma_u = float(np.sqrt(error_variance))
    rng = np.random.default_rng(random_state)

    grid: list[SimexGridPoint] = []
    for lam in lams:
        if lam == 0.0:
            # Not a simulation. Adding zero noise B times is one fit run B
            # times, and the replicate variance is zero by construction —
            # which is the anchor the audit holds the rest of the ladder to.
            theta, var = fit(_design(w, Z), y)
            grid.append(SimexGridPoint(
                lam=0.0, theta=theta, replicate_variance=0.0,
                variance_mean=var, replicates=1,
            ))
            continue
        thetas = np.empty(n_replicates)
        variances = np.empty(n_replicates)
        scale = float(np.sqrt(lam)) * sigma_u
        for b in range(n_replicates):
            noisy = w + scale * rng.standard_normal(len(w))
            thetas[b], variances[b] = fit(_design(noisy, Z), y)
        grid.append(SimexGridPoint(
            lam=lam,
            theta=float(thetas.mean()),
            replicate_variance=float(thetas.var(ddof=1)),
            variance_mean=float(variances.mean()),
            replicates=n_replicates,
        ))

    lam_arr = np.array([g.lam for g in grid])
    theta_arr = np.array([g.theta for g in grid])
    coefficients, point = _extrapolate(extrapolant, lam_arr, theta_arr)

    tau = np.array(
        [g.variance_mean - g.replicate_variance for g in grid])
    variance_coefficients, tau_at = _extrapolate(extrapolant, lam_arr, tau)

    ci_lower = ci_upper = None
    extrapolated: float | None = None
    because: str | None = None
    unreadable: float | None = None
    if cluster is not None:
        # Every variance on the ladder is the fitter's own, and a model-based
        # variance is a statement about independent rows. The caller has said
        # they are not. Nothing about that touches the point — clustering
        # costs precision, not identification — so the point ships and the
        # interval does not, through the same door a non-positive τ uses.
        because = _CLUSTERING_IS_NOT_IN_THE_VARIANCE
    elif tau_at <= 0:
        # Checked before the study's own reading is attempted, because a
        # variance that is not positive at λ = −1 is a fact about the ladder
        # and stays the answer whoever measured σ²_u.
        because = _VARIANCE_WENT_NON_POSITIVE
    elif declared.validation_df is None:
        extrapolated = float(tau_at)
        from scipy import stats

        z = float(stats.norm.ppf(0.5 + ci_level / 2.0))
        half = z * float(np.sqrt(tau_at))
        ci_lower, ci_upper = point - half, point + half
    else:
        extrapolated = float(tau_at)
        ci_lower, ci_upper, unreadable, because = mixture_interval(
            extrapolant, coefficients, variance=float(tau_at),
            validation_df=declared.validation_df, ci_level=ci_level,
        )
        if ci_lower is None:
            extrapolated = None

    assumptions = _assumptions(
        treatment, adjustment, outcome_model, extrapolant, declared)
    return SimexEstimate(
        point=point,
        naive_point=grid[0].theta,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="simex",
        assumptions=assumptions,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome, adjustment=adjustment,
        error_variance=float(error_variance),
        outcome_model=outcome_model,
        extrapolant=extrapolant,
        grid=tuple(grid),
        n_replicates=int(n_replicates),
        random_state=int(random_state),
        coefficients=coefficients,
        variance_coefficients=variance_coefficients,
        extrapolated_variance=extrapolated,
        validation_df=declared.validation_df,
        unreadable_share=unreadable,
        no_interval_because=because,
        cluster=cluster,
        outcome_model_declared=model_declared,
        extrapolant_declared=family_declared,
        form=f"simex_{outcome_model}_{extrapolant}",
        form_provenance=model_origin,
        shape_provenance=shapes_settled(
            assumptions,
            (f"simex_extrapolant_declared_{extrapolant}", family_origin),
        ),
    )


#: Why an interval is missing rather than clipped to touch the point, or
#: shipped under a premise the caller has already contradicted.
_VARIANCE_WENT_NON_POSITIVE = "extrapolated_variance_is_not_positive"
_CLUSTERING_IS_NOT_IN_THE_VARIANCE = "declared_clustering_is_not_in_the_variance"
_STUDY_REACHES_PAST_THE_LADDER = "validation_study_reaches_past_the_ladder"


def off_the_ladder(kind: str, coefficients: tuple[float, ...],
                   validation_df: int) -> float:
    """Of what the study makes plausible, the share with nothing to read.

    Closed form rather than a count over the quadrature, because it IS one:
    the rational family's value is undefined past λ = −γ2, λ* = −df/X puts a
    draw there exactly when X ≤ df/γ2, and X is χ²_df. A polynomial has no
    pole, so nothing about a study can put a draw where it cannot be read
    and the answer is zero.

    And it is not a numerical curiosity. λ* < −γ2 is σ² at or above the
    exposure's whole observed spread — an error variance the observed data
    itself rules out — so this number is the share of the caller's own
    validation study that their data contradicts.
    """
    if kind != "rational":
        return 0.0
    from scipy import stats

    pole = coefficients[2]
    if pole <= 0:
        # λ = −1 is already past it, so every draw is. Reported rather than
        # raised: the caller's next move is the same one the tail case asks
        # for, and a second door to it would be a second sentence.
        return 1.0
    return float(stats.chi2.cdf(validation_df / pole, validation_df))


def mixture_interval(
    kind: str,
    coefficients: tuple[float, ...],
    *,
    variance: float,
    validation_df: int,
    ci_level: float,
) -> tuple[float | None, float | None, float, str | None]:
    """The interval when σ̂²_u came from a study rather than from a protocol.

    Returns ``(lower, upper, unreadable, because)``. ``unreadable`` is
    returned in every case — including when it is zero, which is the
    statement that the study and the ladder agree everywhere it reaches.

    ``variance`` is τ(−1), and holding it there while the reading point
    moves is a DECLARED approximation rather than an oversight. τ(λ) is
    itself an extrapolation of a difference of two estimated variances, and
    reading it away from the one point this module vouches for turned out
    to be governed by where its own fitted pole happened to land: measured
    on the linear oracle at 300 replicates a rung, reading τ at λ* withheld
    41 of 80 intervals at df=24 where holding it at −1 withheld 5, and
    covered 36/39 against 72/75. It understates the conditional variance
    below −1 and overstates it above, and the measurement says the net is
    conservative. What carries the study is the mean shift, and that is
    read exactly.

    Public because the browser is not the only second reader: this is the
    whole interval, so a caller re-deriving it needs the same arithmetic
    rather than a description of it. The verifier does NOT import it — that
    audit restates the construction, as every other one here does.
    """
    from scipy import stats

    unreadable = off_the_ladder(kind, coefficients, validation_df)
    tail = (1.0 - ci_level) / 2.0
    if unreadable >= tail:
        # The excluded mass has swallowed the very tail an endpoint is meant
        # to be. Conditioning on the rest would report a 1−α interval whose
        # α is no longer the α on the page.
        return None, None, unreadable, _STUDY_REACHES_PAST_THE_LADDER

    # Equally spaced probabilities of what is left, so the conditioning is
    # exact rather than a grid that happened to miss the excluded part.
    probabilities = unreadable + (1.0 - unreadable) * (
        (np.arange(_VALIDATION_QUADRATURE) + 0.5) / _VALIDATION_QUADRATURE)
    theta = _read(
        kind, coefficients,
        -validation_df / stats.chi2.ppf(probabilities, validation_df))
    spread = float(np.sqrt(variance))

    def _below(t: float) -> float:
        return float(np.mean(stats.norm.cdf((t - theta) / spread)))

    lo = float(np.min(theta)) - 12.0 * spread
    hi = float(np.max(theta)) + 12.0 * spread
    return (_invert(_below, tail, lo, hi),
            _invert(_below, 1.0 - tail, lo, hi),
            unreadable, None)


def _invert(cdf, target: float, lo: float, hi: float) -> float:
    """Where a monotone CDF crosses ``target``, by bisection on a bracket
    the mixture's own support supplies."""
    for _ in range(_BISECTIONS):
        mid = 0.5 * (lo + hi)
        if cdf(mid) < target:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def _assumptions(treatment, adjustment, outcome_model, extrapolant, declared):
    """The premises, as ids.

    The first two are regression calibration's own, word for word and row
    for row, because they ARE the same premises: what differs between the
    two modules is the outcome model the estimand lives in, not anything
    assumed about the measurement. Minting a second id for the same claim
    would let a reader who refuted it there think it still stood here.

    Which of the two variance premises this is, is the declaration's own
    branch rather than one written here — the same method that keeps the
    five estimators from drifting apart on it.
    """
    out = [
        f"design_error_classical_additive_on_{treatment}",
        declared.premise("design_error_variance", treatment),
        f"simex_estimand_is_the_exposure_coefficient_in_a_{outcome_model}",
        f"simex_extrapolant_declared_{extrapolant}",
        "simex_interval_covers_sampling_not_extrapolation_error",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    else:
        out.append(
            "unconditional_exchangeability_treatment_is_marginally_randomized")
    return tuple(out)
