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
- ``conflicts`` names exactly the constraints that contradict the data
  (a data-established orientation, a non-edge, or an earlier constraint) —
  a producer that silently applied a data-contradicting answer is caught;
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

    changed = True
    while changed:
        changed = False
        for p in list(U):
            a, b = p
            if _forces(D, U, adj, a, b) and not _is_ancestor(D, b, a):
                D.add((a, b)); U.discard(p); changed = True
                continue
            if _forces(D, U, adj, b, a) and not _is_ancestor(D, a, b):
                D.add((b, a)); U.discard(p); changed = True
    return D, U, adj, conflicts


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
    nodes = result.get("nodes")
    _require(isinstance(nodes, list) and nodes, "nodes must be a non-empty list")
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

    # --- independent recomputation --------------------------------------------
    D, U, adj, conflicts = _recompute(nodes, input_directed, input_undirected, constraints)

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

    # --- conflicts ------------------------------------------------------------
    claimed_conflicts = result.get("conflicts")
    _require(isinstance(claimed_conflicts, list), "conflicts must be a list")
    claimed_norm = []
    for c in claimed_conflicts:
        _require(isinstance(c, dict) and "constraint" in c and "reason" in c,
                 f"ill-formed conflict entry {c!r}")
        pair = c["constraint"]
        _require(isinstance(pair, list) and len(pair) == 2, f"bad conflict constraint {pair!r}")
        claimed_norm.append((c["reason"], pair[0], pair[1]))
    _require(
        sorted(claimed_norm) == sorted(conflicts),
        f"conflict set disagrees with the recomputation: "
        f"producer-only {sorted(set(claimed_norm) - set(conflicts))}, "
        f"recompute-only {sorted(set(conflicts) - set(claimed_norm))}",
    )

    # --- provenance -----------------------------------------------------------
    prov = result.get("provenance")
    _require(isinstance(prov, list), "provenance must be a list")
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
