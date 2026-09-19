"""A step of an answer is named by the place it sits.

A step's name exists to be pointed at, and for a long time nothing said
what one had to be. Producers spelled it: a hundred ``DerivationStep``
sites wrote one, thirty-nine ``StepRef`` sites wrote the same string a
second time so a later step could name an earlier one, and the gap report
rebuilt a third copy from an index of its own — ``s_t9_2_{index}`` — to
cite a step it did not hold. Nothing checked any of the three, because
there was nothing to check them against.

So the verifier could ask two things about a name and no more: that two
steps did not share one, and that a reference landed somewhere. A name
nobody pointed at was constrained by neither. Measured on the corpus:
forge the first step's name and 81 of 178 stored answers were accepted at
every public door.

The third copy was not merely fragile, it was wrong. The report's index
ran over every source of a transport block; the chain's ran over the
transporting ones only, so a blocked source ahead of a transporting one
shifted the name the report rebuilt off the step it meant.

What a reader of an answer CAN recompute is where a step sits, so that is
what the name is: :func:`themis.types.step_name`, written by the encoder
and by nobody else. A producer keeps a private ``label``, which is how it
says which step it means while it is still building the chain, and which
stops at the serialization boundary. This file holds both halves — that
nothing spells a name, and that every reader recomputes it.
"""
from __future__ import annotations

import ast
import copy
import dataclasses
import json
import pathlib

import pytest

import themis
from themis.types import DerivationStep, StepRef, step_name
from themis.verifier.errors import StepRefError, VerificationError
from themis.verifier.serialization import (
    DerivationSerializationError,
    derivation_from_dict,
    derivation_to_dict,
)
from themis.verifier.step_name_rules import verify_the_chain_names_its_steps

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHAPES = json.loads(
    (ROOT / "tests" / "fixtures" / "answer_shapes.json").read_text("utf-8"))
UNWITNESSED = json.loads(
    (ROOT / "tests" / "fixtures" / "unwitnessed_leaves.json").read_text("utf-8"))

#: Every stored answer that carries a chain, with how many steps it has.
#: Read off the corpus and not off the declaration this frontier empties:
#: keyed on the file it empties, the roster would be empty and a suite
#: that collects nothing reports green.
CARRYING = [
    (name, len((pair["result"].get("derivation") or {}).get("steps") or ()))
    for name, pair in sorted(SHAPES.items())
    if (pair["result"].get("derivation") or {}).get("steps")
]

#: The three ways the census bends a string: itself with a suffix, empty,
#: and somebody else's.
BENDS = (
    ("suffix", "s1_forged"),
    ("empty", ""),
    ("stranger", "the_admissibility_check"),
)


def test_the_corpus_has_chains_to_ask_about():
    """The roster above is the reason every parametrized test below is
    not vacuously green."""
    assert len(CARRYING) > 100


# ============================================ what a name is


def test_a_name_is_the_place_and_nothing_else():
    assert [step_name(i) for i in range(4)] == ["s1", "s2", "s3", "s4"]


