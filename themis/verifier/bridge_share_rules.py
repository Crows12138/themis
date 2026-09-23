"""The warning about a fitted bridge, against the arms it was counted on.

A proximal run solves a second bridge for the treatment, and that bridge is
a reciprocal probability: fitted, it can come out negative, and where it
does the inverse-probability reading of the answer stops being an average
of anything. The estimator counts the rows this happened on, arm by arm,
writes the share onto the arm beside its cross-moments, and — where the
worst of them crosses a line — files a warning that PRINTS that share back
to the reader.

**Nobody read either end.** The share is the one figure in that record
which no second implementation can re-derive: it is a count of rows, and an
envelope of moments does not carry rows. That is a true reason not to
recompute it, and it was taken for a reason not to read it at all — so the
number a reader is shown that a quarter of the control arm went negative,
and the number on the arm it was printed from, had one author between them
and no reader. A run could count a quarter and warn about four percent, or
count a quarter and not warn, and every door agreed.

What closes it is not a recount. It is that the two are one number written
twice, in two places a reader goes for different reasons — the warning,
which is where somebody who reads the report learns of it, and the arm,
which is where somebody who audits the moments does. The line is here as
well, restated, and held in both directions: a warning with every arm
inside the line is a warning about nothing, and arms outside it with no
warning is the dangerous silence, because a clean run looks exactly like a
run nobody disclosed.

WHAT THIS DOES NOT ASK. That a share be recomputable — it is not, and the
arithmetic a record CAN be held to (a count of rows, over the rows it was
counted on, comes back whole) is asked beside the moments where the rest of
that record's identities are. Nor does it ask anything of an answer whose
arms all sit at zero: a bridge that never went negative and a producer who
says so record the same thing, which is the one value this pair cannot
catch and is named in the declared remainder.

**Independence pin:** this module MUST NOT import from ``themis.estimation``
or ``themis.output``. The line below is restated from the contract, not
imported: a verifier that read the producer's own constant would agree with
it by construction, and moving a line is meant to be something somebody
declares rather than something that happens.
``test_a_warning_about_a_bridge_says_what_it_counted.py`` pins the two
equal.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence

from .errors import VerificationError

_RULE = "bridge_negative_share_check"

#: Where the estimator stops calling a negative share a rounding artefact
#: and tells the reader. RESTATED, not imported — see the pin above.
_LINE = 0.005

#: The warning, and the two statements it speaks. A curve names the level
#: it was worst at; a contrast names both of its arms. Which one is on the
#: page decides which arms the sentence is about, so the correspondence is
#: declared rather than guessed at from the slots that happen to be filled.
_KIND = "treatment_bridge_leaves_its_range"
_AT_A_LEVEL = "the_fitted_treatment_bridge_went_negative_at_a_level"
_BETWEEN_ARMS = "the_fitted_treatment_bridge_went_negative"

#: The two arms a contrast records, under their own names.
_ARMS = ("treated", "control")


def _refuse(what: str, detail: str) -> None:
    raise VerificationError(
        f"{what}: {detail}; the share on the arm and the share in the "
        f"warning are one count of rows written twice, in the two places a "
        f"reader goes for it",
        rule=_RULE,
    )


def _num(value):
    return value if isinstance(value, (int, float)) and not isinstance(
        value, bool) else None


def _a_share(value) -> str:
    """This number, written the way the warning writes it."""
    return f"{float(value):.1%}"


def _the_channels(result: Mapping) -> tuple:
    """Every measurement channel this answer's chain carries.

    Read through the serializer rather than out of the wire form by hand,
    so this pass and the one that wrote the record agree about the format
    by construction. A payload that will not decode is the derivation
    rule's finding and not this one's.
    """
    from .serialization import derivation_from_dict

    payload = result.get("derivation")
    if not isinstance(payload, dict):
        return ()
    try:
        steps = derivation_from_dict(payload)
    except Exception:  # noqa: BLE001 — see the docstring
        return ()
    return tuple(step.inputs["measurement_channel"] for step in steps
                 if isinstance(step.inputs.get("measurement_channel"), dict))


def _the_tables(result: Mapping) -> tuple:
    """Each treatment bridge on this answer, as its arms' shares.

    Keyed by whichever name the arm was filed under, and carrying whether
    the roster was keyed by level, because that is what says which of the
    two statements this bridge would speak.
    """
    tables = []
    for channel in _the_channels(result):
        bridge = channel.get("treatment_bridge")
        if not isinstance(bridge, dict):
            continue
        levels = bridge.get("arms")
        if isinstance(levels, Mapping):
            keyed, blocks = True, levels
        else:
            keyed, blocks = False, {name: bridge.get(name) for name in _ARMS}
        shares = {}
        for name, block in blocks.items():
            if not isinstance(block, Mapping):
                continue
            share = _num(block.get("q_negative_fraction"))
            if share is not None:
                shares[str(name)] = share
        if shares:
            tables.append((keyed, shares))
    return tuple(tables)


def _the_warnings(result: Mapping) -> tuple:
    report = result.get("data_gap_report")
    gaps = report.get("gaps") if isinstance(report, Mapping) else None
    if not isinstance(gaps, Sequence) or isinstance(gaps, (str, bytes)):
        return ()
    return tuple(g for g in gaps
                 if isinstance(g, Mapping) and g.get("kind") == _KIND)


def _the_one_bridge(tables: tuple, keyed: bool, statement: str) -> dict:
    """The roster the statement on the page is about.

    By the shape it speaks in rather than by position. An answer showing
    one warning about the treatment bridge has one treatment bridge for it
    to be about, so more than one roster of that shape is refused and not
    guessed between: attributing the sentence to the first would hold it to
    a bridge it may not be a printing of.
    """
    mine = [shares for shape, shares in tables if shape == keyed]
    if len(mine) != 1:
        _refuse(f"data_gap_report {_KIND} {statement}",
                f"the report carries this warning and the chain records "
                f"{len(mine)} treatment bridges written that way")
    return mine[0]


def _at_a_level_says(said: Mapping, tables: tuple) -> None:
    """The curve's warning: the level it was worst at, and by how much."""
    shares = _the_one_bridge(tables, True, _AT_A_LEVEL)
    worst = max(shares.values())
    where = f"data_gap_report {_KIND} {_AT_A_LEVEL}"
    named = said.get("level")
    if named is not None:
        mine = shares.get(str(named))
        if mine is None:
            _refuse(f"{where}.level",
                    f"the warning is about level {named!r} and the bridge "
                    f"records {sorted(shares)}")
        elif mine < worst:
            _refuse(f"{where}.level",
                    f"the warning names level {named!r}, where {mine!r} of "
                    f"the rows went negative, and this bridge went negative "
                    f"on {worst!r} of another level's")
        elif "share" in said and str(said["share"]) != _a_share(mine):
            _refuse(f"{where}.share",
                    f"the report tells a reader {said['share']!r} and level "
                    f"{named!r} counted {mine!r}, which is written "
                    f"{_a_share(mine)!r}")
    elif "share" in said and str(said["share"]) != _a_share(worst):
        _refuse(f"{where}.share",
                f"the report tells a reader {said['share']!r} and the worst "
                f"level of this bridge counted {worst!r}, which is written "
                f"{_a_share(worst)!r}")
    if "levels" in said and str(said["levels"]) != str(len(shares)):
        _refuse(f"{where}.levels",
                f"the report tells a reader the curve has {said['levels']!r} "
                f"levels and this bridge was solved on {len(shares)}")


