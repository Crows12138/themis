"""A diagnostic verdict is three things, and only one of them was audited.

It is a number measured off a fit, a LINE this system drew, and the
conclusion the two make. #524 closed the number: a share is a count over a
count, a range inside its band is a count of zero outside it. The other two
were each recorded exactly once, by the producer, and nothing compared them
with anything.

Measured end to end before any of this was written: an answer stating that
1453 of 4000 units fell outside the overlap band passed the public door with
the warning that says so **deleted from the report entirely**. The band's
floor could be moved to 0.0, the saturation threshold from 0.10 to 0.90, the
clip's floor from 0.01 to 0.005 — all accepted. One of the four verdicts this
layer makes did refuse, because the assumption ledger re-reads its positivity
conclusion off the block. That asymmetry is the defect: whether a conclusion
could be read back from its evidence was being decided one conclusion at a
time.

Two kinds of line and two ways to hold one, and the difference is who draws
it. The band and the threshold are the system's, restated here and pinned to
the producer's constants by a test. The clip's floor is the CALLER's — the
estimator records whether they named it — so holding it to a constant would
refuse a run for having been asked what it was asked. That one is held to
the ledger, which carries the same floor and the same count as a premise,
and which nothing had ever compared with the block beside it.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.estimation import dispatch
from themis.verifier.errors import VerificationError
from themis.verifier.fitted_diagnostic_rules import (
    _DIAGNOSTICS, verify_fitted_diagnostics,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: The shapes that carry a fitted diagnostic at all.
DIAGNOSED = ("aipw", "tmle", "ipw_stabilized", "backdoor_logistic")


def _pair(method: str):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _door(program, result, match: str) -> None:
    """The door refuses, and this rule is why.

    Both, for the reason the correction-frame tests state: what a caller
    gets is the refusal, and what this test is about is which question
    produced it.
    """
    with pytest.raises(VerificationError):
        themis.verify(program, result)
    with pytest.raises(VerificationError, match=match):
        verify_fitted_diagnostics(result)


@pytest.mark.parametrize("method", DIAGNOSED)
def test_the_answer_this_run_really_gives_is_accepted(method):
    program, result = _pair(method)
    themis.verify(program, result)
    assert "fitted_overlap" in result["numeric_estimate"]


# ------------------------------------------------ the line, and who drew it


def test_the_lines_here_are_the_lines_the_producer_draws():
    """Two copies of one constant, pinned.

    The verifier may not import the producer — a checker that read the
    number it is checking agrees by construction and holds nothing — so the
    lines are restated, and restating is only safe while something says the
    two are the same. This is that something: moving a line becomes a change
    somebody declares in a diff rather than one that happens.
    """
    assert _DIAGNOSTICS["fitted_overlap"][0] == {
        "band_lower": dispatch.PROPENSITY_OVERLAP_LOWER,
        "band_upper": dispatch.PROPENSITY_OVERLAP_UPPER,
        "threshold": dispatch.PROPENSITY_OVERLAP_VIOLATION_FRACTION,
    }
    assert _DIAGNOSTICS["outcome_saturation"][0] == {
        "band_lower": dispatch.OUTCOME_SATURATION_LOWER,
        "band_upper": dispatch.OUTCOME_SATURATION_UPPER,
        "threshold": dispatch.OUTCOME_SATURATION_FRACTION,
    }


@pytest.mark.parametrize("block,field,forged", [
    ("fitted_overlap", "band_lower", 0.0),
    ("fitted_overlap", "band_upper", 0.999),
    ("fitted_overlap", "threshold", 0.9),
    ("outcome_saturation", "band_lower", 0.0),
    ("outcome_saturation", "band_upper", 0.999),
    ("outcome_saturation", "threshold", 0.9),
])
def test_a_diagnostic_cannot_move_the_line_it_is_judged_against(
        block, field, forged):
    program, result = _pair("aipw")
    result["numeric_estimate"][block][field] = forged
    _door(program, result, "the line this system draws")


def test_a_block_that_judges_against_an_unregistered_line_is_refused():
    """Refused rather than skipped, and asked at the rule because a block
    the schema does not declare is turned away one gate earlier.

    A line nobody registered is a line nobody checked, and at a door those
    two are the same silence.
    """
    with pytest.raises(VerificationError, match="no line is registered"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "some_new_diagnostic": {"threshold": 0.42},
        }})


@pytest.mark.parametrize("estimate", [
    {"curve": [{"threshold": 0.42}]},
    {"threshold": 0.42},
    {"outer": {"inner": {"band_lower": 0.42}}},
])
def test_an_unregistered_line_is_reached_wherever_it_sits(estimate):
    """"At any depth" is the claim, so it is asked at each of them.

    A row of a series is where the first version could not look: it walked
    from a dict to its children, so a scalar sitting directly on a list
    element was never examined. No shape carries one, which is why the
    CLAIM had to be repaired rather than the coverage — an unmeasured blind
    spot in a rule about coverage is the thing this repository keeps
    finding.
    """
    with pytest.raises(VerificationError, match="no line is registered"):
        verify_fitted_diagnostics({"numeric_estimate": estimate})


def test_a_registered_block_is_judged_wherever_it_sits_too():
    """The same walk, from the other side: recognition follows the block's
    own name, not the level it was found on."""
    with pytest.raises(VerificationError, match="the line this system draws"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "outer": {"fitted_overlap": {"threshold": 0.9}},
        }})


# ------------------------------------- the conclusion, read back from the number


def test_a_run_whose_overlap_failed_cannot_be_shown_as_a_clean_one():
    """The one measured end to end. Nothing about the answer changes — the
    diagnostic still says 1453 of 4000 — and the reader is simply not told.
    """
    program, result = _pair("aipw")
    report = result["data_gap_report"]
    assert any(g["kind"] == "propensity_overlap_violation"
               for g in report["gaps"])
    report["gaps"] = [g for g in report["gaps"]
                      if g["kind"] != "propensity_overlap_violation"]
    _door(program, result, "a reader is shown a clean run")


def test_a_saturated_outcome_model_cannot_be_shown_as_a_clean_one():
    """The channel no snapshot exercises, forged into the state it warns in.

    Every number moved together so the arithmetic above still passes: the
    range now reaches below the band, the count matches the share, and the
    share crosses the line. What is missing is only the warning.
    """
    program, result = _pair("aipw")
    block = result["numeric_estimate"]["outcome_saturation"]
    block["p_min"] = 0.005
    block["n_outside"] = 500
    block["share_outside"] = 500 / block["n_total"]
    _door(program, result, "carries no 'outcome_model_quasi_separation'")


def test_a_warning_cannot_stand_over_a_diagnostic_that_found_nothing():
    """The other direction. It costs a reader a number they should have
    trusted, and it is the direction a forger reaches for when a warning is
    the excuse for a weaker claim."""
    program, result = _pair("backdoor_logistic")
    assert result["numeric_estimate"]["fitted_overlap"]["share_outside"] == 0.0
    with pytest.raises(VerificationError, match="that would occasion it"):
        verify_fitted_diagnostics(dict(
            result,
            data_gap_report={"gaps": [
                {"kind": "propensity_overlap_violation"}]}))


# ----------------------------------------------------- the count of thin strata


def test_a_stratum_table_cannot_hold_more_supported_cells_than_cells():
    program, result = _pair("backdoor_logistic")
    result["numeric_estimate"]["stratum_support"]["supported"] = 9
    _door(program, result, "strata holding both arms")


def test_a_share_of_the_sample_sits_in_the_strata_that_are_short():
    """One fact said three ways: how many cells, how many held both arms,
    and what share of the sample sat in the ones that did not. A cell with a
    single arm holds at least one unit, so two of the three decide the
    third's sign."""
    program, result = _pair("backdoor_logistic")
    result["numeric_estimate"]["stratum_support"]["extrapolated_share"] = 0.4
    _door(program, result, "holds at least one unit")


