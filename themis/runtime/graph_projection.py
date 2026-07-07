"""Project ground cause statements into a networkx DiGraph G(M).

Each ground atom becomes a node; each ground ``cause(A, B)`` becomes
a directed edge A -> B.

Phase 5 §T / S.T.3 extends the node identity from just
``(predicate, args)`` to the full ``Atom`` value, which now includes an
optional ``time_index``. That means:

- ``sleep(me)@t-1`` and ``sleep(me)@t`` are distinct nodes
- an atemporal atom (no ``time_index``) is its own node, equivalent to
  the charter's "virtual atemporal index"
- DAG acyclicity is checked on this already-unrolled graph

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

from ..types import (
    AssocQuery,
    Atom,
    BidirectedStatement,
    CauseQuery,
    CauseStatement,
    CounterfactualQuery,
    EffectQuery,
    IdentifyQuery,
    QueryStatement,
    Statement,
    VariableDeclaration,
)


class CyclicGraphError(ValueError):
    """Raised when the projected graph contains a directed cycle.

    Attribute ``cycles`` lists the detected cycles (each as a tuple
    of Atom nodes) for easier debugging.
    """

    def __init__(self, message: str, cycles: tuple[tuple[Atom, ...], ...]):
        super().__init__(message)
        self.cycles = cycles


def _format_cycle(cycle: tuple[Atom, ...]) -> str:
    path = [_atom_label(a) for a in cycle]
    return " -> ".join(path + [path[0]])


def _atom_label(atom: Atom) -> str:
    args = ",".join(t.name for t in atom.args)
    base = f"{atom.predicate}({args})"
    if atom.time_index is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def _query_atoms(q) -> tuple[Atom, ...]:
    """Pull structural atoms from a query (mirrors semantic_validator)."""
    if isinstance(q, CauseQuery):
        return (q.from_atom, q.to_atom)
    if isinstance(q, AssocQuery):
        return (q.left, q.right, *q.given)
    if isinstance(q, IdentifyQuery):
        return (q.target, q.intervention.atom, *q.given)
    if isinstance(q, EffectQuery):
        return (
            q.target.atom,
            q.intervention.atom,
            *(iv.atom for iv in q.extra_interventions),
            *(g.atom for g in q.given),
        )
    if isinstance(q, CounterfactualQuery):
        return (
            q.observed.atom,
            q.counterfactual_intervention.atom,
            q.counterfactual_target.atom,
        )
    from ..types import CounterfactualConjunctionQuery, SCMCounterfactualQuery
    if isinstance(q, SCMCounterfactualQuery):
        return (q.intervention.atom, q.target)
    if isinstance(q, CounterfactualConjunctionQuery):
        return tuple(
            a
            for e in q.events
            for a in (e.variable, *(s.atom for s in e.subscript))
        )
    return ()


def project(statements: tuple[Statement, ...]) -> nx.DiGraph:
    """Build a networkx.DiGraph from a ground statement list.

    Node attribute ``atom`` holds the original ``Atom`` dataclass.
    Edge attribute ``source`` points to the CauseStatement that
    produced it.

    Phase 4 relaxation (2026-04-25): atoms that appear in query
    statements OR bidirected statements but are not touched by any
    cause edge are added as **isolated nodes** in the graph, IF
    their predicate has a ``VariableDeclaration``. This makes
    refusal-only narratives (e.g. selection-bias case where A2
    declined to draw the edge) answer correctly with
    ``cause = False (no path)`` instead of raising
    SemanticError.

    The "trace back to a source statement" invariant is preserved:
    each isolated node traces back to a VariableDeclaration plus a
    QueryStatement / BidirectedStatement that referenced it.

    Raises ``CyclicGraphError`` if the resulting graph is not acyclic.
    """
    graph: nx.DiGraph = nx.DiGraph()
    declared_predicates: set[str] = set()
    referenced_atoms: list[Atom] = []

    for stmt in statements:
        if isinstance(stmt, CauseStatement):
            graph.add_node(stmt.from_atom, atom=stmt.from_atom)
            graph.add_node(stmt.to_atom, atom=stmt.to_atom)
            graph.add_edge(stmt.from_atom, stmt.to_atom, source=stmt)
        elif isinstance(stmt, VariableDeclaration):
            declared_predicates.add(stmt.predicate)
        elif isinstance(stmt, BidirectedStatement):
            # Bidirected atoms become isolated DAG nodes (the bidirected
            # structure itself lives in the ADMG layer, not in G(M)).
            referenced_atoms.append(stmt.left)
            referenced_atoms.append(stmt.right)
        elif isinstance(stmt, QueryStatement):
            referenced_atoms.extend(_query_atoms(stmt.query))

    for atom in referenced_atoms:
        if atom in graph:
            continue
        if atom.predicate in declared_predicates:
            graph.add_node(atom, atom=atom)

    if not nx.is_directed_acyclic_graph(graph):
        cycles = tuple(tuple(c) for c in nx.simple_cycles(graph))
        rendered = "; ".join(_format_cycle(c) for c in cycles)
        raise CyclicGraphError(
            f"projected graph contains {len(cycles)} cycle(s): {rendered}",
            cycles,
        )
    return graph
