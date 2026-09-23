"""A follow-up time is not a measurement, and averaging it is not an estimate.

The kernel had no way to say that a column stops when observation stops.
So it read one as an ordinary number and the estimator took its mean. On a
design whose truth is known — exponential survival, a treatment that
doubles the mean, independent exponential censoring taking two units in
five — the arm difference in the RECORDED column is a third of the arm
difference in the survival times, and ``themis.estimate`` returned it as
``numerically_solved`` with no word anywhere in the envelope about what had
happened.

What makes that the worst shape of wrong is that nothing about it looks
wrong. The number is stable, the interval is narrow, the assumptions listed
are all true, and the answer is a third of the truth.

So the declaration is positive and the route is separate. Five layers are
pinned here:

* the estimator, against the closed form the design has (an exponential's
  restricted mean is ``(1 − e^{−λτ})/λ``), and against the plain arm
  difference when nothing is censored — where the two must agree exactly,
  because with no censoring a Kaplan-Meier curve IS the empirical one;
* the routing, that a declared censored outcome is claimed ahead of every
  row that would average the recorded column, and that each way the route
  cannot go stops the query rather than passing it on;
* the refusals, one constructed case each;
* the verifier, which re-derives the whole answer from the risk tables and
  is shown rejecting the one forgery its arithmetic would otherwise pass;
* the two reading surfaces, in both languages.
"""
from __future__ import annotations

import json
import math
import pathlib
import re

import numpy as np
import pandas as pd
import pytest

import themis
from themis import blocks, language, refusals
from themis.estimation.survival import restricted_mean_survival
from themis.refusals import EstimatorFailure, Refusal
from themis.verifier import verify_survival_curve
from themis.verifier.errors import VerificationError

REPO = pathlib.Path(__file__).resolve().parent.parent


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": "u"}]}


X, Y, Z = _atom("x"), _atom("t"), _atom("z")


def _program(*, censoring=True, horizon=2.0, confounded=True):
    """A program whose outcome is a follow-up time.

    ``confounded`` decides whether Z is in the graph at all, which is what
    decides whether a back-door set exists — the fact the survival route
    needs and refuses without.
    """
    declared: dict = {"kind": "variable", "predicate": "t",
                      "scale": "continuous"}
    if censoring:
        declared["censoring"] = {"event_indicator": "seen"}
        if horizon is not None:
            declared["censoring"]["horizon"] = horizon
    edges = [{"kind": "cause", "from": X, "to": Y}]
    if confounded:
        edges = [{"kind": "cause", "from": Z, "to": X},
                 {"kind": "cause", "from": Z, "to": Y}] + edges
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "u"}]},
        "statements": [
            *edges,
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            *([{"kind": "variable", "predicate": "z",
                "domain": [True, False]}] if confounded else []),
            declared,
            {"kind": "query", "id": "q1",
             "query": {"kind": "effect",
                       "intervention": {"atom": X, "value": True},
                       "target": {"atom": Y, "value": True},
                       "given": []}},
        ],
    }


#: The design's own parameters, so the closed form below and the data
#: generator cannot drift apart.
RATE_CONTROL, RATE_TREATED, CENSOR_RATE, HORIZON = 0.5, 0.25, 0.4, 2.0


def _rmst(rate: float, tau: float) -> float:
    """``∫₀^τ e^{−λu} du`` — an exponential's restricted mean, in closed form."""
    return (1.0 - math.exp(-rate * tau)) / rate


def _sample(n=40000, *, seed=20260901, censored=True, confounded=False):
    """Survival times, and how much of each one anybody got to see."""
    rng = np.random.default_rng(seed)
    z = rng.integers(0, 2, n)
    x = ((rng.random(n) < np.where(z == 1, 0.7, 0.3)).astype(int)
         if confounded else rng.integers(0, 2, n))
    rate = np.where(x == 1, RATE_TREATED, RATE_CONTROL)
    if confounded:
        rate = rate * np.exp(0.6 * z)
    survival = rng.exponential(1.0 / rate)
    if censored:
        stop = rng.exponential(1.0 / CENSOR_RATE, n)
        recorded, seen = np.minimum(survival, stop), (survival <= stop)
    else:
        recorded, seen = survival, np.ones(n, dtype=bool)
    return pd.DataFrame({"x": x, "z": z, "t": recorded,
                         "seen": seen.astype(float),
                         # Kept so a test can compare what the estimator
                         # gets with what nobody in the world would have.
                         "true_t": survival})


