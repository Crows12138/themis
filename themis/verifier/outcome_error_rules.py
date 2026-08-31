"""Independent audit of the continuous-outcome measurement-error assessment.

The assessment is unusual among the numeric blocks in this package: it changes
no number. Its whole content is a claim about what a declared σ²_v does and does
not cost — the point is immune, the interval is not — and both halves of that
claim are only as good as the premises attached to them. So this module audits
two things, and the second is the one that matters.

**The arithmetic**, which is fully re-derivable: the residual the split is taken
out of is Var(Y − b'D) = Var(Y) − 2 b'Cov(D,Y) + b'Σ_D b, a closed-form function
of Σ_D, Cov(D, Y), Var(Y) and the coefficient vector b, all recorded. Every
reported scalar — residual variance, signal variance, noise share, inflation
factor — is recomputed here from those statistics alone and must agree. A block
whose inflation factor was copied from a neighbouring run does not survive it.

The general quadratic form rather than the OLS closed form Var(Y) − c'Σ_D⁻¹c it
reduces to, because b is not always an OLS solution: one design takes the
residual around a coefficient the estimator that answered supplied, and there
the reduced form is arithmetic about a model nobody fitted. What IS re-derived
is every coefficient the design does not leave free — the normal equations must
hold on every row but the exposure's, and on that one too wherever the design
does not source it from outside.

**The disclosure**, which is one-sided in the way this package's other audit
surfaces are. The reason no correction was applied is that the error is
non-differential; if it is differential the point estimate is biased and the
answer is wrong. That premise therefore has to reach the reader on the surface
readers are given — the assumption ledger — and an assessment whose premises
stop at its own block is indistinguishable, downstream, from an answer that
assumed nothing. Silence is the defect. WHICH premises they are is a fact about
the design and not a wider or narrower version of one premise, so the design's
own are required by name: the route that rests on the instrument may not reach
the reader claiming the classical premise instead, and the route whose graph
posits an unmeasured confounder may not drop the one premise about it that no
data can refute and that moves the POINT, not the interval, when it fails.

It also rejects the mirror failure: an assessment computed on a design that is
not the design the estimate reports having used. That block would be arithmetic
about one model attached to a number from another.

What it deliberately does NOT audit: whether Σ_D and Var(Y) are the moments of
the data actually analysed. Re-deriving them needs the sample, which is the
data-refit ceiling every numeric verifier here stops at.

**Independence pin:** this module MUST NOT import from ``themis.estimation`` —
it re-derives what is owed from the envelope alone. The design vocabulary below
is therefore re-declared rather than imported; that the two copies must be kept
equal is the point, since a rename that reaches only one of them is caught here
loudly instead of being agreed to silently.
"""
from __future__ import annotations

import math
from typing import NamedTuple, NoReturn

from .declaration_rules import (
    OUTCOME_ERROR_VARIANCE, check_declaration_premises,
)
from .errors import VerificationError
from .inflation_rules import check_inflation_under_a_study

_RULE = "outcome_error_check"
_TOL = 1e-6


#: The premise a design owes about the error itself, in its two spellings.
#: WHICH one is owed is not a property of the design: it turns on whether the
#: caller withdrew the non-differential premise by declaring that the error
#: tracks the exposure. Both are listed against each design that owes one so
#: that the wrong one can be rejected by name — an assessment that split its
#: variance on a declared δ and still told the reader the error moves no
#: conditional mean would be contradicting its own arithmetic on the surface
#: the reader is given.
_CLASSICAL = "outcome_error_classical_non_differential"
_CLASSICAL_UNDER_DELTA = (
    "outcome_error_classical_once_the_exposure_is_partialled_out")


class _Design(NamedTuple):
    """What one design answers to the questions that separate the routes.

    Everything a route needs from this module follows from these: which
    coefficient it is allowed to source from outside the normal equations,
    which key of the numeric block names the columns it carries besides the
    exposure, whether those names reach the design expanded into indicators,
    and which premises it owes the reader.
    """

    name: str
    exposure_coefficient_is_free: bool
    names_the_rest: str
    carried_as_indicators: bool
    premises: tuple[str, ...]


_DESIGNS: dict[str, _Design] = {
    design.name: design
    for design in (
        _Design(
            "back_door", False, "adjustment", False,
            (_CLASSICAL,),
        ),
        _Design(
            "instrumental_variable", True, "conditioning", False,
            # E[V | Z] = 0 is a claim about the INSTRUMENT, so the id carries
            # the instrument's name and only its stem can be matched here.
            ("outcome_error_mean_independent_of_instrument_",),
        ),
        _Design(
            "front_door", False, "mediators", True,
            (_CLASSICAL,
             "outcome_error_independent_of_the_front_door_latent_confounder"),
        ),
    )
}

