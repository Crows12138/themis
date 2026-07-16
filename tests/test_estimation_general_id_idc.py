"""Conditional general-ID (IDC) plug-in on DATA — the pandas end of the
frontier whose theta end shipped in Phase 2 (test_idc_conditional_effect).

The theta path evaluates a conditional PROBABILITY ``P(Y=y | do(X=x), Z=z)``
against supplied probability statements. This path is the DataFrame sibling:
``estimate_general_id_conditional_ate`` identifies ``P(Y | do(X), Z=z)`` via
Shpitser-Pearl IDC and evaluates it on discrete data by the SAME
non-parametric plug-in the unconditional c-factor estimator uses — returning a
conditional-ATE risk difference taken WITHIN the queried ``Z=z`` stratum::

    ATE(z) = P(Y=y_hi | do(X=x_hi), Z=z) − P(Y=y_hi | do(X=x_lo), Z=z)

Two DGPs, both realised as data:

* An EFFECT-MODIFICATION DGP (front-door X→M→Y with an effect modifier C→Y and
  an X↔Y latent). C exchanges into the do-set (non-fraction estimand). The
  conditional ATE genuinely differs across the modifier — ATE(C=1)=0.30,
  ATE(C=0)=0.18 — and both differ from the marginal ATE 0.24. This is the
  anti-silent-wrong signal a CONTRAST reveals: an additive graph would hide it.

* A latent-SCM DGP (Z→X→M→Y, X↔Y, Z↔Y). Z SURVIVES the exchange, so the
  estimand is a genuine FractionExpr — this exercises the VE fraction path on
  data end-to-end. Its mechanism is additive, so its conditional ATE is
  z-invariant (0.375); the point is that the plug-in recovers it on data.

Ground truth is enumerated from each SCM (self-checking, no hardcoded target).
The verifier depth mirrors the unconditional data path: the IDC identifiability
is independently re-confirmed (general_id_criterion re-runs identify_via_idc);
the plug-in arithmetic is the shared data-refit ceiling (metadata audit).
"""
from __future__ import annotations

import copy
import itertools

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result
from themis.estimation.general_id import (
    GeneralIdEstimate,
    estimate_general_id_conditional_ate,
)
from themis.estimation.dose_response import EstimatorFailure
from themis.input.syntactic_validator import validate_ast
from themis.input.semantic_validator import validate_program
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime import structural_solver
from themis.types import Atom, ConstTerm, ValuedAtom


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


_B = (False, True)


# ===========================================================================
# DGP 1 — effect modification (non-fraction; C exchanges into the do-set).
# Front-door X→M→Y, modifier C→Y (with an m·c interaction), X↔Y latent (=U).
# ===========================================================================

_pU_mod, _pC_mod, _betaU = 0.5, 0.5, 0.2


def _mod_pX1(u): return 0.8 if u else 0.2
def _mod_pM1(x): return 0.8 if x else 0.2
def _mod_pY1(m, c, u):
    return 0.1 + 0.3 * m + 0.2 * (m and c) + 0.1 * c + _betaU * u


def _mod_data(n, seed=0):
    rng = np.random.default_rng(seed)
    U = rng.random(n) < _pU_mod
    C = rng.random(n) < _pC_mod
    X = rng.random(n) < np.where(U, _mod_pX1(1), _mod_pX1(0))
    M = rng.random(n) < np.where(X, _mod_pM1(1), _mod_pM1(0))
    pY = np.array([_mod_pY1(int(m), int(c), int(u)) for m, c, u in zip(M, C, U)])
    Y = rng.random(n) < pY
    return pd.DataFrame({"x": X, "c": C, "m": M, "y": Y})


def _mod_true_cond_prob(xv, cv):
    """True P(Y=1 | do(X=xv), C=cv) = P(Y=1 | do(X=xv), do(C=cv)) (Rule-2)."""
    def pM(m): return _mod_pM1(xv) if m else 1 - _mod_pM1(xv)
    def pU(u): return _pU_mod if u else 1 - _pU_mod
    return sum(pM(m) * pU(u) * _mod_pY1(m, cv, u)
               for m in (0, 1) for u in (0, 1))


def _mod_true_cond_ate(cv):
    return _mod_true_cond_prob(1, cv) - _mod_true_cond_prob(0, cv)


def _mod_true_marginal_ate():
    def pC(c): return _pC_mod if c else 1 - _pC_mod
    return sum(pC(c) * _mod_true_cond_ate(c) for c in (0, 1))


def _mod_ast(given):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "c", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("c"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom(g), "value": v} for g, v in given],
            }},
        ],
    }


# ===========================================================================
# DGP 2 — latent SCM, genuine FRACTION (Z survives the exchange).
# Z→X→M→Y with X↔Y (=U) and Z↔Y (=W). Identical params to the theta test.
# ===========================================================================

_pU_f, _pW_f = 0.3, 0.6


def _f_pZ1(w): return 0.8 if w else 0.2
def _f_pX1(z, u): return 0.7 if (z ^ u) else 0.25
def _f_pM1(x): return 0.9 if x else 0.15
def _f_pY1(m, u, w): return min(max(0.2 + 0.5 * m + 0.15 * u + 0.1 * w, 0.0), 1.0)


