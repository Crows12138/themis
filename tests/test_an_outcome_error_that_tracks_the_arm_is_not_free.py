"""A mismeasured outcome whose error tracks the exposure.

The package said, everywhere and for a long time, that a classical additive
error on a continuous outcome costs precision and not bias. The sentence is
true, and the word doing the work in it is CLASSICAL — which the caller was
already able to withdraw, by declaring in the same spec that the error tracks
the exposure. Nothing read that key. The row that owns an outcome-error
declaration read ``error_variance`` and priced it; the answer beside it was the
ordinary back-door slope; and the ordinary back-door slope, under

    Y = Y* + δ·(X − E[X|Z]) + f,   f ⊥ (X, Z)

estimates βx + δ. So the one declaration that says the number is wrong was
dropped without a word, and the number shipped as ``numerically_solved``.

Measured before the fix, at a true 0.8 with δ = 0.5: the envelope returned
1.3103 — β + δ to four places — with no refusal, no annotation, and no premise
naming δ anywhere on it.

Two defects rather than one, and the second only became visible once the first
was fixed. The gate that judges whether a declared σ²_v fits under the residual
compares the declared TOTAL against it. That comparison is written for an error
that is wholly in the residual, which is what a classical error IS; when δ is
declared, the design has already absorbed δ·(X − E[X|Z]) into the exposure's
coefficient and only the remainder is left there. So a perfectly consistent
declaration was refused outright at δ = 1.5 — the whole query, not the price —
and where it was not refused the precision cost was taken on a variance that
was not in the residual it was divided by.

An unblinded outcome assessor is the ordinary way this arises, which is why
this is not an exotic case to have been getting wrong.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.differential_error import (
    estimate_differential_outcome_error,
)
from themis.estimation.dispatch import (
    _differential_outcome_error_block, _outcome_error_block,
)
from themis.estimation.outcome_error import assess_outcome_error
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier import (
    verify_differential_outcome_error_numeric, verify_outcome_error,
)
from themis.verifier.errors import VerificationError

BETA = 0.8
SIGMA_F = 0.6
ARGS = [{"type": "const", "name": "u"}]
ATOM = {"predicate": "x", "args": ARGS}

PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "u"}]},
    "statements": [
        {"kind": "variable", "predicate": "x"},
        {"kind": "variable", "predicate": "y"},
        {"kind": "variable", "predicate": "z"},
        {"kind": "cause", "from": ATOM, "to": {"predicate": "y", "args": ARGS}},
        {"kind": "cause", "from": {"predicate": "z", "args": ARGS}, "to": ATOM},
        {"kind": "cause", "from": {"predicate": "z", "args": ARGS},
         "to": {"predicate": "y", "args": ARGS}},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": ATOM, "value": True},
            "target": {"atom": {"predicate": "y", "args": ARGS}, "value": True},
            "given": []}},
    ],
}


def _sample(delta: float, n: int = 20000, seed: int = 3):
    """The declared model, generated exactly as declared.

    ``V = δ·(X − E[X|Z]) + f`` and not ``δ·X + f``: the two give the same point
    — δ·E[X|Z] is linear in Z and lands in the covariates' coefficients — and
    differ in what the declared total decomposes into. The family settled that
    question on the other channel, where σ²_u = σ²_0 + δ²·Var(Ỹ|Z), and a
    package whose two differential corrections split a declared variance
    against different quantities would be asking its callers to know which
    channel they were on before they could say what their number meant.
    """
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    x_resid = rng.standard_normal(n)
    x = 0.7 * z + x_resid
    truth = BETA * x + 0.5 * z + rng.standard_normal(n)
    v = delta * x_resid + rng.standard_normal(n) * SIGMA_F
    frame = pd.DataFrame({"x": x, "z": z, "y": truth + v})
    sigma_v = delta * delta * float(np.var(x_resid, ddof=1)) + SIGMA_F ** 2
    return frame, sigma_v


# --- what the number is -------------------------------------------------------


@pytest.mark.parametrize("delta", (-0.4, 0.3, 0.5, 1.5))
def test_the_declared_shift_comes_back_off_the_slope(delta):
    """Conformance at four coefficients, including one large enough that the
    naive answer is nearly twice the truth.

    The naive number is checked too, and not as decoration: it is what the
    package used to ship, so a run where the correction silently did nothing
    would pass a test that only looked at the truth if the bias happened to be
    small. Here it is required to be large.
    """
    frame, sigma_v = _sample(delta)
    est = estimate_differential_outcome_error(
        frame, treatment="x", outcome="y", adjustment=("z",),
        error_variance=sigma_v, differential_by="x",
        differential_coefficient=delta, ci_bootstrap=0)
    assert abs(est.point - BETA) < 0.03
    assert abs(est.naive_point - (BETA + delta)) < 0.03
    assert abs(est.naive_point - BETA) > 10 * abs(est.point - BETA)


def test_the_declared_variance_does_not_reach_the_point():
    """σ²_v prices precision and settles consistency, and touches nothing else.

    The sharpest statement of what separates the two channels: on the exposure
    side the declared variance is half the correction, and here a run that
    doubled it would return the same number. So the test is an identity rather
    than a tolerance.
    """
    frame, sigma_v = _sample(0.5)
    points = {
        estimate_differential_outcome_error(
            frame, treatment="x", outcome="y", adjustment=("z",),
            error_variance=v, differential_by="x",
            differential_coefficient=0.5, ci_bootstrap=0).point
        for v in (sigma_v, sigma_v * 2, sigma_v * 5)
    }
    assert len(points) == 1


def test_the_interval_covers_the_truth():
    frame, sigma_v = _sample(0.5)
    est = estimate_differential_outcome_error(
        frame, treatment="x", outcome="y", adjustment=("z",),
        error_variance=sigma_v, differential_by="x",
        differential_coefficient=0.5, ci_bootstrap=300, random_state=7)
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < BETA < est.ci_upper


# --- the row that owns it -----------------------------------------------------


def _run(spec, delta_for_data=0.5):
    frame, sigma_v = _sample(delta_for_data)
    filled = {"error_variance": sigma_v} | spec
    out = themis.estimate(PROGRAM, frame, ci_bootstrap=0, random_state=1,
                          measurement_error={"y": filled})
    return out["results"][0]


def test_a_declared_delta_owns_the_query_rather_than_annotating_it():
    """The measured defect, end to end.

    Before: ``numerically_solved`` at 1.3103, which is β + δ. The row that read
    the declaration priced its precision and passed the query on; nothing
    downstream knew δ existed.
    """
    result = _run({"differential_by": "x", "differential_coefficient": 0.5})
    assert result["status"] == "numerically_solved"
    estimate = result["numeric_estimate"]
    assert estimate["method"] == "differential_outcome_correction"
    assert abs(estimate["point"] - BETA) < 0.03
    assert abs(estimate["differential_outcome_error"]["naive_point"]
               - (BETA + 0.5)) < 0.03
    assert (f"design_error_tracks_the_exposure_on_y"
            in estimate["assumptions"])


def test_without_a_declared_delta_nothing_moves():
    """The classical row, byte for byte where it was.

    An answer that changed here would mean the new row had taken a query it
    has no claim on, and the price of the fix would be every outcome-error run
    that came before it.
    """
    result = _run({})
    assert result["status"] == "numerically_solved"
    assert result["numeric_estimate"]["method"] == "backdoor_linear"
    assert result["outcome_error"] is not None
    assert "differential_coefficient" not in result["outcome_error"]
    assert ("outcome_error_classical_non_differential_on_y"
            in result["outcome_error"]["assumptions"])


def test_a_declared_zero_is_the_classical_premise_and_reads_as_absent():
    result = _run({"differential_by": "x", "differential_coefficient": 0.0},
                  delta_for_data=0.0)
    assert result["numeric_estimate"]["method"] == "backdoor_linear"


def test_a_delta_nobody_could_use_leaves_by_the_refusal_door():
    """The half of the hole that survived the first fix.

    The routing property used to answer two questions with one expression:
    WAS a differential error declared, and IS the declared value usable. Merged,
    the second one's "no" came back in the first one's words — an unusable δ
    read as no δ at all, the row that owns that case never ran, and the answer
    shipped under the very premise the caller had written down to withdraw.
    A declaration nobody can act on has to leave by the refusal door, which
    means the row that owns it has to be reached.
    """
    result = _run({"differential_by": "x",
                   "differential_coefficient": "half a unit"})
    assert result.get("numeric_estimate") is None
    assert (result["estimator_failure"]["failure_type"]
            == "argument_not_a_number")


# --- the price, which is where the second defect lived ------------------------


def test_a_consistent_declaration_is_not_refused_for_not_fitting():
    """δ = 1.5 puts more variance in σ²_v than the residual holds, legitimately.

    Measured before the fix: ``needs_investigation`` with
    ``outcome_error_exceeds_residual_variance``, declared 3.689 against a
    residual of 1.366 — the whole query stopped by a gate comparing a total
    against a residual that never held it. The remainder here is σ²_f = 0.36,
    comfortably under.
    """
    result = _run({"differential_by": "x", "differential_coefficient": 1.5},
                  delta_for_data=1.5)
    assert result["status"] == "numerically_solved"
    assert result.get("estimator_failure") is None


def test_the_price_is_taken_on_what_the_residual_holds():
    """The share is σ²_f/residual, not σ²_v/residual — and at three δ it is the
    same number, because by construction the remainder is.

    That invariance is the whole claim. Priced on the total it would climb
    with δ; priced on the remainder it cannot move, because nothing about the
    unexplained variation changed.
    """
    shares = []
    for delta in (0.5, 1.5, 2.5):
        result = _run({"differential_by": "x",
                       "differential_coefficient": delta},
                      delta_for_data=delta)
        block = result["outcome_error"]
        assert abs(block["residual_error_variance"] - SIGMA_F ** 2) < 0.03
        assert block["error_variance"] > block["residual_error_variance"]
        shares.append(block["noise_share"])
    assert max(shares) - min(shares) < 1e-3
    assert abs(shares[0] - SIGMA_F ** 2 / 1.36) < 0.02


def test_the_withdrawn_premise_is_replaced_and_not_kept():
    """The ledger may not carry a sentence the caller's own declaration denies.

    ``outcome_error_classical_non_differential`` says the error moves no
    conditional mean — the premise that makes an uncorrected point defensible,
    beside a point that was corrected.
    """
    result = _run({"differential_by": "x", "differential_coefficient": 0.5})
    declared = result["outcome_error"]["assumptions"]
    assert "outcome_error_classical_non_differential_on_y" not in declared
    assert ("outcome_error_classical_once_the_exposure_is_partialled_out_on_y"
            in declared)
    on_ledger = {
        str(entry["id"]) for entry in
        result["extensions"]["assumption_ledger"]["assumptions"]
    }
    assert set(declared) <= on_ledger
    assert "design_error_tracks_the_exposure_on_y" in on_ledger


# --- what the estimator refuses -----------------------------------------------


@pytest.mark.parametrize("kwargs,failure", (
    ({"differential_by": "z"},
     Refusal.DIFFERENTIAL_AXIS_IS_AN_ADJUSTED_COVARIATE),
    ({"differential_by": "q"}, Refusal.DIFFERENTIAL_AXIS_IS_NOT_THE_EXPOSURE),
    ({"differential_by": None}, Refusal.ARGUMENT_NOT_GIVEN),
    ({"error_variance": 0.01},
     Refusal.DIFFERENTIAL_COEFFICIENT_EXCEEDS_THE_DECLARED_VARIANCE),
))
def test_the_estimator_refuses_what_it_cannot_answer(kwargs, failure):
    """Three axes and one contradiction.

    The adjusted covariate is not a smaller case of the exposure: an outcome
    error tracking a column the design conditions on shifts THAT column's
    coefficient and leaves the exposure's alone, so it is classical for this
    estimand and what the reader needs is the ordinary assessment. A real
    answer, not a scope boundary — which is why it gets its own species.
    """
    frame, sigma_v = _sample(0.5)
    call = dict(treatment="x", outcome="y", adjustment=("z",),
                error_variance=sigma_v, differential_by="x",
                differential_coefficient=0.5, ci_bootstrap=0)
    call.update(kwargs)
    with pytest.raises(EstimatorFailure) as caught:
        estimate_differential_outcome_error(frame, **call)
    assert caught.value.failure_type is failure


# --- the audits ---------------------------------------------------------------


@pytest.fixture(scope="module")
def audited():
    """One honest estimate and one honest assessment, with their blocks built
    by the producer rather than transcribed here — a hand-written block is a
    test of what the author remembered."""
    frame, sigma_v = _sample(0.5, n=8000)
    est = estimate_differential_outcome_error(
        frame, treatment="x", outcome="y", adjustment=("z",),
        error_variance=sigma_v, differential_by="x",
        differential_coefficient=0.5, ci_bootstrap=0)
    estimate = {
        "point": est.point, "method": est.method,
        "treatment": "x", "outcome": "y", "adjustment": ["z"],
        "assumptions": list(est.assumptions),
        "differential_outcome_error": _differential_outcome_error_block(est),
    }
    assessment = assess_outcome_error(
        frame, treatment="x", outcome="y", adjustment=("z",),
        error_variance=sigma_v, differential_coefficient=0.5)
    result = {
        "outcome_error": _outcome_error_block(assessment, source=None),
        "numeric_estimate": estimate,
        "extensions": {"assumption_ledger": {"assumptions": [
            {"id": a} for a in assessment.assumptions]}},
    }
    return estimate, result


def test_the_audits_accept_what_the_producer_wrote(audited):
    estimate, result = audited
    verify_differential_outcome_error_numeric(estimate)
    verify_outcome_error(result)


@pytest.mark.parametrize("label,mutate", (
    # The forgery this audit exists for. A producer that skipped the
    # subtraction ships the ordinary back-door slope, and every other number
    # on the block still agrees with it — the block would then be describing a
    # real fit of a real model, just not of the estimand the answer claims.
    ("the naive number shipped as the answer",
     lambda e: e.__setitem__(
         "point", e["differential_outcome_error"]["naive_point"])),
    # δ is on the block twice by design; two records of one number are free to
    # disagree unless something holds them together.
    ("δ shown to the reader is not the δ that was used",
     lambda e: e["differential_outcome_error"].__setitem__(
         "differential_coefficient", 0.25)),
    ("the variance split forged",
     lambda e: e["differential_outcome_error"].__setitem__(
         "nondifferential_variance", 0.01)),
    ("the axis renamed to the outcome",
     lambda e: e["differential_outcome_error"].__setitem__(
         "differential_by", "y")),
    # The premise is the whole licence for moving the point, and no data can
    # refute it. Without it on the list the ledger reads as an ordinary
    # correction, or as none, beside an answer that moved.
    ("the tracking premise never reaches the reader",
     lambda e: e.__setitem__("assumptions", [
         a for a in e["assumptions"]
         if not a.startswith("design_error_tracks")])),
))
def test_the_numeric_audit_refuses_a_forgery(audited, label, mutate):
    estimate, _ = audited
    forged = copy.deepcopy(estimate)
    mutate(forged)
    with pytest.raises(VerificationError):
        verify_differential_outcome_error_numeric(forged)


@pytest.mark.parametrize("label,mutate", (
    ("the split reported without the δ that produced it",
     lambda r: r["outcome_error"]["sufficient_statistics"].pop(
         "differential_coefficient")),
    ("the share taken on the declared total",
     lambda r: r["outcome_error"].__setitem__(
         "noise_share",
         r["outcome_error"]["error_variance"]
         / r["outcome_error"]["residual_variance"])),
    ("the tracking variance forged",
     lambda r: r["outcome_error"].__setitem__(
         "exposure_tracking_variance", 0.02)),
    ("the withdrawn premise put back on the ledger",
     lambda r: r["outcome_error"].__setitem__("assumptions", [
         "outcome_error_classical_non_differential_on_y",
         "outcome_error_variance_known_and_fixed_on_y"])),
    ("the split fields dropped while the δ stays",
     lambda r: r["outcome_error"].pop("residual_error_variance")),
))
def test_the_assessment_audit_refuses_a_forgery(audited, label, mutate):
    _, result = audited
    forged = copy.deepcopy(result)
    mutate(forged)
    with pytest.raises(VerificationError):
        verify_outcome_error(forged)
