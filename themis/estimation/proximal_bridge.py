"""Proximal causal inference — the continuous regime (Miao-Geng-Tchetgen 2018 §3).

Where the discrete channel inverts a ``k×k`` matrix, this solves for one or
both **bridge functions**. The outcome bridge ``h``:

    E[h(W, X) | Z, X] = E[Y | Z, X]      for every (z, x)                  (b1)
    E[Y | do(x)]      = E[h(W, x)]                                         (b2)

(b1) is a Fredholm integral equation of the first kind, and that is the whole
character of this module. Such an equation is **ill-posed**: the operator
``E[· | Z, X=x]`` smooths, its inverse therefore amplifies, and two observed
laws that differ by an arbitrarily small amount can have bridges that differ by
an arbitrarily large one. There is no numeric solution without regularisation,
which means every number this module produces has a term in it that the data
did not put there.

Themis's answer to that is not to hide the term. It is to make the choice
sayable (``BridgeFunction`` on the query), attribute it (``CALLER_CHOSE`` when
the caller named λ, ``DEFAULT`` when nobody did), and re-run the whole solve
across four decades of penalty so the reader can see how much of the answer is
the penalty's. Where that spread exceeds the estimate's own standard error, the
number is a property of the penalty and a gap says so.

and the **treatment bridge** ``q`` (Cui, Pu, Miao, Zhang & Tchetgen Tchetgen
2024, JASA 119(546), Theorem 2.2), defined by

    E[q(Z, a, X) | W, A = a, X] = 1 / f(A = a | W, X)                      (q1)
    E[Y(a)]                     = E[I(A=a) q(Z, a, X) Y]                   (q2)

Two bridges rather than one, because each rests on its own assumption and an
estimator built from both is right when EITHER holds — Theorem 3.2's union
model. One bridge cannot be robust to itself.

A linear-in-parameters ``q``, and why not the paper's
-----------------------------------------------------
Cui et al.'s working model is ``q = 1 + exp{(−1)^{1−A}(t₀ + t_z Z + …)}``,
which is nonlinear in ``t`` and has to be solved by iterating over the raw
rows. Nothing finite would then travel on the envelope, and the verifier
could not re-derive ``t`` without the data — the discipline this module
already keeps for ``h``. Multiplying (q1) by ``I(A=a)·n(W,C)`` and taking
expectations gives an equation that never mentions the propensity at all:

    E[I(A=a)·q_a(Z,C)·n(W,C)] = E[f(a|W,C)·(1/f(a|W,C))·n(W,C)] = E[n(W,C)]

so for ``q_a = g(Z,C)ᵀ t_a`` over a declared sieve ``g`` this is a linear
system in cross-moments, ``M_a t_a = n̄``, solvable from the same kind of
small matrices ``h`` leaves behind. The COST is declared rather than
absorbed: the exponential form guarantees ``q > 1``, as a reciprocal
probability must be, and a linear one does not. Where the fitted ``q`` comes
out negative on a share of rows, that share is recorded and a gap says the
reciprocal-probability reading has broken down. The paper's local efficiency
is proved for its working models and is not claimed here.

Method — sieve two-stage least squares, one solve per treatment arm
------------------------------------------------------------------
Within arm ``x``, write ``h(w, x) = b(w)ᵀ θ_x`` for a declared basis ``b`` of
``d`` functions, and ask (b1) to hold at ``m ≥ d`` moments of ``Z`` given by a
basis ``a``. With ``A = [a(Z_i)]`` and ``B = [b(W_i)]`` over that arm's rows,

    S_AA = AᵀA / n,  S_AB = AᵀB / n,  S_Ay = Aᵀy / n
    G    = S_ABᵀ S_AA⁻¹ S_AB          (d×d — the operator being inverted)
    c    = S_ABᵀ S_AA⁻¹ S_Ay          (d,)
    θ_λ  = (G + λI)⁻¹ c

which is ordinary two-stage least squares with ``W`` in the regressor's place
and ``Z`` in the instrument's — the same algebra Themis already runs for an
instrumental variable, applied to a different pair of variables for a different
reason. ``λI`` is Tikhonov regularisation, and ``G``'s condition number is the
ill-posedness made numeric.

The two arms are estimated separately (they are disjoint rows, so their errors
are independent), and (b2) is then averaged over the **whole** sample, since
``E[h(W, x)]`` is over the marginal law of W and not the arm's:

    μ_x = w̄ᵀ θ_x,   w̄ = mean of b(W) over all rows
    ATE = μ_1 − μ_0

The treatment bridge is the same algebra with the roles swapped: it spans
``(Z, C)`` and is tested at moments of ``(W, C)``, so with ``G = [g(Z_i)]``
and ``N = [n(W_i)]`` over arm ``a``'s rows, scaled by the TOTAL count because
(q1) was multiplied by an indicator and averaged over everyone,

    M_a = NᵀG / n,   Ω = (NᵀN / n)⁻¹ over ALL rows
    t_a = (M_aᵀ Ω M_a + λI)⁻¹ M_aᵀ Ω n̄

and the three estimators are then linear in what each arm recorded:

    ψ_POR  = w̄ᵀ(θ_1 − θ_0)
    ψ_PIPW = t_1ᵀs_1 − t_0ᵀs_0,               s_a = Gᵀy / n over arm a
    ψ_PDR  = Σ_a (±)[ t_aᵀ(s_a − R_aθ_a) + w̄ᵀθ_a ],  R_a = GᵀB / n

All three are computed whenever both bridges are declared, and all three go
on the envelope. Which one is THE answer is the query's to say, but a reader
comparing them is reading the two assumptions against each other, and that
comparison costs nothing once the moments are in hand.

Why this and not a kernel bridge
--------------------------------
The RKHS estimators (KPV / PMMR, Mastouri et al. 2021) are more flexible and
are the state of the art for this problem. They are not what Themis can carry:
their solution is an element of a space defined by ``n×n`` Gram matrices, so
nothing finite travels on the envelope and a second implementation cannot
re-derive the number without the data. A sieve solve leaves behind six small
cross-moment matrices per arm, and from those alone the verifier recomputes θ
at any λ, both arm means, the standard errors, the condition numbers and the
whole penalty ladder — the discipline this repository holds every other
estimator to. The cost is declared: a bridge outside the declared span is not
approximated better by more data, and that assumption is on the ledger rather
than dissolved by the method.

Reference: Miao, Geng & Tchetgen Tchetgen 2018 (Biometrika 105(4)) §3;
Deaner 2018 (arXiv:1807.02667) for the sieve two-stage form; Cui, Pu, Miao,
Zhang & Tchetgen Tchetgen 2024 (JASA 119(546)) for the semiparametric theory.
Completeness — the continuous rank condition — is not testable from data
(Canay, Santos & Shaikh 2013, Econometrica 81(6)), which is why it is a ledger
line and the condition number is only its numeric shadow.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import NamedTuple

import numpy as np
import pandas as pd

from ..refusals import BridgeSide, Design, EstimatorFailure, Refusal
from ..types import (
    BasisFamily, BridgeChannel, BridgeFunction, ProximalEstimator,
)

#: Beyond this the penalised system is not being solved, it is being chosen.
#: The same threshold the discrete channel refuses at, for the same reason —
#: what differs is that here the caller has two levers (a smaller sieve, a
#: larger penalty) rather than none.
_MAX_CONDITION_NUMBER = 1e10

#: The default penalty, as a fraction of the problem's own scale ``tr(G)/d``.
#: Small enough to be stabilising rather than shrinking: three decades below
#: the first fraction that visibly bends a well-conditioned solve. It is NOT
#: an optimal choice and is never presented as one — a cross-validated λ
#: targets prediction, and the bridge is not a prediction.
_DEFAULT_RIDGE_FRACTION = 1e-6

#: Where the answer is re-solved, as fractions of that same scale. Fixed
#: rather than centred on the λ in force, because what these measure is a
#: property of the PROBLEM — how far the penalty can move this answer — and
#: a ladder that moved with the choice would report a different quantity for
#: every choice. λ in force is reported beside them as a point on the ladder.
_LADDER_FRACTIONS = (1e-8, 1e-6, 1e-4, 1e-2)


@dataclass(frozen=True)
class _SolveBlock:
    """One row set's cross-moments, and everything derived from them.

    A row set and not an arm. The binary contrast solves two of these,
    one per arm; the curve solves ONE over every row, with the treatment
    inside the designs instead of outside them choosing the rows. The
    fields are the same either way, which is the whole reason the two
    regimes can share every function below this one.
    """

    n: int
    s_aa: np.ndarray          # m×m
    s_ab: np.ndarray          # m×d
    s_ay: np.ndarray          # m
    s_bb: np.ndarray          # d×d
    s_by: np.ndarray          # d
    yy: float                 # mean of y²
    g: np.ndarray             # d×d
    c: np.ndarray             # d


def _standardise(values: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Centre and scale, so a basis is about shape rather than units.

    Returned with its two constants because they are part of the basis: a
    verifier re-deriving the sieve has to raise the same numbers to the same
    powers, and "the mean of this column" is not something it can look up.
    """
    centre = float(np.mean(values))
    spread = float(np.std(values))
    if spread <= 0:
        return np.zeros_like(values), centre, 0.0
    return (values - centre) / spread, centre, spread