def _frac_data(n, seed=0):
    rng = np.random.default_rng(seed)
    U = rng.random(n) < _pU_f
    W = rng.random(n) < _pW_f
    Z = rng.random(n) < np.where(W, _f_pZ1(1), _f_pZ1(0))
    pX = np.array([_f_pX1(int(z), int(u)) for z, u in zip(Z, U)])
    X = rng.random(n) < pX
    M = rng.random(n) < np.where(X, _f_pM1(1), _f_pM1(0))
    pY = np.array([_f_pY1(int(m), int(u), int(w)) for m, u, w in zip(M, U, W)])
    Y = rng.random(n) < pY
    return pd.DataFrame({"z": Z, "x": X, "m": M, "y": Y})


def _frac_true_cond_prob(xv, zv):
    def pU(u): return _pU_f if u else 1 - _pU_f
    def pW(w): return _pW_f if w else 1 - _pW_f
    def pZ(w): return _f_pZ1(w) if zv else 1 - _f_pZ1(w)
    def pM(m): return _f_pM1(xv) if m else 1 - _f_pM1(xv)
    num = sum(pU(u) * pW(w) * pZ(w) * pM(m) * _f_pY1(m, u, w)
              for u in (0, 1) for w in (0, 1) for m in (0, 1))
    den = sum(pU(u) * pW(w) * pZ(w) for u in (0, 1) for w in (0, 1))
    return num / den


def _frac_true_cond_ate(zv):
    return _frac_true_cond_prob(1, zv) - _frac_true_cond_prob(0, zv)


def _frac_graph():
    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
        ],
    }
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    graph = project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    x = next(n for n in graph.nodes() if n.predicate == "x")
    y = next(n for n in graph.nodes() if n.predicate == "y")
    z = next(n for n in graph.nodes() if n.predicate == "z")
    return graph, bidirected, x, y, z


def _frac_ast(zval):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "bidirected", "left": _atom("z"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom("z"), "value": zval}],
            }},
        ],
    }


# ============================================ recovery vs SCM truth (unit)


def test_conditional_ate_recovers_effect_modification_on_data():
    """The conditional ATE differs by the modifier C, and the plug-in recovers
    each stratum's true value from data — the whole point of a conditional
    estimand a marginal ATE would flatten."""
    graph, bi, x, y, c = _mod_graph()
    df = _mod_data(12000, seed=0)
    for cv in (True, False):
        est = estimate_general_id_conditional_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            given=(ValuedAtom(atom=c, value=cv),), ci_bootstrap=0,
        )
        assert isinstance(est, GeneralIdEstimate)
        assert est.method == "general_id_idc_plugin"
        assert est.given == (("c", cv),)
        true_ate = _mod_true_cond_ate(int(cv))
        assert abs(est.point - true_ate) < 0.035, (
            f"C={cv}: plug-in {est.point} vs true {true_ate}"
        )
    # the two strata genuinely differ (effect modification), and from marginal
    assert abs(_mod_true_cond_ate(1) - _mod_true_cond_ate(0)) > 0.1
    assert abs(_mod_true_cond_ate(1) - _mod_true_marginal_ate()) > 0.03


def test_conditional_fraction_estimand_recovers_truth_on_data():
    """The Z-survives (genuine FractionExpr) estimand is evaluated on data via
    the VE fraction path and recovers the SCM's conditional ATE for both z."""
    graph, bi, x, y, z = _frac_graph()
    df = _frac_data(14000, seed=1)
    for zv in (True, False):
        est = estimate_general_id_conditional_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            given=(ValuedAtom(atom=z, value=zv),), ci_bootstrap=0,
        )
        assert est.method == "general_id_idc_plugin"
        true_ate = _frac_true_cond_ate(int(zv))
        assert abs(est.point - true_ate) < 0.05, (
            f"z={zv}: plug-in {est.point} vs true {true_ate}"
        )


