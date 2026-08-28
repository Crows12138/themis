"""A proximal ATE used to leave through an audit of its own description.

``numeric_proximal_estimate`` checked that the method was in an enum, that
the hash was 64 lowercase hex characters, that the sample size was an int,
that the point was a number, and that a recorded confidence interval
bracketed it. Every one of those is a fact about the block's shape. None of
them is the number.

Measured before this file existed: a point of 0.334 moved to 0.634 — wrong
by ninety per cent — passed ``themis.verify`` and all five audits. With no
interval recorded there was nothing the number had to agree with, and with
one it only had to sit inside an interval the same producer wrote.

**The fix is what the estimate carries, not a stricter reading of what it
already carried.** Miao's formula (5) is a matrix inversion of the Z×W
measurement channel, and that channel is a contingency table — so the
estimate records the table, as COUNTS, and the rule runs the formula again.
Counts and not the conditionals they normalise to: all a second pass can ask
of a probability is whether it lies in [0, 1], while a count has to sum to
its stratum, the strata have to sum to the sample, and the sample has to be
the one the data hash stands for. Each of those is an arithmetic identity
somebody editing one number has to satisfy at the same time.

The declared boundary: the re-derivation shares ``numpy.linalg.solve`` with
the producer. What is being independently re-derived is the formula and the
statistics it stands on, not the arithmetic of Gaussian elimination.
"""
from __future__ import annotations

import copy

import numpy as np
import pandas as pd
import pytest

import themis
from themis.verifier import VerificationError

#: The one path a proximal number can leave by, and therefore the only step
#: this file has to be able to reach.
_STEP = "numeric_proximal_estimate"


# --- the corpus ---------------------------------------------------------------

def _var(p):
    return {"kind": "variable", "predicate": p, "domain": [True, False]}


def _cause(a, b):
    return {"kind": "cause", "from": {"predicate": a, "args": []},
            "to": {"predicate": b, "args": []}}


def _atom(p):
    return {"predicate": p, "args": []}


def _program(k: int = 2) -> dict:
    """Miao model (f): U→{X,Y,Z,W}, Z→X, W→Y, X→Y, with U unobserved."""
    return {
        "version": "0.1",
        "domain": {"objects": []},
        "statements": [
            _var("x"), _var("y"), _var("u"), _var("z"), _var("w"),
            _cause("u", "x"), _cause("u", "y"), _cause("u", "z"),
            _cause("u", "w"), _cause("z", "x"), _cause("w", "y"),
            _cause("x", "y"),
            {"kind": "query", "id": "q", "query": {
                "kind": "proximal_effect",
                "treatment": _atom("x"), "outcome": _atom("y"),
                "latent": _atom("u"), "treatment_proxy": _atom("z"),
                "outcome_proxy": _atom("w"),
                "channel": {"kind": "discrete_channel",
                            "latent_cardinality": k}}},
        ],
    }


def _sample(n: int = 1500, seed: int = 0) -> pd.DataFrame:
    """A latent-U SCM the proxies can restore the effect through."""
    rng = np.random.default_rng(seed)
    u = rng.random(n) < 0.5
    z = rng.random(n) < np.where(u, 0.80, 0.20)
    w = rng.random(n) < np.where(u, 0.85, 0.25)
    x = rng.random(n) < np.where(u, np.where(z, 0.80, 0.55),
                                 np.where(z, 0.50, 0.20))
    y = rng.random(n) < (0.15 + 0.35 * x + 0.25 * u + 0.15 * w)
    return pd.DataFrame({"x": x, "y": y, "z": z, "w": w})


@pytest.fixture(scope="module")
def truthful() -> dict:
    out = themis.estimate(_program(), _sample(), ci_bootstrap=0)
    return out["results"][0]


def _step(result: dict) -> dict:
    """The one derivation step a proximal number rests on."""
    for step in result["derivation"]["steps"]:
        if step.get("rule") == _STEP:
            return step
    raise AssertionError(f"no {_STEP} step in this derivation")


