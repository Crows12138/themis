"""S.12.2 — Manski natural bounds tests."""
from __future__ import annotations

import pytest

from themis import language
from themis.output.bounds import attempt_manski_natural
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
    target_val: bool = True,
    intervention_pred: str = "x",
    intervention_val: bool = True,
    given: tuple = (),
) -> EffectQuery:
    return EffectQuery(
        target=ValuedAtom(atom=_atom(target_pred), value=target_val),
        intervention=Intervention(atom=_atom(intervention_pred), value=intervention_val),
        given=given,
    )


# ----------------------------------------------------------- happy path

def test_manski_binary_returns_bounds():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    assert b is not None
    assert b.method == BoundsMethod.MANSKI_NATURAL


def test_manski_no_assumptions():
    """Manski natural is the assumption-free baseline."""
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    assert b.assumptions == ()


def test_manski_lower_is_observed_share():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    # Lower = P(Y=y|X=x) · P(X=x) — the observed mass under the queried arm
    assert "P(y=true | x=true)" in b.lower_expression
    assert "P(x=true)" in b.lower_expression


def test_manski_upper_adds_other_arm_mass():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    # Upper = lower + P(X≠x) — the unbounded contribution
    assert "P(x=false)" in b.upper_expression
    # Lower is contained in upper (upper = lower + extra)
    assert b.lower_expression in b.upper_expression


def test_manski_data_required_lists_joint():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    (needed,) = b.data_required
    assert needed["said"] == {"expression": "P(y, x)"}


def test_manski_notes_explain_width():
    """The width is the whole of what this row has to say.

    It is the off-arm mass, and nothing else on the row records it — the
    expressions carry it as a term inside a sum. So the note is not a
    restatement, and what a reader is given is assembled from the fact.
    """
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    (note,) = b.notes
    assert note["token"] == "width_is_the_off_arm_mass"
    assert note["said"] == {"mass": "P(x=false)"}
    for lang in ("zh", "en"):
        assert "P(x=false)" in language.spoke(note, lang)


# -------------------------------------------------------- boundary conditions

def test_manski_returns_none_on_continuous_outcome():
    """Continuous outcome — different formulation needed; out of scope."""
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=False)
    assert b is None


def test_manski_returns_none_on_conditional_query():
    """effect(Y | do(X), given Z=z) — derivation differs; future."""
    given = (ValuedAtom(atom=_atom("z"), value=True),)
    b = attempt_manski_natural(_effect(given=given), outcome_event_is_discrete=True)
    assert b is None


def test_manski_handles_intervention_value_false():
    """do(X=false) — symbol arithmetic on the negation."""
    b = attempt_manski_natural(
        _effect(intervention_val=False), outcome_event_is_discrete=True
    )
    assert b is not None
    # Lower bound conditions on X=false
    assert "P(y=true | x=false)" in b.lower_expression
    # Upper adds P(X=true) (the other arm mass)
    assert "P(x=true)" in b.upper_expression


def test_manski_handles_target_value_false():
    """asking P(Y=false | do(X=true)) — same machinery."""
    b = attempt_manski_natural(
        _effect(target_val=False), outcome_event_is_discrete=True
    )
    assert b is not None
    assert "P(y=false | x=true)" in b.lower_expression


def test_manski_uses_actual_predicate_names():
    """Predicate names are not hardcoded; rendering pulls from the query."""
    b = attempt_manski_natural(
        _effect(
            target_pred="belly_fat_loss",
            intervention_pred="running",
        ),
        outcome_event_is_discrete=True,
    )
    assert "belly_fat_loss" in b.lower_expression
    assert "running" in b.lower_expression
    assert "running" in b.upper_expression


# -------------------------------------------------------- structural shape

def test_manski_method_enum_value():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    assert b.method.value == "manski_natural"


def test_manski_width_uninformative_default_false():
    """Symbolic phase doesn't know whether bounds are trivial without data —
    leave width_when_uninformative=False, let renderer/numeric layer flag."""
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    assert b.width_when_uninformative is False


def test_manski_result_immutable():
    b = attempt_manski_natural(_effect(), outcome_event_is_discrete=True)
    with pytest.raises(Exception):
        b.method = BoundsMethod.BALKE_PEARL_IV  # type: ignore
