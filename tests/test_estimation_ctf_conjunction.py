"""Numeric end for the counterfactual rung — the ID*/IDC* estimand evaluated
to a POINT from a DataFrame by the non-parametric plug-in (the counterfactual
analogue of the general-ID plug-in, ``test_estimation_general_id*``).

Validation is D1 two-pronged:

1. Analytic oracle on a no-confounding graph (X→Y): P(y_x) and the conditional
   P(y_x | x') both equal P(y | x=1), which the generated data pins exactly.
2. The published worked example on data: fig 1 (X→W→Y ← Z ← D, X↔Y),
   P(y_x | x', z_d, d) is a genuine FractionExpr; the plug-in point on a large
   sample must match an INDEPENDENT conditional counterfactual Monte-Carlo
   oracle (numerator and denominator sharing one exogenous draw) run on the
   very SCM the data was sampled from.

The dispatch / verify tests exercise the whole ``themis.estimate`` →
``themis.verify`` round-trip, including a tampered-derivation rejection that
proves the numeric verifier has teeth.
"""
from __future__ import annotations

import copy
import random

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.ctf_conjunction import estimate_ctf_conjunction_prob
from themis.refusals import EstimatorFailure
from themis.input.syntactic_validator import validate_result
from themis.runtime.ctf_identify import CtfEvent
from themis.types import Atom
from themis.verifier import VerificationError
from themis.verifier.semantic_probe import _sample_scm
from tests.ctf_mc_oracle import conditional_prob


def A(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, W, Y, Z, D = A("x"), A("w"), A("y"), A("z"), A("d")


# ===================================================== SCM sampling + MC oracle
def _draw(dist: dict, rng: random.Random):
    r = rng.random()
    cum = 0.0
    last = None
    for v, p in dist.items():
        last = v
        cum += p
        if r < cum:
            return v
    return last


def _sample_observational_data(scm, graph, n: int, rng: random.Random) -> pd.DataFrame:
    """Sample ``n`` i.i.d. observational rows from the SCM — the exogenous
    background is drawn fresh per row, and only the OBSERVED node values are
    recorded (the latents stay hidden, exactly what a real dataset gives)."""
    topo = list(nx.topological_sort(graph))
    rows = []
    for _ in range(n):
        latents = {L: _draw(scm.latent_dist[L], rng) for L in scm.latents}
        val: dict = {}
        for node in topo:
            combo = tuple(
                latents[p] if isinstance(p, str) else val[p]
                for p in scm.parents[node]
            )
            val[node] = _draw(scm.cpt[node][combo], rng)
        rows.append({node.predicate: val[node] for node in topo})
    return pd.DataFrame(rows)


# The counterfactual P(γ|δ) MC oracle lives in tests.ctf_mc_oracle (a
# vectorized, identification-independent second implementation, pinned to exact
# enumeration by tests/test_counterfactual_mc_vectorized.py).


def _fig1_graph():
    g = nx.DiGraph()
    g.add_edges_from([(X, W), (W, Y), (Z, Y), (D, Z)])
    return g, frozenset({frozenset({X, Y})})


# ===================================================== analytic no-confound data
def _xy_data(n: int, seed: int) -> pd.DataFrame:
    """X → Y, no confounding. P(Y=1 | X=1) = 0.7, P(Y=1 | X=0) = 0.2, so
    P(y_x=1) = P(y | do x=1) = P(y | x=1) = 0.7."""
    rng = np.random.default_rng(seed)
    x = rng.random(n) < 0.5
    y = rng.random(n) < np.where(x, 0.7, 0.2)
    return pd.DataFrame({"x": x, "y": y})


def _xy_graph():
    g = nx.DiGraph()
    g.add_edge(X, Y)
    return g, frozenset()


_TRUE_PY_DO_X1 = 0.7


# ===================================================== unit: estimator
def test_estimate_unconditional_simple_matches_truth():
    g, bi = _xy_graph()
    df = _xy_data(20000, seed=0)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)   # y_x
    est = estimate_ctf_conjunction_prob(
        df, graph=g, bidirected=bi, gamma=gamma, ci_bootstrap=0)
    assert est.method == "ctf_conjunction_plugin"
    assert est.conditional is False
    assert abs(est.point - _TRUE_PY_DO_X1) < 0.03


def test_estimate_conditional_no_confound_matches_truth():
    # P(y_x | x') = P(y_x) = P(y | x=1) = 0.7 (Y_x ⊥ X; the evidence drops).
    g, bi = _xy_graph()
    df = _xy_data(20000, seed=1)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (CtfEvent(X, frozenset(), False),)             # x'
    est = estimate_ctf_conjunction_prob(
        df, graph=g, bidirected=bi, gamma=gamma, delta=delta, ci_bootstrap=0)
    assert est.conditional is True
    assert abs(est.point - _TRUE_PY_DO_X1) < 0.03


def test_estimate_fig1_conditional_matches_mc_oracle():
    # The JMLR Fig 12 worked example P(y_x | x', z_d, d) on data — a genuine
    # FractionExpr. The plug-in point must match the conditional counterfactual
    # MC truth on the very SCM the data came from.
    g, bi = _fig1_graph()
    scm = _sample_scm(g, bi, {}, random.Random(7))
    df = _sample_observational_data(scm, g, 60000, random.Random(8))
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    delta = (
        CtfEvent(X, frozenset(), False),
        CtfEvent(Z, frozenset({(D, True)}), True),
        CtfEvent(D, frozenset(), True),
    )
    true, den = conditional_prob(scm, g, gamma, delta, 150000, 9)
    assert den > 3000, f"conditioning event too rare in the SCM ({den})"
    est = estimate_ctf_conjunction_prob(
        df, graph=g, bidirected=bi, gamma=gamma, delta=delta, ci_bootstrap=0)
    assert est.conditional is True
    assert "|" in est.estimand
    assert abs(est.point - true) < 0.04, f"plug-in {est.point:.4f} vs MC {true:.4f}"


