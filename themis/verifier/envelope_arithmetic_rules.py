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

A second relation was added the same way and passes the same two tests. A
stratified Wald block states an aggregate beside the rows it is an aggregate
of, and the contract spells the arithmetic out at the fields themselves
("Sum over strata of P(w) times the instrument's shift in the outcome") and
says the breakdown is carried so a consumer can check every component. Two
routes reach that table. One keeps a derivation record and a rule executes
the formula against it; the other keeps none, so nothing executed the
formula anywhere on that envelope — measured, every component of it could
be moved and all twelve doors that read the envelope agreed.

**Two claims, and they do not have the same scope.** An identity is closed
on the envelope's own numbers, so it is true or false wherever it is asked.
"An interval with no budget means an endpoint is missing or the width is
zero" is closed on nothing: it reads a producer's habit, and reaches only
as far across the envelope as that producer writes. Both were read off one
traversal, which made the narrower claim's precondition the wider one's
boundary — the identity stopped where the promise stopped, at
``numeric_estimate``, while the reader's copy of the same block one key
over under ``extensions`` could tell a reader to recruit any number of
subjects at all and be contradicted by nothing. Measured on both sides:
the identity alone, from the root, refuses none of the answer shapes this
suite produces; the absence question asked from the root refuses twenty,
every one of them a derivation step's inputs or a bounds row, neither of
which was ever priced or meant to be.

**Independence pin:** this module MUST NOT import from ``themis.output`` or
``themis.estimation``. The identity is restated from what it means, not
from the code that computed it.
"""
from __future__ import annotations

import math

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


#: What a block calls the number its interval is around, and so the number a
#: ratio beside that interval is a ratio OF. A dose-response sample spells it
#: ``effect``, a margin of an ordered dose spells it ``weight``, and an
#: estimate spells it ``point``.
#:
#: Restated here and not imported, for the reason in this package's header.
#: The producer holds the same three words, because it is what decides which
#: sibling a budget is priced against; a test pins the two lists equal, which
#: is the only honest way to have one vocabulary in two modules that must not
#: see each other. A fourth word appearing on one side and not the other is
#: how this rule would go quiet on a whole block — measured: a margin's
#: budget priced against ``weight`` arrived here and was refused as a share
#: of nothing.
_ESTIMATE_NAMES = ("point", "effect", "weight")


def _point_of(node: dict):
    """A sub-answer's central value, under whichever of its names."""
    for key in _ESTIMATE_NAMES:
        found = _num(node.get(key))
        if found is not None:
            return found
    return None


def _no_budget_here(node: dict, sample_size, where: str) -> None:
    """A budget that is not there, held to why it could not be.

    Asked only across ``_BUDGET_IS_PROMISED``, because what makes the
    absence mean anything is a promise, and a promise belongs to whoever
    made it.

    Every figure below prices an interval, and an interval with no budget
    beside it is priced by nothing at all — which is how the reference row
    of every dose-response curve came to have two endpoints that could be
    moved anywhere. The producer attaches a budget wherever one can be
    computed, so its absence already MEANS something: an endpoint that is
    not there, or a width of zero. Read that way the absence is an answer;
    read as a skip it is a hole a forger opens by deleting a block.

    Measured over every shape this system produces before it was written:
    sixty-three intervals priced, forty-three with an endpoint missing,
    three degenerate, and none unexplained.
    """
    if "ci_lower" not in node or "ci_upper" not in node or not sample_size:
        return
    lower, upper = _num(node.get("ci_lower")), _num(node.get("ci_upper"))
    if lower is None or upper is None or upper == lower:
        return
    raise VerificationError(
        f"{where} carries an interval of width {upper - lower} and no "
        f"precision_budget; one is attached wherever it can be computed, so "
        f"its absence says an endpoint is missing or the width is zero, and "
        f"neither is so here",
        rule=_RULE,
    )


def _check_precision_budget(node: dict, sample_size, where: str) -> None:
    """A budget that is there, held to the interval on the same block.

    Every input is already beside it, so the question can be put wherever
    a budget is found and does not need to know who wrote it.
    """
    budget = node["precision_budget"]
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


#: How a stratum row states the two shifts it contributes. A row records
#: either the difference, or the two conditional means it is the difference
#: of, and the two places this table is reached by use one spelling each.
#: They are not copies — they never share an envelope — so neither can be
#: dropped in favour of the other without changing a contract.
#:
#: Restated from what the contract says these fields ARE ("E[Y|Z=1,w] -
#: E[Y|Z=0,w]"), for the reason in this module's header.
_SHIFT_SPELLINGS = (
    (("outcome_shift",), ("treatment_shift",)),
    (("p_y_given_z_treated", "p_y_given_z_control"),
     ("p_x_given_z_treated", "p_x_given_z_control")),
)

