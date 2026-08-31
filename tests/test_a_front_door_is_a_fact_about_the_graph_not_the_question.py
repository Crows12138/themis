"""The picture's label, when the question conditions on something.

The graph-level annotation is the one sentence a reader gets about WHERE
the number came from — "through the mediator M, holding C". On a
front-door graph it said ``c_factor``, the engine's name, as soon as the
question conditioned on anything:

    X -> M -> Y,  X <-> Y,  C -> Y      asking P(Y | do(X), C = c)

The reason recorded for withholding it was that a conditional estimand is
not what the front-door criterion identifies. That is true and it is about
the ESTIMAND; the label is about the GRAPH, and the front door was still
there. The back-door label was never withheld the same way — its search
takes the conditioning and answers for it — so the asymmetry was about the
two SIGNATURES rather than about the two structures.

The reason had been written twice, once at the producer and once in the
verifier's search for a structure a ``c_factor`` claim says is not there.
While both copies agreed, their agreement hid the fact that only one of
them was about the right thing.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

import themis
from themis.runtime import scheduler
from themis.verifier.errors import VerificationError


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _v(p, **kw):
    return {"kind": "variable", "predicate": p, **kw}


def _c(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


# --------------------------------------------------------------- data
def _conditional_front_door(n=6000, seed=3):
    """X -> M -> Y, X <-> Y, C -> Y; the question conditions on C."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    c = rng.random(n) < 0.5
    x = rng.random(n) < 1 / (1 + np.exp(-0.9 * u))
    m = rng.random(n) < 1 / (1 + np.exp(-(1.3 * x.astype(float) - 0.6)))
    y = rng.random(n) < 1 / (1 + np.exp(
        -(1.4 * m.astype(float) + 1.5 * u + 0.5 * c.astype(float) - 1.0)))
    return pd.DataFrame({"c": c, "x": x, "m": m, "y": y})


def _conditional_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _v("c", domain=[True, False]), _v("x", domain=[True, False]),
            _v("m", domain=[True, False]), _v("y", domain=[True, False]),
            _c("x", "m"), _c("m", "y"), _c("c", "y"),
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [{"atom": _atom("c"), "value": True}],
            }},
        ],
    }


def _front_door_needing_a_covariate(n=6000, seed=4):
    """C -> X, C -> M, X -> M -> Y, X <-> Y; nothing conditioned."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    c = rng.random(n) < 0.5
    x = rng.random(n) < 1 / (1 + np.exp(-(0.9 * u + 0.8 * c.astype(float))))
    m = rng.random(n) < 1 / (1 + np.exp(
        -(1.3 * x.astype(float) + 0.7 * c.astype(float) - 0.9)))
    y = rng.random(n) < 1 / (1 + np.exp(
        -(1.4 * m.astype(float) + 1.5 * u - 0.9)))
    return pd.DataFrame({"c": c, "x": x, "m": m, "y": y})


def _covariate_program():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            _v("c", domain=[True, False]), _v("x", domain=[True, False]),
            _v("m", domain=[True, False]), _v("y", domain=[True, False]),
            _c("c", "x"), _c("c", "m"), _c("x", "m"), _c("m", "y"),
            {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("x"), "value": True},
                "target": {"atom": _atom("y"), "value": True},
                "given": [],
            }},
        ],
    }


def _run(program, df):
    return themis.estimate(program, df, ci_bootstrap=0,
                           random_state=1)["results"][0]


def _label(result):
    return (result.get("extensions") or {})["identification"]


# ------------------------------------------------------------- the label
def test_a_conditional_question_still_gets_the_structure_named():
    label = _label(_run(_conditional_program(), _conditional_front_door()))
    assert label["pattern"] == "front_door"
    assert label["mediator_set"] == ["m(me)"]


def test_what_the_question_holds_is_a_different_key_from_what_the_criterion_holds():
    """The distinction the withholding was protecting, kept as two keys.

    A conditioned node and an adjustment covariate read alike and mean
    opposite things on a collider, so putting the question's conditioning
    into ``covariate_set`` would be a worse error than the one being
    fixed."""
    conditional = _label(_run(_conditional_program(),
                              _conditional_front_door()))
    assert conditional["conditioned_on"] == ["c(me)"]
    assert "covariate_set" not in conditional

    held = _label(_run(_covariate_program(), _front_door_needing_a_covariate()))
    assert held["covariate_set"] == ["c(me)"]
    assert "conditioned_on" not in held


def test_the_number_is_unchanged_by_what_the_picture_is_called():
    """The label is not the identification verdict. Both shapes answer,
    through the engine that settles identification either way."""
    a = _run(_conditional_program(), _conditional_front_door())
    b = _run(_covariate_program(), _front_door_needing_a_covariate())
    assert a["status"] == "numerically_solved"
    assert b["status"] == "numerically_solved"
    assert a["numeric_estimate"]["point"] is not None
    assert b["numeric_estimate"]["point"] is not None


# ------------------------------------------------------------ the audit
def test_the_kernel_accepts_the_named_structure():
    program = _conditional_program()
    result = _run(program, _conditional_front_door())
    themis.verify(program, result)


def test_the_audit_refuses_a_modest_label_on_a_conditional_question():
    """The counterexample the verifier's own copy of the reason used to
    let through: claim the general solution where a front door is there
    to be named, with the question conditioning.

    Before this change the search returned early on ``given`` and this
    forgery was accepted."""
    program = _conditional_program()
    result = _run(program, _conditional_front_door())
    forged = json.loads(json.dumps(result))
    forged["extensions"]["identification"] = {"pattern": "c_factor",
                                              "conditioned_on": ["c(me)"]}
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, forged)


def test_the_audit_still_refuses_a_front_door_that_is_not_there():
    """The widening is not a loosening: naming a mediator set that fails
    the criterion is refused exactly as before."""
    program = _conditional_program()
    result = _run(program, _conditional_front_door())
    forged = json.loads(json.dumps(result))
    forged["extensions"]["identification"]["mediator_set"] = ["c(me)"]
    with pytest.raises((VerificationError, ValueError)):
        themis.verify(program, forged)


# ----------------------------------------------------------- the source
def test_the_recognizer_asks_the_graph_and_not_the_query():
    """Read on the function rather than through a run, so a future edit
    that reintroduces the suppression is named here rather than in
    whichever end-to-end case happens to notice."""
    import inspect

    src = inspect.getsource(scheduler._recognize_identification_pattern)
    front = src.split("generalized_front_door_sets")[0]
    assert "() if given else" not in front, (
        "the front-door search is being withheld on the QUESTION's "
        "conditioning again; the label is about the graph"
    )
