"""Joint multi-mediator natural effects (VanderWeele-Vansteelandt 2014).

The JOINT NDE/NIE decomposition through a mediator SET taken as one
block. Covers all layers:

- structural identification (``mediation_sets_joint``) incl. the
  recanting-witness contrast vs the single-mediator check,
- the data-end estimator (``estimate_mediation_joint``) numeric recovery
  and its k=1 equivalence to ``estimate_mediation``,
- scheduler routing (``themis.run``) + ``themis.verify`` round-trip,
- data dispatch (``themis.estimate``) + numeric verifier (strong on the
  linear path) + tamper rejection,
- AST round-trip of the ``mediators`` field.
"""
from __future__ import annotations

import copy

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.mediation import (
    estimate_mediation,
    estimate_mediation_joint,
)
from themis.runtime.structural_solver import (
    mediation_sets,
    mediation_sets_joint,
)
from themis.verifier.rules import (
    _rule_identify_via_mediation_joint,
    _rule_mediation_nde_nie_joint_check,
)


# =====================================================================
# structural identification
# =====================================================================


def test_parallel_mediators_jointly_identifiable():
    """X→M1→Y, X→M2→Y: joint block identifiable with no adjustment."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2"), ("M2", "Y")])
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.mediator_set_valid is True
    assert r.nde_nie.identifiable is True
    assert r.nde_nie.adjustment == frozenset()


def test_recanting_witness_block_absorbs_it():
    """X→M1→Y, X→M1→M2→Y, M2→Y: M1 confounds M2→Y and is an
    X-descendant, so the single-mediator M2 check fails — but the JOINT
    {M1,M2} block is identifiable (cutting every set member's outgoing
    edges removes the intra-set confounding path)."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("M1", "M2"), ("M2", "Y")])
    # single M2 fails
    assert mediation_sets(g, "X", "Y", "M2").nde_nie.identifiable is False
    # joint {M1,M2} succeeds
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.nde_nie.identifiable is True


def test_outside_x_affected_confounder_not_identifiable():
    """X→W, W→M1, W→Y, X→M1→Y: W is an X-affected confounder of M1→Y
    OUTSIDE the set — genuinely not identifiable (honest refusal)."""
    g = nx.DiGraph([("X", "W"), ("W", "M1"), ("W", "Y"), ("X", "M1"), ("M1", "Y")])
    r = mediation_sets_joint(g, "X", "Y", {"M1"})
    assert r.mediator_set_valid is True
    assert r.nde_nie.identifiable is False


def test_baseline_confounder_found_in_adjustment():
    """C→X, C→Y baseline confounder: identifiable with W={C}."""
    g = nx.DiGraph(
        [("C", "X"), ("C", "Y"), ("X", "M1"), ("M1", "Y"),
         ("X", "M2"), ("M2", "Y")]
    )
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.nde_nie.identifiable is True
    assert r.nde_nie.adjustment == frozenset({"C"})


