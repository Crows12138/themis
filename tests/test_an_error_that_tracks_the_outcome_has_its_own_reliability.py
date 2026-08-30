# -*- coding: utf-8 -*-
"""Differential error: the premise regression calibration cannot drop for free.

The classical correction assumes the exposure's error is independent of
everything — the truth and the outcome alike. That last clause is the
NON-DIFFERENTIAL premise, and the deferral this overturns recorded it as a
scope note, as though dropping it made the answer rougher. It does not. A
differential error inflates the observed exposure-outcome COVARIANCE as well
as the exposure's variance, and a correction that divides only the second by
a reliability ratio moves one of the two things that moved. Measured at a
true 0.8, with the correct total error variance handed to both:

    δ      naive     regression calibration     here
    −0.4   0.128     0.398                      0.800
    +0.5   0.598     0.900                      0.799

so the deferral's cost was a number wrong in either direction, and by more
than the attenuation it was correcting.

Three groups for three claims:

- the closed form recovers βx where the classical one cannot, and at δ = 0
  IS the classical one — matched to a floating-point tie, so the module that
  has been in the package for months is this one's oracle;
- the two declarations are checked against each other and against the
  sample, and each contradiction has its own refusal because the reader's
  next move differs;
- δ is a declaration and routes like one. Nothing in (W, Y, Z) separates a δ
  from a βx, so it can only arrive from outside — and the axis it is
  declared on is judged, because an error tracking an adjusted covariate is
  classical rather than a smaller case of this.
"""
from __future__ import annotations

import ast
import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.differential_error import (
    DifferentialErrorEstimate,
    estimate_differential_error,
)
from themis.estimation.dispatch import _differential_error_block
from themis.estimation.regression_calibration import (
    estimate_regression_calibration,
)
from themis.output.analysis_report import build_analysis_report
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.differential_error_rules import (
    verify_differential_error_numeric as audit,
)
from themis.verifier.errors import VerificationError

BETA_X = 0.8
DELTA = 0.3
SIGMA2_0 = 0.5

_TRACKS = "design_error_tracks_the_outcome_on_w"
_COEFFICIENT = "differential_coefficient_known_and_fixed_on_w"
_VARIANCE = "design_error_variance_known_and_fixed_on_w"
OWED = (_TRACKS, _COEFFICIENT, _VARIANCE)


# --- data ---------------------------------------------------------------------


def _residualise(col: np.ndarray, Z: np.ndarray) -> np.ndarray:
    D = np.column_stack([np.ones(len(col)), Z])
    return col - D @ np.linalg.solve(D.T @ D, D.T @ col)


def _frame(delta=DELTA, sigma2_0=SIGMA2_0, n=200_000, seed=0, beta=BETA_X):
    """The error carries a component that tracks the OUTCOME.

    Returns the frame and the TOTAL Var(W − X*), which is what
    ``error_variance`` means here as it does everywhere else in the family —
    the outcome-tracking share of it is derived rather than declared twice.
    """
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x_true = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + beta * x_true + 0.4 * z + rng.normal(0, 1.0, n)
    u = (delta * _residualise(y, z[:, None])
         + rng.normal(0, np.sqrt(sigma2_0), n))
    return (pd.DataFrame({"w": x_true + u, "y": y, "z": z}),
            float(np.var(u, ddof=1)))


def _fit(df=None, sigma_u=None, **kwargs):
    if df is None:
        df, sigma_u = _frame()
    kwargs.setdefault("error_variance", sigma_u)
    kwargs.setdefault("differential_by", "y")
    kwargs.setdefault("differential_coefficient", DELTA)
    kwargs.setdefault("ci_bootstrap", 0)
    return estimate_differential_error(
        df, treatment="w", outcome="y", adjustment=("z",), **kwargs)


