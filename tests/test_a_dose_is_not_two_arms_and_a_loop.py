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


def _spec(*, d_w, d_z, d_x=None, m_x=None, ridge=1e-10, d_q=None, m_q=None,
          q_names_x=False, estimator=None) -> BridgeChannel:
    """A channel with the treatment in each side if asked, and a second
    bridge if ``d_q`` is given."""
    span = [_factor("w", d_w)] + ([_factor("x", d_x)] if d_x else [])
    moment = [_factor("z", d_z)] + ([_factor("x", m_x)] if m_x else [])
    treatment = None
    if d_q is not None:
        q_span = [_factor("z", d_q)] + ([_factor("x", 3)] if q_names_x else [])
        q_moment = [_factor("w", m_q)] + ([_factor("x", 3)] if q_names_x else [])
        treatment = BridgeFunction(span_terms=(_term(*q_span),),
                                   moment_terms=(_term(*q_moment),),
                                   ridge=ridge)
    kwargs = {} if estimator is None else {"estimator": estimator}
    return BridgeChannel(
        outcome_bridge=BridgeFunction(
            span_terms=(_term(*span),), moment_terms=(_term(*moment),),
            ridge=ridge),
        treatment_bridge=treatment, **kwargs)


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

def _rejects(forged: dict, program: "dict | None" = None) -> str:
    with pytest.raises(VerificationError) as raised:
        themis.verify(program or _program(domain=[0, 1, 2]), forged)
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


# --- the second bridge, level by level ---------------------------------------

@pytest.fixture(scope="module")
def bounded() -> pd.DataFrame:
    """A three-level assignment whose propensity is bounded away from zero.

    ``q_a`` solves ``E[q_a(Z)|W,A=a] = 1/f(A=a|W)``, so where ``f`` can be
    tiny the target explodes and no polynomial sieve reaches it. Measured:
    on a clipped-and-rounded dose the inverse-probability curve stayed 0.11
    to 0.33 off the truth at every width up to seven, while the outcome
    regression sat at 0.017. Mixing the multinomial logit with a uniform
    floor bounds ``f`` below, and ``q`` becomes a function a sieve spans —
    which is what makes the two robustness directions constructible here at
    all.
    """
    rng = np.random.default_rng(31)
    n = 200000
    u = rng.standard_normal(n)
    logits = np.stack([np.zeros(n), 0.9 * u, 1.8 * u], axis=1)
    p = np.exp(logits - logits.max(axis=1, keepdims=True))
    p /= p.sum(axis=1, keepdims=True)
    p = 0.7 * p + 0.30 / 3.0
    dose = np.array([rng.choice(3, p=row) for row in p], dtype=float)
    effect = np.where(dose == 0, 0.0, np.where(dose == 1, 1.0, 1.3))
    return pd.DataFrame({
        "x": dose,
        "y": effect + 1.1 * u + 0.9 * (u ** 2 - 1.0)
             + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.4 * rng.standard_normal(n),
        "w": 0.9 * u + 0.4 * rng.standard_normal(n),
    })


def _curves(frame, **kwargs) -> "dict[str, list[float]]":
    got = estimate_curve(frame, xcol="x", ycol="y",
                         spec=_spec(ridge=1e-8, **kwargs), levels=_DOSES)
    return {name: [v - curve[0] for v in curve]
            for name, curve in got.channel["estimates"].items()}


def _worst(effects) -> float:
    return max(abs(effects[i] - _TRUTH[_DOSES[i]]) for i in range(3))


#: Wide enough for each bridge to be right, narrow enough to be wrong.
_WIDE = dict(d_w=4, d_z=6, d_x=3, m_x=3, d_q=4, m_q=6)


def test_the_curve_is_doubly_robust_when_the_outcome_bridge_is_wrong(bounded):
    """Half the theorem, on a curve. The outcome regression's curve is off
    and the doubly robust one is not, at every level."""
    got = _curves(bounded, **dict(_WIDE, d_w=2))
    assert _worst(got["outcome_regression"]) > 0.06
    assert _worst(got["doubly_robust"]) < 0.03
    assert _worst(got["inverse_probability"]) < 0.03


def test_the_curve_is_doubly_robust_when_the_treatment_bridge_is_wrong(
        bounded):
    """The other half, which is the one a single shared design cannot
    reach — and the reason each bridge has its own span and moments."""
    got = _curves(bounded, **dict(_WIDE, d_q=2))
    assert _worst(got["inverse_probability"]) > 0.06
    assert _worst(got["doubly_robust"]) < 0.03
    assert _worst(got["outcome_regression"]) < 0.03


