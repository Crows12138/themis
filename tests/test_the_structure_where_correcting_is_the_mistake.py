# -*- coding: utf-8 -*-
"""Berkson error: the one declared variance that must not be corrected for.

The deferral this overturns lumped Berkson error in with differential
error as "the two structures the moment correction does not cover". They
are not the same kind of gap. A differential error needs an estimator this
package did not have; a Berkson error needs *no estimator at all* — under
``X* = W + U`` with U independent of the RECORDED nominal value,
``E[X*|W,Z] = W`` and the ordinary back-door slope already IS the causal
slope. What the gap cost was therefore not a missing number but a wrong
one: the same declared σ²_u, read as classical, divides a correct answer
through by a reliability ratio. That is measured here rather than asserted.

Three groups for three claims:

- the point needs no correcting, and correcting it is what breaks it;
- the price is real, re-derivable, and refutable — β̂²σ²_u either fits
  under the unexplained variation or the premises do not hold;
- the declaration routes, and nothing about the recorded column does. No
  property of one sample separates the two structures, so which one holds
  arrives as a word, is what keeps the correction rows off, and reaches
  the ledger where a reader can disagree with it.
"""
from __future__ import annotations

import ast
import copy
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.berkson import BerksonAssessment, assess_berkson_error
from themis.estimation.dispatch import _berkson_block
from themis.kernel import verify_berkson_error
from themis.output.analysis_report import build_analysis_report
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.berkson_rules import verify_berkson_error as audit
from themis.verifier.errors import VerificationError

BETA_X = 0.8
SIGMA2_U = 0.5
#: Var(ε) in the structural model, so the residual around the OBSERVED
#: design is 1.0 + β²σ²_u = 1.32 and the inflation factor is √1.32.
SIGMA2_EPS = 1.0

_STRUCTURE = "berkson_error_on_w"
_LINEARITY = "berkson_identity_rests_on_a_linear_outcome_in_the_true_values"
_VARIANCE = "berkson_scatter_variance_known_and_fixed_on_w"
OWED = (_STRUCTURE, _LINEARITY, _VARIANCE)


# --- data ---------------------------------------------------------------------


