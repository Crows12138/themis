"""Pure-structural reasoning on G(M).

Answers questions that depend only on graph topology:

- cause(A, B):  is there a directed path A -> ... -> B ?
- assoc(A, B | C):  is there a path between A and B that is open
  relative to conditioning set C (d-separation) ?
- backdoor paths from X to Y, and valid adjustment sets.

Completeness targets for v0.1 are stated in 理论框架_v0_1.md §14.

Slice 1 only implements directed-path queries (cause). d-separation,
back-door, and adjustment sets land in later slices.
"""
from __future__ import annotations

import networkx as nx

from ..types import Atom, BidirectedStatement


def has_directed_path(graph: nx.DiGraph, src: Atom, dst: Atom) -> bool:
    """Return True iff a directed path src -> ... -> dst exists."""
    if src not in graph or dst not in graph:
        return False
    if src == dst:
        # A node has a trivial path to itself, but for cause() this
        # should not be reported as causal influence.
        return False
    return nx.has_path(graph, src, dst)


def directed_paths(
    graph: nx.DiGraph, src: Atom, dst: Atom
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate directed simple paths from src to dst.

    Used by the explanation layer to cite supporting_paths.
    """
    if src not in graph or dst not in graph or src == dst:
        return ()
    return tuple(tuple(p) for p in nx.all_simple_paths(graph, src, dst))


def _is_collider(graph: nx.DiGraph, u: Atom, v: Atom, w: Atom) -> bool:
    """True iff v is a collider on the path segment u - v - w, i.e.
    both directed edges u -> v and w -> v exist in the DAG."""
    return graph.has_edge(u, v) and graph.has_edge(w, v)


def _node_blocks_path(
    graph: nx.DiGraph,
    u: Atom,
    v: Atom,
    w: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """Decide whether intermediate node v blocks the path segment u - v - w.

    - Non-collider (chain / fork): blocked iff v is in conditioning.
    - Collider: blocked iff neither v nor any descendant of v is in
      conditioning (i.e. blocked when collider is NOT activated).
    """
    if _is_collider(graph, u, v, w):
        activated = {v} | nx.descendants(graph, v)
        return activated.isdisjoint(conditioning)
    return v in conditioning


def _path_is_open(
    graph: nx.DiGraph,
    path: tuple[Atom, ...],
    conditioning: frozenset[Atom],
) -> bool:
    """A simple undirected path is open iff no intermediate node blocks it."""
    for i in range(1, len(path) - 1):
        if _node_blocks_path(
            graph, path[i - 1], path[i], path[i + 1], conditioning
        ):
            return False
    return True


def _iter_undirected_simple_paths(
    graph: nx.DiGraph, src: Atom, dst: Atom
):
    """Iterate simple paths between src and dst ignoring edge direction."""
    return nx.all_simple_paths(graph.to_undirected(as_view=True), src, dst)


def is_d_connected(
    graph: nx.DiGraph,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> bool:
    """Return True iff at least one path between left and right is
    open given the conditioning set (d-separation criterion)."""
    if left not in graph or right not in graph or left == right:
        return False
    c_set = frozenset(conditioning)
    for path in _iter_undirected_simple_paths(graph, left, right):
        if _path_is_open(graph, tuple(path), c_set):
            return True
    return False


def open_paths(
    graph: nx.DiGraph,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate paths that are open under the conditioning set.

    Only the open paths are returned. Closed paths are intentionally
    omitted from the result structure for v0.1; if explanatory value
    requires listing them, extend ``StructuralResult`` separately.
    """
    if left not in graph or right not in graph or left == right:
        return ()
    c_set = frozenset(conditioning)
    return tuple(
        tuple(p)
        for p in _iter_undirected_simple_paths(graph, left, right)
        if _path_is_open(graph, tuple(p), c_set)
    )


def backdoor_paths(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
) -> tuple[tuple[Atom, ...], ...]:
    """Enumerate all back-door paths from X to Y.

    A back-door path is an undirected simple path between X and Y
    whose first edge points INTO X (i.e. there exists a directed
    edge ``path[1] -> X`` in the DAG). These are the paths that
    can carry confounding association.
    """
    if x not in graph or y not in graph or x == y:
        return ()
    result: list[tuple[Atom, ...]] = []
    for raw in _iter_undirected_simple_paths(graph, x, y):
        path = tuple(raw)
        if len(path) >= 2 and graph.has_edge(path[1], x):
            result.append(path)
    return tuple(result)


def front_door_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    bidirected: "BidirectedEdgeSet | None" = None,
) -> tuple[frozenset[Atom], ...]:
    """Find subset-minimal mediator sets Z satisfying Pearl's front-door
    criterion relative to (X, Y):

    (FD1) every directed path from X to Y passes through some z ∈ Z
    (FD2) no back-door path from X to any z ∈ Z is open under empty
          conditioning
    (FD3) every back-door path from any z ∈ Z to Y is blocked by {X}

    The candidate space is restricted to nodes that lie on some
    directed path X → ... → Y (i.e. descendants of X that are
    ancestors of Y, excluding X and Y themselves). Returns () if X / Y
    lie outside the graph, if X == Y, or if no admissible Z exists.

    The front-door criterion is consulted only after back-door search
    has failed — ``minimal_adjustment_sets(graph, x, y, given=())`` is
    the first attempt, and this function covers the residual cases in
    Pearl's textbook where back-door is unavailable but a mediator set
    still identifies the effect.

    Phase 2.latent S3.a: when ``bidirected`` is provided and non-empty,
    FD2 and FD3 use ADMG m-separation (via ``is_m_connected``) instead
    of plain d-separation. This respects any extra back-door paths the
    bidirected edges create. When ``bidirected`` is empty or ``None``
    the logic reduces exactly to the original directed-only front-door
    check (regression guaranteed by the S3.a pin tests). FD1 still uses
    the directed skeleton — mediators must block every *directed* path
    X → ... → Y, which is unaffected by bidirected edges.
    """
    from itertools import combinations

    if x not in graph or y not in graph or x == y:
        return ()

    descendants_x = nx.descendants(graph, x)
    ancestors_y = nx.ancestors(graph, y)
    candidates = [c for c in ((descendants_x & ancestors_y) - {x, y})]
    if not candidates:
        return ()

    directed_all = tuple(
        tuple(p) for p in nx.all_simple_paths(graph, x, y)
    )
    if not directed_all:
        return ()

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    def blocks_all_directed(z: frozenset[Atom]) -> bool:
        for path in directed_all:
            if not (set(path[1:-1]) & z):
                return False
        return True

    def no_open_backdoor_from_x(zi: Atom) -> bool:
        # A back-door path from X to zi is one that leaves X via an
        # arrowhead at X (incoming directed edge OR a bidirected edge),
        # hence d/m-connected from X to zi under empty conditioning AND
        # not via an edge leaving X (X → ...).
        # In practice: when bidir is empty this reduces to the original
        # directed-only check; when bidir is non-empty we must also
        # account for X ↔ ... paths. We compute this by asking: is X
        # connected to zi via a path whose first edge is not X → *?
        #
        # For correctness with bidir present, we inline the per-path
        # check rather than reusing ``backdoor_paths`` (which only
        # enumerates directed-skeleton paths).
        return not _is_admg_backdoor_connected(
            graph, bidir_eff, x, zi, frozenset()
        )

    def all_backdoors_to_y_blocked_by_x(zi: Atom) -> bool:
        return not _is_admg_backdoor_connected(
            graph, bidir_eff, zi, y, frozenset({x})
        )

    def satisfies(z: frozenset[Atom]) -> bool:
        if not blocks_all_directed(z):
            return False
        for zi in z:
            if not no_open_backdoor_from_x(zi):
                return False
            if not all_backdoors_to_y_blocked_by_x(zi):
                return False
        return True

    minimal: list[frozenset[Atom]] = []
    for size in range(1, len(candidates) + 1):
        for combo in combinations(candidates, size):
            z = frozenset(combo)
            if any(existing < z for existing in minimal):
                continue
            if satisfies(z):
                minimal.append(z)
    # Deterministic order. `candidates` derives from a set intersection
    # (descendants ∩ ancestors), whose iteration order is hash-seeded and
    # so varies across processes. That made the returned tuple — and hence
    # the scheduler's `min(front, key=len)` mediator choice — NON-
    # deterministic: the same chain program (x→m1→m2→y, x↔y has the two
    # singleton front-door sets {m1} and {m2}) demanded P(m1|x) on one run
    # and P(m2|x) on the next. Sort by (size, predicate tuple) so callers
    # get a reproducible set and `min(..., key=len)` breaks ties stably.
    # Real-usage probe, 2026-06-15.
    minimal.sort(key=lambda z: (len(z), tuple(sorted(a.predicate for a in z))))
    return tuple(minimal)


