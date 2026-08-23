"""Produce human-readable explanations for a QueryResult.

The explainer reads only data that is already present in the
QueryResult — supporting_paths, formula, missing_information,
investigation_requests. It MUST NOT re-run reasoning.

Every sentence here is a :class:`~themis.language.Words` filled at the
moment it is written, and ``lang`` reaches it from :func:`explain`. It
used to be spelled into the ten producers' NAMES (``_explain_effect_zh``)
— which is the shape :mod:`themis.language` was built to remove: a name
cannot take an argument, so ``explain(result, lang)`` had nothing but a
table of one-language functions to hand its argument to.

Formatting style is intentionally plain: no emoji, no decorative
headers, just short declarative sentences.
"""
from __future__ import annotations

from .. import blocks, intervals, questions, risk_provenance
from . import envelope_glossary
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
    ValuedAtom,
)
from .. import gaps
from .. import language
from .. import refusals

#: What separates two clauses of one sentence, and two items of one list.
#: Punctuation belongs to the language of the sentence it lands in.

_NO_STRUCTURAL_RESULT: language.Words = {
    "zh": "结构层未产生结果。",
    "en": "the structural layer produced no result.",
}
_CAUSE_PATH_SHOWN: language.Words = {
    "zh": "存在从源到目标的有向路径：{path}。源可能因果影响目标{extra}。",
    "en": "there is a directed path from the source to the target: {path}. "
          "The source may causally affect the target{extra}.",
}
_CAUSE_MORE_PATHS: language.Words = {
    "zh": "（共 {count} 条有向路径）",
    "en": " ({count} directed paths in all)",
}
_CAUSE_PATH_EXISTS: language.Words = {
    "zh": "存在从源到目标的有向路径。源可能因果影响目标。",
    "en": "there is a directed path from the source to the target. The "
          "source may causally affect the target.",
}
_CAUSE_NO_PATH: language.Words = {
    "zh": "不存在从源到目标的有向路径。源在结构上不因果影响目标。",
    "en": "there is no directed path from the source to the target. "
          "Structurally, the source does not causally affect the target.",
}


def _explain_cause(result: QueryResult, stmt=None, *,
                   lang: language.Lang | str) -> str:
    sr = result.structural_result
    if sr is None:
        return language.fill(_NO_STRUCTURAL_RESULT, lang)
    if sr.value:
        if sr.supporting_paths:
            path = " -> ".join(sr.supporting_paths[0])
            extra = ""
            if len(sr.supporting_paths) > 1:
                extra = language.fill(_CAUSE_MORE_PATHS, lang,
                                      count=len(sr.supporting_paths))
            return language.fill(_CAUSE_PATH_SHOWN, lang,
                                 path=path, extra=extra)
        return language.fill(_CAUSE_PATH_EXISTS, lang)
    return language.fill(_CAUSE_NO_PATH, lang)


_ASSOC_PATH_SHOWN: language.Words = {
    "zh": "在给定条件集下，存在开放路径：{path}。两者在当前条件下可能相关{extra}。",
    "en": "under the conditioning set given, an open path exists: {path}. "
          "The two may be associated under those conditions{extra}.",
}
_ASSOC_MORE_PATHS: language.Words = {
    "zh": "（共 {count} 条开放路径）",
    "en": " ({count} open paths in all)",
}
_ASSOC_PATH_EXISTS: language.Words = {
    "zh": "在给定条件集下存在至少一条开放路径。两者在当前条件下可能相关。",
    "en": "under the conditioning set given, at least one open path exists. "
          "The two may be associated under those conditions.",
}
_ASSOC_D_SEPARATED: language.Words = {
    "zh": "在给定条件集下所有路径均被堵住。两者在当前条件下 d-分离。",
    "en": "under the conditioning set given, every path is blocked. The two "
          "are d-separated under those conditions.",
}


def _explain_assoc(result: QueryResult, stmt=None, *,
                   lang: language.Lang | str) -> str:
    sr = result.structural_result
    if sr is None:
        return language.fill(_NO_STRUCTURAL_RESULT, lang)
    if sr.value:
        if sr.supporting_paths:
            first = " - ".join(sr.supporting_paths[0])
            if len(sr.supporting_paths) > 1:
                extra = language.fill(_ASSOC_MORE_PATHS, lang,
                                      count=len(sr.supporting_paths))
            else:
                extra = ""
            return language.fill(_ASSOC_PATH_SHOWN, lang,
                                 path=first, extra=extra)
        return language.fill(_ASSOC_PATH_EXISTS, lang)
    return language.fill(_ASSOC_D_SEPARATED, lang)


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


_ADJUSTED_BY: language.Words = {
    "zh": "识别通过后门调整集 {set}{size}。",
    "en": "identified by back-door adjustment on {set}{size}.",
}
_ADJUSTMENT_SIZE: language.Words = {
    "zh": "（共 {count} 个调整变量）",
    "en": " ({count} adjustment variables)",
}
_NO_ADJUSTMENT_NEEDED: language.Words = {
    "zh": "无需后门调整（观察分布直接给出答案）。",
    "en": "no back-door adjustment is needed (the observational "
          "distribution answers it directly).",
}


