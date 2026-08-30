"""Unit tests for the outcome measurement-error audit, over all three designs.

The audit's problem is that one block of numbers now describes three different
models. Nothing in Σ_D, Cov(D, Y) or Var(Y) says which — the same moments admit
a residual around a fitted projection and a residual around a coefficient that
arrived from outside, and those are different numbers about different models.
So every test here is built the same way: take an honest assessment, change one
thing, and check that the audit's answer changes with it.

The two failure shapes worth naming, because both look like success:

- an envelope whose arithmetic is internally perfect around a coefficient
  vector that is not the one its design fixes. Repricing every reported scalar
  off the tampered statistics silences the arithmetic gate entirely, and what
  is left is the only gate that can see it.
- a cross-check that reads a key its route never writes. It finds nothing,
  raises nothing, and is indistinguishable downstream from a check that ran and
  passed.
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator

from themis.estimation import OutcomeErrorDesign, assess_outcome_error
from themis.verifier import VerificationError, verify_outcome_error
from themis.input.syntactic_validator import validator_for


def _outcome_error_validator() -> Draft202012Validator:
    """The ``outcome_error`` subtree, still anchored in its own document.

    Evolved rather than lifted out: a fragment prised loose keeps whatever
    references it contains but loses the base they resolve against.
    """
    whole = validator_for("query_result.schema.json")
    return whole.evolve(schema=whole.schema["properties"]["outcome_error"])

_BACK_DOOR = str(OutcomeErrorDesign.BACK_DOOR)
_IV = str(OutcomeErrorDesign.INSTRUMENTAL_VARIABLE)
_FRONT_DOOR = str(OutcomeErrorDesign.FRONT_DOOR)


# --- one frame per design, each valid for the design it feeds -----------------


def _back_door_frame(n=4000, seed=7, sv2=2.0):
    rng = np.random.default_rng(seed)
    z = rng.standard_normal(n)
    x = 0.5 * z + rng.standard_normal(n)
    ystar = 0.8 * x + z + rng.standard_normal(n)
    return pd.DataFrame({"x": x, "z": z,
                         "y": ystar + rng.normal(0, np.sqrt(sv2), n)})


def _iv_frame(n=4000, seed=11, sv2=4.0):
    """z → x → y with an unmeasured u into both, plus one covariate the answer
    conditions on — so the design has a nuisance coefficient to re-solve."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    z = rng.standard_normal(n)
    x = 0.8 * z + u + rng.standard_normal(n)
    w = rng.standard_normal(n)
    ystar = 0.8 * x + 2.0 * u + 0.5 * w + rng.standard_normal(n)
    return pd.DataFrame({"x": x, "z": z, "w": w,
                         "y": ystar + rng.normal(0, np.sqrt(sv2), n)})


def _front_door_frame(n=6000, seed=13, sv2=0.25):
    """x → m → y with x ↔ y latent and a THREE-level mediator, so the design
    carries indicators rather than the raw column."""
    rng = np.random.default_rng(seed)
    u = rng.standard_normal(n)
    x = (rng.random(n) < 1 / (1 + np.exp(-u))).astype(float)
    m = np.where(rng.random(n) < 0.3 + 0.4 * x, 2.0,
                 np.where(rng.random(n) < 0.5, 1.0, 0.0))
    ystar = 3.0 * (m == 2.0) + 2.0 * u + rng.standard_normal(n)
    return pd.DataFrame({"x": x, "m": m,
                         "y": ystar + rng.normal(0, np.sqrt(sv2), n)})


def _wald(df):
    return float(np.cov(df["z"], df["y"])[0, 1] / np.cov(df["z"], df["x"])[0, 1])


@lru_cache(maxsize=None)
def _assessed(kind: str):
    """One honest assessment per design."""
    if kind == _BACK_DOOR:
        return assess_outcome_error(
            _back_door_frame(), treatment="x", outcome="y",
            adjustment=("z",), error_variance=2.0,
        )
    if kind == _IV:
        df = _iv_frame()
        return assess_outcome_error(
            df, treatment="x", outcome="y", design_kind=_IV,
            adjustment=("w",), instruments=("z",),
            treatment_coefficient=_wald(df), error_variance=4.0,
        )
    return assess_outcome_error(
        _front_door_frame(), treatment="x", outcome="y",
        design_kind=_FRONT_DOOR, mediators=("m",), error_variance=0.25,
    )


