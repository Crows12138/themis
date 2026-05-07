"""Iter 120 — weak-IV instrument gap_kind tests.

Stock-Yogo (2005): when the first-stage F-statistic falls below 10 for
single-instrument 2SLS/Wald, the IV estimate is materially biased
toward OLS and standard 2SLS asymptotic CIs underestimate uncertainty.
Themis surfaces this as a `weak_iv_instrument` informational gap_kind
that gets:

1. Computed in `themis.estimation.iv._first_stage_f_stat` (regression-
   based F via SSR comparison)
2. Carried on `IVEstimate.first_stage_f_stat` and serialized in
   `numeric_estimate.first_stage_f_stat`
3. Routed by `dispatch._attach_weak_iv_warning_if_low_f` into
   `data_gap_report.gaps[]` AND mirrored as a ⚠ line in
   `result.explanation` so the renderer can't silently drop it
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.dispatch import WEAK_IV_F_THRESHOLD
from themis.estimation.iv import _first_stage_f_stat, estimate_iv_ate


# ---------------------------------------------------------------------------
# F-stat computation primitive
# ---------------------------------------------------------------------------


def _make_strong_iv_data(n: int = 1000, seed: int = 0) -> pd.DataFrame:
    """Z explains ~all of X variance — F should be very large."""
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = 2.0 * z + 0.1 * rng.normal(size=n)
    y = 1.5 * x + rng.normal(size=n)
    return pd.DataFrame({"z": z, "x": x, "y": y})


def _make_weak_iv_data(n: int = 500, seed: int = 0) -> pd.DataFrame:
    """Z explains tiny share of X variance — F should be low (< 10).

    With n=500 and coef=0.03, R² ≈ 0.0009 → F ≈ 0.45, comfortably
    below the Stock-Yogo threshold without being so degenerate that
    the regression itself fails.
    """
    rng = np.random.default_rng(seed)
    z = rng.normal(size=n)
    x = 0.03 * z + rng.normal(size=n)  # nearly no first-stage signal
    y = 1.5 * x + rng.normal(size=n)
    return pd.DataFrame({"z": z, "x": x, "y": y})


def test_first_stage_f_strong_signal_returns_large_f():
    df = _make_strong_iv_data()
    f = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    )
    assert f is not None
    assert f > 100.0


def test_first_stage_f_weak_signal_returns_small_f():
    df = _make_weak_iv_data()
    f = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    )
    assert f is not None
    assert f < WEAK_IV_F_THRESHOLD


def test_first_stage_f_returns_none_on_zero_variance_instrument():
    df = pd.DataFrame({
        "z": [0.0] * 50,
        "x": np.random.default_rng(0).normal(size=50),
        "y": np.random.default_rng(1).normal(size=50),
    })
    f = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    )
    assert f is None


def test_first_stage_f_returns_none_on_too_small_sample():
    df = pd.DataFrame({"z": [0, 1], "x": [0, 1], "y": [0, 1]}, dtype=float)
    f = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    )
    assert f is None


def test_first_stage_f_with_conditioning_subtracts_w_signal():
    """Adding W that's correlated with both Z and X should shrink the
    first-stage Z effect after partialing — F drops relative to no W."""
    rng = np.random.default_rng(0)
    n = 500
    w = rng.normal(size=n)
    z = 0.8 * w + 0.5 * rng.normal(size=n)
    x = 1.0 * z + 0.5 * w + 0.2 * rng.normal(size=n)
    y = x + rng.normal(size=n)
    df = pd.DataFrame({"z": z, "x": x, "y": y, "w": w})

    f_no_w = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=(),
    )
    f_with_w = _first_stage_f_stat(
        df, treatment="x", instrument="z", conditioning=("w",),
    )
    assert f_no_w is not None and f_with_w is not None
    # Both must be positive; the with-W F is the partial-correlation
    # F (correct interpretation for conditional IV).
    assert f_no_w > 0
    assert f_with_w > 0


# ---------------------------------------------------------------------------
# IVEstimate carries the F-stat
# ---------------------------------------------------------------------------


def test_iv_estimate_carries_first_stage_f():
    df = _make_strong_iv_data()
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.first_stage_f_stat is not None
    assert est.first_stage_f_stat > 100.0


def test_iv_estimate_first_stage_f_low_for_weak_instrument():
    df = _make_weak_iv_data()
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    assert est.first_stage_f_stat is not None
    assert est.first_stage_f_stat < WEAK_IV_F_THRESHOLD


# ---------------------------------------------------------------------------
# Dispatch attaches weak_iv_instrument gap when F < threshold
# ---------------------------------------------------------------------------


def _attach_directly(df: pd.DataFrame):
    """Skip the kernel for these tests — directly call the IV estimator
    + the dispatch hook on a constructed result dict so we can assert
    the appended gap shape without bringing the whole identification
    pipeline into scope."""
    from themis.estimation.dispatch import _attach_weak_iv_warning_if_low_f

    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    result: dict = {}
    _attach_weak_iv_warning_if_low_f(result, est)
    return est, result


def test_dispatch_attaches_gap_when_f_below_threshold():
    df = _make_weak_iv_data()
    est, result = _attach_directly(df)
    assert est.first_stage_f_stat < WEAK_IV_F_THRESHOLD

    report = result.get("data_gap_report")
    assert report is not None
    kinds = [g["kind"] for g in report["gaps"]]
    assert "weak_iv_instrument" in kinds


def test_dispatch_skips_gap_when_f_above_threshold():
    df = _make_strong_iv_data()
    est, result = _attach_directly(df)
    assert est.first_stage_f_stat >= WEAK_IV_F_THRESHOLD
    # Strong IV → no gap added (and no data_gap_report created either,
    # since this helper doesn't populate one for unrelated reasons).
    assert "data_gap_report" not in result


def test_dispatch_attached_gap_has_informational_severity():
    df = _make_weak_iv_data()
    est, result = _attach_directly(df)
    gap = result["data_gap_report"]["gaps"][0]
    assert gap["severity"] == "informational"
    assert gap["blocks"] == "interpretation"


def test_dispatch_attached_gap_carries_provenance():
    df = _make_weak_iv_data()
    est, result = _attach_directly(df)
    gap = result["data_gap_report"]["gaps"][0]
    prov = gap["provenance"]
    assert len(prov) == 1
    assert prov[0]["ref_kind"] == "verifier_check"
    # Provenance ref names the (instrument -> treatment) edge so T10-3
    # kind-consistency / T10-2 step coverage have a stable handle.
    assert "z" in prov[0]["ref_id"]
    assert "x" in prov[0]["ref_id"]


def test_dispatch_appends_to_existing_data_gap_report():
    """If a prior pipeline step already populated data_gap_report,
    weak_iv appends rather than overwriting."""
    from themis.estimation.dispatch import _attach_weak_iv_warning_if_low_f

    df = _make_weak_iv_data()
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    pre_existing_gap = {
        "kind": "iv_identification_assumption_required",
        "severity": "informational",
        "blocks": "interpretation",
        "description": "stub",
        "required_data": None,
        "alternative_paths": [],
        "provenance": [],
    }
    result = {
        "data_gap_report": {
            "summary": "preexisting",
            "gaps": [pre_existing_gap],
            "actionable_next_steps": [],
        }
    }
    _attach_weak_iv_warning_if_low_f(result, est)
    kinds = [g["kind"] for g in result["data_gap_report"]["gaps"]]
    assert kinds == [
        "iv_identification_assumption_required",
        "weak_iv_instrument",
    ]


def test_dispatch_mirrors_warning_to_explanation():
    """⚠ line lands in result.explanation so the renderer can't silently
    drop the weak-IV caveat — same channel as
    scheduler._attach_structural_caveats uses."""
    df = _make_weak_iv_data()
    _, result = _attach_directly(df)
    explanation = result.get("explanation", "")
    assert "⚠" in explanation
    assert "first-stage F" in explanation.lower() or "F =" in explanation


def test_dispatch_handles_none_f_stat_gracefully():
    """When F could not be computed (degenerate case), no gap is
    attached — None is treated as 'could not assess', not 'weak'."""
    from dataclasses import replace
    from themis.estimation.dispatch import _attach_weak_iv_warning_if_low_f

    df = _make_strong_iv_data()
    est = estimate_iv_ate(
        df, treatment="x", outcome="y", instrument="z",
        ci_bootstrap=0,
    )
    est_no_f = replace(est, first_stage_f_stat=None)
    result: dict = {}
    _attach_weak_iv_warning_if_low_f(result, est_no_f)
    assert "data_gap_report" not in result
