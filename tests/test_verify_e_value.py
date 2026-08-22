"""Independent re-derivation of the VanderWeele-Ding E-value sensitivity
block (``verify_e_value``).

Mirrors ``test_sensitivity_ovb.py``: the block's E-value / CI-bound E-value
are a closed form of the audited headline ATE plus one recorded conversion
input (control-arm baseline rate, or outcome SD), so the verifier recomputes
them from scratch and must reject any tamper.

The oracle is threefold:
- **textbook literals** — a hand-built block whose numbers are the plain
  VanderWeele-Ding value E = RR + √(RR·(RR−1)) for RR=2 (= 2+√2) proves the
  verifier matches the formula, not merely the producer's own code;
- **producer round-trip** — a genuine block from ``themis.estimate`` passes;
- **tamper rejection** — mutating any reported number raises.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.verify import VerificationError, verify_e_value


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


# --- genuine producer blocks -------------------------------------------------


def _confounded_bool_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _binary_result():
    rng = np.random.default_rng(0)
    n = 2000
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    p_y = np.clip(0.2 + 0.1 * z + 0.15 * x.astype(float), 0.01, 0.99)
    y = rng.random(n) < p_y
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    ast = _confounded_bool_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    return ast, out["results"][0]


def _continuous_result():
    rng = np.random.default_rng(1)
    n = 1500
    z = rng.standard_normal(n)
    x = rng.random(n) < (1 / (1 + np.exp(-z)))
    y = 1.0 * z + 2.0 * x.astype(float) + rng.standard_normal(n) * 0.3
    df = pd.DataFrame({"x": x, "z": z, "y": y})
    ast = _confounded_bool_ast()
    out = themis.estimate(ast, df, ci_bootstrap=0)
    return ast, out["results"][0]


# --- textbook oracle (independent of the producer) ---------------------------


def test_textbook_oracle_binary_passes():
    """RR=2 ⇒ E = 2 + √2; RR=1.5 (CI bound) ⇒ E = 1.5 + √0.75. Literals
    computed here by plain arithmetic, NOT the E-value formula function."""
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.2,     # treated = 0.2+0.2 = 0.4 ⇒ RR = 2
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,          # 3.41421356…
            "e_value_ci_bound": 1.5 + 0.75 ** 0.5,  # RR_ci = 0.3/0.2 = 1.5
            # 2.366 < 2.5 ⇒ moderate. The point's 3.414 would have said
            # substantial, which is the whole of the distinction: the reading
            # follows the bound, and the two land in different bands here.
            "interpretation_band": "moderate",
            "band_basis": "ci_bound",
            "note": "textbook oracle",
        },
    }
    verify_e_value(est)  # must not raise


def test_textbook_oracle_continuous_passes():
    rr = math.exp(0.91 * (0.5 / 2.0))          # SMD = 0.25
    rr_ci = math.exp(0.91 * (0.2 / 2.0))        # CI bound = 0.2
    est = {
        "point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
        "sensitivity_analysis": {
            "path": "continuous",
            "baseline_rate": None,
            "outcome_sd": 2.0,
            "risk_ratio": rr,
            "e_value": rr + math.sqrt(rr * (rr - 1.0)),
            "e_value_ci_bound": rr_ci + math.sqrt(rr_ci * (rr_ci - 1.0)),
            # 1.418 < 1.5 ⇒ fragile, where the point's 1.822 says moderate.
            "interpretation_band": "fragile",
            "band_basis": "ci_bound",
            "note": "textbook oracle (continuous)",
        },
    }
    verify_e_value(est)  # must not raise


# --- producer round-trip -----------------------------------------------------


def test_verifier_accepts_genuine_binary_block():
    _, r = _binary_result()
    est = r["numeric_estimate"]
    assert est["sensitivity_analysis"]["path"] == "binary"
    verify_e_value(est)  # no raise


def test_verifier_accepts_genuine_continuous_block():
    _, r = _continuous_result()
    est = r["numeric_estimate"]
    assert est["sensitivity_analysis"]["path"] == "continuous"
    assert est["sensitivity_analysis"]["baseline_rate"] is None
    verify_e_value(est)  # no raise


# --- tamper rejection --------------------------------------------------------


def test_rejects_tampered_e_value():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["e_value"] = 9.99   # inflate to look robust
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_e_value_ci_bound():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["e_value_ci_bound"] = 42.0
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_risk_ratio():
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["risk_ratio"] = 1.0001
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_tampered_baseline_rate():
    """Moving the recorded baseline changes the re-derived RR, so the recorded
    E-value no longer matches — caught."""
    _, r = _binary_result()
    est = dict(r["numeric_estimate"])
    est["sensitivity_analysis"] = dict(est["sensitivity_analysis"])
    est["sensitivity_analysis"]["baseline_rate"] = 0.5
    with pytest.raises(VerificationError):
        verify_e_value(est)


# --- undefined consistency ---------------------------------------------------


def test_accepts_genuinely_undefined():
    """treated = baseline + ATE escapes (0,1) ⇒ producer emits all-None; the
    verifier must agree the E-value is undefined, not invent one."""
    est = {
        "point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.9,   # treated = 1.4 ∉ (0,1)
            "outcome_sd": None,
            "risk_ratio": None,
            "e_value": None,
            "e_value_ci_bound": None,
            "interpretation_band": None,
            "band_basis": None,
            "note": "undefined — linear extrapolation escapes [0,1]",
        },
    }
    verify_e_value(est)  # no raise


def test_rejects_value_claimed_when_undefined():
    est = {
        "point": 0.5, "ci_lower": 0.2, "ci_upper": 0.8,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.9,       # treated = 1.4 ∉ (0,1) ⇒ undefined
            "outcome_sd": None,
            "risk_ratio": None,
            "e_value": 3.0,             # but a value is claimed
            "e_value_ci_bound": None,
            "note": "tampered — claims a value where none is defined",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_a_reading_taken_off_the_point():
    """The reading is audited like the numbers under it.

    The tamper is not a made-up band: it is the band this block would have
    carried under the rule the module used to apply — the point estimate's
    3.414 lands in ``substantial`` while the bound's 2.366 lands in
    ``moderate``. A verifier that re-derived the numbers and took the
    reading on trust would pass a block whose one reader-facing conclusion
    is the one that was wrong.
    """
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "binary",
            "baseline_rate": 0.2,
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,
            "e_value_ci_bound": 1.5 + 0.75 ** 0.5,
            "interpretation_band": "substantial",   # read off the point
            "band_basis": "point",
            "note": "tampered — the reading follows the wrong number",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_rejects_unknown_path():
    est = {
        "point": 0.2, "ci_lower": 0.1, "ci_upper": 0.3,
        "sensitivity_analysis": {
            "path": "logistic-magic",
            "baseline_rate": 0.2,
            "outcome_sd": None,
            "risk_ratio": 2.0,
            "e_value": 2.0 + 2.0 ** 0.5,
            "e_value_ci_bound": None,
            "interpretation_band": "substantial",
            "band_basis": "point",
            "note": "unknown path",
        },
    }
    with pytest.raises(VerificationError):
        verify_e_value(est)


def test_missing_block_is_noop():
    verify_e_value({"point": 0.2})  # no sensitivity_analysis → no raise


# --- end-to-end through the kernel verifier ----------------------------------


def test_e2e_verify_round_trips_binary():
    ast, r = _binary_result()
    themis.verify(ast, r)  # E-value block now audited inside the kernel


def test_e2e_verify_rejects_tampered_e_value():
    ast, r = _binary_result()
    r["numeric_estimate"]["sensitivity_analysis"]["e_value"] = 9.99
    with pytest.raises((VerificationError, Exception)):
        themis.verify(ast, r)
