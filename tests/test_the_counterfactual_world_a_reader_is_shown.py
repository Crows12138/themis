"""The whole counterfactual reaches a reader in one block, unheld.

``extensions.scm_counterfactual`` is a display copy, and what it displays
is answer-grade: the exogenous term abduction recovered for every
variable, the value each takes in the counterfactual world, which variable
was intervened on and at what, and which variable the question was about.
A reader meets those HERE and nowhere else — the derivation's terminal
step has room for one number, the point, so auditing the chain left every
other entry free to say anything.

Free is measurable and it was measured: 440 single-field edits of this
block on the corpus's own answers, and before this all of them passed both
public doors. A reader could be shown a counterfactual world in which the
wrong variable was intervened on, or one variable's value quietly moved,
or one variable dropped altogether.

The verifier already knew every one of those numbers. Both paths that
audit this answer re-run Pearl's three steps independently — the declared
path from the coefficients on the graph, the data path from re-solved OLS
moments — and both threw everything away except the point they were asked
about. So nothing here is a new computation: it is the same re-run, asked
for what it had already worked out.

The sibling block had this and this one did not.
``_verify_causation_extensions_match`` exists for exactly this reason,
about exactly this hazard, four lines away in the same function, with a
comment saying a tamper of the display copy alone must not pass.

What is asserted here:

- no honest answer is refused, on either path that writes the block
- every single-field edit is refused, counted rather than sampled
- both directions of every map: a key naming nothing, a variable dropped,
  and a value moved are three different lies and each is caught
- the two spellings a key can take are the two producers' own
- that accepting both is a decision, with what it costs written down, and
  that it rests on a condition — a spelling naming two variables names
  neither.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.runtime.scheduler import _atom_to_str
from themis.verifier.errors import VerificationError
from themis.verifier.verify import _atom_spellings, _match_display_map

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: Every answer whose reader is shown a counterfactual world.
CARRIERS = sorted(
    name for name, pair in SHAPES.items()
    if (pair["result"].get("extensions") or {}).get("scm_counterfactual"))

#: What one pass of single-field edits over those answers comes to. Stated
#: so that the gate going quiet shows up as a number rather than as a
#: shorter list of passing tests.
EDITS = 440


def _tampers(block):
    """One edit at a time, each a lie the rest of the envelope still fits.

    Three shapes per map, because they are three different lies: a value
    that moved, a variable dropped, and a key naming nothing. A rule
    comparing only the keys both sides have would catch the first and
    neither of the others.
    """
    for key, forged in (("target", "z(nobody)"), ("target_value", 12345.6)):
        if key in block:
            edited = copy.deepcopy(block)
            edited[key] = forged
            yield key, edited
    if isinstance(block.get("intervention"), dict):
        for key, forged in (("variable", "z(nobody)"), ("value", 999.0)):
            if key in block["intervention"]:
                edited = copy.deepcopy(block)
                edited["intervention"][key] = forged
                yield f"intervention.{key}", edited
    for field in ("counterfactual_values", "abducted_noise"):
        shown = block.get(field)
        if not isinstance(shown, dict) or not shown:
            continue
        one = sorted(shown)[0]
        edited = copy.deepcopy(block)
        edited[field][one] = float(edited[field][one]) + 7.5
        yield f"{field}[{one}] moved", edited
        edited = copy.deepcopy(block)
        edited[field].pop(one)
        yield f"{field}[{one}] dropped", edited
        edited = copy.deepcopy(block)
        edited[field]["ghost(nobody)"] = 1.0
        yield f"{field} gains a variable nobody asked about", edited


def test_the_block_is_carried_by_the_answers_that_have_one():
    """The denominator, and that both producers are in it.

    One of these is written by the data path, whose keys are the columns a
    coefficient was fitted from rather than the atoms a question names. A
    rule tested only on the other path would look complete and refuse this
    one the moment it ran.
    """
    assert len(CARRIERS) == 44, len(CARRIERS)
    spellings = {
        "bare" if "(" not in next(iter(
            SHAPES[n]["result"]["extensions"]["scm_counterfactual"]
            ["counterfactual_values"])) else "atom"
        for n in CARRIERS
    }
    assert spellings == {"atom", "bare"}, spellings


@pytest.mark.parametrize("name", CARRIERS)
def test_an_honest_counterfactual_world_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_single_field_edit_of_the_world_is_refused():
    """The other half, one edit at a time and counted.

    One at a time because editing the whole block lets one refusal stand
    for every field in it, which counts a rule that reached one entry as a
    rule that reached them all.
    """
    refused = 0
    for name in CARRIERS:
        row = SHAPES[name]
        block = row["result"]["extensions"]["scm_counterfactual"]
        for what, edited in _tampers(block):
            forged = copy.deepcopy(row["result"])
            forged["extensions"]["scm_counterfactual"] = edited
            with pytest.raises(Exception):                  # noqa: B017
                the_door_for(row["result"])(row["program"], forged)
            refused += 1
    assert refused == EDITS, refused


def test_the_three_lies_a_map_can_tell_are_each_named():
    """Not a count: the sentence a reader would get has to say which.

    A dropped variable and an invented one are opposite mistakes and a
    message that called both "does not match" would leave whoever reads
    the refusal to go and diff two dicts.
    """
    name = CARRIERS[0]
    row = SHAPES[name]
    block = row["result"]["extensions"]["scm_counterfactual"]
    one = sorted(block["counterfactual_values"])[0]

    for edit, expected in (
        (lambda b: b["counterfactual_values"].pop(one), "is silent about"),
        (lambda b: b["counterfactual_values"].update({"ghost(x)": 1.0}),
         "not a variable this counterfactual is about"),
        (lambda b: b["counterfactual_values"].update(
            {one: block["counterfactual_values"][one] + 1}), "and it is"),
    ):
        forged = copy.deepcopy(row["result"])
        edit(forged["extensions"]["scm_counterfactual"])
        with pytest.raises(VerificationError, match=expected):
            the_door_for(row["result"])(row["program"], forged)


def test_the_spelling_of_a_key_is_the_producers_own():
    """Restated in the verifier and pinned to the runtime that writes it.

    The other accepted spelling is the bare predicate, which is what the
    data path keys on; it needs no pin because it IS the attribute.
    """
    atom = next(iter(
        SHAPES[CARRIERS[0]]["result"]["extensions"]["scm_counterfactual"]
        ["counterfactual_values"]))
    assert "(" in atom  # the declared path, whose keys are atoms

    class _Arg:
        def __init__(self, name):
            self.name = name

    class _Atom:
        predicate = "y"
        args = (_Arg("p9"),)
        time_index = None

    made_up = _Atom()
    assert _atom_spellings(made_up) == (_atom_to_str(made_up), "y")


def test_the_bare_spelling_is_accepted_and_what_that_costs():
    """The leniency is a decision, so it is written down as one.

    A key may be the bare predicate of a variable the world spells in
    full. That is deliberate: the data path keys on the column a
    coefficient was fitted from, so refusing the bare form would refuse its
    honest answers outright. The cost, measured rather than assumed: a
    reader can be shown ``x`` where the world says ``x(p9)`` — the same
    variable, less of its name — and this rule will not object. Every
    corpus world is single-unit, so the bare form there resolves to exactly
    one variable, which is the condition the acceptance rests on.

    Stated here because a sweep that swaps a full spelling for its own bare
    form reports those leaves as unheld, and it is right that nothing holds
    them: the swap is a synonym, not a lie.
    """
    name = next(n for n in CARRIERS
                if "(" in next(iter(
                    SHAPES[n]["result"]["extensions"]["scm_counterfactual"]
                    ["counterfactual_values"])))
    row = SHAPES[name]
    block = row["result"]["extensions"]["scm_counterfactual"]
    full = sorted(block["counterfactual_values"])[0]

    forged = copy.deepcopy(row["result"])
    shown = forged["extensions"]["scm_counterfactual"]["counterfactual_values"]
    shown[full.split("(")[0]] = shown.pop(full)
    the_door_for(row["result"])(row["program"], forged)   # accepted, on purpose

    # And it buys nothing: the two spellings are one variable, so a block
    # cannot use both to claim it showed two.
    forged = copy.deepcopy(row["result"])
    shown = forged["extensions"]["scm_counterfactual"]["counterfactual_values"]
    shown[full.split("(")[0]] = shown[full]
    with pytest.raises(VerificationError, match="already given"):
        the_door_for(row["result"])(row["program"], forged)


def test_a_spelling_that_names_two_variables_names_neither():
    """The condition above, on a world no corpus answer has.

    Every corpus world holds one unit, so its bare predicates each resolve
    to one variable and this branch never runs there. A world over two
    units has a bare ``x`` meaning two things, and binding it to whichever
    the re-run happened to yield first would make the rule's verdict a fact
    about dict order. The data path refuses this on its own side already —
    the same invariant, which is why it belongs on both.
    """
    class _Arg:
        def __init__(self, name):
            self.name = name

    class _Atom:
        time_index = None

        def __init__(self, predicate, arg):
            self.predicate = predicate
            self.args = (_Arg(arg),)

        def __hash__(self):
            return hash((self.predicate, self.args[0].name))

        def __eq__(self, other):
            return (isinstance(other, _Atom)
                    and (self.predicate, self.args[0].name)
                    == (other.predicate, other.args[0].name))

    world = {_Atom("x", "p1"): 1.0, _Atom("x", "p2"): 2.0}

    _match_display_map({"x(p1)": 1.0, "x(p2)": 2.0}, world, "counterfactual_values")

    with pytest.raises(VerificationError, match="more than one variable"):
        _match_display_map({"x": 1.0, "x(p2)": 2.0}, world,
                           "counterfactual_values")


def test_an_answer_with_no_block_is_not_asked_about_one():
    """An scm_counterfactual that stopped short carries no world, and a
    rule demanding one would refuse it for what it honestly is."""
    without = [n for n, pair in SHAPES.items()
               if pair["result"].get("query_kind") == "scm_counterfactual"
               and not (pair["result"].get("extensions") or {})
               .get("scm_counterfactual")]
    assert without, "no scm_counterfactual answer lacks the block"
    for name in without:
        verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])