# =====================================================================
# Phase 6.iv: IV identification primitive (see PHASE_6_IV_CHARTER.md)
# =====================================================================

from typing import NamedTuple


class IVCandidate(NamedTuple):
    """A valid instrumental-variable candidate for (X, Y).

    - ``instrument``: the atom Z that serves as the instrument
    - ``conditioning``: frozen set W such that Z satisfies Pearl's IV
      conditions given W (empty set = basic IV; non-empty = conditional
      IV)
    """

    instrument: Atom
    conditioning: frozenset[Atom]


def iv_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    *,
    bidirected: "BidirectedEdgeSet | None" = None,
    max_conditioning_size: int = 3,
) -> tuple[IVCandidate, ...]:
    """Find valid instrumental-variable candidates for (X, Y).

    A node Z is a valid IV (optionally given conditioning set W) iff:

    - **IV1 (relevance)**: Z is m-connected to X given W in G — i.e.
      there is an open directed/ADMG path from Z to X that is not
      entirely blocked by W.
    - **IV2 + IV3 (exogeneity + exclusion)**: in the mutilated graph
      G[\\bar{X}] (G with all edges *leaving* X removed), Z is
      m-separated from Y given W. This captures both:
        - exogeneity: Z shares no latent common cause with Y
          (via bidirected edges, which are preserved in G[\\bar{X}])
        - exclusion: every Z→Y association in original G goes through X

    Reference: Brito & Pearl 2002 Theorem 2; Pearl 2009 ch.8. The IV
    condition reduces cleanly to a single m-separation check in the
    mutilated graph, plus a relevance check in the original graph.

    ``bidirected`` carries ADMG semi-Markov edges (from Phase 2.latent).
    When None or empty, the check reduces to the pure-DAG version.

    ``max_conditioning_size`` caps the size of the search space for W
    (see PHASE_6_IV_CHARTER.md §8.2). Default 3 balances coverage
    (most real-world conditional IV use |W| ≤ 2) against enumeration
    cost (O(n choose k) subsets for each Z).

    W is drawn from nodes that are not X, Y, Z, or descendants of X
    in G. Descendants are excluded to prevent conditioning on
    mediators (standard IV practice).

    Returns a tuple of ``IVCandidate`` entries, sorted by:

    1. |W| ascending (basic IV before conditional IV)
    2. instrument predicate (stable ordering across runs)
    3. conditioning predicates (stable ordering)

    For each Z, only subset-minimal valid W are reported — if both
    W1 ⊂ W2 work for the same Z, only W1 is kept.
    """
    from itertools import combinations

    if x not in graph or y not in graph or x == y:
        return ()

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    # Mutilated graph: G with all edges leaving X removed.
    # This captures "what can Z reach without going through X?".
    mutilated = graph.copy()
    mutilated.remove_edges_from(list(mutilated.out_edges(x)))

    # Descendants of X in ORIGINAL G — these are excluded from W
    # (conditioning on mediators breaks identification).
    x_descendants = nx.descendants(graph, x)

    # Instrument candidates: all nodes except X and Y.
    # IV1 will filter out any Z with no directed route to X.
    z_candidates = [v for v in graph.nodes if v != x and v != y]

    all_results: list[IVCandidate] = []

    for z in z_candidates:
        # W candidates: nodes other than X, Y, Z, and X's descendants.
        w_pool = [
            v for v in graph.nodes
            if v != x and v != y and v != z and v not in x_descendants
        ]

        # Collect subset-minimal valid W for this Z.
        minimal_ws: list[frozenset[Atom]] = []
        upper_size = min(max_conditioning_size, len(w_pool))
        for size in range(0, upper_size + 1):
            for combo in combinations(w_pool, size):
                w = frozenset(combo)
                # Subset-minimality: skip if a smaller valid W exists.
                if any(existing <= w for existing in minimal_ws):
                    continue

                w_tuple = tuple(w)

                # IV1: Z and X m-connected given W in original G.
                if not is_m_connected(graph, bidir_eff, z, x, w_tuple):
                    continue

                # IV2 + IV3: Z m-separated from Y in mutilated graph
                # given W (all remaining Z→Y paths would require going
                # through X's outgoing edges, which are removed).
                if is_m_connected(mutilated, bidir_eff, z, y, w_tuple):
                    continue

                minimal_ws.append(w)

        for w in minimal_ws:
            all_results.append(IVCandidate(instrument=z, conditioning=w))

    all_results.sort(
        key=lambda c: (
            len(c.conditioning),
            c.instrument.predicate,
            tuple(sorted(a.predicate for a in c.conditioning)),
        )
    )
    return tuple(all_results)