# The one premise no design escapes — every number in the block is arithmetic
# on a σ²_v the caller declared and nothing here estimated — is not in this
# table, because it is the one premise that is not a function of the design.
# Which of its two spellings is owed depends on whether a study measured σ²_v,
# and that is asked of :mod:`themis.verifier.declaration_rules` from the
# block's own ``validation_df``.


def _reject(message: str) -> NoReturn:
    raise VerificationError(message, rule=_RULE)


def _close(a: float, b: float, scale: float = 1.0) -> bool:
    return abs(a - b) <= _TOL * max(1.0, abs(scale))


def verify_outcome_error(result: dict) -> None:
    """Audit one result's outcome measurement-error assessment.

    No-op when the result carries none. Raises :class:`VerificationError` when
    a reported scalar does not follow from the recorded sufficient statistics,
    when the coefficients the residual was taken around are not the ones the
    named design fixes, when the assessed design disagrees with the estimate's,
    or when the premises never reach the assumption ledger.
    """
    block = result.get("outcome_error")
    if not isinstance(block, dict):
        return

    stats = block.get("sufficient_statistics")
    if not isinstance(stats, dict):
        _reject("outcome_error carries no sufficient_statistics to re-derive from")

    design = _resolve_design(block)
    sigma, cov_dy, b, var_y = _moments(stats)
    _check_coefficients(sigma, cov_dy, b, design)
    residual = _residual_variance(sigma, cov_dy, b, var_y)
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

    delta, tracking, in_residual = _check_the_split(block, stats, sigma, sigma_v)

    signal = residual - in_residual
    if signal <= 0:
        _reject(
            f"outcome_error reports {in_residual:.6g} of declared measurement "
            f"noise in a residual variance of {residual:.6g}: it does not fit "
            "under the unexplained variation, so the independence premise "
            "that makes the point estimate immune to the error is itself "
            "refuted. Such an assessment must be refused, not issued"
        )
    _check_scalar(block, "signal_variance", signal)
    _check_scalar(block, "noise_share", in_residual / residual)
    _check_scalar(block, "se_inflation", math.sqrt(residual / signal))
    # The factor at the declared σ²_v is one number; what the study that
    # measured σ²_v does to it is the shape of the answer, and the share
    # re-derived here is the one this audit computed rather than the one
    # the block reports.
    check_inflation_under_a_study(
        block, where="outcome_error", rule=_RULE,
        noise_share=in_residual / residual,
        absorbed_share=(0.0 if tracking is None else tracking / residual))

    _check_design(block, stats, result, design)
    _check_premises(block, design, delta)
    _check_disclosure(block, result)


def _check_the_split(
    block: dict, stats: dict, sigma: list[list[float]], sigma_v: float,
) -> tuple[float | None, float | None, float]:
    """How much of the declared σ²_v this residual holds, re-derived.

    All of it, until the statistics carry a δ. That key's ABSENCE is a claim
    and is read as one: the whole declared variance is unexplained variation,
    which is what every assessment in this package meant before a caller could
    say otherwise. Its presence says the design absorbed δ·(X − E[X | rest])
    into the exposure's coefficient, and then three fields on the block are
    about the remainder rather than the total — so all three are re-derived
    here, and a block carrying any of them without the δ that produces them is
    rejected rather than ignored.

    Var(X | rest) is taken as the Schur complement Σ₀₀ − Σ₀ᵣΣᵣᵣ⁻¹Σᵣ₀, which is
    not how the producer computes it (it inverts the whole matrix and reads the
    leading entry of the precision). Same number, different road, which is the
    only kind of agreement worth having here.
    """
    got_delta = stats.get("differential_coefficient")
    named = [k for k in ("differential_coefficient", "exposure_tracking_variance",
                         "residual_error_variance") if k in block]
    if got_delta is None:
        if named:
            _reject(
                f"outcome_error carries {named!r} while its sufficient "
                "statistics record no differential coefficient. Those fields "
                "exist only where a caller withdrew the non-differential "
                "premise, and the audit re-derives them from the δ that was "
                "declared — a block that reports the split without recording "
                "what produced it cannot be confirmed, only believed"
            )
        return None, None, sigma_v
    delta = _as_float(got_delta, "sufficient_statistics.differential_coefficient")
    if delta == 0.0:
        _reject(
            "outcome_error records a differential coefficient of 0, which IS "
            "the non-differential premise; a declared zero routes to the "
            "ordinary assessment and must not arrive here as a split"
        )
    missing = [k for k in ("differential_coefficient", "exposure_tracking_variance",
                           "residual_error_variance") if k not in block]
    if missing:
        _reject(
            f"outcome_error was assessed under a declared δ and does not "
            f"report {missing!r}. The four scalars above are then about the "
            "remainder rather than the declared total, and a reader given the "
            "share without the two numbers it was taken between cannot tell "
            "which"
        )
    if not _close(delta, _as_float(block.get("differential_coefficient"),
                                   "differential_coefficient"), scale=delta):
        _reject(
            f"outcome_error.differential_coefficient "
            f"{block.get('differential_coefficient')!r} disagrees with the δ "
            f"recorded in its own sufficient statistics ({delta!r})"
        )
    conditional = _conditional_variance(sigma)
    tracking = delta * delta * conditional
    _check_scalar(block, "exposure_tracking_variance", tracking)
    in_residual = sigma_v - tracking
    if in_residual < 0:
        _reject(
            f"outcome_error declares σ²_v = {sigma_v:.6g} and a δ whose "
            f"tracking component alone accounts for {tracking:.6g}, leaving "
            f"{in_residual:.6g} of classical error — not a variance. The two "
            "declarations contradict each other before the data is consulted, "
            "which is a refusal and not an assessment"
        )
    _check_scalar(block, "residual_error_variance", in_residual)
    return delta, tracking, in_residual


