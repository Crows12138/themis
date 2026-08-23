"""Independent audit of a Meek orientation-propagation result
(2026-07-17, interactive equivalence-class resolution — Phase 1).

The producer (``estimation.orientation.propagate_orientations``) takes a CPDAG
plus direction constraints and returns the Meek closure, the constraints it
could not apply (conflicts with the data), and the per-edge provenance. This
verifier re-derives all of it from the recorded inputs — the input CPDAG and
the constraints — with a SECOND, standalone transcription of Meek's rules
R1-R4 and the constraint-application / conflict-detection logic. It never calls
the producer and never imports causal-learn. (R4 matters: once a constraint is
applied, R1-R3 alone are incomplete, so a verifier that stopped at R3 would
wrongly reject the producer's genuinely-forced R4 orientations.)

What it guarantees, given the recorded inputs:
- the ``oriented`` set is exactly the Meek closure (soundness — no orientation
  that is not forced; completeness — no forced orientation missing);
- ``remaining_undirected`` is exactly what stays undetermined;
- ``conflicts`` names exactly the inputs that contradict the data — the
  orientation constraints that do (a data-established orientation, a non-edge, an
  earlier constraint, or a cycle), the asserted adjacencies that contradict the
  data's independence structure (a plain ``contradicts_independence``, or an
  ``undermines_collider`` naming the exact collider apexes whose unshielded
  premise the assertion would break), AND the asserted absences (edges to drop)
  that contradict the data's dependence structure (a plain
  ``contradicts_dependence``, or an ``undermines_collider`` naming the apex when
  the edge dropped is a data collider arm) — a producer that silently applied a
  data-contradicting answer, or under-reported which colliders an asserted edge
  undermines, is caught;
- every provenance entry is well-formed and its claimed rule genuinely fires
  in the returned graph, and its ``roots`` are actual applied constraints.

Trust boundary (stated honestly): the recorded input CPDAG (skeleton +
colliders) is taken as given — this function audits the PROPAGATION, not the
upstream discovery that produced the CPDAG (that is ``verify_markov_blanket`` /
the discovery caveats' job). Given the input CPDAG and constraints, the closure
and the conflicts are provably correct.
"""
from __future__ import annotations

from .errors import VerificationError


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _require_list(value: object, message: str) -> list:
    """Same guard as ``_require(isinstance(value, list), message)``, but it
    hands the checked value back so the caller holds a ``list`` rather than
    the untyped ``dict.get`` result."""
    if not isinstance(value, list):
        raise VerificationError(message)
    return value


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _is_ancestor(directed: set, x: str, y: str) -> bool:
    if x == y:
        return True
    children: dict = {}
    for (u, v) in directed:
        children.setdefault(u, []).append(v)
    stack = [x]; seen = {x}
    while stack:
        node = stack.pop()
        for nxt in children.get(node, ()):
            if nxt == y:
                return True
            if nxt not in seen:
                seen.add(nxt); stack.append(nxt)
    return False


def _forces(directed: set, undirected: set, adj: dict, a: str, b: str):
    """Second transcription of Meek R1-R4 (see the producer for the rule
    statements). Returns the rule name that forces ``a→b`` or ``None``."""
    for z in adj[a]:
        if z != b and (z, a) in directed and z not in adj[b]:
            return "R1"
    for z in adj[a]:
        if (a, z) in directed and (z, b) in directed:
            return "R2"
    cand = [z for z in adj[a] if _pair(a, z) in undirected and (z, b) in directed]
    for i, z1 in enumerate(cand):
        for z2 in cand[i + 1:]:
            if z2 not in adj[z1]:
                return "R3"
    for c in adj[a]:
        if c == b or _pair(a, c) not in undirected or c in adj[b]:
            continue
        for d in adj[b]:
            if (d, b) in directed and (c, d) in directed and d in adj[a]:
                return "R4"
    return None


