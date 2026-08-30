"""#474 — the widening factor is a number the declared variance decides.

Two blocks price somebody ELSE's interval rather than reporting one. A
declared measurement variance takes a share of the residual, and every
least-squares interval on that design is wider by ``1/√(1−share)`` —
:mod:`themis.estimation.outcome_error` on the outcome's channel,
:mod:`themis.estimation.berkson` on the exposure's. Both printed ONE number
for that factor whatever the variance behind it was worth knowing.

Where a validation study measured it, σ² = σ̂²·df/X with X ~ χ²_df makes the
factor ``1/√(1 − share·df/X)`` — monotone in X, so its endpoints are exact
quantiles and nothing here needs a simulation or a grid. And the guard both
modules already have at the declared value becomes a probability: the share
of the study at which the declared noise would take the whole residual is
``χ²_df.cdf(df·share)``. Once that reaches the tail an endpoint stands for,
the factor is bounded below and not above — and a finite ceiling there would
be a bound the study does not supply.

Measured on one frame, the same block, σ̂²_v held fixed: the factor is 1.19
throughout, and its interval goes [1.16, 1.23] at df=400, [1.10, 1.52] at
df=24, [1.08, 7.36] at df=9, and [1.06, no ceiling] at df=4. A reader shown
only "1.19" at df=9 has been told a widening is a fifth when the study
behind it allows seven-fold.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from themis.estimation.berkson import assess_berkson_error
from themis.estimation.dispatch import _berkson_block, _outcome_error_block
from themis.estimation.outcome_error import assess_outcome_error
from themis.estimation.resample import DeclaredVariance
from themis.output.analysis_report import build_analysis_report
from themis.refusals import Refusal
from themis.verifier.berkson_rules import verify_berkson_error
from themis.verifier.errors import VerificationError
from themis.verifier.inflation_rules import check_inflation_under_a_study
from themis.verifier.outcome_error_rules import verify_outcome_error

SIGMA2_V = 0.3
SIGMA2_U = 0.5
BETA_X = 0.8


def _outcome_frame(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 1, n)
    y = BETA_X * x + 0.4 * z + rng.normal(0, 1, n)
    return pd.DataFrame({"x": x, "y": y, "z": z})


def _berkson_frame(n=20_000, seed=0, sigma2_u=SIGMA2_U):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    w = 0.6 * z + rng.normal(0, 1, n)
    x_true = w + rng.normal(0, np.sqrt(sigma2_u), n)
    y = 1.0 + BETA_X * x_true + 0.4 * z + rng.normal(0, 1.0, n)
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _declared(value, df):
    return value if df is None else {"error_variance": value,
                                     "validation_df": df}


def _outcome(df, frame=None):
    return assess_outcome_error(
        _outcome_frame() if frame is None else frame,
        treatment="x", outcome="y", adjustment=("z",),
        error_variance=_declared(SIGMA2_V, df))


def _slope(frame):
    design = np.column_stack([np.ones(len(frame)),
                              frame["w"].to_numpy(float),
                              frame["z"].to_numpy(float)])
    return float(np.linalg.lstsq(design, frame["y"].to_numpy(float),
                                 rcond=None)[0][1])


def _berkson(df, frame=None):
    frame = _berkson_frame() if frame is None else frame
    return assess_berkson_error(
        frame, treatment="w", outcome="y", adjustment=("z",),
        treatment_coefficient=_slope(frame),
        error_variance=_declared(SIGMA2_U, df))


_ROUTES = {"outcome_error": _outcome, "berkson_error": _berkson}


# ============================================ the factor gets a spread


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_the_factor_is_one_number_and_the_study_gives_it_a_width(route):
    """The point factor is the same either way: saying how well the variance
    is known prices a second source of uncertainty and moves no estimate."""
    assess = _ROUTES[route]
    exact, measured = assess(None), assess(24)
    assert measured.se_inflation == exact.se_inflation
    assert measured.noise_share == exact.noise_share
    assert exact.se_inflation_lower is None
    assert measured.se_inflation_lower < measured.se_inflation
    assert measured.se_inflation_upper > measured.se_inflation


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_the_less_the_study_pinned_it_down_the_wider_the_factor(route):
    """And without the declaration all of these are the same one number."""
    assess = _ROUTES[route]
    widths = [assess(df).se_inflation_upper - assess(df).se_inflation_lower
              for df in (400, 100, 24)]
    assert widths == sorted(widths)
    assert len({assess(df).se_inflation for df in (400, 100, 24)}) == 1


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_a_study_too_small_to_bound_the_widening_says_so(route):
    """The ceiling is absent for a reason the reader acts on: the study puts
    at least the tail an endpoint stands for on a variance the residual
    cannot hold, which is the case both modules already refuse outright at
    the declared value."""
    est = _ROUTES[route](4)
    assert est.se_inflation_lower is not None
    assert est.se_inflation_upper is None
    assert est.inflation_refuted_share >= 0.025


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_the_refuted_share_is_the_probability_and_not_a_search(route):
    """χ²_df.cdf(df·share) in closed form — a property of the study and this
    residual, not of any grid or draw."""
    est = _ROUTES[route](9)
    assert est.inflation_refuted_share == pytest.approx(
        float(stats.chi2.cdf(9 * est.noise_share, 9)), rel=1e-12)


@pytest.mark.parametrize("route", sorted(_ROUTES))
def test_no_study_is_not_a_study_that_found_nothing(route):
    """All four fields absent together. A zero refuted share would tell every
    reader about a study nobody ran."""
    est = _ROUTES[route](None)
    assert (est.validation_df, est.se_inflation_lower,
            est.se_inflation_upper, est.inflation_refuted_share) == (
        None, None, None, None)


def test_both_channels_are_one_formula_on_a_different_share():
    """The exposure channel scales the declared variance by βx² before it
    becomes a share, and after that the two are the same arithmetic — which
    is why the branch lives on the declaration and not in either module."""
    berkson = _berkson(24)
    declared = DeclaredVariance(value=SIGMA2_V, validation_df=24)
    lower, upper, refuted = declared.inflation_interval(
        berkson.noise_share, ci_level=0.95)
    assert (lower, upper, refuted) == (
        berkson.se_inflation_lower, berkson.se_inflation_upper,
        berkson.inflation_refuted_share)
    # The value of σ² itself does not enter: the share already carries it.
    assert declared.value != berkson.error_variance


def test_the_endpoints_are_the_quantiles_of_the_studys_own_chi_square():
    """Written out here rather than compared to the producer's own routine,
    because the claim is what the endpoints ARE."""
    est = _outcome(24)
    share, df = est.noise_share, 24
    for endpoint, p in ((est.se_inflation_lower, 0.975),
                        (est.se_inflation_upper, 0.025)):
        x = float(stats.chi2.ppf(p, df))
        assert endpoint == pytest.approx(
            1.0 / np.sqrt(1.0 - share * df / x), rel=1e-12)


def test_the_species_for_a_route_that_could_not_carry_it_is_gone():
    """It was minted for the three routes whose interval is not a bootstrap,
    and every one of them turned out to carry the study another way."""
    assert not hasattr(Refusal, "VALIDATION_DF_NOT_CARRIED_HERE")
    assert not hasattr(DeclaredVariance, "refuse_if_not_carried")


# ============================================ what the gate says no to


#: What every envelope here carries besides the block under audit — the
#: report reads the question before it reads anything else.
_ANSWERED = {"query_id": "q", "query_kind": "effect",
             "status": "numerically_solved"}


def _outcome_envelope(est) -> dict:
    return {
        **_ANSWERED,
        "outcome_error": _outcome_error_block(est, source=None),
        "numeric_estimate": {
            "method": "backdoor_linear", "point": BETA_X, "ci_level": 0.95,
            "treatment": "x", "outcome": "y", "adjustment": ["z"],
            "sample_size": est.sample_size, "data_hash": est.data_hash,
            "data_columns": list(est.data_columns),
        },
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in est.assumptions]}},
    }


def _berkson_envelope(est) -> dict:
    return {
        **_ANSWERED,
        "numeric_estimate": {
            "method": "backdoor_linear",
            "point": est.treatment_coefficient, "ci_level": 0.95,
            "assumptions": [], "sample_size": est.sample_size,
            "data_hash": est.data_hash,
            "data_columns": list(est.data_columns),
        },
        "berkson_error": _berkson_block(est),
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in est.assumptions]}},
    }


_AUDITS = {
    "outcome_error": (lambda df: _outcome_envelope(_outcome(df)),
                      verify_outcome_error, "outcome_error"),
    "berkson_error": (lambda df: _berkson_envelope(_berkson(df)),
                      verify_berkson_error, "berkson_error"),
}

FORGERIES = {
    "a moved lower endpoint":
        lambda b: b.__setitem__("se_inflation_lower",
                                b["se_inflation_lower"] - 0.01),
    "a moved upper endpoint":
        lambda b: b.__setitem__("se_inflation_upper",
                                b["se_inflation_upper"] + 0.01),
    "a study inflated after the fact":
        lambda b: b.__setitem__("validation_df", 400),
    "a study denied after the fact":
        lambda b: b.__setitem__("validation_df", None),
    "a refuted share that is not the one the record implies":
        lambda b: b.__setitem__("inflation_refuted_share", 0.2),
    "a df that is not a df": lambda b: b.__setitem__("validation_df", 0),
}


@pytest.mark.parametrize("route", sorted(_AUDITS))
@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_tampered_factor_interval_is_rejected(route, name):
    import copy

    build, audit, key = _AUDITS[route]
    honest = build(24)
    audit(honest)                     # the same record, unaltered, passes
    forged = copy.deepcopy(honest)
    FORGERIES[name](forged[key])
    with pytest.raises(VerificationError):
        audit(forged)


@pytest.mark.parametrize("route", sorted(_AUDITS))
def test_a_ceiling_the_study_does_not_supply_is_rejected(route):
    """The one forgery that leaves every other number here consistent, and
    the one a reader cannot see: [1.06, 7.4] and [1.06, ∞) share a first
    number."""
    import copy

    build, audit, key = _AUDITS[route]
    honest = build(4)
    audit(honest)
    assert honest[key]["se_inflation_upper"] is None
    forged = copy.deepcopy(honest)
    forged[key]["se_inflation_upper"] = 7.4
    with pytest.raises(VerificationError, match="ceiling"):
        audit(forged)


@pytest.mark.parametrize("route", sorted(_AUDITS))
def test_a_spread_where_no_study_was_declared_is_rejected(route):
    """A widening priced on a variance nobody measured has no distribution
    to have quantiles of."""
    import copy

    build, audit, key = _AUDITS[route]
    honest = build(None)
    audit(honest)
    forged = copy.deepcopy(honest)
    forged[key]["se_inflation_lower"] = 1.05
    with pytest.raises(VerificationError, match="no validation study"):
        audit(forged)


def test_the_audit_re_derives_the_share_rather_than_reading_it():
    """The caller hands in the share IT recomputed from the block's own
    moments, so a producer that agreed with itself about a wrong share is
    still caught."""
    block = dict(validation_df=9, se_inflation_lower=1.0,
                 se_inflation_upper=None, inflation_refuted_share=0.5)
    with pytest.raises(VerificationError, match="inflation_refuted_share"):
        check_inflation_under_a_study(
            block, where="somewhere", rule="r", noise_share=0.05)


# ============================================ the reader is told


@pytest.mark.parametrize("route", sorted(_AUDITS))
def test_the_report_says_the_factor_has_a_spread(route):
    build, _, key = _AUDITS[route]
    text = build_analysis_report(build(24))
    assert "24 个自由度" in text and "那个倍数本身" in text

    unbounded = build_analysis_report(build(4))
    assert "上面没有边" in unbounded

    plain = build_analysis_report(build(None))
    assert "自由度" not in plain
    for token in ("se_inflation_lower", "inflation_refuted_share"):
        assert token not in text and token not in unbounded
