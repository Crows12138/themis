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

- **Conflict detection (direction side).** A constraint that contradicts a
  data-established orientation (an unshielded collider) is NOT silently applied.
  It is surfaced as a conflict — the answer disagrees with what the data proved,
  and a human must adjudicate (keep the data, or override it knowingly).
  Re-running a discovery algorithm with the constraint as background knowledge
  would bury that conflict inside the search.
- **Conflict detection (CI-independence side).** An unshielded collider a→C←b
  rests on TWO data facts: the collision at C, and the *non-adjacency* of a and b
  — the conditional independence the discovery's CI test found, which is exactly
  what makes the collider *unshielded* and therefore orientable at all. The
  direction check above audits the first fact; ``asserted_adjacencies`` audits the
  second. When a knowledge source asserts an adjacency the data found absent (a
  missing edge is a data independence finding under faithfulness), it is surfaced
  as a conflict — ``contradicts_independence`` in general, or
  ``undermines_collider`` (naming the collider apexes) when the contradicted
  non-adjacency is the premise of one or more data colliders, because those
  orientations would lose their data support if the pair were truly adjacent. As
  on the direction side, the assertion is NOT applied — applying it would edit the
  skeleton and amount to re-running discovery — it is surfaced for a human to
  adjudicate. The mirror of this — ``asserted_absences`` — audits knowledge that
  contradicts a data DEPENDENCE: a pair the data found adjacent (its CI test did
  not separate them) asserted independent, i.e. an edge to drop. It surfaces as
  ``contradicts_dependence`` in general, or ``undermines_collider`` (naming the
  apex) when the edge asserted absent is a directed collider *arm* — dropping it
  would remove an arm and the collider would lose its data support. Like an
  asserted adjacency it is never applied; dropping an edge would edit the skeleton.
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
from enum import unique

from .. import language
from .refusal_words import Refuses


@unique
class Says(language.Word, vocabulary="orientation_propagation_says"):
    """What a closure says about itself.

    One member for what the closure did and one per kind of input it refused,
    rather than one sentence with a clause bolted on per kind. The bolt was
    where the language went: the summary was written in English, the clause
    that followed it in Chinese, and the two were joined with a full-width
    semicolon — one string that reached every reader half in a language they
    might not have.

    Which is the shape of the defect rather than an accident of who typed
    it. ``note`` was a ``str``, so the first sentence was written where the
    counts were and the second where the conflicts were, and a field that
    holds one finished string has nowhere to put the second author's
    language.
    """

    CLOSED_THE_GRAPH = ("closed_the_graph", {
        "zh": "Meek 闭包：{data} 条边由数据定向、{constraint} 条由外部要求"
              "定向、{propagated} 条由规则推出，还有 {undetermined} 条"
              "方向待定。",
        "en": "Meek closure: {data} edges directed by the data, "
              "{constraint} by external constraint and {propagated} forced "
              "by the rules; {undetermined} still undetermined.",
    })
    CONSTRAINTS_CLASH_WITH_THE_DATA = ("constraints_clash_with_the_data", {
        "zh": "有 {count} 条外部要求的方向与数据冲突，未予采用。",
        "en": "{count} required directions clash with the data and were not "
              "applied.",
    })
    ADJACENCIES_CLASH_WITH_THE_DATA = ("adjacencies_clash_with_the_data", {
        "zh": "有 {count} 条断言的邻接与数据冲突，未予采用。",
        "en": "{count} asserted adjacencies clash with the data and were not "
              "applied.",
    })
    ABSENCES_CLASH_WITH_THE_DATA = ("absences_clash_with_the_data", {
        "zh": "有 {count} 条断言的不邻接与数据冲突，未予采用。",
        "en": "{count} asserted absences clash with the data and were not "
              "applied.",
    })
    ANSWERS_FORCE_UNREPORTED_COLLIDERS = (
        "answers_force_unreported_colliders", {
            "zh": "有 {count} 处被要求的方向会逼出数据从未报告过的对撞结构。",
            "en": "{count} required directions would force a collider the "
                  "data never reported.",
        })
    NOT_THE_PATTERN_OF_ANY_DAG = ("not_the_pattern_of_any_dag", {
        "zh": "这张图不是任何一张 DAG 的 pattern（{count} 处）——无论谁怎么"
              "回答，都没有一种定向能保住数据报告的那组对撞。",
        "en": "this graph is the pattern of no DAG ({count} places) — no "
              "orientation of it keeps the collider set the data reported, "
              "whatever anybody answers.",
    })


