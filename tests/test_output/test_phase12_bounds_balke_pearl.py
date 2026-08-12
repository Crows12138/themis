"""S.12.3 — Balke-Pearl IV bounds, at whatever cardinality the model has.

Three of the tests here used to assert that a non-binary outcome, treatment
or instrument makes this attempt return None. Two of the three cardinalities
never mattered to the method: the response-function model is "which treatment
at each instrument level, which outcome at each treatment level", and the
only thing the cardinalities decide is how many such pairs there are. What
replaces those three is one test per way the model can genuinely be
unavailable — no instrument, no declared domain to enumerate, or a partition
larger than the LP is run at — plus the size law itself, which is what all
three now go through.
"""
from __future__ import annotations

import pytest

from themis.output.bounds import (
    MAX_RESPONSE_TYPES,
    attempt_balke_pearl_iv,
    response_type_count,
)
from themis.types import (
    Atom,
    BoundsMethod,
    ConstTerm,
    EffectQuery,
    Intervention,
    ValuedAtom,
)


def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm("me"),))


def _effect(
    target_pred: str = "y",
    intervention_pred: str = "x",
    given: tuple = (),
    target_value=True,
    intervention_value=True,
) -> EffectQuery:
    return EffectQuery(
        target=ValuedAtom(atom=_atom(target_pred), value=target_value),
        intervention=Intervention(
            atom=_atom(intervention_pred), value=intervention_value),
        given=given,
    )


def _all_binary():
    return dict(outcome_levels=2, treatment_levels=2, instrument_levels=2)


# ---------------------------------------------------------- happy path

def test_balke_pearl_returns_bounds_with_valid_iv():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert b is not None
    assert b.method == BoundsMethod.BALKE_PEARL_IV


def test_assumptions_list_iv_triple():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert "iv1_relevance" in b.assumptions
    assert any("iv2_exclusion" in a for a in b.assumptions)
    assert any("iv3_independence" in a for a in b.assumptions)


def test_data_required_names_observable_joint():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    # P(Y, X | Z) — 8 observable probabilities for a binary triple, and the
    # count is stated from the cardinalities rather than assumed.
    assert any("P(y, x | z)" in s for s in b.data_required)
    assert any("8 probabilities" in s for s in b.data_required)


def test_data_required_counts_the_cells_this_model_has():
    b = attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z",
        outcome_levels=3, treatment_levels=3, instrument_levels=2,
    )
    assert any("18 probabilities" in s for s in b.data_required)


def test_lower_and_upper_reference_balke_pearl():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert "Balke-Pearl" in b.lower_expression
    # Both bounds reference the same observable joint
    assert "z" in b.lower_expression
    assert "z" in b.upper_expression


def test_the_expression_names_the_arm_it_brackets():
    """The estimand is not left to the method's reputation.

    This block once carried an ACE interval under a question that asked for
    one arm, on the strength of a docstring saying the renderer would explain
    the difference. So the arm is in the expression, in the estimand field,
    and in the notes.
    """
    b = attempt_balke_pearl_iv(
        _effect(target_value=True, intervention_value=True),
        instrument_predicate="z", **_all_binary(),
    )
    assert b.estimand == "arm_probability"
    assert b.lower_expression.startswith("min of P(y=true | do(x=true))")
    assert b.upper_expression.startswith("max of P(y=true | do(x=true))")
    assert "P(y=true | do(x=true))" in b.notes


def test_the_arm_follows_the_queried_levels():
    b = attempt_balke_pearl_iv(
        _effect(target_value=2, intervention_value=1),
        instrument_predicate="z",
        outcome_levels=3, treatment_levels=3, instrument_levels=2,
    )
    assert "P(y=2 | do(x=1))" in b.lower_expression


def test_notes_state_the_model_size_and_where_it_comes_from():
    b = attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z",
        outcome_levels=2, treatment_levels=3, instrument_levels=2,
    )
    # 3^2 * 2^3 = 72
    assert "72 response types" in b.notes
    assert "3 treatment levels" in b.notes


def test_uses_actual_predicate_names():
    b = attempt_balke_pearl_iv(
        _effect(target_pred="cancer", intervention_pred="smoking"),
        instrument_predicate="cigarette_tax",
        **_all_binary(),
    )
    assert "cancer" in b.lower_expression
    assert "smoking" in b.lower_expression
    assert "cigarette_tax" in b.lower_expression


