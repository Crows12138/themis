"""Proximal inference had one bridge, and one bridge has no second opinion.

The outcome bridge ``h`` is assumed to lie in a span the caller declares. If
it does not, the answer is wrong and nothing in the machinery notices: more
data does not approach a function that is not in the span being searched.
The back-door road has had three estimators for this reason — the outcome
model, the propensity model, and the augmented combination that is right if
either is — and the proximal road had only the first.

Cui, Pu, Miao, Zhang & Tchetgen Tchetgen 2024 (JASA 119(546)) gives the
second bridge. ``q`` solves ``E[q(Z,a,X) | W, A=a, X] = 1/f(A=a|W,X)`` and is
the mirror of ``h`` in every respect: a function of the TREATMENT-side
proxies, tested at moments of the OUTCOME-side ones. From the two come three
answers, and Theorem 3.2 says the third is consistent under the union of the
two models rather than under either.

Two things this file measures that reasoning alone got wrong.

**The collapse.** With one span and one index shared by both bridges, the
three estimators are the same number — not approximately, to machine
precision, because the inverse-probability answer is then the outcome
regression written backwards. A "doubly robust" estimate assembled that way
insures nothing, so the door refuses the arrangement.

**The reachable half.** With the outcome design serving as ``h``'s span AND
``q``'s moments, narrowing it breaks both bridges at once and the "h wrong,
q right" direction cannot be reached at all. That is why each bridge carries
its own span and its own moments: an estimator robust in one direction only
is singly robust under a longer name.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.input.semantic_validator import Malformed, SemanticError
from themis.verifier import VerificationError

_STEP = "numeric_proximal_bridge_estimate"

#: The truth every sample below is built around.
BETA = 1.5


# --- the corpus ---------------------------------------------------------------

def _var(p, **kw):
    out = {"kind": "variable", "predicate": p}
    out.update(kw)
    return out


def _atom(p):
    return {"predicate": p, "args": []}


def _cause(a, b):
    return {"kind": "cause", "from": _atom(a), "to": _atom(b)}


def _terms(variable, dimension, basis="polynomial"):
    return [{"factors": [{"variable": _atom(variable), "basis": basis,
                          "dimension": dimension}]}]


def _channel(*, d_h, m_h, m_q=None, d_q=None, estimator=None,
             ridge=None, q_ridge=None, q_span=None, q_moment=None):
    """A bridge channel, with as much of the second bridge as is asked for.

    ``q_span`` / ``q_moment`` take whole designs where a test needs the
    treatment bridge to name something other than the usual proxy — which is
    what the door's own counterexamples are about.
    """
    outcome = {"span_terms": _terms("w", d_h), "moment_terms": _terms("z", m_h)}
    if ridge is not None:
        outcome["ridge"] = ridge
    out = {"kind": "bridge_channel", "outcome_bridge": outcome}
    if estimator is not None:
        out["estimator"] = estimator
    if m_q is not None or q_span is not None:
        treatment = {
            "span_terms": q_span if q_span is not None else _terms("z", m_q),
            "moment_terms": (q_moment if q_moment is not None
                             else _terms("w", d_q)),
        }
        if q_ridge is not None:
            treatment["ridge"] = q_ridge
        out["treatment_bridge"] = treatment
    return out


def _program(channel: dict) -> dict:
    """Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y, with U unobserved."""
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x", domain=[True, False]), _var("y", scale="continuous"),
            _var("u"), _var("z", scale="continuous"),
            _var("w", scale="continuous"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom("z")], "outcome_proxy": [_atom("w")],
                "channel": channel,
            }},
        ],
    }


def _sample(n: int = 12000, seed: int = 3, *, curved_outcome: float = 0.0,
            curved_assignment: float = 0.0) -> pd.DataFrame:
    """A latent-confounded SCM with two dials, one per bridge.

    ``U`` is standard normal and unobserved; ``Z`` and ``W`` are noisy linear
    readings of it. With both dials at zero the outcome bridge is
    ``h(w, x) = βx + (τ/γ)w`` exactly and the treatment bridge is reached by
    a low-order polynomial in ``z``, so a modest sieve contains both.

    ``curved_outcome`` bends the outcome's dependence on ``U`` — and bends it
    IN THE TREATED ARM ONLY. That half is not decoration. Confounding that
    enters both arms alike leaves the same misfit in ``h_1`` and ``h_0``,
    which CANCELS in the contrast: a design far too narrow to hold the truth
    still lands on it, and a test built that way would be measuring nothing.
    The ATE stays exactly ``β`` because ``E[u² − 1] = 0``.

    ``curved_assignment`` bends the propensity in ``U``, which is what makes
    the true ``q`` need columns a short sieve does not have.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    logit = 0.9 * u + curved_assignment * (u ** 2 - 1.0)
    x = rng.random(n) < 1 / (1 + np.exp(-logit))
    return pd.DataFrame({
        "x": x,
        "y": (BETA * x + 1.1 * u + curved_outcome * (u ** 2 - 1.0) * x
              + 0.3 * rng.standard_normal(n)),
        "z": 1.2 * u + 0.5 * rng.standard_normal(n),
        "w": 0.9 * u + 0.5 * rng.standard_normal(n),
    })


