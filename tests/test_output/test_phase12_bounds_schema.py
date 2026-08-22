"""Phase 12 §S.12.1 — schema + types layer for BoundsResult."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

from themis.output.result_orchestrator import to_dict
from themis.types import (
    BoundsMethod,
    BoundsResult,
    QueryKind,
    QueryResult,
    ResultStatus,
)

REPO = Path(__file__).resolve().parents[2]
QR_SCHEMA = json.loads((REPO / "themis" / "schemas" / "query_result.schema.json").read_text("utf-8"))
DV_SCHEMA = json.loads((REPO / "themis" / "schemas" / "derivation.schema.json").read_text("utf-8"))
ATOM_SCHEMA = json.loads((REPO / "themis" / "schemas" / "atom.schema.json").read_text("utf-8"))


def _validator():
    registry = Registry().with_resources([
        (
            QR_SCHEMA["$id"],
            Resource.from_contents(
                QR_SCHEMA,
                default_specification=DRAFT202012,
            ),
        ),
        (
            DV_SCHEMA["$id"],
            Resource.from_contents(
                DV_SCHEMA,
                default_specification=DRAFT202012,
            ),
        ),
        (
            ATOM_SCHEMA["$id"],
            Resource.from_contents(
                ATOM_SCHEMA,
                default_specification=DRAFT202012,
            ),
        ),
    ])
    return jsonschema.Draft202012Validator(QR_SCHEMA, registry=registry)


# -------------------------------------------------------- types layer

def test_bounds_result_minimal():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="max(0, P(Y=1|X=1) - P(X=0))",
        upper_expression="min(1, P(Y=1|X=1)·P(X=1) + P(X=0))",
        estimand="arm_probability",
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
        estimand="arm_probability",
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
        estimand="arm_probability",
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
    """bounds_results defaults to empty — backward compatible."""
    qr = QueryResult(status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT)
    assert qr.bounds_results == ()


def test_query_result_carries_bounds():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="0",
        upper_expression="1",
        estimand="arm_probability",
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_results=(b,),
    )
    assert qr.bounds_results == (b,)


def test_serialization_omits_when_none():
    qr = QueryResult(status=ResultStatus.NUMERICALLY_SOLVED, query_kind=QueryKind.EFFECT)
    d = to_dict(qr)
    assert "bounds_results" not in d


def test_serialization_includes_when_present():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="max(0, p1-p0)",
        upper_expression="min(1, p1+p0)",
        estimand="arm_probability",
        assumptions=(),
        data_required=("P(Y|X)", "P(X)"),
        width_when_uninformative=False,
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_results=(b,),
    )
    d = to_dict(qr)
    assert d["bounds_results"][0]["method"] == "manski_natural"
    assert d["bounds_results"][0]["lower_expression"] == "max(0, p1-p0)"
    assert d["bounds_results"][0]["upper_expression"] == "min(1, p1+p0)"
    assert d["bounds_results"][0]["data_required"] == ["P(Y|X)", "P(X)"]
    # Empty assumptions tuple → omitted
    assert "assumptions" not in d["bounds_results"][0]
    # Default width_when_uninformative=False → omitted
    assert "width_when_uninformative" not in d["bounds_results"][0]


def test_serialization_uninformative_flag_surfaces():
    b = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="-1",
        upper_expression="1",
        estimand="arm_probability",
        width_when_uninformative=True,
    )
    qr = QueryResult(
        status=ResultStatus.NEEDS_INVESTIGATION,
        query_kind=QueryKind.EFFECT,
        bounds_results=(b,),
    )
    d = to_dict(qr)
    assert d["bounds_results"][0]["width_when_uninformative"] is True


# ------------------------------------------------------------- JSON schema

def _qr_dict(*bounds: dict) -> dict:
    return {
        "status": "needs_investigation",
        "query_kind": "effect",
        "bounds_results": list(bounds),
    }


def test_schema_accepts_minimal_bounds():
    bounds = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
        "estimand": "arm_probability",
        "tightness": "sharp",
    }
    _validator().validate(_qr_dict(bounds))


def test_schema_accepts_full_bounds():
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "...",
        "upper_expression": "...",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "assumptions": ["iv1_relevance", "iv2_exclusion"],
        "data_required": ["P(Y, X | Z)"],
        "width_when_uninformative": False,
        "notes": "Pearl 1995",
    }
    _validator().validate(_qr_dict(bounds))


def test_schema_accepts_no_bounds():
    """When point is identifiable, the set is empty."""
    _validator().validate(_qr_dict())


def test_schema_accepts_several_rows():
    """The shape the block exists for: one estimand, several methods, each
    carrying the assumptions that produced its interval."""
    _validator().validate(_qr_dict(
        {
            "method": "manski_natural",
            "lower_expression": "0", "upper_expression": "1",
            "estimand": "arm_probability",
            "tightness": "sharp",
        },
        {
            "method": "balke_pearl_iv",
            "lower_expression": "...", "upper_expression": "...",
            "estimand": "arm_probability",
            "tightness": "sharp",
            "assumptions": ["iv1_relevance"],
        },
    ))


def test_schema_rejects_missing_required():
    bounds = {"method": "manski_natural"}  # no lower / upper
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_bounds_that_do_not_say_what_they_bracket():
    """The gate this required-field is for.

    Two endpoints and a method name are what this block shipped for the
    whole of Phase 12, and for the Balke-Pearl branch they bracketed the
    difference between two arms under a question that asked for one.
    """
    bounds = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_accepts_a_named_second_quantity():
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "min of P(y=true | do(x=true)) ...",
        "upper_expression": "max of P(y=true | do(x=true)) ...",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "lower_value": 0.2,
        "upper_value": 0.6,
        # A row that was evaluated answers the interval question too, with
        # null when no band was computed. Absence is reserved for the row
        # that was never evaluated at all, and the schema ties the three
        # together so the two cannot be confused.
        "ci_lower": None,
        "ci_upper": None,
        "contrast": {
            "kind": "ace",
            "reference_value": False,
            "lower_value": -0.1,
            "upper_value": 0.4,
            "tightness": "sharp",
        },
    }
    _validator().validate(_qr_dict(bounds))


def test_schema_rejects_a_contrast_that_does_not_name_its_baseline():
    """A difference is against something. Without the reference level the
    two numbers are a difference from an unstated arm, which is the same
    defect as an interval with no estimand one field down."""
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "min of P(...)",
        "upper_expression": "max of P(...)",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "contrast": {"kind": "ace", "lower_value": -0.1, "upper_value": 0.4},
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_an_unknown_contrast_kind():
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "min of P(...)",
        "upper_expression": "max of P(...)",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "contrast": {
            "kind": "risk_ratio", "reference_value": False,
            "lower_value": 0.5, "upper_value": 2.0,
        },
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_the_estimand_this_block_used_to_carry():
    """`ace` was a member of this enum, and it was Balke-Pearl's value for
    it. It is gone from here on purpose — the ACE has its own field, with
    its own baseline — so a producer that goes back to putting a difference
    in lower_value/upper_value fails at the exit rather than at a reader."""
    bounds = {
        "method": "balke_pearl_iv",
        "lower_expression": "min of P(...)",
        "upper_expression": "max of P(...)",
        "estimand": "ace",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_unknown_method():
    bounds = {
        "method": "fabricated_method",
        "lower_expression": "0",
        "upper_expression": "1",
        "estimand": "arm_probability",
        "tightness": "sharp",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_rejects_extra_field():
    bounds = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "unauthorized_field": "x",
    }
    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(_qr_dict(bounds))


def test_schema_old_results_without_bounds_field_still_valid():
    """Backward compat — results predating Phase 12 omit bounds_results entirely."""
    qr = {
        "status": "numerically_solved",
        "query_kind": "effect",
    }
    _validator().validate(qr)
