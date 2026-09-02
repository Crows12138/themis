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
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
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
    assert len(CARRIERS) == 31
    assert all(len(_mechanisms(SHAPES[n]["result"])) == 1 for n in CARRIERS)


def test_every_honest_answer_shape_is_still_accepted():
    for name in sorted(SHAPES):
        program, result = _pair(name)
        themis.verify(program, result)


def test_the_target_is_the_outcome_the_question_names():
    """The measurement the rule is built on, kept where it can go stale.

    Twenty-six exactly equal. The remaining five are counted here and
    named in the test below, because a rule's reach is a number somebody
    can check and its exceptions are a list somebody must justify.
    """
    equal, other = 0, []
    for name in CARRIERS:
        outcome = _outcome_of(name)
        for mechanism in _mechanisms(SHAPES[name]["result"]):
            if mechanism["target"] == outcome:
                equal += 1
            else:
                other.append(name)
    assert (equal, len(other)) == (26, 5)
    assert set(other) == _RENDERS_ITS_TARGET | {"ctf_conjunction_plugin"}


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
        themis.verify(program, result)
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


def test_the_form_beside_the_target_is_declared_not_held():
    """Counted, so that "we closed the mechanism block" cannot be said.

    ``form`` is a function of ``method`` across the corpus, and the four
    that a bend cannot survive are held by their own route audits, not by
    anything about the shape word. What would hold the rest is a table of
    shape words this repository would then own — a different root cause,
    and its own frontier.
    """
    survived = []
    for name in CARRIERS:
        for bend in ("_forged", "", "x"):
            program, result = _pair(name)
            form = _mechanisms(result)[0]["form"]
            _mechanisms(result)[0]["form"] = (
                form + bend if bend == "_forged" else bend)
            try:
                themis.verify(program, result)
            except Exception:
                continue
            survived.append(name)
            break
    assert len(survived) == 27
    assert set(survived) & _RENDERS_ITS_TARGET == set()


def test_the_rule_is_silent_where_there_is_no_block_to_read():
    """Not a skip: an answer that discloses no mechanism makes no claim
    about a shape, and there is nothing here to be right or wrong about.
    """
    for name in sorted(set(SHAPES) - set(CARRIERS)):
        program, result = _pair(name)
        assert not _mechanisms(result)
        verify_mechanism_target(result, object())