def test_both_bridges_wrong_is_wrong_and_says_nothing(bounded):
    """The ledger's line, as arithmetic: double robustness is not a safety
    net. With both spans narrow the doubly robust curve is wrong too, and
    nothing in the answer announces it."""
    got = _curves(bounded, **dict(_WIDE, d_w=2, d_q=2))
    assert _worst(got["doubly_robust"]) > 0.06


def test_all_three_curves_are_reported_whenever_both_bridges_are_declared(
        bounded):
    got = _curves(bounded, **_WIDE)
    assert set(got) == {"outcome_regression", "inverse_probability",
                        "doubly_robust"}
    for name, effects in got.items():
        assert _worst(effects) < 0.03, name


def test_naming_the_treatment_in_the_treatment_bridge_is_refused(bounded):
    """The exact mirror of the outcome bridge's gate, and the opposite fix.

    ``q`` is solved once per level, so it is already saturated in the
    treatment; naming it adds columns that are constant inside every arm.
    Left alone this surfaced as a condition number, which sends a reader to
    widen or penalise the very design they should be shrinking.
    """
    with pytest.raises(EstimatorFailure) as raised:
        estimate_curve(bounded, xcol="x", ycol="y",
                       spec=_spec(ridge=1e-8, q_names_x=True, **_WIDE),
                       levels=_DOSES)
    assert (str(raised.value.failure_type)
            == "treatment_bridge_is_already_per_level")


def test_a_continuous_dose_has_no_arm_for_the_treatment_bridge(continuous):
    """The boundary the two bridges do not share. The outcome regression
    evaluates a fitted bridge at a point and stays defined where nothing was
    observed; the treatment bridge needs rows at the level and has none."""
    with pytest.raises(EstimatorFailure) as raised:
        estimate_curve(continuous, xcol="x", ycol="y",
                       spec=_spec(d_w=3, d_z=5, d_x=3, m_x=4, d_q=3, m_q=5),
                       levels=(0.0, 1.0, 2.0))
    assert (str(raised.value.failure_type)
            == "treatment_bridge_needs_rows_at_each_level")


def test_the_same_continuous_dose_is_answered_by_the_outcome_regression(
        continuous):
    """The counterexample the refusal above needs: it must be about the
    treatment bridge and not about continuous doses."""
    got = estimate_curve(continuous, xcol="x", ycol="y",
                         spec=_spec(d_w=3, d_z=5, d_x=3, m_x=4),
                         levels=(0.0, 1.0, 2.0))
    assert len(got.means) == 3


# --- the second bridge, end to end -------------------------------------------

def _dr_program() -> dict:
    prog = _program(domain=[0, 1, 2])
    channel = prog["statements"][-1]["query"]["channel"]
    channel["estimator"] = "doubly_robust"
    channel["treatment_bridge"] = {
        "span_terms": [{"factors": [_dict_factor("z", 4)]}],
        "moment_terms": [{"factors": [_dict_factor("w", 6)]}],
    }
    return prog


@pytest.fixture(scope="module")
def doubly_robust(bounded) -> dict:
    return themis.estimate(_dr_program(), bounded,
                           ci_bootstrap=0)["results"][0]


def test_a_doubly_robust_curve_carries_the_union_line(doubly_robust):
    """The claim #455 built, on the shape #456 added. Before the second
    bridge reached this path the ledger said this and one bridge had been
    solved — a claim the verifier caught and a caller who skipped it did
    not."""
    ids = {e["id"] for e in
           doubly_robust["extensions"]["assumption_ledger"]["assumptions"]}
    assert "at_least_one_of_the_two_bridges_lies_in_its_declared_span" in ids
    assert "completeness_of_the_conditional_operator_E[.|W,A=a,X]" in ids


def test_the_doubly_robust_curve_verifies(doubly_robust):
    themis.verify(_dr_program(), doubly_robust)


def test_the_curve_reported_is_the_estimator_the_query_named(doubly_robust):
    """Three curves are recorded and one is the answer. Reporting a
    different one than the query asked for would rest the answer on an
    assumption the ledger did not list."""
    channel = _channel(doubly_robust)
    named = channel["estimates"]["items"]["doubly_robust"]["items"]
    curve = doubly_robust["numeric_estimate"]["dose_response_curve"]
    for index, point in enumerate(curve):
        assert point["effect"] == pytest.approx(named[index] - named[0],
                                                abs=1e-9)


