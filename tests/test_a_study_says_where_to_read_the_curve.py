"""#473 — λ = −1 is the reading point only if σ̂²_u was exact.

SIMEX simulates with the DECLARED σ̂²_u, so the rung at λ carries total error
variance σ² + λσ̂²_u, and that is zero at λ* = −σ²/σ̂²_u. Standard SIMEX reads
at −1, which is that point under the premise σ̂²_u = σ². Where a validation
study measured σ̂²_u, σ̂²_u·df/σ² ~ χ²_df makes λ* = −df/X with X ~ χ²_df — an
exact distribution over WHERE ON THE CURVE the answer sits.

Nothing about that is a resample. #471 left this route refusing a declared
``validation_df`` because σ̂²_u sets the noise at every rung, so a redrawn one
moves the whole ladder rather than one draw on it — which was true, and was
about the draw rather than about the study. The construction here needs no
draw at all: the mixing distribution is closed-form and the extrapolants are
already fitted, so the interval stays re-derivable by a second author from
the recorded coefficients alone.

What that buys is measured against the linear-outcome oracle, where the
rational extrapolant is exact and the true coefficient is known. Holding
σ̂²_u fixed, the interval is the same width whether the study behind it had
400 degrees of freedom or 9 — and its coverage falls from 117/120 to 79/118
across that range. Reading at λ* instead restores it, at the cost of a
wider interval and of saying nothing at all when the study reaches past
where the curve can be read.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.dispatch import _simex_block
from themis.estimation.simex import (
    _STUDY_REACHES_PAST_THE_LADDER,
    _VALIDATION_QUADRATURE,
    SimexEstimate,
    estimate_simex,
    mixture_interval,
    off_the_ladder,
)
from themis.input.syntactic_validator import validate_result
from themis.verifier.errors import VerificationError
from themis.verifier.simex_rules import verify_simex_numeric

SIGMA2_U = 0.25


def _frame(n=4000, seed=0, beta=0.8, sigma2_u=SIGMA2_U):
    """The oracle: a linear outcome, where the decay is exactly rational."""
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.6 * z + rng.normal(0, 1, n)
    y = 1.0 + beta * x + 0.4 * z + rng.normal(0, 1.0, n)
    w = x + rng.normal(0, np.sqrt(sigma2_u), n)
    return pd.DataFrame({"w": w, "y": y, "z": z})


def _fit(df: int | None, frame=None, **kwargs) -> SimexEstimate:
    declared = (SIGMA2_U if df is None
                else {"error_variance": SIGMA2_U, "validation_df": df})
    kwargs.setdefault("outcome_model", "linear")
    kwargs.setdefault("n_replicates", 60)
    kwargs.setdefault("random_state", 3)
    return estimate_simex(
        _frame() if frame is None else frame,
        treatment="w", outcome="y", adjustment=("z",),
        error_variance=declared, **kwargs)


def _envelope(est: SimexEstimate) -> dict:
    return {
        "point": est.point, "ci_lower": est.ci_lower,
        "ci_upper": est.ci_upper, "ci_level": est.ci_level,
        "method": "simex", "treatment": est.treatment,
        "outcome": est.outcome, "simex": _simex_block(est),
    }


def _width(est: SimexEstimate) -> float:
    assert est.ci_upper is not None and est.ci_lower is not None
    return est.ci_upper - est.ci_lower


# ============================================ the answer does not move


def test_a_declared_study_widens_the_interval_and_leaves_the_point_alone():
    """The whole claim, in one comparison. Saying how well σ²_u is known
    prices a second source of uncertainty; it does not change the estimate,
    and a run that says nothing is unchanged down to the bit."""
    exact = _fit(None)
    measured = _fit(24)
    assert measured.point == exact.point
    assert measured.naive_point == exact.naive_point
    assert measured.coefficients == exact.coefficients
    assert measured.grid == exact.grid
    assert _width(measured) > _width(exact)


@pytest.mark.parametrize("df", [400, 100, 24, 9])
def test_the_less_the_study_pinned_it_down_the_wider_the_interval(df):
    """And this is the defect it fixes: without the declaration all four of
    these are the SAME two numbers on the page."""
    fixed = _fit(None)
    assert _width(_fit(df)) > _width(fixed)


def test_a_bigger_study_moves_the_interval_back_toward_the_exact_one():
    """λ* → −1 as df → ∞, so the construction reduces to the one it
    generalises rather than sitting beside it."""
    exact = _width(_fit(None))
    widths = [_width(_fit(df)) for df in (24, 100, 400, 4000, 100_000)]
    assert widths == sorted(widths, reverse=True)
    assert all(w > exact for w in widths)
    # σ̂²/σ² has standard deviation √(2/df), so the extra width closes at
    # that rate rather than vanishing at any particular df.
    assert widths[-1] / exact < 1.005


def test_the_premise_the_run_declares_is_the_one_it_used():
    """Two different claims, so two different ids: one says the number is
    taken as exact, the other says a study estimated it and its own
    uncertainty is in the interval."""
    assert ("design_error_variance_from_a_validation_study_on_w"
            in _fit(24).assumptions)
    assert "design_error_variance_known_and_fixed_on_w" in _fit(None).assumptions
    assert ("design_error_variance_known_and_fixed_on_w"
            not in _fit(24).assumptions)


def test_the_share_is_stated_even_when_it_is_zero():
    """A study that reaches nowhere the ladder cannot read is a fact about
    that study, and it is not the same fact as no study having been
    declared. A polynomial has no pole for it to reach past, so its zero is
    exact rather than small."""
    assert _fit(24, extrapolant="quadratic").unreadable_share == 0.0
    assert _fit(400).unreadable_share < 1e-12
    assert _fit(None).unreadable_share is None
    assert _fit(None).validation_df is None


# ============================================ where the study reaches too far


def test_a_study_that_reaches_past_the_ladder_says_so_instead_of_truncating():
    """λ* below the rational family's pole is σ² at or above the exposure's
    whole observed spread — an error variance the data itself rules out.
    Once that share reaches the tail an endpoint stands for, what is
    reported is no interval rather than a truncated one."""
    est = _fit(3)
    assert est.ci_lower is None and est.ci_upper is None
    assert est.no_interval_because == _STUDY_REACHES_PAST_THE_LADDER
    assert est.unreadable_share >= 0.025
    # And no width dressed up as one: the variance that would have been read
    # at λ = −1 is not the variance this interval would have rested on.
    assert est.extrapolated_variance is None
    # The point is untouched, as it is under every other withholding here.
    assert est.point == _fit(None).point


def test_the_share_grows_as_the_study_shrinks():
    """Monotone in the right direction, which is what makes it a diagnostic
    rather than a numerical accident of the quadrature."""
    shares = [_fit(df).unreadable_share for df in (100, 24, 9, 5, 3)]
    assert shares == sorted(shares)
    assert shares[0] < 1e-12 and shares[-1] > 0.025


def test_the_share_is_a_probability_and_not_a_count_off_the_grid():
    """λ* = −df/X lands past the pole exactly when X ≤ df/γ2, so this is a
    property of the study and the fitted curve. A number counted off the
    quadrature would be a property of the quadrature — it would move with
    the grid, and a reader comparing two runs would be reading resolution."""
    from scipy import stats

    est = _fit(9)
    pole = est.coefficients[2]
    assert est.unreadable_share == pytest.approx(
        float(stats.chi2.cdf(9 / pole, 9)), rel=1e-12)
    assert est.unreadable_share * _VALIDATION_QUADRATURE % 1 != 0


def test_a_pole_that_is_not_below_minus_one_puts_the_whole_study_off():
    """γ2 ≤ 0 puts the pole at or above λ = 0, so every λ* is past it and
    there is nothing anywhere for the study to be read at. Answered as a
    share of one rather than raised, because the caller's next move is the
    same one the tail case asks for and a second door to it would be a
    second sentence."""
    assert off_the_ladder("rational", (0.0, 1.0, -0.5), 24) == 1.0
    assert off_the_ladder("rational", (0.0, 1.0, 0.0), 24) == 1.0
    # And a family with no pole is not asked the question at all.
    assert off_the_ladder("quadratic", (0.0, 1.0, -0.5), 24) == 0.0
    assert off_the_ladder("linear", (0.0, 1.0), 24) == 0.0


def test_no_seed_reaches_this_interval():
    """Everything downstream of the simulated ladder in this module is
    re-derivable by a second author, and an interval drawn from a random
    stream would have moved that line."""
    a, b = _fit(24, random_state=3), _fit(24, random_state=3)
    assert (a.ci_lower, a.ci_upper) == (b.ci_lower, b.ci_upper)


def test_the_construction_answers_for_a_family_with_no_pole():
    """A polynomial is readable everywhere, so the only thing that can put a
    draw off the ladder there is the variance subtraction — and the interval
    still widens with the study's own uncertainty."""
    exact = _fit(None, extrapolant="quadratic")
    measured = _fit(24, extrapolant="quadratic")
    assert measured.point == exact.point
    assert _width(measured) > _width(exact)


