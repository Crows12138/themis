"""The response-function polytope: sharp bounds from an instrument.

An instrument partitions a population into RESPONSE TYPES — a map from
instrument level to treatment taken, and a map from treatment to outcome
shown — and every causal quantity an IV model can speak about is a linear
functional of the distribution over those types. Bounding one is a
linear program over the types that reproduce ``P(X, Y | Z)``, so the range
this module returns is the identified set by its definition rather than an
approximation of it.

WHY THIS IS NOT IN ``estimation/`` OR IN ``runtime/``. The program consumes
two arrays — the table ``P[z, x, y]`` and the marginal ``P(z)`` — and knows
nothing about where they came from. They come from a DataFrame on the data
end and from ``theta`` on the parameter end, and those two ends live in
packages that must not import each other. A solver owned by either one is
reachable from only one of them, and the door that cannot reach it does not
degrade quietly: it reports that the data are insufficient while holding
exactly the table the program wanted. So the polytope sits beside the other
contracts both ends share, and neither owns it.

Reference: Balke & Pearl 1997 JASA / Balke 1995 (thesis); Pearl "Causality"
2nd ed. ch. 8. For the generalisation past binary variables, Cheng & Small
2006 and Richardson & Robins 2014 on multi-valued instruments, and the
causaloptim R package (Sachs, Jonzon, Gabriel & Sjolander), which computes
the same class symbolically by vertex enumeration where this module solves
one LP per table.
"""
from __future__ import annotations

import itertools
from functools import lru_cache

import numpy as np

from . import refusals
from .output.bounds import MAX_RESPONSE_TYPES, response_type_count
from .refusals import EstimatorFailure, Refusal
from .types import envelope_scalar


@lru_cache(maxsize=32)
def _response_types(nx: int, ny: int, nz: int) -> tuple[tuple, tuple]:
    """(X-response types, Y-response types) as tuples of maps, indexed by
    level POSITION: ``fx[z] = x`` and ``gy[x] = y``.

    ``ny`` stays in the exponent. Collapsing the outcome to "is it the value
    the query asked about" would take it out, and is the obvious way to buy
    back the size :data:`~themis.output.bounds.MAX_RESPONSE_TYPES` spends;
    measured over 240 random tables it moves the answer on 154 of them, by up
    to 0.323. Collapsing the outcome collapses the observed table with it, and
    the equality constraints the finer table imposes are information about
    which mixtures of types reproduce the data — dropping them can only
    enlarge the feasible set, so the shortcut is valid and loose rather than
    wrong, which is why it has to be rejected on a number and not on whether
    it looks sound.
    """
    return (
        tuple(itertools.product(range(nx), repeat=nz)),
        tuple(itertools.product(range(ny), repeat=nx)),
    )


@lru_cache(maxsize=32)
def _response_constraints(nx: int, ny: int, nz: int) -> np.ndarray:
    """The equality-constraint matrix mapping a distribution over response
    types to the observable table ``P(X=x, Y=y | Z=z)``, plus the row that
    makes it a distribution.

    Built from the cardinalities alone, so it is identical across bootstrap
    replicates and cached rather than rebuilt (only the right-hand side moves).
    """
    fxs, gys = _response_types(nx, ny, nz)
    A = np.zeros((nz * nx * ny + 1, len(fxs) * len(gys)))
    row = 0
    for z in range(nz):
        for x in range(nx):
            for y in range(ny):
                for i, fx in enumerate(fxs):
                    if fx[z] != x:
                        continue
                    for j, gy in enumerate(gys):
                        if gy[x] == y:
                            A[row, i * len(gys) + j] = 1.0
                row += 1
    A[row, :] = 1.0
    return A


def _arm_objective(nx: int, ny: int, nz: int, xi: int, yi: int) -> np.ndarray:
    """Coefficients of ``P(Y=y | do(X=x))`` over the response types: a type
    contributes iff its outcome map sends level ``xi`` to level ``yi``.
    Intervening fixes X, so the treatment map plays no part."""
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for i in range(len(fxs)):
        for j, gy in enumerate(gys):
            if gy[xi] == yi:
                c[i * len(gys) + j] = 1.0
    return c


