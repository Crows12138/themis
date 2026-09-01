"""A do() over a SET is told to a reader in a block nothing re-derived.

``extensions.identification`` and ``extensions.joint_identification`` answer
the same reader question — where did this number come from — and the
contract says outright that their ``pattern`` vocabularies are disjoint. A
verifier that dispatches on that key therefore cannot reach the second, and
none did: an answer telling a reader to control for {W} over a treatment
vector passed ``themis.verify`` whatever W said, while the scalar sentence
beside it was re-derived from the graph edge by edge.

The criterion here is the treatment-SET back door, and it is not a
conjunction of the scalar ones. Edges are cut out of EVERY treatment at
once — a path from one treatment through another into the outcome is inside
the intervention rather than a back door — and the held set may contain a
descendant of no treatment rather than of one. That difference is what the
first two cases below turn on: the other treatment is a legal thing to be
on a path and an illegal thing to hold.

``joint_general_id`` is the negative claim, identified precisely because no
adjustment set exists, so it is held to being negative the way ``c_factor``
already is — a valid joint adjustment set that went unnamed is the failure.
Both faces are exercised: a graph where one exists rejects the claim, and a
graph where none does accepts it.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


JOINT_QUERY = {
    "kind": "effect",
    "intervention": {"atom": _atom("a"), "value": True},
    "extra_interventions": [{"atom": _atom("b"), "value": True}],
    "target": {"atom": _atom("y"), "value": True},
    "given": []}


def _program(nodes, edges, latent=(), query=None):
    statements = [{"kind": "variable", "predicate": n, "domain": [True, False]}
                  for n in nodes]
    statements += [{"kind": "cause", "from": _atom(u), "to": _atom(w)}
                   for u, w in edges]
    statements += [{"kind": "bidirected", "left": _atom(u), "right": _atom(w)}
                   for u, w in latent]
    statements.append({"kind": "query", "id": "q",
                       "query": query or JOINT_QUERY})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


#: One observed confounder of both treatments and the outcome.
CONFOUNDED = _program(
    ["z", "a", "b", "y"],
    [("z", "a"), ("z", "b"), ("z", "y"), ("a", "y"), ("b", "y")])

#: Latent between a treatment and the outcome, with a mediator carrying the
#: effect: no joint adjustment set exists and the set-valued ID still
#: identifies. The general claim, honestly made.
GENERAL = _program(
    ["a", "b", "m", "y"],
    [("a", "m"), ("m", "y"), ("b", "y")], latent=[("a", "y")])


@pytest.fixture(scope="module")
def frame() -> pd.DataFrame:
    rng = np.random.default_rng(2)
    n = 4000
    z = rng.random(n) < 0.5
    a = rng.random(n) < (0.3 + 0.4 * z)
    b = rng.random(n) < (0.3 + 0.3 * z)
    y = rng.random(n) < (0.15 + 0.25 * a + 0.2 * b + 0.15 * z)
    return pd.DataFrame({"z": z, "a": a, "b": b, "y": y})


def _answer(frame):
    return themis.estimate(CONFOUNDED, frame, ci_bootstrap=0)["results"][0]


def _block(result):
    return result["extensions"]["joint_identification"]


def _refuses(result, fragment, program=CONFOUNDED):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


# ------------------------------------------------------------- denominators


def test_an_untouched_joint_answer_passes(frame):
    result = _answer(frame)
    assert _block(result)["pattern"] == "joint_backdoor"
    themis.verify(CONFOUNDED, result)


def test_an_honest_general_id_answer_passes():
    """The other pattern, and the branch the negative search could break:
    a rule that found an adjustment set here would refuse a correct
    answer."""
    result = themis.run(GENERAL)["results"][0]
    assert _block(result)["pattern"] == "joint_general_id"
    assert "adjustment_set" not in _block(result), _block(result)
    themis.verify(GENERAL, result)


def test_a_latent_edge_between_the_two_treatments_needs_no_adjustment():
    """The joint intervention cuts both, so a common cause of the pair
    alone confounds nothing — an empty set is the honest answer and the
    criterion has to agree."""
    program = _program(["a", "b", "y"], [("a", "y"), ("b", "y")],
                       latent=[("a", "b")])
    result = themis.run(program)["results"][0]
    assert _block(result)["adjustment_set"] == []
    themis.verify(program, result)


# ------------------------------------------------------- the adjustment set


def test_dropping_the_confounder_is_refused(frame):
    result = _answer(frame)
    _block(result)["adjustment_set"] = []
    _refuses(result, "does not satisfy the treatment-set back-door criterion")


def test_holding_the_outcome_is_refused(frame):
    result = _answer(frame)
    _block(result)["adjustment_set"] = ["y(u)"]
    _refuses(result, "does not satisfy the treatment-set back-door criterion")


def test_holding_the_other_treatment_is_refused(frame):
    """The set-specific failure. Holding ``b`` blocks nothing the joint
    intervention has not already cut, and it is a member of the vector,
    which the scalar criterion would have had no opinion about."""
    result = _answer(frame)
    _block(result)["adjustment_set"] = ["b(u)"]
    _refuses(result, "does not satisfy the treatment-set back-door criterion")


# ------------------------------------------------ the vector and its scope


def test_a_vector_missing_an_arm_is_refused(frame):
    """The set the criterion was checked on has to be the set the question
    intervenes on."""
    result = _answer(frame)
    _block(result)["treatments"] = ["a(u)"]
    _refuses(result, "names the treatment vector")


def test_a_vector_naming_a_bystander_is_refused(frame):
    result = _answer(frame)
    _block(result)["treatments"] = ["z(u)", "a(u)"]
    _refuses(result, "names the treatment vector")


def test_an_invented_condition_set_is_refused(frame):
    """``conditioned_on`` is what the QUESTION asks about, so a block that
    invents one describes a different estimand than the one answered."""
    result = _answer(frame)
    _block(result)["conditioned_on"] = ["z(u)"]
    _refuses(result, "which is not what the question conditions on")


# ---------------------------------------------- the general claim, held to


def test_claiming_the_general_solution_where_a_set_exists_is_refused(frame):
    """Too modest is a way to be wrong: a reader told the answer needed
    the set-valued ID is told nothing about the set that would have
    served."""
    result = _answer(frame)
    block = _block(result)
    block["pattern"] = "joint_general_id"
    block.pop("adjustment_set", None)
    _refuses(result, "is a valid joint adjustment set that went unnamed")


def test_a_block_naming_a_node_the_graph_does_not_have_is_refused(frame):
    result = _answer(frame)
    _block(result)["adjustment_set"] = ["nowhere(u)"]
    _refuses(result, "not a node in the graph")
