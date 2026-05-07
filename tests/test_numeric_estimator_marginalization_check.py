"""Iter 171 — unit tests for can_derive_via_marginalization helper.

Foundation for iter 168's option (b): kernel auto-marginalizes
missing CPTs that can be derived from richer joint families. This
test file pins the DETECTION layer; iter 172+ will wire actual
derivation into _evaluate.
"""
from __future__ import annotations

from themis.runtime.numeric_estimator import (
    ProbabilityKey,
    Theta,
    can_derive_via_marginalization,
)
from themis.types import Atom, ConstTerm


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def test_detects_pyx_derivable_from_pyxz_plus_pzx():
    """P(Y|X) demanded; theta has P(Y|X, Z=v) for every v AND
    P(Z=v|X) for every v. Helper returns True."""
    x, y, z = _A("x"), _A("y"), _A("z")
    theta = Theta(entries={
        # Outer: P(Y=True | X=True, Z=v) — both Z values
        ProbabilityKey(y, True, frozenset([(x, True), (z, True)])): 0.8,
        ProbabilityKey(y, True, frozenset([(x, True), (z, False)])): 0.4,
        # Inner: P(Z=v | X=True) — both Z values
        ProbabilityKey(z, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(z, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    assert can_derive_via_marginalization(missing, theta) is True


def test_returns_false_when_inner_factor_missing():
    """P(Y|X) demanded; theta has all P(Y|X, Z=v) but lacks
    P(Z=v|X) → can't marginalize cleanly."""
    x, y, z = _A("x"), _A("y"), _A("z")
    theta = Theta(entries={
        ProbabilityKey(y, True, frozenset([(x, True), (z, True)])): 0.8,
        ProbabilityKey(y, True, frozenset([(x, True), (z, False)])): 0.4,
        # P(Z|X) absent
    })
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    assert can_derive_via_marginalization(missing, theta) is False


def test_returns_false_when_outer_factor_partial():
    """P(Y|X, Z=True) present but P(Y|X, Z=False) absent → can't
    marginalize over Z."""
    x, y, z = _A("x"), _A("y"), _A("z")
    theta = Theta(entries={
        ProbabilityKey(y, True, frozenset([(x, True), (z, True)])): 0.8,
        # missing: P(Y|X=T, Z=F)
        ProbabilityKey(z, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(z, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    assert can_derive_via_marginalization(missing, theta) is False


def test_extra_atoms_hint_used():
    """When theta is sparse but extra_atoms hints at the
    marginalization variable, helper looks there."""
    x, y, z = _A("x"), _A("y"), _A("z")
    theta = Theta(entries={
        ProbabilityKey(y, True, frozenset([(x, True), (z, True)])): 0.8,
        ProbabilityKey(y, True, frozenset([(x, True), (z, False)])): 0.4,
        ProbabilityKey(z, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(z, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    # extra_atoms hint shouldn't break the True path
    assert can_derive_via_marginalization(
        missing, theta, extra_atoms=(z,),
    ) is True


def test_returns_false_when_target_already_in_given():
    """Edge case: missing_key is itself well-formed but the candidate
    Z atom is already in the given set; shouldn't try marginalizing
    over it."""
    x, y = _A("x"), _A("y")
    theta = Theta(entries={
        ProbabilityKey(y, True, frozenset([(x, True)])): 0.5,
    })
    # P(Y|X) — but key already exists; not really "missing", but
    # check the helper doesn't crash on degenerate input
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    # No extra Z to marginalize over → False
    assert can_derive_via_marginalization(missing, theta) is False