class OrientationError(language.Voiced, ValueError):
    """The orientation request is ill-formed — an edge references an unknown
    node, or the same pair is declared both directed and undirected, or a pair
    is oriented both ways in the input. Preferred over silently propagating a
    contradictory graph.

    A :class:`themis.language.Voiced`: it carries the species and this
    occasion's facts, and the sentence is
    :class:`themis.estimation.refusal_words.Refuses`' rather than the
    raise site's. ``ValueError`` as well, because that is what a caller
    has always been able to catch.
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
    - ``conflicts``: inputs not applied because they contradicted the data.
      An orientation-constraint conflict is
      ``{"constraint": [a, b], "reason": ...}`` (a data-established orientation, a
      non-edge, another constraint, or a cycle); an asserted-adjacency conflict is
      ``{"assertion": [a, b], "reason": ...}`` where ``reason`` is
      ``"contradicts_independence"`` / ``"undermines_collider"`` (with a
      ``"colliders"`` list of apexes) / ``"unknown_node"``; an asserted-absence
      (drop-edge) conflict is ``{"absence": [a, b], "reason": ...}`` where
      ``reason`` is ``"contradicts_dependence"`` / ``"undermines_collider"`` (with
      a ``"colliders"`` list of apexes, when the edge asserted absent is a data
      collider arm) / ``"unknown_node"``.
    - ``asserted_adjacencies``: the adjacencies external knowledge asserted,
      echoed canonical and de-duplicated so the verifier can re-derive the
      CI-side conflicts — pairs, never applied to the graph.
    - ``asserted_absences``: the non-adjacencies (edges to drop) external
      knowledge asserted, echoed canonical and de-duplicated so the verifier can
      re-derive the drop-edge conflicts — pairs, never applied to the graph.
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
    asserted_adjacencies: tuple[tuple[str, str], ...] = ()
    asserted_absences: tuple[tuple[str, str], ...] = ()
    note: tuple[language.Statement, ...] = ()


def _pair(a: str, b: str) -> tuple[str, str]:
    return (a, b) if a <= b else (b, a)


def _directed_path(directed: set[Edge], x: str, y: str) -> tuple[Edge, ...] | None:
    """The edges of some directed path x→...→y, or ``None`` if there is none.

    The path itself and not just its existence, because both callers want it:
    one refuses an orientation that would close a cycle, and the other FORCES
    the opposite orientation for the same reason — and a forced orientation
    has to be able to say what forced it, which is these edges.
    """
    if x == y:
        return ()
    children: dict[str, list[str]] = {}
    for (u, v) in directed:
        children.setdefault(u, []).append(v)
    stack: list[tuple[str, tuple[Edge, ...]]] = [(x, ())]
    seen = {x}
    while stack:
        node, so_far = stack.pop()
        for nxt in sorted(children.get(node, ())):
            step = so_far + ((node, nxt),)
            if nxt == y:
                return step
            if nxt not in seen:
                seen.add(nxt)
                stack.append((nxt, step))
    return None


def _is_ancestor(directed: set[Edge], x: str, y: str) -> bool:
    """Is ``x`` an ancestor of ``y`` following the directed edges (path
    x→...→y)? Used to refuse an orientation that would close a cycle."""
    return _directed_path(directed, x, y) is not None


def _forces(directed: set[Edge], undirected: set[tuple[str, str]],
            adj: dict[str, set[str]], a: str, b: str):
    """Do Meek's rules force ``a→b`` for the currently-undirected pair {a, b}?
    Returns ``(rule_name, witness_edges)`` or ``None``.

    Every neighbour scan below is over a SORTED list, and the reason is that
    the witness leaves the kernel: the first z found becomes ``roots`` on the
    envelope, and ``adj`` holds sets of strings, whose iteration order in
    CPython follows a hash that is randomised per process. Unsorted, the same
    input would be justified by a different edge in a different run, and the
    verifier re-derives that field.

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
    for z in sorted(adj[a]):
        if z != b and (z, a) in directed and z not in adj[b]:
            return ("R1", ((z, a),))
    # R2
    for z in sorted(adj[a]):
        if (a, z) in directed and (z, b) in directed:
            return ("R2", ((a, z), (z, b)))
    # R3
    cand = sorted(z for z in adj[a]
                  if _pair(a, z) in undirected and (z, b) in directed)
    for i, z1 in enumerate(cand):
        for z2 in cand[i + 1:]:
            if z2 not in adj[z1]:
                return ("R3", ((z1, b), (z2, b)))
    # R4
    for c in sorted(adj[a]):
        if c == b or _pair(a, c) not in undirected or c in adj[b]:
            continue
        for d in sorted(adj[b]):
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


