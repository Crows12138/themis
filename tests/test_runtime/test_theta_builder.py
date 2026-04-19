"""Unit tests for theta_builder."""
from __future__ import annotations

import pytest

from themis.runtime.theta_builder import (
    ConflictingThetaEntry,
    build_theta,
)
from themis.types import (
    Atom,
    ConstTerm,
    ProbabilityStatement,
    ValuedAtom,
)


def atom(pred: str, obj: str = "alice") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def test_probability_statement_becomes_theta_entry():
    y, x = atom("y"), atom("x")
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.3,
    )
    theta = build_theta((stmt,))
    assert len(theta.entries) == 1
    key = next(iter(theta.entries))
    assert key.target_atom == y
    assert key.target_value is True
    assert key.given == frozenset({(x, True)})
    assert theta.entries[key] == 0.3


def test_empty_given_produces_unconditional_entry():
    z = atom("z")
    stmt = ProbabilityStatement(
        target=ValuedAtom(atom=z, value=False),
        given=(),
        value=0.6,
    )
    theta = build_theta((stmt,))
    (key,) = theta.entries
    assert key.given == frozenset()
    assert theta.entries[key] == 0.6


def test_non_probability_statements_are_skipped():
    from themis.types import CauseStatement, ObservationStatement

    stmts = (
        CauseStatement(from_atom=atom("a"), to_atom=atom("b")),
        ObservationStatement(atom=atom("c"), value=True),
    )
    theta = build_theta(stmts)
    assert theta.entries == {}


def test_multiple_distinct_statements_accumulate():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.7,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=False),),
        value=0.2,
    )
    theta = build_theta((s1, s2))
    assert len(theta.entries) == 2


def test_duplicate_key_with_different_value_raises():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.7,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.9,
    )
    with pytest.raises(ConflictingThetaEntry):
        build_theta((s1, s2))


def test_duplicate_key_with_same_value_is_idempotent():
    y, x = atom("y"), atom("x")
    s1 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.5,
    )
    s2 = ProbabilityStatement(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
        value=0.5,
    )
    theta = build_theta((s1, s2))
    assert len(theta.entries) == 1
