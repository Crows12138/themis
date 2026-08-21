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
from themis.estimation import (
    OutcomeErrorAssessment,
    OutcomeErrorDesign,
    assess_outcome_error,
)
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


def test_no_identifying_design_refuses():
    """The split is taken around whichever design identifies the effect, and
    on this graph none of the three does — which is a conclusion about the
    graph rather than a case this package has yet to build.

    This row was the one that already looked at all three routes, and its own
    prose already said "neither back-door nor front-door identified and has no
    instrument". It filed that under the species the four rows above use for
    "back-door specifically", whose kind claims the effect IS identified.
    """
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
    assert fail["failure_type"] == "no_identifying_design"
    assert fail["kind"] == "graph"


# --- what an annotating row may and may not take away -------------------------
#
# This row annotates on success: a classical additive outcome error moves no
# conditional mean, so it has no estimand of its own and whoever answers the
# query answers it. Ownership is a property of the row rather than of the
# outcome, so the exits that stop the query have to stop it for a reason about
# the ANSWER — and the one that stopped it for a limit of the row's own reach
# was taking the number away from the handler that would have produced it, on
# a condition (no adjustment set) that is exactly what DEFINES the two routes
# below.


def _iv_program():
    """z → x → y with x ↔ y latent: no adjustment set, no mediator, one
    instrument. The route the outcome-error row must not stand in front of."""
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": [
                {"kind": "variable", "predicate": "x"},
                {"kind": "variable", "predicate": "y"},
                {"kind": "variable", "predicate": "z"},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}},
            ]}


