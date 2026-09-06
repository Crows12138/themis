"""The one door a reader gets a number through, and what it refuses.

``/api/estimate`` is where the demo stops saying what is missing and
answers, and ``/api/clarify`` is where a reader supplies framing. Neither
had a test. Both are reachable with no API key, so "unverified" was a fact
about nobody having looked rather than about a key.

Testing them wants data, and this repository has none — not one CSV — for
a reason worth stating rather than working around: its first claim is that
it does not invent numbers, and a table of numbers checked in with no
account of where they came from is the thing that claim is against. Data
SAMPLED FROM A STATED MECHANISM is not that. The mechanism is below, the
effect it implies is derived below, and both are checkable by anyone
reading this file — which turns the test into an oracle rather than an
assertion that some number came back.

The mechanism, with every constant written out::

    Z ~ Bernoulli(0.5)                      a confounder
    X ~ Bernoulli(0.2 + 0.6 Z)              treatment, pushed by Z
    Y ~ Bernoulli(0.1 + 0.3 X + 0.4 Z)      outcome, pushed by both

Y is linear in X and Z, so standardising over Z gives

    P(Y | do(X=1)) - P(Y | do(X=0)) = 0.3   exactly, for any P(Z).

And the association an estimator that did NOT adjust would report::

    P(Z=1 | X=1) = 0.8   P(Z=1 | X=0) = 0.2
    P(Y=1 | X=1) = 0.4 + 0.4(0.8) = 0.72
    P(Y=1 | X=0) = 0.1 + 0.4(0.2) = 0.18   difference 0.54

0.54 against a true 0.3, which is what makes the tolerance below a real
question: it is far too tight to admit the confounded answer, so this test
fails if the adjustment stops happening rather than only if the endpoint
stops responding.
"""
from __future__ import annotations

import numpy as np
import pytest
from fastapi.testclient import TestClient

from themis.web.app import app

client = TestClient(app)

_ME = [{"type": "const", "name": "me"}]

#: What the mechanism above implies, and what an unadjusted reading gives.
TRUE_EFFECT = 0.30
CONFOUNDED_READING = 0.54

#: Measured rather than picked: over twenty seeds at this size the estimate
#: has sd 0.011 and never missed by more than 0.025, so this is about four
#: standard deviations and half the distance to the confounded reading. Both
#: halves matter — loose enough that a resampling change does not flake it,
#: tight enough that it still separates an adjusted answer from a raw one.
TOLERANCE = 0.05
ROWS = 8000
SEED = 20260907


def _var(predicate: str) -> dict:
    return {"kind": "variable", "predicate": predicate,
            "domain": [True, False]}


def _cause(frm: str, to: str) -> dict:
    return {"kind": "cause",
            "from": {"predicate": frm, "args": _ME},
            "to": {"predicate": to, "args": _ME},
            "annotations": {"source": "user_declared"}}


PROGRAM = {
    "version": "0.1",
    "domain": {"objects": [{"kind": "object", "name": "me"}]},
    "statements": [
        _var("treatment"), _var("outcome"), _var("confounder"),
        _cause("treatment", "outcome"),
        _cause("confounder", "treatment"),
        _cause("confounder", "outcome"),
        {"kind": "query", "id": "q", "query": {
            "kind": "effect",
            "intervention": {"atom": {"predicate": "treatment",
                                      "args": _ME}, "value": True},
            "target": {"atom": {"predicate": "outcome", "args": _ME},
                       "value": True},
            "given": []}},
    ],
}


def _rows(seed: int = SEED, n: int = ROWS) -> list[dict]:
    """One sample from the mechanism in this module's docstring."""
    rng = np.random.default_rng(seed)
    z = rng.random(n) < 0.5
    x = rng.random(n) < (0.2 + 0.6 * z)
    y = rng.random(n) < (0.1 + 0.3 * x + 0.4 * z)
    return [{"treatment": bool(a), "outcome": bool(b), "confounder": bool(c)}
            for a, b, c in zip(x, y, z)]


