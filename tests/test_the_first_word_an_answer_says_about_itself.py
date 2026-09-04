"""``status`` is what a reader meets first, and nothing had held it.

It is also what the audit dispatches on: :func:`themis.verify` routes on
it, and so does the estimate half. A field that SELECTS the checks is a
premise of the audit until somebody holds it — the sentence #568 wrote
about ``query_kind`` and ``answer_tier``, with this one named in the same
breath and left there.

Measured before anything was written: of 1458 relabellings of the corpus's
own answers, **673 were accepted at both public doors**. A gap diagnosis
could call itself ``numerically_solved``; an answer that reached a number
could call itself ``outside_language``.

The root cause is not a missing rule. ``ResultStatus`` was seven bare
strings, and what each of them CLAIMS was written nowhere — while a route,
a species and a sentence in this package are each declared with what they
say. Nothing could hold the word because nothing said what it meant. So
the meaning is declared beside the word
(:data:`themis.types.STATUS_CLAIMS`), the audit reads the blocks for
itself, and the two have to agree.

Two things can hold the word and the second one is here too. What the
envelope SHOWS stops where two words show the same thing — a
counterfactual point and an estimated one are one rung. What the question
ASKED separates them, and which words a question's answer may lead with is
declared beside the question (``themis.questions``' ``answers_with``),
while the words a REFUSAL leaves are open to every question and declared
once on ``refusals.Kind.outcome``.

What is asserted here:

- no honest answer is refused, at the strongest door that reads it
- each of the six claims is exercised on a real answer, so a claim that
  quietly stopped applying fails rather than passes
- the two readings the rule takes of one envelope answer oppositely on the
  case that separates them, and the roster they are taken from is the
  block registry's own
- the roster of words a question may answer with is the questions' own and
  is total over the kinds the contract admits; the words open to every
  question are the refusal kinds' own; and each half is put to the case it
  has to say no to, and to the case it must not
- the numbers: what each rule reaches, what they refuse, and what they do
  not — the survivors are named, because a gate that reports its own
  blindness as coverage is the failure this whole line of work is about
- the table is total over the words, and every word it claims about is a
  word the contract admits.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from themis import blocks, questions, refusals
from themis.types import STATUS_CLAIMS, ResultStatus, Shown
from themis.verifier import VerificationError
from themis.verifier.status_rules import (
    _ANSWER_BLOCKS, _ANSWERS_WITH, _REFUSAL_WORDS, _might_be_showing, _shown,
    verify_answer_status, verify_answer_status_fits_its_question)

from . import schema_walk
from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

RULE = "answer_status_check"
RULE_QUESTION = "answer_status_question_check"

#: What one relabelling of every answer comes to. Stated so that a
#: narrowing shows up as a number: 1458 swaps, of which 673 survived both
#: doors before either rule, 246 after the envelope was read, and 139 once
#: the question was too.
SWAPS = 1458
SURVIVING = 139
BY_WHAT_IT_SHOWS = 694
BY_WHAT_WAS_ASKED = 191

#: Which relabellings the envelope cannot tell apart, and how many of each.
#:
#: Named rather than counted, because these are the honest limit of what
#: the two rules can see between them, and a gate that reports its own
#: blindness as coverage is the failure this line of work is about.
#:
#: What is left is of two shapes and neither has a rule to write. Words a
#: REFUSAL leaves are open to every question by construction, so no roster
#: narrows them — a refusal is about what this system could not do rather
#: than about what was asked. And where a question's answer may lead with
#: either of two words that both say a quantity arrived, nothing separates
#: them: on the envelope they show the same thing, and the question admits
#: both. Telling those apart would need what the run DID, which is the
#: derivation, not the word.
#:
#: Forty-six of these were caught by an earlier draft and are given back
#: on purpose. That draft asked ``counterfactual_solved`` for a POINT and
#: ``counterfactual_bounded`` for an INTERVAL, which is a promise about
#: the SHAPE a quantity took — readable only by enumerating the keys a
#: shape can sit under, which is how the same draft came to refuse thirteen
#: honest region answers. A promise is only as good as the totality of the
#: reading behind it, so these words now promise a quantity and not a shape
#: of one, and the forty-six are the price. The roster took 107 of them
#: back by asking the question instead of the envelope.
SURVIVORS = {
    "counterfactual_solved -> numerically_solved": 43,
    "needs_investigation -> numerically_solved": 42,
    "needs_investigation -> outside_language": 24,
    "structurally_solved -> needs_investigation": 19,
    "counterfactual_bounded -> counterfactual_solved": 3,
    "counterfactual_bounded -> numerically_solved": 3,
    "needs_investigation -> structurally_solved": 2,
    "outside_language -> needs_investigation": 2,
    "numerically_solved -> needs_investigation": 1,
}


# --- the word means something, and every word has a meaning -------------------


def test_every_word_an_answer_can_lead_with_says_what_it_claims():
    """The gate the table's own binder raises, asserted here too, because
    the binder runs at import and a test that never imported it would
    report an unclaimed word as nothing at all."""
    assert set(STATUS_CLAIMS) == set(ResultStatus)


def test_the_words_the_table_claims_about_are_the_contracts_words():
    """A claim about a status the envelope may not carry is a claim
    nothing can be held to."""
    declared = next(
        schema_walk.RESULT.resolve(sub).get("enum")
        for path, sub, _c in schema_walk.RESULT.walk()
        if path == ("status",)
        and isinstance(schema_walk.RESULT.resolve(sub).get("enum"), list))
    assert {str(s) for s in STATUS_CLAIMS} == set(declared)


def test_a_claim_is_about_something_an_envelope_can_show():
    """Both halves are written in one vocabulary, and it is the one the
    reading below answers in."""
    for status, claim in STATUS_CLAIMS.items():
        for wanted in claim.carries:
            assert wanted <= frozenset(Shown), status
            assert wanted, f"{status} carries an empty requirement"
        assert claim.withholds <= frozenset(Shown), status


# --- no honest answer is refused ---------------------------------------------


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_honest_answer_keeps_the_word_it_chose(shape):
    """The denominator. Fifteen honest answers were refused by a first
    draft that asked ``numerically_solved`` for a POINT — a joint contrast,
    a dose-response curve and three probabilities of causation each keep
    their number under a key of their own, and an Anderson-Rubin region is
    a number the estimate blocks have no room for. The word claims a
    number, not a shape of one."""
    row = SHAPES[shape]
    verify_honestly(row["program"], row["result"])


def test_every_claim_is_exercised_by_some_honest_answer():
    """A claim no answer ever satisfies is a claim that could be anything.

    ``needs_assumption`` is the exception and is named: no dispatcher
    produces it, which its own declaration says, so the corpus cannot
    exercise it and its entry is a position rather than a measurement.
    """
    seen = {str(row["result"].get("status")) for row in SHAPES.values()}
    unexercised = {str(s) for s in STATUS_CLAIMS} - seen
    assert unexercised == {"needs_assumption"}, unexercised


# --- the teeth ----------------------------------------------------------------


def _swaps():
    for name in sorted(SHAPES):
        row = SHAPES[name]
        was = str(row["result"].get("status"))
        for other in ResultStatus:
            if str(other) == was:
                continue
            forged = copy.deepcopy(row["result"])
            forged["status"] = str(other)
            yield name, row["program"], row["result"], forged, was, str(other)


def test_a_relabelled_answer_is_refused_wherever_the_envelope_says_so():
    """One relabelling of every answer to every other word, through the
    strongest door that reads it."""
    refused = survived = shows = asks = 0
    alive: dict[str, int] = {}
    for _name, program, honest, forged, was, now in _swaps():
        try:
            the_door_for(honest)(program, forged)
        except VerificationError as exc:
            refused += 1
            shows += getattr(exc, "rule", None) == RULE
            asks += getattr(exc, "rule", None) == RULE_QUESTION
        except Exception:                                   # noqa: BLE001
            refused += 1
        else:
            survived += 1
            key = f"{was} -> {now}"
            alive[key] = alive.get(key, 0) + 1
    assert refused + survived == SWAPS, refused + survived
    assert survived == SURVIVING, survived
    assert shows == BY_WHAT_IT_SHOWS, shows
    assert asks == BY_WHAT_WAS_ASKED, asks
    assert alive == SURVIVORS, alive


def test_what_the_question_rule_reaches_on_its_own():
    """Same reason as the sibling below: most of its work happens behind
    other rules at the door, and a gate counting only what got through them
    would not notice this one going quiet."""
    refused = passed = 0
    for _name, _program, _honest, forged, _was, _now in _swaps():
        try:
            verify_answer_status_fits_its_question(forged)
        except VerificationError:
            refused += 1
        else:
            passed += 1
    assert (refused, passed) == (725, 733), (refused, passed)


def test_what_this_rule_reaches_on_its_own():
    """Most of its work is done behind other rules at the door, and a gate
    that only counted what got through them would report this one as
    smaller than it is — and would not notice it going quiet."""
    refused = passed = 0
    for _name, _program, _honest, forged, _was, _now in _swaps():
        try:
            verify_answer_status(forged)
        except VerificationError:
            refused += 1
        else:
            passed += 1
    assert (refused, passed) == (953, 505), (refused, passed)


@pytest.mark.parametrize("status,rung", [
    ("needs_investigation", Shown.POINT),
    ("outside_language", Shown.CHAIN),
    ("structurally_solved", Shown.POINT),
    ("counterfactual_bounded", Shown.POINT),
])
def test_a_word_that_denies_what_is_sitting_beside_it(status, rung):
    """The half a reader cannot check for themselves: they read the word
    and stop looking. Each denial is put to an answer that shows exactly
    the thing the word denies."""
    honest = next(row["result"] for row in SHAPES.values()
                  if rung in _shown(row["result"]))
    forged = copy.deepcopy(honest)
    forged["status"] = status
    with pytest.raises(VerificationError, match="says the run did not"):
        verify_answer_status(forged)


@pytest.mark.parametrize("status", ["structurally_solved",
                                    "numerically_solved",
                                    "counterfactual_solved",
                                    "counterfactual_bounded"])
def test_a_word_that_claims_what_is_not_there(status):
    """The other half, on an answer showing nothing at all."""
    forged = {"status": status, "query_id": "q", "query_kind": "effect"}
    with pytest.raises(VerificationError, match="claims"):
        verify_answer_status(forged)


def test_a_word_this_build_does_not_carry_is_passed_over():
    """Membership is the schema's question. A second, weaker enum check
    standing in front of the real one would answer it differently on the
    day the real one changed."""
    verify_answer_status({"status": "solved_by_vibes"})
    verify_answer_status({})


# --- what the envelope shows --------------------------------------------------


def test_the_reading_answers_off_the_blocks_and_not_off_a_summary():
    """The rule's independence, at the one place it could be lost: a
    reading taken from ``answer_tier`` or from ``status`` itself would be
    the audited field auditing itself."""
    assert _shown({"numeric_estimate": {"point": 1.0}}) == frozenset(
        {Shown.NUMBER, Shown.POINT})
    assert _shown({"numeric_result": {"value": 1.0}}) == frozenset(
        {Shown.NUMBER, Shown.POINT})
    assert _shown({"numeric_result": {"interval": [0.0, 1.0]}}) == frozenset(
        {Shown.NUMBER, Shown.INTERVAL})
    assert _shown({"bounds_results": [{}]}) == frozenset({Shown.INTERVAL})
    assert _shown({"structural_result": {}}) == frozenset({Shown.STRUCTURE})
    assert _shown({"derivation": []}) == frozenset({Shown.CHAIN})
    assert _shown({"status": "numerically_solved",
                   "data_gap_report": {"answer_tier": "point"}}) == frozenset()


def test_the_roster_of_blocks_a_quantity_can_arrive_in_is_pinned():
    """The roster is restated in the verifier, and pinned here.

    Restated for the reason every table in that package is: a verifier
    reading the producer's own roster agrees with it by construction. Pinned
    so a new answer block arrives as a red suite — the alternative is a
    reading that silently stops covering somewhere a number now lives, which
    is how this rule came to refuse thirteen honest answers.
    """
    declared = {str(b) for b in blocks.declared_as(blocks.Family.ANSWER)}
    assert _ANSWER_BLOCKS == declared


def test_the_words_a_refusal_leaves_are_the_refusal_kinds_own():
    """Open to every question, and not this module's guess about which.

    A refusal says what this system could not do, so nothing about the
    question narrows it. Which words one leaves is declared once, on the
    kinds themselves; restated in the verifier and pinned here, so a new
    refusal outcome arrives as a red suite rather than as an honest answer
    the roster has no room for.
    """
    assert _REFUSAL_WORDS == {str(k.outcome) for k in refusals.Kind}


def test_the_roster_is_the_questions_own():
    """The other half of the same pin."""
    assert _ANSWERS_WITH == {q.kind: q.answers_with
                             for q in questions.DECLARED}


def test_every_question_the_contract_admits_declares_a_roster():
    """A question with no roster would let its answers say anything, and
    would read exactly like a question whose roster happens to be wide."""
    declared = next(
        schema_walk.RESULT.resolve(sub).get("enum")
        for path, sub, _c in schema_walk.RESULT.walk()
        if path == ("query_kind",)
        and isinstance(schema_walk.RESULT.resolve(sub).get("enum"), list))
    assert set(_ANSWERS_WITH) == set(declared)


def test_an_answer_may_not_lead_with_another_questions_word():
    """The counterexample the rule exists to say no to.

    An effect query asks for an interventional contrast. A counterfactual
    point is not a sharper answer to it — it is an answer to a question
    nobody put — and the envelope cannot say so, because a point is a point
    whichever question produced it.
    """
    with pytest.raises(VerificationError, match="was not put to it"):
        verify_answer_status_fits_its_question(
            {"status": "counterfactual_solved", "query_kind": "effect"})


def test_a_word_no_question_answers_with_is_refused_everywhere():
    """``needs_assumption`` has no producer, so no question declares it.

    Refused for every kind, and by the roster's own shape rather than by a
    line naming it: a word absent from every roster is absent from the
    table. The day something emits it, the question it is emitted for gains
    an entry and this stops being true — which is the point.
    """
    unclaimed = {str(s) for s in ResultStatus} - _REFUSAL_WORDS - set().union(
        *_ANSWERS_WITH.values())
    assert unclaimed == {"needs_assumption"}, unclaimed
    for kind in _ANSWERS_WITH:
        with pytest.raises(VerificationError, match="was not put to it"):
            verify_answer_status_fits_its_question(
                {"status": "needs_assumption", "query_kind": kind})


@pytest.mark.parametrize("kind", sorted(_ANSWERS_WITH))
def test_a_refusal_word_is_open_to_every_question(kind):
    """The half that must NOT refuse. A question that cannot be answered
    is a thing every question can be."""
    for word in sorted(_REFUSAL_WORDS):
        verify_answer_status_fits_its_question(
            {"status": word, "query_kind": kind})


def test_a_block_that_is_present_and_empty_is_read_both_ways():
    """The counterexample each reading has to give the opposite answer on.

    A confidence region that came back unbounded is a block holding the
    statement that these data do not constrain the effect. Read as a number
    it makes the denial refuse an honest answer; read as nothing it makes
    the promise refuse one. So it is neither: certainly nothing, possibly
    something, and each half asks the reading that errs toward accepting.
    """
    empty = {"extensions": {"anderson_rubin_region": {"region": {}}}}
    assert _shown(empty) == frozenset()
    assert _might_be_showing(empty) == frozenset({Shown.NUMBER})

    # The denial that would fire if the block were read as a number, and
    # the promise that would fire if it were read as nothing. Neither may.
    verify_answer_status({**empty, "status": "needs_investigation"})
    verify_answer_status({**empty, "status": "numerically_solved"})

    # And with the block gone, both of those become refusals again — so
    # what is being accepted above is the block and not the leniency.
    with pytest.raises(VerificationError, match="claims"):
        verify_answer_status({"status": "numerically_solved"})
