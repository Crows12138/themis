"""A bound says whether it says anything, and nothing checked.

``bounds_results[].numeric_uninformative`` is not a description. The
rendering contract routes on it: True sends a reader to the section that
says the data cannot constrain this effect, and the interval itself is not
shown as an answer. So the flag decides whether an answer is presented or
buried, and both ways of getting it wrong are consequential — a False on a
trivial interval presents an empty range as a finding, and a True on a
real one throws an answer the data supports away.

Free was measured before this rule existed: all 63 rows carrying the flag
had it flipped, and every one passed both public doors. A Manski interval
0.50 wide could call itself uninformative.

Nothing new is computed to hold it. The endpoints are already on the row
and already audited, and ``_audit_numeric_bounds`` already reads each
method's declared range in order to check the interval lies inside it.
"Uninformative" is exactly "as wide as that range", so the flag is a
question the function was already holding the answer to.

Two facts the corpus cannot show, asserted here instead:

- every corpus row carries ``False``, so the corpus exercises only the
  refusing half. The accepting half is built from the producer, whose own
  docstring names the case — nobody in the x=True arm makes the interval
  degenerate to [0, 1], honest and trivial.
- the span comes from ``_NUMERIC_ESTIMAND_BY_METHOD`` rather than from a
  constant written here, so a method admitting the ACE range would be
  measured against 2 without this rule being touched. Pinned, because a
  hard-coded 1.0 would keep passing every test in this file.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pandas as pd
import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.estimation.bounds_numeric import evaluate_manski_natural_bounds
from themis.verifier.bounds_rules import (
    _NUMERIC_ESTIMAND_BY_METHOD, _audit_numeric_bounds)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: (answer name, index of the bounds row) for every row carrying the flag.
CARRIERS = sorted(
    (name, i)
    for name, pair in SHAPES.items()
    for i, row in enumerate((pair["result"] or {}).get("bounds_results") or [])
    if "numeric_uninformative" in row
)


def test_the_rows_that_carry_the_flag():
    """The denominator, and that the corpus shows only one of its values."""
    assert len(CARRIERS) == 63, len(CARRIERS)
    values = {SHAPES[n]["result"]["bounds_results"][i]["numeric_uninformative"]
              for n, i in CARRIERS}
    assert values == {False}, values

    methods = {SHAPES[n]["result"]["bounds_results"][i]["method"]
               for n, i in CARRIERS}
    assert methods == {"manski_natural", "manski_tamer_monotonicity",
                       "balke_pearl_iv"}, methods


@pytest.mark.parametrize("name,i", CARRIERS)
def test_an_honest_flag_is_accepted(name, i):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_flipped_flag_is_refused():
    """The other half, one row at a time and counted.

    Counted rather than sampled: flipping the flag on a whole answer at
    once lets one refusal stand for every row in it, which reports a rule
    that reached one bounds_result as a rule that reached them all.
    """
    refused = 0
    for name, i in CARRIERS:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        flag = forged["bounds_results"][i]["numeric_uninformative"]
        forged["bounds_results"][i]["numeric_uninformative"] = not flag
        with pytest.raises(VerificationError, match="numeric_uninformative"):
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 63, refused


def test_an_interval_that_really_says_nothing_is_allowed_to_say_so():
    """The accepting half, from the producer rather than from the corpus.

    Every corpus row is informative, so a rule that simply refused True
    everywhere would pass every other test here and refuse the one answer
    that most needs to be sayable: the data does not constrain this. The
    producer's docstring names the case, so the case is built.
    """
    n = 400
    nobody_treated = pd.DataFrame(
        {"x": [False] * n, "y": [i % 3 == 0 for i in range(n)]})
    trivial = evaluate_manski_natural_bounds(
        nobody_treated, treatment="x", outcome="y",
        treatment_value=True, outcome_value=True)
    assert (trivial.lower_value, trivial.upper_value) == (0.0, 1.0)
    assert trivial.width_is_trivial is True

    honest = {"method": "manski_natural", "estimand": "arm_probability",
              "tightness": "sharp", "lower_value": trivial.lower_value,
              "upper_value": trivial.upper_value, "width": trivial.width,
              "numeric_uninformative": True}
    _audit_numeric_bounds(honest, method="manski_natural", rule="r")

    # And it is held in that direction too: the same interval claiming to
    # constrain something is the lie that presents an empty range as a
    # finding.
    with pytest.raises(VerificationError, match="numeric_uninformative"):
        _audit_numeric_bounds(dict(honest, numeric_uninformative=False),
                              method="manski_natural", rule="r")


def test_the_span_is_the_methods_declared_range_not_a_number_written_here():
    """Where the threshold comes from, pinned.

    A rule comparing against a literal 1.0 passes every other test in this
    file, and would then measure a method carrying the ACE range against
    the wrong span while looking correct. So the source is asserted: the
    range is the one the estimand table declares, and the flag is about
    the ARM interval, which is the only quantity that table admits.
    """
    for method, (estimand, (lo, hi)) in _NUMERIC_ESTIMAND_BY_METHOD.items():
        assert estimand == "arm_probability", (method, estimand)
        assert (lo, hi) == (0.0, 1.0), (method, lo, hi)

    # A row one epsilon short of the full span is informative, and one at
    # it is not. This is the boundary the flag turns on, so it is stated.
    almost = {"method": "manski_natural", "estimand": "arm_probability",
              "tightness": "sharp", "lower_value": 0.0,
              "upper_value": 1.0 - 1e-6, "numeric_uninformative": False}
    _audit_numeric_bounds(almost, method="manski_natural", rule="r")
    with pytest.raises(VerificationError, match="numeric_uninformative"):
        _audit_numeric_bounds(dict(almost, numeric_uninformative=True),
                              method="manski_natural", rule="r")


def test_a_flag_that_is_not_a_boolean_is_refused():
    """``1`` and ``True`` route a reader identically and are not the same
    claim; the contract says boolean, so a truthy stand-in is refused
    rather than quietly read as one."""
    row = {"method": "manski_natural", "estimand": "arm_probability",
           "tightness": "sharp", "lower_value": 0.0, "upper_value": 1.0,
           "numeric_uninformative": "yes"}
    with pytest.raises(VerificationError, match="must be a boolean"):
        _audit_numeric_bounds(row, method="manski_natural", rule="r")


def test_a_symbolic_row_carrying_no_endpoints_is_not_asked():
    """Bounds with no data behind them carry no flag and no interval, and
    a rule demanding one would refuse them for what they honestly are."""
    _audit_numeric_bounds({"method": "manski_natural", "tightness": "sharp"},
                          method="manski_natural", rule="r")
