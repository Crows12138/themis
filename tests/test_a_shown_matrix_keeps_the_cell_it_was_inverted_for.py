"""A shown matrix keeps the cell it was inverted for.

A differential misclassification correction inverts a different confusion
matrix in each cell -- each exposure arm, or each level of a covariate, or
each value of the outcome. Those matrices go onto the envelope twice: into
``measurement_correction.sufficient_statistics``, which is the copy the
verifier re-inverts, and into ``measurement_correction.confusion_matrices``,
which is the copy a reader is shown. Each entry of the second is a matrix
and a coordinate, and the coordinate -- ``arm``, ``level`` or ``outcome``
-- is what says which cell the matrix governs.

A check already held the shown copy to the inverted one, and held the
MATRIX, because a matrix is what the tamper probe that found it had
changed. So the table could be right about every rate and wrong about
which cell each rate belongs to: a reader of a detection-bias correction
is told that the people recorded as cases in the treated arm were
miscounted at the rate that was measured in the untreated one, and every
number on the page still re-derives, because every number re-derives from
the other copy.

That the coordinate is a coordinate and not a number is why an out-of-range
arm was already refused and a swapped one was not. What was unheld is a
LEGAL coordinate on the wrong record, which is the only kind a forger would
write.

Of the three channels that produce these records, two called that check,
and the outcome channel -- whose per-arm table is the one a detection-bias
correction shows -- never did.

What is asserted here:

- the corpus carries a record of every coordinate kind, pinned, because a
  rule whose subject leaves the corpus goes quiet without saying so
- no honest carrier is refused, by its own channel's verifier and again at
  the public door
- a table whose cells are swapped is refused -- every matrix present, every
  coordinate legal, only which-is-which changed
- every channel that writes these records calls the check, asserted at the
  three call sites rather than by three copies of one forgery
- and the limit of the comparison: two spellings of one cell are one cell,
  because the contract coerced the column before any of this ran
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

from themis.verifier import VerificationError
from themis.verifier import verify as _verify
from themis.verifier.verify import _as_contents

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: The three coordinate names, spelled once. Which one a record carries is
#: decided by the channel and the axis, and no record carries two.
COORDINATES = ("arm", "level", "outcome")

#: How many stored answers show a per-cell table, and how many of them use
#: each coordinate. The second is the roster every forgery below draws
#: from, and a roster taken from the corpus is a roster that can empty.
ANSWERS_WITH_A_PER_CELL_TABLE = 4
CARRIERS_BY_COORDINATE = {"arm": 1, "level": 2, "outcome": 1}

#: Which verifier re-derives which method's block. The combined channel
#: writes no per-cell table in the corpus and so appears only where the
#: call sites are counted.
CHANNEL = {
    "measurement_error_correction":
        _verify.verify_measurement_correction_numeric,
    "exposure_measurement_error_correction":
        _verify.verify_exposure_measurement_correction_numeric,
}

#: Every channel that can write one of these tables. Named here because the
#: claim below is about all of them and a list gathered by hand is a list
#: that forgets the one that was added last.
EVERY_CHANNEL = (
    _verify.verify_measurement_correction_numeric,
    _verify.verify_exposure_measurement_correction_numeric,
    _verify.verify_combined_measurement_correction_numeric,
)


def _block(result: dict):
    return (result.get("numeric_estimate") or {}).get("measurement_correction")


def _carriers() -> list[str]:
    out = []
    for name, row in SHAPES.items():
        mc = _block(row["result"])
        if isinstance(mc, dict) and mc.get("confusion_matrices"):
            out.append(name)
    return sorted(out)


def _coordinate_of(name: str) -> str:
    """The one coordinate this carrier's records are keyed by."""
    records = _block(SHAPES[name]["result"])["confusion_matrices"]
    found = {c for record in records for c in COORDINATES if c in record}
    assert len(found) == 1, (name, found)
    return found.pop()


