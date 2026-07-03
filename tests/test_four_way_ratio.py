"""Ratio-scale (excess relative risk) four-way decomposition — VanderWeele
2014 eAppendix §3.4 (binary outcome + binary mediator).

The difference-scale decomposition (test_four_way_decomposition.py) is a
pure computation over standardized cell means and collapses to a linear
combination of p_am / q_a. The RATIO-scale decomposition does NOT: for a
binary outcome the components are functions of the logistic outcome /
mediator coefficients (logistic non-collapsibility), so this estimator
FITS both models and evaluates VanderWeele's closed form.

Validation strategy (no oracle library):
- structural identities the closed form must satisfy exactly (the four
  ERR pieces sum to the total excess relative risk; raw components sum to
  total_rr − 1; proportions sum to 1);
- structural vanishing (no exposure→mediator edge ⇒ no mediation; outcome
  independent of the mediator ⇒ only the CDE survives);
- a SECOND independent transcription of the eAppendix formulas, factored
  differently, agreeing to 1e-10;
- recovery of the decomposition from data simulated at known coefficients;
- estimator guards + cluster-bootstrap parity.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from themis.estimation.dose_response import EstimatorFailure
from themis.estimation.four_way import four_way_ratio_decomposition
from themis.estimation.four_way_ratio import (
    FourWayRatioEstimate,
    estimate_four_way_ratio,
)


# ---------------------------------------------------------------------------
# Second independent transcription of VanderWeele eAppendix §3.4
# ---------------------------------------------------------------------------


def _g(x: float) -> float:
    return 1.0 + math.exp(x)


def _independent_ratio(t1, t2, t3, b0, b1, bcc=0.0, a1=1.0, a0=0.0, mstar=0.0):
    """Re-typed from the eAppendix, factored through named 1+exp(·) building
    blocks (a different code structure than the producer's inline form)."""
    A0 = _g(b0 + b1 * a0 + bcc)
    A1 = _g(b0 + b1 * a1 + bcc)
    A0_00 = _g(b0 + b1 * a0 + bcc + t2 + t3 * a0)
    A0_01 = _g(b0 + b1 * a0 + bcc + t2 + t3 * a1)
    A1_11 = _g(b0 + b1 * a1 + bcc + t2 + t3 * a1)
    A1_10 = _g(b0 + b1 * a1 + bcc + t2 + t3 * a0)
    eT1 = math.exp(t1 * (a1 - a0))
    eCDEhi = math.exp(t1 * (a1 - a0) + t2 * mstar + t3 * a1 * mstar)
    eCDElo = math.exp(t2 * mstar + t3 * a0 * mstar)

    cde = eCDEhi * A0 / A0_00 - eCDElo * A0 / A0_00
    intref = eT1 * A0_01 / A0_00 - 1.0 - eCDEhi * A0 / A0_00 + eCDElo * A0 / A0_00
    intmed = (
        eT1 * A1_11 * A0 / (A0_00 * A1)
        - A1_10 * A0 / (A0_00 * A1)
        - eT1 * A0_01 / A0_00
        + 1.0
    )
    pie = A0 * A1_10 / (A1 * A0_00) - 1.0
    total = math.exp(t1 * a1) * A0 * A1_11 / (math.exp(t1 * a0) * A1 * A0_00)
    return cde, intref, intmed, pie, total


# ---------------------------------------------------------------------------
# Oracle: structural identities
# ---------------------------------------------------------------------------


def test_four_err_pieces_sum_to_total_err():
    c = four_way_ratio_decomposition(t1=0.7, t2=0.5, t3=0.6, b0=-0.3, b1=1.1, bcc=0.2)
    s = c.err_cde + c.err_intref + c.err_intmed + c.err_pie
    assert s == pytest.approx(c.total_err, abs=1e-12)


def test_raw_components_sum_to_total_rr_minus_one():
    """The binary/binary identity terr ≡ total_rr − 1 — a strong internal
    consistency check on the whole transcription (a typo in one of the four
    component formulas or the total formula breaks it)."""
    rng = np.random.default_rng(1)
    for _ in range(500):
        p = rng.uniform(-2, 2, 5)
        c = four_way_ratio_decomposition(
            t1=p[0], t2=p[1], t3=p[2], b0=p[3], b1=p[4], bcc=rng.uniform(-1, 1))
        terr = c.cde_comp + c.intref_comp + c.intmed_comp + c.pie_comp
        assert terr == pytest.approx(c.total_rr - 1.0, rel=1e-10, abs=1e-10)


def test_proportions_sum_to_one():
    c = four_way_ratio_decomposition(t1=0.9, t2=0.4, t3=0.7, b0=-0.5, b1=1.3, bcc=-0.1)
    assert (c.prop_cde + c.prop_intref + c.prop_intmed + c.prop_pie
            == pytest.approx(1.0, abs=1e-12))


def test_no_exposure_mediator_edge_kills_mediation():
    """b1 = 0 (exposure does not affect the mediator) ⇒ both mediation
    components (mediated interaction, pure indirect) vanish exactly."""
    c = four_way_ratio_decomposition(t1=0.7, t2=0.5, t3=0.6, b0=-0.3, b1=0.0, bcc=0.2)
    assert c.intmed_comp == pytest.approx(0.0, abs=1e-12)
    assert c.pie_comp == pytest.approx(0.0, abs=1e-12)
    assert c.err_intmed == pytest.approx(0.0, abs=1e-12)
    assert c.err_pie == pytest.approx(0.0, abs=1e-12)


def test_outcome_independent_of_mediator_leaves_only_cde():
    """t2 = t3 = 0 (outcome does not depend on the mediator) ⇒ only the CDE
    survives; all interaction and mediation pieces are zero."""
    c = four_way_ratio_decomposition(t1=0.7, t2=0.0, t3=0.0, b0=-0.3, b1=1.1, bcc=0.2)
    assert c.intref_comp == pytest.approx(0.0, abs=1e-12)
    assert c.intmed_comp == pytest.approx(0.0, abs=1e-12)
    assert c.pie_comp == pytest.approx(0.0, abs=1e-12)
    assert c.cde_comp == pytest.approx(c.total_err, abs=1e-12)


def test_matches_second_independent_transcription():
    rng = np.random.default_rng(7)
    for _ in range(300):
        t1, t2, t3, b0, b1 = rng.uniform(-1.5, 1.5, 5)
        bcc = rng.uniform(-0.8, 0.8)
        c = four_way_ratio_decomposition(t1=t1, t2=t2, t3=t3, b0=b0, b1=b1, bcc=bcc)
        cde, intref, intmed, pie, total = _independent_ratio(
            t1, t2, t3, b0, b1, bcc)
        assert c.cde_comp == pytest.approx(cde, abs=1e-10)
        assert c.intref_comp == pytest.approx(intref, abs=1e-10)
        assert c.intmed_comp == pytest.approx(intmed, abs=1e-10)
        assert c.pie_comp == pytest.approx(pie, abs=1e-10)
        assert c.total_rr == pytest.approx(total, abs=1e-10)


def test_mstar_shifts_cde_reference():
    """Fixing the mediator at m*=1 vs m*=0 gives a different controlled
    direct effect whenever there is an A·M interaction (t3 ≠ 0)."""
    c0 = four_way_ratio_decomposition(t1=0.7, t2=0.5, t3=0.6, b0=-0.3, b1=1.1, mstar=0.0)
    c1 = four_way_ratio_decomposition(t1=0.7, t2=0.5, t3=0.6, b0=-0.3, b1=1.1, mstar=1.0)
    assert c0.err_cde != pytest.approx(c1.err_cde, abs=1e-6)
    # The TOTAL effect is invariant to the CDE reference level.
    assert c0.total_rr == pytest.approx(c1.total_rr, abs=1e-12)


# ---------------------------------------------------------------------------
# Estimator: recovery from simulated data
# ---------------------------------------------------------------------------


def _sim(seed, n=20000, *, t0=-0.8, t1=0.7, t2=0.5, t3=0.6, b0=-0.4, b1=1.0,
         zc=0.3, tz=0.5, with_cluster=False, G=200):
    def expit(x):
        return 1 / (1 + np.exp(-x))
    rng = np.random.default_rng(seed)
    if with_cluster:
        per = n // G
        clu = np.repeat(np.arange(G), per)
        z = rng.standard_normal(G)[clu]
        a = np.repeat((rng.random(G) < expit(0.5 * rng.standard_normal(G))), per).astype(float)
        u = rng.standard_normal(G)[clu] * 0.0  # confounding via z only
        m = (rng.random(len(clu)) < expit(b0 + b1 * a + zc * z)).astype(float)
        y = (rng.random(len(clu)) < expit(t0 + t1 * a + t2 * m + t3 * a * m + tz * z)).astype(float)
        return pd.DataFrame({"a": a.astype(bool), "m": m.astype(bool),
                             "y": y.astype(bool), "z": z, "fam": clu})
    z = rng.standard_normal(n)
    a = (rng.random(n) < expit(0.5 * z)).astype(float)
    m = (rng.random(n) < expit(b0 + b1 * a + zc * z)).astype(float)
    y = (rng.random(n) < expit(t0 + t1 * a + t2 * m + t3 * a * m + tz * z)).astype(float)
    return pd.DataFrame({"a": a.astype(bool), "m": m.astype(bool),
                         "y": y.astype(bool), "z": z})


def test_estimator_recovers_coefficients_and_decomposition():
    df = _sim(0)
    est = estimate_four_way_ratio(
        df, treatment="a", outcome="y", mediator="m", adjustment=("z",),
        ci_bootstrap=0)
    # Fitted coefficients ≈ truth.
    assert est.t1 == pytest.approx(0.7, abs=0.12)
    assert est.t2 == pytest.approx(0.5, abs=0.12)
    assert est.t3 == pytest.approx(0.6, abs=0.15)
    assert est.b1 == pytest.approx(1.0, abs=0.12)
    # The reported decomposition equals the oracle at the fitted coefficients.
    oracle = four_way_ratio_decomposition(
        t1=est.t1, t2=est.t2, t3=est.t3, b0=est.b0, b1=est.b1, bcc=est.bcc)
    assert est.err_cde_point == pytest.approx(oracle.err_cde, abs=1e-9)
    assert est.err_pie_point == pytest.approx(oracle.err_pie, abs=1e-9)
    assert est.total_rr_point == pytest.approx(oracle.total_rr, abs=1e-9)
    # Sum identity survives estimation.
    s = (est.err_cde_point + est.err_intref_point
         + est.err_intmed_point + est.err_pie_point)
    assert s == pytest.approx(est.total_err_point, abs=1e-9)


def test_estimator_bootstrap_ci_covers_point():
    df = _sim(1, n=6000)
    est = estimate_four_way_ratio(
        df, treatment="a", outcome="y", mediator="m", adjustment=("z",),
        ci_bootstrap=200, random_state=3)
    for lo, pt, hi in [
        (est.err_pie_ci_lower, est.err_pie_point, est.err_pie_ci_upper),
        (est.total_rr_ci_lower, est.total_rr_point, est.total_rr_ci_upper),
        (est.prop_mediated_ci_lower, est.prop_mediated_point, est.prop_mediated_ci_upper),
    ]:
        assert lo is not None and hi is not None
        assert lo <= pt <= hi


def test_estimator_deterministic():
    df = _sim(2, n=4000)
    kw = dict(treatment="a", outcome="y", mediator="m", adjustment=("z",),
              ci_bootstrap=80, random_state=9)
    a = estimate_four_way_ratio(df, **kw)
    b = estimate_four_way_ratio(df, **kw)
    assert a.err_cde_ci_lower == b.err_cde_ci_lower
    assert a.total_rr_point == b.total_rr_point


# ---------------------------------------------------------------------------
# Estimator: guards
# ---------------------------------------------------------------------------


def test_continuous_outcome_rejected():
    df = _sim(3, n=2000)
    df = df.assign(ycont=np.random.default_rng(0).standard_normal(len(df)))
    with pytest.raises(EstimatorFailure) as e:
        estimate_four_way_ratio(df, treatment="a", outcome="ycont",
                                mediator="m", ci_bootstrap=0)
    assert e.value.failure_type == "outcome_not_binary"


def test_continuous_mediator_rejected():
    df = _sim(4, n=2000)
    df = df.assign(mcont=np.random.default_rng(1).standard_normal(len(df)))
    with pytest.raises(EstimatorFailure) as e:
        estimate_four_way_ratio(df, treatment="a", outcome="y",
                                mediator="mcont", ci_bootstrap=0)
    assert e.value.failure_type == "mediator_not_binary"


# ---------------------------------------------------------------------------
# Cluster (pairs) bootstrap — parity
# ---------------------------------------------------------------------------


def test_cluster_none_byte_identical_to_default():
    df = _sim(5, n=4000, with_cluster=True)
    kw = dict(treatment="a", outcome="y", mediator="m", adjustment=("z",),
              ci_bootstrap=150, random_state=7)
    base = estimate_four_way_ratio(df, **kw)
    same = estimate_four_way_ratio(df, cluster=None, **kw)
    assert base.total_rr_point == same.total_rr_point
    assert base.err_pie_ci_lower == same.err_pie_ci_lower
    assert base.data_hash == same.data_hash
    assert base.cluster is None


def test_cluster_column_excluded_from_hash():
    df = _sim(6, n=4000, with_cluster=True)
    with_col = estimate_four_way_ratio(
        df, treatment="a", outcome="y", mediator="m", adjustment=("z",),
        ci_bootstrap=50, random_state=1, cluster="fam")
    without = estimate_four_way_ratio(
        df[["a", "m", "y", "z"]], treatment="a", outcome="y", mediator="m",
        adjustment=("z",), ci_bootstrap=50, random_state=1)
    assert with_col.data_hash == without.data_hash
    assert with_col.cluster == "fam"
    assert any("cluster_bootstrap" in a for a in with_col.assumptions)


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_re_exported_from_themis_estimation():
    import themis.estimation as e
    assert "estimate_four_way_ratio" in e.__all__
    assert "FourWayRatioEstimate" in e.__all__
    assert "four_way_ratio_decomposition" in e.__all__
    assert e.estimate_four_way_ratio is estimate_four_way_ratio