def _polynomial(values: np.ndarray, dimension: int,
                centre: float, spread: float) -> np.ndarray:
    """``[1, t, t², …]`` on the standardised column.

    Global support: every observation moves every coefficient, which is what
    makes a high degree both expressive and badly conditioned. That the two
    come together is not a defect of the implementation — it is the ill-posed
    problem showing through, and the condition number reports it.
    """
    t = values if spread == 0 else (values - centre) / spread
    return np.vstack([t ** power for power in range(dimension)]).T


def _piecewise_linear(values: np.ndarray, knots: np.ndarray) -> np.ndarray:
    """Hat functions on the declared knots, flat outside the range.

    A partition of unity — the columns sum to 1 everywhere — so the constant
    is in the span without a column of its own, and the local support means a
    heavy tail cannot pull the fit in the middle. The usual reason to prefer
    a spline sieve over a polynomial one at equal dimension.
    """
    out = np.zeros((len(values), len(knots)))
    for j, knot in enumerate(knots):
        left = knots[j - 1] if j > 0 else None
        right = knots[j + 1] if j + 1 < len(knots) else None
        column = np.zeros(len(values))
        if left is not None:
            span = knot - left
            rising = (values > left) & (values <= knot)
            column[rising] = (values[rising] - left) / span
        else:
            column[values <= knot] = 1.0
        if right is not None:
            span = right - knot
            falling = (values > knot) & (values < right)
            column[falling] = (right - values[falling]) / span
        else:
            column[values > knot] = 1.0
        out[:, j] = column
    return out


def _knots(values: np.ndarray, dimension: int) -> np.ndarray:
    """Sample quantiles, evenly spaced in probability rather than in value.

    Quantiles and not an even grid because the sieve's job is to resolve
    where the data are; an even grid over a skewed proxy spends most of its
    dimension on the tail, and the columns that carry no rows are exactly
    what makes ``AᵀA`` singular.
    """
    return np.quantile(values, np.linspace(0.0, 1.0, dimension))


_SPLINE_DEGREE = 3


def _spline_knots(values: np.ndarray, dimension: int) -> np.ndarray:
    """A clamped knot vector for ``dimension`` cubic B-splines.

    ``degree + 1`` copies of each end so the basis reaches the boundary
    rather than dying away inside it, and the rest at sample quantiles for
    the reason the hats use quantiles. The count is forced: with a knot
    vector of length ``m + 1`` there are ``m − degree`` B-splines, so
    ``dimension`` of them needs ``dimension + degree + 1`` knots.
    """
    p = _SPLINE_DEGREE
    interior = (
        np.quantile(values, np.linspace(0.0, 1.0, dimension - p + 1)[1:-1])
        if dimension > p + 1 else np.empty(0)
    )
    lo, hi = float(np.min(values)), float(np.max(values))
    return np.concatenate([np.full(p + 1, lo), interior, np.full(p + 1, hi)])


def _bspline(values: np.ndarray, dimension: int,
             knots: np.ndarray) -> np.ndarray:
    """Cox-de Boor, evaluated for every basis function at once.

    Degree zero is the indicator of each span, and each degree after it is
    the two-term recursion over the one below. The last span is closed on
    the right rather than half-open, because otherwise the largest
    observation falls out of every basis function and the partition of
    unity — which is what lets a design drop one column per term and keep
    one constant — would fail on exactly one row.
    """
    x = np.clip(values, knots[0], knots[-1])
    columns = len(knots) - _SPLINE_DEGREE - 1
    basis = np.zeros((len(x), len(knots) - 1))
    for i in range(len(knots) - 1):
        if knots[i] == knots[i + 1]:
            continue
        inside = (x >= knots[i]) & (x < knots[i + 1])
        if knots[i + 1] == knots[-1]:
            inside |= x == knots[-1]
        basis[inside, i] = 1.0
    for degree in range(1, _SPLINE_DEGREE + 1):
        width = len(knots) - degree - 1
        raised = np.zeros((len(x), width))
        for i in range(width):
            left_span = knots[i + degree] - knots[i]
            if left_span > 0:
                raised[:, i] += ((x - knots[i]) / left_span) * basis[:, i]
            right_span = knots[i + degree + 1] - knots[i + 1]
            if right_span > 0:
                raised[:, i] += (
                    (knots[i + degree + 1] - x) / right_span) * basis[:, i + 1]
        basis = raised
    return basis[:, :columns]


