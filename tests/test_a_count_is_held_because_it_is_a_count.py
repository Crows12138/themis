"""A count is held because it is a count, not because something spends it.

A Manski natural row records four counts. Three of them -- the sample, the
target arm's joint count, the off-arm -- were checked where the row is
read: a count is a non-negative int, the two arms are disjoint, and the
interval a reader is shown is re-derived from them. The fourth, the
off-arm's joint count, was checked inside the branch that re-derives the
CONTRAST, because the contrast formula is the only place the number is
spent.

That made a fact about the data conditional on a fact about the report.
Measured on the stored answers: twenty-five rows record the count and
report no contrast, and on every one of them nothing read it -- adding
seven to it was accepted by every public door.

WHAT THE TWO CHECKS BUY DEPENDS ON THE ROW, and that is written down here
rather than rounded up. Where the off-arm is empty they pin the count to
0 outright, which is twenty-three of the twenty-five. Where it is not,
they leave a range, and an edit inside that range still passes. Closing
that needs a second record of the same count, and these rows have none:
no sibling arm row, and the one instrument table in reach is conditioned
on the instrument, so recovering the marginal from it needs a distribution
the row does not carry.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.verifier import bounds_rules
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

LEAF = "bounds_results.[].sufficient_statistics.n_joint_other_arm"


def _row(*, n=100, n_joint=30, n_other=40, n_joint_other=10, contrast=None):
    """A Manski natural row whose interval is what its counts yield."""
    row = {
        "method": "manski_natural",
        "lower_value": n_joint / n,
        "upper_value": (n_joint + n_other) / n,
        "sufficient_statistics": {
            "n": n,
            "n_joint_target_arm": n_joint,
            "n_other_arm": n_other,
            "n_joint_other_arm": n_joint_other,
        },
    }
    if contrast is not None:
        row["contrast"] = contrast
    return row


def _ask(row) -> None:
    bounds_rules._rederive_manski_natural_numeric(row)


# ------------------------------------------- held without a contrast

def test_an_honest_row_with_no_contrast_passes():
    _ask(_row())


def test_a_count_larger_than_the_off_arm_is_refused_with_no_contrast():
    """The case this used to skip: no contrast, so the branch that held
    the count never ran, and the count was free."""
    with pytest.raises(VerificationError, match="off-arm partition"):
        _ask(_row(n_joint_other=41))


def test_a_negative_count_is_refused_with_no_contrast():
    with pytest.raises(VerificationError, match="non-negative int"):
        _ask(_row(n_joint_other=-1))


def test_a_count_that_is_not_an_int_is_refused():
    with pytest.raises(VerificationError, match="non-negative int"):
        _ask(_row(n_joint_other=1.5))


def test_a_true_is_not_a_count():
    with pytest.raises(VerificationError, match="non-negative int"):
        _ask(_row(n_joint_other=True))


def test_an_empty_off_arm_pins_the_count_to_zero():
    """Two checks and no third one needed: non-negative and no larger than
    an off-arm of size zero leaves exactly one value."""
    _ask(_row(n_other=0, n_joint=30, n_joint_other=0))
    for bent in (7, 1, -1):
        with pytest.raises(VerificationError):
            _ask(_row(n_other=0, n_joint=30, n_joint_other=bent))


def test_a_non_empty_off_arm_leaves_a_range_and_this_says_so():
    """The limit, as a test rather than as a remark. An edit inside the
    range passes, and it will keep passing until something records the
    same count twice."""
    _ask(_row(n_other=40, n_joint_other=10))
    _ask(_row(n_other=40, n_joint_other=17))


def test_a_row_that_records_no_such_count_is_not_asked_for_one():
    """Requiring the key would be a claim about the SHAPE of the record,
    which is a different claim from this one and is not made here."""
    row = _row()
    row["sufficient_statistics"].pop("n_joint_other_arm")
    _ask(row)


# ----------------------------------------------- still held with one

def _contrast(*, n=100, n_joint=30, n_other=40, n_joint_other=10):
    n_arm = n - n_other
    return {"lower_value": (n_joint - n_joint_other - n_arm) / n,
            "upper_value": (n_joint - n_joint_other + n_other) / n}


def test_an_honest_contrast_still_passes():
    _ask(_row(contrast=_contrast()))


def test_a_contrast_the_counts_do_not_yield_is_still_refused():
    bad = _contrast()
    bad["lower_value"] += 0.05
    _ask_refused = pytest.raises(VerificationError, match="contrast.lower_value")
    with _ask_refused:
        _ask(_row(contrast=bad))


def test_a_contrast_with_no_count_under_it_is_refused():
    """The count arrives from the caller now, so the absent case is named
    here instead of falling out of a helper that reads the mapping."""
    row = _row(contrast=_contrast())
    row["sufficient_statistics"].pop("n_joint_other_arm")
    with pytest.raises(VerificationError, match="n_joint_other_arm"):
        _ask(row)


def test_the_contrast_helper_no_longer_reads_the_mapping():
    """Structural, and the point of the change: the function that spends
    the counts is handed them, so no validation can hide inside it."""
    import inspect
    signature = inspect.signature(
        bounds_rules._rederive_manski_natural_contrast)
    assert "stats" not in signature.parameters
    assert "n_joint_other" in signature.parameters


# ---------------------------------------------------------- the corpus

def _layers() -> tuple[list, list, list, list]:
    """Every row recording the count, split by what holds it.

    A row with a contrast was already held, by the exact re-derivation the
    contrast branch runs. The rest are what this frontier is about, and
    among them the off-arm decides whether the two checks pin the count or
    only bound it.
    """
    recording, with_contrast, pinned, ranged = [], [], [], []
    for name, pair in sorted(SHAPES.items()):
        for i, row in enumerate(pair["result"].get("bounds_results") or ()):
            stats = row.get("sufficient_statistics")
            if not isinstance(stats, dict) or "n_joint_other_arm" not in stats:
                continue
            recording.append((name, i))
            if row.get("contrast") is not None:
                with_contrast.append((name, i))
            elif stats.get("n_other_arm") == 0:
                pinned.append((name, i))
            else:
                ranged.append((name, i))
    return recording, with_contrast, pinned, ranged


RECORDING, WITH_CONTRAST, PINNED, RANGED = _layers()


def test_the_rosters_are_the_size_they_were_measured_at():
    assert (len(RECORDING), len(WITH_CONTRAST), len(PINNED), len(RANGED)) == \
        (56, 31, 23, 2)


def test_the_unheld_answers_are_exactly_the_rows_with_no_contrast():
    """The declared remainder had twenty-five answers for this leaf, and
    twenty-five answers carry a row whose count no contrast spends. The
    two numbers being the same is the diagnosis, stated as a test."""
    assert len({name for name, _i in PINNED + RANGED}) == 25


def _bend(name, index, bent):
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    result["bounds_results"][index]["sufficient_statistics"][
        "n_joint_other_arm"] = bent
    try:
        the_door_for(result)(pair["program"], result)
    except Exception:
        return True
    return False


@pytest.mark.parametrize("name,index", PINNED, ids=lambda v: str(v))
def test_an_empty_off_arm_refuses_every_edit(name, index):
    value = SHAPES[name]["result"]["bounds_results"][index][
        "sufficient_statistics"]["n_joint_other_arm"]
    for bent in (value + 7, value * 2 + 1, -abs(value) - 1):
        if bent == value:
            continue
        assert _bend(name, index, bent), (name, index, bent)


@pytest.mark.parametrize("name,index", RANGED, ids=lambda v: str(v))
def test_a_non_empty_off_arm_is_held_only_to_its_range(name, index):
    """The measured limit. Over the off-arm is refused; inside it is not,
    and saying so here is what stops the gap being rediscovered as a
    surprise."""
    stats = SHAPES[name]["result"]["bounds_results"][index][
        "sufficient_statistics"]
    value, n_other = stats["n_joint_other_arm"], stats["n_other_arm"]
    assert _bend(name, index, n_other + 1)
    assert _bend(name, index, -1)
    assert not _bend(name, index, value + 7)


@pytest.mark.parametrize("name", sorted({name for name, _i in RECORDING}),
                         ids=lambda v: str(v))
def test_the_honest_counts_still_pass(name):
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])
