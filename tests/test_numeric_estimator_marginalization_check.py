"""The marginalization helpers, and the guard that decides when they
may substitute.

The kernel auto-derives a missing CPT from a richer joint family it was
given. Whether it MAY is a separate question from whether it CAN, and
the difference is the whole subject here: substituting P(Y|S) for a
demanded P(Y|given) asserts a conditional independence, which is either
entailed by the declared graph or is a silently wrong answer.
"""
from __future__ import annotations

from themis.runtime.numeric_estimator import (
    ProbabilityKey,
    Theta,
    can_derive_via_marginalization,
)
from themis.types import Atom, ConstTerm
from themis import gaps as _gaps


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
    """Marginalization recurses through 3 levels (P(Y|X)
    → P(Y|X,Z1) → P(Y|X,Z1,Z2) → P(Y|X,Z1,Z2,Z3) leaf-direct).
    The depth ≤ 3 limit is generous enough for typical ADMG
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
    """Chain-mediator front-door demands P(M1|X, M2)
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


def test_the_dsep_guard_refuses_when_independence_is_violated():
    """The marginal-independence fallback, with the graph-aware
    d-separation guard, refuses when target ⊥ extras | reduced does
    not hold — the chain DAG (X→M1→M2, where M1 → M2 makes them
    dependent given X), which is silently wrong without it."""
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

    # Without a graph there is nothing to check against
    v_nograph = _try_marginal_independence_lookup(missing, theta)
    assert v_nograph == 0.6

    # With graph: refuse (M1 → M2 means NOT independent given X)
    v_withgraph = _try_marginal_independence_lookup(
        missing, theta, graph=g, bidirected=bi,
    )
    assert v_withgraph is None, (
        "the d-sep guard should refuse for a chain DAG"
    )


def test_the_dsep_guard_allows_when_independence_holds():
    """When target ⊥ extras | reduced DOES hold (the parallel
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
    """A sync pin: runtime and verifier marginal-independence
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
    """A sync pin, the Bayes-inversion twin of the marginalization
    one below: runtime
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
    """A sync pin: themis.runtime.numeric_estimator's
    _try_derive_via_marginalization and themis.verifier.rules's
    _verifier_derive_via_marginalization MUST produce identical
    values on every theta. They are independent implementations
    (V0-V5 design goal) but R7 verification only works if they
    agree.

    The two are a paired set by design — two independent
    transcriptions of the same derivation — and this pin catches
    either being refactored without the other."""
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
    # Hand-computed reference for this fixture
    assert abs(runtime_val - 0.596) < 1e-9


def test_direct_lookup_wins_over_marginalization():
    """A sanity pin: when theta has BOTH the direct CPT
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


def test_the_verifiers_marginal_independence_lookup_refuses_too():
    """The verifier-side mirror of the d-sep guard. The helper can
    accept graph kwargs while the call sites in
    _evaluate_formula / _verifier_derive_via_marginalization passed
    nothing, so the guard was dead code. This test pins that when
    the verifier's helper IS called with a chain DAG + marginal
    theta, it refuses — matching the runtime."""
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
        "the verifier d-sep guard should refuse for a chain DAG"
    )


def test_the_verifiers_evaluator_threads_the_graph_to_the_lookup():
    """_evaluate_formula propagates graph + bidirected to
    _verifier_marginal_independence_lookup. Unthreaded, the verifier
    evaluator silently agrees with the runtime's wrong number on a
    chain DAG + marginal-only theta — two independent evaluators
    making the same substitution, which is the one case where their
    agreement proves nothing."""
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


def test_the_verifiers_evaluator_allows_a_parallel_mediator():
    """The positive case — when the graph DOES support the implied
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


def test_runtime_and_verifier_dsep_guards_agree():
    """A sync pin over the guard itself: runtime + verifier
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
# The refusal diagnostic: the user-facing message has to say WHY the
# marginal-independence fallback refused. A guard that refuses without
# saying so leaves the caller reading "supply more theta", which is
# the wrong repair for a graph that contradicts the CPTs they gave.
# ----------------------------------------------------------------------


