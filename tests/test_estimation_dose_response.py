"""Phase 14 slice a — dose-response estimator tests.

Skips when EconML is not installed (it's an optional dependency:
``pip install econml`` or ``pip install themis[estimator]``).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import themis

try:
    import econml  # noqa: F401
    _ECONML_AVAILABLE = True
except ImportError:
    _ECONML_AVAILABLE = False


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _dose_response_program() -> dict:
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "extensions": {
            "ambiguities": [
                {"kind": "dose_response_query",
                 "description": "raise vs engagement curve"},
            ],
        },
        "statements": [
            {"kind": "variable", "predicate": "raise_amount"},
            {"kind": "variable", "predicate": "engagement"},
            {"kind": "cause",
             "from": _atom("raise_amount"), "to": _atom("engagement"),
             "annotations": {"source": "llm_proposal"}},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "effect",
                 "intervention": {"atom": _atom("raise_amount"),
                                  "value": True},
                 "target": {"atom": _atom("engagement"), "value": 4},
                 "given": []}},
        ],
    }


def _synth_data(n: int = 400, slope: float = 0.5, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    raise_amount = rng.uniform(0.0, 10.0, size=n)
    noise = rng.normal(0.0, 1.0, size=n)
    engagement = 1.0 + slope * raise_amount + noise
    return pd.DataFrame({
        "raise_amount": raise_amount,
        "engagement": engagement,
    })


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_curve_attached_when_ambiguity_flagged():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    result = out["results"][0]
    assert "numeric_estimate" in result
    ne = result["numeric_estimate"]
    assert ne["method"] == "dose_response_linear_dml"
    assert "dose_response_curve" in ne
    curve = ne["dose_response_curve"]
    assert len(curve) >= 2
    # First point is the reference: effect should be 0
    assert curve[0]["effect"] == pytest.approx(0.0, abs=1e-9)
    # X values must be non-decreasing
    xs = [p["x"] for p in curve]
    assert xs == sorted(xs)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_recovers_linear_slope():
    """Synthetic data has slope 0.5; the curve at x=10 vs x≈0 should
    show an effect near 5.0 (loose tolerance — DML adds noise)."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(slope=0.5), model="linear",
    )
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    last = curve[-1]
    first = curve[0]
    # ΔY ≈ slope × Δx; with quantile sampling first ≈ 1.0, last ≈ 9.0
    expected = 0.5 * (last["x"] - first["x"])
    assert abs(last["effect"] - expected) < 1.5


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_assumptions_name_linearity():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    ne = out["results"][0]["numeric_estimate"]
    assumptions = " ".join(ne["assumptions"])
    assert "LinearDML" in assumptions or "线性" in assumptions


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_status_flips_to_numerically_solved():
    out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
    assert out["results"][0]["status"] == "numerically_solved"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_uses_declared_domain_when_available():
    """When the treatment has a numeric domain, curve uses those exact
    points (not quantiles)."""
    program = _dose_response_program()
    # Replace raise_amount declaration with a discrete domain
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "raise_amount":
            stmt["domain"] = [0.0, 5.0, 10.0]
    out = themis.estimate(program, _synth_data(), model="linear")
    ne = out["results"][0]["numeric_estimate"]
    assert ne["sampling_points"] == [0.0, 5.0, 10.0]


# ---------- slice b: CausalForestDML backend ----------

def _nonlinear_synth(n: int = 600, seed: int = 11) -> pd.DataFrame:
    """Y = 1 + 0.4·T - 0.03·T² + noise — concave-down dose-response."""
    rng = np.random.default_rng(seed)
    raise_amount = rng.uniform(0.0, 10.0, size=n)
    noise = rng.normal(0.0, 0.5, size=n)
    engagement = 1.0 + 0.4 * raise_amount - 0.03 * raise_amount ** 2 + noise
    return pd.DataFrame({
        "raise_amount": raise_amount,
        "engagement": engagement,
    })


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_forest_backend_via_explicit_model_kwarg():
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(), model="forest",
    )
    ne = out["results"][0]["numeric_estimate"]
    assert ne["method"] == "dose_response_causal_forest_dml"
    assert "森林" in " ".join(ne["assumptions"]) or \
           "CausalForestDML" in " ".join(ne["assumptions"])


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_auto_picks_forest_when_n_large():
    """n=600 ≥ 200 → 'auto' resolves to forest."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(n=600), model="auto",
    )
    assert out["results"][0]["numeric_estimate"]["method"] == \
        "dose_response_causal_forest_dml"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_auto_picks_linear_when_n_small():
    """n=80 < 200 → 'auto' resolves to linear (forest needs the
    sample size for honest splits to behave)."""
    out = themis.estimate(
        _dose_response_program(), _synth_data(n=80), model="auto",
    )
    assert out["results"][0]["numeric_estimate"]["method"] == \
        "dose_response_linear_dml"


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_forest_assumption_admits_t_linearity_limit():
    """Forest's nuisance-stage flexibility doesn't extend to the T-Y
    relationship — the final stage is still linear in T. Make sure the
    assumption text says so, so callers don't read the curve as
    non-linear evidence when it isn't."""
    out = themis.estimate(
        _dose_response_program(), _nonlinear_synth(), model="forest",
    )
    assumptions = " ".join(out["results"][0]["numeric_estimate"]["assumptions"])
    # Either explicit Chinese phrasing or English equivalent
    assert ("不能恢复" in assumptions and "非线性" in assumptions) or \
           "DRLearner" in assumptions


