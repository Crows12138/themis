"""Integration tests for the `causation` query kind — PN / PS / PNS
(Tian & Pearl 2000) wired end-to-end through themis.run + themis.verify.

The pure-formula core lives in tests/test_probabilities_of_causation.py
(verified against the published drug-example numbers). These tests pin
the *integration*: parsing, the observational-joint recovery from theta,
the two ways the interventional risks are obtained (derived via effect
identification vs. user-supplied experimental data), result packaging,
and the independent verifier.
"""
from __future__ import annotations

import copy

import pytest

from themis import kernel

X = {"predicate": "drug", "args": [{"type": "const", "name": "p"}]}
Y = {"predicate": "death", "args": [{"type": "const", "name": "p"}]}


def _prog(query, *, bidirected=False, p_x1=0.5, py_x1=0.2, py_x0=0.1):
    stmts = [{"kind": "cause", "from": X, "to": Y}]
    if bidirected:
        stmts.append({"kind": "bidirected", "left": X, "right": Y})
    stmts += [
        {"kind": "probability", "target": {"atom": X, "value": True},
         "given": [], "value": p_x1},
        {"kind": "probability", "target": {"atom": Y, "value": True},
         "given": [{"atom": X, "value": True}], "value": py_x1},
        {"kind": "probability", "target": {"atom": Y, "value": True},
         "given": [{"atom": X, "value": False}], "value": py_x0},
        {"kind": "query", "id": "q1", "query": query},
    ]
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": stmts,
    }


# ============================================ derived interventional risks


def test_exogenous_monotonic_derives_risks_and_matches_analytic():
    """X→Y, no confounding ⇒ P(Y|do(X))=P(Y|X) is derived from theta.
    With P(x)=0.5, P(y|x)=0.2, P(y|x')=0.1 the analytic monotone points
    are PN=0.5, PNS=0.1, PS=1/9."""
    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    assert r["query_kind"] == "causation"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "derived_identification"
    assert abs(c["p_y_do_x1"] - 0.2) < 1e-9 and abs(c["p_y_do_x0"] - 0.1) < 1e-9
    assert abs(c["pn"]["point"] - 0.5) < 1e-6
    assert abs(c["pns"]["point"] - 0.1) < 1e-6
    assert abs(c["ps"]["point"] - (1.0 / 9.0)) < 1e-6
    # Headline numeric_result carries the PN point.
    assert abs(r["numeric_result"]["value"] - 0.5) < 1e-6
    kernel.verify(prog, r)  # independent audit accepts


def test_measured_confounder_derives_risks_via_backdoor():
    """Z→X, Z→Y, X→Y: do(X) is confounded but identifiable via backdoor
    on the measured Z. The observational joint needs ancestral BN
    factorization (P(X)/P(Y|X) marginals aren't directly in theta), and
    the interventional risks come from the g-formula over Z. Regression:
    an earlier joint-recovery that only did local P(X)·P(Y|X) chain-rule
    failed this whole family with a spurious data gap."""
    Z = {"predicate": "sick", "args": [{"type": "const", "name": "p"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": Z, "to": X},
            {"kind": "cause", "from": Z, "to": Y},
            {"kind": "cause", "from": X, "to": Y},
            {"kind": "probability", "target": {"atom": Z, "value": True},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [{"atom": Z, "value": True}], "value": 0.8},
            {"kind": "probability", "target": {"atom": X, "value": True},
             "given": [{"atom": Z, "value": False}], "value": 0.2},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}, {"atom": Z, "value": True}],
             "value": 0.6},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": True}, {"atom": Z, "value": False}],
             "value": 0.3},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}, {"atom": Z, "value": True}],
             "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": X, "value": False}, {"atom": Z, "value": False}],
             "value": 0.1},
            {"kind": "query", "id": "q1",
             "query": {"kind": "causation", "cause": X, "effect": Y,
                       "monotonic": True}},
        ],
    }
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "derived_identification"
    # Backdoor g-formula: P(Y=1|do(X=1))=Σ_z P(Y=1|X=1,z)P(z)=0.45; do(X=0)=0.30.
    assert abs(c["p_y_do_x1"] - 0.45) < 1e-9
    assert abs(c["p_y_do_x0"] - 0.30) < 1e-9
    # Joint via ancestral factorization (summing over Z).
    assert abs(c["observational_joint"]["p_x1_y1"] - 0.27) < 1e-9
    # Monotone points.
    assert abs(c["pns"]["point"] - 0.15) < 1e-9
    assert abs(c["pn"]["point"] - (0.06 / 0.27)) < 1e-9
    assert abs(c["ps"]["point"] - (0.09 / 0.41)) < 1e-9
    kernel.verify(prog, r)


