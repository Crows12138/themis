"""Which unidentifiable verdict an answer names is held to its question.

A gap's kind says what repairs it and its species says which verdict the
answer reached: that no back-door or front-door set exists, that an ADMG's
effect is reachable only by an instrument, that a joint effect or a
transported one is not identified. ``Need.gap`` holds the first on the
member. Nothing held the second, and on the envelope the pick is one token.

Measured before the change, with the producer made to name another species
of the same kind -- so every copy, the report and the routes it offers agree
-- the strongest door took 125 such answers across the corpus: an answer an
instrument had already computed, told that nothing identifies it and to go
and find an instrument; a single treatment's effect told its joint effect is
not identified; an effect question given the verdict only a counterfactual
conjunction or an identify query can reach.

Each species is reached from one kind of question, and the four the effect
cascade's last resort raises from one graph shape as well. What must hold is
stated per species and every copy is held to it. The verdict that no
instrument reaches the effect and the verdict that one does are one search's
two outcomes, so each is held to what a search of the same reach finds.
"""
from __future__ import annotations

import inspect
import json
import pathlib

import networkx as nx
import pytest

import themis
from tests.answer_corpus import the_door_for
from themis import gaps
from themis.kernel import _refusal_facts
from themis.runtime import structural_solver
from themis.types import (
    Atom, EffectQuery, GapKind, Intervention, ValuedAtom,
)
from themis.verifier import refusal_rules
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import RefusalFacts, verify_species_claims

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures"
                     / "answer_shapes.json").read_text(encoding="utf-8"))
KIND = GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET
SPECIES = sorted(str(m) for m in gaps.Need if m.gap is KIND)


def _written(result):
    """The species of this kind an answer writes. The walk yields every
    species a table in that module judges, so which kind is asked here."""
    return sorted({str(s) for _, s, _ in refusal_rules._species_written(result)
                   if s.gap is KIND})


CARRIERS = {name: _written(pair["result"]) for name, pair in SHAPES.items()
            if _written(pair["result"])}

#: One stored answer per species the corpus writes.
ONE_EACH = {}
for _name in sorted(CARRIERS):
    for _species in CARRIERS[_name]:
        ONE_EACH.setdefault(_species, _name)


def test_every_species_of_the_kind_states_the_question_it_answers():
    assert sorted(str(m) for m in refusal_rules._ANSWERS) == SPECIES


def test_the_corpus_still_writes_most_of_them():
    """A gate over no stored answer holds nothing."""
    assert sorted(ONE_EACH) == [
        "admg_effect_not_identifiable",
        "admg_effect_reachable_only_by_instrument",
        "joint_effect_not_identifiable",
        "proximal_not_identifiable",
        "sequential_exchangeability_fails",
        "transport_not_identifiable",
    ]


@pytest.mark.parametrize("name", sorted(CARRIERS))
def test_every_stored_verdict_is_one_its_question_can_reach(name):
    program, result = SHAPES[name]["program"], SHAPES[name]["result"]
    verify_species_claims(result, _refusal_facts(program, result["query_id"]))


def _answered_as(monkeypatch, program, query_id, old, new):
    """The program run with the producer naming ``new`` where it named
    ``old``: every copy, the report and its routes come out of the real
    pipeline, as they would from a wrong pick."""
    real = gaps.missing

    def missing(*, need, **rest):
        return real(need=gaps.Need(new) if str(need) == old else need, **rest)

    monkeypatch.setattr(gaps, "missing", missing)
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == query_id)
    monkeypatch.setattr(gaps, "missing", real)
    assert old not in _written(result) and new in _written(result)
    return result


def _swaps(rows):
    return [(name, old, new) for name, species in sorted(rows.items())
            for old in species for new in SPECIES if new != old]


@pytest.mark.parametrize("name,old,new", _swaps(
    {name: [old] for old, name in ONE_EACH.items()}))
def test_another_verdict_of_the_same_kind_is_refused(monkeypatch, name, old, new):
    program = SHAPES[name]["program"]
    query_id = SHAPES[name]["result"]["query_id"]
    forged = _answered_as(monkeypatch, program, query_id, old, new)
    with pytest.raises(VerificationError, match=new):
        verify_species_claims(forged, _refusal_facts(program, query_id))
    with pytest.raises(VerificationError):
        the_door_for(forged)(program, forged)


#: Every stored answer the effect cascade's last resort wrote about an
#: instrument, whichever conditioning set the instrument needed.
BY_INSTRUMENT = {
    name: species for name, species in CARRIERS.items()
    if set(species) & {"admg_effect_not_identifiable",
                       "admg_effect_reachable_only_by_instrument"}}


