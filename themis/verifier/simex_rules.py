"""Independent audit of a SIMEX-corrected coefficient.

The deferral this overturns said simulation-extrapolation "does not fit
the per-number re-derivation contract". It half does, and the half is
exactly where the boundary between the two stages falls.

**Re-derived here, from the recorded ladder alone.** The extrapolant's
coefficients, the point at λ = −1, the extrapolated variance, and the
interval. All four are least-squares problems over ``grid``, so a second
transcription recomputes them without simulating anything and without
importing the producer.

**Not re-derived, and said so rather than implied.** The ladder itself is
a seeded Monte Carlo: reproducible from ``random_state``, not recomputable
by a second author. What can still be checked about it is checked —

- the λ = 0 rung is not a simulation at all. Adding no noise leaves the
  data alone, so that rung IS the naive fit, its replicate variance is
  zero by construction, and it must agree with the ``naive_point`` the
  envelope reports beside it. A forger who moves one has to move both.
- the grid is the ladder it claims: starting at zero, strictly climbing,
  long enough that the declared family is fitting rather than
  interpolating.
- every rung's variance is a variance, and every replicate count above the
  zero rung is the declared one.
- a missing interval is a claim like any other, and the one a forger
  reaches for when a recomputation would not match. Both reasons the
  producer may give are checked against the record rather than accepted
  from it: a non-positive variance has to recompute non-positive, and a
  clustering that kept the variance model-based has to name its column.

What that leaves uncheckable is the honest residue: whether the recorded
θ̂(λ) really is what refitting on that noise would give. It is stated on
the envelope as a simulation, and this audit does not pretend to have
redone it.
"""
from __future__ import annotations

import math

import numpy as np

from .errors import VerificationError

#: Agreement tolerance for a re-derived least-squares quantity. Both routes
#: solve the same small normal equations in double precision; the observed
#: disagreement is at the last bit, so the floor is generous by orders of
#: magnitude and still catches any forgery that changes a number.
_RTOL = 1e-9
_ATOL = 1e-12

#: Same as the producer's: |γ2 − 1| below this puts λ = −1 on the pole.
_POLE = 1e-6

_NEEDS = {"linear": 3, "quadratic": 4, "rational": 4}

#: The two ways an interval can be absent, transcribed rather than imported.
#: Each is a claim about the record, and each is checked against it below.
_VARIANCE_WENT_NON_POSITIVE = "extrapolated_variance_is_not_positive"
_CLUSTERING_IS_NOT_IN_THE_VARIANCE = "declared_clustering_is_not_in_the_variance"
_WITHHOLDINGS = frozenset(
    {_VARIANCE_WENT_NON_POSITIVE, _CLUSTERING_IS_NOT_IN_THE_VARIANCE})


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _require_list(value: object, message: str) -> list:
    if not isinstance(value, list):
        raise VerificationError(message)
    return value


def _require_str(value: object, message: str) -> str:
    if not isinstance(value, str):
        raise VerificationError(message)
    return value