def test_the_runtime_diagnostic_explains_a_dsep_refusal():
    """When the d-sep guard refuses an existing-but-graph-
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

    facts = _diagnose_marginal_independence_refusal(
        missing, theta, graph=g, bidirected=bi,
    )
    assert facts is not None, (
        "diagnostic must fire when d-sep guard refused an existing "
        "marginal candidate"
    )
    # The facts name the candidate (P(m2=...|x=...)) and the independence
    # the graph does not carry (M2 ⊥ {m1} | {x}). The words for them are
    # the reader's; what the runtime hands over is the statement.
    assert facts["have"].replace(" ", "") == "P(m2=True|x=True)"
    assert facts["variable"] == "m2"
    assert facts["extras"] == "m1"
    assert facts["conditioning"] == "x"


def test_the_runtime_diagnostic_is_silent_when_nothing_refused():
    """The diagnostic returns None when no candidate was refused
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

    # No graph → no guard → no diagnostic; the caller's generic
    # message is the right one when nothing was considered.
    assert _diagnose_marginal_independence_refusal(
        missing, theta_with, graph=None, bidirected=None,
    ) is None


def test_evaluate_raises_with_the_enriched_reason():
    """End to end through ``estimate_formula``: when the
    chain DAG + marginal-only theta hits the d-sep refusal, the raised
    InsufficientTheta names the species that says the graph contradicts
    the marginal, and carries the extras atom — not the plain shortfall,
    whose repair ('supply more theta') is the wrong one here."""
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

    exc = exc_info.value
    assert str(exc.need) == "graph_contradicts_supplied_marginal"
    assert exc.details["extras"] == "m1"
    # And the sentence the reader assembles from it still opens on the
    # shortfall and goes on to say why more theta is not the repair.
    from themis import gaps
    assert exc.details["key"] == "P(m2=True|m1=True,x=True)"
    said = gaps.said(gaps.fields(exc.need, **exc.details))
    assert "Theta 中缺条目" in said
    assert "m1" in said


def test_runtime_and_verifier_diagnostics_agree_on_a_refusal():
    """A sync pin, the diagnostic twin of the others in this file:
    runtime
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


def test_probability_dispatch_threads_bidirected_for_the_dsep_guard():
    """A sync pin for the dispatch fan-out, which L3 case 012 (Pearl
    1995 smoking-tar-cancer chain) is the regression for.

    ``_dispatch_probability`` can accept ``graph`` but
    NOT ``bidirected``, and then forward ``bidirected=None`` to
    ``_try_numeric``. The d-sep guard inside
    ``_try_marginal_independence_lookup`` short-circuits when
    ``bidirected is None`` (see the ``if graph is not None and
    bidirected is not None`` clause), so the guard goes dormant
    across the entire probability-query dispatch path:
    a chain DAG (S→T→C) with marginal-only theta P(C|S)
    and a query P(C|S,T) silently returned 0.18 (the substituted
    marginal) instead of refusing.

    _dispatch_probability forwards bidirected and the kernel-level
    call site passes it. This test pins the
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
        "regression: the chain × marginal-only probability "
        "query is silently substituting the marginal again"
    )
    assert res.get("numeric_result") is None, (
        "regression: no numeric_result should be emitted "
        "when the d-sep guard refuses the substitution"
    )

    # Structured-channel pin: the dedicated kind fires, not the
    # generic missing_distribution.
    kinds = {g["kind"] for g in res["data_gap_report"]["gaps"]}
    assert "graph_theta_independence_mismatch" in kinds, (
        "regression: d-sep refusal in probability dispatch "
        "did not route to the dedicated gap kind"
    )
    assert "missing_distribution" not in kinds, (
        "when the d-sep refusal signature is present, the "
        "generic missing_distribution must be suppressed"
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
    assert "stress" in _gaps.described(blocking)
