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


def test_iter_199_dsep_guard_refuses_when_independence_violated():
    """Iter 199: marginal-independence fallback with graph-aware
    d-separation guard refuses when target ⊥ extras | reduced
    doesn't hold. Closes iter 195's documented silent-wrong risk
    for chain DAG (X→M1→M2 with M1 → M2 making them dependent)."""
    from themis.runtime.numeric_estimator import (
        _try_marginal_independence_lookup,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])  # CHAIN — M1→M2
    bi = frozenset()  # No bidirected
    theta = Theta(entries={
        # Marginal-only P(M2|X) — user didn't supply chain CPT P(M2|X, M1)
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    # Without graph: trust user (iter 193 contract)
    v_nograph = _try_marginal_independence_lookup(missing, theta)
    assert v_nograph == 0.6

    # With graph: refuse (M1 → M2 means NOT independent given X)
    v_withgraph = _try_marginal_independence_lookup(
        missing, theta, graph=g, bidirected=bi,
    )
    assert v_withgraph is None, (
        "iter 199 d-sep guard should refuse for chain DAG"
    )


def test_iter_199_dsep_guard_allows_when_independence_holds():
    """Iter 199: when target ⊥ extras | reduced DOES hold (parallel
    multi-mediator case), the guard lets the marginal pass through."""
    from themis.runtime.numeric_estimator import (
        _try_marginal_independence_lookup,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    # Parallel: X→M1, X→M2, NO edge M1↔M2 (or M1→M2)
    g.add_edges_from([(x, m1), (x, m2)])
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))
    # Both M1 and M2 are children of X, no edge between them →
    # M1 ⊥ M2 | X by d-separation. Guard should allow.
    v = _try_marginal_independence_lookup(
        missing, theta, graph=g, bidirected=bi,
    )
    assert v == 0.6


def test_runtime_and_verifier_marginal_independence_agree():
    """Iter 194 sync pin: runtime and verifier marginal-independence
    lookups MUST produce identical values. Independent
    implementations preserved per V0-V5; R7 needs agreement."""
    from themis.runtime.numeric_estimator import (
        _try_marginal_independence_lookup,
    )
    from themis.verifier.rules import (
        _verifier_marginal_independence_lookup,
    )

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    # Theta has marginal P(M2|X) but not P(M2|X, M1)
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    # Demand: P(M2=True | X=True, M1=True)
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))
    runtime_val = _try_marginal_independence_lookup(missing, theta)
    verifier_val = _verifier_marginal_independence_lookup(missing, theta)
    assert runtime_val == 0.6
    assert runtime_val == verifier_val


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


def test_iter_200_verifier_marginal_independence_lookup_with_graph_refuses():
    """Iter 200: verifier-side d-sep guard mirror. Without the fix,
    verifier helper accepted graph kwargs but call sites in
    _evaluate_formula / _verifier_derive_via_marginalization passed
    nothing, so the guard was dead code. This test pins that when
    the verifier's helper IS called with a chain DAG + marginal
    theta, it refuses (matches runtime iter 199 behavior)."""
    from themis.verifier.rules import (
        _verifier_marginal_independence_lookup,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    v_no = _verifier_marginal_independence_lookup(missing, theta)
    assert v_no == 0.6
    v_yes = _verifier_marginal_independence_lookup(
        missing, theta, graph=g, bidirected=bi,
    )
    assert v_yes is None, (
        "iter 200 verifier d-sep guard should refuse for chain DAG"
    )


def test_iter_200_verifier_evaluate_formula_threads_graph_to_lookup():
    """Iter 200: _evaluate_formula propagates graph + bidirected to
    _verifier_marginal_independence_lookup. Without threading the
    verifier evaluator silently agreed with runtime's wrong number
    on chain DAG + marginal-only theta (iter 195 silent-wrong risk
    on the verifier side)."""
    from themis.verifier.rules import _evaluate_formula, _NonConcreteValue
    from themis.types import ProbabilityRefExpr, ValuedAtom
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=m2, value=True),
        given=(
            ValuedAtom(atom=x, value=True),
            ValuedAtom(atom=m1, value=True),
        ),
    )

    # Without graph: threads through, helper finds marginal P(M2|X)=0.6
    val_no_graph = _evaluate_formula(expr, theta, {})
    assert val_no_graph == 0.6

    # With chain-DAG graph: d-sep guard refuses, evaluator raises
    import pytest
    with pytest.raises(_NonConcreteValue):
        _evaluate_formula(expr, theta, {}, graph=g, bidirected=bi)


