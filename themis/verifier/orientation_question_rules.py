"""Independent audit of a compiled orientation question set
(2026-07-17, interactive equivalence-class resolution — Phase 2).

The producer (``estimation.orientation_questions.compile_orientation_questions``)
turns a Phase 1 orientation result into a ranked question set: the conflicts to
adjudicate, then one leverage-ranked orientation question per still-undetermined
edge. This verifier re-derives all of it from the recorded inputs — the post-
propagation CPDAG (``oriented`` + ``remaining_undirected``) and the constraints —
with a SECOND, standalone transcription of Meek's rules R1-R4. It re-runs each
edge's two cascades itself; it never calls the producer or ``propagate_orientations``.

What it certifies, given the recorded CPDAG:

- **Conflicts are echoed exactly.** Re-deriving both the constraint application
  and the CI-side adjacency check independently, every conflict — an orientation
  constraint that contradicts the data, or an asserted adjacency that contradicts
  its independence structure — becomes exactly one conflict question, and none is
  invented.
- **Every leverage number is honest.** For each orientation question the claimed
  ``leverage`` (best-case cascade), ``guaranteed`` (worst-case cascade), and
  ``unlocks`` (edges determined regardless of the answer) equal the two Meek
  closures recomputed here from the recorded CPDAG.
- **The set is complete and well-formed.** There is exactly one orientation
  question per remaining undirected edge, none invented on a non-edge or a
  determined edge, and the orientation questions are ordered by non-increasing
  leverage (conflicts first).
- **The input CPDAG is internally consistent** for this purpose: acyclic, no
  two-way orientation, and every remaining edge genuinely two-way (a favourable
  answer determines it, so ``guaranteed`` ≥ 1) — a remaining edge that was
  actually forced would mean Phase 1 under-propagated.

Trust boundary (stated honestly): the recorded CPDAG is taken as given — this
audits the QUESTION COMPILATION, not the Phase 1 propagation that produced the
CPDAG (that is ``verify_orientation_propagation``'s job). The verifier's Meek
transcription and the producer's engine share the same rule set; a brute-force
equivalence-class enumeration in the test suite is the genuinely independent
oracle that guards against a rule-set bug shared by both.
"""
from __future__ import annotations

from collections import defaultdict

from .errors import VerificationError


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def _pair(a: str, b: str):
    return (a, b) if a <= b else (b, a)


def _acyclic(directed: set, nodes) -> bool:
    children: dict = {}
    for (u, v) in directed:
        children.setdefault(u, []).append(v)
    color: dict = {}

    def dfs(u) -> bool:
        color[u] = 0
        for w in children.get(u, ()):
            c = color.get(w)
            if c == 0:
                return False
            if c is None and not dfs(w):
                return False
        color[u] = 1
        return True

    return all(color.get(u) is not None or dfs(u) for u in nodes)


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
    """Second transcription of Meek R1-R4 — does the current graph force a→b?"""
    for z in adj[a]:
        if z != b and (z, a) in directed and z not in adj[b]:
            return True
    for z in adj[a]:
        if (a, z) in directed and (z, b) in directed:
            return True
    cand = [z for z in adj[a] if _pair(a, z) in undirected and (z, b) in directed]
    for i, z1 in enumerate(cand):
        for z2 in cand[i + 1:]:
            if z2 not in adj[z1]:
                return True
    for c in adj[a]:
        if c == b or _pair(a, c) not in undirected or c in adj[b]:
            continue
        for d in adj[b]:
            if (d, b) in directed and (c, d) in directed and d in adj[a]:
                return True
    return False


