"""A yes-or-no met at one of its values is still a yes-or-no.

``build_theta`` read the domain of a variable no declaration names off the
values its statements met it at. The kernel asks for ``P(v=True)`` and leaves
``P(v=False)`` to completion (``fewest_to_ask``), so a reader who answered
exactly what was asked made ``v`` a variable of one value. Completion then
skipped it, a sum over it ran over ``True`` alone, and the next ask dropped
every cell of it that completion had been counted on to fill. On the demo's
question about a history major, answering three rounds of asks gave an
interventional risk of 0.009: the one term of a 32-term back-door sum that
had been asked for, times the five marginals asked beside it.

Pinned here:

- the rule: a variable met only at booleans has both, a category met at one
  value keeps what it was met at, and a declaration wins over either;
- the shape that raised it: a marginal the graph does not license, then the
  back door's ask, answered — the number is the back door's, not one term;
- the property the rule is for: answering exactly what the kernel asks with
  the numbers of one distribution ends at that distribution's interventional
  probability, and the verifier accepts the answer.
"""
from __future__ import annotations

import copy
import random
from itertools import product

import pytest

import themis
from themis import kernel
from themis.runtime import theta_builder
from themis.runtime.instantiation import instantiate
from themis.runtime.numeric_estimator import ProbabilityKey, RangeReadShort
from themis.types import Atom


def _a(name):
    return {"predicate": name, "args": []}


def _p(target, value, given, p):
    return {"kind": "probability",
            "target": {"atom": _a(target), "value": value},
            "given": [{"atom": _a(g), "value": v} for g, v in given],
            "value": p, "annotations": {"source": "a study"}}


def _program(variables, edges, statements, x_value=True):
    """Variables declared without a domain, as the demo's translation
    writes them."""
    body = [{"kind": "variable", "predicate": v} for v in variables]
    body += [{"kind": "cause", "from": _a(a), "to": _a(b)} for a, b in edges]
    body += list(statements)
    body.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": _a("x"), "value": x_value},
        "target": {"atom": _a("y"), "value": True}}})
    return {"version": "0.1", "domain": {"objects": []}, "statements": body}


def _asked(result):
    return [item["skeleton"]
            for request in result.get("investigation_requests") or ()
            for item in request.get("items") or ()
            if (item.get("skeleton") or {}).get("kind") == "probability"]


def _answer_until_solved(program, conditional, rounds=6):
    """Run, answer every probability asked with ``conditional``, run again."""
    for _ in range(rounds):
        result = themis.run(copy.deepcopy(program))["results"][0]
        asked = _asked(result)
        if not asked:
            return program, result
        for stub in asked:
            filled = copy.deepcopy(stub)
            filled["value"] = conditional(
                stub["target"]["atom"]["predicate"], stub["target"]["value"],
                [(g["atom"]["predicate"], g["value"]) for g in stub["given"]])
            filled["annotations"] = {"source": "a study"}
            program["statements"].insert(-1, filled)
    raise AssertionError(f"still asking after {rounds} rounds")


# --- the rule ----------------------------------------------------------------

def _built(*statements, declared=None):
    program = _program(("x", "y", "z", "w"), [("z", "x"), ("x", "y")],
                       statements)
    for statement in program["statements"]:
        if statement["kind"] == "variable" and declared \
                and statement["predicate"] in declared:
            statement["domain"] = declared[statement["predicate"]]
    prog = kernel.validate_program(
        kernel.validate_ast(kernel._to_ast(program)))
    return theta_builder.build_theta(instantiate(prog))


Z, W = Atom(predicate="z", args=()), Atom(predicate="w", args=())


def test_a_boolean_met_at_one_value_has_both_and_the_other_is_completed():
    theta = _built(_p("z", True, [], 0.4))
    assert theta.domain_of(Z) == (False, True)
    assert theta.get(ProbabilityKey(target_atom=Z, target_value=False,
                                    given=frozenset())) == pytest.approx(0.6)


def test_a_boolean_met_only_in_a_condition_has_both():
    theta = _built(_p("y", True, [("z", False)], 0.3))
    assert theta.domain_of(Z) == (False, True)


def test_a_category_met_at_one_value_keeps_what_it_was_met_at():
    """Nothing says what else a category takes; a yes-or-no is two values
    whichever of them was named."""
    theta = _built(_p("w", "high", [], 1.0))
    assert theta.domain_of(W) == ("high",)


def test_a_category_met_at_one_value_with_part_of_the_mass_has_no_range():
    """0.4 at the only value named is the numbers saying there are others.
    The store keeps what was met and refuses to enumerate it: the range is
    not known, and a sum over the one value would be 0.4 of an answer."""
    theta = _built(_p("w", "high", [], 0.4))
    assert W in theta.short
    with pytest.raises(RangeReadShort):
        theta.domain_of(W)


def test_a_declaration_wins_over_the_values_met():
    theta = _built(_p("w", "high", [], 0.4),
                   declared={"w": ["high", "low"]})
    assert theta.domain_of(W) == ("high", "low")


