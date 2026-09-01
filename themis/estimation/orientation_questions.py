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
from enum import unique

from .. import language
from .orientation import OrientationResult, propagate_orientations

Edge = tuple[str, str]
Pair = tuple[str, str]

#: How a list of arrow notations is joined inside a hole. A value travels
#: rendered, once, so a joiner chosen here is frozen into every language —
#: which is why this one is the neutral punctuation rather than the Chinese
#: enumeration comma the branches used to write. What goes in these holes is
#: a formula (``a→c←b``), and a formula is not prose in either language.
_AND = ", "


@unique
class Asks(language.Word, vocabulary="orientation_asks",
           between=language.BETWEEN_SENTENCES):
    """What an orientation session is putting to a person, by name.

    These were a twelve-branch cascade of f-strings, and the branches were
    already this table: every one tested a ``reason`` the propagation
    artifact owns and wrote a finished Chinese sentence for it. A finished
    sentence makes the site the author, and a site does not know who is
    reading — so the whole interactive surface of this feature, the
    questions the tool actually puts to a person, existed in one language.

    Not a missing translation. The field these went into is declared
    ``"A phrasing for a human. Rendering, not data"`` in the artifact's
    own schema, so there was nowhere else for a sentence to go: what was
    missing was the SLOT, exactly as ``discovery.py``'s note records for
    its own six. A member here carries both languages beside each other,
    the occasion's names arrive as holes, and the surface that knows the
    reader renders it.
    """

    # --- the question itself ----------------------------------------------

    # The reach is a second sentence rather than a parenthesis after the
    # mark: a member of this set is joined to the next by the gap that
    # FOLLOWS a sentence's mark, and a trailing aside leaves the pair with
    # no boundary at all.
    WHICH_DIRECTION = (
        "which_direction",
        {"zh": "是 {a} 导致 {b}，还是 {b} 导致 {a}？最多能定下 {most} 条边。",
         "en": "does {a} cause {b}, or {b} cause {a}? It settles at most "
               "{most} edge(s)."})
    WHICH_DIRECTION_AND_UNLOCKS = (
        "which_direction_and_unlocks",
        {"zh": "是 {a} 导致 {b}，还是 {b} 导致 {a}？最多能定下 {most} 条边；"
               "答案若走运，还能顺带定下 {also}。",
         "en": "does {a} cause {b}, or {b} cause {a}? It settles at most "
               "{most} edge(s), and a lucky answer also settles {also}."})

    # --- the graph is the pattern of no DAG at all ------------------------

    NO_CONSISTENT_EXTENSION = (
        "no_consistent_extension",
        {"zh": "这张图不是任何一张 DAG 的 pattern：把它补全成一张 DAG 的路走不"
               "通。断在 {where} 上——{a} 与 {b} 不相邻，却都连着 {where}，而那里"
               "还有边没有方向，往哪边定都会出现一个 {made} 这样的无屏蔽对撞，"
               "可数据并没有报告它。这不是某一条边的毛病，{where} 只是能看见它的"
               "一处：骨架和数据给的那些对撞本身就不可能同时为真。要回到画这张图"
               "或做独立性检验的那一步。",
         "en": "this graph is the pattern of no DAG: there is no way to "
               "complete it into one. It breaks at {where} — {a} and {b} are "
               "not adjacent yet both meet {where}, where edges are still "
               "undirected, and orienting them either way produces an "
               "unshielded collider like {made} that the data did not "
               "report. No single edge is at fault; {where} is only where it "
               "shows. The skeleton and the colliders the data gave cannot "
               "both be true. Go back to drawing the graph, or to the "
               "independence tests."})
    ANSWERS_FORCE_AN_UNSHIELDED_COLLIDER = (
        "answers_force_an_unshielded_collider",
        {"zh": "{a} 与 {b} 不相邻，而到目前为止的回答把 {made} 的两条臂都逼了"
               "出来——这是一个无屏蔽对撞，数据并没有报告它。骨架、数据给的那些"
               "对撞、到目前为止的回答，这三样不可能同时为真：没有任何一张 DAG "
               "同时满足它们。要放弃哪一样——补一条 {a}–{b}，还是撤回一个回答？",
         "en": "{a} and {b} are not adjacent, and the answers so far force "
               "both arms of {made} — an unshielded collider the data did "
               "not report. The skeleton, the colliders the data gave and "
               "the answers so far cannot all three be true: no DAG "
               "satisfies them together. Which goes — add an edge {a}–{b}, "
               "or withdraw an answer?"})

    # --- a declared ABSENCE the data contradicts --------------------------

    ABSENCE_UNDERMINES_A_COLLIDER = (
        "absence_undermines_a_collider",
        {"zh": "知识说 {a} 与 {b} 独立（该删掉这条边），但数据把 {arm} 定向成了"
               "一个无屏蔽对撞的一条臂。删掉这条边就等于拿掉那条臂，对撞也就失去"
               "了数据支持。是信数据给的对撞，还是照知识删边？",
         "en": "knowledge says {a} and {b} are independent (drop the edge), "
               "but the data oriented {arm} as an arm of an unshielded "
               "collider. Dropping the edge removes that arm, and the "
               "collider loses the support the data gave it. Trust the "
               "collider the data found, or drop the edge as knowledge "
               "says?"})
    ABSENCE_CONTRADICTS_DEPENDENCE = (
        "absence_contradicts_dependence",
        {"zh": "知识说 {a} 与 {b} 独立（没有边），但数据发现它们相依——骨架里有"
               "一条 {a}–{b}。是信数据的相依结论，还是照断言把这条边删掉？",
         "en": "knowledge says {a} and {b} are independent (no edge), but "
               "the data found them dependent — the skeleton holds "
               "{a}–{b}. Trust the dependence the data found, or drop the "
               "edge as asserted?"})
    ABSENCE_NAMES_AN_UNKNOWN_NODE = (
        "absence_names_an_unknown_node",
        {"zh": "断言的缺边 {a}–{b} 里有图上没有的变量。",
         "en": "the asserted absence {a}–{b} names a variable that is not "
               "in the graph."})
    ABSENCE_CONFLICTS = (
        "absence_conflicts",
        {"zh": "断言的缺边 {a}–{b} 与数据冲突（{reason}）。",
         "en": "the asserted absence {a}–{b} conflicts with the data "
               "({reason})."})

    # --- a declared ADJACENCY the data contradicts ------------------------

    ADJACENCY_UNDERMINES_A_COLLIDER = (
        "adjacency_undermines_a_collider",
        {"zh": "知识说 {a} 与 {b} 直接相连，但数据发现它们独立——而这正是对撞 "
               "{apex} 的「无屏蔽」前提。若二者相邻，那些定向就没有数据支持了。"
               "是信数据的独立性检验，还是信断言的这条边？",
         "en": "knowledge says {a} and {b} are directly connected, but the "
               "data found them independent — which is exactly what makes "
               "the collider {apex} unshielded. If they are adjacent, those "
               "orientations lose the support the data gave them. Trust the "
               "independence test, or the asserted edge?"})
    ADJACENCY_CONTRADICTS_INDEPENDENCE = (
        "adjacency_contradicts_independence",
        {"zh": "知识说 {a} 与 {b} 直接相连，但数据发现它们条件独立（没有边）。"
               "是信数据的独立性检验，还是信断言的这条边？",
         "en": "knowledge says {a} and {b} are directly connected, but the "
               "data found them conditionally independent (no edge). Trust "
               "the independence test, or the asserted edge?"})
    ADJACENCY_NAMES_AN_UNKNOWN_NODE = (
        "adjacency_names_an_unknown_node",
        {"zh": "断言的相邻 {a}–{b} 里有图上没有的变量。",
         "en": "the asserted adjacency {a}–{b} names a variable that is not "
               "in the graph."})
    ADJACENCY_CONFLICTS = (
        "adjacency_conflicts",
        {"zh": "断言的相邻 {a}–{b} 与数据冲突（{reason}）。",
         "en": "the asserted adjacency {a}–{b} conflicts with the data "
               "({reason})."})

    # --- a proposed DIRECTION that will not apply -------------------------

    DIRECTION_CONTRADICTS_THE_DATA = (
        "direction_contradicts_the_data",
        {"zh": "数据确立了 {settled}（一个无屏蔽对撞），而提出的方向是 "
               "{proposed}。是保留数据给的定向，还是明知而覆盖它？",
         "en": "the data settled {settled} (an unshielded collider), and "
               "the direction proposed is {proposed}. Keep the orientation "
               "the data gave, or override it knowingly?"})
    DIRECTION_NEEDS_AN_EDGE = (
        "direction_needs_an_edge",
        {"zh": "{a} 与 {b} 在图上不相邻，所以 {proposed} 无法应用。是漏了一条 "
               "{a}–{b}，还是这个方向本身站不住？",
         "en": "{a} and {b} are not adjacent in the graph, so {proposed} "
               "cannot apply. Is an edge {a}–{b} missing, or does the "
               "direction itself not hold?"})
    DIRECTION_MAKES_A_CYCLE = (
        "direction_makes_a_cycle",
        {"zh": "{proposed} 会和已确立的定向合成一个有向环——到目前为止的这些回答"
               "不可能同时成立。要改哪一个？",
         "en": "{proposed} closes a directed cycle with the orientations "
               "already settled — the answers so far cannot all hold. Which "
               "one changes?"})
    DIRECTION_NAMES_AN_UNKNOWN_NODE = (
        "direction_names_an_unknown_node",
        {"zh": "{proposed} 里有图上没有的变量。",
         "en": "{proposed} names a variable that is not in the graph."})
    DIRECTION_CONFLICTS = (
        "direction_conflicts",
        {"zh": "约束 {proposed} 没能应用（{reason}）。",
         "en": "the constraint {proposed} did not apply ({reason})."})


