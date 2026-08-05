"""Produce human-readable explanations for a QueryResult.

The explainer reads only data that is already present in the
QueryResult — supporting_paths, formula, missing_information,
investigation_requests. It MUST NOT re-run reasoning.

v0.1 emits Chinese text by default (see 因果图规则总览.md for the
vocabulary: "开放路径", "后门", "调整集", etc.).

Formatting style is intentionally plain: no emoji, no decorative
headers, just short declarative sentences.
"""
from __future__ import annotations

from .. import blocks, questions, risk_provenance
from ..runtime import formula_builder
from ..types import (
    ConstantExpr,
    CounterfactualConjunctionQuery,
    EffectQuery,
    InvestigationAction,
    Priority,
    ProbabilityQuery,
    ProbabilityRefExpr,
    QueryResult,
    ResultStatus,
    SumExpr,
    ValuedAtom,
)


def _explain_cause_zh(result: QueryResult, stmt=None) -> str:
    sr = result.structural_result
    if sr is None:
        return "结构层未产生结果。"
    if sr.value:
        if sr.supporting_paths:
            path = " -> ".join(sr.supporting_paths[0])
            extra = ""
            if len(sr.supporting_paths) > 1:
                extra = f"（共 {len(sr.supporting_paths)} 条有向路径）"
            return f"存在从源到目标的有向路径：{path}。源可能因果影响目标{extra}。"
        return "存在从源到目标的有向路径。源可能因果影响目标。"
    return "不存在从源到目标的有向路径。源在结构上不因果影响目标。"


def _explain_assoc_zh(result: QueryResult, stmt=None) -> str:
    sr = result.structural_result
    if sr is None:
        return "结构层未产生结果。"
    if sr.value:
        if sr.supporting_paths:
            first = " - ".join(sr.supporting_paths[0])
            if len(sr.supporting_paths) > 1:
                extra = f"（共 {len(sr.supporting_paths)} 条开放路径）"
            else:
                extra = ""
            return (
                f"在给定条件集下，存在开放路径：{first}。两者在当前条件下可能相关{extra}。"
            )
        return "在给定条件集下存在至少一条开放路径。两者在当前条件下可能相关。"
    return "在给定条件集下所有路径均被堵住。两者在当前条件下 d-分离。"


def _atom_label(atom) -> str:
    args = ",".join(a.name for a in atom.args)
    base = f"{atom.predicate}({args})"
    if getattr(atom, "time_index", None) is None:
        return base
    t = atom.time_index.value
    return f"{base}@t" if t == 0 else f"{base}@t{t:+d}"


def _format_atom_set(atoms) -> str:
    """Render a sequence of atoms as ``{a(x), b(x), ...}``."""
    labels = [_atom_label(a) for a in atoms]
    return "{" + ", ".join(labels) + "}"


def _labeled_value(va: ValuedAtom) -> str:
    """Render a ValuedAtom as ``predicate(args)=value`` for display."""
    return f"{_atom_label(va.atom)}={va.value}"


def _format_number(x: float) -> str:
    """Compact numeric formatting: avoid trailing zeros from ``.3f``."""
    return f"{x:.4g}"


def _describe_adjustment(formula) -> str:
    """Short sentence describing how the formula identifies its target."""
    if formula is None:
        return ""
    adj = formula_builder.adjustment_atoms(formula)
    if adj:
        size_note = f"（共 {len(adj)} 个调整变量）" if len(adj) > 1 else ""
        return (
            f"识别通过后门调整集 {_format_atom_set(adj)}"
            f"{size_note}。"
        )
    if isinstance(formula, ProbabilityRefExpr):
        return "无需后门调整（观察分布直接给出答案）。"
    return ""


_ACTION_PHRASE: dict[InvestigationAction, str] = {
    InvestigationAction.VALIDATE_PARAMETER:   "提供该参数",
    InvestigationAction.COLLECT_OBSERVATION:  "补采观测",
    InvestigationAction.INCREASE_SAMPLE:      "扩大样本",
    InvestigationAction.RUN_EXPERIMENT:       "运行实验",
    InvestigationAction.DEFINE_ASSUMPTION:    "补充该假设",
}

_PRIORITY_PHRASE: dict[Priority, str] = {
    Priority.HIGH:   "高",
    Priority.MEDIUM: "中",
    Priority.LOW:    "低",
}


