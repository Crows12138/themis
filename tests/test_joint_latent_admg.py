"""Latent-confounded joint interventions do(A=a, B=b, …) on an ADMG.

The joint (treatment-SET) back-door criterion is generalized from
d-separation to **m-separation** in the proper back-door graph, so a
joint effect that is confounded by latent common causes (bidirected
edges) is identified and estimated whenever it is *adjustment*-
identifiable. Where no valid adjustment set exists the caller honestly
refuses (joint general-ID for the front-door / c-component subset is a
declared follow-on).

Conformance latent SCM:

    U (latent) → A, B        ⇒  A ↔ B (a bidirected edge)
    Z → A, B, Y              (observed confounder)
    Y = A + B + 2·A·B + 1.5·Z + noise      (U does NOT enter Y)

Because U does not affect Y, the JOINT intervention do(A,B) neutralizes
the A↔B confounding, and {Z} is a valid ADMG adjustment set. True joint
contrast do(1,1) − do(0,0) = 1 + 1 + 2 = 4; two-way interaction = 2. A
*single*-treatment do(A) is NOT {Z}-adjustable here (the A↔B→Y back-door
stays open) — the SET criterion is genuinely different.
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result
from themis.runtime import structural_solver as ss
from themis.types import Atom, ConstTerm


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _typed(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _ast(bidir):
    stmts = []
    for v in ("a", "b", "z", "y"):
        stmts.append({"kind": "variable", "predicate": v, "domain": [True, False]})
    for u, w in [("z", "a"), ("z", "b"), ("z", "y"), ("a", "y"), ("b", "y")]:
        stmts.append({"kind": "cause", "from": _atom(u), "to": _atom(w)})
    for u, w in bidir:
        stmts.append({"kind": "bidirected", "left": _atom(u), "right": _atom(w)})
    stmts.append({"kind": "query", "id": "qj", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("a"), "value": True},
        "extra_interventions": [{"atom": _atom("b"), "value": True}],
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _latent_dgp(n=8000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    u = rng.standard_normal(n)                       # latent, drives A<->B
    a = rng.random(n) < 1 / (1 + np.exp(-(0.8 * z + 1.2 * u)))
    b = rng.random(n) < 1 / (1 + np.exp(-(0.6 * z + 1.2 * u)))
    y = 1.0 * a + 1.0 * b + 2.0 * (a & b).astype(float) + 1.5 * z + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"a": a, "b": b, "z": z, "y": y})   # U hidden


# ============================================ structural unit


def test_minimal_adjustment_sets_joint_admg_adjustable():
    a, b, y, z = (_typed(p) for p in ("a", "b", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z, a), (z, b), (z, y), (a, y), (b, y)])
    bidir = frozenset({frozenset({a, b})})
    sets = ss.minimal_adjustment_sets_joint(g, (a, b), y, bidirected=bidir)
    assert sets == (frozenset({z}),)


def test_minimal_adjustment_sets_joint_admg_unadjustable():
    a, b, y, z = (_typed(p) for p in ("a", "b", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z, b), (a, y), (b, y)])
    bidir = frozenset({frozenset({a, y})})           # latent A<->Y
    sets = ss.minimal_adjustment_sets_joint(g, (a, b), y, bidirected=bidir)
    assert sets == ()                                # no valid adjustment set


def test_joint_set_criterion_differs_from_single_treatment():
    """With A<->B, the JOINT do(A,B) is {Z}-adjustable but a single do(A)
    is not (needs {B,Z}) — the treatment-set criterion is not the union of
    single-treatment criteria."""
    a, b, y, z = (_typed(p) for p in ("a", "b", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z, a), (z, b), (z, y), (a, y), (b, y)])
    bidir = frozenset({frozenset({a, b})})
    joint = ss.minimal_adjustment_sets_joint(g, (a, b), y, bidirected=bidir)
    single = ss.minimal_adjustment_sets_joint(g, (a,), y, bidirected=bidir)
    assert joint == (frozenset({z}),)
    assert frozenset({z}) not in single             # {Z} alone insufficient for do(A)
    assert frozenset({b, z}) in single


def test_admg_empty_bidirected_byte_identical_to_dag():
    a, b, y, z = (_typed(p) for p in ("a", "b", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z, a), (z, b), (z, y), (a, y), (b, y)])
    with_empty = ss.minimal_adjustment_sets_joint(g, (a, b), y, bidirected=frozenset())
    dag = ss.minimal_adjustment_sets_joint(g, (a, b), y)
    assert with_empty == dag == (frozenset({z}),)


# ============================================ e2e: recovery + verify


def test_latent_ab_joint_recovers_truth_and_verifies():
    ast = _ast([("a", "b")])
    df = _latent_dgp()
    out = themis.estimate(ast, df, ci_bootstrap=100, random_state=1)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_backdoor_linear"
    assert ne["adjustment"] == ["z"]
    assert abs(ne["joint_effect"]["point"] - 4.0) < 0.4     # 1+1+2, latent A<->B neutralized
    assert abs(ne["interaction"]["point"] - 2.0) < 0.4
    validate_result(r)          # schema
    themis.verify(ast, r)       # independent verifier (m-separation re-derivation)


def test_latent_ab_structural_records_adjustment():
    ast = _ast([("a", "b")])
    r = themis.run(ast)["results"][0]
    assert r["status"] == "structurally_solved"
    assert r["extensions"]["joint_identification"]["adjustment_set"] == ["z(me)"]


# ============================================ honest refusal


def test_latent_ay_joint_honest_refusal():
    """A latent common cause of a treatment and the outcome (A<->Y) has NO
    valid joint adjustment set — refuse, never fabricate a number."""
    ast = _ast([("a", "y")])
    s = themis.run(ast)["results"][0]
    assert s["status"] == "needs_investigation"
    names = [m["name"] for m in s.get("missing_information", [])]
    assert any("joint_not_identifiable" in n for n in names)
    # data path attaches no numeric estimate
    df = _latent_dgp()
    r = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)["results"][0]
    assert "numeric_estimate" not in r


# ============================================ verifier rejects tampering


def test_verify_rejects_tampered_latent_joint_adjustment():
    """Drop Z from the latent-joint criterion: the m-separation
    re-derivation over the ADMG finds the open A←Z→Y path and rejects (Z is
    still needed even though the joint intervention neutralizes A<->B)."""
    from themis.verifier.errors import VerificationError
    ast = _ast([("a", "b")])
    df = _latent_dgp()
    r = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)["results"][0]
    for st in r["derivation"]["steps"]:
        if st["rule"] == "joint_backdoor_criterion":
            st["inputs"]["z"]["items"] = []
        if st["rule"] == "numeric_joint_backdoor_estimate":
            st["inputs"]["adjustment"]["items"] = []
    r["numeric_estimate"]["adjustment"] = []
    with pytest.raises(VerificationError):
        themis.verify(ast, r)
