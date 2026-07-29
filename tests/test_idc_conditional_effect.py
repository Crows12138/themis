"""Phase 2 — conditional general-ID (IDC) NUMERIC end for effect queries.

Phase 1 (fix b742fbd) stopped the bleed: a conditional effect query
``P(Y | do(X), Z)`` on an ADMG that is NOT back-door identified — front-door /
Tian-identifiable in its unconditional margin — used to silently drop `given`
and ship the MARGINAL ``P(Y | do(X))`` labelled numerically_solved. Phase 1 made
it refuse honestly. Phase 2 (this) turns that refusal into the CORRECT
conditional number via Shpitser-Pearl IDC: the Rule-2 exchange moves exchangeable
Z into the do-set, the remainder normalizes as ``ID(Y∪Z_rem, X') / ID(Z_rem, X')``,
and the query's Y / Z values are bound before evaluation against theta.

Two independent oracles:
  * a latent-SCM ground truth (Z survives the exchange → genuine fraction), the
    conditional recovered to 1e-9;
  * a hand-computable front-door + effect-modifier program (Z exchanges away →
    non-fraction), the conditional an exact rational.

Plus the anti-silent-wrong assertion (conditional ≠ marginal) and two tamper
vectors the independent verifier must reject.
"""
from __future__ import annotations

import copy
import itertools

import networkx as nx
import pytest

import themis
from themis.runtime import c_factor
from themis.runtime.numeric_estimator import Theta, enumerate_keys
from themis.types import (
    Atom,
    ConstTerm,
    FractionExpr,
    ProbabilityRefExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
)


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


# ---------------------------------------------------------------------------
# Oracle 1 — latent-SCM ground truth, genuine FRACTION (Z survives exchange).
# Graph Z→X→M→Y with X↔Y and Z↔Y (two latent confounders). The Z↔Y latent keeps
# Z m-connected to Y under do(X), so Z is NOT exchanged and the estimand is a
# true ratio whose value depends on z. Identical SCM to the numerically-proven
# test_idc_fraction_matches_latent_scm_ground_truth.
# ---------------------------------------------------------------------------

_B = [True, False]
_pU, _pW = 0.3, 0.6


def _pZ1(w): return 0.8 if w else 0.2
def _pX1(zz, u): return 0.7 if (zz ^ u) else 0.25
def _pM1(xx): return 0.9 if xx else 0.15
def _pY1(mm, u, w): return min(max(0.2 + 0.5 * mm + 0.15 * u + 0.1 * w, 0.0), 1.0)


def _scm_cell(u, w, zz, xx, mm, yy):
    return ((_pU if u else 1 - _pU) * (_pW if w else 1 - _pW)
            * (_pZ1(w) if zz else 1 - _pZ1(w))
            * (_pX1(zz, u) if xx else 1 - _pX1(zz, u))
            * (_pM1(xx) if mm else 1 - _pM1(xx))
            * (_pY1(mm, u, w) if yy else 1 - _pY1(mm, u, w)))


_OBS = {
    (zz, xx, mm, yy): sum(_scm_cell(u, w, zz, xx, mm, yy) for u in _B for w in _B)
    for zz, xx, mm, yy in itertools.product(_B, _B, _B, _B)
}
_IDX = {"z": 0, "x": 1, "m": 2, "y": 3}


def _obs_cond(tp, tv, given):
    def match(k, c):
        return all(k[_IDX[p]] == v for p, v in c.items())
    nu = sum(p for k, p in _OBS.items() if match(k, {**given, tp: tv}))
    de = sum(p for k, p in _OBS.items() if match(k, given))
    return nu / de if de > 0 else 0.0


def _scm_ground_truth(zv):
    """True P(Y=1 | do(X=1), Z=zv): do(X=1) replaces X's mechanism, Z's
    distribution untouched, latents enumerated."""
    num = sum((_pU if u else 1 - _pU) * (_pW if w else 1 - _pW)
              * (_pZ1(w) if zv else 1 - _pZ1(w))
              * (_pM1(True) if mm else 1 - _pM1(True)) * _pY1(mm, u, w)
              for u in _B for w in _B for mm in _B)
    den = sum((_pU if u else 1 - _pU) * (_pW if w else 1 - _pW)
              * (_pZ1(w) if zv else 1 - _pZ1(w)) for u in _B for w in _B)
    return num / den