def test_a_stratum_the_formula_needs_and_does_not_have_is_disclosed():
    """Asked at the rule: a snapshot where this fires would be a snapshot of
    a run whose overlap failed by the counting witness, and no shape here is
    one. The claim is the same either way — a formula summing over a cell
    the data never filled is extrapolation, and a reader who is not told
    reads it as measurement."""
    with pytest.raises(VerificationError, match="the report says nothing"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "stratum_support": {"cells": 4, "supported": 3,
                                "extrapolated_share": 0.2},
        }})


# --------------------------------------------- the clip, and the premise for it


def test_the_clip_a_reader_reads_and_the_clip_the_ledger_asks_for():
    program, result = _pair("aipw")
    result["numeric_estimate"]["propensity_summary"]["floor"] = 0.2
    _door(program, result, "the ledger's premise is about a clip at")


def test_the_count_clipped_is_the_count_the_premise_names():
    program, result = _pair("aipw")
    result["numeric_estimate"]["propensity_summary"]["n_trimmed"] = 625
    _door(program, result, "the ledger's premise is about")


def test_a_clip_nobody_is_asked_to_accept_is_refused():
    program, result = _pair("aipw")
    estimate = result["numeric_estimate"]
    estimate["assumptions"] = [a for a in estimate["assumptions"]
                               if not a.startswith("propensity_clipped")]
    _door(program, result, "no premise on the ledger says so")


def test_a_premise_about_a_clip_that_did_not_happen_is_refused():
    program, result = _pair("backdoor_logistic")
    assert "propensity_summary" not in result["numeric_estimate"]
    with pytest.raises(VerificationError, match="no unit was clipped"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "assumptions": ["propensity_clipped_to_floor_0.01_on_5"],
            "propensity_summary": {"floor": 0.01, "n_trimmed": 0},
        }})


def test_a_caller_who_asked_for_a_different_clip_is_not_refused_for_it():
    """The line the caller draws, and why it is not held to a constant.

    A floor of 0.2 is not this system's number and never was — it is what
    somebody asked for — so what makes it honest is the ledger saying the
    same thing, not the verifier recognising the value. A rule that pinned
    the floor would refuse this run for being what it was asked to be.
    """
    verify_fitted_diagnostics({"numeric_estimate": {
        "assumptions": ["propensity_clipped_to_floor_0.2_on_31"],
        "propensity_summary": {"floor": 0.2, "n_trimmed": 31},
    }})
