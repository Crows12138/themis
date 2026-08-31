"""Differential error on the exposure — the correction that needs one more number.

:mod:`regression_calibration` corrects CLASSICAL additive error: ``W = X* + U``
with ``U`` independent of everything, the truth and the outcome included. That
last clause is the NON-DIFFERENTIAL premise, and it is the one the literature
warns cannot be dropped for free (Carroll et al. 2006 §2.5: a surrogate that is
not conditionally independent of Y given X* is not a surrogate at all). What
follows from dropping it is not that the correction gets rougher; it is that the
correction moves the answer to a new wrong place, and in either direction.

**The model, after partialling the adjustment set out of everything** (tilde =
residual on Z, which is where Frisch-Waugh puts the exposure's coefficient):

    Ỹ = βx·X̃* + ẽ                    ẽ ⟂ X̃*
    W̃ = X̃* + U                       U = δ·Ỹ + f,  f ⟂ (X̃*, ẽ)

so the recorded exposure carries a component that tracks the OUTCOME — a
self-report shaded by how ill the respondent already is, an exposure abstracted
from a chart by someone who has read the diagnosis. ``δ`` is the coefficient a
validation substudy holding (Y, X*, W, Z) reports when it regresses ``W − X*``
on the outcome's residual; ``error_variance`` stays what it means everywhere
else in this family, the TOTAL ``Var(W − X*)``.

**With A = Var(W̃), B = Var(Ỹ), C = Cov(Ỹ, W̃) and S = Var(X̃*):**

    C     = βx·S + δ·B                     the error inflates the covariance
    σ²_0  = σ²_u − δ²·B                    what is left of the error, classical
    S     = A − σ²_u + 2δ²·B − 2δ·C
    βx    = (C − δ·B) / S

Two things move where regression calibration moves one. It divides the observed
covariance by a reliability ratio; here the covariance itself has to be
un-inflated FIRST — ``C − δB`` — because part of what looks like the exposure
covarying with the outcome is the error covarying with the outcome. That is why
a differential error can bias away from the null, and why more correction is not
better correction.

**At δ = 0 this IS regression calibration.** ``S = A − σ²_u`` and
``βx = C/(A − σ²_u)``, the reliability-ratio correction exactly — matched to
4.4e-15 on a shared sample, so the module that has been in the package for
months is this one's oracle rather than its neighbour. Measured at βx = 0.8,
σ²_0 = 0.5, with the correct total variance handed to both:

    δ      naive     regression calibration     here
    −0.4   0.128     0.398                      0.800
    −0.2   0.379     0.693                      0.800
     0.0   0.533     0.800                      0.800
    +0.3   0.607     0.873                      0.799
    +0.5   0.598     0.900                      0.799

Both guards are refusals rather than clamps, and each says a different thing.
``σ²_0 ≤ 0`` is a contradiction between two DECLARATIONS — the stated δ needs
more error variance than the stated σ²_u has — and is decided before the data is
consulted. ``S ≤ 0`` is the declarations meeting the sample: together they leave
the true exposure no variance at all, and a slope over no variance is not a
number.

Scope (declared):

- The BACK-DOOR design, one mismeasured EXPOSURE, a LINEAR outcome. The
  adjustment set is partialled out of both columns and so has to be measured
  exactly; a second mismeasured column would need the covariance between the two
  errors, which a per-column variance does not carry.
- The differential axis is the OUTCOME, and after adjustment it is the only axis
  that can be one. An error that tracks a covariate the design conditions on is
  classical once that covariate is partialled out — ``W̃ = X̃* + f̃`` — so it is
  refused here and sent to the ordinary correction with the residual variance,
  which is a real answer rather than a smaller scope.
- A LINEAR dependence on the outcome. ``δ`` is one number, and one number can
  only say how much the error tracks Y, not that it tracks Y differently at
  different Y. That is the premise nothing in (W, Y, Z) can check: a δ and a βx
  enter the observed covariance in exactly the same way, which is why δ has to
  arrive from outside the sample and why this module cannot estimate it.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from .form import NO_OTHER_SHAPES
from .regression_calibration import _MIN_CONTINUOUS_DISTINCT
from .resample import (
    DeclaredTracking,
    DeclaredVariance,
    Draws,
    cluster_labels,
    resample_indices,
)
from .. import refusals
from ..ledger import Provenance
from ..refusals import EstimatorFailure, Refusal, Remedy

#: Var(X̃*) at or below this share of the observed conditional variance ⇒ the
#: declarations leave the true exposure nothing to vary over ⇒ refuse rather
#: than divide by it.
_SIGNAL_FLOOR = 1e-9


@dataclass(frozen=True)
class DifferentialErrorEstimate:
    """The exposure's slope corrected for an error that tracks the outcome.

    ``point`` is βx, the per-unit slope of the TRUE exposure; ``naive_point``
    is the ordinary back-door slope the correction replaces.
    ``outcome_tracking_covariance`` is δ·B — how much of the observed
    exposure-outcome covariance is the error rather than the effect, and the
    term regression calibration has no counterpart for.
    ``nondifferential_variance`` is σ²_0 = σ²_u − δ²B, what is left of the
    declared error once its outcome-tracking part is removed, and
    ``reliability`` is S/A, which at δ = 0 is exactly the reliability ratio of
    the ordinary correction.
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
    design_vars: tuple[str, ...]
    error_variance: float
    differential_by: str
    differential_coefficient: float
    nondifferential_variance: float
    outcome_tracking_covariance: float
    exposure_variance: float
    reliability: float

    validation_df: int | None = None
    """The degrees of freedom of the study behind the declared error, when one
    was declared. ``None`` is the claim that the number is exact, not a field
    left blank — and the assumption ledger carries the two as separate ids."""

    tracking_standard_error: float | None = None
    """se(δ̂), present exactly when the SAME study also measured δ.

    Which is what separates the two shapes a caller can declare, without a
    second record of the degrees of freedom: a validation regression reports
    one df for both of its numbers, so ``validation_df`` says a study was
    declared and this says that study reached δ as well. Its residual
    variance needs no field of its own — ``nondifferential_variance`` is that
    number, derived under one shape and declared under the other, and the
    same arithmetic relates it to σ²_u either way."""

    sufficient_statistics: dict = field(default_factory=dict)

    #: The replicates this interval was taken over — see
    #: :class:`themis.estimation.resample.Draws`. ``None`` when no
    #: bootstrap ran, which is the one case with no answer to give.
    draws: "Draws | None" = None
    cluster: str | None = None
    form: str = "differential_regression_calibration_backdoor_linear"
    #: Nothing chose this shape: it IS the method, and the only way to
    #: overrule it is to answer by a different one.
    form_provenance: str = Provenance.INHERENT
    shape_provenance: Mapping[str, str] = NO_OTHER_SHAPES


