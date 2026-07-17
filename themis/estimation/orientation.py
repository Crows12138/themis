"""Meek orientation propagation on a CPDAG, with constraint-consistency
(2026-07-17, interactive equivalence-class resolution — Phase 1).

Causal discovery on observational data recovers a CPDAG (a Markov-equivalence
class): the skeleton plus the edges the data can orient from unshielded
colliders. Many edges stay undirected — their direction is not determined by
observational data alone. External knowledge (a temporal order, a domain fact,
an answer from a human or an LLM) can supply some of those directions; the
remaining orientations that are then *logically forced* propagate via Meek's
(1995) rules — WITHOUT re-touching the data.

This module owns that propagation as a deterministic, algorithm-agnostic
primitive (any CPDAG — PC / GES / GRaSP — feeds in the same way), and does two
things a re-run of the discovery algorithm does not:

- **Conflict detection.** A constraint that contradicts a data-established
  orientation (an unshielded collider) is NOT silently applied. It is surfaced
  as a conflict — the answer disagrees with what the data proved, and a human
  must adjudicate (keep the data, or override it knowingly). Re-running a
  discovery algorithm with the constraint as background knowledge would bury
  that conflict inside the search.
- **Provenance.** Every propagated orientation records the rule that forced it
  and the witness edges; from those, each oriented edge is traced back to the
  root constraints it ultimately rests on. A wrong answer's blast radius is
  therefore explicit — the edges resting on it can be found and revisited.

Scope (stated tradeoffs): the CPDAG setting (causal sufficiency — no latent
confounders). Meek's four rules R1-R4 are applied to a fixpoint. R1-R3 alone
complete a *bare* pattern from its colliders (Meek 1995), but this module's job
is to apply external constraints — background knowledge — and once a constraint
orients an edge the data left open, R4 is required for completeness: without it
some genuinely-forced orientations are missed (the result stays sound, but
incomplete). The rules are validated to a fixpoint against a brute-force
equivalence-class oracle (enumerate every DAG consistent with the skeleton, the
colliders and the constraints; an edge is forced iff all of them agree), which
catches both an unsound orientation and an R4-style completeness gap.
causal-learn's reference Meek — which itself implements only R1-R3 — is a
secondary cross-check for the bare, no-constraint completion only, and cannot
certify the constrained case. The PAG / latent-confounder case (FCI) needs the
larger Zhang (2008) rule set and is deliberately deferred rather than run with
an incomplete rule set. The runtime carries no library dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class OrientationError(ValueError):
    """The orientation request is ill-formed — an edge references an unknown
    node, or the same pair is declared both directed and undirected, or a pair
    is oriented both ways in the input. Preferred over silently propagating a
    contradictory graph.
    """


Edge = tuple[str, str]


@dataclass(frozen=True)
class OrientationResult:
    """Output of Meek propagation over a CPDAG plus direction constraints.

    - ``nodes``: all variables, canonical (sorted) order.
    - ``input_directed`` / ``input_undirected``: the CPDAG as given (the
      data-established orientations and the undetermined edges) — echoed so the
      verifier can re-derive the closure without the producer.
    - ``constraints``: the required directions applied (a, b) = require a→b,
      in the order given.
    - ``oriented``: the final directed edges after closure (a, b) = a→b.
    - ``remaining_undirected``: edges still undetermined after propagation.
    - ``conflicts``: constraints not applied because they contradicted the
      input (a data-established orientation, a non-edge, or another
      constraint). Each is ``{"constraint": [a, b], "reason": ..., ...}``.
    - ``provenance``: one entry per oriented edge —
      ``{"from": a, "to": b, "rule": r, "roots": [[a, b], ...]}`` where ``r`` is
      ``"collider_input"`` (from the data), ``"constraint"`` (applied directly),
      or ``"R1"`` / ``"R2"`` / ``"R3"`` / ``"R4"`` (forced by that Meek rule),
      and ``roots``
      lists the constraint edges the orientation ultimately rests on (empty for
      data-established edges).
    - ``note``: human-readable summary.
    """

    nodes: tuple[str, ...]
    input_directed: tuple[Edge, ...]
    input_undirected: tuple[tuple[str, str], ...]
    constraints: tuple[Edge, ...]
    oriented: tuple[Edge, ...]
    remaining_undirected: tuple[tuple[str, str], ...]
    conflicts: tuple[dict, ...]
    provenance: tuple[dict, ...]
    note: str = ""


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _is_ancestor(directed: set[Edge], x: str, y: str) -> bool:
    """Is ``x`` an ancestor of ``y`` following the directed edges (path
    x→...→y)? Used to refuse an orientation that would close a cycle."""
    if x == y:
        return True
    stack = [x]
    seen = {x}
    children: dict[str, list[str]] = {}
    for (u, v) in directed:
        children.setdefault(u, []).append(v)
    while stack:
        node = stack.pop()
        for nxt in children.get(node, ()):
            if nxt == y:
                return True
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return False


def _forces(directed: set[Edge], undirected: set[tuple[str, str]],
            adj: dict[str, set[str]], a: str, b: str):
    """Do Meek's rules force ``a→b`` for the currently-undirected pair {a, b}?
    Returns ``(rule_name, witness_edges)`` or ``None``.

    - **R1** (no new collider): ∃ z with z→a and z not adjacent to b ⟹ a→b
      (else z→a←b would be an unshielded collider the data did not find).
    - **R2** (acyclicity): ∃ z with a→z→b ⟹ a→b (else a—b closes a cycle).
    - **R3** (kite / no new collider): ∃ two non-adjacent z1, z2 with a—z1,
      a—z2 undirected and z1→b, z2→b ⟹ a→b.
    - **R4** (kite with a directed path; needed once constraints are present —
      Meek 1995): ∃ c, d with a—c undirected, c→d, d→b, c and b non-adjacent,
      and a adjacent to d ⟹ a→b. R1-R3 alone are incomplete under background
      knowledge; R4 recovers the orientations they miss. The witness edges are
      the two directed edges c→d and d→b it rests on.
    """
    # R1
    for z in adj[a]:
        if z != b and (z, a) in directed and z not in adj[b]:
            return ("R1", ((z, a),))
    # R2
    for z in adj[a]:
        if (a, z) in directed and (z, b) in directed:
            return ("R2", ((a, z), (z, b)))
    # R3
    cand = [z for z in adj[a] if _pair(a, z) in undirected and (z, b) in directed]
    for i, z1 in enumerate(cand):
        for z2 in cand[i + 1:]:
            if z2 not in adj[z1]:
                return ("R3", ((z1, b), (z2, b)))
    # R4
    for c in adj[a]:
        if c == b or _pair(a, c) not in undirected or c in adj[b]:
            continue
        for d in adj[b]:
            if (d, b) in directed and (c, d) in directed and d in adj[a]:
                return ("R4", ((c, d), (d, b)))
    return None


def _roots(edge: Edge, prov: dict[Edge, tuple]) -> frozenset[Edge]:
    """Constraint edges that ``edge`` ultimately rests on (empty for a
    data-established / collider edge)."""
    rule, witness = prov[edge]
    if rule == "collider_input":
        return frozenset()
    if rule == "constraint":
        return frozenset({edge})
    roots: set[Edge] = set()
    for w in witness:
        roots |= _roots(w, prov)
    return frozenset(roots)


def propagate_orientations(
    nodes,
    *,
    directed=(),
    undirected=(),
    constraints=(),
) -> OrientationResult:
    """Apply direction ``constraints`` to a CPDAG and propagate the forced
    orientations by Meek's rules R1-R4 (R4 is what makes the propagation
    complete once a constraint has been applied).

    ``directed`` are the data-established orientations (a, b) = a→b (the
    unshielded colliders); ``undirected`` are the undetermined edges (pairs);
    ``constraints`` are required directions (a, b) = require a→b, applied in
    order. A constraint that contradicts a data-established orientation, names
    a non-edge, or contradicts an earlier constraint is recorded in
    ``conflicts`` and NOT applied — the data's orientation is left intact for a
    human to adjudicate.
    """
    nodes = tuple(sorted(nodes))
    node_set = set(nodes)

    directed_in: set[Edge] = set()
    undirected_in: set[tuple[str, str]] = set()
    adj: dict[str, set[str]] = {n: set() for n in nodes}

    for e in directed:
        a, b = e
        if a not in node_set or b not in node_set:
            raise OrientationError(f"directed edge {e!r} references an unknown node")
        if (b, a) in directed_in:
            raise OrientationError(f"pair {{{a}, {b}}} is oriented both ways in the input")
        directed_in.add((a, b))
        adj[a].add(b); adj[b].add(a)
    for e in undirected:
        a, b = tuple(e)
        if a not in node_set or b not in node_set:
            raise OrientationError(f"undirected edge {e!r} references an unknown node")
        p = _pair(a, b)
        if (a, b) in directed_in or (b, a) in directed_in:
            raise OrientationError(f"pair {{{a}, {b}}} is both directed and undirected")
        undirected_in.add(p)
        adj[a].add(b); adj[b].add(a)

    D: set[Edge] = set(directed_in)
    U: set[tuple[str, str]] = set(undirected_in)
    prov: dict[Edge, tuple] = {e: ("collider_input", ()) for e in D}
    conflicts: list[dict] = []

    # --- apply constraints (with conflict detection) --------------------------
    applied: list[Edge] = []
    for (a, b) in constraints:
        if a not in node_set or b not in node_set:
            conflicts.append({"constraint": [a, b], "reason": "unknown_node"})
            continue
        p = _pair(a, b)
        if (a, b) in D:
            applied.append((a, b))  # already this direction (redundant, consistent)
            continue
        if (b, a) in D:
            conflicts.append({
                "constraint": [a, b], "reason": "contradicts_data_orientation",
                "data_edge": [b, a],
            })
            continue
        if p not in U:
            conflicts.append({"constraint": [a, b], "reason": "non_adjacent_pair"})
            continue
        U.discard(p)
        D.add((a, b))
        prov[(a, b)] = ("constraint", ())
        applied.append((a, b))

    # --- Meek closure R1-R4 to a fixpoint -------------------------------------
    changed = True
    while changed:
        changed = False
        for p in list(U):
            a, b = p
            f = _forces(D, U, adj, a, b)
            if f and not _is_ancestor(D, b, a):
                D.add((a, b)); U.discard(p); prov[(a, b)] = f; changed = True
                continue
            f2 = _forces(D, U, adj, b, a)
            if f2 and not _is_ancestor(D, a, b):
                D.add((b, a)); U.discard(p); prov[(b, a)] = f2; changed = True

    oriented = tuple(sorted(D))
    remaining = tuple(sorted(U))
    provenance = tuple(
        {
            "from": a, "to": b, "rule": prov[(a, b)][0],
            "roots": [list(r) for r in sorted(_roots((a, b), prov))],
        }
        for (a, b) in oriented
    )
    n_from_constraints = len(applied)
    n_propagated = len(D) - len(directed_in) - n_from_constraints
    note = (
        f"Meek propagation: {len(directed_in)} data-oriented + "
        f"{n_from_constraints} constraint + {n_propagated} propagated edges "
        f"directed, {len(remaining)} still undetermined"
        + (f"; {len(conflicts)} constraint(s) conflicted with the data"
           if conflicts else "")
    )
    return OrientationResult(
        nodes=nodes,
        input_directed=tuple(sorted(directed_in)),
        input_undirected=tuple(sorted(undirected_in)),
        constraints=tuple((a, b) for (a, b) in constraints),
        oriented=oriented,
        remaining_undirected=remaining,
        conflicts=tuple(conflicts),
        provenance=provenance,
        note=note,
    )


def orientation_to_dict(result: OrientationResult) -> dict:
    """JSON-serialisable view — the artifact ``verify_orientation_propagation``
    consumes."""
    return {
        "kind": "orientation_propagation",
        "nodes": list(result.nodes),
        "input_directed": [list(e) for e in result.input_directed],
        "input_undirected": [list(e) for e in result.input_undirected],
        "constraints": [list(e) for e in result.constraints],
        "oriented": [list(e) for e in result.oriented],
        "remaining_undirected": [list(e) for e in result.remaining_undirected],
        "conflicts": [dict(c) for c in result.conflicts],
        "provenance": [dict(p) for p in result.provenance],
        "note": result.note,
    }
