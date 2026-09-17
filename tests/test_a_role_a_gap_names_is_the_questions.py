"""A slot named after a role of the question is held to the question.

The name rule asks whether a word is one this problem is written in. A gap
whose intervention is rewritten from ``x`` to ``y`` answers yes — both are —
and measured before this, 1070 rewrites of such a slot into another
variable the problem really has passed every door, 912 of them on the four
statements about whether an intervention is a state or an event. The
statements writing these slots copy the question, and the question is on
the program: the one record an answer cannot edit.

Not by the slot's name. A longitudinal failure names the treatment at the
time point that failed and the outcome its specification declares, and
neither need be the question's. So which slots copy the question is
declared per statement, the two that do not are declared with them, and
the declaration is bound at import to every statement ``themis.gaps``
declares with such a slot.

A gap's own occasion is one of those statements. ``IF_PROVIDED`` speaks
it under the gap's kind, and until the walk named it so, the 304
rewrites of an ill-defined intervention's own ``said`` had no statement
to be declared under.

And a question has more roles than an effect's two. A proximal one also
names the confounder nobody measured and the proxies standing in for it
on each side, and seven statements copy those: 48 rewrites of them
passed every door while the roles were read off an effect's fields.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

from tests.answer_corpus import the_door_for
from themis.kernel import _premises_of
from themis.types import Atom, EffectQuery, Intervention, ProximalEffectQuery, ValuedAtom
from themis.verifier.context import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import (
    _COPIED_FROM,
    _COPIES_THE_QUESTION,
    _NOT_THE_QUESTIONS,
    _ROLES,
    every_said_mapping,
    holds_a_name,
    statements_and_the_slots_they_declare,
    verify_gap_quotes,
)
from themis.verifier.rules import _atom_label_verifier

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

COPIES = {(statement, slot)
          for statement, slots in _COPIES_THE_QUESTION.items()
          for slot in slots}

#: (answer, path to the ``said``, statement, slot) for every slot the corpus
#: writes as a copy of the question.
SITES = sorted(
    (name, where, statement, slot)
    for name, pair in SHAPES.items()
    for where, statement, said in every_said_mapping(
        pair["result"].get("data_gap_report") or {})
    for slot in said
    if (statement, slot) in COPIES
)
ANSWERS = sorted({site[0] for site in SITES})
CONTEXTS = {name: _premises_of(SHAPES[name]["program"],
                               SHAPES[name]["result"])[3]
            for name in ANSWERS}


def _said(result, where):
    node = result["data_gap_report"]
    for step in where.split("."):
        node = node[int(step)] if step.isdigit() else node[step]
    return node


def _the_questions(context, slot) -> tuple[Atom, ...]:
    """Which atoms the question puts in the role, restated per question
    rather than read off the rule. A proxy role is a set."""
    query = context.query
    if slot == "latent":
        return (query.latent,)
    if slot == "z":
        return tuple(query.treatment_proxy)
    if slot == "w":
        return tuple(query.outcome_proxy)
    acts = slot in ("intervention", "treatment")
    if isinstance(query, ProximalEffectQuery):
        return (query.treatment if acts else query.outcome,)
    if acts:
        return (query.intervention.atom,)
    return (getattr(query.target, "atom", query.target),)


def _spellings(atoms) -> set[str]:
    return {spelt for atom in atoms
            for spelt in (atom.predicate, _atom_label_verifier(atom))}


def _predicates(context) -> set[str]:
    atoms = set(context.graph.nodes)
    if context.theta is not None:
        atoms |= set(context.theta.domains)
    for pair in context.bidirected or ():
        atoms |= set(pair)
    return {atom.predicate for atom in atoms}


# --------------------------------------------------------- the declaration


def test_every_role_slot_says_whether_it_copies_the_question():
    """Bound both ways: a slot named after a role, where its statement files
    it as a name, is declared a copy or declared not one, and nothing else
    is declared."""
    roles = {pair for pair in statements_and_the_slots_they_declare()
             if pair[1] in _ROLES and holds_a_name(*pair)}
    assert roles == COPIES | set(_NOT_THE_QUESTIONS)
    assert not COPIES & set(_NOT_THE_QUESTIONS)
    assert (len(COPIES), len(_NOT_THE_QUESTIONS)) == (62, 2)


_SAYS = {
    "intervention": "the question's intervention",
    "treatment": "the question's intervention",
    "target": "the question's target",
    "outcome": "the question's target",
    "latent": "the question's latent confounder",
    "z": "the question's treatment-side proxies",
    "w": "the question's outcome-side proxies",
}


def test_a_copy_is_in_the_copy_table_under_its_role():
    assert set(_SAYS) == set(_ROLES)
    for statement, slot in COPIES:
        says, _build, lists = _COPIED_FROM[(statement, slot)]
        assert says == _SAYS[slot], (statement, slot)
        assert lists is False
    for pair in _NOT_THE_QUESTIONS:
        assert pair not in _COPIED_FROM, pair


def test_the_corpus_writes_the_copies_it_writes():
    """The denominator, per slot, and the statements no answer shape
    reaches."""
    split: dict[str, int] = {}
    for _name, _where, _statement, slot in SITES:
        split[slot] = split.get(slot, 0) + 1
    assert split == {"intervention": 588, "target": 28,
                     "treatment": 21, "outcome": 18,
                     "latent": 4, "z": 5, "w": 3}, split
    unseen = COPIES - {(statement, slot) for _n, _w, statement, slot in SITES}
    assert unseen == {
        ("feedback_loop_needs_an_instrument", "treatment"),
        ("feedback_loop_needs_an_instrument", "outcome"),
        ("feedback_loop_outside_the_simultaneous_case", "treatment"),
        ("feedback_loop_outside_the_simultaneous_case", "outcome"),
        ("the_proxy_channel_is_singular", "latent"),
        ("the_proxy_channel_is_singular", "z"),
        ("the_proxy_channel_is_singular", "w"),
    }


# -------------------------------------------------------------- the honest side


@pytest.mark.parametrize("name", ANSWERS)
def test_every_honest_copy_is_the_questions_own_atom(name):
    """In one of the two spellings a gap gives an atom, and the rule
    accepts the answer."""
    result, context = SHAPES[name]["result"], CONTEXTS[name]
    for site_name, where, statement, slot in SITES:
        if site_name != name:
            continue
        assert _said(result, where)[slot] in _spellings(
            _the_questions(context, slot)), (where, slot)
    verify_gap_quotes(result, context)


def test_the_same_atom_in_its_other_spelling_is_the_same_copy():
    """The loop family writes ``x()`` where the rest write ``x``. Either is
    the question's atom, and neither is refused for being the other."""
    accepted = 0
    for name, where, _statement, slot in SITES:
        context = CONTEXTS[name]
        for spelt in _spellings(_the_questions(context, slot)):
            forged = copy.deepcopy(SHAPES[name]["result"])
            _said(forged, where)[slot] = spelt
            verify_gap_quotes(forged, context)
            accepted += 1
    assert accepted == 2 * len(SITES) == 1334, accepted


