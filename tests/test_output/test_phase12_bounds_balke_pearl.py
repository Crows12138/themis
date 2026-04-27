"""S.12.3 — Balke-Pearl IV bounds tests."""
from __future__ import annotations

import pytest

from themis.output.bounds import attempt_balke_pearl_iv
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
) -> EffectQuery:
    return EffectQuery(
        target=ValuedAtom(atom=_atom(target_pred), value=True),
        intervention=Intervention(atom=_atom(intervention_pred), value=True),
        given=given,
    )


def _all_binary():
    return dict(
        outcome_is_binary=True,
        treatment_is_binary=True,
        instrument_is_binary=True,
    )


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
    # P(Y, X | Z) — the 8 observable probabilities for binary triple
    assert any("P(y, x | z)" in s for s in b.data_required)


def test_lower_and_upper_reference_balke_pearl():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert "Balke-Pearl" in b.lower_expression
    # Both bounds reference the same observable joint
    assert "z" in b.lower_expression
    assert "z" in b.upper_expression


def test_notes_explain_ace_distinction():
    """User must know BP bounds the difference, not the single P."""
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate="z", **_all_binary())
    assert "ACE" in b.notes or "do(" in b.notes
    # And references the paper
    assert "Balke-Pearl" in b.notes or "1997" in b.notes


def test_uses_actual_predicate_names():
    b = attempt_balke_pearl_iv(
        _effect(target_pred="cancer", intervention_pred="smoking"),
        instrument_predicate="cigarette_tax",
        **_all_binary(),
    )
    assert "cancer" in b.lower_expression
    assert "smoking" in b.lower_expression
    assert "cigarette_tax" in b.lower_expression


# ----------------------------------------------------- refusal conditions

def test_returns_none_when_no_instrument():
    b = attempt_balke_pearl_iv(_effect(), instrument_predicate=None, **_all_binary())
    assert b is None


def test_returns_none_when_outcome_not_binary():
    b = attempt_balke_pearl_iv(
        _effect(),
        instrument_predicate="z",
        outcome_is_binary=False,
        treatment_is_binary=True,
        instrument_is_binary=True,
    )
    assert b is None


def test_returns_none_when_treatment_not_binary():
    b = attempt_balke_pearl_iv(
        _effect(),
        instrument_predicate="z",
        outcome_is_binary=True,
        treatment_is_binary=False,
        instrument_is_binary=True,
    )
    assert b is None


def test_returns_none_when_instrument_not_binary():
    b = attempt_balke_pearl_iv(
        _effect(),
        instrument_predicate="z",
        outcome_is_binary=True,
        treatment_is_binary=True,
        instrument_is_binary=False,
    )
    assert b is None


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
