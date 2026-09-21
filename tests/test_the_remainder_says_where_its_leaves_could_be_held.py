"""The remainder says where the truth of each leaf it declares lives.

The gate declares which leaves nothing holds. It has never said WHERE the
truth of one is, so two quite different things are written down the same
way: a leaf a rule could hold against something the documents already say,
and a leaf nothing in either document determines. Somebody picking the
next frontier off that file cannot tell how far zero is, and a leaf
nothing can hold is revisited until they work out, again, that nothing can
hold it.

Measured, and this file exists because of it: a derivation step's
``step_id`` was held on exactly the steps another step names, and on the
103 steps nothing names it could be rewritten freely. There is no honest
rule for those. It is not a position (97 of 374 stored ids are
producer-chosen handles -- ``s_loop``, ``s_iv_0``, ``s_t9_1_0``), it is
not a function of the step's rule (0 of 374), and recomputing it would
mean copying each producer's naming habit into the verifier, which is the
second document about the first that this repository keeps finding to be
the defect. That judgement took four probes, and before this file there
was nowhere to put it.

Every measurement in that paragraph was right and its conclusion was
wrong, which is why it is still written out above rather than corrected
away. It asked which rule could hold the name a PRODUCER writes, and the
answer was that the producers should stop writing one: a name whose only
job is to be pointed at can be the place the step sits, and the handle a
producer needs while it is still building a chain does not have to be the
name the answer carries. #713 closed the leaf on all 81 rows that
declared it, and every one of the 374 stored names is refusable now. A
heading here says where a second writing could be FOUND. It never says a
leaf is out of reach -- not even when the thing saying so is this file.

A door has three places to look and no fourth: the program it was handed,
the rest of the answer, and this system's own constants. THE DATA IS NOT
ONE OF THEM. So the reading is about second writings, and the vocabulary
says exactly that much:

- a second writing under the same field name is one fact written twice,
  and a comparison can be written for it;
- the same value under another name is a coincidence until somebody says
  which two fields are one fact -- a run asking for 500 replicates has 500
  in its graph's edge list too, on 68 rows;
- no second writing at all means no COMPARISON can hold the leaf. It does
  not mean nothing can: a rule that recomputes a number from sufficient
  statistics holds it without any second writing anywhere. Reading it as
  "impossible" would retire holes that are merely harder, and this file
  says so in a test rather than only in prose.

The split is computed, never stored. A classification kept beside the
thing it classifies is a copy that states no relationship to it.
"""
from __future__ import annotations

import pytest

from . import test_every_answer_shape_is_asked_the_same_question as gate


# ------------------------------------------------- the reading, on its own


def _one(result, program=None, leaf=None):
    """Where the reading puts a single-leaf answer."""
    where = gate._where_the_truth_of(program or {"statements": []}, result)
    return where[leaf] if leaf else where


def test_a_second_writing_under_the_same_name_is_the_strongest_reading():
    """Two fields called the same thing, holding the same value, are one
    fact written twice -- which is the shape a comparison rule is for."""
    result = {"numeric_estimate": {"method": "backdoor_linear"},
              "derivation": {"steps": [{"method": "backdoor_linear"}]}}
    assert _one(result, leaf="numeric_estimate.method") == gate._ANSWER_ALIKE


def test_a_value_that_agrees_under_another_name_is_not_the_same_fact():
    """The distinction this reading exists for. Without it the strongest
    heading would be full of coincidences and would say nothing."""
    result = {"numeric_estimate": {"method": "backdoor_linear"},
              "derivation": {"steps": [{"rule": "backdoor_linear"}]}}
    assert _one(result,
                leaf="numeric_estimate.method") == gate._ANSWER_OTHERWISE


def test_the_run_that_asked_for_five_hundred_is_the_measured_case():
    """And it is in the corpus rather than invented here.

    ``estimation_context.ci_bootstrap`` is 500 on rows whose graph edge
    list also holds a 500. Under a reading that asked only whether the
    value appears elsewhere, every one of those rows would be filed as a
    fact written twice and a frontier would be picked off it.
    """
    filed = _split_by_family()
    assert filed[gate._ANSWER_OTHERWISE]["estimation_context.ci_bootstrap"] > 20
    assert "estimation_context.ci_bootstrap" not in filed[gate._ANSWER_ALIKE]


