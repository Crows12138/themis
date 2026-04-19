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
    ProbabilityRefExpr,
    QueryKind,
    QueryResult,
    SumExpr,
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
    return f"{atom.predicate}({args})"


def _format_atom_set(atoms) -> str:
    """Render a sequence of atoms as ``{a(x), b(x), ...}``."""
    labels = [_atom_label(a) for a in atoms]
    return "{" + ", ".join(labels) + "}"


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


def explain(result: QueryResult, lang: str = "zh") -> str:
    """Render a QueryResult as a plain-text explanation."""
    if lang != "zh":
        raise NotImplementedError(f"language '{lang}' not supported in v0.1")
    if result.query_kind == QueryKind.CAUSE:
        return _explain_cause_zh(result)
    if result.query_kind == QueryKind.ASSOC:
        return _explain_assoc_zh(result)
    if result.query_kind == QueryKind.IDENTIFY:
        return _explain_identify_zh(result)
    # Slice 5+: effect, probability.
    raise NotImplementedError(
        f"explainer for {result.query_kind.value} not implemented yet"
    )
