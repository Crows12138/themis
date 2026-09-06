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

from themis import refusals
from themis.refusals import Refusal
from themis.refusals import EstimatorFailure

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
    _rule_mediation_cde_joint_check,
    _rule_mediation_nde_nie_joint_check,
)
from themis import gaps as _gaps
from tests import caveats


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
    with pytest.raises(EstimatorFailure) as exc:
        estimate_mediation_joint(
            df, treatment="x", outcome="y", mediators=(),
        )
    assert exc.value.failure_type == Refusal.TOO_FEW_INPUTS


def test_duplicate_mediator_raises():
    df, _ = _joint_scm(n=500)
    with pytest.raises(EstimatorFailure) as exc:
        estimate_mediation_joint(
            df, treatment="x", outcome="y", mediators=("m1", "m1"),
        )
    assert exc.value.failure_type == Refusal.DUPLICATE_INPUT


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
    # clean parallel graph: both the joint natural effects AND the
    # CDE-for-a-set identify.
    assert mjd["strategy"] == "nde_nie+cde"
    assert mjd["nde_nie"]["identifiable"] is True
    assert mjd["cde"]["identifiable"] is True
    rules = [s["rule"] for s in res["derivation"]["steps"]]
    assert "mediation_nde_nie_joint_check" in rules
    assert "mediation_cde_joint_check" in rules
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
    mjd = res["extensions"]["mediation_joint_decomposition"]
    assert mjd["mediator_set_valid"] is False
    # both blocks surfaced (non-identifiable) even on a degenerate set
    assert mjd["cde"]["identifiable"] is False


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
# the disclosure layer sees the block
#
# Every producer below used to read `extensions.mediation_decomposition`
# — the SINGLE-mediator key — so a block, which lands under
# `mediation_joint_decomposition`, was invisible to the whole gap layer:
# its identification assumptions never surfaced, and "可识别" on the human
# side read as unconditional. The invariant these pin is parity: on the
# same graph, asking through a block must disclose whatever asking through
# one mediator discloses.
# =====================================================================


def _single_ast_from(joint_ast: dict, keep: str = "m1") -> dict:
    """The same program asked through ONE mediator instead of the block."""
    ast = copy.deepcopy(joint_ast)
    for stmt in ast["statements"]:
        if stmt.get("kind") == "query":
            stmt["query"].pop("mediators")
            stmt["query"]["mediator"] = _atom(keep)
    return ast


def _gap_kinds(res: dict) -> list[str]:
    return [g["kind"] for g in (res.get("data_gap_report") or {}).get("gaps", [])]


def test_block_surfaces_its_identification_assumptions():
    res = themis.run(_joint_ast())["results"][0]
    rows = [
        g for g in res["data_gap_report"]["gaps"]
        if g["kind"] == "mediation_identification_assumption_required"
    ]
    assert len(rows) == 2                          # NDE/NIE + CDE branches
    joined = " ".join(_gaps.described(g) for g in rows)
    # The block's own premises, not the single-mediator ones.
    assert "vanderweele_vansteelandt_2014_joint_natural_effect_conditions" in joined
    assert "controlled_direct_effect_holds_mediator_set_at_a_reference_level" in joined
    # And what the block does NOT claim.
    assert "不拆到单条路径" in joined
    assert "m1(me)" in joined and "m2(me)" in joined
    # The caveat must also reach the human-facing text, not only the report.
    assert "中介分解 NDE/NIE 标识为可识别" in caveats.text(res)


def test_block_and_single_mediator_are_disclosed_alike():
    """The parity invariant. Same graph, same query, one asked through a
    block and one through a single mediator: the gap layer must not go
    quiet just because the answer came back under a different key."""
    joint = themis.run(_joint_ast())["results"][0]
    single = themis.run(_single_ast_from(_joint_ast()))["results"][0]
    def counts(res):
        kinds = _gap_kinds(res)
        return {k: kinds.count(k) for k in set(kinds)}

    # One species is one gap per variable the QUESTION names, and these two
    # questions do not name the same variables: the block asks through m1
    # and m2, the single through m1. So parity is asserted on the species
    # disclosed and on what each per-variable gap is about, rather than on
    # a count that would only match while one of the two was blind to the
    # mediator.
    per_variable = "ambiguous_variable_definition"

    def about(res):
        return {ref["ref_id"]
                for gap in (res.get("data_gap_report") or {}).get("gaps", [])
                if gap["kind"] == per_variable
                for ref in gap.get("provenance") or ()
                if ref.get("ref_kind") == "framing_note"}

    assert counts(joint).keys() == counts(single).keys()
    assert {k: v for k, v in counts(joint).items() if k != per_variable} == \
        {k: v for k, v in counts(single).items() if k != per_variable}
    assert about(joint) == {"x", "y", "m1", "m2"}
    assert about(single) == {"x", "y", "m1"}