def _scm_marginal():
    return sum((_pU if u else 1 - _pU) * (_pW if w else 1 - _pW)
               * (_pZ1(w) if zz else 1 - _pZ1(w))
               * (_pM1(True) if mm else 1 - _pM1(True)) * _pY1(mm, u, w)
               for u in _B for w in _B for zz in _B for mm in _B)


def _scm_theta_prob_statements():
    """Build the observational conditionals the IDC estimand references (from the
    SCM's observational joint) as `probability` statements. Enumerating the
    identify-side formula's keys is legitimate test SETUP — the assertion under
    test is the independent EFFECT path plus verifier."""
    x, m, y, z = _A("x"), _A("m"), _A("y"), _A("z")
    g = nx.DiGraph()
    g.add_edges_from([(z, x), (x, m), (m, y)])
    bi = frozenset({frozenset({x, y}), frozenset({z, y})})
    idc = c_factor.identify_via_idc(g, bi, x, y, (z,), x_value=True)
    assert idc.identifiable and idc.is_fraction

    def bind(node, yv, zv):
        def fix(va):
            if va.value is None and va.atom == y:
                return ValuedAtom(atom=y, value=yv)
            if va.value is None and va.atom == z:
                return ValuedAtom(atom=z, value=zv)
            return va
        if isinstance(node, ProbabilityRefExpr):
            return ProbabilityRefExpr(target=fix(node.target),
                                      given=tuple(fix(gg) for gg in node.given))
        if isinstance(node, ProductExpr):
            return ProductExpr(terms=tuple(bind(t, yv, zv) for t in node.terms))
        if isinstance(node, SumExpr):
            return SumExpr(bind=node.bind, over=node.over, body=bind(node.body, yv, zv))
        if isinstance(node, FractionExpr):
            return FractionExpr(numerator=bind(node.numerator, yv, zv),
                                denominator=bind(node.denominator, yv, zv))
        return node

    th = Theta()
    for zv in _B:
        for yv in _B:
            for part in (idc.formula.numerator, idc.formula.denominator):
                for k in enumerate_keys(bind(part, yv, zv), th):
                    th.entries[k] = _obs_cond(
                        k.target_atom.predicate, k.target_value,
                        {a.predicate: v for a, v in k.given})
    stmts = []
    for k, p in th.entries.items():
        given = [{"atom": _atom(a.predicate), "value": v} for a, v in k.given]
        stmts.append({
            "kind": "probability",
            "target": {"atom": _atom(k.target_atom.predicate), "value": k.target_value},
            "given": given, "value": p,
        })
    return stmts


def _scm_program(zval):
    st = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "domain": [True, False]},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
    ] + _scm_theta_prob_statements() + [
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [{"atom": _atom("z"), "value": zval}]}},
    ]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": st}


def test_idc_conditional_effect_fraction_matches_scm_ground_truth():
    """The genuine-fraction conditional effect is recovered to 1e-9 against the
    latent-SCM ground truth, for both z values, and the derivation carries the
    three IDC witnesses; the verifier accepts."""
    for zval in (True, False):
        prog = _scm_program(zval)
        r = themis.run(prog)["results"][0]
        assert r["status"] == "numerically_solved"
        assert r["formula"]["kind"] == "fraction"
        assert r["numeric_result"]["value"] == pytest.approx(
            _scm_ground_truth(zval), abs=1e-9)
        rules = [s["rule"] for s in r["derivation"]["steps"]]
        assert "idc_rule2_exchange" in rules
        assert "identify_via_idc" in rules
        assert "idc_formula_ast" in rules
        themis.verify(prog, r)


def test_idc_conditional_effect_fraction_differs_by_z_and_from_marginal():
    """Anti-silent-wrong: the two conditionals differ from each other AND from
    the marginal — exactly the estimand Phase 1 refused rather than approximate
    with the marginal. Phase 2 ships the right one."""
    v_true = themis.run(_scm_program(True))["results"][0]["numeric_result"]["value"]
    v_false = themis.run(_scm_program(False))["results"][0]["numeric_result"]["value"]
    marginal = _scm_marginal()
    assert abs(v_true - v_false) > 0.05
    assert abs(v_true - marginal) > 0.02
    assert abs(v_false - marginal) > 0.02


