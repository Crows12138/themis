"""S-admissibility was re-derived, about whichever variable you like.

``s_admissibility_check`` re-derives Bareinboim Theorem 1: every selection
node is d-separated from the outcome given Z, in the intervention graph.
The step records the outcome it was taken over, and nothing compared that
to the question. So the rule could re-derive a TRUE sentence about the
wrong variable, and a transport formula is licensed by it.

Measured before this: swapping the recorded outcome for another real node
of the diagram passed 10 of 11 answers (``y`` for ``x``), and replacing it
with a name no node has passed all 11.

The second is worse than unchecked, and the mechanism is one guard doing
two jobs::

    for s in s_atoms:
        if s not in g_bar_x or outcome not in g_bar_x:
            continue

An S node outside the mutilated graph is IRRELEVANT to this check and is
rightly skipped. The outcome being outside it is not irrelevance, it is
the absence of a subject — nothing to test rather than nothing to say.
Sharing one guard, a missing subject read as "every S is irrelevant",
``recomputed`` stayed True, and admissibility was confirmed having tested
nothing at all.

Why the treatment looked safe: it is not verified either. It builds the
graph under test — ``G_bar_X`` mutilates ITS in-edges — so moving it
changes the answer and shows up. Incidental coupling is not verification,
and it protects exactly the fields that happen to have it.

The three refusals below are reached deliberately, including the two the
corpus cannot show, because a branch no test enters is a branch nobody has
seen work.
"""
from __future__ import annotations

import copy
import json
import pathlib

import networkx as nx
import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.verifier.context import VerificationContext
from themis.verifier.errors import RuleCheckFailed
from themis.verifier.rules import _rule_s_admissibility_check

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

RULE = "s_admissibility_check"

STEPS = sorted(
    (name, i)
    for name, pair in SHAPES.items()
    for i, step in enumerate(
        ((pair["result"] or {}).get("derivation") or {}).get("steps") or [])
    if step.get("rule") == RULE
)


def test_the_steps_that_claim_admissibility():
    """10 since a question naming a population nothing separates stopped
    carrying a transport chain: there is no source domain for a selection
    node to be admissible from, and it is answered in its one population."""
    assert len(STEPS) == 10, len(STEPS)


@pytest.mark.parametrize("name,i", STEPS)
def test_an_honest_step_is_accepted(name, i):
    """The half a rule of this kind gets wrong by being too strict."""
    verify_honestly(SHAPES[name]["program"], SHAPES[name]["result"])


def test_an_outcome_no_node_has_is_refused():
    """Previously the vacuous one: it skipped every S and confirmed."""
    refused = 0
    for name, i in STEPS:
        row = SHAPES[name]
        forged = copy.deepcopy(row["result"])
        forged["derivation"]["steps"][i]["inputs"]["outcome"]["predicate"] = \
            "nobody"
        with pytest.raises(Exception):                          # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 10, refused


def test_an_outcome_that_is_a_real_node_but_the_wrong_one_is_refused():
    """The lie the sweep never tries, and the one the graph guard misses.

    A sweep bending a string reaches for names nothing declares. Swapping
    in a variable the diagram really has is the edit that survives a
    "must exist" rule, and it is the one that produces a true sentence
    about the wrong outcome.
    """
    refused = 0
    for name, i in STEPS:
        row = SHAPES[name]
        step = row["result"]["derivation"]["steps"][i]
        honest = step["inputs"]["outcome"]["predicate"]
        other = step["inputs"]["treatment"]["predicate"]
        assert other != honest, name

        forged = copy.deepcopy(row["result"])
        forged["derivation"]["steps"][i]["inputs"]["outcome"]["predicate"] = other
        with pytest.raises(Exception, match="question asks about"):  # noqa: B017
            the_door_for(row["result"])(row["program"], forged)
        refused += 1
    assert refused == 10, refused


def _atom(predicate: str):
    from themis.types import Atom
    return Atom(predicate=predicate, args=())


def test_an_outcome_the_diagram_does_not_carry_is_refused():
    """The branch the corpus cannot reach, reached on purpose.

    On every corpus answer the question's outcome is a node of the
    diagram, so the guard above always speaks first and this one never
    runs. It is what stands between a subject-less check and a confirmed
    admissibility when a program's target is not in the graph it ships.
    """
    from themis.types import EffectQuery, Intervention, ValuedAtom

    y, x = _atom("y"), _atom("x")
    graph = nx.DiGraph()
    graph.add_edge(x, _atom("w"))          # y is deliberately absent

    ctx = VerificationContext(
        graph=graph,
        query=EffectQuery(
            target=ValuedAtom(atom=y, value=True),
            intervention=Intervention(atom=x, value=True),
            given=()),
    )
    with pytest.raises(RuleCheckFailed, match="no such node"):
        _rule_s_admissibility_check(
            ctx,
            {"treatment": x, "outcome": y, "adjustment_set": frozenset()},
            True, 0)


def test_a_question_with_no_outcome_is_refused_not_skipped():
    """A target is written two ways and reading one is how this goes quiet.

    An effect or probability question carries a ``ValuedAtom``; an
    identify question carries the ``Atom`` itself. A rule reaching only
    for ``.atom`` gets ``None`` on the second kind and, if that means
    "skip", stops checking on a whole family of questions without
    anything going red. Unresolvable is refused instead.
    """
    from themis.types import CauseQuery

    x = _atom("x")
    graph = nx.DiGraph()
    graph.add_edge(x, _atom("y"))
    ctx = VerificationContext(
        graph=graph, query=CauseQuery(from_atom=x, to_atom=_atom("y")))

    with pytest.raises(RuleCheckFailed, match="cannot tell what this question"):
        _rule_s_admissibility_check(
            ctx,
            {"treatment": x, "outcome": _atom("y"),
             "adjustment_set": frozenset()},
            True, 0)


def test_an_identify_question_writes_its_target_the_other_way():
    """The shape that would have been skipped, accepted on its merits.

    ``IdentifyQuery.target`` is a bare Atom rather than a ValuedAtom, so
    this asserts the accessor reads both — otherwise the refusal above
    would fire on an honest identify question and the fix for one silence
    would be a false positive on another.
    """
    from themis.types import IdentifyQuery, Intervention

    y, x = _atom("y"), _atom("x")
    graph = nx.DiGraph()
    graph.add_edge(x, y)
    ctx = VerificationContext(
        graph=graph,
        query=IdentifyQuery(target=y, given=(),
                            intervention=Intervention(atom=x, value=True)),
    )
    # No selection nodes declared, so admissibility is vacuously True and
    # the claim matches; what matters is that it got PAST the subject
    # checks rather than being refused for the shape of its target.
    _rule_s_admissibility_check(
        ctx, {"treatment": x, "outcome": y, "adjustment_set": frozenset()},
        True, 0)