def _channel(step: dict) -> dict:
    """The recorded table, as it sits in the serialized derivation."""
    return step["inputs"]["measurement_channel"]["items"]


def _doctored(result: dict):
    """A deep copy plus its step and channel, ready to be edited."""
    forged = copy.deepcopy(result)
    step = _step(forged)
    return forged, step, _channel(step)


def _refused(forged: dict) -> str:
    """What ``verify`` says about a doctored envelope. Fails if it says yes."""
    with pytest.raises(VerificationError) as raised:
        themis.verify(_program(), forged)
    return str(raised.value)


# --- the number is a number this file can reach -------------------------------

def test_a_truthful_estimate_verifies(truthful):
    """The denominator. A rule that rejected everything would pass every
    counterexample below and be useless."""
    assert truthful["status"] == "numerically_solved"
    themis.verify(_program(), truthful)


def test_the_estimate_carries_the_table_it_was_inverted_from(truthful):
    """A scan that reached nothing would make every rule below vacuous.

    The counts are what the re-derivation is possible from, so their being
    there is the precondition rather than a detail of the encoding.
    """
    channel = _channel(_step(truthful))
    assert set(channel) >= {"z_levels", "w_levels", "n_total",
                            "w_marginal_counts", "treated", "control"}
    k = len(channel["z_levels"]["items"])
    assert k >= 2
    for arm in ("treated", "control"):
        rows = channel[arm]["items"]
        assert len(rows) == k
        for row in rows:
            cell = row["items"]
            counts = [c for c in cell["w_counts"]["items"]]
            assert len(counts) == k
            assert sum(counts) == cell["n"]


def test_the_recorded_sample_is_the_sample_the_estimate_names(truthful):
    """Every row sits in exactly one arm and one Z stratum, so the strata
    cover the sample exactly. That identity is what makes a dropped stratum
    visible; it is asserted on the truthful envelope so that the rule
    checking it downstream is checking something that holds."""
    channel = _channel(_step(truthful))
    n_total = channel["n_total"]
    assert n_total == truthful["numeric_estimate"]["sample_size"]
    assert sum(channel["w_marginal_counts"]["items"]) == n_total
    covered = sum(
        row["items"]["n"]
        for arm in ("treated", "control")
        for row in channel[arm]["items"]
    )
    assert covered == n_total


# --- what each rule says no to ------------------------------------------------
#
# One doctored envelope per rule, each edited the way the defect it names
# would arrive, and each asserted to be refused NAMING ITS OWN CASE — two
# rules that both reject with "invalid" are one rule as far as anybody
# reading the failure is concerned.

def test_a_forged_point_is_refused(truthful):
    """The measurement this file exists for: 0.334 → 0.634 used to pass."""
    forged, step, _ = _doctored(truthful)
    moved = round(forged["numeric_estimate"]["point"] + 0.30, 6)
    forged["numeric_estimate"]["point"] = moved
    step["inputs"]["point"] = moved
    assert "re-deriving formula (5)" in _refused(forged)


def test_a_forged_arm_is_refused(truthful):
    """The ATE is a difference, so a point can be right while an arm is
    invented — and the two arms are what a reader is shown."""
    forged, step, _ = _doctored(truthful)
    step["inputs"]["do_prob_treated"] += 0.2
    assert "do_prob_treated" in _refused(forged)


def test_a_stratum_whose_counts_stop_summing_is_refused(truthful):
    """The W row of a stratum has to account for every row in it."""
    forged, step, channel = _doctored(truthful)
    channel["treated"]["items"][0]["items"]["w_counts"]["items"][0] += 7
    assert "W counts sum to" in _refused(forged)


