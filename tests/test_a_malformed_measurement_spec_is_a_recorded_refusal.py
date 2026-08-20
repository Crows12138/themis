"""What a caller files under a variable's name has to be a spec — or be told so.

Four routes take a measurement spec straight from the caller: the two
misclassification corrections, their combined form, and the outcome-error
precision assessment. Each is reached through a route guard in
``themis.routing`` that tests one :class:`EffectFacts` attribute for ``is not
None``, and nothing anywhere tested that the value behind that name is a
mapping of settings. ``EffectFacts`` annotates the attributes ``dict | None``
on the strength of a dict the caller handed in and no one read.

So ``measurement_error={"y": 0}`` — a caller who names a variable and then does
not describe it — reached a handler whose signature says ``spec: dict`` and
whose body says ``spec.get(...)``, and ``themis.estimate`` raised
``AttributeError: 'int' object has no attribute 'get'`` at its own caller. That
is the one thing this package exists not to do: an answer withheld has to leave
by the estimator-failure door, where it carries a species, a reason a reader can
act on, and a validated envelope. An exception is a run with no verdict at all —
a caller with an ``except`` around it cannot tell a malformed request from a
crashed engine, and a caller without one loses every other query in the batch.

The half of the hole that was falsy — ``0``, ``""``, ``[]`` — used to be
swallowed by an ``(spec or {})`` and reported as "you gave no error variance",
which is a wrong sentence rather than a crash: the caller gave no error variance
because they gave no spec. The truthy half — ``3.0``, ``"abc"`` — crashed on
every version. Both are refused here by name, so neither can come back as the
other's disguise.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.syntactic_validator import validate_result


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


def _program():
    """z → x → y with z → y: back-door identified, so a refusal recorded here
    is about the spec and never about a missing design."""
    return {"version": "0.1",
            "domain": {"objects": [{"kind": "object", "name": "u"}]},
            "statements": [
                {"kind": "variable", "predicate": "x"},
                {"kind": "variable", "predicate": "y"},
                {"kind": "variable", "predicate": "z"},
                {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("x")},
                {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
                {"kind": "query", "id": "q", "query": {
                    "kind": "effect",
                    "intervention": {"atom": _atom("x"), "value": True},
                    "target": {"atom": _atom("y"), "value": True}, "given": []}},
            ]}


def _continuous(n=1500, seed=3):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 1, n)
    y = 0.3 + 0.8 * x + z + rng.normal(0, 1, n)
    return pd.DataFrame({"x": x, "z": z, "y": y})


def _binary(n=1500, seed=3):
    df = _continuous(n=n, seed=seed)
    return df.assign(x=(df.x > 0).astype(float), y=(df.y > 0).astype(float))


# Every shape a caller can put where a spec belongs. The falsy ones are the
# regression — they had a bystander ``or {}`` in front of them and lost it —
# and the truthy ones never had anything, so a fix that only restores the
# fallback passes half this list and fails the other half.
NOT_A_SPEC = [0, 0.0, False, "", [], 1, 3.0, True, "abc", [1], (2,)]


@pytest.mark.parametrize("bad", NOT_A_SPEC)
def test_a_non_mapping_outcome_error_spec_is_recorded_not_raised(bad):
    """The reported regression, at the surface a caller sees.

    Guards the whole path, not the one ``.get`` that happened to be first:
    the assertion is that ``themis.estimate`` returns, that what it returns
    carries a refusal naming this row's estimator, and that no number rode out
    beside it.
    """
    r = themis.estimate(
        _program(), _continuous(), ci_bootstrap=0,
        measurement_error={"y": bad},
    )["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None, "a malformed spec produced neither number nor refusal"
    assert fail["estimator"] == "outcome_measurement_error"
    assert fail["failure_type"] == "invalid_input"
    assert r.get("numeric_estimate") is None
    assert r.get("outcome_error") is None


@pytest.mark.parametrize("channel,estimator", [
    ({"y": None}, "measurement_error_correction"),
    ({"x": None}, "exposure_measurement_error_correction"),
    ({"x": None, "y": None}, "combined_measurement_error_correction"),
])
@pytest.mark.parametrize("bad", [0, 3.0, "abc", []])
def test_a_non_mapping_misclassification_spec_is_recorded_not_raised(
    channel, estimator, bad,
):
    """The same contract on the three confusion-matrix rows.

    They share the guard, so they share the hole; naming them separately is
    what keeps a fix that reaches only the row the bug was reported on from
    looking finished. The estimator on the block is each row's own — a refusal
    filed under a neighbour's name sends the reader to the wrong input.
    """
    spec = {name: bad for name in channel}
    r = themis.estimate(
        _program(), _binary(), ci_bootstrap=0, misclassification=spec,
    )["results"][0]
    fail = r.get("estimator_failure")
    assert fail is not None
    assert fail["estimator"] == estimator
    assert fail["failure_type"] == "invalid_input"
    assert r.get("numeric_estimate") is None


def test_the_refusal_says_what_a_spec_is_and_quotes_what_it_got():
    """A refusal a caller cannot act on is an exception with better manners.

    ``invalid_input`` is the catch-all species, so the sentence is the whole
    of what the reader gets: it has to say that a spec is a mapping of named
    settings, and show the thing that was filed instead.
    """
    r = themis.estimate(
        _program(), _continuous(), ci_bootstrap=0,
        measurement_error={"y": "0.5"},
    )["results"][0]
    reason = r["estimator_failure"]["reason"]
    assert "mapping" in reason
    assert "'0.5'" in reason


def test_a_refused_spec_still_leaves_an_envelope_that_validates():
    """Every public verify entry validates the envelope before auditing it, so
    a refusal that fails its own schema cannot be checked at all — which would
    make this whole path unauditable exactly when something went wrong."""
    r = themis.estimate(
        _program(), _continuous(), ci_bootstrap=0,
        measurement_error={"y": 0},
    )["results"][0]
    validate_result(r)


def test_an_omitted_error_variance_is_quoted_as_absent_not_as_a_number():
    """``{}`` IS a spec — an empty one — and the refusal it earns is the
    estimator's, about σ²_v rather than about the spec's shape.

    What it must not do is name a value the caller never wrote. Handing the
    estimator a ``nan`` for the missing key turns "you did not declare one"
    into "the number you declared is nan", which reads as the caller's own
    input coming back at them and sends them looking for a nan they never
    typed. The two mistakes stay two sentences.
    """
    r = themis.estimate(
        _program(), _continuous(), ci_bootstrap=0,
        measurement_error={"y": {}},
    )["results"][0]
    fail = r["estimator_failure"]
    assert fail["failure_type"] == "non_positive_error_variance"
    assert "got None." in fail["reason"]
    assert "nan" not in fail["reason"]


def test_a_well_formed_spec_still_gets_its_assessment():
    """The positive control for the guard above: it rejects things that are
    not specs, and a mapping is not one of them. A shape check that also
    turned away real specs would trade a crash for a silence."""
    r = themis.estimate(
        _program(), _continuous(), ci_bootstrap=0, random_state=1,
        measurement_error={"y": {"error_variance": 0.5}},
    )["results"][0]
    assert r.get("estimator_failure") is None
    assert r["outcome_error"]["error_variance"] == pytest.approx(0.5)
    assert r["numeric_estimate"]["point"] == pytest.approx(0.8, abs=0.15)
