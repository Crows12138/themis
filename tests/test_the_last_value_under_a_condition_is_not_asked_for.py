"""The last value of a variable under one condition is not asked for.

One variable's probabilities under one condition in one population sum to
one, and ``theta_builder`` completes such a group from all but one of its
values. The callers that collect what an evaluation could not resolve
collected it a cell at a time, so a group lacking every value was listed
whole: an attribution question over four causes with no data asked for 42
numbers where 22 decide them all, and every effect question asked for
``P(z=True)`` beside ``P(z=False)``. A reader following the list writes two
numbers where one decides both — the input #771 has to catch when they do
not sum to one.

The same question had a second wrong answer underneath. A variable the
program declares and supplies no number for took the boolean default, so a
confounder declared low/mid/high was asked for at True and at False, and
the verifier refused the kernel's own ask.

What is pinned here:

- ``fewest_to_ask`` leaves out the last lacking value exactly where the
  collected cells are every value the group lacks, and nowhere else;
- ``Theta.domain_of`` answers a declared variable no statement mentions
  with its declaration;
- on the shapes that raised it, no ask is the remainder of the others, and
  supplying exactly what is asked resolves every parameter;
- the verifier refuses a list that asks for the remainder, reading the
  program rather than the kernel's parameter store.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis import kernel
from themis.runtime import theta_builder
from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.types import Atom
from themis.verifier import investigation_rules
from themis.verifier.errors import VerificationError


def _atom(name: str) -> Atom:
    return Atom(predicate=name, args=())


X, Z = _atom("x"), _atom("z")


def _key(atom, value, given=(), population=None) -> ProbabilityKey:
    return ProbabilityKey(target_atom=atom, target_value=value,
                          given=frozenset(given), population=population)


# --- the rule ----------------------------------------------------------------

def test_a_pair_lacking_both_values_asks_for_one():
    theta = Theta(domains={X: (True, False)})
    asked = theta_builder.fewest_to_ask(
        [_key(X, False), _key(X, True)], theta)
    assert asked == (_key(X, True),)


def test_a_group_only_part_of_which_was_collected_keeps_all_of_it():
    """Supplying exactly those is already the least: completing any of them
    would take every other value of the group."""
    theta = Theta(domains={Z: ("low", "mid", "high")})
    wanted = [_key(Z, "low"), _key(Z, "mid")]
    assert theta_builder.fewest_to_ask(wanted, theta) == tuple(wanted)


def test_values_already_supplied_are_not_counted_as_lacking():
    theta = Theta(entries={_key(Z, "low"): 0.2},
                  domains={Z: ("low", "mid", "high")})
    asked = theta_builder.fewest_to_ask(
        [_key(Z, "mid"), _key(Z, "high")], theta)
    assert asked == (_key(Z, "mid"),)


def test_a_cell_the_caller_keeps_makes_another_one_give_way():
    theta = Theta(domains={X: (True, False)})
    asked = theta_builder.fewest_to_ask(
        [_key(X, True), _key(X, False)], theta, keep=[_key(X, False)])
    assert asked == (_key(X, False),)


def test_conditions_and_populations_are_groups_of_their_own():
    theta = Theta(domains={X: (True, False), Z: (True, False)})
    cells = [_key(X, v, given=[(Z, z)]) for z in (True, False)
             for v in (True, False)]
    cells += [_key(X, v, population="target") for v in (True, False)]
    asked = theta_builder.fewest_to_ask(cells + cells[:1], theta)
    assert asked == (
        _key(X, True, given=[(Z, True)]),
        _key(X, True, given=[(Z, False)]),
        _key(X, True, population="target"),
    )


def test_a_declared_variable_no_statement_mentions_takes_its_declaration():
    theta = Theta(declared={"z": ("low", "mid", "high")})
    assert theta.domain_of(Z) == ("low", "mid", "high")
    assert theta.domain_of(X) == (True, False)


# --- the shapes that raised it ------------------------------------------------

def _a(name):
    return {"predicate": name, "args": []}


def _program(variables, edges, query, *, bidirected=(), domains=None,
             extra=()):
    domains = domains or {}
    statements = [{"kind": "variable", "predicate": v,
                   "domain": domains.get(v, [True, False])}
                  for v in variables]
    statements += [{"kind": "cause", "from": _a(a), "to": _a(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _a(a), "right": _a(b)}
                   for a, b in bidirected]
    statements += list(extra)
    statements.append({"kind": "query", "id": "q", "query": query})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


def _effect(x="x", y="y"):
    return {"kind": "effect", "given": [],
            "intervention": {"atom": _a(x), "value": True},
            "target": {"atom": _a(y), "value": True}}


def _causation(cause, effect):
    return {"kind": "causation", "cause": _a(cause), "effect": _a(effect),
            "monotonic": False}


SHAPES = {
    "attribution over four causes": _program(
        ("ai", "market", "competition", "high_base", "slowdown"),
        [(c, "slowdown") for c in ("ai", "market", "competition",
                                   "high_base")],
        _causation("ai", "slowdown")),
    "confounded attribution": _program(
        ("x", "y", "z"), [("z", "x"), ("z", "y"), ("x", "y")],
        _causation("x", "y")),
    "back door": _program(
        ("x", "y", "z"), [("z", "x"), ("z", "y"), ("x", "y")], _effect()),
    "front door": _program(
        ("x", "m", "y"), [("x", "m"), ("m", "y")], _effect(),
        bidirected=[("x", "y")]),
    "a three-valued confounder": _program(
        ("x", "y", "z"), [("z", "x"), ("z", "y"), ("x", "y")], _effect(),
        domains={"z": ["low", "mid", "high"]}),
}

#: What each shape asks for now. The attribution over four causes asked for
#: 42 before, the back door for 4.
ASKED = {
    "attribution over four causes": 22,
    "confounded attribution": 7,
    "back door": 3,
    "front door": 6,
    "a three-valued confounder": 5,
}


def _stubs(result):
    return [item["skeleton"]
            for request in result.get("investigation_requests") or ()
            for item in request.get("items") or ()
            if (item.get("skeleton") or {}).get("kind") == "probability"]


def _group(stub):
    return (stub["target"]["atom"]["predicate"],
            tuple(sorted((g["atom"]["predicate"], str(g["value"]))
                         for g in stub["given"])))


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_no_ask_is_the_remainder_of_the_others(shape):
    program = SHAPES[shape]
    result = themis.run(copy.deepcopy(program))["results"][0]
    stubs = _stubs(result)
    assert len(stubs) == ASKED[shape], len(stubs)
    domains = {s["predicate"]: s["domain"] for s in program["statements"]
               if s["kind"] == "variable"}
    by_group: dict = {}
    for stub in stubs:
        by_group.setdefault(_group(stub), []).append(stub["target"]["value"])
    for (predicate, _), values in by_group.items():
        assert len(values) < len(domains[predicate]), (predicate, values)
        assert all(v in domains[predicate] for v in values), values
    themis.verify_answer_claims(copy.deepcopy(program), result)


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_supplying_exactly_what_is_asked_leaves_no_parameter_asked(shape):
    program = copy.deepcopy(SHAPES[shape])
    result = themis.run(copy.deepcopy(program))["results"][0]
    for i, stub in enumerate(_stubs(result)):
        stub = copy.deepcopy(stub)
        stub["value"] = round(0.1 + 0.03 * (i % 10), 3)
        stub["annotations"] = {"source": "a study"}
        program["statements"].insert(-1, stub)
    again = themis.run(program)["results"][0]
    assert not [m for m in again.get("missing_information") or ()
                if m.get("kind") == "parameter"]


# --- the verifier ------------------------------------------------------------

def test_a_list_asking_for_the_remainder_is_refused():
    """The honest back-door list asks for ``P(z=True)``; putting
    ``P(z=False)`` back beside it is what the list used to say."""
    program = SHAPES["back door"]
    result = themis.run(copy.deepcopy(program))["results"][0]
    themis.verify_answer_claims(copy.deepcopy(program), result)
    forged = copy.deepcopy(result)
    items = forged["investigation_requests"][0]["items"]
    rows = forged["missing_information"]
    [item] = [i for i in items if i["target"] == "parameter:P(z=True)"]
    [row] = [r for r in rows if r["name"] == "parameter:P(z=True)"]
    twin, twin_row = copy.deepcopy(item), copy.deepcopy(row)
    twin["target"] = twin_row["name"] = "parameter:P(z=False)"
    twin["said"] = twin_row["said"] = {"key": "P(z=False)"}
    twin["skeleton"]["target"]["value"] = False
    items.append(twin)
    rows.append(twin_row)
    forged["investigation_requests"][0]["target"] = (
        f"parameter:{len(items)}_items")
    typed = kernel.validate_program(copy.deepcopy(program))
    investigation_rules.verify_investigation_items(result, typed)
    with pytest.raises(VerificationError, match="the others' remainder"):
        investigation_rules.verify_investigation_items(forged, typed)
