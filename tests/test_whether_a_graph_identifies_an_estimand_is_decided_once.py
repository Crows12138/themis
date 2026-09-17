"""Whether a graph identifies an estimand is decided once.

A refusal saying an effect is not identified is refuted where the door can
exhibit identification. It could exhibit two things: an adjustment set, and
a front door through at most two mediators. The kernel identifies more than
that, by products of c-factors, and every effect whose outcome does not
descend from the treatment is among them. On 700 random latent programs a
kernel refusal moved onto the 659 questions it answers was accepted 133
times: 132 identified by c-factors, and one by a front door that needs a
back door closed first. The same estimand asked as an identify query had no
witness read at all, and moved refusals were accepted on 76 of 120
unconditioned identify queries the kernel answers and on every one of 246
conditioned. The front door also answered for a question asked of a
stratum, and refuted an honest refusal.

The chain's hedge verdict was held to a third criterion: that the treatment
shares a c-component of the outcome's ancestors with a child of its own. It
is not necessary. In the napkin graph the outcome is such a child, the
kernel identifies the effect, and a hedge verdict for it was accepted.

What decides it now is one function, Tian's Identify after the Rule-2
exchange of the stratum, and both doors ask it. On 823 random programs of
five and six variables it agrees with the kernel's identifier on every
one; the sweep at the bottom keeps a sample of that measurement.

Its first version also answered questions it has nothing to say about. A
stratum holding the treatment or the outcome poses no identification
question; the decision stripped the treatment from it and called the rest
identified, which refuted the kernel's refusals of those questions, and it
crashed on the outcome. The question it decides now names two different
nodes and a stratum holding neither, and it says so of anything else.
"""
from __future__ import annotations

import copy
import itertools
import random

import networkx as nx
import pytest

import themis
from themis.kernel import _refusal_facts
from themis.types import (
    Atom, ConstTerm, DerivationStep, IdentifyQuery, Intervention, StepRef,
    StructuralResult,
)
from themis.verifier import VerificationContext, verify_identify
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import verify_refusal_claims
from themis.verifier.rules import interventions_the_graph_identifies

UNIDENTIFIABLE = {"admg_effect_not_identifiable",
                  "conditional_admg_not_identifiable", "no_c_factor_witness",
                  "admg_effect_reachable_only_by_instrument"}


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(edges, latent=(), *, given=(), kind="effect",
             names=("a", "b", "c", "d", "e")):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in names]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    if kind == "identify":
        query = {"kind": "identify",
                 "intervention": {"atom": _atom("a"), "value": True},
                 "target": _atom("b"), "given": [_atom(g) for g in given]}
    else:
        query = {"kind": "effect",
                 "intervention": {"atom": _atom("a"), "value": True},
                 "target": {"atom": _atom("b"), "value": True},
                 "given": [{"atom": _atom(g), "value": True} for g in given]}
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [
                {"kind": "query", "id": "q", "query": query}]}


def _answer(program):
    return themis.run(copy.deepcopy(program))["results"][0]


def _needs(answer):
    return {m["need"] for m in answer.get("missing_information") or ()}


#: The effect of a on b, a refusal of which is the truth: a bow arc.
BLOCKED = _program((("a", "b"),), (("a", "b"),))


@pytest.fixture(scope="module")
def refusal():
    answer = _answer(BLOCKED)
    assert _needs(answer) == {"admg_effect_not_identifiable"}
    return answer


def _moved(refusal):
    return copy.deepcopy(refusal["data_gap_report"])


#: Effects the kernel identifies with neither an adjustment set nor a front
#: door through at most two mediators.
C_FACTOR_ONLY = {
    "the outcome does not descend from the treatment":
        _program((("a", "c"),), (("a", "b"),)),
    "napkin":
        _program((("c", "d"), ("d", "a"), ("a", "b")),
                 (("c", "a"), ("c", "b"))),
    "a front door only once a back door is closed":
        _program((("d", "a"), ("d", "e"), ("a", "e"), ("c", "e"), ("e", "b")),
                 (("a", "b"), ("a", "c"), ("b", "c"))),
}


@pytest.mark.parametrize("name", sorted(C_FACTOR_ONLY))
def test_a_refusal_of_an_effect_the_c_factors_identify_is_refuted(
        name, refusal):
    program = C_FACTOR_ONLY[name]
    assert _answer(program).get("formula") is not None
    with pytest.raises(VerificationError, match="c-factors of this graph"):
        verify_refusal_claims(_moved(refusal), _refusal_facts(program, "q"))


@pytest.mark.parametrize("name", sorted(C_FACTOR_ONLY))
def test_asked_as_an_identify_query_it_is_the_same_estimand(name, refusal):
    program = copy.deepcopy(C_FACTOR_ONLY[name])
    identify = _program(
        [(s["from"]["predicate"], s["to"]["predicate"])
         for s in program["statements"] if s["kind"] == "cause"],
        [(s["left"]["predicate"], s["right"]["predicate"])
         for s in program["statements"] if s["kind"] == "bidirected"],
        kind="identify")
    assert _answer(identify)["status"] == "structurally_solved"
    with pytest.raises(VerificationError, match="c-factors of this graph"):
        verify_refusal_claims(_moved(refusal), _refusal_facts(identify, "q"))


def test_the_front_door_does_not_speak_for_a_stratum():
    """P(b | do(a), c): the effect runs through e, and c is a child of a
    sharing a latent cause with b. The joint distribution of b and c under
    do(a) has a hedge, and the kernel's refusal is honest."""
    program = _program((("a", "e"), ("a", "c"), ("a", "d"), ("e", "b")),
                       (("a", "b"), ("b", "c"), ("b", "d")), given=("c",))
    answer = _answer(program)
    assert _needs(answer) == {"conditional_admg_not_identifiable"}
    themis.verify_refusal(program, answer)


