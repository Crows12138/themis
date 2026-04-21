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
    return tuple(minimal)


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
