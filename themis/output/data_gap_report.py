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

Gap_kind branches (current enum: see ``themis.types.GapKind``; cross-file
sync is pinned by ``tests/test_gap_kind_coverage_meta.py``):

Phase 10 charter §2.2 (initial 8):
1. unidentifiable_no_admissible_set       — derivation has unidentifiable_*
2. missing_distribution                   — investigation parameter group
3. missing_population_distribution        — placeholder for §T9.2/§T9.3
4. missing_assumption                     — status NEEDS_ASSUMPTION
5. missing_iv_candidate                   — structure group naming an IV gap
6. missing_mediator_data                  — mediation block valid + parameter
7. transport_target_distribution_unknown  — transport_identification + non-empty Z
8. ambiguous_variable_definition          — framing_notes non-empty

Phase 11+ structural caveats (must-disclose channel; mirrored to
``result.explanation`` by ``scheduler._attach_structural_caveats``):
- unverified_proposal_edge_on_query_path — Phase 11.x §C
- iv_identification_assumption_required — Phase 6.iv
- mediation_identification_assumption_required — Phase 6.mediation
- transport_identification_assumption_required — Phase 9 §T9.1
- llm_declared_ambiguity — A1-emitted ambiguities
- answer_is_bounds_not_point_estimate — Phase 12 bounds-first
- low_confidence_input_data — composite confidence below threshold
- front_door_identification_assumption_required — A6.front-door (program-shape
  fallback added iter 10 for needs_investigation + missing-theta case)
- counterfactual_identification_assumption_required — Phase 5 §C
- graph_learned_from_data — Phase 8.1 discovery
- transport_source_conditional_unknown — Phase 9 §T9.1 second data need
- dose_response_data_required — Phase 13

L3 simulation 2026-05-07 additions (iter 5 / iter 19):
- unmeasured_confounder_risk — DAG declares confounders but no bidirected;
  warns measured-covariate adjustment may have residual unmeasured-confounder
  bias. Cross-domain examples (HRT-CVD / Card 1995 / vitamin D-CVD).
- unattempted_layer_due_to_dispatch_conflict — query has BOTH mediator and
  target_population set; only one extension populated. Discloses silent skip.
