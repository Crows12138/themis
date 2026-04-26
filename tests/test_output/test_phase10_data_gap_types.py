"""Phase 10 §10.2 type-layer tests.

Covers:
- DerivationStep.success default / explicit
- DataGap / DataGapReport dataclass shape
- Serialization round-trip via result_orchestrator.to_dict
- Schema conformance of the serialized output (S.10.1 schema cross-check)

Generator (S.10.3), verifier (S.10.4), and dispatch wiring come later;
these tests only exercise the type surface and JSON shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest

from themis.output.result_orchestrator import to_dict
from themis.types import (
    DataGap,
    DataGapReport,
    DerivationStep,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    QueryKind,
    QueryResult,
    RequiredDataType,
    ResultStatus,
)

REPO = Path(__file__).resolve().parents[2]
QR_SCHEMA = json.loads((REPO / "query_result.schema.json").read_text(encoding="utf-8"))


def _qr_validator():
    return jsonschema.Draft202012Validator(QR_SCHEMA)


def _result(**overrides) -> QueryResult:
    base = {
        "status": ResultStatus.NEEDS_INVESTIGATION,
        "query_kind": QueryKind.EFFECT,
    }
    base.update(overrides)
    return QueryResult(**base)


# ============================================ DerivationStep.success


def test_derivation_step_success_defaults_true():
    step = DerivationStep(rule="graph_projection", inputs={}, output=True)
    assert step.success is True


def test_derivation_step_success_explicit_false():
    step = DerivationStep(
        rule="backdoor_failed", inputs={}, output=False, success=False
    )
    assert step.success is False


def test_derivation_step_serializes_success_false():
    """When success=False, serialized form must include the field so the
    DataGapReport generator and T10 verifier can pick it up."""
    from themis.verifier.serialization import derivation_to_dict
    steps = (
        DerivationStep(
            rule="iv_invalid",
            inputs={},
            output=False,
            step_id="step_2",
            success=False,
        ),
    )
    payload = derivation_to_dict(steps)
    assert payload["steps"][0]["success"] is False


def test_derivation_step_omits_success_when_true():
    """Back-compat: existing rule fixtures must serialize unchanged."""
    from themis.verifier.serialization import derivation_to_dict
    steps = (DerivationStep(rule="graph_projection", inputs={}, output=True),)
    payload = derivation_to_dict(steps)
    assert "success" not in payload["steps"][0]


def test_derivation_step_round_trip_success_false():
    from themis.verifier.serialization import (
        derivation_from_dict,
        derivation_to_dict,
    )
    steps = (
        DerivationStep(
            rule="frontdoor_failed",
            inputs={},
            output=False,
            step_id="step_3",
            success=False,
        ),
    )
    payload = derivation_to_dict(steps)
    restored = derivation_from_dict(payload)
    assert restored[0].success is False
    assert restored[0].rule == "frontdoor_failed"


def test_derivation_step_round_trip_success_default_true():
    from themis.verifier.serialization import (
        derivation_from_dict,
        derivation_to_dict,
    )
    steps = (DerivationStep(rule="graph_projection", inputs={}, output=True),)
    payload = derivation_to_dict(steps)
    restored = derivation_from_dict(payload)
    assert restored[0].success is True


# ============================================ DataGap / DataGapReport shape


def test_data_gap_minimal_construction():
    gap = DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description="缺 P(Y|X)",
        blocks=GapBlocks.POINT_ESTIMATE,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id="P(y|x)"
            ),
        ),
    )
    assert gap.kind == GapKind.MISSING_DISTRIBUTION
    assert gap.signature is None
    assert gap.required_data is None
    assert gap.alternative_paths == ()


def test_data_gap_report_orders_preserved_in_construction():
    g1 = DataGap(
        kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
        severity=GapSeverity.BLOCKING,
        description="后门没 block",
        blocks=GapBlocks.IDENTIFICATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="step_5"
            ),
        ),
    )
    g2 = DataGap(
        kind=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
        severity=GapSeverity.INFORMATIONAL,
        description="时间窗口未指定",
        blocks=GapBlocks.IDENTIFICATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.FRAMING_NOTE, ref_id="exercise"
            ),
        ),
    )
    report = DataGapReport(summary="缺识别 + 框架不全", gaps=(g1, g2))
    assert report.gaps[0] is g1
    assert report.gaps[1] is g2


# ============================================ to_dict serialization


def test_query_result_without_data_gap_report_omits_field():
    """Back-compat: pre-Phase-10 results serialize unchanged."""
    result = _result()
    payload = to_dict(result)
    assert "data_gap_report" not in payload
    _qr_validator().validate(payload)


def test_query_result_with_null_data_gap_report_emits_null():
    """Future use: cause / assoc results that explicitly carry a null gap
    report (rather than omitting it). Currently no dispatch path emits
    this, but the type system + serializer must support it."""
    result = QueryResult(
        status=ResultStatus.STRUCTURALLY_SOLVED,
        query_kind=QueryKind.CAUSE,
        data_gap_report=None,
    )
    payload = to_dict(result)
    # When data_gap_report is None, it's omitted (matches existing pattern
    # for other optional fields). Schema accepts both omission and null.
    assert "data_gap_report" not in payload
    _qr_validator().validate(payload)


def test_query_result_with_minimal_data_gap_report_serializes():
    report = DataGapReport(
        summary="需要 P(Y|X)",
        gaps=(
            DataGap(
                kind=GapKind.MISSING_DISTRIBUTION,
                severity=GapSeverity.BLOCKING,
                description="P(Y|X) 未提供",
                blocks=GapBlocks.POINT_ESTIMATE,
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id="P(y|x)",
                    ),
                ),
            ),
        ),
    )
    result = _result(data_gap_report=report)
    payload = to_dict(result)
    assert payload["data_gap_report"]["summary"] == "需要 P(Y|X)"
    assert len(payload["data_gap_report"]["gaps"]) == 1
    assert (
        payload["data_gap_report"]["gaps"][0]["kind"]
        == "missing_distribution"
    )
    _qr_validator().validate(payload)


def test_query_result_with_full_data_gap_report_serializes():
    report = DataGapReport(
        summary="缺 transport 目标分布",
        gaps=(
            DataGap(
                kind=GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
                severity=GapSeverity.BLOCKING,
                description="P*(age, sex, bmi) on user 人群未提供",
                blocks=GapBlocks.TRANSPORT,
                signature=None,
                required_data=GapRequiredData(
                    data_type=RequiredDataType.MARGINAL,
                    population="user_28f_normal_weight",
                    variables=("age", "sex", "bmi"),
                    min_sample_size=300,
                    precision_target="±5%",
                ),
                if_provided="可给目标群体上的 transport-adjusted ATE 点估计",
                alternative_paths=(
                    "接受文献的源群体 ATE 作为粗略估计（牺牲外推有效性）",
                    "运行 sensitivity analysis 给一组转移性 bound",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.DERIVATION_STEP,
                        ref_id="transport_formula",
                    ),
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id="P*(Z)",
                    ),
                ),
            ),
        ),
        actionable_next_steps=(
            "查 NHANES / 中国 CDC 拿用户人群在 (age, sex, bmi) 上的边缘",
            "或：运行 transport sensitivity analysis 给区间答案",
        ),
    )
    result = _result(data_gap_report=report)
    payload = to_dict(result)

    gap = payload["data_gap_report"]["gaps"][0]
    assert gap["kind"] == "transport_target_distribution_unknown"
    assert gap["severity"] == "blocking"
    assert gap["blocks"] == "transport"
    assert gap["required_data"]["data_type"] == "marginal"
    assert gap["required_data"]["variables"] == ["age", "sex", "bmi"]
    assert gap["required_data"]["min_sample_size"] == 300
    assert len(gap["provenance"]) == 2
    assert gap["provenance"][0]["ref_kind"] == "derivation_step"
    assert (
        payload["data_gap_report"]["actionable_next_steps"][0].startswith("查")
    )

    _qr_validator().validate(payload)


def test_data_gap_with_signature_field_serializes():
    gap = DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description="缺条件分布",
        blocks=GapBlocks.POINT_ESTIMATE,
        signature="conditional",
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id="P(y|x,z)"
            ),
        ),
    )
    report = DataGapReport(summary="缺一个条件分布", gaps=(gap,))
    result = _result(data_gap_report=report)
    payload = to_dict(result)
    assert payload["data_gap_report"]["gaps"][0]["signature"] == "conditional"
    _qr_validator().validate(payload)


def test_data_gap_required_data_omits_unset_subfields():
    """Sparse RequiredData should not emit None-valued keys."""
    gap = DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description="缺一个边缘",
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(
            data_type=RequiredDataType.MARGINAL,
            variables=("smoking",),
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id="P(smoking)"
            ),
        ),
    )
    report = DataGapReport(summary="x", gaps=(gap,))
    result = _result(data_gap_report=report)
    payload = to_dict(result)
    rd = payload["data_gap_report"]["gaps"][0]["required_data"]
    assert rd == {"data_type": "marginal", "variables": ["smoking"]}
    _qr_validator().validate(payload)


def test_data_gap_required_data_entirely_empty_omits_block():
    """If RequiredData has all None / empty fields, the block itself is
    omitted from the JSON (rather than emitting an empty object)."""
    gap = DataGap(
        kind=GapKind.MISSING_DISTRIBUTION,
        severity=GapSeverity.BLOCKING,
        description="x",
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id="x"
            ),
        ),
    )
    report = DataGapReport(summary="x", gaps=(gap,))
    payload = to_dict(_result(data_gap_report=report))
    assert "required_data" not in payload["data_gap_report"]["gaps"][0]
    _qr_validator().validate(payload)


def test_query_result_with_empty_actionable_steps_omits_field():
    report = DataGapReport(
        summary="x",
        gaps=(
            DataGap(
                kind=GapKind.MISSING_DISTRIBUTION,
                severity=GapSeverity.BLOCKING,
                description="x",
                blocks=GapBlocks.POINT_ESTIMATE,
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST, ref_id="x"
                    ),
                ),
            ),
        ),
    )
    payload = to_dict(_result(data_gap_report=report))
    assert "actionable_next_steps" not in payload["data_gap_report"]
    _qr_validator().validate(payload)


def test_query_result_with_empty_gaps_serializes():
    """numerically_solved with no gaps but an empty report attached."""
    report = DataGapReport(summary="", gaps=())
    payload = to_dict(_result(data_gap_report=report))
    assert payload["data_gap_report"] == {"summary": "", "gaps": []}
    _qr_validator().validate(payload)
