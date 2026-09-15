"""The reason an answer declined a route is held like the route.

An IV number over an ordered dose says one of two things about the
average-causal-response decomposition: the margin table, or why there is
none. The table was re-derived and the reason was free. Asked with the leaf
sweep's own door set, the twelve doors that read those two answers accepted
another declared reason, a word outside the vocabulary, the empty string, a
reason that CONTRADICTS ITSELF (four levels "over the cap of 12"), and the
field's deletion.

The audit was keyed on the method ``iv_acr``, and a decline exists precisely
because the method is ``iv_2sls`` — a claim that is on the envelope BECAUSE a
route was not taken can never be reached through that route's own name. The
same table has learnt this twice already: ``verify_treatment_box`` is keyed on
the box it re-derives because "which route had its numbers checked" used to
mean "which route remembered to keep its corners", and the front-door audit is
keyed on the family rather than on its members. It is now keyed on either
claim about this route.

Nothing asked below needs data, which is what makes the reason checkable at
all: the cap is this build's, the level count is held between the cap the
sentence claims to exceed and the row count it cannot exceed, and which reason
is owed follows from the conditioning set the estimate reports — the first
thing the producer looks at. What stays unreachable is the count itself, and
the field's absence: "should have said and did not" needs to know the route was
chosen automatically and how many levels the dose has, and neither is on the
envelope.

The words and the cap are written out here rather than read from the rule. A
test that asks the implementation which sentences it accepts agrees with it by
construction; the test below asks the PRODUCER instead, and holds all three
copies together.
"""
from __future__ import annotations

import copy
import json
import pathlib

import numpy as np
import pandas as pd
import pytest

import themis
import themis.verifier.verify as verify_module
from themis.verifier import VerificationError, verify_acr_decomposition

SHAPES = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: The corpus rows that declined the route, and the one that took it.
DECLINED = ("iv_2sls", "numerically_solved:effect:numeric_iv_estimate#70a0ba")
TOOK_IT = "iv_acr"

#: What a decline may say, and the cap it may say it about.
CONDITIONAL = "conditional_estimand_is_not_the_unconditional_ACR"
CAP = 12


def _estimate(**over) -> dict:
    """A 2SLS estimate carrying only the fields this rule reads."""
    return {"method": "iv_2sls", "conditioning": [], "sample_size": 6000,
            **over}


def test_the_stored_answers_are_accepted_as_they_stand():
    for name in (*DECLINED, TOOK_IT):
        pair = SHAPES[name]
        themis.verify(pair["program"], pair["result"])


@pytest.mark.parametrize("said", [
    "forged",
    "",
    "x",
    # The reason the producer computes and never sends: every binary
    # treatment is a single margin, so an envelope carrying this one carries
    # a reason nothing could have given it.
    "treatment_has_a_single_margin",
    "dose_has_4_levels_over_the_cap_of_12",        # not over the cap it names
    "dose_has_6000_levels_over_the_cap_of_20",     # not this build's cap
    "dose_has_99999_levels_over_the_cap_of_12",    # more levels than rows
])
@pytest.mark.parametrize("name", DECLINED)
def test_a_reason_the_producer_could_not_have_given_is_refused(name, said):
    pair = SHAPES[name]
    forged = copy.deepcopy(pair["result"])
    forged["numeric_estimate"]["acr_declined"] = said
    with pytest.raises(VerificationError):
        themis.verify(pair["program"], forged)


def test_a_reason_that_is_not_a_sentence_is_refused():
    with pytest.raises(VerificationError):
        verify_acr_decomposition(_estimate(acr_declined=7))


def test_the_conditional_reason_is_owed_when_the_answer_conditions_on_something():
    verify_acr_decomposition(_estimate(conditioning=["w"],
                                       acr_declined=CONDITIONAL))
    with pytest.raises(VerificationError, match="conditions on nothing"):
        verify_acr_decomposition(_estimate(acr_declined=CONDITIONAL))
    with pytest.raises(VerificationError, match="conditions on w"):
        verify_acr_decomposition(_estimate(
            conditioning=["w"],
            acr_declined=f"dose_has_6000_levels_over_the_cap_of_{CAP}"))


def test_the_level_count_is_held_between_the_cap_and_the_rows():
    verify_acr_decomposition(_estimate(
        acr_declined=f"dose_has_{CAP + 1}_levels_over_the_cap_of_{CAP}"))
    with pytest.raises(VerificationError, match="not over the cap"):
        verify_acr_decomposition(_estimate(
            acr_declined=f"dose_has_{CAP}_levels_over_the_cap_of_{CAP}"))
    with pytest.raises(VerificationError, match="distinct levels in 6000 rows"):
        verify_acr_decomposition(_estimate(
            acr_declined=f"dose_has_6001_levels_over_the_cap_of_{CAP}"))


def test_the_table_and_the_reason_there_is_none_cannot_both_be_there():
    with pytest.raises(VerificationError, match="one of the two"):
        verify_acr_decomposition(_estimate(
            acr_declined=f"dose_has_{CAP + 1}_levels_over_the_cap_of_{CAP}",
            acr_decomposition={"cells": []}))


def test_the_method_that_is_the_decomposition_cannot_say_it_declined_it():
    with pytest.raises(VerificationError, match="the method IS"):
        verify_acr_decomposition(_estimate(
            method="iv_acr",
            acr_declined=f"dose_has_{CAP + 1}_levels_over_the_cap_of_{CAP}"))


def test_the_three_copies_of_the_reason_are_one_vocabulary():
    """The producer's words, the verifier's reading of them, and this file's.

    Pinned by asking the producer rather than by comparing source text: the
    verifier may not import the estimation layer, so a test that reads both
    is the only place the copies meet.
    """
    from themis.estimation.iv import _MAX_ACR_LEVELS, _why_not_acr

    assert _MAX_ACR_LEVELS == CAP == verify_module._ACR_LEVEL_CAP
    assert verify_module._ACR_DECLINED_CONDITIONAL == CONDITIONAL

    dose = pd.DataFrame({"x": np.arange(float(CAP + 1))})
    said = _why_not_acr(dose, "x", ())
    found = verify_module._ACR_DECLINED_LEVELS.match(said)
    assert found is not None, said
    assert int(found[1]) == CAP + 1
    assert int(found[2]) == CAP
    assert _why_not_acr(dose, "x", ("w",)) == CONDITIONAL


def test_the_audit_applies_for_what_the_answer_says_not_the_route_it_took():
    """The keying itself, so it cannot go back to the method.

    A rule reached only through ``iv_acr`` cannot read a sentence that is
    there because the method is ``iv_2sls``.
    """
    from themis.kernel import _ESTIMATE_AUDITS

    row = next(r for r in _ESTIMATE_AUDITS
               if r.rule is verify_acr_decomposition)
    assert not row.methods and not row.method_prefixes
    assert row.applies({"method": "iv_2sls", "acr_declined": "whatever"})
    assert row.applies({"method": "iv_acr", "acr_decomposition": {}})
    assert not row.applies({"method": "iv_2sls"})