"""
from __future__ import annotations

from typing import Iterable

from .sample_size import (
    estimate_min_n_single_proportion,
    estimate_min_n_two_arm_binary,
    is_binary_outcome_distribution,
)
from ..types import (
    BidirectedStatement,
    CauseStatement,
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
    VariableDeclaration,
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
    program=None,
    stmt=None,
    structural_result=None,
    bounds_result=None,
    confidence: float | None = None,
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

    must_disclose_gaps: list[DataGap] = []
    must_disclose_gaps.extend(
        _classify_unverified_proposal_edges(
            program, structural_result, stmt, extensions,
        )
    )
    must_disclose_gaps.extend(_classify_iv_assumption(extensions))
    must_disclose_gaps.extend(_classify_mediation_assumptions(extensions))
    must_disclose_gaps.extend(_classify_transport_assumptions(extensions))
    must_disclose_gaps.extend(_classify_llm_ambiguities(extensions))
    must_disclose_gaps.extend(_classify_bounds_not_point(bounds_result))
    must_disclose_gaps.extend(_classify_low_confidence(confidence))
    must_disclose_gaps.extend(_classify_front_door_assumptions(
        derivation, program=program, stmt=stmt,
    ))
    must_disclose_gaps.extend(_classify_counterfactual_assumptions(
        derivation, status, query_kind,
    ))
    must_disclose_gaps.extend(_classify_graph_learned_from_data(program))
    must_disclose_gaps.extend(_classify_unmeasured_confounder_risk(
        program=program, query_kind=query_kind, stmt=stmt, status=status,
    ))
    must_disclose_gaps.extend(_classify_unattempted_layer_dispatch_conflict(
        stmt=stmt, extensions=extensions,
    ))

    # For cause / assoc / probability the only data-need-bearing channel
    # was framing. Must-disclose caveats now also keep the report alive
    # — without them a renderer would never see the structural caveats
    # the kernel detected.
    if (
        query_kind in _QUERY_KINDS_WITHOUT_DATA_NEEDS
        and not framing_notes
        and not must_disclose_gaps
    ):
        return None

    gaps: list[DataGap] = list(must_disclose_gaps)
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
    gaps.extend(_classify_ambiguous_variable(framing_notes, stmt))
    gaps.extend(_classify_dose_response_data(program, stmt, derivation))

    gaps.sort(key=_gap_sort_key)
    summary = _make_summary(gaps)
    actionable = _make_actionable_steps(gaps)
    return DataGapReport(
        summary=summary,
        gaps=tuple(gaps),
        actionable_next_steps=tuple(actionable),
    )


def _classify_unverified_proposal_edges(
    program,
    structural_result,
    stmt,
    extensions: dict,
) -> Iterable[DataGap]:
    """The structural answer rests on edges the upstream LLM proposed
    (``annotations.source == "llm_proposal"``) rather than
    evidence-backed edges. Reasoning replays the LLM's own assumption
    instead of independently verifying it — surfaced as INFORMATIONAL so
    the renderer can disclose without overstating risk.

    Both directed (``CauseStatement``) and bidirected
    (``BidirectedStatement``, latent common cause) edges are scanned.
    Bidirected proposal edges are particularly load-bearing for IV /
    front-door identification, where the latent confounder is the
    *reason* an alternative identification strategy is needed.

    Edges are flagged via two complementary signals (either suffices):

    1. **supporting_paths** — concrete on cause / assoc results; each
       consecutive node pair on a returned path is an edge that was
       actually traversed.

    2. **DAG walk** — for every other query kind (effect / identify /
       IV / mediation / counterfactual), enumerate simple directed
       paths in the program-derived DAG between every pair of
       query-relevant predicates (intervention / target / mediator /
       given), plus instrument / adjustment-set predicates pulled from
       ``extensions`` when the dispatcher exposed them. Any
       proposal edge lying on such a path is load-bearing.

    Bidirected proposal edges are flagged when either endpoint is a
    query-relevant predicate (they are undirected, so 'on the path' is
    not the natural test — incidence on a query node is).
    """
    if program is None:
        return

    proposal_edges, adjacency = _build_dag_with_proposals(program)
    bidirected_proposals = _collect_bidirected_proposal_pairs(program)
    if not proposal_edges and not bidirected_proposals:
        return

    flagged: set[tuple[str, str]] = set()

    paths = getattr(structural_result, "supporting_paths", ()) or ()
    for path in paths:
        for i in range(len(path) - 1):
            a_pred = path[i].split("(", 1)[0]
            b_pred = path[i + 1].split("(", 1)[0]
            if (a_pred, b_pred) in proposal_edges:
                flagged.add((a_pred, b_pred))

    relevant = _query_relevant_predicates_for_path_walk(stmt, extensions)
    if relevant and adjacency:
        for src in relevant:
            for dst in relevant:
                if src == dst:
                    continue
                for path in _enumerate_simple_directed_paths(
                    adjacency, src, dst,
                ):
                    for i in range(len(path) - 1):
                        edge = (path[i], path[i + 1])
                        if edge in proposal_edges:
                            flagged.add(edge)

    if bidirected_proposals and relevant:
        for left, right in bidirected_proposals:
            if left in relevant or right in relevant:
                # Render with ↔ so the renderer distinguishes from
                # directed edges. Tuple ordered for deterministic output.
                a, b = sorted((left, right))
                flagged.add((a, f"↔{b}"))

    edge_sources = _index_edge_sources(program)
    for frm, to in sorted(flagged):
        # Look up the actual source string so the description can name
        # 'LLM hypothesis' vs 'PC algorithm output' specifically.
        bidirected = to.startswith("↔")
        clean_to = to[1:] if bidirected else to
        source_key = (
            ("bidirected", tuple(sorted((frm, clean_to))))
            if bidirected
            else ("cause", (frm, clean_to))
        )
        source_str = edge_sources.get(source_key, "")
        edge_render = f"{frm} ↔ {clean_to}" if bidirected else f"{frm} → {to}"
        if source_str.startswith("discovery:"):
            algo = source_str.split(":", 1)[1]
            description = (
                f"结构性回答途径上的边 `{edge_render}` 是因果发现算法 "
                f"`{algo.upper()}` 从数据中学出的，结果以算法假设（如 PC: "
                f"忠实性 + 因果充足性；LiNGAM: 线性 + 非高斯）为前提。"
            )
        else:
            description = (
                f"结构性回答途径上的边 `{edge_render}` 是上游 LLM 提出的"
                f"假设（annotations.source = llm_proposal），不是经证据"
                f"支持的边。当前回答相当于复述这条假设，而非独立验证。"
            )
        yield DataGap(
            kind=GapKind.UNVERIFIED_PROPOSAL_EDGE_ON_QUERY_PATH,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            if_provided="可换成证据支持的边或外部文献的引用",
            alternative_paths=(
                "提供支持这条边的研究 / 数据来源",
                "改为询问'若该边成立则…'的条件性问题",
            ),
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=(
                        f"program:bidirected:{frm}↔{clean_to}:annotations.source"
                        if bidirected
                        else f"program:cause:{frm}->{to}:annotations.source"
                    ),
                ),
            ),
        )


def _index_edge_sources(program) -> dict[tuple[str, tuple[str, ...]], str]:
    """Build a lookup from (kind, predicate-pair) to the verbatim
    annotations.source string. ``kind`` is ``"cause"`` or ``"bidirected"``.
    Used by the proposal-edge classifier to render description text that
    names the *kind* of non-evidence source (LLM vs discovery algorithm).
    """
    out: dict[tuple[str, tuple[str, ...]], str] = {}
    for st in program.statements:
        ann = getattr(st, "annotations", None)
        if ann is None or ann.source is None:
            continue
        if isinstance(st, CauseStatement):
            out[("cause", (st.from_atom.predicate, st.to_atom.predicate))] = ann.source
        elif isinstance(st, BidirectedStatement):
            pair = tuple(sorted((st.left.predicate, st.right.predicate)))
            out[("bidirected", pair)] = ann.source
    return out


def _collect_bidirected_proposal_pairs(
    program,
) -> set[tuple[str, str]]:
    """Bidirected (latent common cause) statements with a non-evidence
    ``annotations.source``. Returned unordered as sets of (left, right)
    predicate pairs."""
    pairs: set[tuple[str, str]] = set()
    for st in program.statements:
        if not isinstance(st, BidirectedStatement):
            continue
        ann = getattr(st, "annotations", None)
        if ann is None or not _is_non_evidence_source(ann.source):
            continue
        pairs.add((st.left.predicate, st.right.predicate))
    return pairs


def _build_dag_with_proposals(
    program,
) -> tuple[set[tuple[str, str]], dict[str, list[str]]]:
    """Pull the predicate-level DAG and the subset of non-evidence edges
    out of program.statements in a single pass.

    "Non-evidence" covers both ``annotations.source == "llm_proposal"``
    (LLM hypothesis) and ``annotations.source`` starting with
    ``"discovery:"`` (PC / FCI / LiNGAM algorithmic output). Both share
    the load-bearing-without-citation property.
    """
    proposal_edges: set[tuple[str, str]] = set()
    adjacency: dict[str, list[str]] = {}
    for st in program.statements:
        if not isinstance(st, CauseStatement):
            continue
        edge = (st.from_atom.predicate, st.to_atom.predicate)
        adjacency.setdefault(edge[0], []).append(edge[1])
        ann = getattr(st, "annotations", None)
        if ann is not None and _is_non_evidence_source(ann.source):
            proposal_edges.add(edge)
    return proposal_edges, adjacency


def _is_non_evidence_source(source: str | None) -> bool:
    """An edge source counts as non-evidence (must-disclose) when it is
    ``"llm_proposal"`` or starts with ``"discovery:"``."""
    if source is None:
        return False
    if source == "llm_proposal":
        return True
    if source.startswith("discovery:"):
        return True
    return False


def _query_relevant_predicates_for_path_walk(
    stmt, extensions: dict,
) -> frozenset[str]:
    """Predicates whose pairwise directed paths are load-bearing for the
    query. Combines query atoms (via ``_query_referenced_predicates``)
    with structural artifacts the dispatcher exposed in ``extensions``:
    instrument (IV), adjustment set / mediator adjustment, mediator.
    """
    base = set(_query_referenced_predicates(stmt))

    iv = (extensions or {}).get("iv_identification") or {}
    instrument = iv.get("instrument")
    if instrument:
        base.add(str(instrument).split("(", 1)[0])
    for entry in iv.get("conditioning") or ():
        base.add(str(entry).split("(", 1)[0])

    mediation = (extensions or {}).get("mediation_decomposition") or {}
    nde = mediation.get("nde_nie") or {}
    cde = mediation.get("cde") or {}
    for entry in (nde.get("adjustment") or ()):
        base.add(str(entry).split("(", 1)[0])
    for entry in (cde.get("adjustment") or ()):
        base.add(str(entry).split("(", 1)[0])
    mediator = mediation.get("mediator")
    if mediator:
        base.add(str(mediator).split("(", 1)[0])

    return frozenset(base)


def _classify_iv_assumption(extensions: dict) -> Iterable[DataGap]:
    """IV identification rests on monotonicity (LATE/Wald) or linearity
    (2SLS/ATE). The extension carries the wording verbatim; surface as a
    must-disclose caveat so the renderer cannot present an IV estimate
    as an unconditional ATE."""
    iv = (extensions or {}).get("iv_identification") or {}
    assumption = iv.get("required_assumption")
    instrument = iv.get("instrument")
    if not assumption:
        return
    yield DataGap(
        kind=GapKind.IV_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"IV 识别（工具变量 `{instrument}`）的有效性以下列假设为前提："
            f"{assumption}。读 IV 估计前应明确这条假设是否在你的场景下成立。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.iv_identification.required_assumption",
            ),
        ),
    )


def _classify_mediation_assumptions(
    extensions: dict,
) -> Iterable[DataGap]:
    """NDE/NIE / CDE identification each carry a non-empty `assumptions`
    list when identifiable. Surface a single caveat per identifiable
    branch so the renderer cannot read 'identifiable: true' as
    unconditional."""
    mediation = (extensions or {}).get("mediation_decomposition") or {}
    if not mediation.get("mediator_valid"):
        return
    for branch_name, branch in (
        ("NDE/NIE", mediation.get("nde_nie") or {}),
        ("CDE", mediation.get("cde") or {}),
    ):
        if not branch.get("identifiable"):
            continue
        assumptions = branch.get("assumptions") or ()
        if not assumptions:
            continue
        yield DataGap(
            kind=GapKind.MEDIATION_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=(
                f"中介分解 {branch_name} 标识为可识别，前提是以下假设成立："
                f"{', '.join(assumptions)}。"
            ),
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=(
                        "extensions.mediation_decomposition."
                        f"{'nde_nie' if branch_name == 'NDE/NIE' else 'cde'}"
                        ".assumptions"
                    ),
                ),
            ),
        )


def _classify_transport_assumptions(
    extensions: dict,
) -> Iterable[DataGap]:
    """Transport identification (Bareinboim-Pearl) requires
    S-admissibility plus correct selection-node specification. The
    transferred estimate is invalid outside those assumptions."""
    transport = (extensions or {}).get("transport_identification") or {}
    if not transport:
        return
    src_pop = transport.get("source_population", "<源人群>")
    tgt_pop = transport.get("target_population", "<目标人群>")
    yield DataGap(
        kind=GapKind.TRANSPORT_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"将估计从 {src_pop} 转移到 {tgt_pop} 的有效性以 S-admissibility "
            f"为前提：声明的 selection_nodes 必须正确捕获两人群间分布差异。"
        ),
        blocks=GapBlocks.TRANSPORT,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.transport_identification",
            ),
        ),
    )


def _classify_llm_ambiguities(extensions: dict) -> Iterable[DataGap]:
    """LLM-declared ambiguities the kernel did not resolve into a
    structural decision (reciprocal causation, mechanism vs existence,
    mediator choice). Renderer must surface the LLM's own uncertainty —
    leaving these unspoken would make the answer look confident when the
    upstream itself wasn't."""
    ambiguities = (extensions or {}).get("ambiguities") or ()
    for amb in ambiguities:
        if not isinstance(amb, dict):
            continue
        kind = amb.get("kind", "<unspecified>")
        rationale = amb.get("rationale") or amb.get("note") or ""
        # dose_response_query has its own dedicated gap_kind; skip.
        if kind == "dose_response_query":
            continue
        suffix = f"：{rationale}" if rationale else ""
        yield DataGap(
            kind=GapKind.LLM_DECLARED_AMBIGUITY,
            severity=GapSeverity.INFORMATIONAL,
            description=(
                f"上游 LLM 标记了不确定性 `{kind}`{suffix}。"
                f"答案的解读应将其考虑在内。"
            ),
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id=f"extensions.ambiguities[{kind}]",
                ),
            ),
        )


