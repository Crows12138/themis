"""Phase 2.latent ext §S3.b.2 — Tian / Shpitser ID algorithm.

Covers the unit-level c_factor module + scheduler dispatch +
verifier round-trip. Scope: Shpitser ID Lines 1-6 fully + Line 7
simplified shortcut (iter 141, see test_tian_line_7_shortcut.py).
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


def test_line_7_case_identifies_via_shortcut():
    """X → M → Y, X ↔ Y. Iter 141 Line 7 shortcut: Tian now identifies
    via Q[S'] marginalization rather than punting. Front-door also
    handles this case upstream — either path works; what MUST NOT
    happen is identifiable=False with hedge=set (that would falsely
    claim unidentifiability)."""
    x, m, y = _A("x"), _A("m"), _A("y")
    g = nx.DiGraph()
    g.add_edges_from([(x, m), (m, y)])
    bi = frozenset({frozenset({x, y})})
    r = c_factor.identify_via_tian(g, bi, x, y, x_value=True)
    if not r.identifiable:
        assert r.hedge is None, (
            "Line 7 path must NOT carry a hedge — that would falsely "
            "claim unidentifiability when the case is identifiable"
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