@unique
class Says(language.Word, vocabulary="orientation_question_set_says",
           between=language.BETWEEN_STATEMENTS):
    """What the compiled set says about itself.

    One member, and it is here rather than left as an f-string for the
    reason the questions are: the ``note`` field this goes in is a rendered
    string in the schema of all six standalone artifacts, and a rendered
    string has no second language to be written beside it.
    """

    THE_SET = (
        "the_set",
        {"zh": "有 {conflicts} 个冲突需要裁决；另有 {questions} 个定向问题，"
               "覆盖 {edges} 条尚未定向的边，按最好情况下能撬动多少条边排序"
               "（最高 {top}）",
         "en": "{conflicts} conflict(s) to adjudicate; then {questions} "
               "orientation question(s) covering {edges} undirected edge(s), "
               "ranked by how many edges an answer could settle at best "
               "(highest {top})"})


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
    - ``asks``: which question this is and this occasion's names for it,
      as :class:`themis.language.Statement` carries the pair. Not a
      phrasing: it was ``prompt``, a finished string, and a finished
      string is written in whichever language the site was written in.
      :func:`asked` is the reader's door.
    """

    kind: str
    edge: Edge
    leverage: int
    guaranteed: int
    unlocks: tuple[Pair, ...]
    reason: str
    detail: dict
    asks: language.Statement


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
    says: language.Statement | None = None
    """What the set says about itself, as a statement rather than a
    sentence. It was ``note``, and ``note`` is a rendered string in the
    schema of all six standalone artifacts — the one channel #395 could
    not reach, because a string field leaves a writer nowhere to put a
    second language. This is that channel's first member."""


