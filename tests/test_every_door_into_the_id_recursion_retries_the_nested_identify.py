"""Every entry point into the ID recursion retries the full nested Identify.

``c_factor`` answered an ID sub-problem through two doors. ``_run_tian_id``,
for a single or joint effect, retried with Tian's full nested Identify when the
compact Line-7 shortcut punted or leaked, and kept the result only where its
numeric self-check agreed. ``_id_set_structural``, for IDC's numerator and
denominator and for ID*'s base case, ran the shortcut once. Measured after
#661 made the shortcut decline where it had summed an intervention still an
ancestor of the outcome, on random graphs: a conditional effect and a
counterfactual conjunction whose formulas had been right went unanswered, and
before #661 the same door had issued five wrong or ill-formed estimands. The
retry sat with one door because the self-check could ask only about a single
outcome with its intervention's values chosen, which a set sub-problem, built
before any value is stamped, does not have.

The recursion now runs through one function for every door, and the probe asks
about a joint outcome and about an intervention whose values are left open.
"""
from __future__ import annotations

import random

import networkx as nx

from tests.ctf_mc_oracle import counterfactual_prob
from themis.runtime import c_factor
from themis.runtime import ctf_identify as ci
from themis.runtime.numeric_estimator import estimate_formula
from themis.types import (
    Atom, ConstantExpr, ConstTerm, ProbabilityRefExpr, ProductExpr, ValuedAtom,
)
from themis.verifier import semantic_probe as sp


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _admg(names, edges, arcs):
    graph = nx.DiGraph()
    graph.add_nodes_from(_A(p) for p in names)
    graph.add_edges_from((_A(u), _A(v)) for u, v in edges)
    return graph, frozenset(frozenset({_A(u), _A(v)}) for u, v in arcs)


def _open(*atoms):
    return tuple(ValuedAtom(atom=a, value=None) for a in atoms)


# P(f | do(g), a, b): the denominator's shortcut summed an intervention the
# recursion holds at its value; right before #661 only because a and b are
# independent under do(g) in this graph.
CONDITIONAL = _admg(
    "abcdefg",
    [("c", "a"), ("c", "e"), ("c", "f"), ("c", "g"), ("e", "a"), ("e", "d"),
     ("f", "g"), ("g", "a")],
    [("a", "f"), ("b", "f"), ("c", "d"), ("c", "g"), ("e", "f")])

# P(g | do(a), d, b): a sub-formula leaked a variable outside its targets.
LEAKED = _admg(
    "abcdefg",
    [("a", "b"), ("a", "g"), ("c", "a"), ("d", "b"), ("d", "c"), ("d", "e"),
     ("d", "g"), ("e", "c"), ("f", "b"), ("f", "c"), ("f", "g")],
    [("b", "g"), ("c", "d"), ("c", "f"), ("d", "f"), ("d", "g")])

# P(a_{b=true}=true, f=true)
CONJUNCTION = _admg(
    "abcdef",
    [("b", "a"), ("c", "a"), ("d", "b"), ("e", "a"), ("e", "d"), ("e", "f")],
    [("a", "d"), ("c", "d"), ("d", "f")])


def _conditional_verdict(graph, bidirected, x, y, zs, k=5):
    res = c_factor.identify_via_idc(graph, bidirected, x, y, zs, True)
    assert res.identifiable and res.formula is not None, (x, y, zs)
    return sp.probe_identify_formula(
        graph, bidirected, x=x, x_value=True, y=y, given=_open(*zs),
        formula=res.formula, k=k).status


def test_a_conditional_effect_the_shortcut_cannot_give_is_identified_and_computes_its_value():
    graph, bidirected = CONDITIONAL
    assert _conditional_verdict(graph, bidirected, _A("g"), _A("f"), (_A("a"), _A("b"))) == "match"


def test_a_sub_formula_that_leaks_a_variable_is_identified_again_and_computes_its_value():
    graph, bidirected = LEAKED
    assert _conditional_verdict(graph, bidirected, _A("a"), _A("g"), (_A("d"), _A("b"))) == "match"


def test_a_counterfactual_leaf_the_shortcut_cannot_give_is_identified_and_computes_its_value():
    graph, bidirected = CONJUNCTION
    a, b, f = _A("a"), _A("b"), _A("f")
    gamma = (ci.CtfEvent(a, frozenset({(b, True)}), True), ci.CtfEvent(f, frozenset(), True))
    formula = ci.id_star(graph, bidirected, gamma)
    assert formula is not ci.FAIL and formula is not ci.ZERO
    for i in range(2):
        scm = sp._sample_scm(graph, bidirected, {}, random.Random(1000 + i))
        theta = sp._theta_from_scm(scm, formula, graph, bidirected)
        got = estimate_formula(formula, theta, graph=graph, bidirected=bidirected)
        true = counterfactual_prob(scm, graph, gamma, 200000, 50 + i)
        assert abs(got - true) < 0.01, (i, got, true)