def _unshielded_colliders(directed: set[Edge], adj: dict[str, set[str]]):
    """Every ``p→c←q`` with ``p`` and ``q`` non-adjacent, as ``(p, q, c)``.

    The skeleton decides "unshielded", and orienting an edge never changes the
    skeleton — so this asks the same question of the input's colliders and of
    the closure's, which is what lets the two be compared.
    """
    parents: dict[str, list[str]] = {}
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


def _extension_block(
    nodes: tuple[str, ...] | list[str],
    directed: set[Edge],
    undirected: set[tuple[str, str]],
    adj: dict[str, set[str]],
) -> list[tuple[str, str, str]]:
    """Witnesses that this PDAG is the pattern of no DAG — empty if it is one.

    ``guaranteed ≥ 1`` and every other promise this module makes about a
    question having two answers rest on one precondition: the input is the
    pattern of SOME DAG. Nothing used to check it, and the graph #428 was
    found on is the pattern of none — so the session was asked to choose
    between two directions when neither of them exists.

    Deciding it is Dor & Tarjan's (1992) construction, and it is a decision
    rather than a symptom check: repeatedly take a node ``x`` that (i) has no
    outgoing directed edge and (ii) has every undirected neighbour adjacent to
    every other neighbour of ``x``, orient all of ``x``'s undirected edges
    into it, and delete it. Condition (ii) is exactly "orienting them inward
    invents no unshielded collider", so the DAG this builds has the skeleton,
    the directed edges and the colliders it started with. Their theorem is
    that the greedy never needs to backtrack: if no such node exists, no
    consistent extension does.

    Its failure witness has the shape the reader already reads — a node with
    two non-adjacent neighbours, one of them still undirected, which is a
    collider that some orientation is going to be forced into. Every remaining
    node carries one, because being stuck IS every node carrying one.
    """
    live = set(nodes)
    remaining = {tuple(sorted(e)) for e in undirected}
    while live:
        stuck = []
        chosen = None
        for x in sorted(live):
            near = adj[x] & live
            if any((x, y) in directed for y in near):
                continue  # an outgoing edge — x cannot be the sink
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


def _blocking_conflicts(witnesses, reason: str,
                        roots_of=lambda p, q, c: frozenset()) -> list[dict]:
    """Group ``(apex, p, q)`` witnesses into one conflict per non-adjacent
    pair — the pair is what the reader would have to add an edge between, so
    it is what the conflict is about, and the apexes are where it shows."""
    by_pair: dict[tuple[str, str], set[str]] = {}
    for (c, p, q) in witnesses:
        by_pair.setdefault(_pair(p, q), set()).add(c)
    out = []
    for (p, q), apexes in sorted(by_pair.items()):
        roots: set[Edge] = set()
        for c in sorted(apexes):
            roots |= roots_of(p, q, c)
        out.append({
            "forced_collider": [p, q],
            "reason": reason,
            "colliders": sorted(apexes),
            "roots": [list(r) for r in sorted(roots)],
        })
    return out