def _contrast_objective(
    nx: int, ny: int, nz: int, yi: int, hi_xi: int, lo_xi: int,
) -> np.ndarray:
    """Coefficients of ``P(Y=y|do(X=hi)) − P(Y=y|do(X=lo))`` — the same type
    distribution read through a difference instead of a level."""
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for i in range(len(fxs)):
        for j, gy in enumerate(gys):
            c[i * len(gys) + j] = (
                (1.0 if gy[hi_xi] == yi else 0.0)
                - (1.0 if gy[lo_xi] == yi else 0.0)
            )
    return c


def _potential_outcome_objective(
    nx: int, ny: int, nz: int, p_z: np.ndarray,
    *, outcome_map: dict[int, int], factual_arm: int | None,
) -> np.ndarray:
    """Coefficients of ``P(⋀_a Y_{x=a} = outcome_map[a] [, X = factual_arm])``
    over the response types.

    A unit of type ``(fx, gy)`` sitting at instrument level ``z`` takes
    treatment ``fx[z]``, shows outcome ``gy[fx[z]]``, and would have shown
    ``gy[a]`` under ``do(X=a)`` for every ``a`` at once. So a conjunction over
    ARMS is a property of ``gy`` alone, however many arms it names and whether
    or not any of them was the one actually taken — which is why one objective
    covers a counterfactual cell and a probability of causation without
    knowing which it is building.

    ``factual_arm`` is the treatment the unit must actually have taken, and it
    is where the two part company. A cell conditions on the factual world, so
    ``P(z)`` multiplies through — the IV model's independence is exactly the
    claim that the type does not depend on the level. PNS conditions on
    nothing, so every type counts once and no weight appears.

    Callers pass arms that differ (a cell reaches this program only when the
    two worlds do not coincide; PNS names both levels), so the map cannot
    silently lose a constraint to a repeated key.
    """
    fxs, gys = _response_types(nx, ny, nz)
    c = np.zeros(len(fxs) * len(gys))
    for j, gy in enumerate(gys):
        if any(gy[arm] != value for arm, value in outcome_map.items()):
            continue
        for i, fx in enumerate(fxs):
            c[i * len(gys) + j] = (
                1.0 if factual_arm is None
                else float(
                    sum(p_z[zi] for zi in range(nz) if fx[zi] == factual_arm)
                )
            )
    return c


def _factual_mass(
    P: np.ndarray, p_z: np.ndarray,
    *, outcome_map: dict[int, int], factual_arm: int | None,
) -> float:
    """The conditioning event's probability — the objective's DENOMINATOR.

    ``P(X=x [, Y=y])`` is fixed at the observed table by the equality
    constraints, so it is a known number rather than a variable; that is what
    keeps a conditional counterfactual a linear program rather than a
    fractional one. An unconditional functional (PNS) divides by nothing, and
    that is said as 1.0 rather than as a branch at the call site.
    """
    if factual_arm is None:
        return 1.0
    y_factual = outcome_map.get(factual_arm)
    return float(sum(
        p_z[zi] * (
            P[zi, factual_arm, y_factual] if y_factual is not None
            else P[zi, factual_arm, :].sum()
        )
        for zi in range(P.shape[0])
    ))


def monotone_y_types(nx: int, ny: int, direction) -> frozenset[int]:
    """Indices of the outcome-response maps a declared monotonicity permits.

    Monotonicity is a claim about which units the population contains — no
    unit whose outcome moves against the treatment — so it belongs in the
    response-function model as a restriction of the type space, not as a
    second formula applied afterwards. Levels are compared by POSITION, which
    is the sorted order of the observed values.
    """
    from .types import Monotonicity

    # The table is the exhaustiveness statement: a direction added to the enum
    # and not to this line fails at the lookup, rather than being folded into
    # whichever branch happened to be the fallback.
    ascending = {
        Monotonicity.NON_DECREASING: True,
        Monotonicity.NON_INCREASING: False,
    }[direction]
    gys = tuple(itertools.product(range(ny), repeat=nx))
    return frozenset(
        j for j, gy in enumerate(gys)
        if all(
            (gy[i] <= gy[i + 1]) if ascending else (gy[i] >= gy[i + 1])
            for i in range(nx - 1)
        )
    )