def _is_admg_backdoor_connected(
    graph: nx.DiGraph,
    bidirected: "BidirectedEdgeSet",
    src: Atom,
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """Is there an open m-path from ``src`` to ``dst`` whose first edge
    leaves ``src`` with an arrowhead at ``src`` (i.e. a back-door path
    in the ADMG sense)?

    An edge has an arrowhead at ``src`` iff it is a bidirected edge
    incident to ``src`` or a directed edge ``pred → src``. Enumerate
    simple m-paths and filter by the first-edge condition.
    """
    if src == dst:
        return False

    mg = _build_admg_path_graph(graph, bidirected)
    if src not in mg or dst not in mg:
        return False

    for edge_path in nx.all_simple_edge_paths(mg, src, dst):
        first_u, first_w, first_k = edge_path[0]
        data = mg.edges[first_u, first_w, first_k]
        if data["kind"] == "bidirected":
            first_arrowhead_at_src = True
        else:
            first_arrowhead_at_src = (data["dst"] == src)
        if not first_arrowhead_at_src:
            continue

        nodes: list[Atom] = [src]
        for u, w, _k in edge_path:
            nodes.append(w if nodes[-1] == u else u)

        open_path = True
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            ahead_prev = _has_arrowhead_at(mg, edge_path[i - 1], v)
            ahead_next = _has_arrowhead_at(mg, edge_path[i], v)
            is_collider = ahead_prev and ahead_next
            if is_collider:
                activated = {v} | nx.descendants(graph, v) if v in graph else {v}
                if activated.isdisjoint(conditioning):
                    open_path = False
                    break
            else:
                if v in conditioning:
                    open_path = False
                    break
        if open_path:
            return True
    return False


def minimal_adjustment_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    given: tuple[Atom, ...] = (),
    bidirected: "BidirectedEdgeSet | None" = None,
) -> tuple[frozenset[Atom], ...]:
    """Find all subset-minimal **additional** back-door adjustment sets,
    disjoint from ``given``.

    A tuple element ``Z`` returned from this function satisfies:

    - ``Z`` is disjoint from ``given``,
    - no atom in ``Z ∪ given`` is a descendant of X,
    - ``Z ∪ given`` blocks every back-door path from X to Y, and
    - no proper subset ``Z' ⊊ Z`` also satisfies the above.

    The formula consumer treats ``given`` as already-conditioned context
    from the query; only ``Z`` is summed out.

    Returns ``()`` when X or Y lies outside the graph, or when
    ``given`` itself violates the back-door criterion (e.g. contains
    a descendant of X, or contains X or Y).

    Returns ``(frozenset(),)`` when ``given`` alone already blocks
    all back-door paths.

    Phase 2.latent S3.b.1: when ``bidirected`` is provided and non-empty,
    back-door path enumeration + blocking switch to the ADMG:
    ``_is_admg_backdoor_connected`` replaces ``backdoor_paths`` +
    ``_path_is_open``. The empty / None case is bit-identical to the
    original directed-only implementation (regression guaranteed).

    Descendant analysis for the pre-condition / candidate exclusion
    stays directed-only: descendants via bidirected edges are not
    defined in the ADMG, so bidirected-connected nodes are still
    admissible candidates (only directed descendants are forbidden).
    """
    from itertools import combinations

    if x not in graph or y not in graph or x == y:
        return ()

    given_set = frozenset(given)
    descendants_x = nx.descendants(graph, x)

    # given must itself obey the back-door criterion's pre-conditions.
    if given_set & (descendants_x | {x, y}):
        return ()

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    if bidir_eff:
        # ADMG-aware path: blocking check runs over m-paths that leave
        # X via an arrowhead at X (directed incoming OR bidirected).
        def blocks_all(z: frozenset[Atom]) -> bool:
            combined = z | given_set
            return not _is_admg_backdoor_connected(
                graph, bidir_eff, x, y, combined
            )
    else:
        # Directed-only path — unchanged from v1.0.
        bdoors = backdoor_paths(graph, x, y)

        def blocks_all(z: frozenset[Atom]) -> bool:
            combined = z | given_set
            for path in bdoors:
                if _path_is_open(graph, path, combined):
                    return False
            return True

    forbidden = descendants_x | {x, y} | given_set
    candidates: list[Atom] = [n for n in graph.nodes if n not in forbidden]

    minimal: list[frozenset[Atom]] = []
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            z = frozenset(combo)
            if any(existing < z for existing in minimal):
                continue
            if blocks_all(z):
                minimal.append(z)
    return tuple(minimal)