# ---------------------------------------------------------------------------
# Oracle 2 — hand-computable, NON-fraction (Z exchanges away).
# Front-door X→M→Y with X↔Y latent + an effect-modifier C→Y (a c·m interaction so
# the conditional differs from the marginal). After do(X), C reaches Y only via
# the (severed) direct edge, so C exchanges into the do-set and the estimand
# collapses to a front-door-style sum. P(Y=1|do(X=1),C=c) is an exact rational.
# ---------------------------------------------------------------------------


def _p(tp, tv, given, val):
    return {"kind": "probability",
            "target": {"atom": _atom(tp), "value": tv},
            "given": [{"atom": _atom(g), "value": v} for g, v in given],
            "value": val}


def _modifier_program(given):
    st = [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "c", "domain": [True, False]},
        {"kind": "variable", "predicate": "m", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
        {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
        {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
        _p("x", True, [], 0.5), _p("x", False, [], 0.5),
        _p("c", True, [], 0.5), _p("c", False, [], 0.5),
    ]
    pm = {(True, True): 0.8, (False, True): 0.2, (True, False): 0.3, (False, False): 0.7}
    for xv in (True, False):
        for mv in (True, False):
            st.append(_p("m", mv, [("x", xv)], pm[(mv, xv)]))
    for cv in (True, False):
        for mv in (True, False):
            for xv in (True, False):
                pr = 0.1 + 0.3 * mv + 0.2 * (mv and cv) + 0.1 * cv
                st.append(_p("y", True, [("c", cv), ("m", mv), ("x", xv)], pr))
                st.append(_p("y", False, [("c", cv), ("m", mv), ("x", xv)], 1 - pr))
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom(g), "value": v} for g, v in given]}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": st}


def test_idc_conditional_effect_nonfraction_hand_computed():
    """Z-exchanges-away (non-fraction) conditional, an exact rational.

    P(Y=1|do(X=1),C=c) = Σ_m P(m|X=1)·P(Y=1|m,C=c)
      C=1: 0.8·0.7 + 0.2·0.2 = 0.60
      C=0: 0.8·0.4 + 0.2·0.1 = 0.34
    while the marginal P(Y=1|do(X=1)) = 0.47 — the conditional is neither."""
    r1 = themis.run(_modifier_program([("c", True)]))["results"][0]
    assert r1["status"] == "numerically_solved"
    assert r1["numeric_result"]["value"] == pytest.approx(0.60, abs=1e-9)
    rules = [s["rule"] for s in r1["derivation"]["steps"]]
    assert "identify_via_idc" in rules and "idc_formula_ast" in rules
    themis.verify(_modifier_program([("c", True)]), r1)

    r0 = themis.run(_modifier_program([("c", False)]))["results"][0]
    assert r0["numeric_result"]["value"] == pytest.approx(0.34, abs=1e-9)
    themis.verify(_modifier_program([("c", False)]), r0)


def test_marginal_still_routes_front_door_not_idc():
    """Regression: the UNCONDITIONAL margin of the same program routes through
    front-door (not IDC) and equals 0.47 — IDC is the conditional path only."""
    r = themis.run(_modifier_program([]))["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_result"]["value"] == pytest.approx(0.47, abs=1e-9)
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert "identify_via_front_door" in rules
    assert "identify_via_idc" not in rules


# ---------------------------------------------------------------------------
# Tamper — the independent verifier must reject forged numbers and forged binds.
# ---------------------------------------------------------------------------


def test_verify_rejects_forged_conditional_number():
    """Corrupt the computed value to the marginal (0.47) throughout the
    derivation. The verifier independently re-evaluates the IDC estimand
    against theta, recomputes 0.60, and rejects."""
    from themis.verifier.errors import VerificationError

    prog = _modifier_program([("c", True)])
    r = themis.run(prog)["results"][0]
    forged = copy.deepcopy(r)
    for st in forged["derivation"]["steps"]:
        if st["rule"] == "formula_evaluation":
            st["output"] = 0.47
        if st["rule"] == "numeric_result":
            st["output"]["value"] = 0.47
    forged["numeric_result"]["value"] = 0.47
    with pytest.raises(VerificationError):
        themis.verify(prog, forged)