def _require_number(value: object, message: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise VerificationError(message)
    return float(value)


def _require_int(value: object, message: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise VerificationError(message)
    return value


def _agree(recomputed: float, recorded: float, what: str) -> None:
    if not math.isclose(
        float(recomputed), recorded, rel_tol=_RTOL, abs_tol=_ATOL
    ):
        raise VerificationError(
            f"{what}: recorded {recorded!r}, recomputed {float(recomputed)!r}"
        )


def _polynomial(lams: np.ndarray, values: np.ndarray, degree: int):
    """A second transcription: normal equations rather than ``lstsq``.

    Same solution, different route to it — which is the point of writing it
    again on this side.
    """
    design = np.vstack([lams ** k for k in range(degree + 1)]).T
    gram = design.T @ design
    try:
        gamma = np.linalg.solve(gram, design.T @ values)
    except np.linalg.LinAlgError:
        raise VerificationError(
            "the recorded ladder makes the extrapolant's normal equations "
            "singular, so no fit through it is defined"
        )
    at = float(sum(g * (-1.0) ** k for k, g in enumerate(gamma)))
    return tuple(float(g) for g in gamma), at


def _rational(lams: np.ndarray, values: np.ndarray):
    """γ0 + γ1/(γ2+λ) by the same linearisation, solved the same second way."""
    design = np.vstack([lams, np.ones_like(lams), -values]).T
    gram = design.T @ design
    try:
        solved = np.linalg.solve(gram, design.T @ (values * lams))
    except np.linalg.LinAlgError:
        raise VerificationError(
            "the recorded ladder makes the rational extrapolant's normal "
            "equations singular, so no fit through it is defined"
        )
    g0, b, g2 = (float(v) for v in solved)
    g1 = b - g0 * g2
    if abs(g2 - 1.0) < _POLE:
        raise VerificationError(
            f"the recorded ladder fits a rational extrapolant whose pole is "
            f"at λ={-g2!r}, where the answer is read; no value exists there"
        )
    return (g0, g1, g2), float(g0 + g1 / (g2 - 1.0))


def _fit(kind: str, lams: np.ndarray, values: np.ndarray):
    if kind == "linear":
        return _polynomial(lams, values, 1)
    if kind == "quadratic":
        return _polynomial(lams, values, 2)
    return _rational(lams, values)


def verify_simex_numeric(estimate: dict) -> None:
    """Re-derive a ``simex`` estimate's extrapolation from its own ladder.

    Takes the ``numeric_estimate`` block, as every other ``*_numeric``
    audit does, and is called by ``kernel.verify`` on the method name.
    Returns ``None`` when the estimate is not a SIMEX one — the caller
    decides applicability, and this stays quiet on an answer it is not
    about. Raises ``VerificationError`` on a ladder that is not one, on a
    recorded number that disagrees with the recomputation, or on an
    interval that is not the recorded variance read at the recorded level.
    """
    _require(isinstance(estimate, dict), "estimate must be a dict")
    if estimate.get("method") != "simex":
        return
    block = estimate.get("simex")
    _require(
        isinstance(block, dict),
        "a simex estimate must carry the ladder it was extrapolated from",
    )
    assert isinstance(block, dict)  # narrowed by the guard above

    extrapolant = _require_str(
        block.get("extrapolant"), "extrapolant must be a string")
    _require(
        extrapolant in _NEEDS,
        f"unknown extrapolant {extrapolant!r}; expected one of "
        + ", ".join(sorted(_NEEDS)),
    )

    rungs = _require_list(block.get("grid"), "grid must be a list")
    _require(
        len(rungs) >= _NEEDS[extrapolant],
        f"a {extrapolant} extrapolant over {len(rungs)} rungs is "
        f"interpolation, not extrapolation; it needs {_NEEDS[extrapolant]}",
    )
    replicates = _require_int(
        block.get("n_replicates"), "n_replicates must be an integer")
    _require(replicates >= 1, "n_replicates must be at least 1")

    lams: list[float] = []
    thetas: list[float] = []
    taus: list[float] = []
    for i, rung in enumerate(rungs):
        _require(isinstance(rung, dict), f"grid rung {i} must be an object")
        lam = _require_number(rung.get("lambda"), f"grid[{i}].lambda")
        theta = _require_number(rung.get("theta"), f"grid[{i}].theta")
        spread = _require_number(
            rung.get("replicate_variance"), f"grid[{i}].replicate_variance")
        mean_var = _require_number(
            rung.get("variance_mean"), f"grid[{i}].variance_mean")
        count = _require_int(rung.get("replicates"), f"grid[{i}].replicates")
        _require(spread >= 0, f"grid[{i}].replicate_variance is negative")
        _require(mean_var >= 0, f"grid[{i}].variance_mean is negative")
        if i == 0:
            _require(
                lam == 0.0,
                "the ladder must start at λ=0 — that rung is the naive fit, "
                f"and this one starts at {lam!r}",
            )
            _require(
                spread == 0.0,
                "the λ=0 rung has no simulation in it (zero noise leaves the "
                "data alone), so its replicate variance cannot be "
                f"{spread!r}",
            )
            _require(
                count == 1,
                "the λ=0 rung is one fit, not a simulation of "
                f"{count} of them",
            )
            _agree(
                theta,
                _require_number(
                    block.get("naive_point"),
                    "a simex estimate must report the naive point it "
                    "corrected"),
                "the λ=0 rung against the reported naive point",
            )
        else:
            _require(
                lam > lams[-1],
                f"the ladder does not climb: λ={lam!r} follows {lams[-1]!r}",
            )
            _require(
                count == replicates,
                f"grid[{i}] says {count} replicates where the run declares "
                f"{replicates}",
            )
        lams.append(lam)
        thetas.append(theta)
        taus.append(mean_var - spread)

    lam_arr = np.asarray(lams)
    coefficients, point = _fit(extrapolant, lam_arr, np.asarray(thetas))
    recorded_coefficients = [
        _require_number(v, "coefficients must be numbers")
        for v in _require_list(
            block.get("coefficients"), "coefficients must be a list")
    ]
    _require(
        len(recorded_coefficients) == len(coefficients),
        f"a {extrapolant} extrapolant has {len(coefficients)} coefficients, "
        f"not {len(recorded_coefficients)}",
    )
    for i, (got, said) in enumerate(zip(coefficients, recorded_coefficients)):
        _agree(got, said, f"extrapolant coefficient {i}")
    _agree(
        point,
        _require_number(estimate.get("point"), "point must be a number"),
        "the point at λ=−1",
    )

    variance_coefficients, tau_at = _fit(
        extrapolant, lam_arr, np.asarray(taus))
    recorded_variance_coefficients = [
        _require_number(v, "variance_coefficients must be numbers")
        for v in _require_list(
            block.get("variance_coefficients"),
            "variance_coefficients must be a list")
    ]
    for i, (got, said) in enumerate(
        zip(variance_coefficients, recorded_variance_coefficients)
    ):
        _agree(got, said, f"variance extrapolant coefficient {i}")

    declared = block.get("extrapolated_variance")
    lower, upper = estimate.get("ci_lower"), estimate.get("ci_upper")
    reason = block.get("no_interval_because")

    if lower is None and upper is None:
        # Withholding is a claim too, and it is the one a forger reaches for
        # when the recomputation would not match. So the reason has to be
        # true of the record, not merely present in it.
        _require(
            isinstance(reason, str) and reason in _WITHHOLDINGS,
            "an estimate with no interval owes the reader a reason this "
            f"audit can check; it gives {reason!r}",
        )
        _require(
            declared is None,
            "an estimate that shipped no interval has no extrapolated "
            f"variance to declare; it declares {declared!r}",
        )
        if reason == _VARIANCE_WENT_NON_POSITIVE:
            _require(
                tau_at <= 0,
                "the record says the extrapolated variance was not positive, "
                f"and it recomputes to {tau_at!r}",
            )
        else:
            _require(
                bool(block.get("cluster")),
                "the record says a declared clustering kept the variance "
                "model-based, and names no cluster column",
            )
        return

    _require(
        lower is not None and upper is not None,
        "an interval with one endpoint is not one",
    )
    _require(
        reason is None,
        f"an estimate that shipped an interval gives {reason!r} as its "
        "reason for not shipping one",
    )
    _require(
        not block.get("cluster"),
        "a declared cluster column and a model-based interval beside it",
    )
    _require(
        tau_at > 0,
        f"the interval rests on a variance that recomputes to {tau_at!r}",
    )
    _agree(
        tau_at,
        _require_number(declared, "extrapolated_variance must be a number"),
        "the extrapolated variance",
    )

    from scipy import stats

    level = _require_number(
        estimate.get("ci_level"), "ci_level must be a number")
    _require(0 < level < 1, "ci_level must be in (0, 1)")
    half = float(stats.norm.ppf(0.5 + level / 2.0)) * math.sqrt(tau_at)
    _agree(point - half,
           _require_number(lower, "ci_lower must be a number"),
           "the interval's lower endpoint")
    _agree(point + half,
           _require_number(upper, "ci_upper must be a number"),
           "the interval's upper endpoint")
