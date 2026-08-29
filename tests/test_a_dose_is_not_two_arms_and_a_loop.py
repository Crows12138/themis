"""A proximal question about a DOSE, which used to be a refusal.

Cui, Pu, Miao, Zhang & Tchetgen Tchetgen 2024 (*JASA* 119(546)) Theorem 2.1
identifies the counterfactual mean AT A LEVEL::

    E[Y(a)] = ∫∫ h(w, a, x) dF(w|x) dF(x)                              (4)

and the average treatment effect is the difference of two of those. Remark 3
says the same of the treatment bridge and adds that it "also applies for a
continuous possibly multivariate exposure A". So ``a`` is an ARGUMENT of the
bridge, and a curve is the primitive with the contrast derived from it —
not the other way round.

Themis had it the other way round. ``estimate_bridge`` cast the treatment to
``bool``, solved a bridge in each arm and subtracted, so a treatment with
three levels was refused (``treatment_not_binary``) rather than answered.
That refusal was honest and it was covering two different things: a contrast
needs two levels to contrast, which is true, and Themis could not evaluate
one bridge at many levels, which was an absence rather than a boundary.

**The joint solve.** Put the treatment inside both designs and fit ONE
bridge over every row::

    span   b(W, A, C)      moments  a(Z, A, C)
    G = S_ABᵀ S_AA⁻¹ S_AB,  c = S_ABᵀ S_AA⁻¹ S_Ay,  θ = (G + λI)⁻¹c
    E[Y(a)] = w̄(a)ᵀθ,  w̄(a) = mean of b(W, a, C) over ALL rows

``w̄(a)`` is (4)'s inner integral as a sample mean: the span rebuilt with the
treatment column held at ``a`` and everything else left as observed.

**Why both regimes stay.** The two-arm fit gives each arm its own
coefficients, which is the bridge SATURATED in the treatment — strictly more
general than any declared span in ``a``. Migrating the binary path onto the
joint solve would silently narrow it for a caller who did not saturate. What
connects them is an identity, and it is what this file pins first: saturate
the declared designs and the joint solve reproduces the two-arm answer to
machine precision.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.proximal_bridge import (
    estimate_bridge, estimate_curve, resolve_levels,
)
from themis.refusals import EstimatorFailure
from themis.types import (
    Atom, BasisFamily, BridgeChannel, BridgeFunction, SieveFactor, SieveTerm,
)
from themis.verifier.errors import VerificationError


# --- saying it ---------------------------------------------------------------

def _atom(p: str) -> Atom:
    return Atom(predicate=p, args=())


def _factor(variable: str, dimension: int,
            family: BasisFamily = BasisFamily.POLYNOMIAL) -> SieveFactor:
    return SieveFactor(variable=_atom(variable), basis=family,
                       dimension=dimension)


def _term(*factors: SieveFactor) -> SieveTerm:
    return SieveTerm(factors=tuple(factors))


def _spec(*, d_w, d_z, d_x=None, m_x=None, ridge=1e-10) -> BridgeChannel:
    """A one-bridge channel, with the treatment in each side if asked."""
    span = [_factor("w", d_w)] + ([_factor("x", d_x)] if d_x else [])
    moment = [_factor("z", d_z)] + ([_factor("x", m_x)] if m_x else [])
    return BridgeChannel(outcome_bridge=BridgeFunction(
        span_terms=(_term(*span),), moment_terms=(_term(*moment),),
        ridge=ridge))


def _dict_factor(variable: str, dimension: int) -> dict:
    return {"variable": {"predicate": variable, "args": []},
            "basis": "polynomial", "dimension": dimension}


def _program(*, d_w=3, d_z=5, d_x=3, m_x=3, ridge=None, domain=None) -> dict:
    span = [_dict_factor("w", d_w)] + ([_dict_factor("x", d_x)] if d_x else [])
    moment = [_dict_factor("z", d_z)] + ([_dict_factor("x", m_x)] if m_x else [])
    bridge: dict = {"span_terms": [{"factors": span}],
                    "moment_terms": [{"factors": moment}]}
    if ridge is not None:
        bridge["ridge"] = ridge
    x_decl: dict = {"kind": "variable", "predicate": "x"}
    if domain is not None:
        x_decl.update(scale="discrete", domain=domain)

    def var(p, **kw):
        return {"kind": "variable", "predicate": p, **kw}

    def cause(a, b):
        return {"kind": "cause", "from": {"predicate": a, "args": []},
                "to": {"predicate": b, "args": []}}

    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            x_decl, var("y", scale="continuous"), var("u"),
            var("z", scale="continuous"), var("w", scale="continuous"),
            cause("u", "x"), cause("u", "y"), cause("u", "z"), cause("u", "w"),
            cause("z", "x"), cause("w", "y"), cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": {"predicate": "x", "args": []},
                "outcome": {"predicate": "y", "args": []},
                "latent": {"predicate": "u", "args": []},
                "treatment_proxy": [{"predicate": "z", "args": []}],
                "outcome_proxy": [{"predicate": "w", "args": []}],
                "channel": {"kind": "bridge_channel",
                            "outcome_bridge": bridge},
            }},
        ],
    }


# --- the samples -------------------------------------------------------------

#: The three-level truth, deliberately CONCAVE. A straight line through the
#: ends would put 0.65 at dose 1, so a method that only got the endpoints
#: right would be visibly wrong in the middle.
_DOSES = (0.0, 1.0, 2.0)
_TRUTH = {0.0: 0.0, 1.0: 1.0, 2.0: 1.3}


@pytest.fixture(scope="module")
def binary() -> pd.DataFrame:
    rng = np.random.default_rng(5)
    n = 20000
    u = rng.standard_normal(n)
    x = (rng.random(n) < 1 / (1 + np.exp(-0.9 * u))).astype(float)
    return pd.DataFrame({
        "x": x,
        "y": 1.5 * x + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.5 * rng.standard_normal(n),
        "w": 0.9 * u + 0.5 * rng.standard_normal(n),
    })


@pytest.fixture(scope="module")
def three_level() -> pd.DataFrame:
    rng = np.random.default_rng(11)
    n = 40000
    u = rng.standard_normal(n)
    dose = np.clip(np.round(1.0 + 0.9 * u + 0.7 * rng.standard_normal(n)),
                   0, 2) + 0.0
    effect = np.where(dose == 0, 0.0, np.where(dose == 1, 1.0, 1.3))
    return pd.DataFrame({
        "x": dose,
        "y": effect + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.5 * rng.standard_normal(n),
        "w": 0.9 * u + 0.5 * rng.standard_normal(n),
    })


def _continuous_truth(a):
    return 0.9 * a - 0.15 * a ** 2


@pytest.fixture(scope="module")
def continuous() -> pd.DataFrame:
    rng = np.random.default_rng(7)
    n = 60000
    u = rng.standard_normal(n)
    dose = 1.0 + 0.8 * u + 0.9 * rng.standard_normal(n)
    return pd.DataFrame({
        "x": dose,
        "y": _continuous_truth(dose) + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.5 * rng.standard_normal(n),
        "w": 0.9 * u + 0.5 * rng.standard_normal(n),
    })


# --- the identity that connects the two regimes ------------------------------

def test_a_saturated_joint_solve_is_the_two_arm_solve(binary):
    """The claim that lets both regimes stand, checked at machine precision.

    With every term of both sides tensored with a two-dimensional basis on a
    two-valued column — which spans {1, 1(x=1)} exactly — the joint system
    block-diagonalises by arm, and the two solves are the same arithmetic
    written twice. If this drifted, one of the two paths would be answering
    a different question under the same name.
    """
    two_arm = estimate_bridge(binary, xcol="x", ycol="y",
                              spec=_spec(d_w=3, d_z=5, ridge=1e-12))
    curve = estimate_curve(
        binary, xcol="x", ycol="y",
        spec=_spec(d_w=3, d_z=5, d_x=2, m_x=2, ridge=1e-12),
        levels=(0.0, 1.0))
    assert curve.means[0] == pytest.approx(two_arm.do_control, abs=1e-12)
    assert curve.means[1] == pytest.approx(two_arm.do_treated, abs=1e-12)
    assert curve.means[1] - curve.means[0] == pytest.approx(
        two_arm.point, abs=1e-12)


# --- what the curve is for ---------------------------------------------------

def test_a_three_level_curve_recovers_a_shape_two_points_cannot(three_level):
    """The middle level is the test. Confounding pulls the naive contrast
    away from the truth, and a curve that only had the endpoints right would
    put 0.65 where 1.0 belongs."""
    got = estimate_curve(three_level, xcol="x", ycol="y",
                         spec=_spec(d_w=3, d_z=5, d_x=3, m_x=3),
                         levels=_DOSES)
    base = got.means[0]
    for level, mean in zip(got.levels, got.means):
        assert mean - base == pytest.approx(_TRUTH[level], abs=0.05), level
    # And the shape is genuinely concave, not a line through the ends.
    straight = (got.means[2] - got.means[0]) / 2
    assert got.means[1] - got.means[0] > straight + 0.2


def test_a_continuous_dose_is_answered_where_no_row_sits(continuous):
    """The decisive case, and the reason a per-pair two-arm fit is not an
    alternative rather than merely a worse one: at a level no row takes there
    is no arm to fit, and evaluating one fitted bridge there is a different
    operation that remains defined."""
    levels = (-0.5, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5)
    assert not set(levels) & set(continuous["x"].unique())
    got = estimate_curve(continuous, xcol="x", ycol="y",
                         spec=_spec(d_w=3, d_z=5, d_x=3, m_x=4),
                         levels=levels)
    base = got.means[levels.index(0.0)]
    for level, mean in zip(got.levels, got.means):
        assert mean - base == pytest.approx(
            _continuous_truth(level) - _continuous_truth(0.0),
            abs=0.05), level


def test_the_confounding_is_what_makes_this_hard(continuous):
    """The counterexample to the whole exercise being unnecessary: reading
    the dose response straight off the data gets the slope wrong, because U
    drives both the dose and the outcome."""
    quadratic, linear, _ = np.polyfit(continuous["x"], continuous["y"], 2)
    assert linear == pytest.approx(1.5, abs=0.1)   # truth is 0.9
    assert quadratic == pytest.approx(-0.15, abs=0.02)


# --- which levels ------------------------------------------------------------

def test_few_distinct_values_are_the_levels_themselves():
    assert resolve_levels(np.array([2.0, 0.0, 1.0, 1.0, 2.0])) == (0.0, 1.0, 2.0)


def test_many_distinct_values_are_sampled_rather_than_enumerated():
    levels = resolve_levels(np.linspace(0.0, 1.0, 5000))
    assert 2 <= len(levels) <= 7
    assert list(levels) == sorted(levels)
    assert levels[0] == pytest.approx(0.0)
    assert levels[-1] == pytest.approx(1.0)


def test_a_rounded_column_does_not_reach_the_reader_as_minus_zero():
    """``round`` and ``clip`` both produce -0.0, which compares equal to zero
    everywhere in the code and prints as "-0" on the page."""
    levels = resolve_levels(np.array([-0.0, 1.0, 2.0]))
    assert not any(np.signbit(v) for v in levels), levels


# --- the gate ----------------------------------------------------------------

def _curve_refusal(frame, **kwargs):
    with pytest.raises(EstimatorFailure) as raised:
        estimate_curve(frame, xcol="x", ycol="y", spec=_spec(**kwargs),
                       levels=_DOSES)
    return raised.value


def test_a_span_that_cannot_vary_with_the_dose_is_refused(three_level):
    """Without the treatment in the span, h is one function of the proxies at
    every level and every point of the curve is the same number."""
    exc = _curve_refusal(three_level, d_w=3, d_z=5, m_x=3)
    assert str(exc.failure_type) == "bridge_cannot_vary_with_the_treatment"


def test_moments_blind_to_the_dose_are_refused_though_they_are_wide_enough(
        three_level):
    """The case the width count passes, which is why this gate is not that
    count said again.

    A span of ``w(3) ⊗ x(3)`` has 9 unknowns and ``z(10)`` supplies 10
    moments, so "moments ≥ unknowns" is satisfied. The moment condition
    holds GIVEN (Z, A, C) though, and moments that never mention A ask it to
    hold on average across levels instead — the system is exactly identified
    by the wrong equations and would have returned a number.
    """
    exc = _curve_refusal(three_level, d_w=3, d_z=10, d_x=3)
    assert str(exc.failure_type) == "bridge_cannot_vary_with_the_treatment"


def test_a_design_that_names_the_dose_on_both_sides_is_not_refused(
        three_level):
    """The counterexample the two gates need: a gate that fired either way
    would be reporting the method rather than this declaration."""
    got = estimate_curve(three_level, xcol="x", ycol="y",
                         spec=_spec(d_w=3, d_z=5, d_x=3, m_x=3),
                         levels=_DOSES)
    assert len(got.means) == 3


def test_a_binary_treatment_keeps_the_contrast_when_nobody_asked_for_a_curve(
        binary):
    """The regime split, from the outside. A sieve that does not name the
    treatment is a request for a bridge per arm, and it still gets one."""
    answered = themis.estimate(
        _program(d_x=None, m_x=None), binary, ci_bootstrap=0)["results"][0]
    numeric = answered["numeric_estimate"]
    assert numeric["point"] == pytest.approx(1.5, abs=0.08)
    assert "dose_response_curve" not in numeric


# --- the envelope ------------------------------------------------------------

@pytest.fixture(scope="module")
def answered(three_level) -> dict:
    return themis.estimate(_program(domain=[0, 1, 2]), three_level,
                           ci_bootstrap=60)["results"][0]


def test_the_curve_replaces_the_contrast_rather_than_joining_it(answered):
    """Two answers to one question would let every surface that leads with a
    point lead with whichever pair of levels this layer had picked."""
    numeric = answered["numeric_estimate"]
    assert numeric["sampling_points"] == list(_DOSES)
    assert numeric["reference_point"] == 0.0
    assert len(numeric["dose_response_curve"]) == 3
    for absent in ("point", "ci_lower", "ci_upper",
                   "do_prob_treated", "do_prob_control"):
        assert absent not in numeric, absent


def test_the_reference_level_has_no_effect_and_no_band(answered):
    first = answered["numeric_estimate"]["dose_response_curve"][0]
    assert first["effect"] == 0.0
    assert first["ci_lower"] == 0.0 and first["ci_upper"] == 0.0


def test_the_bands_come_from_one_resampled_curve_each(answered):
    """Every band is taken across whole re-solved curves, so the reference's
    own uncertainty is inside all of them and its own band is exactly zero."""
    curve = answered["numeric_estimate"]["dose_response_curve"]
    for point in curve[1:]:
        assert point["ci_lower"] < point["effect"] < point["ci_upper"]
        assert point["ci_lower"] == pytest.approx(_TRUTH[point["x"]], abs=0.15)


def test_the_curve_verifies(answered):
    themis.verify(_program(domain=[0, 1, 2]), answered)


def test_the_ledger_says_the_shape_between_levels_was_the_callers(answered):
    """The line a curve adds and a contrast has no need of: the points are
    the data's and how they join up is the declared basis'."""
    ids = {e["id"] for e in
           answered["extensions"]["assumption_ledger"]["assumptions"]}
    assert ("the_bridge_varies_with_the_treatment_as_the_declared_basis_does"
            in ids)


@pytest.mark.parametrize("lang,phrase", [("zh", "曲线"), ("en", "curve")])
def test_the_reader_is_told_it_is_a_curve_not_a_contrast(answered, lang,
                                                         phrase):
    """The estimator sentence has its own curve form. A reader shown
    "average h(W,1,C) − h(W,0,C)" over a curve has been told the arithmetic
    of a contrast that did not run."""
    from themis.output.analysis_report import build_analysis_report

    text = build_analysis_report(answered, lang=lang)
    assert phrase in text
    assert "h(W,1,C)" not in text
    assert "h(W,a,C)" in text


# --- what the verifier refuses -----------------------------------------------

def _rejects(forged: dict) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(_program(domain=[0, 1, 2]), forged)
    return str(raised.value)


def _step(result: dict) -> dict:
    return result["derivation"]["steps"][1]


def _channel(result: dict) -> dict:
    return _step(result)["inputs"]["measurement_channel"]["items"]


def test_a_moved_curve_point_is_refused(answered):
    """One point of a curve moved is one point moved away from the same θ
    that produces its neighbours."""
    forged = copy.deepcopy(answered)
    _step(forged)["inputs"]["dose_response_curve"]["items"][1][
        "items"]["effect"] += 0.05
    assert "re-solved bridge gives" in _rejects(forged)


def test_a_moved_cross_moment_is_refused(answered):
    """θ comes out of the recorded operator, so a producer that shifted it
    and left the curve alone would be reporting a curve no data gives."""
    forged = copy.deepcopy(answered)
    _channel(forged)["joint"]["items"]["s_ab"]["items"][0]["items"][0] += 0.05
    assert _rejects(forged)


def test_a_curve_carrying_a_contrast_is_refused(answered):
    """Two shapes on one answer: the rule would otherwise check whichever
    was there and pass a producer that shipped neither honestly."""
    forged = copy.deepcopy(answered)
    _step(forged)["inputs"]["point"] = 1.0
    assert "no contrast to lead with" in _rejects(forged)


def test_a_reference_that_is_not_the_lowest_level_is_refused(answered):
    forged = copy.deepcopy(answered)
    _step(forged)["inputs"]["reference_point"] = 1.0
    assert "lowest level" in _rejects(forged)


def test_a_flattered_penalty_ladder_is_refused(answered):
    """The ladder says how much of the CURVE is the penalty's, which the
    curve itself does not, so it is re-walked rather than read."""
    forged = copy.deepcopy(answered)
    rung = _channel(forged)["penalty_ladder"]["items"][-1]
    points = rung["items"]["points"]["items"]
    key = sorted(points)[-1]
    points[key] += 0.2
    assert "penalty_ladder" in _rejects(forged)
