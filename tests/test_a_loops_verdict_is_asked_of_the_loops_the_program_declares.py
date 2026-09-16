"""A loop's verdict is a claim about the loops the program declares.

A declared reciprocal loop the estimand reaches ends an effect question in
one of two refusals. Between the treatment and the outcome, and the only loop
there, it is the two-equation system, and what it lacks is an instrument that
survives the loop. Anywhere else, or beside a second loop, it is outside the
case that has a remedy. Both are the program's to settle -- which loops it
declares, what they reach, whether an instrument survives -- and neither had
a witness, so the three copies of each were held to each other and to
nothing else.

Measured before the witnesses: put beside a program where the claim is
false, 70 were accepted at the door that reads only what the program settles
-- no loop declared, a loop that reaches nothing, the loop elsewhere, an
instrument that survives -- and 5 at every door that reads the answer, each
a program with an instrument the refusal said was not there. One copy's
species swapped for the other, 24 at that door. Bent at every copy, the loop
a copy names and the question's two ends passed every door.

The instrument is searched with the reach the verdict claims, the loop
entering as a latent pair between the two ends; the tests below hold that
reach at both edges. Every witness errs toward accepting: a loop named the
other way round, or any of several loops the estimand reaches, is the same
claim.
"""
from __future__ import annotations

import copy

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis.verifier.errors import VerificationError

NEEDS = "feedback_loop_needs_an_instrument"
OUTSIDE = "feedback_loop_outside_the_simultaneous_case"
NAMES = ("x", "y", "z", "m", "w", "c", "p", "q", "a1", "a2", "a3", "a4")


def _a(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*edges, loops=(), latent=(), given=(), query="effect"):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in NAMES]
    statements += [{"kind": "cause", "from": _a(a), "to": _a(b)}
                   for a, b in edges]
    statements += [{"kind": "feedback", "left": _a(a), "right": _a(b)}
                   for a, b in loops]
    statements += [{"kind": "bidirected", "left": _a(a), "right": _a(b)}
                   for a, b in latent]
    if query == "effect":
        asked = {"kind": "effect",
                 "intervention": {"atom": _a("x"), "value": True},
                 "target": {"atom": _a("y"), "value": True},
                 "given": [{"atom": _a(g), "value": True} for g in given]}
    else:
        asked = {"kind": "identify", "target": _a("y"),
                 "intervention": {"atom": _a("x"), "value": True},
                 "given": []}
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [
                {"kind": "query", "id": "q", "query": asked}]}


_XY = ("x", "y")
_PATH = (("x", "m"), ("m", "y"))


def _confounded_instrument(paths):
    """z -> x -> y, and z sharing a cause with y along each of ``paths``
    back doors: an instrument with that many nodes conditioned."""
    return [("z", "x"), _XY] + [
        edge for i in range(1, paths + 1)
        for edge in ((f"a{i}", "z"), (f"a{i}", "y"))]


#: Honest answers, and the species each is.
HONEST = {
    "a loop between the two ends, and nothing else": (
        _program(_XY, loops=[_XY]), NEEDS),
    "an instrument confounded with the outcome": (
        _program(("z", "x"), _XY, loops=[_XY], latent=[("z", "y")]), NEEDS),
    "an instrument, and the effect in a stratum": (
        _program(("z", "x"), _XY, ("w", "y"), loops=[_XY], given=["w"]),
        NEEDS),
    "an instrument only four conditioned nodes would free": (
        _program(*_confounded_instrument(4), loops=[_XY]), NEEDS),
    "a loop between the two ends, and one that reaches nothing": (
        _program(_XY, loops=[_XY, ("p", "q")]), NEEDS),
    "a loop between a mediator and the outcome": (
        _program(*_PATH, loops=[("m", "y")]), OUTSIDE),
    "a loop between the treatment and a mediator": (
        _program(*_PATH, loops=[("x", "m")]), OUTSIDE),
    "a loop between a cause of the outcome and the outcome": (
        _program(_XY, ("w", "y"), loops=[("w", "y")]), OUTSIDE),
    "the two ends' loop, a second through the outcome, an instrument": (
        _program(("z", "x"), _XY, loops=[_XY, ("y", "c")]), OUTSIDE),
}

