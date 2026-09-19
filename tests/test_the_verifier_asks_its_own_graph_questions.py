"""The verifier asks its own graph questions.

``rules.py`` opens by saying the verifier re-derives structural facts rather
than calling ``structural_solver``: if the verifier and the elaborator agree
the derivation is accepted, and if they disagree it is rejected. That holds
only for a fact the verifier computed itself. Measured before this file
existed, ten verifier functions asked the producer's own search instead:
whether an adjustment set is admissible and whether one exists (numeric
causation, the counterfactual cell and its general-ID risk, missing-data
recovery), d- and m-separation (selection and missing-data recovery, the
marginal-independence lookup and its refusal, the IDC exchange replay) and
c-components (the Tian identification and hedge rules). One of them said it
was "its own re-derivation, not a runtime call".

So a bug in the producer's search reached the verdict from both sides. With
the producer's adjustment search made to say the empty set is admissible, the
verifier refused the honest causation and counterfactual-cell answers, calling
their correct set ``{z}`` inadmissible, and would have accepted any answer
agreeing with the bug.

The imports were written inside function bodies, and the pin that stated the
rule, in ``test_mediation_verifier.py``, looked for a module-level name, which
such an import never binds. This file replaces it and reads every import
statement in the verifier, at any depth.

Nothing a reader sees moves. On 400 random ADMGs (6614 treatment-outcome
pairs) the producer's minimal sets and the verifier's criterion agreed on every
pair before the change, and the agreement is kept below as a pin of its own,
order included, because missing-data recovery takes the first smallest set.
"""
from __future__ import annotations

import ast
import copy
import inspect
import itertools
import json
import pathlib
import random
import sys

import networkx as nx
import pytest

import themis
import themis.verifier.rules
from tests.answer_corpus import the_door_for
from themis.types import Atom, ConstTerm

ROOT = pathlib.Path(__file__).resolve().parent.parent
VERIFIER = pathlib.Path(themis.verifier.rules.__file__).parent
SHAPES = json.loads((ROOT / "tests" / "fixtures" / "answer_shapes.json")
                    .read_text(encoding="utf-8"))

#: The runtime modules the verifier does import, by file. ``numeric_estimator``
#: supplies the probability-table types both sides read; ``semantic_probe.py``
#: also takes the formula evaluator from it, so the probe computes the true
#: do-quantity with its own elimination but evaluates the claimed formula with
#: the runtime's. ``verify.py`` takes only a type from ``ctf_identify``. In
#: ``rules.py``, ``c_factor`` and ``ctf_identify`` are the general-ID and
#: counterfactual-ID engines, which the rules calling them re-run rather than
#: reimplement. ``statement_rules.py`` takes the members of the premise set
#: from ``iv_words``, a closed list of names with no computation behind it,
#: so the table saying which derivation step settles which premise is keyed
#: on the members themselves. These are dependencies declared here, not
#: closed: a module leaves this map by being reimplemented, and one turning
#: up without being entered here is a dependency nobody declared.
DECLARED_RUNTIME_IMPORTS = {
    "context.py": {"numeric_estimator"},
    "rules.py": {"numeric_estimator", "c_factor", "ctf_identify"},
    "semantic_probe.py": {"numeric_estimator"},
    "serialization.py": {"numeric_estimator"},
    "statement_rules.py": {"iv_words"},
    "verify.py": {"ctf_identify"},
}


def _runtime_imports(source: str) -> set[str]:
    """Every runtime module a source file imports, at any depth."""
    found: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 2 and (module == "runtime" or module.startswith("runtime.")):
                parts = module.split(".")[1:]
            elif node.level == 0 and (module == "themis.runtime"
                                      or module.startswith("themis.runtime.")):
                parts = module.split(".")[2:]
            else:
                continue
            if parts:
                found.add(parts[0])
            else:
                found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("themis.runtime."):
                    found.add(alias.name.split(".")[2])
    return found