def _envelope(est: DifferentialErrorEstimate) -> dict:
    """The numeric_estimate dispatch writes, built through the producer's own
    block so the audit reads what ships.

    ``assumptions`` is on it because dispatch puts it there, and the audit
    holds the variance premise against what the block says was done with the
    variance. An envelope short of a field dispatch writes is a fixture that
    can pass an audit the shipped artifact would fail."""
    return {
        "point": est.point,
        "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper,
        "ci_level": est.ci_level,
        "method": est.method,
        "assumptions": list(est.assumptions),
        "treatment": est.treatment,
        "outcome": est.outcome,
        "differential_error": _differential_error_block(est),
    }


@pytest.fixture(scope="module")
def honest() -> dict:
    """One accepted artifact, so each forgery below is it with one change."""
    return _envelope(_fit())


# --- the closed form, and the oracle it reduces to ----------------------------


@pytest.mark.parametrize("delta", [-0.4, -0.2, 0.2, 0.3, 0.5])
def test_the_correction_recovers_the_slope_at_every_declared_delta(delta):
    """Both directions, because a differential error is not a heavier
    attenuation: at δ < 0 the naive slope is crushed far below the truth and
    at δ > 0 it is held up near it, and one correction has to handle both."""
    df, sigma_u = _frame(delta=delta)
    est = _fit(df, sigma_u, differential_coefficient=delta)
    assert est.point == pytest.approx(BETA_X, abs=0.01)


def test_the_classical_correction_is_wrong_in_both_directions():
    """What the deferral cost, as numbers. The same frame, the same TOTAL
    error variance — the quantity regression calibration asks for and is
    entitled to — and it lands on either side of the truth depending on
    which way the error tracks."""
    seen = {}
    for delta in (-0.4, 0.5):
        df, sigma_u = _frame(delta=delta)
        classical = estimate_regression_calibration(
            df, treatment="w", outcome="y", adjustment=("z",),
            error_variance=sigma_u, ci_bootstrap=0)
        here = _fit(df, sigma_u, differential_coefficient=delta)
        seen[delta] = (classical.point, here.point)
        assert here.point == pytest.approx(BETA_X, abs=0.01)
    # Not merely imprecise: one is well below the truth and the other well
    # above it, so no fixed adjustment to the classical answer would do.
    assert seen[-0.4][0] < BETA_X - 0.3
    assert seen[0.5][0] > BETA_X + 0.05


def test_at_a_vanishing_delta_it_is_regression_calibration():
    """The oracle. Every formula here reduces to the classical correction's
    at δ = 0, so the module that has been shipping for months is what this
    one is checked against — not a restatement of its own algebra."""
    df, sigma_u = _frame(delta=0.0)
    classical = estimate_regression_calibration(
        df, treatment="w", outcome="y", adjustment=("z",),
        error_variance=sigma_u, ci_bootstrap=0)
    here = _fit(df, sigma_u, differential_coefficient=1e-12)
    assert here.point == pytest.approx(classical.point, abs=1e-9)
    assert here.reliability == pytest.approx(classical.reliability, abs=1e-9)
    assert here.naive_point == pytest.approx(classical.naive_point, abs=1e-12)


def test_the_covariance_comes_off_before_the_variance_does():
    """The two steps, pinned as two. A reader who takes the reliability
    alone and divides the naive slope by it gets a third number that is
    neither the producer's nor the truth — which is why both are reported
    and why the report says so in words."""
    est = _fit()
    assert est.outcome_tracking_covariance != pytest.approx(0.0)
    assert est.naive_point / est.reliability != pytest.approx(
        est.point, rel=0.05)
    assert est.nondifferential_variance == pytest.approx(SIGMA2_0, rel=0.02)


def test_a_bootstrap_interval_holds_the_declarations_fixed():
    """σ²_u and δ are declarations about the measurement, not quantities
    this sample estimates, so a resample that re-drew them would widen the
    interval by re-drawing something nobody drew."""
    df, sigma_u = _frame(n=20_000)
    est = _fit(df, sigma_u, ci_bootstrap=200, random_state=7)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper


