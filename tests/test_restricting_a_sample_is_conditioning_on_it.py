"""Restricting a sample is conditioning on it.

Two caveats say an effect was estimated where a collider is conditioned on:
one when the question's ``given`` names it, one when an observation
restricts the data to it. They asked one question of one estimate two ways.
The first asked whether conditioning on ``w`` opens a path between the
treatment and the outcome, over the question's ``given`` alone; the second
asked whether ``w`` is a directed common effect of the two. So the same
``w`` between latent arms was a collider in ``given`` and nothing at all in
the sample, and a restriction that closed the path a conditioned collider
opened was not read by the caveat about that collider.

Both now ask the first question, over everything the estimate is taken
given: the question's ``given`` and every atom the sample is restricted to.
Selection recovery keeps its own scope -- a directed common effect -- so a
restriction between latent arms owes the caveat and no recovery verdict.
"""
from __future__ import annotations

import pytest

import themis
from tests.answer_corpus import the_door_for

COLLIDER = "collider_conditioning_opens_backdoor"
SELECTION = "selection_on_collider_opens_path"
_ME = [{"type": "const", "name": "me"}]


def _at(p):
    return {"predicate": p, "args": _ME}


def _program(causes, *, bidirected=(), given=(), observed=()):
    names = sorted({p for edge in (*causes, *bidirected) for p in edge}
                   | set(given) | set(observed))
    st = [{"kind": "variable", "predicate": p, "domain": [True, False]} for p in names]
    st += [{"kind": "cause", "from": _at(a), "to": _at(b)} for a, b in causes]
    st += [{"kind": "bidirected", "left": _at(a), "right": _at(b)} for a, b in bidirected]
    st += [{"kind": "observation", "atom": _at(w), "value": True} for w in observed]
    st.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": [{"atom": _at(g), "value": True} for g in given],
        "intervention": {"atom": _at("x"), "value": True},
        "target": {"atom": _at("y"), "value": True}}})
    return {"version": "0.1", "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": st}


def _answer(program):
    return next(r for r in themis.run(program)["results"] if r.get("query_id") == "q")


def _caveats(result):
    return sorted((g["kind"], g["describes"][0]["said"]["collider"])
                  for g in (result.get("data_gap_report") or {}).get("gaps") or ()
                  if g.get("kind") in (COLLIDER, SELECTION))


#: (causes, bidirected, the atom conditioned on), each a collider on a path
#: between x and y once conditioned: latent arms, one arm latent, and a
#: descendant of a collider whose arms are latent.
COLLIDERS = {
    "latent arms": ((("x", "y"),), (("x", "w"), ("w", "y")), "w"),
    "one latent arm": ((("x", "y"), ("y", "w")), (("x", "w"),), "w"),
    "below latent arms": ((("x", "y"), ("c", "w")), (("x", "c"), ("c", "y")), "w"),
    "the canonical collider": ((("x", "y"), ("x", "w"), ("y", "w")), (), "w"),
}

#: The same atoms, and none is a collider on any path between x and y.
NOT_COLLIDERS = {
    "a chain": ((("x", "w"), ("w", "y")), (), "w"),
    "a latent cause of x alone": ((("x", "y"),), (("x", "w"),), "w"),
}


@pytest.mark.parametrize("shape", sorted(COLLIDERS))
def test_given_or_restricted_the_same_collider_is_told(shape):
    causes, bidirected, w = COLLIDERS[shape]
    for how, kind in (("given", COLLIDER), ("observed", SELECTION)):
        program = _program(causes, bidirected=bidirected, **{how: [w]})
        result = _answer(program)
        assert _caveats(result) == [(kind, w)], (how, _caveats(result))
        the_door_for(result)(program, result)


@pytest.mark.parametrize("shape", sorted(NOT_COLLIDERS))
def test_given_or_restricted_what_is_no_collider_is_not_told(shape):
    causes, bidirected, w = NOT_COLLIDERS[shape]
    for how in ("given", "observed"):
        program = _program(causes, bidirected=bidirected, **{how: [w]})
        result = _answer(program)
        assert _caveats(result) == [], (how, _caveats(result))
        the_door_for(result)(program, result)


#: x -> w <- u -> y, with x -> y: conditioning on w opens x -> w <- u -> y,
#: and conditioning on u as well closes it again.
_THROUGH_A_CONFOUNDER = (("x", "y"), ("x", "w"), ("u", "w"), ("u", "y"))


def test_a_restriction_closes_the_path_a_conditioned_collider_opened():
    opened = _program(_THROUGH_A_CONFOUNDER, given=["w"])
    assert _caveats(_answer(opened)) == [(COLLIDER, "w")]
    closed = _program(_THROUGH_A_CONFOUNDER, given=["w"], observed=["u"])
    result = _answer(closed)
    assert _caveats(result) == []
    the_door_for(result)(closed, result)


def test_a_condition_closes_the_path_a_restriction_opened():
    opened = _program(_THROUGH_A_CONFOUNDER, observed=["w"])
    assert _caveats(_answer(opened)) == [(SELECTION, "w")]
    closed = _program(_THROUGH_A_CONFOUNDER, given=["u"], observed=["w"])
    result = _answer(closed)
    assert _caveats(result) == []
    the_door_for(result)(closed, result)


def test_recovery_keeps_to_directed_common_effects():
    latent = _answer(_program(COLLIDERS["latent arms"][0],
                              bidirected=COLLIDERS["latent arms"][1], observed=["w"]))
    assert "selection_recovery" not in (latent.get("extensions") or {})
    canonical = _answer(_program(COLLIDERS["the canonical collider"][0], observed=["w"]))
    assert "selection_recovery" in (canonical.get("extensions") or {})
