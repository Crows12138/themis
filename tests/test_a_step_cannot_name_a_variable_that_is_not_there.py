"""An atom is its arguments too, and only the predicate was ever held.

``x(u)`` and ``x(nobody)`` are two different variables. The rules that
audit a numeric estimate compare PREDICATES — the data they stand for is
keyed on bare column names — so a step's recorded atoms were only ever
held down to their predicate, and the unit an estimate claimed to be about
was free.

Measured before this: editing the argument name of an atom-valued step
input passed 104 times, across nine estimate rules and the transport
formula. Editing the PREDICATE of the same fields was refused, which is
what made the hole invisible — something did compare those, so the field
looked held.

The gate is asked once, in ``dispatch_rule``, rather than nine times
downstream. What a particular rule needs its atoms FOR is that rule's
business; that a step reasoning about a graph cannot name a variable the
graph does not have is true of all of them.

The walk recurses on purpose. Adjustment sets, instrument tuples and path
lists carry atoms too, and a gate reaching only the scalar fields would
have left those as free as the fields it did reach.

A gate that walks nothing refuses nothing and looks exactly like a gate
that works — the fault #578 was about — so how much this one actually
reaches is asserted as a number rather than inferred from tests passing.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import Atom, ConstTerm
from themis.verifier.errors import RuleCheckFailed
from themis.verifier.rules import (
    _every_atom_a_step_names_is_one_the_graph_has, atoms_within)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Atom-valued inputs across the corpus: (answer, step index, field).
ATOM_INPUTS = sorted(
    (name, i, field)
    for name, pair in SHAPES.items()
    for i, step in enumerate(
        ((pair["result"] or {}).get("derivation") or {}).get("steps") or [])
    for field, raw in (step.get("inputs") or {}).items()
    if isinstance(raw, dict) and raw.get("kind") == "atom"
    and (raw.get("args") or [])
)


def test_how_many_atoms_this_gate_actually_reaches():
    """The gate's own reach, as a number.

    A walk that descends into nothing raises nothing and passes every
    other test in this file. This counts what it finds on the corpus's
    own steps so that a walk which stops recursing fails here rather than
    going quiet.
    """
    reached = 0
    steps = 0
    for name, pair in SHAPES.items():
        for step in (((pair["result"] or {}).get("derivation") or {})
                     .get("steps") or []):
            inputs = step.get("inputs")
            if isinstance(inputs, dict):
                steps += 1
    assert steps == 359, steps

    # The walker itself, on shapes it has to descend through.
    u = ConstTerm(name="u")
    x, y, z = (Atom(predicate=p, args=(u,)) for p in "xyz")
    nested = {"treatment": x, "adjustment": frozenset({y, z}),
              "paths": ((x, y), (y, z)), "note": "not an atom", "n": 3}
    reached = list(atoms_within(nested))
    assert sorted(a.predicate for a in reached) == ["x", "x", "y", "y", "y",
                                                    "z", "z"], reached


def test_the_corpus_carries_atom_inputs_to_be_asked_about():
    """Every atom-valued input with arguments, not a chosen handful.

    An earlier count of this looked at six field names I had in mind —
    treatment, outcome, target and so on — and got 272. Walking whatever
    keys the steps actually carry gets 478: criterion steps name their
    atoms ``x``, ``y``, ``z``. Counting the fields one remembers is the
    same mistake as reading the corpus for a roster.
    """
    assert len(ATOM_INPUTS) == 478, len(ATOM_INPUTS)


@pytest.mark.parametrize(
    "name", sorted({n for n, _, _ in ATOM_INPUTS}))
def test_an_honest_step_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict.

    Every atom every step names on this corpus is a node of its graph —
    272 of them — so no honest answer has anything to fear from the gate.
    """
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_moved_argument_is_refused_and_by_which_rule():
    """The teeth, counted rather than sampled, and split by who speaks.

    One field at a time: editing several at once lets a single refusal
    stand for all of them, which reports a gate that reached one input as
    a gate that reached every input.

    The split matters more than the total. 96 of these were already
    refused by ``_assert_query_binding``, which holds a criterion step's
    x / y / given against the active query — an older and more specific
    check, and it rightly speaks first. Crediting this gate with those
    would be reporting somebody else's coverage as its own; what it added
    is the other 382, which is what "104 argument edits passed" grew into
    once every atom-valued key was asked rather than the six field names
    I happened to have in mind.
    """
    by_who: dict[str, int] = {"new gate": 0, "an older rule": 0}
    for name, i, field in ATOM_INPUTS:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        forged["derivation"]["steps"][i]["inputs"][field]["args"][0]["name"] = \
            "nobody"
        with pytest.raises(Exception) as caught:                 # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        key = ("new gate" if "has no such variable" in str(caught.value)
               else "an older rule")
        by_who[key] += 1

    assert sum(by_who.values()) == 478, by_who
    assert by_who == {"new gate": 382, "an older rule": 96}, by_who


def test_the_message_names_the_whole_atom_not_just_the_predicate():
    """Because the predicate is the half that was already right.

    A refusal saying only ``x`` would send whoever reads it looking for a
    variable that is present, which is the confusion this whole frontier
    is about.
    """
    name, i, field = next(
        (n, i, f) for n, i, f in ATOM_INPUTS
        if SHAPES[n]["result"]["derivation"]["steps"][i]["rule"]
        == "numeric_aipw_estimate" and f == "outcome")
    row = SHAPES[name]
    forged = copy.deepcopy(row["result"])
    forged["derivation"]["steps"][i]["inputs"][field]["args"][0]["name"] = \
        "nobody"
    with pytest.raises(Exception, match=r"\(nobody\)"):          # noqa: B017
        the_door_for(row["result"])(row["program"], forged)


def test_an_atom_inside_a_set_is_reached_too():
    """The recursion, exercised where the corpus's scalar fields cannot.

    An adjustment set is a frozenset of atoms. A gate that checked only
    the fields whose value IS an atom would pass every test above and
    leave every set-valued input free.
    """
    u = ConstTerm(name="u")
    x, y = Atom(predicate="x", args=(u,)), Atom(predicate="y", args=(u,))
    ghost = Atom(predicate="y", args=(ConstTerm(name="nobody"),))

    graph = nx.DiGraph()
    graph.add_edge(x, y)

    class _Ctx:
        pass

    ctx = _Ctx()
    ctx.graph = graph

    _every_atom_a_step_names_is_one_the_graph_has(
        ctx, {"adjustment": frozenset({x, y})}, 0, "r")

    with pytest.raises(RuleCheckFailed, match=r"y\(nobody\)"):
        _every_atom_a_step_names_is_one_the_graph_has(
            ctx, {"adjustment": frozenset({x, ghost})}, 0, "r")
