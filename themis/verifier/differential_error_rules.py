"""Independent audit of the differential-error correction.

The block records six scalars and the moments they came from, and every one
of the six is re-derived here. What makes the audit worth having is that the
correction moves the answer in TWO places where the classical one moves it
in one — the covariance is un-inflated by δ·B before the variance is
un-inflated by σ²_u — so a producer that applied only the second would
return a number that is internally consistent with every reliability ratio a
reader might check by hand, and wrong.

**A second transcription, not a second call.** The producer reaches the
partialled quantities by Schur complements: solve the covariate block against
the exposure's and the outcome's cross-covariances and subtract. This one
inverts the JOINT covariance of (exposure, covariates, outcome), takes the
2×2 sub-block of the precision matrix belonging to (exposure, outcome), and
inverts that — the identity that the inverse of a precision sub-block is the
conditional covariance. Same three numbers, no shared line of code, and an
arithmetic slip in either shows up as disagreement rather than as agreement
with itself.

**Independence pin:** this module MUST NOT import from
``themis.estimation``. Everything it needs is on the block.
"""
from __future__ import annotations

import math
from typing import NoReturn

import numpy as np

from .declaration_rules import (
    DIFFERENTIAL_COEFFICIENT, VARIANCE, check_declaration_premises,
)
from .errors import VerificationError

_RULE = "differential_error_check"
_RTOL = 1e-9
_ATOL = 1e-12