# --------------------------------------------------------------------------
# The estimator, against arithmetic that does not come from it
# --------------------------------------------------------------------------


def test_the_restricted_mean_is_the_one_the_design_has():
    """The closed form, not a previous run of this code.

    An exponential's restricted mean has a closed form and the design is
    exponential, so what the estimator returns can be checked against a
    number nothing in this package computed.
    """
    data = _sample()
    est = restricted_mean_survival(
        data, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON)
    assert est.censored_share > 0.4, "the design is meant to be heavily censored"
    assert est.rmst_treated == pytest.approx(_rmst(RATE_TREATED, HORIZON),
                                             abs=0.01)
    assert est.rmst_control == pytest.approx(_rmst(RATE_CONTROL, HORIZON),
                                             abs=0.01)
    truth = _rmst(RATE_TREATED, HORIZON) - _rmst(RATE_CONTROL, HORIZON)
    assert est.point == pytest.approx(truth, abs=0.01)
    assert est.ci_lower < truth < est.ci_upper


def test_the_recorded_column_would_have_answered_a_different_question():
    """The finding this whole route exists for, kept as arithmetic.

    Not a claim about a past release: the mean of the recorded column is
    computed here, beside the restricted mean, on the same frame.

    The gap is not signed, and that is the part worth pinning. Under
    independent exponential censoring the recorded mean of an arm is
    ``1/(λ+μ)``, so which way the arm difference is wrong depends on the
    CENSORING rate — a quantity nobody records and no reader is told. On
    the design that opened this route the recorded difference was a third
    of the truth; on the design here it is a third too large. Both are the
    same defect: the number answers a question nobody asked, and its sign
    cannot be reasoned about from anything on the page.
    """
    data = _sample()
    naive = (data[data.x == 1].t.mean() - data[data.x == 0].t.mean())
    honest = restricted_mean_survival(
        data, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON).point
    truth = _rmst(RATE_TREATED, HORIZON) - _rmst(RATE_CONTROL, HORIZON)
    assert honest == pytest.approx(truth, abs=0.01)
    assert abs(naive - truth) > 0.3 * truth
    # And the recorded mean of an arm is the closed form that says why:
    # 1/(λ+μ), the survival rate and the censoring rate added.
    assert data[data.x == 1].t.mean() == pytest.approx(
        1.0 / (RATE_TREATED + CENSOR_RATE), abs=0.05)
    assert data[data.x == 0].t.mean() == pytest.approx(
        1.0 / (RATE_CONTROL + CENSOR_RATE), abs=0.05)


def test_with_nothing_censored_it_is_the_ordinary_arm_difference():
    """The reduction that says this is the same estimand as before.

    With no censoring the Kaplan-Meier curve is the empirical survival
    function, so the area under it to τ is the sample mean of min(T, τ) —
    exactly, not approximately. A route that answered a DIFFERENT question
    would not have to agree here.
    """
    data = _sample(n=4000, censored=False)
    est = restricted_mean_survival(
        data, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON)
    plain = data.assign(m=np.minimum(data.t, HORIZON)).groupby("x").m.mean()
    assert est.rmst_treated == pytest.approx(plain[1], abs=1e-12)
    assert est.rmst_control == pytest.approx(plain[0], abs=1e-12)


