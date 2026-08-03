"""A mismeasured CONTINUOUS outcome — the channel that costs precision, not bias.

The defect this replaces, measured before the change: on one continuous
back-door program and one frame, ``estimate(prog, df)`` returned
``backdoor_linear`` point 0.8117 (truth 0.8) while the SAME call with
``measurement_error={"y": {...}}`` returned **no number at all** — status
``needs_investigation``, ``continuous_outcome_mismeasurement_deferred`` — and the
combined ``{"x": …, "y": …}`` call threw away the exposure-side correction with
it. Re-running the first call on the latent clean outcome gives 0.8074: the
number being withheld was already the right one.

It is right for a reason that generalises past linearity. With V ⊥ (X, Z, Y*) and
E[V] = 0, every conditional mean is preserved — E[Y|X,Z] = E[Y*|X,Z] — and every
estimand this package reports on a continuous outcome is built from conditional
means. So there is nothing to de-attenuate, and the correct behaviour is to ship
the number, declare the premise it rests on (non-differential error), and price
the one thing the noise does cost.

D1 oracle discipline — the reported inflation factor is checked against two
independent routes:

- Analytic: the OLS standard error of the same slope on the clean latent outcome
  versus on the observed one. Their ratio is what ``se_inflation`` claims to be,
  computed here from residuals rather than from the recorded moments.
- End to end: the bootstrap interval the engine actually reports, against the
  interval the same design produces on the clean outcome.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation import OutcomeErrorAssessment, assess_outcome_error
from themis.refusals import EstimatorFailure
from themis.input.syntactic_validator import validate_result


# --- linear SCM with a latent clean outcome -----------------------------------


def _make(*, n=20_000, bx=0.8, bz=1.0, a=0.5, sv2=4.0, seed=7, su2=0.0):
    """z → x → y with z → y; the observed outcome is y = y* + V, Var(V) = σ²_v.

    ``su2`` optionally adds classical error to the EXPOSURE as well, so the
    outcome channel can be exercised alongside the correction it must not
    displace. The latent clean outcome rides along as ``ystar`` and is never
    shown to the engine except where a test deliberately substitutes it."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    xstar = a * z + rng.normal(0, 1.0, n)
    ystar = 0.3 + bx * xstar + bz * z + rng.normal(0, 1.0, n)
    y = ystar + rng.normal(0, np.sqrt(sv2), n)
    x = xstar + rng.normal(0, np.sqrt(su2), n) if su2 > 0 else xstar
    return pd.DataFrame({"x": x, "z": z, "y": y, "ystar": ystar}), bx


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": [
                {"kind": "variable", "predicate": "x"},
                {"kind": "variable", "predicate": "y",
                 "measurement": "single-occasion continuous reading (noisy)"},
                {"kind": "variable", "predicate": "z"},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True}, "given": []}},
            ]}


def _ols(df, ycol, xcols):
    """(slope on xcols[0], its standard error) — an independent OLS, so the
    inflation factor is checked against arithmetic this package did not do."""
    X = np.column_stack([np.ones(len(df))] + [df[c].to_numpy() for c in xcols])
    b, *_ = np.linalg.lstsq(X, df[ycol].to_numpy(), rcond=None)
    resid = df[ycol].to_numpy() - X @ b
    s2 = resid @ resid / (len(df) - X.shape[1])
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return float(b[1]), float(se[1])


def _e2e(sv2=4.0, *, seed=7, n=20_000, ci_bootstrap=0, su2=0.0, spec=None,
         column="y"):
    df, bx = _make(n=n, sv2=sv2, seed=seed, su2=su2)
    me = {column: (spec if spec is not None else {"error_variance": sv2})}
    out = themis.estimate(
        _program(), df[["x", "y", "z"]], ci_bootstrap=ci_bootstrap,
        random_state=1, measurement_error=me,
    )
    return _program(), out["results"][0], df, bx


