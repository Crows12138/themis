"""An orientation question is a question only if both answers are open.

``guaranteed`` says what an answer fixes WHICHEVER WAY it goes, and its
docstring said "always ≥ 1, the edge itself". On a five-node graph it read 0,
and the prompt built from it ended ``还能顺带定下`` with nothing after the
verb — a sentence handed to a person with its object missing.

The proximate cause was two facts sharing one channel: a direction's cascade
comes back empty both when it determines nothing (which cannot happen — the
edge is in its own cascade) and when the direction is not available at all,
and intersecting a real cascade with an unavailable one gives nothing.

Under that sits the thing worth fixing. ``guaranteed ≥ 1`` is not an
implementation detail, it is Meek's completeness theorem: close a PATTERN
under R1-R4 and every edge still undirected is reversible, so neither
direction can be unavailable. The theorem has a precondition — that the input
is the pattern of some DAG — and **nothing checked it**. The graph in
question is the pattern of no DAG at all: enumerate its sixteen orientations
and none keeps the collider set the data reported. The system's response was
to ask two questions that have no answers.

So the precondition is now decided, on the input, before anything that rests
on it runs, and by a procedure that is complete rather than a check for the
symptom that happened to show. Dor & Tarjan's (1992) sink rule builds a
consistent extension or proves there is none; when there is none, the session
is handed the conflict — what to give up — instead of a choice between two
directions that both fail to exist.

What is checked here: that the decision agrees with brute-force enumeration
on both populations in both directions, that the promise holds wherever a
question is still asked, and that a question set built on an impossible graph
is refused by the verifier. A first attempt at this file asserted a residual
of four uncaught graphs and a shape they were supposed to share; both were
wrong, which is the reason the check is a decision procedure and not a
collection of the symptoms that had been noticed.
"""
from __future__ import annotations

import itertools
import json
import pathlib
import random

import pytest

from themis.estimation.orientation import (OrientationError,
                                           orientation_to_dict,
                                           propagate_orientations)
from themis.estimation.orientation_questions import (
    compile_orientation_questions, question_set_to_dict)
from themis.verifier.errors import VerificationError
from themis.verifier.orientation_question_rules import (
    verify_orientation_questions)
from themis.verifier.orientation_rules import verify_orientation_propagation

#: The graph the defect was found on: two collider arms into ``c``, a chain
#: out to ``e``, and two edges back to ``e`` from the collider's own parents.
NODES = ("a", "b", "c", "d", "e")
DIRECTED = (("a", "c"), ("b", "c"))
UNDIRECTED = (("c", "d"), ("d", "e"), ("a", "e"), ("b", "e"))


# --- the oracle -------------------------------------------------------------


def _acyclic(nodes, edges) -> bool:
    children = {n: set() for n in nodes}
    for (u, v) in edges:
        children[u].add(v)
    colour: dict = {}

    def go(n):
        if colour.get(n) == 1:
            return False
        if colour.get(n) == 2:
            return True
        colour[n] = 1
        for m in children[n]:
            if not go(m):
                return False
        colour[n] = 2
        return True

    return all(go(n) for n in nodes)


def _colliders(nodes, edges, skeleton) -> set:
    parents = {n: set() for n in nodes}
    for (u, v) in edges:
        parents[v].add(u)
    return {(p, q, c) for c, ps in parents.items()
            for p, q in itertools.combinations(sorted(ps), 2)
            if frozenset((p, q)) not in skeleton}


def _realisable(nodes, directed, undirected) -> bool:
    """Is there a DAG with this skeleton whose unshielded colliders are
    exactly the ones the input declares?

    Brute force over the undirected edges — the definition itself, so that the
    shipped decision can be compared against it rather than argued about.
    """
    skeleton = {frozenset(e) for e in list(directed) + list(undirected)}
    target = _colliders(nodes, set(directed), skeleton)
    for bits in itertools.product([0, 1], repeat=len(undirected)):
        edges = set(directed)
        for bit, (u, v) in zip(bits, undirected):
            edges.add((u, v) if bit == 0 else (v, u))
        if _acyclic(nodes, edges) and _colliders(nodes, edges, skeleton) == target:
            return True
    return False


def test_the_oracle_agrees_with_itself_on_a_graph_built_from_a_dag():
    """A DAG's own pattern is realisable — by the DAG it came from."""
    assert _realisable(("a", "b", "c", "d"), [("a", "c"), ("b", "c")], [("c", "d")])


def test_the_specimen_is_the_pattern_of_no_dag():
    """Which is the fact everything below rests on, so it is asserted rather
    than described: sixteen orientations, and not one of them keeps the
    collider set the input declares."""
    assert not _realisable(NODES, DIRECTED, UNDIRECTED)