def test_the_greenwood_interval_covers_at_about_its_nominal_rate():
    """A width nobody checks is a width nobody should read.

    Sixty replicates at a sample size where the variance term matters. The
    band is wide on purpose — sixty draws cannot resolve 95% from 93% —
    and what it rules out is an interval off by a factor.
    """
    truth = _rmst(RATE_TREATED, HORIZON) - _rmst(RATE_CONTROL, HORIZON)
    covered = 0
    for seed in range(60):
        data = _sample(n=600, seed=1000 + seed)
        est = restricted_mean_survival(
            data, treatment="x", outcome="t", event_indicator="seen",
            horizon=HORIZON)
        covered += est.ci_lower <= truth <= est.ci_upper
    assert 0.85 <= covered / 60 <= 1.0, covered


def test_a_stratum_weight_is_the_share_of_the_sample_it_holds():
    """The g-formula, not a pooled curve.

    Two things could be called "adjusted" here and only one is right: a
    curve fitted on everyone with Z in a model, and a curve per cell
    averaged with the marginal weights. This pins the second.
    """
    data = _sample(n=8000, confounded=True)
    est = restricted_mean_survival(
        data, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON, adjustment=("z",))
    assert {cell.stratum for cell in est.arms} == {(0,), (1,)}
    for arm in (True, False):
        side = [c for c in est.arms if c.arm is arm]
        assert sum(c.weight for c in side) == pytest.approx(1.0)
        assert est.rmst_treated if arm else est.rmst_control
    for stratum in ((0,), (1,)):
        share = float((data.z == stratum[0]).mean())
        for cell in (c for c in est.arms if c.stratum == stratum):
            assert cell.weight == pytest.approx(share)


# --------------------------------------------------------------------------
# The refusals — one constructed case each
# --------------------------------------------------------------------------


def _raises(species: Refusal, **kwargs):
    data = kwargs.pop("data", None)
    if data is None:
        data = _sample(n=400)
    call = {"treatment": "x", "outcome": "t", "event_indicator": "seen",
            "horizon": HORIZON}
    call.update(kwargs)
    with pytest.raises(EstimatorFailure) as caught:
        restricted_mean_survival(data, **call)
    assert caught.value.failure_type is species, caught.value.failure_type
    return caught.value


def test_a_mean_with_no_horizon_is_refused_rather_than_guessed():
    """The refusal this route exists for.

    Not a missing argument in the ordinary sense: the unrestricted mean of
    a censored variable is not a quantity this data holds, so there is no
    default that would be right.

    ``REQUEST`` and not ``DATA``, and the choice is about what the reader
    should DO. Complete follow-up on everybody would produce an
    unrestricted mean, so DATA's promise — a second dataset would work —
    is literally satisfiable here; and sending a reader to collect it,
    when what is missing is one number they already know, is the wrong
    instruction. The route out rides on the occasion as a
    :class:`Remedy`, not in the sentence.
    """
    exc = _raises(Refusal.A_CENSORED_MEAN_NEEDS_A_HORIZON, horizon=None)
    assert exc.details["outcome"] == "t"
    assert refusals.Refusal.A_CENSORED_MEAN_NEEDS_A_HORIZON.kind \
        is refusals.Kind.REQUEST
    assert exc.remedies == [{"remedy": "supply_input", "subject": "horizon"}]


def test_an_event_column_that_is_not_an_indicator_is_refused():
    data = _sample(n=400)
    data.loc[data.index[:5], "seen"] = 2.0
    exc = _raises(Refusal.THE_EVENT_COLUMN_IS_NOT_AN_INDICATOR, data=data)
    assert exc.details["column"] == "seen"


def test_a_negative_follow_up_time_is_refused():
    data = _sample(n=400)
    data.loc[data.index[0], "t"] = -1.0
    _raises(Refusal.A_FOLLOW_UP_TIME_IS_NEGATIVE, data=data)


def test_a_horizon_past_a_cell_s_last_observation_is_refused():
    """Past the last observation a curve is carried flat.

    Which makes the area there a guess about a stretch nobody watched —
    and the guess is invisible in the number, which is why this is a
    refusal rather than a caveat.
    """
    data = _sample(n=400)
    exc = _raises(Refusal.THE_HORIZON_IS_PAST_THE_LAST_OBSERVATION,
                  data=data, horizon=float(data.t.max()) + 1.0)
    assert "last" in exc.details and "horizon" in exc.details


