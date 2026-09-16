"""A selection-recovery block is held in what it tells a reader.

``verify_selection_recovery`` re-derived the evidence a verdict needs: that
the witness satisfies the criterion -- on an effect, with the formula and the
ledger it licenses -- and on a negative that a search to the recorded range
comes back empty. The rest of what the block tells a reader is fixed by that
verdict too, and none of it was restated. The report and the web page show
the formula and the ledger whatever the verdict, a recoverable verdict's
adjustment set, and on a negative why and whether that is a proof. On the
corpus a negative could carry a formula or call its criterion complete, and a
positive could name an adjustment set its halves do not make, and the door
took each; a conditional verdict's formula and ledger were never read.

Which theorem was re-derived was the block's own word as well. An effect
verdict relabelled ``conditional`` was checked as a claim about P(y | x),
while both reader faces went on calling it the unbiased effect. The kind is
the question's: one that intervenes on the treatment asks for P(y | do(x)),
one that conditions on it asks for P(y | x).
"""
from __future__ import annotations

import copy
import json
import pathlib
from types import SimpleNamespace

import networkx as nx
import pytest

from tests.answer_corpus import the_door_for
from themis.runtime.scheduler import _serialize_selection_recovery
from themis.runtime.selection_recovery import recover_conditional, recover_effect
from themis.types import Atom, ObservationStatement
from themis.verifier import verify_selection_recovery
from themis.verifier.errors import VerificationError

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

CARRIERS = sorted(
    n for n in SHAPES
    if (SHAPES[n]["result"].get("extensions") or {}).get("selection_recovery"))


def A(name):
    return Atom(predicate=name, args=())


RESTRICTED_ON_S = (ObservationStatement(atom=A("s"), value=True),)

#: The question each kind of verdict answers.
INTERVENES = SimpleNamespace(intervention=SimpleNamespace(atom=A("x")),
                             target=SimpleNamespace(atom=A("y")), given=())
CONDITIONS = SimpleNamespace(target=SimpleNamespace(atom=A("y")),
                             given=(SimpleNamespace(atom=A("x")),))

#: One graph for each shape a verdict takes, with what comes back on it:
#: the criterion and the two halves of the adjustment set.
VERDICTS = {
    # z confounds the treatment and the outcome and reaches the selection
    # node, so it is adjusted for as a non-descendant of the treatment.
    "effect, a non-descendant adjusted for": (
        [("z", "x"), ("z", "y"), ("x", "y"), ("x", "s"), ("z", "s")],
        "selection_backdoor", ["z"], []),
    # The outcome reaches the selection node only through m, which the
    # treatment reaches, so m is adjusted for as a descendant.
    "effect, a descendant adjusted for": (
        [("x", "y"), ("y", "m"), ("m", "s"), ("x", "s")],
        "selection_backdoor", [], ["m"]),
    # The outcome is selected on directly: nothing separates the two.
    "effect, nothing found": (
        [("x", "y"), ("x", "s"), ("y", "s")], None, [], []),
    "conditional, independent given the treatment": (
        [("x", "y"), ("x", "s")], "conditional_independence", [], []),
    # Two common causes of the outcome and the selection node; only both
    # together separate them.
    "conditional, external data": (
        [("x", "y"), ("a", "y"), ("a", "s"), ("b", "y"), ("b", "s")],
        "external_data", ["a", "b"], []),
    "conditional, nothing found": (
        [("x", "y"), ("x", "s"), ("y", "s")], None, [], []),
}

SHORTFALL = {
    "effect": {"token": "no_admissible_selection_backdoor_set",
               "vocabulary": "selection_recovery_shortfall"},
    "conditional": {"token": "outcome_not_separable_from_selection",
                    "vocabulary": "selection_recovery_shortfall",
                    "said": {"treatment": "x", "outcome": "y"}},
}
LEDGER = [{"vocabulary": "unbiased_distribution", "token": "unbiased",
           "said": {"expression": "P(x, z)"}}]