def _describe_adjustment(formula, *, lang: language.Lang | str) -> str:
    """Short sentence describing how the formula identifies its target."""
    if formula is None:
        return ""
    adj = formula_builder.adjustment_atoms(formula)
    if adj:
        size_note = (language.fill(_ADJUSTMENT_SIZE, lang, count=len(adj))
                     if len(adj) > 1 else "")
        return language.fill(_ADJUSTED_BY, lang,
                             set=_format_atom_set(adj), size=size_note)
    if isinstance(formula, ProbabilityRefExpr):
        return language.fill(_NO_ADJUSTMENT_NEEDED, lang)
    return ""


# Six, because the vocabulary is six. ``DEFINE_VARIABLE`` arrived with the
# framing channel and never got a phrase, so the one action a reader could
# act on without any new data reached them as ``define_variable`` — the
# fallback beside the lookup hands the identifier back.
_ACTION_PHRASE: dict[str, language.Words] = {
    InvestigationAction.VALIDATE_PARAMETER:   {"zh": "提供该参数",
                                               "en": "supply that parameter"},
    InvestigationAction.COLLECT_OBSERVATION:  {"zh": "补采观测",
                                               "en": "collect the observation"},
    InvestigationAction.INCREASE_SAMPLE:      {"zh": "扩大样本",
                                               "en": "enlarge the sample"},
    InvestigationAction.RUN_EXPERIMENT:       {"zh": "运行实验",
                                               "en": "run the experiment"},
    InvestigationAction.DEFINE_ASSUMPTION:    {"zh": "补充该假设",
                                               "en": "state that assumption"},
    InvestigationAction.DEFINE_VARIABLE:      {"zh": "把这个变量定义清楚",
                                               "en": "define this variable "
                                                     "properly"},
}

_PRIORITY_PHRASE: dict[str, language.Words] = {
    Priority.HIGH:   {"zh": "高", "en": "high"},
    Priority.MEDIUM: {"zh": "中", "en": "medium"},
    Priority.LOW:    {"zh": "低", "en": "low"},
}

_REFUSED_WITH_REASON: language.Words = {
    "zh": "{subject}没有给出答案：{reason}",
    "en": "{subject} produced no answer: {reason}",
}
_REFUSED_OUT_OF_RANGE: language.Words = {
    "zh": "{subject}超出当前可解范围。",
    "en": "{subject} is outside what this build can solve.",
}


def _refused(subject: str, result: QueryResult, *,
             lang: language.Lang | str) -> str:
    """Why no number came out, in the words the species already chose.

    A status alone says a query was turned away; the sentence says which of
    several very different things happened — an undefined quantity, a
    contradiction between the caller's own inputs, a case not built. The
    PARTS of it are on the envelope, so the only things to decide here are
    whether to say it and which language to say it in.
    """
    failure = result.estimator_failure or {}
    reason = refusals.said(failure, lang) if failure.get("failure_type") else ""
    if reason:
        return language.fill(_REFUSED_WITH_REASON, lang,
                             subject=subject, reason=reason)
    return language.fill(_REFUSED_OUT_OF_RANGE, lang, subject=subject)


_NUMERIC_BLOCK_MISSING: language.Words = {
    "zh": "（数值结果整段缺失）",
    "en": " (the whole numeric block is absent)",
}
_ONLY_AN_INTERVAL_CAME: language.Words = {
    "zh": "（只给出了区间 [{low}, {high}]）",
    "en": " (only the interval [{low}, {high}] came back)",
}
_SOLVED_WITHOUT_A_POINT: language.Words = {
    "zh": "{subject}：内核状态标为「已解出点值」，但结果里没有点值{detail}。这是"
          "内核输出自相矛盾，本条不可采信——请把该查询连同这条结果一并报给维护"
          "者。",
    "en": "{subject}: the kernel's status says a point value was solved for, "
          "and the result carries none{detail}. That is the kernel "
          "contradicting itself, so this line cannot be relied on — please "
          "send the query and this result to the maintainers.",
}


def _solved_without_point(subject: str, result: QueryResult, *,
                          lang: language.Lang | str) -> str:
    """The sentence for the value-state nothing else here can describe.

    A status says how far the kernel got; ``NumericResult.value`` says
    whether a point came out. They are two facts, carried separately, so
    they can disagree — and when they do, every other sentence this
    module owns is a fluent, credible description of some *other*
    situation ("结果未分类", "在当前结构下不可识别"), which the reader has
    no way to tell apart from the truth. A contradiction the reader
    cannot see is worse than one shouted at them, so this names the
    contradiction itself and withholds the answer rather than borrowing
    a neighbouring branch's words for it.
    """
    numeric = result.numeric_result
    if numeric is None:
        detail = language.fill(_NUMERIC_BLOCK_MISSING, lang)
    elif numeric.interval is not None:
        detail = language.fill(_ONLY_AN_INTERVAL_CAME, lang,
                               low=_format_number(numeric.interval.low),
                               high=_format_number(numeric.interval.high))
    else:
        detail = ""
    return language.fill(_SOLVED_WITHOUT_A_POINT, lang,
                         subject=subject, detail=detail)