def test_no_site_in_the_tree_spells_a_name():
    """The producer's half. A site that could write a name could write a
    name that disagrees with the one the answer carries, and the first
    thing such a site does is stop being checkable."""
    offenders = []
    for path in sorted((ROOT / "themis").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            called = (fn.attr if isinstance(fn, ast.Attribute)
                      else getattr(fn, "id", ""))
            if called not in ("DerivationStep", "StepRef"):
                continue
            for kw in node.keywords:
                if kw.arg == "step_id":
                    offenders.append(
                        f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert offenders == [], (
        "these sites pass step_id to a step or a reference; what a step is "
        "called is its place, and a producer hands over a label instead")


def test_neither_a_step_nor_a_reference_carries_a_field_called_step_id():
    for kind in (DerivationStep, StepRef):
        names = {f.name for f in dataclasses.fields(kind)}
        assert "step_id" not in names
        assert "label" in names


# ============================================ the boundary that names them


def _chain() -> tuple[DerivationStep, ...]:
    """Two steps whose labels are deliberately nothing like a name."""
    return (
        DerivationStep(rule="graph_is_dag", inputs={}, output=True,
                       label="whatever the producer liked"),
        DerivationStep(rule="backdoor_criterion",
                       inputs={"criterion":
                               StepRef(label="whatever the producer liked")},
                       output=True, label="and this one"),
    )


def test_the_encoder_names_by_place_whatever_the_labels_were():
    payload = derivation_to_dict(_chain())
    assert [s["step_id"] for s in payload["steps"]] == ["s1", "s2"]


def test_the_encoder_points_a_reference_at_the_name_it_wrote():
    payload = derivation_to_dict(_chain())
    assert payload["steps"][1]["inputs"]["criterion"] == {
        "kind": "step_ref", "step_id": "s1"}


def test_the_encoder_refuses_two_steps_under_one_label():
    twice = (
        DerivationStep(rule="graph_is_dag", inputs={}, output=True, label="a"),
        DerivationStep(rule="graph_is_dag", inputs={}, output=True, label="a"),
    )
    with pytest.raises(DerivationSerializationError, match="spend one twice"):
        derivation_to_dict(twice)


def test_the_encoder_refuses_a_reference_to_a_label_no_step_carries():
    dangling = (
        DerivationStep(rule="graph_is_dag", inputs={}, output=True, label="a"),
        DerivationStep(rule="backdoor_criterion",
                       inputs={"criterion": StepRef(label="b")},
                       output=True, label="c"),
    )
    with pytest.raises(DerivationSerializationError,
                       match="which no step of this chain carries"):
        derivation_to_dict(dangling)


def test_a_decoded_chain_works_in_the_names_it_arrived_under():
    """The far side of the boundary has no producer, so the name it was
    given is the handle it gets."""
    back = derivation_from_dict(derivation_to_dict(_chain()))
    assert [s.label for s in back] == ["s1", "s2"]
    assert back[1].inputs["criterion"] == StepRef(label="s1")


# ============================================ the rule at the door


def _envelope(names: list[str]) -> dict:
    return {
        "derivation": {
            "version": "0.1",
            "kind": "derivation",
            "steps": [
                {"rule": "graph_is_dag", "inputs": {}, "output": True,
                 "step_id": name}
                for name in names
            ],
        }
    }


def test_the_rule_accepts_a_chain_named_by_place():
    verify_the_chain_names_its_steps(_envelope(["s1", "s2", "s3"]))


@pytest.mark.parametrize("how,forged", BENDS)
def test_the_rule_refuses_every_bend_of_a_name(how, forged):
    envelope = _envelope(["s1", "s2"])
    envelope["derivation"]["steps"][0]["step_id"] = forged
    with pytest.raises(VerificationError, match="named by the place it sits"):
        verify_the_chain_names_its_steps(envelope)


def test_the_rule_refuses_a_step_that_gives_itself_no_name():
    envelope = _envelope(["s1", "s2"])
    del envelope["derivation"]["steps"][1]["step_id"]
    with pytest.raises(VerificationError, match="calls itself None"):
        verify_the_chain_names_its_steps(envelope)


def test_the_rule_refuses_a_reference_that_lands_on_nothing():
    envelope = _envelope(["s1", "s2"])
    envelope["derivation"]["steps"][1]["inputs"]["criterion"] = {
        "kind": "step_ref", "step_id": "s_admissibility_check"}
    with pytest.raises(StepRefError, match="no step of this chain"):
        verify_the_chain_names_its_steps(envelope)


def test_the_rule_says_nothing_about_an_answer_that_took_no_route():
    """A gap diagnosis is a whole answer and it carries no chain."""
    verify_the_chain_names_its_steps({"status": "needs_investigation"})


# ============================================ every stored answer


@pytest.mark.parametrize("row,count", CARRYING)
def test_every_stored_chain_is_named_by_place(row, count):
    steps = SHAPES[row]["result"]["derivation"]["steps"]
    assert [s.get("step_id") for s in steps] == [
        step_name(index) for index in range(count)]


def _references(node):
    if isinstance(node, dict):
        if node.get("kind") == "step_ref":
            yield node.get("step_id")
            return
        for value in node.values():
            yield from _references(value)
    elif isinstance(node, list):
        for value in node:
            yield from _references(value)


@pytest.mark.parametrize("row,count", CARRYING)
def test_every_stored_reference_lands_on_a_step(row, count):
    steps = SHAPES[row]["result"]["derivation"]["steps"]
    names = {step_name(index) for index in range(count)}
    for target in _references(steps):
        assert target in names


@pytest.mark.parametrize("row,count", CARRYING)
def test_a_forged_name_is_refused_at_the_door_that_asks_for_no_chain(
        row, count):
    pair = SHAPES[row]
    forged = copy.deepcopy(pair["result"])
    forged["derivation"]["steps"][0]["step_id"] = "s1_forged"
    with pytest.raises(VerificationError, match="named by the place it sits"):
        themis.verify_answer_claims(pair["program"], forged)


# ============================================ what a gap points at


def _cited(result) -> list[str]:
    out = []
    for gap in (result.get("data_gap_report") or {}).get("gaps", []) or []:
        for ref in gap.get("provenance", []) or []:
            if ref.get("ref_kind") == "derivation_step":
                out.append(ref.get("ref_id"))
    return out


def test_some_stored_gap_cites_a_step_by_its_place():
    """Otherwise the sibling below is a rule about nothing."""
    by_place = [
        row for row, pair in sorted(SHAPES.items())
        for ref in _cited(pair["result"])
        if ref in {step_name(i) for i in range(
            len((pair["result"].get("derivation") or {}).get("steps") or ()))}
    ]
    assert by_place


@pytest.mark.parametrize("row,count", CARRYING)
def test_a_gap_cites_a_place_this_chain_has_or_a_rule_it_ran(row, count):
    result = SHAPES[row]["result"]
    steps = result["derivation"]["steps"]
    reachable = {step_name(index) for index in range(count)}
    reachable |= {s.get("rule") for s in steps}
    for ref in _cited(result):
        assert ref in reachable


# ============================================ the declaration


def test_the_census_no_longer_names_this_leaf_anywhere():
    leaf = "derivation.steps.[].step_id"
    named = sorted(row for row, leaves in UNWITNESSED.items()
                   if leaf in leaves)
    assert named == []
