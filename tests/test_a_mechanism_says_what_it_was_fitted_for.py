"""A mechanism's target, and the room its ruler was missing from.

``extensions.mechanism_audit`` tells a reader what shape stands behind a
number: the ``form`` the fit took, the ``method`` that ran it, the
assumptions it was settled under, and the ``target`` — the thing that
shape was fitted FOR. Three of those four have a holder. The target did
not: measured before this file existed, every one of thirty-one targets
on the forty-four answer shapes could be rewritten and the public door
said yes.

What makes this different from an oversight is that the target was
DECLARED uncheckable, in a paragraph on
``_check_the_block_describes_the_fit_that_ran``, and the reason given was
that the field means two things and so has no witness. Every mechanism
check lives in ``assumption_ledger_rules``, reached through
``verify_assumption_ledger(result)`` — a result-only door with no program
beside it. A target names the thing the QUESTION is about; from behind
that door the question does not exist, and the nearest copy that does is
the answer's own. That copy was tried and refused seventeen honest
results, which is what the declaration was written from.

Asked of the question instead, twenty-six of thirty-one targets are its
outcome EXACTLY. The field was never the problem. Two rulers disagreed
and the disagreement was about where each was standing.

The corpus has since widened to the answers that carry no number. The
reach moved with it and the exception list did not, which is the shape of
an exception that is about a route rather than about how many answers
happened to be looked at.

Three of four had a holder when this file was written, and ``form`` was
the fourth — counted here rather than waved at, because a block with one
unheld field is not a closed block. It has one now: the shapes each
method can fit are declared, and the loop that already held ``method``
and the named assumptions reads the third. The count below stays and
reads zero, which is the only way "the form is held" is a measurement
rather than a claim.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import the_door_for
from tests.answer_corpus import reads, verify_honestly
from themis.verifier.errors import VerificationError
from themis.verifier.mechanism_rules import (
    _RENDERS_ITS_TARGET, outcome_the_question_names, verify_mechanism_target,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _mechanisms(result):
    return (((result.get("extensions") or {})
             .get("mechanism_audit") or {}).get("mechanisms") or [])


CARRIERS = sorted(n for n in SHAPES if _mechanisms(SHAPES[n]["result"]))


def _method_of(name):
    """The estimator a row's answer came from.

    Read off the answer rather than off the row's name: a structural row
    is named for the status, question and terminal rule it has, because it
    has no method to be named after.
    """
    return (SHAPES[name]["result"].get("numeric_estimate") or {}).get("method")


def _pair(method):
    pair = SHAPES[method]
    return pair["program"], copy.deepcopy(pair["result"])


def _verify_with(method, mutate):
    program, result = _pair(method)
    mutate(_mechanisms(result)[0], result)
    themis.verify(program, result)


# ------------------------------------------------- the facts this rests on


def test_a_mechanism_audit_is_carried_by_most_answers():
    """Stated so a narrowing shows up as a failure, not a quiet pass."""
    assert len(CARRIERS) == 58
    assert all(len(_mechanisms(SHAPES[n]["result"])) == 1 for n in CARRIERS)


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        verify_honestly(*_pair(name))


def test_the_target_is_the_outcome_the_question_names():
    """The measurement the rule is built on, kept where it can go stale.

    Three outcomes, not two, and the third is what a widened corpus taught
    this test. Most targets are exactly the outcome. Some are a RENDERING
    of it, and those methods are named in a set the rule itself carries.
    And on some question kinds there is no outcome to compare with at all
    — a causation question asks about a pair of variables and a
    counterfactual one about a world, and neither has the outcome slot an
    effect question has. The rule has always said so
    (``if outcome is None or target == outcome: continue``); this test
    counted that silence as a difference, which was invisible while the
    corpus held only questions that name an outcome.

    A rule's reach is a number somebody can check and its exceptions are a
    list somebody must justify — so the two exceptions are counted apart,
    because "the rule chose not to ask" and "the rule asked and allowed
    it" are different facts about coverage.
    """
    equal, rendered, unasked = 0, [], []
    for name in CARRIERS:
        outcome = _outcome_of(name)
        for mechanism in _mechanisms(SHAPES[name]["result"]):
            if outcome is None:
                unasked.append(name)
            elif mechanism["target"] == outcome:
                equal += 1
            else:
                rendered.append(name)
    assert (equal, len(rendered), len(unasked)) == (48, 7, 3)
    # Compared as METHODS, which is what that frozenset is a set of. A
    # shape's NAME was its method for as long as every row in the corpus
    # carried a number; the answers that take no route are named for what
    # they are instead, and a name-to-method comparison quietly stopped
    # being one comparison at all.
    assert {_method_of(n) for n in rendered} == _RENDERS_ITS_TARGET
    # And the third bucket names a question kind, not a method's habit:
    # causation, the counterfactual cell and the counterfactual
    # conjunction all ask something with no outcome slot in it. The last
    # of those used to be carried as an extra name beside the rendering
    # set — an exception filed under the wrong reason, which reads exactly
    # like a justified one until a corpus arrives with the other two.
    assert {_method_of(n) for n in unasked} == {
        "causation_plugin", "counterfactual_cell_plugin",
        "ctf_conjunction_plugin"}


def _outcome_of(name):
    """The question's outcome, taken the way the rule takes it."""
    program, result = _pair(name)
    captured = []
    import themis.kernel as kernel
    real = kernel.verify_mechanism_target

    def spy(res, context):
        captured.append(outcome_the_question_names(context))
        return real(res, context)

    kernel.verify_mechanism_target = spy
    try:
        the_door_for(result)(program, result)
    finally:
        kernel.verify_mechanism_target = real
    return captured[-1] if captured else None