def _tainted_ast(joint: bool) -> dict:
    """X→{M1,M2}→Y with W confounding the mediators and the outcome; the
    W→Y edge is an unverified LLM proposal. W reaches the query-relevant
    predicate set ONLY through the decomposition's adjustment list."""
    ast = _joint_ast()
    stmts = ast["statements"]
    stmts.insert(4, {"kind": "variable", "predicate": "w",
                     "domain": [True, False]})
    for a, b in (("w", "m1"), ("w", "m2")):
        stmts.insert(-1, {"kind": "cause", "from": _atom(a), "to": _atom(b)})
    stmts.insert(-1, {"kind": "cause", "from": _atom("w"), "to": _atom("y"),
                      "annotations": {"source": "llm_proposal"}})
    return ast if joint else _single_ast_from(ast)


def test_proposal_edge_on_the_blocks_adjustment_set_is_disclosed():
    """An unverified proposal edge among the adjustment covariates is a
    provenance leak the single-mediator path already caught. The block
    inherits the same disclosure."""
    for joint in (False, True):
        res = themis.run(_tainted_ast(joint))["results"][0]
        ext = res["extensions"]
        dec = (ext.get("mediation_joint_decomposition")
               or ext["mediation_decomposition"])
        assert dec["nde_nie"]["adjustment"] == ["w(me)"], "premise: W is adjusted for"
        assert "unverified_proposal_edge_on_query_path" in _gap_kinds(res), (
            f"proposal edge undisclosed for joint={joint}"
        )


def test_block_dispatch_conflict_is_disclosed():
    """mediator + target_population silently skips a layer; the honesty gap
    is gated on the query naming a mediator, and a block names one too."""
    import json
    import pathlib

    path = (pathlib.Path(themis.__file__).parent.parent / "docs"
            / "l3_simulation" / "case_009_mediation_x_transport.json")
    program = json.loads(path.read_text(encoding="utf-8"))
    for stmt in program["statements"]:
        q = stmt.get("query") if stmt.get("kind") == "query" else None
        if q and q.get("mediator") is not None:
            q["mediators"] = [q.pop("mediator")]
    res = themis.run(program)["results"][0]
    assert "unattempted_layer_due_to_dispatch_conflict" in _gap_kinds(res)
    gap = next(g for g in res["data_gap_report"]["gaps"]
               if g["kind"] == "unattempted_layer_due_to_dispatch_conflict")
    assert "`mediators`" in _gaps.described(gap)     # names the field it saw


def test_a_block_of_one_is_still_answered():
    """`mediators: [m]` used to route nowhere: not to the joint path (which
    demanded >= 2) and not to the single-mediator path (which reads the
    singular field), so the decomposition simply did not happen and nothing
    said so. A set of one is a set."""
    ast = _joint_ast()
    for stmt in ast["statements"]:
        if stmt.get("kind") == "query":
            stmt["query"]["mediators"] = [_atom("m1")]
    res = themis.run(ast)["results"][0]
    mjd = res["extensions"]["mediation_joint_decomposition"]
    assert mjd["mediators"] == ["m1(me)"]
    assert mjd["mediator_set_valid"] is True
    assert mjd["nde_nie"]["identifiable"] is True
    assert _gap_kinds(res).count(
        "mediation_identification_assumption_required") == 2
    themis.verify(ast, res)


def test_a_block_of_one_reaches_the_data_end_too():
    """The data-end mirror of ``test_a_block_of_one_is_still_answered``.

    Identification routes ``mediators: [m]`` to the joint block on the
    principle that a set of one is a set; the estimation dispatch kept a
    ``>= 2`` guard, so the same envelope came back carrying the joint
    identification block NEXT TO a plain back-door TOTAL effect — a number
    about a different estimand, with nothing saying so. One query routes one
    way, in both layers.
    """
    df, _ = _joint_scm(n=8000, seed=7)
    ast = _joint_ast()
    for stmt in ast["statements"]:
        if stmt.get("kind") == "query":
            stmt["query"]["mediators"] = [_atom("m1")]
    res = themis.estimate(ast, df, random_state=42)["results"][0]

    # identification still says "I decomposed this block" ...
    assert res["extensions"]["mediation_joint_decomposition"][
        "nde_nie"]["identifiable"] is True
    # ... so the number attached to it must be that block's decomposition.
    ne = res["numeric_estimate"]
    assert ne["method"] == "mediation_joint_linear"
    assert ne["mediators"] == ["m1"]

    # and it is the block's NDE/NIE, not the total effect. At k=1 the joint
    # estimator IS the classical single-mediator one (pinned independently by
    # test_k1_equivalence_to_single_mediator_linear), so that is the oracle.
    oracle = estimate_mediation(
        df, treatment="x", outcome="y", mediator="m1", n_rep=10,
    )
    assert abs(ne["decomposition"]["nie"]["point"] - oracle.nie_point) < 0.05
    assert abs(ne["decomposition"]["nde"]["point"] - oracle.nde_point) < 0.05
    themis.verify(ast, res)


