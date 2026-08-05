"""K-treatment joint interventions do(A=a, B=b, C=c, …) — the numeric end
generalized from exactly-two to K ≥ 2 binary treatments.

The identification layer (``minimal_adjustment_sets_joint``) already
solved the treatment-SET back-door for any K; this suite covers the
numeric plug-in that used to hard-lock at two treatments:

- the joint g-formula contrast E[Y|do(all treated)] − E[Y|do(all control)]
  over a K-treatment vector, and
- the highest-order (K-way) causal interaction — the K-th mixed finite
  difference over the 2^K treatment corners, which for K=2 is the ordinary
  A×B interaction.

Conformance DGP (three binary treatments confounded by Z, with a genuine
three-way interaction):

    A, B, C ~ f(Z)                       (Z confounds all three and Y)
    Y = A + B + C + θ·A·B·C + 2·Z + noise

True quantities (Z averages cancel in the standardized contrast):
    joint contrast do(1,1,1) − do(0,0,0) = 1 + 1 + 1 + θ
    three-way interaction                = θ            (θ = 2 below)

The anti-silent-wrong case swaps the θ·A·B·C term for a two-way γ·A·B
term: the *three*-way interaction must then be ~0 even though a lower-
order interaction is present — the K-th finite difference annihilates
every term below order K.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis import refusals
from themis.refusals import Refusal
from themis.refusals import EstimatorFailure
from themis.estimation.joint import estimate_joint_effect
from themis.input.syntactic_validator import validate_result
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


def _kjoint_ast(treatments, *, y="y", confounder="z", bidirected=None):
    """confounder → every treatment and → y; every treatment → y. The
    query intervenes on all treatments jointly (all True)."""
    stmts = []
    for v in (*treatments, confounder, y):
        stmts.append({"kind": "variable", "predicate": v, "domain": [True, False]})
    for t in treatments:
        stmts.append({"kind": "cause", "from": _atom(confounder), "to": _atom(t)})
        stmts.append({"kind": "cause", "from": _atom(t), "to": _atom(y)})
    stmts.append({"kind": "cause", "from": _atom(confounder), "to": _atom(y)})
    if bidirected:
        for u, v in bidirected:
            stmts.append({"kind": "bidirected", "left": _atom(u), "right": _atom(v)})
    head, *tail = treatments
    stmts.append({"kind": "query", "id": "qj", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom(head), "value": True},
        "extra_interventions": [{"atom": _atom(t), "value": True} for t in tail],
        "target": {"atom": _atom(y), "value": True},
        "given": [],
    }})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _dgp3(n=8000, seed=0, three_way=2.0, ab=0.0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    a = rng.random(n) < 1 / (1 + np.exp(-0.8 * z))
    b = rng.random(n) < 1 / (1 + np.exp(-0.6 * z))
    c = rng.random(n) < 1 / (1 + np.exp(-0.5 * z))
    y = (1.0 * a + 1.0 * b + 1.0 * c
         + ab * (a & b).astype(float)
         + three_way * (a & b & c).astype(float)
         + 2.0 * z + rng.standard_normal(n) * 0.3)
    return pd.DataFrame({"a": a, "b": b, "c": c, "z": z, "y": y})


# ============================================ estimator: recovery


def test_k3_recovers_joint_and_three_way_interaction():
    df = _dgp3(three_way=2.0, ab=0.0)
    est = estimate_joint_effect(
        df, treatments=("a", "b", "c"), outcome="y", adjustment=("z",),
        ci_bootstrap=200, random_state=1,
    )
    assert abs(est.joint_point - 5.0) < 0.4          # 1+1+1+θ, θ=2
    assert abs(est.interaction_point - 2.0) < 0.4    # the three-way coeff θ
    assert est.joint_ci_lower < est.joint_point < est.joint_ci_upper
    assert est.interaction_ci_lower < est.interaction_point < est.interaction_ci_upper
    assert est.method == "joint_backdoor_linear"
    assert est.treatments == ("a", "b", "c")


def test_k3_no_three_way_isolates_zero_interaction():
    """A two-way γ·A·B interaction is present but there is NO three-way
    term. The *three*-way interaction (K=3 finite difference) must isolate
    ~0 — it annihilates the lower-order two-way term. This is the anti-
    silent-wrong guard: reporting γ (1.5) as the three-way interaction
    would be a dramatically wrong number."""
    df = _dgp3(three_way=0.0, ab=1.5)
    est = estimate_joint_effect(
        df, treatments=("a", "b", "c"), outcome="y", adjustment=("z",),
        ci_bootstrap=0, random_state=1,
    )
    assert abs(est.joint_point - 4.5) < 0.4          # 1+1+1+γ, γ=1.5
    assert abs(est.interaction_point - 0.0) < 0.3    # three-way is zero


def test_k4_scales_to_four_way_interaction():
    rng = np.random.default_rng(0)
    n = 12000
    z = rng.standard_normal(n)
    a = rng.random(n) < 1 / (1 + np.exp(-0.7 * z))
    b = rng.random(n) < 1 / (1 + np.exp(-0.6 * z))
    c = rng.random(n) < 1 / (1 + np.exp(-0.5 * z))
    d = rng.random(n) < 1 / (1 + np.exp(-0.4 * z))
    y = (1.0 * a + 1.0 * b + 1.0 * c + 1.0 * d
         + 1.5 * (a & b & c & d).astype(float)
         + 2.0 * z + rng.standard_normal(n) * 0.3)
    df = pd.DataFrame({"a": a, "b": b, "c": c, "d": d, "z": z, "y": y})
    est = estimate_joint_effect(
        df, treatments=("a", "b", "c", "d"), outcome="y", adjustment=("z",),
        ci_bootstrap=0, random_state=1,
    )
    assert abs(est.joint_point - 5.5) < 0.5          # 4 + 1.5
    assert abs(est.interaction_point - 1.5) < 0.5    # the four-way coeff


def test_k2_generalized_basis_matches_known_two_way():
    """The generalized saturated-basis path reproduces the two-treatment
    conformance numbers (joint 5, interaction 3) — no regression from the
    exactly-two implementation it replaced."""
    rng = np.random.default_rng(0)
    n = 4000
    z = rng.standard_normal(n)
    a = rng.random(n) < 1 / (1 + np.exp(-0.8 * z))
    b = rng.random(n) < 1 / (1 + np.exp(-0.6 * z))
    y = 1.0 * a + 1.0 * b + 3.0 * (a & b).astype(float) + 2.0 * z + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"a": a, "b": b, "z": z, "y": y})
    est = estimate_joint_effect(
        df, treatments=("a", "b"), outcome="y", adjustment=("z",),
        ci_bootstrap=0, random_state=1,
    )
    assert abs(est.joint_point - 5.0) < 0.3
    assert abs(est.interaction_point - 3.0) < 0.3


# ============================================ scope / honesty


def test_below_two_treatments_is_not_a_joint_intervention():
    df = _dgp3()
    with pytest.raises(EstimatorFailure) as exc:
        estimate_joint_effect(
            df, treatments=("a",), outcome="y", adjustment=("z",),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.NOT_A_JOINT_INTERVENTION


def test_beyond_cap_is_too_many_joint_treatments():
    n = 300
    cols = {c: (np.arange(n) % 2 == 0) for c in ("a", "b", "c", "d", "e", "f")}
    df = pd.DataFrame(cols)
    df["z"] = np.random.default_rng(0).standard_normal(n)
    df["y"] = np.random.default_rng(1).standard_normal(n)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_joint_effect(
            df, treatments=("a", "b", "c", "d", "e", "f"), outcome="y",
            adjustment=("z",), ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.TOO_MANY_JOINT_TREATMENTS


def test_duplicate_treatment_is_an_invalid_request():
    df = _dgp3()
    with pytest.raises(EstimatorFailure) as exc:
        estimate_joint_effect(
            df, treatments=("a", "a"), outcome="y", adjustment=("z",),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.INVALID_INPUT


# ============================================ structural identification


def test_k3_structural_identification():
    ast = _kjoint_ast(("a", "b", "c"))
    out = themis.run(ast)
    r = out["results"][0]
    assert r["status"] == "structurally_solved"
    ann = r["extensions"]["joint_identification"]
    assert ann["pattern"] == "joint_backdoor"
    assert ann["treatments"] == ["a(me)", "b(me)", "c(me)"]
    assert ann["adjustment_set"] == ["z(me)"]


def test_minimal_adjustment_sets_joint_handles_k3():
    ast = validate_ast(_kjoint_ast(("a", "b", "c")))
    prog = validate_program(ast)
    graph = project(instantiate(prog))
    A, B, C, Y, Z = (_typed_atom(p) for p in ("a", "b", "c", "y", "z"))
    sets = structural_solver.minimal_adjustment_sets_joint(graph, (A, B, C), Y)
    assert sets == (frozenset({Z}),)


# ============================================ e2e dispatch + verify + schema


def test_k3_e2e_routes_verifies_and_validates():
    ast = _kjoint_ast(("a", "b", "c"))
    df = _dgp3(three_way=2.0)
    out = themis.estimate(ast, df, ci_bootstrap=100, random_state=1)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_backdoor_linear"
    assert ne["treatments"] == ["a", "b", "c"]
    assert ne["adjustment"] == ["z"]
    assert ne["interaction"]["order"] == 3
    assert ne["interaction"]["scale"] == "difference"
    assert set(ne["joint_effect"]["treated"]) == {"a", "b", "c"}
    assert set(ne["joint_effect"]["control"]) == {"a", "b", "c"}
    assert ne["joint_effect"]["treated"] == {"a": True, "b": True, "c": True}
    assert ne["joint_effect"]["control"] == {"a": False, "b": False, "c": False}
    # derivation rules are the joint pair (criterion re-run + metadata audit)
    rules = [s["rule"] for s in r["derivation"]["steps"]]
    assert rules == ["joint_backdoor_criterion", "numeric_joint_backdoor_estimate"]
    validate_result(r)          # schema (themis registry) — raises on reject
    themis.verify(ast, r)       # independent verifier — raises on reject


def test_k3_deterministic():
    ast = _kjoint_ast(("a", "b", "c"))
    df = _dgp3()
    a = themis.estimate(ast, df, ci_bootstrap=80, random_state=7)["results"][0]["numeric_estimate"]
    b = themis.estimate(ast, df, ci_bootstrap=80, random_state=7)["results"][0]["numeric_estimate"]
    assert a["joint_effect"] == b["joint_effect"]
    assert a["interaction"] == b["interaction"]


# ============================================ verifier rejects tampering


def test_verify_rejects_tampered_k3_adjustment():
    """Drop Z from the K=3 joint criterion and the numeric adjustment: the
    metadata audit still passes (they agree) but the independent criterion
    re-derivation over the {a,b,c} treatment set finds an open back-door
    and rejects."""
    from themis.verifier.errors import VerificationError
    ast = _kjoint_ast(("a", "b", "c"))
    df = _dgp3()
    out = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)
    r = out["results"][0]
    for st in r["derivation"]["steps"]:
        if st["rule"] == "joint_backdoor_criterion":
            st["inputs"]["z"]["items"] = []
        if st["rule"] == "numeric_joint_backdoor_estimate":
            st["inputs"]["adjustment"]["items"] = []
    r["numeric_estimate"]["adjustment"] = []
    with pytest.raises(VerificationError):
        themis.verify(ast, r)


def test_verify_rejects_k3_interaction_point_outside_ci():
    """Corrupt the K-way interaction point outside its CI — the numeric
    metadata audit must reject (it checks point ∈ [lo, hi])."""
    from themis.verifier.errors import VerificationError
    ast = _kjoint_ast(("a", "b", "c"))
    df = _dgp3()
    out = themis.estimate(ast, df, ci_bootstrap=100, random_state=1)
    r = out["results"][0]
    for st in r["derivation"]["steps"]:
        if st["rule"] == "numeric_joint_backdoor_estimate":
            st["inputs"]["interaction_point"] = 999.0
    r["numeric_estimate"]["interaction"]["point"] = 999.0
    with pytest.raises(VerificationError):
        themis.verify(ast, r)


# ============================================ latent joint still honest


def test_k3_latent_unadjustable_honest_refusal():
    """A latent common cause of a treatment and the outcome (A<->Y) in a
    K=3 joint query has NO valid ADMG adjustment set, so the joint
    criterion honestly refuses — needs_investigation with
    joint_not_identifiable and NO fabricated number. (Latent joint effects
    that ARE adjustment-identifiable are solved; see
    tests/test_joint_latent_admg.py.)"""
    ast = _kjoint_ast(("a", "b", "c"), bidirected=[("a", "y")])
    df = _dgp3()
    out = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)
    r = out["results"][0]
    assert "numeric_estimate" not in r
    assert r["status"] == "needs_investigation"
    names = [m["name"] for m in r.get("missing_information", [])]
    assert any("joint_not_identifiable" in n for n in names)


# ============================================ corner support (positivity)
#
# The joint contrast and the K-way interaction rest on different corners
# of the treatment box, so they can be identified apart. The outcome model
# predicts at every corner whether or not any row is there, which is what
# makes an unsupported corner produce a confident number rather than a
# missing one.


def _never_combined(n=2000, seed=0, joint_effect=3.0):
    """Two treatments that are never seen apart: (a=1,b=0) and (a=0,b=1)
    have no rows. The all-treated and all-control cells are both fully
    observed, so the contrast is identified and its truth is known."""
    rng = np.random.default_rng(seed)
    a = rng.random(n) < 0.5
    z = rng.standard_normal(n)
    y = joint_effect * a + 1.5 * z + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"a": a, "b": a, "z": z, "y": y})


def test_an_unsupported_corner_withholds_the_interaction_not_the_contrast():
    """Two of the four corners have no rows. The K-way interaction is a
    finite difference over all of them, so it is not identified; the
    contrast is taken between the two corners that ARE observed, so it is.

    The number the interaction used to report came from the outcome model
    extrapolating into the empty corners — precise-looking, and about
    nothing."""
    df = _never_combined(n=2000, seed=0, joint_effect=3.0)
    est = estimate_joint_effect(
        df, treatments=("a", "b"), outcome="y", adjustment=("z",),
        ci_bootstrap=50, random_state=1,
    )
    # What survives, survives correctly.
    assert abs(est.joint_point - 3.0) < 0.1
    assert est.joint_ci_lower <= est.joint_point <= est.joint_ci_upper
    # What does not, says so — including its interval, which would
    # otherwise be an interval around a fabrication.
    assert est.interaction_point is None
    assert est.interaction_ci_lower is None
    assert est.interaction_ci_upper is None
    assert dict(est.interaction_unsupported_cells[0]) == {"a": True, "b": False}
    assert dict(est.interaction_unsupported_cells[1]) == {"a": False, "b": True}
    assert "no rows" in est.interaction_unavailable_reason


def test_an_unsupported_contrast_cell_refuses_the_whole_estimate():
    """A treatment stuck at one level empties whichever contrast cell asked
    for the other. Then there is no estimate at all, not a partial one."""
    rng = np.random.default_rng(0)
    n = 500
    df = pd.DataFrame({
        "a": rng.random(n) < 0.5,
        "b": np.ones(n, dtype=bool),       # never False
        "z": rng.standard_normal(n),
        "y": rng.standard_normal(n),
    })
    with pytest.raises(EstimatorFailure) as exc:
        estimate_joint_effect(
            df, treatments=("a", "b"), outcome="y", adjustment=("z",),
            ci_bootstrap=0,
        )
    assert exc.value.failure_type == Refusal.OVERLAP_INSUFFICIENT
    assert exc.value.details["unsupported_cells"] == [{"a": False, "b": False}]


def test_the_envelope_carries_the_withheld_interaction():
    """End-to-end: the block is absent rather than present holding null, and
    `interaction_unavailable` stands where it was."""
    ast = _kjoint_ast(("a", "b"))
    df = _never_combined(n=2000, seed=0)
    out = themis.estimate(ast, df, ci_bootstrap=30, random_state=1)
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    ne = r["numeric_estimate"]
    assert "interaction" not in ne
    unavailable = ne["interaction_unavailable"]
    assert unavailable["order"] == 2
    assert unavailable["unsupported_cells"] == [
        {"a": True, "b": False}, {"a": False, "b": True},
    ]
    validate_result(r)
    themis.verify(ast, r)


def test_verify_rejects_an_interaction_that_went_missing_without_a_reason():
    """Absence has to be declared. A derivation that simply drops the
    interaction point looks, to a reader, exactly like one whose corners
    were empty — so the audit demands the difference in writing."""
    from themis.verifier.errors import VerificationError
    ast = _kjoint_ast(("a", "b", "c"))
    df = _dgp3()
    out = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)
    r = out["results"][0]
    for st in r["derivation"]["steps"]:
        if st["rule"] == "numeric_joint_backdoor_estimate":
            del st["inputs"]["interaction_point"]
    with pytest.raises(VerificationError):
        themis.verify(ast, r)
