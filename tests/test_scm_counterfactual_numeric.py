"""Deterministic linear-SCM counterfactual — DATA end.

The structural path (``test_scm_counterfactual.py``) computes a unit's
counterfactual from coefficients DECLARED on the cause edges. This module
covers the data end: when the coefficients are NOT declared but a population
DataFrame is available, each linear structural equation is FITTED by per-node
OLS, the unit's exogenous terms are abducted from its ObservationStatements,
and the same abduction-action-prediction arithmetic gives the point.

Conformance SCM (closed-form counterfactual):

    z = U_z ; x = 0.8·z + U_x ; m = 1.5·x + U_m ; y = 2.0·m + 0.5·z + U_y

For a unit (z0, x0, m0, y0), do(x=x′) gives — the z→y term cancels through
abduction —  Y_cf = y0 + (1.5·2.0)·(x′ − x0) = y0 + 3.0·(x′ − x0).
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import kernel
from themis.input.syntactic_validator import validate_result
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*, xprime=5.0, unit=(1.0, 2.0, 4.0, 9.0), coeffs=None,
             observe=("z", "x", "m", "y")):
    """z→x, x→m, m→y, z→y. ``coeffs`` (a,b,c,d) declares edge coefficients
    (z→x, x→m, m→y, z→y) for the structural path; None leaves them unset so
    only the data path can answer. ``unit`` is (z0,x0,m0,y0)."""
    z0, x0, m0, y0 = unit
    obs_vals = {"z": z0, "x": x0, "m": m0, "y": y0}
    stmts = [
        {"kind": "variable", "predicate": "z"},
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "m"},
        {"kind": "variable", "predicate": "y"},
    ]
    edges = [("z", "x"), ("x", "m"), ("m", "y"), ("z", "y")]
    for i, (u, w) in enumerate(edges):
        e = {"kind": "cause", "from": _atom(u), "to": _atom(w)}
        if coeffs is not None:
            e["coefficient"] = coeffs[i]
        stmts.append(e)
    for name in observe:
        stmts.append({"kind": "observation", "atom": _atom(name),
                      "value": obs_vals[name]})
    stmts.append({"kind": "query", "id": "q1", "query": {
        "kind": "scm_counterfactual",
        "intervention": {"atom": _atom("x"), "value": xprime},
        "target": _atom("y")}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": stmts}


def _data(n=200_000, seed=1):
    rng = np.random.default_rng(seed)
    Z = rng.standard_normal(n)
    X = 0.8 * Z + rng.standard_normal(n)
    M = 1.5 * X + rng.standard_normal(n)
    Y = 2.0 * M + 0.5 * Z + rng.standard_normal(n)
    return pd.DataFrame({"z": Z, "x": X, "m": M, "y": Y})


# ============================================ fit recovers the point


def test_data_fit_recovers_counterfactual_and_verifies():
    prog = _program()
    # structural path cannot answer (no declared coefficients)
    s = kernel.run(prog)["results"][0]
    assert s["status"] == "needs_investigation", s

    r = themis.estimate(prog, _data(), ci_bootstrap=150, random_state=1)["results"][0]
    assert r["status"] == "numerically_solved", r
    ne = r["numeric_estimate"]
    assert ne["method"] == "scm_counterfactual_linear_fit"
    # Y_cf = 9 + 3.0*(5-2) = 18
    assert abs(ne["point"] - 18.0) < 0.1, ne["point"]
    assert ne["ci_lower"] <= ne["point"] <= ne["ci_upper"]
    fits = {f["node"]: f for f in ne["node_fits"]}
    assert set(fits) == {"z", "m", "y"}          # intervened x excluded
    assert abs(fits["m"]["coefficients"][0] - 1.5) < 0.05
    validate_result(r)
    kernel.verify(prog, r)


def test_data_point_matches_declared_coefficient_theta_point():
    """With TRUE coefficients declared, the structural theta point and the
    data-fitted point agree (the fit recovers the mechanisms)."""
    coeffs = (0.8, 1.5, 2.0, 0.5)
    prog = _program(coeffs=coeffs)
    s = kernel.run(prog)["results"][0]
    assert s["status"] == "counterfactual_solved"
    theta_point = s["numeric_result"]["value"]
    assert abs(theta_point - 18.0) < 1e-9         # exact from declared coeffs

    r = themis.estimate(prog, _data(), ci_bootstrap=0, random_state=1)["results"][0]
    assert r["status"] == "numerically_solved"
    assert abs(r["numeric_estimate"]["point"] - theta_point) < 0.1


# ============================================ verifier rejects tampering


def _solved(ci_bootstrap=0):
    prog = _program()
    r = themis.estimate(prog, _data(), ci_bootstrap=ci_bootstrap,
                        random_state=1)["results"][0]
    return prog, r


def test_verify_rejects_tampered_coefficient():
    """Flip a recorded fitted coefficient: the strong re-solve of the OLS
    moments disagrees and rejects."""
    prog, r = _solved()
    for f in r["numeric_estimate"]["node_fits"]:
        if f["node"] == "m":
            f["coefficients"][0] += 5.0
    with pytest.raises(VerificationError):
        kernel.verify(prog, r)


def test_verify_rejects_tampered_moment_matrix():
    """Tamper a recorded moment (Xty): re-solving gives a slope that no longer
    matches the recorded coefficient."""
    prog, r = _solved()
    for f in r["numeric_estimate"]["node_fits"]:
        if f["node"] == "m":
            f["xty"][1] *= 1.5
    with pytest.raises(VerificationError):
        kernel.verify(prog, r)


def test_verify_rejects_tampered_point():
    """Move the point (and its display copy so the extension cross-check
    passes): the abduction-action-prediction re-run from the moments + unit
    disagrees and rejects."""
    prog, r = _solved()
    r["numeric_estimate"]["point"] = 42.0
    r["extensions"]["scm_counterfactual"]["target_value"] = 42.0
    with pytest.raises(VerificationError):
        kernel.verify(prog, r)


def test_verify_rejects_display_copy_drift():
    """Tamper only the extension display copy: the kernel cross-check against
    the audited numeric point rejects."""
    prog, r = _solved()
    r["extensions"]["scm_counterfactual"]["target_value"] = 99.0
    with pytest.raises(VerificationError):
        kernel.verify(prog, r)


# ============================================ honest refusals


def test_underobserved_unit_no_number():
    """A relevant variable unobserved for the unit blocks abduction — the data
    path attaches no number (the structural gap stands)."""
    prog = _program(observe=("z", "x", "y"))   # m unobserved
    r = themis.estimate(prog, _data(), ci_bootstrap=0, random_state=1)["results"][0]
    assert r["status"] == "needs_investigation"
    assert "numeric_estimate" not in r


def test_rank_deficient_design_no_number():
    """A collinear parent (an exact copy column) makes the OLS design rank-
    deficient — refuse rather than return a least-norm coefficient."""
    prog = _program()
    # Add a variable m2 that duplicates m, both caused by x and causing y.
    prog["statements"].insert(4, {"kind": "variable", "predicate": "m2"})
    prog["statements"].append({"kind": "cause", "from": _atom("x"), "to": _atom("m2")})
    prog["statements"].append({"kind": "cause", "from": _atom("m2"), "to": _atom("y")})
    prog["statements"].append({"kind": "observation", "atom": _atom("m2"), "value": 4.0})
    df = _data()
    df["m2"] = df["m"]                          # exact collinear copy
    r = themis.estimate(prog, df, ci_bootstrap=0, random_state=1)["results"][0]
    assert "numeric_estimate" not in r