_MISSING_ITEM: language.Words = {"zh": "缺：{name}", "en": "missing: {name}"}
_MISSING_BECAUSE: language.Words = {
    "zh": "（原因：{reason}）", "en": " (because: {reason})",
}
_NEXT_STEP: language.Words = {
    "zh": "；下一步 {action}（优先级 {priority}）",
    "en": "; next step: {action} (priority {priority})",
}


def _describe_needs_investigation(result: QueryResult, *,
                                  lang: language.Lang | str) -> str:
    """Render the '缺什么 / 为什么缺 / 下一步做什么' envelope.

    Pulls reasons out of ``missing_information`` and aligns each item
    with the matching ``InvestigationRequest`` (by target = missing
    item name, which is how ``investigation_pusher`` builds them).

    Returns empty string when there are no missing items so callers
    can concatenate unconditionally.
    """
    if not result.missing_information:
        return ""

    # Action and priority are set together on one request, so they travel
    # together: a lone `action` lookup cannot tell mypy — or a reader —
    # that the matching priority is there too.
    reqs_by_target: dict[str, tuple["InvestigationAction", "Priority"]] = {
        req.target: (req.action, req.priority)
        for req in result.investigation_requests
    }

    sentences: list[str] = []
    for m in result.missing_information:
        parts = [language.fill(_MISSING_ITEM, lang, name=m.name)]
        why = gaps.said(m, lang)
        if why:
            parts.append(language.fill(_MISSING_BECAUSE, lang, reason=why))
        req_pair = reqs_by_target.get(m.name)
        if req_pair is not None:
            action, prio = req_pair
            action_label = language.gloss(_ACTION_PHRASE, action, lang,
                                          unknown=action.value)
            prio_label = language.gloss(_PRIORITY_PHRASE, prio, lang,
                                        unknown=prio.value)
            parts.append(language.fill(_NEXT_STEP, lang, action=action_label,
                                       priority=prio_label))
        sentences.append("".join(parts)
                         + language.fill(language.FULL_STOP, lang))
    return language.sentences(*sentences, lang=lang)


_IDENTIFY_NO_RESULT: language.Words = {
    "zh": "识别结果缺失。", "en": "the identification result is absent.",
}
_IDENTIFY_NOT_IDENTIFIABLE: language.Words = {
    "zh": "在当前结构下该干预量不可识别。",
    "en": "under this structure the interventional quantity is not "
          "identifiable.",
}
_IDENTIFY_NO_FORMULA: language.Words = {
    "zh": "该干预量可识别，但本轮未返回具体公式。",
    "en": "the interventional quantity is identifiable, but no formula came "
          "back this round.",
}
_IDENTIFY_VIA_BACKDOOR: language.Words = {
    "zh": "该干预量可通过后门调整识别，调整集 {set} 足以堵住所有后门路径{size}。",
    "en": "the interventional quantity is identifiable by back-door "
          "adjustment: the set {set} blocks every back-door path{size}.",
}
_IDENTIFY_NO_ADJUSTMENT: language.Words = {
    "zh": "该干预量无需后门调整即可识别，观察分布本身给出答案。",
    "en": "the interventional quantity is identifiable with no back-door "
          "adjustment at all: the observational distribution answers it.",
}
_IDENTIFY_IDENTIFIABLE: language.Words = {
    "zh": "该干预量可识别。",
    "en": "the interventional quantity is identifiable.",
}
_IDENTIFY_UNCLASSIFIED: language.Words = {
    "zh": "识别结果未分类。",
    "en": "the identification result falls into no branch here.",
}


def _explain_identify(result: QueryResult, stmt=None, *,
                      lang: language.Lang | str) -> str:
    sr = result.structural_result
    if sr is None:
        return language.fill(_IDENTIFY_NO_RESULT, lang)
    if sr.value is False:
        return language.fill(_IDENTIFY_NOT_IDENTIFIABLE, lang)
    if sr.value is True:
        if result.formula is None:
            return language.fill(_IDENTIFY_NO_FORMULA, lang)

        # Walk the formula to pick up every SumExpr.over, not just
        # the outermost. Multi-var adjustment used to degrade here.
        adj = formula_builder.adjustment_atoms(result.formula)
        if adj:
            size_note = (language.fill(_ADJUSTMENT_SIZE, lang, count=len(adj))
                         if len(adj) > 1 else "")
            return language.fill(_IDENTIFY_VIA_BACKDOOR, lang,
                                 set=_format_atom_set(adj), size=size_note)

        # No SumExpr in the formula ⇒ empty adjustment; the observation
        # distribution itself identifies the quantity.
        if isinstance(result.formula, ProbabilityRefExpr):
            return language.fill(_IDENTIFY_NO_ADJUSTMENT, lang)
        return language.fill(_IDENTIFY_IDENTIFIABLE, lang)
    return language.fill(_IDENTIFY_UNCLASSIFIED, lang)