# =====================================================================
# Joint interventions: generalized (treatment-SET) back-door / adjustment
# criterion for do(A=a, B=b, ...).
#
# Reference: the complete adjustment criterion (van der Zander, Liśkiewicz
# & Textor 2014; Perković, Textor, Kalisch & Maathuis 2018, "Complete
# graphical characterization of adjustment sets") — itself the set
# generalization of Pearl's back-door criterion (Causality 2nd ed §3.3).
#
# A set Z is a valid adjustment set for the treatment SET X relative to Y
# iff
#   (i)  Z ∩ forbidden(X, Y) = ∅, where forbidden = X ∪ cn(X, Y) ∪
#        De(cn(X, Y)) — X itself plus every node on a *proper causal
#        path* from X to Y and all their descendants (the post-treatment
#        / mediator region you must not adjust on), and
#   (ii) Z d-separates X from Y in the *proper back-door graph* G_pbd,
#        which deletes from G the first edge X_i → V of every proper
#        causal path X_i → ... → Y.
# When Z satisfies (i)+(ii), Σ_z P(Y | X=x, Z=z) P(z) = P(Y | do(x)) for
# the whole treatment vector — exactly the joint g-formula the estimator
# plugs into.
# =====================================================================


def _proper_causal_path_nodes(
    graph: nx.DiGraph, treatments: frozenset[Atom], y: Atom,
) -> tuple[set[Atom], set[tuple[Atom, Atom]]]:
    """Return (cn_nodes, first_edges) for the treatment SET.

    - ``cn_nodes``: every node lying on a *proper* causal path from some
      treatment to Y — a directed path whose only treatment node is its
      start. Excludes the treatments themselves; includes Y.
    - ``first_edges``: the set of first edges ``(x, v)`` of those proper
      causal paths, to be removed when building the proper back-door
      graph.
    """
    cn_nodes: set[Atom] = set()
    first_edges: set[tuple[Atom, Atom]] = set()
    for x in treatments:
        if x not in graph or y not in graph or x == y:
            continue
        for raw in nx.all_simple_paths(graph, x, y):
            path = tuple(raw)
            # Proper: the path touches the treatment set only at its start.
            if set(path[1:]) & treatments:
                continue
            cn_nodes.update(path[1:])  # nodes after x, up to and incl. Y
            first_edges.add((path[0], path[1]))
    return cn_nodes, first_edges