def test_a_named_cluster_column_is_answered_rather_than_ignored():
    """Greenwood counts every unit as its own, so this route cannot cluster.

    Which makes the disclosure the whole of what it can do — and the
    disclosure is load-bearing in a way the point never is: clustering
    moves the WIDTH, so an interval that stays silent about a named
    cluster column reads downstream as i.i.d. inference nobody licensed,
    and nothing can see a width that should have been wider.
    """
    data = _sample(n=4000, confounded=True)
    data = data.assign(site=np.arange(len(data)) % 50)
    r = themis.estimate(_program(), data, cluster="site")["results"][0]
    assert r["numeric_estimate"]["method"] == "rmst_kaplan_meier"
    assert ("ci_not_cluster_robust_analytic_interval_ignores_site"
            in r["numeric_estimate"]["assumptions"])
    # And the gate that would have caught the silence accepts the answer.
    themis.verify(_program(), r)


def test_the_two_arms_are_told_apart_by_order_and_not_by_truthiness():
    """A two-level column need not be coded 0/1.

    ``bool`` of the level is the obvious spelling and is wrong for every
    other coding: both arms come back True, one side of the contrast holds
    every cell and the other holds none, and the difference of the two
    standardised means is a number with no second arm in it. Recoded 1/2
    the answer must be the same answer.
    """
    data = _sample(n=2000)
    recoded = data.assign(x=data.x + 1)
    plain = restricted_mean_survival(
        data, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON)
    shifted = restricted_mean_survival(
        recoded, treatment="x", outcome="t", event_indicator="seen",
        horizon=HORIZON)
    assert shifted.point == pytest.approx(plain.point)
    assert shifted.rmst_treated == pytest.approx(plain.rmst_treated)
    assert {cell.arm for cell in shifted.arms} == {True, False}


def test_a_cell_with_one_arm_in_it_is_refused():
    data = _sample(n=600, confounded=True)
    # Empty the treated side of one stratum outright.
    data = data[~((data.z == 1) & (data.x == 1))]
    _raises(Refusal.NO_WITHIN_STRATUM_CONTRAST, data=data, adjustment=("z",))


def test_a_horizon_that_is_not_a_number_is_refused():
    _raises(Refusal.ARGUMENT_NOT_A_NUMBER, horizon=float("inf"))
    _raises(Refusal.ARGUMENT_NOT_A_NUMBER, horizon=-1.0)


# --------------------------------------------------------------------------
# The routing — what the declaration takes the query away from
# --------------------------------------------------------------------------


def test_a_declared_censored_outcome_is_answered_by_the_survival_route():
    out = themis.estimate(_program(), _sample(n=8000, confounded=True))
    r = out["results"][0]
    assert r["status"] == "numerically_solved"
    assert r["numeric_estimate"]["method"] == "rmst_kaplan_meier"
    assert blocks.Block.SURVIVAL_CURVE in r["extensions"]


def test_without_the_declaration_the_same_data_is_answered_as_a_measurement():
    """The counterexample for the declaration itself.

    Undeclared is 'nobody said', never 'said uncensored', so the ordinary
    route still answers — and what it answers is the thing this module
    exists to stop being silent about.

    How far apart the two are is stated against the honest answer's own
    interval rather than against a threshold picked to pass: the silent
    number lies OUTSIDE the interval the survival route reports, which is
    the strongest thing that can be said without a second design. A
    threshold would be an arbitrary line; this one the answer draws itself.
    """
    data = _sample(n=8000, confounded=True)
    out = themis.estimate(_program(censoring=False), data)
    r = out["results"][0]
    assert r["numeric_estimate"]["method"] == "backdoor_linear"
    assert blocks.Block.SURVIVAL_CURVE not in (r.get("extensions") or {})

    honest = themis.estimate(_program(), data)["results"][0]["numeric_estimate"]
    silent = r["numeric_estimate"]["point"]
    assert not honest["ci_lower"] <= silent <= honest["ci_upper"], (
        silent, honest["ci_lower"], honest["ci_upper"])