@pytest.fixture(scope="module")
def plain() -> pd.DataFrame:
    return _sample()


@pytest.fixture(scope="module")
def outcome_bridge_is_wrong() -> pd.DataFrame:
    return _sample(curved_outcome=1.4)


@pytest.fixture(scope="module")
def treatment_bridge_is_wrong() -> pd.DataFrame:
    return _sample(curved_assignment=1.6)


def _answer(channel: dict, frame: pd.DataFrame) -> dict:
    out = themis.estimate(_program(channel), frame, ci_bootstrap=0)["results"][0]
    assert out["status"] == "numerically_solved", out.get("estimator_failure")
    return out


def _point(channel: dict, frame: pd.DataFrame) -> float:
    return _answer(channel, frame)["numeric_estimate"]["point"]


def _refused(channel: dict) -> SemanticError:
    with pytest.raises(SemanticError) as raised:
        themis.run(_program(channel))
    return raised.value


def _step(result: dict) -> dict:
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step
    raise AssertionError(f"no {_STEP} step in this derivation")


def _recorded(result: dict) -> dict:
    return _step(result)["inputs"]["measurement_channel"]["items"]


# --- the two directions, which is the whole point -----------------------------

#: The designs used for both robustness measurements. Each bridge has its own
#: span and its own moments, which is what makes the two directions separable
#: at all: with the outcome design serving as h's span AND q's moments, there
#: is no configuration where h is wrong and q is right.
_ROBUST = dict(d_h=4, m_h=6, m_q=4, d_q=6)
_H_TOO_NARROW = dict(_ROBUST, d_h=2)
_Q_TOO_NARROW = dict(_ROBUST, m_q=2)


def test_the_outcome_regression_is_wrong_when_its_span_is(
        outcome_bridge_is_wrong):
    """The premise of the first direction, measured rather than assumed.

    The bridge needs curvature in ``w`` that a two-column span cannot hold,
    and the misfit does not cancel across the arms — so the answer this file
    is about rescuing really is wrong first.
    """
    narrow = _point(_channel(d_h=2, m_h=6), outcome_bridge_is_wrong)
    wide = _point(_channel(d_h=4, m_h=6), outcome_bridge_is_wrong)
    assert abs(narrow - BETA) > 0.25, narrow
    assert abs(wide - BETA) < 0.06, wide


def test_the_doubly_robust_answer_survives_a_wrong_outcome_span(
        outcome_bridge_is_wrong):
    """Direction one: ``h``'s span is too narrow and ``q``'s is not."""
    ipw = _point(_channel(**_H_TOO_NARROW, estimator="inverse_probability"),
                 outcome_bridge_is_wrong)
    dr = _point(_channel(**_H_TOO_NARROW, estimator="doubly_robust"),
                outcome_bridge_is_wrong)
    # The outcome regression on the SAME narrow span, from a program that
    # declares no second bridge — because a channel that declares one and
    # reads none is refused, and rightly.
    por = _point(_channel(d_h=2, m_h=6), outcome_bridge_is_wrong)

    assert abs(por - BETA) > 0.25, por
    assert abs(ipw - BETA) < 0.08, ipw
    assert abs(dr - BETA) < 0.08, dr


def test_the_doubly_robust_answer_survives_a_wrong_treatment_span(
        treatment_bridge_is_wrong):
    """Direction two, and the one a three-design channel could also reach.

    ``q``'s span is too narrow for a propensity curved in ``U``, so the
    inverse-probability answer is wrong; ``h``'s span holds, so the augmented
    one is not.
    """
    ipw = _point(_channel(**_Q_TOO_NARROW, estimator="inverse_probability"),
                 treatment_bridge_is_wrong)
    dr = _point(_channel(**_Q_TOO_NARROW, estimator="doubly_robust"),
                treatment_bridge_is_wrong)
    por = _point(_channel(d_h=4, m_h=6), treatment_bridge_is_wrong)

    assert abs(ipw - BETA) > 0.09, ipw
    assert abs(por - BETA) < 0.06, por
    assert abs(dr - BETA) < 0.06, dr