def _set_d_connected(
    graph: nx.DiGraph,
    sources: frozenset[Atom],
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """True iff some node in ``sources`` has an open path to ``dst`` given
    ``conditioning`` (set d-connection). Paths may pass through other
    source nodes — they are ordinary intermediate nodes, NOT implicitly
    conditioned."""
    for s in sources:
        if s not in graph or dst not in graph or s == dst:
            continue
        for path in _iter_undirected_simple_paths(graph, s, dst):
            if _path_is_open(graph, tuple(path), conditioning):
                return True
    return False


def minimal_adjustment_sets_joint(
    graph: nx.DiGraph,
    treatments: "tuple[Atom, ...] | frozenset[Atom]",
    y: Atom,
    given: tuple[Atom, ...] = (),
    bidirected: "BidirectedEdgeSet | None" = None,
) -> tuple[frozenset[Atom], ...]:
    """Subset-minimal joint adjustment sets for the treatment SET.

    Generalizes :func:`minimal_adjustment_sets` from a single treatment
    to a set of simultaneously-intervened treatments do(A=a, B=b, ...).
    Each returned ``Z`` (disjoint from ``given``) makes ``Z ∪ given`` a
    valid adjustment set for ``(treatments, y)`` under the complete
    adjustment criterion described in the section header.

    Returns ``()`` when the treatments / y are malformed (outside the
    graph, overlapping, y among treatments, or ``given`` lands in the
    forbidden region). Returns ``(frozenset(),)`` when ``given`` alone
    already blocks all proper non-causal paths.

    v1 scope: directed DAGs only. ``bidirected`` non-empty raises
    ``NotImplementedError`` — joint ADMG (latent-confounded) adjustment
    is a follow-up; the caller falls back / surfaces the limitation.
    """
    from itertools import combinations

    if bidirected:
        raise NotImplementedError(
            "joint adjustment with bidirected (latent) edges is out of "
            "v1 scope; only directed-DAG joint back-door is supported"
        )

    x_set = frozenset(treatments)
    if not x_set or y in x_set:
        return ()
    if any(t not in graph for t in x_set) or y not in graph:
        return ()

    given_set = frozenset(given)
    if given_set & (x_set | {y}):
        return ()

    cn_nodes, first_edges = _proper_causal_path_nodes(graph, x_set, y)

    # (i) forbidden region: X ∪ proper-causal-path nodes ∪ their descendants.
    forbidden: set[Atom] = set(x_set) | set(cn_nodes)
    for node in cn_nodes:
        forbidden |= nx.descendants(graph, node)
    # given must avoid the forbidden region too — it is part of the
    # conditioning set the criterion validates.
    if given_set & forbidden:
        return ()

    # (ii) proper back-door graph: delete the first edge of each proper
    # causal path.
    g_pbd = graph.copy()
    g_pbd.remove_edges_from(first_edges)

    def blocks_all(z: frozenset[Atom]) -> bool:
        return not _set_d_connected(g_pbd, x_set, y, z | given_set)

    candidates = [
        n for n in graph.nodes
        if n not in forbidden and n not in given_set and n != y
    ]

    minimal: list[frozenset[Atom]] = []
    for size in range(len(candidates) + 1):
        for combo in combinations(candidates, size):
            z = frozenset(combo)
            if any(existing < z for existing in minimal):
                continue
            if blocks_all(z):
                minimal.append(z)
    return tuple(minimal)


# =====================================================================
# Phase 6.mediation: NDE/NIE/CDE identification (see
# PHASE_6_MEDIATION_CHARTER.md)
# =====================================================================


class MediationAttempt(NamedTuple):
    """Outcome of attempting to identify one mediation quantity.

    - ``identifiable``: True iff Pearl's graph-level conditions succeed
    - ``adjustment``: frozenset W used in the successful adjustment
      (empty when ``identifiable`` is False)
    - ``failed_condition``: the first condition that blocked
      identification ("M1" / "M2" / "M3" / "M4" / "C1" / "C2"), or None
      on success
    """

    identifiable: bool
    adjustment: frozenset[Atom]
    failed_condition: str | None


class MediationResult(NamedTuple):
    """Identification result for mediation quantities (X, M, Y).

    Both NDE/NIE and CDE are attempted independently. A given graph may
    support CDE only (classic M4 violation) or both — it never supports
    NDE/NIE without CDE when the mediator structure is valid.
    """

    mediator: Atom
    nde_nie: MediationAttempt
    cde: MediationAttempt
    mediator_valid: bool  # False if M doesn't mediate X→Y structurally


def _mutilate_outgoing(graph: nx.DiGraph, node: Atom) -> nx.DiGraph:
    """Return a copy of ``graph`` with all edges leaving ``node`` removed.

    This realises Pearl's ``G_{\\bar{node}}`` subgraph used to isolate
    backdoor paths (paths that cannot exit ``node`` via its outgoing
    directed edges).
    """
    g = graph.copy()
    g.remove_edges_from(list(g.out_edges(node)))
    return g


def _check_nde_nie_with_w(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    w: frozenset[Atom],
    bidirected: "BidirectedEdgeSet",
) -> str | None:
    """Return None iff the Pearl 2001 NDE/NIE four conditions hold for
    adjustment set W; else the first failing condition label.
    """
    # M4: W contains no descendants of X
    x_desc = nx.descendants(graph, x)
    if w & x_desc:
        return "M4"

    w_tuple = tuple(w)

    # M1: Y ⊥ X | W in G\bar{X} (all X→Y backdoors blocked by W)
    g_bar_x = _mutilate_outgoing(graph, x)
    if is_m_connected(g_bar_x, bidirected, x, y, w_tuple):
        return "M1"

    # M2: M ⊥ X | W in G\bar{X} (all X→M backdoors blocked by W)
    if is_m_connected(g_bar_x, bidirected, x, m, w_tuple):
        return "M2"

    # M3: Y ⊥ M | X, W in G\bar{M} (all M→Y backdoors blocked by {X}∪W)
    g_bar_m = _mutilate_outgoing(graph, m)
    xw_tuple = tuple(w | {x})
    if is_m_connected(g_bar_m, bidirected, m, y, xw_tuple):
        return "M3"

    return None


def _check_cde_with_w(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    w: frozenset[Atom],
    bidirected: "BidirectedEdgeSet",
) -> str | None:
    """Return None iff the CDE(m) back-door adjustment conditions hold
    for W; else the first failing condition label.

    C1: in G\\bar{XM} (outgoing edges from both X and M removed), Y is
        m-separated from X given W AND Y is m-separated from M given W.
    C2: W contains no descendants of X or of M.

    C2 is strictly weaker than M4 (CDE tolerates X-descendants that are
    not M-descendants, as long as they aren't on the X→Y backdoor via M
    routes).
    """
    # C2: W excludes descendants of X and of M
    x_desc = nx.descendants(graph, x)
    m_desc = nx.descendants(graph, m)
    if w & (x_desc | m_desc):
        return "C2"

    w_tuple = tuple(w)

    # C1: in G\bar{XM}, Y m-sep from both X and M given W
    g_bar_xm = _mutilate_outgoing(graph, x)
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(m)))
    if is_m_connected(g_bar_xm, bidirected, x, y, w_tuple):
        return "C1"
    if is_m_connected(g_bar_xm, bidirected, m, y, w_tuple):
        return "C1"

    return None