def _fourier(values: np.ndarray, dimension: int,
             lo: float, hi: float) -> np.ndarray:
    """``[1, cos 2πt, sin 2πt, cos 4πt, …]`` on the range mapped to [0, 1].

    Truncated at the declared dimension, so an even one ends on a lone
    cosine. That is not a defect to pad away: which harmonics are in the
    span is what was declared, and quietly adding the matching sine would
    make the design one column wider than the width every other layer
    counted.
    """
    span = hi - lo
    t = np.zeros_like(values) if span <= 0 else (values - lo) / span
    out = [np.ones_like(t)]
    harmonic = 1
    while len(out) < dimension:
        out.append(np.cos(2 * np.pi * harmonic * t))
        if len(out) < dimension:
            out.append(np.sin(2 * np.pi * harmonic * t))
        harmonic += 1
    return np.vstack(out).T


def _hermite(values: np.ndarray, dimension: int,
             centre: float, spread: float) -> np.ndarray:
    """Probabilists' Hermite polynomials, divided by ``√(n!)``.

    Same span as the powers of the same degree and a different matrix: the
    normalised family is orthonormal under the standard normal weight, so a
    roughly bell-shaped column gives a Gram matrix near the identity where
    raw powers give a Vandermonde.

    The recursion carries the normalisation rather than applying it after:
    from ``He_{n+1} = t·He_n − n·He_{n−1}``, dividing each side by the root
    factorial it belongs to gives ``h_{n+1} = (t·h_n − √n·h_{n−1})/√(n+1)``,
    which never forms a factorial at all. Raising the powers first and
    dividing at the end would overflow at a dimension a caller is entitled
    to ask for, and would do it silently — ``inf/inf`` is ``nan``, and a
    column of those reaches the solve as a singular design rather than as
    the arithmetic complaint it is.
    """
    t = values if spread == 0 else (values - centre) / spread
    out = [np.ones_like(t)]
    if dimension > 1:
        out.append(t)
    for n in range(1, dimension - 1):
        out.append((t * out[n] - np.sqrt(n) * out[n - 1]) / np.sqrt(n + 1))
    return np.vstack(out).T


class _Family(NamedTuple):
    """One basis family, as the two halves every one of them has.

    ``fit`` reads the sample once and returns the constants that make this
    family a fixed set of functions — moments, knots, a range. ``evaluate``
    takes only those constants back, never the sample, which is the whole
    reason they are a separate step: a basis that re-derived its knots at
    evaluation time would be a different basis in every bootstrap draw and
    in the verifier's re-derivation.
    """

    fit: "Callable[[np.ndarray, int], tuple[float, ...]]"
    evaluate: "Callable[[np.ndarray, int, tuple[float, ...]], np.ndarray]"


def _moments(values: np.ndarray, dimension: int) -> tuple[float, ...]:
    _, centre, spread = _standardise(values)
    return (centre, spread)


def _extent(values: np.ndarray, dimension: int) -> tuple[float, ...]:
    return (float(np.min(values)), float(np.max(values)))


#: Every family, and nothing outside it. A table rather than a chain of
#: comparisons because two other places have to agree with this set exactly
#: — the schema enum a caller declares from and the reader's glossary — and
#: a branch is not something either of them can be checked against.
_FAMILIES: "dict[BasisFamily, _Family]" = {
    BasisFamily.POLYNOMIAL: _Family(
        fit=_moments,
        evaluate=lambda v, d, c: _polynomial(v, d, c[0], c[1]),
    ),
    BasisFamily.PIECEWISE_LINEAR: _Family(
        fit=lambda v, d: tuple(float(k) for k in _knots(v, d)),
        evaluate=lambda v, d, c: _piecewise_linear(
            v, np.asarray(c, dtype=float)),
    ),
    BasisFamily.CUBIC_SPLINE: _Family(
        fit=lambda v, d: tuple(float(k) for k in _spline_knots(v, d)),
        evaluate=lambda v, d, c: _bspline(v, d, np.asarray(c, dtype=float)),
    ),
    BasisFamily.FOURIER: _Family(
        fit=_extent,
        evaluate=lambda v, d, c: _fourier(v, d, c[0], c[1]),
    ),
    BasisFamily.HERMITE: _Family(
        fit=_moments,
        evaluate=lambda v, d, c: _hermite(v, d, c[0], c[1]),
    ),
}


@dataclass(frozen=True)
class _Basis:
    """A declared family at a declared dimension, and the constants it fixed.

    The constants are one field whatever shape they take — moments for the
    powers, knots for the hats and the splines, a range for the harmonics —
    because what every consumer does with them is the same: hand them back
    to the same family and get the same columns.
    """

    variable: str
    family: BasisFamily
    dimension: int
    constants: tuple[float, ...]

    def evaluate(self, values: np.ndarray) -> np.ndarray:
        return _FAMILIES[self.family].evaluate(
            values, self.dimension, self.constants)

    def as_record(self) -> dict:
        return {
            "variable": self.variable,
            "family": str(self.family),
            "dimension": int(self.dimension),
            "constants": tuple(float(v) for v in self.constants),
        }


def _fit_basis(values: np.ndarray, variable: str, family: BasisFamily,
               dimension: int) -> _Basis:
    return _Basis(variable, family, dimension,
                  _FAMILIES[family].fit(values, dimension))


@dataclass(frozen=True)
class _Design:
    """One side's columns, and the recipe that rebuilt them.

    A sieve over several variables is a SUM OF TERMS, each term the tensor
    product of one basis per variable it names. Additive across terms and
    multiplicative within one, because those are the two things a caller
    can mean and they are not the same claim: a bridge plus a stratifier is
    one function of the proxy moved up or down by C, and a bridge times a
    stratifier is a different function of the proxy in each level of C. Only
    the second is what "stratify, then run proximal inside the stratum"
    asks for, and an additive-only design could not have been asked for it.

    Every family here spans the constant on its own, so each term's first
    column is dropped and one constant is restored for the whole design.
    Without that, two terms put the constant in twice and ``AᵀA`` is
    singular before any data has had a say — a fact about the arrangement
    that would have arrived wearing the costume of a fact about the sample.
    """

    bases: tuple[tuple[_Basis, ...], ...]     # one tuple of bases per term
    columns: np.ndarray

    def as_record(self) -> tuple[tuple[dict, ...], ...]:
        return tuple(tuple(b.as_record() for b in term) for term in self.bases)

    @property
    def width(self) -> int:
        return int(self.columns.shape[1])


def _tensor(blocks: Sequence[np.ndarray]) -> np.ndarray:
    """Row-wise products of one column from each block — the term's columns.

    ``np.einsum`` would say this in one line for a fixed number of factors
    and this has to take any number, so it is a fold. The column order is
    the odometer order of the factors as the query wrote them, which is
    what makes the record replayable by a second implementation.
    """
    out = blocks[0]
    for block in blocks[1:]:
        out = (out[:, :, None] * block[:, None, :]).reshape(len(out), -1)
    return out


