"""A decomposition is asked of the stratum it names.

A mediation question conditioning on something was answered with the
decomposition of the question without it. The identifier took no stratum,
so its conditions were read on the adjustment set alone, and the verifier
re-read them the same way; the numeric step's conditioning was the
producer's to state. On random ADMGs the routes claimed identifiability for
strata holding something the treatment causes, the mediator among them,
and for strata of what it does not cause where the total effect within the
stratum is not identified, so the natural effects summing to it cannot both
be. Every one passed every door.

Within a stratum of what the treatment does not cause, the natural and
controlled effects are identified by the same conditions with the stratum
among the covariates: every condition is read on W together with it, and W
is drawn from the rest (``structural_solver.mediation_sets``). A stratum
holding something the treatment causes holds no one population whose effect
could be decomposed -- which people fall in it depends on the value the
treatment is set to -- and that is the answer. The verifier reads the stratum
off the question, as the general-ID criterion does: in the four checks, in
the block's re-derivation, and in the numeric step's conditioning.
"""
from __future__ import annotations

import copy

import networkx as nx
import pytest

import themis
from themis.runtime import structural_solver
from themis.types import (
    Atom, ConstTerm, EffectQuery, Intervention, ValuedAtom)
from themis.verifier import VerificationContext
from themis.verifier.errors import RuleCheckFailed, VerificationError
from themis.verifier.rules import (
    _rule_mediation_cde_check,
    _rule_mediation_cde_joint_check,
    _rule_mediation_nde_nie_check,
    _rule_mediation_nde_nie_joint_check,
)

REFUSAL = "decomposition_within_a_stratum_the_treatment_moves"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _node(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _program(edges, given, *, latent=(), asked=None, declared=(), names=None):
    names = names or sorted({n for edge in (*edges, *latent) for n in edge})
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in names]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _atom(a), "right": _atom(b)}
                   for a, b in latent]
    statements += list(declared)
    query = {"kind": "effect",
             "intervention": {"atom": _atom("x"), "value": True},
             "target": {"atom": _atom("y"), "value": True},
             "given": [{"atom": _atom(g), "value": v} for g, v in given],
             **(asked or {"mediator": _atom("m")})}
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [
                {"kind": "query", "id": "q", "query": query}]}


def _answer(program):
    return themis.run(copy.deepcopy(program))["results"][0]


def _accepted(program, answer):
    themis.verify_answer_claims(copy.deepcopy(program), copy.deepcopy(answer))
    if answer.get("data_gap_report") is not None:
        themis.verify_refusal(copy.deepcopy(program), copy.deepcopy(answer))
    if (answer.get("derivation") or {}).get("steps"):
        themis.verify(copy.deepcopy(program), copy.deepcopy(answer))


def _refused(door, program, answer):
    with pytest.raises(VerificationError):
        getattr(themis, door)(copy.deepcopy(program), copy.deepcopy(answer))


def _block(answer):
    ext = answer.get("extensions") or {}
    return (ext.get("mediation_decomposition")
            or ext.get("mediation_joint_decomposition"))


def _graph(edges):
    g = nx.DiGraph()
    g.add_edges_from((_node(a), _node(b)) for a, b in edges)
    return g


#: x and y share a latent cause of k each: k is a collider between them, and
#: conditioning on it opens a path nothing observed closes.
COLLIDER = (("x", "m"), ("m", "y"), ("x", "y"))
COLLIDER_LATENT = (("x", "k"), ("k", "y"))

#: c is a common effect of a (a cause of x) and b (a cause of y): nothing to
#: adjust for without it, and a or b to adjust for beside it.
OPENED = (("a", "x"), ("a", "c"), ("b", "c"), ("b", "y"),
          ("x", "m"), ("m", "y"), ("x", "y"))

#: x causes d, m and (through m) e; c causes x and y.
CAUSED = (("c", "x"), ("c", "y"), ("x", "d"), ("d", "y"), ("x", "m"),
          ("m", "y"), ("x", "y"), ("m", "e"))

