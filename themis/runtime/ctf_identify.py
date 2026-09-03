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

from ..types import (
    Atom,
    AtomValue,
    BindDecl,
    ConstantExpr,
    FormulaExpr,
    FractionExpr,
    ProductExpr,
    SumExpr,
    ValuedAtom,
    VarRef,
)
from .structural_solver import BidirectedEdgeSet, c_components, m_separated


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




def _world_value(world: World, atom: Atom) -> AtomValue | None:
    for (a, v) in world:
        if a == atom:
            return v
    return None


def _is_fixed(node: PWNode) -> bool:
    """A node is *fixed* when its own variable is intervened in its world —
    it takes the intervention value and has no incoming mechanism.

    Asked of the same lookup that answers *which* value it takes, so the two
    questions cannot come apart: a node this says is fixed always has a
    value, and that is what lets the caller store one without a fallback.
    """
    return _world_value(node.world, node.variable) is not None


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
        fixed_value = _world_value(n.world, n.variable)
        if fixed_value is not None:  # i.e. _is_fixed(n), one lookup
            known[n] = fixed_value
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
    for edge in bidirected:
        left, right = tuple(edge)
        members = {rep(PWNode(left, w)) for w in worlds
                   if not _is_fixed(PWNode(left, w))}
        members |= {rep(PWNode(right, w)) for w in worlds
                    if not _is_fixed(PWNode(right, w))}
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


# ---------------------------------------------------------------------------
# ID*  (R-336 Fig. 11) — general counterfactual identification
# ---------------------------------------------------------------------------

class _Zero:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "ZERO"


class _Fail:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "FAIL"


class _Undefined:
    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return "UNDEFINED"


ZERO = _Zero()
FAIL = _Fail()
UNDEFINED = _Undefined()

# Defensive cap on ID* recursion depth. The algorithm provably terminates
# (each Line-6 recursion adds interventions that shrink the problem); the cap
# only guards against a pathological non-progressing input and degrades to
# FAIL instead of a RecursionError.
_MAX_CTF_DEPTH = 64


@dataclass(frozen=True)
class _SumVar:
    """A value slot bound by the Line-6 summation over the unvalued
    observable nodes ``V(G')\\γ'``. Carried as a counterfactual event value
    through the recursion and rendered as a FormulaExpr ``VarRef`` at the
    base case, so the same summed variable in a sibling's subscript and in
    its own event share one binding."""

    name: str


def _sumvar_name(node: PWNode) -> str:
    args = "_".join(t.name for t in node.variable.args)
    base = f"cf_{node.variable.predicate}"
    return f"{base}_{args}" if args else base


def _node_value(cf: CfGraph, node: PWNode):
    if node in cf.value:
        return cf.value[node]
    return _SumVar(_sumvar_name(node))  # unvalued observable → outer-Σ bound


def _to_value_expr(value):
    if isinstance(value, _SumVar):
        return VarRef(name=value.name)
    return value


def id_star(graph: nx.DiGraph, bidirected: BidirectedEdgeSet, gamma: Conjunction):
    """ID* (Shpitser-Pearl R-336 Fig. 11): identify ``P(γ)`` for a
    counterfactual conjunction ``γ``.

    Returns a :data:`FormulaExpr` in terms of observational ``P(v)`` (each
    interventional ``P*`` leaf is reduced through the existing ID engine),
    or :data:`ZERO` when ``P(γ)=0`` (an inconsistent / effectiveness-
    violating conjunction), or :data:`FAIL` when the query is provably
    non-identifiable (a w-graph / subscript conflict witness).
    """
    return _id_star(graph, bidirected, gamma, 0)


