"""A slot's kind is its statement's, and the name rule asks the pair.

``target`` fills seven statements a gap report can carry. In five it is the
variable an effect is taken on — the two about a restriction on a collider,
the one about a dose-response curve, and the two ways past a conditioned
collider. In one it is the population an answer is carried to, and in one
the name of an ask. The rosters that decide whether the name rule asks a
slot were keyed on the slot's name, and ``target`` was filed as a
vocabulary member, so the name rule asked it nowhere: a gap saying the
curve runs between ``x`` and ``y_forged`` passed every door.

Two more things stood between a declaration per statement and the
envelope. A way past names its statement under ``route``, which the walk
did not read. And the index the binding holds the rosters to had no routes
in it, so no slot a way past declares was bound — ``scale`` was in no
roster at all.
"""
from __future__ import annotations

import copy
import json
import pathlib
import re

import networkx as nx
import pytest

from tests.answer_corpus import the_door_for
from themis import gaps as _gaps
from themis.kernel import _premises_of
from themis.types import Atom
from themis.verifier.context import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.statement_rules import _CARRIERS
from themis.verifier.gap_claim_rules import (
    _IN_ITS_SENTENCE,
    _NAMES,
    _NOT_NAMES,
    _NAMED_BY,
    _TURNS_ON_THE_SENTENCE,
    every_said_mapping,
    holds_a_name,
    statements_and_the_slots_they_declare,
    verify_gap_names,
    words_the_problem_uses,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: (answer, path to the ``said``, statement) for every ``target`` the corpus
#: writes.
TARGETS = sorted(
    (name, where, statement)
    for name, pair in SHAPES.items()
    for where, statement, said in every_said_mapping(
        pair["result"].get("data_gap_report") or {})
    if "target" in said
)
AS_A_NAME = [site for site in TARGETS if holds_a_name(site[2], "target")]
NOT_AS_A_NAME = [site for site in TARGETS
                 if not holds_a_name(site[2], "target")]


def _said(result, where):
    node = result["data_gap_report"]
    for step in where.split("."):
        node = node[int(step)] if step.isdigit() else node[step]
    return node


def _context(name):
    pair = SHAPES[name]
    return _premises_of(pair["program"], pair["result"])[3]


# --------------------------------------------------------- the declaration


def test_every_statement_declaring_target_says_what_it_holds_there():
    """Bound, both ways: no statement declares the slot without an entry,
    and no entry names a statement that does not declare it."""
    declared = {pair for pair in statements_and_the_slots_they_declare()
                if pair[1] in _TURNS_ON_THE_SENTENCE}
    assert declared == set(_IN_ITS_SENTENCE)
    assert sorted(_IN_ITS_SENTENCE.values()) == [
        "domain", "expression", "name", "name", "name", "name", "name"]


def test_a_slot_whose_kind_is_its_statements_is_in_neither_roster():
    assert _TURNS_ON_THE_SENTENCE == {"target"}
    assert not _TURNS_ON_THE_SENTENCE & set(_NAMES)
    assert not _TURNS_ON_THE_SENTENCE & set(_NOT_NAMES)


def test_the_index_reaches_the_ways_past():
    """What the binding could not see while it read no routes: four slots
    only a way past declares, one of which was in no roster."""
    pairs = statements_and_the_slots_they_declare()
    from_routes = {slot for statement, slot in pairs
                   if statement in _gaps.BY_ROUTE}
    elsewhere = {slot for statement, slot in pairs
                 if statement not in _gaps.BY_ROUTE}
    assert sorted(from_routes - elsewhere) == [
        "fallback", "methods", "scale", "wanted"]
    assert _NOT_NAMES["scale"] == "vocabulary"


def test_holds_a_name_reads_the_pair_only_where_the_kind_turns_on_it():
    assert holds_a_name("the_question_asks_for_a_dose_response_curve",
                        "target")
    assert holds_a_name("ask_the_marginal_effect", "target")
    assert not holds_a_name("transport_rests_on_s_admissibility", "target")
    assert not holds_a_name(
        "the_decomposition_needs_the_mediators_distributions", "target")
    assert not holds_a_name(None, "target")
    assert holds_a_name(None, "variable")
    assert holds_a_name("transport_rests_on_s_admissibility", "variable")
    assert not holds_a_name("the_question_asks_for_a_dose_response_curve",
                            "note")


# ------------------------------------------------------ the statement's name


def test_a_way_past_names_its_statement_and_a_description_its_sentence():
    routes = sentences = 0
    for pair in SHAPES.values():
        report = pair["result"].get("data_gap_report") or {}
        for where, statement, _said_here in every_said_mapping(report):
            if re.fullmatch(r"gaps\.\d+\.alternative_paths\.\d+\.said", where):
                assert statement in _gaps.BY_ROUTE, (where, statement)
                routes += 1
            elif re.fullmatch(r"gaps\.\d+\.describes\.\d+\.said", where):
                assert statement in _gaps.BY_SENTENCE, (where, statement)
                sentences += 1
    # 4 fewer sentences: the sentence naming a Balke-Pearl interval's method and assumptions went with the
    # interval on four refreshed answers, whose instrument needs something conditioned.
    # 1 more sentence: the refreshed joint general-ID answer carries a gap about its second
    # treatment's definition, which its producer had grown since the row was stored.
    # 15 more routes and 56 more sentences: the eight rows brought when the identifier began
    # answering a query conditioning on a descendant of the treatment.
    assert (routes, sentences) == (442, 866), (routes, sentences)


def test_a_gaps_own_said_is_the_occasion_its_kind_names():
    """It named none. A gap's occasion is the statement ``IF_PROVIDED``
    speaks under the gap's kind, which is how the statement rule has
    always read it, and the walk reads it the same way now."""
    tops = []
    for pair in SHAPES.values():
        report = pair["result"].get("data_gap_report") or {}
        for where, statement, _said_here in every_said_mapping(report):
            if re.fullmatch(r"gaps\.\d+\.said", where):
                gap = report["gaps"][int(where.split(".")[1])]
                tops.append((statement, gap["kind"]))
    assert len(tops) == 151, len(tops)
    assert all(statement == kind for statement, kind in tops)
    assert {kind for _statement, kind in tops} <= set(_gaps.IF_PROVIDED)


def test_the_walk_reads_the_spellings_the_statement_rule_reads():
    """One list of which key names a statement, not two. The walk's own
    lost a way past and then an occasion; the statement rule's is held to
    the contract."""
    carried = {spelling for path, (spelling, _vocabulary) in _CARRIERS.items()
               if path.startswith("data_gap_report.")}
    assert set(_NAMED_BY) == carried | {"token"}
    assert (_NAMED_BY[0], _NAMED_BY[-1]) == ("token", "kind")


# -------------------------------------------------------------- the name rule


def test_the_corpus_writes_target_in_six_statements():
    assert len(TARGETS) == 39, len(TARGETS)
    assert len(AS_A_NAME) == 28, len(AS_A_NAME)
    assert {statement for _n, _w, statement in NOT_AS_A_NAME} == {
        "transport_rests_on_s_admissibility"}


@pytest.mark.parametrize("name,where,statement", AS_A_NAME)
def test_an_honest_target_is_a_name_the_problem_has(name, where, statement):
    verify_gap_names(SHAPES[name]["result"], _context(name))


@pytest.mark.parametrize("name,where,statement", AS_A_NAME)
def test_a_target_naming_nothing_the_problem_has_is_refused(
        name, where, statement):
    forged = copy.deepcopy(SHAPES[name]["result"])
    said = _said(forged, where)
    said["target"] = said["target"] + "_forged"
    with pytest.raises(VerificationError, match="does not name"):
        verify_gap_names(forged, _context(name))
    with pytest.raises(VerificationError):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


@pytest.mark.parametrize("name,where,statement", AS_A_NAME)
def test_a_target_that_says_nothing_is_refused(name, where, statement):
    forged = copy.deepcopy(SHAPES[name]["result"])
    _said(forged, where)["target"] = ""
    with pytest.raises(VerificationError, match="says nothing there"):
        verify_gap_names(forged, _context(name))


@pytest.mark.parametrize("name,where,statement", NOT_AS_A_NAME)
def test_a_population_is_not_asked_whether_it_is_a_variable(
        name, where, statement):
    """The false refusal a name-alone filing as a NAME would have made."""
    result = SHAPES[name]["result"]
    context = _context(name)
    assert _said(result, where)["target"] not in words_the_problem_uses(context)
    verify_gap_names(result, context)


def test_a_statement_with_no_entry_is_not_asked():
    """A gloss written from another layer's vocabulary can say ``target``
    too — the adjusted conditional a missing-data recovery could not reach
    is ``P(y|x)`` there — and the declaration cannot reach that vocabulary.
    The name rule leaves the slot alone there rather than guessing; beside
    it, the same word under a statement that files it as a name is held."""
    graph = nx.DiGraph()
    graph.add_nodes_from([Atom("x", ()), Atom("y", ())])

    class _Q:
        pass

    context = VerificationContext(graph=graph, query=_Q())
    description = {
        "sentence": "the_question_asks_for_a_dose_response_curve",
        "said": {"intervention": "x", "target": "y"},
        "words": {"why": {"token": "the_adjusted_conditional",
                          "vocabulary": "shortfall",
                          "said": {"target": "P(y|x)"}}},
    }
    result = {"data_gap_report": {"gaps": [{"describes": [description]}]}}
    verify_gap_names(result, context)
    description["said"]["target"] = "P(y|x)"
    with pytest.raises(VerificationError, match="does not name"):
        verify_gap_names(result, context)


def test_what_a_membership_test_cannot_ask_is_asked_of_the_question():
    """A target rewritten to another variable the problem has is still a
    name it has — ``x``, on seven of these rows — and the name rule has to
    pass it. Whether it is THIS name is the question's own target to
    settle, and the rule holding a copy to its record now does."""
    accepted = []
    for name, where, statement in AS_A_NAME:
        forged = copy.deepcopy(SHAPES[name]["result"])
        _said(forged, where)["target"] = "x"
        try:
            the_door_for(SHAPES[name]["result"])(
                SHAPES[name]["program"], forged)
        except VerificationError:
            continue
        accepted.append((name, statement))
    assert accepted == [], accepted