SHAPES = {
    "one mediator": {"mediator": _atom("m")},
    "a mediator block": {"mediators": [_atom("m"), _atom("d")]},
}


# ------------------------------------------------------------ the identifier

def test_a_stratum_that_opens_a_path_withdraws_the_claim():
    g = _graph(COLLIDER)
    bidirected = frozenset(frozenset({_node(a), _node(b)})
                           for a, b in COLLIDER_LATENT)
    x, y, m, k = (_node(n) for n in ("x", "y", "m", "k"))
    g.add_node(k)
    plain = structural_solver.mediation_sets(g, x, y, m, bidirected=bidirected)
    within = structural_solver.mediation_sets(
        g, x, y, m, given=(k,), bidirected=bidirected)
    assert plain.nde_nie.identifiable and plain.cde.identifiable
    assert (within.nde_nie.identifiable, within.cde.identifiable) == (False, False)
    assert (within.nde_nie.failed_condition, within.cde.failed_condition) == (
        "M1", "C1")


def test_a_stratum_that_opens_a_path_is_adjusted_beside():
    g = _graph(OPENED)
    x, y, m, c = (_node(n) for n in ("x", "y", "m", "c"))
    plain = structural_solver.mediation_sets(g, x, y, m)
    within = structural_solver.mediation_sets(g, x, y, m, given=(c,))
    assert plain.nde_nie.adjustment == frozenset()
    for attempt in (within.nde_nie, within.cde):
        assert attempt.identifiable
        assert attempt.adjustment in ({_node("a")}, {_node("b")})
    joint = structural_solver.mediation_sets_joint(
        g, x, y, frozenset({m}), given=(c,))
    assert joint.nde_nie.adjustment in ({_node("a")}, {_node("b")})


@pytest.mark.parametrize("held", ["m", "d", "e"])
def test_a_stratum_the_treatment_causes_is_not_searched(held):
    g = _graph(CAUSED)
    x, y = _node("x"), _node("y")
    given = (_node("c"), _node(held))
    single = structural_solver.mediation_sets(g, x, y, _node("m"), given=given)
    joint = structural_solver.mediation_sets_joint(
        g, x, y, frozenset({_node("m"), _node("d")}), given=given)
    for result in (single, joint):
        assert result.stratum_moved == {_node(held)}
        assert not result.nde_nie.identifiable and not result.cde.identifiable
    assert not structural_solver.mediation_sets(
        g, x, y, _node("m"), given=(_node("c"),)).stratum_moved


# ------------------------------------------------------------- the dispatch

@pytest.mark.parametrize("shape", SHAPES)
@pytest.mark.parametrize("given", [(("m", True),), (("c", False), ("e", True)),
                                   (("d", True), ("m", False))])
def test_a_decomposition_within_a_moved_stratum_is_refused(shape, given):
    program = _program(CAUSED, given, asked=SHAPES[shape])
    answer = _answer(program)
    assert answer["status"] == "needs_investigation"
    assert [item["need"] for item in answer["missing_information"]] == [REFUSAL]
    moved = [f"{g}(me)" for g, _ in given if g != "c"]
    assert answer["missing_information"][0]["said"] == {"atoms": ", ".join(moved)}
    assert _block(answer) is None
    _accepted(program, answer)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_refusal_is_the_whole_answer(shape):
    program = _program(CAUSED, (("m", True),), asked=SHAPES[shape])
    stripped = _answer(program)
    stripped["missing_information"] = []
    _refused("verify_answer_claims", program, stripped)


#: What triggers each route ranked above the decomposition, beside a
#: mediator and a stratum x causes.
AHEAD = {
    "feedback_loop": ({}, ({"kind": "feedback", "left": _atom("d"),
                            "right": _atom("y")},)),
    "joint_intervention": (
        {"extra_interventions": [{"atom": _atom("c"), "value": True}]}, ()),
    "transport": (
        {"target_population": "real_world"},
        ({"kind": "selection_node", "id": "S", "affects": _atom("c"),
          "source_population": "trial", "target_population": "real_world"},)),
}


