"""Shpitser-Pearl (2007) general counterfactual identification — make-cg.

Phase 16 §CTF. The kernel already identifies *interventional* point
queries ``P(Y | do(X))`` via the complete Shpitser-Pearl ID/IDC engine
(``c_factor.py``). This module builds the piece one rung up the causal
hierarchy: the **counterfactual graph**, the structural object on which
the ID* / IDC* algorithms (Shpitser & Pearl, *Complete Identification
Methods for the Causal Hierarchy*, JMLR 9:1941-1979, 2008; tech report
R-336) decide identifiability of an arbitrary counterfactual conjunction

    γ = y¹_{x¹} ∧ … ∧ yᵏ_{xᵏ}

spanning multiple, possibly contradictory, hypothetical worlds.

``make_cg`` is the heart of that procedure (R-336 Fig. 10, Lemmas 24-25).
It is deliberately a self-contained primitive: it takes ``γ`` and a
causal diagram and returns the counterfactual graph with duplicate nodes
merged (or ``INCONSISTENT`` when ``γ`` asserts contradictory values on
nodes that provably denote the same random variable, so ``P(γ)=0``). No
scheduler / ID* wiring lands here yet — ID*/IDC* consume this next.

Node-merging (Lemma 24) is the crux: two counterfactual variables
``α``, ``β`` that share a functional mechanism and the same exogenous
parents ``U`` are the *same* random variable when every directed parent
is **either shared (already merged) or attains the same value** (fixed by
intervention or fixed by observation in ``γ``). The merge is applied in
topological order so a parent's status is settled before its children
are compared. The value clash that signals ``INCONSISTENT`` is a merge
whose two sides carry different observed values.

The resulting counterfactual graph is *not* unique — Lemma 25 makes an
arbitrary choice of representative when it collapses a group — but the
merge PARTITION, the surviving c-components, and the values on ``γ'`` are
invariant, and the tests pin those invariants (they must not depend on
which representative atom a group elects).
"""
from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import networkx as nx

from ..types import Atom, AtomValue
from .structural_solver import BidirectedEdgeSet, c_components


# A world / submodel is identified by its intervention set: a frozenset of
# (intervened atom, value) assignments. The empty set is the factual world.
World = frozenset  # frozenset[tuple[Atom, AtomValue]]


@dataclass(frozen=True)
class CtfEvent:
    """One counterfactual event ``variable_{subscript} = value``.

    ``variable`` is the base (non-counterfactual) atom ``V``. ``subscript``
    is the world in which ``V`` is read — a frozenset of ``(atom, value)``
    intervention assignments (empty = factual). ``value`` is the value
    ``V`` attains in that world.

    Example: ``Y_x = y`` is ``CtfEvent(Y, frozenset({(X, x)}), y)``;
    the plain observation ``x'`` is ``CtfEvent(X, frozenset(), x')``.
    """

    variable: Atom
    subscript: World
    value: AtomValue


Conjunction = tuple  # tuple[CtfEvent, ...]


# ---------------------------------------------------------------------------
# Shpitser-Pearl operators on counterfactual events (R-336 p.21)
# ---------------------------------------------------------------------------

def sub(gamma: Conjunction) -> frozenset[Atom]:
    """The set of subscript *variables* across all events (R-336: ``sub``)."""
    return frozenset(a for ev in gamma for (a, _v) in ev.subscript)


def var(gamma: Conjunction) -> frozenset[Atom]:
    """The set of (non-counterfactual) variables in ``γ`` (R-336: ``var``)."""
    return frozenset(ev.variable for ev in gamma)


def ev(gamma: Conjunction) -> frozenset[AtomValue]:
    """The set of values, subscript-fixed or observed (R-336: ``ev``)."""
    out: set[AtomValue] = set()
    for e in gamma:
        out.add(e.value)
        out.update(v for (_a, v) in e.subscript)
    return frozenset(out)


# ---------------------------------------------------------------------------
# Parallel-world nodes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PWNode:
    """One base variable read in one world of the parallel-worlds graph."""

    variable: Atom
    world: World


def _intervened(world: World) -> frozenset[Atom]:
    return frozenset(a for (a, _v) in world)


def _world_value(world: World, atom: Atom) -> AtomValue | None:
    for (a, v) in world:
        if a == atom:
            return v
    return None


