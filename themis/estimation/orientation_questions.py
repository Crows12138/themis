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
    ``constraints`` / ``asserted_adjacencies`` / ``asserted_absences``) and the
    post-propagation state (``oriented`` / ``remaining_undirected``) so the
    verifier can re-derive every number — including the CI-side adjacency and
    drop-edge conflicts — without the producer.
    ``questions`` lists conflicts first, then orientation questions by descending
    leverage.
    """

    nodes: tuple[str, ...]
    input_directed: tuple[Edge, ...]
    input_undirected: tuple[Pair, ...]
    constraints: tuple[Edge, ...]
    oriented: tuple[Edge, ...]
    remaining_undirected: tuple[Pair, ...]
    questions: tuple[OrientationQuestion, ...]
    asserted_adjacencies: tuple[Pair, ...] = ()
    asserted_absences: tuple[Pair, ...] = ()
    note: str = ""


def _pair(a: str, b: str) -> Pair:
    return (a, b) if a <= b else (b, a)


def _cascade(nodes, directed, undirected, u_set: set[frozenset], answer: Edge) -> set[Pair]:
    """The undirected edges determined by answering ``answer`` — the Meek closure
    of the single constraint, restricted to the originally-undirected edges."""
    r = propagate_orientations(nodes, directed=directed, undirected=undirected,
                               constraints=[answer])
    return {_pair(*e) for e in r.oriented if frozenset(e) in u_set}


def _conflict_prompt(c: dict) -> str:
    reason = c.get("reason")
    if "forced_collider" in c:
        a, b = c["forced_collider"]
        apexes = c.get("colliders", [])
        made = "、".join(f"{a}→{x}←{b}" for x in apexes)
        if reason == "no_consistent_extension":
            where = "、".join(apexes)
            return (f"这张图不是任何一张 DAG 的 pattern：把它补全成一张 DAG 的路"
                    f"走不通。断在 {where} 上——{a} 与 {b} 不相邻，却都连着 "
                    f"{where}，而那里还有边没有方向，往哪边定都会出现一个 "
                    f"{made} 这样的无屏蔽对撞，可数据并没有报告它。"
                    f"这不是某一条边的毛病，{where} 只是能看见它的一处："
                    f"骨架和数据给的那些对撞本身就不可能同时为真。"
                    f"要回到画这张图或做独立性检验的那一步。")
        return (f"{a} 与 {b} 不相邻，而到目前为止的回答把 {made} 的两条臂都逼了"
                f"出来——这是一个无屏蔽对撞，数据并没有报告它。"
                f"骨架、数据给的那些对撞、到目前为止的回答，这三样不可能同时"
                f"为真：没有任何一张 DAG 同时满足它们。要放弃哪一样——"
                f"补一条 {a}–{b}，还是撤回一个回答？")
    if "absence" in c:
        a, b = c["absence"]
        if reason == "undermines_collider":
            arm = ", ".join(f"{a if x == b else b}→{x}" for x in c.get("colliders", []))
            return (f"知识说 {a} 与 {b} 独立（该删掉这条边），但数据把 {arm} "
                    f"定向成了一个无屏蔽对撞的一条臂。删掉这条边就等于拿掉那条臂，"
                    f"对撞也就失去了数据支持。是信数据给的对撞，"
                    f"还是照知识删边？")
        if reason == "contradicts_dependence":
            return (f"知识说 {a} 与 {b} 独立（没有边），但数据发现它们相依——"
                    f"骨架里有一条 {a}–{b}。是信数据的相依结论，"
                    f"还是照断言把这条边删掉？")
        if reason == "unknown_node":
            return f"断言的缺边 {a}–{b} 里有图上没有的变量。"
        return f"断言的缺边 {a}–{b} 与数据冲突（{reason}）。"
    if "assertion" in c:
        a, b = c["assertion"]
        if reason == "undermines_collider":
            apex = ", ".join(f"{a}→{c0}←{b}" for c0 in c.get("colliders", []))
            return (f"知识说 {a} 与 {b} 直接相连，但数据发现它们独立——"
                    f"而这正是对撞 {apex} 的「无屏蔽」前提。若二者相邻，"
                    f"那些定向就没有数据支持了。是信数据的独立性检验，"
                    f"还是信断言的这条边？")
        if reason == "contradicts_independence":
            return (f"知识说 {a} 与 {b} 直接相连，但数据发现它们条件独立（没有边）。"
                    f"是信数据的独立性检验，还是信断言的这条边？")
        if reason == "unknown_node":
            return f"断言的相邻 {a}–{b} 里有图上没有的变量。"
        return f"断言的相邻 {a}–{b} 与数据冲突（{reason}）。"
    a, b = c["constraint"]
    if reason == "contradicts_data_orientation":
        d = c.get("data_edge", [b, a])
        return (f"数据确立了 {d[0]}→{d[1]}（一个无屏蔽对撞），"
                f"而提出的方向是 {a}→{b}。是保留数据给的定向，"
                f"还是明知而覆盖它？")
    if reason == "non_adjacent_pair":
        return (f"{a} 与 {b} 在图上不相邻，所以 {a}→{b} 无法应用。"
                f"是漏了一条 {a}–{b}，还是这个方向本身站不住？")
    if reason == "creates_cycle":
        return (f"{a}→{b} 会和已确立的定向合成一个有向环——"
                f"到目前为止的这些回答不可能同时成立。要改哪一个？")
    if reason == "unknown_node":
        return f"{a}→{b} 里有图上没有的变量。"
    return f"约束 {a}→{b} 没能应用（{reason}）。"


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
    # A conflict is keyed "constraint" (a direction that contradicts the data),
    # "assertion" (an adjacency that contradicts the data's CI structure),
    # "absence" (a drop-edge that contradicts the data's dependence structure),
    # or "forced_collider" (no orientation of this graph keeps the collider set
    # the data reported — it is the pattern of no DAG); all become adjudication
    # questions a human must resolve first.
    for c in result.conflicts:
        key = ("assertion" if "assertion" in c
               else "absence" if "absence" in c
               else "forced_collider" if "forced_collider" in c
               else "constraint")
        pair = tuple(c[key])
        detail = {k: v for k, v in c.items() if k not in (key, "reason")}
        questions.append(OrientationQuestion(
            kind="conflict", edge=(pair[0], pair[1]), leverage=0, guaranteed=0,
            unlocks=(), reason=c.get("reason", ""), detail=detail,
            prompt=_conflict_prompt(c),
        ))

    # --- orientation questions, leverage-ranked -------------------------------
    # None of them if the graph is the pattern of no DAG. An orientation
    # question offers two directions and asks which one holds; on a graph no
    # DAG realises, neither does, and the honest thing to hand back is the
    # conflicts above — what to give up — rather than a choice between two
    # things that are both false. This is also what makes every promise below
    # (``guaranteed`` ≥ 1, both cascades non-empty) a consequence of Meek's
    # completeness rather than a hope: its precondition is checked upstream,
    # and when it fails there is nothing here to be wrong about.
    orient: list[OrientationQuestion] = []
    unrealisable = any(c.get("reason") == "no_consistent_extension"
                       for c in result.conflicts)
    for e in sorted(_pair(*p) for p in undirected) if not unrealisable else ():
        a, b = e
        fwd = _cascade(nodes, directed, undirected, u_set, (a, b))
        bwd = _cascade(nodes, directed, undirected, u_set, (b, a))
        # Both are non-empty, each holding at least the edge the answer names:
        # the input is the pattern of some DAG, so every edge Meek left
        # undirected is reversible in it, so neither direction is refused.
        leverage = max(len(fwd), len(bwd))
        both = fwd & bwd
        guaranteed = len(both)
        unlocks = tuple(sorted(both - {e}))
        detail = {
            "forward": {"answer": [a, b], "determines": [list(x) for x in sorted(fwd)]},
            "backward": {"answer": [b, a], "determines": [list(x) for x in sorted(bwd)]},
        }
        extra = (f"；答案若走运，还能顺带定下 "
                 f"{'、'.join(f'{u}–{v}' for (u, v) in sorted((fwd | bwd) - {e}))}") \
            if leverage > guaranteed or unlocks else ""
        orient.append(OrientationQuestion(
            kind="orientation", edge=e, leverage=leverage, guaranteed=guaranteed,
            unlocks=unlocks, reason="", detail=detail,
            prompt=(f"是 {a} 导致 {b}，还是 {b} 导致 {a}？"
                    f"（最多能定下 {leverage} 条边{extra}）"),
        ))
    orient.sort(key=lambda q: (-q.leverage, q.edge))
    questions.extend(orient)

    note = (
        f"有 {len(result.conflicts)} 个冲突需要裁决；"
        f"另有 {len(orient)} 个定向问题，覆盖 {len(undirected)} 条尚未定向的边，"
        f"按最好情况下能撬动多少条边排序（最高 "
        f"{orient[0].leverage if orient else 0}）"
    )
    return QuestionSet(
        nodes=nodes,
        input_directed=tuple(result.input_directed),
        input_undirected=tuple(result.input_undirected),
        constraints=tuple(result.constraints),
        oriented=tuple(result.oriented),
        remaining_undirected=tuple(result.remaining_undirected),
        questions=tuple(questions),
        asserted_adjacencies=tuple(result.asserted_adjacencies),
        asserted_absences=tuple(result.asserted_absences),
        note=note,
    )


def question_set_to_dict(qs: QuestionSet) -> dict:
    """JSON-serialisable view — the artifact ``verify_orientation_questions``
    consumes. Checked against its own declared shape on the way out."""
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact({
        "kind": "orientation_question_set",
        "nodes": list(qs.nodes),
        "input_directed": [list(e) for e in qs.input_directed],
        "input_undirected": [list(e) for e in qs.input_undirected],
        "constraints": [list(e) for e in qs.constraints],
        "oriented": [list(e) for e in qs.oriented],
        "remaining_undirected": [list(e) for e in qs.remaining_undirected],
        "asserted_adjacencies": [list(e) for e in qs.asserted_adjacencies],
        "asserted_absences": [list(e) for e in qs.asserted_absences],
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
    })
