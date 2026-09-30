"""The tier of a data answer is what its bounds rule out.

#810. Two answers the data route produces are bounds on a probability: one
cell of the counterfactual joint distribution, and the three probabilities
of causation. The report's tier read both by their shape — a bounds block
meant "interval", a pinned PN meant "point" — and wherever identification
had failed it was not read at all: the tier the identification pass wrote
before any data arrived stood. The identification pass has read its
intervals for what they exclude since #808; these were not read that way.

A census of small random samples over three graphs found the words wrong
four ways. 37 of 285 counterfactual cells came out as [0, 1] and were called
an interval. Four causation answers pinned PN and PNS beside a PS the data
left undefined, and were called a point. On the instrument route, where
identification fails and the response polytope pins each quantity on its
own, three pinned cells kept the stale "no answer", and so did seven
causation answers pinning one, two or all three — which the verifier,
reading the causation block more closely than the producer did, refused.

Both sides now apply one rule, each in its own code: every quantity the
question asks for pinned, and nothing saying the estimand's point is out of
reach, is a point; bounds that rule some of [0, 1] out — a pinned one
included, because a pinned probability is bounds with nothing between them —
are an interval; bounds that rule none of it out are no answer. Rerun on the
same census — 1200 runs, 1045 of them answered from the data — every answer
gets the rule's word and the verifier accepts every one.
"""
from __future__ import annotations

import copy
import warnings

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _retier_to_what_came_out
from themis.types import AnswerTier
from themis.verifier.data_gap_rules import _the_tier_this_envelope_supports
from themis.verifier.errors import VerificationError


def _atom(name):
    return {"predicate": name, "args": []}