def _build_design(df: pd.DataFrame, terms: Sequence,
                  fitted: "dict[tuple, _Basis] | None" = None) -> _Design:
    """The design matrix for one side, and the bases it was built from.

    ``fitted`` lets a variable that appears on BOTH sides — every covariate
    does — reuse one fitted basis where the two sides declared the same
    expansion of it. Fitting it a second time from the same rows would give
    the same numbers, and keying on the declaration rather than trusting
    that is what makes the moment side's functions of C literally the
    outcome side's, rather than two independently-derived copies that a
    later change to the fitting rule could quietly separate.
    """
    seen: dict[tuple, _Basis] = {} if fitted is None else fitted
    bases: list[tuple[_Basis, ...]] = []
    blocks: list[np.ndarray] = []
    for term in terms:
        term_bases: list[_Basis] = []
        factor_columns: list[np.ndarray] = []
        for factor in term.factors:
            name = factor.variable.predicate
            key = (name, str(factor.basis), int(factor.dimension))
            values = df[name].to_numpy(dtype=float)
            basis = seen.get(key)
            if basis is None:
                basis = _fit_basis(values, name, factor.basis, factor.dimension)
                seen[key] = basis
            term_bases.append(basis)
            factor_columns.append(basis.evaluate(values))
        bases.append(tuple(term_bases))
        # Drop this term's own copy of the constant; one is restored below.
        # The FIRST column is the one to drop, and that it is safe is a
        # property of these families rather than a convention: the constant
        # is in every one of their spans with a non-zero coefficient on
        # column 0 (``t⁰`` for the powers, and the hats sum to one), so the
        # dropped column is recoverable from the rest plus the constant and
        # the span is untouched. A family that spanned the constant without
        # using its first column would break that, which is why the rule
        # lives here beside the families and not in a shared helper.
        blocks.append(_tensor(factor_columns)[:, 1:])
    constant = np.ones((len(df), 1))
    return _Design(bases=tuple(bases),
                   columns=np.hstack([constant, *blocks]) if blocks
                   else constant)


def _cross_moments(design_a: np.ndarray, design_b: np.ndarray,
                   y: np.ndarray) -> _SolveBlock:
    """Cross-moments for one set of rows, and the operator they define.

    ``S_AA`` is inverted here and not stored inverted: an inverse recorded is
    an inverse nobody re-takes, and the first stage failing is a fact about
    the instrument basis that the reader can act on.
    """
    n = len(y)
    s_aa = design_a.T @ design_a / n
    s_ab = design_a.T @ design_b / n
    s_ay = design_a.T @ y / n
    if not np.isfinite(s_aa).all() or np.linalg.cond(s_aa) > _MAX_CONDITION_NUMBER:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design=Design.BRIDGE_INSTRUMENT_MOMENTS)
    weight = np.linalg.inv(s_aa)
    return _SolveBlock(
        n=n, s_aa=s_aa, s_ab=s_ab, s_ay=s_ay,
        s_bb=design_b.T @ design_b / n,
        s_by=design_b.T @ y / n,
        yy=float(y @ y / n),
        g=s_ab.T @ weight @ s_ab,
        c=s_ab.T @ weight @ s_ay,
    )


def solve_theta(g: np.ndarray, c: np.ndarray, ridge: float) -> np.ndarray:
    """``(G + λI)⁻¹ c``, refusing where the penalty did not make it solvable.

    Exported because the verifier re-derives every number in this module from
    ``(G, c, λ)`` and must do it by the same arithmetic — this is one function
    with two callers, not a rule written twice.
    """
    penalised = g + ridge * np.eye(len(c))
    condition = float(np.linalg.cond(penalised))
    if not np.isfinite(condition) or condition > _MAX_CONDITION_NUMBER:
        raise EstimatorFailure(
            Refusal.BRIDGE_ILL_POSED_AT_THIS_PENALTY,
            dimension=len(c), ridge=ridge, condition=condition,
        )
    return np.linalg.solve(penalised, c)


def _block_mean(arm: _SolveBlock, w_bar: np.ndarray, ridge: float) -> float:
    return float(w_bar @ solve_theta(arm.g, arm.c, ridge))


def _residual_variance(arm: _SolveBlock, theta: np.ndarray) -> float:
    """``Var(Y − b(W)ᵀθ)`` from the recorded moments alone.

    The structural residual and not the first stage's: what the standard
    error of the bridge rests on is how much of Y the bridge fails to
    explain, and that is a second moment this arm already recorded.
    """
    return max(float(arm.yy - 2 * theta @ arm.s_by + theta @ arm.s_bb @ theta),
               0.0)


def _block_standard_error(arm: _SolveBlock, w_bar: np.ndarray, ridge: float,
                        theta: np.ndarray) -> float:
    """Delta-method SE of ``w̄ᵀθ`` under the GMM sandwich at this penalty.

    The penalty's BIAS is deliberately absent from it. A standard error that
    absorbed the shrinkage would report the answer as more uncertain and let
    the ladder pass unnoticed, when the two facts a reader needs are
    precisely separate: this is how far sampling moves the number, and the
    ladder is how far the penalty does.
    """
    penalised = np.linalg.inv(arm.g + ridge * np.eye(len(arm.c)))
    sandwich = penalised @ arm.g @ penalised
    variance = _residual_variance(arm, theta) * (w_bar @ sandwich @ w_bar)
    return float(np.sqrt(max(variance, 0.0) / arm.n))


def _ladder(at_fraction: "Callable[[float], float]") -> tuple[dict, ...]:
    """The same answer at four penalties, and which of them were solvable.

    A rung that will not solve is recorded as unsolved rather than dropped:
    that the smallest penalty cannot be taken IS the ill-posedness, and a
    ladder that quietly shortened itself would report a narrow spread for
    the worst-conditioned problems.

    The rungs are FRACTIONS of each solve's own scale rather than penalties,
    which is what lets one ladder measure an answer resting on two bridges:
    each is dialled to the same fraction of the problem it is regularising.
    A ladder over one λ while a second stayed fixed would report how far the
    penalty moves the answer while holding half the penalty still.
    """
    out = []
    for fraction in _LADDER_FRACTIONS:
        try:
            point: "float | None" = at_fraction(fraction)
        except EstimatorFailure:
            point = None
        out.append({"fraction": fraction, "point": point})
    return tuple(out)


def _rung_ridges(rungs: Sequence[Mapping], scale: float) -> tuple[dict, ...]:
    """The ladder with each rung's actual penalty written beside its fraction.

    Derived from the scale rather than carried through the solve, because a
    fraction and a scale are what the verifier re-multiplies; the product is
    here for a reader who wants to see the number that was used.
    """
    return tuple({**rung, "ridge": rung["fraction"] * scale} for rung in rungs)


