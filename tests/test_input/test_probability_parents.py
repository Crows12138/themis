"""Regression tests for the ``probability_parents`` graph-level check.

A probability statement's ``given`` must be a subset of the target
atom's structural parents in G(M). Without this check, a probability
term like ``P(cancer | stress)`` in a graph where stress is NOT a
parent of cancer would silently feed Theta with a pseudo-CPT entry
that identification formulas cannot consume coherently.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.input.semantic_validator import (
    SemanticError,
    validate_against_graph,
)
from themis.runtime.graph_projection import project
from themis.runtime.instantiation import instantiate
from themis.types import (
    Atom,
    CauseStatement,
    ConstTerm,
    ProbabilityStatement,
    Program,
    ValuedAtom,
)


def atom(pred: str, obj: str = "alice") -> Atom:
    return Atom(predicate=pred, args=(ConstTerm(name=obj),))


# ------------------------------------------------------------ positive cases

def test_given_equals_parents_accepted():
    """P(y | x) with cause x->y — given={x} == parents(y)."""
    x, y = atom("x"), atom("y")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=y),
            ProbabilityStatement(
                target=ValuedAtom(atom=y, value=True),
                given=(ValuedAtom(atom=x, value=True),),
                value=0.3,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    # Does not raise.
    validate_against_graph(ground, graph)


def test_empty_given_on_rootless_target_accepted():
    """P(z) with z having no parents — given={} ⊆ parents(z)={}."""
    z = atom("z")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            ProbabilityStatement(
                target=ValuedAtom(atom=z, value=True),
                given=(),
                value=0.4,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    validate_against_graph(ground, graph)


def test_given_subset_of_parents_accepted():
    """P(y | x1) with parents(y) = {x1, x2} — marginal is allowed."""
    x1, x2, y = atom("x1"), atom("x2"), atom("y")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x1, to_atom=y),
            CauseStatement(from_atom=x2, to_atom=y),
            ProbabilityStatement(
                target=ValuedAtom(atom=y, value=True),
                given=(ValuedAtom(atom=x1, value=True),),
                value=0.3,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    validate_against_graph(ground, graph)


# ------------------------------------------------------------ negative cases

def test_non_parent_in_given_is_rejected():
    """P(y | z) when cause graph is x->y and z is unrelated."""
    x, y, z = atom("x"), atom("y"), atom("z")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=y),
            ProbabilityStatement(
                target=ValuedAtom(atom=y, value=True),
                given=(ValuedAtom(atom=z, value=True),),
                value=0.3,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    with pytest.raises(SemanticError, match=r"not structural parents"):
        validate_against_graph(ground, graph)


def test_descendant_in_given_is_rejected():
    """P(x | y) when cause graph is x->y. parents(x) = {}, y is a child."""
    x, y = atom("x"), atom("y")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=y),
            ProbabilityStatement(
                target=ValuedAtom(atom=x, value=True),
                given=(ValuedAtom(atom=y, value=True),),
                value=0.3,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    with pytest.raises(SemanticError, match=r"y.*not structural parents"):
        validate_against_graph(ground, graph)


# ------------------------------------------------------------------ dispatch

def test_dispatch_all_surfaces_probability_parents_violation():
    """End-to-end: dispatch_all must raise before building Theta if
    a program violates probability_parents."""
    from themis.runtime.scheduler import dispatch_all

    x, y, z = atom("x"), atom("y"), atom("z")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=y),
            ProbabilityStatement(
                target=ValuedAtom(atom=y, value=True),
                given=(ValuedAtom(atom=z, value=True),),
                value=0.3,
            ),
        ),
    )
    graph = project(instantiate(program))
    with pytest.raises(SemanticError):
        dispatch_all(program, graph)
