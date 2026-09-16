"""The block that says why an instrument stands where a back door was.

A declared reciprocal loop withdraws the routes a DAG would have taken, and
what replaces them is an instrumental-variable answer resting on linearity.
That swap is worth forging, which is why the derivation step behind it
re-derives the loop from the PROGRAM rather than from the step's own
inputs. ``extensions.feedback_loop`` is a third statement of the same fact
— the one the report and the gap list read — and it was re-derived by
nobody: the loop could be moved to a pair the program never declared, the
query's two ends could be renamed to bystanders, and the Haavelmo reduction
could be deleted from beside an answer that used one.

The route has two doors and its suite went through one. Every test of it
takes the data fixture and calls ``themis.estimate``; the same program
through ``themis.run`` produced a ``structurally_solved`` answer that
``themis.verify`` REFUSED — "structural effect derivation must end in
identify_via_mediation, …" — because this is the only route that ends an
effect query in ``identify_via_iv`` and the terminal list had never met it.
An honest answer was rejected at the public door for as long as nobody
asked the question at the door it uses.

That terminal is now admitted by its premise instead of its name: an effect
query may end in an instrument only in the company of the withdrawal that
made an instrument the right answer. Without it, ending there IS the
forgery — a correct adjustment answer swapped for one resting on linearity.

WHAT IS NOT RE-DERIVED. ``withdrew`` names route ids, and recomputing which
routes a loop takes away means reading the producer's route table. The
verifier does not import it, and a check that did would agree by
construction.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime.iv_words import Premise
from themis.types import Atom, ConstTerm, QueryStatement
from themis.verifier.errors import VerificationError
from themis.verifier.verify import verify_feedback_loop

BETA, GAMMA, DELTA = 1.5, 0.4, 0.8


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _typed(p) -> Atom:
    return Atom(predicate=p, args=(ConstTerm(name="u"),))


def _program(*statements, treatment="x", outcome="y"):
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": list(statements) + [{
                "kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom(treatment), "value": True},
                    "target": {"atom": _atom(outcome), "value": True},
                    "given": []}}]}


def _simultaneous(*, loop=True, instrument=True):
    """z -> x -> y, with x and y declared to move each other."""
    statements = [
        {"kind": "variable", "predicate": "x", "scale": "continuous"},
        {"kind": "variable", "predicate": "y", "scale": "continuous"},
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
    ]
    if instrument:
        statements[:0] = [
            {"kind": "variable", "predicate": "z", "domain": [True, False]}]
        statements.append(
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")})
    if loop:
        statements.append(
            {"kind": "feedback", "left": _atom("x"), "right": _atom("y")})
    return _program(*statements)


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    """Draws from the two-equation system, through its reduced form."""
    rng = np.random.default_rng(0)
    n = 6000
    u, v = rng.standard_normal(n), rng.standard_normal(n)
    z = (rng.random(n) < 0.5).astype(float)
    denom = 1.0 - BETA * GAMMA
    return pd.DataFrame({
        "z": z > 0.5,
        "x": (DELTA * z + v + GAMMA * u) / denom,
        "y": (BETA * DELTA * z + BETA * v + u) / denom,
    })


PROGRAM = _simultaneous(loop=True)


def _structural():
    return themis.run(PROGRAM)["results"][0]


def _numeric(frame):
    return themis.estimate(PROGRAM, frame, ci_bootstrap=0)["results"][0]


def _refuses(result, fragment, program=PROGRAM):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


# --------------------------------------------------------- the closed door


def test_the_structural_door_accepts_an_honest_loop_answer():
    """The regression this file was opened for. Same program, no data:
    the kernel answers and its own verifier used to say no."""
    result = _structural()
    assert result["status"] == "structurally_solved", result["status"]
    assert (result["extensions"] or {}).get("feedback_loop"), result
    themis.verify(PROGRAM, result)


def test_the_two_doors_carry_the_same_block(frame):
    """One route, two terminals — ``identify_via_iv`` with no data and
    ``numeric_iv_estimate`` with it — and one explanation either way."""
    assert (_structural()["extensions"]["feedback_loop"]
            == _numeric(frame)["extensions"]["feedback_loop"])


def test_an_instrument_with_no_withdrawal_behind_it_is_refused():
    """The terminal is admitted by its premise. Strip the licence and the
    same derivation is an ordinary IV escalation on a graph where a
    back-door answer was there to be had.

    Stripping the step alone leaves the answer saying it rests on a linear
    simultaneous system, which only that step settles, so the door refuses
    that sentence first. The escalation is pinned on the forgery that also
    rewrites the premise to what the stripped chain settles: that one says
    nothing the premise rule can refuse."""
    result = _structural()
    steps = result["derivation"]["steps"]
    result["derivation"]["steps"] = [
        s for s in steps if s["rule"] != "feedback_loop_withdraws_adjustment"]
    assert len(result["derivation"]["steps"]) == len(steps) - 1
    _refuses(result, "the derivation it ran settles")

    premise = result["extensions"]["iv_identification"]["required_assumption"]
    premise["token"] = str(Premise.MONOTONICITY_OR_LINEARITY)
    _refuses(result, "an instrument is the escalation, not the first answer")


# ------------------------------------------------- the block, on both doors


@pytest.fixture(params=["structural", "numeric"])
def answer(request, frame):
    return (_structural() if request.param == "structural"
            else _numeric(frame))


def test_a_loop_the_program_never_declared_is_refused(answer):
    """The forgery the step rule already refuses, made in the block
    instead. Both are read; only one was audited."""
    answer["extensions"]["feedback_loop"].update(
        {"left": "z(u)", "right": "y(u)"})
    _refuses(answer, "the program declares")


@pytest.mark.parametrize("field", ["treatment", "outcome"])
def test_a_block_naming_somebody_elses_query_is_refused(answer, field):
    """Whether a loop reaches an estimand is a fact about the pair. A
    block recording a different pair is claiming a fact it never
    established."""
    answer["extensions"]["feedback_loop"][field] = "z(u)"
    _refuses(answer, f"records {field}=")


def test_deleting_the_reduction_beside_an_instrument_is_refused(answer):
    """Under a loop an instrument identifies a coefficient of the
    two-equation system or nothing at all, so the reader who is shown the
    number and not the reduction is shown a different quantity than the
    one named."""
    del answer["extensions"]["feedback_loop"]["reduction"]
    _refuses(answer, "names no reduction beside an answer that reached an")


def test_the_reduction_must_run_between_the_querys_own_two_ends(answer):
    """Haavelmo's reduction is what being between them buys. A block
    claiming it for a loop elsewhere is claiming the wrong theorem."""
    program = copy.deepcopy(PROGRAM)
    program["statements"].insert(-1, {
        "kind": "variable", "predicate": "p", "scale": "continuous"})
    program["statements"].insert(-1, {
        "kind": "feedback", "left": _atom("p"), "right": _atom("y")})
    answer["extensions"]["feedback_loop"].update(
        {"left": "p(u)", "right": "y(u)"})
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, answer)
    assert "rather than between the treatment and the outcome" in str(
        caught.value), str(caught.value)


# ------------------------------------------------------- the other outcomes


def test_a_loop_that_reached_no_instrument_carries_no_reduction():
    """Two of this route's three outcomes are refusals that carry the
    block and no instrument, and absence of the reduction is correct
    there. A rule that required it would refuse them.

    Held against the rule directly, and the reason is worth recording:
    ``themis.verify`` declines a result with no derivation before it reads
    any block, so these two outcomes reach a reader through the report and
    the gap list and reach this door not at all. That is a fact about
    where the public audit begins, not about this block.
    """
    program = _simultaneous(loop=True, instrument=False)
    result = themis.run(program)["results"][0]
    block = (result["extensions"] or {})["feedback_loop"]
    assert "reduction" not in block, block
    assert "iv_identification" not in result["extensions"], result
    assert result.get("derivation") is None, result.get("derivation")
    with pytest.raises(ValueError, match="requires a result with a "):
        themis.verify(program, result)

    parsed = validate_program(validate_ast(copy.deepcopy(program)))
    query = next(s for s in parsed.statements
                 if isinstance(s, QueryStatement)).query
    verify_feedback_loop(
        block, None,
        frozenset({frozenset({_typed("x"), _typed("y")})}), query)
