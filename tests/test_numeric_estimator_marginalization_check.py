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


def test_three_deep_marginalization_resolves():
    """Iter 176: marginalization recurses through 3 levels (P(Y|X)
    → P(Y|X,Z1) → P(Y|X,Z1,Z2) → P(Y|X,Z1,Z2,Z3) leaf-direct).
    iter 172's depth ≤ 3 limit is generous enough for typical ADMG
    c-component shapes; pin so future tweaks don't accidentally
    block this case."""
    from themis.runtime.numeric_estimator import (
        _try_derive_via_marginalization,
    )

    import itertools

    x, y = _A("x"), _A("y")
    z1, z2, z3 = _A("z1"), _A("z2"), _A("z3")

    theta_entries = {}
    # Chain factors P(Z_i | X, Z_<i) — uniform
    for i, z in enumerate([z1, z2, z3]):
        prior = [z1, z2, z3][:i]
        for vals in itertools.product([True, False], repeat=len(prior)):
            g = frozenset([(x, True)] + list(zip(prior, vals)))
            theta_entries[ProbabilityKey(z, True, g)] = 0.5
            theta_entries[ProbabilityKey(z, False, g)] = 0.5
    # P(Y=T | X, Z1, Z2, Z3) — all 8 combos uniform
    for v1, v2, v3 in itertools.product([True, False], repeat=3):
        g = frozenset([(x, True), (z1, v1), (z2, v2), (z3, v3)])
        theta_entries[ProbabilityKey(y, True, g)] = 0.5
    theta = Theta(entries=theta_entries)
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    val = _try_derive_via_marginalization(missing, theta)
    assert val is not None, "3-deep marginalization should resolve"
    assert abs(val - 0.5) < 1e-9


def test_bayes_inversion_resolves_chain_mediator_inner_factor():
    """Iter 187: chain mediator front-door demands P(M1|X, M2)
    which user typically doesn't supply. Bayes inversion derives it
    from supplied P(M2|X, M1) + P(M1|X) (the chain factors):

        P(M1|X, M2) = P(M2|X, M1) · P(M1|X) / P(M2|X)

    where P(M2|X) is itself marginalizable from the supplied chain.
    """
    from themis.runtime.numeric_estimator import (
        _try_derive_via_bayes_inversion,
    )

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    theta = Theta(entries={
        ProbabilityKey(m1, True, frozenset([(x, True)])): 0.7,
        ProbabilityKey(m1, False, frozenset([(x, True)])): 0.3,
        ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True), (m1, True)])): 0.4,
        ProbabilityKey(m2, True, frozenset([(x, True), (m1, False)])): 0.3,
        ProbabilityKey(m2, False, frozenset([(x, True), (m1, False)])): 0.7,
    })
    missing = ProbabilityKey(m1, True, frozenset([(x, True), (m2, True)]))
    val = _try_derive_via_bayes_inversion(missing, theta)
    # P(M2=T|X=T) = 0.6·0.7 + 0.3·0.3 = 0.51
    # P(M1=T|X=T, M2=T) = 0.6·0.7 / 0.51 = 0.823529...
    expected = 0.6 * 0.7 / (0.6 * 0.7 + 0.3 * 0.3)
    assert val is not None
    assert abs(val - expected) < 1e-9, (
        f"Bayes inversion got {val}, expected {expected}"
    )


def test_runtime_and_verifier_bayes_inversion_agree_byte_for_byte():
    """Iter 189 sync pin (parallel to iter 175): runtime
    _try_derive_via_bayes_inversion and verifier
    _verifier_derive_via_bayes_inversion MUST produce identical
    values on every theta. Independent implementations (V0-V5
    design goal) but R7 verification only works if they agree."""
    from themis.runtime.numeric_estimator import (
        _try_derive_via_bayes_inversion,
    )
    from themis.verifier.rules import (
        _verifier_derive_via_bayes_inversion,
    )

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    theta = Theta(entries={
        ProbabilityKey(m1, True, frozenset([(x, True)])): 0.7,
        ProbabilityKey(m1, False, frozenset([(x, True)])): 0.3,
        ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True), (m1, True)])): 0.4,
        ProbabilityKey(m2, True, frozenset([(x, True), (m1, False)])): 0.3,
        ProbabilityKey(m2, False, frozenset([(x, True), (m1, False)])): 0.7,
    })
    missing = ProbabilityKey(m1, True, frozenset([(x, True), (m2, True)]))
    runtime_val = _try_derive_via_bayes_inversion(missing, theta)
    verifier_val = _verifier_derive_via_bayes_inversion(missing, theta)
    assert runtime_val is not None and verifier_val is not None
    assert abs(runtime_val - verifier_val) < 1e-12, (
        f"Runtime and verifier Bayes inversion diverged: "
        f"runtime={runtime_val} verifier={verifier_val}"
    )
    expected = 0.6 * 0.7 / (0.6 * 0.7 + 0.3 * 0.3)
    assert abs(runtime_val - expected) < 1e-9