# Threshold below which composite confidence triggers a must-disclose
# caveat. 0.6 is the conventional "substantial uncertainty" line —
# anything ≥ 0.6 gets through silently to keep the channel signal-rich
# rather than firing on every routine answer.
_LOW_CONFIDENCE_THRESHOLD: float = 0.6


def _classify_low_confidence(confidence: float | None) -> Iterable[DataGap]:
    """Composite confidence (min across slot-level annotations) below the
    threshold means at least one input statement carries substantial
    uncertainty. The answer inherits that uncertainty — surface so it
    does not read as a clean point estimate."""
    if confidence is None:
        return
    if confidence >= _LOW_CONFIDENCE_THRESHOLD:
        return
    yield DataGap(
        kind=GapKind.LOW_CONFIDENCE_INPUT_DATA,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            f"答案的复合可信度为 {confidence:.2f}（< {_LOW_CONFIDENCE_THRESHOLD}）— "
            f"至少有一项输入语句的置信度较低，结果应视为不确定的。具体的薄弱"
            f"环节见 `confidence_sources` 中标记 is_weakest=true 的条目。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="result.confidence",
            ),
        ),
    )


_FRONT_DOOR_DERIVATION_RULES: frozenset[str] = frozenset({
    "front_door_criterion",
    "front_door_adjustment_formula",
    "identify_via_front_door",
})


def _classify_front_door_assumptions(
    derivation: tuple[DerivationStep, ...],
    *,
    program=None,
    stmt=None,
) -> Iterable[DataGap]:
    """Front-door identification rests on Pearl's three graphical premises
    plus consistency. Primary signal is a derivation step with rule in
    ``_FRONT_DOOR_DERIVATION_RULES``. Fallback signal: program-shape
    detection of a front-door pattern (X↔Y bidirected + at least one
    M with X→M and M→Y), used when status is NEEDS_INVESTIGATION due
    to missing theta and the kernel skipped recording the
    identify_via_front_door step. Same fallback pattern as
    ``_classify_unmeasured_confounder_risk``.
    """
    description = (
        "前门识别（Pearl front-door criterion）的有效性以下列假设为前提："
        "(1) 中介集 M 阻断 X→Y 的所有有向路径；"
        "(2) 不存在未阻断的 X→M 后门路径；"
        "(3) 所有 M→Y 后门路径已被 X 阻断；"
        "(4) consistency of potential outcomes。"
        "若任一假设不成立，前门估计失效。"
    )
    triggering = next(
        (
            step for step in derivation
            if step.rule in _FRONT_DOOR_DERIVATION_RULES
            and not _step_failed(step)
        ),
        None,
    )
    if triggering is not None:
        yield DataGap(
            kind=GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.DERIVATION_STEP,
                    ref_id=triggering.step_id or triggering.rule,
                ),
            ),
        )
        return
    if _has_front_door_pattern(program, stmt):
        yield DataGap(
            kind=GapKind.FRONT_DOOR_IDENTIFICATION_ASSUMPTION_REQUIRED,
            severity=GapSeverity.INFORMATIONAL,
            description=description,
            blocks=GapBlocks.INTERPRETATION,
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.VERIFIER_CHECK,
                    ref_id="program:front_door_pattern",
                ),
            ),
        )


def _has_front_door_pattern(program, stmt) -> bool:
    """Detect front-door identification pattern from program shape:
    bidirected edge between intervention X and target Y AND at least
    one mediator M with X→M and M→Y. Used as a fallback when the
    derivation chain is empty (NEEDS_INVESTIGATION due to missing theta)."""
    if program is None or stmt is None:
        return False
    q = getattr(stmt, "query", None)
    intervention = getattr(q, "intervention", None)
    target = getattr(q, "target", None)
    if intervention is None or target is None:
        return False
    # Some queries hold ValuedAtom / Intervention with `.atom`; others hold
    # Atom directly. Fall through with getattr to handle both.
    x_atom = getattr(intervention, "atom", intervention)
    y_atom = getattr(target, "atom", target)
    x_pred = getattr(x_atom, "predicate", None)
    y_pred = getattr(y_atom, "predicate", None)
    if x_pred is None or y_pred is None:
        return False
    has_bidirected_xy = False
    children_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, BidirectedStatement):
            pair = {st.left.predicate, st.right.predicate}
            if pair == {x_pred, y_pred}:
                has_bidirected_xy = True
        if isinstance(st, CauseStatement):
            children_of.setdefault(
                st.from_atom.predicate, set()
            ).add(st.to_atom.predicate)
    if not has_bidirected_xy:
        return False
    for mediator in children_of.get(x_pred, ()):
        if mediator in (x_pred, y_pred):
            continue
        if y_pred in children_of.get(mediator, ()):
            return True
    return False