# --- the theorem: the point does not move -------------------------------------


def test_the_withheld_number_was_the_right_one():
    """The behaviour the deferral replaced: an outcome-side spec now yields the
    ordinary back-door answer, and that answer matches the one the same design
    gives on the latent CLEAN outcome."""
    prog, r, df, bx = _e2e(sv2=4.0)
    assert r.get("estimator_failure") is None
    assert r["status"] == "numerically_solved"
    noisy_point = r["numeric_estimate"]["point"]

    clean = themis.estimate(
        prog, df[["x", "z"]].assign(y=df["ystar"]), ci_bootstrap=0,
        random_state=1,
    )["results"][0]
    clean_point = clean["numeric_estimate"]["point"]

    assert noisy_point == pytest.approx(bx, abs=0.03)
    assert noisy_point == pytest.approx(clean_point, abs=0.03)


def test_the_correction_is_absent_because_none_is_owed():
    """No estimator claimed the query: the method is the ordinary one, and no
    corrected-versus-naive contrast is reported, because there is none."""
    _prog, r, _df, _bx = _e2e()
    assert r["numeric_estimate"]["method"] == "backdoor_linear"
    assert "regression_calibration" not in r["numeric_estimate"]
    assert "measurement_correction" not in r["numeric_estimate"]


# --- the price, checked two independent ways ----------------------------------


def test_se_inflation_equals_the_analytic_standard_error_ratio():
    """The factor claimed is the factor an independent OLS on the clean versus
    the observed outcome actually shows."""
    for sv2 in (0.5, 2.0, 8.0):
        _prog, r, df, _bx = _e2e(sv2=sv2, n=60_000)
        _, se_noisy = _ols(df, "y", ["x", "z"])
        _, se_clean = _ols(df, "ystar", ["x", "z"])
        claimed = r["outcome_error"]["se_inflation"]
        assert claimed == pytest.approx(se_noisy / se_clean, rel=0.02), sv2


def test_the_reported_interval_is_wider_by_the_reported_factor():
    """End to end, on the intervals the engine actually ships: the bootstrap CI
    under outcome noise against the CI the same design gives on the clean
    outcome."""
    prog, r, df, _bx = _e2e(sv2=4.0, n=20_000, ci_bootstrap=600)
    clean = themis.estimate(
        prog, df[["x", "z"]].assign(y=df["ystar"]), ci_bootstrap=600,
        random_state=1,
    )["results"][0]
    ne, nc = r["numeric_estimate"], clean["numeric_estimate"]
    ratio = (ne["ci_upper"] - ne["ci_lower"]) / (nc["ci_upper"] - nc["ci_lower"])
    assert ratio == pytest.approx(r["outcome_error"]["se_inflation"], rel=0.10)
    assert ratio > 1.5


def test_the_split_is_internally_exact():
    _prog, r, _df, _bx = _e2e(sv2=3.0)
    oe = r["outcome_error"]
    assert oe["signal_variance"] == pytest.approx(
        oe["residual_variance"] - oe["error_variance"], abs=1e-12)
    assert oe["noise_share"] == pytest.approx(
        oe["error_variance"] / oe["residual_variance"], abs=1e-12)
    assert oe["se_inflation"] == pytest.approx(
        np.sqrt(oe["residual_variance"] / oe["signal_variance"]), abs=1e-12)
    assert 0.0 < oe["noise_share"] < 1.0
    assert oe["se_inflation"] > 1.0


# --- estimator-level API ------------------------------------------------------


def test_assessment_recovers_the_structural_residual_variance():
    """σ²_resid − σ²_v must land on the structural error variance (1.0 by
    construction) when the exposure is measured accurately."""
    df, _bx = _make(n=100_000, sv2=4.0, seed=3)
    a = assess_outcome_error(
        df[["x", "y", "z"]], treatment="x", outcome="y",
        adjustment=("z",), error_variance=4.0,
    )
    assert isinstance(a, OutcomeErrorAssessment)
    assert a.residual_variance == pytest.approx(5.0, rel=0.03)
    assert a.signal_variance == pytest.approx(1.0, rel=0.10)
    assert a.design_vars == ("x", "z")
    assert a.sample_size == len(df)