# --- the two populations ----------------------------------------------------


def _from_a_dag(rng, nodes, density):
    """A genuine pattern: some DAG's skeleton plus exactly its unshielded
    colliders — which is what causal discovery hands the session."""
    order = list(nodes)
    rng.shuffle(order)
    rank = {n: i for i, n in enumerate(order)}
    skel = [tuple(sorted(e)) for e in itertools.combinations(nodes, 2)
            if rng.random() < density]
    dag = {(u, v) if rank[u] < rank[v] else (v, u) for (u, v) in skel}
    cols = _colliders(nodes, dag, {frozenset(e) for e in skel})
    directed = sorted({(p, c) for (p, _q, c) in cols} |
                      {(q, c) for (_p, q, c) in cols})
    oriented = {frozenset(e) for e in directed}
    return directed, sorted(e for e in skel if frozenset(e) not in oriented)


def _drawn(rng, nodes, density):
    """What a person can hand to the public entry point: a skeleton with an
    arbitrary subset oriented. Nothing stops this, and a third of them are the
    pattern of no DAG."""
    directed, undirected = [], []
    for e in itertools.combinations(nodes, 2):
        if rng.random() >= density:
            continue
        u, v = sorted(e)
        r = rng.random()
        if r < 0.35:
            directed.append((u, v))
        elif r < 0.7:
            directed.append((v, u))
        else:
            undirected.append((u, v))
    return sorted(directed), sorted(undirected)


def _sample(maker, rounds, seed, cap=8):
    rng = random.Random(seed)
    for _ in range(rounds):
        n = rng.randint(4, 6)
        nodes = tuple("abcdef"[:n])
        directed, undirected = maker(rng, nodes, rng.choice([0.4, 0.5, 0.6]))
        if not undirected or len(undirected) > cap:
            continue
        yield nodes, directed, undirected


# --- the decision -----------------------------------------------------------


def _verdict(nodes, directed, undirected):
    """(raised, said-it-is-impossible, result) for one graph."""
    try:
        result = propagate_orientations(nodes, directed=directed,
                                        undirected=undirected)
    except OrientationError:
        return True, True, None
    said = any(c.get("reason") == "no_consistent_extension"
               for c in result.conflicts)
    return False, said, result


def test_the_decision_is_the_definition_on_graphs_a_person_can_draw():
    """Both directions, against brute-force enumeration: no realisable graph
    is ever told it is impossible, and no impossible one gets through.

    The first attempt at this defect fixed the symptom that had been noticed —
    orient what acyclicity forces, then look for a collider nobody declared —
    and it was sound but not complete: three graphs in this very sample went
    through it silently. Soundness alone would still pass the first assertion
    below. The second is the one that says the check knows what it is
    deciding.
    """
    caught = raised = quiet = 0
    for nodes, directed, undirected in _sample(_drawn, 6000, seed=11):
        real = _realisable(nodes, directed, undirected)
        threw, said, _ = _verdict(nodes, directed, undirected)
        assert not (said and real), (
            "a realisable graph was told it is impossible", nodes, directed,
            undirected)
        assert said or real, (
            "an impossible graph was let through", nodes, directed, undirected)
        raised += threw
        caught += said and not threw
        quiet += real
    assert caught > 100 and raised > 100 and quiet > 1000


def test_a_genuine_pattern_is_never_accused():
    """The other population, where the answer is known in advance: a pattern
    read off a DAG is realisable by that DAG, so the decision must be silent
    every single time."""
    seen = 0
    for nodes, directed, undirected in _sample(_from_a_dag, 3000, seed=13):
        threw, said, result = _verdict(nodes, directed, undirected)
        assert not threw and not said, (nodes, directed, undirected)
        assert not result.conflicts, (nodes, directed, undirected)
        seen += 1
    assert seen > 500


def test_a_cyclic_input_is_ill_formed_rather_than_propagated():
    """The guard the cycle check never had. Every other direction an edge can
    be oriented was checked against a cycle — a constraint, a Meek rule — and
    the one the caller states outright was not."""
    with pytest.raises(OrientationError, match="cycle"):
        propagate_orientations(("a", "b", "c"),
                               directed=[("a", "b"), ("b", "c"), ("c", "a")],
                               undirected=[])


# --- the invariant that rests on it -----------------------------------------