def penalty_verdict(rungs: Sequence[Mapping], point: float,
                    standard_error: "float | None") -> dict:
    """Whether the number being reported is the data's or the penalty's.

    Two facts, and the second is the one that turned out to matter.

    ``spread`` — how far the answer moves across four decades of penalty — is
    a property of the PROBLEM: it says how ill-posed this bridge is at this
    sieve dimension, and it is large for a rich basis whatever λ was used.
    Reported always, because a reader deciding whether to believe a sieve
    wants it; a criterion, never, because it condemns a stable answer for
    what a penalty nobody chose would have done to it.

    ``bend`` — how far the penalty IN FORCE moved the answer away from the
    least-penalised solve available — is the property of THIS ANSWER, and is
    what a gap fires on. Beside it, a rung that would not solve at all: where
    the problem is so ill-posed that a smaller penalty has no solution, the
    number exists because of the penalty rather than in spite of it, and that
    is the same finding arriving by the other door.

    ``standard_error`` may be absent, and then the first door is closed
    rather than opened wide: "further than sampling noise" needs a measure of
    sampling noise, and comparing a bend against a number that is not one
    would be filing or withholding a finding on nothing. The second door
    stays open, because an unsolvable rung is a claim about the problem that
    needs no scale at all.
    """
    solved = [r for r in rungs if r.get("point") is not None]
    points = [r["point"] for r in solved]
    spread = max(points) - min(points) if len(points) >= 2 else None
    bend = abs(point - solved[0]["point"]) if solved else None
    unsolved = tuple(r["fraction"] for r in rungs if r.get("point") is None)
    bent_past_noise = (bend is not None and standard_error is not None
                       and bend > standard_error)
    return {
        "spread": spread,
        "bend": bend,
        "unsolved": unsolved,
        "the_penalty_is_doing_the_work": bool(unsolved or bent_past_noise),
    }


@dataclass(frozen=True)
class _TreatmentArm:
    """One arm's cross-moments for the treatment bridge.

    Scaled by the TOTAL sample size rather than the arm's, because (q1)
    reaches the estimator multiplied by ``I(A = a)`` and averaged over
    everyone: the indicator is part of the quantity, and dividing by the
    arm's count would silently condition on it.
    """

    n: int
    m: np.ndarray             # d_q×m_q — E[I(A=a) n(W,C) g(Z,C)ᵀ]
    s: np.ndarray             # m_q     — E[I(A=a) g(Z,C) Y]
    r: np.ndarray             # m_q×d_h — E[I(A=a) g(Z,C) b(W,C)ᵀ]
    gg: np.ndarray            # m_q×m_q — E[I(A=a) g(Z,C) g(Z,C)ᵀ]
    g_operator: np.ndarray    # m_q×m_q — MᵀΩM, the operator being inverted
    c: np.ndarray             # m_q     — MᵀΩn̄
    q_negative_fraction: float


def _treatment_arm(design_g: np.ndarray, design_n: np.ndarray,
                   design_b: np.ndarray, y: np.ndarray,
                   weight: np.ndarray, moment_mean: np.ndarray,
                   n_total: int) -> _TreatmentArm:
    """Cross-moments for one arm of the treatment bridge.

    ``q_negative_fraction`` is left at zero here and filled once ``t`` is
    solved: it is the one quantity in this module that a second
    implementation cannot re-derive from the record, being a count of rows
    rather than a moment of them. It travels in the same category as ``n``
    and ``yy`` — a measurement the envelope reports and the arithmetic
    downstream is checked against, not a step of that arithmetic.
    """
    m = design_n.T @ design_g / n_total
    return _TreatmentArm(
        n=len(y),
        m=m,
        s=design_g.T @ y / n_total,
        r=design_g.T @ design_b / n_total,
        gg=design_g.T @ design_g / n_total,
        g_operator=m.T @ weight @ m,
        c=m.T @ weight @ moment_mean,
        q_negative_fraction=0.0,
    )


@dataclass(frozen=True)
class BridgeSolution:
    """What one run of the bridge estimator produced, arithmetic and all.

    Handed back rather than folded into the caller's estimate object because
    the caller assembles one ``ProximalEstimate`` for both regimes: what
    differs between them is the sufficient statistics and the two do-arms,
    and those are exactly the fields here.
    """

    point: float
    do_treated: float
    do_control: float
    #: The delta-method standard error of the OUTCOME REGRESSION, and absent
    #: for the other two estimators. See :func:`_analytic_standard_error`.
    standard_error: "float | None"
    ridge: float
    ridge_was_declared: bool
    channel: dict


def design_columns(spec: BridgeChannel) -> tuple[str, ...]:
    """Every column the declared designs read, in first-mention order.

    Derived from the terms rather than from the query's roles: what the
    estimator has to find in the frame is what it is about to evaluate a
    basis on, and a role the design never uses would put a column in the
    contract that nothing reads. Both bridges when both were declared —
    each names the same variables in the opposite roles, but a covariate
    one uses and the other does not is still a column that has to be there.
    """
    seen: dict[str, None] = {}
    for bridge in _declared_bridges(spec):
        for terms in (bridge.span_terms, bridge.moment_terms):
            for term in terms:
                for factor in term.factors:
                    seen.setdefault(factor.variable.predicate, None)
    return tuple(seen)


def _declared_bridges(spec: BridgeChannel) -> tuple[BridgeFunction, ...]:
    """The bridges this channel actually carries, outcome side first."""
    if spec.treatment_bridge is None:
        return (spec.outcome_bridge,)
    return (spec.outcome_bridge, spec.treatment_bridge)


def _ridge_for(scale: float, declared: "float | None") -> float:
    return (float(declared) if declared is not None
            else _DEFAULT_RIDGE_FRACTION * scale)


def _analytic_standard_error(
    estimator: ProximalEstimator, treated: _SolveBlock, control: _SolveBlock,
    w_bar: np.ndarray, ridge: float, theta_treated: np.ndarray,
    theta_control: np.ndarray,
) -> "float | None":
    """The outcome regression's sandwich, and nothing for the other two.

    Not an omission. The obvious analytic error for a doubly robust estimate
    is the variance of its influence function evaluated at the fitted
    nuisances, and that was written, measured against repeated sampling, and
    thrown away: it came out three percent low where BOTH bridges are well
    specified and twenty-one percent low where one is not. The reason is the
    theorem's own shape — that influence function is the efficient one AT THE
    INTERSECTION of the two models, and away from the intersection what the
    nuisance estimation leaves behind does not vanish. So the number would
    have been trustworthy exactly where the doubly robust estimator was not
    needed, which is the worst place for a standard error to be trustworthy.

    What carries the uncertainty instead is the percentile bootstrap already
    on this path, which resamples and re-solves everything and therefore sees
    the nuisance estimation and the misspecification alike. Measured the same
    way, its width comes to 1.04 times the sampling standard deviation in
    both regimes.

    Absent and not zero, and absent rather than the outcome regression's
    number under another name: a point from one estimator carrying the
    standard error of another is a number reported with somebody else's
    uncertainty, which is what this branch used to do.
    """
    if estimator != ProximalEstimator.OUTCOME_REGRESSION:
        return None
    return float(np.sqrt(
        _block_standard_error(treated, w_bar, ridge, theta_treated) ** 2
        + _block_standard_error(control, w_bar, ridge, theta_control) ** 2))


