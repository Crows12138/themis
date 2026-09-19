"""A transport block is a copy, and a copy is held to what it copies.

``verify_transport_sources`` re-derives the multi-source verdict -- which
routes agree, whether a number was owed or owed to be withheld -- and it
used to do that from the block alone. That posture is right for the
verdict and wrong for everything beside it, because the rest of the block
is not something the kernel concluded. It is three documents copied back
to a reader: the program declares each selection diagram, the chain
records the adjustment set and the estimand of each route, and the
question says which population the answer is for.

Held by nothing, those were 38 declared leaves of variable names and 10
of printed estimands. Worse than free: the block's own ``s_nodes`` list
was the roster the routes were checked against, so a route and the
declaration it was held to could be edited in one stroke and stay
consistent.

The twin of this rule, about the other kind of selection-diagram block,
says the sentence outright -- which nodes a verdict is about are read
from the PREMISES, not from the block -- and the four other block rules
in the same dispatch table all take theirs. What was missing here was
never a rule. It was an argument.

One route is deliberately not held to the chain, and the last test says
so: a program declaring no selection diagram gets the one no-boundary
route, whose chain has no transport step to have recorded anything.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _block(result):
    return (result.get("extensions") or {}).get("transport_identification")


def _routes(result, *, transporting: bool):
    out = []
    for route in (_block(result) or {}).get("sources") or ():
        named = bool(route.get("s_nodes"))
        if bool(route.get("transportable")) and named == transporting:
            out.append(route)
    return out


#: Derived rather than listed, so a corpus that grows a source domain is
#: asked the same questions without anybody remembering to add it here.
TRANSPORT_ROWS = sorted(
    name for name, pair in SHAPES.items()
    if isinstance(_block(pair["result"]), dict))
WITH_DIAGRAM = sorted(
    name for name in TRANSPORT_ROWS
    if _block(SHAPES[name]["result"]).get("s_nodes"))
WITH_ROUTE = sorted(
    name for name in TRANSPORT_ROWS
    if _routes(SHAPES[name]["result"], transporting=True))
TWO_ROUTES = sorted(
    name for name in TRANSPORT_ROWS
    if len(_routes(SHAPES[name]["result"], transporting=True)) >= 2)
NO_BOUNDARY = sorted(
    name for name in TRANSPORT_ROWS
    if _routes(SHAPES[name]["result"], transporting=False))


def _refused(name, edit, match):
    """One forgery, put to the strongest door that reads this answer."""
    pair = SHAPES[name]
    bad = copy.deepcopy(pair["result"])
    edit(_block(bad))
    with pytest.raises(Exception, match=match):
        the_door_for(pair["result"])(pair["program"], bad)


def test_the_corpus_asks_these_questions_of_something():
    """Rosters that came out empty would make every test below pass while
    asking nothing."""
    assert (len(TRANSPORT_ROWS), len(WITH_DIAGRAM), len(WITH_ROUTE),
            len(TWO_ROUTES), len(NO_BOUNDARY)) == (11, 10, 9, 1, 1)


@pytest.mark.parametrize("name", TRANSPORT_ROWS)
def test_an_answer_that_transports_is_accepted(name):
    """First, because a forgery refused by an answer the doors already
    refuse proves nothing."""
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


# ------------------------------------------- the diagrams are the program's


@pytest.mark.parametrize("name", WITH_DIAGRAM)
def test_a_diagram_about_another_variable_is_refused(name):
    """Which variable differs between the domains is the whole of what
    transports, and the block said it without anybody asking."""
    def edit(block):
        block["s_nodes"][0]["affects"]["predicate"] += "_forged"
    _refused(name, edit, "the program declares it about")


@pytest.mark.parametrize("name", WITH_DIAGRAM)
def test_a_diagram_about_another_unit_is_refused(name):
    """An atom is its arguments as much as its predicate: a diagram about
    ``z1(me)`` is not one about ``z1(nobody)``."""
    def edit(block):
        args = block["s_nodes"][0]["affects"].get("args")
        if not args:
            pytest.skip("this diagram's variable takes no argument")
        args[0]["name"] += "_forged"
    _refused(name, edit, "the program declares it about")


@pytest.mark.parametrize("name", WITH_DIAGRAM)
def test_a_diagram_the_program_never_declared_is_refused(name):
    def edit(block):
        block["s_nodes"][0]["id"] = "S_invented"
    _refused(name, edit, "declares no selection node of that name")


@pytest.mark.parametrize("name", WITH_DIAGRAM)
def test_a_declared_diagram_dropped_from_the_roster_is_refused(name):
    """The direction a block alone can never be asked. Dropping a source
    domain from the roster is dropping it from the verdict, and the block
    that lost it agrees with itself perfectly."""
    def edit(block):
        block["s_nodes"].pop(0)
        for route in block.get("sources") or ():
            route["s_nodes"] = []
    _refused(name, edit, "the block shows none of them")


@pytest.mark.parametrize("name", WITH_DIAGRAM)
def test_a_diagram_moved_to_another_domain_is_refused(name):
    def edit(block):
        block["s_nodes"][0]["source_population"] = "somewhere_else"
    _refused(name, edit, "the program declares it for")


# ----------------------------------------------- the routes are the chain's


@pytest.mark.parametrize("name", WITH_ROUTE)
def test_an_adjustment_set_the_chain_never_recorded_is_refused(name):
    """What a route says it adjusted for is what the step that produced
    its formula was handed, and nothing else."""
    def edit(block):
        route = next(r for r in block["sources"]
                     if r.get("transportable") and r.get("s_nodes"))
        if not route.get("adjustment_set"):
            pytest.skip("this route adjusts for nothing")
        route["adjustment_set"][0]["predicate"] += "_forged"
    _refused(name, edit, "recorded that set and produced that formula")


@pytest.mark.parametrize("name", WITH_ROUTE)
def test_an_estimand_the_chain_never_produced_is_refused(name):
    def edit(block):
        route = next(r for r in block["sources"]
                     if r.get("transportable") and r.get("s_nodes"))
        route["formula_repr"] = "P*(y | do(x)) = 1"
    _refused(name, edit, "recorded that set and produced that formula")


@pytest.mark.parametrize("name", TWO_ROUTES)
def test_two_routes_with_their_adjustment_sets_swapped_are_refused(name):
    """Why the pair is asked together. Each half on its own is still a
    thing the chain recorded -- just not on that route -- so a rule
    asking them separately would accept the swap and a reader would be
    told the wrong domain needed the wrong variables."""
    def edit(block):
        a, b = [r for r in block["sources"]
                if r.get("transportable") and r.get("s_nodes")][:2]
        if a.get("adjustment_set") == b.get("adjustment_set"):
            pytest.skip("both routes adjust for the same variables")
        a["adjustment_set"], b["adjustment_set"] = (
            b["adjustment_set"], a["adjustment_set"])
    _refused(name, edit, "recorded that set and produced that formula")


# ------------------------------------ the population is the question's


@pytest.mark.parametrize("name", TRANSPORT_ROWS)
def test_an_answer_carried_to_another_population_is_refused(name):
    """Which population a number is about is the question's fact. A block
    that renames it has changed the answer's subject without changing a
    number."""
    def edit(block):
        block["target_population"] = "somewhere_else"
    _refused(name, edit, "the question asks about")


# --------------------------------------------------- and what is not held


@pytest.mark.parametrize("name", NO_BOUNDARY)
def test_the_no_boundary_routes_estimand_is_not_held_and_that_is_stated(name):
    """A program declaring no selection diagram gets the one no-boundary
    route: its chain took an ordinary route and has no transport step to
    have recorded anything, so there is nothing to hold its printed
    formula against. Holding it would mean restating a rendering in the
    verifier, which buys a string and costs the independence that makes
    the rest of this worth reading. Written as a test rather than as
    prose, so that a later frontier finds it rather than rediscovering
    it.
    """
    pair = SHAPES[name]
    bad = copy.deepcopy(pair["result"])
    route = _routes(bad, transporting=False)[0]
    route["formula_repr"] = "P*(y | do(x)) = 1"
    the_door_for(pair["result"])(pair["program"], bad)