def mediation_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    *,
    bidirected: "BidirectedEdgeSet | None" = None,
    max_adjustment_size: int = 3,
) -> MediationResult:
    """Identify mediation quantities for treatment X, mediator M, outcome Y.

    Checks two strategies in order of informativeness:

    1. **NDE/NIE** (Pearl 2001 Theorem 2): four conditions M1-M4 over a
       candidate adjustment set W. Succeeds iff some W of size ≤
       ``max_adjustment_size`` (and drawn from non-X-descendants)
       satisfies all four. When succeeds, both NDE and NIE are
       identifiable via the mediation formula.
    2. **CDE(m)** (backdoor adjustment): conditions C1-C2 over a
       candidate W. Weaker than NDE/NIE — succeeds whenever standard
       backdoor adjustment on (X, M) jointly works for Y.

    Both strategies are attempted independently — a graph with an
    intermediate confounder (X-descendant that affects both M and Y)
    fails NDE/NIE (M4) but may still support CDE.

    Structural precondition: M must mediate — ``X → ... → M`` and
    ``M → ... → Y`` directed paths must both exist in ``graph``. If
    not, ``mediator_valid`` is False and both attempts are reported as
    non-identifiable with no specific failure code (mediator structure
    itself fails).

    Subset-minimal search: smallest W first, both strategies return the
    first valid W found (not all W — keeps output compact).

    Reference: Pearl 2001 "Direct and indirect effects"; VanderWeele
    2015 ch.2.
    """
    from itertools import combinations

    # Structural prerequisite: mediator must actually mediate
    mediator_ok = (
        x in graph and y in graph and m in graph
        and x != y and x != m and y != m
        and nx.has_path(graph, x, m)
        and nx.has_path(graph, m, y)
    )

    if not mediator_ok:
        empty = MediationAttempt(
            identifiable=False,
            adjustment=frozenset(),
            failed_condition=None,
        )
        return MediationResult(
            mediator=m,
            nde_nie=empty,
            cde=empty,
            mediator_valid=False,
        )

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    # Candidate W pool for NDE/NIE: excludes X, Y, M, and X-descendants
    # (M4 pre-filter — saves redundant checks).
    x_desc = nx.descendants(graph, x)
    nde_w_pool = [
        n for n in graph.nodes
        if n != x and n != y and n != m and n not in x_desc
    ]

    # Candidate W pool for CDE: excludes X, Y, M, X-descendants, and
    # M-descendants (C2 pre-filter).
    m_desc = nx.descendants(graph, m)
    cde_w_pool = [
        n for n in graph.nodes
        if n != x and n != y and n != m
        and n not in x_desc and n not in m_desc
    ]

    # Search NDE/NIE (smallest W first)
    nde_attempt = _search_mediation_adjustment(
        graph, x, y, m, nde_w_pool, bidir_eff,
        max_adjustment_size, _check_nde_nie_with_w,
        default_failed="M4",
    )

    # Search CDE (smallest W first)
    cde_attempt = _search_mediation_adjustment(
        graph, x, y, m, cde_w_pool, bidir_eff,
        max_adjustment_size, _check_cde_with_w,
        default_failed="C1",
    )

    return MediationResult(
        mediator=m,
        nde_nie=nde_attempt,
        cde=cde_attempt,
        mediator_valid=True,
    )