def _unreported_collider_conflicts(
    directed_in: set[Edge],
    closed: set[Edge],
    adj: dict[str, set[str]],
    prov: dict[Edge, tuple],
) -> list[dict]:
    """Colliders standing at the end of the closure that the DATA never
    reported — which is what an ANSWER can do that the data alone cannot.

    ``directed`` is this module's contract for "the unshielded colliders the
    data established"; a pattern's every other edge is one the data left open
    precisely because orienting it would invent a collider. Meek's rules
    cannot produce a new one (R1 and R3 exist to prevent exactly that), so
    this fires on the constraints: a caller who answers a→b when b already had
    a parent non-adjacent to a has made a collider the data did not find, and
    no DAG has this skeleton, those colliders and that answer at once.

    A conflict rather than an exception, and for the same reason the others
    are: what to give up — an answer, an edge, the collider — is the caller's
    judgement, and the material for it is the constraints the arms rest on.
    """
    was = _unshielded_colliders(directed_in, adj)
    new = sorted(_unshielded_colliders(closed, adj) - was)
    return _blocking_conflicts(
        [(c, p, q) for (p, q, c) in new],
        "forces_unreported_collider",
        roots_of=lambda p, q, c: _roots((p, c), prov) | _roots((q, c), prov),
    )


def _asserted_adjacency_conflicts(
    node_set: set[str],
    directed_in: set[Edge],
    adj: dict[str, set[str]],
    asserted: list[tuple[str, str]],
) -> list[dict]:
    """CI-independence-side conflicts (see the module docstring).

    A pair the data left non-adjacent is a data independence finding (under
    faithfulness); asserting it is adjacent contradicts that. If the contradicted
    non-adjacency is the unshielded premise of one or more data colliders
    (``a→C`` and ``b→C`` both in ``directed_in``, with ``a``, ``b`` non-adjacent),
    the assertion would SHIELD them — those orientations would lose their data
    support — a higher-stakes ``undermines_collider`` naming the apexes; a pair
    with no such collider is a plain ``contradicts_independence``. An assertion on
    a pair that IS already adjacent agrees with the data and is no conflict.
    ``directed_in`` is taken to be the data collider orientations (the module's
    input contract), so the apex test is exactly the unshielded-collider test.
    """
    conflicts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for (a, b) in asserted:
        p = _pair(a, b)
        if p in seen:
            continue
        seen.add(p)
        if a not in node_set or b not in node_set:
            conflicts.append({"assertion": [p[0], p[1]], "reason": "unknown_node"})
            continue
        if b in adj[a]:
            continue  # already adjacent — the assertion agrees with the data
        colliders = sorted(
            c for c in node_set if (a, c) in directed_in and (b, c) in directed_in
        )
        if colliders:
            conflicts.append({
                "assertion": [p[0], p[1]], "reason": "undermines_collider",
                "colliders": colliders,
            })
        else:
            conflicts.append(
                {"assertion": [p[0], p[1]], "reason": "contradicts_independence"})
    return conflicts