# --- public entry -------------------------------------------------------------


def estimate_differential_error(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: Sequence[str] = (),
    # Defaulted because ONE of the two declarations supplies it and the other
    # derives it, and which is which is settled by the coefficient below. A
    # required argument here would make the studied shape pass a number it
    # does not have, and the refusal it would then trip is about a number
    # nobody meant to declare.
    error_variance: object = None,
    differential_by: object,
    differential_coefficient: object,
    ci_bootstrap: int = 500,
    ci_level: float = 0.95,
    random_state: int = 42,
    cluster: str | None = None,
) -> DifferentialErrorEstimate:
    """Correct a mismeasured exposure whose error tracks the outcome.

    Parameters
    ----------
    error_variance: the KNOWN total σ²_u = Var(W − X*), the same quantity the
        classical correction takes. Its outcome-tracking part is derived, not
        declared twice: σ²_0 = σ²_u − δ²·Var(Y|Z). Absent — and refused — under
        the declaration below that measures δ, where the total is the derived
        one.
    differential_by: the column the error tracks. Must be ``outcome`` — see the
        module docstring for why an adjusted covariate is not a smaller case of
        this but a classical one.
    differential_coefficient: δ, the slope of the error on the outcome's
        residual, from a validation substudy holding (Y, X*, W, Z). A bare
        number says it is exact and is held fixed across resamples. Declared
        as what that substudy's regression reported — ``coefficient``,
        ``standard_error``, ``residual_variance``, ``validation_df`` — δ and
        the error left under it are redrawn together each round and the
        interval carries the substudy's own uncertainty. See
        :class:`~themis.estimation.resample.DeclaredTracking` for why the
        remainder is what a study declares and the total is what it derives.

    Raises
    ------
    EstimatorFailure: an absent or unusable σ²_u or δ; both a validation
        regression and a total variance, which is one fact twice; a
        differential axis that is not the outcome; a near-discrete exposure; a
        singular design; a δ that leaves no non-differential error variance; or
        declarations that together leave the true exposure no variance.
    """
    tracking = _refuse_unusable_coefficient(differential_coefficient, treatment)
    delta = tracking.coefficient
    declared, sigma_u, remainder = _one_declaration_of_the_error(
        error_variance, tracking, treatment)

    adjustment = tuple(sorted(adjustment))
    _refuse_an_axis_that_is_not_the_outcome(
        differential_by, treatment=treatment, outcome=outcome,
        adjustment=adjustment,
    )

    presence = (cluster,) if cluster is not None else ()
    contract = validate_data(
        data,
        required_columns={treatment, outcome, *adjustment},
        presence_columns=presence,
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
    D = np.column_stack([df[v].to_numpy(dtype=float) for v in design_vars])
    y = df[outcome].to_numpy(dtype=float)
    n = len(df)

    groups = (
        cluster_labels(df, cluster, expected_n=n)
        if cluster is not None else None
    )

    point, naive, parts, Sigma, cov_Dy, var_y = _formula(
        D, y, sigma_u=sigma_u, remainder=remainder, delta=delta,
        exposure=treatment)
    # σ²_u is the derived one under the study shape, so what the block reports
    # is what this sample composed rather than what the caller wrote.
    sigma_u = parts["error_variance"]

    ci_lower = ci_upper = None
    draws = Draws(ci_bootstrap) if ci_bootstrap > 0 else None
    if draws is not None:
        ci_lower, ci_upper = _bootstrap(
            D, y, declared=declared, tracking=tracking, exposure=treatment,
            groups=groups, draws=draws, ci_level=ci_level,
            random_state=random_state,
        )

    return DifferentialErrorEstimate(
        point=point,
        naive_point=naive,
        ci_lower=ci_lower, ci_upper=ci_upper, ci_level=ci_level,
        method="differential_regression_calibration",
        # The remainder IS a variance that study measured, so under the study
        # shape it is what settles the variance premise — one object answering
        # for one number, rather than an id written where nothing can correct
        # it.
        assumptions=_assumptions(
            treatment, adjustment, cluster,
            declared if declared is not None else DeclaredVariance(
                value=float(tracking.residual_variance or 0.0),
                validation_df=tracking.validation_df),
            tracking),
        validation_df=(tracking.validation_df if tracking.studied
                       else declared.validation_df if declared is not None
                       else None),
        tracking_standard_error=tracking.standard_error,
        draws=draws,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        data_columns=contract.columns,
        treatment=treatment, outcome=outcome,
        adjustment=adjustment,
        design_vars=design_vars,
        error_variance=sigma_u,
        differential_by=outcome,
        differential_coefficient=delta,
        nondifferential_variance=parts["nondifferential_variance"],
        outcome_tracking_covariance=parts["outcome_tracking_covariance"],
        exposure_variance=parts["exposure_variance"],
        reliability=parts["reliability"],
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "var_y": float(var_y),
            "error_variance": sigma_u,
            "differential_coefficient": delta,
            "n": int(n),
        },
        cluster=cluster,
    )