#: These figures are not rounded on the way to a reader — they arrive at
#: the precision they were computed at — so the only slack an identity on
#: them needs is the order the additions happened in. Wider than that and
#: it starts accepting the aggregate of something else.
_AGGREGATE_TOL = 1e-9


def _shift(row: dict, names: tuple[str, ...]):
    """One stratum's contribution, under whichever spelling the row uses."""
    got = [_num(row.get(name)) for name in names]
    if any(value is None for value in got):
        return None
    return got[0] if len(got) == 1 else got[0] - got[1]


def _stratified_aggregate(strata: list):
    """``(Σ w·Δy, Σ w·Δx)`` — the two halves of a ratio of averages.

    ``None`` when the rows do not state what an aggregate would be over,
    which is most stratum tables: a measurement-error correction carries a
    weight per stratum and no shift, and nothing beside it is an aggregate
    of anything.
    """
    outcome, treatment = [], []
    for row in strata:
        if not isinstance(row, dict):
            return None
        weight = _num(row.get("weight"))
        if weight is None:
            return None
        for outcome_names, treatment_names in _SHIFT_SPELLINGS:
            d_y = _shift(row, outcome_names)
            d_x = _shift(row, treatment_names)
            if d_y is not None and d_x is not None:
                outcome.append(weight * d_y)
                treatment.append(weight * d_x)
                break
        else:
            return None
    return math.fsum(outcome), math.fsum(treatment)


def _check_stratified_aggregate(node: dict, where: str) -> None:
    """An aggregate stated beside the rows it is an aggregate of.

    The contract writes this arithmetic out at the fields themselves —
    "Sum over strata of P(w) times the instrument's shift in the outcome",
    "``late`` aggregates as a RATIO OF AVERAGES — outcome_shift /
    treatment_shift" — and says the breakdown is carried "so downstream
    consumers can sanity-check every component". One of the two places
    this table is reached by executes that, against the derivation record
    the route keeps. The other route keeps no such record, so its block IS
    the record, and every component of it reached a reader free: measured,
    a stratum's probability moved, a figure moved, a row repeated and a row
    deleted, each accepted by all twelve doors that read the envelope.

    The wrong answer this separates from is the average of the per-stratum
    ratios, which weights each stratum by P(w) instead of by its complier
    share. The two coincide whenever the first stage is equally strong in
    every stratum — on the one shape that carries this, 0.65 against
    0.625 — so nothing short of re-aggregating tells them apart.

    On the home that does keep a record the figures here are held already,
    through that rule and the one that ties the display to it. This asks
    from the block alone and so needs no record, which is a different
    premise rather than a second copy; what decides it is that it closes
    leaves nothing else closes, and four of them are on the other home.
    """
    strata = node.get("strata")
    if not isinstance(strata, list) or not strata:
        return
    parts = _stratified_aggregate(strata)
    if parts is None:
        return
    outcome, treatment = parts
    for name, computed in (
            ("outcome_shift", outcome),
            ("treatment_shift", treatment),
            ("late", outcome / treatment if treatment else None)):
        shown = _num(node.get(name))
        if shown is None:
            continue
        if computed is None or abs(shown - computed) > _AGGREGATE_TOL:
            _refuse(f"{where}.{name}", shown, computed)


#: The subtree whose producer promises a budget wherever one can be
#: computed, and therefore the only subtree where an absent budget says
#: anything. Outside it an interval may simply never have been priced:
#: a derivation step records what an estimator was handed, and a bounds
#: row states a range that no sample narrows.
#:
#: Restated here rather than imported, for the reason in this module's
#: header — the producer holds the same subtree, and a test pins the two
#: equal, which is the only honest way to have one fact in two modules
#: that must not see each other. Widening this without the producer
#: widening with it is measurable: the question arrives at intervals
#: nobody promised to price, and twenty honest answers are refused.
_BUDGET_IS_PROMISED: tuple[str, ...] = ("numeric_estimate",)


def _blocks(node, path=()):
    """Every mapping on the envelope, with the path that reached it.

    By shape and not at a list of places: a block added under a new name
    arrives here on its own, wherever on the envelope it is put.
    """
    if isinstance(node, dict):
        yield path, node
        for key, value in node.items():
            yield from _blocks(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _blocks(value, path + (f"[{index}]",))


def verify_envelope_arithmetic(result: dict) -> None:
    """Hold every figure the envelope computed from its own figures.

    Returns ``None`` on accept; raises ``VerificationError`` naming the
    figure, what it says and what the numbers beside it give.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    sample_size = (_num(estimate.get("sample_size"))
                   if isinstance(estimate, dict) else None)
    for path, node in _blocks(result):
        if isinstance(node.get("precision_budget"), dict):
            _check_precision_budget(
                node, sample_size, ".".join(path) or "the answer")
        elif path and path[0] in _BUDGET_IS_PROMISED:
            _no_budget_here(node, sample_size, ".".join(path))
        _check_stratified_aggregate(node, ".".join(path) or "the answer")
