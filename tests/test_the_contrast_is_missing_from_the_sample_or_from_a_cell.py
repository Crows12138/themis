"""Three answers on one boundary, and one function that gave two of them.

``insufficient_support`` and ``overlap_insufficient`` were written as a pair
— "what is missing: rows, or a difference" — and thirteen sites filed the
second while stating three different facts under it. The one in the middle
is the one an estimator has to be able to say on its own: a stratum that
holds rows and a single treatment arm.

It is in the middle because it is the only one of the three where refusing
and answering are BOTH defensible. A column that never varies cannot be
estimated from at all. A cell with no rows contributes a term that does not
exist. A cell with one arm sits among cells that have both, so a regression
fills it from their slope and returns a number — which is a modelling
choice, and an estimator that makes it silently is claiming the data said
something it did not.

``backdoor_do_risk`` is where that shows: its two guards are two of the
three facts, and until this split both filed ``insufficient_support``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis import refusals
from themis.estimation.binary_do_risk import backdoor_do_risk
from themis.refusals import EstimatorFailure, Refusal

N = 900
#: The last channel was never advertised to. Every other channel was.
SHARE = (0.40, 0.35, 0.25)


def _sample(*, treated_rate_in_last: float):
    rng = np.random.default_rng(19)
    channel = rng.choice([0, 1, 2], N, p=list(SHARE))
    p_ad = np.where(channel == 0, .55,
                    np.where(channel == 1, .45, treated_rate_in_last))
    x = rng.random(N) < p_ad
    y = rng.random(N) < .4
    return x, y, pd.DataFrame({"channel": channel})


def test_a_column_that_never_varies_is_the_whole_samples_problem():
    """No rows at this arm ANYWHERE. Nothing in the data can be adjusted to
    reach it and no model can be fitted across it, so the reader's move is
    to go and get data rather than to look at a cell."""
    x = np.zeros(N, dtype=bool)
    y = np.ones(N, dtype=bool)
    with pytest.raises(EstimatorFailure) as exc:
        backdoor_do_risk(x, y, pd.DataFrame(index=range(N)), (),
                         arm=True, treatment="x")
    assert exc.value.failure_type == Refusal.OVERLAP_INSUFFICIENT


def test_a_stratum_that_holds_one_arm_is_that_cells_problem():
    """The sample HAS both arms — the marginal check that guards the
    regression paths passes on this very frame — and one cell does not."""
    x, y, frame = _sample(treated_rate_in_last=0.0)
    assert len(np.unique(x)) == 2, "the sample's contrast is there"

    with pytest.raises(EstimatorFailure) as exc:
        backdoor_do_risk(x, y, frame, ("channel",), arm=True, treatment="x")
    assert exc.value.failure_type == Refusal.NO_WITHIN_STRATUM_CONTRAST


def test_the_cell_is_named_because_positivity_alone_is_not_actionable():
    """"A positivity violation" tells a reader that something is wrong and
    not where. The stratum is the part they can go and do something about,
    so it is in ``details`` as data and in the sentence as a cell."""
    x, y, frame = _sample(treated_rate_in_last=0.0)
    with pytest.raises(EstimatorFailure) as exc:
        backdoor_do_risk(x, y, frame, ("channel",), arm=True, treatment="x")

    assert exc.value.details["strata"] == [{"channel": 2}]
    assert "channel=2" in str(exc.value)


def test_a_thin_stratum_is_not_an_empty_one():
    """The counterexample for the guard: few treated rows is not no treated
    rows, and a check that could not tell them apart would be a sample-size
    rule wearing a positivity name."""
    x, y, frame = _sample(treated_rate_in_last=0.08)
    assert frame.groupby("channel").apply(
        lambda g: x[g.index].sum(), include_groups=False).min() > 0
    backdoor_do_risk(x, y, frame, ("channel",),
                     arm=True, treatment="x")                  # answers


def test_the_three_do_not_share_a_definition():
    """A species is a claim about what is missing, so the three have to be
    telling three different people to do three different things. They are
    kept apart here rather than only in prose because the last time these
    definitions were a pair, four sites stated each other's."""
    said = {
        s: refusals.Refusal(s).says
        for s in ("insufficient_support", "overlap_insufficient",
                  "no_within_stratum_contrast")
    }
    assert len(set(said.values())) == 3
    assert "no rows" in said["insufficient_support"]
    assert "ANYWHERE" in said["overlap_insufficient"]
    assert "only one level" in said["no_within_stratum_contrast"]