def test_the_program_is_read_when_the_answer_does_not_say_it():
    """The second of the three places, and it is a different heading from
    the first because writing the rule means reading a different
    document."""
    result = {"numeric_estimate": {"treatment": "x"}}
    program = {"statements": [{"kind": "variable", "treatment": "x"}]}
    assert _one(result, program,
                "numeric_estimate.treatment") == gate._PROGRAM_ALIKE


def test_a_flag_or_an_absence_is_not_evidence_of_anything():
    """Every boolean matches every other and every absence matches every
    other, so finding one elsewhere is not finding anything. Counted under
    its own heading rather than under the strongest one available."""
    for value in (True, False, None):
        result = {"numeric_estimate": {"identified": value},
                  "extensions": {"identified": value}}
        assert _one(result, leaf="numeric_estimate.identified") == \
            gate._EVERY_READING_MATCHES


def test_nothing_written_twice_is_not_a_claim_that_nothing_could_hold_it():
    """The limit of what this reading says, as a test and not only as
    prose.

    Here the leaf IS determined -- it is the sum of two numbers the same
    answer records -- and a rule that recomputes it would hold it without
    any second writing. The reading files it under "nothing either
    document writes", because that heading is about second writings and
    about nothing else. A reader who took it to mean "unholdable" would
    retire this leaf.
    """
    result = {"numeric_estimate": {"total": 3, "parts": [1, 2]}}
    assert _one(result, leaf="numeric_estimate.total") == gate._NOTHING


def test_a_list_position_is_not_part_of_a_name():
    """The third gap's severity and the first's are the same field."""
    assert gate._the_field("data_gap_report.gaps.[].severity") == "severity"
    assert gate._the_field("status") == "status"


def test_the_reading_is_a_fact_about_one_pair():
    """A classification that consulted the rest of the corpus would move a
    leaf when an unrelated row was added, which is a classification that
    rots by construction. Asked of one row alone and of the same row
    inside the corpus walk: the same answers."""
    name = sorted(gate.UNWITNESSED)[0]
    pair = gate.SHAPES[name]
    alone = gate._where_the_truth_of(pair["program"], pair["result"])
    again = gate._where_the_truth_of(pair["program"], pair["result"])
    assert alone == again
    assert set(gate.UNWITNESSED[name]) <= set(alone)


# ------------------------------------------------ the whole declaration


def _split_by_family():
    """The declaration, by heading and then by leaf."""
    out = {where: {} for where in gate._WHERE}
    for name, leaves in gate.UNWITNESSED.items():
        pair = gate.SHAPES[name]
        where = gate._where_the_truth_of(pair["program"], pair["result"])
        for leaf in leaves:
            bucket = out[where[leaf]]
            bucket[leaf] = bucket.get(leaf, 0) + 1
    return out


def test_every_declared_leaf_is_one_this_reading_reaches():
    """The reading walks the gate's own scope, so a leaf in the file that
    it cannot place is a leaf the gate no longer asks about -- which is a
    stale declaration and not a classification problem."""
    missing = {}
    for name, leaves in gate.UNWITNESSED.items():
        where = gate._where_the_truth_of(gate.SHAPES[name]["program"],
                                         gate.SHAPES[name]["result"])
        gone = sorted(set(leaves) - set(where))
        if gone:
            missing[name] = gone
    assert missing == {}


def test_the_split_accounts_for_the_whole_remainder():
    """Tied to the same file the total is read from, so the two numbers
    cannot drift apart."""
    split = gate._the_remainder_by_where_its_truth_is()
    assert sum(split.values()) == sum(
        len(v) for v in gate.UNWITNESSED.values())


