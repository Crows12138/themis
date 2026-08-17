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
    BidirectedStatement,
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


def test_a_bidirected_sibling_is_accepted():
    """P(Z2|X, Z1) where Z1 ↔ Z2 bidirected and X is parent of
    Z2. Z1 isn't structural parent but IS bidirected sibling →
    admissible. Tian's c-factor product needs this."""
    x, z1, z2 = atom("x"), atom("z1"), atom("z2")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=z1),
            CauseStatement(from_atom=x, to_atom=z2),
            BidirectedStatement(left=z1, right=z2),
            ProbabilityStatement(
                target=ValuedAtom(atom=z2, value=True),
                given=(
                    ValuedAtom(atom=x, value=True),
                    ValuedAtom(atom=z1, value=True),
                ),
                value=0.5,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    bidirected = frozenset({frozenset({z1, z2})})
    # Should NOT raise
    validate_against_graph(ground, graph, bidirected=bidirected)


def test_a_bidirected_sibling_is_accepted_either_way_round():
    """Bidirected is symmetric — P(Z1|X, Z2) must also be
    admissible (the c-factor topo can put Z2 first then Z1)."""
    x, z1, z2 = atom("x"), atom("z1"), atom("z2")
    program = Program(
        version="0.1",
        objects=("alice",),
        statements=(
            CauseStatement(from_atom=x, to_atom=z1),
            CauseStatement(from_atom=x, to_atom=z2),
            BidirectedStatement(left=z1, right=z2),
            ProbabilityStatement(
                target=ValuedAtom(atom=z1, value=True),
                given=(
                    ValuedAtom(atom=x, value=True),
                    ValuedAtom(atom=z2, value=True),
                ),
                value=0.5,
            ),
        ),
    )
    ground = instantiate(program)
    graph = project(ground)
    bidirected = frozenset({frozenset({z1, z2})})
    validate_against_graph(ground, graph, bidirected=bidirected)


def test_a_descendant_is_rejected_even_under_the_loosened_rule():
    """The loosening MUST still reject descendants in given. Test
    P(X|Y) where X → Y with NO bidirected — Y is descendant of X,
    not ancestor; admissible = parents(X) = {} → reject. The
    bidirected loosen shouldn't accidentally allow descendants."""
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
        validate_against_graph(ground, graph, bidirected=frozenset())


def test_the_rejection_message_includes_actionable_hints():
    """The rejection message lists three concrete fix paths
    (add cause statement, drop given atoms, or note the Tian/ADMG
    end-to-end gap from wall.md iter 150). Without these hints the
    user only knows what's wrong, not what to do about it."""
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
    with pytest.raises(SemanticError) as excinfo:
        validate_against_graph(ground, graph)
    msg = str(excinfo.value)
    # Three actionable hints must appear
    assert "add the missing 'cause' statement" in msg
    assert "drop" in msg and "marginalized CPT" in msg
    # The pointer, not just the number: a bare ordinal in a message the
    # user reads is a reference they cannot follow.
    assert "Tian" in msg and "wall.md iter 150" in msg


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
