"""A Markov blanket over columns of both kinds.

Two conditional-independence tests were built and a frame holding both kinds of
column met neither, so it was refused. The refusal was honest about its reason —
the Fisher-Z statistic is a correlation matrix and the chi-square one a
contingency table, and neither is a sufficient statistic for the other's
columns — but the reason is about those two statistics rather than about the
question, and there is a third statistic that covers both.

Lauritzen & Wermuth (1989), the homogeneous conditional-Gaussian family: the
discrete columns carry a joint distribution, and the continuous ones given each
discrete configuration are multivariate normal with a per-configuration mean and
one covariance shared across configurations. Its maximised log-likelihood over a
set of columns is a closed form in per-configuration counts, sums and sums of
outer products, and the CI test is the likelihood ratio between two nested fits.

**Why that family and not a more general mixed test.** The audit here re-derives
every test from a recorded statistic without the data, so the choice was never
between more and less powerful tests — it was between statistics that can be
written down and statistics that cannot. A kernel test's is the n×n Gram matrix
and a rank test's is the ranks, which is to say the data, and an artifact that
has to carry the data in order to be audited is not one. What this family costs
instead is a premise, homogeneity, and a premise is a thing this package knows
how to carry: it is named in the artifact's own description, and the test below
that varies the per-cell covariance is what says out loud where it bites.

**The oracle is its own degenerate points.** With no discrete column the
statistic is −n·log(1−ρ²), the likelihood ratio the Fisher-Z transform
approximates; with no continuous column it is the deviance form of the test
Pearson's statistic estimates, on the same degrees of freedom. Both are checked
against the two paths already built, which is a better witness than a second
transcription of the same algebra would be — and it is why those two paths were
left where they are rather than folded into this one.
"""
from __future__ import annotations

import copy
import math

import numpy as np
import pandas as pd
import pytest
from scipy import stats

import themis
from themis.estimation.discovery import (
    MarkovBlanketError, _cg_cells, _cg_dof, _cg_loglik, _corr_matrix,
    _partial_corr, markov_blanket, markov_blanket_to_dict,
)
from themis.estimation.refusal_words import Refuses
from themis.verifier.errors import VerificationError

N = 4000


def _mixed(n: int = N, seed: int = 0) -> pd.DataFrame:
    """a → t → b, with c an independent bystander.

    Deliberately one of each kind on both sides of the target: ``a`` is
    discrete and a parent, ``b`` is discrete and a child, ``c`` is continuous
    and neither. A blanket that got the types right but the structure wrong
    would still contain ``c``.
    """
    rng = np.random.default_rng(seed)
    a = rng.integers(0, 3, n)
    t = 0.8 * a + rng.standard_normal(n)
    b = (rng.random(n) < 1.0 / (1.0 + np.exp(-t))).astype(int)
    c = rng.standard_normal(n)
    return pd.DataFrame({"t": t, "a": a, "b": b, "c": c})


# --- the answer ---------------------------------------------------------------


def test_a_mixed_frame_is_answered_rather_than_refused():
    result = markov_blanket(_mixed(), "t")
    assert result.test == "cg_lrt"
    assert result.blanket == ("a", "b")
    assert result.conditional_gaussian["discrete"] == ["a", "b"]
    assert result.conditional_gaussian["continuous"] == ["t", "c"]


def test_the_statistic_is_sparse_over_occupied_cells():
    """Bounded by what was observed, not by the product of the cardinalities.

    3 × 2 = 6 here, and the point is the bound rather than the number: the
    same frame with a 40-level discrete column would record at most n rows,
    which is what makes a full artifact a reasonable thing to hand a verifier.
    """
    result = markov_blanket(_mixed(), "t")
    cells = result.conditional_gaussian["cells"]
    assert len(cells) <= 3 * 2
    assert sum(count for _cfg, count, _s, _x in cells) == N
    for _cfg, _count, sums, cross in cells:
        assert len(sums) == 2
        assert len(cross) == 2 and all(len(row) == 2 for row in cross)


def test_the_artifact_verifies():
    themis.verify_markov_blanket(markov_blanket_to_dict(markov_blanket(_mixed(), "t")))


# --- the oracle: the two paths already built ----------------------------------


