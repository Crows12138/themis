"""A question asked two ways is answered alike.

P(y | do(x), given) is one estimand whether it is asked as an effect or as
an identify query, and the two spellings answered it by different
preconditions. The identify query refused a stratum holding any descendant
of the treatment, a back-door criterion's precondition standing in front of
an identifier that does not need it: of 161 such random questions the
effect spelling identified 123, and the identifier agreed on all 161. A
stratum holding the treatment or the outcome went the other way. The
identify query refused it; the effect query sent it down the routes, to come
back as an effect the graph does not identify, with data to collect for it.

Holding the treatment fixed beside setting it, or the outcome beside asking
for it, is no stratum an effect is asked of, and no graph identifies it or
fails to. That is now the one precondition both spellings ask before any
route is offered the question (``themis.types.ends_the_given_holds``), and a
descendant of the treatment is the identifier's. On 700 random programs the
two spellings answered 424 questions differently and now answer none.

The verifier holds the refusal where the dispatch gives it. Given before any
route, it leaves no route's verdict to be the question's, the loop's among
them; and it is the whole answer. Answers the routes gave such questions
before the dispatch asked -- mediation decompositions and transported
estimands on a treatment held fixed -- passed every door, and so did the
refusal with its item removed. The loop's withdrawal is owed by the answers
a route gives, and the rule asking for it refused this refusal wherever a
loop reaches the question.
"""
from __future__ import annotations

import copy
import itertools
import random

import pytest

import themis
from themis.verifier.errors import VerificationError

REFUSAL = "given_holds_the_treatment_or_outcome"
UNIDENTIFIABLE = {"admg_effect_not_identifiable",
                  "conditional_admg_not_identifiable", "no_c_factor_witness",
                  "admg_effect_reachable_only_by_instrument",
                  "no_backdoor_or_frontdoor"}
BEFORE_ANY_ROUTE = "refused before any route"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _valued(p):
    return {"atom": _atom(p), "value": True}


#: c confounds x and y, and w; d and m carry the effect of x; w is a second
#: treatment where the question asks for one.
EDGES = (("c", "x"), ("c", "y"), ("x", "y"), ("x", "d"), ("d", "y"),
         ("c", "w"), ("w", "y"), ("x", "m"), ("m", "y"))


def _program(given, *, kind="effect", asked=None, declared=(), edges=EDGES,
             latent=(), names=("c", "x", "y", "d", "w", "m"), options=None):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in names]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    statements += list(declared)
    if kind == "identify":
        query = {"kind": "identify",
                 "intervention": {"atom": _atom("x"), "value": True},
                 "target": _atom("y"), "given": [_atom(g) for g in given]}
    else:
        query = {"kind": "effect", "intervention": _valued("x"),
                 "target": _valued("y"),
                 "given": [_valued(g) for g in given], **(asked or {})}
    program = {"version": "0.1",
               "domain": {"objects": [{"kind": "object", "name": "me"}]},
               "statements": statements + [
                   {"kind": "query", "id": "q", "query": query}]}
    if options is not None:
        program["options"] = options
    return program


def _answer(program):
    return themis.run(copy.deepcopy(program))["results"][0]


def _needs(answer):
    return [m["need"] for m in answer.get("missing_information") or ()]


def _accepted(program, answer):
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))
    if answer.get("data_gap_report") is not None:
        themis.verify_refusal(copy.deepcopy(program), copy.deepcopy(answer))
    if (answer.get("derivation") or {}).get("steps"):
        themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def _population(affected):
    return ({"target_population": "real_world"},
            ({"kind": "selection_node", "id": "S", "affects": _atom(affected),
              "source_population": "trial",
              "target_population": "real_world"},))


#: Every shape the effect query carries, as what it asks and what the
#: program declares beside it.
SHAPES = {
    "an effect": (None, ()),
    "a joint effect": ({"extra_interventions": [_valued("w")]}, ()),
    "a mediated effect": ({"mediator": _atom("m")}, ()),
    "an effect through a mediator block": (
        {"mediators": [_atom("m"), _atom("d")]}, ()),
    "an effect in another population": _population("c"),
    "an effect a loop reaches": (
        None, ({"kind": "feedback", "left": _atom("d"), "right": _atom("y")},)),
    "an effect under latent confounding": (
        None, ({"kind": "bidirected", "left": _atom("x"),
                "right": _atom("y")},)),
}

HELD = {"the treatment": ("x",), "the outcome": ("y",),
        "the outcome beside a covariate": ("c", "y")}


@pytest.mark.parametrize("held", sorted(HELD))
@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_a_given_holding_an_end_is_refused_before_any_route(shape, held):
    asked, declared = SHAPES[shape]
    program = _program(HELD[held], asked=asked, declared=declared)
    answer = _answer(program)
    assert answer["status"] == "needs_investigation"
    assert _needs(answer) == [REFUSAL]
    [item] = answer["missing_information"]
    assert item["name"] == "query:effect_given"
    _accepted(program, answer)


def test_the_second_treatment_of_a_joint_effect_is_an_end():
    program = _program(("w",), asked=SHAPES["a joint effect"][0])
    answer = _answer(program)
    assert _needs(answer) == [REFUSAL]
    _accepted(program, answer)


@pytest.mark.parametrize("held", sorted(HELD))
def test_asked_as_an_identify_query_it_is_refused_alike(held):
    program = _program(HELD[held], kind="identify")
    answer = _answer(program)
    assert _needs(answer) == [REFUSAL]
    assert answer["missing_information"][0]["name"] == "query:identify_given"
    _accepted(program, answer)


