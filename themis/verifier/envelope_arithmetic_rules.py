"""What an interval costs, worked out from the interval.

Some of what a reader is shown is not a measurement at all. "Your interval
is 0.046 wide, that is 21% of the effect, and 4000 subjects would halve it"
states three sums over the interval, the point and the sample size sitting
beside them on the same envelope.

None of it was checked. The derivation records what the estimator did; it
does not record the sums somebody took afterwards, so the rule that holds
the reader's copy to the record had nothing to hold these against. They
reached a reader on the producer's word — and the most actionable figure
this system prints, go and collect four thousand more subjects, is the one
nobody would recompute by hand.

Nothing had to be recorded to close them: every input is already on the
envelope. That is what makes this a different species from the audits that
re-derive an estimator. There is no independence question, because there is
no second implementation — only an identity that holds or does not.

**Measured before asserted, and measured again after.** Eight candidate
relations were checked against the forty-four answer shapes the suite
produces. Two failed on honest answers and are absent: the additive
interaction is not the sum of the two interaction terms, and the two blocks
that each report a proportion mediated do not agree on the logit scale.
Three more held — the mediation total against its parts, and two of the
four-way ratios — and are STILL absent, because re-running the sweep with
and without them closed exactly the same leaves: ``verify_mediation_numeric``
already holds every one. A rule restating a check that exists is not a
second opinion, it is a second place for the same thing to be wrong.

**Independence pin:** this module MUST NOT import from ``themis.output`` or
``themis.estimation``. The identity is restated from what it means, not
from the code that computed it.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "envelope_arithmetic_check"

#: The reader's copy is rounded — six places for a half width, four for a
#: ratio — so the comparison allows half a place of it and nothing more. A
#: tolerance wider than the rounding would start accepting numbers that are
#: not the rounding of anything.
_HALF_WIDTH_TOL = 5.1e-7
_RATIO_TOL = 5.1e-5

#: What halving an interval costs. A confidence interval narrows with the
#: square root of the sample, so four times the sample halves it.
_HALVING_FACTOR = 4

#: And the figure is a number of people somebody is being asked to recruit,
#: so it reaches them rounded up to a round number rather than as 4n to the
#: unit. The step is restated here because a check written as exactly 4n
#: refuses an honest answer whenever 4n is not already a multiple of it —
#: which is what happened, on a sample of ninety, in a test the
#: forty-four-shape snapshot does not contain.
_RECRUITMENT_STEP = 50


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(
        value, bool) else None


def _refuse(what: str, shown, computed) -> None:
    gives = ("nothing — the figure it is a share OF is zero or absent"
             if computed is None else repr(computed))
    raise VerificationError(
        f"{what} is {shown!r} and the numbers beside it on this same "
        f"envelope give {gives}; a figure a reader acts on that no "
        f"other figure supports is the producer's word twice",
        rule=_RULE,
    )


def _point_of(node: dict):
    """A sub-answer's central value. A dose-response point spells it
    ``effect`` where an estimate spells it ``point``, and both are the
    number a ratio beside them is a ratio of."""
    for key in ("point", "effect"):
        found = _num(node.get(key))
        if found is not None:
            return found
    return None


def _check_precision_budget(node: dict, sample_size, where: str) -> None:
    budget = node.get("precision_budget")
    if not isinstance(budget, dict):
        return
    lower, upper = _num(node.get("ci_lower")), _num(node.get("ci_upper"))
    if lower is None or upper is None:
        raise VerificationError(
            f"{where}.precision_budget prices an interval that is not "
            f"beside it; a budget for narrowing nothing cannot be wrong "
            f"and cannot be right",
            rule=_RULE,
        )
    half = (upper - lower) / 2
    shown = _num(budget.get("current_ci_half_width"))
    if shown is not None and abs(shown - half) > _HALF_WIDTH_TOL:
        _refuse(f"{where}.precision_budget.current_ci_half_width", shown, half)

    point = _point_of(node)
    shown = _num(budget.get("relative_width"))
    if shown is not None:
        # A width relative to nothing. The guard here was `if point:`,
        # written to keep a zero out of a denominator, and skipping is not
        # what a zero denominator means: it means the ratio beside it
        # cannot be right. Measured — a sweep that bends a point to exactly
        # 0.0 walked through this, taking the whole joint effect with it,
        # because the ratio was the only thing holding that number.
        if not point:
            _refuse(f"{where}.precision_budget.relative_width", shown, None)
        relative = half / abs(point)
        if abs(shown - relative) > _RATIO_TOL:
            _refuse(f"{where}.precision_budget.relative_width",
                    shown, relative)

    # Every budget on the envelope, including the one on each point of a
    # dose-response curve. Those looked at first like a slice with a sample
    # of its own — their figure is not four times the run's total — and the
    # rule was written to decline them. It was the rounding that was
    # missing, not the sample: with it they hold, and the exception went.
    shown = budget.get("n_to_halve_ci")
    if shown is not None and sample_size:
        needed = _HALVING_FACTOR * sample_size
        want = -(-needed // _RECRUITMENT_STEP) * _RECRUITMENT_STEP
        if shown != want:
            _refuse(f"{where}.precision_budget.n_to_halve_ci", shown, want)


def _walk(node, path, sample_size) -> None:
    """Wherever a budget appears, and not at a list of places it is known
    to appear: a block added under a new name arrives here on its own."""
    if isinstance(node, dict):
        _check_precision_budget(
            node, sample_size, ".".join(path) or "numeric_estimate")
        for key, value in node.items():
            _walk(value, path + (key,), sample_size)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _walk(value, path + (f"[{index}]",), sample_size)


def verify_envelope_arithmetic(result: dict) -> None:
    """Hold every figure the envelope computed from its own figures.

    Returns ``None`` on accept; raises ``VerificationError`` naming the
    figure, what it says and what the numbers beside it give.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    _walk(estimate, (), _num(estimate.get("sample_size")))