def _search_mediation_adjustment(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    w_pool: list[Atom],
    bidirected: "BidirectedEdgeSet",
    max_size: int,
    checker,
    default_failed: str,
) -> MediationAttempt:
    """Subset-enumerate W up to ``max_size`` and return the first
    candidate passing ``checker``. If none pass, report the failure
    mode of the smallest attempted W (or ``default_failed`` when the
    pool is pre-filtered and empty).
    """
    from itertools import combinations

    last_failure = default_failed
    upper_size = min(max_size, len(w_pool))

    for size in range(0, upper_size + 1):
        for combo in combinations(w_pool, size):
            w = frozenset(combo)
            failure = checker(graph, x, y, m, w, bidirected)
            if failure is None:
                return MediationAttempt(
                    identifiable=True,
                    adjustment=w,
                    failed_condition=None,
                )
            # Track the failure seen at the smallest W; when the pool is
            # pre-filtered (M4/C2 already enforced), the failure must be
            # a structural one (M1/M2/M3 or C1).
            if size == 0:
                last_failure = failure

    return MediationAttempt(
        identifiable=False,
        adjustment=frozenset(),
        failed_condition=last_failure,
    )


# =====================================================================
# Phase 2.latent S2 — ADMG primitives (solver-only, no scheduler hookup)
#
# m-separation and c-component decomposition on a mixed graph. Charter:
# PHASE_2_LATENT_CHARTER.md §3, §7 (S2). These primitives are deliberately
# independent — scheduler / graph_projection / verifier do NOT call them
# in S2. S3 wires the runtime, S4 wires the verifier with an independent
# reimplementation.
# =====================================================================

BidirectedEdgeSet = frozenset[frozenset[Atom]]


def bidirected_from_ground(ground_statements) -> BidirectedEdgeSet:
    """Extract the set of bidirected edges from a list of ground
    statements (post-instantiation). Returns an empty frozenset when
    the program declares no bidirected edges — keeps pre-ADMG dispatch
    paths unaffected.

    Each returned element is a 2-element frozenset — the pair is
    unordered, matching the undirected semantics of bidirectedness.
    Parallel duplicate declarations on the same pair collapse into
    one entry (per charter §4.2 first-pass simplification).
    """
    pairs: list[frozenset[Atom]] = []
    for stmt in ground_statements:
        if isinstance(stmt, BidirectedStatement):
            pairs.append(frozenset({stmt.left, stmt.right}))
    return frozenset(pairs)


def _has_arrowhead_at(
    mg: "nx.MultiGraph",
    edge_key: tuple,
    v: Atom,
) -> bool:
    """Does the edge identified by ``edge_key`` (a (u, w, k) triple in
    the path-multi-graph) have an arrowhead at node ``v``?

    - Directed edge src → dst: arrowhead at dst, arrowtail at src.
    - Bidirected edge A ↔ B: arrowhead at both endpoints.

    The multi-graph annotates each edge with ``kind`` plus (for directed
    edges) the original ``src`` / ``dst`` so orientation can be recovered
    from the undirected path view.
    """
    u, w, k = edge_key
    data = mg.edges[u, w, k]
    if data["kind"] == "bidirected":
        return True
    # directed: arrowhead at the original dst
    return data["dst"] == v


def _build_admg_path_graph(
    directed: "nx.DiGraph",
    bidirected: BidirectedEdgeSet,
) -> "nx.MultiGraph":
    """Collapse an ADMG into a MultiGraph suitable for simple-path
    enumeration. Each directed edge becomes one undirected edge tagged
    ``kind='directed'`` with ``src``/``dst``; each bidirected edge
    becomes one undirected edge tagged ``kind='bidirected'``.

    Nodes from both edge sets are included so a bidirected endpoint that
    is absent from the directed graph still participates in paths.
    """
    mg = nx.MultiGraph()
    mg.add_nodes_from(directed.nodes())
    for pair in bidirected:
        mg.add_nodes_from(pair)
    for src, dst in directed.edges():
        mg.add_edge(src, dst, kind="directed", src=src, dst=dst)
    for pair in bidirected:
        a, b = tuple(pair)
        mg.add_edge(a, b, kind="bidirected")
    return mg


