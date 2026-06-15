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
        g, bi, x=x, x_value=True, y=y, given=(z,), formula=idc.formula)
    assert r.status == "match", r.detail


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