#: The method name whose blocks this audits. Restated rather than imported,
#: for the reason in the header.
METHOD = "differential_regression_calibration"


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def _number(value: object, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        _reject(f"{what} must be a number; got {value!r}")
    return float(value)


def _agree(recomputed: float, recorded: float, what: str) -> None:
    if not math.isclose(recomputed, recorded, rel_tol=_RTOL,
                        abs_tol=_ATOL + _RTOL * abs(recomputed)):
        _reject(f"{what}: recorded {recorded!r}, recomputed {recomputed!r}")


def verify_differential_error_numeric(estimate: dict) -> None:
    """Re-derive a differential correction from its own recorded moments.

    Takes the ``numeric_estimate``. Returns ``None`` when the estimate was
    produced by some other method. Raises ``VerificationError`` when a
    reported scalar does not follow from the recorded moments and the two
    declarations, when a declaration the block ships would have had to be
    refused, or when the block's own summary of what it did disagrees with
    the arithmetic behind it.
    """
    if not isinstance(estimate, dict):
        _reject("numeric_estimate must be a dict")
    if estimate.get("method") != METHOD:
        return
    block = estimate.get("differential_error")
    if not isinstance(block, dict):
        _reject(
            "a differential_regression_calibration estimate carries no "
            "differential_error block, so there is nothing to re-derive it "
            "from and the point stands on the producer's word alone"
        )

    stats = block.get("sufficient_statistics")
    if not isinstance(stats, dict):
        _reject("sufficient_statistics is missing")

    names = stats.get("design_vars")
    if not isinstance(names, list) or not names:
        _reject("sufficient_statistics.design_vars is missing")
    p = len(names)
    if str(names[0]) != str(estimate.get("treatment")):
        _reject(
            f"the design leads with {names[0]!r} and the estimate is about "
            f"{estimate.get('treatment')!r}; the correction is written for "
            f"the exposure's own slope, so a design that does not lead with "
            f"it corrects a coefficient on another column"
        )

    sigma = _square(stats.get("cov_matrix"), p)
    cov_dy = _vector(stats.get("cov_design_y"), p, "cov_design_y")
    var_y = _number(stats.get("var_y"), "var_y")
    sigma_u = _number(stats.get("error_variance"), "error_variance")
    delta = _number(stats.get("differential_coefficient"),
                    "differential_coefficient")
    if sigma_u <= 0:
        _reject(f"an error variance of {sigma_u!r} is not one")
    if delta == 0.0:
        _reject(
            "a differential coefficient of 0 says the error is "
            "non-differential, which is the ordinary correction's case; a "
            "block claiming this method for it took the long road to a "
            "number the short one already gives"
        )

    a, b, c = _conditional(sigma, cov_dy, var_y)
    if a <= 0:
        _reject(f"the exposure's conditional variance recomputes to {a!r}")

    # The two declarations against each other, then against the sample. A
    # block that shipped through either of these shipped a variance that is
    # not one, and the reader cannot see that from the point alone.
    nondifferential = sigma_u - delta * delta * b
    if nondifferential <= 0:
        _reject(
            f"the declared σ²_u={sigma_u!r} and δ={delta!r} leave the error's "
            f"classical part at {nondifferential!r}, which is not a variance; "
            f"this block should not exist"
        )
    exposure_variance = (
        a - sigma_u + 2.0 * delta * delta * b - 2.0 * delta * c)
    if exposure_variance <= 0:
        _reject(
            f"the declarations leave the true exposure a conditional variance "
            f"of {exposure_variance!r}, and the reported slope is taken over "
            f"it; this block should not exist"
        )

    tracking = delta * b
    _agree(nondifferential,
           _number(block.get("nondifferential_variance"),
                   "nondifferential_variance"),
           "what is left of the declared error once its outcome-tracking "
           "part is removed")
    _agree(tracking,
           _number(block.get("outcome_tracking_covariance"),
                   "outcome_tracking_covariance"),
           "how much of the observed covariance is error rather than effect")
    _agree(exposure_variance,
           _number(block.get("exposure_variance"), "exposure_variance"),
           "the true exposure's conditional variance")
    _agree(exposure_variance / a,
           _number(block.get("reliability"), "reliability"),
           "the share of the observed conditional variance that is signal")
    _agree(c / a, _number(block.get("naive_point"), "naive_point"),
           "the uncorrected slope the correction replaces")

    # The point last, and re-derived from the parts rather than from the
    # parts as recorded: a producer that got a part wrong and a point right
    # would otherwise pass on the point and fail on the part, which reads as
    # a bookkeeping slip rather than as what it is.
    _agree((c - tracking) / exposure_variance,
           _number(estimate.get("point"), "point"),
           "the corrected exposure slope")

    _check_the_axis_is_the_outcome(estimate, block)

    # The arithmetic above is the same however the two were declared — it is
    # the INTERVAL that differs, and no recorded moment can reproduce a
    # bootstrap. So what is left to check is that the block's record of what a
    # study measured and the premises the estimate declares are the same
    # story, on both declarations. δ is one of them now: its sampling
    # distribution is not the variance's χ² and never was, which is why it
    # arrives through a regression's standard error and degrees of freedom
    # rather than through the variance's field.
    #
    # Each keyed on the field that RECORDS the study rather than on the
    # premise, and on a different field for each, because the two can be
    # declared apart: a δ fixed by protocol beside a σ²_u a substudy measured
    # is a run this block can carry, and a check keyed on one field for both
    # would read that run as declaring neither or both.
    exposure = str(block.get("exposure"))
    check_declaration_premises(
        VARIANCE,
        rule=_RULE,
        declared=estimate.get("assumptions") or (),
        measured=[exposure],
        carried=({exposure: block["validation_df"]}
                 if block.get("validation_df") is not None else {}),
    )
    check_declaration_premises(
        DIFFERENTIAL_COEFFICIENT,
        rule=_RULE,
        declared=estimate.get("assumptions") or (),
        measured=[exposure],
        carried=({exposure: block["tracking_standard_error"]}
                 if block.get("tracking_standard_error") is not None else {}),
    )


def _check_the_axis_is_the_outcome(estimate: dict, block: dict) -> None:
    """δ is the coefficient of the OUTCOME's residual, and the block says so.

    Not a formality: the same arithmetic run with δ read as a coefficient on
    some other column would be a different correction with the same numbers
    in it, and ``differential_by`` is the only place the block says which
    variable the reader is being asked to believe the error tracks. The
    exposure is checked the same way and for the same reason — the block
    names one, the estimate names one, and a pair that disagrees describes a
    correction of some column other than the one the answer is about.
    """
    axis = block.get("differential_by")
    outcome = estimate.get("outcome")
    if axis != outcome:
        _reject(
            f"the block says the error tracks {axis!r} while the estimate is "
            f"of an effect on {outcome!r}; δ enters the arithmetic as a "
            f"coefficient on the OUTCOME's residual, so a block naming any "
            f"other axis describes a correction other than the one it did"
        )
    if block.get("exposure") != estimate.get("treatment"):
        _reject(
            f"the block corrects {block.get('exposure')!r} and the estimate "
            f"is of an effect of {estimate.get('treatment')!r}"
        )


def _square(rows: object, n: int) -> np.ndarray:
    if not isinstance(rows, list) or len(rows) != n:
        _reject(f"cov_matrix must be a {n}x{n} matrix")
    out = []
    for row in rows:
        if not isinstance(row, list) or len(row) != n:
            _reject(f"cov_matrix must be a {n}x{n} matrix")
        out.append([_number(v, "cov_matrix entry") for v in row])
    m = np.array(out, dtype=float)
    if not np.allclose(m, m.T, rtol=_RTOL, atol=_ATOL):
        _reject("cov_matrix is not symmetric, so it is not a covariance")
    return m


def _vector(values: object, n: int, what: str) -> np.ndarray:
    if not isinstance(values, list) or len(values) != n:
        _reject(f"{what} must have {n} entries")
    return np.array([_number(v, f"{what} entry") for v in values], dtype=float)


def _conditional(sigma: np.ndarray, cov_dy: np.ndarray,
                 var_y: float) -> tuple[float, float, float]:
    """(A, B, C) — Var(W|Z), Var(Y|Z), Cov(W, Y|Z) — by precision inversion.

    The producer subtracts Schur complements. This assembles the joint
    covariance of (W, Z…, Y), inverts it, and inverts the 2×2 sub-block
    belonging to (W, Y): the inverse of a precision sub-block IS the
    conditional covariance of those variables given the rest. Linear algebra
    rather than an assumption about the distribution, and a different
    arithmetic path to the same three numbers.
    """
    p = sigma.shape[0]
    joint = np.empty((p + 1, p + 1), dtype=float)
    joint[:p, :p] = sigma
    joint[:p, p] = cov_dy
    joint[p, :p] = cov_dy
    joint[p, p] = var_y
    try:
        precision = np.linalg.inv(joint)
        pair = np.linalg.inv(precision[np.ix_([0, p], [0, p])])
    except np.linalg.LinAlgError:
        _reject(
            "the recorded joint covariance of the design and the outcome is "
            "singular, so the conditional quantities the correction is built "
            "from do not exist"
        )
    return float(pair[0, 0]), float(pair[1, 1]), float(pair[0, 1])
