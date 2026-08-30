"""Berkson error on the exposure — the structure where correcting is the mistake.

:mod:`regression_calibration` and :mod:`simex` both correct CLASSICAL
additive error: ``W = X* + U`` with ``U`` independent of the TRUTH, which
inflates the exposure's variance and attenuates the slope toward zero.
Berkson (1950) error is the other structure and the arrow runs the other
way:

    X* = W + U ,   U ⟂ W ,   E[U] = 0

The recorded ``W`` is the NOMINAL value — a dose assigned to a group, a
station's reading applied to a district, a prescribed rather than absorbed
amount — and the truth scatters around it. Both are "classical additive
error with a known variance", and no property of a single column tells
them apart: which one holds is a fact about how the measurement was MADE.

**Under a linear outcome the naive slope is already unbiased, so the
correction is what introduces the error.** ``E[X*|W, Z] = W`` exactly, so

    E[Y | W, Z] = β0 + βx·W + βz'·Z

carries the same coefficients as the model in the true values, and the
ordinary back-door slope IS βx. Measured on a synthetic sample with true
βx = 0.8 and σ²_u = 0.5: the back-door slope is 0.79940, and dividing it
through by the reliability ratio the classical correction would compute
gives 1.60681 — a correct number moved 101% by a correction repairing an
attenuation that never happened. That is the reason this module exists.
Nothing here estimates the effect; the estimator that already answered
the query answered it correctly, and this says so and prices what the
error DID cost.

**What it costs is precision, and the cost is knowable because σ²_u is.**
The residual around the observed design absorbs the scattered truth:

    Y − E[Y|W,Z] = βx·U + ε        Var(Y|W,Z) = Var(Y|X*,Z) + βx²·σ²_u

so every least-squares interval on this design is wider by the fixed
factor ``sqrt(Var(Y|W,Z) / (Var(Y|W,Z) − βx²σ²_u))``. That is the same
split :mod:`outcome_error` takes on the other channel, and it is the same
arithmetic — what differs is the coefficient the declared variance enters
through. **Here the noise is scaled by the answer**, βx², which has a
consequence worth stating rather than deriving: a larger effect makes the
same nominal-exposure error more expensive, and the price therefore
cannot be computed until the query has been answered.

The split is refutable, which is the point of computing it. βx²σ²_u ≥
Var(Y|W,Z) says the declared scatter does not fit under the variation the
data leave unexplained; one of the declared variance, the linearity, or
the independence of U from W is then false — and the last is the premise
that made the point safe. So this refuses rather than reporting a
negative signal variance.

Scope (declared):

- The BACK-DOOR design. The Berkson identity is about a conditional mean,
  and it is the back-door slope that is a conditional mean of Y given the
  recorded exposure. A front-door answer standardises over a mediator
  fitted on the exposure, and an IV answer is a ratio of covariances with
  an instrument; each is plausibly unbiased under Berkson error too and
  each needs its own argument, so neither is claimed here.
- A LINEAR outcome model. Under a nonlinear one Berkson error DOES bias
  — the conditional mean of a nonlinear function is not that function of
  the conditional mean — and the correction is not a moment identity.
  That case is refused rather than priced.
- One nominally-measured EXPOSURE. A Berkson-structured covariate is a
  different object: the identity that saves the exposure's slope says
  nothing about a coefficient on a covariate whose truth scattered.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from ..refusals import EstimatorFailure, Refusal, Remedy
from .outcome_error import _moments
from .regression_calibration import _MIN_CONTINUOUS_DISTINCT

#: Signal variance at or below this share of the residual ⇒ the declared
#: scatter swallows the model's unexplained variation ⇒ refuse rather than
#: report a meaningless inflation factor. The same floor
#: :mod:`outcome_error` uses, because it is the same judgement.
_SIGNAL_FLOOR = 1e-9


@dataclass(frozen=True)
class BerksonAssessment:
    """What a known Berkson error variance implies for one answered query.

    There is no ``point`` here and the absence is the finding: the number
    the query already carries is the causal slope, unchanged. ``exposure``
    names the nominally-measured column, ``treatment_coefficient`` is the
    β̂ the price is scaled by, ``residual_variance`` is Var(Y|W,Z) around
    the observed design, ``signal_variance`` what remains once βx²σ²_u is
    removed, ``noise_share`` the fraction of the unexplained variation
    that is scattered truth, and ``se_inflation`` the factor by which it
    widens every least-squares interval on this design.
    """

    exposure: str
    outcome: str
    design_vars: tuple[str, ...]
    error_variance: float
    treatment_coefficient: float
    scattered_variance: float
    """βx²·σ²_u — what the declared scatter contributes to the residual.
    Recorded beside σ²_u rather than left to be recomputed, because it is
    the one quantity here that depends on the ANSWER."""
    residual_variance: float
    signal_variance: float
    noise_share: float
    se_inflation: float
    sample_size: int
    data_hash: str
    data_columns: tuple[str, ...]
    assumptions: tuple[str, ...] = ()
    sufficient_statistics: dict = field(default_factory=dict)


def assess_berkson_error(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: Sequence[str] = (),
    # ``object`` rather than ``float`` for both, because judging whether
    # what arrived is a usable number IS this entry point's job, and an
    # annotation claiming it was settled beforehand would move that
    # judgement somewhere no caller can see it fail.
    treatment_coefficient: object = None,
    error_variance: object,
) -> BerksonAssessment:
    """Price what a declared Berkson error costs the query it rode in on.

    Parameters
    ----------
    treatment: the NOMINALLY measured exposure column — the assigned value
        the truth scattered around, not a noisy reading of the truth.
    adjustment: the back-door set the answer was taken over. The residual
        is taken around that design, so a different set prices a model
        nobody fitted.
    treatment_coefficient: β̂ from the answer this rides on. The scatter
        enters the residual as βx²σ²_u, so the price is a property of the
        answer and cannot be had before it.
    error_variance: the KNOWN Berkson variance σ²_u = Var(X* − W), from a
        validation substudy or from how the nominal value was assigned.

    Raises
    ------
    EstimatorFailure: an absent, non-positive or non-finite σ²_u or β̂; a
        near-discrete exposure (a misclassification object rather than a
        continuously-scattered one); a singular design; or a βx²σ²_u that
        meets or exceeds the observed residual variance.
    """
    sigma_u = _refuse_unusable_variance(error_variance, treatment)
    beta = _refuse_unusable_coefficient(treatment_coefficient, treatment)

    adjustment = tuple(adjustment)
    contract = validate_data(
        data,
        required_columns={treatment, outcome, *adjustment},
        quantity_columns=(treatment, outcome, *adjustment),
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

    design_vars = (treatment, *adjustment)
    D = np.column_stack(
        [df[c].to_numpy(dtype=float) for c in design_vars])
    Sigma, cov_Dy, var_y, n = _moments(D, df[outcome].to_numpy(dtype=float))

    try:
        b = np.linalg.solve(Sigma, cov_Dy)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design="design_matrix")
    residual_variance = float(var_y - 2.0 * (b @ cov_Dy) + b @ Sigma @ b)

    # The identity is about ONE functional — the ordinary least-squares slope
    # of Y on the recorded exposure and the adjustment set — so a coefficient
    # that is not that slope is not the quantity E[X*|W,Z]=W leaves alone.
    # Without this the block would ride beside any back-door answer at all,
    # pricing whatever number happened to be there and telling its reader that
    # number needed no correcting. The check is what confines the claim to the
    # estimator it is true of, and it is arithmetic rather than a method name:
    # a name is a second record of what the number is, free to disagree with
    # it, and a family added later would be judged by a list nobody updated.
    if not np.isclose(beta, b[0], rtol=1e-6, atol=1e-9):
        raise EstimatorFailure(
            Refusal.BERKSON_ANSWER_IS_NOT_THE_DESIGN_SLOPE,
            exposure=treatment, answered=beta, slope=float(b[0]),
        )

    scattered = float(beta * beta * sigma_u)
    signal_variance = residual_variance - scattered
    if signal_variance <= _SIGNAL_FLOOR * max(residual_variance, 1.0):
        raise EstimatorFailure(
            Refusal.BERKSON_SCATTER_EXCEEDS_RESIDUAL_VARIANCE,
            declared=sigma_u, exposure=treatment, scattered=scattered,
            residual=residual_variance,
        )

    return BerksonAssessment(
        exposure=treatment,
        outcome=outcome,
        design_vars=design_vars,
        error_variance=sigma_u,
        treatment_coefficient=beta,
        scattered_variance=scattered,
        residual_variance=residual_variance,
        signal_variance=signal_variance,
        noise_share=scattered / residual_variance,
        se_inflation=float(np.sqrt(residual_variance / signal_variance)),
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        assumptions=_assumptions(treatment),
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "design_coefficients": [float(v) for v in b],
            "var_y": var_y,
            "error_variance": sigma_u,
            "treatment_coefficient": beta,
            "n": int(n),
        },
    )


def _refuse_unusable_variance(error_variance: object, exposure: str) -> float:
    """σ²_u as a number, or the refusal that says it is not one.

    Absence is answered separately from unusability, because the reader's
    next move differs: one supplies a number and the other corrects one.
    Told "the variance you declared is not positive" about a variance they
    never declared, a reader goes looking in their own call for a value
    that is not there.
    """
    if error_variance is None:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="error_variance=",
            remedies=[(Remedy.SUPPLY_INPUT, "error_variance")],
            recorded={"exposure": exposure},
        )
    if (
        not isinstance(error_variance, (int, float))
        or isinstance(error_variance, bool)
        or not np.isfinite(error_variance)
        or error_variance <= 0
    ):
        raise EstimatorFailure(
            Refusal.NON_POSITIVE_ERROR_VARIANCE,
            variable=exposure, given=error_variance,
        )
    return float(error_variance)


def _refuse_unusable_coefficient(value: object, exposure: str) -> float:
    """β̂ as a number, or the refusal that says the price has no scale.

    Zero is refused with the rest, and not as an edge case: at β̂ = 0 the
    scatter contributes nothing to the residual, so the price is exactly
    nil — and a nil price reported as a price reads as "measured, and
    small" rather than "there was no effect for the error to cost
    anything on".
    """
    if value is None:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="treatment_coefficient=",
            remedies=[(Remedy.SUPPLY_INPUT, "treatment_coefficient")],
            recorded={"exposure": exposure},
        )
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not np.isfinite(value)
        or value == 0
    ):
        raise EstimatorFailure(
            Refusal.BERKSON_PRICE_HAS_NO_COEFFICIENT,
            exposure=exposure, given=value,
        )
    return float(value)


def _assumptions(exposure: str) -> tuple[str, ...]:
    """The three premises this assessment adds, and not the design's.

    The back-door premise is load-bearing here — "the ordinary back-door
    slope IS the causal slope" is a claim about a valid adjustment set —
    and it is deliberately absent, because the estimator this block rides
    beside has already declared it. A block that restated it would put a
    second line with the same id on one ledger, where a reader cannot tell
    a premise stated twice from two premises that happen to agree.

    What is left is what belongs to nobody else: which STRUCTURE the error
    has, which is why no correction was applied; the SIZE of the scatter,
    which is why the price has the size it has; and the LINEARITY, which is
    what makes E[X*|W,Z] = W carry through to the coefficients at all.

    The last is deliberately not spelled with the id
    ``linear_structural_outcome_model_in_the_true_values`` that
    :mod:`regression_calibration` uses for the same proposition, and the
    difference is what each family DOES with it. There the estimator fits a
    linear model, so it is a shape choice, disclosed through the mechanism
    audit and graded distorting. Here nothing is fitted: the identity that
    leaves the point alone rests on the shape being true, and if it is not,
    the answer is biased rather than merely mis-shaped. A block with no
    mechanism to audit must not claim one, and a premise whose failure
    invalidates the number must not be graded as one that only bends it.
    """
    return (
        f"berkson_error_on_{exposure}",
        f"berkson_scatter_variance_known_and_fixed_on_{exposure}",
        "berkson_identity_rests_on_a_linear_outcome_in_the_true_values",
    )