def test_iter_200_verifier_evaluate_formula_allows_parallel_mediator():
    """Iter 200: positive case — when graph DOES support the implied
    independence (parallel mediators with no edge between them),
    the verifier evaluator returns the marginal as expected."""
    from themis.verifier.rules import _evaluate_formula
    from themis.types import ProbabilityRefExpr, ValuedAtom
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    # Parallel paths: X→M1, X→M2, no edge between M1 and M2.
    g.add_edges_from([(x, m1), (x, m2)])
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=m2, value=True),
        given=(
            ValuedAtom(atom=x, value=True),
            ValuedAtom(atom=m1, value=True),
        ),
    )
    val = _evaluate_formula(expr, theta, {}, graph=g, bidirected=bi)
    assert val == 0.6


def test_iter_200_runtime_and_verifier_dsep_guard_agree():
    """Iter 200 sync pin (extends iter 194): runtime + verifier
    marginal-independence helpers must agree under the d-sep guard
    too — both refuse the chain DAG, both allow the parallel one."""
    from themis.runtime.numeric_estimator import (
        _try_marginal_independence_lookup,
    )
    from themis.verifier.rules import (
        _verifier_marginal_independence_lookup,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    g_chain = nx.DiGraph()
    g_chain.add_edges_from([(x, m1), (m1, m2)])
    rt_chain = _try_marginal_independence_lookup(
        missing, theta, graph=g_chain, bidirected=bi,
    )
    vf_chain = _verifier_marginal_independence_lookup(
        missing, theta, graph=g_chain, bidirected=bi,
    )
    assert rt_chain is None and vf_chain is None

    g_par = nx.DiGraph()
    g_par.add_edges_from([(x, m1), (x, m2)])
    rt_par = _try_marginal_independence_lookup(
        missing, theta, graph=g_par, bidirected=bi,
    )
    vf_par = _verifier_marginal_independence_lookup(
        missing, theta, graph=g_par, bidirected=bi,
    )
    assert rt_par == 0.6 and vf_par == 0.6
    assert rt_par == vf_par


# ----------------------------------------------------------------------
# Iter 202: d-sep guard refusal diagnostic — make user-facing message
# explain WHY the marginal-independence fallback refused (closes the
# VISION principle 5 gap iter 199-201 left in the diagnostic layer).
# ----------------------------------------------------------------------


def test_iter_202_runtime_diagnostic_explains_dsep_refusal():
    """Iter 202: when d-sep guard refuses an existing-but-graph-
    incompatible marginal, the diagnostic helper returns a structured
    explanation naming the candidate and the violated independence."""
    from themis.runtime.numeric_estimator import (
        _diagnose_marginal_independence_refusal,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])  # CHAIN — M1→M2
    bi = frozenset()
    theta = Theta(entries={
        # Marginal-only — would be wrong to use as P(M2|X, M1)
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    msg = _diagnose_marginal_independence_refusal(
        missing, theta, graph=g, bidirected=bi,
    )
    assert msg is not None, (
        "diagnostic must fire when d-sep guard refused an existing "
        "marginal candidate"
    )
    # Must name the candidate (P(m2=...|x=...)) and the violated
    # independence (M2 ⊥ {m1} | {x}).
    assert "P(m2=True|x=True)" in msg or "P(m2=True|x=True)" in msg.replace(" ", "")
    assert "m1" in msg
    assert "d-separation" in msg or "d-sep" in msg


def test_iter_202_runtime_diagnostic_silent_when_no_refusal():
    """Iter 202: diagnostic returns None when no candidate was refused
    — either no marginal in theta at all, or graph supports the
    independence (parallel-mediator allows the fallback). The caller's
    generic 'Theta 中缺条目' message is the right surface in those
    cases."""
    from themis.runtime.numeric_estimator import (
        _diagnose_marginal_independence_refusal,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    bi = frozenset()
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    # No marginal in theta — nothing to refuse.
    theta_empty = Theta(entries={})
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])
    assert _diagnose_marginal_independence_refusal(
        missing, theta_empty, graph=g, bidirected=bi,
    ) is None

    # Graph supports independence (parallel mediator) — guard wouldn't
    # have refused, so no diagnostic.
    theta_with = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
    })
    g_par = nx.DiGraph()
    g_par.add_edges_from([(x, m1), (x, m2)])
    assert _diagnose_marginal_independence_refusal(
        missing, theta_with, graph=g_par, bidirected=bi,
    ) is None

    # No graph → no guard → no diagnostic (caller's generic message
    # is fine; iter 193 trust contract applies).
    assert _diagnose_marginal_independence_refusal(
        missing, theta_with, graph=None, bidirected=None,
    ) is None


