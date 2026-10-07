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

from enum import unique

import networkx as nx

from .. import language
from ..types import (
    Atom,
    BidirectedStatement,
    FeedbackLoop,
    CauseStatement,
    QueryStatement,
    Statement,
    VariableDeclaration,
    atoms_the_graph_is_asked_about,
)


@unique
class Closed(language.Word, vocabulary="graph_refusal",
             between=language.BETWEEN_STATEMENTS):
    """Why the cause statements handed in do not make a graph.

    Addressed to whoever wrote the program — a model, most often, which
    is handed this back with the program to mend. The sentence says what
    the language offers in place of the loop, because a model that drew
    both directions was told something the question did not settle, and
    the prompt's two statements for that are what it should have used.
    """

    THE_EDGES_CLOSE_A_LOOP = ("the_edges_close_a_loop", {
        "zh": "图里的因果边连成了 {count} 个环：{cycles}。因果图不能有环。两个变量"
              "互为因果时，只保留问题要问的那个方向的 cause 边，另一方向用 feedback "
              "语句声明那一对；如果其实是先后发生，用时间下标写成两个时刻之间的边",
        "en": "the cause edges close {count} loop(s): {cycles}. A causal graph "
              "has none. Where two variables cause each other, keep the cause "
              "edge the question asks about and declare the pair in a feedback "
              "statement; where one in fact comes before the other, write the "
              "edges between time slices",
    })


class CyclicGraphError(language.Voiced, ValueError):
    """Raised when the projected graph contains a directed cycle.

    A refusal of the program as written — the edges are the author's —
    so it carries its sentence the way the validators' refusals do, and
    the web hands it back to the model with the program. Attribute
    ``cycles`` lists the detected cycles (each as a tuple of Atom nodes).
    """

    def __init__(self, cycles: tuple[tuple[Atom, ...], ...]):
        super().__init__(Closed.THE_EDGES_CLOSE_A_LOOP, count=len(cycles),
                         cycles="; ".join(_format_cycle(c) for c in cycles))
        self.cycles = cycles


def _format_cycle(cycle: tuple[Atom, ...]) -> str:
    path = [atom_label(a) for a in cycle]
    return " -> ".join(path + [path[0]])


def atom_label(atom: Atom) -> str:
    """A ground atom as an envelope spells it: ``sleep(me)@t-1``.

    Defined once, beside the graph whose nodes it names, because what is
    written with it is read back against them: a supporting path is a run
    of these, and so are the instrument and the mediators a block names.
    Two spellings that drifted apart would match no node, and an atom that
    matches no node is one an answer silently stops resting on.
    """
    args = ",".join(t.name for t in atom.args)
    base = f"{atom.predicate}({args})"
    if atom.time_index is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def project(statements: tuple[Statement, ...]) -> nx.DiGraph:
    """Build a networkx.DiGraph from a ground statement list.

    Node attribute ``atom`` holds the original ``Atom`` dataclass.
    Edge attribute ``source`` points to the CauseStatement that
    produced it.

    Phase 4 relaxation (2026-04-25): atoms a question asks the graph
    about (:func:`themis.types.atoms_the_graph_is_asked_about`) OR that
    appear in bidirected statements but are not touched by any
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
        elif isinstance(stmt, (BidirectedStatement, FeedbackLoop)):
            # Bidirected atoms become isolated DAG nodes (the bidirected
            # structure itself lives in the ADMG layer, not in G(M)).
            #
            # A declared feedback loop is here for the same reason and adds
            # no edge either. It is not a claim ABOUT G(M) that G(M) could
            # hold — it is the claim that G(M) is missing an edge it cannot
            # have, which is why the loop travels beside the graph and why
            # what it does downstream is withdraw routes rather than open
            # one. Adding the reverse edge here would make every DAG
            # algorithm in the kernel wrong at once.
            referenced_atoms.append(stmt.left)
            referenced_atoms.append(stmt.right)
        elif isinstance(stmt, QueryStatement):
            referenced_atoms.extend(
                atoms_the_graph_is_asked_about(stmt.query))

    for atom in referenced_atoms:
        if atom in graph:
            continue
        if atom.predicate in declared_predicates:
            graph.add_node(atom, atom=atom)

    if not nx.is_directed_acyclic_graph(graph):
        raise CyclicGraphError(tuple(tuple(c) for c in nx.simple_cycles(graph)))
    return graph
