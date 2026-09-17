"""The skeleton is the part of an ask somebody actually collects against.

``investigation_requests[].items[].skeleton`` names the variables a
reader goes and measures. Nothing held them, so a skeleton could send
somebody after ``survival(nobody)`` — a unit the problem never had.

Measured before this: 85 of 85 moved argument names inside a skeleton's
target passed both public doors.

The roster this is held to took three attempts, and the two rejected ones
are the content of this file as much as the rule is.

THE GRAPH IS WRONG. 192 of 193 skeleton atoms are graph nodes; the
exception is an honest answer whose graph is EMPTY — a bare probability
question declaring no edges, whose skeleton names ``y(me)`` with nothing
for it to be missing from. A graph roster refuses that answer.

THE PREDICATE ROSTER IS WRONG THE OTHER WAY. ``predicates_of`` answers
"does this problem know this name", which cannot tell ``x(u)`` from
``x(nobody)`` — and the argument is the census leaf, so it would close
nothing at all.

WHAT WORKS is the problem's own variables, GROUNDED. A statement may be
written for all units — ``forall I: z(I) → y(I)`` — while what a reader is
told to measure is ``z(me)``. Instantiating the quantified positions at
the constants the same problem names is the grounding the graph performs,
and it admits ``z(me)`` while still refusing ``z(nobody)``, because
``nobody`` is a unit this problem never mentions.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.kernel import _premises_of
from themis.verifier.investigation_rules import (
    _skeleton_atoms, predicates_of, variables_named_by)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

#: (answer, request index, item index) for every item carrying a skeleton
#: whose target is an atom with arguments — the ones this can speak for.
TARGETS = sorted(
    (name, ri, ii)
    for name, pair in SHAPES.items()
    for ri, req in enumerate(
        (pair["result"] or {}).get("investigation_requests") or [])
    for ii, item in enumerate(req.get("items") or [])
    if isinstance(item.get("skeleton"), dict)
    and isinstance((item["skeleton"].get("target") or {}).get("atom"), dict)
    and ((item["skeleton"]["target"]["atom"].get("args")) or [])
)


def test_the_items_that_send_a_reader_to_measure_something():
    """The denominator, and the two skeleton kinds told apart.

    306 of the 417 skeletons are variable patches, which name a predicate
    and no arguments — their whole purpose is to introduce a variable the
    problem does NOT have, so this rule is silent for them by construction
    rather than by exception.

    Both numbers went up by eight together with a targeted corpus refresh
    that picked up investigation items its rows predated, so the 85 this
    rule does speak for is unchanged. They went up by one together again
    when the joint general-ID row was refreshed. When the identifier began
    answering a query conditioning on a descendant of the treatment, the
    eight rows collected for it brought nine patches and 26 skeletons this
    rule speaks for.
    """
    skeletons = [
        item["skeleton"]
        for pair in SHAPES.values()
        for req in (pair["result"] or {}).get("investigation_requests") or []
        for item in req.get("items") or []
        if isinstance(item.get("skeleton"), dict) and item["skeleton"]
    ]
    assert len(skeletons) == 417, len(skeletons)
    kinds = {}
    for sk in skeletons:
        kinds[sk.get("kind")] = kinds.get(sk.get("kind"), 0) + 1
    assert kinds == {"variable_patch": 306, "probability": 111}, kinds
    assert len(TARGETS) == 111, len(TARGETS)


@pytest.mark.parametrize("name", sorted({n for n, _, _ in TARGETS}))
def test_an_honest_skeleton_is_accepted(name):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_every_moved_unit_is_refused():
    """The teeth, counted rather than sampled."""
    refused = 0
    for name, ri, ii in TARGETS:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        (forged["investigation_requests"][ri]["items"][ii]["skeleton"]
         ["target"]["atom"]["args"][0]["name"]) = "nobody"
        with pytest.raises(Exception, match="no such variable"):  # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 111, refused


def test_the_given_side_is_held_too():
    """A skeleton conditions on variables as well as targeting one, and a
    reader collects the conditioning columns just as literally."""
    checked = 0
    for name, ri, ii in TARGETS:
        row = SHAPES[name]
        given = (row["result"]["investigation_requests"][ri]["items"][ii]
                 ["skeleton"].get("given")) or []
        if not given or not (given[0].get("atom") or {}).get("args"):
            continue
        forged = copy.deepcopy(row["result"])
        (forged["investigation_requests"][ri]["items"][ii]["skeleton"]
         ["given"][0]["atom"]["args"][0]["name"]) = "nobody"
        with pytest.raises(Exception, match="no such variable"):  # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        checked += 1
    assert checked > 0, "no skeleton conditions on anything"


def test_the_roster_is_grounded_and_neither_of_the_two_wrong_ones():
    """The three rosters, on the answers that tell them apart.

    Asserted rather than described, because the difference between them
    is exactly one honest answer and exactly one lie, and a rule built on
    either wrong roster passes a great many tests before failing on those.
    """
    # (1) The empty-graph answer: grounded roster has it, graph does not.
    name = "needs_investigation:probability:none#6bdf54"
    pair = SHAPES[name]
    _, prog, _, ctx = _premises_of(pair["program"], pair["result"])
    assert list(ctx.graph) == [], "this answer is supposed to have no graph"
    assert ("y", ("me",)) in variables_named_by(prog)

    # (2) The forall answer: statements say z(I), the skeleton says z(me).
    name = "needs_investigation:effect:none#63d205"
    pair = SHAPES[name]
    _, prog, _, _ = _premises_of(pair["program"], pair["result"])
    grounded = variables_named_by(prog)
    assert ("z", ("me",)) in grounded, sorted(grounded)
    assert ("z", ("nobody",)) not in grounded

    # (3) The predicate roster cannot tell those two apart at all, which
    # is why it would have closed nothing.
    assert "z" in predicates_of(prog)


def test_a_variable_patch_is_not_asked_whether_its_variable_exists():
    """The silence that is deliberate, exercised.

    A patch introducing a brand-new variable is the one ask that MUST be
    allowed to name something the problem does not have.
    """
    patches = [
        (name, ri, ii)
        for name, pair in SHAPES.items()
        for ri, req in enumerate(
            (pair["result"] or {}).get("investigation_requests") or [])
        for ii, item in enumerate(req.get("items") or [])
        if isinstance(item.get("skeleton"), dict)
        and item["skeleton"].get("kind") == "variable_patch"
    ]
    assert patches, "no variable patch in the corpus"
    name, ri, ii = patches[0]
    sk = SHAPES[name]["result"]["investigation_requests"][ri]["items"][ii][
        "skeleton"]
    assert "args" not in sk, sk
    assert _skeleton_atoms(sk, []) == [], _skeleton_atoms(sk, [])