def test_the_full_identify_on_a_set_sub_problem_is_held_to_its_numbers(monkeypatch):
    """The retry is kept where the self-check agrees, and only there: with the
    full nested Identify made to return a constant, the conditional effect goes
    unanswered rather than answered wrong."""
    graph, bidirected = CONDITIONAL
    g, f, a, b = _A("g"), _A("f"), _A("a"), _A("b")
    verdicts = []
    real = c_factor._full_line7_numerically_sound

    def spy(*args, **kwargs):
        verdicts.append(real(*args, **kwargs))
        return verdicts[-1]

    monkeypatch.setattr(c_factor, "_full_line7_numerically_sound", spy)
    assert c_factor.identify_via_idc(graph, bidirected, g, f, (a, b), True).identifiable
    assert verdicts == [True]

    verdicts.clear()
    monkeypatch.setattr(c_factor, "_bind_free_params",
                        lambda state, formula, keep: ConstantExpr(value=0.5))
    assert not c_factor.identify_via_idc(graph, bidirected, g, f, (a, b), True).identifiable
    assert verdicts == [False]


def test_no_set_sub_problem_estimand_is_refused_on_random_graphs():
    """Whatever the set-valued door returns, shortcut or full Identify, is a
    formula that validates and computes the joint distribution of its targets
    under every value of its intervention."""
    rng = random.Random(662)
    nodes = [_A(p) for p in "abcdef"]
    seen: dict[str, int] = {}
    for _ in range(300):
        order = rng.sample(nodes, len(nodes))
        graph = nx.DiGraph()
        graph.add_nodes_from(order)
        graph.add_edges_from((u, v) for i, u in enumerate(order)
                             for v in order[i + 1:] if rng.random() < 0.4)
        bidirected = frozenset(frozenset((u, v)) for i, u in enumerate(order)
                               for v in order[i + 1:] if rng.random() < 0.2)
        picked = rng.sample(order, 4)
        x_set = frozenset(picked[:rng.choice((1, 2))])
        y_set = frozenset(picked[2:2 + rng.choice((1, 2))])
        V = frozenset(order)
        topo = tuple(c_factor._admg_topo_order(graph, V))
        formula, _trail, _hedge = c_factor._id_set_structural(
            graph, bidirected, topo, V, x_set=x_set, y_set=y_set)
        if formula is None:
            seen["unidentified"] = seen.get("unidentified", 0) + 1
            continue
        assert c_factor._formula_is_well_formed(formula), (x_set, y_set)
        asked = c_factor._map_valued_atoms(
            formula,
            lambda va, _bound: (ValuedAtom(atom=va.atom, value=None)
                                if va.value is c_factor._IDC_VALUE_SENTINEL else va))
        verdict = sp.probe_intervention_formula(
            graph, bidirected, intervention=dict.fromkeys(x_set),
            outcome=_open(*sorted(y_set, key=c_factor._atom_sort_key)),
            given=(), formula=asked)
        assert not verdict.refuses, (sorted(graph.edges), bidirected, x_set, y_set, verdict)
        seen[verdict.status] = seen.get(verdict.status, 0) + 1
    assert seen.get("match", 0) > 200 and seen.get("unidentified", 0) > 40, seen


def test_an_open_intervention_is_asked_at_every_value():
    x, y = _A("x"), _A("y")
    graph = nx.DiGraph([(x, y)])
    held_open = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=None),
                                   given=(ValuedAtom(atom=x, value=None),))
    held_at_true = ProbabilityRefExpr(target=ValuedAtom(atom=y, value=None),
                                      given=(ValuedAtom(atom=x, value=True),))

    def ask(formula, intervention):
        return sp.probe_intervention_formula(
            graph, frozenset(), intervention=intervention, outcome=_open(y),
            given=(), formula=formula).status

    assert ask(held_open, {x: None}) == "match"
    assert ask(held_at_true, {x: True}) == "match"
    assert ask(held_at_true, {x: None}) == "mismatch"


def test_a_joint_outcome_is_asked_as_one_distribution():
    x, m, y = _A("x"), _A("m"), _A("y")
    graph = nx.DiGraph([(x, m), (m, y)])

    def P(target, *given):
        return ProbabilityRefExpr(target=ValuedAtom(atom=target, value=None),
                                  given=tuple(ValuedAtom(atom=g, value=v) for g, v in given))

    chain = ProductExpr(terms=(P(m, (x, True)), P(y, (m, None))))
    marginal = ProductExpr(terms=(P(m, (x, True)), P(y)))

    def ask(formula):
        return sp.probe_intervention_formula(
            graph, frozenset(), intervention={x: True}, outcome=_open(m, y),
            given=(), formula=formula).status

    assert ask(chain) == "match"
    assert ask(marginal) == "mismatch"
