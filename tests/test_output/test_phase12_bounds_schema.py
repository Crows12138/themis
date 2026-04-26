"""Phase 12 §S.12.1 — schema + types layer for BoundsResult."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from themis.output.result_orchestrator import to_dict
from themis.types import (
    BoundsMethod,
    BoundsResult,
    QueryKind,
    QueryResult,
    ResultStatus,
)

REPO = Path(__file__).resolve().parents[2]
QR_SCHEMA = json.loads((REPO / "query_result.schema.json").read_text("utf-8"))


def _validator():
    resolver = jsonschema.RefResolver.from_schema(QR_SCHEMA)
    return jsonschema.Draft202012Validator(QR_SCHEMA, resolver=resolver)


# -------------------------------------------------------- types layer

def test_bounds_result_minimal():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="max(0, P(Y=1|X=1) - P(X=0))",
        upper_expression="min(1, P(Y=1|X=1)·P(X=1) + P(X=0))",
    )
    assert b.method == BoundsMethod.MANSKI_NATURAL
    assert b.assumptions == ()
    assert b.data_required == ()
    assert b.width_when_uninformative is False


def test_bounds_result_full():
    b = BoundsResult(
        method=BoundsMethod.BALKE_PEARL_IV,
        lower_expression="...lower formula...",
        upper_expression="...upper formula...",
        assumptions=("iv1_relevance", "iv2_exclusion", "iv3_independence"),
        data_required=("P(Y, X | Z)",),
        notes="Pearl 1995 §3",
    )
    assert "iv1_relevance" in b.assumptions
    assert b.data_required == ("P(Y, X | Z)",)


def test_bounds_result_immutable():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="0",
        upper_expression="1",
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        b.method = BoundsMethod.BALKE_PEARL_IV  # type: ignore


def test_bounds_method_all_values():
    """All 4 enum values from charter §3 are present."""
    expected = {
        "manski_natural",
        "balke_pearl_iv",
        "frontdoor_partial",
        "manski_tamer_monotonicity",
    }
    assert {m.value for m in BoundsMethod} == expected


# --------------------------------------------------- QueryResult wiring

def test_query_result_default_no_bounds():
    """bounds_result defaults to None — backward compatible."""
    qr = QueryResult(status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT)
    assert qr.bounds_result is None


def test_query_result_carries_bounds():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="0",
        upper_expression="1",
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_result=b,
    )
    assert qr.bounds_result is b


def test_serialization_omits_when_none():
    qr = QueryResult(status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT)
    d = to_dict(qr)
    assert "bounds_result" not in d


def test_serialization_includes_when_present():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="max(0, p1-p0)",
        upper_expression="min(1, p1+p0)",
        assumptions=(),
        data_required=("P(Y|X)", "P(X)"),
        width_when_uninformative=False,
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_result=b,
    )
    d = to_dict(qr)
    assert d["bounds_result"]["method"] == "manski_natural"
    assert d["bounds_result"]["lower_expression"] == "max(0, p1-p0)"
    assert d["bounds_result"]["upper_expression"] == "min(1, p1+p0)"
    assert d["bounds_result"]["data_required"] == ["P(Y|X)", "P(X)"]
    # Empty assumptions tuple → omitted
    assert "assumptions" not in d["bounds_result"]
    # Default width_when_uninformative=False → omitted
    assert "width_when_uninformative" not in d["bounds_result"]


def test_serialization_uninformative_flag_surfaces():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="-1",
        upper_expression="1",
        width_when_uninformative=True,
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_result=b,
    )
    d = to_dict(qr)
    assert d["bounds_result"]["width_when_uninformative"] is True


# ------------------------------------------------------------- JSON schema

def _qr_dict(bounds: dict | None = None) -> dict:
    return {
        "status": "needs_investigation",
        "query_kind": "effect",
        "bounds_result": bounds,
    }


def test_schema_accepts_minimal_bounds():
    bounds = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
    }
    _validator().validate(_qr_dict(bounds))


def test_schema_accepts_full_bounds():
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "...",
        "upper_expression": "...",
        "assumptions": ["iv1_relevance", "iv2_exclusion"],
        "data_required": ["P(Y, X | Z)"],
        "width_when_uninformative": False,
        "notes": "Pearl 1995",
    }
    _validator().validate(_qr_dict(bounds))


def test_schema_accepts_null_bounds():
    """When point is identifiable, bounds_result is null."""
    _validator().validate(_qr_dict(None))


def test_schema_rejects_missing_required():
    bounds = {"method": "manski_natural"}  # no lower / upper
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_unknown_method():
    bounds = {
        "method": "fabricated_method",
        "lower_expression": "0",
        "upper_expression": "1",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_extra_field():
    bounds = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
        "unauthorized_field": "x",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_old_results_without_bounds_field_still_valid():
    """Backward compat — results predating Phase 12 omit bounds_result entirely."""
    qr = {
        "status": "numerically_solved",
        "query_kind": "effect",
    }
    _validator().validate(qr)