def test_the_door_reads_the_routes_ranked_above_the_decomposition():
    """The refusal is owed where the question reaches the mediation routes,
    and the door reads what triggers each route ranked above them; the
    longitudinal strategy question is the one not exercised below."""
    from themis import routing

    first = min(r.precedence for r in routing.EFFECT_ROUTES
                if r.id in ("mediation_joint", "mediation_single"))
    assert {r.id for r in routing.EFFECT_ROUTES if r.precedence < first} == {
        *AHEAD, "longitudinal"}


@pytest.mark.parametrize("ahead", sorted(AHEAD))
def test_a_route_ranked_above_the_decomposition_answers_first(ahead):
    asked, declared = AHEAD[ahead]
    program = _program(CAUSED, (("m", True),),
                       asked={"mediator": _atom("m"), **asked},
                       declared=declared)
    answer = _answer(program)
    assert REFUSAL not in [item["need"]
                           for item in answer.get("missing_information") or ()]
    _accepted(program, answer)


def test_a_mediator_off_the_paths_is_refused_before_its_stratum():
    program = _program(CAUSED, (("m", True),), asked={"mediator": _atom("c")})
    answer = _answer(program)
    assert [item["need"] for item in answer["missing_information"]] == [
        "mediator_off_the_directed_paths"]
    _accepted(program, answer)


def test_an_unmoved_stratum_is_answered_and_accepted():
    for edges, given, latent in ((OPENED, (("c", True),), ()),
                                 (COLLIDER, (("k", False),), COLLIDER_LATENT),
                                 (CAUSED, (("c", True),), ())):
        for asked in ({"mediator": _atom("m")}, {"mediators": [_atom("m")]}):
            program = _program(edges, given, latent=latent, asked=asked)
            answer = _answer(program)
            assert answer["status"] != "needs_investigation"
            _accepted(program, answer)


# ------------------------------------------------------------- the verifier

def _ctx(graph, given, *, block=False):
    x, y = _node("x"), _node("y")
    mediation = ({"mediators": (_node("m"),)} if block
                 else {"mediator": _node("m")})
    query = EffectQuery(
        target=ValuedAtom(atom=y, value=True),
        intervention=Intervention(atom=x, value=True),
        given=tuple(ValuedAtom(atom=_node(g), value=True) for g in given),
        **mediation)
    return VerificationContext(graph=graph, query=query,
                               bidirected=frozenset())


@pytest.mark.parametrize("rule, block", [
    (_rule_mediation_nde_nie_check, False),
    (_rule_mediation_cde_check, False),
    (_rule_mediation_nde_nie_joint_check, True),
    (_rule_mediation_cde_joint_check, True),
])
def test_a_check_is_read_beside_the_stratum_the_question_names(rule, block):
    g = _graph(OPENED)
    inputs = {"graph": g, "x": _node("x"), "y": _node("y"),
              **({"mediators": frozenset({_node("m")})} if block
                 else {"mediator": _node("m")})}
    # Nothing to adjust for without the stratum ...
    rule(_ctx(g, ()), {**inputs, "adjustment": frozenset()}, True, 0)
    # ... and the same claim beside it is another question's.
    with pytest.raises(RuleCheckFailed):
        rule(_ctx(g, ("c",), block=block),
             {**inputs, "adjustment": frozenset()}, True, 0)
    rule(_ctx(g, ("c",), block=block),
         {**inputs, "adjustment": frozenset({_node("a")})}, True, 0)
    # The stratum is not an adjustment set of its own.
    with pytest.raises(RuleCheckFailed):
        rule(_ctx(g, ("c",), block=block),
             {**inputs, "adjustment": frozenset({_node("a"), _node("c")})},
             True, 0)