# ============================================ what the gate says no to


@pytest.fixture(scope="module")
def honest() -> dict:
    return _envelope(_fit(24))


def _forged(honest: dict, mutate) -> dict:
    import copy

    forged = copy.deepcopy(honest)
    mutate(forged)
    return forged


FORGERIES = {
    # The endpoints are the whole point of the declaration, so moving one is
    # the forgery the audit exists for.
    "a moved lower endpoint": lambda d: d.__setitem__(
        "ci_lower", d["ci_lower"] - 0.01),
    "a moved upper endpoint": lambda d: d.__setitem__(
        "ci_upper", d["ci_upper"] + 0.01),
    # A study restated as bigger than it was: the same two endpoints, now
    # claimed to price more uncertainty than they do.
    "a study inflated after the fact": lambda d: d["simex"].__setitem__(
        "validation_df", 400),
    # The declaration dropped, which turns the mixture interval into a claim
    # that it is the plain one.
    "a study denied after the fact": lambda d: d["simex"].__setitem__(
        "validation_df", None),
    "a share that is not the one the record implies":
        lambda d: d["simex"].__setitem__("unreadable_share", 0.02),
    "a share declared where no study was": lambda d: (
        d["simex"].__setitem__("validation_df", None),
        d["simex"].__setitem__("unreadable_share", 0.0)),
}


