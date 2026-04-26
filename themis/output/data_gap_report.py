"""Phase 10 §10.3 — DataGapReport generator.

Pure-function synthesis of a structured "what data is still needed" report
from existing result-envelope signals (derivation steps, investigation
requests, framing notes, extensions). No I/O.

Per Phase 10 charter §4 out-of-scope: this module **MUST NOT**
- import any KB / retrieval module,
- make HTTP / file / DB calls,
- call out to LLMs.

It only reads what dispatch already produced and re-shapes it into the
DataGap / DataGapReport schema. The independence pin in T10 verifier
(S.10.4) guarantees the verifier itself does not depend on this module.

Eight gap_kind branches per charter §2.2:

1. unidentifiable_no_admissible_set       — derivation has unidentifiable_*
2. missing_distribution                   — investigation parameter group
3. missing_population_distribution        — placeholder, populated by future
                                            multi-source transport (§T9.2/§T9.3)
4. missing_assumption                     — status NEEDS_ASSUMPTION or
                                            assumption-pending derivation
5. missing_iv_candidate                   — structure group naming an IV gap
6. missing_mediator_data                  — mediation block valid + parameter
                                            request for mediator distribution
7. transport_target_distribution_unknown  — transport_identification block
                                            present with non-empty Z (P*(Z)
                                            never quantified in §T9.1)
8. ambiguous_variable_definition          — framing_notes non-empty
"""
from __future__ import annotations

from typing import Iterable

from ..types import (
    DataGap,
    DataGapReport,
    DerivationStep,
    FramingNote,
    GapBlocks,
    GapKind,
    GapProvenanceRef,
    GapRefKind,
    GapRequiredData,
    GapSeverity,
    InvestigationRequest,
    QueryKind,
    RequiredDataType,
    ResultStatus,
)

# ============================================ failure-rule registry
#
# Rule names whose presence means a structural failure happened. The
# scheduler is in the process of also marking these with success=False
# (Phase 10 §10.2 added the field with default True). Until the scheduler
# is fully converted, the generator detects failure both ways:
#   (a) explicit: step.success is False
#   (b) by name : step.rule in FAILURE_RULE_NAMES
_FAILURE_RULE_NAMES: frozenset[str] = frozenset({
    "unidentifiable_via_backdoor",
    "unidentifiable_via_front_door",
    "unidentifiable_via_iv",
    "unidentifiable_via_mediation",
    "unidentifiable_via_transport",
})


def _step_failed(step: DerivationStep) -> bool:
    return (not step.success) or step.rule in _FAILURE_RULE_NAMES


# ============================================ public entry


_QUERY_KINDS_WITHOUT_DATA_NEEDS: frozenset[QueryKind] = frozenset({
    QueryKind.CAUSE,
    QueryKind.ASSOC,
    QueryKind.PROBABILITY,
})


def compute_data_gap_report(
    *,
    query_kind: QueryKind,
    status: ResultStatus,
    derivation: tuple[DerivationStep, ...] = (),
    investigation_requests: tuple[InvestigationRequest, ...] = (),
    framing_notes: tuple[FramingNote, ...] = (),
    extensions: dict | None = None,
) -> DataGapReport | None:
    """Synthesize a DataGapReport from the result-envelope signals.

    Returns ``None`` when the query kind does not carry data needs
    (cause / assoc / probability) and no framing or assumption gaps
    exist. For effect / identify / counterfactual queries the returned
    report may still have ``gaps=()`` when fully solved — callers can
    distinguish "no need to ask" (None) from "asked and got a clean
    bill of health" (empty tuple).
    """
    extensions = extensions or {}

    # For cause / assoc / probability the only data-need-bearing channel
    # is framing (variable definition ambiguity). If that's also empty,
    # short-circuit to None — no point attaching an empty report.
    if query_kind in _QUERY_KINDS_WITHOUT_DATA_NEEDS and not framing_notes:
        return None

    gaps: list[DataGap] = []
    gaps.extend(_classify_unidentifiable(derivation))
    gaps.extend(
        _classify_unidentifiable_from_request(investigation_requests)
    )
    gaps.extend(_classify_missing_distribution(investigation_requests))
    gaps.extend(_classify_missing_population_distribution(extensions))
    gaps.extend(_classify_missing_assumption(
        status, derivation, investigation_requests
    ))
    gaps.extend(_classify_missing_iv(investigation_requests, derivation))
    gaps.extend(_classify_missing_mediator(extensions, investigation_requests))
    gaps.extend(_classify_transport_target_distribution(extensions))
    gaps.extend(_classify_ambiguous_variable(framing_notes))

    gaps.sort(key=_gap_sort_key)
    summary = _make_summary(gaps)
    actionable = _make_actionable_steps(gaps)
    return DataGapReport(
        summary=summary,
        gaps=tuple(gaps),
        actionable_next_steps=tuple(actionable),
    )