def test_the_doubly_robust_answer_is_wrong_where_both_spans_are(
        outcome_bridge_is_wrong):
    """The edge, stated as a measurement rather than as a caveat.

    Double robustness is not a safety net. With BOTH spans too narrow the
    augmented estimator is wrong too, and it does not announce it — which is
    the sentence the ledger line carries and the reason it is worth carrying.
    """
    both_narrow = _point(
        _channel(d_h=2, m_h=6, m_q=2, d_q=6, estimator="doubly_robust"),
        outcome_bridge_is_wrong)
    assert abs(both_narrow - BETA) > 0.25, both_narrow


# --- the collapse, which is why the designs may not mirror --------------------

def test_a_treatment_bridge_that_mirrors_the_outcome_bridge_is_refused():
    """The gate shown the case it exists for.

    ``q`` spanning what ``h`` takes moments along, and taking moments along
    ``h``'s span. Each bridge needs at least as many moments as unknowns, so
    that arrangement forces both systems square, and two square systems built
    from one pair of designs solve to the same answer.
    """
    error = _refused(_channel(d_h=3, m_h=3, m_q=3, d_q=3,
                              estimator="doubly_robust"))
    assert error.species is Malformed.BRIDGES_ARE_EACH_OTHERS_MIRROR


def test_widening_one_side_is_all_the_mirror_gate_asks(plain):
    """The other half of the counterexample: the refusal is about the mirror
    and not about the estimator, so the same request with one side widened is
    answered."""
    assert _point(_channel(d_h=3, m_h=5, m_q=3, d_q=5,
                           estimator="doubly_robust"), plain) == pytest.approx(
        BETA, abs=0.1)


def test_the_three_estimators_are_one_estimator_when_the_designs_mirror(plain):
    """WHY that gate exists, measured on the arithmetic it refuses.

    The door will not accept a mirrored pair, so the collapse is measured one
    layer down, on the estimator itself — and measured as a PROPERTY rather
    than against a tolerance, because a tolerance would not tell the two
    stories apart. Two different estimators that are both consistent land
    near each other and stay there. These do something else: the gap between
    them is O(λ), so dropping each bridge's penalty by three decades drops
    the gap by three decades too. That is one identity showing through a
    perturbation, which is what makes a doubly robust request under mirrored
    designs a request for nothing.
    """
    from themis.estimation.proximal_bridge import estimate_bridge
    from themis.types import (
        Atom, BasisFamily, BridgeChannel, BridgeFunction, ProximalEstimator,
        SieveFactor, SieveTerm,
    )

    def _design(name, dimension):
        return (SieveTerm(factors=(SieveFactor(
            variable=Atom(predicate=name, args=()),
            basis=BasisFamily.POLYNOMIAL, dimension=dimension),)),)

    frame = plain.assign(x=plain["x"].astype(int))
    for width in (2, 3, 4):
        span, moment = _design("w", width), _design("z", width)
        gaps = []
        for ridge in (1e-6, 1e-9, 1e-12):
            got = estimate_bridge(frame, xcol="x", ycol="y", spec=BridgeChannel(
                outcome_bridge=BridgeFunction(span, moment, ridge),
                # The mirror: q spans what h takes moments along, and takes
                # moments along h's span.
                treatment_bridge=BridgeFunction(moment, span, ridge),
                estimator=ProximalEstimator.DOUBLY_ROBUST,
            )).channel["estimates"]
            gaps.append(abs(got["outcome_regression"]
                            - got["inverse_probability"]))
        assert gaps[0] > 0, "a gap of exactly zero would measure nothing"
        for coarse, fine in zip(gaps, gaps[1:]):
            assert fine == pytest.approx(coarse * 1e-3, rel=0.05), gaps
        assert gaps[-1] < 1e-10, gaps


# --- the rest of the door ------------------------------------------------------

def test_an_estimator_that_needs_the_second_bridge_may_not_go_without_one():
    error = _refused(_channel(d_h=3, m_h=5, estimator="doubly_robust"))
    assert error.species is Malformed.TREATMENT_BRIDGE_NOT_DECLARED
    assert error.details["estimator"] == "doubly_robust"


def test_a_second_bridge_nothing_reads_is_refused_rather_than_ignored():
    """The other direction of the same gate.

    A caller who declares ``q`` and leaves the estimator at its default has
    written down insurance the arithmetic never collects on, and a report
    that listed the design would read as protection the answer does not have.
    """
    error = _refused(_channel(d_h=3, m_h=5, m_q=3, d_q=5))
    assert error.species is Malformed.TREATMENT_BRIDGE_UNUSED