def test_the_block_carries_the_share_and_the_set_it_is_through():
    """A share is a fraction OF something, and here that something is the
    block taken whole — never the sum of per-mediator shares, which are
    not identified at all.

    This used to read a Chinese headline the estimator prepended to the
    envelope, which said the share and named the set in one sentence. The
    headline is gone (#395): it restated two fields sitting beside it and
    said them in whichever language the kernel defaulted to. The two
    fields are what a reader surface composes that sentence from, so they
    are what is pinned.
    """
    df, _truth = _joint_scm(n=4000, seed=7)
    res = themis.estimate(_joint_ast(), df, random_state=42)["results"][0]
    ne = res["numeric_estimate"]
    pm = ne["decomposition"]["proportion_mediated"]
    assert pm["point"] is not None
    assert pm["ci_lower"] is not None and pm["ci_upper"] is not None
    assert ne["mediators"] == ["m1", "m2"]


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
        _rule_mediation_cde_joint_check,
        _rule_identify_via_mediation_joint,
    ):
        names = set(fn.__code__.co_names)
        assert not (names & forbidden), (
            f"{fn.__name__} references forbidden symbol: {names & forbidden}"
        )


# =====================================================================
# CDE-for-a-set (controlled direct effect holding the whole block fixed)
# =====================================================================