def _id_star(graph, bidirected, gamma, depth):
    if depth > _MAX_CTF_DEPTH:
        return FAIL

    # Line 1: empty conjunction.
    if not gamma:
        return ConstantExpr(value=1.0)

    # Lines 2-3: an event whose variable is intervened in its own world.
    for e in gamma:
        forced = _world_value(e.subscript, e.variable)
        if forced is not None:
            if forced != e.value:
                return ZERO   # Line 2: effectiveness violation, x_{x'}.
            rest = tuple(x for x in gamma if x is not e)  # Line 3: drop x_{x}.
            return _id_star(graph, bidirected, rest, depth + 1)

    # Line 4: build the counterfactual graph.
    cf = make_cg(graph, bidirected, gamma)
    if cf is INCONSISTENT:
        return ZERO   # Line 5.

    parts = cf.c_component_partition()
    obs = cf.observable()
    gp_nodes = frozenset(n for n, _v in cf.gamma_prime)
    summed = obs - gp_nodes   # V(G') \ γ'

    if len(parts) > 1:
        # Line 6: Σ_{V(G')\γ'} Π_i ID*(G, S^i_{ v(G')\S^i }).
        factors: list = []
        for si in parts:
            sub_gamma = _subconjunction(cf, si, obs)
            f = _id_star(graph, bidirected, sub_gamma, depth + 1)
            if f is FAIL:
                return FAIL
            if f is ZERO:
                return ZERO
            factors.append(f)
        body: FormulaExpr = (
            factors[0] if len(factors) == 1 else ProductExpr(terms=tuple(factors))
        )
        for m in sorted(summed, key=_sumvar_name):
            body = SumExpr(
                bind=BindDecl(name=_sumvar_name(m)), over=m.variable, body=body)
        return body

    # Lines 7-9: single c-component.
    (s,) = parts
    return _base_case(graph, bidirected, cf, s)


def _subconjunction(cf: CfGraph, si, obs) -> Conjunction:
    """Build ``S^i_{ v(G')\\S^i }`` (Line 6): the events of ``S^i``, each
    additionally intervened by fixing every OTHER observable node to its
    value.

    An added intervention on a variable that already fixes the node's own
    world (i.e. it is present in ``cf.subscript[n]``) is DROPPED: it refers to
    a *different* world-copy of that variable and must not override the
    node's own ancestral value. Without this, a node like ``W_x`` (whose own
    world fixes ``X=x``) collides with the factual observation ``x'`` on the
    base variable ``X`` — the subscript becomes ``{(X,x),(X,x')}`` and the
    downstream ``P(W)`` is evaluated under the wrong intervention value. This
    is exactly the paper's "remove redundant subscripts" step: the {W}
    c-component of ``P(y_{x,z},x')`` reduces to ``P(w_x)``, keeping only
    ``x`` and dropping the added ``x'`` and ``y``."""
    others = tuple((m.variable, _node_value(cf, m)) for m in (obs - set(si)))
    events = []
    for n in si:
        own_vars = {a for (a, _v) in cf.subscript[n]}
        extra = frozenset((v, val) for (v, val) in others if v not in own_vars)
        events.append(CtfEvent(
            variable=n.variable,
            subscript=cf.subscript[n] | extra,
            value=_node_value(cf, n),
        ))
    return tuple(events)


