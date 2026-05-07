"""Phase 9 §T9.2 (iter 128) — transport-numeric ATE estimator tests.

Cole & Stuart 2010 §3 post-stratification:
  ATE_target = Σ_z P(z|target) · ATE_source(z)

Closes the documented gap on COVERAGE_MAP board 9 (transport):
identification (§T9.1) was structural-only; this iter adds the
numeric path.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.transport import (
    TransportEstimate,
    estimate_transport,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _balanced_source(n: int = 1000, seed: int = 0,
                      ate_when_z_true: float = 0.5,
                      ate_when_z_false: float = 0.2) -> pd.DataFrame:
    """Source with two strata (z=True, z=False), each with both X arms.
    Outcome Y has stratum-specific treatment effect."""
    rng = np.random.default_rng(seed)
    z = (rng.random(n) < 0.5)
    x = (rng.random(n) < 0.5)
    # Y depends on (X, Z) with stratum-specific effect.
    base = 0.3 + 0.0 * z.astype(float)
    treat_eff = np.where(z, ate_when_z_true, ate_when_z_false)
    y_continuous = base + x.astype(float) * treat_eff + rng.normal(scale=0.1, size=n)
    return pd.DataFrame({"x": x, "z": z, "y": y_continuous})


# ---------------------------------------------------------------------------
# Hand-checked math
# ---------------------------------------------------------------------------


def test_transport_recovers_weighted_average_when_target_50_50():
    """Source has ATE(z=T)=0.5, ATE(z=F)=0.2. Target marginal 50-50
    → transport ATE ≈ 0.35. Loose tolerance for finite-sample noise."""
    df = _balanced_source(n=4000, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 0.5, False: 0.5},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(0.35, abs=0.05)


def test_transport_recovers_treated_stratum_when_target_all_z_true():
    """Target marginal P(z=T)=1.0 → transport ATE ≈ source ATE in
    z=True stratum = 0.5."""
    df = _balanced_source(n=4000, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 1.0, False: 0.0},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(0.5, abs=0.05)


def test_transport_recovers_untreated_stratum_when_target_all_z_false():
    df = _balanced_source(n=4000, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 0.0, False: 1.0},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(0.2, abs=0.05)


def test_transport_with_skewed_target_70_30():
    """Target P(z=T)=0.7, P(z=F)=0.3 → 0.7*0.5 + 0.3*0.2 = 0.41."""
    df = _balanced_source(n=4000, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 0.7, False: 0.3},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.point == pytest.approx(0.41, abs=0.05)


# ---------------------------------------------------------------------------
# Bootstrap CI
# ---------------------------------------------------------------------------


def test_bootstrap_ci_brackets_point():
    df = _balanced_source(n=2000, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 0.5, False: 0.5},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=200,
    )
    assert est.ci_lower is not None and est.ci_upper is not None
    assert est.ci_lower < est.point < est.ci_upper


def test_zero_bootstrap_skips_ci():
    df = _balanced_source(n=300, seed=0)
    target_marginal = {
        "predicate": "z",
        "marginal": {True: 0.5, False: 0.5},
    }
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.ci_lower is None and est.ci_upper is None


# ---------------------------------------------------------------------------
# Estimate audit fields
# ---------------------------------------------------------------------------


def test_estimate_carries_audit_fields():
    df = _balanced_source(n=300, seed=0)
    target_marginal = {"predicate": "z", "marginal": {True: 0.5, False: 0.5}}
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assert est.method == "transport_post_stratification"
    assert est.treatment == "x"
    assert est.outcome == "y"
    assert est.adjustment == ("z",)
    assert est.target_marginal == target_marginal
    assert isinstance(est.data_hash, str) and len(est.data_hash) == 64
    assert isinstance(est, TransportEstimate)


def test_estimate_assumptions_name_s_admissibility():
    df = _balanced_source(n=300, seed=0)
    target_marginal = {"predicate": "z", "marginal": {True: 0.5, False: 0.5}}
    est = estimate_transport(
        df, treatment="x", outcome="y", adjustment=("z",),
        target_marginal=target_marginal, ci_bootstrap=0,
    )
    assumptions_str = " ".join(est.assumptions)
    assert "s_admissibility" in assumptions_str
    assert "consistency" in assumptions_str


# ---------------------------------------------------------------------------
# Validation / error paths
# ---------------------------------------------------------------------------


def test_rejects_marginal_not_summing_to_one():
    df = _balanced_source(n=300, seed=0)
    bad = {"predicate": "z", "marginal": {True: 0.3, False: 0.3}}  # 0.6 ≠ 1
    with pytest.raises(ValueError, match="must sum to 1"):
        estimate_transport(
            df, treatment="x", outcome="y", adjustment=("z",),
            target_marginal=bad, ci_bootstrap=0,
        )


def test_rejects_predicate_mismatch_with_adjustment():
    df = _balanced_source(n=300, seed=0)
    bad = {"predicate": "wrong_z", "marginal": {True: 0.5, False: 0.5}}
    with pytest.raises(ValueError, match="doesn't match the adjustment"):
        estimate_transport(
            df, treatment="x", outcome="y", adjustment=("z",),
            target_marginal=bad, ci_bootstrap=0,
        )


def test_rejects_multi_variable_adjustment_for_now():
    df = _balanced_source(n=300, seed=0)
    target_marginal = {"predicate": "z", "marginal": {True: 0.5, False: 0.5}}
    with pytest.raises(NotImplementedError, match="single-variable"):
        estimate_transport(
            df, treatment="x", outcome="y", adjustment=("z", "z2"),
            target_marginal=target_marginal, ci_bootstrap=0,
        )


def test_rejects_empty_stratum():
    """If z=True stratum is missing entirely from source, the estimator
    refuses (positivity violation in source)."""
    rng = np.random.default_rng(0)
    n = 200
    df = pd.DataFrame({
        "x": (rng.random(n) < 0.5),
        "y": rng.normal(size=n),
        "z": [False] * n,  # z=True absent from source
    })
    target_marginal = {"predicate": "z", "marginal": {True: 0.5, False: 0.5}}
    with pytest.raises(ValueError, match="no observations"):
        estimate_transport(
            df, treatment="x", outcome="y", adjustment=("z",),
            target_marginal=target_marginal, ci_bootstrap=0,
        )


def test_rejects_malformed_target_marginal():
    df = _balanced_source(n=200, seed=0)
    with pytest.raises(ValueError, match="must be"):
        estimate_transport(
            df, treatment="x", outcome="y", adjustment=("z",),
            target_marginal={"wrong": "shape"}, ci_bootstrap=0,
        )


# ---------------------------------------------------------------------------
# Public re-export
# ---------------------------------------------------------------------------


def test_re_exported_from_themis_estimation():
    import themis.estimation as e
    assert "estimate_transport" in e.__all__
    assert "TransportEstimate" in e.__all__
    assert e.estimate_transport is estimate_transport
    assert e.TransportEstimate is TransportEstimate


# ---------------------------------------------------------------------------
# Dispatch end-to-end through themis.estimate
# ---------------------------------------------------------------------------


def _transport_program(target_marginal_value=True):
    """Minimal Phase 9 §T9.1 + §T9.2 program with selection node and
    target_marginal extension."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "target_marginal": {
                "predicate": "z",
                "marginal": {True: 0.7, False: 0.3},
            },
        },
        "statements": [
            {"kind": "variable", "predicate": "z"},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y"},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "x",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "z",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            {"kind": "cause", "forall": ["I"],
             "from": {"predicate": "x",
                      "args": [{"type": "var", "name": "I"}]},
             "to": {"predicate": "y",
                    "args": [{"type": "var", "name": "I"}]}},
            # Selection node — S → Z (shifted-covariate transport
            # pattern, Bareinboim 2014 Theorem 1 case where Z's
            # distribution differs across populations and Z is a
            # backdoor adjustment for X→Y).
            {"kind": "selection_node", "id": "s_z",
             "source_population": "trial",
             "target_population": "real_world",
             "affects": {"predicate": "z",
                         "args": [{"type": "const", "name": "me"}]}},
            {"kind": "query", "id": "transport_e2e",
             "query": {"kind": "effect",
                       "target_population": "real_world",
                       "target": {"atom": {"predicate": "y",
                                           "args": [{"type": "const",
                                                     "name": "me"}]},
                                  "value": True},
                       "intervention": {"atom": {"predicate": "x",
                                                 "args": [{"type": "const",
                                                           "name": "me"}]},
                                        "value": True},
                       "given": []}},
        ],
    }


def test_dispatch_attaches_transport_numeric_e2e():
    """themis.estimate on a transport program populates
    numeric_estimate.method = transport_post_stratification."""
    import themis

    program = _transport_program()
    df = _balanced_source(n=2000, seed=0)
    out = themis.estimate(program, df)
    result = out["results"][0]
    estimate = result.get("numeric_estimate")
    assert estimate is not None, (
        f"transport numeric should attach; result keys: "
        f"{list(result.keys())}"
    )
    assert estimate.get("method") == "transport_post_stratification"
    # 0.7*0.5 + 0.3*0.2 = 0.41
    assert estimate.get("point") == pytest.approx(0.41, abs=0.05)


def test_dispatch_skips_transport_numeric_when_no_target_marginal():
    """If program.extensions.target_marginal is absent, the numeric
    layer doesn't attach. Structural transport result is still valid."""
    import themis

    program = _transport_program()
    program["extensions"] = {}  # no target marginal
    df = _balanced_source(n=500, seed=0)
    out = themis.estimate(program, df)
    result = out["results"][0]
    # Structurally identifiable still — numeric just absent.
    assert result.get("numeric_estimate") is None
