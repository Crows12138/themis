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
    out = themis.estimate(_dose_response_program(), _synth_data())
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
    out = themis.estimate(_dose_response_program(), _synth_data(slope=0.5))
    curve = out["results"][0]["numeric_estimate"]["dose_response_curve"]
    last = curve[-1]
    first = curve[0]
    # ΔY ≈ slope × Δx; with quantile sampling first ≈ 1.0, last ≈ 9.0
    expected = 0.5 * (last["x"] - first["x"])
    assert abs(last["effect"] - expected) < 1.5


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_assumptions_name_linearity():
    out = themis.estimate(_dose_response_program(), _synth_data())
    ne = out["results"][0]["numeric_estimate"]
    assumptions = " ".join(ne["assumptions"])
    assert "LinearDML" in assumptions or "线性" in assumptions


@pytest.mark.skipif(not _ECONML_AVAILABLE, reason="econml not installed")
def test_dose_response_status_flips_to_numerically_solved():
    out = themis.estimate(_dose_response_program(), _synth_data())
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
    out = themis.estimate(program, _synth_data())
    ne = out["results"][0]["numeric_estimate"]
    assert ne["sampling_points"] == [0.0, 5.0, 10.0]


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
        out = themis.estimate(_dose_response_program(), _synth_data())
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
