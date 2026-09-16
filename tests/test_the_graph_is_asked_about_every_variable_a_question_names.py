"""The graph is asked about every variable a question names, in one reading.

Three places ask whether what a question names is a node of the working
graph: the projection, which admits a declared variable with no edge as a
node when a question names it; the validator, which refuses a program whose
question names one that is no node; and each dispatcher, before it tries a
route. Each had written its own list of which fields hold a variable. None
listed the mediator block, the projection and the validator left out the
mediator as well, and the projection left out the causation kind — while the
framing check, which tells a reader which of those variables still needs
defining, reads every field.

So a declared mediator in no edge was a variable an answer told its reader
to define and a node the graph did not have, and the verifier, reading this
problem's names off the graph, refused the honest answer for naming a
variable the problem does not have. An undeclared one got past the validator
that refuses an undeclared treatment: a lone mediator came back as an atom
the graph lacks, and a member of a mediator block as a block off the directed
paths, which the verifier refused in turn for naming no node.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis.input.semantic_validator import (
    Malformed,
    SemanticError,
    validate_against_graph,
)
from themis.kernel import validate_ast, validate_program
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.runtime.scheduler import _dispatch_effect
from themis.runtime.theta_builder import build_theta
from themis.types import (
    Atom,
    CausationQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ProbabilityQuery,
    Program,
    QueryStatement,
    ValuedAtom,
    VariableDeclaration,
    atoms_held_by,
    atoms_the_graph_is_asked_about,
)
from themis.verifier.errors import VerificationError
from themis.verifier.gap_claim_rules import names_said

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))


def _atom(predicate: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name="u"),))


X, Y, Z, M = _atom("x"), _atom("y"), _atom("z"), _atom("m")


def _effect(**fields) -> EffectQuery:
    fields.setdefault("given", ())
    return EffectQuery(target=ValuedAtom(atom=Y, value=True),
                       intervention=Intervention(atom=X, value=True),
                       **fields)


#: A question naming ``m`` in one field, where ``m`` takes part in no edge.
#: The first three are the fields the lists left out; the rest were always
#: listed, and are here so the reading is seen to be one for all of them.
QUESTIONS = {
    "the mediator": _effect(mediator=M),
    "a member of the mediator block": _effect(mediators=(Z, M)),
    "the cause of a causation question": CausationQuery(cause=M, effect=Y),
    "the second treatment": _effect(
        extra_interventions=(Intervention(atom=M, value=True),)),
    "what an effect is conditioned on": _effect(
        given=(ValuedAtom(atom=M, value=True),)),
    "what an identification is conditioned on": IdentifyQuery(
        target=Y, intervention=Intervention(atom=X, value=True), given=(M,)),
}


def _program(query, *, declared: bool) -> Program:
    names = ("x", "y", "z", "m") if declared else ("x", "y", "z")
    return Program(version="0.1", objects=("u",), statements=(
        *(VariableDeclaration(predicate=n, domain=(True, False))
          for n in names),
        CauseStatement(from_atom=X, to_atom=Z),
        CauseStatement(from_atom=Z, to_atom=Y),
        CauseStatement(from_atom=X, to_atom=Y),
        QueryStatement(id="q", query=query),
    ))


def _ground_and_graph(program):
    ground = instantiate(program)
    return ground, project(ground)


@pytest.mark.parametrize("field", sorted(QUESTIONS))
def test_a_declared_variable_is_a_node_whichever_field_names_it(field):
    ground, graph = _ground_and_graph(
        _program(QUESTIONS[field], declared=True))
    assert M in graph
    assert graph.degree(M) == 0
    validate_against_graph(ground, graph)


@pytest.mark.parametrize("field", sorted(QUESTIONS))
def test_an_undeclared_one_is_refused_at_the_door_whichever_field(field):
    """The rule a treatment was always held to."""
    ground, graph = _ground_and_graph(
        _program(QUESTIONS[field], declared=False))
    assert M not in graph
    with pytest.raises(SemanticError) as raised:
        validate_against_graph(ground, graph)
    assert raised.value.species is Malformed.QUERY_ATOM_NOT_IN_GRAPH
    assert raised.value.details["atoms"] == ["m"]


def test_a_dispatcher_asks_the_graph_about_the_block_too():
    """Called past the validator, a member of the block the graph lacks is
    an atom the graph lacks — not a block that sits off the paths."""
    program = _program(QUESTIONS["a member of the mediator block"],
                       declared=False)
    ground, graph = _ground_and_graph(program)
    stmt = next(s for s in program.statements
                if isinstance(s, QueryStatement))
    result = _dispatch_effect(stmt, graph, build_theta(ground))
    assert [(str(item.need), item.name)
            for item in result.missing_information] == [
        ("atom_not_in_graph", "atom:m(u)")]


def test_the_reading_is_the_walk_and_a_probability_asks_the_graph_nothing():
    """Asked of every question in the corpus."""
    seen = {"probability": 0, "other": 0}
    for name in sorted(SHAPES):
        program = validate_program(validate_ast(SHAPES[name]["program"]))
        for stmt in program.statements:
            if not isinstance(stmt, QueryStatement):
                continue
            asked = atoms_the_graph_is_asked_about(stmt.query)
            if isinstance(stmt.query, ProbabilityQuery):
                seen["probability"] += 1
                assert asked == (), name
            else:
                seen["other"] += 1
                assert asked == atoms_held_by(stmt.query), name
    assert seen["probability"] and seen["other"]


# ======================================= what a reader is told, both sides


def _a(predicate):
    return {"predicate": predicate, "args": [{"type": "const", "name": "me"}]}


def _document(variables, causes, **query):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            *({"kind": "variable", "predicate": n, "domain": [True, False]}
              for n in variables),
            *({"kind": "cause", "from": _a(a), "to": _a(b)}
              for a, b in causes),
            {"kind": "query", "id": "q", "query": query},
        ],
    }


def _effect_document(variables, causes, **extra):
    return _document(variables, causes, kind="effect",
                     intervention={"atom": _a("x"), "value": True},
                     target={"atom": _a("y"), "value": True},
                     given=[], **extra)


#: Declared variables a question names and no edge touches, and the refusal
#: or verdict each honest answer carries.
HONEST = {
    "a mediator in no edge": (
        _effect_document(("x", "m", "y"), [("x", "y")], mediator=_a("m")),
        "mediator_off_the_directed_paths"),
    "one of a mediator block in no edge": (
        _effect_document(("x", "m1", "m2", "y"),
                         [("x", "m1"), ("m1", "y"), ("x", "y")],
                         mediators=[_a("m1"), _a("m2")]),
        "mediator_set_off_the_directed_paths"),
    "a mediator block wholly in no edge": (
        _effect_document(("x", "m1", "m2", "y"), [("x", "y")],
                         mediators=[_a("m1"), _a("m2")]),
        "mediator_set_off_the_directed_paths"),
    "a causation question over variables in no edge": (
        _document(("x", "y"), [], kind="causation",
                  cause=_a("x"), effect=_a("y")),
        "interventional_risk_needs_distributions"),
}


@pytest.fixture(scope="module")
def answers():
    return {name: next(r for r in themis.run(document)["results"]
                       if r.get("query_id") == "q")
            for name, (document, _need) in HONEST.items()}


@pytest.mark.parametrize("name", sorted(HONEST))
def test_the_honest_answer_is_accepted(name, answers):
    document, need = HONEST[name]
    result = answers[name]
    assert need in {m.get("need") for m in result["missing_information"]}
    declared = {s["predicate"] for s in document["statements"]
                if s["kind"] == "variable"}
    named = {value for _where, value in
             names_said(result["data_gap_report"])}
    assert declared <= named
    verify_honestly(document, result)
    themis.verify_refusal(document, result)


@pytest.mark.parametrize("name", sorted(HONEST))
def test_a_name_the_problem_does_not_have_is_still_refused(name, answers):
    """At every leaf that names a variable, one at a time."""
    document, _need = HONEST[name]
    result = answers[name]
    leaves = [where for where, _value in
              names_said(result["data_gap_report"])]
    assert leaves
    for where in leaves:
        forged = copy.deepcopy(result)
        node = forged["data_gap_report"]
        *path, key = where.split(".")
        for step in path:
            node = node[int(step)] if step.isdigit() else node[step]
        node[key] = "nobody_declared_this"
        with pytest.raises(VerificationError):
            themis.verify_answer_claims(document, forged)


def test_an_undeclared_mediator_is_refused_where_an_undeclared_treatment_is():
    for document in (
        _effect_document(("x", "y"), [("x", "y")], mediator=_a("m")),
        _effect_document(("x", "m1", "y"), [("x", "m1"), ("m1", "y")],
                         mediators=[_a("m1"), _a("m2")]),
        _effect_document(("x", "y"), [("x", "y")],
                         extra_interventions=[
                             {"atom": _a("b"), "value": True}]),
    ):
        with pytest.raises(SemanticError) as raised:
            themis.run(document)
        assert raised.value.species is Malformed.QUERY_ATOM_NOT_IN_GRAPH