# --- the two declarations, judged --------------------------------------------


def test_a_delta_too_large_for_the_declared_variance_is_refused():
    """Settled before the data is consulted: δ²·Var(Y|Z) is the variance the
    outcome-tracking component alone contributes, so a smaller total
    describes an error whose classical part has negative variance."""
    df, sigma_u = _frame()
    with pytest.raises(EstimatorFailure) as exc:
        _fit(df, sigma_u, differential_coefficient=1.5)
    assert exc.value.failure_type is (
        Refusal.DIFFERENTIAL_COEFFICIENT_EXCEEDS_THE_DECLARED_VARIANCE)


def test_declarations_that_leave_the_exposure_no_variance_are_refused():
    """The other contradiction, and it is with the SAMPLE rather than
    between the two declarations — which is why it has its own species."""
    df, sigma_u = _frame()
    with pytest.raises(EstimatorFailure) as exc:
        _fit(df, sigma_u, error_variance=3.0, differential_coefficient=0.05)
    assert exc.value.failure_type is (
        Refusal.DIFFERENTIAL_CORRECTION_LEAVES_NO_TRUE_VARIANCE)


def test_an_axis_that_is_an_adjusted_covariate_has_an_answer_waiting():
    """Not a scope boundary. Partial that covariate out of both columns and
    what is left is independent of the truth — which is classical error —
    so the reader is sent to the ordinary correction rather than told this
    package cannot help."""
    df, sigma_u = _frame()
    with pytest.raises(EstimatorFailure) as exc:
        _fit(df, sigma_u, differential_by="z")
    assert exc.value.failure_type is (
        Refusal.DIFFERENTIAL_AXIS_IS_AN_ADJUSTED_COVARIATE)


def test_an_axis_that_is_neither_is_a_gap_and_says_so():
    df, sigma_u = _frame()
    with pytest.raises(EstimatorFailure) as exc:
        _fit(df, sigma_u, differential_by="q")
    assert exc.value.failure_type is Refusal.DIFFERENTIAL_AXIS_IS_NOT_THE_OUTCOME


@pytest.mark.parametrize("kwargs", [
    {"differential_by": None},
    {"differential_coefficient": None},
    {"error_variance": None},
    {"error_variance": 0.0},
    {"error_variance": -1.0},
    {"differential_coefficient": float("nan")},
    {"differential_coefficient": "0.3"},
])
def test_a_declaration_that_is_not_one_is_refused(kwargs):
    df, sigma_u = _frame()
    with pytest.raises(EstimatorFailure):
        _fit(df, sigma_u, **kwargs)


def test_a_near_discrete_exposure_is_a_different_object():
    df, sigma_u = _frame(n=4000)
    df["w"] = np.round(df["w"]).clip(-2, 2)
    with pytest.raises(EstimatorFailure) as exc:
        _fit(df, sigma_u)
    assert exc.value.failure_type is Refusal.EXPOSURE_NOT_CONTINUOUS


# --- the audit ----------------------------------------------------------------


def test_an_honest_estimate_is_accepted(honest):
    audit(honest)


def test_an_estimate_from_another_method_is_not_this_audit_s_business():
    audit({"method": "backdoor_linear", "point": 1.0})


@pytest.mark.parametrize("path, value", [
    (("point",), 0.9),
    (("differential_error", "naive_point"), 0.5),
    (("differential_error", "reliability"), 0.9),
    (("differential_error", "exposure_variance"), 1.4),
    (("differential_error", "nondifferential_variance"), 0.2),
    (("differential_error", "outcome_tracking_covariance"), 0.1),
    (("differential_error", "sufficient_statistics", "var_y"), 4.0),
    (("differential_error", "sufficient_statistics", "error_variance"), 0.9),
    (("differential_error", "sufficient_statistics",
      "differential_coefficient"), 0.1),
])
def test_a_scalar_that_does_not_follow_from_the_moments_is_rejected(
        honest, path, value):
    forged = copy.deepcopy(honest)
    target = forged
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(VerificationError):
        audit(forged)