def test_the_import_reader_sees_an_import_inside_a_function():
    """The narrowing the old pin had, stated so this one cannot have it."""
    source = (
        "def f():\n"
        "    from ..runtime import structural_solver\n"
        "    from ..runtime.structural_solver import m_separated\n"
    )
    assert _runtime_imports(source) == {"structural_solver"}


def test_no_verifier_module_imports_the_producer_s_graph_search():
    imported = {
        path.name: _runtime_imports(path.read_text(encoding="utf-8"))
        for path in sorted(VERIFIER.glob("*.py"))
    }
    imported = {name: mods for name, mods in imported.items() if mods}
    assert not {name for name, mods in imported.items()
                if "structural_solver" in mods}, imported
    assert imported == DECLARED_RUNTIME_IMPORTS, imported


# ------------------------------------------- the verdicts, with the search gone


class _VerifierAskedTheProducer(BaseException):
    """A BaseException, so an ``except Exception`` around a call cannot hide it."""


@pytest.fixture
def cut_off(monkeypatch):
    """Returns a switch. Once thrown, every ``structural_solver`` function
    raises when a verifier frame calls it. A runtime engine the verifier
    re-runs keeps working, since its own calls come from runtime frames, and
    so does everything a test does before throwing it."""
    from themis.runtime import structural_solver

    here = str(VERIFIER)

    def wrap(name, fn):
        def asked(*args, **kwargs):
            if sys._getframe(1).f_code.co_filename.startswith(here):
                raise _VerifierAskedTheProducer(name)
            return fn(*args, **kwargs)
        return asked

    def throw():
        for name, fn in list(vars(structural_solver).items()):
            if inspect.isfunction(fn) and fn.__module__ == structural_solver.__name__:
                monkeypatch.setattr(structural_solver, name, wrap(name, fn))
    return throw


def test_the_cut_off_fires_on_a_verifier_caller_and_on_no_other(cut_off):
    """Without this, a cut-off that never fired would pass every test below."""
    from themis.runtime import structural_solver

    cut_off()
    namespace: dict = {}
    exec(compile("def ask(solver, graph):\n"
                 "    return solver.c_components(graph, frozenset())\n",
                 str(VERIFIER / "_asks.py"), "exec"), namespace)
    with pytest.raises(_VerifierAskedTheProducer):
        namespace["ask"](structural_solver, nx.DiGraph())
    assert structural_solver.c_components(nx.DiGraph(), frozenset()) == ()


@pytest.mark.parametrize("name", sorted(SHAPES))
def test_every_honest_answer_is_read_without_the_producer_s_search(name, cut_off):
    pair = SHAPES[name]
    cut_off()
    the_door_for(pair["result"])(copy.deepcopy(pair["program"]),
                                 copy.deepcopy(pair["result"]))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def test_a_hedge_is_read_without_the_producer_s_search(cut_off):
    """No corpus answer carries a hedge witness; the bow arc does."""
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "identify", "target": _atom("y"),
                "intervention": {"atom": _atom("x"), "value": True},
                "given": []}},
        ],
    }
    result = themis.run(program)["results"][0]
    assert "tian_hedge_witness" in [s["rule"] for s in result["derivation"]["steps"]]
    cut_off()
    themis.verify(program, result)


def _A(p):
    return Atom(predicate=p, args=(ConstTerm(name="me"),))


def test_a_marginal_the_graph_refuses_is_explained_without_the_producer_s_search(
        cut_off):
    """No corpus answer reaches this explanation; a chain does.

    On x -> m1 -> m2 a table holding P(m2 | x) cannot stand in for
    P(m2 | x, m1), because m1 and m2 are not separated given x.
    """
    from themis.runtime.numeric_estimator import ProbabilityKey, Theta
    from themis.verifier.rules import _verifier_diagnose_marginal_independence_refusal

    x, m1, m2 = _A("x"), _A("m1"), _A("m2")
    theta = Theta(entries={
        ProbabilityKey(m2, True, frozenset([(x, True)])): 0.6,
        ProbabilityKey(m2, False, frozenset([(x, True)])): 0.4,
    })
    missing = ProbabilityKey(m2, True, frozenset([(x, True), (m1, True)]))
    cut_off()
    said = _verifier_diagnose_marginal_independence_refusal(
        missing, theta, graph=nx.DiGraph([(x, m1), (m1, m2)]),
        bidirected=frozenset())
    assert said == {
        "have": "P(m2=True|x=True)",
        "variable": "m2",
        "extras": "m1",
        "conditioning": "x",
    }