# --- formula core -------------------------------------------------------------


def _partialled(Sigma: np.ndarray, cov_Dy: np.ndarray,
                var_y: float) -> tuple[float, float, float]:
    """(A, B, C) — the exposure's and outcome's variances and covariance once
    the adjustment set is partialled out of both.

    Frisch-Waugh is what makes this the whole of the problem: the exposure's
    coefficient in the full design equals its coefficient in this two-column
    one, so the correction is algebra over three scalars however many
    covariates the design carries.
    """
    p = Sigma.shape[0]
    if p == 1:
        return float(Sigma[0, 0]), float(var_y), float(cov_Dy[0])
    rest = list(range(1, p))
    s_oo = Sigma[np.ix_(rest, rest)]
    s_xo = Sigma[0, rest]
    c_oy = cov_Dy[rest]
    solved_x = np.linalg.solve(s_oo, s_xo)
    solved_y = np.linalg.solve(s_oo, c_oy)
    a = float(Sigma[0, 0] - s_xo @ solved_x)
    b = float(var_y - c_oy @ solved_y)
    c = float(cov_Dy[0] - s_xo @ solved_y)
    return a, b, c


def _formula(D: np.ndarray, y: np.ndarray, *, delta: float, exposure: str,
             sigma_u: float | None = None, remainder: float | None = None):
    """βx and the parts it is made of, from the design and the two declarations.

    Exactly one of ``sigma_u`` and ``remainder`` is given, and which one is the
    whole difference between the two declarations. ``sigma_u`` is the TOTAL
    Var(W − X*) pinned by the caller, and σ²_0 = σ²_u − δ²B moves with the
    sample. ``remainder`` is σ²_0 pinned by a validation regression, and σ²_u =
    σ²_0 + δ²B is the one that moves. The algebra below is written on σ²_0
    because that is the quantity both shapes end up agreeing about, and so the
    correction has one form rather than two.

    Returns ``(point, naive, parts, Σ_obs, Cov(D, y), Var(y))``. Raises on a
    singular design, a δ too large for the declared variance, or declarations
    that leave the true exposure no variance.
    """
    Dc = D - D.mean(axis=0)
    yc = y - y.mean()
    n = len(y)
    Sigma = (Dc.T @ Dc) / (n - 1)
    cov_Dy = (Dc.T @ yc) / (n - 1)
    var_y = float((yc @ yc) / (n - 1))

    try:
        a, b, c = _partialled(Sigma, cov_Dy, var_y)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=refusals.Design.DESIGN_COVARIANCE)
    if a <= 0.0:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN,
            design=refusals.Design.DESIGN_COVARIANCE)

    # Before the sample is consulted at all: the two declarations have to be
    # consistent with each other. δ²·B is the variance the outcome-tracking
    # component alone contributes, so a σ²_u smaller than that describes an
    # error whose classical part has negative variance.
    #
    # Unreachable under the study shape, and not by luck: a declaration that
    # names the two INDEPENDENT pieces cannot contradict itself, because σ²_0
    # is stated positive and σ²_u is whatever the two compose to. The
    # contradiction exists only where a caller pins the total and the slope
    # separately, which is the shape that asks them for a number their study
    # did not print.
    if remainder is None:
        assert sigma_u is not None
        nondifferential = sigma_u - delta * delta * b
        if nondifferential <= 0.0:
            raise EstimatorFailure(
                Refusal.DIFFERENTIAL_COEFFICIENT_EXCEEDS_THE_DECLARED_VARIANCE,
                exposure=exposure, declared=sigma_u, coefficient=delta,
                tracking=float(delta * delta * b),
                remainder=float(nondifferential),
            )
    else:
        nondifferential = remainder
        sigma_u = remainder + delta * delta * b

    exposure_variance = a - sigma_u + 2.0 * delta * delta * b - 2.0 * delta * c
    if exposure_variance <= _SIGNAL_FLOOR * max(a, 1.0):
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_CORRECTION_LEAVES_NO_TRUE_VARIANCE,
            exposure=exposure, declared=sigma_u, coefficient=delta,
            observed=float(a), remainder=float(exposure_variance),
        )

    covariance = float(delta * b)
    point = float((c - covariance) / exposure_variance)
    parts = {
        "nondifferential_variance": float(nondifferential),
        "outcome_tracking_covariance": covariance,
        "exposure_variance": float(exposure_variance),
        "reliability": float(exposure_variance / a),
        # What the block reports as σ²_u: the caller's number under one
        # declaration and this sample's composition of the pieces under the
        # other. Returned rather than recomputed by the caller, because the
        # B it is composed with is the one this call partialled out.
        "error_variance": float(sigma_u),
    }
    return point, float(c / a), parts, Sigma, cov_Dy, var_y


