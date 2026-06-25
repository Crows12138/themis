"""Deterministic linear-SCM counterfactual point — abduction-action-
prediction (Pearl, Glymour & Jewell *Primer* §4.2), wired end-to-end
through themis.run + themis.verify.

The headline conformance is the Primer's worked Model 4.1 (Joe): the
exact same coefficients, evidence, intervention, and answer (Y=1.90).
"""
from __future__ import annotations

import copy

import pytest

from themis import kernel
from themis.runtime.scm_counterfactual import linear_scm_counterfactual
from themis.input.syntactic_validator import validate_result


# ============================================ pure core


def test_core_matches_pearl_model_4_1():
    """Primer Model 4.1: X=Ux; H=0.5X+Uh; Y=0.7X+0.4H+Uy. Joe observed
    X=0.5, H=1, Y=1.5. Abduction ⇒ U=(0.5, 0.75, 0.75); do(H=2) ⇒ Y=1.90."""
    eq = {"X": (), "H": (("X", 0.5),), "Y": (("X", 0.7), ("H", 0.4))}
    obs = {"X": 0.5, "H": 1.0, "Y": 1.5}
    r = linear_scm_counterfactual(
        equations=eq, observed=obs,
        intervention_var="H", intervention_value=2.0,
        target="Y", topo_order=("X", "H", "Y"),
    )
    assert abs(r.noise["X"] - 0.5) < 1e-12
    assert abs(r.noise["H"] - 0.75) < 1e-12
    assert abs(r.noise["Y"] - 0.75) < 1e-12
    assert abs(r.target_value - 1.9) < 1e-12


def test_core_intervention_off_path_returns_factual():
    """Intervening on a variable with no path to the target leaves the
    target at its factual value (the recovered U reconstruct it)."""
    eq = {"X": (), "Y": (("X", 0.7),)}
    obs = {"X": 0.5, "Y": 1.5}
    r = linear_scm_counterfactual(
        equations=eq, observed=obs,
        intervention_var="X", intervention_value=0.5,  # no change
        target="Y", topo_order=("X", "Y"),
    )
    assert abs(r.target_value - 1.5) < 1e-12


# ============================================ end-to-end via themis.run


def _joe_program(intervention_value=2.0, *, coeffs=(0.5, 0.7, 0.4),
                 observe=("X", "H", "Y")):
    X = {"predicate": "X", "args": [{"type": "const", "name": "joe"}]}
    H = {"predicate": "H", "args": [{"type": "const", "name": "joe"}]}
    Y = {"predicate": "Y", "args": [{"type": "const", "name": "joe"}]}
    a, b, c = coeffs
    stmts = [
        {"kind": "cause", "from": X, "to": H, "coefficient": a},
        {"kind": "cause", "from": X, "to": Y, "coefficient": b},
        {"kind": "cause", "from": H, "to": Y, "coefficient": c},
    ]
    obs_vals = {"X": 0.5, "H": 1.0, "Y": 1.5}
    atoms = {"X": X, "H": H, "Y": Y}
    for name in observe:
        stmts.append({"kind": "observation", "atom": atoms[name],
                      "value": obs_vals[name]})
    stmts.append({"kind": "query", "id": "q1", "query": {
        "kind": "scm_counterfactual",
        "intervention": {"atom": H, "value": intervention_value},
        "target": Y}})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "joe"}]},
        "statements": stmts,
    }


def test_run_reproduces_pearl_joe_and_verifies():
    prog = _joe_program()
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "counterfactual_solved"
    assert r["query_kind"] == "scm_counterfactual"
    assert abs(r["numeric_result"]["value"] - 1.9) < 1e-9
    sc = r["extensions"]["scm_counterfactual"]
    assert abs(sc["abducted_noise"]["Y(joe)"] - 0.75) < 1e-9
    assert abs(sc["counterfactual_values"]["H(joe)"] - 2.0) < 1e-9
    validate_result(r)
    kernel.verify(prog, r)   # independent abduction-action-prediction agrees


# ============================================ gap paths


def test_missing_coefficient_is_a_gap():
    """An edge on the path to the target without a coefficient under-
    specifies the SCM — no point can be computed."""
    prog = _joe_program()
    # Drop the coefficient on the H->Y edge.
    for s in prog["statements"]:
        if s.get("kind") == "cause" and s["from"]["predicate"] == "H":
            del s["coefficient"]
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "needs_investigation"
    assert any(m["name"].startswith("coefficient:")
               for m in r["missing_information"])


def test_missing_observation_is_a_gap():
    """A relevant variable not observed for the unit blocks abduction."""
    prog = _joe_program(observe=("X", "Y"))   # H unobserved
    r = kernel.run(prog)["results"][0]
    assert r["status"] == "needs_investigation"
    assert any(m["name"] == "observation:H(joe)"
               for m in r["missing_information"])


# ============================================ verifier independence (tamper)


@pytest.fixture()
def solved():
    prog = _joe_program()
    return prog, kernel.run(prog)["results"][0]


def test_verify_rejects_tampered_output(solved):
    prog, r = solved
    rT = copy.deepcopy(r)
    rT["derivation"]["steps"][-1]["output"]["value"] = 2.5
    rT["numeric_result"]["value"] = 2.5
    with pytest.raises(Exception):
        kernel.verify(prog, rT)


def test_verify_rejects_tampered_coefficient(solved):
    """If the program's coefficient is changed, the verifier's independent
    recomputation no longer matches the (now-stale) claimed point."""
    prog, r = solved
    progT = copy.deepcopy(prog)
    for s in progT["statements"]:
        if s.get("kind") == "cause" and s["from"]["predicate"] == "H":
            s["coefficient"] = 0.9   # was 0.4
    with pytest.raises(Exception):
        kernel.verify(progT, r)