def test_the_forgery_the_reliability_alone_would_hide(honest):
    """The one a hand-checking reader cannot catch: keep the reliability and
    the variances honest, and simply skip the covariance step — the point
    becomes naive/λ, which is what a reader redoing the classical arithmetic
    would compute and agree with."""
    forged = copy.deepcopy(honest)
    de = forged["differential_error"]
    forged["point"] = de["naive_point"] / de["reliability"]
    with pytest.raises(VerificationError, match="corrected exposure slope"):
        audit(forged)


def test_a_block_that_names_an_axis_other_than_the_outcome(honest):
    forged = copy.deepcopy(honest)
    forged["differential_error"]["differential_by"] = "z"
    with pytest.raises(VerificationError, match="tracks"):
        audit(forged)


def test_a_block_that_corrects_a_column_the_answer_is_not_about(honest):
    forged = copy.deepcopy(honest)
    forged["differential_error"]["exposure"] = "z"
    with pytest.raises(VerificationError):
        audit(forged)


def test_a_design_that_does_not_lead_with_the_exposure(honest):
    forged = copy.deepcopy(honest)
    stats = forged["differential_error"]["sufficient_statistics"]
    stats["design_vars"] = list(reversed(stats["design_vars"]))
    with pytest.raises(VerificationError):
        audit(forged)


def test_a_covariance_matrix_that_is_not_one(honest):
    forged = copy.deepcopy(honest)
    forged["differential_error"]["sufficient_statistics"][
        "cov_matrix"][0][1] += 0.5
    with pytest.raises(VerificationError, match="symmetric"):
        audit(forged)


def test_a_zero_coefficient_is_the_other_method_s_case(honest):
    """A block claiming this method for δ = 0 took the long road to a number
    the short one already gives, and the ledger line beside it would tell a
    reader a premise was withdrawn that was not."""
    forged = copy.deepcopy(honest)
    forged["differential_error"]["sufficient_statistics"][
        "differential_coefficient"] = 0.0
    with pytest.raises(VerificationError, match="non-differential"):
        audit(forged)


def test_a_block_that_should_have_been_refused_is_rejected_not_believed(
        honest):
    """The guards are re-run rather than trusted: a producer that shipped
    through one of them shipped a variance that is not one, and nothing in
    the point shows it."""
    forged = copy.deepcopy(honest)
    stats = forged["differential_error"]["sufficient_statistics"]
    stats["differential_coefficient"] = 3.0
    with pytest.raises(VerificationError, match="should not exist"):
        audit(forged)


def test_an_estimate_with_no_block_stands_on_the_producer_s_word(honest):
    forged = copy.deepcopy(honest)
    del forged["differential_error"]
    with pytest.raises(VerificationError, match="nothing to re-derive"):
        audit(forged)


def test_the_audit_does_not_import_the_estimator():
    """A correction re-derived through the arithmetic its producer wrote is
    not an independent audit. Read off the import statements, so the module
    can go on SAYING what it must not do."""
    import themis.verifier.differential_error_rules as rules
    tree = ast.parse(pathlib.Path(rules.__file__).read_text(encoding="utf-8"))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            reached.add("." * node.level + (node.module or ""))
    assert not any("estimation" in m for m in reached), sorted(reached)


