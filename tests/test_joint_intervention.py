"""Joint interventions do(A=a, B=b) — identification, estimation,
interaction, verification, and backward-compatibility.

Conformance DGP (two binary treatments, both confounded by Z, with a
known joint effect AND a known A×B interaction):

    A, B ~ f(Z)                 (Z confounds both treatments and Y)
    Y = 1·A + 1·B + 3·A·B + 2·Z + noise

True quantities:
    E[Y|do(A=1,B=1)] − E[Y|do(A=0,B=0)] = 1 + 1 + 3 = 5
    interaction = [do(1,1)−do(1,0)] − [do(0,1)−do(0,0)]
                = (5 − 1) − (1 − 0) = 3   (the A·B coefficient)

The single-treatment-with-the-other-as-covariate approach instead
recovers ≈ 1 + 3·E[B] ≈ 2.5 — a different estimand — demonstrating why
the joint contrast cannot be reconstructed from separate single-
treatment queries.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.joint import estimate_joint_effect
from themis.runtime import structural_solver
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.types import Atom, ConstTerm


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _typed_atom(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _joint_dgp(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    a = rng.random(n) < (1 / (1 + np.exp(-0.8 * z)))
    b = rng.random(n) < (1 / (1 + np.exp(-0.6 * z)))
    y = (
        1.0 * a.astype(float)
        + 1.0 * b.astype(float)
        + 3.0 * (a & b).astype(float)
        + 2.0 * z
        + rng.standard_normal(n) * 0.3
    )
    return pd.DataFrame({"a": a, "b": b, "z": z, "y": y})


def _joint_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "a", "domain": [True, False]},
            {"kind": "variable", "predicate": "b", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("a")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("b")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("a"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("b"), "to": _atom("y")},
            {"kind": "query", "id": "qj", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("a"), "value": True},
                "extra_interventions": [
                    {"atom": _atom("b"), "value": True},
                ],
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _single_ast():
    """Same program, but a plain single-treatment effect of A on Y
    (B is left as an ordinary covariate)."""
    ast = json.loads(json.dumps(_joint_ast()))
    for s in ast["statements"]:
        if s.get("kind") == "query":
            del s["query"]["extra_interventions"]
    return ast


# ============================================ structural identification


def test_joint_structural_identification():
    out = themis.run(_joint_ast())
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    ann = r["extensions"]["joint_identification"]
    assert ann["pattern"] == "joint_backdoor"
    assert ann["treatments"] == ["a(me)", "b(me)"]
    assert ann["adjustment_set"] == ["z(me)"]
    assert ann["interaction"] == "difference_scale"


def test_extra_interventions_round_trips_in_program():
    out = themis.run(_joint_ast())
    prog = out["program"]
    blob = json.dumps(prog)
    assert "extra_interventions" in blob


# ============================================ joint back-door unit


def test_minimal_adjustment_sets_joint_recovers_Z():
    ast = validate_ast(_joint_ast())
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    A, B, Y, Z = (_typed_atom(p) for p in ("a", "b", "y", "z"))
    sets = structural_solver.minimal_adjustment_sets_joint(graph, (A, B), Y)
    assert sets == (frozenset({Z}),)


def test_joint_backdoor_excludes_mediator_descendant():
    """A node on a proper causal path from a treatment to Y (a mediator)
    must never be admitted into the joint adjustment set."""
    ast = validate_ast({
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "a", "domain": [True, False]},
            {"kind": "variable", "predicate": "b", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("a"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("b"), "to": _atom("y")},
        ],
    })
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    A, B, M, Y = (_typed_atom(p) for p in ("a", "b", "m", "y"))
    sets = structural_solver.minimal_adjustment_sets_joint(graph, (A, B), Y)
    # No confounding here → empty set identifies; M (mediator) must not appear.
    assert frozenset() in sets
    assert all(M not in s for s in sets)


# ============================================ numeric estimate + interaction


def test_joint_estimate_recovers_contrast_and_interaction():
    df = _joint_dgp(n=4000, seed=0)
    out = themis.estimate(_joint_ast(), df, ci_bootstrap=300, random_state=1)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_backdoor_linear"
    assert ne["adjustment"] == ["z"]
    assert ne["treatments"] == ["a", "b"]

    joint = ne["joint_effect"]
    assert abs(joint["point"] - 5.0) < 0.3
    assert joint["ci_lower"] < joint["point"] < joint["ci_upper"]
    assert joint["treated"] == {"a": True, "b": True}
    assert joint["control"] == {"a": False, "b": False}

    inter = ne["interaction"]
    assert inter["scale"] == "difference"
    assert abs(inter["point"] - 3.0) < 0.3
    assert inter["ci_lower"] < inter["point"] < inter["ci_upper"]


def test_joint_estimate_is_deterministic():
    df = _joint_dgp(n=2000, seed=3)
    a = themis.estimate(_joint_ast(), df, ci_bootstrap=100, random_state=7)
    b = themis.estimate(_joint_ast(), df, ci_bootstrap=100, random_state=7)
    na = a["results"][0]["numeric_estimate"]
    nb = b["results"][0]["numeric_estimate"]
    assert na["joint_effect"] == nb["joint_effect"]
    assert na["interaction"] == nb["interaction"]


def test_single_treatment_approach_is_biased_vs_joint():
    """The single-treatment-with-the-other-as-covariate ATE recovers a
    DIFFERENT estimand (≈ 1 + 3·E[B] ≈ 2.5) than the joint contrast (5)."""
    df = _joint_dgp(n=4000, seed=0)
    joint = themis.estimate(_joint_ast(), df, ci_bootstrap=0, random_state=1)
    single = themis.estimate(_single_ast(), df, ci_bootstrap=0, random_state=1)

    joint_point = joint["results"][0]["numeric_estimate"]["joint_effect"]["point"]
    single_point = single["results"][0]["numeric_estimate"]["point"]

    assert abs(joint_point - 5.0) < 0.3
    assert abs(single_point - 2.5) < 0.4
    # The two are materially different — the joint effect cannot be read
    # off the single-treatment query.
    assert abs(joint_point - single_point) > 1.5


# ============================================ verification


def test_verify_accepts_joint_numeric_derivation():
    df = _joint_dgp(n=3000, seed=2)
    out = themis.estimate(_joint_ast(), df, ci_bootstrap=100, random_state=1)
    r = out["results"][0]
    themis.verify(_joint_ast(), r)  # raises on reject


def test_verify_accepts_joint_structural_derivation():
    out = themis.run(_joint_ast())
    r = out["results"][0]
    themis.verify(_joint_ast(), r)


def test_verify_rejects_tampered_joint_adjustment():
    """If the joint adjustment set is corrupted (Z dropped), the
    independent verifier must reject — it re-derives the criterion."""
    from themis.verifier.errors import VerificationError
    df = _joint_dgp(n=2000, seed=5)
    out = themis.estimate(_joint_ast(), df, ci_bootstrap=0, random_state=1)
    r = out["results"][0]
    # Drop Z from BOTH the criterion step and the numeric step's adjustment
    # input so the metadata audit passes but the criterion re-derivation fails.
    steps = r["derivation"]["steps"]
    for st in steps:
        if st["rule"] == "joint_backdoor_criterion":
            st["inputs"]["z"]["items"] = []
        if st["rule"] == "numeric_joint_backdoor_estimate":
            st["inputs"]["adjustment"]["items"] = []
    r["numeric_estimate"]["adjustment"] = []
    with pytest.raises(VerificationError):
        themis.verify(_joint_ast(), r)


# ============================================ backward compatibility


def test_single_treatment_program_byte_identical_without_field():
    """A program that never sets extra_interventions must serialize
    identically — the new field is omitted when empty."""
    out = themis.run(_single_ast())
    prog = out["program"]
    blob = json.dumps(prog)
    assert "extra_interventions" not in blob
    # And the single-treatment numeric path is unchanged.
    df = _joint_dgp(n=1500, seed=4)
    est = themis.estimate(_single_ast(), df, ci_bootstrap=0)
    assert est["results"][0]["numeric_estimate"]["method"] == "backdoor_linear"


# ============================================ cluster (pairs) bootstrap


def _joint_cluster_dgp(seed, *, G=60, per=20, cluster_sd=2.0):
    """Cluster-level treatments A, B (assigned once per cluster from a
    cluster-level confounder Z) + a shared family shock on Y. Within a
    cluster A, B, Z are constant and the shock is shared, so the i.i.d.
    bootstrap UNDERSTATES the variance and the cluster CI must be wider —
    for BOTH the joint contrast and the interaction. True joint contrast
    = 1+1+3 = 5, interaction = 3 (same coefficients as _joint_dgp)."""
    rng = np.random.default_rng(seed)
    clu = np.repeat(np.arange(G), per)
    z_c = rng.standard_normal(G)
    a_c = rng.random(G) < (1 / (1 + np.exp(-0.8 * z_c)))
    b_c = rng.random(G) < (1 / (1 + np.exp(-0.6 * z_c)))
    a = a_c[clu]; b = b_c[clu]; z = z_c[clu]
    u = rng.standard_normal(G) * cluster_sd
    y = (
        1.0 * a.astype(float) + 1.0 * b.astype(float)
        + 3.0 * (a & b).astype(float) + 2.0 * z
        + u[clu] + rng.standard_normal(G * per) * 0.3
    )
    return pd.DataFrame({"a": a, "b": b, "z": z, "y": y, "fam": clu})


def test_joint_cluster_none_byte_identical_to_default():
    df = _joint_cluster_dgp(0)
    kw = dict(treatments=("a", "b"), outcome="y", adjustment=("z",),
              ci_bootstrap=200, random_state=7)
    base = estimate_joint_effect(df, **kw)
    same = estimate_joint_effect(df, cluster=None, **kw)
    assert base.joint_point == same.joint_point
    assert base.joint_ci_lower == same.joint_ci_lower
    assert base.joint_ci_upper == same.joint_ci_upper
    assert base.interaction_ci_lower == same.interaction_ci_lower
    assert base.interaction_ci_upper == same.interaction_ci_upper
    assert base.data_hash == same.data_hash
    assert base.cluster is None


def test_joint_cluster_column_excluded_from_hash():
    df = _joint_cluster_dgp(1)
    with_col = estimate_joint_effect(
        df, treatments=("a", "b"), outcome="y", adjustment=("z",),
        ci_bootstrap=50, random_state=1, cluster="fam")
    without = estimate_joint_effect(
        df[["a", "b", "z", "y"]], treatments=("a", "b"), outcome="y",
        adjustment=("z",), ci_bootstrap=50, random_state=1)
    assert with_col.data_hash == without.data_hash
    assert with_col.cluster == "fam"


def test_joint_cluster_ci_wider_for_both_contrasts():
    """Both the joint contrast AND the interaction ride the same clustered
    resample, so both intervals widen under clustering."""
    df = _joint_cluster_dgp(2)
    kw = dict(treatments=("a", "b"), outcome="y", adjustment=("z",),
              ci_bootstrap=400, random_state=1)
    iid = estimate_joint_effect(df, **kw)
    clu = estimate_joint_effect(df, cluster="fam", **kw)
    j_iid = iid.joint_ci_upper - iid.joint_ci_lower
    j_clu = clu.joint_ci_upper - clu.joint_ci_lower
    i_iid = iid.interaction_ci_upper - iid.interaction_ci_lower
    i_clu = clu.interaction_ci_upper - clu.interaction_ci_lower
    assert j_clu > 1.3 * j_iid
    assert i_clu > 1.3 * i_iid
    assert any("cluster_bootstrap" in a for a in clu.assumptions)


def test_joint_cluster_e2e_attaches_bootstrap_meta_and_verifies():
    """options.cluster on a joint query: the numeric_estimate carries the
    cluster bootstrap provenance and the independent verifier still accepts
    (the cluster column is a variance concern, outside the derivation)."""
    ast = _joint_ast()
    ast["options"] = {"cluster": "fam"}
    df = _joint_cluster_dgp(3)
    out = themis.estimate(ast, df, ci_bootstrap=150, random_state=1)
    r = out["results"][0]
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_backdoor_linear"
    assert ne["bootstrap"] == {
        "kind": "cluster", "cluster_column": "fam",
        "requested": 150, "used": 150,
    }
    assert any("cluster_bootstrap" in a for a in ne["assumptions"])
    themis.verify(ast, r)  # raises on reject
    # Without the option the block is still written and says i.i.d. — its
    # absence used to carry that claim, and how many draws survived is a
    # second fact one absence cannot also carry.
    r2 = themis.estimate(_joint_ast(), df, ci_bootstrap=150,
                         random_state=1)["results"][0]
    assert r2["numeric_estimate"]["bootstrap"] == {
        "kind": "iid", "requested": 150, "used": 150,
    }