def _conditional_variance(sigma: list[list[float]]) -> float:
    """Var(X | rest of the design), as the Schur complement of the exposure."""
    p = len(sigma)
    if p == 1:
        return sigma[0][0]
    rest = [row[1:] for row in sigma[1:]]
    cross = [sigma[0][j] for j in range(1, p)]
    solved = _solve(rest, cross)
    value = sigma[0][0] - sum(c * s for c, s in zip(cross, solved))
    if value <= 0:
        _reject(
            f"outcome_error: the recorded moments leave the exposure a "
            f"conditional variance of {value:.6g}; the design does not "
            "separate it from the columns beside it, and a split taken over "
            "it is arithmetic about a fit that does not exist"
        )
    return value


# --- the design named ---------------------------------------------------------


def _resolve_design(block: dict) -> _Design:
    """Which of the three residuals these numbers describe.

    Read before any of them, because it is what they mean rather than a label
    on top of them: the same Σ_D and Var(Y) give different residuals under
    different designs, and the same factor is exact under two of them and a
    ceiling under the third. A block that does not say cannot be audited, and
    guessing the commonest route would turn this whole module into an audit of
    an assumption it made itself.
    """
    name = block.get("design_kind")
    design = _DESIGNS.get(name) if isinstance(name, str) else None
    if design is None:
        _reject(
            f"outcome_error.design_kind {name!r} is not one of the designs a "
            f"residual can be taken around ({', '.join(_DESIGNS)}); which one "
            "it was decides which model the split describes and which premise "
            "it rests on, so an assessment that does not say is not one this "
            "audit can confirm"
        )
    return design


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


def _moments(stats: dict) -> tuple[list[list[float]], list[float], list[float], float]:
    """Σ_D, Cov(D, Y), b and Var(Y), with one dimension across all four.

    The dimension is checked here rather than trusted, because every quantity
    below is a sum over it: a coefficient vector one entry short of the design
    is not a rounding disagreement, it is a different model, and the quadratic
    form would still return a plausible number for it.
    """
    sigma_raw = stats.get("cov_matrix")
    cov_raw = stats.get("cov_design_y")
    b_raw = stats.get("design_coefficients")
    names = stats.get("design_vars")
    var_y = _as_float(stats.get("var_y"), "sufficient_statistics.var_y")
    if (
        not isinstance(sigma_raw, list) or not sigma_raw
        or not isinstance(cov_raw, list) or not isinstance(b_raw, list)
        or not isinstance(names, list)
    ):
        _reject(
            "outcome_error.sufficient_statistics is missing Σ_D / Cov(D,Y) / "
            "the design coefficients / the design's names"
        )
    p = len(sigma_raw)
    widths = {
        "cov_design_y": len(cov_raw),
        "design_coefficients": len(b_raw),
        "design_vars": len(names),
    }
    if any(not isinstance(row, list) or len(row) != p for row in sigma_raw):
        _reject(
            f"outcome_error.sufficient_statistics.cov_matrix has {p} rows and "
            f"they are not all {p} wide; it is not a covariance matrix"
        )
    off = {k: v for k, v in widths.items() if v != p}
    if off:
        _reject(
            f"outcome_error.sufficient_statistics: Σ_D is {p}×{p} while "
            + ", ".join(f"{k} has {v}" for k, v in off.items())
            + " entries; all four describe one design and must share its "
            "dimension"
        )
    sigma = [
        [_as_float(v, f"sufficient_statistics.cov_matrix[{i}][{j}]")
         for j, v in enumerate(row)]
        for i, row in enumerate(sigma_raw)
    ]
    cov_dy = [_as_float(v, f"sufficient_statistics.cov_design_y[{i}]")
              for i, v in enumerate(cov_raw)]
    b = [_as_float(v, f"sufficient_statistics.design_coefficients[{i}]")
         for i, v in enumerate(b_raw)]
    for i in range(p):
        for j in range(i + 1, p):
            if not _close(sigma[i][j], sigma[j][i], scale=sigma[i][j]):
                _reject(
                    f"outcome_error.sufficient_statistics.cov_matrix is not "
                    f"symmetric at ({i},{j}); it is not a covariance matrix"
                )
    return sigma, cov_dy, b, var_y


