"""A reader is asked for the conditional the graph reads, in a statement
the kernel takes back.

A back-door adjustment over two confounders is a sum over their joint, and
the formula builder writes the joint by the chain rule in the order the
adjustment set came in: ``P(z)·P(w|z)``, whether or not the graph connects
the two. The evaluator already knew better. Where the graph separates the
target from part of what a factor conditions on, it reads the shorter
conditional whenever theta holds one. But the ask left the evaluator
spelt the way the formula wrote it, so:

- with two independent confounders a reader was sent for ``P(w|z)`` at
  every value of ``z``, twice the cells the evaluation reads; and the
  statement they filled in was refused at the input door, because ``z`` is
  neither a parent, an ancestor nor a bidirected sibling of ``w``;
- with two confounders sharing a cause, ``P(w|z)`` is the right number and
  the statement for it was refused all the same, because the stub did not
  say what the door requires such a statement to say: that it is an
  observational conditional;
- and a transported question's stub left out the population its key
  names, so the number a reader pasted back landed in the default
  population's table and the ask stayed open.

What is pinned here:

- ``_as_asked`` cuts a key to the fewest atoms of its conditioning given
  which the graph separates the target from the rest, and leaves it alone
  without a graph;
- on the shapes that raised it, the asks are those conditionals, every stub
  pastes back as written, and pasting all of them leaves no parameter
  asked;
- a stub carries its population, and pasting it answers the ask;
- the transported question is evaluated against the graph's bidirected
  edges like every other formula, so a marginal the graph refuses no
  longer stands in for the conditional;
- the verifier refuses a stub whose population, or observational mark,
  disagrees with what the door takes back, and an ask conditioning on an
  atom the graph separates from its target.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis import kernel
from themis.runtime.numeric_estimator import ProbabilityKey, _as_asked
from themis.types import Atom
from themis.verifier import investigation_rules
from themis.verifier.errors import VerificationError

import networkx as nx


def _atom(name: str) -> Atom:
    return Atom(predicate=name, args=())


A, B, C, W, X, Y, Z = (_atom(n) for n in "abcwxyz")


def _key(atom, value, given=(), population=None) -> ProbabilityKey:
    return ProbabilityKey(target_atom=atom, target_value=value,
                          given=frozenset(given), population=population)


def _graph(*edges) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_edges_from(edges)
    return graph


# --- the rule ----------------------------------------------------------------

def test_without_a_graph_the_key_is_asked_as_spelt():
    key = _key(W, True, [(Z, True)])
    assert _as_asked(key) == key
    assert _as_asked(key, graph=_graph((Z, X), (W, X))) == key


def test_a_confounder_independent_of_the_other_is_asked_for_alone():
    graph = _graph((Z, X), (Z, Y), (W, X), (W, Y), (X, Y))
    asked = _as_asked(_key(W, True, [(Z, False)], population="trial"),
                      graph=graph, bidirected=frozenset())
    assert asked == _key(W, True, population="trial")


def test_two_confounders_sharing_a_cause_keep_each_other():
    graph = _graph((C, Z), (C, W), (Z, X), (W, X), (Z, Y), (W, Y), (X, Y))
    key = _key(W, True, [(Z, True)])
    assert _as_asked(key, graph=graph, bidirected=frozenset()) == key


def test_a_latent_link_keeps_them_too():
    graph = _graph((Z, X), (W, X), (Z, Y), (W, Y), (X, Y))
    key = _key(W, True, [(Z, True)])
    assert _as_asked(key, graph=graph,
                     bidirected=frozenset({frozenset({Z, W})})) == key


def test_a_chain_keeps_the_link_nearest_the_target():
    graph = _graph((A, B), (B, Y))
    asked = _as_asked(_key(Y, True, [(A, True), (B, False)]),
                      graph=graph, bidirected=frozenset())
    assert asked == _key(Y, True, [(B, False)])


def test_a_parent_is_never_cut():
    graph = _graph((Z, Y), (X, Y), (Z, X))
    key = _key(Y, True, [(X, True), (Z, True)])
    assert _as_asked(key, graph=graph, bidirected=frozenset()) == key


# --- the shapes that raised it ------------------------------------------------

def _a(name):
    return {"predicate": name, "args": []}


def _program(variables, edges, *, bidirected=()):
    statements = [{"kind": "variable", "predicate": v, "domain": [True, False]}
                  for v in variables]
    statements += [{"kind": "cause", "from": _a(a), "to": _a(b)}
                   for a, b in edges]
    statements += [{"kind": "bidirected", "left": _a(a), "right": _a(b)}
                   for a, b in bidirected]
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [],
        "intervention": {"atom": _a("x"), "value": True},
        "target": {"atom": _a("y"), "value": True}}})
    return {"version": "0.1", "domain": {"objects": []},
            "statements": statements}


def _confounded(*confounders, extra=()):
    edges = [(c, t) for c in confounders for t in ("x", "y")]
    return _program(("x", "y", *confounders, *{a for a, _ in extra}),
                    [*edges, *extra, ("x", "y")])


SHAPES = {
    "two independent confounders": _confounded("z", "w"),
    "three independent confounders": _confounded("a", "b", "d"),
    "two confounders sharing a cause": _confounded(
        "z", "w", extra=(("c", "z"), ("c", "w"))),
}

#: What each shape asks for: its conditionals of the confounders, and
#: which of them the stub marks observational.
CONFOUNDER_ASKS = {
    "two independent confounders": {"P(z=True)": False, "P(w=True)": False},
    "three independent confounders": {
        "P(a=True)": False, "P(b=True)": False, "P(d=True)": False},
    "two confounders sharing a cause": {
        "P(z=True)": False,
        "P(w=True|z=True)": True, "P(w=True|z=False)": True},
}


def _items(result):
    return [item for request in result.get("investigation_requests") or ()
            for item in request.get("items") or ()
            if (item.get("skeleton") or {}).get("kind") == "probability"]


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_the_confounders_are_asked_for_as_the_graph_reads_them(shape):
    program = SHAPES[shape]
    result = themis.run(copy.deepcopy(program))["results"][0]
    themis.verify_answer_claims(copy.deepcopy(program), result)
    asked = {item["said"]["key"]: item["skeleton"].get("provenance")
             == "observational"
             for item in _items(result)
             if item["skeleton"]["target"]["atom"]["predicate"] != "y"}
    assert asked == CONFOUNDER_ASKS[shape]
    marked = [item["said"]["key"] for item in _items(result)
              if item["skeleton"]["target"]["atom"]["predicate"] == "y"
              and "provenance" in item["skeleton"]]
    assert not marked


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_stub_pasted_back_as_written_is_taken(shape):
    """Through the door a reader uses, all at once: nothing is refused, and
    nothing is left to ask."""
    program = SHAPES[shape]
    result = themis.run(copy.deepcopy(program))["results"][0]
    filled = [dict(item["skeleton"], value=0.3) for item in _items(result)]
    again = themis.apply_patch_and_run(copy.deepcopy(program), filled)
    [answer] = again["results"]
    assert answer["status"] == "numerically_solved"
    assert not [m for m in answer.get("missing_information") or ()
                if m.get("kind") == "parameter"]


# --- the population -----------------------------------------------------------

def _me(name):
    return {"predicate": name, "args": [{"type": "const", "name": "me"}]}


TRANSPORTED = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        *({"kind": "variable", "predicate": v, "domain": [True, False]}
          for v in ("z", "x", "y")),
        {"kind": "cause", "from": _me("z"), "to": _me("x")},
        {"kind": "cause", "from": _me("z"), "to": _me("y")},
        {"kind": "cause", "from": _me("x"), "to": _me("y")},
        {"kind": "selection_node", "id": "s_z", "affects": _me("z"),
         "source_population": "trial", "target_population": "user"},
        {"kind": "query", "id": "q", "query": {
            "kind": "effect", "given": [],
            "intervention": {"atom": _me("x"), "value": True},
            "target": {"atom": _me("y"), "value": True},
            "target_population": "user"}},
    ],
}

SOURCE_ASK = "parameter:P_trial(y=True|x=True,z=True)"


def _names(result):
    return [row["name"] for row in result.get("missing_information") or ()]


def test_a_transported_stub_names_its_population_and_answers_its_ask():
    result = themis.run(copy.deepcopy(TRANSPORTED))["results"][0]
    themis.verify_answer_claims(copy.deepcopy(TRANSPORTED), result)
    [item] = [i for i in _items(result) if i["target"] == SOURCE_ASK]
    assert item["skeleton"]["population"] == "trial"
    again = themis.apply_patch_and_run(
        copy.deepcopy(TRANSPORTED), [dict(item["skeleton"], value=0.6)])
    assert SOURCE_ASK not in _names(again["results"][0])


def test_a_marginal_the_graph_refuses_does_not_stand_in_for_a_transported_factor():
    """The transported route read ``P_trial(y|x)`` for ``P_trial(y|x,z)``
    unchecked, although ``z`` causes ``y``, and with ``P_user(z)`` supplied
    answered 0.6: the trial's marginal, as if every stratum of ``z`` had it.
    It was the one formula evaluated without the graph's bidirected edges,
    which is what the evaluator's separation check needs to run."""
    program = copy.deepcopy(TRANSPORTED)
    program["statements"][-1:-1] = [
        {"kind": "probability", "population": "trial",
         "target": {"atom": _me("y"), "value": True},
         "given": [{"atom": _me("x"), "value": True}],
         "value": 0.6, "annotations": {"source": "a trial"}},
        {"kind": "probability", "population": "user",
         "target": {"atom": _me("z"), "value": True}, "given": [],
         "value": 0.3, "annotations": {"source": "a survey"}},
    ]
    result = themis.run(copy.deepcopy(program))["results"][0]
    themis.verify_answer_claims(copy.deepcopy(program), result)
    assert result["status"] != "numerically_solved"
    [row] = [r for r in result["missing_information"]
             if r["name"] == SOURCE_ASK]
    assert row["need"] == "graph_contradicts_supplied_marginal"


