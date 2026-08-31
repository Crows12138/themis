# -*- coding: utf-8 -*-
"""δ arrives from a validation regression, and that regression can be wrong.

Every other declaration in this family had a door for the study behind it —
σ²_u redraws from its χ², a confusion matrix from its Dirichlet, and the two
channels that price somebody else's interval read the widening factor's
endpoints off the same χ². δ had none, and the module said so in as many
words: its estimate is a regression coefficient, its sampling distribution is
not a χ², and a second distribution declared through the variance's field
would be one field meaning two things. That was right about the field and
wrong about the conclusion — the answer is a second declaration, not a second
meaning for the first.

**Why the remainder and not the total.** A validation regression of ``W − X*``
on the outcome's residual reports a slope and a residual variance, and under
normality those two are independent. The TOTAL error variance is not
independent of the slope: σ̂²_u = σ̂²_0 + δ̂²·Var(Ỹ) is a function of δ̂ itself,
so a run that redrew (δ̂, σ̂²_u) as though they were separate would understate
its own interval by an amount that vanishes only at δ = 0. Declaring what the
regression printed is what makes the pair's draw exact — and it is also the
shape a caller has, since the total was a number they had to assemble.

**What the study buys is width.** δ enters the correction itself, so a δ that
is systematically wrong moves the point and no interval can rescue it. Its
sampling uncertainty is a different thing and buys a different thing: the
point stays at δ̂ and the interval around it widens.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.differential_error import estimate_differential_error
from themis.estimation.resample import DeclaredTracking
from themis.ledger import Layer
from themis.output import assumption_glossary as glossary
from themis.output.analysis_report import build_analysis_report
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier.differential_error_rules import (
    verify_differential_error_numeric,
)
from themis.verifier.errors import VerificationError

BETA_X = 0.8
DELTA = 0.3
SIGMA2_0 = 0.5
DF = 48
SE = 0.03

EXACT = "differential_coefficient_known_and_fixed_on_w"
STUDIED = "differential_coefficient_from_a_validation_study_on_w"


# --- a frame the correction is exactly right on -------------------------------


def _frame(n=8000, seed=0):
    """W = X* + δ·Ỹ + f — the error carries a component that tracks Y.

    Returns the frame and Var(Ỹ), which is what the total error variance is
    composed with and so what the two declarations differ by.
    """
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + BETA_X * x + 0.4 * z + rng.normal(0, 1, n)
    residual = y - np.polyval(np.polyfit(z, y, 1), z)
    w = x + DELTA * residual + rng.normal(0, np.sqrt(SIGMA2_0), n)
    return (pd.DataFrame({"w": w, "y": y, "z": z}),
            float(np.var(residual, ddof=1)))


FRAME, VAR_Y_RESIDUAL = _frame()
TOTAL = SIGMA2_0 + DELTA * DELTA * VAR_Y_RESIDUAL


def _study(**overrides):
    spec = {"coefficient": DELTA, "standard_error": SE,
            "residual_variance": SIGMA2_0, "validation_df": DF}
    spec.update(overrides)
    return spec


def _run(*, coefficient, variance=..., bootstrap=400, frame=None):
    kwargs = {} if variance is ... else {"error_variance": variance}
    return estimate_differential_error(
        FRAME if frame is None else frame,
        treatment="w", outcome="y", adjustment=("z",),
        differential_by="y", differential_coefficient=coefficient,
        ci_bootstrap=bootstrap, ci_level=0.95, random_state=1, **kwargs)


def _envelope(est) -> dict:
    """The numeric estimate the audit reads, through the producer's block."""
    from themis.estimation.dispatch import _differential_error_block

    return {
        "method": est.method,
        "point": est.point,
        "ci_level": est.ci_level,
        "treatment": est.treatment,
        "outcome": est.outcome,
        "adjustment": list(est.adjustment),
        "sample_size": est.sample_size,
        "assumptions": list(est.assumptions),
        "differential_error": _differential_error_block(est),
    }


