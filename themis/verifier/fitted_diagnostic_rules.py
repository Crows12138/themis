"""The diagnostics a reader consults to decide whether to trust the number.

Two of the checks a back-door-family run makes answer by FITTING a model and
reading where its probabilities land: ``fitted_overlap`` on P(X|Z) and
``outcome_saturation`` on P(Y|X,Z). A weighted estimator adds
``propensity_summary`` — the range before Winsorizing and how many units were
clipped. These are not digits of the answer. They are the evidence a reader
weighs the answer with, and the assumption ledger reads its positivity
verdict off the first of them.

**They arrived as summaries with nothing to divide out.** The counts —
how many units fell outside the band, out of how many — were computed at the
estimator, spoken to the reader inside the gap's own sentence, and then
dropped before the envelope was written. What reached the door was a
quotient. So the ledger, which deliberately re-reads the estimate's own
numbers rather than restating a threshold, so that its verdict is a
disclosure and not a claim, was re-reading a figure that was itself nothing
but a claim. Independence that stops one level short of the ground is
decoration.

What closes it is not a second fit — the verifier has no data and could not
run one. It is the arithmetic every fitted range obeys whatever model
produced it: a share is a count over a count; a range that lies inside the
band is a count of zero outside it, and a range that reaches outside is not;
a diagnostic is about the units the estimate is about. The counts are now
recorded, and this divides them for itself.

WHAT THIS DOES NOT ASK. That a run which COULD have fitted one did. Nothing
on the envelope says whether the treatment was binary or the fit converged,
so an absent block is a check not made rather than a check hidden — and a
reader is told nothing rather than told something false. That is the
difference from ``post_stratification``, where the method's own name says
the strata must exist and silence therefore has to be a refusal. Presence
here is the schema's to require, and it does: a block arriving without its
counts is refused at the public door one gate before this one.

**Independence pin:** this module MUST NOT import from
``themis.estimation``. The identities are restated from what a fitted range
means.
"""
from __future__ import annotations

from .errors import VerificationError

_RULE = "fitted_diagnostic_check"

#: A share is one count divided by another, so the only distance allowed
#: between the share shown and the quotient is what writing one float costs.
_TOL = 1e-9

#: The two blocks one estimator-side writer produces. Same arithmetic on a
#: different fitted model; the band is what tells them apart.
_FITTED = ("fitted_overlap", "outcome_saturation")


def _refuse(what: str, detail: str) -> None:
    raise VerificationError(
        f"{what}: {detail}; a diagnostic is what a reader weighs the answer "
        f"with, and a summary of a fit that nothing can divide out is the "
        f"producer's word about its own work",
        rule=_RULE,
    )


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(
        value, bool) else None


def _count(value):
    return value if isinstance(value, int) and not isinstance(
        value, bool) else None


def _fitted_range(where: str, block: dict, sample_size) -> None:
    """One fitted diagnostic, held to what a fitted range means."""
    p_min, p_max = _num(block.get("p_min")), _num(block.get("p_max"))
    low, high = _num(block.get("band_lower")), _num(block.get("band_upper"))
    share = _num(block.get("share_outside"))
    outside, total = _count(block.get("n_outside")), \
        _count(block.get("n_total"))
    if None in (p_min, p_max, low, high, share, outside, total):
        # The schema requires every one of these, so reaching this means the
        # rule was called on a fragment rather than through the door.
        return

    if p_min > p_max:
        _refuse(f"{where}.p_min",
                f"a range that runs backwards: {p_min!r} to {p_max!r}")
    if low >= high:
        _refuse(f"{where}.band_lower",
                f"a band that holds nothing: {low!r} to {high!r}")
    if not 1 <= total:
        _refuse(f"{where}.n_total", "a fit on nobody")
    if not 0 <= outside <= total:
        _refuse(f"{where}.n_outside",
                f"{outside!r} of {total!r} units outside the band")
    if abs(share - outside / total) > _TOL:
        _refuse(f"{where}.share_outside",
                f"shown as {share!r}, and {outside!r} out of {total!r} is "
                f"{outside / total!r}")

    # Which side of the band the range lies on decides the count exactly, in
    # both directions. This is what a forger has to satisfy to show a clean
    # share: the range is printed for the reader too, so the lie has to be
    # told twice and in plain sight.
    reaches_out = (p_min < low) + (p_max > high)
    if not reaches_out and outside:
        _refuse(f"{where}.n_outside",
                f"every fitted value lies within {low!r} to {high!r} and "
                f"{outside!r} of them are counted outside it")
    if outside < reaches_out:
        _refuse(f"{where}.n_outside",
                f"the range {p_min!r} to {p_max!r} reaches outside "
                f"{low!r} to {high!r} and {outside!r} units are counted "
                f"there")

    if sample_size is not None and total != sample_size:
        # A diagnostic is only evidence about the answer if it is about the
        # same units the answer is about.
        _refuse(f"{where}.n_total",
                f"fitted on {total!r} units where the estimate was computed "
                f"on {sample_size!r}")