def test_cde_for_set_identifiable_clean_parallel():
    """Clean parallel mediators: the CDE-for-a-set identifies with no
    adjustment, alongside the joint NDE/NIE."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2"), ("M2", "Y")])
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.cde.identifiable is True
    assert r.cde.adjustment == frozenset()


def test_cde_identifiable_where_nde_fails_under_latent_x_m():
    """A LATENT X<->M2 confounder sinks the joint natural effects (the M2
    no-confounding condition fails), but the CDE-for-a-set is still
    identifiable — it never needs that condition. The whole point of a
    separate CDE branch."""
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2"), ("M2", "Y")])
    bidir = frozenset({frozenset({"X", "M2"})})
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"}, bidirected=bidir)
    assert r.nde_nie.identifiable is False
    assert r.cde.identifiable is True
    assert r.cde.adjustment == frozenset()


def test_cde_needs_baseline_confounder_in_adjustment():
    """C→X, C→Y baseline confounder: CDE-for-a-set needs W={C}, same as
    the joint natural effects."""
    g = nx.DiGraph(
        [("C", "X"), ("C", "Y"), ("X", "M1"), ("M1", "Y"),
         ("X", "M2"), ("M2", "Y")]
    )
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.cde.identifiable is True
    assert r.cde.adjustment == frozenset({"C"})


def test_cde_post_treatment_confounder_not_backdoor_identifiable():
    """A post-treatment (intermediate) confounder L of the M2→Y edge that is
    itself affected by X: neither the joint natural effects nor the backdoor
    CDE-for-a-set identify (L needs the longitudinal g-formula — honest
    limitation of the backdoor-only method)."""
    g = nx.DiGraph(
        [("X", "M1"), ("M1", "Y"), ("X", "M2"), ("M2", "Y"),
         ("X", "L"), ("L", "M2"), ("L", "Y")]
    )
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.nde_nie.identifiable is False
    assert r.cde.identifiable is False


def test_cde_invalid_set_empty_attempt():
    g = nx.DiGraph([("X", "M1"), ("M1", "Y"), ("X", "M2")])
    r = mediation_sets_joint(g, "X", "Y", {"M1", "M2"})
    assert r.mediator_set_valid is False
    assert r.cde.identifiable is False


def _joint_cde_truth(seed=0):
    """The same SCM as _joint_scm, exposing the structural CDE truth:
    CDE(m*) = beta_x + g1*m1* + g2*m2*  (m1*=m2*=m*)."""
    bx, g1, g2 = 0.5, 0.3, -0.2
    return {"cde0": bx, "cde1": bx + g1 + g2}


def test_joint_cde_recovers_truth():
    df, _ = _joint_scm()
    est = estimate_mediation_joint(
        df, treatment="x", outcome="y", mediators=("m1", "m2"), n_rep=40,
    )
    truth = _joint_cde_truth()
    c0 = est.cde["reference_control"]["point"]
    c1 = est.cde["reference_treated"]["point"]
    assert abs(c0 - truth["cde0"]) < 0.03
    assert abs(c1 - truth["cde1"]) < 0.03
    assert est.cde["reference_control"]["mediator_level"] == 0.0
    assert est.cde["reference_treated"]["mediator_level"] == 1.0


def test_joint_cde_bridge_reproduces_point():
    """CDE(m*=0)=beta_x and CDE(m*=1)=beta_x+sum_j gamma_j are exact
    functionals of the recorded coefficients — the bridge the verifier
    re-derives on the linear path."""
    df, _ = _joint_scm(n=8000)
    est = estimate_mediation_joint(
        df, treatment="x", outcome="y", mediators=("m1", "m2"), n_rep=10,
    )
    oc = est.sufficient_statistics["outcome_coefficients"]
    beta_x = oc["treatment"]
    sum_g = sum(oc["interactions"].values())
    assert abs(est.cde["reference_control"]["point"] - beta_x) < 1e-9
    assert abs(est.cde["reference_treated"]["point"] - (beta_x + sum_g)) < 1e-9


def test_estimate_attaches_cde_and_verifies():
    df, _ = _joint_scm(n=6000, seed=1)
    ast = _joint_ast()
    res = themis.estimate(ast, df, random_state=42)["results"][0]
    d = res["numeric_estimate"]["decomposition"]
    assert "cde" in d
    assert "reference_control" in d["cde"] and "reference_treated" in d["cde"]
    # linear CDE(m*=0) equals the recorded treatment coefficient
    beta_x = d["sufficient_statistics"]["outcome_coefficients"]["treatment"]
    assert abs(d["cde"]["reference_control"]["point"] - beta_x) < 1e-9
    # verify must not raise (re-derives the cde from the coefficients)
    themis.verify(ast, res)


def test_verifier_rejects_tampered_cde():
    """Strong verification: corrupting a reported CDE point mismatches the
    coefficient re-derivation."""
    df, _ = _joint_scm(n=4000, seed=2)
    ast = _joint_ast()
    res = themis.estimate(ast, df, random_state=42)["results"][0]
    bad = copy.deepcopy(res)
    bad["numeric_estimate"]["decomposition"]["cde"][
        "reference_control"]["point"] += 0.5
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_run_surfaces_cde_identifiability_and_verifies():
    ast = _joint_ast()
    res = themis.run(ast)["results"][0]
    mjd = res["extensions"]["mediation_joint_decomposition"]
    assert mjd["cde"]["identifiable"] is True
    assert mjd["cde"]["adjustment"] == []
    themis.verify(ast, res)


# =====================================================================
# theta / SCM numeric end — the joint block evaluated against declared
# CPTs, the parity counterpart of the DATA end above
# =====================================================================


def _pr(target, tval, given, value):
    return {
        "kind": "probability",
        "target": {"atom": _atom(target), "value": tval},
        "given": [{"atom": _atom(g), "value": v} for g, v in given],
        "value": value,
    }


# Parallel two-mediator SCM with a measured baseline confounder W.
_P_W = {True: 0.4, False: 0.6}
_P_X = {True: 0.7, False: 0.25}                    # P(X=1 | W)
_P_M1 = {(True, True): 0.8, (True, False): 0.35,   # P(M1=1 | X, W)
         (False, True): 0.5, (False, False): 0.15}
_P_M2 = {(True, True): 0.6, (True, False): 0.3,    # P(M2=1 | X, W)
         (False, True): 0.45, (False, False): 0.1}


def _p_y(x, m1, m2, w):
    """P(Y=1 | X, M1, M2, W) — includes an X·M1 interaction so the two
    Pearl decompositions genuinely differ."""
    v = 0.05 + 0.30 * x + 0.25 * m1 + 0.20 * m2 + 0.10 * w
    v += 0.08 * (x and m1)
    return min(0.98, v)


def _joint_theta_ast(with_confounder=True):
    """Two parallel mediators + a measured confounder, with a FULL theta.

    Crucially theta declares only the per-mediator CPTs P(Mj | X, W) —
    never a joint mediator distribution. The block's joint law has to come
    from the chain rule plus the graph-guarded reduction.
    """
    stmts = [
        {"kind": "variable", "predicate": p, "domain": [True, False]}
        for p in ("w", "x", "m1", "m2", "y")
    ]
    edges = [("x", "m1"), ("m1", "y"), ("x", "m2"), ("m2", "y"), ("x", "y")]
    if with_confounder:
        edges += [("w", "x"), ("w", "y"), ("w", "m1"), ("w", "m2")]
    stmts += [{"kind": "cause", "from": _atom(f), "to": _atom(t)}
              for f, t in edges]

    for wv in (True, False):
        stmts.append(_pr("w", wv, [], _P_W[wv]))
        for xv in (True, False):
            stmts.append(_pr("x", xv, [("w", wv)],
                             _P_X[wv] if xv else 1 - _P_X[wv]))
            for mv in (True, False):
                p1 = _P_M1[(xv, wv)]
                p2 = _P_M2[(xv, wv)]
                stmts.append(_pr("m1", mv, [("x", xv), ("w", wv)],
                                 p1 if mv else 1 - p1))
                stmts.append(_pr("m2", mv, [("x", xv), ("w", wv)],
                                 p2 if mv else 1 - p2))
            for m1v in (True, False):
                for m2v in (True, False):
                    py = _p_y(xv, m1v, m2v, wv)
                    for yv in (True, False):
                        stmts.append(_pr(
                            "y", yv,
                            [("x", xv), ("m1", m1v), ("m2", m2v), ("w", wv)],
                            py if yv else 1 - py,
                        ))

    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
        "mediators": [_atom("m1"), _atom("m2")],
    }})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def _oracle_potential(x_outer, x_inner):
    """E[Y(x_outer, M(x_inner))] by DIRECT enumeration of the declared
    structural CPTs — written from the VanderWeele-Vansteelandt definition,
    never touching formula_builder or the scheduler."""
    total = 0.0
    for w in (True, False):
        inner = 0.0
        for m1 in (True, False):
            for m2 in (True, False):
                p1 = _P_M1[(x_inner, w)]
                p2 = _P_M2[(x_inner, w)]
                inner += (
                    _p_y(x_outer, m1, m2, w)
                    * (p1 if m1 else 1 - p1)
                    * (p2 if m2 else 1 - p2)
                )
        total += _P_W[w] * inner
    return total


def _oracle_block_cde(m1v, m2v):
    t = sum(_P_W[w] * _p_y(True, m1v, m2v, w) for w in (True, False))
    c = sum(_P_W[w] * _p_y(False, m1v, m2v, w) for w in (True, False))
    return t - c


def test_joint_theta_numeric_matches_enumeration_oracle():
    """The joint natural effects computed against theta equal an
    independent brute-force enumeration of the same CPTs."""
    ast = _joint_theta_ast()
    res = themis.run(ast)["results"][0]
    assert res["status"] == "numerically_solved"
    num = res["extensions"]["mediation_joint_decomposition"]["numeric"]

    e_t = _oracle_potential(True, True)
    e_c = _oracle_potential(False, False)
    e_x = _oracle_potential(True, False)
    for key, expected in (
        ("e_y_treated", e_t),
        ("e_y_control", e_c),
        ("e_y_cross_treated_outer", e_x),
        ("te", e_t - e_c),
        ("nde_at_control", e_x - e_c),
        ("nie_at_treated", e_t - e_x),
    ):
        assert abs(num[key] - expected) < 1e-12, key
    assert abs(res["numeric_result"]["value"] - (e_t - e_c)) < 1e-12


def test_joint_theta_block_cde_matches_oracle_over_the_grid():
    """CDE-for-a-set: one entry per reference point of the block, keyed by
    the mediator values joined in block order."""
    res = themis.run(_joint_theta_ast())["results"][0]
    cde = res["extensions"]["mediation_joint_decomposition"]["numeric"]["cde"]
    assert set(cde) == {"True|True", "True|False", "False|True", "False|False"}
    for m1v in (True, False):
        for m2v in (True, False):
            got = cde[f"{m1v}|{m2v}"]
            assert abs(got - _oracle_block_cde(m1v, m2v)) < 1e-12


def test_joint_theta_needs_no_declared_joint_mediator_distribution():
    """The de-risked design claim, pinned: theta declares only the
    per-mediator CPTs, yet the block's joint law resolves."""
    ast = _joint_theta_ast()
    declared = [
        s for s in ast["statements"]
        if s["kind"] == "probability"
        and s["target"]["atom"]["predicate"] in ("m1", "m2")
    ]
    # no CPT of one mediator ever conditions on the other
    for s in declared:
        given = {g["atom"]["predicate"] for g in s["given"]}
        assert not ({"m1", "m2"} & given)
    res = themis.run(ast)["results"][0]
    assert res["status"] == "numerically_solved"


