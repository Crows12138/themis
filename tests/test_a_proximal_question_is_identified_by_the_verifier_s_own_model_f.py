"""A proximal question is identified by the verifier's own model (f).

``_rule_proximal_criterion`` licenses every proximal answer, structural and
numeric. It did so by calling the producer's ``identify_proximal``, and by
calling it without the covariates the question conditions on, which both
producers pass. Measured before this file existed, on the structural bridge
answer (u -> x, u -> y, x -> y, u -> z, u -> w) with an observed c added:

- c -> z and c -> y, the question conditioned on c: only c blocks z's path to
  y. The producer identified the effect and the strongest door refused it.
- z -> c <- w, the question conditioned on c: conditioning on the collider
  opens z - c - w between the two proxies and the producer refused. The
  answer to the same question without c, with every place it names its
  covariates rewritten to c, was accepted.

And a re-run of the producer's code agrees with the producer by construction.
With ``identify_proximal`` made blind to added bidirected edges, all fourteen
proximal answers in the corpus passed the doors on their programs with a
bidirected edge beside every directed one, which breaks model (f) on each.

So the criterion is transcribed in the verifier with its own m-separation,
read within the covariates, and a pin below holds it to the producer's
decision on random graphs: agreement is what lets an honest answer through.
"""
from __future__ import annotations

import copy
import itertools
import json
import pathlib
import random

import networkx as nx
import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.types import Atom, DiscreteChannel, ProximalEffectQuery, QueryStatement
from themis.verifier.errors import RuleCheckFailed
from tests.answer_corpus import the_door_for

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "answer_shapes.json")
                    .read_text(encoding="utf-8"))
#: Named by kind rather than by shape digest: the one structural bridge answer.
BASE = "structurally_solved:proximal_effect:proximal_criterion"


def _query_of(program):
    return next(s for s in program["statements"] if s.get("kind") == "query")["query"]


def _with_an_observed_c(edges, *, conditioned):
    """The base program with a variable c, the given edges, and c among the
    question's covariates when ``conditioned``."""
    program = copy.deepcopy(SHAPES[BASE]["program"])
    q = _query_of(program)
    z = q["treatment_proxy"][0]
    c = dict(copy.deepcopy(z), predicate="c")
    atoms = {"c": c, "z": z, "w": q["outcome_proxy"][0], "y": q["outcome"]}
    declared = next(s for s in program["statements"]
                    if s.get("kind") == "variable" and s.get("predicate") == "z")
    program["statements"].insert(program["statements"].index(declared) + 1,
                                 dict(copy.deepcopy(declared), predicate="c"))
    program["statements"] += [
        {"kind": "cause", "from": copy.deepcopy(atoms[a]), "to": copy.deepcopy(atoms[b])}
        for a, b in edges]
    if conditioned:
        q["covariates"] = [copy.deepcopy(c)]
    return program


def _answer(program):
    return themis.run(copy.deepcopy(program))["results"][0]


def test_a_question_only_its_covariates_identify_is_accepted():
    program = _with_an_observed_c((("c", "z"), ("c", "y")), conditioned=True)
    honest = _answer(program)
    assert honest["status"] == "structurally_solved"
    themis.verify(copy.deepcopy(program), honest)


def _naming_c(answer):
    """The answer, saying at every place it names covariates that it held c."""
    forged = copy.deepcopy(answer)
    for step in forged["derivation"]["steps"]:
        estimand = step["inputs"].get("estimand")
        if isinstance(estimand, dict):
            estimand["items"]["covariates"]["items"] = [
                {"kind": "atom", "predicate": "c", "args": []}]
    for key, block in forged["extensions"].items():
        if isinstance(block, dict) and "covariates" in block:
            block["covariates"] = ["c()"]
    assert forged != answer
    return forged


def test_an_answer_the_covariates_undo_is_refused():
    program = _with_an_observed_c((("z", "c"), ("w", "c")), conditioned=True)
    assert _answer(program)["status"] == "needs_investigation"
    without = _with_an_observed_c((("z", "c"), ("w", "c")), conditioned=False)
    forged = _naming_c(_answer(without))
    with pytest.raises(RuleCheckFailed,
                       match=r"outcome proxy w.* is not separated from the treatment proxy z"):
        themis.verify(copy.deepcopy(program), forged)


def _proximal_rows():
    return sorted(
        name for name, pair in SHAPES.items()
        if "proximal_criterion" in {s["rule"] for s in
                                    (pair["result"].get("derivation") or {}).get("steps") or ()})