@pytest.mark.parametrize("shape", SHAPES)
def test_the_decomposition_asked_without_the_stratum_is_refused_beside_it(shape):
    asked = SHAPES[shape] if shape == "one mediator" else {
        "mediators": [_atom("m")]}
    program = _program(COLLIDER, (("k", True),), latent=COLLIDER_LATENT,
                       asked=asked, names=["k", "m", "x", "y"])
    plain = _answer(_program(COLLIDER, (), latent=COLLIDER_LATENT,
                             asked=asked, names=["k", "m", "x", "y"]))
    assert _block(plain)["nde_nie"]["identifiable"]
    _refused("verify_answer_claims", program, plain)
    _refused("verify", program, plain)


@pytest.mark.parametrize("shape", SHAPES)
def test_a_decomposition_beside_a_moved_stratum_is_refused(shape):
    program = _program(CAUSED, (("m", True),), asked=SHAPES[shape])
    plain = _answer(_program(CAUSED, (), asked=SHAPES[shape]))
    assert _block(plain) is not None
    _refused("verify_answer_claims", program, plain)


def test_the_refusal_is_refuted_where_the_treatment_moves_nothing():
    refusal = _answer(_program(CAUSED, (("m", True),)))
    _refused("verify_refusal", _program(CAUSED, (("c", True),)), refusal)
    misnamed = copy.deepcopy(refusal)
    for holder in (misnamed["missing_information"][0],):
        holder["said"] = {"atoms": "d(me)"}
    _refused("verify_refusal", _program(CAUSED, (("m", True),)), misnamed)


# ------------------------------------------------------- numbers within it

#: c causes y alone: nothing to adjust for with or without it, and the
#: effects within c differ from the population's.
WITHIN = (("c", "y"), ("x", "m"), ("m", "y"), ("x", "y"))
P_C, P_X = 0.35, 0.6
P_M = {True: 0.8, False: 0.3}                                  # given x
P_Y = {(c, m, x): 0.1 + 0.5 * c + 0.2 * m + 0.15 * x - 0.1 * c * x
       for c in (True, False) for m in (True, False) for x in (True, False)}


def _declared():
    def prob(target, given, value):
        return {"kind": "probability",
                "target": {"atom": _atom(target), "value": True},
                "given": [{"atom": _atom(g), "value": v} for g, v in given],
                "value": value}
    out = [prob("c", (), P_C), prob("x", (), P_X)]
    out += [prob("m", (("x", x),), P_M[x]) for x in (True, False)]
    out += [prob("y", (("c", c), ("m", m), ("x", x)), P_Y[(c, m, x)])
            for c, m, x in P_Y]
    return out


def _within(c, outer, inner):
    """E[Y(outer, M(inner)) | c]: m's law does not depend on c here."""
    return sum((P_M[inner] if m else 1 - P_M[inner]) * P_Y[(c, m, outer)]
               for m in (True, False))


@pytest.mark.parametrize("c", [True, False])
def test_the_numbers_within_a_stratum_are_its_own(c):
    program = _program(WITHIN, (("c", c),), declared=_declared())
    answer = _answer(program)
    numeric = _block(answer)["numeric"]
    assert numeric["e_y_treated"] == pytest.approx(_within(c, True, True))
    assert numeric["e_y_control"] == pytest.approx(_within(c, False, False))
    assert numeric["e_y_cross_treated_outer"] == pytest.approx(
        _within(c, True, False))
    assert numeric["e_y_cross_control_outer"] == pytest.approx(
        _within(c, False, True))
    _accepted(program, answer)


def test_numbers_evaluated_within_another_stratum_are_refused():
    """Every step checks out beside the stratum -- nothing to adjust for
    either way -- and the numbers are right about the whole population.
    What is wrong is which population, and that is the numeric step's
    conditioning. The numbers are the chain's to replay: the result-only
    door replays no theta-path number, this one's or any other's."""
    program = _program(WITHIN, (("c", True),), declared=_declared())
    plain = _answer(_program(WITHIN, (), declared=_declared()))
    assert _block(plain)["numeric"]["te"] != pytest.approx(
        _block(_answer(program))["numeric"]["te"])
    _refused("verify", program, plain)