def _frame(n=60_000, seed=0, beta=BETA_X, sigma2_u=SIGMA2_U):
    """W is the NOMINAL value and the truth scatters around it.

    Note the direction, which is the whole of what makes this Berkson: the
    noise is drawn AFTER w and added to it, so U is independent of what was
    recorded. A classical frame draws x first and adds noise to make w, and
    the two frames are indistinguishable column by column.
    """
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    w = 0.6 * z + rng.normal(0, 1, n)
    x_true = w + rng.normal(0, np.sqrt(sigma2_u), n)
    y = (1.0 + beta * x_true + 0.4 * z
         + rng.normal(0, np.sqrt(SIGMA2_EPS), n))
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _classical_frame(n=60_000, seed=0, beta=BETA_X, sigma2_u=SIGMA2_U):
    """The other structure, same marginals to the eye: x first, then w."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x_true = 0.6 * z + rng.normal(0, 1, n)
    y = (1.0 + beta * x_true + 0.4 * z
         + rng.normal(0, np.sqrt(SIGMA2_EPS), n))
    w = x_true + rng.normal(0, np.sqrt(sigma2_u), n)
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _slope(df, treatment="w", outcome="y", adjustment=("z",)):
    """The ordinary back-door slope — what the answer beside the block is."""
    design = np.column_stack(
        [np.ones(len(df))] + [df[c].to_numpy(float)
                              for c in (treatment, *adjustment)])
    y = df[outcome].to_numpy(float)
    return float(np.linalg.lstsq(design, y, rcond=None)[0][1])


def _assess(df=None, **kwargs):
    df = _frame() if df is None else df
    kwargs.setdefault("error_variance", SIGMA2_U)
    kwargs.setdefault("treatment_coefficient", _slope(df))
    return assess_berkson_error(
        df, treatment="w", outcome="y", adjustment=("z",), **kwargs)


def _envelope(assessment: BerksonAssessment) -> dict:
    """A result carrying the block, the answer it rides beside, and the
    ledger its premises are owed to — built through the producer's own
    block so the audit reads what dispatch writes."""
    return {
        "numeric_estimate": {
            "method": "backdoor_linear",
            "point": assessment.treatment_coefficient,
            "ci_level": 0.95,
            "assumptions": [],
            "sample_size": assessment.sample_size,
            "data_hash": assessment.data_hash,
            "data_columns": list(assessment.data_columns),
        },
        "berkson_error": _berkson_block(assessment),
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in assessment.assumptions]}},
    }


@pytest.fixture(scope="module")
def honest() -> dict:
    """One accepted artifact, so each forgery below is it with exactly one
    thing changed."""
    return _envelope(_assess())


# --- the point needs no correcting, and correcting it is the mistake ----------


def test_the_uncorrected_back_door_slope_is_already_the_causal_one():
    """The identity, measured. E[X*|W,Z] = W carries the coefficients over,
    so the ordinary slope of Y on (W, Z) estimates βx with no correction —
    which is the claim the whole block rides on."""
    assert _slope(_frame()) == pytest.approx(BETA_X, abs=0.01)


def test_reading_the_same_variance_as_classical_moves_a_right_answer():
    """What the deferral cost, as a number rather than a worry.

    Same frame, same declared σ²_u, one word different in the spec — and
    the corrected answer is nowhere near the truth the uncorrected one was
    already on. This is why the correction rows are guarded off the word
    instead of running whenever a variance is declared.
    """
    df = _frame()
    berkson = _run(df, {"w": {"structure": "berkson",
                             "error_variance": SIGMA2_U}})
    classical = _run(df, {"w": {"error_variance": SIGMA2_U}})

    assert berkson["numeric_estimate"]["method"] == "backdoor_linear"
    assert classical["numeric_estimate"]["method"] == "regression_calibration"

    right = berkson["numeric_estimate"]["point"]
    wrong = classical["numeric_estimate"]["point"]
    assert right == pytest.approx(BETA_X, abs=0.01)
    # Not "somewhat worse". The correction reads Var(W|Z)=1 as Var(X*|Z)+σ²_u
    # and so believes the reliability is (1−0.5)/1 = ½ — it divides a number
    # that needed nothing done to it by a half.
    assert wrong == pytest.approx(BETA_X * 2.0, rel=0.05)
    assert abs(wrong - BETA_X) > 20 * abs(right - BETA_X)


def test_the_same_correction_is_right_on_the_other_structure():
    """The mirror, so the test above is about the structure and not about
    regression calibration being broken: on a CLASSICAL frame, with the
    same columns and the same σ²_u, the correction is what recovers βx and
    the uncorrected slope is the attenuated one."""
    df = _classical_frame()
    corrected = _run(df, {"w": {"error_variance": SIGMA2_U}})
    assert corrected["numeric_estimate"]["point"] == pytest.approx(
        BETA_X, abs=0.02)
    assert _slope(df) == pytest.approx(BETA_X * 2 / 3, rel=0.05)


# --- the price ----------------------------------------------------------------


def test_the_scatter_enters_the_residual_scaled_by_the_answer():
    """Var(Y|W,Z) = Var(Y|X*,Z) + βx²σ²_u, every term against its theory."""
    a = _assess()
    assert a.scattered_variance == pytest.approx(
        BETA_X ** 2 * SIGMA2_U, rel=0.02)
    assert a.residual_variance == pytest.approx(
        SIGMA2_EPS + BETA_X ** 2 * SIGMA2_U, rel=0.02)
    assert a.signal_variance == pytest.approx(SIGMA2_EPS, rel=0.02)
    assert a.noise_share == pytest.approx(
        a.scattered_variance / a.residual_variance)
    assert a.se_inflation == pytest.approx(
        np.sqrt(a.residual_variance / a.signal_variance))


def test_a_larger_effect_makes_the_same_error_more_expensive():
    """The one thing that separates this price from the outcome channel's:
    there the declared variance enters the residual unscaled, here it is
    scaled by β̂², so the price cannot exist before the answer does."""
    small = _assess(_frame(beta=0.2))
    large = _assess(_frame(beta=1.6))
    assert small.error_variance == large.error_variance
    assert large.scattered_variance > 40 * small.scattered_variance
    assert large.se_inflation > small.se_inflation


def test_a_scatter_that_does_not_fit_under_the_residual_is_refused():
    """β̂²σ²_u ≥ Var(Y|W,Z) says one of the declared variance, the
    linearity, or the independence of U from W is false — and the last is
    the premise that made the point safe. A negative signal variance
    reported as a price would put a number on a split that does not
    exist."""
    with pytest.raises(EstimatorFailure) as exc:
        _assess(error_variance=40.0)
    assert exc.value.failure_type is (
        Refusal.BERKSON_SCATTER_EXCEEDS_RESIDUAL_VARIANCE)


@pytest.mark.parametrize("given", [None, 0.0, float("nan"), "0.4", True])
def test_a_price_with_no_scale_is_not_a_price(given):
    """Zero is refused with the rest and not as an edge case: at β̂ = 0 the
    scatter costs exactly nothing, and a nil price reported as a price
    reads as "measured, and small"."""
    with pytest.raises(EstimatorFailure):
        _assess(treatment_coefficient=given)


def test_a_coefficient_that_is_not_the_design_slope_is_refused():
    """The identity is about ONE functional. A block riding beside some
    other back-door number would tell its reader that number needed no
    correcting, which is a claim nothing here has checked."""
    df = _frame()
    with pytest.raises(EstimatorFailure) as exc:
        _assess(df, treatment_coefficient=_slope(df) + 0.05)
    assert exc.value.failure_type is (
        Refusal.BERKSON_ANSWER_IS_NOT_THE_DESIGN_SLOPE)


def test_a_near_discrete_exposure_is_a_different_object():
    """A truth that scatters over a handful of levels is misclassification,
    and the arithmetic here is about a variance."""
    df = _frame(n=4000)
    df["w"] = np.round(df["w"]).clip(-2, 2)
    with pytest.raises(EstimatorFailure) as exc:
        _assess(df, treatment_coefficient=_slope(df))
    assert exc.value.failure_type is Refusal.EXPOSURE_NOT_CONTINUOUS


@pytest.mark.parametrize("given", [None, 0.0, -1.0, float("inf"), "0.5"])
def test_an_unusable_scatter_variance_is_refused(given):
    with pytest.raises(EstimatorFailure):
        _assess(error_variance=given)


# --- the audit ----------------------------------------------------------------


def test_an_honest_block_is_accepted(honest):
    audit(honest)


def test_a_result_with_no_block_is_not_a_finding():
    audit({"numeric_estimate": {"point": 1.0}})


@pytest.mark.parametrize("path, value", [
    (("berkson_error", "scattered_variance"), 0.1),
    (("berkson_error", "residual_variance"), 1.9),
    (("berkson_error", "signal_variance"), 0.9),
    (("berkson_error", "noise_share"), 0.1),
    (("berkson_error", "se_inflation"), 1.02),
    (("berkson_error", "treatment_coefficient"), 0.5),
    (("berkson_error", "sufficient_statistics", "var_y"), 3.0),
    (("berkson_error", "sufficient_statistics", "error_variance"), 0.2),
    (("berkson_error", "sufficient_statistics", "treatment_coefficient"), 0.5),
])
def test_a_scalar_that_does_not_follow_from_the_moments_is_rejected(
        honest, path, value):
    """Every reported number is a closed-form function of the recorded
    moments, so moving any one of them alone contradicts the rest."""
    forged = copy.deepcopy(honest)
    target = forged
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(VerificationError):
        audit(forged)


def test_a_price_scaled_by_a_coefficient_the_answer_never_reports(honest):
    """The one forgery that leaves every scalar internally consistent: move
    β̂ and everything derived from it together, and the block recomputes
    perfectly while pricing an effect the reader was never given."""
    forged = copy.deepcopy(honest)
    block = forged["berkson_error"]
    beta = block["treatment_coefficient"] * 1.4
    scattered = beta ** 2 * block["error_variance"]
    signal = block["residual_variance"] - scattered
    block["treatment_coefficient"] = beta
    block["sufficient_statistics"]["treatment_coefficient"] = beta
    block["scattered_variance"] = scattered
    block["signal_variance"] = signal
    block["noise_share"] = scattered / block["residual_variance"]
    block["se_inflation"] = float(
        np.sqrt(block["residual_variance"] / signal))
    with pytest.raises(VerificationError, match="rides beside"):
        audit(forged)


def test_a_design_that_does_not_lead_with_the_exposure(honest):
    """The block's arithmetic is about the exposure's own slope, which is
    the design's first coefficient. A design that opens with a covariate
    prices the wrong column while every equation still solves."""
    forged = copy.deepcopy(honest)
    block = forged["berkson_error"]
    block["exposure"] = "z"
    with pytest.raises(VerificationError):
        audit(forged)


def test_a_design_the_statistics_do_not_describe(honest):
    forged = copy.deepcopy(honest)
    forged["berkson_error"]["design_vars"] = ["w", "q"]
    with pytest.raises(VerificationError, match="different designs"):
        audit(forged)


def test_coefficients_that_do_not_solve_the_normal_equations(honest):
    """Unlike the outcome channel's, every row here is checked — nothing in
    this block is sourced from outside the design, because the whole claim
    is that the ORDINARY slope is already the causal one."""
    forged = copy.deepcopy(honest)
    stats = forged["berkson_error"]["sufficient_statistics"]
    stats["design_coefficients"] = [c + 0.01
                                    for c in stats["design_coefficients"]]
    with pytest.raises(VerificationError, match="normal equation"):
        audit(forged)


@pytest.mark.parametrize("dropped", OWED)
def test_a_premise_that_stops_at_the_block_reaches_no_reader(honest, dropped):
    """The three premises are owed separately because they fail
    separately: the structure and the linearity each hold the POINT up, the
    variance only the width. None is inferable from the number.

    Matched on the word every refusal here shares rather than on one
    module's sentence: the variance is owed by the module that owns the
    question of WHICH variance premise this run owes, and what this test
    asserts is that a premise reaching no ledger is refused — not which of
    the two auditors said so.
    """
    forged = copy.deepcopy(honest)
    ledger = forged["extensions"]["assumption_ledger"]
    ledger["assumptions"] = [e for e in ledger["assumptions"]
                             if e["id"] != dropped]
    with pytest.raises(VerificationError, match="ledger"):
        audit(forged)


def test_a_block_with_no_ledger_at_all_is_rejected(honest):
    forged = copy.deepcopy(honest)
    forged["extensions"] = {}
    with pytest.raises(VerificationError, match="assumption ledger"):
        audit(forged)


def test_the_audit_does_not_import_the_estimator():
    """The independence pin: a price re-derived through the arithmetic its
    producer wrote is not an independent audit. Read off the import
    statements rather than the file's text, so the module can go on SAYING
    what it must not do."""
    import themis.verifier.berkson_rules as rules
    tree = ast.parse(pathlib.Path(rules.__file__).read_text(encoding="utf-8"))
    reached = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            reached.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            reached.add("." * node.level + (node.module or ""))
    assert not any("estimation" in m for m in reached), sorted(reached)


# --- the declaration routes, and nothing about the column does ----------------


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "w",
             "measurement": "assigned nominal dose; the truth scatters"},
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


def _run(df: pd.DataFrame, spec: dict) -> dict:
    out = themis.estimate(_program(), df, ci_bootstrap=0,
                          measurement_error=spec)
    return out["results"][0]


@pytest.fixture(scope="module")
def declared() -> dict:
    return _run(_frame(), {"w": {"structure": "berkson",
                                 "error_variance": SIGMA2_U,
                                 "source": "dosimetry substudy"}})


def test_a_declared_berkson_structure_reaches_the_envelope(declared):
    block = declared["berkson_error"]
    assert block["exposure"] == "w"
    assert block["design_vars"] == ["w", "z"]
    assert block["source"] == "dosimetry substudy"
    assert block["treatment_coefficient"] == pytest.approx(
        declared["numeric_estimate"]["point"])
    verify_berkson_error(declared)


def test_the_declaration_reaches_the_ledger(declared):
    ledger = declared["extensions"]["assumption_ledger"]["assumptions"]
    by_id = {e["id"]: e for e in ledger}
    assert set(OWED) <= set(by_id)
    # The structure and the linearity hold the POINT up; the variance only
    # the width. The severities have to say so, or the reader is asked to
    # weigh three premises that look alike.
    assert by_id[_STRUCTURE]["layer"] == "identification"
    assert by_id[_LINEARITY]["layer"] == "identification"
    assert by_id[_VARIANCE]["layer"] == "confidence"
    assert by_id[_STRUCTURE]["severity"] == by_id[_LINEARITY]["severity"]
    assert by_id[_VARIANCE]["severity"] != by_id[_STRUCTURE]["severity"]


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_report_leads_with_what_was_not_done(declared, lang):
    """A reader who declared a variance and sees no correction reads an
    omission. The line has to say the point was left alone on purpose
    before it says what the width cost."""
    text = build_analysis_report(declared, lang=lang)
    said = [ln for ln in text.splitlines() if "Berkson" in ln]
    assert said, text
    row = said[0]
    factor = f"{declared['berkson_error']['se_inflation']:.2f}"
    assert factor in row
    for token in (("没有", "去偏") if lang == "zh"
                  else ("not", "de-attenuated")):
        assert token in row


@pytest.mark.parametrize("spec, method", [
    # The word is the whole of what routes. Same columns, same variance.
    ({"w": {"structure": "berkson", "error_variance": SIGMA2_U}},
     "backdoor_linear"),
    ({"w": {"structure": "classical", "error_variance": SIGMA2_U}},
     "regression_calibration"),
    ({"w": {"error_variance": SIGMA2_U}}, "regression_calibration"),
    # A declared nonlinear outcome model would reach simulation-extrapolation
    # — but not under a structure whose whole finding is that there is
    # nothing to extrapolate back to.
    ({"w": {"structure": "berkson", "error_variance": SIGMA2_U,
            "outcome_model": "logistic"}}, "backdoor_linear"),
])
def test_the_structure_word_decides_which_row_answers(spec, method):
    assert _run(_frame(), spec)["numeric_estimate"]["method"] == method


def test_a_structure_nobody_recognises_keeps_the_corrections_off():
    """The unsafe direction is the silent one. A word this package does not
    know is exactly the case where correcting is unjustified — the premise a
    correction rests on is the one in doubt — so the correction rows stay
    off, and the declaration is named rather than dropped onto a result that
    looks in every other respect like one where nothing was declared."""
    result = _run(_frame(), {"w": {"structure": "berkston",
                                   "error_variance": SIGMA2_U}})
    assert result["numeric_estimate"]["method"] == "backdoor_linear"
    assert "berkson_error" not in result
    failure = result["estimator_failure"]
    assert failure["estimator"] == "berkson_error"
    assert failure["failure_type"] == "malformed_argument"
    assert failure["details"]["given"] == "berkston"
    assert "berkson" in failure["details"]["shape"]


def test_a_query_answered_off_the_back_door_is_told_the_price_was_not_taken():
    """The identity that saves the point is about a conditional mean of Y
    given the recorded exposure, and that is what a back-door answer is. On
    any other route this row has nothing it can honestly say — and saying
    nothing is what it must not do, because the declaration would then reach
    no reader at all."""
    program = _program()
    program["statements"].insert(
        3, {"kind": "bidirected", "left": _atom("w"), "right": _atom("y")})
    out = themis.estimate(program, _frame(n=4000), ci_bootstrap=0,
                          measurement_error={"w": {
                              "structure": "berkson",
                              "error_variance": SIGMA2_U}})
    result = out["results"][0]
    assert "berkson_error" not in result
    failure = result["estimator_failure"]
    assert failure["estimator"] == "berkson_error"
    assert failure["failure_type"] in {
        "requires_backdoor_identification", "no_identifying_design"}
