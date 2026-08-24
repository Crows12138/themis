"""Phase 12 §S.12.1 — schema + types layer for BoundsResult."""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource

from themis.output.result_orchestrator import to_dict
from themis.types import (
    BoundsMethod,
    BoundsResult,
    QueryKind,
    QueryResult,
    ResultStatus,
)
from themis.input.syntactic_validator import validator_for
from themis import language
from themis.output.bounds import Note, Observable, Side


def _needed(expression):
    """One observable a client must supply, as a producer states it."""
    return language.state(Observable.A_JOINT_DISTRIBUTION,
                          expression=expression)


def _note():
    """One thing true of an interval that no other field carries."""
    return language.state(Note.ONE_SIDE_TIGHTENED, side=Side.LOWER,
                          to="P(y=true)")


def _validator():
    return validator_for("query_result.schema.json")


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
        data_required=(_needed("P(Y, X | Z)"),),
        notes=(_note(),),
    )
    assert "iv1_relevance" in b.assumptions
    assert b.data_required == (_needed("P(Y, X | Z)"),)


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
        data_required=(_needed("P(Y|X)"), _needed("P(X)")),
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
    assert d["bounds_results"][0]["data_required"] == [
        _needed("P(Y|X)"), _needed("P(X)")]
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
        "data_required": [_needed("P(Y, X | Z)")],
        "width_when_uninformative": False,
        "notes": [_note()],
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


# --- what a bound says beyond its two endpoints --------------------------
#
# The row could say WHAT the interval is and could not say what a reader
# still needs to know ABOUT it, so the two fields that hold sentences became
# where those facts went. They are statements now, which is what lets a
# check ask what a note SAYS instead of searching prose for a substring.


def test_the_envelope_refuses_a_note_written_as_text():
    """The counterexample: the shape this replaced.

    A sentence in this field is the kernel choosing a language for a reader
    it cannot see, and it has to be refused at the contract — nothing
    downstream can tell a sentence the kernel wrote from one it did not.
    A string is also not a list, which is the second half of the same
    defect: the field had a fourth author appending to it with a space.
    """
    good = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "notes": [_note()],
    }
    _validator().validate(_qr_dict(good))

    for instead in ("Manski (1990) 自然界，不加任何假设。",
                    [{"vocabulary": "bounds_note"}]):
        with pytest.raises(jsonschema.ValidationError):
            _validator().validate(_qr_dict({**good, "notes": instead}))


def test_the_envelope_refuses_an_observable_with_a_comment_glued_on():
    """The other seam: one slot holding two things.

    ``P(y, x)  # 联合观测`` is a formula and a clause about it, joined by a
    mark the producer invented for want of a second slot — so a reader that
    wants the formula has to strip the comment and a reader that wants the
    clause has to look for a ``#``.
    """
    good = {
        "method": "manski_natural",
        "lower_expression": "0",
        "upper_expression": "1",
        "estimand": "arm_probability",
        "tightness": "sharp",
        "data_required": [_needed("P(y, x)")],
    }
    _validator().validate(_qr_dict(good))

    with pytest.raises(jsonschema.ValidationError):
        _validator().validate(
            _qr_dict({**good, "data_required": ["P(y, x)  # 联合观测"]}))


def test_a_second_author_appends_rather_than_concatenating():
    """What the sequence is for.

    The scheduler reports the assumption-free floor when the sharp method is
    too big to solve, and says so. While the field was a string it had to
    know what the method had already written and what to put between the
    two — which is the reader's punctuation, decided in the kernel.
    """
    from dataclasses import replace

    method_said = BoundsResult(
        method=BoundsMethod.MANSKI_NATURAL,
        lower_expression="0", upper_expression="1",
        estimand="arm_probability",
        notes=(_note(),),
    )
    both = replace(method_said, notes=method_said.notes + (_note(),))
    assert len(both.notes) == 2
    for lang in ("zh", "en"):
        assert all(language.spoke(one, lang) for one in both.notes)