#: For each shape, each field a reader is told beside the verdict, told
#: otherwise. Every value is one some block of a verdict's kind says, so
#: what is refused is the pairing with this verdict and not a spelling.
LIES = {
    "effect, a non-descendant adjusted for": {
        "complete_criterion": True,
        "failure_reason": SHORTFALL["effect"],
        "adjustment_set": [],
    },
    "effect, a descendant adjusted for": {
        "complete_criterion": True,
        "failure_reason": SHORTFALL["effect"],
        "adjustment_set": [],
    },
    "effect, nothing found": {
        "complete_criterion": True,
        "criterion": "selection_backdoor",
        "recovery_formula": "P(y | do(x)) = P(y | x, S)",
        "external_data_needed": LEDGER,
        "failure_reason": None,
        "z_plus": ["z"],
    },
    "conditional, independent given the treatment": {
        "complete_criterion": False,
        "recovery_formula": "P(y | x) = Σ_{z} P(y | x, z, S) · P(z | x)",
        "external_data_needed": LEDGER,
        "adjustment_set": ["z"],
        "failure_reason": SHORTFALL["conditional"],
    },
    "conditional, external data": {
        "complete_criterion": False,
        "z_plus": [],
        "z_minus": ["a"],
        "recovery_formula": "P(y | x) = P(y | x, S)",
        "external_data_needed": [],
        "failure_reason": SHORTFALL["conditional"],
    },
    "conditional, nothing found": {
        "complete_criterion": False,
        "criterion": "conditional_independence",
        "recovery_formula": "P(y | x) = P(y | x, S)",
        "external_data_needed": LEDGER,
        "failure_reason": SHORTFALL["effect"],
        "adjustment_set": ["z"],
    },
}


def _honest(shape):
    edges = VERDICTS[shape][0]
    graph = nx.DiGraph([(A(u), A(v)) for u, v in edges])
    produce, question = ((recover_effect, INTERVENES)
                         if shape.startswith("effect")
                         else (recover_conditional, CONDITIONS))
    rec = produce(graph, A("x"), A("y"), (A("s"),))
    return _serialize_selection_recovery(rec, A("x"), A("y")), graph, question


def _refusal(block, graph, question):
    try:
        verify_selection_recovery(block, graph, RESTRICTED_ON_S, question)
    except VerificationError as exc:
        return str(exc)
    return None


@pytest.mark.parametrize("shape", sorted(VERDICTS))
def test_an_honest_block_is_accepted_by_the_question_it_answers(shape):
    block, graph, question = _honest(shape)
    _, criterion, z_plus, z_minus = VERDICTS[shape]
    assert (block["criterion"], block["z_plus"], block["z_minus"]) == (
        criterion, z_plus, z_minus)
    assert _refusal(block, graph, question) is None


@pytest.mark.parametrize("shape", sorted(VERDICTS))
def test_a_verdict_is_about_the_quantity_its_question_asks_for(shape):
    """Put to the other question, or relabelled, the same honest block is
    refused for what it is about and not for anything it computed."""
    block, graph, question = _honest(shape)
    other = CONDITIONS if question is INTERVENES else INTERVENES
    assert "query_kind" in (_refusal(block, graph, other) or "")
    relabelled = dict(block, query_kind=(
        "conditional" if block["query_kind"] == "effect" else "effect"))
    assert "query_kind" in (_refusal(relabelled, graph, question) or "")


@pytest.mark.parametrize("shape,field", sorted(
    (shape, field) for shape, lies in LIES.items() for field in lies))
def test_what_a_reader_is_told_beside_the_verdict_is_what_it_fixes(shape, field):
    block, graph, question = _honest(shape)
    assert block[field] != LIES[shape][field]
    block[field] = copy.deepcopy(LIES[shape][field])
    refusal = _refusal(block, graph, question)
    assert refusal is not None and f"{field}:" in refusal, refusal


def test_every_stored_block_is_accepted_and_both_verdicts_are_stored():
    verdicts = set()
    for name in CARRIERS:
        program = SHAPES[name]["program"]
        result = copy.deepcopy(SHAPES[name]["result"])
        verdicts.add(result["extensions"]["selection_recovery"]["recoverable"])
        the_door_for(result)(program, result)
    assert verdicts == {True, False}


#: Each passed the strongest door on the answer named before the fields
#: were held.
CORPUS_LIES = [
    ("needs_investigation:effect:none#44412c", "query_kind", "conditional"),
    ("needs_investigation:effect:none#44412c", "complete_criterion", True),
    ("needs_investigation:effect:none#44412c", "criterion",
     "selection_backdoor"),
    ("needs_investigation:effect:none#44412c", "recovery_formula",
     "P(y | do(x)) = P(y | x, S)"),
    ("needs_investigation:effect:none#4c2552", "adjustment_set", []),
    ("needs_investigation:effect:none#4c2552", "complete_criterion", True),
    ("numerically_solved:effect:none", "adjustment_set", []),
    ("numerically_solved:effect:none", "complete_criterion", True),
]


@pytest.mark.parametrize("name,field,lie", CORPUS_LIES)
def test_a_stored_answer_telling_a_reader_otherwise_is_refused(name, field, lie):
    program = SHAPES[name]["program"]
    result = copy.deepcopy(SHAPES[name]["result"])
    block = result["extensions"]["selection_recovery"]
    assert block[field] != lie
    block[field] = lie
    with pytest.raises(VerificationError, match=field):
        the_door_for(result)(program, result)
