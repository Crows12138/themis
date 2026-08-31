"""A widening factor's own interval, re-derived from what the block records.

Two blocks price somebody ELSE's interval rather than reporting one. A
declared measurement variance takes a share of the residual, and every
least-squares interval on that design is wider by ``1/√(1−share)`` —
:mod:`themis.verifier.outcome_error_rules` on the outcome's channel,
:mod:`themis.verifier.berkson_rules` on the exposure's, and the two differ
only in what the declared variance is multiplied by before it becomes a
share.

Where a validation study measured that variance, the factor inherits the
study's uncertainty: σ² = σ̂²·df/X with X ~ χ²_df makes it
``1/√(1 − share·df/X)``, monotone decreasing in X, so its endpoints are
exact quantiles of a χ² and nothing here needs a simulation or a grid.

**What that makes checkable is the shape of the answer as much as its
arithmetic.** The upper endpoint is absent for two different reasons — no
study was declared, or the study puts at least the tail an endpoint stands
for on a variance the residual cannot hold — and only the other two fields
tell them apart. A block that reported a finite ceiling in the second case
would be supplying a bound its own declaration does not, which is the one
failure here a reader could not see: an interval of ``[1.08, 7.4]`` and an
interval of ``[1.08, ∞)`` are the same first number.

**Independence pin:** this module restates the construction rather than
importing :meth:`themis.estimation.resample.DeclaredVariance.inflation_interval`.
A ceiling read from the producer's own routine agrees with the producer by
construction.
"""
from __future__ import annotations

import math

from .errors import VerificationError

#: The level the producer prices the factor at. Restated, for the reason in
#: the header: this is the number that decides whether an upper endpoint
#: exists at all, so reading it from the producer would make the shape of
#: the answer self-certifying.
CI_LEVEL = 0.95

_TOL = 1e-6


def check_inflation_under_a_study(
    block: dict, *, where: str, rule: str, noise_share: float,
    absorbed_share: float = 0.0,
) -> None:
    """Hold one block's factor-interval to the study it says measured it.

    ``noise_share`` is re-derived by the caller from the block's own
    moments — not read off it — so the endpoints are checked against the
    arithmetic rather than against the number they were computed from.

    ``absorbed_share`` is the part of the declared variance the design took
    out of the residual before the split, likewise re-derived. It matters
    because the study measured the TOTAL: the redrawn quantity is
    ``share + absorbed``, and what is left in the residual at draw X is
    ``(share + absorbed)·df/X − absorbed``. At zero every expression below is
    the one it was, term for term.

    No-op when the block declares no study, beyond insisting that it then
    reports no interval either: three fields standing where nobody measured
    anything is a precision claim with no source.
    """
    def reject(message: str) -> None:
        raise VerificationError(f"{where}: {message}", rule=rule)

    df = block.get("validation_df")
    lower = block.get("se_inflation_lower")
    upper = block.get("se_inflation_upper")
    said = block.get("inflation_refuted_share")

    if df is None:
        if lower is not None or upper is not None or said is not None:
            reject(
                "no validation study is declared, and the factor is still "
                f"given an interval of ({lower!r}, {upper!r}) with "
                f"{said!r} of a study refuted. A widening priced on a "
                "variance nobody measured has no distribution to have "
                "quantiles of"
            )
        return

    if isinstance(df, bool) or not isinstance(df, int) or df < 1:
        reject(f"validation_df must be a positive whole number; got {df!r}")

    from scipy import stats

    tail = (1.0 - CI_LEVEL) / 2.0
    total = noise_share + absorbed_share
    refuted = float(stats.chi2.cdf(df * total / (1.0 + absorbed_share), df))
    if not isinstance(said, (int, float)) or isinstance(said, bool) or not (
            math.isclose(float(said), refuted, rel_tol=_TOL, abs_tol=1e-12)):
        reject(
            f"inflation_refuted_share is {said!r}; a study of {df} degrees "
            f"of freedom behind a noise share of {noise_share!r} puts "
            f"{refuted!r} of its own distribution on a variance this "
            "residual cannot hold"
        )

    def factor(x: float) -> float:
        left = 1.0 - (total * df / x - absorbed_share)
        if left <= 0:
            reject("the endpoint quantile sits where the factor is undefined")
        return 1.0 / math.sqrt(left)

    want_lower = factor(float(stats.chi2.ppf(1.0 - tail, df)))
    if not isinstance(lower, (int, float)) or isinstance(lower, bool) or not (
            math.isclose(float(lower), want_lower, rel_tol=_TOL,
                         abs_tol=_TOL)):
        reject(f"se_inflation_lower is {lower!r}; it re-derives to "
               f"{want_lower!r}")

    if refuted >= tail:
        if upper is not None:
            reject(
                f"{refuted!r} of the declared study sits on a variance this "
                f"residual cannot hold, which is past the {tail!r} tail an "
                f"endpoint stands for — and the block still reports a "
                f"ceiling of {upper!r}. The widening is bounded below and "
                "not above, and a number there is a bound the study does "
                "not supply"
            )
        return

    want_upper = factor(float(stats.chi2.ppf(tail, df)))
    if not isinstance(upper, (int, float)) or isinstance(upper, bool) or not (
            math.isclose(float(upper), want_upper, rel_tol=_TOL,
                         abs_tol=_TOL)):
        reject(f"se_inflation_upper is {upper!r}; it re-derives to "
               f"{want_upper!r}")
