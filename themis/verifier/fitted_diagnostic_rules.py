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

**A verdict is three things, and that closed the first.** A diagnostic
verdict is a number measured off a fit, a LINE this system drew, and the
conclusion the two make. The arithmetic above is the number. The line was on
the block once and nowhere else, so a band could be widened and a threshold
moved and every reader of it — the ledger, the gap's own sentence — re-read
the moved line and agreed. And the conclusion was on the report once and
nowhere else: measured end to end, an answer saying 1453 of 4000 units fell
outside the overlap band passed the public door with the warning that says
so deleted from the report entirely.

One of the four verdicts this layer makes did have a second record — the
ledger re-reads its positivity conclusion off ``fitted_overlap``, so that
one refuses. Which is the shape of the defect: whether a conclusion can be
read back from its evidence was being decided one conclusion at a time. So
the line is a vocabulary here, restated and pinned by a test, and a block
that judges against a line nobody registered is refused rather than skipped;
and every registered diagnostic's warning is required to be exactly what its
share and its line say it is, in both directions.

**Two kinds of line, and which kind it is decides how it can be held.** A
line this system draws has no second record anywhere, so the only honest
copy is the constant, restated. A line the CALLER may draw — where to clip
the propensity — must NOT be held to a constant, or a run that asked for a
different clip is refused for being what it was asked to be. That one is
held instead to the ledger, which already carries the same floor and the
same count as a premise a reader is asked to accept, and which had never
been compared with the block beside it.

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

#: Every diagnostic that judges against a line: the line it draws, and the
#: warning that comes out of crossing it.
#:
#: RESTATED, not imported. A verifier that read the producer's constant would
#: agree with it by construction and hold nothing; two copies and one test
#: pinning them equal is what makes moving a line something somebody declares
#: rather than something that happens. The independence pin below is the same
#: argument said generally.
_DIAGNOSTICS: dict[str, tuple[dict[str, float], str | None]] = {
    "fitted_overlap": ({"band_lower": 0.05, "band_upper": 0.95,
                        "threshold": 0.05},
                       "propensity_overlap_violation"),
    "outcome_saturation": ({"band_lower": 0.01, "band_upper": 0.99,
                            "threshold": 0.10},
                           "outcome_model_quasi_separation"),
}

#: The clip's floor is NOT here, and the difference is who draws the line.
#: These two are the system's own — no caller can move them, so the only
#: honest copy is the constant. The propensity floor is the caller's to name,
#: and the estimator records whether they named it; held to a constant it
#: would refuse an honest run that asked for a different clip. It has a
#: second record of its own, and ``_the_clip_is_disclosed_once`` is where
#: that is spent.
_CLIP = "propensity_clipped_to_floor_"

#: The words a block uses for a line THIS SYSTEM draws. A block carrying one
#: of these and registered nowhere above is REFUSED rather than skipped: an
#: unregistered line is a line nobody checked, and at a door that reads
#: exactly like a line nobody needed to check.
#:
#: ``floor`` is deliberately not one of them. A floor is where somebody
#: chose to clip, and the caller is allowed to be that somebody — so the
#: word does not promise a constant, and a rule that read it as one would
#: refuse a run for having been asked what it was asked.
_LINE_NAMES = frozenset({"band_lower", "band_upper", "threshold"})

#: The two blocks one estimator-side writer produces. Same arithmetic on a
#: different fitted model; the band is what tells them apart — which is also
#: what tells them apart from the clip summary, so this is read off the
#: registry rather than kept beside it.
_FITTED = tuple(name for name, (lines, _) in _DIAGNOSTICS.items()
                if "band_lower" in lines)


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