def _propensity_summary(estimate: dict, sample_size) -> None:
    """What a weighted estimator DID about thin overlap.

    A different fact from what the diagnostic above FOUND, and held to a
    different identity: the clip is defined by the floor, so how many units
    were clipped is decided by whether the raw range crossed it. The one
    thing the two blocks do share is the range itself, and the last check
    below is where that is said.
    """
    block = estimate.get("propensity_summary")
    if not isinstance(block, dict):
        return
    where = "numeric_estimate.propensity_summary"
    raw_min, raw_max = _num(block.get("raw_min")), _num(block.get("raw_max"))
    floor = _num(block.get("floor"))
    trimmed = _count(block.get("n_trimmed"))
    model = block.get("model")
    if None in (raw_min, raw_max, floor, trimmed):
        return

    if raw_min > raw_max:
        _refuse(f"{where}.raw_min",
                f"a range that runs backwards: {raw_min!r} to {raw_max!r}")
    if sample_size is not None and trimmed > sample_size:
        _refuse(f"{where}.n_trimmed",
                f"{trimmed!r} units clipped in a run of {sample_size!r}")

    crossed = (raw_min < floor) + (raw_max > 1.0 - floor)
    if not crossed and trimmed:
        _refuse(f"{where}.n_trimmed",
                f"every propensity lies within {floor!r} to "
                f"{1.0 - floor!r} and {trimmed!r} of them are reported "
                f"clipped to it")
    if trimmed < crossed:
        _refuse(f"{where}.n_trimmed",
                f"the range {raw_min!r} to {raw_max!r} crosses the floor "
                f"{floor!r} and {trimmed!r} units are reported clipped")

    # An empty adjustment set leaves P(X=1|Z) with nothing to depend on, so
    # the propensity is one constant and cannot have a range. The envelope
    # says which set was adjusted for, which is what makes this checkable
    # rather than a second reading of the same field.
    adjustment = estimate.get("adjustment")
    if isinstance(adjustment, list) and (not adjustment) != (
            model == "marginal"):
        _refuse(f"{where}.model",
                f"a {model!r} propensity where the answer adjusts for "
                f"{sorted(adjustment)}")
    if model == "marginal" and raw_min != raw_max:
        _refuse(f"{where}.raw_min",
                f"a propensity that depends on nothing, ranging from "
                f"{raw_min!r} to {raw_max!r}")

    # The same quantity, disclosed twice. What this block calls the raw
    # propensity range and what the overlap diagnostic calls the range of
    # its fitted P(X|Z) are one range of one conditional probability over
    # one adjustment set, and a reader is shown BOTH lines, in the same
    # section, one under the other. Two answers there is a reader misled
    # whichever module is right — so this is an identity between two
    # disclosures, not two implementations held to each other.
    found = estimate.get("fitted_overlap")
    if not isinstance(found, dict):
        return
    for mine, theirs in (("raw_min", "p_min"), ("raw_max", "p_max")):
        ours, other = _num(block.get(mine)), _num(found.get(theirs))
        if other is not None and abs(ours - other) > _TOL:
            _refuse(f"{where}.{mine}",
                    f"{ours!r}, where the overlap diagnostic found the same "
                    f"fitted propensity reaching {other!r}")


def verify_fitted_diagnostics(result: dict) -> None:
    """Re-derive what the fitted diagnostics claim, from what they record.

    Returns ``None`` on accept. Raises ``VerificationError`` when a share
    disagrees with the counts it is a share of, when a range and its count
    disagree about whether anything fell outside the band, when a clip count
    and the range it was clipped from disagree, or when a diagnostic
    describes units the estimate was not computed on.
    """
    if not isinstance(result, dict):
        return
    estimate = result.get("numeric_estimate")
    if not isinstance(estimate, dict):
        return
    sample_size = _count(estimate.get("sample_size"))
    for field in _FITTED:
        block = estimate.get(field)
        if isinstance(block, dict):
            _fitted_range(f"numeric_estimate.{field}", block, sample_size)
    _propensity_summary(estimate, sample_size)