_CONDITIONING_EVENT_IS_NULL: language.Words = {
    "zh": "该条件反事实 {quantity} 未定义：条件事件 δ 的概率为 0（效力违反或不同"
          "世界断言冲突），无法作为条件。",
    "en": "the conditional counterfactual {quantity} is undefined: the "
          "conditioning event δ has probability 0 (an efficacy violation, or "
          "assertions in different worlds that conflict), so nothing can be "
          "conditioned on it.",
}
_CONJUNCTION_NOT_IDENTIFIABLE: language.Words = {
    "zh": "该反事实合取 {quantity} 在当前结构下不可识别（{algorithm} 报出 "
          "w-graph / 下标冲突见证，观察数据无法给出估计式）。",
    "en": "the counterfactual conjunction {quantity} is not identifiable "
          "under this structure ({algorithm} returned a w-graph / subscript "
          "conflict witness, and observational data yields no estimand).",
}
_CONJUNCTION_SELF_CONTRADICTORY: language.Words = {
    "zh": "该反事实合取的分子自相矛盾（不同世界的断言冲突），因此 {quantity}=0。",
    "en": "the counterfactual conjunction's numerator contradicts itself "
          "(assertions in different worlds conflict), so {quantity}=0.",
}
_CONJUNCTION_IDENTIFIABLE: language.Words = {
    "zh": "该反事实合取 {quantity} 可识别：{algorithm} 已把它约化为观察分布上的估"
          "计式。",
    "en": "the counterfactual conjunction {quantity} is identifiable: "
          "{algorithm} reduced it to an estimand over the observational "
          "distribution.",
}
_CONJUNCTION_UNCLASSIFIED: language.Words = {
    "zh": "反事实合取查询：结果未分类。",
    "en": "counterfactual-conjunction query: the result falls into no branch "
          "here.",
}


def _explain_counterfactual_conjunction(result: QueryResult, stmt=None, *,
                                        lang: language.Lang | str) -> str:
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
            base = language.fill(_CONDITIONING_EVENT_IS_NULL, lang,
                                 quantity=quantity)
        else:
            base = language.fill(_CONJUNCTION_NOT_IDENTIFIABLE, lang,
                                 quantity=quantity, algorithm=algo)
        gap = _describe_needs_investigation(result, lang=lang)
        return f"{base}{gap}" if gap else base
    sr = result.structural_result
    if sr is not None and sr.value is True:
        if isinstance(result.formula, ConstantExpr) and result.formula.value == 0.0:
            return language.fill(_CONJUNCTION_SELF_CONTRADICTORY, lang,
                                 quantity=quantity)
        return language.fill(_CONJUNCTION_IDENTIFIABLE, lang,
                             quantity=quantity, algorithm=algo)
    return language.fill(_CONJUNCTION_UNCLASSIFIED, lang)


_PROXIMAL_NOT_IDENTIFIABLE: language.Words = {
    "zh": "该效应 P(Y|do(X)) 在未观测混杂下近端不可识别：所声明的两个 proxy 不构"
          "成 Miao model (f) 结构（治疗侧 proxy 泄漏到结局、结局侧 proxy 泄漏到治"
          "疗，或 U 之外还有未阻断的混杂）。",
    "en": "the effect P(Y|do(X)) is not proximally identifiable under "
          "unmeasured confounding: the two proxies declared do not form Miao "
          "model (f) (the treatment-side proxy leaks into the outcome, the "
          "outcome-side proxy leaks into the treatment, or confounding "
          "beyond U is left unblocked).",
}
_PROXIMAL_IDENTIFIABLE: language.Words = {
    "zh": "该效应 P(Y|do(X)) 在未观测混杂 {latent} 下近端可识别：借治疗侧 proxy "
          "{treatment_proxy} 与结局侧 proxy {outcome_proxy}（Miao model f），可由 "
          "P(y|Z,x)·P(W|Z,x)⁻¹·P(W) 反演 Z×W 测量通道从数据恢复 ATE（需 proxy 对 "
          "{latent} 足够相关，rank 条件在数据上核验）。",
    "en": "the effect P(Y|do(X)) is proximally identifiable under the "
          "unmeasured confounder {latent}: through the treatment-side proxy "
          "{treatment_proxy} and the outcome-side proxy {outcome_proxy} "
          "(Miao model f), the ATE is recoverable from data by inverting the "
          "Z×W measurement channel as P(y|Z,x)·P(W|Z,x)⁻¹·P(W) (the proxies "
          "have to be related to {latent} strongly enough, and the rank "
          "condition is checked against the data).",
}
_PROXIMAL_IDENTIFIABLE_PLAIN: language.Words = {
    "zh": "该效应 P(Y|do(X)) 在未观测混杂下近端可识别（Miao model f）。",
    "en": "the effect P(Y|do(X)) is proximally identifiable under unmeasured "
          "confounding (Miao model f).",
}
_PROXIMAL_UNCLASSIFIED: language.Words = {
    "zh": "近端效应查询：结果未分类。",
    "en": "proximal-effect query: the result falls into no branch here.",
}


