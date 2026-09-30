"""A joint read beside a derived risk shares the risk's factors.

Past the ancestral bound the observational joint was read off the chain
rule's two marginals, ``P(X)·P(Y | X)``, while the interventional risk beside
it was derived by adjusting over the back-door set, ``Σ_z P(z)·P(Y | X, z)``.
The two are one distribution's marginal and its adjustment, and asked for in
one round as separate entries they were guessed separately. The demo asked
"did I do badly on the exam because I slept badly the night before?", and the
model put the rate of doing badly among the well rested at 0.15 in the one
and at 0.28 in the other. Both lay inside the bounds consistency sets, so
nothing was refused: the probability of necessity — the question asked —
came back as all of [0, 1], its lower bound below zero and its upper above
one before clamping, because its numerator and denominator were read off two
different distributions.

Where the door derives the risk from theta, the joint is now read through the
risk's own adjustment set, ``Σ_z P(z)·P(x | z)·P(y | x, z)`` — the chain rule
over the set, X and Y. The two share every factor but ``P(x | z)``, and the
risk then lies inside the bounds the joint sets on it whatever values in
[0, 1] the factors are given.

Pinned here:

- past the bound the joint is asked for through the adjustment set, and not
  as the two marginals;
- any numbers given to what is asked reach an answer the verifier accepts,
  for a counterfactual cell and for the probabilities of causation;
- where theta holds the two marginals, or the risk is supplied, or the graph
  offers no back-door set, the joint is read as before;
- the step records the set it read through, and the verifier reads it: a
  step naming the exposure in it is refused, and so is one that drops it.
"""
from __future__ import annotations

import copy
import random

import pytest

import themis
from tests.test_a_counterfactual_too_wide_to_enumerate_is_asked_for_in_one_round import (  # noqa: E501
    CAUSATION,
    _Model,
    _a,
    _answered,
    _asked,
    _conditions,
    _counterfactual,
    _program,
    _run,
)
from themis.verifier.errors import RuleCheckFailed


def _answered_at_random(program, asked, seed):
    """Every ask given its own number, as a guesser would give it: nothing
    ties one to another."""
    rng = random.Random(seed)
    program = copy.deepcopy(program)
    for stub in asked:
        filled = copy.deepcopy(stub)
        filled["value"] = round(rng.uniform(0.02, 0.98), 3)
        filled["annotations"] = {"source": "a guess"}
        program["statements"].insert(-1, filled)
    return program


def _step(result):
    (step,) = result["derivation"]["steps"]
    return step


def _through(result):
    recorded = _step(result)["inputs"].get("joint_through")
    if recorded is None:
        return None
    return [atom["predicate"] for atom in recorded["items"]]


# --- what is asked -----------------------------------------------------------

@pytest.mark.parametrize("query", [_counterfactual(True, False), CAUSATION],
                         ids=["cell", "causation"])
def test_past_the_bound_the_joint_is_asked_through_the_adjustment_set(query):
    model = _Model(9, 2, seed=5)
    asked = _asked(_run(_program(model, query)))
    confounders = set(model.confounders)
    by_target: dict[str, set] = {}
    for stub in asked:
        by_target.setdefault(stub["target"]["atom"]["predicate"], set()).add(
            frozenset(_conditions(stub)))
    assert by_target["x"] == {frozenset(confounders)}, by_target["x"]
    assert by_target["y"] == {frozenset(confounders | {"x"})}, by_target["y"]
    assert all(by_target[c] == {frozenset()} for c in confounders), by_target
    assert set(by_target) == confounders | {"x", "y"}, set(by_target)


# --- any numbers -------------------------------------------------------------

_CELLS = [
    (True, False, None),
    (False, True, None),
    (True, False, True),
    (False, True, False),
]


@pytest.mark.parametrize("seed", range(4))
@pytest.mark.parametrize("observed, intervention, factual", _CELLS)
def test_any_numbers_given_to_the_asks_answer_a_counterfactual_cell(
        observed, intervention, factual, seed):
    model = _Model(9, 2, seed=seed)
    program = _program(model, _counterfactual(observed, intervention,
                                              factual=factual))
    program = _answered_at_random(program, _asked(_run(program)), seed)
    result = _run(program)
    assert result["status"] in ("counterfactual_solved",
                                "counterfactual_bounded"), (
        result["status"], result.get("missing_information"))
    assert _through(result) == model.confounders
    themis.verify(copy.deepcopy(program), result)


