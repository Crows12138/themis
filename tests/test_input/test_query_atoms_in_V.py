"""Regression tests for the ``query_atoms_in_V`` graph-level check.

Structural queries (cause / assoc / identify / effect) must only
reference atoms that are nodes in the instantiated working graph.
Probability queries are intentionally exempt — they are distributional
lookups backed by Theta, not by the causal DAG.
"""
from __future__ import annotations

import pytest

from themis.input.semantic_validator import (
    SemanticError,
    validate_against_graph,
)
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.types import (
    AssocQuery,
    Atom,
    CauseQuery,
    CauseStatement,
    ConstTerm,
    EffectQuery,
    IdentifyQuery,
    Intervention,
    ProbabilityQuery,
    ProbabilityStatement,
    Program,
    QueryStatement,
    ValuedAtom,
)


def atom(pred: str, obj: str = "alice") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


def _program(statements):
    return Program(version="0.1", objects=("alice",), statements=tuple(statements))


def _ground_and_graph(program):
    ground = instantiate(program)
    return ground, project(ground)


# --------------------------------------------------------------- cause/assoc

def test_cause_query_with_unknown_atom_is_rejected():
    x, y, z = atom("x"), atom("y"), atom("z")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        QueryStatement(id="q", query=CauseQuery(from_atom=x, to_atom=z)),
    ])
    ground, graph = _ground_and_graph(prog)
    with pytest.raises(SemanticError, match=r"'z'.*not in the instantiated"):
        validate_against_graph(ground, graph)


def test_assoc_query_with_unknown_conditioning_atom_is_rejected():
    x, y, w = atom("x"), atom("y"), atom("w")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        QueryStatement(
            id="q",
            query=AssocQuery(left=x, right=y, given=(w,)),
        ),
    ])
    ground, graph = _ground_and_graph(prog)
    with pytest.raises(SemanticError, match=r"'w'"):
        validate_against_graph(ground, graph)


# ----------------------------------------------------------- identify/effect

def test_identify_query_with_unknown_intervention_atom_is_rejected():
    x, y, w = atom("x"), atom("y"), atom("w")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        QueryStatement(
            id="q",
            query=IdentifyQuery(
                target=y,
                intervention=Intervention(atom=w, value=True),
                given=(),
            ),
        ),
    ])
    ground, graph = _ground_and_graph(prog)
    with pytest.raises(SemanticError, match=r"'w'"):
        validate_against_graph(ground, graph)


def test_effect_query_with_unknown_target_is_rejected():
    x, y, w = atom("x"), atom("y"), atom("w")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        QueryStatement(
            id="q",
            query=EffectQuery(
                target=ValuedAtom(atom=w, value=True),
                intervention=Intervention(atom=x, value=False),
                given=(),
            ),
        ),
    ])
    ground, graph = _ground_and_graph(prog)
    with pytest.raises(SemanticError, match=r"'w'"):
        validate_against_graph(ground, graph)


# -------------------------------------------------- probability exemption

def test_probability_query_with_atom_outside_DAG_is_accepted():
    """A pure probability query may reference atoms that live only
    in Theta and were never declared via a cause statement."""
    coin = atom("coin", obj="a")
    prog = Program(
        version="0.1",
        objects=("a",),
        statements=(
            ProbabilityStatement(
                target=ValuedAtom(atom=coin, value=True),
                given=(),
                value=0.7,
            ),
            QueryStatement(
                id="q",
                query=ProbabilityQuery(
                    target=ValuedAtom(atom=coin, value=True),
                    given=(),
                ),
            ),
        ),
    )
    ground, graph = _ground_and_graph(prog)
    # No cause statements -> coin is not in G(M). The check must NOT
    # complain, because probability queries are distributional.
    validate_against_graph(ground, graph)


# ------------------------------------------------------------- dispatch_all

def test_dispatch_all_fails_fast_on_unknown_query_atom():
    """dispatch_all should raise SemanticError from the graph-level
    validator instead of letting cause / assoc silently return False."""
    from themis.runtime.scheduler import dispatch_all

    x, y, z = atom("x"), atom("y"), atom("z")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        QueryStatement(id="q", query=CauseQuery(from_atom=x, to_atom=z)),
    ])
    graph = project(instantiate(prog))
    with pytest.raises(SemanticError):
        dispatch_all(prog, graph)


# ---------------------------------------------- Phase 4 V-set relaxation

def test_query_atom_with_variable_declaration_admitted_as_isolated_node():
    """Phase 4 (2026-04-25) relaxation: when a query references atoms
    whose predicate has a VariableDeclaration but no cause edge touches
    the atom, the atom is admitted to G(M) as an isolated node and the
    cause query answers ``False`` (no directed path) — instead of the
    pre-relaxation SemanticError.

    Rationale: refusal-only narratives (selection bias, etc.) explicitly
    declare variables and ask "does X cause Y?" while declining to draw
    an edge. The right answer is "no causal path", not "your program is
    broken"."""
    from themis.types import VariableDeclaration

    x, y = atom("x"), atom("y")
    prog = _program([
        VariableDeclaration(predicate="x", domain=(True, False)),
        VariableDeclaration(predicate="y", domain=(True, False)),
        QueryStatement(id="q", query=CauseQuery(from_atom=x, to_atom=y)),
    ])
    ground, graph = _ground_and_graph(prog)
    # No SemanticError — both atoms admitted as isolated nodes
    validate_against_graph(ground, graph)
    assert x in graph and y in graph
    # No edge between them — cause query will answer False downstream


def test_query_atom_without_variable_declaration_still_rejected():
    """The relaxation is keyed on a VariableDeclaration being present.
    Bare query atoms with no declaration AND no cause edge still fail
    the V-set check (catches typos / missing setup)."""
    x, y, z = atom("x"), atom("y"), atom("z")
    prog = _program([
        CauseStatement(from_atom=x, to_atom=y),
        # z has no VariableDeclaration AND no cause edge — still rejected
        QueryStatement(id="q", query=CauseQuery(from_atom=x, to_atom=z)),
    ])
    ground, graph = _ground_and_graph(prog)
    with pytest.raises(SemanticError, match=r"'z'.*not in the instantiated"):
        validate_against_graph(ground, graph)