# --- the envelope, built the way dispatch builds it ---------------------------


def _block(kind: str) -> dict:
    a = _assessed(kind)
    return copy.deepcopy({
        "outcome": a.outcome,
        "treatment": a.treatment,
        "design_kind": str(a.design_kind),
        "design_vars": list(a.design_vars),
        "error_variance": a.error_variance,
        "residual_variance": a.residual_variance,
        "signal_variance": a.signal_variance,
        "noise_share": a.noise_share,
        "se_inflation": a.se_inflation,
        # Null in this fixture: nobody said a study measured σ²_v, and the
        # four keys are what the block says about the one that did.
        "validation_df": a.validation_df,
        "se_inflation_lower": a.se_inflation_lower,
        "se_inflation_upper": a.se_inflation_upper,
        "inflation_refuted_share": a.inflation_refuted_share,
        "sample_size": a.sample_size,
        "data_hash": a.data_hash,
        "data_columns": list(a.data_columns),
        "assumptions": list(a.assumptions),
        "sufficient_statistics": a.sufficient_statistics,
        "source": None,
    })


# What each route's answer records about the columns it used, under the key
# that route writes and no other.
_NUMERIC = {
    _BACK_DOOR: {"outcome": "y", "adjustment": ["z"]},
    _IV: {"outcome": "y", "instrument": "z", "conditioning": ["w"]},
    _FRONT_DOOR: {"outcome": "y", "mediators": ["m"]},
}


def _result(block: dict, numeric: dict | None = None) -> dict:
    """The block beside an answer, with its premises on the ledger.

    The ledger is built from whatever the block declares, so a test that
    rewrites the premises is testing the premise rule rather than tripping the
    disclosure rule on its way past.
    """
    if numeric is None:
        numeric = copy.deepcopy(_NUMERIC[block["design_kind"]])
    return {
        "outcome_error": block,
        "numeric_estimate": numeric,
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in block["assumptions"]],
        }},
    }


def _reprice(block: dict) -> dict:
    """Make every reported scalar follow from the block's own statistics again.

    Used after tampering with the moments or the coefficients: it silences the
    arithmetic gate, so whatever the audit rejects afterwards is rejected by
    the rule under test and not by a number left stale.
    """
    s = block["sufficient_statistics"]
    Sigma = np.array(s["cov_matrix"])
    c = np.array(s["cov_design_y"])
    b = np.array(s["design_coefficients"])
    residual = float(s["var_y"] - 2.0 * (b @ c) + b @ Sigma @ b)
    sigma_v = float(s["error_variance"])
    block["residual_variance"] = residual
    block["signal_variance"] = residual - sigma_v
    block["noise_share"] = sigma_v / residual
    block["se_inflation"] = float(np.sqrt(residual / (residual - sigma_v)))
    return block


_KINDS = [_BACK_DOOR, _IV, _FRONT_DOOR]


# --- what must pass -----------------------------------------------------------


@pytest.mark.parametrize("kind", _KINDS)
def test_an_honest_assessment_passes_on_every_design(kind):
    verify_outcome_error(_result(_block(kind)))


@pytest.mark.parametrize("kind", _KINDS)
def test_the_block_each_design_produces_is_the_block_the_schema_admits(kind):
    _outcome_error_validator().validate(_block(kind))


def test_the_supplied_coefficient_is_held_where_the_caller_put_it():
    """The IV route's residual is the STRUCTURAL one, and the audit has to
    confirm it as such: re-solving the exposure's coefficient would produce the
    OLS slope, which on this frame is a materially different number, and every
    honest instrumental assessment would be rejected for not matching it."""
    block = _block(_IV)
    s = block["sufficient_statistics"]
    Sigma = np.array(s["cov_matrix"])
    c = np.array(s["cov_design_y"])
    ols = np.linalg.solve(Sigma, c)
    assert abs(s["design_coefficients"][0] - ols[0]) > 0.1
    closed_form = float(s["var_y"] - c @ ols)
    assert block["residual_variance"] > closed_form + 0.1
    verify_outcome_error(_result(block))


# --- which residual these numbers are ----------------------------------------


def test_a_block_that_does_not_say_which_residual_it_took_is_refused():
    """Every scalar in the block means something different under each design,
    so the name is not a label on the numbers — it is what they are."""
    block = _block(_BACK_DOOR)
    del block["design_kind"]
    with pytest.raises(VerificationError, match="design_kind"):
        verify_outcome_error(_result(block, copy.deepcopy(_NUMERIC[_BACK_DOOR])))


