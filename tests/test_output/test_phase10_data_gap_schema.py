"""Phase 10 §10.1 schema additions: shape tests.

Covers the new schema fields for DataGapReport:
- ``data_gap_report`` (top-level, nullable) on QueryResult
- ``dataGapReport`` $def: summary + gaps + actionable_next_steps
- ``dataGap`` $def: kind enum (8 values) + severity + provenance array
- ``success`` (optional bool, default true) on derivation steps

Pure schema-level validation — no runtime semantics yet (those land in
S.10.2 types and S.10.3 generator).
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO = Path(__file__).resolve().parents[2]
QR_SCHEMA = json.loads((REPO / "query_result.schema.json").read_text(encoding="utf-8"))
DV_SCHEMA = json.loads((REPO / "derivation.schema.json").read_text(encoding="utf-8"))
ATOM_SCHEMA = json.loads((REPO / "atom.schema.json").read_text(encoding="utf-8"))


def _qr_validator():
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


def _gap(**overrides) -> dict:
    base = {
        "kind": "missing_distribution",
        "severity": "blocking",
        "description": "需要 P(Y|X=true) 的边缘分布",
        "blocks": "point_estimate",
        "provenance": [
            {"ref_kind": "investigation_request", "ref_id": "P(y|x)"}
        ],
    }
    base.update(overrides)
    return base


def _result_envelope(**overrides) -> dict:
    base = {
        "status": "needs_investigation",
        "query_kind": "effect",
    }
    base.update(overrides)
    return base


# ============================================ data_gap_report top-level


def test_data_gap_report_null_validates():
    """cause / assoc queries (no data needs) carry data_gap_report=null."""
    envelope = _result_envelope(query_kind="cause", data_gap_report=None)
    _qr_validator().validate(envelope)


def test_data_gap_report_omitted_validates():
    """Field is optional — back-compat with pre-Phase-10 results."""
    envelope = _result_envelope()
    _qr_validator().validate(envelope)


def test_data_gap_report_minimal_validates():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "需要 P(Y|X) 才能给点估计",
            "gaps": [_gap()],
        }
    )
    _qr_validator().validate(envelope)


def test_data_gap_report_with_actionable_steps_validates():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "缺一个边缘分布",
            "gaps": [_gap()],
            "actionable_next_steps": [
                "查 NHANES 2017-2018 的吸烟人群肺癌发病率",
                "或：接受 Balke-Pearl bounds 给区间答案",
            ],
        }
    )
    _qr_validator().validate(envelope)


def test_data_gap_report_empty_gaps_validates():
    """Status normal but generator chose to attach an empty report — allowed."""
    envelope = _result_envelope(
        status="numerically_solved",
        data_gap_report={"summary": "", "gaps": []},
    )
    _qr_validator().validate(envelope)


# ============================================ dataGap shape


@pytest.mark.parametrize(
    "kind",
    [
        "unidentifiable_no_admissible_set",
        "missing_distribution",
        "missing_population_distribution",
        "missing_assumption",
        "missing_iv_candidate",
        "missing_mediator_data",
        "transport_target_distribution_unknown",
        "transport_source_conditional_unknown",
        "ambiguous_variable_definition",
    ],
)
def test_all_eight_gap_kinds_accepted(kind):
    envelope = _result_envelope(
        data_gap_report={"summary": "x", "gaps": [_gap(kind=kind)]}
    )
    _qr_validator().validate(envelope)


def test_unknown_gap_kind_rejected():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [_gap(kind="not_a_real_kind")],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


@pytest.mark.parametrize(
    "severity", ["blocking", "important", "informational"]
)
def test_all_three_severity_levels_accepted(severity):
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [_gap(severity=severity)],
        }
    )
    _qr_validator().validate(envelope)


def test_unknown_severity_rejected():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [_gap(severity="critical")],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


# ============================================ provenance


def test_provenance_requires_at_least_one_ref():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [_gap(provenance=[])],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


def test_provenance_accepts_multiple_refs():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(
                    provenance=[
                        {"ref_kind": "derivation_step", "ref_id": "step_3"},
                        {
                            "ref_kind": "investigation_request",
                            "ref_id": "P(y|x)",
                        },
                        {"ref_kind": "framing_note", "ref_id": "smoking"},
                    ]
                )
            ],
        }
    )
    _qr_validator().validate(envelope)


@pytest.mark.parametrize(
    "ref_kind",
    [
        "derivation_step",
        "investigation_request",
        "framing_note",
        "verifier_check",
    ],
)
def test_all_four_ref_kinds_accepted(ref_kind):
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(provenance=[{"ref_kind": ref_kind, "ref_id": "x"}])
            ],
        }
    )
    _qr_validator().validate(envelope)


def test_unknown_ref_kind_rejected():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(
                    provenance=[
                        {"ref_kind": "made_up_source", "ref_id": "x"}
                    ]
                )
            ],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


# ============================================ optional fields


def test_signature_field_accepted():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [_gap(signature="conditional")],
        }
    )
    _qr_validator().validate(envelope)


def test_required_data_block_accepted():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(
                    required_data={
                        "data_type": "rct",
                        "population": "adults_with_smoking_exposure",
                        "variables": ["smoking", "lung_cancer"],
                        "min_sample_size": 800,
                        "precision_target": "ATE within ±0.05 at 95% CI",
                    }
                )
            ],
        }
    )
    _qr_validator().validate(envelope)


def test_unknown_data_type_rejected():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(required_data={"data_type": "telepathy"})
            ],
        }
    )
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


def test_alternative_paths_and_if_provided_accepted():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(
                    if_provided="可给点估计 + bootstrap CI",
                    alternative_paths=[
                        "接受 Balke-Pearl bounds (区间)",
                        "添加单调性假设 (point estimate, 假设不可证伪)",
                    ],
                )
            ],
        }
    )
    _qr_validator().validate(envelope)


# ============================================ derivation step.success


def test_derivation_step_without_success_validates():
    """Back-compat: existing rules need not set success explicitly."""
    derivation = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "graph_projection",
                "step_id": "step_0",
                "inputs": {},
                "output": True,
            }
        ],
    }
    jsonschema.Draft202012Validator(DV_SCHEMA).validate(derivation)


def test_derivation_step_with_success_true_validates():
    derivation = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "backdoor_admissible",
                "step_id": "step_1",
                "inputs": {},
                "output": True,
                "success": True,
            }
        ],
    }
    jsonschema.Draft202012Validator(DV_SCHEMA).validate(derivation)


def test_derivation_step_with_success_false_validates():
    """Phase 10: failure-bearing rules emit success=false to feed gap generator."""
    derivation = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "backdoor_failed",
                "step_id": "step_2",
                "inputs": {},
                "output": False,
                "success": False,
            }
        ],
    }
    jsonschema.Draft202012Validator(DV_SCHEMA).validate(derivation)


def test_derivation_step_success_must_be_bool():
    derivation = {
        "version": "0.1",
        "kind": "derivation",
        "steps": [
            {
                "rule": "x",
                "step_id": "step_0",
                "inputs": {},
                "output": True,
                "success": "yes",
            }
        ],
    }
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(DV_SCHEMA).validate(derivation)