@pytest.mark.parametrize("name", sorted(FORGERIES))
def test_a_tampered_study_record_is_rejected(honest, name):
    verify_simex_numeric(honest)          # the same record, unaltered, passes
    with pytest.raises(VerificationError):
        verify_simex_numeric(_forged(honest, FORGERIES[name]))


def test_withholding_on_a_study_that_did_not_reach_that_far_is_rejected():
    """Withholding is a claim too, and it is the one a forger reaches for
    when the recomputation would not match."""
    def _withhold(d: dict) -> None:
        d["ci_lower"] = d["ci_upper"] = None
        d["simex"]["extrapolated_variance"] = None
        d["simex"]["no_interval_because"] = _STUDY_REACHES_PAST_THE_LADDER

    with pytest.raises(VerificationError, match="off the ladder"):
        verify_simex_numeric(_forged(_envelope(_fit(24)), _withhold))


def test_the_real_withholding_is_re_derived_and_accepted():
    """The other half: the audit must accept the record that IS true, or it
    is refusing the estimator rather than auditing it."""
    verify_simex_numeric(_envelope(_fit(3)))


def test_the_audit_reads_the_curve_where_the_study_says_and_not_at_minus_one():
    """The discriminating check. A record whose endpoints are the plain
    ± z√τ(−1) while declaring a study is exactly the interval this whole
    item exists to stop shipping."""
    from scipy import stats

    forged = _envelope(_fit(24))
    tau = forged["simex"]["extrapolated_variance"]
    half = float(stats.norm.ppf(0.975)) * float(np.sqrt(tau))
    forged["ci_lower"] = forged["point"] - half
    forged["ci_upper"] = forged["point"] + half
    with pytest.raises(VerificationError):
        verify_simex_numeric(forged)