def _refused_zh(subject: str, result: QueryResult) -> str:
    """Why no number came out, in the words the refusal already chose.

    A status alone says a query was turned away; the reason says which of
    several very different things happened — an undefined quantity, a
    contradiction between the caller's own inputs, a case not built. That
    reason is on the envelope, so the only thing to decide here is
    whether to say it.
    """
    reason = (result.estimator_failure or {}).get("reason")
    return f"{subject}没有给出答案：{reason}" if reason else (
        f"{subject}超出当前可解范围。"
    )


def _describe_needs_investigation(result: QueryResult) -> str:
    """Render the '缺什么 / 为什么缺 / 下一步做什么' envelope.

    Pulls reasons out of ``missing_information`` and aligns each item
    with the matching ``InvestigationRequest`` (by target = missing
    item name, which is how ``investigation_pusher`` builds them).

    Returns empty string when there are no missing items so callers
    can concatenate unconditionally.
    """
    if not result.missing_information:
        return ""

    reqs_by_target: dict[str, "InvestigationAction"] = {}
    reqs_priority: dict[str, "Priority"] = {}
    for req in result.investigation_requests:
        reqs_by_target[req.target] = req.action
        reqs_priority[req.target] = req.priority

    sentences: list[str] = []
    for m in result.missing_information:
        parts = [f"缺：{m.name}"]
        if m.reason:
            parts.append(f"（原因：{m.reason}）")
        action = reqs_by_target.get(m.name)
        if action is not None:
            action_label = _ACTION_PHRASE.get(action, action.value)
            prio = reqs_priority.get(m.name)
            prio_label = _PRIORITY_PHRASE.get(prio, prio.value if prio else "")
            parts.append(
                f"；下一步 {action_label}（优先级 {prio_label}）"
            )
        sentences.append("".join(parts) + "。")
    return " ".join(sentences)


def _explain_identify_zh(result: QueryResult, stmt=None) -> str:
    sr = result.structural_result
    if sr is None:
        return "识别结果缺失。"
    if sr.value is False:
        return "在当前结构下该干预量不可识别。"
    if sr.value is True:
        if result.formula is None:
            return "该干预量可识别，但本轮未返回具体公式。"

        # Walk the formula to pick up every SumExpr.over, not just
        # the outermost. Multi-var adjustment used to degrade here.
        adj = formula_builder.adjustment_atoms(result.formula)
        if adj:
            size_note = f"（共 {len(adj)} 个调整变量）" if len(adj) > 1 else ""
            return (
                f"该干预量可通过后门调整识别，"
                f"调整集 {_format_atom_set(adj)} 足以堵住所有后门路径"
                f"{size_note}。"
            )

        # No SumExpr in the formula ⇒ empty adjustment; the observation
        # distribution itself identifies the quantity.
        if isinstance(result.formula, ProbabilityRefExpr):
            return "该干预量无需后门调整即可识别，观察分布本身给出答案。"
        return "该干预量可识别。"
    return "识别结果未分类。"


def _explain_counterfactual_conjunction_zh(result: QueryResult, stmt=None) -> str:
    """General counterfactual identification (Shpitser-Pearl ID*/IDC*)."""
    conditional = bool(
        stmt is not None
        and isinstance(stmt.query, CounterfactualConjunctionQuery)
        and stmt.query.condition
    )
    quantity = "P(γ|δ)" if conditional else "P(γ)"
    algo = "IDC*" if conditional else "ID*"
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        if any(
            m.name == "query:conditioning_event_probability_zero"
            for m in result.missing_information
        ):
            base = (
                f"该条件反事实 {quantity} 未定义：条件事件 δ 的概率为 0"
                "（效力违反或不同世界断言冲突），无法作为条件。"
            )
        else:
            base = (
                f"该反事实合取 {quantity} 在当前结构下不可识别"
                f"（{algo} 报出 w-graph / 下标冲突见证，观察数据无法给出估计式）。"
            )
        gap = _describe_needs_investigation(result)
        return f"{base}{gap}" if gap else base
    sr = result.structural_result
    if sr is not None and sr.value is True:
        if isinstance(result.formula, ConstantExpr) and result.formula.value == 0.0:
            return (
                f"该反事实合取的分子自相矛盾（不同世界的断言冲突），"
                f"因此 {quantity}=0。"
            )
        return (
            f"该反事实合取 {quantity} 可识别："
            f"{algo} 已把它约化为观察分布上的估计式。"
        )
    return "反事实合取查询：结果未分类。"