def test_a_curve_from_the_wrong_estimator_is_refused(doubly_robust):
    """The forgery this record is shaped to catch: swap in the outcome
    regression's curve, which is a real curve from real moments and simply
    not the one the query asked for."""
    forged = copy.deepcopy(doubly_robust)
    other = _channel(forged)["estimates"]["items"]["outcome_regression"]["items"]
    reported = _step(forged)["inputs"]["dose_response_curve"]["items"]
    for index, point in enumerate(reported):
        point["items"]["effect"] = other[index] - other[0]
    assert "re-solved bridge gives" in _rejects(forged, _dr_program())


def test_a_moved_treatment_arm_moment_is_refused(doubly_robust):
    """``t`` at one level comes out of that level's recorded ``m``."""
    forged = copy.deepcopy(doubly_robust)
    arms = _channel(forged)["treatment_bridge"]["items"]["arms"]["items"]
    key = sorted(arms)[1]
    arms[key]["items"]["m"]["items"][0]["items"][0] += 0.05
    assert _rejects(forged, _dr_program())


# --- what #455 promised, kept on the new shape -------------------------------

@pytest.fixture(scope="module")
def q_leaves_its_range() -> dict:
    """A clipped-and-rounded dose, whose propensity is tiny in the tails.

    ``1/f`` explodes there, the linear sieve cannot hold a function of that
    shape, and the fitted ``q`` dips below zero — which #455 promised would
    be reported rather than absorbed. That promise was written against a
    record with two arms named ``treated`` and ``control``, so it lapsed
    silently the moment a curve's arms became its levels.
    """
    rng = np.random.default_rng(23)
    n = 60000
    u = rng.standard_normal(n)
    dose = np.clip(np.round(1.0 + 0.9 * u + 0.8 * (u ** 2 - 1.0)
                            + 0.8 * rng.standard_normal(n)), 0, 2) + 0.0
    effect = np.where(dose == 0, 0.0, np.where(dose == 1, 1.0, 1.3))
    frame = pd.DataFrame({
        "x": dose,
        "y": effect + 1.1 * u + 0.3 * rng.standard_normal(n),
        "z": 1.2 * u + 0.4 * rng.standard_normal(n),
        "w": 0.9 * u + 0.4 * rng.standard_normal(n),
    })
    program = _dr_program()
    program["statements"][-1]["query"]["channel"]["estimator"] = (
        "inverse_probability")
    return themis.estimate(program, frame, ci_bootstrap=0)["results"][0]


def test_a_curve_says_when_its_treatment_bridge_left_its_range(
        q_leaves_its_range):
    filed = [g for g in q_leaves_its_range["data_gap_report"]["gaps"]
             if g["kind"] == "treatment_bridge_leaves_its_range"]
    assert len(filed) == 1, [
        g["kind"] for g in q_leaves_its_range["data_gap_report"]["gaps"]]
    routes = {p["route"] for p in filed[0]["alternative_paths"]}
    assert routes == {"widen_the_treatment_bridge",
                      "read_the_doubly_robust_answer_instead"}


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_worst_level_is_named_with_its_share(q_leaves_its_range, lang):
    """The level matters as much as the share: a reader deciding whether to
    trust the curve needs to know it is one point's problem rather than the
    whole curve's."""
    from themis.output.analysis_report import build_analysis_report

    arms = (_channel(q_leaves_its_range)["treatment_bridge"]["items"]
            ["arms"]["items"])
    shares = {level: block["items"]["q_negative_fraction"]
              for level, block in arms.items()}
    worst = max(shares, key=lambda level: shares[level])
    text = build_analysis_report(q_leaves_its_range, lang=lang)
    assert f"{shares[worst]:.1%}" in text
    assert str(float(worst)) in text
    assert str(len(shares)) in text


@pytest.mark.parametrize("lang,phrase", [
    ("zh", "双稳健"), ("en", "doubly robust")])
def test_the_reader_is_told_which_curve_this_is(doubly_robust, lang, phrase):
    """Every estimator's curve needs its own sentence. A lookup that missed
    would print no statement at all, leaving a reader a curve and no account
    of what has to be true for it."""
    from themis.output.analysis_report import build_analysis_report

    text = build_analysis_report(doubly_robust, lang=lang)
    assert phrase in text


def test_a_flattered_penalty_ladder_is_refused(answered):
    """The ladder says how much of the CURVE is the penalty's, which the
    curve itself does not, so it is re-walked rather than read."""
    forged = copy.deepcopy(answered)
    rung = _channel(forged)["penalty_ladder"]["items"][-1]
    points = rung["items"]["points"]["items"]
    key = sorted(points)[-1]
    points[key] += 0.2
    assert "penalty_ladder" in _rejects(forged)