def _bootstrap(D: np.ndarray, y: np.ndarray, *,
               declared: DeclaredVariance | None,
               tracking: DeclaredTracking,
               exposure: str, groups: np.ndarray | None, draws: Draws,
               ci_level: float,
               random_state: int) -> tuple[float | None, float | None]:
    """Percentile bootstrap of βx — resample rows (or clusters), redraw what a
    study measured, and recompute. Draws that trip either guard are skipped
    rather than clamped.

    **Nothing a caller pinned is redrawn, and everything a study measured
    is.** This function said, correctly, that resampling a declaration would
    be "widening the interval by re-drawing something nobody drew". What it
    could not see is that a number from a validation study WAS drawn, by that
    study, and the main sample's resample cannot know it. Declaring what the
    study reported is what makes the draw available; where nothing is
    declared nothing is drawn — the old behaviour, rng stream included.

    δ arrives through its own declaration rather than through the variance's,
    and the reason it could not share one is the reason it now has one: a
    regression's slope has no χ² and a variance has no standard error, so one
    field carrying both would be one field meaning two things. What that
    declaration does carry is the pair, drawn together — δ and the error left
    under it come out of a single fit, and drawing them apart would price a
    study that was never run.
    """
    rng = np.random.default_rng(random_state)
    n = len(y)
    pts: list[float] = []
    for _ in draws:
        idx = resample_indices(n, rng, groups=groups)
        delta, remainder = tracking.draw(rng)
        if remainder is None:
            assert declared is not None  # the two shapes are exhaustive
            sigma_u: float | None = declared.draw(rng)
        else:
            sigma_u = None
        try:
            point, *_ = _formula(D[idx], y[idx], sigma_u=sigma_u,
                                 remainder=remainder, delta=delta,
                                 exposure=exposure)
        except EstimatorFailure as exc:
            draws.unusable(exc.failure_type)
            continue
        pts.append(point)
        draws.usable()
    if not draws.enough:
        return None, None
    alpha = (1.0 - ci_level) / 2.0
    return float(np.quantile(pts, alpha)), float(np.quantile(pts, 1 - alpha))