def _recompute(nodes, input_directed, input_undirected, constraints):
    """Independently rebuild (oriented, remaining, conflicts) from the inputs."""
    node_set = set(nodes)
    D = set(input_directed)
    U = {_pair(a, b) for (a, b) in input_undirected}
    adj: dict = {n: set() for n in nodes}
    for (a, b) in D:
        adj[a].add(b); adj[b].add(a)
    for (a, b) in U:
        adj[a].add(b); adj[b].add(a)

    conflicts = []
    for (a, b) in constraints:
        if a not in node_set or b not in node_set:
            conflicts.append(("unknown_node", a, b)); continue
        p = _pair(a, b)
        if (a, b) in D:
            continue
        if (b, a) in D:
            conflicts.append(("contradicts_data_orientation", a, b)); continue
        if p not in U:
            conflicts.append(("non_adjacent_pair", a, b)); continue
        if _is_ancestor(D, b, a):
            conflicts.append(("creates_cycle", a, b)); continue
        U.discard(p); D.add((a, b))

    # ``sorted`` and not ``list``: the visiting order is part of what is being
    # transcribed, not an implementation choice. Two rules can be ready on the
    # same edge, and the one that reaches it first signs the provenance this
    # verifier re-derives — ``U`` holds tuples of strings, so an unsorted walk
    # would make that a per-process coin flip on both sides.
    changed = True
    while changed:
        changed = False
        for p in sorted(U):
            a, b = p
            if _forces(D, U, adj, a, b) and not _is_ancestor(D, b, a):
                D.add((a, b)); U.discard(p); changed = True
                continue
            if _forces(D, U, adj, b, a) and not _is_ancestor(D, a, b):
                D.add((b, a)); U.discard(p); changed = True
    return D, U, adj, conflicts


def _extension_block(nodes, directed: set, undirected: set, adj: dict) -> list:
    """Second transcription of Dor & Tarjan's consistent-extension test (see
    the producer for the statement): the ``(apex, p, q)`` witnesses that this
    PDAG is the pattern of no DAG, empty if it is one.

    Transcribed rather than imported like everything else here, and it earns
    that more than most: the claim it decides — that the caller was asked a
    question with two live answers — is the one #428 found the system making
    without checking.
    """
    live = set(nodes)
    remaining = {tuple(sorted(e)) for e in undirected}
    while live:
        stuck = []
        chosen = None
        for x in sorted(live):
            near = adj[x] & live
            if any((x, y) in directed for y in near):
                continue
            blocked = [(x, y, z) for y in sorted(near)
                       if tuple(sorted((x, y))) in remaining
                       for z in sorted(near) if z != y and z not in adj[y]]
            if blocked:
                stuck.extend(blocked)
            else:
                chosen = x
                break
        if chosen is None:
            return stuck
        for y in adj[chosen] & live:
            remaining.discard(tuple(sorted((chosen, y))))
        live.discard(chosen)
    return []


def _unshielded_colliders(directed: set, adj: dict) -> set:
    """Every ``p→c←q`` with ``p`` and ``q`` non-adjacent, as ``(p, q, c)``."""
    parents: dict = {}
    for (u, v) in directed:
        parents.setdefault(v, []).append(u)
    out = set()
    for c, ps in parents.items():
        ordered = sorted(ps)
        for i, p in enumerate(ordered):
            for q in ordered[i + 1:]:
                if q not in adj[p]:
                    out.add((p, q, c))
    return out


def _grouped(witnesses, reason):
    """``(apex, p, q)`` witnesses as one ``(reason, p, q, apexes)`` row per
    non-adjacent pair — the shape the producer's conflicts are compared in."""
    by_pair: dict = {}
    for (c, p, q) in witnesses:
        by_pair.setdefault(_pair(p, q), set()).add(c)
    return [(reason, p, q, tuple(sorted(apexes)))
            for (p, q), apexes in sorted(by_pair.items())]