def _asserted_absence_conflicts(
    node_set: set[str],
    directed_in: set[Edge],
    adj: dict[str, set[str]],
    asserted: list[tuple[str, str]],
) -> list[dict]:
    """Drop-edge (asserted-non-adjacency) conflicts — the mirror of
    ``_asserted_adjacency_conflicts`` (see the module docstring).

    A pair the data left adjacent is a data DEPENDENCE finding (its CI test did
    not separate them); asserting it is independent (an edge to drop) contradicts
    that. If the data edge between them is a directed collider *arm* (``a→b`` with
    ``b`` a collider apex — some other parent ``x→b`` in ``directed_in``), dropping
    it would remove that arm and the collider would lose its data support — a
    higher-stakes ``undermines_collider`` naming the apex; a pair joined only by an
    undirected (bare-skeleton) edge is a plain ``contradicts_dependence``. An
    assertion on a pair that is ALREADY non-adjacent agrees with the data and is no
    conflict. As with an asserted adjacency, the assertion is NOT applied — dropping
    an edge would edit the skeleton (re-run discovery) — it is only surfaced.
    ``directed_in`` is taken to be the data collider orientations (the module's
    input contract), so the arm test is exactly the unshielded-collider test.
    """
    conflicts: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for (a, b) in asserted:
        p = _pair(a, b)
        if p in seen:
            continue
        seen.add(p)
        if a not in node_set or b not in node_set:
            conflicts.append({"absence": [p[0], p[1]], "reason": "unknown_node"})
            continue
        if b not in adj[a]:
            continue  # already non-adjacent — the assertion agrees with the data
        apexes = sorted(
            head for (tail, head) in ((a, b), (b, a))
            if (tail, head) in directed_in
            and any(x != tail and (x, head) in directed_in for x in node_set)
        )
        if apexes:
            conflicts.append({
                "absence": [p[0], p[1]], "reason": "undermines_collider",
                "colliders": apexes,
            })
        else:
            conflicts.append(
                {"absence": [p[0], p[1]], "reason": "contradicts_dependence"})
    return conflicts