# ------------------------------------------------------------- the gate


def test_a_target_swapped_for_another_variable_is_refused():
    """The counter-example this rule exists to say no to.

    ``z`` is a name this problem declares, so a rule that asked only
    "is this a name we have" would accept it. What the reader is misled
    about is not whether the word is real; it is which fit they are
    weighing.
    """
    with pytest.raises(VerificationError, match="fitted for 'z'"):
        _verify_with("backdoor_linear",
                     lambda m, r: m.update(target="z"))


def test_a_target_dressed_as_the_outcome_is_refused():
    with pytest.raises(VerificationError, match=r"fitted for 'y\[0\]'"):
        _verify_with("backdoor_linear",
                     lambda m, r: m.update(target="y[0]"))


def test_a_mechanism_may_not_name_its_target_and_leave_it_empty():
    """Asked before any exemption reaches it, and that order is the point.

    An exemption is a way of not asking, and a blank is the value every
    way of not asking lets through. Put after the roster check, this
    passes for the four routes below — which is how the same hole was
    reached three frontiers running.
    """
    for method in ("backdoor_linear", "simex"):
        with pytest.raises(VerificationError, match="hole where that goes"):
            _verify_with(method, lambda m, r: m.update(target="  "))


def test_the_authority_is_the_question_not_the_answers_copy_of_it():
    """``scm_counterfactual_linear_fit`` records no ``outcome`` of its own.

    Its target is held anyway, which no rule reachable from the
    result-only door could have managed. This is the whole difference
    between the two rulers, stated as a case rather than as a claim.
    """
    program, result = _pair("scm_counterfactual_linear_fit")
    assert "outcome" not in (result.get("numeric_estimate") or {})
    with pytest.raises(VerificationError, match="the question asks about"):
        _verify_with("scm_counterfactual_linear_fit",
                     lambda m, r: m.update(target="z"))


# ------------------------------------------- what the rule does not reach


def test_the_routes_that_render_their_target_are_named():
    """A rendering is not a reference, and there are four of them.

    A measurement-error route models a SLOPE, and the slot has no way to
    say "the derivative of ``y`` with respect to ``w``" except by
    spelling it. Pinned by name so a fifth is a red suite rather than a
    quiet fifth.
    """
    assert _RENDERS_ITS_TARGET == frozenset({
        "differential_outcome_correction",
        "differential_regression_calibration",
        "regression_calibration",
        "simex",
    })
    for method in _RENDERS_ITS_TARGET:
        assert method in CARRIERS, f"{method} names no answer shape"
        target = _mechanisms(SHAPES[method]["result"])[0]["target"]
        assert target != _outcome_of(method)


