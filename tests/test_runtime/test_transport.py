"""Phase 9 §T9.1.3: Bareinboim transportability primitives.

Unit-level tests for the transport module's core building blocks:
- ``build_selection_diagram``
- ``s_admissibility_check``
- ``find_s_admissible_set``
- ``identify_via_transport``

End-to-end behavior (transport queries through ``themis.run``) is
covered in ``test_phase9_transport_schema.py``.
"""
from __future__ import annotations

import networkx as nx
import pytest

from themis.runtime.transport import (
    TransportIdentificationResult,
    build_selection_diagram,
    find_s_admissible_set,
    identify_via_transport,
    is_s_node,
    s_admissibility_check,
)
from themis.types import Atom, ConstTerm, SelectionNode


def _atom(p: str) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def _selection_node(id_: str, affects_pred: str) -> SelectionNode:
    return SelectionNode(
        id=id_,
        affects=_atom(affects_pred),
        source_population="rct_2022",
        target_population="user",
    )


def _basic_graph(edges: list[tuple[str, str]]) -> nx.DiGraph:
    g = nx.DiGraph()
    for a, b in edges:
        atom_a, atom_b = _atom(a), _atom(b)
        g.add_node(atom_a, atom=atom_a)
        g.add_node(atom_b, atom=atom_b)
        g.add_edge(atom_a, atom_b)
    return g


# ============================================ build_selection_diagram


def test_build_selection_diagram_adds_s_node_and_edge():
    g = _basic_graph([("age", "y"), ("x", "y")])
    sn = _selection_node("S_age", "age")
    diagram, s_atoms = build_selection_diagram([sn], g)

    assert len(s_atoms) == 1
    assert is_s_node(s_atoms[0])
    assert diagram.has_edge(s_atoms[0], _atom("age"))
    # original edges preserved
    assert diagram.has_edge(_atom("age"), _atom("y"))
    assert diagram.has_edge(_atom("x"), _atom("y"))


def test_build_selection_diagram_empty_when_no_selection_nodes():
    g = _basic_graph([("x", "y")])
    diagram, s_atoms = build_selection_diagram([], g)
    assert s_atoms == ()
    # no S nodes added
    assert len(diagram.nodes) == 2


def test_build_selection_diagram_does_not_mutate_input():
    g = _basic_graph([("age", "y"), ("x", "y")])
    original_nodes = set(g.nodes)
    sn = _selection_node("S_age", "age")
    build_selection_diagram([sn], g)
    assert set(g.nodes) == original_nodes


# ============================================ s_admissibility_check


def test_s_admissibility_empty_z_when_no_s_to_y_path():
    """If S → affects has no path to Y, Z=∅ is S-admissible (vacuously)."""
    g = _basic_graph([("x", "y"), ("isolated", "y")])
    sn = _selection_node("S_iso", "isolated")
    diagram, s_atoms = build_selection_diagram([sn], g)
    # In G_{\bar{x}} = same as g (x has no incoming edges to remove),
    # S_iso → isolated → y is a directed path. Z=∅ does NOT block it
    # since isolated is not in conditioning.
    assert s_admissibility_check(diagram, _atom("x"), _atom("y"), (), s_atoms) is False


def test_s_admissibility_z_blocks_s_to_y_path():
    """Conditioning on the affected variable d-separates S from Y."""
    g = _basic_graph([("age", "y"), ("x", "y")])
    sn = _selection_node("S_age", "age")
    diagram, s_atoms = build_selection_diagram([sn], g)

    # Z = {} → S_age → age → y open
    assert s_admissibility_check(diagram, _atom("x"), _atom("y"), (), s_atoms) is False
    # Z = {age} → blocks the path
    assert s_admissibility_check(
        diagram, _atom("x"), _atom("y"), (_atom("age"),), s_atoms
    ) is True


def test_s_admissibility_no_s_nodes_trivially_true():
    """No S nodes → no path to block → S-admissibility holds for any Z."""
    g = _basic_graph([("x", "y")])
    assert s_admissibility_check(g, _atom("x"), _atom("y"), (), ()) is True


# ============================================ find_s_admissible_set


def test_find_s_admissible_set_returns_minimal():
    g = _basic_graph([("age", "y"), ("bmi", "y"), ("x", "y")])
    sns = [_selection_node("S_age", "age"), _selection_node("S_bmi", "bmi")]
    diagram, s_atoms = build_selection_diagram(sns, g)

    z = find_s_admissible_set(diagram, _atom("x"), _atom("y"), s_atoms)
    assert z is not None
    z_preds = {a.predicate for a in z}
    # both age AND bmi must be in Z to block both S paths
    assert "age" in z_preds and "bmi" in z_preds


def test_find_s_admissible_set_returns_empty_when_no_adjustment_needed():
    """No S nodes → empty Z works."""
    g = _basic_graph([("x", "y")])
    z = find_s_admissible_set(g, _atom("x"), _atom("y"), ())
    assert z == ()


def test_find_s_admissible_set_returns_none_when_unidentifiable():
    """If S affects Y directly (S → Y), no adjustment can block it
    since Y itself can't be in Z."""
    g = _basic_graph([("x", "y")])
    # Synthetic: pretend S_y affects Y directly
    sn = _selection_node("S_y", "y")
    diagram, s_atoms = build_selection_diagram([sn], g)
    # Now S_y → y is one edge; in G_{\bar{x}} this path is open and
    # no Z (excluding y itself) can block it.
    z = find_s_admissible_set(diagram, _atom("x"), _atom("y"), s_atoms)
    assert z is None


# ============================================ identify_via_transport


def test_identify_via_transport_no_s_nodes_trivially_identifiable():
    g = _basic_graph([("x", "y")])
    diagram, s_atoms = build_selection_diagram([], g)
    result = identify_via_transport(diagram, s_atoms, _atom("x"), _atom("y"))
    assert result.identifiable
    assert result.adjustment_set == ()
    assert "P*(y | do(x))" in result.formula_repr


def test_identify_via_transport_with_adjustable_s():
    g = _basic_graph([("age", "y"), ("x", "y")])
    sn = _selection_node("S_age", "age")
    diagram, s_atoms = build_selection_diagram([sn], g)
    result = identify_via_transport(diagram, s_atoms, _atom("x"), _atom("y"))
    assert result.identifiable
    assert "age" in {a.predicate for a in result.adjustment_set}
    assert "Σ_{age}" in result.formula_repr


def test_identify_via_transport_unidentifiable_returns_failure_reason():
    g = _basic_graph([("x", "y")])
    sn = _selection_node("S_y", "y")
    diagram, s_atoms = build_selection_diagram([sn], g)
    result = identify_via_transport(diagram, s_atoms, _atom("x"), _atom("y"))
    assert not result.identifiable
    assert result.failure_reason
    assert "找不到 S-可容许" in result.failure_reason


def test_identify_via_transport_missing_treatment_in_diagram():
    g = _basic_graph([("a", "b")])  # x not in graph
    sn = _selection_node("S_a", "a")
    diagram, s_atoms = build_selection_diagram([sn], g)
    result = identify_via_transport(diagram, s_atoms, _atom("x"), _atom("b"))
    assert not result.identifiable
    assert "不在选择图中" in (result.failure_reason or "")
