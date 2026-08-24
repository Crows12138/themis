"""Joint general-ID: latent-confounded joint interventions do(A, B, …) that
have NO valid adjustment set but are still non-parametrically point-identified
by the set-valued Shpitser-Pearl ID (front-door / c-component for a treatment
SET).

This is the joint analog of the single-treatment general-ID escape layer. It
fires ONLY when the joint (treatment-set) back-door adjustment criterion fails
(latent confounding) yet the joint effect is genuinely identified — never
fabricating a number for a genuine joint hedge.

Conformance latent SCM — 2× front-door (two independent front-doors, each with
a latent treatment↔outcome common cause, so adjustment is impossible):

    A → Ma → Y,   B → Mb → Y,   A ↔ Y,   B ↔ Y
    Ua, Ub ~ Bern(.5);  A: .85/.15 by Ua;  B: .80/.20 by Ub
    Ma: .9/.1 by A;     Mb: .9/.1 by B
    Y : Bern(clip(.10 + .35·Ma + .30·Mb + .12·Ua + .10·Ub))

The latent A↔Y / B↔Y bow-free arcs are neutralized by the front-door mediators,
so P(Y | do(A, B)) is identified. The true uniform joint contrast
P(Y | do(1,1)) − P(Y | do(0,0)) ≈ 0.52 (Monte-Carlo oracle).
"""
from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result
from themis.types import Atom, ConstTerm


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _typed(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _ast_2x_frontdoor():
    """do(A, B) on Y in the 2× front-door latent graph (adjustment fails,
    set-valued ID succeeds)."""
    stmts = []
    for v in ("a", "b", "ma", "mb", "y"):
        stmts.append({"kind": "variable", "predicate": v, "domain": [True, False]})
    for u, w in [("a", "ma"), ("ma", "y"), ("b", "mb"), ("mb", "y")]:
        stmts.append({"kind": "cause", "from": _atom(u), "to": _atom(w)})
    for u, w in [("a", "y"), ("b", "y")]:
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


def _ast_bow_arc():
    """do(A, B) on Y where A ↔ Y is a BOW arc (A → Y direct AND A ↔ Y): the
    joint effect is genuinely NOT identified — no adjustment set AND no
    set-valued ID estimand. The honest answer is to refuse."""
    stmts = []
    for v in ("a", "b", "z", "y"):
        stmts.append({"kind": "variable", "predicate": v, "domain": [True, False]})
    for u, w in [("z", "a"), ("z", "b"), ("z", "y"), ("a", "y"), ("b", "y")]:
        stmts.append({"kind": "cause", "from": _atom(u), "to": _atom(w)})
    stmts.append({"kind": "bidirected", "left": _atom("a"), "right": _atom("y")})
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


def _ast_adjustable_dag():
    """do(A, B) on Y in a fully-observed DAG — adjustment succeeds, so the
    joint effect must route through the joint BACK-DOOR path, not general-ID."""
    stmts = []
    for v in ("a", "b", "z", "y"):
        stmts.append({"kind": "variable", "predicate": v, "domain": [True, False]})
    for u, w in [("z", "a"), ("z", "b"), ("z", "y"), ("a", "y"), ("b", "y")]:
        stmts.append({"kind": "cause", "from": _atom(u), "to": _atom(w)})
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


def _scm_2x(n=200_000, seed=1):
    rng = np.random.default_rng(seed)
    ua = rng.random(n) < 0.5
    ub = rng.random(n) < 0.5
    a = rng.random(n) < np.where(ua, 0.85, 0.15)
    b = rng.random(n) < np.where(ub, 0.80, 0.20)
    ma = rng.random(n) < np.where(a, 0.9, 0.1)
    mb = rng.random(n) < np.where(b, 0.9, 0.1)
    py = 0.10 + 0.35 * ma + 0.30 * mb + 0.12 * ua + 0.10 * ub
    y = rng.random(n) < np.clip(py, 0, 1)
    return pd.DataFrame({"a": a, "b": b, "ma": ma, "mb": mb, "y": y})   # U hidden


def _true_joint(av, bv, seed=0, n=3_000_000):
    rng = np.random.default_rng(seed)
    ua = rng.random(n) < 0.5
    ub = rng.random(n) < 0.5
    ma = rng.random(n) < np.where(av, 0.9, 0.1)
    mb = rng.random(n) < np.where(bv, 0.9, 0.1)
    py = 0.10 + 0.35 * ma + 0.30 * mb + 0.12 * ua + 0.10 * ub
    return float(np.mean(np.clip(py, 0, 1)))


# ============================================ structural


def test_2x_frontdoor_structural_general_id():
    """Adjustment fails; the joint effect is identified by the set-valued ID.
    Structurally solved with the joint_general_id pattern + terminal."""
    r = themis.run(_ast_2x_frontdoor())["results"][0]
    assert r["status"] == "structurally_solved", r
    ann = r["extensions"]["joint_identification"]
    assert ann["pattern"] == "joint_general_id", ann
    assert ann["treatments"] == ["a(me)", "b(me)"], ann["treatments"]
    rules = [st["rule"] for st in r["derivation"]["steps"]]
    assert rules == ["general_id_criterion", "identify_via_general_id"], rules
    themis.verify(_ast_2x_frontdoor(), r)        # set-ID re-derivation


# ============================================ numeric recovery + verify


def test_2x_frontdoor_numeric_recovers_and_verifies():
    ast = _ast_2x_frontdoor()
    df = _scm_2x()
    r = themis.estimate(ast, df, ci_bootstrap=100, random_state=1)["results"][0]
    assert r["status"] == "numerically_solved", r
    ne = r["numeric_estimate"]
    assert ne["method"] == "joint_general_id_plugin", ne["method"]
    assert ne["treatments"] == ["a", "b"], ne["treatments"]
    joint = ne["joint_effect"]
    true_ate = _true_joint(True, True) - _true_joint(False, False)
    assert abs(joint["point"] - true_ate) < 0.03, (joint["point"], true_ate)
    assert joint["ci_lower"] <= joint["point"] <= joint["ci_upper"]
    validate_result(r)                            # schema
    themis.verify(ast, r)                         # independent verifier


# ============================================ honest refusal (soundness core)


def test_bow_arc_joint_honest_refusal():
    """A genuine joint hedge (A→Y with A↔Y bow arc): neither adjustment nor the
    set-valued ID identifies it. Refuse — never fabricate a number."""
    ast = _ast_bow_arc()
    s = themis.run(ast)["results"][0]
    assert s["status"] == "needs_investigation", s
    names = [m["name"] for m in s.get("missing_information", [])]
    assert any("joint_not_identifiable" in n for n in names), names
    # data path attaches NO numeric estimate (no silent-wrong general-ID number)
    df = pd.DataFrame({
        "a": [True, False] * 50, "b": [True, False] * 50,
        "z": [True, False] * 50, "y": [True, False] * 50,
    })
    r = themis.estimate(ast, df, ci_bootstrap=0, random_state=1)["results"][0]
    assert "numeric_estimate" not in r, r.get("numeric_estimate")


def test_bow_arc_criterion_rule_rejects_identifiable_claim():
    """Directly: the verifier's general_id_criterion recomputes the set-valued
    ID off ctx.query and REJECTS a forged identifiable=True claim on the bow
    arc — the number can never be licensed for a non-identified joint."""
    from themis.verifier.context import VerificationContext
    from themis.verifier.rules import _rule_general_id_criterion
    from themis.verifier.errors import RuleCheckFailed
    from themis.types import EffectQuery, Intervention, ValuedAtom

    a, b, y, z = (_typed(p) for p in ("a", "b", "y", "z"))
    g = nx.DiGraph()
    g.add_edges_from([(z, a), (z, b), (z, y), (a, y), (b, y)])
    bidir = frozenset({frozenset({a, y})})       # A ↔ Y bow arc
    query = EffectQuery(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=a, value=True),
        given=(),
        extra_interventions=(Intervention(atom=b, value=True),),
    )
    ctx = VerificationContext(graph=g, query=query, bidirected=bidir)
    with pytest.raises(RuleCheckFailed):
        _rule_general_id_criterion(
            ctx, {"graph": g, "x": a, "y": y}, True, 0,
        )