# ============================================ classifiers


def _classify_unidentifiable(
    derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    for step in derivation:
        if not _step_failed(step):
            continue
        # IV-specific failure routes through _classify_missing_iv to attach
        # IV-flavored copy and avoid double-counting.
        if "iv" in step.rule:
            continue
        # Transport-specific failure routes through transport classifier.
        if "transport" in step.rule:
            continue
        yield DataGap(
            kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
            severity=GapSeverity.BLOCKING,
            description=(
                f"识别失败：rule `{step.rule}` 报告无可调整集 / 公式不存在"
            ),
            blocks=GapBlocks.IDENTIFICATION,
            provenance=(_step_ref(step),),
            if_provided="可给出识别公式 + 后续点估计",
            alternative_paths=(
                "测量并加入 unmeasured confounder Z，重新识别",
                "在 X 上做 RCT (如可行)，旁路 backdoor",
                "找一个满足 IV 条件的工具变量",
            ),
        )


def _classify_unidentifiable_from_request(
    requests: tuple[InvestigationRequest, ...],
) -> Iterable[DataGap]:
    """Identification failures that go through the missing-info channel
    (no derivation step) — e.g. ADMG identify_admg returning a
    structure-group request with target ``query:identify_*``."""
    for req in requests:
        if req.group != "structure":
            continue
        for item in req.items:
            target = item.target.lower()
            if "iv" in target:
                # Routes through _classify_missing_iv to keep IV-flavored
                # alternatives.
                continue
            if not target.startswith("query:identify"):
                continue
            yield DataGap(
                kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
                severity=GapSeverity.BLOCKING,
                description=(
                    f"识别路径失败：{item.reason or item.target}"
                ),
                blocks=GapBlocks.IDENTIFICATION,
                if_provided="可给出识别公式 + 后续点估计",
                alternative_paths=(
                    "测量并加入 unmeasured confounder Z，重新识别",
                    "在 X 上做 RCT (如可行)，旁路 backdoor",
                    "找一个满足 IV 条件的工具变量",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )


def _classify_missing_distribution(
    requests: tuple[InvestigationRequest, ...],
) -> Iterable[DataGap]:
    for req in requests:
        if req.group != "parameter":
            continue
        for item in req.items:
            target = item.target  # e.g. "P(y=true|x=true)"
            # The MissingItem.name carries a "parameter:" prefix from the
            # upstream pusher; strip it for user-facing copy. Provenance
            # ref_id keeps the prefixed form so T10-1 can match.
            display = target[len("parameter:"):] if target.startswith(
                "parameter:"
            ) else target
            signature = _distribution_signature(display)
            yield DataGap(
                kind=GapKind.MISSING_DISTRIBUTION,
                severity=GapSeverity.BLOCKING,
                description=f"缺概率分布 {display}",
                blocks=GapBlocks.POINT_ESTIMATE,
                signature=signature,
                required_data=GapRequiredData(
                    data_type=(
                        RequiredDataType.IPD
                        if signature == "conditional"
                        else RequiredDataType.MARGINAL
                    ),
                ),
                if_provided="可给点估计",
                alternative_paths=(
                    "接受 Balke-Pearl bounds 给区间答案",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )


def _classify_missing_population_distribution(
    extensions: dict,
) -> Iterable[DataGap]:
    """Placeholder. The signal that triggers this — a multi-source
    transport block (§T9.2 / §T9.3) — does not yet exist in the kernel.
    Kept as a stable enum slot so future phases plug in without schema
    revisions. Returns empty in current scope."""
    return ()


def _classify_missing_assumption(
    status: ResultStatus,
    derivation: tuple[DerivationStep, ...],
    requests: tuple[InvestigationRequest, ...],
) -> Iterable[DataGap]:
    if status == ResultStatus.NEEDS_ASSUMPTION:
        # Try to find the precise assumption from missing-info channel.
        for req in requests:
            if req.group != "assumption":
                continue
            for item in req.items:
                yield DataGap(
                    kind=GapKind.MISSING_ASSUMPTION,
                    severity=GapSeverity.IMPORTANT,
                    description=f"识别需要假设：{item.target}",
                    blocks=GapBlocks.POINT_ESTIMATE,
                    if_provided="可给点估计（在该假设成立的前提下）",
                    alternative_paths=(
                        "接受 bounds 而非点估计 (Balke-Pearl / Manski)",
                        "运行 sensitivity analysis 量化假设违反程度",
                    ),
                    provenance=(
                        GapProvenanceRef(
                            ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                            ref_id=item.target,
                        ),
                    ),
                )
            return
        # No assumption-group request — emit a generic placeholder so the
        # gap surface still reflects status.
        yield DataGap(
            kind=GapKind.MISSING_ASSUMPTION,
            severity=GapSeverity.IMPORTANT,
            description="识别需要额外假设（具体假设未在 missing_information 标注）",
            blocks=GapBlocks.POINT_ESTIMATE,
            alternative_paths=(
                "接受 bounds 而非点估计",
                "运行 sensitivity analysis",
            ),
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id="status:needs_assumption",
                ),
            ),
        )


def _classify_missing_iv(
    requests: tuple[InvestigationRequest, ...],
    derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    # Signal A: a structure-group investigation_request whose target
    # mentions IV.
    for req in requests:
        if req.group != "structure":
            continue
        for item in req.items:
            if "iv" not in item.target.lower():
                continue
            yield DataGap(
                kind=GapKind.MISSING_IV_CANDIDATE,
                severity=GapSeverity.IMPORTANT,
                description=f"未找到满足 IV 条件的工具变量：{item.target}",
                blocks=GapBlocks.IDENTIFICATION,
                if_provided="可走 IV 路径给出 LATE / 2SLS-ATE",
                alternative_paths=(
                    "改用 backdoor 路径（如有可调整集）",
                    "改用 front-door 路径（如有有效中介）",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )
    # Signal B: a derivation step on the IV path that failed.
    for step in derivation:
        if not _step_failed(step):
            continue
        if "iv" not in step.rule:
            continue
        yield DataGap(
            kind=GapKind.MISSING_IV_CANDIDATE,
            severity=GapSeverity.IMPORTANT,
            description=f"IV 路径失败：rule `{step.rule}` 未通过",
            blocks=GapBlocks.IDENTIFICATION,
            if_provided="可走 IV 路径给出 LATE / 2SLS-ATE",
            alternative_paths=(
                "改用 backdoor 路径（如有可调整集）",
                "改用 front-door 路径（如有有效中介）",
            ),
            provenance=(_step_ref(step),),
        )


def _classify_missing_mediator(
    extensions: dict,
    requests: tuple[InvestigationRequest, ...],
) -> Iterable[DataGap]:
    block = extensions.get("mediation_decomposition")
    if not block or not block.get("mediator_valid"):
        return
    mediator = block.get("mediator", "<unknown mediator>")
    # Surface only when there's a parameter request whose target hits the
    # mediator atom — otherwise mediation is fully solved.
    for req in requests:
        if req.group != "parameter":
            continue
        for item in req.items:
            if mediator not in item.target:
                continue
            yield DataGap(
                kind=GapKind.MISSING_MEDIATOR_DATA,
                severity=GapSeverity.BLOCKING,
                description=(
                    f"中介分解需要 {mediator} 相关分布：{item.target}"
                ),
                blocks=GapBlocks.POINT_ESTIMATE,
                required_data=GapRequiredData(
                    data_type=RequiredDataType.IPD,
                    variables=(mediator,),
                ),
                if_provided="可给 NDE / NIE / TE 数值分解",
                alternative_paths=(
                    "回退到 CDE（控制中介，给条件直接效应）",
                    "退回 total effect，不分解",
                ),
                provenance=(
                    GapProvenanceRef(
                        ref_kind=GapRefKind.INVESTIGATION_REQUEST,
                        ref_id=item.target,
                    ),
                ),
            )


def _classify_transport_target_distribution(
    extensions: dict,
) -> Iterable[DataGap]:
    block = extensions.get("transport_identification")
    if not block:
        return
    adjustment_set = block.get("adjustment_set", []) or []
    target_pop = block.get("target_population")
    if not adjustment_set:
        return
    # Phase 9 §T9.1 only solves to formula shape; the target-population
    # distribution P*(Z) is never quantified by the kernel. So whenever
    # a transport block carries a non-empty adjustment set we know
    # P*(Z) is open data work for the user.
    z_names = ", ".join(_atom_label(a) for a in adjustment_set)
    yield DataGap(
        kind=GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN,
        severity=GapSeverity.BLOCKING,
        description=(
            f"转移公式已识别，但目标人群 {target_pop or '<未命名>'} "
            f"在 {{{z_names}}} 上的分布 P*(Z) 未提供"
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.MARGINAL,
            population=target_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
        ),
        if_provided="可给目标人群的 transport-adjusted ATE 点估计",
        alternative_paths=(
            "接受源人群 ATE 作为粗略估计（外推有效性弱）",
            "等待 §T9.2 transport sensitivity 给区间",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="s_t9_2"
            ),
        ),
    )


def _classify_ambiguous_variable(
    framing_notes: tuple[FramingNote, ...],
) -> Iterable[DataGap]:
    for note in framing_notes:
        missing_str = ", ".join(note.missing)
        yield DataGap(
            kind=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
            severity=GapSeverity.INFORMATIONAL,
            description=(
                f"变量 `{note.predicate}` 缺操作化定义：{missing_str}"
            ),
            blocks=GapBlocks.IDENTIFICATION,
            if_provided="变量被框架化后下游识别 / 估计才有明确语义",
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.FRAMING_NOTE, ref_id=note.predicate
                ),
            ),
        )