#: The honest answer beside a program where what it says is false.
ELSEWHERE = {
    "an instrument survives the loop": (
        "a loop between the two ends, and nothing else",
        _program(("z", "x"), _XY, loops=[_XY])),
    "an instrument survives with a node conditioned": (
        "a loop between the two ends, and nothing else",
        _program(("z", "x"), ("w", "z"), ("w", "y"), _XY, loops=[_XY])),
    "an instrument three conditioned nodes free": (
        "an instrument only four conditioned nodes would free",
        _program(*_confounded_instrument(3), loops=[_XY])),
    "a second loop reaches the estimand": (
        "a loop between the two ends, and nothing else",
        _program(_XY, loops=[_XY, ("y", "c")])),
    "the loop is between a mediator and the outcome": (
        "a loop between the two ends, and nothing else",
        _program(*_PATH, _XY, loops=[("m", "y")])),
    "no loop is declared": (
        "a loop between the two ends, and nothing else", _program(_XY)),
    "the only loop reaches nothing": (
        "a loop between the two ends, and nothing else",
        _program(_XY, loops=[("p", "q")])),
    "the question is an identification": (
        "a loop between the two ends, and nothing else",
        _program(_XY, loops=[_XY], query="identify")),
    "the one loop is between the two ends": (
        "a loop between a mediator and the outcome",
        _program(*_PATH, _XY, loops=[_XY])),
    "no loop is declared, for the other verdict": (
        "a loop between a mediator and the outcome", _program(*_PATH)),
    "the loop declared reaches nothing": (
        "a loop between a mediator and the outcome",
        _program(*_PATH, loops=[("p", "q")])),
}

#: A detail bent, and whether what it then says is still true.
BENT = {
    "a loop the program does not declare": (
        "a loop between the two ends, and nothing else",
        {"left": "z(me)", "right": "y(me)"}, False),
    "the two ends' loop the other way round": (
        "a loop between the two ends, and nothing else",
        {"left": "y(me)", "right": "x(me)"}, True),
    "the question's ends swapped": (
        "a loop between the two ends, and nothing else",
        {"treatment": "y(me)", "outcome": "x(me)"}, False),
    "the treatment renamed to a bystander": (
        "a loop between a mediator and the outcome",
        {"treatment": "w(me)"}, False),
    "the two ends' loop, where it is not declared": (
        "a loop between a mediator and the outcome",
        {"left": "x(me)", "right": "y(me)"}, False),
    "a declared loop the estimand does not reach": (
        "a loop between the two ends, and one that reaches nothing",
        {"left": "p(me)", "right": "q(me)"}, False),
    "the other of two loops that reach it": (
        "the two ends' loop, a second through the outcome, an instrument",
        {"left": "x(me)", "right": "y(me)"}, True),
}


def _run(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


@pytest.fixture(scope="module")
def answers():
    return {name: _run(program) for name, (program, _) in HONEST.items()}


def _copies(node, species):
    if isinstance(node, dict):
        if node.get("need") == species:
            yield node
        for value in node.values():
            yield from _copies(value, species)
    elif isinstance(node, list):
        for item in node:
            yield from _copies(item, species)


def _bend(result, species, facts, only=None):
    forged = copy.deepcopy(result)
    for index, holder in enumerate(_copies(forged, species)):
        if only is None or index == only:
            holder["said"].update(facts)
    return forged


def _swap(result, species, other, only):
    forged = copy.deepcopy(result)
    list(_copies(forged, species))[only]["need"] = other
    return forged


@pytest.mark.parametrize("name", sorted(HONEST))
def test_an_honest_loop_verdict_is_accepted(name, answers):
    program, species = HONEST[name]
    result = answers[name]
    assert len(list(_copies(result, species))) == 3, name
    verify_honestly(program, result)
    themis.verify_refusal(program, result)


@pytest.mark.parametrize("name", sorted(ELSEWHERE))
def test_beside_a_program_where_it_is_false_it_is_refused(name, answers):
    honest, program = ELSEWHERE[name]
    species = HONEST[honest][1]
    with pytest.raises(VerificationError, match=f"says '{species}'"):
        themis.verify_refusal(program, answers[honest])
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(program, answers[honest])


@pytest.mark.parametrize("name", sorted(BENT))
def test_the_loop_and_the_ends_are_held_at_every_copy_and_at_each_one(
        name, answers):
    honest, facts, true = BENT[name]
    program, species = HONEST[honest]
    result = answers[honest]
    if true:
        verify_honestly(program, _bend(result, species, facts))
        themis.verify_refusal(program, _bend(result, species, facts))
        return
    with pytest.raises(VerificationError):
        themis.verify_answer_claims(program, _bend(result, species, facts))
    for index in range(3):
        with pytest.raises(VerificationError, match=f"says '{species}'"):
            themis.verify_refusal(
                program, _bend(result, species, facts, only=index))


@pytest.mark.parametrize("honest", [
    "a loop between the two ends, and nothing else",
    "a loop between a mediator and the outcome",
])
def test_one_copy_saying_the_other_verdict_is_refused(honest, answers):
    program, species = HONEST[honest]
    other = OUTSIDE if species == NEEDS else NEEDS
    for index in range(3):
        with pytest.raises(VerificationError, match=f"says '{other}'"):
            themis.verify_refusal(
                program, _swap(answers[honest], species, other, index))