def test_conditional_iv_effect_does_not_ship_unconditional_late():
    """Adjacent silent-drop, IV path: IV-in-effect runs BEFORE the IDC branch in
    the conditional routing. Its Wald LATE is UNCONDITIONAL (looks up P(Y|Z),
    P(X|Z) with no `given` term), so a conditional query with monotonicity + a
    valid instrument used to ship that LATE and silently drop `given`. It must
    now fall through (to IDC / honest refusal) — the unconditional control still
    ships the LATE, proving the guard is conditional-specific."""
    def at(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    def _gr(p, v):
        return {"atom": at(p), "value": v}

    def _pr(tp, tv, gv, val):
        return {"kind": "probability", "target": _gr(tp, tv),
                "given": [_gr(g, v) for g, v in gv], "value": val}

    base = [
        {"kind": "variable", "predicate": "iv", "domain": [True, False]},
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "c", "domain": [True, False]},
        {"kind": "cause", "from": at("iv"), "to": at("x")},
        {"kind": "cause", "from": at("x"), "to": at("y")},
        {"kind": "cause", "from": at("c"), "to": at("y")},
        {"kind": "bidirected", "left": at("x"), "right": at("y")},
    ]
    for zt in (True, False):
        base.append(_pr("y", True, [("iv", zt)], 0.6 if zt else 0.4))
        base.append(_pr("x", True, [("iv", zt)], 0.7 if zt else 0.3))

    def prog(given):
        q = {"kind": "query", "id": "q", "query": {
            "kind": "effect", "intervention": _gr("x", True), "target": _gr("y", True),
            "given": given, "assumptions": {"monotonicity": "non_decreasing"}}}
        return {"version": "0.1",
                "domain": {"objects": [{"kind": "object", "name": "me"}]},
                "statements": base + [q]}

    cond = themis.run(prog([_gr("c", True)]))["results"][0]
    assert cond["status"] == "needs_investigation"
    assert cond.get("numeric_result") is None  # never the unconditional 0.50

    uncond = themis.run(prog([]))["results"][0]
    assert uncond["status"] == "numerically_solved"
    assert uncond["numeric_result"]["value"] == pytest.approx(0.5, abs=1e-9)
    rules = [s["rule"] for s in uncond["derivation"]["steps"]]
    assert "iv_wald_numeric_evaluate" in rules


def test_verify_rejects_tampered_bound_formula():
    """Replace the idc_formula_ast output (the value-bound estimand) with its own
    unbound input (Y / Z left as holes). The verifier re-binds the query values
    independently and rejects the mismatch."""
    from themis.verifier.errors import VerificationError

    prog = _modifier_program([("c", True)])
    r = themis.run(prog)["results"][0]
    forged = copy.deepcopy(r)
    for st in forged["derivation"]["steps"]:
        if st["rule"] == "idc_formula_ast":
            st["output"] = copy.deepcopy(st["inputs"]["unbound_formula"])
    with pytest.raises(VerificationError):
        themis.verify(prog, forged)


def test_idc_is_reached_without_latent_confounding():
    """A conditional query on a plain DAG reaches IDC too.

    The two layers used to disagree about whether this query is even
    identifiable: ``themis.run`` refused it as ``not_identifiable`` while
    ``themis.estimate`` identified it via IDC, produced the number, and had
    that envelope ACCEPTED by the independent verifier. The cause was
    structural rather than theoretical — the identification pass carried two
    copies of its strategy ladder, and IDC sat in the copy guarded on latent
    confounding, which conditional identification has nothing to do with.

    ``x -> m -> y`` conditioned on the mediator: no adjustment set survives
    (every candidate is a descendant of x) and front-door needs an
    unconditioned query, so nothing before IDC can reach it.
    """
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom("m"), "value": True}],
            }},
        ],
    }
    r = themis.run(prog)["results"][0]
    kinds = {m["kind"] for m in (r.get("missing_information") or [])}
    names = {m["name"] for m in (r.get("missing_information") or [])}
    # Identified but unparameterised — a data gap, NOT a structural refusal.
    assert kinds == {"parameter"}, r.get("missing_information")
    assert "identification:not_identifiable" not in names