#: Past this many distinct values a column is a dose rather than a set of
#: levels, and the curve is sampled instead of enumerated. The same cut the
#: envelope's own scale classifier makes at twenty, held here as its own
#: constant rather than imported: that one runs in ``dispatch``, which
#: imports this module, and a rule two layers share by import is a rule one
#: of them cannot be tested without the other.
_LEVELS_ARE_ENUMERABLE = 20

#: How many points a sampled curve gets. Quantiles and not an even grid over
#: the range, so every point sits where there are rows — an even grid runs
#: into the tails, where the bridge is extrapolating and the standard error
#: does not say so loudly enough.
_SAMPLED_LEVELS = 7


def resolve_levels(values: np.ndarray) -> tuple[float, ...]:
    """Which levels a curve over this column is drawn at.

    Exported because the verifier re-derives the curve and must ask the
    column the same question — one rule with two callers, the discipline
    every other number in this module is held to.
    """
    # ``+ 0.0`` collapses negative zero, which a column that has been
    # rounded or clipped can carry and which reaches a reader's page as the
    # level "-0". It is the same level as zero to every comparison the code
    # makes and a different one to every reader who sees it.
    distinct = np.unique(values[np.isfinite(values)]) + 0.0
    if len(distinct) <= _LEVELS_ARE_ENUMERABLE:
        return tuple(float(v) for v in distinct)
    quantiles = np.linspace(0.0, 1.0, _SAMPLED_LEVELS)
    return tuple(dict.fromkeys(
        float(v) + 0.0 for v in np.quantile(distinct, quantiles)))


@dataclass(frozen=True)
class CurveSolution:
    """A counterfactual mean at each declared level, and one solve behind it.

    ``means`` are ``E[Y(a)]`` themselves rather than contrasts. Theorem 2.1
    identifies the MEAN at a level and leaves the contrast to whoever wants
    one, so that is the order the numbers are produced in; which level a
    reader's curve is drawn against is a rendering decision made downstream
    and does not belong in the arithmetic.
    """

    levels: tuple[float, ...]
    means: tuple[float, ...]
    standard_errors: tuple[float, ...]
    ridge: float
    ridge_was_declared: bool
    channel: dict


def _mentions(terms: Sequence, column: str) -> bool:
    return any(factor.variable.predicate == column
               for term in terms for factor in term.factors)


def mentions_treatment(spec: BridgeChannel, xcol: str) -> bool:
    """Whether the outcome bridge was declared as varying with the level.

    The switch between the two solves, read off the declaration rather than
    off the data, because it IS a declaration: a caller who wrote the
    treatment into their sieve asked for one bridge indexed by the level,
    and a caller who did not asked for a bridge per arm. Either side of it
    can be answered for a binary treatment and only the first for a
    multi-valued one, which is a fact about the two solves and not a
    preference between them.
    """
    return (_mentions(spec.outcome_bridge.span_terms, xcol)
            or _mentions(spec.outcome_bridge.moment_terms, xcol))


def _require_treatment_in_designs(spec: BridgeChannel, xcol: str,
                                  levels: int) -> None:
    """Both sides have to mention the treatment, and for different reasons.

    Missing from the SPAN, ``h`` is one function of the proxies for every
    level and every point of the curve is the same number — the question
    would be answered with a flat line that says nothing about the dose.

    Missing from the MOMENTS, the failure is quieter. The moment condition
    holds GIVEN ``(Z, A, C)``, so moments that never mention ``A`` impose a
    weaker restriction than the theorem's: they ask the equation to hold on
    average across levels rather than within each one. Often the width count
    catches it — a span tensored with the treatment has several times the
    unknowns it had — but a moment design wide enough in ``Z`` alone passes
    that count and still pins ``h`` down by the wrong equations, which is
    the case that would return a number rather than a refusal.
    """
    for terms, side in ((spec.outcome_bridge.span_terms, BridgeSide.SPAN),
                        (spec.outcome_bridge.moment_terms,
                         BridgeSide.MOMENTS)):
        if not _mentions(terms, xcol):
            raise EstimatorFailure(
                Refusal.BRIDGE_CANNOT_VARY_WITH_THE_TREATMENT,
                treatment=xcol, levels=levels, design=side)


def estimate_curve(
    df: pd.DataFrame, *, xcol: str, ycol: str, spec: BridgeChannel,
    levels: Sequence[float],
) -> CurveSolution:
    """``E[Y(a)]`` at each level, from ONE bridge fitted over every row.

    The binary path splits the rows and fits a bridge in each; this one puts
    the treatment inside the designs and fits a single bridge over all of
    them. Theorem 2.1 identifies ``E[Y(a)] = ∫∫h(w, a, x)dF(w|x)dF(x)`` —
    one ``h``, evaluated at each level, integrated against the FULL marginal
    law of the proxies.

    The alternative of fitting a two-arm bridge per pair of levels is ruled
    out by what it cannot do rather than by how far off it lands: measured on
    a three-level sample it agrees to within a thousandth, and on a
    CONTINUOUS treatment it has nothing to run on at all, because a level no
    row takes has no arm to fit. Evaluating one fitted ``h`` at a level is
    not the same operation as fitting on rows that sit at it, and only the
    first is defined where the dose is continuous — which is the regime the
    curve exists for. What it costs where both are defined is that the points
    of a per-pair curve share no bridge, so nothing makes them a function.

    The two regimes therefore coexist rather than one replacing the other.
    With a binary treatment the two-arm fit gives each arm its own
    coefficients, which is the bridge SATURATED in the treatment and strictly
    more general than any declared span in ``a``; migrating it here would
    silently narrow it for callers who did not saturate. The identity that
    connects them is exact and is the test this path is pinned by: saturate
    the declared designs in the treatment and the joint solve reproduces the
    two-arm answer.
    """
    levels = tuple(float(a) for a in levels)
    _require_treatment_in_designs(spec, xcol, len(levels))

    y = df[ycol].to_numpy(dtype=float)
    n_total = len(df)
    shared: dict[tuple, _Basis] = {}
    span = _build_design(df, spec.outcome_bridge.span_terms, shared)
    moment = _build_design(df, spec.outcome_bridge.moment_terms, shared)

    block = _cross_moments(moment.columns, span.columns, y)
    scale = float(np.trace(block.g) / span.width)
    if not np.isfinite(scale) or scale <= 0:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design=Design.BRIDGE_OUTCOME_MOMENTS)
    declared = spec.outcome_bridge.ridge is not None
    ridge = _ridge_for(scale, spec.outcome_bridge.ridge)

    # ``w̄(a)``: the span rebuilt with the treatment column held at ``a`` and
    # every other column left as observed, averaged over all rows. That is
    # the inner integral of (4) written as a sample mean — over the whole
    # sample, because the law it integrates against is the marginal one and
    # not the law among those who happened to receive ``a``.
    #
    # ``shared`` is passed so the treatment's basis is the one FITTED on the
    # observed column. Rebuilding it from a constant column would standardise
    # by a zero spread and evaluate a different function at every level.
    w_bars = []
    for level in levels:
        at_level = df.assign(**{xcol: float(level)})
        w_bars.append(_build_design(
            at_level, spec.outcome_bridge.span_terms, shared
        ).columns.mean(axis=0))

    theta = solve_theta(block.g, block.c, ridge)
    means = tuple(float(w @ theta) for w in w_bars)
    errors = tuple(_block_standard_error(block, w, ridge, theta)
                   for w in w_bars)

    def _at(fraction: float) -> "dict[str, float] | None":
        try:
            rung = solve_theta(block.g, block.c, fraction * scale)
        except EstimatorFailure:
            return None
        return {str(a): float(w @ rung) for a, w in zip(levels, w_bars)}

    channel = {
        "estimator": str(spec.estimator),
        "z_basis": moment.as_record(),
        "w_basis": span.as_record(),
        "n_total": int(n_total),
        "joint": _block_record(block),
        # Which column the levels are levels OF. A record naming numbers and
        # not what they measure is one a reader cannot check the designs
        # against — and the ledger's claim that the caller chose how the
        # bridge varies with the treatment is exactly that check.
        "level_variable": xcol,
        "levels": levels,
        # One ``w̄`` per level, in the levels' own order. The verifier solves
        # θ once and multiplies; the curve below is what that must come to,
        # recorded so a reader can see the answer and a checker can refuse it.
        "level_means": tuple(tuple(float(v) for v in w) for w in w_bars),
        "curve": means,
        "ridge": ridge,
        "ridge_scale": scale,
        "ridge_was_declared": declared,
        "penalty_ladder": _curve_ladder(_at, scale, levels),
    }
    return CurveSolution(
        levels=levels, means=means, standard_errors=errors,
        ridge=ridge, ridge_was_declared=declared, channel=channel,
    )