@pytest.mark.parametrize("seed", range(6))
def test_any_numbers_given_to_the_asks_answer_the_probabilities_of_causation(
        seed):
    model = _Model(9, 2, seed=seed)
    program = _program(model, CAUSATION)
    program = _answered_at_random(program, _asked(_run(program)), seed)
    result = _run(program)
    assert result["status"] == "counterfactual_bounded", (
        result["status"], result.get("missing_information"))
    assert _through(result) == model.confounders
    themis.verify(copy.deepcopy(program), result)


def test_the_shape_that_raised_it():
    """Five confounders of the exposure and the outcome and eight more causes
    of the outcome alone, answered by guesses: the tables over the five for
    the outcome at both exposures and for the exposure, and each
    confounder's own rate."""
    model = _Model(8, 5, seed=8)
    program = _program(model, CAUSATION)
    asked = _asked(_run(program))
    assert len(asked) == 3 * 2 ** 5 + 5, len(asked)
    program = _answered_at_random(program, asked, 8)
    result = _run(program)
    assert result["status"] == "counterfactual_bounded", (
        result["status"], result.get("missing_information"))
    themis.verify(copy.deepcopy(program), result)


# --- where the joint is read as before --------------------------------------

def _marginals(program, model):
    """``P(X)`` and ``P(Y | X)``, as a reader who measured them would write
    them."""
    asked = [
        {"kind": "probability",
         "target": {"atom": _a("x"), "value": True}, "given": [],
         "provenance": "observational"},
        *({"kind": "probability",
           "target": {"atom": _a("y"), "value": True},
           "given": [{"atom": _a("x"), "value": x}],
           "provenance": "observational"} for x in (True, False)),
    ]
    return _answered(program, model, asked)


def test_where_theta_holds_the_two_marginals_they_are_read():
    model = _Model(9, 2, seed=3)
    program = _program(model, _counterfactual(True, False))
    program = _marginals(program, model)
    program = _answered(program, model, _asked(_run(program)))
    result = _run(program)
    assert result["status"] == "counterfactual_solved", result["status"]
    assert _through(result) is None
    themis.verify(copy.deepcopy(program), result)


def test_a_supplied_risk_is_read_beside_the_two_marginals():
    model = _Model(9, 2, seed=4)
    query = _counterfactual(True, False)
    query["experimental_risk_control"] = round(model.risk(False), 6)
    asked = _asked(_run(_program(model, query)))
    assert {s["target"]["atom"]["predicate"] for s in asked} == {"x", "y"}
    assert all(_conditions(s) <= {"x"} for s in asked), asked


def test_a_graph_with_no_back_door_set_reads_the_two_marginals():
    """A bow between the exposure and the outcome: no set adjusts, so there
    is no set to share."""
    model = _Model(11, 0, seed=6)
    asked = _asked(_run(_program(model, _counterfactual(True, False),
                                 bidirected=[("x", "y")])))
    x_asks = [s for s in asked if s["target"]["atom"]["predicate"] == "x"]
    assert x_asks and all(not _conditions(s) for s in x_asks), x_asks


# --- the record --------------------------------------------------------------

def _answered_cell(seed=2):
    model = _Model(9, 2, seed=seed)
    program = _program(model, _counterfactual(False, True))
    program = _answered_at_random(program, _asked(_run(program)), seed)
    return model, program, _run(program)


def test_a_step_that_reads_through_the_exposure_is_refused():
    model, program, result = _answered_cell()
    forged = copy.deepcopy(result)
    recorded = _step(forged)["inputs"]["joint_through"]
    recorded["items"].append({"kind": "atom", "predicate": "x", "args": []})
    with pytest.raises(RuleCheckFailed, match="joint_through"):
        themis.verify(copy.deepcopy(program), forged)


def test_a_step_that_drops_the_record_is_refused():
    """Without the set the verifier has no route to the joint: theta holds
    neither the marginals nor the ancestors' tables."""
    model, program, result = _answered_cell()
    forged = copy.deepcopy(result)
    del _step(forged)["inputs"]["joint_through"]
    with pytest.raises(RuleCheckFailed):
        themis.verify(copy.deepcopy(program), forged)
