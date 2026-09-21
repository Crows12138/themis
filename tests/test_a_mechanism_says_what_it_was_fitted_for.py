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
    FITS, _RENDERS_ITS_TARGET, _the_link_a_slope_is_taken_through,
    _the_slope_as_spelt, outcome_the_question_names,
    treatment_the_question_intervenes_on, verify_mechanism_target,
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


def _a_row_on(method):
    """A stored answer that ran this route.

    By the route rather than by the row's name: a row is named after its
    method only while every row in the corpus carries a number, and the
    three routes that spell a world are named for the question they
    answered instead.
    """
    for name in CARRIERS:
        if _method_of(name) == method:
            return name
    raise AssertionError(f"{method} names no answer shape")


def _context_of(name):
    """The question, as the rule receives it."""
    program, result = _pair(name)
    captured = []
    import themis.kernel as kernel
    real = kernel.verify_mechanism_target

    def spy(res, context):
        captured.append(context)
        return real(res, context)

    kernel.verify_mechanism_target = spy
    try:
        the_door_for(result)(program, result)
    finally:
        kernel.verify_mechanism_target = real
    return captured[-1] if captured else None


def _asked_of(name):
    """What a slope renderer is offered, taken the way the rule takes it."""
    context = _context_of(name)
    return (outcome_the_question_names(context),
            treatment_the_question_intervenes_on(context))


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
    # Compared as METHODS, which is what that roster is keyed on. A
    # shape's NAME was its method for as long as every row in the corpus
    # carried a number; the answers that take no route are named for what
    # they are instead, and a name-to-method comparison quietly stopped
    # being one comparison at all.
    assert {_method_of(n) for n in rendered} == {
        "differential_outcome_correction",
        "differential_regression_calibration",
        "regression_calibration", "simex"}
    # And the third bucket names a question kind, not a method's habit:
    # causation, the counterfactual cell and the counterfactual
    # conjunction all ask something with no outcome slot in it. That was
    # once read as a reason to be silent about them; what it is a reason
    # for is reading them against a different sentence, which is why both
    # buckets are the same roster now.
    assert {_method_of(n) for n in unasked} == {
        "causation_plugin", "counterfactual_cell_plugin",
        "ctf_conjunction_plugin"}
    assert ({_method_of(n) for n in rendered}
            | {_method_of(n) for n in unasked}) == set(_RENDERS_ITS_TARGET)


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


# ------------------------------------- what is spelled is spelled again


def test_the_routes_that_spell_their_target_are_named():
    """A rendering is not a reference, and there are seven of them.

    Four model a SLOPE, which the problem has no name for, so the slot can
    only spell "the derivative of ``y`` with respect to ``w``". Three spell
    a WORLD — a cell of the counterfactual joint, a conjunction of
    counterfactual events, a probability of necessity — and their
    questions name no single outcome to be equal to. Pinned by name so an
    eighth is a red suite rather than a quiet eighth, because a route that
    spells a sentence nobody wrote down is read against a sentence it never
    meant.
    """
    assert set(_RENDERS_ITS_TARGET) == {
        "differential_outcome_correction",
        "differential_regression_calibration",
        "regression_calibration",
        "simex",
        "causation_plugin",
        "counterfactual_cell_plugin",
        "ctf_conjunction_plugin",
    }
    for method in _RENDERS_ITS_TARGET:
        name = _a_row_on(method)
        target = _mechanisms(SHAPES[name]["result"])[0]["target"]
        assert target != _outcome_of(name)


def test_what_each_route_spells_is_what_the_question_spells():
    """The measurement the reading rests on, kept where it can go stale.

    Every stored answer on one of these routes, spelled from its own
    question and compared with what it stored. A producer that changes its
    wording arrives here rather than as an honest answer the kernel refuses
    at its own exit.
    """
    seen = 0
    for name in CARRIERS:
        spells = _RENDERS_ITS_TARGET.get(_method_of(name))
        if spells is None:
            continue
        mechanism = _mechanisms(SHAPES[name]["result"])[0]
        assert spells(_context_of(name),
                      mechanism["form"]) == mechanism["target"]
        seen += 1
    assert seen == 10, seen


def test_a_slope_and_a_world_are_spelled_by_different_hands():
    """The roster is a mapping and not a set, so what each route spells is
    a fact beside its name rather than one rule's guess at which sentence
    a route meant."""
    assert (_RENDERS_ITS_TARGET["simex"]
            is _RENDERS_ITS_TARGET["regression_calibration"])
    assert (_RENDERS_ITS_TARGET["causation_plugin"]
            is not _RENDERS_ITS_TARGET["simex"])
    assert len({spells for spells in _RENDERS_ITS_TARGET.values()}) == 4