def test_a_design_outside_the_vocabulary_is_refused_with_the_vocabulary_named():
    block = _block(_IV)
    block["design_kind"] = "two_stage_least_squares"
    with pytest.raises(VerificationError) as exc:
        verify_outcome_error(_result(block, copy.deepcopy(_NUMERIC[_IV])))
    assert "instrumental_variable" in str(exc.value)


# --- the coefficients the design fixes ----------------------------------------


def test_a_nuisance_coefficient_that_is_not_the_designs_is_refused():
    """The counterexample the arithmetic gate cannot see. Moving the covariate's
    coefficient off the fit and then repricing every scalar around it leaves an
    envelope that is internally exact — Var(Y − b'D) really is what it says —
    and describes a model the design does not admit."""
    block = _block(_IV)
    block["sufficient_statistics"]["design_coefficients"][1] += 0.4
    _reprice(block)
    with pytest.raises(VerificationError, match="design_coefficients"):
        verify_outcome_error(_result(block))


def test_the_exposures_coefficient_is_free_only_where_the_design_says_so():
    """The mirror of the test above: the same tamper on the back-door route's
    exposure, where no coefficient comes from outside and all of them are the
    normal equations' answer."""
    block = _block(_BACK_DOOR)
    block["sufficient_statistics"]["design_coefficients"][0] += 0.4
    _reprice(block)
    with pytest.raises(VerificationError, match="design_coefficients"):
        verify_outcome_error(_result(block))


@pytest.mark.parametrize("kind", _KINDS)
def test_a_coefficient_vector_of_the_wrong_width_is_not_this_design(kind):
    """A vector one entry short is not a rounding disagreement; it is a
    different design, and the quadratic form would return a plausible number
    for it."""
    block = _block(kind)
    block["sufficient_statistics"]["design_coefficients"].pop()
    with pytest.raises(VerificationError, match="dimension"):
        verify_outcome_error(_result(block))


def test_a_design_whose_fit_does_not_exist_is_refused():
    """The elimination still earns its keep on the OLS routes: with two
    collinear columns there is no fit for the residual to be a variance
    around, and the coefficients recorded cannot be the design's."""
    block = _block(_BACK_DOOR)
    s = block["sufficient_statistics"]
    s["cov_matrix"] = [[1.0, 1.0], [1.0, 1.0]]
    s["cov_design_y"] = [1.0, 1.0]
    s["var_y"] = 6.0
    _reprice(block)
    with pytest.raises(VerificationError, match="singular"):
        verify_outcome_error(_result(block))


def test_where_the_design_is_only_the_supplied_coefficient_the_arithmetic_stands_alone():
    """The instrumental limit case: with no covariates every entry of b came
    from outside, so no normal equation is left to re-solve and the residual
    around it is the whole of what can be confirmed — which it still is."""
    df = _iv_frame()
    a = assess_outcome_error(
        df, treatment="x", outcome="y", design_kind=_IV,
        instruments=("z",), treatment_coefficient=_wald(df), error_variance=4.0,
    )
    block = copy.deepcopy({
        "outcome": a.outcome, "treatment": a.treatment,
        "design_kind": str(a.design_kind), "design_vars": list(a.design_vars),
        "error_variance": a.error_variance,
        "residual_variance": a.residual_variance,
        "signal_variance": a.signal_variance,
        "noise_share": a.noise_share, "se_inflation": a.se_inflation,
        "sample_size": a.sample_size, "data_hash": a.data_hash,
        "assumptions": list(a.assumptions),
        "sufficient_statistics": a.sufficient_statistics, "source": None,
    })
    assert block["design_vars"] == ["x"]
    numeric = {"outcome": "y", "instrument": "z", "conditioning": []}
    verify_outcome_error(_result(block, numeric))
    block["se_inflation"] *= 1.2
    with pytest.raises(VerificationError, match="se_inflation"):
        verify_outcome_error(_result(block, dict(numeric)))


def test_a_covariance_matrix_that_is_not_square_is_not_one():
    block = _block(_BACK_DOOR)
    block["sufficient_statistics"]["cov_matrix"][0].pop()
    with pytest.raises(VerificationError, match="covariance matrix"):
        verify_outcome_error(_result(block))