def _closure_cascade(nodes, D0: set, U0: set, adj: dict, u_set: set, answer):
    """Meek closure of the single ``answer`` on the CPDAG (D0, U0); returns the
    originally-undirected edges it determines (the answer's cascade)."""
    a, b = answer
    D = set(D0)
    U = set(U0)
    D.add((a, b)); U.discard(_pair(a, b))
    changed = True
    while changed:
        changed = False
        for p in list(U):
            x, y = p
            if _forces(D, U, adj, x, y) and not _is_ancestor(D, y, x):
                D.add((x, y)); U.discard(p); changed = True
                continue
            if _forces(D, U, adj, y, x) and not _is_ancestor(D, x, y):
                D.add((y, x)); U.discard(p); changed = True
    return {tuple(sorted(e)) for e in D if frozenset(e) in u_set}


def _recompute_conflicts(nodes, input_directed, input_undirected, constraints):
    """Independent second transcription of the constraint application, returning
    the conflict tuples ``(reason, a, b)`` — the same logic Phase 1 uses."""
    node_set = set(nodes)
    D = set(input_directed)
    U = {_pair(a, b) for (a, b) in input_undirected}
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
    return conflicts


def _adjacency_conflict_pairs(node_set, input_directed, adj, asserted):
    """Independent second transcription of the CI-side conflict detection, at the
    granularity a conflict question carries — ``(reason, a, b)`` with ``a<=b``.
    (The collider apexes an ``undermines_collider`` names are audited in
    ``verify_orientation_propagation``; here every conflict is one question.)"""
    directed = set(input_directed)
    out = []
    seen = set()
    for (a, b) in asserted:
        p = _pair(a, b)
        if p in seen:
            continue
        seen.add(p)
        if a not in node_set or b not in node_set:
            out.append(("unknown_node", p[0], p[1]))
            continue
        if b in adj[a]:
            continue
        if any((a, c) in directed and (b, c) in directed for c in node_set):
            out.append(("undermines_collider", p[0], p[1]))
        else:
            out.append(("contradicts_independence", p[0], p[1]))
    return out