# ============================================ helpers


def _distribution_signature(target: str) -> str | None:
    """Cheap heuristic: P(...|...) is conditional, P(...) is marginal,
    P(a, b) is joint. The signature is informational; the gap is the
    same blocking shape either way."""
    if "|" in target:
        return "conditional"
    if "," in target:
        return "joint"
    return "marginal"


def _step_ref(step: DerivationStep) -> GapProvenanceRef:
    return GapProvenanceRef(
        ref_kind=GapRefKind.DERIVATION_STEP,
        ref_id=step.step_id or step.rule,
    )


def _atom_label(atom_dict: dict) -> str:
    """Render a JSON atom dict back to a short string label for the
    description / required_data.variables list."""
    if isinstance(atom_dict, dict):
        return atom_dict.get("predicate", "<atom>")
    # Defensive: transport_block schemas vary slightly between code paths.
    return str(atom_dict)


_SEVERITY_ORDER: dict[GapSeverity, int] = {
    GapSeverity.BLOCKING: 0,
    GapSeverity.IMPORTANT: 1,
    GapSeverity.INFORMATIONAL: 2,
}


def _gap_sort_key(gap: DataGap) -> tuple[int, str]:
    return (_SEVERITY_ORDER[gap.severity], gap.kind.value)


def _make_summary(gaps: list[DataGap]) -> str:
    if not gaps:
        return ""
    head = gaps[0]
    blocking_count = sum(
        1 for g in gaps if g.severity == GapSeverity.BLOCKING
    )
    if blocking_count <= 1:
        return head.description
    return f"{head.description}（共 {blocking_count} 个 blocking 缺口）"


def _make_actionable_steps(gaps: list[DataGap]) -> list[str]:
    steps: list[str] = []
    for gap in gaps:
        if gap.severity == GapSeverity.INFORMATIONAL:
            continue
        if gap.if_provided:
            steps.append(f"补 {gap.description} → {gap.if_provided}")
        if gap.alternative_paths:
            steps.append(f"或：{gap.alternative_paths[0]}")
    return steps