@pytest.mark.parametrize("bend", ["_forged", "", "xz"])
def test_a_slope_spelled_some_other_way_is_refused(bend):
    """The three lies a free string can be told, each put to the sentence
    the question spells. The blank is refused by the check that runs ahead
    of every reading; the other two by the reading itself."""
    target = _mechanisms(SHAPES["simex"]["result"])[0]["target"]
    with pytest.raises(VerificationError):
        _verify_with("simex", lambda m, r: m.update(
            target=target + bend if bend == "_forged" else bend))


def test_a_slope_taken_through_another_variable_is_refused():
    """The lie this reading exists for: a sentence that is well formed,
    names variables the problem declares, and is about a different
    derivative than the one asked for."""
    with pytest.raises(VerificationError, match="nobody asked"):
        _verify_with("regression_calibration", lambda m, r: m.update(
            target="dE[y|do(z),Z]/dz"))


def test_the_arm_a_slope_is_taken_through_is_read_off_its_shape_word():
    """Every shape these four routes may declare, and what each spells.

    Driven over ``FITS`` rather than over the corpus: the corpus holds one
    simex shape of six, and a table built from it would send this to green
    while refusing the other five at the kernel's exit.
    """
    for method in sorted(_RENDERS_ITS_TARGET):
        for form in sorted(FITS[method]):
            link = _the_link_a_slope_is_taken_through(form)
            assert link == ("logit " if "logistic" in form.split("_") else "")
    assert sorted(FITS["simex"]) == [
        "simex_linear_linear", "simex_linear_quadratic",
        "simex_linear_rational", "simex_logistic_linear",
        "simex_logistic_quadratic", "simex_logistic_rational"]


def test_a_shape_word_is_not_read_as_a_substring_of_itself():
    """``logistic`` is a WORD of a form, not a run of letters in it. A
    reading by substring would find the arm inside a route that merely
    mentions it, and a route named after the arm it is NOT would be read
    as the arm it is."""
    assert _the_link_a_slope_is_taken_through("simex_logistic_rational")
    assert not _the_link_a_slope_is_taken_through("unlogistic_linear_rational")
    assert not _the_link_a_slope_is_taken_through(
        "regression_calibration_backdoor_linear")


def test_a_question_that_intervenes_on_nothing_leaves_nothing_to_spell():
    """The silence this reading keeps, and it is the same silence the rule
    beside it keeps: a slope is a slope OF something, and a question with
    no intervention names no variable to differentiate through."""
    assert treatment_the_question_intervenes_on(object()) is None
    verify_mechanism_target(
        {"extensions": {"mechanism_audit": {"mechanisms": [
            {"method": "simex", "form": "simex_logistic_rational",
             "target": "anything at all"}]}}},
        object())


@pytest.mark.parametrize("method,bend", [
    ("causation_plugin", "_forged"),
    ("causation_plugin", "xz"),
    ("counterfactual_cell_plugin", "_forged"),
    ("counterfactual_cell_plugin", "xz"),
    ("ctf_conjunction_plugin", "_forged"),
])
def test_a_world_spelled_some_other_way_is_refused(method, bend):
    """The three sentences about worlds, each put the lies a free string
    can be told. Their questions name no outcome, which is what used to
    make every one of these pass."""
    name = _a_row_on(method)
    target = _mechanisms(SHAPES[name]["result"])[0]["target"]
    with pytest.raises(VerificationError):
        _verify_with(name, lambda m, r: m.update(
            target=target + bend if bend == "_forged" else bend))


def test_a_question_with_no_single_outcome_is_read_against_its_own_sentence():
    """What that question has no outcome FOR is being equal to something.

    A counterfactual conjunction asks about a sentence rather than a
    variable, and for as long as the only reading was "is this the
    outcome", having no outcome read as having nothing to check. The
    sentence is in the question, so the target is read against it now, and
    a forgery there is refused like any other.
    """
    assert _outcome_of("ctf_conjunction_plugin") is None
    with pytest.raises(VerificationError, match="nobody asked"):
        _verify_with("ctf_conjunction_plugin",
                     lambda m, r: m.update(target="anything at all"))


def test_the_silence_left_is_a_question_that_carries_no_sentence():
    """What an exemption became: a reading that has nothing to read.

    Not an exception list and not a habit of four routes — a question
    object with none of the parts its own sentence is made of leaves every
    renderer with nothing to build, and the rule is silent there for the
    reason it is silent about a question with no outcome.
    """
    for spells in set(_RENDERS_ITS_TARGET.values()):
        assert spells(object(), "simex_logistic_rational") is None
    verify_mechanism_target(
        {"extensions": {"mechanism_audit": {"mechanisms": [
            {"method": "ctf_conjunction_plugin",
             "form": "nonparametric_plug_in",
             "target": "anything at all"}]}}},
        object())


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