def test_joint_theta_both_pearl_decompositions_close():
    """TE = NDE_at_control + NIE_at_treated = NDE_at_treated + NIE_at_control."""
    res = themis.run(_joint_theta_ast())["results"][0]
    n = res["extensions"]["mediation_joint_decomposition"]["numeric"]
    assert abs(n["te"] - (n["nde_at_control"] + n["nie_at_treated"])) < 1e-12
    assert abs(n["te"] - (n["nde_at_treated"] + n["nie_at_control"])) < 1e-12


def test_joint_theta_verify_round_trip():
    ast = _joint_theta_ast()
    res = themis.run(ast)["results"][0]
    rules = [s["rule"] for s in res["derivation"]["steps"]]
    assert "identify_via_mediation_joint" in rules
    assert rules[-2:] == ["mediation_numeric_evaluate", "numeric_result"]
    themis.verify(ast, res)


def test_joint_theta_verify_rejects_tampered_effect():
    ast = _joint_theta_ast()
    res = themis.run(ast)["results"][0]
    bad = copy.deepcopy(res)
    for step in bad["derivation"]["steps"]:
        if step["rule"] == "mediation_numeric_evaluate":
            step["output"]["items"]["nie_at_treated"] += 0.05
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_joint_theta_verify_rejects_tampered_block_cde():
    ast = _joint_theta_ast()
    res = themis.run(ast)["results"][0]
    bad = copy.deepcopy(res)
    for step in bad["derivation"]["steps"]:
        if step["rule"] == "mediation_numeric_evaluate":
            step["output"]["items"]["cde"]["items"]["True|False"] = 0.999
    with pytest.raises(Exception):
        themis.verify(ast, bad)


