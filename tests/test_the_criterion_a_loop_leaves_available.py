"""A declared loop, and the two things it settles about an identification.

A reciprocal loop the estimand reaches takes the ordinary routes off the
table, and the envelope says so in two places: the withdrawal block names
the routes that went, and the identification block names the criterion the
answer came by instead. Neither was held. The routes could be named
anything at all, and the criterion could be one that is a theorem about an
acyclic graph -- because a loop is declared as a statement and is not an
edge, so every graph-level re-derivation is handed an acyclic graph and
agrees.

What is asserted here:

- the vocabulary is split in two and the split covers the schema's own two
  enums exactly, so a sixth pattern word cannot be added and go unclassified
- the leaf: the stored answer that reached its number through an
  instrument, relabelled with each of the three acyclic criteria, refused
  at the strongest door that reads it
- the joint surface too, which the corpus does not exercise and which has
  no escape word in its vocabulary at all
- the escape word passes under the same loop, which is what it is for
- the withdrawal's names are route ids this build declares, held against
  ``themis.routing`` -- where the schema sends a reader to look one up --
  rather than against a copy of it
- four silences, each about something absent
- no honest answer is refused.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

from themis import routing
from themis.types import Atom, ConstTerm, EffectQuery, Intervention, ValuedAtom
from themis.verifier.acyclic_criterion_rules import (
    _ACYCLIC_ONLY, _HOLDS_UNDER_A_LOOP, _RULE,
    verify_no_acyclic_criterion_is_claimed_under_a_loop as verify)
from themis.verifier.errors import VerificationError

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))
SCHEMA = json.loads(
    (ROOT / "themis" / "schemas" / "query_result.schema.json")
    .read_text(encoding="utf-8"))

#: How many stored answers record a withdrawal. Named, because a rule the
#: corpus stopped exercising would go quiet without saying so.
ANSWERS_RECORDING_A_WITHDRAWAL = 3

#: The one of those that also names a criterion a reader is shown.
THE_ANSWER_THAT_NAMES_A_CRITERION = "iv_2sls"


def A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _graph(edges, loops=()):
    graph = nx.DiGraph()
    names = {n for edge in edges for n in edge} | {
        n for loop in loops for n in loop}
    for name in names:
        graph.add_node(A(name))
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    return graph, frozenset(frozenset({A(u), A(v)}) for u, v in loops)


def _asks(*, extra=()):
    return EffectQuery(
        target=ValuedAtom(atom=A("y"), value=True),
        intervention=Intervention(atom=A("x"), value=True), given=(),
        extra_interventions=tuple(
            Intervention(atom=A(e), value=True) for e in extra))


#: A loop between the two ends, which is the shape the reduction applies to.
BETWEEN_THE_ENDS = ([("z", "x"), ("x", "y")], [("x", "y")])

#: A loop somewhere else entirely, reaching neither end.
SOMEWHERE_ELSE = ([("x", "y")], [("s", "t")])


def _withdrawers():
    return sorted(
        name for name, row in SHAPES.items()
        if isinstance(((row["result"].get("extensions") or {})
                       .get("feedback_loop") or {}).get("withdrew"), list))


# ------------------------------------------------------------- the rosters


def test_the_two_rosters_cover_the_schema_s_two_vocabularies():
    """Held against the schema rather than against a sentence about it. A
    sixth pattern word added there and not here would be a criterion whose
    domain of validity nothing states."""
    blocks = SCHEMA["properties"]["extensions"]["properties"]
    scalar = set(blocks["identification"]["properties"]["pattern"]["enum"])
    joint = set(blocks["joint_identification"]["properties"]["pattern"]["enum"])
    assert _ACYCLIC_ONLY | _HOLDS_UNDER_A_LOOP == scalar | joint
    assert not (_ACYCLIC_ONLY & _HOLDS_UNDER_A_LOOP)
    assert _HOLDS_UNDER_A_LOOP == {"instrumental_variable"}
    assert joint <= _ACYCLIC_ONLY, "the joint vocabulary has no escape word"


def test_the_withdrawal_roster_is_the_one_the_schema_sends_a_reader_to():
    """``themis.routing``, named in the schema's own description of the
    field, rather than the dispatcher's table or a copy of either."""
    ids = {row.id for row in routing.EFFECT_ROUTES}
    assert {"backdoor", "frontdoor", "general_id", "iv_wald"} <= ids
    for name in _withdrawers():
        withdrew = SHAPES[name]["result"]["extensions"]["feedback_loop"][
            "withdrew"]
        assert set(withdrew) <= ids, (name, withdrew)


# ----------------------------------------------------------- what it refuses


@pytest.mark.parametrize("pattern", sorted(
    _ACYCLIC_ONLY & {"backdoor", "front_door", "c_factor"}))
