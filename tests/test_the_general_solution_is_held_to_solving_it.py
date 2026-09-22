"""The strongest identification claim, held to being one.

``extensions.identification`` is the one sentence a reader gets about
where a number came from, and ``c_factor`` — the ID algorithm's general
solution — is the strongest thing it can say. Three of its four patterns
were re-derived from the graph; the fourth was searched only for what it
says is NOT there, a back door or a front door that could have been named
instead. An instrument's answer has neither, so it could wear the label
and both searches came back empty and agreed.

What is asserted here:

- the claim is held positively: on a graph where the ID algorithm gives
  up, a block claiming the general solution is refused
- WHICH engine answers belongs to the question, not to the block. A
  conditional question is IDC's, and IDC can fail where the unconditional
  criterion succeeds — a reading that asked the easier question would pass
  exactly the claims the harder one refuses
- the leaf this closes: a stored IV answer relabelled the general
  solution, refused at the strongest door that reads it
- the negative half still fires, on both structures, so the positive half
  is not refusing everything on its way past
- no honest answer carrying this block is refused, and honest answers
  exercise both engines
- one transcription, two callers: the derivation's own licence and the
  block a reader is shown route the same question the same way.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

from themis.types import (
    Atom, ConstTerm, EffectQuery, IdentifyQuery, Intervention, ValuedAtom,
)
from themis.verifier import VerificationContext
from themis.verifier.errors import RuleCheckFailed, VerificationError
from themis.verifier.rules import (
    _joint_treatments_of, _rule_general_id_criterion, general_id_identifies,
)
from themis.verifier.verify import verify_identification_pattern

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: How many stored answers carry an identification block at all, and how
#: many of those claim the general solution. Named, because a rule the
#: corpus stopped exercising would go quiet without saying so.
ANSWERS_CARRYING_AN_IDENTIFICATION = 99
ANSWERS_CLAIMING_THE_GENERAL_SOLUTION = 11


def A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _graph(edges, latent=()):
    graph = nx.DiGraph()
    for name in {n for edge in edges for n in edge} | {
            n for edge in latent for n in edge}:
        graph.add_node(A(name))
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    return graph, frozenset(frozenset({A(u), A(v)}) for u, v in latent)


def _asks(*, given=(), extra=()):
    return EffectQuery(
        target=ValuedAtom(atom=A("y"), value=True),
        intervention=Intervention(atom=A("x"), value=True),
        given=tuple(ValuedAtom(atom=A(g), value=True) for g in given),
        extra_interventions=tuple(
            Intervention(atom=A(e), value=True) for e in extra),
    )


#: x and y share an unobserved cause and nothing else stands between
#: them: the bow arc, where no algorithm identifies the effect.
BOW = [("x", "y")], [("x", "y")]

#: Tian answers ``P(y | do(x))`` here and IDC does not answer
#: ``P(y | do(x), z)``: the conditioning is on a variable x causes and
#: is confounded with. A reading that asked the unconditional question
#: about a conditional one would pass a claim this graph cannot support.
IDC_FAILS = [("x", "y"), ("x", "z"), ("y", "z")], [("x", "z")]

#: A back door to find, so the general solution is too modest.
HAS_A_BACK_DOOR = [("z", "x"), ("z", "y"), ("x", "y")], []

#: A front door to find, same.
HAS_A_FRONT_DOOR = [("x", "m"), ("m", "y")], [("x", "y")]


def _carriers():
    return sorted(
        name for name, row in SHAPES.items()
        if isinstance((row["result"].get("extensions") or {}).get(
            "identification"), dict))


def _claims_the_general_solution():
    return sorted(
        name for name in _carriers()
        if SHAPES[name]["result"]["extensions"]["identification"].get(
            "pattern") == "c_factor")


# ----------------------------------------------------------- what it refuses


def test_a_general_solution_that_does_not_solve_is_refused():
    """The claim, held positively. Nothing identifies an effect across a
    bow arc, and until the algorithm was re-run here the word saying it
    had been was free: both searches below look for structure that is not
    there either, and finding none is what they report as agreement."""
    graph, latent = _graph(*BOW)
    with pytest.raises(VerificationError, match="does not identify") as err:
        verify_identification_pattern(
            {"pattern": "c_factor"}, graph, latent, _asks())
    assert "P(y | do(x))" in str(err.value)
    assert err.value.rule == "identification"


def test_the_question_s_conditioning_decides_which_engine_answers():
    """IDC is the load-bearing one. This graph answers the unconditional
    question and not the conditional one, so a check that asked Tian about
    a question that conditions would pass a claim IDC refuses — which is
    why the routing is read from the question rather than assumed."""
    graph, latent = _graph(*IDC_FAILS)
    assert general_id_identifies(graph, latent, A("x"), A("y"), _asks())
    assert not general_id_identifies(
        graph, latent, A("x"), A("y"), _asks(given=("z",)))
    with pytest.raises(VerificationError, match="does not identify") as err:
        verify_identification_pattern(
            {"pattern": "c_factor", "conditioned_on": ["z(me)"]},
            graph, latent, _asks(given=("z",)))
    assert "P(y | do(x), ['z'])" in str(err.value)


def test_an_answer_an_instrument_identified_cannot_wear_the_label():
    """The leaf. A stored answer that reached its number through an
    instrument, relabelled the general solution: an IV graph has neither a
    back door nor a front door, so the two searches agree with the
    forgery and only the algorithm itself disagrees."""
    names = [
        n for n in sorted(SHAPES)
        if (SHAPES[n]["result"].get("extensions") or {}).get(
            "identification", {}).get("pattern") == "instrumental_variable"
        and "identify_via_iv" in n]
    assert len(names) == 2, names
    for name in names:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        forged["extensions"]["identification"]["pattern"] = "c_factor"
        with pytest.raises(VerificationError, match="does not identify"):
            the_door_for(row["result"])(row["program"], forged)


def test_the_negative_half_still_fires_where_something_could_be_named():
    """The positive half runs first and passes on both of these, so the
    complaint a reader gets is still the one about being told nothing
    when something could have been said."""
    graph, latent = _graph(*HAS_A_BACK_DOOR)
    with pytest.raises(VerificationError, match="valid back-door adjustment"):
        verify_identification_pattern(
            {"pattern": "c_factor"}, graph, latent, _asks())

    graph, latent = _graph(*HAS_A_FRONT_DOOR)
    with pytest.raises(VerificationError, match="identified by the front door"):
        verify_identification_pattern(
            {"pattern": "c_factor"}, graph, latent, _asks())


# -------------------------------------------------------- the honest answers


def test_the_corpus_claims_the_general_solution_this_many_times():
    names = _claims_the_general_solution()
    assert len(_carriers()) == ANSWERS_CARRYING_AN_IDENTIFICATION
    assert len(names) == ANSWERS_CLAIMING_THE_GENERAL_SOLUTION, names


def test_honest_claims_exercise_both_engines():
    """A block records ``conditioned_on`` exactly when its question
    conditions — one rule holds the copy equal to the question's and
    another refuses the silence — so it says which engine answered. Nine
    IDC and two Tian: neither branch is a branch nothing reaches."""
    conditional = [
        name for name in _claims_the_general_solution()
        if SHAPES[name]["result"]["extensions"]["identification"].get(
            "conditioned_on")]
    assert len(conditional) == 9, conditional
    assert len(_claims_the_general_solution()) - len(conditional) == 2


@pytest.mark.parametrize("shape", _carriers())
def test_no_answer_carrying_this_block_is_refused(shape):
    """The denominator, through the strongest door that reads each one."""
    row = SHAPES[shape]
    verify_honestly(row["program"], row["result"])


# ------------------------------------------------------- one transcription


def test_the_derivation_s_licence_and_the_block_route_alike():
    """Two callers, one routing. The step that licenses a number and the
    word a reader is shown are different objects holding one fact, and a
    second transcription would be one more place for them to disagree."""
    graph, latent = _graph(*IDC_FAILS)
    query = _asks(given=("z",))
    ctx = VerificationContext(graph=graph, query=query, bidirected=latent)
    with pytest.raises(RuleCheckFailed, match="recomputed identifiable=False"):
        _rule_general_id_criterion(
            ctx, {"graph": graph, "x": A("x"), "y": A("y")}, True, 0)
    with pytest.raises(VerificationError, match="does not identify"):
        verify_identification_pattern(
            {"pattern": "c_factor", "conditioned_on": ["z(me)"]},
            graph, latent, query)


def test_both_question_shapes_reach_the_routing():
    """``IdentifyQuery`` says it of itself — "target / given have no values
    attached because identifiability depends on atoms, not values" — so
    the two shapes spell their conditioning differently. While the step
    rule was the only caller only the valued shape ever arrived, and the
    routing read it the one way. Reading the block a reader is shown sends
    the other shape through the same transcription."""
    graph, latent = _graph(*IDC_FAILS)
    bare = IdentifyQuery(
        target=A("y"),
        intervention=Intervention(atom=A("x"), value=True),
        given=(A("z"),),
    )
    assert not general_id_identifies(graph, latent, A("x"), A("y"), bare)
    assert general_id_identifies(
        graph, latent, A("x"), A("y"),
        IdentifyQuery(target=A("y"),
                      intervention=Intervention(atom=A("x"), value=True),
                      given=()))


def test_the_treatment_set_is_read_from_the_question():
    assert _joint_treatments_of(_asks()) == frozenset()
    assert _joint_treatments_of(_asks(extra=("b",))) == {A("x"), A("b")}
    assert _joint_treatments_of(object()) == frozenset()


def test_a_conditional_joint_question_has_no_estimand_to_identify():
    """v1 scope, stated as a verdict rather than as a call: there is no
    supported estimand, so nothing identifies it and no engine is asked."""
    graph, latent = _graph([("x", "y"), ("b", "y"), ("z", "y")], [])
    assert not general_id_identifies(
        graph, latent, A("x"), A("y"), _asks(given=("z",), extra=("b",)))


def test_a_joint_question_goes_to_the_set_valued_algorithm():
    """No stored answer carrying this block asks a joint question — the
    producer attaches it only on rows whose estimand is P(Y | do(X)) for a
    single X — so the routing is held here rather than by the corpus."""
    graph, latent = _graph([("x", "y"), ("b", "y")], [])
    assert general_id_identifies(
        graph, latent, A("x"), A("y"), _asks(extra=("b",)))
    graph, latent = _graph([("x", "y"), ("b", "y")], [("x", "y")])
    assert not general_id_identifies(
        graph, latent, A("x"), A("y"), _asks(extra=("b",)))