def test_joint_theta_verify_rejects_a_dropped_mediator():
    """A block that quietly sheds a mediator answers a DIFFERENT question.
    The numbers would be internally consistent, so only checking them
    against the query's declared set catches it."""
    ast = _joint_theta_ast()
    res = themis.run(ast)["results"][0]
    bad = copy.deepcopy(res)
    for step in bad["derivation"]["steps"]:
        if step["rule"] == "mediation_numeric_evaluate":
            items = step["inputs"]["mediators"]["items"]
            assert len(items) == 2
            step["inputs"]["mediators"]["items"] = items[:1]
    with pytest.raises(Exception, match="not the ones asked for"):
        themis.verify(ast, bad)


def test_joint_theta_without_theta_stays_structural():
    """No CPTs declared → honest structural answer, no fabricated number."""
    res = themis.run(_joint_ast())["results"][0]
    assert res["status"] == "structurally_solved"
    assert res.get("numeric_result") is None


def test_cde_reference_grid_capped(monkeypatch):
    """The reference grid is the Cartesian product of the block's domains,
    so it is bounded rather than enumerated without limit."""
    from themis.runtime import scheduler as sched
    monkeypatch.setattr(sched, "_CDE_REFERENCE_POINT_CAP", 2)
    res = themis.run(_joint_theta_ast())["results"][0]
    num = res["extensions"]["mediation_joint_decomposition"]["numeric"]
    assert num["cde_status"]["status"] == "too_many_reference_points"
    assert num["cde_status"]["reference_point_count"] == 4
    assert "cde" not in num
    # the natural effects are unaffected — they marginalise the block
    assert abs(num["te"] - (_oracle_potential(True, True)
                            - _oracle_potential(False, False))) < 1e-12


def _bare(p):
    from themis.types import Atom
    return Atom(predicate=p, args=())


def test_mediator_block_order_is_topological():
    """A chained block M2 → M1 must factorise in that order, so the chain
    rule asks for P(M1 | M2, ...) — the CPT the graph actually names."""
    from themis.runtime.scheduler import _mediator_block_order
    x, y, m1, m2 = _bare("x"), _bare("y"), _bare("m1"), _bare("m2")
    g = nx.DiGraph([(x, m2), (m2, m1), (m1, y), (x, m1)])
    assert _mediator_block_order(g, (m1, m2)) == (m2, m1)
    assert _mediator_block_order(g, (m2, m1)) == (m2, m1)


def test_mediator_block_order_falls_back_deterministically():
    """A mediator absent from the graph must not produce an arbitrary
    order — name order is the documented fallback."""
    from themis.runtime.scheduler import _mediator_block_order
    x, y, m1 = _bare("x"), _bare("y"), _bare("m1")
    g = nx.DiGraph([(x, m1), (m1, y)])
    mb, ma = _bare("mb"), _bare("ma")
    assert _mediator_block_order(g, (mb, ma)) == (ma, mb)


