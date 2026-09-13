"""A formula the contract spells out, executed at one of its two addresses.

``extensions.iv_identification.numeric`` carries a stratified Wald table and
the three figures it aggregates to. The contract writes the arithmetic out
at the fields themselves — "Sum over strata of P(w) times the instrument's
shift in the outcome", "``late`` aggregates as a RATIO OF AVERAGES —
outcome_shift / treatment_shift" — and says the breakdown is carried there
"so downstream consumers can sanity-check every component".

Nothing checked any component. Move a stratum's probability, move one of
the three figures, repeat a row, delete a row: each was accepted by all
twelve doors that read that envelope. The block could state 0.9 while the
answer above it said 0.625.

The same table has a second address. Under ``numeric_estimate
.stratified_wald`` the route keeps a derivation record of the stratum
columns, ``_check_stratified_wald`` pins the aggregates to those columns and
the point to their ratio, and the display-copy rule ties the block to the
aggregates. Every figure held. So this was never a gap in what anybody
knew — the formula was executed where a record existed, and the check was
attached to that address rather than to the claim.

The route behind the other address keeps no such record: its four
conditional probabilities are the caller's own theta, and the block IS the
record. An identity closed on the block needs no record, which is why it
reaches both addresses — and what decides it is not the overlap but that it
closes four leaves nothing closes.

WHAT THIS DOES NOT CHECK: that the block's ``late`` is the same number as
the answer the envelope reports. Measured and left open deliberately: with
``late`` at 0.9 and ``numeric_result.value`` at 0.625 nothing refused, and
one shape is not enough to say whether an IV-identified query always
reports the LATE as its answer. Closing the identity narrows it — a lone
``late`` no longer moves — and what remains is a block bent consistently
throughout, which is its own question and not this one.

Nor does it check that the weights sum to one. The contract says they do
("a shortfall would mean the average runs over a narrower population than
the query asked about") and one address already executes that, but it is a
constraint on one field rather than an identity between figures, so it does
not belong to this module.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier import verify_envelope_arithmetic
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

FIGURES = ("outcome_shift", "treatment_shift", "late")


def _tables(node, path=()):
    """Every block carrying a stratum table, with the path that reached it."""
    if isinstance(node, dict):
        rows = node.get("strata")
        if isinstance(rows, list) and rows and all(
                isinstance(row, dict) for row in rows):
            yield path, node
        for key, value in node.items():
            yield from _tables(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _tables(value, path + (f"[{index}]",))


def _aggregates(node) -> bool:
    """Whether a block's rows say what an aggregate would be over."""
    return any(row.get("weight") is not None
               and ("outcome_shift" in row or "p_y_given_z_treated" in row)
               for row in node["strata"])


#: ``(shape, path)`` for every stratum table that states an aggregate, and
#: for every one that does not. Read off the snapshot rather than listed:
#: the second group is the side this rule must stay quiet about, and a
#: table added under a new name belongs to whichever group it belongs to.
CARRIES, DECLINES = [], []
for _name, _pair in sorted(SHAPES.items()):
    for _path, _node in _tables(_pair["result"]):
        (CARRIES if _aggregates(_node) else DECLINES).append(
            (_name, ".".join(_path)))

def _at(result, where: str):
    node = result
    for step in where.split("."):
        node = node[int(step[1:-1])] if step.startswith("[") else node[step]
    return node


# ------------------------------------------------------------ the two groups


def test_there_are_stratum_tables_of_both_kinds():
    """The denominator. Every row below is about one group or the other, so
    a corpus holding only one would make half of them pass by having
    nothing to ask."""
    assert CARRIES, "no stratum table states an aggregate"
    assert DECLINES, "no stratum table states something else"


def test_the_identity_is_carried_at_more_than_one_address():
    """What makes this a rule about a shape rather than about a field. One
    address keeps a derivation record and one does not; a rule reaching
    only the one with a record is how the other came to be free."""
    assert len({where for _name, where in CARRIES}) >= 2, sorted(
        {where for _name, where in CARRIES})


# --------------------------------------------------- what the aggregate owes


@pytest.mark.parametrize("shape,where", CARRIES, ids=lambda v: str(v))
@pytest.mark.parametrize("figure", FIGURES)
def test_a_figure_that_the_rows_do_not_give_is_refused(shape, where, figure):
    result = copy.deepcopy(SHAPES[shape]["result"])
    block = _at(result, where)
    if not isinstance(block.get(figure), (int, float)):
        pytest.skip(f"{where} states no {figure}")
    block[figure] += 0.17
    with pytest.raises(VerificationError, match="producer's word twice"):
        verify_envelope_arithmetic(result)


@pytest.mark.parametrize("shape,where", CARRIES, ids=lambda v: str(v))
@pytest.mark.parametrize("how", ["move a number", "repeat a row",
                                 "delete a row", "move a weight"])