def _base_case(graph, bidirected, cf: CfGraph, s):
    """Lines 7-9: single c-component ``S``. Line 8 fails on a subscript /
    observation conflict; Line 9 returns ``P_x(var(S))`` with ``x=⋃sub(S)``,
    reduced to observational ``P(v)`` through the ID engine."""
    from .c_factor import (
        _admg_topo_order,
        _id_set_structural,
        _IDC_VALUE_SENTINEL,
        _map_valued_atoms,
    )

    # Gather, across the whole component, the values each variable takes as a
    # subscript (intervention) and as an observation (a node value).
    sub_by_var: dict = {}
    for n in s:
        for (a, av) in cf.subscript[n]:
            sub_by_var.setdefault(a, set()).add(av)
    obs_by_var: dict = {}
    for n in s:
        obs_by_var.setdefault(n.variable, set()).add(_node_value(cf, n))

    # Line 8: FAIL when a variable is intervened to two different values, or a
    # subscript value conflicts with an observed value of the same variable
    # (∃ x≠x', x∈sub(S), x'∈ev(S)) — this is the w-graph / PNS witness. Also
    # FAIL a genuine cross-world joint on one variable (two distinct observed
    # values) that the subscript check did not already rule out: that shape is
    # outside the single-interventional-distribution base case.
    for a, vals in sub_by_var.items():
        if len(vals) > 1:
            return FAIL
        (sv,) = tuple(vals)
        if a in obs_by_var and any(ov != sv for ov in obs_by_var[a]):
            return FAIL
    for vals in obs_by_var.values():
        if len(vals) > 1:
            return FAIL

    # Line 9: P_x(var(S)), x = ⋃ sub(S). make_cg's subscripts are An(ω)∩sub(γ)
    # — already ancestor-restricted, so redundant subscripts are gone.
    target_value = {n.variable: _node_value(cf, n) for n in s}
    xsub = {a: next(iter(vals)) for a, vals in sub_by_var.items()}
    y_set = frozenset(target_value)
    x_set = frozenset(xsub) - y_set

    V = _base_vars(graph, bidirected)
    topo = tuple(_admg_topo_order(graph, V))
    formula, _trail, _hedge = _id_set_structural(
        graph, bidirected, topo, V, x_set=x_set, y_set=y_set,
    )
    if formula is None:
        # Identifiable from experiments (P*) but the interventional leaf does
        # not reduce to observational P(v) — outside this engine's remit.
        return FAIL

    def bind(va: ValuedAtom, _bound: frozenset[str]) -> ValuedAtom:
        if va.value is _IDC_VALUE_SENTINEL:
            return ValuedAtom(atom=va.atom, value=_to_value_expr(xsub[va.atom]))
        if va.value is None and va.atom in target_value:
            return ValuedAtom(
                atom=va.atom, value=_to_value_expr(target_value[va.atom]))
        return va

    return _map_valued_atoms(formula, bind)


# ---------------------------------------------------------------------------
# IDC*  (R-336 / JMLR 9:1941-1979 Fig. 12) — conditional counterfactual id.
# ---------------------------------------------------------------------------

def idc_star(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    gamma: Conjunction,
    delta: Conjunction,
):
    """IDC* (Shpitser-Pearl Fig. 12): identify ``P(γ | δ)`` for a
    conditional counterfactual — a conjunction ``γ`` given counterfactual
    evidence ``δ`` (both spanning arbitrary hypothetical worlds).

    Returns a :data:`FormulaExpr` (a :class:`FractionExpr` numerator/den
    ratio, ultimately in terms of observational ``P(v)``), or:

    - :data:`ZERO` — ``P(γ|δ) = 0`` (the numerator conjunction is
      inconsistent while the conditioning event has positive probability);
    - :data:`FAIL` — provably non-identifiable from ``P*``;
    - :data:`UNDEFINED` — ``P(δ) = 0``, so the conditional is not defined
      (Line 1: conditioning on a zero-probability counterfactual event).

    When ``δ`` is empty this is exactly the unconditional :func:`id_star`.

    The algorithm's central step (Line 4) moves a conditioning event
    ``Y_x = y`` from the evidence ``δ`` into the *intervention* subscript of
    every descendant in ``γ`` whenever there is no back-door path from
    ``Y_x`` to ``γ'`` — tested as the **marginal** m-separation
    ``(Y_x ⊥⊥ γ')`` (empty conditioning set) in the counterfactual graph
    ``G'`` with the *outgoing* arcs of ``Y_x`` deleted (``G'_{\\underline{y_x}}``;
    bidirected arcs, being latent common causes *into* ``Y_x``, remain — a
    surviving one is precisely a back-door and correctly blocks the move).
    """
    return _idc_star(graph, bidirected, tuple(gamma), tuple(delta), 0)


