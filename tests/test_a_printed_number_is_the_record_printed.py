"""A number a gap prints is the record, printed the way the sentence prints it.

A ``said`` value travels rendered. The contract says why: the rule that
renders it would otherwise have to run on surfaces that cannot run it, so
the kernel prints once and ships the printing. What follows from that, and
what nobody had drawn, is that the printing is then the WHOLE of what a
reader is given -- and a printing can be printed again.

The three questions this module already asked of a slot are membership:
of a roster, of the record another slot names, of what this gap writes
elsewhere. A diagnostic number answers none of them. It is not a member of
anything; it is a formatting of one number that is on this envelope under
its own name, and the machine for that has been here since a transport
formula needed it -- with one row, and a refusal written about estimands,
which is a sentence no second row could have raised.

So the sentence is about printings now, the reader is split from the
speller, and the numbers a reader weighs an IV answer or an overlap
diagnosis against are held to the records they came from.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import _PRINTED_FROM

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))
UNWITNESSED = json.loads(
    (FIXTURES / "unwitnessed_leaves.json").read_text(encoding="utf-8"))

#: The rows this file was written against, as (sentence, slot). The entry
#: keyed ``None`` for its sentence is the transport formula's, which was
#: here first and is exercised by its own file.
THE_ROWS = frozenset(_PRINTED_FROM) - {
    ("the_source_populations_stratified_conditional_is_missing", "formula")}
ROW_COUNT = 10


def _sentences(result):
    """Every (sentence, said) a gap report speaks, wherever it speaks it."""
    out = []

    def walk(node):
        if isinstance(node, dict):
            if isinstance(node.get("sentence"), str) and isinstance(
                    node.get("said"), dict):
                out.append((node["sentence"], node["said"]))
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(result.get("data_gap_report"))
    return out


def _speaking(row):
    """Every stored answer whose report speaks this row's sentence and slot."""
    sentence, slot = row
    return sorted(
        name for name, pair in SHAPES.items()
        if any(s == sentence and slot in said
               for s, said in _sentences(pair["result"])))


WHO_SPEAKS = {row: _speaking(row) for row in THE_ROWS}


def test_the_table_is_the_size_this_file_was_written_against():
    assert len(THE_ROWS) == ROW_COUNT, sorted(THE_ROWS)


def test_no_row_is_one_this_corpus_never_reaches():
    """A row nothing speaks reads from outside like a row that found
    nothing wrong, which is the defect this repository keeps naming. Not a
    claim that the sentence is unreachable -- a claim that nothing here
    would notice if the reading were wrong."""
    unreached = sorted(row for row, who in WHO_SPEAKS.items() if not who)
    assert unreached == [], unreached


# ------------------------------------------------------- the printing is held


@pytest.mark.parametrize("row", sorted(THE_ROWS))
def test_a_moved_printing_is_refused(row):
    """Every row, on every answer that speaks it.

    The forgery is a digit, not a word: what a reader takes from `F = 4.96`
    is the number, and a sentence that reaches them with `49.6` in it has
    told them the first stage was strong.
    """
    sentence, slot = row
    for name in WHO_SPEAKS[row]:
        pair = SHAPES[name]
        result = copy.deepcopy(pair["result"])
        moved = 0
        for spoken, said in _sentences(result):
            if spoken == sentence and slot in said:
                said[slot] = said[slot] + "9"
                moved += 1
        assert moved, (row, name)
        with pytest.raises(VerificationError, match="prints"):
            themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("row", sorted(THE_ROWS))
def test_an_emptied_printing_is_refused(row):
    """And the emptiest forgery there is, which a membership test passes
    wherever the roster it consults came back empty."""
    sentence, slot = row
    for name in WHO_SPEAKS[row]:
        pair = SHAPES[name]
        result = copy.deepcopy(pair["result"])
        for spoken, said in _sentences(result):
            if spoken == sentence and slot in said:
                said[slot] = ""
        with pytest.raises(VerificationError, match="prints"):
            themis.verify_answer_claims(pair["program"], result)


@pytest.mark.parametrize("row", sorted(THE_ROWS))
def test_the_printing_and_the_record_agree_today(row):
    """The premise, stated rather than assumed."""
    sentence, slot = row
    read = _PRINTED_FROM[row][1]
    for name in WHO_SPEAKS[row]:
        pair = SHAPES[name]
        said = next(s for spoken, s in _sentences(pair["result"])
                    if spoken == sentence and slot in s)
        printed = read(pair["result"], None, said)
        assert printed, (row, name)
        assert said[slot] in printed, (row, name, said[slot], printed)