def test_joint_potential_outcome_formula_uses_the_chain_rule():
    """The block's joint law is ∏_j P(Mj | M_<j, x_inner, W) — each factor
    conditions on the mediators before it, and on the INNER arm."""
    from themis.runtime.formula_builder import (
        mediation_potential_outcome_formula,
    )
    from themis.types import Atom, ProductExpr, SumExpr, ValuedAtom

    def at(p):
        return Atom(predicate=p, args=())

    y, x, m1, m2 = at("y"), at("x"), at("m1"), at("m2")
    f = mediation_potential_outcome_formula(
        target=ValuedAtom(atom=y, value=True),
        intervention_outer=ValuedAtom(atom=x, value=True),
        intervention_inner=ValuedAtom(atom=x, value=False),
        mediators=(m1, m2),
    )
    # two mediator sums wrapping the product
    assert isinstance(f, SumExpr) and f.over == m1
    assert isinstance(f.body, SumExpr) and f.body.over == m2
    body = f.body.body
    assert isinstance(body, ProductExpr)
    y_cond, m1_cond, m2_cond = body.terms
    # outcome conditions on BOTH mediators and the OUTER arm
    assert y_cond.target.atom == y
    assert {g.atom for g in y_cond.given} == {x, m1, m2}
    assert next(g for g in y_cond.given if g.atom == x).value is True
    # first mediator factor: inner arm, no other mediator
    assert m1_cond.target.atom == m1
    assert {g.atom for g in m1_cond.given} == {x}
    assert next(g for g in m1_cond.given if g.atom == x).value is False
    # second mediator factor: inner arm AND the first mediator
    assert m2_cond.target.atom == m2
    assert {g.atom for g in m2_cond.given} == {x, m1}


def test_single_mediator_block_reproduces_the_classical_formula():
    """k=1 must be the classical Pearl 2001 shape — the generalisation is
    a superset, not a replacement."""
    from themis.runtime.formula_builder import (
        mediation_potential_outcome_formula,
    )
    from themis.types import Atom, ProductExpr, SumExpr, ValuedAtom

    def at(p):
        return Atom(predicate=p, args=())

    y, x, m = at("y"), at("x"), at("m")
    f = mediation_potential_outcome_formula(
        target=ValuedAtom(atom=y, value=True),
        intervention_outer=ValuedAtom(atom=x, value=True),
        intervention_inner=ValuedAtom(atom=x, value=False),
        mediators=(m,),
    )
    assert isinstance(f, SumExpr) and f.over == m
    assert isinstance(f.body, ProductExpr)
    y_cond, m_cond = f.body.terms          # exactly two factors, no extras
    assert {g.atom for g in y_cond.given} == {x, m}
    assert {g.atom for g in m_cond.given} == {x}


# ---------------------------------------------------------------------
# anti-silent-wrong: the chain rule demands P(Mj | M_<j, X, W), and a
# declared marginal may only stand in for it when the GRAPH says so
# ---------------------------------------------------------------------


def _chained_block_marginal_only_ast():
    """X→M1→M2→Y (+M1→Y, X→Y) with theta declaring only P(M2|X).

    The block's chain rule demands P(M2|M1,X); M1 → M2 makes the marginal
    an invalid substitute, and theta has no other route to the conditional.
    There is therefore NO correct natural-effect number to report here.
    """
    stmts = [{"kind": "variable", "predicate": p, "domain": [True, False]}
             for p in ("x", "m1", "m2", "y")]
    stmts += [{"kind": "cause", "from": _atom(f), "to": _atom(t)} for f, t in
              [("x", "m1"), ("m1", "m2"), ("m2", "y"), ("m1", "y"), ("x", "y")]]
    p_m1 = {True: 0.8, False: 0.3}
    p_m2_given_m1x = {(True, True): 0.9, (True, False): 0.2,
                      (False, True): 0.7, (False, False): 0.1}
    for xv in (True, False):
        stmts.append(_pr("x", xv, [], 0.5))
        # marginalised over M1 — the ONLY M2 law declared
        p1 = p_m1[xv]
        pm2 = p1 * p_m2_given_m1x[(True, xv)] + (1 - p1) * p_m2_given_m1x[(False, xv)]
        for mv in (True, False):
            stmts.append(_pr("m1", mv, [("x", xv)],
                             p_m1[xv] if mv else 1 - p_m1[xv]))
            stmts.append(_pr("m2", mv, [("x", xv)], pm2 if mv else 1 - pm2))
        for m1v in (True, False):
            for m2v in (True, False):
                py = min(0.98, 0.05 + 0.3 * xv + 0.25 * m1v + 0.2 * m2v)
                for yv in (True, False):
                    stmts.append(_pr(
                        "y", yv, [("x", xv), ("m1", m1v), ("m2", m2v)],
                        py if yv else 1 - py,
                    ))
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect",
        "intervention": {"atom": _atom("x"), "value": True},
        "target": {"atom": _atom("y"), "value": True},
        "given": [],
        "mediators": [_atom("m1"), _atom("m2")],
    }})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": stmts,
    }


