"""Phase 12.MT — Manski-Tamer monotonicity bounds tests.

Manski (1997) MTR — when the user asserts monotone treatment response,
one side of the Manski natural interval tightens to the observed
outcome marginal P(Y=y), strictly contained in the assumption-free
Manski natural bounds.
"""
from __future__ import annotations

from themis import language
from themis.output.bounds import attempt_manski_tamer_monotonicity
from themis.ledger import Monotonicity
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

def test_mtr_returns_bounds_when_monotonicity_declared():
    b = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b is not None
    assert b.method == BoundsMethod.MANSKI_TAMER_MONOTONICITY


def test_mtr_carries_mtr_assumption():
    b = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b.assumptions == ("mtr_non_decreasing",)


def test_mtr_assumption_records_direction():
    b_inc = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_INCREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b_inc.assumptions == ("mtr_non_increasing",)


# ------------------------------------------------- bounds tightening shape

def test_mtr_treating_high_with_non_decreasing_tightens_lower():
    """Y(1) >= Y(0), querying do(X=1): lower bound tightens to P(Y=y).

    Intuition: under MTR, observing Y=1 in the X=0 stratum forces
    Y(1)=1 in that stratum, lifting the lower of E[Y(1)] from
    P(Y=1, X=1) to the observed marginal P(Y=1).
    """
    b = attempt_manski_tamer_monotonicity(
        _effect(intervention_val=True),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    # Lower tightens to marginal; upper is Manski natural upper.
    assert b.lower_expression == "P(y=true)"
    assert "P(y=true | x=true)" in b.upper_expression
    assert "P(x=false)" in b.upper_expression


def test_mtr_treating_low_with_non_decreasing_tightens_upper():
    """Y(1) >= Y(0), querying do(X=0): upper bound tightens to P(Y=y).

    Symmetric: among the X=1 stratum, observing Y=0 forces Y(0)=0
    (since Y(0) <= Y(1)=0); upper of E[Y(0)] caps at observed marginal.
    """
    b = attempt_manski_tamer_monotonicity(
        _effect(intervention_val=False),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    # Lower is Manski natural lower; upper tightens to marginal.
    assert "P(y=true | x=false)" in b.lower_expression
    assert "P(x=false)" in b.lower_expression
    assert b.upper_expression == "P(y=true)"


def test_mtr_treating_high_with_non_increasing_tightens_upper():
    """Y(1) <= Y(0), querying do(X=1): upper tightens (mirror of above)."""
    b = attempt_manski_tamer_monotonicity(
        _effect(intervention_val=True),
        monotonicity=Monotonicity.NON_INCREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert "P(y=true | x=true)" in b.lower_expression
    assert b.upper_expression == "P(y=true)"


def test_mtr_treating_low_with_non_increasing_tightens_lower():
    """Y(1) <= Y(0), querying do(X=0): lower tightens (mirror)."""
    b = attempt_manski_tamer_monotonicity(
        _effect(intervention_val=False),
        monotonicity=Monotonicity.NON_INCREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b.lower_expression == "P(y=true)"
    assert "P(y=true | x=false)" in b.upper_expression


# -------------------------------------------------------- boundary conditions

def test_mtr_returns_none_on_continuous_outcome():
    b = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=False,
    )
    assert b is None


def test_mtr_returns_none_on_conditional_query():
    given = (ValuedAtom(atom=_atom("z"), value=True),)
    b = attempt_manski_tamer_monotonicity(
        _effect(given=given),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b is None


def test_mtr_returns_none_on_non_bool_intervention():
    """Manski-Tamer's binary derivation requires bool intervention."""
    bad_query = EffectQuery(
        target=ValuedAtom(atom=_atom("y"), value=True),
        intervention=Intervention(atom=_atom("x"), value=42),
        given=(),
    )
    b = attempt_manski_tamer_monotonicity(
        bad_query,
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    assert b is None


# ----------------------------------------------------- notes / data_required

def test_mtr_notes_say_which_side_moved_and_to_what():
    """What this row has that Manski natural does not.

    The note used to open by naming the method, which `method` already
    carries; that clause is gone. What stays is what nothing else says —
    the direction assumed, which end it moved, and what it moved to. Both
    words go in HOLES: the note used to render them where it was built,
    which put an English token in a Chinese sentence for one and a
    hand-written pair of Chinese characters for the other.
    """
    b = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    (note,) = b.notes
    assert note["token"] == "one_side_tightened"
    assert note["words"]["side"] == {"vocabulary": "bound_side",
                                     "token": "lower"}
    assert note["words"]["direction"] == {"vocabulary": "monotonicity",
                                          "token": "non_decreasing"}
    for lang in ("zh", "en"):
        said = language.spoke(note, lang)
        assert Monotonicity.said(Monotonicity.NON_DECREASING, lang) in said
        assert "non_decreasing" not in said
    assert b.assumptions == ("mtr_non_decreasing",)


def test_mtr_data_required_lists_joint():
    b = attempt_manski_tamer_monotonicity(
        _effect(),
        monotonicity=Monotonicity.NON_DECREASING,
        outcome_levels=[False, True],
        outcome_event_is_discrete=True,
    )
    (needed,) = b.data_required
    assert needed["said"] == {"expression": "P(y, x)"}
