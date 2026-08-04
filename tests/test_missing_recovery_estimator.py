"""Phase 9 §S9.2 numeric end — estimate_recovered_ate.

The back-door ATE recovered from data that itself has missing values
(Mohan-Pearl-Tian). The centrepiece correctness signal is the same one my
hand-run confirmed before coding: on a MAR data set with effect
modification, the multi-factor recovery (each g-formula factor from its
own complete cases) hits the full-data g-formula truth while naive
listwise deletion is biased.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import estimate, verify_data_gap_report
from themis.estimation import RecoveredATEEstimate, estimate_recovered_ate
from themis.refusals import EstimatorFailure


# ---- DGP: Z confounds X; Y has X·Z effect modification; R_Y depends on Z ----
#
# Effect modification is essential: with a constant within-stratum effect
# the distorted P(Z) would not bias the ATE. R_Y ← Z is MAR (missingness of
# Y depends only on the observed Z), so the complete-case CONDITIONAL stays
# unbiased and ALL the bias lives in the naive marginal P(Z).


def _mar_frame(n=30_000, seed=0, miss_col="y"):
    rng = np.random.default_rng(seed)
    Z = rng.binomial(1, 0.5, n)
    X = rng.binomial(1, 0.3 + 0.4 * Z)
    pY = np.clip(0.2 + 0.2 * X + 0.2 * Z + 0.3 * X * Z, 0, 1)
    Yf = rng.binomial(1, pY)
    R = rng.binomial(1, 0.1 + 0.6 * Z)          # miss depends on Z (MAR)
    col = np.asarray(locals()[{"y": "Yf", "x": "X"}[miss_col]], dtype=float).copy()
    col[R == 1] = np.nan
    df = pd.DataFrame({"x": X.astype(float), "y": Yf.astype(float), "z": Z.astype(float)})
    df[miss_col] = col
    return df, Yf, X, Z


def _full_gformula(Yf, X, Z):
    """Oracle: the g-formula ATE on the COMPLETE (pre-missingness) data."""
    ate = 0.0
    for z in (0, 1):
        pz = np.mean(Z == z)
        m1 = Yf[(X == 1) & (Z == z)].mean()
        m0 = Yf[(X == 0) & (Z == z)].mean()
        ate += (m1 - m0) * pz
    return ate


def test_recovers_full_data_gformula_and_beats_naive():
    df, Yf, X, Z = _mar_frame(seed=1)
    truth = _full_gformula(Yf, X, Z)
    est = estimate_recovered_ate(
        df, treatment="x", outcome="y", adjustment=("z",),
        ci_bootstrap=200, random_state=1,
    )
    assert isinstance(est, RecoveredATEEstimate)
    assert est.method == "missing_data_recovery_gformula"
    # recovery lands on the full-data g-formula truth ...
    assert abs(est.point - truth) < 0.02
    # ... while naive listwise deletion is meaningfully biased.
    assert est.naive_listwise_ate is not None
    assert abs(est.naive_listwise_ate - truth) > 0.04
    # and the recovery correction is larger than the residual recovery error.
    assert abs(est.point - est.naive_listwise_ate) > abs(est.point - truth)


def test_marginal_uses_more_rows_than_conditional_when_y_missing():
    df, *_ = _mar_frame(seed=2)
    est = estimate_recovered_ate(
        df, treatment="x", outcome="y", adjustment=("z",), ci_bootstrap=0,
    )
    # Z is fully observed, Y is not: P(Z) uses ALL rows, E[Y|X,Z] fewer.
    assert est.n_marginal_rows == est.n_total
    assert est.n_conditional_rows < est.n_marginal_rows
    assert est.missing_columns == ("y",)
    assert est.n_strata == 2


def test_no_missingness_matches_ordinary_gformula():
    """With nothing missing, the recovery and the naive number coincide and
    both equal the ordinary g-formula."""
    df, Yf, X, Z = _mar_frame(seed=3)
    df = df.copy()
    df["y"] = Yf.astype(float)              # restore — no missingness
    truth = _full_gformula(Yf, X, Z)
    est = estimate_recovered_ate(
        df, treatment="x", outcome="y", adjustment=("z",), ci_bootstrap=0,
    )
    assert est.missing_columns == ()
    assert abs(est.point - truth) < 1e-9
    assert abs(est.naive_listwise_ate - est.point) < 1e-9


def test_determinism():
    df, *_ = _mar_frame(seed=4)
    a = estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=100, random_state=7)
    b = estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=100, random_state=7)
    assert a.point == b.point
    assert a.ci_lower == b.ci_lower and a.ci_upper == b.ci_upper


def test_bootstrap_ci_brackets_point():
    df, *_ = _mar_frame(seed=5)
    est = estimate_recovered_ate(df, treatment="x", outcome="y",
                                 adjustment=("z",), ci_bootstrap=300, random_state=5)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower <= est.point <= est.ci_upper
    assert est.n_bootstrap > 0


def test_recovers_when_treatment_is_missing_column():
    """Missingness on X (not Y): the conditional drops X-missing rows, the
    marginal P(Z) still uses all rows. Recovery still tracks truth."""
    df, Yf, X, Z = _mar_frame(seed=6, miss_col="x")
    truth = _full_gformula(Yf, X, Z)
    est = estimate_recovered_ate(df, treatment="x", outcome="y",
                                 adjustment=("z",), ci_bootstrap=0)
    assert est.missing_columns == ("x",)
    assert abs(est.point - truth) < 0.03


def test_no_adjustment_case():
    """Empty adjustment: E[Y|do(x)] = E[Y|X=x] on complete cases."""
    rng = np.random.default_rng(11)
    n = 5000
    X = rng.binomial(1, 0.5, n)
    Yf = rng.binomial(1, 0.3 + 0.25 * X)
    R = rng.binomial(1, 0.2, n)              # MCAR
    Y = Yf.astype(float); Y[R == 1] = np.nan
    df = pd.DataFrame({"x": X.astype(float), "y": Y})
    est = estimate_recovered_ate(df, treatment="x", outcome="y",
                                 adjustment=(), ci_bootstrap=0)
    assert est.n_strata == 1
    assert abs(est.point - 0.25) < 0.03


# --------------------------------------------------------------- guards


def test_guard_continuous_adjustment():
    df, *_ = _mar_frame(seed=8)
    df = df.copy()
    df["z"] = np.random.default_rng(0).normal(size=len(df))
    with pytest.raises(EstimatorFailure) as ei:
        estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=0)
    assert ei.value.failure_type == "adjustment_not_discrete"


def test_guard_treatment_not_binary():
    df, *_ = _mar_frame(seed=9)
    df = df.copy()
    df["x"] = np.arange(len(df)) % 3          # 0/1/2
    with pytest.raises(EstimatorFailure) as ei:
        estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=0)
    assert ei.value.failure_type == "treatment_not_binary"


def test_guard_sample_too_small():
    df = pd.DataFrame({"x": [0.0, 1.0], "y": [0.0, 1.0], "z": [0.0, 1.0]})
    with pytest.raises(EstimatorFailure) as ei:
        estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=0)
    assert ei.value.failure_type == "sample_too_small"


def test_guard_missing_column():
    df = pd.DataFrame({"x": [0.0] * 20, "y": [0.0] * 20})
    with pytest.raises(EstimatorFailure) as ei:
        estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=0)
    assert ei.value.failure_type == "missing_column"


def test_insufficient_support_raises():
    """A stratum whose treatment cell has no complete case ⇒ the recovered
    conditional is undefined there, and the point estimate refuses."""
    # z=1 exists in the marginal but NO complete-case row has z=1 & x=1.
    x = [0.0, 1.0] * 10 + [0.0] * 10
    z = [0.0] * 20 + [1.0] * 10
    y = [0.0, 1.0] * 10 + [np.nan] * 10       # all z=1 rows have Y missing
    df = pd.DataFrame({"x": x, "y": y, "z": z})
    with pytest.raises(EstimatorFailure) as ei:
        estimate_recovered_ate(df, treatment="x", outcome="y",
                               adjustment=("z",), ci_bootstrap=0)
    assert ei.value.failure_type == "insufficient_support"


def test_cluster_bootstrap_runs_and_annotates():
    df, *_ = _mar_frame(seed=12)
    df = df.copy()
    df["fam"] = np.arange(len(df)) // 2       # pairs
    est = estimate_recovered_ate(df, treatment="x", outcome="y",
                                 adjustment=("z",), ci_bootstrap=100,
                                 random_state=3, cluster="fam")
    assert est.cluster == "fam"
    assert any("pairs_cluster_bootstrap_on_fam" in a for a in est.assumptions)
    assert est.ci_lower is not None


# --------------------------------------------------- end-to-end via estimate


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


def _prog(stmts):
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "p"}]},
            "statements": stmts}


_RECOVERABLE_PROG = _prog([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
    _indicator("y", caused_by=("z",)), _query(),
])
_UNRECOVERABLE_PROG = _prog([
    _var("x"), _var("y"), _var("z"),
    _edge("z", "x"), _edge("z", "y"), _edge("x", "y"),
    _indicator("z", caused_by=("z",)), _query(),
])


def test_e2e_estimate_recoverable_attaches_numeric():
    df, Yf, X, Z = _mar_frame(seed=20)
    truth = _full_gformula(Yf, X, Z)
    out = estimate(_RECOVERABLE_PROG, df)
    res = out["results"][0]
    ne = res.get("numeric_estimate")
    assert ne is not None
    assert ne["method"] == "missing_data_recovery_gformula"
    assert abs(ne["point"] - truth) < 0.03
    ra = ne["recovered_ate"]
    assert ra["missing_columns"] == ["y"]
    assert ra["n_marginal_rows"] > ra["n_conditional_rows"]
    assert ra["naive_listwise_ate"] is not None
    assert res.get("estimator_failure") is None


def test_e2e_estimate_not_recoverable_refuses():
    """Self-masking confounder ⇒ P(Z) unrecoverable ⇒ the kernel REFUSES to
    produce a number (the core no-fabrication guarantee)."""
    df, *_ = _mar_frame(seed=21)
    df = df.copy()
    # give z some missingness so it is genuinely partially observed
    zmiss = np.random.default_rng(0).binomial(1, 0.2, len(df)).astype(bool)
    df.loc[zmiss, "z"] = np.nan
    out = estimate(_UNRECOVERABLE_PROG, df)
    res = out["results"][0]
    assert res.get("numeric_estimate") is None
    ef = res.get("estimator_failure")
    assert ef is not None
    assert ef["failure_type"] == "not_recoverable"
    assert ef["estimator"] == "missing_data_recovery"


def _theta_surfaces(result):
    """The four places a request for a probability the data supplied lives."""
    report = result.get("data_gap_report") or {}
    return {
        "items": [
            m for m in result.get("missing_information") or []
            if m["gap"] == "missing_distribution"
        ],
        "requests": [
            item
            for request in result.get("investigation_requests") or []
            for item in request.get("items") or []
            if item["gap"] == "missing_distribution"
        ],
        "gaps": [
            g for g in report.get("gaps") or []
            if g["kind"] == "missing_distribution"
        ],
        "steps": [
            s for s in report.get("actionable_next_steps") or []
            if s.startswith("补 P(")
        ],
    }


def test_a_recovered_ate_withdraws_the_asks_it_answered():
    """This path returns before the shared prologue, and so before every
    reconciliation the prologue arranges.

    It has to: the columns it recovers from carry NaN, which the data
    contract forbids. What it does not have to skip is what a number
    answers — it estimated those very conditionals from the complete
    cases, and shipped beside four blocking gaps asking to be supplied
    them, with the report's next steps opening on the first.
    """
    df, *_ = _mar_frame(seed=23)
    result = estimate(_RECOVERABLE_PROG, df)["results"][0]

    assert result["numeric_estimate"]["point"] is not None
    for surface, entries in _theta_surfaces(result).items():
        assert not entries, f"{surface}: {entries}"
    verify_data_gap_report(result)


def test_an_unrecoverable_estimand_keeps_the_asks_its_columns_do_not_answer():
    """Having a column is not having the distribution.

    A self-masking Z leaves P(Z) unrecoverable — that is the refusal —
    while the DataFrame still carries a z column. Settling these asks on
    what the sample measures, the rule the contract path uses, would
    withdraw exactly the requests the refusal exists to justify. What is
    withdrawn on this path is what a number answered, and no number came.
    """
    df, *_ = _mar_frame(seed=24)
    df = df.copy()
    zmiss = np.random.default_rng(0).binomial(1, 0.2, len(df)).astype(bool)
    df["z"] = df["z"].astype(object)
    df.loc[zmiss, "z"] = np.nan
    result = estimate(_UNRECOVERABLE_PROG, df)["results"][0]

    assert result["estimator_failure"]["failure_type"] == "not_recoverable"
    assert result.get("numeric_estimate") is None
    surfaces = _theta_surfaces(result)
    assert surfaces["items"] and surfaces["gaps"] and surfaces["steps"]
    assert any(
        m["name"] == "parameter:P(z=True)" for m in surfaces["items"]
    ), [m["name"] for m in surfaces["items"]]


def test_e2e_estimate_output_validates_against_schema():
    from themis.input.syntactic_validator import validate_result
    df, *_ = _mar_frame(seed=22)
    out = estimate(_RECOVERABLE_PROG, df)
    for r in out["results"]:
        validate_result(r)               # no raise