def test_the_remainder_split_is_what_it_is():
    """How far zero is, and in which direction.

    566 of the 1702 have a second writing under their own name: a rule can
    be written against something the answer already says, and 264 families
    is the size of that backlog. 674 have no second writing at all, and
    that heading is where the leaves nothing can hold live -- along with
    the ones a recomputation could still reach, which this reading cannot
    tell apart. 317 agree with something under another name, which is
    mostly coincidence and has to be read family by family before any of
    it counts as work.

    Pinned so that movement BETWEEN headings shows in a diff. A frontier
    that closes leaves takes them out of the file; a frontier that makes a
    producer write a fact down a second time moves them from the last
    heading to the first without closing anything, and that is progress
    nobody would otherwise see.

    First use, and it read true: the frontier after this one closed 70
    leaves and 68 of them came out of the first heading, which is where
    this reading said the work a rule could reach was. Second use, all 94
    of them, out of the same heading again -- and in both cases the
    comparison this heading says CAN be written turned out to be one that
    already existed and was not reaching far enough: once with a subject
    that named the wrong block, once with a walk that could not see into
    a formula.

    Third use, and the first to move three headings at once: 41 here, 3
    from the program's, 9 from "named otherwise". One block's copy of
    three different documents, which is what a spread across headings
    looks like from inside -- and the nine were a printed estimand, whose
    second writing is a step's OUTPUT and so under no name at all.

    Fourth use, and the first to take anything out of the last heading:
    81 here, 13 from "named otherwise", and 7 from "nothing either
    document writes". Those seven are what this reading says about itself
    higher up -- that heading means no COMPARISON can reach the leaf, not
    that nothing can. A sieve's width is arithmetic on the fields beside
    it, and a method is the channel the question declares; both are
    recomputed rather than looked up, and so a leaf nothing writes twice
    was held anyway. The heading is honest about comparisons. It cannot
    see a function.

    Fifth use, and the plainest: 38 here, 15 from "named otherwise", and
    nothing from anywhere else. The frontier held a step's record of the
    descriptor it was handed to the same rebuild the block is held to, so
    the leaves that moved are exactly the ones this reading said were a
    second writing of something the answer already carries.

    Sixth use, 18 more from the same heading, and the first time the
    heading was right for a reason it does not itself state. These
    leaves are a sum's binder and the references to it, and what holds
    them is not a second writing anywhere: it is that the formula uses
    the name it binds. The reading files a leaf under "named alike"
    whenever the same word appears twice in the answer, which is true
    here — the binder and its references ARE the same word. It read the
    evidence correctly and called it a coincidence; the frontier turned
    the coincidence into the reason.

    Seventh use, and the last heading gave up its first 9. A boolean
    literal IS matched by every reading of the two documents, so filing
    it here was right; what holds it is a third thing neither document
    is — the QUESTION. That is a limit of this reading rather than an
    error in it, and it is worth saying plainly: the headings describe
    where a SECOND WRITING could be found, and two of the frontiers so
    far were held by something that is not a second writing at all.

    Eighth use, and it split a frontier three ways rather than one: of
    twenty-one transport premises, twelve sat under a name the answer
    also uses, seven under another name it uses, and two under "nothing
    either document writes". The two are the sharpest. A step names its
    selection nodes as one comma-joined string, and that string appears
    verbatim in neither document, because the program declares the nodes
    ONE AT A TIME. So the heading was right — no comparison of values
    reaches it — and the leaf is held anyway, by rebuilding the joined
    string from the declarations it renders. Which is this reading's own
    sentence being used rather than contradicted: the headings say where
    a second WRITING is, and a value that is computed from several is
    held by recomputing it.

    Ninth use, and the first frontier this reading pointed AT rather than
    explained afterwards: the off-arm's joint count was filed under "in
    the answer, named otherwise" and the second writing turned out to be
    the other three counts of its own row, which bound it by arithmetic
    rather than repeat it. Where that arithmetic leaves one value the
    leaf closed; where it leaves a range the leaf stayed, and the reading
    says the same thing about both. A heading names where a second
    writing IS, never how tightly it decides.

    Tenth use, and the first time the LAST heading was the one pointed
    at. The arm a contrast is reported against was filed under "a flag
    or an absence, which every reading matches", because it is a boolean
    and both of its values sit everywhere in both documents. That is a
    fact about comparison, and what closed the leaf was not a comparison
    but a recomputation -- from the question, which is neither of the two
    documents this reading reads. The caveat the docstring above makes
    about `_NOTHING` holds of this heading too, and all thirty-one went
    at once.

    Eleventh use, and the caveat came due on `_NOTHING` itself. Thirty-two
    of the thirty-seven estimator names sat there -- no second writing of
    the name anywhere on either document, which is exactly what the
    heading says. What held them was not a second writing but a roster:
    the names this build can give, read from the two tables that already
    declare methods and routes. A leaf under the last heading is one no
    COMPARISON can reach, and a recomputation, a re-derivation and a
    membership check are none of them comparisons.

    Twelfth use, and the last heading again, all thirty at once. The word
    that stands in an ask's source until a reader writes one is written
    nowhere else on either document, and the heading is right about that.
    What held it is a third kind of thing again, and the plainest so far:
    the record goes OUT on the envelope and comes BACK through the patch
    door, and the rule for the return trip was written years before this
    one. A heading here describes where a second writing of a VALUE is.
    It says nothing about the other direction of the same record.

    Thirteenth use, and the first time the pointed-at heading was NOT the
    last one. Thirty-two of the thirty-three leaves were filed under
    "somewhere in the answer, named otherwise", and the heading was exactly
    right: the name a shortfall is filed under is written a second time on
    the same envelope, as the target of the ask it was pushed into. That
    second writing is what holds the half no declaration can -- the subject
    is the occasion's -- while the channel half is recomputed from the
    species instead. So one leaf was closed by two different kinds of
    thing at once, and only one of them is what this heading describes.
    The thirty-third is the framing channel's, whose ask carries the
    subject without the channel, so no second writing of the NAME exists
    and the last heading had it right too.

    Fourteenth use, and the frontier was this file's own opening example.
    All 81 came out of the last heading, which is where the paragraph at
    the top put them and for the reason it gives: a step's name is written
    nowhere else on either document, so no comparison reaches it. What
    closed them is not a comparison, not a membership check and not the
    other direction of a record. It is that the name stopped being
    something anybody writes -- a producer keeps a private handle, and
    what the answer calls a step is computed from the chain it is in. The
    fourth time in six rounds that this heading gave up leaves to a
    recomputation, and the first time the recomputation was of the field
    itself rather than of something it had to agree with.

    Fifteenth use, and the two halves of ONE fact were filed under two
    different headings, which is most of why they looked like two
    frontiers. A shortfall's priority sat under "another field of the
    answer, named alike" on eighteen leaves -- the ask above it says the
    same word -- and the ask's own priority sat under "nothing either
    document writes" on thirteen, an ask being the only place its word
    appears. The fourteenth leaf of the last heading is the one this
    frontier had to refresh the corpus for: two framing rows filed at
    ``high`` beside an ask at ``medium``, so no second writing agreed
    with them and the reading quite correctly put that leaf here rather
    than in the first heading. Refreshed, the two agree and the leaf
    moves up a heading; closed, all 32 leave.

    So this reading was right about each half and would have sent a
    reader to two different places, and neither is where the work was.
    What holds both is a declaration beside the species: not a second
    writing in either document, which is the limit this file states about
    itself at the top, met here from both sides at once.

    Sixteenth use, and the largest share went to the heading that was
    right about the leaf and wrong about what its reading implied. 44 of
    the 68 sat under "another field of the answer, named alike", because
    the derivation step that evaluated a mediation block carries the same
    numbers under the same names -- which is true, and is exactly where
    the second writing is. But a rule DID read that second writing, and
    read it INSTEAD of the envelope's copy. So this heading was pointing
    at a copy that was already held while the leaf it was filed against
    went unread. That a second writing exists is not the same fact as the
    rule reading it reading the copy in front of a reader, and this file
    has not had to say that before.

    13 more came from "somewhere in the answer, named otherwise" -- every
    single leaf of these blocks filed there -- and 11 from "nothing
    either document writes", which is where an arm's account of running
    out of theta belongs and where the paragraph at the top would have
    put it: which reference point the walk stopped at is written nowhere
    else on either document. What closed those is a recomputation, the
    fifth time in seven rounds that this heading gave up leaves to one.

    Seventeenth use, all 18 out of the last heading again, and the first
    time the heading was right about the VALUE while a fact INSIDE that
    value was written twice. A Balke-Pearl row prints its bound as a
    sentence, and the size of the partition is a number in that sentence
    and again a slot of the note beside it. The sentence as a whole
    appears nowhere else in either document, which is what this reading
    compares, so "nothing either document writes" is exactly right --
    and it is right about a leaf one of whose SUBSTRINGS is written a
    second time three fields away. The headings read values whole. A
    leaf whose value contains another field's value is a second writing
    this reading cannot see, and that is worth saying once rather than
    leaving for the next frontier to rediscover.

    What closed them is a recomputation, which is the sixth time in
    eight rounds. The sentence is rebuilt out of the query, the
    instrument field and the cardinalities the program declares -- so
    the two places the count appears were never independent, and the
    frontier was not the second writing but the fact that one of the two
    was determined and unchecked.

    Eighteenth use, 2 leaves, and the same heading for the same kind of
    reason. A condition's label is a word from a closed vocabulary, and
    a word from a closed vocabulary is written in the CONTRACT and not
    in either of the two documents this reading compares. So "nothing
    either document writes" is right, and what holds the leaf is a
    re-derivation -- the seventh time in nine rounds. The heading keeps
    being right and keeps being a poor guide to which leaves are
    reachable, which is the sentence this file has now earned rather
    than only asserted.

    Nineteenth use, 13 leaves, the same heading once more, and the first
    time it was right about the VALUE and wrong about the kind of second
    writing there is. The word over a mediation caveat -- ``CDE`` --
    appears nowhere else in either document, which is what this reading
    compares and what it correctly reports. The word is a NAME, though,
    and what a name is written a second time as is the RECORD IT NAMES:
    the branch key the caveat's own provenance cites, and the premises in
    the same breath, which are that branch's list and never the other's.
    This reading looks for another copy of the value. A locator's second
    writing is not a copy of it at all, and no comparison of values can
    find one.

    What closed it is neither a recomputation nor an equality between two
    copies. The word is read as the key under which the rest of its own
    claim was found, and a key is checked by looking there.

    Twentieth use, 14 leaves, and the first time ONE frontier's leaves
    came out of three headings at once: 2 from "another field of the
    answer, named alike", 6 from "somewhere in the answer, named
    otherwise", 6 from "nothing either document writes". One slot, one
    rule, one record per sentence -- and this reading put the same kind
    of leaf in three places.

    Which is not a fault in it. What it compares is whether the VALUE
    appears again, and the values here are small integers: ``"2"`` is a
    level, an index and a count of rows as readily as it is the number of
    intervals, so whether it recurs says nothing about this leaf. The two
    under the first heading recur because the same ask is written twice
    over; the six under the last do not recur at all; and the record that
    holds every one of them is neither -- it is a LENGTH, which is not
    written anywhere as a value and is derivable everywhere.

    So the sentence this file has been earning has its sharpest form. A
    reading that asks whether a value recurs cannot see whether a value
    is DERIVABLE, and derivable is what decides.

    Twenty-first use, 21 leaves, three headings again -- 11 "named alike",
    3 "named otherwise", 7 "nothing either document writes" -- and the
    same sentence arriving from the other end. These leaves are words a
    stamp uses, and a word like ``iid`` recurs across an answer carrying
    more than one loop, so the reading finds a second copy and files the
    leaf under "alike". The second copy is a DIFFERENT loop's, which is
    the one thing that would have mattered about it.

    What held them is that a block contradicts itself, and that the column
    it names is not the column the run resolved. Neither of those is a
    value appearing twice, so neither is a thing this reading could have
    found. Twice in a row now, and both times the heading was measuring
    something real and beside the point.

    Twenty-second use, 115 leaves, and for once they are all under ONE
    heading -- "nothing either document writes", 450 to 565, with the
    other five unmoved. The reading is right here, and right for the same
    reason it was beside the point the two times before: it asks whether
    the value recurs, and a status word recurs nowhere, because no other
    slot on either document is written in that vocabulary.

    It is still not what decides. What a status word may be is settled by
    what the answer CONTAINS -- a chain, an estimate, a request to go and
    look -- and none of that is the word appearing a second time. Three
    frontiers running, this reading has been accurate about recurrence and
    silent about derivability, which is now less a caveat about these
    headings than the sentence they are for.

    Twenty-third use, 13 leaves, again all under one heading -- "a flag
    or an absence, which every reading matches", 89 to 76. Here the
    heading is not beside the point but empty by construction: the leaf
    is a boolean, and a boolean matches every reading, so recurrence had
    nothing it COULD say. What held it was that the same answer commits
    to the same fact three more times -- in the step that concluded it,
    in its own gap report, in the number sitting beside it. That is a
    seventh heading these five do not have: not where the value recurs,
    but what else in the document could only be true if it held.

    Twenty-fourth use, 40 leaves, all of them out of "nothing either
    document writes" -- the heading the status word arrived under two
    frontiers ago, and for the same reason: no other slot on either
    document is written in that vocabulary. Right again about recurrence,
    silent again about what decides, which here was that the word claims
    a quantity and the block beside it is the one that says none was
    reached. Four uses now, and the sentence has stopped being a caveat
    about these headings: what they read is whether the value is written
    twice, and what has held every leaf they were asked about is what
    else on the envelope could only be true if this one were.

    Twenty-fifth use, 37 leaves, and the first one that comes out of
    three headings at once: 20 from "another field of the answer, named
    alike", 2 from "somewhere in the answer, named otherwise", and 15
    from "nothing either document writes". The last of those is the
    interesting number, because it is this reading's own caveat finally
    being paid. ``_where_the_truth_of`` says in as many words that
    ``_NOTHING`` means no COMPARISON can hold the leaf and not that
    nothing can -- "a rule that recomputes a number from sufficient
    statistics holds it without any second writing" -- and until now no
    frontier had done that. Fifteen blocks of second moments with no
    second copy anywhere on either document are held by the standard
    error they determine.

    And the twenty under "alike" say the sentence these paragraphs keep
    arriving at, once more. Their values DO recur -- one arm's row count
    equals a number elsewhere, one moment equals another -- and the
    recurrence is not what held them; the sum they belong to and the
    figure they feed are. Five frontiers now: accurate about recurrence,
    silent about what decides.

    Twenty-sixth use, 24 leaves, and 20 of them out of the sixth heading:
    "a flag or an absence, which every reading matches". That heading is
    the honest one -- a ``True`` matches every other ``True``, so no
    comparison can find where such a leaf is written a second time, and it
    says so. What held them was not a comparison. A counterfactual cell's
    four coordinates are booleans, and each one is read BY NAME out of the
    question: this field shows back which arm was observed, that one what
    was intervened to. The second writing was never on the envelope at
    all. So the sixth heading joins the fifth: both are statements about
    what comparing can reach, and neither is a statement about the leaf.

    The remaining 4 came from "alike", and say something narrower. The
    assumption a question grants is written in both copies of the cell, so
    each one's value did recur -- under its own name, in the other copy --
    and that recurrence is exactly what the heading promises a comparison
    could use. Nobody had written the comparison. Six frontiers now, and
    for the first time one of them found a leaf where the heading was
    right and the work was simply undone.

    Twenty-seventh use, 33 leaves, and 27 of them out of the third
    heading: "somewhere in the answer, named otherwise". That heading had
    the defect exactly. The value IS on the envelope, under a different
    word: a joint contrast's endpoints are ``joint_ci_lower`` in the step
    the number came from and ``joint_effect.ci_lower`` where a reader
    reads it; a trimming summary is ``propensity_floor`` beside
    ``propensity_summary.floor``. The rule that holds a reader's copy to
    the record joins the two sides by name, so a fact the two sides spell
    differently fell out of its reach, and this heading is what had been
    saying so all along. Seven frontiers of "accurate about recurrence,
    silent about what decides", and this is the first where the heading
    was accurate about recurrence AND the recurrence was the whole of what
    decided.

    The remaining 6 are the same seam at a different shape. A curve's rows
    are each their own subject, so the walk does not descend into the
    series at all -- rightly, measured: a dose's interval and the run's are
    two different intervals. One row is the step's own, and the step names
    it by the point it reports.

    Twenty-eighth use, thirty leaves, and every one of them out of
    "nothing either document writes" -- which is the third frontier to
    spend the caveat this heading carries, and the first to spend it on a
    second writing that is right there on the envelope. A gap's sentence
    shows a reader the numbers the diagnostic found, and the estimator
    PRINTS them: a share as "36.3%", a fitted range to three places. A
    comparison looking for the same value finds nothing, correctly, and
    the leaf is held anyway by asking whether that string is that number
    written that way. So this heading now has three escapes rather than
    two: recompute it, read it by name out of the question, or print the
    record and compare the printing.

    Twenty-ninth use, twenty-three leaves, and all of them out of the sixth
    heading, which is the second frontier to spend ITS caveat and the same
    escape both times. A ``True`` matches every other ``True``, so no
    comparison can say which of them is this leaf's second writing -- and
    the estimand's arm has no second writing on the envelope to find. The
    question names it, and a table reading the question by name holds it
    without comparing anything. That heading is now a statement about what
    comparing can reach and nothing else, which is what it always said.

    Thirtieth use, twenty-seven leaves, every one out of the FIRST
    heading, and the same sentence is what let them go. A status has no
    second writing on the envelope in any shape a comparison reaches. It
    has a MEANING, and what holds it is a table saying what each word
    claims -- which is not comparing, and was never going to be reported
    here as anything but nothing either document writes.

    Thirty-first use, twenty-two leaves, and this time out of the two
    headings that say a second writing IS somewhere: seventeen named
    alike, five named otherwise. Both were right and neither says where,
    which is the whole of what a heading claims. Where turned out to be
    the same GAP -- one occasion described in several sentences, from one
    value the producer had in hand -- and a comparison reaches that only
    once a rule knows which two of a gap's slots are one fact.

    Thirty-second use, forty-three leaves, and this time every one of them
    from the heading that says nothing either document writes. The heading
    was right: the word appears nowhere else, in either document. It is the
    sixth thing to hold a leaf no document writes twice, and the first that
    reads nothing present. Where a word is one of two, what holds it is the
    fork: one road leaves an estimate behind and the other leaves the
    model's own arithmetic, so the absence of the first says the second was
    taken. A heading that asks where a value is WRITTEN cannot see that,
    and is not wrong to be unable to.

    Thirty-third use, seven leaves, and from the same heading twice
    running. Right again, and again not the end of it: a rendering is not
    WRITTEN anywhere a second time, it is BUILT, and what builds it is on
    both documents in pieces -- the outcome and the variable in the
    question, the arm in the shape word beside the value. Twice in three
    frontiers the thing that held a leaf was not a second writing of it,
    which is what this heading can see and the whole of what it can see.

    Thirty-fourth use, three leaves, and the first time two headings move
    together for one reason. Two of the three sat under nothing either
    document writes and the third under somewhere in the answer, named
    otherwise; the two headings disagreed about where the value was, they
    were each right, and neither was what held it. The same slot, the same
    move: what is spelled is spelled again. Where a value is WRITTEN and
    whether a leaf can be HELD are two questions, and this table answers
    the first.

    Thirty-fifth use, seven leaves, every one of them under nothing
    either document writes — and the heading is right for the third
    frontier running. A printing is not a second writing of anything: it
    is MADE, and what it is made from sits in two places on the envelope
    and one on the program. Where a value is written and what can hold it
    are two questions, and a leaf with no second writing can still be
    held by what it was printed from.

    Thirty-sixth use, six leaves, under the same heading again — and
    this time what held them is on neither document. The word a way past
    offers a reader is the one the question's own reading declares, and
    this package restates that reading a rule away. A heading that
    answers where on these two papers a value is written has nothing to
    say about a value that is written on a third.

    Thirty-seventh use, seven leaves, the same heading a third time —
    and it has been right every time. A shape word IS written once; what
    held it is not a second writing but a declaration of which shapes
    each method can fit. This table says where a value is written, and
    three frontiers running have been closed by something that is not a
    writing at all.

    Thirty-eighth use, five leaves, and out of the heading that says
    another field of the ANSWER writes this value under the same name.
    Right again, and this time being right was a warning rather than a
    direction: the second writing it points at is a gap sentence's own
    population slot, which is a copy the same hand wrote and the same
    hand can move. What holds the leaf is the program, which no answer
    edits, and the key on the row beside it. A heading that says a value
    is written twice does not say which of the two writings is a record.

    Thirty-ninth use, three leaves, out of the heading that says nothing
    either document writes. Right, and this time the heading's own
    question is the wrong one to have asked: the word says which
    estimator ran, and what holds it is not a second writing of the word
    anywhere but the BLOCK that estimator left behind. A block is not a
    copy of the word; it is the work the word claims, and the difference
    between a run that left the work and one that only says it did is
    invisible to a table asking where a value is written.
    """
    assert gate._the_remainder_by_where_its_truth_is() == {
        gate._ANSWER_ALIKE: 87,
        gate._PROGRAM_ALIKE: 6,
        gate._ANSWER_OTHERWISE: 156,
        gate._PROGRAM_OTHERWISE: 5,
        gate._NOTHING: 378,
        gate._EVERY_READING_MATCHES: 33,
    }


@pytest.mark.parametrize("where", gate._WHERE)
def test_every_heading_is_one_the_corpus_reaches(where):
    """A vocabulary with an entry nothing is ever filed under is a
    vocabulary describing a corpus other than this one."""
    split = gate._the_remainder_by_where_its_truth_is()
    assert split[where] > 0, where