def test_conditional_bootstrap_ci_brackets_point():
    graph, bi, x, y, c = _mod_graph()
    df = _mod_data(9000, seed=2)
    est = estimate_general_id_conditional_ate(
        df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
        given=(ValuedAtom(atom=c, value=True),),
        ci_bootstrap=150, random_state=42,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def _mod_graph():
    ast = _mod_ast([])
    prog = validate_program(validate_ast(ast))
    ground = instantiate(prog)
    graph = project(ground)
    bidirected = structural_solver.bidirected_from_ground(ground)
    x = next(n for n in graph.nodes() if n.predicate == "x")
    y = next(n for n in graph.nodes() if n.predicate == "y")
    c = next(n for n in graph.nodes() if n.predicate == "c")
    return graph, bidirected, x, y, c


# ============================================ honest refusals (guards)


def test_not_idc_identifiable_raises():
    """X→Y, X↔Y (a hedge) plus a modifier C→Y conditioned on: C exchanges into
    the do-set but do(X) itself is unidentified, so IDC fails — the estimator
    refuses rather than fabricating a value."""
    x, y, c = _A("x"), _A("y"), _A("c")
    import networkx as nx
    g = nx.DiGraph()
    g.add_edges_from([(x, y), (c, y)])
    bi = frozenset({frozenset({x, y})})
    rng = np.random.default_rng(0)
    n = 400
    df = pd.DataFrame({
        "x": rng.random(n) < 0.5, "y": rng.random(n) < 0.5,
        "c": rng.random(n) < 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_conditional_ate(
            df, graph=g, bidirected=bi, treatment_atom=x, outcome_atom=y,
            given=(ValuedAtom(atom=c, value=True),), ci_bootstrap=0,
        )
    assert exc.value.failure_type == "not_identifiable_by_idc"


def test_non_binary_treatment_raises():
    graph, bi, x, y, c = _mod_graph()
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "x": rng.integers(0, 3, n), "c": rng.random(n) < 0.5,
        "m": rng.random(n) < 0.5, "y": rng.random(n) < 0.5,
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_conditional_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            given=(ValuedAtom(atom=c, value=True),), ci_bootstrap=0,
        )
    assert exc.value.failure_type == "treatment_not_binary"


def test_positivity_empty_given_stratum_raises():
    """A queried Z=z stratum with zero support is a positivity violation, not a
    fabricated value."""
    graph, bi, x, y, c = _mod_graph()
    df = _mod_data(2000, seed=3)
    df["c"] = False                       # the C=True stratum is empty
    with pytest.raises(EstimatorFailure) as exc:
        estimate_general_id_conditional_ate(
            df, graph=graph, bidirected=bi, treatment_atom=x, outcome_atom=y,
            given=(ValuedAtom(atom=c, value=True),), ci_bootstrap=0,
        )
    assert exc.value.failure_type == "insufficient_support"


# ============================================ dispatch + verifier (e2e)


def test_dispatch_routes_conditional_to_idc_plugin():
    out = themis.estimate(_mod_ast([("c", True)]), _mod_data(10000, 4),
                          ci_bootstrap=0)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    est = r["numeric_estimate"]
    assert est["method"] == "general_id_idc_plugin"
    assert est["given"] == [["c", True]]
    assert abs(est["point"] - _mod_true_cond_ate(1)) < 0.04
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert rules == ["general_id_criterion", "numeric_general_id_estimate"]


def test_unconditional_margin_routes_front_door_not_idc():
    """Regression: the UNCONDITIONAL margin of the same graph routes through
    front-door (given is empty), not IDC — IDC is the conditional path only."""
    out = themis.estimate(_mod_ast([]), _mod_data(10000, 5), ci_bootstrap=0)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    est = r["numeric_estimate"]
    assert est["method"] in ("frontdoor_linear", "frontdoor_logistic")
    assert abs(est["point"] - _mod_true_marginal_ate()) < 0.04


def test_conditional_idc_verify_round_trips():
    ast = _mod_ast([("c", True)])
    out = themis.estimate(ast, _mod_data(10000, 6), ci_bootstrap=0)
    themis.verify(ast, out["results"][0])


def test_conditional_idc_output_validates_against_schema():
    out = themis.estimate(_mod_ast([("c", False)]), _mod_data(8000, 7),
                          ci_bootstrap=40, random_state=7)
    for r in out["results"]:
        validate_result(r)


def test_fraction_conditional_verify_round_trips():
    ast = _frac_ast(True)
    out = themis.estimate(ast, _frac_data(12000, 8), ci_bootstrap=0)
    r = out["results"][0]
    assert r["numeric_estimate"]["method"] == "general_id_idc_plugin"
    themis.verify(ast, r)


# ============================================ verifier tamper rejection


def _solved_mod_result(seed=9):
    ast = _mod_ast([("c", True)])
    out = themis.estimate(ast, _mod_data(10000, seed), ci_bootstrap=60,
                          random_state=11)
    return ast, out["results"][0]


def test_verify_rejects_criterion_claiming_unidentifiable():
    """The general_id_criterion step re-runs identify_via_idc for the
    conditional query. A tampered derivation claiming NOT identifiable (output
    False) while the estimate stands is contradicted by the independent re-run
    — proving the criterion exercises the IDC engine on the conditional path."""
    ast, r = _solved_mod_result()
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "general_id_criterion":
            s["output"] = False
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_verify_rejects_wrong_numeric_method():
    ast, r = _solved_mod_result(seed=10)
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "numeric_general_id_estimate":
            s["inputs"]["method"] = "iv_wald"
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_verify_rejects_point_outside_ci():
    """Data-refit ceiling: the metadata audit does NOT re-derive the plug-in
    point, but it does enforce point ∈ [ci_lower, ci_upper]. A point shoved
    outside its own CI is rejected."""
    ast, r = _solved_mod_result(seed=12)
    bad = copy.deepcopy(r)
    for s in bad["derivation"]["steps"]:
        if s["rule"] == "numeric_general_id_estimate":
            s["inputs"]["point"] = s["inputs"]["ci_upper"] + 5.0
    bad["numeric_estimate"]["point"] = bad["numeric_estimate"]["ci_upper"] + 5.0
    with pytest.raises(Exception):
        themis.verify(ast, bad)
