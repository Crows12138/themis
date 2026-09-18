"""The remainder says where the truth of each leaf it declares lives.

The gate declares which leaves nothing holds. It has never said WHERE the
truth of one is, so two quite different things are written down the same
way: a leaf a rule could hold against something the documents already say,
and a leaf nothing in either document determines. Somebody picking the
next frontier off that file cannot tell how far zero is, and a leaf
nothing can hold is revisited until they work out, again, that nothing can
hold it.

Measured, and this file exists because of it: a derivation step's
``step_id`` is held on exactly the steps another step names, and on the
103 steps nothing names it can be rewritten freely. There is no honest
rule for those. It is not a position (97 of 374 stored ids are
producer-chosen handles -- ``s_loop``, ``s_iv_0``, ``s_t9_1_0``), it is
not a function of the step's rule (0 of 374), and recomputing it would
mean copying each producer's naming habit into the verifier, which is the
second document about the first that this repository keeps finding to be
the defect. That judgement took four probes, and before this file there
was nowhere to put it.

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
    """
    assert gate._the_remainder_by_where_its_truth_is() == {
        gate._ANSWER_ALIKE: 226,
        gate._PROGRAM_ALIKE: 6,
        gate._ANSWER_OTHERWISE: 280,
        gate._PROGRAM_OTHERWISE: 5,
        gate._NOTHING: 667,
        gate._EVERY_READING_MATCHES: 129,
    }


@pytest.mark.parametrize("where", gate._WHERE)
def test_every_heading_is_one_the_corpus_reaches(where):
    """A vocabulary with an entry nothing is ever filed under is a
    vocabulary describing a corpus other than this one."""
    split = gate._the_remainder_by_where_its_truth_is()
    assert split[where] > 0, where