def _solve_response_lp(
    P: np.ndarray, nx: int, ny: int, nz: int, objective: np.ndarray,
    *, allowed_y_types: frozenset[int] | None = None,
) -> tuple[float, float]:
    """Range of a linear functional over every response-type distribution
    that reproduces ``P[z,x,y] = P(X=x, Y=y | Z=z)`` — the identified set by
    its definition, not an approximation of it.

    ``allowed_y_types`` narrows the population to the outcome-response maps a
    declared assumption permits; the constraint matrix is untouched, because
    forbidding a type is saying no unit is of it, and that is a bound of zero
    on its mass.
    """
    from scipy.optimize import linprog

    A_eq = _response_constraints(nx, ny, nz)
    b_eq = np.concatenate([P.reshape(-1), [1.0]])
    n_gy = ny ** nx
    simplex: list[tuple[float, float | None]] = [
        (0.0, None)
        if allowed_y_types is None or (k % n_gy) in allowed_y_types
        else (0.0, 0.0)
        for k in range(A_eq.shape[1])
    ]
    lo = linprog(objective, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    hi = linprog(-objective, A_eq=A_eq, b_eq=b_eq, bounds=simplex, method="highs")
    if not (lo.success and hi.success):
        stalled = _not_infeasible(lo, hi)
        if stalled is not None:
            raise EstimatorFailure(
                Refusal.LINEAR_PROGRAM_FAILED,
                statuses=[int(lo.status), int(hi.status)],
                diagnostic=str(stalled.message),
            )
        # No type distribution reproduces the observed table under IV
        # independence + exclusion — i.e. the data REFUTES the instrument.
        # Translate the LP infeasibility into the instrumental inequality so
        # the message is causal rather than numeric.
        violation = _instrumental_inequality_violation(P, nx, ny, nz)
        raise EstimatorFailure(
            Refusal.IV_MODEL_REFUTED,
            f"the observed P(X,Y|Z) table is incompatible with the IV model "
            f"at {nx}×{ny}×{nz} levels: no distribution over response types "
            "reproduces it under instrument independence + exclusion. "
            + (violation or "The response-function LP is infeasible.")
            + " Either the instrument is invalid (IV1/IV2/IV3 fail) or, on a "
            "small sample, this is sampling noise near the model boundary.",
        )
    return float(lo.fun), float(-hi.fun)


#: What HiGHS reports when the constraints admit no point at all. The one
#: status that is a statement about the MODEL: everything else non-zero is
#: the solver saying it stopped — an iteration or time limit, a numerical
#: breakdown, an unbounded objective.
_LP_INFEASIBLE = 2


def _not_infeasible(*programs):
    """The first program that did not certify infeasibility, or ``None``.

    ``success`` is a two-valued shadow of a five-valued status, and only one
    of those values licenses the conclusion the caller draws from it. Read
    off ``success`` alone, an iteration limit becomes "your instrument is
    refuted" — a claim about the reader's graph, made because a solver ran
    out of iterations, and made in the one direction where being wrong costs
    the most: the reader is told to distrust a design that may be sound.

    Both programs, because they share their feasible set — same equality
    constraints, same simplex, opposite objectives — so a refutation is
    something both of them prove and a disagreement between them is a
    solver's, not the data's.
    """
    return next((p for p in programs if p.status != _LP_INFEASIBLE), None)


def _instrumental_inequality_violation(
    P: np.ndarray, nx: int, ny: int, nz: int,
) -> str | None:
    """Pearl's instrumental inequality: for each treatment level,
    ``Σ_y max_z P(Y=y, X=x | Z=z) ≤ 1``. A violation WITNESSES that the IV
    model is refuted, and reduces to Balke-Pearl (1997) eq (6)'s four checks
    when everything is binary.

    It is a witness, not the whole test: outside the binary-instrument case
    the inequality is not known here to be sufficient, so the caller treats
    the LP's infeasibility as the authority and uses this only to say WHY in
    the cases where it can.
    """
    worst_x, worst = -1, -1.0
    for x in range(nx):
        total = float(sum(P[:, x, y].max() for y in range(ny)))
        if total > worst:
            worst_x, worst = x, total
    if worst > 1.0 + 1e-9:
        return (
            f"Instrumental inequality violated at treatment level index "
            f"{worst_x}: Σ_y max_z P(Y=y, X=x | Z=z) = {worst:.4f} > 1 "
            f"(Pearl 1995; Balke-Pearl 1997 eq 6 in the binary case)."
        )
    return None


def polytope_preconditions(zcol: str, z_levels: list) -> None:
    """The instrument route's two preconditions on the instrument column.

    An instrument that never varies enumerates one ``z → x`` map and carries
    no information; one with too many levels enumerates ``2^|Z| · 4`` types and
    the LP behind them is re-solved once per bootstrap replicate. Neither is a
    reason to fall back quietly to a route that would have answered a weaker
    question — the caller is told which of its columns is the obstacle and
    what to do to it.

    Here rather than in either door, because what makes a table solvable is a
    property of the polytope and of nothing about who is asking.
    """
    if len(z_levels) < 2:
        raise EstimatorFailure(
            Refusal.INSUFFICIENT_SUPPORT,
            f"instrument {zcol!r} takes a single value "
            f"({refusals.describe(z_levels)}) in this sample; an instrument "
            f"that never varies carries no response types to bound over.",
        )
    if response_type_count(
        treatment_levels=2, outcome_levels=2, instrument_levels=len(z_levels),
    ) is None:
        raise EstimatorFailure(
            Refusal.RESPONSE_MODEL_TOO_LARGE,
            nx=2, ny=2, nz=len(z_levels), cap=MAX_RESPONSE_TYPES,
            instrument=zcol,
        )


def polytope_sufficient_statistic(
    P: np.ndarray, p_z: np.ndarray, z_levels: list,
) -> tuple[tuple, tuple, tuple]:
    """``(instrument_levels, p_xyz, p_z)`` as plain Python, for the envelope.

    What the envelope carries has to be what the LP consumed, not a numpy view
    of it, and the level list has to travel WITH the table: the table's own
    shape says nothing about which stratum is which, so a permuted reading
    re-derives a different interval and calls an honest producer a liar. The
    three go out together because they are only meaningful together.
    """
    return (
        tuple(envelope_scalar(v) for v in z_levels),
        tuple(
            tuple(tuple(float(P[z, x, y]) for y in range(P.shape[2]))
                  for x in range(P.shape[1]))
            for z in range(P.shape[0])
        ),
        tuple(float(v) for v in p_z),
    )


def potential_outcome_response_bounds(
    P: np.ndarray, p_z: np.ndarray,
    *, outcome_map: dict[int, int], factual_arm: int | None, monotonicity=None,
) -> tuple[float, float]:
    """Sharp bounds on one potential-outcome functional, from an instrument.

    The functional is ``P(⋀_a Y_{x=a} = outcome_map[a] | X = factual_arm)``:
    a counterfactual cell when one arm carries the target and the other the
    factual evidence, a probability of causation when both arms are named at
    once. Either way it is a ratio of two linear functionals over the
    response-type distributions that reproduce ``P(X, Y | Z)`` — the polytope
    Balke-Pearl's arm bounds are read off — with a denominator the equality
    constraints hold constant across the feasible set. So the range is the
    identified set by its definition, not an approximation of it, and the
    method is one program with a different objective vector each time.

    That is also why this is sharp where routing an ARM'S INTERVAL through a
    closed-form theorem is not: the theorem consumes the interventional risk
    as a scalar, and a scalar cannot carry the fact that the distribution
    producing the risk is the one that has to produce the answer.

    What that is worth is measured rather than argued, because the two-step is
    valid and cheap-looking and would otherwise keep being proposed: over 400
    random binary IV models sampled straight from the response-type
    distribution, it says something non-trivial about 46 of them against this
    program's 133, the widest single gap being [0.9207, 1.0] here against
    [0, 1] there. The median width ratio is 1.000 — an average reports the loss
    as nothing, because it is concentrated in exactly the models where having
    an instrument was worth anything. Both cover the truth on all 400, and the
    cheap route is not cheaper: same polytope, different objective vector.

    A declared ``monotonicity`` enters as the population containing no unit
    whose outcome moves against the treatment. When that leaves the program
    infeasible but dropping it does not, the assumption — not the instrument —
    is what the data refute, and the two are told apart rather than reported
    under whichever refusal came first.
    """
    nz, nx, ny = P.shape
    objective = _potential_outcome_objective(
        nx, ny, nz, p_z, outcome_map=outcome_map, factual_arm=factual_arm,
    )
    denominator = _factual_mass(
        P, p_z, outcome_map=outcome_map, factual_arm=factual_arm,
    )
    allowed = (
        None if monotonicity is None
        else monotone_y_types(nx, ny, monotonicity)
    )
    try:
        lower, upper = _solve_response_lp(
            P, nx, ny, nz, objective, allowed_y_types=allowed,
        )
    except EstimatorFailure:
        if allowed is None:
            raise
        _solve_response_lp(P, nx, ny, nz, objective)
        raise EstimatorFailure(Refusal.COUNTERFACTUAL_INPUTS_INFEASIBLE)
    if denominator <= 0.0:
        # The conditioning event has no mass, so the functional is a ratio of
        # zeros and no distribution can distinguish its values. The identity
        # route answers the same degeneracy with the same box; disagreeing
        # about it would make WHICH ROUTE ran visible in the answer.
        return 0.0, 1.0
    # The numerator is a sub-event of the denominator on every feasible point,
    # so the ratio is a probability by construction and anything outside [0, 1]
    # is the simplex solver's last few bits. Clamped for the same reason the
    # identity route clamps: an answer that leaves [0, 1] is not a tighter
    # claim, it is a claim the quantity cannot carry.
    return (
        min(max(lower / denominator, 0.0), 1.0),
        min(max(upper / denominator, 0.0), 1.0),
    )


def counterfactual_cell_response_bounds(
    P: np.ndarray, p_z: np.ndarray,
    *, x_observed: int, x_counterfactual: int, y_star: int,
    factual_y: int | None, monotonicity=None,
) -> tuple[float, float]:
    """``P(Y_{x'}=y* | X=x [, Y=y])`` — the cell's coordinates as a functional.

    The cell reaches this program only when the two worlds differ (a same-world
    cell is answered by consistency and never gets here), so the two arms named
    below are distinct and neither constraint can displace the other.
    """
    outcome_map = {x_counterfactual: y_star}
    if factual_y is not None:
        outcome_map[x_observed] = factual_y
    return potential_outcome_response_bounds(
        P, p_z, outcome_map=outcome_map, factual_arm=x_observed,
        monotonicity=monotonicity,
    )


#: PN, PS and PNS as (outcome map, factual arm) over a BINARY treatment.
#:
#: All three name the same outcome-response map — the unit whose outcome
#: follows the treatment, ``Y_{x=0}=0`` and ``Y_{x=1}=1``. That is not a
#: coincidence to be noted afterwards; it is what "probabilities of causation"
#: means. They differ only in which factual population the question asks about:
#: PN asks among the treated who responded, PS among the untreated who did not,
#: and PNS asks about everyone, which is why its factual arm is absent rather
#: than set to something. Written as data because three rows saying the same
#: thing in three branches is how the three drift apart.
CAUSATION_FUNCTIONALS: dict[str, tuple[dict[int, int], int | None]] = {
    "pn": ({0: 0, 1: 1}, 1),
    "ps": ({0: 0, 1: 1}, 0),
    "pns": ({0: 0, 1: 1}, None),
}


def causation_response_bounds(
    P: np.ndarray, p_z: np.ndarray, *, monotonicity=None,
) -> dict[str, tuple[float, float]]:
    """PN / PS / PNS from an instrument, as three reads of one polytope.

    The alternative to this route is Tian-Pearl's closed form, which needs both
    interventional risks as numbers; when the graph carries a bow arc there are
    none to be had and the closed form has nothing to consume. So this is not a
    tighter version of that answer — it is an answer where that one does not
    exist, obtained under the instrument's three assumptions instead of under a
    back door.
    """
    return {
        name: potential_outcome_response_bounds(
            P, p_z, outcome_map=outcome_map, factual_arm=factual_arm,
            monotonicity=monotonicity,
        )
        for name, (outcome_map, factual_arm) in CAUSATION_FUNCTIONALS.items()
    }
