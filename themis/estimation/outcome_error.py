"""Classical measurement error on a CONTINUOUS OUTCOME — what it costs.

The third role a mismeasured variable can play, and the only one that costs no
bias. Where the exposure channel loses the effect to regression dilution and a
mismeasured covariate leaves residual confounding, a classical additive error on
the outcome — Y = Y* + V with E[V | X, Z, Y*] = 0 — leaves **every conditional
mean unchanged**. Every estimand this package reports on a continuous outcome is
built from conditional means (a back-door contrast, a Wald ratio, a front-door
sum, a natural-effect decomposition), so none of them moves. There is nothing to
de-attenuate.

What it does cost is precision, and that cost is knowable rather than merely
lamentable, because σ²_v is supplied. The residual variance of the observed
outcome around its model splits exactly:

    Var(Y | D) = Var(Y* | D) + σ²_v

so the standard error of every least-squares functional of that design is
inflated by the fixed factor

    se_inflation = sqrt( Var(Y | D) / (Var(Y | D) − σ²_v) )

— the interval the study actually reports, divided by the interval the same
design would have reported had the outcome been measured without error. That is
the actionable answer to "should I collect more subjects or measure better".

The split is also refutable, which is the point of computing it. σ²_v ≥
Var(Y | D) says the declared measurement noise does not fit underneath the
unexplained variation the data actually show. One of three things is then false
— the declared variance, the linearity of the outcome model, or the
independence of the error from the design — and the last of those is precisely
the premise under which the point estimate was safe. So the assessment refuses
rather than reporting a negative signal variance.

Deliberately out of scope, each refused by name rather than absorbed: a
DISCRETE outcome (that is misclassification, a different object with a different
correction — ``misclassification=``), and differential / Berkson error (the
spec has no way to declare either, so accepting one silently would be inventing
a premise the caller never made).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .contract import validate_data
from .. import refusals
from ..refusals import EstimatorFailure
# Shared with regression calibration on purpose: "how many distinct values before
# a column stops being a misclassification object" is one decision, and the two
# channels must route the same variable the same way.
from .regression_calibration import _MIN_CONTINUOUS_DISTINCT

# Signal variance at or below this share of the residual ⇒ the declared error
# swallows the model's unexplained variation ⇒ refuse rather than report a
# meaningless inflation factor.
_SIGNAL_FLOOR = 1e-9


@dataclass(frozen=True)
class OutcomeErrorAssessment:
    """What a known classical outcome-error variance implies for one query.

    ``residual_variance`` is Var(Y | D) — the unexplained variance of the
    OBSERVED outcome around the linear projection on the design D = (exposure,
    *adjustment). ``signal_variance`` is what remains of it once the declared
    measurement noise is removed, ``noise_share`` the fraction of the
    unexplained variation that is pure measurement, and ``se_inflation`` the
    factor by which that noise widens every least-squares interval on this
    design. ``sufficient_statistics`` carries Σ_D, Cov(D, Y), Var(Y), σ²_v and
    n — everything the verifier re-derives the split from without the data.
    """
    outcome: str
    treatment: str
    design_vars: tuple[str, ...]
    error_variance: float
    residual_variance: float
    signal_variance: float
    noise_share: float
    se_inflation: float
    sample_size: int
    data_hash: str
    assumptions: tuple[str, ...] = ()
    sufficient_statistics: dict = field(default_factory=dict)


def assess_outcome_error(
    data: pd.DataFrame,
    *,
    treatment: str,
    outcome: str,
    adjustment: tuple[str, ...],
    error_variance: float,
) -> OutcomeErrorAssessment:
    """Split the observed outcome's residual variance into signal and declared
    measurement noise, and report what the noise costs in precision.

    Parameters
    ----------
    data: the sample carrying the observed (error-prone) outcome.
    treatment / outcome: this query's exposure and continuous outcome columns.
    adjustment: the back-door covariates; together with ``treatment`` they are
        the design the outcome is projected on.
    error_variance: the KNOWN classical additive error variance σ²_v of the
        outcome (validation study / repeat measurement).

    Raises
    ------
    EstimatorFailure: a non-positive or non-finite σ²_v; a near-discrete
        outcome (a misclassification object, not a continuously-mismeasured
        one); a singular design; or a σ²_v that meets or exceeds the observed
        residual variance.
    """
    if (
        not isinstance(error_variance, (int, float))
        or isinstance(error_variance, bool)
        or not np.isfinite(error_variance)
        or error_variance <= 0
    ):
        raise EstimatorFailure(
            refusals.NON_POSITIVE_ERROR_VARIANCE,
            f"the classical measurement-error variance σ²_v for the outcome "
            f"{outcome!r} must be a positive finite number; got "
            f"{refusals.describe(error_variance)}.",
        )

    adjustment = tuple(adjustment)
    contract = validate_data(
        data, required_columns={treatment, outcome, *adjustment},
    )
    df = contract.data

    n_distinct = int(df[outcome].dropna().nunique())
    if n_distinct < _MIN_CONTINUOUS_DISTINCT:
        raise EstimatorFailure(
            refusals.OUTCOME_NOT_CONTINUOUS,
            f"outcome {outcome!r} has only {n_distinct} distinct values; an "
            f"additive error variance describes a CONTINUOUS measurement. A "
            f"discrete outcome is a misclassification object, and its error "
            f"does attenuate the effect — supply a validated confusion matrix "
            f"(misclassification=) instead, which corrects it.",
        )

    design_vars = (treatment, *adjustment)
    D = np.column_stack([df[v].to_numpy(dtype=float) for v in design_vars])
    y = df[outcome].to_numpy(dtype=float)
    n = len(df)

    Dc = D - D.mean(axis=0)
    yc = y - y.mean()
    Sigma = (Dc.T @ Dc) / (n - 1)
    cov_Dy = (Dc.T @ yc) / (n - 1)
    var_y = float(yc @ yc / (n - 1))

    try:
        b = np.linalg.solve(Sigma, cov_Dy)
    except np.linalg.LinAlgError:
        raise EstimatorFailure(
            refusals.SINGULAR_DESIGN,
            "the design covariance Σ_D is singular (collinear covariates); the "
            "outcome's residual variance is undefined.",
        )
    residual_variance = var_y - float(cov_Dy @ b)

    error_variance = float(error_variance)
    signal_variance = residual_variance - error_variance
    if signal_variance <= _SIGNAL_FLOOR * max(residual_variance, 1.0):
        raise EstimatorFailure(
            refusals.OUTCOME_ERROR_EXCEEDS_RESIDUAL_VARIANCE,
            f"the declared outcome error variance σ²_v = {error_variance:.6g} "
            f"meets or exceeds the observed residual variance Var({outcome}|D) "
            f"= {residual_variance:.6g}. The noise does not fit underneath the "
            f"variation the data leave unexplained, so at least one of the "
            f"declared variance, the linearity of the outcome model, and the "
            f"independence of the error from the design is false — and that "
            f"last one is what makes the point estimate immune to the error. "
            f"No assessment is issued.",
        )

    noise_share = error_variance / residual_variance
    se_inflation = float(np.sqrt(residual_variance / signal_variance))

    return OutcomeErrorAssessment(
        outcome=outcome,
        treatment=treatment,
        design_vars=design_vars,
        error_variance=error_variance,
        residual_variance=residual_variance,
        signal_variance=signal_variance,
        noise_share=noise_share,
        se_inflation=se_inflation,
        sample_size=contract.sample_size,
        data_hash=contract.data_hash,
        assumptions=_assumptions(outcome),
        sufficient_statistics={
            "design_vars": list(design_vars),
            "cov_matrix": [[float(v) for v in row] for row in Sigma],
            "cov_design_y": [float(v) for v in cov_Dy],
            "var_y": var_y,
            "error_variance": error_variance,
            "n": int(n),
        },
    )


def _assumptions(outcome: str) -> tuple[str, ...]:
    """The two premises, and only the premises.

    What the split *implies* — that the point needs no correction, that the
    interval carries a fixed amount of measurement — is a consequence, and
    consequences belong in the block's numbers and in what the renderer says
    about them, not in a list of things that could be false. Mixing the two
    would put a derived quantity on the disclosure surface at the severity
    reserved for a premise whose failure kills the answer.
    """
    return (
        f"outcome_error_classical_non_differential_on_{outcome}",
        f"outcome_error_variance_known_and_fixed_on_{outcome}",
    )