def _report(est) -> str:
    """The page, from a result carrying that estimate."""
    return build_analysis_report({
        "status": "numerically_solved",
        "query_kind": "effect",
        "numeric_estimate": _envelope(est),
        "extensions": {"assumption_ledger": {
            "assumptions": [{"id": a} for a in est.assumptions]}},
    })


# --- the point is δ̂'s, and the study buys width -------------------------------


def test_the_three_declarations_agree_on_the_point():
    """Whatever the caller said about how well δ and σ²_u are known, the
    correction is applied at the numbers they declared — so the point is one
    number and only the interval around it moves. A study that shifted the
    point would be reporting a different correction under the same premise."""
    bare = _run(coefficient=DELTA, variance=TOTAL, bootstrap=0)
    studied_variance = _run(
        coefficient=DELTA, bootstrap=0,
        variance={"error_variance": TOTAL, "validation_df": DF})
    studied_delta = _run(coefficient=_study(), bootstrap=0)

    assert bare.point == pytest.approx(BETA_X, abs=0.02)
    assert studied_variance.point == pytest.approx(bare.point, rel=1e-12)
    assert studied_delta.point == pytest.approx(bare.point, rel=1e-9)
    # ...and the split behind it, reached from the other end: the study
    # declares σ²_0 and the total is composed, so the two shapes have to meet
    # on both numbers or they are describing different errors.
    assert studied_delta.error_variance == pytest.approx(TOTAL, rel=1e-9)
    assert studied_delta.nondifferential_variance == pytest.approx(
        SIGMA2_0, rel=1e-9)


def test_a_measured_delta_widens_the_interval_and_a_better_study_widens_it_less():
    """Monotone in what the study says about itself, which is the whole
    content of the claim. A regression with a large standard error leaves δ
    poorly pinned and the interval has to say so; one with a small standard
    error is nearly the fixed-δ case and the interval nearly matches it."""
    fixed = _run(coefficient=DELTA, variance=TOTAL)
    widths = [
        _run(coefficient=_study(standard_error=se)).ci_upper
        - _run(coefficient=_study(standard_error=se)).ci_lower
        for se in (0.01, 0.05, 0.15)
    ]
    assert widths == sorted(widths), widths
    assert widths[0] > (fixed.ci_upper - fixed.ci_lower)


def test_the_shape_of_the_declaration_does_not_move_the_random_stream():
    """A δ declared as a bare number and the same δ declared as a mapping with
    no study are the same claim, and a run must not be able to tell them
    apart: the draw consumes no randomness where there is nothing to draw
    from, which is what keeps every run that declares nothing reproducing."""
    bare = _run(coefficient=DELTA, variance=TOTAL)
    wrapped = _run(coefficient={"coefficient": DELTA}, variance=TOTAL)
    assert wrapped.ci_lower == bare.ci_lower
    assert wrapped.ci_upper == bare.ci_upper


# --- the draw itself ----------------------------------------------------------


def test_the_pair_is_drawn_from_the_regressions_own_law():
    """The claim the declaration rests on, measured rather than asserted.

    Marginally δ* is δ̂ + se·t_df, whose variance is se²·df/(df−2); σ²_0*
    is σ̂²_0·df/χ²_df, whose mean is σ̂²_0·df/(df−2). And the standardised
    slope is independent of the variance it was scaled by — which is the
    property that made the remainder the right thing to declare, so it is
    the property worth checking.
    """
    declared = DeclaredTracking(coefficient=DELTA, residual_variance=SIGMA2_0,
                                standard_error=SE, validation_df=DF)
    rng = np.random.default_rng(0)
    drawn = np.array([declared.draw(rng) for _ in range(200_000)])
    deltas, remainders = drawn[:, 0], drawn[:, 1]

    assert deltas.mean() == pytest.approx(DELTA, abs=4e-4)
    assert deltas.var(ddof=1) == pytest.approx(SE * SE * DF / (DF - 2),
                                               rel=0.02)
    assert remainders.mean() == pytest.approx(SIGMA2_0 * DF / (DF - 2),
                                              rel=0.01)
    standardised = (deltas - DELTA) / np.sqrt(remainders)
    assert abs(np.corrcoef(standardised, remainders)[0, 1]) < 0.02