def test_the_default_estimator_is_the_one_that_asks_for_least(plain):
    """Absent is ``outcome_regression`` — what a program written before there
    was a second bridge meant, and the estimator that assumes strictly less
    than the other two."""
    answered = _answer(_channel(d_h=3, m_h=5), plain)
    block = answered["extensions"]["proximal_estimand"]
    assert block["estimator"] == "outcome_regression"
    assert "treatment_bridge_span_terms" not in block


def test_the_moment_rule_is_one_rule_read_over_each_bridge():
    """``q`` under-determined is refused by the species that refuses ``h``
    under-determined, because it is the same fact about a solve — and the
    slots say which bridge, since the reader has two."""
    error = _refused(_channel(d_h=3, m_h=5, m_q=5, d_q=3,
                              estimator="doubly_robust"))
    assert error.species is Malformed.BRIDGE_UNDER_DETERMINED
    assert error.details["bridge"] == "treatment_bridge"
    assert error.details["unknowns"] == 5 and error.details["moments"] == 3


def test_the_treatment_bridge_spans_the_treatment_side_proxies():
    """``q`` is a function of ``(Z, C)``. A term of its span naming ``w``
    puts an outcome-side proxy where the equation's other side stands."""
    error = _refused(_channel(d_h=3, m_h=5, d_q=5, estimator="doubly_robust",
                              q_span=_terms("w", 3)))
    assert error.species is Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_TREATMENT_PROXY
    assert error.details["bridge"] == "treatment_bridge"
    assert error.details["variable"] == "w"


def test_the_treatment_bridge_takes_moments_of_the_outcome_side_proxies():
    """And the mirror of the mirror: its MOMENT side reads ``W``, so ``z``
    there is the stranger. The two species are keyed on the role a side may
    read rather than on the side's name, which is what lets one of them
    serve both bridges."""
    error = _refused(_channel(d_h=3, m_h=5, m_q=3, estimator="doubly_robust",
                              q_moment=_terms("z", 5)))
    assert error.species is Malformed.SIEVE_TERM_NAMES_A_STRANGER_TO_OUTCOME_PROXY
    assert error.details["bridge"] == "treatment_bridge"
    assert error.details["variable"] == "z"


# --- what the answer carries ---------------------------------------------------

def test_all_three_answers_travel_even_though_one_is_the_answer(plain):
    """They cost nothing once the moments are in hand, and a reader comparing
    them is comparing the two assumptions rather than two numbers."""
    channel = _recorded(_answer(
        _channel(d_h=3, m_h=5, m_q=3, d_q=5, estimator="doubly_robust"), plain))
    estimates = channel["estimates"]["items"]
    assert set(estimates) == {"outcome_regression", "inverse_probability",
                              "doubly_robust"}


def test_each_bridge_carries_its_own_penalty_and_its_own_author(plain):
    """Two ill-posed solves over two operators with two scales. A caller who
    named one λ and left the other alone is on the ledger as both."""
    answered = _answer(
        _channel(d_h=3, m_h=5, m_q=3, d_q=5, estimator="doubly_robust",
                 ridge=0.01), plain)
    ids = {e["id"]: e["provenance"]
           for e in answered["extensions"]["assumption_ledger"]["assumptions"]}
    assert ids["regularisation_lambda_chosen_by_the_caller"] == "caller_chose"
    assert ids[
        "treatment_bridge_regularisation_lambda_defaulted_by_the_estimator"
    ] == "default"


def test_the_ledger_asks_for_one_span_and_not_both_under_double_robustness(
        plain):
    """The theorem, as an absence.

    ``doubly_robust`` needs neither span to be right on its own, so neither
    individual line is on the ledger — a ledger listing both as required
    would be describing a stricter estimator than the one that ran.
    """
    ids = {e["id"] for e in _answer(
        _channel(d_h=3, m_h=5, m_q=3, d_q=5, estimator="doubly_robust"),
        plain)["extensions"]["assumption_ledger"]["assumptions"]}
    assert "at_least_one_of_the_two_bridges_lies_in_its_declared_span" in ids
    assert "the_outcome_bridge_lies_in_the_span_of_the_declared_sieve" not in ids
    assert "the_treatment_bridge_lies_in_the_span_of_the_declared_sieve" not in ids