# --- the verifier ------------------------------------------------------------

def _forge(program, key, change):
    result = themis.run(copy.deepcopy(program))["results"][0]
    themis.verify_answer_claims(copy.deepcopy(program), result)
    forged = copy.deepcopy(result)
    [item] = [i for i in _items(forged) if i["said"]["key"] == key]
    change(item["skeleton"])
    return forged


def test_a_stub_without_its_population_is_refused():
    forged = _forge(TRANSPORTED, SOURCE_ASK.split(":", 1)[1],
                    lambda stub: stub.pop("population"))
    with pytest.raises(VerificationError, match="theta keys a number by its "
                                                "population"):
        themis.verify_answer_claims(copy.deepcopy(TRANSPORTED), forged)


def test_a_stub_that_would_be_refused_at_the_door_is_refused_here():
    program = SHAPES["two confounders sharing a cause"]
    forged = _forge(program, "P(w=True|z=True)",
                    lambda stub: stub.pop("provenance"))
    with pytest.raises(VerificationError, match="refused on arrival"):
        themis.verify_answer_claims(copy.deepcopy(program), forged)


def test_a_model_parameter_marked_observational_is_refused():
    program = SHAPES["two independent confounders"]
    forged = _forge(program, "P(z=True)",
                    lambda stub: stub.__setitem__("provenance",
                                                  "observational"))
    with pytest.raises(VerificationError, match="measured conditional"):
        themis.verify_answer_claims(copy.deepcopy(program), forged)