def test_iter_202_evaluate_raises_with_enriched_reason():
    """Iter 202: end-to-end through ``estimate_formula``: when the
    chain DAG + marginal-only theta hits the d-sep refusal, the raised
    InsufficientTheta carries a reason mentioning d-separation and the
    extras atom — not just the bare 'Theta 中缺条目'."""
    from themis.runtime.numeric_estimator import (
        InsufficientTheta,
        estimate_formula,
    )
    from themis.types import (
        ProbabilityRefExpr,
        ValuedAtom,
    )
    import networkx as nx
    import pytest

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    g = nx.DiGraph()
    g.add_edges_from([(x, m1), (m1, m2)])
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    # Ask for P(m2=True | x=True, m1=True).
    expr = ProbabilityRefExpr(
        target=ValuedAtom(atom=m2, value=True),
        given=(
            ValuedAtom(atom=x, value=True),
            ValuedAtom(atom=m1, value=True),
        ),
    )

    with pytest.raises(InsufficientTheta) as exc_info:
        estimate_formula(expr, theta, graph=g, bidirected=bi)

    reason = exc_info.value.reason
    # Generic prefix preserved (no behaviour break).
    assert "Theta 中缺条目" in reason
    # Enrichment present.
    assert "d-separation" in reason
    assert "m1" in reason


def test_iter_202_runtime_and_verifier_diagnostics_agree_on_refusal():
    """Iter 202 sync pin (parallel to iter 175/189/194/200): runtime
    and verifier diagnostic helpers must agree on whether a refusal
    fired. The exact message text differs (Chinese vs English by
    historical convention of each layer) but presence/absence must
    match — V0-V5 independence requires both layers reach the same
    structural conclusion about the same theta + graph."""
    from themis.runtime.numeric_estimator import (
        _diagnose_marginal_independence_refusal,
    )
    from themis.verifier.rules import (
        _verifier_diagnose_marginal_independence_refusal,
    )
    import networkx as nx

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    bi = frozenset()
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))

    # Chain DAG: both refuse → both produce diagnostic.
    g_chain = nx.DiGraph()
    g_chain.add_edges_from([(x, m1), (m1, m2)])
    rt_chain = _diagnose_marginal_independence_refusal(
        missing, theta, graph=g_chain, bidirected=bi,
    )
    vf_chain = _verifier_diagnose_marginal_independence_refusal(
        missing, theta, graph=g_chain, bidirected=bi,
    )
    assert (rt_chain is not None) and (vf_chain is not None)

    # Parallel DAG: both ALLOW (no refusal) → both return None.
    g_par = nx.DiGraph()
    g_par.add_edges_from([(x, m1), (x, m2)])
    rt_par = _diagnose_marginal_independence_refusal(
        missing, theta, graph=g_par, bidirected=bi,
    )
    vf_par = _verifier_diagnose_marginal_independence_refusal(
        missing, theta, graph=g_par, bidirected=bi,
    )
    assert rt_par is None and vf_par is None


