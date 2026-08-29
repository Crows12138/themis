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

from typing import Callable, Hashable, NamedTuple, TypeVar

import networkx as nx

from ..types import Atom, BidirectedStatement

# What a node is depends on who built the graph. The scheduler keys its
# graphs by ``Atom``; the data-gap report builds a predicate-level ADMG
# keyed by ``str``. The path routines below never look inside a node —
# they compare them and index the graph with them — so they are written
# over whichever type the caller's graph uses, and this states that the
# four node arguments must agree with each other.
_Node = TypeVar("_Node", bound=Hashable)


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


class FrontDoorSet(NamedTuple):
    """A mediator set together with the baseline covariates it needs held.

    An empty ``covariates`` is Pearl's textbook front-door criterion. A
    non-empty one is the GENERALIZED front-door criterion (Fulcher,
    Shpitser, Marealle & Tchetgen Tchetgen, JRSS-B 2020), whose estimand

        Σ_c P(c) Σ_z P(z | x, c) Σ_x' P(x' | c) P(y | x', z, c)

    collapses to the textbook front-door formula at C = ∅. The two are
    one species with one parameter, not two criteria.
    """

    mediators: frozenset[Atom]
    covariates: frozenset[Atom]


def _atom_order(atoms) -> tuple:
    """Deterministic order for a set of atoms, by predicate."""
    return tuple(sorted(a.predicate for a in atoms))


def _front_door_criterion_holds(
    graph: nx.DiGraph,
    bidirected: "BidirectedEdgeSet",
    x: Atom,
    y: Atom,
    directed_paths_xy: tuple[tuple[Atom, ...], ...],
    z: frozenset[Atom],
    c: frozenset[Atom],
) -> bool:
    """The front-door criterion for mediators ``z`` holding covariates ``c``:

    (FD1) every directed path X → ... → Y passes through some z ∈ Z
    (FD2) no back-door path from X to any z ∈ Z is open given C
    (FD3) every back-door path from any z ∈ Z to Y is blocked by {X} ∪ C

    One statement of the conditions, two enumerators over it:
    ``front_door_sets`` passes ``c = frozenset()`` and gets Pearl's
    textbook conditions back verbatim, ``generalized_front_door_sets``
    searches over ``c`` as well. The conditions are the part that could
    drift apart between the two, so they are written once.
    """
    for path in directed_paths_xy:
        if not (set(path[1:-1]) & z):
            return False
    blocked_to_y = c | {x}
    for zi in z:
        if _is_admg_backdoor_connected(graph, bidirected, x, zi, c):
            return False
        if _is_admg_backdoor_connected(graph, bidirected, zi, y, blocked_to_y):
            return False
    return True


def _front_door_pools(
    graph: nx.DiGraph, x: Atom, y: Atom,
) -> "tuple[list[Atom], list[Atom], tuple[tuple[Atom, ...], ...]] | None":
    """The two candidate pools and the directed X → Y paths, or ``None``
    when the graph cannot exhibit a front door at all.

    Mediators must lie on a directed path X → ... → Y. Covariates are
    held at their own marginal P(c), so they must be unaffected by the
    treatment — non-descendants of X, which (Y being a descendant of X
    whenever such a path exists) also rules out everything downstream of
    the outcome. The two pools are therefore disjoint by construction.
    """
    if x not in graph or y not in graph or x == y:
        return None
    descendants_x = nx.descendants(graph, x)
    mediators = list((descendants_x & nx.ancestors(graph, y)) - {x, y})
    if not mediators:
        return None
    directed_all = tuple(tuple(p) for p in nx.all_simple_paths(graph, x, y))
    if not directed_all:
        return None
    covariates = [
        n for n in graph.nodes
        if n not in descendants_x and n != x and n != y
    ]
    return mediators, covariates, directed_all


