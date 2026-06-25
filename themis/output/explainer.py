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

from ..runtime import formula_builder
from ..types import (
    EffectQuery,
    InvestigationAction,
    Priority,
    ProbabilityQuery,
    ProbabilityRefExpr,
    QueryKind,
    QueryResult,
    ResultStatus,
    SumExpr,
    ValuedAtom,
)


def _explain_cause_zh(result: QueryResult) -> str:
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


def _explain_assoc_zh(result: QueryResult) -> str:
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


def _explain_identify_zh(result: QueryResult) -> str:
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


def _explain_effect_zh(result: QueryResult, stmt) -> str:
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


def _explain_probability_zh(result: QueryResult, stmt) -> str:
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


def _explain_counterfactual_zh(result: QueryResult) -> str:
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
        return "反事实查询已进入语法层，但当前仍未进入求解层。"
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


def _explain_causation_zh(result: QueryResult) -> str:
    """Render PN / PS / PNS (probabilities of causation, Tian-Pearl 2000).

    Reads the ``extensions.causation`` envelope the scheduler attached;
    re-runs no reasoning. PN (necessity / 归因) is the headline; PS
    (sufficiency) and PNS round out the picture.
    """
    if result.status is ResultStatus.OUTSIDE_LANGUAGE:
        err = (result.extensions or {}).get("causation_error")
        return f"因果概率查询超出当前语言范围：{err}" if err else (
            "因果概率查询超出当前语言范围。"
        )
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        base = "因果概率（PN/PS/PNS）暂时算不出。"
        return f"{base}{gap}" if gap else base

    c = (result.extensions or {}).get("causation")
    if not c:
        return "因果概率查询：结果未分类。"

    def _q(block: dict) -> str:
        if "point" in block:
            return f"{_format_number(block['point'])}（点识别）"
        return (
            f"[{_format_number(block['lower'])}, "
            f"{_format_number(block['upper'])}]（界）"
        )

    prov = (
        "干预风险由识别推导得到"
        if c.get("interventional_risk_provenance") == "derived_identification"
        else "干预风险由随机实验数据直接给出"
    )
    return (
        f"因果归因概率（Tian-Pearl 2000，{prov}）："
        f"必要性 PN = {_q(c['pn'])}；"
        f"充分性 PS = {_q(c['ps'])}；"
        f"必要且充分 PNS = {_q(c['pns'])}。"
    )


def _explain_scm_counterfactual_zh(result: QueryResult) -> str:
    """Render a deterministic linear-SCM counterfactual point (Pearl
    Primer §4.2). Reads ``extensions.scm_counterfactual``; re-runs nothing."""
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result)
        base = "线性 SCM 反事实点暂时算不出（结构方程或单元观测不全）。"
        return f"{base}{gap}" if gap else base
    sc = (result.extensions or {}).get("scm_counterfactual")
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
    if result.query_kind == QueryKind.CAUSE:
        text = _explain_cause_zh(result)
    elif result.query_kind == QueryKind.ASSOC:
        text = _explain_assoc_zh(result)
    elif result.query_kind == QueryKind.IDENTIFY:
        text = _explain_identify_zh(result)
    elif result.query_kind == QueryKind.EFFECT:
        text = _explain_effect_zh(result, stmt)
    elif result.query_kind == QueryKind.PROBABILITY:
        text = _explain_probability_zh(result, stmt)
    elif result.query_kind == QueryKind.COUNTERFACTUAL:
        text = _explain_counterfactual_zh(result)
    elif result.query_kind == QueryKind.CAUSATION:
        text = _explain_causation_zh(result)
    elif result.query_kind == QueryKind.SCM_COUNTERFACTUAL:
        text = _explain_scm_counterfactual_zh(result)
    else:
        raise NotImplementedError(
            f"explainer for {result.query_kind.value} not implemented yet"
        )
    text = _with_confidence_suffix(text, result)
    text = _with_framing_suffix(text, result)
    return text