def _iv_frame(n=8000, seed=11, sv2=4.0):
    """z ⊥ u; x = 0.8z + u + e; y* = 0.5x + 2u + e; y = y* + V."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    u = rng.normal(0, 1, n)
    x = 0.8 * z + u + rng.normal(0, 1, n)
    ystar = 0.5 * x + 2.0 * u + rng.normal(0, 1, n)
    return pd.DataFrame({"x": x, "y": ystar + rng.normal(0, np.sqrt(sv2), n),
                         "z": z})


def _frontdoor_program():
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": [
                {"kind": "variable", "predicate": "x", "domain": [True, False]},
                {"kind": "variable", "predicate": "m", "domain": [True, False]},
                {"kind": "variable", "predicate": "y"},
                {"kind": "cause", "from": _atom("x"), "to": _atom("m")},
                {"kind": "cause", "from": _atom("m"), "to": _atom("y")},
                {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}},
            ]}


def _frontdoor_frame(n=3000, seed=0):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = rng.random(n) < 1 / (1 + np.exp(-(2.0 * x.astype(float) - 1)))
    y = m.astype(float) + 2.0 * u + rng.standard_normal(n) * 0.3
    return pd.DataFrame({"x": x, "m": m, "y": y})


@pytest.mark.parametrize("program,frame", [
    (_frontdoor_program, _frontdoor_frame),
    (_iv_program, _iv_frame),
])
def test_declaring_an_outcome_error_does_not_cost_the_number(program, frame):
    # The two-version run, differing only in whether the caller says what they
    # know about their outcome. The point has to be the same one: the premise
    # under which it was safe is what the declaration asserts, so declaring it
    # cannot change what the estimator computes.
    df = frame()
    silent = themis.estimate(program(), df, ci_bootstrap=0)["results"][0]
    declared = themis.estimate(
        program(), df, ci_bootstrap=0,
        measurement_error={"y": {"error_variance": 0.5}},
    )["results"][0]

    assert silent["numeric_estimate"] is not None
    assert declared["numeric_estimate"] is not None, (
        "declaring what the caller knows about their outcome took the answer "
        "away from the handler that had produced it"
    )
    assert (declared["numeric_estimate"]["method"]
            == silent["numeric_estimate"]["method"])
    assert (declared["numeric_estimate"]["point"]
            == silent["numeric_estimate"]["point"])
    assert declared["status"] == silent["status"]


@pytest.mark.parametrize("program,frame,expected_design", [
    (_frontdoor_program, _frontdoor_frame, "front_door"),
    (_iv_program, _iv_frame, "instrumental_variable"),
])
def test_the_design_that_answered_is_the_design_that_was_priced(
    program, frame, expected_design,
):
    """The point of the whole exercise, on the two routes that used to be
    stood in front of and then left unpriced.

    The design named on the envelope has to be the one that produced the
    number rather than a design that would also have been valid: the same
    σ²_v prices differently against a residual taken around a different
    projection, so a block naming the wrong one would be arithmetic about a
    model nobody fitted.
    """
    r = themis.estimate(
        program(), frame(), ci_bootstrap=0,
        measurement_error={"y": {"error_variance": 0.5}},
    )["results"][0]
    assert r.get("estimator_failure") is None
    block = r["outcome_error"]
    assert block["design_kind"] == expected_design
    assert block["se_inflation"] > 1.0
    assert block["signal_variance"] > 0.0
    validate_result(r)


def test_the_priced_coefficient_is_the_shipped_one_not_a_second_copy():
    """The IV split is taken around β̂, and two IV rows can answer this query.

    Re-deriving β̂ inside the assessment would put a second copy of the
    shipped number in the envelope, free to disagree with it the moment the
    other row answers. Read back instead — so the two are the same object,
    not two computations that currently agree.
    """
    r = themis.estimate(
        _iv_program(), _iv_frame(), ci_bootstrap=0,
        measurement_error={"y": {"error_variance": 0.5}},
    )["results"][0]
    shipped = r["numeric_estimate"]["point"]
    priced = r["outcome_error"]["sufficient_statistics"]["design_coefficients"]
    assert priced[0] == shipped
    # and the premise is about the instrument, which is NOT in the design
    assert r["outcome_error"]["assumptions"][0] == (
        "outcome_error_mean_independent_of_instrument_z_on_y"
    )
    assert "z" not in r["outcome_error"]["design_vars"]


def test_the_two_exits_that_do_stop_the_query_still_stop_it():
    # The distinction the row turns on, stated as its own counterexample: a
    # variance that does not fit under the residual variation puts the
    # INDEPENDENCE premise in doubt, and that premise is what made the point
    # safe — so that one is a fact about the answer and withholds it. Pinned
    # beside the passing case so the two cannot be collapsed into one rule.
    _prog, refused, _df, _bx = _e2e(sv2=1.0, spec={"error_variance": 500.0})
    assert refused.get("numeric_estimate") is None
    assert (refused["estimator_failure"]["failure_type"]
            == "outcome_error_exceeds_residual_variance")


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
    assert nd["provenance"] == "caller_asserted"
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
    assert not any(str(e.get("id", "")).startswith("outcome_error_")
                   for e in entries)


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


# --- three designs, one arithmetic --------------------------------------------
#
# A classical additive error leaves the POINT of every estimand built from
# conditional means alone, on every design. What a design supplies is which
# residual absorbs σ²_v, which conditioning set the classical premise has to
# hold on, and whether the reported factor is the answer or a ceiling on it —
# and nothing else. So what follows holds the arithmetic fixed and varies only
# those three.


def _multilevel_frontdoor_frame(n=40_000, seed=13, sv2=0.25):
    """x → m → y with x ↔ y latent, and a THREE-level mediator whose effect is
    not linear in its code.

    The nonlinearity is the point: it is what makes the saturated span the
    front-door outcome model is fitted on and the raw column's span two
    different models, so a test can tell which one the split was taken
    around."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = (rng.random(n) < 1 / (1 + np.exp(-u))).astype(float)
    m = np.where(rng.random(n) < 0.3 + 0.4 * x, 2.0,
                 np.where(rng.random(n) < 0.5, 1.0, 0.0))
    ystar = 3.0 * (m == 2.0) + 2.0 * u + rng.standard_normal(n)
    return pd.DataFrame({"x": x, "m": m, "w": rng.standard_normal(n),
                         "y": ystar + rng.normal(0, np.sqrt(sv2), n)})