@pytest.mark.parametrize("maker,seed", [(_from_a_dag, 3), (_drawn, 5)])
def test_every_question_asked_guarantees_at_least_its_own_edge(maker, seed):
    """The docstring's claim, over both populations rather than over the one
    the theorem covers.

    A gate that only sampled genuine patterns would be sampling the case where
    the claim IS the theorem, and the claim was false exactly where the
    theorem does not reach.
    """
    asked = 0
    for nodes, directed, undirected in _sample(maker, 600, seed):
        threw, _said, result = _verdict(nodes, directed, undirected)
        if threw:
            continue
        for q in compile_orientation_questions(result).questions:
            if q.kind != "orientation":
                continue
            asked += 1
            assert q.guaranteed >= 1, (nodes, directed, undirected, q)
            assert q.leverage >= q.guaranteed, q
            for side in ("forward", "backward"):
                assert q.detail[side]["determines"], (q.edge, side)
    assert asked, "no orientation question was asked at all"


@pytest.mark.parametrize("maker,seed", [(_from_a_dag, 7), (_drawn, 11)])
def test_no_prompt_offers_a_list_and_then_names_nothing(maker, seed):
    """The reader-facing half of the same invariant.

    The sentence was assembled from ``leverage > guaranteed``, which was true
    while the set it then interpolated was empty. The check is on the rendered
    string because that is what a person reads.
    """
    for nodes, directed, undirected in _sample(maker, 400, seed):
        threw, _said, result = _verdict(nodes, directed, undirected)
        if threw:
            continue
        for q in compile_orientation_questions(result).questions:
            assert "定下 ）" not in q.prompt, (nodes, q.prompt)
            assert not q.prompt.rstrip("）").endswith("定下 "), q.prompt
            assert q.prompt.strip() == q.prompt and q.prompt


def test_an_impossible_graph_is_adjudicated_and_not_asked_about():
    """The registered symptom, end to end.

    ONE conflict, not one per witness. Four of this graph's five nodes cannot
    be the sink, and each has its own reason — but the theorem says no other
    build order would have got further, so those are four views of one fact.
    Four conflicts would read as four problems and would suggest that
    connecting any one of the four pairs is a way out, which nothing says.
    """
    result = propagate_orientations(NODES, directed=DIRECTED,
                                    undirected=UNDIRECTED)
    assert len(result.conflicts) == 1
    (c,) = result.conflicts
    assert c["reason"] == "no_consistent_extension"
    # The least witness: at c, the undirected c–d and the collider arm a→c,
    # with a and d non-adjacent. Orienting d→c makes a collider nobody
    # reported; orienting c→d only moves the problem along.
    assert c["forced_collider"] == ["a", "d"] and c["colliders"] == ["c"]
    assert c["roots"] == [], "no answer is at fault — the input is"

    questions = compile_orientation_questions(result).questions
    assert {q.kind for q in questions} == {"conflict"}
    for q in questions:
        assert "不是任何一张 DAG 的 pattern" in q.prompt
        assert "无屏蔽对撞" in q.prompt
        assert "这不是某一条边的毛病" in q.prompt

    verify_orientation_propagation(orientation_to_dict(result))
    verify_orientation_questions(question_set_to_dict(
        compile_orientation_questions(result)))


def test_the_verifier_refuses_a_question_asked_on_an_impossible_graph():
    """The counterexample the gate exists to say no to.

    Built by hand rather than by breaking the producer, because what is being
    checked is that the verifier decides this for itself. ``guaranteed`` is
    not what gives this one away — it carries an honest 1 — so what has to
    catch it is the graph, not the number.
    """
    artifact = question_set_to_dict(compile_orientation_questions(
        propagate_orientations(NODES, directed=DIRECTED, undirected=UNDIRECTED)))
    verify_orientation_questions(artifact)  # as shipped: accepted

    artifact["questions"] = [{
        "kind": "orientation", "edge": ["a", "e"], "leverage": 1,
        "guaranteed": 1, "unlocks": [], "reason": "", "prompt": "a→e 还是 e→a？",
        "detail": {"forward": {"answer": ["a", "e"], "determines": [["a", "e"]]},
                   "backward": {"answer": ["e", "a"], "determines": [["a", "e"]]}},
    }]
    with pytest.raises(VerificationError, match="conflict questions disagree"):
        verify_orientation_questions(artifact)


def test_the_promise_is_stated_where_the_number_is_declared():
    """The floor is a theorem with a precondition, and both belong beside the
    field — a reader who finds ``minimum: 0`` next to a promise of 1 needs to
    be told which one is the schema being cautious."""
    schema = json.loads(
        (pathlib.Path(__file__).resolve().parent.parent / "themis" / "schemas"
         / "orientation_question_set.schema.json").read_text(encoding="utf-8"))
    said = schema["$defs"]["question"]["properties"]["guaranteed"]["description"]
    assert "never less than 1" in said
    assert "no_consistent_extension" in said