def generalized_front_door_sets(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    bidirected: "BidirectedEdgeSet | None" = None,
) -> tuple[FrontDoorSet, ...]:
    """Subset-minimal (mediator set, covariate set) pairs satisfying the
    generalized front-door criterion relative to (X, Y).

    Pearl's textbook criterion is the C = ∅ face of this one, and
    ``front_door_sets`` returns exactly that face. What the generalized
    criterion additionally covers is the graph where a mediator is
    confounded with the treatment by something OBSERVED — C → X and
    C → M — which the textbook conditions reject outright (FD2 asks for
    no open back-door from X to M under EMPTY conditioning, and
    X ← C → M is one) even though holding C restores every condition.

    Minimality is over the pair under the componentwise order: a pair is
    kept unless an already-admissible pair is a subset in both
    coordinates. Enumeration runs by total size, so a dominating pair is
    always in hand before the pair it dominates is reached.

    Searching covariate subsets as well as mediator subsets costs more
    than ``front_door_sets`` does. This is called where a pattern is
    being NAMED for a reader, not from the routing cascade that answers
    the query.
    """
    from itertools import combinations

    pools = _front_door_pools(graph, x, y)
    if pools is None:
        return ()
    mediator_pool, covariate_pool, directed_all = pools
    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    minimal: list[FrontDoorSet] = []
    for total in range(1, len(mediator_pool) + len(covariate_pool) + 1):
        for zsize in range(1, min(total, len(mediator_pool)) + 1):
            csize = total - zsize
            if csize > len(covariate_pool):
                continue
            for zc in combinations(mediator_pool, zsize):
                z = frozenset(zc)
                for cc in combinations(covariate_pool, csize):
                    c = frozenset(cc)
                    if any(e.mediators <= z and e.covariates <= c
                           for e in minimal):
                        continue
                    if _front_door_criterion_holds(
                        graph, bidir_eff, x, y, directed_all, z, c,
                    ):
                        minimal.append(FrontDoorSet(z, c))
    minimal.sort(key=lambda fd: (
        len(fd.mediators), len(fd.covariates),
        _atom_order(fd.mediators), _atom_order(fd.covariates),
    ))
    return tuple(minimal)


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

    pools = _front_door_pools(graph, x, y)
    if pools is None:
        return ()
    candidates, _covariates, directed_all = pools
    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()
    nothing_held: frozenset[Atom] = frozenset()

    def satisfies(z: frozenset[Atom]) -> bool:
        return _front_door_criterion_holds(
            graph, bidir_eff, x, y, directed_all, z, nothing_held,
        )

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


class VectorIVCandidate(NamedTuple):
    """A valid instrument for a treatment VECTOR.

    ``relevant_to`` names the treatments this instrument is m-connected to
    given ``conditioning``. It is reported, not required: an Anderson-Rubin
    region is valid whether or not the instruments move anything, and a
    candidate relevant to nothing still contributes a degree of freedom to the
    test — which is a cost, not an error, and one only the caller can price.
    """

    instrument: Atom
    conditioning: frozenset[Atom]
    relevant_to: frozenset[Atom]


def vector_iv_sets(
    graph: nx.DiGraph,
    treatments: "tuple[Atom, ...]",
    y: Atom,
    *,
    bidirected: "BidirectedEdgeSet | None" = None,
    max_conditioning_size: int = 3,
) -> tuple[VectorIVCandidate, ...]:
    """Find instruments valid for the whole treatment vector at once.

    The scalar :func:`iv_sets` asks three questions of a candidate; this asks
    the same exogeneity + exclusion question of the SET, and reports the
    relevance question rather than filtering on it:

    - **exogeneity + exclusion, jointly**: in the graph with every edge
      *leaving any treatment* removed, Z is m-separated from Y given W. Cutting
      all the treatments at once is what makes this the vector condition and
      not a conjunction of scalar ones: an instrument that reaches Y through
      ANOTHER treatment in the vector is excluded here and would be rejected by
      the scalar test, correctly for that test — the other treatment is a
      confounder there and part of the intervention here.
    - **relevance**: recorded per treatment in ``relevant_to``. The AR region's
      coverage does not depend on it; what it predicts is whether the region
      comes back bounded.

    ``W`` is drawn from nodes that are not a treatment, Y, Z, or a descendant
    of any treatment — conditioning on a mediator of any treatment in the
    vector breaks the same thing it breaks in the scalar case.

    Returns candidates sorted by (|W|, instrument, W), with only subset-minimal
    valid W per instrument.

    Reference: Anderson & Rubin (1949) for what the instruments are used for;
    Brito & Pearl (2002) Theorem 2 for the graphical condition, read on the
    treatment set.
    """
    from itertools import combinations

    x_set = set(treatments)
    if not x_set or y in x_set or any(t not in graph for t in x_set):
        return ()
    if y not in graph:
        return ()

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    mutilated = graph.copy()
    for t in x_set:
        mutilated.remove_edges_from(list(mutilated.out_edges(t)))

    descendants: set[Atom] = set()
    for t in x_set:
        descendants |= nx.descendants(graph, t)

    z_candidates = [v for v in graph.nodes if v not in x_set and v != y]

    results: list[VectorIVCandidate] = []
    for z in z_candidates:
        w_pool = [
            v for v in graph.nodes
            if v not in x_set and v != y and v != z and v not in descendants
        ]
        minimal_ws: list[frozenset[Atom]] = []
        upper_size = min(max_conditioning_size, len(w_pool))
        for size in range(0, upper_size + 1):
            for combo in combinations(w_pool, size):
                w = frozenset(combo)
                if any(existing <= w for existing in minimal_ws):
                    continue
                if is_m_connected(mutilated, bidir_eff, z, y, tuple(w)):
                    continue
                minimal_ws.append(w)

        for w in minimal_ws:
            relevant = frozenset(
                t for t in treatments
                if is_m_connected(graph, bidir_eff, z, t, tuple(w))
            )
            results.append(VectorIVCandidate(
                instrument=z, conditioning=w, relevant_to=relevant))

    results.sort(
        key=lambda c: (
            len(c.conditioning),
            c.instrument.predicate,
            tuple(sorted(a.predicate for a in c.conditioning)),
        )
    )
    return tuple(results)


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


