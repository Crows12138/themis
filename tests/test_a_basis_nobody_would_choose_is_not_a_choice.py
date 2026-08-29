"""Five families a caller can declare, and what each of them is for.

A closed vocabulary of assumptions is only worth its size if a caller has
a reason to reach for each member. Two members made that reason easy —
global support or local — and this file is the measurement for the three
that were added beside them, because a family whose advantage nobody can
demonstrate is a name rather than a choice.

What the members are measured on is deliberately not one axis. A sieve is
picked under two pressures at once: whether the bridge is IN the span, and
whether the inverse of the design is takeable at all. The orthogonal
family wins the second outright, the periodic one wins the first on a
variable that comes back to where it started, and the spline TRADES — it
is closer on a smooth target, further on a kinked one, and worse
conditioned than the hats either way.

One invariant runs under all of it and is checked for every member: each
family spans the constant with a non-zero coefficient on its first column.
A design lays several bases side by side and removes one constant from
each so the whole keeps exactly one, and a family that reached the
constant some other way would make that subtraction change the span
instead of deduplicating it.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.proximal_bridge import _FAMILIES, _fit_basis
from themis.input.semantic_validator import Malformed, SemanticError
from themis.output.analysis_report import _BASIS_WORDS
from themis.types import SIEVE_MINIMUM_DIMENSION, BasisFamily

BETA = 1.5


def _widest(family: BasisFamily) -> int:
    """A dimension every family admits, for the invariants below."""
    return max(4, SIEVE_MINIMUM_DIMENSION[family])


# --- the vocabulary is complete ------------------------------------------------

@pytest.mark.parametrize("family", list(BasisFamily), ids=str)
def test_every_family_can_be_built_and_evaluated(family):
    """The half a schema enum cannot state. A member a caller may declare
    and the estimator has no arithmetic for is a name that reaches a
    KeyError with a question behind it."""
    assert family in _FAMILIES
    assert family in SIEVE_MINIMUM_DIMENSION


def test_no_family_is_declared_that_nothing_names():
    """The other direction, which the parametrised test above cannot see:
    arithmetic for a family the vocabulary does not carry is arithmetic a
    caller has no way to ask for."""
    assert set(_FAMILIES) == set(BasisFamily)
    assert set(SIEVE_MINIMUM_DIMENSION) == set(BasisFamily)


@pytest.mark.parametrize("family", list(BasisFamily), ids=str)
def test_every_family_spans_the_constant_from_its_first_column(family):
    """The invariant a multi-term design rests on.

    Not "the constant is in the span" but "it is in the span with a
    non-zero coefficient on column 0" — the design drops each term's FIRST
    column and restores one constant for the whole, and that is only
    lossless while the dropped column is recoverable from what is left
    plus the constant.
    """
    column = np.random.default_rng(4).standard_normal(3000)
    dimension = _widest(family)
    design = _fit_basis(column, "w", family, dimension).evaluate(column)

    assert design.shape[1] == dimension, "a family owes the width it was asked"
    coefficients, *_ = np.linalg.lstsq(design, np.ones(len(column)), rcond=None)
    assert np.abs(design @ coefficients - 1.0).max() < 1e-10
    assert abs(coefficients[0]) > 1e-6


@pytest.mark.parametrize("family", list(BasisFamily), ids=str)
def test_a_family_evaluates_from_its_constants_and_not_from_the_sample(family):
    """Fitting and evaluating are two steps for a reason: the bootstrap
    re-fits per draw and the verifier re-derives from a record. A basis
    that reached for the sample at evaluation time would be a different
    basis in each, and nothing downstream would say so."""
    rng = np.random.default_rng(9)
    fitted = _fit_basis(rng.standard_normal(3000), "w", family,
                        _widest(family))
    somewhere_else = rng.standard_normal(50) * 3 + 1
    first = fitted.evaluate(somewhere_else)
    second = fitted.evaluate(somewhere_else)
    assert np.array_equal(first, second)
    assert np.isfinite(first).all(), "evaluated outside the fitted range"


# --- what the orthogonal family buys -------------------------------------------

def _gram_condition(family: BasisFamily, dimension: int) -> float:
    column = np.random.default_rng(11).standard_normal(4000)
    design = _fit_basis(column, "w", family, dimension).evaluate(column)
    return float(np.linalg.cond(design.T @ design / len(column)))


@pytest.mark.parametrize("dimension", [6, 8, 10, 12])
def test_hermite_conditions_the_same_span_far_better(dimension):
    """Why a second polynomial family is not a duplicate.

    Hermite and the raw powers span the SAME functions at the same degree.
    What differs is the matrix: the normalised Hermite family is
    orthonormal under the standard normal weight, so a bell-shaped column
    gives a Gram near the identity where powers give a Vandermonde. On an
    ILL-POSED problem that is not tidiness — the condition number is the
    ill-posedness made numeric, and it is what the estimator refuses on.
    """
    powers = _gram_condition(BasisFamily.POLYNOMIAL, dimension)
    hermite = _gram_condition(BasisFamily.HERMITE, dimension)
    assert hermite < powers / 100, (powers, hermite)


# --- the programs the families are declared through ----------------------------

def _atom(p):
    return {"predicate": p, "args": []}


def _factor(variable, basis, dimension):
    return {"variable": _atom(variable), "basis": basis,
            "dimension": dimension}


def _program(*, w_basis, w_dimension, z_basis, z_dimension):
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "scale": "continuous"},
            {"kind": "variable", "predicate": "u"},
            {"kind": "variable", "predicate": "z", "scale": "continuous"},
            {"kind": "variable", "predicate": "w", "scale": "continuous"},
            {"kind": "cause", "from": _atom("u"), "to": _atom("x")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("z")},
            {"kind": "cause", "from": _atom("u"), "to": _atom("w")},
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect", "treatment": _atom("x"),
                "outcome": _atom("y"), "latent": _atom("u"),
                "treatment_proxy": [_atom("z")],
                "outcome_proxy": [_atom("w")],
                "channel": {
                    "kind": "bridge_channel",
                    "outcome_bridge": {
                        "span_terms": [
                            {"factors": [_factor("w", w_basis, w_dimension)]}],
                        "moment_terms": [
                            {"factors": [_factor("z", z_basis, z_dimension)]}],
                    },
                }}},
        ],
    }


def _same(basis, dimension):
    return _program(w_basis=basis, w_dimension=dimension,
                    z_basis=basis, z_dimension=dimension + 2)


def _answer(program, frame):
    out = themis.estimate(program, frame, ci_bootstrap=0)["results"][0]
    if out["status"] != "numerically_solved":
        return (out.get("estimator_failure") or {}).get("failure_type")
    return out["numeric_estimate"]["point"]


@pytest.fixture(scope="module")
def bell_frame() -> pd.DataFrame:
    """An ordinary continuous-proxy problem — nothing periodic, nothing
    kinked. What varies across the tests using it is only the sieve."""
    rng = np.random.default_rng(3)
    n = 6000
    u = rng.standard_normal(n)
    x = rng.random(n) < 1 / (1 + np.exp(-1.1 * u))
    return pd.DataFrame({
        "x": x,
        "y": BETA * x + np.sin(1.4 * u) + 0.6 * u
             + 0.25 * rng.standard_normal(n),
        "z": 1.3 * u + 0.3 * rng.standard_normal(n),
        "w": 1.0 * u + 0.3 * rng.standard_normal(n),
    })


def test_the_orthogonal_family_answers_where_raw_powers_give_out(bell_frame):
    """The conditioning gap, as the thing a caller would notice.

    At this width the design of raw powers is singular to working
    precision and the estimator refuses it — correctly, since a solve
    there would be reporting rounding. The same span in the orthogonal
    family is still invertible and the question gets an answer.
    """
    assert _answer(_same("polynomial", 12), bell_frame) == "singular_design"
    assert isinstance(_answer(_same("hermite", 12), bell_frame), float)


# --- what the periodic family buys ---------------------------------------------

@pytest.fixture(scope="module")
def periodic_frame() -> pd.DataFrame:
    """The confounder is a PHASE and both proxies read it as one.

    ``u`` is an angle on [0, 2π) and everything reading it reads it through
    a periodic function, so a bridge in ``w`` has to arrive back where it
    started. A low-degree polynomial cannot: its two ends are free.
    """
    rng = np.random.default_rng(5)
    n = 8000
    phase = rng.uniform(0, 2 * np.pi, n)
    signal = np.sin(phase)
    x = rng.random(n) < 1 / (1 + np.exp(-1.6 * signal))
    return pd.DataFrame({
        "x": x,
        "y": BETA * x + 1.5 * signal + 0.25 * rng.standard_normal(n),
        "z": np.mod(phase + 0.15 * rng.standard_normal(n), 2 * np.pi),
        "w": np.mod(phase + 0.15 * rng.standard_normal(n), 2 * np.pi),
    })


def test_a_periodic_proxy_is_reached_in_three_columns_not_five(periodic_frame):
    """Declaring the periodic family is asserting something TRUE here, and
    the assertion is worth columns: at a width of three the harmonics are
    already at the answer while the powers are a sixth of the effect above
    it. Fewer columns for the same span is a better conditioned inverse,
    which is the currency an ill-posed problem is paid in."""
    fourier = _answer(_same("fourier", 3), periodic_frame)
    powers = _answer(_same("polynomial", 3), periodic_frame)

    assert abs(fourier - BETA) < 0.05, fourier
    assert abs(powers - BETA) > 0.15, powers


# --- what the spline trades ----------------------------------------------------

def _best_fit_error(family: BasisFamily, dimension: int, target) -> float:
    """How far the closest member of this span is from a known function.

    Approximation alone — no estimator, no data-generating process — so
    what is compared is the SPANS, which is what a caller declaring a
    family is choosing between.
    """
    column = np.random.default_rng(11).standard_normal(4000)
    design = _fit_basis(column, "w", family, dimension).evaluate(column)
    wanted = target(column)
    coefficients, *_ = np.linalg.lstsq(design, wanted, rcond=None)
    return float(np.sqrt(np.mean((design @ coefficients - wanted) ** 2)))


def test_the_spline_is_a_trade_against_the_hats_and_not_an_upgrade():
    """Both directions, because only one of them was expected.

    On a SMOOTH target the cubic span is several times closer at the same
    width — the reason to have it. On a KINKED one the hats win, because a
    corner is in their span exactly and a cubic can only round it. A
    vocabulary that offered the spline as strictly better would be
    inviting the second case to be answered with the first case's family.
    """
    smooth = (lambda t: np.sin(1.4 * t) + 0.6 * t)
    kinked = np.abs

    hats_smooth = _best_fit_error(BasisFamily.PIECEWISE_LINEAR, 10, smooth)
    spline_smooth = _best_fit_error(BasisFamily.CUBIC_SPLINE, 10, smooth)
    assert spline_smooth < hats_smooth / 3, (hats_smooth, spline_smooth)

    hats_kinked = _best_fit_error(BasisFamily.PIECEWISE_LINEAR, 10, kinked)
    spline_kinked = _best_fit_error(BasisFamily.CUBIC_SPLINE, 10, kinked)
    assert hats_kinked < spline_kinked, (hats_kinked, spline_kinked)


def test_the_hats_are_better_conditioned_than_the_spline():
    """The other half of the same trade, and the half that decides it when
    the bridge could be either: smoothness costs conditioning, and on an
    ill-posed problem conditioning is what runs out first."""
    for dimension in (6, 10, 16):
        hats = _gram_condition(BasisFamily.PIECEWISE_LINEAR, dimension)
        spline = _gram_condition(BasisFamily.CUBIC_SPLINE, dimension)
        assert hats < spline, (dimension, hats, spline)


def test_a_cubic_spline_narrower_than_its_degree_is_refused():
    """The counterexample the minimum exists for.

    Below four functions a clamped cubic knot vector has no room for the
    degree, so what would be built is not the family that was named. The
    door says so; the alternative is an estimator quietly handing back
    some other span under the declared family's name.
    """
    with pytest.raises(SemanticError) as raised:
        themis.run(_program(w_basis="cubic_spline", w_dimension=3,
                            z_basis="polynomial", z_dimension=5))
    assert raised.value.species is Malformed.SIEVE_BASIS_TOO_NARROW
    assert raised.value.details["minimum"] == 4
    assert raised.value.details["dimension"] == 3


def test_the_families_with_no_minimum_take_the_narrowest_sieve(bell_frame):
    """The twin. Two columns is a real sieve for four of the five, and a
    minimum applied to all of them would be the gate above overreaching."""
    for family in BasisFamily:
        if SIEVE_MINIMUM_DIMENSION[family] > 2:
            continue
        assert isinstance(_answer(_same(str(family), 2), bell_frame), float), (
            family)


# --- every family goes the whole way ------------------------------------------

@pytest.mark.parametrize("family", list(BasisFamily), ids=str)
def test_a_declared_family_survives_the_round_trip(family, bell_frame):
    """Parse, run, re-derive, and say so — for each member rather than for
    the one the fixtures happen to use. A family that only the estimator
    knows about is a family the verifier cannot re-derive and the reader
    is handed the token of."""
    program = _same(str(family), _widest(family))
    answered = themis.estimate(program, bell_frame, ci_bootstrap=0)["results"][0]
    assert answered["status"] == "numerically_solved"

    themis.verify(program, answered)

    for lang in ("zh", "en"):
        report = themis.build_analysis_report(answered, lang=lang)
        assert "bridge" in report
        # The family reaches the reader through its own gloss in their
        # language, which is what a generated table is generated for. Not
        # "the token is absent": the English gloss for the powers IS the
        # token, and a test written that way would be pinning a coincidence
        # of English rather than the rule.
        assert _BASIS_WORDS[str(family)][lang].strip() in report, (
            lang, family)