def _forced_collider_conflicts(nodes, input_directed, input_undirected, closed, adj):
    """Both ways a graph can fail to be the pattern of a DAG, as compared rows.

    They are two different facts and the reader is told them differently. The
    input can already be unrealisable — no DAG has this skeleton with these
    colliders, whatever anyone answers — and that is decided on the input
    alone. Or the input was fine and an ANSWER made a collider the data never
    reported, which is decided by comparing the closure's colliders with the
    input's.
    """
    was = _unshielded_colliders(set(input_directed), adj)
    new = sorted(_unshielded_colliders(closed, adj) - was)
    rows = []
    blocked = _extension_block(nodes, set(input_directed),
                               set(input_undirected), adj)
    if blocked:
        # One row however many witnesses — being stuck is one fact about the
        # graph, and the producer reports the least witness for concreteness.
        apex, p, q = min(blocked)
        pq = _pair(p, q)
        rows.append(("no_consistent_extension", pq[0], pq[1], (apex,)))
    return rows + _grouped([(c, p, q) for (p, q, c) in new],
                           "forces_unreported_collider")


def _adjacency_conflicts(node_set, input_directed, adj, asserted):
    """Independent second transcription of the CI-independence-side conflict
    detection (see the producer). Returns tuples ``(reason, a, b, colliders)``
    with ``a<=b`` and ``colliders`` a sorted tuple (empty unless
    ``undermines_collider``)."""
    directed = set(input_directed)
    conflicts = []
    seen = set()
    for (a, b) in asserted:
        p = _pair(a, b)
        if p in seen:
            continue
        seen.add(p)
        if a not in node_set or b not in node_set:
            conflicts.append(("unknown_node", p[0], p[1], ()))
            continue
        if b in adj[a]:
            continue
        colliders = tuple(sorted(
            c for c in node_set if (a, c) in directed and (b, c) in directed))
        if colliders:
            conflicts.append(("undermines_collider", p[0], p[1], colliders))
        else:
            conflicts.append(("contradicts_independence", p[0], p[1], ()))
    return conflicts


def _asserted_absence_conflicts(node_set, input_directed, adj, asserted):
    """Independent second transcription of the drop-edge (asserted-non-adjacency)
    conflict detection (see the producer). Returns ``(reason, a, b, colliders)``
    with ``a<=b``; ``colliders`` is the sorted apex tuple, non-empty only when the
    edge asserted absent is a data collider arm."""
    directed = set(input_directed)
    conflicts = []
    seen = set()
    for (a, b) in asserted:
        p = _pair(a, b)
        if p in seen:
            continue
        seen.add(p)
        if a not in node_set or b not in node_set:
            conflicts.append(("unknown_node", p[0], p[1], ()))
            continue
        if b not in adj[a]:
            continue  # already non-adjacent — agrees with the data
        apexes = tuple(sorted(
            head for (tail, head) in ((a, b), (b, a))
            if (tail, head) in directed
            and any(x != tail and (x, head) in directed for x in node_set)))
        if apexes:
            conflicts.append(("undermines_collider", p[0], p[1], apexes))
        else:
            conflicts.append(("contradicts_dependence", p[0], p[1], ()))
    return conflicts


_RULE_NAMES = {"collider_input", "constraint", "R1", "R2", "R3", "R4"}


