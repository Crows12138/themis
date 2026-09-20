"""A count a gap spells is a count of something this answer lists.

Two gaps put a number in front of a reader: several intervals bound one
quantity, and an instrument was offered with no monotonicity declared.
Both numbers were unheld, and the roster holding the rest of a gap gave a
reason for numbers -- a RENDERED number, ``36.3%`` for 0.363, is not
equal to anything on the envelope, because a rendering puts a formatting
step between the value and its spelling.

True of a rendering. These are not renderings. ``"2"`` is ``str`` of a
length, and the thing it is the length of is on the same envelope: the
intervals this answer reports, the instruments its graph admits. The
reason belonged to the rendering and was read as belonging to the number.

Underneath the second one was a blindness worth its own tests. This
module reads the question's two ends TWICE -- once off the parsed query
for the rosters that copy it, once off the program document -- and
neither copy knew that a counterfactual query spells them
``counterfactual_intervention`` and ``counterfactual_target``. Both were
silent on every counterfactual answer, and silent about being silent.
The spellings are one list now, read by three readers.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis import kernel
from themis.verifier import gap_claim_rules as _rules

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))

#: The two sentences whose count this file is about.
INTERVALS = "several_intervals_bound_the_same_quantity"
INSTRUMENTS = "iv_monotonicity_undeclared"


def _counts():
    """Every count under a report: where it sits and what says it."""
    for name in sorted(SHAPES):
        report = SHAPES[name]["result"].get("data_gap_report")
        if not isinstance(report, dict):
            continue
        for where, sentence, said in _rules.every_said_mapping(report):
            if "count" in said:
                yield name, where, sentence, said


COUNTS = tuple(_counts())
IDS = tuple(f"{n}:{w}" for n, w, _s, _d in COUNTS)
OURS = tuple(row for row in COUNTS if row[2] in (INTERVALS, INSTRUMENTS))
OUR_IDS = tuple(f"{n}:{w}" for n, w, _s, _d in OURS)


def _at(node, where):
    """The mapping a walk's path string points at."""
    for step in where.split("."):
        node = node[int(step)] if step.isdigit() else node[step]
    return node


def _bend(name, where, value):
    result = copy.deepcopy(SHAPES[name]["result"])
    _at(result["data_gap_report"], where)["count"] = value
    return result


def _refusal(name, result):
    door = the_door_for(result)
    with pytest.raises(Exception) as caught:
        door(SHAPES[name]["program"], result)
    return str(caught.value)


def _context(name):
    pair = SHAPES[name]
    return kernel._premises_of(pair["program"], pair["result"])[3]


# --------------------------------------------------------------- census

def test_the_counts_this_file_is_about():
    """Which sentences put a number in front of a reader, and how many of
    each -- so a corpus that stops carrying them says so here."""
    by_sentence: dict = {}
    for _n, _w, sentence, _said in COUNTS:
        by_sentence[sentence] = by_sentence.get(sentence, 0) + 1
    assert by_sentence == {
        "declared_binary_but_the_column_has_more_levels": 31,
        "several_intervals_bound_the_same_quantity": 12,
        "declared_discrete_but_the_values_form_a_continuum": 3,
        "iv_monotonicity_undeclared": 2,
        "declared_continuous_but_the_column_is_discrete": 2,
    }
    assert len(OURS) == 14


def test_a_count_is_still_not_a_name():
    """The other roster was right and stays as it was.

    A number contains no identifier to be wrong about, so the rule asking
    whether a word is one of this problem's names does not ask this one.
    That answer was never the reason nothing held it.
    """
    assert _rules._NOT_NAMES["count"] == "number"
    assert not _rules.holds_a_name(INTERVALS, "count")
    assert not _rules.holds_a_name(INSTRUMENTS, "count")


# ------------------------------------------------- the records they copy

@pytest.mark.parametrize("name", sorted(SHAPES))
def test_the_intervals_reader_counts_the_intervals(name):
    """Read directly, over every answer: the number this reader offers is
    the length of the list a reader is shown."""
    result = SHAPES[name]["result"]
    assert _rules._the_intervals_this_answer_reports(result) == {
        str(len(result.get("bounds_results") or ()))}


@pytest.mark.parametrize("name,where,sentence,said", OURS, ids=OUR_IDS)
def test_each_count_equals_the_record_it_counts(name, where, sentence, said):
    reader = (_rules._the_intervals_this_answer_reports
              if sentence == INTERVALS
              else _rules._the_instruments_the_graph_offers)
    assert reader(SHAPES[name]["result"], _context(name)) == {
        str(said["count"])}


