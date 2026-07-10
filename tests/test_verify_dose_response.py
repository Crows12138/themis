"""Construction-invariant audit of the dose-response curve
(``verify_dose_response_curve``).

The curve values come from a black-box EconML DML / DRLearner fit, so — like
every data-refit estimator — the verifier can't re-derive them. What it CAN
audit, and does, are the invariants the curve holds BY CONSTRUCTION: one
point per sampling point (matching x), the reference-point effect is 0, and
every point sits inside its own interval. Before this verifier the curve
array (the answer for a dose-response query) shipped checked for JSON shape
only — a corrupted / reordered curve or a point escaping its CI passed
``themis.verify``.

Most tests build the numeric_estimate by hand and call the verifier directly
(no EconML needed); two EconML-gated tests round-trip a genuine curve through
``themis.verify``.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.verify import VerificationError, verify_dose_response_curve

try:
    import econml  # noqa: F401
    _ECONML_AVAILABLE = True
except ImportError:
    _ECONML_AVAILABLE = False


def _valid_estimate() -> dict:
    """A well-formed dose-response numeric_estimate (reference effect 0,
    every point inside its interval, x matching the sampling grid)."""
    return {
        "method": "dose_response_linear_dml",
        "sampling_points": [1.0, 2.0, 4.0, 8.0],
        "reference_point": 1.0,
        "dose_response_curve": [
            {"x": 1.0, "effect": 0.0, "ci_lower": 0.0, "ci_upper": 0.0},
            {"x": 2.0, "effect": 0.6, "ci_lower": 0.5, "ci_upper": 0.7},
            {"x": 4.0, "effect": 1.8, "ci_lower": 1.6, "ci_upper": 2.0},
            {"x": 8.0, "effect": 3.9, "ci_lower": 3.5, "ci_upper": 4.3},
        ],
    }


# --- accepts a well-formed curve ---------------------------------------------


def test_accepts_valid_curve():
    verify_dose_response_curve(_valid_estimate())  # no raise


def test_missing_curve_is_noop():
    verify_dose_response_curve({"method": "backdoor_linear", "point": 0.3})


def test_accepts_null_intervals():
    """Some EconML configs don't expose a CI — null ci bounds skip the
    in-interval check for that point but the x / count / reference
    invariants still hold."""
    est = _valid_estimate()
    est["dose_response_curve"][2]["ci_lower"] = None
    est["dose_response_curve"][2]["ci_upper"] = None
    verify_dose_response_curve(est)  # no raise


# --- tamper rejection --------------------------------------------------------


def test_rejects_reference_effect_off_zero():
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"][0]["effect"] = 99.0
    est["dose_response_curve"][0]["ci_lower"] = -200.0
    est["dose_response_curve"][0]["ci_upper"] = 200.0  # widen so in-CI passes
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_point_outside_its_interval():
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"][2]["effect"] = 1e6  # far outside [1.6, 2.0]
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_x_off_the_sampling_grid():
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"][1]["x"] = -999.0
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_wrong_point_count():
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"].pop()   # curve now shorter than sampling_points
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_reordered_curve():
    est = copy.deepcopy(_valid_estimate())
    c = est["dose_response_curve"]
    c[1], c[2] = c[2], c[1]            # x no longer matches sampling grid
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_inverted_interval():
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"][1]["ci_lower"] = 0.9
    est["dose_response_curve"][1]["ci_upper"] = 0.1  # lo > hi
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


def test_rejects_reference_point_mismatch():
    est = copy.deepcopy(_valid_estimate())
    est["reference_point"] = 7.0       # != sampling_points[0] == 1.0
    with pytest.raises(VerificationError):
        verify_dose_response_curve(est)


# --- honest scope: a fully self-consistent forgery is NOT caught -------------


def test_self_consistent_forgery_is_not_caught():
    """Documents the ceiling: moving a point's effect AND its interval
    together to a plausible pair keeps every construction invariant intact,
    so the verifier passes it. Catching this would require re-running the
    EconML fit on the data — out of scope for any data-refit estimator's
    verifier (the same ceiling backdoor / IV / TMLE points sit at)."""
    est = copy.deepcopy(_valid_estimate())
    est["dose_response_curve"][2]["effect"] = 1000.0
    est["dose_response_curve"][2]["ci_lower"] = 999.0
    est["dose_response_curve"][2]["ci_upper"] = 1001.0
    verify_dose_response_curve(est)  # passes — honest limitation, not a bug


# --- end-to-end through the kernel verifier (EconML-gated) -------------------


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dose_response_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query", "description": "x"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "variable", "predicate": "engagement"},
            {"kind": "cause", "from": _atom("raise_amount"),
             "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("raise_amount"), "value": True},
                "target": {"atom": _atom("engagement"), "value": 4},
                "given": []}},
        ],
    }


def _synth_data(n=400, slope=0.5, seed=7):
    rng = np.random.default_rng(seed)
    ra = rng.uniform(0.0, 10.0, size=n)
    eng = 1.0 + slope * ra + rng.normal(0.0, 1.0, size=n)
    return pd.DataFrame({"raise_amount": ra, "engagement": eng})


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_e2e_verify_round_trips_dose_response():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    assert themis.verify(_dose_response_program(), out["results"][0]) is None


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_e2e_verify_rejects_tampered_curve():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    r = out["results"][0]
    r["numeric_estimate"]["dose_response_curve"][2]["effect"] = 1e6
    with pytest.raises((VerificationError, Exception)):
        themis.verify(_dose_response_program(), r)
