"""§S9.1 numeric end — selection-backdoor recovered ATE on data.

Covers the estimator (:mod:`themis.estimation.selection`), the honest gate in
the estimate dispatch (a selection-biased effect query never ships an ordinary
back-door number), and the independent numeric verifier
(:func:`themis.verify_selection_recovery_numeric`).

D1 oracles are two SCMs whose true ATE is known by construction; the recovered
number must match while the naive biased contrast does not. Everything is
pandas/numpy/sklearn — no Monte-Carlo recursion.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.selection import estimate_selection_recovery
from themis.refusals import EstimatorFailure
from themis.input.syntactic_validator import validate_result
from themis.verifier.errors import VerificationError


# ============================================================ SCMs (D1 oracles)


def _scm_zminus_only(n: int, seed: int) -> pd.DataFrame:
    """X→Y, X→W, Y→M, M→W. W is a selection collider; recovery uses Z⁻={m},
    Z⁺=∅. X is exogenous ⇒ true ATE = 0.40 by construction."""
    rng = np.random.default_rng(seed)
    X = rng.binomial(1, 0.5, n)
    Y = rng.binomial(1, 0.3 + 0.4 * X)
    M = rng.binomial(1, 0.2 + 0.5 * Y)
    W = rng.binomial(1, 0.1 + 0.4 * X + 0.4 * M)
    return pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool),
                         "m": M.astype(bool), "w": W.astype(bool)})


def _scm_zplus_zminus(n: int, seed: int) -> pd.DataFrame:
    """X→Y, X→S, Y→A, A→S, B→X, B→Y. S is a selection collider; B confounds
    (Z⁺={b}); A is a Y-descendant on the S path (Z⁻={a}). True ATE = 0.30
    (P(Y=1|X,B)=0.2+0.3X+0.3B ⇒ effect of X is 0.30 controlling B)."""
    rng = np.random.default_rng(seed)
    B = rng.binomial(1, 0.5, n)
    X = rng.binomial(1, 0.3 + 0.4 * B)
    Y = rng.binomial(1, 0.2 + 0.3 * X + 0.3 * B)
    A = rng.binomial(1, 0.2 + 0.5 * Y)
    S = rng.binomial(1, 0.1 + 0.4 * X + 0.4 * A)
    return pd.DataFrame({"x": X.astype(bool), "y": Y.astype(bool),
                         "a": A.astype(bool), "b": B.astype(bool),
                         "s": S.astype(bool)})


# ============================================================ estimator D1


def test_estimator_recovers_true_ate_zminus_only():
    full = _scm_zminus_only(120_000, seed=0)
    biased = full[full.w].reset_index(drop=True)
    reference = _scm_zminus_only(120_000, seed=1)
    est = estimate_selection_recovery(
        biased, reference, treatment="x", outcome="y",
        z_plus=(), z_minus=("m",), selection_nodes=("w",),
        selected_values={"w": True}, ci_bootstrap=0, random_state=0,
    )
    assert est.method == "selection_backdoor_recovery"
    assert abs(est.point - 0.40) < 0.03
    # The naive biased contrast is materially off (collider bias).
    naive = biased.loc[biased.x, "y"].mean() - biased.loc[~biased.x, "y"].mean()
    assert abs(naive - 0.40) > 0.07


def test_estimator_recovers_true_ate_zplus_zminus():
    full = _scm_zplus_zminus(200_000, seed=2)
    biased = full[full.s].reset_index(drop=True)
    reference = _scm_zplus_zminus(200_000, seed=3)
    est = estimate_selection_recovery(
        biased, reference, treatment="x", outcome="y",
        z_plus=("b",), z_minus=("a",), selection_nodes=("s",),
        selected_values={"s": True}, ci_bootstrap=0, random_state=0,
    )
    assert abs(est.point - 0.30) < 0.04
    suff = est.sufficient_statistics
    assert suff["z_plus_vars"] == ["b"] and suff["z_minus_vars"] == ["a"]
    # 2 arms × 2 b × 2 a = 8 biased strata; 2 z⁺ marginal cells.
    assert len(suff["biased_strata"]) == 8
    assert len(suff["ref_p_zplus"]) == 2


def test_estimator_bootstrap_ci_brackets_point():
    full = _scm_zminus_only(60_000, seed=4)
    biased = full[full.w].reset_index(drop=True)
    reference = _scm_zminus_only(60_000, seed=5)
    est = estimate_selection_recovery(
        biased, reference, treatment="x", outcome="y",
        z_plus=(), z_minus=("m",), selection_nodes=("w",),
        selected_values={"w": True}, ci_bootstrap=150, random_state=0,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper


def test_estimator_restricts_unrestricted_biased_sample():
    """Passing the FULL (unrestricted) sample as 'biased' is filtered to
    S=selected internally and flagged."""
    full = _scm_zminus_only(120_000, seed=6)
    reference = _scm_zminus_only(120_000, seed=7)
    est = estimate_selection_recovery(
        full, reference, treatment="x", outcome="y",
        z_plus=(), z_minus=("m",), selection_nodes=("w",),
        selected_values={"w": True}, ci_bootstrap=0, random_state=0,
    )
    assert est.sufficient_statistics["biased_restricted"] is True
    assert est.sample_size < len(full)
    assert abs(est.point - 0.40) < 0.03


# ============================================================ estimator guards


def test_estimator_refuses_non_binary_treatment():
    full = _scm_zminus_only(5_000, seed=8)
    biased = full[full.w].reset_index(drop=True).copy()
    biased["x"] = np.arange(len(biased)) % 3  # 3-valued treatment
    with pytest.raises(EstimatorFailure) as ei:
        estimate_selection_recovery(
            biased, full, treatment="x", outcome="y",
            z_plus=(), z_minus=("m",), selection_nodes=("w",),
            selected_values={"w": True}, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "treatment_not_binary"


def test_estimator_refuses_continuous_adjustment():
    full = _scm_zminus_only(5_000, seed=9)
    biased = full[full.w].reset_index(drop=True).copy()
    rng = np.random.default_rng(0)
    biased["m"] = rng.normal(size=len(biased))  # continuous "adjustment"
    ref = biased.copy()
    with pytest.raises(EstimatorFailure) as ei:
        estimate_selection_recovery(
            biased, ref, treatment="x", outcome="y",
            z_plus=(), z_minus=("m",), selection_nodes=("w",),
            selected_values={"w": True}, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "continuous_adjustment"


def test_estimator_refuses_reference_missing_column():
    full = _scm_zminus_only(5_000, seed=10)
    biased = full[full.w].reset_index(drop=True)
    ref = full.drop(columns=["m"])  # missing the z⁻ weight column
    with pytest.raises(EstimatorFailure) as ei:
        estimate_selection_recovery(
            biased, ref, treatment="x", outcome="y",
            z_plus=(), z_minus=("m",), selection_nodes=("w",),
            selected_values={"w": True}, ci_bootstrap=0,
        )
    assert ei.value.failure_type == "reference_missing_column"


# ============================================================ program builders


def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _edge(a, b):
    return {"kind": "cause",
            "from": {"predicate": a, "args": [{"type": "const", "name": "p"}]},
            "to": {"predicate": b, "args": [{"type": "const", "name": "p"}]}}


def _obs(p, value=True):
    return {"kind": "observation",
            "atom": {"predicate": p, "args": [{"type": "const", "name": "p"}]},
            "value": value}


def _effect_query(x="x", y="y"):
    return {"kind": "query", "id": "q",
            "query": {"kind": "effect",
                      "target": {"atom": {"predicate": y, "args": [{"type": "const", "name": "p"}]}, "value": True},
                      "intervention": {"atom": {"predicate": x, "args": [{"type": "const", "name": "p"}]}, "value": True},
                      "given": []}}


def _program(statements):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "p"}]},
            "statements": statements}


_COLLIDER_PROG = _program([
    _var("x"), _var("y"), _var("m"), _var("w"),
    _edge("x", "y"), _edge("x", "w"), _edge("y", "m"), _edge("m", "w"),
    _obs("w"), _effect_query(),
])
_HERNAN_PROG = _program([
    _var("x"), _var("y"), _var("w"),
    _edge("x", "y"), _edge("x", "w"), _edge("y", "w"),
    _obs("w"), _effect_query(),
])


# ============================================================ wired honest gate


def test_wired_no_reference_refuses_biased_number():
    """THE BUG FIX: a selection-biased effect query must NOT ship an ordinary
    back-door number. Without reference data it refuses, naming the external
    data the ledger demands."""
    full = _scm_zminus_only(40_000, seed=11)
    biased = full[full.w].reset_index(drop=True)
    out = themis.estimate(_COLLIDER_PROG, biased)
    res = out["results"][0]
    assert res.get("numeric_estimate") is None
    ef = res["estimator_failure"]
    assert ef["estimator"] == "selection_backdoor_recovery"
    assert ef["failure_type"] == "external_data_required"
    assert ef["external_data_needed"]  # names unbiased P(...)
    validate_result(res)  # the refusal shape conforms to query_result.schema.json


def test_wired_with_reference_produces_recovered_number():
    full = _scm_zminus_only(100_000, seed=12)
    biased = full[full.w].reset_index(drop=True)
    reference = _scm_zminus_only(100_000, seed=13)
    out = themis.estimate(_COLLIDER_PROG, biased, reference_data=reference)
    res = out["results"][0]
    ne = res["numeric_estimate"]
    assert res["status"] == "numerically_solved"
    assert ne["method"] == "selection_backdoor_recovery"
    assert abs(ne["point"] - 0.40) < 0.03
    validate_result(res)  # the recovered shape conforms to query_result.schema.json
    # and it passes its own independent numeric verifier
    themis.verify_selection_recovery_numeric(res)


def test_wired_hernan_not_recoverable_refuses():
    full = _scm_zminus_only(20_000, seed=14)  # any data; w is the collider
    biased = full[full.w].reset_index(drop=True)
    out = themis.estimate(_HERNAN_PROG, biased, reference_data=full)
    res = out["results"][0]
    assert res.get("numeric_estimate") is None
    assert res["estimator_failure"]["failure_type"] == "not_recoverable"


def test_wired_no_selection_still_runs_ordinary_backdoor():
    """A program without any selection restriction is untouched by the gate —
    the ordinary back-door number is still produced."""
    prog = _program([_var("x"), _var("y"), _edge("x", "y"), _effect_query()])
    full = _scm_zminus_only(20_000, seed=15)
    out = themis.estimate(prog, full[["x", "y"]])
    res = out["results"][0]
    assert res.get("numeric_estimate") is not None
    assert res["numeric_estimate"]["method"] != "selection_backdoor_recovery"


# ============================================================ numeric verifier


def _recovered_result():
    full = _scm_zminus_only(100_000, seed=16)
    biased = full[full.w].reset_index(drop=True)
    reference = _scm_zminus_only(100_000, seed=17)
    out = themis.estimate(_COLLIDER_PROG, biased, reference_data=reference)
    return out["results"][0]


def test_verifier_accepts_truthful():
    themis.verify_selection_recovery_numeric(_recovered_result())  # no raise


def test_verifier_rejects_forged_point():
    res = _recovered_result()
    res["numeric_estimate"]["point"] = 0.28  # the biased value a forger wants
    with pytest.raises(VerificationError):
        themis.verify_selection_recovery_numeric(res)


def test_verifier_rejects_tampered_biased_risk():
    res = _recovered_result()
    suff = res["numeric_estimate"]["selection_recovery_numeric"]["sufficient_statistics"]
    suff["biased_strata"][0]["y_sum"] *= 1.5
    with pytest.raises(VerificationError):
        themis.verify_selection_recovery_numeric(res)


def test_verifier_rejects_tampered_weight_breaking_normalisation():
    res = _recovered_result()
    suff = res["numeric_estimate"]["selection_recovery_numeric"]["sufficient_statistics"]
    suff["ref_p_zminus_given"][0]["p"] += 0.3
    with pytest.raises(VerificationError):
        themis.verify_selection_recovery_numeric(res)


def test_verifier_noop_on_non_selection_result():
    prog = _program([_var("x"), _var("y"), _edge("x", "y"), _effect_query()])
    full = _scm_zminus_only(5_000, seed=18)
    out = themis.estimate(prog, full[["x", "y"]])
    # ordinary backdoor result — verifier is a no-op, must not raise
    themis.verify_selection_recovery_numeric(out["results"][0])