def test_a_dropped_stratum_is_refused(truthful):
    """M has one column per Z level; a table one column short is not the
    channel this estimate inverted."""
    forged, step, channel = _doctored(truthful)
    channel["control"]["items"] = channel["control"]["items"][:-1]
    assert "one record per Z level" in _refused(forged)


def test_a_stratum_rescaled_into_internal_consistency_is_refused(truthful):
    """The edit that survives every local check.

    Doubling one stratum's ``n`` and its W counts together leaves the row
    summing correctly and the conditionals unchanged — it is the sample
    that no longer adds up. Which is why the rule counts rows across BOTH
    arms against the sample size rather than checking each row alone.
    """
    forged, step, channel = _doctored(truthful)
    row = channel["treated"]["items"][0]["items"]
    row["n"] *= 2
    row["w_counts"]["items"] = [c * 2 for c in row["w_counts"]["items"]]
    row["y_count"] *= 2
    assert "dropped stratum" in _refused(forged)


def test_a_tampered_marginal_is_refused(truthful):
    """P(W) is the vector the inverted channel is applied to, so moving it
    moves the answer while every stratum still balances."""
    forged, step, channel = _doctored(truthful)
    channel["w_marginal_counts"]["items"][0] += 25
    assert "W marginal sums to" in _refused(forged)


def test_strata_recorded_out_of_order_are_refused(truthful):
    """A column of M standing where another one's inverse will be applied.

    Nothing about the counts themselves is wrong here — they are the same
    numbers. What is wrong is which Z level each column is for, which is a
    fact only the labels carry.
    """
    forged, step, channel = _doctored(truthful)
    rows = channel["treated"]["items"]
    rows[0], rows[1] = rows[1], rows[0]
    assert "same order" in _refused(forged)


def test_a_table_from_another_sample_is_refused(truthful):
    """The hash names a dataset; the table has to be of that dataset."""
    forged, step, channel = _doctored(truthful)
    channel["n_total"] += 1
    assert "not the same sample" in _refused(forged)


def test_an_estimate_with_no_table_is_refused(truthful):
    """The shape the old rule accepted: a point and its description.

    Kept as a case because it is what every envelope written before this
    looks like, and because "the statistics are optional" is the one edit
    that would quietly restore the hole.
    """
    forged, step, _ = _doctored(truthful)
    del step["inputs"]["measurement_channel"]
    said = _refused(forged)
    assert "measurement_channel" in said


def test_a_channel_that_fails_the_rank_condition_is_refused(truthful):
    """The estimate claims P(W|Z,x) is invertible; the table has to show it.

    Every Z stratum sitting entirely at one W level is a channel that says
    nothing about U — M has identical columns, is exactly singular, and the
    estimator refuses it on the data. Each row still sums to its stratum and
    the strata still cover the sample, so this is the case the arithmetic
    identities cannot see and only the rank condition can.

    Exactly singular rather than nearly so, which is what integer counts
    give: with n in the hundreds the smallest non-zero gap between two
    columns keeps the condition number near 10³, far under any threshold.
    That is also why the rank test runs before the solve — a singular matrix
    makes the solver raise, and this case is what found it.
    """
    forged, step, channel = _doctored(truthful)
    for row in channel["treated"]["items"]:
        cell = row["items"]
        cell["w_counts"]["items"] = [cell["n"]] + [0] * (
            len(cell["w_counts"]["items"]) - 1)
    assert "rank condition" in _refused(forged)


# --- the bootstrap path still walks the same transcription --------------------

def test_a_resampled_interval_still_verifies():
    """The producer's two halves — the counts and the formula — are composed
    for the bootstrap too, so a draw cannot walk a second transcription that
    the recorded point is then compared against."""
    out = themis.estimate(_program(), _sample(), ci_bootstrap=40)
    result = out["results"][0]
    estimate = result["numeric_estimate"]
    assert estimate["ci_lower"] is not None
    assert estimate["ci_lower"] <= estimate["point"] <= estimate["ci_upper"]
    themis.verify(_program(), result)
