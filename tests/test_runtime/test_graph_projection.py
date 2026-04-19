"""Regression tests for graph projection DAG invariant."""
from __future__ import annotations

import pytest

from causal_kernel.runtime.graph_projection import CyclicGraphError, project
from causal_kernel.types import Atom, CauseStatement, ConstTerm


def _ground_atom(predicate: str, obj: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name=obj),))


def test_project_rejects_direct_two_cycle() -> None:
    a = _ground_atom("a", "x")
    b = _ground_atom("b", "x")
    stmts = (
        CauseStatement(from_atom=a, to_atom=b),
        CauseStatement(from_atom=b, to_atom=a),
    )
    with pytest.raises(CyclicGraphError) as exc:
        project(stmts)
    assert len(exc.value.cycles) == 1
    assert "a(x)" in str(exc.value)


def test_project_rejects_three_cycle() -> None:
    a = _ground_atom("a", "x")
    b = _ground_atom("b", "x")
    c = _ground_atom("c", "x")
    stmts = (
        CauseStatement(from_atom=a, to_atom=b),
        CauseStatement(from_atom=b, to_atom=c),
        CauseStatement(from_atom=c, to_atom=a),
    )
    with pytest.raises(CyclicGraphError):
        project(stmts)


def test_project_accepts_acyclic_graph() -> None:
    a = _ground_atom("a", "x")
    b = _ground_atom("b", "x")
    c = _ground_atom("c", "x")
    stmts = (
        CauseStatement(from_atom=a, to_atom=b),
        CauseStatement(from_atom=b, to_atom=c),
    )
    g = project(stmts)
    assert g.number_of_edges() == 2
