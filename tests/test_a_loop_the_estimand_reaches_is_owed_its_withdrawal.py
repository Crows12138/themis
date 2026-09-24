"""A loop the estimand reaches is owed its withdrawal.

A declared loop between an effect question's treatment and outcome takes
the DAG's routes away: the kernel answers with an instrument under the
two-equation reduction, or with one of the loop's two refusals, and either
way the answer carries the block saying which routes were withdrawn. The
verifier held that block, the step that cites it, and the two refusals to
the program wherever an answer made the claim. It never asked where one was
owed. Measured on the corpus: every effect answer computed from the DAG --
77 numbers, 13 decompositions, 48 refusals naming what to collect -- put
beside the same program with a loop declared between its two ends passed
every door that reads it; and at the door that reads only what the program
settles, the 12 among them whose verdict another route reaches passed too.

Which answers owe the block is read off the program, the question and the
graph; the answers that owe none although a loop reaches are the ones given
before any route runs, the loop's among them: the strict framing gate's, and
the refusal of a question conditioning on its own treatment or outcome. The
other way round, the block's audit held the loop it names to one the program
declares, not to one that reaches the question: beside a program declaring a
second loop that reaches nothing of it, a refusal whose block named that one
passed every door. And a loop's route outranks every other route to an effect
question, so a verdict any other route reaches is not the question's where
a loop reaches it.

Identification questions ask the same estimand and do not yet read the
loops at all; they are the next change, and are left out of the rows below.
"""
from __future__ import annotations

import copy
import json
import pathlib

import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis.verifier.errors import VerificationError
from themis.verifier.refusal_rules import _species_written

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SHAPES = json.loads(
    (FIXTURES / "answer_shapes.json").read_text(encoding="utf-8"))

LOOP_SPECIES = {"feedback_loop_needs_an_instrument",
                "feedback_loop_outside_the_simultaneous_case"}


def _question(program, result):
    return next(s for s in program["statements"]
                if s.get("kind") == "query"
                and s.get("id") == result.get("query_id"))


def _looped(name):
    """The row's program with a loop declared between its question's ends."""
    pair = SHAPES[name]
    program = copy.deepcopy(pair["program"])
    query = _question(program, pair["result"])["query"]
    program["statements"].insert(len(program["statements"]) - 1, {
        "kind": "feedback", "left": query["intervention"]["atom"],
        "right": query["target"]["atom"]})
    return program


def _before_any_route(name):
    """Answered before any route: stopped by the strict framing gate, or
    refused for conditioning on its own treatment or outcome."""
    pair = SHAPES[name]
    needs = [m.get("need") for m in pair["result"].get("missing_information")
             or ()]
    gated = (bool((pair["program"].get("options") or {}).get("strict_framing"))
             and bool(needs)
             and all(n == "framing_fields_unfilled" for n in needs))
    return gated or needs == ["given_holds_the_treatment_or_outcome"]


ROWS = sorted(
    name for name, pair in SHAPES.items()
    if _question(pair["program"], pair["result"])["query"].get("kind")
    == "effect"
    and not any(s.get("kind") == "feedback"
                for s in pair["program"]["statements"]))

VERDICTS = sorted(
    name for name in ROWS
    if not _before_any_route(name)
    and SHAPES[name]["result"].get("status") == "needs_investigation"
    and {str(s) for _, s, _ in _species_written(SHAPES[name]["result"])}
    - LOOP_SPECIES)


def test_the_rows():
    assert len(ROWS) == 142, len(ROWS)
    assert [name for name in ROWS if _before_any_route(name)] == [
        "needs_investigation:effect:none#614789",
        "needs_investigation:effect:none#af79f6"]
    assert len(VERDICTS) == 11, VERDICTS


@pytest.mark.parametrize("name", ROWS)
def test_an_answer_beside_a_loop_it_withdraws_nothing_for(name):
    program, result = _looped(name), SHAPES[name]["result"]
    if _before_any_route(name):
        themis.verify_answer_claims(program, copy.deepcopy(result))
        return
    with pytest.raises(VerificationError, match="withdraws nothing"):
        themis.verify_answer_claims(program, copy.deepcopy(result))


@pytest.mark.parametrize("name", ROWS)
def test_the_kernels_own_answer_to_the_looped_program_is_accepted(name):
    program = _looped(name)
    qid = SHAPES[name]["result"]["query_id"]
    result = next(r for r in themis.run(program)["results"]
                  if r.get("query_id") == qid)
    assert ("feedback_loop" in (result.get("extensions") or {})) != (
        _before_any_route(name))
    verify_honestly(program, result)
    themis.verify_refusal(program, result)


@pytest.mark.parametrize("name", VERDICTS)
def test_a_verdict_another_route_reaches_is_not_the_loops(name):
    with pytest.raises(VerificationError, match="before any other"):
        themis.verify_refusal(_looped(name), copy.deepcopy(
            SHAPES[name]["result"]))


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program(*loops):
    statements = [
        {"kind": "variable", "predicate": n, "domain": [True, False]}
        for n in ("x", "y", "p", "q")]
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in (("x", "y"), ("p", "q"))]
    statements += [{"kind": "feedback", "left": _atom(a), "right": _atom(b)}
                   for a, b in loops]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements + [{
                "kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}}]}


@pytest.mark.parametrize("beside, named, refusal", [
    ((), ("x", "y"), "the program declares"),
    ((("p", "q"),), ("x", "y"), "the program declares"),
    ((("x", "y"), ("p", "q")), ("p", "q"), "reaches neither"),
    ((("x", "y"), ("p", "q")), ("q", "p"), "reaches neither"),
], ids=["no loop declared", "only a loop that reaches nothing",
        "a declared loop that reaches nothing, beside one that does",
        "the same loop written the other way round"])
def test_a_withdrawal_names_a_loop_that_reaches_the_question(
        beside, named, refusal):
    looped = _program(("x", "y"), ("p", "q"))
    answer = themis.run(looped)["results"][0]
    assert [m["need"] for m in answer["missing_information"]] == [
        "feedback_loop_needs_an_instrument"]
    verify_honestly(looped, answer)
    themis.verify_refusal(looped, answer)
    block = answer["extensions"]["feedback_loop"]
    block["left"], block["right"] = (f"{n}(me)" for n in named)
    with pytest.raises(VerificationError, match=refusal):
        themis.verify_answer_claims(_program(*beside), answer)