@pytest.mark.parametrize("name,old,new", [
    swap for swap in _swaps(BY_INSTRUMENT)
    if swap[2] in ("admg_effect_not_identifiable",
                   "admg_effect_reachable_only_by_instrument")])
def test_the_other_instrument_verdict_is_refused_on_every_stored_answer(
        monkeypatch, name, old, new):
    """A stratified Wald ratio's answer told that no instrument reaches it
    was the case the bare-instrument check let through."""
    program = SHAPES[name]["program"]
    query_id = SHAPES[name]["result"]["query_id"]
    forged = _answered_as(monkeypatch, program, query_id, old, new)
    with pytest.raises(VerificationError, match=new):
        verify_species_claims(forged, _refusal_facts(program, query_id))


# ------------------------------------------------------- the instrument pair
def A(name):
    return Atom(predicate=name, args=())


def _facts(edges, *, latent=(("x", "y"),)):
    graph = nx.DiGraph()
    graph.add_edges_from((A(u), A(v)) for u, v in edges)
    graph.add_nodes_from(A(n) for pair in latent for n in pair)
    return RefusalFacts(
        graph=graph,
        bidirected=frozenset(frozenset({A(u), A(v)}) for u, v in latent),
        query=EffectQuery(target=ValuedAtom(atom=A("y"), value=True),
                          intervention=Intervention(atom=A("x"), value=True),
                          given=()))


def _names(species):
    return {"missing_information": [{"need": species}]}


NONE = "admg_effect_not_identifiable"
SOME = "admg_effect_reachable_only_by_instrument"
FOUR = [(f"c{i}", end) for i in range(4) for end in ("z", "y")]

#: Graphs on which x and y share a latent cause, and what each says about
#: the two verdicts that differ by an instrument.
INSTRUMENTS = {
    "an instrument needing nothing conditioned": (
        [("z", "x"), ("x", "y")],
        {NONE: "z is an instrument for it with nothing conditioned", SOME: None}),
    # z shares a cause c with y, so z is an instrument given c.
    "an instrument given what confounds it with the outcome": (
        [("z", "x"), ("x", "y"), ("c", "z"), ("c", "y")],
        {NONE: "z is an instrument for it with c conditioned", SOME: None}),
    "no instrument under any set": (
        [("x", "y"), ("c", "x"), ("c", "y")],
        {NONE: None, SOME: "no node is an instrument"}),
    # Four confounders of z and y: an instrument given all four, past the
    # reach of the search the two verdicts come out of.
    "an instrument only past the search's reach": (
        [("z", "x"), ("x", "y"), *FOUR],
        {NONE: None, SOME: "no node is an instrument"}),
    # z reaches y through d, which x also causes: z is an instrument given
    # d, and holding a mediator fixed is not the effect.
    "an instrument only given a descendant of the treatment": (
        [("z", "x"), ("x", "y"), ("z", "d"), ("d", "y"), ("x", "d")],
        {NONE: None, SOME: "no node is an instrument"}),
}


@pytest.mark.parametrize("graph,species", [
    (graph, species) for graph, (_, says) in sorted(INSTRUMENTS.items())
    for species in sorted(says)])
def test_the_instrument_verdicts_are_one_search_s_two_outcomes(graph, species):
    edges, says = INSTRUMENTS[graph]
    facts = _facts(edges)
    expected = says[species]
    if expected is None:
        verify_species_claims(_names(species), facts)
    else:
        with pytest.raises(VerificationError, match=expected):
            verify_species_claims(_names(species), facts)


@pytest.mark.parametrize("graph", sorted(INSTRUMENTS))
def test_the_search_they_are_held_to_is_the_one_they_come_out_of(graph):
    """Of the same reach as the producer's: one shorter refutes an honest
    "an instrument reaches it", one longer an honest "none does"."""
    facts = _facts(INSTRUMENTS[graph][0])
    produced = structural_solver.iv_sets(
        facts.graph, A("x"), A("y"), bidirected=facts.bidirected)
    assert bool(produced) == (refusal_rules._an_instrument_found(facts) is not None)
    reach = inspect.signature(structural_solver.iv_sets).parameters[
        "max_conditioning_size"].default
    assert refusal_rules._CONDITIONING_SEARCHED == reach


def test_a_verdict_about_latent_confounding_on_a_graph_without_it_is_refused():
    facts = _facts([("z", "x"), ("x", "y")], latent=())
    with pytest.raises(VerificationError, match="no latent confounding"):
        verify_species_claims(_names(NONE), facts)
    verify_species_claims(_names("no_backdoor_or_frontdoor"), facts)