def test_non_monotonic_returns_bounds_not_points():
    prog = _prog({"kind": "causation", "cause": X, "effect": Y})
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_bounded"
    c = r["extensions"]["causation"]
    for q in ("pn", "ps", "pns"):
        assert "point" not in c[q]
        assert c[q]["lower"] <= c[q]["upper"]
    # Headline is an interval, not a point.
    assert r["numeric_result"]["value"] is None
    assert r["numeric_result"]["interval"]["low"] <= r["numeric_result"]["interval"]["high"]
    kernel.verify(prog, r)


# ============================================ user-supplied experimental risks
# Tian & Pearl (2000) drug-court example: confounded (do(X) not identifiable
# from observation alone), experimental risks supplied from an RCT.


def test_drug_example_experimental_matches_tian_pearl_published():
    prog = _prog(
        {"kind": "causation", "cause": X, "effect": Y, "monotonic": True,
         "experimental_risk_treated": 0.016, "experimental_risk_control": 0.014},
        bidirected=True, py_x1=0.002, py_x0=0.028,
    )
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    c = r["extensions"]["causation"]
    assert c["interventional_risk_provenance"] == "user_experimental"
    # Tian-Pearl eqs (58)-(63): PN=1.0, PNS∈[0.002,0.016], PS∈[0.002,0.031].
    assert abs(c["pn"]["point"] - 1.0) < 1e-3
    assert abs(c["pns"]["lower"] - 0.002) < 1e-3
    assert abs(c["pns"]["upper"] - 0.016) < 1e-3
    assert abs(c["ps"]["lower"] - 0.002) < 1e-3
    assert abs(c["ps"]["upper"] - 0.031) < 1e-3
    kernel.verify(prog, r)


# ============================================ gap paths


def test_confounded_without_experimental_risks_is_a_gap():
    """A bidirected X↔Y bow arc makes P(Y|do(X)) unidentifiable; with no
    experimental risks supplied the query cannot be answered and surfaces
    the experimental-risk escape hatch."""
    prog = _prog(
        {"kind": "causation", "cause": X, "effect": Y, "monotonic": True},
        bidirected=True,
    )
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "needs_investigation"
    names = {m["name"] for m in r["missing_information"]}
    assert "causation:interventional_risk_unavailable" in names


def test_non_binary_cause_is_outside_language():
    Xc = {"predicate": "dose", "args": [{"type": "const", "name": "p"}]}
    prog = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "p"}]},
        "statements": [
            {"kind": "cause", "from": Xc, "to": Y},
            {"kind": "probability", "target": {"atom": Xc, "value": "low"},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Xc, "value": "high"},
             "given": [], "value": 0.5},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": Xc, "value": "low"}], "value": 0.1},
            {"kind": "probability", "target": {"atom": Y, "value": True},
             "given": [{"atom": Xc, "value": "high"}], "value": 0.3},
            {"kind": "query", "id": "q1",
             "query": {"kind": "causation", "cause": Xc, "effect": Y}},
        ],
    }
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "outside_language"
    assert "binary" in r["extensions"]["causation_error"]


# ============================================ verifier independence (tamper)


@pytest.fixture()
def solved():
    prog = _prog({"kind": "causation", "cause": X, "effect": Y,
                  "monotonic": True})
    return prog, kernel.run(prog)["results"][0]


def _step_output_items(result):
    return result["derivation"]["steps"][-1]["output"]["items"]


def test_verify_rejects_tampered_pn_point(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    _step_output_items(rT)["pn"]["items"]["point"] = 0.99
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_tampered_joint_cell_input(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["inputs"]["p_x1_y1"] = 0.3
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_tampered_headline(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["numeric_result"]["value"] = 0.77
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_phantom_point_when_non_monotonic(solved):
    """Flipping monotonic to False while keeping a point must be caught —
    the quantity is not point-identified without monotonicity."""
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["inputs"]["monotonic"] = False
    _step_output_items(rT)["monotonic"] = False
    with pytest.raises(Exception):
        kernel.verify(prog, rT)