def propagate_orientations(
    nodes,
    *,
    directed=(),
    undirected=(),
    constraints=(),
    asserted_adjacencies=(),
    asserted_absences=(),
) -> OrientationResult:
    """Apply direction ``constraints`` to a CPDAG and propagate the forced
    orientations by Meek's rules R1-R4 (R4 is what makes the propagation
    complete once a constraint has been applied).

    ``directed`` are the data-established orientations (a, b) = a→b (the
    unshielded colliders); ``undirected`` are the undetermined edges (pairs);
    ``constraints`` are required directions (a, b) = require a→b, applied in
    order. A constraint that contradicts a data-established orientation, names
    a non-edge, contradicts an earlier constraint, or would close a directed
    cycle with an already-established orientation (``reason="creates_cycle"``) is
    recorded in ``conflicts`` and NOT applied — the established orientation is
    left intact for a human to adjudicate.

    ``asserted_adjacencies`` are pairs external knowledge claims are directly
    connected. Each is checked against the data's independence structure (the CI
    side, see the module docstring): an asserted adjacency the data found absent
    is recorded in ``conflicts`` (``contradicts_independence``, or
    ``undermines_collider`` when it would shield a data collider) and — like a
    conflicting constraint — is NOT applied; the skeleton is left intact.

    ``asserted_absences`` are the mirror: pairs external knowledge claims are
    independent (edges to drop). An asserted absence the data found adjacent is
    recorded in ``conflicts`` (``contradicts_dependence``, or
    ``undermines_collider`` when the edge is a data collider arm) and — like an
    asserted adjacency — is NOT applied; the skeleton is left intact.
    """
    nodes = tuple(sorted(nodes))
    node_set = set(nodes)

    directed_in: set[Edge] = set()
    undirected_in: set[tuple[str, str]] = set()
    adj: dict[str, set[str]] = {n: set() for n in nodes}

    for e in directed:
        a, b = e
        if a not in node_set or b not in node_set:
            raise OrientationError(Refuses.EDGE_NAMES_AN_UNKNOWN_NODE,
                                   where="directed", edge=list(e))
        if (b, a) in directed_in:
            raise OrientationError(Refuses.PAIR_IS_ORIENTED_BOTH_WAYS,
                                   pair=[a, b])
        directed_in.add((a, b))
        adj[a].add(b); adj[b].add(a)
    for e in undirected:
        a, b = tuple(e)
        if a not in node_set or b not in node_set:
            raise OrientationError(Refuses.EDGE_NAMES_AN_UNKNOWN_NODE,
                                   where="undirected", edge=list(e))
        p = _pair(a, b)
        if (a, b) in directed_in or (b, a) in directed_in:
            raise OrientationError(Refuses.PAIR_IS_DIRECTED_AND_UNDIRECTED,
                                   pair=[a, b])
        undirected_in.add(p)
        adj[a].add(b); adj[b].add(a)

    # A directed cycle among the INPUT orientations is ill-formed in the same way
    # a pair oriented both ways is: no DAG has it, so nothing downstream means
    # anything. It was never checked — the cycle guard watched constraints and
    # propagation, which is every direction an edge can be oriented EXCEPT the
    # one the caller states outright. Checked here, the closure below can rely
    # on ``D`` being acyclic, which is what makes "one direction would cycle" a
    # statement about ONE direction.
    for (a, b) in directed_in:
        if _is_ancestor(directed_in - {(a, b)}, b, a):
            raise OrientationError(Refuses.THE_STATED_EDGES_CYCLE,
                                   tail=a, head=b)

    D: set[Edge] = set(directed_in)
    U: set[tuple[str, str]] = set(undirected_in)
    prov: dict[Edge, tuple] = {e: ("collider_input", ()) for e in D}
    conflicts: list[dict] = []

    # --- is the input the pattern of any DAG? ---------------------------------
    # First, and on the input alone, because everything after it is written on
    # the assumption that the answer is yes: the closure's completeness, the
    # promise that a remaining edge has two live directions, the questions
    # built from that promise. Answered where the answer belongs — before any
    # of them run — rather than inferred later from a symptom.
    # ONE conflict, however many witnesses came back. Being stuck is one fact
    # about the whole graph — the theorem is that no other order of building
    # would have got further — and the witnesses are places it shows, not
    # separate things to decide. Reporting them one each would put four
    # questions in front of a reader who has one problem, and would suggest
    # that connecting any one of the four pairs is a way out. It is not:
    # nothing says an edge there makes the graph realisable. What the reader
    # has is one concrete place to look, so that is what is carried.
    if (blocked := _extension_block(nodes, directed_in, undirected_in, adj)):
        apex, near, far = min(blocked)
        conflicts.append({
            "forced_collider": list(_pair(near, far)),
            "reason": "no_consistent_extension",
            "colliders": [apex],
            "roots": [],
        })

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
        if _is_ancestor(D, b, a):
            # applying a→b would close a directed cycle with an already-established
            # orientation (data or an earlier answer) — the answer set is not a DAG
            conflicts.append({"constraint": [a, b], "reason": "creates_cycle"})
            continue
        U.discard(p)
        D.add((a, b))
        prov[(a, b)] = ("constraint", ())
        applied.append((a, b))

    # --- asserted adjacencies (CI-independence-side conflict detection) -------
    # These never touch the closure — applying an adjacency would edit the
    # skeleton (re-run discovery); they only surface conflicts with the data's CI
    # structure, using the data colliders (directed_in) and the data skeleton (adj).
    asserted_pairs: list[tuple[str, str]] = []
    for e in asserted_adjacencies:
        a, b = tuple(e)
        if a == b:
            raise OrientationError(Refuses.SELF_LOOP, edge=list(e),
                                   where="asserted_adjacencies")
        asserted_pairs.append((a, b))
    conflicts.extend(
        _asserted_adjacency_conflicts(node_set, directed_in, adj, asserted_pairs))
    asserted_out = tuple(sorted({_pair(a, b) for (a, b) in asserted_pairs}))

    # --- asserted absences (drop-edge conflict detection, the mirror) ---------
    # Also never touch the closure — dropping an edge would edit the skeleton;
    # they only surface conflicts with the data's dependence structure (the data
    # skeleton in ``adj``, and its collider arms in ``directed_in``).
    absence_pairs: list[tuple[str, str]] = []
    for e in asserted_absences:
        a, b = tuple(e)
        if a == b:
            raise OrientationError(Refuses.SELF_LOOP, edge=list(e),
                                   where="asserted_absences")
        absence_pairs.append((a, b))
    conflicts.extend(
        _asserted_absence_conflicts(node_set, directed_in, adj, absence_pairs))
    absences_out = tuple(sorted({_pair(a, b) for (a, b) in absence_pairs}))

    # --- Meek closure R1-R4, to a fixpoint ------------------------------------
    # ``sorted`` and not ``list``: ``U`` holds tuples of strings, whose set
    # iteration order in CPython follows a per-process hash. Two rules can be
    # ready on the same edge at the same moment, and the one that gets there
    # first signs the provenance the verifier re-derives — so the order an
    # edge is visited in is part of what the two sides have to agree on.
    changed = True
    while changed:
        changed = False
        for p in sorted(U):
            a, b = p
            f = _forces(D, U, adj, a, b)
            if f and not _is_ancestor(D, b, a):
                D.add((a, b)); U.discard(p); prov[(a, b)] = f; changed = True
                continue
            f2 = _forces(D, U, adj, b, a)
            if f2 and not _is_ancestor(D, a, b):
                D.add((b, a)); U.discard(p); prov[(b, a)] = f2; changed = True

    conflicts.extend(_unreported_collider_conflicts(directed_in, D, adj, prov))

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
    n_adj_conflict = sum(1 for c in conflicts if "assertion" in c)
    n_abs_conflict = sum(1 for c in conflicts if "absence" in c)
    n_unrealisable = sum(1 for c in conflicts
                         if c.get("reason") == "no_consistent_extension")
    n_collider_conflict = sum(1 for c in conflicts
                              if c.get("reason") == "forces_unreported_collider")
    n_con_conflict = (len(conflicts) - n_adj_conflict - n_abs_conflict
                      - n_collider_conflict - n_unrealisable)
    note = [language.state(
        Says.CLOSED_THE_GRAPH,
        data=len(directed_in), constraint=n_from_constraints,
        propagated=n_propagated, undetermined=len(remaining),
    )]
    note.extend(
        language.state(member, count=count)
        for member, count in (
            (Says.CONSTRAINTS_CLASH_WITH_THE_DATA, n_con_conflict),
            (Says.ADJACENCIES_CLASH_WITH_THE_DATA, n_adj_conflict),
            (Says.ABSENCES_CLASH_WITH_THE_DATA, n_abs_conflict),
            (Says.ANSWERS_FORCE_UNREPORTED_COLLIDERS, n_collider_conflict),
            (Says.NOT_THE_PATTERN_OF_ANY_DAG, n_unrealisable),
        )
        if count
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
        asserted_adjacencies=asserted_out,
        asserted_absences=absences_out,
        note=tuple(note),
    )


def orientation_to_dict(result: OrientationResult) -> dict:
    """JSON-serialisable view — the artifact ``verify_orientation_propagation``
    consumes.

    Checked against its own declared shape on the way out, the way the kernel
    checks an envelope. A schema nothing validates is a description of what
    somebody believed the producer emitted.
    """
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact({
        "kind": "orientation_propagation",
        "nodes": list(result.nodes),
        "input_directed": [list(e) for e in result.input_directed],
        "input_undirected": [list(e) for e in result.input_undirected],
        "constraints": [list(e) for e in result.constraints],
        "oriented": [list(e) for e in result.oriented],
        "remaining_undirected": [list(e) for e in result.remaining_undirected],
        "asserted_adjacencies": [list(e) for e in result.asserted_adjacencies],
        "asserted_absences": [list(e) for e in result.asserted_absences],
        "conflicts": [dict(c) for c in result.conflicts],
        "provenance": [dict(p) for p in result.provenance],
        "note": [dict(one) for one in result.note],
    })
