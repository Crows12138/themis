"""Phase 10 §10.1 schema additions: shape tests.

Covers the new schema fields for DataGapReport:
- ``data_gap_report`` (top-level, nullable) on QueryResult
- ``dataGapReport`` $def: summary + gaps
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
from themis.input.syntactic_validator import validator_for


def _qr_validator():
    return validator_for("query_result.schema.json")


def _dv_validator():
    return validator_for("derivation.schema.json")


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


def test_data_gap_report_null_is_refused():
    """This used to be asserted the other way, on a claim nothing supported.

    The docstring said cause / assoc queries carry ``data_gap_report=null``;
    the serializer writes the key only when there IS a report, so null was a
    second legal way to say what absence already said, and no producer ever
    said it. Two spellings for one nothing is what a consumer cannot tell
    apart, so the contract now allows one.
    """
    envelope = _result_envelope(query_kind="cause", data_gap_report=None)
    with pytest.raises(jsonschema.ValidationError):
        _qr_validator().validate(envelope)


def test_data_gap_report_omitted_validates():
    """Field is optional — back-compat with pre-Phase-10 results, and the one
    way this envelope says it has no data needs."""
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


def test_a_next_steps_tail_on_the_report_is_refused():
    """The report carried one, and its own description said the entries
    were Chinese sentences a renderer reads as-is. Every input to them was
    on the gaps beside them, so it was a rendering the kernel had grown,
    with the language written into the contract. The contract refuses it
    now rather than merely omitting it — a producer that keeps writing the
    key finds out here."""
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
    with pytest.raises(jsonschema.ValidationError):
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


def test_alternative_paths_and_the_occasion_are_accepted():
    envelope = _result_envelope(
        data_gap_report={
            "summary": "x",
            "gaps": [
                _gap(
                    said={"what": "P(y|x)"},
                    words={"scale": {"vocabulary": "measurement_scale",
                                     "token": "binary"}},
                    alternative_paths=[
                        {"route": "accept_the_interval",
                         "said": {"fallback": "Balke-Pearl bounds"}},
                        {"route": "tighten_the_iv_interval"},
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
    _dv_validator().validate(derivation)


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
    _dv_validator().validate(derivation)


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
    _dv_validator().validate(derivation)


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
        _dv_validator().validate(derivation)
