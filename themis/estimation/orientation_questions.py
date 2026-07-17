"""Compile a leverage-ranked question set from an equivalence class
(2026-07-17, interactive equivalence-class resolution — Phase 2).

Phase 1 (``propagate_orientations``) takes a CPDAG plus whatever direction
constraints are known and returns the Meek closure: the edges now oriented, the
edges still undetermined, and any constraint that CONFLICTED with the data. What
remains is the interactive problem — *which questions should the tool put to the
human / LLM next, and in what order*, so the highest-impact answers come first.
This module compiles that ranked question set. It is the bridge between the
deterministic kernel and the LLM front door: Phase 3 asks the top question, feeds
the answer back through ``propagate_orientations`` (which cascades and removes
every edge that answer determined), then re-compiles the shrunken set.

Two kinds of question come out, in priority order:

- **Conflict questions (first).** Every conflict Phase 1 surfaced — an answer or
  a piece of background knowledge that contradicts a data-established collider,
  or names a non-edge — becomes a question a human MUST adjudicate first, because
  it is a disagreement about a fact the data already settled. These block
  correctness, so they outrank everything.

- **Orientation questions (leverage-ranked).** One per still-undetermined edge,
  ranked by *leverage*: how many edges its answer would determine by propagation.
  An undetermined edge can be answered either way, and the two answers can cascade
  differently, so each question carries BOTH numbers — ``leverage`` is the larger
  (the best-case unlock, used for ranking) and ``guaranteed`` is the smaller (what
  an answer fixes regardless of direction, always ≥ 1: the edge itself). Asking a
  high-leverage edge first tends to collapse the remaining set fastest, because a
  favourable answer resolves many edges at once and they drop out on re-compile.

Why this shape, and the stated tradeoffs:

- Leverage is measured by the Phase 1 propagation engine itself — orient the edge
  each way, run the Meek closure, count the newly-determined edges. This is exact
  (Meek closure of a single answer = the edges determined in every member DAG that
  agrees with that answer) and reuses the already-validated primitive, so there is
  no enumeration blow-up and no large-component fallback. Every undetermined edge
  is genuinely two-way (else Phase 1 would have forced it), so both answers are
  equivalence-class-consistent and their cascades are valid.

- The set is NOT a pre-committed minimal cover. In the CPDAG worst case the
  guaranteed leverage of any single edge is exactly 1 — no single answer forces a
  second edge no matter how it is answered — so a worst-case cover would just be
  "every edge", a vacuous claim. The honest and useful object is therefore the
  full remaining set ranked by *best-case* cascade, resolved one answer at a time
  by the interactive loop; typically far fewer than the whole list get asked
  because early answers cascade. We rank, we do not under-count the questions.

Scope: the CPDAG setting (causal sufficiency), inherited from Phase 1. The
runtime carries no library dependency.
"""
from __future__ import annotations

from dataclasses import dataclass

from .orientation import OrientationResult, propagate_orientations

Edge = tuple[str, str]
Pair = tuple[str, str]


@dataclass(frozen=True)
class OrientationQuestion:
    """One question to put to the human / LLM.

    - ``kind``: ``"conflict"`` or ``"orientation"``.
    - ``edge``: the pair in question — ``(a, b)`` with ``a <= b`` for an
      orientation question; the constraint pair as given for a conflict.
    - ``leverage``: for an orientation question, the larger of the two answers'
      cascade sizes (edges determined, itself included) — the best-case unlock,
      used for ranking; ``0`` for a conflict (its value is correctness).
    - ``guaranteed``: the smaller of the two — what the answer fixes regardless of
      direction (always ≥ 1, the edge itself); ``0`` for a conflict.
    - ``unlocks``: the OTHER edges determined regardless of the answer (the
      intersection of the two cascades, minus the edge itself).
    - ``reason``: the conflict reason for a conflict question, else ``""``.
    - ``detail``: structured transparency — for an orientation question the two
      directed answers and each one's full cascade; for a conflict the data edge
      it contradicts.
    - ``prompt``: a human-readable phrasing.
    """

    kind: str
    edge: Edge
    leverage: int
    guaranteed: int
    unlocks: tuple[Pair, ...]
    reason: str
    detail: dict
    prompt: str


@dataclass(frozen=True)
class QuestionSet:
    """The compiled, ranked question set for one equivalence class.

    Echoes the Phase 1 inputs (``input_directed`` / ``input_undirected`` /
    ``constraints``) and the post-propagation state (``oriented`` /
    ``remaining_undirected``) so the verifier can re-derive every number without
    the producer. ``questions`` lists conflicts first, then orientation questions
    by descending leverage.
    """

    nodes: tuple[str, ...]
    input_directed: tuple[Edge, ...]
    input_undirected: tuple[Pair, ...]
    constraints: tuple[Edge, ...]
    oriented: tuple[Edge, ...]
    remaining_undirected: tuple[Pair, ...]
    questions: tuple[OrientationQuestion, ...]
    note: str = ""


def _pair(a: str, b: str) -> Pair:
    return (a, b) if a <= b else (b, a)