_COUNTERFACTUAL_DERIVATION_RULES: frozenset[str] = frozenset({
    "counterfactual_bounds_binary_monotone",
    "counterfactual_twin_network",
    "counterfactual_consistency",
})


def _classify_counterfactual_assumptions(
    derivation: tuple[DerivationStep, ...],
    status: ResultStatus,
    query_kind: QueryKind,
) -> Iterable[DataGap]:
    """Counterfactual identification (twin network / monotone bounds)
    rests on consistency + composition axioms (and binary + monotonicity
    when bounds are used). The user asking a counterfactual question is
    itself the trigger — the assumptions apply whether the kernel
    reached COUNTERFACTUAL_SOLVED, returned bounds, or stopped at
    NEEDS_ASSUMPTION. Without this caveat a NEEDS_ASSUMPTION counterfactual
    surfaces only as a generic 'missing assumption' gap and the
    L3 vs L2 distinction is lost in rendering."""
    triggering = next(
        (
            step for step in derivation
            if step.rule in _COUNTERFACTUAL_DERIVATION_RULES
            and not _step_failed(step)
        ),
        None,
    )
    is_counterfactual_status = status in (
        ResultStatus.COUNTERFACTUAL_SOLVED,
        ResultStatus.COUNTERFACTUAL_BOUNDED,
    )
    is_counterfactual_query = query_kind == QueryKind.COUNTERFACTUAL
    if (
        triggering is None
        and not is_counterfactual_status
        and not is_counterfactual_query
    ):
        return
    yield DataGap(
        kind=GapKind.COUNTERFACTUAL_IDENTIFICATION_ASSUMPTION_REQUIRED,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            "反事实推理的有效性以 consistency（观察值 = do(实际取值) 下的潜在结果）"
            "+ composition 公理为前提；当走 monotone bounds 时还需要二值结果"
            "+ X 对 Y 的单调性。这些假设无法从数据本身验证。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP,
                ref_id=(
                    (triggering.step_id or triggering.rule)
                    if triggering
                    else (
                        "counterfactual_status"
                        if is_counterfactual_status
                        else "counterfactual_query_kind"
                    )
                ),
            ),
        ),
    )


def _classify_bounds_not_point(bounds_result) -> Iterable[DataGap]:
    """When ``bounds_result`` is non-null the answer is a symbolic
    interval, not a point estimate. Surfaces both the method-vs-point
    distinction and the method's specific assumptions (e.g. Balke-Pearl
    needs IV1/IV2/IV3) — without these the bounds read like a point
    with confidence intervals."""
    if bounds_result is None:
        return
    method = getattr(bounds_result, "method", None)
    method_name = method.value if hasattr(method, "value") else str(method)
    uninformative = getattr(bounds_result, "width_when_uninformative", False)
    assumptions = getattr(bounds_result, "assumptions", ()) or ()
    pieces: list[str] = [
        f"答案是 `{method_name}` 给出的符号区间，不是点估计"
    ]
    if uninformative:
        pieces.append("（且区间为非信息性 [0,1] / [-1,1]，无实际辨别力）")
    pieces.append("。渲染时必须明示这是 bounds 而非具体数值")
    if assumptions:
        pieces.append(
            f"。区间的有效性以以下假设为前提：{', '.join(assumptions)}"
        )
    pieces.append("。")
    yield DataGap(
        kind=GapKind.ANSWER_IS_BOUNDS_NOT_POINT_ESTIMATE,
        severity=GapSeverity.INFORMATIONAL,
        description="".join(pieces),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="bounds_result",
            ),
        ),
    )


def _classify_graph_learned_from_data(program) -> Iterable[DataGap]:
    """When ``program.extensions.discovery_metadata`` is populated, the
    DAG (or part of it) was learned from data by a causal-discovery
    algorithm. The user must know — without disclosure they assume the
    graph came from domain knowledge.

    Reads from ``program.extensions`` rather than ``result.extensions``
    because discovery is a program-shape signal, not a per-query one.
    """
    if program is None:
        return
    program_ext = getattr(program, "extensions", None) or {}
    metadata = program_ext.get("discovery_metadata") or {}
    if not metadata:
        return
    algo = metadata.get("algorithm", "<unknown>")
    alpha = metadata.get("alpha")
    n = metadata.get("sample_size")
    pieces = [
        f"DAG 是由因果发现算法 `{algo.upper()}` 从数据中学出的，不是用"
        f"领域知识手工声明的。"
    ]
    if alpha is not None:
        pieces.append(f"显著性阈值 α = {alpha}。")
    if n is not None:
        pieces.append(f"样本量 N = {n}。")
    pieces.append(
        "结果继承算法的核心假设："
        "PC 需要忠实性 (faithfulness) + 因果充足性 (causal sufficiency)；"
        "FCI 放宽因果充足性但仍需忠实性；"
        "LiNGAM 需要线性 + 非高斯噪声。"
    )
    violations = metadata.get("assumption_violations") or ()
    if violations:
        pieces.append(
            " 检测到当前数据上算法假设的具体违反："
            + "；".join(violations)
            + "。"
        )
    yield DataGap(
        kind=GapKind.GRAPH_LEARNED_FROM_DATA,
        severity=GapSeverity.INFORMATIONAL,
        description="".join(pieces),
        blocks=GapBlocks.INTERPRETATION,
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="extensions.discovery_metadata",
            ),
        ),
    )


