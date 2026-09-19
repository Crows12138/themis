"""A domain a step names is one the program declares, whole.

A transport step says three things that decide what it is about: the
source it reasons from, the target it reasons to, and the selection nodes
it takes its diagram over. Somebody else wrote all three down first. The
question names the target it asks about; the program's selection nodes
name the pairs and the nodes that mark them. The step restates them, and
a restatement is held to what it restates.

What the two halves were doing instead, measured on the stored answers:

- the ids were held to what the list CONTAINS (each one declared, all of
  one source) and never to what it OMITS. Bareinboim's Theorem 1 is about
  the omission: Z is S-admissible when EVERY selection node of the domain
  is d-separated from the outcome given Z. The empty list is that taken to
  its end -- no S node, a selection diagram equal to the causal graph,
  every adjustment set admissible for free -- and it was accepted on all
  nine stored transport answers.
- the populations were held to being non-empty strings, which holds a
  label to being a label and never to being the right one.

The third fact is about the CHAIN rather than about a step, and it lives
where the chain is: a route in the transport block claims a source, an
adjustment set and an estimand, and the step it points at has to have
recorded all three. The source was outside that tuple, so with two
declared domains a step could say it transported from the other one and
each end still lined up.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

from tests.answer_corpus import the_door_for, verify_honestly
from themis.types import Atom, ConstTerm, SelectionNode
from themis.verifier.rules import (
    RuleCheckFailed,
    _every_domain_a_step_names_is_one_the_program_declares,
    _the_domains_the_program_declares,
)

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

KEYS = ("selection_nodes_ids", "source_population", "target_population")


def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name="me"),))


def _node(node_id: str, affects: str, source: str, target: str):
    return SelectionNode(id=node_id, affects=_atom(affects),
                         source_population=source, target_population=target)


class _Question:
    def __init__(self, target_population=None):
        self.target_population = target_population


class _Ctx:
    def __init__(self, nodes=(), asked=None):
        self.selection_nodes = tuple(nodes)
        self.query = _Question(asked)


def _ask(ctx, **inputs) -> None:
    _every_domain_a_step_names_is_one_the_program_declares(
        ctx, inputs, 0, "a_rule")


def _refuses(ctx, **inputs) -> str:
    with pytest.raises(RuleCheckFailed) as caught:
        _ask(ctx, **inputs)
    return str(caught.value)


TWO_SOURCES = _Ctx(
    (_node("S_us", "z1", "rct_us", "here"),
     _node("S_eu", "z2", "rct_eu", "here")), asked="here")
ONE_DOMAIN = _Ctx(
    (_node("S_a", "z1", "trial", "here"),
     _node("S_b", "z2", "trial", "here")), asked="here")


# --------------------------------------------- what a program declares

def test_a_domain_is_a_pair_and_the_nodes_that_mark_it():
    assert _the_domains_the_program_declares(ONE_DOMAIN) == {
        ("trial", "here"): frozenset({"S_a", "S_b"})}


def test_two_sources_to_one_target_are_two_domains():
    assert _the_domains_the_program_declares(TWO_SOURCES) == {
        ("rct_us", "here"): frozenset({"S_us"}),
        ("rct_eu", "here"): frozenset({"S_eu"})}


def test_one_source_to_two_targets_are_two_domains():
    """Why the key is the pair and not the source. One source carried to
    two targets is two transport problems and two selection diagrams, and
    a table keyed on the source alone would call them one."""
    ctx = _Ctx((_node("S_a", "z1", "trial", "here"),
                _node("S_b", "z2", "trial", "there")))
    assert _the_domains_the_program_declares(ctx) == {
        ("trial", "here"): frozenset({"S_a"}),
        ("trial", "there"): frozenset({"S_b"})}


def test_a_program_with_no_selection_node_declares_no_domain():
    assert _the_domains_the_program_declares(_Ctx()) == {}


# --------------------------------------------------- where it declines

def test_a_program_that_declares_nothing_is_not_asked():
    """A membership question with nothing to be a member of has no
    content, the same way the atom roster declines on a problem with no
    graph. Not a hole: the names a step would be held to are the ones a
    selection node introduces, and there are none."""
    _ask(_Ctx(), source_population="anywhere", target_population="elsewhere",
         selection_nodes_ids="whatever")


def test_an_id_the_program_does_not_declare_is_left_to_the_rule():
    """The rule that resolves the ids names WHICH one is unknown and this
    cannot, so this stays silent and lets the better message speak."""
    _ask(ONE_DOMAIN, selection_nodes_ids="S_a,S_nope")


def test_a_population_that_is_not_a_string_is_not_a_claim():
    _ask(ONE_DOMAIN, source_population=None, target_population=None)


def test_a_question_that_names_no_population_does_not_speak():
    """An identify question carries no target population. The domain
    check below still applies; the comparison with the question does
    not."""
    ctx = _Ctx(ONE_DOMAIN.selection_nodes, asked=None)
    _ask(ctx, source_population="trial", target_population="here")


# ------------------------------------------------ the selection nodes

def test_the_whole_of_one_domain_is_accepted():
    _ask(ONE_DOMAIN, selection_nodes_ids="S_a,S_b")


def test_a_domain_with_one_node_left_out_is_refused():
    """The omission direction, which is the one a forgery wants: every
    dropped selection node is one fewer d-separation the transport
    formula was licensed by."""
    message = _refuses(ONE_DOMAIN, selection_nodes_ids="S_a")
    assert "['S_a']" in message and "S_b" in message
    assert "EVERY selection node" in message


def test_an_empty_list_is_refused():
    """A selection diagram with no S node is the causal graph, and every
    adjustment set is S-admissible in it for free. Accepted on all nine
    stored transport answers before this."""
    assert "[]" in _refuses(ONE_DOMAIN, selection_nodes_ids="")


def test_nodes_from_two_domains_are_not_a_domain():
    assert _refuses(TWO_SOURCES, selection_nodes_ids="S_us,S_eu")


def test_the_order_ids_are_written_in_is_not_a_claim():
    _ask(ONE_DOMAIN, selection_nodes_ids="S_b,S_a")


def test_naming_one_node_twice_names_the_same_set():
    _ask(TWO_SOURCES, selection_nodes_ids="S_us,S_us")


def test_an_absent_list_is_not_spoken_for():
    """Recorded rather than closed. A step that omits the key is read by
    its rule as taking every declared node, which on a two-domain program
    is a diagram nobody made. No stored answer omits it, so there is no
    leaf here to hold, and inventing a claim about the absent case would
    be holding a shape nothing writes."""
    _ask(TWO_SOURCES, treatment=_atom("x"))


# ---------------------------------------------------- the populations

def test_the_pair_the_program_declares_is_accepted():
    _ask(TWO_SOURCES, source_population="rct_us", target_population="here")


def test_a_source_no_node_declares_is_refused():
    assert "declares no selection node between them" in _refuses(
        TWO_SOURCES, source_population="somewhere", target_population="here")


def test_a_pair_each_half_of_which_is_declared_is_still_refused():
    """The halves are not the claim. Two domains, one to each target, and
    a step that crosses them names a pair of real names that no selection
    node ever put together."""
    ctx = _Ctx((_node("S_a", "z1", "trial", "here"),
                _node("S_b", "z2", "study", "there")), asked="there")
    assert _refuses(ctx, source_population="trial", target_population="there")


def test_only_a_source_stated_is_held_to_the_sources():
    _ask(TWO_SOURCES, source_population="rct_eu")
    assert _refuses(TWO_SOURCES, source_population="rct_nowhere")


def test_only_a_target_stated_is_held_to_the_targets():
    _ask(TWO_SOURCES, target_population="here")
    assert _refuses(TWO_SOURCES, target_population="elsewhere")


# ------------------------------------------------------- the question

def test_a_target_the_question_does_not_ask_about_is_refused():
    """Even when the program declares it. An effect in one population is
    not the effect in another, and which one an answer is for is the
    question's fact."""
    ctx = _Ctx((_node("S_a", "z1", "trial", "here"),
                _node("S_b", "z2", "trial", "there")), asked="here")
    message = _refuses(ctx, source_population="trial",
                       target_population="there")
    assert "the question asks about" in message


