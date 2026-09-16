"""Two equations are one loop, not one loop among several.

A declared loop between the treatment and the outcome has a remedy: an
instrument for X identifies the coefficient of X in the Y equation, by
Haavelmo's reduction of the two-equation system. The route asked whether
SOME loop the estimand reaches runs between the two, and everything it wrote
named the reached loop that sorts first. With a second loop declared beside
the first the two readings came apart: the answer named the other loop,
claimed the reduction, and its own verifier refused it.

Naming the right loop would have made the verifier accept a wrong number. A
second loop through Y puts a third equation under the ratio, and the first
test below computes where the ratio goes. So the shape is read as what it
was documented to be -- the only loop the estimand reaches -- and the
verifier holds a reduction to that, since an answer claiming one beside a
second reaching loop passed every door.

What this gives up is pinned too. A second loop on X's side alone leaves
the ratio at the coefficient, and such a program is refused rather than
answered: telling the shapes apart is per-shape algebra, the same the reach
rule declines, and the refusal names the routes for a loop that turns out
not to matter.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from tests.answer_corpus import verify_honestly
from themis.verifier.errors import VerificationError

BETA, GAMMA, DELTA = 1.5, 0.2, 2.0
LAMBDA, KAPPA = 0.5, 0.6
OUTSIDE = "feedback_loop_outside_the_simultaneous_case"


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program(*loops, instrument=True, edges=()):
    """z -> x -> y, and the loops given, each a pair of predicates."""
    names = sorted({"x", "y"} | {p for pair in (*loops, *edges) for p in pair}
                   - {"z"})
    statements = [{"kind": "variable", "predicate": n, "scale": "continuous"}
                  for n in names]
    statements.append({"kind": "cause", "from": _atom("x"), "to": _atom("y")})
    statements += [{"kind": "cause", "from": _atom(a), "to": _atom(b)}
                   for a, b in edges]
    if instrument:
        statements.insert(0, {"kind": "variable", "predicate": "z",
                              "domain": [True, False]})
        statements.append(
            {"kind": "cause", "from": _atom("z"), "to": _atom("x")})
    statements += [{"kind": "feedback", "left": _atom(a), "right": _atom(b)}
                   for a, b in loops]
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements + [{
                "kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True},
                    "given": []}}]}


def _draws(second: str, n: int = 40_000) -> pd.DataFrame:
    """The system solved draw by draw: x, y and the second loop's variable.

    ``outcome``: x = γy + δz + v, y = βx + λc + u, c = κy + w.
    ``treatment``: x = γy + δz + λb + v, y = βx + u, b = κx + w.
    """
    rng = np.random.default_rng(0)
    z = (rng.random(n) < 0.5).astype(float)
    v, u, w = rng.standard_normal((3, n))
    if second == "outcome":  # order x, y, c
        a = np.array([[0, GAMMA, 0], [BETA, 0, LAMBDA], [0, KAPPA, 0]])
    else:  # order x, y, b
        a = np.array([[0, GAMMA, LAMBDA], [BETA, 0, 0], [KAPPA, 0, 0]])
    shocks = np.stack([DELTA * z + v, u, w])
    x, y, other = np.linalg.solve(np.eye(3) - a, shocks)
    return pd.DataFrame({"z": z > 0.5, "x": x, "y": y,
                         "c" if second == "outcome" else "b": other})


def _wald(frame: pd.DataFrame) -> float:
    z = frame["z"].to_numpy()
    return ((frame["y"][z].mean() - frame["y"][~z].mean())
            / (frame["x"][z].mean() - frame["x"][~z].mean()))


def _needs(result) -> list:
    return [m.get("need") for m in result.get("missing_information") or ()]


# --------------------------------------------------------------- the oracle


def test_a_second_loop_through_the_outcome_moves_the_ratio_off_the_coefficient():
    """y = βx + λc + u beside c = κy + w is y = βx/(1-λκ) + ...: the ratio
    identifies that, and the answer would have called it β."""
    wald = _wald(_draws("outcome"))
    assert wald == pytest.approx(BETA / (1 - LAMBDA * KAPPA), rel=0.03)
    assert abs(wald - BETA) > 0.4


def test_a_second_loop_on_the_treatments_side_alone_leaves_it_and_is_refused():
    """The cost of reading the shape as one loop, stated as a fact: the
    ratio is still β here, and the program is refused all the same."""
    frame = _draws("treatment")
    assert _wald(frame) == pytest.approx(BETA, rel=0.03)
    program = _program(("x", "y"), ("b", "x"))
    result = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    assert result.get("numeric_estimate") is None
    assert OUTSIDE in _needs(result)


# --------------------------------------------------------------- the kernel


SECOND_LOOPS = {
    "through the outcome": ("y", "c"),
    "on the treatment's side": ("b", "x"),
}


@pytest.mark.parametrize("instrument", [True, False])
@pytest.mark.parametrize("second", sorted(SECOND_LOOPS))
def test_a_second_reaching_loop_is_outside_the_two_equations(second,
                                                             instrument):
    program = _program(("x", "y"), SECOND_LOOPS[second],
                       instrument=instrument)
    result = themis.run(program)["results"][0]
    assert result["status"] == "needs_investigation", result["status"]
    assert _needs(result) and _needs(result)[0] == OUTSIDE, _needs(result)
    extensions = result.get("extensions") or {}
    assert "iv_identification" not in extensions
    assert "reduction" not in extensions["feedback_loop"]
    verify_honestly(program, result)
    themis.verify_refusal(program, result)


@pytest.mark.parametrize("second", sorted(SECOND_LOOPS))
def test_every_copy_names_a_loop_the_program_declares(second):
    program = _program(("x", "y"), SECOND_LOOPS[second])
    result = themis.run(program)["results"][0]
    declared = {frozenset({"x(u)", "y(u)"}),
                frozenset(f"{p}(u)" for p in SECOND_LOOPS[second])}
    named = [result["extensions"]["feedback_loop"],
             *(m["said"] for m in result["missing_information"])]
    for said in named:
        assert frozenset({said["left"], said["right"]}) in declared, said


def test_a_loop_that_reaches_nothing_leaves_the_two_equations_standing():
    """The denominator: a second loop the estimand does not reach is not
    under the ratio."""
    program = _program(("x", "y"), ("p", "q"))
    result = themis.run(program)["results"][0]
    assert result["status"] == "structurally_solved", result["status"]
    assert result["extensions"]["feedback_loop"]["reduction"]
    themis.verify(program, result)


def test_with_data_no_number_is_estimated_where_a_second_loop_reaches():
    frame = _draws("outcome")
    program = _program(("x", "y"), ("y", "c"))
    result = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    assert result.get("numeric_estimate") is None
    assert OUTSIDE in _needs(result)


# --------------------------------------------------------------- the forgery


@pytest.fixture(params=["structural", "numeric"])
def the_answer_that_ignores_the_second_loop(request):
    """The honest answer to z -> x -> y -> c with only x and y looped."""
    program = _program(("x", "y"), edges=[("y", "c")])
    if request.param == "structural":
        return themis.run(program)["results"][0]
    frame = _draws("outcome")
    return themis.estimate(program, frame, ci_bootstrap=0)["results"][0]


def test_a_reduction_beside_a_second_reaching_loop_is_refused(
        the_answer_that_ignores_the_second_loop):
    """Same graph, one more declaration: y and c move each other. The
    answer's instrument, its withdrawal and its block all still name what
    the program declares; the number is the one the first test computes."""
    answer = the_answer_that_ignores_the_second_loop
    assert answer["extensions"]["feedback_loop"]["reduction"]
    single = _program(("x", "y"), edges=[("y", "c")])
    themis.verify(single, copy.deepcopy(answer))
    looped = _program(("x", "y"), ("y", "c"), edges=[("y", "c")])
    with pytest.raises(VerificationError) as caught:
        themis.verify(looped, answer)
    assert "reaches 2 declared loops" in str(caught.value), str(caught.value)
