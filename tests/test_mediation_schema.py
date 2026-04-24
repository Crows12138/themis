"""Phase 6.mediation S.M.4: schema + result serialization.

Validates that:
- Effect queries with mediator serialize to JSON matching
  query_result.schema.json (including extensions.mediation_decomposition)
- The NDE/NIE, CDE, and invalid-mediator variants all conform
- Malformed mediation_decomposition payloads are rejected
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
import pytest

import themis


_REPO_ROOT = Path(__file__).parent.parent
_RESULT_SCHEMA_PATH = _REPO_ROOT / "query_result.schema.json"
_DERIVATION_SCHEMA_PATH = _REPO_ROOT / "derivation.schema.json"


def _load_validator():
    with open(_RESULT_SCHEMA_PATH, "r", encoding="utf-8") as f:
        result_schema = json.load(f)
    with open(_DERIVATION_SCHEMA_PATH, "r", encoding="utf-8") as f:
        derivation_schema = json.load(f)
    registry = Registry().with_resources([
        ("derivation.schema.json", Resource.from_contents(derivation_schema)),
    ])
    return Draft202012Validator(result_schema, registry=registry)


def _atom_dict(pred):
    return {"predicate": pred, "args": [{"type": "const", "name": "me"}]}


def _bare_mediator_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("m"), "to": _atom_dict("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom_dict("x"), "value": True},
                "target": {"atom": _atom_dict("y"), "value": True},
                "given": [],
                "mediator": _atom_dict("m"),
            }},
        ],
    }


def _intermediate_confounder_ast():
    return {
        "version": "0.1",
        "domain": {"objects": [{"kind": "object", "name": "me"}]},
        "statements": [
            {"kind": "variable", "predicate": "x", "domain": [True, False]},
            {"kind": "variable", "predicate": "w", "domain": [True, False]},
            {"kind": "variable", "predicate": "m", "domain": [True, False]},
            {"kind": "variable", "predicate": "y", "domain": [True, False]},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("w")},
            {"kind": "cause", "from": _atom_dict("w"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("w"), "to": _atom_dict("y")},
            {"kind": "cause", "from": _atom_dict("x"), "to": _atom_dict("m")},
            {"kind": "cause", "from": _atom_dict("m"), "to": _atom_dict("y")},
            {"kind": "query", "id": "q", "query": {
                "kind": "effect",
                "intervention": {"atom": _atom_dict("x"), "value": True},
                "target": {"atom": _atom_dict("y"), "value": True},
                "given": [],
                "mediator": _atom_dict("m"),
            }},
        ],
    }


# ============================================= end-to-end serialization


def test_bare_mediator_result_validates_against_schema():
    out = themis.run(_bare_mediator_ast())
    result = out["results"][0]
    validator = _load_validator()
    validator.validate(result)  # raises if bad

    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["strategy"] == "nde_nie"
    assert mediation["mediator_valid"] is True
    assert mediation["nde_nie"]["failed_condition"] is None
    assert mediation["cde"]["failed_condition"] is None


def test_intermediate_confounder_result_validates_against_schema():
    out = themis.run(_intermediate_confounder_ast())
    result = out["results"][0]
    validator = _load_validator()
    validator.validate(result)

    mediation = result["extensions"]["mediation_decomposition"]
    assert mediation["strategy"] == "none"
    assert mediation["nde_nie"]["identifiable"] is False
    assert mediation["cde"]["identifiable"] is False
    # failed_condition enum values enforced by schema
    assert mediation["nde_nie"]["failed_condition"] in ("M1", "M2", "M3", "M4")
    assert mediation["cde"]["failed_condition"] in ("C1", "C2")


# ============================================= invalid payloads rejected


def _minimal_result_base():
    """Baseline schema-conforming result to mutate."""
    return {
        "status": "structurally_solved",
        "query_kind": "effect",
        "query_id": "q",
        "structural_result": {"value": True},
    }


def test_schema_rejects_unknown_strategy_value():
    validator = _load_validator()
    bad = _minimal_result_base()
    bad["extensions"] = {
        "mediation_decomposition": {
            "mediator": "m(me)",
            "mediator_valid": True,
            "strategy": "bogus_strategy",  # not in enum
            "nde_nie": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
            "cde": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
        }
    }
    with pytest.raises(Exception):
        validator.validate(bad)


def test_schema_rejects_missing_required_fields():
    validator = _load_validator()
    bad = _minimal_result_base()
    bad["extensions"] = {
        "mediation_decomposition": {
            "mediator": "m(me)",
            # mediator_valid omitted — required
            "nde_nie": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
            "cde": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
        }
    }
    with pytest.raises(Exception):
        validator.validate(bad)


def test_schema_rejects_invalid_failed_condition_enum():
    validator = _load_validator()
    bad = _minimal_result_base()
    bad["extensions"] = {
        "mediation_decomposition": {
            "mediator": "m(me)",
            "mediator_valid": True,
            "nde_nie": {
                "identifiable": False,
                "adjustment": [],
                "failed_condition": "M5",  # not in enum
            },
            "cde": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
        }
    }
    with pytest.raises(Exception):
        validator.validate(bad)


def test_schema_rejects_additional_properties():
    validator = _load_validator()
    bad = _minimal_result_base()
    bad["extensions"] = {
        "mediation_decomposition": {
            "mediator": "m(me)",
            "mediator_valid": True,
            "strategy": "nde_nie",
            "nde_nie": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
            "cde": {
                "identifiable": True, "adjustment": [], "failed_condition": None,
            },
            "extra_unexpected_key": "nope",
        }
    }
    with pytest.raises(Exception):
        validator.validate(bad)


def test_schema_accepts_minimal_valid_payload():
    """Sanity: the minimal shape (strategy=none, both branches
    unidentifiable) is accepted."""
    validator = _load_validator()
    ok = _minimal_result_base()
    ok["extensions"] = {
        "mediation_decomposition": {
            "mediator": "m(me)",
            "mediator_valid": True,
            "strategy": "none",
            "nde_nie": {
                "identifiable": False, "adjustment": [],
                "failed_condition": "M3",
            },
            "cde": {
                "identifiable": False, "adjustment": [],
                "failed_condition": "C1",
            },
        }
    }
    validator.validate(ok)  # must not raise