# ============================================ regression: adjustable → backdoor


def test_adjustable_joint_still_routes_backdoor():
    """A fully-observed adjustable joint must NOT hit the general-ID fallback —
    it stays on the joint back-door path (general-ID fires only when adjustment
    fails)."""
    r = themis.run(_ast_adjustable_dag())["results"][0]
    assert r["status"] == "structurally_solved", r
    ann = r["extensions"]["joint_identification"]
    assert ann["pattern"] == "joint_backdoor", ann
    rules = [st["rule"] for st in r["derivation"]["steps"]]
    assert "identify_via_joint_backdoor" in rules, rules
    assert "identify_via_general_id" not in rules, rules


# ============================================ verifier rejects tampering


def test_verify_rejects_point_outside_ci():
    """Tamper the plug-in point outside its CI: the numeric general-ID audit
    rejects."""
    from themis.verifier.errors import VerificationError
    ast = _ast_2x_frontdoor()
    df = _scm_2x()
    r = themis.estimate(ast, df, ci_bootstrap=100, random_state=1)["results"][0]
    for st in r["derivation"]["steps"]:
        if st["rule"] == "numeric_joint_general_id_estimate":
            st["inputs"]["joint_point"] = st["inputs"]["joint_ci_upper"] + 5.0
    joint = r["numeric_estimate"]["joint_effect"]
    joint["point"] = joint["ci_upper"] + 5.0
    with pytest.raises(VerificationError):
        themis.verify(ast, r)


# ============================================ serialization round-trip


def test_extra_interventions_round_trip():
    """The joint treatment vector must survive derivation (de)serialization —
    the verifier reads the SET from ctx.query, so the round-trip is load-
    bearing for the joint general-ID criterion."""
    from themis.verifier.serialization import _query_to_dict, _decode_query
    from themis.types import EffectQuery, Intervention, ValuedAtom

    a, b, c, y = (_typed(p) for p in ("a", "b", "c", "y"))
    q = EffectQuery(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=a, value=True),
        given=(),
        extra_interventions=(
            Intervention(atom=b, value=True),
            Intervention(atom=c, value=False),
        ),
    )
    d = _query_to_dict(q)
    assert len(d["extra_interventions"]) == 2
    q2 = _decode_query(d)
    assert tuple(iv.atom for iv in q2.extra_interventions) == (b, c)
    assert tuple(iv.value for iv in q2.extra_interventions) == (True, False)


def test_single_treatment_effect_serialization_unchanged():
    """A single-treatment effect query omits extra_interventions entirely —
    byte-identical serialization to before the joint field existed."""
    from themis.verifier.serialization import _query_to_dict
    from themis.types import EffectQuery, Intervention, ValuedAtom

    a, y = _typed("a"), _typed("y")
    q = EffectQuery(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=a, value=True),
        given=(),
    )
    d = _query_to_dict(q)
    assert "extra_interventions" not in d