def _wald(df):
    """The IV coefficient a caller would hand in, computed independently."""
    return float(np.cov(df["z"], df["y"])[0, 1] / np.cov(df["z"], df["x"])[0, 1])


def _projection_residual(df, ycol, cols):
    """Var(Y) − Cov(D,Y)'Σ_D⁻¹Cov(D,Y) on raw columns, from arithmetic this
    package did not do."""
    D = np.column_stack([df[c].to_numpy(dtype=float) for c in cols])
    n = len(df)
    Dc = D - D.mean(axis=0)
    yc = df[ycol].to_numpy(dtype=float)
    yc = yc - yc.mean()
    Sigma = Dc.T @ Dc / (n - 1)
    c = Dc.T @ yc / (n - 1)
    return float(yc @ yc / (n - 1)) - float(c @ np.linalg.solve(Sigma, c))


def _closed_form_residual(stats):
    """The OLS-only closed form the general quadratic form replaced, recomputed
    from the recorded moments so the two can be held against each other."""
    Sigma = np.array(stats["cov_matrix"])
    c = np.array(stats["cov_design_y"])
    return float(stats["var_y"]) - float(c @ np.linalg.solve(Sigma, c))


def _quadratic_form_residual(stats):
    """Var(Y − b'D) from the recorded moments and the recorded coefficients,
    assuming nothing about where b came from — the re-derivation a verifier is
    owed on every route, including the one where b is not an OLS solution."""
    Sigma = np.array(stats["cov_matrix"])
    c = np.array(stats["cov_design_y"])
    b = np.array(stats["design_coefficients"])
    return (float(stats["var_y"]) - 2.0 * float(b @ c)
            + float(b @ Sigma @ b))


def _one_of_each():
    """One assessment per design, each on a frame its design is valid on."""
    back, _bx = _make(n=20_000, sv2=2.0, seed=5)
    iv = _iv_frame(n=20_000, seed=11, sv2=4.0)
    fd = _multilevel_frontdoor_frame()
    return {
        OutcomeErrorDesign.BACK_DOOR: assess_outcome_error(
            back[["x", "y", "z"]], treatment="x", outcome="y",
            adjustment=("z",), error_variance=2.0,
        ),
        OutcomeErrorDesign.INSTRUMENTAL_VARIABLE: assess_outcome_error(
            iv, treatment="x", outcome="y",
            design_kind=OutcomeErrorDesign.INSTRUMENTAL_VARIABLE,
            instruments=("z",), treatment_coefficient=_wald(iv),
            error_variance=4.0,
        ),
        OutcomeErrorDesign.FRONT_DOOR: assess_outcome_error(
            fd, treatment="x", outcome="y",
            design_kind=OutcomeErrorDesign.FRONT_DOOR,
            mediators=("m",), adjustment=("w",), error_variance=0.25,
        ),
    }


# --- the back-door route, unchanged -------------------------------------------


def test_the_back_door_numbers_are_the_ones_that_were_already_pinned():
    """Generalising the residual must not reprice the assessments already
    issued. On the OLS route the general quadratic form has to reduce to the
    closed form it replaced, and the reduction is exact rather than close."""
    df, _bx = _make(n=100_000, sv2=4.0, seed=3)
    a = assess_outcome_error(
        df[["x", "y", "z"]], treatment="x", outcome="y",
        adjustment=("z",), error_variance=4.0,
    )
    assert a.residual_variance == pytest.approx(
        _closed_form_residual(a.sufficient_statistics), rel=1e-12)
    assert a.residual_variance == pytest.approx(
        _projection_residual(df, "y", ["x", "z"]), rel=1e-12)
    # and the values the estimator-level tests above pin, unmoved
    assert a.design_vars == ("x", "z")
    assert a.residual_variance == pytest.approx(5.0, rel=0.03)
    assert a.signal_variance == pytest.approx(1.0, rel=0.10)
    assert a.sample_size == len(df)
    assert a.design_kind == "back_door"
    assert a.assumptions == (
        "outcome_error_classical_non_differential_on_y",
        "outcome_error_variance_known_and_fixed_on_y",
    )