def _var(name):
    return {"kind": "variable", "predicate": name, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


_EXOGENOUS = (_var("x"), _var("y"), _cause("x", "y"))
_CONFOUNDED = (_var("x"), _var("y"), _var("z"),
               _cause("z", "x"), _cause("z", "y"), _cause("x", "y"))
# An instrument and a bow arc: no adjustment set exists, so identification
# fails and the three quantities are bounded over the response polytope.
_INSTRUMENT = (_var("z"), _var("x"), _var("y"),
               _cause("z", "x"), _cause("x", "y"),
               {"kind": "bidirected", "left": _atom("x"), "right": _atom("y")})


def _cell(*, factual_y, target_y, monotonicity=None):
    """P(Y_{x=False} = target_y | X=True, Y=factual_y)."""
    query = {"kind": "counterfactual",
             "observed": {"atom": _atom("x"), "value": True},
             "counterfactual_intervention": {"atom": _atom("x"),
                                             "value": False},
             "counterfactual_target": {"atom": _atom("y"), "value": target_y},
             "factual_target_known": factual_y}
    if monotonicity is not None:
        query["assumptions"] = {"monotonicity": monotonicity}
    return query


def _causation(monotonic=False):
    return {"kind": "causation", "cause": _atom("x"), "effect": _atom("y"),
            "monotonic": monotonic}


def _program(graph, query):
    return {"version": "0.1", "domain": {"objects": []},
            "statements": [*graph, {"kind": "query", "id": "q",
                                    "query": query}]}


def _rows(counts, columns):
    return pd.DataFrame([dict(zip(columns, values))
                         for values, n in counts.items() for _ in range(n)])


# P(y | x) = P(y | x') = 1/2 with x exogenous.
_HALVES = _rows({(True, True): 10, (True, False): 10,
                 (False, True): 10, (False, False): 10}, ("x", "y"))
# Everybody has the outcome, so nobody is in (X=False, Y=False): PS asks
# about a group the data hold none of.
_EVERYBODY = _rows({(True, True): 20, (False, True): 20}, ("x", "y"))
# The instrument decides the treatment and the treatment the outcome.
_COMPLIANT = _rows({(True, True, True): 20, (False, False, False): 20},
                   ("z", "x", "y"))


def _answer(graph, query, frame):
    program = _program(graph, query)
    (result,) = themis.estimate(copy.deepcopy(program), frame,
                                ci_bootstrap=0)["results"]
    return program, result


def _refused_as(program, result, tier, match):
    forged = copy.deepcopy(result)
    forged["data_gap_report"]["answer_tier"] = tier
    with pytest.raises(VerificationError, match=match):
        themis.verify(copy.deepcopy(program), forged)


# --- the four ways, each on a table small enough to read -------------------


def test_a_cell_bounded_to_the_whole_line_is_no_answer():
    program, result = _answer(_EXOGENOUS,
                              _cell(factual_y=False, target_y=True), _HALVES)
    cell = result["numeric_estimate"]["counterfactual_cell"]
    assert (cell["lower"], cell["upper"], cell["point"]) == (0.0, 1.0, None)
    assert result["data_gap_report"]["answer_tier"] == "none"
    themis.verify(copy.deepcopy(program), result)
    _refused_as(program, result, "interval", "carries is 'none'")


def test_one_undefined_probability_keeps_the_other_two_from_being_three_points():
    program, result = _answer(_EXOGENOUS, _causation(monotonic=True),
                              _EVERYBODY)
    causation = result["numeric_estimate"]["probabilities_of_causation"]
    assert causation["pn"]["point"] is not None
    assert causation["pns"]["point"] is not None
    assert causation["ps"]["point"] is None
    assert (causation["ps"]["lower"], causation["ps"]["upper"]) == (0.0, 1.0)
    assert result["data_gap_report"]["answer_tier"] == "interval"
    # The headline is the three-point answer's, and this is not that one.
    assert "point" not in result["numeric_estimate"]
    themis.verify(copy.deepcopy(program), result)
    _refused_as(program, result, "point", "promises a reader a point")


def test_three_pinned_where_identification_failed_are_an_interval():
    program, result = _answer(_INSTRUMENT, _causation(), _COMPLIANT)
    causation = result["numeric_estimate"]["probabilities_of_causation"]
    assert all(causation[name]["point"] == 1.0 for name in ("pn", "ps", "pns"))
    assert causation["interventional_risk_provenance"] == \
        "instrument_response_polytope"
    kinds = {gap["kind"] for gap in result["data_gap_report"]["gaps"]}
    assert "unidentifiable_no_admissible_set" in kinds
    assert result["data_gap_report"]["answer_tier"] == "interval"
    themis.verify(copy.deepcopy(program), result)
    _refused_as(program, result, "point", "promises a reader a point")
    _refused_as(program, result, "none", "no answer is available")


def test_a_cell_pinned_where_identification_failed_is_an_interval():
    program, result = _answer(_INSTRUMENT,
                              _cell(factual_y=True, target_y=False),
                              _COMPLIANT)
    cell = result["numeric_estimate"]["counterfactual_cell"]
    assert cell["point"] == 1.0
    assert result["data_gap_report"]["answer_tier"] == "interval"
    themis.verify(copy.deepcopy(program), result)
    _refused_as(program, result, "none", "no answer is available")


def test_one_quantity_ruling_something_out_is_enough():
    """PN and PS span the line and PNS does not: the question asks for all
    three, and each is an answer to part of it."""
    program, result = _answer(_EXOGENOUS, _causation(), _HALVES)
    causation = result["numeric_estimate"]["probabilities_of_causation"]
    assert (causation["pn"]["lower"], causation["pn"]["upper"]) == (0.0, 1.0)
    assert (causation["ps"]["lower"], causation["ps"]["upper"]) == (0.0, 1.0)
    assert causation["pns"]["upper"] == pytest.approx(0.5)
    assert result["data_gap_report"]["answer_tier"] == "interval"
    themis.verify(copy.deepcopy(program), result)


# --- the two readings, block by block --------------------------------------

_LINE = {"lower": 0.0, "upper": 1.0, "point": None}
_NARROW = {"lower": 0.2, "upper": 0.6, "point": None}
_PINNED = {"lower": 0.4, "upper": 0.4, "point": 0.4}
_BLOCKED = [{"kind": "unidentifiable_no_admissible_set"}]


def _three(pn, ps, pns):
    return {"method": "causation_plugin",
            "probabilities_of_causation": {"pn": pn, "ps": ps, "pns": pns}}


def _one(cell):
    estimate = {"method": "counterfactual_cell_plugin",
                "counterfactual_cell": cell}
    if cell["point"] is not None:
        estimate["point"] = cell["point"]
    return estimate


_CASES = {
    "three pinned": (_three(_PINNED, _PINNED, _PINNED), [], "point"),
    "three pinned, blocked": (_three(_PINNED, _PINNED, _PINNED), _BLOCKED,
                              "interval"),
    "pn pinned beside two lines": (_three(_PINNED, _LINE, _LINE), [],
                                   "interval"),
    "pn pinned beside two lines, blocked": (_three(_PINNED, _LINE, _LINE),
                                            _BLOCKED, "interval"),
    "one narrow": (_three(_LINE, _LINE, _NARROW), [], "interval"),
    "three lines": (_three(_LINE, _LINE, _LINE), [], "none"),
    "three lines, blocked": (_three(_LINE, _LINE, _LINE), _BLOCKED, "none"),
    "cell pinned": (_one(_PINNED), [], "point"),
    "cell pinned, blocked": (_one(_PINNED), _BLOCKED, "interval"),
    "cell narrow": (_one(_NARROW), [], "interval"),
    "cell line": (_one(_LINE), [], "none"),
    "cell line, blocked": (_one(_LINE), _BLOCKED, "none"),
}


@pytest.mark.parametrize("name", sorted(_CASES))
def test_producer_and_verifier_read_the_same_block_the_same_way(name):
    """Every finaliser's word is overridden by the shape here, so the road
    the producer is called from does not decide it; both are asked."""
    estimate, gaps, tier = _CASES[name]
    for came_out in (AnswerTier.POINT, AnswerTier.INTERVAL):
        result = {"status": "numerically_solved",
                  "numeric_estimate": copy.deepcopy(estimate),
                  "data_gap_report": {"gaps": copy.deepcopy(gaps),
                                      "answer_tier": None}}
        _retier_to_what_came_out(result, came_out=came_out)
        assert result["data_gap_report"]["answer_tier"] == tier, came_out
        assert _the_tier_this_envelope_supports(result, None) == tier


# --- and on random samples, the census as a regression ---------------------


def _frame(rng, graph, n):
    """Small samples from a latent-variable model, some of whose draws make
    the instrument irrelevant or the outcome a copy of the treatment — the
    corners where bounds collapse or span the line."""
    w = rng.random(n) < rng.uniform(0.1, 0.9)
    z = rng.random(n) < rng.uniform(0.1, 0.9)
    u = rng.random(n)
    if rng.random() < 0.25:
        y0, y1 = np.zeros(n, bool), np.ones(n, bool)
    else:
        a0, a1 = rng.uniform(0, 1, 2), rng.uniform(0, 1, 2)
        driver = w if graph == "instrument" else z
        y0 = u < np.where(driver, a0[0], a0[1])
        y1 = u < np.where(driver, a1[0], a1[1])
    if graph == "instrument":
        strength = 0.0 if rng.random() < 0.3 else rng.uniform(0, 0.6)
        p = (np.where(w, rng.uniform(0.1, 0.9), rng.uniform(0.1, 0.9))
             + np.where(z, strength, 0))
    elif graph == "confounded":
        p = np.where(z, rng.uniform(0.05, 0.95), rng.uniform(0.05, 0.95))
    else:
        p = np.full(n, rng.uniform(0.05, 0.95))
    x = rng.random(n) < np.clip(p, 0, 1)
    out = {"x": x, "y": np.where(x, y1, y0)}
    if graph != "exogenous":
        out["z"] = z
    return pd.DataFrame(out)


def _rule(result, kind):
    """The rule, written from the envelope and nothing else."""
    estimate = result["numeric_estimate"]
    blocked = any(gap.get("kind") in {"unidentifiable_no_admissible_set",
                                      "transport_sources_disagree"}
                  for gap in result["data_gap_report"]["gaps"])
    quantities = (
        [estimate["probabilities_of_causation"][n] for n in ("pn", "ps", "pns")]
        if kind == "causation" else [estimate["counterfactual_cell"]])
    if all(q["point"] is not None for q in quantities) and not blocked:
        return "point"
    if any(q["point"] is not None or not (q["lower"] <= 0 and q["upper"] >= 1)
           for q in quantities):
        return "interval"
    return "none"


_GRAPHS = {"exogenous": _EXOGENOUS, "confounded": _CONFOUNDED,
           "instrument": _INSTRUMENT}


@pytest.mark.parametrize("graph", sorted(_GRAPHS))
@pytest.mark.parametrize("kind", ["causation", "counterfactual"])
def test_every_sampled_answer_gets_the_rules_word_and_is_accepted(kind, graph):
    rng = np.random.default_rng(810)
    asked, answered = 0, 0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for monotonic in (False, True):
            for n in (20, 50, 200, 2000):
                for _ in range(5):
                    if kind == "causation":
                        query = _causation(monotonic)
                    else:
                        query = _cell(
                            factual_y=bool(rng.random() < 0.5),
                            target_y=bool(rng.random() < 0.5),
                            monotonicity="non_decreasing" if monotonic
                            else None)
                    program = _program(_GRAPHS[graph], query)
                    asked += 1
                    (result,) = themis.estimate(
                        copy.deepcopy(program), _frame(rng, graph, n),
                        ci_bootstrap=0)["results"]
                    # An estimator that refused leaves the structural
                    # answer, whose tier #808 is about.
                    if not isinstance(result.get("numeric_estimate"), dict):
                        continue
                    answered += 1
                    assert (result["data_gap_report"]["answer_tier"]
                            == _rule(result, kind))
                    themis.verify(copy.deepcopy(program), result)
    assert asked == 40
    assert answered >= 20, answered