def test_estimate_bootstrap_ci_brackets_point():
    g, bi = _xy_graph()
    df = _xy_data(8000, seed=2)
    gamma = (CtfEvent(Y, frozenset({(X, True)}), True),)
    est = estimate_ctf_conjunction_prob(
        df, graph=g, bidirected=bi, gamma=gamma, ci_bootstrap=80)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_estimate_non_identifiable_raises():
    # PNS w-graph P(y_x ∧ y'_{x'}) with X→Y and X↔Y — non-identifiable.
    g = nx.DiGraph()
    g.add_edge(X, Y)
    bi = frozenset({frozenset({X, Y})})
    df = _xy_data(2000, seed=3)
    gamma = (
        CtfEvent(Y, frozenset({(X, True)}), True),
        CtfEvent(Y, frozenset({(X, False)}), False),
    )
    with pytest.raises(EstimatorFailure):
        estimate_ctf_conjunction_prob(df, graph=g, bidirected=bi, gamma=gamma)


# ===================================================== AST builders
def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _bidir(a, b):
    return {"kind": "bidirected", "left": {"predicate": a, "args": []},
            "right": {"predicate": b, "args": []}}


def _ev(varname, subs, value):
    return {"variable": {"predicate": varname, "args": []},
            "subscript": [{"atom": {"predicate": a, "args": []}, "value": v}
                          for (a, v) in subs],
            "value": value}


def _ast(statements, events, condition=None):
    q = {"kind": "counterfactual_conjunction", "events": events}
    if condition is not None:
        q["condition"] = condition
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [*statements,
                       {"kind": "query", "id": "q", "query": q}],
    }


def _xy_conditional_ast():
    return _ast([_var("x"), _var("y"), _cause("x", "y")],
                events=[_ev("y", [("x", True)], True)],
                condition=[_ev("x", [], False)])


def _xy_unconditional_ast():
    return _ast([_var("x"), _var("y"), _cause("x", "y")],
                events=[_ev("y", [("x", True)], True)])


def _pns_ast():
    return _ast([_var("x"), _var("y"), _cause("x", "y"), _bidir("x", "y")],
                events=[_ev("y", [("x", True)], True),
                        _ev("y", [("x", False)], False)])


# ===================================================== dispatch (themis.estimate)
def test_estimate_dispatch_conditional_attaches_numeric():
    df = _xy_data(20000, seed=10)
    out = themis.estimate(_xy_conditional_ast(), df, ci_bootstrap=0)
    r = out["results"][0]
    validate_result(r)
    assert r["status"] == "numerically_solved"
    assert r["query_kind"] == "counterfactual_conjunction"
    est = r["numeric_estimate"]
    assert est["method"] == "ctf_conjunction_plugin"
    assert est["conditional"] is True
    assert "treatment" not in est and "outcome" not in est
    assert abs(est["point"] - _TRUE_PY_DO_X1) < 0.03


def test_estimate_dispatch_unconditional_conditional_flag_false():
    df = _xy_data(20000, seed=11)
    out = themis.estimate(_xy_unconditional_ast(), df, ci_bootstrap=0)
    r = out["results"][0]
    validate_result(r)
    assert r["numeric_estimate"]["conditional"] is False


def test_estimate_dispatch_non_identifiable_stays_structural():
    # A non-identifiable conjunction gets NO numeric_estimate — the
    # identifiability verdict remains the primary answer.
    df = _xy_data(2000, seed=12)
    out = themis.estimate(_pns_ast(), df, ci_bootstrap=0)
    r = out["results"][0]
    validate_result(r)
    assert r["status"] == "needs_investigation"
    assert "numeric_estimate" not in r


# ===================================================== verify (independent mirror)
def test_verify_accepts_ctf_conjunction_numeric():
    ast = _xy_conditional_ast()
    df = _xy_data(20000, seed=13)
    r = themis.estimate(ast, df, ci_bootstrap=0)["results"][0]
    themis.verify(ast, r)   # raises on reject


def test_verify_rejects_tampered_numeric_metadata():
    """The numeric verifier audits the estimate's metadata self-consistency:
    a malformed data_hash on the numeric derivation step is rejected by the
    rule (the result's schema-checked numeric_estimate.data_hash is left
    intact, so this exercises the verifier rule, not the schema)."""
    ast = _xy_conditional_ast()
    df = _xy_data(20000, seed=14)
    r = themis.estimate(ast, df, ci_bootstrap=0)["results"][0]
    tampered = copy.deepcopy(r)
    tampered["derivation"]["steps"][-1]["inputs"]["data_hash"] = "tampered"
    with pytest.raises(VerificationError):
        themis.verify(ast, tampered)


def test_verify_rejects_tampered_criterion_flag():
    """Safety-critical: claiming the conjunction is identified when the
    criterion step's own output says otherwise is rejected — the criterion
    re-runs ID*/IDC*."""
    ast = _xy_conditional_ast()
    df = _xy_data(20000, seed=15)
    r = themis.estimate(ast, df, ci_bootstrap=0)["results"][0]
    tampered = copy.deepcopy(r)
    # Flip the criterion's claimed output to False; the engine recomputes
    # identifiable=True → mismatch → reject.
    tampered["derivation"]["steps"][0]["output"] = False
    with pytest.raises(VerificationError):
        themis.verify(ast, tampered)