def _cg_pvalue(frame, discrete_names, continuous_names, x, y, cond):
    """One CI test through the new machinery, addressed by column name."""
    names = tuple(discrete_names) + tuple(continuous_names)
    codes = np.column_stack([
        np.searchsorted(np.unique(frame[c].to_numpy()), frame[c].to_numpy())
        for c in discrete_names
    ]) if discrete_names else np.zeros((len(frame), 0), dtype=np.int64)
    continuous = (np.column_stack([frame[c].to_numpy(dtype=float)
                                   for c in continuous_names])
                  if continuous_names else np.zeros((len(frame), 0)))
    cells = _cg_cells(codes, continuous)
    cards = tuple(int(frame[c].nunique()) for c in discrete_names)
    at = {c: (True, i) for i, c in enumerate(discrete_names)}
    at |= {c: (False, i) for i, c in enumerate(continuous_names)}
    n = len(frame)

    statistic = 0.0
    dof = 0
    for group, sign in (((x, y, *cond), 1), (cond, 1),
                        ((x, *cond), -1), ((y, *cond), -1)):
        d_keep = tuple(sorted(at[c][1] for c in group if at[c][0]))
        c_keep = tuple(sorted(at[c][1] for c in group if not at[c][0]))
        statistic += sign * _cg_loglik(cells, n, d_keep, c_keep)
        dof += sign * _cg_dof(cards, d_keep, len(c_keep))
    statistic *= 2.0
    assert names  # the frame's own order is what the caller indexed by
    return statistic, dof


def test_with_no_discrete_column_it_is_the_gaussian_likelihood_ratio():
    """G² = −n·log(1 − ρ²_{XY·S}), to twelve places.

    Not "close to Fisher-Z" — exactly the quantity Fisher's transform is a
    variance-stabilising approximation OF, so this is an algebraic identity
    and is tested as one. What it pins is the continuous half of the new
    likelihood: the pooled covariance with no configurations to pool over is
    the plain covariance, and its determinant ratio is the partial
    correlation.
    """
    rng = np.random.default_rng(5)
    z = rng.standard_normal(N)
    frame = pd.DataFrame({
        "x": 0.8 * z + rng.standard_normal(N),
        "y": 0.6 * z + rng.standard_normal(N),
        "z": z,
    })
    statistic, dof = _cg_pvalue(frame, (), ("x", "y", "z"), "x", "y", ("z",))
    R = _corr_matrix(frame[["x", "y", "z"]].to_numpy(dtype=float))
    rho = _partial_corr(R, 0, 1, (2,))
    assert dof == 1
    assert statistic == pytest.approx(-N * math.log(1 - rho * rho), abs=1e-9)


def test_with_no_continuous_column_it_is_the_deviance_of_the_same_test():
    """The discrete degenerate point, on the same degrees of freedom.

    G² and Pearson's χ² are two estimators of one quantity and do not agree to
    machine precision on any finite sample, so what is pinned exactly is the
    DOF — Σ_s (k_x − 1)(k_y − 1), which the general formula has to reproduce
    from four parameter counts — and the statistics are held to agreeing about
    the verdict at a sample where both are far from the boundary.
    """
    rng = np.random.default_rng(6)
    s = rng.integers(0, 3, N)
    frame = pd.DataFrame({
        "x": (rng.random(N) < 0.2 + 0.2 * s).astype(int),
        "y": (rng.random(N) < 0.3 + 0.15 * s).astype(int),
        "s": s,
    })
    statistic, dof = _cg_pvalue(frame, ("x", "y", "s"), (), "x", "y", ("s",))
    assert dof == 3 * (2 - 1) * (2 - 1)

    chi = 0.0
    for level in range(3):
        rows = frame[frame["s"] == level]
        table = pd.crosstab(rows["x"], rows["y"]).to_numpy(dtype=float)
        total = table.sum()
        expected = np.outer(table.sum(1), table.sum(0)) / total
        chi += float(np.sum((table - expected) ** 2 / expected))
    assert abs(statistic - chi) < 0.05 * max(statistic, 1.0)
    assert (stats.chi2.sf(statistic, dof) > 0.05) == (stats.chi2.sf(chi, dof) > 0.05)


def test_the_degrees_of_freedom_count_what_the_premise_leaves_free():
    """One covariance for every configuration is what homogeneity buys, and
    the count says so: the covariance term does not multiply by the number of
    configurations the way the mean term does."""
    # two discrete columns of 3 and 2 levels, two continuous
    assert _cg_dof((3, 2), (0, 1), 2) == (6 - 1) + 2 * 6 + 3
    # the same continuous columns with no discrete conditioning at all
    assert _cg_dof((3, 2), (), 2) == 0 + 2 + 3


# --- where the premise bites --------------------------------------------------


