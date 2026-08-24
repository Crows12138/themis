"""Phase 9 §T9.1: Bareinboim-Pearl transportability across source domains.

Implements the structural identification side of cross-population
causal effect transport, per Bareinboim & Pearl 2014 "A General
Algorithm for Deciding Transportability of Experimental Results".

A selection diagram belongs to ONE source domain: it is the target's
graph plus the S nodes saying where THAT source differs from the target.
Several sources are several diagrams over one shared G, and each has its
own S set, its own admissible adjustment, and its own answer. This module
therefore builds a diagram PER declared ``source_population``; the
familiar single-source case is the one where that grouping has one
member, not a different code path.

That is the whole of what changed at #326, and it was a representation
fact rather than a missing feature: ``source_population`` is a field of
each selection node, and reading it off the FIRST node made every other
node's domain unsayable. A two-source program then answered exactly what
a one-source program answered — same formula, same source tag, same
missing parameter — with the second source discarded in silence.

- ``build_selection_diagrams``: one :class:`SourceDiagram` per declared
  source population, in first-declared order
- ``s_admissibility_check``: given one diagram, treatment X, outcome Y
  and candidate adjustment Z, return True iff the diagram's S nodes are
  d-separated from Y given Z in D_{\\bar{X}} (X's incoming edges removed)
- ``find_s_admissible_set``: the smallest S-admissible Z in one diagram,
  or None if the size budget holds none
- ``identify_from_source``: one domain's verdict — transportable with
  which Z, or blocked by which of ``TRANSPORT_BLOCKED_KINDS``
- ``identify_across_sources``: every domain's verdict. The effect
  transports iff SOME domain's does; when more than one does, they are
  separate estimands of the same target quantity, which is a testable
  restriction rather than a menu.

Scope, declared. The criterion is the adjustment-based sufficient
condition (Bareinboim & Pearl 2014 Theorem 1) — the same one the
single-source path has always used, now asked once per domain. What that
does NOT cover is COMPOSING a target estimand out of pieces licensed by
different domains (mz-transportability, Bareinboim & Pearl 2014,
"Transportability from Multiple Environments with Limited Experiments").
That is not a multi-source catch-up on this criterion: it is an ID-style
recursion, and its single-source form is absent here too. So a target
that no single declared source transports is reported as such, naming
each domain's own reason, rather than guessed at.

Also out of scope: latent S nodes (S pointing at unobserved variables),
counterfactual transport (Bareinboim & Pearl 2013).

Selection diagrams are built fresh per transport query — the working
graph G(M) that other dispatch paths use is never mutated.
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Iterable

import networkx as nx

from ..types import Atom, SelectionNode, Statement


# =========================================================== diagram


# Sentinel atom used internally to represent S nodes inside the
# selection diagram. The ``predicate`` collides with no real predicate
# (forbidden by atom schema's identifier pattern). The ``args[0].name``
# carries the SelectionNode id for traceability in derivation.
_S_PREDICATE_PREFIX = "__S__"

#: Why one source domain cannot carry the effect. Two members, and a
#: closed vocabulary rather than a sentence because the two differ in
#: what a reader does next: a treatment off the diagram is a program
#: that does not say what it means, and no admissible set is a claim
#: about the mechanisms that domain was declared to differ in.
TRANSPORT_BLOCKED_KINDS = ("treatment_or_outcome_off_diagram",
                           "no_s_admissible_set")


def _s_node_atom(s_node: SelectionNode) -> Atom:
    from ..types import ConstTerm
    return Atom(
        predicate=f"{_S_PREDICATE_PREFIX}{s_node.id}",
        args=(ConstTerm(name=s_node.id),),
    )


def is_s_node(atom: Atom) -> bool:
    return atom.predicate.startswith(_S_PREDICATE_PREFIX)


@dataclass(frozen=True)
class SourceDiagram:
    """One source domain and the diagram that says how it differs.

    ``diagram`` is G(M) plus this domain's own S nodes — never another
    domain's. Two domains that both shift the same variable each get
    their own S node in their own diagram, because "Z differs between
    the target and THIS source" is a claim about a pair of populations
    and says nothing about a third.
    """

    source_population: str
    diagram: nx.DiGraph
    s_atoms: tuple[Atom, ...]
    #: The declaring statements' ids, in the order they were declared —
    #: what a reader is pointed at when this domain is the one that works.
    s_node_ids: tuple[str, ...]


def build_selection_diagrams(
    ground_statements: Iterable[Statement],
    base_graph: nx.DiGraph,
) -> tuple[SourceDiagram, ...]:
    """One diagram per declared source population, first-declared first.

    Returns an empty tuple when no selection node is declared, which is
    also when there is no population boundary to cross. ``base_graph`` is
    not mutated.
    """
    by_source: dict[str, list[SelectionNode]] = {}
    for stmt in ground_statements:
        if isinstance(stmt, SelectionNode):
            by_source.setdefault(stmt.source_population, []).append(stmt)

    built: list[SourceDiagram] = []
    for source, nodes in by_source.items():
        diagram = base_graph.copy()
        s_atoms: list[Atom] = []
        for node in nodes:
            s_atom = _s_node_atom(node)
            s_atoms.append(s_atom)
            diagram.add_node(s_atom, atom=s_atom, kind="selection_node")
            # The S node itself doesn't need to be in V (it's never
            # queried); the affects atom must be in V (it's a regular
            # variable). If affects is missing from base_graph, fall
            # through — d-sep on a missing endpoint just returns False.
            if node.affects in diagram:
                diagram.add_edge(s_atom, node.affects, source=node)
        built.append(SourceDiagram(
            source_population=source,
            diagram=diagram,
            s_atoms=tuple(s_atoms),
            s_node_ids=tuple(n.id for n in nodes),
        ))
    return tuple(built)


def _mutilate_incoming(graph: nx.DiGraph, node: Atom) -> nx.DiGraph:
    """G_{\\overline{X}}: remove all edges pointing INTO ``node``.

    This is Pearl 2009's overbar mutilation, the intervention graph
    used by Bareinboim 2014 Theorem 1 for transport identification."""
    g = graph.copy()
    g.remove_edges_from(list(g.in_edges(node)))
    return g


# =========================================================== check


@dataclass(frozen=True)
class TransportIdentificationResult:
    """What ONE source domain can do for this query.

    ``source_population`` is None only in the no-selection-node case,
    where the two populations are not declared to differ at all and the
    transport formula is the identity.
    """
    identifiable: bool
    adjustment_set: tuple[Atom, ...]   # the Z that satisfies S-admissibility
    s_atoms: tuple[Atom, ...]          # this domain's S nodes
    formula_repr: str                  # symbolic transport formula
    source_population: str | None = None
    s_node_ids: tuple[str, ...] = ()
    #: A member of :data:`TRANSPORT_BLOCKED_KINDS`, present exactly when
    #: ``identifiable`` is False. The sentence is made where the reader's
    #: language is known; what travels is which of the two happened.
    blocked_by: str | None = None


def s_admissibility_check(
    diagram: nx.DiGraph,
    x: Atom,
    y: Atom,
    z: tuple[Atom, ...],
    s_atoms: tuple[Atom, ...],
) -> bool:
    """Bareinboim 2014 sufficient condition (Theorem 1, simplified):

    Z is S-admissible iff every S node is d-separated from Y given Z
    in D_{\\overline{X}} (the intervention graph).

    Z must consist of observed (non-S) atoms; this function does not
    enforce that — it's the caller's job to pass a valid candidate Z.
    """
    if x not in diagram or y not in diagram:
        return False
    g_bar_x = _mutilate_incoming(diagram, x)

    # Lazy import to avoid circular dep at module load time.
    from .structural_solver import is_d_connected

    for s in s_atoms:
        if s not in g_bar_x:
            # S node didn't reach the diagram (affects atom missing) —
            # vacuously d-separated, but really a structural error
            # caller should catch upstream. Treat as separated.
            continue
        # d-connected = path open ⇒ NOT d-separated. We want all S to
        # be d-separated from Y.
        if is_d_connected(g_bar_x, s, y, z):
            return False
    return True


def _pretreatment_observed_atoms(
    diagram: nx.DiGraph, x: Atom, s_atoms: tuple[Atom, ...]
) -> tuple[Atom, ...]:
    """Atoms eligible for inclusion in Z.

    "Pretreatment" = not a descendant of X (per Bareinboim 2014).
    "Observed" = not an S node and not the treatment / outcome itself.
    """
    if x not in diagram:
        return ()
    descendants_of_x = nx.descendants(diagram, x)
    s_set = frozenset(s_atoms)
    candidates = [
        n for n in diagram.nodes
        if n != x
        and n not in descendants_of_x
        and n not in s_set
    ]
    return tuple(candidates)


def find_s_admissible_set(
    diagram: nx.DiGraph,
    x: Atom,
    y: Atom,
    s_atoms: tuple[Atom, ...],
    max_size: int = 5,
) -> tuple[Atom, ...] | None:
    """Search for the smallest S-admissible Z, up to ``max_size`` atoms.

    Returns the empty tuple if Z=∅ already satisfies S-admissibility
    (no transport adjustment needed). Returns None if no Z within the
    size budget works.
    """
    candidates = _pretreatment_observed_atoms(diagram, x, s_atoms)
    # Try empty set first — the cheapest case.
    if s_admissibility_check(diagram, x, y, (), s_atoms):
        return ()
    for size in range(1, min(len(candidates), max_size) + 1):
        for subset in combinations(candidates, size):
            if s_admissibility_check(diagram, x, y, subset, s_atoms):
                return subset
    return None


# =========================================================== orchestrator


def transport_formula_repr(
    target: Atom,
    intervention: Atom,
    z: tuple[Atom, ...],
) -> str:
    """Render the Bareinboim transport formula symbolically.

    P*(y | do(x)) = Σ_z P(y | do(x), z) · P*(z)
    """
    y = target.predicate
    x = intervention.predicate
    if not z:
        return f"P*({y} | do({x})) = P({y} | do({x}))"
    z_names = ", ".join(a.predicate for a in z)
    return (
        f"P*({y} | do({x})) = "
        f"Σ_{{{z_names}}} P({y} | do({x}), {z_names}) · P*({z_names})"
    )


#: The no-boundary case: nothing was declared to differ, so the target
#: effect IS the source effect and the formula reduces to the identity.
#: Written once and returned as the single route, because "there are no
#: source domains" is the n=0 case of the grouping rather than a state
#: some other branch has to remember to handle.
def _no_boundary_route(
    treatment: Atom, outcome: Atom,
) -> TransportIdentificationResult:
    return TransportIdentificationResult(
        identifiable=True,
        adjustment_set=(),
        s_atoms=(),
        formula_repr=transport_formula_repr(outcome, treatment, ()),
        source_population=None,
        s_node_ids=(),
        blocked_by=None,
    )


def identify_from_source(
    source: SourceDiagram,
    treatment: Atom,
    outcome: Atom,
) -> TransportIdentificationResult:
    """Run Bareinboim Theorem 1 on ONE source domain's diagram.

    Check ``.identifiable`` before reading ``.adjustment_set`` /
    ``.formula_repr``; ``.blocked_by`` says which way it failed.
    """
    if treatment not in source.diagram or outcome not in source.diagram:
        return TransportIdentificationResult(
            identifiable=False,
            adjustment_set=(),
            s_atoms=source.s_atoms,
            formula_repr="",
            source_population=source.source_population,
            s_node_ids=source.s_node_ids,
            blocked_by="treatment_or_outcome_off_diagram",
        )

    z = find_s_admissible_set(
        source.diagram, treatment, outcome, source.s_atoms)
    if z is None:
        return TransportIdentificationResult(
            identifiable=False,
            adjustment_set=(),
            s_atoms=source.s_atoms,
            formula_repr="",
            source_population=source.source_population,
            s_node_ids=source.s_node_ids,
            blocked_by="no_s_admissible_set",
        )

    return TransportIdentificationResult(
        identifiable=True,
        adjustment_set=z,
        s_atoms=source.s_atoms,
        formula_repr=transport_formula_repr(outcome, treatment, z),
        source_population=source.source_population,
        s_node_ids=source.s_node_ids,
        blocked_by=None,
    )


def identify_across_sources(
    sources: tuple[SourceDiagram, ...],
    treatment: Atom,
    outcome: Atom,
) -> tuple[TransportIdentificationResult, ...]:
    """Every declared source domain's verdict, in declared order.

    The effect transports iff some route comes back identifiable. More
    than one is not an embarrassment of riches to be resolved by picking:
    each is an estimand of the SAME target quantity under a DIFFERENT
    selection diagram, so agreeing is a restriction the data can refute
    and disagreeing says at least one of the declared diagrams is wrong.
    Which is why every route is returned rather than the first that works.
    """
    if not sources:
        return (_no_boundary_route(treatment, outcome),)
    return tuple(
        identify_from_source(source, treatment, outcome)
        for source in sources
    )