# --- the declaration routes ---------------------------------------------------


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "w",
             "measurement": "self-reported intake (noisy)"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("w")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("w"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _run(spec: dict, df=None) -> dict:
    frame = _frame()[0] if df is None else df
    out = themis.estimate(_program(), frame, ci_bootstrap=0,
                          measurement_error=spec)
    return out["results"][0]


@pytest.fixture(scope="module")
def declared() -> dict:
    df, sigma_u = _frame()
    return _run({"w": {"error_variance": sigma_u, "differential_by": "y",
                       "differential_coefficient": DELTA}}, df)


def test_the_declaration_reaches_the_envelope_and_the_audit(declared):
    ne = declared["numeric_estimate"]
    assert ne["method"] == "differential_regression_calibration"
    assert ne["point"] == pytest.approx(BETA_X, abs=0.01)
    block = ne["differential_error"]
    assert block["differential_by"] == "y"
    assert block["differential_coefficient"] == DELTA
    assert block["design_vars"] == ["w", "z"]
    audit(ne)


def test_the_premises_reach_the_ledger_at_the_severity_they_deserve(declared):
    ledger = declared["extensions"]["assumption_ledger"]["assumptions"]
    by_id = {e["id"]: e for e in ledger}
    assert set(OWED) <= set(by_id)
    # All three hold the POINT up — a wrong δ is a wrong number, not a wider
    # interval — so none of them may be graded as touching only the width.
    for owed in OWED:
        assert by_id[owed]["layer"] == "identification"
    assert not by_id[_TRACKS]["testable"]
    assert by_id[_COEFFICIENT]["testable"]


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_report_says_both_steps(declared, lang):
    text = build_analysis_report(declared, lang=lang)
    for token in (("是误差而不是效应", "除以 λ") if lang == "zh"
                  else ("error rather than effect", "divided by λ")):
        assert token in text, text


def test_a_declared_coefficient_is_what_routes():
    """Nothing in the data does. The same columns and the same variance
    answer by the classical correction when no δ is declared, and a declared
    zero is the classical case rather than a longer road to it."""
    df, sigma_u = _frame()
    assert _run({"w": {"error_variance": sigma_u}},
                df)["numeric_estimate"]["method"] == "regression_calibration"
    assert _run({"w": {"error_variance": sigma_u, "differential_by": "y",
                       "differential_coefficient": 0.0}},
                df)["numeric_estimate"]["method"] == "regression_calibration"
    assert _run({"w": {"error_variance": sigma_u, "differential_by": "y",
                       "differential_coefficient": DELTA,
                       "outcome_model": "logistic"}},
                df)["numeric_estimate"]["method"] == (
                    "differential_regression_calibration")


def test_a_berkson_structure_and_a_differential_coefficient_cannot_both_hold():
    """Two premises that contradict each other, and the row picks neither.
    Berkson error IS the error's independence from the recorded value; an
    error tracking the outcome is not that, because the outcome depends on
    the truth and the truth is the recorded value plus the error."""
    df, sigma_u = _frame()
    result = _run({"w": {"structure": "berkson", "error_variance": sigma_u,
                         "differential_by": "y",
                         "differential_coefficient": DELTA}}, df)
    assert "berkson_error" not in result
    assert result["estimator_failure"]["failure_type"] == (
        "berkson_and_differential_are_incompatible_premises")


def test_a_second_mismeasured_column_is_refused():
    """The closed form partials the adjustment set out of both columns and
    so needs it measured exactly; a second mismeasured column would need the
    covariance between the two errors, which a per-column variance does not
    carry."""
    df, sigma_u = _frame()
    result = _run({"w": {"error_variance": sigma_u, "differential_by": "y",
                         "differential_coefficient": DELTA},
                   "z": {"error_variance": 0.2}}, df)
    assert result.get("numeric_estimate") is None
    assert result["estimator_failure"]["estimator"] == "differential_error"


def test_a_query_with_no_back_door_design_is_told_so():
    program = _program()
    program["statements"].insert(
        3, {"kind": "bidirected", "left": _atom("w"), "right": _atom("y")})
    df, sigma_u = _frame(n=4000)
    out = themis.estimate(program, df, ci_bootstrap=0,
                          measurement_error={"w": {
                              "error_variance": sigma_u,
                              "differential_by": "y",
                              "differential_coefficient": DELTA}})
    result = out["results"][0]
    assert result.get("numeric_estimate") is None
    assert result["estimator_failure"]["failure_type"] in {
        "requires_backdoor_identification", "no_identifying_design"}
