"""A check that answers by fitting a model, and leaves a record either way.

Two of the judgements a back-door-family run makes are made by FITTING a
model and reading where its probabilities land: overlap, against P(X|Z), and
quasi-separation, against P(Y|X,Z). Both used to speak only through a
``data_gap_report`` entry — and a gap is raised only when something is wrong,
so an answer carrying neither could not be read as "the check passed" rather
than "the check was never made".

That silence cost two things. A reader could not tell the two apart. And the
assumption ledger, which can now say what a check concluded, had nothing to
read a verdict off — so a CONTINUOUS adjustment set, where the cell count
declines and the fit is the only witness there is, carried no positivity
verdict at all while the gap list beside it said overlap was violated.

The fix is the shape the two gaps that already got this right use: the
finding is arithmetic on a statistic the envelope carries. What is pinned
here:

- both records are written whichever side of the threshold the run falls;
- the gap is exactly the threshold comparison on the record, so the two
  surfaces cannot disagree about one frame;
- the threshold travels WITH the finding, so nothing restates it;
- the fitted witness earns ``not_refuted`` and never ``held`` — a logistic
  fit smooths across cells and estimates the condition the count settles;
- the saturation record adjudicates NOTHING, which is a decision: the form
  line beside it says what was done rather than something data can refuse.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.output import result_orchestrator
from themis.output.analysis_report import build_analysis_report
from themis.verifier.errors import VerificationError

POSITIVITY = "positivity_overlap_of_treatment_arms"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "u"}]},
    "statements": [
        {"kind": "variable", "predicate": "x", "domain": [True, False]},
        {"kind": "variable", "predicate": "y", "domain": [True, False]},
        {"kind": "variable", "predicate": "z", "scale": "continuous"},
        {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
        {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": []}},
    ],
}


def _frame(strength: float, n: int = 4000, seed: int = 7) -> pd.DataFrame:
    """A continuous confounder. ``strength`` drives the propensity to the
    edges, so overlap fails with no cell to count it in."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = rng.random(n) < 1 / (1 + np.exp(-strength * z))
    y = rng.random(n) < np.clip(0.3 + 0.2 * x + 0.15 * z, 0.01, 0.99)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _separated(n: int = 3000, seed: int = 11) -> pd.DataFrame:
    """An adjustment column that settles the outcome, so the fitted outcome
    model is quasi-separated while overlap is fine."""
    rng = np.random.default_rng(seed)
    return pd.DataFrame({"x": rng.random(n) < 0.5,
                         "z": (z := rng.normal(size=n)),
                         "y": z > 0.0})