def test_naming_the_back_door_design_changes_nothing():
    """The default is the design this estimator always computed, so naming it
    must give back the identical assessment — otherwise the vocabulary quietly
    introduced a fourth route wearing the first one's name."""
    df, _bx = _make(n=8000, sv2=2.0, seed=5)
    frame = df[["x", "y", "z"]]
    common = dict(treatment="x", outcome="y", adjustment=("z",),
                  error_variance=2.0)
    assert (assess_outcome_error(frame, design_kind="back_door", **common)
            == assess_outcome_error(frame, **common))


# --- what the recorded coefficients buy ---------------------------------------


def test_the_recorded_coefficients_regenerate_the_residual_on_every_route():
    """The property an independent audit depends on, and the reason b is
    recorded at all: on one route it is the OLS solution and on another it is
    the caller's, so a re-derivation that solves for it would agree with the
    producer only where the producer happened to solve too."""
    for kind, a in _one_of_each().items():
        stats = a.sufficient_statistics
        assert a.design_kind == kind
        assert list(stats["design_vars"]) == list(a.design_vars)
        assert len(stats["design_coefficients"]) == len(a.design_vars)
        assert a.residual_variance == pytest.approx(
            _quadratic_form_residual(stats), rel=1e-12), kind


# --- the instrumental-variable route ------------------------------------------


def test_the_instrumental_residual_is_the_structural_one():
    """Var(Y − βX) around the coefficient the caller supplied, not around the
    projection of Y on the same column. The two differ by exactly what the
    latent confounder does to the OLS slope, so taking the split around the
    projection would have priced a model nobody fitted."""
    df = _iv_frame(n=20_000, seed=11, sv2=4.0)
    beta = _wald(df)
    a = assess_outcome_error(
        df, treatment="x", outcome="y",
        design_kind="instrumental_variable",
        instruments=("z",), treatment_coefficient=beta, error_variance=4.0,
    )
    hand = float(np.var(df["y"].to_numpy() - beta * df["x"].to_numpy(), ddof=1))
    assert a.residual_variance == pytest.approx(hand, rel=1e-9)
    assert a.residual_variance > _projection_residual(df, "y", ["x"]) + 0.1
    assert a.se_inflation > 1.0


def test_the_instrument_names_the_premise_and_stays_out_of_the_design():
    """E[V | Z] = 0 is a claim about the INSTRUMENT, and E[V | X, W] = 0 is
    neither necessary nor sufficient for it — so the classical premise is not
    declared here, and the instrument that IS declared about is not a column
    the residual is taken around."""
    df = _iv_frame(n=20_000, seed=11, sv2=4.0)
    df = df.assign(w=np.random.default_rng(2).standard_normal(len(df)))
    a = assess_outcome_error(
        df, treatment="x", outcome="y",
        design_kind="instrumental_variable", adjustment=("w",),
        instruments=("z",), treatment_coefficient=_wald(df), error_variance=4.0,
    )
    assert a.design_vars == ("x", "w")
    assert "z" not in a.design_vars
    assert a.assumptions == (
        "outcome_error_mean_independent_of_instrument_z_on_y",
        "outcome_error_variance_known_and_fixed_on_y",
    )
    # the supplied coefficient is held; only the nuisance columns are fitted
    assert a.sufficient_statistics["design_coefficients"][0] == pytest.approx(
        _wald(df), rel=1e-12)


# --- the front-door route ------------------------------------------------------


def test_the_front_door_mediator_expands_to_drop_first_named_indicators():
    """The span the front-door outcome model is fitted on, named the way that
    model names it: one indicator per non-reference level, the first level
    carried by the intercept."""
    fd = _multilevel_frontdoor_frame()
    a = assess_outcome_error(
        fd, treatment="x", outcome="y", design_kind="front_door",
        mediators=("m",), adjustment=("w",), error_variance=0.25,
    )
    assert a.design_vars == ("x", "m=1.0", "m=2.0", "w")
    assert "m" not in a.design_vars
    assert "m=0.0" not in a.design_vars
    assert a.design_kind == "front_door"


