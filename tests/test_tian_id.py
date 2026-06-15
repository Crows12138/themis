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


# ============================================ unit: identify_via_idc


def test_idc_exchange_collapses_to_plain_intervention():
    """Z → X → Y, query P(Y | do(X), Z). After do(X), Z reaches Y only
    through the now-severed X, so Rule 2 exchanges Z into the do-set and
    the conditional collapses to the plain interventional P(Y | do(X')) —
    no fraction. The whole conditioning set is consumed."""
    from themis.input.semantic_validator import validate_formula
    x, y, z = _A("x"), _A("y"), _A("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    r = c_factor.identify_via_idc(g, frozenset(), x, y, (z,), x_value=True)
    assert r.identifiable is True
    assert r.is_fraction is False
    assert r.exchanged == frozenset({z})
    assert r.remaining_z == frozenset()
    validate_formula(r.formula)


def test_idc_fraction_when_z_stays_conditioned():
    """X → Y, Z → X, Z ↔ Y. Query P(Y | do(X), Z). The latent Z↔Y keeps
    Y and Z m-connected even in G_{X̄, Z_}, so Z cannot be exchanged — IDC
    must emit the normalized ratio ID(Y,Z | do X) / ID(Z | do X) as a
    FractionExpr, both halves identifiable via the c-factor."""
    from themis.types import FractionExpr
    from themis.input.semantic_validator import validate_formula
    x, y, z = _A("x"), _A("y"), _A("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bi = frozenset({frozenset({z, y})})
    r = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    assert r.identifiable is True
    assert r.is_fraction is True
    assert r.remaining_z == frozenset({z})
    assert r.exchanged == frozenset()
    assert isinstance(r.formula, FractionExpr)
    validate_formula(r.formula)


def test_idc_intervention_value_only_on_x():
    """The do-value rides ONLY on X. Y and the conditioned Z are
    structural query-bound holes (value=None) — never the literal
    do-value. Guards the value-stamping invariant in _apply_idc_values."""
    from themis.types import FractionExpr, ProbabilityRefExpr, ValuedAtom, VarRef
    x, y, z = _A("x"), _A("y"), _A("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, y)])
    bi = frozenset({frozenset({z, y})})
    r = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    assert isinstance(r.formula, FractionExpr)

    # Collect every ValuedAtom in the formula and check value semantics.
    seen = {"x": [], "y": [], "z": []}

    def walk(node):
        from themis.types import ConstantExpr, ProductExpr, SumExpr
        if isinstance(node, ProbabilityRefExpr):
            for va in (node.target, *node.given):
                seen[va.atom.predicate].append(va.value)
        elif isinstance(node, ProductExpr):
            for t in node.terms:
                walk(t)
        elif isinstance(node, SumExpr):
            walk(node.body)
        elif isinstance(node, FractionExpr):
            walk(node.numerator)
            walk(node.denominator)

    walk(r.formula)
    # X always at the concrete do-value.
    assert seen["x"] and all(v is True for v in seen["x"])
    # Y and Z are query-bound holes (None) or summed (VarRef), never True.
    for pred in ("y", "z"):
        assert all(v is None or isinstance(v, VarRef) for v in seen[pred]), (
            f"{pred} carried a literal do-value — value leak"
        )


def test_idc_fraction_matches_latent_scm_ground_truth():
    """NUMERIC correctness, not just well-formedness. Graph: Z→X→M→Y with
    X↔Y and Z↔Y (two latent confounders). Query P(Y|do(X),Z) is genuinely
    fraction-shaped (Z survives the Rule-2 exchange). We build a concrete
    SCM with explicit latents U (X↔Y) and W (Z↔Y), compute the true
    P(Y=1|do(X=1),Z=z) by enumerating the latents, and confirm the IDC
    fraction — evaluated against the SCM's OBSERVATIONAL conditionals —
    reproduces it exactly. This is the check that caught the inner-Σ_x'
    degenerate-sum bug: structural validation, the schema, and the
    verifier all passed a numerically WRONG formula."""
    import itertools
    from themis.runtime.numeric_estimator import (
        Theta, estimate_formula, enumerate_keys,
    )
    from themis.types import (
        ValuedAtom, ProbabilityRefExpr, ProductExpr, SumExpr, FractionExpr,
    )
    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    B = [True, False]
    pU, pW = 0.3, 0.6

    def pZ1(w): return 0.8 if w else 0.2
    def pX1(zz, u): return 0.7 if (zz ^ u) else 0.25
    def pM1(xx): return 0.9 if xx else 0.15
    def pY1(mm, u, w): return min(max(0.2 + 0.5 * mm + 0.15 * u + 0.1 * w, 0.0), 1.0)

    def cell(u, w, zz, xx, mm, yy):
        return ((pU if u else 1 - pU) * (pW if w else 1 - pW)
                * (pZ1(w) if zz else 1 - pZ1(w))
                * (pX1(zz, u) if xx else 1 - pX1(zz, u))
                * (pM1(xx) if mm else 1 - pM1(xx))
                * (pY1(mm, u, w) if yy else 1 - pY1(mm, u, w)))

    # Observational joint P(z,x,m,y), latents summed out.
    obs = {
        (zz, xx, mm, yy): sum(cell(u, w, zz, xx, mm, yy) for u in B for w in B)
        for zz, xx, mm, yy in itertools.product(B, B, B, B)
    }
    idx = {"z": 0, "x": 1, "m": 2, "y": 3}

    def obs_cond(tp, tv, given):
        def match(k, c): return all(k[idx[p]] == v for p, v in c.items())
        nu = sum(p for k, p in obs.items() if match(k, {**given, tp: tv}))
        de = sum(p for k, p in obs.items() if match(k, given))
        return nu / de if de > 0 else 0.0

    def ground_truth(zv):
        # do(X=1): X's mechanism replaced; Z's distribution untouched.
        num = sum((pU if u else 1 - pU) * (pW if w else 1 - pW)
                  * (pZ1(w) if zv else 1 - pZ1(w))
                  * (pM1(True) if mm else 1 - pM1(True)) * pY1(mm, u, w)
                  for u in B for w in B for mm in B)
        den = sum((pU if u else 1 - pU) * (pW if w else 1 - pW)
                  * (pZ1(w) if zv else 1 - pZ1(w)) for u in B for w in B)
        return num / den

    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    r = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    assert r.is_fraction

    def bind(node, yv, zv):
        def fix(va):
            if va.value is None and va.atom == y:
                return ValuedAtom(atom=y, value=yv)
            if va.value is None and va.atom == z:
                return ValuedAtom(atom=z, value=zv)
            return va
        if isinstance(node, ProbabilityRefExpr):
            return ProbabilityRefExpr(
                target=fix(node.target), given=tuple(fix(gg) for gg in node.given))
        if isinstance(node, ProductExpr):
            return ProductExpr(terms=tuple(bind(t, yv, zv) for t in node.terms))
        if isinstance(node, SumExpr):
            return SumExpr(bind=node.bind, over=node.over, body=bind(node.body, yv, zv))
        if isinstance(node, FractionExpr):
            return FractionExpr(
                numerator=bind(node.numerator, yv, zv),
                denominator=bind(node.denominator, yv, zv))
        return node

    for zv in B:
        th = Theta()
        for yv in B:
            for f in (bind(r.formula.numerator, yv, zv),
                      bind(r.formula.denominator, yv, zv)):
                for k in enumerate_keys(f, th):
                    th.entries[k] = obs_cond(
                        k.target_atom.predicate, k.target_value,
                        {a.predicate: v for a, v in k.given})
        n1 = estimate_formula(bind(r.formula.numerator, True, zv), th)
        n0 = estimate_formula(bind(r.formula.numerator, False, zv), th)
        den = estimate_formula(bind(r.formula.denominator, True, zv), th)
        # Fraction reproduces the SCM's true interventional conditional.
        assert abs(n1 / den - ground_truth(zv)) < 1e-9
        # Normalization identity: Σ_y numerator == denominator.
        assert abs((n1 + n0) - den) < 1e-9


# ============================================ end-to-end: scheduler


def test_e2e_idc_fraction_routes_and_verifies():
    """Scheduler-level FRACTION case. Z→X→M→Y, X↔Y, Z↔Y. The latent Z↔Y
    keeps Z m-connected to Y even after do(X), so Z is NOT exchanged — the
    estimand stays a genuine ratio. Routes to IDC (ADMG backdoor-with-given
    can't block the direct X↔Y) and the verifier accepts the fraction."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("z"), "to": _atom_dict("x")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("m"), "to": _atom_dict("y")},
            {"kind": "bidirected", "left": _atom_dict("x"), "right": _atom_dict("y")},
            {"kind": "bidirected", "left": _atom_dict("z"), "right": _atom_dict("y")},
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "target": _atom_dict("y"),
                    "intervention": {"atom": _atom_dict("x"), "value": True},
                    "given": [_atom_dict("z")],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is True
    assert r["formula"]["kind"] == "fraction"
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_idc" in rules
    themis.verify(ast, r)


# ============================================ legacy scheduler tests


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


def test_e2e_idc_conditional_routes_and_verifies():
    """Scheduler-level conditional identification. X → M → Y with X ↔ Y
    (front-door confounder) and Z → X. Query P(Y | do(X), Z).

    Backdoor-with-given cannot block the direct X↔Y latent edge, and
    front-door / IV / plain-Tian are gated on an empty conditioning set —
    so this routes to IDC. The Rule-2 exchange moves the now-irrelevant Z
    (after do(X), Z reaches Y only through the severed X) into the do-set,
    collapsing the conditional to the front-door effect. Verifier must
    independently re-derive the exchange and accept."""
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("z"), "to": _atom_dict("x")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("m"), "to": _atom_dict("y")},
            {
                "kind": "bidirected",
                "left": _atom_dict("x"), "right": _atom_dict("y"),
            },
            {
                "kind": "query", "id": "q",
                "query": {
                    "kind": "identify",
                    "target": _atom_dict("y"),
                    "intervention": {"atom": _atom_dict("x"), "value": True},
                    "given": [_atom_dict("z")],
                },
            },
        ],
    }
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["structural_result"]["value"] is True
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "idc_rule2_exchange" in rules
    assert "identify_via_idc" in rules
    # Independent verifier replay (re-derives the exchange) must accept.
    themis.verify(ast, r)


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


def test_verifier_rejects_idc_fraction_when_exchange_consumes_all_z():
    """Tampering: a graph where the Rule-2 exchange provably consumes the
    whole conditioning set (Z→X→M→Y, X↔Y — after do(X), Z reaches Y only
    through the severed X, so Z exchanges away). The forged derivation
    presents a FractionExpr, claiming Z survived. The verifier replays the
    exchange independently, finds z_remaining=∅, and rejects the
    shape mismatch — catching a runtime that emitted the wrong estimand."""
    from themis.types import (
        Atom as _Atom, ConstTerm as _CT,
        DerivationStep, IdentifyQuery, Intervention, StepRef,
        StructuralResult, ValuedAtom, ProbabilityRefExpr, FractionExpr,
    )
    from themis.verifier import VerificationContext, verify_identify
    from themis.verifier.errors import VerificationError

    def at(p):
        return _Atom(predicate=p, args=(_CT(name="me"),))
    x, mm, yy, zz = at("x"), at("m"), at("y"), at("z")
    g = nx.DiGraph()
    g.add_edges_from([(zz, x), (x, mm), (mm, yy)])
    bi = frozenset({frozenset({x, yy})})

    q = IdentifyQuery(
        target=yy,
        intervention=Intervention(atom=x, value=True),
        given=(zz,),
    )
    # A well-formed but unwarranted fraction (P(y)/P(y)).
    py = ProbabilityRefExpr(target=ValuedAtom(atom=yy, value=None), given=())
    forged = FractionExpr(numerator=py, denominator=py)
    derivation = (
        DerivationStep(
            rule="idc_rule2_exchange",
            inputs={"graph": g, "x": x, "y": yy},
            output=True,
            step_id="s1",
        ),
        DerivationStep(
            rule="identify_via_idc",
            inputs={"exchange": StepRef(step_id="s1"), "formula": forged},
            output=StructuralResult(value=True),
            step_id="s2",
        ),
    )
    ctx = VerificationContext(graph=g, query=q, bidirected=bi)
    with pytest.raises(VerificationError):
        verify_identify(derivation, ctx, StructuralResult(value=True))


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