def _the_lines(node, where: str, name: str) -> None:
    """Where the line a verdict is measured against came from.

    Asked of every object the envelope holds, at any depth, because which
    of them judge against a line is a fact about the envelope's shape and
    not a list kept here. ``name`` is the key the object arrived under, and
    it is what the registry is looked up by; a series passes its own name
    down, since the fifth row of a table judges against the table's line.

    An object carrying a line and registered nowhere is REFUSED. The
    alternative is passing it, and a line nobody registered is a line nobody
    checked — which at a door is the same silence as a line that needed no
    checking.
    """
    if isinstance(node, list):
        for item in node:
            _the_lines(item, where, name)
        return
    if not isinstance(node, dict):
        return

    shown = sorted(k for k in node if k in _LINE_NAMES)
    if shown:
        entry = _DIAGNOSTICS.get(name)
        if entry is None:
            _refuse(where,
                    f"judges against {shown} and no line is registered for "
                    f"it, so whatever it decided was decided against a "
                    f"number of its own choosing")
            return
        lines = entry[0]
        for field in shown:
            want, got = lines.get(field), _num(node.get(field))
            if want is None:
                _refuse(f"{where}.{field}",
                        f"a line this system does not draw for {name!r}")
                return
            if got is None or abs(got - want) > _TOL:
                _refuse(f"{where}.{field}",
                        f"shown as {node.get(field)!r} where the line this "
                        f"system draws is {want!r}")

    for key, value in node.items():
        _the_lines(value, f"{where}.{key}", key)


def _the_clip_is_disclosed_once(estimate: dict) -> None:
    """The clip a reader reads, and the clip the ledger asks them to accept.

    Winsorizing is not something the run found; it is something it DID, and
    a reader is told about it in two places: the summary block, and a
    premise on the assumption ledger naming the floor and the count. Two
    disclosures of one act, and nothing held them together — a block could
    report a floor of 0.01 beside a premise about 0.2, and each reader would
    believe whichever they read.

    Held by READING the premise rather than by rebuilding it. The id's
    format belongs to whoever writes it; what this rule is about is the two
    numbers inside, and rebuilding the string here would make a formatting
    change look like a disagreement about the clip.

    Both directions. A clip with no premise is the dangerous one: the
    estimate then rests on a Winsorizing step a reader can only find by
    reading a diagnostic block, and the ledger — which is where a reader
    goes to see what they are being asked to believe — says nothing.
    """
    block = estimate.get("propensity_summary")
    if not isinstance(block, dict):
        return
    trimmed, floor = _count(block.get("n_trimmed")), _num(block.get("floor"))
    if trimmed is None or floor is None:
        return
    declared = [a for a in (estimate.get("assumptions") or ())
                if isinstance(a, str) and a.startswith(_CLIP)]
    where = "numeric_estimate.propensity_summary"
    if not trimmed:
        if declared:
            _refuse(f"{where}.n_trimmed",
                    f"no unit was clipped and the ledger asks a reader to "
                    f"accept {declared!r}")
        return
    if not declared:
        _refuse(f"{where}.n_trimmed",
                f"{trimmed!r} units were Winsorized and no premise on the "
                f"ledger says so; a reader is asked to accept a step they "
                f"can only find by reading a diagnostic")
        return
    said, _sep, count = declared[0][len(_CLIP):].partition("_on_")
    try:
        at, units = float(said), int(count)
    except ValueError:
        _refuse(f"{where}.floor",
                f"the ledger's clip premise reads {declared[0]!r}, which "
                f"names no floor and no count")
        return
    if abs(at - floor) > _TOL:
        _refuse(f"{where}.floor",
                f"clipped at {floor!r} and the ledger's premise is about a "
                f"clip at {at!r}")
    if units != trimmed:
        _refuse(f"{where}.n_trimmed",
                f"{trimmed!r} units clipped and the ledger's premise is "
                f"about {units!r}")


def _warned(result: dict) -> set:
    report = result.get("data_gap_report")
    gaps = report.get("gaps") if isinstance(report, dict) else None
    return {g.get("kind") for g in (gaps or ()) if isinstance(g, dict)}


