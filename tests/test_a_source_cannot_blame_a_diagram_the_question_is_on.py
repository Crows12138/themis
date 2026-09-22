"""A blocked route cannot blame a diagram the question's ends are on.

A source domain that does not transport names which of two things stopped
it. One is a search that came back empty -- no S-admissible adjustment
set. The other is a claim about the GRAPH: that the question's treatment
or its outcome is not a node of this source's selection diagram. The two
send a reader to different places, and only the second is a thing a second
document can answer.

The rule that reads these routes had no graph. Its two siblings over the
same kind of block -- ``verify_selection_recovery`` and
``verify_missing_data_recovery`` -- are each handed one at the same call
site, and both re-derive this very species for their own verdicts. This
one was passed the selection nodes, the chain and the question, and not
the graph, so the word was the one reason a route could give and be
believed.

What is asserted here:

- the corpus exercises the rule, and every blocked route in it states the
  OTHER reason -- so this holds a word the corpus never writes, which is
  why the roster is pinned rather than assumed
- no honest carrier is refused, by the rule and again at the door
- a route that swaps its reason for the diagram one is refused, through
  the public door
- the rule is SILENT where the graph does not carry the question's ends,
  because there the word may be true and nothing here can tell
- and silent about the other reason entirely: whether an S-admissible set
  exists is a search, and running it here would be re-deriving the verdict
  rather than holding the word. That frontier stays open and says so.
- the premise is pinned at the call site, because the premise and not the
  check is what was missing.
"""
from __future__ import annotations

import copy
import inspect
import json
import pathlib

import pytest

from themis import kernel
from themis.types import SelectionNode
from themis.verifier import VerificationError, verify_transport_sources
from themis.verifier.verify import _TRANSPORT_BLOCKED_KINDS

from .answer_corpus import the_door_for, verify_honestly

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json")
    .read_text(encoding="utf-8"))

#: The word this rule is about. Named once: the point of the tests below
#: is that the corpus never says it, and a string repeated in six places
#: is one nobody can count.
OFF_DIAGRAM = "treatment_or_outcome_off_diagram"

#: How many stored answers carry a transport block at all, and how many of
#: those carry a route that did not transport. Pinned because a rule whose
#: subject left the corpus would otherwise go quiet without saying so --
#: and because the second number is the denominator of every forgery here.
ANSWERS_WITH_A_BLOCK = 11
ANSWERS_WITH_A_BLOCKED_ROUTE = 2


def _block(result: dict):
    return (result.get("extensions") or {}).get("transport_identification")


def _carriers() -> list[str]:
    return sorted(name for name, row in SHAPES.items()
                  if isinstance(_block(row["result"]), dict))


def _blocked_carriers() -> list[str]:
    out = []
    for name in _carriers():
        routes = _block(SHAPES[name]["result"]).get("sources") or []
        if any(not r.get("transportable") for r in routes):
            out.append(name)
    return out


def _audit(name: str, result: dict, graph=None) -> None:
    """The rule with the premises the kernel hands it."""
    program = SHAPES[name]["program"]
    _ast, prog, query_stmt, ctx = kernel._premises_of(
        program, SHAPES[name]["result"])
    verify_transport_sources(
        _block(result), ctx.graph if graph is None else graph,
        [s for s in prog.statements if isinstance(s, SelectionNode)],
        (result.get("derivation") or {}).get("steps") or (),
        query_stmt.query)


def test_the_corpus_exercises_this_rule():
    assert len(_carriers()) == ANSWERS_WITH_A_BLOCK, _carriers()
    assert len(_blocked_carriers()) == ANSWERS_WITH_A_BLOCKED_ROUTE, \
        _blocked_carriers()


def test_the_corpus_states_the_other_reason():
    """Every blocked route in the corpus blames the search, not the graph.

    Which is what makes the word this rule refuses a word no run of this
    system produces: a query naming an atom outside V is refused before
    identification, so the species guards a layer a reader never reaches.
    It stays in the vocabulary, and stays refusable here, because an
    envelope is a document anyone can write.
    """
    said = set()
    for name in _blocked_carriers():
        for route in _block(SHAPES[name]["result"])["sources"]:
            if not route.get("transportable"):
                said.add(route.get("blocked_by"))
    assert said == {"no_s_admissible_set"}, said
    assert OFF_DIAGRAM in _TRANSPORT_BLOCKED_KINDS


@pytest.mark.parametrize("name", _carriers())
def test_no_honest_carrier_is_refused(name):
    """The denominator, by the rule and again at the strongest door that
    reads it -- a rule that refuses an honest answer fails here rather
    than in the remainder sweep."""
    row = SHAPES[name]
    _audit(name, row["result"])
    verify_honestly(row["program"], row["result"])


def test_a_route_that_blames_the_diagram_is_refused():
    """The forgery this exists for, through the public door.

    A reader handed this word goes looking for a variable that is not in
    the model. The graph says it is there.
    """
    for name in _blocked_carriers():
        honest = SHAPES[name]["result"]
        forged = copy.deepcopy(honest)
        for route in _block(forged)["sources"]:
            if not route.get("transportable"):
                route["blocked_by"] = OFF_DIAGRAM
        with pytest.raises(VerificationError, match="off its diagram"):
            the_door_for(honest)(SHAPES[name]["program"], forged)


def test_the_rule_is_silent_where_the_graph_lacks_an_end():
    """Where the word could be true, nothing here says otherwise.

    Built by taking the outcome off the graph the run was given, which is
    the only way to reach the case: the kernel refuses a query naming an
    atom outside V before any of this runs.
    """
    name = _blocked_carriers()[0]
    honest = SHAPES[name]["result"]
    _ast, _prog, query_stmt, ctx = kernel._premises_of(
        SHAPES[name]["program"], honest)
    forged = copy.deepcopy(honest)
    for route in _block(forged)["sources"]:
        if not route.get("transportable"):
            route["blocked_by"] = OFF_DIAGRAM

    target = getattr(query_stmt.query, "target", None)
    y = getattr(target, "atom", target)
    lame = ctx.graph.copy()
    lame.remove_node(y)
    _audit(name, forged, graph=lame)


def test_the_search_is_not_re_derived_and_says_so():
    """The other half of the pair stays open, and this says which.

    Stated rather than left to a reader of the diff: a rule that decided
    whether an S-admissible set exists would be re-deriving the verdict,
    which is a frontier of its own. So the honest word is accepted here
    whatever the graph shows, and the leaf it sits on is not claimed.
    """
    for name in _blocked_carriers():
        _audit(name, SHAPES[name]["result"])


def test_the_rule_is_handed_the_graph_like_its_siblings():
    """The premise, not the check, is what was missing.

    Pinned at the call site: three rules read a block of this kind and the
    other two were already given the graph. A signature that drifts back
    fails here rather than in a sweep three hundred leaves wide.
    """
    sig = inspect.signature(verify_transport_sources)
    assert list(sig.parameters)[:2] == ["block", "graph"], list(sig.parameters)
    source = inspect.getsource(kernel._audit_transport_identification)
    assert "facts.graph" in source, source