def test_a_moment_that_is_not_a_number_is_refused_rather_than_crashing():
    block = _block(_BACK_DOOR)
    block["sufficient_statistics"]["cov_matrix"][0][0] = "3.0"
    with pytest.raises(VerificationError):
        verify_outcome_error(_result(block))


# --- the design assessed against the design answered on -----------------------


def test_the_key_the_route_writes_is_the_key_the_cross_check_reads():
    """The silent no-op this replaces: the instrumental answer records its
    conditioning set under ``conditioning`` and never under ``adjustment``, so
    a guard fixed on the latter found nothing, raised nothing, and read
    downstream exactly like a guard that ran."""
    block = _block(_IV)
    numeric = {"outcome": "y", "instrument": "z", "conditioning": ["not_w"]}
    with pytest.raises(VerificationError, match="conditioning"):
        verify_outcome_error(_result(block, numeric))


def test_an_answer_that_does_not_say_which_columns_it_used_is_refused():
    """And the other half: the key absent altogether. Nothing here can be
    confirmed, which is a refusal rather than a pass — including when the
    answer carries some OTHER route's key."""
    block = _block(_IV)
    numeric = {"outcome": "y", "adjustment": ["w"]}
    with pytest.raises(VerificationError, match="conditioning"):
        verify_outcome_error(_result(block, numeric))


def test_the_front_door_design_is_matched_through_the_indicators_it_carries():
    """The front-door design carries the mediator expanded into drop-first
    indicators, and the answer names the raw variable — so the two are compared
    through the expansion rather than as sets of names."""
    block = _block(_FRONT_DOOR)
    assert "m=2.0" in block["design_vars"] and "m" not in block["design_vars"]
    verify_outcome_error(_result(block))
    numeric = {"outcome": "y", "mediators": ["m", "other"]}
    with pytest.raises(VerificationError, match="mediators"):
        verify_outcome_error(_result(block, numeric))


# --- the premises each design owes --------------------------------------------


def test_the_front_door_premise_about_the_latent_confounder_cannot_be_dropped():
    """It is the one premise whose failure moves the POINT rather than the
    interval, and it is about a variable no data can speak for — so a block
    that quietly stops declaring it is the case that most needs catching."""
    block = _block(_FRONT_DOOR)
    block["assumptions"] = [
        a for a in block["assumptions"] if "latent_confounder" not in a
    ]
    with pytest.raises(VerificationError, match="latent_confounder"):
        verify_outcome_error(_result(block))


def test_the_instrumental_route_may_not_borrow_the_classical_premise():
    """E[V | X, W] = 0 is neither necessary nor sufficient for the immunity the
    instrumental route claims, so declaring it there tells the reader a
    true-looking sentence about the wrong variable while the premise that does
    the work goes unsaid."""
    block = _block(_IV)
    block["assumptions"] = [
        "outcome_error_classical_non_differential_on_y",
        "outcome_error_variance_known_and_fixed_on_y",
    ]
    with pytest.raises(VerificationError, match="instrument"):
        verify_outcome_error(_result(block))


@pytest.mark.parametrize("kind", _KINDS)
def test_the_declared_variance_is_a_premise_on_every_design(kind):
    """Every number in the block is arithmetic on a σ²_v nothing here
    estimated, so no design escapes saying so."""
    block = _block(kind)
    block["assumptions"] = [
        a for a in block["assumptions"] if "variance_known_and_fixed" not in a
    ]
    with pytest.raises(VerificationError, match="variance_known_and_fixed"):
        verify_outcome_error(_result(block))


# --- what the schema must refuse ----------------------------------------------


@pytest.mark.parametrize("mutate", [
    pytest.param(lambda b: b.pop("design_kind"), id="no design_kind"),
    pytest.param(lambda b: b.update(design_kind="two_stage_least_squares"),
                 id="a design outside the vocabulary"),
    pytest.param(lambda b: b["sufficient_statistics"].pop("design_coefficients"),
                 id="no design_coefficients"),
])
def test_the_envelope_shape_is_required_of_every_design(mutate):
    """Both new keys are required rather than optional: the name is what the
    numbers mean, and the coefficients are what a reader re-derives them from.
    An envelope free to omit either is an envelope whose block cannot be
    audited at all."""
    block = _block(_FRONT_DOOR)
    mutate(block)
    with pytest.raises(Exception):
        _outcome_error_validator().validate(block)