def test_a_declaration_with_no_study_draws_nothing():
    """Consuming no randomness is what "the number is exact" means at the
    draw, and it is what keeps the rng stream of every existing run intact."""
    declared = DeclaredTracking(coefficient=DELTA)
    assert not declared.studied
    before = np.random.default_rng(3)
    after = np.random.default_rng(3)
    assert declared.draw(before) == (DELTA, None)
    assert before.standard_normal() == after.standard_normal()


# --- the ledger ---------------------------------------------------------------


@pytest.mark.parametrize(
    "coefficient,variance,owed,wrong",
    (
        (DELTA, TOTAL, EXACT, STUDIED),
        (DELTA, {"error_variance": TOTAL, "validation_df": DF},
         EXACT, STUDIED),
        (_study(), ..., STUDIED, EXACT),
    ),
    ids=("nothing-studied", "variance-studied", "delta-studied"),
)
def test_the_premise_says_which_way_delta_was_settled(
    coefficient, variance, owed, wrong,
):
    est = _run(coefficient=coefficient, variance=variance, bootstrap=0)
    assert owed in est.assumptions
    assert wrong not in est.assumptions


def test_the_two_studies_are_declared_apart():
    """A δ fixed by protocol beside a σ²_u a substudy measured is a real run,
    and so is its mirror. The block records them in two fields for that
    reason — one field for both would read either run as declaring both or
    neither, and the audit is keyed on those fields."""
    variance_only = _run(
        coefficient=DELTA, bootstrap=0,
        variance={"error_variance": TOTAL, "validation_df": DF})
    assert variance_only.validation_df == DF
    assert variance_only.tracking_standard_error is None

    both = _run(coefficient=_study(), bootstrap=0)
    assert both.validation_df == DF
    assert both.tracking_standard_error == SE
    assert "design_error_variance_from_a_validation_study_on_w" in (
        both.assumptions)


@pytest.mark.parametrize("coefficient,variance", (
    (DELTA, TOTAL),
    (_study(), ...),
))
def test_the_audit_confirms_the_honest_pair(coefficient, variance):
    verify_differential_error_numeric(
        _envelope(_run(coefficient=coefficient, variance=variance,
                       bootstrap=0)))


@pytest.mark.parametrize("coefficient,variance,said,instead", (
    (_study(), ..., "from_a_validation_study", "known_and_fixed"),
    (DELTA, TOTAL, "known_and_fixed", "from_a_validation_study"),
), ids=("studied-premise-says-exact", "exact-premise-claims-a-study"))
def test_the_audit_refuses_a_premise_that_says_the_opposite(
    coefficient, variance, said, instead,
):
    """Neither direction shows on the page — the interval is the same pair of
    numbers either way — so the audit is the only thing that can see it."""
    envelope = _envelope(_run(coefficient=coefficient, variance=variance,
                              bootstrap=0))
    envelope["assumptions"] = [
        a.replace(said, instead) if a.startswith("differential_coefficient_")
        else a
        for a in envelope["assumptions"]
    ]
    with pytest.raises(VerificationError, match="differential_coefficient"):
        verify_differential_error_numeric(envelope)


def test_both_spellings_reach_the_reader_as_a_sentence():
    """An id no row matches keeps itself as the token, which is the honest
    fallback and not an answer. Both stay identification premises: δ enters
    the correction, so what the study buys is width around a point that still
    rests on the regression having been right."""
    for premise, tail in ((EXACT, "known_and_fixed_on_"),
                          (STUDIED, "from_a_validation_study_on_")):
        row = glossary.classify_assumption(premise)
        assert row["claim"][0]["token"] == "differential_coefficient_" + tail
        assert row["claim"][0]["said"] == {"suffix": "w"}
        assert glossary.layer_of(premise) is Layer.IDENTIFICATION