# --- what arrived, judged ------------------------------------------------------


def _refuse_unusable_variance(
    error_variance: object, exposure: str,
) -> DeclaredVariance:
    """σ²_u with its precision, or the refusal that says it is not a number.

    Absence is answered separately from unusability, because the reader's next
    move differs: one supplies a number and the other corrects one.
    """
    if error_variance is None:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="error_variance=",
            remedies=[(Remedy.SUPPLY_INPUT, "error_variance")],
            recorded={"exposure": exposure},
        )
    value = DeclaredVariance.declared_value(error_variance)
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not np.isfinite(value)
        or value <= 0
    ):
        raise EstimatorFailure(
            Refusal.NON_POSITIVE_ERROR_VARIANCE,
            variable=exposure, given=value,
        )
    return DeclaredVariance.read(error_variance)


def _refuse_unusable_coefficient(
    value: object, exposure: str,
) -> DeclaredTracking:
    """δ with its precision, or the refusal that says it is not a number.

    Zero is NOT refused here and is not reachable either: a declared δ of zero
    says the error is non-differential, which is the ordinary correction's
    case, and the route sends it there rather than to an estimator that would
    compute the same number by a longer road. What this rejects is a δ that is
    not a number at all — the STUDY around it is judged where it becomes an
    object, for the reason every declaration in this family is judged there.
    """
    if value is None:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="differential_coefficient=",
            remedies=[(Remedy.SUPPLY_INPUT, "differential_coefficient")],
            recorded={"exposure": exposure},
        )
    coefficient = DeclaredTracking.declared_value(value)
    if (
        not isinstance(coefficient, (int, float))
        or isinstance(coefficient, bool)
        or not np.isfinite(coefficient)
    ):
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_A_NUMBER,
            argument="differential_coefficient=", given=coefficient,
        )
    return DeclaredTracking.read(value)