def test_the_survival_route_outranks_every_row_that_would_average_the_column():
    """Precedence, read off the shared table rather than off an outcome.

    Every row that turns the outcome column into a number has to come
    after this one. Asked of the table because that is where the claim
    lives: a test that only checked one worked example would pass while a
    row added later quietly outranked it.
    """
    from themis import routing

    survival = routing.route("survival")
    for other in routing.EFFECT_ROUTES:
        if other.id in ("survival", "feedback_loop", "longitudinal",
                        "joint_intervention", "transport", "mediation_joint",
                        "mediation_single", "selection_recovery",
                        "measurement_correction_both_channels",
                        "measurement_correction_outcome",
                        "measurement_correction_exposure"):
            continue
        assert survival.precedence < other.precedence, other.id


def test_a_censored_outcome_also_declared_mismeasured_stops_the_query():
    """Two declarations about one column, and one route that honours one.

    Answering under the first while dropping the second would be an answer
    under a premise the author withdrew — which is the failure this
    package has already had once, on the outcome channel.
    """
    out = themis.estimate(
        _program(), _sample(n=4000, confounded=True),
        measurement_error={"t": {"error_variance": 0.25}},
    )
    r = out["results"][0]
    assert r.get("numeric_estimate") is None
    assert r["estimator_failure"]["failure_type"] == \
        "a_censored_outcome_is_also_declared_mismeasured"


def test_a_censored_outcome_with_no_backdoor_set_stops_the_query():
    """The other way out, and it stops too.

    A graph with no back-door set has routes that would still produce a
    number — and every one of them would produce it by averaging the
    recorded column. Refusing is the point.
    """
    prog = _program(confounded=True)
    # A latent confounder: X and T share an unmeasured cause, so no
    # measured set closes the back door.
    prog["statements"].insert(0, {"kind": "bidirected", "left": X, "right": Y})
    out = themis.estimate(prog, _sample(n=4000, confounded=True))
    r = out["results"][0]
    assert r["estimator_failure"]["failure_type"] == \
        "a_censored_outcome_needs_a_backdoor_set"


def test_a_declaration_with_no_horizon_reaches_the_reader_as_that_refusal():
    """Optional in the schema, required by the estimator, and the gap
    between those two is where the sentence lives."""
    out = themis.estimate(_program(horizon=None),
                          _sample(n=4000, confounded=True))
    r = out["results"][0]
    assert r["estimator_failure"]["failure_type"] == \
        "a_censored_mean_needs_a_horizon"


def test_the_event_column_reaches_the_estimator():
    """The contract narrows the frame to the columns a declaration names.

    The indicator is not a node of the graph and never will be, so
    ``_collect_required_columns`` had to learn that one declaration can
    name two columns — without which every run of this route died in the
    data contract on a column the program had plainly named.
    """
    from themis.estimation.dispatch import _collect_required_columns

    assert _collect_required_columns(_program()) == {"x", "z", "t", "seen"}
    assert "seen" not in _collect_required_columns(_program(censoring=False))


# --------------------------------------------------------------------------
# The verifier — an independent re-derivation, and the forgery it catches
# --------------------------------------------------------------------------


def _answered():
    out = themis.estimate(_program(), _sample(n=6000, confounded=True))
    return out["results"][0]


def test_the_answer_verifies_end_to_end():
    r = _answered()
    themis.verify(_program(), r)
    verify_survival_curve(r)


def test_a_curve_that_does_not_recompute_is_rejected():
    r = _answered()
    r["extensions"]["survival_curve"]["cells"][0]["rmst"] += 0.1
    with pytest.raises(VerificationError, match="Kaplan-Meier"):
        verify_survival_curve(r)


def test_a_variance_that_does_not_recompute_is_rejected():
    r = _answered()
    r["extensions"]["survival_curve"]["cells"][0]["variance"] *= 0.5
    with pytest.raises(VerificationError, match="Greenwood"):
        verify_survival_curve(r)


