"""Independent audit of the continuous-outcome measurement-error assessment.

The assessment is unusual among the numeric blocks in this package: it changes
no number. Its whole content is a claim about what a declared σ²_v does and does
not cost — the point is immune, the interval is not — and both halves of that
claim are only as good as the premises attached to them. So this module audits
two things, and the second is the one that matters.

**The arithmetic**, which is fully re-derivable: the split is a closed-form
function of Σ_D, Cov(D, Y), Var(Y) and σ²_v, all recorded. Every reported
scalar — residual variance, signal variance, noise share, inflation factor — is
recomputed here from those statistics alone and must agree. A block whose
inflation factor was copied from a neighbouring run does not survive it.

**The disclosure**, which is one-sided in the way this package's other audit
surfaces are. The reason no correction was applied is that the error is
non-differential; if it is differential the point estimate is biased and the
answer is wrong. That premise therefore has to reach the reader on the surface
readers are given — the assumption ledger — and an assessment whose premises
stop at its own block is indistinguishable, downstream, from an answer that
assumed nothing. Silence is the defect.

It also rejects the mirror failure: an assessment computed on a design that is
not the design the estimate reports having used. That block would be arithmetic
about one model attached to a number from another.

What it deliberately does NOT audit: whether Σ_D and Var(Y) are the moments of
the data actually analysed. Re-deriving them needs the sample, which is the
data-refit ceiling every numeric verifier here stops at.

**Independence pin:** this module MUST NOT import from ``themis.estimation`` —
it re-derives what is owed from the envelope alone.
"""
from __future__ import annotations

import math

from .errors import VerificationError

_RULE = "outcome_error_check"
_TOL = 1e-6


def _reject(message: str) -> None:
    raise VerificationError(message, rule=_RULE)


def _close(a: float, b: float, scale: float = 1.0) -> bool:
    return abs(a - b) <= _TOL * max(1.0, abs(scale))


def verify_outcome_error(result: dict) -> None:
    """Audit one result's outcome measurement-error assessment.

    No-op when the result carries none. Raises :class:`VerificationError` when
    a reported scalar does not follow from the recorded sufficient statistics,
    when the assessed design disagrees with the estimate's, or when the
    premises never reach the assumption ledger.
    """
    block = result.get("outcome_error")
    if not isinstance(block, dict):
        return

    stats = block.get("sufficient_statistics")
    if not isinstance(stats, dict):
        _reject("outcome_error carries no sufficient_statistics to re-derive from")

    residual = _recompute_residual_variance(stats)
    sigma_v = _as_float(stats.get("error_variance"), "sufficient_statistics.error_variance")

    if not _close(sigma_v, _as_float(block.get("error_variance"), "error_variance")):
        _reject(
            f"outcome_error.error_variance {block.get('error_variance')!r} "
            f"disagrees with the σ²_v recorded in its own sufficient "
            f"statistics ({sigma_v!r})"
        )
    if sigma_v <= 0:
        _reject(
            f"outcome_error declares a non-positive error variance {sigma_v!r}; "
            "a classical additive error variance is positive by definition"
        )

    _check_scalar(block, "residual_variance", residual)

    signal = residual - sigma_v
    if signal <= 0:
        _reject(
            f"outcome_error reports σ²_v = {sigma_v:.6g} against a residual "
            f"variance of {residual:.6g}: the declared measurement noise does "
            "not fit under the unexplained variation, so the independence "
            "premise that makes the point estimate immune to the error is "
            "itself refuted. Such an assessment must be refused, not issued"
        )
    _check_scalar(block, "signal_variance", signal)
    _check_scalar(block, "noise_share", sigma_v / residual)
    _check_scalar(block, "se_inflation", math.sqrt(residual / signal))

    _check_design(block, stats, result)
    _check_disclosure(block, result)


# --- arithmetic ---------------------------------------------------------------


