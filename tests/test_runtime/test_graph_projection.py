"""Regression tests for graph projection DAG invariant and temporal node identity."""
from __future__ import annotations

import pytest

from themis.runtime.graph_projection import CyclicGraphError, project
from themis.types import Atom, CauseStatement, ConstTerm, RelativeTimeIndex


def _ground_atom(predicate: str, obj: str) -> Atom:
    return Atom(predicate=predicate, args=(ConstTerm(name=obj),))


def _timed_atom(predicate: str, obj: str, t: int) -> Atom:
    return Atom(
        predicate=predicate,
        args=(ConstTerm(name=obj),),
        time_index=RelativeTimeIndex(value=t),
    )


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


def test_project_treats_same_predicate_different_times_as_distinct_nodes() -> None:
    x_t_minus_1 = _timed_atom("x", "me", -1)
    x_t = _timed_atom("x", "me", 0)
    y_t_plus_1 = _timed_atom("y", "me", 1)
    stmts = (
        CauseStatement(from_atom=x_t_minus_1, to_atom=x_t),
        CauseStatement(from_atom=x_t, to_atom=y_t_plus_1),
    )
    g = project(stmts)
    assert g.number_of_nodes() == 3
    assert x_t_minus_1 in g and x_t in g and y_t_plus_1 in g
    assert g.has_edge(x_t_minus_1, x_t)
    assert g.has_edge(x_t, y_t_plus_1)


def test_project_keeps_atemporal_and_timed_atoms_distinct() -> None:
    sleep_atemporal = _ground_atom("sleep", "me")
    sleep_t = _timed_atom("sleep", "me", 0)
    tired_t_plus_1 = _timed_atom("tired", "me", 1)
    stmts = (
        CauseStatement(from_atom=sleep_atemporal, to_atom=tired_t_plus_1),
        CauseStatement(from_atom=sleep_t, to_atom=tired_t_plus_1),
    )
    g = project(stmts)
    assert sleep_atemporal in g
    assert sleep_t in g
    assert sleep_atemporal != sleep_t
    assert g.number_of_nodes() == 3


def test_project_cycle_error_renders_time_indices() -> None:
    x_t = _timed_atom("x", "me", 0)
    y_t_plus_1 = _timed_atom("y", "me", 1)
    stmts = (
        CauseStatement(from_atom=x_t, to_atom=y_t_plus_1),
        CauseStatement(from_atom=y_t_plus_1, to_atom=x_t),
    )
    with pytest.raises(CyclicGraphError) as exc:
        project(stmts)
    msg = str(exc.value)
    assert "x(me)@t" in msg
    assert "y(me)@t+1" in msg