def test_chained_block_refuses_the_unlicensed_marginal():
    """The producer must NOT substitute the declared marginal P(M2|X) for
    the demanded P(M2|M1,X): the graph makes them dependent, so any number
    would be wrong. Honest refusal, naming the missing CPT and the reason."""
    ast = _chained_block_marginal_only_ast()
    res = themis.run(ast)["results"][0]
    assert res["status"] == "structurally_solved"
    assert res.get("numeric_result") is None
    num = res["extensions"]["mediation_joint_decomposition"]["numeric"]
    assert "te" not in num
    status = num["nde_nie_status"]
    assert status["status"] == "insufficient_theta"
    assert "m2" in status["missing_key"] and "m1" in status["missing_key"]
    themis.verify(ast, res)


def test_chained_block_still_reports_the_block_cde():
    """CDE fixes the whole block by do, so it never needs the joint
    mediator law — it stays available exactly where the natural effects
    cannot be evaluated."""
    res = themis.run(_chained_block_marginal_only_ast())["results"][0]
    num = res["extensions"]["mediation_joint_decomposition"]["numeric"]
    assert set(num["cde"]) == {
        "True|True", "True|False", "False|True", "False|False"
    }


def test_parallel_block_still_accepts_the_licensed_marginal():
    """The guard must not over-refuse: when the graph DOES imply the
    mediators are conditionally independent, the declared marginals are
    the right quantities and the block evaluates."""
    res = themis.run(_joint_theta_ast())["results"][0]
    assert res["status"] == "numerically_solved"


# ---------------------------------------------------------------------
# two numeric channels on one result
#
# Once a decomposition evaluates against theta, a query that ALSO carries
# a DataFrame ends up with two independent numbers for the same split: the
# derivation's theta evaluation and the attached data estimate. verify has
# to audit each on its own terms — comparing the data estimate against the
# theta derivation's terminal would reject an honest result. The
# single-mediator case is exercised here too, alongside the block, because
# both ride the same routing.
# ---------------------------------------------------------------------


def _binary_df(n=6000, seed=0):
    """A DataFrame over the same variables as _joint_theta_ast."""
    rng = np.random.default_rng(seed)
    w = rng.random(n) < 0.4
    x = rng.random(n) < np.where(w, 0.7, 0.25)
    m1 = rng.random(n) < np.where(x, np.where(w, .8, .35), np.where(w, .5, .15))
    m2 = rng.random(n) < np.where(x, np.where(w, .6, .3), np.where(w, .45, .1))
    py = np.clip(.05 + .3 * x + .25 * m1 + .2 * m2 + .1 * w + .08 * (x & m1),
                 0, .98)
    return pd.DataFrame({
        "w": w, "x": x, "m1": m1, "m2": m2, "y": rng.random(n) < py,
    })


def test_block_carries_theta_and_data_channels_and_both_verify():
    ast = _joint_theta_ast()
    res = themis.estimate(ast, _binary_df())["results"][0]
    assert res["status"] == "numerically_solved"
    # theta channel: exact, terminates the derivation
    theta_te = res["extensions"]["mediation_joint_decomposition"]["numeric"]["te"]
    assert abs(res["numeric_result"]["value"] - theta_te) < 1e-12
    # data channel: a separate estimate of the same split
    ne = res["numeric_estimate"]
    assert ne["method"].startswith("mediation_joint_")
    assert res["derivation"]["steps"][-1]["rule"] == "numeric_result"
    themis.verify(ast, res)


def test_single_mediator_carries_theta_and_data_channels_and_both_verify():
    """Parity anchor: the same routing serves one mediator and a block."""
    ast = _joint_theta_ast()
    for s in ast["statements"]:
        if s.get("kind") == "query":
            del s["query"]["mediators"]
            s["query"]["mediator"] = _atom("m1")
    res = themis.estimate(ast, _binary_df())["results"][0]
    assert res["status"] == "numerically_solved"
    assert res["derivation"]["steps"][-1]["rule"] == "numeric_result"
    assert res["numeric_estimate"]["method"].startswith("mediation_")
    themis.verify(ast, res)