def test_the_instrument_reader_is_silent_where_the_graph_has_no_ends():
    """The discipline the rule beside it keeps. A question whose two ends
    this graph does not both hold is not one this reader can count for,
    and a rule reading an empty roster says nothing."""
    silent = 0
    for name in sorted(SHAPES):
        try:
            context = _context(name)
        except Exception:
            continue
        if _rules._the_questions_ends(context) == (None, None):
            silent += 1
            assert _rules._the_instruments_the_graph_offers(
                SHAPES[name]["result"], context) == set()
    assert silent == 23


# ------------------------------------------------------ honest, then bent

@pytest.mark.parametrize("name", sorted({n for n, _w, _s, _d in OURS}))
def test_an_honest_count_is_still_accepted(name):
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


@pytest.mark.parametrize("name,where,sentence,said", OURS, ids=OUR_IDS)
def test_a_forged_count_is_refused(name, where, sentence, said):
    assert _refusal(name, _bend(name, where, str(said["count"]) + "_forged"))


@pytest.mark.parametrize("name,where,sentence,said", OURS, ids=OUR_IDS)
def test_a_count_left_blank_is_refused(name, where, sentence, said):
    assert _refusal(name, _bend(name, where, ""))


@pytest.mark.parametrize("name,where,sentence,said", OURS, ids=OUR_IDS)
def test_a_count_one_out_is_refused(name, where, sentence, said):
    """The lie a forgery does not tell.

    A number one out of the list it counts is the one a reader cannot see
    is wrong, and it is a whole interval or a whole instrument -- the
    reader is sent to look for one more than there is, or told there is
    one fewer to weigh.
    """
    one_out = str(int(str(said["count"])) + 1)
    assert _refusal(name, _bend(name, where, one_out))


# ------------------------------------------------ the spelling they share

def test_the_two_ends_are_spelt_in_one_place():
    """Three readers, one list. A reader with a list of its own is a
    second place for a query shape to go unlearnt."""
    assert _rules._THE_TWO_ENDS == (
        ("intervention", "target"),
        ("treatment", "outcome"),
        ("counterfactual_intervention", "counterfactual_target"),
    )
    assert _rules._the_questions_intervention.__code__.co_names.count(
        "_THE_TWO_ENDS") == 1
    assert _rules._the_questions_target.__code__.co_names.count(
        "_THE_TWO_ENDS") == 1
    assert "_THE_TWO_ENDS" in _rules._the_questions_ends.__code__.co_names
    assert "_THE_TWO_ENDS" in _rules._the_question_asked.__code__.co_names


def test_a_counterfactual_question_names_its_two_ends():
    """The blindness this frontier found, pinned from both readers.

    A counterfactual query spells its two ends in two fields of its own.
    Both readers here used to return nothing for it, which is not the same
    claim as a question that names no ends -- and the roster that copies
    the question was silent on every counterfactual answer because of it.
    """
    seen = 0
    for name in sorted(SHAPES):
        try:
            context = _context(name)
        except Exception:
            continue
        if type(context.query).__name__ != "CounterfactualQuery":
            continue
        seen += 1
        ends = _rules._the_questions_ends(context)
        assert ends != (None, None), name
        assert _rules._the_questions_intervention(
            SHAPES[name]["result"], context), name
        assert _rules._the_questions_target(
            SHAPES[name]["result"], context), name
        assert _rules._the_question_asked(SHAPES[name]["program"]) != (
            None, None), name
    assert seen == 11


def test_which_questions_name_two_ends_and_which_do_not():
    """Measured rather than asserted: the classes that name a pair, and
    the classes that name none. A question about an association or about
    a cause has no intervention and no target, and a reader that answered
    for one would be inventing a role the question does not give."""
    named, silent = set(), set()
    for name in sorted(SHAPES):
        try:
            context = _context(name)
        except Exception:
            continue
        kind = type(context.query).__name__
        (named if _rules._the_questions_ends(context) != (None, None)
         else silent).add(kind)
    assert named == {"EffectQuery", "SCMCounterfactualQuery",
                     "ProximalEffectQuery", "CounterfactualQuery",
                     "IdentifyQuery"}
    assert silent == {"AssocQuery", "CausationQuery", "CauseQuery",
                      "CounterfactualConjunctionQuery", "ProbabilityQuery"}
    assert not named & silent


# ------------------------------------------------------------ the reason

def test_the_reason_a_number_stays_unheld_names_the_rendering():
    """The sentence this frontier corrects, corrected rather than deleted:
    what cannot be held is a rendering, and the reason says so."""
    source = pathlib.Path(_rules.__file__).read_text("utf-8")
    assert "a RENDERING puts" in source or "a rendering puts" in source
    assert "formatting step" in source
    for statement in (INTERVALS, INSTRUMENTS):
        assert (statement, "count") in _rules._COPIED_FROM