@pytest.fixture(scope="module")
def mild():
    return themis.estimate(PROGRAM, _frame(0.4), ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def thin():
    return themis.estimate(PROGRAM, _frame(6.0), ci_bootstrap=0)["results"][0]


@pytest.fixture(scope="module")
def saturated():
    return themis.estimate(PROGRAM, _separated(),
                           ci_bootstrap=0)["results"][0]


def _kinds(result: dict) -> list[str]:
    return [g["kind"] for g in
            (result.get("data_gap_report") or {}).get("gaps", ())]


def _line(result: dict, assumption_id: str) -> dict:
    entries = result["extensions"]["assumption_ledger"]["assumptions"]
    return next(e for e in entries if e.get("id") == assumption_id)


# --- the record is there either way -------------------------------------------


@pytest.mark.parametrize("field", ["fitted_overlap", "outcome_saturation"])
def test_the_passing_run_records_what_it_found(mild, field):
    """The half that was missing. Nothing was wrong, so no gap was raised —
    and until this record existed that was the entire trace of a check that
    ran on every back-door-family answer."""
    found = mild["numeric_estimate"][field]
    assert found["share_outside"] <= found["threshold"]
    assert 0.0 <= found["p_min"] <= found["p_max"] <= 1.0


def test_the_failing_run_records_the_same_shape(thin):
    found = thin["numeric_estimate"]["fitted_overlap"]
    assert found["share_outside"] > found["threshold"]
    assert "propensity_overlap_violation" in _kinds(thin)


def test_the_saturated_run_records_the_same_shape(saturated):
    found = saturated["numeric_estimate"]["outcome_saturation"]
    assert found["share_outside"] > found["threshold"]
    assert "outcome_model_quasi_separation" in _kinds(saturated)


@pytest.mark.parametrize("kind,field", [
    ("propensity_overlap_violation", "fitted_overlap"),
    ("outcome_model_quasi_separation", "outcome_saturation"),
])
@pytest.mark.parametrize("strength", [0.4, 2.0, 6.0])
def test_the_gap_is_the_comparison_on_the_record(kind, field, strength):
    """The gap and the record cannot disagree about one frame, because the
    gap is now arithmetic on the statistic the envelope carries — the shape
    the penalty and treatment-bridge gaps already use, and the one the
    overlap witnesses were the exception to."""
    result = themis.estimate(PROGRAM, _frame(strength),
                             ci_bootstrap=0)["results"][0]
    found = result["numeric_estimate"].get(field)
    assert found is not None
    assert (kind in _kinds(result)) is (
        found["share_outside"] > found["threshold"])


def test_the_threshold_travels_with_the_finding(mild):
    """Nobody restates it. A number written down in the estimator, the
    producer of the verdict and the verifier is three chances to disagree,
    and the verdict claims the DATA refused a premise — so it has to say that
    exactly where the gap beside it says the same thing."""
    for field in ("fitted_overlap", "outcome_saturation"):
        assert "threshold" in mild["numeric_estimate"][field]


# --- what the ledger does with it ---------------------------------------------


def test_the_only_witness_there_is_still_answers(mild, thin):
    """A continuous adjustment set has no cells to count. Before the record
    existed the line said nothing at all, on both frames alike."""
    assert _line(mild, POSITIVITY)["checked"] == {
        "verdict": "not_refuted", "by": "fitted_propensity_range"}
    assert _line(thin, POSITIVITY)["checked"] == {
        "verdict": "refuted", "by": "fitted_propensity_range"}


def test_a_fit_never_earns_held():
    """It estimates the condition the count settles, and the difference is
    measurable: on the frame this repository keeps for it, a logistic fit
    hands a stratum whose empirical treated rate is 0.000 a comfortable
    0.091. A vocabulary that let a fit say "held" would be printing the
    model's opinion as the data's answer."""
    from themis import ledger

    assert ledger.Check.FITTED_PROPENSITY_RANGE.a_pass_settles_it is False
    assert ledger.checked(ledger.Check.FITTED_PROPENSITY_RANGE, False)[1] is (
        ledger.Verdict.NOT_REFUTED)


def test_saturation_adjudicates_nothing(saturated):
    """Declared rather than forgotten. The form line says the outcome was
    modelled by a logit regression — a statement of what was done, not a
    premise this data can refuse — so a verdict there would be a vocabulary
    answering a question nobody asked."""
    entries = saturated["extensions"]["assumption_ledger"]["assumptions"]
    forms = [e for e in entries if "outcome_regression" in str(e.get("id"))]
    assert forms
    assert all("checked" not in e for e in forms)
    adjudicated = {i for ids, _c, _r
                   in result_orchestrator.WHAT_THIS_RUN_CHECKED for i in ids}
    assert not any("outcome_regression" in i for i in adjudicated)


# --- what the reader is handed ------------------------------------------------


def test_the_report_says_the_check_passed(mild):
    report = build_analysis_report(mild, program=PROGRAM)
    assert "重叠（拟合倾向分）" in report
    assert "判定线以内" in report


def test_the_report_says_what_the_saturated_fit_costs(saturated):
    report = build_analysis_report(saturated, program=PROGRAM)
    assert "准分离的信号" in report


# --- the verifier re-derives it -----------------------------------------------


def _tampered(result: dict, change) -> dict:
    bad = copy.deepcopy(result)
    change(bad)
    return bad


def test_the_honest_answers_pass(mild, thin, saturated):
    for result in (mild, thin, saturated):
        themis.verify_assumption_ledger(result)


def test_softening_the_fitted_refutation_is_caught(thin):
    def soften(result):
        (result["extensions"]["assumption_ledger"]["assumptions"][0]
         ["checked"]["verdict"]) = "not_refuted"

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(thin, soften))


def test_a_fit_reported_as_settling_it_is_caught(mild):
    def overstate(result):
        _line(result, POSITIVITY)["checked"]["verdict"] = "held"

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(mild, overstate))


def test_moving_the_threshold_moves_the_verdict_the_check_owes(thin):
    """The verifier judges against the record's OWN threshold rather than one
    it restates, so the two move together. Raise the line on the record and
    leave the verdict alone, and the numbers no longer say what the ledger
    says — which is the same defect as editing the verdict, arrived at from
    the other side."""
    def loosen(result):
        result["numeric_estimate"]["fitted_overlap"]["threshold"] = 1.0

    with pytest.raises(VerificationError, match="re-read"):
        themis.verify_assumption_ledger(_tampered(thin, loosen))