def test_a_binary_mediator_yields_exactly_its_own_column():
    """Why the expansion is invisible on the common case: with two levels the
    drop-first indicator IS the column, so only the name records that an
    encoding happened."""
    df = _frontdoor_frame(n=6000, seed=0)
    a = assess_outcome_error(
        df, treatment="x", outcome="y", design_kind="front_door",
        mediators=("m",), error_variance=0.5,
    )
    assert a.design_vars == ("x", "m=True")
    assert a.residual_variance == pytest.approx(
        _projection_residual(df, "y", ["x", "m"]), rel=1e-12)


def test_the_raw_column_would_have_understated_the_cost():
    """And why it is not cosmetic anywhere else. A model linear in the
    mediator's CODE fits worse than the saturated one, so its residual is
    larger — and a larger residual makes the same σ²_v a smaller share of it.
    The coarser span errs in the one direction that matters."""
    fd = _multilevel_frontdoor_frame()
    sigma_v = 0.25
    a = assess_outcome_error(
        fd, treatment="x", outcome="y", design_kind="front_door",
        mediators=("m",), adjustment=("w",), error_variance=sigma_v,
    )
    coarse = _projection_residual(fd, "y", ["x", "m", "w"])
    assert coarse > a.residual_variance
    assert np.sqrt(coarse / (coarse - sigma_v)) < a.se_inflation


def test_the_front_door_premise_about_the_latent_confounder_stands_alone():
    """If V depends on the unmeasured X-Y confounder the front-door graph
    posits, E[V | A, M, X] ≠ 0 and the POINT moves — so it is a premise, not a
    precision caveat. No data can refute it, which is why it cannot be folded
    into the classical one; and the IV route must not carry it, since there
    only E[ZV] = 0 is needed and Z is independent of that confounder by
    assumption."""
    latent = "outcome_error_independent_of_the_front_door_latent_confounder_on_y"
    by_kind = _one_of_each()
    assert by_kind[OutcomeErrorDesign.FRONT_DOOR].assumptions == (
        "outcome_error_classical_non_differential_on_y",
        "outcome_error_variance_known_and_fixed_on_y",
        latent,
    )
    assert latent not in by_kind[
        OutcomeErrorDesign.INSTRUMENTAL_VARIABLE].assumptions
    assert latent not in by_kind[OutcomeErrorDesign.BACK_DOOR].assumptions


def test_a_mediator_the_front_door_model_could_not_encode_is_refused():
    """The span belongs to the front-door estimator, so its limit does too. A
    mediator that estimator calls continuous has no indicator basis, and an
    assessment around an invented one would price a model that cannot be
    fitted."""
    fd = _multilevel_frontdoor_frame(n=4000)
    fd = fd.assign(m=np.linspace(0.0, 1.0, len(fd)))
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            fd, treatment="x", outcome="y", design_kind="front_door",
            mediators=("m",), error_variance=0.25,
        )
    assert exc.value.failure_type == "continuous_mediator"


# --- the argument contract, both halves, constructed and run -------------------


_ARGUMENT_VALUES = {
    "mediators": ("m",),
    "instruments": ("z",),
    "treatment_coefficient": 0.5,
}


def _contract_frame():
    """One frame carrying every column any design might name."""
    df = _iv_frame(n=4000, seed=11, sv2=4.0)
    return df.assign(m=(df["x"] > 0))


@pytest.mark.parametrize("kind,name", [
    (kind, name)
    for kind in OutcomeErrorDesign
    for name in sorted(_ARGUMENT_VALUES)
    if name in kind.requires
])
def test_a_design_refuses_the_argument_it_cannot_proceed_without(kind, name):
    """Every argument a design names, withheld. Read off the registry rather
    than listed, so a fourth design cannot arrive with its own requirement
    untested."""
    supplied = {n: _ARGUMENT_VALUES[n] for n in sorted(kind.requires)}
    supplied.pop(name)
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            _contract_frame(), treatment="x", outcome="y", design_kind=kind,
            error_variance=1.0, **supplied,
        )
    assert exc.value.failure_type == "invalid_input"
    assert name in str(exc.value)