def is_m_connected(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> bool:
    """True iff at least one open m-path connects ``left`` and ``right``
    in the ADMG (directed edges from ``graph`` plus ``bidirected`` pairs)
    under ``conditioning``.

    A path is open iff every intermediate node is unblocked. A node V is
    a collider on the path iff both incident edge ends have arrowheads
    at V (directed-incoming or bidirected). Blocking rule:

    - non-collider: blocked iff V ∈ conditioning
    - collider: blocked iff V and all its directed-descendants are
      disjoint from conditioning

    Directed descendants use only the directed edges of the ADMG
    (bidirected edges do not contribute to ancestry).

    When ``bidirected`` is empty, the answer must agree with
    ``is_d_connected`` — verified in the S2 regression tests.
    """
    if left == right:
        return False

    mg = _build_admg_path_graph(graph, bidirected)
    if left not in mg or right not in mg:
        return False

    c_set = frozenset(conditioning)

    for edge_path in nx.all_simple_edge_paths(mg, left, right):
        nodes: list[Atom] = [left]
        for u, w, _k in edge_path:
            nodes.append(w if nodes[-1] == u else u)

        open_path = True
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            ahead_from_prev = _has_arrowhead_at(mg, edge_path[i - 1], v)
            ahead_from_next = _has_arrowhead_at(mg, edge_path[i], v)
            is_collider = ahead_from_prev and ahead_from_next
            if is_collider:
                activated = {v} | nx.descendants(graph, v) if v in graph else {v}
                if activated.isdisjoint(c_set):
                    open_path = False
                    break
            else:
                if v in c_set:
                    open_path = False
                    break

        if open_path:
            return True

    return False


def conditioned_collider_opens_path(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    left: Atom,
    right: Atom,
    conditioning: "frozenset[Atom] | tuple[Atom, ...]",
    collider: Atom,
) -> bool:
    """True iff some OPEN m-path between ``left`` and ``right`` (given
    ``conditioning``) stays open because ``collider`` activates a collider on
    it — i.e. ``collider`` IS a collider on the path, or a conditioned
    descendant of one. This is the selection-bias / collider-conditioning
    signal: conditioning on ``collider`` opens a (non-causal) path between the
    intervention and the outcome, so a conditional effect estimate carries
    collider-induced bias.

    Unlike a directed-ancestor test, this sees colliders whose arms are
    bidirected (latent common causes) — e.g. M-bias ``X<->W<->Y`` (What If
    Fig 7.4) — and colliders activated through a conditioned descendant
    (Fig 8.2), not only the direct ``X->W<-Y`` shape (Fig 8.1).
    """
    if left == right or collider == left or collider == right:
        return False
    mg = _build_admg_path_graph(graph, bidirected)
    if left not in mg or right not in mg:
        return False
    c_set = frozenset(conditioning)
    if collider not in c_set:
        return False

    for edge_path in nx.all_simple_edge_paths(mg, left, right):
        nodes: list[Atom] = [left]
        for u, w, _k in edge_path:
            nodes.append(w if nodes[-1] == u else u)

        open_path = True
        collider_activated_by_target = False
        for i in range(1, len(nodes) - 1):
            v = nodes[i]
            ahead_from_prev = _has_arrowhead_at(mg, edge_path[i - 1], v)
            ahead_from_next = _has_arrowhead_at(mg, edge_path[i], v)
            is_collider = ahead_from_prev and ahead_from_next
            if is_collider:
                descendants = nx.descendants(graph, v) if v in graph else set()
                activated = {v} | descendants
                if activated.isdisjoint(c_set):
                    open_path = False
                    break
                # Does conditioning on `collider` specifically activate this
                # collider v (v is the collider itself, or `collider` is a
                # conditioned descendant of v)?
                if collider == v or collider in descendants:
                    collider_activated_by_target = True
            else:
                if v in c_set:
                    open_path = False
                    break

        if open_path and collider_activated_by_target:
            return True

    return False


def m_separated(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
    left: Atom,
    right: Atom,
    conditioning: tuple[Atom, ...],
) -> bool:
    """Convenience: ``not is_m_connected(...)``.

    Two distinct nodes are m-separated iff no open m-path connects them.
    ``left == right`` returns True (a node is trivially separated from
    itself — there is no non-trivial path).
    """
    if left == right:
        return True
    return not is_m_connected(graph, bidirected, left, right, conditioning)


def c_components(
    graph: nx.DiGraph,
    bidirected: BidirectedEdgeSet,
) -> tuple[frozenset[Atom], ...]:
    """Partition the ADMG node set into c-components.

    A c-component is an equivalence class of nodes connected by paths
    of **bidirected** edges only. Directed edges do not merge
    components. Nodes untouched by any bidirected edge form singleton
    components.

    Returns a tuple of frozensets covering exactly the union of
    directed-graph nodes and bidirected-edge endpoints. Order is not
    semantically meaningful — callers should not depend on it.

    When ``bidirected`` is empty, every node is its own c-component.
    """
    nodes: set[Atom] = set(graph.nodes())
    for pair in bidirected:
        nodes |= set(pair)

    parent: dict[Atom, Atom] = {n: n for n in nodes}

    def find(x: Atom) -> Atom:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x: Atom, y: Atom) -> None:
        rx, ry = find(x), find(y)
        if rx != ry:
            parent[rx] = ry

    for pair in bidirected:
        a, b = tuple(pair)
        union(a, b)

    groups: dict[Atom, set[Atom]] = {}
    for n in nodes:
        r = find(n)
        groups.setdefault(r, set()).add(n)

    return tuple(frozenset(g) for g in groups.values())