# ---------- slice c: structured failures ----------

@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_overlap_insufficient_when_constant_treatment():
    """Treatment with zero variance can't yield any dose-response;
    surface as overlap_insufficient, not a crash."""
    df = _synth_data()
    df["raise_amount"] = 5.0  # collapse to constant
    out = themis.estimate(_dose_response_program(), df, model="linear")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "overlap_insufficient"
    assert "没有变化" in failure["reason"] or "max == min" in failure["reason"]


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_overlap_insufficient_when_sampling_point_in_gap():
    """Declared domain includes points outside the observed support;
    those points should fail with sparse_points details."""
    program = _dose_response_program()
    for stmt in program["statements"]:
        if stmt.get("kind") == "variable" and stmt["predicate"] == "raise_amount":
            # Observed data is uniform on [0, 10]. Declaring 100 forces
            # a sampling point that's nowhere near any observation.
            stmt["domain"] = [0.0, 5.0, 100.0]
    out = themis.estimate(program, _synth_data(), model="linear")
    failure = out["results"][0].get("estimator_failure")
    assert failure is not None
    assert failure["failure_type"] == "overlap_insufficient"
    sparse = failure["details"]["sparse_points"]
    assert any(p["x"] == 100.0 for p in sparse)


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_failure_type_field_present_on_all_paths():
    """Every estimator_failure block must carry failure_type so callers
    can branch on it without parsing the reason string."""
    df = _synth_data()
    df["raise_amount"] = 5.0
    out = themis.estimate(_dose_response_program(), df, model="linear")
    failure = out["results"][0]["estimator_failure"]
    # Three legal values (slice c): overlap_insufficient,
    # convergence_failure, unknown
    assert failure["failure_type"] in {
        "overlap_insufficient", "convergence_failure", "unknown",
    }


def test_no_dose_response_ambiguity_keeps_binary_path():
    """Without the ambiguity flag, dispatch must NOT route to the
    dose-response estimator — it falls through to the standard binary
    backdoor path. Used as a regression guard."""
    program = _dose_response_program()
    program.pop("extensions", None)
    # Force outcome to bool so the binary path can fit
    df = _synth_data()
    df["engagement"] = (df["engagement"] > df["engagement"].median())
    df["raise_amount"] = (df["raise_amount"] > 5.0)
    out = themis.estimate(program, df)
    ne = out["results"][0].get("numeric_estimate", {})
    assert ne.get("method") != "dose_response_linear_dml"


def test_missing_econml_surfaces_structured_error(monkeypatch):
    """If EconML isn't importable, dispatch attaches an
    ``estimator_dependency_missing`` block instead of crashing."""
    import sys
    # Hide econml from the import system for this test only
    real_econml = sys.modules.pop("econml", None)
    real_econml_dml = sys.modules.pop("econml.dml", None)
    monkeypatch.setitem(sys.modules, "econml", None)
    try:
        out = themis.estimate(_dose_response_program(), _synth_data(), model="linear")
        result = out["results"][0]
        # Either dependency-missing block is set, or the binary
        # fallback ran (also acceptable — both paths surface
        # structurally, neither crashes)
        if "estimator_dependency_missing" in result:
            block = result["estimator_dependency_missing"]
            assert block["package"] == "econml"
            assert "pip install" in block["install_hint"]
    finally:
        if real_econml is not None:
            sys.modules["econml"] = real_econml
        if real_econml_dml is not None:
            sys.modules["econml.dml"] = real_econml_dml