def _check_coefficients(
    sigma: list[list[float]], cov_dy: list[float], b: list[float], design: _Design,
) -> None:
    """The coefficients the design fixes, re-solved here from Σ_D and Cov(D,Y).

    A design fixes every coefficient by the normal equations except, on the
    route where the estimator that answered supplied one, the exposure's. So
    the free entries are held where the envelope put them and the rest are
    re-derived around them — which on that route is exactly what makes the
    audit independent, since re-solving for a coefficient nobody solved for
    would reject every honest assessment while confirming nothing.
    """
    free = 1 if design.exposure_coefficient_is_free else 0
    if len(b) <= free:
        return  # the whole design is the supplied coefficient; nothing is owed
    rhs = [
        cov_dy[i] - sum(sigma[i][j] * b[j] for j in range(free))
        for i in range(free, len(b))
    ]
    fitted = _solve([row[free:] for row in sigma[free:]], rhs)
    for offset, (got, expected) in enumerate(zip(b[free:], fitted)):
        if not _close(got, expected, scale=expected):
            i = free + offset
            _reject(
                f"outcome_error.sufficient_statistics.design_coefficients[{i}] "
                f"= {got!r} is not the coefficient the {design.name} design "
                f"fixes there; re-solving its normal equations from the "
                f"recorded moments gives {expected!r}. The residual is the "
                "variance around a fit, and this vector is not that fit"
            )