def test_a_denominator_that_is_not_what_the_row_before_it_leaves_is_rejected():
    """The producer bug the recomputation cannot see.

    Everything below the risk set is a function of it, so a table whose
    ``at_risk`` column is wrong recomputes to a curve, an area and a
    variance that agree with each other perfectly and describe nobody.
    Counting ``>`` instead of ``>=``, or forgetting that a unit who leaves
    without the event still leaves, both take this shape. What catches it
    is the table's own arithmetic: a risk set is what the row before it
    leaves standing.
    """
    r = _answered()
    rows = r["extensions"]["survival_curve"]["cells"][0]["risk_table"]
    rows[3]["at_risk"] += 5
    with pytest.raises(VerificationError, match="account for its own losses"):
        verify_survival_curve(r)


def test_a_table_that_pretends_nobody_left_early_is_rejected():
    """The forgery, and the check that actually catches it.

    Rebuild the table as though every unit who left had had the event
    instead: denominators that fall only by the events, no censorings
    anywhere. It is a VALID risk table — internally consistent, and its
    curve, area and variance all recompute from it — and it is too
    optimistic everywhere. What refuses it is the count the cell records
    beside the table: the block says how many left without the event, and
    a table holding none of them contradicts it.

    Which is the honest limit of this audit, stated as a test rather than
    left implied: a producer that rewrote the table AND every scalar
    derived from it would leave a block nothing in the block could refute.
    The evidence IS the block. What the audit rules out is a wrong table
    and a producer bug, not a determined liar with a consistent story.
    """
    cell = _answered()
    block = cell["extensions"]["survival_curve"]["cells"][0]
    standing = block["risk_table"][0]["at_risk"]
    forged = []
    for row in block["risk_table"]:
        forged.append({**row, "at_risk": standing, "censored": 0})
        standing -= row["events"]
    block["risk_table"] = [row for row in forged if row["events"]]
    with pytest.raises(VerificationError,
                       match="units whose follow-up ended"):
        verify_survival_curve(cell)


def test_a_standardisation_whose_weights_do_not_sum_is_rejected():
    r = _answered()
    for cell in r["extensions"]["survival_curve"]["cells"]:
        cell["weight"] = cell["weight"] * 0.5
    with pytest.raises(VerificationError, match="weights within"):
        verify_survival_curve(r)


def test_an_answer_that_is_not_the_difference_of_the_two_arms_is_rejected():
    r = _answered()
    r["numeric_estimate"]["point"] += 0.5
    with pytest.raises(VerificationError, match="difference of the two arms"):
        verify_survival_curve(r)


def test_an_interval_the_tables_do_not_imply_is_rejected():
    r = _answered()
    r["numeric_estimate"]["ci_upper"] += 0.5
    with pytest.raises(VerificationError, match="interval's width"):
        verify_survival_curve(r)


def test_an_unstated_independent_censoring_premise_is_rejected():
    """The one thing here no arithmetic witnesses.

    Whether the units still standing are exchangeable with those who left
    is not a question any table answers. So what is checked is that the
    premise reached the ledger, where a reader can disagree with it — the
    same shape the Berkson audit holds its own structure to.
    """
    r = _answered()
    ledger = r["extensions"]["assumption_ledger"]
    ledger["assumptions"] = [
        e for e in ledger["assumptions"]
        if not str(e.get("id")).startswith("censoring_is_independent")
    ]
    with pytest.raises(VerificationError, match="censoring_is_independent"):
        verify_survival_curve(r)


def test_a_censored_share_its_own_cells_do_not_add_up_to_is_rejected():
    """The share is a count over a count, and both counts are in the block.

    Every cell records how many units it held and how many of them left
    without the event. The block's share is over the whole run, so it is
    those two sums divided — the producer's word about its own tables until
    somebody divides them.
    """
    r = _answered()
    block = r["extensions"]["survival_curve"]
    block["censored_share"] = float(block["censored_share"]) / 2.0
    with pytest.raises(VerificationError,
                       match="leaving without the event"):
        verify_survival_curve(r)