# --------------------------------------------------------------- the teeth


def test_another_variable_the_problem_has_is_refused():
    """Every other predicate the problem has, at every site. Each one is a
    word the name rule has to pass."""
    refused = 0
    for name, where, _statement, slot in SITES:
        context = CONTEXTS[name]
        own = {atom.predicate for atom in _the_questions(context, slot)}
        for other in sorted(_predicates(context) - own):
            forged = copy.deepcopy(SHAPES[name]["result"])
            _said(forged, where)[slot] = other
            with pytest.raises(VerificationError, match="the question's"):
                verify_gap_quotes(forged, context)
            refused += 1
    assert refused == 1568, refused


@pytest.mark.parametrize("statement,slot", sorted(
    {(statement, slot) for _n, _w, statement, slot in SITES}))
def test_the_door_refuses_it_on_every_statement_the_corpus_writes(
        statement, slot):
    name, where, _s, _k = next(site for site in SITES
                               if site[2:] == (statement, slot))
    context = CONTEXTS[name]
    own = {atom.predicate for atom in _the_questions(context, slot)}
    other = sorted(_predicates(context) - own)[0]
    forged = copy.deepcopy(SHAPES[name]["result"])
    _said(forged, where)[slot] = other
    with pytest.raises(VerificationError):
        the_door_for(SHAPES[name]["result"])(SHAPES[name]["program"], forged)


# --------------------------------------------------------------- the silences


def _synthetic(sentence: str, said: dict, query) -> tuple[dict, VerificationContext]:
    graph = nx.DiGraph()
    graph.add_nodes_from(Atom(p, ()) for p in ("x", "y", "a1"))
    context = VerificationContext(graph=graph, query=query)
    report = {"gaps": [{"describes": [{"sentence": sentence, "said": said}]}]}
    return {"data_gap_report": report}, context


_EFFECT = EffectQuery(
    target=ValuedAtom(Atom("y", ()), True),
    intervention=Intervention(Atom("x", ()), True),
    given=(),
)


def test_a_slot_declared_not_the_questions_is_not_held_to_it():
    """A longitudinal failure's treatment is the one at the time point that
    failed. The same word under a loop statement is the question's."""
    said = {"treatment": "a1", "time": 1, "outcome": "y"}
    result, context = _synthetic("sequential_exchangeability_fails", said,
                                 _EFFECT)
    verify_gap_quotes(result, context)
    result, context = _synthetic("the_treatment_is_inside_a_declared_loop",
                                 said, _EFFECT)
    with pytest.raises(VerificationError, match="the question's intervention"):
        verify_gap_quotes(result, context)


def test_a_question_without_the_role_says_nothing():
    """A question with no intervention and no treatment has no such role to
    appeal to, and the rule is silent rather than refusing an answer it has
    nothing to judge by."""

    class _Q:
        pass

    result, context = _synthetic("the_treatment_is_inside_a_declared_loop",
                                 {"treatment": "a1", "outcome": "y"}, _Q())
    verify_gap_quotes(result, context)
