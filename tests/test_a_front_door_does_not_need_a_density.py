"""#483 — the front door through a mediator that has no levels.

The refusal this replaces said the high-cardinality case "needs density
estimation, which is deferred". The first half is a claim about the
formula and it is false: Pearl's front-door expression takes P(M | X) as
the WEIGHT of an average, not as a curve to be drawn, so under a binary
treatment the two arms' own rows already are that weight and nothing has
to be smoothed:

    E[Y | do(x)] = ⟨ Σ_x' P(x') · Ê[Y | X=x', M=M_i] ⟩_{i : X_i = x}

Two model evaluations per row. No strata, no cross-product cap, no
density — and both outcome forms, since nothing here integrates the link.

What these tests hold, in order: that the arithmetic lands on a truth
computed outside it; that the road is chosen by the mediator SET and not
one column at a time; that the enumerating road is untouched where it was
already right; and that the audit at the end refuses a point that does
not follow from the numbers the same result reports — which is the whole
reason those numbers are recorded.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.frontdoor import (
    MAX_LEVELS_PER_MEDIATOR,
    estimate_frontdoor_ate,
    exactly_summable,
)
from themis.verifier import VerificationError, verify_frontdoor_empirical_numeric


# --- the truth, and where it comes from ---------------------------------------


def _continuum(n=20000, seed=0, a=1.3, b=0.7):
    """X → M → Y with X ↔ Y latent and M a continuum.

    The mediated effect is a product of two coefficients no estimator here
    is told: X shifts M by ``a``, and M moves Y by ``b`` once X is held, so
    the front-door answer is ``a·b``. The latent U enters both X and Y and
    nothing else, which is what makes back-door adjustment unavailable and
    the front door the only road.
    """
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = (u + rng.standard_normal(n) > 0).astype(float)
    m = a * x + rng.standard_normal(n)
    y = b * m + 1.0 * u + rng.standard_normal(n) * 0.5
    return pd.DataFrame({"x": x, "m": m, "y": y}), a * b


def test_the_point_lands_on_a_truth_computed_outside_it():
    df, truth = _continuum()
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert est.method == "frontdoor_empirical_linear"
    assert abs(est.point - truth) < 0.03, (est.point, truth)


def test_the_naive_regression_this_beats_is_the_one_that_ignores_the_graph():
    """The counterexample that makes the number mean something.

    A front-door estimate that agreed with the confounded regression of Y
    on X would be a number that had not used the graph at all. The latent
    U is deliberately large enough that the two disagree by more than the
    front-door estimate's own error, so the test can tell them apart.
    """
    df, truth = _continuum()
    naive = float(np.mean(df.y[df.x > 0.5]) - np.mean(df.y[df.x < 0.5]))
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert abs(naive - truth) > 10 * abs(est.point - truth), (naive, est.point)


def test_the_interval_brackets_the_point_and_the_truth():
    df, truth = _continuum(n=6000, seed=3)
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=200,
    )
    assert est.ci_lower < est.point < est.ci_upper
    assert est.ci_lower < truth < est.ci_upper


def test_a_binary_outcome_takes_the_same_road_on_the_logit_form():
    rng = np.random.default_rng(7)
    n = 6000
    u = rng.standard_normal(n)
    x = (u + rng.standard_normal(n) > 0).astype(float)
    m = 1.2 * x + rng.standard_normal(n)
    y = rng.random(n) < 1 / (1 + np.exp(-(0.9 * m + 1.5 * u)))
    df = pd.DataFrame({"x": x, "m": m, "y": y})

    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert est.method == "frontdoor_empirical_logistic"
    stats = est.sufficient_statistics
    # Standardized probabilities, so each arm is one — and their difference
    # is a risk difference, which is what the point claims to be.
    assert 0.0 <= stats["arm_control"] <= 1.0
    assert 0.0 <= stats["arm_treated"] <= 1.0
    assert est.point == pytest.approx(
        stats["arm_treated"] - stats["arm_control"])


# --- which road, and why it is asked of the set -------------------------------


def test_the_fork_is_a_question_about_the_set_not_about_a_column():
    """Three mediators each as enumerable as a coin, and 15³ strata.

    Asked one column at a time the answer is yes three times over, and the
    query goes down a road that enumerates 3375 assignments. The exact sum
    is over the JOINT assignment, so that is what the question has to be
    about.
    """
    rng = np.random.default_rng(4)
    n = 900
    df = pd.DataFrame({
        "x": (rng.random(n) < 0.5).astype(float),
        "m1": rng.integers(0, 15, n).astype(float),
        "m2": rng.integers(0, 15, n).astype(float),
        "m3": rng.integers(0, 15, n).astype(float),
        "y": rng.standard_normal(n),
    })
    assert all(exactly_summable(df, (m,)) for m in ("m1", "m2", "m3"))
    assert not exactly_summable(df, ("m1", "m2", "m3"))


def test_a_column_at_the_cap_and_one_past_it_fall_on_opposite_sides():
    rng = np.random.default_rng(11)
    n = 600
    at_cap = pd.DataFrame({
        "m": rng.integers(0, MAX_LEVELS_PER_MEDIATOR, n).astype(float)})
    past = pd.DataFrame({
        "m": rng.integers(0, MAX_LEVELS_PER_MEDIATOR + 1, n).astype(float)})
    assert exactly_summable(at_cap, ("m",))
    assert not exactly_summable(past, ("m",))


def test_the_enumerating_road_still_answers_where_it_always_did():
    """The fork must not move a number that was already right.

    A bool mediator has two levels and the exact sum over them is what this
    package has reported all along; a route that quietly took the new road
    here would change published answers for no reason anyone asked for.
    """
    rng = np.random.default_rng(0)
    n = 4000
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-u))
    m = rng.random(n) < 1 / (1 + np.exp(-(2.0 * x - 1)))
    df = pd.DataFrame({
        "x": x, "m": m,
        "y": 1.0 * m + 2.0 * u + rng.standard_normal(n) * 0.3,
    })
    est = estimate_frontdoor_ate(
        df, treatment="x", outcome="y", mediators=("m",), ci_bootstrap=0,
    )
    assert est.method == "frontdoor_linear"
    assert est.sufficient_statistics == {}, (
        "the enumerating road published arms it cannot re-derive"
    )


def test_the_road_is_chosen_once_and_the_interval_stays_on_it():
    """A resample can lose a level; it cannot gain one.

    So a sample the fork calls summable has summable resamples, and the
    bootstrap never has to ask again. The property is what lets one
    decision cover the point and every replicate — and if it were false,
    an interval could be built from two different estimators.
    """
    rng = np.random.default_rng(9)
    n = 500
    df = pd.DataFrame({
        "x": (rng.random(n) < 0.5).astype(float),
        "m": rng.integers(0, MAX_LEVELS_PER_MEDIATOR, n).astype(float),
        "y": rng.standard_normal(n),
    })
    assert exactly_summable(df, ("m",))
    for seed in range(25):
        draw = df.iloc[np.random.default_rng(seed).integers(0, n, n)]
        assert exactly_summable(draw, ("m",))


# --- the audit, and the point it has to refuse --------------------------------


def _envelope(**overrides):
    df, _ = _continuum(n=3000, seed=5)
    program = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "from": {"predicate": "x", "args": []},
             "to": {"predicate": "m", "args": []}},
            {"kind": "cause", "from": {"predicate": "m", "args": []},
             "to": {"predicate": "y", "args": []}},
            {"kind": "bidirected", "left": {"predicate": "x", "args": []},
             "right": {"predicate": "y", "args": []}},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": {"predicate": "x", "args": []},
                                 "value": True},
                "target": {"atom": {"predicate": "y", "args": []},
                           "value": True},
                "given": []}},
        ],
    }
    out = themis.estimate(program, df.assign(x=df.x > 0.5), ci_bootstrap=0)
    result = out["results"][0]
    result["numeric_estimate"].update(overrides)
    return program, result


def test_the_round_trip_stands():
    program, result = _envelope()
    assert result["numeric_estimate"]["method"] == "frontdoor_empirical_linear"
    themis.verify(program, result)


def test_a_point_that_is_not_the_difference_of_its_own_arms_is_refused():
    _, result = _envelope()
    estimate = dict(result["numeric_estimate"])
    estimate["point"] = estimate["point"] + 0.4
    with pytest.raises(VerificationError, match="difference of the two"):
        verify_frontdoor_empirical_numeric(estimate)


def test_a_point_made_consistent_with_its_arms_is_still_refused():
    """The forgery the first check cannot see, and the reason for the second.

    Moving the point and both arms together keeps the difference identity
    exactly true — the answer now agrees with itself. What it no longer
    agrees with is the fit: on a linear outcome model the intercept and the
    treatment term cancel from the contrast, so the point IS the
    coefficients dotted with the mediator shift, and those are recorded.
    """
    _, result = _envelope()
    estimate = dict(result["numeric_estimate"])
    block = dict(estimate["front_door_empirical"])
    block["arm_treated"] = block["arm_treated"] + 0.4
    estimate["front_door_empirical"] = block
    estimate["point"] = estimate["point"] + 0.4

    with pytest.raises(VerificationError, match="does not follow from the"):
        verify_frontdoor_empirical_numeric(estimate)


def test_a_result_that_names_the_road_without_carrying_the_block_is_refused():
    _, result = _envelope()
    estimate = dict(result["numeric_estimate"])
    estimate.pop("front_door_empirical")
    with pytest.raises(VerificationError, match="front_door_empirical block"):
        verify_frontdoor_empirical_numeric(estimate)


def test_an_arm_with_no_rows_in_it_cannot_be_claimed():
    """The one refusal this road does keep, said at the audit too.

    Both arms are where an arm's mediator spread is READ, so a treatment at
    a single level is not a thin case of this estimator, it is no case of
    it. The enumerating road never needed the check — a fitted conditional
    returns a number at a level no row holds.
    """
    _, result = _envelope()
    estimate = dict(result["numeric_estimate"])
    block = dict(estimate["front_door_empirical"])
    block["treatment_prevalence"] = 1.0
    estimate["front_door_empirical"] = block
    with pytest.raises(VerificationError, match="strictly between 0 and 1"):
        verify_frontdoor_empirical_numeric(estimate)


def test_the_logit_form_is_audited_for_what_it_can_answer_for():
    """Standardization is not collapsible, so the coefficients do not
    re-derive the arms — claiming they did would be the audit agreeing with
    itself. What stays checkable is the difference identity and the fact
    that each arm is a probability."""
    _, result = _envelope()
    estimate = dict(result["numeric_estimate"])
    estimate["method"] = "frontdoor_empirical_logistic"
    block = dict(estimate["front_door_empirical"])
    block["arm_treated"], block["arm_control"] = 0.62, 0.41
    estimate["front_door_empirical"] = block
    estimate["point"] = 0.21
    verify_frontdoor_empirical_numeric(estimate)   # must not raise

    block["arm_treated"] = 1.4
    estimate["point"] = 1.4 - 0.41
    with pytest.raises(VerificationError, match=r"lie in \[0, 1\]"):
        verify_frontdoor_empirical_numeric(estimate)