def _standardized_over_nothing(result):
    """The same answer, saying it adjusted for nothing at every place it
    names its adjustment set, so no rule comparing two copies can tell."""
    forged = copy.deepcopy(result)

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "adjustment" and isinstance(value, list):
                    node[key] = []
                    continue
                if key == "adjustment" and isinstance(value, dict) and "items" in value:
                    value["items"] = []
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(forged)
    assert forged != result
    return forged


@pytest.mark.parametrize("name", ["causation_plugin", "counterfactual_cell_plugin"])
def test_a_producer_search_that_lies_moves_no_verdict(name, monkeypatch):
    """Both answers stand on z -> x, z -> y, x -> y and standardize over {z}.
    Here the producer's search says the empty set is admissible. Measured
    before this change, on both: the honest answer was refused, and the
    answer saying it adjusted for nothing was accepted."""
    from themis.runtime import structural_solver
    from themis.verifier.errors import RuleCheckFailed

    pair = SHAPES[name]
    program, honest = pair["program"], pair["result"]
    forged = _standardized_over_nothing(honest)
    monkeypatch.setattr(structural_solver, "minimal_adjustment_sets",
                        lambda *args, **kwargs: (frozenset(),))
    themis.verify(copy.deepcopy(program), copy.deepcopy(honest))
    with pytest.raises(RuleCheckFailed,
                       match=r"claimed adjustment set \[\] is not an admissible"):
        themis.verify(copy.deepcopy(program), forged)


# ------------------------------------------------ the two searches agree


def _random_admg(rng, n):
    names = [f"v{i}" for i in range(n)]
    order = names[:]
    rng.shuffle(order)
    graph = nx.DiGraph()
    inserted = names[:]
    rng.shuffle(inserted)
    graph.add_nodes_from(_A(v) for v in inserted)
    p = rng.choice([0.3, 0.45, 0.6])
    for i, u in enumerate(order):
        for w in order[i + 1:]:
            if rng.random() < p:
                graph.add_edge(_A(u), _A(w))
    pairs = list(itertools.combinations(names, 2))
    rng.shuffle(pairs)
    bidirected = frozenset(frozenset({_A(u), _A(w)})
                           for u, w in pairs[:rng.randint(0, 3)])
    return graph, bidirected


def test_the_verifier_s_adjustment_search_finds_what_the_producer_s_does():
    """The same sets in the same order. Agreement is what lets an honest
    answer through, and missing-data recovery reads the order."""
    from themis.runtime.structural_solver import minimal_adjustment_sets
    from themis.verifier.rules import _verifier_minimal_adjustment_sets

    rng = random.Random(657)
    compared = with_given = 0
    for _ in range(120):
        graph, bidirected = _random_admg(rng, rng.randint(3, 6))
        nodes = list(graph.nodes)
        for x, y in itertools.permutations(nodes, 2):
            others = [n for n in nodes if n != x]
            given = tuple(rng.sample(others, rng.randint(0, 1)))
            producer = minimal_adjustment_sets(
                graph, x, y, given=given, bidirected=bidirected or None)
            verifier = _verifier_minimal_adjustment_sets(
                graph, x, y, given=given, bidirected=bidirected)
            assert verifier == producer, (x, y, given, sorted(graph.edges), bidirected)
            compared += 1
            with_given += bool(given and producer)
    assert compared > 1500 and with_given > 100, (compared, with_given)