def test_the_reader_is_told_which_assumption_the_number_rests_on(plain):
    """All three estimators are the same shape and differ only in what has to
    be true, so a report naming the method and not the assumption would have
    left out the number's whole content."""
    from themis.output.analysis_report import build_analysis_report

    for estimator, zh, en in (
            ("inverse_probability", "逆概率加权", "inverse-probability"),
            ("doubly_robust", "双稳健", "doubly robust")):
        answered = _answer(
            _channel(d_h=3, m_h=5, m_q=3, d_q=5, estimator=estimator), plain)
        assert zh in build_analysis_report(answered, lang="zh")
        assert en in build_analysis_report(answered, lang="en")


# --- the verifier re-derives both bridges --------------------------------------

@pytest.fixture(scope="module")
def doubly_robust(plain) -> dict:
    return _answer(_channel(d_h=3, m_h=5, m_q=3, d_q=5,
                            estimator="doubly_robust"), plain)


@pytest.fixture(scope="module")
def doubly_robust_program() -> dict:
    return _program(_channel(d_h=3, m_h=5, m_q=3, d_q=5,
                             estimator="doubly_robust"))


def _rejects(forged: dict, program: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program, forged)
    return str(raised.value)


def test_a_truthful_two_bridge_estimate_verifies(doubly_robust,
                                                 doubly_robust_program):
    """The denominator: an untouched envelope passes, so a refusal below is
    about what was moved."""
    themis.verify(doubly_robust_program, doubly_robust)


def test_a_forged_doubly_robust_point_is_refused(doubly_robust,
                                                 doubly_robust_program):
    """A number no combination of the recorded moments produces."""
    forged = copy.deepcopy(doubly_robust)
    moved = _step(forged)["inputs"]["point"] + 0.4
    _step(forged)["inputs"]["point"] = moved
    assert str(moved) in _rejects(forged, doubly_robust_program)


def test_reporting_a_different_one_of_the_three_is_refused(
        doubly_robust, doubly_robust_program):
    """The sharpest of these. Every number on the envelope stays true and the
    point becomes another honestly-computed answer — the outcome regression,
    reported under the doubly robust estimator's ledger. Only re-deriving
    which of the three the query asked for sees it.
    """
    forged = copy.deepcopy(doubly_robust)
    channel = _recorded(forged)
    other = channel["estimates"]["items"]["outcome_regression"]
    if other == pytest.approx(_step(forged)["inputs"]["point"], abs=1e-9):
        pytest.skip("the two estimators agree on this sample to the tolerance "
                    "that would make this counterexample vacuous")
    _step(forged)["inputs"]["point"] = other
    assert "estimator the query named" in _rejects(forged,
                                                   doubly_robust_program)


def test_a_moved_treatment_cross_moment_is_refused(doubly_robust,
                                                   doubly_robust_program):
    """The second bridge's moments are re-solved from, not read.

    ``M`` is what ``t`` comes out of, so a producer that shifted it and left
    every reported figure alone would be reporting an answer no data gives.
    """
    forged = copy.deepcopy(doubly_robust)
    block = _recorded(forged)["treatment_bridge"]["items"]
    block["treated"]["items"]["m"]["items"][0]["items"][0] += 0.05
    assert _rejects(forged, doubly_robust_program)


def test_a_treatment_penalty_that_does_not_follow_from_the_declaration(
        doubly_robust, doubly_robust_program):
    """Nobody named ``q``'s λ, so it is a fixed fraction of that solve's own
    scale — and which fraction is not the producer's to restate."""
    forged = copy.deepcopy(doubly_robust)
    block = _recorded(forged)["treatment_bridge"]["items"]
    block["ridge"] *= 7
    assert "treatment_bridge.ridge" in _rejects(forged, doubly_robust_program)


def test_a_treatment_bridge_dropped_from_the_record_is_refused(
        doubly_robust, doubly_robust_program):
    """An estimator that divides by ``q`` cannot have run without one, so a
    channel that records no second bridge under a query that declares one is
    refused rather than re-read as the single-bridge case."""
    forged = copy.deepcopy(doubly_robust)
    _recorded(forged).pop("treatment_bridge")
    assert "declares a treatment bridge" in _rejects(forged,
                                                     doubly_robust_program)


def test_a_treatment_sieve_other_than_the_one_asked_for_is_refused(
        doubly_robust, doubly_robust_program):
    """The tie between the recorded moments and the QUERY. Without it a second
    bridge could be internally perfect and be a different assumption than the
    one the ledger attributes to the caller."""
    forged = copy.deepcopy(doubly_robust)
    block = _recorded(forged)["treatment_bridge"]["items"]
    factor = block["span_basis"]["items"][0]["items"][0]["items"]
    factor["family"] = "hermite"
    assert "treatment_bridge.span_basis" in _rejects(forged,
                                                     doubly_robust_program)