def test_a_question_with_no_single_outcome_leaves_nothing_to_compare():
    """The fifth is not a gap: a counterfactual conjunction asks about a
    sentence, not a variable, so there is no outcome for a target to be.

    The silence is keyed on the ASKED side, which is what makes being
    silent safe here — an answer cannot edit its question into having no
    outcome. Stated as a passing forgery so the day a target IS available
    there fails loudly.
    """
    assert _outcome_of("ctf_conjunction_plugin") is None
    _verify_with("ctf_conjunction_plugin",
                 lambda m, r: m.update(target="anything at all"))


def test_the_exemption_costs_two_lies_and_still_does_not_buy_anything():
    """Whether a route can reach the roster by claiming to be on it.

    The roster is keyed on ``method`` because that is the field naming a
    route that a verifier can see. Claiming it on the block alone is
    refused by the check that holds the block to the estimate; claiming
    it on both is refused because a simex estimate must carry the ladder
    it was extrapolated from. Measured rather than assumed, since a
    roster with a free door is a roster of exemptions for everyone.
    """
    with pytest.raises(VerificationError, match="the fit was 'simex'"):
        _verify_with("backdoor_linear", lambda m, r: m.update(
            target="dE[y|do(x),Z]/dx", method="simex"))

    def both(m, r):
        m.update(target="dE[y|do(x),Z]/dx", method="simex")
        r["numeric_estimate"]["method"] = "simex"

    with pytest.raises(VerificationError, match="ladder"):
        _verify_with("backdoor_linear", both)


def test_the_form_beside_the_target_survives_no_bend_now():
    """This counted the hole, so that "we closed the mechanism block"
    could not be said while fifty-one forms could be rewritten. It counts
    zero, and that is the whole of the change: the table of shape words
    it named as a different frontier exists —
    :data:`themis.estimation.form.FITS`, re-declared for this side in
    ``verifier.mechanism_rules`` — and the loop that already held the
    block's ``method`` and its named assumptions now looks at the shape
    too.

    The note here said ``form`` is a function of ``method`` across the
    corpus. It is not one in the build: ``tmle`` fits the logit link for a
    bool outcome and the line otherwise, and the corpus holds one of the
    two because a corpus is a sample. That is why the count stays, in the
    other direction: a table assembled from the corpus would send this to
    zero as well, while refusing honest runs, and
    ``test_a_shape_is_one_this_build_can_fit`` is where the difference is
    held.
    """
    # Every mechanism block is asked at a door that READS the answer
    # carrying it, which is the point this guard was making: a door that
    # refuses an answer for what it IS would score every bend below as
    # held by a refusal that never looked. It used to be made by requiring
    # a chain of every carrier, which was true of the corpus of the day
    # and stopped being true the moment the corpus reached the answers
    # that take no route — and those carry mechanism blocks to a reader
    # just the same. The requirement is about the DOOR, so it is now
    # asked of the door.
    assert all(the_door_for(SHAPES[n]["result"]) is not None
               for n in CARRIERS)

    survived = []
    for name in CARRIERS:
        for bend in ("_forged", "", "x"):
            program, result = _pair(name)
            form = _mechanisms(result)[0]["form"]
            _mechanisms(result)[0]["form"] = (
                form + bend if bend == "_forged" else bend)
            try:
                the_door_for(result)(program, result)
            except Exception:
                continue
            survived.append(name)
            break
    assert survived == []
    # And the carriers really were asked — a count of zero reached by
    # having nothing to bend would say the same thing and mean nothing.
    assert len(CARRIERS) >= 51


def test_the_rule_is_silent_where_there_is_no_block_to_read():
    """Not a skip: an answer that discloses no mechanism makes no claim
    about a shape, and there is nothing here to be right or wrong about.
    """
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        assert not _mechanisms(result)
        verify_mechanism_target(result, object())
