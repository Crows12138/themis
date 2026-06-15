"""Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID algorithm.

Covers the unit-level c_factor module + scheduler dispatch +
verifier round-trip. Scope: Shpitser ID Lines 1-6. Line 7 (recursive
symbolic substitution Q[S']) returns None and the scheduler falls
through to needs_investigation — see the punt-case test below.
Iter 141 attempted a `_build_q_factor` shortcut but iter 143 traced
that the produced formula was mathematically wrong (atoms in
`state.x` get hardcoded literal do-values, breaking inner sums) and
reverted. See wall.md iter 143 retraction note.
"""
from __future__ import annotations

import networkx as nx
import pytest

import themis
from themis.runtime import c_factor
from themis.types import Atom, ConstTerm


def _A(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _atom_dict(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# ============================================ unit: identify_via_tian


def test_pure_dag_chain_yields_tian_product_form():
    """X → M → Y, no bidirected. Tian gives the product Σ_M P(M|X) ·
    P(Y|X,M). Backdoor with empty adjustment also works (and would win
    in the scheduler), but the unit-level Tian primitive should still
    succeed independently."""
    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    r = c_factor.identify_via_tian(g, frozenset(), x, y, x_value=True)
    assert r.identifiable is True
    assert r.formula is not None


def test_bow_arc_is_unidentifiable_via_hedge():
    """X → Y, X ↔ Y. Canonical hedge — Shpitser Line 5 fires."""
    x, y = _A("x"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, y)])
    bi = frozenset({frozenset({x, y})})
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.identifiable is False
    assert r.hedge is not None
    assert {x, y} <= r.hedge


def test_disjoint_y_component_identifiable_directly():
    """X → Z1, X → Z2, Z1 ↔ Z2, Z1 → Y, Z2 → Y. cc_full =
    ({X}, {Z1, Z2}, {Y}); after removing X the c-component containing
    Y splits cleanly. Tian Line 4 product form succeeds."""
    x, z1, z2, y = _A("x"), _A("z1"), _A("z2"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, z1), (x, z2), (z1, y), (z2, y)])
    bi = frozenset({frozenset({z1, z2})})
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.identifiable is True
    assert r.formula is not None


def test_line_7_front_door_variant_now_identifies():
    """X → M → Y, X ↔ Y. Shpitser Line 7 (S={Y} ⊊ S'={X,Y}).
    identify_via_tian now reproduces the front-door formula
    Σ_m P(m|do x) · Σ_x' P(x') P(y|x',m) instead of punting. The crucial
    detail pinned here: the inner P(y|x',m) conditions on the SUMMED x'
    (a VarRef bound by Σ_x'), NOT the literal do-value — that literal
    collapse was the iter-143 retraction bug."""
    from themis.types import SumExpr, ProductExpr, ProbabilityRefExpr, VarRef
    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bi = frozenset({frozenset({x, y})})
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    assert r.identifiable is True
    assert r.hedge is None

    # outer Σ_m
    f = r.formula
    assert isinstance(f, SumExpr) and f.over == m
    body = f.body
    assert isinstance(body, ProductExpr) and len(body.terms) == 2

    # term 1: P(m | x=True) — X at the literal do-value
    mref = next(
        t for t in body.terms
        if isinstance(t, ProbabilityRefExpr) and t.target.atom == m
    )
    assert any(gv.atom == x and gv.value is True for gv in mref.given)

    # term 2: inner Σ_x' of P(x') · P(y | x', m)
    inner = next(t for t in body.terms if isinstance(t, SumExpr))
    assert inner.over == x
    assert isinstance(inner.body, ProductExpr)
    yref = next(
        t for t in inner.body.terms
        if isinstance(t, ProbabilityRefExpr) and t.target.atom == y
    )
    # y conditions on the SUMMED x' (a VarRef), not the literal True
    xref_in_y = next(gv for gv in yref.given if gv.atom == x)
    assert isinstance(xref_in_y.value, VarRef), (
        "inner x' must be a bound sum variable, not the literal do-value "
        "(the iter-143 degenerate-collapse bug)"
    )


# ============================================ end-to-end: scheduler


def test_e2e_bow_arc_returns_structurally_solved_unidentifiable():
    """Scheduler-level: bow arc routes through Tian and surfaces a
    definitive unidentifiable answer with verifier round-trip."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("y")},
            {
                "kind": "bidirected",
                "left": _atom_dict("x"),
                "right": _atom_dict("y"),
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "target": _atom_dict("y"),
                    "intervention": {"atom": _atom_dict("x"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is False
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "tian_c_decomposition" in rules
    assert "tian_hedge_witness" in rules
    # Independent verifier replay must accept.
    themis.verify(ast, r)
    # Gap report carries the unidentifiable signal with the hedge wording.
    report = r["data_gap_report"]
    blocking = next(
        g for g in report["gaps"]
        if g["kind"] == "unidentifiable_no_admissible_set"
    )
    assert blocking["severity"] == "blocking"
    assert "hedge" in blocking["description"]


def test_e2e_three_bidirected_hedge():
    """X → M → Y with X ↔ Y AND X ↔ M. The double bidirected pulls X,
    M, Y into one c-component → hedge."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("m"), "to": _atom_dict("y")},
            {
                "kind": "bidirected",
                "left": _atom_dict("x"), "right": _atom_dict("y"),
            },
            {
                "kind": "bidirected",
                "left": _atom_dict("x"), "right": _atom_dict("m"),
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "target": _atom_dict("y"),
                    "intervention": {"atom": _atom_dict("x"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is False
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "tian_hedge_witness" in rules


def test_e2e_backdoor_still_wins_when_available():
    """Pure DAG with a confounder: backdoor is tried first and succeeds.
    Tian must NOT preempt — the kernel takes the simplest available
    identification path."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("w"), "to": _atom_dict("x")},
            {"kind": "cause", "from": _atom_dict("w"), "to": _atom_dict("y")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "target": _atom_dict("y"),
                    "intervention": {"atom": _atom_dict("x"), "value": True},
                    "given": [],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_backdoor" in rules
    assert "tian_c_decomposition" not in rules


# ============================================ verifier rule unit tests


def test_verifier_rejects_hedge_claim_without_actual_hedge():
    """Tampering: claim tian_hedge_witness for a graph with no hedge.
    Verifier's independent c_components replay must reject."""
    from themis.types import (
        Atom as _Atom, ConstTerm as _CT,
        DerivationStep, IdentifyQuery, Intervention, StepRef,
        StructuralResult,
    )
    from themis.verifier import VerificationContext, verify_identify
    from themis.verifier.errors import VerificationError

    x, y = _Atom(predicate="x", args=(_CT(name="me"),)), \
           _Atom(predicate="y", args=(_CT(name="me"),))
    g = nx.DiGraph()
    g.add_edges_from([(x, y)])

    q = IdentifyQuery(
        target=y,
        intervention=Intervention(atom=x, value=True),
        given=(),
    )
    derivation = (
        DerivationStep(
            rule="tian_c_decomposition",
            inputs={"graph": g, "x": x, "y": y},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="tian_hedge_witness",
            inputs={"decomposition": StepRef(step_id="s1")},
            output=StructuralResult(value=False),
            step_id="s2",
        ),
    )
    # No bidirected → no actual hedge. Verifier must reject.
    ctx = VerificationContext(graph=g, query=q, bidirected=frozenset())
    with pytest.raises(VerificationError):
        verify_identify(derivation, ctx, StructuralResult(value=False))
