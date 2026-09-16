"""A structural refusal names what it cannot run, and nobody asked the program.

``missing_structural_input`` says a question or a declaration cannot be run
as written, and was filed with the claims the data settles, so no list said
a witness was owed. Two of its species carry the whole of their claim in
their own facts: a name, the part of the program that writes it, and whether
the graph has no node of it or several. Each copy of one -- the ask, the
note summing the asks up, the sentence in the report -- was held to the
others and to nothing else. Measured with every copy bent together: the part
rewritten to any other part, the name to one the graph holds or to one no
part writes, the nodes to fewer, and every door that reads the answer took
all of them.

A question naming an atom the graph lacks is not among the programs below,
though the witness reads that part too. The one such answer ``run`` gave was
reached through a mediator nobody declared, the field the validator's own
list of a question's atoms had left out; that list is gone, and the program
is refused at the input the way an undeclared treatment always was (see
``test_the_graph_is_asked_about_every_variable_a_question_names.py``).
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from themis import gaps
from themis.gaps import GapKind, QueryPart
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import (
    _THE_QUESTION_A_PART_IS,
    _WITNESSES,
    SETTLED_BY,
    THE_PROGRAM,
)
from tests.test_a_name_a_strategy_declares_is_one_node import UNROLLED

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
_STORED = json.loads((FIXTURES / "answer_shapes.json").read_text(
    encoding="utf-8"))["needs_investigation:effect:none#2beaf3"]["program"]


#: A confounder a declared strategy names and the graph lacks, and names a
#: strategy declares that the unrolled graph holds at more than one step.
PROGRAMS = {
    "a_strategy_names_a_confounder_the_graph_lacks": _STORED,
    **{f"a_strategy_unrolled_{name}": program
       for name, program in UNROLLED.items()},
}

#: For each, a name its part writes that the graph holds at one node.
_HELD_ONCE = {
    "a_strategy_names_a_confounder_the_graph_lacks": "L0",
    **{f"a_strategy_unrolled_{name}": "Y" for name in UNROLLED},
}

_SPECIES = {str(member) for member in _WITNESSES}


def _run(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


@pytest.fixture(scope="module")
def answers():
    return {name: _run(program) for name, program in PROGRAMS.items()}


def _copies(node):
    """Every copy of the two species, wherever the envelope spells one."""
    if isinstance(node, dict):
        token = node.get("need")
        if token is None and node.get("vocabulary") == gaps.NEEDED:
            token = node.get("token")
        if token in _SPECIES:
            yield node
        for value in node.values():
            yield from _copies(value)
    elif isinstance(node, list):
        for item in node:
            yield from _copies(item)


def _bent(result, change, only=None):
    forged = copy.deepcopy(result)
    for index, holder in enumerate(_copies(forged)):
        if only is None or index == only:
            change(holder)
    return forged


# ================================================================ honest first


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_an_honest_structural_refusal_is_accepted(name, answers):
    """At both doors that read it, and with every copy it spells."""
    result = answers[name]
    assert result["status"] == "needs_investigation"
    assert len(list(_copies(result))) >= 4
    themis.verify_answer_claims(PROGRAMS[name], result)
    themis.verify_refusal(PROGRAMS[name], result)


# ============================================================== the forgeries


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_a_part_that_writes_no_such_name_is_refused(name, answers):
    """Every other part, at every copy together."""
    result = answers[name]
    part = next(_copies(result))["words"]["part"]["token"]
    others = sorted(str(m) for m in QueryPart if str(m) != part)
    for other in others:
        forged = _bent(result, lambda h, o=other:
                       h["words"]["part"].__setitem__("token", o))
        with pytest.raises(VerificationError, match="writes no"):
            themis.verify_answer_claims(PROGRAMS[name], forged)
    assert len(others) == 5


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_a_name_the_graph_holds_once_is_refused(name, answers):
    """Whichever of the two species says it."""
    forged = _bent(answers[name], lambda h:
                   h["said"].__setitem__("atom", _HELD_ONCE[name]))
    with pytest.raises(VerificationError, match="holds"):
        themis.verify_answer_claims(PROGRAMS[name], forged)


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_a_name_no_part_writes_is_refused(name, answers):
    forged = _bent(answers[name], lambda h:
                   h["said"].__setitem__("atom", "WRITTEN_NOWHERE"))
    with pytest.raises(VerificationError, match="writes no"):
        themis.verify_answer_claims(PROGRAMS[name], forged)


def test_nodes_a_name_is_are_every_node_of_it(answers):
    """The statement lists them, and a list one short sends a reader to
    choose between fewer steps than the graph has."""
    name = "a_strategy_unrolled_names_each_variable_once"
    forged = _bent(answers[name], lambda h: h["said"].__setitem__(
        "atoms", h["said"]["atoms"].split(", ")[0]))
    with pytest.raises(VerificationError, match="the nodes"):
        themis.verify_answer_claims(PROGRAMS[name], forged)


@pytest.mark.parametrize("name", sorted(PROGRAMS))
def test_each_copy_is_held_to_the_program_on_its_own(name, answers):
    """Asked at the door that reads nothing but what the program settles, so
    no copy is refused for disagreeing with another."""
    result = answers[name]
    count = len(list(_copies(result)))
    for index in range(count):
        forged = _bent(result, lambda h:
                       h["said"].__setitem__("atom", "WRITTEN_NOWHERE"),
                       only=index)
        with pytest.raises(VerificationError, match="writes no"):
            themis.verify_refusal(PROGRAMS[name], forged)


# ============================================================== the accounting


def test_the_kind_is_the_programs_to_settle_and_every_part_is_read():
    assert SETTLED_BY[GapKind.MISSING_STRUCTURAL_INPUT] is THE_PROGRAM
    assert (set(_THE_QUESTION_A_PART_IS) | {str(QueryPart.LONGITUDINAL_SPEC)}
            == {str(m) for m in QueryPart})
