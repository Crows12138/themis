"""A population nothing separates is asked of one population.

An effect question may name a target population in a program that declares
no selection node. Nothing is then declared to differ, the effect carries to
that population as it stands, and the transport route says so on its block.
What it carried was the transport formula's source factor with no source:
``P(y | x)``, which stands for the effect only in a domain where the
treatment was randomised, and in the one population there is asserts that
nothing confounds it. On 300 random five-variable graphs the verifier's own
model refused 118 of those answers -- all 78 whose outcome is upstream of
the treatment -- while the same questions without the population passed.
Put a corpus question's treatment and outcome the other way round and it is
one of them.

The carried effect is now identified by the routes that identify the one
population's question, and the block stays on the answer as the disclosure
it was. The refusal rules read the same thing: a population nothing
separates asks the one population's total effect, and only a population a
selection node separates can fail to transport.
"""
from __future__ import annotations

import copy
import itertools
import json
import pathlib
import random

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis import gaps
from themis.kernel import _refusal_facts
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import verify_species_claims

SHAPES = json.loads((pathlib.Path(__file__).parent / "fixtures"
                     / "answer_shapes.json").read_text(encoding="utf-8"))
NAMES = ("a", "b", "c", "d", "e")


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(edges, x, y, *, latent=(), mediator=None, population="clinic"):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in NAMES]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    query = {"kind": "effect",
             "intervention": {"atom": _atom(x), "value": True},
             "target": {"atom": _atom(y), "value": True}, "given": []}
    if mediator:
        query["mediator"] = _atom(mediator)
    if population:
        query["target_population"] = population
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [
                {"kind": "query", "id": "q", "query": query}]}


def _answer(program):
    return themis.run(program)["results"][0]


def _one_population(program):
    plain = copy.deepcopy(program)
    query = plain["statements"][-1]["query"]
    query.pop("target_population")
    query.pop("mediator", None)
    return plain


def _the_block_says_nothing_separates(answer):
    block = answer["extensions"]["transport_identification"]
    assert block["s_nodes"] == []
    [route] = block["sources"]
    assert route["source_population"] is None and route["transportable"]


def _corpus_questions_nothing_separates():
    """The corpus rows asking about a population the program declares no
    boundary to, read by what they are: a row's name is a digest of the
    shapes it carries, and it moves whenever the answer does."""
    return sorted(
        name for name, pair in SHAPES.items()
        if not any(s["kind"] == "selection_node"
                   for s in pair["program"]["statements"])
        and any(s["query"].get("target_population")
                for s in pair["program"]["statements"]
                if s["kind"] == "query"))


def test_the_corpus_asks_a_question_nothing_separates():
    assert _corpus_questions_nothing_separates()


@pytest.mark.parametrize("name", _corpus_questions_nothing_separates())
def test_the_corpus_question_the_other_way_round(name):
    program = copy.deepcopy(SHAPES[name]["program"])
    query = program["statements"][-1]["query"]
    query["intervention"]["atom"], query["target"]["atom"] = (
        query["target"]["atom"], query["intervention"]["atom"])
    answer = _answer(program)
    plain = copy.deepcopy(program)
    plain["statements"][-1]["query"].pop("target_population")
    assert answer["formula"] == _answer(plain)["formula"]
    _the_block_says_nothing_separates(answer)
    verify_honestly(program, answer)


def _programs():
    rng = random.Random(691)
    found = []
    for i in range(16):
        order = list(NAMES)
        rng.shuffle(order)
        edges = tuple((order[p], order[q])
                      for p, q in itertools.combinations(range(5), 2)
                      if rng.random() < 0.4)
        x, y = rng.sample(NAMES, 2)
        latent = tuple(pair for pair in itertools.combinations(NAMES, 2)
                       if i % 2 and rng.random() < 0.25)
        mediator = rng.choice([n for n in NAMES if n not in (x, y)]) \
            if i % 3 == 0 else None
        found.append((edges, x, y, latent, mediator))
    return found


@pytest.mark.parametrize("edges, x, y, latent, mediator", _programs())
def test_the_answer_is_the_one_populations(edges, x, y, latent, mediator):
    program = _program(edges, x, y, latent=latent, mediator=mediator)
    answer = _answer(program)
    plain = _answer(_one_population(program))
    for field in ("status", "formula", "numeric_result"):
        assert answer.get(field) == plain.get(field), field
    assert ([m["need"] for m in answer.get("missing_information") or ()]
            == [m["need"] for m in plain.get("missing_information") or ()])
    _the_block_says_nothing_separates(answer)
    verify_honestly(program, answer)
    themis.verify_refusal(program, answer)


def test_the_formula_it_used_to_carry_is_refused():
    """y -> x, the effect of x on y: nothing is between them to adjust for,
    and the conditional is not the effect."""
    program = _program((("y", "x"),), "x", "y")
    answer = copy.deepcopy(_answer(program))
    answer["formula"] = {
        "kind": "probability_ref",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": True}]}
    with pytest.raises(VerificationError, match="not the one this graph"):
        themis.verify_answer_claims(program, answer)


def _answered_as(monkeypatch, program, old, new):
    real = gaps.missing

    def missing(*, need, **rest):
        if str(need) != old:
            return real(need=need, **rest)
        swapped = gaps.Need(new)
        # The name a row is filed under follows its species, so the half a
        # site supplies follows it too. This forgery is of a kernel that
        # raised the OTHER species, and such a kernel would have handed
        # over that species' half; keeping this call's is forging a
        # producer that cannot exist, which gaps.filed says rather than
        # building a name for it.
        rest.pop("channel", None)
        rest.pop("subject", None)
        if swapped in gaps.FILED_UNDER:
            rest["subject"] = "the_forged_occasion"
        elif swapped in gaps.FILED_ABOUT:
            rest["channel"] = "mediation"
        return real(need=swapped, **rest)

    monkeypatch.setattr(gaps, "missing", missing)
    result = _answer(program)
    monkeypatch.setattr(gaps, "missing", real)
    return result


def _latent_program():
    program = _program((("a", "b"),), "a", "b", latent=(("a", "b"),))
    answer = _answer(program)
    assert [m["need"] for m in answer["missing_information"]] == [
        "admg_effect_not_identifiable"]
    return program, answer


def test_a_population_nothing_separates_cannot_fail_to_transport(monkeypatch):
    program, _ = _latent_program()
    forged = _answered_as(monkeypatch, program, "admg_effect_not_identifiable",
                          "transport_not_identifiable")
    with pytest.raises(VerificationError, match="across no declared boundary"):
        verify_species_claims(forged, _refusal_facts(program, "q"))


def test_a_verdict_the_one_population_does_not_reach_is_refused():
    """The refusal moved onto the same question over a graph with latent
    confounding where the one population's effect is still identified: the
    search finds the adjustment set it says does not exist."""
    _, answer = _latent_program()
    identified = _program((("c", "a"), ("c", "b"), ("a", "b")), "a", "b",
                          latent=(("a", "c"),))
    assert {m["need"] for m in _answer(identified)["missing_information"]} == {
        "theta_entry_missing"}
    with pytest.raises(VerificationError,
                       match="satisfies the backdoor criterion"):
        themis.verify_refusal(identified, answer)
