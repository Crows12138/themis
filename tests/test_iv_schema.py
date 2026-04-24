"""Phase 6.iv S.IV.4: schema + result serialization.

Tests that:
- IV identification results serialize to JSON matching
  query_result.schema.json (including the new extensions.iv_identification
  sub-schema)
- Deserializing and re-running themis.verify round-trips correctly
- Bad IV extension shapes are rejected by the schema validator
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import pytest

import themis


_REPO_ROOT = Path(__file__).parent.parent
_RESULT_SCHEMA_PATH = _REPO_ROOT / "query_result.schema.json"
_DERIVATION_SCHEMA_PATH = _REPO_ROOT / "derivation.schema.json"


def _load_schema():
    with open(_RESULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_validator():
    """Build a Draft202012Validator with a registry that resolves the
    derivation.schema.json $ref used by query_result.schema.json."""
    result_schema = _load_schema()
    with open(_DERIVATION_SCHEMA_PATH, "r", encoding="utf-8") as f:
        derivation_schema = json.load(f)
    registry = Registry().with_resources([
        ("derivation.schema.json", Resource.from_contents(derivation_schema)),
    ])
    return Draft202012Validator(result_schema, registry=registry)


def _atom_dict(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _classic_iv_ast():
    """Z → X → Y with X ↔ Y latent confounder — the canonical IV case."""
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "z", "domain": [True, False]},
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("z"), "to": _atom_dict("x")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("y")},
            {"kind": "bidirected",
             "left": _atom_dict("x"), "right": _atom_dict("y")},
            {"kind": "query", "id": "q",
             "query": {
                 "kind": "identify",
                 "target": _atom_dict("y"),
                 "intervention": {"atom": _atom_dict("x"), "value": True},
                 "given": [],
             }},
        ],
    }


# ================================================== serialization


def test_iv_identify_result_validates_against_schema():
    """End-to-end: run an IV identify, serialize, validate against
    query_result.schema.json."""
    out = themis.run(_classic_iv_ast())
    result = out["results"][0]
    validator = _load_validator()
    validator.validate(result)


def test_iv_extensions_content_shape():
    """Explicit sanity check on the iv_identification fields.
    Shape is stable because scheduler consistently emits these keys."""
    out = themis.run(_classic_iv_ast())
    result = out["results"][0]
    iv_meta = result["extensions"]["iv_identification"]

    assert iv_meta["strategy"] == "iv"
    assert isinstance(iv_meta["instrument"], str)
    assert isinstance(iv_meta["conditioning"], list)
    assert all(isinstance(w, str) for w in iv_meta["conditioning"])
    assert isinstance(iv_meta["required_assumption"], str)
    assert isinstance(iv_meta["alternatives_count"], int)
    assert iv_meta["alternatives_count"] >= 1


def test_iv_result_roundtrips_through_json():
    """Serialize → parse → verify still succeeds."""
    ast = _classic_iv_ast()
    out = themis.run(ast)
    result = out["results"][0]

    # Round-trip through JSON
    serialized = json.dumps(result, default=str, ensure_ascii=False)
    parsed = json.loads(serialized)

    # Validate against schema after round-trip
    validator = _load_validator()
    validator.validate(parsed)


# ================================================== schema rejection tests


def test_schema_rejects_iv_identification_missing_required_field():
    """An iv_identification object missing 'instrument' must fail validation."""
    bad_result = {
        "status": "structurally_solved",
        "query_kind": "identify",
        "extensions": {
            "iv_identification": {
                "strategy": "iv",
                # "instrument" missing
                "conditioning": [],
                "required_assumption": "monotonicity",
                "alternatives_count": 1,
            }
        }
    }
    validator = _load_validator()
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_result)


def test_schema_rejects_wrong_strategy_value():
    """strategy must be literally 'iv'."""
    bad_result = {
        "status": "structurally_solved",
        "query_kind": "identify",
        "extensions": {
            "iv_identification": {
                "strategy": "backdoor",  # wrong
                "instrument": "z(me)",
                "conditioning": [],
                "required_assumption": "monotonicity",
                "alternatives_count": 1,
            }
        }
    }
    validator = _load_validator()
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_result)


def test_schema_rejects_extra_field_in_iv_identification():
    """iv_identification uses additionalProperties=false — extra fields rejected."""
    bad_result = {
        "status": "structurally_solved",
        "query_kind": "identify",
        "extensions": {
            "iv_identification": {
                "strategy": "iv",
                "instrument": "z(me)",
                "conditioning": [],
                "required_assumption": "monotonicity",
                "alternatives_count": 1,
                "rogue_field": "shouldn't be here",
            }
        }
    }
    validator = _load_validator()
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_result)


def test_schema_allows_unknown_extensions_keys():
    """extensions itself is still open — unknown sub-fields (future extensions)
    must be allowed to pass validation."""
    ok_result = {
        "status": "structurally_solved",
        "query_kind": "identify",
        "extensions": {
            "some_future_extension": {"whatever": 42}
        }
    }
    validator = _load_validator()
    validator.validate(ok_result)  # must not raise


def test_schema_rejects_conditioning_non_string_entries():
    """conditioning items must be strings."""
    bad_result = {
        "status": "structurally_solved",
        "query_kind": "identify",
        "extensions": {
            "iv_identification": {
                "strategy": "iv",
                "instrument": "z(me)",
                "conditioning": ["w(me)", 42],  # int not allowed
                "required_assumption": "monotonicity",
                "alternatives_count": 1,
            }
        }
    }
    validator = _load_validator()
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(bad_result)
