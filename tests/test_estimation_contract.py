"""Phase 7.1 S.N.1 — unit tests for the estimation data contract."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from themis.estimation.contract import (
    DataContract,
    DataContractError,
    validate_data,
)


def _clean_frame(n=50, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "x": rng.integers(0, 2, n).astype(bool),
        "y": rng.integers(0, 2, n).astype(bool),
        "z": rng.standard_normal(n),
    })


# ========================================= happy path


def test_clean_bool_and_continuous_validates():
    df = _clean_frame()
    contract = validate_data(
        df,
        required_columns=["x", "y", "z"],
        bool_columns=["x", "y"],
        continuous_columns=["z"],
    )
    assert isinstance(contract, DataContract)
    assert contract.sample_size == 50
    assert contract.columns == ("x", "y", "z")
    # bool columns stay bool, continuous columns become float64
    assert contract.data["x"].dtype == bool
    assert contract.data["y"].dtype == bool
    assert contract.data["z"].dtype == np.float64
    # no warnings for 50 rows
    assert contract.warnings == ()


def test_data_hash_is_deterministic():
    df = _clean_frame(seed=0)
    c1 = validate_data(
        df, required_columns=["x", "y"],
        bool_columns=["x", "y"],
    )
    c2 = validate_data(
        df, required_columns=["x", "y"],
        bool_columns=["x", "y"],
    )
    assert c1.data_hash == c2.data_hash
    # Hash is 64 hex chars (SHA-256)
    assert len(c1.data_hash) == 64
    assert all(c in "0123456789abcdef" for c in c1.data_hash)


def test_data_hash_changes_with_values():
    df1 = _clean_frame(seed=0)
    df2 = _clean_frame(seed=1)
    c1 = validate_data(df1, required_columns=["x", "y"], bool_columns=["x", "y"])
    c2 = validate_data(df2, required_columns=["x", "y"], bool_columns=["x", "y"])
    assert c1.data_hash != c2.data_hash


# ========================================= auto type detection


def test_auto_detects_bool_like_numeric():
    """0/1 int columns should be coerced to bool without explicit hint."""
    df = pd.DataFrame({
        "x": [0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0],
        "y": [1, 0, 1, 0, 0, 1, 0, 1, 0, 1, 0, 1],
    })
    contract = validate_data(df, required_columns=["x", "y"])
    assert contract.data["x"].dtype == bool
    assert contract.data["y"].dtype == bool


def test_auto_coerces_numeric_to_float():
    df = pd.DataFrame({
        "z": list(range(10, 25)),  # int, not bool-like
        "w": [1.5] * 15,
    })
    contract = validate_data(df, required_columns=["z", "w"])
    assert contract.data["z"].dtype == np.float64
    assert contract.data["w"].dtype == np.float64


# ========================================= error paths


def test_rejects_non_dataframe():
    with pytest.raises(DataContractError, match="DataFrame"):
        validate_data([[1, 2, 3]], required_columns=["x"])


def test_rejects_missing_column():
    df = _clean_frame()
    with pytest.raises(DataContractError, match="missing required columns"):
        validate_data(df, required_columns=["x", "y", "missing_col"])


def test_rejects_nan_values():
    df = _clean_frame().astype(object)
    df.loc[0, "z"] = np.nan
    with pytest.raises(DataContractError, match="NaN"):
        validate_data(
            df, required_columns=["z"], continuous_columns=["z"],
        )


def test_rejects_too_few_samples():
    df = pd.DataFrame({"x": [True, False]})
    with pytest.raises(DataContractError, match="sample size"):
        validate_data(df, required_columns=["x"], bool_columns=["x"])


def test_warns_below_recommended_sample_size():
    df = pd.DataFrame({"x": [True, False] * 10})  # 20 rows
    contract = validate_data(
        df, required_columns=["x"], bool_columns=["x"],
    )
    assert contract.sample_size == 20
    assert any("建议阈值" in w for w in contract.warnings)


def test_rejects_non_boollike_values_in_bool_column():
    df = pd.DataFrame({"x": [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]})
    with pytest.raises(DataContractError, match="outside"):
        validate_data(df, required_columns=["x"], bool_columns=["x"])


def test_rejects_non_numeric_continuous_column():
    df = pd.DataFrame({
        "z": ["small", "big"] * 10,
        "x": [True, False] * 10,
    })
    with pytest.raises(DataContractError, match="expected numeric"):
        validate_data(
            df, required_columns=["z", "x"],
            continuous_columns=["z"], bool_columns=["x"],
        )


# ========================================= themis.estimate skeleton


def test_themis_estimate_round_trips_identification():
    """themis.estimate with a mediator effect query attaches
    estimation_context to each result and does not regress the
    identification output."""
    import themis

    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("m")},
            {"kind": "cause", "from": atom("m"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": [],
                "mediator": atom("m"),
            }},
        ],
    }
    df = pd.DataFrame({
        "x": [True, False] * 15,
        "m": [True, False, True] * 10,
        "y": [False, True] * 15,
    })
    out = themis.estimate(ast, df)

    # Identification output preserved
    result = out["results"][0]
    assert result["status"] == "structurally_solved"
    assert "mediation_decomposition" in result["extensions"]

    # Estimation context populated
    ctx = result["estimation_context"]
    assert len(ctx["data_hash"]) == 64
    assert ctx["sample_size"] == 30
    assert ctx["random_state"] == 42
    assert ctx["ci_bootstrap"] == 500
    assert ctx["model_preference"] == "auto"


def test_themis_estimate_rejects_bad_data_early():
    import themis

    def atom(p):
        return {"predicate": p, "args": [{"type": "const", "name": "me"}]}

    ast = {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": atom("x"), "to": atom("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": atom("x"), "value": True},
                "target": {"atom": atom("y"), "value": True},
                "given": [],
            }},
        ],
    }
    # DataFrame missing 'x' column
    bad_df = pd.DataFrame({"y": [True, False] * 10})
    with pytest.raises(DataContractError):
        themis.estimate(ast, bad_df)
