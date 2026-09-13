"""A restriction on a collider is read on the graph the answer was reached on.

Two caveats tell a reader that an effect was estimated inside a restricted
sample and that the restriction is on a collider, so the estimate carries
selection bias: ``collider_conditioning_opens_backdoor`` when the question
conditions on it, ``selection_on_collider_opens_path`` when an observation
restricts the data. Both were decided on the predicates, where ``x`` a step
back and ``x`` now are one node, while the effect was asked of ground atoms.

Measured on programs unrolled in time, both caveats were wrong both ways: a
restriction on an atom no ground path reached from the intervention was
reported, and a restriction on ``x`` now that was the collider was passed
over as the intervention itself. On that second answer selection recovery,
which already asked its question of ground atoms, named the restriction a
selection node beside a caveat that said nothing. Read on the ground graph,
every corpus answer names what it named before.
"""
from __future__ import annotations

import pytest

import themis

COLLIDER = "collider_conditioning_opens_backdoor"
SELECTION = "selection_on_collider_opens_path"
_ME = [{"type": "const", "name": "me"}]


def _at(predicate, t=None):
    atom = {"predicate": predicate, "args": _ME}
    if t is not None:
        atom["time_index"] = {"kind": "relative", "value": t}
    return atom


def _asked(edges, x, y, w, restricted_by):
    """The effect of ``x`` on ``y`` over cause edges, the sample restricted
    to ``w`` by the question's ``given`` or by an observation."""
    names = sorted({a["predicate"] for edge in edges for a in edge})
    statements = [{"kind": "variable", "predicate": p, "domain": [True, False]}
                  for p in names]
    statements += [{"kind": "cause", "from": a, "to": b} for a, b in edges]
    given = []
    if restricted_by == "given":
        given = [{"atom": w, "value": True}]
    else:
        statements.append({"kind": "observation", "atom": w, "value": True})
    statements.append({"kind": "query", "id": "q", "query": {
        "kind": "effect", "given": given,
        "intervention": {"atom": x, "value": True},
        "target": {"atom": y, "value": True}}})
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "me"}]},
            "statements": statements}


def _answer(program):
    return next(r for r in themis.run(program)["results"]
                if r.get("query_id") == "q")


def _named(result, kind):
    return {str((s.get("said") or {}).get("collider"))
            for gap in (result.get("data_gap_report") or {}).get("gaps") or ()
            if gap.get("kind") == kind
            for s in gap.get("describes") or ()
            if (s.get("said") or {}).get("collider")}


_BOTH = [pytest.param("given", COLLIDER, id="conditioned-on"),
         pytest.param("observation", SELECTION, id="observed")]

#: Over predicates ``x -> w <- y``. On the ground graph ``w`` a step back is
#: moved by ``y`` a step back alone, and no path joins it to ``x``.
_NO_GROUND_PATH = ((_at("x", -1), _at("y", 0)), (_at("x", -1), _at("w", 0)),
                   (_at("y", -1), _at("w", -1)))

#: ``x`` now is moved by ``x`` a step back and by ``y`` now: a common effect
#: of the intervention and the target, under the intervention's predicate.
_UNDER_THE_INTERVENTION_S_NAME = ((_at("x", -1), _at("y", 0)),
                                  (_at("x", -1), _at("x", 0)),
                                  (_at("y", 0), _at("x", 0)))


@pytest.mark.parametrize(("restricted_by", "kind"), _BOTH)
def test_a_restriction_no_ground_path_reaches_is_not_on_a_collider(
        restricted_by, kind):
    result = _answer(_asked(_NO_GROUND_PATH, _at("x", -1), _at("y", 0),
                            _at("w", -1), restricted_by))
    assert _named(result, kind) == set()


@pytest.mark.parametrize(("restricted_by", "kind"), _BOTH)
def test_a_collider_under_the_intervention_s_own_predicate_is_one(
        restricted_by, kind):
    result = _answer(_asked(_UNDER_THE_INTERVENTION_S_NAME, _at("x", -1),
                            _at("y", 0), _at("x", 0), restricted_by))
    assert _named(result, kind) == {"x"}


def test_the_caveat_and_the_recovery_verdict_say_the_same_of_one_answer():
    """Recovery asked of ground atoms and the caveat of predicates, and on
    this answer the block named a selection node the caveat did not."""
    result = _answer(_asked(_UNDER_THE_INTERVENTION_S_NAME, _at("x", -1),
                            _at("y", 0), _at("x", 0), "observation"))
    recovery = (result.get("extensions") or {}).get("selection_recovery")
    assert recovery is not None
    assert recovery["selection_nodes"] == ["x"]
    assert _named(result, SELECTION) == {"x"}


@pytest.mark.parametrize(("restricted_by", "kind"), _BOTH)
def test_an_untimed_collider_is_read_as_it_was(restricted_by, kind):
    edges = ((_at("x"), _at("y")), (_at("x"), _at("w")), (_at("y"), _at("w")))
    result = _answer(_asked(edges, _at("x"), _at("y"), _at("w"), restricted_by))
    assert _named(result, kind) == {"w"}
