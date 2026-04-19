"""Project ground cause statements into a networkx DiGraph G(M).

Each ground atom becomes a node; each ground ``cause(A, B)`` becomes
a directed edge A -> B.

The resulting graph is the working surface on which d-separation,
back-door search, and identification operate.

The projection must be faithful: every node and edge in G(M) traces
back to exactly one source statement in the program.

Additionally the theory mandates that the compiled graph is a DAG.
Cyclic inputs are rejected at the end of ``project``; otherwise
``structural_solver.has_directed_path`` would happily report causal
influence in both directions and diverge from the semantics.
"""
from __future__ import annotations

import networkx as nx

from ..types import Atom, CauseStatement, Statement


class CyclicGraphError(ValueError):
    """Raised when the projected graph contains a directed cycle.

    Attribute ``cycles`` lists the detected cycles (each as a tuple
    of Atom nodes) for easier debugging.
    """

    def __init__(self, message: str, cycles: tuple[tuple[Atom, ...], ...]):
        super().__init__(message)
        self.cycles = cycles


def _format_cycle(cycle: tuple[Atom, ...]) -> str:
    path = [f"{a.predicate}({','.join(t.name for t in a.args)})" for a in cycle]
    return " -> ".join(path + [path[0]])


def project(statements: tuple[Statement, ...]) -> nx.DiGraph:
    """Build a networkx.DiGraph from a ground statement list.

    Node attribute ``atom`` holds the original ``Atom`` dataclass.
    Edge attribute ``source`` points to the CauseStatement that
    produced it.

    Raises ``CyclicGraphError`` if the resulting graph is not acyclic.
    """
    graph: nx.DiGraph = nx.DiGraph()
    for stmt in statements:
        if not isinstance(stmt, CauseStatement):
            continue
        graph.add_node(stmt.from_atom, atom=stmt.from_atom)
        graph.add_node(stmt.to_atom, atom=stmt.to_atom)
        graph.add_edge(stmt.from_atom, stmt.to_atom, source=stmt)

    if not nx.is_directed_acyclic_graph(graph):
        cycles = tuple(tuple(c) for c in nx.simple_cycles(graph))
        rendered = "; ".join(_format_cycle(c) for c in cycles)
        raise CyclicGraphError(
            f"projected graph contains {len(cycles)} cycle(s): {rendered}",
            cycles,
        )
    return graph