def _classify_unmeasured_confounder_risk(
    *,
    program,
    query_kind: QueryKind,
    stmt,
    status,
) -> Iterable[DataGap]:
    """User-provided DAG has at least one declared confounder (Z with
    Z→X and Z→Y) but no bidirected / latent-common-cause edges — the DAG
    implicitly asserts every confounder is measured. Real-world cases
    (HRT-CVD WHI 2002, vitamin D-CVD VITAL 2018, breastfeeding-IQ
    Der 2006) document large RCT-vs-observational gaps from *unmeasured*
    confounders surviving measured-covariate adjustment. Surfaced as
    INFORMATIONAL so the user is alerted *before* collecting data —
    sensitivity hooks (E-value) attach later at the numeric stage
    (Phase 8.2).

    Triggered by program-shape only (declared confounder pattern + no
    bidirected), not derivation, because the kernel does not always
    record an `identify_via_backdoor` step when status is
    NEEDS_INVESTIGATION due to missing theta.

    Suppressed when:
    - query is not effect (data needs don't apply)
    - bidirected edges declared (user already knows about latents)
    - status indicates identification failed (UNIDENTIFIABLE branches
      already surface their own gap_kind)
    - no Z with Z→X AND Z→Y in the declared edges (no confounder
      modeling — would fire on front-door / IV / mediator-only shapes
      where this advisory is unhelpful)
    """
    if program is None or stmt is None:
        return
    if query_kind != QueryKind.EFFECT:
        return
    if status not in (
        ResultStatus.STRUCTURALLY_SOLVED,
        ResultStatus.NUMERICALLY_SOLVED,
        ResultStatus.NEEDS_INVESTIGATION,
    ):
        return
    has_bidirected = any(
        isinstance(st, BidirectedStatement) for st in program.statements
    )
    if has_bidirected:
        return
    query_atom = getattr(stmt, "query", None)
    intervention = getattr(query_atom, "intervention", None)
    target = getattr(query_atom, "target", None)
    if intervention is None or target is None:
        return
    intervention_pred = intervention.atom.predicate
    target_pred = target.atom.predicate
    children_of: dict[str, set[str]] = {}
    for st in program.statements:
        if isinstance(st, CauseStatement):
            children_of.setdefault(
                st.from_atom.predicate, set()
            ).add(st.to_atom.predicate)
    has_confounder = False
    for pred, children in children_of.items():
        if pred in (intervention_pred, target_pred):
            continue
        if intervention_pred in children and target_pred in children:
            has_confounder = True
            break
    if not has_confounder:
        return
    yield DataGap(
        kind=GapKind.UNMEASURED_CONFOUNDER_RISK,
        severity=GapSeverity.INFORMATIONAL,
        description=(
            "Backdoor 识别假设你列出的 confounder 已经测全 —— DAG 里没"
            "有声明任何 bidirected / latent-common-cause 边。这是"
            " measured-covariate 调整后仍残留 unmeasured confounder 的"
            "典型场景。多个域有 well-documented RCT-vs-observational"
            "（或实验-vs-观察）反转：医学（HRT-CVD WHI 2002、"
            "vitamin D-CVD VITAL 2018）、劳动经济学（Card 1995 schooling"
            "-earnings 中的 ability bias）、教育评估（charter schools "
            "CREDO 2013 中的 parental motivation）。机制各域不同（"
            "healthy-user bias / ability bias / selection effects），"
            "但**结构教训一致**——measured 调整不够。拿到数据后跑 "
            "sensitivity analysis（E-value）量化对 unmeasured confounder"
            " 的稳健性，或在 DAG 里把怀疑的 latent 显式声明为 "
            "bidirected。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=(
            "若怀疑某 latent 共因，添加 bidirected 边；Themis 会改走 "
            "ADMG-aware（Tian / front-door / IV）识别策略并报对应的 "
            "structural gap"
        ),
        alternative_paths=(
            "数据到位后跑 E-value sensitivity analysis（Phase 8.2，对"
            " binary outcome 自动附）",
            "Triangulate with RCT / quasi-experimental data when available",
            "Hernán-Robins target trial emulation framework "
            "（per-protocol analysis with strict eligibility）",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="program:confounder_pattern:no_bidirected",
            ),
        ),
    )


def _enumerate_simple_directed_paths(
    adjacency: dict[str, list[str]],
    src: str,
    dst: str,
    *,
    max_paths: int = 32,
    max_depth: int = 12,
) -> list[tuple[str, ...]]:
    """Bounded DFS for simple directed paths src→dst. Bounds protect
    against pathological dense DAGs; real causal models are sparse so
    32×12 is comfortably above what any real query traverses.
    """
    paths: list[tuple[str, ...]] = []

    def _dfs(node: str, trail: list[str], visited: set[str]) -> None:
        if len(paths) >= max_paths:
            return
        if len(trail) > max_depth:
            return
        if node == dst:
            paths.append(tuple(trail))
            return
        for nxt in adjacency.get(node, ()):
            if nxt in visited:
                continue
            visited.add(nxt)
            trail.append(nxt)
            _dfs(nxt, trail, visited)
            trail.pop()
            visited.remove(nxt)

    if src not in adjacency:
        return paths
    _dfs(src, [src], {src})
    return paths


# ============================================ classifiers