def _estimate(rows: list[dict], program: dict | None = None):
    return client.post("/api/estimate",
                       json={"program": program or PROGRAM, "rows": rows})


def _point(response) -> float | None:
    body = response.json()
    results = body.get("results") if isinstance(body, dict) else None
    if not results:
        return None
    return (results[0].get("numeric_estimate") or {}).get("point")


# ---------------------------------------------- the number, against a truth


def test_the_door_returns_the_effect_the_mechanism_puts_there():
    response = _estimate(_rows())
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "numerically_solved", result["status"]
    point = (result.get("numeric_estimate") or {}).get("point")
    assert point is not None, result.get("numeric_estimate")
    assert abs(point - TRUE_EFFECT) < TOLERANCE, point


def test_the_sample_really_does_carry_the_confounding_it_claims_to():
    """So the test above is answering a question rather than a formality.

    Read straight off the rows, with no estimator involved: if this sample
    did not carry the bias, an estimator that ignored the confounder would
    also land on 0.3 and the assertion above would pass on nothing.
    """
    rows = _rows()
    treated = [r["outcome"] for r in rows if r["treatment"]]
    untreated = [r["outcome"] for r in rows if not r["treatment"]]
    crude = sum(treated) / len(treated) - sum(untreated) / len(untreated)
    assert abs(crude - CONFOUNDED_READING) < TOLERANCE, crude
    assert abs(crude - TRUE_EFFECT) > 4 * TOLERANCE, crude


# ------------------------------------------------------- what it refuses


def test_no_rows_is_refused_and_not_answered():
    response = _estimate([])
    assert response.status_code == 400, response.text
    assert response.json()["stage"] == "empty_data"


def test_a_column_the_estimate_needs_and_the_data_lacks_is_named():
    without = [{k: v for k, v in row.items() if k != "confounder"}
               for row in _rows(n=400)]
    response = _estimate(without)
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"] == "DataContractError"
    assert "confounder" in str(body.get("slots") or body.get("diagnostic"))


def test_a_value_the_declaration_never_listed_is_refused():
    labelled = [dict(row, treatment="sometimes") for row in _rows(n=400)]
    response = _estimate(labelled)
    assert response.status_code == 400, response.text
    assert _point(response) is None


def test_data_with_one_arm_answers_with_no_number_rather_than_a_bad_one():
    """The claim this whole system is for, at the door a reader uses.

    One arm supports no contrast, and what comes back is not an error and
    not a number: an answer that says what is missing. A build that started
    returning a figure here would be doing the one thing the product says
    it does not do.
    """
    one_armed = [dict(row, treatment=True) for row in _rows(n=400)]
    response = _estimate(one_armed)
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "needs_investigation", result["status"]
    assert not (result.get("numeric_estimate") or {}).get("point")


# --------------------------------------------------------- framing, not data


def test_answering_the_framing_questions_does_not_conjure_data():
    """``/api/clarify`` fills in what a variable MEANS, which is not what a
    number needs. A reader who answered every framing question and was then
    shown an estimate would have been handed one built from nothing."""
    picks = [{"predicate": "treatment",
              "fields": {"population": "adults in the study cohort",
                         "timing": "over twelve weeks"}}]
    response = client.post("/api/clarify",
                           json={"program": PROGRAM, "picks": picks})
    assert response.status_code == 200, response.text
    result = response.json()["results"][0]
    assert result["status"] == "needs_investigation", result["status"]
    kinds = {gap.get("kind") for gap in
             ((result.get("data_gap_report") or {}).get("gaps") or [])}
    assert "missing_distribution" in kinds, sorted(kinds)
    assert not (result.get("numeric_estimate") or {}).get("point")


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_answer_does_not_depend_on_which_sample_it_saw(seed):
    """Three more draws from the same mechanism, because one seed passing
    is a fact about that seed."""
    point = _point(_estimate(_rows(seed=seed)))
    assert point is not None
    assert abs(point - TRUE_EFFECT) < TOLERANCE, (seed, point)