def _set_m_connected(
    graph: nx.DiGraph,
    bidirected: "BidirectedEdgeSet",
    sources: frozenset[Atom],
    dst: Atom,
    conditioning: frozenset[Atom],
) -> bool:
    """ADMG analogue of :func:`_set_d_connected`: True iff some node in
    ``sources`` has an open m-path to ``dst`` given ``conditioning`` in the
    ADMG (directed ``graph`` + ``bidirected`` latent edges). Other source
    nodes on a path are ordinary intermediate nodes, NOT implicitly
    conditioned. When ``bidirected`` is empty this reduces to
    ``_set_d_connected`` (the empty-bidirected invariant of
    ``is_m_connected``)."""
    cond = tuple(conditioning)
    for s in sources:
        if s == dst:
            continue
        if is_m_connected(graph, bidirected, s, dst, cond):
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

    ADMG (latent-confounded) case: when ``bidirected`` is non-empty the
    proper-non-causal-path blocking check (ii) switches from d-separation
    to **m-separation** in the proper back-door graph — the generalized
    (treatment-SET) back-door / adjustment criterion for ADMGs (van der
    Zander, Liśkiewicz & Textor 2019; Perković et al. 2018, the same
    complete criterion the section header cites). Condition (i) — the
    forbidden region — stays directed-only (a proper causal path and its
    descendants are defined by directed edges; a bidirected edge is a
    latent common cause, not causal). The empty / ``None`` bidirected case
    is bit-identical to the directed-only implementation (regression). The
    criterion is SOUND — any returned ``Z`` makes the joint g-formula
    Σ_z P(Y|X,Z=z)P(z) equal P(Y|do(X)) — but only covers the
    adjustment-identifiable subset; latent-confounded joint effects that
    are ID-identifiable but not adjustment-identifiable (front-door /
    c-component for sets) return ``()`` and the caller honestly refuses.
    """
    from itertools import combinations

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

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()
    if bidir_eff:
        def blocks_all(z: frozenset[Atom]) -> bool:
            return not _set_m_connected(g_pbd, bidir_eff, x_set, y, z | given_set)
    else:
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
    - ``failed_condition``: the condition that stopped the candidate
      adjustment set that got FURTHEST — "M1" / "M2" / "M3" / "M4" for
      the natural effects, "C1" / "C2" for the controlled one — or None
      on success. Not "the first condition that blocked identification":
      failure is a property of the search, not of one W, and the label
      only says something about the graph once it is the best any
      candidate managed. See ``_search_mediation_adjustment``.
    """

    identifiable: bool
    adjustment: frozenset[Atom]
    failed_condition: str | None