#: Strata holding the treatment and the outcome, on graphs where the
#: decision's first version called the question identified or crashed.
NO_QUESTION = {
    "the treatment": ((("b", "c"), ("b", "e"), ("b", "a"), ("c", "e"),
                       ("c", "d")), (("d", "e"),), ("a",)),
    "the outcome": ((("b", "d"), ("b", "a"), ("d", "e"), ("a", "c")),
                    (("b", "c"),), ("b",)),
}


@pytest.mark.parametrize("kind", ["effect", "identify"])
@pytest.mark.parametrize("held", sorted(NO_QUESTION))
def test_a_stratum_holding_the_treatment_or_the_outcome_is_no_question(
        held, kind):
    edges, latent, given = NO_QUESTION[held]
    program = _program(edges, latent, given=given, kind=kind)
    themis.verify_refusal(program, _answer(program))
    facts = _refusal_facts(program, "q")
    q = facts.query
    y = q.target if isinstance(q, IdentifyQuery) else q.target.atom
    stratum = frozenset(q.given) if isinstance(q, IdentifyQuery) else frozenset(
        g.atom for g in q.given)
    with pytest.raises(ValueError, match="holds neither"):
        interventions_the_graph_identifies(
            facts.graph, facts.bidirected, q.intervention.atom, y, stratum)
    chain = _hedge_chain(facts.graph, q.intervention.atom, y)
    ctx = VerificationContext(
        graph=facts.graph, bidirected=facts.bidirected,
        query=IdentifyQuery(target=y, intervention=q.intervention,
                            given=tuple(stratum)))
    with pytest.raises(VerificationError, match="no identification question"):
        verify_identify(chain, ctx, StructuralResult(value=False))


def _hedge_chain(graph, x, y):
    """A hedge verdict over this graph, built the way tests/test_tian_id.py
    builds one."""
    return (
        DerivationStep(rule="tian_c_decomposition",
                       inputs={"graph": graph, "x": x, "y": y},
                       output=True, step_id="s1"),
        DerivationStep(rule="tian_hedge_witness",
                       inputs={"decomposition": StepRef(step_id="s1")},
                       output=StructuralResult(value=False), step_id="s2"),
    )


def _napkin_hedge_chain():
    me = ConstTerm(name="me")
    w1, w2, x, y = (Atom(predicate=p, args=(me,)) for p in ("c", "d", "a", "b"))
    graph = nx.DiGraph()
    graph.add_edges_from([(w1, w2), (w2, x), (x, y)])
    bidirected = frozenset({frozenset({w1, x}), frozenset({w1, y})})
    query = IdentifyQuery(target=y, intervention=Intervention(atom=x, value=True),
                          given=())
    return _hedge_chain(graph, x, y), VerificationContext(
        graph=graph, query=query, bidirected=bidirected)


def test_a_hedge_verdict_is_held_to_the_same_decision():
    """The napkin graph: the outcome is a child of the treatment in its
    c-component, which the hedge rule read as a hedge."""
    chain, ctx = _napkin_hedge_chain()
    assert interventions_the_graph_identifies(
        ctx.graph, ctx.bidirected, ctx.query.intervention.atom,
        ctx.query.target) is not None
    with pytest.raises(VerificationError, match="c-factors of this graph"):
        verify_identify(chain, ctx, StructuralResult(value=False))


def _random_programs(seed, count):
    rng = random.Random(seed)
    for _ in range(count):
        names = "abcdef"[: rng.choice([5, 6])]
        order = list(names)
        rng.shuffle(order)
        density = rng.choice([0.3, 0.45, 0.6])
        edges = tuple((order[p], order[q])
                      for p, q in itertools.combinations(range(len(names)), 2)
                      if rng.random() < density)
        chance = rng.choice([0.15, 0.3])
        latent = tuple(pair for pair in itertools.combinations(names, 2)
                       if rng.random() < chance)
        kind = rng.choice(["effect", "identify"])
        given = tuple(rng.sample(names[2:], rng.choice([0, 0, 1, 2])))
        yield _program(edges, latent, given=given, kind=kind, names=names)


def _kernel_identifies(answer):
    rules = {s["rule"] for s in (answer.get("derivation") or {}).get("steps")
             or ()}
    if _needs(answer) & UNIDENTIFIABLE or "tian_hedge_witness" in rules:
        return False
    return True if answer.get("formula") is not None else None


@pytest.mark.parametrize("index", range(40))
def test_the_decision_is_the_identifiers_and_both_doors_hold_it(
        index, refusal):
    program = list(_random_programs(692, 40))[index]
    answer = _answer(program)
    kernel = _kernel_identifies(answer)
    facts = _refusal_facts(program, "q")
    q = facts.query
    x = q.intervention.atom
    y = q.target if isinstance(q, IdentifyQuery) else q.target.atom
    given = frozenset(q.given) if isinstance(q, IdentifyQuery) else frozenset(
        g.atom for g in q.given)
    ours = interventions_the_graph_identifies(
        facts.graph, facts.bidirected, x, y, given) is not None
    if kernel is not None:
        assert ours == kernel
    themis.verify_refusal(program, answer)
    if kernel:
        with pytest.raises(VerificationError,
                           match="adjusting for|front-door|c-factors"):
            verify_refusal_claims(_moved(refusal), facts)
