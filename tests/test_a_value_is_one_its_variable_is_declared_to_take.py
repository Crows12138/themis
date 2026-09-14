"""A value written beside a variable is one its declaration lists.

Past the input, ``domain`` is read one way: the theta layer takes it as an
atom's values, a dose-response route as the points it estimates at, the
verifier as the values a reader can be asked to record. Nothing at the input
held a literal to it. A program declaring ``raise_amount`` to take
``[0.0, 5.0, 100.0]`` and asking ``do(raise_amount=True)`` was taken; its
curve was drawn over the domain while its request for data copied the
query's value, and the answer was refused at the door for asking a reader
for a value the variable does not have. It is a row of the answer corpus,
harvested from three dose-response tests that wrote ``True`` as a
placeholder.

Measured over the whole suite with the check recording rather than refusing:
five distinct literals outside a domain, every one of them a program that
says two things of one variable -- those three placeholders, a bounds test
asking about ``engagement = 99`` on a variable declared ``1..5``, and a
three-level ``x`` given probabilities as if it had two.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.input.semantic_validator import (
    Malformed,
    SemanticError,
    validate_program,
)
from themis.input.syntactic_validator import validate_ast


def _atom(predicate):
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _program(*, intervention=5.0, target=True, given=None, extra=()):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "dose", "domain": [0.0, 5.0, 100.0]},
            {"kind": "variable", "predicate": "level", "domain": ["lo", "mid", "hi"]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "variable", "predicate": "w"},
            {"kind": "cause", "from": _atom("level"), "to": _atom("dose")},
            {"kind": "cause", "from": _atom("level"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("dose"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            *extra,
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("dose"), "value": intervention},
                "target": {"atom": _atom("y"), "value": target},
                "given": given if given is not None else []}},
        ],
    }


def _observed(predicate, value):
    return {"kind": "observation", "atom": _atom(predicate), "value": value}


def _probability(target, given):
    return {"kind": "probability",
            "target": {"atom": _atom(target[0]), "value": target[1]},
            "given": [{"atom": _atom(p), "value": v} for p, v in given],
            "value": 0.3}


def _checked(program):
    validate_ast(program)
    return validate_program(program)


OUTSIDE = {
    "an_intervention": lambda: _program(intervention=True),
    "a_target": lambda: _program(target=4),
    "a_given": lambda: _program(
        given=[{"atom": _atom("level"), "value": "high"}]),
    "an_observation": lambda: _program(extra=[_observed("level", "high")]),
    "a_probability_s_target": lambda: _program(
        extra=[_probability(("level", True), [])]),
    "a_probability_s_given": lambda: _program(
        extra=[_probability(("y", True), [("level", False)])]),
}

INSIDE = {
    "every_value_declared": lambda: _program(
        given=[{"atom": _atom("level"), "value": "mid"}],
        extra=[_observed("level", "mid"),
               _probability(("y", True), [("level", "lo")])]),
    # Equality is the verifier's: the number five, however it is written.
    "a_number_written_as_an_integer": lambda: _program(intervention=5),
    # A variable declaring no domain has nothing to be held to.
    "a_variable_with_no_domain": lambda: _program(
        extra=[_observed("w", 42.5)]),
}


@pytest.mark.parametrize("where", sorted(OUTSIDE))
def test_a_value_the_declaration_does_not_list_is_refused(where):
    with pytest.raises(SemanticError) as raised:
        _checked(OUTSIDE[where]())
    assert raised.value.species is Malformed.VALUE_NOT_IN_DOMAIN


@pytest.mark.parametrize("where", sorted(INSIDE))
def test_a_value_the_declaration_lists_is_taken(where):
    _checked(INSIDE[where]())


def test_the_program_the_corpus_row_came_from_is_refused_before_it_runs():
    """The dose-response program three tests wrote, with the domain two of
    them declared and the placeholder all three kept."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "raise_amount",
             "domain": [0.0, 5.0, 100.0]},
            {"kind": "variable", "predicate": "engagement"},
            {"kind": "cause", "from": _atom("raise_amount"),
             "to": _atom("engagement")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("raise_amount"), "value": True},
                "target": {"atom": _atom("engagement"), "value": 4},
                "given": []}},
        ],
    }
    with pytest.raises(SemanticError) as raised:
        themis.run(program)
    assert raised.value.species is Malformed.VALUE_NOT_IN_DOMAIN
    fixed = copy.deepcopy(program)
    fixed["statements"][-1]["query"]["intervention"]["value"] = 5.0
    themis.run(fixed)