def _explain_proximal_effect_zh(result: QueryResult, stmt=None) -> str:
    """Proximal causal inference (Miao-Geng-Tchetgen 2018 model (f))."""
    from ..types import ProximalEffectQuery

    q = (
        stmt.query
        if stmt is not None and isinstance(stmt.query, ProximalEffectQuery)
        else None
    )
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        base = (
            "该效应 P(Y|do(X)) 在未观测混杂下近端不可识别："
            "所声明的两个 proxy 不构成 Miao model (f) 结构"
            "（治疗侧 proxy 泄漏到结局、结局侧 proxy 泄漏到治疗，"
            "或 U 之外还有未阻断的混杂）。"
        )
        gap = _describe_needs_investigation(result)
        return f"{base}{gap}" if gap else base
    sr = result.structural_result
    if sr is not None and sr.value is True:
        if q is not None:
            z, w, u = (
                q.treatment_proxy.predicate,
                q.outcome_proxy.predicate,
                q.latent.predicate,
            )
            return (
                f"该效应 P(Y|do(X)) 在未观测混杂 {u} 下近端可识别："
                f"借治疗侧 proxy {z} 与结局侧 proxy {w}（Miao model f），"
                f"可由 P(y|Z,x)·P(W|Z,x)⁻¹·P(W) 反演 Z×W 测量通道从数据恢复 "
                f"ATE（需 proxy 对 {u} 足够相关，rank 条件在数据上核验）。"
            )
        return "该效应 P(Y|do(X)) 在未观测混杂下近端可识别（Miao model f）。"
    return "近端效应查询：结果未分类。"


def _explain_effect_zh(result: QueryResult, stmt=None) -> str:
    """Render an effect query result.

    Needs the originating stmt to quote the target value, intervention
    and conditioning context the user actually asked about — those are
    not recoverable from result.formula alone (e.g. the intervention
    value is embedded inside a ValuedAtom nested under probability_ref,
    but extracting it from the structured query is cleaner).
    """
    if stmt is not None and isinstance(stmt.query, EffectQuery):
        q = stmt.query
        target_desc = _labeled_value(q.target)
        intervention_desc = (
            f"do({_atom_label(q.intervention.atom)}={q.intervention.value})"
        )
        given_desc = (
            "，条件 " + ", ".join(_labeled_value(g) for g in q.given)
            if q.given else ""
        )
        quantity = f"P({target_desc} | {intervention_desc}{given_desc})"
    else:
        quantity = "该干预量"

    if result.status is ResultStatus.NUMERICALLY_SOLVED and result.numeric_result is not None:
        return (
            f"{quantity} = {_format_number(result.numeric_result.value)}。"
            f"{_describe_adjustment(result.formula)}"
        )

    sr = result.structural_result
    if sr is not None and sr.value is False:
        return f"{quantity} 在当前结构下不可识别（无有效后门调整集）。"

    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        pieces = [f"{quantity} 可识别。"]
        adj = _describe_adjustment(result.formula)
        if adj:
            pieces.append(adj)
        gap = _describe_needs_investigation(result)
        if gap:
            pieces.append(gap)
        return "".join(pieces)

    return f"{quantity}：结果未分类。"


def _explain_probability_zh(result: QueryResult, stmt=None) -> str:
    """Render a plain probability query result."""
    if stmt is not None and isinstance(stmt.query, ProbabilityQuery):
        q = stmt.query
        target_desc = _labeled_value(q.target)
        given_desc = (
            " | " + ", ".join(_labeled_value(g) for g in q.given)
            if q.given else ""
        )
        quantity = f"P({target_desc}{given_desc})"
    else:
        quantity = "该条件概率"

    if result.status is ResultStatus.NUMERICALLY_SOLVED and result.numeric_result is not None:
        return f"{quantity} = {_format_number(result.numeric_result.value)}。"

    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        if gap:
            return f"{quantity} 暂无法计算。{gap}"
        return f"{quantity} 暂无法计算。"

    return f"{quantity}：结果未分类。"