def _pair(a: str, b: str) -> Pair:
    return (a, b) if a <= b else (b, a)


def _cascade(nodes, directed, undirected, u_set: set[frozenset], answer: Edge) -> set[Pair]:
    """The undirected edges determined by answering ``answer`` — the Meek closure
    of the single constraint, restricted to the originally-undirected edges."""
    r = propagate_orientations(nodes, directed=directed, undirected=undirected,
                               constraints=[answer])
    return {_pair(*e) for e in r.oriented if frozenset(e) in u_set}


def _conflict_asks(c: dict) -> language.Statement:
    """Which question this conflict is, and this occasion's names for it.

    The branch structure is the one the f-strings had, because it was
    never about the wording: each test reads a ``reason`` the propagation
    artifact owns, and picking the species is the whole of what the old
    cascade did before it started writing prose.
    """
    reason = c.get("reason")
    if "forced_collider" in c:
        a, b = c["forced_collider"]
        apexes = c.get("colliders", [])
        made = _AND.join(f"{a}→{x}←{b}" for x in apexes)
        if reason == "no_consistent_extension":
            return language.state(Asks.NO_CONSISTENT_EXTENSION, a=a, b=b,
                                  where=_AND.join(apexes), made=made)
        return language.state(Asks.ANSWERS_FORCE_AN_UNSHIELDED_COLLIDER,
                              a=a, b=b, made=made)
    if "absence" in c:
        a, b = c["absence"]
        if reason == "undermines_collider":
            return language.state(
                Asks.ABSENCE_UNDERMINES_A_COLLIDER, a=a, b=b,
                arm=_AND.join(f"{a if x == b else b}→{x}"
                              for x in c.get("colliders", [])))
        if reason == "contradicts_dependence":
            return language.state(Asks.ABSENCE_CONTRADICTS_DEPENDENCE,
                                  a=a, b=b)
        if reason == "unknown_node":
            return language.state(Asks.ABSENCE_NAMES_AN_UNKNOWN_NODE, a=a, b=b)
        return language.state(Asks.ABSENCE_CONFLICTS, a=a, b=b, reason=reason)
    if "assertion" in c:
        a, b = c["assertion"]
        if reason == "undermines_collider":
            return language.state(
                Asks.ADJACENCY_UNDERMINES_A_COLLIDER, a=a, b=b,
                apex=_AND.join(f"{a}→{c0}←{b}"
                               for c0 in c.get("colliders", [])))
        if reason == "contradicts_independence":
            return language.state(Asks.ADJACENCY_CONTRADICTS_INDEPENDENCE,
                                  a=a, b=b)
        if reason == "unknown_node":
            return language.state(Asks.ADJACENCY_NAMES_AN_UNKNOWN_NODE,
                                  a=a, b=b)
        return language.state(Asks.ADJACENCY_CONFLICTS, a=a, b=b, reason=reason)
    a, b = c["constraint"]
    proposed = f"{a}→{b}"
    if reason == "contradicts_data_orientation":
        d = c.get("data_edge", [b, a])
        return language.state(Asks.DIRECTION_CONTRADICTS_THE_DATA,
                              settled=f"{d[0]}→{d[1]}", proposed=proposed)
    if reason == "non_adjacent_pair":
        return language.state(Asks.DIRECTION_NEEDS_AN_EDGE, a=a, b=b,
                              proposed=proposed)
    if reason == "creates_cycle":
        return language.state(Asks.DIRECTION_MAKES_A_CYCLE, proposed=proposed)
    if reason == "unknown_node":
        return language.state(Asks.DIRECTION_NAMES_AN_UNKNOWN_NODE,
                              proposed=proposed)
    return language.state(Asks.DIRECTION_CONFLICTS, proposed=proposed,
                          reason=reason)


