"""What a mediation answer promises, held to the graph it promises it of.

``extensions.mediation_decomposition`` and its joint twin are what tell a
reader which decomposition they are being given — the natural effects, or
only the controlled one, or neither — and what has to hold for it. Nothing
re-derived them. ``verify_mediation_numeric`` audits ``numeric_estimate``,
which is a different object: the mediator could be renamed to the outcome,
the adjustment set replaced, an arm flipped from identifiable to not, and
the answer passed the public door.

One verifier serves both blocks, because there is one criterion. Pearl's
2001 conditions with the mediator replaced by a SET
(VanderWeele-Vansteelandt 2014) reduce to his own at a singleton: the graph
with every member's outgoing edges cut is the graph with the one member's
cut, and the membership restriction is written over a set on both routes
already. A second transcription would be one more place for the two to
disagree about the same theorem.

The two claims are held differently, and the asymmetry is the design. A
claim of identifiability NAMES the W that carries it, so it is checkable in
full. A claim of non-identifiability names no witness and is the claim that
withholds an answer from a reader, so it is held to being negative by
search — a W satisfying every condition that went unnamed is the failure.

``failed_condition`` is checked for agreement and not re-derived. Which
condition is named is the label of the candidate that got FURTHEST along a
fixed order, searched without the membership restriction so an intermediate
confounder can be named rather than hidden — a property of that search, not
of the graph. What IS a graph fact is that a condition is named exactly
when one failed, and that is checked.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program(nodes, edges, query):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in nodes]
    statements += [{"kind": "cause", "from": _atom(u), "to": _atom(w)}
                   for u, w in edges]
    statements.append({"kind": "query", "id": "q", "query": query})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


def _query(**extra):
    return {"kind": "effect",
            "intervention": {"atom": _atom("x"), "value": True},
            "target": {"atom": _atom("y"), "value": True},
            "given": [], **extra}


SINGLE = _program(
    ["x", "m", "y"], [("x", "m"), ("m", "y"), ("x", "y")],
    _query(mediator=_atom("m")))

JOINT = _program(
    ["x", "m1", "m2", "y"],
    [("x", "m1"), ("x", "m2"), ("m1", "y"), ("m2", "y"), ("x", "y")],
    _query(mediators=[_atom("m1"), _atom("m2")]))

#: An intermediate confounder: ``c`` descends from the treatment and is the
#: set that would block the mediator-outcome back door, so both routes
#: refuse it and the natural effects are honestly non-identifiable.
INTERMEDIATE = _program(
    ["x", "c", "m", "y"],
    [("x", "c"), ("c", "m"), ("c", "y"), ("x", "m"), ("m", "y"), ("x", "y")],
    _query(mediator=_atom("m")))


def _answer(program):
    return themis.run(program)["results"][0]


def _block(result):
    extensions = result["extensions"]
    for key in ("mediation_decomposition", "mediation_joint_decomposition"):
        if key in extensions:
            return extensions[key]
    raise AssertionError(sorted(extensions))


def _refuses(program, result, fragment):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


def _tampered(program, change):
    result = copy.deepcopy(_answer(program))
    change(_block(result))
    return result


# ------------------------------------------------------------- denominators


@pytest.mark.parametrize("program", [SINGLE, JOINT, INTERMEDIATE],
                         ids=["single", "joint", "intermediate"])
def test_an_untouched_mediation_answer_passes(program):
    themis.verify(program, _answer(program))


def test_the_intermediate_confounder_is_honestly_non_identifiable():
    """The denominator for the negative search. If the graph identified
    the natural effects after all, the case below would prove nothing."""
    block = _block(_answer(INTERMEDIATE))
    assert block["nde_nie"]["identifiable"] is False, block
    assert block["nde_nie"]["failed_condition"] is not None, block


def test_the_joint_block_can_report_both_arms_and_the_single_one_cannot():
    """The one field where the two blocks genuinely differ is a
    vocabulary, not a rule: the joint one has a member for both arms
    identifiable and the singular one answers by naming the stronger."""
    joint, single = _block(_answer(JOINT)), _block(_answer(SINGLE))
    assert joint["nde_nie"]["identifiable"] and joint["cde"]["identifiable"]
    assert joint["strategy"] == "nde_nie+cde", joint
    assert single["nde_nie"]["identifiable"] and single["cde"]["identifiable"]
    assert single["strategy"] == "nde_nie", single


# --------------------------------------------------- the mediator declared


@pytest.mark.parametrize("program,key,value", [
    (SINGLE, "mediator", "y(u)"),
    (JOINT, "mediators", ["m1(u)", "y(u)"]),
    (JOINT, "mediators", ["m1(u)"]),
])
def test_a_block_naming_other_mediators_than_the_query_is_refused(
        program, key, value):
    _refuses(program, _tampered(program, lambda b: b.__setitem__(key, value)),
             "as the mediator(s) beside a query that declares")


@pytest.mark.parametrize("program,key", [
    (SINGLE, "mediator_valid"), (JOINT, "mediator_set_valid")])
def test_denying_that_the_mediator_mediates_is_refused(program, key):
    """Vacuous is a strong claim: it says both arms were never on the
    table. It is a fact about directed paths, so it is one."""
    _refuses(program, _tampered(program, lambda b: b.__setitem__(key, False)),
             "carry a directed path from the treatment through every one")


# --------------------------------------------- a positive claim, in full


@pytest.mark.parametrize("arm", ["nde_nie", "cde"])
def test_an_adjustment_set_that_does_not_satisfy_the_conditions_is_refused(
        arm):
    _refuses(SINGLE, _tampered(SINGLE, lambda b: b[arm].update(
        {"adjustment": ["y(u)"]})),
        "which does not satisfy the conditions")


@pytest.mark.parametrize("arm", ["nde_nie", "cde"])
def test_claiming_identifiability_with_no_assumption_is_refused(arm):
    """The premises are the price of the claim; a claim with no price is
    not the same claim."""
    _refuses(SINGLE, _tampered(SINGLE, lambda b: b[arm].update(
        {"assumptions": []})),
        "claims identifiability and names no assumption")


# --------------------------------------- a negative claim, held to being one


def test_withholding_an_identifiable_decomposition_is_refused():
    """The forgery this half exists to stop. Reporting a decomposition
    non-identifiable where a valid W exists withholds an answer from a
    reader who could have had it."""
    def change(block):
        block["nde_nie"].update(
            {"identifiable": False, "adjustment": [],
             "failed_condition": "M1", "assumptions": []})
        block["strategy"] = "cde"
    _refuses(SINGLE, _tampered(SINGLE, change),
             "the answer was withheld from a reader who could have had it")


def test_a_non_identifiable_arm_that_still_names_a_set_is_refused():
    def change(block):
        block["nde_nie"]["adjustment"] = ["c(u)"]
    _refuses(INTERMEDIATE, _tampered(INTERMEDIATE, change),
             "is not identifiable and still names an adjustment set")


# ----------------------------------------- the two fields that must agree


def test_a_condition_named_beside_an_identifiable_arm_is_refused():
    """``failed_condition`` is not re-derived — which condition gets named
    is a property of the producer's search order — but a condition is
    named exactly when one failed, and that is a graph fact."""
    _refuses(SINGLE, _tampered(SINGLE, lambda b: b["nde_nie"].__setitem__(
        "failed_condition", "M3")),
        "a condition is named exactly when one failed")


def test_dropping_the_condition_from_a_failing_arm_is_refused():
    _refuses(INTERMEDIATE, _tampered(
        INTERMEDIATE, lambda b: b["nde_nie"].__setitem__(
            "failed_condition", None)),
        "a condition is named exactly when one failed")


@pytest.mark.parametrize("program,claimed", [
    (SINGLE, "cde"), (SINGLE, "none"), (JOINT, "nde_nie"), (JOINT, "none")])
def test_a_strategy_the_arms_do_not_support_is_refused(program, claimed):
    _refuses(program, _tampered(
        program, lambda b: b.__setitem__("strategy", claimed)),
        "as the strategy while the arms it reports identifiable make it")