@pytest.mark.parametrize("kind", ["effect", "identify"])
def test_a_descendant_of_the_treatment_is_the_identifiers(kind):
    program = _program(("d",), kind=kind)
    answer = _answer(program)
    assert REFUSAL not in _needs(answer)
    assert answer.get("formula") is not None
    _accepted(program, answer)


@pytest.mark.parametrize("kind", ["effect", "identify"])
def test_the_framing_gate_still_speaks_first(kind):
    """Strict framing stops an effect question before anything else is
    asked of it, and an identify query has no such gate."""
    program = _program(("x",), kind=kind, options={"strict_framing": True})
    answer = _answer(program)
    expected = {"effect": {"framing_fields_unfilled"}, "identify": {REFUSAL}}
    assert set(_needs(answer)) == expected[kind]
    _accepted(program, answer)


def _shaped(shape, given):
    asked, declared = SHAPES[shape] if isinstance(shape, str) else shape
    return _program(given, asked=asked, declared=declared)


#: A route's verdict on a question conditioning on nothing, the stratum the
#: same question holds an end in, and the verdict.
VERDICTS = {
    "a loop's": ("an effect a loop reaches", ("x",),
                 "feedback_loop_outside_the_simultaneous_case"),
    "latent confounding's": ("an effect under latent confounding", ("y",),
                             "admg_effect_not_identifiable"),
    "transport's": (_population("y"), ("x",), "transport_not_identifiable"),
    "a joint effect's": (
        (SHAPES["a joint effect"][0],
         ({"kind": "bidirected", "left": _atom("w"), "right": _atom("y")},)),
        ("w",), "joint_effect_not_identifiable"),
}


@pytest.mark.parametrize("verdict", sorted(VERDICTS))
def test_no_route_s_verdict_is_written_on_it(verdict):
    shape, held, need = VERDICTS[verdict]
    donor = _answer(_shaped(shape, ()))
    assert _needs(donor) == [need]
    with pytest.raises(VerificationError, match=BEFORE_ANY_ROUTE):
        themis.verify_refusal(_shaped(shape, held), donor)


#: A route's answer to a question conditioning on nothing, and the stratum
#: the same question holds an end in.
ANSWERS = {
    "a mediation decomposition": ("a mediated effect", ("x",)),
    "a decomposition through a mediator block": (
        "an effect through a mediator block", ("y",)),
    "a transported estimand": ("an effect in another population", ("x",)),
    "a joint back-door estimand": ("a joint effect", ("w",)),
}


@pytest.mark.parametrize("routed", sorted(ANSWERS))
def test_no_route_s_answer_is_its_answer(routed):
    shape, held = ANSWERS[routed]
    donor = _answer(_shaped(shape, ()))
    assert donor["status"] == "structurally_solved"
    with pytest.raises(VerificationError, match=BEFORE_ANY_ROUTE):
        themis.verify_answer_claims(_shaped(shape, held), donor)


def test_the_refusal_is_the_whole_answer():
    program = _shaped("an effect a loop reaches", ("x",))
    honest = _answer(program)
    stripped = copy.deepcopy(honest)
    stripped["missing_information"] = []
    with pytest.raises(VerificationError, match=BEFORE_ANY_ROUTE):
        themis.verify_answer_claims(program, stripped)
    beside = copy.deepcopy(honest)
    beside["missing_information"].append(copy.deepcopy(_answer(_shaped(
        "an effect a loop reaches", ()))["missing_information"][0]))
    with pytest.raises(VerificationError, match=BEFORE_ANY_ROUTE):
        themis.verify_answer_claims(program, beside)
    with pytest.raises(VerificationError, match=BEFORE_ANY_ROUTE):
        themis.verify_refusal(program, beside)


def _random_questions(seed, count):
    """Latent programs whose stratum is drawn from every variable, the
    treatment and the outcome among them. No loops: the identify query does
    not read them."""
    rng = random.Random(seed)
    for _ in range(count):
        names = ("x", "y", "c", "d", "e", "f")[: rng.choice([5, 6])]
        order = list(names)
        rng.shuffle(order)
        density = rng.choice([0.3, 0.45, 0.6])
        edges = tuple((order[p], order[q])
                      for p, q in itertools.combinations(range(len(names)), 2)
                      if rng.random() < density)
        chance = rng.choice([0.0, 0.15, 0.3])
        latent = tuple(pair for pair in itertools.combinations(names, 2)
                       if rng.random() < chance)
        given = tuple(rng.sample(names, rng.choice([1, 1, 2])))
        yield {kind: _program(given, kind=kind, edges=edges, latent=latent,
                              names=names)
               for kind in ("effect", "identify")}


def _verdict(answer):
    needs = set(_needs(answer))
    if REFUSAL in needs:
        return BEFORE_ANY_ROUTE
    rules = {s["rule"] for s in (answer.get("derivation") or {}).get("steps")
             or ()}
    if needs & UNIDENTIFIABLE or "tian_hedge_witness" in rules:
        return "not identified"
    return "identified" if answer.get("formula") is not None else sorted(needs)


@pytest.mark.parametrize("index", range(30))
def test_both_spellings_reach_one_verdict(index):
    spellings = list(_random_questions(693, 30))[index]
    answers = {kind: _answer(program) for kind, program in spellings.items()}
    assert _verdict(answers["effect"]) == _verdict(answers["identify"])
    for kind, program in spellings.items():
        _accepted(program, answers[kind])