def _is_fixed(node: PWNode) -> bool:
    """A node is *fixed* when its own variable is intervened in its world —
    it takes the intervention value and has no incoming mechanism."""
    return node.variable in _intervened(node.world)


class _Inconsistent:
    """Sentinel: ``γ`` is self-contradictory, so ``P(γ) = 0``."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "INCONSISTENT"


INCONSISTENT = _Inconsistent()


@dataclass(frozen=True)
class CfGraph:
    """A counterfactual graph produced by ``make_cg``.

    - ``graph`` / ``bidirected`` — the merged ADMG over ``PWNode``
      representatives (directed edges are within-world, mutilated by
      interventions; bidirected edges are shared exogenous background:
      one clique per un-merged same-variable copy set, plus one per
      original latent spread across worlds). Fixed nodes appear in
      ``graph`` (they are parents / carry ancestry) but never in
      ``bidirected`` and never in a c-component.
    - ``fixed`` — the intervention-fixed representatives.
    - ``value`` — every representative's known value (observed or fixed);
      absent when unknown.
    - ``subscript`` — every representative's counterfactual subscript
      ``An(ω) ∩ sub(γ)`` (its fixed ancestors, as ``(atom, value)``).
    - ``gamma_prime`` — the refined conjunction: the ``γ`` events remapped
      onto representatives, each ``(rep, value)``.
    """

    graph: nx.DiGraph
    bidirected: frozenset
    fixed: frozenset
    value: dict
    subscript: dict
    gamma_prime: tuple

    def observable(self) -> frozenset:
        """``V(G')`` — the non-fixed nodes (the ones ID* factorizes over)."""
        return frozenset(n for n in self.graph.nodes() if n not in self.fixed)

    def c_component_partition(self) -> tuple[frozenset, ...]:
        """The maximal c-components of ``G'`` over the observable nodes
        (fixed / intervened nodes are excluded, R-336 §A.8)."""
        obs = self.observable()
        sub_graph = self.graph.subgraph(obs)
        sub_bi = frozenset(p for p in self.bidirected if p <= obs)
        return c_components(sub_graph, sub_bi)


# ---------------------------------------------------------------------------
# make-cg
# ---------------------------------------------------------------------------

def _base_vars(graph: nx.DiGraph, bidirected: BidirectedEdgeSet) -> frozenset[Atom]:
    return frozenset(graph.nodes()) | {a for pair in bidirected for a in pair}


def _base_topo(graph: nx.DiGraph, base: frozenset[Atom]) -> list[Atom]:
    in_graph = [n for n in base if n in graph.nodes()]
    order = list(nx.topological_sort(graph.subgraph(in_graph)))
    extras = sorted(
        (n for n in base if n not in graph.nodes()),
        key=lambda a: (a.predicate, tuple(t.name for t in a.args)),
    )
    return order + extras


class _UnionFind:
    def __init__(self, items):
        self.parent = {x: x for x in items}

    def find(self, x):
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[x] != root:
            self.parent[x], x = root, self.parent[x]
        return root

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb
        return self.find(a)


def make_cg(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    gamma: Conjunction,
):
    """Construct the counterfactual graph of ``γ`` (R-336 Fig. 10).

    Returns a :class:`CfGraph`, or :data:`INCONSISTENT` when two nodes that
    merge under Lemma 24 carry different observed values (so ``P(γ)=0``).
    """
    base = _base_vars(graph, bidirected)
    worlds = frozenset(e.subscript for e in gamma)
    if not worlds:
        worlds = frozenset({frozenset()})

    nodes = [PWNode(v, w) for v in base for w in worlds]

    # ---- known values: intervention-fixed, then γ-observed --------------
    known: dict[PWNode, AtomValue] = {}
    for n in nodes:
        if _is_fixed(n):
            known[n] = _world_value(n.world, n.variable)
    for e in gamma:
        n = PWNode(e.variable, e.subscript)
        if n in known and known[n] != e.value:
            # An event observes a value contradicting the intervention that
            # fixes the same node — the effectiveness violation (x_{x'}).
            return INCONSISTENT
        known[n] = e.value

    fixed = frozenset(n for n in nodes if _is_fixed(n))

    # ---- merge (Lemmas 24-25) in topological order ----------------------
    uf = _UnionFind(nodes)
    group_value: dict[PWNode, AtomValue] = {}
    for n in nodes:
        if n in known:
            group_value[uf.find(n)] = known[n]

    def rep_value(n: PWNode) -> AtomValue | None:
        return group_value.get(uf.find(n))

    def merge_group(a: PWNode, b: PWNode) -> bool:
        """Union ``a`` and ``b``; return False if their values clash."""
        va, vb = rep_value(a), rep_value(b)
        if va is not None and vb is not None and va != vb:
            return False
        root = uf.union(a, b)
        v = va if va is not None else vb
        if v is not None:
            group_value[root] = v
        return True

    def parents(v: Atom) -> tuple[Atom, ...]:
        return tuple(graph.predecessors(v)) if v in graph else ()

    for v in _base_topo(graph, base):
        copies = [PWNode(v, w) for w in worlds if not _is_fixed(PWNode(v, w))]
        for a, b in combinations(copies, 2):
            if uf.find(a) == uf.find(b):
                continue
            shared_or_equal = True
            for p in parents(v):
                pa, pb = PWNode(p, a.world), PWNode(p, b.world)
                if uf.find(pa) == uf.find(pb):
                    continue  # shared parent
                vpa, vpb = rep_value(pa), rep_value(pb)
                if vpa is not None and vpb is not None and vpa == vpb:
                    continue  # parents attain the same value
                shared_or_equal = False
                break
            if shared_or_equal:
                if not merge_group(a, b):
                    return INCONSISTENT

    rep = uf.find

    # ---- directed edges over representatives ----------------------------
    cg = nx.DiGraph()
    for n in nodes:
        cg.add_node(rep(n))
    for v in base:
        for w in worlds:
            child = PWNode(v, w)
            if _is_fixed(child):
                continue  # intervention severs incoming mechanism
            for p in parents(v):
                cg.add_edge(rep(PWNode(p, w)), rep(child))
    cg.remove_edges_from(list(nx.selfloop_edges(cg)))

    fixed_reps = frozenset(rep(n) for n in fixed)

    # ---- bidirected edges: shared exogenous background ------------------
    bi: set[frozenset] = set()
    # U_V shared across un-merged random copies of each variable.
    for v in base:
        grp = {rep(PWNode(v, w)) for w in worlds if not _is_fixed(PWNode(v, w))}
        grp -= fixed_reps
        for pair in combinations(sorted(grp, key=id), 2):
            bi.add(frozenset(pair))
    # An original latent L (for A↔B) is one exogenous shared by every world,
    # so it couples all random copies of A and B into one clique.
    for pair in bidirected:
        a, b = tuple(pair)
        members = {rep(PWNode(a, w)) for w in worlds if not _is_fixed(PWNode(a, w))}
        members |= {rep(PWNode(b, w)) for w in worlds if not _is_fixed(PWNode(b, w))}
        members -= fixed_reps
        for x, y in combinations(sorted(members, key=id), 2):
            bi.add(frozenset((x, y)))

    # ---- ancestral restriction An(γ') -----------------------------------
    gamma_nodes = [rep(PWNode(e.variable, e.subscript)) for e in gamma]
    keep: set = set(gamma_nodes)
    for gn in gamma_nodes:
        if gn in cg:
            keep |= nx.ancestors(cg, gn)
    cg = cg.subgraph(keep).copy()
    bi = {p for p in bi if p <= keep}
    fixed_reps = frozenset(n for n in fixed_reps if n in keep)

    # ---- per-node value + subscript (An(ω) ∩ sub(γ)) --------------------
    value = {n: group_value[n] for n in cg.nodes() if n in group_value}
    subscript: dict = {}
    for n in cg.nodes():
        anc = nx.ancestors(cg, n) | {n}
        fixed_anc = {a for a in anc if a in fixed_reps}
        subscript[n] = frozenset(
            (a.variable, value[a]) for a in fixed_anc if a in value
        )

    gamma_prime = tuple((rep(PWNode(e.variable, e.subscript)), e.value) for e in gamma)

    return CfGraph(
        graph=cg,
        bidirected=frozenset(bi),
        fixed=fixed_reps,
        value=value,
        subscript=subscript,
        gamma_prime=gamma_prime,
    )