def test_the_helper_returns_the_share_in_every_case():
    """Including the one where it refuses, because the number IS the reason
    and a caller handed only ``None`` would have to guess why."""
    est = _fit(24)
    lo, hi, share, because = mixture_interval(
        est.extrapolant, est.coefficients,
        variance=est.extrapolated_variance, validation_df=24, ci_level=0.95)
    assert (lo, hi) == (est.ci_lower, est.ci_upper)
    assert share == est.unreadable_share and because is None

    lo, hi, share, because = mixture_interval(
        est.extrapolant, est.coefficients,
        variance=est.extrapolated_variance, validation_df=3, ci_level=0.95)
    assert lo is None and hi is None
    assert share > 0.025 and because == _STUDY_REACHES_PAST_THE_LADDER


# ============================================ end to end


def _atom(predicate: str) -> dict:
    return {"predicate": predicate, "args": [{"type": "const", "name": "u"}]}


def _program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            {"kind": "variable", "predicate": "w",
             "measurement": "single-occasion continuous measurement (noisy)"},
            {"kind": "variable", "predicate": "y"},
            {"kind": "variable", "predicate": "z"},
            {"kind": "cause", "from": _atom("w"), "to": _atom("y")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("w")},
            {"kind": "cause", "from": _atom("z"), "to": _atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom("w"), "value": True},
                "target": {"atom": _atom("y"), "value": True}, "given": []}},
        ],
    }


def _binary_frame(seed=11, n=5000):
    rng = np.random.default_rng(seed)
    z = rng.normal(0, 1, n)
    x = 0.5 * z + rng.normal(0, 1, n)
    p = 1.0 / (1.0 + np.exp(-(-0.2 + x + 0.5 * z)))
    return pd.DataFrame({
        "w": x + rng.normal(0, np.sqrt(SIGMA2_U), n),
        "y": (rng.random(n) < p),
        "z": z,
    })


def _run(df: int | None) -> dict:
    spec = {"error_variance": SIGMA2_U, "outcome_model": "logistic"}
    if df is not None:
        spec["validation_df"] = df
    return themis.estimate(
        _program(), _binary_frame(), ci_bootstrap=0,
        measurement_error={"w": spec})["results"][0]


def test_the_whole_road_carries_the_study_and_verifies():
    program = _program()
    result = _run(24)
    validate_result(result)
    block = result["numeric_estimate"]["simex"]
    assert block["validation_df"] == 24
    assert block["unreadable_share"] is not None
    themis.verify(program, result)

    plain = _run(None)
    assert plain["numeric_estimate"]["simex"]["validation_df"] is None
    assert plain["numeric_estimate"]["simex"]["unreadable_share"] is None
    assert plain["numeric_estimate"]["point"] == (
        result["numeric_estimate"]["point"])
    themis.verify(program, plain)


def test_the_reader_is_told_the_study_moved_where_the_answer_was_read():
    """Two intervals differing only in width look identical on the page, so
    the sentence that separates them has to be there."""
    text = themis.build_analysis_report(_run(24))
    assert "24 个自由度" in text
    assert "λ=−1 这一个点上" in text
    assert "unreadable_share" not in text
    assert "validation_df" not in text

    assert "自由度" not in themis.build_analysis_report(_run(None))