def _chain_ask(need):
    """``a → b → y`` asked for ``P(y|a,b)``: the graph separates ``y`` from
    ``a`` given ``b``."""
    program = _program(("a", "b", "x", "y"),
                       [("a", "b"), ("b", "y"), ("x", "y")])
    result = {"query_id": "q", "investigation_requests": [{"items": [{
        "need": need,
        "target": "parameter:P(y=True|a=True,b=True)",
        "skeleton": {
            "kind": "probability", "value": None,
            "target": {"atom": _a("y"), "value": True},
            "given": [{"atom": _a("a"), "value": True},
                      {"atom": _a("b"), "value": True}],
            "annotations": {"source": "TODO"}},
    }]}]}
    _, _, _, ctx = kernel._premises_of(copy.deepcopy(program), result)
    return result, ctx


def test_an_ask_conditioning_on_what_the_graph_separates_is_refused():
    result, ctx = _chain_ask("theta_entry_missing")
    with pytest.raises(VerificationError, match="finer table"):
        investigation_rules.verify_asks_against_the_graph(
            result, ctx.graph, ctx.bidirected)


def test_an_ask_read_as_spelt_is_not_held_to_the_graph():
    """An ancestral factorisation looks its keys up as they are spelt, so
    its asks are the keys it reads."""
    result, ctx = _chain_ask("counterfactual_bound_needs_entry")
    investigation_rules.verify_asks_against_the_graph(
        result, ctx.graph, ctx.bidirected)