def _curve_ladder(at: Callable[[float], "dict[str, float] | None"],
                  scale: float, levels: tuple[float, ...]) -> tuple:
    """The same ladder the point path reports, per level.

    A curve has no single number for the penalty to move, and reporting the
    ladder for one level only would hide that the penalty can flatten a
    curve without moving any one point of it much.
    """
    return tuple({
        "fraction": fraction,
        "ridge": fraction * scale,
        "points": at(fraction),
    } for fraction in _LADDER_FRACTIONS)


def estimate_bridge(
    df: pd.DataFrame, *, xcol: str, ycol: str, spec: BridgeChannel,
) -> BridgeSolution:
    """Solve each declared bridge in each arm, and combine them as asked.

    Which columns build each side is read off the declared terms rather
    than passed in: a proximal query names as many proxies as its author
    has and as many covariates as they want conditioned on, and a signature
    with one name per role could only ever have taken the first of each.
    """
    treated_rows = df[xcol].to_numpy().astype(bool)
    y = df[ycol].to_numpy(dtype=float)
    n_total = len(df)

    # The bases are fitted on the FULL sample and evaluated per arm. Fitting
    # them per arm would make ``b`` a different function in each, and the two
    # arm means would then be averages of different bridges — which (b2)
    # subtracts as though they were the same one. The same dictionary spans
    # both bridges, so a variable both of them expand the same way is
    # literally one basis rather than two derivations of it.
    shared: dict[tuple, _Basis] = {}
    outcome_span = _build_design(df, spec.outcome_bridge.span_terms, shared)
    outcome_moment = _build_design(df, spec.outcome_bridge.moment_terms, shared)
    design_a, design_b = outcome_moment.columns, outcome_span.columns
    # E[h(W, x, C)] is over the MARGINAL law of (W, C), so the average that
    # answers (b2) runs over every row rather than over the arm's — which is
    # also what makes a covariate's contribution an average over the
    # population's C rather than over the C of whoever got treated.
    w_bar = design_b.mean(axis=0)

    treated = _cross_moments(design_a[treated_rows], design_b[treated_rows],
                   y[treated_rows])
    control = _cross_moments(design_a[~treated_rows],
                             design_b[~treated_rows], y[~treated_rows])

    scale = float((np.trace(treated.g) + np.trace(control.g))
                  / (2 * outcome_span.width))
    if not np.isfinite(scale) or scale <= 0:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design=Design.BRIDGE_OUTCOME_MOMENTS)
    declared = spec.outcome_bridge.ridge is not None
    ridge = _ridge_for(scale, spec.outcome_bridge.ridge)

    channel: dict = {
        "estimator": str(spec.estimator),
        # Cross-moments and not the solved coefficients: θ is one function of
        # these and a penalty, so recording θ would record the answer and
        # invite a reader to check it against itself. From what is here a
        # second implementation re-derives θ at ANY penalty, both do-arms,
        # the standard errors, the condition numbers and the whole ladder —
        # without the data.
        #
        # The bases go out per TERM and per FACTOR within it, because that
        # is what a design over several variables is: a record naming one
        # basis a side cannot say which of several columns it belongs to,
        # and a verifier that cannot rebuild the arrangement can only check
        # the numbers against themselves.
        "z_basis": outcome_moment.as_record(),
        "w_basis": outcome_span.as_record(),
        "w_mean": tuple(float(v) for v in w_bar),
        "n_total": int(n_total),
        "treated": _block_record(treated),
        "control": _block_record(control),
        "ridge": ridge,
        "ridge_scale": scale,
        "ridge_was_declared": declared,
    }

    if spec.treatment_bridge is None:
        point = _at_fractions(treated, control, w_bar, scale, None,
                              spec.estimator)
        channel["penalty_ladder"] = _rung_ridges(
            _ladder(lambda f: point(f, None)), scale)
        theta_treated = solve_theta(treated.g, treated.c, ridge)
        theta_control = solve_theta(control.g, control.c, ridge)
        do_treated = float(w_bar @ theta_treated)
        do_control = float(w_bar @ theta_control)
        channel["estimates"] = {str(spec.estimator): do_treated - do_control}
        return BridgeSolution(
            point=do_treated - do_control,
            do_treated=do_treated,
            do_control=do_control,
            standard_error=_analytic_standard_error(
                spec.estimator, treated, control, w_bar, ridge,
                theta_treated, theta_control),
            ridge=ridge,
            ridge_was_declared=declared,
            channel=channel,
        )

    q_span = _build_design(df, spec.treatment_bridge.span_terms, shared)
    q_moment = _build_design(df, spec.treatment_bridge.moment_terms, shared)
    design_g, design_n = q_span.columns, q_moment.columns
    # Ω weights the moment directions by their own second moment over the
    # WHOLE sample, the mirror of ``S_AA⁻¹`` on the outcome side. Over the
    # whole sample and not the arm's because ``n̄`` on the right-hand side is
    # a full-sample mean: (q1) times an indicator, averaged over everyone.
    s_nn = design_n.T @ design_n / n_total
    if not np.isfinite(s_nn).all() or np.linalg.cond(s_nn) > _MAX_CONDITION_NUMBER:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design=Design.BRIDGE_INSTRUMENT_MOMENTS)
    weight_q = np.linalg.inv(s_nn)
    n_bar = design_n.mean(axis=0)

    q_arms = {}
    for name, rows in (("treated", treated_rows), ("control", ~treated_rows)):
        q_arms[name] = _treatment_arm(
            design_g[rows], design_n[rows], design_b[rows], y[rows],
            weight_q, n_bar, n_total)
    q_treated, q_control = q_arms["treated"], q_arms["control"]

    q_scale = float((np.trace(q_treated.g_operator)
                     + np.trace(q_control.g_operator)) / (2 * q_span.width))
    if not np.isfinite(q_scale) or q_scale <= 0:
        raise EstimatorFailure(
            Refusal.SINGULAR_DESIGN, design=Design.BRIDGE_OUTCOME_MOMENTS)
    q_declared = spec.treatment_bridge.ridge is not None
    q_ridge = _ridge_for(q_scale, spec.treatment_bridge.ridge)

    t_treated = solve_theta(q_treated.g_operator, q_treated.c, q_ridge)
    t_control = solve_theta(q_control.g_operator, q_control.c, q_ridge)
    q_treated = replace(q_treated, q_negative_fraction=float(
        (design_g[treated_rows] @ t_treated < 0).mean()))
    q_control = replace(q_control, q_negative_fraction=float(
        (design_g[~treated_rows] @ t_control < 0).mean()))

    at = _at_fractions(treated, control, w_bar, scale,
                       (q_treated, q_control, q_scale), spec.estimator)
    estimates = _all_estimates(treated, control, w_bar, ridge,
                               q_treated, q_control, q_ridge)
    channel["treatment_bridge"] = {
        "span_basis": q_span.as_record(),
        "moment_basis": q_moment.as_record(),
        # ``n̄`` and ``Ω`` are the right-hand side and the weight of a solve
        # over the whole sample, so they sit beside the arms rather than
        # inside one. ``w_mean`` above is the outcome bridge's counterpart
        # and they are different vectors whenever the two designs differ —
        # which, since a mirrored pair is refused at the door, is always.
        "moment_mean": tuple(float(v) for v in n_bar),
        "s_nn": _matrix(s_nn),
        "treated": _treatment_record(q_treated),
        "control": _treatment_record(q_control),
        "ridge": q_ridge,
        "ridge_scale": q_scale,
        "ridge_was_declared": q_declared,
    }
    channel["estimates"] = {k: float(v) for k, v in estimates.items()}
    channel["penalty_ladder"] = _rung_ridges(_ladder(lambda f: at(f, f)), scale)

    theta_treated = solve_theta(treated.g, treated.c, ridge)
    theta_control = solve_theta(control.g, control.c, ridge)
    return BridgeSolution(
        point=estimates[str(spec.estimator)],
        do_treated=float(w_bar @ theta_treated),
        do_control=float(w_bar @ theta_control),
        standard_error=_analytic_standard_error(
            spec.estimator, treated, control, w_bar, ridge, theta_treated,
            theta_control),
        ridge=ridge,
        ridge_was_declared=declared,
        channel=channel,
    )


