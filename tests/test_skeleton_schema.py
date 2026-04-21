"""Pin that ``investigationItem.skeleton`` now accepts exactly two
shapes — parameterSkeleton (``kind: probability``) and variablePatch
(``kind: variable_patch``) — and rejects any third shape.

This is the last schema tightening of the "contract lock-down" round.
The boundary is explicit: future skeleton kinds land here as new
$defs plus a new branch in the ``oneOf``, never as a loose
fallthrough.
"""
from __future__ import annotations

import copy

import pytest

import themis
from themis.input.syntactic_validator import SyntacticError, validate_result


def _atom(p: str) -> dict:
    return {"predicate": p, "args": [{"type": "const", "name": "me"}]}


def _program_with_both_skeleton_kinds() -> dict:
    """Underframed variables + missing Theta entry → result carries
    both a parameterSkeleton (from missing CPT) and variablePatch
    skeletons (from framing gaps)."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom("x"), "to": _atom("y")},
            {"kind": "query", "id": "q",
             "query": {"kind": "effect",
                       "target": {"atom": _atom("y"), "value": True},
                       "intervention": {"atom": _atom("x"), "value": True},
                       "given": []}},
        ],
    }


def _get_skeletons(result: dict) -> list[dict]:
    out = []
    for req in result.get("investigation_requests", []):
        for item in req.get("items", []):
            if "skeleton" in item:
                out.append(item["skeleton"])
    return out


# =========================================== accept both canonical shapes

def test_real_run_produces_two_canonical_skeleton_kinds():
    """The live runtime emits both shapes on a single underframed
    effect program; the outer validator must pass every one."""
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    skeletons = _get_skeletons(r)
    kinds = {s["kind"] for s in skeletons}
    assert kinds == {"probability", "variable_patch"}
    # And the whole envelope passes validate_result, which now
    # enforces the oneOf on every skeleton.
    validate_result(r)


def test_schema_accepts_parameter_skeleton_with_null_value():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    parameter = next(s for s in _get_skeletons(r) if s["kind"] == "probability")
    assert parameter["value"] is None
    validate_result(r)  # already accepted above, explicit here


def test_schema_accepts_parameter_skeleton_after_user_fills_value():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    r2 = copy.deepcopy(r)
    for req in r2["investigation_requests"]:
        for item in req["items"]:
            s = item.get("skeleton")
            if s and s["kind"] == "probability":
                s["value"] = 0.42
    validate_result(r2)


def test_schema_accepts_variable_patch_with_filled_fields():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    r2 = copy.deepcopy(r)
    for req in r2["investigation_requests"]:
        for item in req["items"]:
            s = item.get("skeleton")
            if s and s["kind"] == "variable_patch":
                s["fields"] = {
                    "time_window": "12w",
                    "measurement": "cm",
                    "threshold": ">=3",
                    "observability": "self-report",
                }
    validate_result(r2)


# =========================================== reject non-canonical shapes

def _replace_skeleton_on_first_item(result: dict, new_skeleton: dict) -> dict:
    r = copy.deepcopy(result)
    # Find the first request with items and replace its first skeleton.
    for req in r["investigation_requests"]:
        for item in req.get("items", []):
            if "skeleton" in item:
                item["skeleton"] = new_skeleton
                return r
    raise AssertionError("test setup: no item with skeleton found")


def test_schema_rejects_skeleton_with_unknown_kind():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "future_skeleton_kind",
        "payload": {"anything": 1},
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_parameter_skeleton_missing_required_field():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "probability",
        # 'target' missing
        "given": [],
        "value": None,
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_parameter_skeleton_with_out_of_range_value():
    """value type is number-or-null; once filled, the number still has
    to be a JSON number. A clearly non-numeric value (string) must be
    rejected at the schema layer."""
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "probability",
        "target": {"atom": _atom("y"), "value": True},
        "given": [{"atom": _atom("x"), "value": True}],
        "value": "half",  # not a number or null
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_variable_patch_missing_predicate():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "variable_patch",
        # 'predicate' missing
        "existing": {},
        "fields": {"time_window": None},
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_variable_patch_with_empty_predicate():
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "variable_patch",
        "predicate": "",
        "existing": {},
        "fields": {"time_window": None},
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_variable_patch_with_boolean_field_value():
    """fields values must be string / array / null — a bool must be
    rejected so malformed user input doesn't leak into a merge."""
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "variable_patch",
        "predicate": "x",
        "existing": {},
        "fields": {"time_window": True},
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)


def test_schema_rejects_skeleton_with_additional_top_level_property():
    """Both canonical shapes forbid additionalProperties. A stray
    top-level field must trip the validator."""
    r = themis.run(_program_with_both_skeleton_kinds())["results"][0]
    tampered = _replace_skeleton_on_first_item(r, {
        "kind": "variable_patch",
        "predicate": "x",
        "existing": {},
        "fields": {"time_window": None},
        "unexpected_extra": "nope",
    })
    with pytest.raises(SyntacticError):
        validate_result(tampered)
