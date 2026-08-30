"""Interactive orientation-resolution session
(2026-07-17, interactive equivalence-class resolution — Phase 3).

Phase 1 (``propagate_orientations``) closes a CPDAG under direction constraints;
Phase 2 (``compile_orientation_questions``) ranks the questions to ask about the
edges still undetermined. Phase 3 runs the *loop* around them: it ingests the
answers (from a human or an LLM), feeds the directional ones back through the
Phase 1 closure — which cascades and removes every edge that answer determined —
re-compiles the Phase 2 questions over what remains, and reports whether the
graph is resolved, still open, or blocked on answers only a human can give.

The session is **event-sourced**: it stores nothing but the immutable input CPDAG
and the ordered list of answers. Every derived quantity (the current orientation,
the remaining edges, the next questions, the provenance) is recomputed from that
list by replaying the Phase 1 closure. This is deliberate — it is the cheapest
thing to verify independently (replay the same answers, compare), and it keeps
the kernel a pure function of its recorded inputs. There is NO LLM in this
module: the LLM (or human) produces the answer JSON at the front door; the kernel
only validates, applies, and audits it.

An answer is about a pair, and it makes exactly ONE claim about that pair: a
*direction* (a→b), an *adjacency polarity* (``"present"`` — the edge exists / add
it; ``"absent"`` — the edge does not exist / drop it), or *nothing* ("unknown").
A direction feeds the Phase 1 closure as a constraint; an adjacency polarity feeds
the producer's CI-side / drop-edge conflict detection (an asserted adjacency the
data found absent, or an asserted absence the data found present, surfaces as a
conflict question — never applied, since either would edit the skeleton); an
unknown defers. The three are on equal footing and latest-wins is per pair ACROSS
all of them.

Three things the loop does that a one-shot pass does not:

- **Unknown escape.** An answer may decline to say anything about a pair
  (``direction=None`` and ``adjacency=None``). That edge is recorded as *deferred*
  and is NOT asked again — forcing an answer is exactly how a silent wrong
  orientation gets injected, so "I don't know" is a first-class, safe outcome.
  When the only edges left are deferred, the session is ``blocked`` and hands back
  to a human rather than guessing.
- **Revision (latest-wins).** A later answer for the same pair replaces an
  earlier one — regardless of kind — so a human can change "unknown" into a
  direction, retract an adjacency claim back to agnostic, or flip a direction into
  a drop-edge assertion, and the closure is simply replayed. Only each pair's
  latest answer counts.
- **Source trail.** Every applied directional answer is recorded with its source
  (``"llm_proposal"`` / ``"human"`` / ``"temporal_order"`` / …) and its
  *entailment* — the edges the Phase 1 closure forced from it. If that answer
  turns out to be wrong, the edges resting on it are explicit (its blast radius),
  the discovery-session-level analogue of the query envelope's assumption ledger.

Composition and scope (stated): a session artifact embeds a Phase 1
``orientation_propagation`` dict and a Phase 2 ``orientation_question_set`` dict,
each audited by its own verifier; the session verifier adds only the glue checks
(answers → constraints, unknown → deferred, the source trail, the status). A
directional answer that contradicts a data-established orientation is NOT applied
— it flows into the Phase 1 conflict list and surfaces as a conflict question for
a human, never silently overriding the data. An adjacency claim is likewise never
applied: an asserted adjacency the data found absent surfaces as a CI-side conflict
question (``contradicts_independence`` / ``undermines_collider``); an asserted
absence the data found present surfaces as a drop-edge conflict question
(``contradicts_dependence`` / ``undermines_collider``) — the two polarities of the
independence-side analogue of a direction conflict, both surfaced for a human
(applying either would edit the skeleton = re-run discovery). ``start``'s
``asserted_adjacencies`` / ``asserted_absences`` are the *base* (turn-0 upfront
knowledge); a per-turn adjacency answer OVERRIDES its pair's base membership by the
same latest-wins projection that governs directions, so the two sets actually fed
to the closure — the base with every answered pair re-projected from its latest
answer — are the *effective* sets echoed inside the embedded propagation artifact,
and it is those the session verifier re-derives and ties to. Wiring
the source trail into the
query-level ``assumption_ledger`` (the existing ``GRAPH_LEARNED_FROM_DATA`` /
``llm_proposal`` gap-kind path) happens when a resolved graph is USED in a query,
and is not redone here. CPDAG setting (causal sufficiency), inherited from
Phase 1. No library dependency.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import unique

from .orientation import (
    OrientationResult,
    orientation_to_dict,
    propagate_orientations,
)
from .orientation_questions import (
    QuestionSet,
    compile_orientation_questions,
    question_set_to_dict,
)
from .. import language
from .refusal_words import Refuses

Edge = tuple[str, str]
Pair = tuple[str, str]


@unique
class Says(language.Word, vocabulary="orientation_session_says"):
    """What a turn of the session says about itself.

    The counts, and then what the status MEANS — because the status is a
    word a person needs and the enum beside it is excused from a gloss on
    the grounds that this field says it in a sentence. Three members rather
    than one with the token interpolated: the distinction the enum exists
    for is ``blocked`` against ``open``, both of which leave edges
    undetermined, and only one of which another turn can fix. That is a
    difference in what to DO next, which is a sentence and not a word.
    """

    INGESTED_THE_ANSWERS = ("ingested_the_answers", {
        "zh": "读入 {answers} 条回答：已定向 {oriented} 条，"
              "{undetermined} 条方向待定（其中 {deferred} 条被搁置），"
              "{conflicts} 处冲突。",
        "en": "{answers} answers ingested: {oriented} oriented, "
              "{undetermined} still undetermined ({deferred} of them "
              "deferred), {conflicts} conflicts.",
    })
    STILL_WORTH_ASKING = ("still_worth_asking", {
        "zh": "还有可问的——要么有边等着定向，要么有冲突等着裁决。",
        "en": "there is still something worth asking — an edge to orient or "
              "a conflict to adjudicate.",
    })
    NOTHING_LEFT_TO_ASK = ("nothing_left_to_ask", {
        "zh": "没有待定的边，也没有要裁决的冲突——这一等价类已经收敛到一张图。",
        "en": "nothing is undetermined and nothing is left to adjudicate — "
              "the equivalence class has collapsed to one graph.",
    })
    EVERY_REMAINING_EDGE_IS_DEFERRED = (
        "every_remaining_edge_is_deferred", {
            "zh": "还有边没定向，但每一条都已被搁置——再问一轮不会有进展，"
                  "得有人改主意。",
            "en": "edges remain undetermined and every one of them has been "
                  "deferred — another turn will not move this, somebody has "
                  "to change their mind.",
        })


#: Which sentence each status is. The status is decided one place and said
#: another, and a mapping is what keeps the two from being two records: a
#: status added without a sentence fails the completeness check below rather
#: than reaching a reader as a token.
SAYS_STATUS: dict[str, Says] = {
    "open": Says.STILL_WORTH_ASKING,
    "resolved": Says.NOTHING_LEFT_TO_ASK,
    "blocked": Says.EVERY_REMAINING_EDGE_IS_DEFERRED,
}


class OrientationSessionError(language.Voiced, ValueError):
    """An answer is ill-formed — its direction is not a permutation of its edge,
    or it references an unknown node. Preferred over silently dropping it.

    A :class:`themis.language.Voiced`: it carries the species and this
    occasion's facts, and the sentence is
    :class:`themis.estimation.refusal_words.Refuses`' rather than the
    raise site's. ``ValueError`` as well, because that is what a caller
    has always been able to catch.
    """


@dataclass(frozen=True)
class OrientationAnswer:
    """One answer about one pair — a direction, an adjacency polarity, or unknown.

    - ``edge``: the undirected pair the answer is about, ``(a, b)`` with ``a<=b``.
    - ``direction``: the claimed causal direction ``(a, b)`` (a→b) — a permutation
      of ``edge`` — or ``None`` when the answer is not a direction.
    - ``adjacency``: ``"present"`` (assert the edge exists / add it) or ``"absent"``
      (assert it does not / drop it), or ``None``. Mutually exclusive with a set
      ``direction`` (a direction already implies the edge is present, and orients
      it). Feeds the producer's CI-side / drop-edge conflict detection, never the
      closure — an adjacency claim is surfaced, not applied.
    - ``direction=None`` AND ``adjacency=None`` is the "unknown" escape hatch.
    - ``source``: who produced it (``"llm_proposal"`` / ``"human"`` /
      ``"temporal_order"`` / ``"domain_knowledge"`` / …). Recorded, not trusted.
    - ``note``: optional free text.
    """

    edge: Pair
    direction: Edge | None
    adjacency: str | None = None
    source: str = "unspecified"
    note: str = ""


@dataclass(frozen=True)
class OrientationSession:
    """The full state of an orientation-resolution loop (event-sourced).

    - ``answers``: the ordered history (the only mutable input across ingests).
    - ``constraints``: the directional answers actually fed to the Phase 1 closure
      — each edge's latest directional answer, in the order that latest answer
      appeared (earlier revisions dropped).
    - ``result`` / ``question_set``: the Phase 1 closure and the Phase 2 question
      set derived from replaying ``constraints``.
    - ``deferred``: edges whose latest answer was "unknown" and that are still
      undetermined — not asked again.
    - ``source_trail``: one entry per applied directional answer (edge, direction,
      source, note, and the edges it entailed via the closure).
    - ``rejected``: directional answers the closure could not apply (they conflict
      with the data or an earlier answer) — joined back to their source.
    - ``asserted_adjacencies``: the BASE adjacencies external knowledge claims
      (turn-0 upfront knowledge given at ``start``). Per-turn ``adjacency="present"``
      answers override membership by latest-wins; the *effective* set fed to the
      closure (those the data found absent surface as CI-side conflict questions)
      lives in the embedded propagation artifact.
    - ``asserted_absences``: the BASE non-adjacencies (edges to drop) external
      knowledge claims (turn-0, given at ``start``). Per-turn ``adjacency="absent"``
      answers override membership by latest-wins; the *effective* set (those the
      data found present surface as drop-edge conflict questions) lives in the
      embedded propagation artifact.
    - ``status``: ``"resolved"`` (nothing undetermined), ``"open"`` (askable
      questions remain), or ``"blocked"`` (only deferred edges remain).
    """

    nodes: tuple[str, ...]
    input_directed: tuple[Edge, ...]
    input_undirected: tuple[Pair, ...]
    answers: tuple[OrientationAnswer, ...]
    constraints: tuple[Edge, ...]
    result: OrientationResult
    question_set: QuestionSet
    deferred: tuple[Pair, ...]
    source_trail: tuple[dict, ...]
    rejected: tuple[dict, ...]
    status: str
    asserted_adjacencies: tuple[Pair, ...] = ()
    asserted_absences: tuple[Pair, ...] = ()
    note: tuple[language.Statement, ...] = ()


def _pair(a: str, b: str) -> Pair:
    return (a, b) if a <= b else (b, a)


def _coerce_answer(a, nodes: set) -> OrientationAnswer:
    """Accept an ``OrientationAnswer`` or a dict and normalise it. A directional
    answer is ``{"direction": [a, b]}`` (edge inferred); an adjacency answer is
    ``{"edge": [a, b], "adjacency": "present"|"absent"}``; an unknown answer is
    ``{"edge": [a, b], "direction": None}`` (no adjacency either)."""
    if isinstance(a, OrientationAnswer):
        ans = a
    elif isinstance(a, dict):
        direction = a.get("direction")
        adjacency = a.get("adjacency")
        edge = a.get("edge")
        if direction is not None:
            direction = (direction[0], direction[1])
            edge = _pair(direction[0], direction[1])
        else:
            if edge is None:
                raise OrientationSessionError(
                    Refuses.AN_ANSWER_MUST_NAME_ITS_EDGE)
            edge = _pair(edge[0], edge[1])
        ans = OrientationAnswer(edge=edge, direction=direction, adjacency=adjacency,
                                source=a.get("source", "unspecified"),
                                note=a.get("note", ""))
    else:
        raise OrientationSessionError(Refuses.ANSWER_IS_NOT_AN_ANSWER,
                                      got=type(a).__name__)

    e = _pair(ans.edge[0], ans.edge[1])
    if e[0] not in nodes or e[1] not in nodes:
        raise OrientationSessionError(Refuses.EDGE_NAMES_AN_UNKNOWN_NODE,
                                      where="answer", edge=list(ans.edge))
    if e[0] == e[1]:
        raise OrientationSessionError(Refuses.SELF_LOOP, where="answer",
                                      edge=list(ans.edge))
    if ans.direction is not None:
        d = tuple(ans.direction)
        if {d[0], d[1]} != {e[0], e[1]} or d[0] == d[1]:
            raise OrientationSessionError(
                Refuses.DIRECTION_IS_NOT_OF_THIS_EDGE,
                direction=list(ans.direction), edge=list(e))
        if ans.adjacency is not None:
            raise OrientationSessionError(
                Refuses.AN_ANSWER_STATES_ONE_OR_THE_OTHER)
        return OrientationAnswer(edge=e, direction=(d[0], d[1]), adjacency=None,
                                 source=ans.source, note=ans.note)
    if ans.adjacency is not None:
        if ans.adjacency not in ("present", "absent"):
            raise OrientationSessionError(
                Refuses.ADJACENCY_IS_LIMITED_TO,
                accepted=["present", "absent"], got=ans.adjacency)
        return OrientationAnswer(edge=e, direction=None, adjacency=ans.adjacency,
                                 source=ans.source, note=ans.note)
    return OrientationAnswer(edge=e, direction=None, adjacency=None,
                             source=ans.source, note=ans.note)


def _derive_answer_sets(answers: tuple[OrientationAnswer, ...]):
    """Project the answer history by latest-wins per pair. Each pair's LATEST
    answer decides its contribution:

    - a direction  → a constraint (ordered by where that latest answer appeared);
    - ``adjacency="present"`` → the pair is an answer-asserted adjacency;
    - ``adjacency="absent"``  → the pair is an answer-asserted absence;
    - unknown → neither (a deferred candidate).

    Returns ``(constraints, adj_pairs, abs_pairs, latest_by_edge)``."""
    latest: dict[Pair, tuple[int, OrientationAnswer]] = {}
    for i, ans in enumerate(answers):
        latest[ans.edge] = (i, ans)
    ordered = sorted(latest.items(), key=lambda kv: kv[1][0])
    constraints = tuple(ans.direction for (_e, (_i, ans)) in ordered
                        if ans.direction is not None)
    adj_pairs = {e for e, (_i, ans) in latest.items() if ans.adjacency == "present"}
    abs_pairs = {e for e, (_i, ans) in latest.items() if ans.adjacency == "absent"}
    latest_by_edge = {e: ans for (e, (_i, ans)) in latest.items()}
    return constraints, adj_pairs, abs_pairs, latest_by_edge


def _build(nodes, input_directed, input_undirected,
           answers: tuple[OrientationAnswer, ...],
           base_adjacencies=(), base_absences=()) -> OrientationSession:
    node_set = set(nodes)
    constraints, adj_answers, abs_answers, latest_by_edge = _derive_answer_sets(answers)

    # effective asserted sets = base (turn-0), with every ANSWERED pair re-projected
    # from its latest answer (an adjacency answer overrides the base membership; a
    # direction or unknown answer drops the pair from both bases). Latest-wins is
    # per pair across all answer kinds, exactly as it is for direction constraints.
    answered = set(latest_by_edge)
    base_adj = {_pair(a, b) for (a, b) in base_adjacencies}
    base_abs = {_pair(a, b) for (a, b) in base_absences}
    eff_adjacencies = tuple(sorted({p for p in base_adj if p not in answered} | adj_answers))
    eff_absences = tuple(sorted({p for p in base_abs if p not in answered} | abs_answers))

    result = propagate_orientations(
        nodes, directed=input_directed, undirected=input_undirected,
        constraints=constraints, asserted_adjacencies=eff_adjacencies,
        asserted_absences=eff_absences,
    )
    question_set = compile_orientation_questions(result)

    oriented = set(result.oriented)
    remaining = set(result.remaining_undirected)

    # deferred = edges whose latest answer was "unknown" (neither a direction nor
    # an adjacency polarity) and that are still undetermined
    deferred = tuple(sorted(
        e for e, ans in latest_by_edge.items()
        if ans.direction is None and ans.adjacency is None and e in remaining
    ))

    # source trail: each applied directional answer + the edges it entailed.
    # Only orientation-constraint conflicts correspond to an answer; the CI-side
    # adjacency conflicts come from the session-level asserted adjacencies, not
    # from any directional answer, so they are excluded here.
    conflict_pairs = {_p(c["constraint"]) for c in result.conflicts if "constraint" in c}
    prov_roots = {(p["from"], p["to"]): {tuple(r) for r in p["roots"]}
                  for p in result.provenance}
    source_trail = []
    rejected = []
    for ans in [latest_by_edge[e] for e in sorted(latest_by_edge)]:
        if ans.direction is None:
            continue
        d = ans.direction
        if d in oriented and _pair(*d) not in conflict_pairs:
            entails = sorted(
                [list(edge) for edge, roots in prov_roots.items()
                 if d in roots and edge != d]
            )
            source_trail.append({
                "edge": list(ans.edge), "direction": [d[0], d[1]],
                "source": ans.source, "note": ans.note, "entails": entails,
            })
        else:
            reason = next((c.get("reason") for c in result.conflicts
                           if "constraint" in c
                           and (_p(c["constraint"]) == _pair(*d)
                                or tuple(c["constraint"]) == d)), "not_applied")
            rejected.append({
                "edge": list(ans.edge), "direction": [d[0], d[1]],
                "source": ans.source, "reason": reason,
            })

    askable = [q for q in question_set.questions
               if q.kind == "conflict"
               or (q.kind == "orientation" and q.edge not in set(deferred))]
    if askable:
        status = "open"          # a conflict to adjudicate or a non-deferred edge to ask
    elif not remaining:
        status = "resolved"      # nothing undetermined, nothing to adjudicate
    else:
        status = "blocked"       # edges remain but all are deferred (needs a human)

    note = (
        language.state(
            Says.INGESTED_THE_ANSWERS,
            answers=len(answers), oriented=len(oriented),
            undetermined=len(remaining), deferred=len(deferred),
            conflicts=len(result.conflicts),
        ),
        language.state(SAYS_STATUS[status]),
    )
    return OrientationSession(
        nodes=tuple(result.nodes),
        input_directed=tuple(result.input_directed),
        input_undirected=tuple(result.input_undirected),
        answers=answers,
        constraints=constraints,
        result=result,
        question_set=question_set,
        deferred=deferred,
        source_trail=tuple(source_trail),
        rejected=tuple(rejected),
        status=status,
        asserted_adjacencies=tuple(sorted(base_adj)),
        asserted_absences=tuple(sorted(base_abs)),
        note=note,
    )


def _p(pair) -> Pair:
    return _pair(pair[0], pair[1])


def start_orientation_session(nodes, *, directed=(), undirected=(),
                              asserted_adjacencies=(),
                              asserted_absences=()) -> OrientationSession:
    """Open a session on a CPDAG (data colliders ``directed`` + undetermined
    ``undirected``) with no answers yet — the initial questions are Phase 2's
    ranking over the whole undetermined part, plus any conflict question raised by
    ``asserted_adjacencies`` (adjacencies external knowledge claims that the data's
    independence structure contradicts) or ``asserted_absences`` (non-adjacencies /
    edges to drop that the data's dependence structure contradicts). Both are the
    *base* (turn-0 knowledge); per-turn ``adjacency`` answers ingested later
    override them pair-by-pair (see ``ingest_orientation_answers``)."""
    nodes = tuple(sorted(nodes))
    # normalise input edges through a trivial propagate to reuse its guards
    directed = tuple((a, b) for (a, b) in directed)
    undirected = tuple((a, b) for (a, b) in undirected)
    asserted_adjacencies = tuple((a, b) for (a, b) in asserted_adjacencies)
    asserted_absences = tuple((a, b) for (a, b) in asserted_absences)
    return _build(nodes, directed, undirected, (),
                  base_adjacencies=asserted_adjacencies,
                  base_absences=asserted_absences)


def ingest_orientation_answers(session: OrientationSession, answers) -> OrientationSession:
    """Append ``answers`` (dicts or ``OrientationAnswer``) to the session and
    replay the Phase 1 closure over the full history. Returns a new session (the
    input is not mutated). A directional answer contradicting the data is not
    applied — it surfaces as a conflict; an ``adjacency`` answer overrides its
    pair's base membership (surfaced as a CI-side / drop-edge conflict, never
    applied); an "unknown" answer defers its edge."""
    node_set = set(session.nodes)
    coerced = tuple(_coerce_answer(a, node_set) for a in answers)
    return _build(session.nodes, session.input_directed, session.input_undirected,
                  session.answers + coerced,
                  base_adjacencies=session.asserted_adjacencies,
                  base_absences=session.asserted_absences)


def next_questions(session: OrientationSession) -> tuple:
    """The questions still worth asking: all conflict questions, plus the
    orientation questions on edges NOT deferred, in the Phase 2 ranking."""
    deferred = set(session.deferred)
    return tuple(
        q for q in session.question_set.questions
        if q.kind == "conflict" or (q.kind == "orientation" and q.edge not in deferred)
    )


def session_to_dict(session: OrientationSession) -> dict:
    """JSON-serialisable view — the artifact ``verify_orientation_session``
    consumes. Embeds the Phase 1 and Phase 2 artifacts verbatim so their own
    verifiers can audit them, and is checked against its own declared shape on
    the way out — which reaches those two as well, since the schema references
    theirs rather than restating them."""
    from ..input.syntactic_validator import validate_artifact

    return validate_artifact({
        "kind": "orientation_session",
        "nodes": list(session.nodes),
        "input_directed": [list(e) for e in session.input_directed],
        "input_undirected": [list(e) for e in session.input_undirected],
        "answers": [
            {
                "edge": list(a.edge),
                "direction": [a.direction[0], a.direction[1]] if a.direction else None,
                "adjacency": a.adjacency,
                "source": a.source,
                "note": a.note,
            }
            for a in session.answers
        ],
        "constraints": [list(e) for e in session.constraints],
        "asserted_adjacencies": [list(e) for e in session.asserted_adjacencies],
        "asserted_absences": [list(e) for e in session.asserted_absences],
        "propagation": orientation_to_dict(session.result),
        "question_set": question_set_to_dict(session.question_set),
        "deferred": [list(e) for e in session.deferred],
        "source_trail": [dict(s) for s in session.source_trail],
        "rejected": [dict(r) for r in session.rejected],
        "status": session.status,
        "note": [dict(one) for one in session.note],
    })
