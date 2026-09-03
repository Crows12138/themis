"""Phase 15 §A4 — semantic verification backbone.

The probe is the method-agnostic answer to "does this identification
formula compute the TRUE interventional quantity?" — the question the
per-method structural verifier rules never asked, which is how Phase 14
shipped a numerically-wrong IDC fraction that passed every structural
check. These tests pin: the probe accepts correct backdoor / front-door
/ IDC formulas, rejects a numerically-wrong one, and — wired into
verify_identify — rejects a shape-valid-but-wrong fraction that the
structural IDC rule alone waves through.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime import c_factor
from themis.verifier import semantic_probe as sp
from themis.types import (
    Atom, ConstTerm, ValuedAtom, VarRef, BindDecl,
    ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr,
)


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


# ============================================ unit: the probe


def test_probe_accepts_correct_backdoor():
    """W→X, W→Y, X→Y. The backdoor formula Σ_w P(Y|X,w)P(w) computes the
    true do-quantity — the probe must say so."""
    w, x, y = _A("w"), _A("x"), _A("y")
    g = nx.DiGraph([(w, x), (w, y), (x, y)])
    formula = SumExpr(
        bind=BindDecl(name="t_w"), over=w,
        body=ProductExpr(terms=(
            ProbabilityRefExpr(
                target=ValuedAtom(atom=y, value=None),
                given=(ValuedAtom(atom=x, value=True),
                       ValuedAtom(atom=w, value=VarRef("t_w")))),
            ProbabilityRefExpr(
                target=ValuedAtom(atom=w, value=VarRef("t_w")), given=()),
        )))
    r = sp.probe_identify_formula(
        g, frozenset(), x=x, x_value=True, y=y, given=(), formula=formula)
    assert r.status == "match", r.detail


def test_probe_rejects_confounded_naive_formula():
    """Same graph, but the naive P(Y|X=True) ignores the confounder W —
    it is NOT the interventional quantity. The probe must catch it."""
    w, x, y = _A("w"), _A("x"), _A("y")
    g = nx.DiGraph([(w, x), (w, y), (x, y)])
    naive = ProbabilityRefExpr(
        target=ValuedAtom(atom=y, value=None),
        given=(ValuedAtom(atom=x, value=True),))
    r = sp.probe_identify_formula(
        g, frozenset(), x=x, x_value=True, y=y, given=(), formula=naive)
    assert r.status == "mismatch"


def test_probe_accepts_correct_idc_fraction():
    """Z→X→M→Y, X↔Y, Z↔Y. The IDC fraction is the genuine
    P(Y|do(X),Z) — probe confirms numerically (the Phase-14 regression)."""
    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    g = nx.DiGraph([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    idc = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    assert idc.is_fraction
    r = sp.probe_identify_formula(
        g, bi, x=x, x_value=True, y=y,
        given=(ValuedAtom(atom=z, value=None),), formula=idc.formula)
    assert r.status == "match", r.detail


def test_probe_asks_about_the_value_the_question_conditions_on():
    """A conditioned variable reaches the probe as a name AND, where the
    question names one, the value its estimand is about — the same sentence
    ``y_values`` says about the outcome.

    An effect answer's estimand is already bound at one Z value. Asked
    about the other it returns that same number, while the truth moves, and
    the probe reads the difference as a mismatch — the identify-side
    reading applied to a question that had said which value it meant. So
    the loop ranges over a conditioned variable's domain exactly when the
    question leaves it open, and over the named value when it does not.
    """
    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    g = nx.DiGraph([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    idc = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    bound_at_true = c_factor.bind_idc_values(idc.formula, {z: True})

    def ask(given):
        return sp.probe_identify_formula(
            g, bi, x=x, x_value=True, y=y, given=given,
            formula=bound_at_true, y_values=(True,))

    assert ask((ValuedAtom(atom=z, value=True),)).status == "match"
    ranged_over_both = ask((ValuedAtom(atom=z, value=None),))
    assert ranged_over_both.status == "mismatch"
    assert "z(me)=False" in ranged_over_both.detail


def test_probe_accepts_correct_front_door():
    """X→M→Y, X↔Y. The front-door / Tian formula is the true effect."""
    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph([(x, m), (m, y)])
    bi = frozenset({frozenset({x, y})})
    tian = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    r = sp.probe_identify_formula(
        g, bi, x=x, x_value=True, y=y, given=(), formula=tian.formula)
    assert r.status == "match", r.detail


# ============================================ integration: verify_identify


def test_verify_identify_rejects_numerically_wrong_idc_fraction():
    """The Phase-14-class bug, caught at the verifier this time. A fraction
    with the RIGHT shape (matches the replayed exchange) but WRONG contents
    (P(z)/P(z) ≡ 1) passes the structural IDC rule — the semantic backbone
    must reject it, because P(Y|do(X),Z) ≠ 1."""
    from themis.types import (
        DerivationStep, IdentifyQuery, Intervention, StepRef, StructuralResult,
    )
    from themis.verifier import VerificationContext, verify_identify
    from themis.verifier.errors import VerificationError

    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    g = nx.DiGraph([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    q = IdentifyQuery(
        target=y, intervention=Intervention(atom=x, value=True), given=(z,))

    pz = ProbabilityRefExpr(target=ValuedAtom(atom=z, value=None), given=())
    wrong = FractionExpr(numerator=pz, denominator=pz)  # ≡ 1, shape-valid
    derivation = (
        DerivationStep(rule="idc_rule2_exchange",
                       inputs={"graph": g, "x": x, "y": y},
                       output=True, step_id="s1"),
        DerivationStep(rule="identify_via_idc",
                       inputs={"exchange": StepRef(step_id="s1"), "formula": wrong},
                       output=StructuralResult(value=True), step_id="s2"),
    )
    ctx = VerificationContext(graph=g, query=q, bidirected=bi)
    with pytest.raises(VerificationError):
        verify_identify(derivation, ctx, StructuralResult(value=True))


def test_verify_identify_accepts_correct_idc_fraction():
    """Control: the genuine IDC fraction passes the same backbone."""
    from themis.types import (
        DerivationStep, IdentifyQuery, Intervention, StepRef, StructuralResult,
    )
    from themis.verifier import VerificationContext, verify_identify

    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    g = nx.DiGraph([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    q = IdentifyQuery(
        target=y, intervention=Intervention(atom=x, value=True), given=(z,))
    idc = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    derivation = (
        DerivationStep(rule="idc_rule2_exchange",
                       inputs={"graph": g, "x": x, "y": y},
                       output=True, step_id="s1"),
        DerivationStep(rule="identify_via_idc",
                       inputs={"exchange": StepRef(step_id="s1"),
                               "formula": idc.formula},
                       output=StructuralResult(value=True), step_id="s2"),
    )
    ctx = VerificationContext(graph=g, query=q, bidirected=bi)
    verify_identify(derivation, ctx, StructuralResult(value=True))  # no raise


# ============================================ grouped Theta rebuild


def _napkin_chain(n_mediators: int):
    """Pearl's napkin (W→Z→X→Y, W↔X, W↔Y) extended with a mediator chain
    between X and Y — the canonical family that forces the full nested-ID
    Line-7 path. |V| = 4 + n_mediators."""
    w, z, x, y = _A("w"), _A("z"), _A("x"), _A("y")
    meds = [_A(f"m{i}") for i in range(n_mediators)]
    chain = [w, z, x] + meds + [y]
    g = nx.DiGraph(list(zip(chain, chain[1:])))
    bi = frozenset({frozenset({w, x}), frozenset({w, y})})
    return g, bi, x, y


def test_theta_from_scm_matches_enumeration_reference():
    """`_theta_from_scm` (variable-elimination marginals) must reproduce
    the conditional the brute-force per-key reference (`_observational_cond`)
    computes for EVERY key — VE is a pure speedup, not an approximation.
    Checked on a genuine nested-ID estimand whose formula references
    hundreds of keys but only |V| distinct conditioning atom-sets.
    (Tolerance, not bit-exact: VE re-associates the same mass sums.)"""
    import random

    g, bi, x, y = _napkin_chain(3)  # |V| = 7
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.formula is not None
    bound = sp._bind_holes(r.formula, {y: True})

    scm = sp._sample_scm(g, bi, {}, random.Random(12345))
    theta = sp._theta_from_scm(scm, bound, g, bi)

    keys = sp.enumerate_keys(bound, sp.Theta())
    ref = {}
    for key in keys:
        given = {a: v for a, v in key.given}
        ref[key] = sp._observational_cond(
            scm, key.target_atom, key.target_value, given)

    assert set(theta.entries) == set(ref)
    for key, val in ref.items():
        assert abs(theta.entries[key] - val) <= 1e-12

    # what VE (and the grouping) exploits: distinct conditioning atom-sets
    # are linear in |V|, while the key count is exponential.
    n_groups = len({
        (k.target_atom, frozenset(a for a, _ in k.given)) for k in keys
    })
    assert n_groups <= g.number_of_nodes()
    assert len(keys) > 5 * n_groups


def test_true_do_ve_matches_enumeration():
    """The VE ground truth ``_true_do`` must equal the brute-force
    ``_true_do_enum`` EXACTLY (float tol) — it is the numeric oracle the
    whole probe rests on, so any drift is a correctness bug. Checked across
    mediator counts and a second (non-chain) family, unconditional and
    conditioned, both Y values, several SCMs."""
    import random

    families = [_napkin_chain(k) for k in (0, 2, 4)]
    # a non-chain family: Z→X→M→Y with Z→Y and X↔Y
    z2, m2, x2, y2 = _A("z2"), _A("m2"), _A("x"), _A("y")
    g2 = nx.DiGraph([(z2, x2), (x2, m2), (m2, y2), (z2, y2)])
    families.append((g2, frozenset({frozenset({x2, y2})}), x2, y2))

    for g, bi, x, y in families:
        others = [n for n in g.nodes() if n not in (x, y)]
        for seed in range(1, 5):
            scm = sp._sample_scm(g, bi, {}, random.Random(seed))
            for yv in (True, False):
                assert abs(sp._true_do_enum(scm, x, True, y, yv, {})
                           - sp._true_do(scm, x, True, y, yv, {})) < 1e-9
                if others:
                    gvar = others[0]
                    for gv in (True, False):
                        assert abs(
                            sp._true_do_enum(scm, x, True, y, yv, {gvar: gv})
                            - sp._true_do(scm, x, True, y, yv, {gvar: gv})) < 1e-9


def test_full_nested_id_identifies_with_ve_probe():
    """A genuine nested-ID case at the raised Line-7 cap (|V| = 14, well past
    the original cap of 8/10) identifies in-config with a numerically-sound
    formula, exercising the full variable-elimination pipeline end to end — the
    ground-truth do-quantity, the observational-conditional theta, the
    referenced-key collection, AND the formula evaluation are all VE now. With
    the recursive walk the probe self-check crashed ~33% at these sizes; VE
    makes it crash-free and fast (~80ms)."""
    g, bi, x, y = _napkin_chain(10)  # |V| = 14 = _FULL_LINE7_MAX_NODES
    assert g.number_of_nodes() == c_factor._FULL_LINE7_MAX_NODES == 14
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.identifiable
    assert r.formula is not None
