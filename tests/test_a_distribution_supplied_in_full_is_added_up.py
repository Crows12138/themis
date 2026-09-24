"""A distribution supplied in full is added up — by the builder, and again
by the verifier.

The builder checked the probability axiom only on the way to completing a
group, which is the case where exactly one value is missing. A pair given
in full was never added up. So with ``P(y=True|x=True)=0.7`` beside
``P(y=False|x=True)=0.4`` (1.1), and ``P(y=True|x=False)=0.3`` beside
``P(y=False|x=False)=0.6`` (0.9), the joint the attribution bounds are
built from still summed to one, the check on it passed, and the answer
came back ``counterfactual_bounded`` with PS ≥ 0.667 where the numbers the
caller meant give PS ≥ 0.571. The audit accepted it: its context is built
by the same builder, and it reads cells with a copy of the producer's
reader.

The shape is the one an agent is led to. The ask for a missing boolean
distribution lists both of its cells, so an agent filling priors writes
both, and two numbers a model writes separately need not add up.

What is held:

- a group supplied in full that does not sum to one is refused, and the
  refusal names the distribution with its condition — the cancelling case
  included, and the case of a single pair that used to be caught later
  under a reason about interventional risks;
- a group supplied in part is refused once its values already exceed one,
  however many values it leaves out;
- a consistent pair supplied in full answers exactly as its true cells
  alone do;
- the verifier holds the same axiom in its own code: with the builder's
  check switched off the kernel answers the cancelling case wrongly again,
  and the audit refuses it.
"""
from __future__ import annotations

import math

import pytest

import themis
from themis.input.semantic_validator import validate_program
from themis.input.syntactic_validator import validate_ast
from themis.runtime import theta_builder
from themis.runtime.numeric_estimator import ProbabilityKey, Theta
from themis.runtime.theta_words import Refuses
from themis.types import Atom
from themis.verifier.errors import VerificationError
from themis.verifier.theta_rules import verify_theta_is_a_distribution


def _atom(p):
    return {"predicate": p, "args": []}


def _prob(target, value, p, given=()):
    return {"kind": "probability",
            "target": {"atom": _atom(target), "value": value},
            "given": [{"atom": _atom(a), "value": v} for a, v in given],
            "value": p}