def _audit(name: str, result: dict) -> None:
    """The block's own channel, re-deriving it."""
    estimate = result["numeric_estimate"]
    CHANNEL[estimate["method"]](estimate)


def test_the_corpus_exercises_this_rule():
    carriers = _carriers()
    assert len(carriers) == ANSWERS_WITH_A_PER_CELL_TABLE, carriers
    counted: dict[str, int] = {}
    for name in carriers:
        coordinate = _coordinate_of(name)
        counted[coordinate] = counted.get(coordinate, 0) + 1
    assert counted == CARRIERS_BY_COORDINATE, counted
    assert set(CHANNEL) == {SHAPES[n]["result"]["numeric_estimate"]["method"]
                            for n in carriers}


@pytest.mark.parametrize("name", _carriers())
def test_no_honest_carrier_is_refused(name):
    """The denominator, by the channel and again at the strongest door that
    reads it -- a rule that refuses an honest answer fails here rather than
    in the remainder sweep."""
    row = SHAPES[name]
    _audit(name, row["result"])
    verify_honestly(row["program"], row["result"])


@pytest.mark.parametrize("name", _carriers())
def test_a_table_with_its_cells_swapped_is_refused(name):
    """The forgery this exists for, through the public door.

    Nothing is invented: both matrices were inverted on this run and both
    coordinates are cells of this table. Only the pairing moved, which is
    the whole of what a reader reads the table for.
    """
    honest = SHAPES[name]["result"]
    coordinate = _coordinate_of(name)
    forged = copy.deepcopy(honest)
    records = _block(forged)["confusion_matrices"]
    assert len(records) >= 2, records
    records[0][coordinate], records[1][coordinate] = (
        records[1][coordinate], records[0][coordinate])

    with pytest.raises(VerificationError, match="the record the inversion"):
        _audit(name, forged)
    with pytest.raises(VerificationError, match="the record the inversion"):
        the_door_for(honest)(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name", _carriers())
def test_the_complaint_names_the_coordinate_that_moved(name):
    """A reader of the refusal is told where to look, not that something
    somewhere differs."""
    honest = SHAPES[name]["result"]
    coordinate = _coordinate_of(name)
    forged = copy.deepcopy(honest)
    records = _block(forged)["confusion_matrices"]
    records[0][coordinate], records[1][coordinate] = (
        records[1][coordinate], records[0][coordinate])
    with pytest.raises(VerificationError) as caught:
        _audit(name, forged)
    assert coordinate in str(caught.value), str(caught.value)


@pytest.mark.parametrize(
    "channel", EVERY_CHANNEL, ids=lambda f: f.__name__)
def test_every_channel_that_writes_these_records_checks_them(channel):
    """The premise, at the call site.

    Two of these three called the check from the day it was written and the
    third did not, which is why the table it shows was the one nothing held.
    Asserted here rather than by a third forgery, because what was missing
    was the call and a missing call is visible only where calls are made.
    """
    assert "_check_block_matrices_match" in inspect.getsource(channel), \
        channel.__name__


def test_two_spellings_of_one_cell_are_one_cell():
    """The normalisation, and the limit of it.

    A coordinate written ``1`` and one written ``1.0`` name the same cell,
    and so do ``False`` and ``0``: the contract coerces the column before
    any of this runs, and ``_level_key`` in the producer keys the inverse
    maps so that a bool level matches the 0/1 the data carried. A
    comparison here that split them would refuse an honest answer for
    being written down twice.
    """
    assert _as_contents(1) == _as_contents(1.0)
    assert _as_contents(False) == _as_contents(0)
    assert _as_contents({"level": 1}) == _as_contents({"level": 1.0})
    assert _as_contents({"outcome": False}) == _as_contents({"outcome": 0})
    assert _as_contents({"outcome": False}) != _as_contents({"outcome": True})
    assert _as_contents({"level": [False, True]}) != _as_contents(
        {"level": [True, False]})
