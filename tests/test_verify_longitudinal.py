"""Structural identification + numeric audit of a longitudinal g-formula /
IPW-MSM strategy-contrast answer (``verify_longitudinal_numeric`` and the
``identify_via_gformula`` terminal).

Before Phase 7.L wired the structural side, a time-varying strategy number
rode on a ``needs_investigation`` result with NO derivation, so
``themis.verify`` refused to audit it at all (the no-verification-by-omission
guard) — the number shipped entirely outside the audit contract. Now the
scheduler identifies the strategy effect via the g-formula / sequential
back-door criterion (``identify_via_gformula``), the estimation dispatch
flips the result to numerically_solved with the number attached (mirroring
transport), and this verifier re-derives the number:

- ``longitudinal_ipw_msm`` (STRONG-ish): the reported point and both strategy
  means are exact closed forms of the recorded marginal-structural-model
  coefficients β — recompute and reject a mismatch, so a tampered point /
  mean / single coefficient is caught. A fully self-consistent forgery of the
  whole β vector is the honest ceiling (no re-fit).
- ``longitudinal_gformula`` (INVARIANTS): the two means come from a black-box
  Monte-Carlo simulation — only ``point = E_treated − E_control`` and the
  sim / bootstrap counts are checkable.

And the honest identification GATE: when an unmeasured confounder breaks
sequential exchangeability, the g-formula would be biased, so no number ships.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.verify import VerificationError, verify_longitudinal_numeric


def _expit(x):
    return 1.0 / (1.0 + np.exp(-x))


def _gen_dgp(n=1500, seed=8):
    """Canonical 2-time-point DGP with a time-varying confounder (L1)
    affected by past treatment (A0) — the structure that makes ordinary
    adjustment biased and g-methods necessary."""
    rng = np.random.default_rng(seed)
    L0 = rng.normal(0, 1, n)
    A0 = rng.random(n) < _expit(0.5 * L0)
    L1 = 1.0 * A0 + 0.5 * L0 + rng.normal(0, 1, n)
    A1 = rng.random(n) < _expit(0.8 * L1 - 0.4)
    Y = 2.0 * A0 + 3.0 * A1 + 1.5 * L1 + 0.5 * L0 + rng.normal(0, 1, n)
    return pd.DataFrame({"L0": L0, "A0": A0, "L1": L1, "A1": A1, "Y": Y})


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "subj"}]}


def _program(estimator, extra=None):
    stmts = [
        {"kind": "variable", "predicate": "L0"},
        {"kind": "variable", "predicate": "A0", "domain": [True, False]},
        {"kind": "variable", "predicate": "L1"},
        {"kind": "variable", "predicate": "A1", "domain": [True, False]},
        {"kind": "variable", "predicate": "Y"},
        {"kind": "cause", "from": _atom("A0"), "to": _atom("L1")},
        {"kind": "cause", "from": _atom("L1"), "to": _atom("A1")},
        {"kind": "cause", "from": _atom("L1"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("A0"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("A1"), "to": _atom("Y")},
        {"kind": "cause", "from": _atom("L0"), "to": _atom("A0")},
        {"kind": "cause", "from": _atom("L0"), "to": _atom("Y")},
    ]
    if extra:
        stmts.extend(extra)
    stmts.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "target": {"atom": _atom("Y"), "value": True},
        "intervention": {"atom": _atom("A1"), "value": True}, "given": []}})
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "subj"}]},
        "options": {"longitudinal": {
            "estimator": estimator, "treatments": ["A0", "A1"],
            "confounders_by_time": [["L0"], ["L1"]], "outcome": "Y",
            "strategy_treated": 1, "strategy_control": 0,
            "n_sim": 2000, "ci_bootstrap": 0,
        }},
        "statements": stmts,
    }


# Unmeasured common cause of a treatment and the outcome — breaks
# sequential exchangeability at A1, so the g-formula is not identified.
_LATENT = [{"kind": "bidirected", "left": _atom("A1"), "right": _atom("Y")}]


@pytest.fixture(scope="module")
def gformula_result():
    out = themis.estimate(_program("gformula"), _gen_dgp(), ci_bootstrap=0)
    return out["results"][0]


@pytest.fixture(scope="module")
def ipw_msm_result():
    out = themis.estimate(_program("ipw_msm"), _gen_dgp(), ci_bootstrap=0)
    return out["results"][0]


def _ne(result):
    return copy.deepcopy(result["numeric_estimate"])


# --- structural identification -----------------------------------------------


def test_gformula_structural_identification():
    r = themis.run(_program("gformula"))["results"][0]
    assert r["status"] == "structurally_solved"
    ident = r["extensions"]["longitudinal_identification"]
    assert ident["identified"] is True
    assert ident["estimand"] == "time_varying_strategy_contrast"
    assert r["derivation"]["steps"][-1]["rule"] == "identify_via_gformula"


def test_estimate_flips_to_numerically_solved(ipw_msm_result):
    assert ipw_msm_result["status"] == "numerically_solved"
    assert ipw_msm_result["numeric_estimate"]["method"] == "longitudinal_ipw_msm"
    assert ipw_msm_result["derivation"]["steps"][-1]["rule"] == "identify_via_gformula"


# --- round-trip: genuine answers pass verify ---------------------------------


def test_gformula_round_trips(gformula_result):
    assert themis.verify(_program("gformula"), gformula_result) is None


def test_ipw_msm_round_trips(ipw_msm_result):
    assert themis.verify(_program("ipw_msm"), ipw_msm_result) is None


def test_verifier_accepts_genuine_ipw_msm(ipw_msm_result):
    verify_longitudinal_numeric(ipw_msm_result["numeric_estimate"])  # no raise


# --- IPW-MSM: contrast re-derived from recorded coefficients ------------------


def test_rejects_tampered_ipw_msm_point(ipw_msm_result):
    ne = _ne(ipw_msm_result)
    ne["point"] = 999.0
    ne["longitudinal_ipw_msm"]["point"] = 999.0
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


def test_rejects_tampered_e_y_treated(ipw_msm_result):
    ne = _ne(ipw_msm_result)
    ne["longitudinal_ipw_msm"]["e_y_treated"] += 3.0
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


def test_rejects_tampered_msm_coefficient(ipw_msm_result):
    """Moving a recorded MSM coefficient re-derives a different contrast, so
    the (untampered) reported point no longer matches — proving the block is
    tied to the fitted coefficients, not merely internally shaped."""
    ne = _ne(ipw_msm_result)
    ne["longitudinal_ipw_msm"]["msm_coefficients"][1] += 0.5
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


def test_rejects_coefficient_count_mismatch(ipw_msm_result):
    ne = _ne(ipw_msm_result)
    ne["longitudinal_ipw_msm"]["msm_coefficients"].append(0.1)
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


def test_rejects_missing_coefficients(ipw_msm_result):
    ne = _ne(ipw_msm_result)
    del ne["longitudinal_ipw_msm"]["msm_coefficients"]
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


# --- g-formula: construction invariants only ---------------------------------


def test_rejects_tampered_gformula_point(gformula_result):
    ne = _ne(gformula_result)
    ne["point"] = 999.0
    ne["longitudinal_gformula"]["point"] = 999.0  # breaks point == e1 - e0
    with pytest.raises(VerificationError):
        verify_longitudinal_numeric(ne)


def test_gformula_self_consistent_forgery_not_caught(gformula_result):
    """Scaling both strategy means, the block point AND the headline point by
    the same factor keeps ``point == e_y_treated − e_y_control`` — the only
    g-formula invariant — so the construction-invariant check passes it.
    Catching this would need the black-box Monte-Carlo re-simulation: the
    honest ceiling for the g-formula block, unlike the coefficient-anchored
    IPW-MSM contrast."""
    ne = _ne(gformula_result)
    b = ne["longitudinal_gformula"]
    for k in ("e_y_treated", "e_y_control", "point"):
        b[k] *= 2.0
    ne["point"] *= 2.0
    verify_longitudinal_numeric(ne)  # passes — documented limitation


# --- honest identification gate: unmeasured confounder refuses a number ------


def test_not_identified_structural_run():
    r = themis.run(_program("ipw_msm", extra=_LATENT))["results"][0]
    assert r["status"] == "needs_investigation"
    assert r["extensions"]["longitudinal_identification"]["identified"] is False


def test_not_identified_refuses_number():
    r = themis.estimate(
        _program("ipw_msm", extra=_LATENT), _gen_dgp(), ci_bootstrap=0,
    )["results"][0]
    assert r["status"] == "needs_investigation"
    assert "numeric_estimate" not in r
    assert r["estimator_failure"]["failure_type"] == "not_identified"


# --- unit-level + hand-built + E2E -------------------------------------------


def test_missing_block_is_noop():
    verify_longitudinal_numeric({"method": "backdoor_linear", "point": 0.3})


def test_hand_built_valid_ipw_msm_block_passes():
    # point = (1 - 0)·(β_A0 + β_A1); e_y_v = β0 + v·Σβ.
    betas = [0.5, 2.0, 3.0]  # β0, β_A0, β_A1
    sum_beta = betas[1] + betas[2]
    ne = {
        "method": "longitudinal_ipw_msm",
        "point": (1.0 - 0.0) * sum_beta,
        "outcome": "Y",
        "treatment": "A0,A1",
        "longitudinal_ipw_msm": {
            "point": (1.0 - 0.0) * sum_beta,
            "treatments": ["A0", "A1"],
            "outcome": "Y",
            "strategy_treated": 1.0,
            "strategy_control": 0.0,
            "e_y_treated": betas[0] + 1.0 * sum_beta,
            "e_y_control": betas[0] + 0.0 * sum_beta,
            "msm_coefficients": betas,
            "weight_mean": 1.0,
            "weight_max": 4.2,
            "n_bootstrap": 0,
        },
    }
    verify_longitudinal_numeric(ne)  # no raise


def test_e2e_verify_rejects_tampered_ipw_msm(ipw_msm_result):
    r = copy.deepcopy(ipw_msm_result)
    r["numeric_estimate"]["longitudinal_ipw_msm"]["e_y_control"] -= 5.0
    with pytest.raises((VerificationError, Exception)):
        themis.verify(_program("ipw_msm"), r)