# ---------------------------------------------------- the size law itself

def test_the_partition_is_a_function_of_the_cardinalities():
    """Balke-Pearl's 16 is what this number is when everything is binary."""
    assert response_type_count(
        treatment_levels=2, outcome_levels=2, instrument_levels=2) == 16
    # X responds to each of |Z| instrument levels; Y to each of |X|.
    assert response_type_count(
        treatment_levels=2, outcome_levels=2, instrument_levels=3) == 32
    assert response_type_count(
        treatment_levels=3, outcome_levels=2, instrument_levels=2) == 72
    assert response_type_count(
        treatment_levels=2, outcome_levels=3, instrument_levels=2) == 36


@pytest.mark.parametrize("levels", [
    dict(outcome_levels=3, treatment_levels=2, instrument_levels=2),
    dict(outcome_levels=2, treatment_levels=3, instrument_levels=2),
    dict(outcome_levels=2, treatment_levels=2, instrument_levels=3),
    dict(outcome_levels=4, treatment_levels=4, instrument_levels=2),
])
def test_a_non_binary_variable_no_longer_refuses_the_method(levels):
    """The three refusals this file used to assert, inverted.

    Each of these is a query that used to fall all the way to the
    assumption-free Manski floor — the instrument's entire contribution
    discarded — over a cardinality the response-function model never needed.
    """
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **levels)
    assert b is not None
    assert b.method == BoundsMethod.BALKE_PEARL_IV


# ----------------------------------------------------- refusal conditions

def test_returns_none_when_no_instrument():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate=None, **_all_binary())
    assert b is None


@pytest.mark.parametrize("role", ["outcome_levels", "treatment_levels",
                                  "instrument_levels"])
def test_returns_none_when_a_variable_has_no_finite_domain(role):
    """An undeclared continuous variable has no response-function partition:
    there is no finite map to enumerate. This is the honest reason the method
    can be unavailable, and it is about the domain existing, not its size."""
    levels = _all_binary() | {role: None}
    assert attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z", **levels) is None


@pytest.mark.parametrize("role", ["outcome_levels", "treatment_levels",
                                  "instrument_levels"])
def test_returns_none_when_a_variable_never_varies(role):
    levels = _all_binary() | {role: 1}
    assert attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z", **levels) is None


def test_returns_none_when_the_partition_is_larger_than_the_lp_is_run_at():
    """5^2 · 5^5 = 78125 types — a real model whose LP this package declines.

    The refusal is about compute, and it is taken HERE rather than only at
    the numeric end so that the symbolic layer never promises a method the
    data path will refuse: the two are supposed to name the same method.
    """
    big = dict(outcome_levels=5, treatment_levels=5, instrument_levels=2)
    assert response_type_count(
        treatment_levels=5, outcome_levels=5, instrument_levels=2) is None
    assert attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z", **big) is None


def test_the_size_law_stops_counting_instead_of_overflowing():
    """A continuous column arrives here as thousands of observed levels, and
    |Y|^|X| on those is an integer Python will not even render as a decimal
    string. Past the cap the only fact anyone needs is that it is past."""
    assert response_type_count(
        treatment_levels=4000, outcome_levels=4000, instrument_levels=4000,
    ) is None


def test_the_largest_model_still_offered_is_offered():
    """The cap is a boundary, not a mood: just under it, the method applies."""
    ok = dict(outcome_levels=4, treatment_levels=4, instrument_levels=2)
    assert response_type_count(
        treatment_levels=4, outcome_levels=4, instrument_levels=2,
    ) <= MAX_RESPONSE_TYPES
    assert attempt_balke_pearl_iv(
        _effect(), instrument_predicate="z", **ok) is not None


def test_returns_none_for_conditional_query():
    given = (ValuedAtom(atom=_atom("w"), value=True),)
    b = attempt_balke_pearl_iv(
        _effect(given=given), instrument_predicate="z", **_all_binary()
    )
    assert b is None


# --------------------------------------------------------- structural

def test_method_enum_value():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert b.method.value == "balke_pearl_iv"


def test_immutable():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    with pytest.raises(Exception):
        b.method = BoundsMethod.MANSKI_NATURAL  # type: ignore