def asked(question, lang: language.Lang | str = language.DEFAULT) -> str:
    """One question as the sentence this reader gets.

    The reader's half of :func:`_conflict_asks`, and the door a caller
    driving the interactive loop puts in front of a person. Takes the
    dataclass or the envelope's dict for the reason
    :func:`themis.gaps.shortfall` does: which side of the serialization
    boundary a caller is on is not this function's question.
    """
    entry = question.get("asks") if isinstance(question, dict) else question.asks
    return language.spoke(entry, lang)


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
            asks=_conflict_asks(c),
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
        # Two species rather than one with an optional tail: the tail was a
        # clause built at the site, and a clause built at the site is a
        # sentence with a second author. Which one it is turns on whether
        # there is anything to name, which is the test the tail already
        # made — and a question ending "also settles" with nothing after
        # the verb is the defect this file's own test is named for.
        also = sorted((fwd | bwd) - {e})
        orient.append(OrientationQuestion(
            kind="orientation", edge=e, leverage=leverage, guaranteed=guaranteed,
            unlocks=unlocks, reason="", detail=detail,
            asks=(
                language.state(Asks.WHICH_DIRECTION_AND_UNLOCKS, a=a, b=b,
                               most=leverage,
                               also=_AND.join(f"{u}–{v}" for (u, v) in also))
                if also else
                language.state(Asks.WHICH_DIRECTION, a=a, b=b, most=leverage)
            ),
        ))
    orient.sort(key=lambda q: (-q.leverage, q.edge))
    questions.extend(orient)

    says = language.state(
        Says.THE_SET,
        conflicts=len(result.conflicts), questions=len(orient),
        edges=len(undirected),
        top=orient[0].leverage if orient else 0,
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
        says=says,
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
                "asks": dict(q.asks),
            }
            for q in qs.questions
        ],
        **({"says": dict(qs.says)} if qs.says else {}),
    })