def _between_arms_says(said: Mapping, tables: tuple) -> None:
    """The contrast's warning: what each of the two arms counted."""
    shares = _the_one_bridge(tables, False, _BETWEEN_ARMS)
    where = f"data_gap_report {_KIND} {_BETWEEN_ARMS}"
    for arm in _ARMS:
        if arm not in said:
            continue
        mine = shares.get(arm)
        if mine is None:
            _refuse(f"{where}.{arm}",
                    f"the warning speaks for the {arm} arm and this bridge "
                    f"records {sorted(shares)}")
        elif str(said[arm]) != _a_share(mine):
            _refuse(f"{where}.{arm}",
                    f"the report tells a reader {said[arm]!r} and the {arm} "
                    f"arm counted {mine!r}, which is written "
                    f"{_a_share(mine)!r}")


_SAYS = {_AT_A_LEVEL: _at_a_level_says, _BETWEEN_ARMS: _between_arms_says}


def verify_a_bridge_warning_says_the_share_it_counted(result: object) -> None:
    """The negative share a reader is shown, against the arm it was on.

    Returns ``None`` on accept. Raises ``VerificationError`` when a bridge
    sent more of a sample negative than the line this system draws and the
    report says nothing, when the report carries that warning and every arm
    of every bridge sits inside the line, when the level a warning names is
    not the level that was worst, or when a share printed for a reader is
    not the share the arm it speaks for counted.

    A slot a statement does not carry is not a disagreement — the writer
    fills what it has, and a sentence that says less than it could is not
    one that says something false. What it does say has to be this
    bridge's.
    """
    if not isinstance(result, Mapping):
        return
    tables = _the_tables(result)
    if not tables:
        return
    warnings = _the_warnings(result)
    over = [shares for _keyed, shares in tables
            if max(shares.values()) > _LINE]
    if over and not warnings:
        worst = max(max(shares.values()) for shares in over)
        _refuse("data_gap_report",
                f"the fitted treatment bridge went negative on {worst!r} of "
                f"an arm, where the line for telling a reader is {_LINE!r}, "
                f"and the report carries no {_KIND!r}")
    if warnings and not over:
        inside = max(max(shares.values()) for _keyed, shares in tables)
        _refuse("data_gap_report",
                f"the report warns of {_KIND!r} and the most any arm of this "
                f"answer's bridges sent negative is {inside!r}, within the "
                f"{_LINE!r} that would occasion it")
    for gap in warnings:
        for described in gap.get("describes") or ():
            if not isinstance(described, Mapping):
                continue
            sentence = described.get("sentence")
            said = described.get("said")
            says = _SAYS.get(sentence) if isinstance(sentence, str) else None
            if says is not None and isinstance(said, Mapping):
                says(said, tables)
