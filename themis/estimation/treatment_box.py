"""The treatment box — its corners, how many of them there may be, and the
two ways an interaction over them can fail to exist.

A joint intervention on K binary treatments has 2^K corners. The joint
CONTRAST needs two of them (all-hi and all-lo); the highest-order causal
interaction needs every one, because it IS the K-th mixed finite difference
over the box::

    interaction_K = Σ_{corners} (−1)^{#{treatments at lo}} E[Y | do(corner)]

Two estimators reach that quantity by different roads — the joint back-door
g-formula standardizes a saturated outcome model over the corners, and the
joint general-ID plug-in identifies each corner's estimand and evaluates it —
but the box they enumerate is the same box, and the alternating sign is the
same definition. Keeping the enumeration, the sign, the cap and the RECORD of
the walked box here is what stops the definition from having two copies that
can drift apart.

The record is the fourth of those and it was the last to arrive. Both routes
compute every corner and take their two reported numbers as differences of
them; for a long time only one route kept the corners, and the difference
that made was not a rendering detail — the route that kept them had both its
numbers re-derived, and the route that dropped them had a joint contrast
nothing on the envelope could contradict.

The cap is a resource bound, not a fundamental one: identification places no
limit on K, and both estimators still report the CONTRAST above it, since that
one needs two corners no matter how large the box is. What the cap withholds is
the interaction, and :data:`INTERACTION_UNAVAILABLE_KINDS` is what an estimator
says instead of a number when it does.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import product


#: Bound on 2^K corner enumeration, shared by every route that walks the
#: treatment box. Five treatments is 32 corners — the saturated back-door
#: basis is 2^K − 1 columns wide and the general-ID plug-in identifies once
#: per corner, so both grow the same way and both stop at the same place.
MAX_JOINT_TREATMENTS = 5

#: Why an estimator has a joint contrast but no K-way interaction to put
#: beside it. Both members leave the contrast intact, which is the reason
#: they are a withholding rather than a refusal:
#:
#: - ``corner_unsupported`` — a corner of the box has nothing to stand on.
#:   The outcome model (or the identified estimand) would still produce a
#:   number there, so what is on offer is an extrapolation reported as a
#:   measurement.
#: - ``order_above_cap`` — K is past :data:`MAX_JOINT_TREATMENTS`, so the
#:   box was never walked. The data may well support every corner; nobody
#:   looked.
#:
#: A closed vocabulary rather than a sentence: the two say different things
#: to a reader deciding what to do next (supply the missing cell, versus ask
#: for a smaller treatment vector), and only the reader's own surface knows
#: which language to say it in.
INTERACTION_UNAVAILABLE_KINDS: tuple[str, ...] = (
    "corner_unsupported",
    "order_above_cap",
)

Corner = tuple[bool, ...]
Cell = tuple[tuple[str, object], ...]


def corners(k: int) -> tuple[Corner, ...]:
    """The 2^k corners of the treatment box, each a per-treatment hi/lo mask.

    ``mask[i]`` true means treatment ``i`` is at its high level. The order is
    :func:`itertools.product`'s, which puts the all-hi corner first and the
    all-lo corner last — stable across calls, so a recorded corner list and a
    recomputed one line up positionally as well as by cell.
    """
    return tuple(product((True, False), repeat=k))


def interaction_sign(mask: Corner) -> float:
    """``(−1)^{#treatments at lo}`` — this corner's weight in the K-way
    finite difference. The alternating sum annihilates every lower-order
    term (main effects, all the pairwise and intermediate interactions) and
    the covariate contribution, leaving the top-order interaction alone."""
    return -1.0 if mask.count(False) % 2 else 1.0


def cell(
    mask: Corner,
    treatments: tuple[str, ...],
    high: Mapping[str, object],
    low: Mapping[str, object],
) -> Cell:
    """The corner named in the caller's own levels rather than in the mask.

    A mask is how the enumeration talks about a corner; ``{treatment: value}``
    is how a reader and a positivity check do. The values come from ``high`` /
    ``low`` untouched, so a bool stays a bool and a coded level stays whatever
    the column holds — never whatever a design matrix turned it into.
    """
    return tuple(
        (t, (high if mask[k] else low)[t]) for k, t in enumerate(treatments)
    )


@dataclass(frozen=True)
class CornerRisk:
    """``E[Y | do(cell)]`` at one corner of the treatment box.

    The estimator's own output, before any difference is taken. Recorded
    rather than discarded because both reported quantities are finite
    differences of these: the contrast is two of them subtracted, the K-way
    interaction is the alternating sum of all of them. An auditor holding
    the corners re-derives both; one holding only the two results can check
    that they are numbers and nothing more.

    ``risk`` because that is what this package calls the standardized value
    at an arm, whatever scale the outcome is on — a controlled direct
    effect's curve reports ``risk_treated`` for a linear outcome too. It is
    a probability when the outcome is binary; a route that can name the level
    it is the probability OF puts it on the envelope as ``outcome_high``, and
    an auditor holds the corners to the unit interval exactly there.
    """

    cell: Cell
    risk: float