def _as_float(value, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        _reject(f"outcome_error.{label} must be a number; got {value!r}")
    return float(value)


def _check_scalar(block: dict, key: str, expected: float) -> None:
    got = _as_float(block.get(key), key)
    if not _close(got, expected, scale=expected):
        _reject(
            f"outcome_error.{key} = {got!r} does not follow from the recorded "
            f"sufficient statistics; re-derived {expected!r}"
        )


def _recompute_residual_variance(stats: dict) -> float:
    """Var(Y|D) = Var(Y) − Cov(D,Y)' Σ_D⁻¹ Cov(D,Y), solved here from scratch.

    Gaussian elimination with partial pivoting rather than a linear-algebra
    dependency: the point of re-deriving is to not share code with the
    producer, and a 1–5 column design does not need more.
    """
    sigma = stats.get("cov_matrix")
    cov_dy = stats.get("cov_design_y")
    var_y = _as_float(stats.get("var_y"), "sufficient_statistics.var_y")
    if not isinstance(sigma, list) or not isinstance(cov_dy, list) or not sigma:
        _reject("outcome_error.sufficient_statistics is missing Σ_D / Cov(D,Y)")
    p = len(sigma)
    if len(cov_dy) != p or any(not isinstance(r, list) or len(r) != p for r in sigma):
        _reject(
            f"outcome_error.sufficient_statistics: Σ_D is {p}×? and Cov(D,Y) has "
            f"{len(cov_dy)} entries; the two must share the design's dimension"
        )
    for i in range(p):
        for j in range(i + 1, p):
            if not _close(float(sigma[i][j]), float(sigma[j][i]), scale=sigma[i][j]):
                _reject(
                    f"outcome_error.sufficient_statistics.cov_matrix is not "
                    f"symmetric at ({i},{j}); it is not a covariance matrix"
                )
    beta = _solve([[float(v) for v in row] for row in sigma],
                  [float(v) for v in cov_dy])
    explained = sum(c * b for c, b in zip(cov_dy, beta))
    residual = var_y - explained
    if residual <= 0:
        _reject(
            f"outcome_error: the recorded moments give a non-positive residual "
            f"variance {residual:.6g} (Var(Y) = {var_y:.6g}); the outcome cannot "
            "be less variable than its own projection"
        )
    return residual


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            _reject(
                "outcome_error.sufficient_statistics.cov_matrix is singular; the "
                "residual variance it is supposed to define does not exist"
            )
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(n):
            if r == col:
                continue
            f = m[r][col] / m[col][col]
            for c in range(col, n + 1):
                m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


# --- cross-source -------------------------------------------------------------


def _check_design(block: dict, stats: dict, result: dict) -> None:
    """The design assessed must be the design estimated."""
    design = block.get("design_vars")
    if not isinstance(design, list) or not design:
        _reject("outcome_error.design_vars is missing or empty")
    if list(stats.get("design_vars") or ()) != design:
        _reject(
            f"outcome_error.design_vars {design!r} disagrees with the design "
            f"recorded in its sufficient statistics "
            f"{stats.get('design_vars')!r}"
        )
    if design[0] != block.get("treatment"):
        _reject(
            f"outcome_error.design_vars starts with {design[0]!r} but the "
            f"assessed treatment is {block.get('treatment')!r}; the exposure "
            "heads the design"
        )
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    if estimate.get("outcome") is not None and estimate["outcome"] != block.get("outcome"):
        _reject(
            f"outcome_error assesses {block.get('outcome')!r} but the estimate "
            f"on this result is of {estimate['outcome']!r}"
        )
    adjustment = estimate.get("adjustment")
    if isinstance(adjustment, list) and sorted(adjustment) != sorted(design[1:]):
        _reject(
            f"outcome_error was assessed on the design {design!r}, but the "
            f"estimate adjusts for {sorted(adjustment)!r}; the variance split "
            "describes a model this answer did not fit"
        )


def _check_disclosure(block: dict, result: dict) -> None:
    """Every premise the assessment rests on must reach the assumption ledger —
    the surface the report and the rendering bridge lead with."""
    declared = [a for a in (block.get("assumptions") or ()) if isinstance(a, str)]
    if not declared:
        _reject(
            "outcome_error declares no assumptions: the point estimate is left "
            "uncorrected only because the error is non-differential, and an "
            "assessment that states no premise claims that for free"
        )
    if not isinstance(result.get("numeric_estimate"), dict):
        return  # no answer to qualify
    ledger = (result.get("extensions") or {}).get("assumption_ledger") or {}
    on_ledger = {
        str(e.get("id")) for e in (ledger.get("assumptions") or ())
        if isinstance(e, dict)
    }
    missing = [a for a in declared if a not in on_ledger]
    if missing:
        _reject(
            f"{len(missing)} of the outcome-error assessment's premises never "
            f"reach the assumption ledger (first: {missing[0]!r}). An answer "
            "whose premises stop at a side block is, to every consumer, an "
            "answer that assumed nothing — and the premise held back here is "
            "the one that makes the uncorrected point defensible"
        )