def verify_orientation_propagation(result: dict) -> None:
    """Independently audit an orientation-propagation result dict (the artifact
    from ``orientation_to_dict``).

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, a closure that disagrees with the independent recomputation,
    a mis-reported conflict set, or an ill-formed / unjustified provenance
    entry.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(
        result.get("kind") == "orientation_propagation",
        f"not an orientation_propagation result (kind={result.get('kind')!r})",
    )
    nodes = _require_list(result.get("nodes"), "nodes must be a non-empty list")
    _require(bool(nodes), "nodes must be a non-empty list")
    _require(len(set(nodes)) == len(nodes), "duplicate node names")
    node_set = set(nodes)

    def _edges(key, *, ordered_pairs):
        raw = result.get(key)
        _require(isinstance(raw, list), f"{key} must be a list")
        out = []
        for e in raw:
            _require(
                isinstance(e, list) and len(e) == 2 and e[0] in node_set and e[1] in node_set,
                f"{key} entry {e!r} is not a pair of known nodes",
            )
            _require(e[0] != e[1], f"{key} has a self-loop {e!r}")
            out.append((e[0], e[1]))
        return out

    input_directed = _edges("input_directed", ordered_pairs=True)
    input_undirected = _edges("input_undirected", ordered_pairs=False)
    constraints = _edges("constraints", ordered_pairs=True)
    claimed_oriented = _edges("oriented", ordered_pairs=True)
    claimed_remaining = _edges("remaining_undirected", ordered_pairs=False)

    # input well-formedness (mirrors the producer's OrientationError guards)
    dir_set = set(input_directed)
    for (a, b) in input_directed:
        _require((b, a) not in dir_set, f"input pair {{{a}, {b}}} oriented both ways")
    und_set = {_pair(a, b) for (a, b) in input_undirected}
    _require(len(und_set) == len(input_undirected), "duplicate input undirected edge")
    for (a, b) in input_undirected:
        _require(
            (a, b) not in dir_set and (b, a) not in dir_set,
            f"input pair {{{a}, {b}}} is both directed and undirected",
        )

    # asserted adjacencies (may name unknown nodes — those become conflicts —
    # so they are NOT routed through _edges, which requires known nodes)
    raw_asserted = _require_list(
        result.get("asserted_adjacencies", []), "asserted_adjacencies must be a list"
    )
    asserted = []
    for e in raw_asserted:
        _require(isinstance(e, list) and len(e) == 2,
                 f"asserted_adjacencies entry {e!r} is not a pair")
        _require(e[0] != e[1], f"asserted_adjacencies has a self-loop {e!r}")
        asserted.append((e[0], e[1]))

    raw_absences = _require_list(
        result.get("asserted_absences", []), "asserted_absences must be a list"
    )
    absences = []
    for e in raw_absences:
        _require(isinstance(e, list) and len(e) == 2,
                 f"asserted_absences entry {e!r} is not a pair")
        _require(e[0] != e[1], f"asserted_absences has a self-loop {e!r}")
        absences.append((e[0], e[1]))

    # --- independent recomputation --------------------------------------------
    D, U, adj, conflicts = _recompute(nodes, input_directed, input_undirected, constraints)
    adj_conflicts = _adjacency_conflicts(node_set, input_directed, adj, asserted)
    abs_conflicts = _asserted_absence_conflicts(node_set, input_directed, adj, absences)
    collider_conflicts = _forced_collider_conflicts(
        nodes, input_directed, input_undirected, D, adj)

    claimed_D = set(claimed_oriented)
    _require(len(claimed_D) == len(claimed_oriented), "duplicate edge in 'oriented'")
    _require(
        claimed_D == D,
        f"oriented set disagrees with the independent Meek closure: "
        f"producer-only {sorted(claimed_D - D)}, closure-only {sorted(D - claimed_D)}",
    )
    claimed_U = {_pair(a, b) for (a, b) in claimed_remaining}
    _require(
        claimed_U == U,
        f"remaining_undirected disagrees with the recomputation: "
        f"producer-only {sorted(claimed_U - U)}, recompute-only {sorted(U - claimed_U)}",
    )

    # --- conflicts (orientation-side and CI-independence-side, partitioned) ---
    claimed_conflicts = _require_list(result.get("conflicts"), "conflicts must be a list")
    claimed_orient = []
    claimed_adj = []
    claimed_abs = []
    claimed_forced = []
    for c in claimed_conflicts:
        _require(isinstance(c, dict) and "reason" in c, f"ill-formed conflict entry {c!r}")
        if "constraint" in c:
            pair = c["constraint"]
            _require(isinstance(pair, list) and len(pair) == 2,
                     f"bad conflict constraint {pair!r}")
            claimed_orient.append((c["reason"], pair[0], pair[1]))
        elif "assertion" in c:
            pair = c["assertion"]
            _require(isinstance(pair, list) and len(pair) == 2,
                     f"bad conflict assertion {pair!r}")
            p = _pair(pair[0], pair[1])
            claimed_adj.append((c["reason"], p[0], p[1], tuple(sorted(c.get("colliders", [])))))
        elif "absence" in c:
            pair = c["absence"]
            _require(isinstance(pair, list) and len(pair) == 2,
                     f"bad conflict absence {pair!r}")
            p = _pair(pair[0], pair[1])
            claimed_abs.append((c["reason"], p[0], p[1], tuple(sorted(c.get("colliders", [])))))
        elif "forced_collider" in c:
            pair = c["forced_collider"]
            _require(isinstance(pair, list) and len(pair) == 2,
                     f"bad conflict forced_collider {pair!r}")
            _require(c["reason"] in ("no_consistent_extension",
                                     "forces_unreported_collider"),
                     f"forced_collider entry with reason {c['reason']!r}")
            p = _pair(pair[0], pair[1])
            claimed_forced.append(
                (c["reason"], p[0], p[1], tuple(sorted(c.get("colliders", [])))))
        else:
            _require(False,
                     f"conflict entry {c!r} has none of 'constraint' / 'assertion' / "
                     f"'absence' / 'forced_collider'")
    _require(
        sorted(claimed_orient) == sorted(conflicts),
        f"orientation-conflict set disagrees with the recomputation: "
        f"producer-only {sorted(set(claimed_orient) - set(conflicts))}, "
        f"recompute-only {sorted(set(conflicts) - set(claimed_orient))}",
    )
    _require(
        sorted(claimed_adj) == sorted(adj_conflicts),
        f"adjacency-conflict set disagrees with the recomputation: "
        f"producer-only {sorted(set(claimed_adj) - set(adj_conflicts))}, "
        f"recompute-only {sorted(set(adj_conflicts) - set(claimed_adj))}",
    )
    _require(
        sorted(claimed_abs) == sorted(abs_conflicts),
        f"absence-conflict set disagrees with the recomputation: "
        f"producer-only {sorted(set(claimed_abs) - set(abs_conflicts))}, "
        f"recompute-only {sorted(set(abs_conflicts) - set(claimed_abs))}",
    )
    _require(
        sorted(claimed_forced) == sorted(collider_conflicts),
        f"forced-collider set disagrees with the recomputation: "
        f"producer-only {sorted(set(claimed_forced) - set(collider_conflicts))}, "
        f"recompute-only {sorted(set(collider_conflicts) - set(claimed_forced))}",
    )

    # --- provenance -----------------------------------------------------------
    prov = _require_list(result.get("provenance"), "provenance must be a list")
    _require(len(prov) == len(claimed_D), "provenance must have one entry per oriented edge")
    applied_constraints = {(a, b) for (a, b) in constraints
                           if (a, b) in D and (b, a) not in set(input_directed)}
    covered = set()
    for entry in prov:
        _require(isinstance(entry, dict), f"provenance entry {entry!r} is not a dict")
        a, b, rule = entry.get("from"), entry.get("to"), entry.get("rule")
        _require((a, b) in claimed_D, f"provenance names non-oriented edge {(a, b)!r}")
        _require((a, b) not in covered, f"duplicate provenance for {(a, b)!r}")
        covered.add((a, b))
        _require(rule in _RULE_NAMES, f"unknown provenance rule {rule!r}")
        roots = entry.get("roots")
        _require(isinstance(roots, list), f"provenance roots for {(a, b)!r} must be a list")
        root_set = {tuple(r) for r in roots}
        if rule == "collider_input":
            _require((a, b) in dir_set, f"{(a, b)!r} marked collider_input but not in input_directed")
            _require(not root_set, f"collider_input edge {(a, b)!r} must have no roots")
        elif rule == "constraint":
            _require((a, b) in applied_constraints, f"{(a, b)!r} marked constraint but was not applied")
            _require(root_set == {(a, b)}, f"constraint edge {(a, b)!r} roots must be itself")
        else:
            # a Meek rule: it must genuinely fire for this edge in the final graph
            _require(
                _forces(D, U, adj, a, b) is not None,
                f"{(a, b)!r} marked {rule} but no Meek rule forces it in the closure",
            )
            _require(
                root_set.issubset(applied_constraints),
                f"{(a, b)!r} roots {sorted(root_set)} are not all applied constraints",
            )
    _require(covered == claimed_D, "provenance does not cover every oriented edge")