def _idc_star(graph, bidirected, gamma, delta, depth):
    if depth > _MAX_CTF_DEPTH:
        return FAIL

    # Line 1: conditioning on a zero-probability event is undefined. (δ empty
    # degenerates to the unconditional query, whose ID* handles Line 1's job.)
    if not delta:
        return id_star(graph, bidirected, gamma)
    if id_star(graph, bidirected, delta) is ZERO:
        return UNDEFINED

    # Line 2: one counterfactual graph for the *joint* γ ∧ δ (make-cg only
    # takes conjunctions), so γ' and δ' share the same relabelled worlds.
    cf = make_cg(graph, bidirected, gamma + delta)
    if cf is INCONSISTENT:
        return ZERO   # Line 3.

    # Split γ' | δ': gamma_prime preserves the input order, so the first
    # |γ| representatives are γ', the rest δ'.
    gamma_reps = cf.gamma_prime[: len(gamma)]
    delta_reps = cf.gamma_prime[len(gamma):]
    gamma_nodes = frozenset(r for r, _v in gamma_reps)

    # Line 4: can any y_x ∈ δ' be moved into γ's subscript (no back-door)?
    for idx, (yx_rep, _yx_val) in enumerate(delta_reps):
        if yx_rep in gamma_nodes:
            continue  # already a γ' node (merged) — nothing to move
        g_under = cf.graph.copy()
        g_under.remove_edges_from(list(cf.graph.out_edges(yx_rep)))
        if all(
            m_separated(g_under, cf.bidirected, yx_rep, g, ())
            for g in gamma_nodes
        ):
            new_gamma, new_delta = _move_evidence(cf, gamma_reps, delta_reps, idx)
            return _idc_star(graph, bidirected, new_gamma, new_delta, depth + 1)

    # Line 5: no more moves. P(γ|δ) = P(γ' ∧ δ') / P(δ'). Both ends are
    # ID* on the current (relabelled) conjunctions. The denominator is the
    # marginal P(δ') — computed as an independent ID*(δ') rather than the
    # paper's syntactic Σ_{var(γ')} of the joint. The two are numerically
    # identical by the law of total probability; the independent form
    # sidesteps the ambiguity of marginalising "over var(γ')" once ID* has
    # dissolved the counterfactual nodes into observational P(v) and the
    # γ'/δ' provenance of a shared base variable is no longer visible. The
    # cost is a ratio whose common factors are not syntactically cancelled;
    # the graph, not the formula, is the human surface, and the MC probe
    # checks the number regardless.
    num = id_star(graph, bidirected, gamma + delta)
    if num is FAIL:
        return FAIL
    if num is ZERO:
        return ConstantExpr(value=0.0)
    den = id_star(graph, bidirected, delta)
    if den is FAIL:
        return FAIL
    if den is ZERO:
        return UNDEFINED
    return FractionExpr(numerator=num, denominator=den)


def _move_evidence(cf: CfGraph, gamma_reps, delta_reps, idx):
    """Line-4 relabelling: move ``δ'[idx] = (Y_x = y)`` into the intervention
    subscript of every γ' event that descends from it (``γ'_{y_x}``), and drop
    it from δ' (``δ' ∖ {y_x}``). Representatives are rebuilt into counterfactual
    events over the *original* variables — the recursion re-runs make-cg, so
    the moved world propagates through a fresh (possibly different) cf graph,
    exactly as the worked example ``P(y_x | x',z_d,d)`` does."""
    yx_rep, yx_val = delta_reps[idx]
    added = (yx_rep.variable, yx_val)
    descendants = nx.descendants(cf.graph, yx_rep)

    def to_event(rep, value, extra):
        world = cf.subscript[rep] | ({added} if extra else frozenset())
        return CtfEvent(variable=rep.variable, subscript=frozenset(world), value=value)

    new_gamma = tuple(
        to_event(rep, value, rep in descendants) for (rep, value) in gamma_reps
    )
    new_delta = tuple(
        to_event(rep, value, False)
        for j, (rep, value) in enumerate(delta_reps) if j != idx
    )
    return new_gamma, new_delta