def _residual_variance(
    sigma: list[list[float]], cov_dy: list[float], b: list[float], var_y: float,
) -> float:
    """Var(Y − b'D) = Var(Y) − 2 b'Cov(D,Y) + b'Σ_D b."""
    cross = sum(bi * ci for bi, ci in zip(b, cov_dy))
    quadratic = sum(
        b[i] * sigma[i][j] * b[j] for i in range(len(b)) for j in range(len(b))
    )
    residual = var_y - 2.0 * cross + quadratic
    if residual <= 0:
        _reject(
            f"outcome_error: the recorded moments give a non-positive residual "
            f"variance {residual:.6g} (Var(Y) = {var_y:.6g}); the outcome cannot "
            "vary less than nothing around its own fit"
        )
    return residual


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Gaussian elimination with partial pivoting rather than a linear-algebra
    dependency: the point of re-deriving is to not share code with the
    producer, and a 1–5 column design does not need more."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-12:
            _reject(
                "outcome_error.sufficient_statistics.cov_matrix is singular; the "
                "fit the residual variance is defined around does not exist"
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


def _check_design(block: dict, stats: dict, result: dict, design: _Design) -> None:
    """The design assessed must be the design estimated."""
    design_vars = block.get("design_vars")
    if not isinstance(design_vars, list) or not design_vars:
        _reject("outcome_error.design_vars is missing or empty")
    if list(stats.get("design_vars") or ()) != design_vars:
        _reject(
            f"outcome_error.design_vars {design_vars!r} disagrees with the "
            f"design recorded in its sufficient statistics "
            f"{stats.get('design_vars')!r}"
        )
    if design_vars[0] != block.get("treatment"):
        _reject(
            f"outcome_error.design_vars starts with {design_vars[0]!r} but the "
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
    _check_the_rest_of_the_design(estimate, design, design_vars)


def _check_the_rest_of_the_design(
    estimate: dict, design: _Design, design_vars: list,
) -> None:
    """The columns the design carries besides the exposure, against the ones
    the answer says it used.

    Each route records them under its own key, so the key is read off the
    design rather than fixed: looking for one route's key on another route's
    answer finds nothing and passes, and a check that passes because it could
    not find what it was checking is worse than no check — it reads, on every
    surface downstream, exactly like a check that ran.
    """
    named = estimate.get(design.names_the_rest)
    if not isinstance(named, list):
        _reject(
            f"outcome_error was assessed on the {design.name} design, whose "
            f"non-exposure columns the answer records under "
            f"{design.names_the_rest!r} — and this estimate carries no such "
            f"key ({sorted(estimate)!r}). Either the assessment is about a "
            "design this answer did not use, or the answer stopped saying "
            "which design it used; neither can be waved through"
        )
    named_here = sorted(str(v) for v in named)
    if design.carried_as_indicators:
        # These reach the design expanded — one drop-first indicator per
        # non-reference level, "<variable>=<level>" — because that is the span
        # the outcome model is fitted on. So the variables are recovered from
        # the indicator names, and the design's remaining columns (adjustment,
        # which this route's answer does not record) are left alone. A raw
        # column whose own name contains "=" would be misread as an indicator
        # and rejected: a false alarm, which is the direction an audit errs in.
        carried = sorted({str(v).split("=", 1)[0] for v in design_vars[1:] if "=" in str(v)})
        if carried != named_here:
            _reject(
                f"outcome_error was assessed on a design carrying indicators "
                f"for {carried!r}, but the estimate's {design.names_the_rest} "
                f"are {named_here!r}; the variance split describes a model "
                "this answer did not fit"
            )
        return
    if named_here != sorted(str(v) for v in design_vars[1:]):
        _reject(
            f"outcome_error was assessed on the design {design_vars!r}, but "
            f"the estimate's {design.names_the_rest} are {named_here!r}; the "
            "variance split describes a model this answer did not fit"
        )


def _check_premises(block: dict, design: _Design,
                    delta: float | None = None) -> None:
    """The premises this design rests on, by name.

    Not merely "some premise was declared": the routes rest on different
    things, and a premise borrowed from a neighbouring route is a true-looking
    sentence about the wrong variable. The instrumental route's immunity is
    mean-independence of the INSTRUMENT, for which the classical premise on the
    design is neither necessary nor sufficient; the front-door route owes one
    premise about the unmeasured confounder its own graph posits, whose failure
    moves the point rather than the interval and which no data can refute — the
    two properties that together make silence about it unrecoverable.
    """
    outcome = block.get("outcome")
    if not isinstance(outcome, str) or not outcome:
        _reject("outcome_error.outcome must name the mismeasured column")
    declared = [a for a in (block.get("assumptions") or ()) if isinstance(a, str)]
    tail = f"_on_{outcome}"
    # A declared δ withdraws the classical premise, so the design owes the
    # other spelling — and owes it INSTEAD. Keeping both would put on the
    # ledger, in the package's own words, a claim the caller's own declaration
    # contradicts, beside numbers computed on the contradiction.
    wanted = tuple(
        _CLASSICAL_UNDER_DELTA if (stem == _CLASSICAL and delta is not None)
        else stem
        for stem in design.premises
    )
    if delta is not None and any(
            a.startswith(_CLASSICAL) and a.endswith(tail) for a in declared):
        _reject(
            f"outcome_error split its variance on a declared δ = {delta!r} "
            f"and still declares {_CLASSICAL}{tail}. That premise says the "
            "error moves no conditional mean, which is the sentence the "
            "declaration withdrew and the sentence the split contradicts; a "
            "ledger carrying it here tells the reader the point needed no "
            "correction beside a number that was corrected"
        )
    for stem in wanted:
        if not any(a.startswith(stem) and a.endswith(tail) for a in declared):
            _reject(
                f"outcome_error was assessed on the {design.name} design, "
                f"which rests on a premise named {stem}…{tail}, and declares "
                f"{declared!r}. A premise the design needs and the block does "
                "not name reaches no reader at all — the ledger can only carry "
                "what it is given"
            )
    # And the premise every design owes, whose spelling is settled by the
    # study the block itself records rather than by the design. Taken from
    # ``validation_df`` and not from the premise: a check that read which of
    # the two the producer chose would confirm the choice by making it.
    study = block.get("validation_df")
    check_declaration_premises(
        OUTCOME_ERROR_VARIANCE,
        rule=_RULE,
        declared=declared,
        measured=[outcome],
        carried={outcome: study} if study is not None else {},
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