def test_the_question_speaks_before_the_program_does():
    """Both would refuse a target that is neither asked for nor declared.
    The question's refusal is the one a reader needs, because it names
    what this answer was supposed to be about."""
    assert "the question asks about" in _refuses(
        ONE_DOMAIN, target_population="nowhere")


# ---------------------------------------------------------- the corpus

def _spots(name: str) -> list:
    steps = (SHAPES[name]["result"].get("derivation") or {}).get("steps") or []
    return [(i, key) for i, step in enumerate(steps) for key in KEYS
            if isinstance((step.get("inputs") or {}).get(key), str)]


ROWS = sorted(name for name in SHAPES if _spots(name))
BENDS = {"forged": lambda v: v + "_forged", "empty": lambda v: "",
         "stranger": lambda v: "qqzz"}
SPOTS = [(name, i, key, label)
         for name in ROWS for i, key in _spots(name) for label in BENDS]


def test_the_rosters_are_the_size_they_were_measured_at():
    assert (len(ROWS), len(SPOTS)) == (9, 102)


@pytest.mark.parametrize("name,index,key,label", SPOTS,
                         ids=lambda v: str(v))
def test_a_bent_premise_is_refused(name, index, key, label):
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    inputs = result["derivation"]["steps"][index]["inputs"]
    inputs[key] = BENDS[label](inputs[key])
    with pytest.raises(Exception):
        the_door_for(result)(pair["program"], result)