def _explain_counterfactual_cell_data_zh(cell: dict) -> str:
    """Render the DATA-recovered cell. Reads ``extensions.counterfactual_cell``
    (attached by the estimation dispatch); re-runs nothing."""
    prov = risk_provenance.describe(
        cell.get("interventional_risk_provenance")
    )
    point = cell.get("point")
    if point is not None:
        head = f"反事实单格 = {_format_number(point)}（点识别）"
    else:
        head = (
            f"反事实单格 ∈ [{_format_number(cell.get('lower'))}, "
            f"{_format_number(cell.get('upper'))}]（区间，非点）"
        )
    ci_lo, ci_hi = cell.get("ci_lower"), cell.get("ci_upper")
    if ci_lo is not None and ci_hi is not None:
        band = "置信区间" if point is not None else "区间自身的抽样带"
        head += f"，{band} [{_format_number(ci_lo)}, {_format_number(ci_hi)}]"
    refuted = cell.get("bootstrap_draws_infeasible") or 0
    used = cell.get("bootstrap_draws_used") or 0
    tail = ""
    if refuted and (used + refuted):
        share = refuted / (used + refuted)
        tail = (
            f"注意：{_format_number(share * 100)}% 的重抽样在所声明的单调性下"
            f"无解，说明这条假设离被数据推翻很近。"
        )
    return f"{head}（从数据算得，{prov}）。{tail}"


def _explain_counterfactual_zh(result: QueryResult, stmt=None) -> str:
    cell = (result.extensions or {}).get(blocks.COUNTERFACTUAL_CELL)
    if cell:
        return _explain_counterfactual_cell_data_zh(cell)
    if result.status is ResultStatus.COUNTERFACTUAL_SOLVED and result.numeric_result is not None:
        return (
            "反事实查询已得到点值结果。"
            f"P(counterfactual target) = {_format_number(result.numeric_result.value)}。"
        )
    if (
        result.status is ResultStatus.COUNTERFACTUAL_BOUNDED
        and result.numeric_result is not None
        and result.numeric_result.interval is not None
    ):
        interval = result.numeric_result.interval
        return (
            "反事实查询当前得到界而非点值。"
            f"区间为 [{_format_number(interval.low)}, {_format_number(interval.high)}]。"
        )
    if result.status is ResultStatus.OUTSIDE_LANGUAGE:
        return _refused_zh("反事实查询", result)
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        if gap:
            return f"反事实查询暂时还算不出 bounds。{gap}"
        return "反事实查询暂时还算不出 bounds。"
    if result.status is ResultStatus.NEEDS_ASSUMPTION:
        gap = _describe_needs_investigation(result)
        if gap:
            return f"反事实查询还缺少必要假设。{gap}"
        return "反事实查询还缺少必要假设。"
    return "反事实查询：结果未分类。"


def _explain_causation_zh(result: QueryResult, stmt=None) -> str:
    """Render PN / PS / PNS (probabilities of causation, Tian-Pearl 2000).

    Reads the ``extensions.causation`` envelope the scheduler attached;
    re-runs no reasoning. PN (necessity / 归因) is the headline; PS
    (sufficiency) and PNS round out the picture.
    """
    if result.status is ResultStatus.OUTSIDE_LANGUAGE:
        return _refused_zh("因果概率查询", result)
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        base = "因果概率（PN/PS/PNS）暂时算不出。"
        return f"{base}{gap}" if gap else base

    c = (result.extensions or {}).get(blocks.CAUSATION)
    if not c:
        return "因果概率查询：结果未分类。"

    def _q(block: dict) -> str:
        if block.get("point") is not None:
            return f"{_format_number(block['point'])}（点识别）"
        return (
            f"[{_format_number(block['lower'])}, "
            f"{_format_number(block['upper'])}]（界）"
        )

    # A lookup rather than a branch: this block reaches here from theta and
    # from data, and an ``if/else`` over a two-value domain answered the
    # data path's licences with the other path's sentence.
    prov = risk_provenance.describe(c.get("interventional_risk_provenance"))
    return (
        f"因果归因概率（Tian-Pearl 2000，{prov}）："
        f"必要性 PN = {_q(c['pn'])}；"
        f"充分性 PS = {_q(c['ps'])}；"
        f"必要且充分 PNS = {_q(c['pns'])}。"
    )