def _explain_proximal_effect(result: QueryResult, stmt=None, *,
                             lang: language.Lang | str) -> str:
    """Proximal causal inference (Miao-Geng-Tchetgen 2018 model (f))."""
    from ..types import ProximalEffectQuery

    q = (
        stmt.query
        if stmt is not None and isinstance(stmt.query, ProximalEffectQuery)
        else None
    )
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        base = language.fill(_PROXIMAL_NOT_IDENTIFIABLE, lang)
        gap = _describe_needs_investigation(result, lang=lang)
        return f"{base}{gap}" if gap else base
    sr = result.structural_result
    if sr is not None and sr.value is True:
        if q is not None:
            return language.fill(
                _PROXIMAL_IDENTIFIABLE, lang,
                latent=q.latent.predicate,
                treatment_proxy=q.treatment_proxy.predicate,
                outcome_proxy=q.outcome_proxy.predicate,
            )
        return language.fill(_PROXIMAL_IDENTIFIABLE_PLAIN, lang)
    return language.fill(_PROXIMAL_UNCLASSIFIED, lang)


_EFFECT_GIVEN: language.Words = {
    "zh": "，条件 {given}", "en": ", given {given}",
}
_THE_INTERVENTIONAL_QUANTITY: language.Words = {
    "zh": "该干预量", "en": "the interventional quantity",
}
_EQUALS: language.Words = {"zh": "{quantity} = {value}。",
                           "en": "{quantity} = {value}."}
_EFFECT_NOT_IDENTIFIABLE: language.Words = {
    "zh": "{quantity} 在当前结构下不可识别（无有效后门调整集）。",
    "en": "{quantity} is not identifiable under this structure (no valid "
          "back-door adjustment set).",
}
_EFFECT_IDENTIFIABLE: language.Words = {
    "zh": "{quantity} 可识别。", "en": "{quantity} is identifiable.",
}
_UNCLASSIFIED: language.Words = {
    "zh": "{quantity}：结果未分类。",
    "en": "{quantity}: the result falls into no branch here.",
}


def _explain_effect(result: QueryResult, stmt=None, *,
                    lang: language.Lang | str) -> str:
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
            language.fill(_EFFECT_GIVEN, lang,
                          given=", ".join(_labeled_value(g) for g in q.given))
            if q.given else ""
        )
        quantity = f"P({target_desc} | {intervention_desc}{given_desc})"
    else:
        quantity = language.fill(_THE_INTERVENTIONAL_QUANTITY, lang)

    # Enter on the status alone: the status is the kernel's claim about
    # this query, and a renderer that quietly overrules it on a missing
    # payload hands the reader the next branch's sentence instead.
    if result.status is ResultStatus.NUMERICALLY_SOLVED:
        numeric = result.numeric_result
        if numeric is None or numeric.value is None:
            return _solved_without_point(quantity, result, lang=lang)
        return (
            language.fill(_EQUALS, lang, quantity=quantity,
                          value=_format_number(numeric.value))
            + _describe_adjustment(result.formula, lang=lang)
        )

    sr = result.structural_result
    if sr is not None and sr.value is False:
        return language.fill(_EFFECT_NOT_IDENTIFIABLE, lang, quantity=quantity)

    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        pieces = [language.fill(_EFFECT_IDENTIFIABLE, lang, quantity=quantity)]
        adj = _describe_adjustment(result.formula, lang=lang)
        if adj:
            pieces.append(adj)
        gap = _describe_needs_investigation(result, lang=lang)
        if gap:
            pieces.append(gap)
        return "".join(pieces)

    return language.fill(_UNCLASSIFIED, lang, quantity=quantity)


_THE_CONDITIONAL_PROBABILITY: language.Words = {
    "zh": "该条件概率", "en": "the conditional probability",
}
_NOT_COMPUTABLE_YET: language.Words = {
    "zh": "{quantity} 暂无法计算。",
    "en": "{quantity} cannot be computed yet.",
}


def _explain_probability(result: QueryResult, stmt=None, *,
                         lang: language.Lang | str) -> str:
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
        quantity = language.fill(_THE_CONDITIONAL_PROBABILITY, lang)

    if result.status is ResultStatus.NUMERICALLY_SOLVED:
        numeric = result.numeric_result
        if numeric is None or numeric.value is None:
            return _solved_without_point(quantity, result, lang=lang)
        return language.fill(_EQUALS, lang, quantity=quantity,
                             value=_format_number(numeric.value))

    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        head = language.fill(_NOT_COMPUTABLE_YET, lang, quantity=quantity)
        gap = _describe_needs_investigation(result, lang=lang)
        return f"{head}{gap}" if gap else head

    return language.fill(_UNCLASSIFIED, lang, quantity=quantity)


