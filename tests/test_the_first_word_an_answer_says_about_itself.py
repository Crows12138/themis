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

Three things can hold the word and the other two are here too. What the
envelope SHOWS stops where two words show the same thing — a
counterfactual point and an estimated one are one rung. What the question
ASKED separates them, and which words a question's answer may lead with is
declared beside the question (``themis.questions``' ``answers_with``),
while the words a REFUSAL leaves are open to every question and declared
once on ``refusals.Kind.outcome``.

And a roster keyed on the question is only as fine as the question is.
Four questions are about more than one world and have two roads to a
number — estimate it from data, or compute it from the structural model
the program itself declares — so their roster lists the words of both
roads and holds neither. Which ROAD an answer came by is the third thing,
read off the estimate the estimating road leaves behind.

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
- that the word is held to the road as well: the questions about more than
  one world are the questions' own, the word this rule calls the estimating
  road's is the one the estimation layer writes, and the case it must
  refuse and the two it must not are each put to it
- that the promise half is not satisfied by the block that exists to say
  a quantity was NOT reached, and that the one word whose answer may be
  that range still admits it — both sides put to honest answers
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
from themis.types import (
    A_QUANTITY, A_QUANTITY_OR_THE_RANGE_STANDING_IN,
    STATUS_CLAIMS, ResultStatus, Shown)
from themis.verifier import VerificationError
from themis.estimation import dispatch
from themis.verifier.status_rules import (
    _ACROSS_WORLDS, _ANSWER_BLOCKS, _ANSWERS_WITH, _REFUSAL_WORDS,
    _THE_ESTIMATORS_WORD, _might_be_showing, _shown, verify_answer_status,
    verify_answer_status_fits_its_question)

from . import schema_walk
from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

RULE = "answer_status_check"
RULE_QUESTION = "answer_status_question_check"
RULE_ROAD = "answer_status_road_check"

#: What one relabelling of every answer comes to. Stated so that a
#: narrowing shows up as a number: 1458 swaps, of which 673 survived both
#: doors before either rule, 246 after the envelope was read, 139 once the
#: question was too, and 119 once the report's tier was recomputed — the
#: status is one of the five things that recomputation reads, so a word
#: these two rules cannot tell apart is told apart by what the tier would
#: have to become (#588). The eight rows collected when the identifier
#: began answering a query conditioning on a descendant of the treatment,
#: less the refusal they replaced, made it 1500 and 124. Each of the five
#: new survivors relabels an identification as needing investigation, as
#: 19 already did.
SWAPS = 1512
SURVIVING = 11

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
#:
#: Twenty more went in #588, and to neither of these rules. The report's
#: TIER is recomputed now, and the status is one of the five things that
#: recomputation reads — ``outside_language`` says a question does not
#: stand, so no answer is available under it, and the two blocked statuses
#: say a point is not. A word these two rules cannot tell apart is told
#: apart by what the tier would have to become under it. That is what it
#: means for a field to select an audit: the fields it selects can hold it.
#:
#: Forty-one more went in #726, and to this rule's PROMISE half rather
#: than its denial — the half a first draft was warned off making finer.
#: ``A_QUANTITY`` offered three rungs as alternatives and two of them
#: were already implied by the third: a point sits in a block that holds
#: a quantity, and so does an estimate's interval. What the pair let in
#: was the one interval that is not a quantity at all —
#: ``bounds_results``, which the reading's own words call where an answer
#: that COULD NOT reach a point keeps what it did reach. So the word
#: saying a number arrived was satisfied by the block that says none did,
#: and 42 gap diagnoses holding nothing but Manski bounds could call
#: themselves numerically solved. Making the promise finer is what the
#: warning was about; this made it narrower without making it finer, and
#: the reading behind it is the same total one. The single survivor is
#: the diagnosis that also carries an answer block, where a quantity
#: really is on the envelope and what is wrong with the word is something
#: else.
#:
#: Twenty-seven more went in #733, and the paragraph three above this one
#: was half right for the wrong reason. Words a refusal leaves ARE open to
#: every question, so no roster narrows them — and the sentence stopped
#: there, as though a word no roster narrows is a word nothing holds. What
#: holds them is the other rule, and it could not, because the vocabulary
#: it reads in had nothing but rungs in it. A word that says the run did
#: not get there is not a claim about rungs; it is a claim about what is
#: to be done instead. ``Shown.ASK`` is that, and with it
#: ``outside_language`` denies an answer that says what is missing from
#: the question — eight of these — and ``needs_investigation`` promises
#: that something is missing, which nineteen answers carrying a settled
#: structure and its whole chain did not. The five that remain identify
#: and then refuse at the estimator for want of data, and this rule leaves
#: them alone on purpose: on those five the word would not be a lie.
#:
#: Forty-five more went in #735, and what reached them is the sentence
#: three paragraphs above being wrong about its own limit. Where a
#: question's answer may lead with either of two words that both say a
#: quantity arrived, nothing on the envelope separates them — true, and
#: the sentence went on to say that telling them apart would need the
#: derivation. It needs less than that. Four questions are about more than
#: one world, and a number for one of them is either estimated from data or
#: computed from the structural model the program itself declares: two
#: roads, and the word is which road this answer took. The estimating road
#: leaves an estimate behind, so the word naming it is asked for one — and
#: forty-three counterfactual points and two bounded ones stop being able
#: to call themselves numerically solved.
#:
#: What is left is eleven, of two shapes. Nine relabel into or out of a word
#: a refusal leaves, which is open to every question by construction. Two
#: are between the two words the computing road itself ends in, where the
#: roster admits both, the road is one, and the envelope shows a quantity
#: either way.
#: The questions with one world and one road, whose answers say the
#: estimating road's word without owing an estimate for it.
ONE_WORLD_QUESTIONS_ANSWERING_WITH_IT = sorted(
    kind for kind, words in _ANSWERS_WITH.items()
    if kind not in _ACROSS_WORLDS and _THE_ESTIMATORS_WORD in words)

SURVIVORS = {
    "counterfactual_bounded -> counterfactual_solved": 2,
    "needs_investigation -> numerically_solved": 1,
    "needs_investigation -> structurally_solved": 2,
    "numerically_solved -> needs_investigation": 1,
    "structurally_solved -> needs_investigation": 5,
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
    strongest door that reads it.

    What the door does, and not which rule said it. Two rules reading one
    field both refuse the same lie, and the one a caller hears is decided
    by the order the kernel runs its passes — so an attribution counted
    here measures that order. What each rule reaches is asserted below by
    calling it, where no other rule can get there first.
    """
    refused = survived = 0
    alive: dict[str, int] = {}
    for _name, program, honest, forged, was, now in _swaps():
        try:
            the_door_for(honest)(program, forged)
        except Exception:                                   # noqa: BLE001
            refused += 1
        else:
            survived += 1
            key = f"{was} -> {now}"
            alive[key] = alive.get(key, 0) + 1
    assert refused + survived == SWAPS, refused + survived
    assert survived == SURVIVING, survived
    assert alive == SURVIVORS, alive


def test_what_the_question_rule_reaches_on_its_own():
    """Same reason as the sibling below: most of its work happens behind
    other rules at the door, and a gate counting only what got through them
    would not notice this one going quiet.

    Both halves of it, because they are one function reading one envelope:
    sixty of these refusals are the road half, which is what the roster
    could not do and the estimate can.
    """
    refused = passed = 0
    for _name, _program, _honest, forged, _was, _now in _swaps():
        try:
            verify_answer_status_fits_its_question(forged)
        except VerificationError:
            refused += 1
        else:
            passed += 1
    assert (refused, passed) == (816, 696), (refused, passed)


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
    assert (refused, passed) == (1116, 396), (refused, passed)


@pytest.mark.parametrize("status,rung", [
    ("needs_investigation", Shown.POINT),
    ("outside_language", Shown.CHAIN),
    ("outside_language", Shown.ASK),
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


# --- the other axis: what is to be done instead --------------------------------


def _with(**fields):
    return {"status": "needs_investigation", "query_id": "q",
            "query_kind": "effect", **fields}


@pytest.mark.parametrize("field", ["investigation_requests",
                                   "missing_information"])
def test_an_ask_is_read_off_the_fields_whose_whole_content_is_one(field):
    """The denial's reading, and it is held to what is certainly there.

    Two fields carry an ask and nothing else does: one is the thing the
    kernel needed and did not have, the other is the action form of it.
    Neither is a rung, which is the point — a status that says the run got
    nowhere is not making a claim about rungs.
    """
    assert Shown.ASK in _shown(_with(**{field: [{"any": "row"}]}))
    assert Shown.ASK not in _shown(_with(**{field: []}))
    assert Shown.ASK not in _shown(_with())


def test_a_recorded_refusal_is_an_ask_to_the_promise_and_not_to_the_denial():
    """The two readings part company here, for the reason they always do.

    ``themis.refusals.Kind`` is in its own words what the reader should do
    about a refusal — change the graph, get other data, fix what was sent
    — so an envelope carrying one has told the reader what to do even
    where no ask was written out. That is enough to satisfy a promise and
    not enough to sustain a denial, which is the polarity the whole module
    is built on.
    """
    envelope = _with(estimator_failure={"kind": "data", "estimator": "e"})
    assert Shown.ASK not in _shown(envelope)
    assert Shown.ASK in _might_be_showing(envelope)


def test_a_question_with_no_representation_here_cannot_say_what_it_lacks():
    """``outside_language`` says the form of the question has no reading in
    this system yet. An answer that can name what is missing from the
    question has read it far enough for it to be inside the language."""
    forged = _with(status="outside_language",
                   investigation_requests=[{"action": "supply_input"}])
    with pytest.raises(VerificationError, match="says the run did not"):
        verify_answer_status(forged)


def test_a_word_that_sends_the_reader_away_says_where_to():
    """And the promise. An answer carrying a settled structure and the
    chain that reached it, naming nothing to go and find out, is not an
    answer that needs investigating — it is one that got there."""
    forged = _with(structural_result={"value": True},
                   derivation=[{"rule": "backdoor"}])
    with pytest.raises(VerificationError, match="claims"):
        verify_answer_status(forged)


#: The stored answers that identify cleanly and then refuse at the
#: estimator for want of data. The promise leaves them alone — on these
#: the word is not a lie — and the number is here so that a corpus which
#: stopped carrying the shape says so rather than reading as a win.
IDENTIFIED_THEN_REFUSED = 5


def test_the_answers_that_identify_and_then_refuse_keep_the_word():
    """The declared cost of reading a refusal as an ask, counted.

    Narrowing the promise to the two ask fields would close these five as
    well. It would also refuse a shape that is honest: identification
    succeeded, the estimator could not run on this sample, and "needs
    investigation" is a fair thing for such an answer to say.
    """
    kept = [name for name, row in SHAPES.items()
            if str(row["result"].get("status")) == "structurally_solved"
            and not row["result"].get("investigation_requests")
            and not row["result"].get("missing_information")
            and row["result"].get("estimator_failure") is not None]
    assert len(kept) == IDENTIFIED_THEN_REFUSED, sorted(kept)
    for name in kept:
        forged = copy.deepcopy(SHAPES[name]["result"])
        forged["status"] = "needs_investigation"
        verify_answer_status(forged)


#: How many stored answers hold a range and no quantity, and how many
#: say the run reached one. Both sides of the asymmetry, counted, so a
#: corpus that stopped exercising either says so here.
ANSWERS_HOLDING_ONLY_A_RANGE = 41
ANSWERS_SAYING_THE_RUN_GOT_THERE = 141


def test_the_two_rungs_the_promise_dropped_were_never_adding_to_it():
    """``POINT`` and ``INTERVAL`` sat in ``A_QUANTITY``, and one of them
    was the whole hole. A point is only ever read out of a block that
    holds a quantity, and so is an estimate's interval, so both imply
    ``NUMBER``. The single reading they added is the one interval that is
    not a quantity at all."""
    assert A_QUANTITY == frozenset({Shown.NUMBER})
    for envelope in ({"numeric_estimate": {"point": 1.0}},
                     {"numeric_result": {"value": 1.0}},
                     {"numeric_estimate": {"ci_lower": 0.0}},
                     {"numeric_result": {"interval": [0.0, 1.0]}}):
        assert Shown.NUMBER in _shown(envelope), envelope
    assert _shown({"bounds_results": [{}]}) == frozenset({Shown.INTERVAL})
    assert A_QUANTITY_OR_THE_RANGE_STANDING_IN == frozenset(
        {Shown.NUMBER, Shown.INTERVAL})


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_tells_the_old_reading_from_the_new_one(shape):
    """Which is what made the old set the second sentence under the first
    one's name: over every stored answer, "any of the three rungs" and "a
    number, or else a range" answer the same."""
    result = SHAPES[shape]["result"]
    might = _might_be_showing(result)
    three = frozenset({Shown.POINT, Shown.INTERVAL, Shown.NUMBER})
    assert bool(three & might) == (
        Shown.NUMBER in might or bool(result.get("bounds_results")))


@pytest.mark.parametrize("word", ["numerically_solved",
                                  "counterfactual_solved"])
def test_a_word_saying_the_run_got_there_is_not_satisfied_by_a_range(word):
    """The block that exists to say a quantity was not reached is not
    evidence that one was."""
    with pytest.raises(VerificationError, match="claims"):
        verify_answer_status({
            "query_id": "q", "query_kind": "effect", "status": word,
            "bounds_results": [{"lower_value": 0.1, "upper_value": 0.9}]})


def test_the_word_whose_answer_may_be_the_range_admits_it():
    """The asymmetry is the claim rather than a hedge: a bounded
    counterfactual reached bounds, and saying so is its answer."""
    verify_answer_status({
        "query_id": "q", "query_kind": "counterfactual",
        "status": "counterfactual_bounded",
        "bounds_results": [{"lower_value": 0.1, "upper_value": 0.9}]})


def test_both_sides_of_the_asymmetry_are_exercised_by_honest_answers():
    """A claim only a constructed envelope reaches is a claim about
    nothing this system builds."""
    only_a_range = sorted(
        name for name, row in SHAPES.items()
        if Shown.NUMBER not in _might_be_showing(row["result"])
        and row["result"].get("bounds_results"))
    assert len(only_a_range) == ANSWERS_HOLDING_ONLY_A_RANGE
    assert {SHAPES[n]["result"]["status"] for n in only_a_range} == {
        "needs_investigation"}
    got_there = sorted(
        name for name, row in SHAPES.items()
        if row["result"].get("status") in ("numerically_solved",
                                           "counterfactual_solved"))
    assert len(got_there) == ANSWERS_SAYING_THE_RUN_GOT_THERE
    assert all(Shown.NUMBER in _might_be_showing(SHAPES[n]["result"])
               for n in got_there)


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


def test_the_questions_about_more_than_one_world_are_the_questions_own():
    """The same pin, on the other fact this rule reads off the question.

    Both directions, and they fail differently. A question that gains the
    property and not an entry leaves its answers unheld by the road half;
    an entry no question carries asks a single-world answer for an estimate
    it never owed.
    """
    assert _ACROSS_WORLDS == {q.kind for q in questions.DECLARED
                              if q.asks_across_worlds}


def test_the_word_this_rule_calls_the_estimating_roads_is_written_there():
    """Named in the verifier, written in the estimation layer.

    Every road that attaches a number for the query's own estimand ends in
    one finaliser, and that finaliser is what puts a word on an envelope
    when data produced the number. Called rather than read, so a rename
    arrives here as a red suite instead of as a rule that stopped holding.
    """
    envelope: dict = {}
    dispatch._finalise_numeric_result(envelope)
    assert envelope["status"] == _THE_ESTIMATORS_WORD


def test_an_across_world_answer_the_program_settled_itself_keeps_its_word():
    """The honest shape this must never touch: an SCM counterfactual is
    computed from the coefficients the program declares and estimates
    nothing, so there is no estimate to ask it for."""
    verify_answer_status_fits_its_question(
        {"status": "counterfactual_solved",
         "query_kind": "scm_counterfactual"})


def test_the_estimating_roads_word_is_asked_for_the_estimate_it_names():
    """The counterexample. Both words say a quantity arrived and the roster
    admits both, so what road it came by is the only thing left that can
    tell a reader which answer they are holding."""
    with pytest.raises(VerificationError, match="came from data") as err:
        verify_answer_status_fits_its_question(
            {"status": _THE_ESTIMATORS_WORD,
             "query_kind": "scm_counterfactual"})
    assert err.value.rule == RULE_ROAD


def test_the_estimating_roads_word_is_kept_where_the_estimate_is_there():
    """The half that must NOT refuse: a counterfactual cell estimated from
    data leads with this word, and nine stored answers do."""
    verify_answer_status_fits_its_question(
        {"status": _THE_ESTIMATORS_WORD, "query_kind": "scm_counterfactual",
         "numeric_estimate": {"method": "scm_counterfactual_linear_fit"}})


def test_the_one_world_questions_this_word_is_open_to():
    """The roster the case below is parametrized over, counted here: a
    parametrize that has gone empty is a green test asking nothing."""
    assert ONE_WORLD_QUESTIONS_ANSWERING_WITH_IT == [
        "effect", "probability", "proximal_effect"]


@pytest.mark.parametrize("kind", ONE_WORLD_QUESTIONS_ANSWERING_WITH_IT)
def test_a_question_about_one_world_is_not_asked_for_an_estimate(kind):
    """Nineteen stored answers evaluate an identified formula on declared
    parameters, lead with this word and estimated nothing. A question with
    one road to a number needs no word to say which road."""
    verify_answer_status_fits_its_question(
        {"status": _THE_ESTIMATORS_WORD, "query_kind": kind})


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
    #
    # The first word promises an ask as well, which is a claim on the
    # other axis and not what is under test here, so the envelope is given
    # one. An envelope assembled to exercise one half of a rule stops
    # being a probe for it the day the other half gains a requirement, and
    # what is wanted then is the missing half supplied rather than the
    # claim weakened.
    asked = {**empty, "investigation_requests": [{"action": "supply_input"}]}
    verify_answer_status({**asked, "status": "needs_investigation"})
    verify_answer_status({**empty, "status": "numerically_solved"})

    # And with the block gone, both of those become refusals again — so
    # what is being accepted above is the block and not the leniency.
    with pytest.raises(VerificationError, match="claims"):
        verify_answer_status({"status": "numerically_solved"})