def test_an_empty_mediator_tuple_is_no_mediator_rather_than_a_mediator():
    """"Not passed" and "passed empty" are one state, so the front-door design
    refuses both — a caller told their argument arrived would go looking for
    the mediator in the design and find none."""
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            _contract_frame(), treatment="x", outcome="y",
            design_kind="front_door", mediators=(), error_variance=1.0,
        )
    assert exc.value.failure_type == "invalid_input"
    assert "mediators" in str(exc.value)


@pytest.mark.parametrize("kind,name", [
    (kind, name)
    for kind in OutcomeErrorDesign
    for name in sorted(_ARGUMENT_VALUES)
    if name not in kind.requires
])
def test_a_design_refuses_the_argument_it_has_no_place_for(kind, name):
    """Every pair the vocabulary says is impossible, constructed and run.
    Ignoring such an argument would leave the caller holding a premise they
    believe they declared, and the assessment would look identical."""
    supplied = {n: _ARGUMENT_VALUES[n] for n in sorted(kind.requires)}
    supplied[name] = _ARGUMENT_VALUES[name]
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            _contract_frame(), treatment="x", outcome="y", design_kind=kind,
            error_variance=1.0, **supplied,
        )
    assert exc.value.failure_type == "invalid_input"
    assert name in str(exc.value)


def test_an_unknown_design_is_refused_with_the_vocabulary_quoted():
    """A closed vocabulary that refuses without saying what is in it sends the
    caller to read the source."""
    df, _bx = _make(n=4000)
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            df[["x", "y", "z"]], treatment="x", outcome="y",
            design_kind="frontdoor", adjustment=("z",), error_variance=1.0,
        )
    assert exc.value.failure_type == "invalid_input"
    for known in OutcomeErrorDesign:
        assert str(known) in str(exc.value)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), "0.5", True, [0.5]])
def test_a_coefficient_the_residual_cannot_be_taken_around_is_refused(bad):
    """β̂ is what the structural residual is subtracted around; a value that is
    not a finite number makes the residual not a number either, and the
    refusal has to name the argument rather than surface as a nan downstream."""
    with pytest.raises(EstimatorFailure) as exc:
        assess_outcome_error(
            _contract_frame(), treatment="x", outcome="y",
            design_kind="instrumental_variable", instruments=("z",),
            treatment_coefficient=bad, error_variance=1.0,
        )
    assert exc.value.failure_type == "invalid_input"
    assert "treatment_coefficient" in str(exc.value)


# --- what the design name is, once it leaves ----------------------------------


def test_whether_the_factor_is_exact_is_a_fact_of_the_design_and_only_that():
    """The back-door and IV factors are exact; the front-door one overstates
    the loss, because the influence function there carries a second term with
    no outcome residual in it. That is a function of the design, so recording
    it beside the factor as well would be a second record of the same fact,
    free to disagree with the first."""
    import dataclasses

    assert OutcomeErrorDesign.BACK_DOOR.exact is True
    assert OutcomeErrorDesign.INSTRUMENTAL_VARIABLE.exact is True
    assert OutcomeErrorDesign.FRONT_DOOR.exact is False
    names = {f.name for f in dataclasses.fields(OutcomeErrorAssessment)}
    assert not [n for n in names if "exact" in n or "bound" in n]


def test_the_design_name_leaves_as_the_plain_string_it_always_was():
    """It becomes a field of the envelope, and whoever serialises the envelope
    must not receive the registry along with it."""
    import copy
    import pickle

    design = OutcomeErrorDesign.FRONT_DOOR
    assert design == "front_door"
    assert type(copy.deepcopy(design)) is str
    assert type(pickle.loads(pickle.dumps(design))) is str
    assert pickle.loads(pickle.dumps(design)) == "front_door"
