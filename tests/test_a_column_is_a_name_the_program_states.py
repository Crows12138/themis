"""A column a number was read off is a name the program states.

``estimation_context.data_columns`` is the list of columns the frame was
narrowed to before anything was computed. One rule already read it and
asked whether a column stood for SEVERAL of the program's nodes. It could
not ask the other half -- whether a column stood for any -- because it
finds its nodes by looking each column up, so a column matching nothing is
a column it never visits. The two failures of one list were not two halves
of one question: one was asked, and the other could not be phrased from
where it was standing.

Measured on the corpus of the day: of the 120 stored answers that state a
column list, a column the program declares nothing under walked past the
strongest public door on 38 and was refused on 82 -- and refused there by
rules that re-derive a number from the columns they were given, which is a
different question that happens to notice.

Read off the PROGRAM and not off the graph. A program names a column in
two places and the graph carries one of them: the predicate a variable is
declared under, and the indicator a follow-up time declares beside it,
saying which rows had the event and which merely ran out of observation.
That second column is not a node of any graph, so a rule reading the graph
refuses the one honest survival answer the corpus has -- which is how a
rule reading the wrong document announces itself.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for
from themis.verifier import (
    verify_a_column_is_a_name_the_program_states,
    verify_a_column_is_one_node,
)
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every stored answer that says which columns its number was read off.
FRAMED = sorted(
    name for name, pair in SHAPES.items()
    if isinstance((pair["result"].get("estimation_context") or {})
                  .get("data_columns"), list))

#: The one stored answer whose frame holds a column that is no node of any
#: graph: a survival time's event indicator.
SURVIVAL = "rmst_kaplan_meier"


def _stranger(program) -> str:
    """A column name this program cannot be read as already declaring."""
    said = set(json.dumps(program, ensure_ascii=False).split('"'))
    name = "q"
    while name in said:
        name += "z"
    return name


def _declared_nodes(program) -> set[str]:
    """Every predicate the program's GRAPH carries, which is the other
    document a rule about columns could have been written against."""
    out: set[str] = set()
    for stmt in program.get("statements") or ():
        if stmt.get("kind") not in {"cause", "bidirected"}:
            continue
        for side in ("from", "to", "left", "right"):
            atom = stmt.get(side)
            if isinstance(atom, dict) and isinstance(atom.get("predicate"), str):
                out.add(atom["predicate"])
    return out


# ------------------------------------------------------------ honest first


def test_the_corpus_states_a_column_list_on_a_hundred_and_twenty_answers():
    """The denominator, low enough not to churn and high enough that a
    corpus this gate had stopped reading would fail here."""
    assert len(FRAMED) >= 100, len(FRAMED)


@pytest.mark.parametrize("name", FRAMED)
def test_every_column_a_stored_answer_read_is_one_its_program_states(name):
    """Honest first, per answer. A rule that refuses what this repository
    really produces is not a rule, whatever it catches."""
    pair = SHAPES[name]
    verify_a_column_is_a_name_the_program_states(pair["result"], pair["program"])


def test_no_stored_answer_is_refused_at_its_own_door():
    """And through the door, because a rule is only as accepted as the
    surface that runs it."""
    for name in FRAMED:
        pair = SHAPES[name]
        the_door_for(pair["result"])(pair["program"], pair["result"])


# ------------------------------------------------ the column nobody declared


def test_a_column_the_program_declares_nothing_under_is_refused():
    """Every framed answer, since the question is about the list and not
    about any route that fills it."""
    for name in FRAMED:
        pair = SHAPES[name]
        forged = copy.deepcopy(pair["result"])
        forged["estimation_context"]["data_columns"] = sorted([
            *forged["estimation_context"]["data_columns"],
            _stranger(pair["program"]),
        ])
        with pytest.raises(VerificationError, match="declares no variable"):
            verify_a_column_is_a_name_the_program_states(forged, pair["program"])


def test_the_door_refuses_it_too_on_every_framed_answer():
    """The rule reaching the public surface, asked of the whole corpus at
    once: a hole measured through the door is closed through the door."""
    walked = []
    for name in FRAMED:
        pair = SHAPES[name]
        forged = copy.deepcopy(pair["result"])
        forged["estimation_context"]["data_columns"] = sorted([
            *forged["estimation_context"]["data_columns"],
            _stranger(pair["program"]),
        ])
        try:
            the_door_for(forged)(pair["program"], forged)
        except VerificationError:
            continue
        walked.append(name)
    assert walked == []


def test_the_sibling_takes_the_same_stranger_without_a_word():
    """Why this is a second rule and not a line added to the first.

    ``verify_a_column_is_one_node`` looks each column up among the graph's
    nodes and complains where a column finds several. A column that finds
    none puts nothing in the table it reads, so there is no place in that
    rule for the question to be asked from.
    """
    from themis.kernel import _premises_of

    pair = SHAPES[SURVIVAL]
    forged = copy.deepcopy(pair["result"])
    forged["estimation_context"]["data_columns"] = sorted([
        *forged["estimation_context"]["data_columns"],
        _stranger(pair["program"]),
    ])
    _, _, _, ctx = _premises_of(pair["program"], forged)
    verify_a_column_is_one_node(forged, ctx.graph)
    with pytest.raises(VerificationError, match="declares no variable"):
        verify_a_column_is_a_name_the_program_states(forged, pair["program"])


# ------------------------------------------- the document the rule reads


def test_the_event_indicator_is_a_column_no_graph_carries():
    """The measurement that decides which document the rule reads.

    The survival answer's frame holds ``seen``, declared on the follow-up
    time as the column saying which rows had the event. It is not a node of
    the graph and never will be. A rule reading the graph would refuse this
    answer; the rule reads the program, and does not.
    """
    pair = SHAPES[SURVIVAL]
    columns = set(pair["result"]["estimation_context"]["data_columns"])
    indicators = {
        stmt["censoring"]["event_indicator"]
        for stmt in pair["program"]["statements"]
        if isinstance(stmt.get("censoring"), dict)
    }
    assert indicators & columns, (indicators, columns)
    assert not (indicators & _declared_nodes(pair["program"]))
    verify_a_column_is_a_name_the_program_states(pair["result"], pair["program"])


def test_an_indicator_the_program_stops_declaring_is_refused():
    """The same answer, with the declaration that names the column taken
    away: the column is then a name nothing states, and is refused. The
    honest case above and this one differ by exactly that declaration."""
    pair = SHAPES[SURVIVAL]
    program = copy.deepcopy(pair["program"])
    for stmt in program["statements"]:
        stmt.pop("censoring", None)
    with pytest.raises(VerificationError, match="declares no variable"):
        verify_a_column_is_a_name_the_program_states(pair["result"], program)


# --------------------------------------------------- what is not a claim


def test_an_answer_that_claims_no_frame_is_not_asked():
    """No envelope, no column list, and a list that is not a list: three
    ways of having said nothing about a frame, which is not a claim to be
    contradicted."""
    program = {"statements": [
        {"kind": "variable", "predicate": "x", "domain": [0, 1]}]}
    for result in ({}, {"estimation_context": {}},
                   {"estimation_context": {"data_columns": None}}):
        verify_a_column_is_a_name_the_program_states(result, program)


def test_neither_half_being_a_dict_is_not_a_claim_either():
    """The verifier is handed what a caller sent it."""
    verify_a_column_is_a_name_the_program_states(None, {"statements": []})
    verify_a_column_is_a_name_the_program_states(
        {"estimation_context": {"data_columns": ["x"]}}, None)