def _cascade(nodes, directed, undirected, u_set: set[frozenset], answer: Edge) -> set[Pair]:
    """The undirected edges determined by answering ``answer`` — the Meek closure
    of the single constraint, restricted to the originally-undirected edges."""
    r = propagate_orientations(nodes, directed=directed, undirected=undirected,
                               constraints=[answer])
    return {tuple(sorted(e)) for e in r.oriented if frozenset(e) in u_set}


def _conflict_prompt(c: dict) -> str:
    a, b = c["constraint"]
    reason = c.get("reason")
    if reason == "contradicts_data_orientation":
        d = c.get("data_edge", [b, a])
        return (f"The data establishes {d[0]}→{d[1]} (an unshielded collider), but "
                f"the proposed direction is {a}→{b}. Keep the data's orientation, or "
                f"override it knowingly?")
    if reason == "non_adjacent_pair":
        return (f"{a} and {b} are not adjacent in the graph, so {a}→{b} cannot be "
                f"applied. Is an edge {a}–{b} missing, or is the direction spurious?")
    if reason == "unknown_node":
        return f"{a}→{b} names a variable not in the graph."
    return f"Constraint {a}→{b} could not be applied ({reason})."


def compile_orientation_questions(result: OrientationResult) -> QuestionSet:
    """Compile the ranked question set for a Phase 1 orientation result.

    Conflicts become adjudication questions (ranked first); each still-undetermined
    edge becomes an orientation question annotated with its best-case and
    guaranteed cascade sizes, ranked by descending leverage. See the module
    docstring for the leverage definition and the stated tradeoffs (leverage is
    the best-case cascade; the set is ranked, not a worst-case minimal cover).
    """
    nodes = tuple(result.nodes)
    directed = list(result.oriented)
    undirected = list(result.remaining_undirected)
    u_set = {frozenset(e) for e in undirected}

    questions: list[OrientationQuestion] = []

    # --- conflict questions (rank first) --------------------------------------
    for c in result.conflicts:
        pair = tuple(c["constraint"])
        detail = {k: v for k, v in c.items() if k not in ("constraint", "reason")}
        questions.append(OrientationQuestion(
            kind="conflict", edge=(pair[0], pair[1]), leverage=0, guaranteed=0,
            unlocks=(), reason=c.get("reason", ""), detail=detail,
            prompt=_conflict_prompt(c),
        ))

    # --- orientation questions, leverage-ranked -------------------------------
    orient: list[OrientationQuestion] = []
    for e in sorted(tuple(sorted(p)) for p in undirected):
        a, b = e
        fwd = _cascade(nodes, directed, undirected, u_set, (a, b))
        bwd = _cascade(nodes, directed, undirected, u_set, (b, a))
        leverage = max(len(fwd), len(bwd))
        both = fwd & bwd
        guaranteed = len(both)
        unlocks = tuple(sorted(both - {e}))
        detail = {
            "forward": {"answer": [a, b], "determines": [list(x) for x in sorted(fwd)]},
            "backward": {"answer": [b, a], "determines": [list(x) for x in sorted(bwd)]},
        }
        extra = (f"; a favourable answer also fixes "
                 f"{', '.join(f'{u}–{v}' for (u, v) in sorted((fwd | bwd) - {e}))}") \
            if leverage > guaranteed or unlocks else ""
        orient.append(OrientationQuestion(
            kind="orientation", edge=e, leverage=leverage, guaranteed=guaranteed,
            unlocks=unlocks, reason="", detail=detail,
            prompt=(f"Does {a} cause {b}, or {b} cause {a}? "
                    f"(determines up to {leverage} edge(s){extra})"),
        ))
    orient.sort(key=lambda q: (-q.leverage, q.edge))
    questions.extend(orient)

    note = (
        f"{len(result.conflicts)} conflict question(s) to adjudicate; "
        f"{len(orient)} orientation question(s) over {len(undirected)} undetermined "
        f"edge(s), ranked by best-case leverage (top leverage "
        f"{orient[0].leverage if orient else 0})"
    )
    return QuestionSet(
        nodes=nodes,
        input_directed=tuple(result.input_directed),
        input_undirected=tuple(result.input_undirected),
        constraints=tuple(result.constraints),
        oriented=tuple(result.oriented),
        remaining_undirected=tuple(result.remaining_undirected),
        questions=tuple(questions),
        note=note,
    )


def question_set_to_dict(qs: QuestionSet) -> dict:
    """JSON-serialisable view — the artifact ``verify_orientation_questions``
    consumes."""
    return {
        "kind": "orientation_question_set",
        "nodes": list(qs.nodes),
        "input_directed": [list(e) for e in qs.input_directed],
        "input_undirected": [list(e) for e in qs.input_undirected],
        "constraints": [list(e) for e in qs.constraints],
        "oriented": [list(e) for e in qs.oriented],
        "remaining_undirected": [list(e) for e in qs.remaining_undirected],
        "questions": [
            {
                "kind": q.kind,
                "edge": list(q.edge),
                "leverage": q.leverage,
                "guaranteed": q.guaranteed,
                "unlocks": [list(e) for e in q.unlocks],
                "reason": q.reason,
                "detail": dict(q.detail),
                "prompt": q.prompt,
            }
            for q in qs.questions
        ],
        "note": qs.note,
    }