def _key(atom):
    return atom["predicate"], json.dumps(atom.get("args") or [], sort_keys=True)


def _confounded_everywhere(program):
    """A bidirected edge beside every directed edge that has none."""
    forged = copy.deepcopy(program)
    seen = {frozenset((_key(s["left"]), _key(s["right"])))
            for s in program["statements"] if s.get("kind") == "bidirected"}
    for s in program["statements"]:
        pair = frozenset((_key(s.get("from") or {}), _key(s.get("to") or {}))) \
            if s.get("kind") == "cause" else None
        if pair is None or pair in seen:
            continue
        seen.add(pair)
        forged["statements"].append({"kind": "bidirected",
                                     "left": copy.deepcopy(s["from"]),
                                     "right": copy.deepcopy(s["to"])})
    return forged


def test_every_proximal_answer_in_the_corpus_is_asked():
    assert len(_proximal_rows()) == 14, _proximal_rows()


@pytest.mark.parametrize("name", _proximal_rows())
def test_a_producer_criterion_blind_to_confounding_moves_no_verdict(name, monkeypatch):
    from themis.runtime import proximal_identify

    real = proximal_identify.identify_proximal
    monkeypatch.setattr(proximal_identify, "identify_proximal",
                        lambda graph, bidirected, **kw: real(graph, frozenset(), **kw))
    pair = SHAPES[name]
    program, result = pair["program"], pair["result"]
    the_door_for(result)(copy.deepcopy(program), copy.deepcopy(result))
    with pytest.raises(RuleCheckFailed, match="proximal_criterion"):
        the_door_for(result)(_confounded_everywhere(program), copy.deepcopy(result))


# ------------------------------------------------ the two criteria agree


def _A(p):
    return Atom(predicate=p, args=())


def _bridge_channel():
    program = validate_program(validate_ast(copy.deepcopy(SHAPES[BASE]["program"])))
    return next(s.query for s in program.statements
                if isinstance(s, QueryStatement)).channel


def test_the_verifier_s_model_f_decides_what_the_producer_s_does():
    from themis.runtime.proximal_identify import ProximalEstimand, identify_proximal
    from themis.verifier.rules import _verifier_proximal_criterion_fails

    rng = random.Random(658)
    bridge = _bridge_channel()
    decided = {True: 0, False: 0}
    for _ in range(600):
        zs = ("z1", "z2")[:rng.randint(1, 2)]
        ws = ("w1", "w2")[:rng.randint(1, 2)]
        cs = ("c",)[:rng.randint(0, 1)]
        names = ["x", "y", "u", *zs, *ws, "c", "v"]
        graph = nx.DiGraph()
        order = names[:]
        rng.shuffle(order)
        graph.add_nodes_from(_A(n) for n in order)
        spine = [("u", "x"), ("u", "y"), ("x", "y"), *(("u", z) for z in zs),
                 *(("u", w) for w in ws)]
        for a, b in spine:
            graph.add_edge(_A(a), _A(b))
        for a, b in itertools.permutations(names, 2):
            if rng.random() < 0.06 and not graph.has_edge(_A(b), _A(a)):
                graph.add_edge(_A(a), _A(b))
                if not nx.is_directed_acyclic_graph(graph):
                    graph.remove_edge(_A(a), _A(b))
        pairs = list(itertools.combinations(names, 2))
        bidirected = frozenset(frozenset({_A(a), _A(b)})
                               for a, b in rng.sample(pairs, rng.randint(0, 2)))
        channel = rng.choice([bridge, DiscreteChannel(latent_cardinality=1),
                              DiscreteChannel(latent_cardinality=2)])
        roles = dict(treatment=_A("x"), outcome=_A("y"), latent=_A("u"),
                     treatment_proxy=tuple(_A(z) for z in zs),
                     outcome_proxy=tuple(_A(w) for w in ws),
                     covariates=tuple(_A(c) for c in cs))
        producer = isinstance(
            identify_proximal(graph, bidirected, channel=channel, **roles),
            ProximalEstimand)
        verifier = _verifier_proximal_criterion_fails(
            graph, bidirected, ProximalEffectQuery(channel=channel, **roles)) is None
        assert producer == verifier, (sorted(graph.edges), bidirected, roles, channel)
        decided[producer] += 1
    assert decided[True] > 50 and decided[False] > 50, decided