def test_bayes_inversion_returns_none_when_flip_unavailable():
    """If P(A | reduced_given, target) is missing AND not derivable,
    Bayes can't help — returns None."""
    from themis.runtime.numeric_estimator import (
        _try_derive_via_bayes_inversion,
    )

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    # Sparse theta: only the inner P(M1|X)
    theta = Theta(entries={
        ProbabilityKey(m1, True, frozenset([(x, True)])): 0.7,
        ProbabilityKey(m1, False, frozenset([(x, True)])): 0.3,
    })
    missing = ProbabilityKey(m1, True, frozenset([(x, True), (m2, True)]))
    val = _try_derive_via_bayes_inversion(missing, theta)
    assert val is None


def test_runtime_and_verifier_marginalization_agree_byte_for_byte():
    """Iter 175 sync pin: themis.runtime.numeric_estimator's
    _try_derive_via_marginalization and themis.verifier.rules's
    _verifier_derive_via_marginalization MUST produce identical
    values on every theta. They are independent implementations
    (V0-V5 design goal) but R7 verification only works if they
    agree.

    iter 172/173 introduced both as a paired set; this pin catches
    silent drift if either is refactored without the other."""
    from themis.runtime.numeric_estimator import (
        _try_derive_via_marginalization,
    )
    from themis.verifier.rules import _verifier_derive_via_marginalization

    x, y, z1, z2 = _A("x"), _A("y"), _A("z1"), _A("z2")

    # Two-deep marginalization theta (matches disjoint-Y fixture)
    theta = Theta(entries={
        ProbabilityKey(z1, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(z1, False, frozenset([(x, True)])): 0.4,
        ProbabilityKey(z2, True, frozenset([(x, True), (z1, True)])): 0.5,
        ProbabilityKey(z2, False, frozenset([(x, True), (z1, True)])): 0.5,
        ProbabilityKey(z2, True, frozenset([(x, True), (z1, False)])): 0.3,
        ProbabilityKey(z2, False, frozenset([(x, True), (z1, False)])): 0.7,
        ProbabilityKey(y, True, frozenset([(x, True), (z1, True), (z2, True)])): 0.9,
        ProbabilityKey(y, True, frozenset([(x, True), (z1, True), (z2, False)])): 0.7,
        ProbabilityKey(y, True, frozenset([(x, True), (z1, False), (z2, True)])): 0.5,
        ProbabilityKey(y, True, frozenset([(x, True), (z1, False), (z2, False)])): 0.2,
    })
    missing = ProbabilityKey(
        target_atom=y, target_value=True,
        given=frozenset([(x, True)]),
    )
    runtime_val = _try_derive_via_marginalization(missing, theta)
    verifier_val = _verifier_derive_via_marginalization(missing, theta)
    assert runtime_val is not None and verifier_val is not None
    assert abs(runtime_val - verifier_val) < 1e-12, (
        f"Runtime and verifier marginalization helpers diverged: "
        f"runtime={runtime_val} verifier={verifier_val}"
    )
    # Hand-computed reference from iter 148/172 fixture
    assert abs(runtime_val - 0.596) < 1e-9


def test_direct_lookup_wins_over_marginalization():
    """Iter 174 sanity pin: when theta has BOTH the direct CPT
    P(Y|X) AND the joint family P(Y|X,Z) + P(Z|X), the direct
    value is used. estimate_formula's miss path only triggers when
    direct lookup returns None — so a present direct value short-
    circuits before the marginalization fallback runs.

    User intent: if they supplied a direct P(Y|X), trust it (even
    if it'd be inconsistent with the joint-family marginal). Themis
    doesn't auto-detect inconsistencies between user-supplied CPTs;
    that's not its contract."""
    from themis.runtime.numeric_estimator import (
        ProbabilityRefExpr,
        ValuedAtom,
        estimate_formula,
    )

    x, y, z = _A("x"), _A("y"), _A("z")
    # Direct P(Y=True|X=True) = 0.5 (different from what marginalization
    # would give: 0.6·0.8 + 0.4·0.4 = 0.64).
    theta = Theta(entries={
        ProbabilityKey(y, True, frozenset([(x, True)])): 0.5,
        ProbabilityKey(y, True, frozenset([(x, True), (z, True)])): 0.8,
        ProbabilityKey(y, True, frozenset([(x, True), (z, False)])): 0.4,
        ProbabilityKey(z, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(z, False, frozenset([(x, True)])): 0.4,
    })
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=True),
        given=(ValuedAtom(atom=x, value=True),),
    )
    val = estimate_formula(expr, theta)
    # Direct value 0.5 wins; marginalization 0.64 is bypassed
    assert val == 0.5