_CELL_INSTRUMENT: language.Words = {
    "zh": "，工具变量 `{instrument}`",
    "en": ", instrument `{instrument}`",
}
_CELL_POINT: language.Words = {
    "zh": "反事实单格 = {value}（点识别）",
    "en": "the counterfactual cell = {value} (point identified)",
}
_CELL_INTERVAL: language.Words = {
    "zh": "反事实单格 ∈ [{low}, {high}]（区间，非点）",
    "en": "the counterfactual cell ∈ [{low}, {high}] (an interval, not a "
          "point)",
}
#: The pair of ci keys on a counterfactual cell, and what it holds. This
#: surface was the fourth to work that out from ``point is not None``, in
#: its own two words — one of which ("区间自身的抽样带") was a fourth
#: name for what the vocabulary calls an outer band (#419).
_CELL_CI = intervals.pair_at(
    "numeric_estimate.counterfactual_cell", "ci_lower", "ci_upper")
_CELL_BAND: language.Words = {
    "zh": "，{band} [{low}, {high}]", "en": ", {band} [{low}, {high}]",
}
_CELL_MONOTONICITY_NEARLY_REFUTED: language.Words = {
    "zh": "注意：{share}% 的重抽样在所声明的单调性下无解，说明这条假设离被数据推翻"
          "很近。",
    "en": "Note: {share}% of the resamples have no solution under the "
          "monotonicity declared, which says that assumption is close to "
          "being refuted by the data.",
}
_CELL_FROM_DATA: language.Words = {
    "zh": "{head}（从数据算得，{provenance}）。{tail}",
    "en": "{head} (computed from data, {provenance}). {tail}",
}


def _explain_counterfactual_cell_data(cell: dict, *,
                                      lang: language.Lang | str) -> str:
    """Render the DATA-recovered cell. Reads ``extensions.counterfactual_cell``
    (attached by the estimation dispatch); re-runs nothing."""
    prov = risk_provenance.describe(
        cell.get("interventional_risk_provenance"), lang
    )
    # The licence says what kind of thing was leaned on; this says which
    # column it was. A reader told "a response-function polytope" and not
    # which variable carried it cannot go and check the assumption.
    if cell.get("instrument"):
        prov += language.fill(_CELL_INSTRUMENT, lang,
                              instrument=cell["instrument"])
    point = cell.get("point")
    if point is not None:
        head = language.fill(_CELL_POINT, lang, value=_format_number(point))
    else:
        # ``lower`` / ``upper`` are the cell block's non-optional fields
        # (``point`` is the optional one) — index, do not ``.get``: their
        # absence is a broken writer, not an interval-free answer.
        head = language.fill(_CELL_INTERVAL, lang,
                             low=_format_number(cell["lower"]),
                             high=_format_number(cell["upper"]))
    ci_lo, ci_hi = cell.get("ci_lower"), cell.get("ci_upper")
    if ci_lo is not None and ci_hi is not None:
        band = language.fill(
            intervals.width_or_unstated(_CELL_CI, cell)[1], lang)
        head += language.fill(_CELL_BAND, lang, band=band,
                              low=_format_number(ci_lo),
                              high=_format_number(ci_hi))
    refuted = cell.get("bootstrap_draws_infeasible") or 0
    used = cell.get("bootstrap_draws_used") or 0
    tail = ""
    if refuted and (used + refuted):
        share = refuted / (used + refuted)
        tail = language.fill(_CELL_MONOTONICITY_NEARLY_REFUTED, lang,
                             share=_format_number(share * 100))
    return language.fill(_CELL_FROM_DATA, lang,
                         head=head, provenance=prov, tail=tail)


_THE_COUNTERFACTUAL_QUERY: language.Words = {
    "zh": "反事实查询", "en": "the counterfactual query",
}
_COUNTERFACTUAL_POINT: language.Words = {
    "zh": "反事实查询已得到点值结果。P(counterfactual target) = {value}。",
    "en": "the counterfactual query has a point value. P(counterfactual "
          "target) = {value}.",
}
_COUNTERFACTUAL_BOUNDED: language.Words = {
    "zh": "反事实查询当前得到界而非点值。区间为 [{low}, {high}]。",
    "en": "the counterfactual query has bounds rather than a point value. "
          "The interval is [{low}, {high}].",
}
_COUNTERFACTUAL_NO_BOUNDS_YET: language.Words = {
    "zh": "反事实查询暂时还算不出 bounds。",
    "en": "the counterfactual query cannot be bounded yet.",
}
_COUNTERFACTUAL_NEEDS_ASSUMPTION: language.Words = {
    "zh": "反事实查询还缺少必要假设。",
    "en": "the counterfactual query is still short of an assumption it "
          "needs.",
}
_COUNTERFACTUAL_UNCLASSIFIED: language.Words = {
    "zh": "反事实查询：结果未分类。",
    "en": "counterfactual query: the result falls into no branch here.",
}


