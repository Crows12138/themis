"""Audit of the numeric answer blocks riding on a mediation structural
result (``verify_mediation_numeric``).

Mediation stays ``structurally_solved`` (routed to verify_effect_structural,
which checks only the identify_via_mediation terminal), so the numbers
attached to it — the Imai NDE/NIE decomposition and the two four-way splits —
shipped with no numeric audit: a tampered err_cde or prop_mediated passed
``themis.verify``.

Two levels of check:
- ``four_way_ratio`` (STRONG): every ERR component is a closed form of the
  fitted logistic coefficients (now recorded), so the verifier re-derives
  them and catches ANY tamper, even a self-consistent one — including a
  tampered coefficient.
- ``four_way_decomposition`` / ``decomposition`` (INVARIANTS): sufficient
  statistics not recorded / simulation-based, so only the construction
  identities (TE = sum of parts; proportion = ratio) are checked; a
  self-consistent forgery of those two is the honest ceiling.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.verify import VerificationError, verify_mediation_numeric


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _mediation_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
            {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
                "mediator": _atom("m")}},
        ],
    }


def _binary_data(n=1000, seed=1):
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    m = rng.binomial(1, 1 / (1 + np.exp(-(-0.2 + 1.0 * x))))
    y = rng.binomial(1, 1 / (1 + np.exp(-(-1.0 + 0.6 * x + 0.7 * m + 0.4 * x * m))))
    return pd.DataFrame({"x": x.astype(float), "m": m.astype(float),
                         "y": y.astype(float)})


def _continuous_data(n=1200, seed=2):
    rng = np.random.default_rng(seed)
    x = rng.binomial(1, 0.5, n)
    m = rng.binomial(1, 1 / (1 + np.exp(-(-0.2 + 1.0 * x))))
    y = 0.5 + 0.5 * x + 2.0 * m + rng.normal(0, 1, n)
    return pd.DataFrame({"x": x.astype(float), "m": m.astype(float), "y": y})


@pytest.fixture(scope="module")
def binary_result():
    out = themis.estimate(_mediation_ast(), _binary_data(), ci_bootstrap=12,
                          random_state=7)
    return out["results"][0]


@pytest.fixture(scope="module")
def continuous_result():
    out = themis.estimate(_mediation_ast(), _continuous_data(), ci_bootstrap=12,
                          random_state=7)
    return out["results"][0]


def _ne(result):
    return copy.deepcopy(result["numeric_estimate"])


# --- round-trip: genuine blocks pass -----------------------------------------


def test_binary_result_has_all_three_blocks(binary_result):
    ne = binary_result["numeric_estimate"]
    assert "four_way_ratio" in ne
    assert "coefficients" in ne["four_way_ratio"]
    assert "four_way_decomposition" in ne
    assert "decomposition" in ne


def test_binary_round_trips(binary_result):
    assert themis.verify(_mediation_ast(), binary_result) is None


def test_continuous_round_trips(continuous_result):
    assert themis.verify(_mediation_ast(), continuous_result) is None


def test_verifier_accepts_genuine_blocks(binary_result):
    verify_mediation_numeric(binary_result["numeric_estimate"])  # no raise


# --- four_way_ratio: STRONG re-derivation catches any tamper -----------------


def test_rejects_tampered_err_cde(binary_result):
    ne = _ne(binary_result)
    ne["four_way_ratio"]["err_cde"]["point"] = 999.0
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_tampered_prop_mediated(binary_result):
    ne = _ne(binary_result)
    ne["four_way_ratio"]["prop_mediated"]["point"] = 42.0
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_tampered_total_rr(binary_result):
    ne = _ne(binary_result)
    ne["four_way_ratio"]["total_rr"]["point"] *= 1.5
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_tampered_coefficient(binary_result):
    """Moving a recorded coefficient re-derives different components, so the
    (untampered) reported points no longer match — proving the block is tied
    to the fit, not merely internally consistent."""
    ne = _ne(binary_result)
    ne["four_way_ratio"]["coefficients"]["t1"] += 0.5
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_missing_coefficients(binary_result):
    ne = _ne(binary_result)
    del ne["four_way_ratio"]["coefficients"]
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


# --- four_way_decomposition + decomposition: construction identities ---------


def test_rejects_tampered_difference_scale_cde(continuous_result):
    ne = _ne(continuous_result)
    ne["four_way_decomposition"]["cde"]["point"] += 5.0  # breaks sum == te
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_tampered_nde(continuous_result):
    ne = _ne(continuous_result)
    ne["decomposition"]["nde"]["point"] += 5.0  # breaks nde + nie == te
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


def test_rejects_tampered_decomposition_proportion(continuous_result):
    ne = _ne(continuous_result)
    ne["decomposition"]["proportion_mediated"]["point"] = 7.0
    with pytest.raises(VerificationError):
        verify_mediation_numeric(ne)


# --- honest ceiling: a self-consistent forgery of an invariant-only block ----


def test_self_consistent_difference_scale_forgery_not_caught(continuous_result):
    """Scaling every difference-scale component AND te by the same factor
    keeps TE = sum-of-parts and every proportion = its ratio, so the
    invariant-only check passes it. Catching this would need the recorded
    cell means (not stored) — the honest ceiling for that block, unlike the
    coefficient-anchored four_way_ratio."""
    ne = _ne(continuous_result)
    fw = ne["four_way_decomposition"]
    for k in ("cde", "intref", "intmed", "pie", "te"):
        fw[k]["point"] *= 2.0
    verify_mediation_numeric(ne)  # passes — documented limitation


# --- unit-level + no-op ------------------------------------------------------


def test_missing_blocks_is_noop():
    verify_mediation_numeric({"method": "mediation", "point": 0.3})


def test_hand_built_valid_ratio_block_passes():
    # err pieces sum to total_err; total_err = total_rr - 1; props are the
    # component ratios; coefficients re-derive to these values.
    from themis.estimation.four_way import four_way_ratio_decomposition
    c = four_way_ratio_decomposition(
        t1=0.6, t2=0.7, t3=0.4, b0=-0.2, b1=1.0, bcc=0.0,
        a1=1.0, a0=0.0, mstar=0.0,
    )

    def _p(v):
        return {"point": v, "ci_lower": None, "ci_upper": None}

    ne = {
        "four_way_ratio": {
            "mediator_scale": "binary",
            "err_cde": _p(c.err_cde), "err_intref": _p(c.err_intref),
            "err_intmed": _p(c.err_intmed), "err_pie": _p(c.err_pie),
            "total_err": _p(c.total_err), "total_rr": _p(c.total_rr),
            "prop_mediated": _p(c.prop_mediated),
            "prop_interaction": _p(c.prop_interaction),
            "prop_eliminated": _p(c.prop_eliminated),
            "coefficients": {
                "t1": 0.6, "t2": 0.7, "t3": 0.4,
                "b0": -0.2, "b1": 1.0, "bcc": 0.0, "mediator_reference": 0.0,
            },
        }
    }
    verify_mediation_numeric(ne)  # no raise


def test_e2e_verify_rejects_tampered_ratio(binary_result):
    r = copy.deepcopy(binary_result)
    r["numeric_estimate"]["four_way_ratio"]["err_intmed"]["point"] = 1e6
    with pytest.raises((VerificationError, Exception)):
        themis.verify(_mediation_ast(), r)