# --- the shape that raised it -------------------------------------------------

#: z confounds x and y; the reader first supplies the marginal P(y | x) a
#: study reports, which the graph does not license for the effect.
P_Z = 0.4
P_Y = {(True, True): 0.8, (True, False): 0.5,
       (False, True): 0.6, (False, False): 0.2}          # P(y=T | x, z)
P_X = {True: 0.7, False: 0.3}                            # P(x=T | z)


def _backdoor_truth():
    return P_Z * P_Y[(True, True)] + (1 - P_Z) * P_Y[(True, False)]


def _backdoor_conditional(target, value, given):
    joint = {}
    for x, z, y in product((True, False), repeat=3):
        pz = P_Z if z else 1 - P_Z
        px = P_X[z] if x else 1 - P_X[z]
        py = P_Y[(x, z)] if y else 1 - P_Y[(x, z)]
        joint[(x, y, z)] = pz * px * py
    names = ("x", "y", "z")
    pick = lambda row, pairs: all(row[names.index(n)] == v for n, v in pairs)
    den = sum(p for row, p in joint.items() if pick(row, given))
    return sum(p for row, p in joint.items()
               if pick(row, given + [(target, value)])) / den


def test_the_back_door_asked_after_a_marginal_is_the_back_door_not_one_term():
    marginal = _backdoor_conditional("y", True, [("x", True)])
    program = _program(("x", "y", "z"),
                       [("z", "x"), ("z", "y"), ("x", "y")],
                       [_p("y", True, [("x", True)], marginal)])
    program, result = _answer_until_solved(program, _backdoor_conditional)
    assert result["status"] == "numerically_solved"
    value = result["numeric_result"]["value"]
    assert value == pytest.approx(_backdoor_truth())
    assert value != pytest.approx(P_Z * P_Y[(True, True)])
    themis.verify(copy.deepcopy(program), result)


# --- the property ------------------------------------------------------------

def _case(seed):
    """A random binary model: confounders of x and y, perhaps a chain
    among them and a mediator, and a few marginals of it supplied first."""
    rng = random.Random(seed)
    k = rng.randint(1, 3)
    cs = [f"c{i}" for i in range(k)]
    parents = {c: [] for c in cs}
    if k > 1 and rng.random() < 0.5:
        parents["c1"] = ["c0"]
    parents["x"] = [c for c in cs if rng.random() < 0.7] or [cs[0]]
    into_y = [c for c in cs if rng.random() < 0.7] or [parents["x"][0]]
    variables = cs + ["x"]
    if rng.random() < 0.4:
        parents["m"] = ["x"]
        parents["y"] = ["m"] + into_y
        variables.append("m")
    else:
        parents["y"] = ["x"] + into_y
    variables.append("y")
    cpt = {v: {row: round(rng.uniform(0.1, 0.9), 3)
               for row in product((True, False), repeat=len(parents[v]))}
           for v in variables}
    x_value = rng.random() < 0.5

    def joint(fixed=None):
        out = {}
        for row in product((True, False), repeat=len(variables)):
            a = dict(zip(variables, row))
            if fixed and any(a[n] != v for n, v in fixed.items()):
                continue
            p = 1.0
            for v in variables:
                if fixed and v in fixed:
                    continue
                q = cpt[v][tuple(a[u] for u in parents[v])]
                p *= q if a[v] else 1 - q
            out[row] = p
        return out

    observed = joint()

    def conditional(target, value, given):
        pick = lambda row, pairs: all(
            row[variables.index(n)] == v for n, v in pairs)
        den = sum(p for row, p in observed.items() if pick(row, given))
        return sum(p for row, p in observed.items()
                   if pick(row, list(given) + [(target, value)])) / den

    truth = sum(p for row, p in joint({"x": x_value}).items()
                if row[variables.index("y")])
    supplied = [_p("y", True, [("x", xv)], conditional("y", True, [("x", xv)]))
                for xv in (True, False) if rng.random() < 0.6]
    if rng.random() < 0.5:
        supplied.append(_p("x", True, [], conditional("x", True, [])))
    edges = [(u, v) for v in variables for u in parents.get(v, ())]
    return (_program(variables, edges, supplied, x_value=x_value),
            conditional, truth)


@pytest.mark.parametrize("seed", range(30))
def test_answering_what_is_asked_ends_at_the_models_answer(seed):
    program, conditional, truth = _case(seed)
    program, result = _answer_until_solved(program, conditional)
    assert result["status"] == "numerically_solved", result["status"]
    assert result["numeric_result"]["value"] == pytest.approx(truth, abs=1e-9)
    themis.verify(copy.deepcopy(program), result)


def test_the_cases_start_from_a_marginal_the_graph_does_not_license():
    """Where nothing is supplied first, every variable is asked for in the
    first round at both values of its conditions, and no domain is read off
    a single value — the property would hold without the rule."""
    started = sum(
        any(s["kind"] == "probability" for s in _case(seed)[0]["statements"])
        for seed in range(30))
    assert started >= 15, started