def _attribution(*probs, domains=True):
    declared = [{"kind": "variable", "predicate": v, "domain": [True, False]}
                for v in ("x", "y")] if domains else []
    return {"version": "0.1", "domain": {"objects": []}, "statements": [
        *declared,
        {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
        *probs,
        {"kind": "query", "id": "q", "query": {
            "kind": "causation", "cause": _atom("x"), "effect": _atom("y")}},
    ]}


TRUE_CELLS = (
    _prob("x", True, 0.5),
    _prob("y", True, 0.7, [("x", True)]),
    _prob("y", True, 0.3, [("x", False)]),
)

#: Off by 0.1 in opposite directions, so the joint still sums to one.
CANCELLING = _attribution(
    _prob("x", True, 0.5), _prob("x", False, 0.5),
    _prob("y", True, 0.7, [("x", True)]), _prob("y", False, 0.4, [("x", True)]),
    _prob("y", True, 0.3, [("x", False)]), _prob("y", False, 0.6, [("x", False)]),
)


def _refusal(program) -> theta_builder.ConflictingThetaEntry:
    with pytest.raises(theta_builder.ConflictingThetaEntry) as caught:
        themis.run(program)
    return caught.value


# ------------------------------------------------------------------ builder


def test_the_cancelling_pairs_are_refused_by_name():
    exc = _refusal(CANCELLING)
    assert exc.species is Refuses.A_FULL_DISTRIBUTION_DOES_NOT_SUM_TO_ONE
    assert exc.details["distribution"] in ("P(y=*|x=True)", "P(y=*|x=False)")
    assert exc.details["distribution"] in str(exc)


def test_one_pair_off_is_refused_as_what_it_is():
    """It used to reach the attribution solver and come back as risks that
    contradict the joint — true of the arithmetic, and no help in finding
    which two numbers to change."""
    exc = _refusal(_attribution(
        _prob("x", True, 0.7), _prob("x", False, 0.2), *TRUE_CELLS[1:]))
    assert exc.species is Refuses.A_FULL_DISTRIBUTION_DOES_NOT_SUM_TO_ONE
    assert exc.details["distribution"] == "P(x=*)"
    assert math.isclose(float(exc.details["total"]), 0.9)


def test_a_group_given_in_part_is_refused_once_it_exceeds_one():
    """Two of four values supplied, so nothing is completed — and they
    already leave the other two less than nothing."""
    program = {"version": "0.1", "domain": {"objects": []}, "statements": [
        {"kind": "variable", "predicate": "c",
         "domain": ["red", "green", "blue", "yellow"]},
        _prob("c", "red", 0.7), _prob("c", "green", 0.5),
    ]}
    exc = _refusal(program)
    assert exc.species is Refuses.THE_SUPPLIED_MASS_LEAVES_NO_COMPLEMENT
    assert exc.details["distribution"] == "P(c=*)"
    assert exc.details["missing"] == "blue, yellow"


def test_a_consistent_pair_given_in_full_answers_as_its_true_cells_do():
    full = _attribution(
        _prob("x", True, 0.5), _prob("x", False, 0.5),
        _prob("y", True, 0.7, [("x", True)]), _prob("y", False, 0.3, [("x", True)]),
        _prob("y", True, 0.3, [("x", False)]), _prob("y", False, 0.7, [("x", False)]),
    )
    got = themis.run(full)["results"][0]
    want = themis.run(_attribution(*TRUE_CELLS))["results"][0]
    assert got["status"] == want["status"] == "counterfactual_bounded"
    for p in ("pn", "ps", "pns"):
        for end in ("lower", "upper"):
            assert math.isclose(got["extensions"]["causation"][p][end],
                                want["extensions"]["causation"][p][end],
                                abs_tol=1e-12), (p, end)


def test_a_domain_nobody_declared_is_not_read_as_complete():
    """With no declaration the builder infers ``y``'s domain from the one
    value the program mentions, and a single value says nothing about
    what else ``y`` can be — so ``P(y=True|x=True)=0.7`` alone is not a
    distribution summing to 0.7."""
    program = _attribution(*TRUE_CELLS, domains=False)
    themis.run(program)
    verify_theta_is_a_distribution(theta_builder.build_theta_from_program(
        validate_program(validate_ast(program))))


# ------------------------------------------------------------------ verifier


def test_the_audit_refuses_what_the_builder_let_through(monkeypatch):
    """The audit's context comes from the same builder, so the builder's
    check is switched off for both — what refuses is the verifier's own."""
    monkeypatch.setattr(theta_builder, "_hold_the_axiom",
                        lambda *args, **kwargs: None)
    result = themis.run(CANCELLING)["results"][0]
    assert result["status"] == "counterfactual_bounded"
    assert math.isclose(result["extensions"]["causation"]["ps"]["lower"], 2 / 3)
    with pytest.raises(VerificationError, match=r"P\(y=\*\|x=(True|False)\)"):
        themis.verify(CANCELLING, result)
    with pytest.raises(VerificationError, match=r"P\(y=\*\|x=(True|False)\)"):
        themis.verify_answer_claims(CANCELLING, result)


def _theta(*cells, domain=(True, False)):
    y = Atom(predicate="y", args=())
    return Theta(entries={ProbabilityKey(target_atom=y, target_value=v,
                                         given=frozenset()): p
                          for v, p in cells},
                 domains={y: domain})


@pytest.mark.parametrize("cells, says", [
    (((True, 0.7), (False, 0.4)), r"sum to .*, not 1"),
    (((True, 0.7),), None),
    (((True, float("nan")),), "not a probability"),
    (((True, 1.2),), "not a probability"),
], ids=["full-off", "partial-fine", "nan", "above-one"])
def test_the_verifier_reads_the_axiom_itself(cells, says):
    theta = _theta(*cells)
    if says is None:
        verify_theta_is_a_distribution(theta)
        return
    with pytest.raises(VerificationError, match=says):
        verify_theta_is_a_distribution(theta)


def test_a_partial_group_over_one_is_refused_by_the_verifier_too():
    theta = _theta(("red", 0.7), ("green", 0.5),
                   domain=("red", "green", "blue", "yellow"))
    with pytest.raises(VerificationError, match="more than 1"):
        verify_theta_is_a_distribution(theta)
