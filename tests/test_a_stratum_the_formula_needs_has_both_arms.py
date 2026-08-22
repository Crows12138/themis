"""The g-formula's per-stratum condition, asked of the data rather than of a proxy.

``Σ_z P(Y | X=arm, Z=z) · P(z)`` needs the inner term in every stratum with
weight. Where a stratum holds one arm the data never made that comparison, and
an outcome regression fills it from the slope it learned in the strata that
had both. Three places said so and none of them measured it: the estimator
guards tested the treatment column's MARGINAL variation, which is this same
condition summed over z; the assumption row declared the per-stratum claim
unconditionally; and the overlap gap's own comment defined itself by the cell
count and then triggered on a FITTED propensity.

The frame below is the one that separates them. Channel 2 was never
advertised to, so it holds a quarter of the sample and one arm — and the
treatment column still varies, the fitted propensity for that cell still comes
back at 0.09, and the true effect there has the opposite sign from the other
two, which is precisely what the data cannot rule out and the model cannot
know.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis
from themis.estimation.support import MAX_LEVELS, arm_support
from themis.refusals import EstimatorFailure, Refusal

O = "u"

#: Per-stratum effect. The never-treated stratum is also the one where the
#: effect reverses — a combination the data cannot exclude precisely because
#: that cell is empty, which is why the check has to be structural rather than
#: a diagnostic fitted to the data.
SHARE = (0.40, 0.35, 0.25)
EFFECT = (0.20, 0.20, -0.35)
BASE = (0.30, 0.30, 0.55)
TRUE_ATE = sum(w * e for w, e in zip(SHARE, EFFECT))          # +0.0625


def _atom(p):
    return {"predicate": p, "args": [{"type": "const", "name": O}]}


def _program(levels=(0, 1, 2)):
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": O}]},
        "statements": [
            {"kind": "variable", "predicate": "ad", "domain": [True, False]},
            {"kind": "variable", "predicate": "bought", "domain": [True, False]},
            {"kind": "variable", "predicate": "channel", "domain": list(levels)},
            {"kind": "cause", "from": _atom("ad"), "to": _atom("bought")},
            {"kind": "cause", "from": _atom("channel"), "to": _atom("ad")},
            {"kind": "cause", "from": _atom("channel"), "to": _atom("bought")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "target": {"atom": _atom("bought"), "value": True},
                "intervention": {"atom": _atom("ad"), "value": True},
                "given": []}},
        ],
    }


def _campaign(*, treated_rate_in_last: float, n: int = 4000) -> pd.DataFrame:
    """The campaign reached channel 2 at this rate — or not at all."""
    rng = np.random.default_rng(19)
    channel = rng.choice([0, 1, 2], n, p=list(SHARE))
    p_ad = np.where(channel == 0, .55,
                    np.where(channel == 1, .45, treated_rate_in_last))
    ad = rng.random(n) < p_ad
    bought = rng.random(n) < np.clip(
        np.take(BASE, channel) + np.take(EFFECT, channel) * ad, 0, 1)
    return pd.DataFrame({"ad": ad, "bought": bought, "channel": channel})


def _separated(m: int = 450) -> pd.DataFrame:
    """Every stratum holds exactly one arm, and the true effect is zero."""
    rng = np.random.default_rng(19)
    channel = np.r_[np.zeros(m, int), np.ones(m, int)]
    bought = rng.random(2 * m) < np.where(channel == 0, .30, .55)
    return pd.DataFrame({"ad": channel == 0, "bought": bought,
                         "channel": channel})


def _overlap_gaps(result: dict) -> list[dict]:
    return [g for g in (result.get("data_gap_report") or {}).get("gaps", [])
            if g["kind"] == "propensity_overlap_violation"]


def _positivity_rows(result: dict) -> list[str]:
    assumptions = (result.get("numeric_estimate") or {}).get("assumptions", [])
    return [a for a in assumptions if "positivity" in a]


# --- why the two checks that existed could not see it -------------------------


def test_the_marginal_check_is_this_condition_summed_over_z():
    """``df[x].nunique() >= 2`` is true as soon as ANY stratum has both arms,
    which is exactly the situation this frame builds. It is not a weaker
    version of the per-stratum test; it is a different question."""
    df = _campaign(treated_rate_in_last=0.0)
    assert df["ad"].nunique() == 2                    # the old guard passes
    per_stratum = df.groupby("channel")["ad"].nunique()
    assert (per_stratum == 1).any()                   # and the fact it missed


def test_the_fitted_propensity_could_not_have_seen_it_either():
    """The gap's trigger was a fitted P(X=1|Z) leaving [0.05, 0.95]. A
    logistic fit smooths across cells, so the never-treated stratum — whose
    empirical rate is exactly zero — is handed a comfortable number and the
    threshold is never approached. Blind by construction, not by calibration."""
    from sklearn.linear_model import LogisticRegression

    df = _campaign(treated_rate_in_last=0.0)
    z = df[["channel"]].to_numpy(dtype=float)
    clf = LogisticRegression(max_iter=1000).fit(z, df["ad"].to_numpy().astype(int))
    fitted = clf.predict_proba(np.array([[2.0]]))[0, 1]

    assert df.loc[df.channel == 2, "ad"].mean() == 0.0
    assert 0.05 < fitted < 0.95, fitted


# --- what the count answers ---------------------------------------------------


def test_the_cells_are_counted_and_the_unsupported_one_is_named():
    df = _campaign(treated_rate_in_last=0.0)
    support = arm_support(df, "ad", ("channel",))

    assert support.enumerable
    assert (support.cells, support.supported) == (3, 2)
    assert support.one_armed == ({"channel": 2},)
    assert support.share == pytest.approx(0.251, abs=0.01)
    assert support.violated and not support.exhausted


def test_a_stratum_with_few_treated_rows_is_not_an_unsupported_one():
    """The counterexample the gate has to answer: thin is not empty. A rule
    that could not tell them apart would be a sample-size rule wearing a
    positivity name, and it would decline answers the data supports."""
    support = arm_support(_campaign(treated_rate_in_last=0.08), "ad",
                          ("channel",))
    assert support.supported == 3
    assert not support.violated


def test_a_continuous_adjustment_set_has_no_cells_to_count():
    """Every row is its own stratum, so a per-cell rule would refuse every run
    that regression adjustment exists to serve. The count declines to answer
    and the fitted witness is the only one there is."""
    rng = np.random.default_rng(0)
    df = pd.DataFrame({
        "ad": rng.random(500) < 0.5,
        "bought": rng.random(500) < 0.4,
        "z": rng.normal(size=500),
    })
    assert df["z"].nunique() > MAX_LEVELS
    assert not arm_support(df, "ad", ("z",)).enumerable


def test_a_short_frame_of_floats_is_not_twelve_strata():
    """Cardinality alone cannot tell a stratifier from a regressor.

    Twelve distinct floats in twelve rows sit under ``MAX_LEVELS``, so the
    cap — calibrated for whether a SATURATED formula can enumerate its
    strata — says yes; and reading them as strata finds every one of them
    single-armed, because a cell of one row cannot hold two arms however the
    treatment was assigned. What separates the two is rows per cell, and the
    number is not tuned: two is what "both arms are present" costs."""
    df = pd.DataFrame({
        "t": [True, False] * 6,
        "y": np.arange(12, dtype=float),
        "z": [0.1, -0.4, 0.9, 0.3, -0.2, 0.7, 0.5, -0.7, 0.2, 0.8, -0.3, 0.6],
    })
    assert df["z"].nunique() <= MAX_LEVELS          # the cap says yes
    assert not arm_support(df, "t", ("z",)).enumerable


# --- what the reader is told --------------------------------------------------


def test_the_ledger_stops_claiming_what_the_count_contradicts():
    """The row said "both treatment arms have units in every stratum of the
    adjustment set" on a frame where a quarter of the sample sits in a
    stratum that has one. Declaring it is worse than not checking: the reader
    takes the ledger as the list of things that were considered."""
    out = themis.estimate(_program(), _campaign(treated_rate_in_last=0.0),
                          ci_bootstrap=0)
    result = out["results"][0]
    assert _positivity_rows(result) == [
        "positivity_violated_some_strata_hold_one_arm"]


def test_the_reader_is_told_which_cell_and_how_much_of_the_sample():
    """"Positivity is violated" is not something a reader can act on. Which
    stratum, and how much of the answer rests on the model rather than on
    data, is."""
    out = themis.estimate(_program(), _campaign(treated_rate_in_last=0.0),
                          ci_bootstrap=0)
    gaps = _overlap_gaps(out["results"][0])
    assert len(gaps) == 1
    said = gaps[0]["description"]
    assert "channel=2" in said
    assert "25.1%" in said


def test_a_supported_frame_keeps_the_claim_and_raises_no_gap():
    """The other side of both gates at once."""
    out = themis.estimate(_program(), _campaign(treated_rate_in_last=0.08),
                          ci_bootstrap=0)
    result = out["results"][0]
    assert _positivity_rows(result) == ["positivity_overlap_of_treatment_arms"]
    assert _overlap_gaps(result) == []


@pytest.mark.parametrize("estimator", ["ipw", "aipw", "tmle"])
def test_the_propensity_estimators_declare_it_too(estimator):
    """Four functions build this row — ``backdoor._assumptions_for`` and one
    each in ``_assumptions_ipw`` / ``_assumptions_aipw`` / ``_assumptions_tmle``
    — and Winsorizing does not save them: the floor is applied to the FITTED
    score, so nothing is trimmed on the very frame where an arm is missing."""
    out = themis.estimate(_program(), _campaign(treated_rate_in_last=0.0),
                          ci_bootstrap=0, ate_estimator=estimator)
    result = out["results"][0]
    assert _positivity_rows(result) == [
        "positivity_violated_some_strata_hold_one_arm"]


# --- where answering stops being defensible -----------------------------------


def test_no_stratum_with_both_arms_is_refused_rather_than_answered():
    """Complete separation: channel 0 all treated, channel 1 all untreated.
    The treatment column varies, so every marginal guard passes, and there is
    no cell anywhere in which the two arms can be compared. Every term the
    formula needs came from the outcome model, so a point with an interval
    would be a confidence interval on a model's opinion — it measured
    -0.1445, CI [-0.1616, -0.0874], on data whose true effect is zero."""
    out = themis.estimate(_program((0, 1)), _separated(), ci_bootstrap=200)
    result = out["results"][0]

    failure = result["estimator_failure"]
    assert failure["failure_type"] == "no_within_stratum_contrast"
    assert result.get("numeric_estimate") is None
    assert failure["details"]["share"] == 1.0


def test_a_treatment_column_that_never_varies_is_still_the_other_species():
    """The neighbour on the same boundary, and the reason the two are not one
    check: with no contrast in the sample there is no stratum to name, and the
    reader's move is to go and get data rather than to look at a cell.

    It reaches the reader at all only because the back-door strategy now keeps
    the cascade's convention; before, this guard left ``themis.estimate`` as a
    traceback."""
    df = _campaign(treated_rate_in_last=0.0)
    df["ad"] = True
    result = themis.estimate(_program(), df, ci_bootstrap=0)["results"][0]
    assert result["estimator_failure"]["failure_type"] == "overlap_insufficient"