def test_iter_204_probability_dispatch_threads_bidirected_for_dsep_guard():
    """Iter 204 — sync pin for the dispatch-fan-out hole found by
    L3 case 012 (Pearl 1995 smoking-tar-cancer chain).

    Pre-iter-204, ``_dispatch_probability`` accepted ``graph`` but
    NOT ``bidirected``, then forwarded with ``bidirected=None`` to
    ``_try_numeric``. The d-sep guard inside
    ``_try_marginal_independence_lookup`` short-circuits when
    ``bidirected is None`` (see the ``if graph is not None and
    bidirected is not None`` clause), so on the entire
    probability-query dispatch path the iter 199-201 guard was
    dormant: a chain DAG (S→T→C) with marginal-only theta P(C|S)
    and a query P(C|S,T) silently returned 0.18 (the substituted
    marginal) instead of refusing.

    iter 204 fixes _dispatch_probability to forward bidirected and
    the kernel-level call site to pass it. This test pins the
    end-to-end behaviour: the same chain + marginal + probability
    query goes through ``themis.run`` and lands on
    ``graph_theta_independence_mismatch`` with status
    ``needs_investigation``, not ``numerically_solved`` with value
    0.18.

    Effect-query d-sep was already covered by tests
    test_iter_199 / test_iter_202 / case 012 catches the parallel
    probability-query path that those tests didn't reach.
    """
    import themis

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "variable", "predicate": "smoking",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "tar",
             "domain": [True, False]},
            {"kind": "variable", "predicate": "lung_cancer",
             "domain": [True, False]},
            {"kind": "cause",
             "from": {"predicate": "smoking",
                      "args": [{"type": "const", "name": "p"}]},
             "to": {"predicate": "tar",
                    "args": [{"type": "const", "name": "p"}]}},
            {"kind": "cause",
             "from": {"predicate": "tar",
                      "args": [{"type": "const", "name": "p"}]},
             "to": {"predicate": "lung_cancer",
                    "args": [{"type": "const", "name": "p"}]}},
            {"kind": "probability",
             "target": {"atom": {"predicate": "lung_cancer",
                                 "args": [{"type": "const",
                                           "name": "p"}]},
                        "value": True},
             "given": [{"atom": {"predicate": "smoking",
                                 "args": [{"type": "const",
                                           "name": "p"}]},
                        "value": True}],
             "value": 0.18},
            {"kind": "probability",
             "target": {"atom": {"predicate": "lung_cancer",
                                 "args": [{"type": "const",
                                           "name": "p"}]},
                        "value": True},
             "given": [{"atom": {"predicate": "smoking",
                                 "args": [{"type": "const",
                                           "name": "p"}]},
                        "value": False}],
             "value": 0.013},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "probability",
                 "target": {"atom": {"predicate": "lung_cancer",
                                     "args": [{"type": "const",
                                               "name": "p"}]},
                            "value": True},
                 "given": [
                     {"atom": {"predicate": "smoking",
                               "args": [{"type": "const",
                                         "name": "p"}]},
                      "value": True},
                     {"atom": {"predicate": "tar",
                               "args": [{"type": "const",
                                         "name": "p"}]},
                      "value": True},
                 ]}},
        ],
    }

    out = themis.run(ast)
    res = out["results"][0]

    # Behaviour pin: silent-wrong path is closed.
    assert res["status"] == "needs_investigation", (
        "iter 204 regression: the chain × marginal-only probability "
        "query is silently substituting the marginal again"
    )
    assert res.get("numeric_result") is None, (
        "iter 204 regression: no numeric_result should be emitted "
        "when the d-sep guard refuses the substitution"
    )

    # Structured-channel pin: the dedicated iter 203 kind fires, not
    # the generic missing_distribution.
    kinds = {g["kind"] for g in res["data_gap_report"]["gaps"]}
    assert "graph_theta_independence_mismatch" in kinds, (
        "iter 204 regression: d-sep refusal in probability dispatch "
        "did not route to the dedicated gap kind"
    )
    assert "missing_distribution" not in kinds, (
        "iter 204: when the d-sep refusal signature is present, the "
        "generic missing_distribution must be suppressed (per iter 203)"
    )


def test_bare_marginal_is_missing_distribution_not_graph_mismatch():
    """Real-usage probe 2026-06-15 — a supplied bare marginal P(Y) must
    NOT be diagnosed as a graph-vs-CPT contradiction.

    A real user asks for the causal effect of coffee on depression with a
    textbook confounder (stress → coffee, stress → depression,
    coffee → depression) and supplies only the outcome BASE RATE
    P(depression)=0.25 — entirely consistent with the DAG. The backdoor
    formula demands P(depression|coffee,stress); the bare marginal cannot
    substitute (correct), but supplying a marginal is NEVER a claim that
    depression ⊥ {coffee,stress}, so it is not a graph-CPT mismatch.

    Pre-fix, the d-sep refusal diagnostic fired on the empty-conditioning
    candidate and routed to graph_theta_independence_mismatch (important)
    whose headline remedy was "delete the confounding edge" — backwards
    advice that would validate the naive unadjusted estimate. The fix
    skips empty-conditioning candidates so this lands on the honest
    missing_distribution (blocking): "supply P(Y|X,Z), adjust for the
    confounder". Contrast test_iter_204_… above, where the refused
    candidate P(C|S) keeps a NON-empty conditioning set and correctly
    stays a mismatch.
    """
    import themis

    def atom(p, name="me"):
        return {"predicate": p, "args": [{"type": "const", "name": name}]}

    def cause(s, d):
        return {"kind": "cause", "from": atom(s), "to": atom(d)}

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            cause("stress", "coffee"),
            cause("stress", "depression"),
            cause("coffee", "depression"),
            {"kind": "probability",
             "target": {"atom": atom("depression"), "value": True},
             "given": [], "value": 0.25},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": atom("depression"), "value": True},
                       "intervention": {"atom": atom("coffee"), "value": True},
                       "given": []}},
        ],
    }

    out = themis.run(ast)
    res = out["results"][0]
    kinds = {g["kind"] for g in res["data_gap_report"]["gaps"]}

    assert "graph_theta_independence_mismatch" not in kinds, (
        "a bare marginal P(Y) was mis-diagnosed as a graph-CPT "
        "contradiction — empty conditioning is not an independence claim"
    )
    blocking = next(
        g for g in res["data_gap_report"]["gaps"]
        if g["kind"] == "missing_distribution"
    )
    assert blocking["severity"] == "blocking"
    assert blocking["blocks"] == "point_estimate"
    # The honest gap names the confounder-adjusted conditional to collect.
    assert "stress" in blocking["description"]