def verify_orientation_questions(result: dict) -> None:
    """Independently audit an orientation-question-set dict (the artifact from
    ``question_set_to_dict``).

    Returns ``None`` on accept; raises ``VerificationError`` on any structural
    inconsistency, a fabricated / dropped conflict question, a leverage /
    guaranteed / unlocks number that disagrees with the independent Meek closures,
    a missing or spurious orientation question, or a mis-ordered ranking.
    """
    _require(isinstance(result, dict), "result must be a dict")
    _require(result.get("kind") == "orientation_question_set",
             f"not an orientation_question_set (kind={result.get('kind')!r})")
    nodes = result.get("nodes")
    _require(isinstance(nodes, list) and nodes, "nodes must be a non-empty list")
    _require(len(set(nodes)) == len(nodes), "duplicate node names")
    node_set = set(nodes)

    def _edges(key):
        raw = result.get(key)
        _require(isinstance(raw, list), f"{key} must be a list")
        out = []
        for e in raw:
            _require(isinstance(e, list) and len(e) == 2
                     and e[0] in node_set and e[1] in node_set,
                     f"{key} entry {e!r} is not a pair of known nodes")
            _require(e[0] != e[1], f"{key} has a self-loop {e!r}")
            out.append((e[0], e[1]))
        return out

    input_directed = _edges("input_directed")
    input_undirected = _edges("input_undirected")
    constraints = _edges("constraints")
    raw_asserted = result.get("asserted_adjacencies", [])
    _require(isinstance(raw_asserted, list), "asserted_adjacencies must be a list")
    asserted = []
    for e in raw_asserted:
        _require(isinstance(e, list) and len(e) == 2,
                 f"asserted_adjacencies entry {e!r} is not a pair")
        _require(e[0] != e[1], f"asserted_adjacencies has a self-loop {e!r}")
        asserted.append((e[0], e[1]))
    D0 = set(_edges("oriented"))
    U0 = {_pair(a, b) for (a, b) in _edges("remaining_undirected")}
    u_set = {frozenset(e) for e in U0}

    # --- the CPDAG the questions are about ------------------------------------
    for (a, b) in D0:
        _require((b, a) not in D0, f"oriented pair {{{a}, {b}}} points both ways")
    _require(_acyclic(D0, nodes), "oriented set is cyclic")
    for p in U0:
        _require(p not in D0 and (p[1], p[0]) not in D0,
                 f"pair {p} is both oriented and remaining")
    adj: dict = defaultdict(set)
    for (a, b) in D0:
        adj[a].add(b); adj[b].add(a)
    for (a, b) in U0:
        adj[a].add(b); adj[b].add(a)

    questions = result.get("questions")
    _require(isinstance(questions, list), "questions must be a list")
    for q in questions:
        _require(isinstance(q, dict) and "kind" in q, f"ill-formed question {q!r}")

    # --- conflict questions: exact echo of the recomputed conflicts -----------
    # Both the orientation-constraint conflicts and the CI-side adjacency
    # conflicts become one conflict question each; the granularity here is
    # (reason, a, b) (the collider apexes are audited in the propagation verifier).
    recomputed = (
        _recompute_conflicts(nodes, input_directed, input_undirected, constraints)
        + _adjacency_conflict_pairs(node_set, input_directed, adj, asserted)
    )
    claimed_conflicts = []
    for q in questions:
        if q.get("kind") != "conflict":
            continue
        edge = q.get("edge")
        _require(isinstance(edge, list) and len(edge) == 2, f"bad conflict edge {edge!r}")
        claimed_conflicts.append((q.get("reason"), edge[0], edge[1]))
    _require(sorted(claimed_conflicts) == sorted(recomputed),
             f"conflict questions disagree with the recomputation: "
             f"producer-only {sorted(set(claimed_conflicts) - set(recomputed))}, "
             f"recompute-only {sorted(set(recomputed) - set(claimed_conflicts))}")

    # --- conflicts must precede orientation questions -------------------------
    kinds = [q.get("kind") for q in questions]
    _require("conflict" not in kinds[kinds.count("conflict"):],
             "a conflict question is ranked below an orientation question")

    # --- orientation questions: one per remaining edge, honest leverage -------
    orient = [q for q in questions if q.get("kind") == "orientation"]
    seen = set()
    prev_leverage = None
    for q in orient:
        edge = q.get("edge")
        _require(isinstance(edge, list) and len(edge) == 2, f"bad orientation edge {edge!r}")
        e = _pair(edge[0], edge[1])
        _require(e in U0, f"orientation question on {e!r} which is not a remaining edge")
        _require(e not in seen, f"duplicate orientation question on {e!r}")
        seen.add(e)

        a, b = e
        fwd = _closure_cascade(nodes, D0, U0, adj, u_set, (a, b))
        bwd = _closure_cascade(nodes, D0, U0, adj, u_set, (b, a))
        leverage = max(len(fwd), len(bwd))
        both = fwd & bwd
        guaranteed = len(both)

        _require(guaranteed >= 1,
                 f"remaining edge {e!r} determines nothing — Phase 1 under-propagated")
        _require(q.get("leverage") == leverage,
                 f"leverage for {e!r} claimed {q.get('leverage')} but recomputed {leverage}")
        _require(q.get("guaranteed") == guaranteed,
                 f"guaranteed for {e!r} claimed {q.get('guaranteed')} but recomputed {guaranteed}")
        claimed_unlocks = {_pair(u[0], u[1]) for u in q.get("unlocks", [])}
        _require(claimed_unlocks == (both - {e}),
                 f"unlocks for {e!r} disagree: claimed {sorted(claimed_unlocks)}, "
                 f"recomputed {sorted(both - {e})}")
        if prev_leverage is not None:
            _require(leverage <= prev_leverage,
                     f"orientation questions not ranked by descending leverage "
                     f"({prev_leverage} then {leverage} at {e!r})")
        prev_leverage = leverage

    _require(seen == U0,
             f"orientation questions do not match the remaining edges one-to-one: "
             f"missing {sorted(U0 - seen)}")
