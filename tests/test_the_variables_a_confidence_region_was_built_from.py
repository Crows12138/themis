"""A region can be exact arithmetic on the wrong variables.

``verify_vector_iv_region`` re-derives the Anderson-Rubin region from the
recorded second moments: the inverted quadratic, the shape in the
eigenbasis of A, the centre, the 2SLS point, every coordinate projection.
Those moments arrive already built from whichever columns were chosen, so
every one of those numbers can be right about a region computed on the
wrong variables. ``extensions.vector_iv_identification`` is the block that
names them, and it said anything: that the treatments are their own
instruments, that the outcome is one, that an instrument moves something it
cannot reach, that the coordinate order is something else.

The condition is read on the treatment SET and is NOT a conjunction of the
scalar ones. Both faces are exercised here, because getting it backwards in
either direction is a real failure:

- an instrument that reaches the outcome only through ANOTHER treatment in
  the vector is VALID here — that path is inside the intervention — and the
  scalar test rejects it, correctly for the scalar test, where the other
  treatment is a confounder;
- a set that holds a descendant of any treatment is refused, because
  conditioning on a mediator of one member breaks what it breaks in the
  scalar case.

``relevance`` is reported rather than required — the region covers whether
or not the instruments move anything — and reported is not unchecked. An
empty ``moves`` is a fact about the graph, so it is re-derived in the
ORIGINAL graph, where relevance lives, rather than in the cut one.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


VECTOR_QUERY = {
    "kind": "effect",
    "intervention": {"atom": _atom("a"), "value": 1.0},
    "extra_interventions": [{"atom": _atom("b"), "value": 1.0}],
    "target": {"atom": _atom("y"), "value": 1.0},
    "given": []}


def _program(nodes, edges, latent):
    statements = [{"kind": "variable", "predicate": n, "scale": "continuous"}
                  for n in nodes]
    statements += [{"kind": "cause", "from": _atom(u), "to": _atom(w)}
                   for u, w in edges]
    statements += [{"kind": "bidirected", "left": _atom(u), "right": _atom(w)}
                   for u, w in latent]
    statements.append({"kind": "query", "id": "q", "query": VECTOR_QUERY})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": statements}


#: One instrument per treatment.
SEPARATE = _program(
    ["z1", "z2", "a", "b", "y"],
    [("z1", "a"), ("z2", "b"), ("a", "y"), ("b", "y")],
    [("a", "y"), ("b", "y")])

#: ``z1`` reaches the outcome through BOTH treatments and through nothing
#: else. Valid for the vector, rejected for either treatment alone.
SHARED = _program(
    ["z1", "z2", "a", "b", "y"],
    [("z1", "a"), ("z1", "b"), ("z2", "b"), ("a", "y"), ("b", "y")],
    [("a", "y"), ("b", "y")])


def _frame(shared: bool, n=5000, seed=5):
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z1, z2 = rng.standard_normal(n), rng.standard_normal(n)
    a = 0.9 * z1 + 0.7 * u + 0.3 * rng.standard_normal(n)
    b = ((0.6 * z1 if shared else 0.0) + 0.8 * z2 + 0.6 * u
         + 0.3 * rng.standard_normal(n))
    y = 1.2 * a + 0.7 * b + 1.5 * u + 0.4 * rng.standard_normal(n)
    return pd.DataFrame({"z1": z1, "z2": z2, "a": a, "b": b, "y": y})


@pytest.fixture(scope="module")
def answer():
    result = themis.estimate(
        SEPARATE, _frame(shared=False), ci_bootstrap=0)["results"][0]
    assert "vector_iv_identification" in (result.get("extensions") or {})
    return result


def _tampered(answer, change):
    import copy
    bad = copy.deepcopy(answer)
    change(bad["extensions"]["vector_iv_identification"])
    return bad


def _refuses(result, fragment, program=SEPARATE):
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert fragment in str(caught.value), str(caught.value)


# ------------------------------------------------------------- denominators


def test_an_untouched_region_answer_passes(answer):
    themis.verify(SEPARATE, answer)


def test_an_instrument_reaching_the_outcome_through_the_other_treatment():
    """The face a conjunction of scalar tests would get wrong. ``z1``
    reaches the outcome only through ``a`` and ``b``, both of which the
    joint intervention cuts, so it is a valid instrument for the vector
    and is named as one."""
    result = themis.estimate(
        SHARED, _frame(shared=True), ci_bootstrap=0)["results"][0]
    block = result["extensions"]["vector_iv_identification"]
    assert "z1" in block["instruments"], block
    moves = next(r["moves"] for r in block["relevance"]
                 if r["instrument"] == "z1")
    assert moves == ["a", "b"], block
    themis.verify(SHARED, result)


# ------------------------------------------------------- what it says no to


def test_the_treatments_as_their_own_instruments_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b.__setitem__(
        "instruments", ["a", "b"])), "which is a treatment")


def test_the_outcome_as_an_instrument_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b.__setitem__(
        "instruments", ["z1", "y"])), "which is the outcome")


def test_an_instrument_with_its_own_road_to_the_outcome_is_refused(answer):
    """``z2`` is honest here; the graph is what decides. Swap in a
    bystander that is not m-separated from the outcome with every
    treatment cut and the claim fails on the criterion rather than on a
    name."""
    program = _program(
        ["z1", "z2", "w", "a", "b", "y"],
        [("z1", "a"), ("z2", "b"), ("w", "y"), ("a", "y"), ("b", "y")],
        [("a", "y"), ("b", "y")])
    frame = _frame(shared=False)
    rng = np.random.default_rng(11)
    frame = frame.assign(w=rng.standard_normal(len(frame)))
    result = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    block = result["extensions"]["vector_iv_identification"]
    assert "w" not in block["instruments"], block
    block["instruments"] = list(block["instruments"]) + ["w"]
    block["relevance"] = list(block["relevance"]) + [
        {"instrument": "w", "moves": ["b"]}]
    with pytest.raises(VerificationError) as caught:
        themis.verify(program, result)
    assert "reaches the outcome with every treatment" in str(caught.value), \
        str(caught.value)


def test_a_reordered_treatment_vector_is_refused(answer):
    """The region's coordinate projections are indexed by this list, so a
    reader told which interval belongs to which treatment is reading this
    order. Sorting it away would make the two disagree silently."""
    _refuses(_tampered(answer, lambda b: b.__setitem__(
        "treatments", ["b", "a"])), "beside a query that intervenes, in order")


def test_a_vector_naming_a_bystander_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b.__setitem__(
        "treatments", ["a", "z2"])), "names the treatment vector")


def test_a_renamed_outcome_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b.__setitem__("outcome", "a")),
             "as the outcome beside a query whose outcome is")


def test_a_condition_set_meeting_the_answer_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b.__setitem__("conditioning", ["y"])),
             "meets the treatments, the outcome or an instrument")


@pytest.mark.parametrize("moves,fragment", [
    (["y"], "moves ['y']"),
    ([], "moves []"),
])
def test_a_relevance_claim_the_graph_denies_is_refused(answer, moves, fragment):
    """Reported is not unchecked. Both directions: an instrument credited
    with moving something it cannot reach, and one denied what it does."""
    _refuses(_tampered(answer, lambda b: b["relevance"][0].__setitem__(
        "moves", moves)), fragment)


def test_relevance_reported_for_the_wrong_instruments_is_refused(answer):
    _refuses(_tampered(answer, lambda b: b["relevance"].__setitem__(
        0, {"instrument": "z2", "moves": ["b"]})),
        "reports relevance for")