def test_an_acyclic_criterion_named_under_a_loop_is_refused(pattern):
    """The graph these criteria would be read off is acyclic only because
    the loop is a statement, so each of them can be true there while none
    of them is true of the model the program states.

    Asked before the criterion is re-derived, and that ordering is the
    claim: two of these three were already refused, for failing their own
    criterion ON the acyclic picture, which is a complaint about the wrong
    thing once the picture is known to be wrong. The third -- the leaf --
    satisfied its criterion there and was refused by nothing at all.
    """
    row = SHAPES[THE_ANSWER_THAT_NAMES_A_CRITERION]
    forged = copy.deepcopy(row["result"])
    forged["extensions"]["identification"]["pattern"] = pattern
    with pytest.raises(VerificationError, match="acyclic graph") as err:
        the_door_for(row["result"])(row["program"], forged)
    assert "identification:" in str(err.value)


def test_the_leaf_is_the_one_the_acyclic_picture_agreed_with():
    """Named so the count does not go quiet. On this answer's graph the
    empty set IS a valid back-door set -- the loop is what makes it not
    one -- so that word, alone of the three, passed every reading."""
    graph, loops = _graph(*BETWEEN_THE_ENDS)
    assert not nx.is_directed_acyclic_graph(
        nx.DiGraph(list(graph.edges) + [(A("y"), A("x"))]))
    verify({"pattern": "instrumental_variable"}, graph, loops, _asks(),
           "identification")


def test_the_joint_surface_is_asked_the_same_question():
    """Which the corpus does not exercise: no stored joint answer declares
    a loop. A rule that knew only the scalar block would leave this one
    free, and both of its words name an acyclic criterion."""
    graph, loops = _graph(*BETWEEN_THE_ENDS)
    for pattern in sorted({"joint_backdoor", "joint_general_id"}):
        block = {"pattern": pattern, "treatments": ["x(me)", "b(me)"]}
        with pytest.raises(VerificationError, match="acyclic graph") as err:
            verify(block, graph, loops, _asks(extra=("b",)),
                   "joint_identification")
        assert "joint_identification:" in str(err.value)
        assert err.value.rule == _RULE


def test_the_refusal_names_the_loop_the_program_declares():
    """Which loop, not just that there is one: a reader told the picture
    is wrong needs the pair to go and look at."""
    graph, loops = _graph(*BETWEEN_THE_ENDS)
    with pytest.raises(VerificationError, match=r"x\(me\)', 'y\(me\)'"):
        verify({"pattern": "backdoor"}, graph, loops, _asks(),
               "identification")


# -------------------------------------------------------- what it allows


def test_the_escape_word_passes_under_the_same_loop():
    """An instrument identifies a coefficient of the two-equation system,
    and being the way out of exactly this is what it is for."""
    graph, loops = _graph(*BETWEEN_THE_ENDS)
    verify({"pattern": "instrumental_variable", "instrument": "z(me)",
            "conditioning": []}, graph, loops, _asks(), "identification")


@pytest.mark.parametrize("surface", [
    {"pattern": "backdoor"},
    {"pattern": "c_factor"},
])
def test_a_loop_that_reaches_neither_end_says_nothing_here(surface):
    """A loop declared elsewhere in the graph is a reason for nothing
    about this estimand -- the same reading the withdrawal block and the
    derivation's own licence already use."""
    graph, loops = _graph(*SOMEWHERE_ELSE)
    verify(surface, graph, loops, _asks(), "identification")


@pytest.mark.parametrize("surface", [
    None, [], "backdoor", {}, {"pattern": None},
    {"pattern": "instrumental_variable"},
    {"pattern": "a_word_no_schema_carries"},
])
def test_the_shapes_this_rule_says_nothing_about(surface):
    """An unregistered word is passed over on purpose: membership in the
    vocabulary is the schema's question, and the two pattern
    re-derivations refuse an unknown word already."""
    graph, loops = _graph(*BETWEEN_THE_ENDS)
    verify(surface, graph, loops, _asks(), "identification")


def test_a_program_declaring_no_loop_says_nothing_here():
    graph, _loops = _graph([("z", "x"), ("x", "y")])
    verify({"pattern": "backdoor"}, graph, frozenset(), _asks(),
           "identification")


# ------------------------------------------------- the withdrawal's names


@pytest.mark.parametrize("name", _withdrawers())
def test_a_withdrawn_route_that_is_no_route_is_refused(name):
    """Three bends, one per way of not being a route id: a name with
    something appended, an empty name, and a name from somewhere else."""
    row = SHAPES[name]
    for bent in ("backdoor_forged", "", "a_route_this_build_has_not_got"):
        forged = copy.deepcopy(row["result"])
        forged["extensions"]["feedback_loop"]["withdrew"][0] = bent
        with pytest.raises(VerificationError, match="dispatches no"):
            the_door_for(row["result"])(row["program"], forged)


def test_the_corpus_records_this_many_withdrawals():
    names = _withdrawers()
    assert len(names) == ANSWERS_RECORDING_A_WITHDRAWAL, names
    assert THE_ANSWER_THAT_NAMES_A_CRITERION in names


# ------------------------------------------------------------- at the door


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_honest_answer_is_refused(shape):
    row = SHAPES[shape]
    verify_honestly(row["program"], row["result"])