def test_a_share_is_held_to_the_float_and_not_to_the_neighbourhood():
    """One unit in six thousand is a different share, and says so."""
    r = _answered()
    block = r["extensions"]["survival_curve"]
    censored = sum(c["n_censored"] for c in block["cells"])
    units = sum(c["n"] for c in block["cells"])
    block["censored_share"] = (censored + 1) / units
    with pytest.raises(VerificationError,
                       match="leaving without the event"):
        verify_survival_curve(r)


def test_a_follow_up_that_ends_before_a_cell_was_last_seen_is_rejected():
    """The one direction that needs no condition.

    Follow-up ends when the last unit anywhere was last seen. The cells are
    part of the sample whether or not they are all of it, so a block whose
    follow-up ends before a time it itself records is inconsistent with
    itself and not merely with a denominator this audit cannot see.
    """
    r = _answered()
    block = r["extensions"]["survival_curve"]
    block["follow_up_ends"] = min(c["last_observed"] for c in block["cells"]) \
        / 2.0
    with pytest.raises(VerificationError,
                       match="not before a time the block itself carries"):
        verify_survival_curve(r)


def test_a_follow_up_that_outlasts_every_cell_is_rejected():
    r = _answered()
    block = r["extensions"]["survival_curve"]
    block["follow_up_ends"] = float(block["follow_up_ends"]) + 10.0
    with pytest.raises(VerificationError,
                       match="the last time any of its cells records"):
        verify_survival_curve(r)


def test_where_the_cells_are_not_the_whole_sample_the_share_is_left_alone():
    """The declared boundary, pinned as a test rather than left implied.

    The share's denominator is everyone the run read, and the cells are per
    (stratum, arm). They are the sample exactly when their units add up to
    the estimate's, and the envelope says so for itself. Where they do not,
    dividing by the cells anyway would refuse an honest run for being
    partial — so the share is not asked, and the follow-up still is, because
    that one is bounded by the cells rather than equal to them.
    """
    r = _answered()
    block = r["extensions"]["survival_curve"]
    r["numeric_estimate"]["sample_size"] = int(
        r["numeric_estimate"]["sample_size"]) + 1
    block["censored_share"] = 0.99
    block["follow_up_ends"] = float(block["follow_up_ends"]) + 10.0
    verify_survival_curve(r)

    block["follow_up_ends"] = 0.5
    with pytest.raises(VerificationError,
                       match="not before a time the block itself carries"):
        verify_survival_curve(r)


def test_an_event_column_the_run_never_read_is_rejected():
    r = _answered()
    r["extensions"]["survival_curve"]["event_indicator"] = "not_a_column"
    with pytest.raises(VerificationError, match="a column nobody opened"):
        verify_survival_curve(r)


def test_an_event_column_that_is_the_recorded_time_itself_is_rejected():
    """A column cannot be both the duration and the flag about it."""
    r = _answered()
    r["extensions"]["survival_curve"]["event_indicator"] = \
        r["numeric_estimate"]["outcome"]
    with pytest.raises(VerificationError, match="a curve read off itself"):
        verify_survival_curve(r)


def test_two_arms_standardised_over_different_strata_are_rejected():
    """Weights that each sum to one over two different sets of strata.

    ``Σ_z w(z)·[m(1,z) − m(0,z)]`` is one set of strata read twice. Two
    arms carrying different sets pass the check that each arm's weights sum
    to one, and the difference they report is between two populations.
    """
    r = _answered()
    cells = r["extensions"]["survival_curve"]["cells"]
    first = next(c for c in cells if c["arm"] is False)
    first["stratum"] = ["a stratum the other arm has never heard of"]
    with pytest.raises(VerificationError,
                       match="standardised over different strata"):
        verify_survival_curve(r)