def _one_declaration_of_the_error(
    error_variance: object, tracking: DeclaredTracking, exposure: str,
) -> tuple[DeclaredVariance | None, float | None, float | None]:
    """Which of the two numbers the caller pinned, and the refusal if both.

    Returns ``(declared, σ²_u, σ²_0)`` with exactly one of the last two set —
    the total under the classical declaration, the remainder under the one
    that carries a validation regression. The regression's shape is what makes
    the choice: it reports σ̂²_0, and σ²_u = σ²_0 + δ²·Var(Ỹ) is then a
    consequence rather than a second declaration. Accepting both would leave
    two numbers for one quantity with no answer to which the correction used,
    and the interval would be the same pair of numbers either way.
    """
    if not tracking.studied:
        declared = _refuse_unusable_variance(error_variance, exposure)
        return declared, declared.value, None
    if error_variance is not None:
        raise EstimatorFailure(
            Refusal.TRACKING_STUDY_AND_A_DECLARED_VARIANCE,
            exposure=exposure,
            variance=DeclaredVariance.declared_value(error_variance),
            remedies=[(Remedy.CHANGE_INPUT, "error_variance=")],
        )
    return None, None, tracking.residual_variance


def _refuse_an_axis_that_is_not_the_outcome(
    axis: object, *, treatment: str, outcome: str, adjustment: tuple[str, ...],
) -> None:
    """Which variable the error tracks, judged against what the geometry allows.

    Three answers rather than one, because the reader's next move differs at
    each. The outcome is the case this module exists for. An adjusted covariate
    is not a smaller case of it: partialling that covariate out of both columns
    leaves ``W̃ = X̃* + f̃``, which is classical, so what that reader needs is the
    ordinary correction and the error's residual variance — a real answer, not a
    scope boundary. Anything else names an axis this correction cannot condition
    on at all.
    """
    if axis is None:
        raise EstimatorFailure(
            Refusal.ARGUMENT_NOT_GIVEN,
            argument="differential_by=",
            remedies=[(Remedy.SUPPLY_INPUT, "differential_by")],
            recorded={"exposure": treatment},
        )
    named = str(axis)
    if named == outcome:
        return
    if named in adjustment:
        raise EstimatorFailure(
            Refusal.DIFFERENTIAL_AXIS_IS_AN_ADJUSTED_COVARIATE,
            axis=named, exposure=treatment,
            remedies=[(Remedy.CHANGE_INPUT, "differential_by=")],
        )
    raise EstimatorFailure(
        Refusal.DIFFERENTIAL_AXIS_IS_NOT_THE_OUTCOME,
        axis=named, outcome=outcome, adjustment=list(adjustment),
    )


def _assumptions(exposure: str, adjustment: tuple[str, ...],
                 cluster: str | None,
                 declared: DeclaredVariance,
                 tracking: DeclaredTracking) -> tuple[str, ...]:
    """The premises, as ids.

    Three of the four are shared with the classical correction word for word,
    and the sharing is the point: this is that correction with one premise
    replaced rather than a separate method. What replaces
    ``design_error_classical_additive_on_`` is a pair, because two facts arrive
    where one used to — THAT the error tracks the outcome, which is untestable
    and holds the point up, and HOW MUCH, which is a number from outside the
    sample that these data can refute one-sidedly.

    Both settled premises are asked of the declaration that settled them, and
    neither is written here. Under the study shape the caller pinned no total
    variance, and the variance premise is still owed and still the studied
    one — the regression measured the remainder σ²_u is composed from, so the
    interval carries that study on both counts. The caller passes the
    remainder AS a declared variance rather than this function spelling the
    id, because an id spelled at a site is one no declaration can correct.
    """
    out = [
        f"design_error_tracks_the_outcome_on_{exposure}",
        declared.premise("design_error_variance", exposure),
        tracking.premise(exposure),
        "linear_structural_outcome_model_in_the_true_values",
    ]
    if adjustment:
        out.append("backdoor_adjustment_{" + ",".join(adjustment) + "}")
    else:
        out.append(
            "unconditional_exchangeability_treatment_is_marginally_randomized")
    if cluster is not None:
        out.append(f"ci_via_pairs_cluster_bootstrap_on_{cluster}")
    return tuple(out)