def _classify_unidentifiable(
    derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    for step in derivation:
        # Tian Shpitser Line 5: a successful tian_hedge_witness step
        # IS the unidentifiability witness — same downstream meaning
        # as a failed unidentifiable_via_backdoor, just discovered via
        # the c-component decomposition rather than backdoor exhaustion.
        if step.rule == "tian_hedge_witness" and not _step_failed(step):
            yield DataGap(
                kind=GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET,
                severity=GapSeverity.BLOCKING,
                description=(
                    "识别失败：Tian 算法在 An(Y) 子图上找到 c-component "
                    "hedge —— X 与 Y 处于同一 c-component，说明它们之间存在"
                    "未被任何观测变量遮断的潜在共同原因 / 双向耦合，"
                    "P(Y | do(X)) 在该 ADMG 下不可从观测分布识别"
                ),
                blocks=GapBlocks.IDENTIFICATION,
                provenance=(_step_ref(step),),
                if_provided="可给出识别公式 + 后续点估计",
                alternative_paths=(
                    "测量并加入 unmeasured confounder Z，打破 hedge",
                    "在 X 上做 RCT (如可行)，旁路 hedge",
                    "找一个满足 IV 条件的工具变量",
                ),
            )
            continue
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
    structure-group request with target ``query:identify_*`` /
    ``query:effect_admg`` / ``query:counterfactual_admg``."""
    # Targets that signal "no admissible identification path on this graph";
    # all share the same downstream remediation (more variables / RCT / IV).
    _UNIDENTIFIABLE_PREFIXES = (
        "query:identify",
        "query:effect_admg",
        "query:counterfactual_admg",
    )
    for req in requests:
        if req.group != "structure":
            continue
        for item in req.items:
            target = item.target.lower()
            if "iv" in target:
                # Routes through _classify_missing_iv to keep IV-flavored
                # alternatives.
                continue
            if not any(target.startswith(p) for p in _UNIDENTIFIABLE_PREFIXES):
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
            min_n, precision = _estimate_sample_size_for_distribution(
                display, signature,
            )
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
                    min_sample_size=min_n,
                    precision_target=precision,
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
            min_n, precision = _estimate_sample_size_for_mediator(item.target)
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
                    min_sample_size=min_n,
                    precision_target=precision,
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
    """Bareinboim transport formula:

        P*(y|do(x)) = Σ_z P(y|do(x), z) · P*(z)

    Two distinct data needs that ``§T9.1`` structural identification
    leaves open — both must be filled before §T9.2 can produce a
    transport-adjusted point estimate:

    1. Target-side ``P*(z)`` — population-level marginal on Z (this gap)
    2. Source-side ``P(y|do(x), z)`` — RCT subgroup / IPD stratification
       (the second gap, often the real bottleneck since most
       meta-analyses only publish marginal effects)

    Both are emitted whenever a transport_identification block exists
    with a non-empty adjustment set."""
    block = extensions.get("transport_identification")
    if not block:
        return
    adjustment_set = block.get("adjustment_set", []) or []
    if not adjustment_set:
        return
    target_pop = block.get("target_population")
    source_pop = block.get("source_population")
    z_names = ", ".join(_atom_label(a) for a in adjustment_set)
    treatment, outcome = _transport_treatment_outcome(block)

    # Heuristic strata count: assume each adjustment-set predicate is
    # binary. Phase 12 is binary-only; revise when non-binary lands.
    n_strata = 2 ** len(adjustment_set)
    target_n, target_precision = _estimate_sample_size_for_transport_target(
        n_strata,
    )
    source_n, source_precision = _estimate_sample_size_for_transport_source(
        n_strata,
    )

    # 1. Target-side P*(Z) — population marginal.
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
            min_sample_size=target_n,
            precision_target=target_precision,
        ),
        if_provided="可给目标人群的 transport-adjusted ATE 点估计",
        alternative_paths=(
            "接受源人群 ATE 作为粗略估计（外推有效性弱）",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="s_t9_2"
            ),
        ),
    )

    # 2. Source-side P(Y|do(X), Z) — stratified conditional.
    # Often the real bottleneck since meta-analyses publish marginal
    # effects (one number) rather than per-subgroup tables.
    if treatment and outcome:
        formula_repr = (
            f"P({outcome} | do({treatment}), {z_names})"
        )
    else:
        formula_repr = "P(Y | do(X), Z)"
    yield DataGap(
        kind=GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN,
        severity=GapSeverity.BLOCKING,
        description=(
            f"转移公式还需要源人群 {source_pop or '<未命名>'} 的"
            f"分层条件分布 {formula_repr}（meta-analysis 通常只汇总"
            "成一个数，不给分层）"
        ),
        blocks=GapBlocks.TRANSPORT,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            population=source_pop,
            variables=tuple(_atom_label(a) for a in adjustment_set),
            min_sample_size=source_n,
            precision_target=source_precision,
        ),
        if_provided="可给目标人群的 transport-adjusted ATE 点估计",
        alternative_paths=(
            "找原始 RCT IPD（联系作者 / 看附件 supplementary table）",
            "找 meta-analysis 的 subgroup analysis（按 age / sex / BMI 分层）",
            "退而求其次：找单个最匹配你子群的小型 RCT，承担样本量小的代价",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.DERIVATION_STEP, ref_id="s_t9_2"
            ),
        ),
    )


def _transport_treatment_outcome(block: dict) -> tuple[str | None, str | None]:
    """Pull treatment / outcome predicate names out of a transport
    block's formula_repr like ``P*(Y | do(X)) = ...``. Returns (X, Y)
    or (None, None) if parsing fails (defensive — block schema may
    drift)."""
    formula = block.get("formula_repr", "")
    # Cheap regex-free parse: look for "P*(<outcome> | do(<treatment>)".
    try:
        head = formula.split("=", 1)[0]
        out_part = head.split("(", 1)[1]
        outcome = out_part.split("|", 1)[0].strip()
        do_part = out_part.split("do(", 1)[1]
        treatment = do_part.split(")", 1)[0].strip()
        return treatment or None, outcome or None
    except (IndexError, ValueError):
        return None, None


_DEFAULT_DOSE_RESPONSE_K = 5


def _classify_dose_response_data(
    program, stmt, derivation: tuple[DerivationStep, ...],
) -> Iterable[DataGap]:
    """Phase 13: when the user asks for a dose-response curve (NL flagged
    via program.extensions.ambiguities[kind=dose_response_query]),
    Themis itself doesn't compute curves — but emits a fully-specified
    'what data you need to fit it elsewhere' gap.

    Trigger: program-level ambiguity entry with kind=dose_response_query.
    Renderer + LLM-prompt layer pair this with 'use EconML / DoubleML
    / GAM' guidance.
    """
    if program is None or stmt is None:
        return
    ext = getattr(program, "extensions", None) or {}
    ambs = ext.get("ambiguities") or []
    triggered = any(
        isinstance(a, dict) and a.get("kind") == "dose_response_query"
        for a in ambs
    )
    if not triggered:
        return

    from ..output.sample_size import estimate_min_n_two_arm_continuous

    # Per-arm n at default Cohen's d=0.5 → estimate_min_n_two_arm_continuous
    # returns total (~150). Per-arm = total / 2 ≈ 75; rounded → 100 for
    # K-point scaling readability.
    total_two_arm, _ = estimate_min_n_two_arm_continuous()
    n_per_point = max(50, total_two_arm // 2)
    K = _DEFAULT_DOSE_RESPONSE_K
    total = K * n_per_point

    confounders = _extract_dose_response_confounders(derivation)

    # Best-effort target / intervention names for the description
    target_label = _query_target_label(stmt)
    intervention_label = _query_intervention_label(stmt)

    # iter 13 (case 005 finding): if confounders_required is empty AND the
    # user's program has no extra-variable nodes beyond X / Y, the DAG is
    # bare X→Y. This is unusual for observational dose-response work
    # (Whelton 2002 / AHA 2013 / Cornelissen 2013 all flag baseline
    # outcome + demographic covariates as standard). Append a generic
    # hint so the renderer prompts the user to confirm minimality is
    # intentional. Avoids hardcoding domain-specific covariate names.
    extra_hint = ""
    if not confounders and _program_has_no_declared_confounders(program, stmt):
        extra_hint = (
            "（注：你的 DAG 仅声明了 intervention + target 两个节点，没有"
            "任何 confounder。观察性剂量响应分析典型需要在 DAG 里至少声明"
            " baseline outcome 与关键 demographic covariates；若你确实"
            "想保持 minimal DAG（如随机化 RCT 设计），可以忽略此提示。）"
        )

    yield DataGap(
        kind=GapKind.DOSE_RESPONSE_DATA_REQUIRED,
        severity=GapSeverity.BLOCKING,
        description=(
            f"用户问的是 {intervention_label} 与 {target_label} 之间的"
            f"剂量响应关系（曲线 / 关系图）。Themis 不算曲线（请用 EconML "
            f"/ DoubleML / GAM）—— 但下面是你做这件事所需的数据规格。"
            f"{extra_hint}"
        ),
        blocks=GapBlocks.POINT_ESTIMATE,
        required_data=GapRequiredData(
            data_type=RequiredDataType.IPD,
            sampling_point_count=K,
            min_sample_size=total,
            precision_target=(
                f"K={K} 个 X 采样点 × n={n_per_point}/点 "
                f"(Cohen's d=0.5, α=0.05, power=0.80)"
            ),
            confounders_required=tuple(confounders),
            time_window="建议 baseline + 4w + 12w（视实际研究问题调整）",
            sutva_concerns=(
                "受试者之间不能讨论 / 协调干预（违反 SUTVA）",
                "若有溢出 / 同侪效应，需登记并在分析中纳入",
            ),
        ),
        if_provided=(
            "数据齐了之后，去 EconML / DoubleML / GAM 拟合曲线 —— "
            "Themis 不在 estimator 这一步参与"
        ),
        alternative_paths=(
            "退一步只看二元对比 (X=high vs X=low)：Themis 能给区间答案",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id="program:extensions.ambiguities.dose_response_query",
            ),
        ),
    )


def _classify_unattempted_layer_dispatch_conflict(
    *,
    stmt,
    extensions: dict,
) -> Iterable[DataGap]:
    """L3 case 009 finding: when a query specifies multiple identification
    layers (e.g. both ``mediator`` and ``target_population``), the kernel
    only dispatches one and silently skips the other. Without this
    disclosure the user may read the ``structurally_solved`` result and
    assume both layers were handled. Cole & Stuart 2010 + VanderWeele
    2016 §6.2 establish that mediation × transport are sequential
    operations, not a single dispatch.

    Trigger pairs (when both fields set on the query but only one
    extension populated):
    - mediator + target_population, transport_identification populated
      but mediation_decomposition missing/invalid → mediation skipped
    - mediator + target_population, mediation_decomposition populated
      but transport_identification missing → transport skipped

    Severity: IMPORTANT — the dispatched layer is structurally valid
    (not a bug to block), but silent skip violates VISION's
    honest-about-what-wasn't-done principle.
    """
    if stmt is None:
        return
    q = getattr(stmt, "query", None)
    has_mediator = getattr(q, "mediator", None) is not None
    has_target_pop = getattr(q, "target_population", None) is not None
    if not (has_mediator and has_target_pop):
        return
    ext = extensions or {}
    transport_done = bool(ext.get("transport_identification"))
    mediation_done = bool(
        (ext.get("mediation_decomposition") or {}).get("mediator_valid")
    )
    if transport_done and not mediation_done:
        attempted, skipped = "transport", "mediation"
    elif mediation_done and not transport_done:
        attempted, skipped = "mediation", "transport"
    else:
        return
    yield DataGap(
        kind=GapKind.UNATTEMPTED_LAYER_DUE_TO_DISPATCH_CONFLICT,
        severity=GapSeverity.IMPORTANT,
        description=(
            f"Query 同时设了 `mediator` 和 `target_population` 字段；"
            f"当前 dispatch 只跑了 **{attempted}**，**{skipped}** 被静默"
            f"跳过。"
            f"Cole & Stuart 2010 / VanderWeele 2016 §6.2: mediation × "
            f"transport 是 sequential operations（先在 source population"
            f"做 mediation, 再 transport 各 component 到 target），"
            f"不能在一个 query 里同时 dispatch。当前 result 只反映 "
            f"{attempted} 层；{skipped} 分析需要单独 query。"
        ),
        blocks=GapBlocks.INTERPRETATION,
        if_provided=(
            f"拆成两个 query：先在 source population 跑 {skipped} 分析，"
            f"再用结果做 {attempted}（或反过来按 Cole-Stuart 顺序）"
        ),
        alternative_paths=(
            f"如果只想要 {attempted} 结果，从 query 删除"
            f" {'`target_population`' if attempted == 'mediation' else '`mediator`'}"
            f" 字段使 dispatch 唯一",
            f"如果只想要 {skipped} 结果，从 query 删除"
            f" {'`target_population`' if skipped == 'mediation' else '`mediator`'}"
            f" 字段使 dispatch 唯一",
        ),
        provenance=(
            GapProvenanceRef(
                ref_kind=GapRefKind.VERIFIER_CHECK,
                ref_id=f"query:dispatch_conflict:{attempted}_dispatched_{skipped}_skipped",
            ),
        ),
    )


def _program_has_no_declared_confounders(program, stmt) -> bool:
    """Returns True when the program declares only the intervention and
    target predicates (no third node that could be a confounder /
    mediator / instrument). Used by the dose-response advisory to detect
    when the DAG is bare X→Y so the renderer can prompt the user to
    confirm minimality is intentional. Conservative: requires both
    intervention and target to be identifiable from stmt — if either is
    None, returns False (don't fire the hint)."""
    if program is None or stmt is None:
        return False
    q = getattr(stmt, "query", None)
    intervention = getattr(q, "intervention", None)
    target = getattr(q, "target", None)
    if intervention is None or target is None:
        return False
    x_atom = getattr(intervention, "atom", intervention)
    y_atom = getattr(target, "atom", target)
    x_pred = getattr(x_atom, "predicate", None)
    y_pred = getattr(y_atom, "predicate", None)
    if x_pred is None or y_pred is None:
        return False
    declared_predicates = {
        st.predicate for st in program.statements
        if isinstance(st, VariableDeclaration)
    }
    extras = declared_predicates - {x_pred, y_pred}
    return len(extras) == 0


def _extract_dose_response_confounders(
    derivation: tuple[DerivationStep, ...],
) -> list[str]:
    """Pull confounder predicates from the derivation's backdoor /
    front-door step. Best-effort — returns an empty list if no
    adjustment set is present (e.g. unidentifiable graph). The
    response renderer surfaces 'no confounders captured' explicitly
    rather than pretending."""
    for step in derivation:
        if "backdoor" in step.rule and not _step_failed(step):
            ctx = step.context or {}
            adj = ctx.get("adjustment_set") or ctx.get("backdoor_set")
            if isinstance(adj, (list, tuple)):
                return [str(z) for z in adj]
    return []


def _query_target_label(stmt) -> str:
    """Best-effort label for the query's outcome variable.

    Real-test caught: cause queries (with `from`/`to`) used to fall
    through to the literal string ``<target>`` because only effect
    queries' `target.atom` shape was handled. Now also reads `to` for
    cause queries and falls back to a generic phrase instead of an
    angle-bracketed placeholder a renderer would surface verbatim.
    """
    q = getattr(stmt, "query", None)
    if q is None:
        return "目标变量"
    target = getattr(q, "target", None)
    if target is not None:
        atom = getattr(target, "atom", None) or target
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # CauseQuery exposes its source/destination as ``from_atom`` /
    # ``to_atom`` (avoiding Python's ``from`` keyword); AssocQuery uses
    # left/right.
    for attr in ("to_atom", "to", "right"):
        atom = getattr(q, attr, None)
        if atom is not None:
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return "目标变量"


def _query_intervention_label(stmt) -> str:
    """Best-effort label for the query's treatment variable. See
    ``_query_target_label`` for the cause-query motivation."""
    q = getattr(stmt, "query", None)
    if q is None:
        return "干预变量"
    intv = getattr(q, "intervention", None)
    if intv is not None:
        atom = getattr(intv, "atom", None) or intv
        pred = getattr(atom, "predicate", None)
        if pred:
            return pred
    # CauseQuery exposes its source as ``from_atom``; AssocQuery uses
    # ``left``. ``from`` is a Python keyword so it never appears as an
    # attribute name on typed objects, but check it for dict-shaped
    # callers anyway.
    for attr in ("from_atom", "from_", "from", "left"):
        atom = getattr(q, attr, None)
        if atom is not None:
            pred = getattr(atom, "predicate", None)
            if pred:
                return pred
    return "干预变量"


def _classify_ambiguous_variable(
    framing_notes: tuple[FramingNote, ...],
    stmt=None,
) -> Iterable[DataGap]:
    on_query_path = _query_referenced_predicates(stmt)
    for note in framing_notes:
        # Predicates the query directly references take IMPORTANT
        # severity — their framing shapes how the answer is read,
        # so the gap belongs near the headline rather than at the end
        # as a quiet caveat. Predicates declared in the program but
        # not on the query path stay INFORMATIONAL.
        severity = (
            GapSeverity.IMPORTANT
            if note.predicate in on_query_path
            else GapSeverity.INFORMATIONAL
        )
        missing_str = ", ".join(note.missing)
        yield DataGap(
            kind=GapKind.AMBIGUOUS_VARIABLE_DEFINITION,
            severity=severity,
            description=(
                f"变量 `{note.predicate}` 缺操作化定义：{missing_str}"
            ),
            blocks=GapBlocks.INTERPRETATION,
            if_provided=(
                "变量框架化后，下游结果（点估计 / bounds）的语义才确定 —— "
                "用户能判断 'P(Y|X)' 到底说的是哪段时间窗 / 哪种测量"
            ),
            provenance=(
                GapProvenanceRef(
                    ref_kind=GapRefKind.FRAMING_NOTE, ref_id=note.predicate
                ),
            ),
        )


def _query_referenced_predicates(stmt) -> frozenset[str]:
    """Predicates the query atom references — across all query kinds.

    Returns an empty set when ``stmt`` is None or has no recoverable
    query atoms. Effect queries name intervention / target / given /
    mediator; cause queries name from_atom / to_atom; assoc queries
    name left / right.
    """
    if stmt is None:
        return frozenset()
    q = getattr(stmt, "query", None)
    if q is None:
        return frozenset()
    found: set[str] = set()

    def _add_atom(obj) -> None:
        if obj is None:
            return
        atom = getattr(obj, "atom", None) or obj
        pred = getattr(atom, "predicate", None)
        if pred:
            found.add(pred)

    # Effect / counterfactual shape: intervention.atom, target.atom, mediator,
    # given is a list of atoms (or atom wrappers).
    _add_atom(getattr(q, "intervention", None))
    _add_atom(getattr(q, "target", None))
    _add_atom(getattr(q, "mediator", None))
    given = getattr(q, "given", None)
    if given:
        for entry in given:
            _add_atom(entry)
    # Cause query: from_atom / to_atom (plus dict-shaped fallbacks).
    for attr in ("from_atom", "from_", "from", "to_atom", "to"):
        _add_atom(getattr(q, attr, None))
    # Assoc query: left / right.
    for attr in ("left", "right"):
        _add_atom(getattr(q, attr, None))
    # Counterfactual query: observed (GroundedValue), intervention
    # (Intervention wrapper), counterfactual_target (GroundedValue).
    _add_atom(getattr(q, "observed", None))
    _add_atom(getattr(q, "counterfactual_intervention", None))
    _add_atom(getattr(q, "counterfactual_target", None))
    return frozenset(found)


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


def _estimate_sample_size_for_mediator(
    target: str,
) -> tuple[int | None, str | None]:
    """Mediation NDE/NIE sample size: only fires when the rendered
    parameter target looks binary-outcome (same heuristic as
    ``_estimate_sample_size_for_distribution``)."""
    from .sample_size import (
        estimate_min_n_mediation_nde_nie,
        is_binary_outcome_distribution,
    )

    if not is_binary_outcome_distribution(target):
        return None, None
    return estimate_min_n_mediation_nde_nie()


def _estimate_sample_size_for_transport_target(
    n_strata: int,
) -> tuple[int | None, str | None]:
    """Target-population P*(Z): single-proportion per stratum."""
    from .sample_size import estimate_min_n_transport_target_marginal

    return estimate_min_n_transport_target_marginal(n_strata=n_strata)


def _estimate_sample_size_for_transport_source(
    n_strata: int,
) -> tuple[int | None, str | None]:
    """Source-population stratified P(Y|do(X), Z)."""
    from .sample_size import estimate_min_n_transport_source_conditional

    return estimate_min_n_transport_source_conditional(n_strata=n_strata)


def _estimate_sample_size_for_distribution(
    display: str, signature: str | None,
) -> tuple[int | None, str | None]:
    """Map a missing-distribution gap to (min_n, precision_target).

    Routes by outcome dtype sniffed from the rendered ``P(...)`` string:

    - Binary outcome (``P(y=true|...)``):
      conditional → two-arm Cohen's h, marginal/joint → single proportion
    - Continuous outcome (``P(systolic_bp=140|...)`` or marginal numeric):
      conditional → two-arm Cohen's d, marginal → leave None (single
      mean estimation needs σ that we don't have)
    - Unknown shape: ``(None, None)`` — better silent than wrong.
    """
    from .sample_size import (
        estimate_min_n_two_arm_continuous,
        is_continuous_outcome_distribution,
    )

    if is_binary_outcome_distribution(display):
        if signature == "conditional":
            return estimate_min_n_two_arm_binary()
        return estimate_min_n_single_proportion()
    if is_continuous_outcome_distribution(display):
        if signature == "conditional":
            return estimate_min_n_two_arm_continuous()
        # marginal continuous: we don't have σ, can't run mean precision
        return None, None
    return None, None


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
    """Short imperative tail rendered after the gap section.

    Each step is an action ('补 X' / '或：换识别路径'), not a restatement
    of gap.description or gap.if_provided — those live inside the gap
    object and are already surfaced by the renderer within each gap's
    bullet. Concatenating description + if_provided here produced a
    wall of text that just repeated the gap section verbatim.
    """
    steps: list[str] = []
    for gap in gaps:
        if gap.severity == GapSeverity.INFORMATIONAL:
            continue
        if gap.if_provided:
            steps.append(f"补 {_short_label_for(gap)}")
        if gap.alternative_paths:
            steps.append(f"或：{gap.alternative_paths[0]}")
    return steps


def _short_label_for(gap: DataGap) -> str:
    """A noun-phrase label for the actionable_next_steps line. The full
    ``description`` is a complete sentence — concatenating it into "补 X
    → Y" produces a wall of text. Each gap_kind gets a concise label
    that names *what is missing* in 1-3 nouns."""
    rd = gap.required_data
    if gap.kind == GapKind.TRANSPORT_TARGET_DISTRIBUTION_UNKNOWN:
        if rd and rd.variables:
            vars_str = ", ".join(rd.variables)
            pop = rd.population or "目标人群"
            return f"P*({vars_str}) on {pop}"
        return "目标人群上的 P*(Z)"
    if gap.kind == GapKind.TRANSPORT_SOURCE_CONDITIONAL_UNKNOWN:
        if rd and rd.variables:
            vars_str = ", ".join(rd.variables)
            pop = rd.population or "源人群"
            return f"P(Y|do(X), {vars_str}) 在 {pop} 上的分层条件分布"
        return "源人群上的分层条件分布 P(Y|do(X), Z)"
    if gap.kind == GapKind.MISSING_DISTRIBUTION:
        # gap.description is already "缺概率分布 P(...)" — strip the prefix.
        prefix = "缺概率分布 "
        if gap.description.startswith(prefix):
            return gap.description[len(prefix):]
        return gap.description
    if gap.kind == GapKind.MISSING_POPULATION_DISTRIBUTION:
        return "目标人群分布"
    if gap.kind == GapKind.MISSING_ASSUMPTION:
        return "识别假设"
    if gap.kind == GapKind.MISSING_IV_CANDIDATE:
        return "有效的工具变量"
    if gap.kind == GapKind.MISSING_MEDIATOR_DATA:
        if rd and rd.variables:
            return f"中介 {rd.variables[0]} 的相关分布"
        return "中介相关分布"
    if gap.kind == GapKind.UNIDENTIFIABLE_NO_ADMISSIBLE_SET:
        return "可识别的调整集 / 替代识别路径"
    if gap.kind == GapKind.AMBIGUOUS_VARIABLE_DEFINITION:
        # Provenance carries the predicate name (a FRAMING_NOTE ref).
        for prov in gap.provenance or ():
            if prov.ref_kind == GapRefKind.FRAMING_NOTE and prov.ref_id:
                return f"`{prov.ref_id}` 的操作化定义"
        return "变量的操作化定义"
    return gap.description