def test_a_table_that_no_longer_gives_the_figure_is_refused(shape, where, how):
    """Four ways to leave the figures untouched and make them wrong. The
    first two are outside the census's own alphabet, which is why this is
    asked here."""
    result = copy.deepcopy(SHAPES[shape]["result"])
    rows = _at(result, where)["strata"]
    if how == "repeat a row":
        rows.append(copy.deepcopy(rows[-1]))
    elif how == "delete a row":
        if len(rows) < 2:
            pytest.skip("one row — deleting it leaves no table")
        rows.pop()
    elif how == "move a weight":
        rows[0]["weight"] = rows[0]["weight"] / 2
    else:
        moved = next(key for key in ("outcome_shift", "p_y_given_z_treated")
                     if key in rows[0])
        rows[0][moved] += 0.13
    with pytest.raises(VerificationError, match="producer's word twice"):
        verify_envelope_arithmetic(result)


@pytest.mark.parametrize("shape,where", CARRIES, ids=lambda v: str(v))
def test_the_average_of_the_ratios_is_refused_as_a_different_estimand(
        shape, where):
    """The wrong answer this exists to separate from: each stratum weighted
    by P(w) instead of by its complier share. The two coincide whenever the
    first stage is equally strong everywhere, so a rule that recomputed
    nothing would wave it through."""
    result = copy.deepcopy(SHAPES[shape]["result"])
    block = _at(result, where)
    if not isinstance(block.get("late"), (int, float)):
        pytest.skip(f"{where} states no late of its own")
    rows = block["strata"]

    def shift(row, one, two=None):
        return row[one] if two is None else row[one] - row[two]

    spelt = "outcome_shift" in rows[0]
    block["late"] = sum(
        row["weight"] * (
            (shift(row, "outcome_shift") if spelt
             else shift(row, "p_y_given_z_treated", "p_y_given_z_control"))
            / (shift(row, "treatment_shift") if spelt
               else shift(row, "p_x_given_z_treated", "p_x_given_z_control")))
        for row in rows)
    with pytest.raises(VerificationError, match="producer's word twice"):
        verify_envelope_arithmetic(result)


@pytest.mark.parametrize("shape,where", CARRIES + DECLINES,
                         ids=lambda v: str(v))
def test_the_answer_each_forgery_was_made_from_is_honest(shape, where):
    """The other side of every row above, and the only side the second
    group has: a table the rule declines must also be a table nothing here
    refuses."""
    pair = SHAPES[shape]
    verify_envelope_arithmetic(pair["result"])
    the_door_for(pair["result"])(pair["program"], pair["result"])


# ------------------------------------- and what it declines to have a view on


@pytest.mark.parametrize("shape,where", DECLINES, ids=lambda v: str(v))
def test_a_table_that_is_not_an_aggregate_is_not_asked_to_be_one(shape, where):
    """A stratum of a measurement-error correction carries counts, and a
    failure's details carry a channel. Neither states an aggregate and
    nothing beside them is one, so bending a row here is somebody else's
    question — this rule has no view, and a rule with a view would be
    refusing honest answers for a claim they never made."""
    result = copy.deepcopy(SHAPES[shape]["result"])
    rows = _at(result, where)["strata"]
    rows.append(copy.deepcopy(rows[-1]))
    for row in rows:
        for key, value in row.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                row[key] = value + 1
    verify_envelope_arithmetic(result)


# -------------------------------------------------- and both ways of saying it


@pytest.mark.parametrize("rows,label", [
    ([{"weight": 0.4, "outcome_shift": 0.3, "treatment_shift": 0.6},
      {"weight": 0.6, "outcome_shift": 0.3, "treatment_shift": 0.4}],
     "the row records the difference"),
    ([{"weight": 0.4, "p_y_given_z_treated": 0.7, "p_y_given_z_control": 0.4,
       "p_x_given_z_treated": 0.9, "p_x_given_z_control": 0.3},
      {"weight": 0.6, "p_y_given_z_treated": 0.5, "p_y_given_z_control": 0.2,
       "p_x_given_z_treated": 0.6, "p_x_given_z_control": 0.2}],
     "the row records the two means"),
])
def test_either_spelling_of_a_shift_is_read(rows, label):
    """The two addresses do not share a vocabulary — one records the
    difference, the other the conditional means it is the difference of —
    and they never share an envelope, so neither can be dropped. A spelling
    this stops reading goes quiet rather than loud, which is why both are
    asked here in a block of their own."""
    honest = {"strata": rows, "outcome_shift": 0.3, "treatment_shift": 0.48,
              "late": 0.625}
    verify_envelope_arithmetic({"a_block_nobody_has_written_yet": honest})
    for figure in FIGURES:
        bent = copy.deepcopy(honest)
        bent[figure] += 0.2
        with pytest.raises(VerificationError, match="producer's word twice"):
            verify_envelope_arithmetic({"a_block_nobody_has_written_yet": bent})
