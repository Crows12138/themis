"""The overlap diagnostic decided nothing, and nothing decided it.

``fitted_overlap`` is what a reader consults to answer the question that
comes before "how big is the effect": is this data able to answer it at
all. The assumption ledger reads its positivity verdict off this block, and
reads it deliberately — re-computing the outcome from the estimate's own
numbers rather than believing the verdict field, because a verdict is the
one thing a producer could fill in with a sentence and no evidence.

**That re-reading rested on ground nobody had checked.** The block arrived
as a summary: a share, a range, a band. The counts behind the share — how
many units fell outside, out of how many — were computed at the estimator,
spoken to the reader inside the gap's own sentence, and dropped before the
envelope. So the ledger's re-read was one comparison against one figure,
and any edit that left the figure on the same side of the threshold moved
nothing it could see. Measured through the public door, before this file
existed: a fitted overlap of 36.3% shown as 90%, and shown as 19%, each
accepted — three different pictures of how badly this data fails, all of
them fine.

What closes it is not a second fit; the verifier has no data. It is the
arithmetic a fitted range obeys whatever model produced it: a share is a
count over a count, a range lying inside its band is a count of zero
outside it, a diagnostic is about the units the estimate is about, and the
propensity range this answer discloses twice is one range.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier import verify_fitted_diagnostics
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: A weighted estimate whose overlap genuinely fails — 36.3% of the fitted
#: propensities outside [0.05, 0.95] — so the ledger on it says the data
#: refuted positivity, and the numbers this file moves are the numbers that
#: sentence is read off.
THIN = SHAPES["aipw"]

#: One whose overlap is clean, so the identities can be pushed from the
#: other side: a count of zero is as checkable as a count of 1453.
CLEAN = SHAPES["backdoor_logistic"]

_CARRIES = sorted(
    method for method, pair in SHAPES.items()
    if any(k in (pair["result"].get("numeric_estimate") or {})
           for k in ("fitted_overlap", "outcome_saturation",
                     "propensity_summary")))


def _bend(pair, path, value):
    bad = copy.deepcopy(pair["result"])
    node = bad["numeric_estimate"]
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return bad


def _at(pair, *path):
    node = pair["result"]["numeric_estimate"]
    for step in path:
        node = node[step]
    return node


# ============================================================ honest first


@pytest.mark.parametrize("method", _CARRIES)
def test_the_honest_answers_pass(method):
    """First, because a forgery refused by a broken producer proves
    nothing — and because every identity below was measured against these
    before it was asserted."""
    themis.verify(SHAPES[method]["program"], SHAPES[method]["result"])


def test_the_diagnostics_reach_more_than_one_shape():
    """A sweep over an empty list satisfies every parametrized test above
    in silence."""
    assert len(_CARRIES) >= 4, _CARRIES


# ============================================== the share, and moving it


@pytest.mark.parametrize("shown", [0.9, 0.191_625, 0.0])
def test_how_badly_this_data_fails_can_no_longer_be_any_number(shown):
    """Each of these passed the public door.

    The first two sit on the same side of the threshold as the truth, which
    is why the ledger's re-read never moved: it asks whether the share
    exceeds the threshold, and a lie that keeps the answer to that question
    is a lie about a quantity nobody else reads. The third crosses it, and
    was caught for a different reason — the ledger's own verdict field then
    disagreed — which is a rule about the ledger, not about this number.
    """
    with pytest.raises(VerificationError):
        themis.verify(THIN["program"],
                      _bend(THIN, ("fitted_overlap", "share_outside"), shown))


def test_a_clean_share_still_has_to_move_the_range_the_reader_sees():
    """The consistent forgery, which is the one that matters.

    Editing the share alone is now caught by the counts. So edit the counts
    to match — a clean share of exactly zero, honestly divided — and the
    positivity verdict flips from refuted to not-refuted. What refuses it is
    the range: no unit outside the band means every fitted propensity lies
    inside it, and this one runs from 0.000002 to 0.99998. The forger has to
    say so twice, and the second place is printed to the reader.
    """
    bad = copy.deepcopy(THIN["result"])
    block = bad["numeric_estimate"]["fitted_overlap"]
    block["n_outside"], block["share_outside"] = 0, 0.0
    assert block["p_min"] < block["band_lower"]
    with pytest.raises(VerificationError, match="reaches outside"):
        themis.verify(THIN["program"], bad)


def test_a_count_outside_a_band_nothing_reached_outside_of():
    """The same identity from the other side. This answer's fitted
    propensities all lie well inside the band, so any count of units beyond
    it is a count of nobody."""
    bad = copy.deepcopy(CLEAN["result"])
    block = bad["numeric_estimate"]["fitted_overlap"]
    block["n_outside"] = 5
    block["share_outside"] = 5 / block["n_total"]
    with pytest.raises(VerificationError, match="lies within"):
        themis.verify(CLEAN["program"], bad)


def test_the_share_and_the_counts_it_is_a_share_of_are_one_fact():
    """Counts moved without the share. Sums and counts on the envelope and
    the division done here is what makes this an identity rather than a
    second copy of the quotient."""
    bad = copy.deepcopy(THIN["result"])
    bad["numeric_estimate"]["fitted_overlap"]["n_outside"] -= 3
    with pytest.raises(VerificationError, match="out of"):
        themis.verify(THIN["program"], bad)


def test_more_units_outside_the_band_than_were_fitted_at_all():
    total = _at(THIN, "fitted_overlap", "n_total")
    bad = copy.deepcopy(THIN["result"])
    block = bad["numeric_estimate"]["fitted_overlap"]
    block["n_outside"], block["share_outside"] = total + 1, 1.0
    with pytest.raises(VerificationError, match="outside the band"):
        themis.verify(THIN["program"], bad)


def test_a_diagnostic_is_about_the_units_the_estimate_is_about():
    """A share can also be shrunk by growing what it is out of. The
    diagnostic is evidence about THIS answer only while it was fitted on the
    units this answer was computed on."""
    bad = copy.deepcopy(THIN["result"])
    block = bad["numeric_estimate"]["fitted_overlap"]
    block["n_total"] += 4000
    block["share_outside"] = block["n_outside"] / block["n_total"]
    with pytest.raises(VerificationError, match="where the estimate"):
        themis.verify(THIN["program"], bad)


def test_the_saturation_diagnostic_is_asked_the_same_question():
    """The second block the same writer produces, on the outcome model
    rather than the treatment model. One writer, so one set of identities —
    and a test each, because "the same writer" is a fact about today."""
    bad = copy.deepcopy(THIN["result"])
    block = bad["numeric_estimate"]["outcome_saturation"]
    assert block["n_outside"] == 0
    block["n_outside"], block["share_outside"] = 40, 40 / block["n_total"]
    with pytest.raises(VerificationError, match="lies within"):
        themis.verify(THIN["program"], bad)


# ================================== what the estimator DID about it


def test_a_clip_count_and_the_range_it_was_clipped_from():
    """``n_trimmed`` is how many propensities were Winsorized to
    ``[floor, 1-floor]``, and the report prints "none were clipped" when it
    is zero. That sentence is decided by the range: a propensity of
    0.000002 against a floor of 0.01 was clipped, whatever the count says.
    """
    bad = copy.deepcopy(THIN["result"])
    summary = bad["numeric_estimate"]["propensity_summary"]
    assert summary["raw_min"] < summary["floor"] and summary["n_trimmed"]
    summary["n_trimmed"] = 0
    with pytest.raises(VerificationError, match="crosses the floor"):
        themis.verify(THIN["program"], bad)


def test_a_clip_of_units_that_were_never_outside_the_floor():
    """And the other direction, which is the one that reads as candour: a
    run reporting units it had to clip when nothing needed clipping."""
    bad = copy.deepcopy(THIN["result"])
    bad["numeric_estimate"].pop("fitted_overlap")
    summary = bad["numeric_estimate"]["propensity_summary"]
    summary["raw_min"], summary["raw_max"] = 0.2, 0.8
    with pytest.raises(VerificationError, match="reported clipped"):
        verify_fitted_diagnostics(bad)


def test_the_one_range_this_answer_discloses_twice():
    """The propensity range appears in two blocks and, in the report, on two
    lines one under the other. They are one range of one conditional
    probability over one adjustment set. Two answers there is a reader
    misled whichever module is right."""
    bad = copy.deepcopy(THIN["result"])
    summary = bad["numeric_estimate"]["propensity_summary"]
    assert summary["raw_min"] == _at(THIN, "fitted_overlap", "p_min")
    summary["raw_min"] = 0.004
    with pytest.raises(VerificationError, match="the same fitted propensity"):
        themis.verify(THIN["program"], bad)


def test_a_propensity_that_depends_on_nothing_cannot_have_a_range():
    """An empty adjustment set leaves P(X=1|Z) with nothing to vary with, so
    the model is one constant. Constructed rather than harvested: no answer
    the suite produces takes this branch, and a branch nothing exercises is
    an assertion nobody has read."""
    with pytest.raises(VerificationError, match="depends on nothing"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "adjustment": [], "sample_size": 100,
            "propensity_summary": {"raw_min": 0.2, "raw_max": 0.8,
                                   "n_trimmed": 0, "floor": 0.01,
                                   "model": "marginal"}}})


def test_which_model_was_fitted_is_decided_by_what_was_adjusted_for():
    """The envelope already says which set this answer adjusted for, and
    that settles which of the two propensity models can have been fitted.
    Both directions, because both are a reader told the wrong thing about
    where the weights came from."""
    def summary(**over):
        block = {"raw_min": 0.4, "raw_max": 0.4, "n_trimmed": 0,
                 "floor": 0.01, "model": "marginal"}
        block.update(over)
        return block

    with pytest.raises(VerificationError, match="adjusts for"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "adjustment": ["z"], "propensity_summary": summary()}})
    with pytest.raises(VerificationError, match="adjusts for"):
        verify_fitted_diagnostics({"numeric_estimate": {
            "adjustment": [],
            "propensity_summary": summary(model="logistic")}})


# ==================================================== where the line is


def test_a_block_arriving_without_its_counts_is_refused_at_the_door():
    """Presence is the schema's to require, and this pins that it does.

    The rule above holds the arithmetic and says nothing when the counts are
    absent — which would be the silence this whole item is about, if the
    door did not already refuse one gate earlier. Asked of the door, because
    that is the claim: not that some module would refuse it, but that
    ``themis.verify`` does.
    """
    bad = copy.deepcopy(THIN["result"])
    bad["numeric_estimate"]["fitted_overlap"].pop("n_outside")
    with pytest.raises(Exception):
        themis.verify(THIN["program"], bad)


def test_an_answer_with_no_such_diagnostic_is_left_alone():
    """A run whose treatment is not binary fits no propensity, and a run
    whose fit did not converge records nothing. Nothing on the envelope says
    which happened, so an absent block is a check not made rather than a
    check hidden — and the reader is told nothing rather than something
    false. Refusing here would refuse every estimator that has no reason to
    carry one."""
    verify_fitted_diagnostics({})
    verify_fitted_diagnostics({"numeric_estimate": {}})
    verify_fitted_diagnostics(
        {"numeric_estimate": {"method": "backdoor_linear", "point": 1.0,
                              "sample_size": 500}})
