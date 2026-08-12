"""§S9.2 numeric end — verify_missing_data_numeric.

The back-door ATE recovered from data that itself has missing values
(Mohan-Pearl-Tian) ships on a result with no derivation, so the
derivation-gated ``themis.verify`` never reaches it: a tampered ``point``
passed unaudited. This verifier is the audit path — it
re-runs the g-formula Σ_z (E[Y|1,z]−E[Y|0,z])·P(z) from the recorded
per-stratum sufficient statistics (conditional {n, y_sum} + marginal
{z, count} tables) as a standalone transcription and rejects a forged point,
a tampered stratum, or a dropped stratum.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis import estimate
from themis.verifier.errors import VerificationError
from themis.verifier.missing_numeric_rules import verify_missing_data_numeric


# --------------------------------------------------------------- AST + DGP


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause",
            "from": {"predicate": a, "args": [{"type": "const", "name": "p"}]},
            "to": {"predicate": b, "args": [{"type": "const", "name": "p"}]}}


def _indicator(v, caused_by=()):
    return {"kind": "missingness_indicator", "id": f"R_{v}",
            "missing_var": {"predicate": v, "args": [{"type": "const", "name": "p"}]},
            "caused_by": [{"predicate": c, "args": [{"type": "const", "name": "p"}]}
                          for c in caused_by]}


def _query():
    return {"kind": "query", "id": "q", "query": {"kind": "effect",
            "target": {"atom": {"predicate": "y", "args": [{"type": "const", "name": "p"}]}, "value": True},
            "intervention": {"atom": {"predicate": "x", "args": [{"type": "const", "name": "p"}]}, "value": True},
            "given": []}}


_RECOVERABLE_PROG = {
    "version": "0.1", "domain": {"objects": [{"kind": "object", "name": "p"}]},
    "statements": [
        _var("x"), _var("y"), _var("z"),
        _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
        _indicator("y", caused_by=("z",)), _query(),
    ],
}


def _mar_frame(n=30_000, seed=20):
    rng = np.random.default_rng(seed)
    Z = rng.binomial(1, 0.5, n)
    X = rng.binomial(1, 0.3 + 0.4 * Z)
    pY = np.clip(0.2 + 0.2 * X + 0.2 * Z + 0.3 * X * Z, 0, 1)
    Yf = rng.binomial(1, pY)
    R = rng.binomial(1, 0.1 + 0.6 * Z)
    col = Yf.astype(float).copy()
    col[R == 1] = np.nan
    return pd.DataFrame({"x": X.astype(float), "y": col, "z": Z.astype(float)})


@pytest.fixture(scope="module")
def recoverable_result():
    return estimate(_RECOVERABLE_PROG, _mar_frame())["results"][0]


def _ne(result):
    return copy.deepcopy(result["numeric_estimate"])


def _wrap(ne):
    return {"numeric_estimate": ne}


# ---------------------------------------------------- round-trip: genuine passes


def test_block_carries_sufficient_statistics(recoverable_result):
    suff = recoverable_result["numeric_estimate"]["recovered_ate"]["sufficient_statistics"]
    assert suff["adjustment_vars"] == ["z"]
    rec = suff["recovered"]
    assert {"conditional_strata", "marginal_counts", "marginal_total"} <= rec.keys()
    # marginal (all rows, only y missing) uses more rows than the conditional
    assert rec["marginal_total"] > sum(
        s["n"] for s in rec["conditional_strata"] if s["arm"] == 1
    )
    assert suff["naive"] is not None


def test_genuine_result_accepted(recoverable_result):
    verify_missing_data_numeric(recoverable_result)  # no raise


def test_public_api_accepts(recoverable_result):
    themis.verify_missing_data_numeric(recoverable_result)  # no raise


def test_result_validates_against_schema(recoverable_result):
    from themis.input.syntactic_validator import validate_result
    validate_result(recoverable_result)  # no raise


# ----------------------------------------------------- tamper: recovered point


def test_rejects_forged_top_point(recoverable_result):
    ne = _ne(recoverable_result)
    ne["point"] = 0.99
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_forged_recovered_ate_point(recoverable_result):
    ne = _ne(recoverable_result)
    ne["recovered_ate"]["point"] = ne["point"] + 0.2
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_tampered_conditional_y_sum(recoverable_result):
    ne = _ne(recoverable_result)
    ne["recovered_ate"]["sufficient_statistics"]["recovered"]["conditional_strata"][0]["y_sum"] *= 1.5
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_tampered_conditional_n(recoverable_result):
    ne = _ne(recoverable_result)
    ne["recovered_ate"]["sufficient_statistics"]["recovered"]["conditional_strata"][0]["n"] += 500
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_tampered_marginal_count(recoverable_result):
    """Shifting a marginal count reweights P(z); the re-derived ATE no longer
    matches the reported point (a self-consistent-looking single-table edit is
    still caught because the point is tied to the recorded weights)."""
    ne = _ne(recoverable_result)
    mc = ne["recovered_ate"]["sufficient_statistics"]["recovered"]["marginal_counts"]
    # move mass between strata but keep the total (so the sum==total check
    # passes) — the ATE re-derivation still catches it
    mc[0]["count"] += 100
    mc[1]["count"] -= 100
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_dropped_marginal_stratum(recoverable_result):
    ne = _ne(recoverable_result)
    ne["recovered_ate"]["sufficient_statistics"]["recovered"]["marginal_counts"].pop()
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_rejects_tampered_naive_ate(recoverable_result):
    ne = _ne(recoverable_result)
    assert ne["recovered_ate"]["naive_listwise_ate"] is not None
    ne["recovered_ate"]["naive_listwise_ate"] += 0.3
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


# ---------------------------------------------------------- unit / edge cases


def _factor(strata, marg, total):
    return {"conditional_strata": strata, "marginal_counts": marg,
            "marginal_total": total}


def _hand_block(recovered, *, adjustment_vars, point, naive=None, naive_point=None):
    ra = {
        "point": point, "ci_lower": None, "ci_upper": None,
        "naive_listwise_ate": naive_point,
        "adjustment": adjustment_vars, "n_total": 100, "n_complete_case": 100,
        "n_conditional_rows": 100, "n_marginal_rows": 100,
        "n_strata": max(1, len(recovered["marginal_counts"])),
        "missing_columns": ["y"], "n_bootstrap": 0,
        "sufficient_statistics": {
            "adjustment_vars": adjustment_vars,
            "recovered": recovered,
            "naive": naive,
        },
    }
    return {"method": "missing_data_recovery_gformula", "point": point,
            "recovered_ate": ra}


def test_hand_built_valid_block_passes():
    rec = _factor(
        strata=[
            {"z": [0.0], "arm": 1, "n": 30, "y_sum": 15.0},
            {"z": [0.0], "arm": 0, "n": 30, "y_sum": 6.0},
            {"z": [1.0], "arm": 1, "n": 20, "y_sum": 16.0},
            {"z": [1.0], "arm": 0, "n": 20, "y_sum": 4.0},
        ],
        marg=[{"z": [0.0], "count": 60}, {"z": [1.0], "count": 40}],
        total=100,
    )
    # (0.5−0.2)*0.6 + (0.8−0.2)*0.4 = 0.18 + 0.24 = 0.42
    verify_missing_data_numeric(_wrap(_hand_block(rec, adjustment_vars=["z"], point=0.42)))


def test_hand_built_no_adjustment_case_passes():
    rec = _factor(
        strata=[
            {"z": [], "arm": 1, "n": 50, "y_sum": 30.0},   # 0.6
            {"z": [], "arm": 0, "n": 50, "y_sum": 20.0},   # 0.4
        ],
        marg=[{"z": [], "count": 100}],
        total=100,
    )
    verify_missing_data_numeric(_wrap(_hand_block(rec, adjustment_vars=[], point=0.2)))


def test_hand_built_forged_point_rejected():
    rec = _factor(
        strata=[
            {"z": [0.0], "arm": 1, "n": 30, "y_sum": 15.0},
            {"z": [0.0], "arm": 0, "n": 30, "y_sum": 6.0},
            {"z": [1.0], "arm": 1, "n": 20, "y_sum": 16.0},
            {"z": [1.0], "arm": 0, "n": 20, "y_sum": 4.0},
        ],
        marg=[{"z": [0.0], "count": 60}, {"z": [1.0], "count": 40}],
        total=100,
    )
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(_hand_block(rec, adjustment_vars=["z"], point=0.42 + 0.1)))


def test_marginal_counts_not_summing_to_total_rejected():
    rec = _factor(
        strata=[
            {"z": [0.0], "arm": 1, "n": 30, "y_sum": 15.0},
            {"z": [0.0], "arm": 0, "n": 30, "y_sum": 6.0},
        ],
        marg=[{"z": [0.0], "count": 55}],  # 55 != total 100
        total=100,
    )
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(_hand_block(rec, adjustment_vars=["z"], point=0.3)))


def test_missing_conditional_arm_rejected():
    rec = _factor(
        strata=[{"z": [0.0], "arm": 1, "n": 30, "y_sum": 15.0}],  # no arm 0
        marg=[{"z": [0.0], "count": 100}],
        total=100,
    )
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(_hand_block(rec, adjustment_vars=["z"], point=0.5)))


def test_missing_sufficient_statistics_rejected():
    ne = {"method": "missing_data_recovery_gformula", "point": 0.3,
          "recovered_ate": {"point": 0.3, "naive_listwise_ate": None}}
    with pytest.raises(VerificationError):
        verify_missing_data_numeric(_wrap(ne))


def test_non_missing_data_numeric_is_noop():
    verify_missing_data_numeric({"numeric_estimate": {"method": "backdoor_linear", "point": 0.3}})


def test_no_numeric_estimate_is_noop():
    verify_missing_data_numeric({"status": "needs_investigation"})


def test_public_api_type_error_on_non_dict():
    with pytest.raises(TypeError):
        themis.verify_missing_data_numeric(["not", "a", "dict"])