def _explain_counterfactual(result: QueryResult, stmt=None, *,
                            lang: language.Lang | str) -> str:
    cell = (result.extensions or {}).get(blocks.Block.COUNTERFACTUAL_CELL)
    if cell:
        return _explain_counterfactual_cell_data(cell, lang=lang)
    numeric = result.numeric_result
    subject = language.fill(_THE_COUNTERFACTUAL_QUERY, lang)
    if result.status is ResultStatus.COUNTERFACTUAL_SOLVED:
        if numeric is None or numeric.value is None:
            return _solved_without_point(subject, result, lang=lang)
        return language.fill(_COUNTERFACTUAL_POINT, lang,
                             value=_format_number(numeric.value))
    if (
        result.status is ResultStatus.COUNTERFACTUAL_BOUNDED
        and numeric is not None
        and numeric.interval is not None
    ):
        interval = numeric.interval
        return language.fill(_COUNTERFACTUAL_BOUNDED, lang,
                             low=_format_number(interval.low),
                             high=_format_number(interval.high))
    if result.status is ResultStatus.OUTSIDE_LANGUAGE:
        return _refused(subject, result, lang=lang)
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        head = language.fill(_COUNTERFACTUAL_NO_BOUNDS_YET, lang)
        gap = _describe_needs_investigation(result, lang=lang)
        return f"{head}{gap}" if gap else head
    if result.status is ResultStatus.NEEDS_ASSUMPTION:
        head = language.fill(_COUNTERFACTUAL_NEEDS_ASSUMPTION, lang)
        gap = _describe_needs_investigation(result, lang=lang)
        return f"{head}{gap}" if gap else head
    return language.fill(_COUNTERFACTUAL_UNCLASSIFIED, lang)


_THE_CAUSATION_QUERY: language.Words = {
    "zh": "因果概率查询", "en": "the probabilities-of-causation query",
}
_CAUSATION_NOT_YET: language.Words = {
    "zh": "因果概率（PN/PS/PNS）暂时算不出。",
    "en": "the probabilities of causation (PN/PS/PNS) cannot be computed "
          "yet.",
}
_CAUSATION_UNCLASSIFIED: language.Words = {
    "zh": "因果概率查询：结果未分类。",
    "en": "probabilities-of-causation query: the result falls into no branch "
          "here.",
}
_CAUSATION_POINT: language.Words = {
    "zh": "{value}（点识别）", "en": "{value} (point identified)",
}
_CAUSATION_BOUNDS: language.Words = {
    "zh": "[{low}, {high}]（界）", "en": "[{low}, {high}] (bounds)",
}
_CAUSATION_ALL_THREE: language.Words = {
    "zh": "因果归因概率（Tian-Pearl 2000，{provenance}）：必要性 PN = {pn}；充分性 "
          "PS = {ps}；必要且充分 PNS = {pns}。",
    "en": "probabilities of causation (Tian-Pearl 2000, {provenance}): "
          "necessity PN = {pn}; sufficiency PS = {ps}; necessity and "
          "sufficiency PNS = {pns}.",
}


def _explain_causation(result: QueryResult, stmt=None, *,
                       lang: language.Lang | str) -> str:
    """Render PN / PS / PNS (probabilities of causation, Tian-Pearl 2000).

    Reads the ``extensions.causation`` envelope the scheduler attached;
    re-runs no reasoning. PN (necessity / 归因) is the headline; PS
    (sufficiency) and PNS round out the picture.
    """
    if result.status is ResultStatus.OUTSIDE_LANGUAGE:
        return _refused(language.fill(_THE_CAUSATION_QUERY, lang), result,
                        lang=lang)
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result, lang=lang)
        base = language.fill(_CAUSATION_NOT_YET, lang)
        return f"{base}{gap}" if gap else base

    c = (result.extensions or {}).get(blocks.Block.CAUSATION)
    if not c:
        return language.fill(_CAUSATION_UNCLASSIFIED, lang)

    def _q(block: dict) -> str:
        if block.get("point") is not None:
            return language.fill(_CAUSATION_POINT, lang,
                                 value=_format_number(block["point"]))
        return language.fill(_CAUSATION_BOUNDS, lang,
                             low=_format_number(block["lower"]),
                             high=_format_number(block["upper"]))

    # A lookup rather than a branch: this block reaches here from theta and
    # from data, and an ``if/else`` over a two-value domain answered the
    # data path's licences with the other path's sentence.
    prov = risk_provenance.describe(
        c.get("interventional_risk_provenance"), lang)
    return language.fill(_CAUSATION_ALL_THREE, lang, provenance=prov,
                         pn=_q(c["pn"]), ps=_q(c["ps"]), pns=_q(c["pns"]))


_SCM_NOT_YET: language.Words = {
    "zh": "线性 SCM 反事实点暂时算不出（结构方程或单元观测不全）。",
    "en": "the linear-SCM counterfactual point cannot be computed yet (the "
          "structural equations or this unit's observations are "
          "incomplete).",
}
_SCM_UNCLASSIFIED: language.Words = {
    "zh": "线性 SCM 反事实查询：结果未分类。",
    "en": "linear-SCM counterfactual query: the result falls into no branch "
          "here.",
}
_SCM_POINT: language.Words = {
    "zh": "在已知线性结构方程下，对这个单元做 do({variable}={value}),{target} 的反"
          "事实值 = {target_value}(Pearl 三步法：溯因-干预-预测)。",
    "en": "under the linear structural equations given, doing "
          "do({variable}={value}) to this unit puts {target} at the "
          "counterfactual value {target_value} (Pearl's three steps: "
          "abduction, action, prediction).",
}