@pytest.mark.parametrize("name", ROWS)
def test_the_honest_premises_still_pass(name):
    pair = SHAPES[name]
    verify_honestly(pair["program"], pair["result"])


def _droppable() -> list:
    out = []
    for name in ROWS:
        for i, key in _spots(name):
            if key != "selection_nodes_ids":
                continue
            ids = SHAPES[name]["result"]["derivation"]["steps"][i][
                "inputs"][key].split(",")
            if len(ids) > 1:
                out.append((name, i))
    return out


DROPPABLE = _droppable()


def test_some_stored_answer_names_more_than_one_selection_node():
    assert len(DROPPABLE) == 2, DROPPABLE


@pytest.mark.parametrize("name,index", DROPPABLE, ids=lambda v: str(v))
def test_a_selection_node_quietly_dropped_is_refused(name, index):
    """The forgery the old check could not see: every id it names is
    declared, they are all one source's, and one of them is missing."""
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    inputs = result["derivation"]["steps"][index]["inputs"]
    inputs["selection_nodes_ids"] = ",".join(
        inputs["selection_nodes_ids"].split(",")[:-1])
    with pytest.raises(Exception):
        the_door_for(result)(pair["program"], result)


def _reseatable() -> list:
    out = []
    for name in ROWS:
        sources = {s["source_population"]
                   for s in SHAPES[name]["program"].get("statements", [])
                   if isinstance(s, dict) and s.get("kind") == "selection_node"}
        if len(sources) < 2:
            continue
        for i, key in _spots(name):
            if key == "source_population":
                out.append((name, i, sorted(sources)))
    return out


RESEATABLE = _reseatable()


def test_some_stored_answer_declares_more_than_one_source_domain():
    assert len(RESEATABLE) == 4, RESEATABLE


@pytest.mark.parametrize("name,index,sources", RESEATABLE, ids=lambda v: str(v))
def test_a_step_reseated_on_another_declared_domain_is_refused(
        name, index, sources):
    """A source the program really does declare, stated by a step whose
    route claims the other one. Both ends are real names and the pair is
    a declared pair, so nothing that reads one step can see it; what sees
    it is the route, which claims a source and now has to point at a step
    that recorded the same one."""
    pair = SHAPES[name]
    result = copy.deepcopy(pair["result"])
    inputs = result["derivation"]["steps"][index]["inputs"]
    other = [s for s in sources if s != inputs["source_population"]][0]
    inputs["source_population"] = other
    with pytest.raises(Exception):
        the_door_for(result)(pair["program"], result)