def test_invalid_set_when_member_does_not_mediate():
    """M2 has no path to Y → set invalid."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2")])
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.mediator_set_valid is False
    assert r.nde_nie.identifiable is False


def test_empty_set_invalid():
    g = nx.DiGraph([("X", "M1"), ("M1", "Y")])
    r = mediation_sets_joint(g, "X", "Y", set())
    assert r.mediator_set_valid is False


# =====================================================================
# estimation core — numeric recovery
# =====================================================================


def _joint_scm(n=40000, seed=0):
    """Linear SCM with two CORRELATED mediators; returns (df, truth)."""
    rng = np.random.default_rng(seed)
    bx, b1, b2, g1, g2 = 0.5, 0.8, 0.6, 0.3, -0.2
    a1, a2, c1, c2, rho = 1.0, 1.5, 0.2, 0.1, 0.7
    X = (rng.random(n) < 0.5).astype(float)
    U1 = rng.standard_normal(n)
    U2 = rng.standard_normal(n)
    M1 = c1 + a1 * X + U1
    M2 = c2 + a2 * X + rho * U1 + U2
    Y = (bx * X + b1 * M1 + b2 * M2 + g1 * X * M1 + g2 * X * M2
         + 0.5 * rng.standard_normal(n))
    df = pd.DataFrame({"x": X.astype(bool), "m1": M1, "m2": M2, "y": Y})
    q10, q11, q20, q21 = c1, c1 + a1, c2, c2 + a2
    nie = (b1 + g1) * (q11 - q10) + (b2 + g2) * (q21 - q20)
    nde = bx + g1 * q10 + g2 * q20
    return df, {"nde": nde, "nie": nie, "te": nde + nie}


def test_joint_linear_recovers_truth():
    df, truth = _joint_scm()
    est = estimate_mediation_joint(
        df, treatment="x", outcome="y", mediators=("m1", "m2"), n_rep=40,
    )
    assert est.method == "mediation_joint_linear"
    assert abs(est.nde_point - truth["nde"]) < 0.03
    assert abs(est.nie_point - truth["nie"]) < 0.03
    assert abs(est.te_point - truth["te"]) < 0.03
    # proportion mediated = NIE / TE
    assert abs(est.proportion_mediated_point - truth["nie"] / truth["te"]) < 0.02
    # TE = NDE + NIE identity
    assert abs(est.te_point - (est.nde_point + est.nie_point)) < 1e-9


def test_joint_linear_bridge_reproduces_point():
    """The recorded sufficient statistics re-derive the reported NDE/NIE
    exactly — the same bridge the verifier uses."""
    df, _ = _joint_scm(n=8000)
    est = estimate_mediation_joint(
        df, treatment="x", outcome="y", mediators=("m1", "m2"), n_rep=10,
    )
    ss = est.sufficient_statistics
    oc, mm = ss["outcome_coefficients"], ss["mediator_means"]
    names = list(oc["mediators"].keys())
    nde_rd = oc["treatment"] + sum(
        oc["interactions"][n] * mm[n]["m0"] for n in names
    )
    nie_rd = sum(
        (oc["mediators"][n] + oc["interactions"][n]) * (mm[n]["m1"] - mm[n]["m0"])
        for n in names
    )
    assert abs(nde_rd - est.nde_point) < 1e-9
    assert abs(nie_rd - est.nie_point) < 1e-9


def test_k1_equivalence_to_single_mediator_linear():
    """estimate_mediation_joint with one mediator equals estimate_mediation
    byte-for-byte on the linear path (both plug in the marginal mean)."""
    df, _ = _joint_scm(n=8000)
    j = estimate_mediation_joint(
        df, treatment="x", outcome="y", mediators=("m1",), n_rep=10,
    )
    s = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m1", n_rep=10,
    )
    assert abs(j.nde_point - s.nde_point) < 1e-9
    assert abs(j.nie_point - s.nie_point) < 1e-9


def test_joint_logit_runs_and_holds_identity():
    df, _ = _joint_scm(n=8000)
    df = df.copy()
    df["yb"] = df["y"] > df["y"].median()
    est = estimate_mediation_joint(
        df, treatment="x", outcome="yb", mediators=("m1", "m2"), n_rep=20,
    )
    assert est.method == "mediation_joint_logit"
    assert abs(est.te_point - (est.nde_point + est.nie_point)) < 1e-9


def test_empty_mediators_raises():
    df, _ = _joint_scm(n=500)
    with pytest.raises(ValueError):
        estimate_mediation_joint(
            df, treatment="x", outcome="y", mediators=(),
        )


def test_duplicate_mediator_raises():
    df, _ = _joint_scm(n=500)
    with pytest.raises(ValueError):
        estimate_mediation_joint(
            df, treatment="x", outcome="y", mediators=("m1", "m1"),
        )


# =====================================================================
# end-to-end: run / estimate / verify
# =====================================================================


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _joint_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m1", "domain": [True, False]},
            {"kind": "variable", "predicate": "m2", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m1")},
            {"kind": "cause", "from": _atom("m1"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m2")},
            {"kind": "cause", "from": _atom("m2"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "mediators": [_atom("m1"), _atom("m2")],
            }},
        ],
    }


def test_run_routes_to_joint_and_verifies():
    ast = _joint_ast()
    out = themis.run(ast)
    res = out["results"][0]
    assert res["status"] == "structurally_solved"
    mjd = res["extensions"]["mediation_joint_decomposition"]
    assert mjd["mediator_set_valid"] is True
    assert mjd["strategy"] == "nde_nie"
    assert mjd["nde_nie"]["identifiable"] is True
    rules = [s["rule"] for s in res["derivation"]["steps"]]
    assert "mediation_nde_nie_joint_check" in rules
    assert "identify_via_mediation_joint" in rules
    # verify must not raise
    themis.verify(ast, res)


def test_invalid_set_run_reports_needs_investigation():
    ast = _joint_ast()
    # break m2's path to y by removing m2→y
    ast["statements"] = [
        s for s in ast["statements"]
        if not (s.get("kind") == "cause"
                and s.get("from", {}).get("predicate") == "m2"
                and s.get("to", {}).get("predicate") == "y")
    ]
    out = themis.run(ast)
    res = out["results"][0]
    assert res["status"] == "needs_investigation"
    assert res["extensions"]["mediation_joint_decomposition"][
        "mediator_set_valid"] is False


def test_estimate_attaches_joint_decomposition_and_verifies():
    df, truth = _joint_scm(n=6000, seed=1)
    ast = _joint_ast()
    out = themis.estimate(ast, df, random_state=42)
    res = out["results"][0]
    assert res["status"] == "structurally_solved"
    est = res["numeric_estimate"]
    assert est["method"] == "mediation_joint_linear"
    assert set(est["mediators"]) == {"m1", "m2"}
    d = est["decomposition"]
    assert abs(d["nde"]["point"] - truth["nde"]) < 0.06
    assert abs(d["nie"]["point"] - truth["nie"]) < 0.06
    assert "sufficient_statistics" in d
    # verify must not raise
    themis.verify(ast, res)


def test_verifier_rejects_tampered_nde():
    df, _ = _joint_scm(n=4000, seed=2)
    ast = _joint_ast()
    res = themis.estimate(ast, df, random_state=42)["results"][0]
    bad = copy.deepcopy(res)
    bad["numeric_estimate"]["decomposition"]["nde"]["point"] += 0.5
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_verifier_rejects_tampered_coefficient():
    """Strong verification: corrupting a recorded coefficient changes the
    re-derived NDE, which then mismatches the recorded NDE."""
    df, _ = _joint_scm(n=4000, seed=3)
    ast = _joint_ast()
    res = themis.estimate(ast, df, random_state=42)["results"][0]
    bad = copy.deepcopy(res)
    ss = bad["numeric_estimate"]["decomposition"]["sufficient_statistics"]
    ss["outcome_coefficients"]["treatment"] += 1.0
    with pytest.raises(Exception):
        themis.verify(ast, bad)


# =====================================================================
# latent / ADMG-aware joint
# =====================================================================


def test_joint_admg_aware_bidirected():
    """A bidirected M1↔M2 (shared unmeasured cause of the two mediators)
    does not by itself break the joint block: neither is on an X→M
    or M→Y backdoor. Still identifiable."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2"), ("M2", "Y")])
    bidir = frozenset({frozenset({"M1", "M2"})})
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"}, bidirected=bidir)
    assert r.nde_nie.identifiable is True


# =====================================================================
# AST round-trip
# =====================================================================


def test_mediators_field_round_trips():
    from themis.input.semantic_validator import _to_query  # type: ignore

    q = _to_query({
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
        "mediators": [_atom("m1"), _atom("m2")],
    })
    assert len(q.mediators) == 2
    assert {a.predicate for a in q.mediators} == {"m1", "m2"}
    assert q.mediator is None


# =====================================================================
# verifier byte-code independence pin
# =====================================================================


def test_joint_verifier_rules_do_not_reference_structural_solver():
    forbidden = {
        "structural_solver",
        "mediation_sets_joint",
        "MediationJointResult",
        "MediationAttempt",
    }
    for fn in (
        _rule_mediation_nde_nie_joint_check,
        _rule_identify_via_mediation_joint,
    ):
        names = set(fn.__code__.co_names)
        assert not (names & forbidden), (
            f"{fn.__name__} references forbidden symbol: {names & forbidden}"
        )
