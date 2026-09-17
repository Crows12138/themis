"""A node is read back by the name the envelope writes it with.

Every block that names a node of the graph -- an adjustment set, an
instrument, the mediators, the proxies, a feedback pair, the treatments of a
sequence -- names it with ``atom_label``: the predicate, its arguments and,
on a program unrolled in time, when it is (``z(u)@t-1``). The verifier read
those names back through maps of its own, six of them, each keyed on the
predicate and its arguments alone. On an untimed program the two spellings
are one string, and every answer the corpus was harvested from is untimed,
so nothing failed. Restated with every atom at time 0 -- the same problem in
one time slice -- 109 of the corpus's 242 programs were answered as before
and refused at the door, each for naming a node the graph has.

The name rule was the same mistake in words: ``m(me)@t`` is written with
``t``, and a gap's names were held to the problem's predicates and objects.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

import themis
from themis.runtime.graph_projection import atom_label
from themis.types import Atom, ConstTerm, RelativeTimeIndex
from themis.verifier.context import VerificationContext
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import (
    words_its_names_are_spelt_with,
    words_the_problem_uses,
)
from themis.verifier.rules import _atom_label_verifier, _verifier_nodes_by_label
from tests.answer_corpus import the_door_for

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

_ME = (ConstTerm("me"),)


def _in_one_time_slice(node):
    """The same problem with every atom that has no time put at time 0."""
    if isinstance(node, dict):
        out = {key: _in_one_time_slice(value) for key, value in node.items()}
        if (isinstance(out.get("predicate"), str)
                and isinstance(out.get("args"), list)
                and "time_index" not in out):
            out["time_index"] = {"kind": "relative", "value": 0}
        return out
    if isinstance(node, list):
        return [_in_one_time_slice(value) for value in node]
    return node


RESTATED = {
    name: restated
    for name, entry in SHAPES.items()
    if (restated := _in_one_time_slice(entry["program"])) != entry["program"]
}


def _what_the_door_says(program, asked) -> str:
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == asked)
    try:
        the_door_for(result)(program, result)
    except VerificationError as exc:
        return f"{exc.rule}: {str(exc)[:160]}"
    return "accepted"


def test_a_time_index_changes_nothing_the_door_says():
    """The honest side, over the whole corpus: each program and its
    restatement are run the same way and put to the strongest door that
    reads the answer, and the door says the same of both.

    Held to the untimed run rather than to acceptance, because that is
    the claim. The programs are stored without the data some were
    harvested with, and an answer run without it is not the stored one.
    """
    differs = {}
    for name, restated in sorted(RESTATED.items()):
        asked = SHAPES[name]["result"].get("query_id")
        untimed = _what_the_door_says(SHAPES[name]["program"], asked)
        timed = _what_the_door_says(restated, asked)
        if timed != untimed:
            differs[name] = (untimed, timed)
    assert differs == {}, differs
    assert len(RESTATED) == 250, len(RESTATED)


def test_the_verifier_spells_a_node_as_the_producer_does():
    for time in (None, -2, -1, 0, 3):
        atom = Atom("sleep", _ME,
                    None if time is None else RelativeTimeIndex(time))
        assert _atom_label_verifier(atom) == atom_label(atom), time


def test_two_times_of_one_variable_are_two_nodes():
    now = Atom("z", _ME, RelativeTimeIndex(0))
    before = Atom("z", _ME, RelativeTimeIndex(-1))
    graph = nx.DiGraph()
    graph.add_nodes_from((now, before))
    assert _verifier_nodes_by_label(graph) == {"z(me)@t": now,
                                               "z(me)@t-1": before}


def _at(predicate, time):
    return {"predicate": predicate,
            "args": [{"type": "const", "name": "me"}],
            "time_index": {"kind": "relative", "value": time}}


def _confounded_a_step_back():
    """z a step back confounds x and y now; z now is a second node under the
    same predicate and arguments, declared first, causing only w."""
    edges = ((_at("z", 0), _at("w", 0)), (_at("z", -1), _at("x", 0)),
             (_at("z", -1), _at("y", 0)), (_at("x", 0), _at("y", 0)))
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in "wxyz"]
    statements += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": _at("x", 0), "value": True},
        "target": {"atom": _at("y", 0), "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def test_an_adjustment_is_held_at_the_time_it_names():
    program = _confounded_a_step_back()
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == "q")
    assert result["extensions"]["identification"] == {
        "pattern": "backdoor", "adjustment_set": ["z(me)@t-1"]}
    the_door_for(result)(program, result)
    for spelt, why in (("z(me)@t", "does not satisfy the back-door criterion"),
                       ("z(me)", "which is not a node in the graph")):
        forged = copy.deepcopy(result)
        forged["extensions"]["identification"]["adjustment_set"] = [spelt]
        with pytest.raises(VerificationError, match=why):
            the_door_for(forged)(program, forged)


def test_the_words_of_a_timed_name_include_when_and_a_variable_does_not():
    class _Q:
        pass

    graph = nx.DiGraph()
    graph.add_node(Atom("m", _ME, RelativeTimeIndex(-1)))
    context = VerificationContext(graph=graph, query=_Q())
    assert words_the_problem_uses(context) == {"m", "me"}
    assert words_its_names_are_spelt_with(context) == {"m", "me", "t"}