def test_assessment_sufficient_statistics_regenerate_the_split():
    """Everything reported is a closed form of the recorded moments — the
    property the verifier depends on."""
    df, _bx = _make(n=20_000, sv2=2.0, seed=5)
    a = assess_outcome_error(
        df[["x", "y", "z"]], treatment="x", outcome="y",
        adjustment=("z",), error_variance=2.0,
    )
    s = a.sufficient_statistics
    Sigma = np.array(s["cov_matrix"])
    c = np.array(s["cov_design_y"])
    residual = s["var_y"] - float(c @ np.linalg.solve(Sigma, c))
    assert residual == pytest.approx(a.residual_variance, rel=1e-9)


# --- refusals, each naming a different mistake --------------------------------


@pytest.mark.parametrize("bad", [0.0, -1.0, float("nan")])
def test_non_positive_error_variance_refuses(bad):
    df, _bx = _make(n=4000)
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            df[["x", "y", "z"]], treatment="x", outcome="y",
            adjustment=("z",), error_variance=bad,
        )
    assert exc.value.failure_type == "non_positive_error_variance"


def test_discrete_outcome_refuses_pointing_at_the_confusion_matrix():
    df, _bx = _make(n=4000)
    df = df.copy()
    df["y"] = (df["y"] > df["y"].median()).astype(float)
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            df[["x", "y", "z"]], treatment="x", outcome="y",
            adjustment=("z",), error_variance=0.1,
        )
    assert exc.value.failure_type == "outcome_not_continuous"
    assert "misclassification" in str(exc.value)


def test_error_variance_larger_than_the_residual_refuses():
    """The declared noise does not fit under the unexplained variation, so the
    independence premise that makes the point safe is itself refuted."""
    df, _bx = _make(n=8000, sv2=1.0)
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            df[["x", "y", "z"]], treatment="x", outcome="y",
            adjustment=("z",), error_variance=500.0,
        )
    assert exc.value.failure_type == "outcome_error_exceeds_residual_variance"


def test_a_refused_spec_withholds_the_number():
    """A refusal is a refusal: no number rides out beside it."""
    _prog, r, _df, _bx = _e2e(sv2=1.0, spec={"error_variance": 500.0})
    assert r.get("numeric_estimate") is None
    fail = r["estimator_failure"]
    assert fail["estimator"] == "outcome_measurement_error"
    assert fail["failure_type"] == "outcome_error_exceeds_residual_variance"


def test_discrete_outcome_refusal_reaches_the_envelope():
    df, _bx = _make(n=8000)
    df = df.copy()
    df["y"] = (df["y"] > df["y"].median()).astype(float)
    r = themis.estimate(
        _program(), df[["x", "y", "z"]], ci_bootstrap=0,
        measurement_error={"y": {"error_variance": 0.1}},
    )["results"][0]
    assert r.get("numeric_estimate") is None
    assert r["estimator_failure"]["failure_type"] == "outcome_not_continuous"