def test_a_stratum_weighted_differently_in_the_two_arms_is_rejected():
    """A weight is the stratum's share, which no arm gets its own copy of."""
    r = _answered()
    cells = r["extensions"]["survival_curve"]["cells"]
    treated = next(c for c in cells if c["arm"] is True)
    other = next(c for c in cells
                 if c["arm"] is False
                 and list(c["stratum"]) == list(treated["stratum"]))
    treated["weight"] = other["weight"] + 1e-3
    with pytest.raises(VerificationError,
                       match="share of the sample whichever arm"):
        verify_survival_curve(r)


def test_a_stratum_recorded_twice_in_one_arm_is_rejected():
    """Weighted once is what the standardisation does with each stratum."""
    r = _answered()
    cells = r["extensions"]["survival_curve"]["cells"]
    treated = [c for c in cells if c["arm"] is True]
    treated[1]["stratum"] = list(treated[0]["stratum"])
    with pytest.raises(VerificationError,
                       match="a stratum recorded twice is one weighted twice"):
        verify_survival_curve(r)


def test_the_verifier_does_not_import_the_estimator():
    """Duplication is the design; a shared import would undo it."""
    source = (REPO / "themis" / "verifier" / "survival_rules.py").read_text(
        encoding="utf-8")
    assert not re.search(r"^\s*from\s+\.\.estimation", source, re.M)
    assert not re.search(r"^\s*import\s+themis\.estimation", source, re.M)


def test_the_verifier_runs_inside_verify_without_being_asked():
    """A verifier nobody calls is a verifier that passes everything."""
    r = _answered()
    r["extensions"]["survival_curve"]["cells"][0]["rmst"] += 0.1
    with pytest.raises(VerificationError):
        themis.verify(_program(), r)


# --------------------------------------------------------------------------
# The two reading surfaces
# --------------------------------------------------------------------------


@pytest.mark.parametrize("lang", ["zh", "en"])
def test_the_reader_is_told_which_mean_this_is(lang):
    """A restricted mean without its horizon is unreadable, not imprecise.

    So the report has to say the horizon, has to say that this is not the
    mean survival time, and has to say how much of the answer rests on the
    curve — in whichever language the reader is reading.
    """
    r = _answered()
    text = themis.build_analysis_report(r, program=_program(), lang=lang)
    assert "Kaplan-Meier" in text
    assert str(HORIZON).rstrip("0").rstrip(".") in text
    said = language.fill(
        {"zh": "不是平均生存时间", "en": "not the mean survival time"}, lang)
    assert said in text


def test_the_browser_holds_the_same_five_facts():
    """One block, two surfaces, and the check is that neither is silent.

    Held against the schema rather than against a second list: the block
    is closed, so its properties ARE the facts there are to say, and a
    field added later without a reader shows up here.
    """
    source = (REPO / "themis" / "web" / "frontend" / "src" / "lib"
              / "verdict.ts").read_text(encoding="utf-8")
    body = source[source.index("survival_curve: (b, { lang })"):]
    body = body[:body.index("selection_recovery: (b, { lang })")]
    for field in ("horizon", "rmst_treated", "rmst_control", "censored_share",
                  "n_events", "follow_up_ends", "exhausted_cells", "cells"):
        assert field in body, field


def test_the_block_says_nothing_the_schema_does_not_declare():
    """The envelope's own list, walked.

    ``additionalProperties: false`` makes the schema the closed statement
    of what this block holds; a producer that grew a field without one is
    what this asks about.
    """
    schema = json.loads(
        (REPO / "themis" / "schemas" / "query_result.schema.json").read_text(
            encoding="utf-8"))
    declared = schema["properties"]["extensions"]["properties"][
        "survival_curve"]
    block = _answered()["extensions"]["survival_curve"]
    assert set(block) <= set(declared["properties"])
    assert set(declared["required"]) <= set(block)
    cell = declared["properties"]["cells"]["items"]
    assert set(block["cells"][0]) == set(cell["properties"])
    row = cell["properties"]["risk_table"]["items"]
    assert set(block["cells"][0]["risk_table"][0]) == set(row["properties"])
