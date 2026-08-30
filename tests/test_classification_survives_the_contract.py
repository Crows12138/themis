"""A column classification has to survive the data contract.

``validate_data`` widens every model column to bool or float64 before an
estimator sees the frame. A criterion that reads dtype to tell an integer
code from a measurement therefore stops being decidable at that boundary, and
does so in the quietest possible way: one branch takes all the traffic, the
other becomes unreachable, and neither raises. What makes such a criterion
safe is a property, not a call site — it must give the same answer on both
sides of the contract. These tests pin that property, and the claims the
system makes to a reader once it holds.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.contract import validate_data
from themis.estimation.refusal_words import Refuses
from themis.estimation.discovery import (
    _classify_column,
    _viol_lingam,
    discover_graph,
    markov_blanket,
)

N = 600


def _column(shape: str, rng: np.random.Generator, base: np.ndarray):
    """One column per way of writing the same underlying quantity down."""
    if shape == "boolean":
        return base % 2 == 0
    if shape == "integer_coded_five_levels":
        return base % 5
    if shape == "float_written_integer_codes":
        return (base % 5).astype(float)
    if shape == "high_cardinality_integer_code":
        return base % 300
    if shape == "continuous":
        return base + rng.standard_normal(len(base))
    raise AssertionError(shape)


# What each shape IS, not merely that the answer is stable — a criterion
# that answered "continuous" for everything would satisfy stability alone.
EXPECTED = {
    "boolean": "bool",
    "integer_coded_five_levels": "discrete",
    "float_written_integer_codes": "discrete",
    "high_cardinality_integer_code": "continuous",
    "continuous": "continuous",
}


def _frame(shape: str, seed: int = 3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    base = rng.integers(0, 1000, N)
    return pd.DataFrame({
        "a": _column(shape, rng, base),
        "b": _column(shape, rng, (base * 7 + 3) % 1000),
        "c": _column(shape, rng, (base * 11 + 5) % 1000),
    })


def _coerced(df: pd.DataFrame) -> pd.DataFrame:
    return validate_data(df, required_columns=set(df.columns)).data


@pytest.mark.parametrize("shape", sorted(EXPECTED))
def test_the_classification_is_the_same_on_both_sides_of_the_contract(shape):
    df = _frame(shape)
    coerced = _coerced(df)
    for col in df.columns:
        before = _classify_column(df[col])
        after = _classify_column(coerced[col])
        assert before == after, (
            f"{shape}/{col}: {before!r} before the contract, {after!r} after "
            f"— the criterion is reading something validate_data rewrites"
        )


@pytest.mark.parametrize("shape", sorted(EXPECTED))
def test_each_shape_is_classified_as_what_it_is(shape):
    coerced = _coerced(_frame(shape))
    for col in coerced.columns:
        assert _classify_column(coerced[col]) == EXPECTED[shape]


def test_the_contract_really_does_erase_the_dtype_the_old_criterion_read():
    """The premise of the whole file: without this, the tests above would
    hold for a dtype-reading criterion too, and pin nothing."""
    df = _frame("integer_coded_five_levels")
    assert all(str(dt) == "int64" for dt in df.dtypes)
    assert all(str(dt) == "float64" for dt in _coerced(df).dtypes)


# ---------------------------------------------------------------- the reader


def test_auto_routes_an_integer_coded_frame_to_a_discrete_test():
    result = discover_graph(_frame("integer_coded_five_levels"),
                            algorithm="auto")
    assert result.indep_test == "chisq"
    assert result.algorithm != "lingam"
    assert {kind for _, kind in result.column_dtypes} == {"discrete"}
    assert result.data_diagnostics.n_continuous == 0
    assert result.data_diagnostics.n_discrete == 3


def test_the_rationale_does_not_speak_of_variables_the_frame_has_none_of():
    """The selector explains itself in the reader's terms; the explanation
    has to be about the frame it actually saw."""
    result = discover_graph(_frame("integer_coded_five_levels"),
                            algorithm="auto")
    assert result.data_diagnostics.n_continuous == 0
    # The route that says "the data are continuous" is a different
    # sentence, and naming it is what this pins — the substring it used to
    # search for could also have arrived inside some other clause.
    assert "auto_chose_pc_for_the_fewest_assumptions" not in {
        one["token"] for one in result.selection_rationale}
    assert "auto_chose_pc_because_everything_is_categorical" in {
        one["token"] for one in result.selection_rationale}


def test_a_continuous_frame_still_reaches_the_continuous_route():
    """The counterexample to the fix over-reaching: integer-valuedness must
    not swallow measurements."""
    rng = np.random.default_rng(5)
    df = pd.DataFrame({
        "x": rng.exponential(1.0, N) - 1.0,
        "y": rng.exponential(1.0, N) - 1.0,
        "z": rng.exponential(1.0, N) - 1.0,
    })
    result = discover_graph(df, algorithm="auto")
    assert {kind for _, kind in result.column_dtypes} == {"continuous"}
    assert result.data_diagnostics.n_continuous == 3


@pytest.mark.parametrize("shape", ["boolean", "integer_coded_five_levels"])
def test_lingam_names_the_frame_it_cannot_orient(shape):
    """A frame with no continuous column violates LiNGAM's premise outright.
    Selecting the columns to judge by dtype dropped exactly those columns, so
    the check went silent on its own worst case."""
    coerced = _coerced(_frame(shape))
    violations = _viol_lingam(coerced, len(coerced))
    assert violations, f"{shape}: no violation reported for a frame with no continuous column"
    assert violations[0]["token"] == "lingam_was_given_level_codes"
    # And it names the columns it is about, which is the half a sentence
    # searched for a substring never checked.
    assert set(coerced.columns) <= set(violations[0]["said"]["columns"])


def test_lingam_says_nothing_about_level_codes_when_there_are_none():
    rng = np.random.default_rng(9)
    df = pd.DataFrame({
        "x": rng.exponential(1.0, N) - 1.0,
        "y": rng.exponential(1.0, N) - 1.0,
    })
    violations = _viol_lingam(_coerced(df), N)
    assert not any("level-coded" in v for v in violations)


def test_markov_blanket_still_separates_the_two_routes():
    """The call site stopped reaching around the contract for un-coerced
    data; the discrete/continuous split it was reaching for must survive."""
    rng = np.random.default_rng(4)
    discrete = pd.DataFrame({
        "t": rng.integers(0, 4, N),
        "u": rng.integers(0, 4, N),
        "v": rng.integers(0, 4, N),
    })
    result = markov_blanket(discrete, target="t")
    assert result.test == "chisq"

    mixed = discrete.copy()
    mixed["w"] = rng.standard_normal(N)
    with pytest.raises(Exception) as raised:
        markov_blanket(mixed, target="t")
    assert raised.value.species is Refuses.MIXED_TYPES_IN_ONE_TEST