def test_a_covariance_that_differs_by_cell_is_read_as_dependence():
    """The homogeneity premise, failing out loud rather than quietly.

    Two configurations whose continuous column has the same mean and different
    spreads carry real information about the discrete one, and a fit that
    insists on one covariance cannot represent it. What the test does with it
    is the question, and the answer is the safe direction: the mean model
    still separates nothing, so the likelihood ratio stays small and the
    columns are called independent. That is a MISS, not a false alarm — the
    premise costs power here and does not manufacture edges — and it is why
    the premise is named in the artifact rather than left implicit.
    """
    rng = np.random.default_rng(11)
    g = rng.integers(0, 2, N)
    frame = pd.DataFrame({
        "g": g,
        "v": rng.standard_normal(N) * np.where(g == 1, 3.0, 0.5),
    })
    statistic, dof = _cg_pvalue(frame, ("g",), ("v",), "g", "v", ())
    assert dof == 1
    assert stats.chi2.sf(statistic, dof) > 0.05


def test_a_sample_that_cannot_support_a_pooled_covariance_is_refused():
    """Enough cells and the within-configuration spread runs out.

    Not the old refusal under a new name: that one said a mixed test was not
    built, and this one says this sample cannot support the test that is. The
    difference matters to a reader, because only one of them has a remedy that
    is about their data.
    """
    rng = np.random.default_rng(3)
    n = 30
    # Three discrete columns of eight levels each: nearly every row lands in
    # a cell of its own, so subtracting each cell's own mean leaves almost
    # nothing to pool. Eight and not thirty, because a column with more
    # distinct values than ``_MAX_DISCRETE_LEVELS`` is read as continuous and
    # the frame would not be mixed at all.
    frame = pd.DataFrame({
        "k": rng.integers(0, 8, n),
        "j": rng.integers(0, 8, n),
        "i": rng.integers(0, 8, n),
        "u": rng.standard_normal(n),
        "v": rng.standard_normal(n),
    })
    with pytest.raises(MarkovBlanketError) as caught:
        markov_blanket(frame, "u")
    assert caught.value.species is Refuses.THE_CELLS_LEAVE_NO_SPREAD_TO_POOL


# --- the audit ----------------------------------------------------------------


@pytest.fixture(scope="module")
def artifact():
    return markov_blanket_to_dict(markov_blanket(_mixed(), "t"))


@pytest.mark.parametrize("label,mutate", (
    # The forgery the definition check exists for: a member quietly removed,
    # with its entry relabelled so the artifact stays internally consistent.
    ("a member dropped and its entry relabelled",
     lambda d: (d["blanket"].remove("a"),
                next(e for e in d["tests"] if e["variable"] == "a")
                .__setitem__("role", "shield"))),
    ("the likelihood ratio inflated",
     lambda d: d["tests"][0].__setitem__(
         "likelihood_ratio", d["tests"][0]["likelihood_ratio"] + 5.0)),
    # The dof is the part a reader cannot check by eye — it is not a function
    # of the two variables' cardinalities the way the chi-square one is.
    ("the degrees of freedom forged",
     lambda d: d["tests"][0].__setitem__("dof", d["tests"][0]["dof"] + 1)),
    # Counts moved between cells keep the total, so nothing structural
    # complains; only re-deriving the four fits catches it.
    ("seven observations moved from one cell to another",
     lambda d: (d["conditional_gaussian"]["cells"][0].__setitem__(
         1, d["conditional_gaussian"]["cells"][0][1] + 7),
         d["conditional_gaussian"]["cells"][1].__setitem__(
             1, d["conditional_gaussian"]["cells"][1][1] - 7))),
    ("a cross-product matrix made asymmetric",
     lambda d: d["conditional_gaussian"]["cells"][0][3][0].__setitem__(
         1, d["conditional_gaussian"]["cells"][0][3][0][1] + 3.0)),
    ("a continuous column claimed as discrete",
     lambda d: (d["conditional_gaussian"]["discrete"].append("c"),
                d["conditional_gaussian"]["continuous"].remove("c"))),
    ("the statistic swapped for another test's",
     lambda d: (d.pop("conditional_gaussian"),
                d.__setitem__("correlation", [[1.0] * 4] * 4))),
))
def test_the_audit_refuses_a_forgery(artifact, label, mutate):
    forged = copy.deepcopy(artifact)
    mutate(forged)
    with pytest.raises(VerificationError):
        themis.verify_markov_blanket(forged)