def _all_estimates(treated: _SolveBlock, control: _SolveBlock, w_bar: np.ndarray,
                   ridge: float, q_treated: _TreatmentArm,
                   q_control: _TreatmentArm, q_ridge: float) -> "dict[str, float]":
    """All three answers the two bridges support, at the penalties in force.

    Computed together and reported together. They are three different claims
    about the same population quantity, each right under its own assumption,
    and a reader who can see them side by side can see whether the two
    assumptions agree — which is a fact about this data that no single one of
    them carries.
    """
    theta = {arm: solve_theta(a.g, a.c, ridge)
             for arm, a in (("1", treated), ("0", control))}
    t = {arm: solve_theta(a.g_operator, a.c, q_ridge)
         for arm, a in (("1", q_treated), ("0", q_control))}
    q_arm = {"1": q_treated, "0": q_control}
    por = float(w_bar @ (theta["1"] - theta["0"]))
    pipw = float(sum(sign * (t[arm] @ q_arm[arm].s)
                     for sign, arm in ((1.0, "1"), (-1.0, "0"))))
    pdr = float(sum(
        sign * (t[arm] @ (q_arm[arm].s - q_arm[arm].r @ theta[arm])
                + w_bar @ theta[arm])
        for sign, arm in ((1.0, "1"), (-1.0, "0"))))
    return {"outcome_regression": por,
            "inverse_probability": pipw,
            "doubly_robust": pdr}


def _at_fractions(
    treated: _SolveBlock, control: _SolveBlock, w_bar: np.ndarray, scale: float,
    treatment: "tuple[_TreatmentArm, _TreatmentArm, float] | None",
    estimator: ProximalEstimator,
) -> "Callable[[float, float | None], float]":
    """The declared estimator as a function of the penalties, for the ladder.

    The ladder has to re-solve THE answer, not a fixed one: an answer that
    rests on two bridges moves under both penalties, and a ladder that
    re-solved the outcome regression while reporting the doubly robust
    number would be measuring the stability of something else.
    """
    def at(fraction: float, q_fraction: "float | None") -> float:
        ridge = fraction * scale
        if treatment is None:
            return float(w_bar @ (solve_theta(treated.g, treated.c, ridge)
                                  - solve_theta(control.g, control.c, ridge)))
        q_treated, q_control, q_scale = treatment
        assert q_fraction is not None
        return _all_estimates(treated, control, w_bar, ridge, q_treated,
                              q_control, q_fraction * q_scale)[str(estimator)]

    return at


def _block_record(arm: _SolveBlock) -> dict:
    return {
        "n": int(arm.n),
        "s_aa": _matrix(arm.s_aa),
        "s_ab": _matrix(arm.s_ab),
        "s_ay": tuple(float(v) for v in arm.s_ay),
        "s_bb": _matrix(arm.s_bb),
        "s_by": tuple(float(v) for v in arm.s_by),
        "yy": float(arm.yy),
    }


def _treatment_record(arm: _TreatmentArm) -> dict:
    return {
        "n": int(arm.n),
        "m": _matrix(arm.m),
        "s": tuple(float(v) for v in arm.s),
        "r": _matrix(arm.r),
        "gg": _matrix(arm.gg),
        "q_negative_fraction": float(arm.q_negative_fraction),
    }


def _matrix(m: np.ndarray) -> tuple[tuple[float, ...], ...]:
    return tuple(tuple(float(v) for v in row) for row in m)