#: The record each row prints, by the road to it. Written here and not
#: read off the table, because a test that asked the rule where it looked
#: would be asking the thing under test to grade itself.
THE_RECORD = {
    ("the_first_stage_is_weak", "f"):
        ("numeric_estimate", "first_stage_f_stat"),
    ("the_overidentification_test_refuted_the_instruments", "j"):
        ("numeric_estimate", "over_identification", "hansen_j"),
    ("the_overidentification_test_refuted_the_instruments", "df"):
        ("numeric_estimate", "over_identification", "hansen_dof"),
    ("the_overidentification_test_refuted_the_instruments", "p"):
        ("numeric_estimate", "over_identification", "hansen_p_value"),
    ("the_homoskedastic_sargan_says_the_same", "j"):
        ("numeric_estimate", "over_identification", "sargan_j"),
    ("the_homoskedastic_sargan_says_the_same", "p"):
        ("numeric_estimate", "over_identification", "sargan_p_value"),
    ("every_stratum_should_have_both_arms_and_some_do_not", "cells"):
        ("numeric_estimate", "stratum_support", "cells"),
    ("every_stratum_should_have_both_arms_and_some_do_not", "share"):
        ("numeric_estimate", "stratum_support", "extrapolated_share"),
    ("every_stratum_should_have_both_arms_and_some_do_not", "bad"):
        ("numeric_estimate", "stratum_support", "supported"),
    ("the_composite_confidence_is_below_the_threshold", "confidence"):
        ("confidence",),
}


def test_every_row_says_which_record_it_prints():
    assert set(THE_RECORD) == set(THE_ROWS), (
        set(THE_RECORD) ^ set(THE_ROWS))


@pytest.mark.parametrize("row", sorted(THE_ROWS))
def test_a_moved_record_is_refused_too(row):
    """The other direction, and the half that makes this worth doing.

    A printing held to a record refuses a moved printing AND a moved
    record. Which of the two a forger touched is not something the
    comparison needs to know, and it is why closing a printing closes the
    number behind it: the support table's three fields left the declared
    remainder with the three sentences that print them.
    """
    path = THE_RECORD[row]
    for name in WHO_SPEAKS[row]:
        pair = SHAPES[name]
        result = copy.deepcopy(pair["result"])
        node = result
        for step in path[:-1]:
            node = node[step]
        was = node[path[-1]]
        # Inside whatever range the contract declares for the field. A
        # probability bent past one is refused by the schema before any
        # rule runs, and a test that took that for this rule's refusal
        # would be pinning the contract and calling it a printing.
        if isinstance(was, bool) or not isinstance(was, (int, float)):
            pytest.fail(f"{row}: the record is {was!r}")
        elif isinstance(was, int):
            node[path[-1]] = was + 7
        elif 0.0 <= float(was) <= 1.0:
            node[path[-1]] = 0.5 if abs(float(was) - 0.5) > 0.01 else 0.25
        else:
            node[path[-1]] = float(was) * 3 + 1
        with pytest.raises(VerificationError, match="prints"):
            themis.verify_answer_claims(pair["program"], result)


def test_a_reader_with_no_record_is_told_nothing():
    """Silent rather than refusing where the record is not there.

    An answer can speak one of these sentences with the block it prints
    from absent -- a gap is filed by whichever pass found the shortfall,
    and the passes do not all write the same blocks. A rule refusing there
    would be refusing a report for the shape of the answer around it.
    """
    for row in sorted(THE_ROWS):
        read = _PRINTED_FROM[row][1]
        assert read({}, None, {}) == set(), row


# --------------------------------------------------------- declared silences


def test_what_this_table_leaves_out_is_written_down():
    """Three kinds of slot are not here, and the module says which and why.

    A table that simply stopped where its author's patience did is one
    nobody can tell from a complete one.
    """
    blob = (pathlib.Path(__file__).parent.parent / "themis" / "verifier"
            / "gap_claim_rules.py").read_text(encoding="utf-8")
    for saying in ("a table with a silence in it",
                   "PROGRAM's side channel",
                   "print a CONSTANT of the check",
                   "in the wire form a chain is written in"):
        assert saying in blob, saying


def test_the_learned_graphs_provenance_is_on_no_answer():
    """Why the three discovery sentences are out of reach, measured.

    They tell a reader which algorithm learned the graph, at what level
    and on how many rows. The record all three print is the caller's own
    side channel, and no answer that speaks them carries it -- so a reader
    holding the answer has the sentence and nothing to hold it to, and
    neither has anything here.

    The printed WORD does turn up elsewhere on such an answer, in the
    assumption ledger, because the ledger quotes the same statement. That
    is a second printing rather than the record: two renderings agreeing
    says the producer wrote one value into both, and says nothing about
    what the value was.
    """
    spoken = 0
    for name, pair in SHAPES.items():
        sentences = {s for s, _ in _sentences(pair["result"])}
        if not sentences & {"the_graph_was_learned_by_an_algorithm",
                            "the_edge_was_learned_by_discovery",
                            "discovery_ran_on_this_many_rows",
                            "discovery_used_this_significance_threshold"}:
            continue
        spoken += 1
        assert (pair["program"].get("extensions") or {}).get(
            "discovery_metadata"), name
        assert (pair["result"].get("extensions") or {}).get(
            "discovery_metadata") is None, name
        # And the gap says so itself: it cites the program site the record
        # is at, which is a pointer at something this envelope does not
        # carry a copy of.
        assert "program:extensions.discovery_metadata" in json.dumps(
            pair["result"].get("data_gap_report"), ensure_ascii=False), name
    assert spoken, "no answer speaks a discovery sentence any more"


# ----------------------------------------------------------- nothing else moved


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_stored_answer_is_refused(shape):
    themis.verify_answer_claims(
        SHAPES[shape]["program"], SHAPES[shape]["result"])