def _the_verdicts(estimate: dict, warned: set) -> None:
    """The warning that comes out of a diagnostic, held to the diagnostic.

    Both directions, and the silent one is the dangerous one: a warning that
    is simply absent is what a clean run looks like, so the whole of the
    disclosure is that somebody remembered to make it.

    That the block being present decides who raised the warning is the one
    subtlety here. The overlap condition has two witnesses — a count of
    one-armed strata where the adjustment set has cells to count, and the
    fitted propensity where it does not — and they file the same kind. They
    cannot both speak: the counting witness raises and stops, before any
    model is fitted, so the fitted block on the envelope is itself the
    statement that the other witness had nothing to say.
    """
    for name, (_lines, warns) in _DIAGNOSTICS.items():
        if warns is None:
            continue
        block = estimate.get(name)
        if not isinstance(block, dict):
            continue
        share, line = _num(block.get("share_outside")), \
            _num(block.get("threshold"))
        if share is None or line is None:
            continue
        over = share > line
        if over and warns not in warned:
            _refuse(f"numeric_estimate.{name}.share_outside",
                    f"{share!r} of the sample is outside the band and the "
                    f"line for saying so is {line!r}, and the report carries "
                    f"no {warns!r}; a reader is shown a clean run")
        if warns in warned and not over:
            _refuse(f"numeric_estimate.{name}.share_outside",
                    f"the report warns of {warns!r} and this diagnostic puts "
                    f"{share!r} of the sample outside the band, within the "
                    f"{line!r} that would occasion it")


def _stratum_support(estimate: dict, warned: set) -> None:
    """The count the positivity premise is actually about.

    The kind's own definition is a count — every stratum the formula sums
    over holds both arms — and where the strata can be enumerated this is
    the direct witness rather than the fitted proxy. Three numbers that are
    one fact said three ways: how many cells, how many held both arms, and
    what share of the sample sat in the ones that did not. A cell that holds
    one arm holds at least one unit, so the share is positive exactly when
    some cell is short, and a run where some cell is short is a run this
    condition was violated in.
    """
    block = estimate.get("stratum_support")
    if not isinstance(block, dict):
        return
    where = "numeric_estimate.stratum_support"
    cells, supported = _count(block.get("cells")), \
        _count(block.get("supported"))
    share = _num(block.get("extrapolated_share"))
    if None in (cells, supported, share):
        return
    if cells < 1:
        _refuse(f"{where}.cells", f"{cells!r} strata to sum over")
    if not 0 <= supported <= cells:
        _refuse(f"{where}.supported",
                f"{supported!r} of {cells!r} strata holding both arms")
    if not 0.0 <= share <= 1.0:
        _refuse(f"{where}.extrapolated_share",
                f"{share!r} of the sample sitting in the short strata")
    thin = supported < cells
    if thin != (share > _TOL):
        _refuse(f"{where}.extrapolated_share",
                f"{supported!r} of {cells!r} strata hold both arms and "
                f"{share!r} of the sample sits in the ones that do not; a "
                f"stratum with a single arm holds at least one unit")
    if thin and "propensity_overlap_violation" not in warned:
        _refuse(f"{where}.supported",
                f"{cells - supported} of {cells!r} strata the formula sums "
                f"over hold a single arm and the report says nothing; that "
                f"part of the answer is the outcome model's, not the data's")


def verify_fitted_diagnostics(result: dict) -> None:
    """Re-derive what the fitted diagnostics claim, from what they record.

    Returns ``None`` on accept. Raises ``VerificationError`` when a share
    disagrees with the counts it is a share of, when a range and its count
    disagree about whether anything fell outside the band, when a clip count
    and the range it was clipped from disagree, when a diagnostic describes
    units the estimate was not computed on, when a block judges against a
    line other than the one this system draws, or when what a diagnostic
    found and what the report warns of are two different runs.
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
    _the_lines(estimate, "numeric_estimate", "numeric_estimate")
    _the_clip_is_disclosed_once(estimate)
    warned = _warned(result)
    _the_verdicts(estimate, warned)
    _stratum_support(estimate, warned)