def test_the_report_says_the_study_exactly_when_there_was_one():
    """The failure this whole family keeps having is a capability landing
    without the layer that SAYS it: the same two endpoints look the same
    whether or not a study is behind them, so the sentence is the only
    difference a reader gets."""
    studied = _report(_run(coefficient=_study(), bootstrap=0))
    assert "δ̂" in studied and str(DF) in studied
    assert "残差方差 σ²_0" in studied

    fixed = _report(_run(coefficient=DELTA, variance=TOTAL, bootstrap=0))
    assert "δ̂" not in fixed
    assert "声明的误差总方差" in fixed


# --- what the declaration refuses ---------------------------------------------


def test_a_study_and_a_total_variance_are_one_fact_twice():
    """Under the study shape the total is DERIVED, so a second one has no
    answer to which the correction used — and the interval would be the same
    pair of numbers whichever it was."""
    with pytest.raises(EstimatorFailure) as raised:
        _run(coefficient=_study(), variance=TOTAL, bootstrap=0)
    assert raised.value.failure_type == (
        Refusal.TRACKING_STUDY_AND_A_DECLARED_VARIANCE)


@pytest.mark.parametrize("spec", (
    {"coefficient": DELTA, "validation_df": DF},
    {"coefficient": DELTA, "standard_error": SE},
    {"coefficient": DELTA, "residual_variance": SIGMA2_0},
    _study(validation_df=0),
    _study(validation_df=2.5),
    _study(validation_df=True),
    _study(standard_error=0.0),
    _study(standard_error=-1.0),
    _study(residual_variance=0.0),
    _study(standard_error=float("nan")),
), ids=lambda s: "-".join(sorted(k for k in s if k != "coefficient")) + str(
    sorted(v for k, v in s.items() if k != "coefficient")))
def test_half_a_study_names_no_distribution(spec):
    """The three come out of one fit, so a subset of them is not a smaller
    declaration — it is one with no sampling distribution behind it."""
    with pytest.raises(EstimatorFailure) as raised:
        _run(coefficient=spec, bootstrap=0)
    assert raised.value.failure_type == Refusal.TRACKING_STUDY_NOT_USABLE


def test_a_coefficient_that_is_not_a_number_is_still_refused_as_one():
    """The shape is judged where the declaration becomes an object and the
    COEFFICIENT where the estimator reads it, so a caller who wrapped a
    non-number is told about the number rather than about the wrapper."""
    with pytest.raises(EstimatorFailure) as raised:
        _run(coefficient={"coefficient": "large"}, variance=TOTAL,
             bootstrap=0)
    assert raised.value.failure_type == Refusal.ARGUMENT_NOT_A_NUMBER


def test_the_contradiction_guard_cannot_fire_under_the_study_shape():
    """A declaration naming the two INDEPENDENT pieces cannot contradict
    itself: σ²_0 is stated positive and σ²_u is whatever they compose to. The
    same δ against a total that cannot hold it is refused, which is what makes
    this a property of the shape rather than of the numbers."""
    too_small = SIGMA2_0 * 0.1
    with pytest.raises(EstimatorFailure) as raised:
        _run(coefficient=DELTA, variance=too_small, bootstrap=0)
    assert raised.value.failure_type == (
        Refusal.DIFFERENTIAL_COEFFICIENT_EXCEEDS_THE_DECLARED_VARIANCE)

    est = _run(coefficient=_study(residual_variance=too_small), bootstrap=0)
    assert est.nondifferential_variance == pytest.approx(too_small, rel=1e-9)


def test_the_family_is_now_under_the_rule_that_watches_the_other_three():
    """The gate from the sibling frontier reads its own scope off the
    glossary — every family worded both ways — so this family entered its
    scope the day it grew a second spelling, with nothing added to a list.
    Asserting it here is what makes that mechanism visible from this end."""
    from tests.test_a_factor_that_priced_a_study_says_so_on_the_ledger import (
        _settled_both_ways,
    )

    assert "differential_coefficient" in _settled_both_ways()