def test_not_backdoor_identified_refuses():
    """The split is taken around the back-door design; without one there is no
    design to take it around, and that is said rather than guessed."""
    df, _bx = _make(n=8000)
    prog = _program()
    prog["statements"].insert(
        3, {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")})
    r = themis.estimate(
        prog, df[["x", "y", "z"]], ci_bootstrap=0,
        measurement_error={"y": {"error_variance": 1.0}},
    )["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["estimator"] == "outcome_measurement_error"
    assert fail["failure_type"] == "requires_backdoor_identification"


# --- composition with the exposure-side correction ----------------------------


def test_the_exposure_correction_still_runs_under_an_outcome_spec():
    """Both channels at once: the outcome's error corrects nothing but must not
    cost the caller the correction that IS available."""
    df, bx = _make(n=60_000, sv2=4.0, su2=0.5, seed=9)
    r = themis.estimate(
        _program(), df[["x", "y", "z"]], ci_bootstrap=0, random_state=1,
        measurement_error={"x": {"error_variance": 0.5},
                           "y": {"error_variance": 4.0}},
    )["results"][0]
    assert r.get("estimator_failure") is None
    ne = r["numeric_estimate"]
    assert ne["method"] == "regression_calibration"
    assert ne["point"] == pytest.approx(bx, abs=0.05)
    # the naive slope it replaces is attenuated, so the correction did work ...
    assert ne["regression_calibration"]["naive_point"] < bx - 0.1
    # ... and the outcome assessment rides alongside on the same design.
    assert r["outcome_error"]["design_vars"] == ["x", *ne["adjustment"]]


# --- disclosure ---------------------------------------------------------------


def test_the_premises_reach_the_assumption_ledger():
    """An assessment whose premises stop at its own block is, to every
    consumer, an answer that assumed nothing. They must land on the surface the
    report leads with — and beside the estimator's own, not instead of them."""
    _prog, r, _df, _bx = _e2e()
    declared = r["outcome_error"]["assumptions"]
    assert declared
    entries = ((r.get("extensions") or {}).get("assumption_ledger") or {}).get(
        "assumptions") or []
    by_id = {e.get("id"): e for e in entries}
    assert all(a in by_id for a in declared), sorted(by_id)
    # the estimator's own identification entries survive alongside
    assert any(e.get("provenance") == "inherent" for e in entries)


def test_the_non_differential_premise_is_ranked_as_invalidating():
    """It is the reason the point was left uncorrected, so its failure kills the
    answer — it cannot be filed beside a precision caveat."""
    _prog, r, _df, _bx = _e2e()
    entries = ((r.get("extensions") or {}).get("assumption_ledger") or {}).get(
        "assumptions") or []
    by_id = {e.get("id"): e for e in entries}
    nd = by_id["outcome_error_classical_non_differential_on_y"]
    assert nd["severity"] == "invalidating"
    assert nd["layer"] == "identification"
    assert nd["provenance"] == "measurement_declared"
    assert "非差异" in nd["claim"]
    known = by_id["outcome_error_variance_known_and_fixed_on_y"]
    assert known["severity"] == "confidence_only"


def test_the_report_prices_the_noise_beside_the_precision_hint():
    """The precision hint says how many more subjects halve the interval; part
    of this interval no number of subjects removes. Printing only the first
    sends the reader to buy the wrong thing."""
    _prog, r, _df, _bx = _e2e(sv2=4.0, n=4000, ci_bootstrap=200)
    report = themis.build_analysis_report(r)
    assert "结局测量误差" in report
    assert "点估计不受影响" in report
    assert "非差异" in report          # the premise, from the ledger


def test_the_result_validates_against_the_schema():
    _prog, r, _df, _bx = _e2e()
    validate_result(r)


@pytest.mark.parametrize("spec,expected", [
    ({"error_variance": 500.0}, "outcome_error_exceeds_residual_variance"),
    ({"error_variance": -1.0}, "non_positive_error_variance"),
])
def test_a_refusal_envelope_also_validates(spec, expected):
    """A refusal whose failure_type the schema does not list makes the envelope
    fail its own validation — and every public verify entry validates first, so
    such a result cannot be audited at all."""
    _prog, r, _df, _bx = _e2e(sv2=1.0, spec=spec)
    assert r["estimator_failure"]["failure_type"] == expected
    validate_result(r)


def test_a_run_with_no_spec_carries_no_block():
    df, _bx = _make(n=4000)
    r = themis.estimate(
        _program(), df[["x", "y", "z"]], ci_bootstrap=0,
    )["results"][0]
    assert "outcome_error" not in r
    entries = ((r.get("extensions") or {}).get("assumption_ledger") or {}).get(
        "assumptions") or []
    assert not any(e.get("provenance") == "measurement_declared" for e in entries)


# --- why the discrete case routes elsewhere -----------------------------------


def test_a_discrete_outcome_really_is_attenuated():
    """The contrast that justifies routing a discrete outcome to the confusion
    matrix instead: there, the same kind of noise DOES move the point, so a
    correction is owed and refusing to assess is the right answer."""
    rng = np.random.default_rng(4)
    n = 200_000
    z = rng.binomial(1, 0.5, n)
    x = rng.binomial(1, 0.3 + 0.4 * z)
    ystar = rng.binomial(1, np.clip(0.2 + 0.3 * x + 0.2 * z, 0, 1))
    flip = rng.random(n) < 0.15                      # non-differential
    y = np.where(flip, 1 - ystar, ystar)
    d = pd.DataFrame({"x": x, "z": z, "ys": ystar, "y": y})

    def ate(col):
        return sum(
            (d[(d.x == 1) & (d.z == zz)][col].mean()
             - d[(d.x == 0) & (d.z == zz)][col].mean()) * (d.z == zz).mean()
            for zz in (0, 1)
        )

    assert ate("ys") == pytest.approx(0.3, abs=0.01)
    assert abs(ate("y") - 0.3) > 0.05          # attenuated: a correction is owed


# --- verifier -----------------------------------------------------------------


def _verifiable():
    prog, r, _df, _bx = _e2e(sv2=3.0, n=8000)
    return prog, r


def test_verify_accepts_an_honest_assessment():
    prog, r = _verifiable()
    themis.verify(prog, r)
    themis.verify_outcome_error(r)


def test_verify_rejects_a_copied_inflation_factor():
    prog, r = _verifiable()
    r["outcome_error"]["se_inflation"] *= 1.4
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_a_residual_variance_that_does_not_follow():
    prog, r = _verifiable()
    r["outcome_error"]["residual_variance"] += 1.0
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_a_noise_share_that_does_not_follow():
    prog, r = _verifiable()
    r["outcome_error"]["noise_share"] = 0.5 * r["outcome_error"]["noise_share"]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_an_error_variance_that_disagrees_with_its_own_moments():
    prog, r = _verifiable()
    r["outcome_error"]["error_variance"] *= 0.5
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_a_split_taken_on_another_design():
    prog, r = _verifiable()
    r["outcome_error"]["design_vars"] = ["x"]
    r["outcome_error"]["sufficient_statistics"]["design_vars"] = ["x"]
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_an_asymmetric_covariance():
    prog, r = _verifiable()
    r["outcome_error"]["sufficient_statistics"]["cov_matrix"][0][1] += 0.5
    with pytest.raises(Exception):
        themis.verify(prog, r)


def test_verify_rejects_premises_that_never_reach_the_ledger():
    """The one-sided check: strip the folded premises and the answer becomes
    indistinguishable from one that assumed nothing."""
    prog, r = _verifiable()
    declared = set(r["outcome_error"]["assumptions"])
    ledger = r["extensions"]["assumption_ledger"]
    ledger["assumptions"] = [
        e for e in ledger["assumptions"] if e.get("id") not in declared
    ]
    with pytest.raises(Exception):
        themis.verify_outcome_error(r)


def test_verify_rejects_an_assessment_with_no_premises_at_all():
    prog, r = _verifiable()
    r["outcome_error"]["assumptions"] = []
    with pytest.raises(Exception):
        themis.verify_outcome_error(r)


def test_verify_runs_the_outcome_audit_on_the_main_path():
    """The audit is reachable through verify(), not only through its own entry."""
    prog, r = _verifiable()
    r["outcome_error"]["signal_variance"] += 0.75
    with pytest.raises(Exception):
        themis.verify(prog, r)