def _explain_scm_counterfactual(result: QueryResult, stmt=None, *,
                                lang: language.Lang | str) -> str:
    """Render a deterministic linear-SCM counterfactual point (Pearl
    Primer §4.2). Reads ``extensions.scm_counterfactual``; re-runs nothing."""
    if result.status is ResultStatus.NEEDS_INVESTIGATION:
        gap = _describe_needs_investigation(result, lang=lang)
        base = language.fill(_SCM_NOT_YET, lang)
        return f"{base}{gap}" if gap else base
    sc = (result.extensions or {}).get(blocks.Block.SCM_COUNTERFACTUAL)
    if not sc:
        return language.fill(_SCM_UNCLASSIFIED, lang)
    iv = sc.get("intervention", {})
    return language.fill(
        _SCM_POINT, lang,
        variable=iv.get("variable"), value=_format_number(iv.get("value")),
        target=sc.get("target"),
        target_value=_format_number(sc.get("target_value")),
    )


_CONFIDENCE_SUFFIX: language.Words = {
    "zh": "综合可信度 {value}（最弱证据水平，按 min 规则聚合）。",
    "en": "Composite confidence {value} (the weakest evidence level, "
          "aggregated by the min rule).",
}


def _with_confidence_suffix(text: str, result: QueryResult, *,
                            lang: language.Lang | str) -> str:
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
    return text + language.fill(_CONFIDENCE_SUFFIX, lang,
                                value=_format_number(result.confidence))


_FRAMING_ONE_PREDICATE: language.Words = {
    "zh": "{predicate} 缺 {fields}",
    "en": "{predicate} never says {fields}",
}
_FRAMING_SUFFIX: language.Words = {
    "zh": "问题定义：{parts}。",
    "en": "Question definition: {parts}.",
}


def _with_framing_suffix(text: str, result: QueryResult, *,
                         lang: language.Lang | str) -> str:
    """Slice A0: append advisory 问题定义 clause for underspecified
    predicates. Advisory only — the numeric/structural verdict is
    already stated in ``text``; this just tells the reader which
    variables lack metadata that would make the question operational.
    """
    if not result.framing_notes:
        return text
    parts: list[str] = []
    for note in result.framing_notes:
        parts.append(language.fill(
            _FRAMING_ONE_PREDICATE, lang, predicate=note.predicate,
            fields=envelope_glossary.framing_fields_word(note.missing, lang),
        ))
    joined = language.fill(language.BETWEEN_STATEMENTS, lang).join(parts)
    return text + language.fill(_FRAMING_SUFFIX, lang, parts=joined)


# One explainer per kind of question, bound to the vocabulary rather than
# chained. The chain that was here covered all ten and raised on anything
# else, which made this the one surface that was complete — the report's
# answer line had no branch at all, the report's question line tested for a
# string no query kind has, and the web answered seven kinds with a
# fallback. Binding moves this surface's guarantee from "the eleventh
# branch raises when a result arrives" to "a query kind without an
# explainer fails at import".
_EXPLAINERS = questions.bind({
    questions.CAUSE: _explain_cause,
    questions.ASSOC: _explain_assoc,
    questions.IDENTIFY: _explain_identify,
    questions.EFFECT: _explain_effect,
    questions.PROBABILITY: _explain_probability,
    questions.COUNTERFACTUAL: _explain_counterfactual,
    questions.CAUSATION: _explain_causation,
    questions.SCM_COUNTERFACTUAL: _explain_scm_counterfactual,
    questions.COUNTERFACTUAL_CONJUNCTION: _explain_counterfactual_conjunction,
    questions.PROXIMAL_EFFECT: _explain_proximal_effect,
})


def explain(
    result: QueryResult,
    lang: language.Lang | str = language.DEFAULT,
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

    ``lang`` has been in this signature since v0.1 and had nowhere to
    go: the language was part of the names of the things that make the
    sentences, so there was nothing to hand it to. What it selects
    among is :class:`themis.language.Lang`, and a value outside it is
    refused by name rather than against a literal here — a build gains
    a language by gaining a member, not by someone finding this line.
    The sentences below are now a function of it, all the way down.
    """
    try:
        language.Lang(lang)
    except ValueError:
        raise NotImplementedError(
            f"language {str(lang)!r} is not one this build answers in; "
            f"it answers in "
            f"{', '.join(sorted(str(x) for x in language.Lang))}"
        ) from None
    text = _EXPLAINERS[questions.reading_of(result.query_kind.value)](
        result, stmt, lang=lang)
    text = _with_confidence_suffix(text, result, lang=lang)
    text = _with_framing_suffix(text, result, lang=lang)
    return text
