"""A transported effect, added up again from what it is a sum over.

Transport reweights a source population's strata by the target's covariate
distribution: the answer is Σ_z P*(z)·[E(Y|X=1,z) − E(Y|X=0,z)], one term
per cell of the declared target marginal.

**This number rode on nothing.** The route attaches a ``numeric_estimate``
to a result whose derivation ends at ``identify_via_transport`` and appends
no step of its own — the chain says how the estimand was IDENTIFIED and
stops. So the rule that holds a reader's copy to the record had no record
to hold it against, and a rule comparing two copies does nothing at all
when the second one is absent. Doing nothing and passing look identical at
the door. Measured, end to end: a transported effect of 0.4106 could be
shown as 2.23, as −1.41, or as 0.0, and the public door accepted each.

What closes it is not a second implementation of the estimator — there is
nothing to be independent OF here. It is the estimand's own definition,
restated over statistics the producer now records: per cell, the target
weight and each arm's size and outcome total. Sums and counts rather than
the two means, so this divides for itself; a mean copied onto the envelope
would be one more figure taken on the producer's word.

**Independence pin:** this module MUST NOT import from
``themis.estimation``. The identity is restated from what transport means.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "post_stratification_check"

#: The point reaches a reader in full precision, so the only distance
#: allowed between it and the sum is floating-point reassociation over the
#: cells — the producer adds them in one order and this adds them in
#: another.
_TOL = 1e-9

#: The weights are a caller's declaration rather than a computed figure, so
#: what they may drift by is what adding a handful of decimals costs, not
#: what an estimator's arithmetic costs.
_WEIGHT_TOL = 1e-9

_BLOCK = "post_stratification"


def _refuse(what: str, detail: str) -> None:
    raise VerificationError(
        f"{what}: {detail}; a transported effect that the strata it is a "
        f"sum over do not add up to is the producer's word twice",
        rule=_RULE,
    )


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(
        value, bool) else None


def verify_post_stratification(result: dict) -> None:
    """Re-derive a transported point estimate from its own strata.

    Returns ``None`` on accept. Raises ``VerificationError`` when the sum
    disagrees with the number shown, when a cell is missing what it takes
    to add it up, or when an answer of this method carries no strata at
    all — that last one because "nothing to check" is the state this rule
    exists to make impossible to be in silently.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    if estimate.get("method") != "transport_post_stratification":
        return

    rows = estimate.get(_BLOCK)
    if not isinstance(rows, list) or not rows:
        _refuse(f"numeric_estimate.{_BLOCK}",
                "a transported effect arrives with no record of the strata "
                "it was summed over, and its derivation records the "
                "identification rather than the estimation, so nothing "
                "anywhere can re-derive it")
        return

    point = _num(estimate.get("point"))
    if point is None:
        _refuse("numeric_estimate.point",
                "the strata are recorded and the number they add up to is "
                "not on the envelope")
        return

    # Which cell each row describes is the one thing the sum above does not
    # read: relabel two rows and the arithmetic is untouched while a reader
    # is shown the target's weight for one stratum against another's
    # numbers. Held to what survives with no record to check against — a
    # row's coordinates are the variables adjusted for, and two rows of one
    # table are two different cells.
    adjustment = estimate.get("adjustment")
    named = set(adjustment) if isinstance(adjustment, list) else None
    seen: set = set()

    total, weights = 0.0, 0.0
    for index, row in enumerate(rows):
        where = f"numeric_estimate.{_BLOCK}[{index}]"
        if not isinstance(row, dict):
            _refuse(where, "a stratum that is not an object")
            return
        values = row.get("values")
        if not isinstance(values, dict) or not values:
            _refuse(f"{where}.values",
                    "a stratum that does not say which stratum it is")
            return
        if named is not None and set(values) != named:
            _refuse(f"{where}.values",
                    f"a stratum over {sorted(values)} where this answer "
                    f"adjusts for {sorted(named)}")
            return
        cell = tuple(sorted((str(k), repr(v)) for k, v in values.items()))
        if cell in seen:
            _refuse(f"{where}.values",
                    "a cell another row of this same table already "
                    "describes, so one of the two weights is applied to "
                    "numbers that are not its own")
            return
        seen.add(cell)
        weight = _num(row.get("probability"))
        n_treated, n_control = _num(row.get("n_treated")), \
            _num(row.get("n_control"))
        sum_treated, sum_control = _num(row.get("sum_treated")), \
            _num(row.get("sum_control"))
        if None in (weight, n_treated, n_control, sum_treated, sum_control):
            _refuse(where,
                    "a stratum missing the weight, an arm size or an arm "
                    "total, so its term cannot be added up")
            return
        if not n_treated or not n_control:
            # An arm with nobody in it. The estimator refuses this before it
            # can reach an answer, so seeing it here means the record was
            # edited — and dividing by it would raise where the reader
            # deserves a sentence.
            _refuse(where,
                    "a stratum with an empty arm, which is a contrast that "
                    "cannot have been taken")
            return
        total += weight * (sum_treated / n_treated - sum_control / n_control)
        weights += weight

    # A target marginal is a distribution over the strata. Two weights moved
    # against each other leave the sum below untouched, and this is what
    # says so.
    if abs(weights - 1.0) > _WEIGHT_TOL:
        _refuse(f"numeric_estimate.{_BLOCK}",
                f"the target weights add up to {weights!r} rather than to a "
                f"whole population")

    if abs(total - point) > _TOL:
        _refuse("numeric_estimate.point",
                f"shown as {point!r}, and the {len(rows)} strata beside it "
                f"weight up to {total!r}")

    shown_n = _num(estimate.get("sample_size"))
    counted = sum(_num(r.get("n_treated")) + _num(r.get("n_control"))
                  for r in rows)
    if shown_n is not None and counted > shown_n:
        # Not equality: a target marginal names the cells it weights, and a
        # source may hold rows in strata it never mentions. More units in
        # the strata than in the run is the direction that cannot happen.
        _refuse("numeric_estimate.sample_size",
                f"the run says {shown_n!r} units and the strata account for "
                f"{counted!r} of them")