def _explain_scm_counterfactual_zh(result: QueryResult, stmt=None) -> str:
    """Render a deterministic linear-SCM counterfactual point (Pearl
    Primer §4.2). Reads ``extensions.scm_counterfactual``; re-runs nothing."""
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        base = "线性 SCM 反事实点暂时算不出（结构方程或单元观测不全）。"
        return f"{base}{gap}" if gap else base
    sc = (result.extensions or {}).get(blocks.SCM_COUNTERFACTUAL)
    if not sc:
        return "线性 SCM 反事实查询：结果未分类。"
    iv = sc.get("intervention", {})
    return (
        f"在已知线性结构方程下,对这个单元做 do({iv.get('variable')}="
        f"{_format_number(iv.get('value'))}),"
        f"{sc.get('target')} 的反事实值 = {_format_number(sc.get('target_value'))}"
        f"(Pearl 三步法:溯因-干预-预测)。"
    )


def _with_confidence_suffix(text: str, result: QueryResult) -> str:
    """Append a confidence clause when the result carries one.

    Surfaces the v0.2 composite min rule: the single number is the
    weakest evidence level among the inputs the collection rules
    reached. Structural queries currently carry None so this suffix
    only shows up on numerically-solved effect / probability today,
    but the helper is kind-agnostic to stay correct if future slices
    start attaching confidence to other paths.
    """
    if result.confidence is None:
        return text
    rendered = _format_number(result.confidence)
    return f"{text}综合可信度 {rendered}（最弱证据水平，按 min 规则聚合）。"


def _with_framing_suffix(text: str, result: QueryResult) -> str:
    """Slice A0: append advisory 问题定义 clause for underspecified
    predicates. Advisory only — the numeric/structural verdict is
    already stated in ``text``; this just tells the reader which
    variables lack metadata that would make the question operational.
    """
    if not result.framing_notes:
        return text
    parts: list[str] = []
    for note in result.framing_notes:
        parts.append(f"{note.predicate} 缺 {', '.join(note.missing)}")
    return f"{text}问题定义：{'；'.join(parts)}。"


# One explainer per kind of question, bound to the vocabulary rather than
# chained. The chain that was here covered all ten and raised on anything
# else, which made this the one surface that was complete — the report's
# answer line had no branch at all, the report's question line tested for a
# string no query kind has, and the web answered seven kinds with a
# fallback. Binding moves this surface's guarantee from "the eleventh
# branch raises when a result arrives" to "a query kind without an
# explainer fails at import".
_EXPLAINERS = questions.bind({
    questions.CAUSE: _explain_cause_zh,
    questions.ASSOC: _explain_assoc_zh,
    questions.IDENTIFY: _explain_identify_zh,
    questions.EFFECT: _explain_effect_zh,
    questions.PROBABILITY: _explain_probability_zh,
    questions.COUNTERFACTUAL: _explain_counterfactual_zh,
    questions.CAUSATION: _explain_causation_zh,
    questions.SCM_COUNTERFACTUAL: _explain_scm_counterfactual_zh,
    questions.COUNTERFACTUAL_CONJUNCTION: _explain_counterfactual_conjunction_zh,
    questions.PROXIMAL_EFFECT: _explain_proximal_effect_zh,
})


def explain(
    result: QueryResult,
    lang: str = "zh",
    *,
    stmt=None,
) -> str:
    """Render a QueryResult as a plain-text explanation.

    Positional args are stable for backward compatibility. The
    keyword-only ``stmt`` lets callers hand in the originating
    ``QueryStatement`` so ``effect`` / ``probability`` explanations
    can quote the exact target value / intervention / conditioning
    the user asked about. The explainer still MUST NOT re-run any
    reasoning — ``stmt`` is used for display only.

    Slice 9.x-D: if ``result.confidence`` is non-None the text
    gains a trailing clause naming the composite value, so users
    reading the explanation don't miss what is otherwise only in
    the structured payload.
    """
    if lang != "zh":
        raise NotImplementedError(f"language '{lang}' not supported in v0.1")
    text = _EXPLAINERS[questions.reading_of(result.query_kind.value)](result, stmt)
    text = _with_confidence_suffix(text, result)
    text = _with_framing_suffix(text, result)
    return text