class MediationResult(NamedTuple):
    """Identification result for mediation quantities (X, M, Y).

    Both NDE/NIE and CDE are attempted independently. A given graph may
    support CDE only, or both, and never the natural effects without the
    controlled one. That last is a theorem, not an observation: with the
    same W, M1 already gives C1's X arm (G\\bar{XM} has a subset of
    G\\bar{X}'s edges, so a path open there is open there too), and M3
    gives C1's M arm (X has no outgoing edge in G\\bar{XM}, so it cannot
    be a non-collider on any M–Y path, so dropping it from the
    conditioning set can only close paths); the two routes search one
    pool and M4 and C2 forbid the same nodes. Counted as well as argued —
    ``tests/test_which_gate_is_weaker_is_a_count.py`` enumerates every
    labelled DAG on four nodes and finds the cell empty.
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


#: The order the NDE/NIE conditions are named in, and the order they are
#: checked in. See ``_check_nde_nie_with_w`` for why the order is load-bearing.
_NDE_NIE_ORDER: tuple[str, ...] = ("M1", "M2", "M3", "M4")

#: Its CDE twin. Two members rather than four because the controlled effect
#: fixes M by intervention instead of holding it at its natural distribution,
#: so the cross-world conditions do not arise.
_CDE_ORDER: tuple[str, ...] = ("C1", "C2")


def _forbidden_for_nde(
    graph: nx.DiGraph, x: Atom, ms: "frozenset[Atom]",
) -> set[Atom]:
    """Nodes W may not contain if the natural effects are to be identified:
    the descendants of X (Pearl's M4, and its joint twin).

    The searcher and the checker both ask here, so the rule that decides
    which candidates are admissible and the rule that names the failure
    cannot drift apart.
    """
    return set(nx.descendants(graph, x))


def _forbidden_for_cde(
    graph: nx.DiGraph, x: Atom, ms: "frozenset[Atom]",
) -> set[Atom]:
    """Its CDE twin: the ordinary back-door restriction for the JOINT
    intervention do(X, M) forbids a descendant of X and a descendant of any
    mediator alike.

    Under this module's mediator precondition — a directed X → … → M path
    must exist for every mediator — every descendant of M is already a
    descendant of X, so this set always equals ``_forbidden_for_nde``'s.
    That is measured, not assumed: over every labelled DAG on four nodes
    with a valid mediator the two coincide with no exception. The union is
    written out anyway because it is the criterion — the coincidence is a
    consequence of the precondition, not of what a controlled effect needs
    — and ``tests/test_which_gate_is_weaker_is_a_count.py`` pins it as a
    consequence, so relaxing the precondition surfaces there rather than
    silently changing what CDE accepts.
    """
    forbidden = set(nx.descendants(graph, x))
    for member in ms:
        forbidden |= nx.descendants(graph, member)
    return forbidden


class _Route(NamedTuple):
    """One identification route, bound to a graph.

    Everything that does not depend on the candidate W is computed once
    when the route is built — the mutilated graphs the separations are
    read off, and the set the membership condition refuses — so the search
    varies only W, which is the one thing it is searching over. The
    checkers used to rebuild both per candidate, which was invisible while
    the pool was pre-filtered down to a handful; the second pass
    enumerates the pool the first one filters, and there it is the
    difference between a constant and a cubic.

    Handing the check and the forbidden set over together is also what
    keeps the rule that admits a candidate and the rule that names its
    refusal from drifting apart: a route states both, in one place, once.
    """

    check: "Callable[[frozenset[Atom]], str | None]"
    forbidden: set[Atom]
    order: tuple[str, ...]


def _nde_nie_route(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    bidirected: "BidirectedEdgeSet",
) -> _Route:
    """Pearl 2001's four conditions for the natural effects.

    ``check`` returns None iff all four hold for W, else the first to fail
    in the theorem's own order.

    The order is what the label means. M4 is a membership test on W and
    the other three are separations, so checking M4 first is cheaper — but
    then a W that is inadmissible AND leaves a backdoor wide open would be
    labelled "M4", and nothing could tell it from a W that satisfied every
    separation and was rejected only for reaching into X's descendants.
    ``_search_mediation_adjustment`` reports the label of the candidate
    that got FURTHEST, and that is a statement about the graph only while
    "furthest" is measured along one fixed order.
    """
    g_bar_x = _mutilate_outgoing(graph, x)
    g_bar_m = _mutilate_outgoing(graph, m)
    forbidden = _forbidden_for_nde(graph, x, frozenset({m}))

    def check(w: frozenset[Atom]) -> str | None:
        w_tuple = tuple(w)

        # M1: Y ⊥ X | W in G\bar{X} (all X→Y backdoors blocked by W)
        if is_m_connected(g_bar_x, bidirected, x, y, w_tuple):
            return "M1"

        # M2: M ⊥ X | W in G\bar{X} (all X→M backdoors blocked by W)
        if is_m_connected(g_bar_x, bidirected, x, m, w_tuple):
            return "M2"

        # M3: Y ⊥ M | X, W in G\bar{M} (M→Y backdoors blocked by {X}∪W)
        if is_m_connected(g_bar_m, bidirected, m, y, tuple(w | {x})):
            return "M3"

        # M4: W contains no descendants of X
        if w & forbidden:
            return "M4"

        return None

    return _Route(check=check, forbidden=forbidden, order=_NDE_NIE_ORDER)


def _cde_route(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    m: Atom,
    bidirected: "BidirectedEdgeSet",
) -> _Route:
    """The CDE(m) back-door adjustment conditions.

    ``check`` returns None iff both hold for W, else the first to fail, in
    the order they are named.

    C1: in G\\bar{XM} (outgoing edges from both X and M removed), Y is
        m-separated from X given W AND Y is m-separated from M given W.
    C2: W contains no descendants of X or of M.

    C2 does not admit one candidate M4 would refuse. It is the same
    restriction: see ``_forbidden_for_cde`` for why the mediator
    precondition collapses the two, and why the union is still written
    out. What separates the routes is C1 against M1–M3, not this.
    """
    g_bar_xm = _mutilate_outgoing(graph, x)
    g_bar_xm.remove_edges_from(list(g_bar_xm.out_edges(m)))
    forbidden = _forbidden_for_cde(graph, x, frozenset({m}))

    def check(w: frozenset[Atom]) -> str | None:
        w_tuple = tuple(w)

        # C1: in G\bar{XM}, Y m-sep from both X and M given W
        if is_m_connected(g_bar_xm, bidirected, x, y, w_tuple):
            return "C1"
        if is_m_connected(g_bar_xm, bidirected, m, y, w_tuple):
            return "C1"

        # C2: W excludes descendants of X and of M
        if w & forbidden:
            return "C2"

        return None

    return _Route(check=check, forbidden=forbidden, order=_CDE_ORDER)


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
       backdoor adjustment on (X, M) jointly works for Y, which is
       strictly more often: over every labelled DAG on four nodes with a
       valid mediator, 256 graphs identify the controlled effect and not
       the natural ones, and none the other way round.

    An intermediate confounder — an X-descendant affecting both M and Y —
    sinks BOTH. It is the set that would block the M–Y backdoor, and both
    routes refuse it for descending from X. This slice adjusts on one W;
    identifying a controlled effect there needs the longitudinal
    g-formula, which is a different method and not attempted here. What
    the reader is told is M4 (resp. C2), naming the restriction rather
    than the open path, because the restriction is the part they can
    argue with.

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

    # One candidate pool: every node that is neither an endpoint nor the
    # mediator. Which of them a route may actually use is that route's own
    # membership condition, asked through the same function the checker
    # asks — so the rule that admits a candidate and the rule that names
    # its refusal cannot come apart.
    w_pool = [n for n in graph.nodes if n != x and n != y and n != m]

    # Search NDE/NIE (smallest W first)
    nde_attempt = _search_mediation_adjustment(
        _nde_nie_route(graph, x, y, m, bidir_eff), w_pool,
        max_adjustment_size,
    )

    # Search CDE (smallest W first)
    cde_attempt = _search_mediation_adjustment(
        _cde_route(graph, x, y, m, bidir_eff), w_pool, max_adjustment_size,
    )

    return MediationResult(
        mediator=m,
        nde_nie=nde_attempt,
        cde=cde_attempt,
        mediator_valid=True,
    )


def _search_mediation_adjustment(
    route: _Route,
    w_pool: list[Atom],
    max_size: int,
) -> MediationAttempt:
    """Two questions, answered by two passes.

    The first asks whether any ADMISSIBLE W identifies the quantity, and
    it is the only pass that runs when the answer is yes.

    The second runs only on failure and asks something else: which
    condition stopped the candidate that got furthest. It searches the
    pool WITHOUT the membership restriction, because the candidate that
    gets furthest is routinely one the restriction rules out — an
    intermediate confounder is exactly the set that satisfies every
    separation and is refused only for descending from X. Naming that is
    the diagnosis a reader can act on, and it used to be unreachable:
    reporting the failure of the smallest W meant reporting the failure
    of the EMPTY set, which contains no descendant of anything, so "M4"
    and "C2" could not be said however true they were. Over every
    labelled DAG on five nodes with a valid mediator the old rule named
    only M1, M3 and C1 — three of the six conditions the contract
    declares, and each of the other three already had a sentence waiting
    for a reader.

    Every candidate is checked at most once. The first pass already saw
    the admissible ones, and it keeps the furthest they got, so the second
    only visits the candidates the membership restriction hid — which are
    the ones it is there for.

    ``route.order`` is the sequence the conditions are named in;
    "furthest" means furthest along it, so it has to be the same order
    the route checks them in.
    """
    from itertools import combinations

    check, forbidden, order = route
    furthest = order[0]
    rank = 0

    admissible = [n for n in w_pool if n not in forbidden]
    for size in range(0, min(max_size, len(admissible)) + 1):
        for combo in combinations(admissible, size):
            w = frozenset(combo)
            failure = check(w)
            if failure is None:
                return MediationAttempt(
                    identifiable=True,
                    adjustment=w,
                    failed_condition=None,
                )
            if order.index(failure) > rank:
                furthest, rank = failure, order.index(failure)

    # Only the candidates the first pass hid are left to look at, so when
    # it hid none there is no second pass.
    hidden = forbidden.intersection(w_pool)
    upper = min(max_size, len(w_pool)) if hidden else 0
    for size in range(1, upper + 1):
        for combo in combinations(w_pool, size):
            if not hidden.intersection(combo):
                continue  # admissible, and the first pass already saw it
            failure = check(frozenset(combo))
            if failure is None or order.index(failure) <= rank:
                continue
            furthest, rank = failure, order.index(failure)
            # Nothing can get further than the last condition: a candidate
            # refused there satisfied every one before it.
            if rank == len(order) - 1:
                return MediationAttempt(
                    identifiable=False,
                    adjustment=frozenset(),
                    failed_condition=furthest,
                )

    return MediationAttempt(
        identifiable=False,
        adjustment=frozenset(),
        failed_condition=furthest,
    )


# =====================================================================
# Joint multi-mediator natural effects — VanderWeele-Vansteelandt 2014.
# The natural direct/indirect effects through a SET of mediators taken as
# one block. Treating the set as a block is what makes the decomposition
# identifiable without knowing the causal ORDERING among the mediators: a
# recanting witness INSIDE the set does not break the joint split (only a
# path-SPECIFIC split through one member would). The CDE-for-a-set (holding
# the whole block fixed at a reference level) is a distinct quantity and is
# identified here too, by the ordinary back-door criterion for the joint
# intervention do(X, M_set) — it needs strictly WEAKER conditions than the
# joint natural effects (no X-M_set no-confounding requirement).
# =====================================================================


class MediationJointResult(NamedTuple):
    """Identification result for the JOINT natural effects through a
    mediator SET (X, {M_1..M_k}, Y).

    - ``mediators``: the mediator set queried.
    - ``nde_nie``: the joint NDE/NIE ``MediationAttempt`` (identifiable +
      adjustment W + failing condition on the smallest attempted W).
    - ``cde``: the CDE-for-a-set ``MediationAttempt`` — back-door
      identifiability of the controlled direct effect holding the whole
      block fixed (weaker conditions than ``nde_nie``).
    - ``mediator_set_valid``: False if some M_j does not mediate X→Y
      (no X→M_j directed path or no M_j→Y directed path) or the set is
      degenerate (empty, or contains X / Y).
    """

    mediators: frozenset[Atom]
    nde_nie: MediationAttempt
    mediator_set_valid: bool
    # CDE-for-a-set: back-door identifiability of the controlled direct
    # effect that holds the WHOLE mediator block fixed (the joint
    # intervention do(X, M_set)). Identifiable under strictly weaker
    # conditions than nde_nie — a LATENT X<->M_j edge that sinks the joint
    # natural effects still leaves the controlled effect adjustable. Default
    # is the non-identifiable empty attempt so callers that predate the CDE
    # branch stay valid.
    cde: MediationAttempt = MediationAttempt(
        identifiable=False, adjustment=frozenset(), failed_condition=None,
    )


def _mutilate_outgoing_set(graph: nx.DiGraph, nodes) -> nx.DiGraph:
    """Return a copy of ``graph`` with all edges leaving EVERY node in
    ``nodes`` removed — the block-mediator analog of ``_mutilate_outgoing``
    (Pearl's ``G_{\\overline{M_set}}``). Cutting every set member's
    outgoing edges is what removes the intra-set confounding path a
    recanting witness would otherwise open.
    """
    g = graph.copy()
    for n in nodes:
        g.remove_edges_from(list(g.out_edges(n)))
    return g


def _nde_nie_joint_route(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    ms: "frozenset[Atom]",
    bidirected: "BidirectedEdgeSet",
) -> _Route:
    """The joint NDE/NIE conditions for the mediator SET ``ms``.

    ``check`` returns None iff all hold for W, else the first to fail, in
    the same order as the single-mediator twin and for the same reason.

    The single-mediator four conditions (Pearl 2001, Theorem 2) with M
    replaced by the vector M_set (VanderWeele-Vansteelandt 2014):

      M1: Y _|_ X | W        in G_Xbar.
      M2: M_set _|_ X | W     in G_Xbar        (checked per member).
      M3: Y _|_ M_set | X, W  in G_Msetbar     (ALL set outgoing removed).
      M4: W contains no descendant of X.

    Treating the set as a block is what tolerates a recanting witness
    INSIDE the set: cutting every set member's outgoing edges removes the
    intra-set confounding path, so M3 passes here where the single-mediator
    check on the confounded member alone does not identify anything.
    """
    g_bar_x = _mutilate_outgoing(graph, x)
    g_bar_ms = _mutilate_outgoing_set(graph, ms)
    forbidden = _forbidden_for_nde(graph, x, ms)

    def check(w: frozenset[Atom]) -> str | None:
        w_tuple = tuple(w)

        # M1: Y _|_ X | W in G_Xbar.
        if is_m_connected(g_bar_x, bidirected, x, y, w_tuple):
            return "M1"

        # M2: each M_j _|_ X | W in G_Xbar.
        for m in ms:
            if is_m_connected(g_bar_x, bidirected, x, m, w_tuple):
                return "M2"

        # M3: each M_j _|_ Y | X, W in G_Msetbar (all set outgoing removed).
        xw_tuple = tuple(w | {x})
        for m in ms:
            if is_m_connected(g_bar_ms, bidirected, m, y, xw_tuple):
                return "M3"

        # M4: W contains no descendant of X.
        if w & forbidden:
            return "M4"

        return None

    return _Route(check=check, forbidden=forbidden, order=_NDE_NIE_ORDER)


def _cde_set_route(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    ms: "frozenset[Atom]",
    bidirected: "BidirectedEdgeSet",
) -> _Route:
    """The CDE(m*) back-door conditions for the mediator SET ``ms``.

    ``check`` returns None iff both hold for W, else the first failing
    label.

    The single-mediator CDE conditions (``_cde_route``) with M
    replaced by the vector M_set — the ordinary back-door criterion for the
    JOINT intervention do(X, M_1..M_k) that holds the whole block fixed:

      C1: in G\\bar{X,M_set} (outgoing edges of X AND every M_j removed),
          Y is m-separated from X given W AND from each M_j given W.
      C2: W contains no descendant of X or of any M_j.

    Holding every mediator fixed is what makes CDE-for-a-set identifiable in
    strictly MORE graphs than the joint NDE/NIE: the CDE never needs the
    X–M_set no-confounding condition (M2), so a LATENT X<->M_j edge that
    sinks the joint natural effects still leaves the controlled effect
    adjustable. That containment is counted rather than recalled — over
    every labelled DAG on {X, Y, M1, M2} with a valid mediator set, no graph
    identifies the joint natural effects without also identifying the
    controlled one, and the reverse happens in ninety. Back-door only,
    mirroring the single-mediator CDE — a post-treatment (intermediate)
    confounder of the mediator-outcome edge is honestly reported
    non-identifiable here (it needs the longitudinal g-formula, out of
    scope), and C2 is then the condition the reader is told about.
    """
    g_bar = _mutilate_outgoing_set(graph, ms | {x})
    forbidden = _forbidden_for_cde(graph, x, ms)

    def check(w: frozenset[Atom]) -> str | None:
        w_tuple = tuple(w)

        # C1: in G\bar{X,M_set}, Y m-sep from X and from each M_j given W.
        if is_m_connected(g_bar, bidirected, x, y, w_tuple):
            return "C1"
        for m in ms:
            if is_m_connected(g_bar, bidirected, m, y, w_tuple):
                return "C1"

        # C2: W excludes descendants of X and of any set member.
        if w & forbidden:
            return "C2"

        return None

    return _Route(check=check, forbidden=forbidden, order=_CDE_ORDER)


def mediation_sets_joint(
    graph: nx.DiGraph,
    x: Atom,
    y: Atom,
    mediators: "frozenset[Atom] | tuple[Atom, ...]",
    *,
    bidirected: "BidirectedEdgeSet | None" = None,
    max_adjustment_size: int = 3,
) -> MediationJointResult:
    """Identify the JOINT natural effects (joint NDE / joint NIE) AND the
    CDE-for-a-set through a mediator SET {M_1..M_k}, treated as one block.

    Two strategies, attempted independently (mirroring the single-mediator
    ``mediation_sets``):

    1. **Joint NDE/NIE** — the natural-effect block decomposition of the
       total effect into "through the set" and "not through the set"
       (Pearl's four conditions with M a vector).
    2. **CDE-for-a-set** — the controlled direct effect holding the whole
       block fixed at a reference level, by the ordinary back-door criterion
       for the joint intervention do(X, M_set). Weaker conditions than the
       natural effects: it may identify where the joint NDE/NIE fails (e.g.
       under a latent X-M confounder).

    Structural prerequisite: every M_j must mediate — a directed
    ``X -> ... -> M_j`` and ``M_j -> ... -> Y`` path must both exist — the
    set must be non-empty, and no member may be X or Y. Otherwise
    ``mediator_set_valid`` is False and the attempt is non-identifiable
    with no specific failure code.

    Subset-minimal search over the adjustment set W (smallest first);
    returns the first W satisfying the joint conditions. The W pool is
    every node that is neither an endpoint nor a mediator; each route
    then applies its own membership condition to it.

    Reference: VanderWeele & Vansteelandt 2014 "Mediation analysis with
    multiple mediators" (Epidemiologic Methods); Pearl 2001 is the k=1
    special case.
    """
    ms = frozenset(mediators)

    mediator_set_ok = (
        len(ms) >= 1
        and x in graph and y in graph and x != y
        and x not in ms and y not in ms
        and all(m in graph for m in ms)
        and all(
            nx.has_path(graph, x, m) and nx.has_path(graph, m, y)
            for m in ms
        )
    )

    empty_attempt = MediationAttempt(
        identifiable=False, adjustment=frozenset(), failed_condition=None,
    )
    if not mediator_set_ok:
        return MediationJointResult(
            mediators=ms,
            nde_nie=empty_attempt,
            mediator_set_valid=False,
            cde=empty_attempt,
        )

    bidir_eff: BidirectedEdgeSet = bidirected or frozenset()

    w_pool = [
        n for n in graph.nodes
        if n != x and n != y and n not in ms
    ]

    # The subset searcher varies only W, and a route has already bound
    # itself to the graph — so the joint routes drop into it unchanged.
    attempt = _search_mediation_adjustment(
        _nde_nie_joint_route(graph, x, y, ms, bidir_eff), w_pool,
        max_adjustment_size,
    )

    # CDE-for-a-set: back-door for the joint do(X, M_set), which forbids a
    # descendant of any mediator as well as of X.
    cde_attempt = _search_mediation_adjustment(
        _cde_set_route(graph, x, y, ms, bidir_eff), w_pool,
        max_adjustment_size,
    )

    return MediationJointResult(
        mediators=ms,
        nde_nie=attempt,
        mediator_set_valid=True,
        cde=cde_attempt,
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


FeedbackLoopSet = frozenset[frozenset[Atom]]


def feedback_from_ground(ground_statements) -> FeedbackLoopSet:
    """The declared reciprocal loops, as unordered pairs.

    Shaped like :func:`bidirected_from_ground` and kept apart from it on
    purpose. A bidirected edge says an unobserved common cause; a feedback
    loop says both directions are causal. They have the same consequence
    for one thing — the treatment is not exogenous — and different
    consequences for everything else, which is why folding one into the
    other would be a quiet over-identification rather than a shortcut: the
    front-door criterion holds in the reduction and does not hold under the
    loop, whose mediator sits INSIDE it.
    """
    from ..types import FeedbackLoop

    return frozenset(
        frozenset({stmt.left, stmt.right})
        for stmt in ground_statements
        if isinstance(stmt, FeedbackLoop)
    )


def _loop_key(loop: "frozenset[Atom]") -> tuple:
    return tuple(sorted(str(a) for a in loop))


def loops_reaching_the_estimand(
    graph: nx.DiGraph,
    loops: FeedbackLoopSet,
    *,
    x: Atom,
    y: Atom,
) -> "tuple[frozenset[Atom], ...]":
    """Which declared loops could have corrupted what this estimand reads.

    A loop somewhere else in the model is not this query's problem, and a
    rule that treated every declared loop as fatal would make the
    declaration too expensive to make — the reader would learn to leave it
    out, which is the silence this whole mechanism exists to end.

    The criterion is one sentence: **a loop that can influence neither the
    treatment nor the outcome cannot corrupt the joint distribution the
    estimand is computed from; one that can, may.** So the graph is
    augmented with every declared loop's two edges and the question is
    plain reachability to ``x`` or ``y``.

    The harm is NOT a fact about the mutilated graph, which is what makes
    this rule read the graph as declared. Intervening does cut the arm
    coming back into the treatment — that is exactly what ``do`` means —
    and the answer is wrong anyway, because the OBSERVATIONAL joint the
    adjustment formula reads was generated by the cycle and does not
    factorize the way the DAG says. A rule written on the mutilated graph
    would clear the simultaneous-equations case, which is the one case
    everybody agrees is broken.

    **Conservative on purpose, and the cost is real.** "Could have
    corrupted" is not "did": a loop between two covariates, or between the
    treatment and a dead-end child of it, leaves the treatment exogenous
    and the adjustment answer correct, and this rule withdraws it anyway.
    Sharpening that needs the algebra of each shape, and the error it
    would risk points the other way — a silently wrong number instead of a
    refusal with three routes attached. The routes say what to do about a
    loop that turns out not to matter: withdraw it, and the withdrawal is
    then a premise the reader took deliberately.

    Plain reachability, never d-separation: the augmented graph is cyclic,
    and d-separation is a DAG notion. Under linearity it does extend to
    cyclic graphs (Spirtes 1995), but nothing here needs that, and a
    reachability question answered by reachability cannot quietly become
    wrong when the linearity premise is withdrawn.
    """
    if not loops or x == y:
        return ()

    augmented = graph.copy()
    for loop in loops:
        left, right = tuple(loop)
        for node in (left, right):
            if node not in augmented:
                augmented.add_node(node, atom=node)
        augmented.add_edge(left, right)
        augmented.add_edge(right, left)
    if y not in augmented or x not in augmented:
        return ()

    reaching = [
        loop for loop in loops
        if any(
            end in (x, y) or bool(
                {x, y} & nx.descendants(augmented, end))
            for end in loop if end in augmented
        )
    ]
    return tuple(sorted(reaching, key=_loop_key))


def _has_arrowhead_at(
    mg: "nx.MultiGraph",
    edge_key: tuple,
    v: _Node,
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
    bidirected: "frozenset[frozenset[_Node]]",
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
    bidirected: "frozenset[frozenset[_Node]]",
    left: _Node,
    right: _Node,
    conditioning: "frozenset[_Node] | tuple[_Node, ...]",
    collider: _Node,
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
        nodes: list[_Node] = [left]
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
